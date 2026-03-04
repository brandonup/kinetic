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
