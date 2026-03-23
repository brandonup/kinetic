# KIN-244: Frontend Scaffold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Port and adapt FounderPanel's Next.js 14 frontend scaffold into `projects/kinetic/packages/web/`, applying Kinetic's dark/teak theme and new nav structure.

**Architecture:** Next.js 14 App Router with a route-group `(app)` for authenticated app shell and `/admin` for the admin panel. Auth protection via Next.js `middleware.ts` using Supabase session. SSE proxied through a Next.js Edge route to inject JWT before forwarding to FastAPI.

**Tech Stack:** Next.js 14, TypeScript (strict), shadcn/ui, Radix UI, Tailwind CSS v3, Supabase JS client v2, Vitest

---

### Task 1: Scaffold package directory and config files

**Files:**
- Create: `projects/kinetic/packages/web/package.json`
- Create: `projects/kinetic/packages/web/tsconfig.json`
- Create: `projects/kinetic/packages/web/next.config.js`
- Create: `projects/kinetic/packages/web/postcss.config.js`
- Create: `projects/kinetic/packages/web/tailwind.config.ts`
- Create: `projects/kinetic/packages/web/components.json`
- Create: `projects/kinetic/packages/web/.env.local.example`
- Create: `projects/kinetic/packages/web/vitest.config.ts`
- Create: `projects/kinetic/packages/web/vitest.setup.ts`

### Task 2: Install dependencies

```bash
cd projects/kinetic/packages/web
pnpm install --ignore-scripts
```

### Task 3: globals.css — dark-first Kinetic theme

`--primary` = teak/amber (`30 70% 47%`). Background = very dark slate (`222 25% 7%`). Always dark — no `.dark` toggle needed because `<html class="dark">` is forced.

### Task 4: Supabase client and utils

- `lib/supabaseClient.ts` — port from FounderPanel unchanged
- `lib/utils.ts` — shadcn `cn()` helper

### Task 5: API client (lib/api.ts)

- Core fetch infra: `apiFetch`, `parseApiError`, `resolveApiBaseUrl`, `createStreamEventSource`
- Strip all FounderPanel-specific APIs
- `createStreamEventSource` params renamed to Kinetic domain: `conversationId` (not `session_id`), `agentInstanceId`
- Tests: `app/__tests__/lib/api.test.ts`

### Task 6: shadcn/ui components

Port from FounderPanel: `badge`, `button`, `card`, `input`, `label`, `progress`, `switch`, `textarea`, `toast`, `toaster`, `use-toast`.
Add new: `separator`, `scroll-area`, `tooltip`.

### Task 7: Auth middleware

`middleware.ts` — protects all routes except `/login`, `/api/*`, `/_next/*`. Redirects to `/login?redirectTo=...` if no session.

Tests: `app/__tests__/middleware.test.ts`

### Task 8: App shell — layout + AppSidebar

- `app/layout.tsx` — root layout, forces `class="dark"` on `<html>`
- `app/(app)/layout.tsx` — flex row: `AppSidebar` + `<main>`
- `components/AppSidebar.tsx` — left sidebar: company switcher placeholder, nav (Projects, Agents, Profile), conversation history placeholder

Tests: `app/__tests__/components/AppSidebar.test.tsx`

### Task 9: Admin shell layout

`app/admin/layout.tsx` — checks admin role via API, tabs: Users + LLM Models.

Tests: `app/__tests__/admin/layout.test.tsx`

### Task 10: Stub pages

- `app/(app)/page.tsx` — redirect to /projects
- `app/(app)/projects/page.tsx` — stub
- `app/(app)/agents/page.tsx` — stub
- `app/(app)/profile/page.tsx` — stub
- `app/login/page.tsx` — placeholder (auth wired in KIN-243)
- `app/admin/users/page.tsx` — stub
- `app/admin/models/page.tsx` — stub

### Task 11: SSE proxy route

`app/api/stream/route.ts` — Edge runtime. Port from FounderPanel, update backend path to `/api/v1/chat/stream`.

Tests: `app/__tests__/api/stream/route.test.ts`

### Task 12: Verify app boots

```bash
./node_modules/.bin/vitest run          # all tests pass
./node_modules/.bin/tsc -p . --noEmit   # no type errors
./node_modules/.bin/next build          # build succeeds
```

### Task 13: Commit

```
feat: scaffold Kinetic frontend (Next.js 14, shadcn/ui, dark theme, app shell) [KIN-244]
```

If sandbox blocks git: write `/private/tmp/claude-501/commit-kin-244.sh` immediately.
