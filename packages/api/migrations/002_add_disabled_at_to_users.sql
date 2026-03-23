-- KIN-264: Add disabled_at to public.users for admin enable/disable functionality
-- Run in Supabase SQL editor or via CLI

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS disabled_at timestamptz DEFAULT NULL;
