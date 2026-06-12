"""Pydantic schemas for API responses."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import JobStatus


class JobCreatedResponse(BaseModel):
    """Returned immediately from POST /jobs/upload."""

    job_id: uuid.UUID
    status: JobStatus
    filename: str
    message: str = "Job accepted and queued for processing."


class JobSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_spend_inr: float
    total_spend_usd: float
    top_merchants: list | None = None
    anomaly_count: int
    narrative: str | None = None
    risk_level: str | None = None
    llm_failed: bool = False


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: JobStatus
    filename: str
    row_count_raw: int | None = None
    row_count_clean: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    # Present only when status == completed.
    summary: JobSummarySchema | None = None


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    filename: str
    status: JobStatus
    row_count_raw: int | None = None
    row_count_clean: int | None = None
    created_at: datetime


class TransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txn_id: str | None = None
    date: date_type | None = None
    merchant: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str | None = None
    category: str | None = None
    account_id: str | None = None
    notes: str | None = None
    is_anomaly: bool = False
    anomaly_reason: list | None = None
    llm_category: str | None = None
    llm_failed: bool = False


class AnomalySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txn_id: str | None = None
    merchant: str | None = None
    amount: float | None = None
    currency: str | None = None
    account_id: str | None = None
    anomaly_reason: list | None = None


class CategoryBreakdownItem(BaseModel):
    category: str
    transaction_count: int
    total_amount_inr: float
    total_amount_usd: float


class JobResultsResponse(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    row_count_raw: int | None = None
    row_count_clean: int | None = None
    transactions: list[TransactionSchema]
    anomalies: list[AnomalySchema]
    category_breakdown: list[CategoryBreakdownItem]
    summary: JobSummarySchema | None = None
