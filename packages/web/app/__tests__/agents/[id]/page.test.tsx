/**
 * Agent Profile Page tests — KIN-366
 *
 * Tests: regenerate button visibility (thought_leader + owner), hidden for custom/non-owner,
 * API call on click, instructions editor.
 *
 * Strategy: mock `apiFetch` and `useToast`. Component renders with mocked agent + profile data.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — before component imports
// ---------------------------------------------------------------------------

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

// Stub tabs that make their own API calls
vi.mock("@/components/FrameworkLibraryTab", () => ({
  FrameworkLibraryTab: () => <div data-testid="framework-tab">Frameworks</div>,
}));

vi.mock("@/components/KnowledgeBaseTab", () => ({
  KnowledgeBaseTab: () => <div data-testid="kb-tab">KB</div>,
}));

import { apiFetch } from "@/lib/api";
import AgentProfilePage from "@/app/(app)/agents/[id]/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const USER_ID = "user-uuid-1";
const AGENT_ID = "agent-uuid-1";

function makeAgent(overrides: Record<string, unknown> = {}) {
  return {
    id: AGENT_ID,
    owner_id: USER_ID,
    name: "Nate Jones",
    instructions: "You are Nate Jones...",
    type: "thought_leader",
    visibility: "private",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeProfile(userId: string = USER_ID) {
  return {
    id: userId,
    full_name: "Brandon",
    short_bio: null,
  };
}

function mockFetchResponses(
  agent: Record<string, unknown>,
  profileUserId: string = USER_ID,
  kbId: string | null = "kb-uuid-1",
) {
  mockApiFetch.mockImplementation((url: string) => {
    if (url.includes("/knowledge-base") && !url.includes("generate")) {
      if (kbId) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: kbId }) });
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: "Not found" }) });
    }
    if (url.includes("/api/v1/agents/") && !url.includes("generate")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(agent) });
    }
    if (url.includes("/api/v1/profile")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeProfile(profileUserId)) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgentProfilePage — Instructions tab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Regenerate button for thought_leader agent when user is owner", async () => {
    mockFetchResponses(makeAgent());

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nate Jones" })).toBeDefined();
    });

    expect(screen.getByRole("button", { name: /regenerate from corpus/i })).toBeDefined();
  });

  it("hides Regenerate button for custom agent", async () => {
    mockFetchResponses(makeAgent({ type: "custom" }));

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nate Jones" })).toBeDefined();
    });

    expect(screen.queryByRole("button", { name: /regenerate from corpus/i })).toBeNull();
  });

  it("hides Regenerate button for non-owner", async () => {
    mockFetchResponses(makeAgent(), "other-user-id");

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nate Jones" })).toBeDefined();
    });

    expect(screen.queryByRole("button", { name: /regenerate from corpus/i })).toBeNull();
  });

  it("calls generate-instructions API on Regenerate click and populates textarea", async () => {
    const user = userEvent.setup();
    mockFetchResponses(makeAgent());

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /regenerate from corpus/i })).toBeDefined();
    });

    // Mock the generate-instructions response
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes("generate-instructions") && opts?.method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ instructions: "Generated: You are Nate Jones, a strategic operator..." }),
        });
      }
      // Default: return agent/profile data
      if (url.includes("/api/v1/agents/") && !url.includes("generate")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeAgent()) });
      }
      if (url.includes("/api/v1/profile")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(makeProfile()) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    await user.click(screen.getByRole("button", { name: /regenerate from corpus/i }));

    // Verify the API was called
    await waitFor(() => {
      const calls = mockApiFetch.mock.calls;
      const generateCall = calls.find(
        ([url, opts]: [string, RequestInit?]) =>
          url.includes("generate-instructions") && opts?.method === "POST"
      );
      expect(generateCall).toBeDefined();
    });

    // Verify textarea shows generated content
    await waitFor(() => {
      const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
      expect(textarea.value).toContain("Generated: You are Nate Jones");
    });
  });
});

describe("AgentProfilePage — Knowledge Base tab (KIN-367)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Create Knowledge Base button when no KB attached and user is owner", async () => {
    const user = userEvent.setup();
    mockFetchResponses(makeAgent(), USER_ID, null); // no KB

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nate Jones" })).toBeDefined();
    });

    // Click KB tab
    await user.click(screen.getByRole("button", { name: /knowledge base/i }));

    expect(screen.getByRole("button", { name: /create knowledge base/i })).toBeDefined();
  });

  it("hides Create Knowledge Base button for non-owner", async () => {
    const user = userEvent.setup();
    mockFetchResponses(makeAgent(), "other-user-id", null); // no KB, not owner

    render(<AgentProfilePage params={{ id: AGENT_ID }} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Nate Jones" })).toBeDefined();
    });

    await user.click(screen.getByRole("button", { name: /knowledge base/i }));

    expect(screen.queryByRole("button", { name: /create knowledge base/i })).toBeNull();
  });
});
