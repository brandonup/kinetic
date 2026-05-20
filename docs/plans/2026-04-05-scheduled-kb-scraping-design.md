# Scheduled KB Scraping — Design

**Status:** Draft
**Date:** 2026-04-05
**Author:** Jared

---

## Problem

The Substack scraper (`nbj_extractor/substack_scraper.py`) runs manually and re-scrapes everything on each run. There is no way for users to set up automatic, incremental content ingestion into an agent's knowledge base. Users who want their agents to stay current with external content sources must manually re-run scripts and upload results.

## Goal

Users can provide a URL (Substack newsletter or RSS/Atom feed) and a frequency (daily, weekly, monthly), and new content from that source is automatically scraped and ingested into the linked agent's knowledge base.

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| Source types at launch | Substack + RSS/Atom | Covers newsletters + most blogs. Pluggable for future types. |
| Auth model | User provides cookie/token per source, encrypted at rest | Required for paid Substack content |
| BYOK key | Required at source creation | Fail early — don't create sources that can't complete ingestion |
| Scheduler | APScheduler in-process (poller pattern) | Simple, no new infra. Single job polls every 5 min. |
| Source scope | One source per agent KB | Simplest model. Duplicate sources if multiple agents need same URL. |
| UI | Backend-only for now | API endpoints ready; UI added later |

---

## Data Model

### `scrape_sources`

One row per URL configured for an agent's KB.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `knowledge_base_id` | uuid | FK NOT NULL, ON DELETE CASCADE | Links to one agent's KB |
| `user_id` | uuid | FK NOT NULL | Denormalized for RLS (matches KB pattern) |
| `source_type` | text | NOT NULL, CHECK IN ('substack', 'rss') | Extensible via CHECK constraint update |
| `source_url` | text | NOT NULL | Substack base URL or RSS feed URL |
| `frequency` | text | NOT NULL, CHECK IN ('daily', 'weekly', 'monthly') | |
| `credential_ciphertext` | bytea | | AES-256-GCM encrypted cookie/token. NULL for public feeds. Uses existing `app/services/encryption.py` with per-user key derivation. |
| `credential_nonce` | bytea | | Encryption nonce. NULL when `credential_ciphertext` is NULL. |
| `is_active` | boolean | NOT NULL DEFAULT true | Pause/resume without deleting |
| `last_scraped_at` | timestamptz | | NULL until first successful run |
| `next_run_at` | timestamptz | NOT NULL | Set on creation based on frequency. Poller checks this. |
| `last_error` | text | | NULL on success. Set on failure. |
| `consecutive_failures` | int | NOT NULL DEFAULT 0 | Tracks sequential failures. Auto-deactivates after 5. Reset on success. |
| `created_at` | timestamptz | NOT NULL DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL DEFAULT now() | |

**Indexes:**
- `idx_scrape_sources_poll`: `(is_active, next_run_at)` WHERE `is_active = true` — poller query
- `idx_scrape_sources_kb`: `(knowledge_base_id)` — list sources for a KB

**Constraints:**
- `chk_scrape_sources_credential_pair`: `(credential_ciphertext IS NULL AND credential_nonce IS NULL) OR (credential_ciphertext IS NOT NULL AND credential_nonce IS NOT NULL)` — prevents corrupted half-set credential rows
- `updated_at` trigger per schema conventions

**RLS:** Owner-only access via `user_id = auth.uid()`.

### `scrape_source_posts`

Deduplication tracker. Prevents re-ingesting the same post on subsequent scrape runs.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `scrape_source_id` | uuid | FK NOT NULL, ON DELETE CASCADE | |
| `user_id` | uuid | FK NOT NULL | Denormalized for RLS (Supabase can't follow FK joins) |
| `external_id` | text | NOT NULL | Substack post ID or RSS entry GUID |
| `document_id` | uuid | FK | Links to `knowledge_base_documents` row |
| `url` | text | | Post URL for reference |
| `title` | text | | Post title for display |
| `scraped_at` | timestamptz | NOT NULL DEFAULT now() | |

**Unique constraint:** `(scrape_source_id, external_id)`

**RLS:** Owner-only access via `user_id = auth.uid()`.

---

## Scraper Architecture

### Interface

```
BaseScraper (abstract)
  scrape(source: ScrapeSource) → List[ScrapedPost]

ScrapedPost:
  external_id: str      # Substack post ID or RSS GUID
  title: str
  url: str
  content: str           # Clean plain text
  published_at: datetime
```

### Implementations

**SubstackScraper** — Refactored from `substack_scraper.py`:
- Fetches posts via Substack API (`/api/v1/posts`)
- Uses session cookie from `auth_credentials` for paid content
- Converts HTML → clean text (existing logic)
- Returns `external_id` = Substack post ID

**RSSFeedScraper** — New:
- Parses feed via `feedparser` library
- Extracts entry content (prefers `content` field, falls back to `summary`)
- Strips HTML tags → clean text
- Returns `external_id` = RSS entry `id` or `guid`

### Scraper Registry

```python
SCRAPER_REGISTRY = {
    "substack": SubstackScraper,
    "rss": RSSFeedScraper,
}
```

Adding a new source type = add a class + registry entry.

---

## Ingestion Flow

1. Poller finds a source with `next_run_at <= now()`
2. Look up the scraper class via `SCRAPER_REGISTRY[source.source_type]`
3. Call `scraper.scrape(source)` → list of `ScrapedPost`
4. For each post:
   a. Check `scrape_source_posts` for `(source_id, external_id)` — skip if exists
   b. Create `knowledge_base_documents` row (title = post title, file_type = 'text/plain', status = 'pending')
   c. Store post text in Supabase Storage at `{document_id}/extracted.txt`
   d. Insert `scrape_source_posts` row linking source → post → document
   e. Dispatch ingestion pipeline **from the chunking stage** (text already extracted)
5. Update source: `last_scraped_at = now()`, `next_run_at` = calculated from frequency, `last_error = NULL`
6. On failure: set `last_error`, do NOT advance `next_run_at` (retries next poll)
7. On 0 new posts (no new content): treat as success — update `last_scraped_at`, advance `next_run_at`, reset `consecutive_failures`

**Key reuse:** Steps 4b–4e use the existing ingestion pipeline (`run_ingestion_from_stage`). No changes to chunking, embedding, or indexing.

---

## Scheduling

- **APScheduler** initialized in FastAPI lifespan (start on boot, graceful shutdown)
- One `IntervalTrigger` job: runs every 5 minutes
- Job logic:
  1. Query `scrape_sources WHERE is_active = true AND next_run_at <= now()` with `FOR UPDATE SKIP LOCKED` (safe under multiple replicas)
  2. Process each source sequentially (avoid parallel to stay within BYOK rate limits)
  3. Each source is independent — one failure doesn't block others
  4. On failure: increment `consecutive_failures`, apply exponential backoff to `next_run_at` (5min × 2^failures, capped at 24h). Auto-deactivate (`is_active = false`) after 5 consecutive failures.
  5. On success: reset `consecutive_failures` to 0

**`next_run_at` calculation:**
- `daily` → `last_scraped_at + 24 hours`
- `weekly` → `last_scraped_at + 7 days`
- `monthly` → `last_scraped_at + 30 days`

**Restart resilience:** On API restart, APScheduler restarts and the poller immediately catches any sources that were due during downtime.

---

## API Endpoints

All under `/api/v1/scrape-sources`. Auth required. Backend-only for now.

| Method | Path | ACL | Notes |
|---|---|---|---|
| POST | `/` | Auth user; must own target KB (404 if not) | Validates: BYOK OpenAI key exists (MVP-hardcoded; code comment for multi-provider), source_url format, frequency. Sets `next_run_at`. |
| GET | `/?knowledge_base_id=` | Auth user; RLS filters to own sources | Returns empty list if no sources or KB not owned |
| PATCH | `/{id}` | Auth user; must own source (404 if not) | Update frequency, toggle `is_active`, update credentials |
| DELETE | `/{id}` | Auth user; must own source (404 if not) | CASCADE deletes `scrape_source_posts` |
| POST | `/{id}/run` | Auth user; must own source (404 if not) | Trigger immediate scrape. Acquires row lock (`FOR UPDATE`) to prevent concurrent poller overlap. |

**Background poller ACL:** Operates with service role key (no user auth context). Uses each source's `user_id` to resolve BYOK key at scrape time.

---

## Credential Encryption

- **Algorithm:** AES-256-GCM with per-user HKDF key derivation (reuses existing `app/services/encryption.py`)
- **Storage:** `credential_ciphertext` (bytea) + `credential_nonce` (bytea) columns
- **Flow:** Encrypt on write (`POST`/`PATCH`), decrypt on read (only in scraper, never returned via API)
- **API responses** never include credential fields — omitted from response schema
- **Per-user isolation:** Each user's credentials encrypted with a key derived from their user ID — compromising one user's data doesn't expose others

---

## Dependencies

**New Python packages:**
- `apscheduler` — in-process job scheduling
- `feedparser` — RSS/Atom feed parsing (note: last release 2023, effectively unmaintained — no better alternative exists)

**Existing (reused):**
- `beautifulsoup4`, `httpx` — already in use by substack_scraper.py
- Ingestion pipeline — unchanged

---

## Technical Review (Gilfoyle, 2026-04-05)

**Review 1 verdict:** ISSUES FOUND (2 blockers, 3 warnings, 4 notes)
**Review 2 verdict:** APPROVED WITH NOTES (all blockers/warnings resolved, 2 new notes added)

| Finding | Severity | Resolution |
|---|---|---|
| B1: Fernet → use existing AES-256-GCM encryption module | Blocker | Fixed: switched to `app/services/encryption.py` pattern |
| B2: `scrape_source_posts` missing `user_id` for RLS | Blocker | Fixed: added denormalized `user_id` column |
| W1: Duplicate scrapes under multiple replicas | Warning | Fixed: added `FOR UPDATE SKIP LOCKED` to poller query |
| W2: No backoff on persistent failures | Warning | Fixed: added `consecutive_failures` counter + exponential backoff + auto-deactivate at 5 |
| W3: BYOK validation underspecified | Warning | Fixed: creation endpoint validates OpenAI key existence |
| N1: Poller needs `project_id`/`agent_definition_id` | Note | Resolved at runtime: looked up from `knowledge_base_id` FK → `knowledge_bases` row |
| N3: `feedparser` unmaintained | Note | Acknowledged in dependencies section |
| N4: Missing `updated_at` trigger | Note | Standard `updated_at` trigger applied per schema conventions |
| N5 (R2): Credential column pair needs CHECK constraint | Note | Fixed: added `chk_scrape_sources_credential_pair` CHECK constraint |
| N6 (R2): BYOK validation hardcoded to OpenAI | Note | Fixed: documented in POST endpoint notes + code comment for future multi-provider |

---

## Open Questions

| Question | Owner |
|---|---|
| Should failed scrape runs trigger a user notification (email, in-app)? | Brandon (post-MVP) |
| Rate limiting — max sources per user? | Brandon |
