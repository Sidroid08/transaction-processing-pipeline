"""Unit tests for the data-cleaning step."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app.pipeline.cleaning import (
    UNCATEGORISED,
    clean_amount,
    clean_dataframe,
    normalize_currency,
    normalize_status,
    parse_date,
)


def test_parse_date_ddmmyyyy():
    assert parse_date("04-09-2024") == date(2024, 9, 4)
    assert parse_date("17-02-2024") == date(2024, 2, 17)


def test_parse_date_yyyymmdd_slash():
    assert parse_date("2024/02/05") == date(2024, 2, 5)
    assert parse_date("2024/09/05") == date(2024, 9, 5)


def test_parse_date_blank_returns_none():
    assert parse_date("") is None
    assert parse_date(None) is None


def test_clean_amount_strips_dollar():
    assert clean_amount("$11325.79") == Decimal("11325.79")
    assert clean_amount("6874.1") == Decimal("6874.1")
    assert clean_amount("1,234.50") == Decimal("1234.50")


def test_clean_amount_blank():
    assert clean_amount("") is None


def test_normalize_currency():
    assert normalize_currency("inr") == "INR"
    assert normalize_currency("Usd") == "USD"


def test_normalize_status():
    assert normalize_status("success") == "SUCCESS"
    assert normalize_status("Failed") == "FAILED"


def test_clean_dataframe_fills_category_and_dedupes():
    raw = pd.DataFrame(
        [
            {
                "txn_id": "T1",
                "date": "04-09-2024",
                "merchant": "Amazon",
                "amount": "$100.00",
                "currency": "inr",
                "status": "success",
                "category": "",
                "account_id": "ACC1",
                "notes": "",
            },
            # exact duplicate of T1
            {
                "txn_id": "T1",
                "date": "04-09-2024",
                "merchant": "Amazon",
                "amount": "$100.00",
                "currency": "inr",
                "status": "success",
                "category": "",
                "account_id": "ACC1",
                "notes": "",
            },
            {
                "txn_id": "T2",
                "date": "2024/01/04",
                "merchant": "Swiggy",
                "amount": "50",
                "currency": "INR",
                "status": "FAILED",
                "category": "Food",
                "account_id": "ACC1",
                "notes": "",
            },
        ]
    )
    result = clean_dataframe(raw)
    assert result.row_count_raw == 3
    assert result.row_count_clean == 2  # duplicate removed
    first = result.rows[0]
    assert first["category"] == UNCATEGORISED
    assert first["amount"] == Decimal("100.00")
    assert first["currency"] == "INR"
    assert first["status"] == "SUCCESS"
    assert first["date"] == date(2024, 9, 4)
