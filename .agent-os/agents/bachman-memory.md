# Bachman — Cross-Project Memory

Bug patterns, root causes, and triage lessons learned. Updated at session end.

---

<!-- Entries format: - [YYYY-MM-DD] [project] Lesson learned -->

## Triage Lessons

- [2026-03-19] [kinetic] **Test mocks that don't mirror the real library API give false confidence.** When a route 400s in production but tests pass, check the mock's export shape against the package's actual exports — especially after a major version bump. (pdf-parse v1 `default fn` → v2 `PDFParse class`)
- [2026-03-19] [kinetic] **`createServerClient` (SSR) vs `createAdminClient` (service role) is not interchangeable.** SSR client attaches user JWT → runs as `authenticated` → FORCE RLS applies → needs `app.workspace_id`. Admin client = no JWT, pure service_role, bypasses FORCE RLS. In Kinetic: API routes always use `createAdminClient` + explicit workspace_id filters.
- [2026-03-19] [kinetic] **When a DB function is missing from migrations, it's invisible to debugging.** `set_workspace_context` existed only in the dashboard; no error pointed to it being the cause. Always check if an RPC has a corresponding migration file before debugging its behavior.
