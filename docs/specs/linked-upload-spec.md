# Kinetic Linked Upload — Implementation Spec

**Status:** Approved
**Author:** Jared
**Date:** 2026-03-23
**Ticket:** KIN-281
**Feature doc:** `docs/feature-linked-upload.md`
**FounderPanel ref:** `docs/reference-linked-upload-founderpanel.md`
**PRD ref:** `docs/prd.md` §2 (User Profile), §3 (Companies), §6 (Agents), §12 (Linked Upload)

---

## §1 Overview

Linked Upload is a document-to-field extraction feature on three profile surfaces. The user uploads a document, the system extracts structured fields via LLM, the user reviews and edits, then saves. The uploaded file is discarded after extraction — it is never added to any Knowledge Base or retained in storage.

**Surfaces:**
| Surface | Fields extracted | Upload purpose |
|---|---|---|
| User Profile | Name, Short Bio | Auto-fill from LinkedIn PDF, resume, bio |
| Company Profile | Name, Short Description | Auto-fill from business plan, pitch deck, one-pager |
| Agent Profile | Name, Instructions (system prompt) | Auto-fill from thought leader writing sample |

**Key constraint:** Linked upload uses the user's BYOK key. The user must have at least one API key configured. The system selects the user's default model, or the first available model if no default is set.

---

## §2 Shared Upload API

### §2.1 Endpoint Pattern

Three surface-specific endpoints — not one shared endpoint. Each returns different field shapes.

| Method | Endpoint | Surface |
|---|---|---|
| POST | `/api/v1/profile/upload-document` | User Profile |
| POST | `/api/v1/companies/{id}/upload-document` | Company |
| POST | `/api/v1/agents/{id}/upload-document` | Agent Profile |

### §2.2 Request Shape

All three endpoints accept the same request shape:

```
POST /api/v1/{surface}/upload-document
Content-Type: multipart/form-data

file: <binary file content>
```

**Headers:** Standard `Authorization: Bearer <JWT>` (Supabase auth, not MCP token).

### §2.3 Response Shapes

**User Profile (200):**
```json
{
  "name": "string | null",
  "bio": "string | null"
}
```

**Company (200):**
```json
{
  "name": "string | null",
  "description": "string | null"
}
```

**Agent (200):**
```json
{
  "name": "string | null",
  "instructions": "string | null"
}
```

**Null fields:** A null value means the LLM could not extract/generate that field from the document. The frontend leaves the corresponding field empty and prompts the user to fill it manually.

### §2.4 Processing Flow (all surfaces)

1. **Validate file** — check format and size (see §5)
2. **BYOK gate** — verify user has at least one API key configured (see §6). Return 400 if not.
3. **Extract text** — use `unstructured` library (same as KB ingestion). Text extraction runs in-memory from file bytes — no file is written to disk or storage.
4. **Call LLM** — send extracted text + surface-specific prompt (see §3) to the user's BYOK model
5. **Parse response** — extract structured fields from LLM output
6. **Discard file** — file bytes are released from memory. No storage write. No DB record of the upload.
7. **Return fields** — extracted fields returned to the caller. The caller saves via the normal profile/company/agent update endpoint — the upload endpoint does NOT write to the profile.

**Timeout:** 30 seconds. If the LLM call takes longer, return 504 with error message: "Extraction timed out. Try a shorter document or try again."

---

## §3 Surface-Specific Extraction Prompts

All prompts are stored in the prompts module (versioned, not hardcoded in route handlers). Prompt IDs follow the `generate-{surface}-{field}` convention.

### §3.1 User Profile Prompts

**`generate-user-name` (prompt ID: `linked-upload-user-name-v1`)**

> Extract the person's full name from the document. Return only the name — no additional text. If the name cannot be determined, return null.

**`generate-user-bio` (prompt ID: `linked-upload-user-bio-v1`)**

> Generate a concise professional bio (2–4 sentences, max 1000 characters) based on the person's current role, professional background, and domain expertise as described in the document. Write in first person. Do not include specific company names, dates, or metrics unless essential to context.

**LLM call pattern:**
```python
messages = [
    {"role": "system", "content": prompt},
    {"role": "user", "content": f"Document Content:\n\n{extracted_text}"}
]
```

Temperature: 0.3. Max completion tokens: 200 (name), 800 (bio).

### §3.2 Company Prompts

**`generate-company-name` (prompt ID: `linked-upload-company-name-v1`)**

> Extract the company name from the document. Return only the name. If ambiguous or not found, return null.

**`generate-company-description` (prompt ID: `linked-upload-company-description-v1`)**

> Generate a concise company description (2–4 sentences, max 1000 characters) covering what the company does, who it serves, and what makes it distinctive. Base this only on the document content. Write in third person.

Temperature: 0.3. Max completion tokens: 200 (name), 800 (description).

### §3.3 Agent Profile Prompts

**`generate-agent-name` (prompt ID: `linked-upload-agent-name-v1`)**

> Identify the primary author, speaker, or thought leader in this document. Return their full name only — no additional text. If the document has no clear single author (e.g., a co-authored piece), return the most prominent name. If no name can be determined, return null.

**`generate-agent-instructions` (prompt ID: `linked-upload-agent-instructions-v1`)**

> You are building a system prompt for an AI agent that thinks and reasons like the person whose writing is provided below. Analyze the document for:
>
> 1. **Thinking style** — How does this person approach problems? Do they reason from first principles, use analogies, lean on data, or rely on intuition? What mental models do they favor?
> 2. **Communication patterns** — What is their tone? Are they direct or nuanced? Do they use stories, frameworks, provocative questions, or structured arguments?
> 3. **Core principles** — What beliefs, values, or recurring themes appear across their work? What do they consistently advocate for or push back against?
> 4. **Areas of expertise** — What domains do they operate in? What topics do they have deep conviction about?
> 5. **Distinctive perspective** — What makes their viewpoint different from the mainstream in their field?
>
> Generate a system prompt (300–500 tokens) written as instructions to an LLM. The prompt should begin with "You are [name]..." and instruct the model to adopt this person's reasoning style, principles, and communication patterns. Do not simply summarize the document — distill the person's intellectual fingerprint into actionable instructions that shape how the LLM reasons, not just what it says.

Temperature: 0.5 (slightly higher — creative generation, not extraction). Max completion tokens: 1200 (instructions need room for a rich system prompt).

---

## §4 Review + Edit Flow

The upload endpoint returns extracted fields — it does NOT save them. The frontend handles the review-before-save pattern.

### §4.1 Frontend Flow

1. User clicks "Upload document to auto-fill" button
2. File picker opens — filtered to accepted formats for this surface
3. On file select: POST to upload endpoint, show loading state
4. On success: populate form fields with extracted values. All fields are editable inline.
5. Show review banner: "Review the fields above before saving."
6. Agent surface adds: "The system prompt is a starting point — refine it to match your intent."
7. User edits as needed, then clicks Save (same save action as manual editing)
8. Save calls the normal profile/company/agent PATCH endpoint — the upload endpoint is not involved

### §4.2 Re-upload

After a successful extraction, the upload button changes to "Re-upload". Re-uploading triggers a confirmation prompt: "This will replace the current extracted fields. Continue?" On confirm, the extraction runs again and repopulates the fields.

### §4.3 Editable Fields

| Surface | Editable fields |
|---|---|
| User Profile | Name (text input), Bio (textarea, max 1000 chars) |
| Company | Name (text input), Description (textarea, max 1000 chars) |
| Agent | Name (text input), Instructions (textarea, multi-line, ~500 tokens) |

All fields are fully editable. The extraction output is a starting point — the user has final control.

---

## §5 File Handling

### §5.1 Accepted Types Per Surface

| Surface | Formats | Max size |
|---|---|---|
| User Profile | `.pdf`, `.docx`, `.doc`, `.txt` | 10 MB |
| Company | `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md` | 25 MB |
| Agent | `.pdf`, `.docx`, `.doc`, `.txt`, `.md` | 25 MB |

### §5.2 MIME Type Validation

| Extension | MIME type |
|---|---|
| `.pdf` | `application/pdf` |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `.doc` | `application/msword` |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| `.ppt` | `application/vnd.ms-powerpoint` |
| `.txt` | `text/plain` |
| `.md` | `text/markdown`, `text/x-markdown` |

Unsupported format → 400 with error:
```json
{
  "error": "unsupported_format",
  "message": "Only PDF, Word, and text files are supported",
  "supported_types": [".pdf", ".docx", ".doc", ".txt"]
}
```

### §5.3 File Size Validation

Oversized file → 400 with error:
```json
{
  "error": "file_too_large",
  "message": "File must be under 10 MB",
  "max_bytes": 10485760
}
```

### §5.4 File Lifecycle

The uploaded file is **never persisted**:
- File bytes are read into memory from the multipart request
- Text is extracted from file bytes via `unstructured`
- File bytes are released after extraction (Python garbage collection)
- No write to Supabase Storage, no write to any DB table
- No record of the upload exists after the request completes

This is the key difference from FounderPanel, which stores the uploaded file permanently.

---

## §6 BYOK Gate

### §6.1 Pre-key State

If the user has zero API keys configured:
- **Upload button:** disabled (greyed out)
- **Tooltip on hover:** "Add an API key to enable auto-fill"
- **Server-side enforcement:** return 400 if no key is configured — the frontend gate can be bypassed via direct API call

```json
{
  "error": "no_api_key",
  "message": "Configure at least one API key in your profile to use linked upload"
}
```

### §6.2 Model Selection

The extraction call uses the user's BYOK key via LiteLLM:
1. Use user's default model if set
2. Otherwise, use the first available model matching the user's configured keys
3. If no model can be resolved (keys exist but no matching models enabled) → 400 `no_available_model`

### §6.3 Key Failure During Extraction

If the LLM call fails due to a key issue (invalid key, quota exceeded, rate limited):
- Return 502 with classified error code (same error classification as FounderPanel — see reference doc):

```json
{
  "error": "llm_error",
  "error_code": "invalid_api_key | quota | rate_limit | timeout | network | unknown",
  "message": "Human-readable description"
}
```

The frontend shows the error inline with a "Try again" option. The user's form fields are not modified on error.

---

## §7 Edge Cases

| Scenario | Behavior |
|---|---|
| **All fields null** — LLM returns null for every field | Return 200 with all-null response. Frontend shows empty fields with note: "Couldn't extract content from this file. Try a different document." |
| **Partial extraction** — some fields extracted, others null | Return 200 with mixed null/non-null. Frontend populates available fields, leaves null fields empty for manual entry. |
| **Empty document** — file has zero extractable text | Return 400 `empty_document`: "No text could be extracted from this file. Try a different format." |
| **Oversized text** — extracted text exceeds context window | Truncate to the first N characters that fit the model's context window (leaving room for prompt + completion). Log a warning. |
| **Upload fails (network error)** | Frontend shows error state with retry option. No fields modified. |
| **Re-upload** — user uploads a second document | Confirmation prompt before replacing. On confirm, new extraction replaces previous values. |
| **Agent: no identifiable author** | `name` returns null. `instructions` still generated from content — the system prompt is useful even without identifying the author. |
| **Agent: document is too short** (<500 chars extracted) | Generate best-effort instructions. Append note to response: "Upload additional writing samples for a richer persona." |
| **Agent: multi-author document** | `name` returns the most prominent author. `instructions` note: "Multiple voices detected — review carefully." |
| **Extraction endpoints do NOT validate ownership** | Per MEMORY.md decision (2026-03-23): extraction is compute-only (no DB write, no read of protected data). Ownership is validated by the save PATCH endpoint. |

---

## §8 Error Response Catalog

| HTTP | Error code | When |
|---|---|---|
| 400 | `unsupported_format` | File type not in accepted list for this surface |
| 400 | `file_too_large` | File exceeds surface-specific size limit |
| 400 | `empty_document` | No text extracted from file |
| 400 | `no_api_key` | User has no API keys configured (BYOK gate) |
| 400 | `no_available_model` | Keys exist but no matching model is enabled |
| 502 | `llm_error` | LLM call failed (with `error_code` subfield) |
| 504 | `extraction_timeout` | LLM call exceeded 30s timeout |
| 500 | `extraction_failed` | Text extraction from file failed |

---

## §9 Implementation Tickets

| Ticket | Scope |
|---|---|
| KIN-310 | User Profile + Company surfaces — full upload → extract → return flow |
| KIN-311 | Agent Profile surface — includes system prompt generation |
| KIN-314 | Test coverage across all three surfaces (Jìan) |
