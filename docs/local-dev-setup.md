# Local Development Setup

How to run Kinetic locally against the dev Supabase project.

## Prerequisites

- **Docker** (Docker Desktop or CLI)
- **pnpm** (for the frontend)
- **Dev Supabase project** — credentials from Brandon

## 1. Apply Migrations to Dev Database

Paste `packages/api/migrations/dev_bootstrap.sql` into the **Supabase SQL Editor** on the dev project and run it once. This creates all tables, enums, indexes, RLS policies, RPCs, and seed data.

If `dev_bootstrap.sql` is ever out of date, run migrations individually in this order:

1. `000_complete_schema.sql`
2. `20260328000005_seed_llm_models.sql`
3. `20260329000007_add_debug_prompt_to_messages.sql`
4. `20260330000009_add_match_chunks_rpc.sql`
5. `20260330000010_add_email_to_users.sql`

These are already included in `dev_bootstrap.sql` — only use the manual order if the bootstrap falls behind.

## 2. Configure Environment Variables

### API (`packages/api/.env.dev`)

Copy the template and fill in dev Supabase credentials:

```bash
cp packages/api/.env.dev.template packages/api/.env.dev
```

Then edit `.env.dev` with your values. Generate a fresh `API_KEY_ENCRYPTION_KEY` for dev:

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Do **not** reuse the production encryption key.

### Frontend (`packages/web/.env.local`)

Copy the template and fill in dev Supabase credentials:

```bash
cp packages/web/.env.local.template packages/web/.env.local
```

## 3. Run the API (Docker)

Build and run:

```bash
docker build -t kinetic-api-dev packages/api
docker run --rm -p 8000:8000 --env-file packages/api/.env.dev kinetic-api-dev
```

The `.env.dev` sets `PORT=8000`, overriding the Dockerfile's Railway default of 8080.

Verify:

- `http://localhost:8000/health` should return `{"status": "ok"}`
- `http://localhost:8000/docs` should load the Swagger UI

### Rebuild After Code Changes

```bash
docker build -t kinetic-api-dev packages/api
docker run --rm -p 8000:8000 --env-file packages/api/.env.dev kinetic-api-dev
```

Docker doesn't hot-reload — rebuild after each change. (A bind-mount workflow with uvicorn `--reload` is a future improvement.)

## 4. Run the Frontend

```bash
cd packages/web
pnpm install
pnpm dev
```

Opens at `http://localhost:3000`. The frontend talks to the local API at `http://localhost:8000` (configured via `NEXT_PUBLIC_API_BASE_URL`).

## 5. Run Tests

### API Tests

```bash
cd packages/api
pip install -r requirements.txt
pytest -v
```

API tests use mocks — they don't require a running database.

### Frontend Tests

```bash
cd packages/web
pnpm test
```

## Environment Summary

| Environment | API | Database | Frontend |
|---|---|---|---|
| Production | Railway (`kinetic-production-b568.up.railway.app`) | Supabase (prod) | Vercel (`kinetic-ashy-beta.vercel.app`) |
| Development | `localhost:8000` (Docker) | Supabase (dev) | `localhost:3000` (pnpm dev) |
