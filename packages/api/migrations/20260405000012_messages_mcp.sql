-- messages_mcp table (KIN-452)
-- Logs every assemble_context invocation from the MCP Edge Function.
-- Append-only: no updated_at, no soft-delete.

CREATE TABLE IF NOT EXISTS public.messages_mcp (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id               uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  agent_definition_id   uuid        REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  agent_instance_id     uuid        REFERENCES public.agent_instances(id) ON DELETE CASCADE,
  query                 text        NOT NULL,
  agent_slug            text        NOT NULL,
  context_payload       text,
  layer_persona         text,
  layer_memory          text,
  layer_framework       text,
  layer_kb              text,
  layer_status          jsonb       NOT NULL,
  latency_ms            int,
  embedding_latency_ms  int,
  token_count_estimate  int,
  error                 text,
  mcp_session_id        text,
  created_at            timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_messages_mcp_user ON public.messages_mcp (user_id);
CREATE INDEX idx_messages_mcp_agent_instance ON public.messages_mcp (agent_instance_id);
CREATE INDEX idx_messages_mcp_created ON public.messages_mcp (created_at);

-- RLS
ALTER TABLE public.messages_mcp ENABLE ROW LEVEL SECURITY;

CREATE POLICY messages_mcp_select_own ON public.messages_mcp
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY messages_mcp_insert_service ON public.messages_mcp
  FOR INSERT WITH CHECK (true);
  -- INSERT restricted to service role in practice (Edge Function uses service role key).
  -- No user-facing INSERT endpoint exists.

CREATE POLICY messages_mcp_update_deny ON public.messages_mcp
  FOR UPDATE USING (false);

CREATE POLICY messages_mcp_delete_deny ON public.messages_mcp
  FOR DELETE USING (false);

-- memory_proposals: make conversation_id nullable, add mcp_message_id FK
ALTER TABLE public.memory_proposals
  ALTER COLUMN conversation_id DROP NOT NULL;

ALTER TABLE public.memory_proposals
  ADD COLUMN IF NOT EXISTS mcp_message_id uuid REFERENCES public.messages_mcp(id) ON DELETE CASCADE;

ALTER TABLE public.memory_proposals
  ADD CONSTRAINT chk_memory_proposals_source
  CHECK (conversation_id IS NOT NULL OR mcp_message_id IS NOT NULL);
