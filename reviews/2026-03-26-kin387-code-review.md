# Code Review — KIN-387: Implement citation assembly in generation responses

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED
**Critical:** 1 | **Important:** 0

---

## Summary

`_build_citations()` is correctly implemented and properly wired. Field mapping, sort order, snippet truncation, closure capture, and empty-list behavior all match spec §8.2–8.3. The conftest sandbox patch is clean. Tests are well-structured.

One Critical finding: the `done` SSE event is missing the `model` field specified in §1.5. KIN-387 touched this exact dict, making it in-scope for this review.

---

## Findings

### C1 — `model` field missing from `done` SSE event

**File:** `packages/api/app/api/routes/generation.py`, lines 299–303

**Spec reference:** §1.5 SSE Stream Format

The spec defines the `done` event as:
```
data: {"message_id": "uuid", "model": "claude-sonnet-4-6", "citations": [...]}
```

The implementation builds:
```python
done_event = json.dumps({
    "type": "done",
    "message_id": message_id,
    "citations": _build_citations(ctx.rag_chunks),
})
```

`model` is absent. `_model_name` is in scope as a closure variable and must be included.

**Fix:**
```python
done_event = json.dumps({
    "type": "done",
    "message_id": message_id,
    "model": _model_name,
    "citations": _build_citations(ctx.rag_chunks),
})
```

**Test coverage required:** Add an assertion in `TestGenerateSuccess` (and at minimum `TestCitationsInDoneEvent`) that `done["model"] == MODEL_NAME`. The field is present in spec — it needs a test.

---

## Approved Items

| Area | Assessment |
|---|---|
| `_build_citations()` field mapping | Correct. `document_type` → `file_type` matches spec §8.2. |
| Snippet truncation | `chunk.text[:200]` matches spec §8.2. Handles both short and long text correctly. |
| Sort order | `similarity_score DESC` matches spec §8.3. |
| Empty list when no RAG | `[]` returned correctly. |
| Closure capture of `ctx` | `ctx` is in scope from `generate()` outer function — correct. |
| No DB persistence | Matches spec §8.4. |
| Both scope values | `project_kb` and `agent_kb` both flow through correctly. |
| `_build_citations` placement | Before `GenerateRequest` — minor plan deviation, functionally correct. |
| `conftest.py` sandbox patch | Correctly monkey-patches `pathlib.Path` at collection time. Scope is `.env*` only. Clean. |
| Test class naming | All three new classes are uniquely named — no shadowing risk. |
| Test structure | 3 classes, focused, well-structured. Deliberately out-of-order input in `TestCitationsInDoneEvent` is a good adversarial check. |

---

## Required Changes

1. Add `"model": _model_name` to the `done_event` dict in `event_generator()`.
2. Add assertion `assert done["model"] == MODEL_NAME` to `TestCitationsInDoneEvent.test_citations_returned_in_done_event` (and to `TestGenerateSuccess` if not already present).
