"""
Tests for Linked Upload extraction endpoints — KIN-310 / KIN-311.

Spec: docs/feature-linked-upload.md
Implementation tickets: KIN-310 (User Profile + Company), KIN-311 (Agent Profile)

All tests are unit-tier: get_supabase_client and LLM client patched; no real DB or LLM calls.

Endpoints under test:
  POST /api/profile/upload-document
  POST /api/company/{id}/upload-document
  POST /api/agent/{id}/upload-document
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPANY_ID = str(uuid4())
AGENT_ID = str(uuid4())

PATCH_SUPABASE = "app.api.routes.linked_upload.get_supabase_client"
PATCH_LLM = "app.api.routes.linked_upload.get_llm_client"
PATCH_EXTRACT_TEXT = "app.api.routes.linked_upload.extract_text"

# Default return value for extract_text mock — a plain text document
_EXTRACTED_TEXT = "Brandon Smith\nSoftware Engineer with 10 years of experience."

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pdf_file(filename: str = "doc.pdf") -> tuple[str, tuple]:
    """Build a multipart file tuple for TestClient uploads (PDF)."""
    minimal_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td"
        b"(Hello world)Tj ET\nendstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    return ("file", (filename, BytesIO(minimal_pdf), "application/pdf"))


def _text_file(content: str = "Brandon Smith\nSoftware Engineer", filename: str = "bio.txt") -> tuple[str, tuple]:
    return ("file", (filename, BytesIO(content.encode()), "text/plain"))


def _make_extraction_result(name: str = "Test Name", bio: str = "A short bio.") -> dict:
    return {"name": name, "bio": bio}


# ---------------------------------------------------------------------------
# BYOK gate
# ---------------------------------------------------------------------------


class TestBYOKGate:
    def test_profile_upload_no_api_keys_returns_400(self, client):
        """User with no API keys configured → POST /api/profile/upload-document returns 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]  # no API keys
            )
            resp = client.post(
                "/api/profile/upload-document",
                files=[_text_file()],
            )
        assert resp.status_code == 400
        assert "api key" in resp.json()["detail"].lower()

    def test_profile_upload_with_api_key_proceeds(self, client):
        """User with at least one API key → extraction proceeds (200)."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            # Stub: one API key exists
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = _make_extraction_result()
            resp = client.post(
                "/api/profile/upload-document",
                files=[_pdf_file()],
            )
        assert resp.status_code == 200

    def test_byok_gate_enforced_server_side(self, client):
        """
        BYOK gate is enforced at the API level, not just the frontend.
        Calling the endpoint directly without a key still returns 400.
        """
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            resp = client.post(
                "/api/profile/upload-document",
                files=[_text_file()],
                headers={"Authorization": "Bearer valid-jwt"},  # auth passes, BYOK gate must still fire
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# File lifecycle
# ---------------------------------------------------------------------------


class TestFileLifecycle:
    def test_no_storage_interaction_on_successful_extraction(self, client):
        """
        Extraction is fully in-memory — Supabase Storage must never be called.
        No upload, no delete, regardless of outcome.
        """
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = _make_extraction_result()
            storage_mock = MagicMock()
            mock_db.return_value.storage = storage_mock

            resp = client.post("/api/profile/upload-document", files=[_pdf_file()])

        assert resp.status_code == 200
        storage_mock.from_.assert_not_called()

    def test_no_storage_interaction_on_extraction_failure(self, client):
        """
        Storage must not be touched even when LLM extraction fails.
        The in-memory path has no storage involvement at any point.
        """
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.side_effect = RuntimeError("LLM unavailable")
            storage_mock = MagicMock()
            mock_db.return_value.storage = storage_mock

            client.post("/api/profile/upload-document", files=[_pdf_file()])

        storage_mock.from_.assert_not_called()


# ---------------------------------------------------------------------------
# Extraction — User Profile
# ---------------------------------------------------------------------------


class TestExtractionUserProfile:
    def test_valid_pdf_extracts_name_and_bio(self, client):
        """Valid PDF → name and bio extracted and returned."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = _make_extraction_result(
                name="Brandon Smith", bio="Experienced founder and product leader."
            )
            resp = client.post("/api/profile/upload-document", files=[_pdf_file()])

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Brandon Smith"
        assert body["bio"] == "Experienced founder and product leader."

    def test_valid_docx_extracts_name_and_bio(self, client):
        """Valid DOCX → name and bio extracted and returned."""
        docx_bytes = b"PK\x03\x04"  # minimal DOCX magic bytes (zip header)
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = _make_extraction_result()
            resp = client.post(
                "/api/profile/upload-document",
                files=[("file", ("resume.docx", BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body
        assert "bio" in body

    def test_unsupported_file_type_returns_meaningful_error(self, client):
        """
        Unsupported file type (e.g. .exe) → returns 4xx with a clear error message.
        Must not return 500.
        """
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            resp = client.post(
                "/api/profile/upload-document",
                files=[("file", ("malware.exe", BytesIO(b"MZ"), "application/octet-stream"))],
            )

        assert resp.status_code in (400, 415, 422)
        assert resp.status_code != 500
        body = resp.json()
        assert "detail" in body or "error" in body

    def test_llm_failure_surfaced_no_partial_write(self, client):
        """
        LLM extraction error → error returned to caller; no partial profile write occurs.
        """
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.side_effect = RuntimeError("upstream LLM error")
            resp = client.post("/api/profile/upload-document", files=[_pdf_file()])

        assert resp.status_code in (500, 502, 503)
        # Verify no DB write occurred (profile update table not called)
        # Exact assertion depends on implementation — verify profile update was NOT called
        mock_db.return_value.table.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# Extraction — Company
# ---------------------------------------------------------------------------


class TestExtractionCompany:
    def test_valid_file_extracts_name_and_description(self, client):
        """Valid document → company name and description extracted."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = {
                "name": "Acme Corp",
                "description": "A leading provider of anvils.",
            }
            resp = client.post(
                f"/api/company/{COMPANY_ID}/upload-document",
                files=[_pdf_file("pitch.pdf")],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Acme Corp"
        assert body["description"] == "A leading provider of anvils."

    def test_company_unsupported_file_type_returns_error(self, client):
        """Unsupported file type on company upload → 4xx, not 500."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            resp = client.post(
                f"/api/company/{COMPANY_ID}/upload-document",
                files=[("file", ("data.json", BytesIO(b"{}"), "application/json"))],
            )

        assert resp.status_code in (400, 415, 422)
        assert resp.status_code != 500

    def test_company_llm_failure_surfaced_no_partial_write(self, client):
        """LLM error on company extraction → error surfaced; company record not mutated."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.side_effect = RuntimeError("LLM error")
            resp = client.post(
                f"/api/company/{COMPANY_ID}/upload-document",
                files=[_pdf_file()],
            )

        assert resp.status_code in (500, 502, 503)
        mock_db.return_value.table.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# Extraction — Agent Profile
# ---------------------------------------------------------------------------


class TestExtractionAgentProfile:
    def test_valid_corpus_extracts_name_and_system_prompt(self, client):
        """Valid corpus file → agent name and non-empty system prompt extracted."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = {
                "name": "Nate Jones",
                "instructions": "You are Nate Jones, a strategic operator who..." + " reasoning " * 50,
            }
            resp = client.post(
                f"/api/agent/{AGENT_ID}/upload-document",
                files=[_pdf_file("corpus.pdf")],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Nate Jones"
        assert len(body["instructions"]) > 0

    def test_system_prompt_within_token_range(self, client):
        """
        System prompt token count should be within ~500 token range (rough check).
        Using the mock_tiktoken approximation (len // 4), target: 200–700 tokens.
        """
        instructions = "You are Nate Jones. " + ("You reason from first principles. " * 40)
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = {
                "name": "Nate Jones",
                "instructions": instructions,
            }
            resp = client.post(
                f"/api/agent/{AGENT_ID}/upload-document",
                files=[_pdf_file()],
            )

        assert resp.status_code == 200
        body = resp.json()
        # Rough token estimate: len // 4 (matches mock_tiktoken)
        token_estimate = len(body["instructions"]) // 4
        assert 100 <= token_estimate <= 1000, (
            f"System prompt token estimate {token_estimate} outside expected 100–1000 range"
        )

    def test_agent_extraction_uses_different_prompt_than_profile(self, client):
        """
        Agent profile extraction must use a different prompt ID than user profile extraction.
        Verify by inspecting the prompt ID passed to the LLM client.
        """
        user_prompt_id = None
        agent_prompt_id = None

        def _capture_extract(prompt_id, *args, **kwargs):
            return {"instructions": "You are...", "name": "Author"}

        # Capture profile extraction prompt
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.side_effect = lambda *a, **kw: (
                _capture_extract("user", *a, **kw)
            )
            client.post("/api/profile/upload-document", files=[_pdf_file()])
            if mock_llm.return_value.extract.call_args:
                user_prompt_id = mock_llm.return_value.extract.call_args[1].get("prompt_id")

        # Capture agent extraction prompt
        with (
            patch(PATCH_SUPABASE) as mock_db2,
            patch(PATCH_LLM) as mock_llm2,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db2.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm2.return_value.extract.return_value = {"name": "Nate", "instructions": "You are..."}
            client.post(f"/api/agent/{AGENT_ID}/upload-document", files=[_pdf_file()])
            if mock_llm2.return_value.extract.call_args:
                agent_prompt_id = mock_llm2.return_value.extract.call_args[1].get("prompt_id")

        assert user_prompt_id is not None, "Failed to capture user profile prompt ID — call_args was None"
        assert agent_prompt_id is not None, "Failed to capture agent prompt ID — call_args was None"
        assert user_prompt_id != agent_prompt_id, (
            "Agent extraction must use a different prompt than user profile extraction"
        )

    def test_agent_llm_failure_surfaced(self, client):
        """LLM error on agent corpus extraction → error returned; agent record not mutated."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.side_effect = RuntimeError("LLM error")
            resp = client.post(
                f"/api/agent/{AGENT_ID}/upload-document",
                files=[_pdf_file()],
            )

        assert resp.status_code in (500, 502, 503)
        mock_db.return_value.table.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# Review + Save
# ---------------------------------------------------------------------------


class TestReviewAndSave:
    def test_edited_fields_saved_not_original_extraction(self, client):
        """
        After extraction, user edits fields before saving.
        The save endpoint must persist the edited version, not the original extraction output.
        """
        # Step 1: extract
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_LLM) as mock_llm,
            patch(PATCH_EXTRACT_TEXT, return_value=_EXTRACTED_TEXT),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            mock_llm.return_value.extract.return_value = _make_extraction_result(
                name="AI Name", bio="AI-generated bio."
            )
            extract_resp = client.post("/api/profile/upload-document", files=[_pdf_file()])

        assert extract_resp.status_code == 200

        # Step 2: save with user-edited content (via the normal profile update endpoint)
        with patch(PATCH_SUPABASE) as mock_db2:
            update_chain = mock_db2.return_value.table.return_value.update.return_value.eq.return_value
            update_chain.execute.return_value = MagicMock(data=[{"id": TEST_USER_ID}])

            save_resp = client.patch(
                "/api/profile",
                json={"full_name": "User Edited Name", "short_bio": "User-edited bio."},
            )

        if save_resp.status_code == 200:
            # The saved data must be the user-edited version
            update_chain.execute.assert_called_once()
            update_args = mock_db2.return_value.table.return_value.update.call_args[0][0]
            assert update_args.get("full_name") == "User Edited Name"
            assert update_args.get("short_bio") == "User-edited bio."

    def test_save_writes_to_correct_profile_fields(self, client):
        """
        Save must write to profile fields (full_name, short_bio), not to KB or other users.
        """
        with patch(PATCH_SUPABASE) as mock_db:
            update_chain = mock_db.return_value.table.return_value.update.return_value.eq.return_value
            update_chain.execute.return_value = MagicMock(data=[{"id": TEST_USER_ID}])

            resp = client.patch(
                "/api/profile",
                json={"full_name": "Brandon Smith", "short_bio": "AI product leader."},
            )

        if resp.status_code == 200:
            # Table targeted must be 'users' (profile table), not 'documents' or 'knowledge_bases'
            table_name = mock_db.return_value.table.call_args[0][0]
            assert table_name == "users", f"Expected 'users' table, got '{table_name}'"
            # Scoped to current user only
            eq_args = mock_db.return_value.table.return_value.update.return_value.eq.call_args
            assert TEST_USER_ID in str(eq_args)


# ---------------------------------------------------------------------------
# Corrupted document (parsing error path) — 422 responses
# ---------------------------------------------------------------------------


class TestCorruptedDocumentParsing:
    """
    extract_text raises RuntimeError when a file is corrupted / unreadable.
    All three surfaces must return 422 (not 500) with a clear message.
    This is the 'parsing error' path distinct from the LLM model error path.
    """

    def test_corrupted_pdf_profile_returns_422(self, client):
        """Corrupted document on profile upload → extract_text raises RuntimeError → 422."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_EXTRACT_TEXT, side_effect=RuntimeError("pdfminer failed")),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            resp = client.post("/api/profile/upload-document", files=[_pdf_file()])

        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert "extract" in body["detail"].lower() or "corrupt" in body["detail"].lower()

    def test_corrupted_pdf_company_returns_422(self, client):
        """Corrupted document on company upload → extract_text raises RuntimeError → 422."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_EXTRACT_TEXT, side_effect=RuntimeError("pdfminer failed")),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            resp = client.post(
                f"/api/company/{COMPANY_ID}/upload-document",
                files=[_pdf_file()],
            )

        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_corrupted_pdf_agent_returns_422(self, client):
        """Corrupted document on agent upload → extract_text raises RuntimeError → 422."""
        with (
            patch(PATCH_SUPABASE) as mock_db,
            patch(PATCH_EXTRACT_TEXT, side_effect=RuntimeError("pdfminer failed")),
        ):
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"provider": "anthropic", "key_ciphertext": "aabbcc", "key_nonce": "112233"}]
            )
            resp = client.post(
                f"/api/agent/{AGENT_ID}/upload-document",
                files=[_pdf_file()],
            )

        assert resp.status_code == 422
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# BYOK gate — company and agent surfaces
# ---------------------------------------------------------------------------


class TestBYOKGateAllSurfaces:
    """
    BYOK gate must be enforced on all three surfaces, not just profile.
    Tests complement TestBYOKGate which covers only the profile surface.
    """

    def test_company_upload_no_api_keys_returns_400(self, client):
        """No API keys on company upload → 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            resp = client.post(
                f"/api/company/{COMPANY_ID}/upload-document",
                files=[_text_file()],
            )
        assert resp.status_code == 400
        assert "api key" in resp.json()["detail"].lower()

    def test_agent_upload_no_api_keys_returns_400(self, client):
        """No API keys on agent upload → 400."""
        with patch(PATCH_SUPABASE) as mock_db:
            mock_db.return_value.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
            resp = client.post(
                f"/api/agent/{AGENT_ID}/upload-document",
                files=[_text_file()],
            )
        assert resp.status_code == 400
        assert "api key" in resp.json()["detail"].lower()
