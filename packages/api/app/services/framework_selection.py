"""
Framework selection pipeline — KIN-289.

4-step pipeline (ADR-003 §6):
  1. Embed the query
  2. Cosine similarity against all trigger embeddings for the agent's frameworks
  3. Expertise boost (+FRAMEWORK_EXPERTISE_BOOST for each additional trigger
     match above the short-circuit threshold)
  4. Haiku reranker — if ≥1 candidate above FRAMEWORK_MIN_RERANK_THRESHOLD,
     call Claude Haiku to select the best framework
  Returns the winning framework dict, or None if no match is good enough.

Entry point: select_framework(query, agent_definition_id, agent_category, supabase)

ADR ref:    docs/adr-003-agents-architecture.md §6
Schema ref: docs/db-schema-spec.md §14-15 (frameworks, framework_trigger_embeddings)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def select_framework(
    *,
    query: str,
    agent_definition_id: str,
    agent_category: Optional[str],
    supabase: Any,
) -> Optional[dict]:
    """Run the 4-step framework selection pipeline.

    Returns a framework row dict (from the frameworks table) or None.
    """
    from app.config import get_settings
    from app.services.embedding_service import embed_text

    settings = get_settings()
    loop = asyncio.get_running_loop()

    async def db(fn: Any) -> Any:
        return await loop.run_in_executor(None, fn)

    # Step 1 — Embed the query
    try:
        query_embedding = await embed_text(query)
    except Exception:
        logger.exception("Embedding failed in framework selection for agent %s", agent_definition_id)
        return None

    # Fetch all trigger embeddings for this agent's frameworks
    try:
        triggers_result = await db(
            lambda: supabase.table("framework_trigger_embeddings")
            .select("framework_db_id, trigger_text, embedding")
            .eq("agent_definition_id", agent_definition_id)
            .execute()
        )
        trigger_rows: list[dict] = triggers_result.data or []
    except Exception:
        logger.exception("Failed to fetch trigger embeddings for agent %s", agent_definition_id)
        return None

    if not trigger_rows:
        return None

    # Filter out rows without embeddings
    trigger_rows = [r for r in trigger_rows if r.get("embedding")]
    if not trigger_rows:
        return None

    # Step 2 — Cosine similarity + Step 3 — Expertise boost
    scored = _score_frameworks(
        query_embedding=query_embedding,
        trigger_rows=trigger_rows,
        expertise_boost=settings.FRAMEWORK_EXPERTISE_BOOST,
        boost_threshold=settings.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT,
    )

    # Short-circuit: no candidate above minimum threshold
    candidates = [s for s in scored if s["score"] >= settings.FRAMEWORK_SIMILARITY_SHORT_CIRCUIT]
    if not candidates:
        return None

    # Fetch framework rows for candidates
    candidate_ids = [c["framework_db_id"] for c in candidates[: settings.FRAMEWORK_TOP_K]]
    try:
        fw_result = await db(
            lambda: supabase.table("frameworks")
            .select("*")
            .in_("id", candidate_ids)
            .execute()
        )
        framework_rows: list[dict] = fw_result.data or []
    except Exception:
        logger.exception("Failed to fetch framework rows for agent %s", agent_definition_id)
        return None

    if not framework_rows:
        return None

    # Build lookup: db_id → framework row
    fw_map = {fw["id"]: fw for fw in framework_rows}

    # Build ranked candidate list (preserve score ordering)
    ranked: list[tuple[float, dict]] = []
    for s in candidates[: settings.FRAMEWORK_TOP_K]:
        fw = fw_map.get(s["framework_db_id"])
        if fw:
            ranked.append((s["score"], fw))

    if not ranked:
        return None

    # If only one candidate or nothing meets reranker threshold, skip Haiku
    above_rerank = [fw for score, fw in ranked if score >= settings.FRAMEWORK_MIN_RERANK_THRESHOLD]

    if not above_rerank:
        # Best candidate doesn't meet min threshold for reranker
        return None

    if len(ranked) == 1:
        # Only one candidate — no need for Haiku
        return ranked[0][1]

    # Step 4 — Haiku reranker
    try:
        winner = await _haiku_rerank(
            query=query,
            candidates=[fw for _score, fw in ranked],
            agent_category=agent_category,
        )
        return winner
    except Exception:
        logger.exception("Haiku reranker failed for agent %s — using top-score fallback", agent_definition_id)
        # Fallback: return highest-scoring candidate
        return ranked[0][1]


def _score_frameworks(
    *,
    query_embedding: list[float],
    trigger_rows: list[dict],
    expertise_boost: float,
    boost_threshold: float,
) -> list[dict]:
    """Score each framework by aggregating trigger cosine similarities.

    For each framework:
      - base score = max cosine similarity across all its triggers
      - for each additional trigger above boost_threshold beyond the first,
        add expertise_boost to the score (up to the number of triggers - 1)

    Returns list of {"framework_db_id": str, "score": float}, sorted descending.
    """
    import numpy as np

    q_vec = np.array(query_embedding, dtype=float)
    q_norm = float(np.linalg.norm(q_vec))
    if q_norm == 0:
        q_norm = 1e-10

    # Group trigger rows by framework_db_id
    groups: dict[str, list[float]] = {}
    for row in trigger_rows:
        fid = row["framework_db_id"]
        emb = row.get("embedding")
        if not emb:
            continue
        try:
            t_vec = np.array(emb, dtype=float)
            t_norm = float(np.linalg.norm(t_vec))
            if t_norm == 0:
                continue
            sim = float(np.dot(q_vec, t_vec) / (q_norm * t_norm))
        except Exception:
            continue
        groups.setdefault(fid, []).append(sim)

    results: list[dict] = []
    for fid, sims in groups.items():
        sims_sorted = sorted(sims, reverse=True)
        base_score = sims_sorted[0]

        # Count additional triggers above boost_threshold (beyond the first)
        extra_matches = sum(1 for s in sims_sorted[1:] if s >= boost_threshold)
        score = base_score + extra_matches * expertise_boost

        results.append({"framework_db_id": fid, "score": score})

    return sorted(results, key=lambda x: x["score"], reverse=True)


async def _haiku_rerank(
    *,
    query: str,
    candidates: list[dict],
    agent_category: Optional[str],
) -> Optional[dict]:
    """Call Claude Haiku to select the most relevant framework.

    Uses the platform ANTHROPIC_API_KEY (not BYOK).
    Returns the winning framework dict, or None if Haiku's choice is unclear.
    """
    from app.config import get_settings
    from app.services.llm_client import complete

    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Haiku reranker, using top candidate")
        return candidates[0] if candidates else None

    # Build the reranker prompt
    candidate_lines: list[str] = []
    for fw in candidates:
        fid = fw.get("framework_id", fw.get("id", "unknown"))
        name = fw.get("name", "")
        description = fw.get("description", "")
        triggers = ", ".join(fw.get("when_to_apply", [])[:3])
        candidate_lines.append(f"  - {fid}: {name}. {description} (Triggers: {triggers})")

    category_hint = f" (Agent category: {agent_category})" if agent_category else ""
    prompt = (
        f"You are selecting the most relevant thinking framework for a user query{category_hint}.\n\n"
        f"User query: \"{query}\"\n\n"
        f"Candidate frameworks:\n" + "\n".join(candidate_lines) + "\n\n"
        "Which framework_id is most relevant to this query? "
        "Respond with ONLY the framework_id (kebab-case identifier), nothing else."
    )

    try:
        response = await complete(
            messages=[{"role": "user", "content": prompt}],
            model="claude-haiku-4-5-20251001",
            api_key=settings.ANTHROPIC_API_KEY,
            provider="anthropic",
            max_tokens=32,
        )
    except Exception:
        logger.exception("Haiku reranker API call failed")
        return candidates[0] if candidates else None

    chosen_id = (response or "").strip().strip('"').strip("'")
    if not chosen_id:
        return candidates[0] if candidates else None

    # Match to a candidate
    # Try exact framework_id match first, then name match, then db id
    for fw in candidates:
        if fw.get("framework_id") == chosen_id:
            return fw
    for fw in candidates:
        if fw.get("id") == chosen_id:
            return fw

    # Haiku returned something unrecognisable — fallback to top candidate
    logger.warning("Haiku returned unknown framework_id '%s', using top candidate", chosen_id)
    return candidates[0] if candidates else None
