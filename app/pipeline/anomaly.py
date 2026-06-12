"""Step (b): Anomaly detection.

Two independent rules, both of which can fire on the same row:

  1. Statistical outlier - amount exceeds ``multiplier`` x the *account's* median
     amount (default 3x). The median is computed per ``account_id`` over the
     cleaned rows of this job.
  2. Currency anomaly - currency is USD while the merchant is a domestic-only
     brand (Swiggy, Ola, IRCTC, ...), which cannot legitimately charge in USD.
"""

from __future__ import annotations

import statistics
from decimal import Decimal

from app.config import settings


def detect_anomalies(rows: list[dict], multiplier: float | None = None) -> None:
    """Annotate each row in place with ``is_anomaly`` and ``anomaly_reason``."""
    multiplier = multiplier if multiplier is not None else settings.anomaly_median_multiplier

    # Per-account median of present amounts.
    amounts_by_account: dict[str, list[float]] = {}
    for row in rows:
        acc = row.get("account_id")
        amt = row.get("amount")
        if acc and amt is not None:
            amounts_by_account.setdefault(acc, []).append(float(amt))

    median_by_account = {
        acc: statistics.median(vals) for acc, vals in amounts_by_account.items() if vals
    }

    domestic = {m.lower() for m in settings.domestic_only_merchants}

    for row in rows:
        reasons: list[str] = []

        amt = row.get("amount")
        acc = row.get("account_id")
        if amt is not None and acc in median_by_account:
            median = median_by_account[acc]
            threshold = median * multiplier
            if median > 0 and float(amt) > threshold:
                reasons.append(
                    f"Amount {Decimal(str(amt))} exceeds {multiplier}x account median "
                    f"({median:.2f}) for {acc}"
                )

        currency = (row.get("currency") or "").upper()
        merchant = (row.get("merchant") or "").strip().lower()
        if currency == "USD" and merchant in domestic:
            reasons.append(
                f"Currency USD for domestic-only merchant '{row.get('merchant')}'"
            )

        row["is_anomaly"] = bool(reasons)
        row["anomaly_reason"] = reasons or None
