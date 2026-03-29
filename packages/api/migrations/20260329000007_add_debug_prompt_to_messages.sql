-- KIN-419: Store full assembled prompt on messages table
-- Adds a JSONB column to capture the complete messages array sent to the LLM.
-- Only populated on assistant messages. No index needed (admin inspection only).

ALTER TABLE public.messages
ADD COLUMN IF NOT EXISTS debug_prompt jsonb;

COMMENT ON COLUMN public.messages.debug_prompt IS
  'Full messages array sent to the LLM for this assistant turn. '
  'Stored as JSONB array of {role, content} objects. Only populated on assistant messages.';
