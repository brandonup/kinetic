-- Migration: mcp_check_and_increment_rate_limit RPC
-- KIN-321 fix: atomic rate limit check-and-increment per ADR-006 §3
--
-- Performs INSERT ... ON CONFLICT DO UPDATE SET request_count = request_count + 1
-- in a single transaction, then returns whether the post-increment count is within cap.
-- Called by _check_rate_limit in app/api/routes/mcp.py.

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
