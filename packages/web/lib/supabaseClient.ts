import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

if (typeof window !== "undefined" && (!supabaseUrl || !supabaseAnonKey)) {
  console.error(
    "[kinetic] Missing Supabase environment variables. Check your .env.local file."
  );
}

export const supabase = createBrowserClient(
  supabaseUrl || "http://localhost",
  supabaseAnonKey || "placeholder"
);
