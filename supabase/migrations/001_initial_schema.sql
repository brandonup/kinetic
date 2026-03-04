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
