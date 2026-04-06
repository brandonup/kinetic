"""
Tests for scrape sources CRUD + manual run endpoints — KIN-463.

All Supabase calls are mocked. Uses client fixture from conftest.py.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

PATCH_TARGET = "app.api.routes.scrape_sources._get_client"

TEST_USER_ID = "test-user-00000000-0000-0000-0000-000000000001"
KB_ID = str(uuid4())
SOURCE_ID = str(uuid4())


def _kb_row(kb_id=KB_ID, user_id=TEST_USER_ID):
    return {"id": kb_id, "user_id": user_id}


def _byok_row():
    return {"id": str(uuid4()), "user_id": TEST_USER_ID, "provider": "openai"}


def _source_row(source_id=SOURCE_ID, user_id=TEST_USER_ID, **overrides):
    row = {
        "id": source_id,
        "knowledge_base_id": KB_ID,
        "user_id": user_id,
        "source_type": "rss",
        "source_url": "https://example.com/feed.xml",
        "frequency": "daily",
        "is_active": True,
        "last_scraped_at": None,
        "next_run_at": "2026-04-06T12:00:00+00:00",
        "last_error": None,
        "consecutive_failures": 0,
        "created_at": "2026-04-05T12:00:00+00:00",
        "updated_at": "2026-04-05T12:00:00+00:00",
    }
    row.update(overrides)
    return row


def _mock_db_for_create(kb_exists=True, byok_exists=True):
    """Build a mock Supabase client for the create flow."""
    mock = MagicMock()

    def _table_side_effect(table_name):
        chain = MagicMock()
        if table_name == "knowledge_bases":
            chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data=_kb_row() if kb_exists else None
            )
        elif table_name == "user_api_keys":
            chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
                data=_byok_row() if byok_exists else None
            )
        elif table_name == "scrape_sources":
            # insert returns the row
            chain.insert.return_value.execute.return_value = MagicMock(
                data=[_source_row()]
            )
            # re-fetch with safe columns
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=_source_row()
            )
        return chain

    mock.table.side_effect = _table_side_effect
    return mock


# ---------------------------------------------------------------------------
# POST /api/v1/scrape-sources
# ---------------------------------------------------------------------------


class TestCreateScrapeSource:
    def test_create_success_201(self, client):
        mock_db = _mock_db_for_create()
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/scrape-sources",
                json={
                    "knowledge_base_id": KB_ID,
                    "source_type": "rss",
                    "source_url": "https://example.com/feed.xml",
                    "frequency": "daily",
                },
            )
        assert response.status_code == 201
        data = response.json()
        assert data["source_type"] == "rss"
        assert "credential_ciphertext" not in data
        assert "credential_nonce" not in data

    def test_create_no_byok_key_400(self, client):
        mock_db = _mock_db_for_create(byok_exists=False)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/scrape-sources",
                json={
                    "knowledge_base_id": KB_ID,
                    "source_type": "rss",
                    "source_url": "https://example.com/feed.xml",
                    "frequency": "daily",
                },
            )
        assert response.status_code == 400
        assert "OpenAI API key required" in response.json()["detail"]

    def test_create_non_owned_kb_404(self, client):
        mock_db = _mock_db_for_create(kb_exists=False)
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(
                "/api/v1/scrape-sources",
                json={
                    "knowledge_base_id": KB_ID,
                    "source_type": "rss",
                    "source_url": "https://example.com/feed.xml",
                    "frequency": "daily",
                },
            )
        assert response.status_code == 404

    def test_create_invalid_source_type_422(self, client):
        """Invalid source_type → 422 validation error."""
        response = client.post(
            "/api/v1/scrape-sources",
            json={
                "knowledge_base_id": KB_ID,
                "source_type": "invalid",
                "source_url": "https://example.com/feed.xml",
                "frequency": "daily",
            },
        )
        assert response.status_code == 422

    def test_create_invalid_url_422(self, client):
        """Invalid URL → 422 validation error."""
        response = client.post(
            "/api/v1/scrape-sources",
            json={
                "knowledge_base_id": KB_ID,
                "source_type": "rss",
                "source_url": "not-a-url",
                "frequency": "daily",
            },
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/scrape-sources
# ---------------------------------------------------------------------------


class TestListScrapeSources:
    def test_list_returns_own_sources(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[_source_row()]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(
                f"/api/v1/scrape-sources?knowledge_base_id={KB_ID}"
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "credential_ciphertext" not in data[0]

    def test_list_empty(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=[]
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.get(
                f"/api/v1/scrape-sources?knowledge_base_id={KB_ID}"
            )
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# PATCH /api/v1/scrape-sources/{id}
# ---------------------------------------------------------------------------


class TestUpdateScrapeSource:
    def test_update_frequency(self, client):
        mock_db = MagicMock()
        # Ownership check
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=_source_row()
        )
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[_source_row(frequency="weekly")]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=_source_row(frequency="weekly")
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/scrape-sources/{SOURCE_ID}",
                json={"frequency": "weekly"},
            )
        assert response.status_code == 200

    def test_update_non_owned_404(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.patch(
                f"/api/v1/scrape-sources/{SOURCE_ID}",
                json={"frequency": "weekly"},
            )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/scrape-sources/{id}
# ---------------------------------------------------------------------------


class TestDeleteScrapeSource:
    def test_delete_success_204(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=_source_row()
        )
        mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/scrape-sources/{SOURCE_ID}")
        assert response.status_code == 204

    def test_delete_non_owned_404(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.delete(f"/api/v1/scrape-sources/{SOURCE_ID}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/scrape-sources/{id}/run
# ---------------------------------------------------------------------------


class TestRunScrapeSource:
    def test_run_non_owned_404(self, client):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        with patch(PATCH_TARGET, return_value=mock_db):
            response = client.post(f"/api/v1/scrape-sources/{SOURCE_ID}/run")
        assert response.status_code == 404
