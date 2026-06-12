"""Unit tests for the anomaly-detection step."""

from __future__ import annotations

from decimal import Decimal

from app.pipeline.anomaly import detect_anomalies


def _row(**kw):
    base = {
        "txn_id": "T",
        "merchant": "Amazon",
        "amount": Decimal("100"),
        "currency": "INR",
        "account_id": "ACC1",
    }
    base.update(kw)
    return base


def test_statistical_outlier_flagged():
    rows = [
        _row(txn_id="a", amount=Decimal("100")),
        _row(txn_id="b", amount=Decimal("100")),
        _row(txn_id="c", amount=Decimal("100")),
        _row(txn_id="d", amount=Decimal("1000")),  # 10x median -> outlier
    ]
    detect_anomalies(rows)
    flagged = {r["txn_id"]: r["is_anomaly"] for r in rows}
    assert flagged["d"] is True
    assert flagged["a"] is False


def test_no_outlier_when_within_threshold():
    rows = [
        _row(txn_id="a", amount=Decimal("100")),
        _row(txn_id="b", amount=Decimal("200")),
        _row(txn_id="c", amount=Decimal("250")),  # below 3x median(200)=600
    ]
    detect_anomalies(rows)
    assert all(r["is_anomaly"] is False for r in rows)


def test_usd_domestic_merchant_flagged():
    rows = [
        _row(txn_id="a", merchant="Swiggy", currency="USD", amount=Decimal("100")),
        _row(txn_id="b", merchant="Swiggy", currency="INR", amount=Decimal("100")),
    ]
    detect_anomalies(rows)
    by_id = {r["txn_id"]: r for r in rows}
    assert by_id["a"]["is_anomaly"] is True
    assert "USD" in by_id["a"]["anomaly_reason"][0]
    assert by_id["b"]["is_anomaly"] is False


def test_both_reasons_combine():
    rows = [
        _row(txn_id="a", merchant="IRCTC", amount=Decimal("100")),
        _row(txn_id="b", merchant="IRCTC", amount=Decimal("100")),
        _row(txn_id="c", merchant="IRCTC", currency="USD", amount=Decimal("5000")),
    ]
    detect_anomalies(rows)
    c = next(r for r in rows if r["txn_id"] == "c")
    assert c["is_anomaly"] is True
    assert len(c["anomaly_reason"]) == 2
