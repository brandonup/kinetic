# Kinetic PRD
## AI Co-Pilot for Solo Consulting Practice

**Author:** Brandon Upchurch
**Version:** 3.2
**Date:** March 2026
**Status:** Draft

---

## 1. Executive Summary

Kinetic is a personal AI co-pilot that helps a solo AI consultant operate with the depth and responsiveness of a full consulting team. At its core is the **Intelligence Layer** — seven cognitive capabilities (pattern recognition, generative questioning, perspective shifting, counterfactual reasoning, temporal intelligence, synthesis under complexity, and intellectual honesty) embedded in every output the system produces. Kinetic doesn't just help you do things faster — it changes what you're aware of, what you question, and how you think. It synthesizes client context, domain knowledge, relationship history, and strategic frameworks into a unified system that proactively surfaces actionable intelligence — so every meeting is better prepared, every follow-up is timely, every recommendation is grounded in the latest AI landscape, and every client relationship compounds over time. The primary user is Brandon Upchurch, launching an AI consulting practice targeting B2B companies under 2,000 employees. Kinetic replaces the current patchwork of spreadsheets and Notion with a single system where people, knowledge, and action converge. It uses an open protocol (MCP) so any AI tool — Claude, ChatGPT, Cursor, Claude Code — can read from and write to the same brain.

**Design Principles:**
- **Intelligence Layer First:** Every AI output is informed by the seven Intelligence Layer capabilities. If an output doesn't make the user think differently — not just act faster — it's not done.
- **Minimum Effort:** Every interaction should require the minimum possible effort from the user. If a step can be automated, it should be. If context can be surfaced proactively, it must be.
- **Work from Anywhere:** Capture should be possible from wherever you're working — not just the web app. If you're in Claude Desktop, Cursor, or Slack, you should be able to save a thought or search your brain without switching contexts.
- **Grounded, Not Generic:** Intelligence Layer outputs appear only when enough data exists to be specific. Vague platitudes are worse than silence.

---

## 2. Problem Statement

### Who has this problem?

A solo AI consultant launching a new advisory practice — technical but not a developer, managing contacts in spreadsheets, knowledge in notes apps, and follow-ups in his head.

### What is the problem?

The work of being a great consultant spans too many disconnected systems. Client context lives in meeting notes. AI trends and research live in bookmarks and articles. Follow-ups live in memory. Frameworks used previously live in old docs that can't be found. Nothing connects a client's pain point to a trend from last week to a framework used with a different client last month. The consultant is the only integration layer across relationship management, knowledge synthesis, strategic thinking, communication, and time management — and can't hold it all in his head.

### Why is it painful?

Warm leads go cold because key details are forgotten or follow-ups slip. Knowledge goes unleveraged — articles read, patterns observed across conversations, frameworks built — because it can't be surfaced at the right moment. Client context gets lost between meetings, degrading the quality of advice. At the pre-launch stage, every gap in the system is a gap in credibility.

### Evidence

- Currently managing contacts in Google Sheets with no automated follow-up or contextual linking
- Using Notion for meeting notes with no connection to contact records or knowledge base
- No system for surfacing relevant AI trends or research during client conversations
- The AI consulting landscape changes weekly, making static knowledge a liability

### Full Problem Framing

See [problem-statement.md](./problem-statement.md) for the complete narrative.

---

## 3. Target User & Persona

### Primary Persona: Brandon Upchurch — Solo AI Consultant

| Attribute | Detail |
|-----------|--------|
| **Role** | Independent AI consultant, solo practitioner |
| **Target market** | B2B companies under 2,000 employees |
| **Services offered** | Strategy & advisory, implementation, training & enablement |
| **Tech level** | Technical but not a developer — comfortable with AI tools, APIs, and configuration; not writing production code daily |
| **Current tools** | Google Sheets (contacts), Notion (notes/knowledge), memory (follow-ups) |
| **Location** | Portland, OR — heavy in-person networking market |
| **Stage** | Pre-launch, pre-revenue, building pipeline through networking, meetups, and coffee chats |
| **Timeline** | First paying client within 90 days |

### Jobs-to-be-Done

1. **Understand my clients deeply** — Capture and synthesize everything I learn about a client's goals, pain points, org dynamics, and context so I can give sharper advice every time we talk.
2. **Stay current on AI** — Absorb and organize the latest AI trends, tools, case studies, and research from trusted sources so my recommendations are always grounded in current reality.
3. **Connect the dots** — Link what a client needs to what I know (from research, past clients, frameworks) so I can surface the right insight at the right moment.
4. **Never drop the ball** — Follow up reliably, prepare thoroughly for every meeting, and maintain the kind of responsiveness that builds trust and referrals.
5. **Compound my expertise** — Ensure that every conversation, every article, every engagement makes me a better consultant for the next one.

### Secondary Persona (Future)

Other solo AI or technology consultants with similar workflows. Not a design consideration for v1, but Kinetic should avoid hard-coding Brandon-specific assumptions where a general pattern would work equally well.

---

## 4. Strategic Context

### Business Goals

Kinetic exists to accelerate the launch and effectiveness of an AI consulting practice. Specifically:

- **Pipeline velocity:** Move from 0 to first paying client within 90 days
- **Relationship quality:** Maintain meaningful, responsive relationships with 50+ contacts simultaneously
- **Advisory quality:** Deliver AI consulting advice grounded in current research and client-specific context
- **Operational efficiency:** Operate a solo practice without administrative overhead consuming client-facing time

### Competitive Landscape

| Tool | What it does well | Where it falls short |
|------|------------------|---------------------|
| **Notion** | Flexible notes and knowledge management | No relationship management, no proactive surfacing, no AI synthesis across documents, doesn't link people to knowledge |
| **Google Sheets / Airtable** | Structured contact tracking | Manual, no AI layer, no semantic search, doesn't scale with context richness |
| **HubSpot / Salesforce** | Enterprise CRM with automation | Designed for sales teams, not solo consultants. Overkill on pipeline, zero knowledge management |
| **Clay / Folk / Attio** | Modern lightweight CRMs | Better UX, but still CRM-first. No knowledge base, no domain expertise layer, no consulting-specific intelligence |
| **Obsidian / Roam** | Deep knowledge management | No relationship management, no follow-up automation, no proactive intelligence |
| **ChatGPT / Claude** | Powerful AI assistants | Stateless by default — no persistent client context, no relationship tracking, no structured data |

**Gap:** No existing tool combines relationship intelligence, domain knowledge management, and consulting-specific workflows (meeting prep, client context synthesis, framework reuse) into a unified AI-native system. Every alternative requires the consultant to be the manual integration layer between 3-5 apps.

### Why Now?

- **Pre-launch window:** The system needs to be operational before first client meetings, not after. Retrofitting is exponentially harder than starting with the right system.
- **AI tooling maturity:** LLMs (Claude), vector-capable databases (Supabase pgvector), and open protocols (MCP) are now good enough and cheap enough to build this as a solo project.
- **Market timing:** Demand for AI consulting is accelerating. Companies under 2,000 employees are actively looking for advisory help but underserved by enterprise consulting firms. Speed to market matters.
- **Compounding advantage:** Every week of use makes Kinetic more valuable. Starting now means 90 days of accumulated intelligence by the time the first client engagement begins.

---

## 5. The Intelligence Layer

The Intelligence Layer is Kinetic's primary differentiator and the foundation of the entire platform. It is not a feature — it is a design principle that transforms every AI-generated output. Most AI tools help users do things faster. The Intelligence Layer changes what users are *aware of*, what they *question*, and how they *think*.

Every system prompt, every agent, every output structure, and every interaction Kinetic produces is informed by seven capabilities:

| # | Capability | What it does | Key manifestation |
|---|-----------|-------------|-------------------|
| 1 | **Pattern Recognition** | Detects connections across fragmented information that no human could hold in their head | Post-Meeting Agent flags cross-client patterns; `patterns` table tracks them as first-class data |
| 2 | **Generative Questioning** | Asks the questions you didn't know you needed to ask | "Questions You Haven't Asked" in every prep brief; "What This Conversation Didn't Address" in every post-meeting summary |
| 3 | **Perspective Shifting** | Models how stakeholders, clients, and competitors might think | "How [Stakeholder] Might See This" in prep briefs; on-demand simulation in chat |
| 4 | **Counterfactual & Scenario Reasoning** | Explores branching futures grounded in actual data | "What if?" exploration in chat and client dashboard; contingency reasoning in recommendations |
| 5 | **Temporal Intelligence** | Connects past, present, and future — notices gradual shifts humans miss | "What's Changed Since Last Meeting" in prep briefs; drift detection in weekly reviews |
| 6 | **Synthesis Under Complexity** | Compresses complexity into the essential mental model | "Bottom Line" compression in every output; "The Essential Situation" in prep briefs |
| 7 | **Intellectual Honesty Engine** | Surfaces uncomfortable truths grounded in your own data | Assumption tracking from meetings; "Assumptions at Risk" in prep briefs; "What You Might Be Avoiding" in weekly reviews |

### How It Integrates

The Intelligence Layer is not a separate feature tier. It permeates the platform through six mechanisms:

1. **Shared Prompt Architecture** — A shared `INTELLIGENCE_LAYER_PROMPT` is injected into every LLM system prompt. It instructs generative questioning, synthesis compression, and perspective awareness in every output.
2. **Output Structure** — Every AI-generated artifact (prep briefs, summaries, reviews, briefings) includes conditional sections driven by the seven capabilities. Sections appear only when enough data exists to ground them — no vague platitudes.
3. **Data Model** — Assumptions, hypotheses, and patterns are first-class data types. They are extracted from meetings, tracked over time, and checked against new evidence.
4. **Agent Behavior** — Every agent applies Intelligence Layer thinking: the Post-Meeting Agent extracts assumptions, the Morning Briefing surfaces uncomfortable truths, the Pre-Meeting Research Agent adds perspective analysis.
5. **Chat Interface** — On-demand Intelligence Layer capabilities activated by natural prompt patterns: perspective shifting ("How would the CFO see this?"), counterfactual reasoning ("What if their budget gets cut?"), intellectual honesty ("What am I wrong about with [Client]?"), and more.
6. **Per-Client CLAUDE.md** — Generated `CLAUDE.md` files include Intelligence Layer instructions so Claude Code sessions in client folders automatically apply questioning, assumption-checking, and synthesis behaviors.

See [Intelligence Layer Design Document](./docs/plans/2026-03-04-intelligence-layer-design.md) for the complete specification, output templates, and implementation details.

---

## 6. Solution Overview

### What Kinetic Is

Kinetic is a personal AI co-pilot for running a consulting practice, built on two pillars: a **web application** (the dashboard) and an **MCP server** (the open protocol). Together, they ensure Kinetic's intelligence is accessible from wherever you're working.

**Layer 1: Capture** — Ingest information with minimal friction from multiple channels. The web app handles structured inputs (LinkedIn PDFs, meeting notes, URL ingestion). A quick-capture channel (Slack or any messaging interface) handles fast, unstructured thoughts. The MCP server lets any connected AI tool write directly to Kinetic — capture a thought mid-conversation in Claude Desktop, log a quick note from Cursor, save an insight from ChatGPT. Everything gets automatically summarized, tagged, embedded for semantic search, and linked to the relevant client context.

**Layer 2: Connect** — AI links people, knowledge, and context. A client mentions a pain point → Kinetic connects it to an article you saved last week and a framework you used with a previous client. You prepare for a meeting → Kinetic pulls the full client context, relevant trends, and suggested talking points. Nothing exists in isolation. Any MCP-connected AI can search Kinetic semantically, meaning your accumulated knowledge is available in every tool you use — not just the Kinetic web app.

**Layer 3: Act** — Proactive intelligence that drives action. Follow-up reminders surface with pre-drafted messages. Weekly reviews highlight who needs attention and what patterns are emerging. Meeting prep briefs are generated automatically. The system nudges you toward the right action at the right time.

**Layer 4: Agents** — Autonomous multi-step workflows that run without being asked. Three agents ship in Tier 1. The **Post-Meeting Agent** fires automatically every time a meeting is logged — it summarizes notes, extracts action items, updates client memory, drafts the thank-you email, creates follow-up records, scans the knowledge base for relevant items, and flags connections to other clients — all in one chained workflow using Anthropic tool use. The **Morning Briefing Agent** runs on a daily cron schedule, compiles everything you need to know before the day starts, and delivers it to Slack: today's meetings with auto-generated prep briefs, overdue follow-ups, and knowledge items relevant to today's conversations. The **Pre-Meeting Research Agent** runs every 30 minutes, checks for meetings starting within 2 hours, and automatically researches the contact's company for recent news — appending live findings to the prep brief so you walk in knowing what changed since you last spoke.

### Architecture

Kinetic has two interfaces that serve different purposes:

**Web Application (Next.js)** — The dashboard. This is where you manage contacts, review client context, work through follow-ups, browse knowledge, and run structured workflows like meeting prep and weekly reviews. It's the "command center" for the practice.

**MCP Server (Supabase Edge Function)** — The open protocol. A hosted MCP server that exposes Kinetic's core capabilities — semantic search, quick capture, memory read/write, contact lookup, and active client context — to any MCP-compatible AI client. Claude Desktop, ChatGPT, Cursor, Claude Code, and any future MCP-compatible tool can connect via a single URL. No local server, no build steps.

**Per-Client CLAUDE.md (Folder-Aware Co-Pilot)** — Each client folder on your machine contains a `CLAUDE.md` file that tells Claude Code which client you're working on and how to load their full Kinetic context. When you open Claude Code inside `/Projects/AcmeCorp/`, it reads the `CLAUDE.md`, calls `set_active_client` via MCP, and your session is automatically loaded with Acme's goals, pain points, meeting history, memory, and relevant knowledge — without you typing a single context-setting message. Every AI tool you use in that folder operates as an informed consulting partner for that specific client.

**Quick-Capture Channel (Slack)** — The fast input. A Slack channel connected to a Supabase Edge Function. Type a thought, it gets embedded, classified, and stored automatically with a threaded confirmation. For moments when you need to capture something faster than opening the web app — a name dropped at an event, a quick insight from a podcast, a follow-up idea while driving.

### How It Works

The primary interaction model is a **per-client context dashboard** — a unified view of everything Kinetic knows about a client: their goals, pain points, meeting history, action items, relevant knowledge, and relationship health. This is the "co-pilot seat" where Brandon operates during and between client engagements.

Supporting this are:

- A **knowledge base** with semantic search and a chat interface for querying accumulated expertise
- A **follow-up manager** that ensures nothing falls through the cracks
- A **meeting prep generator** that synthesizes client context, knowledge, and talking points
- A **practice memory** system (client-level and practice-level) that compounds over time
- A **weekly review** prompt that provides structured reflection on the practice
- An **MCP server** that makes all of the above accessible from any AI tool you use
- A **quick-capture channel** (Slack) for zero-friction thought capture on the go

### Key Features (Tier 1 — Ship First)

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Knowledge Management** | Ingest articles, YouTube videos, transcripts, files, and raw text; AI summarization, tagging, semantic search; chat interface to query knowledge base |
| 2 | **Relationship Management** | Contact tracking, meeting logging, AI summaries, relationship status, ICP scoring |
| 3 | **Follow-up & Reminders** | Auto-generated follow-ups, thank-you drafts, "stay in touch" nudges, important date alerts |
| 4 | **Meeting Prep** | Prep briefs pulling from contact history + knowledge base + client context |
| 5 | **Document Management** | Client folders as the backbone — file management per client |
| 6 | **Client Context Dashboard** | Unified co-pilot view per client: goals, pain points, meetings, action items, relationship health |
| 7 | **Client Intake Flow** | Structured onboarding for new clients: goals, constraints, industry context, initial pain points |
| 8 | **Weekly Review Prompt** | Structured reflection: who to follow up with, knowledge captured, patterns emerging, next week's focus |
| 9 | **Practice Memory** | Two-layer memory (client + practice) that compounds over time and persists across sessions |
| 10 | **Client-Facing Summaries** | Client-safe versions of meeting notes and prep briefs — professional, stripped of internal strategy notes |
| 11 | **MCP Server** | Hosted MCP server exposing semantic search, quick capture, memory read/write, and contact lookup to any MCP-compatible AI client |
| 12 | **Quick-Capture Channel** | Slack integration for zero-friction thought capture — type a message, it gets embedded, classified, and stored with auto-confirmation |
| 13 | **Post-Meeting Agent** | Autonomous agent triggered on meeting log — chains: summarize → extract action items → update client memory → draft thank-you → create follow-ups → scan knowledge base for relevance → flag cross-client connections |
| 14 | **Morning Briefing Agent** | Daily cron agent — compiles today's meetings with auto-generated prep briefs, overdue follow-ups, and relevant knowledge items; delivers to Slack DM each morning |
| 15 | **Pre-Meeting Research Agent** | Triggered 1-2 hours before a meeting — searches for recent news, funding, product launches, and leadership changes for the contact's company; appends live findings to the prep brief |
| 16 | **Folder-Aware Co-Pilot (CLAUDE.md)** | Each client folder contains a `CLAUDE.md` that auto-loads client context when Claude Code opens in that directory — goals, meetings, memory, and knowledge are pre-loaded via MCP without any manual context-setting |

See [feature-tiers.md](./feature-tiers.md) for complete Tier 2, Tier 3, and Parking Lot features.

### Automated Workflows

**On Contact Created:**
1. Parse input (LinkedIn PDF, URL, or form data)
2. Generate AI profile summary
3. Embed contact in Supabase (pgvector) for semantic search
4. Check for potential connections with existing contacts

**On Meeting Logged (Post-Meeting Agent):**

This is an autonomous agent using Anthropic tool use. Each step is a tool call; the agent decides sequence and can branch based on what it finds.

1. Generate AI summary of raw notes (includes "The Essential Takeaway" — Synthesis)
2. Extract action items with suggested due dates → create follow-up records
3. Identify and tag pain points and buying signals on meeting record
4. Extract assumptions stated or implied → store as client_memory type `assumption` (Intellectual Honesty)
5. Identify gaps: what was NOT discussed relative to client goals → include "What This Conversation Didn't Address" in summary (Generative Questioning)
6. Generate thank-you email draft referencing specific conversation points
7. Update contact profile (ai_summary, relationship_status)
8. Embed meeting in Supabase (pgvector)
9. Update client memory with new context extracted from meeting
10. Generate client-facing summary (if meeting is flagged as client engagement)
11. Semantic search knowledge base → surface items relevant to pain points or topics discussed → link to meeting record
12. Scan other client records for cross-client pattern matches → write to `patterns` table with evidence references if found (Pattern Recognition)

**On Morning Briefing (Daily Cron Agent — 8am):**

Runs as a Supabase Edge Function on a cron schedule. Delivers to Slack DM.

1. Fetch today's meetings (from calendar or manually logged upcoming meetings)
2. For each meeting: generate prep brief (contact context + relevant knowledge + suggested talking points)
3. For each meeting: generate "One Question Worth Asking" (Generative Questioning)
4. Fetch all follow-ups due today or overdue
5. For each overdue follow-up: ensure message draft exists; generate if missing
6. Fetch knowledge items added in the last 24 hours; cross-reference against active clients for relevance
7. Check for tracked assumptions with contradicting evidence → select one for "Assumption to Revisit Today" (Intellectual Honesty)
8. Check for drift_detected events in last 7 days → include "Gradual Shift Alert" if found (Temporal Intelligence)
9. Compile all outputs into a structured briefing message
10. Send to Slack DM with sections: Today's Meetings | One Question Worth Asking | Follow-ups Due | New Knowledge Worth Noting | Assumption to Revisit Today (conditional) | Gradual Shift Alert (conditional)

**On Upcoming Meeting (Pre-Meeting Research Agent — 2 hours before):**

Triggered by a cron that scans for meetings starting in the next 2 hours. Runs as a Supabase Edge Function.

1. Identify meetings starting in the next 2 hours that don't have a "research_complete" flag
2. For each meeting: look up the contact's company
3. Web search: "[Company] news", "[Company] funding", "[Company] product launch", "[Company] leadership" — last 30 days
4. LLM summarizes findings into a "Recent Company News" section (3-5 bullet points)
5. Generate "How this news might affect what [Contact] cares about" grounded in client memory (Perspective Shifting)
6. Append findings + perspective analysis to the existing prep brief (or create one if it doesn't exist)
7. Flag the meeting as "research_complete" to prevent re-runs
8. Send a Slack notification: "Prep brief updated for [Contact] @ [Company] — [N] recent developments found"

**On Knowledge Item Added:**
1. Detect input type: YouTube URL → transcript extractor; article URL → web scraper; file/text → direct
2. If YouTube URL: extract video ID, fetch transcript via `youtube-transcript` npm package, clean (strip timestamps, merge segments into paragraphs)
3. If article URL: fetch and parse page content (title, body, author)
4. Generate summary + key takeaways
5. Auto-classify and tag
6. Chunk content and embed in Supabase (pgvector)
7. Check for relevance to existing clients/opportunities

**On Quick Capture (Slack or MCP):**
1. Receive raw text input
2. Generate embedding via OpenAI text-embedding-3-small
3. Extract metadata via LLM (category, people mentioned, action items, tags)
4. Store as knowledge item or meeting note (based on classification) with embedding in Supabase
5. Reply with confirmation showing what was captured and how it was classified
6. Check for relevance to existing clients/contacts and link if applicable

**On Follow-Up Due:**
1. Surface in follow-up dashboard
2. If message draft doesn't exist, generate one based on context
3. (Future: automated email sending with confirmation)

---

## 7. Success Metrics

### Primary Metric

**Consulting readiness:** Can Kinetic reliably prepare Brandon for any client interaction within 5 minutes — with full context, relevant knowledge, and suggested talking points?

Measured by: Consistent use of meeting prep briefs before every meeting within the first 30 days.

### Secondary Metrics

| Metric | Current State | Target | Timeline |
|--------|--------------|--------|----------|
| Follow-up completion rate | Unknown (no system) | 90% of follow-ups completed within 48 hours | 30 days post-launch |
| Knowledge capture rate | Ad hoc, inconsistent | 5+ knowledge items added per week | 30 days post-launch |
| Contact context richness | Spreadsheet with name/company only | Every active contact has AI-generated profile, meeting history, and linked knowledge | 60 days post-launch |
| Time to log a meeting | N/A | Under 2 minutes (paste notes → all automation fires) | Launch |
| Time to add a contact | N/A | Under 30 seconds (quick-add or LinkedIn PDF) | Launch |
| Weekly review completion | None | Weekly review completed every week | 30 days post-launch |

### Intelligence Layer Metrics

| Metric | Target | Timeline |
|--------|--------|----------|
| Prep brief Intelligence Layer sections non-empty | >60% of prep briefs have at least 2 Intelligence Layer sections populated with grounded content | 60 days post-launch |
| Tracked assumptions per active client | 3+ tracked assumptions per client with 3+ meetings | 60 days post-launch |
| Patterns detected | At least 1 cross-client or behavioral pattern detected per month after 3+ active clients | 90 days post-launch |
| Weekly review usefulness | Brandon reads and acts on the weekly review >75% of weeks | 30 days post-launch |
| Assumption contradiction surfaced | At least 1 "Assumptions at Risk" finding per month that leads to a changed approach | 90 days post-launch |

### Guardrail Metrics

- **LLM cost per month:** Should stay under $50/month for normal usage
- **System maintenance time:** Should require less than 1 hour/week of maintenance or data cleanup
- **Data quality:** AI summaries and tags should be accurate enough that Brandon trusts them without manual review >80% of the time
- **Intelligence Layer noise:** Intelligence Layer sections should feel grounded and specific >80% of the time. If sections feel generic or repetitive, that's a prompt engineering failure to address immediately.

### Outcome Metrics (90-day)

These are the consulting practice outcomes Kinetic should enable:

- **Pipeline:** 10+ warm relationships actively managed in Kinetic
- **First client:** Signed engagement within 90 days of launch
- **Knowledge depth:** 50+ curated knowledge items across AI trends, case studies, and methodologies
- **Practice memory:** System can meaningfully assist with meeting prep, follow-ups, and client strategy by day 60

---

## 8. User Stories & Requirements

### Epic Hypothesis

We believe that building an AI co-pilot that synthesizes relationship intelligence, domain knowledge, and consulting workflows into a unified system will enable a solo consultant to land their first client within 90 days and manage 10+ active relationships without dropping the ball — because the current patchwork of spreadsheets and notes apps fragments context and requires manual effort that doesn't scale.

### Tier 1 User Stories

**Story 1: Add a Contact Quickly**
As a consultant, I want to add a new contact in under 30 seconds, so I can capture people I meet at events without friction.

Acceptance Criteria:
- [ ] Can add via quick-add form: name + company + how we met (minimum)
- [ ] Can upload LinkedIn PDF → auto-extract name, title, company, location, experience
- [ ] On creation, AI generates initial profile summary
- [ ] Contact is embedded in Supabase (pgvector) for semantic search
- [ ] Default relationship_status set to "new"

**Story 2: Log Meeting Notes and Trigger Processing**
As a consultant, I want to paste meeting notes and have Kinetic automatically handle all processing, so I spend time consulting instead of organizing.

Acceptance Criteria:
- [ ] Can paste raw notes or transcript into a text field
- [ ] Can upload a text/markdown file
- [ ] Can schedule an upcoming meeting (date, contact, type) before it happens
- [ ] Can add notes to a previously scheduled upcoming meeting (transitions status from "upcoming" → "completed")
- [ ] On submit, meeting is saved and the Post-Meeting Agent (Story 13) is triggered asynchronously
- [ ] UI shows "Processing..." indicator while agent runs; updates when complete
- [ ] User is not blocked from navigating while agent processes

**Story 3: Never Miss a Follow-Up**
As a consultant, I want a dashboard showing all pending follow-ups with pre-drafted messages, so nothing falls through the cracks.

Acceptance Criteria:
- [ ] Dashboard shows pending follow-ups sorted by due date
- [ ] Each follow-up shows: contact name, type, suggested message draft
- [ ] Can copy message to clipboard or open in email client
- [ ] Can snooze, mark sent, or dismiss
- [ ] Overdue follow-ups visually highlighted

**Story 4: Build a Knowledge Base from Trusted Sources**
As a consultant, I want to capture articles, transcripts, and research and have them automatically organized, so I can build expertise that's searchable and connected to client needs.

Acceptance Criteria:
- [ ] Can paste a URL → auto-fetch article content
- [ ] Can paste a YouTube URL → auto-extract transcript, clean it, and process through the standard pipeline
- [ ] Can paste raw text (podcast transcripts, personal notes)
- [ ] Can upload file (PDF, markdown, text)
- [ ] AI generates summary and key takeaways
- [ ] AI auto-classifies into categories (market intelligence, technical, methodology, etc.)
- [ ] Content is chunked and embedded for semantic search
- [ ] Can query knowledge base via semantic search ("what do I know about SMB sales automation?")
- [ ] Graceful error shown when a YouTube video has no available transcript

**Story 5: Chat with My Knowledge Base**
As a consultant, I want to ask natural language questions across everything I've captured, so I can prepare for conversations and develop recommendations.

Acceptance Criteria:
- [ ] Conversational interface to query knowledge base, meeting notes, and contact context
- [ ] Uses semantic search to retrieve relevant context, then LLM to synthesize
- [ ] Responses cite which sources they drew from (with links)
- [ ] Can scope queries to a specific client context
- [ ] Chat system prompt includes `INTELLIGENCE_LAYER_PROMPT` — all responses benefit from generative questioning, synthesis, and perspective capabilities
- [ ] Supports Intelligence Layer prompt patterns: "How would [role] see this?" (Perspective Shifting), "What if [scenario]?" (Counterfactual), "What am I wrong about with [Client]?" (Intellectual Honesty — uses tracked assumptions), "What patterns am I seeing?" (Pattern Recognition — queries patterns table), "What's changed with [Client] over time?" (Temporal Intelligence)

**Story 6: Generate Meeting Prep Briefs**
As a consultant, I want to generate a prep brief before any meeting, so I walk in with full context and sharp questions.

Acceptance Criteria:
- [ ] Select a contact → generate prep brief
- [ ] Brief pulls from: contact profile, all past meeting notes, relevant knowledge items, client goals
- [ ] Output follows Intelligence Layer output template (see Intelligence Layer Design Doc, Mechanism 2):
  - [ ] "The Essential Situation" (Synthesis — always present)
  - [ ] Background & context, talking points (baseline — always present)
  - [ ] "Questions You Haven't Asked" (Generative Questioning — always present)
  - [ ] "What's Changed Since Last Meeting" (Temporal Intelligence — conditional: after 2+ meetings)
  - [ ] "How [Stakeholder] Might See This" (Perspective Shifting — conditional: when stakeholder data exists)
  - [ ] "Assumptions at Risk" (Intellectual Honesty — conditional: when tracked assumptions exist)
  - [ ] "Recent Company News" (Pre-Meeting Research Agent — conditional: when research runs)
- [ ] Brief is generated in under 60 seconds
- [ ] Can generate a client-facing version (stripped of internal strategy notes and Intelligence Layer sections)

**Story 7: See Everything About a Client in One Place**
As a consultant, I want a unified client view that shows goals, context, meeting history, action items, and relevant knowledge, so I can operate as an informed partner.

Acceptance Criteria:
- [ ] Client context dashboard shows: goals, pain points, all meetings (with summaries), open action items, follow-up status, relevant knowledge items, relationship health
- [ ] Dashboard updates automatically as new meetings and knowledge are added
- [ ] Can edit client goals and context directly from this view

**Story 8: Onboard a New Client**
As a consultant, I want a structured intake flow when I start working with a client, so Kinetic has enough context to be useful immediately.

Acceptance Criteria:
- [ ] Guided intake captures: company overview, client goals, constraints, industry context, key stakeholders, initial pain points
- [ ] Creates client folder for document management
- [ ] Populates initial client memory
- [ ] Links to existing contact record

**Story 9: Kinetic Remembers What Matters**
As a consultant, I want Kinetic to remember important context from our interactions — per client and across my practice — so it gets smarter over time.

Acceptance Criteria:
- [ ] Client memory persists: goals, preferences, decisions made, org dynamics, project status
- [ ] Practice memory persists: frameworks, positioning, pricing decisions, lessons learned, market observations
- [ ] Memory is structured and queryable, not just chat history
- [ ] Memory is automatically updated from meeting logs and interactions
- [ ] Memory compounds — prep briefs and recommendations improve as context grows

**Story 10: Weekly Practice Review**
As a consultant, I want a structured weekly review that surfaces what needs attention, so I stay ahead instead of catching up.

Acceptance Criteria:
- [ ] Prompts review of: contacts needing follow-up, knowledge captured this week, patterns emerging across conversations, priorities for next week
- [ ] Surfaces overdue action items and dormant relationships
- [ ] Available on-demand or on a set schedule
- [ ] **Intelligence Layer output template:** "The State of the Practice" (Synthesis — always); "Emerging Patterns" (Pattern Recognition — conditional); "Gradual Shifts You Might Not Notice" (Temporal Intelligence — conditional: after 30+ days); "This Week's Uncomfortable Question" (Generative Questioning + Intellectual Honesty — always); "What You Might Be Avoiding" (Intellectual Honesty — conditional); "Scenarios Worth Considering" (Counterfactual — conditional: when significant client changes detected)

**Story 11: Access Kinetic from Any AI Tool**
As a consultant, I want any AI tool I use (Claude Desktop, ChatGPT, Cursor, Claude Code) to be able to search and write to Kinetic, so I don't have to context-switch to the web app to capture or retrieve information.

Acceptance Criteria:
- [ ] MCP server is deployed as a Supabase Edge Function with a single connection URL
- [ ] MCP exposes tools: semantic search, quick capture, contact lookup, memory read/write
- [ ] Access is secured via an access key (URL parameter or header)
- [ ] Claude Desktop, ChatGPT, and Claude Code can connect and use all tools
- [ ] Capture via MCP triggers the same embedding + classification pipeline as the web app
- [ ] Search results include source links back to Kinetic web app records

**Story 12: Capture a Thought Instantly via Slack**
As a consultant, I want to type a quick thought into Slack and have it automatically embedded, classified, and stored in Kinetic, so I can capture insights without breaking my flow.

Acceptance Criteria:
- [ ] Private Slack channel serves as capture interface
- [ ] Messages are received by a Supabase Edge Function via Slack Events API
- [ ] Each message is embedded, classified (category, people, action items, tags), and stored
- [ ] Threaded reply confirms what was captured: classification, tags, people mentioned, action items
- [ ] Captured thoughts are searchable via both the web app and MCP server
- [ ] If a person is mentioned who matches an existing contact, the thought is linked to that contact

**Story 13: Post-Meeting Agent Handles Everything After a Meeting**
As a consultant, I want logging a meeting to automatically trigger all follow-on work, so I never have to manually process meeting notes.

Acceptance Criteria:
- [ ] Logging a meeting triggers the Post-Meeting Agent automatically (no extra button click)
- [ ] Agent completes the full chain: summary → action items → thank-you draft → follow-ups → memory update → knowledge relevance scan
- [ ] Agent runs asynchronously — UI shows "Processing..." and updates when complete (no blocking the user)
- [ ] Each agent step result is visible in the meeting detail view
- [ ] If any step fails, the agent logs the error and continues remaining steps (partial completion is better than total failure)
- [ ] Knowledge items surfaced as relevant are shown on the meeting detail with links
- [ ] Cross-client pattern matches are flagged in practice memory with source reference
- [ ] **Intelligence Layer steps:** Agent extracts assumptions stated or implied → stores as client_memory type `assumption`; identifies gaps between what was discussed and client goals → includes "What This Conversation Didn't Address" in summary; writes to `patterns` table when cross-client pattern found
- [ ] Post-meeting summary follows Intelligence Layer output template: Summary, The Essential Takeaway, Action Items, Pain Points & Buying Signals, Assumptions Stated or Implied, What This Conversation Didn't Address, Patterns Across Clients (conditional)

**Story 14: Morning Briefing Delivered Before the Day Starts**
As a consultant, I want a daily briefing that prepares me for the day before I open the web app, so I walk into every day already oriented.

Acceptance Criteria:
- [ ] Briefing is delivered to a configured Slack DM at a set time each morning (default: 8am)
- [ ] Briefing includes: today's scheduled/upcoming meetings with prep brief summaries, all overdue and due-today follow-ups with draft messages, knowledge items added in the last 24 hours flagged as relevant to active clients
- [ ] Briefing is skipped (with a brief "Nothing on the schedule today" message) on days with no meetings and no overdue follow-ups
- [ ] Delivery time is configurable via an environment variable
- [ ] Briefing links back to the Kinetic web app for full context on each item
- [ ] **Intelligence Layer sections:** "One Question Worth Asking" per meeting (Generative Questioning); "Assumption to Revisit Today" when contradicting evidence exists (Intellectual Honesty); "Gradual Shift Alert" when drift detected in last 7 days (Temporal Intelligence)

**Story 15: Pre-Meeting Research Delivered Automatically**
As a consultant, I want Kinetic to research my contact's company before every meeting and update my prep brief with what's happening right now, so I walk in knowing what changed since we last talked.

Acceptance Criteria:
- [ ] Agent triggers automatically for any meeting starting within 2 hours
- [ ] Searches for recent news, funding, product launches, and leadership changes (last 30 days)
- [ ] Appends a "Recent Company News" section to the prep brief with 3-5 bullet points
- [ ] Sends a Slack notification when the prep brief has been updated
- [ ] If no recent news is found, brief notes "No recent company news found" rather than leaving the section empty
- [ ] Does not re-run if research has already been completed for that meeting
- [ ] **Intelligence Layer step:** After finding company news, includes "How this news might affect what [Contact] cares about" grounded in client memory (Perspective Shifting)

**Story 16: Work on Client Deliverables with Full Context Already Loaded**
As a consultant, I want to open a client folder in Claude Code and have my AI co-pilot automatically know which client I'm working on — with all their context pre-loaded — so I can ask for help with deliverables without re-explaining the client situation every time.

Acceptance Criteria:
- [ ] Each client record in Kinetic has a "Generate CLAUDE.md" action that creates a ready-to-use `CLAUDE.md` file for that client's local folder
- [ ] The `CLAUDE.md` includes: client name, Kinetic client ID, MCP server URL, and instructions telling Claude Code to call `set_active_client` and `get_client_context` at session start
- [ ] `set_active_client` MCP tool accepts a client_id and returns: goals, pain points, recent meetings (last 3), open action items, client memory, and relevant knowledge items
- [ ] When Claude Code opens in a client folder, it reads the `CLAUDE.md` and the MCP tools load the client context automatically
- [ ] With context loaded, Claude Code can answer: "What are their top pain points?", "What did we discuss last meeting?", "Help me draft a recommendations section based on what we know" — without additional context-setting
- [ ] The `CLAUDE.md` is regenerated/updated when significant client context changes (new meeting logged, goals updated)
- [ ] **Intelligence Layer instructions included in CLAUDE.md:** surface questions before recommending, flag contradictions with tracked assumptions, include stakeholder perspective notes, end complex analyses with Bottom Line compression, share what might go wrong when giving advice

### Constraints & Edge Cases

- **Single user only (v1):** No multi-tenant architecture needed. Auth deferred until deployment.
- **Transcript format agnosticism:** Meeting input must handle plain text from Zoom transcripts, Notion, and manual notes without format-specific parsing.
- **LinkedIn PDF parsing:** Must have graceful fallback to manual entry when extraction fails.
- **Content chunking:** Long knowledge items must be chunked for embedding without losing context at chunk boundaries.
- **Client data isolation:** Each client's documents and memory should be logically separated.
- **MCP server must be stateless and hosted:** No local server dependencies. Runs as a Supabase Edge Function, accessible from anywhere via URL.
- **Quick-capture classification is best-effort:** LLM metadata extraction won't always be perfect. The embedding handles fuzzy semantic search regardless of classification accuracy.
- **Slack duplicate handling:** Slack retries webhooks after 3 seconds; edge function may receive duplicate events for slow operations. Deduplication logic or idempotency needed.

---

## 9. Out of Scope

**Not included in v1:**

| Feature | Rationale |
|---------|-----------|
| Multi-user / multi-tenant | Building for personal use only; architecture complexity not justified |
| Mobile app | Desktop-first; responsive web is sufficient for v1 |
| Email integration (send from Kinetic) | Copy-to-clipboard is adequate; direct send adds auth and delivery complexity |
| Calendar integration | Manual meeting logging is acceptable for v1; calendar sync is Tier 3 |
| Audio transcription | Accept text input; users transcribe via Zoom/Notion before ingesting |
| Browser extension | MCP + Slack quick-capture covers most use cases; URL paste handles the rest |
| Gamification or scoring | No badges, streaks, or point systems |
| Advanced personalization | Same interface for all contexts; per-client UI customization deferred |
| Automated opportunity identification | AI-suggested opportunities are Tier 2; manual creation is fine for v1 |
| Connection matching | Requires critical mass of contacts; Tier 3 |

**Future considerations documented in [feature-tiers.md](./feature-tiers.md).**

---

## 10. Dependencies & Risks

### Technical Dependencies

| Dependency | Purpose | Risk Level |
|------------|---------|------------|
| Supabase (PostgreSQL + pgvector) | Structured data storage AND vector search in a single database | Low — managed service, generous free tier, pgvector is mature |
| Supabase Edge Functions | MCP server + Slack quick-capture function hosting | Low — Deno runtime, deployed alongside database |
| Anthropic API (Claude) | LLM for summarization, analysis, generation | Low — stable API, pay-per-use |
| OpenAI API | Embeddings (text-embedding-3-small) | Low — stable, cheap; could switch to Voyage AI to consolidate on Anthropic ecosystem |
| Next.js + Vercel | Frontend + hosting | Low — mature ecosystem |
| Slack API | Quick-capture channel (Events API + Bot) | Low — stable, free tier sufficient |

### Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Scope creep delays launch | Miss the 90-day client window | High | Strict Tier 1 scope; ship minimum, iterate based on real usage |
| LLM costs exceed budget | Unsustainable at pre-revenue stage | Medium | Set token budgets per operation, log costs, use cheaper models for classification/tagging |
| LinkedIn PDF parsing is unreliable | Core contact ingestion breaks | Medium | Build manual entry fallback from day 1; test with real exports early |
| AI summaries aren't trustworthy | User stops using the system | Medium | Include "view raw" toggle on all AI-generated content; iterate on prompts based on actual output quality |
| pgvector performance degrades at scale | Slow semantic search | Low | Only relevant at 500K+ vectors; Kinetic will have <10K for the first year. Migrate to dedicated vector DB if needed. |
| Building instead of selling | 3 months of dev, 0 clients | High | **Ship Tier 1 in 3-4 weeks max.** Timebox ruthlessly. The tool should enable consulting, not replace it. |
| Two API providers (OpenAI + Anthropic) | Complexity in billing, key management, debugging | Low | Acceptable for v1; consolidate to one ecosystem in Tier 2 if it causes friction |
| MCP server security | Unauthorized access to Kinetic data | Medium | Access key required on every request; treat key like a password; rotate if compromised |
| Slack webhook reliability | Duplicate captures from retried events | Low | Implement idempotency check (message timestamp deduplication) in edge function |

---

## 11. Open Questions

| Question | Status | Notes |
|----------|--------|-------|
| What does "practice memory" look like technically? | **Resolved** | Two Supabase tables (client_memory, practice_memory) with embedding columns. See Appendix B and Appendix C #9. |
| How should client-facing summaries differ from internal ones? | Open | Define what gets stripped vs. kept. May need a "sensitivity" tag on internal notes. |
| Should the chat interface be global or per-client? | Open | Likely both — global for "what do I know about X" and per-client for "help me think about Client Y's problem." |
| How to handle knowledge item staleness? | Open | Tier 2 feature (relevance decay) but classification taxonomy should account for temporal relevance from the start. |
| What's the right ICP scoring methodology? | Open | Manual 1-5 rating for v1, or define criteria (company size, industry, budget signals) for semi-automated scoring? |
| How to handle meetings with multiple contacts? | **Deferred (v2)** | v1 uses single `contact_id` per meeting. For multi-person meetings, log under primary contact and note others in raw_notes. Junction table (`meeting_contacts`) planned for v2. See limitation note in Appendix B `meetings` table. |
| What MCP tools should be exposed in v1? | **Resolved** | Eight tools: search_kinetic, capture_thought, lookup_contact, read_memory, write_memory, list_follow_ups, set_active_client, get_client_context. See Appendix E. |
| Should quick-capture auto-link to contacts? | **Resolved** | Yes. LLM extracts people mentioned during classification; fuzzy match against contacts table. See quick_captures.linked_contact_id in Appendix B and Story 12 acceptance criteria. |
| How should quick-capture items be classified? | **Resolved** | Stored in `quick_captures` table with LLM-extracted metadata. Can be promoted to knowledge_item or meeting via `promoted_to` field. See Appendix B. |
| pgvector index strategy? | **Resolved** | Start with no index (brute-force scan fine for <10K rows). Add HNSW index per table when query times exceed 200ms. See Appendix B. |

---

## 12. Build Order

### Phase 1: Foundation + Infrastructure (Weeks 1-2)

1. Project setup: Next.js, Supabase schema with pgvector extension (including `patterns` table, expanded memory type enums), Anthropic API connection, shared `INTELLIGENCE_LAYER_PROMPT` module
2. Supabase vector search function (`match_documents` using cosine similarity)
3. Contact CRUD + LinkedIn PDF parsing
4. Meeting logging with AI summary, action items, pain point extraction
5. Embedding pipeline: auto-embed contacts and meetings on create/update
6. Thank-you email generation
7. Follow-up manager (basic — show pending, mark complete)
8. Contact dashboard with search (text + semantic via pgvector)
9. Basic dashboard homepage

### Phase 2: Knowledge, Context & Open Protocol (Weeks 3-4)

10. Knowledge item ingestion (URL fetch, file upload, paste)
11. AI classification, summarization, tagging pipeline
12. Embedding pipeline for knowledge items (chunked, stored with pgvector)
13. Knowledge base browser with semantic search
14. Chat interface for querying knowledge base (includes Intelligence Layer prompt patterns — see Section 5)
15. Client context dashboard (unified client view)
16. Client intake flow
17. Practice memory (basic — structured storage, manual + auto updates)
18. Client-facing summary generation
19. Meeting prep brief generator (prep_briefs table, contact context + knowledge + talking points + Intelligence Layer sections)
20. Weekly review prompt (Tier 1 Feature 8 — structured reflection with Intelligence Layer sections)
21. **MCP server** — Supabase Edge Function exposing: semantic search, quick capture, contact lookup, memory read/write
22. **Slack quick-capture** — Edge Function receiving Slack events, embedding + classifying, storing, and replying with confirmation
23. **Post-Meeting Agent** — Anthropic tool-use agent triggered on meeting log; chains all post-meeting steps autonomously (includes Intelligence Layer steps: assumption extraction, gap detection, pattern writing)
24. **Morning Briefing Agent** — Supabase Edge Function on daily cron; compiles and delivers briefing to Slack DM (includes Intelligence Layer sections: "One Question Worth Asking", "Assumption to Revisit Today", "Gradual Shift Alert")
25. **Pre-Meeting Research Agent** — Edge Function on cron; researches company news 2 hours before each meeting, appends to prep brief (includes Intelligence Layer step: perspective analysis on news)
26. **Folder-aware CLAUDE.md generator** — "Generate CLAUDE.md" action on client records; `set_active_client` + `get_client_context` MCP tools; includes Intelligence Layer instructions
27. Connect MCP server to Claude Desktop and ChatGPT; test folder-aware workflow end-to-end

### Phase 3: Growth & Operational Intelligence (Month 2-3)

28. Goal & priority management per client
29. Frameworks library
30. Opportunity pipeline (manual creation via web app; see Appendix B `opportunities` table)
31. Proposal / SOW generator (consolidates with Proposal Draft Agent)
32. Revenue & utilization tracker
33. **Knowledge Relevance Agent** — on knowledge ingestion; scans active clients for relevance matches
34. **Relationship Health Agent** — weekly cron; scores dormancy, queues re-engagement drafts
35. **Recommendation Engine Agent** — on-demand from client dashboard; searches knowledge + web for solutions to flagged pain points
36. **Deliverable Drafting Agent** — on-demand post-meeting; drafts next deliverable from meeting context + frameworks
37. **Client Check-In Agent** — weekly cron per active client; generates check-in draft with progress references
38. **Pipeline Pulse Agent** — weekly cron; flags stale deals, drafts prioritized pipeline action list
39. **Engagement Wrap-Up Agent** — triggered on engagement close; generates after-action review, updates practice memory
40. **AI Landscape Monitor Agent** — daily/weekly cron; searches for AI news relevant to active client industries, ingests to knowledge base
41. **Knowledge Gap Agent** — pre-meeting or on new pain point; identifies what you don't know, generates study list
42. **Stakeholder Map Agent** — after 3+ client meetings; builds stakeholder map from meeting note analysis
43. **Risk & Blocker Agent** — weekly cron; scans active clients for risk signals, surfaces watch list
44. **Follow-Up Quality Agent** — on-demand pre-send; reviews draft against meeting context, flags generic or missing references

### Phase 4: Integrations & Advanced (Month 4+)

45. Calendar integration (replaces manual upcoming meeting entry)
46. Pattern recognition across meetings
47. Decision / strategy support
48. Communication support
49. Connection matching + warm intro drafts
50. Learning management recommendations
51. **Revenue Snapshot Agent** — weekly cron; pipeline value, hours, revenue, utilization → Slack
52. **Synthesis Agent** — on-demand or weekly; consolidated "state of knowledge" summaries per topic

---

## Appendix A: Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Frontend | Next.js + Tailwind CSS | Single project handles UI + API routes |
| Database + Vector search | Supabase (PostgreSQL + pgvector) | Single database for structured data AND vector embeddings. No separate vector DB. |
| Edge Functions | Supabase Edge Functions (Deno) | Hosts MCP server and Slack quick-capture function. Deployed alongside database. |
| LLM | Anthropic API (Claude) | Summarization, classification, analysis, generation |
| Embeddings | OpenAI text-embedding-3-small (1536 dimensions) | Evaluate Voyage AI as alternative for Anthropic ecosystem consolidation |
| Quick capture | Slack API (Events API + Bot) | Private channel for zero-friction thought capture |
| Open protocol | MCP (Model Context Protocol) | Any MCP-compatible AI client can read from and write to Kinetic via hosted Edge Function |
| Local dev | `npm run dev` | Start local, deploy to Vercel later |
| Auth | None (single user, local) | Add auth layer before hosting. MCP server uses access key. |

### Environment Variables

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
SLACK_BOT_TOKEN=
SLACK_CAPTURE_CHANNEL=
MCP_ACCESS_KEY=
```

Note: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are automatically available inside Supabase Edge Functions and do not need to be set as secrets for the MCP server or Slack function.

---

## Appendix B: Data Model

### Core Entities (Supabase)

**contacts**
- `id` (uuid, PK)
- `name` (text)
- `email` (text, nullable)
- `phone` (text, nullable)
- `company` (text, nullable)
- `title` (text, nullable)
- `linkedin_url` (text, nullable)
- `location` (text, nullable)
- `tags` (text[])
- `relationship_status` (enum: "new", "warm", "active", "dormant")
- `ai_summary` (text)
- `source` (text)
- `notes` (text)
- `icp_fit_score` (integer, nullable, 1-5)
- `embedding` (vector(1536) — auto-generated from ai_summary + profile text)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**meetings**
- `id` (uuid, PK)
- `contact_id` (uuid, FK → contacts) — **v1 limitation: single contact per meeting.** Multi-contact meetings (events, group calls) require a junction table in a future version. For v1, log multi-person meetings under the primary contact and note other attendees in raw_notes.
- `date` (timestamp — when the meeting is scheduled or occurred)
- `status` (enum: "upcoming", "completed", "cancelled" — enables scheduling future meetings for agent triggers)
- `type` (enum: "networking", "discovery_call", "follow_up", "coffee_chat", "event", "other")
- `location` (text, nullable)
- `raw_notes` (text, nullable — null for upcoming meetings until notes are added)
- `ai_summary` (text, nullable — null until Post-Meeting Agent processes)
- `action_items` (jsonb, nullable)
- `key_insights` (text, nullable)
- `pain_points_mentioned` (text[])
- `buying_signals` (text[])
- `thank_you_draft` (text, nullable)
- `client_facing_summary` (text, nullable)
- `embedding` (vector(1536), nullable — auto-generated from raw_notes + ai_summary after meeting is completed)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**knowledge_items**
- `id` (uuid, PK)
- `title` (text)
- `source_url` (text, nullable)
- `source_type` (enum: "article", "youtube_transcript", "podcast_transcript", "video_transcript", "research_paper", "personal_note", "book_notes", "other")
- `raw_content` (text)
- `ai_summary` (text)
- `key_takeaways` (text[])
- `categories` (text[])
- `relevance_tags` (text[])
- `embedding` (vector(1536) — auto-generated from content; chunked items use knowledge_chunks table)
- `created_at` (timestamp)

**opportunities** *(Tier 2, Phase 3 — manual creation via web app in v1; Pipeline Pulse Agent monitors for staleness once opportunities exist)*
- `id` (uuid, PK)
- `contact_id` (uuid, FK → contacts)
- `title` (text)
- `status` (enum: "identified", "exploring", "proposal_sent", "won", "lost", "on_hold")
- `service_type` (text, nullable)
- `estimated_value` (integer, nullable)
- `evidence` (text)
- `next_step` (text)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**follow_ups**
- `id` (uuid, PK)
- `contact_id` (uuid, FK → contacts)
- `meeting_id` (uuid, FK → meetings, nullable)
- `due_date` (date)
- `type` (enum: "thank_you", "check_in", "share_resource", "intro_request", "proposal", "custom")
- `message_draft` (text, nullable)
- `status` (enum: "pending", "sent", "skipped")
- `created_at` (timestamp)

**client_memory**
- `id` (uuid, PK)
- `contact_id` (uuid, FK → contacts)
- `memory_type` (enum: "goal", "preference", "decision", "org_dynamic", "project_status", "constraint", "assumption", "hypothesis", "other")
- `content` (text)
- `source_meeting_id` (uuid, FK → meetings, nullable)
- `is_active` (boolean, default true)
- `embedding` (vector(1536) — auto-generated from content)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**practice_memory**
- `id` (uuid, PK)
- `memory_type` (enum: "framework", "positioning", "pricing", "lesson_learned", "market_observation", "methodology", "pattern_observed", "drift_detected", "bias_noted", "other")
- `content` (text)
- `context` (text, nullable — when/why this was captured)
- `is_active` (boolean, default true)
- `embedding` (vector(1536) — auto-generated from content)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**quick_captures**
- `id` (uuid, PK)
- `content` (text — raw input from Slack or MCP)
- `embedding` (vector(1536) — auto-generated on capture)
- `source_channel` (enum: "slack", "mcp_claude", "mcp_chatgpt", "mcp_cursor", "mcp_other", "web")
- `metadata` (jsonb — LLM-extracted: category, people mentioned, action items, tags)
- `linked_contact_id` (uuid, FK → contacts, nullable — auto-linked if person match found)
- `promoted_to` (text, nullable — if converted to a knowledge_item or meeting, reference the new record)
- `created_at` (timestamp)

### Vector Search (pgvector)

Instead of a separate vector database, all embeddings are stored as columns directly on the tables they describe:

**Embedding columns:**
- `contacts.embedding` (vector(1536)) — embedding of AI summary + profile
- `meetings.embedding` (vector(1536)) — embedding of raw notes + AI summary
- `knowledge_items.embedding` (vector(1536)) — embedding of content (chunked if long)
- `client_memory.embedding` (vector(1536)) — embedding of memory content
- `practice_memory.embedding` (vector(1536)) — embedding of memory content
- `quick_captures.embedding` (vector(1536)) — embedding of raw capture text

**For chunked content** (long knowledge items), a separate `knowledge_chunks` table stores individual chunks with their own embeddings:

**knowledge_chunks**
- `id` (uuid, PK)
- `knowledge_item_id` (uuid, FK → knowledge_items)
- `chunk_index` (integer)
- `content` (text — chunk text)
- `embedding` (vector(1536))
- `created_at` (timestamp)

**patterns** *(Intelligence Layer)*
- `id` (uuid, PK)
- `pattern_type` (enum: "cross_client", "market_trend", "behavioral", "knowledge_gap")
- `description` (text — what the pattern is)
- `evidence` (jsonb — array of source references: meeting_ids, knowledge_item_ids, contact_ids)
- `affected_contacts` (uuid[] — contacts this pattern is relevant to)
- `confidence` (enum: "emerging", "established", "fading")
- `first_detected` (timestamp)
- `last_reinforced` (timestamp)
- `embedding` (vector(1536))
- `created_at` (timestamp)

**prep_briefs**
- `id` (uuid, PK)
- `meeting_id` (uuid, FK → meetings)
- `contact_id` (uuid, FK → contacts)
- `content` (text — full prep brief markdown)
- `recent_news` (text, nullable — appended by Pre-Meeting Research Agent)
- `research_complete` (boolean, default false — prevents duplicate research runs)
- `generated_at` (timestamp)
- `updated_at` (timestamp)

**agent_runs**
- `id` (uuid, PK)
- `agent_name` (text — e.g., "post_meeting_agent", "morning_briefing")
- `trigger_type` (enum: "event", "cron", "on_demand")
- `trigger_ref` (text, nullable — meeting_id, contact_id, or knowledge_item_id that triggered the run)
- `status` (enum: "running", "complete", "failed")
- `steps_completed` (integer)
- `steps_total` (integer)
- `errors` (jsonb, nullable)
- `output_summary` (text, nullable — brief description of what the agent produced)
- `created_at` (timestamp)
- `completed_at` (timestamp, nullable)

**Semantic search function:** A single SQL function (`match_documents`) accepts a query embedding and searches across all tables using cosine similarity (`<=>` operator), returning results ranked by relevance with source type and ID for linking back to full records. Optional parameters filter by source type, client ID, or date range.

**Index strategy:** Start with no index (brute-force scan is fast for <10K rows). Add HNSW index per table when query times exceed 200ms.

---

## Appendix C: Resolved Design Decisions

1. **Vector search: Supabase pgvector, not a dedicated vector DB.** Single database for structured data and embeddings. Eliminates sync complexity, reduces infrastructure dependencies, and is more than sufficient for the expected data volume (<10K vectors in year 1). Migration path to a dedicated vector DB exists if needed later.
2. **Embedding model:** OpenAI `text-embedding-3-small` (1536 dimensions). Evaluate Voyage AI for Anthropic ecosystem consolidation in Tier 2.
3. **Content chunking:** Fixed-size chunks with overlap (~500 tokens per chunk, ~50 token overlap). Chunks stored in `knowledge_chunks` table with their own embeddings. Simple and predictable.
4. **LinkedIn PDF parsing:** Test with real export in Phase 1. Graceful fallback to manual entry.
5. **YouTube transcript ingestion:** URL handler uses `youtube-transcript` npm package (no API key required). Detects YouTube URLs by pattern (`youtube.com/watch` or `youtu.be/`), extracts video ID, fetches captions, strips timestamps, merges into clean paragraphs. Same downstream pipeline as any other knowledge item. Show error gracefully if no transcript is available.
6. **Transcript agnosticism:** Meeting input handles plain text regardless of source (Zoom, Notion, manual). No format-specific parsing.
7. **Knowledge scope:** AI and consulting-related content only. Taxonomy: market intelligence, technical/tools, sales strategy, case studies, industry trends, competitor info, methodology, client pain points, pricing/packaging.
8. **Client data isolation:** Logical separation via client_id foreign keys and pgvector WHERE clause filtering. Physical folder separation for documents.
9. **Memory architecture:** Two Supabase tables (client_memory, practice_memory) with embedding columns for semantic retrieval. Structured fields, not freeform chat history.
10. **MCP server: hosted on Supabase Edge Functions, not local.** One URL, no local dependencies, no build steps, accessible from anywhere. Secured via access key.
11. **Quick capture: Slack as primary channel.** Zero-friction input via a private Slack channel. MCP capture tool provides secondary capture from any AI client. Both feed the same embedding + classification pipeline.
12. **Agent architecture:** All agents run as Supabase Edge Functions using Anthropic tool use (`claude-sonnet-4-5-20250929`). Shared tool library, partial completion on failure, results tracked in `agent_runs` table.
13. **Intelligence Layer as design principle, not feature tier.** The seven capabilities (pattern recognition, generative questioning, perspective shifting, counterfactual reasoning, temporal intelligence, synthesis, intellectual honesty) are embedded in every system prompt, output structure, and agent — not built as separate features. Shared `INTELLIGENCE_LAYER_PROMPT` injected into all LLM calls. Assumptions and hypotheses tracked as client_memory types. Patterns stored in dedicated `patterns` table. Output sections are conditional — they appear only when enough data exists to be grounded.
14. **Folder-aware co-pilot via CLAUDE.md:** Each client folder contains a generated `CLAUDE.md` that instructs Claude Code to call `set_active_client` + `get_client_context` via MCP at session start. This makes the client context available in Claude Code, Cursor, or any MCP-compatible editor without manual re-entry. The `CLAUDE.md` is generated from within the Kinetic web app and regenerated when key client context changes. No local server required — the MCP server handles all context retrieval.

---

## Appendix D: UI Structure

### Visual Design

**Color Scheme:** Predominantly black with teal highlights.

- **Background:** Near-black (`#0a0a0a` or `#111111`) — not pure black; slightly off-black reduces eye strain during long sessions
- **Surface / cards:** Dark gray (`#1a1a1a` or `#1e1e1e`) — creates subtle depth against the background
- **Primary accent:** Teal (`#00b5a3` or similar) — used for interactive elements, active states, CTAs, progress indicators, and key data highlights
- **Secondary accent:** Muted teal/cyan for hover states and secondary interactions
- **Text:** White / light gray (`#f5f5f5`) for primary content; medium gray (`#888888`) for secondary/metadata
- **Borders / dividers:** Subtle dark borders (`#2a2a2a`) — barely visible, just enough to define structure
- **Status colors:** Teal for positive/active, amber for warnings/overdue, red for critical alerts — all desaturated to fit the dark palette

**Design sensibility:** Dense and information-rich, not sparse. This is a professional tool used for hours at a time — prioritize scannability and data density over whitespace. Think terminal-meets-modern-dashboard.

### Navigation

- **Dashboard** — Overview: upcoming follow-ups, recent meetings, latest opportunities, quick-add buttons
- **Contacts** — List, search, filter, detail view
- **Meetings** — List, log new meeting, detail view
- **Knowledge Base** — List, add new, search, chat interface
- **Clients** — Client context dashboards (for active engagements)
- **Chat** — Full-width conversational interface to query everything

### Quick Actions (always accessible)

- Add Contact
- Log Meeting
- Add to Knowledge Base
- Search Everything

---

## Appendix E: API Routes

### Next.js Web App Routes

```
POST   /api/contacts              — Create contact
GET    /api/contacts              — List contacts (with filters)
GET    /api/contacts/:id          — Get contact detail
PUT    /api/contacts/:id          — Update contact
DELETE /api/contacts/:id          — Delete contact

POST   /api/meetings              — Log meeting (triggers automation chain)
GET    /api/meetings              — List meetings
GET    /api/meetings/:id          — Get meeting detail

POST   /api/knowledge             — Add knowledge item (triggers automation chain)
GET    /api/knowledge             — List knowledge items
GET    /api/knowledge/:id         — Get knowledge item detail
POST   /api/knowledge/chat        — Chat with knowledge base

POST   /api/search                — Semantic search across everything (pgvector)
POST   /api/prep/:contactId       — Generate meeting prep brief

GET    /api/follow-ups            — List pending follow-ups
PUT    /api/follow-ups/:id        — Update follow-up status

GET    /api/opportunities         — List opportunities
POST   /api/opportunities         — Create opportunity
PUT    /api/opportunities/:id     — Update opportunity

GET    /api/clients/:id/context   — Get client context dashboard data
POST   /api/clients/:id/intake    — Client intake flow
GET    /api/clients/:id/memory    — Get client memory
POST   /api/clients/:id/memory    — Add client memory item

GET    /api/practice/memory       — Get practice memory
POST   /api/practice/memory       — Add practice memory item

POST   /api/review/weekly         — Generate weekly review
POST   /api/summary/client-facing — Generate client-facing summary from meeting
```

### Supabase Edge Functions

```
POST   /functions/v1/kinetic-mcp    — MCP server (hosted, accessed by AI clients via URL + access key)
         Tools exposed:
         - search_kinetic        — Semantic search across all content (contacts, meetings, knowledge, memory)
         - capture_thought        — Quick capture with auto-embed + classify
         - lookup_contact         — Find a contact by name or company
         - read_memory            — Read client or practice memory
         - write_memory           — Add a memory item (client or practice level)
         - list_follow_ups        — Get pending follow-ups
         - set_active_client      — Accept client_id or client_name; scopes all subsequent calls to that client context
         - get_client_context     — Return full client snapshot: goals, pain points, recent meetings (last 3), open action items, client memory, relevant knowledge items. Used by CLAUDE.md on session start.

POST   /functions/v1/slack-capture          — Slack Events API receiver
         - Receives message events from capture channel
         - Embeds, classifies, stores, and replies with confirmation

POST   /functions/v1/post-meeting-agent     — Post-Meeting Agent (called by web app after meeting is logged)
         - Anthropic tool-use agent; chains all post-meeting steps
         - Tools: summarize, extract_action_items, update_memory, draft_thank_you, create_follow_ups, search_knowledge, flag_patterns
         - Runs asynchronously; updates meeting record with results

GET    /functions/v1/morning-briefing            — Morning Briefing Agent (triggered by cron; also callable on demand)
         - Fetches today's meetings, overdue follow-ups, recent knowledge items
         - Generates prep briefs per meeting
         - Sends compiled briefing to Slack DM

GET    /functions/v1/pre-meeting-research        — Pre-Meeting Research Agent (cron every 30 min; checks for meetings starting in 2 hours)
         - Web searches company news for upcoming meeting contacts
         - Appends "Recent Company News" section to prep brief
         - Sends Slack notification when complete

POST   /functions/v1/knowledge-relevance-agent   — Knowledge Relevance Agent (called after knowledge item ingested)
         - Scans active clients for relevance to new knowledge item
         - Flags matches with contact/meeting references

GET    /functions/v1/relationship-health-agent   — Relationship Health Agent (weekly cron)
         - Scores dormancy across all contacts
         - Queues re-engagement drafts for review

GET    /functions/v1/pipeline-pulse-agent        — Pipeline Pulse Agent (weekly cron)
         - Flags stale opportunities
         - Drafts prioritized pipeline action list, delivers to Slack

GET    /functions/v1/ai-landscape-monitor        — AI Landscape Monitor Agent (daily/weekly cron)
         - Searches for AI news relevant to active client industries
         - Auto-ingests top findings into knowledge base with summaries

GET    /functions/v1/risk-blocker-agent          — Risk & Blocker Agent (weekly cron)
         - Scans active clients for risk signals (silence, unresolved objections, missed commitments)
         - Surfaces watch list with suggested actions, delivers to Slack
```
