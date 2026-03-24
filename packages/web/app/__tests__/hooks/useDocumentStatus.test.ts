/**
 * useDocumentStatus hook tests — KIN-346
 *
 * Tests polling lifecycle: start on mount, stop on terminal status, cleanup on unmount.
 */

import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";
import { useDocumentStatus } from "@/lib/hooks/useDocumentStatus";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const DOC_ID = "doc-uuid-1";

function makeStatusResponse(status: string) {
  return {
    document_id: DOC_ID,
    status,
    error_stage: null,
    error_message: null,
    retry_count: 0,
    tags: [],
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

describe("useDocumentStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("fetches status on mount", async () => {
    mockApiFetch.mockReturnValue(mockFetchOk(makeStatusResponse("completed")));

    const { result } = renderHook(() => useDocumentStatus(DOC_ID));

    await waitFor(() => {
      expect(result.current.data).not.toBeNull();
    });
    expect(result.current.data?.status).toBe("completed");
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
  });

  it("does not fetch when documentId is null", async () => {
    const { result } = renderHook(() => useDocumentStatus(null));

    // Give it a tick
    await act(async () => {
      vi.advanceTimersByTime(100);
    });

    expect(result.current.data).toBeNull();
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it("does not fetch when enabled is false", async () => {
    const { result } = renderHook(() =>
      useDocumentStatus(DOC_ID, { enabled: false }),
    );

    await act(async () => {
      vi.advanceTimersByTime(100);
    });

    expect(result.current.data).toBeNull();
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it("stops polling when status becomes completed", async () => {
    // First fetch: pending (should start polling)
    // Second fetch: completed (should stop polling)
    mockApiFetch
      .mockReturnValueOnce(mockFetchOk(makeStatusResponse("pending")))
      .mockReturnValueOnce(mockFetchOk(makeStatusResponse("completed")))
      .mockReturnValue(mockFetchOk(makeStatusResponse("completed")));

    const { result } = renderHook(() =>
      useDocumentStatus(DOC_ID, { intervalMs: 1000 }),
    );

    // Wait for initial fetch
    await waitFor(() => {
      expect(result.current.data?.status).toBe("pending");
    });

    // Advance past one poll interval
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(result.current.data?.status).toBe("completed");
    });

    // Advance another interval — should NOT fetch again (polling stopped)
    const callCountAfterCompleted = mockApiFetch.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(mockApiFetch.mock.calls.length).toBe(callCountAfterCompleted);
  });

  it("stops polling when status becomes failed", async () => {
    mockApiFetch
      .mockReturnValueOnce(mockFetchOk(makeStatusResponse("extracting")))
      .mockReturnValueOnce(mockFetchOk(makeStatusResponse("failed")))
      .mockReturnValue(mockFetchOk(makeStatusResponse("failed")));

    const { result } = renderHook(() =>
      useDocumentStatus(DOC_ID, { intervalMs: 1000 }),
    );

    await waitFor(() => {
      expect(result.current.data?.status).toBe("extracting");
    });

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(result.current.data?.status).toBe("failed");
    });

    // Advance another interval — should NOT fetch again
    const callCountAfterFailed = mockApiFetch.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(mockApiFetch.mock.calls.length).toBe(callCountAfterFailed);
  });

  it("cleans up interval on unmount", async () => {
    mockApiFetch.mockReturnValue(mockFetchOk(makeStatusResponse("pending")));

    const { unmount } = renderHook(() =>
      useDocumentStatus(DOC_ID, { intervalMs: 1000 }),
    );

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalled();
    });

    unmount();

    // Advance timers — should NOT fetch after unmount
    const callCountAtUnmount = mockApiFetch.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(mockApiFetch.mock.calls.length).toBe(callCountAtUnmount);
  });

  it("sets error on fetch failure", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("Network failure"));

    const { result } = renderHook(() => useDocumentStatus(DOC_ID));

    await waitFor(() => {
      expect(result.current.error).toBe("Network failure");
    });
    expect(result.current.data).toBeNull();
  });
});
