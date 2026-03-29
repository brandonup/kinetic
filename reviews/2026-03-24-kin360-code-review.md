# KIN-360 — Consolidated Migration Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**File:** `packages/api/migrations/000_complete_schema.sql`
**Spec:** `docs/db-schema-spec.md`
**Verdict:** Changes requested — 2 Critical, 3 Important, 3 Informational

---

## Critical (2)

### C1. `users` table: column `display_name` should be `name`, and `bio` column is missing

**Spec §1** defines `name text NOT NULL` and `bio text CHECK (char_length(bio) <= 1000)`.

Migration creates `display_name text` (nullable, no NOT NULL) and has no `bio` column at all.

**Runtime impact:** The API code queries `users.name` and `users.bio` in multiple places:
- `mcp.py:259` — `.select("id, name, bio")` for L1 context assembly
- `profile.py:102` — `.select("id, name, bio, default_model_id")` for profile fetch

With the migration as-is, these queries will return `null` for both fields (Supabase/PostgREST silently ignores non-existent column names in select). MCP context will show "User: " with no name. Profile page will be blank.

**Fix:**
```sql
-- Replace:
display_name text,
-- With:
name text NOT NULL,
bio text CHECK (char_length(bio) <= 1000),
```

Remove `avatar_url` and `onboarding_complete` — they are not in the spec. If they're needed, add them to the spec first.

Also add `email` to the spec if it's intentional (Supabase `auth.users` has email, but the spec says public.users extends it via same ID — unclear if email should be duplicated).

### C2. Missing `handle_new_user()` trigger on `auth.users`

**Spec §Auth User Trigger** defines a `SECURITY DEFINER` function that creates a `public.users` row when a new user signs up via Supabase Auth. The migration does not include this function or trigger.

**Runtime impact:** Without this trigger, new signups will have an `auth.users` row but no `public.users` row. Every API call will fail — `get_current_user` extracts `user_id` from JWT, then any profile/company/project query against `public.users` returns empty.

**Fix:** Add to the migration:
```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.users (id, name, role)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'name', NEW.email), 'user');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

Note: This requires `auth` schema access. If Supabase blocks direct trigger creation on `auth.users`, Brandon may need to create this via the Supabase dashboard SQL editor (not the migration runner).

---

## Important (3)

### I1. `users` RLS missing admin SELECT override

**Spec §1 RLS:** "SELECT/UPDATE: `auth.uid() = id` (own row) OR role = `admin` (all rows)"

Migration only has `users_select_own`: `auth.uid() = id` — no admin override.

**Impact:** The `admin_users` route uses service-role client (bypasses RLS), so this doesn't break functionality. But the spec explicitly requires admin-level RLS policies, and if any future code uses anon/user-role client for admin queries, it will fail silently.

**Fix:** Add admin SELECT policy:
```sql
DO $$ BEGIN CREATE POLICY "users_select_admin" ON public.users
  FOR SELECT USING (EXISTS (
    SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin'
  ));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
```

### I2. `mcp_tokens` UPDATE policy denies all — spec allows user update (for `last_used_at`)

Migration line 394: `mcp_tokens_update_deny USING (false)` — denies all UPDATE.

**Spec §18 RLS:** Lists SELECT/INSERT/DELETE for `auth.uid() = user_id`. Does not list UPDATE, but also doesn't deny it.

**Impact:** The API uses service-role for `last_used_at` and `revoked_at` updates (bypasses RLS), so this works. But the explicit deny is stricter than what the spec describes. This is actually correct security posture — document it as intentional.

**Action:** No code change needed. Add a comment to the spec: "UPDATE: service role only (token metadata updates bypass RLS)."

### I3. Missing vector search RPC functions (`match_chunks`, `match_framework_triggers`)

The RAG pipeline calls `supabase.rpc("match_chunks", ...)` (retrieval.py:243) and `supabase.rpc("match_framework_triggers", ...)` (framework_selection.py:79). The consolidated migration does not include these functions.

The `mcp_check_and_increment_rate_limit` RPC is in a separate migration (`supabase/migrations/20260324000000_mcp_rate_limit_rpc.sql`).

**Impact:** Without these functions, RAG retrieval falls back to the client-side cosine similarity path (retrieval.py:259–292), which works but is slower and doesn't use pgvector indexes efficiently. Framework selection will fail with a warning and omit L7.

**Fix:** Create these RPC functions. They should be part of the migration set (either in this file or a companion `001_rpc_functions.sql`). The function bodies need to:
1. Accept `query_embedding vector(3072)`, scope filter params, and `match_count int`
2. Perform `ORDER BY embedding <=> query_embedding LIMIT match_count` with scope filter
3. Return `id, document_id, text, embedding, chunk_index, section_path, page_range, similarity, document_title, document_type`

---

## Informational (3)

### N1. Extra columns on `users`: `email`, `avatar_url`, `onboarding_complete`

The migration includes `email text NOT NULL UNIQUE`, `avatar_url text`, and `onboarding_complete boolean NOT NULL DEFAULT false`. None of these are in the spec.

`email` is reasonable — duplicating from `auth.users` for easier querying. `avatar_url` and `onboarding_complete` may be from FounderPanel lineage.

**Action:** Either add these to the spec (if intentional) or remove from the migration. No runtime breakage either way — the API doesn't query these columns.

### N2. IVFFlat `lists = 10` is appropriate for MVP

At ~20K chunks (MVP ceiling), IVFFlat with `lists = 10` gives ~2000 rows per list. The rule of thumb is `lists ≈ sqrt(rows)` (~141 for 20K), but at MVP scale the difference is negligible. The indexes will need retuning when data grows past ~100K chunks.

### N3. Table ordering in migration differs from spec migration order

The migration creates `knowledge_bases` (4.18) after `retrieval_debug_logs` (4.17), while the spec puts knowledge tables (§10–13) before frameworks (§14–15). This doesn't cause FK issues — all referenced tables exist before they're needed. The ordering is valid.

---

## Checklist Summary

| Check | Status | Notes |
|---|---|---|
| All 21 spec tables present | **PASS** | All accounted for |
| Column names match spec | **FAIL** | C1: `display_name` vs `name`, missing `bio` |
| Column types match spec | **PASS** | All types correct where columns exist |
| Constraints match spec | **PASS** | Polymorphic checks, unique constraints all present |
| RLS policies match spec | **PARTIAL** | I1: missing admin SELECT on users |
| IVFFlat config appropriate | **PASS** | lists=10 fine for MVP scale |
| FK dependency order correct | **PASS** | No forward references |
| No security issues | **PARTIAL** | C2: missing auth trigger means no users created |
| Idempotency guards | **PASS** | IF NOT EXISTS + DO/EXCEPTION throughout |

---

**Do not run this migration until C1 and C2 are fixed.** The `users.name`/`bio` mismatch will break profile and MCP endpoints. The missing auth trigger will break signup entirely.

— Gilfoyle
