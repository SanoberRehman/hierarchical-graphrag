"""GraphRAG retrieval as a LangGraph pipeline (the multi-hop stage).

The retrieval flow is expressed as a compiled LangGraph ``StateGraph`` so the
multi-hop logic is explicit and inspectable:

    vector_search → seed_graph → traverse (N-hop) → build_context

* **vector_search** — child-chunk ANN, grouped into parent-level citations.
* **seed_graph** — entities grounded in the matched child chunks.
* **traverse** — N-hop neighbourhood around those seeds (the graph signal).
* **build_context** — fuse parent passages + relationship triples into the
  grounded context handed to the generator.

Generation itself is streamed by the API layer (token SSE); this stage produces
the citations, subgraph, triples, and context string.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.models.graph import Subgraph
from app.models.retrieval import RetrievalResult
from app.models.schemas import Citation, GraphTriple
from app.services.graph_store import GraphStore
from app.services.vector_store import VectorHit, VectorStore


class _State(TypedDict, total=False):
    query: str
    top_k: int
    max_hops: int
    hits: list[VectorHit]
    citations: list[Citation]
    seed_keys: list[str]
    subgraph: Subgraph
    triples: list[GraphTriple]
    context: str


def hits_to_citations(hits: list[VectorHit]) -> list[Citation]:
    """Collapse child hits to unique parent-level citations (best score wins)."""
    by_parent: dict[str, Citation] = {}
    for hit in hits:
        existing = by_parent.get(hit.parent_id)
        if existing is None:
            by_parent[hit.parent_id] = Citation(
                parent_id=hit.parent_id,
                doc_id=hit.doc_id,
                title=hit.title,
                text=hit.parent_text,
                score=hit.score,
                matched_child_ids=[hit.child_id],
            )
        else:
            existing.matched_child_ids.append(hit.child_id)
            existing.score = max(existing.score, hit.score)
    return sorted(by_parent.values(), key=lambda c: c.score, reverse=True)


def subgraph_to_triples(subgraph: Subgraph) -> list[GraphTriple]:
    """Render edges as human-readable (source)-[type]->(target) triples."""
    name_by_key = {n.key: n.name for n in subgraph.nodes}
    triples: list[GraphTriple] = []
    for edge in subgraph.edges:
        triples.append(
            GraphTriple(
                source=name_by_key.get(edge.source, edge.source),
                type=edge.type,
                target=name_by_key.get(edge.target, edge.target),
                description=edge.description,
            )
        )
    return triples


def build_context(query: str, citations: list[Citation], triples: list[GraphTriple]) -> str:
    """Assemble the grounded context block passed to the generator."""
    if not citations and not triples:
        return "No relevant context was retrieved."
    parts: list[str] = ["# Retrieved passages"]
    for i, citation in enumerate(citations, start=1):
        source = citation.title or citation.doc_id
        parts.append(f"[{i}] (source: {source})\n{citation.text}")
    if triples:
        parts.append("# Knowledge-graph relationships")
        parts.append("\n".join(f"- ({t.source}) -[{t.type}]-> ({t.target})" for t in triples))
    return "\n\n".join(parts)


def build_generation_prompt(query: str, context: str) -> str:
    return (
        f"Question: {query}\n\n"
        f"Context:\n{context}\n\n"
        "Answer the question using ONLY the context above. Cite supporting passages "
        "inline as [1], [2], ... If the context is insufficient, say so."
    )


class GraphRAGRetriever:
    """Compiles and runs the LangGraph retrieval pipeline."""

    def __init__(
        self, settings: Settings, vector_store: VectorStore, graph_store: GraphStore
    ) -> None:
        self._settings = settings
        self._vs = vector_store
        self._gs = graph_store
        self._app = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(_State)

        def vector_search(state: _State) -> _State:
            hits = self._vs.search(state["query"], state["top_k"])
            return {"hits": hits, "citations": hits_to_citations(hits)}

        def seed_graph(state: _State) -> _State:
            # Two complementary signals into the graph: entities grounded in the
            # matched child chunks (provenance), and entities named in the
            # retrieved parent context (recovers ones the child slice missed).
            child_ids = [h.child_id for h in state.get("hits", [])]
            keys = set(self._gs.seed_keys_by_child_ids(child_ids))
            parent_text = "\n".join(c.text for c in state.get("citations", []))
            keys |= set(self._gs.seed_keys_in_text(parent_text))
            return {"seed_keys": sorted(keys)}

        def traverse(state: _State) -> _State:
            subgraph = self._gs.expand_subgraph(state.get("seed_keys", []), state["max_hops"])
            return {"subgraph": subgraph, "triples": subgraph_to_triples(subgraph)}

        def make_context(state: _State) -> _State:
            return {
                "context": build_context(
                    state["query"], state.get("citations", []), state.get("triples", [])
                )
            }

        graph.add_node("vector_search", vector_search)
        graph.add_node("seed_graph", seed_graph)
        graph.add_node("traverse", traverse)
        graph.add_node("build_context", make_context)

        graph.add_edge(START, "vector_search")
        graph.add_edge("vector_search", "seed_graph")
        graph.add_edge("seed_graph", "traverse")
        graph.add_edge("traverse", "build_context")
        graph.add_edge("build_context", END)
        return graph.compile()

    def retrieve(
        self, query: str, query_id: str, top_k: int | None = None, max_hops: int | None = None
    ) -> RetrievalResult:
        final = self._app.invoke(
            {
                "query": query,
                "top_k": top_k or self._settings.vector_top_k,
                "max_hops": self._settings.graph_max_hops if max_hops is None else max_hops,
            }
        )
        return RetrievalResult(
            query_id=query_id,
            citations=final.get("citations", []),
            subgraph=final.get("subgraph", Subgraph()),
            triples=final.get("triples", []),
            seed_keys=final.get("seed_keys", []),
            context=final.get("context", ""),
        )
