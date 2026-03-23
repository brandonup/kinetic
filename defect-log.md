# Kinetic Defect Log

_Append-only. One row per Critical or Important finding from code review._

| Date | Ticket | Reviewer | Category | Severity | Description |
| 2026-03-22 | KIN-258 | Gilfoyle | spec-gap | Important | Deleted document leakage: chunks of soft-deleted documents returned during 7-day cleanup window — fallback select missing documents.deleted_at filter |
|---|---|---|---|---|---|
| 2026-03-21 | KIN-244 | Gilfoyle | other | Critical | `cookies()` from `next/headers` imported in Edge runtime route — throws in production Edge deployments |
| 2026-03-21 | KIN-244 | Gilfoyle | api-contract | Critical | Admin layout gates access by fetching `/api/v1/admin/users` data endpoint — conflates data fetch with ACL check |
| 2026-03-21 | KIN-244 | Gilfoyle | other | Important | `darkMode: ["class"]` config undocumented for always-dark intent — future contributor confusion risk |
| 2026-03-21 | KIN-244 | Gilfoyle | other | Important | `resolveApiBaseUrl()` called twice per request — `API_BASE_URL` constant not used internally in `apiFetch` |
| 2026-03-22 | KIN-253 | Gilfoyle | async-supabase | Critical | `@supabase/auth-helpers-nextjs` used in middleware — deprecated package, does not reliably refresh tokens at edge runtime |
| 2026-03-22 | KIN-253 | Gilfoyle | spec-gap | Important | Auth callback always redirects to app root; `redirectTo` param set by middleware is never preserved through magic link or OAuth flow |
| 2026-03-22 | KIN-253 | Gilfoyle | acl-leak | Important | Admin role check runs client-side only; RSC payload for `/admin/*` served to any authenticated non-admin user who fetches directly |
| 2026-03-21 | KIN-244 | Gilfoyle | other | Important | `loading` in `useEffect` dependency array in admin layout causes double-fire on mount |
| 2026-03-22 | KIN-253 | Gilfoyle | acl-leak | Critical | Open redirect in `app/auth/callback/route.ts` — `redirectTo` param not validated; absolute URL bypasses `new URL()` base, allows redirect to arbitrary external domain post-auth |
| 2026-03-22 | KIN-267 | Gilfoyle | error-swallow | Important | log_scrub.py scrub_dict crashes on list-shaped JSON bodies — bare except swallows the error silently |
| 2026-03-22 | KIN-267 | Gilfoyle | api-contract | Important | SSE createStreamEventSource passes message content in URL query param — will hit URL length limits on long messages |
