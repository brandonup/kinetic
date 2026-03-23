// Model library types (admin LLM Models tab — wired in Sprint 2)
export type ModelCategory = "generation" | "embedding" | "reranking";

export interface ModelConfiguration {
  id: string;
  name: string;
  provider: "anthropic" | "openai" | "google" | "groq";
  category: ModelCategory;
  enabled: boolean;
  context_window?: number | null;
  created_at: string;
  updated_at: string;
}

// Streaming event types (used by SSE proxy)
export type StreamEventType = "start" | "delta" | "done" | "error";

export interface StreamEventData {
  text?: string;
  message_id?: string;
  status?: string;
  error_code?: string;
  error_message?: string;
}

export interface StreamEvent {
  event: StreamEventType;
  event_id: number;
  generation_id: string;
  conversation_id: string;
  data: StreamEventData;
}
