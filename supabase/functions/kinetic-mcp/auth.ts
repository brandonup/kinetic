/**
 * Auth middleware for Kinetic Remote MCP Server — KIN-428.
 *
 * Token validation: Bearer mcp_<token> header (preferred) or ?key= query param.
 * Hash: SHA-256 via Web Crypto → lookup in mcp_tokens WHERE revoked_at IS NULL.
 * Rate limit: mcp_check_and_increment_rate_limit RPC, fail-open on error.
 *
 * Port from: packages/api/app/api/routes/mcp.py (_authenticate, _check_rate_limit)
 * Schema ref: db-schema-spec.md §18 (mcp_tokens), §21 (mcp_rate_limits)
 */

import { SupabaseClient } from "@supabase/supabase-js";

/**
 * SHA-256 hash a raw MCP token string to hex.
 * Matches Python: hashlib.sha256(raw.encode("utf-8")).hexdigest()
 */
async function hashToken(raw: string): Promise<string> {
  const data = new TextEncoder().encode(raw);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Result of successful authentication. */
export interface AuthResult {
  userId: string;
}

/**
 * Extract and validate MCP bearer token from a request.
 *
 * Token source priority:
 *   1. Authorization: Bearer mcp_<token> header
 *   2. ?key=mcp_<token> query parameter
 *
 * Returns user_id on success. Throws on invalid/missing/revoked tokens.
 *
 * Side effects:
 *   - Updates last_used_at on the token (fire-and-forget)
 *   - Calls rate limit RPC (fail-open)
 */
export async function authenticate(
  req: Request,
  supabase: SupabaseClient
): Promise<AuthResult> {
  // 1. Extract raw token
  const rawToken = extractToken(req);
  if (!rawToken) {
    throw new Error("Error: Missing or invalid authentication token");
  }

  // 2. Strip mcp_ prefix if present, then SHA-256 hash
  const stripped = rawToken.startsWith("mcp_") ? rawToken.slice(4) : rawToken;
  const tokenHash = await hashToken(stripped);

  // 3. Look up token hash in mcp_tokens
  const { data, error } = await supabase
    .from("mcp_tokens")
    .select("id, user_id, revoked_at")
    .eq("token_hash", tokenHash)
    .is("revoked_at", null)
    .single();

  if (error || !data) {
    throw new Error("Error: Invalid or revoked MCP token");
  }

  const tokenId: string = data.id;
  const userId: string = data.user_id;

  // 4. Fire-and-forget: update last_used_at
  // EdgeRuntime may not complete dangling promises — use waitUntil if available
  const lastUsedPromise = supabase
    .from("mcp_tokens")
    .update({ last_used_at: new Date().toISOString() })
    .eq("id", tokenId)
    .then(() => {})
    .catch(() => {}); // Swallow errors — non-critical

  // Use Deno's built-in to keep the promise alive after response
  if (typeof (globalThis as Record<string, unknown>).EdgeRuntime !== "undefined") {
    // Supabase Edge Functions may have EdgeRuntime.waitUntil
    try {
      (globalThis as Record<string, unknown> & { EdgeRuntime: { waitUntil: (p: Promise<void>) => void } })
        .EdgeRuntime.waitUntil(lastUsedPromise);
    } catch {
      // Fallback: let it run as dangling promise
    }
  }

  // 5. Rate limiting — fail-open on error
  await checkRateLimit(userId, supabase);

  return { userId };
}

/**
 * Extract bearer token from Authorization header or ?key= query param.
 * Header takes precedence if both are present.
 */
function extractToken(req: Request): string | null {
  // Try Authorization header first
  const authHeader = req.headers.get("Authorization") || req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    return authHeader.slice(7); // Strip "Bearer "
  }

  // Fall back to ?key= query param
  try {
    const url = new URL(req.url);
    const keyParam = url.searchParams.get("key");
    if (keyParam) return keyParam;
  } catch {
    // Invalid URL — ignore
  }

  return null;
}

/**
 * Per-user daily rate limit check via RPC.
 *
 * Calls mcp_check_and_increment_rate_limit which atomically increments
 * and returns (allowed, request_count, daily_cap).
 *
 * Fails open on error — rate limit infrastructure issues should not
 * block user requests.
 */
async function checkRateLimit(
  userId: string,
  supabase: SupabaseClient
): Promise<void> {
  const today = new Date().toISOString().split("T")[0]; // YYYY-MM-DD

  try {
    const { data, error } = await supabase.rpc(
      "mcp_check_and_increment_rate_limit",
      { p_user_id: userId, p_date: today }
    );

    if (error) {
      // Fail open — log but don't block
      console.warn("Rate limit RPC error (fail-open):", error.message);
      return;
    }

    const rows = Array.isArray(data) ? data : [];
    if (rows.length > 0 && !rows[0].allowed) {
      throw new Error(
        `Error: Daily rate limit exceeded (${rows[0].request_count}/${rows[0].daily_cap} requests)`
      );
    }
  } catch (err) {
    // Re-throw rate limit exceeded errors
    if (err instanceof Error && err.message.startsWith("Error: Daily rate limit")) {
      throw err;
    }
    // Fail open on infrastructure errors
    console.warn("Rate limit check failed (fail-open):", err);
  }
}
