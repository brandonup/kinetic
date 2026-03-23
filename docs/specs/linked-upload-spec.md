# Linked Upload Spec

**Owner:** Jared
**Sprint:** 5 (implementation)
**Status:** Approved
**Tickets:** KIN-281

---

## 1. Overview

Linked Upload allows users to upload a file and have the system extract structured fields from it using an LLM (BYOK key). The extracted fields are presented for review before saving. The file is discarded after extraction — it is never stored or added to a knowledge base.

Three surfaces: **User Profile**, **Company**, **Agent**.

---

## 2. BYOK Gate

The upload affordance (button) is hidden/disabled when the user has no API keys configured.

- **No API keys:** button renders as disabled with tooltip: "Add an API key in your profile to use this feature."
- **At least one API key configured:** button is enabled.

Model used: user's `default_model_id`. Fallback: first available BYOK key/model in any provider order. The extraction call uses the user's BYOK key — platform key is not used.

---

## 3. File Handling

| Surface | Accepted types | Max size |
|---------|---------------|----------|
| User Profile | PDF, TXT, DOCX | 10 MB |
| Company | PDF, TXT, DOCX | 25 MB |
| Agent | PDF, TXT, DOCX | 25 MB |

- File is read server-side, passed to the LLM extraction call, then **discarded immediately** — not written to storage, not added to any KB.
- If file exceeds size limit: reject before upload with `413 Content Too Large` and client-side error: "File too large. Maximum size is {N} MB."
- If file type not accepted: reject with `415 Unsupported Media Type` and client-side error: "Unsupported file type. Please upload a PDF, TXT, or DOCX file."

---

## 4. API

### 4.1 Endpoint

```
POST /api/v1/upload/extract
```

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | The uploaded file |
| `surface` | string | Yes | `user_profile`, `company`, or `agent` |
| `agent_id` | string | Conditional | Required when `surface = agent` |

**Auth:** `get_current_user`. User must have at least one BYOK key configured; 422 if not.

### 4.2 Response 200

```json
{
  "surface": "user_profile",
  "extracted": {
    "name": "Jane Smith",
    "bio": "Product designer with 10 years..."
  },
  "confidence": "partial",
  "warnings": ["bio was truncated to 500 characters"]
}
```

`confidence` values:
- `full` — all fields extracted successfully
- `partial` — some fields extracted, some null
- `empty` — no fields could be extracted

### 4.3 Error responses

| Status | Code | Meaning |
|--------|------|---------|
| 413 | `file_too_large` | File exceeds max size |
| 415 | `unsupported_type` | File type not accepted |
| 422 | `byok_key_required` | No BYOK key configured |
| 422 | `agent_id_required` | `surface = agent` but no `agent_id` |
| 502 | `llm_extraction_failed` | BYOK call failed (auth error, timeout, etc.) |

On 502: show error state with retry button. Message: "Extraction failed. Check that your API key is valid and try again."

---

## 5. Surface-Specific Extraction

### 5.1 User Profile

**Fields extracted:** `name`, `bio`

**Extraction prompt:**
```
Extract the following from this document:
1. The person's full name
2. A short professional bio (2–3 sentences maximum, plain text, no markdown)

Return JSON: { "name": "...", "bio": "..." }
If a field cannot be determined, return null for that field.
```

**Post-processing:**
- `bio` truncated to 1000 characters if longer (matches `users.bio` DB constraint)
- `name` truncated to 100 characters

### 5.2 Company

**Fields extracted:** `name`, `description`

**Extraction prompt:**
```
Extract the following from this document:
1. The company's name
2. A description of the company (what it does, its mission, key focus areas — 2–4 sentences, plain text)

Return JSON: { "name": "...", "description": "..." }
If a field cannot be determined, return null for that field.
```

**Post-processing:**
- `description` truncated to 1000 characters if longer
- `name` truncated to 200 characters

### 5.3 Agent

**Fields extracted:** `name`, `instructions` (full system prompt)

This surface is unique: it generates a structured system prompt from the corpus, rather than extracting existing text.

**Extraction prompt:**
```
You are analyzing a document to create a configuration for an AI agent that emulates the thinking and communication style of the person or entity described.

Based on this document, generate:
1. A short agent name (the person's name or a descriptive label, ≤60 characters)
2. A system prompt for the agent (300–500 tokens) that captures:
   - Their thinking style and reasoning approach
   - Their communication patterns and voice
   - Their core principles or values
   - Their areas of expertise
   - How they typically structure responses

The system prompt should be written in second person ("You are...") and be ready to use directly as an AI agent's instructions.

Return JSON: { "name": "...", "instructions": "..." }
```

**Post-processing:**
- `instructions` not truncated (system prompt is expected to be long)
- `name` truncated to 100 characters

---

## 6. Review + Edit Flow

After extraction, the user sees a review panel before saving. This is the same flow on all three surfaces.

### 6.1 Review panel

- Shows each extracted field with its value
- Each field is **editable inline** (same input types as the normal edit form for that surface)
- Fields that are `null` show a placeholder: "Could not extract — enter manually"
- `confidence` banner:
  - `full`: no banner
  - `partial`: "Some fields could not be extracted. Please review before saving."
  - `empty`: "Nothing could be extracted from this file. You can enter the details manually below."

### 6.2 Actions

- **Save** — saves extracted (and user-edited) values to the entity. Calls the normal entity PATCH endpoint.
- **Cancel** — dismisses the panel without saving. No changes applied.

### 6.3 What is saved

The review panel submits only the fields relevant to the surface. It does not overwrite unrelated fields on the entity.

---

## 7. Edge Cases

| Case | Behavior |
|------|----------|
| All fields null (empty extraction) | `confidence = empty`. Review panel shown with all fields blank and editable. User can enter manually or cancel. |
| Partial extraction | `confidence = partial`. Panel shown with populated + null fields. |
| File too large | Rejected client-side before upload. Error shown inline near the upload button. |
| Unsupported file type | Rejected client-side. Same inline error pattern. |
| BYOK key fails mid-extraction | 502 returned. Error state shown with retry button. No partial state saved. |
| BYOK key missing | Button disabled (see §2). If somehow reached, 422 returned with `byok_key_required`. |
| Oversized extracted field | Backend truncates to field max (see §5). Warning returned in `warnings` array. |
| Agent has no KB | Extraction proceeds normally — the LLM uses the uploaded document content directly, not the KB. |

---

## 8. UI Entry Points

### User Profile

Location: User Profile page → below name/bio fields

Button: **"Upload from file"** (disabled + tooltip when no BYOK key)

### Company

Location: Company settings page → below name/description fields

Button: **"Upload from file"**

### Agent

Location: Agent Profile → Instructions tab → below the instructions textarea

Button: **"Generate from document"** (label differentiated because it's generative, not extractive)

Note: the "Generate from corpus" button (from KB) is a separate action — do not conflate.

---

## 9. Open Questions

None. Spec is complete for Gilfoyle pre-implementation review.
