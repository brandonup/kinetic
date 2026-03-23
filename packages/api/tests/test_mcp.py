"""
Tests for MCP Server — KIN-303.

Scaffolded by Jìan (KIN-303). Activated by a future Jìan Sprint 6 coverage ticket
once Big Head ships Sprint 6 MCP implementations.

Spec ref: docs/specs/mcp-spec.md (KIN-286)
Schema:   docs/db-schema-spec.md §18 (mcp_tokens), §21 (mcp_rate_limits)

Authentication: MCP bearer token (prefix `mcp_`) — NOT the standard user JWT.
  Generate via POST /api/v1/mcp/tokens (JWT auth).
  Use via Authorization: Bearer mcp_<token>.

⚠️  SPEC DISCREPANCY: mcp_tokens.token_hash
  - db-schema-spec.md §18 says: bcrypt hash
  - mcp-spec.md §11 says: SHA-256 hash
  Gilfoyle must resolve this in the Sprint 5 MCP ADR before implementation.
  Update these tests once the ADR locks the approach.

Endpoint: POST /api/v1/mcp/context
  Requires MCP bearer token.
  Scoping params: project_id, agent_id, company_id (at least one required).
"""

import pytest
from .conftest import make_company, make_project

SKIP_REASON = "Blocked — waiting for Sprint 6 MCP implementation (Big Head)"
SKIP_RATE_LIMIT = "Blocked — waiting for Sprint 6 MCP rate limiting (Big Head)"


# ---------------------------------------------------------------------------
# Token management — POST /api/v1/mcp/tokens (JWT auth)
# ---------------------------------------------------------------------------

class TestMcpTokenCreation:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_generate_token_returns_plaintext_once(self, auth_client):
        """POST creates a token and returns the plaintext value once in the response."""
        resp = auth_client.post("/api/v1/mcp/tokens", json={"label": "Claude Desktop"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["token"].startswith("mcp_")
        assert "token_hash" not in data  # hash never returned

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_label_required(self, auth_client):
        resp = auth_client.post("/api/v1/mcp/tokens", json={})
        assert resp.status_code == 422

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_label_max_64_chars(self, auth_client):
        resp = auth_client.post("/api/v1/mcp/tokens", json={"label": "A" * 65})
        assert resp.status_code in (400, 422)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_token_prefix_is_mcp_underscore(self, auth_client):
        resp = auth_client.post("/api/v1/mcp/tokens", json={"label": "Test"})
        assert resp.json()["token"].startswith("mcp_")

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_user_can_have_multiple_tokens(self, auth_client):
        auth_client.post("/api/v1/mcp/tokens", json={"label": "Client A"})
        auth_client.post("/api/v1/mcp/tokens", json={"label": "Client B"})
        resp = auth_client.get("/api/v1/mcp/tokens")
        assert len(resp.json()["tokens"]) == 2

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_token_not_shown_in_list(self, auth_client):
        """After creation, plaintext token must not appear in GET /mcp/tokens response."""
        auth_client.post("/api/v1/mcp/tokens", json={"label": "Cursor"})
        resp = auth_client.get("/api/v1/mcp/tokens")
        for token in resp.json()["tokens"]:
            assert "token" not in token or token.get("token", "").startswith("mcp_••")

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_unauthenticated_token_generation_returns_401(self, client):
        resp = client.post("/api/v1/mcp/tokens", json={"label": "Test"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token management — GET /api/v1/mcp/tokens (JWT auth)
# ---------------------------------------------------------------------------

class TestMcpTokenList:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_list_returns_active_tokens_only(self, auth_client):
        """Revoked tokens must not appear in the list."""
        r1 = auth_client.post("/api/v1/mcp/tokens", json={"label": "Keep"})
        r2 = auth_client.post("/api/v1/mcp/tokens", json={"label": "Revoke"})
        token_id = r2.json()["id"]
        auth_client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")
        resp = auth_client.get("/api/v1/mcp/tokens")
        labels = [t["label"] for t in resp.json()["tokens"]]
        assert "Keep" in labels
        assert "Revoke" not in labels

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_list_includes_label_created_last_used(self, auth_client):
        auth_client.post("/api/v1/mcp/tokens", json={"label": "My Client"})
        resp = auth_client.get("/api/v1/mcp/tokens")
        token = resp.json()["tokens"][0]
        assert "label" in token
        assert "created_at" in token
        assert "last_used_at" in token

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_does_not_return_other_users_tokens(self, auth_client, other_client):
        other_client.post("/api/v1/mcp/tokens", json={"label": "Other"})
        resp = auth_client.get("/api/v1/mcp/tokens")
        assert resp.json()["tokens"] == []


# ---------------------------------------------------------------------------
# Token revocation — PATCH /api/v1/mcp/tokens/{id}/revoke (JWT auth)
# ---------------------------------------------------------------------------

class TestMcpTokenRevocation:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_revoke_sets_revoked_at(self, auth_client):
        r = auth_client.post("/api/v1/mcp/tokens", json={"label": "Revokable"})
        token_id = r.json()["id"]
        resp = auth_client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")
        assert resp.status_code in (200, 204)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_revoked_token_returns_401_on_mcp_context(self, auth_client):
        """After revocation, the bearer token is immediately invalid."""
        r = auth_client.post("/api/v1/mcp/tokens", json={"label": "Temp"})
        token_value = r.json()["token"]
        token_id = r.json()["id"]
        auth_client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/mcp/context",
            json={"query": "test", "company_id": company["id"]},
            headers={"Authorization": f"Bearer {token_value}"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_revoke_other_users_token(self, auth_client, other_client):
        r = other_client.post("/api/v1/mcp/tokens", json={"label": "Other"})
        token_id = r.json()["id"]
        resp = auth_client.patch(f"/api/v1/mcp/tokens/{token_id}/revoke")
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# POST /api/v1/mcp/context — authentication
# ---------------------------------------------------------------------------

class TestMcpContextAuthentication:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_valid_mcp_token_succeeds(self, auth_client):
        r = auth_client.post("/api/v1/mcp/tokens", json={"label": "Test"})
        token = r.json()["token"]
        company = make_company(auth_client)
        resp = auth_client.post(
            "/api/v1/mcp/context",
            json={"query": "What is this company?", "company_id": company["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_auth_header_returns_401(self, client):
        resp = client.post(
            "/api/v1/mcp/context",
            json={"query": "test", "company_id": "00000000-0000-0000-0000-000000000001"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_invalid_token_returns_401(self, auth_client):
        resp = auth_client.post(
            "/api/v1/mcp/context",
            json={"query": "test", "company_id": "00000000-0000-0000-0000-000000000001"},
            headers={"Authorization": "Bearer mcp_invalid_token_value"},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_jwt_auth_does_not_work_on_mcp_context(self, auth_client):
        """MCP context endpoint requires MCP bearer token — not user JWT."""
        company = make_company(auth_client)
        # auth_client uses JWT; attempting to use it on the MCP endpoint must fail
        resp = auth_client.post(
            "/api/v1/mcp/context",
            json={"query": "test", "company_id": company["id"]},
            # No explicit Bearer header — auth_client sends JWT automatically
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_last_used_at_updated_on_successful_request(self, auth_client):
        """After a successful MCP context request, last_used_at on the token row is updated."""
        ...


# ---------------------------------------------------------------------------
# POST /api/v1/mcp/context — scoping table (§4.2)
# ---------------------------------------------------------------------------

class TestMcpContextScopingProjectOnly:
    """project_id only → L1, L2, L3, L8"""

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_project_id_only_assembles_l1_l2_l3_l8(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_layers_assembled_metadata_shows_correct_layers(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_project_not_owned_by_user_returns_403(self, auth_mcp_client, other_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_nonexistent_project_returns_404(self, auth_mcp_client):
        ...


class TestMcpContextScopingProjectPlusAgent:
    """project_id + agent_id → L1, L2, L3, L5, L7, L8, L9 (L6 excluded)"""

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_project_and_agent_assembles_correct_layers(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l6_agent_active_memory_excluded(self, auth_mcp_client):
        """L6 must never appear in MCP context, even when AgentInstance has active memory."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_private_agent_accessible_by_owner_in_mcp(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_private_agent_of_other_user_returns_403(self, auth_mcp_client, other_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_public_agent_accessible_by_any_authenticated_user(self, auth_mcp_client, other_mcp_client):
        ...


class TestMcpContextScopingAgentOnly:
    """agent_id only → L1, L2, L5, L7, L9"""

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_agent_only_assembles_l1_l2_l5_l7_l9(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l8_project_kb_absent_when_no_project(self, auth_mcp_client):
        ...


class TestMcpContextScopingCompanyOnly:
    """company_id only → L1, L2, L3"""

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_company_only_assembles_l1_l2_l3(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_company_not_owned_by_user_returns_403(self, auth_mcp_client, other_client):
        ...


class TestMcpContextScopingNoScope:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_scope_returns_400_missing_scope(self, auth_mcp_client):
        resp = auth_mcp_client.post("/api/v1/mcp/context", json={"query": "test"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "missing_scope"

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_company_id_redundant_with_project_id_accepted(self, auth_mcp_client):
        """project_id + company_id: company_id is ignored, same as project_id only."""
        ...


# ---------------------------------------------------------------------------
# POST /api/v1/mcp/context — response structure
# ---------------------------------------------------------------------------

class TestMcpContextResponse:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_response_includes_context_string(self, auth_mcp_client):
        """Response must include 'context' field — the assembled string ready to prepend."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_response_includes_metadata(self, auth_mcp_client):
        """Response must include 'metadata' with layers_assembled, sources, and token_count_estimate."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_sources_includes_rag_citations(self, auth_mcp_client):
        """When KB chunks are injected, metadata.sources lists document_id, chunk_index, similarity_score."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_matched_framework_id_set_when_framework_matched(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_matched_framework_id_null_when_no_match(self, auth_mcp_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_platform_key_used_for_rag_embedding_not_byok(self, auth_mcp_client):
        """MCP pipeline uses platform-owned embedding key — BYOK not required."""
        ...


# ---------------------------------------------------------------------------
# Rate limiting — §7
# ---------------------------------------------------------------------------

class TestMcpRateLimiting:
    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_429_when_daily_cap_exceeded(self, auth_mcp_client):
        """After 1,000 requests in a calendar day, further requests return 429."""
        ...

    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_429_response_includes_required_headers(self, auth_mcp_client):
        """429 response must include Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset."""
        ...

    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_429_body_includes_reset_at(self, auth_mcp_client):
        """429 body: { error: 'rate_limit_exceeded', limit: 1000, reset_at: <UTC midnight> }"""
        ...

    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_rate_limit_resets_at_utc_midnight(self, auth_mcp_client):
        """Counter resets at UTC midnight — requests after midnight should succeed again."""
        ...

    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_rate_limit_is_per_user_not_per_token(self, auth_mcp_client):
        """Multiple tokens belonging to the same user share the same daily cap."""
        ...

    @pytest.mark.skip(reason=SKIP_RATE_LIMIT)
    def test_admin_configurable_cap(self, auth_mcp_client, admin_client):
        """Admin can set a per-user override cap. User sees the override limit, not default 1000."""
        ...


# ---------------------------------------------------------------------------
# Error response shape
# ---------------------------------------------------------------------------

class TestMcpErrorShape:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_all_errors_return_json_with_error_and_message(self, auth_mcp_client):
        """Every error response must have { error: string, message: string } body."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_400_invalid_scope_params_on_bad_uuid(self, auth_mcp_client):
        resp = auth_mcp_client.post(
            "/api/v1/mcp/context",
            json={"query": "test", "project_id": "not-a-uuid"},
        )
        assert resp.status_code in (400, 422)
