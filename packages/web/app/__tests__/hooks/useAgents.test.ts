/**
 * useAgents hook tests — KIN-365
 *
 * Tests: fetch on mount, client-side split (myAgents / publicAgents),
 * no-op when currentUserId is null, error handling.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";
import { useAgents } from "@/lib/hooks/useAgents";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const USER_ID = "user-uuid-1";
const OTHER_USER_ID = "user-uuid-2";

function makeAgent(overrides: Partial<{ id: string; owner_id: string; visibility: string; instructions: string }> = {}) {
  return {
    id: "agent-uuid-1",
    owner_id: USER_ID,
    name: "Test Agent",
    instructions: "Be helpful.",
    type: "custom",
    visibility: "private",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockFetchOk(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

function mockFetchError(status: number, text: string) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(text),
  });
}

describe("useAgents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches agents on mount when currentUserId is provided", async () => {
    const agents = [makeAgent()];
    mockApiFetch.mockReturnValue(mockFetchOk(agents));

    const { result } = renderHook(() => useAgents(USER_ID));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockApiFetch).toHaveBeenCalledWith("/api/v1/agents");
    expect(result.current.myAgents).toHaveLength(1);
    expect(result.current.publicAgents).toHaveLength(0);
    expect(result.current.error).toBeNull();
  });

  it("splits agents client-side: owner_id matches → myAgents; others → publicAgents", async () => {
    const myAgent = makeAgent({ id: "a1", owner_id: USER_ID, visibility: "private" });
    const publicAgent = makeAgent({ id: "a2", owner_id: OTHER_USER_ID, visibility: "public" });
    mockApiFetch.mockReturnValue(mockFetchOk([myAgent, publicAgent]));

    const { result } = renderHook(() => useAgents(USER_ID));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.myAgents).toHaveLength(1);
    expect(result.current.myAgents[0].id).toBe("a1");

    expect(result.current.publicAgents).toHaveLength(1);
    expect(result.current.publicAgents[0].id).toBe("a2");
  });

  it("does not fetch when currentUserId is null", async () => {
    const { result } = renderHook(() => useAgents(null));

    // Small tick to confirm no async work
    await new Promise((r) => setTimeout(r, 10));

    expect(mockApiFetch).not.toHaveBeenCalled();
    expect(result.current.myAgents).toHaveLength(0);
    expect(result.current.publicAgents).toHaveLength(0);
  });

  it("sets error on non-ok response", async () => {
    mockApiFetch.mockReturnValue(mockFetchError(500, "Internal server error"));

    const { result } = renderHook(() => useAgents(USER_ID));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe("Internal server error");
    expect(result.current.myAgents).toHaveLength(0);
    expect(result.current.publicAgents).toHaveLength(0);
  });

  it("sets error on network failure", async () => {
    mockApiFetch.mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() => useAgents(USER_ID));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe("Network failure");
  });

  it("refetch re-calls the API and updates data", async () => {
    const initial = [makeAgent({ id: "a1" })];
    const updated = [makeAgent({ id: "a1" }), makeAgent({ id: "a2", owner_id: USER_ID })];

    mockApiFetch
      .mockReturnValueOnce(mockFetchOk(initial))
      .mockReturnValueOnce(mockFetchOk(updated));

    const { result } = renderHook(() => useAgents(USER_ID));

    await waitFor(() => expect(result.current.myAgents).toHaveLength(1));

    await result.current.refetch();

    await waitFor(() => expect(result.current.myAgents).toHaveLength(2));
    expect(mockApiFetch).toHaveBeenCalledTimes(2);
  });
});
