"""Job endpoints: upload, status, results, list."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Job, JobStatus, Transaction
from app.pipeline.tasks import process_job
from app.schemas import (
    AnomalySchema,
    CategoryBreakdownItem,
    JobCreatedResponse,
    JobListItem,
    JobResultsResponse,
    JobStatusResponse,
    JobSummarySchema,
    TransactionSchema,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/upload", response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreatedResponse:
    """Accept a CSV upload, persist a pending Job, enqueue processing, return id."""
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    content = await file.read()
    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_upload_bytes} bytes.",
        )

    # Basic structural validation: must contain a header line.
    try:
        header = content.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Unable to read CSV header.")
    if "," not in header:
        raise HTTPException(status_code=400, detail="CSV does not look comma-separated.")

    job = Job(filename=filename, status=JobStatus.pending)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Persist the raw CSV to the shared volume so the worker can read it.
    os.makedirs(settings.upload_dir, exist_ok=True)
    with open(os.path.join(settings.upload_dir, f"{job.id}.csv"), "wb") as fh:
        fh.write(content)

    # Enqueue the async processing task.
    process_job.delay(str(job.id))

    return JobCreatedResponse(job_id=job.id, status=job.status, filename=job.filename)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
def job_status(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Return job status; includes a summary when completed."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    summary = None
    if job.status == JobStatus.completed and job.summary is not None:
        summary = JobSummarySchema.model_validate(job.summary)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        summary=summary,
    )


@router.get("/{job_id}/results", response_model=JobResultsResponse)
def job_results(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobResultsResponse:
    """Return the full structured output for a completed job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.status.value}'. Results are available once completed.",
        )

    txns = db.scalars(select(Transaction).where(Transaction.job_id == job_id)).all()

    transactions = [TransactionSchema.model_validate(t) for t in txns]
    anomalies = [AnomalySchema.model_validate(t) for t in txns if t.is_anomaly]
    breakdown = _category_breakdown(txns)
    summary = JobSummarySchema.model_validate(job.summary) if job.summary else None

    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        row_count_raw=job.row_count_raw,
        row_count_clean=job.row_count_clean,
        transactions=transactions,
        anomalies=anomalies,
        category_breakdown=breakdown,
        summary=summary,
    )


@router.get("", response_model=list[JobListItem])
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[JobListItem]:
    """List all jobs, newest first. Optional ?status= filter."""
    stmt = select(Job).order_by(Job.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Job.status == status_filter)
    jobs = db.scalars(stmt).all()
    return [
        JobListItem(
            job_id=j.id,
            filename=j.filename,
            status=j.status,
            row_count_raw=j.row_count_raw,
            row_count_clean=j.row_count_clean,
            created_at=j.created_at,
        )
        for j in jobs
    ]


def _category_breakdown(txns: list[Transaction]) -> list[CategoryBreakdownItem]:
    agg: dict[str, dict] = {}
    for t in txns:
        cat = t.category or "Uncategorised"
        entry = agg.setdefault(
            cat, {"transaction_count": 0, "total_amount_inr": 0.0, "total_amount_usd": 0.0}
        )
        entry["transaction_count"] += 1
        if t.amount is not None:
            if (t.currency or "").upper() == "USD":
                entry["total_amount_usd"] += float(t.amount)
            else:
                entry["total_amount_inr"] += float(t.amount)
    return [
        CategoryBreakdownItem(
            category=cat,
            transaction_count=v["transaction_count"],
            total_amount_inr=round(v["total_amount_inr"], 2),
            total_amount_usd=round(v["total_amount_usd"], 2),
        )
        for cat, v in sorted(agg.items(), key=lambda kv: kv[1]["transaction_count"], reverse=True)
    ]
