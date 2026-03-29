# KIN-364 — Agents List Page Frontend Gap Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-25
**Verdict:** Architecture approved. Ready for Dinesh.
**Findings:** 0 Critical, 0 Important, 3 Notes

---

## 1. Current State Audit

### `/agents` list page — Placeholder confirmed

`packages/web/app/(app)/agents/page.tsx` — 10 lines. Static text: "Your agents will appear here. Coming in Sprint 4." No API calls, no components. Full replacement needed.

### `/agents/:id` Agent Profile — Functional

`packages/web/app/(app)/agents/[id]/page.tsx` — all 4 tabs render:
- **Instructions:** displays name + instructions (read-only view). Works.
- **Knowledge Base:** wired to `KnowledgeBaseTab` component. Works.
- **Framework Library:** wired to `FrameworkLibraryTab` component. Full CRUD. Works.
- **Settings:** placeholder ("Coming soon."). Expected — settings are Sprint 8+ scope.

Owner detection works via `GET /api/v1/profile` → compare `owner_id`. No tab-level bugs found.

### API — Complete

`GET /api/v1/agents` returns owned + public agents, merged and deduplicated. `POST /api/v1/agents` creates with name, instructions, type, visibility, mcp_enabled. Both endpoints are tested (`test_agents.py`). No gaps.

---

## 2. AgentSelector.tsx — Does Not Exist

The ticket description references `AgentSelector.tsx` as an existing component with agent-fetching logic to extract. **This component does not exist.** Searched all `.tsx` files in `packages/web/` — no match.

The closest component is `AgentSwitchMarker.tsx`, which is purely a visual marker inserted between chat messages when `agent_definition_id` changes. It has no data-fetching logic.

**Impact on KIN-365:** The "extract shared hook" guidance in the ticket is moot — there's nothing to extract from. Dinesh should create `useAgents()` from scratch. The hook should call `GET /api/v1/agents` and split the response into `myAgents` (where `owner_id === currentUserId`) and `publicAgents` (the rest). This hook will be reusable when the agent selector dropdown is built for the chat UI later.

---

## 3. Create Agent Flow — Recommendation

**Modal, not a dedicated route.**

Rationale:
- Spec says creation requires only name + type + visibility (3 fields). That's modal-sized.
- After creation, user lands on `/agents/:id` (Instructions tab) to set the system prompt. The profile page already handles editing.
- A `/agents/new` route adds a router entry, a back button, and breadcrumb handling for something that takes 5 seconds to fill out.

**Create flow spec for Dinesh:**
1. "New Agent" button in page header.
2. Modal: name (required, ≤100 chars), type (`custom` / `thought_leader`), visibility (`private` default).
3. `instructions` should be set to empty string `""` (the field is required by the API). The user fills it in on the profile page.
4. On submit: `POST /api/v1/agents` → on success, `router.push(/agents/${newAgent.id})`.
5. Validation: name required. Surface 422 errors (name uniqueness) as inline field error on the name input.

**Note:** The API currently requires `instructions` as a non-empty string on `CreateAgentRequest`. The spec (§2) says instructions must be non-empty before the agent can be *used* or set to *public* — but creation should allow empty instructions so the user can fill them in on the profile page. **Dinesh should update `CreateAgentRequest` to make `instructions` optional with default `""`, and only enforce non-empty on visibility=public.** This is a 1-line Pydantic change + the existing validation already handles the public case.

---

## 4. Empty State

Spec (§5) says agents without valid instructions are "shown greyed out and cannot be invoked." For the list page empty state:

- **My Agents section, no agents:** "You haven't created any agents yet." + "Create your first agent" CTA button (opens the create modal).
- **Public Agents section, no public agents:** "No public agents available yet." No CTA.

---

## 5. Notes (informational, not blocking)

| # | Note | Detail |
|---|---|---|
| N1 | Settings tab placeholder | Profile page Settings tab shows "Coming soon." — not in scope for KIN-365, just noting it's still a placeholder. |
| N2 | Agent selector for chat UI | The `useAgents()` hook Dinesh builds should be designed for reuse by the eventual chat-side agent selector (spec §5). Keep the hook in `lib/hooks/useAgents.ts`, not co-located with the list page. |
| N3 | `instructions` field optionality | The `CreateAgentRequest` Pydantic model requires `instructions: str`. Dinesh needs to change this to `instructions: str = ""` so the create modal can skip instructions. Existing public-visibility guard already rejects empty instructions for public agents. |

---

## Verdict

**Architecture approved.** No blocking issues. The scope is confirmed: list page + create modal, one Dinesh ticket. KIN-365 is correctly scoped and ready to move to Todo.

Constraints for Dinesh:
1. Create `useAgents()` hook from scratch in `lib/hooks/` — no existing component to extract from.
2. Create flow uses a modal, not a route.
3. Update `CreateAgentRequest.instructions` to default `""`.
4. Split API response into My Agents / Public Agents client-side (API returns a merged list).
