# Hierarchical GraphRAG

> Full-stack Retrieval-Augmented Generation that fuses **hierarchical (small-to-big) vector retrieval** with an **explicit knowledge graph**, served through a streaming FastAPI backend and an interactive Next.js chat UI.

This system ingests complex documents using parent–child hierarchical chunking, extracts a typed entity–relationship graph with an LLM, and answers questions by fusing vector similarity search with N-hop graph traversal — streaming grounded answers with expandable citations and an interactive graph inspector.

## Status

🚧 Under active development. The full architecture, setup instructions, sample queries, and design trade-offs are documented as each component lands. See the [design doc](docs/architecture.md) and open PRs for progress.

## Stack

| Layer        | Technology                                              |
| ------------ | ------------------------------------------------------- |
| Frontend     | Next.js · React · Tailwind · Cytoscape                  |
| Backend      | FastAPI · Pydantic v2 · LangGraph · SSE streaming       |
| Vector store | Qdrant                                                  |
| Graph store  | Neo4j                                                   |
| LLM          | OpenAI (embeddings + generation), pluggable provider    |
| Orchestration| docker-compose (UI + API + Neo4j + Qdrant)             |

## Repository layout

```
backend/    FastAPI service: ingestion, retrieval, graph + vector stores
frontend/   Next.js chat UI with citations and graph inspector
tests/       Backend unit + integration tests (pytest)
docs/        Architecture notes and diagrams
docker-compose.yml
```

## License

[MIT](LICENSE) © Sanober Rehman
