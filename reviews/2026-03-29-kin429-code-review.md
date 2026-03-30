# Code Review: KIN-429 — Remote MCP: Slug Migration + Scaffold + RPC Verification

**Reviewer:** Gilfoyle
**Date:** 2026-03-29
**Verdict:** Architecture approved. 0 Critical, 1 Important.

---

## Files Reviewed

| File | Change |
|---|---|
| `packages/api/migrations/20260329000008_add_agent_slug.sql` | Incremental migration: add slug column, backfill, global unique constraint |
| `packages/api/migrations/000_complete_schema.sql` | Fresh-DB schema: slug column + constraint added |
| `docs/db-schema-spec.md` | Schema doc: slug column + `uq_agent_definitions_slug` index documented |
| `packages/api/app/api/routes/agents.py` | Agent creation sets slug; agent rename regenerates slug; `_ensure_unique_slug` helper |
| `packages/api/tests/test_agents.py` | Unit tests for `_agent_slug`, integration tests verify slug in create/patch responses |

## Acceptance Criteria Check

| Criteria | Status |
|---|---|
| Migration adds `slug text NOT NULL DEFAULT ''` | PASS — line 15 of migration |
| Constraint: `UNIQUE (slug)` globally | PASS — migration line 85, complete schema line 211 |
| Backfill: lowercase, hyphens, strip edges | PASS — migration lines 20-27 |
| Backfill: global dedup with `-2`, `-3` suffix | PASS — migration lines 39-68 |
| Backfill: empty/special-char names → fallback slug | PASS — migration lines 34-37 (`agent-<uuid-prefix>`) |
| Backfill: truncation to 60 chars | PASS — migration lines 29-32 |
| Agent creation API sets slug + checks uniqueness | PASS — `agents.py` line 232 |
| Agent rename regenerates slug | PASS — `agents.py` lines 811-813 |
| `db-schema-spec.md` updated | PASS — slug column + index documented |
| Tests cover slug generation | PASS — 6 unit tests for `_agent_slug`, integration tests verify slug in responses |

## Findings

### Important — Agent creation auto-suffixes instead of rejecting

The spec (Step 9) says: "Agent creation API: before INSERT, check if slug exists. If taken, return 400 with 'This agent name is already taken.' No auto-suffixing — user picks a new name."

The implementation does the opposite — `_ensure_unique_slug` auto-appends `-2`, `-3` etc. and silently creates the agent with a modified slug. This means:
- User creates "Nate Jones" → gets slug `nate-jones-2` without knowing why
- No feedback to the user that the name was taken
- The slug returned in the API response won't match what the user expects

This contradicts the spec, but I'd argue the implementation is actually better UX for the MVP. Auto-suffixing is less friction than making the user rename. However, it's a conscious spec deviation that Brandon should sign off on.

**Decision needed:** Keep auto-suffix (current implementation) or switch to 400 rejection (per spec)? If keeping auto-suffix, update the spec to match.

### Notes (non-blocking)

1. **Migration dedup logic is correct.** The `WHERE b.created_at <= a.created_at` clause ensures the first-created agent keeps the clean slug. Later agents get suffixes. Good.

2. **Complete schema and incremental migration are consistent.** Both produce the same end state: `slug NOT NULL DEFAULT ''`, `UNIQUE (slug)`, old per-owner constraint dropped. The complete schema even has the cleanup `DROP CONSTRAINT IF EXISTS uq_agent_definitions_owner_slug` for safety.

3. **Comment posted on wrong ticket.** The slug migration work was commented on KIN-427 instead of KIN-429. Cosmetic but noted.

4. **The `_slug` function (line 105) is for frameworks, not agents.** It has a different fallback (`"framework"` vs `"agent"`). Two slugify functions is fine — they serve different tables with different fallback semantics.

5. **RPC verification items (done-when 12-13) not addressed in the comment.** The Builder comment doesn't mention verifying `match_chunks` or `match_framework_triggers` RPCs exist. These are still pending on this ticket.

## Verdict

Code quality is solid. Migration is well-structured and idempotent. Application code correctly generates and maintains slugs on both create and rename paths. Tests cover the key cases.

The one spec deviation (auto-suffix vs 400 rejection) needs a decision from Brandon. Since the migration and the application code are internally consistent with each other, I'm approving the code — the spec just needs to be updated to match whichever behavior Brandon chooses.

**RPC verification (done-when 12-13) is still pending.** Do not move to Done until those are addressed.
