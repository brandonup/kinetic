# Context Load Audit — 2026-05-24

## Scope

Cross-project audit of all files loaded into agent sessions. Question: where can we reduce token budget without reducing quality? Compared against the 2026-04-05 baseline.

## Multipliers Matter More Than Line Counts

Lines saved must be weighted by how often a file loads:

| File category | Multiplier | Why |
|---|---|---|
| User CLAUDE.md, auto-memory MEMORY.md, root CLAUDE.md | **1.0** (every session) | Loaded for every agent invocation, every project |
| linear-workflow.md | **~0.85** | Loaded by every Linear-using session (all but pure-research) |
| Project MEMORY.md, Project CLAUDE.md | **~0.5** | Loaded only when working on that project |
| Per-agent file | **~0.15** | Loaded only when that specific agent runs |
| Lazy-loaded references | **~0.1** | Only when the specific task path is hit |

**Implication:** A 10-line cut in CLAUDE.md is worth more than a 50-line cut in `dinesh.md`.

## Current State (2026-05-24)

### Cross-Project Shared Overhead (loaded every session)

| File | Lines | vs 2026-04-05 |
|---|---|---|
| User CLAUDE.md (~/.claude/CLAUDE.md) | 17 | — (not counted prior) |
| Son of Anton CLAUDE.md | 153 | **+37** (Security section added) |
| Auto-memory MEMORY.md (index) | 38 | — (not counted prior) |
| linear-workflow.md | 108 | -1 |
| **Total** | **316** | (vs ~225 prior, excluding additions) |

### Project-Specific

| File | Lines | Notes |
|---|---|---|
| projects/kinetic/MEMORY.md | 81 | Header says "as of 2026-04-08" but contains entries through 2026-05-24. Stale claim. |
| projects/kinetic/CLAUDE.md | 8 | Lean. Pointer only. |
| projects/brain/MEMORY.md | 44 | Reasonable. |
| projects/brain/CLAUDE.md | 77 | **9x larger than Kinetic's.** Includes reference content that belongs in `brain/docs/`. |

### Per-Agent

| Agent | File | Memory | Reference (lazy) |
|---|---|---|---|
| Dinesh | 163 | 47 | 57 (dinesh-reference) |
| Jared | 147 | 40 | — |
| Jian | 133 | 26 | — |
| Gilfoyle | 118 | 29 | 79 (handoffs) |
| Richard | 111 | 53 | 104+19 (diagnostics, board-scan) |
| Monica | 89 | 17 | — |
| Reviewer | 76 | — | — |

### Auto-Memory (~/.claude/projects/.../memory/)

28 memory files, ~472 lines total. Only `MEMORY.md` (38 lines) auto-loads per session as an index. Individual files load only when relevant — but the **index** is always present.

Of 14 `feedback_*` entries, several are near-duplicates of CLAUDE.md operating norms:
- `feedback_always_include_cd.md`
- `feedback_commands_not_links.md`
- `feedback_commit_commands.md`
- `feedback_give_paths_directly.md`
- `feedback_no_placeholders.md`
- `feedback_commit_commands.md`

All converge on "give paste-ready commands with full paths." CLAUDE.md § Operating Norms already says this.

## Key Findings

1. **CLAUDE.md grew 32% since April (116 → 153) — entirely the Security section (51 lines).** Loaded every session, every agent. The security rules are non-negotiable, but the rationale/preamble inside each numbered rule can be condensed without weakening behavior. Estimated 25 lines compressible.

2. **Auto-memory feedback files duplicate CLAUDE.md operating norms.** ~6 feedback entries say variations of "give paste-ready commands with `cd` in the directory." Consolidating to one entry saves index lines and reduces noise.

3. **linear-workflow.md has 10 lines of MCP tool table that the `linear-automation` skill already provides on demand.** Redundant. Loaded by ~85% of sessions.

4. **Kinetic MEMORY.md violates the 2-sentence-per-entry rule** in the Implementation Status section. Paragraph-style entries about Recency-aware retrieval (KIN-481/482/483/484/489/492) and Substack sync (KIN-479) total ~25 lines. Plus stale header. Estimated 30 lines trimmable, none load-bearing.

5. **brain/CLAUDE.md is 77 lines** (Kinetic's is 8). Sections "What This Repo Is", "OB1 Repo Structure", "PR Standards", "Key Files" are reference-style — load on demand from `brain/docs/`. Saves ~40 lines per Brain session.

6. **dinesh.md "Spawning the Reviewer" prompt template (16 lines)** is a one-time reference, not procedural guidance Dinesh re-reads each ticket. Belongs in `dinesh-reference.md`.

7. **richard-memory.md stale entries.** Defect log analyzed through 2026-03-28 (8 weeks stale today). The "Multi-agent system collapsed into Builder + Reviewer" entry contradicts current reality — Dinesh/Gilfoyle/Jian files all still exist and CLAUDE.md still references them. 2026-04-05 R1 (15 lines archivable) was never executed.

8. **2026-04-05 R1 not executed** — `richard-memory.md` archive recommendation pending 7 weeks.

## Recommendations (Ranked by Lines × Multiplier per Session)

| # | Recommendation | Raw Lines | Multiplier | Effective Saving | Quality Risk | Effort |
|---|---|---|---|---|---|---|
| **R1** | Compress CLAUDE.md § Security: keep all hard rules, strip rationale/preamble. Move detailed explanations to `policies/security.md`, lazy-loaded for high-risk operations. | 25 | 1.0 | **25** | Low — rules preserved verbatim, only justifications move | Med |
| **R2** | Consolidate ~6 feedback memories about paste-ready commands into one `feedback_paste_ready_commands.md`. Delete the redundant individual files. | 6 (index) | 1.0 | **6** | None — same rule, fewer references | Low |
| **R3** | Strip MCP Tools table from linear-workflow.md (lines 99-108). `linear-automation` skill provides this. | 10 | 0.85 | **8.5** | Low — table is reference, skill loads schemas | Low |
| **R4** | Compress kinetic MEMORY.md § Implementation Status: enforce 2-sentence-per-entry rule, move historical detail to `decisions-archive.md`, fix stale header. | 30 | 0.5 | **15** | None — historical detail preserved, just relocated | Med |
| **R5** | Move brain/CLAUDE.md sections "OB1 Repo Structure", "PR Standards", "Key Files" to `brain/docs/contributing.md`. | 40 | 0.5 (Brain only) | **20** | Low — those sections are reference, not behavioral | Low |
| **R6** | Execute prior 2026-04-05 R1: archive stale richard-memory entries to richard-memory-archive.md. Includes the inaccurate "collapsed into Builder + Reviewer" claim. | 15 | 0.15 (Richard sessions only) | **2.3** | None — archived, not deleted | Low |
| **R7** | Move dinesh.md "Spawning the Reviewer" prompt template to dinesh-reference.md. | 16 | 0.15 (Dinesh sessions) | **2.4** | Low — reference content, loaded on demand | Low |
| **R8** | Audit project_kinetic_* auto-memory files for staleness (`project_kinetic_framework_review_findings`, `_launch_risks`, `_eval_status`, `_framework_review_prep` — all 2026-03-23). Delete or consolidate to current state. | 4 (index) | 1.0 | **4** | Low — outdated context isn't quality, it's noise | Low |
| **R9** | Operating Norms in CLAUDE.md duplicates 4+ auto-memory feedback entries (paste-ready, cd-paths, no-placeholders). Decide ONE canonical location and reference from the other. | 8 | 1.0 | **8** | None — same guidance, single source | Med |

**Total effective saving if all executed: ~91 lines per average session.**

That's a ~29% reduction against the 316-line shared overhead — without removing any behavioral rule.

### Saving Wins by Effort

**Quick wins (Low effort, ~40 saved per session):**
- R2 (consolidate feedback memories): 6
- R3 (strip MCP table from linear-workflow): 8.5
- R6 (archive richard-memory): 2.3
- R7 (move Reviewer prompt to reference): 2.4
- R8 (audit stale project memories): 4

**High-leverage (Med effort, ~51 saved per session):**
- R1 (compress CLAUDE.md Security): 25
- R4 (compress kinetic MEMORY.md): 15
- R5 (move brain/CLAUDE.md reference content): 20 (Brain only)
- R9 (de-duplicate Operating Norms vs auto-memory): 8

## What's Working Well

- **Lazy-load architecture remains effective.** dinesh-reference, gilfoyle-handoffs, richard-diagnostics, richard-board-scan total ~258 lines kept out of default sessions.
- **conventions.md → policies/ migration landed.** 137 lines removed from shared overhead; replaced by 13 task-specific policies loaded on demand. Net win.
- **Kinetic/CLAUDE.md is exemplary at 8 lines.** This is the right pattern for project CLAUDE.md.
- **Memory file caps holding for most agents.** All under 40 lines except richard-memory (53 — already known overflow, archive pending).

## Open Questions for Brandon

1. **richard-memory.md's "collapsed into Builder + Reviewer" claim** — is the multi-agent system still active, or did the collapse happen and the file naming just didn't catch up? This affects how R6 archives that entry.

2. **Auto-memory consolidation (R9)** — for "paste-ready commands" guidance, should the canonical location be CLAUDE.md Operating Norms (visible to every session by default), or a feedback memory (loads on demand)? Recommend Operating Norms; delete the duplicating feedback memories.

3. **Security section (R1)** — willing to accept compression to ~25 lines if the hard rules are preserved word-for-word and only the explanatory text moves? Or do you want the full 51-line version always present?

4. **Should I create Linear `[Richard]` tickets for the recommendations you approve, or just execute them directly?** Per agent file, Richard can edit policy/agent/CLAUDE.md files with your approval.

## Baselines Updated

| Metric | Prior (Apr 5) | Current (May 24) | Post-Execution | Δ from prior |
|---|---|---|---|---|
| Cross-project shared overhead | 362 | 354 (incl. auto-mem) | **293** (145+97+33+18 user) | **−69** |
| CLAUDE.md | 116 | 153 | **145** | +29 (post-R1) |
| linear-workflow.md | 109 | 108 | **97** | −12 |
| conventions.md | 137 | 0 (migrated) | 0 | -137 |
| Auto-memory MEMORY.md | — | 40 | **33** | −7 |
| `policies/` directory | — | 13 files | **14 files** (added security.md) | +104 lazy |
| Kinetic MEMORY.md | 76 | 81 | **74** | −2 net, ~600+ tokens saved |
| Brain CLAUDE.md | — (didn't exist) | 77 | **35** | new file, −42 from May 24 |
| richard-memory.md | 54 | 53 | **27** | −27 |
| dinesh.md | 162 | 163 | **145** | −17 |

---

## Execution Log — 2026-05-24

All recommendations were executed in the same session per Brandon's direction. Final results vs. estimates:

| # | Estimated saving (per session) | Actual saving | Notes |
|---|---|---|---|
| R1 | 25 lines | **8 lines + ~30% word reduction within preserved rules** | All hard rules kept verbatim per Brandon; only rationale moved to `policies/security.md`. Token reduction larger than line delta. |
| R2 | 6 lines | 6 lines (index reduction) | Consolidated 5 redundant feedback files into `feedback_paste_ready_commands.md`. Old files tombstoned. |
| R3 | 8.5 lines | **11 lines** | MCP Tools table removed; pointer to `linear-automation` skill replaced it. Slightly more than estimate. |
| R4 | 30 lines | **7 lines + ~700 tokens** | Paragraph→bullet compression in Implementation Status. Lines didn't drop much, but token count did — paragraphs were ~870 words, now ~330. |
| R5 | 40 lines | **42 lines** | brain/CLAUDE.md: 77 → 35. Reference content moved to new `brain/docs/contributing.md`. |
| R6 | 15 lines | **26 lines** | richard-memory.md: 53 → 27. 15+ stale entries archived to `richard-memory-archive.md`. |
| R7 | 16 lines | **18 lines** | Dinesh reviewer-prompt template moved to dinesh-reference.md. |
| R8 | 4 lines | 4 lines (index reduction) | 4 stale `project_kinetic_*` memories from 2026-03-23 tombstoned. |
| R9 | 8 lines | 0 lines (absorbed by R2) | Canonical guidance confirmed = CLAUDE.md § Operating Norms. The deduplication is already covered by R2. |

**Net effective reduction per arbitrary agent session (weighted by multipliers): ~42 lines + meaningful token-level reduction inside dense files.**

### Files Created
- `policies/security.md` (104 lines, lazy-loaded)
- `policies/INDEX.md` (added security row)
- `projects/brain/docs/contributing.md` (43 lines, lazy-loaded)
- `~/.claude/.../feedback_paste_ready_commands.md` (22 lines, replaces 5)
- `CLAUDE.md.backup-2026-05-24` (snapshot of 153-line original)

### Tombstones (1-line "SUPERSEDED" pointers)
Auto-memory files no longer in the index: `feedback_commands_not_links`, `feedback_commit_commands`, `feedback_give_paths_directly`, `feedback_always_include_cd`, `feedback_no_placeholders`, `project_kinetic_framework_review_findings`, `project_kinetic_launch_risks`, `project_kinetic_eval_status`, `project_monica_framework_review_prep`. They don't auto-load. Cleanup command lives in [KIN-498](https://linear.app/brandonup/issue/KIN-498).

### Linear
- [KIN-498](https://linear.app/brandonup/issue/KIN-498) — created, all items checked, status: Done.

### Lessons for the next audit
1. **Verbatim-preservation constraints reduce CLAUDE.md savings.** When rules must stay word-for-word, the only compression is in rationale and preamble. The pattern is to MOVE rationale to a lazy-loaded policy and keep CLAUDE.md to rules-only.
2. **Token savings ≠ line savings in dense paragraphs.** Kinetic MEMORY.md was −7 lines but ~−700 tokens because paragraph entries were 100-200 words each. Future audits should measure tokens, not lines.
3. **Tombstones are acceptable when `rm` is hard-blocked.** Files don't auto-load if absent from MEMORY.md index — physical existence doesn't cost tokens. Brandon can clean up at his pace.
