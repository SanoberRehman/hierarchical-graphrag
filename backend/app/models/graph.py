"""Knowledge-graph extraction models.

These are the schemas the LLM is asked to populate via structured output, plus
the provenance-carrying shapes we persist to Neo4j. Provenance is *bidirectional*
per the brief: every node and edge records both the child chunk ids (what the
extractor actually read) and the parent chunk ids (the context they belong to).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


def normalize_entity_name(name: str) -> str:
    """Canonicalize an entity name so the same real-world thing merges.

    Collapses whitespace and trims; casing is preserved for display but a
    separate ``key`` (lowercased) is used for identity in the graph store.
    """
    return re.sub(r"\s+", " ", name).strip()


class Entity(BaseModel):
    """A named entity (graph node) produced by the extractor."""

    name: str = Field(description="Canonical surface form of the entity, e.g. 'Acme Corp'.")
    type: str = Field(description="Entity type in SCREAMING_SNAKE_CASE, e.g. COMPANY, PERSON.")
    description: str | None = Field(
        default=None, description="One-line description grounded in the source text."
    )

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        cleaned = normalize_entity_name(v)
        if not cleaned:
            raise ValueError("entity name must be non-empty")
        return cleaned

    @field_validator("type")
    @classmethod
    def _clean_type(cls, v: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", v.upper().strip()) or "ENTITY"

    @property
    def key(self) -> str:
        """Identity key used for merging nodes (type + lowercased name)."""
        return f"{self.type}:{self.name.lower()}"


class Relationship(BaseModel):
    """A typed, directed edge between two entities."""

    source: str = Field(description="Name of the source entity.")
    target: str = Field(description="Name of the target entity.")
    type: str = Field(description="Relationship type, e.g. ACQUIRED, FOUNDED, WORKS_AT.")
    description: str | None = Field(
        default=None, description="One-line evidence for the relationship from the text."
    )

    @field_validator("source", "target")
    @classmethod
    def _clean_endpoints(cls, v: str) -> str:
        cleaned = normalize_entity_name(v)
        if not cleaned:
            raise ValueError("relationship endpoints must be non-empty")
        return cleaned

    @field_validator("type")
    @classmethod
    def _clean_type(cls, v: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", v.upper().strip()) or "RELATED_TO"


class GraphExtraction(BaseModel):
    """Structured-output container the LLM fills for one chunk of text."""

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


# --- Persisted / API-facing graph shapes (with provenance) ---


class GraphNode(BaseModel):
    """A graph node as stored/returned, with provenance back to chunks."""

    key: str
    name: str
    type: str
    description: str | None = None
    parent_chunk_ids: list[str] = Field(default_factory=list)
    child_chunk_ids: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    """A graph edge as stored/returned, with provenance back to chunks."""

    source: str = Field(description="Source node key.")
    target: str = Field(description="Target node key.")
    type: str
    description: str | None = None
    parent_chunk_ids: list[str] = Field(default_factory=list)
    child_chunk_ids: list[str] = Field(default_factory=list)


class Subgraph(BaseModel):
    """A node-edge bundle for visualization / traversal results."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
