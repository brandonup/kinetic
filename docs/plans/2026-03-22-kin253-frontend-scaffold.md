# KIN-253: Frontend Scaffold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Kinetic Next.js 14 frontend scaffold ported from FounderPanel — dark teak theme, left-sidebar layout, admin shell with Users/LLM Models/RAG Debug tabs, auth-gated routes.

**Architecture:** Next.js 14 App Router with `(app)/` route group for auth-gated app shell. Admin at `/admin` uses a client-side layout that checks `app_metadata.role === "admin"` from the Supabase JWT. Middleware at the edge redirects unauthenticated users to `/login`. No backend calls required for this ticket — all auth checks are JWT-local.

**Tech Stack:** Next.js 14, TypeScript strict, shadcn/ui, Radix UI, Tailwind CSS, Supabase auth-helpers, vitest + @testing-library/react

---

## Pre-work Assessment (completed)

The scaffold was pre-built. Files in `packages/web/` are complete except for one gap:

| Component | Status |
|---|---|
| `app/layout.tsx` — dark root layout, always-dark | ✅ Done |
| `app/globals.css` — teak/amber theme tokens | ✅ Done |
| `tailwind.config.ts` — teak color palette | ✅ Done |
| `middleware.ts` — edge auth redirect to /login | ✅ Done |
| `app/(app)/layout.tsx` — sidebar + main shell | ✅ Done |
| `components/AppSidebar.tsx` — nav + company switcher placeholder | ✅ Done |
| `app/login/page.tsx` — placeholder (auth wired in KIN-252) | ✅ Done |
| `app/admin/layout.tsx` — admin auth check + nav | ⚠️ Missing RAG Debug tab |
| `app/admin/users/page.tsx` — placeholder | ✅ Done |
| `app/admin/models/page.tsx` — placeholder | ✅ Done |
| `app/admin/rag-debug/page.tsx` — placeholder | ❌ Missing |
| `lib/api.ts` — Kinetic-adapted fetch wrapper + SSE factory | ✅ Done |
| `lib/supabaseClient.ts` — Supabase browser client | ✅ Done |
| `app/__tests__/middleware.test.ts` — middleware config tests | ✅ Done |
| `components.json`, `vitest.config.ts`, `package.json` | ✅ Done |

---

## Task 1: Add RAG Debug tab to admin layout

**Files:**
- Modify: `packages/web/app/admin/layout.tsx`

**Step 1: Update NAV_ITEMS**

Add `{ label: "RAG Debug", href: "/admin/rag-debug", activePrefix: "/admin/rag-debug" }` between LLM Models and Back to App.

**Step 2: Verify the change looks correct**

NAV_ITEMS should read: Users → LLM Models → RAG Debug → Back to App.

---

## Task 2: Create RAG Debug placeholder page

**Files:**
- Create: `packages/web/app/admin/rag-debug/page.tsx`

**Content:**

```tsx
export default function AdminRagDebugPage() {
  return (
    <div className="p-8">
      <h1 className="text-xl font-semibold text-foreground">RAG Debug</h1>
      <p className="text-muted-foreground mt-2 text-sm">
        Retrieval traces and diagnostic tools. Coming in Sprint 6.
      </p>
    </div>
  );
}
```

---

## Task 3: Run tests

```bash
cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/web
./node_modules/.bin/vitest run
```

Expected: all 3 middleware tests pass.

---

## Task 4: TypeScript check

```bash
cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/web
./node_modules/.bin/tsc -p . --noEmit
```

Expected: no errors.

---

## Task 5: Commit

Generate a commit script to `$TMPDIR` (sandbox blocks git directly).

Script copies `packages/web/` to `kinetic3/packages/web/` and commits on branch `brandonup/kin-253-dinesh-port-frontend-scaffold-nextjs-app-router-shadcn-admin`.

---

## Done When

- App boots (verify: `next build` passes or `tsc --noEmit` clean)
- Dark teak theme renders
- Admin shell shows Users, LLM Models, RAG Debug placeholder tabs
- Auth redirect works (middleware exports correct config matcher)
- All vitest tests pass
