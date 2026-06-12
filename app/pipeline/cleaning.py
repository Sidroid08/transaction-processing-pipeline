"""Step (a): Data cleaning.

Normalises raw CSV rows into clean, typed records:
  * date  -> ISO 8601 (datetime.date), handling DD-MM-YYYY and YYYY/MM/DD
  * amount -> Decimal, stripping ``$`` / thousands separators
  * currency -> upper-cased (INR / USD)
  * status -> upper-cased (SUCCESS / FAILED / PENDING)
  * category -> blanks filled with 'Uncategorised'
  * exact duplicate rows removed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

UNCATEGORISED = "Uncategorised"

# Explicit formats are tried first (fast, unambiguous for this dataset),
# then dateutil as a last resort with day-first preference.
_DATE_FORMATS = ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")

EXPECTED_COLUMNS = [
    "txn_id",
    "date",
    "merchant",
    "amount",
    "currency",
    "status",
    "category",
    "account_id",
    "notes",
]


@dataclass
class CleanResult:
    rows: list[dict] = field(default_factory=list)
    row_count_raw: int = 0
    row_count_clean: int = 0


def _blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def parse_date(raw) -> date | None:
    """Parse a messy date string into a ``date`` (ISO 8601 when serialised)."""
    if _blank(raw):
        return None
    text = str(raw).strip()
    from datetime import datetime

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Fallback for anything unexpected.
    try:
        from dateutil import parser as date_parser

        return date_parser.parse(text, dayfirst=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def clean_amount(raw) -> Decimal | None:
    """Strip currency symbols / separators and return a Decimal."""
    if _blank(raw):
        return None
    text = str(raw).strip()
    for ch in ("$", "₹", ",", " "):
        text = text.replace(ch, "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def normalize_currency(raw) -> str | None:
    if _blank(raw):
        return None
    return str(raw).strip().upper()


def normalize_status(raw) -> str | None:
    if _blank(raw):
        return None
    return str(raw).strip().upper()


def normalize_category(raw) -> str:
    if _blank(raw):
        return UNCATEGORISED
    return str(raw).strip()


def _clean_text(raw) -> str | None:
    if _blank(raw):
        return None
    return str(raw).strip()


def clean_dataframe(df: pd.DataFrame) -> CleanResult:
    """Clean a raw DataFrame of transactions and drop exact duplicate rows."""
    # Ensure all expected columns exist even if the CSV omits some.
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    raw_count = len(df)

    # Remove EXACT duplicate rows (all original columns identical) before typing.
    df = df.drop_duplicates(subset=EXPECTED_COLUMNS, keep="first").reset_index(drop=True)

    rows: list[dict] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "txn_id": _clean_text(row.get("txn_id")),
                "date": parse_date(row.get("date")),
                "merchant": _clean_text(row.get("merchant")),
                "amount": clean_amount(row.get("amount")),
                "currency": normalize_currency(row.get("currency")),
                "status": normalize_status(row.get("status")),
                "category": normalize_category(row.get("category")),
                "account_id": _clean_text(row.get("account_id")),
                "notes": _clean_text(row.get("notes")),
            }
        )

    return CleanResult(rows=rows, row_count_raw=raw_count, row_count_clean=len(rows))
