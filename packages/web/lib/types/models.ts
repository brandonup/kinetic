// Conversation + Message types (Sprint 3)
export interface Conversation {
  id: string;
  user_id: string;
  company_id: string;
  project_id: string | null;
  title: string | null;
  active_agent_id: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  agent_definition_id: string | null;
  model: string | null;
  sequence: number;
  created_at: string;
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}

export interface CreateConversationRequest {
  company_id: string;
  project_id?: string | null;
  title?: string | null;
}

export interface UpdateConversationRequest {
  title?: string;
  active_agent_id?: string | null;
}

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

// Agent types (Sprint 4 — KIN-287, KIN-288)
export type AgentType = "custom" | "thought_leader";
export type AgentVisibility = "private" | "public";

export interface AgentDefinition {
  id: string;
  owner_id: string;
  name: string;
  instructions: string | null;
  type: AgentType;
  visibility: AgentVisibility;
  mcp_enabled: boolean;
  knowledge_base_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface FrameworkOverrides {
  pinned: string[];
  excluded: string[];
}

export interface AgentInstance {
  id: string;
  agent_definition_id: string;
  user_id: string;
  framework_overrides: FrameworkOverrides;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  name: string;
  instructions?: string | null;
  type?: AgentType;
  visibility?: AgentVisibility;
  mcp_enabled?: boolean;
}

export interface UpdateAgentRequest {
  name?: string;
  instructions?: string | null;
  visibility?: AgentVisibility;
  mcp_enabled?: boolean;
}

export interface UpdateInstanceRequest {
  framework_overrides?: FrameworkOverrides;
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
