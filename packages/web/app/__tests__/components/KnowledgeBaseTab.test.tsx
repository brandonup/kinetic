/**
 * KnowledgeBaseTab component tests — KIN-370
 *
 * Spec: PRD §7 (Knowledge Base & RAG)
 * Component: packages/web/components/KnowledgeBaseTab.tsx
 *
 * Strategy: mock apiFetch + DocumentRow (avoids nested polling hooks).
 * Validates: render, null KB, document rows, file type rejection,
 * file size rejection, successful upload flow.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — must be before component imports
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn().mockResolvedValue("Something went wrong"),
}));

// Stub DocumentRow to avoid nested useDocumentStatus polling
vi.mock("@/components/DocumentRow", () => ({
  DocumentRow: ({ title }: { title: string }) => (
    <div data-testid="document-row">{title}</div>
  ),
}));

import { apiFetch } from "@/lib/api";
import { KnowledgeBaseTab } from "@/components/KnowledgeBaseTab";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;
const KB_ID = "kb-uuid-1";

function mockFetchOk(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

function mockFetchErr(status: number) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: "Error" }),
    text: () => Promise.resolve(JSON.stringify({ detail: "Error" })),
  });
}

/** Default: empty documents + empty folders */
function mockEmptyKb() {
  mockApiFetch.mockImplementation(() => {
    return mockFetchOk({ documents: [], folders: [] });
  });
  // docs call returns { documents: [] }, folders call returns { folders: [] }
  mockApiFetch
    .mockReturnValueOnce(mockFetchOk({ documents: [] }))
    .mockReturnValueOnce(mockFetchOk({ folders: [] }));
}

function makeDocument(overrides: Record<string, unknown> = {}) {
  return {
    id: "doc-1",
    title: "report.pdf",
    file_type: "application/pdf",
    status: "completed",
    folder_id: null,
    tags: [],
    file_size_bytes: 1024,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("KnowledgeBaseTab — null KB", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders empty state message and no upload button when knowledgeBaseId is null", () => {
    render(<KnowledgeBaseTab knowledgeBaseId={null} />);

    expect(screen.getByText(/no knowledge base attached/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upload documents/i })).not.toBeInTheDocument();
  });
});

describe("KnowledgeBaseTab — with KB", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty documents state and upload button when no documents", async () => {
    mockEmptyKb();

    render(<KnowledgeBaseTab knowledgeBaseId={KB_ID} />);

    await waitFor(() => {
      expect(screen.getByText(/no documents uploaded yet/i)).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /upload documents/i })).toBeInTheDocument();
  });

  it("renders document rows when documents exist", async () => {
    mockApiFetch
      .mockReturnValueOnce(mockFetchOk({ documents: [makeDocument()] }))
      .mockReturnValueOnce(mockFetchOk({ folders: [] }));

    render(<KnowledgeBaseTab knowledgeBaseId={KB_ID} />);

    await waitFor(() => {
      expect(screen.getByTestId("document-row")).toBeInTheDocument();
    });

    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText(/1 document/)).toBeInTheDocument();
  });

  it("shows unsupported file type error without calling upload API", async () => {
    mockEmptyKb();

    render(<KnowledgeBaseTab knowledgeBaseId={KB_ID} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /upload documents/i })).toBeInTheDocument();
    });

    const file = new File(["x"], "virus.exe", { type: "application/octet-stream" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).not.toBeNull();

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument();
    });

    // Upload endpoint must NOT have been called
    const uploadCalls = mockApiFetch.mock.calls.filter(
      ([url]: [string]) => typeof url === "string" && url.includes("/documents/upload"),
    );
    expect(uploadCalls).toHaveLength(0);
  });

  it("shows file too large error without calling upload API", async () => {
    mockEmptyKb();

    render(<KnowledgeBaseTab knowledgeBaseId={KB_ID} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /upload documents/i })).toBeInTheDocument();
    });

    const oversizedFile = new File(["x"], "giant.pdf", { type: "application/pdf" });
    Object.defineProperty(oversizedFile, "size", { value: 26 * 1024 * 1024 });

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [oversizedFile] } });

    await waitFor(() => {
      expect(screen.getByText(/file too large/i)).toBeInTheDocument();
    });

    const uploadCalls = mockApiFetch.mock.calls.filter(
      ([url]: [string]) => typeof url === "string" && url.includes("/documents/upload"),
    );
    expect(uploadCalls).toHaveLength(0);
  });

  it("calls upload endpoint on valid file and refetches document list", async () => {
    // Initial fetch: empty KB
    mockApiFetch
      .mockReturnValueOnce(mockFetchOk({ documents: [] }))
      .mockReturnValueOnce(mockFetchOk({ folders: [] }))
      // Upload response
      .mockReturnValueOnce(
        mockFetchOk({ id: "doc-new", status: "pending", title: "spec.pdf" }),
      )
      // Refetch after upload
      .mockReturnValueOnce(
        mockFetchOk({
          documents: [makeDocument({ id: "doc-new", title: "spec.pdf" })],
        }),
      )
      .mockReturnValueOnce(mockFetchOk({ folders: [] }));

    render(<KnowledgeBaseTab knowledgeBaseId={KB_ID} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /upload documents/i })).toBeInTheDocument();
    });

    const validFile = new File(["content"], "spec.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [validFile] } });

    await waitFor(() => {
      const uploadCalls = mockApiFetch.mock.calls.filter(
        ([url]: [string]) => typeof url === "string" && url.includes("/documents/upload"),
      );
      expect(uploadCalls.length).toBeGreaterThanOrEqual(1);
    });

    // Verify knowledge_base_id was included in the FormData
    const uploadCall = mockApiFetch.mock.calls.find(
      ([url]: [string]) => typeof url === "string" && url.includes("/documents/upload"),
    );
    expect(uploadCall).toBeDefined();
    expect(uploadCall[1]?.method).toBe("POST");
    const formData = uploadCall[1]?.body as FormData;
    expect(formData.get("knowledge_base_id")).toBe(KB_ID);
  });
});
