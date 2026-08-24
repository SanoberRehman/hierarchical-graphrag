"""Hierarchical chunk models.

The system uses a *small-to-big* (parent-child) strategy:

* **Child chunks** (~200 tokens) are embedded and indexed for high-precision
  vector search.
* **Parent chunks** (~1000 tokens) hold the broader context and are the units
  actually handed to the LLM at generation time.

Each child stores its ``parent_id``; each parent stores its ``child_ids``. This
bidirectional link is what lets a precise vector hit expand into rich context.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChildChunk(BaseModel):
    """A small, embedded chunk optimized for retrieval precision."""

    id: str = Field(description="Stable, content-derived child chunk id.")
    parent_id: str = Field(description="Id of the parent chunk this belongs to.")
    doc_id: str = Field(description="Id of the source document.")
    text: str
    token_count: int
    index: int = Field(description="Ordinal position of this child within the document.")
    title: str | None = None


class ParentChunk(BaseModel):
    """A larger context block that is expanded to at generation time."""

    id: str = Field(description="Stable, content-derived parent chunk id.")
    doc_id: str
    text: str
    token_count: int
    index: int = Field(description="Ordinal position of this parent within the document.")
    child_ids: list[str] = Field(default_factory=list)
    title: str | None = None


class HierarchicalChunks(BaseModel):
    """The full parent-child decomposition of a single document."""

    doc_id: str
    parents: list[ParentChunk]
    children: list[ChildChunk]

    @property
    def parent_by_id(self) -> dict[str, ParentChunk]:
        return {p.id: p for p in self.parents}
