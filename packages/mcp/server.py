"""
Kinetic Brain MCP Server — bridges Cowork to Kinetic's Supabase backend.

Exposes 5 tools for context assembly:
  - get_agent_persona (L5)
  - get_active_memory (L6)
  - select_framework (L7)
  - search_knowledge_base (L9)
  - assemble_context (all layers in one call)
"""

import logging
import os
from collections import defaultdict

import openai
from mcp.server.fastmcp import Context, FastMCP
from supabase import Client, create_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-large"  # 3072 dims
FRAMEWORK_TRIGGER_TOP_K = 20
FRAMEWORK_MIN_SIMILARITY = 0.55
MULTI_TRIGGER_BOOST = 0.05
KB_MATCH_COUNT = 20
KB_SIMILARITY_THRESHOLD = 0.3
KB_TOP_K = 8


# ---------------------------------------------------------------------------
# Initialize clients at module level
# ---------------------------------------------------------------------------

_supabase_url = os.environ.get("SUPABASE_URL", "")
_supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_openai_key = os.environ.get("OPENAI_API_KEY", "")

if not _supabase_url or not _supabase_key:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
if not _openai_key:
    raise RuntimeError("OPENAI_API_KEY must be set")

_supabase: Client = create_client(_supabase_url, _supabase_key)
_oai = openai.OpenAI(api_key=_openai_key)

_APP_STATE = {
    "supabase": _supabase,
    "openai": _oai,
    "agent_id": os.environ.get("NATE_AGENT_ID", ""),
    "instance_id": os.environ.get("NATE_INSTANCE_ID", ""),
    "user_id": os.environ.get("KINETIC_USER_ID", ""),
}

mcp = FastMCP("kinetic_brain_mcp")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def embed_query(oai_client: openai.OpenAI, text: str) -> list[float]:
    """Embed a single text using OpenAI text-embedding-3-large (3072 dims)."""
    response = oai_client.embeddings.create(input=[text], model=EMBEDDING_MODEL)
    return response.data[0].embedding


def _get_state(ctx: Context) -> dict:
    """Retrieve app state."""
    return _APP_STATE


# ---------------------------------------------------------------------------
# Tool: get_agent_persona (L5)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_agent_persona",
    annotations={
        "title": "Get Agent Persona",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_agent_persona(ctx: Context) -> str:
    """Fetch Nate's agent persona — name and system prompt instructions.

    Returns the agent's name and full instructions text, which defines
    the reasoning style and voice for the advisory conversation.
    """
    state = _get_state(ctx)
    supabase: Client = state["supabase"]
    agent_id = state["agent_id"]

    if not agent_id:
        return "Error: NATE_AGENT_ID not configured"

    try:
        result = (
            supabase.table("agent_definitions")
            .select("id, name, instructions")
            .eq("id", agent_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.error("Failed to fetch agent persona: %s", e)
        return f"Error fetching agent persona: {e}"

    if not result.data:
        return "Agent not found"

    row = result.data
    name = row.get("name", "Unknown")
    instructions = row.get("instructions", "")

    if not instructions:
        return f"# {name}\n\nNo instructions configured for this agent."

    return f"# {name}\n\n{instructions}"


# ---------------------------------------------------------------------------
# Tool: get_active_memory (L6)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_active_memory",
    annotations={
        "title": "Get Active Memory",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def get_active_memory(ctx: Context) -> str:
    """Fetch active memory entries for Nate's agent instance.

    Returns recent memory entries that provide context from prior
    conversations, ordered most-recent-first.
    """
    state = _get_state(ctx)
    supabase: Client = state["supabase"]
    instance_id = state["instance_id"]
    user_id = state["user_id"]

    if not instance_id or not user_id:
        return "No active memories (instance or user not configured)"

    try:
        result = (
            supabase.table("active_memory_entries")
            .select("id, content, created_at, updated_at")
            .eq("agent_instance_id", instance_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.error("Failed to fetch active memory: %s", e)
        return f"Error fetching active memory: {e}"

    entries = result.data or []
    if not entries:
        return "No active memories"

    lines = ["# Active Memory\n"]
    for entry in entries:
        content = entry.get("content", "")
        created = entry.get("created_at", "")[:10]  # date only
        lines.append(f"- **{created}:** {content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: select_framework (L7)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="select_framework",
    annotations={
        "title": "Select Framework",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def select_framework(query: str, ctx: Context) -> str:
    """Select the best-matching framework for the user's question.

    Uses embedding similarity against framework trigger phrases, with
    multi-trigger boosting and a confidence gate. Returns the full
    framework text if a match is found.

    Args:
        query: The user's question to match against frameworks.
    """
    state = _get_state(ctx)
    supabase: Client = state["supabase"]
    oai: openai.OpenAI = state["openai"]
    agent_id = state["agent_id"]

    if not agent_id:
        return "Framework selection unavailable (agent not configured)"

    # Step 1: Embed the query
    try:
        query_embedding = embed_query(oai, query)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return "Framework selection unavailable (embedding error)"

    # Step 2: Vector search on framework triggers
    try:
        result = supabase.rpc(
            "match_framework_triggers",
            {
                "query_embedding": query_embedding,
                "p_agent_id": agent_id,
                "match_count": FRAMEWORK_TRIGGER_TOP_K,
            },
        ).execute()
    except Exception as e:
        logger.error("Framework trigger search failed: %s", e)
        return f"Framework selection unavailable (search error): {e}"

    triggers = result.data if isinstance(result.data, list) else []
    if not triggers:
        return "No matching framework found"

    # Step 3: Group by framework, apply multi-trigger boost
    framework_scores: dict[str, dict] = defaultdict(
        lambda: {"max_sim": 0.0, "count": 0}
    )
    for t in triggers:
        fid = t["framework_db_id"]
        sim = float(t["similarity"])
        entry = framework_scores[fid]
        entry["max_sim"] = max(entry["max_sim"], sim)
        entry["count"] += 1

    ranked = []
    for fid, scores in framework_scores.items():
        boosted = scores["max_sim"] + (scores["count"] - 1) * MULTI_TRIGGER_BOOST
        ranked.append((fid, boosted))

    ranked.sort(key=lambda x: x[1], reverse=True)

    # Step 4: Confidence gate
    top_id, top_score = ranked[0]
    if top_score < FRAMEWORK_MIN_SIMILARITY:
        return "No matching framework found"

    # Step 5: Fetch full framework
    try:
        fw_result = (
            supabase.table("frameworks")
            .select("id, name, description, when_to_apply, principles, steps, example_application")
            .eq("id", top_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logger.error("Framework fetch failed: %s", e)
        return f"Framework selection unavailable (fetch error): {e}"

    if not fw_result.data:
        return "No matching framework found"

    fw = fw_result.data
    return _assemble_framework_text(fw)


def _assemble_framework_text(fw: dict) -> str:
    """Assemble framework fields into a single context block."""
    parts = []

    name = fw.get("name", "")
    if name:
        parts.append(f"# Framework: {name}\n")

    description = fw.get("description", "")
    if description:
        parts.append(description)

    when_to_apply = fw.get("when_to_apply", [])
    if when_to_apply:
        items = when_to_apply if isinstance(when_to_apply, list) else [when_to_apply]
        parts.append("\n## When to Apply\n" + "\n".join(f"- {w}" for w in items))

    principles = fw.get("principles", [])
    if principles:
        items = principles if isinstance(principles, list) else [principles]
        parts.append("\n## Principles\n" + "\n".join(f"- {p}" for p in items))

    steps = fw.get("steps", [])
    if steps:
        items = steps if isinstance(steps, list) else [steps]
        parts.append("\n## Steps\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(items)))

    example = fw.get("example_application", "")
    if example:
        parts.append(f"\n## Example Application\n{example}")

    return "\n".join(parts) if parts else "No matching framework found"


# ---------------------------------------------------------------------------
# Tool: search_knowledge_base (L9)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="search_knowledge_base",
    annotations={
        "title": "Search Knowledge Base",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_knowledge_base(query: str, ctx: Context) -> str:
    """Search Nate's knowledge base for content relevant to the user's question.

    Uses embedding similarity to find the most relevant KB chunks,
    filtered by similarity threshold and limited to top results.

    Args:
        query: The user's question to search the knowledge base for.
    """
    state = _get_state(ctx)
    supabase: Client = state["supabase"]
    oai: openai.OpenAI = state["openai"]
    agent_id = state["agent_id"]

    if not agent_id:
        return "KB search unavailable (agent not configured)"

    # Step 1: Embed the query
    try:
        query_embedding = embed_query(oai, query)
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return "KB search unavailable (embedding error)"

    # Step 2: Vector search on KB chunks
    try:
        result = supabase.rpc(
            "match_chunks",
            {
                "query_embedding": query_embedding,
                "scope_column": "agent_definition_id",
                "scope_value": agent_id,
                "match_count": KB_MATCH_COUNT,
            },
        ).execute()
    except Exception as e:
        logger.error("KB search failed: %s", e)
        return f"KB search unavailable (search error): {e}"

    chunks = result.data if isinstance(result.data, list) else []
    if not chunks:
        return "No relevant knowledge base entries found"

    # Step 3: Filter by similarity threshold
    chunks = [c for c in chunks if float(c.get("similarity", 0)) >= KB_SIMILARITY_THRESHOLD]

    if not chunks:
        return "No relevant knowledge base entries found"

    # Step 4: Take top K
    chunks = chunks[:KB_TOP_K]

    # Step 5: Format with metadata
    lines = ["# Knowledge Base Results\n"]
    for i, chunk in enumerate(chunks, 1):
        title = chunk.get("document_title", "Unknown")
        section = chunk.get("section_path", "")
        similarity = float(chunk.get("similarity", 0))
        text = chunk.get("text", "")

        header = f"## [{i}] {title}"
        if section:
            header += f" > {section}"
        header += f" (relevance: {similarity:.2f})"

        lines.append(header)
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared layer helpers (used by both individual tools and assemble_context)
# ---------------------------------------------------------------------------

def _fetch_persona(supabase: Client, agent_id: str) -> str:
    """Fetch agent persona. Returns formatted persona string or empty string."""
    if not agent_id:
        return ""

    result = (
        supabase.table("agent_definitions")
        .select("id, name, instructions")
        .eq("id", agent_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        return ""

    row = result.data
    name = row.get("name", "Unknown")
    instructions = row.get("instructions", "")

    if not instructions:
        return f"# {name}\n\nNo instructions configured for this agent."

    return f"# {name}\n\n{instructions}"


def _fetch_active_memory(supabase: Client, instance_id: str, user_id: str) -> str:
    """Fetch active memory entries. Returns formatted memory or 'No active memories'."""
    if not instance_id or not user_id:
        return "No active memories"

    result = (
        supabase.table("active_memory_entries")
        .select("id, content, created_at, updated_at")
        .eq("agent_instance_id", instance_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    entries = result.data or []
    if not entries:
        return "No active memories"

    lines = []
    for entry in entries:
        content = entry.get("content", "")
        created = entry.get("created_at", "")[:10]
        lines.append(f"- **{created}:** {content}")

    return "\n".join(lines)


def _fetch_framework(supabase: Client, agent_id: str, query_embedding: list[float]) -> str:
    """Select best-matching framework using a pre-computed embedding."""
    result = supabase.rpc(
        "match_framework_triggers",
        {
            "query_embedding": query_embedding,
            "p_agent_id": agent_id,
            "match_count": FRAMEWORK_TRIGGER_TOP_K,
        },
    ).execute()

    triggers = result.data if isinstance(result.data, list) else []
    if not triggers:
        return "No matching framework found"

    # Group by framework, apply multi-trigger boost
    framework_scores: dict[str, dict] = defaultdict(
        lambda: {"max_sim": 0.0, "count": 0}
    )
    for t in triggers:
        fid = t["framework_db_id"]
        sim = float(t["similarity"])
        entry = framework_scores[fid]
        entry["max_sim"] = max(entry["max_sim"], sim)
        entry["count"] += 1

    ranked = []
    for fid, scores in framework_scores.items():
        boosted = scores["max_sim"] + (scores["count"] - 1) * MULTI_TRIGGER_BOOST
        ranked.append((fid, boosted))

    ranked.sort(key=lambda x: x[1], reverse=True)

    top_id, top_score = ranked[0]
    if top_score < FRAMEWORK_MIN_SIMILARITY:
        return "No matching framework found"

    fw_result = (
        supabase.table("frameworks")
        .select("id, name, description, when_to_apply, principles, steps, example_application")
        .eq("id", top_id)
        .maybe_single()
        .execute()
    )

    if not fw_result.data:
        return "No matching framework found"

    return _assemble_framework_text(fw_result.data)


def _fetch_knowledge_base(supabase: Client, agent_id: str, query_embedding: list[float]) -> str:
    """Search KB using a pre-computed embedding."""
    result = supabase.rpc(
        "match_chunks",
        {
            "query_embedding": query_embedding,
            "scope_column": "agent_definition_id",
            "scope_value": agent_id,
            "match_count": KB_MATCH_COUNT,
        },
    ).execute()

    chunks = result.data if isinstance(result.data, list) else []
    if not chunks:
        return "No relevant knowledge base entries found"

    chunks = [c for c in chunks if float(c.get("similarity", 0)) >= KB_SIMILARITY_THRESHOLD]
    if not chunks:
        return "No relevant knowledge base entries found"

    chunks = chunks[:KB_TOP_K]

    lines = []
    for i, chunk in enumerate(chunks, 1):
        title = chunk.get("document_title", "Unknown")
        section = chunk.get("section_path", "")
        similarity = float(chunk.get("similarity", 0))
        text = chunk.get("text", "")

        header = f"### [{i}] {title}"
        if section:
            header += f" > {section}"
        header += f" (relevance: {similarity:.2f})"

        lines.append(header)
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: assemble_context (all layers)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="assemble_context",
    annotations={
        "title": "Assemble Context",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def assemble_context(query: str, ctx: Context) -> str:
    """Assemble all context layers for an agent in a single call: persona,
    active memory, framework selection, and knowledge base search.

    More efficient than calling the 4 individual tools separately — use this
    as the default for full context assembly.

    Args:
        query: The user's question — used for framework matching and KB search.
    """
    state = _get_state(ctx)
    supabase: Client = state["supabase"]
    oai: openai.OpenAI = state["openai"]
    agent_id = state["agent_id"]
    instance_id = state["instance_id"]
    user_id = state["user_id"]

    sections: list[str] = []

    # --- Layer 1: Persona (single agent lookup from _APP_STATE) ---
    try:
        persona = _fetch_persona(supabase, agent_id)
        if persona:
            sections.append("## Persona\n\n" + persona)
    except Exception as e:
        logger.error("assemble_context: persona fetch failed: %s", e)
        # Graceful degradation — skip persona

    # --- Layer 2: Active Memory (no embedding needed) ---
    try:
        memory = _fetch_active_memory(supabase, instance_id, user_id)
        sections.append("## Active Memory\n\n" + memory)
    except Exception as e:
        logger.error("assemble_context: memory fetch failed: %s", e)
        sections.append("## Active Memory\n\nNo active memories")

    # --- Single embedding call (shared by framework + KB) ---
    query_embedding: list[float] | None = None
    embedding_error: str | None = None
    try:
        query_embedding = embed_query(oai, query)
    except Exception as e:
        logger.error("assemble_context: embedding failed: %s", e)
        embedding_error = f"Embedding unavailable: {e}"

    # --- Layer 3: Framework (requires embedding) ---
    if query_embedding:
        try:
            framework = _fetch_framework(supabase, agent_id, query_embedding)
            sections.append("## Framework\n\n" + framework)
        except Exception as e:
            logger.error("assemble_context: framework fetch failed: %s", e)
            sections.append("## Framework\n\nNo matching framework found")
    else:
        sections.append("## Framework\n\n" + (embedding_error or "No matching framework found"))

    # --- Layer 4: Knowledge Base (requires embedding) ---
    if query_embedding:
        try:
            kb = _fetch_knowledge_base(supabase, agent_id, query_embedding)
            sections.append("## Knowledge Base\n\n" + kb)
        except Exception as e:
            logger.error("assemble_context: KB search failed: %s", e)
            sections.append("## Knowledge Base\n\nNo relevant knowledge base entries found")
    else:
        sections.append("## Knowledge Base\n\n" + (embedding_error or "No relevant knowledge base entries found"))

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if "--sse" in sys.argv:
        mcp.settings.port = 8765
        mcp.run(transport="sse")
    else:
        mcp.run()
