"""Dependency container: builds and holds the app's singletons.

Constructed once at startup (lifespan) and stored on ``app.state``; routes read
it via the ``get_container`` dependency. Centralizing construction keeps provider
selection (openai | fake) and store wiring in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings, get_settings
from app.services.cache import SubgraphCache
from app.services.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.graph_store import GraphStore
from app.services.ingestion import IngestionPipeline
from app.services.jobs import JobStore
from app.services.llm import LLMProvider, build_llm_provider
from app.services.retrieval import GraphRAGRetriever
from app.services.vector_store import VectorStore


@dataclass
class Container:
    settings: Settings
    embeddings: EmbeddingProvider
    llm: LLMProvider
    vector_store: VectorStore
    graph_store: GraphStore
    ingestion: IngestionPipeline
    retriever: GraphRAGRetriever
    jobs: JobStore
    subgraph_cache: SubgraphCache

    def prepare_stores(self) -> None:
        """Ensure the vector collection and graph constraints exist."""
        self.vector_store.ensure_collection()
        self.graph_store.init_schema()

    def close(self) -> None:
        self.vector_store.close()
        self.graph_store.close()


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    embeddings = build_embedding_provider(settings)
    llm = build_llm_provider(settings)
    vector_store = VectorStore(settings, embeddings)
    graph_store = GraphStore(settings)
    ingestion = IngestionPipeline(settings, embeddings, llm, vector_store, graph_store)
    retriever = GraphRAGRetriever(settings, vector_store, graph_store)
    return Container(
        settings=settings,
        embeddings=embeddings,
        llm=llm,
        vector_store=vector_store,
        graph_store=graph_store,
        ingestion=ingestion,
        retriever=retriever,
        jobs=JobStore(),
        subgraph_cache=SubgraphCache(),
    )


def get_container(request: Request) -> Container:
    return request.app.state.container
