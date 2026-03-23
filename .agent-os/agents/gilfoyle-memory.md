# Gilfoyle — Cross-Project Memory

Transferable technical lessons learned across projects. Updated when Brandon says "remember this" or "add that to your memory."

---

<!-- Entries format: - [YYYY-MM-DD] [project] Lesson learned -->

- 2026-03-19 — **Sprint-level meta-review tickets catch cross-session gaps.** KIN-193 was moved to Done by a background fix agent but never got a formal Gilfoyle re-review (context compacted). KIN-196 (W10 meta-review) caught it. Always create one umbrella review ticket per sprint week.
- 2026-03-18 — **Verify ticket claims about missing infrastructure before creating it.** KIN-191 said "zero test files in packages/app/" — directory was actually `packages/web/` with 52 test files, Vitest config, and RTL already installed. Checking first saved a full spike.
- 2026-03-18 — **Mark stale/duplicate tickets immediately when found during board scan.** Catching KIN-186 (dup of KIN-185) and KIN-126 (dup of KIN-180) prevents future sessions from picking up dead work.
- 2026-03-17 — **Never ask "want me to pick up X next?" — follow the workflow.** Code Review first, then Todo by priority. The session protocol is deterministic; asking breaks autonomy and wastes Brandon's time. Got corrected once — don't repeat.
- 2026-03-17 — **Cross-reference inline DDL against the canonical schema during code review.** Specs written early may define `CREATE TABLE` statements that diverge from `db-schema-spec.md` (different table names, column names, constraints). Test plans that inherit these propagate the error to implementation. Always check table references against the single-source schema spec.

