"""Graph inspector endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.container import Container, get_container
from app.models.schemas import SubgraphResponse

router = APIRouter(prefix="/api/v1", tags=["graph"])


@router.get("/graph/subgraph", response_model=SubgraphResponse)
async def get_subgraph(
    query_id: str | None = Query(
        default=None, description="Return the subgraph used for this chat query."
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    container: Container = Depends(get_container),
) -> SubgraphResponse:
    """Return a query-specific subgraph (by ``query_id``) or a whole-graph sample."""
    if query_id:
        subgraph = container.subgraph_cache.get(query_id)
        if subgraph is None:
            raise HTTPException(status_code=404, detail="unknown or expired query_id")
        return SubgraphResponse(query_id=query_id, subgraph=subgraph)

    subgraph = await run_in_threadpool(container.graph_store.sample_subgraph, limit)
    return SubgraphResponse(subgraph=subgraph)
