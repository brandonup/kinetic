-- KIN-429: Add match_chunks RPC
-- Vector similarity search on knowledge base chunks with dynamic scope filtering.
-- Called by RAG retrieval pipeline and local MCP server (packages/mcp/).
-- SECURITY DEFINER: bypasses RLS — called from service-role backend only.
-- Uses EXECUTE format(...) for dynamic column filtering (scope_column).

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
  -- Validate scope_column to prevent SQL injection (only known column names allowed)
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
