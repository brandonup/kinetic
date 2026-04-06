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
    ...(fetchOptions.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
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
      if (d.error && typeof d.error === "object") {
        const err = d.error as Record<string, unknown>;
        if (typeof err.message === "string") return err.message;
      }
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
 * EventSource factory for SSE streaming via Next.js proxy route.
 * Passes auth token as query param (EventSource cannot send headers).
 */
export function createStreamEventSource(params: {
  conversationId: string;
  content: string;
  accessToken?: string;
  agentInstanceId?: string;
}): EventSource {
  const searchParams = new URLSearchParams({
    conversation_id: params.conversationId,
    content: params.content,
  });
  if (params.agentInstanceId) {
    searchParams.set("agent_instance_id", params.agentInstanceId);
  }
  if (params.accessToken) {
    searchParams.set("access_token", params.accessToken);
  }
  return new EventSource(`/api/stream?${searchParams.toString()}`);
}
