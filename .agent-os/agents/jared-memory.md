# Jared — Cross-Project Memory

Transferable product lessons learned across projects. Updated when Brandon says "remember this" or "add that to your memory."

---

<!-- Entries format: - [YYYY-MM-DD] [project] Lesson learned -->

- 2026-03-17 [Kinetic] Sprint tracking uses **project milestones** in Linear, not cycles and not dates. Never ask about sprint dates or reference cycle numbers. Milestones are the canonical sprint container — check `projectMilestone` field on issues to determine what sprint something belongs to.
- 2026-03-16 [Kinetic] Single-source-of-truth beats duplication in multi-agent systems. When multiple agents share instructions, one canonical file + agent-specific additions eliminates drift. Duplicated instructions always diverge.
- 2026-03-16 [Kinetic] Token budget is architectural. Before adding content to any file loaded every session, ask: "does this actually change what I'd do?" Templates and best practices already internalized are waste. Cut them.
- 2026-03-16 [Kinetic] Handoffs are the highest-failure point in multi-agent work. Design them explicitly: comment on downstream issue with handoff summary + "Ready to start", then move Backlog→Todo as a single step. Implicit handoffs stall invisibly.
- 2026-03-16 [Kinetic] A spec with open questions isn't done — it's a blocked dependency. Surface the exact decisions needed, get answers, mark Approved, then unblock downstream. Shipping ambiguity forces implementers to guess.
- 2026-03-16 [General] Adversarial eval cases (no-context, conflicting sources, out-of-scope) require 100% pass threshold, not the same 80% as functional cases. A system that confidently invents answers when it doesn't know is worse than a mediocre system.
- 2026-03-16 [Kinetic] Minimum viable means asking "what are the 3 things users actually need to do their job here?" Once asked honestly, most MV specs shed 60% of their scope immediately. Dashboard went 9 widgets → 3 active + 4 placeholders.
- 2026-03-16 [General] MEMORY.md + retrospective at session end is compound interest. Every skipped session-end ritual is a tax on the next session. The last 10 minutes are worth more than the first 10 — they're what the next session starts from.
- 2026-03-15 [Kinetic] Lock the domain model before writing any doc. Roles, key entities, and relationships should be defined in a one-page model first. Prevents bulk renames — the CEO→Business Leader rename touched 9 files, 183 references.
- 2026-03-15 [Kinetic] Define permissions as an action table (who can do what), not prose, before writing any persona section.
- 2026-03-15 [Kinetic] Establish source-of-truth rules upfront: product summary owns what/why, PRD owns how/acceptance criteria, design docs own flow/edge cases. Update order when a decision changes: product summary → PRD → design docs. Never cross-file edit until source-of-truth doc is settled.
- 2026-03-15 [Kinetic] Surface all clarifying questions before any edit touching more than 2 files. Mid-edit misunderstandings are expensive.
- 2026-03-15 [Kinetic] On shared resources, ask "whose scope is this — the system's or the user's?" early. This question would have settled the Drive ingestion design in session one instead of three revisions across two sessions.
- 2026-03-16 [General] CLAUDE.md optimization test: "Does every agent need this before they start working?" If no, move to a skill. Security rules pass (unconditional). Linear naming passes (team norm). Plugin install instructions fail (one-time, dead weight). Session-end routing logic fails (retrospective skill handles it).
