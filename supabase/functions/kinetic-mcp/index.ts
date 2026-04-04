/**
 * Kinetic Remote MCP Server — Supabase Edge Function Entry Point (KIN-433).
 *
 * Direct Deno.serve handler implementing MCP Streamable HTTP transport (JSON-RPC 2.0).
 * Fully stateless — new server context per request. No subscriptions.
 *
 * Auth: Bearer mcp_<token> → user_id
 * Tools: 6 tools via tools.ts
 * Prompts: Dynamic per-user via prompts.ts
 *
 * Spec: docs/specs/remote-mcp-server-spec.md, Step 7
 */

import { createClient } from "@supabase/supabase-js";
import { authenticate } from "./auth.ts";
import { TOOL_DEFINITIONS, executeTool } from "./tools.ts";
import { listPrompts, getPrompt } from "./prompts.ts";

// ---------------------------------------------------------------------------
// Supabase client (uses auto-injected env vars)
// ---------------------------------------------------------------------------

function getSupabase() {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set");
  }
  return createClient(url, key);
}

// ---------------------------------------------------------------------------
// MCP Protocol Constants
// ---------------------------------------------------------------------------

const MCP_PROTOCOL_VERSION = "2025-03-26";
const SERVER_INFO = {
  name: "kinetic-mcp",
  version: "1.0.0",
};

// ---------------------------------------------------------------------------
// CORS headers
// ---------------------------------------------------------------------------

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
  "Access-Control-Allow-Headers":
    "Content-Type, Authorization, Mcp-Session-Id, Last-Event-ID",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

// ---------------------------------------------------------------------------
// JSON-RPC helpers
// ---------------------------------------------------------------------------

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: Record<string, unknown>;
}

/** Does the request Accept SSE? If so, wrap responses as text/event-stream. */
function wantsSSE(req: Request): boolean {
  const accept = req.headers.get("Accept") || req.headers.get("accept") || "";
  return accept.includes("text/event-stream");
}

/** Wrap a JSON-RPC payload as a single SSE event and close the stream. */
function sseResponse(
  payload: Record<string, unknown>,
  extraHeaders?: Record<string, string>
): Response {
  const data = JSON.stringify(payload);
  const body = `event: message\ndata: ${data}\n\n`;
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

function jsonRpcResponse(
  id: string | number | null,
  result: unknown,
  req: Request,
  extraHeaders?: Record<string, string>
): Response {
  const payload = { jsonrpc: "2.0" as const, id, result };
  if (wantsSSE(req)) {
    return sseResponse(payload, extraHeaders);
  }
  return new Response(JSON.stringify(payload), {
    headers: {
      "Content-Type": "application/json",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

function jsonRpcError(
  id: string | number | null,
  code: number,
  message: string,
  req?: Request,
  extraHeaders?: Record<string, string>
): Response {
  const payload = {
    jsonrpc: "2.0" as const,
    id,
    error: { code, message },
  };
  if (req && wantsSSE(req)) {
    return sseResponse(payload, extraHeaders);
  }
  return new Response(JSON.stringify(payload), {
    headers: {
      "Content-Type": "application/json",
      ...CORS_HEADERS,
      ...extraHeaders,
    },
  });
}

// ---------------------------------------------------------------------------
// MCP method handlers
// ---------------------------------------------------------------------------

async function handleMcpMethod(
  method: string,
  params: Record<string, unknown>,
  userId: string,
  supabase: ReturnType<typeof createClient>
): Promise<unknown> {
  switch (method) {
    case "initialize":
      return {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {
          tools: {},
          prompts: {},
        },
        serverInfo: SERVER_INFO,
      };

    case "notifications/initialized":
      return null;

    case "tools/list":
      return { tools: TOOL_DEFINITIONS };

    case "tools/call": {
      const toolName = params.name as string;
      const toolArgs = (params.arguments || {}) as Record<string, unknown>;

      if (!toolName) {
        throw { code: -32602, message: "Missing tool name" };
      }

      try {
        const result = await executeTool(supabase, userId, toolName, toolArgs);
        return {
          content: [{ type: "text", text: result }],
        };
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        return {
          content: [{ type: "text", text: message }],
          isError: true,
        };
      }
    }

    case "prompts/list": {
      console.log("[prompts/list] userId:", userId);
      const prompts = await listPrompts(supabase, userId);
      console.log("[prompts/list] result:", JSON.stringify(prompts));
      return { prompts };
    }

    case "prompts/get": {
      const promptName = params.name as string;
      if (!promptName) {
        throw { code: -32602, message: "Missing prompt name" };
      }

      const prompt = await getPrompt(supabase, userId, promptName);
      if (!prompt) {
        throw { code: -32602, message: `Prompt '${promptName}' not found` };
      }

      return prompt;
    }

    case "ping":
      return {};

    default:
      throw { code: -32601, message: `Method not found: ${method}` };
  }
}

// ---------------------------------------------------------------------------
// Request handler (no Hono — direct Deno.serve)
// ---------------------------------------------------------------------------

Deno.serve(async (req: Request) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  // DELETE — session termination (stateless: always accept)
  if (req.method === "DELETE") {
    return new Response(null, { status: 202, headers: CORS_HEADERS });
  }

  // GET — spec uses this for server→client SSE stream.
  // Stateless server: no server-initiated messages. Return 405.
  if (req.method === "GET") {
    return new Response(null, {
      status: 405,
      headers: { Allow: "POST, OPTIONS, DELETE", ...CORS_HEADERS },
    });
  }

  // Only POST from here
  if (req.method !== "POST") {
    return new Response("Method not allowed", {
      status: 405,
      headers: CORS_HEADERS,
    });
  }

  const supabase = getSupabase();

  // Authenticate
  let userId: string;
  try {
    const authResult = await authenticate(req, supabase);
    userId = authResult.userId;
  } catch (err) {
    const message = err instanceof Error ? err.message : "Authentication failed";
    return jsonRpcError(null, -32000, message, req);
  }

  // Parse JSON-RPC request
  let rpcRequest: JsonRpcRequest;
  try {
    rpcRequest = await req.json();
  } catch {
    return jsonRpcError(null, -32700, "Parse error: invalid JSON", req);
  }

  if (rpcRequest.jsonrpc !== "2.0" || !rpcRequest.method) {
    return jsonRpcError(
      rpcRequest.id ?? null,
      -32600,
      "Invalid request: missing jsonrpc version or method",
      req
    );
  }

  const id = rpcRequest.id ?? null;
  const params = rpcRequest.params || {};

  // Notifications (no id) get 202 Accepted per spec
  if (id === null || id === undefined) {
    try {
      await handleMcpMethod(rpcRequest.method, params, userId, supabase);
    } catch {
      // Notifications don't get error responses
    }
    return new Response(null, { status: 202, headers: CORS_HEADERS });
  }

  // For initialize: generate a session ID (stateless — throwaway, but spec-
  // compliant clients expect to receive and echo it back).
  const extraHeaders: Record<string, string> = {};
  if (rpcRequest.method === "initialize") {
    extraHeaders["Mcp-Session-Id"] = crypto.randomUUID();
  }

  // Dispatch to MCP handler
  try {
    const result = await handleMcpMethod(
      rpcRequest.method,
      params,
      userId,
      supabase
    );
    return jsonRpcResponse(id, result, req, extraHeaders);
  } catch (err) {
    if (
      typeof err === "object" &&
      err !== null &&
      "code" in err &&
      "message" in err
    ) {
      const rpcErr = err as { code: number; message: string };
      return jsonRpcError(id, rpcErr.code, rpcErr.message, req, extraHeaders);
    }
    const message = err instanceof Error ? err.message : "Internal error";
    return jsonRpcError(id, -32603, message, req, extraHeaders);
  }
});
