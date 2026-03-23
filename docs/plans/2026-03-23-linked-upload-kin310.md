# KIN-310: Linked Upload — User Profile + Company Surfaces

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add backend extraction endpoints and frontend upload/review UI for the User Profile and Company pages, letting users auto-fill name/bio or name/description from an uploaded document via BYOK LLM.

**Architecture:** New `linked_upload.py` FastAPI router at prefix `/api` (no v1 — matches Jìan test URLs). Extraction is stateless: receive file, upload to Supabase temp storage, extract text, call LLM via `LinkedUploadExtractor`, delete temp file, return fields. Frontend adds hidden file input + inline review panel to existing profile and companies pages — no new routes needed.

**Tech Stack:** FastAPI, supabase-py, unstructured (existing), LiteLLM (existing), Next.js 14 App Router, shadcn/ui

---

## Key Decisions

- Router prefix `/api` (not `/api/v1`) — Jìan scaffolding tests call `/api/profile/upload-document`.
- `LinkedUploadExtractor.extract(text, *, prompt_id, key_row, model)` — decrypts BYOK key internally so tests can mock away the whole method without touching encryption.
- `get_llm_client(user_id)` is module-level (patchable at `app.api.routes.linked_upload.get_llm_client`).
- `get_supabase_client()` is module-level (patchable at `app.api.routes.linked_upload.get_supabase_client`).
- File temp-stored in Supabase Storage bucket `linked-upload-temp`; always deleted in `finally` block — even on LLM failure.
- BYOK gate: `HTTPException(400, detail="No API key configured. Add an API key to use this feature.")` — "api key" in `detail.lower()` satisfies the test assertion.
- No DB writes in extraction endpoints — return fields only, caller saves via normal PATCH.
- Agent endpoint (`/api/agent/{id}/upload-document`) included in KIN-310 for shared infrastructure; its tests stay `@pytest.mark.skip(reason="Pending KIN-311 implementation")`.
- Frontend uses inline review panel (no Dialog component available) — matches existing inline edit pattern.

---

## Task 1: Create `linked_upload.py` backend route

**Files:**
- Create: `packages/api/app/api/routes/linked_upload.py`

### Shared constants

```python
TEMP_BUCKET = "linked-upload-temp"
PROFILE_MAX_SIZE = 10 * 1024 * 1024   # 10 MB
COMPANY_MAX_SIZE = 25 * 1024 * 1024   # 25 MB
AGENT_MAX_SIZE   = 25 * 1024 * 1024   # 25 MB

PROFILE_ALLOWED_TYPES = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "text/plain"}
COMPANY_ALLOWED_TYPES = PROFILE_ALLOWED_TYPES | {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.ms-powerpoint", "text/markdown", "text/x-markdown"}
AGENT_ALLOWED_TYPES   = PROFILE_ALLOWED_TYPES | {"text/markdown", "text/x-markdown"}

PROMPT_ID_PROFILE = "generate-user-profile-v1"
PROMPT_ID_COMPANY = "generate-company-profile-v1"
PROMPT_ID_AGENT   = "generate-agent-persona-v1"
```

### Patchable helpers

```python
def get_supabase_client():   return get_supabase()
def get_llm_client(user_id: str) -> "LinkedUploadExtractor":
    return LinkedUploadExtractor(user_id=user_id)
```

### `LinkedUploadExtractor`

```python
class LinkedUploadExtractor:
    def __init__(self, user_id: str): self._user_id = user_id

    def extract(self, text: str, *, prompt_id: str, key_row: dict, model: str = "gpt-4o-mini") -> dict:
        master_key = load_master_key()
        api_key = decrypt_api_key(
            bytes.fromhex(key_row["key_ciphertext"]),
            bytes.fromhex(key_row["key_nonce"]),
            master_key, self._user_id,
        )
        if prompt_id == PROMPT_ID_PROFILE:  return self._profile(text, api_key, model)
        if prompt_id == PROMPT_ID_COMPANY:  return self._company(text, api_key, model)
        if prompt_id == PROMPT_ID_AGENT:    return self._agent(text, api_key, model)
        raise ValueError(f"Unknown prompt_id: {prompt_id!r}")
```

Each `_profile/_company/_agent` method calls `call_llm(messages=[...], model=model, api_key=api_key, max_tokens=..., timeout=25)` twice (name + body field). Prompts verbatim from `docs/feature-linked-upload.md § Extraction Logic`. Returns `{"name": ..., "bio": ...}` / `{"name": ..., "description": ...}` / `{"name": ..., "instructions": ...}`. Truncate bio/description to 1000 chars. Truncate document text to 8000 chars (12000 for agent instructions).

### Shared async helpers

```python
async def _get_first_api_key(client, user_id: str) -> Optional[dict]:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None,
        lambda: client.table("user_api_keys")
            .select("provider, key_ciphertext, key_nonce")
            .eq("user_id", user_id).execute())
    rows = result.data or []
    return rows[0] if rows else None

async def _upload_to_temp_storage(client, content: bytes, filename: str) -> str:
    path = f"{uuid.uuid4()}/{filename}"
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None,
        lambda: client.storage.from_(TEMP_BUCKET).upload(path, content))
    return path

async def _delete_from_temp_storage(client, path: str) -> None:  # best-effort, logs on failure
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None,
            lambda: client.storage.from_(TEMP_BUCKET).remove([path]))
    except Exception as exc:
        logger.warning("Failed to delete temp file %s: %s", path, exc)

def _validate_file(content_type, size, allowed_types, max_size) -> None:
    if content_type not in allowed_types:
        raise HTTPException(400, detail=f"Unsupported file type: {content_type!r}.")
    if size > max_size:
        raise HTTPException(400, detail=f"File too large. Max {max_size // (1024*1024)} MB.")
```

### Route pattern (same for all three endpoints)

```python
@router.post("/profile/upload-document")
async def upload_profile_document(file: UploadFile = File(...), current_user = Depends(get_current_user)):
    client = get_supabase_client()
    key_row = await _get_first_api_key(client, current_user.user_id)
    if key_row is None:
        raise HTTPException(400, detail="No API key configured. Add an API key to use this feature.")
    content = await file.read()
    _validate_file(file.content_type or "", len(content), PROFILE_ALLOWED_TYPES, PROFILE_MAX_SIZE)
    temp_path = await _upload_to_temp_storage(client, content, file.filename or "upload.bin")
    try:
        try:
            text = extract_text(content, file.content_type or "", file.filename or "upload.bin")
        except (UnsupportedFileTypeError, RuntimeError):
            raise HTTPException(422, detail="Couldn't extract content from this file. Try a different format.")
        extractor = get_llm_client(current_user.user_id)
        return extractor.extract(text, prompt_id=PROMPT_ID_PROFILE, key_row=key_row, model="gpt-4o-mini")
    finally:
        await _delete_from_temp_storage(client, temp_path)
```

Repeat for company (`/company/{company_id}/upload-document`, `COMPANY_*` constants, `PROMPT_ID_COMPANY`) and agent (`/agent/{agent_id}/upload-document`, `AGENT_*` constants, `PROMPT_ID_AGENT`).

---

## Task 2: Wire router in `main.py`

**Files:**
- Modify: `packages/api/app/main.py`

```python
from app.api.routes.linked_upload import router as linked_upload_router
...
app.include_router(linked_upload_router)
```

Add after existing `app.include_router(active_memory_admin_router)`.

---

## Task 3: Remove skip markers and run KIN-310 tests

**Files:**
- Modify: `packages/api/tests/test_linked_upload.py`

Remove all `@pytest.mark.skip(reason="Pending KIN-310 implementation")` lines.
**Leave** all `@pytest.mark.skip(reason="Pending KIN-311 implementation")` untouched.

Run:
```bash
cd packages/api && python -m pytest tests/test_linked_upload.py -v 2>&1 | tail -40
```

Expected: All KIN-310 tests pass. KIN-311 tests (agent profile) show as SKIPPED.

---

## Task 4: Wire profile page upload

**Files:**
- Modify: `packages/web/app/(app)/profile/page.tsx`

Add state:
```typescript
const [uploadState, setUploadState] = useState<"idle" | "loading" | "review" | "error">("idle");
const [uploadError, setUploadError] = useState<string | null>(null);
const [extracted, setExtracted] = useState<{ name: string | null; bio: string | null } | null>(null);
const [reviewName, setReviewName] = useState("");
const [reviewBio, setReviewBio] = useState("");
const fileInputRef = useRef<HTMLInputElement>(null);
```

Replace the existing "Auto-fill from Document" section with:
- Hidden `<input type="file" ref={fileInputRef} accept=".pdf,.docx,.doc,.txt" onChange={handleFileSelect} className="hidden" />`
- Upload button `onClick={() => fileInputRef.current?.click()}` disabled when `!hasAnyKey || uploadState === "loading"`
- Loading: replace button text with "Extracting…"
- Review panel (when `uploadState === "review"`): editable name + bio inputs, "Use this" button (sets `name`/`bio` state, calls `saveProfile()`, resets to idle), "Discard" button
- Error: inline `<p className="text-sm text-destructive">{uploadError}</p>`

`handleFileSelect`:
```typescript
async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
  const f = e.target.files?.[0]; if (!f) return;
  setUploadState("loading"); setUploadError(null);
  const form = new FormData(); form.append("file", f);
  try {
    const res = await apiFetch("/api/profile/upload-document", { method: "POST", body: form });
    if (!res.ok) { setUploadError("Couldn't extract content. Try a different file."); setUploadState("error"); return; }
    const data = await res.json();
    setExtracted(data); setReviewName(data.name ?? ""); setReviewBio(data.bio ?? "");
    setUploadState("review");
  } catch { setUploadError("Upload failed. Please try again."); setUploadState("error"); }
  finally { e.target.value = ""; }
}
```

"Use this" handler: `setName(reviewName); setBio(reviewBio); await saveProfile(); setUploadState("idle");`

Remove the `Content-Type: application/json` header concern: `apiFetch` must NOT set Content-Type when body is FormData (browser sets multipart automatically). Check `lib/api.ts` — if it forces `application/json`, pass the FormData without calling apiFetch's JSON wrapper, or use `fetch` directly.

---

## Task 5: Wire companies page upload

**Files:**
- Modify: `packages/web/app/(app)/companies/page.tsx`

Add per-company upload state (keyed by company ID):
```typescript
const [uploadingId, setUploadingId] = useState<string | null>(null);
const [uploadErrorId, setUploadErrorId] = useState<string | null>(null);
const [companyExtracted, setCompanyExtracted] = useState<{ name: string | null; description: string | null } | null>(null);
const companyFileRef = useRef<HTMLInputElement>(null);
const uploadingCompanyId = useRef<string | null>(null);
```

Within the `isEditing` edit form, add below the existing fields:
```tsx
<div className="pt-1">
  <input type="file" ref={companyFileRef} accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md"
    className="hidden" onChange={(e) => handleCompanyFileSelect(e, company.id)} />
  {companyExtracted && uploadingCompanyId.current === company.id ? (
    <div className="space-y-2 rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground font-medium">Review extracted fields</p>
      {/* editable name + description inputs pre-filled from companyExtracted */}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => { setEditName(companyExtracted.name ?? editName); setEditDesc(companyExtracted.description ?? editDesc); setCompanyExtracted(null); }}>Use this</Button>
        <Button size="sm" variant="ghost" onClick={() => setCompanyExtracted(null)}>Discard</Button>
      </div>
    </div>
  ) : (
    <Button variant="outline" size="sm" disabled={uploadingId === company.id}
      onClick={() => { uploadingCompanyId.current = company.id; companyFileRef.current?.click(); }}>
      {uploadingId === company.id ? "Extracting…" : "Auto-fill from document"}
    </Button>
  )}
  {uploadErrorId === company.id && <p className="text-xs text-destructive mt-1">Couldn't extract. Try a different file.</p>}
</div>
```

`handleCompanyFileSelect` mirrors `handleFileSelect` — POST to `/api/company/${companyId}/upload-document`.

Remove the standalone "Auto-fill from Document" section at bottom of page (now per-company in edit form).

---

## Task 6: Check `lib/api.ts` — FormData header handling

**Files:**
- Read: `packages/web/lib/api.ts`

If `apiFetch` sets `Content-Type: application/json` unconditionally, add guard:
```typescript
if (!(options?.body instanceof FormData)) {
  headers["Content-Type"] = "application/json";
}
```

---

## Done When

- [ ] `python -m pytest tests/test_linked_upload.py -v` — all KIN-310 tests pass, KIN-311 tests skipped, 0 failures
- [ ] `python -m pytest tests/ -v` — full suite still passes (131+ tests)
- [ ] Profile upload button fires file picker when key configured, disabled when not
- [ ] After upload: review panel shows extracted fields, "Use this" fills name/bio
- [ ] Companies edit form: "Auto-fill from document" button triggers upload flow per company
- [ ] Inline errors shown on extraction failure (no toast that disappears)
- [ ] TypeScript clean (`./node_modules/.bin/tsc --noEmit` from `packages/web`)
