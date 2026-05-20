# MCP Server Architecture Audit

**Date:** 2026-04-04
**Author:** Gilfoyle
**Scope:** All MCP server implementations in the Kinetic codebase

---

## 1. Inventory

### Server A: Local Python MCP Server

| Dimension | Value |
|---|---|
| **Location** | `projects/kinetic/packages/mcp/server.py` |
| **Language / Runtime** | Python 3.11+ / FastMCP |
| **Transport** | stdio (default), SSE via `--sse` flag |
| **Tools** | 5: `get_agent_persona`, `get_active_memory`, `select_framework`, `search_knowledge_base`, `assemble_context` |
| **Auth model** | None. Uses Supabase service role key directly from env vars |
| **Agent model** | Single-agent. Hardcoded to Nate via `NATE_AGENT_ID`, `NATE_INSTANCE_ID` env vars |
| **Database** | Configurable via `SUPABASE_URL` env var (can point to dev or prod) |
| **Embedding key** | Platform-owned OpenAI key from `OPENAI_API_KEY` env var |
| **Users** | Dev only (Brandon's local Cowork) |
| **Deployment** | Local process launched by `claude_desktop_config.json`. Plugin metadata in `.claude-plugin/plugin.json` and `.mcp.json` |
| **Config required** | 6 env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `NATE_AGENT_ID`, `NATE_INSTANCE_ID`, `KINETIC_USER_ID` |
| **Status** | Live in Brandon's local Cowork |

### Server B: Remote MCP Server (Supabase Edge Function)

| Dimension | Value |
|---|---|
| **Location** | `projects/kinetic/supabase/functions/kinetic-mcp/` (index.ts + 5 modules) |
| **Language / Runtime** | TypeScript / Deno (Supabase Edge Functions) |
| **Transport** | HTTP (Streamable HTTP / JSON-RPC 2.0 with SSE response negotiation) |
| **Tools** | 7: `list_kinetic_agents`, `get_agent_persona`, `get_active_memory`, `select_framework`, `search_knowledge_base`, `assemble_context`, `debug_prompts_list` |
| **Auth model** | Bearer token (`mcp_<token>`) -> SHA-256 hash lookup in `mcp_tokens` table. Daily per-user rate limiting via RPC (fail-open) |
| **Agent model** | Multi-agent. Resolves by globally unique slug with ownership/visibility enforcement. Auto-creates agent instances on first invocation |
| **Database** | Prod Supabase (auto-injected env vars) |
| **Embedding key** | User's BYOK OpenAI key (encrypted in `user_api_keys`, decrypted via HKDF+AES-256-GCM at request time) |
| **Prompts** | Dynamic per-user prompt registration. Each agent becomes a discoverable MCP prompt/slash command |
| **Users** | Any Kinetic user with an MCP token (multi-tenant) |
| **Deployment** | Supabase Edge Function. Connected via Cowork native Connectors (paste URL) |
| **Config required** | 1 URL pasted in Cowork Connectors. MCP token generated once in Kinetic UI |
| **Status** | Live (production) |

### Server C: Old `kinetic-brain/` Directory (Deprecated)

| Dimension | Value |
|---|---|
| **Location** | `kinetic-brain/mcp-server/server.py` (old Python) + `kinetic-brain/supabase/functions/kinetic-mcp/` (old remote copy) |
| **Status** | README.md says "MOVED" as of 2026-04-03. All files still present on disk |
| **Relationship** | Stale copy of Servers A and B. The new `packages/mcp/server.py` has diverged ahead (gained `assemble_context`) |

---

## 2. Feature Comparison: Local vs Remote

| Capability | Local (Python) | Remote (Edge Function) |
|---|---|---|
| `get_agent_persona` | Yes | Yes |
| `get_active_memory` | Yes | Yes |
| `select_framework` | Yes | Yes |
| `search_knowledge_base` | Yes | Yes |
| `assemble_context` | Yes | Yes |
| `list_kinetic_agents` | **No** | Yes |
| `debug_prompts_list` | **No** | Yes (temporary) |
| Dynamic MCP prompts | **No** | Yes |
| Multi-agent resolution | **No** (hardcoded Nate) | Yes (slug-based + ACL) |
| Token auth + rate limiting | **No** | Yes |
| BYOK key management | **No** (platform key) | Yes |
| Auto instance creation | **No** (manual UUID) | Yes |
| Dev database access | **Yes** (configurable) | **No** (prod only) |

**The remote server is a strict functional superset of the local server.** The only capability the local server has that the remote lacks is the ability to point at a dev Supabase instance.

---

## 3. Active Redundancy Issue: Dual Connection in Cowork

The current Claude Code session shows **two MCP server registrations with overlapping tool sets:**

| UUID | Tools | Likely server |
|---|---|---|
| `975241c2-...` | 7 tools (incl. `debug_prompts_list`, `list_kinetic_agents`) | Remote Edge Function |
| `fd85330d-...` | 6 tools (incl. `list_kinetic_agents`, no `debug_prompts_list`) | Second remote connection OR local (upgraded) |

Both registrations expose `list_kinetic_agents`, which the Python local server does **not** implement. This means either:

1. **Two remote connections** to the same Edge Function (e.g., dev + prod URLs, or duplicate connector entries), or
2. The local server was updated outside version control.

Regardless of cause, **duplicate tool registrations create ambiguity** for Claude about which server to call, and double the token cost of tool descriptions in every request.

**Action needed:** Audit Cowork Connectors settings and `claude_desktop_config.json` to identify and remove the duplicate.

---

## 4. Configuration Audit

### Local Server Setup Cost

| Step | Effort |
|---|---|
| Install Python venv + deps | ~2 min |
| Look up `SUPABASE_URL` | Dashboard > Project Settings > API |
| Look up `SUPABASE_SERVICE_ROLE_KEY` | Dashboard > Project Settings > API (secret) |
| Look up `OPENAI_API_KEY` | OpenAI dashboard |
| Look up `NATE_AGENT_ID` | Table Editor > `agent_definitions` > find row > copy UUID |
| Look up `NATE_INSTANCE_ID` | Table Editor > `agent_instances` > find matching row > copy UUID |
| Look up `KINETIC_USER_ID` | Table Editor > `profiles` > find row > copy UUID |
| Edit `claude_desktop_config.json` | Manual JSON editing |
| Restart Cowork | Quit + relaunch |
| Create RPC functions (if missing) | Run 2 SQL blocks in Supabase SQL Editor |
| Create `/nate` skill in Cowork | Manual UI entry |

**Total: 11 steps, ~15-20 minutes for someone who knows the system.** Any UUID change (new agent, new user, new instance) requires re-editing the config and restarting Cowork. Service role key sits in a plaintext JSON file.

### Remote Server Setup Cost

| Step | Effort |
|---|---|
| Paste Edge Function URL in Cowork Connectors | ~30 seconds |
| Enter MCP token when prompted | ~30 seconds |

**Total: 2 steps, ~1 minute.** Agent changes, user changes, instance creation handled server-side. No secrets in local files.

### Verdict

The local server's 6-env-var configuration burden is not justified by its dev testing value. The remote server delivers a 10x better setup experience with strictly more functionality.

---

## 5. Recommendation

### Sunset the local server. Keep only the remote Edge Function.

**Rationale:**
1. Remote is a strict functional superset
2. 10:1 configuration reduction
3. Eliminates 647 lines of Python that duplicate TypeScript logic
4. Removes service role key from local plaintext
5. Multi-agent and BYOK only exist remotely
6. Dynamic prompts only work remotely
7. Two codebases means feature drift (already happening: local lacks `list_kinetic_agents` and prompts)

### What to do about dev Supabase testing

The only unique value of the local server is pointing at a dev database. Two options:

**Option 1 (Simpler): Dev Edge Function instance.** Deploy the same `kinetic-mcp` function to the dev Supabase project. Create a dev MCP token. Connect to it in Cowork as a second connector. This gives identical dev testing with zero code duplication.

**Option 2 (Lighter): Don't MCP-test against dev at all.** Use the API test suite (565 tests) and the web app for dev verification. MCP testing against prod is sufficient for the MCP-specific transport/auth layer.

### Tradeoffs

| Factor | Sunset local | Keep local |
|---|---|---|
| Maintenance cost | 1 codebase | 2 codebases (Python + TypeScript) |
| Feature parity | Guaranteed | Diverging (already behind) |
| Dev testing | Via dev Edge Function or API tests | Direct local access |
| Config burden | 1 URL | 6 env vars |
| Security | No service role key in plaintext | Service role key in `claude_desktop_config.json` |
| Cold start | 2-3 sec (Edge Function) | Instant (local) |
| Offline use | No | Yes (if Supabase is reachable) |

The only real counterargument is cold start latency, which is 2-3 seconds on first request per session. That's acceptable for an advisory tool.

---

## 6. Migration Completeness Check

### Correctly migrated

- `kinetic-brain/mcp-server/server.py` -> `packages/mcp/server.py` (and upgraded with `assemble_context`)
- `kinetic-brain/supabase/functions/kinetic-mcp/*` -> `supabase/functions/kinetic-mcp/*`
- `kinetic-brain/docs/deployment-guide.md` -> `packages/mcp/docs/deployment-guide.md`
- `.mcp.json` and `.claude-plugin/` metadata copied

### Issues Found

| # | Issue | Severity | Location |
|---|---|---|---|
| 1 | **Old `kinetic-brain/` directory not deleted.** README says "MOVED" but all files, venv, and subdirectories remain on disk. Git status shows it tracked. | Important | `kinetic-brain/` |
| 2 | **Old deployment guide references old paths.** `kinetic-brain/docs/deployment-guide.md` still references `~/son_of_anton/kinetic-brain/mcp-server/server.py` and old config paths. | Low (deprecated file) | `kinetic-brain/docs/deployment-guide.md` |
| 3 | **Port-from comments reference old path.** `tools.ts:9` says `Port from: kinetic-brain/mcp-server/server.py` and `embedding.ts:7` says the same. Should reference `packages/mcp/server.py`. | Low | `supabase/functions/kinetic-mcp/tools.ts`, `embedding.ts` |
| 4 | **`kinetic-brain-plugin-spec.md` references `mcp-server/server.py`** without a full path, creating ambiguity about which copy. | Low | `docs/specs/kinetic-brain-plugin-spec.md:85,204` |
| 5 | **`debug_prompts_list` tool still in production.** Comment says "Remove after KIN-454." KIN-454 is In Progress. | Low (temporary) | `supabase/functions/kinetic-mcp/tools.ts:697` |
| 6 | **Dual MCP connection in Cowork.** Two server registrations with overlapping tools — likely a duplicate connector or local+remote overlap. | Critical | Cowork Connectors config |

### Recommended Cleanup (in order)

1. **Remove duplicate Cowork connector** (Issue 6) — this is actively causing confusion.
2. **Delete `kinetic-brain/` directory** (Issue 1) — the migration is complete, old files are stale.
3. **Update port-from comments** (Issue 3) — or remove them entirely since the canonical source is now `packages/mcp/server.py`.
4. **Remove `debug_prompts_list`** (Issue 5) — when KIN-454 is verified.

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sunsetting local breaks Brandon's current `/nate` flow | Medium | High | Verify remote connector is working before disconnecting local |
| Dev Supabase testing gap | Low | Medium | Option 1 (dev Edge Function) or Option 2 (API tests sufficient) |
| Edge Function cold start annoys users | Low | Low | 2-3 sec is acceptable; warms on first request per session |
| Removing `kinetic-brain/` loses git history | None | None | Git preserves history regardless of file deletion |
