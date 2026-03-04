# Kinetic Phase 1: Foundation Implementation Plan

> **For Claude:** Invoke these skills at the tasks indicated. Do not skip them — they are not optional.
>
> | Task | Skill | Purpose |
> |---|---|---|
> | Task 1 (start) | `executing-plans` | Sets the execution pattern for all tasks |
> | Task 3 | `supabase-postgres-best-practices` | Schema is the foundation — get it right before writing SQL |
> | Task 12 | `web-design-guidelines` → `brainstorming` | Before any UI/CSS work |
> | Task 13 | `brainstorming` → `frontend-design` | Before building contact components |
> | Task 14 | `frontend-design` | Before building dashboard components |
> | Phase 1 Complete | `verification-before-completion` | Before marking the phase done |
> | Any blocker | `systematic-debugging` | When stuck on a bug — don't improvise |

**Goal:** Build the complete data layer, shared infrastructure, API routes, and basic UI for contacts, meetings, follow-ups, and the dashboard home — the full foundation that every other Kinetic feature depends on.

**Architecture:** Next.js 15 App Router with TypeScript serves both the UI and API routes. Supabase provides PostgreSQL + pgvector for structured data and semantic search in one database. All LLM calls (Anthropic Claude) and embedding calls (OpenAI text-embedding-3-small) run server-side. The `INTELLIGENCE_LAYER_PROMPT` is baked into every LLM system prompt from day one — never omit it.

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS, Supabase (`@supabase/supabase-js`), Anthropic API (`@anthropic-ai/sdk`), OpenAI API (`openai` — embeddings only), `pdf-parse`, Vitest + `@testing-library/react`

**Design System:** Dark theme — background `#0a0a0a`, surface `#1a1a1a`, teal accent `#00b5a3`, text `#f5f5f5`, secondary text `#888888`, borders `#2a2a2a`. Dense, information-rich layout — think terminal-meets-modern-dashboard.

**Before starting:** Read `docs/prd-kinetic-v2.md` (master PRD), `docs/plans/2026-03-04-intelligence-layer-design.md`, and Appendix B of the PRD for the full data model and Appendix E for all API routes.

**Covers PRD Build Order Steps:** 1–9

---

## Task 1: Project Initialization

> **Skill:** Invoke `executing-plans` before starting. It sets the task-by-task execution pattern you must follow for all 14 tasks.

**Files:**
- Create: `package.json` (via create-next-app)
- Create: `.env.local`
- Create: `vitest.config.ts`
- Create: `vitest.setup.ts`

**Step 1: Scaffold the Next.js project**

Run from inside the `kinetic/` directory (which already contains `docs/` — that's fine, create-next-app with `.` will add to an existing folder):

```bash
npx create-next-app@latest . --typescript --tailwind --app --src-dir --import-alias "@/*" --no-git --yes
```

Expected: Next.js project scaffolded with `src/app/`, `src/` structure, `tailwind.config.ts`, `tsconfig.json`.

**Step 2: Install dependencies**

```bash
npm install @supabase/supabase-js @anthropic-ai/sdk openai pdf-parse
npm install -D vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @types/pdf-parse jsdom
```

Expected: `node_modules/` populated, no errors.

**Step 3: Create `.env.local`**

```bash
cat > .env.local << 'EOF'
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
NEXT_PUBLIC_APP_URL=http://localhost:3000
EOF
```

**Step 4: Create `vitest.config.ts`**

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

**Step 5: Create `vitest.setup.ts`**

```typescript
// vitest.setup.ts
import '@testing-library/jest-dom'
```

**Step 6: Add test script to `package.json`**

In `package.json`, add to the `scripts` section:
```json
"test": "vitest",
"test:run": "vitest run"
```

**Step 7: Verify dev server starts**

```bash
npm run dev
```

Expected: `http://localhost:3000` serves the default Next.js page. Stop with Ctrl+C.

**Step 8: Commit**

```bash
git init
git add -A
git commit -m "feat: initialize Next.js project with Tailwind, Supabase, Anthropic, Vitest"
```

---

## Task 2: TypeScript Types

**Files:**
- Create: `src/types/index.ts`
- Create: `src/types/api.ts`

**Step 1: Create `src/types/index.ts`**

These mirror the Supabase schema exactly. Every table has a corresponding type.

```typescript
// src/types/index.ts

export type RelationshipStatus = 'new' | 'warm' | 'active' | 'dormant'
export type MeetingStatus = 'upcoming' | 'completed' | 'cancelled'
export type MeetingType = 'networking' | 'discovery_call' | 'follow_up' | 'coffee_chat' | 'event' | 'other'
export type KnowledgeSourceType = 'article' | 'youtube_transcript' | 'podcast_transcript' | 'video_transcript' | 'research_paper' | 'personal_note' | 'book_notes' | 'other'
export type OpportunityStatus = 'identified' | 'exploring' | 'proposal_sent' | 'won' | 'lost' | 'on_hold'
export type FollowUpType = 'thank_you' | 'check_in' | 'share_resource' | 'intro_request' | 'proposal' | 'custom'
export type FollowUpStatus = 'pending' | 'sent' | 'skipped'
export type ClientMemoryType = 'goal' | 'preference' | 'decision' | 'org_dynamic' | 'project_status' | 'constraint' | 'assumption' | 'hypothesis' | 'other'
export type PracticeMemoryType = 'framework' | 'positioning' | 'pricing' | 'lesson_learned' | 'market_observation' | 'methodology' | 'pattern_observed' | 'drift_detected' | 'bias_noted' | 'other'
export type QuickCaptureSource = 'slack' | 'mcp_claude' | 'mcp_chatgpt' | 'mcp_cursor' | 'mcp_other' | 'web'
export type PatternType = 'cross_client' | 'market_trend' | 'behavioral' | 'knowledge_gap'
export type PatternConfidence = 'emerging' | 'established' | 'fading'
export type AgentTriggerType = 'event' | 'cron' | 'on_demand'
export type AgentStatus = 'running' | 'complete' | 'failed'

export interface Contact {
  id: string
  name: string
  email: string | null
  phone: string | null
  company: string | null
  title: string | null
  linkedin_url: string | null
  location: string | null
  tags: string[]
  relationship_status: RelationshipStatus
  ai_summary: string
  source: string
  notes: string
  icp_fit_score: number | null
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface Meeting {
  id: string
  contact_id: string
  date: string
  status: MeetingStatus
  type: MeetingType
  location: string | null
  raw_notes: string | null
  ai_summary: string | null
  action_items: ActionItem[] | null
  key_insights: string | null
  pain_points_mentioned: string[]
  buying_signals: string[]
  thank_you_draft: string | null
  client_facing_summary: string | null
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface ActionItem {
  text: string
  due_date: string | null
  priority: 'high' | 'medium' | 'low'
}

export interface FollowUp {
  id: string
  contact_id: string
  meeting_id: string | null
  due_date: string
  type: FollowUpType
  message_draft: string | null
  status: FollowUpStatus
  created_at: string
}

export interface KnowledgeItem {
  id: string
  title: string
  source_url: string | null
  source_type: KnowledgeSourceType
  raw_content: string
  ai_summary: string
  key_takeaways: string[]
  categories: string[]
  relevance_tags: string[]
  embedding: number[] | null
  created_at: string
}

export interface Opportunity {
  id: string
  contact_id: string
  title: string
  status: OpportunityStatus
  service_type: string | null
  estimated_value: number | null
  evidence: string
  next_step: string
  created_at: string
  updated_at: string
}

export interface ClientMemory {
  id: string
  contact_id: string
  memory_type: ClientMemoryType
  content: string
  source_meeting_id: string | null
  is_active: boolean
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface PracticeMemory {
  id: string
  memory_type: PracticeMemoryType
  content: string
  context: string | null
  is_active: boolean
  embedding: number[] | null
  created_at: string
  updated_at: string
}

export interface Pattern {
  id: string
  pattern_type: PatternType
  description: string
  evidence: Array<{ type: string; id: string }>
  affected_contacts: string[]
  confidence: PatternConfidence
  first_detected: string
  last_reinforced: string
  embedding: number[] | null
  created_at: string
}

export interface PrepBrief {
  id: string
  meeting_id: string
  contact_id: string
  content: string
  recent_news: string | null
  research_complete: boolean
  generated_at: string
  updated_at: string
}

export interface AgentRun {
  id: string
  agent_name: string
  trigger_type: AgentTriggerType
  trigger_ref: string | null
  status: AgentStatus
  steps_completed: number
  steps_total: number
  errors: unknown | null
  output_summary: string | null
  created_at: string
  completed_at: string | null
}

export interface QuickCapture {
  id: string
  content: string
  embedding: number[] | null
  source_channel: QuickCaptureSource
  metadata: {
    category?: string
    people_mentioned?: string[]
    action_items?: string[]
    tags?: string[]
  }
  linked_contact_id: string | null
  promoted_to: string | null
  created_at: string
}

export interface SearchResult {
  id: string
  source_table: string
  content: string
  metadata: Record<string, unknown>
  similarity: number
}
```

**Step 2: Create `src/types/api.ts`**

```typescript
// src/types/api.ts
// Request/response shapes for API routes

export interface CreateContactRequest {
  name: string
  email?: string
  phone?: string
  company?: string
  title?: string
  linkedin_url?: string
  location?: string
  source?: string
  notes?: string
  tags?: string[]
}

export interface UpdateContactRequest {
  name?: string
  email?: string
  phone?: string
  company?: string
  title?: string
  linkedin_url?: string
  location?: string
  source?: string
  notes?: string
  tags?: string[]
  relationship_status?: import('./index').RelationshipStatus
  icp_fit_score?: number
}

export interface CreateMeetingRequest {
  contact_id: string
  date: string
  type?: import('./index').MeetingType
  location?: string
  status?: import('./index').MeetingStatus
  raw_notes?: string
}

export interface UpdateFollowUpRequest {
  status: import('./index').FollowUpStatus
}

export interface ApiError {
  error: string
  details?: string
}
```

**Step 3: Write a type smoke test**

```typescript
// src/types/index.test.ts
import { describe, it, expect } from 'vitest'
import type { Contact, Meeting, FollowUp } from './index'

describe('types', () => {
  it('Contact type has required fields', () => {
    const contact: Contact = {
      id: 'test-id',
      name: 'Jane Smith',
      email: null,
      phone: null,
      company: 'Acme',
      title: null,
      linkedin_url: null,
      location: null,
      tags: [],
      relationship_status: 'new',
      ai_summary: '',
      source: '',
      notes: '',
      icp_fit_score: null,
      embedding: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    expect(contact.name).toBe('Jane Smith')
  })
})
```

**Step 4: Run the type test**

```bash
npm run test:run -- src/types/index.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/types/ vitest.config.ts vitest.setup.ts
git commit -m "feat: add TypeScript types for all database entities and API shapes"
```

---

## Task 3: Supabase Schema Migration

> **Skill:** Invoke `supabase-postgres-best-practices` before writing any SQL. The schema is the hardest thing to change later — RLS, indexing strategy, and pgvector configuration must be right from the start.

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`
- Create: `supabase/migrations/002_match_documents.sql`

**Step 1: Create the migrations directory**

```bash
mkdir -p supabase/migrations
```

**Step 2: Create `supabase/migrations/001_initial_schema.sql`**

```sql
-- supabase/migrations/001_initial_schema.sql
-- Enable pgvector for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- ENUMS
-- ============================================================
CREATE TYPE relationship_status AS ENUM ('new', 'warm', 'active', 'dormant');
CREATE TYPE meeting_status AS ENUM ('upcoming', 'completed', 'cancelled');
CREATE TYPE meeting_type AS ENUM ('networking', 'discovery_call', 'follow_up', 'coffee_chat', 'event', 'other');
CREATE TYPE knowledge_source_type AS ENUM ('article', 'youtube_transcript', 'podcast_transcript', 'video_transcript', 'research_paper', 'personal_note', 'book_notes', 'other');
CREATE TYPE opportunity_status AS ENUM ('identified', 'exploring', 'proposal_sent', 'won', 'lost', 'on_hold');
CREATE TYPE follow_up_type AS ENUM ('thank_you', 'check_in', 'share_resource', 'intro_request', 'proposal', 'custom');
CREATE TYPE follow_up_status AS ENUM ('pending', 'sent', 'skipped');
CREATE TYPE client_memory_type AS ENUM ('goal', 'preference', 'decision', 'org_dynamic', 'project_status', 'constraint', 'assumption', 'hypothesis', 'other');
CREATE TYPE practice_memory_type AS ENUM ('framework', 'positioning', 'pricing', 'lesson_learned', 'market_observation', 'methodology', 'pattern_observed', 'drift_detected', 'bias_noted', 'other');
CREATE TYPE quick_capture_source AS ENUM ('slack', 'mcp_claude', 'mcp_chatgpt', 'mcp_cursor', 'mcp_other', 'web');
CREATE TYPE pattern_type AS ENUM ('cross_client', 'market_trend', 'behavioral', 'knowledge_gap');
CREATE TYPE pattern_confidence AS ENUM ('emerging', 'established', 'fading');
CREATE TYPE agent_trigger_type AS ENUM ('event', 'cron', 'on_demand');
CREATE TYPE agent_status_enum AS ENUM ('running', 'complete', 'failed');

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  company TEXT,
  title TEXT,
  linkedin_url TEXT,
  location TEXT,
  tags TEXT[] DEFAULT '{}',
  relationship_status relationship_status DEFAULT 'new',
  ai_summary TEXT DEFAULT '',
  source TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  icp_fit_score INTEGER CHECK (icp_fit_score BETWEEN 1 AND 5),
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- v1 limitation: single contact per meeting.
-- For multi-person meetings, log under primary contact and note others in raw_notes.
-- A junction table (meeting_contacts) is planned for v2.
CREATE TABLE meetings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  date TIMESTAMPTZ NOT NULL,
  status meeting_status DEFAULT 'upcoming',
  type meeting_type DEFAULT 'other',
  location TEXT,
  raw_notes TEXT,
  ai_summary TEXT,
  action_items JSONB,
  key_insights TEXT,
  pain_points_mentioned TEXT[] DEFAULT '{}',
  buying_signals TEXT[] DEFAULT '{}',
  thank_you_draft TEXT,
  client_facing_summary TEXT,
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  source_url TEXT,
  source_type knowledge_source_type DEFAULT 'article',
  raw_content TEXT NOT NULL,
  ai_summary TEXT DEFAULT '',
  key_takeaways TEXT[] DEFAULT '{}',
  categories TEXT[] DEFAULT '{}',
  relevance_tags TEXT[] DEFAULT '{}',
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tier 2 / Phase 3 — manual creation via web app in v1.
-- Pipeline Pulse Agent monitors for staleness once opportunities exist.
CREATE TABLE opportunities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status opportunity_status DEFAULT 'identified',
  service_type TEXT,
  estimated_value INTEGER,
  evidence TEXT DEFAULT '',
  next_step TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE follow_ups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,
  due_date DATE NOT NULL,
  type follow_up_type DEFAULT 'custom',
  message_draft TEXT,
  status follow_up_status DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE client_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  memory_type client_memory_type DEFAULT 'other',
  content TEXT NOT NULL,
  source_meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,
  is_active BOOLEAN DEFAULT TRUE,
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE practice_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_type practice_memory_type DEFAULT 'other',
  content TEXT NOT NULL,
  context TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE quick_captures (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content TEXT NOT NULL,
  embedding vector(1536),
  source_channel quick_capture_source DEFAULT 'web',
  metadata JSONB DEFAULT '{}',
  linked_contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
  promoted_to TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  knowledge_item_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Intelligence Layer: first-class data structure for detected patterns
CREATE TABLE patterns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pattern_type pattern_type NOT NULL,
  description TEXT NOT NULL,
  evidence JSONB DEFAULT '[]',
  affected_contacts UUID[] DEFAULT '{}',
  confidence pattern_confidence DEFAULT 'emerging',
  first_detected TIMESTAMPTZ DEFAULT NOW(),
  last_reinforced TIMESTAMPTZ DEFAULT NOW(),
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE prep_briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id UUID REFERENCES meetings(id) ON DELETE CASCADE,
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  content TEXT NOT NULL DEFAULT '',
  recent_news TEXT,
  research_complete BOOLEAN DEFAULT FALSE,
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name TEXT NOT NULL,
  trigger_type agent_trigger_type DEFAULT 'event',
  trigger_ref TEXT,
  status agent_status_enum DEFAULT 'running',
  steps_completed INTEGER DEFAULT 0,
  steps_total INTEGER DEFAULT 0,
  errors JSONB,
  output_summary TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_contacts_relationship_status ON contacts(relationship_status);
CREATE INDEX idx_contacts_company ON contacts(company);
CREATE INDEX idx_meetings_contact_id ON meetings(contact_id);
CREATE INDEX idx_meetings_status ON meetings(status);
CREATE INDEX idx_meetings_date ON meetings(date);
CREATE INDEX idx_follow_ups_contact_id ON follow_ups(contact_id);
CREATE INDEX idx_follow_ups_status ON follow_ups(status);
CREATE INDEX idx_follow_ups_due_date ON follow_ups(due_date);
CREATE INDEX idx_client_memory_contact_id ON client_memory(contact_id);
CREATE INDEX idx_client_memory_type ON client_memory(memory_type);
CREATE INDEX idx_knowledge_chunks_item_id ON knowledge_chunks(knowledge_item_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_created_at ON agent_runs(created_at DESC);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_contacts_updated_at
  BEFORE UPDATE ON contacts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_meetings_updated_at
  BEFORE UPDATE ON meetings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_opportunities_updated_at
  BEFORE UPDATE ON opportunities FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_client_memory_updated_at
  BEFORE UPDATE ON client_memory FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_practice_memory_updated_at
  BEFORE UPDATE ON practice_memory FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_prep_briefs_updated_at
  BEFORE UPDATE ON prep_briefs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**Step 3: Create `supabase/migrations/002_match_documents.sql`**

```sql
-- supabase/migrations/002_match_documents.sql
-- Unified semantic search across contacts, meetings, knowledge, and memory.
-- Returns results ranked by cosine similarity.
-- No index needed yet (brute-force scan is fast for < 10K rows).
-- Add HNSW index per table when query times exceed 200ms.

CREATE OR REPLACE FUNCTION match_documents(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10,
  filter_source text DEFAULT NULL  -- pass 'contacts', 'meetings', 'knowledge_items', or NULL for all
)
RETURNS TABLE (
  id uuid,
  source_table text,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT id, 'contacts'::text AS source_table,
    ai_summary AS content,
    jsonb_build_object(
      'name', name,
      'company', company,
      'relationship_status', relationship_status::text
    ) AS metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM contacts
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) > match_threshold
    AND (filter_source IS NULL OR filter_source = 'contacts')

  UNION ALL

  SELECT id, 'meetings'::text AS source_table,
    COALESCE(ai_summary, raw_notes, '') AS content,
    jsonb_build_object(
      'contact_id', contact_id::text,
      'date', date::text,
      'type', type::text,
      'status', status::text
    ) AS metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM meetings
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) > match_threshold
    AND (filter_source IS NULL OR filter_source = 'meetings')

  UNION ALL

  SELECT id, 'knowledge_items'::text AS source_table,
    COALESCE(ai_summary, raw_content, '') AS content,
    jsonb_build_object(
      'title', title,
      'source_type', source_type::text
    ) AS metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM knowledge_items
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) > match_threshold
    AND (filter_source IS NULL OR filter_source = 'knowledge_items')

  UNION ALL

  SELECT id, 'client_memory'::text AS source_table,
    content,
    jsonb_build_object(
      'contact_id', contact_id::text,
      'memory_type', memory_type::text
    ) AS metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM client_memory
  WHERE embedding IS NOT NULL
    AND is_active = TRUE
    AND 1 - (embedding <=> query_embedding) > match_threshold
    AND (filter_source IS NULL OR filter_source = 'client_memory')

  ORDER BY similarity DESC
  LIMIT match_count;
$$;
```

**Step 4: Apply the migrations to your Supabase project**

Go to your Supabase project → SQL Editor → paste and run `001_initial_schema.sql`, then `002_match_documents.sql`.

Verify in Table Editor: all 13 tables appear (contacts, meetings, knowledge_items, opportunities, follow_ups, client_memory, practice_memory, quick_captures, knowledge_chunks, patterns, prep_briefs, agent_runs, plus the function).

**Step 5: Commit**

```bash
git add supabase/
git commit -m "feat: add full Supabase schema with pgvector and match_documents function"
```

---

## Task 4: Shared Infrastructure (lib/)

**Files:**
- Create: `src/lib/supabase.ts`
- Create: `src/lib/anthropic.ts`
- Create: `src/lib/openai.ts`

**Step 1: Create `src/lib/supabase.ts`**

Single-user, no auth in v1. Uses service role key everywhere (server-side only).

```typescript
// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

if (!process.env.SUPABASE_URL) throw new Error('Missing SUPABASE_URL')
if (!process.env.SUPABASE_SERVICE_ROLE_KEY) throw new Error('Missing SUPABASE_SERVICE_ROLE_KEY')

// Server-only Supabase client with service role (bypasses RLS).
// Do NOT expose this key client-side.
export const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  {
    auth: { persistSession: false },
  }
)
```

**Step 2: Create `src/lib/anthropic.ts`**

```typescript
// src/lib/anthropic.ts
import Anthropic from '@anthropic-ai/sdk'

if (!process.env.ANTHROPIC_API_KEY) throw new Error('Missing ANTHROPIC_API_KEY')

export const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
})

/**
 * Make a single-turn LLM call. Always pass the INTELLIGENCE_LAYER_PROMPT as part of systemPrompt.
 * Model: claude-sonnet-4-5-20250929 for all substantive calls.
 * Use 'claude-haiku-4-5-20251001' for lightweight classification/extraction.
 */
export async function callLLM({
  systemPrompt,
  userMessage,
  model = 'claude-sonnet-4-5-20250929',
  maxTokens = 2048,
}: {
  systemPrompt: string
  userMessage: string
  model?: string
  maxTokens?: number
}): Promise<string> {
  const message = await anthropic.messages.create({
    model,
    max_tokens: maxTokens,
    system: systemPrompt,
    messages: [{ role: 'user', content: userMessage }],
  })

  const block = message.content[0]
  if (block.type !== 'text') throw new Error('Unexpected non-text response from LLM')
  return block.text
}
```

**Step 3: Create `src/lib/openai.ts`**

```typescript
// src/lib/openai.ts
import OpenAI from 'openai'

if (!process.env.OPENAI_API_KEY) throw new Error('Missing OPENAI_API_KEY')

export const openaiClient = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
})
```

**Step 4: Commit**

```bash
git add src/lib/supabase.ts src/lib/anthropic.ts src/lib/openai.ts
git commit -m "feat: add Supabase, Anthropic, and OpenAI client wrappers"
```

---

## Task 5: Intelligence Layer Prompt Module

**Files:**
- Create: `src/lib/intelligence-layer.ts`
- Create: `src/lib/intelligence-layer.test.ts`

**Step 1: Write the failing test first**

```typescript
// src/lib/intelligence-layer.test.ts
import { describe, it, expect } from 'vitest'
import { INTELLIGENCE_LAYER_PROMPT, buildSystemPrompt } from './intelligence-layer'

describe('INTELLIGENCE_LAYER_PROMPT', () => {
  it('is a non-empty string', () => {
    expect(typeof INTELLIGENCE_LAYER_PROMPT).toBe('string')
    expect(INTELLIGENCE_LAYER_PROMPT.length).toBeGreaterThan(100)
  })

  it('includes all seven capability names', () => {
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Generative Questioning')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Synthesis')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Perspective Shifting')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Pattern Recognition')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Intellectual Honesty')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Temporal')
    expect(INTELLIGENCE_LAYER_PROMPT).toContain('Counterfactual')
  })
})

describe('buildSystemPrompt', () => {
  it('combines feature prompt with Intelligence Layer prompt', () => {
    const result = buildSystemPrompt('You are a contact summarizer.')
    expect(result).toContain('You are a contact summarizer.')
    expect(result).toContain('Intelligence Layer')
  })
})
```

**Step 2: Run test to verify it fails**

```bash
npm run test:run -- src/lib/intelligence-layer.test.ts
```

Expected: FAIL — module not found.

**Step 3: Create `src/lib/intelligence-layer.ts`**

```typescript
// src/lib/intelligence-layer.ts
// The Intelligence Layer is Kinetic's primary design principle.
// This prompt is injected into EVERY LLM system prompt in the application.
// Never make a callLLM() call without including buildSystemPrompt() — it wraps
// your feature-specific prompt with this block.

export const INTELLIGENCE_LAYER_PROMPT = `
## Intelligence Layer

You are an AI co-pilot with seven cognitive capabilities that transform every output you produce. Apply them as follows:

**1. Generative Questioning**
Surface 2-3 questions the user hasn't thought to ask, grounded in the context provided. These must be non-obvious questions that reveal gaps, assumptions, or unexplored angles. Label this section "Questions Worth Asking" in your output.

**2. Synthesis Under Complexity**
End every substantive response with a "Bottom Line" — 2-3 sentences that compress the essential structure. If something is complex, find the simplest true mental model. Never skip this section.

**3. Perspective Shifting**
When stakeholder context is available, briefly note how a key stakeholder might see this differently. Only include when it adds genuine insight — don't force it.

**4. Pattern Recognition**
When multiple sources or data points are provided, identify non-obvious connections between them. Surface these connections explicitly rather than leaving them implicit.

**5. Intellectual Honesty**
When tracked assumptions are provided, check them against current evidence. Surface contradictions directly. Never omit uncomfortable findings to make output more pleasant.

**6. Temporal Intelligence**
When historical data or previous interactions are provided, note what has changed or drifted over time. Gradual shifts that humans miss are high-value observations.

**7. Counterfactual Reasoning**
When asked for recommendations, briefly note the most important "what if this doesn't work" contingency. Ground it in the actual context — no generic risk language.

**Quality standard:** Intelligence Layer sections must be grounded in the specific context provided. If there is not enough data for a section to be specific rather than generic, omit that section entirely. Vague platitudes are worse than silence.
`.trim()

/**
 * Wraps a feature-specific system prompt with the Intelligence Layer.
 * Call this for EVERY LLM invocation. No exceptions.
 */
export function buildSystemPrompt(featurePrompt: string): string {
  return `${featurePrompt}\n\n---\n\n${INTELLIGENCE_LAYER_PROMPT}`
}
```

**Step 4: Run test to verify it passes**

```bash
npm run test:run -- src/lib/intelligence-layer.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/lib/intelligence-layer.ts src/lib/intelligence-layer.test.ts
git commit -m "feat: add INTELLIGENCE_LAYER_PROMPT module — baked into all LLM calls"
```

---

## Task 6: Embedding Utility

**Files:**
- Create: `src/lib/embeddings.ts`
- Create: `src/lib/embeddings.test.ts`

**Step 1: Write the failing test**

```typescript
// src/lib/embeddings.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createEmbedding } from './embeddings'

// Mock the OpenAI module
vi.mock('./openai', () => ({
  openaiClient: {
    embeddings: {
      create: vi.fn().mockResolvedValue({
        data: [{ embedding: new Array(1536).fill(0.1) }],
      }),
    },
  },
}))

describe('createEmbedding', () => {
  it('returns a vector of 1536 dimensions', async () => {
    const result = await createEmbedding('test text')
    expect(result).toHaveLength(1536)
    expect(typeof result[0]).toBe('number')
  })

  it('throws on empty input', async () => {
    await expect(createEmbedding('')).rejects.toThrow('Cannot embed empty text')
  })
})
```

**Step 2: Run test to verify it fails**

```bash
npm run test:run -- src/lib/embeddings.test.ts
```

Expected: FAIL — module not found.

**Step 3: Create `src/lib/embeddings.ts`**

```typescript
// src/lib/embeddings.ts
import { openaiClient } from './openai'

const EMBEDDING_MODEL = 'text-embedding-3-small'
const EMBEDDING_DIMENSIONS = 1536

/**
 * Generate a 1536-dimension embedding for the given text.
 * Used for: contacts, meetings, knowledge_items, client_memory, practice_memory, quick_captures.
 */
export async function createEmbedding(text: string): Promise<number[]> {
  if (!text || text.trim().length === 0) {
    throw new Error('Cannot embed empty text')
  }

  // Truncate to avoid token limit (8191 tokens for text-embedding-3-small)
  // ~4 chars per token, so 32000 chars is a safe ceiling
  const truncated = text.slice(0, 32000)

  const response = await openaiClient.embeddings.create({
    model: EMBEDDING_MODEL,
    input: truncated,
    dimensions: EMBEDDING_DIMENSIONS,
  })

  return response.data[0].embedding
}

/**
 * Formats text from a contact for embedding.
 * Combines the most semantically rich fields.
 */
export function contactEmbeddingText(contact: {
  name: string
  company?: string | null
  title?: string | null
  ai_summary?: string
  notes?: string
  tags?: string[]
}): string {
  return [
    contact.name,
    contact.title,
    contact.company,
    contact.ai_summary,
    contact.notes,
    contact.tags?.join(', '),
  ]
    .filter(Boolean)
    .join('\n')
}

/**
 * Formats text from a meeting for embedding.
 */
export function meetingEmbeddingText(meeting: {
  raw_notes?: string | null
  ai_summary?: string | null
  pain_points_mentioned?: string[]
  key_insights?: string | null
}): string {
  return [
    meeting.ai_summary,
    meeting.raw_notes,
    meeting.key_insights,
    meeting.pain_points_mentioned?.join(', '),
  ]
    .filter(Boolean)
    .join('\n')
}
```

**Step 4: Run test to verify it passes**

```bash
npm run test:run -- src/lib/embeddings.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/lib/embeddings.ts src/lib/embeddings.test.ts
git commit -m "feat: add createEmbedding utility using OpenAI text-embedding-3-small"
```

---

## Task 7: LLM Prompt Templates

**Files:**
- Create: `src/lib/prompts/contact-summary.ts`
- Create: `src/lib/prompts/meeting-processing.ts`
- Create: `src/lib/prompts/thank-you.ts`
- Create: `src/lib/prompts/contact-summary.test.ts`

**Step 1: Write the failing test**

```typescript
// src/lib/prompts/contact-summary.test.ts
import { describe, it, expect } from 'vitest'
import { buildContactSummaryPrompt } from './contact-summary'

describe('buildContactSummaryPrompt', () => {
  it('includes name and company in the user message', () => {
    const { userMessage } = buildContactSummaryPrompt({
      name: 'Jane Smith',
      company: 'Acme Corp',
      title: 'VP of Engineering',
    })
    expect(userMessage).toContain('Jane Smith')
    expect(userMessage).toContain('Acme Corp')
  })

  it('system prompt includes Intelligence Layer instruction', () => {
    const { systemPrompt } = buildContactSummaryPrompt({ name: 'Test' })
    expect(systemPrompt).toContain('Intelligence Layer')
  })
})
```

**Step 2: Run test to verify it fails**

```bash
npm run test:run -- src/lib/prompts/contact-summary.test.ts
```

Expected: FAIL

**Step 3: Create `src/lib/prompts/contact-summary.ts`**

```typescript
// src/lib/prompts/contact-summary.ts
import { buildSystemPrompt } from '../intelligence-layer'

interface ContactInput {
  name: string
  company?: string | null
  title?: string | null
  location?: string | null
  source?: string | null
  notes?: string | null
  linkedin_text?: string | null
}

export function buildContactSummaryPrompt(contact: ContactInput): {
  systemPrompt: string
  userMessage: string
} {
  const systemPrompt = buildSystemPrompt(`
You are a consulting practice intelligence system. Your job is to generate a concise, useful AI summary of a contact for use in meeting prep, relationship management, and identifying consulting opportunities.

The summary should be 2-4 sentences covering: who this person is, their professional context, why they're relevant to an AI consulting practice, and any signals about their needs or fit. Be specific — use the data provided. Do not speculate beyond what's given.
`.trim())

  const userMessage = `Generate a contact summary for:

Name: ${contact.name}
${contact.title ? `Title: ${contact.title}` : ''}
${contact.company ? `Company: ${contact.company}` : ''}
${contact.location ? `Location: ${contact.location}` : ''}
${contact.source ? `How we met: ${contact.source}` : ''}
${contact.notes ? `Notes: ${contact.notes}` : ''}
${contact.linkedin_text ? `LinkedIn context:\n${contact.linkedin_text}` : ''}

Write a 2-4 sentence summary. Be specific and grounded in what's provided. No filler.`

  return { systemPrompt, userMessage }
}
```

**Step 4: Create `src/lib/prompts/meeting-processing.ts`**

```typescript
// src/lib/prompts/meeting-processing.ts
import { buildSystemPrompt } from '../intelligence-layer'

export function buildMeetingProcessingPrompt(params: {
  contactName: string
  contactCompany?: string | null
  rawNotes: string
  clientGoals?: string | null
}): { systemPrompt: string; userMessage: string } {
  const systemPrompt = buildSystemPrompt(`
You are a consulting practice intelligence system processing meeting notes. Extract structured intelligence from raw meeting notes and return it as valid JSON.

Your output must be a single JSON object with these exact keys:
- "summary": string — 3-5 sentence narrative summary of the meeting
- "essential_takeaway": string — 1 sentence Bottom Line compression (Synthesis capability)
- "action_items": array of { "text": string, "due_date": string|null, "priority": "high"|"medium"|"low" }
- "pain_points_mentioned": string[] — specific pain points or challenges mentioned
- "buying_signals": string[] — signals of interest, urgency, or budget readiness
- "key_insights": string — 1-3 sentences on the most important strategic observations
- "assumptions_stated": string[] — beliefs or assumptions the contact stated or implied (Intellectual Honesty capability)
- "gaps_not_addressed": string — what was NOT discussed relative to their apparent needs (Generative Questioning capability)

Return only valid JSON. No markdown code blocks. No explanation outside the JSON.
`.trim())

  const userMessage = `Process these meeting notes:

Contact: ${params.contactName}${params.contactCompany ? ` at ${params.contactCompany}` : ''}
${params.clientGoals ? `Known goals/context: ${params.clientGoals}` : ''}

Meeting notes:
${params.rawNotes}

Return structured JSON as specified.`

  return { systemPrompt, userMessage }
}
```

**Step 5: Create `src/lib/prompts/thank-you.ts`**

```typescript
// src/lib/prompts/thank-you.ts
import { buildSystemPrompt } from '../intelligence-layer'

export function buildThankYouPrompt(params: {
  contactName: string
  meetingSummary: string
  actionItems: Array<{ text: string }>
  meetingType: string
}): { systemPrompt: string; userMessage: string } {
  const systemPrompt = buildSystemPrompt(`
You are drafting a brief thank-you message for a consultant to send after a meeting. The message should:
- Be warm but professional
- Reference 1-2 specific things discussed (not generic)
- Mention next steps if action items exist
- Be 3-5 sentences maximum — consultants are busy, so is the recipient
- Sound like it was written by a human, not a corporate template

Return only the message body. No subject line. No "Here is your email:" preamble.
`.trim())

  const userMessage = `Draft a thank-you message after a ${params.meetingType} with ${params.contactName}.

Meeting summary: ${params.meetingSummary}

${params.actionItems.length > 0 ? `Action items agreed to:\n${params.actionItems.map(a => `- ${a.text}`).join('\n')}` : 'No specific action items.'}

Write the thank-you message.`

  return { systemPrompt, userMessage }
}
```

**Step 6: Run tests**

```bash
npm run test:run -- src/lib/prompts/
```

Expected: PASS

**Step 7: Commit**

```bash
git add src/lib/prompts/
git commit -m "feat: add LLM prompt templates for contact summary, meeting processing, thank-you"
```

---

## Task 8: Contact API

**Files:**
- Create: `src/app/api/contacts/route.ts`
- Create: `src/app/api/contacts/[id]/route.ts`

**Step 1: Create `src/app/api/contacts/route.ts`**

```typescript
// src/app/api/contacts/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { callLLM } from '@/lib/anthropic'
import { createEmbedding, contactEmbeddingText } from '@/lib/embeddings'
import { buildContactSummaryPrompt } from '@/lib/prompts/contact-summary'
import type { CreateContactRequest } from '@/types/api'

// GET /api/contacts — list all contacts, optional ?search= query
export async function GET(request: NextRequest) {
  try {
    const searchQuery = request.nextUrl.searchParams.get('search')

    if (searchQuery) {
      // Semantic search: embed the query, then match_documents
      const queryEmbedding = await createEmbedding(searchQuery)
      const { data, error } = await supabase.rpc('match_documents', {
        query_embedding: queryEmbedding,
        match_threshold: 0.4,
        match_count: 20,
        filter_source: 'contacts',
      })
      if (error) throw error

      // Fetch full contact records for the matched IDs
      const ids = (data ?? []).map((r: { id: string }) => r.id)
      if (ids.length === 0) return NextResponse.json([])

      const { data: contacts, error: contactsError } = await supabase
        .from('contacts')
        .select('*')
        .in('id', ids)
        .order('updated_at', { ascending: false })

      if (contactsError) throw contactsError
      return NextResponse.json(contacts)
    }

    // Default: return all contacts sorted by recently updated
    const { data, error } = await supabase
      .from('contacts')
      .select('*')
      .order('updated_at', { ascending: false })

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/contacts error:', err)
    return NextResponse.json({ error: 'Failed to fetch contacts' }, { status: 500 })
  }
}

// POST /api/contacts — create a new contact
export async function POST(request: NextRequest) {
  try {
    const body: CreateContactRequest = await request.json()

    if (!body.name?.trim()) {
      return NextResponse.json({ error: 'name is required' }, { status: 400 })
    }

    // Generate AI summary
    const { systemPrompt, userMessage } = buildContactSummaryPrompt({
      name: body.name,
      company: body.company,
      title: body.title,
      location: body.location,
      source: body.source,
      notes: body.notes,
    })
    const aiSummary = await callLLM({ systemPrompt, userMessage, maxTokens: 512 })

    // Generate embedding from combined contact text
    const embeddingText = contactEmbeddingText({
      name: body.name,
      company: body.company,
      title: body.title,
      ai_summary: aiSummary,
      notes: body.notes,
      tags: body.tags,
    })
    const embedding = await createEmbedding(embeddingText)

    const { data, error } = await supabase
      .from('contacts')
      .insert({
        name: body.name.trim(),
        email: body.email ?? null,
        phone: body.phone ?? null,
        company: body.company ?? null,
        title: body.title ?? null,
        linkedin_url: body.linkedin_url ?? null,
        location: body.location ?? null,
        source: body.source ?? '',
        notes: body.notes ?? '',
        tags: body.tags ?? [],
        ai_summary: aiSummary,
        embedding,
        relationship_status: 'new',
      })
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data, { status: 201 })
  } catch (err) {
    console.error('POST /api/contacts error:', err)
    return NextResponse.json({ error: 'Failed to create contact' }, { status: 500 })
  }
}
```

**Step 2: Create `src/app/api/contacts/[id]/route.ts`**

```typescript
// src/app/api/contacts/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { createEmbedding, contactEmbeddingText } from '@/lib/embeddings'
import type { UpdateContactRequest } from '@/types/api'

// GET /api/contacts/:id
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { data, error } = await supabase
      .from('contacts')
      .select('*')
      .eq('id', id)
      .single()

    if (error) {
      if (error.code === 'PGRST116') {
        return NextResponse.json({ error: 'Contact not found' }, { status: 404 })
      }
      throw error
    }
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to fetch contact' }, { status: 500 })
  }
}

// PUT /api/contacts/:id
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body: UpdateContactRequest = await request.json()

    // Re-embed if name, company, title, or notes changed
    const shouldReEmbed = body.name || body.company || body.title || body.notes

    let embedding: number[] | undefined
    if (shouldReEmbed) {
      // Fetch current contact to merge
      const { data: current } = await supabase
        .from('contacts')
        .select('name, company, title, ai_summary, notes, tags')
        .eq('id', id)
        .single()

      if (current) {
        const embeddingText = contactEmbeddingText({
          name: body.name ?? current.name,
          company: body.company ?? current.company,
          title: body.title ?? current.title,
          ai_summary: current.ai_summary,
          notes: body.notes ?? current.notes,
          tags: body.tags ?? current.tags,
        })
        embedding = await createEmbedding(embeddingText)
      }
    }

    const { data, error } = await supabase
      .from('contacts')
      .update({ ...body, ...(embedding ? { embedding } : {}) })
      .eq('id', id)
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update contact' }, { status: 500 })
  }
}

// DELETE /api/contacts/:id
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { error } = await supabase.from('contacts').delete().eq('id', id)
    if (error) throw error
    return NextResponse.json({ success: true })
  } catch (err) {
    console.error('DELETE /api/contacts/[id] error:', err)
    return NextResponse.json({ error: 'Failed to delete contact' }, { status: 500 })
  }
}
```

**Step 3: Manual smoke test**

Start dev server (`npm run dev`), then:

```bash
# Create a contact
curl -X POST http://localhost:3000/api/contacts \
  -H "Content-Type: application/json" \
  -d '{"name":"Jane Smith","company":"Acme Corp","title":"VP Engineering","source":"Portland Tech Meetup"}'
```

Expected: 201 response with contact object including `ai_summary` and `id`.

```bash
# List contacts
curl http://localhost:3000/api/contacts
```

Expected: Array with the created contact.

```bash
# Semantic search
curl "http://localhost:3000/api/contacts?search=engineering+leader"
```

Expected: Jane Smith returned if her embedding was created.

**Step 4: Commit**

```bash
git add src/app/api/contacts/
git commit -m "feat: add contact CRUD API with AI summary generation and semantic search"
```

---

## Task 9: LinkedIn PDF Parsing

**Files:**
- Create: `src/app/api/contacts/parse-linkedin/route.ts`
- Create: `src/lib/parsers/linkedin-pdf.ts`
- Create: `src/lib/parsers/linkedin-pdf.test.ts`

**Step 1: Create `src/lib/parsers/linkedin-pdf.ts`**

```typescript
// src/lib/parsers/linkedin-pdf.ts
import pdf from 'pdf-parse'
import { callLLM } from '../anthropic'
import { buildSystemPrompt } from '../intelligence-layer'

export interface LinkedInExtract {
  name?: string
  title?: string
  company?: string
  location?: string
  email?: string
  linkedin_url?: string
  summary?: string
  raw_text: string
}

/**
 * Parse a LinkedIn PDF export and extract structured contact data.
 * Falls back to empty fields if extraction fails — never throw on partial data.
 */
export async function parseLinkedInPDF(buffer: Buffer): Promise<LinkedInExtract> {
  let rawText = ''
  try {
    const parsed = await pdf(buffer)
    rawText = parsed.text
  } catch {
    throw new Error('Could not read PDF — ensure this is a valid LinkedIn export')
  }

  if (!rawText || rawText.trim().length < 50) {
    throw new Error('PDF appears empty or unreadable')
  }

  // Use LLM to extract structured data from raw LinkedIn text
  const systemPrompt = buildSystemPrompt(`
You extract structured contact information from raw LinkedIn PDF export text.
Return a JSON object with these exact keys (use null for missing fields):
- "name": string | null
- "title": string | null (current job title)
- "company": string | null (current company)
- "location": string | null
- "email": string | null
- "linkedin_url": string | null
- "summary": string | null (their LinkedIn About/summary section, max 500 chars)

Return only valid JSON. No markdown. No explanation.
`.trim())

  const userMessage = `Extract contact info from this LinkedIn export:\n\n${rawText.slice(0, 4000)}`

  try {
    const response = await callLLM({
      systemPrompt,
      userMessage,
      model: 'claude-haiku-4-5-20251001', // lightweight extraction task
      maxTokens: 512,
    })
    const extracted = JSON.parse(response)
    return { ...extracted, raw_text: rawText }
  } catch {
    // If LLM parsing fails, return raw text so user can fill in manually
    return { raw_text: rawText }
  }
}
```

**Step 2: Write a parser test**

```typescript
// src/lib/parsers/linkedin-pdf.test.ts
import { describe, it, expect, vi } from 'vitest'
import { parseLinkedInPDF } from './linkedin-pdf'

// Mock pdf-parse and anthropic
vi.mock('pdf-parse', () => ({
  default: vi.fn().mockResolvedValue({
    text: 'Jane Smith\nVP Engineering at Acme Corp\nPortland, Oregon\njane@acme.com',
  }),
}))

vi.mock('../anthropic', () => ({
  callLLM: vi.fn().mockResolvedValue(
    JSON.stringify({
      name: 'Jane Smith',
      title: 'VP Engineering',
      company: 'Acme Corp',
      location: 'Portland, Oregon',
      email: 'jane@acme.com',
      linkedin_url: null,
      summary: null,
    })
  ),
}))

describe('parseLinkedInPDF', () => {
  it('extracts name and company from a LinkedIn PDF', async () => {
    const result = await parseLinkedInPDF(Buffer.from('fake pdf content'))
    expect(result.name).toBe('Jane Smith')
    expect(result.company).toBe('Acme Corp')
    expect(result.raw_text).toBeTruthy()
  })
})
```

**Step 3: Run test**

```bash
npm run test:run -- src/lib/parsers/
```

Expected: PASS

**Step 4: Create the API route**

```typescript
// src/app/api/contacts/parse-linkedin/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { parseLinkedInPDF } from '@/lib/parsers/linkedin-pdf'

// POST /api/contacts/parse-linkedin
// Accepts: multipart/form-data with a "file" field containing a LinkedIn PDF
// Returns: extracted contact fields for user review — does NOT auto-create the contact
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 })
    }

    if (file.type !== 'application/pdf') {
      return NextResponse.json({ error: 'File must be a PDF' }, { status: 400 })
    }

    const buffer = Buffer.from(await file.arrayBuffer())
    const extracted = await parseLinkedInPDF(buffer)

    return NextResponse.json(extracted)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to parse PDF'
    console.error('POST /api/contacts/parse-linkedin error:', err)
    return NextResponse.json({ error: message }, { status: 422 })
  }
}
```

**Step 5: Commit**

```bash
git add src/lib/parsers/ src/app/api/contacts/parse-linkedin/
git commit -m "feat: add LinkedIn PDF parsing — LLM extracts structured fields for review"
```

---

## Task 10: Meeting Logging + AI Processing

**Files:**
- Create: `src/app/api/meetings/route.ts`
- Create: `src/app/api/meetings/[id]/route.ts`
- Create: `src/lib/meeting-processor.ts`
- Create: `src/lib/meeting-processor.test.ts`

**Step 1: Write the failing test**

```typescript
// src/lib/meeting-processor.test.ts
import { describe, it, expect, vi } from 'vitest'
import { parseMeetingProcessingResponse } from './meeting-processor'

describe('parseMeetingProcessingResponse', () => {
  it('parses a valid JSON response from the LLM', () => {
    const json = JSON.stringify({
      summary: 'Great meeting about AI strategy.',
      essential_takeaway: 'They need a clear AI roadmap.',
      action_items: [{ text: 'Send proposal', due_date: '2026-03-07', priority: 'high' }],
      pain_points_mentioned: ['No AI strategy'],
      buying_signals: ['Asked about pricing'],
      key_insights: 'Strong interest, budget unclear.',
      assumptions_stated: ['Assumes AI can replace their data team'],
      gaps_not_addressed: 'Did not discuss timeline or stakeholder buy-in.',
    })
    const result = parseMeetingProcessingResponse(json)
    expect(result.summary).toContain('AI strategy')
    expect(result.action_items).toHaveLength(1)
    expect(result.assumptions_stated).toHaveLength(1)
  })

  it('returns safe defaults on malformed JSON', () => {
    const result = parseMeetingProcessingResponse('not valid json')
    expect(result.summary).toBe('')
    expect(result.action_items).toEqual([])
  })
})
```

**Step 2: Run test to verify it fails**

```bash
npm run test:run -- src/lib/meeting-processor.test.ts
```

Expected: FAIL

**Step 3: Create `src/lib/meeting-processor.ts`**

```typescript
// src/lib/meeting-processor.ts
import { callLLM } from './anthropic'
import { supabase } from './supabase'
import { createEmbedding, meetingEmbeddingText } from './embeddings'
import { buildMeetingProcessingPrompt } from './prompts/meeting-processing'
import { buildThankYouPrompt } from './prompts/thank-you'
import type { ActionItem } from '@/types'

interface ProcessedMeeting {
  summary: string
  essential_takeaway: string
  action_items: ActionItem[]
  pain_points_mentioned: string[]
  buying_signals: string[]
  key_insights: string
  assumptions_stated: string[]
  gaps_not_addressed: string
}

export function parseMeetingProcessingResponse(json: string): ProcessedMeeting {
  try {
    const parsed = JSON.parse(json)
    return {
      summary: parsed.summary ?? '',
      essential_takeaway: parsed.essential_takeaway ?? '',
      action_items: Array.isArray(parsed.action_items) ? parsed.action_items : [],
      pain_points_mentioned: Array.isArray(parsed.pain_points_mentioned) ? parsed.pain_points_mentioned : [],
      buying_signals: Array.isArray(parsed.buying_signals) ? parsed.buying_signals : [],
      key_insights: parsed.key_insights ?? '',
      assumptions_stated: Array.isArray(parsed.assumptions_stated) ? parsed.assumptions_stated : [],
      gaps_not_addressed: parsed.gaps_not_addressed ?? '',
    }
  } catch {
    return {
      summary: '',
      essential_takeaway: '',
      action_items: [],
      pain_points_mentioned: [],
      buying_signals: [],
      key_insights: '',
      assumptions_stated: [],
      gaps_not_addressed: '',
    }
  }
}

/**
 * Full AI processing chain for a completed meeting.
 * Called after meeting is saved to DB with raw_notes.
 *
 * Steps:
 * 1. Generate AI summary + extract action items, pain points, buying signals,
 *    assumptions (Intelligence Layer: Intellectual Honesty),
 *    and gaps not addressed (Intelligence Layer: Generative Questioning)
 * 2. Generate thank-you email draft
 * 3. Create follow-up records
 * 4. Embed the meeting
 * 5. Store extracted assumptions as client_memory entries
 */
export async function processMeeting(meetingId: string): Promise<void> {
  // Fetch meeting + contact
  const { data: meeting } = await supabase
    .from('meetings')
    .select('*, contacts(name, company)')
    .eq('id', meetingId)
    .single()

  if (!meeting || !meeting.raw_notes) return

  const contact = meeting.contacts as { name: string; company: string | null }

  // Step 1: Process meeting notes with LLM
  const { systemPrompt, userMessage } = buildMeetingProcessingPrompt({
    contactName: contact.name,
    contactCompany: contact.company,
    rawNotes: meeting.raw_notes,
  })
  const rawResponse = await callLLM({ systemPrompt, userMessage, maxTokens: 2048 })
  const processed = parseMeetingProcessingResponse(rawResponse)

  // Step 2: Generate thank-you draft
  const thankYouPrompts = buildThankYouPrompt({
    contactName: contact.name,
    meetingSummary: processed.summary,
    actionItems: processed.action_items,
    meetingType: meeting.type,
  })
  const thankYouDraft = await callLLM({
    systemPrompt: thankYouPrompts.systemPrompt,
    userMessage: thankYouPrompts.userMessage,
    maxTokens: 512,
  })

  // Step 3: Generate embedding
  const embeddingText = meetingEmbeddingText({
    raw_notes: meeting.raw_notes,
    ai_summary: processed.summary,
    pain_points_mentioned: processed.pain_points_mentioned,
    key_insights: processed.key_insights,
  })
  const embedding = await createEmbedding(embeddingText)

  // Step 4: Update meeting record with all processed data
  await supabase
    .from('meetings')
    .update({
      status: 'completed',
      ai_summary: processed.summary,
      action_items: processed.action_items,
      pain_points_mentioned: processed.pain_points_mentioned,
      buying_signals: processed.buying_signals,
      key_insights: `${processed.essential_takeaway}\n\n${processed.key_insights}\n\nGaps not addressed: ${processed.gaps_not_addressed}`,
      thank_you_draft: thankYouDraft,
      embedding,
    })
    .eq('id', meetingId)

  // Step 5: Create follow-up records
  const today = new Date()
  const followUps = []

  // Always create a thank-you follow-up
  followUps.push({
    contact_id: meeting.contact_id,
    meeting_id: meetingId,
    type: 'thank_you' as const,
    message_draft: thankYouDraft,
    due_date: new Date(today.getTime() + 24 * 60 * 60 * 1000)
      .toISOString()
      .split('T')[0],
    status: 'pending' as const,
  })

  // If buying signals detected, create a check-in follow-up
  if (processed.buying_signals.length > 0) {
    followUps.push({
      contact_id: meeting.contact_id,
      meeting_id: meetingId,
      type: 'check_in' as const,
      message_draft: null,
      due_date: new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000)
        .toISOString()
        .split('T')[0],
      status: 'pending' as const,
    })
  }

  if (followUps.length > 0) {
    await supabase.from('follow_ups').insert(followUps)
  }

  // Step 6 (Intelligence Layer): Store extracted assumptions as client_memory
  if (processed.assumptions_stated.length > 0) {
    const memoryEntries = processed.assumptions_stated.map((assumption) => ({
      contact_id: meeting.contact_id,
      memory_type: 'assumption' as const,
      content: assumption,
      source_meeting_id: meetingId,
    }))
    await supabase.from('client_memory').insert(memoryEntries)
  }
}
```

**Step 4: Run test**

```bash
npm run test:run -- src/lib/meeting-processor.test.ts
```

Expected: PASS

**Step 5: Create `src/app/api/meetings/route.ts`**

```typescript
// src/app/api/meetings/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { processMeeting } from '@/lib/meeting-processor'
import type { CreateMeetingRequest } from '@/types/api'

// GET /api/meetings
export async function GET(request: NextRequest) {
  try {
    const contactId = request.nextUrl.searchParams.get('contact_id')
    const status = request.nextUrl.searchParams.get('status')

    let query = supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .order('date', { ascending: false })

    if (contactId) query = query.eq('contact_id', contactId)
    if (status) query = query.eq('status', status)

    const { data, error } = await query
    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/meetings error:', err)
    return NextResponse.json({ error: 'Failed to fetch meetings' }, { status: 500 })
  }
}

// POST /api/meetings
export async function POST(request: NextRequest) {
  try {
    const body: CreateMeetingRequest = await request.json()

    if (!body.contact_id) {
      return NextResponse.json({ error: 'contact_id is required' }, { status: 400 })
    }
    if (!body.date) {
      return NextResponse.json({ error: 'date is required' }, { status: 400 })
    }

    const isCompleted = body.status === 'completed' && body.raw_notes

    // Insert meeting record
    const { data: meeting, error } = await supabase
      .from('meetings')
      .insert({
        contact_id: body.contact_id,
        date: body.date,
        type: body.type ?? 'other',
        location: body.location ?? null,
        status: isCompleted ? 'completed' : (body.status ?? 'upcoming'),
        raw_notes: body.raw_notes ?? null,
      })
      .select()
      .single()

    if (error) throw error

    // Trigger AI processing asynchronously if notes provided
    // Note: In Phase 2 this moves to the Post-Meeting Agent (Edge Function).
    // For Phase 1, we process synchronously and return when done.
    if (isCompleted && body.raw_notes) {
      await processMeeting(meeting.id)
      // Re-fetch to get the processed version
      const { data: processed } = await supabase
        .from('meetings')
        .select('*')
        .eq('id', meeting.id)
        .single()
      return NextResponse.json(processed, { status: 201 })
    }

    return NextResponse.json(meeting, { status: 201 })
  } catch (err) {
    console.error('POST /api/meetings error:', err)
    return NextResponse.json({ error: 'Failed to create meeting' }, { status: 500 })
  }
}
```

**Step 6: Create `src/app/api/meetings/[id]/route.ts`**

```typescript
// src/app/api/meetings/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'
import { processMeeting } from '@/lib/meeting-processor'

// GET /api/meetings/:id
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { data, error } = await supabase
      .from('meetings')
      .select('*, contacts(name, company), follow_ups(*)')
      .eq('id', id)
      .single()

    if (error) {
      if (error.code === 'PGRST116') {
        return NextResponse.json({ error: 'Meeting not found' }, { status: 404 })
      }
      throw error
    }
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/meetings/[id] error:', err)
    return NextResponse.json({ error: 'Failed to fetch meeting' }, { status: 500 })
  }
}

// PUT /api/meetings/:id — used to add notes to an upcoming meeting (transitions to completed)
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()

    const { data: existing } = await supabase
      .from('meetings')
      .select('status')
      .eq('id', id)
      .single()

    const isTransitioningToCompleted =
      existing?.status === 'upcoming' && body.raw_notes

    const { data, error } = await supabase
      .from('meetings')
      .update({
        ...body,
        ...(isTransitioningToCompleted ? { status: 'completed' } : {}),
      })
      .eq('id', id)
      .select()
      .single()

    if (error) throw error

    // Trigger processing if transitioning from upcoming → completed with notes
    if (isTransitioningToCompleted) {
      await processMeeting(id)
      const { data: processed } = await supabase
        .from('meetings')
        .select('*')
        .eq('id', id)
        .single()
      return NextResponse.json(processed)
    }

    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/meetings/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update meeting' }, { status: 500 })
  }
}
```

**Step 7: Manual smoke test**

```bash
# Log a completed meeting with notes
curl -X POST http://localhost:3000/api/meetings \
  -H "Content-Type: application/json" \
  -d '{
    "contact_id": "<id from Task 8 smoke test>",
    "date": "2026-03-04T14:00:00Z",
    "type": "discovery_call",
    "status": "completed",
    "raw_notes": "Met with Jane at Acme. They are struggling with AI adoption across their engineering team. Budget is approved for Q2. She mentioned they assume the team will self-educate but morale is low. Discussed potential training engagement. She asked about pricing models."
  }'
```

Expected: 201 with `ai_summary`, `action_items`, `pain_points_mentioned`, `buying_signals`, `thank_you_draft` populated. Check Supabase: `follow_ups` table has 2 records, `client_memory` has 1 assumption entry.

**Step 8: Commit**

```bash
git add src/app/api/meetings/ src/lib/meeting-processor.ts src/lib/meeting-processor.test.ts
git commit -m "feat: add meeting logging API with full AI processing chain (Intelligence Layer enabled)"
```

---

## Task 11: Follow-Up Manager API

**Files:**
- Create: `src/app/api/follow-ups/route.ts`
- Create: `src/app/api/follow-ups/[id]/route.ts`

**Step 1: Create `src/app/api/follow-ups/route.ts`**

```typescript
// src/app/api/follow-ups/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// GET /api/follow-ups — list pending follow-ups, sorted by due date
// Optional: ?status=pending|sent|skipped&contact_id=<uuid>
export async function GET(request: NextRequest) {
  try {
    const status = request.nextUrl.searchParams.get('status') ?? 'pending'
    const contactId = request.nextUrl.searchParams.get('contact_id')

    let query = supabase
      .from('follow_ups')
      .select('*, contacts(name, company, email)')
      .eq('status', status)
      .order('due_date', { ascending: true })

    if (contactId) query = query.eq('contact_id', contactId)

    const { data, error } = await query
    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('GET /api/follow-ups error:', err)
    return NextResponse.json({ error: 'Failed to fetch follow-ups' }, { status: 500 })
  }
}
```

**Step 2: Create `src/app/api/follow-ups/[id]/route.ts`**

```typescript
// src/app/api/follow-ups/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

// PUT /api/follow-ups/:id — update status (mark sent, skipped, back to pending)
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()

    const allowed = ['pending', 'sent', 'skipped']
    if (body.status && !allowed.includes(body.status)) {
      return NextResponse.json(
        { error: `status must be one of: ${allowed.join(', ')}` },
        { status: 400 }
      )
    }

    const { data, error } = await supabase
      .from('follow_ups')
      .update(body)
      .eq('id', id)
      .select()
      .single()

    if (error) throw error
    return NextResponse.json(data)
  } catch (err) {
    console.error('PUT /api/follow-ups/[id] error:', err)
    return NextResponse.json({ error: 'Failed to update follow-up' }, { status: 500 })
  }
}
```

**Step 3: Manual smoke test**

```bash
# List pending follow-ups
curl http://localhost:3000/api/follow-ups

# Mark the thank-you as sent
curl -X PUT http://localhost:3000/api/follow-ups/<follow-up-id> \
  -H "Content-Type: application/json" \
  -d '{"status":"sent"}'
```

Expected: Follow-up status updates to "sent".

**Step 4: Commit**

```bash
git add src/app/api/follow-ups/
git commit -m "feat: add follow-up manager API (list pending, mark sent/skipped)"
```

---

## Task 12: Global Layout + Tailwind Dark Theme

> **Skills:** Invoke `web-design-guidelines` first, then `brainstorming` before writing any component code. The dark theme design system (`#0a0a0a` / `#1a1a1a` / `#00b5a3`) is non-negotiable — do not improvise on color, spacing, or typography.

**Files:**
- Modify: `src/app/layout.tsx`
- Modify: `tailwind.config.ts`
- Modify: `src/app/globals.css`

**Step 1: Update `tailwind.config.ts`**

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0a0a0a',
          surface: '#1a1a1a',
          elevated: '#222222',
        },
        accent: {
          teal: '#00b5a3',
          'teal-hover': '#00cbb7',
          'teal-muted': '#007a70',
        },
        content: {
          primary: '#f5f5f5',
          secondary: '#888888',
          muted: '#555555',
        },
        border: {
          subtle: '#2a2a2a',
          DEFAULT: '#333333',
        },
        status: {
          warning: '#d97706',
          danger: '#dc2626',
          success: '#00b5a3',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
export default config
```

**Step 2: Update `src/app/globals.css`**

```css
/* src/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #0a0a0a;
  --foreground: #f5f5f5;
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}

/* Scrollbar styling */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0a0a; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #333; }

/* Focus ring */
*:focus-visible {
  outline: 2px solid #00b5a3;
  outline-offset: 2px;
}
```

**Step 3: Update `src/app/layout.tsx`**

```typescript
// src/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Kinetic',
  description: 'AI co-pilot for your consulting practice',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-bg-base text-content-primary min-h-screen">
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <nav className="w-56 bg-bg-surface border-r border-border-subtle flex-shrink-0 flex flex-col">
            <div className="p-4 border-b border-border-subtle">
              <span className="text-accent-teal font-mono font-bold text-lg tracking-tight">
                KINETIC
              </span>
            </div>
            <div className="flex-1 py-2">
              <NavLink href="/" label="Dashboard" />
              <NavLink href="/contacts" label="Contacts" />
              <NavLink href="/meetings" label="Meetings" />
              <NavLink href="/follow-ups" label="Follow-ups" />
              <NavLink href="/knowledge" label="Knowledge" />
              <NavLink href="/clients" label="Clients" />
            </div>
          </nav>

          {/* Main content */}
          <main className="flex-1 overflow-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="block px-4 py-2 text-sm text-content-secondary hover:text-content-primary hover:bg-bg-elevated transition-colors"
    >
      {label}
    </a>
  )
}
```

**Step 4: Commit**

```bash
git add src/app/layout.tsx tailwind.config.ts src/app/globals.css
git commit -m "feat: add dark theme layout with sidebar navigation"
```

---

## Task 13: Contact Dashboard UI

> **Skills:** Invoke `brainstorming` first to align on component structure, then `frontend-design` before writing code. The contact list and detail view are the primary UI Brandon uses daily — quality matters here.

**Files:**
- Create: `src/app/contacts/page.tsx`
- Create: `src/app/contacts/[id]/page.tsx`

**Step 1: Create `src/app/contacts/page.tsx`**

This is a server component — fetches contacts server-side, no client-side state needed for the list.

```typescript
// src/app/contacts/page.tsx
import { supabase } from '@/lib/supabase'
import type { Contact } from '@/types'
import Link from 'next/link'

interface PageProps {
  searchParams: Promise<{ search?: string }>
}

export default async function ContactsPage({ searchParams }: PageProps) {
  const { search } = await searchParams

  // Text search server-side (semantic search hits the API client-side via the search bar)
  let contacts: Contact[] = []
  if (search) {
    const { data } = await supabase
      .from('contacts')
      .select('*')
      .or(`name.ilike.%${search}%,company.ilike.%${search}%`)
      .order('updated_at', { ascending: false })
    contacts = data ?? []
  } else {
    const { data } = await supabase
      .from('contacts')
      .select('*')
      .order('updated_at', { ascending: false })
    contacts = data ?? []
  }

  const statusColor: Record<string, string> = {
    new: 'text-content-secondary',
    warm: 'text-yellow-500',
    active: 'text-accent-teal',
    dormant: 'text-content-muted',
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-content-primary">Contacts</h1>
          <p className="text-sm text-content-secondary mt-0.5">{contacts.length} contacts</p>
        </div>
        <a
          href="/contacts/new"
          className="px-4 py-2 bg-accent-teal text-bg-base text-sm font-medium rounded hover:bg-accent-teal-hover transition-colors"
        >
          + Add Contact
        </a>
      </div>

      {/* Search bar */}
      <form method="GET" className="mb-4">
        <input
          name="search"
          defaultValue={search}
          placeholder="Search contacts by name, company..."
          className="w-full bg-bg-surface border border-border-subtle rounded px-4 py-2 text-sm text-content-primary placeholder-content-muted focus:border-accent-teal focus:outline-none"
        />
      </form>

      {/* Contact list */}
      <div className="space-y-1">
        {contacts.length === 0 ? (
          <div className="text-center py-12 text-content-secondary">
            {search ? `No contacts matching "${search}"` : 'No contacts yet. Add your first contact.'}
          </div>
        ) : (
          contacts.map((contact) => (
            <Link
              key={contact.id}
              href={`/contacts/${contact.id}`}
              className="flex items-center justify-between p-3 bg-bg-surface hover:bg-bg-elevated rounded border border-border-subtle hover:border-border transition-colors group"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-content-primary group-hover:text-accent-teal">
                    {contact.name}
                  </span>
                  <span className={`text-xs ${statusColor[contact.relationship_status]}`}>
                    {contact.relationship_status}
                  </span>
                </div>
                <div className="text-xs text-content-secondary mt-0.5 truncate">
                  {[contact.title, contact.company].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="text-xs text-content-muted flex-shrink-0 ml-4">
                {new Date(contact.updated_at).toLocaleDateString()}
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  )
}
```

**Step 2: Create `src/app/contacts/[id]/page.tsx`**

```typescript
// src/app/contacts/[id]/page.tsx
import { supabase } from '@/lib/supabase'
import { notFound } from 'next/navigation'

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function ContactDetailPage({ params }: PageProps) {
  const { id } = await params

  const [{ data: contact }, { data: meetings }, { data: followUps }] = await Promise.all([
    supabase.from('contacts').select('*').eq('id', id).single(),
    supabase.from('meetings').select('*').eq('contact_id', id).order('date', { ascending: false }),
    supabase.from('follow_ups').select('*').eq('contact_id', id).eq('status', 'pending').order('due_date'),
  ])

  if (!contact) notFound()

  return (
    <div className="p-6 max-w-4xl">
      {/* Contact header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-content-primary">{contact.name}</h1>
        <p className="text-sm text-content-secondary mt-0.5">
          {[contact.title, contact.company, contact.location].filter(Boolean).join(' · ')}
        </p>
      </div>

      {/* AI Summary */}
      {contact.ai_summary && (
        <div className="bg-bg-surface border border-border-subtle rounded p-4 mb-4">
          <h2 className="text-xs font-medium text-accent-teal uppercase tracking-wider mb-2">AI Summary</h2>
          <p className="text-sm text-content-primary leading-relaxed">{contact.ai_summary}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Meetings */}
        <div>
          <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-2">
            Meetings ({meetings?.length ?? 0})
          </h2>
          <div className="space-y-2">
            {meetings?.map((m) => (
              <a
                key={m.id}
                href={`/meetings/${m.id}`}
                className="block p-3 bg-bg-surface border border-border-subtle rounded hover:border-border text-sm"
              >
                <div className="text-content-primary">{m.type.replace('_', ' ')}</div>
                <div className="text-xs text-content-secondary mt-0.5">
                  {new Date(m.date).toLocaleDateString()} · {m.status}
                </div>
              </a>
            ))}
            {!meetings?.length && (
              <p className="text-sm text-content-muted">No meetings yet</p>
            )}
          </div>
        </div>

        {/* Pending Follow-ups */}
        <div>
          <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider mb-2">
            Pending Follow-ups ({followUps?.length ?? 0})
          </h2>
          <div className="space-y-2">
            {followUps?.map((f) => (
              <div key={f.id} className="p-3 bg-bg-surface border border-border-subtle rounded text-sm">
                <div className="text-content-primary capitalize">{f.type.replace('_', ' ')}</div>
                <div className="text-xs text-content-secondary mt-0.5">
                  Due: {new Date(f.due_date).toLocaleDateString()}
                </div>
              </div>
            ))}
            {!followUps?.length && (
              <p className="text-sm text-content-muted">No pending follow-ups</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add src/app/contacts/
git commit -m "feat: add contacts list and detail pages with dark theme"
```

---

## Task 14: Dashboard Homepage

> **Skill:** Invoke `frontend-design` before building. This is the first screen Brandon sees every session — it sets the tone for the entire app.

**Files:**
- Modify: `src/app/page.tsx`

**Step 1: Replace `src/app/page.tsx`**

```typescript
// src/app/page.tsx
import { supabase } from '@/lib/supabase'
import Link from 'next/link'

export default async function DashboardPage() {
  const today = new Date().toISOString().split('T')[0]

  const [
    { count: contactCount },
    { data: pendingFollowUps },
    { data: recentMeetings },
    { data: upcomingMeetings },
  ] = await Promise.all([
    supabase.from('contacts').select('*', { count: 'exact', head: true }),
    supabase
      .from('follow_ups')
      .select('*, contacts(name, company)')
      .eq('status', 'pending')
      .lte('due_date', today)
      .order('due_date', { ascending: true })
      .limit(5),
    supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .eq('status', 'completed')
      .order('date', { ascending: false })
      .limit(5),
    supabase
      .from('meetings')
      .select('*, contacts(name, company)')
      .eq('status', 'upcoming')
      .gte('date', new Date().toISOString())
      .order('date', { ascending: true })
      .limit(3),
  ])

  const overdueCount = pendingFollowUps?.filter(
    (f) => f.due_date < today
  ).length ?? 0

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-content-primary">Dashboard</h1>
        <p className="text-sm text-content-secondary mt-0.5">
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <StatCard label="Contacts" value={contactCount ?? 0} href="/contacts" />
        <StatCard
          label="Due Follow-ups"
          value={pendingFollowUps?.length ?? 0}
          href="/follow-ups"
          alert={overdueCount > 0}
          alertLabel={`${overdueCount} overdue`}
        />
        <StatCard label="Upcoming Meetings" value={upcomingMeetings?.length ?? 0} href="/meetings" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Due & Overdue Follow-ups */}
        <Section title="Follow-ups Due" count={pendingFollowUps?.length} href="/follow-ups">
          {pendingFollowUps?.length === 0 ? (
            <EmptyState text="All caught up." />
          ) : (
            pendingFollowUps?.map((f) => {
              const isOverdue = f.due_date < today
              return (
                <ItemRow
                  key={f.id}
                  primary={(f.contacts as { name: string } | null)?.name ?? 'Unknown'}
                  secondary={`${f.type.replace('_', ' ')} · ${f.due_date}`}
                  tag={isOverdue ? 'overdue' : undefined}
                />
              )
            })
          )}
        </Section>

        {/* Upcoming Meetings */}
        <Section title="Upcoming Meetings" count={upcomingMeetings?.length} href="/meetings">
          {upcomingMeetings?.length === 0 ? (
            <EmptyState text="No upcoming meetings." />
          ) : (
            upcomingMeetings?.map((m) => (
              <Link key={m.id} href={`/meetings/${m.id}`}>
                <ItemRow
                  primary={(m.contacts as { name: string } | null)?.name ?? 'Unknown'}
                  secondary={`${m.type.replace('_', ' ')} · ${new Date(m.date).toLocaleDateString()}`}
                />
              </Link>
            ))
          )}
        </Section>

        {/* Recent Meetings */}
        <Section title="Recent Meetings" count={recentMeetings?.length} href="/meetings">
          {recentMeetings?.length === 0 ? (
            <EmptyState text="No meetings yet." />
          ) : (
            recentMeetings?.map((m) => (
              <Link key={m.id} href={`/meetings/${m.id}`}>
                <ItemRow
                  primary={(m.contacts as { name: string } | null)?.name ?? 'Unknown'}
                  secondary={`${m.type.replace('_', ' ')} · ${new Date(m.date).toLocaleDateString()}`}
                />
              </Link>
            ))
          )}
        </Section>
      </div>
    </div>
  )
}

// ---- Sub-components ----

function StatCard({
  label,
  value,
  href,
  alert,
  alertLabel,
}: {
  label: string
  value: number
  href: string
  alert?: boolean
  alertLabel?: string
}) {
  return (
    <a
      href={href}
      className="bg-bg-surface border border-border-subtle rounded p-4 hover:border-border transition-colors"
    >
      <div className={`text-2xl font-mono font-bold ${alert ? 'text-status-warning' : 'text-accent-teal'}`}>
        {value}
      </div>
      <div className="text-xs text-content-secondary mt-1">{label}</div>
      {alert && alertLabel && (
        <div className="text-xs text-status-warning mt-0.5">{alertLabel}</div>
      )}
    </a>
  )
}

function Section({
  title,
  count,
  href,
  children,
}: {
  title: string
  count?: number | null
  href: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-content-secondary uppercase tracking-wider">{title}</h2>
        {count !== undefined && count !== null && (
          <a href={href} className="text-xs text-accent-teal hover:underline">
            View all
          </a>
        )}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function ItemRow({
  primary,
  secondary,
  tag,
}: {
  primary: string
  secondary: string
  tag?: string
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-0">
      <div>
        <div className="text-sm text-content-primary">{primary}</div>
        <div className="text-xs text-content-secondary">{secondary}</div>
      </div>
      {tag && (
        <span className="text-xs text-status-warning border border-status-warning rounded px-1.5 py-0.5">
          {tag}
        </span>
      )}
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <p className="text-sm text-content-muted py-2">{text}</p>
}
```

**Step 2: Verify dashboard loads**

```bash
npm run dev
```

Open `http://localhost:3000`. Expected: dark dashboard with stat cards and empty sections (or data from smoke tests).

**Step 3: Run full test suite**

```bash
npm run test:run
```

Expected: All tests PASS.

**Step 4: Final Phase 1 commit**

```bash
git add src/app/page.tsx
git commit -m "feat: add dashboard homepage with stats, follow-ups, and recent meetings"
git tag phase1-complete
```

---

## Phase 1 Complete — Verification Checklist

> **Skill:** Invoke `verification-before-completion` before checking any box on this list. Do not self-certify.

Before moving to Phase 2, verify all of these manually:

- [ ] `npm run dev` starts without errors
- [ ] `npm run test:run` all tests pass
- [ ] Supabase: all 13 tables exist in Table Editor
- [ ] `match_documents` function appears in Database → Functions
- [ ] `POST /api/contacts` creates a contact with `ai_summary` populated
- [ ] Contact list at `/contacts` shows created contacts
- [ ] `POST /api/meetings` with `status: "completed"` and `raw_notes` triggers full AI processing
- [ ] After meeting creation: `follow_ups` table has records, `client_memory` has assumption entries
- [ ] Dashboard at `/` shows correct counts and follow-ups
- [ ] All API responses include proper error messages when input is invalid
- [ ] INTELLIGENCE_LAYER_PROMPT is present in every LLM system prompt (check by adding a `console.log(systemPrompt)` in `callLLM` temporarily)

---

**Plan complete and saved. Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open a new Cowork/Claude Code session pointed at the `kinetic/` folder, paste this plan, and execute task-by-task with checkpoints

Which approach?
