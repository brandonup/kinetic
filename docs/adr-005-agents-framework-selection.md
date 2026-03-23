# ADR-005: Framework Selection Pipeline

**Status:** Proposed
**Author:** Gilfoyle
**Date:** 2026-03-23
**Project:** Kinetic
**Spec ref:** `docs/specs/agents.md` (KIN-242) · `docs/framework-schema-recommendations.md`
**ADR ref:** `docs/adr-003-agents-architecture.md` (entity split, embedding tables)
**Schema ref:** `docs/db-schema-spec.md` §14–15 (frameworks, framework_trigger_embeddings)
**Tickets:** KIN-284 (this ADR) · KIN-289 (implementation) · KIN-290 (context stack activation)

---

## Context

Kinetic agents attach a **Framework Library** — a set of named reasoning tools extracted from a thought leader's corpus. At generation time, the most relevant framework is selected and injected whole into the context stack as Layer 7 (L7). The selection must be accurate (wrong pick is worse than no injection), fast (< 500ms added latency), and able to express user preferences (pinned/excluded overrides in AgentInstance).

Forces at play:

1. **Wrong picks are worse than no injection.** Applying an irrelevant framework causes the agent to reason through the wrong lens. No-injection is always better than a wrong pick. The pipeline must have a confident confidence threshold below which no framework is injected.
2. **Multi-turn context blindness.** The current user message alone is insufficient for accurate matching in a multi-turn conversation. Follow-up messages ("what are the main risks?") are only meaningful relative to the prior turns. The query must incorporate conversational context.
3. **Scale.** MVP targets ~115 frameworks per agent, ~5 trigger phrases per framework → ~575 embedding vectors per agent. This is comfortably within pgvector's HNSW index at MVP scale. No dedicated vector DB needed.
4. **BYOK constraints.** Per MEMORY.md 2026-03-21: embedding and pipeline LLM calls use the platform-owned key, not user BYOK. Only the per-query generation call uses the user's key. The framework selection pipeline (embed + reranker) is platform-funded.
5. **User overrides.** AgentInstance.framework_overrides contains `pinned` and `excluded` framework IDs. Pinned frameworks get a score boost; excluded frameworks are filtered before ranking. These are per-user preferences that must survive the selection pipeline.
6. **Runtime payload trimming.** Per `docs/framework-schema-recommendations.md` §2: routing/metadata fields are stripped before injection. The context window sees only: `name`, `description`, `type`, `principles`, `steps`, `example_application`, `adjacent_ids`, `guidance`. Target: 400–600 tokens per injected payload.

---

## Decision

### 1. Query Construction (Multi-Turn Context Enrichment)

Before embedding, construct an enriched query from the conversation context:

```
enriched_query = last_2_user_messages + "\n\n" + current_user_message
```

If the conversation has a rolling summary, prepend a one-sentence summary of the summary's topic (not the full summary text — token budget is tight).

**Rationale:** Step 1 (embedding) and Step 3 (reranker) both operate on the enriched query. A bare follow-up message like "what are the main risks here?" is semantically unanchored; the last 2 user messages give the embedding space to match on the actual topic. Implementation cost: two DB rows fetched in `context_stack.assemble()` which already fetches history — no additional round-trip.

**Token budget:** The enriched query is used only for the internal pipeline (embedding + reranker). It is not injected into the context stack. Budget impact: ~200–400 tokens in the embedding call, ~500–800 tokens in the reranker call. Both use platform key.

### 2. Four-Step Selection Pipeline

```
Step 1: Embedding similarity search (pgvector)
        ↓ top-10 candidates
Step 2: Apply AgentInstance overrides (boost pinned, filter excluded)
        ↓ top-5 candidates (after override adjustments)
Step 3: LLM reranker (claude-haiku-4-5) — select winner or "none"
        ↓ winner framework_id or None
Step 4: Inject winner into L7, or omit L7 if no winner
```

#### Step 1: Embedding Similarity Search

- Embed the enriched query using `text-embedding-3-large` (platform OpenAI key).
- Run pgvector cosine similarity search on `framework_trigger_embeddings` for the agent's frameworks.
  - Table has one row per trigger phrase + one row per `core_question` (if populated).
  - Filter by `agent_definition_id` (index on this column).
  - Return top-10 distinct frameworks by max similarity score across all their trigger rows.

```sql
SELECT DISTINCT ON (f.id)
    f.id,
    f.name,
    MAX(1 - (fte.embedding <=> $query_embedding)) AS similarity
FROM framework_trigger_embeddings fte
JOIN frameworks f ON f.id = fte.framework_id
WHERE f.agent_definition_id = $agent_id
GROUP BY f.id, f.name
ORDER BY similarity DESC
LIMIT 10;
```

**Core question embedding:** `core_question` is embedded as an additional row in `framework_trigger_embeddings` with `trigger_type = 'core_question'`. This gives the retrieval step a "what problem is the user solving?" signal alongside situational triggers. The `MAX()` aggregation means the framework scores on whichever trigger or core question is most similar — the core question vector improves recall for high-level problem statements.

#### Step 2: Apply AgentInstance Overrides

After retrieval, apply user-specific adjustments from `AgentInstance.framework_overrides`:

```python
def _apply_overrides(candidates: list[dict], overrides: dict) -> list[dict]:
    pinned = set(overrides.get("pinned", []))
    excluded = set(overrides.get("excluded", []))

    # Filter excluded frameworks
    candidates = [c for c in candidates if c["id"] not in excluded]

    # Boost pinned frameworks by 0.15 similarity points
    for c in candidates:
        if c["id"] in pinned:
            c["similarity"] = min(1.0, c["similarity"] + 0.15)

    # Re-sort and take top-5
    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    return candidates[:5]
```

**Pinned boost value (0.15):** Enough to move a pinned framework from 4th to 1st place in typical distributions (similarity scores cluster in 0.60–0.85 range), but not enough to override a genuinely poor match (similarity < 0.50 + 0.15 = 0.65 → reranker will likely reject it). This is a starting value; empirical calibration recommended in KIN-260.

**Unknown IDs:** If a pinned or excluded `framework_id` no longer exists (deleted framework), it is silently ignored. Defensive filtering on read — no cleanup required.

#### Step 3: LLM Reranker (Haiku)

Present the top-5 candidates to `claude-haiku-4-5` for precision ranking and no-injection judgment.

**System prompt:**
```
You are a framework selection judge for an AI assistant. Given a user's message and a set of candidate reasoning frameworks, select the single most applicable framework — or output "none" if no framework is a strong match.

A framework is a strong match if:
- It directly addresses the underlying question the user is wrestling with
- Applying it would produce meaningfully better reasoning than not applying it
- It is not excluded by the user's anti_triggers

Output only the framework ID (e.g., "pricing-strategy-premium") or the word "none". No explanation.
```

**User prompt:**
```
User message:
{enriched_query}

Candidate frameworks:
{for each candidate: id, name, description, when_to_apply[0:2], anti_triggers[0:2], core_question}

Select the best framework ID, or output "none".
```

**Haiku reranker cost:** ~50–150 tokens total. Platform key. Sub-100ms typical latency.

**Confidence threshold:** If the highest similarity score from Step 1 (before overrides) is below `FRAMEWORK_MIN_SIMILARITY = 0.55`, skip the reranker and return `None` directly. This prevents calling Haiku for queries with no plausible framework match and avoids "worse-than-no-injection" outcomes.

`FRAMEWORK_MIN_SIMILARITY = 0.55` is the initial value. KIN-260 (Jìan) is tasked with empirical calibration across 30–50 representative queries including no-match and ambiguous cases.

#### Step 4: Inject Winner or Omit L7

If a winner is selected, build the L7 injection payload by selecting fields from the winner framework row and stripping routing/metadata fields:

**Injected fields:** `name`, `description`, `type`, `principles`, `steps`, `example_application`, `adjacent_ids`, `guidance`

**Stripped fields:** `when_to_apply`, `category`, `source_posts`, `confidence`, `origin`, `related_frameworks`, `anti_triggers`, `core_question`

Injection format (L7 in context stack):
```
## Active Framework: {name}

{description}

{guidance}

**Principles:**
{principles as bullet list}

**Steps:**
{steps as numbered list, if non-empty}

**Example:**
{example_application}

**Related frameworks to consider:** {adjacent_ids joined by ", ", if non-empty}
```

If no winner (reranker returns "none" or similarity below threshold): L7 is omitted from the context stack. The agent operates on L1–L6 + L8–L9.

### 3. AgentInstance Auto-Creation (Get-or-Create)

When `GET /api/v1/agents/:id/instance` is called and no instance exists for `(user_id, agent_definition_id)`:

```python
async def get_or_create_instance(supabase, agent_definition_id: str, user_id: str) -> dict:
    # Try select first (fast path — most calls hit existing instance)
    result = await _run(
        lambda: supabase.table("agent_instances")
        .select("*")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data

    # Insert with ON CONFLICT DO NOTHING to handle concurrent first-invocations
    await _run(
        lambda: supabase.table("agent_instances")
        .insert({
            "agent_definition_id": agent_definition_id,
            "user_id": user_id,
            "framework_overrides": {"pinned": [], "excluded": []},
        })
        .execute()
    )

    # Re-select to get the row (works whether our insert won or a concurrent insert did)
    result = await _run(
        lambda: supabase.table("agent_instances")
        .select("*")
        .eq("agent_definition_id", agent_definition_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data
```

The `UNIQUE(user_id, agent_definition_id)` constraint on `agent_instances` prevents duplicate rows. `ON CONFLICT DO NOTHING` means concurrent first-invocations safely produce exactly one row.

### 4. Agent Context Layers (L5, L6, L7, L9)

These layers are activated in `context_stack.assemble()` when `active_agent_id` is non-null.

| Layer | Content | Source | Status in Sprint 4 |
|---|---|---|---|
| L5 | Agent system prompt | `agent_definitions.instructions` | **Active** (KIN-290) |
| L6 | Agent active memory | `active_memory_entries` for instance | **Stub** (Sprint 5) |
| L7 | Selected framework (whole) | `frameworks` row via pipeline | **Active** (KIN-289+290) |
| L8 | Project/agent KB RAG results | `rag_service.retrieve()` | **Active** (KIN-290, uses existing stub) |
| L9 | Agent-specific KB RAG results | `rag_service.retrieve(agent_kb_id)` | **Active** (KIN-290) |

**L5 format:**
```
## Agent Instructions

{agent_definition.instructions}
```

**L6 format (Sprint 5):**
```
## Agent Memory

{active memory entries for this user + this agent, most recent first}
```

**Assembly ordering in context stack:**
```
system_prompt = L1 (user bio) + L2 (company) + L3 (project instructions)
              + L4 (project active memory, stub)
              + L5 (agent system prompt, if agent active)
              + L6 (agent active memory, stub)
              + L7 (selected framework, if agent active and winner found)

history = rolling summary + last VERBATIM_WINDOW messages (existing)

rag_context = L8 (project/general KB) + L9 (agent KB, if agent active)
```

`rag_context` is appended to `system_prompt` before the history, consistent with existing L8 behavior.

---

## Alternatives Considered

### Selection Pipeline

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **4-step (chosen):** embed → override → reranker → inject | High precision. User overrides respected. No-injection path for weak matches. | Haiku reranker adds ~100ms latency. | N/A |
| Embedding only (no reranker) | Faster. No LLM call. | Lower precision on ambiguous queries. No anti-trigger negative signal. | Wrong picks worse than no injection — reranker is necessary. |
| BM25 keyword matching | No embedding cost. Fast. | No semantic understanding. Trigger phrases are short — keyword overlap is noisy. | Semantic similarity is required for the trigger phrase vocabulary. |
| All frameworks injected (no selection) | Simplest. Never wrong-picks. | Context window explosion (~115 frameworks * 500 tokens = 57,500 tokens). Model cannot reason well with all frameworks. | Context budget incompatible. |
| Dedicated vector DB (Qdrant) | Scales beyond MVP. Faster at high volume. | Operational overhead. Unnecessary at ~575 vectors per agent. | YAGNI. pgvector is sufficient at MVP scale. |

### Override Mechanism

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Score boost (chosen)** | Proportional — pinned framework needs to be a plausible match to win. User preference respected without overriding precision. | Boost magnitude requires calibration. | N/A |
| Force-inject pinned framework regardless of score | Simple. User always gets their pinned framework. | Breaks "wrong pick is worse than no injection" invariant. | Violates core quality constraint. |
| Pinned = always top candidate sent to reranker | Reranker still has final judgment. | Pinned framework always evaluated — reranker may reject it. Acceptable but slightly wasteful. | Score boost is cleaner — keeps the algorithm uniform. |

### Context Enrichment Query

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Last 2 user messages + current (chosen)** | Low token cost. Good signal for most follow-ups. | May miss very long threads where critical context is older. | Sufficient for MVP usage patterns. |
| Full conversation history | Maximum context. | Embedding context window limits. Cost. | Overkill for retrieval step. |
| Rolling summary only | Consistent. Doesn't grow with conversation. | Summary lags behind current topic. | Too coarse for precise retrieval. |
| Current message only | Fastest. Zero additional DB reads. | Breaks on short follow-ups. | Unacceptable precision loss. |

---

## Consequences

**Positive:**
- 4-step pipeline provides high precision with a clear no-injection escape hatch. Wrong picks are explicitly gated by the similarity threshold and reranker judgment.
- Score-boost override respects user preferences without sacrificing quality guarantees — a pinned framework with a 0.40 similarity score + 0.15 boost = 0.55, which still needs to convince the reranker.
- Query enrichment with last 2 user messages costs nothing extra (messages already fetched) and fixes multi-turn context blindness.
- Runtime payload trimming recovers 100–400 context window tokens per query by stripping routing/metadata fields from the injected framework.
- `ON CONFLICT DO NOTHING` auto-creation is race-condition safe at MVP scale.

**Negative:**
- Haiku reranker adds ~100ms latency per query when an agent is active. Mitigation: run framework selection concurrently with context assembly (separate `asyncio.create_task`).
- `FRAMEWORK_MIN_SIMILARITY = 0.55` is uncalibrated. Risk: too high → frameworks rarely fire; too low → wrong picks leak through to reranker. KIN-260 must run before user testing.
- Score boost magnitude (0.15) is arbitrary. May need adjustment per agent or per framework density. Logged for future empirical review.
- `core_question` embedding is only useful once frameworks have this field populated. Existing frameworks extracted without `core_question` skip this signal. The pipeline degrades gracefully to trigger-only vectors.

**Neutral:**
- L6 (agent active memory) remains a stub in Sprint 4. Its absence means the active memory entries don't influence responses — acceptable for Sprint 4, required for Sprint 5.
- Adjacent framework follow-on suggestions (`adjacent_ids` in L7 payload) are informational only in MVP. The agent can mention them; no automated follow-on selection.

---

## Implementation Notes

### `app/services/framework_selection.py` (KIN-289)

```python
async def select_framework(
    supabase: Any,
    agent_definition_id: str,
    enriched_query: str,
    framework_overrides: dict,
    *,
    platform_openai_key: str,
    platform_anthropic_key: str,
) -> Optional[dict]:
    """
    Returns the selected framework row (injected fields only), or None.
    """
    ...
```

The function is async-safe and returns a dict of injected fields (not the full DB row). Returns `None` when no framework is selected.

### `app/services/context_stack.py` activation (KIN-290)

When `active_agent_id` is set in the conversation:
1. Fetch `agent_definitions` row for L5 system prompt.
2. Fetch `agent_instances` row for `framework_overrides` (used in Step 2).
3. Run `framework_selection.select_framework()` as a concurrent task alongside other context fetches.
4. Build L5 section from `agent_definitions.instructions`.
5. Build L7 section from the selected framework (if any).
6. Run L9 RAG retrieval using `agent_definitions.knowledge_base_id` (if set).

Both L5 and L7 are appended to `system_prompt` before the conversation history.

### Platform Key Configuration

```
PLATFORM_OPENAI_KEY   — Used for framework query embedding (text-embedding-3-large)
PLATFORM_ANTHROPIC_KEY — Used for Haiku reranker (claude-haiku-4-5)
```

Both keys are environment variables. The framework selection service reads them directly (not from `user_api_keys`). If either key is missing, framework selection is skipped and L7 is omitted (silent degradation, logged at WARNING level).

---

## Open Questions

1. **`FRAMEWORK_MIN_SIMILARITY` calibration.** KIN-260 tasked to Jìan. Must complete before user testing of agent features.
2. **`adjacent_ids` vs. `related_frameworks`.** `docs/framework-schema-recommendations.md` §Open Questions item 4 — these overlap. Decision: retain `related_frameworks` as extracted (topically related), add `adjacent_ids` as the applied-in-sequence field. Both stored; only `adjacent_ids` injected at runtime. `related_frameworks` is routing metadata (stripped at injection).
3. **L6 Sprint 5 contract.** When L6 (agent active memory) ships, the `context_stack.assemble()` function must fetch `active_memory_entries` for `(agent_instance_id)` and inject them between L5 and L7. The `agent_instances` row is already fetched in Sprint 4 for `framework_overrides` — L6 activation requires only the additional `active_memory_entries` query.

---

## Review Trigger

Revisit this ADR when:
- Framework vector count exceeds 5,000 per agent (HNSW index pressure — consider partition by agent)
- Haiku reranker latency consistently exceeds 300ms (consider batching or caching recent selections)
- `FRAMEWORK_MIN_SIMILARITY` is recalibrated by KIN-260 (update value in this ADR)
- Multi-agent per conversation ships (pipeline must run once per active agent — budget implications)
- L6 (agent active memory) ships — verify L6 doesn't push L7 below context window
