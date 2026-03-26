# Citation Assembly Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add citation metadata to SSE generation responses so AI answers that used KB content include expandable source references.

**Architecture:** After LLM streaming completes, build a citation array from `ctx.rag_chunks` (already collected by ContextAssembler) and include it in the `done` SSE event. No DB persistence — citations are ephemeral per spec §8.4.

**Tech Stack:** Python, FastAPI, SSE (existing generation endpoint)

---

## Existing State

- `ContextAssembler.assemble()` already populates `ctx.rag_chunks` with `RetrievedChunk` objects
- `RetrievedChunk` fields: `chunk_id`, `document_id`, `document_title`, `document_type`, `text`, `chunk_index`, `section_path`, `page_range`, `similarity_score`, `token_count`, `scope`
- Generation endpoint (`generation.py`) streams `delta` → `done` → (or `error`) SSE events
- Tests already written in `test_generation.py` lines 758-936 (3 test classes, currently failing)

## Spec Reference

- `docs/specs/generation-engine-spec.md` §8.2 (Citation Data Model), §8.3 (Assembly Flow), §8.4 (Citation Storage), §8.5 (Frontend Display)

---

### Task 1: Add `_build_citations()` helper + wire into `done` event

**Files:**
- Modify: `packages/api/app/api/routes/generation.py`
- Test: `packages/api/tests/test_generation.py` (existing — 3 citation test classes)

**Step 1: Add `_build_citations()` function**

Add after the `GenerateRequest` class:

```python
def _build_citations(rag_chunks: list) -> list[dict]:
    """Build citation metadata from RAG chunks for the SSE done event.

    Returns citations sorted by similarity_score DESC (most relevant first).
    Snippet is first ~200 chars of chunk text.

    Spec: generation-engine-spec.md §8.2, §8.3
    """
    citations = []
    for chunk in rag_chunks:
        citations.append({
            "document_id": chunk.document_id,
            "document_title": chunk.document_title,
            "file_type": chunk.document_type,
            "chunk_index": chunk.chunk_index,
            "snippet": chunk.text[:200],
            "similarity_score": chunk.similarity_score,
            "scope": chunk.scope,
        })
    citations.sort(key=lambda c: c["similarity_score"], reverse=True)
    return citations
```

**Step 2: Wire citations into the `done` SSE event inside `event_generator()`**

The `done_event` line currently builds:
```python
done_event = json.dumps({"type": "done", "message_id": message_id})
```

Change to:
```python
done_event = json.dumps({
    "type": "done",
    "message_id": message_id,
    "citations": _build_citations(ctx.rag_chunks),
})
```

Note: `ctx` must be captured in the closure — it's already available since `event_generator()` is defined inside `generate()` which has `ctx` in scope.

**Step 3: Run tests to verify they pass**

Run: `cd packages/api && python -m pytest tests/test_generation.py -v -k "Citation" 2>&1 | head -40`
Expected: 3 PASSED (TestCitationsInDoneEvent, TestCitationsEmptyWithNoRAG, TestCitationsBothScopes)

**Step 4: Run full test suite**

Run: `cd packages/api && python -m pytest tests/test_generation.py -v 2>&1 | tail -20`
Expected: All existing tests still pass (adding `citations` to done event is additive).

**Step 5: Commit**

```bash
git add packages/api/app/api/routes/generation.py
git commit -m "feat: add citation assembly to SSE generation responses (KIN-387)"
```

---

## Done When

- `done` SSE event includes `citations` array with correct fields per spec §8.2
- Citations sorted by `similarity_score` DESC
- Empty `citations: []` when no RAG chunks
- Both `project_kb` and `agent_kb` scopes captured
- All 3 citation tests + all 11 existing generation tests pass
- No DB persistence of citations (spec §8.4)
