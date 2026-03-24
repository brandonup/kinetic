// User profile types (KIN-261)
export type ApiKeyProvider = "anthropic" | "openai" | "google" | "groq";

export interface UserProfile {
  id: string;
  name: string;
  bio: string | null;
  default_model_id: string | null;
}

export interface ApiKeyEntry {
  provider: ApiKeyProvider;
  key_hint: string;
  validated_at: string | null;
}

// Company types (KIN-262)
export interface Company {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

// Project types (KIN-263)
export interface Project {
  id: string;
  company_id: string;
  user_id: string;
  name: string;
  instructions: string | null;
  created_at: string;
  updated_at: string;
}

// Model library types (admin LLM Models tab — KIN-265)
export type ModelCategory = "generation" | "embedding" | "reranking";
export type ModelProvider = "anthropic" | "openai" | "google" | "groq";

export interface ModelConfiguration {
  id: string;
  provider: ModelProvider;
  model_id: string;
  display_name: string;
  category: ModelCategory;
  enabled: boolean;
  context_window: number | null;
  created_at: string;
  updated_at: string;
}

// Admin user types (KIN-264)
export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user";
  disabled_at: string | null;
  created_at: string;
}

// Active Memory types (KIN-309)
export interface ActiveMemoryEntry {
  id: string;
  content: string;
  source_conversation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActiveMemoryUsage {
  current_tokens: number;
  cap_tokens: number;
}

export interface ActiveMemoryListResponse {
  entries: ActiveMemoryEntry[];
  token_usage: ActiveMemoryUsage;
}

export interface MemoryProposal {
  id: string;
  proposed_content: string;
  trigger_type: "conversation_end" | "periodic";
  conversation_id: string;
  created_at: string;
}

export interface MemoryProposalsResponse {
  proposals: MemoryProposal[];
}

export interface ProposalDecision {
  proposal_id: string;
  action: "accept" | "reject";
}

export interface ProposalReviewResponse {
  results: Array<{
    proposal_id: string;
    action: "accepted" | "rejected" | "skipped_cap_exceeded";
  }>;
  token_usage: ActiveMemoryUsage;
}

// Agent types (KIN-287/319)
export type AgentType = "custom" | "thought_leader";
export type AgentVisibility = "private" | "public";

export interface FrameworkOverrides {
  pinned: string[];
  excluded: string[];
}

export interface AgentDefinition {
  id: string;
  owner_id: string;
  name: string;
  instructions: string;
  type: AgentType;
  visibility: AgentVisibility;
  knowledge_base_id: string | null;
  mcp_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentInstance {
  id: string;
  agent_definition_id: string;
  user_id: string;
  framework_overrides: FrameworkOverrides;
  created_at: string;
  updated_at: string;
}

export interface Framework {
  id: string;
  agent_definition_id: string;
  framework_id: string;
  name: string;
  description: string | null;
  category: string | null;
  when_to_apply: string[];
  confidence: "high" | "medium";
  origin: "extracted" | "manual";
  principles: string[];
  steps: string[];
  example_application: string | null;
  related_frameworks: string[];
  source_posts: Record<string, unknown>[] | null;
  created_at: string;
  updated_at: string;
}

export interface FrameworkListResponse {
  frameworks: Framework[];
}

export interface CreateAgentRequest {
  name: string;
  instructions: string;
  type: AgentType;
  visibility: AgentVisibility;
  mcp_enabled: boolean;
}

export interface UpdateAgentInstanceRequest {
  framework_overrides: FrameworkOverrides;
}

// Framework mutation types (KIN-320)
export interface CreateFrameworkRequest {
  name: string;
  when_to_apply: string[];
  principles: string[];
  confidence: "high" | "medium";
  framework_id?: string;
  category?: string;
  description?: string;
  example_application?: string;
  steps?: string[];
  related_frameworks?: string[];
}

export interface UpdateFrameworkRequest {
  name?: string;
  when_to_apply?: string[];
  category?: string;
  example_application?: string;
  confidence?: "high" | "medium";
  principles?: string[];
}

export interface UploadFrameworksResponse {
  added: number;
  updated: number;
  retained: number;
  failed: Array<{ framework_id: string; error: string }>;
}

// MCP token types (KIN-325)
export interface McpToken {
  id: string;
  name: string;
  last_used_at: string | null;
  created_at: string;
}

export interface McpTokenListResponse {
  tokens: McpToken[];
}

export interface CreateMcpTokenResponse {
  id: string;
  name: string;
  token: string; // raw token — shown once only, never stored in frontend state after modal dismissed
  created_at: string;
}

// Document / KB types (KIN-346)
export type DocumentStatus =
  | "pending"
  | "extracting"
  | "chunking"
  | "embedding"
  | "completed"
  | "failed";

export interface DocumentStatusResponse {
  document_id: string;
  status: DocumentStatus;
  error_stage: string | null;
  error_message: string | null;
  retry_count: number;
  tags: string[];
}

export interface DocumentRetryResponse {
  document_id: string;
  status: string;
  message: string;
}

// Chat message types (KIN-337)
export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessageRecord {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  agent_definition_id: string | null;
  /** Resolved via JOIN agent_definitions ON messages.agent_definition_id = agent_definitions.id.
   *  Not a column in the messages table — API must populate this. */
  agent_name: string | null;
  model: string | null;
  token_count: number | null;
  sequence: number;
  created_at: string;
  /** Resolved from retrieval_debug_logs.injected_chunks joined via message_id.
   *  Not a column in the messages table — API must hydrate from debug logs. */
  citations: ChatCitation[];
}

/** Maps to retrieval_debug_logs.injected_chunks (§20).
 *  chunk_id + score + text_preview come from injected_chunks jsonb.
 *  document_title is resolved via JOIN knowledge_base_chunks → knowledge_base_documents.
 *  If the join is unavailable, document_title may be null. */
export interface ChatCitation {
  chunk_id: string;
  document_title: string | null;
  text_preview: string;
  score: number;
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
