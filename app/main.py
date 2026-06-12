"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.jobs import router as jobs_router
from app.config import settings
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on boot - no manual migration step required.
    init_db()
    yield


app = FastAPI(
    title="AI-Powered Transaction Processing Pipeline",
    description=(
        "Upload a raw transactions CSV, process it asynchronously through a job "
        "queue (clean -> detect anomalies -> LLM classify -> summarise), and poll "
        "for structured results."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.include_router(jobs_router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "llm_provider": settings.effective_llm_provider}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "transaction-processing-pipeline",
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "POST /jobs/upload",
            "GET /jobs/{job_id}/status",
            "GET /jobs/{job_id}/results",
            "GET /jobs?status=",
        ],
    }
