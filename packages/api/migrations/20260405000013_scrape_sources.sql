-- KIN-459: Create scrape_sources + scrape_source_posts tables
-- Design doc: docs/plans/2026-04-05-scheduled-kb-scraping-design.md

-- =========================================================================
-- scrape_sources — one row per configured scraping source
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.scrape_sources (
  id                     uuid            NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  knowledge_base_id      uuid            NOT NULL REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
  user_id                uuid            NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  source_type            text            NOT NULL,
  source_url             text            NOT NULL,
  frequency              text            NOT NULL,
  credential_ciphertext  bytea,
  credential_nonce       bytea,
  is_active              boolean         NOT NULL DEFAULT true,
  last_scraped_at        timestamptz,
  next_run_at            timestamptz     NOT NULL,
  last_error             text,
  consecutive_failures   int             NOT NULL DEFAULT 0,
  created_at             timestamptz     NOT NULL DEFAULT now(),
  updated_at             timestamptz     NOT NULL DEFAULT now(),

  CONSTRAINT chk_scrape_sources_source_type
    CHECK (source_type IN ('substack', 'rss')),

  CONSTRAINT chk_scrape_sources_frequency
    CHECK (frequency IN ('daily', 'weekly', 'monthly')),

  CONSTRAINT chk_scrape_sources_credential_pair
    CHECK (
      (credential_ciphertext IS NULL AND credential_nonce IS NULL)
      OR
      (credential_ciphertext IS NOT NULL AND credential_nonce IS NOT NULL)
    )
);

-- Partial index: poller finds active sources due for scraping
CREATE INDEX IF NOT EXISTS idx_scrape_sources_poll
  ON public.scrape_sources (is_active, next_run_at)
  WHERE is_active = true;

-- List sources for a knowledge base
CREATE INDEX IF NOT EXISTS idx_scrape_sources_kb
  ON public.scrape_sources (knowledge_base_id);

-- updated_at trigger
DO $$ BEGIN
  CREATE TRIGGER trg_scrape_sources_updated_at
    BEFORE UPDATE ON public.scrape_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- RLS
ALTER TABLE public.scrape_sources ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN CREATE POLICY "scrape_sources_select_own"
  ON public.scrape_sources FOR SELECT
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_sources_insert_own"
  ON public.scrape_sources FOR INSERT
  WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_sources_update_own"
  ON public.scrape_sources FOR UPDATE
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_sources_delete_own"
  ON public.scrape_sources FOR DELETE
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;


-- =========================================================================
-- scrape_source_posts — deduplication tracker for scraped posts
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.scrape_source_posts (
  id                uuid            NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  scrape_source_id  uuid            NOT NULL REFERENCES public.scrape_sources(id) ON DELETE CASCADE,
  user_id           uuid            NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  external_id       text            NOT NULL,
  document_id       uuid            REFERENCES public.knowledge_base_documents(id) ON DELETE SET NULL,
  url               text,
  title             text,
  scraped_at        timestamptz     NOT NULL DEFAULT now(),

  CONSTRAINT uq_scrape_source_posts_source_external
    UNIQUE (scrape_source_id, external_id)
);

-- RLS
ALTER TABLE public.scrape_source_posts ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN CREATE POLICY "scrape_source_posts_select_own"
  ON public.scrape_source_posts FOR SELECT
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_source_posts_insert_own"
  ON public.scrape_source_posts FOR INSERT
  WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_source_posts_update_own"
  ON public.scrape_source_posts FOR UPDATE
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN CREATE POLICY "scrape_source_posts_delete_own"
  ON public.scrape_source_posts FOR DELETE
  USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
