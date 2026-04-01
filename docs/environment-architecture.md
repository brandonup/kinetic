# Kinetic Environment Architecture

## Infrastructure

### Production

- **Frontend:** Vercel (`kinetic-ashy-beta.vercel.app`)
- **API:** Railway (`kinetic-production-b568.up.railway.app`)
- **Database:** Supabase (prod project)
- **Users:** Tester (live)

### Development

- **Frontend:** `localhost:3000` (pnpm dev, hot reload)
- **API:** `localhost:8000` (Docker container, `kinetic-api-dev` image)
- **Database:** Supabase (dev project — separate instance, same schema)
- **Users:** Brandon + Dinesh

## What's Shared vs. Isolated

- **Shared:** Same repo, same branch, same migrations (`dev_bootstrap.sql`)
- **Isolated:** Separate Supabase projects (separate data, auth, users, agents, keys). Separate `API_KEY_ENCRYPTION_KEY` — prod keys can't decrypt in dev. Prod hosted on Railway + Vercel; dev runs locally.

## Data Flow

1. Developer makes code change
2. `docker build` + `docker run` (API against dev Supabase)
3. `pnpm dev` (frontend against localhost API)
4. Test locally against dev DB
5. `git push` → Railway auto-deploys API, Vercel auto-deploys frontend
6. Production updated (prod Supabase, real users)

## Migration Flow

1. New migration written
2. **Dev:** Paste into dev Supabase SQL Editor → test
3. **Prod:** Paste into prod Supabase SQL Editor → deploy (Brandon only, after dev verification)

## Dev MCP Server

The `kinetic-mcp` Edge Function is deployed to **both** Supabase projects. This gives Brandon a parallel dev MCP connection in Cowork for testing agent behavior before deploying to prod.

### Convention

- Dev agents use `{name}-dev` slug (e.g., `nate-dev` → `/nate-dev` in Cowork)
- Prod agents use the bare slug (e.g., `nate` → `/nate` in Cowork)
- Each environment has its own Cowork connector:

| | Prod | Dev |
|---|---|---|
| Connector name | `Kinetic` | `Kinetic-dev` |
| MCP URL | Prod Edge Function URL | Dev Edge Function URL |
| Agent slug | `nate` | `nate-dev` |
| Trigger | `/nate` | `/nate-dev` |
| Database | Prod Supabase | Dev Supabase |

### Adding a New Dev Agent

1. INSERT into `agent_definitions` in the dev DB with slug `{name}-dev`
2. Set `visibility = 'public'` so MCP prompts list it
3. The agent auto-appears as a prompt in the Kinetic-dev connector — no code change needed

### Setting Up the Cowork Dev Connector

1. Sign into the dev web app, generate an MCP token on the Profile page
2. In Cowork, add a connector:
   - **Name:** `Kinetic-dev`
   - **URL:** `https://<DEV_PROJECT_REF>.supabase.co/functions/v1/kinetic-mcp?key=mcp_<DEV_TOKEN>`

### Deploying the Edge Function

Always use `--project-ref` explicitly — never rely on `supabase link` state.

```bash
# Dev
supabase functions deploy kinetic-mcp --no-verify-jwt --project-ref <DEV_PROJECT_REF>

# Prod
supabase functions deploy kinetic-mcp --no-verify-jwt --project-ref <PROD_PROJECT_REF>
```

Secrets are set per-project:
```bash
supabase secrets set API_KEY_ENCRYPTION_KEY=<KEY> --project-ref <PROJECT_REF>
```

**Warning:** `API_KEY_ENCRYPTION_KEY` must be different per environment. Prod keys cannot decrypt dev data and vice versa.

## Key Config Files

- `packages/api/.env.dev` — Dev API credentials (gitignored)
- `packages/api/.env.dev.template` — Placeholder template (committed)
- `packages/web/.env.local` — Dev frontend credentials (gitignored)
- `packages/web/.env.local.template` — Placeholder template (committed)
- Railway env vars — Prod API credentials (Railway dashboard)
- Vercel env vars — Prod frontend credentials (Vercel dashboard)
