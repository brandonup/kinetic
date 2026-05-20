# UI Reference Guide: Claude Cowork → Kinetic

**Type:** UI Reference Guide
**Date:** 2026-03-26
**Author:** Jared (Product)
**Status:** Active
**Related tickets:** KIN-380, KIN-381, KIN-383

---

## Purpose

This document maps Claude cowork's UI patterns to Kinetic's feature set. The dev team should use this as the primary visual and structural reference when building the project chat page (KIN-383), agent chat page (KIN-381), and global sidebar (KIN-380).

Kinetic is not copying Claude cowork pixel-for-pixel. We're adopting its **layout structure, interaction patterns, and information hierarchy** while adapting the right panel to Kinetic's domain (agents, frameworks, active memory, KB).

---

## Claude Cowork Layout — Three-Panel Structure

Claude cowork uses a persistent three-panel layout:

```
┌──────────────┬────────────────────────────────┬──────────────────────┐
│              │                                │                      │
│  Left        │  Center                        │  Right               │
│  Sidebar     │  Panel                         │  Panel               │
│  (~240px)    │  (flex, fills remaining)       │  (~320px)            │
│              │                                │                      │
│  Global      │  Page-specific                 │  Page-specific       │
│  Persists    │  Changes per route             │  Changes per route   │
│  across      │                                │                      │
│  all pages   │                                │                      │
│              │                                │                      │
└──────────────┴────────────────────────────────┴──────────────────────┘
```

---

## Panel 1: Left Sidebar (Global, Persistent)

### Claude Cowork

| Section | Contents |
|---|---|
| **Top actions** | New task, Search, Scheduled, Dispatch, Ideas, Customize |
| **Projects** | Collapsible list of all projects with `+` button. Active project highlighted. |
| **Scheduled** | Scheduled/recurring tasks for the active project. Blue dot = pending. |
| **Recents** | All recent conversations across all projects. Truncated title, no timestamp. |

**Key patterns:**
- Sidebar is fixed-width (~240px), full viewport height
- Projects list is collapsible with a section header
- Recents fills remaining vertical space with a scroll area
- Active project gets visual highlight (background color change)
- Clicking a project navigates to the project home view (center + right panels change)
- Clicking a recent conversation navigates to that conversation within its project

### Kinetic Adaptation

| Section | Contents | Notes |
|---|---|---|
| **Company switcher** | Dropdown at top — select active company | Already built (`AppSidebar.tsx`). No change. |
| **Main nav** | Companies, Projects, Agents, Profile — icon + label links | Already built. No change. |
| **Projects** | Truncated list (max 5) of projects for active company, sorted by recency | NEW. `+` button or "View all" link. Active project highlighted. |
| **Conversations** | Recent conversations across all projects and agents (max 10), sorted by recency | UPDATE existing placeholder. Each item: title + parent context (project/agent name). |
| **Sign out** | Sign out button at bottom | Already built. No change. |

**What we skip from Claude:** New task, Search, Scheduled, Dispatch, Ideas, Customize top actions. These are Claude-specific features we don't need.

**Component:** `AppSidebar.tsx` — extend existing component.

---

## Panel 2: Center Panel (Page-Specific)

### Claude Cowork — Project Home

| Element | Description |
|---|---|
| **Project title** | Large text at top of panel, with `...` overflow menu |
| **Chat input** | Prominent input field: "What would you like to work on in this project?" |
| **Input controls** | Below/inside the input: project name tag, `+` button (attachments), folder icon, model selector dropdown ("Sonnet 4.6"), microphone button |
| **Recents** | Section header "Recents". List of recent conversations from this project only. Each item: title, relative timestamp ("14 hours ago"), preview of last message. Scheduled conversations show a badge. |

**Key patterns:**
- Chat input is the primary CTA — it's the first thing the user sees after the title
- Model selector is inside/adjacent to the chat input, not in a settings page
- Recents are project-scoped (not global — global recents are in the sidebar)
- Clicking a recent conversation replaces the home view with the full message thread
- Message thread view: scrollable messages, chat input at bottom, back navigation to project home

### Kinetic Adaptation — Project Chat Page (KIN-383)

| Element | Kinetic version | Notes |
|---|---|---|
| **Project title** | Large text at top | Same pattern |
| **Chat input** | "What would you like to work on in this project?" | Same pattern |
| **Input controls** | Project name tag + `ModelSelector` component (already built) | Skip: microphone, folder icon. Keep: model selector, attachment button. |
| **Recents** | Recent conversations from this project (max 20) | Same pattern: title, timestamp, preview |
| **Active conversation** | Full message thread with chat input at bottom | Same pattern: scrollable messages, agent badge on AI messages if agent active |

### Kinetic Adaptation — Agent Chat Page (KIN-381)

Same center panel structure, but scoped to an agent instead of a project:

| Element | Kinetic version |
|---|---|
| **Agent name + type badge** | Large text at top (e.g., "Nate Jones" with `custom` badge) |
| **Chat input** | "Chat with [agent name]..." |
| **Input controls** | Agent name tag + `ModelSelector` |
| **Recents** | Recent conversations with this agent (max 20) |
| **Active conversation** | Full message thread, AI messages show agent name badge |

---

## Panel 3: Right Panel (Page-Specific)

### Claude Cowork — Project View

| Section | Contents |
|---|---|
| **Instructions** | Project system prompt (role, context, behavioral instructions). Edit icon. "Show more" expand. |
| **Scheduled** | Scheduled/recurring tasks with Active/Inactive badges, frequency labels. `+` button to add. |
| **Context** | Three subsections: "On your computer" (local folders), "Memory" (Claude memory entries), "Projects from Chat" (linked projects). Each with `+` button. |

**Key patterns:**
- Each section is a collapsible accordion with a header and optional action button (`+`, edit icon)
- Sections are stacked vertically with clear visual separation
- Content within sections is compact — truncated text with "Show more" expansion
- The right panel provides at-a-glance context about what's loaded into the conversation

### Kinetic Adaptation — Project Chat Right Panel (KIN-383)

| Section | Claude equivalent | Kinetic contents |
|---|---|---|
| **Agents** (TOP) | _No direct equivalent_ | List of available agents. Click to activate/deactivate. Active badge. One at a time. |
| **Instructions** | Instructions | Project instructions (Layer 3). Inline editable. Token count. |
| **Active Memory** | Memory (under Context) | Per-project active memory entries (Layer 4). Add/edit/delete. Token count with cap indicator. |
| **Knowledge Base** | Context > On your computer | Project KB documents. Upload button. Processing status badges. |

### Kinetic Adaptation — Agent Chat Right Panel (KIN-381)

| Section | Claude equivalent | Kinetic contents |
|---|---|---|
| **Instructions** | Instructions | Agent system prompt (Layer 5). Read-only in chat view. "Edit in Settings" link. |
| **Knowledge Base** | Context > On your computer | Agent KB documents. Upload button. Status badges. |
| **Frameworks** | _No direct equivalent_ | Agent framework library (Layer 7). Framework name, category, description. Read-only. |
| **Active Memory** | Memory (under Context) | Per-user agent instance memory (Layer 6). Add/edit/delete. Token count. |

---

## Interaction Patterns to Adopt

### 1. Chat-First Project Experience

In Claude cowork, clicking a project doesn't open a settings page — it opens a **chat-ready view**. The chat input is the hero element. Kinetic should do the same: `/projects/<id>` is a chat page, not a form.

### 2. Inline Context Visibility

The right panel shows what context is loaded into the conversation **without navigating away**. Users can see instructions, memory, and documents while chatting. This is critical for Kinetic where the context stack determines AI behavior.

### 3. Global Navigation + Contextual Panels

The left sidebar is the **same on every page** (navigation). The center and right panels **change per page** (content). This keeps orientation consistent — users always know where they are.

### 4. Recents as Navigation

Recent conversations serve as both a history view and a navigation pattern. Claude shows them in two places: sidebar (global, all projects) and center panel (scoped to current project/agent).

### 5. Collapsible Accordion Sections

Right panel sections use collapsible accordions — expanded by default, collapsible to save space. Each section has a header with an action button (`+`, edit, count badge).

### 6. Model Selector in Chat Input

The model selector is adjacent to the chat input, not buried in settings. This makes model choice a per-conversation decision, which matches Kinetic's `ModelSelector` component (already built).

---

## Patterns We Do NOT Adopt

| Claude pattern | Why we skip it |
|---|---|
| Scheduled tasks / recurring prompts | Not in Kinetic MVP scope |
| Dispatch / Ideas / Customize nav items | Claude-specific features, no Kinetic equivalent |
| Artifact/preview panel (code, React, SVG rendering) | Kinetic is not a code generation tool — the right panel is for context, not output |
| File tree / workspace view | Kinetic doesn't have a virtual filesystem |
| "Projects from Chat" linking | Kinetic projects are explicit, not inferred from conversation |
| Microphone input | Not in scope |
| Conversation branching (edit + retry) | Not in MVP |

---

## Component Mapping

| Claude component | Kinetic component | Status |
|---|---|---|
| Left sidebar | `AppSidebar.tsx` | Exists — extend with projects list + conversations list |
| Company/org switcher | Company switcher in `AppSidebar` | Exists — no change |
| Model selector | `ModelSelector.tsx` | Exists — reuse in chat input |
| Chat input | New: `ChatInput.tsx` | Build new — text field + model selector + project/agent tag |
| Message thread | New: `MessageThread.tsx` | Build new — user + AI messages, streaming, agent badges |
| Right panel accordion | New: `ContextPanel.tsx` with `AccordionSection` children | Build new — collapsible sections |
| Instructions editor | New: `InstructionsEditor.tsx` | Build new — inline edit for project, read-only for agent chat |
| Active memory list | New: `ActiveMemoryPanel.tsx` | Build new — entries + add/edit/delete + token count |
| KB document list | Existing: `KnowledgeBaseTab.tsx` | Exists — adapt for right panel layout |
| Agent selector | New: `AgentSelector.tsx` | Build new — list with activate/deactivate |
| Agent card (list page) | New: `AgentCard.tsx` | Build new — name, badges, Chat/Settings/Delete actions |
| Conversation list item | New: `ConversationItem.tsx` | Build new — title, timestamp, preview, parent context |
| Skeleton loaders | New or existing | Build per-section skeleton placeholders |

---

## Visual Design Notes

Kinetic already uses a dark theme with teal accents. Adopt these Claude cowork patterns within the existing Kinetic design system:

- **Max-width container** for center panel messages (~720px) for readability
- **Generous whitespace** between messages and sections
- **Rounded corners** on cards, message bubbles, accordion headers
- **Muted text** for secondary information (timestamps, subtitles, token counts)
- **Accent color** (teal) for active states, selected items, CTAs
- **Skeleton placeholders** during loading — match the shape of the content they'll replace

---

## References

- Screenshot provided by Brandon, 2026-03-26 (Claude cowork project view for "AI-Evolution Program")
- Kinetic PRD §5 (Conversations), §6 (Agents), §7 (Knowledge Base)
- Existing components: `AppSidebar.tsx`, `ModelSelector.tsx`, `KnowledgeBaseTab.tsx`
