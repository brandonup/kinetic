/**
 * Auth callback route tests — KIN-252
 *
 * Verifies the route handler redirects to origin after exchanging a code.
 * createRouteHandlerClient and cookies are mocked to prevent real Supabase calls.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockExchangeCodeForSession = vi.fn().mockResolvedValue({ data: {}, error: null });

vi.mock("@supabase/ssr", () => ({
  createServerClient: vi.fn(() => ({
    auth: {
      exchangeCodeForSession: mockExchangeCodeForSession,
    },
  })),
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => ({ get: vi.fn(), set: vi.fn() })),
}));

import { GET } from "@/app/auth/callback/route";
import { NextRequest } from "next/server";

describe("GET /auth/callback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExchangeCodeForSession.mockResolvedValue({ data: {}, error: null });
  });

  it("redirects to /projects when code is present and no redirectTo param", async () => {
    const request = new NextRequest("http://localhost:3000/auth/callback?code=test-code-123");
    const response = await GET(request);

    expect(response.status).toBe(307);
    const location = response.headers.get("location")?.replace(/\/$/, "");
    expect(location).toBe("http://localhost:3000/projects");
  });

  it("calls exchangeCodeForSession with the provided code", async () => {
    const request = new NextRequest("http://localhost:3000/auth/callback?code=my-auth-code");
    await GET(request);

    expect(mockExchangeCodeForSession).toHaveBeenCalledWith("my-auth-code");
  });

  it("redirects to /projects when no code is provided (graceful fallback)", async () => {
    const request = new NextRequest("http://localhost:3000/auth/callback");
    const response = await GET(request);

    expect(response.status).toBe(307);
    const location = response.headers.get("location")?.replace(/\/$/, "");
    expect(location).toBe("http://localhost:3000/projects");
    expect(mockExchangeCodeForSession).not.toHaveBeenCalled();
  });

  it("redirects to a valid relative redirectTo path", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/callback?code=abc&redirectTo=%2Fadmin%2Fusers"
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    const location = response.headers.get("location");
    expect(location).toBe("http://localhost:3000/admin/users");
  });

  it("rejects absolute URL redirectTo and falls back to /projects (open redirect prevention)", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/callback?code=abc&redirectTo=https%3A%2F%2Fevil.com"
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    const location = response.headers.get("location");
    expect(location).toBe("http://localhost:3000/projects");
  });

  it("rejects protocol-relative URL redirectTo and falls back to /projects (open redirect prevention)", async () => {
    const request = new NextRequest(
      "http://localhost:3000/auth/callback?code=abc&redirectTo=%2F%2Fevil.com%2Fsteal"
    );
    const response = await GET(request);

    expect(response.status).toBe(307);
    const location = response.headers.get("location");
    expect(location).toBe("http://localhost:3000/projects");
  });
});
