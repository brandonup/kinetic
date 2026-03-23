import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock supabase before importing api
vi.mock("@/lib/supabaseClient", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
    },
  },
}));

import { apiFetch, parseApiError, resolveApiBaseUrl } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";

describe("resolveApiBaseUrl", () => {
  it("returns localhost default when no env set", () => {
    const url = resolveApiBaseUrl();
    expect(url).toBe("http://localhost:8000");
  });
});

describe("parseApiError", () => {
  it("extracts detail string from FastAPI error shape", async () => {
    const response = new Response(JSON.stringify({ detail: "Not found" }), {
      status: 404,
    });
    const message = await parseApiError(response);
    expect(message).toBe("Not found");
  });

  it("falls back to generic message on non-JSON response", async () => {
    const response = new Response("Internal Server Error", { status: 500 });
    const message = await parseApiError(response);
    expect(message).toBe("Internal Server Error");
  });
});

describe("apiFetch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("throws when not authenticated and no session", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
      error: null,
    } as any);

    await expect(apiFetch("/api/test")).rejects.toThrow(
      "You are not logged in"
    );
  });
});
