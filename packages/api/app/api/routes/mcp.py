"""
MCP context endpoint — KIN-321.

POST /api/v1/mcp/context

Auth: SHA-256 bearer token looked up in mcp_tokens (NOT Supabase JWT).
Scope: project_id, company_id, agent_id (at least one required).
Context layers assembled (spec §4.2):
  L1 = users.name + users.bio
  L2 = companies.name + companies.description
  L3 = projects.instructions
  L4 = omitted (no conversation history — MCP is stateless, ADR-006 §6)
  L5 = agent_definitions.instructions
  L6 = omitted (AgentInstance active memory is private)
  L7/L8/L9 = pending KIN-322 (framework + RAG)

Validation order (ADR-006 §4): Auth → Rate limit → Scope → Assemble.

Schema: docs/db-schema-spec.md §18 (mcp_tokens), §21 (mcp_rate_limits), §1 (users),
        §3 (companies), §4 (projects), §8 (agent_definitions)
Spec: docs/specs/mcp-spec.md
ADR: docs/adr-006-mcp-server.md
Conventions: all Supabase calls in async def use run_in_executor (conventions.md § Supabase in Async Code)
"""

import asyncio
import hashlib
import logging
import math
from datetime import date
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.errors import AuthenticationError, NotFoundError, RateLimitError, ValidationError
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Module-level so tests can patch it."""
    return get_supabase()


def _hash_token(raw: str) -> str:
    """SHA-256 hash of a raw MCP token. Per ADR-006 §1."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_valid_uuid(value: str) -> bool:
    from uuid import UUID
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def resolve_layers(
    project_id: Optional[str],
    agent_id: Optional[str],
    company_id: Optional[str],
) -> list[str]:
    """
    Return context layers to assemble for the given scope combination.

    Scoping table (spec §4.2):
      project only          → L1, L2, L3
      project + agent       → L1, L2, L3, L5
      agent only            → L1, L5          (no L2 — no company when agent-only)
      company only          → L1, L2          (no L3 — no project instructions)
      project + company     → L1, L2, L3      (project wins L3; company used for L2)
      all three             → L1, L2, L3, L5
      agent + company       → L1, L2, L5
    """
    layers = ["L1"]
    if project_id or company_id:
        layers.append("L2")
    if project_id:
        layers.append("L3")
    if agent_id:
        layers.append("L5")
    return layers


async def _authenticate(request: Request, client) -> str:
    """
    Validate MCP bearer token. Returns user_id on success.

    Raises AuthenticationError (401) if the header is missing, non-Bearer scheme,
    or the token hash is not in mcp_tokens (or is revoked).

    Fire-and-forget: schedules last_used_at update via run_in_executor (no await).
    """
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    raw_token = auth_header[len("Bearer "):]
    if raw_token.startswith("mcp_"):
        raw_token = raw_token[4:]

    token_hash = _hash_token(raw_token)
    loop = asyncio.get_running_loop()

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .select("id, user_id, revoked_at")
            .eq("token_hash", token_hash)
            .is_("revoked_at", "null")
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthenticationError("Invalid or revoked MCP token")

    token_id = result.data["id"]
    user_id = result.data["user_id"]

    # Fire-and-forget: stamp last_used_at — does not block response
    loop.run_in_executor(
        None,
        lambda: client.table("mcp_tokens").update({"last_used_at": "now()"}).eq("id", token_id).execute(),
    )
    return user_id


async def _check_rate_limit(user_id: str, client, loop: asyncio.AbstractEventLoop) -> None:
    """
    Enforce per-user daily rate limit (ADR-006 §3).

    Checks mcp_rate_limits for today's row. If request_count >= daily_cap,
    raises RateLimitError (429). Otherwise increments the counter via UPSERT.
    """
    today = date.today().isoformat()

    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_rate_limits")
            .select("request_count, daily_cap")
            .eq("user_id", user_id)
            .eq("date", today)
            .execute(),
    )

    rows = result.data if isinstance(result.data, list) else []
    if rows:
        row = rows[0]
        if row["request_count"] >= row["daily_cap"]:
            raise RateLimitError(
                "Daily MCP request limit reached",
                details={"daily_cap": row["daily_cap"]},
            )
        new_count = row["request_count"] + 1
    else:
        new_count = 1

    await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_rate_limits")
            .upsert(
                {"user_id": user_id, "date": today, "request_count": new_count},
                on_conflict="user_id,date",
            )
            .execute(),
    )


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class MCPContextRequest(BaseModel):
    query: str
    project_id: Optional[str] = None
    company_id: Optional[str] = None
    agent_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/context")
async def mcp_context(
    body: MCPContextRequest,
    request: Request,
) -> dict:
    """
    Assemble and return context for an MCP client.

    Auth uses MCP bearer token, not Supabase JWT.
    At least one scope param required: project_id, company_id, agent_id.

    Returns: context (str), metadata (layers_assembled, token_count_estimate,
             matched_framework_id, matched_framework_name, sources)
    """
    client = get_supabase_client()
    loop = asyncio.get_running_loop()

    # Step 1: Auth
    user_id = await _authenticate(request, client)

    # Step 2: Rate limit (ADR-006 §4 order: Auth → Rate limit → Scope → Assemble)
    await _check_rate_limit(user_id, client, loop)

    # Step 3: Scope validation
    if not body.project_id and not body.company_id and not body.agent_id:
        raise ValidationError(
            "At least one scope parameter is required: project_id, company_id, or agent_id",
            details={"code": "MISSING_SCOPE"},
        )

    for field, value in [
        ("project_id", body.project_id),
        ("company_id", body.company_id),
        ("agent_id", body.agent_id),
    ]:
        if value and not _is_valid_uuid(value):
            raise ValidationError(f"Invalid UUID for {field}: {value!r}")

    # Step 4: Fetch entities

    # L1 — user profile (always fetched)
    user_result = await loop.run_in_executor(
        None,
        lambda: client
            .table("users")
            .select("id, name, bio")
            .eq("id", user_id)
            .single()
            .execute(),
    )
    user = user_result.data or {}

    # L3 — project (ownership enforced via user_id filter)
    project_row = None
    if body.project_id:
        r = await loop.run_in_executor(
            None,
            lambda: client
                .table("projects")
                .select("id, name, instructions, company_id")
                .eq("id", body.project_id)
                .eq("user_id", user_id)
                .single()
                .execute(),
        )
        if not r.data:
            raise NotFoundError("Project not found")
        project_row = r.data

    # Cross-scope validation §6.4: when both company_id and project_id provided,
    # verify projects.company_id = body.company_id (spec §6.4)
    if body.project_id and body.company_id and project_row:
        if project_row.get("company_id") != body.company_id:
            raise ValidationError(
                "company_id does not match the project's company",
                details={"code": "SCOPE_MISMATCH"},
            )

    # L2 — company
    # When project_id given: fetch via project's company_id (ownership already verified via project)
    # When explicit company_id without project: ownership check via user_id
    company_row = None
    effective_company_id = None
    if project_row:
        effective_company_id = project_row.get("company_id")
    elif body.company_id:
        effective_company_id = body.company_id

    if effective_company_id and (body.project_id or body.company_id):
        if project_row and not body.company_id:
            # Fetched via project's parent — no separate user_id ownership check needed
            r = await loop.run_in_executor(
                None,
                lambda: client
                    .table("companies")
                    .select("id, name, description")
                    .eq("id", effective_company_id)
                    .single()
                    .execute(),
            )
        else:
            # Explicit company_id — enforce ownership
            r = await loop.run_in_executor(
                None,
                lambda: client
                    .table("companies")
                    .select("id, name, description")
                    .eq("id", effective_company_id)
                    .eq("user_id", user_id)
                    .single()
                    .execute(),
            )
        if not r.data:
            raise NotFoundError("Company not found")
        company_row = r.data

    # L5 — agent (public agents accessible to all; private agents owner-only — ADR-006 §4)
    agent_row = None
    if body.agent_id:
        r = await loop.run_in_executor(
            None,
            lambda: client
                .table("agent_definitions")
                .select("id, name, instructions, visibility, owner_id")
                .eq("id", body.agent_id)
                .single()
                .execute(),
        )
        if not r.data:
            raise NotFoundError("Agent not found")
        agent_row = r.data
        # ACL: private agents are owner-only; return 404 to avoid confirming existence
        if agent_row["visibility"] != "public" and agent_row["owner_id"] != user_id:
            raise NotFoundError("Agent not found")

    # Step 5: Assemble context
    layers = resolve_layers(body.project_id, body.agent_id, body.company_id)

    parts: list[str] = []

    # L1: user profile
    user_section = f"User: {user.get('name', '')}"
    if user.get("bio"):
        user_section += f"\nBio: {user['bio']}"
    parts.append(user_section)

    # L2: company
    if "L2" in layers and company_row:
        company_section = f"Company: {company_row.get('name', '')}"
        if company_row.get("description"):
            company_section += f"\nDescription: {company_row['description']}"
        parts.append(company_section)

    # L3: project instructions
    if "L3" in layers and project_row:
        parts.append(
            f"Project: {project_row.get('name', '')}\n"
            f"Instructions: {project_row.get('instructions', '')}"
        )

    # L5: agent instructions
    if "L5" in layers and agent_row:
        parts.append(
            f"Agent: {agent_row.get('name', '')}\n"
            f"Instructions: {agent_row.get('instructions', '')}"
        )

    context = "\n\n".join(parts)

    return {
        "context": context,
        "metadata": {
            "layers_assembled": layers,
            "token_count_estimate": math.ceil(len(context) / 4),
            "matched_framework_id": None,
            "matched_framework_name": None,
            "sources": [],
        },
    }
