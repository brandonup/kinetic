# Kinetic Defect Log

_Append-only. One row per Critical or Important finding from code review._

| Date | Ticket | Reviewer | Category | Severity | Description |
| 2026-03-23 | KIN-319 | Gilfoyle | api-contract | Critical | `PATCH /{agent_id}/instance` queries `agent_instances.id` with agent_definition UUID — wrong column, always 404 in production |
| 2026-03-23 | KIN-319 | Gilfoyle | acl-leak | Important | `get_or_create_instance` had no agent access check — any user could create instances for private or nonexistent agents |
| 2026-03-23 | KIN-319 | Gilfoyle | acl-leak | Important | `list_frameworks` returned 403 for private non-owner agents, leaking agent existence (should be 404) |
| 2026-03-23 | KIN-319 | Gilfoyle | other | Important | `framework_overrides` accepted as bare `dict` — no shape validation on pinned/excluded fields |
| 2026-03-23 | KIN-319 | Gilfoyle | error-swallow | Important | AgentProfilePage: network errors / 500s shown as "Agent not found" — no differentiation from 404 |
| 2026-03-23 | KIN-310 | Gilfoyle | error-swallow | Important | extract_text RuntimeError caught silently; returns HTTP 200 with null fields instead of 422 error state |
| 2026-03-23 | KIN-310 | Gilfoyle | other | Important | Company "Use this" uses `\|\|` operator — drops intentionally-cleared extracted fields, silently reverts to pre-upload value |
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
| 2026-03-23 | KIN-308 | Gilfoyle | api-contract | Critical | review_proposals response omits spec-required token_usage field — UI cannot update token bar after proposal review |
| 2026-03-23 | KIN-308 | Gilfoyle | error-swallow | Critical | ProposalDecision.action unconstrained str — invalid action silently drops proposal_id from results array with no error |
| 2026-03-23 | KIN-308 | Gilfoyle | spec-gap | Important | test_create_empty_content_422 asserts 422 but spec says 400 for empty content — test documents wrong contract |
| 2026-03-23 | KIN-308 | Gilfoyle | api-contract | Important | update_entry raises MemoryCapExceededError with current_total - old_tokens instead of current_total — error message reports artificially low usage |
| 2026-03-23 | KIN-310 | Gilfoyle | spec-gap | Critical | Supabase Storage used for temp files despite explicit pre-impl ban (KIN-312) — storage upload never read back, adds latency + orphan risk for zero benefit |
| 2026-03-23 | KIN-307 | Gilfoyle | schema-mismatch | Critical | Agent-scoped conversations write project_id to memory_proposals instead of agent_instance_id — active_agent_id fetched but ignored; dedup query also scoped wrong |
| 2026-03-23 | KIN-307 | Gilfoyle | other | Critical | bytes.fromhex() called on bytea columns returned as bytes by Supabase — crashes all real BYOK key decryption silently, disabling proposal generation for all keyed users |
| 2026-03-23 | KIN-307 | Gilfoyle | spec-gap | Important | Conversation fetch missing deleted_at IS NULL filter — soft-deleted conversations can receive proposals |
| 2026-03-23 | KIN-307 | Gilfoyle | error-swallow | Important | Per-proposal insert().execute() not wrapped — DB write failure crashes loop mid-run with no logging or partial-insert visibility |
| 2026-03-23 | KIN-307 | Gilfoyle | test-missing | Important | No test for agent-scoped path, soft-deleted conversation, LLM failure silent-skip, or real bytes decryption |
| 2026-03-23 | KIN-306 | Gilfoyle | async-supabase | Critical | bytes.fromhex() on bytea columns in _generate_periodic_proposals_job — crashes every real BYOK key decryption, silently disabling periodic proposals for all keyed users |
| 2026-03-23 | KIN-306 | Gilfoyle | schema-mismatch | Critical | Agent-scoped conversations write project_id instead of agent_instance_id to memory_proposals — active_agent_id fetched but ignored; violates polymorphic constraint |
| 2026-03-23 | KIN-306 | Gilfoyle | spec-gap | Important | Soft-deleted conversation not filtered (missing deleted_at IS NULL) in store_message ownership check and periodic job conversation fetch |
| 2026-03-23 | KIN-306 | Gilfoyle | error-swallow | Important | Per-proposal insert().execute() unwrapped in _generate_periodic_proposals_job — DB failure crashes loop silently with no log and partial insert |
| 2026-03-23 | KIN-306 | Gilfoyle | test-missing | Important | Missing count=20 boundary test; no agent-scoped job test; no trigger_type assertion on inserted rows |
| 2026-03-23 | KIN-320 | Gilfoyle | api-contract | Important | PATCH /{agent_id}/frameworks/{framework_id} path param named `framework_id` but queries by DB UUID (`frameworks.id`) — naming mismatch will cause future client wiring errors |
| 2026-03-23 | KIN-320 | Gilfoyle | error-swallow | Important | upload_frameworks update path omits `source_posts` from field list — silently drops source_posts updates on re-upload of extracted frameworks |
| 2026-03-23 | KIN-320 | Gilfoyle | other | Important | handleFormSave sends empty PATCH body with no guard — spurious DB write and misleading "Framework saved" toast when user saves without changes |
| 2026-03-23 | KIN-320 | Gilfoyle | other | Important | loadFrameworks after upload swallows network errors — stale list shown with no toast if refresh fails post-upload |
