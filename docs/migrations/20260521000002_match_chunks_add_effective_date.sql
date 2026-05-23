-- DRAFT — recency-aware retrieval, Component B (Task 2).
-- Do NOT apply from here. Task 2 copies this into packages/api/migrations/ with the
-- final timestamp, applies it to the dev Supabase SQL Editor, and INVOKES match_chunks
-- with representative args before shipping (policies/database-migrations.md §2a —
-- KIN-478 shipped a uuid=text bug because the RPC was created but never called).
--
-- Change: add two columns to the match_chunks RETURNS TABLE + SELECT —
--   document_date  (raw, nullable — knowledge_base_documents.document_date)
--   document_created_at (knowledge_base_documents.created_at, cast to date)
-- Python (retrieval.py) derives effective_date = COALESCE(document_date, document_created_at)
-- and date_is_estimated = (document_date IS NULL). The RPC does NOT pre-COALESCE —
-- Python must distinguish a real publish date from an ingestion-date estimate
-- (design § Component B, § Component D).
--
-- created_at is timestamptz; it is cast to `date` here so both returned date columns
-- share one type and PostgREST serializes them identically (a plain "YYYY-MM-DD"
-- string the Python side parses with date.fromisoformat).
--
-- PRESERVED from prior migrations (must not regress):
--   * KIN-476 (20260518000001): query_embedding is `text`, cast to halfvec(3072)
--     inside the body. PostgREST has no JSON-array -> halfvec implicit cast.
--   * KIN-478 (20260521000001): WHERE c.%I = $2::uuid — scope columns are uuid-typed,
--     scope_value is bound as text. Without the ::uuid cast every call raises
--     `operator does not exist: uuid = text`.
--   * deleted_at IS NULL filter on the knowledge_base_documents JOIN — soft-deleted
--     documents are excluded. VERIFIED present in 20260521000001 (line 57); kept here.
--
-- SIGNATURE CHANGE: the RETURNS TABLE column set changes (9 -> 11 columns), so
-- CREATE OR REPLACE alone fails with "cannot change return type of existing function".
-- All historical overloads are dropped first (vector / halfvec / text param variants),
-- mirroring 20260518000001 lines 58-60.

-- ============================================================================
-- 1. Drop all historical match_chunks overloads (signature change)
-- ============================================================================

DROP FUNCTION IF EXISTS public.match_chunks(extensions.vector, text, text, integer);
DROP FUNCTION IF EXISTS public.match_chunks(extensions.halfvec, text, text, integer);
DROP FUNCTION IF EXISTS public.match_chunks(text, text, text, integer);

-- ============================================================================
-- 2. Recreate match_chunks with document_date + document_created_at
-- ============================================================================

CREATE FUNCTION public.match_chunks(
  query_embedding text,                          -- JSON-array text, cast to halfvec inside
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
  similarity double precision,
  document_date date,                            -- NEW — raw, nullable; NULL when unset
  document_created_at date                       -- NEW — knowledge_base_documents.created_at::date
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
  q extensions.halfvec(3072) := query_embedding::extensions.halfvec(3072);
BEGIN
  -- Validate scope_column to prevent SQL injection (only known column names allowed)
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
      1 - (c.embedding <=> $1) AS similarity,
      d.document_date AS document_date,
      d.created_at::date AS document_created_at
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

-- ============================================================================
-- 3. Post-apply verification (run manually in the dev SQL Editor — do NOT skip)
-- ============================================================================
-- policies/database-migrations.md §2a: a created function is not a working function.
-- After applying, invoke with a real agent_definition_id that has ingested chunks and
-- a real 3072-element embedding (copy one from knowledge_base_chunks.embedding::text):
--
--   SELECT id, similarity, document_date, document_created_at
--   FROM public.match_chunks(
--     '<3072-element JSON array as text>',
--     'agent_definition_id',
--     '<agent_definition_id uuid>',
--     5
--   );
--
-- Confirm: 11 columns return; similarity is in (0,1]; document_created_at is never
-- NULL; document_date is NULL for documents ingested before Component A. Then re-run
-- the existing match_chunks regression / smoke test to confirm no behavior change for
-- the 9 pre-existing columns.
