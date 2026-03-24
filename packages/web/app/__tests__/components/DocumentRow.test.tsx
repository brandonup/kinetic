/**
 * DocumentRow component tests — KIN-346
 *
 * Spec: PRD §7 (Knowledge Base & RAG)
 * Component: packages/web/components/DocumentRow.tsx
 *
 * Strategy: mock apiFetch for status polling and retry calls.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn().mockResolvedValue("Something went wrong"),
}));

import { apiFetch } from "@/lib/api";
import { DocumentRow } from "@/components/DocumentRow";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const DOC_ID = "doc-uuid-1";

function mockFetchOk(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

function mockFetchErr(status: number, detail: string) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    text: () => Promise.resolve(JSON.stringify({ detail })),
  });
}

function makeStatusResponse(overrides: Record<string, unknown> = {}) {
  return {
    document_id: DOC_ID,
    status: "completed",
    error_stage: null,
    error_message: null,
    retry_count: 0,
    tags: [],
    ...overrides,
  };
}

describe("DocumentRow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("renders document title and initial status", async () => {
    mockApiFetch.mockReturnValue(mockFetchOk(makeStatusResponse()));

    render(
      <DocumentRow
        documentId={DOC_ID}
        title="architecture.pdf"
        fileType="application/pdf"
        initialStatus="completed"
      />,
    );

    expect(screen.getByText("architecture.pdf")).toBeInTheDocument();
    expect(screen.getByText("PDF")).toBeInTheDocument();
  });

  it("shows retry button only for failed status", async () => {
    mockApiFetch.mockReturnValue(
      mockFetchOk(makeStatusResponse({ status: "failed", error_stage: "chunking" })),
    );

    render(
      <DocumentRow documentId={DOC_ID} title="report.docx" initialStatus="failed" />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  it("does not show retry button for completed status", async () => {
    mockApiFetch.mockReturnValue(mockFetchOk(makeStatusResponse({ status: "completed" })));

    render(
      <DocumentRow documentId={DOC_ID} title="report.docx" initialStatus="completed" />,
    );

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("calls retry endpoint when retry button clicked", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    // First call: status fetch returns failed
    // Second call: retry POST returns success
    // Third call: refetch returns pending
    mockApiFetch
      .mockReturnValueOnce(
        mockFetchOk(makeStatusResponse({ status: "failed", error_stage: "extracting" })),
      )
      .mockReturnValueOnce(
        mockFetchOk({ document_id: DOC_ID, status: "pending", message: "Retry initiated" }),
      )
      .mockReturnValue(
        mockFetchOk(makeStatusResponse({ status: "pending" })),
      );

    render(
      <DocumentRow documentId={DOC_ID} title="data.csv" initialStatus="failed" />,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      // Verify retry endpoint was called
      const retryCalls = mockApiFetch.mock.calls.filter(
        (call: string[]) => typeof call[0] === "string" && call[0].includes("/retry"),
      );
      expect(retryCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows file type label from MIME type", () => {
    mockApiFetch.mockReturnValue(mockFetchOk(makeStatusResponse()));

    render(
      <DocumentRow
        documentId={DOC_ID}
        title="notes.txt"
        fileType="text/plain"
        initialStatus="completed"
      />,
    );

    expect(screen.getByText("PLAIN")).toBeInTheDocument();
  });
});
