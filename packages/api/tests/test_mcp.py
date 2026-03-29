"""
Tests for MCP context endpoint — KIN-321.

POST /api/v1/mcp/context

Auth: SHA-256 bearer token looked up in mcp_tokens (NOT Supabase JWT).
Schema: docs/db-schema-spec.md §18 (mcp_tokens), §1 (users), §3 (companies),
        §4 (projects), §8 (agent_definitions)
Spec: docs/specs/mcp-spec.md
ADR: docs/adr-006-mcp-server.md

Layer definitions (spec §4.2):
  L1 = users.name + users.bio
  L2 = companies.name + companies.description
  L3 = projects.instructions
  L5 = agent_definitions.instructions

Scoping table:
  project only        → L1, L2, L3
  project + agent     → L1, L2, L3, L5
  agent only          → L1, L5
  company only        → L1, L2
  company + agent     → L1, L2, L5
  company + project   → L1, L2, L3
  all three           → L1, L2, L3, L5

All tests are unit-tier: `get_supabase_client` is patched; no real DB.
Uses `raw_client` from conftest.py (no dependency overrides — MCP uses bearer token auth).
"""

import math
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.rag.framework_selection import FrameworkMatch


# ---------------------------------------------------------------------------
# Auto-patch: RAG and framework selection return empty/no-match by default.
# Individual tests override these when testing L7/L8/L9 specifically.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_pipeline_services(monkeypatch):
    """Patch retrieve and select_framework to no-op for all MCP tests."""
    async def _no_rag(*args, **kwargs):
        return []

    async def _no_framework(*args, **kwargs):
        return FrameworkMatch(matched_framework_id=None, matched_framework_name=None, framework_text=None)

    monkeypatch.setattr("app.api.routes.mcp.retrieve", _no_rag)
    monkeypatch.setattr("app.api.routes.mcp.select_framework", _no_framework)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PATCH_TARGET = "app.api.routes.mcp.get_supabase_client"
PATCH_RETRIEVE = "app.api.routes.mcp.retrieve"
PATCH_SELECT_FRAMEWORK = "app.api.routes.mcp.select_framework"

MCP_USER_ID = str(uuid4())
MCP_TOKEN_ID = str(uuid4())
COMPANY_ID = str(uuid4())
PROJECT_ID = str(uuid4())
AGENT_ID = str(uuid4())

MCP_TOKEN_ROW = {"id": MCP_TOKEN_ID, "user_id": MCP_USER_ID, "revoked_at": None}
USER_ROW = {"id": MCP_USER_ID, "name": "Alice", "bio": "Builder and maker."}
COMPANY_ROW = {
    "id": COMPANY_ID,
    "user_id": MCP_USER_ID,
    "name": "ACME Corp",
    "description": "We build things.",
}
PROJECT_ROW = {
    "id": PROJECT_ID,
    "company_id": COMPANY_ID,
    "user_id": MCP_USER_ID,
    "name": "Alpha Project",
    "instructions": "Always be concise.",
}
AGENT_ROW = {
    "id": AGENT_ID,
    "owner_id": MCP_USER_ID,
    "name": "Strategist",
    "instructions": "Think strategically about every problem.",
    "visibility": "public",
}

VALID_BEARER = "Bearer valid-mcp-token-abc123"
QUERY = "What should I prioritize this week?"


# ---------------------------------------------------------------------------
# Mock builder
# ---------------------------------------------------------------------------


def _make_db_mock(
    token_data=MCP_TOKEN_ROW,
    user_data=USER_ROW,
    project_data=PROJECT_ROW,
    company_data=COMPANY_ROW,
    agent_data=AGENT_ROW,
    rate_limit_data=None,
):
    """
    Build a Supabase mock that routes .table(name) and .rpc(name) calls to
    per-entity responses.

    Chain patterns:
      mcp_tokens lookup:    .select().eq().is_().single().execute()
      projects:             .select().eq(id).eq(user_id).single().execute()
      companies (one-eq):   .select().eq(id).single().execute()  (via project's company_id)
      companies (two-eq):   .select().eq(id).eq(user_id).single().execute()  (explicit company_id)
      users/agents:         .select().eq().single().execute()
      rate limit RPC:       .rpc("mcp_check_and_increment_rate_limit", ...).execute()
                            → [{"allowed": bool, "request_count": int, "daily_cap": int}]
    """
    if rate_limit_data is None:
        # Default: first request today — allowed
        rate_limit_data = [{"allowed": True, "request_count": 1, "daily_cap": 1000}]

    mock = MagicMock()

    def _table_side_effect(table_name):
        chain = MagicMock()
        if table_name == "mcp_tokens":
            # Token lookup: .select().eq().is_().single().execute()
            chain.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data=token_data
            )
            # last_used_at update (fire-and-forget): .update().eq().execute()
            chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "users":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=user_data
            )
        elif table_name == "projects":
            # Ownership filter: .select().eq(id).eq(user_id).single().execute()
            chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=project_data
            )
        elif table_name == "companies":
            # One-eq path: via project's company_id (no user_id filter)
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=company_data
            )
            # Two-eq path: explicit company_id with ownership filter
            chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=company_data
            )
        elif table_name == "agent_definitions":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=agent_data
            )
        return chain

    def _rpc_side_effect(fn_name, params=None):
        chain = MagicMock()
        if fn_name == "mcp_check_and_increment_rate_limit":
            chain.execute.return_value = MagicMock(data=rate_limit_data)
        return chain

    mock.table.side_effect = _table_side_effect
    mock.rpc.side_effect = _rpc_side_effect
    return mock


# ---------------------------------------------------------------------------
# TestMCPTokenAuth — 401 on bad/missing/revoked tokens
# ---------------------------------------------------------------------------


class TestMCPTokenAuth:
    def test_missing_authorization_header_returns_401(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
            )
        assert resp.status_code == 401

    def test_non_bearer_scheme_returns_401(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": "Basic sometoken"},
            )
        assert resp.status_code == 401

    def test_token_not_in_db_returns_401(self, raw_client):
        mock_db = _make_db_mock(token_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 401

    def test_valid_token_allows_request(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200

    def test_401_response_has_error_shape(self, raw_client):
        mock_db = _make_db_mock(token_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


# ---------------------------------------------------------------------------
# TestMCPRequestValidation — 400 on bad scope params
# ---------------------------------------------------------------------------


class TestMCPRequestValidation:
    def test_no_scope_params_returns_400(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 400

    def test_no_scope_params_returns_missing_scope_code(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY},
                headers={"Authorization": VALID_BEARER},
            )
        body = resp.json()
        assert "MISSING_SCOPE" in str(body)

    def test_invalid_uuid_company_id_returns_400(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": "not-a-uuid"},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 400

    def test_invalid_uuid_project_id_returns_400(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": "bad-uuid"},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 400

    def test_invalid_uuid_agent_id_returns_400(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": "not-a-uuid"},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 400

    def test_entity_not_found_project_returns_404(self, raw_client):
        mock_db = _make_db_mock(project_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_entity_not_found_company_returns_404(self, raw_client):
        mock_db = _make_db_mock(company_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_entity_not_found_agent_returns_404(self, raw_client):
        mock_db = _make_db_mock(agent_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_cross_scope_mismatch_returns_400(self, raw_client):
        """project_id + company_id where company doesn't match project's company → 400 scope_mismatch."""
        other_company_id = str(uuid4())
        # PROJECT_ROW has company_id = COMPANY_ID; sending a different company_id
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID, "company_id": other_company_id},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 400
        assert "SCOPE_MISMATCH" in str(resp.json())

    def test_cross_scope_matching_company_returns_200(self, raw_client):
        """project_id + correct company_id (same as project's company) → 200."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestMCPScopeRouting — all 7 valid scope combinations (spec §4.2)
# ---------------------------------------------------------------------------


class TestMCPScopeRouting:
    """
    Scoping table (spec §4.2):
      project_id only           → L1, L2, L3            (no L5)
      project_id + agent_id     → L1, L2, L3, L5
      agent_id only             → L1, L5                (no L2, no L3)
      company_id only           → L1, L2                (no L3, no L5)
      project_id + company_id   → L1, L2, L3            (no L5)
      all three                 → L1, L2, L3, L5
      agent_id + company_id     → L1, L2, L5            (no L3)
    """

    def _layers(self, resp) -> list:
        return resp.json()["metadata"]["layers_assembled"]

    def test_project_only_has_l1_l2_l3_no_l5(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" in layers
        assert "L5" not in layers

    def test_project_and_agent_has_l1_l2_l3_l5(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" in layers
        assert "L5" in layers

    def test_agent_only_has_l1_l5_no_l2_no_l3(self, raw_client):
        """Agent-only scope: no company or project context — L2 and L3 must be absent."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L5" in layers
        assert "L2" not in layers
        assert "L3" not in layers

    def test_company_only_has_l1_l2_no_l3_no_l5(self, raw_client):
        """Company-only scope: company context but no project instructions (L3 absent)."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" not in layers
        assert "L5" not in layers

    def test_project_and_company_has_l1_l2_l3_no_l5(self, raw_client):
        """project + matching company_id: project wins L3; no agent L5."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                # COMPANY_ID matches PROJECT_ROW['company_id']
                json={"query": QUERY, "project_id": PROJECT_ID, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" in layers
        assert "L5" not in layers
        # Context should contain project instructions
        assert PROJECT_ROW["instructions"] in resp.json()["context"]

    def test_all_three_has_l1_l2_l3_l5(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={
                    "query": QUERY,
                    "project_id": PROJECT_ID,
                    "agent_id": AGENT_ID,
                    "company_id": COMPANY_ID,
                },
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L3" in layers
        assert "L5" in layers

    def test_agent_and_company_has_l1_l2_l5_no_l3(self, raw_client):
        """agent + company: company context included (L2), no project (L3 absent)."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        layers = self._layers(resp)
        assert "L1" in layers
        assert "L2" in layers
        assert "L5" in layers
        assert "L3" not in layers

    def test_l4_never_assembled(self, raw_client):
        """L4 (conversation history) is always omitted in MCP context (ADR-006 §6)."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={
                    "query": QUERY,
                    "project_id": PROJECT_ID,
                    "agent_id": AGENT_ID,
                    "company_id": COMPANY_ID,
                },
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert "L4" not in resp.json()["metadata"]["layers_assembled"]


# ---------------------------------------------------------------------------
# TestMCPContextAssembly — response shape and content
# ---------------------------------------------------------------------------


class TestMCPContextAssembly:
    def test_response_has_required_fields(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data
        assert "metadata" in data
        meta = data["metadata"]
        assert "layers_assembled" in meta
        assert "token_count_estimate" in meta
        assert "matched_framework_id" in meta
        assert "matched_framework_name" in meta
        assert "sources" in meta

    def test_sources_is_empty_list(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.json()["metadata"]["sources"] == []

    def test_matched_framework_id_is_null(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.json()["metadata"]["matched_framework_id"] is None

    def test_matched_framework_name_is_null(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.json()["metadata"]["matched_framework_name"] is None

    def test_token_count_estimate_is_ceil_of_context_over_4(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        data = resp.json()
        expected = math.ceil(len(data["context"]) / 4)
        assert data["metadata"]["token_count_estimate"] == expected

    def test_context_contains_user_name(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert USER_ROW["name"] in resp.json()["context"]

    def test_context_contains_company_description_for_company_scope(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert COMPANY_ROW["description"] in resp.json()["context"]

    def test_context_contains_project_instructions_for_project_scope(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert PROJECT_ROW["instructions"] in resp.json()["context"]

    def test_context_contains_agent_instructions_when_agent_present(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert AGENT_ROW["instructions"] in resp.json()["context"]

    def test_context_is_nonempty_string(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert isinstance(resp.json()["context"], str)
        assert len(resp.json()["context"]) > 0

    def test_user_bio_included_when_present(self, raw_client):
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert USER_ROW["bio"] in resp.json()["context"]

    def test_user_bio_omitted_when_null(self, raw_client):
        user_no_bio = {**USER_ROW, "bio": None}
        mock_db = _make_db_mock(user_data=user_no_bio)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert USER_ROW["name"] in resp.json()["context"]

    def test_project_scope_includes_company_context_in_l2(self, raw_client):
        """When project_id is given, company is fetched via project's company_id for L2."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        # L2 company context should be present for project scope
        assert COMPANY_ROW["name"] in resp.json()["context"]

    def test_agent_only_context_excludes_company_data(self, raw_client):
        """Agent-only scope has no L2 — company data must not appear in context."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert COMPANY_ROW["description"] not in resp.json()["context"]


# ---------------------------------------------------------------------------
# TestMCPRateLimit — 429 on daily cap exceeded, 200 on first request
# ---------------------------------------------------------------------------


class TestMCPRateLimit:
    def test_rate_limit_exceeded_returns_429(self, raw_client):
        """RPC returns allowed=False → cap exceeded, should 429."""
        at_cap = [{"allowed": False, "request_count": 1001, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429

    def test_first_request_today_succeeds(self, raw_client):
        """RPC returns allowed=True → first request today, should proceed."""
        mock_db = _make_db_mock()  # default = allowed, request_count=1
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestMCPEntityACL — ownership checks prevent cross-user data access
# ---------------------------------------------------------------------------


class TestMCPEntityACL:
    """KIN-324: access control — anti-enumeration: 404 for both not-found and not-authorized."""

    def test_project_not_owned_returns_404(self, raw_client):
        """project_data=None simulates ownership filter returning no row → 404."""
        mock_db = _make_db_mock(project_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_private_agent_not_owned_returns_404(self, raw_client):
        """Private agent owned by a different user → 404 (anti-enumeration, spec §6.2)."""
        other_owner = str(uuid4())
        private_agent = {**AGENT_ROW, "visibility": "private", "owner_id": other_owner}
        mock_db = _make_db_mock(agent_data=private_agent)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_public_agent_not_owned_is_accessible(self, raw_client):
        """Public agent owned by another user → 200 (spec §6.2: public = any auth'd user)."""
        other_owner = str(uuid4())
        public_agent = {**AGENT_ROW, "visibility": "public", "owner_id": other_owner}
        mock_db = _make_db_mock(agent_data=public_agent)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200

    def test_owner_accessing_own_private_agent_returns_200(self, raw_client):
        """Owner of a private agent can access it via MCP."""
        own_private = {**AGENT_ROW, "visibility": "private", "owner_id": MCP_USER_ID}
        mock_db = _make_db_mock(agent_data=own_private)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200

    def test_company_not_owned_returns_404(self, raw_client):
        """company_data=None simulates ownership filter returning no row → 404."""
        mock_db = _make_db_mock(company_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404



# ---------------------------------------------------------------------------
# TestMCPRevocationExplicit — token with revoked_at set is rejected
# ---------------------------------------------------------------------------


class TestMCPRevocationExplicit:
    def test_revoked_token_returns_401(self, raw_client):
        """Token with revoked_at populated should be rejected.

        The .is_("revoked_at", "null") filter excludes revoked tokens from the
        DB query, so the result is data=None — same 401 path as missing token.
        """
        mock_db = _make_db_mock(token_data=None)  # revoked token excluded by query
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestMCPRateLimitHeaders — pending KIN-323
# 429 responses must include Retry-After and X-RateLimit-Remaining headers.
# NOTE: Implementation gap — mcp.py RateLimitError response does not currently
# set these headers. Big Head must add them in KIN-323.
# ---------------------------------------------------------------------------


class TestMCPRateLimitHeaders:
    def test_rate_limit_429_includes_retry_after_header(self, raw_client):
        """KIN-323: 429 response must include Retry-After header (seconds until UTC midnight)."""
        at_cap = [{"allowed": False, "request_count": 1001, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        # Retry-After is seconds — must be a positive integer
        assert int(resp.headers["Retry-After"]) > 0

    def test_rate_limit_429_includes_x_ratelimit_remaining_zero(self, raw_client):
        """KIN-323: 429 response must include X-RateLimit-Remaining: 0."""
        at_cap = [{"allowed": False, "request_count": 1001, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert resp.headers.get("X-RateLimit-Remaining") == "0"

    def test_rate_limit_429_includes_x_ratelimit_limit(self, raw_client):
        """KIN-323: 429 response must include X-RateLimit-Limit with the daily cap."""
        at_cap = [{"allowed": False, "request_count": 1001, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert resp.headers.get("X-RateLimit-Limit") == "1000"

    def test_rate_limit_429_includes_x_ratelimit_reset(self, raw_client):
        """KIN-323: 429 response must include X-RateLimit-Reset (Unix timestamp)."""
        at_cap = [{"allowed": False, "request_count": 1001, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert "X-RateLimit-Reset" in resp.headers
        assert int(resp.headers["X-RateLimit-Reset"]) > 0


# ---------------------------------------------------------------------------
# TestMCPRateLimitAdvanced — KIN-323
# Per-user cap override and UTC midnight counter reset.
# ---------------------------------------------------------------------------


class TestMCPRateLimitAdvanced:
    def test_per_user_cap_override_respected(self, raw_client):
        """A user with daily_cap=500 should 429 when RPC returns allowed=False.

        Per-user cap is stored in mcp_rate_limits.daily_cap (default 1000,
        admin-configurable per db-schema-spec.md §21).
        """
        at_custom_cap = [{"allowed": False, "request_count": 501, "daily_cap": 500}]
        mock_db = _make_db_mock(rate_limit_data=at_custom_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        # Verify custom cap reflected in response
        assert resp.headers.get("X-RateLimit-Limit") == "500"

    def test_counter_resets_at_utc_midnight(self, raw_client):
        """After UTC midnight, RPC returns allowed=True for first request of new day."""
        first_request_new_day = [{"allowed": True, "request_count": 1, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=first_request_new_day)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestMCPContextAssemblyWithRAG — pending KIN-322
# L7 (framework), L8 (project KB RAG), L9 (agent KB RAG) layer assembly.
# ---------------------------------------------------------------------------


class TestMCPContextAssemblyWithRAG:
    """KIN-322: L7 (framework), L8 (project KB RAG), L9 (agent KB RAG) layer assembly.

    The autouse _patch_pipeline_services fixture patches retrieve → [] and
    select_framework → no-match by default. Tests override via monkeypatch.
    """

    @pytest.fixture(autouse=True)
    def _mock_user_key(self, monkeypatch):
        """Provide a fake BYOK key so RAG/framework paths execute."""
        async def _fake_fetch(*args, **kwargs):
            return "sk-test"
        monkeypatch.setattr("app.api.routes.mcp.fetch_user_key_async", _fake_fetch)

    def test_project_scope_assembles_l8(self, raw_client, monkeypatch):
        """project_id + RAG hit: assembled layers should include L8."""
        fake_chunk = MagicMock(
            chunk_id="c1", document_id="d1", document_title="Doc One",
            document_type="pdf", text="RAG chunk content", chunk_index=0,
            section_path=None, page_range=None, similarity_score=0.85,
            token_count=10, scope="project_kb",
        )

        async def _fake_retrieve(*args, **kwargs):
            return [fake_chunk]

        monkeypatch.setattr("app.api.routes.mcp.retrieve", _fake_retrieve)
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "L8" in data["metadata"]["layers_assembled"]
        assert len(data["metadata"]["sources"]) == 1
        assert data["metadata"]["sources"][0]["scope"] == "project_kb"

    def test_agent_scope_assembles_l9(self, raw_client, monkeypatch):
        """agent_id + RAG hit: assembled layers should include L9."""
        fake_chunk = MagicMock(
            chunk_id="c2", document_id="d2", document_title="Agent Doc",
            document_type="md", text="Agent RAG content", chunk_index=0,
            section_path=None, page_range=None, similarity_score=0.78,
            token_count=8, scope="agent_kb",
        )

        async def _fake_retrieve(*args, **kwargs):
            return [fake_chunk]

        monkeypatch.setattr("app.api.routes.mcp.retrieve", _fake_retrieve)
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "L9" in data["metadata"]["layers_assembled"]
        assert len(data["metadata"]["sources"]) == 1
        assert data["metadata"]["sources"][0]["scope"] == "agent_kb"

    def test_agent_scope_assembles_l7_on_framework_match(self, raw_client, monkeypatch):
        """agent_id + framework match: L7 included and matched_framework_id set."""
        fw_match = FrameworkMatch(
            matched_framework_id=str(uuid4()),
            matched_framework_name="SWOT Analysis",
            framework_text="Framework: SWOT Analysis\nDescription: Strategic planning tool.",
        )

        async def _fake_select(*args, **kwargs):
            return fw_match

        monkeypatch.setattr("app.api.routes.mcp.select_framework", _fake_select)
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "L7" in data["metadata"]["layers_assembled"]
        assert data["metadata"]["matched_framework_id"] == fw_match.matched_framework_id
        assert data["metadata"]["matched_framework_name"] == "SWOT Analysis"
        assert "SWOT Analysis" in data["context"]

    def test_agent_scope_omits_l7_on_no_framework_match(self, raw_client):
        """agent_id + no framework match: L7 omitted, matched_framework_id null.

        Uses the default autouse fixture which returns no-match.
        """
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "L7" not in data["metadata"]["layers_assembled"]
        assert data["metadata"]["matched_framework_id"] is None

    def test_rag_miss_returns_empty_sources(self, raw_client):
        """RAG returns no chunks (all below threshold): sources list is empty.

        Uses the default autouse fixture which returns [].
        """
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["sources"] == []


# ---------------------------------------------------------------------------
# TestMCPLastUsedAt — last_used_at update is scheduled on successful auth
# ---------------------------------------------------------------------------


class TestMCPLastUsedAt:
    """KIN-321: after valid token auth, last_used_at is updated via fire-and-forget."""

    def test_last_used_at_update_is_scheduled_on_successful_auth(self, raw_client):
        """
        A successful auth must schedule a last_used_at update on the token row.

        Implementation fires this as run_in_executor (fire-and-forget) — the update
        does not block the response. We verify by confirming the mcp_tokens table was
        accessed at least twice: once for the SELECT lookup, once for the UPDATE.

        A short sleep is required because run_in_executor submits to a thread pool;
        the mock lambda is trivial so 50 ms is far more than needed.
        """
        import time

        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200

        # Give the fire-and-forget thread pool task a moment to execute
        time.sleep(0.05)

        # mcp_tokens accessed once for SELECT (auth lookup) + once for UPDATE (last_used_at)
        mcp_token_calls = [
            c for c in mock_db.table.call_args_list
            if c.args and c.args[0] == "mcp_tokens"
        ]
        assert len(mcp_token_calls) >= 2, (
            f"Expected ≥2 mcp_tokens accesses (SELECT + UPDATE), "
            f"got {len(mcp_token_calls)}. Fire-and-forget update may not have run."
        )

    def test_last_used_at_not_updated_on_failed_auth(self, raw_client):
        """A failed auth (invalid token) must NOT schedule a last_used_at update."""
        import time

        mock_db = _make_db_mock(token_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 401

        time.sleep(0.05)

        # Only the SELECT should have been called; no UPDATE after a failed auth
        mcp_token_calls = [
            c for c in mock_db.table.call_args_list
            if c.args and c.args[0] == "mcp_tokens"
        ]
        assert len(mcp_token_calls) == 1, (
            f"Expected exactly 1 mcp_tokens access (SELECT only) on failed auth, "
            f"got {len(mcp_token_calls)}"
        )


# ---------------------------------------------------------------------------
# TestMCPRateLimitFailOpen — RPC error must not block context assembly
# ---------------------------------------------------------------------------


class TestMCPRateLimitFailOpen:
    """KIN-323: rate limit RPC error must fail open — context assembly proceeds."""

    def test_rate_limit_rpc_error_fails_open(self, raw_client):
        """
        If mcp_check_and_increment_rate_limit raises an unexpected exception,
        the request must proceed (fail-open). A 500 here would block all MCP
        traffic whenever the rate limit DB is degraded.

        Implementation: the except block in _check_rate_limit logs and returns
        without raising, so the endpoint continues.
        """
        def _rpc_side_effect(fn_name, params=None):
            if fn_name == "mcp_check_and_increment_rate_limit":
                raise RuntimeError("DB connection timeout")
            return MagicMock()

        mock_db = _make_db_mock()
        mock_db.rpc.side_effect = _rpc_side_effect

        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        # Must succeed (fail-open) — rate limit error should not block the request
        assert resp.status_code == 200
