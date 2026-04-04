/**
 * Embedding Helper — KIN-428.
 *
 * Decrypts user's OpenAI key from user_api_keys, calls OpenAI embeddings API.
 * Returns embedding as number[] for use with match_chunks / match_framework_triggers RPCs.
 *
 * Port from: packages/mcp/server.py (embed_query helper)
 * Schema ref: db-schema-spec.md §2 (user_api_keys)
 */

import { SupabaseClient } from "@supabase/supabase-js";
import { byteaToUint8Array, decryptApiKey, loadMasterKey } from "./crypto.ts";

const EMBEDDING_MODEL = "text-embedding-3-large";
const EMBEDDING_DIMS = 3072;

/**
 * Fetch and decrypt a user's OpenAI API key.
 *
 * Matches Python: fetch_user_key(supabase, user_id, "openai") in user_keys.py
 *
 * Returns null if no key is configured (not an error — caller handles messaging).
 */
export async function fetchUserOpenAiKey(
  supabase: SupabaseClient,
  userId: string
): Promise<string | null> {
  const { data, error } = await supabase
    .from("user_api_keys")
    .select("key_ciphertext, key_nonce")
    .eq("user_id", userId)
    .eq("provider", "openai")
    .maybeSingle();

  if (error || !data) {
    return null;
  }

  try {
    const masterKey = loadMasterKey();
    const ciphertext = byteaToUint8Array(data.key_ciphertext);
    const nonce = byteaToUint8Array(data.key_nonce);
    return await decryptApiKey(ciphertext, nonce, masterKey, userId);
  } catch (err) {
    console.error(
      `Failed to decrypt OpenAI key for user ${userId} ` +
      "(likely API_KEY_ENCRYPTION_KEY changed since key was stored — " +
      "user must re-save their key in Settings):",
      err
    );
    return null;
  }
}

/**
 * Generate an embedding for a query string using the user's OpenAI key.
 *
 * Returns number[] (3072 dimensions) compatible with extensions.vector(3072)
 * for use in match_chunks and match_framework_triggers RPCs.
 *
 * Throws descriptive error strings matching the MCP error convention:
 *   - "Error: No OpenAI API key configured — add one in Kinetic settings to use this tool"
 *   - "Error: OpenAI API error — <message>"
 */
export async function embedQuery(
  supabase: SupabaseClient,
  userId: string,
  query: string
): Promise<number[]> {
  const apiKey = await fetchUserOpenAiKey(supabase, userId);
  if (!apiKey) {
    throw new Error(
      "Error: No OpenAI API key configured — add one in Kinetic settings to use this tool"
    );
  }

  try {
    const response = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: EMBEDDING_MODEL,
        input: query,
        dimensions: EMBEDDING_DIMS,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      let message = `HTTP ${response.status}`;
      try {
        const parsed = JSON.parse(body);
        message = parsed?.error?.message || message;
      } catch {
        // Use HTTP status as message
      }
      throw new Error(`Error: OpenAI API error — ${message}`);
    }

    const data = await response.json();
    const embedding: number[] = data?.data?.[0]?.embedding;

    if (!embedding || !Array.isArray(embedding)) {
      throw new Error("Error: OpenAI API error — unexpected response format");
    }

    return embedding;
  } catch (err) {
    // Re-throw our formatted errors
    if (err instanceof Error && err.message.startsWith("Error:")) {
      throw err;
    }
    // Wrap unexpected errors
    throw new Error(
      `Error: OpenAI API error — ${err instanceof Error ? err.message : "unknown error"}`
    );
  }
}
