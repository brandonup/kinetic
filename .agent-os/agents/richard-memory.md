# Richard — Cross-Project Memory

Process baselines, bottleneck patterns, and recommendation outcomes. Updated at session end.

---

<!-- Entries format: - [YYYY-MM-DD] [project] Lesson or baseline -->

- [2026-03-18] [kinetic] **Baseline: review rejection rate = 30%.** Dinesh 28% (5/18 tickets), Big Head 33% (4/12 tickets). KIN-165 (Big Head) was the only 3-round ticket.

- [2026-03-18] [kinetic] **Baseline: estimate coverage = 2.5%.** 2 of 81 Done tickets have estimates. Recent Code Review tickets (KIN-181, KIN-193) have estimates — improvement starting W9.

- [2026-03-18] [kinetic] **Top Critical review categories: async/sync Supabase (5), RLS bypass (4), schema mismatch (3), error swallowing (8+ Important).** Error swallowing not in either implementer memory file — biggest uncaptured pattern.

- [2026-03-18] [kinetic] **Big Head handoff comments missing on KIN-171 and KIN-172.** Process requires summary + test command + test count before Gilfoyle review spawns.

- [2026-03-18] [kinetic] **Decision ticket lag is not a bottleneck.** KIN-147 resolved in 2.5 hours, KIN-188 in 1 hour. Jared question-routing filter is effective.

- [2026-03-18] [kinetic] **Big Head's 0 standalone bug tickets is a tracking gap, not cleaner code.** 33% review rejection rate + only 3-round ticket suggests inline fixing without separate Bug tickets.

- [2026-03-19] [kinetic] **Pipeline stages per feature: 5–7 (spec → tech spec → scaffolding → implement → review → QA).** Gilfoyle pre-spec is redundant for non-architectural features. Target: 3–4 stages.

- [2026-03-19] [kinetic] **Context loading per sprint: ~25K–30K lines of process docs.** ~60% of subagent tokens go to setup, not work. Lean subagent prompts could halve this.

- [2026-03-19] [kinetic] **Serial A→B→C chains add ~2 cycles per multi-part feature.** Horizontal decomposition (data → logic → API) enables parallelism. W9 Custom Agents would have been ~50% faster.

- [2026-03-19] [kinetic] **R1 and R5 are partially mutually exclusive.** Eliminating Gilfoyle pre-spec increases the value of Jìan scaffolding (which catches spec errors). Adopt R5 only if R1 is not adopted.

- [2026-03-19] [kinetic] **Token baseline: ~55K-65K lines process overhead per sprint.** Base context per session: ~1,100 lines. Per Gilfoyle subagent: ~1,300 lines. W11: 14 subagent spawns consumed ~18K lines of base context alone.

- [2026-03-19] [kinetic] **MEMORY.md is a growing liability: 199 lines / 140 entries / 51KB.** Loaded by every session + subagent. ~80% of entries are historical. Needs archival to stay under 80 lines.

- [2026-03-19] [kinetic] **conventions.md has ~40-50% redundancy.** Supabase async, error handling, snake_case mapping, Linear labels, issue lifecycle — all duplicated in agent files or linear-workflow.md. ~90 lines removable.

- [2026-03-22] [kinetic] **Baseline: Sprint 1 (Cycle 1) completion rate = 91.7% (22/24).** 2 carryovers, both Big Head (KIN-201, KIN-202), both Custom Agents Part C. Root cause: mid-sprint scope additions to in-progress ticket.

- [2026-03-22] [kinetic] **Estimate coverage improved to 27.6% (21/76 Done).** Dinesh 43%, Big Head 38%, Jìan 33%, Gilfoyle 0%, Jared 0%. Improvement from 2.5% baseline — norm establishing organically. Target for Sprint 2: 70%+ on implementation tickets.

- [2026-03-22] [kinetic] **Carryover baseline: 8.3% (2/24), 100% Big Head.** Both from mid-sprint scope additions. Watch for repeat pattern. Decision KIN-220 (scope question) archived without resolution.

- [2026-03-22] [kinetic] **Review doc coverage: 1 of 16 Gilfoyle reviews have a doc in reviews/.** KIN-244 only. 15 prior reviews exist in Linear only. Decision pending with Brandon on whether review docs are required for all reviews or only Complex-tier.

- [2026-03-22] [kinetic] **Sprint 2 board state at pivot: clean.** 0 In Progress, 0 Code Review, 2 Todo (Jìan QA stubs), 5 Backlog (4 archived old-project, 1 active). No cycle created yet. Codebase not bootstrapped — first implementation tickets not yet written.
