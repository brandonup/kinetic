# Code Review — KIN-346 (R2)
**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Ticket:** KIN-346 — Document status badge + polling UI
**Files reviewed:**
- `packages/web/components/DocumentStatusBadge.tsx`
- `packages/web/components/DocumentRow.tsx`
- `packages/web/components/KnowledgeBaseTab.tsx`
- `packages/web/lib/hooks/useDocumentStatus.ts`
- `packages/web/lib/types/models.ts`
- `packages/web/app/__tests__/components/DocumentStatusBadge.test.tsx`
- `packages/web/app/__tests__/components/DocumentRow.test.tsx`
- `packages/web/app/__tests__/hooks/useDocumentStatus.test.ts`

---

## R1 Findings — Verification

| ID | Finding | Status |
|---|---|---|
| I1 | KnowledgeBaseTab catch — no console.error before setError | FIXED |
| I2 | useDocumentStatus catch — no console.error before setError | FIXED |
| I3 | No hook tests | FIXED — 7 hook-level tests added |
| M4/M5 | Inline union types | FIXED — DocumentStatus imported from models.ts |
| M6 | retryError outside border | FIXED — column layout, error inside border div |
| M7 | Failed badge a11y | FIXED — aria-label with error stage + message |
| M8 | eslint-disable in agent page | Pre-existing, skipped |

All R1 findings are confirmed resolved.

---

## New Findings (R2)

### I1 (Important) — KnowledgeBaseTab: !res.ok path discards HTTP status and response body without logging

**File:** `packages/web/components/KnowledgeBaseTab.tsx`, lines 42–44

**Problem:**

```ts
if (!res.ok) {
  setError("Failed to load documents");
  return;
}
```

The HTTP status code and API response body are silently discarded. The error is set to a static string with no logging. This violates the convention: "Surface errors explicitly — don't swallow them silently." In production, a 403, 404, or 500 from this endpoint is indistinguishable from any other failure — the HTTP status and server error detail are lost.

The `catch` block (I1 from R1) was fixed with `console.error`, but the `!res.ok` path was not given the same treatment. These are two distinct error paths and both need logging.

**Fix:**

```ts
if (!res.ok) {
  const errText = await res.text().catch(() => "");
  console.error("[KnowledgeBaseTab] fetchDocuments HTTP error:", res.status, errText);
  setError("Failed to load documents");
  return;
}
```

**Severity:** Important — read-only path (no data loss), but HTTP errors are invisible in production logs.

---

## Summary

All 7 R1 findings resolved. One new Important finding: `!res.ok` path in `KnowledgeBaseTab.fetchDocuments` lacks logging, making HTTP errors invisible in production. Fix is a two-line change.

**Verdict: CHANGES_REQUESTED.** 0 Critical, 1 Important.
