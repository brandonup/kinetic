/**
 * ActiveMemoryPanel component tests — KIN-334
 *
 * Spec: docs/specs/active-memory-spec.md §Part 5 (UI)
 * Component: packages/web/components/ActiveMemoryPanel.tsx
 *
 * Strategy: mock `apiFetch` at module level; use @testing-library/user-event
 * for interactions. No real HTTP calls.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mock — must be before component import
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";
import { ActiveMemoryPanel } from "@/components/ActiveMemoryPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const PROJECT_ID = "proj-uuid-1";

function makeEntry(overrides: Partial<{
  id: string;
  content: string;
  created_at: string;
  source_conversation_id: string | null;
}> = {}) {
  return {
    id: "entry-1",
    content: "User prefers bullet points",
    created_at: "2026-03-23T10:00:00.000Z",
    source_conversation_id: null,
    ...overrides,
  };
}

function makeListResponse(entries: ReturnType<typeof makeEntry>[], current_tokens = 100) {
  return {
    entries,
    token_usage: { current_tokens, cap_tokens: 1000 },
  };
}

function mockFetchOk(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
}

function mockFetch422(body: unknown) {
  return Promise.resolve({
    ok: false,
    status: 422,
    json: () => Promise.resolve(body),
  });
}

function mockFetchError() {
  return Promise.resolve({
    ok: false,
    status: 500,
    json: () => Promise.resolve({}),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ActiveMemoryPanel", () => {
  beforeEach(() => {
    // resetAllMocks clears implementations too — prevents stale mockImplementation
    // from one test bleeding into the next via fallback behavior.
    vi.resetAllMocks();
  });

  describe("loading and empty states", () => {
    it("shows loading state while initial fetch is pending", () => {
      // Never resolve — component stays in loading
      mockApiFetch.mockReturnValue(new Promise(() => {}));
      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);
      expect(screen.getByText(/Loading memory/i)).toBeInTheDocument();
    });

    it("shows empty state message when no entries exist", async () => {
      mockApiFetch.mockImplementation(() => mockFetchOk(makeListResponse([])));

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => {
        expect(screen.getByText(/No memory entries yet/i)).toBeInTheDocument();
      });
    });
  });

  describe("entry list rendering", () => {
    it("renders entry content text", async () => {
      const entry = makeEntry({ content: "Prefers async communication" });
      mockApiFetch.mockImplementation(() => mockFetchOk(makeListResponse([entry])));

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => {
        expect(screen.getByText("Prefers async communication")).toBeInTheDocument();
      });
    });

    it("renders token usage as N / cap", async () => {
      mockApiFetch.mockImplementation(() =>
        mockFetchOk({ entries: [], token_usage: { current_tokens: 340, cap_tokens: 1000 } })
      );

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => {
        expect(screen.getByText("340 / 1000")).toBeInTheDocument();
      });
    });

    it("shows near-full warning when usage ≥ 90% of cap", async () => {
      mockApiFetch.mockImplementation(() =>
        mockFetchOk({ entries: [], token_usage: { current_tokens: 920, cap_tokens: 1000 } })
      );

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => {
        expect(screen.getByText(/Memory is almost full/i)).toBeInTheDocument();
      });
    });

    it("does not show near-full warning at < 90% usage", async () => {
      mockApiFetch.mockImplementation(() =>
        mockFetchOk({ entries: [], token_usage: { current_tokens: 500, cap_tokens: 1000 } })
      );

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => {
        expect(screen.queryByText(/Memory is almost full/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("inline edit", () => {
    it("clicking entry content opens edit textarea pre-filled with content", async () => {
      const entry = makeEntry({ content: "I prefer async comms" });
      mockApiFetch.mockImplementation(() => mockFetchOk(makeListResponse([entry])));

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByText("I prefer async comms"));
      await userEvent.click(screen.getByText("I prefer async comms"));

      // Two textareas exist: edit textarea (no placeholder) + add entry textarea.
      // Use getByDisplayValue to target the edit textarea specifically.
      const editTextarea = screen.getByDisplayValue("I prefer async comms") as HTMLTextAreaElement;
      expect(editTextarea.value).toBe("I prefer async comms");
    });

    it("shows soft length warning when edit content exceeds 400 chars", async () => {
      const entry = makeEntry({ content: "short" });
      mockApiFetch.mockImplementation(() => mockFetchOk(makeListResponse([entry])));

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByText("short"));
      await userEvent.click(screen.getByText("short"));

      // Target edit textarea by its current display value; add-entry textarea is separate.
      const editTextarea = screen.getByDisplayValue("short");
      await userEvent.clear(editTextarea);
      await userEvent.type(editTextarea, "x".repeat(401));

      expect(screen.getByText(/Keep entries short/i)).toBeInTheDocument();
    });

    it("save edit calls PATCH with trimmed content", async () => {
      const entry = makeEntry({ id: "entry-abc", content: "Old content" });
      const updated = { ...entry, content: "New content" };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([entry])))
        .mockImplementationOnce(() => mockFetchOk(updated))             // PATCH
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([updated]))); // re-fetch

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByText("Old content"));
      await userEvent.click(screen.getByText("Old content"));

      const editTextarea = screen.getByDisplayValue("Old content");
      await userEvent.clear(editTextarea);
      await userEvent.type(editTextarea, "  New content  ");
      await userEvent.click(screen.getByRole("button", { name: /^Save$/i }));

      await waitFor(() => {
        const patchCall = mockApiFetch.mock.calls.find(
          ([url, opts]) => typeof url === "string" && url.includes("entry-abc") && opts?.method === "PATCH"
        );
        expect(patchCall).toBeDefined();
        const body = JSON.parse(patchCall![1].body as string);
        expect(body.content).toBe("New content");
      });
    });

    it("PATCH 422 shows memory-full error message", async () => {
      const entry = makeEntry({ id: "entry-abc", content: "Old content" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([entry])))
        .mockImplementationOnce(() =>
          mockFetch422({ current_tokens: 990, cap_tokens: 1000 })
        );

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByText("Old content"));
      await userEvent.click(screen.getByText("Old content"));

      const editTextarea = screen.getByDisplayValue("Old content");
      await userEvent.clear(editTextarea);
      await userEvent.type(editTextarea, "Updated");
      await userEvent.click(screen.getByRole("button", { name: /^Save$/i }));

      await waitFor(() => {
        expect(screen.getByText(/Memory is full/i)).toBeInTheDocument();
      });
    });
  });

  describe("delete entry", () => {
    it("delete button calls DELETE endpoint and removes entry from list", async () => {
      const entry = makeEntry({ id: "entry-del", content: "Entry to delete" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([entry])))
        .mockImplementationOnce(() =>
          Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) })
        )
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([]))); // re-fetch

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByText("Entry to delete"));
      await userEvent.click(screen.getByRole("button", { name: /Delete memory entry/i }));

      await waitFor(() => {
        const deleteCall = mockApiFetch.mock.calls.find(
          ([url, opts]) => typeof url === "string" && url.includes("entry-del") && opts?.method === "DELETE"
        );
        expect(deleteCall).toBeDefined();
      });
    });
  });

  describe("add entry", () => {
    it("add entry calls POST /api/v1/active-memory with project_id", async () => {
      const newEntry = makeEntry({ id: "entry-new", content: "New memory" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([])))
        .mockImplementationOnce(() => mockFetchOk(newEntry))               // POST
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([newEntry]))); // re-fetch

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByPlaceholderText(/Add a memory entry/i));

      const textarea = screen.getByPlaceholderText(/Add a memory entry/i);
      await userEvent.type(textarea, "New memory");
      await userEvent.click(screen.getByRole("button", { name: /Add entry/i }));

      await waitFor(() => {
        const postCall = mockApiFetch.mock.calls.find(
          ([url, opts]) => typeof url === "string" && url === "/api/v1/active-memory" && opts?.method === "POST"
        );
        expect(postCall).toBeDefined();
        const body = JSON.parse(postCall![1].body as string);
        expect(body.content).toBe("New memory");
        expect(body.project_id).toBe(PROJECT_ID);
      });
    });

    it("POST 422 shows memory-full error message", async () => {
      mockApiFetch
        .mockImplementationOnce(() => mockFetchOk(makeListResponse([])))
        .mockImplementationOnce(() =>
          mockFetch422({ current_tokens: 1000, cap_tokens: 1000 })
        );

      render(<ActiveMemoryPanel projectId={PROJECT_ID} />);

      await waitFor(() => screen.getByPlaceholderText(/Add a memory entry/i));

      const textarea = screen.getByPlaceholderText(/Add a memory entry/i);
      await userEvent.type(textarea, "New entry");
      await userEvent.click(screen.getByRole("button", { name: /Add entry/i }));

      await waitFor(() => {
        expect(screen.getByText(/Memory is full/i)).toBeInTheDocument();
      });
    });
  });
});
