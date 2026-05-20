# Context Load Audit — 2026-04-04

**Scope:** All session-loaded files across active agents (Dinesh, Gilfoyle, Jared, Richard, Monica). Comparison against 2026-03-28 baseline.

---

## Scope

Lines measured per agent session = shared overhead + agent file + agent memory file. Does not include lazy-loaded referenced files (correct behavior). Auto-memory MEMORY.md (28 lines, system-injected) counted separately — not agent-controlled.

---

## Measurements

### Shared Overhead (loaded every agent, every session)

| File | Lines | vs. Baseline |
|---|---|---|
| `CLAUDE.md` | 115 | — |
| `conventions.md` | 181 | — |
| `agents/linear-workflow.md` | 108 | — |
| `projects/kinetic/MEMORY.md` | 73 | ↓ from 205 (−132 lines, **−64%**) |
| **Shared total** | **477** | **↓ from ~930 (−453 lines, −49%)** |

### Per-Agent Session Load

| Agent | Agent file | Memory file | Agent subtotal | Session total | vs. 2026-03-28 baseline |
|---|---|---|---|---|---|
| Dinesh | 199 | 28 | 227 | **704** | ↓ from 1,202 (−41%) |
| Gilfoyle | 118 | 20 | 138 | **615** | ↓ from 1,104 (−44%) |
| Jared | 143 | 27 | 170 | **647** | ↓ from 1,191 (−46%) |
| Richard | 112 | 79 | 191 | **668** | ↓ from 1,162 (−43%) |
| Monica | 89 | 17 | 106 | **583** | no prior baseline |

### Correctly Lazy-Loaded (not in every session — good)

| File | Lines | Loaded when |
|---|---|---|
| `agents/richard-board-scan.md` | 19 | Board health scan only |
| `agents/richard-diagnostics.md` | 104 | Diagnostic report sessions |
| `agents/gilfoyle-handoffs.md` | 77 | Gilfoyle session start |
| `agents/reviewer.md` | 76 | Subagent spawn only |

---

## Key Findings

### F1 — Massive improvement since 2026-03-28 (no action required)

Session load dropped 41–46% across all agents. Root causes of improvement:
- **MEMORY.md trimmed 64%** (205 → 73 lines) from prior archival work
- **Agent consolidation** eliminated Big Head, Jìan, Bachman — 3 fewer per-session agent contexts, plus eliminated per-sprint sub-agent spawning overhead

No action required. Baseline recorded.

### F2 — `conventions.md` carries ~67 lines of lazy-load candidates (medium impact)

At 181 lines, `conventions.md` is the largest shared overhead file — loaded by every agent, every session. Three sections are situational:

| Section | Lines | When actually needed |
|---|---|---|
| § Environments (table + config files + migration flow) | 30 | Only when Dinesh/Gilfoyle touch env setup or migrations |
| § GenAI-Specific | 17 | Only when implementing LLM features |
| § Memory Staleness Prevention | 20 | Only when agents write memory (session end) |

Estimated savings: **~67 lines** removable from the always-loaded file, moved to a `conventions-reference.md` lazy-loaded on demand.

### F3 — `dinesh.md` carries ~49 lines of lookup content (medium impact)

At 199 lines, Dinesh's agent file is the largest. Three sections are reference lookups, not flow instructions:

| Section | Lines | When actually needed |
|---|---|---|
| § Known Gotchas | 27 | When hitting a specific bug — lookup, not upfront read |
| § Defect Logging (format + categories) | 13 | Only when a Critical finding is logged |
| § Documentation Updates (checklist) | 9 | Only at end of implementation |

These are correctly structured as references but are loaded every Dinesh session regardless. Moving to `dinesh-reference.md` would save **~49 lines** from Dinesh's agent file.

### F4 — `richard-memory.md` growing and overdue for archival (low impact)

At 79 lines, richard-memory.md is the largest memory file by 2.8×. Several entries predate the agent consolidation (2026-03-28) and reference archived agents (Big Head, Jìan, Bachman). These entries are retained for trend comparison per prior note in the file, but they add load every session.

Estimated archival candidates: entries prior to 2026-03-22 (W9 baselines) → ~25 lines → `richard-memory-archive.md`.

---

## Recommendations (ranked by lines saved)

| # | Action | Est. lines saved | Impact | Effort |
|---|---|---|---|---|
| R1 | Extract lazy-load sections from `conventions.md` → `conventions-reference.md` | ~67 lines / session | High (shared overhead — affects every agent) | Low |
| R2 | Extract lookup sections from `dinesh.md` → `dinesh-reference.md` | ~49 lines / Dinesh session | Medium | Low |
| R3 | Archive pre-2026-03-22 entries in `richard-memory.md` → `richard-memory-archive.md` | ~25 lines / Richard session | Low | Low |

**R1 is highest leverage** — shared overhead is multiplied across every agent and every subagent spawn.

---

## What's Working Well

- **MEMORY.md discipline** is working: 73 lines is well within healthy range, and the 2-sentence rule is holding
- **Lazy loading pattern** is correctly applied to all Richard referenced files and Gilfoyle handoffs
- **Agent file sizes** are lean across the board (89–199 lines), well below the 2026-03-28 bloat levels
- **Reviewer subagent** stays out of session load (76 lines, spawned only when needed)

---

## Open Questions

- R1 requires a decision on naming convention for the extracted file. Recommend `conventions-reference.md` but Brandon should confirm.
- R3 archival: should archived entries be deleted outright or moved? Moving preserves historical record; deleting keeps the repo clean.

---

## Baselines Updated

| File | New baseline |
|---|---|
| Shared overhead | 477 lines |
| Dinesh session total | 704 lines |
| Gilfoyle session total | 615 lines |
| Jared session total | 647 lines |
| Richard session total | 668 lines |
| Monica session total | 583 lines |
| MEMORY.md | 73 lines |

_Prior baselines (2026-03-28): Dinesh 1,202 / Gilfoyle 1,104 / Jared 1,191 / Richard 1,162 / Shared ~930_
