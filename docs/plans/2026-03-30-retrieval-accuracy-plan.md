# Retrieval Accuracy Improvement Plan

**Status:** Draft (Gilfoyle-reviewed, issues addressed)
**Author:** Jared (product)
**Reviewer:** Gilfoyle
**Date:** 2026-03-30

---

## The Problem

A user query about "AI adoption resistance in their team" matched the "Three-Layer Enterprise Context Taxonomy" framework — about enterprise data sharing strategy. Wrong intent, plausible topical overlap. Cosine similarity alone can't tell the difference between "these topics are in the same neighborhood" and "this framework actually answers this question."

This affects both:
- **L7 (Framework Selection):** Which framework gets injected into the conversation
- **L8/L9 (KB Retrieval):** Which document chunks get injected as RAG context

---

## Two-System Sync Requirements

Both the Python web app (`packages/api/`) and the TypeScript MCP server (`kinetic-brain/supabase/functions/kinetic-mcp/tools.ts`) implement framework selection and KB retrieval independently. They share the same Supabase RPCs but have separate threshold constants and pipeline logic. **Every change in this plan must be applied to both.**

**Shared constants that must stay in sync:**

| Constant | Python location | TS location | Current value |
|----------|----------------|-------------|---------------|
| Framework similarity threshold | `framework_selection.py` `FRAMEWORK_MIN_SIMILARITY` | `tools.ts` `CONFIDENCE_GATE` | 0.55 |
| Framework trigger top-K | `framework_selection.py` `FRAMEWORK_TRIGGER_TOP_K` | `tools.ts` `match_count` param | 20 |
| Multi-trigger boost | `framework_selection.py` `MULTI_TRIGGER_BOOST` | `tools.ts` `MULTI_TRIGGER_BOOST` | 0.05 |
| KB similarity threshold | `retrieval.py` `SIMILARITY_THRESHOLD` | `tools.ts` `KB_SIMILARITY_THRESHOLD` | 0.3 |
| KB candidate count | `retrieval.py` `VECTOR_TOP_K` | `tools.ts` `KB_MATCH_COUNT` | 20 |
| KB final count | `retrieval.py` `MMR_TOP_K` | `tools.ts` `KB_TOP_K` | 8 |

**Known divergence:** The TS MCP server does NOT implement MMR for KB retrieval — it takes top-K by raw similarity. The Python pipeline has full MMR (λ=0.6). This means KB Lever 2 (MMR Lambda Tuning) is Python-only. Flagging as a pre-existing gap; not blocking for this plan but should be addressed separately.

**Known divergence:** Python caps framework candidates to `FRAMEWORK_TOP_K = 5` before the confidence gate. TS has no equivalent cap. Both select top-1, so this only matters if a future reranker operates on top-N.

**Per-lever sync requirements are noted inline below.**

---

## Part 1: Evaluation Design (Do This First)

### 1.1 What We Have Now

**Existing eval plans (not yet executed):**
- `docs/evals/2026-03-24-kin340-framework-selection-eval.md` — 15 on-topic + 5 off-topic queries, precision/recall targets of 80%
- `docs/evals/2026-03-24-kin348-rag-retrieval-eval.md` — MMR, threshold, citation, and budget tests
- `docs/framework-eval-plan.md` — Monica's 4-test plan (originality, application quality, no-harm, separation)

**Existing data in the database:**
- 184 curated frameworks with `when_to_apply` trigger phrases (3–5 each)
- Framework trigger embeddings (if backfill has been run)
- KB documents and chunks with embeddings
- Conversation history in `messages` table (prior user queries with matched agents)

**Unit tests (mocked):**
- `test_framework_selection.py` — verifies boost logic, thresholds, fail-open
- `test_rag_retrieval.py` — verifies MMR, thresholds, budget, citations

**What's missing:** Live evaluation against real embeddings. Every existing eval is either mocked or unexecuted.

### 1.2 Eval Dataset Design

#### Framework Selection (L7) — Eval Dataset

**Format:** Each row is a (query, expected_framework_id, label) triple.

```
| query                                          | expected         | label     |
|------------------------------------------------|------------------|-----------|
| "My team is resisting AI tools, how do I..."   | adoption-readiness| on-topic  |
| "What's the weather tomorrow?"                 | null              | off-topic |
| "Should I hire a CTO or outsource dev?"        | build-vs-buy      | on-topic  |
```

**Labels:**
- `on-topic` — query should match the expected framework
- `off-topic` — query should match nothing (null)
- `adjacent` — query is topically close to a framework but doesn't warrant it (the "AI adoption resistance → Enterprise Context Taxonomy" case). These are the hardest and most valuable test cases.

**How to generate it without massive manual effort:**

1. **Mine trigger phrases directly (30 min, ~100 cases).** For each of the 184 frameworks, take each `when_to_apply` trigger and rephrase it as a natural user question. This is mechanical — the trigger "When a team is resistant to new technology" becomes "My team is pushing back on adopting new AI tools, what should I do?" Add the framework_id as the expected match. ~550 trigger phrases → sample 100, write natural question variants.

2. **Mine the `adjacent` failure mode (1 hr, ~30 cases).** Take the top 10 frameworks by category overlap (e.g., 43 frameworks in `ai-adoption`, 39 in `problem-diagnosis`). For each category, write 3 queries that are topically adjacent but should NOT match that specific framework. These are the cases that expose the cosine-similarity-alone problem.

3. **Mine existing conversations (30 min, ~20 cases).** Query the `messages` table for user messages where an agent was active and a framework was injected (check `debug_prompt` on assistant messages). For each, manually label: was the selected framework correct? This gives real-world signal on current performance.

4. **Generate off-topic queries (15 min, ~20 cases).** Simple: "What time zone is Tokyo in?", "Summarize this article for me", etc. These should all return null.

**Target dataset size:** ~170 cases (100 on-topic, 30 adjacent, 20 mined, 20 off-topic). Enough for statistical significance without being a research project.

#### KB Retrieval (L8/L9) — Eval Dataset

**Format:** Each row is a (query, expected_doc_ids, expected_absent_doc_ids) triple.

```
| query                                    | should_retrieve         | should_not_retrieve     |
|------------------------------------------|-------------------------|-------------------------|
| "How should I price my AI SaaS?"         | [pricing-post, ...]     | [hiring-post, ...]      |
| "What's the best model for embeddings?"  | [embeddings-post, ...]  | [leadership-post, ...]  |
```

**How to generate it:**

1. **Mine KB documents directly (30 min, ~50 cases).** For each document in the KB, read the title and first chunk. Write 2–3 natural queries that should retrieve it. Also note 1–2 documents that are topically adjacent but should NOT be retrieved.

2. **Mine the adjacent failure mode (30 min, ~20 cases).** Similar to frameworks: queries where topic proximity misleads embedding similarity.

3. **Off-topic baseline (15 min, ~10 cases).** Queries completely outside the KB's domain. Should return empty or below threshold.

**Target dataset size:** ~80 cases. KB retrieval is more standard RAG — the framework selection pipeline is where most novelty (and most risk) lives.

### 1.3 Metrics

#### Framework Selection (L7)

| Metric | Definition | Target | Why |
|--------|-----------|--------|-----|
| **Precision@1** | % of on-topic queries where the top-1 match is correct | ≥ 80% | The system only injects one framework — if it's wrong, it's worse than nothing |
| **False positive rate** | % of off-topic + adjacent queries that match any framework | ≤ 10% | The "Enterprise Context Taxonomy" problem — matching when it shouldn't |
| **Adjacent rejection rate** | % of adjacent queries correctly returning null | ≥ 70% (Phase 1–3), ≥ 90% (long-term with reranker) | Hardest metric — measures intent discrimination. Embedding-only approaches may plateau at 70–80%; 90% likely requires an LLM reranker (Phase 4 decision gate) |
| **MRR (Mean Reciprocal Rank)** | 1/rank of correct framework in top-5 candidates | ≥ 0.7 | Useful if we later allow top-3 selection or reranking |

**Ground truth format:** `(query, expected_framework_id | null, label)`

**Why Precision@1 over Recall:** Kinetic injects exactly one framework. A false positive (wrong framework injected) is actively harmful — it forces the model into the wrong diagnostic lens. A false negative (no framework when one exists) is merely neutral — the model reasons without a framework. Precision matters more than recall pre-launch.

#### KB Retrieval (L8/L9)

| Metric | Definition | Target | Why |
|--------|-----------|--------|-----|
| **Precision@8** | % of 8 retrieved chunks from relevant documents | ≥ 70% | 8 chunks is the budget; irrelevant chunks waste tokens and confuse the model |
| **Recall@20** | % of relevant documents with at least one chunk in top-20 candidates (pre-MMR) | ≥ 80% | Measures whether the vector search finds the right documents before MMR diversifies |
| **MRR** | 1/rank of first relevant chunk | ≥ 0.6 | First chunk should be relevant — it has the most influence on generation |
| **False injection rate** | % of retrieved chunks from irrelevant documents | ≤ 15% | Noise in context degrades generation quality |

**Ground truth format:** `(query, [relevant_doc_ids], [irrelevant_doc_ids])`

### 1.4 Minimum Viable Eval (Run Now)

**What we can do today with what we have:**

**Step 1: Framework selection spot-check (2 hours).**

Write a script that:
1. Takes 20 hand-written queries (10 on-topic, 5 adjacent, 5 off-topic)
2. Calls `select_framework()` with each query against Nate's agent
3. Records the top-1 match, similarity score, and trigger text
4. Outputs a table: query | matched_framework | score | trigger_text | expected | correct?

This gives an immediate signal on current precision. Monica's finding that only 1/7 representative queries produced a correct #1 match suggests we'll see problems fast.

**Step 2: KB retrieval spot-check (1 hour).**

Same pattern: 10 queries, record top-8 chunks, manually label relevance. Faster because we're just checking document relevance, not exact chunk matching.

**Step 3: Similarity distribution analysis (30 min).**

Query the database for all trigger embeddings, compute pairwise similarities across frameworks. This reveals the "topical neighborhood" problem: if many frameworks cluster at 0.50–0.65 similarity, the 0.55 threshold is too close to the noise floor.

**Total baseline effort: ~4 hours for a meaningful signal.**

### 1.5 Mining Existing Data

**Conversations table:** Query `messages` where `role = 'assistant'` and `debug_prompt IS NOT NULL` to find conversations where the generation engine ran with full context assembly. The `debug_prompt` field is a **raw text blob** (the full assembled prompt sent to the LLM), not structured data. Extracting framework names and KB chunk IDs requires manual reading or regex parsing of the prompt text — look for the "Framework:" header from L7 injection and source document titles from L8/L9 injection. This is approximate, not an automated pipeline. Cross-reference with the user's query (`role = 'user'` message preceding it) to build (query, selected_framework, selected_chunks) triples. These are **unlabeled** — they show what the system chose, not whether it was correct — but they're a free dataset for error analysis.

**Framework trigger embeddings table:** Query all `framework_trigger_embeddings` rows for Nate's agent. Compute pairwise cosine similarity between all trigger embeddings. This reveals which frameworks are dangerously close in embedding space and which triggers are semantically redundant. Output: a confusion matrix of frameworks by trigger proximity.

---

## Part 2: Improvement Levers (After Baseline)

### 2.1 Framework Selection (L7)

Listed in order of implementation priority — quick wins first.

#### Lever 1: Threshold Tuning (Quick Win)

**What:** Adjust `FRAMEWORK_MIN_SIMILARITY` from 0.55 based on empirical distribution.

**Why it helps:** If the similarity distribution analysis shows that most correct matches score > 0.65 and most false positives score 0.55–0.65, raising the threshold to 0.65 eliminates the noise floor with minimal recall loss.

**Tradeoffs:**
- Accuracy: High impact if threshold is currently in the noise zone
- Latency: Zero — threshold is applied in Python post-RPC
- Cost: Zero — no additional API calls
- Complexity: One-line change + eval validation

**Risk:** If the correct matches and false positives overlap heavily in similarity score, threshold tuning alone won't fix the problem. The baseline eval will reveal this.

#### Lever 2: Trigger Phrase Quality (Quick Win)

**What:** Rewrite trigger phrases from author vocabulary to user vocabulary. Monica flagged this as the #1 issue (KIN-351): triggers use Nate's framework language, not how a user would phrase the question.

**Example:**
- Current trigger: "Three-Layer Enterprise Context Taxonomy application"
- User query: "My team is resisting AI tools"
- Better trigger: "When a team pushes back on adopting new technology"

**Tradeoffs:**
- Accuracy: High impact — better triggers mean the embedding is closer to user queries
- Latency: Zero at query time — triggers are embedded at write time
- Cost: One-time re-embedding cost (~$0.001 for all triggers)
- Complexity: Manual effort to rewrite 184 × 3–5 triggers. Can be LLM-assisted: prompt GPT-4 to rephrase each trigger as a natural user question.

**Risk:** Still relies on cosine similarity alone. Better triggers improve the signal but don't solve the discrimination problem structurally.

#### Lever 3: Negative Triggers / Do-Not-Match Filtering (Medium Effort)

**What:** The `do_not_use_when` field already exists on the `frameworks` table but isn't used in the selection pipeline. Embed these negative triggers. At selection time, if the query is more similar to a negative trigger than any positive trigger, reject the match.

**Implementation scope (Gilfoyle review):**
- **Schema change:** Add `trigger_type text NOT NULL DEFAULT 'positive'` column to `framework_trigger_embeddings`. Values: `'positive'` (from `when_to_apply`) or `'negative'` (from `do_not_use_when`).
- **RPC change:** `match_framework_triggers` needs to either return `trigger_type` so the Python/TS pipeline can filter, or split into two RPCs. Returning `trigger_type` is simpler.
- **ADR-007 amendment:** The write-time embedding pipeline (background job + admin backfill) must also embed `do_not_use_when` phrases with `trigger_type = 'negative'`.
- **Python pipeline change:** After grouping by framework, compute max negative similarity. If max_negative > max_positive for a framework, reject it.
- **TS pipeline change:** Same logic in `tools.ts` `selectFramework()`.
- **Sync:** Both systems share the RPC, so schema/RPC changes propagate. Pipeline logic must be implemented in both.

**Tradeoffs:**
- Accuracy: Targeted fix for the "adjacent topic" failure mode
- Latency: +1 vector comparison per candidate (negligible)
- Cost: One-time embedding of negative triggers
- Complexity: Moderate — schema migration, RPC change, ADR amendment, both pipeline updates, eval validation

**Risk:** Only works if someone writes good negative triggers. The "Enterprise Context Taxonomy" misfire would need a negative trigger like "team dynamics," "change management," or "adoption resistance." Requires the same user-vocabulary rewriting as positive triggers.

#### Lever 4: LLM Reranker (Structural Change)

**What:** After the vector pipeline returns top-5 candidates, call a lightweight LLM (e.g., GPT-4o-mini) to score each candidate's relevance to the actual query. The reranker sees the query text, the framework name/description, and the matched trigger — and returns a 1–5 relevance score.

**The reranker prompt:**
```
Given this user query: "{query}"
And this candidate framework:
  Name: {name}
  Description: {description}
  Matched trigger: {trigger}

Rate 1-5 how well this framework would help answer the query.
5 = directly applicable, 1 = wrong topic.
Return only the number.
```

**Tradeoffs:**
- Accuracy: Highest impact lever. An LLM can discriminate intent vs. topic proximity in a way cosine similarity fundamentally cannot.
- Latency: +300–500ms per query (one LLM call with 5 candidates)
- Cost: **User's BYOK key** — each query adds ~800–1500 input tokens (prompt template + 5 candidates × ~100–250 tokens each for name/description/trigger). At GPT-4o-mini pricing (~$0.15/M input tokens), this is ~$0.0001–0.0002 per query. Negligible per-query, but it's a new cost category users don't currently have.
- Complexity: **Python: moderate** — `framework_selection.py` already has a commented-out reranker step placeholder at Step 3 ("skip Haiku reranker for MVP"). The insertion point exists. **TS: high** — `tools.ts` has no reranker hook; net-new implementation.

**Risk:** Adds a dependency on LLM availability at query time. If the user's BYOK key is rate-limited, the reranker fails. Needs fail-open behavior (fall back to cosine-only).

**Recommendation:** Defer until after Levers 1–3 are measured. If threshold tuning + trigger quality + negative triggers get precision@1 above 80%, the reranker's cost/complexity isn't justified pre-launch.

#### Lever 5: Query Expansion (Structural Change)

**What:** Before embedding the user's query, use an LLM to expand or rephrase it to capture intent more precisely. Example: "My team is resisting AI tools" → expanded to "team resistance to AI adoption, change management, overcoming organizational inertia around technology."

**Tradeoffs:**
- Accuracy: Moderate — helps when user queries are terse or use different vocabulary than triggers
- Latency: +200–400ms (LLM call before embedding)
- Cost: User's BYOK key — ~100 tokens per query expansion
- Complexity: Moderate — new step in pipeline, need to handle expansion failures

**Recommendation:** Defer. Trigger quality improvements (Lever 2) solve the vocabulary gap from the other direction, without adding query-time cost.

#### Lever 6: Hybrid Search (Structural Change)

**What:** Combine cosine similarity with BM25 keyword matching. Supabase supports `tsvector` for full-text search natively. Score = α × cosine_sim + (1-α) × bm25_score.

**Tradeoffs:**
- Accuracy: Helps when the user's exact words appear in triggers (keyword match catches what embedding misses)
- Latency: Minimal — both searches run in Postgres
- Cost: Zero (no LLM calls)
- Complexity: Moderate — requires `tsvector` index on trigger phrases, new RPC function, score normalization

**Recommendation:** Viable post-launch. Less impactful than trigger quality + reranker for the intent discrimination problem specifically. BM25 excels at exact-match scenarios, not the "topically adjacent but wrong intent" problem.

### 2.2 KB Retrieval (L8/L9)

The KB pipeline is more mature (has MMR for diversity), so the levers are more targeted.

#### Lever 1: Threshold Tuning (Quick Win)

**What:** Current `SIMILARITY_THRESHOLD = 0.3` is very permissive. Evaluate whether raising to 0.4 or 0.45 eliminates low-quality chunks without losing recall.

**Tradeoffs:** Same as framework threshold tuning — zero cost, one-line change, needs eval validation.

#### Lever 2: MMR Lambda Tuning (Quick Win)

**What:** Current `MMR_LAMBDA = 0.6` balances relevance (60%) vs. diversity (40%). If we're injecting irrelevant chunks, raising lambda to 0.7 or 0.8 weights relevance more heavily.

**Tradeoffs:**
- Higher lambda → more relevant but potentially redundant chunks
- Lower lambda → more diverse but potentially less relevant
- Needs eval to find the right balance for Nate's KB

#### Lever 3: Chunk Quality / Chunking Strategy (Medium Effort)

**What:** Review how documents are chunked. If chunks are too small, they lose context and embed poorly. If too large, they embed too broadly (the same problem as frameworks). Optimal chunk size for `text-embedding-3-large` is typically 200–500 tokens with overlap.

**Tradeoffs:**
- Accuracy: Can significantly improve retrieval if current chunking is suboptimal
- Latency: Zero at query time (chunking is write-time)
- Cost: One-time re-chunking and re-embedding
- Complexity: Moderate — requires analysis of current chunk size distribution, then re-ingestion

#### Lever 4: LLM Reranker (Structural Change)

**What:** Same concept as framework reranker — after MMR returns 8 chunks, call an LLM to score relevance and drop irrelevant chunks.

**Tradeoffs:** Same as framework reranker. Adds latency and cost. More impactful for KB than frameworks because 8 chunks have more surface area for noise than 1 framework.

**Recommendation:** Defer until after quick wins are measured.

#### Lever 5: Metadata Filtering (Medium Effort)

**What:** Use document metadata (tags, folder, type) as a pre-filter before vector search. If the user's question is about "pricing," filter to documents tagged with pricing/business before running similarity.

**Tradeoffs:**
- Accuracy: Eliminates topically distant documents before embedding comparison
- Latency: Faster — smaller candidate pool for vector search
- Cost: Zero
- Complexity: Requires reliable document tagging. Kinetic has tags from ingestion (KIN-336 AI tags) — need to verify quality.

---

## Part 3: Sequencing

### Phase 1: Baseline (Week 1) — 4 hours

1. Run the minimum viable eval (§1.4): 20 framework queries, 10 KB queries
2. Run the similarity distribution analysis on trigger embeddings
3. Mine existing conversations for unlabeled (query, selection) pairs
4. **Deliverable:** Baseline precision@1 number + similarity distribution chart + identified failure modes

### Phase 2: Quick Wins (Week 1–2) — 1–2 days

Based on baseline results:

5. Tune `FRAMEWORK_MIN_SIMILARITY` threshold (if distribution supports it)
6. Tune `SIMILARITY_THRESHOLD` for KB (same analysis)
7. Rewrite 20 highest-usage framework triggers to user vocabulary (pilot)
8. Re-run eval on pilot set, measure delta
9. **Decision gate:** If pilot trigger rewrite improves precision@1 by ≥ 15 points, commit to rewriting all 184

### Phase 3: Targeted Fixes (Week 2–3) — 2–3 days

10. Complete trigger phrase rewriting for all 184 frameworks (LLM-assisted)
11. Populate `do_not_use_when` negative triggers for top 20 most-confused frameworks
12. Wire negative triggers into the selection pipeline
13. Tune MMR lambda for KB based on eval
14. **Deliverable:** Full eval dataset (§1.2) constructed and all metrics measured

### Phase 4: Structural Changes (Post-Launch, If Needed)

15. LLM reranker — only if Phase 2–3 doesn't hit 80% precision@1
16. Hybrid search — only if keyword matching gaps are identified in eval
17. Query expansion — only if user vocabulary gap persists after trigger rewriting

---

## Constraints Acknowledged

- **BYOK cost:** Any lever that adds LLM calls at query time (reranker, query expansion) costs the user, not us. Quick wins (threshold tuning, trigger quality, negative triggers) are all zero-cost to the user.
- **Embedding model:** Both systems use `text-embedding-3-large` (3072-dim). Changing models would require re-embedding all triggers and chunks — not recommended pre-launch.
- **Pre-launch bias:** Favor correctness over complexity. Phases 1–3 use no new infrastructure. Phase 4 is a post-launch backlog.

---

## Part 4: Framework Selection Evaluation Plan

> **Context:** We're improving framework selection accuracy (Levers 1–3 above). Before and after those changes ship, we need to measure whether retrieval actually got better. This section is the eval plan for L7 specifically.
>
> **Skill dependency:** All tickets that implement eval work must include this instruction:
> ```
> Before starting implementation, invoke the /llm-evaluation skill for eval patterns,
> metrics implementation, and LLM-as-judge templates.
> ```

### 4.1 Ground Truth Dataset

**Format:** JSON lines, one case per line.

```jsonl
{"query": "My team is resisting AI tools, how do I get buy-in?", "expected": "adoption-readiness-assessment", "label": "on-topic"}
{"query": "What's the weather in Tokyo?", "expected": null, "label": "off-topic"}
{"query": "How should I structure my data team?", "expected": null, "label": "adjacent", "adjacent_to": "three-layer-enterprise-context-taxonomy"}
```

**Fields:**
- `query` — natural language user question
- `expected` — `framework_id` (kebab-case semantic ID from the `frameworks` table) or `null` for no-match cases
- `label` — `on-topic` | `off-topic` | `adjacent`
- `adjacent_to` (optional) — for adjacent cases, which framework the query is topically near but should NOT match. This is the diagnostic field — it tells us which frameworks have the worst false positive rates.

**How to generate without massive manual effort:**

**Method 1: LLM-assisted synthetic generation from triggers (~2 hours, ~150 cases).**

For each framework, feed the `when_to_apply` triggers to an LLM with this prompt:

```
You are generating evaluation data for a retrieval system.

Framework: {name}
Description: {description}
Trigger phrases: {when_to_apply}

Generate:
1. Two natural user questions that this framework SHOULD match.
   Write them as a real person would ask — not as a keyword search,
   not repeating the trigger language. Vary vocabulary and specificity.

2. One natural user question that is TOPICALLY ADJACENT but this
   framework should NOT match. The question should be in the same
   domain but require different diagnostic reasoning.

Format as JSON:
{"on_topic": ["q1", "q2"], "adjacent": "q3"}
```

Run this for a sample of 50 frameworks (from the top categories: ai-adoption, problem-diagnosis, competitive-positioning). Yields ~100 on-topic + ~50 adjacent cases. Add 20 hand-written off-topic queries. **Total: ~170 cases.**

**Cost:** ~50 LLM calls × ~300 input tokens = ~15K tokens. At GPT-4o-mini pricing: ~$0.002. Negligible.

**Method 2: Mining existing framework matches from the database (~30 min, ~20 cases).**

```sql
-- Find conversations where a framework was likely injected
-- (debug_prompt contains "Framework:" header from L7 assembly)
SELECT m_user.content AS user_query,
       m_asst.debug_prompt
FROM messages m_user
JOIN messages m_asst ON m_asst.conversation_id = m_user.conversation_id
  AND m_asst.role = 'assistant'
  AND m_asst.debug_prompt IS NOT NULL
WHERE m_user.role = 'user'
ORDER BY m_user.created_at DESC
LIMIT 50;
```

Manually scan `debug_prompt` for the "Framework:" header text. Extract the framework name. Label each (query, framework) pair as correct or incorrect. These are the highest-value eval cases because they're real user queries — but they require manual labeling.

**Limitation:** Pre-launch, this dataset will be small (mostly Brandon's test queries). It supplements but doesn't replace synthetic data.

**Method 3: Trigger-as-query baseline (~15 min, ~50 cases).**

Use the raw `when_to_apply` trigger phrases directly as queries. Each should match its own framework. This is the easiest possible test — if the system can't even match its own trigger text, there's a fundamental problem. Useful as a smoke test, not a comprehensive eval.

**How many cases do we need?**

With 184 frameworks, we need enough cases to detect per-category failure patterns, not just an aggregate number.

- **Minimum for aggregate precision@1:** 50 on-topic cases gives ±14% confidence interval at 95% confidence. Enough to distinguish "20% precision" from "80% precision" but not "75%" from "85%".
- **Minimum for meaningful signal:** 100 on-topic + 30 adjacent + 20 off-topic = **150 cases**. This gives ±10% CI on precision@1 and enough adjacent cases to identify the worst false-positive categories.
- **Ideal for per-category analysis:** 200+ on-topic (3–5 per category). Deferred — this level of granularity matters post-launch, not for the initial baseline.

**Recommendation:** 150 cases for baseline. Expand to 200+ after launch when we have real user queries to supplement synthetic data.

### 4.2 Metrics

| Metric | What it measures | Formula | Launch bar |
|--------|-----------------|---------|------------|
| **Precision@1** | When we inject a framework, is it the right one? | TP / (TP + FP) where TP = correct match, FP = wrong match | ≥ 80% |
| **No-match accuracy** | When no framework should fire, do we correctly abstain? | TN / (TN + FP_null) where TN = correct null, FP_null = false fire on off-topic/adjacent | ≥ 85% |
| **False positive rate (adjacent)** | How often do topically-adjacent queries trigger the wrong framework? | FP_adjacent / total_adjacent_cases | ≤ 30% (Phase 1–3), ≤ 10% (long-term) |
| **False negative rate** | How often do on-topic queries return no framework? | FN / (TP + FN) | ≤ 25% |
| **MRR** | Is the correct framework in the top candidates even if not top-1? | mean(1/rank) over on-topic cases | ≥ 0.7 (informational) |

**Handling the "no match" case:**

False positives and false negatives are fundamentally different failure modes:

- **False positive (framework fires incorrectly):** Actively harmful. The model is forced into the wrong diagnostic lens. The "Enterprise Context Taxonomy" case. Measured by no-match accuracy and adjacent FP rate.
- **False negative (no framework when one should fire):** Merely neutral. The model reasons without a framework — this is the pre-Kinetic baseline. Acceptable up to ~25%.

**"Good enough" as a launch bar:**

| Metric | Must-hit | Nice-to-hit |
|--------|----------|-------------|
| Precision@1 | ≥ 80% | ≥ 90% |
| No-match accuracy | ≥ 85% | ≥ 95% |
| Adjacent FP rate | ≤ 30% | ≤ 10% |
| False negative rate | ≤ 25% | ≤ 15% |

**Rationale:** Pre-launch, it's better to inject no framework than the wrong one. The launch bar is asymmetric: strict on false positives, lenient on false negatives.

### 4.3 Minimum Viable Eval (Baseline — Run Before Any Changes)

**Goal:** Establish current precision@1 and false positive rate so we can measure improvement.

**Tooling recommendation: Custom Python script, not promptfoo.**

Promptfoo is designed for LLM output evaluation (prompt → response quality). Our eval is retrieval evaluation (query → did we select the right framework?). The pipeline under test is `select_framework()`, not a generation call. A custom script calling the function directly and comparing results to ground truth is simpler and more precise than shoehorning this into promptfoo's assertion model.

**Script: `eval_framework_selection.py`**

```python
# Pseudocode — invoke /llm-evaluation skill for full implementation patterns

import json
from framework_selection import select_framework

async def run_eval(eval_dataset_path: str, agent_id: str, openai_key: str):
    """Run framework selection eval against ground truth dataset."""
    with open(eval_dataset_path) as f:
        cases = [json.loads(line) for line in f]

    results = []
    for case in cases:
        match = await select_framework(
            query_text=case["query"],
            agent_id=agent_id,
            openai_key=openai_key,
            supabase=supabase_client,
        )

        actual_id = match.matched_framework_id  # framework_id or None
        expected_id = case["expected"]           # framework_id or None

        results.append({
            "query": case["query"],
            "expected": expected_id,
            "actual": actual_id,
            "actual_name": match.matched_framework_name,
            "score": match.boosted_score if hasattr(match, 'boosted_score') else None,
            "label": case["label"],
            "correct": actual_id == expected_id,
        })

    # Compute metrics
    on_topic = [r for r in results if r["label"] == "on-topic"]
    adjacent = [r for r in results if r["label"] == "adjacent"]
    off_topic = [r for r in results if r["label"] == "off-topic"]
    no_match = adjacent + off_topic

    precision_at_1 = sum(1 for r in on_topic if r["correct"]) / len(on_topic)
    no_match_acc = sum(1 for r in no_match if r["actual"] is None) / len(no_match)
    adjacent_fp = sum(1 for r in adjacent if r["actual"] is not None) / len(adjacent)
    false_neg = sum(1 for r in on_topic if r["actual"] is None) / len(on_topic)

    print(f"Precision@1:        {precision_at_1:.1%}")
    print(f"No-match accuracy:  {no_match_acc:.1%}")
    print(f"Adjacent FP rate:   {adjacent_fp:.1%}")
    print(f"False negative rate: {false_neg:.1%}")

    # Dump failures for analysis
    failures = [r for r in results if not r["correct"]]
    for f in failures:
        print(f"  FAIL: '{f['query']}' → got {f['actual_name']} (score {f['score']}), expected {f['expected']}")
```

**BYOK cost for baseline eval:**

- 150 eval cases × 1 embedding call each = 150 embedding calls
- `text-embedding-3-large` at ~$0.13/M tokens, ~20 tokens per query = ~$0.0004 total
- Negligible. The eval dataset can be run hundreds of times for pennies.

**What this baseline tells us:**

1. Current precision@1 — are we at 20%? 50%? 80%?
2. Which categories have the highest false positive rates — where does "topical neighborhood" confusion occur most?
3. The similarity score distribution for correct vs. incorrect matches — is there a clean threshold boundary?
4. Which specific frameworks are the worst offenders — inputs to Lever 2 (trigger rewriting) and Lever 3 (negative triggers)

### 4.4 Post-Implementation Eval

**Same dataset, same script, new pipeline.** After each change ships (threshold tuning, trigger rewriting, negative triggers), re-run the eval and compare.

**What counts as meaningful improvement:**

| Metric | Baseline → Post-change delta | Interpretation |
|--------|------------------------------|----------------|
| Precision@1 | +15 points or more | Clear win — the change worked |
| Precision@1 | +5–15 points | Modest improvement — may combine with other levers |
| Precision@1 | < +5 points | Noise. Not enough to justify the change alone |
| Adjacent FP rate | -15 points or more | Direct evidence the discrimination problem is improving |
| False negative rate | +10 points or more | **Regression** — the change is too aggressive |

**Regression risks by lever:**

| Lever | Regression risk | What to watch |
|-------|----------------|---------------|
| **Threshold tuning** (raise 0.55 → 0.65) | False negatives increase — correct frameworks that scored 0.55–0.65 now get rejected | Run eval, check FN rate before deploying. If FN rate jumps >10 points, the threshold is too aggressive. |
| **Trigger rewriting** | Rewritten triggers may accidentally match new false-positive queries that the old triggers didn't | Re-run the full eval (not just on-topic), check that adjacent FP rate didn't worsen. A/B compare old triggers vs. new. |
| **Negative triggers** | Over-aggressive negative triggers suppress correct matches | Check FN rate specifically for frameworks that have negative triggers. If a framework goes from matching correctly to not matching, the negative trigger is too broad. |

**Eval cadence:**

1. **Before any changes:** Baseline run (Phase 1)
2. **After threshold tuning:** Delta check on precision@1 and FN rate
3. **After trigger rewriting pilot (20 frameworks):** Delta check on the pilot subset + full dataset regression check
4. **After full trigger rewrite (184 frameworks):** Full eval run — this is the Phase 3 gate
5. **After negative triggers:** Full eval run — check adjacent FP rate specifically

### 4.5 Synthetic Data Limitations

The eval dataset is primarily synthetic (LLM-generated from trigger phrases). Known limitations:

1. **Vocabulary bias.** The LLM generating eval queries has seen the trigger phrases — its "natural user questions" may be closer to trigger vocabulary than real users would produce. This inflates precision@1 on synthetic data vs. real-world performance.

2. **Distribution mismatch.** Real user queries are messier: typos, multi-part questions, implicit context from conversation history. Synthetic queries are clean single-turn questions.

3. **Coverage gaps.** 50 of 184 frameworks are covered in the eval. The other 134 have no eval cases. False positives involving uncovered frameworks won't be caught.

4. **No conversation context.** Real queries have conversation history that influences what the user means. The eval tests cold queries only.

**Mitigations:**
- Supplement with mined conversation data as it becomes available (Method 2)
- After launch, build a feedback loop: log framework selections, sample for human review, add confirmed failures to the eval dataset
- Flag synthetic-only results as "optimistic" — real-world precision will likely be 5–10 points lower

---

## Recommended Skills for Eval Tickets

All tickets implementing eval work should invoke these skills:

| Skill | When to invoke | Why |
|-------|---------------|-----|
| `/llm-evaluation` | Start of any eval implementation ticket | Eval patterns, metrics implementation, LLM-as-judge templates, A/B testing framework |
| `/evaluate-rag` | KB retrieval eval specifically | RAG-specific metrics (MRR, NDCG, Precision@K) |
| `/generate-synthetic-data` | Building the eval dataset | Synthetic query generation patterns |
| `/write-judge-prompt` | If LLM-as-judge is needed for qualitative eval | Judge prompt design and calibration |
| `/systematic-debugging` | When eval reveals failures to diagnose | Root cause analysis of retrieval mismatches |

---

## Open Questions

| Question | Owner | Blocks |
|----------|-------|--------|
| Has the admin backfill been run? Are all 184 frameworks' triggers actually embedded? | Brandon | Phase 1 baseline |
| Can we access existing conversation `debug_prompt` data for mining? | Dinesh | Phase 1 mining |
| Who writes the pilot trigger rewrites — Jared (product vocabulary) or Monica (framework expertise)? | Brandon | Phase 2 |
| Is GPT-4o-mini acceptable for a future reranker, or must we support all BYOK models? | Brandon | Phase 4 |
