"""
Framework selection pipeline — KIN-289.

4-step pipeline per ADR-005:
  Step 1: pgvector embedding similarity search (top-10 candidates)
  Step 2: Apply AgentInstance overrides (boost pinned, filter excluded)
  Step 3: LLM reranker (claude-haiku-4-5) — select winner or None
  Step 4: Return winner framework row (injection-ready fields) or None

Called from context_stack.assemble() when active_agent_id is set.

ADR ref: docs/adr-005-agents-framework-selection.md
Schema ref: docs/db-schema-spec.md §14-15 (frameworks, framework_trigger_embeddings)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

try:
    import litellm  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRAMEWORK_MIN_SIMILARITY: float = 0.55  # Below this: skip reranker, return None
FRAMEWORK_EMBEDDING_MODEL: str = "text-embedding-3-large"
FRAMEWORK_RERANKER_MODEL: str = "anthropic/claude-haiku-4-5-20251001"
PINNED_BOOST: float = 0.15  # Score boost for pinned frameworks

# Fields injected into L7 (strips routing/metadata fields per ADR-005 §2)
_INJECT_FIELDS = {
    "name", "description", "type", "principles", "steps",
    "example_application", "adjacent_ids", "guidance",
}

# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


async def _run(fn: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn)


# ---------------------------------------------------------------------------
# Step 1: Embedding similarity search
# ---------------------------------------------------------------------------


async def _embed_query(query: str, api_key: str) -> Optional[list[float]]:
    """Embed the enriched query using the platform OpenAI key."""
    try:
        response = await litellm.aembedding(
            model=FRAMEWORK_EMBEDDING_MODEL,
            input=[query],
            api_key=api_key,
        )
        return response.data[0]["embedding"]
    except Exception as exc:
        logger.warning("Framework embedding failed: %s", exc)
        return None


async def _search_embeddings(
    supabase: Any,
    agent_definition_id: str,
    query_embedding: list[float],
) -> list[dict]:
    """
    Run pgvector cosine similarity search for the agent's framework trigger embeddings.
    Returns top-10 distinct frameworks by max similarity score.

    Uses manual in-Python similarity since Supabase REST cosine search requires
    a custom RPC function. Falls back to fetching all embeddings and computing in-process.
    At MVP scale (~575 vectors per agent) this is acceptable.
    """
    result = await _run(
        lambda: supabase.table("framework_trigger_embeddings")
        .select("framework_db_id, embedding")
        .eq("agent_definition_id", agent_definition_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return []

    # Compute cosine similarity in-process
    import math

    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # Score each trigger embedding row; keep max per framework_db_id
    scores: dict[str, float] = {}
    for row in rows:
        embedding = row.get("embedding")
        if not embedding:
            continue
        if isinstance(embedding, str):
            try:
                embedding = json.loads(embedding)
            except Exception:
                continue
        sim = cosine_similarity(query_embedding, embedding)
        fw_id = row["framework_db_id"]
        if fw_id not in scores or sim > scores[fw_id]:
            scores[fw_id] = sim

    # Sort by score descending, take top 10
    top_ids = sorted(scores, key=lambda k: scores[k], reverse=True)[:10]
    if not top_ids:
        return []

    # Fetch full framework rows for top candidates
    fw_result = await _run(
        lambda: supabase.table("frameworks")
        .select("*")
        .in_("id", top_ids)
        .execute()
    )
    fw_rows = fw_result.data or []

    # Attach similarity score
    score_map = {fw_id: scores[fw_id] for fw_id in top_ids}
    for row in fw_rows:
        row["_similarity"] = score_map.get(row["id"], 0.0)

    fw_rows.sort(key=lambda r: r["_similarity"], reverse=True)
    return fw_rows


# ---------------------------------------------------------------------------
# Step 2: Apply AgentInstance overrides
# ---------------------------------------------------------------------------


def _apply_overrides(
    candidates: list[dict],
    overrides: dict,
) -> list[dict]:
    """
    Filter excluded frameworks and boost pinned frameworks.
    Returns top-5 after adjustments.
    ADR ref: docs/adr-005-agents-framework-selection.md §2 Step 2
    """
    pinned = set(overrides.get("pinned", []))
    excluded = set(overrides.get("excluded", []))

    # Filter excluded
    candidates = [c for c in candidates if c["id"] not in excluded]

    # Boost pinned
    for c in candidates:
        if c["id"] in pinned:
            c["_similarity"] = min(1.0, c["_similarity"] + PINNED_BOOST)

    candidates.sort(key=lambda c: c["_similarity"], reverse=True)
    return candidates[:5]


# ---------------------------------------------------------------------------
# Step 3: LLM reranker
# ---------------------------------------------------------------------------

_RERANKER_SYSTEM = """\
You are a framework selection judge for an AI assistant. Given a user's message \
and a set of candidate reasoning frameworks, select the single most applicable \
framework — or output "none" if no framework is a strong match.

A framework is a strong match if:
- It directly addresses the underlying question the user is wrestling with
- Applying it would produce meaningfully better reasoning than not applying it
- The user's situation does not match the framework's anti_triggers

Output only the framework ID (e.g., "pricing-strategy-premium") or the word "none". \
No explanation."""


def _build_reranker_prompt(enriched_query: str, candidates: list[dict]) -> str:
    parts = [f"User message:\n{enriched_query}\n\nCandidate frameworks:"]
    for c in candidates:
        when_to_apply = (c.get("when_to_apply") or [])[:2]
        anti_triggers = (c.get("anti_triggers") or [])[:2]
        core_question = c.get("core_question") or ""
        parts.append(
            f"\nID: {c['id']}\n"
            f"Name: {c.get('name', '')}\n"
            f"Description: {c.get('description', '')}\n"
            f"Core question: {core_question}\n"
            f"When to apply: {'; '.join(when_to_apply)}\n"
            f"Anti-triggers: {'; '.join(anti_triggers)}"
        )
    parts.append("\nSelect the best framework ID, or output \"none\".")
    return "\n".join(parts)


async def _rerank(
    enriched_query: str,
    candidates: list[dict],
    api_key: str,
) -> Optional[str]:
    """Call Haiku to select the best framework ID from candidates, or return None."""
    prompt = _build_reranker_prompt(enriched_query, candidates)
    try:
        response = await litellm.acompletion(
            model=FRAMEWORK_RERANKER_MODEL,
            messages=[
                {"role": "system", "content": _RERANKER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=30,
            temperature=0.0,
            api_key=api_key,
        )
        winner = response.choices[0].message.content.strip().lower()
        if winner == "none":
            return None
        return winner
    except Exception as exc:
        logger.warning("Framework reranker failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Step 4: Build injection payload
# ---------------------------------------------------------------------------


def _build_injection_payload(framework_row: dict) -> dict:
    """
    Strip routing/metadata fields and return only injection-ready fields.
    ADR ref: docs/adr-005-agents-framework-selection.md §2 Step 4
    """
    return {k: v for k, v in framework_row.items() if k in _INJECT_FIELDS}


def format_framework_for_prompt(framework: dict) -> str:
    """Format a framework dict as an L7 context section."""
    lines = [f"## Active Framework: {framework.get('name', 'Framework')}\n"]

    if framework.get("description"):
        lines.append(framework["description"] + "\n")

    if framework.get("guidance"):
        lines.append(framework["guidance"] + "\n")

    principles = framework.get("principles") or []
    if principles:
        lines.append("**Principles:**")
        for p in principles:
            lines.append(f"- {p}")
        lines.append("")

    steps = framework.get("steps") or []
    if steps:
        lines.append("**Steps:**")
        for i, s in enumerate(steps, 1):
            lines.append(f"{i}. {s}")
        lines.append("")

    if framework.get("example_application"):
        lines.append(f"**Example:**\n{framework['example_application']}\n")

    adjacent = framework.get("adjacent_ids") or []
    if adjacent:
        lines.append(f"**Related frameworks to consider:** {', '.join(adjacent)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def select_framework(
    supabase: Any,
    agent_definition_id: str,
    enriched_query: str,
    framework_overrides: dict,
    *,
    platform_openai_key: Optional[str] = None,
    platform_anthropic_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Run the 4-step framework selection pipeline.

    Returns the selected framework dict (injection-ready fields only), or None if:
    - No frameworks exist for this agent
    - Top similarity score is below FRAMEWORK_MIN_SIMILARITY
    - Reranker returns "none"
    - Any platform key is missing (silent degradation)

    ADR ref: docs/adr-005-agents-framework-selection.md
    """
    openai_key = platform_openai_key or os.environ.get("PLATFORM_OPENAI_KEY", "")
    anthropic_key = platform_anthropic_key or os.environ.get("PLATFORM_ANTHROPIC_KEY", "")

    if not openai_key:
        logger.warning("PLATFORM_OPENAI_KEY not set — framework selection skipped")
        return None
    if not anthropic_key:
        logger.warning("PLATFORM_ANTHROPIC_KEY not set — framework selection skipped")
        return None

    # Step 1: Embed + search
    query_embedding = await _embed_query(enriched_query, openai_key)
    if not query_embedding:
        return None

    candidates = await _search_embeddings(supabase, agent_definition_id, query_embedding)
    if not candidates:
        return None

    # Confidence gate: skip reranker if top score is too low
    top_score = candidates[0].get("_similarity", 0.0)
    if top_score < FRAMEWORK_MIN_SIMILARITY:
        logger.debug(
            "Framework top score %.3f below threshold %.3f — no injection",
            top_score,
            FRAMEWORK_MIN_SIMILARITY,
        )
        return None

    # Step 2: Apply overrides
    candidates = _apply_overrides(candidates, framework_overrides)
    if not candidates:
        return None

    # Step 3: Reranker
    winner_id = await _rerank(enriched_query, candidates, anthropic_key)
    if not winner_id:
        return None

    # Find the winner row
    winner_row = next((c for c in candidates if c["id"] == winner_id), None)
    if not winner_row:
        logger.warning("Reranker returned unknown framework ID: %s", winner_id)
        return None

    # Step 4: Build injection payload
    return _build_injection_payload(winner_row)
