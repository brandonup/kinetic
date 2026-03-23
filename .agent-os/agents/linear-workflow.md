# Linear Workflow — Shared Standards

All agents follow these rules. Agent files add agent-specific sections (when to create issues, handoffs, etc.).

---

## Board

**Kinetic Linear board:** https://linear.app/brandonup/team/KIN

All issues for the Kinetic project live here. Team identifier: `KIN`. Use this URL when linking Brandon to specific tickets.

---

## Skill

**Invoke `linear-automation` once per session, lazily** — only when you're about to make your first Linear call. Do not invoke it as a reflex at session start before you know what you need.

After invoking: read first (`list_*` / `get_*` to look up IDs), then write (`save_issue`, `save_comment`) in batches. See § Token Efficiency for query rules.

---

## Comment Rules

**Keep Linear comments short.** Long comments burn agent context when tickets are read. Detailed findings belong in doc files, not inline.

- **Sign every comment** with your agent name at the end: `— Gilfoyle`, `— Dinesh`, `— Big Head`, `— Jared`, `— Jìan`, or `— Bachman`. Brandon needs to know at a glance who wrote what.
- **Max 5 lines per comment.** Verdict + summary + link to the detailed doc.
- **Reviews, test plans, and handoffs:** Write the full artifact to `reviews/` or `docs/plans/`, then comment with a 1-line summary and a link.
- **Status updates and handoffs:** Verdict, what changed, what's next. No tables or line-by-line breakdowns in the comment.

---

## MCP Tools

| Operation | Tool |
|---|---|
| List / search issues | `list_issues` |
| Get one issue | `get_issue` |
| Create or update issue | `save_issue` (pass `id` to update, omit to create) |
| Add or update comment | `save_comment` (`issueId` required on create) |
| List statuses | `list_issue_statuses` |
| List / create labels | `list_issue_labels`, `create_issue_label` |
| List users | `list_users`, `get_user` (use `"me"` for self) |
| Projects | `list_projects`, `get_project`, `save_project` |
| Cycles | `list_cycles` |

**Never guess IDs** — always look them up first.

---

## Token Efficiency

Linear MCP calls are expensive. Every `list_issues` response loads full issue objects. Follow these rules to minimize overhead.

**1. Tight `list_issues` filters — always.** Never load the full board. Always specify:
- `assignee: "me"` — only your own issues
- `state: "Todo"` (or the specific state you need)
- `limit: 5` — you only need the top items

Note: `list_issues` does not support `orderBy: "priority"` — only `"createdAt"` and `"updatedAt"` are valid. Omit `orderBy` and rely on Linear's default sort (priority) instead.

**2. Skip `get_issue` when the list response is enough.** `list_issues` returns the full description. Only call `get_issue` when you specifically need relations (`blockedBy`/`blocks`) or the description appears truncated.

**3. Get context from files, not ticket comments.** Read review docs from `reviews/`, specs from `docs/`, plans from `docs/plans/`. Ticket comments exist for Brandon's visibility — loading them burns tokens and adds noise. Do not read ticket comments to get working context.

**4. One `list_issues` call per session start.** Do not call `list_issues` multiple times to check different states (e.g., Code Review then Todo). Agents that need to check multiple states (Gilfoyle) should do so in the minimum number of targeted calls their agent file requires.

**5. Write in batches.** After reading, make all writes in a single pass — `save_issue` + `save_comment` together, not interleaved with more reads.

---

## Issue Fields

| Field | `save_issue` param | Notes |
|---|---|---|
| Title | `title` | `[Agent] Short imperative description` |
| Team | `team: "Kinetic"` | Always |
| Project | `project: "Kinetic"` | Always |
| Assignee | `assignee` | Always set — use `"me"` or agent name |
| Priority | `priority: N` | 1=Urgent 2=High 3=Normal 4=Low |
| Status | `state` | Move to `In Progress` before starting, not after |
| Due date | `dueDate: "YYYY-MM-DD"` | Only on `Todo` / `In Progress` — never on `Backlog` |
| Labels | `labels: [...]` | One owner label + one type label |
| Blocked by | `blockedBy: ["KIN-XX"]` | Set on creation — never leave sequencing implicit |
| Blocks | `blocks: ["KIN-XX"]` | Makes downstream impact visible |
| Cycle | `cycle` | Auto-assigned by automation — only set manually for future cycles |
| Parent | `parentId: "KIN-XX"` | For child issues under a tracking epic |
| Description | `description` | What to do, done-when, links to PRD/ADR/spec |
| Estimate | `estimate: N` | 1=half day, 2=full day, 3=two days, 4=three+ days |
| Related to | `relatedTo: ["KIN-XX"]` | Append-only — links related (non-blocking) issues |

**Estimate is required on every `[Dinesh]` and `[Big Head]` implementation ticket before moving to `In Progress`.** Use the scale in the table above. Any ticket estimated at 4 (three+ days) must be split before starting — see Jared's § Prepare Sprint.

### Ticket Scoping

- **Target estimate: 1–2 per ticket.** If you estimate 3+, split before starting.
- **Use parent + subtask structure** for multi-step features. Create a parent ticket (feature-scoped) with subtasks underneath. Report velocity at the parent level.
- **Subtask threshold:** If a task completes in under 2 hours, it should be a subtask of a parent ticket, not a standalone ticket.

---

## Priority

| Value | Level | When |
|---|---|---|
| 1 | Urgent | Blocking the sprint — do this first |
| 2 | High | Critical path this week — slippage delays the sprint |
| 3 | Normal | Standard work — default |
| 4 | Low | Can slip without impact |

---

## Status

`Backlog → Todo → In Progress → Code Review → Done`
`In Progress → Blocked` (dependency or Brandon decision pending)

| Status | Meaning |
|---|---|
| Backlog | Not yet started — either unprioritized or waiting on an upstream deliverable (spec not written, another issue not done). No due date. Use **Blocked** instead when work has started and then hit a wall. |
| Todo | No blockers. Ready to start this sprint. Work has not started. |
| In Progress | Active. Set **before** starting work. |
| Code Review | Implementation complete; awaiting Gilfoyle architecture review before Done. |
| Blocked | Cannot proceed. Set `blockedBy`, comment with reason. |
| Done | Complete. Artifact saved or merged. |
| Canceled | Dropped. Comment with reason before canceling. |

**Key rules:** Never set `In Progress` retroactively. Move to `Code Review` when work is complete and ready for review — the implementer sets it, not the reviewer. **Code Review requires Gilfoyle's signoff only.** Gilfoyle comments "Architecture approved" and moves to `Done`. Jìan does not do per-ticket code review — quality signal comes from integration testing and the eval suite. Move `Blocked` → `In Progress` the moment the blocker resolves. `needs-decision` + `Blocked` = waiting on Brandon. **Backlog ≠ Blocked:** Backlog means work hasn't started yet (upstream dependency or not yet prioritized). Blocked means work started and then hit a wall — always pair with `blockedBy` and a comment explaining why.

**In Progress guard:** Before moving any issue to `In Progress`, check `list_issues` with `state: "In Progress"` for that assignee. If one already exists, the new issue stays in `Todo`. One In Progress per agent — no exceptions. Dinesh and Big Head each track their own In Progress independently.

**Code Review rejection (automated loop):** When Gilfoyle rejects within an automated review loop, the implementation agent (Dinesh or Big Head) fixes inline on the same ticket — no separate fix ticket. Move the issue back to `In Progress`, fix, then move to `Code Review` again. See § Automated Review Loops.

**Code Review rejection (standalone session):** If Gilfoyle reviews in a standalone session (not as a subagent), move the rejected issue to `Blocked` (not `In Progress`). Set `blockedBy` on a new fix ticket. The assignee picks it up after finishing their current In Progress item.

---

## Labels

One owner label + one type label on every issue.

| Label | Owner | Use for |
|---|---|---|
| `product` | Jared | Specs, research, UX decisions |
| `architecture` | Gilfoyle | ADRs, spikes, code reviews, tech debt |
| `implementation` | Dinesh, Big Head | Code, tests, bug fixes |
| `qa` | Jìan | Test plans, evals, quality bugs, performance |
| `needs-decision` | Brandon | Blocked on Brandon's call |
| `Bug` / `Feature` / `Improvement` | Any | Issue type |

---

## Cycles

Cycles are 1-week sprints aligned to the build order. They start on Monday, no cooldown.

**Automation handles assignment.** With cycle automation enabled:
- **Active issues** (Todo) → auto-added to the current cycle
- **Started issues** (In Progress) → auto-added to the current cycle
- **Completed issues** (Done) → auto-added to the current cycle

Agents do not need to manually set the `cycle` field. The automation captures everything that moves through Todo → In Progress → Done during the sprint.

**When to manually set `cycle`:** Only when creating an issue that targets a *future* cycle (not the current one). Use `save_issue` with `cycle` set to the cycle number.

**Carryover:** Incomplete issues at cycle end automatically carry over to the next cycle. Jared flags carryover in the weekly board check.

**Weekly review (Jared):** At each session start, check the current cycle for completion rate, carryover from the previous cycle, and any issues that should be in the cycle but aren't.

---

## Session Start (Default)

When starting a new session:
1. Read agent memory file (`agents/[agent]-memory.md`) and project `MEMORY.md`.
2. Invoke `linear-automation` — once, when you're ready to make your first Linear call.
3. Check for `Todo` issues using tight filters: `assignee: "me"`, `state: "Todo"`, `limit: 5`. Do not load the full board. (`orderBy: "priority"` is not supported — omit it.)
4. Pick the highest-priority item. The list response contains enough to start — skip `get_issue` unless you specifically need `blockedBy`/`blocks` relations or the description is truncated. Move to `In Progress` before starting work. **Never ask Brandon which ticket to pick — always decide autonomously by priority, then dependency order.**
5. If no issues are available, report to Brandon: "No [Agent] work queued — board is empty."

**One at a time:** Only one issue should be `In Progress` at any time. Finish or hand off before picking the next `Todo`.

**Sprint loop — keep going.** After completing a ticket (review approved, issue moved to Done), automatically pick up the next highest-priority `Todo` without asking Brandon. Do not check in between tickets. Keep working through the sprint queue until a stop condition is met.

**Stop conditions — two types:**

**🔴 Blocking (stop in session, output clearly, wait for Brandon's response):**
- **Hard-blocked command needed** — a `git push`, `rm`, or other hard-blocked command is required to continue. Output exactly:
  ```
  ⚡ ACTION REQUIRED
  Command: [exact command to run]
  Reason: [one line — why this is needed]
  Ticket: [KIN-XX]
  ```
  Wait for Brandon to confirm it's done before continuing.
- **⚠️ COMPLEXITY FLAG** — stop, output the flag, wait for Brandon's go/no-go before writing any code.
- **Max review iterations reached** — stop, output a summary of what Gilfoyle or Jìan flagged that remains unresolved. Wait for Brandon's direction.
- **Escalation blocks all remaining work** — if Jared returns `ESCALATE` and no other `Todo` tickets are available to work on, stop and report the blocker to Brandon in session.

**🟡 Non-blocking (post to Linear, keep going):**
- **Jared returns `ESCALATE` but other work exists** — create the `[Decision]` issue, post a comment on it explaining the block, then continue with the next available `Todo`.
- **Sprint queue empty** — post a completion signal on the last completed ticket, then end the session:
  ```
  🏁 Sprint queue empty.
  Completed: [KIN-XX, KIN-YY, KIN-ZZ]
  Pending Brandon action: [list any ACTION REQUIRED items posted earlier, or "none"]
  — [Agent name]
  ```

Agent files override specific steps (e.g., Gilfoyle checks Code Review before Todo, Dinesh states "Security layers active" first).

---

## Automated Review Loops

When an agent finishes work that requires review, the review happens **inline in the same session** using the Agent tool — no manual handoff to Brandon required.

### How It Works

1. **Dinesh or Big Head finishes implementation** → moves ticket to `Code Review` → spawns Gilfoyle subagent.
2. **Gilfoyle subagent reviews** → writes review doc, updates Linear.
   - **Approved:** Moves ticket to `Done`. Loop ends.
   - **Changes requested:** Returns findings to the implementation agent.
3. **Implementation agent fixes** → moves ticket to `In Progress` while fixing → moves back to `Code Review` → re-spawns Gilfoyle subagent.
4. **Loop repeats** until approved or max iterations reached.
5. **After Gilfoyle approval:** If a Jìan test plan or eval suite exists for this feature, the implementation agent spawns Jìan subagent.
6. **Jìan tests** → if bugs found, the implementation agent fixes → Jìan retests.

### Rules

- **Max iterations:** 3 for Gilfoyle review, 2 for Jìan QA. If not resolved, stop and report to Brandon.
- **Estimate gate:** Before spawning the Gilfoyle subagent, verify the ticket has an estimate. If missing, set one now (`save_issue` with `estimate`) and note it in the handoff comment. No review without an estimate.
- **Handoff comment gate:** Before spawning the Gilfoyle subagent, verify a handoff comment has been posted (summary + test command + test count + agent signature). If not posted, post it now. No review without a handoff comment.
- **Linear status tracks real state:** `Code Review` during Gilfoyle review, `In Progress` during Dinesh fixes, `Done` on final approval.
- **Review artifacts still land in `reviews/`** — subagents write the same docs as standalone sessions.
- **One loop at a time.** Finish the current ticket's review loop before starting the next ticket.
- **Subagent sessions are disposable.** The subagent reviews one ticket and exits. No carryover between review loops.
- **Background subagents cannot post Linear comments** — the permission modal has no user present. Always instruct review subagents to return the comment text in their result; post it yourself from the parent agent.

### Subagent Prompt Template

When spawning a review subagent, use `Agent` tool with `subagent_type: "general-purpose"`. Include in the prompt:

1. Which agent persona to load (`agents/gilfoyle.md` or `agents/jian.md`)
2. The ticket ID and what was implemented
3. File paths or package directory to review
4. Instruction to write findings to the correct location (`reviews/` or test results)
5. Instruction to update the Linear ticket (invoke `linear-automation` first)
6. Instruction to return a structured verdict — see agent-specific sections for exact format

---

## Question Routing

When an agent hits a question mid-session, **spawn a Jared subagent before escalating to Brandon.** Jared filters questions — answering what he can from specs, MEMORY.md, and prior decisions, and only escalating what truly needs the CEO.

### How It Works

1. Agent hits a question that would otherwise block progress.
2. **Spawn Jared subagent** using the Agent tool (`subagent_type: "general-purpose"`, `model: "haiku"`).
3. Jared reads the question, checks MEMORY.md + specs + prior decisions.
   - **If Jared can answer:** Returns the answer. Agent continues working. No interruption to Brandon.
   - **If Jared cannot answer:** Returns `ESCALATE: [1-line question]`. The calling agent creates a `[Decision]` issue for Brandon (see § [Decision] Issues below).

### What Jared Can Decide

- Spec intent and feature scope ("does the PRD mean X or Y?")
- Priority between tickets ("which of these should I do first?")
- PRD/ADR interpretation ("does this match the spec?")
- Which agent owns a task ("is this Gilfoyle or Dinesh work?")
- Process questions ("should I break this into subtasks?")
- Test scope and acceptance criteria ("is this edge case in scope?")

### What Jared Escalates to Brandon

- Budget, timeline, or resource changes
- Scope cuts or new features not in the roadmap
- Strategic direction or product vision
- Anything with revenue, customer, or partnership impact
- Disagreements between agents that Jared can't resolve

### Subagent Prompt Template

```
You are Jared. Read `agents/jared.md` for your persona.
Read `agents/jared-memory.md` for cross-project lessons. Read `projects/kinetic/MEMORY.md` for project context.

[Agent name] is working on [KIN-XX] and has a question:
[Paste the question]

Check MEMORY.md, the relevant spec, and prior decisions. If you can answer confidently, return:
ANSWERED: [your answer, 1-3 sentences]

If this requires Brandon's call, return:
ESCALATE: [1-line question for Brandon]
```

---

## [Decision] Issues

Use `[Decision]` issues when an agent cannot proceed without Brandon's explicit call. They are not work items — they are questions with consequences.

**When to create one:** A design or architecture choice would unblock one or more `Blocked` issues, and agents have already surfaced their recommended option. **Always route through Jared first** (see § Question Routing) — only create a `[Decision]` issue if Jared returns `ESCALATE`.

**Fields:**

| Field | Value |
|---|---|
| Title | `[Decision] One-sentence question` |
| State | `Todo` (open) → `Done` (resolved) |
| Labels | `needs-decision` + relevant type label |
| Assignee | Brandon |
| Description | See format below |
| `blocks` | All issues waiting on this decision |

**Description format:**

```
## Question
One clear sentence.

## Context
Why this matters and what happens either way (2–4 sentences max).

## Options
- **Option A:** What it means, tradeoff.
- **Option B:** What it means, tradeoff.

## Recommendation
Which option the agent recommends and why (one sentence).
```

**Resolution:** When Brandon decides, add a comment with the chosen option and rationale, move to `Done`, then unblock downstream issues.
