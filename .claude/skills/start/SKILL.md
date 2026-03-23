---
name: start
description: Start a Kinetic work session. Reads project memory, checks Linear for in-progress tickets, and gives a clear briefing on what to work on next.
---

You are starting a Kinetic development session. Follow these steps exactly.

## 1. Read project memory

Read `MEMORY.md` in full. Note:
- Current sprint and ticket range
- Implementation status (what's shipped, what's pending)
- Any pending commits from Brandon

## 2. Check Linear for in-progress tickets

Use the Linear MCP tool to list all in-progress issues for the KIN team:
- `state: "in progress"`, `team: "KIN"`

For each in-progress ticket, note the ticket ID, title, and assignee.

## 3. Check git status

Run `git log --oneline -10` and `git status` to see recent commits and any uncommitted changes on the current branch.

## 4. Deliver a session briefing

Write a concise briefing in this format:

---
**Kinetic — Session Start**

**Sprint:** [current sprint name and ticket range]
**Branch:** [current branch]

**In Progress:**
- [KIN-XXX] [Title] — [Assignee]
- ...

**Recent commits:**
- [short summary of last few commits]

**Pending / blockers:**
- [anything from MEMORY.md about pending commits, blockers, or open questions relevant to in-progress work]

**Suggested next action:**
[One sentence on the most logical thing to work on given the above]
---

Be concise. Don't summarize the entire MEMORY.md — only what's relevant to the current sprint and in-progress work.
