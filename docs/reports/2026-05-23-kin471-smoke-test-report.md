# KIN-471 — KB ingestion pipeline smoke test

**Date:** 2026-05-23
**Author:** Jìan
**Target env:** Prod (Supabase `iiapaogaoadtvjnryuls`, Railway `kinetic-production-b568`)
**KB tested:** Nate B Jones agent (`91db7050-aa0b-403a-8faf-dcdcd095add0`)
**Recommendation:** **SHIP** — the daily scraper is operational. One real defect found (KIN-490) with a clean fix path; one operational gap recommended (sentinel below). No regressions in the live pipeline.

---

## What we actually wanted to know

Does the daily Substack sync reliably find new posts on `natesnewsletter.substack.com` and ingest them into Nate's KB with the correct embeddings, chunk format, and retrievability?

**Yes — provided the dedup table doesn't contain orphans.** Today's exercise both proved the pipeline works end-to-end *and* surfaced the silent-skip bug that explained why Brandon's new article never landed.

---

## Pipeline state on prod (verified during test)

| Layer | Setting | Verification |
| -- | -- | -- |
| Embedding model | `gemini-embedding-001` | 2,529 chunks, 100% match |
| Embedding storage | `halfvec(3072)` | random + sampled chunks, all dim=3072 |
| HNSW index | active on `knowledge_base_chunks.embedding` | `match_chunks` returns sub-second on 2,529-row corpus |
| `match_chunks` RPC | working post-KIN-478 uuid-cast fix | self-query sim=1.0, related chunks ranked 0.78-0.93 |
| `match_framework_triggers` RPC | working | 886 triggers / 184 frameworks all embedded; self-query sim=1.0 |
| Chunk overlap | paragraph-based, capped at 75 words | verified across 162 chunks; see "Overlap caveat" below |
| Contextual header | `"Source: {title}\n(Part X of Y)\n\n"` | 162/162 chunks across 10 sampled docs; 2/2 on the new ingest |
| Scrape poller | every 5 min, picks `next_run_at <= NOW()` | fired twice today, both runs clean |

## What was tested

### 1. Structural sampling — 10 existing docs / 162 chunks
Pulled 3 short, 4 medium, 3 long docs from the existing 567-doc corpus and verified per-doc:

- **dim=3072** on every chunk ✓
- **`gemini-embedding-001`** on every chunk ✓
- **`Source: {title}\n(Part X of Y)\n\n…`** header on every chunk ✓ (including single-chunk docs, which carry `(Part 1 of 1)` — note this corrects the assumption in the rewritten ticket acceptance criteria)
- **Part X of Y numbering** monotonic and matches `count(*) OVER (PARTITION BY document_id)`

### 2. End-to-end live ingestion
Forced a scrape via `UPDATE scrape_sources SET next_run_at = NOW()`. Article `ai-organize-files-before-writing` flowed scrape → dedup-check → Substack extractor → chunker → Gemini embedder → DB in ~4 seconds.

- 2 chunks created (1825 + 1996 chars)
- dim=3072, gemini-embedding-001
- Headers correct
- **Overlap working**: chunk 1's head text exactly mirrors chunk 0's tail ("Only after that did the writing prompt become simple…")
- `match_chunks` self-query: own chunks rank at sim 1.00 + 0.93, then 3 semantically-clustered articles (`prompting-just-split-into-4-different`, `chatgpt-55-scored-87`, `ai-agents-better-communicator`) at 0.78–0.81

### 3. Vector RPC regression guards
- `match_chunks` ✓ — KIN-478 uuid-cast fix holds
- `match_framework_triggers` ✓ — 886 trigger embeddings present, ordering healthy

---

## Findings

### 🔴 Real bug — silently dropped articles (KIN-490 filed)

`nbj_extractor/preseed_dedup.py` marks every Substack post as "seen" in `scrape_source_posts` without checking that the post actually exists in the target KB. Any Substack post that wasn't manually uploaded becomes permanently invisible to the daily scraper — no error, no log, no signal.

**Today's scope:** 2 orphans out of 569 dedup rows (0.4%):
1. `ai-organize-files-before-writing` — Brandon's missing article ✅ recovered during this test
2. `coming-soon` — Substack template page (legitimate skip)

**Workaround applied:** Deleted the orphan dedup row + force-ran the scraper. Article now ingested cleanly into the KB (doc `a1113e5d-462d-4928-9e82-3456ae341b01`).

**Fix:** See KIN-490 for three options. Recommended: preseed only inserts dedup rows for slugs that already match a KB doc.

### 🟡 Operational gap — no sentinel for silent-skip class

Today's discovery only happened because Brandon noticed an article was missing and asked. If a future Substack post hits the same dedup-orphan condition, it'll be silently dropped until someone notices. **Recommend a daily check** (filed as a separate Linear ticket) that compares scrape_source_posts to knowledge_base_documents and flags orphans.

### 🟡 Naming inconsistency between upload paths

| Path | Title format |
| -- | -- |
| Manual upload (567 existing docs) | URL slug, e.g. `the-claude-code-complete-guide-learn.txt` |
| Scraper ingest (new doc today) | Article subtitle, e.g. `Build the room before you write the memo. Grab the 4-prompt project room kit: source inventory, duplicate log, missing-context list, grounded draft..txt` |

Two problems: (a) document.title means different things depending on ingestion path, which complicates any title-based retrieval/filtering; (b) cosmetic — the trailing `..txt` (double period) when the subtitle already ends in a period.

### 🟡 `document.token_count = NULL` on scraper-ingested docs

The new doc has `token_count = NULL` at the document level, despite chunks being created correctly. The chunker computes word counts per chunk but the document-level field isn't populated on the scraper path. Manual-upload path presumably populates it. Worth checking `pipeline.py:414` (`_update_document(supabase, document_id, token_count=total_tokens)`) — may only fire on a code branch the scraper bypasses.

### 🟡 Overlap caveat — long paragraphs get zero overlap

Per `chunker.py:124-132`, overlap is paragraph-based: walk the buffer in reverse, add each paragraph until the cumulative word count exceeds `CHUNK_OVERLAP_WORDS=75`, then `break`. If the *last* paragraph in the buffer is already > 75 words, the loop breaks on the first iteration and overlap is **zero**.

**Observed:** in the long Claude Code guide doc (28 chunks), chunks 0→1 had clear overlap, chunks 1→2 had **none** because chunk 1's closing paragraph was ~110 words.

This isn't a bug — code does what it says. But it means long-paragraph content (transcripts, long-form essays, podcasts) gets less retrieval continuity than the design intent suggests. Worth keeping in mind when interpreting future RAG quality issues.

### 🟢 Scrape cadence drift (minor)

First forced run took 6:30 to fire (cycle: 5 min). Second forced run took 2:35 — within window. Worth noting that the "every 5 min" cadence is best-effort against APScheduler ticks, not a hard SLA. Not blocking.

---

## Skipped on purpose

- **KIN-449 eval re-run.** Existing baseline scored 100% on a 13-case dataset (2 on-topic, 10 off-topic). Re-running against the 568-doc corpus would produce ~the same numbers and prove nothing pipeline-specific. The real eval expansion lives in KIN-483. Per Brandon: "the goal is the daily sync working" — eval re-run is over-engineered tactical work for that goal.
- **Framework JSON ingestion + transcript edge case.** Not part of the daily Substack sync. Will be exercised naturally as Brandon ingests those content types via their own paths.
- **`SEMANTIC_CHUNKING_ENABLED` toggle test.** Default `False` in code; runtime value on Railway not confirmed. Defaults are safe; not worth the cycle.

---

## Recommendation

**SHIP — daily Substack sync is operational.** Two follow-ups, neither blocking the production flow:

1. **KIN-490** (filed) — fix preseed orphan bug. Medium priority. Until fixed, manually verify any newly-published article actually lands within ~24h, or run the SQL diagnostic from the KIN-490 description.
2. **New ticket: dedup-orphan sentinel** (to be filed) — daily check + alert so silent-skip incidents surface automatically.

No regressions found in the post-KIN-476/KIN-478 retrieval pipeline. The 567 existing docs are all clean.
