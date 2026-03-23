# Code Review — KIN-310: Linked Upload (User Profile + Company)

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Ticket:** KIN-310
**Round:** 1

---

## Assessment

The implementation is structurally sound — extraction flow, BYOK gate, temp storage lifecycle, and LLM prompts all match spec. Three issues need fixing before merge: one Important (silent fallback on corrupt files masks the error from the user), one Important (company "Use this" loses extracted data when the LLM returns empty strings), and one Minor (test stubs carry incorrect field name for API key row).

---

## Findings

### [Important] Backend: Silent fallback on corrupt/unextractable files returns 200 with empty fields

**File:** `packages/api/app/api/routes/linked_upload.py`, lines 388–392 (profile), 453–455 (company), 515–517 (agent)

**Problem:** When `extract_text()` raises `RuntimeError` (corrupt file, unstructured unavailable, parse failure), the code catches it, logs a warning, sets `text = ""`, and continues to the LLM call. The LLM then receives an empty document and returns `null` for all fields. The endpoint returns HTTP 200 with `{"name": null, "bio": null}`. The frontend interprets this as a successful extraction and moves to the review state — showing the user an empty review panel with no error message. The user has no signal that extraction failed.

The spec says: "Upload fails (network/processing error) → Show error state with retry option; no fields are modified." Corrupt file / unstructured failure is a processing error. Silently returning nulls violates the spec's edge case table and the conventions rule: "Never return None/[]/False in a try/except on write paths." While this is technically a read path, the user-visible outcome (silent empty result) is indistinguishable from a failure.

**Fix:** Re-raise `RuntimeError` from `extract_text()` as `HTTPException(422, "Couldn't read this file. It may be corrupt or password-protected.")`. Remove the `text = ""` fallback. The frontend already handles non-ok responses by showing an error state.

---

### [Important] Frontend (companies): "Use this" silently drops extracted fields when LLM returns empty strings

**File:** `packages/web/app/(app)/companies/page.tsx`, lines 347–349

**Problem:**
```tsx
setEditName(companyExtracted.name || editName);
setEditDesc(companyExtracted.description || editDesc);
```

The `||` operator treats an empty string as falsy. If the LLM extracts a name but returns an empty description (valid — spec says description generation can return null/empty), `setEditDesc` keeps the existing `editDesc` value instead of clearing it. More critically: if the user edits the extracted description field to be empty (intentionally blanking it before clicking "Use this"), the `||` silently reverts to the pre-upload value. The user's explicit edit is discarded.

**Fix:** Use nullish coalescing or explicit checks. At minimum: `setEditName(companyExtracted.name ?? editName)` and `setEditDesc(companyExtracted.description ?? editDesc)`. The `??` operator only falls back on `null`/`undefined`, not empty string — preserving the user's intent when they explicitly clear a field.

---

### [Minor] Tests: `encrypted_key` field name doesn't match backend schema

**File:** `packages/api/tests/test_linked_upload.py`, lines 89, 133, 153, 176, 195, etc. (every mock `data=[]` stub)

**Problem:** Every mock API key row uses `{"provider": "anthropic", "encrypted_key": "enc-key"}`. The backend's `_get_first_api_key()` selects `provider, key_ciphertext, key_nonce` (line 283–286 of `linked_upload.py`) and `LinkedUploadExtractor.extract()` reads `key_row["key_ciphertext"]` and `key_row["key_nonce"]` (lines 121–125). The mock rows don't include `key_ciphertext` or `key_nonce`. This is only harmless because `get_llm_client` is patched in the same tests — the mock extractor never actually reads the key row. But if a future test exercises `LinkedUploadExtractor.extract()` directly without patching, it will KeyError immediately. The field name is also misleading — it documents the wrong schema.

**Fix:** Update all mock key rows to `{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}` to match the actual DB schema (`docs/db-schema-spec.md §2`).

---

## What's Correct

**Security:**
- BYOK gate is enforced server-side at every endpoint before any file I/O. Frontend disabling is layered on top, not instead. Correct.
- `_validate_file()` runs before `_upload_to_temp_storage()` — fast fail before touching storage. Correct.
- Temp file is deleted in a `finally` block, guaranteeing cleanup on success, LLM failure, extraction failure, and even `UnsupportedFileTypeError`. Correct.
- `_delete_from_temp_storage()` catches and logs on failure without raising — orphan accumulation is logged, not silenced and not able to break the response. Correct pattern for cleanup paths.
- Company endpoint does not validate `company_id` ownership. This is acceptable for MVP — the endpoint is stateless (no DB write) and the user is authenticated. The only risk is an authenticated user querying the endpoint with another company's ID, which returns extracted fields they uploaded themselves. No data leak. Flag as tech debt if company-scoped auth is added later.

**Correctness:**
- LLM prompts match spec verbatim for profile (`generate-user-bio`) and company (`generate-company-description`). Agent prompt (KIN-311 stub) matches spec for `generate-agent-instructions` format.
- Text truncation: profile and company use `_TEXT_LIMIT_SHORT = 8_000`, agent uses `_TEXT_LIMIT_AGENT = 12_000`. Matches spec.
- Bio and description hard-capped at 1000 chars post-LLM (lines 175, 214). Matches spec max.
- `RuntimeError` from LLM explicitly caught and raised as `HTTPException(500)`. The anyio/BaseHTTPMiddleware Python 3.13 ExceptionGroup issue is correctly addressed.
- All Supabase calls use `run_in_executor` with `get_running_loop()`. Conventions-compliant.
- No DB writes in extraction endpoints. Caller saves via normal PATCH endpoints. Correct.

**Frontend (profile page):**
- Upload state machine (idle → loading → review → error) is correct and complete.
- `handleUseExtracted()` reads `reviewName`/`reviewBio` directly from local variables, not from stale React state closures. The `apiFetch` call inside uses the current captured values at the time of the click. Correct.
- `e.target.value = ""` reset in `finally` ensures re-uploading the same file re-triggers `onChange`. Correct.
- FormData upload correctly omits `Content-Type: application/json` header (via the guard in `api.ts` line 48). Correct.
- Review panel fields are editable (`setReviewName`, `setReviewBio`). Correct.
- File input `accept` attribute: `.pdf,.docx,.doc,.txt` — matches `PROFILE_ALLOWED_TYPES`. Correct.

**Frontend (companies page):**
- `activeUploadCompanyId` ref correctly tracks which company is being uploaded to across async boundaries. Shared file input pattern is sound for a single-active-upload-at-a-time flow.
- Review panel inside the edit form is the right UX — keeps the extraction result in context alongside the editable fields.
- File input `accept`: `.pdf,.docx,.doc,.pptx,.ppt,.txt,.md` — matches `COMPANY_ALLOWED_TYPES`. Correct.
- Error state (`uploadCompanyErrorId`) correctly scoped per company. Correct.

**api.ts:**
- FormData guard `fetchOptions.body instanceof FormData ? {} : { "Content-Type": "application/json" }` is correct. Browser sets multipart boundary automatically when `Content-Type` is omitted for FormData. Correct.

**Tests:**
- 14 tests passing, 4 correctly skipped (KIN-311 pending). Coverage of BYOK gate, file lifecycle (success and failure paths), extraction happy path, file type rejection, LLM failure surfacing, and review-save flow is adequate for the scope.
- `finally` block cleanup test correctly asserts `remove.assert_called_once()` on both success and failure paths.

---

## Summary

2 Important findings, 1 Minor. The silent corrupt-file fallback is the more dangerous of the two — it returns a misleading 200 with empty fields that the user will see as "the AI couldn't find anything" when the actual problem is a file parse failure. The company "Use this" bug is a data correctness issue that will occasionally discard a user's intentional edit. Both are fixable in an hour.

---

**Verdict: Changes requested.** 2 Important, 1 Minor. Review: `reviews/2026-03-23-kin310-code-review.md`.
Block: silent RuntimeError fallback (extract_text) returns misleading 200; company "Use this" drops intentionally-cleared fields.
