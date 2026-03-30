# Code Review: KIN-427 — Profile: prioritize OpenAI key + required-key messaging

**Reviewer:** Gilfoyle
**Date:** 2026-03-29
**Verdict:** Architecture approved. 0 Critical, 0 Important.
**File:** `packages/web/app/(app)/profile/page.tsx`

---

## Acceptance Criteria Check

| Criteria | Status |
|---|---|
| OpenAI key appears first in the API Keys list | PASS — line 50: `["openai", "anthropic", "google", "groq"]` |
| "Required" indicator visible next to OpenAI | PASS — lines 501, 510-514: amber badge, 10px uppercase |
| Missing-key alert shown when no OpenAI key is configured | PASS — lines 345, 490-494: amber border alert banner |
| Other provider keys unaffected | PASS — `isRequired` only true for `provider === "openai"` |

## Review Notes

- Change is ~15 lines, self-contained, no new logic paths. Visual-only.
- Amber styling is consistent between the badge (`amber-600`/`amber-400` dark mode) and the alert banner (`amber-500/50` border, `amber-500/10` background). Good.
- Alert message is clear and actionable: tells the user *what* is needed and *why*.
- No accessibility issues — alert is a visible `div`, not hidden behind interaction.
- No test changes needed — no new logic, no new API calls, no state changes.

## LGTM

Clean, minimal change. Meets all acceptance criteria.
