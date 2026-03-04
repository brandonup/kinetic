# Kinetic — Session Summary

**Author:** Brandon Upchurch
**Date:** March 2026
**Session:** Product definition and PRD development

---

## What We Built

Starting from a rough PRD draft (CRM-focused, no problem statement, no strategic framing), we developed the full product definition for Kinetic across three working documents and one comprehensive PRD.

### Files Created

| File | Description |
|------|-------------|
| `problem-statement.md` | Formal problem framing narrative + final problem statement |
| `feature-tiers.md` | Full feature list prioritized into Tier 1 / 2 / 3 / Parking Lot |
| `prd-kinetic-v2.md` | Complete PRD (v2.1) — 10 sections + 5 appendices |

---

## Key Product Decisions Made

**Vision clarification:** Kinetic is not a CRM. It is an AI consulting co-pilot — a partner that synthesizes client context, domain knowledge, relationship history, and strategic frameworks into actionable intelligence. The CRM and knowledge base are infrastructure; the co-pilot is the product.

**Architecture decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector database | Supabase pgvector (not Qdrant) | Single database, eliminates sync complexity, sufficient for <10K vectors in year 1 |
| MCP server | Supabase Edge Function | Exposes Kinetic to Claude Desktop, ChatGPT, Cursor, Claude Code via a single hosted URL |
| Quick capture | Slack private channel | Zero-friction thought capture; messages auto-embedded, classified, confirmed in-thread |
| Memory architecture | Two-layer (client + practice) | Structured tables with embedding columns, not freeform chat history |
| Embedding model | OpenAI text-embedding-3-small | 1536-dim vectors; evaluate Voyage AI as alternative |
| Frontend | Next.js + Tailwind CSS | Single project handles UI + API routes |
| Auth | None for v1 (single user, local) | Add before hosting |

**Visual design:** Mostly black with teal highlights. Terminal-meets-modern-dashboard aesthetic.
- Background: `#0a0a0a` / `#111111`
- Cards/surfaces: `#1a1a1a` / `#1e1e1e`
- Primary accent: `#00b5a3` (teal)
- Text: `#f5f5f5` / `#888888`
- Borders: `#2a2a2a`

---

## Feature Priorities (Summary)

**Tier 1 — Build before first client meetings (12 features):**
Knowledge Management, Relationship Management, Follow-up & Reminders, Meeting Prep, Document Management, Client Context Dashboard, Client Intake Flow, Weekly Review Prompt, Practice Memory, Client-Facing Summaries, MCP Server, Quick-Capture Channel (Slack)

**Tier 2 — Month 2-3, compounds with data (8 features):**
Goal & Priority Management, Time Management, Pattern Recognition, Frameworks, Opportunity Pipeline, Proposal/SOW Generator, Revenue & Utilization Tracker, Relevance Decay

**Tier 3 — Month 4+, integrations and advanced intelligence (7 features):**
Calendar Management, Decision/Strategy Support, Communication Support, Brainstorming, Learning Management, Connection Matching, Warm Intro Request Drafts

---

## Problem Statement (Final)

> A solo AI consultant needs a way to operate with the depth and responsiveness of a full consulting team — synthesizing client context, domain knowledge, relationship history, and strategic frameworks into actionable intelligence that helps solve client problems — because existing tools silo these functions into disconnected apps, forcing the consultant to be the manual integration layer and causing client insights to go unleveraged, advice quality to suffer, and early-stage credibility to erode.

---

## Build Order (from PRD)

**Phase 1 — Foundation:** Project setup, contact CRUD + LinkedIn PDF parsing, meeting logging + AI pipeline, thank-you email generation, follow-up manager, contact dashboard, basic homepage

**Phase 2 — Knowledge Base:** URL/file ingestion, AI classification pipeline, Qdrant → pgvector embedding, knowledge browser, chat interface

**Phase 3 — Intelligence:** Meeting prep brief, pattern detection, opportunity identification, connection matching

**Phase 4 — Friction Reduction:** MCP server, Slack quick-capture, browser extension, calendar integration, email integration

---

## Open Questions (from PRD)

1. LinkedIn PDF parsing reliability — test during Phase 1, build manual fallback
2. Calendar integration approach — native API vs. Notion/Zapier bridge
3. Client-facing summaries — separate export flow or dedicated portal?
4. Frameworks library — template-based or freeform?
5. Embedding model — OpenAI vs. Voyage AI tradeoffs
6. Relationship health scoring — algorithmic or AI-assessed?
7. Multi-tenancy — how to structure if selling to other consultants
