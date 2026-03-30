# Code Review: KIN-434 — Deploy FastAPI backend to Railway

**Reviewer:** Gilfoyle
**Date:** 2026-03-29
**Verdict:** Architecture approved. 0 Critical, 0 Important, 2 Notes.

---

## Files Reviewed

| File | Purpose |
|---|---|
| `packages/api/Dockerfile` | Multi-stage build with system deps for unstructured |
| `packages/api/railway.toml` | Dockerfile builder config, health check, restart policy |
| `packages/api/Procfile` | Uvicorn start command (fallback) |
| `packages/api/.dockerignore` | Build context exclusions |
| `docs/deploy-railway.md` | Step-by-step deploy guide |
| `app/main.py` | Health check endpoint (pre-existing) |
| `app/core/config.py` | Production validation (pre-existing) |

## Done-when Check

| Criteria | Status |
|---|---|
| Dockerfile with Python 3.11 + system deps | PASS — multi-stage build, correct deps |
| railway.toml with Dockerfile builder + health check | PASS — builder=DOCKERFILE, /health, 300s timeout |
| Health check endpoint at /health | PASS — returns `{"status": "ok"}` |
| Production validation rejects localhost | PASS — config.py lines 120-129 |
| Deploy process documented | PASS — clear 6-step guide with troubleshooting |

## Security Check

| Check | Status |
|---|---|
| No platform OpenAI key references in codebase | PASS — grep found zero matches for OPENAI_API_KEY or PLATFORM_OPENAI across all .py files |
| `.env` excluded from Docker image | PASS — .dockerignore line 3 |
| `LOCAL_DEV_AUTH_BYPASS` defaults False | PASS — deploy doc explicitly says not to set it |
| Tests excluded from image | PASS — .dockerignore line 6 |

## Notes (non-blocking)

**1. Procfile is redundant.** The Dockerfile CMD handles the start command, and `railway.toml` specifies Dockerfile builder. The Procfile would only matter if Railway fell back to Nixpacks, which it won't with the explicit `railway.toml` config. Harmless but unnecessary.

**2. Image size may be large.** `libreoffice-core` + `tesseract-ocr` + `poppler-utils` add significant weight (~300-500MB). This is correct for `unstructured[all-docs]` support, but expect 3-5 minute builds and higher memory usage on Railway. If deploy times become a problem post-launch, consider splitting document ingestion into a separate worker service.

## LGTM

Clean deployment config. Dockerfile is correctly structured (multi-stage, system deps in both stages for build + runtime). Railway config is minimal and correct. Deploy doc is actionable with good troubleshooting section. No security concerns.
