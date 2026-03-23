/**
 * FrameworkLibraryTab component tests — KIN-330
 *
 * Component: packages/web/components/FrameworkLibraryTab.tsx
 *
 * KIN-319 tests (browse + delete): fully implemented — component is built.
 * KIN-320 tests (edit form + add + JSON upload): skipped stubs — activate when
 *   FrameworkEditForm and FrameworkUploadModal components exist.
 *
 * Strategy: mock `apiFetch` at module level; use @testing-library/user-event
 * for interactions. No real HTTP calls.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — must be before component import
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { apiFetch } from "@/lib/api";
import { FrameworkLibraryTab } from "@/components/FrameworkLibraryTab";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const AGENT_ID = "agent-uuid-1";

function makeFramework(overrides: Partial<{
  id: string;
  name: string;
  category: string | null;
  confidence: "high" | "medium";
  when_to_apply: string[];
  origin: "extracted" | "manual";
}> = {}) {
  return {
    id: "fw-1",
    agent_definition_id: AGENT_ID,
    framework_id: "fw-uuid-1",
    name: "First Principles Thinking",
    description: null,
    category: "reasoning",
    confidence: "high" as const,
    when_to_apply: ["when facing novel problems", "when reframing an issue"],
    origin: "extracted" as const,
    principles: [],
    steps: [],
    example_application: null,
    related_frameworks: [],
    source_posts: null,
    created_at: "2026-03-23T10:00:00.000Z",
    updated_at: "2026-03-23T10:00:00.000Z",
    ...overrides,
  };
}

function mockFetchFrameworks(frameworks: ReturnType<typeof makeFramework>[]) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ frameworks }),
  });
}

function mockFetch204() {
  return Promise.resolve({
    ok: true,
    status: 204,
    json: () => Promise.resolve({}),
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
// KIN-319: Browse + filter + delete tests (fully implemented)
// ---------------------------------------------------------------------------

describe("FrameworkLibraryTab — KIN-319", () => {
  beforeEach(() => {
    // resetAllMocks clears implementations too — prevents stale mockImplementation
    // from one test bleeding into the next via fallback behavior.
    vi.resetAllMocks();
  });

  describe("browse and loading", () => {
    it("shows loading state while initial fetch is pending", () => {
      // Never resolve — component stays in loading
      mockApiFetch.mockReturnValue(new Promise(() => {}));
      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);
      expect(screen.getByText(/Loading frameworks/i)).toBeInTheDocument();
    });

    it("shows empty state with CTAs when agent has no frameworks", async () => {
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([]));
      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => {
        expect(screen.getByText(/No frameworks yet/i)).toBeInTheDocument();
      });
      expect(screen.getByRole("button", { name: /Upload JSON/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Add manually/i })).toBeInTheDocument();
    });

    it("renders framework rows with name, category, confidence, trigger count, and origin", async () => {
      const fw = makeFramework({
        name: "First Principles Thinking",
        category: "reasoning",
        confidence: "high",
        when_to_apply: ["trigger A", "trigger B"],
        origin: "extracted",
      });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => {
        expect(screen.getByText("First Principles Thinking")).toBeInTheDocument();
      });
      // "reasoning" appears twice: category filter button + table cell badge
      expect(screen.getAllByText("reasoning").length).toBeGreaterThan(0);
      expect(screen.getByText("high")).toBeInTheDocument();
      // trigger count = when_to_apply.length = 2
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("extracted")).toBeInTheDocument();
    });

    it("search: partial name match shows only matching frameworks", async () => {
      const fw1 = makeFramework({ id: "fw-1", name: "First Principles Thinking" });
      const fw2 = makeFramework({ id: "fw-2", name: "Inversion Method" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw1, fw2]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));

      const searchInput = screen.getByPlaceholderText(/Search frameworks/i);
      await userEvent.type(searchInput, "Inversion");

      expect(screen.queryByText("First Principles Thinking")).not.toBeInTheDocument();
      expect(screen.getByText("Inversion Method")).toBeInTheDocument();
    });

    it("search: no match shows filter empty state, not the no-frameworks empty state", async () => {
      const fw = makeFramework({ name: "First Principles Thinking" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));

      const searchInput = screen.getByPlaceholderText(/Search frameworks/i);
      await userEvent.type(searchInput, "zzz-no-match");

      expect(screen.getByText(/No frameworks match your filter/i)).toBeInTheDocument();
      expect(screen.queryByText(/No frameworks yet/i)).not.toBeInTheDocument();
    });

    it("category filter shows only frameworks with the selected category", async () => {
      const fw1 = makeFramework({ id: "fw-1", name: "Framework Alpha", category: "reasoning" });
      const fw2 = makeFramework({ id: "fw-2", name: "Framework Beta", category: "communication" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw1, fw2]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

      await waitFor(() => screen.getByText("Framework Alpha"));

      await userEvent.click(screen.getByRole("button", { name: "reasoning" }));

      expect(screen.getByText("Framework Alpha")).toBeInTheDocument();
      expect(screen.queryByText("Framework Beta")).not.toBeInTheDocument();
    });

    it("clicking 'All' clears category filter and shows all frameworks", async () => {
      const fw1 = makeFramework({ id: "fw-1", name: "Framework Alpha", category: "reasoning" });
      const fw2 = makeFramework({ id: "fw-2", name: "Framework Beta", category: "communication" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw1, fw2]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

      await waitFor(() => screen.getByText("Framework Alpha"));

      // Filter to reasoning, then reset
      await userEvent.click(screen.getByRole("button", { name: "reasoning" }));
      await userEvent.click(screen.getByRole("button", { name: "All" }));

      expect(screen.getByText("Framework Alpha")).toBeInTheDocument();
      expect(screen.getByText("Framework Beta")).toBeInTheDocument();
    });

    it("isOwner=false: no Actions column and no Delete button", async () => {
      const fw = makeFramework();
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));

      expect(screen.queryByRole("columnheader", { name: /Actions/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Delete/i })).not.toBeInTheDocument();
    });
  });

  describe("delete", () => {
    it("clicking Delete opens confirm dialog with framework name in copy", async () => {
      const fw = makeFramework({ name: "First Principles Thinking" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Delete$/i }));

      // Dialog heading present (the "Delete framework?" h2)
      expect(screen.getByText(/Delete framework\?/i)).toBeInTheDocument();
      // Framework name appears in the dialog body (text is split by HTML entity nodes)
      expect(screen.getAllByText("First Principles Thinking").length).toBeGreaterThan(0);
      // Confirm dialog shows Cancel + Delete; both Delete buttons are now in DOM
      // (dialog's destructive Delete + table row's ghost Delete)
      expect(screen.getByRole("button", { name: /^Cancel$/i })).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /^Delete$/i })).toHaveLength(2);
    });

    it("Cancel closes dialog without making a DELETE request", async () => {
      const fw = makeFramework({ name: "First Principles Thinking" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Delete$/i }));
      await userEvent.click(screen.getByRole("button", { name: /^Cancel$/i }));

      // Dialog closed
      expect(screen.queryByRole("button", { name: /^Cancel$/i })).not.toBeInTheDocument();
      // Row still present
      expect(screen.getByText("First Principles Thinking")).toBeInTheDocument();
      // No DELETE call was made
      const deleteCall = mockApiFetch.mock.calls.find(
        ([, opts]) => opts?.method === "DELETE"
      );
      expect(deleteCall).toBeUndefined();
    });

    it("Confirm calls DELETE endpoint and removes row from table", async () => {
      const fw = makeFramework({ id: "fw-del", name: "To Delete" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([fw]))
        .mockImplementationOnce(() => mockFetch204());

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("To Delete"));

      // Open dialog — table row Delete button
      await userEvent.click(screen.getByRole("button", { name: /^Delete$/i }));
      // Confirm dialog is rendered BEFORE the table in the JSX, so the confirm
      // dialog's Delete button is deleteButtons[0]; table's Delete button is [1].
      const deleteButtons = screen.getAllByRole("button", { name: /^Delete$/i });
      await userEvent.click(deleteButtons[0]);

      await waitFor(() => {
        const deleteCall = mockApiFetch.mock.calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("fw-del") &&
            opts?.method === "DELETE"
        );
        expect(deleteCall).toBeDefined();
      });

      // Row removed optimistically
      expect(screen.queryByText("To Delete")).not.toBeInTheDocument();
    });

    it.skip("API error on DELETE restores the row", () => {
      // KNOWN BUG (KIN-335 — [Dinesh]): Component uses a React ref for the deleted
      // row snapshot, but `finally` nulls `deletedRowRef.current` synchronously before
      // React executes the queued functional `setFrameworks(prev => [...prev, deletedRowRef.current!])`
      // update callback. By execution time, deletedRowRef.current is null and the
      // restore silently adds null to the list instead of the original row.
      // Fix: capture the ref value into a local const inside catch before queuing setFrameworks.
      // Activate this test once KIN-335 is resolved.
    });
  });
});

// ---------------------------------------------------------------------------
// KIN-320: Edit form + add manually + JSON upload — STUBS
// Activate when FrameworkEditForm and FrameworkUploadModal components are built.
// ---------------------------------------------------------------------------

describe("FrameworkLibraryTab — KIN-320 stubs (edit, add, upload)", () => {
  describe("edit form", () => {
    it.skip("all fields render with existing values populated", () => {
      // KIN-320 — activate when FrameworkEditForm component exists
    });

    it.skip("save with changed name calls PATCH with updated name", () => {
      // KIN-320 — PATCH /api/v1/agents/:agentId/frameworks/:id
    });

    it.skip("save with changed when_to_apply calls PATCH and shows embedding regeneration note", () => {
      // KIN-320 — changing when_to_apply triggers re-embedding; UI should indicate this
    });

    it.skip("confidence stored as decimal: input '75' → API receives 0.75", () => {
      // KIN-320 — confidence display is percentage string but stored as decimal
    });

    it.skip("save with no changes makes no PATCH request", () => {
      // KIN-320 — optimistic no-op if nothing changed
    });
  });

  describe("add manually", () => {
    it.skip("empty form is shown when Add manually is clicked", () => {
      // KIN-320 — activate when add-framework flow exists
    });

    it.skip("required field validation: name and when_to_apply must be non-empty", () => {
      // KIN-320 — POST should not fire with blank required fields
    });

    it.skip("successful create shows new framework row in table", () => {
      // KIN-320 — POST /api/v1/agents/:agentId/frameworks → re-fetch
    });
  });

  describe("JSON upload", () => {
    it.skip("non-JSON file is rejected before upload", () => {
      // KIN-320 — client-side file type guard before POST
    });

    it.skip("valid JSON upload shows summary modal with correct counts", () => {
      // KIN-320 — { added, updated, retained, failed } shown in modal
    });

    it.skip("partial import with errors shows error list with framework ID and message", () => {
      // KIN-320 — failed frameworks listed in modal
    });

    it.skip("'OK' closes modal and refreshes the framework table", () => {
      // KIN-320 — modal dismiss triggers re-fetch
    });

    it.skip("modal is informational only — import is already applied, no second confirm", () => {
      // KIN-320 — modal has no Cancel/Undo; data is already written
    });
  });
});
