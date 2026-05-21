-- Fix match_chunks — cast scope_value to uuid.
--
-- Bug (shipped in 20260518000001_kin476_embeddings_3072_halfvec.sql): the dynamic
-- query filtered `WHERE c.%I = $2`, where $2 (scope_value) is bound as `text` but
-- every valid scope column — agent_definition_id, project_id, knowledge_base_id —
-- is a `uuid` column. Postgres has no implicit `uuid = text` operator, so
-- match_chunks raised `operator does not exist: uuid = text` on EVERY call.
-- The MCP/API KB-search path caught the error and silently returned zero results.
--
-- Fix: cast the bind parameter inside the dynamic query — `WHERE c.%I = $2::uuid`.
-- Signature is unchanged, so CREATE OR REPLACE is sufficient (no DROP needed).
-- match_framework_triggers is unaffected — its p_agent_id parameter is already uuid-typed.

CREATE OR REPLACE FUNCTION public.match_chunks(
  query_embedding text,
  scope_column text,
  scope_value text,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  document_title text,
  document_type text,
  text text,
  chunk_index integer,
  section_path text,
  page_range text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  q extensions.halfvec(3072) := query_embedding::extensions.halfvec(3072);
BEGIN
  IF scope_column NOT IN ('agent_definition_id', 'knowledge_base_id', 'project_id') THEN
    RAISE EXCEPTION 'Invalid scope_column: %', scope_column;
  END IF;

  RETURN QUERY EXECUTE format(
    $q$
    SELECT
      c.id,
      c.document_id,
      d.title AS document_title,
      d.file_type AS document_type,
      c.text,
      c.chunk_index,
      c.section_path,
      c.page_range,
      1 - (c.embedding <=> $1) AS similarity
    FROM public.knowledge_base_chunks c
    JOIN public.knowledge_base_documents d ON d.id = c.document_id
    WHERE c.%I = $2::uuid
      AND d.deleted_at IS NULL
    ORDER BY c.embedding <=> $1
    LIMIT $3
    $q$,
    scope_column
  )
  USING q, scope_value, match_count;
END;
$$;
