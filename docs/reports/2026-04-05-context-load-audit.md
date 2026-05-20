## Context Load Audit — 2026-04-05

### Scope

Cross-project audit of all files loaded into agent sessions. Triggered by upcoming Brain project launch — measuring the inherited overhead every Brain session will carry from day one. Compared against the 2026-04-04 baseline in `richard-memory.md`.

### Line Counts

**Cross-Project Shared Overhead (loaded by every agent, every session, regardless of project):**

| File | Lines | Change from Apr 4 |
|---|---|---|
| CLAUDE.md | 116 | +1 |
| conventions.md | 137 | **-44** (was 181) |
| linear-workflow.md | 109 | +1 |
| **Cross-project subtotal** | **362** | **-42** |

**Project-Specific Overhead:**

| Project | MEMORY.md Lines |
|---|---|
| Kinetic | 76 (was 73, +3) |
| Brain (projected) | ~20 (doesn't exist yet) |

**Kinetic total shared:** 438 lines | **Brain total shared (projected):** ~382 lines

**Per-Agent Files:**

| Agent | Agent File | Memory File | Agent Subtotal |
|---|---|---|---|
| Dinesh | 162 | 29 | 191 |
| Gilfoyle | 119 | 22 | 141 |
| Jared | 144 | 28 | 172 |
| Richard | 113 | 54 | 167 |
| Monica | 90 | 18 | 108 |
| Reviewer (subagent) | 70 | — | 70 |

**Session Totals — Kinetic:**

| Agent | Total | Prior (Apr 4) | Change |
|---|---|---|---|
| Dinesh | 629 | 704 | -75 (-11%) |
| Gilfoyle | 579 | 615 | -36 (-6%) |
| Jared | 610 | 647 | -37 (-6%) |
| Richard | 605 | 668 | -63 (-9%) |
| Monica | 546 | 583 | -37 (-6%) |

**Session Totals — Brain (projected, once MEMORY.md created):**

| Agent | Projected Total |
|---|---|
| Dinesh | 573 |
| Gilfoyle | 523 |
| Jared | 554 |
| Richard | 549 |
| Monica | 490 |

**Lazy-Loaded Reference Files (not in default session load):**

| File | Lines | Loaded by |
|---|---|---|
| dinesh-reference.md | 58 | Dinesh (on demand) |
| conventions-reference.md | 75 | Any agent (on demand) |
| gilfoyle-handoffs.md | 78 | Gilfoyle (on demand) |
| richard-diagnostics.md | 105 | Richard (on demand) |
| richard-board-scan.md | 20 | Richard (on demand) |
| **Total kept out of sessions** | **336** | |

### Key Findings

1. **All agents down 6-11% from prior audit.** conventions.md extraction (R1 from Apr 4 audit) accounts for most of the shared overhead reduction (-44 lines). No file has grown beyond its prior cap. System is trending leaner.

2. **Brain sessions will start at 490-573 lines — 10-15% lighter than current Kinetic sessions.** The difference is the MEMORY.md: Kinetic's is 76 lines (accumulated over 3+ weeks of development); Brain's will start at ~20. This is the right position — lean at launch, grows as real decisions accumulate.

3. **Agent memory files are cross-project — Kinetic lessons load in Brain sessions.** dinesh-memory.md (29 lines) contains Kinetic-specific gotchas (Supabase OAuth, Vercel config, MCP patterns). When Dinesh works on Brain, these entries are noise unless Brain uses the same stack. No filtering mechanism exists. At current sizes (18-54 lines) this is acceptable. At 80+ lines per memory file, it becomes a tax on Brain sessions.

4. **richard-memory.md is the largest agent memory file at 54 lines.** Contains Sprint 1/2 baselines and stale ticket recommendations from March that no longer affect behavior. 15+ lines are archivable.

5. **conventions.md still has ~19 implementation-only lines** (§Python Style, §TypeScript Style, §Testing, §API Design) that Richard, Monica, and Jared never reference. Low-priority since the file is already lean at 137.

6. **Kinetic MEMORY.md has 2 stale entries:** "Known issue" (L7/L8/L9 bug, 2026-03-30) and "Pending commits" (old commit scripts). Both should be investigated and cleaned.

### Recommendations

| # | Recommendation | Lines Saved | Effort | Affected Files |
|---|---|---|---|---|
| R1 | Archive stale richard-memory.md entries (Sprint 1/2 baselines, stale ticket recommendations) to richard-memory-archive.md | 15 | Low | richard-memory.md, richard-memory-archive.md |
| R2 | Clean kinetic MEMORY.md: investigate L7/L8/L9 bug status, remove "Pending commits", compress historical deployment details | 8-10 | Low | projects/kinetic/MEMORY.md |
| R3 | Set memory file growth cap: 40 lines per agent memory file. Archive to `{agent}-memory-archive.md` when exceeded. Add to conventions.md § MEMORY.md Entry Rules | 0 (preventive) | Low | conventions.md |
| R4 | Move conventions.md §Python/§TypeScript/§Testing/§API to conventions-reference.md | 19 (×3 agents) | Low | conventions.md, conventions-reference.md |

R1-R3 are recommended before Brain launch. R4 is optional — diminishing returns at current file sizes.

### What's Working Well

- **Lazy-load architecture is effective.** 336 lines of reference content stay out of default sessions. dinesh-reference.md, gilfoyle-handoffs.md, richard-diagnostics.md, and richard-board-scan.md are all correctly separated.
- **conventions.md extraction from prior audit landed.** Down 44 lines from the R1 recommendation. conventions-reference.md is doing its job.
- **Agent files are lean.** All between 70-162 lines. No file has runaway growth. The largest (dinesh.md at 162) is justified — it carries the most procedural content (verification checklist, review tiering, bug fix mode).
- **Project-agnostic refactor (today) keeps shared overhead constant.** The `[project]` placeholder changes didn't add lines — they replaced hardcoded paths 1:1.

### Open Questions for Brandon

1. **L7/L8/L9 bug (kinetic MEMORY.md line 49):** Is this resolved? If yes, remove the entry. If no, it should have a Linear ticket.
2. **"Pending commits" (kinetic MEMORY.md line 53):** Are the commit scripts at `packages/api/commit_kin3XX.sh` and `/private/tmp/claude-501/` still needed? If not, this line can be removed.
3. **Memory file cap policy (R3):** Should the 40-line cap be a hard rule in conventions.md, or a guideline agents enforce at session-end retrospective?

### Baselines Updated

| Metric | Prior (Apr 4) | Current (Apr 5) |
|---|---|---|
| Cross-project shared overhead | 477 lines | 438 lines (-8%) |
| Dinesh session total | 704 | 629 (-11%) |
| Gilfoyle session total | 615 | 579 (-6%) |
| Jared session total | 647 | 610 (-6%) |
| Richard session total | 668 | 605 (-9%) |
| Monica session total | 583 | 546 (-6%) |
| conventions.md | 181 | 137 (-24%) |
| kinetic MEMORY.md | 73 | 76 (+4%) |
| Lazy-loaded reference content | — | 336 lines (new baseline) |
