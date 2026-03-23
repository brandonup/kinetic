"""
Tests for Linked Upload — KIN-298.

Scaffolded by Jìan (KIN-298). Activated by a future Jìan Sprint 5 coverage ticket
once Dinesh ships Sprint 5 Linked Upload implementations.

Spec ref: docs/feature-linked-upload.md
          docs/specs/active-memory-spec.md (§ BYOK gate)

Endpoint: POST /api/v1/upload/extract
  surface = "user_profile" | "company" | "agent"

Three surfaces:
  - user_profile: extracts name + bio (max 10MB)
  - company: extracts company name + description (max 25MB)
  - agent: extracts agent name + instructions (max 25MB)

Critical invariant: uploaded file is DISCARDED after extraction — never persisted.
"""

import io
import pytest

SKIP_REASON = "Blocked — waiting for Sprint 5 Linked Upload implementation (Dinesh)"

FILE_SIZE_LIMIT_PROFILE = 10 * 1024 * 1024   # 10MB
FILE_SIZE_LIMIT_COMPANY = 25 * 1024 * 1024   # 25MB
FILE_SIZE_LIMIT_AGENT = 25 * 1024 * 1024     # 25MB

SUPPORTED_FORMATS_PROFILE = {".pdf", ".docx", ".doc", ".txt"}
SUPPORTED_FORMATS_COMPANY = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md"}
SUPPORTED_FORMATS_AGENT = {".pdf", ".docx", ".doc", ".txt", ".md"}


def fake_pdf_bytes(size_bytes: int = 1024) -> bytes:
    """Return a minimal fake PDF payload for upload testing."""
    return b"%PDF-1.4 fake content" + b"X" * max(0, size_bytes - 20)


# ---------------------------------------------------------------------------
# User Profile surface
# ---------------------------------------------------------------------------

class TestUserProfileUpload:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_returns_name_and_bio_fields(self, auth_client):
        """Successful upload returns extracted name and generated bio."""
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
            files={"file": ("resume.pdf", io.BytesIO(fake_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "bio" in data

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_name_null_when_unextractable(self, auth_client):
        """If name cannot be extracted, name field is null (not an error)."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_bio_present_even_when_name_null(self, auth_client):
        """Bio is generated from document content regardless of whether name was extracted."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_bio_max_1000_chars(self, auth_client):
        """Generated bio must not exceed 1000 characters."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_key_required(self, auth_client):
        """Returns 402 if the user has no BYOK key configured."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_not_persisted_after_extraction(self, auth_client):
        """After successful extraction, no file is stored in Supabase Storage."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_unsupported_format_rejected(self, auth_client):
        """Uploading a .zip file returns a format validation error."""
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
            files={"file": ("archive.zip", io.BytesIO(b"PK fake zip"), "application/zip")},
        )
        assert resp.status_code in (400, 422)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_exceeds_10mb_rejected(self, auth_client):
        """Files larger than 10MB return a size limit error for user_profile surface."""
        oversized = fake_pdf_bytes(FILE_SIZE_LIMIT_PROFILE + 1)
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
            files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert resp.status_code in (400, 413)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_result_not_auto_saved_to_profile(self, auth_client):
        """Extraction result is returned for review only — profile fields not updated until user saves."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_pdf_format_accepted(self, auth_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_txt_format_accepted(self, auth_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_docx_format_accepted(self, auth_client):
        ...


# ---------------------------------------------------------------------------
# Company surface
# ---------------------------------------------------------------------------

class TestCompanyUpload:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_returns_company_name_and_description(self, auth_client):
        """Successful upload returns extracted company_name and description."""
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "company"},
            files={"file": ("deck.pdf", io.BytesIO(fake_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "company_name" in data
        assert "description" in data

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_description_max_1000_chars(self, auth_client):
        """Generated company description must not exceed 1000 characters."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_company_name_null_when_ambiguous(self, auth_client):
        """company_name is null when document doesn't clearly identify a company."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_exceeds_25mb_rejected(self, auth_client):
        oversized = fake_pdf_bytes(FILE_SIZE_LIMIT_COMPANY + 1)
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "company"},
            files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert resp.status_code in (400, 413)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_pptx_format_accepted(self, auth_client):
        """PowerPoint files are accepted for company surface."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_md_format_accepted(self, auth_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_key_required(self, auth_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_discarded_after_extraction(self, auth_client):
        ...


# ---------------------------------------------------------------------------
# Agent Profile surface
# ---------------------------------------------------------------------------

class TestAgentProfileUpload:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_returns_agent_name_and_instructions(self, auth_client):
        """Successful upload returns extracted agent_name and generated instructions."""
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "agent"},
            files={"file": ("corpus.pdf", io.BytesIO(fake_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_name" in data
        assert "instructions" in data

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_instructions_begins_with_you_are(self, auth_client):
        """Generated system prompt must begin with 'You are [name]...' per the prompt spec."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_instructions_300_to_500_tokens(self, auth_client):
        """Generated instructions are 300–500 tokens (character proxy: 1200–2000 chars)."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_agent_name_null_when_no_clear_author(self, auth_client):
        """agent_name is null when no identifiable primary author."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_instructions_generated_even_when_name_null(self, auth_client):
        """System prompt is still generated even if agent_name is null."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_multi_author_document_name_is_most_prominent(self, auth_client):
        """For multi-author documents, agent_name is the most prominent author."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_short_document_returns_best_effort_with_note(self, auth_client):
        """Very short document returns partial extraction with advisory note."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_exceeds_25mb_rejected(self, auth_client):
        oversized = fake_pdf_bytes(FILE_SIZE_LIMIT_AGENT + 1)
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "agent"},
            files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert resp.status_code in (400, 413)

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_key_required(self, auth_client):
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_file_discarded_after_extraction(self, auth_client):
        """No storage artifact left after extraction — file not saved to Supabase Storage."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_result_not_auto_saved_to_agent(self, auth_client):
        """Extraction result returned for user review — AgentDefinition fields not updated until user saves."""
        ...


# ---------------------------------------------------------------------------
# Common / cross-surface rules
# ---------------------------------------------------------------------------

class TestLinkedUploadCommon:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_invalid_surface_param_returns_422(self, auth_client):
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "unknown_surface"},
            files={"file": ("doc.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_missing_file_returns_422(self, auth_client):
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
            files={"file": ("doc.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code == 401

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_network_error_during_extraction_returns_error_state(self, auth_client):
        """If LLM call fails mid-extraction, endpoint returns an error — profile fields unmodified."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_empty_file_returns_extraction_error(self, auth_client):
        resp = auth_client.post(
            "/api/v1/upload/extract",
            data={"surface": "user_profile"},
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )
        assert resp.status_code in (400, 422)
