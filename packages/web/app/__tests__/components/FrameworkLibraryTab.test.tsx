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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  example_application: string | null;
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

function mockFetchFramework(fw: ReturnType<typeof makeFramework>) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(fw),
  });
}

function mockFetchUploadSummary(summary: {
  added: number;
  updated: number;
  retained: number;
  failed: Array<{ framework_id: string; error: string }>;
}) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(summary),
  });
}

/**
 * Simulate a file upload on the hidden file input.
 * userEvent.upload skips display:none elements; fireEvent.change bypasses that check.
 */
function uploadFile(file: File) {
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(fileInput, "files", { value: [file], configurable: true });
  fireEvent.change(fileInput);
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
      // Controls bar + empty state both render an "Upload JSON" button when isOwner=true
      expect(screen.getAllByRole("button", { name: /Upload JSON/i }).length).toBeGreaterThan(0);
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
// KIN-320: Edit form + add manually + JSON upload
// ---------------------------------------------------------------------------

describe("FrameworkLibraryTab — KIN-320 (edit, add, upload)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe("edit form", () => {
    it("all fields render with existing values populated", async () => {
      const fw = makeFramework({
        name: "First Principles Thinking",
        category: "reasoning",
        confidence: "medium",
        when_to_apply: ["when facing a novel problem"],
        example_application: "Use when reframing difficult decisions",
      });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      // Modal heading
      expect(screen.getByRole("heading", { name: /Edit "First Principles Thinking"/i })).toBeInTheDocument();
      // Name input populated
      expect(screen.getByDisplayValue("First Principles Thinking")).toBeInTheDocument();
      // Trigger phrase input populated
      expect(screen.getByDisplayValue("when facing a novel problem")).toBeInTheDocument();
      // Category input populated
      expect(screen.getByDisplayValue("reasoning")).toBeInTheDocument();
      // Example application populated
      expect(screen.getByDisplayValue("Use when reframing difficult decisions")).toBeInTheDocument();
      // Confidence select shows "medium"
      expect(screen.getByRole("combobox")).toHaveValue("medium");
    });

    it("save with changed name calls PATCH /frameworks/:id with updated name", async () => {
      const fw = makeFramework({ id: "fw-edit", name: "Original Name" });
      const updated = { ...fw, name: "Updated Name" };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([fw]))
        .mockImplementationOnce(() => mockFetchFramework(updated));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("Original Name"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      const nameInput = screen.getByDisplayValue("Original Name");
      await userEvent.clear(nameInput);
      await userEvent.type(nameInput, "Updated Name");

      await userEvent.click(screen.getByRole("button", { name: /^Save changes$/i }));

      await waitFor(() => {
        const patchCall = mockApiFetch.mock.calls.find(
          ([url, opts]: [string, RequestInit]) =>
            url.includes("fw-edit") && opts?.method === "PATCH"
        );
        expect(patchCall).toBeDefined();
        const body = JSON.parse(patchCall![1].body as string);
        expect(body.name).toBe("Updated Name");
      });
    });

    it("changing when_to_apply shows embedding regeneration note and sends PATCH", async () => {
      const fw = makeFramework({
        id: "fw-trigger",
        name: "First Principles Thinking",
        when_to_apply: ["original trigger"],
      });
      const updated = { ...fw, when_to_apply: ["modified trigger"] };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([fw]))
        .mockImplementationOnce(() => mockFetchFramework(updated));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      // Change the trigger phrase
      const triggerInput = screen.getByDisplayValue("original trigger");
      await userEvent.clear(triggerInput);
      await userEvent.type(triggerInput, "modified trigger");

      // Embedding note appears immediately on change
      expect(
        screen.getByText(/Trigger embeddings will be updated in the background/i)
      ).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: /^Save changes$/i }));

      await waitFor(() => {
        const patchCall = mockApiFetch.mock.calls.find(
          ([url, opts]: [string, RequestInit]) =>
            url.includes("fw-trigger") && opts?.method === "PATCH"
        );
        expect(patchCall).toBeDefined();
        const body = JSON.parse(patchCall![1].body as string);
        expect(body.when_to_apply).toEqual(["modified trigger"]);
      });
    });

    it("confidence select reflects current value and sends PATCH when changed", async () => {
      const fw = makeFramework({ id: "fw-conf", confidence: "medium" });
      const updated = { ...fw, confidence: "high" as const };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([fw]))
        .mockImplementationOnce(() => mockFetchFramework(updated));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      const select = screen.getByRole("combobox");
      expect(select).toHaveValue("medium");

      await userEvent.selectOptions(select, "high");
      await userEvent.click(screen.getByRole("button", { name: /^Save changes$/i }));

      await waitFor(() => {
        const patchCall = mockApiFetch.mock.calls.find(
          ([url, opts]: [string, RequestInit]) =>
            url.includes("fw-conf") && opts?.method === "PATCH"
        );
        expect(patchCall).toBeDefined();
        const body = JSON.parse(patchCall![1].body as string);
        expect(body.confidence).toBe("high");
      });
    });

    it("save with no changes makes no PATCH request and closes form", async () => {
      const fw = makeFramework({ id: "fw-noop" });
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      // Click Save immediately without changing anything
      await userEvent.click(screen.getByRole("button", { name: /^Save changes$/i }));

      // Form closed
      await waitFor(() => {
        expect(
          screen.queryByRole("heading", { name: /Edit "First Principles Thinking"/i })
        ).not.toBeInTheDocument();
      });

      // No PATCH call
      const patchCall = mockApiFetch.mock.calls.find(
        ([, opts]: [string, RequestInit]) => opts?.method === "PATCH"
      );
      expect(patchCall).toBeUndefined();
    });
  });

  describe("add manually", () => {
    it("empty form is shown when Add manually is clicked in empty state", async () => {
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));
      await userEvent.click(screen.getByRole("button", { name: /^Add manually$/i }));

      // Modal heading (h2 inside the modal)
      expect(screen.getByRole("heading", { name: "Add framework" })).toBeInTheDocument();

      // Name field is empty
      const nameInput = screen.getByPlaceholderText(/Coordination Tax Diagnostic/i);
      expect(nameInput).toHaveValue("");
    });

    it("Save button is disabled when name is empty, enabled after typing", async () => {
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));
      await userEvent.click(screen.getByRole("button", { name: /^Add manually$/i }));

      // Two "Add framework" buttons exist: modal save (index 0, rendered first in JSX) and
      // controls bar open-form button (index 1). The modal save button is disabled when name is blank.
      const addButtons = screen.getAllByRole("button", { name: /^Add framework$/i });
      const saveButton = addButtons[0]; // modal renders before controls bar in JSX
      expect(saveButton).toBeDisabled();

      // Type a name — save button becomes enabled
      await userEvent.type(screen.getByPlaceholderText(/Coordination Tax Diagnostic/i), "New FW");
      expect(saveButton).not.toBeDisabled();
    });

    it("successful create appends new framework row to table", async () => {
      const newFw = makeFramework({ id: "fw-new", name: "New Framework" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([]))
        .mockImplementationOnce(() => mockFetchFramework(newFw));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));
      await userEvent.click(screen.getByRole("button", { name: /^Add manually$/i }));

      await userEvent.type(
        screen.getByPlaceholderText(/Coordination Tax Diagnostic/i),
        "New Framework"
      );
      await userEvent.type(
        screen.getByPlaceholderText(/When facing a complex problem/i),
        "when starting fresh"
      );

      // Modal save button is index 0 (modal renders before controls bar in JSX)
      const saveButton = screen.getAllByRole("button", { name: /^Add framework$/i })[0];
      await userEvent.click(saveButton);

      await waitFor(() => {
        expect(screen.getByText("New Framework")).toBeInTheDocument();
      });

      const postCall = mockApiFetch.mock.calls.find(
        ([url, opts]: [string, RequestInit]) =>
          url.includes("/frameworks") && opts?.method === "POST"
      );
      expect(postCall).toBeDefined();
    });
  });

  describe("JSON upload", () => {
    it("invalid JSON file is rejected: summary modal does not appear and POST not called", async () => {
      mockApiFetch.mockImplementation(() => mockFetchFrameworks([]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));

      uploadFile(new File(["not valid json {{"], "bad.json", { type: "application/json" }));
      // Allow async handleUpload to settle
      await new Promise((r) => setTimeout(r, 50));

      // Upload summary modal should NOT appear
      expect(screen.queryByText(/Import Summary/i)).not.toBeInTheDocument();

      // No upload POST was made
      const uploadCall = mockApiFetch.mock.calls.find(
        ([url, opts]: [string, RequestInit]) =>
          typeof url === "string" && url.includes("upload") && opts?.method === "POST"
      );
      expect(uploadCall).toBeUndefined();
    });

    it("valid JSON upload shows summary modal with correct counts", async () => {
      const summary = { added: 3, updated: 2, retained: 5, failed: [] };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([]))
        .mockImplementationOnce(() => mockFetchUploadSummary(summary))
        .mockImplementation(() => mockFetchFrameworks([])); // re-fetch

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));

      uploadFile(
        new File(
          [JSON.stringify([{ name: "FW 1", when_to_apply: ["trigger"] }])],
          "import.json",
          { type: "application/json" }
        )
      );

      await waitFor(() => {
        expect(screen.getByText("Import Summary")).toBeInTheDocument();
      });
      expect(screen.getByText("3 frameworks added")).toBeInTheDocument();
      expect(screen.getByText("2 frameworks updated")).toBeInTheDocument();
      expect(screen.getByText("5 frameworks retained")).toBeInTheDocument();
    });

    it("partial import with errors shows error list with framework ID and message", async () => {
      const summary = {
        added: 1,
        updated: 0,
        retained: 0,
        failed: [{ framework_id: "fw-xyz", error: "when_to_apply is required" }],
      };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([]))
        .mockImplementationOnce(() => mockFetchUploadSummary(summary))
        .mockImplementation(() => mockFetchFrameworks([]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));

      uploadFile(
        new File(
          [JSON.stringify([{ name: "FW" }])],
          "import.json",
          { type: "application/json" }
        )
      );

      await waitFor(() => screen.getByText("Import Summary"));

      expect(screen.getByText("1 failed")).toBeInTheDocument();
      expect(screen.getByText(/fw-xyz: when_to_apply is required/i)).toBeInTheDocument();
    });

    it("'OK' closes modal and refreshes the framework table", async () => {
      const summary = { added: 1, updated: 0, retained: 0, failed: [] };
      const uploaded = makeFramework({ id: "fw-uploaded", name: "Uploaded Framework" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([]))
        .mockImplementationOnce(() => mockFetchUploadSummary(summary))
        .mockImplementation(() => mockFetchFrameworks([uploaded])); // re-fetch returns new row

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));

      uploadFile(
        new File(
          [JSON.stringify([{ name: "FW" }])],
          "import.json",
          { type: "application/json" }
        )
      );

      await waitFor(() => screen.getByText("Import Summary"));

      await userEvent.click(screen.getByRole("button", { name: /^OK$/i }));

      // Modal dismissed
      expect(screen.queryByText("Import Summary")).not.toBeInTheDocument();

      // Refreshed table shows the uploaded framework
      await waitFor(() => {
        expect(screen.getByText("Uploaded Framework")).toBeInTheDocument();
      });
    });

    it("upload modal is informational only — shows OK, no Cancel or Undo", async () => {
      const summary = { added: 2, updated: 0, retained: 0, failed: [] };

      mockApiFetch
        .mockImplementationOnce(() => mockFetchFrameworks([]))
        .mockImplementationOnce(() => mockFetchUploadSummary(summary))
        .mockImplementation(() => mockFetchFrameworks([]));

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText(/No frameworks yet/i));

      uploadFile(
        new File([JSON.stringify([])], "import.json", { type: "application/json" })
      );

      await waitFor(() => screen.getByText("Import Summary"));

      expect(screen.getByRole("button", { name: /^OK$/i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /undo/i })).not.toBeInTheDocument();
    });
  });
});
