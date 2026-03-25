import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const rawRedirect = requestUrl.searchParams.get("redirectTo") ?? "/projects";
  // Clamp to relative paths — rejects absolute URLs and protocol-relative URLs to prevent open redirect
  const redirectTo =
    rawRedirect.startsWith("/") && !rawRedirect.startsWith("//")
      ? rawRedirect
      : "/projects";

  const redirectUrl = new URL(redirectTo, requestUrl.origin);
  const response = NextResponse.redirect(redirectUrl);

  if (code) {
    const cookieStore = cookies();
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          get(name: string) {
            return cookieStore.get(name)?.value;
          },
          set(name: string, value: string, options: CookieOptions) {
            response.cookies.set({ name, value, ...options });
          },
          remove(name: string, options: CookieOptions) {
            response.cookies.set({ name, value: "", ...options });
          },
        },
      }
    );
    await supabase.auth.exchangeCodeForSession(code);
  }

  return response;
}
