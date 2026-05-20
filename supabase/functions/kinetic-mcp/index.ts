/**
 * Kinetic Remote MCP Server — Supabase Edge Function (KIN-464).
 *
 * Ported from hand-rolled JSON-RPC to official MCP SDK.
 * Reference: projects/brain/supabase/functions/open-brain-mcp/index.ts
 *
 * Auth: Bearer mcp_<token> → user_id
 * Tools: 6 tools via tools.ts
 * Prompts: Dynamic per-user via prompts.ts
 */

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPTransport } from "@hono/mcp";
import { Hono } from "hono";
import { z } from "zod";
import { createClient } from "@supabase/supabase-js";
import { authenticate } from "./auth.ts";
import { executeTool } from "./tools.ts";
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
// CORS headers
// ---------------------------------------------------------------------------

const corsHeaders: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
  "Access-Control-Allow-Headers":
    "authorization, content-type, accept, mcp-session-id",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

// ---------------------------------------------------------------------------
// MCP Server factory — per-request with user context
// ---------------------------------------------------------------------------

async function createMcpServer(
  supabase: ReturnType<typeof createClient>,
  userId: string,
  sessionId: string | null
): Promise<McpServer> {
  const server = new McpServer({
    name: "kinetic-mcp",
    version: "1.0.0",
  });

  // Helper: delegate to executeTool and return MCP-formatted result
  const callTool = async (
    toolName: string,
    args: Record<string, unknown>
  ) => {
    try {
      const result = await executeTool(supabase, userId, toolName, args, sessionId);
      const isError = result.startsWith("Error:");
      return {
        content: [{ type: "text" as const, text: result }],
        ...(isError && { isError: true }),
      };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return { content: [{ type: "text" as const, text: message }], isError: true };
    }
  };

  // --- Register 6 tools ---

  server.registerTool(
    "list_kinetic_agents",
    {
      description:
        "List all available Kinetic agents — your own agents and public agents. Returns names, slugs, descriptions, and ownership.",
      inputSchema: {},
    },
    async () => callTool("list_kinetic_agents", {})
  );

  server.registerTool(
    "get_agent_persona",
    {
      description:
        "Fetch an agent's persona — their name and system prompt instructions that define reasoning style and voice.",
      inputSchema: {
        agent: z.string().describe("Agent slug (e.g., 'nate')"),
      },
    },
    async ({ agent }) => callTool("get_agent_persona", { agent })
  );

  server.registerTool(
    "get_active_memory",
    {
      description:
        "Fetch active memory entries for an agent — context from prior conversations, ordered most-recent-first.",
      inputSchema: {
        agent: z.string().describe("Agent slug (e.g., 'nate')"),
      },
    },
    async ({ agent }) => callTool("get_active_memory", { agent })
  );

  server.registerTool(
    "select_framework",
    {
      description:
        "Select the best-matching reasoning framework for a user question. Uses embedding similarity against framework trigger phrases.",
      inputSchema: {
        agent: z.string().describe("Agent slug (e.g., 'nate')"),
        query: z.string().describe("The user's question to match against frameworks"),
      },
    },
    async ({ agent, query }) => callTool("select_framework", { agent, query })
  );

  server.registerTool(
    "search_knowledge_base",
    {
      description:
        "Search an agent's knowledge base for content relevant to a question. Uses embedding similarity to find the most relevant documents.",
      inputSchema: {
        agent: z.string().describe("Agent slug (e.g., 'nate')"),
        query: z.string().describe("The user's question to search the knowledge base for"),
      },
    },
    async ({ agent, query }) => callTool("search_knowledge_base", { agent, query })
  );

  server.registerTool(
    "assemble_context",
    {
      description:
        "Assemble all context layers for an agent in a single call: persona, active memory, framework selection, and knowledge base search. More efficient than calling the 4 individual tools separately — use this as the default for full context assembly.",
      inputSchema: {
        agent: z.string().describe("Agent slug (e.g., 'nate')"),
        query: z.string().describe(
          "The user's question — used for framework matching and KB search"
        ),
      },
    },
    async ({ agent, query }) => callTool("assemble_context", { agent, query })
  );

  // --- Register dynamic prompts (user's agents become discoverable slash commands) ---

  const prompts = await listPrompts(supabase, userId);
  for (const prompt of prompts) {
    server.registerPrompt(
      prompt.name,
      { description: prompt.description },
      async () => {
        const result = await getPrompt(supabase, userId, prompt.name);
        if (!result) {
          throw new Error(`Prompt '${prompt.name}' not found`);
        }
        return result;
      }
    );
  }

  return server;
}

// ---------------------------------------------------------------------------
// Hono App
// ---------------------------------------------------------------------------

const app = new Hono();

// CORS preflight
app.options("*", (c) => c.text("ok", 200, corsHeaders));

// All MCP requests
app.all("*", async (c) => {
  const supabase = getSupabase();

  // Authenticate
  let userId: string;
  try {
    const authResult = await authenticate(c.req.raw, supabase);
    userId = authResult.userId;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Authentication failed";
    return c.json(
      { jsonrpc: "2.0", id: null, error: { code: -32000, message } },
      401,
      corsHeaders
    );
  }

  // Fix: Claude Desktop / Cowork connectors don't always send the Accept header
  // that StreamableHTTPTransport requires. Patch the request if missing.
  // Reference: open-brain-mcp/index.ts lines 389-401
  if (!c.req.header("accept")?.includes("text/event-stream")) {
    const headers = new Headers(c.req.raw.headers);
    headers.set("Accept", "application/json, text/event-stream");
    const patched = new Request(c.req.raw.url, {
      method: c.req.raw.method,
      headers,
      body: c.req.raw.body,
      // @ts-ignore -- duplex required for streaming body in Deno
      duplex: "half",
    });
    Object.defineProperty(c.req, "raw", { value: patched, writable: true });
  }

  // Extract session ID for logging (may not exist until after initialize)
  const sessionId = c.req.header("mcp-session-id") || null;

  // Create per-request MCP server with user context and dynamic prompts
  const server = await createMcpServer(supabase, userId, sessionId);
  const transport = new StreamableHTTPTransport();
  await server.connect(transport);
  return transport.handleRequest(c);
});

Deno.serve(app.fetch);
