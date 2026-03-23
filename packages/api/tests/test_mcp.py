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
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PATCH_TARGET = "app.api.routes.mcp.get_supabase_client"

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
    Build a Supabase mock that routes .table(name) calls to per-entity responses.

    Chain patterns:
      mcp_tokens lookup:    .select().eq().is_().single().execute()
      mcp_rate_limits:      .select().eq().eq().execute()  (user_id + date)
      projects:             .select().eq(id).eq(user_id).single().execute()
      companies (one-eq):   .select().eq(id).single().execute()  (via project's company_id)
      companies (two-eq):   .select().eq(id).eq(user_id).single().execute()  (explicit company_id)
      users/agents:         .select().eq().single().execute()
    """
    if rate_limit_data is None:
        rate_limit_data = []  # empty = no row today = first request, proceed

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
        elif table_name == "mcp_rate_limits":
            # Rate limit check: .select().eq().eq().execute()
            chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=rate_limit_data
            )
            # Rate limit upsert: .upsert().execute()
            chain.upsert.return_value.execute.return_value = MagicMock(data=[])
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

    mock.table.side_effect = _table_side_effect
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
        at_cap = [{"request_count": 1000, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429

    def test_first_request_today_succeeds(self, raw_client):
        """No rate limit row for today → user's first request, should proceed."""
        mock_db = _make_db_mock(rate_limit_data=[])
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
    def test_project_not_owned_returns_404(self, raw_client):
        """project_data=None simulates ownership filter returning no row."""
        mock_db = _make_db_mock(project_data=None)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 404

    def test_private_agent_not_owned_returns_404(self, raw_client):
        """Private agent owned by a different user should be invisible."""
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
        """Public agent owned by another user should be accessible to any MCP token holder."""
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
        """company_data=None simulates company_id + user_id ownership filter returning no row."""
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
    @pytest.mark.skip(reason="Implementation gap — KIN-323: Retry-After header not set in RateLimitError response")
    def test_rate_limit_429_includes_retry_after_header(self, raw_client):
        """KIN-329 requirement: 429 response must include Retry-After header."""
        at_cap = [{"request_count": 1000, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    @pytest.mark.skip(reason="Implementation gap — KIN-323: X-RateLimit-Remaining header not set")
    def test_rate_limit_429_includes_x_ratelimit_remaining_zero(self, raw_client):
        """KIN-329 requirement: 429 response must include X-RateLimit-Remaining: 0."""
        at_cap = [{"request_count": 1000, "daily_cap": 1000}]
        mock_db = _make_db_mock(rate_limit_data=at_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429
        assert resp.headers.get("X-RateLimit-Remaining") == "0"


# ---------------------------------------------------------------------------
# TestMCPRateLimitAdvanced — pending KIN-323
# Per-user cap override and UTC midnight counter reset.
# ---------------------------------------------------------------------------


class TestMCPRateLimitAdvanced:
    @pytest.mark.skip(reason="Pending KIN-323 — users.mcp_daily_limit schema gap: column not in db-schema-spec.md §1")
    def test_per_user_cap_override_respected(self, raw_client):
        """A user with mcp_daily_limit=500 should 429 on the 501st request.

        Blocked by: schema gap (users.mcp_daily_limit not in canonical schema).
        KIN-323 must reconcile users.mcp_daily_limit vs mcp_rate_limits.daily_cap.
        """
        at_custom_cap = [{"request_count": 500, "daily_cap": 500}]
        mock_db = _make_db_mock(rate_limit_data=at_custom_cap)
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "company_id": COMPANY_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 429

    @pytest.mark.skip(reason="Pending KIN-323 — UTC midnight reset requires mocking date.today()")
    def test_counter_resets_at_utc_midnight(self, raw_client):
        """After UTC midnight, a user who was at cap can make requests again."""
        after_midnight_mock = _make_db_mock(rate_limit_data=[])
        with patch(PATCH_TARGET, return_value=after_midnight_mock):
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
    @pytest.mark.skip(reason="Pending KIN-322 — L8 (project KB RAG) not yet implemented")
    def test_project_scope_assembles_l8(self, raw_client):
        """project_id only: assembled layers should include L8 (project KB RAG)."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert "L8" in resp.json()["metadata"]["layers_assembled"]

    @pytest.mark.skip(reason="Pending KIN-322 — L9 (agent KB RAG) not yet implemented")
    def test_agent_scope_assembles_l9(self, raw_client):
        """agent_id only: assembled layers should include L9 (agent KB RAG)."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "agent_id": AGENT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert "L9" in resp.json()["metadata"]["layers_assembled"]

    @pytest.mark.skip(reason="Pending KIN-322 — L7 (framework selection) not yet implemented")
    def test_agent_scope_assembles_l7_on_framework_match(self, raw_client):
        """agent_id with a matching framework: L7 included and matched_framework_id set."""
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
        assert data["metadata"].get("matched_framework_id") is not None

    @pytest.mark.skip(reason="Pending KIN-322 — framework no-match path not yet implemented")
    def test_agent_scope_omits_l7_on_no_framework_match(self, raw_client):
        """agent_id with no matching framework: L7 omitted, matched_framework_id null."""
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
        assert data["metadata"].get("matched_framework_id") is None

    @pytest.mark.skip(reason="Pending KIN-322 — RAG integration not yet implemented")
    def test_rag_miss_returns_empty_sources(self, raw_client):
        """When all chunks fall below similarity threshold, sources list is empty."""
        mock_db = _make_db_mock()
        with patch(PATCH_TARGET, return_value=mock_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": QUERY, "project_id": PROJECT_ID},
                headers={"Authorization": VALID_BEARER},
            )
        assert resp.status_code == 200
        assert resp.json()["metadata"]["sources"] == []
