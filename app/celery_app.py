"""Celery application instance shared by the API (producer) and worker (consumer)."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "transaction_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.pipeline.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Each transaction job is a single coarse-grained task; one at a time per
    # worker process keeps memory predictable for the pandas pipeline.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
