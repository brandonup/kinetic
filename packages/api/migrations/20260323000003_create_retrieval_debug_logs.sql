-- Migration: create retrieval_debug_logs table
-- KIN-326: Admin RAG Debug Tab
-- Schema ref: docs/db-schema-spec.md §20

-- Append-only table — no updated_at column per schema conventions.
-- Retention: rows auto-purge after 30 days via scheduled job.
-- RLS: SELECT admin-only; INSERT service-role only.

CREATE TABLE IF NOT EXISTS retrieval_debug_logs (
    id              uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    message_id      uuid        NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
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

-- Index for paginated list queries (created_at DESC cursor)
CREATE INDEX IF NOT EXISTS idx_retrieval_debug_logs_created_at
    ON retrieval_debug_logs (created_at DESC);

-- Row-Level Security
ALTER TABLE retrieval_debug_logs ENABLE ROW LEVEL SECURITY;

-- SELECT: admin role only (EXISTS subquery against public.users — avoids JWT claim reliance)
CREATE POLICY "admin_select_retrieval_debug_logs"
    ON retrieval_debug_logs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    );

-- INSERT: service role only (no user-facing inserts)
-- Service role bypasses RLS by default — no explicit policy needed.
-- Deny all user-role inserts:
CREATE POLICY "deny_user_insert_retrieval_debug_logs"
    ON retrieval_debug_logs
    FOR INSERT
    WITH CHECK (false);
