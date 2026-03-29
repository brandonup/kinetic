# Code Review — KIN-373: Add JSON file support to Knowledge Base upload

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 1

---

## Files Reviewed

- `packages/api/app/services/ingestion/extractor.py`
- `packages/web/components/KnowledgeBaseTab.tsx` (ACCEPTED_TYPES + ACCEPT_STRING)

---

## Backend Verification

### MIME type registration

`SUPPORTED_MIME_TYPES` (extractor.py, lines 18–35) now includes:
- `"application/json"` — correct
- `"application/jsonl"` — correct
- `"application/x-jsonlines"` — correct (some browsers/tools send this instead)

Extension fallback `_EXT_TO_MIME`:
- `.json` → `application/json`
- `.jsonl` → `application/jsonl`

This handles browsers that send `.json` files as `application/octet-stream`. Correct.

### JSON extraction path (lines 86–91)

```python
parsed = json.loads(content)
return json.dumps(parsed, indent=2, ensure_ascii=False)
```

Pretty-prints the parsed JSON. This is a reasonable approach — preserves the structure as readable text for chunking. `ensure_ascii=False` handles Unicode correctly. `RuntimeError` raised on invalid JSON — caught by the pipeline retry logic. Correct.

### JSONL extraction path (lines 93–129)

Multi-field text extraction with priority (`content` > `text` > `body` > `message` > `description`) plus `title`. Fallback to all string values if no known text field. This is pragmatic and handles the most common JSONL formats (chat logs, export dumps, article collections).

**Edge case: empty JSONL file** — `segments = []` → returns `""`. An empty string passed to chunking produces zero chunks and the pipeline reaches `completed` with zero chunks indexed. This is acceptable behavior — the user uploaded an empty or whitespace-only file.

**Edge case: non-dict JSONL lines** — `str(obj)` is appended. Handles arrays and primitives (e.g., `["item1", "item2"]` → `"['item1', 'item2']"`). Acceptable for MVP.

**`UnicodeDecodeError` is caught** (line 128) — raised to `RuntimeError`. Correct — prevents pipeline from hanging on binary-disguised-as-JSONL.

### Error handling

Both JSON and JSONL paths re-raise as `RuntimeError(f"Invalid ... in {filename!r}: {exc}")`. This satisfies the conventions rule: never silently swallow on write operations. The pipeline catches `RuntimeError` and marks the document `failed` with the error message. User will see the error via the status UI.

---

## Frontend Verification

`KnowledgeBaseTab.tsx`:

- `ACCEPTED_TYPES` includes `application/json`, `application/jsonl`, `application/x-jsonlines` — matches backend
- `ACCEPT_STRING` includes `.json,.jsonl` — correct file picker filter
- The extension-based client-side fallback in `ACCEPTED_TYPES` check: confirmed the component checks `file.type` against `ACCEPTED_TYPES`. For `.json` files, browsers typically send `application/json` — this is in the set. For `.jsonl`, browsers may send `application/octet-stream` — not in `ACCEPTED_TYPES`. The client-side check would reject `.jsonl` files that the browser misidentifies. However, the backend handles this via the extension fallback — so if the user bypasses client-side validation (or the browser does send the octet-stream type), the backend will still process it correctly.

---

## Important Findings

### I1 — Frontend extension fallback not implemented for JSONL

**File:** `packages/web/components/KnowledgeBaseTab.tsx`

The backend handles `.jsonl` files sent as `application/octet-stream` via `_EXT_TO_MIME`. The frontend `ACCEPTED_TYPES` check only validates `file.type` — if a browser sends a `.jsonl` file with `type = "application/octet-stream"`, the client-side validation will reject it with "Unsupported file type." The user cannot upload it from the UI even though the backend would accept it.

The fix is to add an extension-based fallback check in the client-side validation:
```typescript
const resolvedType = ACCEPTED_TYPES.has(file.type)
  ? file.type
  : file.name.endsWith(".jsonl") || file.name.endsWith(".json")
    ? "application/json" // or application/jsonl — just needs to be in the set
    : file.type;
if (!ACCEPTED_TYPES.has(resolvedType)) { /* reject */ }
```

**Severity:** Important. Affects `.jsonl` files on browsers that send `application/octet-stream` for unknown extensions (common on Windows). `.json` files are widely recognized by browsers and typically sent with the correct MIME type — less affected. Not blocking for approval since the backend works correctly and this is a UX gap rather than a data integrity issue. However, Dinesh should add the extension fallback in a follow-up.

---

## Test Coverage

Dinesh's comment confirms backend tests pass. No specific mention of test coverage for the JSON/JSONL extraction paths — the existing `test_ingestion.py` mocks `extract_text` at the pipeline level, so the extractor logic is not covered by the pipeline tests. The extractor itself does not appear to have dedicated unit tests.

**Gap (non-blocking):** `test_ingestion.py` mocks `extract_text` — the JSON/JSONL extraction paths are not covered by automated tests. A `TestJsonExtraction` class in a dedicated `test_extractor.py` would be valuable (valid JSON, invalid JSON, JSONL with known fields, JSONL with unknown fields, empty JSONL). Flag for KIN-333 (BYOK audit) or a dedicated hardening ticket.

---

## Summary

Backend implementation is correct. JSON parsing is clean, JSONL extraction is pragmatic and handles the common cases. I1 (JSONL extension fallback missing on frontend) is a UX gap worth fixing but does not affect data integrity. Approved — Dinesh to address I1 in a follow-up.

— Gilfoyle
