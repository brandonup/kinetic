-- Migration: 001_create_users
-- Ticket: KIN-252
-- Schema ref: docs/db-schema-spec.md §1
--
-- NOTE: default_model_id (→ llm_models) and active_company_id (→ companies) FK
-- constraints are intentionally omitted here because those tables do not exist yet.
-- They will be added as ALTER TABLE statements in the migrations that create
-- llm_models and companies respectively.
--
-- This migration can be applied standalone without error.

-- ---------------------------------------------------------------------------
-- Enum
-- ---------------------------------------------------------------------------

CREATE TYPE user_role AS ENUM ('admin', 'user');

-- ---------------------------------------------------------------------------
-- Table: public.users
-- Extends auth.users. Populated exclusively by the handle_new_user() trigger.
-- default_model_id and active_company_id FKs added by later migrations.
-- ---------------------------------------------------------------------------

CREATE TABLE public.users (
  id                uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name              text        NOT NULL,
  email             text        NOT NULL UNIQUE,
  bio               text        CHECK (char_length(bio) <= 1000),
  role              user_role   NOT NULL DEFAULT 'user',
  default_model_id  uuid,       -- FK to llm_models added in migration 00X_create_llm_models
  active_company_id uuid,       -- FK to companies added in migration 00X_create_companies
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- updated_at trigger (shared function — idempotent)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- handle_new_user: fires on auth.users INSERT → creates public.users row
-- Name is seeded from raw_user_meta_data->>'name', falling back to email prefix.
-- ---------------------------------------------------------------------------

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

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- SELECT: own row OR admin (admin check avoids recursion by using EXISTS subquery)
CREATE POLICY "users_select_own_or_admin"
  ON public.users FOR SELECT
  USING (
    auth.uid() = id
    OR EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin'
    )
  );

-- UPDATE: own row OR admin
CREATE POLICY "users_update_own_or_admin"
  ON public.users FOR UPDATE
  USING (
    auth.uid() = id
    OR EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin'
    )
  );

-- INSERT: trigger only — authenticated users cannot insert directly
CREATE POLICY "users_insert_deny"
  ON public.users FOR INSERT
  WITH CHECK (false);

-- DELETE: denied — use Supabase Auth admin API to delete users
CREATE POLICY "users_delete_deny"
  ON public.users FOR DELETE
  USING (false);
