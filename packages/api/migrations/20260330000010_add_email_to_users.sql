-- Migration: 20260330000010_add_email_to_users
-- Ticket: KIN-451
-- Schema ref: docs/db-schema-spec.md §1 (users)
--
-- Adds email column to public.users and updates handle_new_user() trigger
-- to populate it from auth.users.email on signup.
--
-- Run order:
--   1. Add column (nullable first)
--   2. Backfill from current name values (they're currently emails)
--   3. Set NOT NULL after backfill
--   4. Replace handle_new_user() to populate email on new signups

-- Step 1: Add email column
ALTER TABLE public.users ADD COLUMN email text UNIQUE;

-- Step 2: Backfill from existing name values (currently storing emails in name)
UPDATE public.users SET email = name;

-- Step 3: Make NOT NULL after backfill
ALTER TABLE public.users ALTER COLUMN email SET NOT NULL;

-- Step 4: Update handle_new_user() trigger to populate both email and name
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, name, email, role)
  VALUES (
    NEW.id,
    COALESCE(
      NULLIF(TRIM(NEW.raw_user_meta_data->>'name'), ''),
      split_part(NEW.email, '@', 1)
    ),
    NEW.email,
    'user'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
