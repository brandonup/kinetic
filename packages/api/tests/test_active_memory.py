"""
Tests for Active Memory — KIN-298.

Scaffolded by Jìan (KIN-298). Activated by a future Jìan Sprint 5 coverage ticket
once Big Head and Dinesh ship Sprint 5 implementations.

Spec ref: docs/specs/active-memory-spec.md (KIN-268)
Schema:   docs/db-schema-spec.md §16 (active_memory_entries), §17 (memory_proposals)

Token counting: character-proxy, ceil(char_length(content) / 4)
  Project cap:       1,000 tokens  (ACTIVE_MEMORY_CAP_PROJECT)
  Agent-instance cap:  500 tokens  (ACTIVE_MEMORY_CAP_AGENT)
"""

import pytest
from .conftest import make_company, make_project

SKIP_REASON = "Blocked — waiting for Sprint 5 Active Memory implementation (Big Head + Dinesh)"

# Token-counting constants (matches spec)
ACTIVE_MEMORY_CAP_PROJECT = 1000
ACTIVE_MEMORY_CAP_AGENT = 500

# Helpers: ~1 token ≈ 4 chars
def content_of_approx_tokens(n_tokens: int) -> str:
    return "A " * (n_tokens * 2)  # 2 chars per "A " ≈ 0.5 tokens; so 2*n gives ~n tokens


# ---------------------------------------------------------------------------
# GET /api/v1/active-memory — list entries for a scope
# ---------------------------------------------------------------------------

class TestListActiveMemory:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_requires_exactly_one_scope_param(self, auth_client):
        """Providing neither or both scope params returns 400."""
        resp = auth_client.get("/api/v1/active-memory")
        assert resp.status_code == 400

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_both_scope_params_returns_400(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.get(
            f"/api/v1/active-memory?project_id={project['id']}&agent_instance_id=some-id"
        )
        assert resp.status_code == 400

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_list_project_entries(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.get(f"/api/v1/active-memory?project_id={project['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "token_usage" in data

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_token_usage_reported_correctly(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        content = "A" * 40  # 40 chars = 10 tokens (ceil(40/4))
        auth_client.post(
            "/api/v1/active-memory",
            json={"content": content, "project_id": project["id"]},
        )
        resp = auth_client.get(f"/api/v1/active-memory?project_id={project['id']}")
        usage = resp.json()["token_usage"]
        assert usage["current_tokens"] == 10
        assert usage["cap_tokens"] == ACTIVE_MEMORY_CAP_PROJECT

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_does_not_return_other_users_entries(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        resp = auth_client.get(f"/api/v1/active-memory?project_id={other_project['id']}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/active-memory — create entry
# ---------------------------------------------------------------------------

class TestCreateActiveMemoryEntry:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_project_entry(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "User prefers short answers.", "project_id": project["id"]},
        )
        assert resp.status_code == 201
        assert resp.json()["content"] == "User prefers short answers."

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_create_agent_instance_entry(self, auth_client, other_client):
        """Entry scoped to an AgentInstance."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_polymorphic_constraint_both_scope_params_rejected(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={
                "content": "Test.",
                "project_id": project["id"],
                "agent_instance_id": "some-id",
            },
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_empty_content_returns_400(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "", "project_id": project["id"]},
        )
        assert resp.status_code == 400

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_source_conversation_id_optional(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={
                "content": "User authored.",
                "project_id": project["id"],
                "source_conversation_id": None,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["source_conversation_id"] is None

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_other_users_project_returns_403(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "Hijack.", "project_id": other_project["id"]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Token cap enforcement
# ---------------------------------------------------------------------------

class TestTokenCapEnforcement:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_project_cap_1000_tokens_enforced(self, auth_client):
        """Writing an entry that would push total past 1,000 tokens returns 422."""
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        # Fill to ~990 tokens (3960 chars)
        big_content = "A" * 3960
        auth_client.post(
            "/api/v1/active-memory",
            json={"content": big_content, "project_id": project["id"]},
        )
        # Attempt to add more
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "A" * 200, "project_id": project["id"]},
        )
        assert resp.status_code == 422
        error = resp.json()["error"]
        assert error == "memory_full" or "memory_full" in str(resp.json())

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_422_response_includes_current_and_cap_tokens(self, auth_client):
        """memory_full response must include current_tokens and cap_tokens."""
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        auth_client.post(
            "/api/v1/active-memory",
            json={"content": "A" * 3960, "project_id": project["id"]},
        )
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "A" * 200, "project_id": project["id"]},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "current_tokens" in str(body)
        assert "cap_tokens" in str(body)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_agent_instance_cap_500_tokens_enforced(self, auth_client, other_client):
        """Agent instance cap is 500 tokens — half the project cap."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_token_count_uses_char_proxy_ceil_div_4(self, auth_client):
        """Token count = ceil(char_length(content) / 4)."""
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        resp = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "A" * 5, "project_id": project["id"]},  # ceil(5/4) = 2 tokens
        )
        assert resp.status_code == 201
        usage = auth_client.get(
            f"/api/v1/active-memory?project_id={project['id']}"
        ).json()["token_usage"]
        assert usage["current_tokens"] == 2  # ceil(5/4) = 2

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_edit_enforces_cap_on_new_content_size(self, auth_client):
        """PATCH: cap check uses (total - old_tokens + new_tokens) <= cap."""
        ...


# ---------------------------------------------------------------------------
# PATCH /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------

class TestUpdateActiveMemoryEntry:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_update_content(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        entry = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "Original.", "project_id": project["id"]},
        ).json()
        resp = auth_client.patch(
            f"/api/v1/active-memory/{entry['id']}",
            json={"content": "Updated."},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Updated."

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_update_other_users_entry(self, auth_client, other_client):
        other_company = make_company(other_client)
        other_project = make_project(other_client, other_company["id"])
        entry = other_client.post(
            "/api/v1/active-memory",
            json={"content": "Mine.", "project_id": other_project["id"]},
        ).json()
        resp = auth_client.patch(
            f"/api/v1/active-memory/{entry['id']}",
            json={"content": "Hijacked."},
        )
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# DELETE /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------

class TestDeleteActiveMemoryEntry:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_hard_delete_returns_204(self, auth_client):
        company = make_company(auth_client)
        project = make_project(auth_client, company["id"])
        entry = auth_client.post(
            "/api/v1/active-memory",
            json={"content": "Delete me.", "project_id": project["id"]},
        ).json()
        resp = auth_client.delete(f"/api/v1/active-memory/{entry['id']}")
        assert resp.status_code == 204

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_delete_frees_token_budget(self, auth_client):
        """After deleting an entry, token_usage.current_tokens decreases."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_delete_other_users_entry(self, auth_client, other_client):
        ...


# ---------------------------------------------------------------------------
# Proposal queue — GET /api/v1/active-memory/proposals
# ---------------------------------------------------------------------------

class TestProposalQueue:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_list_pending_proposals_for_project(self, auth_client):
        """GET /proposals?project_id=X returns pending proposals for that project."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_only_pending_proposals_returned_by_default(self, auth_client):
        """Accepted and rejected proposals do not appear in the list endpoint."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_proposal_includes_trigger_type(self, auth_client):
        """Each proposal row includes trigger_type: conversation_end or periodic."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_periodic_trigger_deduplication(self, auth_client):
        """Duplicate proposed_content (case-insensitive) for same scope not re-queued."""
        ...


# ---------------------------------------------------------------------------
# Proposal review — POST /api/v1/active-memory/proposals/review
# ---------------------------------------------------------------------------

class TestProposalReview:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_accept_proposal_creates_entry(self, auth_client):
        """Accepting a proposal inserts a row into active_memory_entries."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_accept_marks_proposal_approved(self, auth_client):
        """After accept, proposal.status = 'approved'."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_reject_marks_proposal_rejected_no_entry_created(self, auth_client):
        """Rejecting a proposal sets status='rejected' and does not create an entry."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_accept_rejected_when_cap_exceeded(self, auth_client):
        """Accept returns 'skipped_cap_exceeded' when memory is full."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_bulk_review_processes_in_order(self, auth_client):
        """Multiple decisions processed in the order listed in the request."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_review_response_includes_token_usage(self, auth_client):
        """Review response includes token_usage.current_tokens and cap_tokens."""
        ...


# ---------------------------------------------------------------------------
# Triple-trigger write path
# ---------------------------------------------------------------------------

class TestWriteTriggers:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_1_user_initiated_direct_write(self, auth_client):
        """User-initiated save via POST /api/v1/active-memory writes immediately — no proposal queue."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_2_conversation_end_creates_proposals(self, auth_client):
        """Navigating away from a conversation (or explicit end) queues proposals — no auto-write."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_trigger_3_periodic_at_every_10th_message(self, auth_client):
        """Proposals generated and queued at message count = 10, 20, 30..."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_all_triggers_require_user_confirmation(self, auth_client):
        """Triggers 2 and 3 queue proposals; only the user action (review/accept) writes to entries."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_failure_on_trigger_2_skips_silently(self, auth_client):
        """If BYOK call fails on conversation-end trigger, no error surfaces — proposals just not generated."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_failure_on_trigger_3_skips_silently(self, auth_client):
        """Same silent fail policy for periodic trigger."""
        ...


# ---------------------------------------------------------------------------
# Company-level conversations excluded
# ---------------------------------------------------------------------------

class TestCompanyConversationExclusion:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_cannot_save_to_memory_in_company_conversation(self, auth_client):
        """POST /api/v1/active-memory returns 400 when source conversation has no project_id and no agent."""
        ...


# ---------------------------------------------------------------------------
# Context assembly integration (Sprint 5 activation of L4 and L6 stubs)
# ---------------------------------------------------------------------------

class TestContextAssemblyIntegration:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l4_project_active_memory_injected_in_context(self, auth_client):
        """With entries present, L4 appears in assembled context for project conversations."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l4_absent_when_no_entries(self, auth_client):
        """L4 is omitted entirely from context when project has no active memory entries."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l4_uses_standard_header_format(self, auth_client):
        """L4 injected as '## What I know about this project\\n- [entry]\\n...'"""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_l6_agent_instance_memory_injected_in_context(self, auth_client):
        """With agent active and instance memory set, L6 appears in context."""
        ...
