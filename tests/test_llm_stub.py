"""Unit tests for the LLM stub provider (offline, deterministic)."""

from __future__ import annotations

from app.llm.client import ALLOWED_CATEGORIES, LLMClient


def _stub_client(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "llm_provider", "stub", raising=False)
    monkeypatch.setattr(config.settings, "gemini_api_key", None, raising=False)
    return LLMClient()


def test_classify_batch_known_merchants(monkeypatch):
    client = _stub_client(monkeypatch)
    items = [
        {"ref": "T1", "merchant": "Swiggy", "notes": ""},
        {"ref": "T2", "merchant": "Amazon", "notes": ""},
        {"ref": "T3", "merchant": "IRCTC", "notes": ""},
        {"ref": "T4", "merchant": "Unknown Co", "notes": ""},
    ]
    result = client.classify_batch(items)
    assert result["T1"] == "Food"
    assert result["T2"] == "Shopping"
    assert result["T3"] == "Travel"
    assert result["T4"] == "Other"
    assert all(v in ALLOWED_CATEGORIES for v in result.values())


def test_summary_risk_levels(monkeypatch):
    client = _stub_client(monkeypatch)
    low = client.summarize({"total_transactions": 100, "anomaly_count": 0, "top_merchants": []})
    assert low["risk_level"] == "low"
    high = client.summarize({"total_transactions": 10, "anomaly_count": 5, "top_merchants": []})
    assert high["risk_level"] == "high"
    assert isinstance(low["narrative"], str) and low["narrative"]
