# Kinetic — Feature Tiers

**Author:** Brandon Upchurch
**Date:** March 2026
**Status:** Draft

---

## Cross-Cutting: The Intelligence Layer

The Intelligence Layer is not a feature tier — it is a design principle embedded in every feature below. Every AI-generated output in Kinetic is informed by seven capabilities: **Pattern Recognition, Generative Questioning, Perspective Shifting, Counterfactual Reasoning, Temporal Intelligence, Synthesis Under Complexity, and Intellectual Honesty.** These manifest as output sections (e.g., "Questions You Haven't Asked" in prep briefs), agent behaviors (e.g., assumption extraction in the Post-Meeting Agent), and data structures (e.g., `patterns` table, `assumption` memory type). See [Intelligence Layer Design Document](./docs/plans/2026-03-04-intelligence-layer-design.md) for full specification.

---

## Tier 1: Ship First (Pre-launch essentials)

The features you need before your first client meetings. The "can't consult without it" capabilities.

| # | Feature | Description |
|---|---------|-------------|
| 1 | Knowledge Management | Ingest articles, YouTube videos, transcripts, files, and raw text; AI summarization, tagging, semantic search, chat interface to query knowledge base |
| 2 | Relationship Management | Contact tracking, meeting logging, AI summaries, relationship status, ICP scoring, communication recommendations |
| 3 | Follow-up & Reminders | Auto-generated follow-ups, thank-you drafts, "stay in touch" nudges, important date alerts |
| 4 | Meeting Prep | Prep briefs pulling from contact history + knowledge base + client context |
| 5 | Document Management | Client folders as the backbone — Cowork-style file management per client |
| 6 | Client Context Dashboard | Unified co-pilot view per client: goals, pain points, meetings, action items, relationship health |
| 7 | Client Intake Flow | Structured onboarding for new clients: goals, constraints, industry context, initial pain points |
| 8 | Weekly Review Prompt | Structured reflection: who to follow up with, knowledge captured, patterns emerging, next week's focus |
| 9 | Practice Memory | Two-layer memory (client + practice) that compounds over time and persists across sessions |
| 10 | Client-Facing Summaries | Client-safe versions of meeting notes and prep briefs — professional, stripped of internal strategy notes |
| 11 | MCP Server | Hosted MCP server exposing semantic search, quick capture, memory read/write, and contact lookup to any MCP-compatible AI client (Claude Desktop, ChatGPT, Cursor, Claude Code) |
| 12 | Quick-Capture Channel (Slack) | Zero-friction thought capture via a private Slack channel — messages are auto-embedded, classified, stored, and confirmed in-thread |
| 13 | Post-Meeting Agent | Autonomous agent triggered on meeting log — chains: summarize → extract action items → update client memory → draft thank-you → create follow-ups → scan knowledge base for relevance → flag cross-client connections |
| 14 | Morning Briefing Agent | Daily cron agent — compiles today's meetings with prep briefs, overdue follow-ups, and relevant knowledge items; delivers to Slack DM each morning |
| 15 | Pre-Meeting Research Agent | Triggered 2 hours before a meeting — web searches for recent company news, funding, launches, and leadership changes; appends findings to prep brief; sends Slack notification |
| 16 | Folder-Aware Co-Pilot (CLAUDE.md) | Each client folder on your machine contains a generated `CLAUDE.md` — when Claude Code opens in that folder, it calls `set_active_client` + `get_client_context` via MCP and loads the full client context automatically; enables in-folder deliverable work with full co-pilot awareness |

---

## Tier 2: Month 2-3 (Features that compound with data)

These become valuable once you have clients, meeting history, and knowledge in the system.

| # | Feature | Description |
|---|---------|-------------|
| 17 | Goal & Priority Management | Proactively track and update client goals/priorities as they evolve |
| 18 | Time Management | "What's next?" prompts, top 3 priorities, daily focus recommendations |
| 19 | Pattern Recognition | Identify themes across meetings, transcripts, emails; surface emerging opportunities |
| 20 | Frameworks | Create, store, and reuse consulting frameworks across clients |
| 21 | Opportunity Pipeline | Track opportunities by status, estimated value, next steps |
| 22 | Proposal / SOW Generator | AI-assisted proposal creation pulling from client context, pain points, frameworks, and pricing (consolidates with Proposal Draft Agent) |
| 23 | Revenue & Utilization Tracker | Hours worked per client, revenue per engagement, pipeline forecast |
| 24 | Relevance Decay | Recency signals on knowledge items so old content doesn't surface with equal weight |
| 25 | Knowledge Relevance Agent | When a new knowledge item is ingested, agent scans all active clients and flags: "This article is relevant to [Client X]'s pain point from [Meeting Y]" |
| 26 | Relationship Health Agent | Weekly agent that scans contacts for dormancy (no interaction in X days), scores relationship health, and queues pre-drafted re-engagement messages for review |
| 27 | Recommendation Engine Agent | On-demand from client dashboard — searches knowledge base + practice memory + web for solutions to a flagged client pain point; drafts a structured recommendation for review |
| 28 | Deliverable Drafting Agent | On-demand post-meeting — drafts the next deliverable (summary deck, action plan, recommendations doc, training outline) using meeting notes + client memory + frameworks |
| 29 | Client Check-In Agent | Weekly cron per active client — reviews goals, recent meetings, and open items; generates a personalized check-in draft with specific progress references |
| 30 | Pipeline Pulse Agent | Weekly cron — flags stale opportunities (no activity in X days), identifies contacts ready to advance, drafts a prioritized pipeline action list |
| 31 | Engagement Wrap-Up Agent | Triggered when engagement is marked complete — generates after-action review, extracts reusable frameworks, updates practice memory, drafts case study outline |
| 32 | AI Landscape Monitor Agent | Daily/weekly cron — searches for new AI tool releases, model updates, case studies, and industry news relevant to active client industries; auto-ingests top findings into knowledge base |
| 33 | Knowledge Gap Agent | Pre-meeting or on new pain point — scans knowledge base for what you don't know about a topic; generates a focused study list of recommended searches or resources |
| 34 | Stakeholder Map Agent | After 3+ meetings with a client — analyzes meeting notes to identify decision-makers, influencers, blockers, and champions; flags relationships not yet engaged |
| 35 | Risk & Blocker Agent | Weekly cron — scans active client records for risk signals (silence gaps, unresolved objections, missed commitments, negative sentiment); surfaces a watch list with suggested mitigations |
| 36 | Follow-Up Quality Agent | On-demand pre-send — reviews a follow-up draft against meeting context and client memory; flags if too generic or missing key references; suggests improvements |

---

## Tier 3: Month 4+ (Integrations and advanced intelligence)

Nice-to-haves that require external integrations or critical mass of data.

| # | Feature | Description |
|---|---------|-------------|
| 37 | Calendar Management | Calendar connection, meeting reminders, auto-prep briefs triggered by calendar events (replaces manual upcoming meeting entry) |
| 38 | Decision / Strategy Support | Help ask the right questions, identify info gaps, get data needed for next decision |
| 39 | Communication Support | Email drafts, message drafts, communication style recommendations |
| 40 | Brainstorming | Idea generation contextualized to client situation and knowledge base |
| 41 | Learning Management | Recommendations on what to learn to better serve specific clients |
| 42 | Connection Matching | AI-suggested introductions between contacts with rationale |
| 43 | Warm Intro Request Drafts | Auto-drafted intro requests with context for connection matching |
| 44 | Revenue Snapshot Agent | Weekly cron — summarizes pipeline value, hours logged, revenue recognized, and utilization rate; flags if off-track for monthly targets; delivers to Slack |
| 45 | Synthesis Agent | On-demand or weekly cron — reviews all knowledge items on a topic or client industry; generates a consolidated "state of knowledge" summary of what you know, what's changing, and what's conflicting |

---

## Parking Lot (Interesting but not committed)

| Feature | Notes |
|---------|-------|
| Engagement Health Score | Computed red/yellow/green per client — revisit after Tier 1 is live |
| After-Action Review Prompts | Reflection prompts after engagements — could fold into weekly review |
| Competitor / Landscape Tracker | Track AI tools/vendors across clients — revisit when pattern recognition is built |
| Content Generation | Turn knowledge + patterns into thought leadership drafts |
| "What Would Brandon Say?" Simulator | Advisory simulation from practice memory — needs months of data |
| Content Opportunity Agent | Weekly cron — scans meeting notes and knowledge base for recurring themes that would make strong LinkedIn posts or articles; drafts outlines or opening paragraphs |
