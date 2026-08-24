"""The graph-seeding recall fix, tested deterministically with fake stores.

Regression guard for a subtle gap: when an entity's stored ``child_chunk_ids``
don't intersect the vector-matched child chunk (e.g. the LLM's canonical name
didn't line up with that particular slice), seeding purely from child provenance
returns nothing and graph traversal is silently skipped for it. The retriever now
*also* seeds from the retrieved parent text, which recovers those entities.

Uses fake vector/graph stores so it runs in ``pytest -m "not integration"`` with
no Neo4j/Qdrant.
"""

from __future__ import annotations

from app.config import Settings
from app.models.graph import GraphNode, Subgraph
from app.services.retrieval import GraphRAGRetriever
from app.services.vector_store import VectorHit

_MISSED_KEY = "COMPANY:acme corporation"


class _FakeVectorStore:
    def search(self, query_text: str, top_k: int) -> list[VectorHit]:
        # One child hit whose parent context names "Acme Corporation".
        return [
            VectorHit(
                child_id="c-miss",
                parent_id="p1",
                doc_id="d1",
                parent_text="Acme Corporation acquired Beta Industries.",
                child_text="... a landmark deal ...",
                title="Deals",
                score=0.88,
            )
        ]


class _FakeGraphStore:
    def __init__(self) -> None:
        self.by_child_calls: list[list[str]] = []
        self.in_text_calls: list[str] = []

    def seed_keys_by_child_ids(self, child_ids: list[str]) -> list[str]:
        self.by_child_calls.append(child_ids)
        return []  # the entity's provenance did NOT include child "c-miss"

    def seed_keys_in_text(self, text: str) -> list[str]:
        self.in_text_calls.append(text)
        return [_MISSED_KEY] if "acme corporation" in text.lower() else []

    def expand_subgraph(self, seed_keys: list[str], hops: int) -> Subgraph:
        return Subgraph(
            nodes=[
                GraphNode(key=k, name=k.split(":", 1)[1].title(), type=k.split(":", 1)[0])
                for k in seed_keys
            ]
        )


def _retriever(gs: _FakeGraphStore) -> GraphRAGRetriever:
    return GraphRAGRetriever(Settings(), _FakeVectorStore(), gs)  # type: ignore[arg-type]


def test_parent_text_seeding_recovers_entity_missed_by_child_provenance() -> None:
    gs = _FakeGraphStore()
    result = _retriever(gs).retrieve("What did Acme acquire?", "q-1")

    # Child-provenance seeding ran and returned nothing; the parent-text signal
    # recovered the entity, so traversal is seeded (not silently skipped).
    assert gs.by_child_calls == [["c-miss"]]
    assert any("Acme Corporation" in t for t in gs.in_text_calls)
    assert result.seed_keys == [_MISSED_KEY]
    assert [n.key for n in result.subgraph.nodes] == [_MISSED_KEY]


def test_seeds_are_unioned_and_deduped() -> None:
    class _BothSignals(_FakeGraphStore):
        def seed_keys_by_child_ids(self, child_ids: list[str]) -> list[str]:
            return [_MISSED_KEY, "COMPANY:beta industries"]

        def seed_keys_in_text(self, text: str) -> list[str]:
            return [_MISSED_KEY]  # overlaps the child-provenance seed

    gs = _BothSignals()
    result = _retriever(gs).retrieve("q", "q-2")
    # Deduped union of both signals (seed_keys is returned sorted).
    assert result.seed_keys == ["COMPANY:acme corporation", "COMPANY:beta industries"]
