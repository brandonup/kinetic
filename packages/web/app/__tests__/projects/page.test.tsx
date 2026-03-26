/**
 * ProjectsPage — Knowledge Base section tests — KIN-370
 *
 * Spec: PRD §4 (Projects) + §7 (Knowledge Base)
 * Component: packages/web/app/(app)/projects/page.tsx
 *
 * Strategy: mock apiFetch, KnowledgeBaseTab, ActiveMemoryPanel, ProposalReviewPanel,
 * and useToast. Open Settings on a project, then assert KB section behavior:
 * — renders KnowledgeBaseTab when KB exists
 * — renders Create Knowledge Base button when no KB
 * — Create KB calls POST and then renders KnowledgeBaseTab
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — must be before component imports
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn().mockResolvedValue("Something went wrong"),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

// Stub complex sub-components to isolate page-level KB wiring
vi.mock("@/components/KnowledgeBaseTab", () => ({
  KnowledgeBaseTab: ({ knowledgeBaseId }: { knowledgeBaseId: string | null }) => (
    <div data-testid="kb-tab" data-kb-id={knowledgeBaseId}>
      KB Tab
    </div>
  ),
}));

vi.mock("@/components/ActiveMemoryPanel", () => ({
  ActiveMemoryPanel: () => <div data-testid="active-memory-panel" />,
}));

vi.mock("@/components/ProposalReviewPanel", () => ({
  ProposalReviewPanel: () => <div data-testid="proposal-review-panel" />,
}));

import { apiFetch } from "@/lib/api";
import ProjectsPage from "@/app/(app)/projects/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const CO_ID = "co-uuid-1";
const PROJ_ID = "proj-uuid-1";

function makeCompany(overrides: Record<string, unknown> = {}) {
  return { id: CO_ID, name: "Acme Corp", created_at: "2026-01-01T00:00:00Z", ...overrides };
}

function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: PROJ_ID,
    name: "Alpha",
    company_id: CO_ID,
    instructions: null,
    created_at: "2026-01-01T00:00:00Z",
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

function mockFetchErr(status: number) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: "Not found" }),
    text: () => Promise.resolve(JSON.stringify({ detail: "Not found" })),
  });
}

/**
 * Sets up the default fetch sequence for a rendered ProjectsPage:
 * 1. GET /api/v1/companies
 * 2. GET /api/v1/projects
 *
 * When Settings opens, two more calls fire in parallel:
 * 3. GET /api/v1/active-memory/proposals?project_id=...
 * 4. GET /api/v1/projects/:id/knowledge-base
 *
 * kbResponse: mockFetchOk({ id: "kb-1" }) or mockFetchErr(404)
 */
function setupMocks(kbResponse: ReturnType<typeof mockFetchOk | typeof mockFetchErr>) {
  mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
    if (url.includes("/api/v1/companies")) {
      return mockFetchOk([makeCompany()]);
    }
    if (url.includes("/api/v1/projects") && !url.includes("/knowledge-base") && !opts?.method) {
      return mockFetchOk({ projects: [makeProject()] });
    }
    if (url.includes("/active-memory/proposals")) {
      return mockFetchOk({ proposals: [] });
    }
    if (url.includes("/knowledge-base") && (!opts?.method || opts.method === "GET")) {
      return kbResponse;
    }
    return mockFetchOk({});
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ProjectsPage — Knowledge Base section (KIN-370)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders KnowledgeBaseTab when KB exists for the project", async () => {
    const user = userEvent.setup();
    setupMocks(mockFetchOk({ id: "kb-existing" }));

    render(<ProjectsPage />);

    // Wait for project list to load
    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeInTheDocument();
    });

    // Open Settings
    await user.click(screen.getByRole("button", { name: /settings/i }));

    // Wait for KB to load (kbLoading → false)
    await waitFor(() => {
      expect(screen.getByTestId("kb-tab")).toBeInTheDocument();
    });

    // KnowledgeBaseTab receives the correct KB id
    expect(screen.getByTestId("kb-tab").getAttribute("data-kb-id")).toBe("kb-existing");

    // Create KB button is NOT shown when KB exists
    expect(screen.queryByRole("button", { name: /create knowledge base/i })).not.toBeInTheDocument();
  });

  it("shows Create Knowledge Base button when no KB attached to the project", async () => {
    const user = userEvent.setup();
    setupMocks(mockFetchErr(404));

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /settings/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create knowledge base/i })).toBeInTheDocument();
    });

    // KnowledgeBaseTab is NOT rendered when no KB
    expect(screen.queryByTestId("kb-tab")).not.toBeInTheDocument();
  });

  it("calls POST to create KB and then renders KnowledgeBaseTab", async () => {
    const user = userEvent.setup();

    // Initial GET returns 404 (no KB)
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes("/api/v1/companies")) {
        return mockFetchOk([makeCompany()]);
      }
      if (url.includes("/api/v1/projects") && !url.includes("/knowledge-base") && !opts?.method) {
        return mockFetchOk({ projects: [makeProject()] });
      }
      if (url.includes("/active-memory/proposals")) {
        return mockFetchOk({ proposals: [] });
      }
      // KB GET: 404 (no KB yet)
      if (url.includes("/knowledge-base") && (!opts?.method || opts.method === "GET")) {
        return mockFetchErr(404);
      }
      // KB POST: success
      if (url.includes("/knowledge-base") && opts?.method === "POST") {
        return mockFetchOk({ id: "kb-new" });
      }
      return mockFetchOk({});
    });

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /settings/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create knowledge base/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /create knowledge base/i }));

    // POST to create KB endpoint must have been called
    await waitFor(() => {
      const kbPostCalls = mockApiFetch.mock.calls.filter(
        ([url, opts]: [string, RequestInit?]) =>
          typeof url === "string" &&
          url.includes("/knowledge-base") &&
          opts?.method === "POST",
      );
      expect(kbPostCalls.length).toBeGreaterThanOrEqual(1);
    });

    // After creation, KnowledgeBaseTab appears with the new KB id
    await waitFor(() => {
      expect(screen.getByTestId("kb-tab")).toBeInTheDocument();
    });

    expect(screen.getByTestId("kb-tab").getAttribute("data-kb-id")).toBe("kb-new");
  });
});
