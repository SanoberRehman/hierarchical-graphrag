"""Provenance mapping: link extracted graph elements back to their chunks.

Extraction runs on **parent** text (more context → better relationships). This
module maps each extracted entity/relationship down to the specific **child**
chunks that mention it, and up to the owning **parent** — giving every node and
edge the bidirectional provenance the brief requires
(``parent_chunk_ids`` + ``child_chunk_ids``).
"""

from __future__ import annotations

from app.models.chunk import ChildChunk, ParentChunk
from app.models.graph import Entity, GraphEdge, GraphExtraction, GraphNode


def _entity_key(name: str, entities_by_name: dict[str, Entity]) -> str:
    match = entities_by_name.get(name.lower())
    if match is not None:
        return match.key
    # Endpoint not in the entity list: synthesize a stable generic key.
    return f"ENTITY:{name.lower()}"


def _children_mentioning(term: str, children: list[ChildChunk]) -> list[str]:
    needle = term.lower()
    return [c.id for c in children if needle in c.text.lower()]


def map_provenance(
    extraction: GraphExtraction,
    parent: ParentChunk,
    children: list[ChildChunk],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Return provenance-carrying nodes and edges for one parent's extraction."""
    entities_by_name = {e.name.lower(): e for e in extraction.entities}

    nodes: list[GraphNode] = []
    nodes_by_key: dict[str, GraphNode] = {}
    for entity in extraction.entities:
        child_ids = _children_mentioning(entity.name, children)
        node = GraphNode(
            key=entity.key,
            name=entity.name,
            type=entity.type,
            description=entity.description,
            parent_chunk_ids=[parent.id],
            child_chunk_ids=child_ids,
        )
        nodes.append(node)
        nodes_by_key[node.key] = node

    def _ensure_endpoint_node(name: str) -> str:
        """Return the node key for an edge endpoint, creating a synthetic node
        if the extractor named it in a relationship but not in the entity list.
        Guarantees every edge has both endpoints present in the graph."""
        key = _entity_key(name, entities_by_name)
        if key not in nodes_by_key:
            synthetic = GraphNode(
                key=key,
                name=name,
                type=key.split(":", 1)[0],
                parent_chunk_ids=[parent.id],
                child_chunk_ids=_children_mentioning(name, children),
            )
            nodes.append(synthetic)
            nodes_by_key[key] = synthetic
        return key

    edges: list[GraphEdge] = []
    for rel in extraction.relationships:
        src_children = set(_children_mentioning(rel.source, children))
        tgt_children = set(_children_mentioning(rel.target, children))
        both = src_children & tgt_children
        # Prefer chunks mentioning both endpoints (stronger evidence); else either.
        evidence = both or (src_children | tgt_children)
        edges.append(
            GraphEdge(
                source=_ensure_endpoint_node(rel.source),
                target=_ensure_endpoint_node(rel.target),
                type=rel.type,
                description=rel.description,
                parent_chunk_ids=[parent.id],
                child_chunk_ids=sorted(evidence),
            )
        )

    return nodes, edges
