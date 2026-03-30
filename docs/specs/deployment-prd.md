# Deployment — Product Requirements Document

**Status:** Draft
**Author:** Jared
**Date:** 2026-03-29
**Project:** Kinetic

---

## Problem Statement

Kinetic's frontend and backend run only on localhost. Users cannot create accounts, build agents, add API keys, or use the product. Without deployment, the entire MVP is inaccessible. This is the hard blocker between "code complete" and "users can use it."

## Proposed Solution

Deploy the three Kinetic services to production: Next.js frontend on Vercel, FastAPI backend on Railway, and the MCP Edge Function on Supabase. Manual deploys — no CI/CD pipeline for now.

## User Stories

- As a new user, I want to visit the Kinetic URL and sign up with Google so that I can start using the product
- As a user, I want my conversations and agent interactions to work in production so that the app is functional beyond localhost
- As Brandon, I want to deploy new versions manually so that I control what goes live

## Success Metrics

| Metric | Baseline | Target | Timeframe |
|---|---|---|---|
| App reachable at Vercel URL | No | Yes | End of sprint |
| Google OAuth sign-up works in production | No | Yes | End of sprint |
| User can create agent + start conversation (end-to-end) | No | Yes | End of sprint |

## Scope

**In scope:**
- Vercel deployment of Next.js frontend (default `.vercel.app` URL)
- Railway deployment of FastAPI backend
- Supabase Edge Function deployment (`kinetic-mcp`)
- Environment variables configured in all three services
- CORS configured for production URLs
- Supabase Auth redirect URLs updated for production
- End-to-end smoke test

**Out of scope:**
- Custom domain / DNS
- CI/CD (GitHub Actions)
- Monitoring / alerting / logging infrastructure
- CDN or caching configuration
- Staging environment
- Load testing

## Surface Inventory

- **Pages / Views:** None new — all existing pages must work at production URLs
- **API Endpoints:** None new — existing endpoints must be reachable from the Vercel frontend
- **Database Tables:** None new or modified
- **Background Jobs / Cron:** None
- **Integrations:** Vercel (hosting), Railway (hosting), Supabase Auth (redirect URL update)

## Data Requirements

None — this feature requires no new or modified tables.

---

## Environment Variables

### Frontend (Vercel)

| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Already used in dev |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key | Already used in dev |
| `NEXT_PUBLIC_API_BASE_URL` | Railway backend URL | Points frontend API calls to Railway |
| `NEXT_PUBLIC_ALLOW_REMOTE_API` | `"true"` | Enables non-localhost API calls |

### Backend (Railway)

| Variable | Value | Notes |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key | **Secret** |
| `SUPABASE_ANON_KEY` | Anon key | |
| `SUPABASE_JWT_SECRET` | JWT secret | **Secret** |
| `API_KEY_ENCRYPTION_KEY` | Base64-encoded 32-byte key | **Secret** |
| `ENVIRONMENT` | `"production"` | Triggers production validation |
| `CORS_ORIGINS` | Vercel app URL | Must match actual frontend URL |
| `ADMIN_PORTAL_URL` | Vercel app URL | Used for admin links |

### Edge Function (Supabase)

| Variable | Value | Notes |
|---|---|---|
| `API_KEY_ENCRYPTION_KEY` | Same as backend | **Secret** — set via `supabase secrets set` |
| `SUPABASE_URL` | Auto-injected | No manual config |
| `SUPABASE_SERVICE_ROLE_KEY` | Auto-injected | No manual config |

## Dependencies

- **Technical:** Supabase project must be accessible (it already is — used in development)
- **Product:** Core features code-complete (auth, agents, conversations, KB, active memory, generation)
- **External:** Railway account, Vercel account

## Deployment Order

```
T1: Railway (backend)     ─┐
                            ├──→  T3: Vercel (frontend, needs backend URL)
T2: Supabase Edge Function ─┘     │
                                   ├──→  T4: Smoke Test
                                   │
                            Supabase Auth redirect URL update ──┘
```

1. **T1 — Railway backend** must deploy first — the frontend needs its URL for `NEXT_PUBLIC_API_BASE_URL`
2. **T2 — Edge Function** is independent (existing Supabase project)
3. **T3 — Vercel frontend** needs the Railway URL. Also requires Supabase Auth redirect URLs updated to include the Vercel domain
4. **T4 — Smoke test** verifies end-to-end after all three are live

## Decisions Needed

None — platforms decided (Vercel, Railway, manual deploys, no custom domain).

## Open Questions

- [ ] Does Railway's free tier or starter plan support the `unstructured` Python package (large binary dependencies)?
- [ ] Does the FastAPI app need a `Procfile` or `railway.toml` for Railway, or does Railway auto-detect?
