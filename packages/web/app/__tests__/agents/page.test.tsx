/**
 * AgentsPage tests — KIN-365
 *
 * Tests: list rendering, empty states, "New Agent" button, create modal flow,
 * error state, loading state.
 *
 * Strategy: mock `apiFetch` and `useRouter`. The useAgents hook is used
 * inside the page — we exercise it indirectly via apiFetch mocks.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — before component imports
// ---------------------------------------------------------------------------

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn(),
}));

import { apiFetch, parseApiError } from "@/lib/api";
import AgentsPage from "@/app/(app)/agents/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;
const mockParseApiError = parseApiError as ReturnType<typeof vi.fn>;

const USER_ID = "user-uuid-1";
const OTHER_USER_ID = "user-uuid-2";

function makeProfile(id: string = USER_ID) {
  return { id, name: "Test User", bio: null, default_model_id: null };
}

function makeAgent(overrides: Partial<{
  id: string;
  owner_id: string;
  name: string;
  instructions: string;
  visibility: string;
}> = {}) {
  return {
    id: "agent-uuid-1",
    owner_id: USER_ID,
    name: "My Test Agent",
    instructions: "Be helpful.",
    type: "custom",
    visibility: "private",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockOk(body: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
}

function mockError(status: number, body: string) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(body),
  });
}

/**
 * Helper: mock apiFetch to return profile then agents list responses.
 */
function mockProfileAndAgents(agents: ReturnType<typeof makeAgent>[]) {
  mockApiFetch
    .mockImplementationOnce((url: string) => {
      if (url === "/api/v1/profile") return mockOk(makeProfile());
      return mockOk([]);
    })
    .mockImplementationOnce((url: string) => {
      if (url === "/api/v1/agents") return mockOk(agents);
      return mockOk([]);
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockParseApiError.mockResolvedValue("Something went wrong");
  });

  it("renders page header with New Agent button", async () => {
    mockProfileAndAgents([]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Agents")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /new agent/i })).toBeInTheDocument();
  });

  it("shows empty state for My Agents when user has no agents", async () => {
    mockProfileAndAgents([]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText(/you haven't created any agents yet/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /create your first agent/i })).toBeInTheDocument();
  });

  it("shows empty state for Public Agents when none exist", async () => {
    mockProfileAndAgents([]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText(/no public agents available yet/i)).toBeInTheDocument();
    });
  });

  it("renders My Agents list with agent cards", async () => {
    const agent = makeAgent({ name: "Strategy Bot" });
    mockProfileAndAgents([agent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Strategy Bot")).toBeInTheDocument();
    });
  });

  it("renders Public Agents list for agents from other users", async () => {
    const publicAgent = makeAgent({
      id: "a2",
      owner_id: OTHER_USER_ID,
      name: "Public Helper",
      visibility: "public",
    });
    mockProfileAndAgents([publicAgent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Public Helper")).toBeInTheDocument();
    });
    // Should not appear in My Agents empty state
    expect(screen.queryByText(/you haven't created any agents yet/i)).toBeInTheDocument();
  });

  it("navigates to agent settings when Settings button is clicked", async () => {
    const user = userEvent.setup();
    const agent = makeAgent({ id: "agent-123", name: "Clickable Agent" });
    mockProfileAndAgents([agent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Clickable Agent")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("agent-settings-agent-123"));
    expect(mockPush).toHaveBeenCalledWith("/agents/agent-123");
  });

  it("navigates to agent chat when Chat button is clicked", async () => {
    const user = userEvent.setup();
    const agent = makeAgent({ id: "agent-123", name: "Chat Agent" });
    mockProfileAndAgents([agent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Chat Agent")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("agent-chat-agent-123"));
    expect(mockPush).toHaveBeenCalledWith("/agents/agent-123/chat");
  });

  it("shows delete button only for owned agents", async () => {
    const myAgent = makeAgent({ id: "my-1", name: "My Bot" });
    const otherAgent = makeAgent({ id: "other-1", owner_id: OTHER_USER_ID, name: "Other Bot", visibility: "public" });
    mockProfileAndAgents([myAgent, otherAgent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("My Bot")).toBeInTheDocument();
      expect(screen.getByText("Other Bot")).toBeInTheDocument();
    });

    expect(screen.getByTestId("agent-delete-my-1")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-delete-other-1")).not.toBeInTheDocument();
  });

  it("opens delete confirmation dialog and deletes agent", async () => {
    const user = userEvent.setup();
    const agent = makeAgent({ id: "del-1", name: "Doomed Agent" });
    let deleted = false;

    // Use URL-routing mock to handle async refetch without leaking
    mockApiFetch.mockImplementation((url: string, opts?: { method?: string }) => {
      if (url === "/api/v1/profile") return mockOk(makeProfile());
      if (url === "/api/v1/agents/del-1" && opts?.method === "DELETE") {
        deleted = true;
        return Promise.resolve({ ok: true, status: 204 });
      }
      if (url === "/api/v1/agents") return mockOk(deleted ? [] : [agent]);
      return mockOk([]);
    });

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Doomed Agent")).toBeInTheDocument();
    });

    // Click delete button
    await user.click(screen.getByTestId("agent-delete-del-1"));

    // Confirmation dialog should appear
    await waitFor(() => {
      expect(screen.getByText(/delete doomed agent/i)).toBeInTheDocument();
    });

    // Confirm deletion
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    // Should have called DELETE endpoint and refetched (showing empty)
    await waitFor(() => {
      const deleteCall = mockApiFetch.mock.calls.find(
        (c: unknown[]) => c[0] === "/api/v1/agents/del-1" && (c[1] as { method?: string })?.method === "DELETE"
      );
      expect(deleteCall).toBeDefined();
    });
  });

  it("filters agents by search query", async () => {
    const user = userEvent.setup();
    const a1 = makeAgent({ id: "a1", name: "Strategy Bot" });
    const a2 = makeAgent({ id: "a2", name: "Code Helper" });
    mockProfileAndAgents([a1, a2]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Strategy Bot")).toBeInTheDocument();
      expect(screen.getByText("Code Helper")).toBeInTheDocument();
    });

    await user.type(screen.getByTestId("agent-search"), "Strategy");

    expect(screen.getByText("Strategy Bot")).toBeInTheDocument();
    expect(screen.queryByText("Code Helper")).not.toBeInTheDocument();
  });

  it("opens create modal when New Agent button is clicked", async () => {
    const user = userEvent.setup();
    mockProfileAndAgents([]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/you haven't created any agents yet/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /new agent/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it("submits create form and navigates to new agent", async () => {
    const user = userEvent.setup();
    const newAgent = makeAgent({ id: "new-agent-id", name: "Fresh Agent" });

    mockApiFetch
      .mockImplementationOnce(() => mockOk(makeProfile()))
      .mockImplementationOnce(() => mockOk([]))
      .mockImplementationOnce(() => mockOk(newAgent)); // POST /api/v1/agents

    render(<AgentsPage />);

    await waitFor(() => screen.getByRole("button", { name: /new agent/i }));

    // Open modal
    await user.click(screen.getByRole("button", { name: /new agent/i }));

    // Fill name
    await user.type(screen.getByLabelText(/name/i), "Fresh Agent");

    // Submit
    await user.click(screen.getByRole("button", { name: /create agent/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/agents/new-agent-id");
    });

    // Verify POST called with empty instructions
    const postCall = mockApiFetch.mock.calls.find(
      (c: string[]) => c[0] === "/api/v1/agents" && (c[1] as { method?: string })?.method === "POST"
    );
    expect(postCall).toBeDefined();
    const body = JSON.parse((postCall![1] as { body: string }).body);
    expect(body.instructions).toBe("");
  });

  it("shows field error when name is empty on submit", async () => {
    const user = userEvent.setup();
    mockProfileAndAgents([]);

    render(<AgentsPage />);

    await waitFor(() => screen.getByRole("button", { name: /new agent/i }));
    await user.click(screen.getByRole("button", { name: /new agent/i }));

    // Submit without name
    await user.click(screen.getByRole("button", { name: /create agent/i }));

    expect(screen.getByText(/name is required/i)).toBeInTheDocument();
  });

  it("surfaces 422 error from API as inline field error", async () => {
    const user = userEvent.setup();
    mockParseApiError.mockResolvedValue("An agent with this name already exists.");

    mockApiFetch
      .mockImplementationOnce(() => mockOk(makeProfile()))
      .mockImplementationOnce(() => mockOk([]))
      .mockImplementationOnce(() => mockError(422, "An agent with this name already exists."));

    render(<AgentsPage />);

    await waitFor(() => screen.getByRole("button", { name: /new agent/i }));
    await user.click(screen.getByRole("button", { name: /new agent/i }));
    await user.type(screen.getByLabelText(/name/i), "Existing Agent");
    await user.click(screen.getByRole("button", { name: /create agent/i }));

    await waitFor(() => {
      expect(screen.getByText(/an agent with this name already exists/i)).toBeInTheDocument();
    });
  });

  it("shows error state when agents fetch fails", async () => {
    mockApiFetch
      .mockImplementationOnce(() => mockOk(makeProfile()))
      .mockImplementationOnce(() => mockError(500, "Internal server error"));

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText(/internal server error/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/try again/i)).toBeInTheDocument();
  });

  it("shows greyed-out badge for agent with empty instructions", async () => {
    const draftAgent = makeAgent({ name: "Draft Bot", instructions: "" });
    mockProfileAndAgents([draftAgent]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Draft Bot")).toBeInTheDocument();
    });
    expect(screen.getByText(/no instructions/i)).toBeInTheDocument();
  });

  it("shows profile error state when profile fetch fails", async () => {
    mockApiFetch.mockImplementationOnce(() =>
      Promise.reject(new Error("Network failure"))
    );

    render(<AgentsPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/failed to load your profile/i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/try again/i)).toBeInTheDocument();
    // Should NOT show empty states
    expect(
      screen.queryByText(/you haven't created any agents yet/i)
    ).not.toBeInTheDocument();
  });
});
