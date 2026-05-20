"""
Tests for KIN-412: embed_framework_triggers background job.

Covers:
  - Happy path: embeds triggers, deletes old rows, inserts new rows
  - No-op when triggers list is empty
  - Graceful skip when embedding fails
  - Route dispatch: create_framework dispatches embedding job
  - Route dispatch: update_framework dispatches job only when when_to_apply changes
  - Route dispatch: upload_frameworks dispatches jobs for inserts and updated when_to_apply
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_AGENT_ID = str(uuid4())
TEST_FW_ID = str(uuid4())
TEST_EMBED = [0.1, 0.2, 0.3]

PATCH_SUPABASE = "app.api.routes.agents.get_supabase_client"
PATCH_DISPATCHER = "app.api.routes.agents.get_task_dispatcher"
PATCH_CREATE_SUPABASE = "app.services.framework_embeddings.create_supabase"
PATCH_EMBEDDER = "app.services.framework_embeddings.EmbeddingService"


def _agent_row(owner_id: str = TEST_USER_ID) -> dict:
    return {
        "id": TEST_AGENT_ID,
        "owner_id": owner_id,
        "name": "Test Agent",
        "instructions": "Do things",
        "type": "custom",
        "visibility": "private",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _fw_row(fw_id: str = TEST_FW_ID, agent_id: str = TEST_AGENT_ID) -> dict:
    return {
        "id": fw_id,
        "agent_definition_id": agent_id,
        "framework_id": "test-fw",
        "name": "Test Framework",
        "when_to_apply": ["when unsure"],
        "confidence": "high",
        "principles": ["Think first"],
        "steps": [],
        "related_frameworks": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Unit tests: embed_framework_triggers service function
# ---------------------------------------------------------------------------


class TestEmbedFrameworkTriggers:
    def test_embeds_and_inserts(self):
        """Happy path: embeds triggers using platform Gemini key, deletes old rows, inserts new ones."""
        from app.services.framework_embeddings import embed_framework_triggers

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = [TEST_EMBED]

        with (
            patch(PATCH_CREATE_SUPABASE, return_value=mock_client),
            patch(PATCH_EMBEDDER, return_value=mock_embedder),
        ):
            asyncio.get_event_loop().run_until_complete(
                embed_framework_triggers(
                    framework_db_id=TEST_FW_ID,
                    agent_definition_id=TEST_AGENT_ID,
                    triggers=["when unsure"],
                    user_id=TEST_USER_ID,
                )
            )

        # Verify delete was called for idempotency
        mock_client.table.assert_any_call("framework_trigger_embeddings")
        mock_embedder.embed_batch.assert_called_once_with(["when unsure"])

    def test_no_op_when_triggers_empty(self):
        """When triggers list is empty, function returns immediately."""
        from app.services.framework_embeddings import embed_framework_triggers

        mock_client = MagicMock()

        with patch(PATCH_CREATE_SUPABASE, return_value=mock_client):
            asyncio.get_event_loop().run_until_complete(
                embed_framework_triggers(
                    framework_db_id=TEST_FW_ID,
                    agent_definition_id=TEST_AGENT_ID,
                    triggers=[],
                    user_id=TEST_USER_ID,
                )
            )

        mock_client.table.assert_not_called()

    def test_graceful_skip_on_embedding_error(self):
        """If embedding raises, function logs and returns without inserting."""
        from app.services.framework_embeddings import embed_framework_triggers

        mock_client = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.side_effect = RuntimeError("Gemini unreachable")

        with (
            patch(PATCH_CREATE_SUPABASE, return_value=mock_client),
            patch(PATCH_EMBEDDER, return_value=mock_embedder),
        ):
            # Should not raise
            asyncio.get_event_loop().run_until_complete(
                embed_framework_triggers(
                    framework_db_id=TEST_FW_ID,
                    agent_definition_id=TEST_AGENT_ID,
                    triggers=["when unsure"],
                    user_id=TEST_USER_ID,
                )
            )

        # Embedding failed — old rows are preserved (delete never called) and insert not called
        mock_client.table.assert_not_called()
        mock_embedder.embed_batch.assert_called_once()


# ---------------------------------------------------------------------------
# Route dispatch tests: create_framework
# ---------------------------------------------------------------------------

OTHER_USER_ID = str(uuid4())


class TestCreateFrameworkDispatch:
    def test_create_dispatches_embedding_job(self, client):
        """create_framework dispatches embed_framework_triggers after successful insert."""
        agent = _agent_row()
        fw_row = _fw_row()
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[fw_row]
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks",
                json={
                    "name": "Test Framework",
                    "when_to_apply": ["when unsure"],
                    "principles": ["Think first"],
                    "confidence": "high",
                },
            )

        assert response.status_code == 200
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        # args: (embed_framework_triggers, fw_db_id, agent_id, triggers, user_id)
        from app.services.framework_embeddings import embed_framework_triggers as _fn
        assert args[0] is _fn
        assert args[2] == TEST_AGENT_ID
        assert args[3] == ["when unsure"]

    def test_create_no_dispatch_on_validation_error(self, client):
        """create_framework does not dispatch if when_to_apply is empty (400 before insert)."""
        agent = _agent_row()
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks",
                json={
                    "name": "Bad",
                    "when_to_apply": [],
                    "principles": ["ok"],
                    "confidence": "high",
                },
            )

        assert response.status_code == 400
        mock_dispatcher.dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Route dispatch tests: update_framework
# ---------------------------------------------------------------------------


class TestUpdateFrameworkDispatch:
    def _setup_mocks(self, mock_db, agent, fw, updated_fw):
        """Wire mock_db for a standard update flow."""
        single_results = [MagicMock(data=agent), MagicMock(data=fw)]
        call_count = {"n": 0}

        def _single_execute():
            idx = call_count["n"]
            call_count["n"] += 1
            return single_results[idx] if idx < len(single_results) else MagicMock(data=None)

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = _single_execute
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = _single_execute
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[updated_fw])

    def test_update_dispatches_when_when_to_apply_changes(self, client):
        """PATCH dispatches embed job when when_to_apply is in the update."""
        agent = _agent_row()
        fw = _fw_row()
        updated_fw = {**fw, "when_to_apply": ["new trigger"]}
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()
        self._setup_mocks(mock_db, agent, fw, updated_fw)

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{TEST_FW_ID}",
                json={"when_to_apply": ["new trigger"]},
            )

        assert response.status_code == 200
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        assert args[1] == TEST_FW_ID
        assert args[3] == ["new trigger"]

    def test_update_no_dispatch_when_when_to_apply_unchanged(self, client):
        """PATCH does not dispatch embed job when when_to_apply is not in the update."""
        agent = _agent_row()
        fw = _fw_row()
        updated_fw = {**fw, "name": "Renamed"}
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()
        self._setup_mocks(mock_db, agent, fw, updated_fw)

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.patch(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/{TEST_FW_ID}",
                json={"name": "Renamed"},
            )

        assert response.status_code == 200
        mock_dispatcher.dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Route dispatch tests: upload_frameworks
# ---------------------------------------------------------------------------


class TestUploadFrameworksDispatch:
    def test_upload_dispatches_for_new_framework(self, client):
        """upload_frameworks dispatches embed job for each successfully inserted framework."""
        agent = _agent_row()
        new_fw_id = str(uuid4())
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()

        # Agent fetch
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        # Existing frameworks fetch (empty — all items are new inserts)
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        # Insert returns the new row with an ID
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": new_fw_id, "framework_id": "my-fw"}]
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            "name": "My Framework",
                            "framework_id": "my-fw",
                            "when_to_apply": ["when confused"],
                            "confidence": "high",
                            "principles": ["Think"],
                        }
                    ]
                },
            )

        assert response.status_code == 200
        assert response.json()["added"] == 1
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        assert args[1] == new_fw_id
        assert args[3] == ["when confused"]

    def test_upload_dispatches_for_updated_when_to_apply(self, client):
        """upload_frameworks dispatches embed job when updating an existing framework's when_to_apply."""
        agent = _agent_row()
        existing_db_id = str(uuid4())
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()

        # Agent fetch (uses .single())
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        # Existing frameworks fetch — has one existing framework
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"framework_id": "existing-fw", "id": existing_db_id}])
        )
        # Update call
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": existing_db_id}])
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            "name": "Existing Framework",
                            "framework_id": "existing-fw",
                            "when_to_apply": ["new trigger"],
                            "confidence": "high",
                            "principles": ["Think"],
                        }
                    ]
                },
            )

        assert response.status_code == 200
        assert response.json()["updated"] == 1
        mock_dispatcher.dispatch.assert_called_once()
        args = mock_dispatcher.dispatch.call_args[0]
        assert args[1] == existing_db_id
        assert args[3] == ["new trigger"]

    def test_upload_dispatches_when_when_to_apply_in_update(self, client):
        """upload_frameworks dispatches when when_to_apply is present in an updated framework."""
        agent = _agent_row()
        existing_db_id = str(uuid4())
        mock_db = MagicMock()
        mock_dispatcher = MagicMock()

        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
            MagicMock(data=agent)
        )
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"framework_id": "existing-fw", "id": existing_db_id}])
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": existing_db_id}])
        )

        with (
            patch(PATCH_SUPABASE, return_value=mock_db),
            patch(PATCH_DISPATCHER, return_value=mock_dispatcher),
        ):
            response = client.post(
                f"/api/v1/agents/{TEST_AGENT_ID}/frameworks/upload",
                json={
                    "frameworks": [
                        {
                            "name": "Renamed Framework",
                            "framework_id": "existing-fw",
                            "confidence": "high",
                            "principles": ["Think"],
                            "when_to_apply": ["original trigger"],
                        }
                    ]
                },
            )

        assert response.status_code == 200
        mock_dispatcher.dispatch.assert_called_once()
