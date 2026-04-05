-- Migration: Admin bootstrap — first-user auto-promotion + promote endpoint support
-- Ticket: KIN-417
-- Date: 2026-04-05
--
-- Problem: handle_new_user() always sets role='user'. No mechanism to assign admin roles
-- without manual Supabase intervention.
--
-- Fix:
--   1. Modify handle_new_user() to auto-promote the first user (empty users table).
--      Handles fresh deployments — the first user to sign up becomes admin.
--   2. Promote the earliest-created existing user to admin.
--      Idempotent: no-op if that user is already admin. Fixes existing deployments.
--
-- Ongoing management: use PATCH /api/v1/admin/users/{user_id}/promote (KIN-417).

-- ---------------------------------------------------------------------------
-- 1. Update handle_new_user() trigger — auto-promote first user
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  v_role user_role;
BEGIN
  -- Auto-promote to admin if no users exist yet (first signup = first admin)
  IF NOT EXISTS (SELECT 1 FROM public.users) THEN
    v_role := 'admin';
  ELSE
    v_role := 'user';
  END IF;

  INSERT INTO public.users (id, name, email, role)
  VALUES (
    NEW.id,
    COALESCE(
      NULLIF(TRIM(NEW.raw_user_meta_data->>'name'), ''),
      split_part(NEW.email, '@', 1)
    ),
    NEW.email,
    v_role
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ---------------------------------------------------------------------------
-- 2. Promote the earliest-created user to admin (fixes existing deployments)
-- ---------------------------------------------------------------------------
-- Idempotent: if the first user is already admin, this is a no-op.

UPDATE public.users
SET role = 'admin'
WHERE id = (SELECT id FROM public.users ORDER BY created_at ASC LIMIT 1);
