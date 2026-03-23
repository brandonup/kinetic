# Framework Library Spec

**Owner:** Jared
**Sprint:** 6 (implementation by Dinesh — UI; preceded by Gilfoyle review)
**Status:** Draft
**Tickets:** KIN-280

---

## 1. Overview

The Framework Library is the UI and API for managing an agent's frameworks — browsing, manual editing, deletion, and JSON bulk upload with merge behavior. Frameworks are the structured knowledge objects that feed the 4-step framework selection pipeline at query time.

Each framework belongs to an `AgentDefinition`. An agent can have many frameworks.

---

## 2. Framework Schema

```json
{
  "id": "string (uuid, owner-assigned or generated)",
  "name": "string",
  "when_to_apply": ["string", "..."],
  "category": "string (open taxonomy — not a fixed list)",
  "example_application": "string",
  "related_frameworks": ["string (framework id)", "..."],
  "confidence": "number (0.0–1.0)",
  "origin": "string (e.g. 'manual', 'upload', 'generated')"
}
```

**Field notes:**
- `when_to_apply`: array of trigger phrases. Each phrase is embedded separately at upload time for cosine similarity search. Required and non-empty.
- `category`: free-text. The taxonomy is open — no fixed enum. Used for expertise boost in the selection pipeline.
- `confidence`: float 0.0–1.0. Author-assigned signal of how reliable the framework is.
- `origin`: informational only. Not used in pipeline logic.
- `related_frameworks`: array of sibling framework IDs. Informational, not used in selection pipeline at MVP.

---

## 3. API Endpoints

All endpoints scoped to an agent: `/api/v1/agents/{agent_id}/frameworks`

Auth: `get_current_user`. Owner of the `AgentDefinition` only for write operations. Read operations: same visibility rules as the agent (public agents → any authenticated user can read frameworks).

### 3.1 List frameworks

```
GET /api/v1/agents/{agent_id}/frameworks
```

**Query params:**
- `category` (optional) — filter by category (case-insensitive match)
- `search` (optional) — filter by name substring

**Response 200:**
```json
{
  "frameworks": [
    {
      "id": "uuid",
      "name": "string",
      "category": "string",
      "confidence": 0.85,
      "trigger_count": 3,
      "origin": "upload",
      "created_at": "ISO",
      "updated_at": "ISO"
    }
  ]
}
```

`trigger_count` = length of `when_to_apply` array. Full `when_to_apply` content not returned in list — only in single-framework GET.

No pagination in MVP.

### 3.2 Get framework

```
GET /api/v1/agents/{agent_id}/frameworks/{framework_id}
```

**Response 200:** full framework object including `when_to_apply`, `example_application`, `related_frameworks`.

### 3.3 Create framework (manual)

```
POST /api/v1/agents/{agent_id}/frameworks
```

**Request body:**
```json
{
  "name": "string (required)",
  "when_to_apply": ["string", "..."],
  "category": "string",
  "example_application": "string",
  "related_frameworks": [],
  "confidence": 0.8,
  "origin": "manual"
}
```

**Validation:**
- `name` required, ≤200 chars
- `when_to_apply` required, non-empty array, each item ≤500 chars
- `confidence` must be 0.0–1.0 if provided (default: 0.8)

**On success:** 201 with created framework. Trigger embedding job fired in background.

### 3.4 Update framework

```
PATCH /api/v1/agents/{agent_id}/frameworks/{framework_id}
```

Partial update — only provided fields are updated. Owner only.

If `when_to_apply` is updated, re-embedding job fires in background for affected triggers.

**Response 200:** updated framework object.

### 3.5 Delete framework

```
DELETE /api/v1/agents/{agent_id}/frameworks/{framework_id}
```

Owner only. Deletes the framework row and removes its trigger vectors from pgvector. Hard delete — no soft delete.

**Response 204.**

### 3.6 Bulk upload (JSON merge)

```
POST /api/v1/agents/{agent_id}/frameworks/upload
```

**Request:** `multipart/form-data` with field `file` (`.json`).

**File format:** JSON array of framework objects. Each object must include at minimum `id`, `name`, `when_to_apply`.

#### Merge behavior

| Condition | Action |
|-----------|--------|
| `id` matches existing framework | Update — overwrite all provided fields |
| `id` is new (not in existing set) | Add — insert as new framework |
| `id` exists in DB but not in upload | Retain — not deleted |

Upload never deletes frameworks. Missing from upload = retained as-is.

#### Validation

Each framework in the upload is validated independently. Partial import is allowed: valid frameworks are imported even if others fail.

**Response 200:**
```json
{
  "summary": {
    "added": 3,
    "updated": 2,
    "failed": 1,
    "retained": 5
  },
  "errors": [
    {
      "id": "framework-uuid-or-index",
      "error": "when_to_apply is required"
    }
  ]
}
```

Trigger embedding job fires in background for all added/updated frameworks.

---

## 4. Vector Management

### Trigger embedding

Each `when_to_apply` trigger phrase is embedded separately using `text-embedding-3-large` (platform-owned key, not BYOK).

**When embedding fires:**
- Framework created (manual or upload)
- Framework `when_to_apply` updated

**Implementation:** background job via `TaskDispatcher`. Does not block the API response.

**Failure handling:** if embedding fails for a trigger, mark that trigger as `embedding_status = 'failed'` in the DB. The framework selection pipeline ignores unembedded triggers. Retry on next update to the framework.

### Delete cascade

On framework delete, all trigger vectors for that framework are removed from pgvector. Must complete synchronously before 204 is returned (or be tracked to completion).

---

## 5. Framework Browsing UI

**Location:** Agent Profile → Framework Library tab
*(Tab was a stub in Sprint 4 — activated in Sprint 6)*

### Table view

Columns: Name, Category (tag badge), Confidence (percentage badge), Trigger count, Origin, Actions

- **Search:** text input filtering by name (client-side, no pagination)
- **Filter by category:** dropdown populated from distinct categories present in the agent's frameworks
- **No pagination** in MVP

### Empty state

"No frameworks yet. Upload a JSON file or add one manually."

Two CTAs: "Upload JSON" + "Add manually"

---

## 6. Framework Edit UI

Triggered by clicking a framework row or an "Edit" action.

**Form fields:**
- `name` — text input
- `when_to_apply` — list of trigger phrases, each editable inline. Add/remove phrase buttons.
- `category` — free-text input (no dropdown — open taxonomy)
- `example_application` — textarea
- `confidence` — number input 0–100 (displayed as percentage, stored as 0.0–1.0)

Save calls `PATCH /api/v1/agents/{agent_id}/frameworks/{framework_id}`.

If `when_to_apply` changed, show inline note: "Trigger embeddings will be updated in the background."

---

## 7. Framework Delete

"Delete" action on a framework row opens a confirm dialog:

> "Delete **{framework name}**? This will remove the framework and its trigger vectors. This cannot be undone."

Buttons: Cancel | Delete

On confirm: calls `DELETE` endpoint. On success: remove row from table. On error: show inline error toast.

---

## 8. JSON Upload Flow

1. User clicks "Upload JSON" → file picker (accepts `.json` only)
2. File selected → call `POST /upload`
3. **Pending state:** spinner, "Validating…"
4. **Response received:** show import summary modal:

   > **Import Summary**
   > 3 frameworks added
   > 2 frameworks updated
   > 5 frameworks retained
   > 1 failed — see errors below
   >
   > Errors:
   > • `framework-id-xyz`: `when_to_apply` is required

5. Buttons: **Cancel** (discard, no changes applied) | **Apply import** (confirm)

   — Wait, clarification: the upload endpoint applies immediately (no two-phase confirm). The summary modal is informational. The "Apply" button is just "Close" / "Done". Failed frameworks were not imported; successful ones already are.

   → Revised: summary modal shows what was applied. "OK" closes it. No second confirm step.

6. Table refreshes after modal closes.

---

## 9. Access Control Summary

| Operation | Who |
|-----------|-----|
| List / read frameworks | Owner + any authenticated user (if agent is public) |
| Create, update, delete, upload | Owner only |
| Trigger embedding | Backend only (platform key) |

---

## 10. Open Questions

None. Spec is complete for Gilfoyle pre-implementation review.
