"""
Tests for KIN-413: Admin backfill endpoint for trigger embeddings.

Covers:
  - Admin auth guard (403 for non-admin)
  - Happy path: 2 agents, one with key (embeddings created), one without (skipped)
  - Idempotent on re-run (delete-then-insert for each framework)
  - Scoped to single agent_definition_id
  - Empty frameworks list for an agent (no embeddings, not counted)

All Supabase calls are mocked. Uses admin_client fixture from conftest.py.
ADR-007 §1.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_ADMIN_ID, TEST_USER_ID

PATCH_SUPABASE = "app.api.routes.admin_backfill.get_supabase_client"
PATCH_FETCH_KEY = "app.api.routes.admin_backfill.fetch_user_key"
PATCH_EMBEDDER = "app.api.routes.admin_backfill.EmbeddingService"

AGENT_1_ID = str(uuid4())
AGENT_2_ID = str(uuid4())
AGENT_1_OWNER = str(uuid4())
AGENT_2_OWNER = str(uuid4())
FW_1_ID = str(uuid4())
FW_2_ID = str(uuid4())
TEST_EMBED = [0.1, 0.2, 0.3]


def _agent(aid: str, owner_id: str) -> dict:
    return {"id": aid, "owner_id": owner_id}


def _fw(fw_id: str, agent_id: str, triggers: list[str]) -> dict:
    return {"id": fw_id, "agent_definition_id": agent_id, "when_to_apply": triggers}


# ---------------------------------------------------------------------------
# Admin auth guard
# ---------------------------------------------------------------------------


class TestBackfillAuthGuard:
    def test_non_admin_gets_403(self, client):
        """Non-admin calling the backfill endpoint gets 403."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error():
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            response = client.post("/api/v1/admin/backfill-trigger-embeddings")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------


class TestBackfillTriggerEmbeddings:
    def _setup_mock_db(self, mock_db, agents: list[dict], frameworks_by_agent: dict):
        """
        Wire mock_db for:
          - agent_definitions fetch (all agents)
          - per-agent frameworks fetch
        """
        # Agent list fetch
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=agents
        )
        # Per-agent framework fetch — use side_effect on .eq().execute() to return
        # different results per agent. We rely on lambda capture in the route, so
        # the mock chain for frameworks uses .eq().execute() (no .single()).
        # We route by tracking call order.
        fw_call_count = {"n": 0}
        agent_ids = [a["id"] for a in agents]

        def _fw_execute():
            # Returns frameworks for agents in order
            idx = fw_call_count["n"]
            fw_call_count["n"] += 1
            if idx < len(agent_ids):
                agent_id = agent_ids[idx]
                return MagicMock(data=frameworks_by_agent.get(agent_id, []))
            return MagicMock(data=[])

        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
            _fw_execute
        )

        # Delete + insert for trigger embeddings
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )

    def test_two_agents_one_with_key_one_without(self, admin_client):
        """
        2 agents: agent 1 has an OpenAI key (1 framework, 2 triggers),
        agent 2 has no key → skipped.
        Returns correct processed/skipped/frameworks_embedded/triggers_embedded counts.
        """
        agents = [_agent(AGENT_1_ID, AGENT_1_OWNER), _agent(AGENT_2_ID, AGENT_2_OWNER)]
        frameworks_by_agent = {
            AGENT_1_ID: [_fw(FW_1_ID, AGENT_1_ID, ["when planning", "when unsure"])],
            AGENT_2_ID: [],  # frameworks fetch never reached (no key)
        }

        mock_db = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [TEST_EMBED, TEST_EMBED]

        def _key_side_effect(client_arg, uid, provider):
            return "sk-test" if uid == AGENT_1_OWNER else None

        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=agents
        )
        fw_call_count = {"n": 0}

        def _fw_execute():
            idx = fw_call_count["n"]
            fw_call_count["n"] += 1
            return MagicMock(
                data=frameworks_by_agent.get(list(frameworks_by_agent.keys())[idx], [])
                if idx < len(frameworks_by_agent)
                else []
            )

        mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
            _fw_execute
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_FETCH_KEY, side_effect=_key_side_effect),
            patch(PATCH_EMBEDDER, return_value=mock_embedder),
        ):
            response = admin_client.post("/api/v1/admin/backfill-trigger-embeddings")

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 2
        assert data["skipped_no_key"] == 1
        assert data["frameworks_embedded"] == 1
        assert data["triggers_embedded"] == 2

    def test_idempotent_on_rerun(self, admin_client):
        """
        Running the backfill twice yields the same result — delete before insert
        ensures no duplicate rows.
        """
        agents = [_agent(AGENT_1_ID, AGENT_1_OWNER)]
        mock_db = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [TEST_EMBED]

        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=agents
        )
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[_fw(FW_1_ID, AGENT_1_ID, ["when planning"])])
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_FETCH_KEY, return_value="sk-test"),
            patch(PATCH_EMBEDDER, return_value=mock_embedder),
        ):
            r1 = admin_client.post("/api/v1/admin/backfill-trigger-embeddings")
            # Reset mock state for second run
            mock_db.reset_mock()
            mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
                data=agents
            )
            mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[_fw(FW_1_ID, AGENT_1_ID, ["when planning"])])
            )
            mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
                MagicMock(data=[])
            )
            mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": str(uuid4())}]
            )
            r2 = admin_client.post("/api/v1/admin/backfill-trigger-embeddings")

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()
        # Delete was called on each run (idempotent)
        mock_db.table.return_value.delete.assert_called()

    def test_scoped_to_single_agent(self, admin_client):
        """agent_definition_id query param scopes the backfill to one agent."""
        agents = [_agent(AGENT_1_ID, AGENT_1_OWNER)]
        mock_db = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [TEST_EMBED]

        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=agents)
        )
        # Frameworks for the scoped agent
        # The route does a second .eq() for the frameworks query — need to chain
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[_fw(FW_1_ID, AGENT_1_ID, ["when planning"])])
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": str(uuid4())}]
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_FETCH_KEY, return_value="sk-test"),
            patch(PATCH_EMBEDDER, return_value=mock_embedder),
        ):
            response = admin_client.post(
                f"/api/v1/admin/backfill-trigger-embeddings?agent_definition_id={AGENT_1_ID}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 1
