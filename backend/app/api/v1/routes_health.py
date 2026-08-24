"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.container import Container, get_container
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(container: Container = Depends(get_container)) -> HealthResponse:
    return HealthResponse(
        llm_provider=container.settings.llm_provider,
        embedding_provider=container.settings.embedding_provider,
    )
