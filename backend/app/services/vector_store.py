"""Qdrant vector store for child chunks (the precision tier of retrieval).

Only **child** chunks are embedded and indexed. Each child point denormalizes its
parent's id and text into the payload, so a precise child hit can be expanded to
full parent context in a single round trip (the "small-to-big" step) without a
second store or collection.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from app.config import Settings
from app.models.chunk import ChildChunk, ParentChunk
from app.services.embeddings import EmbeddingProvider

# Fixed namespace so a child chunk's string id maps to a stable Qdrant point UUID.
_POINT_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _point_id(child_id: str) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, child_id))


class VectorHit(BaseModel):
    """One child-chunk match, carrying enough to expand to its parent."""

    child_id: str
    parent_id: str
    doc_id: str
    parent_text: str
    child_text: str
    title: str | None = None
    score: float


class VectorStore:
    """Thin, typed wrapper over a Qdrant collection of child-chunk vectors."""

    def __init__(self, settings: Settings, embeddings: EmbeddingProvider) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._collection = settings.qdrant_collection
        self._client = QdrantClient(url=settings.qdrant_url)

    def ensure_collection(self) -> None:
        """Create the collection (idempotently) sized to the embedding dim."""
        if self._client.collection_exists(self._collection):
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=models.VectorParams(
                size=self._embeddings.dim, distance=models.Distance.COSINE
            ),
        )

    def upsert_children(
        self, children: list[ChildChunk], parents_by_id: dict[str, ParentChunk]
    ) -> int:
        """Embed and upsert child chunks. Returns the number of points written."""
        if not children:
            return 0
        vectors = self._embeddings.embed_documents([c.text for c in children])
        points: list[models.PointStruct] = []
        for child, vector in zip(children, vectors, strict=True):
            parent = parents_by_id.get(child.parent_id)
            points.append(
                models.PointStruct(
                    id=_point_id(child.id),
                    vector=vector,
                    payload={
                        "child_id": child.id,
                        "parent_id": child.parent_id,
                        "doc_id": child.doc_id,
                        "child_text": child.text,
                        "parent_text": parent.text if parent else child.text,
                        "index": child.index,
                        "title": child.title,
                    },
                )
            )
        self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def search(self, query_text: str, top_k: int) -> list[VectorHit]:
        """Return the top-k child matches for a query."""
        vector = self._embeddings.embed_query(query_text)
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        hits: list[VectorHit] = []
        for point in response.points:
            payload = point.payload or {}
            hits.append(
                VectorHit(
                    child_id=payload.get("child_id", ""),
                    parent_id=payload.get("parent_id", ""),
                    doc_id=payload.get("doc_id", ""),
                    parent_text=payload.get("parent_text", ""),
                    child_text=payload.get("child_text", ""),
                    title=payload.get("title"),
                    score=float(point.score),
                )
            )
        return hits

    def delete_collection(self) -> None:
        """Drop the collection if it exists (ops/test reset)."""
        if self._client.collection_exists(self._collection):
            self._client.delete_collection(self._collection)

    def close(self) -> None:
        self._client.close()
