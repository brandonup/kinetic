# Kinetic Defect Log

_Append-only. One row per Critical or Important finding from code review._

| Date | Ticket | Reviewer | Category | Severity | Description |
| 2026-05-21 | KIN-478 | Dinesh | untested-infra | Critical | `match_chunks` RPC bound `scope_value` as `text` but scope columns are `uuid` — `operator does not exist: uuid = text` on every call; MCP/API KB search returned zero results since KIN-476. Shipped because the RPC was created but never invoked. Fixed in `20260521000001` (`$2::uuid`); `database-migrations.md` rule 2a added. |
| 2026-04-03 | KIN-454 | Gilfoyle | other | Important | Debug console.log in `index.ts:183-184` logs userId and prompt list to Edge Function logs on every `prompts/list` call — minor info leak, remove before deploy |
| 2026-03-28 | KIN-407 | Bachman | untested-infra | High | KB ingestion jobs stalling at pending/extracting/embedding stages; stale job timeout monitor catching silent failures. storage_uri NULL on all documents. Complex-tier — routed to Gilfoyle for diagnosis, Dinesh for fix (KIN-408). |
| 2026-03-26 | KIN-388 | Gilfoyle | other | Critical | `run_in_executor` call for periodic proposal job not awaited or `ensure_future`'d — job silently never executes in production |
| 2026-03-26 | KIN-388 | Gilfoyle | test-missing | Important | `TestPeriodicProposalTriggerFires` asserts `mock_job.called` which only passes due to sync test harness behavior, not production async path; test comment describes wrong sequence arithmetic |
| 2026-03-25 | KIN-372 | Gilfoyle | schema-mismatch | Critical | Override arrays stored `f.id` (row UUID) instead of `f.framework_id` (stable semantic ID) — breaks overrides on re-import; violates ADR-003 §5 |
| 2026-03-25 | KIN-366 | Gilfoyle | schema-mismatch | Critical | Chunks queried from non-existent table `document_chunks`; correct table is `knowledge_base_chunks`; column `chunk_text` does not exist, correct column is `text` |
| 2026-03-25 | KIN-366 | Gilfoyle | schema-mismatch | Critical | `knowledge_base_id` selected from `agent_definitions` — column does not exist in schema; KB must be found via `knowledge_bases.agent_definition_id` FK |
| 2026-03-25 | KIN-366 | Gilfoyle | test-missing | Critical | Frontend tests for agent profile page (4 cases per plan) not implemented |
| 2026-03-25 | KIN-366 | Gilfoyle | spec-gap | Important | Model hardcoded to `gpt-4o-mini`; spec §7 requires user's default model |
| 2026-03-25 | KIN-366 | Gilfoyle | schema-mismatch | Critical | R2: `knowledge_base_id` still selected from `agent_definitions`; column absent from migration DDL and db-schema-spec.md §8; comment pointing to agents.md §2 is not a fix — canonical schema wins on conflict |
| 2026-03-24 | KIN-337 | Gilfoyle | other | Important | ModelSelector listbox missing aria-activedescendant — screen readers cannot announce focused option during ArrowUp/Down keyboard navigation |
| 2026-03-24 | KIN-337 | Gilfoyle | schema-mismatch | Critical | ChatCitation.document_title and ChatMessageRecord.citations[] have no backing column in messages table or retrieval_debug_logs schema (§6, §20) |
| 2026-03-24 | KIN-337 | Gilfoyle | other | Critical | ModelSelector listbox ARIA pattern invalid — role="option" on <button> elements, missing aria-haspopup + aria-controls, no keyboard focus trap or Escape handler |
| 2026-03-24 | KIN-337 | Gilfoyle | other | Important | ModelSelector dropdown has no outside-click or Escape dismiss handler — stays open on click-away |
| 2026-03-24 | KIN-337 | Gilfoyle | schema-mismatch | Important | ChatMessageRecord.agent_name is a join-resolved field with no messages column — not documented, will cause schema confusion in API implementation |
| 2026-03-24 | KIN-346 | Gilfoyle | error-swallow | Important | KnowledgeBaseTab !res.ok path discards HTTP status and response body without logging |
| 2026-03-23 | KIN-319 | Gilfoyle | api-contract | Critical | `PATCH /{agent_id}/instance` queries `agent_instances.id` with agent_definition UUID — wrong column, always 404 in production |
| 2026-03-23 | KIN-319 | Gilfoyle | acl-leak | Important | `get_or_create_instance` had no agent access check — any user could create instances for private or nonexistent agents |
| 2026-03-23 | KIN-319 | Gilfoyle | acl-leak | Important | `list_frameworks` returned 403 for private non-owner agents, leaking agent existence (should be 404) |
| 2026-03-23 | KIN-319 | Gilfoyle | other | Important | `framework_overrides` accepted as bare `dict` — no shape validation on pinned/excluded fields |
| 2026-03-23 | KIN-319 | Gilfoyle | error-swallow | Important | AgentProfilePage: network errors / 500s shown as "Agent not found" — no differentiation from 404 |
| 2026-03-23 | KIN-325 | Gilfoyle | other | Critical | `revoked_at` set to literal string `"now()"` instead of `datetime.now(timezone.utc).isoformat()` — stores garbage timestamp in DB |
| 2026-03-23 | KIN-325 | Gilfoyle | api-contract | Important | `create_token` raises `ValidationError` (400) on internal insert failure — should be `AppException` (500) |
| 2026-03-23 | KIN-325 | Gilfoyle | spec-gap | Important | Token list does not show masked `mcp_••••••••` value per ticket spec — needs product decision on token_prefix or AC update |
| 2026-03-23 | KIN-327 | Gilfoyle | acl-leak | Important | linked_upload.py: company_id and agent_id path params never verified as belonging to current_user — unvalidated IDOR pattern |
| 2026-03-23 | KIN-327 | Gilfoyle | other | Important | linked_upload.py: extraction prompts hardcoded inline in _extract_* methods — not in prompts module, unversionable |
| 2026-03-23 | KIN-327 | Gilfoyle | acl-leak | Minor | conversations.py: end_conversation dispatches background job without verifying conversation ownership |
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
| 2026-03-23 | KIN-325 | Gilfoyle | error-swallow | Important | revoke_token raises NotFoundError on empty update_result after confirmed fetch — should be AppException(INTERNAL_ERROR) (race condition path, not user-facing in normal operation) |
| 2026-03-23 | KIN-321 | Gilfoyle | acl-leak | Critical | mcp.py: no ownership/visibility check on project, company, or agent after fetch — any MCP token can read any entity by UUID |
| 2026-03-23 | KIN-321 | Gilfoyle | other | Critical | mcp.py: rate limiting (mcp_rate_limits UPSERT + 429 path) entirely absent — ADR-006 §3 requirement not implemented |
| 2026-03-23 | KIN-321 | Gilfoyle | other | Important | mcp.py: company row fetched even when project_id also present — wasted DB query, spurious 404 if company UUID invalid while project wins L3 |
| 2026-03-23 | KIN-326 | Gilfoyle | rls-bypass | Critical | RLS SELECT policy uses `auth.jwt() ->> 'role'` — not a real JWT claim; evaluates to NULL/false for all users including admins |
| 2026-03-23 | KIN-326 | Gilfoyle | error-swallow | Critical | Both admin_rag_debug route handlers missing try/except on run_in_executor Supabase calls — unhandled exceptions surface as raw 500s with no error shape |
| 2026-03-23 | KIN-326 | Gilfoyle | test-missing | Important | WRITER_PATCH constant in test file is dead code — patch target `trace_writer.get_supabase` does not exist in the module |
| 2026-03-23 | KIN-326 | Gilfoyle | other | Important | Fragment key missing on outer `<>` in traces.map() — React key warning in development builds |
| 2026-03-23 | KIN-326 | Gilfoyle | api-contract | Important | scope query param unvalidated — accepts arbitrary strings, returns empty list instead of 422 |
| 2026-03-23 | KIN-326 | Gilfoyle | spec-gap | Important | Spec §2 annotates next_cursor as "uuid" but implementation emits ISO-8601 timestamp |
| 2026-03-24 | KIN-321 | Gilfoyle | api-contract | Critical | Rate limit UPSERT is non-atomic (check-then-act); diverges from ADR-006 §3 prescribed atomic DO UPDATE SET increment |
| 2026-03-24 | KIN-321 | Gilfoyle | error-swallow | Important | _check_rate_limit UPSERT has no try/except or log — write failure propagates as unhandled 500 instead of fail-open with warning |
| 2026-03-24 | KIN-324 | Gilfoyle | acl-leak | Critical | 403 for unauthorized entities enables UUID enumeration — should be 404 to prevent information leak |
| 2026-03-24 | KIN-324 | Gilfoyle | spec-gap | Important | Spec §6.3 references nonexistent company_members table — schema only has companies.user_id |
| 2026-03-23 | KIN-323 | Gilfoyle | spec-gap | Important | Spec §7 requires X-RateLimit-* headers on all MCP responses; implementation only adds them on 429 |
| 2026-03-24 | KIN-322 | Gilfoyle | spec-gap | Critical | Haiku reranker (framework selection step 3) omitted from implementation without spec update or approval |
| 2026-03-24 | KIN-322 | Gilfoyle | api-contract | Important | retrieve() expects scope_id: UUID but MCP route passes str — type mismatch |
| 2026-03-24 | KIN-322 | Gilfoyle | other | Important | Framework selection fallback path returns meaningless scores (0.0 similarity, selects by trigger count) |
| 2026-03-24 | KIN-322 | Gilfoyle | test-missing | Important | framework_selection.py (170 lines) has zero unit tests — only MCP integration coverage |
| 2026-03-24 | KIN-336 | Gilfoyle | error-swallow | Critical | Storage upload + storage_uri update batched in single swallowed try/except at upload; upload failure silently leaves document unretriable without surfacing to the user |
| 2026-03-24 | KIN-336 | Gilfoyle | spec-gap | Important | `indexing` stage in run_ingestion docstring not in document_status enum; indexer outside retry wrapper — failure leaves document stuck in `embedding` with no error_stage or error_message |
| 2026-03-24 | KIN-336 | Gilfoyle | test-missing | Important | No test coverage for retry Storage fallback path (extracted text unavailable → full re-extraction, both unavailable → 500) |
| 2026-03-23 | KIN-336 | Gilfoyle | error-swallow | Important | Status reset write in retry endpoint has no try/except or logging — bare failure leaves document in corrupted state (chunks deleted, status stuck) with no diagnostics |
| 2026-03-24 | KIN-338 | Gilfoyle | other | Critical | Chunk cleanup runs before atomic status lock — concurrent retry can delete chunks currently being written by a racing pipeline |
| 2026-03-24 | KIN-338 | Gilfoyle | acl-leak | Critical | Status check before ownership check in retry endpoint — any authenticated user can probe document ingestion state by document_id |
| 2026-03-24 | KIN-338 | Gilfoyle | other | Important | `asyncio.get_event_loop()` (deprecated Python 3.10+) used in test _run helper — should be `asyncio.run()` |
| 2026-03-24 | KIN-338 | Gilfoyle | test-missing | Important | `TestRetryDedup` KB ownership mock chain is fragile and does not reliably exercise the ownership verification path |
| 2026-03-24 | KIN-346 | Gilfoyle | error-swallow | Important | KnowledgeBaseTab fetchDocuments catch block swallows error with no log — set bare catch binding and add console.error before setError |
| 2026-03-24 | KIN-346 | Gilfoyle | error-swallow | Important | useDocumentStatus fetchStatus catch block swallows error with no log — no console.error before setError |
| 2026-03-24 | KIN-346 | Gilfoyle | test-missing | Important | useDocumentStatus hook has no direct unit tests — polling stop-on-terminal-status, interval cleanup on unmount, and retry-to-pending transition are untested at hook level |
| 2026-03-24 | KIN-345 | Gilfoyle | test-missing | Important | KnowledgeBaseTab and TagEditor have no dedicated frontend test files — folder CRUD actions, tag filtering, and tag add/remove/save are untested at component level |
| 2026-03-24 | KIN-360 | Gilfoyle | schema-mismatch | Critical | `users` table creates `display_name` instead of `name`, and `bio` column missing entirely — API queries `name` and `bio`, will return null in production |
| 2026-03-24 | KIN-360 | Gilfoyle | migration | Critical | `handle_new_user()` trigger on `auth.users` not included — new signups create no `public.users` row, breaking all API calls |
| 2026-03-24 | KIN-360 | Gilfoyle | rls-bypass | Important | `users` RLS missing admin SELECT policy — spec requires admin override, migration only has own-row access |
| 2026-03-24 | KIN-360 | Gilfoyle | spec-gap | Important | Vector search RPCs (`match_chunks`, `match_framework_triggers`) not in migration — RAG falls back to slow client-side path |
| 2026-03-24 | KIN-339 | Gilfoyle | spec-gap | Important | MCP spec §9.1 uses field name `label` but implementation + schema use `name` — spec-code mismatch |
| 2026-03-24 | KIN-339 | Gilfoyle | spec-gap | Important | MCP spec §9.2 requires `token_hint: "mcp_••••••••"` in list response but implementation omits it |
| 2026-03-24 | KIN-339 | Gilfoyle | other | Important | `last_used_at` update in mcp.py:137 sends literal string `"now()"` instead of ISO timestamp — stores garbage |
| 2026-03-25 | KIN-365 | Gilfoyle | other | Important | useAgents initializes `loading` as `false` — brief empty-state flash between profile fetch completing and agent fetch starting (isLoading goes false for one React tick) |
| 2026-03-25 | KIN-365 | Gilfoyle | error-swallow | Important | AgentsPage profile fetch failure silent — catch logs but sets no error state; currentUserId stays null, page shows empty states with no user feedback and no retry path |
| 2026-03-25 | KIN-365 | Gilfoyle | test-missing | Important | No test for AgentCard greyed-out state (opacity-60 + "No instructions" badge) for agents with empty instructions — spec §5 requirement unverified by test suite |
| 2026-03-25 | KIN-370 | Gilfoyle | test-missing | Critical | No tests for GET/POST knowledge-base endpoints — 0 of 6 paths covered (200 found, 404 no KB, 404 unowned, 201 created, 200 idempotent, insert failure 500) |
| 2026-03-25 | KIN-370 | Gilfoyle | api-contract | Important | Idempotent POST /{project_id}/knowledge-base returns 201 instead of 200 when KB already exists — FastAPI applies route-level status_code to all returns |
| 2026-03-25 | KIN-372 | Gilfoyle | test-missing | Critical | Zero tests for pin/exclude override feature; mount-time loadOverrides call introduced without updating existing test mock routing — all prior tests now service instance GET with frameworks-shaped response |
| 2026-03-25 | KIN-372 | Gilfoyle | test-missing | Important | Existing tests mock apiFetch with single implementation — both /frameworks GET and /instance GET receive same response after KIN-372 mount change; mock routing must be split by URL |
| 2026-03-25 | KIN-372 | Gilfoyle | api-contract | Critical | R2: Override arrays store f.id (row UUID) instead of f.framework_id (stable semantic ID) — violates db-schema-spec.md §agent_instances comment and ADR-003 §5; overrides silently broken on framework re-import |
| 2026-03-26 | KIN-376 | Gilfoyle | error-swallow | Important | modelsError not reset at top of loadAll — retry path would show stale state if retry button added |
| 2026-03-26 | KIN-376 | Gilfoyle | error-swallow | Important | Outer catch swallows network-level models fetch error — wrong empty state shown instead of error message |
| 2026-03-26 | KIN-378 | Gilfoyle | schema-mismatch | Critical | Both delete endpoints issue hard DELETE; db-schema-spec.md §12 + MEMORY.md lock documents to soft-delete (deleted_at); immediate CASCADE forces HNSW reindex on pgvector index |
| 2026-03-26 | KIN-378 | Gilfoyle | acl-leak | Critical | Single delete returns 403 for cross-tenant access; established anti-enumeration convention requires 404 (MEMORY.md 2026-03-24) |
| 2026-03-26 | KIN-378 | Gilfoyle | other | Important | ACTIVE_INGESTION_STATUSES constant duplicated in documents.py and kb_management.py — single missed update will desync status guards |
| 2026-03-26 | KIN-378 | Gilfoyle | test-missing | Important | No test for storage cleanup failure on delete-all (equivalent test exists for single delete) |
| 2026-03-26 | KIN-373 | Gilfoyle | other | Important | JSONL extension fallback missing in KnowledgeBaseTab client-side validation — browsers that send `application/octet-stream` for `.jsonl` files will be rejected by ACCEPTED_TYPES check even though backend handles them via `_EXT_TO_MIME`; affects Windows browsers primarily |
| 2026-03-26 | KIN-377 | Gilfoyle | test-missing | Important | FrameworkLibraryTab KIN-319 tests use flat `mockFetchFrameworks` mock — does not route `/instance` GET added in KIN-372 mount change; latent unrouted concurrent fetch across all 20+ KIN-319 tests; "successful create" test confirmed failing |
| 2026-03-26 | KIN-385 | Gilfoyle | other | Critical | Sequence race condition on message insert — count then insert is not atomic; concurrent requests produce duplicate sequence values with no UNIQUE constraint to catch them |
| 2026-03-26 | KIN-385 | Gilfoyle | rls-bypass | Critical | Agent switch UPDATE missing user_id filter at application layer — only .eq("id", ...) used; defense-in-depth requires explicit user_id scope on all write operations |
| 2026-03-26 | KIN-385 | Gilfoyle | other | Important | Misleading 400 error message when model UUID is valid but disabled — "No model selected and no default model configured" shown instead of "Model not found or not enabled" |
| 2026-03-26 | KIN-385 | Gilfoyle | schema-mismatch | Important | context_assembler.py docstring cites §19 for messages and §6 for conversation_summaries — correct sections are §6 (messages) and §7 (conversation_summaries) |
| 2026-03-26 | KIN-387 | Gilfoyle | spec-gap | Critical | `done` SSE event missing `model` field — spec §1.5 requires `{"message_id": ..., "model": "...", "citations": [...]}` but implementation omits `model`; `_model_name` is in closure scope |
| 2026-03-27 | KIN-405 | Gilfoyle | other | Important | `delete_all_documents` pre-flight fetch filters `.is_("deleted_at", "null")` but hard-delete does not — scope mismatch causes wrong deleted_count and skipped ingestion guards for any rows with non-null deleted_at |
| 2026-03-27 | KIN-405 | Gilfoyle | other | Important | `delete_folder` (no reassign_to) hard-deletes documents with no ingestion guard — every other deletion path checks ACTIVE_INGESTION_STATUSES and returns 409; folder delete is the only exception |
| 2026-03-27 | KIN-405 | Gilfoyle | other | Important | Stale `.is_("deleted_at", "null")` fetch filter in `delete_document` — misleading artifact of prior soft-delete model; should be removed or commented |
| 2026-03-27 | KIN-405 | Gilfoyle | test-missing | Important | `test_delete_folder_without_reassign_deletes_documents` does not assert delete mock was called — test would pass even if code took reassignment path |
| 2026-03-28 | KIN-408 | Gilfoyle | test-missing | Important | No test for the orphaned row cleanup path in upload route — `except Exception` branch (post-insert, pre-dispatch) deletes the DB row but no test verifies the delete is called or that the route still returns a non-200 |
