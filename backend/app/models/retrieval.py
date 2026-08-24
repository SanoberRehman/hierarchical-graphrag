"""Result of the retrieval stage, consumed by the chat endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.graph import Subgraph
from app.models.schemas import Citation, GraphTriple


class RetrievalResult(BaseModel):
    """Everything the generator needs, plus what the UI renders as evidence."""

    query_id: str
    citations: list[Citation] = Field(default_factory=list)
    subgraph: Subgraph = Field(default_factory=Subgraph)
    triples: list[GraphTriple] = Field(default_factory=list)
    seed_keys: list[str] = Field(default_factory=list)
    context: str = ""
