/**
 * MCP Tool Implementations — KIN-433, KIN-454.
 *
 * 6 tools: list_kinetic_agents, get_agent_persona, get_active_memory,
 * select_framework, search_knowledge_base, assemble_context.
 *
 * All agent-accepting tools use resolveAgent() for access control.
 *
 * Spec: docs/specs/remote-mcp-server-spec.md, Step 6
 */

import { SupabaseClient } from "@supabase/supabase-js";
import { embedQuery } from "./embedding.ts";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FRAMEWORK_TRIGGER_TOP_K = 20;
const FRAMEWORK_MIN_SIMILARITY = 0.62;
const HIGH_CONFIDENCE_THRESHOLD = 0.75;
const MULTI_TRIGGER_BOOST = 0.05;

const MODERATE_CONFIDENCE_CAVEAT =
  "This framework was matched with moderate confidence. Apply it only if it\n" +
  "directly addresses the user's question. If it seems tangential, ignore it\n" +
  "and reason without a framework.";
const KB_MATCH_COUNT = 20;
const KB_SIMILARITY_THRESHOLD = 0.3;
const KB_TOP_K = 8;

// Context enrichment (KIN-447) — prefix cap ~50 tokens
const MAX_CONTEXT_PREFIX_CHARS = 200;

// ---------------------------------------------------------------------------
// KIN-485 (Component D, MCP/Cowork path): date-aware output, env-var gated.
//
// Deno Edge Functions can't read the Python `settings` object, so the MCP
// surface is gated by its own Supabase Edge Function env var rather than the
// Python `RECENCY_ENABLED`. Off-state must produce byte-identical output to
// pre-feature `main` — both the per-chunk header line and the assembleContext
// payload preamble are unchanged when this is "0" / unset.
// ---------------------------------------------------------------------------

function isRecencyDateAwareEnabled(): boolean {
  const raw = Deno.env.get("RECENCY_DATE_AWARE_ENABLED");
  // Accept "1" / "true" (case-insensitive). Anything else (including unset)
  // is OFF. Mirrors the strict-true gate the Python settings field implements.
  if (!raw) return false;
  const v = raw.trim().toLowerCase();
  return v === "1" || v === "true";
}

const RECENCY_KB_PREAMBLE =
  "Sources are labeled with publication dates. This domain evolves rapidly — " +
  "when sources conflict, prefer the more recent one. If you rely on information " +
  "that may be outdated given its date, briefly note that.";

/**
 * Build the date suffix to append to a KB result header line.
 *
 * Mirrors the Python context_assembler._format_source_header logic — uses the
 * raw `document_date` when present (PostgREST returns the `match_chunks` date
 * columns as plain "YYYY-MM-DD" strings, see
 * `migrations/20260523000001_match_chunks_add_effective_date.sql`), and falls
 * back to `document_created_at` with the `Added` label when document_date is
 * null/missing/implausible. Returns an empty string when both are null OR when
 * the gating env var is off — keeping off-state output byte-identical.
 *
 * Supabase TS types lag the new RPC columns, so callers access these fields
 * via the `Record<string, unknown>` shape and we read them through `unknown`
 * here. No `as any` cast is needed.
 */
function formatChunkDateSuffix(chunk: Record<string, unknown>): string {
  if (!isRecencyDateAwareEnabled()) return "";

  const rawDate = chunk.document_date;
  const createdAt = chunk.document_created_at;

  // Python parity: pre-2015 / future-dated values are not validated here —
  // the API path handles plausibility in `_derive_effective_date`. On the MCP
  // surface we trust what the RPC returns; the eval suite will catch any
  // observable drift via end-to-end cases.
  if (typeof rawDate === "string" && rawDate.length > 0) {
    return `, Published: ${rawDate}`;
  }
  if (typeof createdAt === "string" && createdAt.length > 0) {
    return `, Added: ${createdAt}`;
  }
  return "";
}

interface QueryContextFields {
  agentName?: string | null;     // L5 — strongest scoping signal for KB
  companyName?: string | null;   // L2
  companyDescription?: string | null; // L2
  userBio?: string | null;       // L1
  projectName?: string | null;   // L3
}

/**
 * Prepend available context to the query before embedding.
 * Template must match Python build_enriched_query() exactly.
 * Agent goes first — strongest scoping signal for KB retrieval (KIN-450).
 */
function buildEnrichedQuery(query: string, ctx?: QueryContextFields | null): string {
  if (!ctx) return query;

  const parts: string[] = [];

  // Agent first — strongest scope signal for KB (KIN-450)
  if (ctx.agentName) {
    parts.push(`[Agent: ${ctx.agentName}]`);
  }

  if (ctx.companyName) {
    let line = `[Company: ${ctx.companyName}`;
    if (ctx.companyDescription) {
      line += ` — ${ctx.companyDescription.slice(0, 80).trim()}`;
    }
    line += "]";
    parts.push(line);
  }

  if (ctx.userBio) {
    parts.push(`[User: ${ctx.userBio.slice(0, 80).trim()}]`);
  }

  if (ctx.projectName) {
    parts.push(`[Project: ${ctx.projectName}]`);
  }

  if (parts.length === 0) return query;

  let prefix = parts.join("\n");
  if (prefix.length > MAX_CONTEXT_PREFIX_CHARS) {
    prefix = prefix.slice(0, MAX_CONTEXT_PREFIX_CHARS);
  }

  return prefix + "\n" + query;
}

// ---------------------------------------------------------------------------
// resolve_agent — shared access control helper
// ---------------------------------------------------------------------------

interface ResolvedAgent {
  definitionId: string;
  instanceId: string;
  name: string;
  instructions: string;
}

/**
 * Resolve an agent by slug with ownership/visibility enforcement.
 *
 * Resolution chain:
 * 1. Look up agent_definitions by globally unique slug
 * 2. Check access: owner OR public visibility
 * 3. Find or auto-create agent_instance for this user
 *
 * Returns ResolvedAgent or throws descriptive error string.
 */
export async function resolveAgent(
  supabase: SupabaseClient,
  userId: string,
  slug: string
): Promise<ResolvedAgent> {
  // Step 1: Look up agent definition by slug (globally unique)
  const { data: def, error: defErr } = await supabase
    .from("agent_definitions")
    .select("id, owner_id, name, instructions, visibility")
    .eq("slug", slug)
    .maybeSingle();

  if (defErr || !def) {
    throw new Error(`Error: Agent '${slug}' not found for this user`);
  }

  // Step 2: Access control — owned or public
  if (def.owner_id !== userId && def.visibility !== "public") {
    // Never say "forbidden" — prevents slug enumeration
    throw new Error(`Error: Agent '${slug}' not found for this user`);
  }

  const definitionId: string = def.id;

  // Step 3: Find existing instance for this user
  const { data: inst, error: instErr } = await supabase
    .from("agent_instances")
    .select("id")
    .eq("agent_definition_id", definitionId)
    .eq("user_id", userId)
    .maybeSingle();

  let instanceId: string;

  if (instErr || !inst) {
    // Auto-create instance (matches web app first-invocation behavior)
    const { data: newInst, error: createErr } = await supabase
      .from("agent_instances")
      .insert({ user_id: userId, agent_definition_id: definitionId })
      .select("id")
      .single();

    if (createErr || !newInst) {
      throw new Error(`Error: Failed to initialize agent '${slug}'`);
    }
    instanceId = newInst.id;
  } else {
    instanceId = inst.id;
  }

  return {
    definitionId,
    instanceId,
    name: def.name || slug,
    instructions: def.instructions || "",
  };
}

// ---------------------------------------------------------------------------
// Tool: list_kinetic_agents
// ---------------------------------------------------------------------------

/**
 * List user's own agents plus all public agents.
 * Returns formatted text with name, slug, description, ownership.
 */
export async function listKineticAgents(
  supabase: SupabaseClient,
  userId: string
): Promise<string> {
  // Query user's own agent instances joined with definitions
  const { data: ownInstances } = await supabase
    .from("agent_instances")
    .select("agent_definition_id")
    .eq("user_id", userId);

  const ownDefIds = (ownInstances || []).map(
    (i: { agent_definition_id: string }) => i.agent_definition_id
  );

  let ownAgents: Array<Record<string, unknown>> = [];
  if (ownDefIds.length > 0) {
    const { data } = await supabase
      .from("agent_definitions")
      .select("name, slug, instructions")
      .in("id", ownDefIds);
    ownAgents = data || [];
  }

  // Query public agents (not already in own list)
  const { data: publicAgents } = await supabase
    .from("agent_definitions")
    .select("name, slug, instructions")
    .eq("visibility", "public");

  const ownSlugs = new Set(ownAgents.map((a) => a.slug));
  const publicOnly = (publicAgents || []).filter(
    (a: Record<string, unknown>) => !ownSlugs.has(a.slug as string)
  );

  if (ownAgents.length === 0 && publicOnly.length === 0) {
    return "No agents available";
  }

  const lines: string[] = ["# Your Kinetic Agents\n"];

  for (const a of ownAgents) {
    const desc = a.instructions ? a.instructions.split("\n")[0].slice(0, 200) : "No description";
    lines.push(`- **${a.name}** (\`${a.slug}\`) — ${desc} [own]`);
  }

  if (publicOnly.length > 0) {
    lines.push("\n# Public Agents\n");
    for (const a of publicOnly) {
      const desc = a.instructions ? a.instructions.split("\n")[0].slice(0, 200) : "No description";
      lines.push(`- **${a.name}** (\`${a.slug}\`) — ${desc} [public]`);
    }
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Tool: get_agent_persona
// ---------------------------------------------------------------------------

/**
 * Fetch an agent's persona (name + system prompt instructions).
 */
export async function getAgentPersona(
  supabase: SupabaseClient,
  userId: string,
  slug: string
): Promise<string> {
  const agent = await resolveAgent(supabase, userId, slug);
  if (!agent.instructions) {
    return "";
  }
  return `# ${agent.name}\n\n${agent.instructions}`;
}

// ---------------------------------------------------------------------------
// Tool: get_active_memory
// ---------------------------------------------------------------------------

/**
 * Fetch active memory entries for an agent instance.
 * Uses instance_id (NOT definition_id) — critical distinction.
 */
export async function getActiveMemory(
  supabase: SupabaseClient,
  userId: string,
  slug: string
): Promise<string> {
  const agent = await resolveAgent(supabase, userId, slug);

  const { data: entries, error } = await supabase
    .from("active_memory_entries")
    .select("id, content, created_at, updated_at")
    .eq("agent_instance_id", agent.instanceId)
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error || !entries || entries.length === 0) {
    return "No active memories";
  }

  const lines = ["# Active Memory\n"];
  for (const entry of entries) {
    const content = entry.content || "";
    const created = (entry.created_at || "").slice(0, 10);
    lines.push(`- **${created}:** ${content}`);
  }

  return lines.join("\n");
}

/**
 * Fetch lightweight L1/L2/L3 context for query enrichment (KIN-447).
 * Returns null fields if data is missing — callers skip gracefully.
 * No latency impact when user has no profile/company (queries return empty).
 */
async function fetchQueryContext(
  supabase: SupabaseClient,
  userId: string
): Promise<QueryContextFields> {
  const ctx: QueryContextFields = {};

  try {
    // User bio (L1)
    const { data: user } = await supabase
      .from("users")
      .select("bio")
      .eq("id", userId)
      .maybeSingle();
    if (user?.bio) ctx.userBio = user.bio;

    // Company (L2) — find user's active company
    const { data: userRow } = await supabase
      .from("users")
      .select("active_company_id")
      .eq("id", userId)
      .maybeSingle();
    if (userRow?.active_company_id) {
      const { data: company } = await supabase
        .from("companies")
        .select("name, description")
        .eq("id", userRow.active_company_id)
        .maybeSingle();
      if (company) {
        ctx.companyName = company.name;
        ctx.companyDescription = company.description;
      }
    }
  } catch {
    // Fail-open: enrichment is best-effort
  }

  return ctx;
}

// ---------------------------------------------------------------------------
// Tool: select_framework
// ---------------------------------------------------------------------------

/**
 * Select the best-matching framework for a query using embedding similarity.
 * Multi-trigger boost + confidence gate at 0.62, caveat for 0.62–0.75 band.
 */
export async function selectFramework(
  supabase: SupabaseClient,
  userId: string,
  slug: string,
  query: string
): Promise<string> {
  const agent = await resolveAgent(supabase, userId, slug);

  // Check if agent has any frameworks
  const { data: frameworks } = await supabase
    .from("frameworks")
    .select("id")
    .eq("agent_definition_id", agent.definitionId)
    .limit(1);

  if (!frameworks || frameworks.length === 0) {
    return "No framework library configured for this agent. Proceeding without framework guidance.";
  }

  // Fetch user/company/project context for query enrichment (KIN-447, KIN-450)
  const queryCtx = await fetchQueryContext(supabase, userId);
  queryCtx.agentName = agent.name;  // L5: agent scope signal

  // Embed the enriched query (uses platform Gemini key)
  const enrichedQuery = buildEnrichedQuery(query, queryCtx);
  let queryEmbedding: number[];
  try {
    queryEmbedding = await embedQuery(enrichedQuery);
  } catch (err) {
    if (err instanceof Error) return err.message;
    return "Error: Embedding failed";
  }

  // Vector search on framework triggers
  const { data: triggers, error: rpcErr } = await supabase.rpc(
    "match_framework_triggers",
    {
      query_embedding: queryEmbedding,
      p_agent_id: agent.definitionId,
      match_count: FRAMEWORK_TRIGGER_TOP_K,
    }
  );

  if (rpcErr || !triggers || !Array.isArray(triggers) || triggers.length === 0) {
    return "No matching framework found";
  }

  // Group by framework, apply multi-trigger boost
  const frameworkScores: Map<string, { maxSim: number; count: number }> = new Map();
  for (const t of triggers) {
    const fid = t.framework_db_id as string;
    const sim = Number(t.similarity);
    const entry = frameworkScores.get(fid) || { maxSim: 0, count: 0 };
    entry.maxSim = Math.max(entry.maxSim, sim);
    entry.count += 1;
    frameworkScores.set(fid, entry);
  }

  // Rank with boost
  const ranked: Array<[string, number]> = [];
  for (const [fid, scores] of frameworkScores) {
    const boosted = scores.maxSim + (scores.count - 1) * MULTI_TRIGGER_BOOST;
    ranked.push([fid, boosted]);
  }
  ranked.sort((a, b) => b[1] - a[1]);

  // Confidence gate
  const [topId, topScore] = ranked[0];
  if (topScore < FRAMEWORK_MIN_SIMILARITY) {
    return "No matching framework found";
  }

  // Fetch full framework
  const { data: fw, error: fwErr } = await supabase
    .from("frameworks")
    .select("id, name, description, when_to_apply, principles, steps, example_application")
    .eq("id", topId)
    .maybeSingle();

  if (fwErr || !fw) {
    return "No matching framework found";
  }

  const text = assembleFrameworkText(fw);
  if (topScore < HIGH_CONFIDENCE_THRESHOLD) {
    return `[Framework: ${fw.name} (moderate confidence match)]\n${MODERATE_CONFIDENCE_CAVEAT}\n\n${text}`;
  }
  return text;
}

function assembleFrameworkText(fw: Record<string, unknown>): string {
  const parts: string[] = [];

  const name = fw.name as string;
  if (name) parts.push(`# Framework: ${name}\n`);

  const description = fw.description as string;
  if (description) parts.push(description);

  const whenToApply = fw.when_to_apply;
  if (whenToApply) {
    const items = Array.isArray(whenToApply) ? whenToApply : [whenToApply];
    parts.push("\n## When to Apply\n" + items.map((w: string) => `- ${w}`).join("\n"));
  }

  const principles = fw.principles;
  if (principles) {
    const items = Array.isArray(principles) ? principles : [principles];
    parts.push("\n## Principles\n" + items.map((p: string) => `- ${p}`).join("\n"));
  }

  const steps = fw.steps;
  if (steps) {
    const items = Array.isArray(steps) ? steps : [steps];
    parts.push(
      "\n## Steps\n" +
        items.map((s: string, i: number) => `${i + 1}. ${s}`).join("\n")
    );
  }

  const example = fw.example_application as string;
  if (example) parts.push(`\n## Example Application\n${example}`);

  return parts.length > 0 ? parts.join("\n") : "No matching framework found";
}

// ---------------------------------------------------------------------------
// Tool: search_knowledge_base
// ---------------------------------------------------------------------------

/**
 * Search an agent's knowledge base using embedding similarity.
 * Threshold 0.3, top 8 results from 20 candidates.
 */
export async function searchKnowledgeBase(
  supabase: SupabaseClient,
  userId: string,
  slug: string,
  query: string
): Promise<string> {
  const agent = await resolveAgent(supabase, userId, slug);

  // Check if agent has a knowledge base
  const { data: kbs } = await supabase
    .from("knowledge_bases")
    .select("id")
    .eq("agent_definition_id", agent.definitionId)
    .limit(1);

  if (!kbs || kbs.length === 0) {
    return "No knowledge base configured for this agent. Proceeding without KB context.";
  }

  // Fetch user/company context + add agent name for query enrichment (KIN-450)
  const queryCtx = await fetchQueryContext(supabase, userId);
  queryCtx.agentName = agent.name;

  // Embed the enriched query
  const enrichedQuery = buildEnrichedQuery(query, queryCtx);
  let queryEmbedding: number[];
  try {
    queryEmbedding = await embedQuery(enrichedQuery);
  } catch (err) {
    if (err instanceof Error) return err.message;
    return "Error: Embedding failed";
  }

  // Vector search via match_chunks RPC
  const { data: chunks, error: rpcErr } = await supabase.rpc("match_chunks", {
    query_embedding: queryEmbedding,
    scope_column: "agent_definition_id",
    scope_value: agent.definitionId,
    match_count: KB_MATCH_COUNT,
  });

  if (rpcErr || !chunks || !Array.isArray(chunks) || chunks.length === 0) {
    return "No relevant knowledge base entries found";
  }

  // Filter by similarity threshold
  const filtered = chunks.filter(
    (c: Record<string, unknown>) => Number(c.similarity) >= KB_SIMILARITY_THRESHOLD
  );

  if (filtered.length === 0) {
    return "No relevant knowledge base entries found";
  }

  // Take top K
  const topChunks = filtered.slice(0, KB_TOP_K);

  // KIN-485 (Component D): when RECENCY_DATE_AWARE_ENABLED, prepend a recency /
  // contradiction-preference preamble so the Cowork-side LLM applies the same
  // tie-break rule the Kinetic-side generation prompt does. Off-state omits it
  // so output is byte-identical to pre-feature.
  const recencyOn = isRecencyDateAwareEnabled();
  const lines = ["# Knowledge Base Results\n"];
  if (recencyOn) {
    lines.push(RECENCY_KB_PREAMBLE);
    lines.push("");
  }
  for (let i = 0; i < topChunks.length; i++) {
    const chunk = topChunks[i];
    const title = (chunk.document_title as string) || "Unknown";
    const section = chunk.section_path as string;
    const similarity = Number(chunk.similarity);
    const text = (chunk.text as string) || "";

    let header = `## [${i + 1}] ${title}`;
    if (section) header += ` > ${section}`;
    header += ` (relevance: ${similarity.toFixed(2)})`;
    header += formatChunkDateSuffix(chunk);

    lines.push(header);
    lines.push(text);
    lines.push("");
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Tool: assemble_context (KIN-454)
// ---------------------------------------------------------------------------

/**
 * Single-call context assembly: persona + memory + framework + KB search.
 *
 * Optimization over 4 separate tool calls:
 * - 1 authenticate() instead of 4 (handled by caller)
 * - 1 resolveAgent() instead of 4
 * - 1 embedQuery() instead of 2 (shared by framework + KB)
 * - Promise.allSettled fan-out for parallel data fetching
 *
 * Each layer degrades gracefully — a failure in one never cascades to others.
 */
export async function assembleContext(
  supabase: SupabaseClient,
  userId: string,
  slug: string,
  query: string,
  sessionId: string | null = null
): Promise<string> {
  const startTime = Date.now();
  let topLevelError: string | null = null;

  // Single agent resolution (eliminates 3 redundant lookups)
  let agent: ResolvedAgent;
  try {
    agent = await resolveAgent(supabase, userId, slug);
  } catch (err) {
    topLevelError = err instanceof Error ? err.message : String(err);
    // Log the failed invocation
    const logRow = {
      user_id: userId,
      agent_definition_id: null,
      agent_instance_id: null,
      query,
      agent_slug: slug,
      context_payload: null,
      layer_persona: null,
      layer_memory: null,
      layer_framework: null,
      layer_kb: null,
      layer_status: { persona: "error", memory: "error", framework: "error", kb: "error" },
      latency_ms: Date.now() - startTime,
      embedding_latency_ms: null,
      token_count_estimate: null,
      error: topLevelError,
      mcp_session_id: sessionId,
    };
    fireAndForgetLog(supabase, logRow);
    throw err;
  }

  // --- Persona: already available from resolveAgent ---
  const persona = agent.instructions
    ? `# ${agent.name}\n\n${agent.instructions}`
    : "";

  // --- Fetch context for query enrichment (KIN-447, KIN-450) ---
  const queryCtx = await fetchQueryContext(supabase, userId);
  queryCtx.agentName = agent.name;  // L5: strongest scope signal for KB

  // --- Single embedding call with enriched query (platform Gemini key) ---
  const enrichedCtxQuery = buildEnrichedQuery(query, queryCtx);
  let queryEmbedding: number[] | null = null;
  let embeddingError: string | null = null;
  const embeddingStart = Date.now();
  try {
    queryEmbedding = await embedQuery(enrichedCtxQuery);
  } catch (err) {
    embeddingError = err instanceof Error ? err.message : "Error: Embedding failed";
  }
  const embeddingLatency = queryEmbedding ? Date.now() - embeddingStart : null;

  // --- Fan out: memory + framework + KB in parallel via Promise.allSettled ---
  const [memoryResult, frameworkResult, kbResult] = await Promise.allSettled([
    // Memory: no embedding needed, independent query
    fetchActiveMemory(supabase, userId, agent.instanceId),
    // Framework: requires embedding
    queryEmbedding
      ? fetchFramework(supabase, agent.definitionId, queryEmbedding)
      : Promise.resolve(embeddingError || "No embedding available — skipping framework selection."),
    // KB: requires embedding
    queryEmbedding
      ? fetchKnowledgeBase(supabase, agent.definitionId, queryEmbedding)
      : Promise.resolve(embeddingError || "No embedding available — skipping knowledge base search."),
  ]);

  // --- Assemble structured response ---
  const sections: string[] = [];

  // Persona
  if (persona) {
    sections.push("## Persona\n\n" + persona);
  }

  // Active Memory
  const memoryText = memoryResult.status === "fulfilled"
    ? memoryResult.value
    : "No active memories";
  sections.push("## Active Memory\n\n" + memoryText);

  // Framework
  const frameworkText = frameworkResult.status === "fulfilled"
    ? frameworkResult.value
    : "No matching framework found";
  sections.push("## Framework\n\n" + frameworkText);

  // Knowledge Base
  const kbText = kbResult.status === "fulfilled"
    ? kbResult.value
    : "No relevant knowledge base entries found";
  sections.push("## Knowledge Base\n\n" + kbText);

  const result = sections.join("\n\n---\n\n");

  // --- Build layer_status and fire-and-forget log ---
  const layerStatus = {
    persona: persona ? "ok" : "empty",
    memory: getLayerStatus(memoryResult, !queryEmbedding, "No active memories"),
    framework: getLayerStatus(frameworkResult, !queryEmbedding, "No matching framework found"),
    kb: getLayerStatus(kbResult, !queryEmbedding, "No relevant knowledge base entries found"),
  };

  const logRow = {
    user_id: userId,
    agent_definition_id: agent.definitionId,
    agent_instance_id: agent.instanceId,
    query,
    agent_slug: slug,
    context_payload: result,
    layer_persona: persona || null,
    layer_memory: memoryText !== "No active memories" ? memoryText : null,
    layer_framework: frameworkText !== "No matching framework found" ? frameworkText : null,
    layer_kb: kbText !== "No relevant knowledge base entries found" ? kbText : null,
    layer_status: layerStatus,
    latency_ms: Date.now() - startTime,
    embedding_latency_ms: embeddingLatency,
    token_count_estimate: null,
    error: topLevelError,
    mcp_session_id: sessionId,
  };
  fireAndForgetLog(supabase, logRow);

  return result;
}

/**
 * Determine layer status from a Promise.allSettled result.
 */
function getLayerStatus(
  result: PromiseSettledResult<string>,
  embeddingFailed: boolean,
  emptyMarker: string
): string {
  if (result.status === "rejected") return "error";
  if (embeddingFailed && (result.value.includes("skipping") || result.value.includes("No embedding"))) return "skipped";
  if (result.value === emptyMarker || result.value.includes("No ") || result.value.includes("Proceeding without")) return "empty";
  return "ok";
}

/**
 * Fire-and-forget log write to messages_mcp.
 * Uses EdgeRuntime.waitUntil to keep the promise alive after response.
 */
function fireAndForgetLog(
  supabase: SupabaseClient,
  logRow: Record<string, unknown>
): void {
  const logPromise = supabase
    .from("messages_mcp")
    .insert(logRow)
    .then(() => {})
    .catch((err: Error) => console.warn("MCP log write failed:", err));

  if (typeof (globalThis as Record<string, unknown>).EdgeRuntime !== "undefined") {
    try {
      (globalThis as Record<string, unknown> & { EdgeRuntime: { waitUntil: (p: Promise<void>) => void } })
        .EdgeRuntime.waitUntil(logPromise);
    } catch {
      // Fallback: dangling promise
    }
  }
}

// ---------------------------------------------------------------------------
// assemble_context internal helpers (no resolveAgent, no embedQuery)
// ---------------------------------------------------------------------------

/**
 * Fetch active memory entries by instance ID.
 * Extracted from getActiveMemory — skips resolveAgent (already done).
 */
async function fetchActiveMemory(
  supabase: SupabaseClient,
  userId: string,
  instanceId: string
): Promise<string> {
  const { data: entries, error } = await supabase
    .from("active_memory_entries")
    .select("id, content, created_at, updated_at")
    .eq("agent_instance_id", instanceId)
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error || !entries || entries.length === 0) {
    return "No active memories";
  }

  const lines: string[] = [];
  for (const entry of entries) {
    const content = entry.content || "";
    const created = (entry.created_at || "").slice(0, 10);
    lines.push(`- **${created}:** ${content}`);
  }
  return lines.join("\n");
}

/**
 * Select best-matching framework using a pre-computed embedding.
 * Extracted from selectFramework — skips resolveAgent + embedQuery (already done).
 */
async function fetchFramework(
  supabase: SupabaseClient,
  definitionId: string,
  queryEmbedding: number[]
): Promise<string> {
  // Check if agent has any frameworks
  const { data: frameworks } = await supabase
    .from("frameworks")
    .select("id")
    .eq("agent_definition_id", definitionId)
    .limit(1);

  if (!frameworks || frameworks.length === 0) {
    return "No framework library configured for this agent. Proceeding without framework guidance.";
  }

  // Vector search on framework triggers
  const { data: triggers, error: rpcErr } = await supabase.rpc(
    "match_framework_triggers",
    {
      query_embedding: queryEmbedding,
      p_agent_id: definitionId,
      match_count: FRAMEWORK_TRIGGER_TOP_K,
    }
  );

  if (rpcErr || !triggers || !Array.isArray(triggers) || triggers.length === 0) {
    return "No matching framework found";
  }

  // Group by framework, apply multi-trigger boost
  const frameworkScores: Map<string, { maxSim: number; count: number }> = new Map();
  for (const t of triggers) {
    const fid = t.framework_db_id as string;
    const sim = Number(t.similarity);
    const entry = frameworkScores.get(fid) || { maxSim: 0, count: 0 };
    entry.maxSim = Math.max(entry.maxSim, sim);
    entry.count += 1;
    frameworkScores.set(fid, entry);
  }

  // Rank with boost
  const ranked: Array<[string, number]> = [];
  for (const [fid, scores] of frameworkScores) {
    const boosted = scores.maxSim + (scores.count - 1) * MULTI_TRIGGER_BOOST;
    ranked.push([fid, boosted]);
  }
  ranked.sort((a, b) => b[1] - a[1]);

  // Confidence gate
  const [topId, topScore] = ranked[0];
  if (topScore < FRAMEWORK_MIN_SIMILARITY) {
    return "No matching framework found";
  }

  // Fetch full framework
  const { data: fw, error: fwErr } = await supabase
    .from("frameworks")
    .select("id, name, description, when_to_apply, principles, steps, example_application")
    .eq("id", topId)
    .maybeSingle();

  if (fwErr || !fw) {
    return "No matching framework found";
  }

  const text = assembleFrameworkText(fw);
  if (topScore < HIGH_CONFIDENCE_THRESHOLD) {
    return `[Framework: ${fw.name} (moderate confidence match)]\n${MODERATE_CONFIDENCE_CAVEAT}\n\n${text}`;
  }
  return text;
}

/**
 * Search knowledge base using a pre-computed embedding.
 * Extracted from searchKnowledgeBase — skips resolveAgent + embedQuery (already done).
 */
async function fetchKnowledgeBase(
  supabase: SupabaseClient,
  definitionId: string,
  queryEmbedding: number[]
): Promise<string> {
  // Check if agent has a knowledge base
  const { data: kbs } = await supabase
    .from("knowledge_bases")
    .select("id")
    .eq("agent_definition_id", definitionId)
    .limit(1);

  if (!kbs || kbs.length === 0) {
    return "No knowledge base configured for this agent. Proceeding without KB context.";
  }

  // Vector search via match_chunks RPC
  const { data: chunks, error: rpcErr } = await supabase.rpc("match_chunks", {
    query_embedding: queryEmbedding,
    scope_column: "agent_definition_id",
    scope_value: definitionId,
    match_count: KB_MATCH_COUNT,
  });

  if (rpcErr || !chunks || !Array.isArray(chunks) || chunks.length === 0) {
    return "No relevant knowledge base entries found";
  }

  // Filter by similarity threshold
  const filtered = chunks.filter(
    (c: Record<string, unknown>) => Number(c.similarity) >= KB_SIMILARITY_THRESHOLD
  );

  if (filtered.length === 0) {
    return "No relevant knowledge base entries found";
  }

  // Take top K
  const topChunks = filtered.slice(0, KB_TOP_K);

  // KIN-485 (Component D): preamble + per-chunk date suffix, env-var gated.
  // `assembleContext` already wraps this in a `## Knowledge Base` section, so
  // we prepend the preamble *inside* that section (right above the result
  // headers) when recency is on. Off-state is byte-identical.
  const recencyOn = isRecencyDateAwareEnabled();
  const lines: string[] = [];
  if (recencyOn) {
    lines.push(RECENCY_KB_PREAMBLE);
    lines.push("");
  }
  for (let i = 0; i < topChunks.length; i++) {
    const chunk = topChunks[i];
    const title = (chunk.document_title as string) || "Unknown";
    const section = chunk.section_path as string;
    const similarity = Number(chunk.similarity);
    const text = (chunk.text as string) || "";

    let header = `### [${i + 1}] ${title}`;
    if (section) header += ` > ${section}`;
    header += ` (relevance: ${similarity.toFixed(2)})`;
    header += formatChunkDateSuffix(chunk);

    lines.push(header);
    lines.push(text);
    lines.push("");
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Tool definitions for MCP registration
// ---------------------------------------------------------------------------

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export const TOOL_DEFINITIONS: ToolDefinition[] = [
  {
    name: "list_kinetic_agents",
    description:
      "List all available Kinetic agents — your own agents and public agents. Returns names, slugs, descriptions, and ownership.",
    inputSchema: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    name: "get_agent_persona",
    description:
      "Fetch an agent's persona — their name and system prompt instructions that define reasoning style and voice.",
    inputSchema: {
      type: "object",
      properties: {
        agent: {
          type: "string",
          description: "Agent slug (e.g., 'nate')",
        },
      },
      required: ["agent"],
    },
  },
  {
    name: "get_active_memory",
    description:
      "Fetch active memory entries for an agent — context from prior conversations, ordered most-recent-first.",
    inputSchema: {
      type: "object",
      properties: {
        agent: {
          type: "string",
          description: "Agent slug (e.g., 'nate')",
        },
      },
      required: ["agent"],
    },
  },
  {
    name: "select_framework",
    description:
      "Select the best-matching reasoning framework for a user question. Uses embedding similarity against framework trigger phrases.",
    inputSchema: {
      type: "object",
      properties: {
        agent: {
          type: "string",
          description: "Agent slug (e.g., 'nate')",
        },
        query: {
          type: "string",
          description: "The user's question to match against frameworks",
        },
      },
      required: ["agent", "query"],
    },
  },
  {
    name: "search_knowledge_base",
    description:
      "Search an agent's knowledge base for content relevant to a question. Uses embedding similarity to find the most relevant documents.",
    inputSchema: {
      type: "object",
      properties: {
        agent: {
          type: "string",
          description: "Agent slug (e.g., 'nate')",
        },
        query: {
          type: "string",
          description: "The user's question to search the knowledge base for",
        },
      },
      required: ["agent", "query"],
    },
  },
  {
    name: "assemble_context",
    description:
      "Assemble all context layers for an agent in a single call: persona, active memory, framework selection, and knowledge base search. More efficient than calling the 4 individual tools separately — use this as the default for full context assembly.",
    inputSchema: {
      type: "object",
      properties: {
        agent: {
          type: "string",
          description: "Agent slug (e.g., 'nate')",
        },
        query: {
          type: "string",
          description: "The user's question — used for framework matching and KB search",
        },
      },
      required: ["agent", "query"],
    },
  },
];

/**
 * Execute a tool by name with given arguments.
 */
export async function executeTool(
  supabase: SupabaseClient,
  userId: string,
  toolName: string,
  args: Record<string, unknown>,
  sessionId: string | null = null
): Promise<string> {
  // Validate required 'agent' param for agent-scoped tools
  const agentTools = [
    "get_agent_persona",
    "get_active_memory",
    "select_framework",
    "search_knowledge_base",
    "assemble_context",
  ];
  if (agentTools.includes(toolName) && !args.agent) {
    return `Error: Missing required parameter "agent" (the agent slug, e.g. "nate"). ` +
      `Call list_kinetic_agents to see available agents.`;
  }

  const queryTools = ["select_framework", "search_knowledge_base", "assemble_context"];
  if (queryTools.includes(toolName) && !args.query) {
    return `Error: Missing required parameter "query" (the user's question to search for).`;
  }

  switch (toolName) {
    case "list_kinetic_agents":
      return await listKineticAgents(supabase, userId);
    case "get_agent_persona":
      return await getAgentPersona(supabase, userId, args.agent as string);
    case "get_active_memory":
      return await getActiveMemory(supabase, userId, args.agent as string);
    case "select_framework":
      return await selectFramework(
        supabase,
        userId,
        args.agent as string,
        args.query as string
      );
    case "search_knowledge_base":
      return await searchKnowledgeBase(
        supabase,
        userId,
        args.agent as string,
        args.query as string
      );
    case "assemble_context":
      return await assembleContext(
        supabase,
        userId,
        args.agent as string,
        args.query as string,
        sessionId
      );
    default:
      return `Error: Unknown tool '${toolName}'`;
  }
}
