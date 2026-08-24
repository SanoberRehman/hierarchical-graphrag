"""Graph extraction: parent text → provenance-carrying nodes and edges.

Extraction runs on **parent** chunks (richer context yields better, more accurate
relationships) and is then mapped down to child provenance. Provider calls are
retried with backoff to tolerate transient LLM API errors during ingestion.
"""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.provenance import map_provenance
from app.models.chunk import ChildChunk, ParentChunk
from app.models.graph import GraphEdge, GraphExtraction, GraphNode
from app.services.llm import LLMProvider


class GraphExtractor:
    """Wraps an ``LLMProvider`` to produce a persisted graph for one parent."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    )
    def _extract(self, text: str) -> GraphExtraction:
        return self._llm.extract_graph(text)

    def extract(
        self, parent: ParentChunk, children: list[ChildChunk]
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        extraction = self._extract(parent.text)
        return map_provenance(extraction, parent, children)
