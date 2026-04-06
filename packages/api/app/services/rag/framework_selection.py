"""
Framework selection pipeline — KIN-322.

4-step pipeline that matches a user query to the best framework for an agent:
  1. Embed query → cosine search on framework_trigger_embeddings
  2. Group by framework, apply multi-trigger boost
  3. Rerank top candidates via Haiku
  4. Confidence gate (FRAMEWORK_MIN_SIMILARITY)

Schema: docs/db-schema-spec.md §14 (frameworks), §15 (framework_trigger_embeddings)
ADR: docs/adr-003-agents-architecture.md (framework selection pipeline)
Spec: docs/specs/mcp-spec.md §4.4
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRAMEWORK_TRIGGER_TOP_K = 20      # candidates from vector search
FRAMEWORK_TOP_K = 5               # after grouping, before reranker
FRAMEWORK_MIN_SIMILARITY = 0.62   # confidence gate (below = no match)
HIGH_CONFIDENCE_THRESHOLD = 0.75  # above = inject normally; between MIN and this = caveat
MULTI_TRIGGER_BOOST = 0.05        # boost per additional trigger match

# Context enrichment (KIN-447)
MAX_CONTEXT_PREFIX_CHARS = 200    # ~50 tokens; hard cap to avoid diluting query signal


# ---------------------------------------------------------------------------
# Context enrichment — KIN-447
# ---------------------------------------------------------------------------

@dataclass
class QueryContext:
    """Optional context for embedding enrichment.

    Fields mirror L1 (user), L2 (company), L3 (project), L5 (agent)
    data available at query time. Null/empty fields are skipped.
    """
    agent_name: Optional[str] = None       # L5 — strongest scoping signal for KB
    company_name: Optional[str] = None     # L2
    company_description: Optional[str] = None  # L2
    user_bio: Optional[str] = None         # L1
    project_name: Optional[str] = None     # L3


def build_enriched_query(query: str, context: QueryContext | None = None) -> str:
    """Prepend available context to query before embedding.

    Template (fields skipped if null/empty):
        [Agent: {name}]
        [Company: {name} — {description_excerpt}]
        [User: {bio_excerpt}]
        [Project: {name}]
        {original_query}

    Agent goes first — strongest scoping signal for KB retrieval (KIN-450).
    Keeps prefix under MAX_CONTEXT_PREFIX_CHARS (~50 tokens) to avoid
    diluting the query signal.
    """
    if context is None:
        return query

    parts: list[str] = []

    # Agent first — strongest scope signal for KB (KIN-450)
    if context.agent_name:
        parts.append(f"[Agent: {context.agent_name}]")

    if context.company_name:
        line = f"[Company: {context.company_name}"
        if context.company_description:
            # Truncate description to keep total short
            desc = context.company_description[:80].strip()
            line += f" — {desc}"
        line += "]"
        parts.append(line)

    if context.user_bio:
        parts.append(f"[User: {context.user_bio[:80].strip()}]")

    if context.project_name:
        parts.append(f"[Project: {context.project_name}]")

    if not parts:
        return query

    prefix = "\n".join(parts)
    if len(prefix) > MAX_CONTEXT_PREFIX_CHARS:
        prefix = prefix[:MAX_CONTEXT_PREFIX_CHARS]

    return prefix + "\n" + query


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class FrameworkMatch:
    """Result of the framework selection pipeline."""
    matched_framework_id: Optional[str]
    matched_framework_name: Optional[str]
    framework_text: Optional[str]    # Full framework assembled as L7 context
    confidence_score: float = 0.0
    high_confidence: bool = True


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _assemble_framework_text(fw: dict) -> str:
    """Build L7 context text from a framework row dict."""
    parts = [f"Framework: {fw['name']}"]
    if fw.get("description"):
        parts.append(f"Description: {fw['description']}")
    if fw.get("when_to_apply"):
        parts.append(f"When to apply: {', '.join(fw['when_to_apply'])}")
    if fw.get("principles"):
        parts.append("Principles:\n" + "\n".join(f"- {p}" for p in fw["principles"]))
    if fw.get("steps"):
        parts.append("Steps:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(fw["steps"])))
    if fw.get("example_application"):
        parts.append(f"Example: {fw['example_application']}")
    return "\n\n".join(parts)


_FW_SELECT_COLS = "id, name, description, when_to_apply, principles, steps, example_application"


async def fetch_pinned_frameworks(
    pinned_ids: list[str],
    supabase,
) -> list[FrameworkMatch]:
    """Fetch pinned frameworks directly by ID, bypassing the selection pipeline.

    Returns a FrameworkMatch per pinned ID that exists in the DB.
    Missing IDs are silently skipped (fail-open).

    Spec: docs/specs/agents.md §11.4
    """
    loop = asyncio.get_running_loop()
    matches: list[FrameworkMatch] = []
    for fid in pinned_ids:
        try:
            fw_result = await loop.run_in_executor(
                None,
                lambda fid=fid: supabase.table("frameworks")
                    .select(_FW_SELECT_COLS)
                    .eq("id", fid)
                    .maybe_single()
                    .execute(),
            )
            if fw_result.data:
                fw = fw_result.data
                matches.append(FrameworkMatch(
                    matched_framework_id=fw["id"],
                    matched_framework_name=fw["name"],
                    framework_text=_assemble_framework_text(fw),
                ))
        except Exception:
            logger.warning("Failed to fetch pinned framework %s — skipping", fid, exc_info=True)
    return matches


async def select_framework(
    query_text: str,
    agent_id: str,
    supabase,
    openai_key: str = "",
    excluded_ids: set[str] | None = None,
    context: QueryContext | None = None,
) -> FrameworkMatch:
    """
    Run the 4-step framework selection pipeline for MCP context assembly (L7).

    Uses user's BYOK OpenAI key for embedding.

    Args:
        excluded_ids: Framework IDs to exclude from the candidate pool
            before ranking. Spec: docs/specs/agents.md §11.4.
        context: Optional L1/L2/L3 context for query enrichment (KIN-447).
            When provided, context is prepended to the query before embedding
            to shift results toward contextually relevant frameworks.

    Returns FrameworkMatch with matched_framework_id=None if no framework
    matches above the confidence threshold.

    Fails open: if embedding or search fails, returns no-match rather than
    raising. The MCP response will simply omit L7.
    """
    loop = asyncio.get_running_loop()
    no_match = FrameworkMatch(matched_framework_id=None, matched_framework_name=None, framework_text=None)

    try:
        # Step 1: Enrich query with context, then embed (KIN-447)
        enriched_query = build_enriched_query(query_text, context)

        from app.services.ingestion.embedder import EmbeddingService
        embedder = EmbeddingService(api_key=openai_key)
        query_embedding = await loop.run_in_executor(
            None, lambda: embedder.embed_batch([enriched_query])[0]
        )

        # Step 2: Vector search on framework_trigger_embeddings
        result = await loop.run_in_executor(
            None,
            lambda: supabase.rpc(
                "match_framework_triggers",
                {
                    "query_embedding": query_embedding,
                    "p_agent_id": agent_id,
                    "match_count": FRAMEWORK_TRIGGER_TOP_K,
                },
            ).execute(),
        )
        triggers = result.data if isinstance(result.data, list) else []

        if not triggers:
            return no_match

        # Step 2b: Filter excluded frameworks from candidate pool (KIN-391)
        if excluded_ids:
            triggers = [t for t in triggers if t["framework_db_id"] not in excluded_ids]
            if not triggers:
                return no_match

        # Step 3: Group by framework, count triggers, apply boost
        framework_scores: dict[str, dict] = {}
        for trigger in triggers:
            fid = trigger["framework_db_id"]
            sim = trigger.get("similarity", 0.0)
            if fid not in framework_scores:
                framework_scores[fid] = {"max_sim": sim, "trigger_count": 1}
            else:
                framework_scores[fid]["max_sim"] = max(framework_scores[fid]["max_sim"], sim)
                framework_scores[fid]["trigger_count"] += 1

        # Apply multi-trigger boost and sort
        for fid, scores in framework_scores.items():
            extra_triggers = scores["trigger_count"] - 1
            scores["boosted_score"] = scores["max_sim"] + (extra_triggers * MULTI_TRIGGER_BOOST)

        ranked = sorted(
            framework_scores.items(),
            key=lambda x: x[1]["boosted_score"],
            reverse=True,
        )[:FRAMEWORK_TOP_K]

        # Step 4: Confidence gate (skip Haiku reranker for MVP — use boosted score)
        top_fid, top_scores = ranked[0]
        boosted = top_scores["boosted_score"]
        if boosted < FRAMEWORK_MIN_SIMILARITY:
            return no_match

        # Fetch the winning framework
        fw_result = await loop.run_in_executor(
            None,
            lambda: supabase.table("frameworks")
                .select(_FW_SELECT_COLS)
                .eq("id", top_fid)
                .single()
                .execute(),
        )
        if not fw_result.data:
            logger.warning(f"Framework {top_fid} not found in frameworks table")
            return no_match

        fw = fw_result.data
        framework_text = _assemble_framework_text(fw)

        return FrameworkMatch(
            matched_framework_id=fw["id"],
            matched_framework_name=fw["name"],
            framework_text=framework_text,
            confidence_score=boosted,
            high_confidence=boosted >= HIGH_CONFIDENCE_THRESHOLD,
        )

    except Exception:
        logger.warning("Framework selection pipeline failed — omitting L7", exc_info=True)
        return no_match
