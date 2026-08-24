"""Unit tests for bidirectional provenance mapping."""

from __future__ import annotations

from app.core.provenance import map_provenance
from app.models.chunk import ChildChunk, ParentChunk
from app.models.graph import Entity, GraphExtraction, Relationship


def _parent_with_children() -> tuple[ParentChunk, list[ChildChunk]]:
    children = [
        ChildChunk(
            id="c0", parent_id="p0", doc_id="d", index=0, token_count=10,
            text="Acme Corp acquired Beta Inc last year.",
        ),
        ChildChunk(
            id="c1", parent_id="p0", doc_id="d", index=1, token_count=10,
            text="Gamma Labs remained independent.",
        ),
    ]
    parent = ParentChunk(
        id="p0", doc_id="d", index=0, token_count=25,
        text="Acme Corp acquired Beta Inc last year. Gamma Labs remained independent.",
        child_ids=["c0", "c1"],
    )
    return parent, children


def test_nodes_carry_bidirectional_provenance() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[
            Entity(name="Acme Corp", type="COMPANY"),
            Entity(name="Beta Inc", type="COMPANY"),
            Entity(name="Gamma Labs", type="COMPANY"),
        ],
        relationships=[],
    )
    nodes, _ = map_provenance(extraction, parent, children)
    by_name = {n.name: n for n in nodes}

    assert by_name["Acme Corp"].parent_chunk_ids == ["p0"]
    assert by_name["Acme Corp"].child_chunk_ids == ["c0"]
    assert by_name["Gamma Labs"].child_chunk_ids == ["c1"]
    # Node identity key = TYPE:lowercased-name
    assert by_name["Acme Corp"].key == "COMPANY:acme corp"


def test_edges_prefer_child_mentioning_both_endpoints() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[
            Entity(name="Acme Corp", type="COMPANY"),
            Entity(name="Beta Inc", type="COMPANY"),
        ],
        relationships=[
            Relationship(source="Acme Corp", target="Beta Inc", type="ACQUIRED"),
        ],
    )
    _, edges = map_provenance(extraction, parent, children)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "COMPANY:acme corp"
    assert edge.target == "COMPANY:beta inc"
    assert edge.type == "ACQUIRED"
    assert edge.parent_chunk_ids == ["p0"]
    # c0 mentions both endpoints; c1 mentions neither -> evidence is exactly {c0}
    assert edge.child_chunk_ids == ["c0"]


def test_mention_matching_is_normalized_across_surface_variants() -> None:
    # The child mentions the entity with extra whitespace and punctuation
    # ("Acme  Corp." with a double space + period) that a raw lowercase
    # substring check would miss; normalized matching still links them.
    child = ChildChunk(
        id="c0", parent_id="p0", doc_id="d", index=0, token_count=10,
        text="Earlier, Acme  Corp. announced its results.",
    )
    parent = ParentChunk(
        id="p0", doc_id="d", index=0, token_count=10,
        text=child.text, child_ids=["c0"],
    )
    extraction = GraphExtraction(entities=[Entity(name="Acme Corp", type="COMPANY")])

    # Guard: raw substring matching would NOT find it (proves the test is real).
    assert "acme corp" not in child.text.lower()

    nodes, _ = map_provenance(extraction, parent, [child])
    assert nodes[0].child_chunk_ids == ["c0"]


def test_edge_endpoint_missing_from_entities_gets_synthetic_key() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[Entity(name="Acme Corp", type="COMPANY")],
        relationships=[
            Relationship(source="Acme Corp", target="Beta Inc", type="ACQUIRED"),
        ],
    )
    nodes, edges = map_provenance(extraction, parent, children)
    assert edges[0].target == "ENTITY:beta inc"
    # A synthetic node is created so every edge endpoint exists in the graph.
    node_keys = {n.key for n in nodes}
    assert "ENTITY:beta inc" in node_keys
    synthetic = next(n for n in nodes if n.key == "ENTITY:beta inc")
    assert synthetic.name == "Beta Inc"
    assert "c0" in synthetic.child_chunk_ids
