"""Ingestion pipeline: documents → hierarchical chunks → vector + graph stores.

For each document:

1. Hierarchical chunking (parents + children).
2. Embed and upsert **child** chunks into Qdrant (with parent context in payload).
3. Extract a knowledge graph from each **parent**, map provenance, and upsert
   entities + typed relationships into Neo4j.

The pipeline mutates a :class:`JobStatus` in place so the API can report progress
for the asynchronous ingest endpoint.
"""

from __future__ import annotations

from collections import defaultdict

from app.config import Settings
from app.core.chunking import HierarchicalChunker
from app.models.schemas import DocumentInput, JobState, JobStatus
from app.services.embeddings import EmbeddingProvider
from app.services.extraction import GraphExtractor
from app.services.graph_store import GraphStore
from app.services.llm import LLMProvider
from app.services.vector_store import VectorStore


class IngestionPipeline:
    """Orchestrates chunking, embedding, extraction, and persistence."""

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        llm: LLMProvider,
        vector_store: VectorStore,
        graph_store: GraphStore,
    ) -> None:
        self._settings = settings
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._chunker = HierarchicalChunker(settings)
        self._extractor = GraphExtractor(llm)

    def prepare(self) -> None:
        """Ensure the target stores exist (collection + graph constraints)."""
        self._vector_store.ensure_collection()
        self._graph_store.init_schema()

    def ingest_document(self, doc: DocumentInput, status: JobStatus) -> None:
        chunks = self._chunker.chunk_document(doc.text, doc_id=doc.doc_id, title=doc.title)

        status.children_indexed += self._vector_store.upsert_children(
            chunks.children, chunks.parent_by_id
        )
        status.parents_indexed += len(chunks.parents)

        children_by_parent: dict[str, list] = defaultdict(list)
        for child in chunks.children:
            children_by_parent[child.parent_id].append(child)

        all_nodes = []
        all_edges = []
        for parent in chunks.parents:
            nodes, edges = self._extractor.extract(parent, children_by_parent[parent.id])
            all_nodes.extend(nodes)
            all_edges.extend(edges)

        status.entities_upserted += self._graph_store.upsert_nodes(all_nodes)
        status.relationships_upserted += self._graph_store.upsert_edges(all_edges)
        status.processed_documents += 1

    def run(self, documents: list[DocumentInput], status: JobStatus) -> JobStatus:
        """Run the full pipeline over a batch of documents, updating ``status``."""
        status.state = JobState.running
        try:
            self.prepare()
            for doc in documents:
                self.ingest_document(doc, status)
            status.state = JobState.completed
        except Exception as exc:  # surface failure to the job status
            status.state = JobState.failed
            status.error = f"{type(exc).__name__}: {exc}"
            raise
        return status
