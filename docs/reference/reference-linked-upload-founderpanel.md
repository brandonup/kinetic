# Reference Implementation: Linked Upload (from FounderPanel)

**Purpose:** This document contains the actual FounderPanel code that implements the upload → extract → LLM generate → review pattern. The team should use this as the starting template for Kinetic's Linked Upload feature across all three profile pages (User, Company, Agent).

**Source codebase:** `/Users/brandonupchuch/Projects/founder_panel`

---

## What to Reuse vs. What to Change

| Component | Reuse from FounderPanel | Change for Kinetic |
|---|---|---|
| Text extraction (`DocumentProcessor`) | Reuse as-is — PDF, Word, plaintext parsing | Add `.pptx` support for company uploads, add `.md` support |
| Upload → Storage → Extract → LLM → Save flow | Reuse the pattern exactly | Swap Supabase Storage calls if needed |
| LLM call pattern with fallback | Reuse structure | Replace `call_llm()` with LiteLLM, use user's BYOK keys instead of system key |
| Frontend upload component | Reuse validation and UI patterns | Restyle for Kinetic's dark/teak UI, adapt for inline field population instead of onboarding wizard |
| Error classification (`error_code` mapping) | Reuse as-is | Same error codes work |
| Prompt constants + DB fallback pattern | Reuse `_get_prompt_with_fallback()` | Replace prompts with Kinetic-specific versions from `feature-linked-upload.md` |

---

## Backend: Extraction Service

**File:** `backend/app/services/ingestion/processor.py`

```python
"""
Document ingestion processor for corpus documents.
Handles text extraction, chunking, embedding, and Qdrant upload.
"""

import logging
import re
from io import BytesIO
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Service for processing corpus documents."""

    def __init__(self):
        """Initialize document processor."""
        self.chunk_size = 350  # Target tokens
        self.chunk_overlap = 100  # Overlap tokens

    def extract_text(self, file_content: bytes, mime_type: str) -> str:
        """
        Extract text from document.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file

        Returns:
            Extracted text content
        """
        try:
            if mime_type in ["text/plain", "text/markdown", "text/x-markdown", "text/csv"]:
                return file_content.decode("utf-8", errors="ignore")
            elif mime_type == "application/pdf":
                return self._extract_pdf_text(file_content)
            elif mime_type in [
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]:
                return self._extract_word_text(file_content)
            else:
                raise ValueError(f"Unsupported file type: {mime_type}")
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            raise

    def _extract_pdf_text(self, pdf_content: bytes) -> str:
        """Extract text from PDF (prefer pdfplumber; fallback to PyPDF2)."""
        try:
            from app.services.ingestion.parsers.pdf_parser import extract_pdf_text
            return extract_pdf_text(pdf_content)
        except Exception:
            pass

        try:
            from PyPDF2 import PdfReader

            pdf_file = BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text:
                    text_parts.append(f"[Page {page_num}]\n{text}")

            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            raise ValueError(f"Failed to extract PDF text: {str(e)}") from e

    def _extract_word_text(self, word_content: bytes) -> str:
        """Extract text from Word document (.doc or .docx)."""
        try:
            from docx import Document

            doc = Document(BytesIO(word_content))
            text_parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            if not text_parts:
                logger.warning("No text content found in Word document")
                return ""

            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting Word text: {e}")
            raise ValueError(f"Failed to extract Word text: {str(e)}") from e
```

**Kinetic note:** This class is reusable almost verbatim. For Kinetic, add PPTX extraction (using `python-pptx`) and markdown support. The chunking methods on this class are used for KB ingestion, NOT for linked upload — linked upload only uses `extract_text()`.

---

## Backend: Prompt Constants + Fallback Helper

**File:** `backend/app/api/routes/onboarding.py` (lines 53-87)

```python
DEFAULT_USER_NAME_PROMPT = (
    "Extract the person's full name from the LinkedIn or resume content. "
    "Return only the full name, no extra text."
)
DEFAULT_USER_SUMMARY_PROMPT = (
    "Summarize the person's background in 4-6 sentences, focusing on role, "
    "experience, and notable strengths. Return plain text."
)
DEFAULT_STARTUP_SUMMARY_SHORT_PROMPT = (
    "Write a 1-2 sentence elevator pitch for the startup based on the documents."
)
DEFAULT_STARTUP_SUMMARY_LONG_PROMPT = (
    "Write a detailed startup summary in 6-10 sentences based on the documents. "
    "Cover the problem, solution, market, traction, and business model."
)
DEFAULT_COMPANY_NAME_PROMPT = (
    "Suggest a concise company name based on the documents. Return only the name."
)


def _get_prompt_with_fallback(prompts, attr: str, error_message: str, fallback_text: str) -> str:
    prompt_value = getattr(prompts, attr, None) if prompts else None
    if prompt_value:
        return prompt_value
    _log_onboarding_event(
        "prompt.missing",
        {
            "prompt": attr,
            "has_prompts": bool(prompts),
            "fallback_enabled": bool(settings.ALLOW_ONBOARDING_PROMPT_FALLBACK),
        },
    )
    if settings.ALLOW_ONBOARDING_PROMPT_FALLBACK:
        return fallback_text
    raise ValidationError(error_message)
```

**Kinetic note:** Replace these prompts with the Kinetic-specific versions in `feature-linked-upload.md`. The fallback pattern is good — reuse it. Kinetic prompts are:
- `generate-user-name`, `generate-user-bio` (User Profile)
- `generate-company-name`, `generate-company-description` (Company Profile)
- `generate-agent-name`, `generate-agent-instructions` (Agent Profile — NEW)

---

## Backend: File Upload Endpoint (LinkedIn)

**File:** `backend/app/api/routes/onboarding.py` (lines 1092-1177)

```python
ALLOWED_LINKEDIN_MIME_TYPES = {
    "application/pdf",
    "application/msword",  # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}


@router.post(
    "/linkedin", response_model=LinkedInProfileResponse, status_code=status.HTTP_201_CREATED
)
async def upload_linkedin_profile(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a LinkedIn profile PDF for the current user.
    Replaces any existing LinkedIn profile.
    """
    user_id = UUID(current_user.user_id)
    # Validate file type (must be PDF or Word)
    if file.content_type not in ALLOWED_LINKEDIN_MIME_TYPES:
        raise ValidationError(
            "Only PDF or Word files are supported for LinkedIn profiles/resumes",
            details={
                "supported_types": list(ALLOWED_LINKEDIN_MIME_TYPES),
                "received": file.content_type,
            },
        )

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    supabase = get_supabase_client()

    # Check if user already has a LinkedIn profile
    existing_profile = db.query(LinkedInProfile).filter_by(user_id=user_id).first()

    if existing_profile:
        # Delete old file from storage
        try:
            supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove(
                [existing_profile.storage_uri]
            )
        except Exception as e:
            logger.warning(f"Error deleting old LinkedIn profile from storage: {e}")

    # Create or get the LinkedIn profile record
    if existing_profile:
        linkedin_profile = existing_profile
    else:
        linkedin_profile = LinkedInProfile(
            user_id=user_id,
            file_name=file.filename or "linkedin_profile.pdf",
            storage_uri="__pending__",  # temporary placeholder; replaced after storage upload
            content_type=file.content_type,
            file_size_bytes=file_size,
        )
        db.add(linkedin_profile)
        db.flush()  # Get the ID

    # Upload to Supabase storage
    storage_path = f"users/{user_id}/linkedin_profiles/{linkedin_profile.id}/{file.filename}"

    try:
        supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": file.content_type},
        )
    except Exception as e:
        logger.error(f"Error uploading LinkedIn profile to storage: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to upload LinkedIn profile: {str(e)}"
        ) from e

    # Update the LinkedIn profile record
    linkedin_profile.file_name = file.filename or "linkedin_profile.pdf"
    linkedin_profile.storage_uri = storage_path
    linkedin_profile.content_type = file.content_type
    linkedin_profile.file_size_bytes = file_size

    db.commit()
    db.refresh(linkedin_profile)

    logger.info(f"Uploaded LinkedIn profile for user {user_id}: {storage_path}")

    return linkedin_profile
```

**Kinetic note:** In FounderPanel, the file is stored permanently (used later for generation). In Kinetic, the file is temporary — upload to Supabase Storage, extract text, call LLM, return results, then delete the file. The endpoint should NOT persist the upload record. Kinetic's endpoints return extracted fields only — the caller saves via the normal profile update endpoint.

---

## Backend: Generation Endpoint (User Name)

**File:** `backend/app/api/routes/onboarding.py` (lines 470-559)

```python
@router.post(
    "/generate-user-name",
    response_model=GenerateUserNameResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_user_name(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a user name from their LinkedIn profile PDF using LLM.
    """
    user_id = UUID(current_user.user_id)

    linkedin_profile = db.query(LinkedInProfile).filter_by(user_id=user_id).first()
    if not linkedin_profile:
        raise NotFoundError(
            "Please upload your LinkedIn profile PDF before generating a name.",
            details={"user_id": str(user_id)},
        )

    prompts = db.query(Prompts).first()
    user_name_prompt = _get_prompt_with_fallback(
        prompts,
        "user_name_prompt",
        "Name generation is not configured. Please contact support.",
        DEFAULT_USER_NAME_PROMPT,
    )

    supabase_client = get_supabase_client()
    try:
        file_content = supabase_client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(
            linkedin_profile.storage_uri
        )
    except Exception as e:
        logger.error(f"Error downloading LinkedIn profile for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to download LinkedIn profile from storage"
        ) from e

    processor = get_processor()
    try:
        text_content = processor.extract_text(file_content, linkedin_profile.content_type)
    except Exception as e:
        logger.error(f"Error extracting text from LinkedIn PDF for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to extract text from LinkedIn profile PDF"
        ) from e

    if not settings.LLM_ENABLED or not settings.GEMINI_API_KEY:
        raise ValidationError("LLM service is not enabled or Gemini API key is missing")

    try:
        from app.core.config import get_model_for_use_case, is_reasoning_model
        from app.services.llm_client import call_llm

        model_name = get_model_for_use_case("user_name_extraction")
        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": user_name_prompt},
                {"role": "user", "content": f"LinkedIn Profile Content:\n\n{text_content}"},
            ],
            "max_completion_tokens": 200,
            "timeout": 20,
        }
        if not is_reasoning_model(model_name):
            kwargs["temperature"] = 0.3
        generated_name = call_llm(**kwargs).strip()
    except Exception as e:
        logger.error(f"OpenAI error during user name generation for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate name with LLM") from e

    if not generated_name:
        raise HTTPException(status_code=500, detail="LLM returned an empty name. Please try again.")

    profile = _ensure_founder_profile(db, user_id)
    profile.name = generated_name
    db.commit()

    return GenerateUserNameResponse(user_name=generated_name)
```

**Kinetic note:** This is the simplest generation endpoint — good template for all Kinetic extraction endpoints. Key difference: Kinetic uses BYOK keys via LiteLLM instead of a system OpenAI key. Replace `call_llm()` with LiteLLM's `completion()` using the user's configured keys.

---

## Backend: Generation Endpoint (User Summary — with fallback model)

**File:** `backend/app/api/routes/onboarding.py` (lines 284-467)

```python
@router.post(
    "/generate-user-summary",
    response_model=GenerateUserSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_user_summary(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a user summary from their LinkedIn profile PDF using LLM.
    """
    user_id = UUID(current_user.user_id)

    # 1. Fetch LinkedIn profile
    linkedin_profile = db.query(LinkedInProfile).filter_by(user_id=user_id).first()
    if not linkedin_profile:
        raise NotFoundError(
            "Please upload your LinkedIn profile PDF before generating a summary.",
            details={"user_id": str(user_id)},
        )

    # 2. Fetch prompt
    prompts = db.query(Prompts).first()
    user_summary_prompt = _get_prompt_with_fallback(
        prompts,
        "user_summary_prompt",
        "Summary generation is not configured. Please contact support.",
        DEFAULT_USER_SUMMARY_PROMPT,
    )

    # 3. Download PDF from Supabase
    supabase_client = get_supabase_client()
    try:
        file_content = supabase_client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(
            linkedin_profile.storage_uri
        )
    except Exception as e:
        logger.error(f"Error downloading LinkedIn profile for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to download LinkedIn profile from storage"
        ) from e

    # 4. Extract text using DocumentProcessor
    processor = get_processor()
    try:
        text_content = processor.extract_text(file_content, linkedin_profile.content_type)
    except Exception as e:
        logger.error(f"Error extracting text from LinkedIn PDF for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to extract text from LinkedIn profile PDF"
        ) from e

    # 5. Call LLM
    try:
        from app.core.config import get_model_for_use_case, is_reasoning_model
        from app.services.llm_client import call_llm

        model_name = get_model_for_use_case("user_profile_summary")
        timeout_sec = 30
        max_completion = 800
        reasoning_effort = None
        max_attempts = 2

        if is_reasoning_model(model_name):
            timeout_sec = 120
            max_completion = 1200
            max_attempts = 1
            if model_name.startswith("gemini"):
                reasoning_effort = "low"

        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": user_summary_prompt},
                {"role": "user", "content": f"LinkedIn Profile Content:\n\n{text_content}"},
            ],
            "max_completion_tokens": max_completion,
            "timeout": timeout_sec,
            "max_attempts": max_attempts,
        }
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        if not is_reasoning_model(model_name):
            kwargs["temperature"] = 0.3
        generated_summary = call_llm(**kwargs).strip()

        # Fallback to a known-good model if empty
        if not generated_summary:
            fallback_model = "gpt-4o-mini"
            if model_name != fallback_model:
                logger.warning(
                    f"User summary model returned empty output; retrying with fallback={fallback_model}"
                )
                fallback_kwargs = {
                    "model": fallback_model,
                    "messages": kwargs["messages"],
                    "max_completion_tokens": 800,
                    "timeout": max(timeout_sec, 45),
                    "max_attempts": 1,
                    "temperature": 0.3,
                }
                generated_summary = call_llm(**fallback_kwargs).strip()

        if not generated_summary:
            error_id = f"llm_user_summary_empty_{uuid.uuid4().hex[:10]}"
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "LLM returned empty output while generating user summary",
                    "error_id": error_id,
                    "error_code": "empty_output",
                    "stage": "llm",
                },
            )
    except Exception as e:
        # Error classification — safe to expose error code, not raw message
        error_id = f"llm_user_summary_{uuid.uuid4().hex[:10]}"
        safe_msg = str(e)
        if len(safe_msg) > 300:
            safe_msg = safe_msg[:300] + "…"

        msg_lower = safe_msg.lower()
        error_code = "unknown"
        if "invalid_api_key" in msg_lower or "incorrect api key" in msg_lower:
            error_code = "invalid_api_key"
        elif "insufficient_quota" in msg_lower or "quota" in msg_lower:
            error_code = "quota"
        elif "rate limit" in msg_lower or "ratelimit" in msg_lower or "too many requests" in msg_lower:
            error_code = "rate_limit"
        elif "model_not_found" in msg_lower or "does not exist" in msg_lower or "not found" in msg_lower:
            error_code = "model_not_found"
        elif "timeout" in msg_lower or "timed out" in msg_lower:
            error_code = "timeout"
        elif "connection" in msg_lower or "connect" in msg_lower or "dns" in msg_lower:
            error_code = "network"

        logger.exception(
            f"LLM call failed during user summary generation (error_id={error_id}, error_code={error_code})"
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to generate summary with LLM",
                "error_id": error_id,
                "error_code": error_code,
            },
        ) from e

    # 6. Save to user_profiles and return
    profile = _ensure_founder_profile(db, user_id)
    profile.user_summary = generated_summary
    db.commit()

    return GenerateUserSummaryResponse(user_summary=generated_summary)
```

**Kinetic note:** This is the most complete generation endpoint — includes reasoning model handling, fallback model retry, and full error classification. Use this as the template for all generation endpoints. The error classification block (lines mapping exception messages to error codes) should be extracted into a shared utility.

---

## Backend: Company Name Generation (from multiple documents)

**File:** `backend/app/api/routes/onboarding.py` (lines 965-1069)

```python
@router.post(
    "/generate-company-name",
    response_model=GenerateCompanyNameResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_company_name(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a company name from uploaded startup documents using LLM.
    """
    user_id = UUID(current_user.user_id)

    documents = db.query(StartupDocument).filter_by(user_id=user_id).all()
    if not documents:
        raise ValidationError(
            "Please upload at least one startup document before generating a company name.",
            details={"user_id": str(user_id)},
        )

    prompts = db.query(Prompts).first()
    company_name_prompt = _get_prompt_with_fallback(
        prompts,
        "company_name_prompt",
        "Company name generation is not configured. Please contact support.",
        DEFAULT_COMPANY_NAME_PROMPT,
    )

    # Extract and combine text from all documents
    combined_text = ""
    supabase_client = get_supabase_client()
    processor = get_processor()

    for doc in documents:
        try:
            file_content = supabase_client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(
                doc.storage_uri
            )
            text_content = processor.extract_text(file_content, doc.mime_type)
            combined_text += f"\n\n--- Document: {doc.filename} ---\n{text_content}"
        except Exception as e:
            logger.error(f"Error processing document {doc.id} for user {user_id}: {e}")
            continue

    if not combined_text.strip():
        raise HTTPException(
            status_code=500, detail="Failed to extract text from any uploaded documents"
        )

    try:
        from app.core.config import get_model_for_use_case, is_reasoning_model
        from app.services.llm_client import call_llm

        model_name = get_model_for_use_case("company_name")
        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": company_name_prompt},
                {"role": "user", "content": f"Startup Documents Content:\n\n{combined_text}"},
            ],
            "max_completion_tokens": 200,
            "timeout": 30,
        }
        if not is_reasoning_model(model_name):
            kwargs["temperature"] = 0.3
        generated_company_name = call_llm(**kwargs).strip()
    except Exception as e:
        logger.error(f"OpenAI error during company name generation for user {user_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate company name with LLM"
        ) from e

    if not generated_company_name:
        raise HTTPException(
            status_code=500, detail="LLM returned an empty company name. Please try again."
        )

    startup = db.query(Startup).filter_by(user_id=user_id).first()
    if not startup:
        startup = Startup(
            user_id=user_id,
            name=generated_company_name,
            stage="idea",
            startup_summary_short="",
            startup_summary_long="",
        )
        db.add(startup)
    else:
        startup.name = generated_company_name

    db.commit()

    return GenerateCompanyNameResponse(company_name=generated_company_name)
```

**Kinetic note:** This shows the multi-document extraction pattern — FounderPanel combines text from ALL uploaded startup docs into one prompt. Kinetic's company upload is simpler (single file), but the agent upload could benefit from this pattern if we later support uploading multiple writing samples.

---

## Frontend: API Client Functions

**File:** `frontend/lib/api.ts` (lines 486-565)

```typescript
export async function uploadMyLinkedIn(file: File): Promise<LinkedInProfile> {
  const formData = new FormData();
  formData.append("file", file);

  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers: Record<string, string> = {};
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  } else {
    throw new Error("You are not logged in. Please sign in again.");
  }

  const response = await fetch(`${API_BASE_URL}/api/onboarding/linkedin`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    const errorMessage = await parseApiError(response);
    throw new Error(errorMessage);
  }
  return response.json();
}

export async function generateUserSummary(): Promise<{ user_summary: string }> {
  const response = await apiFetch("/api/onboarding/generate-user-summary", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}

export async function generateStartupSummaryShort(): Promise<{ startup_summary_short: string }> {
  const response = await apiFetch("/api/onboarding/generate-startup-summary-short", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}

export async function generateStartupSummaryLong(): Promise<{ startup_summary_long: string }> {
  const response = await apiFetch("/api/onboarding/generate-startup-summary-long", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}

export async function generateUserName(): Promise<{ user_name: string }> {
  const response = await apiFetch("/api/onboarding/generate-user-name", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}

export async function generateCompanyName(): Promise<{ company_name: string }> {
  const response = await apiFetch("/api/onboarding/generate-company-name", {
    method: "POST",
  });
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json();
}
```

**Kinetic note:** In FounderPanel, upload and generation are separate API calls (upload first, then trigger generation separately). Kinetic's design is simpler: one endpoint per page that accepts the file, extracts text, calls LLM, and returns the generated fields in one round-trip. The frontend calls one endpoint, not two.

---

## Frontend: Full Onboarding Page Component

**File:** `frontend/app/onboarding/page.tsx`

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import {
  uploadMyLinkedIn,
  uploadMyDocuments,
  getMyDocuments,
  deleteMyDocument,
  initOnboardingProfile,
  generateUserName,
  generateUserSummary,
  generateCompanyName,
  generateStartupSummaryShort,
  generateStartupSummaryLong,
} from "@/lib/api";
import { File, Trash2 } from "lucide-react";

interface StartupDocument {
  id: string;
  user_id: string;
  filename: string;
  storage_uri: string;
  mime_type: string;
  file_size: number;
  created_at: string;
}

const ALLOWED_EXTENSIONS = [
  ".txt", ".pdf", ".md", ".csv", ".xlsx", ".xls",
  ".docx", ".doc", ".pptx", ".ppt", ".rtf", ".odt", ".xml", ".zip",
];

const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB

export default function OnboardingPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [currentStep, setCurrentStep] = useState(1);
  const navigationStarted = useRef(false);
  const [userGenerationPromise, setUserGenerationPromise] = useState<Promise<void> | null>(null);
  const [startupGenerationPromise, setStartupGenerationPromise] = useState<Promise<void> | null>(null);
  const [showLoadingScreen, setShowLoadingScreen] = useState(false);
  const [generatingUserFields, setGeneratingUserFields] = useState(false);
  const [generatingStartupFields, setGeneratingStartupFields] = useState(false);

  useEffect(() => {
    initOnboardingProfile().catch(() => {});
  }, []);

  // Step 1: LinkedIn/Resume upload
  const [uploadingLinkedIn, setUploadingLinkedIn] = useState(false);
  const [linkedInFile, setLinkedInFile] = useState<{ name: string; size: number } | null>(null);
  const [linkedInUnsupportedMessage, setLinkedInUnsupportedMessage] = useState<string | null>(null);

  // Step 2: Startup documents upload
  const [uploadingDocuments, setUploadingDocuments] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [documents, setDocuments] = useState<StartupDocument[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);

  const handleLinkedInUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (
      file.type !== "application/pdf" &&
      file.type !== "application/msword" &&
      file.type !== "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ) {
      toast({ title: "Error", description: "Only PDF or Word files are supported", variant: "destructive" });
      setLinkedInUnsupportedMessage("Unsupported document type. Please upload a PDF or Word file.");
      return;
    }

    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      toast({ title: "Error", description: "File size must be less than 10 MB", variant: "destructive" });
      return;
    }

    setUploadingLinkedIn(true);
    setLinkedInUnsupportedMessage(null);

    try {
      await uploadMyLinkedIn(file);
      setLinkedInFile({ name: file.name, size: file.size });
      toast({ title: "Success", description: "LinkedIn profile uploaded successfully" });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to upload LinkedIn profile",
        variant: "destructive",
      });
    } finally {
      setUploadingLinkedIn(false);
      e.target.value = "";
    }
  };

  // Generation sequencing: Step 1→2 triggers user name + summary
  const handleNext = () => {
    if (currentStep === 1) {
      if (!linkedInFile) {
        toast({ title: "Error", description: "Please upload your LinkedIn profile first", variant: "destructive" });
        return;
      }

      if (!userGenerationPromise) {
        const promise = (async () => {
          setGeneratingUserFields(true);
          try {
            await generateUserName();
            await generateUserSummary();
          } catch (error) {
            toast({
              title: "Generation error",
              description: error instanceof Error ? error.message : "Failed to generate your name and summary",
              variant: "destructive",
            });
          } finally {
            setGeneratingUserFields(false);
          }
        })();
        setUserGenerationPromise(promise);
      }

      setCurrentStep(2);
    } else if (currentStep === 2) {
      // Step 2→3 triggers company name + startup summaries
      if (!startupGenerationPromise) {
        const promise = (async () => {
          setGeneratingStartupFields(true);
          try {
            await generateCompanyName();
            await generateStartupSummaryShort();
            await generateStartupSummaryLong();
          } catch (error) {
            toast({
              title: "Generation error",
              description: error instanceof Error ? error.message : "Failed to generate startup details",
              variant: "destructive",
            });
          } finally {
            setGeneratingStartupFields(false);
          }
        })();
        setStartupGenerationPromise(promise);
      }

      setCurrentStep(3);
    }
  };

  // Wait for all generation to complete before redirecting
  useEffect(() => {
    if (currentStep !== 3) {
      setShowLoadingScreen(false);
      return;
    }

    const promises = [userGenerationPromise, startupGenerationPromise].filter(Boolean) as Promise<void>[];

    if (promises.length === 0) {
      if (!navigationStarted.current) {
        navigationStarted.current = true;
        router.push("/profile");
      }
      return;
    }

    setShowLoadingScreen(true);

    Promise.all(promises)
      .catch((error) => {
        toast({
          title: "Generation error",
          description: error instanceof Error ? error.message : "Failed to complete profile generation",
          variant: "destructive",
        });
      })
      .finally(() => {
        if (!navigationStarted.current) {
          navigationStarted.current = true;
          router.push("/profile");
        }
      });
  }, [currentStep, userGenerationPromise, startupGenerationPromise, router, toast]);

  // ... rest of JSX render (upload UI, document list, loading screen)
}
```

**Kinetic note:** FounderPanel uses a wizard flow (Step 1 → 2 → 3). Kinetic's linked upload is inline on each profile page — not a separate onboarding flow. The key pattern to reuse is the async generation with loading state and error handling. Kinetic's version is simpler: one upload button per page, one API call, populate fields inline, user reviews and saves.

---

## Key Architecture Differences: FounderPanel → Kinetic

| Aspect | FounderPanel | Kinetic |
|---|---|---|
| **LLM keys** | System-wide OpenAI key | User's BYOK keys via LiteLLM |
| **Upload persistence** | File stored permanently | File discarded after extraction |
| **Upload + Generate** | Separate endpoints (upload first, then generate) | Single endpoint: upload → extract → generate → return fields |
| **Flow** | Onboarding wizard (multi-step) | Inline on each profile page |
| **Model selection** | `get_model_for_use_case()` with system config | User's default model or fast model from their configured keys |
| **Agent linked upload** | Not present | NEW — generates Name + Instructions (system prompt) from writing sample |
| **Vector DB** | Qdrant | pgvector (Supabase) — but irrelevant for linked upload, which doesn't use vectors |
