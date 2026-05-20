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

## MCP Server

The `kinetic-mcp` Edge Function is deployed to the **prod** Supabase project only. Brandon connects to it via a single Cowork connector (`Kinetic`).

> **Removed 2026-04-04:** The dev MCP connector (`Kinetic-dev`) was removed. Running both prod and dev connectors caused tool-name conflicts (identical tool names on both servers). A single prod connector is sufficient — the dev Supabase instance is still available for API/frontend testing but does not need its own MCP endpoint.

### Deploying the Edge Function

Always use `--project-ref` explicitly — never rely on `supabase link` state.

```bash
supabase functions deploy kinetic-mcp --no-verify-jwt --project-ref <PROD_PROJECT_REF>
```

Secrets:
```bash
supabase secrets set API_KEY_ENCRYPTION_KEY=<KEY> --project-ref <PROD_PROJECT_REF>
```

## Key Config Files

- `packages/api/.env.dev` — Dev API credentials (gitignored)
- `packages/api/.env.dev.template` — Placeholder template (committed)
- `packages/web/.env.local` — Dev frontend credentials (gitignored)
- `packages/web/.env.local.template` — Placeholder template (committed)
- Railway env vars — Prod API credentials (Railway dashboard)
- Vercel env vars — Prod frontend credentials (Vercel dashboard)
