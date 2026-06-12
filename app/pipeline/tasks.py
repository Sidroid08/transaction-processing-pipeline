"""Celery task orchestrating the end-to-end processing pipeline.

Steps (run in order when a job is dequeued):
  a) clean      -> normalise + dedupe
  b) anomaly    -> per-account outliers + currency anomalies
  c) classify   -> batched LLM categorisation of uncategorised rows
  d) summarise  -> deterministic aggregates + single LLM narrative call
  e) retry      -> LLM calls retry w/ backoff; on exhaustion mark llm_failed
                   and continue (the job itself never fails because of the LLM)
"""

from __future__ import annotations

import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.llm.client import LLMClient, LLMError
from app.models import Job, JobStatus, JobSummary, Transaction
from app.pipeline.anomaly import detect_anomalies
from app.pipeline.cleaning import UNCATEGORISED, clean_dataframe

logger = logging.getLogger(__name__)


def _csv_path(job_id) -> str:
    return os.path.join(settings.upload_dir, f"{job_id}.csv")


@celery_app.task(name="app.pipeline.tasks.process_job", bind=True)
def process_job(self, job_id: str) -> dict:
    """Process a single uploaded CSV job by id."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            logger.error("Job %s not found", job_id)
            return {"job_id": job_id, "status": "missing"}

        job.status = JobStatus.processing
        db.commit()

        # --- (a) Clean ----------------------------------------------------
        df = pd.read_csv(_csv_path(job_id), dtype=str, keep_default_na=False)
        clean = clean_dataframe(df)
        job.row_count_raw = clean.row_count_raw
        job.row_count_clean = clean.row_count_clean

        # --- (b) Anomaly detection ---------------------------------------
        detect_anomalies(clean.rows)

        # --- (c) LLM classification (batched) ----------------------------
        llm = LLMClient()
        _classify_uncategorised(clean.rows, llm)

        # Persist transactions.
        tx_models = [_to_model(job_id, row) for row in clean.rows]
        db.add_all(tx_models)
        db.commit()

        # --- (d) Narrative summary (single LLM call) ---------------------
        summary = _build_summary(job_id, clean.rows, llm)
        db.add(summary)

        job.status = JobStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Job %s completed (%s clean rows)", job_id, clean.row_count_clean)
        return {"job_id": job_id, "status": "completed"}

    except Exception as exc:  # noqa: BLE001 - record any hard failure on the job
        logger.exception("Job %s failed", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.failed
            job.error_message = str(exc)[:2000]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        return {"job_id": job_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()


def _classify_uncategorised(rows: list[dict], llm: LLMClient) -> None:
    """Step (c): assign categories to rows missing one, in batches.

    A failed batch (after retries) is marked ``llm_failed`` and skipped - the
    job continues regardless.
    """
    targets = [r for r in rows if not r.get("category") or r["category"] == UNCATEGORISED]
    if not targets:
        return

    batch_size = settings.llm_batch_size
    for start in range(0, len(targets), batch_size):
        batch = targets[start : start + batch_size]
        items = [
            {
                "ref": r.get("txn_id") or f"row-{start + i}",
                "merchant": r.get("merchant"),
                "notes": r.get("notes"),
            }
            for i, r in enumerate(batch)
        ]
        try:
            mapping = llm.classify_batch(items)
            for item, row in zip(items, batch):
                category = mapping.get(item["ref"])
                if category:
                    row["llm_category"] = category
                    row["category"] = category
                    row["llm_raw_response"] = "ok"
        except LLMError as exc:
            logger.warning("Classification batch failed, marking llm_failed: %s", exc)
            for row in batch:
                row["llm_failed"] = True
                row["llm_raw_response"] = f"llm_failed: {exc}"[:1000]


def _build_summary(job_id, rows: list[dict], llm: LLMClient) -> JobSummary:
    """Step (d): deterministic aggregates + one LLM narrative call."""
    total_inr = Decimal("0")
    total_usd = Decimal("0")
    merchant_spend: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    anomaly_count = 0

    for row in rows:
        amt = row.get("amount")
        if amt is None:
            continue
        amt = Decimal(str(amt))
        currency = (row.get("currency") or "").upper()
        if currency == "USD":
            total_usd += amt
        else:  # default INR
            total_inr += amt
        if row.get("merchant"):
            merchant_spend[row["merchant"]] += amt
        if row.get("is_anomaly"):
            anomaly_count += 1

    top_merchants = [
        {"merchant": m, "total_amount": float(v)}
        for m, v in sorted(merchant_spend.items(), key=lambda kv: kv[1], reverse=True)[:3]
    ]

    stats = {
        "total_transactions": len(rows),
        "total_spend_inr": float(total_inr),
        "total_spend_usd": float(total_usd),
        "top_merchants": top_merchants,
        "anomaly_count": anomaly_count,
    }

    llm_failed = False
    try:
        narrative_data = llm.summarize(stats)
    except LLMError as exc:
        logger.warning("Summary LLM call failed, using deterministic fallback: %s", exc)
        narrative_data = LLMClient._stub_summary(stats)  # noqa: SLF001 - deliberate fallback
        llm_failed = True

    return JobSummary(
        job_id=job_id,
        total_spend_inr=total_inr,
        total_spend_usd=total_usd,
        top_merchants=top_merchants,
        anomaly_count=anomaly_count,
        narrative=narrative_data["narrative"],
        risk_level=narrative_data["risk_level"],
        llm_failed=llm_failed,
    )


def _to_model(job_id, row: dict) -> Transaction:
    return Transaction(
        job_id=job_id,
        txn_id=row.get("txn_id"),
        date=row.get("date"),
        merchant=row.get("merchant"),
        amount=row.get("amount"),
        currency=row.get("currency"),
        status=row.get("status"),
        category=row.get("category"),
        account_id=row.get("account_id"),
        notes=row.get("notes"),
        is_anomaly=row.get("is_anomaly", False),
        anomaly_reason=row.get("anomaly_reason"),
        llm_category=row.get("llm_category"),
        llm_raw_response=row.get("llm_raw_response"),
        llm_failed=row.get("llm_failed", False),
    )
