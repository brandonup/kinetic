/**
 * API client for Kinetic backend communication.
 * Automatically injects Supabase auth token into all authenticated requests.
 */
import { supabase } from "./supabaseClient";

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function isLocalApiBaseUrl(baseUrl: string): boolean {
  return (
    baseUrl.startsWith("http://localhost") ||
    baseUrl.startsWith("http://127.0.0.1")
  );
}

export function resolveApiBaseUrl(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  const allowRemote = process.env.NEXT_PUBLIC_ALLOW_REMOTE_API === "true";
  const isDev = process.env.NODE_ENV !== "production";

  if (isDev && !allowRemote) {
    if (envBase && isLocalApiBaseUrl(envBase)) {
      return envBase;
    }
    return DEFAULT_API_BASE_URL;
  }

  return envBase || DEFAULT_API_BASE_URL;
}

export const API_BASE_URL = resolveApiBaseUrl();

interface FetchOptions extends RequestInit {
  requireAuth?: boolean;
}

/**
 * Fetch wrapper that automatically adds Authorization header from Supabase session.
 * All authenticated API calls go through this function.
 */
export async function apiFetch(
  endpoint: string,
  options: FetchOptions = {}
): Promise<Response> {
  const { requireAuth = true, headers, ...fetchOptions } = options;

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string>),
  };

  if (requireAuth) {
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (session?.access_token) {
      requestHeaders["Authorization"] = `Bearer ${session.access_token}`;
    } else {
      throw new Error("You are not logged in. Please sign in again.");
    }
  }

  const url = `${API_BASE_URL}${endpoint}`;
  return fetch(url, { ...fetchOptions, headers: requestHeaders });
}

/**
 * Parse error response from FastAPI backend.
 * Handles: {"detail": "..."}, {"detail": {"message": "..."}}, {"message": "..."}, plain text.
 */
export async function parseApiError(response: Response): Promise<string> {
  let text: string;
  try {
    text = await response.text();
  } catch {
    return "An unexpected error occurred";
  }

  try {
    const data = JSON.parse(text);
    if (data && typeof data === "object") {
      const d = data as Record<string, unknown>;
      if (typeof d.detail === "string") return d.detail;
      if (d.detail && typeof d.detail === "object") {
        const detail = d.detail as Record<string, unknown>;
        if (typeof detail.message === "string") return detail.message;
        if (typeof detail.error === "string") return detail.error;
      }
      if (typeof d.message === "string") return d.message;
      if (typeof d.error === "string") return d.error;
      if (Array.isArray(d.detail)) {
        const first = d.detail[0] as Record<string, unknown> | undefined;
        if (first && typeof first.msg === "string") return first.msg;
      }
    }
    return "An error occurred";
  } catch {
    return text?.trim() || "An unexpected error occurred";
  }
}

/**
 * Conversation CRUD API functions (Sprint 3)
 */
import type {
  Conversation,
  ConversationWithMessages,
  CreateConversationRequest,
  UpdateConversationRequest,
  ModelConfiguration,
} from "./types/models";

export async function createConversation(
  data: CreateConversationRequest
): Promise<Conversation> {
  const res = await apiFetch("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function listConversations(params?: {
  company_id?: string;
  project_id?: string;
  include_deleted?: boolean;
}): Promise<{ conversations: Conversation[] }> {
  const qs = new URLSearchParams();
  if (params?.company_id) qs.set("company_id", params.company_id);
  if (params?.project_id) qs.set("project_id", params.project_id);
  if (params?.include_deleted) qs.set("include_deleted", "true");
  const res = await apiFetch(`/api/v1/conversations?${qs.toString()}`);
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function getConversation(
  id: string
): Promise<ConversationWithMessages> {
  const res = await apiFetch(`/api/v1/conversations/${id}`);
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function updateConversation(
  id: string,
  data: UpdateConversationRequest
): Promise<Conversation> {
  const res = await apiFetch(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/conversations/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseApiError(res));
}

export async function listEnabledGenerationModels(): Promise<
  ModelConfiguration[]
> {
  const res = await apiFetch(
    "/api/v1/admin/models?category=generation&enabled=true"
  );
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = await res.json();
  return (data.models ?? data) as ModelConfiguration[];
}

/**
 * EventSource factory for SSE streaming via Next.js proxy route.
 * Passes auth token as query param (EventSource cannot send headers).
 */
export function createStreamEventSource(params: {
  conversationId: string;
  content: string;
  accessToken?: string;
  modelId?: string;
  agentInstanceId?: string;
}): EventSource {
  const searchParams = new URLSearchParams({
    conversation_id: params.conversationId,
    content: params.content,
  });
  if (params.modelId) {
    searchParams.set("model_id", params.modelId);
  }
  if (params.agentInstanceId) {
    searchParams.set("agent_instance_id", params.agentInstanceId);
  }
  if (params.accessToken) {
    searchParams.set("access_token", params.accessToken);
  }
  return new EventSource(`/api/stream?${searchParams.toString()}`);
}
