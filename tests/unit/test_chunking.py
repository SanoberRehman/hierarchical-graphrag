"""Unit tests for hierarchical (small-to-big) chunking."""

from __future__ import annotations

import pytest

from app.core.chunking import HierarchicalChunker, derive_doc_id


@pytest.fixture
def long_text() -> str:
    # Distinct sentences so children are not all identical, long enough for
    # several parents under the small test token budgets.
    sentences = [
        f"Sentence number {i} describes how entity Alpha{i} relates to entity Beta{i} "
        f"in the context of project Gamma{i} during quarter {i}."
        for i in range(60)
    ]
    return " ".join(sentences)


def test_chunk_document_produces_parents_and_children(fake_settings, long_text) -> None:
    chunker = HierarchicalChunker(fake_settings)
    result = chunker.chunk_document(long_text, doc_id="doc-1")

    assert len(result.parents) >= 2, "long text should yield multiple parents"
    assert len(result.children) >= len(result.parents)
    assert all(c.text.strip() for c in result.children)


def test_every_child_maps_to_exactly_one_parent(fake_settings, long_text) -> None:
    chunker = HierarchicalChunker(fake_settings)
    result = chunker.chunk_document(long_text, doc_id="doc-1")

    parent_ids = {p.id for p in result.parents}
    # Every child points at a real parent.
    for child in result.children:
        assert child.parent_id in parent_ids

    # The union of parents' child_ids exactly equals the set of children, with no
    # child shared between two parents (disjoint parents => unambiguous provenance).
    listed: list[str] = [cid for p in result.parents for cid in p.child_ids]
    assert sorted(listed) == sorted(c.id for c in result.children)
    assert len(listed) == len(set(listed)), "no child may belong to two parents"


def test_child_chunks_respect_token_budget(fake_settings, long_text) -> None:
    chunker = HierarchicalChunker(fake_settings)
    result = chunker.chunk_document(long_text, doc_id="doc-1")
    # Children should be smaller than parents on average (small-to-big).
    avg_child = sum(c.token_count for c in result.children) / len(result.children)
    avg_parent = sum(p.token_count for p in result.parents) / len(result.parents)
    assert avg_child < avg_parent
    # No child grossly exceeds the configured child budget.
    assert max(c.token_count for c in result.children) <= fake_settings.child_chunk_tokens * 2


def test_chunking_is_deterministic(fake_settings, long_text) -> None:
    chunker = HierarchicalChunker(fake_settings)
    a = chunker.chunk_document(long_text, doc_id="doc-1")
    b = chunker.chunk_document(long_text, doc_id="doc-1")
    assert [p.id for p in a.parents] == [p.id for p in b.parents]
    assert [c.id for c in a.children] == [c.id for c in b.children]


def test_derive_doc_id() -> None:
    assert derive_doc_id("hello", provided="explicit") == "explicit"
    auto = derive_doc_id("hello world")
    assert auto.startswith("doc-")
    assert derive_doc_id("hello world") == auto  # deterministic
    assert derive_doc_id("different") != auto


def test_short_document_yields_single_parent(fake_settings) -> None:
    chunker = HierarchicalChunker(fake_settings)
    result = chunker.chunk_document("A tiny document about Acme Corp.", doc_id="d")
    assert len(result.parents) == 1
    assert len(result.children) >= 1
    assert result.parents[0].child_ids == [c.id for c in result.children]
