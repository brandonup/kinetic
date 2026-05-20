-- KIN-464: Create mcp_rate_limits table and RPC.
-- Eliminates "Rate limit RPC error (fail-open)" warning spam in Edge Function logs.
--
-- Table may already exist from 000_complete_schema.sql on fresh instances.
-- CREATE TABLE IF NOT EXISTS is safe to re-run.

-- 1. Table
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

-- RLS: service-role only (no direct user access)
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_select_deny" ON public.mcp_rate_limits FOR SELECT USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_insert_deny" ON public.mcp_rate_limits FOR INSERT WITH CHECK (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_update_deny" ON public.mcp_rate_limits FOR UPDATE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE POLICY "mcp_rate_limits_delete_deny" ON public.mcp_rate_limits FOR DELETE USING (false); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 2. RPC: atomic check-and-increment
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
