"""FastAPI application entrypoint.

Builds the dependency container at startup, prepares the stores (with retry, so
the API can wait for Neo4j/Qdrant to come up under docker-compose), and mounts
the v1 routers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from tenacity import retry, stop_after_attempt, wait_fixed

from app import __version__
from app.api.v1 import routes_chat, routes_graph, routes_health, routes_ingest
from app.config import get_settings
from app.container import build_container
from app.models.schemas import RootResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("app")


# Bounded, so a missing store delays startup by seconds, not ~90s. Under
# docker-compose the backend waits for Neo4j/Qdrant to be healthy first, so this
# normally succeeds on the first attempt anyway.
@retry(stop=stop_after_attempt(10), wait=wait_fixed(1.5), reraise=True)
def _prepare_stores_with_retry(container) -> None:
    container.prepare_stores()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    container = build_container(settings)
    app.state.container = container
    logger.info(
        "Starting up (llm=%s, embeddings=%s)",
        settings.llm_provider,
        settings.embedding_provider,
    )
    try:
        # Off the event loop: the retry loop does blocking network I/O.
        await run_in_threadpool(_prepare_stores_with_retry, container)
        logger.info("Stores ready (Qdrant collection + Neo4j schema).")
    except Exception:
        logger.warning(
            "Could not prepare stores at startup; will surface on first use.", exc_info=True
        )
    try:
        yield
    finally:
        container.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Hierarchical GraphRAG API",
        version=__version__,
        description="Hierarchical vector retrieval fused with a Neo4j knowledge graph.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_health.router)
    app.include_router(routes_ingest.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_graph.router)

    @app.get("/", tags=["meta"], response_model=RootResponse)
    async def root() -> RootResponse:
        return RootResponse(name="hierarchical-graphrag", version=__version__, docs="/docs")

    return app


app = create_app()
