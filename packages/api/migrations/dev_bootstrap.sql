-- ==========================================================================
-- Kinetic Dev Database Bootstrap
-- ==========================================================================
-- ONE file. Paste into Supabase SQL Editor and run ONCE on a fresh project.
--
-- Combines:
--   000_complete_schema.sql          (all tables, enums, indexes, RLS)
--   20260328000005_seed_llm_models   (model library seed data)
--   20260329000007_add_debug_prompt  (debug_prompt column on messages)
--   20260330000009_add_match_chunks  (match_chunks RPC)
--   20260330000010_add_email_to_users (handle_new_user trigger fix)
--
-- Skipped (already included in 000):
--   001_create_users, 002_add_disabled_at, 003_create_retrieval_debug_logs,
--   004_create_knowledge_base_tables, 006_match_framework_triggers,
--   008_add_agent_slug
-- ==========================================================================


-- =========================================================================
-- PART 1: Complete Schema (from 000_complete_schema.sql)
-- =========================================================================

-- 1. Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Utility functions
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. Enums
DO $$ BEGIN CREATE TYPE user_role AS ENUM ('user', 'admin'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE api_key_provider AS ENUM ('anthropic', 'openai', 'google', 'groq'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE agent_type AS ENUM ('custom', 'thought_leader'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE agent_visibility AS ENUM ('private', 'public'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE framework_confidence AS ENUM ('high', 'medium'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE framework_origin AS ENUM ('extracted', 'manual'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE proposal_status AS ENUM ('pending', 'approved', 'rejected'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE proposal_trigger AS ENUM ('conversation_end', 'periodic'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE llm_model_category AS ENUM ('generation', 'embedding', 'reranking'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE retrieval_scope AS ENUM ('project_kb', 'agent_kb'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE document_status AS ENUM ('pending', 'extracting', 'chunking', 'embedding', 'completed', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4. Tables (dependency order)

-- 4.1 users
CREATE TABLE IF NOT EXISTS public.users (
  id                uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  email             text        NOT NULL UNIQUE,
  name              text        NOT NULL,
  bio               text        CHECK (char_length(bio) <= 1000),
  role              user_role   NOT NULL DEFAULT 'user',
  default_model_id  uuid,
  active_company_id uuid,
  disabled_at       timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "users_select_own" ON public.users FOR SELECT USING (auth.uid() = id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "users_select_admin" ON public.users FOR SELECT USING (EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "users_update_own" ON public.users FOR UPDATE USING (auth.uid() = id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "users_insert_own" ON public.users FOR INSERT WITH CHECK (auth.uid() = id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "users_delete_deny" ON public.users FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.2 llm_models
CREATE TABLE IF NOT EXISTS public.llm_models (
  id             uuid               NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  provider       text               NOT NULL,
  model_id       text               NOT NULL UNIQUE,
  display_name   text               NOT NULL,
  category       llm_model_category NOT NULL,
  enabled        boolean            NOT NULL DEFAULT true,
  context_window int,
  created_at     timestamptz        NOT NULL DEFAULT now(),
  updated_at     timestamptz        NOT NULL DEFAULT now()
);
DO $$ BEGIN CREATE TRIGGER trg_llm_models_updated_at BEFORE UPDATE ON public.llm_models FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.llm_models ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "llm_models_select_authenticated" ON public.llm_models FOR SELECT USING (auth.uid() IS NOT NULL); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "llm_models_insert_admin" ON public.llm_models FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "llm_models_update_admin" ON public.llm_models FOR UPDATE USING (EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "llm_models_delete_admin" ON public.llm_models FOR DELETE USING (EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- FK patch: users.default_model_id
DO $$ BEGIN
  ALTER TABLE public.users ADD CONSTRAINT fk_users_default_model_id FOREIGN KEY (default_model_id) REFERENCES public.llm_models(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 4.3 user_api_keys
CREATE TABLE IF NOT EXISTS public.user_api_keys (
  id             uuid             NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id        uuid             NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  provider       api_key_provider NOT NULL,
  key_ciphertext bytea            NOT NULL,
  key_nonce      bytea            NOT NULL,
  key_hint       text             NOT NULL,
  validated_at   timestamptz,
  created_at     timestamptz      NOT NULL DEFAULT now(),
  updated_at     timestamptz      NOT NULL DEFAULT now(),
  CONSTRAINT uq_user_api_keys_user_provider UNIQUE (user_id, provider)
);
DO $$ BEGIN CREATE TRIGGER trg_user_api_keys_updated_at BEFORE UPDATE ON public.user_api_keys FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.user_api_keys ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "user_api_keys_select_own" ON public.user_api_keys FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "user_api_keys_insert_own" ON public.user_api_keys FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "user_api_keys_update_own" ON public.user_api_keys FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "user_api_keys_delete_own" ON public.user_api_keys FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.4 companies
CREATE TABLE IF NOT EXISTS public.companies (
  id          uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id     uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name        text        NOT NULL,
  description text        CHECK (char_length(description) <= 1000),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN CREATE TRIGGER trg_companies_updated_at BEFORE UPDATE ON public.companies FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "companies_select_own" ON public.companies FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "companies_insert_own" ON public.companies FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "companies_update_own" ON public.companies FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "companies_delete_own" ON public.companies FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- FK patch: users.active_company_id
DO $$ BEGIN
  ALTER TABLE public.users ADD CONSTRAINT fk_users_active_company_id FOREIGN KEY (active_company_id) REFERENCES public.companies(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 4.5 projects
CREATE TABLE IF NOT EXISTS public.projects (
  id           uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  company_id   uuid        NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  user_id      uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name         text        NOT NULL,
  instructions text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
DO $$ BEGIN CREATE TRIGGER trg_projects_updated_at BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "projects_select_own" ON public.projects FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "projects_insert_own" ON public.projects FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "projects_update_own" ON public.projects FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "projects_delete_own" ON public.projects FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.6 agent_definitions
CREATE TABLE IF NOT EXISTS public.agent_definitions (
  id           uuid             NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  owner_id     uuid             NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name         text             NOT NULL,
  slug         text             NOT NULL DEFAULT '',
  instructions text,
  type         agent_type       NOT NULL DEFAULT 'custom',
  visibility   agent_visibility NOT NULL DEFAULT 'private',
  created_at   timestamptz      NOT NULL DEFAULT now(),
  updated_at   timestamptz      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_definitions_owner ON public.agent_definitions (owner_id);
CREATE INDEX IF NOT EXISTS idx_agent_definitions_visibility ON public.agent_definitions (visibility) WHERE visibility = 'public';
ALTER TABLE public.agent_definitions DROP CONSTRAINT IF EXISTS uq_agent_definitions_owner_slug;
ALTER TABLE public.agent_definitions DROP CONSTRAINT IF EXISTS uq_agent_definitions_slug;
ALTER TABLE public.agent_definitions ADD CONSTRAINT uq_agent_definitions_slug UNIQUE (slug);
DO $$ BEGIN CREATE TRIGGER trg_agent_definitions_updated_at BEFORE UPDATE ON public.agent_definitions FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.agent_definitions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "agent_definitions_select" ON public.agent_definitions FOR SELECT USING (auth.uid() = owner_id OR visibility = 'public'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_definitions_insert_own" ON public.agent_definitions FOR INSERT WITH CHECK (auth.uid() = owner_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_definitions_update_own" ON public.agent_definitions FOR UPDATE USING (auth.uid() = owner_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_definitions_delete_own" ON public.agent_definitions FOR DELETE USING (auth.uid() = owner_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.7 conversations
CREATE TABLE IF NOT EXISTS public.conversations (
  id              uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id         uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  company_id      uuid        NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  project_id      uuid        REFERENCES public.projects(id) ON DELETE CASCADE,
  title           text,
  active_agent_id uuid        REFERENCES public.agent_definitions(id) ON DELETE SET NULL,
  deleted_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_company ON public.conversations (user_id, company_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_conversations_project ON public.conversations (project_id) WHERE deleted_at IS NULL;
DO $$ BEGIN CREATE TRIGGER trg_conversations_updated_at BEFORE UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "conversations_select_own" ON public.conversations FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conversations_insert_own" ON public.conversations FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conversations_update_own" ON public.conversations FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conversations_delete_own" ON public.conversations FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.8 messages (append-only)
CREATE TABLE IF NOT EXISTS public.messages (
  id                   uuid         NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  conversation_id      uuid         NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  role                 message_role NOT NULL,
  content              text         NOT NULL,
  agent_definition_id  uuid         REFERENCES public.agent_definitions(id) ON DELETE SET NULL,
  model                text,
  token_count          int,
  sequence             int          NOT NULL,
  debug_prompt         jsonb,
  created_at           timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_seq ON public.messages (conversation_id, sequence);
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "messages_select_own" ON public.messages FOR SELECT USING (conversation_id IN (SELECT id FROM public.conversations WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "messages_insert_own" ON public.messages FOR INSERT WITH CHECK (conversation_id IN (SELECT id FROM public.conversations WHERE auth.uid() = user_id AND deleted_at IS NULL)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "messages_update_deny" ON public.messages FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "messages_delete_deny" ON public.messages FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.9 conversation_summaries (append-only)
CREATE TABLE IF NOT EXISTS public.conversation_summaries (
  id                      uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  conversation_id         uuid        NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  summary_text            text        NOT NULL,
  messages_covered_up_to  int         NOT NULL,
  model                   text,
  created_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conv_summaries_conversation ON public.conversation_summaries (conversation_id);
ALTER TABLE public.conversation_summaries ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "conv_summaries_select_own" ON public.conversation_summaries FOR SELECT USING (conversation_id IN (SELECT id FROM public.conversations WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conv_summaries_insert_own" ON public.conversation_summaries FOR INSERT WITH CHECK (conversation_id IN (SELECT id FROM public.conversations WHERE auth.uid() = user_id AND deleted_at IS NULL)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conv_summaries_update_deny" ON public.conversation_summaries FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "conv_summaries_delete_deny" ON public.conversation_summaries FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.10 agent_instances
CREATE TABLE IF NOT EXISTS public.agent_instances (
  id                   uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id              uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  agent_definition_id  uuid        NOT NULL REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  framework_overrides  jsonb       NOT NULL DEFAULT '{}',
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_agent_instances_user_agent UNIQUE (user_id, agent_definition_id)
);
DO $$ BEGIN CREATE TRIGGER trg_agent_instances_updated_at BEFORE UPDATE ON public.agent_instances FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.agent_instances ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "agent_instances_select_own" ON public.agent_instances FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_instances_insert_own" ON public.agent_instances FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_instances_update_own" ON public.agent_instances FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "agent_instances_delete_own" ON public.agent_instances FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.11 frameworks
CREATE TABLE IF NOT EXISTS public.frameworks (
  id                   uuid                 NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_definition_id  uuid                 NOT NULL REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  framework_id         text                 NOT NULL,
  name                 text                 NOT NULL,
  description          text,
  category             text,
  when_to_apply        text[]               NOT NULL CHECK (array_length(when_to_apply, 1) >= 1),
  principles           text[]               NOT NULL CHECK (array_length(principles, 1) >= 1),
  steps                text[],
  example_application  text,
  related_frameworks   text[],
  source_posts         jsonb,
  type                 text,
  do_not_use_when      text[],
  confidence           framework_confidence NOT NULL,
  origin               framework_origin     NOT NULL,
  created_at           timestamptz          NOT NULL DEFAULT now(),
  updated_at           timestamptz          NOT NULL DEFAULT now(),
  CONSTRAINT uq_frameworks_agent_framework_id UNIQUE (agent_definition_id, framework_id)
);
CREATE INDEX IF NOT EXISTS idx_frameworks_agent_def ON public.frameworks (agent_definition_id);
DO $$ BEGIN CREATE TRIGGER trg_frameworks_updated_at BEFORE UPDATE ON public.frameworks FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.frameworks ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "frameworks_select" ON public.frameworks FOR SELECT USING (agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE owner_id = auth.uid() OR visibility = 'public')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "frameworks_insert_own" ON public.frameworks FOR INSERT WITH CHECK (auth.uid() = (SELECT owner_id FROM public.agent_definitions WHERE id = agent_definition_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "frameworks_update_own" ON public.frameworks FOR UPDATE USING (auth.uid() = (SELECT owner_id FROM public.agent_definitions WHERE id = agent_definition_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "frameworks_delete_own" ON public.frameworks FOR DELETE USING (auth.uid() = (SELECT owner_id FROM public.agent_definitions WHERE id = agent_definition_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.12 framework_trigger_embeddings
CREATE TABLE IF NOT EXISTS public.framework_trigger_embeddings (
  id                   uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  framework_db_id      uuid        NOT NULL REFERENCES public.frameworks(id) ON DELETE CASCADE,
  agent_definition_id  uuid        NOT NULL REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  trigger_text         text        NOT NULL,
  embedding            vector(3072) NOT NULL,
  embedding_model      text        NOT NULL DEFAULT 'text-embedding-3-large',
  created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trigger_embeddings_framework ON public.framework_trigger_embeddings (framework_db_id);
ALTER TABLE public.framework_trigger_embeddings ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "trigger_embeddings_select" ON public.framework_trigger_embeddings FOR SELECT USING (agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE owner_id = auth.uid() OR visibility = 'public')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "trigger_embeddings_insert_own" ON public.framework_trigger_embeddings FOR INSERT WITH CHECK (auth.uid() = (SELECT owner_id FROM public.agent_definitions WHERE id = agent_definition_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "trigger_embeddings_update_deny" ON public.framework_trigger_embeddings FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "trigger_embeddings_delete_own" ON public.framework_trigger_embeddings FOR DELETE USING (auth.uid() = (SELECT owner_id FROM public.agent_definitions WHERE id = agent_definition_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.13 active_memory_entries
CREATE TABLE IF NOT EXISTS public.active_memory_entries (
  id                      uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id                 uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  project_id              uuid        REFERENCES public.projects(id) ON DELETE CASCADE,
  agent_instance_id       uuid        REFERENCES public.agent_instances(id) ON DELETE CASCADE,
  content                 text        NOT NULL,
  source_conversation_id  uuid        REFERENCES public.conversations(id) ON DELETE SET NULL,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_active_memory_single_parent CHECK (
    (project_id IS NOT NULL AND agent_instance_id IS NULL) OR
    (project_id IS NULL AND agent_instance_id IS NOT NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_active_memory_project ON public.active_memory_entries (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_active_memory_agent_instance ON public.active_memory_entries (agent_instance_id) WHERE agent_instance_id IS NOT NULL;
DO $$ BEGIN CREATE TRIGGER trg_active_memory_entries_updated_at BEFORE UPDATE ON public.active_memory_entries FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.active_memory_entries ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "active_memory_entries_select_own" ON public.active_memory_entries FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "active_memory_entries_insert_own" ON public.active_memory_entries FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "active_memory_entries_update_own" ON public.active_memory_entries FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "active_memory_entries_delete_own" ON public.active_memory_entries FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.14 memory_proposals
CREATE TABLE IF NOT EXISTS public.memory_proposals (
  id                 uuid             NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id            uuid             NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  conversation_id    uuid             NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  project_id         uuid             REFERENCES public.projects(id) ON DELETE CASCADE,
  agent_instance_id  uuid             REFERENCES public.agent_instances(id) ON DELETE CASCADE,
  proposed_content   text             NOT NULL,
  status             proposal_status  NOT NULL DEFAULT 'pending',
  trigger_type       proposal_trigger NOT NULL,
  created_at         timestamptz      NOT NULL DEFAULT now(),
  reviewed_at        timestamptz
);
CREATE INDEX IF NOT EXISTS idx_memory_proposals_pending ON public.memory_proposals (user_id, project_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_memory_proposals_agent_pending ON public.memory_proposals (user_id, agent_instance_id) WHERE status = 'pending';
ALTER TABLE public.memory_proposals ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "memory_proposals_select_own" ON public.memory_proposals FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "memory_proposals_update_own" ON public.memory_proposals FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "memory_proposals_insert_deny" ON public.memory_proposals FOR INSERT WITH CHECK (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "memory_proposals_delete_deny" ON public.memory_proposals FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.15 mcp_tokens
CREATE TABLE IF NOT EXISTS public.mcp_tokens (
  id           uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id      uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  token_hash   text        NOT NULL,
  name         text,
  last_used_at timestamptz,
  revoked_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mcp_tokens_user ON public.mcp_tokens (user_id) WHERE revoked_at IS NULL;
ALTER TABLE public.mcp_tokens ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "mcp_tokens_select_own" ON public.mcp_tokens FOR SELECT USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_tokens_insert_own" ON public.mcp_tokens FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_tokens_update_deny" ON public.mcp_tokens FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_tokens_delete_own" ON public.mcp_tokens FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.16 mcp_rate_limits
CREATE TABLE IF NOT EXISTS public.mcp_rate_limits (
  id            uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id       uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  date          date        NOT NULL,
  request_count int         NOT NULL DEFAULT 0,
  daily_cap     int         NOT NULL DEFAULT 1000,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_mcp_rate_limits_user_date UNIQUE (user_id, date)
);
ALTER TABLE public.mcp_rate_limits ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_select_deny" ON public.mcp_rate_limits FOR SELECT USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_insert_deny" ON public.mcp_rate_limits FOR INSERT WITH CHECK (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_update_deny" ON public.mcp_rate_limits FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_delete_deny" ON public.mcp_rate_limits FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.17 retrieval_debug_logs (append-only)
CREATE TABLE IF NOT EXISTS public.retrieval_debug_logs (
  id              uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  message_id      uuid        NOT NULL REFERENCES public.messages(id) ON DELETE CASCADE,
  scope           retrieval_scope NOT NULL,
  query_text      text        NOT NULL,
  query_variants  text[],
  vector_candidates jsonb,
  mmr_selections  jsonb,
  rerank_scores   jsonb,
  gating_decision text        NOT NULL,
  injected_chunks jsonb,
  error_message   text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_retrieval_debug_logs_created_at ON public.retrieval_debug_logs (created_at DESC);
ALTER TABLE public.retrieval_debug_logs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "admin_select_retrieval_debug_logs" ON public.retrieval_debug_logs FOR SELECT USING (EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "deny_user_insert_retrieval_debug_logs" ON public.retrieval_debug_logs FOR INSERT WITH CHECK (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.18 knowledge_bases
CREATE TABLE IF NOT EXISTS public.knowledge_bases (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  project_id            uuid        REFERENCES public.projects(id) ON DELETE CASCADE,
  agent_definition_id   uuid        REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  user_id               uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_knowledge_bases_single_parent CHECK (
    (project_id IS NOT NULL AND agent_definition_id IS NULL) OR
    (project_id IS NULL AND agent_definition_id IS NOT NULL)
  )
);
DO $$ BEGIN CREATE TRIGGER trg_knowledge_bases_updated_at BEFORE UPDATE ON public.knowledge_bases FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.knowledge_bases ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "kb_select" ON public.knowledge_bases FOR SELECT USING (auth.uid() = user_id OR agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE visibility = 'public')); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_insert" ON public.knowledge_bases FOR INSERT WITH CHECK (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_update" ON public.knowledge_bases FOR UPDATE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_delete" ON public.knowledge_bases FOR DELETE USING (auth.uid() = user_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.19 knowledge_base_folders
CREATE TABLE IF NOT EXISTS public.knowledge_base_folders (
  id                uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  knowledge_base_id uuid        NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  parent_folder_id  uuid        REFERENCES public.knowledge_base_folders(id) ON DELETE CASCADE,
  name              text        NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kb_folders_kb ON public.knowledge_base_folders (knowledge_base_id);
ALTER TABLE public.knowledge_base_folders ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "kb_folders_select" ON public.knowledge_base_folders FOR SELECT USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id OR agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE visibility = 'public'))); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_folders_insert" ON public.knowledge_base_folders FOR INSERT WITH CHECK (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_folders_update" ON public.knowledge_base_folders FOR UPDATE USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_folders_delete" ON public.knowledge_base_folders FOR DELETE USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.20 knowledge_base_documents
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
  key_topics        text[],
  document_date     date,
  tags              text[]          DEFAULT '{}',
  status            document_status NOT NULL DEFAULT 'pending',
  error_stage       text,
  error_message     text,
  retry_count       int             NOT NULL DEFAULT 0,
  deleted_at        timestamptz,
  created_at        timestamptz     NOT NULL DEFAULT now(),
  updated_at        timestamptz     NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kb_docs_kb ON public.knowledge_base_documents (knowledge_base_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kb_docs_status ON public.knowledge_base_documents (status) WHERE status != 'completed';
DO $$ BEGIN CREATE TRIGGER trg_knowledge_base_documents_updated_at BEFORE UPDATE ON public.knowledge_base_documents FOR EACH ROW EXECUTE FUNCTION set_updated_at(); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE public.knowledge_base_documents ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "kb_docs_select" ON public.knowledge_base_documents FOR SELECT USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id OR agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE visibility = 'public'))); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_docs_insert" ON public.knowledge_base_documents FOR INSERT WITH CHECK (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_docs_update" ON public.knowledge_base_documents FOR UPDATE USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_docs_delete" ON public.knowledge_base_documents FOR DELETE USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 4.21 knowledge_base_chunks
CREATE TABLE IF NOT EXISTS public.knowledge_base_chunks (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  document_id           uuid        NOT NULL REFERENCES public.knowledge_base_documents(id) ON DELETE CASCADE,
  knowledge_base_id     uuid        NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  project_id            uuid,
  agent_definition_id   uuid,
  text                  text        NOT NULL,
  embedding             vector(3072),
  chunk_summary         text,
  keywords              text[],
  section_path          text,
  page_range            text,
  chunk_index           int         NOT NULL,
  tsv                   tsvector,
  embedding_model       text        NOT NULL DEFAULT 'text-embedding-3-large',
  created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON public.knowledge_base_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON public.knowledge_base_chunks (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_agent_def ON public.knowledge_base_chunks (agent_definition_id) WHERE agent_definition_id IS NOT NULL;
ALTER TABLE public.knowledge_base_chunks ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN CREATE POLICY "kb_chunks_select" ON public.knowledge_base_chunks FOR SELECT USING (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id OR agent_definition_id IN (SELECT id FROM public.agent_definitions WHERE visibility = 'public'))); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_chunks_insert" ON public.knowledge_base_chunks FOR INSERT WITH CHECK (knowledge_base_id IN (SELECT id FROM public.knowledge_bases WHERE auth.uid() = user_id)); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_chunks_update_deny" ON public.knowledge_base_chunks FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "kb_chunks_delete_deny" ON public.knowledge_base_chunks FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =========================================================================
-- 5. Auth trigger — creates public.users row on Supabase Auth signup
-- =========================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.users (id, name, email, role)
  VALUES (
    NEW.id,
    COALESCE(
      NULLIF(TRIM(NEW.raw_user_meta_data->>'name'), ''),
      split_part(NEW.email, '@', 1)
    ),
    NEW.email,
    'user'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DO $$ BEGIN
  CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
EXCEPTION WHEN duplicate_object THEN NULL;
         WHEN insufficient_privilege THEN
           RAISE WARNING 'Cannot create trigger on auth.users — create manually via Supabase Dashboard';
END $$;

-- =========================================================================
-- 6. RPC functions
-- =========================================================================

-- match_framework_triggers (KIN-411)
CREATE OR REPLACE FUNCTION public.match_framework_triggers(
  query_embedding extensions.vector(3072),
  p_agent_id uuid,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  framework_db_id uuid,
  trigger_text text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  RETURN QUERY
  SELECT
    fte.framework_db_id,
    fte.trigger_text,
    1 - (fte.embedding <=> query_embedding) AS similarity
  FROM public.framework_trigger_embeddings fte
  WHERE fte.agent_definition_id = p_agent_id
  ORDER BY fte.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- match_chunks (KIN-429)
CREATE OR REPLACE FUNCTION public.match_chunks(
  query_embedding extensions.vector(3072),
  scope_column text,
  scope_value text,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  document_title text,
  section_path text,
  text text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  IF scope_column NOT IN ('agent_definition_id', 'knowledge_base_id', 'project_id') THEN
    RAISE EXCEPTION 'Invalid scope_column: %', scope_column;
  END IF;

  RETURN QUERY EXECUTE format(
    $q$
    SELECT
      c.id,
      d.title AS document_title,
      c.section_path,
      c.text,
      1 - (c.embedding <=> $1) AS similarity
    FROM public.knowledge_base_chunks c
    JOIN public.knowledge_base_documents d ON d.id = c.document_id
    WHERE c.%I = $2
      AND d.deleted_at IS NULL
    ORDER BY c.embedding <=> $1
    LIMIT $3
    $q$,
    scope_column
  )
  USING query_embedding, scope_value, match_count;
END;
$$;

-- mcp_check_and_increment_rate_limit
CREATE OR REPLACE FUNCTION mcp_check_and_increment_rate_limit(
    p_user_id uuid,
    p_date date
)
RETURNS TABLE(allowed boolean, request_count int, daily_cap int)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH upserted AS (
        INSERT INTO mcp_rate_limits (user_id, date, request_count, daily_cap)
        VALUES (p_user_id, p_date, 1, 1000)
        ON CONFLICT (user_id, date)
        DO UPDATE SET request_count = mcp_rate_limits.request_count + 1
        RETURNING mcp_rate_limits.request_count, mcp_rate_limits.daily_cap
    )
    SELECT
        (upserted.request_count <= upserted.daily_cap) AS allowed,
        upserted.request_count::int,
        upserted.daily_cap::int
    FROM upserted;
END;
$$;

-- =========================================================================
-- 7. Seed data — LLM models (KIN-416)
-- =========================================================================

INSERT INTO public.llm_models (provider, model_id, display_name, category, enabled)
VALUES
  -- Anthropic
  ('anthropic', 'claude-opus-4-6',    'Claude Opus 4.6',    'generation', true),
  ('anthropic', 'claude-sonnet-4-6',  'Claude Sonnet 4.6',  'generation', true),
  ('anthropic', 'claude-sonnet-4-5',  'Claude Sonnet 4.5',  'generation', true),
  ('anthropic', 'claude-haiku-4-5',   'Claude Haiku 4.5',   'generation', true),
  ('anthropic', 'claude-opus-4-5',    'Claude Opus 4.5',    'generation', true),
  ('anthropic', 'claude-opus-4-1',    'Claude Opus 4.1',    'generation', true),
  ('anthropic', 'claude-sonnet-4-0',  'Claude Sonnet 4.0',  'generation', true),
  ('anthropic', 'claude-opus-4-0',    'Claude Opus 4.0',    'generation', true),
  -- Google
  ('google', 'gemini-3.1-pro-preview',        'Gemini 3.1 Pro Preview',        'generation', true),
  ('google', 'gemini-3.1-flash-lite-preview', 'Gemini 3.1 Flash Lite Preview', 'generation', true),
  ('google', 'gemini-3-flash-preview',        'Gemini 3 Flash Preview',        'generation', true),
  ('google', 'gemini-2.5-pro',                'Gemini 2.5 Pro',                'generation', true),
  ('google', 'gemini-2.5-flash',              'Gemini 2.5 Flash',              'generation', true),
  ('google', 'gemini-2.5-flash-lite',         'Gemini 2.5 Flash Lite',         'generation', true),
  -- OpenAI
  ('openai', 'gpt-5.4-pro',           'GPT-5.4 Pro',           'generation', true),
  ('openai', 'gpt-5.4',               'GPT-5.4',               'generation', true),
  ('openai', 'gpt-5.4-mini',          'GPT-5.4 Mini',          'generation', true),
  ('openai', 'gpt-5.4-nano',          'GPT-5.4 Nano',          'generation', true),
  ('openai', 'gpt-5.2-pro',           'GPT-5.2 Pro',           'generation', true),
  ('openai', 'gpt-5.2',               'GPT-5.2',               'generation', true),
  ('openai', 'gpt-5.1',               'GPT-5.1',               'generation', true),
  ('openai', 'gpt-5-pro',             'GPT-5 Pro',             'generation', true),
  ('openai', 'gpt-5',                 'GPT-5',                 'generation', true),
  ('openai', 'gpt-5-mini',            'GPT-5 Mini',            'generation', true),
  ('openai', 'gpt-5-nano',            'GPT-5 Nano',            'generation', true),
  ('openai', 'gpt-4.1',               'GPT-4.1',               'generation', true),
  ('openai', 'gpt-4.1-mini',          'GPT-4.1 Mini',          'generation', true),
  ('openai', 'gpt-4.1-nano',          'GPT-4.1 Nano',          'generation', true),
  ('openai', 'gpt-4o',                'GPT-4o',                'generation', true),
  ('openai', 'gpt-4o-mini',           'GPT-4o Mini',           'generation', true),
  ('openai', 'o4-mini',               'o4 Mini',               'generation', true),
  ('openai', 'o4-mini-2025-04-16',    'o4 Mini (2025-04-16)',  'generation', true),
  ('openai', 'o3-pro',                'o3 Pro',                'generation', true),
  ('openai', 'o3',                    'o3',                    'generation', true),
  ('openai', 'o3-2025-04-16',         'o3 (2025-04-16)',       'generation', true),
  ('openai', 'o3-mini',               'o3 Mini',               'generation', true),
  ('openai', 'o3-mini-2025-01-31',    'o3 Mini (2025-01-31)',  'generation', true),
  ('openai', 'o1-pro',                'o1 Pro',                'generation', true),
  ('openai', 'o1-pro-2025-03-19',     'o1 Pro (2025-03-19)',   'generation', true),
  ('openai', 'o1',                    'o1',                    'generation', true),
  ('openai', 'o1-2024-12-17',         'o1 (2024-12-17)',       'generation', true),
  -- Groq
  ('groq', 'groq/compound',                                 'Compound',               'generation', true),
  ('groq', 'groq/compound-mini',                            'Compound Mini',          'generation', true),
  ('groq', 'llama-3.1-8b-instant',                          'Llama 3.1 8B Instant',   'generation', true),
  ('groq', 'llama-3.3-70b-versatile',                       'Llama 3.3 70B Versatile','generation', true),
  ('groq', 'meta-llama/llama-4-scout-17b-16e-instruct',     'Llama 4 Scout 17B',      'generation', true),
  ('groq', 'openai/gpt-oss-120b',                           'GPT OSS 120B',           'generation', true),
  ('groq', 'openai/gpt-oss-20b',                            'GPT OSS 20B',            'generation', true),
  ('groq', 'qwen/qwen3-32b',                                'Qwen3 32B',              'generation', true),
  -- OpenAI — embedding
  ('openai', 'text-embedding-3-large', 'Text Embedding 3 Large', 'embedding', true),
  ('openai', 'text-embedding-3-small', 'Text Embedding 3 Small', 'embedding', true),
  ('openai', 'text-embedding-ada-002', 'Text Embedding Ada 002', 'embedding', true),
  -- Cohere — reranking
  ('cohere', 'rerank-english-v3.0',      'Rerank English v3.0',      'reranking', true),
  ('cohere', 'rerank-multilingual-v3.0', 'Rerank Multilingual v3.0', 'reranking', true)
ON CONFLICT (model_id) DO NOTHING;

-- =========================================================================
-- Done. All tables, RLS, RPCs, triggers, and seed data applied.
-- =========================================================================
