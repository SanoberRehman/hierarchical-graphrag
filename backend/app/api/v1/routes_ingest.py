"""Ingestion endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.container import Container, get_container
from app.models.schemas import IngestRequest, IngestResponse, JobStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def ingest(
    request: IngestRequest,
    background: BackgroundTasks,
    container: Container = Depends(get_container),
) -> IngestResponse:
    """Accept documents and run hierarchical ingestion asynchronously."""
    status = container.jobs.create(accepted_documents=len(request.documents))

    def run_job() -> None:
        try:
            container.ingestion.run(request.documents, status)
        except Exception:  # status already marked failed inside run()
            logger.exception("Ingest job %s failed", status.job_id)

    background.add_task(run_job)
    return IngestResponse(
        job_id=status.job_id, state=status.state, accepted_documents=status.accepted_documents
    )


@router.get("/ingest/jobs/{job_id}", response_model=JobStatus)
async def job_status(
    job_id: str, container: Container = Depends(get_container)
) -> JobStatus:
    status = container.jobs.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return status
