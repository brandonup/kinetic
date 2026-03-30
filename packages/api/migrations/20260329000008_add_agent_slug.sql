-- Migration: Add slug column to agent_definitions
-- Ticket: KIN-429 — agent slug for MCP resolution by friendly name
-- Date: 2026-03-29
-- Constraint: GLOBALLY unique (not per-owner) per remote-mcp-server-spec.md §9

-- 1. Add column (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'agent_definitions'
      AND column_name = 'slug'
  ) THEN
    ALTER TABLE public.agent_definitions ADD COLUMN slug text NOT NULL DEFAULT '';
  END IF;
END $$;

-- 2. Backfill: slugify name (lowercase, replace non-alphanumeric runs with hyphens)
UPDATE public.agent_definitions
SET slug = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'))
WHERE slug = '';

-- 3. Trim leading/trailing hyphens
UPDATE public.agent_definitions
SET slug = trim(BOTH '-' FROM slug)
WHERE slug LIKE '-%' OR slug LIKE '%-';

-- 4. Truncate to 60 chars (E.22), trim trailing hyphens after truncation
UPDATE public.agent_definitions
SET slug = trim(BOTH '-' FROM left(slug, 60))
WHERE length(slug) > 60;

-- 5. Handle empty slugs (empty or all-special-char names)
UPDATE public.agent_definitions
SET slug = 'agent-' || left(id::text, 8)
WHERE slug = '';

-- 6. Deduplicate GLOBALLY: append -2, -3, etc. for collisions
DO $$
DECLARE
  r RECORD;
  suffix INT;
  candidate TEXT;
BEGIN
  FOR r IN
    SELECT id, slug
    FROM public.agent_definitions a
    WHERE EXISTS (
      SELECT 1 FROM public.agent_definitions b
      WHERE b.slug = a.slug
        AND b.id <> a.id
        AND b.created_at <= a.created_at
    )
    ORDER BY slug, created_at
  LOOP
    suffix := 2;
    candidate := r.slug || '-' || suffix;
    WHILE EXISTS (
      SELECT 1 FROM public.agent_definitions
      WHERE slug = candidate AND id <> r.id
    ) LOOP
      suffix := suffix + 1;
      candidate := r.slug || '-' || suffix;
    END LOOP;
    UPDATE public.agent_definitions SET slug = candidate WHERE id = r.id;
  END LOOP;
END $$;

-- 7. Drop old per-owner constraint if it exists, add global unique constraint
DO $$
BEGIN
  -- Remove per-owner constraint from prior migration version
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_agent_definitions_owner_slug'
  ) THEN
    ALTER TABLE public.agent_definitions DROP CONSTRAINT uq_agent_definitions_owner_slug;
  END IF;

  -- Add global unique constraint (idempotent)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_agent_definitions_slug'
  ) THEN
    ALTER TABLE public.agent_definitions
      ADD CONSTRAINT uq_agent_definitions_slug UNIQUE (slug);
  END IF;
END $$;
