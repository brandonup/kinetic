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

## Key Config Files

- `packages/api/.env.dev` — Dev API credentials (gitignored)
- `packages/api/.env.dev.template` — Placeholder template (committed)
- `packages/web/.env.local` — Dev frontend credentials (gitignored)
- `packages/web/.env.local.template` — Placeholder template (committed)
- Railway env vars — Prod API credentials (Railway dashboard)
- Vercel env vars — Prod frontend credentials (Vercel dashboard)
