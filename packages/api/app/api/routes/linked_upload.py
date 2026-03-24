"""
Linked Upload extraction endpoints — KIN-310 (profile + company) and KIN-311 (agent).

Endpoints:
  POST /api/profile/upload-document         — extract name + bio from user profile document
  POST /api/company/{company_id}/upload-document — extract name + description from company doc
  POST /api/agent/{agent_id}/upload-document    — extract name + instructions from agent corpus

Extraction is stateless and fully in-memory: receive file → extract text → LLM → return.
No DB writes. No file storage. Caller reviews and saves via normal PATCH endpoints.
BYOK gate: user must have at least one API key. Uses first available key.

Spec: docs/feature-linked-upload.md
Schema ref: docs/db-schema-spec.md §2 (user_api_keys)
Conventions: all Supabase calls in async def use run_in_executor (conventions.md)
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.deps import CurrentUser, get_current_user
from app.db.supabase_client import get_supabase
from app.services.encryption import decrypt_api_key, load_master_key
from app.services.ingestion.extractor import UnsupportedFileTypeError, extract_text
from app.services.llm_client import call_llm
from app.services.prompts import get_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["linked-upload"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROFILE_MAX_SIZE = 10 * 1024 * 1024   # 10 MB
COMPANY_MAX_SIZE = 25 * 1024 * 1024   # 25 MB
AGENT_MAX_SIZE = 25 * 1024 * 1024     # 25 MB

PROFILE_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}
COMPANY_ALLOWED_TYPES = PROFILE_ALLOWED_TYPES | {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "text/markdown",
    "text/x-markdown",
}
AGENT_ALLOWED_TYPES = PROFILE_ALLOWED_TYPES | {
    "text/markdown",
    "text/x-markdown",
}

PROMPT_ID_PROFILE = "generate-user-profile-v1"
PROMPT_ID_COMPANY = "generate-company-profile-v1"
PROMPT_ID_AGENT = "generate-agent-persona-v1"

# Max document text length passed to LLM (chars)
_TEXT_LIMIT_SHORT = 8_000
_TEXT_LIMIT_AGENT = 12_000


# ---------------------------------------------------------------------------
# Patchable helpers (module-level so tests can patch them)
# ---------------------------------------------------------------------------


def get_supabase_client():
    """Return the service-role Supabase client. Module-level for test patching."""
    return get_supabase()


class LinkedUploadExtractor:
    """
    Handles LLM extraction for all three surfaces (profile, company, agent).

    Decrypts the BYOK key internally so tests can mock the whole extract()
    method without touching the encryption service.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    def extract(
        self,
        text: str,
        *,
        prompt_id: str,
        key_row: dict,
        model: str = "gpt-4o-mini",
    ) -> dict:
        """
        Extract structured fields from document text via LLM.

        Args:
            text: Extracted document text.
            prompt_id: Which extraction prompt to use — determines output schema.
            key_row: User API key row with key_ciphertext and key_nonce (DB schema §2).
            model: LiteLLM-compatible model name.

        Returns:
            Dict of extracted fields:
              PROMPT_ID_PROFILE → {"name": str|None, "bio": str|None}
              PROMPT_ID_COMPANY → {"name": str|None, "description": str|None}
              PROMPT_ID_AGENT   → {"name": str|None, "instructions": str|None}

        Raises:
            RuntimeError: LLM call failed.
            ValueError: Unknown prompt_id.
        """
        master_key = load_master_key()
        api_key = decrypt_api_key(
            bytes.fromhex(key_row["key_ciphertext"]),
            bytes.fromhex(key_row["key_nonce"]),
            master_key,
            self._user_id,
        )

        if prompt_id == PROMPT_ID_PROFILE:
            return self._extract_profile(text, api_key, model)
        if prompt_id == PROMPT_ID_COMPANY:
            return self._extract_company(text, api_key, model)
        if prompt_id == PROMPT_ID_AGENT:
            return self._extract_agent(text, api_key, model)
        raise ValueError(f"Unknown prompt_id: {prompt_id!r}")

    # ------------------------------------------------------------------
    # Surface-specific extraction methods
    # ------------------------------------------------------------------

    def _extract_profile(self, text: str, api_key: str, model: str) -> dict:
        snippet = text[:_TEXT_LIMIT_SHORT]

        raw_name = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_PROFILE, "name_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=100,
            timeout=25,
        ).strip()
        name = raw_name if raw_name.lower() != "null" else None

        raw_bio = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_PROFILE, "bio_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=300,
            timeout=25,
        ).strip()
        bio: Optional[str] = raw_bio[:1000] if raw_bio else None

        return {"name": name, "bio": bio}

    def _extract_company(self, text: str, api_key: str, model: str) -> dict:
        snippet = text[:_TEXT_LIMIT_SHORT]

        raw_name = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_COMPANY, "name_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=100,
            timeout=25,
        ).strip()
        name = raw_name if raw_name.lower() != "null" else None

        raw_desc = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_COMPANY, "description_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=300,
            timeout=25,
        ).strip()
        description: Optional[str] = raw_desc[:1000] if raw_desc else None

        return {"name": name, "description": description}

    def _extract_agent(self, text: str, api_key: str, model: str) -> dict:
        snippet = text[:_TEXT_LIMIT_AGENT]

        raw_name = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_AGENT, "name_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=100,
            timeout=25,
        ).strip()
        name = raw_name if raw_name.lower() != "null" else None

        raw_instructions = call_llm(
            messages=[{
                "role": "user",
                "content": get_prompt(PROMPT_ID_AGENT, "instructions_extract") + "\n\n" + snippet,
            }],
            model=model,
            api_key=api_key,
            max_tokens=800,
            timeout=30,
        ).strip()
        instructions: Optional[str] = raw_instructions if raw_instructions else None

        return {"name": name, "instructions": instructions}


def get_llm_client(user_id: str) -> LinkedUploadExtractor:
    """Factory — returns a LinkedUploadExtractor. Module-level for test patching."""
    return LinkedUploadExtractor(user_id=user_id)


# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


async def _get_first_api_key(client, user_id: str) -> Optional[dict]:
    """
    Return the first configured API key row for the user, or None if none configured.
    Selects provider, key_ciphertext, key_nonce for downstream decryption.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("user_api_keys")
            .select("provider, key_ciphertext, key_nonce")
            .eq("user_id", user_id)
            .execute(),
    )
    rows = result.data or []
    return rows[0] if rows else None


def _validate_file(content_type: str, size: int, allowed_types: set, max_size: int) -> None:
    """
    Raise HTTPException(400) if file type or size is not acceptable.
    Called before text extraction to fail fast.
    """
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type!r}. Supported formats: {sorted(allowed_types)}",
        )
    if size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size // (1024 * 1024)} MB.",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/profile/upload-document")
async def upload_profile_document(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Extract name + bio from a user profile document.

    Returns extracted fields — does NOT save to the user's profile.
    Caller reviews in the UI and saves via PATCH /api/v1/profile.

    BYOK gate: user must have at least one API key configured.
    File is discarded after extraction — never stored in DB or KB.
    Accepted formats: PDF, DOCX, DOC, TXT. Max 10 MB.

    Raises:
        HTTPException(400): No API key / unsupported file type / file too large.
        HTTPException(422): Text extraction failed (unreadable document).
        HTTPException(500): LLM call failed.
    """
    client = get_supabase_client()

    # BYOK gate — server-side enforcement (frontend also disables button)
    key_row = await _get_first_api_key(client, current_user.user_id)
    if key_row is None:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Add an API key to use this feature.",
        )

    content = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or "upload.bin"
    _validate_file(content_type, len(content), PROFILE_ALLOWED_TYPES, PROFILE_MAX_SIZE)

    try:
        text = extract_text(content, content_type, filename)
    except UnsupportedFileTypeError:
        raise HTTPException(
            status_code=400,
            detail="Couldn't extract content from this file. Try a different format.",
        )
    except RuntimeError as exc:
        logger.warning("Text extraction failed for %s: %s", filename, exc)
        raise HTTPException(
            status_code=422,
            detail="Couldn't extract content from this file. The document may be corrupted.",
        )

    extractor = get_llm_client(current_user.user_id)
    try:
        return extractor.extract(
            text,
            prompt_id=PROMPT_ID_PROFILE,
            key_row=key_row,
            model="gpt-4o-mini",
        )
    except Exception as exc:
        logger.error("LLM extraction failed for profile: %s", exc)
        raise HTTPException(status_code=500, detail="Extraction failed. Please try again.")


@router.post("/company/{company_id}/upload-document")
async def upload_company_document(
    company_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Extract name + description from a company document.

    Returns extracted fields — does NOT save to the company record.
    Caller reviews in the UI and saves via PATCH /api/v1/companies/{id}.

    BYOK gate: user must have at least one API key configured.
    File is discarded after extraction.
    Accepted formats: PDF, DOCX, DOC, PPTX, PPT, TXT, MD. Max 25 MB.

    Raises:
        HTTPException(400): No API key / unsupported file type / file too large.
        HTTPException(422): Text extraction failed.
        HTTPException(500): LLM call failed.
    """
    client = get_supabase_client()

    key_row = await _get_first_api_key(client, current_user.user_id)
    if key_row is None:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Add an API key to use this feature.",
        )

    content = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or "upload.bin"
    _validate_file(content_type, len(content), COMPANY_ALLOWED_TYPES, COMPANY_MAX_SIZE)

    try:
        text = extract_text(content, content_type, filename)
    except UnsupportedFileTypeError:
        raise HTTPException(
            status_code=400,
            detail="Couldn't extract content from this file. Try a different format.",
        )
    except RuntimeError as exc:
        logger.warning("Text extraction failed for %s: %s", filename, exc)
        raise HTTPException(
            status_code=422,
            detail="Couldn't extract content from this file. The document may be corrupted.",
        )

    extractor = get_llm_client(current_user.user_id)
    try:
        return extractor.extract(
            text,
            prompt_id=PROMPT_ID_COMPANY,
            key_row=key_row,
            model="gpt-4o-mini",
        )
    except Exception as exc:
        logger.error("LLM extraction failed for company: %s", exc)
        raise HTTPException(status_code=500, detail="Extraction failed. Please try again.")


@router.post("/agent/{agent_id}/upload-document")
async def upload_agent_document(
    agent_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Extract name + system prompt (instructions) from an agent corpus document.

    Returns extracted fields — does NOT save to the agent definition.
    Caller reviews in the UI and saves via PATCH on the agent profile.

    BYOK gate: user must have at least one API key configured.
    File is discarded after extraction — not added to KB.
    Accepted formats: PDF, DOCX, DOC, TXT, MD. Max 25 MB.

    Raises:
        HTTPException(400): No API key / unsupported file type / file too large.
        HTTPException(422): Text extraction failed.
        HTTPException(500): LLM call failed.
    """
    client = get_supabase_client()

    key_row = await _get_first_api_key(client, current_user.user_id)
    if key_row is None:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Add an API key to use this feature.",
        )

    content = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or "upload.bin"
    _validate_file(content_type, len(content), AGENT_ALLOWED_TYPES, AGENT_MAX_SIZE)

    try:
        text = extract_text(content, content_type, filename)
    except UnsupportedFileTypeError:
        raise HTTPException(
            status_code=400,
            detail="Couldn't extract content from this file. Try a different format.",
        )
    except RuntimeError as exc:
        logger.warning("Text extraction failed for %s: %s", filename, exc)
        raise HTTPException(
            status_code=422,
            detail="Couldn't extract content from this file. The document may be corrupted.",
        )

    extractor = get_llm_client(current_user.user_id)
    try:
        return extractor.extract(
            text,
            prompt_id=PROMPT_ID_AGENT,
            key_row=key_row,
            model="gpt-4o-mini",
        )
    except Exception as exc:
        logger.error("LLM extraction failed for agent: %s", exc)
        raise HTTPException(status_code=500, detail="Extraction failed. Please try again.")
