"""LLM client used for steps (c) classification and (d) narrative summary.

Design goals
------------
* **Batched** - classification sends many transactions per request (never one
  call per row), as required.
* **Resilient** - real network calls are wrapped in exponential-backoff retry
  (up to ``llm_max_retries``). The caller decides what to do when all retries
  are exhausted (we mark the batch ``llm_failed`` and continue).
* **Zero-config** - when no ``GEMINI_API_KEY`` is configured the client uses a
  deterministic local stub so ``docker compose up`` works with no secrets.
"""

from __future__ import annotations

import json
import logging
import re

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Cash Withdrawal",
    "Entertainment",
    "Other",
]

# Deterministic merchant -> category map for the local stub provider.
_MERCHANT_CATEGORY = {
    "swiggy": "Food",
    "zomato": "Food",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "irctc": "Travel",
    "makemytrip": "Travel",
    "ola": "Transport",
    "uber": "Transport",
    "jio recharge": "Utilities",
    "hdfc atm": "Cash Withdrawal",
    "bookmyshow": "Entertainment",
    "netflix": "Entertainment",
}


class LLMError(Exception):
    """Raised when an LLM call ultimately fails (after retries)."""


def _heuristic_category(merchant: str | None) -> str:
    key = (merchant or "").strip().lower()
    return _MERCHANT_CATEGORY.get(key, "Other")


def _extract_json(text: str) -> dict | list:
    """Pull the first JSON object/array out of a possibly noisy LLM response."""
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        raise LLMError("No JSON found in LLM response")
    return json.loads(match.group(1))


class LLMClient:
    """Provider-agnostic facade over the configured LLM backend."""

    def __init__(self) -> None:
        self.provider = settings.effective_llm_provider
        self._model = None
        if self.provider == "gemini":
            self._init_gemini()

    def _init_gemini(self) -> None:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(settings.llm_model)

    # ----- Low-level call with retry --------------------------------------

    def _gemini_generate(self, prompt: str) -> str:
        @retry(
            stop=stop_after_attempt(settings.llm_max_retries),
            wait=wait_exponential(multiplier=settings.llm_backoff_base, min=1, max=30),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def _call() -> str:
            response = self._model.generate_content(prompt)
            if not getattr(response, "text", None):
                raise LLMError("Empty response from Gemini")
            return response.text

        try:
            return _call()
        except Exception as exc:  # noqa: BLE001 - normalise to LLMError for the caller
            raise LLMError(f"Gemini call failed after retries: {exc}") from exc

    # ----- (c) Classification ---------------------------------------------

    def classify_batch(self, items: list[dict]) -> dict[str, str]:
        """Classify a batch of uncategorised transactions.

        ``items`` is a list of ``{"ref": str, "merchant": str, "notes": str}``.
        Returns a mapping ``ref -> category`` (one of ALLOWED_CATEGORIES).
        Raises ``LLMError`` if the (real) provider fails after all retries.
        """
        if not items:
            return {}

        if self.provider == "stub":
            return {item["ref"]: _heuristic_category(item.get("merchant")) for item in items}

        prompt = self._build_classification_prompt(items)
        raw = self._gemini_generate(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            raise LLMError("Classification response was not a JSON object")

        result: dict[str, str] = {}
        for item in items:
            ref = item["ref"]
            category = parsed.get(ref) or parsed.get(str(ref))
            if category not in ALLOWED_CATEGORIES:
                # Defensive: fall back rather than store junk.
                category = _heuristic_category(item.get("merchant"))
            result[ref] = category
        return result

    def _build_classification_prompt(self, items: list[dict]) -> str:
        catalogue = ", ".join(ALLOWED_CATEGORIES)
        lines = [
            f'  "{item["ref"]}": merchant="{item.get("merchant") or ""}", '
            f'notes="{item.get("notes") or ""}"'
            for item in items
        ]
        return (
            "You are a financial transaction classifier. Assign exactly one "
            f"category from this list to each transaction: {catalogue}.\n"
            "Respond ONLY with a JSON object mapping each transaction id to its "
            "category string. No prose, no markdown.\n\n"
            "Transactions:\n" + "\n".join(lines) + "\n\n"
            'Example response: {"TXN1": "Food", "TXN2": "Shopping"}'
        )

    # ----- (d) Narrative summary ------------------------------------------

    def summarize(self, stats: dict) -> dict:
        """Produce the structured narrative summary from pre-computed stats.

        Returns a dict with keys: narrative, risk_level. (Numeric aggregates are
        computed deterministically by the caller; the LLM only writes the prose
        and assigns the risk level.) Raises ``LLMError`` on provider failure.
        """
        if self.provider == "stub":
            return self._stub_summary(stats)

        prompt = self._build_summary_prompt(stats)
        raw = self._gemini_generate(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            raise LLMError("Summary response was not a JSON object")
        narrative = str(parsed.get("narrative", "")).strip()
        risk = str(parsed.get("risk_level", "")).strip().lower()
        if risk not in ("low", "medium", "high"):
            risk = self._stub_summary(stats)["risk_level"]
        if not narrative:
            narrative = self._stub_summary(stats)["narrative"]
        return {"narrative": narrative, "risk_level": risk}

    def _build_summary_prompt(self, stats: dict) -> str:
        return (
            "You are a financial analyst. Given the aggregated statistics below, "
            "write a concise spending review.\n"
            "Respond ONLY as JSON with keys 'narrative' (2-3 sentences) and "
            "'risk_level' (one of low/medium/high). Base risk on the anomaly "
            "ratio and presence of suspicious/failed transactions.\n\n"
            f"Statistics:\n{json.dumps(stats, indent=2, default=str)}\n\n"
            'Example: {"narrative": "...", "risk_level": "low"}'
        )

    @staticmethod
    def _stub_summary(stats: dict) -> dict:
        total_txns = stats.get("total_transactions", 0) or 0
        anomalies = stats.get("anomaly_count", 0) or 0
        ratio = (anomalies / total_txns) if total_txns else 0
        if ratio >= 0.2 or anomalies >= 10:
            risk = "high"
        elif ratio >= 0.08 or anomalies > 0:
            risk = "medium"
        else:
            risk = "low"

        top = stats.get("top_merchants", []) or []
        top_names = ", ".join(m["merchant"] for m in top[:3]) if top else "n/a"
        narrative = (
            f"Across {total_txns} transactions, spending totalled "
            f"INR {stats.get('total_spend_inr', 0):,.2f} and "
            f"USD {stats.get('total_spend_usd', 0):,.2f}, led by {top_names}. "
            f"{anomalies} transaction(s) were flagged as anomalous, indicating a "
            f"{risk} overall risk profile."
        )
        return {"narrative": narrative, "risk_level": risk}
