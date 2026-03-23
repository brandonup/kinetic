# Kinetic — Feature Spec: Linked Upload

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)
**Target release:** MVP

---

## Overview

Linked Upload is a document-to-field extraction feature on the User Profile page and the Company profile page. Instead of typing their bio or company description manually, a user uploads a document (LinkedIn export, resume, bio, business plan, pitch deck, etc.) and the system uses an LLM to extract and generate the relevant fields automatically. The user reviews and edits the AI-generated content before saving.

This removes the blank-page friction from profile setup and ensures the context injected into every prompt reflects the user's real background and the company's actual situation — without requiring the user to write anything from scratch.

---

## Feature Locations

### User Profile Page — Personal Bio Upload

| Detail | Value |
|---|---|
| Route | `/profile` |
| Upload purpose | Auto-populate Name and Short Bio |
| Accepted document types | LinkedIn PDF export, resume, personal bio, CV |
| Supported formats | `.pdf`, `.docx`, `.doc`, `.txt` |
| Max file size | 10MB |

**Fields auto-generated from upload:**

| Field | Generation method |
|---|---|
| Name | Extracted directly from document (name appears at top of LinkedIn/resume) |
| Short bio | AI-synthesized from professional background, current role, and relevant experience |

---

### Company Profile Page — Company Description Upload

| Detail | Value |
|---|---|
| Route | `/company/{id}/edit` |
| Upload purpose | Auto-populate Company Name and Short Description |
| Accepted document types | Business plan, pitch deck, one-pager, executive summary, website copy |
| Supported formats | `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md` |
| Max file size | 25MB |

**Fields auto-generated from upload:**

| Field | Generation method |
|---|---|
| Company name | Extracted directly from document |
| Short description | AI-synthesized from mission, product/service, and business model sections |

---

### Agent Profile Page — Agent Instructions Upload

| Detail | Value |
|---|---|
| Route | `/agent/{id}/edit` |
| Upload purpose | Auto-populate Agent Name and Instructions (system prompt) |
| Accepted document types | Thought leader writing samples, transcripts, interviews, articles, book excerpts, blog posts |
| Supported formats | `.pdf`, `.docx`, `.doc`, `.txt`, `.md` |
| Max file size | 25MB |

**Fields auto-generated from upload:**

| Field | Generation method |
|---|---|
| Agent name | AI-inferred from the author/speaker identified in the document |
| Instructions (system prompt) | AI-synthesized persona definition capturing the person's thinking style, communication patterns, core principles, areas of expertise, and perspective — written as a system prompt that instructs the LLM to reason like this person |

**Relationship to Agent Knowledge Base:** The uploaded file is used only for field extraction and then discarded. If the user wants the document available for RAG retrieval, they upload it separately to the agent's Knowledge Base. This is the same boundary as User Profile and Company Profile uploads — linked upload populates fields, KB upload populates the retrieval corpus.

---

## User Flow

### User Profile Upload

```
Profile Page → Upload Document button → File picker → Upload →
Processing indicator → Review AI-generated fields →
Edit if needed → Save
```

1. User sees an "Upload document to auto-fill" button alongside the Name and Bio fields on the profile page.
2. User selects a file. Accepted formats are shown; unsupported formats are rejected with a clear error.
3. File uploads and the system shows a processing state ("Extracting your information...").
4. On completion, the Name and Bio fields are populated with AI-generated content. The upload button is replaced by a "Re-upload" option.
5. User reviews the generated content inline. Both fields are fully editable.
6. User saves the profile. The uploaded file is not retained after extraction — it is discarded once fields are populated.

### Company Profile Upload

```
Company Edit Page → Upload document button → File picker → Upload →
Processing indicator → Review AI-generated fields →
Edit if needed → Save
```

Same flow as user profile. The uploaded document is discarded after extraction.

### Agent Profile Upload

```
Agent Profile Page → Upload document button → File picker → Upload →
Processing indicator → Review AI-generated fields →
Edit if needed → Save
```

1. User sees an "Upload document to auto-fill" button alongside the Name and Instructions fields on the Agent Profile page.
2. User selects a file (thought leader writing, transcript, interview, etc.). Accepted formats are shown; unsupported formats are rejected with a clear error.
3. File uploads and the system shows a processing state ("Analyzing writing to generate persona...").
4. On completion, the Name and Instructions (system prompt) fields are populated with AI-generated content. The upload button is replaced by a "Re-upload" option.
5. User reviews the generated content inline. Both fields are fully editable — the user is expected to refine the system prompt.
6. User saves the agent profile. The uploaded file is not retained after extraction — it is discarded once fields are populated.
7. If the user wants this document available for RAG, they upload it separately to the agent's Knowledge Base.

---

## Extraction Logic

### User Profile Extraction

The uploaded document is passed to an LLM with extraction prompts:

**`generate-user-name`**
Extract the person's full name from the document. Return only the name — no additional text. If the name cannot be determined, return null.

**`generate-user-bio`**
Generate a concise professional bio (2-4 sentences, max 1000 characters) based on the person's current role, professional background, and domain expertise as described in the document. Write in first person. Do not include specific company names, dates, or metrics unless essential to context.

### Company Profile Extraction

**`generate-company-name`**
Extract the company name from the document. Return only the name. If ambiguous or not found, return null.

**`generate-company-description`**
Generate a concise company description (2-4 sentences, max 1000 characters) covering what the company does, who it serves, and what makes it distinctive. Base this only on the document content. Write in third person.

### Agent Profile Extraction

**`generate-agent-name`**
Identify the primary author, speaker, or thought leader in this document. Return their full name only — no additional text. If the document has no clear single author (e.g., a co-authored piece), return the most prominent name. If no name can be determined, return null.

**`generate-agent-instructions`**
You are building a system prompt for an AI agent that thinks and reasons like the person whose writing is provided below. Analyze the document for:

1. **Thinking style** — How does this person approach problems? Do they reason from first principles, use analogies, lean on data, or rely on intuition? What mental models do they favor?
2. **Communication patterns** — What is their tone? Are they direct or nuanced? Do they use stories, frameworks, provocative questions, or structured arguments?
3. **Core principles** — What beliefs, values, or recurring themes appear across their work? What do they consistently advocate for or push back against?
4. **Areas of expertise** — What domains do they operate in? What topics do they have deep conviction about?
5. **Distinctive perspective** — What makes their viewpoint different from the mainstream in their field?

Generate a system prompt (300–500 tokens) written as instructions to an LLM. The prompt should begin with "You are [name]..." and instruct the model to adopt this person's reasoning style, principles, and communication patterns. Do not simply summarize the document — distill the person's intellectual fingerprint into actionable instructions that shape how the LLM reasons, not just what it says.

---

## Handling Edge Cases

| Scenario | Behavior |
|---|---|
| File format not supported | Reject at upload with clear format list |
| File exceeds size limit | Reject at upload with size limit displayed |
| Name cannot be extracted | Name field left empty; user prompted to fill manually |
| Bio/description generation returns low-confidence content | Display result with a note: "Review carefully — our extraction may be incomplete." |
| Upload fails (network/processing error) | Show error state with retry option; no fields are modified |
| User uploads a second document | Overwrites the previously generated fields after confirmation prompt |
| Agent upload: no identifiable author | Name field left empty; user prompted to fill manually. Instructions still generated from content. |
| Agent upload: document is too short for persona extraction | Generate best-effort instructions with a note: "Upload additional writing samples for a richer persona." |
| Agent upload: document is multi-author | Name set to most prominent author; Instructions note: "Review carefully — multiple voices detected." |

---

## What the Uploaded File Is NOT Used For

- The file is **not** added to any Knowledge Base.
- The file is **not** retained after extraction is complete.
- The file is **not** used for RAG retrieval.
- The sole purpose of the upload is to populate the Name/Bio (user) or Name/Description (company) fields. Once those fields are written, the file is discarded.

This is intentional. If the user wants the full document (e.g., a business plan) available for RAG retrieval, they upload it separately to the Project Knowledge Base. The profile upload is purely a convenience for field population.

---

## UI Behavior

### Profile page — before upload

```
Name          [ __________________ ]
Short Bio     [ __________________ ]

              [↑ Upload document to auto-fill]
              LinkedIn, resume, bio — PDF, DOCX, TXT
```

### Profile page — processing state

```
Name          [ __________________ ]
Short Bio     [ __________________ ]

              [⟳ Extracting your information...]
```

### Profile page — after upload

```
Name          [ Brandon Smith      ]   ← editable
Short Bio     [ AI consultant...   ]   ← editable

              [↑ Re-upload]

              ⚠ Review the fields above before saving.
```

### Agent profile page — before upload

```
Name             [ __________________ ]
Instructions     [ __________________ ]
                 [ __________________ ]
                 [ __________________ ]

                 [↑ Upload document to auto-fill]
                 Writing sample, transcript, interview — PDF, DOCX, TXT, MD
```

### Agent profile page — processing state

```
Name             [ __________________ ]
Instructions     [ __________________ ]

                 [⟳ Analyzing writing to generate persona...]
```

### Agent profile page — after upload

```
Name             [ Nate Jones         ]   ← editable
Instructions     [ You are Nate...    ]   ← editable (multi-line, ~500 tokens)
                 [ reasoning style... ]
                 [ core principles... ]

                 [↑ Re-upload]

                 ⚠ Review the fields above before saving.
                   The system prompt is a starting point — refine it to match your intent.
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/profile/upload-document` | Upload user profile document, returns extracted name and bio |
| POST | `/api/company/{id}/upload-document` | Upload company document, returns extracted name and description |
| POST | `/api/agent/{id}/upload-document` | Upload agent document, returns extracted name and instructions (system prompt) |

All endpoints:
- Accept multipart form data
- Return extracted field values (not a saved record — caller saves via the normal profile/company update endpoint)
- Discard the uploaded file after extraction
- Do not create Knowledge Base documents or chunks

---

## Future Extension (post-MVP)

Once the Company profile has more structured fields (mission, business model, goals, constraints — deferred from MVP), the company document upload can be extended to populate all of them, not just name and description. The extraction prompts would expand accordingly. The UX pattern (upload → review generated fields → save) remains identical.

---

## Dependencies

- LLM access via BYOK key — user must have at least one API key configured before linked upload is available. The system selects a generation model matching the user's configured keys (default model preferred, else first available). **The upload button is hidden or disabled until at least one key is saved**, with a tooltip: "Add an API key to enable auto-fill."
- File storage for temporary processing (Supabase Storage, auto-deleted post-extraction)
- Text extraction library (PDF, DOCX, PPTX parsing — same library used by KB ingestion pipeline)
