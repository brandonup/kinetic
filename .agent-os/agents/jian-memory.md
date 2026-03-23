# Jìan — Cross-Project Memory

Transferable QA and evaluation lessons learned across projects. Updated when Brandon says "remember this" or "add that to your memory."

---

<!-- Entries format: - [YYYY-MM-DD] [project] Lesson learned -->

- [2026-03-17] [kinetic] Sync Supabase calls from async methods is a systemic pattern — found in 4 separate files across 2 packages. When reviewing any new repo/method using Supabase, check for run_in_executor wrapping first.
- [2026-03-17] [kinetic] Tests that mock away external clients can't catch integration issues. The consecutive-user-messages P0 (KIN-105) was invisible in tests because MagicMock.messages.create() doesn't validate message format. Always check: does the test actually exercise the contract?
- [2026-03-17] [kinetic] Inner try/catch blocks that catch broad Exception can swallow intentional throws. Found in use-copilot.ts where a JSON.parse try/catch also caught the intentional error event throw. Pattern: keep inner try/catch tight and specific.
- [2026-03-17] [kinetic] Eval suites that only test LLM output quality miss the retrieval layer. All 21 Copilot eval cases inject pre-selected context via fixtures — none test whether the retrieval/ACL layer actually excludes unauthorized chunks. ACL enforcement needs integration-level evals, not just fixture-based ones.
- [2026-03-17] [kinetic] Single-turn evals don't cover multi-turn fragility. Session history, pronoun resolution ("tell me more about *that*"), and context carryover are invisible to single-turn evals. Always plan multi-turn cases for any conversational system.
- [2026-03-17] [kinetic] Edit tool `replace_all` fails when the target string appears in multiple places. When appending YAML entries after a field like `adversarial: true` that appears in several cases, provide wider surrounding context to make the match unique — or use targeted single-instance edits instead.
- [2026-03-18] [kinetic] Sprint loop: don't pause for diagnostic Linear reads after loading the Todo queue. Pick the first Todo, move to In Progress, start work. Extra status checks (KIN-XX done? KIN-YY still relevant?) before starting violate the sprint loop and require Brandon to intervene.
- [2026-03-18] [kinetic] Test plan ticket scoping: "write the plan" = Done (plan doc is the deliverable). Don't leave a ticket open indefinitely waiting for implementation to land. When implementation arrives, running the tests is handled via the Jìan subagent review loop — not a pre-existing open ticket.
- [2026-03-18] [general] Bash `mkdir -p` is sandbox-blocked; use the Write tool to create files in new directories — Write creates parent dirs automatically. Never fall back to Bash for directory creation.
- [2026-03-19] [kinetic] When the only Todo is blocked, scaffolding-ahead is the right pivot: check next-sprint specs (Done) that lack test plans, create ticket, write plans + scaffolding. Don't idle or ask Brandon what to do.
- [2026-03-19] [kinetic] For features built with TDD, verify existing tests against test plan requirements before writing new ones. Implementation tests often already have 100% coverage — only scaffold what's missing (e.g., SoT docs had no tests, but accuracy graph and Company Briefs were fully covered).
- [2026-03-19] [kinetic] Read stub files before implementing them — Dinesh's TDD workflow may have already replaced Jìan stubs with complete implementations. SR/HM TypeScript tests were fully written by Dinesh as part of KIN-207; writing them again would have been duplicate work.
- [2026-03-19] [kinetic] Python stubs for TypeScript routes can't test across language boundaries. When activation reveals stubs are in the wrong language (e.g., SR/HM in .py but testing Next.js routes), create tests in the correct package (packages/web/tests/) and remove the Python stubs.
- [2026-03-19] [kinetic] Supabase multi-eq mock chains: `update().eq1().eq2()` — eq2 is tracked via `eq.return_value.eq.call_args_list`, NOT `eq.call_args_list`. When verifying workspace_id scoping, check both levels: `eq1 = ...update.return_value.eq.call_args_list` and `eq2 = ...update.return_value.eq.return_value.eq.call_args_list`, then combine.

