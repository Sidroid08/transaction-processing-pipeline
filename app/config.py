"""Application configuration loaded from environment variables.

All settings have sensible defaults so the stack boots with a single
``docker compose up`` and zero manual configuration. Secrets (e.g. the LLM
API key) are optional - when absent the pipeline transparently falls back to a
deterministic local classifier so the system is fully functional out of the box.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/transactions"

    # --- Celery / Redis ---
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # --- Uploads ---
    # Shared volume that both the API and the worker mount, so the worker can
    # read the CSV the API persisted.
    upload_dir: str = "/data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    # --- LLM ---
    # provider: "auto" uses Gemini when GEMINI_API_KEY is set, otherwise the
    # deterministic local stub. Force one explicitly with "gemini" or "stub".
    llm_provider: str = "auto"
    gemini_api_key: str | None = None
    llm_model: str = "gemini-1.5-flash"
    llm_batch_size: int = 20
    llm_max_retries: int = 3
    llm_backoff_base: float = 1.0  # seconds; doubles each retry

    # --- Anomaly detection ---
    anomaly_median_multiplier: float = 3.0
    # Domestic-only brands that should never legitimately transact in USD.
    domestic_only_merchants: tuple[str, ...] = (
        "swiggy",
        "ola",
        "irctc",
        "zomato",
        "jio recharge",
        "hdfc atm",
    )

    @property
    def effective_llm_provider(self) -> str:
        if self.llm_provider == "auto":
            return "gemini" if self.gemini_api_key else "stub"
        return self.llm_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
