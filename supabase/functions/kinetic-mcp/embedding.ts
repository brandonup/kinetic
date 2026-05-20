/**
 * Embedding Helper — KIN-467.
 *
 * Uses platform Gemini API key to generate embeddings (1024 dims).
 * No BYOK decryption needed — simplifies the embedding path.
 *
 * Returns embedding as number[] for use with match_chunks / match_framework_triggers RPCs.
 */

const EMBEDDING_MODEL = "gemini-embedding-001";
const EMBEDDING_DIMS = 1024;

/**
 * Generate an embedding for a query string using the platform Gemini key.
 *
 * Returns number[] (1024 dimensions) compatible with extensions.vector(1024)
 * for use in match_chunks and match_framework_triggers RPCs.
 *
 * Throws descriptive error strings matching the MCP error convention:
 *   - "Error: GEMINI_API_KEY not configured — contact the platform admin"
 *   - "Error: Gemini API error — <message>"
 */
export async function embedQuery(
  query: string
): Promise<number[]> {
  const apiKey = Deno.env.get("GEMINI_API_KEY");
  if (!apiKey) {
    throw new Error(
      "Error: GEMINI_API_KEY not configured — contact the platform admin"
    );
  }

  try {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${EMBEDDING_MODEL}:embedContent?key=${apiKey}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          content: {
            parts: [{ text: query }],
          },
        }),
      }
    );

    if (!response.ok) {
      const body = await response.text();
      let message = `HTTP ${response.status}`;
      try {
        const parsed = JSON.parse(body);
        message = parsed?.error?.message || message;
      } catch {
        // Use HTTP status as message
      }
      throw new Error(`Error: Gemini API error — ${message}`);
    }

    const data = await response.json();
    const embedding: number[] = data?.embedding?.values;

    if (!embedding || !Array.isArray(embedding)) {
      throw new Error("Error: Gemini API error — unexpected response format");
    }

    return embedding;
  } catch (err) {
    // Re-throw our formatted errors
    if (err instanceof Error && err.message.startsWith("Error:")) {
      throw err;
    }
    // Wrap unexpected errors
    throw new Error(
      `Error: Gemini API error — ${err instanceof Error ? err.message : "unknown error"}`
    );
  }
}
