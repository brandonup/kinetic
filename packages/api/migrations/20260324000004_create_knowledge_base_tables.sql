-- Migration: create knowledge base tables
-- Schema ref: docs/db-schema-spec.md §10–13
-- Tables: knowledge_bases, knowledge_base_folders, knowledge_base_documents, knowledge_base_chunks
--
-- Prerequisites (must exist before running this migration):
--   - public.users (001_create_users.sql)
--   - public.projects (not yet in a migration file — assumed applied directly in Supabase)
--   - public.agent_definitions (not yet in a migration file — assumed applied directly)
--   - document_status enum (defined below; skip if already exists in your Supabase instance)
--   - pgvector extension (CREATE EXTENSION IF NOT EXISTS vector)
--
-- AMBIGUITY NOTE: The schema spec §13 lists project_id and agent_definition_id on
-- knowledge_base_chunks as "denormalized scope" columns but does NOT define FK
-- constraints for them (unlike knowledge_bases which has explicit CASCADE FKs).
-- This migration omits FK constraints on those denormalized columns consistent with
-- the spec's intent (they mirror the parent KB's ownership for query efficiency).
-- If you want FK constraints on those columns, add them manually after confirming
-- projects and agent_definitions tables exist.

-- ---------------------------------------------------------------------------
-- Extension
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Enum: document_status
-- ---------------------------------------------------------------------------

DO $$ BEGIN
  CREATE TYPE document_status AS ENUM (
    'pending',
    'extracting',
    'chunking',
    'embedding',
    'completed',
    'failed'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL; -- already exists; safe to skip
END $$;

-- ---------------------------------------------------------------------------
-- Table: public.knowledge_bases  (§10)
-- Polymorphic parent: belongs to a Project OR an AgentDefinition, never both.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.knowledge_bases (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  project_id            uuid        REFERENCES public.projects(id) ON DELETE CASCADE,
  agent_definition_id   uuid        REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  user_id               uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_knowledge_bases_single_parent CHECK (
    (project_id IS NOT NULL AND agent_definition_id IS NULL) OR
    (project_id IS NULL     AND agent_definition_id IS NOT NULL)
  )
);

CREATE TRIGGER trg_knowledge_bases_updated_at
  BEFORE UPDATE ON public.knowledge_bases
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE public.knowledge_bases ENABLE ROW LEVEL SECURITY;

-- SELECT: own KBs OR KBs attached to a public agent
CREATE POLICY "kb_select"
  ON public.knowledge_bases FOR SELECT
  USING (
    auth.uid() = user_id
    OR agent_definition_id IN (
      SELECT id FROM public.agent_definitions WHERE visibility = 'public'
    )
  );

CREATE POLICY "kb_insert"
  ON public.knowledge_bases FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "kb_update"
  ON public.knowledge_bases FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "kb_delete"
  ON public.knowledge_bases FOR DELETE
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Table: public.knowledge_base_folders  (§11)
-- Self-referencing hierarchy. Null parent_folder_id = root.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.knowledge_base_folders (
  id                uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  knowledge_base_id uuid        NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  parent_folder_id  uuid        REFERENCES public.knowledge_base_folders(id) ON DELETE CASCADE,
  name              text        NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
  -- No updated_at per spec (spec does not list it for this table).
  -- AMBIGUITY: spec lists standard columns as applying to "every table" but the
  -- folders table spec table only shows created_at. Omitting updated_at to match
  -- the explicit spec definition for this table. Add if needed.
);

CREATE INDEX IF NOT EXISTS idx_kb_folders_kb
  ON public.knowledge_base_folders (knowledge_base_id);

ALTER TABLE public.knowledge_base_folders ENABLE ROW LEVEL SECURITY;

-- Access via knowledge_base ownership chain
CREATE POLICY "kb_folders_select"
  ON public.knowledge_base_folders FOR SELECT
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases
      WHERE auth.uid() = user_id
        OR agent_definition_id IN (
          SELECT id FROM public.agent_definitions WHERE visibility = 'public'
        )
    )
  );

CREATE POLICY "kb_folders_insert"
  ON public.knowledge_base_folders FOR INSERT
  WITH CHECK (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

CREATE POLICY "kb_folders_update"
  ON public.knowledge_base_folders FOR UPDATE
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

CREATE POLICY "kb_folders_delete"
  ON public.knowledge_base_folders FOR DELETE
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

-- ---------------------------------------------------------------------------
-- Table: public.knowledge_base_documents  (§12)
-- Soft-delete via deleted_at. V1 columns (key_topics, document_date) included
-- as nullable — unused in MVP per spec § V1 Column Strategy.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.knowledge_base_documents (
  id                uuid            NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  knowledge_base_id uuid            NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  folder_id         uuid            REFERENCES public.knowledge_base_folders(id) ON DELETE SET NULL,
  title             text            NOT NULL,
  file_type         text,
  storage_uri       text,
  file_size_bytes   bigint,
  token_count       int,
  summary           text,
  key_topics        text[],                          -- V1 — null in MVP
  document_date     date,                            -- V1 — publication date for recency scoring
  tags              text[]          DEFAULT '{}',
  status            document_status NOT NULL DEFAULT 'pending',
  error_stage       text,
  error_message     text,
  retry_count       int             NOT NULL DEFAULT 0,
  deleted_at        timestamptz,
  created_at        timestamptz     NOT NULL DEFAULT now(),
  updated_at        timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_docs_kb
  ON public.knowledge_base_documents (knowledge_base_id)
  WHERE deleted_at IS NULL;

-- For retry/admin queries — documents not yet completed
CREATE INDEX IF NOT EXISTS idx_kb_docs_status
  ON public.knowledge_base_documents (status)
  WHERE status != 'completed';

CREATE TRIGGER trg_knowledge_base_documents_updated_at
  BEFORE UPDATE ON public.knowledge_base_documents
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE public.knowledge_base_documents ENABLE ROW LEVEL SECURITY;

-- Access via knowledge_base ownership chain; soft-delete filtering is application responsibility
CREATE POLICY "kb_docs_select"
  ON public.knowledge_base_documents FOR SELECT
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases
      WHERE auth.uid() = user_id
        OR agent_definition_id IN (
          SELECT id FROM public.agent_definitions WHERE visibility = 'public'
        )
    )
  );

CREATE POLICY "kb_docs_insert"
  ON public.knowledge_base_documents FOR INSERT
  WITH CHECK (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

CREATE POLICY "kb_docs_update"
  ON public.knowledge_base_documents FOR UPDATE
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

CREATE POLICY "kb_docs_delete"
  ON public.knowledge_base_documents FOR DELETE
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

-- ---------------------------------------------------------------------------
-- Table: public.knowledge_base_chunks  (§13)
-- Primary vector search target. Append-only — no updated_at per spec.
-- Requires pgvector extension (CREATE EXTENSION IF NOT EXISTS vector).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.knowledge_base_chunks (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  document_id           uuid        NOT NULL REFERENCES public.knowledge_base_documents(id) ON DELETE CASCADE,
  knowledge_base_id     uuid        NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  project_id            uuid,       -- Denormalized scope (no FK per spec); set if KB belongs to a Project
  agent_definition_id   uuid,       -- Denormalized scope (no FK per spec); set if KB belongs to an AgentDefinition
  text                  text        NOT NULL,
  embedding             vector(3072),
  chunk_summary         text,       -- V1 — chunk-level enrichment
  keywords              text[],     -- V1 — chunk-level enrichment
  section_path          text,
  page_range            text,
  chunk_index           int         NOT NULL,
  tsv                   tsvector,   -- V1 — FTS index column (GIN index enabled when FTS_ENABLED)
  embedding_model       text        NOT NULL DEFAULT 'text-embedding-3-large',
  created_at            timestamptz NOT NULL DEFAULT now()
  -- No updated_at: append-only table per spec conventions
);

-- IVFFlat vector indexes (scoped by ownership type)
-- Supabase limits HNSW to 2000 dimensions; text-embedding-3-large is 3072.
-- Using IVFFlat which supports higher dimensions. lists=10 is appropriate for MVP scale.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_project
  ON public.knowledge_base_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)
  WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_embedding_agent
  ON public.knowledge_base_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)
  WHERE agent_definition_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_document
  ON public.knowledge_base_chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_chunks_project
  ON public.knowledge_base_chunks (project_id)
  WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_agent_def
  ON public.knowledge_base_chunks (agent_definition_id)
  WHERE agent_definition_id IS NOT NULL;

-- NOTE: GIN index on tsv is intentionally omitted here.
-- Add when FTS_ENABLED = true (V1 feature flag). Schema ref: §13, V1 enhancement flags.

ALTER TABLE public.knowledge_base_chunks ENABLE ROW LEVEL SECURITY;

-- Chunks for public agents are readable by all authenticated users
CREATE POLICY "kb_chunks_select"
  ON public.knowledge_base_chunks FOR SELECT
  USING (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases
      WHERE auth.uid() = user_id
        OR agent_definition_id IN (
          SELECT id FROM public.agent_definitions WHERE visibility = 'public'
        )
    )
  );

-- Chunks are written by the backend processing pipeline (service role or authenticated user)
CREATE POLICY "kb_chunks_insert"
  ON public.knowledge_base_chunks FOR INSERT
  WITH CHECK (
    knowledge_base_id IN (
      SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id
    )
  );

-- Chunks are immutable after creation — update and delete go through cascade
-- (document deletion cascades to chunks). No direct user UPDATE/DELETE policies.
CREATE POLICY "kb_chunks_update_deny"
  ON public.knowledge_base_chunks FOR UPDATE
  USING (false);

CREATE POLICY "kb_chunks_delete_deny"
  ON public.knowledge_base_chunks FOR DELETE
  USING (false);
