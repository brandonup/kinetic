/**
 * AgentChatPage tests — KIN-381
 *
 * Tests: agent title, chat input, model selector, instructions section,
 * active memory section, KB section, recent conversations, not-found state.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ id: "agent-123" })),
  useRouter: vi.fn(() => ({ push: mockPush })),
}));

vi.mock("@/lib/supabaseClient", () => ({
  supabase: { auth: { signOut: vi.fn(() => Promise.resolve()) } },
}));

const mockApiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

vi.mock("@/components/ModelSelector", () => ({
  ModelSelector: ({
    selectedModelId,
    onModelChange,
  }: {
    selectedModelId: string | null;
    onModelChange: (id: string) => void;
  }) => (
    <button
      data-testid="model-selector"
      onClick={() => onModelChange("test-model")}
    >
      {selectedModelId ?? "Select model"}
    </button>
  ),
}));

import AgentChatPage from "@/app/(app)/agents/[id]/chat/page";

function mockAgentApiResponses(overrides?: {
  agent?: unknown;
  conversations?: unknown[];
  memory?: unknown;
}) {
  const agent = overrides?.agent ?? {
    id: "agent-123",
    owner_id: "u1",
    name: "Nate Jones",
    instructions: "You are a strategic advisor.",
    type: "custom",
    visibility: "private",
    created_at: "2026-01-01",
    updated_at: "2026-03-26",
  };
  const conversations = overrides?.conversations ?? [];
  const memory = overrides?.memory ?? {
    entries: [],
    token_usage: { current_tokens: 0, cap_tokens: 1000 },
  };

  mockApiFetch.mockImplementation((url: string) => {
    // Check /instance before the general agents URL to avoid false match.
    if (url.includes("/api/v1/agents/agent-123/instance")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ id: "instance-abc", agent_definition_id: "agent-123", user_id: "u1", framework_overrides: [] }),
      });
    }
    if (url.includes("/api/v1/agents/agent-123")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(agent),
      });
    }
    if (url.includes("/api/v1/conversations")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ conversations }),
      });
    }
    if (url.includes("/api/v1/active-memory")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(memory),
      });
    }
    return Promise.resolve({ ok: false });
  });
}

describe("AgentChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders agent name", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Nate Jones" })
      ).toBeInTheDocument();
    });
  });

  it("renders chat input with agent-specific placeholder", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText("Chat with Nate Jones...")
      ).toBeInTheDocument();
    });
  });

  it("renders agent name badge in chat input area", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      const badges = screen.getAllByText("Nate Jones");
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders model selector", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByTestId("model-selector")).toBeInTheDocument();
    });
  });

  it("renders instructions section in right panel", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Instructions")).toBeInTheDocument();
      expect(
        screen.getByText("You are a strategic advisor.")
      ).toBeInTheDocument();
    });
  });

  it("renders active memory section in right panel", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Active Memory")).toBeInTheDocument();
    });
  });

  it("renders knowledge base section in right panel", async () => {
    mockAgentApiResponses();
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Knowledge Base")).toBeInTheDocument();
    });
  });

  it("shows recent conversations when they exist", async () => {
    mockAgentApiResponses({
      conversations: [
        {
          id: "conv-1",
          user_id: "u1",
          company_id: "comp-1",
          project_id: null,
          title: "Strategy session",
          active_agent_id: "agent-123",
          deleted_at: null,
          created_at: "2026-03-26T10:00:00Z",
          updated_at: "2026-03-26T10:00:00Z",
          project_name: null,
          agent_name: "Nate Jones",
        },
      ],
    });
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Strategy session")).toBeInTheDocument();
      expect(screen.getByText("Recents")).toBeInTheDocument();
    });
  });

  it("shows empty state for instructions when none exist", async () => {
    mockAgentApiResponses({
      agent: {
        id: "agent-123",
        owner_id: "u1",
        name: "Nate Jones",
        instructions: "",
        type: "custom",
        visibility: "private",
        created_at: "2026-01-01",
        updated_at: "2026-03-26",
      },
    });
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(
        screen.getByText("Add instructions for this agent")
      ).toBeInTheDocument();
    });
  });

  it("shows 'Agent not found' when agent doesn't exist", async () => {
    mockApiFetch.mockImplementation(() =>
      Promise.resolve({ ok: false })
    );
    render(<AgentChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Agent not found")).toBeInTheDocument();
    });
  });
});
