## KIN-391 Code Review — R1

**Reviewer:** Gilfoyle
**Date:** 2026-03-26
**Verdict:** APPROVED

**Files reviewed:**
- `packages/api/app/services/rag/framework_selection.py` — `_assemble_framework_text()`, `fetch_pinned_frameworks()`, `excluded_ids` param
- `packages/api/app/services/context_assembler.py` — `_assemble_framework()` override logic
- `packages/api/app/api/routes/agents.py` — `FrameworkOverrides` model (`disabled` field)
- `packages/api/tests/test_framework_selection.py` — `TestExcludedIdsFiltering`, `TestFetchPinnedFrameworks`
- `packages/api/tests/test_context_assembly.py` — `TestL7OverrideDisabled`, `TestL7OverridePinned`, `TestL7OverrideExcluded`, `TestL7OverrideNoInstance`
**Spec:** `docs/specs/agents.md` §11

---

### Findings

**[Medium] `framework_selection.py` L82–89 — Sequential DB fetch for pinned frameworks**

`fetch_pinned_frameworks` loops over `pinned_ids` and issues one Supabase query per ID. With max 3 pinned (spec §11.3 rule 4), this is tolerable, but a single `.in_("id", pinned_ids)` query would be cleaner and faster. Not blocking — the max-3 cap limits the damage.

**[Medium] `context_assembler.py` L385–393 — Duplicate agent_instances query**

`_assemble_framework` issues its own `agent_instances` query to fetch `framework_overrides`. This is the second query to `agent_instances` in the same `assemble()` call — `_assemble_agent_memory` already queries the same table at L309-317. The instance row could be fetched once (selecting both `id` and `framework_overrides`) and passed through. Not blocking for this PR, but worth consolidating in a follow-up to cut one DB round-trip per request.

**[Low] `framework_selection.py` L99 — Bare except with warning log is correct but could log framework ID context**

The `except Exception` block at L98-99 logs a warning with `exc_info=True`, which is good. Minor: the log message already includes `fid`, so this is fine as-is.

**[Low] `context_assembler.py` L427 — Exception log uses `%s` for exc (correct)**

The catch-all at L426 logs with `%s` for the exception, which is the correct pattern (lazy formatting). Good.

---

### Checklist Verification

1. **Disabled path correctly skips L7?** Yes. `context_assembler.py` L397-402: checks `overrides.get("disabled")`, logs, returns early. `select_framework` is never called. Test `TestL7OverrideDisabled` confirms `mock_select.assert_not_called()`. Matches spec §11.1 ("Skip framework selection entirely") and §11.3 rule 3 ("`disabled` supersedes").

2. **Pinned path bypasses pipeline and fetches by ID?** Yes. `context_assembler.py` L405-413: checks `overrides.get("pinned", [])`, calls `fetch_pinned_frameworks`, appends each match to `system_parts`, returns before reaching the pipeline. `fetch_pinned_frameworks` in `framework_selection.py` L68-100 queries by individual ID using `.maybe_single()`. Test `TestL7OverridePinned` confirms `mock_select.assert_not_called()` and `mock_fetch_pinned.assert_called_once()`. Matches spec §11.4 pseudocode.

3. **Excluded path filters candidates before ranking?** Yes. `framework_selection.py` L153-157: after vector search returns triggers but before grouping/ranking, excluded IDs are filtered out with a list comprehension. If all candidates filtered, returns `no_match`. Test `TestExcludedIdsFiltering` covers both partial and total exclusion. `context_assembler.py` L416-421 converts the list to a set and passes as `excluded_ids`. Matches spec §11.4.

4. **Error handling correct (fail-open, every except has a log)?** Yes.
   - `fetch_pinned_frameworks` L98-99: `except Exception` with `logger.warning` + `exc_info=True`. Silently skips. Correct fail-open per spec.
   - `select_framework` L208-210: outer `except Exception` with `logger.warning` + `exc_info=True`. Returns `no_match`. Correct.
   - `_assemble_framework` L426-427: `except Exception` with `logger.warning`. Returns (skips L7). Correct.
   - No silent swallows without logging.

5. **Missing test cases?**
   - `fetch_pinned_frameworks` exception path (DB throws on fetch) — not tested. The `except Exception` at L98-99 handles it, but there is no test confirming the warning is logged and the framework is skipped rather than the whole function crashing. Low risk since the code is straightforward.
   - Interaction between `disabled=True` with non-empty `pinned` list — spec §11.3 rule 3 says disabled supersedes. The code checks `disabled` first (L397), so pinned is never reached. No explicit test for this interaction, but the code ordering makes it implicit. Would be nice to have.
   - Empty `pinned` list (should fall through to pipeline) — implicitly tested by `TestL7OverrideExcluded` which passes `pinned: []`, but not explicitly named.

6. **`_assemble_framework` signature change breaks callers?** No. The only call site is `context_assembler.py` L158-160, which was updated in the same diff to pass `user_id`. The MCP route (`mcp.py` L358) calls `select_framework` directly (not `_assemble_framework`) — and the new `excluded_ids` param defaults to `None`, so existing callers are unaffected. The generation engine test at `test_generation.py` L701 patches `select_framework` — also unaffected since the new param is optional.

---

### Summary

Clean implementation. The three override paths (disabled, pinned, excluded) follow the spec §11.4 pseudocode exactly, in the correct priority order. Error handling is consistently fail-open with logging. The `_assemble_framework` signature change is backward-compatible. The `FrameworkOverrides` Pydantic model correctly adds the `disabled: bool = False` field. Test coverage is solid — all four override scenarios tested in `test_context_assembly.py`, and `test_framework_selection.py` covers the excluded-ids filtering and pinned fetch.

Two medium items (sequential pinned fetch, duplicate instance query) are optimization opportunities for a follow-up, not blockers.

No Critical or Important findings. Approved.
