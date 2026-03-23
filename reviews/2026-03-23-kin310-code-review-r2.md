# Code Review R2: KIN-310 — Linked Upload (User Profile + Company)

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Author:** Dinesh
**Ticket:** KIN-310
**R1 doc:** `reviews/2026-03-23-kin310-code-review.md`

---

## R1 Status

| R1 Finding | Status |
|---|---|
| [Important] Silent `text = ""` fallback on RuntimeError | **UNRESOLVED.** Dinesh pushed back ("would break 10 tests"). See I1 below — pushback rejected. |
| [Important] Company "Use this" `\|\|` → `??` | **RESOLVED.** Confirmed `??` coalescing in implementation. |
| [Minor] Mock field names (`encrypted_key` → `key_ciphertext`) | **RESOLVED.** Mock rows now use correct field names. |

---

## New Findings

### C1 — Supabase Storage used for temp files despite explicit architectural ban

**File:** `linked_upload.py:39, 292-319, 379, 405-406, 444, 468-469, 507, 531-532`
**Category:** `spec-gap`

**Problem:**

The pre-implementation review (KIN-312, posted 10:07 on 2026-03-23) set an explicit constraint:

> **Do NOT implement [Supabase Storage for temp files].** Kinetic's design is a single combined endpoint: receive file → extract text → call LLM → return fields. The file never needs to leave the request.

The implementation ignores this. Every endpoint:
1. Reads file into memory: `content = await file.read()`
2. Uploads to Supabase Storage: `temp_path = _upload_to_temp_storage(client, content, filename)`
3. Extracts text from **in-memory bytes** (not from storage): `extract_text(content, content_type, filename)`
4. Calls LLM on extracted text
5. Deletes from storage in `finally` block

The storage upload on step 2 is never read back. Text extraction on step 3 uses the `content` variable from step 1. The entire storage round-trip (upload + delete) adds latency, creates orphan risk when deletion fails, and is a point of failure before extraction even starts.

R1 missed this — it approved the "temp storage lifecycle" as correct. The R1 reviewer did not have the KIN-312 pre-implementation constraint loaded. This R2 corrects that.

**Fix:** Remove `TEMP_BUCKET`, `_upload_to_temp_storage()`, `_delete_from_temp_storage()`. Remove `temp_path` assignment and `try/finally` wrapper from all three endpoints. The code already works without them — `content`, `extract_text`, and `extractor.extract` are all in-memory. Update the two `TestFileLifecycle` tests to verify no storage interaction occurs.

---

### I1 — `text = ""` fallback on RuntimeError (UNRESOLVED from R1)

**File:** `linked_upload.py:388-392, 453-455, 516-518`
**Category:** `error-swallow`

**Dinesh's pushback:** "Changing to 422 would break 10 tests without adding `extract_text` mocks to Jìan's scaffolding."

**Pushback rejected.** The test breakage is a scaffolding gap, not an architectural justification. Shipping a silent empty fallback that wastes the user's BYOK credits on a guaranteed-useless LLM call to avoid updating test mocks is the wrong tradeoff. The spec says extraction failure → error state with retry. The implementation returns 200 with null fields. Fix the behavior, fix the tests.

**Fix:** Same as R1 — replace `text = ""` with `HTTPException(422, "Couldn't extract content from this file.")`. Add `extract_text` mocks to affected tests.

---

### I2 — Agent extraction `max_tokens=700` — should be 800+

**File:** `linked_upload.py:256`
**Category:** `spec-gap`

KIN-311 pre-implementation review (KIN-312) specified `max_completion_tokens: 800 minimum` for `generate-agent-instructions`. Implementation uses 700. The target output is 300-500 tokens; 700 leaves no headroom for model framing. Truncation risk.

**Fix:** Change `max_tokens=700` to `max_tokens=800`.

---

## Verdict: Changes Requested

**1 Critical (C1), 2 Important (I1, I2).**

C1 is the blocker — the storage pattern directly contradicts the pre-implementation architectural direction and adds unnecessary complexity. I1 is an R1 carryover that must be resolved. I2 is a quick constant change.

---

## Required Changes Before R3

1. **C1:** Remove Supabase Storage. Pure in-memory only.
2. **I1:** Replace `text = ""` fallback with 422 error. Update tests.
3. **I2:** `max_tokens=700` → `800` for agent extraction.
