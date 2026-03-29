"""
Tests for Admin Prompt Debug endpoint — KIN-419.

Covers:
  - Happy path: admin retrieves full prompt for an assistant message
  - 404 when message not found
  - 404 when debug_prompt is null (user message or pre-feature message)
  - 403 for non-admin caller
  - Prompt size computation
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

PATCH_TARGET = "app.api.routes.admin_prompt_debug.get_supabase_client"

MSG_ID = str(uuid4())
CONV_ID = str(uuid4())

SAMPLE_PROMPT = [
    {"role": "system", "content": "You are a helpful assistant.\n\nContext layers here."},
    {"role": "user", "content": "What is authentication?"},
    {"role": "assistant", "content": "Authentication is the process..."},
    {"role": "user", "content": "How do I implement it?"},
]


def _message_row(
    debug_prompt=None,
    role: str = "assistant",
    model: str = "claude-sonnet-4-6",
) -> dict:
    return {
        "id": MSG_ID,
        "conversation_id": CONV_ID,
        "role": role,
        "model": model,
        "debug_prompt": debug_prompt,
    }


class TestGetMessagePrompt:
    def test_returns_full_prompt(self, admin_client):
        """GET /api/v1/admin/messages/{id}/prompt returns debug_prompt with metrics."""
        row = _message_row(debug_prompt=SAMPLE_PROMPT)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=row)

        with patch(PATCH_TARGET, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/messages/{MSG_ID}/prompt")

        assert resp.status_code == 200
        data = resp.json()
        assert data["message_id"] == MSG_ID
        assert data["conversation_id"] == CONV_ID
        assert data["model"] == "claude-sonnet-4-6"
        assert data["role"] == "assistant"
        assert len(data["debug_prompt"]) == 4
        assert data["message_count"] == 4
        assert data["debug_prompt"][0]["role"] == "system"

    def test_prompt_size_chars_computed(self, admin_client):
        """prompt_size_chars is the sum of all message content lengths."""
        row = _message_row(debug_prompt=SAMPLE_PROMPT)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=row)

        with patch(PATCH_TARGET, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/messages/{MSG_ID}/prompt")

        expected_chars = sum(len(m["content"]) for m in SAMPLE_PROMPT)
        assert resp.json()["prompt_size_chars"] == expected_chars

    def test_404_when_message_not_found(self, admin_client):
        """Returns 404 when message ID doesn't exist."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("not found")

        with patch(PATCH_TARGET, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/messages/{str(uuid4())}/prompt")

        assert resp.status_code == 404

    def test_404_when_debug_prompt_is_null(self, admin_client):
        """Returns 404 when message exists but debug_prompt is null."""
        row = _message_row(debug_prompt=None)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=row)

        with patch(PATCH_TARGET, return_value=mock_db):
            resp = admin_client.get(f"/api/v1/admin/messages/{MSG_ID}/prompt")

        assert resp.status_code == 404

    def test_403_for_non_admin(self, client):
        """Returns 403 for non-admin users."""
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app

        async def _raise_auth_error():
            raise AuthorizationError()

        app.dependency_overrides[require_admin] = _raise_auth_error
        try:
            resp = client.get(f"/api/v1/admin/messages/{MSG_ID}/prompt")
        finally:
            app.dependency_overrides.pop(require_admin, None)
        assert resp.status_code == 403
