import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: vi.fn(() => ({ id: "proj-123" })),
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
  ModelSelector: ({ selectedModelId, onModelChange }: { selectedModelId: string | null; onModelChange: (id: string) => void }) => (
    <button data-testid="model-selector" onClick={() => onModelChange("test-model")}>
      {selectedModelId ?? "Select model"}
    </button>
  ),
}));

vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: () => ({
    myAgents: [
      { id: "agent-1", owner_id: "u1", name: "Nate Jones", instructions: "", type: "custom", visibility: "private", created_at: "", updated_at: "" },
    ],
    publicAgents: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  }),
}));

import ProjectChatPage from "@/app/(app)/projects/[id]/page";

function mockProjectApiResponses(overrides?: {
  project?: unknown;
  conversations?: unknown[];
  memory?: unknown;
}) {
  const project = overrides?.project ?? {
    id: "proj-123",
    company_id: "comp-1",
    user_id: "u1",
    name: "Kinetic",
    instructions: "Be helpful and concise.",
    created_at: "2026-01-01",
    updated_at: "2026-03-26",
  };
  const conversations = overrides?.conversations ?? [];
  const memory = overrides?.memory ?? { entries: [], token_usage: { current_tokens: 0, cap_tokens: 1000 } };

  mockApiFetch.mockImplementation((url: string) => {
    if (url.includes("/api/v1/projects/proj-123") && !url.includes("knowledge")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(project) });
    }
    if (url.includes("/api/v1/conversations")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ conversations }) });
    }
    if (url.includes("/api/v1/active-memory")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(memory) });
    }
    return Promise.resolve({ ok: false });
  });
}

describe("ProjectChatPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders project title", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Kinetic" })).toBeInTheDocument();
    });
  });

  it("renders chat input with placeholder", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(
        screen.getByPlaceholderText("What would you like to work on in this project?")
      ).toBeInTheDocument();
    });
  });

  it("renders project name badge in chat input area", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      // Project name appears as a badge inside the chat input area
      const badges = screen.getAllByText("Kinetic");
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders model selector", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByTestId("model-selector")).toBeInTheDocument();
    });
  });

  it("renders agents section in right panel", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Agents")).toBeInTheDocument();
      expect(screen.getByText("Nate Jones")).toBeInTheDocument();
    });
  });

  it("renders instructions section in right panel", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Instructions")).toBeInTheDocument();
      expect(screen.getByText("Be helpful and concise.")).toBeInTheDocument();
    });
  });

  it("renders active memory section in right panel", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Active Memory")).toBeInTheDocument();
    });
  });

  it("renders knowledge base section in right panel", async () => {
    mockProjectApiResponses();
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Knowledge Base")).toBeInTheDocument();
    });
  });

  it("shows recent conversations when they exist", async () => {
    mockProjectApiResponses({
      conversations: [
        {
          id: "conv-1",
          user_id: "u1",
          company_id: "comp-1",
          project_id: "proj-123",
          title: "Fix auth bug",
          active_agent_id: null,
          deleted_at: null,
          created_at: "2026-03-26T10:00:00Z",
          updated_at: "2026-03-26T10:00:00Z",
          project_name: "Kinetic",
          agent_name: null,
        },
      ],
    });
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Fix auth bug")).toBeInTheDocument();
      expect(screen.getByText("Recents")).toBeInTheDocument();
    });
  });

  it("shows empty state for instructions when none exist", async () => {
    mockProjectApiResponses({
      project: {
        id: "proj-123",
        company_id: "comp-1",
        user_id: "u1",
        name: "Kinetic",
        instructions: null,
        created_at: "2026-01-01",
        updated_at: "2026-03-26",
      },
    });
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(
        screen.getByText("Add instructions for this project")
      ).toBeInTheDocument();
    });
  });

  it("shows 'Project not found' when project doesn't exist", async () => {
    mockApiFetch.mockImplementation(() =>
      Promise.resolve({ ok: false })
    );
    render(<ProjectChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Project not found")).toBeInTheDocument();
    });
  });
});
