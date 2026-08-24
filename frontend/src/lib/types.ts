/**
 * TypeScript mirrors of the backend Pydantic schemas.
 * Keep in sync with backend/app/models/{schemas,graph}.py.
 */

// --- Health ---

export interface HealthResponse {
  status: "ok";
  llm_provider: string;
  embedding_provider: string;
}

// --- Ingestion ---

export interface DocumentInput {
  text: string;
  title?: string;
  doc_id?: string;
  metadata?: Record<string, string>;
}

export interface IngestRequest {
  documents: DocumentInput[];
}

export type JobState = "queued" | "running" | "completed" | "failed";

export interface IngestResponse {
  job_id: string;
  state: JobState;
  accepted_documents: number;
}

export interface JobStatus {
  job_id: string;
  state: JobState;
  accepted_documents: number;
  processed_documents: number;
  parents_indexed: number;
  children_indexed: number;
  entities_upserted: number;
  relationships_upserted: number;
  error?: string | null;
}

// --- Chat request ---

export interface ChatRequest {
  query: string;
  session_id?: string;
  top_k?: number;
  max_hops?: number;
}

// --- Graph ---

export interface GraphNode {
  key: string;
  name: string;
  type: string;
  description?: string | null;
  parent_chunk_ids: string[];
  child_chunk_ids: string[];
}

export interface GraphEdge {
  /** Source node key (matches GraphNode.key). */
  source: string;
  /** Target node key (matches GraphNode.key). */
  target: string;
  type: string;
  description?: string | null;
  parent_chunk_ids: string[];
  child_chunk_ids: string[];
}

export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** Note: triple source/target are entity *names*, not node keys. */
export interface GraphTriple {
  source: string;
  type: string;
  target: string;
  description?: string | null;
}

export interface Citation {
  parent_id: string;
  doc_id: string;
  title?: string | null;
  text: string;
  score: number;
  matched_child_ids: string[];
}

export interface SubgraphResponse {
  query_id?: string | null;
  subgraph: Subgraph;
}

// --- SSE events (discriminated union on `type`) ---

export interface MetadataEvent {
  type: "metadata";
  query_id: string;
  session_id?: string | null;
}

export interface CitationsEvent {
  type: "citations";
  citations: Citation[];
}

export interface GraphStreamEvent {
  type: "graph";
  subgraph: Subgraph;
  triples: GraphTriple[];
}

export interface TokenEvent {
  type: "token";
  text: string;
}

export interface DoneEvent {
  type: "done";
  query_id: string;
  finish_reason: string;
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export type ChatStreamEvent =
  | MetadataEvent
  | CitationsEvent
  | GraphStreamEvent
  | TokenEvent
  | DoneEvent
  | ErrorEvent;
