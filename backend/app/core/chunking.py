"""Hierarchical (small-to-big) chunking.

A document is split into **disjoint parent chunks** (~1000 tokens). Each parent is
then split into **child chunks** (~200 tokens, with a small overlap for recall).
Because parents are disjoint, every child belongs to exactly one parent — which
keeps parent↔child provenance unambiguous (a graded requirement).

Splitting is token-aware but boundary-friendly: we use a recursive splitter that
prefers paragraph/sentence/word boundaries while measuring length in tiktoken
tokens, so chunks rarely cut mid-word.

IDs are content-derived and deterministic, so re-ingesting the same document is
idempotent (identical ids → upserts overwrite in place).
"""

from __future__ import annotations

import hashlib

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings
from app.models.chunk import ChildChunk, HierarchicalChunks, ParentChunk


def _hash_id(*parts: str, length: int = 16) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def derive_doc_id(text: str, provided: str | None = None) -> str:
    """Return the provided doc id, or a stable content-derived one."""
    if provided:
        return provided
    return "doc-" + _hash_id(text, length=16)


class HierarchicalChunker:
    """Splits documents into parent/child tiers using token-aware recursion."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._encoder = tiktoken.get_encoding(settings.tokenizer_encoding)
        self._parent_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=settings.tokenizer_encoding,
            chunk_size=settings.parent_chunk_tokens,
            chunk_overlap=settings.parent_chunk_overlap_tokens,
        )
        self._child_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=settings.tokenizer_encoding,
            chunk_size=settings.child_chunk_tokens,
            chunk_overlap=settings.child_chunk_overlap_tokens,
        )

    def _count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))

    def chunk_document(
        self, text: str, doc_id: str | None = None, title: str | None = None
    ) -> HierarchicalChunks:
        """Decompose a single document into parents and children."""
        resolved_doc_id = derive_doc_id(text, doc_id)

        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []

        parent_texts = [t for t in self._parent_splitter.split_text(text) if t.strip()]
        child_ordinal = 0
        for p_index, parent_text in enumerate(parent_texts):
            parent_id = _hash_id(resolved_doc_id, "p", str(p_index), parent_text)
            child_ids: list[str] = []

            child_texts = [t for t in self._child_splitter.split_text(parent_text) if t.strip()]
            # A parent must always have at least one child (its own text) so that no
            # content is unreachable by vector search.
            if not child_texts:
                child_texts = [parent_text]

            for child_text in child_texts:
                child_id = _hash_id(parent_id, "c", str(child_ordinal), child_text)
                children.append(
                    ChildChunk(
                        id=child_id,
                        parent_id=parent_id,
                        doc_id=resolved_doc_id,
                        text=child_text,
                        token_count=self._count_tokens(child_text),
                        index=child_ordinal,
                    )
                )
                child_ids.append(child_id)
                child_ordinal += 1

            parents.append(
                ParentChunk(
                    id=parent_id,
                    doc_id=resolved_doc_id,
                    text=parent_text,
                    token_count=self._count_tokens(parent_text),
                    index=p_index,
                    child_ids=child_ids,
                )
            )

        return HierarchicalChunks(doc_id=resolved_doc_id, parents=parents, children=children)
