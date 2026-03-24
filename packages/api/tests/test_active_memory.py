"""
Tests for Active Memory CRUD endpoints — KIN-308.

Spec: docs/specs/active-memory-spec.md
Schema: docs/db-schema-spec.md §16 (active_memory_entries), §17 (memory_proposals)

All tests are unit-tier: `get_supabase_client` is patched; no real DB.
Token counting: ceil(len(content) / 4).
Caps: project=1000, agent_instance=500 tokens.
"""

import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Constants shared across test classes
# ---------------------------------------------------------------------------

PROJECT_ID = str(uuid4())
AGENT_INSTANCE_ID = str(uuid4())
ENTRY_ID = str(uuid4())
CONVERSATION_ID = str(uuid4())

PATCH_TARGET = "app.api.routes.active_memory.get_supabase_client"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    entry_id: str = None,
    content: str = "test memory entry",
    project_id: str = PROJECT_ID,
    agent_instance_id: str = None,
    source_conversation_id: str = None,
) -> dict:
    """Build a mock active_memory_entries row."""
    return {
        "id": entry_id or str(uuid4()),
        "user_id": str(uuid4()),
        "project_id": project_id,
        "agent_instance_id": agent_instance_id,
        "content": content,
        "source_conversation_id": source_conversation_id,
        "created_at": "2026-03-23T10:00:00+00:00",
        "updated_at": "2026-03-23T10:00:00+00:00",
    }


def _make_proposal(
    proposal_id: str = None,
    proposed_content: str = "a proposed memory entry",
    project_id: str = PROJECT_ID,
    agent_instance_id: str = None,
    status: str = "pending",
    trigger_type: str = "periodic",
) -> dict:
    return {
        "id": proposal_id or str(uuid4()),
        "user_id": str(uuid4()),
        "conversation_id": CONVERSATION_ID,
        "project_id": project_id,
        "agent_instance_id": agent_instance_id,
        "proposed_content": proposed_content,
        "status": status,
        "trigger_type": trigger_type,
        "created_at": "2026-03-23T10:00:00+00:00",
        "reviewed_at": None,
    }


def _mock_supabase_for_ownership(mock_client, *, project_found: bool = True, agent_found: bool = True):
    """
    Configure mock to return data for project/agent_instance ownership checks.
    The ownership check queries: .table(...).select("id").eq(...).eq(...).single().execute()
    """
    project_data = {"id": PROJECT_ID} if project_found else None
    agent_data = {"id": AGENT_INSTANCE_ID} if agent_found else None

    def _side_effect(table_name):
        chain = MagicMock()
        if table_name == "projects":
            chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=project_data)
        elif table_name == "agent_instances":
            chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=agent_data)
        else:
            chain.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])
            chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            chain.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            chain.insert.return_value.execute.return_value = MagicMock(data=[])
            chain.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            chain.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return chain

    mock_client.table.side_effect = _side_effect


# ---------------------------------------------------------------------------
# Task 2a: GET /api/v1/active-memory — list entries
# ---------------------------------------------------------------------------


class TestListEntries:
    def _setup_list_mock(self, mock_client, entries, *, project_found=True):
        """Configure mock for list endpoint: ownership check + entries query."""
        entries_chain = MagicMock()
        entries_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=entries)

        ownership_chain = MagicMock()
        data = {"id": PROJECT_ID} if project_found else None
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=data)

        call_count = [0]

        def _table_side_effect(table_name):
            if table_name == "projects":
                return ownership_chain
            return entries_chain

        mock_client.table.side_effect = _table_side_effect

    def test_list_by_project_id(self, client):
        entry = _make_entry()
        mock_client = MagicMock()
        self._setup_list_mock(mock_client, [entry])
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory?project_id={PROJECT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert "entries" in body
        assert "token_usage" in body
        assert body["token_usage"]["cap_tokens"] == 1000

    def test_list_by_agent_instance_id(self, client):
        entry = _make_entry(project_id=None, agent_instance_id=AGENT_INSTANCE_ID)
        mock_client = MagicMock()

        agent_chain = MagicMock()
        agent_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"id": AGENT_INSTANCE_ID})

        entries_chain = MagicMock()
        entries_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[entry])

        def _table(name):
            if name == "agent_instances":
                return agent_chain
            return entries_chain

        mock_client.table.side_effect = _table
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory?agent_instance_id={AGENT_INSTANCE_ID}")
        assert resp.status_code == 200
        assert resp.json()["token_usage"]["cap_tokens"] == 500

    def test_list_neither_scope_400(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            resp = client.get("/api/v1/active-memory")
        assert resp.status_code == 400

    def test_list_both_scopes_400(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            resp = client.get(
                f"/api/v1/active-memory?project_id={PROJECT_ID}&agent_instance_id={AGENT_INSTANCE_ID}"
            )
        assert resp.status_code == 400

    def test_list_wrong_user_403(self, client):
        mock_client = MagicMock()
        # Ownership check returns None (project not found / not owned)
        ownership_chain = MagicMock()
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
        mock_client.table.return_value = ownership_chain
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory?project_id={PROJECT_ID}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Task 2b: POST /api/v1/active-memory — create entry
# ---------------------------------------------------------------------------


class TestCreateEntry:
    def _setup_create_mock(self, mock_client, *, existing_tokens=0, cap=1000, new_entry=None, project_found=True):
        """
        Mock for POST /api/v1/active-memory.
        existing_tokens: controls sum returned from existing entries select.
        """
        # Build fake existing entries whose total token count equals existing_tokens.
        # Use one entry of content length = existing_tokens * 4 (so ceil(4n/4) == n).
        if existing_tokens > 0:
            existing_entries = [{"content": "x" * (existing_tokens * 4)}]
        else:
            existing_entries = []

        new_row = new_entry or _make_entry()

        ownership_chain = MagicMock()
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"id": PROJECT_ID} if project_found else None)

        entries_select_chain = MagicMock()
        entries_select_chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=existing_entries)

        entries_insert_chain = MagicMock()
        entries_insert_chain.insert.return_value.execute.return_value = MagicMock(data=[new_row])

        call_idx = [0]

        def _table(name):
            if name == "projects":
                return ownership_chain
            # active_memory_entries: first call is select (token count), second is insert
            call_idx[0] += 1
            if call_idx[0] == 1:
                return entries_select_chain
            return entries_insert_chain

        mock_client.table.side_effect = _table

    def test_create_project_entry_201(self, client):
        mock_client = MagicMock()
        self._setup_create_mock(mock_client, existing_tokens=0)
        payload = {"content": "Prefers bullet points", "project_id": PROJECT_ID}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 201
        assert "id" in resp.json()

    def test_create_empty_content_422(self, client):
        # Pydantic body validation raises ValueError → FastAPI returns 422 (Unprocessable Entity).
        # Spec says 400, but FastAPI/Pydantic request body validation is conventionally 422.
        # This matches the codebase pattern (see test_companies.py lines 73, 80).
        with patch(PATCH_TARGET, return_value=MagicMock()):
            resp = client.post("/api/v1/active-memory", json={"content": "", "project_id": PROJECT_ID})
        assert resp.status_code == 422

    def test_create_cap_exceeded_422(self, client):
        mock_client = MagicMock()
        # existing = 990 tokens, new content = 100 chars = 25 tokens → 1015 > 1000
        self._setup_create_mock(mock_client, existing_tokens=990)
        payload = {"content": "x" * 100, "project_id": PROJECT_ID}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "MEMORY_CAP_EXCEEDED"

    def test_create_exactly_at_cap_passes(self, client):
        """total == cap exactly → write succeeds."""
        mock_client = MagicMock()
        # existing = 975, new content = 100 chars = 25 tokens → 1000 == cap → OK
        self._setup_create_mock(mock_client, existing_tokens=975)
        payload = {"content": "x" * 100, "project_id": PROJECT_ID}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 201

    def test_create_one_over_cap_fails_422(self, client):
        """total == cap + 1 → rejected."""
        mock_client = MagicMock()
        # existing = 976, new content = 100 chars = 25 tokens → 1001 > 1000
        self._setup_create_mock(mock_client, existing_tokens=976)
        payload = {"content": "x" * 100, "project_id": PROJECT_ID}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Task 2c: PATCH /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------


class TestUpdateEntry:
    def _setup_update_mock(self, mock_client, *, old_content="x" * 40, existing_tokens=10, updated_entry=None, entry_found=True):
        """
        Mock for PATCH. First call: fetch existing entry. Second: select all for cap calc. Third: update.
        existing_tokens includes old entry token count.
        """
        old_entry = _make_entry(entry_id=ENTRY_ID, content=old_content)

        # Existing entries for token counting (including the old entry)
        existing_entries = [{"content": "x" * (existing_tokens * 4)}]

        updated = updated_entry or {**old_entry, "content": "updated content"}

        call_idx = [0]

        def _table(name):
            call_idx[0] += 1
            m = MagicMock()
            if call_idx[0] == 1:
                # Fetch entry by id + user_id
                m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=old_entry if entry_found else None
                )
            elif call_idx[0] == 2:
                # Select all entries for token count
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=existing_entries)
            else:
                # Update
                m.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated])
            return m

        mock_client.table.side_effect = _table

    def test_update_content_200(self, client):
        mock_client = MagicMock()
        self._setup_update_mock(mock_client, old_content="x" * 40, existing_tokens=10)
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.patch(f"/api/v1/active-memory/{ENTRY_ID}", json={"content": "new content"})
        assert resp.status_code == 200

    def test_update_cap_exceeded_422(self, client):
        """Expanding content that would push total over cap → 422."""
        mock_client = MagicMock()
        # existing_tokens = 990 (all entries combined including old).
        # old_content = 100 chars = 25 tokens.
        # new_content = 1000 chars = 250 tokens. delta = +225 → 990 - 25 + 250 = 1215 > 1000
        self._setup_update_mock(mock_client, old_content="x" * 100, existing_tokens=990)
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.patch(f"/api/v1/active-memory/{ENTRY_ID}", json={"content": "x" * 1000})
        assert resp.status_code == 422

    def test_update_not_found_404(self, client):
        mock_client = MagicMock()
        self._setup_update_mock(mock_client, entry_found=False)
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.patch(f"/api/v1/active-memory/{ENTRY_ID}", json={"content": "anything"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 2d: DELETE /api/v1/active-memory/{entry_id}
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    def test_delete_204(self, client):
        mock_client = MagicMock()
        delete_chain = MagicMock()
        delete_chain.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": ENTRY_ID}]
        )
        mock_client.table.return_value = delete_chain
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.delete(f"/api/v1/active-memory/{ENTRY_ID}")
        assert resp.status_code == 204

    def test_delete_not_found_404(self, client):
        mock_client = MagicMock()
        delete_chain = MagicMock()
        delete_chain.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_client.table.return_value = delete_chain
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.delete(f"/api/v1/active-memory/{ENTRY_ID}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Task 3: GET /api/v1/active-memory/proposals
# ---------------------------------------------------------------------------


class TestListProposals:
    def _setup_proposals_mock(self, mock_client, proposals, *, project_found=True):
        ownership_chain = MagicMock()
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": PROJECT_ID} if project_found else None
        )

        proposals_chain = MagicMock()
        proposals_chain.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proposals)

        def _table(name):
            if name == "projects":
                return ownership_chain
            return proposals_chain

        mock_client.table.side_effect = _table

    def test_list_pending_by_project(self, client):
        proposals = [_make_proposal()]
        mock_client = MagicMock()
        self._setup_proposals_mock(mock_client, proposals)
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory/proposals?project_id={PROJECT_ID}")
        assert resp.status_code == 200
        assert len(resp.json()["proposals"]) == 1

    def test_list_pending_by_agent(self, client):
        proposals = [_make_proposal(project_id=None, agent_instance_id=AGENT_INSTANCE_ID)]
        mock_client = MagicMock()

        agent_chain = MagicMock()
        agent_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"id": AGENT_INSTANCE_ID})

        proposals_chain = MagicMock()
        proposals_chain.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=proposals)

        def _table(name):
            if name == "agent_instances":
                return agent_chain
            return proposals_chain

        mock_client.table.side_effect = _table
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory/proposals?agent_instance_id={AGENT_INSTANCE_ID}")
        assert resp.status_code == 200

    def test_list_no_scope_400(self, client):
        with patch(PATCH_TARGET, return_value=MagicMock()):
            resp = client.get("/api/v1/active-memory/proposals")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Task 3b: POST /api/v1/active-memory/proposals/review
# ---------------------------------------------------------------------------


PROPOSAL_ID_1 = str(uuid4())
PROPOSAL_ID_2 = str(uuid4())


class TestReviewProposals:
    def _build_review_mock(self, mock_client, *, proposals_by_id, existing_tokens=0, insert_success=True):
        """
        proposals_by_id: dict of proposal_id → proposal row.
        existing_tokens: current token total for the scope.
        """
        existing_entries = [{"content": "x" * (existing_tokens * 4)}] if existing_tokens > 0 else []
        inserted_entry = _make_entry()

        call_log = []

        def _table(name):
            call_log.append(name)
            m = MagicMock()
            if name == "memory_proposals":
                # Fetch by id + user_id
                def _proposal_chain_eq1(col, val=None, **kw):
                    inner = MagicMock()
                    def _eq2(col2, val2=None, **kw2):
                        inner2 = MagicMock()
                        inner2.single.return_value.execute.return_value = MagicMock(
                            data=proposals_by_id.get(val)
                        )
                        inner2.execute.return_value = MagicMock(data=None)
                        return inner2
                    inner.eq = _eq2
                    return inner
                m.select.return_value.eq = _proposal_chain_eq1

                # Update (status change)
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

            elif name == "active_memory_entries":
                # Token count select
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=existing_entries)
                # Insert
                m.insert.return_value.execute.return_value = MagicMock(data=[inserted_entry] if insert_success else [])
            return m

        mock_client.table.side_effect = _table

    def test_accept_proposal_inserts_entry(self, client):
        proposal = _make_proposal(proposal_id=PROPOSAL_ID_1, proposed_content="Short content")
        mock_client = MagicMock()
        self._build_review_mock(mock_client, proposals_by_id={PROPOSAL_ID_1: proposal})
        payload = {"decisions": [{"proposal_id": PROPOSAL_ID_1, "action": "accept"}]}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory/proposals/review", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        results = body["results"]
        assert results[0]["action"] == "accepted"
        assert "token_usage" in body

    def test_reject_proposal_no_entry(self, client):
        proposal = _make_proposal(proposal_id=PROPOSAL_ID_1)
        mock_client = MagicMock()
        self._build_review_mock(mock_client, proposals_by_id={PROPOSAL_ID_1: proposal})
        payload = {"decisions": [{"proposal_id": PROPOSAL_ID_1, "action": "reject"}]}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory/proposals/review", json=payload)
        assert resp.status_code == 200
        assert resp.json()["results"][0]["action"] == "rejected"

    def test_accept_cap_exceeded_skipped(self, client):
        # proposed_content = 100 chars = 25 tokens; existing = 990 → would exceed 1000
        content = "x" * 100
        proposal = _make_proposal(proposal_id=PROPOSAL_ID_1, proposed_content=content)
        mock_client = MagicMock()
        self._build_review_mock(mock_client, proposals_by_id={PROPOSAL_ID_1: proposal}, existing_tokens=990)
        payload = {"decisions": [{"proposal_id": PROPOSAL_ID_1, "action": "accept"}]}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory/proposals/review", json=payload)
        assert resp.status_code == 200
        assert resp.json()["results"][0]["action"] == "skipped_cap_exceeded"

    def test_mixed_decisions(self, client):
        p1 = _make_proposal(proposal_id=PROPOSAL_ID_1, proposed_content="short")
        p2 = _make_proposal(proposal_id=PROPOSAL_ID_2, proposed_content="also short")
        mock_client = MagicMock()
        self._build_review_mock(mock_client, proposals_by_id={PROPOSAL_ID_1: p1, PROPOSAL_ID_2: p2})
        payload = {
            "decisions": [
                {"proposal_id": PROPOSAL_ID_1, "action": "accept"},
                {"proposal_id": PROPOSAL_ID_2, "action": "reject"},
            ]
        }
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory/proposals/review", json=payload)
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        actions = {r["proposal_id"]: r["action"] for r in results}
        assert actions[PROPOSAL_ID_1] == "accepted"
        assert actions[PROPOSAL_ID_2] == "rejected"


# ---------------------------------------------------------------------------
# Task 4: GET /api/v1/admin/active-memory
# ---------------------------------------------------------------------------


OTHER_USER_ID = str(uuid4())


class TestAdminListEntries:
    def test_admin_can_read_any_user(self, admin_client):
        entry = _make_entry()
        mock_client = MagicMock()
        entries_chain = MagicMock()
        entries_chain.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[entry])
        mock_client.table.return_value = entries_chain
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = admin_client.get(
                f"/api/v1/admin/active-memory?user_id={OTHER_USER_ID}&project_id={PROJECT_ID}"
            )
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_non_admin_403(self, client):
        """Regular user cannot access admin endpoint — require_admin raises AuthorizationError."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error():
            raise AuthorizationError("Admin access required")

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            with patch(PATCH_TARGET, return_value=MagicMock()):
                resp = client.get(
                    f"/api/v1/admin/active-memory?user_id={OTHER_USER_ID}&project_id={PROJECT_ID}"
                )
        finally:
            del app.dependency_overrides[require_admin]
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Entry structure — field assertions (KIN-308)
# ---------------------------------------------------------------------------


class TestEntryStructure:
    """Verify response shape and field constraints for active_memory_entries."""

    def _setup_create(self, mock_client, *, new_entry):
        """Minimal create mock: no existing entries, insert returns new_entry."""
        ownership_chain = MagicMock()
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": PROJECT_ID}
        )
        select_chain = MagicMock()
        select_chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        insert_chain = MagicMock()
        insert_chain.insert.return_value.execute.return_value = MagicMock(data=[new_entry])

        call_idx = [0]

        def _table(name):
            if name == "projects":
                return ownership_chain
            call_idx[0] += 1
            return select_chain if call_idx[0] == 1 else insert_chain

        mock_client.table.side_effect = _table

    def test_create_entry_response_includes_required_fields(self, client):
        """POST response includes id, content, created_at, and source_conversation_id."""
        new_entry = _make_entry(
            content="Remember: prefers bullet points",
            source_conversation_id=CONVERSATION_ID,
        )
        mock_client = MagicMock()
        self._setup_create(mock_client, new_entry=new_entry)
        payload = {
            "content": "Remember: prefers bullet points",
            "project_id": PROJECT_ID,
            "source_conversation_id": CONVERSATION_ID,
        }
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "content" in body
        assert "created_at" in body
        assert "source_conversation_id" in body
        assert body["source_conversation_id"] == CONVERSATION_ID

    def test_source_conversation_id_nullable_for_user_entries(self, client):
        """User-authored entries may omit source_conversation_id — null in response."""
        new_entry = _make_entry(content="User authored entry", source_conversation_id=None)
        mock_client = MagicMock()
        self._setup_create(mock_client, new_entry=new_entry)
        payload = {"content": "User authored entry", "project_id": PROJECT_ID}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory", json=payload)
        assert resp.status_code == 201
        assert resp.json()["source_conversation_id"] is None

    def test_list_entries_ordered_by_created_at_desc(self, client):
        """GET query applies ORDER BY created_at DESC (not ASC, not unordered)."""
        entries_chain = MagicMock()
        entries_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )
        ownership_chain = MagicMock()
        ownership_chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": PROJECT_ID}
        )

        mock_client = MagicMock()

        def _table(name):
            return ownership_chain if name == "projects" else entries_chain

        mock_client.table.side_effect = _table

        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.get(f"/api/v1/active-memory?project_id={PROJECT_ID}")

        assert resp.status_code == 200
        entries_chain.select.return_value.eq.return_value.eq.return_value.order.assert_called_once_with(
            "created_at", desc=True
        )


# ---------------------------------------------------------------------------
# Proposal accept — source_conversation_id propagation (KIN-308)
# ---------------------------------------------------------------------------


class TestProposalSourceConversation:
    def test_accepted_proposal_entry_carries_source_conversation_id(self, client):
        """
        When a proposal is accepted, the inserted active_memory_entries row has
        source_conversation_id set from the proposal's conversation_id.
        """
        proposal = _make_proposal(proposal_id=PROPOSAL_ID_1, proposed_content="Short content")

        inserted_rows: list = []

        def _table(name):
            m = MagicMock()
            if name == "memory_proposals":
                m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=proposal
                )
                m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
            elif name == "active_memory_entries":
                # Token count: no existing entries
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

                def _capture_insert(row):
                    inserted_rows.append(row)
                    inner = MagicMock()
                    inner.execute.return_value = MagicMock(data=[_make_entry()])
                    return inner

                m.insert.side_effect = _capture_insert
            return m

        mock_client = MagicMock()
        mock_client.table.side_effect = _table

        payload = {"decisions": [{"proposal_id": PROPOSAL_ID_1, "action": "accept"}]}
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/api/v1/active-memory/proposals/review", json=payload)

        assert resp.status_code == 200
        assert len(inserted_rows) == 1, "Expected exactly one entry inserted"
        assert inserted_rows[0]["source_conversation_id"] == CONVERSATION_ID


# ---------------------------------------------------------------------------
# Periodic proposals — KIN-306
# ---------------------------------------------------------------------------


def _make_messages_db(mock_client, *, existing_message_count=9, pending_proposals=None):
    """
    Wire a mock Supabase client for the store_message endpoint DB calls.

    - conversations → ownership check (always passes)
    - messages.select → existing_message_count rows (controls sequence + trigger)
    - messages.insert → returns stored row
    - memory_proposals.select → pending_proposals list (for debounce check)
    """
    pending_proposals = pending_proposals or []
    stored_message = {
        "id": str(uuid4()),
        "conversation_id": CONVERSATION_ID,
        "role": "user",
        "content": "Hello",
        "sequence": existing_message_count,
        "created_at": "2026-03-23T10:00:00+00:00",
    }

    def _table(name):
        m = MagicMock()
        if name == "conversations":
            # Chain: .select().eq().eq().is_().single().execute()
            m.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": CONVERSATION_ID, "project_id": PROJECT_ID}
            )
        elif name == "messages":
            # Count query: select("id").eq(...)
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": str(uuid4())} for _ in range(existing_message_count)]
            )
            # Insert
            m.insert.return_value.execute.return_value = MagicMock(data=[stored_message])
        elif name == "memory_proposals":
            # Debounce check: select("id").eq(...).eq(...).execute()
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": str(uuid4())} for _ in pending_proposals]
            )
        return m

    mock_client.table.side_effect = _table


class TestPeriodicProposals:
    """
    Tests for the periodic background proposal trigger (every 10 messages).
    Route: POST /api/v1/conversations/{id}/messages (message-count side-effect)
    Implementation ticket: KIN-306
    """

    def test_tenth_message_triggers_proposal_job(self, client):
        """
        After storing the 10th message (existing_count=9 → new_count=10),
        TaskDispatcher.dispatch() is called once with the correct conversation_id.
        """
        mock_client = MagicMock()
        _make_messages_db(mock_client, existing_message_count=9)  # new_count = 10

        mock_dispatcher = MagicMock()
        payload = {"role": "user", "content": "Message 10"}

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
            resp = client.post(
                f"/api/v1/conversations/{CONVERSATION_ID}/messages", json=payload
            )

        assert resp.status_code == 201
        mock_dispatcher.dispatch.assert_called_once()
        call_args = mock_dispatcher.dispatch.call_args[0]
        assert call_args[1] == CONVERSATION_ID  # dispatch(fn, conversation_id, user_id)

    def test_twentieth_message_triggers_proposal_job(self, client):
        """
        The 10-message window repeats: the 20th message (existing_count=19 → new_count=20)
        also dispatches a proposal job.
        """
        mock_client = MagicMock()
        _make_messages_db(mock_client, existing_message_count=19)  # new_count = 20

        mock_dispatcher = MagicMock()
        payload = {"role": "user", "content": "Message 20"}

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
            resp = client.post(
                f"/api/v1/conversations/{CONVERSATION_ID}/messages", json=payload
            )

        assert resp.status_code == 201
        mock_dispatcher.dispatch.assert_called_once()
        call_args = mock_dispatcher.dispatch.call_args[0]
        assert call_args[1] == CONVERSATION_ID

    def test_non_tenth_message_does_not_trigger(self, client):
        """
        Messages at counts 1–9 and 11 do NOT trigger a proposal job.
        """
        for existing_count in (0, 4, 8, 10):  # new_count = 1, 5, 9, 11
            mock_client = MagicMock()
            _make_messages_db(mock_client, existing_message_count=existing_count)

            mock_dispatcher = MagicMock()
            payload = {"role": "user", "content": "Non-tenth message"}

            with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
                 patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
                resp = client.post(
                    f"/api/v1/conversations/{CONVERSATION_ID}/messages", json=payload
                )

            assert resp.status_code == 201, f"Failed for existing_count={existing_count}"
            mock_dispatcher.dispatch.assert_not_called(), f"Dispatch called for count={existing_count + 1}"

    def test_existing_pending_proposals_no_duplicate_dispatch(self, client):
        """
        If pending proposals already exist for the conversation,
        the periodic trigger is debounced — dispatch() is NOT called.
        """
        mock_client = MagicMock()
        _make_messages_db(
            mock_client,
            existing_message_count=9,  # new_count = 10 → would trigger
            pending_proposals=["existing proposal"],  # debounce fires
        )

        mock_dispatcher = MagicMock()
        payload = {"role": "user", "content": "Message 10 (debounced)"}

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
            resp = client.post(
                f"/api/v1/conversations/{CONVERSATION_ID}/messages", json=payload
            )

        assert resp.status_code == 201
        mock_dispatcher.dispatch.assert_not_called()

    def test_no_byok_key_periodic_silent_skip(self, client):
        """
        No BYOK API key configured → periodic bg job returns silently.
        call_llm must NOT be called; no rows written to memory_proposals.
        """
        from app.api.routes.conversations import _generate_periodic_proposals_job

        mock_client = MagicMock()
        inserted = _make_conv_db(mock_client, api_key_data=None)  # None = no key in DB

        mock_llm = MagicMock()
        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_LLM_PATCH, mock_llm):
            _generate_periodic_proposals_job(CONVERSATION_ID, "test-user-id")

        mock_llm.assert_not_called()
        assert inserted == [], "Expected no proposals inserted when no BYOK key"

    def test_agent_scoped_periodic_proposal_uses_agent_instance_id(self, client):
        """
        When active_agent_id is set, the periodic bg job must write agent_instance_id
        (not project_id) to the memory_proposals row.

        Regression test for KIN-306 C2: agent scope fetched but ignored — all proposals
        were written with project_id regardless of conversation scope.
        """
        from app.api.routes.conversations import _generate_periodic_proposals_job

        proposal = "User iterates quickly in short sessions"
        mock_client = MagicMock()
        inserted = _make_conv_db(
            mock_client,
            project_id=PROJECT_ID,
            active_agent_id=_AGENT_DEF_ID,
            agent_instance_id=_AGENT_INSTANCE_ID,
        )

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_LLM_PATCH, return_value=f'["{proposal}"]'), \
             patch("app.api.routes.conversations.load_master_key", return_value=b"\x00" * 32), \
             patch("app.api.routes.conversations.decrypt_api_key", return_value="sk-test"):
            _generate_periodic_proposals_job(CONVERSATION_ID, "test-user-id")

        assert len(inserted) == 1, f"Expected 1 insert, got {len(inserted)}: {inserted}"
        row = inserted[0]
        assert row.get("agent_instance_id") == _AGENT_INSTANCE_ID
        assert "project_id" not in row
        assert row["trigger_type"] == "periodic"


# ---------------------------------------------------------------------------
# Conversation-end proposals — KIN-307
# ---------------------------------------------------------------------------

CONV_ROUTE_PATCH = "app.api.routes.conversations.get_supabase_client"
CONV_DISPATCHER_PATCH = "app.api.routes.conversations.get_task_dispatcher"
CONV_LLM_PATCH = "app.api.routes.conversations.call_llm"

_VALID_KEY_DATA = {"key_ciphertext": "deadbeef", "key_nonce": "cafebabe"}


_AGENT_INSTANCE_ID = "agent-instance-uuid-1"
_AGENT_DEF_ID = "agent-def-uuid-1"


def _make_conv_db(
    mock_client,
    *,
    project_id=PROJECT_ID,
    active_agent_id=None,
    agent_instance_id=_AGENT_INSTANCE_ID,
    api_key_data=_VALID_KEY_DATA,
    proposals=None,
):
    """
    Wire a mock Supabase client for _generate_proposals_job DB calls.

    Tables wired:
    - conversations → project_id, active_agent_id (with deleted_at IS NULL filter)
    - agent_instances → id (when active_agent_id is set)
    - users → default_model_id
    - llm_models → model_id, provider
    - user_api_keys → api_key_data (pass None to simulate no key configured)
    - messages → one user message
    - memory_proposals → existing pending proposals (for dedup) + insert tracking

    Returns a list that will be populated with inserted memory_proposals rows.
    """

    inserted_proposals: list = []
    existing_proposals = proposals or []

    def _table(name):
        m = MagicMock()
        if name == "conversations":
            # Chain: .select().eq().eq().is_().single().execute()
            m.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={"project_id": project_id, "active_agent_id": active_agent_id}
            )
        elif name == "agent_instances":
            m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": agent_instance_id} if agent_instance_id else None
            )
        elif name == "users":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"default_model_id": "model-uuid-1"}
            )
        elif name == "llm_models":
            m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"model_id": "gpt-4o", "provider": "openai"}
            )
        elif name == "user_api_keys":
            m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=api_key_data
            )
        elif name == "messages":
            m.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"role": "user", "content": "I prefer async comms", "sequence": 0}]
            )
        elif name == "memory_proposals":
            m.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"proposed_content": p} for p in existing_proposals]
            )

            def _capture_insert(row):
                inserted_proposals.append(row)
                return MagicMock(execute=MagicMock(return_value=MagicMock(data=[row])))

            m.insert.side_effect = _capture_insert
        return m

    mock_client.table.side_effect = _table
    return inserted_proposals


class TestConversationEndProposals:
    """
    Tests for the explicit conversation-end proposal trigger.
    Route: POST /api/v1/conversations/{id}/end
    Implementation ticket: KIN-307
    """

    def test_conversation_end_endpoint_fires_proposal_job(self, client):
        """
        POST /conversations/{id}/end dispatches a proposal generation job.
        Verify: TaskDispatcher.dispatch() called once with the correct conversation_id.
        """
        mock_client = MagicMock()
        # Ownership check: conversations.select().eq().eq().is_().single().execute()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": CONVERSATION_ID}
        )
        mock_dispatcher = MagicMock()
        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
            resp = client.post(f"/api/v1/conversations/{CONVERSATION_ID}/end")

        assert resp.status_code == 202
        mock_dispatcher.dispatch.assert_called_once()
        call_args = mock_dispatcher.dispatch.call_args[0]
        # dispatch(fn, conversation_id, user_id) — args[1] is conversation_id
        assert call_args[1] == CONVERSATION_ID

    def test_conversation_end_wrong_user_returns_404(self, client):
        """
        POST /conversations/{id}/end with a conversation owned by another user → 404.
        The ownership check must prevent dispatching the background job. (KIN-344)
        """
        mock_client = MagicMock()
        # Ownership check fails: no matching row
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_dispatcher = MagicMock()
        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_DISPATCHER_PATCH, return_value=mock_dispatcher):
            resp = client.post(f"/api/v1/conversations/{CONVERSATION_ID}/end")

        assert resp.status_code == 404
        mock_dispatcher.dispatch.assert_not_called()

    def test_conversation_end_existing_proposals_append_not_duplicate(self, client):
        """
        If existing pending proposals exist for the scope, the bg job appends new unique
        proposals (merge into single review batch) and skips content-level duplicates.

        Spec decision: conversation-end does not block on existing proposals;
        deduplication is content-level only (case-insensitive).
        """
        from app.api.routes.conversations import _generate_proposals_job

        new_proposal = "User prefers bullet points over paragraphs"
        existing_proposal = "User works best in the mornings"  # already pending

        mock_client = MagicMock()
        inserted = _make_conv_db(mock_client, proposals=[existing_proposal])

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_LLM_PATCH, return_value=f'["{new_proposal}", "{existing_proposal}"]'), \
             patch("app.api.routes.conversations.load_master_key", return_value=b"\x00" * 32), \
             patch("app.api.routes.conversations.decrypt_api_key", return_value="sk-test"):
            _generate_proposals_job(CONVERSATION_ID, "test-user-id")

        # Only the new proposal should be inserted; existing content is deduped
        assert inserted is not None
        assert len(inserted) == 1, f"Expected 1 insert, got {len(inserted)}: {inserted}"
        assert inserted[0]["proposed_content"] == new_proposal
        assert inserted[0]["trigger_type"] == "conversation_end"
        assert inserted[0]["project_id"] == PROJECT_ID

    def test_no_byok_key_conversation_end_silent_skip(self, client):
        """
        No BYOK key configured → bg job returns silently.
        call_llm must NOT be called; no rows written to memory_proposals.
        """
        from app.api.routes.conversations import _generate_proposals_job

        mock_client = MagicMock()
        inserted = _make_conv_db(mock_client, api_key_data=None)  # None = no key in DB

        mock_llm = MagicMock()
        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_LLM_PATCH, mock_llm):
            _generate_proposals_job(CONVERSATION_ID, "test-user-id")

        mock_llm.assert_not_called()
        assert inserted is not None
        assert len(inserted) == 0, "Expected no proposals inserted when no BYOK key"

    def test_agent_scoped_conversation_proposal_uses_agent_instance_id(self, client):
        """
        When active_agent_id is set on the conversation (agent-scoped), the inserted
        memory_proposals row must use agent_instance_id (not project_id).

        Regression test for C1 from Gilfoyle's KIN-307 review: agent scope was fetched
        but ignored — all proposals were written with project_id regardless.
        """
        from app.api.routes.conversations import _generate_proposals_job

        proposal = "User prefers concise code comments"
        mock_client = MagicMock()
        inserted = _make_conv_db(
            mock_client,
            project_id=PROJECT_ID,
            active_agent_id=_AGENT_DEF_ID,
            agent_instance_id=_AGENT_INSTANCE_ID,
        )

        with patch(CONV_ROUTE_PATCH, return_value=mock_client), \
             patch(CONV_LLM_PATCH, return_value=f'["{proposal}"]'), \
             patch("app.api.routes.conversations.load_master_key", return_value=b"\x00" * 32), \
             patch("app.api.routes.conversations.decrypt_api_key", return_value="sk-test"):
            _generate_proposals_job(CONVERSATION_ID, "test-user-id")

        assert len(inserted) == 1, f"Expected 1 insert, got {len(inserted)}: {inserted}"
        row = inserted[0]
        assert row.get("agent_instance_id") == _AGENT_INSTANCE_ID, (
            f"Expected agent_instance_id={_AGENT_INSTANCE_ID!r}, got row={row}"
        )
        assert "project_id" not in row, (
            f"project_id must not be set for agent-scoped proposals, got row={row}"
        )
        assert row["trigger_type"] == "conversation_end"
