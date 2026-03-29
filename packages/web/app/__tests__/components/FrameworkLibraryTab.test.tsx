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
    type: null,
    do_not_use_when: [],
    created_at: "2026-03-23T10:00:00.000Z",
    updated_at: "2026-03-23T10:00:00.000Z",
    ...overrides,
  };
}

function mockFetchInstance(overrides: { pinned: string[]; excluded: string[] } = { pinned: [], excluded: [] }) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ framework_overrides: overrides }),
  });
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
 *
 * userEvent.upload and fireEvent.change both fail for display:none inputs: user-event's
 * pointer mechanics use elementFromPoint(0,0) which returns a different visible element,
 * and jsdom's Object.defineProperties getter on fileInput.files is unreliable in React's
 * synthetic event layer. The reliable workaround is to invoke the React onChange prop
 * directly via __reactProps (React 17+ stores current props on DOM nodes under that key).
 * This bypasses DOM simulation entirely and calls handleUpload with a mock event where
 * e.target.files[0] is our file.
 */
function uploadFile(file: File) {
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

  // React 17+ stores the current props on the DOM node under __reactProps$<hash>
  const propsKey = Object.keys(fileInput).find((k) => k.startsWith('__reactProps'));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onChange: ((e: unknown) => void) | undefined = propsKey ? (fileInput as any)[propsKey]?.onChange : undefined;
  if (!onChange) throw new Error('uploadFile: React onChange not found on file input — is the input mounted?');

  const fakeFileList = {
    0: file,
    length: 1,
    item: (i: number) => (i === 0 ? file : null),
    [Symbol.iterator]: function* () { yield file; },
  };

  onChange({ target: { files: fakeFileList } });
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

    it("renders framework rows with name, category, trigger count, and origin", async () => {
      const fw = makeFramework({
        name: "First Principles Thinking",
        category: "reasoning",
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

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "DELETE") return mockFetch204();
        if (url.includes("/instance")) return mockFetchInstance();
        return mockFetchFrameworks([fw]);
      });

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
        when_to_apply: ["when facing a novel problem"],
        example_application: "Use when reframing difficult decisions",
      });
      mockApiFetch.mockImplementation((url: string) => {
        if (url.includes("/instance")) return mockFetchInstance();
        return mockFetchFrameworks([fw]);
      });

      render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

      await waitFor(() => screen.getByText("First Principles Thinking"));
      await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));

      // Modal heading
      expect(screen.getByRole("heading", { name: /Edit "First Principles Thinking"/i })).toBeInTheDocument();
      // Name input populated
      expect(screen.getByDisplayValue("First Principles Thinking")).toBeInTheDocument();
      // When to apply input populated
      expect(screen.getByDisplayValue("when facing a novel problem")).toBeInTheDocument();
      // Category input populated
      expect(screen.getByDisplayValue("reasoning")).toBeInTheDocument();
    });

    it("save with changed name calls PATCH /frameworks/:id with updated name", async () => {
      const fw = makeFramework({ id: "fw-edit", name: "Original Name" });
      const updated = { ...fw, name: "Updated Name" };

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "PATCH" && url.includes("fw-edit")) return mockFetchFramework(updated);
        if (url.includes("/instance")) return mockFetchInstance();
        return mockFetchFrameworks([fw]);
      });

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

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "PATCH" && url.includes("fw-trigger")) return mockFetchFramework(updated);
        if (url.includes("/instance")) return mockFetchInstance();
        return mockFetchFrameworks([fw]);
      });

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

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "POST" && url.includes("/frameworks")) return mockFetchFramework(newFw);
        if (url.includes("/instance")) return mockFetchInstance();
        return mockFetchFrameworks([]);
      });

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

      // Route by method+URL so call ordering doesn't matter (handles StrictMode double-mount)
      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "POST" && url.includes("upload")) return mockFetchUploadSummary(summary);
        return mockFetchFrameworks([]);
      });

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

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "POST" && url.includes("upload")) return mockFetchUploadSummary(summary);
        return mockFetchFrameworks([]);
      });

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
      let uploadDone = false;

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "POST" && url.includes("upload")) {
          uploadDone = true;
          return mockFetchUploadSummary(summary);
        }
        // After upload completes, re-fetch returns the new row
        if (uploadDone) return mockFetchFrameworks([uploaded]);
        return mockFetchFrameworks([]);
      });

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

      mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
        if (opts?.method === "POST" && url.includes("upload")) return mockFetchUploadSummary(summary);
        return mockFetchFrameworks([]);
      });

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

// ---------------------------------------------------------------------------
// KIN-372: Pin / exclude toggles
// ---------------------------------------------------------------------------

describe("FrameworkLibraryTab — KIN-372 (pin/exclude)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("Pin and Exclude buttons render per framework row for owners", async () => {
    const fw = makeFramework({ id: "fw-1", name: "First Principles" });

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/instance")) return mockFetchInstance();
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("First Principles"));

    expect(screen.getByRole("button", { name: /^Pin$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Exclude$/i })).toBeInTheDocument();
  });

  it("Pin and Exclude buttons do NOT render for non-owners", async () => {
    const fw = makeFramework({ id: "fw-1", name: "First Principles" });

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/instance")) return mockFetchInstance();
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={false} />);

    await waitFor(() => screen.getByText("First Principles"));

    expect(screen.queryByRole("button", { name: /^Pin$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Exclude$/i })).not.toBeInTheDocument();
  });

  it("pinned framework shows 'Pinned' badge and 'Unpin' button", async () => {
    const fw = makeFramework({ id: "fw-pinned", name: "Pinned Framework" });

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/instance")) return mockFetchInstance({ pinned: [fw.framework_id], excluded: [] });
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Pinned Framework"));

    expect(screen.getByText("Pinned")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Unpin$/i })).toBeInTheDocument();
    // Exclude button still shows (not currently excluded)
    expect(screen.getByRole("button", { name: /^Exclude$/i })).toBeInTheDocument();
  });

  it("excluded framework shows 'Excluded' badge, strikethrough name, and 'Include' button", async () => {
    const fw = makeFramework({ id: "fw-excl", name: "Excluded Framework" });

    mockApiFetch.mockImplementation((url: string) => {
      if (url.includes("/instance")) return mockFetchInstance({ pinned: [], excluded: [fw.framework_id] });
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Excluded Framework"));

    expect(screen.getByText("Excluded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Include$/i })).toBeInTheDocument();
    // Pin button still shows (not currently pinned)
    expect(screen.getByRole("button", { name: /^Pin$/i })).toBeInTheDocument();
    // Name has line-through style
    const nameSpan = screen.getByText("Excluded Framework");
    expect(nameSpan.className).toContain("line-through");
  });

  it("clicking Pin calls PATCH with framework_id in pinned array", async () => {
    const fw = makeFramework({ id: "fw-topin", name: "Pin Me" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) {
        return mockFetchInstance({ pinned: [fw.framework_id], excluded: [] });
      }
      if (url.includes("/instance")) return mockFetchInstance();
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Pin Me"));
    await userEvent.click(screen.getByRole("button", { name: /^Pin$/i }));

    await waitFor(() => {
      const patchCall = mockApiFetch.mock.calls.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (call: any[]) => call[0]?.includes("/instance") && call[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1].body as string);
      expect(body.framework_overrides.pinned).toContain(fw.framework_id);
      expect(body.framework_overrides.excluded).not.toContain(fw.framework_id);
    });
  });

  it("clicking Exclude calls PATCH with framework_id in excluded array", async () => {
    const fw = makeFramework({ id: "fw-toexcl", name: "Exclude Me" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) {
        return mockFetchInstance({ pinned: [], excluded: [fw.framework_id] });
      }
      if (url.includes("/instance")) return mockFetchInstance();
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Exclude Me"));
    await userEvent.click(screen.getByRole("button", { name: /^Exclude$/i }));

    await waitFor(() => {
      const patchCall = mockApiFetch.mock.calls.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (call: any[]) => call[0]?.includes("/instance") && call[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1].body as string);
      expect(body.framework_overrides.excluded).toContain(fw.framework_id);
      expect(body.framework_overrides.pinned).not.toContain(fw.framework_id);
    });
  });

  it("mutual exclusion: pinning an excluded framework removes it from excluded", async () => {
    const fw = makeFramework({ id: "fw-switch", name: "Switch Me" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) {
        const body = JSON.parse(opts.body as string);
        return mockFetchInstance(body.framework_overrides);
      }
      if (url.includes("/instance")) return mockFetchInstance({ pinned: [], excluded: [fw.framework_id] });
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Switch Me"));
    // Framework starts excluded — Pin button should be visible
    expect(screen.getByRole("button", { name: /^Pin$/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^Pin$/i }));

    await waitFor(() => {
      const patchCall = mockApiFetch.mock.calls.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (call: any[]) => call[0]?.includes("/instance") && call[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1].body as string);
      expect(body.framework_overrides.pinned).toContain(fw.framework_id);
      expect(body.framework_overrides.excluded).not.toContain(fw.framework_id);
    });
  });

  it("mutual exclusion: excluding a pinned framework removes it from pinned", async () => {
    const fw = makeFramework({ id: "fw-switch2", name: "Switch Two" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) {
        const body = JSON.parse(opts.body as string);
        return mockFetchInstance(body.framework_overrides);
      }
      if (url.includes("/instance")) return mockFetchInstance({ pinned: [fw.framework_id], excluded: [] });
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Switch Two"));
    // Framework starts pinned — Exclude button should be visible
    expect(screen.getByRole("button", { name: /^Exclude$/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^Exclude$/i }));

    await waitFor(() => {
      const patchCall = mockApiFetch.mock.calls.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (call: any[]) => call[0]?.includes("/instance") && call[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1].body as string);
      expect(body.framework_overrides.excluded).toContain(fw.framework_id);
      expect(body.framework_overrides.pinned).not.toContain(fw.framework_id);
    });
  });

  it("Unpin clears framework from pinned array", async () => {
    const fw = makeFramework({ id: "fw-unpin", name: "Unpin Me" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) {
        const body = JSON.parse(opts.body as string);
        return mockFetchInstance(body.framework_overrides);
      }
      if (url.includes("/instance")) return mockFetchInstance({ pinned: [fw.framework_id], excluded: [] });
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Unpin Me"));
    await userEvent.click(screen.getByRole("button", { name: /^Unpin$/i }));

    await waitFor(() => {
      const patchCall = mockApiFetch.mock.calls.find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (call: any[]) => call[0]?.includes("/instance") && call[1]?.method === "PATCH"
      );
      expect(patchCall).toBeDefined();
      const body = JSON.parse(patchCall![1].body as string);
      expect(body.framework_overrides.pinned).not.toContain(fw.framework_id);
    });
  });

  it("PATCH failure rolls back optimistic override and shows error toast", async () => {
    const fw = makeFramework({ id: "fw-fail", name: "Fail Pin" });

    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (opts?.method === "PATCH" && url.includes("/instance")) return mockFetchError();
      if (url.includes("/instance")) return mockFetchInstance();
      return mockFetchFrameworks([fw]);
    });

    render(<FrameworkLibraryTab agentId={AGENT_ID} isOwner={true} />);

    await waitFor(() => screen.getByText("Fail Pin"));
    await userEvent.click(screen.getByRole("button", { name: /^Pin$/i }));

    // After error, badge should not persist — button should revert to "Pin"
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Pin$/i })).toBeInTheDocument();
    });
    expect(screen.queryByText("Pinned")).not.toBeInTheDocument();
  });
});
