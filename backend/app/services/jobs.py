"""In-memory async-ingest job registry.

Small and process-local by design — sufficient for a single-instance demo. A
production deployment would back this with Redis/DB; the interface is narrow
enough to swap.
"""

from __future__ import annotations

import uuid

from app.models.schemas import JobState, JobStatus


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}

    def create(self, accepted_documents: int) -> JobStatus:
        job_id = "job-" + uuid.uuid4().hex[:12]
        status = JobStatus(
            job_id=job_id, state=JobState.queued, accepted_documents=accepted_documents
        )
        self._jobs[job_id] = status
        return status

    def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)
