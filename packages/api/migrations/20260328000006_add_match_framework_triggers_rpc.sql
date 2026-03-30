-- KIN-411: Add match_framework_triggers RPC
-- Called by framework_selection.py for cosine similarity search over trigger embeddings.
-- SECURITY DEFINER: bypasses RLS — called from service-role backend only.
-- Scoped by p_agent_id for tenant isolation.
-- See ADR-007 §5 for full rationale.

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
