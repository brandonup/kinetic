"""
Pytest configuration and shared fixtures for Kinetic API tests.

Schema source of truth: docs/db-schema-spec.md
Auth pattern: Supabase Auth manages auth.users; handle_new_user() trigger creates public.users rows.
JWT verification: SupabaseJWTVerifier checks 'sub' claim → user id.

Two fixture tiers:
  - Unit (no DB): dependency_overrides bypass JWT + DB. Default for all tests.
  - Integration (real Supabase): set KINETIC_RUN_INTEGRATION_TESTS=1 to enable.
"""

import os

# ---------------------------------------------------------------------------
# Required env var injection — must happen before any app module imports.
# pydantic-settings reads env at import time; setdefault avoids clobbering
# real values when running in a populated environment.
# ---------------------------------------------------------------------------
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("API_KEY_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")  # 32 zero-bytes, base64 (43 A's + =)
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

# ---------------------------------------------------------------------------
# Sandbox workaround: prevent pydantic-settings from stat-ing .env files.
# The sandbox denies os.stat() on .env* paths. Override the config module's
# ENV_FILE_PATH to a non-existent path BEFORE Settings() is instantiated.
# ---------------------------------------------------------------------------
import pathlib as _pathlib

_original_is_file = _pathlib.Path.is_file


def _safe_is_file(self, *args, **kwargs):
    """Return False for .env files to avoid sandbox PermissionError."""
    if ".env" in self.name:
        return False
    return _original_is_file(self, *args, **kwargs)


_pathlib.Path.is_file = _safe_is_file

from datetime import datetime, timedelta, timezone
from typing import Generator
from uuid import uuid4

import jwt
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Must match SUPABASE_JWT_SECRET set above so SupabaseJWTVerifier can verify test tokens
TEST_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]
TEST_USER_ID = str(uuid4())
TEST_ADMIN_ID = str(uuid4())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _make_jwt(
    user_id: str,
    exp_delta: timedelta = timedelta(hours=1),
) -> str:
    """Mint a test Supabase-style JWT (HS256, audience='authenticated')."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def valid_user_token() -> str:
    """Valid JWT for a regular user (role='user' in public.users)."""
    return _make_jwt(TEST_USER_ID)


@pytest.fixture
def valid_admin_token() -> str:
    """Valid JWT for an admin user (role='admin' in public.users)."""
    return _make_jwt(TEST_ADMIN_ID)


@pytest.fixture
def expired_token() -> str:
    """JWT that is already expired."""
    return _make_jwt(TEST_USER_ID, exp_delta=timedelta(seconds=-1))


@pytest.fixture
def tampered_token(valid_user_token: str) -> str:
    """Valid JWT with the signature corrupted (last 4 chars replaced)."""
    parts = valid_user_token.split(".")
    parts[-1] = parts[-1][:-4] + "XXXX"
    return ".".join(parts)


# ---------------------------------------------------------------------------
# App client — unit-tier (dependency overrides, no real DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> Generator:
    """
    TestClient with get_current_user overridden to return TEST_USER_ID.
    No real Supabase connection needed. Use for session + role tests.
    """
    from fastapi.testclient import TestClient

    from app.auth.deps import CurrentUser, get_current_user
    from app.main import app

    async def _override_user() -> CurrentUser:
        return CurrentUser(user_id=TEST_USER_ID)

    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client() -> Generator:
    """
    TestClient with both get_current_user and require_admin overridden to return TEST_ADMIN_ID.
    Used for admin-role endpoint tests.
    """
    from fastapi.testclient import TestClient

    from app.auth.deps import CurrentUser, get_current_user, require_admin
    from app.main import app

    async def _override_admin() -> CurrentUser:
        return CurrentUser(user_id=TEST_ADMIN_ID)

    app.dependency_overrides[get_current_user] = _override_admin
    app.dependency_overrides[require_admin] = _override_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def raw_client() -> Generator:
    """
    TestClient with NO dependency overrides.
    Used for JWT validation tests (expired, tampered) where the real
    SupabaseJWTVerifier must run. Works because SUPABASE_JWT_SECRET == TEST_JWT_SECRET.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Integration-tier marker — opt-in only
# ---------------------------------------------------------------------------
# Set KINETIC_RUN_INTEGRATION_TESTS=1 to run tests that require a real Supabase instance.
# Registration + OAuth tests need the handle_new_user() trigger and auth.users table.

skip_integration = pytest.mark.skipif(
    os.environ.get("KINETIC_RUN_INTEGRATION_TESTS") != "1",
    reason="Set KINETIC_RUN_INTEGRATION_TESTS=1 to run integration tests (requires live Supabase)",
)


# ---------------------------------------------------------------------------
# Ingestion fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_pdf() -> bytes:
    """Minimal valid PDF bytes for ingestion tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td"
        b"(Hello world)Tj ET\nendstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )


@pytest.fixture(autouse=True)
def mock_gemini_token_counter():
    """
    Mock EmbeddingService.count_tokens to avoid Gemini API calls in tests.
    Uses len(text) // 4 as token count approximation (same as old tiktoken mock).
    KIN-467: replaced tiktoken mock with Gemini count_tokens mock.
    """
    from unittest.mock import patch

    with patch(
        "app.services.ingestion.embedder.EmbeddingService.count_tokens",
        lambda self, text: max(1, len(text) // 4),
    ):
        yield


@pytest.fixture
def large_document() -> bytes:
    """
    Text document that exceeds the 1M token ingestion limit.
    With mock count_tokens (len // 4 tokens), needs >4M chars.
    4,500,000 chars → ~1,125,000 mock tokens.
    """
    word = "The quick brown fox jumps over the lazy dog. " * 500
    return (word * 200).encode("utf-8")


@pytest.fixture
def oversized_file() -> bytes:
    """Binary blob that exceeds the 25 MB upload limit."""
    return b"x" * (25 * 1024 * 1024 + 1)


@pytest.fixture
def mock_embedding_service():
    """Patches EmbeddingService.embed_batch to return fake 3072-dim vectors (KIN-476)."""
    from unittest.mock import patch

    def _make_embeddings(texts):
        return [[0.1] * 3072 for _ in texts]

    with patch(
        "app.services.ingestion.embedder.EmbeddingService.embed_batch",
        side_effect=_make_embeddings,
    ) as mock:
        yield mock


@pytest.fixture
def db_session():
    """
    Mock Supabase client for ingestion unit tests.
    Stubs the table/insert/update/select chain.
    """
    from unittest.mock import MagicMock

    session = MagicMock()
    _id = str(uuid4())
    session.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": _id}]
    )
    session.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[])
    )
    session.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"project_id": str(uuid4()), "agent_definition_id": None}
    )
    return session


# ---------------------------------------------------------------------------
# RAG retrieval fixtures
# ---------------------------------------------------------------------------


import math as _math
from typing import List as _List, Optional as _Optional


def _make_embedding_fixture(seed: float, dims: int = 16) -> _List[float]:
    """Deterministic unit-normalised embedding for test fixtures (dims=16)."""
    raw = [_math.cos(seed + i * (2 * _math.pi / dims)) for i in range(dims)]
    norm = _math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


@pytest.fixture
def seeded_chunks():
    """
    Factory fixture that returns a (mock_supabase, chunk_rows) pair.

    Usage:
        mock_supabase, rows = seeded_chunks(
            project_id=some_uuid,
            similarities=[0.8, 0.5, 0.2],
            document_ids=None,       # auto-generated if not supplied
        )

    The mock_supabase.rpc(...).execute() returns the chunk rows formatted
    as if the match_chunks RPC responded (id, document_id, text, embedding,
    chunk_index, section_path, page_range, similarity, document_title, document_type).
    """
    from unittest.mock import MagicMock

    def _factory(
        project_id,
        similarities: _List[float],
        document_ids: _Optional[_List[str]] = None,
    ):
        rows = []
        for i, sim in enumerate(similarities):
            doc_id = document_ids[i] if document_ids and i < len(document_ids) else str(uuid4())
            rows.append(
                {
                    "id": str(uuid4()),
                    "document_id": doc_id,
                    "text": f"chunk text {i}",
                    "embedding": _make_embedding_fixture(float(i) * 1.0),
                    "chunk_index": i,
                    "section_path": f"§{i + 1}",
                    "page_range": str(i + 1),
                    "similarity": sim,
                    "document_title": f"Test Document {i}",
                    "document_type": "text/plain",
                }
            )

        mock_supabase = MagicMock()
        # Wire RPC path (match_chunks) to return our rows
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=rows)
        return mock_supabase, rows

    return _factory
