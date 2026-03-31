"""
E2E Flow Tests — KIN-340

Mock-based multi-step user journey tests. Each test sequences multiple API calls
with consistent state across steps, verifying the full route orchestration.

These run in CI without a real Supabase instance. For full integration tests
against a seeded DB, see test_e2e_integration.py (requires KINETIC_RUN_INTEGRATION_TESTS=1).

Run with:  python -m pytest tests/test_e2e_flows.py -v

7 journeys:
  1. Onboarding          — profile setup + company + project creation
  2. KB Ingestion        — document upload → polling for completed status
  3. Agent Setup         — create agent → get-or-create instance → update overrides
  4. Generation          — store messages in a project conversation
  5. Active Memory       — create entries + proposals + review flow
  6. MCP                 — generate token → hit /mcp/context → verify context assembled
  7. Admin Flows         — list users + disable gate + RAG debug traces

All Supabase calls are mocked per-route using the same PATCH_TARGET pattern as unit tests.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID, TEST_ADMIN_ID

# ---------------------------------------------------------------------------
# Shared IDs — consistent across all steps in a journey
# ---------------------------------------------------------------------------

_COMPANY_ID = str(uuid4())
_PROJECT_ID = str(uuid4())
_AGENT_ID = str(uuid4())
_INSTANCE_ID = str(uuid4())
_KB_ID = str(uuid4())
_DOCUMENT_ID = str(uuid4())
_ENTRY_ID = str(uuid4())
_PROPOSAL_ID = str(uuid4())
_CONV_ID = str(uuid4())
_MESSAGE_ID = str(uuid4())
_TOKEN_ID = str(uuid4())
_TOKEN_RAW = "abc" * 21  # 63 chars — stands in for os.urandom output
_TRACE_ID = str(uuid4())

_MCP_USER_ID = str(uuid4())
_MCP_TOKEN_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_PROFILE_DB = "app.api.routes.profile.get_supabase_client"
_COMPANIES_DB = "app.api.routes.companies.get_supabase_client"
_PROJECTS_DB = "app.api.routes.projects.get_supabase_client"
_AGENTS_DB = "app.api.routes.agents.get_supabase_client"
_ACTIVE_MEMORY_DB = "app.api.routes.active_memory.get_supabase_client"
_CONVERSATIONS_DB = "app.api.routes.conversations.get_supabase_client"
_DOCUMENTS_DB = "app.api.routes.documents.get_supabase"
_MCP_DB = "app.api.routes.mcp.get_supabase_client"
_MCP_TOKENS_DB = "app.api.routes.mcp_tokens.get_supabase_client"
_ADMIN_USERS_DB = "app.api.routes.admin_users.get_supabase_client"
_RAG_DEBUG_DB = "app.api.routes.admin_rag_debug.get_supabase_client"


# ---------------------------------------------------------------------------
# Patch pipeline services (framework + RAG) for MCP journey
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_pipeline_services(monkeypatch):
    """Silence framework selection and RAG retrieval for MCP journey steps."""
    from app.services.rag.framework_selection import FrameworkMatch

    async def _no_rag(*args, **kwargs):
        return []

    async def _no_framework(*args, **kwargs):
        return FrameworkMatch(
            matched_framework_id=None,
            matched_framework_name=None,
            framework_text=None,
        )

    monkeypatch.setattr("app.api.routes.mcp.retrieve", _no_rag)
    monkeypatch.setattr("app.api.routes.mcp.select_framework", _no_framework)


# ---------------------------------------------------------------------------
# Journey 1: Onboarding
# Sequence: GET profile → PATCH profile → POST api-key → POST company → POST project
# ---------------------------------------------------------------------------


class TestJourney1Onboarding:
    """User creates account, sets up profile, creates company and project."""

    def test_onboarding_flow(self, client):
        # --- Step 1: GET /profile ---
        profile_row = {
            "id": TEST_USER_ID,
            "name": "Alice",
            "email": "alice@example.com",
            "bio": None,
            "default_model_id": None,
        }
        profile_db = MagicMock()
        profile_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=profile_row
        )
        with patch(_PROFILE_DB, return_value=profile_db):
            resp = client.get("/api/v1/profile")
        assert resp.status_code == 200
        assert resp.json()["id"] == TEST_USER_ID

        # --- Step 2: PATCH /profile (name + bio) ---
        updated_profile = {**profile_row, "name": "Alice Builder", "bio": "Product + AI"}
        profile_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_profile]
        )
        with patch(_PROFILE_DB, return_value=profile_db):
            resp = client.patch(
                "/api/v1/profile",
                json={"name": "Alice Builder", "bio": "Product + AI"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice Builder"

        # --- Step 3: POST /profile/api-keys (Anthropic key) ---
        api_key_db = MagicMock()
        api_key_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"provider": "anthropic"}])
        # API key route may also fetch the existing row first — wire select too
        api_key_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=None)
        with patch(_PROFILE_DB, return_value=api_key_db):
            resp = client.post(
                "/api/v1/profile/api-keys",
                json={"provider": "anthropic", "api_key": "sk-ant-test-key"},
            )
        # Upsert — 200 or 201 depending on implementation
        assert resp.status_code in (200, 201)

        # --- Step 4: POST /companies ---
        company_row = {
            "id": _COMPANY_ID,
            "user_id": TEST_USER_ID,
            "name": "ACME Corp",
            "description": "Test company",
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        company_db = MagicMock()
        company_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[company_row]
        )
        with patch(_COMPANIES_DB, return_value=company_db):
            resp = client.post(
                "/api/v1/companies",
                json={"name": "ACME Corp", "description": "Test company"},
            )
        assert resp.status_code == 200
        company_id = resp.json()["id"]
        assert company_id == _COMPANY_ID

        # --- Step 5: POST /projects with company_id from step 4 ---
        project_row = {
            "id": _PROJECT_ID,
            "company_id": company_id,
            "user_id": TEST_USER_ID,
            "name": "Alpha Project",
            "instructions": "Be concise.",
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        project_db = MagicMock()
        project_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[project_row]
        )
        # Projects may check company ownership — wire that too
        project_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": company_id, "user_id": TEST_USER_ID}
        )
        with patch(_PROJECTS_DB, return_value=project_db):
            resp = client.post(
                "/api/v1/projects",
                json={
                    "name": "Alpha Project",
                    "company_id": company_id,
                    "instructions": "Be concise.",
                },
            )
        assert resp.status_code in (200, 201)
        project_id = resp.json()["id"]
        assert project_id == _PROJECT_ID
        assert resp.json()["company_id"] == company_id


# ---------------------------------------------------------------------------
# Journey 2: KB Ingestion
# Sequence: POST /documents/upload → GET /documents/{id} (status=completed)
# ---------------------------------------------------------------------------


class TestJourney2KBIngestion:
    """User uploads a document to a KB; polls until status=completed."""

    def test_kb_ingestion_flow(self, client):
        # --- Step 1: POST /documents/upload ---
        kb_row = {
            "project_id": _PROJECT_ID,
            "agent_definition_id": None,
            "user_id": TEST_USER_ID,
        }
        doc_row = {
            "id": _DOCUMENT_ID,
            "knowledge_base_id": _KB_ID,
            "filename": "strategy.pdf",
            "status": "pending",
            "error_stage": None,
            "error_message": None,
            "retry_count": 0,
        }

        upload_db = MagicMock()
        # KB lookup
        upload_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=kb_row
        )
        # Document insert
        upload_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[doc_row]
        )

        pdf_bytes = b"%PDF-1.4 minimal test content"
        file_payload = io.BytesIO(pdf_bytes)

        # Also patch ingestion pipeline and BYOK key fetch
        with patch(_DOCUMENTS_DB, return_value=upload_db), \
             patch("app.api.routes.documents.run_ingestion"), \
             patch("app.api.routes.documents.fetch_user_key_async", new_callable=AsyncMock, return_value="sk-test"):
            resp = client.post(
                "/api/v1/documents/upload",
                data={"knowledge_base_id": _KB_ID},
                files={"file": ("strategy.pdf", file_payload, "application/pdf")},
            )
        assert resp.status_code == 200
        data = resp.json()
        # document_id is generated internally by the route (uuid4()), not from mock data
        assert data["document_id"]
        assert data["status"] == "pending"
        document_id = data["document_id"]

        # --- Step 2: GET /documents/{id} — polled after processing, status=completed ---
        # Route queries knowledge_base_documents (with is_("deleted_at")), then knowledge_bases for RLS.
        completed_doc = {**doc_row, "status": "completed"}
        status_db = MagicMock()

        def _status_table(name):
            chain = MagicMock()
            if name == "knowledge_base_documents":
                chain.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[completed_doc]
                )
            elif name == "knowledge_bases":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"user_id": TEST_USER_ID}
                )
            return chain

        status_db.table.side_effect = _status_table
        with patch(_DOCUMENTS_DB, return_value=status_db):
            resp = client.get(f"/api/v1/documents/{document_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# Journey 3: Agent Setup
# Sequence: POST /agents → GET /agents/{id}/instance → PATCH instance overrides
# ---------------------------------------------------------------------------


class TestJourney3AgentSetup:
    """User creates an agent, gets or creates an instance, updates framework overrides."""

    def test_agent_setup_flow(self, client):
        agent_row = {
            "id": _AGENT_ID,
            "owner_id": TEST_USER_ID,
            "name": "Strategist",
            "instructions": "Think strategically.",
            "type": "custom",
            "visibility": "private",
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        instance_row = {
            "id": _INSTANCE_ID,
            "agent_definition_id": _AGENT_ID,
            "user_id": TEST_USER_ID,
            "framework_overrides": {"pinned": [], "excluded": []},
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }

        # --- Step 1: POST /agents ---
        create_db = MagicMock()
        create_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[agent_row]
        )
        with patch(_AGENTS_DB, return_value=create_db):
            resp = client.post(
                "/api/v1/agents",
                json={
                    "name": "Strategist",
                    "instructions": "Think strategically.",
                    "type": "custom",
                },
            )
        assert resp.status_code == 200
        agent_id = resp.json()["id"]
        assert agent_id == _AGENT_ID

        # --- Step 2: GET /agents/{id}/instance (get-or-create) ---
        # get_or_create_instance: Step 0 fetches agent_definitions (ownership check),
        # Step 1 fetches agent_instances (SELECT returns existing row → no insert needed).
        instance_db = MagicMock()

        def _instance_table(name):
            chain = MagicMock()
            if name == "agent_definitions":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": _AGENT_ID, "owner_id": TEST_USER_ID, "visibility": "private"}
                )
            elif name == "agent_instances":
                chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[instance_row]
                )
            return chain

        instance_db.table.side_effect = _instance_table
        with patch(_AGENTS_DB, return_value=instance_db):
            resp = client.get(f"/api/v1/agents/{agent_id}/instance")
        assert resp.status_code == 200
        assert resp.json()["agent_definition_id"] == agent_id

        # --- Step 3: PATCH /agents/{id}/instance (framework overrides) ---
        overrides = {"pinned": ["framework-abc"], "excluded": []}
        updated_instance = {**instance_row, "framework_overrides": overrides}
        update_db = MagicMock()
        update_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=instance_row
        )
        # update_instance: .update().eq("id", instance["id"]).execute() — single eq
        update_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[updated_instance]
        )
        with patch(_AGENTS_DB, return_value=update_db):
            resp = client.patch(
                f"/api/v1/agents/{agent_id}/instance",
                json={"framework_overrides": overrides},
            )
        assert resp.status_code == 200
        assert resp.json()["framework_overrides"] == overrides


# ---------------------------------------------------------------------------
# Journey 4: Generation with Full Context Stack
# Sequence: POST /conversations/{id}/messages (with agent) → 201
# ---------------------------------------------------------------------------


class TestJourney4Generation:
    """User sends a message with agent invoked; message is stored with correct scope."""

    def test_generation_flow_stores_message(self, client):
        conv_row = {
            "id": _CONV_ID,
            "project_id": _PROJECT_ID,
            "active_agent_id": _AGENT_ID,
        }
        message_row = {
            "id": _MESSAGE_ID,
            "conversation_id": _CONV_ID,
            "role": "user",
            "content": "What should I prioritize this week?",
            "sequence": 1,
            "agent_definition_id": _AGENT_ID,
            "model": None,
            "created_at": "2026-03-24T00:00:00+00:00",
        }

        conv_db = MagicMock()
        # Conversation lookup
        conv_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=conv_row
        )
        # Message insert
        conv_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[message_row]
        )
        # Periodic proposal check (count)
        conv_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch(_CONVERSATIONS_DB, return_value=conv_db):
            resp = client.post(
                f"/api/v1/conversations/{_CONV_ID}/messages",
                json={
                    "role": "user",
                    "content": "What should I prioritize this week?",
                    "agent_definition_id": _AGENT_ID,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["role"] == "user"
        assert resp.json()["conversation_id"] == _CONV_ID


# ---------------------------------------------------------------------------
# Journey 5: Active Memory
# Sequence: POST entry → GET list → GET proposals → POST proposals/review
# ---------------------------------------------------------------------------


class TestJourney5ActiveMemory:
    """User saves to active memory, views proposals, and accepts them."""

    def test_active_memory_flow(self, client):
        entry_row = {
            "id": _ENTRY_ID,
            "user_id": TEST_USER_ID,
            "project_id": _PROJECT_ID,
            "agent_instance_id": None,
            "content": "Alice is focused on Q2 growth targets.",
            "source_conversation_id": None,
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        proposal_row = {
            "id": _PROPOSAL_ID,
            "user_id": TEST_USER_ID,
            "project_id": _PROJECT_ID,
            "agent_instance_id": None,
            "proposed_content": "Alice prioritises revenue metrics over cost reduction.",
            "status": "pending",
            "trigger_type": "conversation_end",
            "conversation_id": _CONV_ID,
            "created_at": "2026-03-24T00:00:00+00:00",
        }

        # --- Step 1: POST /active-memory ---
        create_db = MagicMock()
        # Token count check (existing entries)
        create_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[]
        )
        # Insert
        create_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[entry_row]
        )
        with patch(_ACTIVE_MEMORY_DB, return_value=create_db):
            resp = client.post(
                "/api/v1/active-memory",
                json={"content": entry_row["content"], "project_id": _PROJECT_ID},
            )
        assert resp.status_code in (200, 201)
        assert resp.json()["id"] == _ENTRY_ID

        # --- Step 2: GET /active-memory?project_id=... ---
        # Route calls _verify_project_ownership (projects table) then queries active_memory_entries.
        # Chain: .select().eq().eq().order().execute() — no .is_() in the entries query.
        list_db = MagicMock()

        def _list_table(name):
            chain = MagicMock()
            if name == "projects":
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": _PROJECT_ID}
                )
            elif name == "active_memory_entries":
                chain.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=[entry_row]
                )
            return chain

        list_db.table.side_effect = _list_table
        with patch(_ACTIVE_MEMORY_DB, return_value=list_db):
            resp = client.get(f"/api/v1/active-memory?project_id={_PROJECT_ID}")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) >= 1
        assert entries[0]["id"] == _ENTRY_ID

        # --- Step 3: GET /active-memory/proposals?project_id=... ---
        # Route: _verify_project_ownership (projects), then memory_proposals .eq().eq().eq().execute() (no .order())
        proposals_db = MagicMock()

        def _proposals_table(name):
            chain = MagicMock()
            if name == "projects":
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": _PROJECT_ID}
                )
            elif name == "memory_proposals":
                chain.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[proposal_row]
                )
            return chain

        proposals_db.table.side_effect = _proposals_table
        with patch(_ACTIVE_MEMORY_DB, return_value=proposals_db):
            resp = client.get(f"/api/v1/active-memory/proposals?project_id={_PROJECT_ID}")
        assert resp.status_code == 200
        proposals = resp.json()["proposals"]
        assert len(proposals) >= 1
        assert proposals[0]["id"] == _PROPOSAL_ID

        # --- Step 4: POST /active-memory/proposals/review (accept) ---
        accepted_entry = {**entry_row, "id": str(uuid4()), "content": proposal_row["proposed_content"]}
        review_db = MagicMock()
        # Proposal lookup
        review_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[proposal_row]
        )
        # Token count check
        review_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(
            data=[entry_row]
        )
        # Insert accepted entry
        review_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[accepted_entry]
        )
        # Proposal status update
        review_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{**proposal_row, "status": "accepted"}]
        )
        with patch(_ACTIVE_MEMORY_DB, return_value=review_db):
            resp = client.post(
                "/api/v1/active-memory/proposals/review",
                json={"decisions": [{"proposal_id": _PROPOSAL_ID, "action": "accept"}]},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Journey 6: MCP
# Sequence: POST /mcp/tokens → POST /mcp/context (bearer token auth)
# ---------------------------------------------------------------------------


class TestJourney6MCP:
    """User generates an MCP token and hits the context endpoint."""

    def test_mcp_flow(self, client, raw_client):
        # --- Step 1: POST /mcp/tokens (requires Supabase JWT auth via `client`) ---
        token_row = {
            "id": _TOKEN_ID,
            "user_id": TEST_USER_ID,
            "name": "Claude Desktop",
            "last_used_at": None,
            "revoked_at": None,
            "created_at": "2026-03-24T00:00:00+00:00",
        }
        token_db = MagicMock()
        token_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[token_row]
        )
        with patch(_MCP_TOKENS_DB, return_value=token_db):
            resp = client.post("/api/v1/mcp/tokens", json={"name": "Claude Desktop"})
        assert resp.status_code == 200
        raw_token = resp.json()["token"]
        assert raw_token.startswith("mcp_")

        # --- Step 2: POST /mcp/context (bearer token auth, project_id + agent_id) ---
        import hashlib
        token_value = raw_token[4:]  # strip "mcp_" prefix
        token_hash = hashlib.sha256(token_value.encode()).hexdigest()

        mcp_token_row = {"id": _TOKEN_ID, "user_id": _MCP_USER_ID, "revoked_at": None}
        user_row = {"id": _MCP_USER_ID, "name": "Alice", "email": "alice@example.com", "bio": "Builder"}
        company_row = {"id": _COMPANY_ID, "name": "ACME Corp", "description": "Test"}
        project_row = {
            "id": _PROJECT_ID, "company_id": _COMPANY_ID,
            "user_id": _MCP_USER_ID, "name": "Alpha Project",
            "instructions": "Be concise.",
        }
        agent_row = {
            "id": _AGENT_ID, "owner_id": _MCP_USER_ID, "name": "Strategist",
            "instructions": "Think strategically.", "visibility": "public",
        }

        def _mcp_table(name):
            chain = MagicMock()
            if name == "mcp_tokens":
                chain.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=mcp_token_row
                )
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "users":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=user_row)
            elif name == "projects":
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=project_row)
            elif name == "companies":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
            elif name == "agent_definitions":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=agent_row)
            return chain

        mcp_db = MagicMock()
        mcp_db.table.side_effect = _mcp_table
        mcp_db.rpc.return_value.execute.return_value = MagicMock(
            data=[{"allowed": True, "request_count": 1, "daily_cap": 1000}]
        )

        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={
                    "query": "What should I focus on this week?",
                    "project_id": _PROJECT_ID,
                    "agent_id": _AGENT_ID,
                },
                headers={"Authorization": f"Bearer {raw_token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data
        assert "L1" in data["metadata"]["layers_assembled"]
        assert "L3" in data["metadata"]["layers_assembled"]
        assert "L5" in data["metadata"]["layers_assembled"]


# ---------------------------------------------------------------------------
# Journey 7: Admin Flows
# Sequence: GET /admin/users → PATCH /admin/users/{id}/disable → GET /admin/rag-debug
# ---------------------------------------------------------------------------


class TestJourney7AdminFlows:
    """Admin lists users, attempts to disable (hits public-agent gate), views RAG traces."""

    def test_admin_flows(self, admin_client):
        target_user_id = str(uuid4())

        # --- Step 1: GET /admin/users ---
        user_rows = [
            {
                "id": TEST_ADMIN_ID,
                "name": "Admin User",
                "role": "admin",
                "disabled_at": None,
                "created_at": "2026-03-24T00:00:00+00:00",
                "email": "admin@test.com",
            },
            {
                "id": target_user_id,
                "name": "Regular User",
                "role": "user",
                "disabled_at": None,
                "created_at": "2026-03-24T00:00:00+00:00",
                "email": "user@test.com",
            },
        ]
        list_db = MagicMock()
        list_db.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
            data=user_rows
        )
        with patch(_ADMIN_USERS_DB, return_value=list_db):
            resp = admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        users = resp.json()["users"]
        assert len(users) == 2
        user_ids = {u["id"] for u in users}
        assert target_user_id in user_ids

        # --- Step 2: PATCH /admin/users/{id}/disable — blocked (public agent exists) ---
        public_agent_row = {
            "id": _AGENT_ID,
            "owner_id": target_user_id,
            "name": "Public Agent",
            "visibility": "public",
        }
        target_user_row = {
            "id": target_user_id,
            "name": "Regular User",
            "role": "user",
            "disabled_at": None,
        }
        block_db = MagicMock()
        # User fetch
        block_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=target_user_row
        )
        # Public agents check — returns one (blocks disable)
        block_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[public_agent_row]
        )
        with patch(_ADMIN_USERS_DB, return_value=block_db):
            resp = admin_client.patch(f"/api/v1/admin/users/{target_user_id}/disable")
        # Expect 409 — cannot disable while public agents exist
        assert resp.status_code == 409

        # --- Step 3: GET /admin/rag-debug ---
        trace_rows = [
            {
                "id": _TRACE_ID,
                "message_id": _MESSAGE_ID,
                "scope": "project_kb",
                "query_text": "What should I focus on?",
                "gating_decision": "injected",
                "created_at": "2026-03-24T00:00:00+00:00",
                "injected_chunk_count": 3,
                "vector_candidate_count": 10,
            }
        ]
        debug_db = MagicMock()
        debug_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=trace_rows
        )
        with patch(_RAG_DEBUG_DB, return_value=debug_db):
            resp = admin_client.get("/api/v1/admin/rag-debug")
        assert resp.status_code == 200
        traces = resp.json()["traces"]
        assert len(traces) >= 1
        assert traces[0]["id"] == _TRACE_ID


# ---------------------------------------------------------------------------
# Journey 8: Agent Switch Mid-Conversation (KIN-347)
# Sequence: POST message with Agent A → POST message with Agent B → verify both stored
# ---------------------------------------------------------------------------

_AGENT_B_ID = str(uuid4())


class TestJourney8AgentSwitch:
    """User sends messages with two different agents in the same conversation."""

    def test_agent_switch_mid_conversation(self, client):
        msg1_id = str(uuid4())
        msg2_id = str(uuid4())

        msg1_row = {
            "id": msg1_id,
            "conversation_id": _CONV_ID,
            "role": "user",
            "content": "Strategist, help me plan Q3.",
            "sequence": 0,
            "agent_definition_id": _AGENT_ID,
            "model": None,
            "created_at": "2026-03-24T00:00:00+00:00",
        }
        msg2_row = {
            "id": msg2_id,
            "conversation_id": _CONV_ID,
            "role": "user",
            "content": "Analyst, review the numbers.",
            "sequence": 1,
            "agent_definition_id": _AGENT_B_ID,
            "model": None,
            "created_at": "2026-03-24T00:01:00+00:00",
        }

        # --- Step 1: POST message with Agent A ---
        def _msg1_table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": _CONV_ID, "project_id": _PROJECT_ID}
                )
            elif name == "messages":
                chain.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                chain.insert.return_value.execute.return_value = MagicMock(data=[msg1_row])
            return chain

        db1 = MagicMock()
        db1.table.side_effect = _msg1_table
        with patch(_CONVERSATIONS_DB, return_value=db1):
            resp = client.post(
                f"/api/v1/conversations/{_CONV_ID}/messages",
                json={
                    "role": "user",
                    "content": "Strategist, help me plan Q3.",
                    "agent_definition_id": _AGENT_ID,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["agent_definition_id"] == _AGENT_ID

        # --- Step 2: POST message with Agent B (switch) ---
        def _msg2_table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": _CONV_ID, "project_id": _PROJECT_ID}
                )
            elif name == "messages":
                chain.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[msg1_row])
                chain.insert.return_value.execute.return_value = MagicMock(data=[msg2_row])
            return chain

        db2 = MagicMock()
        db2.table.side_effect = _msg2_table
        with patch(_CONVERSATIONS_DB, return_value=db2):
            resp = client.post(
                f"/api/v1/conversations/{_CONV_ID}/messages",
                json={
                    "role": "user",
                    "content": "Analyst, review the numbers.",
                    "agent_definition_id": _AGENT_B_ID,
                },
            )
        assert resp.status_code == 201
        assert resp.json()["agent_definition_id"] == _AGENT_B_ID
        # Verify agent B is different from agent A
        assert resp.json()["agent_definition_id"] != _AGENT_ID


# ---------------------------------------------------------------------------
# Journey 9: Cross-Entity Data Flow (KIN-347)
# Sequence: POST company → POST project (with company_id) →
#           POST conversation → POST message → POST active-memory (with project_id)
# Verifies IDs chain correctly across entity boundaries.
# ---------------------------------------------------------------------------


class TestJourney9CrossEntityFlow:
    """Company→project→conversation→message→memory: IDs chain correctly."""

    def test_cross_entity_data_flow(self, client):
        # Use unique IDs for this journey to avoid collision
        j9_company_id = str(uuid4())
        j9_project_id = str(uuid4())
        j9_conv_id = str(uuid4())
        j9_msg_id = str(uuid4())
        j9_entry_id = str(uuid4())

        # --- Step 1: POST /companies ---
        company_row = {
            "id": j9_company_id,
            "user_id": TEST_USER_ID,
            "name": "FlowCo",
            "description": "Cross-entity test",
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        company_db = MagicMock()
        company_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[company_row])
        with patch(_COMPANIES_DB, return_value=company_db):
            resp = client.post("/api/v1/companies", json={"name": "FlowCo", "description": "Cross-entity test"})
        assert resp.status_code == 200
        assert resp.json()["id"] == j9_company_id

        # --- Step 2: POST /projects with company_id from step 1 ---
        project_row = {
            "id": j9_project_id,
            "company_id": j9_company_id,
            "user_id": TEST_USER_ID,
            "name": "Flow Project",
            "instructions": "Test instructions.",
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        project_db = MagicMock()
        project_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[project_row])
        project_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": j9_company_id, "user_id": TEST_USER_ID}
        )
        with patch(_PROJECTS_DB, return_value=project_db):
            resp = client.post(
                "/api/v1/projects",
                json={"name": "Flow Project", "company_id": j9_company_id, "instructions": "Test instructions."},
            )
        assert resp.status_code in (200, 201)
        assert resp.json()["company_id"] == j9_company_id

        # --- Step 3: POST message in conversation (conversation scoped to project) ---
        msg_row = {
            "id": j9_msg_id,
            "conversation_id": j9_conv_id,
            "role": "user",
            "content": "Track this insight.",
            "sequence": 0,
            "agent_definition_id": None,
            "model": None,
            "created_at": "2026-03-24T00:00:00+00:00",
        }

        def _msg_table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": j9_conv_id, "project_id": j9_project_id}
                )
            elif name == "messages":
                chain.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
                chain.insert.return_value.execute.return_value = MagicMock(data=[msg_row])
            return chain

        conv_db = MagicMock()
        conv_db.table.side_effect = _msg_table
        with patch(_CONVERSATIONS_DB, return_value=conv_db):
            resp = client.post(
                f"/api/v1/conversations/{j9_conv_id}/messages",
                json={"role": "user", "content": "Track this insight."},
            )
        assert resp.status_code == 201
        assert resp.json()["conversation_id"] == j9_conv_id

        # --- Step 4: POST /active-memory with project_id from step 2 ---
        entry_row = {
            "id": j9_entry_id,
            "user_id": TEST_USER_ID,
            "project_id": j9_project_id,
            "agent_instance_id": None,
            "content": "Key insight from conversation.",
            "source_conversation_id": j9_conv_id,
            "created_at": "2026-03-24T00:00:00+00:00",
            "updated_at": "2026-03-24T00:00:00+00:00",
        }
        mem_db = MagicMock()
        mem_db.table.return_value.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=[])
        mem_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[entry_row])
        with patch(_ACTIVE_MEMORY_DB, return_value=mem_db):
            resp = client.post(
                "/api/v1/active-memory",
                json={
                    "content": "Key insight from conversation.",
                    "project_id": j9_project_id,
                    "source_conversation_id": j9_conv_id,
                },
            )
        assert resp.status_code in (200, 201)
        # Verify the chain: memory entry references the correct project
        assert resp.json()["project_id"] == j9_project_id


# ---------------------------------------------------------------------------
# Journey 10: MCP Context Stack Layer Verification (KIN-347)
# Verifies correct layers_assembled for different scope combinations.
# ---------------------------------------------------------------------------


class TestJourney10ContextLayers:
    """MCP context endpoint returns correct layers for different scope combos."""

    def _make_mcp_db(self, token_user_id, project_row=None, company_row=None, agent_row=None):
        """Build an MCP DB mock with table routing for the given scope entities."""
        mcp_token_row = {"id": _MCP_TOKEN_ID, "user_id": token_user_id, "revoked_at": None}
        user_row = {"id": token_user_id, "name": "Alice", "email": "alice@example.com", "bio": "Builder"}

        def _table(name):
            chain = MagicMock()
            if name == "mcp_tokens":
                chain.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=mcp_token_row
                )
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "users":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=user_row)
            elif name == "projects" and project_row:
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=project_row)
            elif name == "companies" and company_row:
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
            elif name == "agent_definitions" and agent_row:
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=agent_row)
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        db.rpc.return_value.execute.return_value = MagicMock(
            data=[{"allowed": True, "request_count": 1, "daily_cap": 1000}]
        )
        return db

    def test_project_only_returns_l1_l2_l3(self, raw_client):
        """project_id only → L1, L2, L3 (no agent layer)."""
        uid = _MCP_USER_ID
        mcp_db = self._make_mcp_db(
            uid,
            project_row={
                "id": _PROJECT_ID, "company_id": _COMPANY_ID,
                "user_id": uid, "name": "P", "instructions": "X",
            },
            company_row={"id": _COMPANY_ID, "name": "C", "description": "D"},
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "project_id": _PROJECT_ID},
                headers={"Authorization": "Bearer mcp_test_token_project_only"},
            )
        assert resp.status_code == 200
        layers = resp.json()["metadata"]["layers_assembled"]
        assert layers == ["L1", "L2", "L3"]

    def test_company_only_returns_l1_l2(self, raw_client):
        """company_id only → L1, L2 (no project or agent layers)."""
        uid = _MCP_USER_ID
        mcp_db = self._make_mcp_db(
            uid,
            company_row={"id": _COMPANY_ID, "name": "C", "description": "D"},
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "company_id": _COMPANY_ID},
                headers={"Authorization": "Bearer mcp_test_token_company_only"},
            )
        assert resp.status_code == 200
        layers = resp.json()["metadata"]["layers_assembled"]
        assert layers == ["L1", "L2"]

    def test_project_plus_agent_returns_l1_l2_l3_l5(self, raw_client):
        """project_id + agent_id → L1, L2, L3, L5."""
        uid = _MCP_USER_ID
        mcp_db = self._make_mcp_db(
            uid,
            project_row={
                "id": _PROJECT_ID, "company_id": _COMPANY_ID,
                "user_id": uid, "name": "P", "instructions": "X",
            },
            company_row={"id": _COMPANY_ID, "name": "C", "description": "D"},
            agent_row={
                "id": _AGENT_ID, "owner_id": uid, "name": "A",
                "instructions": "Y", "visibility": "public",
            },
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "project_id": _PROJECT_ID, "agent_id": _AGENT_ID},
                headers={"Authorization": "Bearer mcp_test_token_proj_agent"},
            )
        assert resp.status_code == 200
        layers = resp.json()["metadata"]["layers_assembled"]
        assert layers == ["L1", "L2", "L3", "L5"]


# ---------------------------------------------------------------------------
# Journey 11: Error State Propagation (KIN-347)
# Verifies correct error codes for invalid state.
# ---------------------------------------------------------------------------


class TestJourney11ErrorPropagation:
    """Error states return correct HTTP codes, not silent failures."""

    def test_nonexistent_conversation_returns_404(self, client):
        """POST message to a conversation that doesn't exist → 404."""
        fake_conv_id = str(uuid4())

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        with patch(_CONVERSATIONS_DB, return_value=db):
            resp = client.post(
                f"/api/v1/conversations/{fake_conv_id}/messages",
                json={"role": "user", "content": "hello"},
            )
        assert resp.status_code == 404

    def test_nonexistent_document_returns_404(self, client):
        """GET document status for a non-existent document → 404."""
        fake_doc_id = str(uuid4())

        def _table(name):
            chain = MagicMock()
            if name == "knowledge_base_documents":
                chain.select.return_value.eq.return_value.is_.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        with patch(_DOCUMENTS_DB, return_value=db):
            resp = client.get(f"/api/v1/documents/{fake_doc_id}")
        assert resp.status_code == 404

    def test_non_owner_conversation_returns_404(self, client):
        """POST message to a conversation owned by another user → 404."""
        other_conv_id = str(uuid4())

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                # user_id filter returns no match (conversation exists but belongs to someone else)
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        with patch(_CONVERSATIONS_DB, return_value=db):
            resp = client.post(
                f"/api/v1/conversations/{other_conv_id}/messages",
                json={"role": "user", "content": "not my conversation"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Journey 12: MCP Private Agent Access Control (KIN-347)
# Verifies public agent accessible by any user, private agent by owner only.
# ---------------------------------------------------------------------------


class TestJourney12MCPPrivateAccess:
    """MCP: private agent → owner 200, non-owner 404. Public agent → any user 200."""

    def _make_mcp_db_for_access(self, token_user_id, agent_owner_id, agent_visibility):
        """Build MCP DB mock for access control tests."""
        mcp_token_row = {"id": _MCP_TOKEN_ID, "user_id": token_user_id, "revoked_at": None}
        user_row = {"id": token_user_id, "name": "User", "email": "user@example.com", "bio": "Test"}
        project_row = {
            "id": _PROJECT_ID, "company_id": _COMPANY_ID,
            "user_id": token_user_id, "name": "P", "instructions": "X",
        }
        company_row = {"id": _COMPANY_ID, "name": "C", "description": "D"}
        agent_row = {
            "id": _AGENT_ID, "owner_id": agent_owner_id, "name": "Agent",
            "instructions": "Y", "visibility": agent_visibility,
        }

        def _table(name):
            chain = MagicMock()
            if name == "mcp_tokens":
                chain.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data=mcp_token_row
                )
                chain.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "users":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=user_row)
            elif name == "projects":
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=project_row)
            elif name == "companies":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=company_row)
            elif name == "agent_definitions":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=agent_row)
            return chain

        db = MagicMock()
        db.table.side_effect = _table
        db.rpc.return_value.execute.return_value = MagicMock(
            data=[{"allowed": True, "request_count": 1, "daily_cap": 1000}]
        )
        return db

    def test_private_agent_owner_gets_200(self, raw_client):
        """Owner accessing own private agent → 200."""
        owner_id = _MCP_USER_ID
        mcp_db = self._make_mcp_db_for_access(
            token_user_id=owner_id,
            agent_owner_id=owner_id,
            agent_visibility="private",
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "project_id": _PROJECT_ID, "agent_id": _AGENT_ID},
                headers={"Authorization": "Bearer mcp_owner_private"},
            )
        assert resp.status_code == 200

    def test_private_agent_non_owner_gets_404(self, raw_client):
        """Non-owner accessing private agent → 404 (anti-enumeration)."""
        requester_id = _MCP_USER_ID
        actual_owner_id = str(uuid4())  # different user
        mcp_db = self._make_mcp_db_for_access(
            token_user_id=requester_id,
            agent_owner_id=actual_owner_id,
            agent_visibility="private",
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "project_id": _PROJECT_ID, "agent_id": _AGENT_ID},
                headers={"Authorization": "Bearer mcp_nonowner_private"},
            )
        assert resp.status_code == 404

    def test_public_agent_non_owner_gets_200(self, raw_client):
        """Non-owner accessing public agent → 200."""
        requester_id = _MCP_USER_ID
        actual_owner_id = str(uuid4())  # different user
        mcp_db = self._make_mcp_db_for_access(
            token_user_id=requester_id,
            agent_owner_id=actual_owner_id,
            agent_visibility="public",
        )
        with patch(_MCP_DB, return_value=mcp_db):
            resp = raw_client.post(
                "/api/v1/mcp/context",
                json={"query": "test", "project_id": _PROJECT_ID, "agent_id": _AGENT_ID},
                headers={"Authorization": "Bearer mcp_nonowner_public"},
            )
        assert resp.status_code == 200
