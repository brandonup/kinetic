-- KIN-476: Switch embeddings to Gemini-001 native 3072 dims, using halfvec for HNSW
--
-- Supersedes KIN-467 (20260407000002_gemini_embeddings_1024.sql).
-- Reason: 1024 was chosen because pgvector's HNSW had a 2000-dim limit for the
-- standard `vector` type. pgvector 0.8 supports HNSW on `halfvec` up to 4000 dims,
-- so we can use Gemini-001's native 3072 output for better retrieval quality with
-- ~50% storage savings vs vector(3072).
--
-- PREREQUISITE: tables must be empty. This migration TRUNCATEs both embedding tables
-- and the single sample document row that produced the chunks; framework source rows
-- in `frameworks` are preserved and will be re-embedded via the admin backfill endpoint
-- (POST /api/v1/admin/backfill-trigger-embeddings, per ADR-007).
--
-- RPC parameter type note (Gilfoyle C2): the RPC `query_embedding` parameter is
-- declared as `text` rather than `halfvec(3072)`. PostgREST has no implicit JSON-array
-- → halfvec cast, so Python `list[float]` callers from supabase.rpc() would fail.
-- We accept the embedding as JSON-text and cast inside the function — pgvector's
-- text → halfvec cast is well-supported. This keeps the Python call sites unchanged.
--
-- After this migration:
--   1. Deploy code change (config.py + embedder.py) — Railway picks up new binary.
--   2. Trigger admin backfill to re-embed 900 framework triggers (184 frameworks).
--   3. Re-ingest sample doc / proceed to KIN-471 smoke test, then KIN-475 bulk upload.

-- ============================================================================
-- 1. Wipe existing embedding data (1024 vectors aren't valid 3072 inputs)
-- ============================================================================

TRUNCATE TABLE public.knowledge_base_chunks;

-- knowledge_base_documents is FK'd by chunks (already truncated above), so DELETE is safe.
-- scrape_source_posts.document_id is ON DELETE SET NULL, so this is safe too.
DELETE FROM public.knowledge_base_documents;

TRUNCATE TABLE public.framework_trigger_embeddings;

-- ============================================================================
-- 2. Drop existing HNSW indexes (column type change requires dropping indexes first)
-- ============================================================================

DROP INDEX IF EXISTS public.idx_kb_chunks_embedding_hnsw;
DROP INDEX IF EXISTS public.idx_fw_trigger_embeddings_hnsw;

-- ============================================================================
-- 3. ALTER vector columns: vector(1024) -> halfvec(3072)
-- ============================================================================

ALTER TABLE public.knowledge_base_chunks
  ALTER COLUMN embedding TYPE extensions.halfvec(3072);

ALTER TABLE public.framework_trigger_embeddings
  ALTER COLUMN embedding TYPE extensions.halfvec(3072);

-- ============================================================================
-- 4. Drop old RPC overloads (re-runnability — covers vector, halfvec, text variants)
-- ============================================================================

DROP FUNCTION IF EXISTS public.match_chunks(extensions.vector, text, text, integer);
DROP FUNCTION IF EXISTS public.match_chunks(extensions.halfvec, text, text, integer);
DROP FUNCTION IF EXISTS public.match_chunks(text, text, text, integer);

DROP FUNCTION IF EXISTS public.match_framework_triggers(extensions.vector, uuid, integer);
DROP FUNCTION IF EXISTS public.match_framework_triggers(extensions.halfvec, uuid, integer);
DROP FUNCTION IF EXISTS public.match_framework_triggers(text, uuid, integer);

-- ============================================================================
-- 5. Recreate RPCs with `text` parameter + internal halfvec(3072) cast
-- ============================================================================

-- match_framework_triggers — cosine similarity search over trigger embeddings
CREATE OR REPLACE FUNCTION public.match_framework_triggers(
  query_embedding text,
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
DECLARE
  q extensions.halfvec(3072) := query_embedding::extensions.halfvec(3072);
BEGIN
  RETURN QUERY
  SELECT
    fte.framework_db_id,
    fte.trigger_text,
    1 - (fte.embedding <=> q) AS similarity
  FROM public.framework_trigger_embeddings fte
  WHERE fte.agent_definition_id = p_agent_id
  ORDER BY fte.embedding <=> q
  LIMIT match_count;
END;
$$;

-- match_chunks — scope-filtered vector search on knowledge_base_chunks
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
    WHERE c.%I = $2
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
-- 6. Create HNSW indexes with halfvec_cosine_ops
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding_hnsw
  ON public.knowledge_base_chunks
  USING hnsw (embedding extensions.halfvec_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_fw_trigger_embeddings_hnsw
  ON public.framework_trigger_embeddings
  USING hnsw (embedding extensions.halfvec_cosine_ops);
