"""API request/response schemas and the typed SSE event envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.config import MAX_GRAPH_HOPS
from app.models.graph import Subgraph

# --- Ingestion ---


class DocumentInput(BaseModel):
    """One document to ingest. ``text`` is required; ``doc_id`` is optional and
    derived from content when omitted so re-ingesting the same doc is idempotent.
    """

    text: str = Field(min_length=1)
    title: str | None = None
    doc_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    documents: list[DocumentInput] = Field(min_length=1)


class JobState(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class IngestResponse(BaseModel):
    job_id: str
    state: JobState
    accepted_documents: int


class JobStatus(BaseModel):
    job_id: str
    state: JobState
    accepted_documents: int
    processed_documents: int = 0
    parents_indexed: int = 0
    children_indexed: int = 0
    entities_upserted: int = 0
    relationships_upserted: int = 0
    error: str | None = None


# --- Chat ---


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    max_hops: int | None = Field(default=None, ge=0, le=MAX_GRAPH_HOPS)


class Citation(BaseModel):
    """A retrieved parent chunk surfaced as an expandable citation card."""

    parent_id: str
    doc_id: str
    title: str | None = None
    text: str
    score: float = Field(description="Best child-match similarity that mapped to this parent.")
    matched_child_ids: list[str] = Field(default_factory=list)


class GraphTriple(BaseModel):
    """A (source)-[type]->(target) triple surfaced alongside the answer."""

    source: str
    type: str
    target: str
    description: str | None = None


# --- SSE event envelope ---
# Every streamed event is one of these, serialized as the SSE ``data:`` payload.


class SSEEventType(StrEnum):
    metadata = "metadata"
    citations = "citations"
    graph = "graph"
    token = "token"
    done = "done"
    error = "error"


class MetadataEvent(BaseModel):
    type: Literal[SSEEventType.metadata] = SSEEventType.metadata
    query_id: str
    session_id: str | None = None


class CitationsEvent(BaseModel):
    type: Literal[SSEEventType.citations] = SSEEventType.citations
    citations: list[Citation]


class GraphEvent(BaseModel):
    type: Literal[SSEEventType.graph] = SSEEventType.graph
    subgraph: Subgraph
    triples: list[GraphTriple]


class TokenEvent(BaseModel):
    type: Literal[SSEEventType.token] = SSEEventType.token
    text: str


class DoneEvent(BaseModel):
    type: Literal[SSEEventType.done] = SSEEventType.done
    query_id: str
    finish_reason: str = "stop"


class ErrorEvent(BaseModel):
    type: Literal[SSEEventType.error] = SSEEventType.error
    message: str


# --- Graph inspector ---


class SubgraphResponse(BaseModel):
    query_id: str | None = None
    subgraph: Subgraph


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm_provider: str
    embedding_provider: str


class RootResponse(BaseModel):
    name: str
    version: str
    docs: str
