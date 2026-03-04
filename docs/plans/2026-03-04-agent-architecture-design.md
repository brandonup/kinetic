# Kinetic Agent Architecture — Design Document

**Date:** March 2026
**Status:** Approved
**Author:** Brandon Upchurch

---

## Overview

Kinetic uses autonomous agents to eliminate manual work across four categories: client-facing delivery, practice operations, knowledge & learning, and relationship management. Agents are multi-step AI workflows that run without being asked — triggered by events, schedules, or on-demand.

All agents share the same infrastructure: Supabase Edge Functions (Deno runtime), Anthropic API with tool use, and the Kinetic Supabase database. No separate orchestration layer is needed.

---

## Architecture Pattern

Every agent follows the same pattern:

1. **Trigger** — event (meeting logged), cron schedule, or on-demand API call
2. **Context fetch** — agent reads relevant data from Supabase (contacts, meetings, memory, knowledge)
3. **Tool-use loop** — Anthropic Claude executes a sequence of tool calls to complete the work
4. **Write back** — agent writes results back to Supabase (updates records, creates new items, appends to memory)
5. **Notify** — agent sends a Slack message confirming what was done

Agents use Anthropic's tool use API (`tool_use` content blocks) rather than a fixed pipeline. This means the agent can branch, retry, and decide sequence based on what it finds — not just execute a hardcoded script.

---

## Agent Inventory

### Tier 1 — Ship with Phase 2

| # | Agent | Trigger | Output |
|---|-------|---------|--------|
| 13 | Post-Meeting Agent | Meeting logged | Summary, action items, thank-you draft, follow-ups, memory update, knowledge relevance links, cross-client pattern flags |
| 14 | Morning Briefing Agent | Daily cron (8am) | Slack DM with today's meetings + prep briefs, overdue follow-ups, relevant new knowledge |
| 15 | Pre-Meeting Research Agent | Cron every 30min (checks for meetings in 2 hours) | Recent company news appended to prep brief; Slack notification |

### Tier 2 — Phase 3 (Month 2-3)

| # | Agent | Trigger | Output |
|---|-------|---------|--------|
| 25 | Knowledge Relevance Agent | Knowledge item ingested | Relevance flags linked to active client records |
| 26 | Relationship Health Agent | Weekly cron | Dormancy scores, re-engagement drafts queued |
| 27 | Recommendation Engine Agent | On-demand (client dashboard) | Structured recommendation doc from knowledge + web |
| 28 | Deliverable Drafting Agent | On-demand (post-meeting) | First-draft deliverable (deck outline, action plan, recommendations doc) |
| 29 | Client Check-In Agent | Weekly cron per active client | Personalized check-in draft with progress references |
| 30 | Pipeline Pulse Agent | Weekly cron | Stale deal flags + prioritized pipeline action list → Slack |
| 31 | Engagement Wrap-Up Agent | Engagement closed | After-action review, practice memory updated, case study outline |
| 32 | AI Landscape Monitor Agent | Daily/weekly cron | New knowledge items auto-ingested from AI news search |
| 33 | Knowledge Gap Agent | Pre-meeting or new pain point | Study list: what you don't know about a topic |
| 34 | Stakeholder Map Agent | After 3+ client meetings | Stakeholder map with roles and engagement gaps |
| 35 | Risk & Blocker Agent | Weekly cron | Watch list of at-risk clients + suggested mitigations → Slack |
| 36 | Follow-Up Quality Agent | On-demand (pre-send review) | Draft improvements flagged with specific suggestions |

### Tier 3 — Phase 4 (Month 4+)

| # | Agent | Trigger | Output |
|---|-------|---------|--------|
| 44 | Revenue Snapshot Agent | Weekly cron | Pipeline value, hours logged, revenue, utilization → Slack |
| 45 | Synthesis Agent | On-demand or weekly cron | Consolidated "state of knowledge" summary per topic |

### Parking Lot

| Agent | Notes |
|-------|-------|
| Content Opportunity Agent | Turns practice patterns into thought leadership drafts — deprioritize until clients are active |

---

## Shared Infrastructure

**Runtime:** Supabase Edge Functions (Deno)
**LLM:** Anthropic Claude (`claude-sonnet-4-5-20250929` — fast and cheap enough for agent loops; upgrade to newer model versions as released)
**Shared prompt:** All agents include the `INTELLIGENCE_LAYER_PROMPT` in their system prompt, instructing generative questioning, synthesis compression, and perspective awareness in every output.

**Tools available to all agents:**
- `search_knowledge` — semantic search across knowledge base
- `read_client_memory` / `write_client_memory` — client-level memory CRUD (includes assumption/hypothesis types)
- `read_practice_memory` / `write_practice_memory` — practice-level memory CRUD (includes pattern_observed/drift_detected types)
- `get_contact` — fetch contact profile
- `get_meetings` — fetch meeting history for a contact
- `get_follow_ups` — fetch pending follow-ups
- `create_follow_up` — create a new follow-up record
- `update_meeting` — write agent results back to a meeting record
- `write_pattern` — create or reinforce a pattern in the `patterns` table (Intelligence Layer)
- `get_assumptions` — fetch tracked assumptions for a client (Intelligence Layer)
- `web_search` — search the web (used by Pre-Meeting Research, AI Landscape Monitor)
- `send_slack` — send a DM or channel message

**Cron schedule (Supabase pg_cron):**
- Every 30 min — Pre-Meeting Research Agent (checks for meetings in 2 hours)
- 8:00am daily — Morning Briefing Agent
- Sunday 7:00pm — Relationship Health Agent, Pipeline Pulse Agent, Risk & Blocker Agent, Client Check-In Agents
- 6:00am daily — AI Landscape Monitor Agent

---

## Intelligence Layer Agent Behaviors

Every Tier 1 agent includes specific Intelligence Layer steps:

**Post-Meeting Agent — 3 additional steps:**
1. Extract assumptions stated or implied in meeting → store as client_memory type `assumption`
2. Identify what was NOT discussed relative to client goals → include in summary as "What This Conversation Didn't Address"
3. When cross-client pattern found, write to `patterns` table with evidence references

**Morning Briefing Agent — 3 additional sections:**
1. Per meeting: "One Question Worth Asking" (Generative Questioning)
2. "Assumption to Revisit Today" — pick one tracked assumption with contradicting evidence (Intellectual Honesty)
3. "Gradual Shift Alert" — if drift_detected for any client in last 7 days (Temporal Intelligence)

**Pre-Meeting Research Agent — 1 additional step:**
1. After finding company news: "How this news might affect what [Contact] cares about" grounded in client memory (Perspective Shifting)

---

## Error Handling

- All agents use **partial completion**: if one tool call fails, the agent logs the error and continues remaining steps
- Agent run results are stored in an `agent_runs` table: `agent_name`, `trigger`, `status`, `steps_completed`, `errors`, `created_at`
- Slack notifications include error counts: "Post-Meeting Agent complete — 9/10 steps succeeded. 1 error logged."

---

## Data Model Addition

**agent_runs**
- `id` (uuid, PK)
- `agent_name` (text)
- `trigger_type` (enum: "event", "cron", "on_demand")
- `trigger_ref` (text, nullable — e.g., meeting_id or contact_id that triggered the agent)
- `status` (enum: "running", "complete", "failed")
- `steps_completed` (integer)
- `steps_total` (integer)
- `errors` (jsonb, nullable)
- `output_summary` (text, nullable)
- `created_at` (timestamp)
- `completed_at` (timestamp, nullable)
