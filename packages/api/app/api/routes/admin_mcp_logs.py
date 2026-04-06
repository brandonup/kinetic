"""
Admin MCP Logs API routes — KIN-452.

Endpoints:
  GET /api/v1/admin/mcp/logs   — list recent MCP activity (admin only)
  GET /api/v1/admin/mcp/stats  — aggregated latency stats by agent (admin only)

Schema ref: docs/db-schema-spec.md (messages_mcp)
Admin enforcement: require_admin dependency from app.auth.deps.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.deps import CurrentUser, require_admin
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/mcp", tags=["admin-mcp"])


def get_supabase_client():
    """Return the service-role Supabase client. Defined as a module-level function so tests can patch it."""
    return get_supabase()


@router.get("/logs")
async def list_mcp_logs(
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    List recent MCP activity logs, optionally filtered by user_id.
    Returns {"logs": [...]}.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    def _query():
        q = client.table("messages_mcp").select(
            "id, user_id, agent_slug, query, layer_status, "
            "latency_ms, embedding_latency_ms, error, mcp_session_id, created_at"
        )
        if user_id:
            q = q.eq("user_id", user_id)
        return q.order("created_at", desc=True).limit(limit).execute()

    result = await loop.run_in_executor(None, _query)
    return {"logs": result.data or []}


@router.get("/stats")
async def mcp_log_stats(
    days: int = Query(7, ge=1, le=90),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """
    Aggregated MCP stats: avg latency, avg embedding latency, invocation count by agent.
    Returns {"stats": [...]}.
    """
    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    def _query():
        return (
            client.table("messages_mcp")
            .select("agent_slug, latency_ms, embedding_latency_ms")
            .gte("created_at", cutoff)
            .execute()
        )

    result = await loop.run_in_executor(None, _query)
    rows = result.data or []

    if not rows:
        return {"stats": []}

    # Aggregate in Python (no GROUP BY via PostgREST)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row["agent_slug"]].append(row)

    stats = []
    for slug, entries in buckets.items():
        latencies = [e["latency_ms"] for e in entries if e.get("latency_ms") is not None]
        embed_latencies = [e["embedding_latency_ms"] for e in entries if e.get("embedding_latency_ms") is not None]
        stats.append({
            "agent_slug": slug,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else None,
            "avg_embedding_latency_ms": sum(embed_latencies) / len(embed_latencies) if embed_latencies else None,
            "invocations": len(entries),
        })

    return {"stats": stats}
