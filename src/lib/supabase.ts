// src/lib/supabase.ts
import { createClient, SupabaseClient } from '@supabase/supabase-js'

// Lazy singleton — env check deferred to first call so Next.js build doesn't throw at module eval
let _client: SupabaseClient | null = null

// Server-only Supabase client with service role (bypasses RLS).
// Do NOT expose this key client-side.
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    if (!_client) {
      if (!process.env.SUPABASE_URL) throw new Error('Missing SUPABASE_URL')
      if (!process.env.SUPABASE_SERVICE_ROLE_KEY) throw new Error('Missing SUPABASE_SERVICE_ROLE_KEY')
      _client = createClient(
        process.env.SUPABASE_URL,
        process.env.SUPABASE_SERVICE_ROLE_KEY,
        { auth: { persistSession: false } }
      )
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const value = (_client as any)[prop]
    return typeof value === 'function' ? value.bind(_client) : value
  },
})
