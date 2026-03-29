import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/projects"),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

vi.mock("@/lib/supabaseClient", () => ({
  supabase: { auth: { signOut: vi.fn(() => Promise.resolve()) } },
}));

const mockApiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

import { AppSidebar } from "@/components/AppSidebar";

function mockApiResponses(overrides?: {
  companies?: unknown[];
  projects?: unknown[];
  conversations?: unknown[];
}) {
  const companies = overrides?.companies ?? [
    { id: "c1", user_id: "u1", name: "Acme Corp", description: null, created_at: "2026-01-01", updated_at: "2026-01-01" },
  ];
  const projects = overrides?.projects ?? [];
  const conversations = overrides?.conversations ?? [];

  mockApiFetch.mockImplementation((url: string) => {
    if (url.includes("/api/v1/companies")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(companies),
      });
    }
    if (url.includes("/api/v1/projects")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ projects }),
      });
    }
    if (url.includes("/api/v1/conversations")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ conversations }),
      });
    }
    return Promise.resolve({ ok: false });
  });
}

describe("AppSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nav items: Companies, Projects, Agents, Profile", () => {
    mockApiResponses();
    render(<AppSidebar />);
    expect(screen.getByText("Companies")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Projects/i })).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Profile")).toBeInTheDocument();
  });

  it("renders company switcher placeholder", () => {
    mockApiResponses();
    render(<AppSidebar />);
    expect(screen.getByTestId("company-switcher")).toBeInTheDocument();
  });

  it("renders conversation history section", () => {
    mockApiResponses();
    render(<AppSidebar />);
    expect(screen.getByTestId("conversation-history")).toBeInTheDocument();
  });

  it("highlights active nav item based on pathname", () => {
    mockApiResponses();
    render(<AppSidebar />);
    const projectsLink = screen.getByRole("link", { name: /projects/i });
    expect(projectsLink).toHaveClass("bg-accent");
  });

  it("renders sidebar projects section", () => {
    mockApiResponses();
    render(<AppSidebar />);
    expect(screen.getByTestId("sidebar-projects")).toBeInTheDocument();
  });

  it("shows 'No projects yet' when company has no projects", async () => {
    mockApiResponses({ projects: [] });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("No projects yet")).toBeInTheDocument();
    });
  });

  it("renders project list when projects exist", async () => {
    mockApiResponses({
      projects: [
        { id: "p1", company_id: "c1", user_id: "u1", name: "Kinetic", instructions: null, created_at: "2026-01-01", updated_at: "2026-03-26" },
        { id: "p2", company_id: "c1", user_id: "u1", name: "Phoenix", instructions: null, created_at: "2026-01-01", updated_at: "2026-03-25" },
      ],
    });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("Kinetic")).toBeInTheDocument();
      expect(screen.getByText("Phoenix")).toBeInTheDocument();
    });
  });

  it("shows 'View all' when more than 5 projects", async () => {
    const manyProjects = Array.from({ length: 7 }, (_, i) => ({
      id: `p${i}`,
      company_id: "c1",
      user_id: "u1",
      name: `Project ${i}`,
      instructions: null,
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    }));
    mockApiResponses({ projects: manyProjects });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("View all")).toBeInTheDocument();
    });
    // Only first 5 should be visible
    expect(screen.getByText("Project 0")).toBeInTheDocument();
    expect(screen.getByText("Project 4")).toBeInTheDocument();
    expect(screen.queryByText("Project 5")).not.toBeInTheDocument();
  });

  it("shows 'No conversations yet' when no conversations", async () => {
    mockApiResponses({ conversations: [] });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("No conversations yet")).toBeInTheDocument();
    });
  });

  it("renders conversation list with title and parent context", async () => {
    mockApiResponses({
      conversations: [
        {
          id: "conv1",
          user_id: "u1",
          company_id: "c1",
          project_id: "p1",
          title: "Fix auth bug",
          active_agent_id: null,
          deleted_at: null,
          created_at: "2026-03-26T10:00:00Z",
          updated_at: "2026-03-26T10:00:00Z",
          project_name: "Kinetic",
          agent_name: null,
        },
        {
          id: "conv2",
          user_id: "u1",
          company_id: "c1",
          project_id: null,
          title: "Agent chat",
          active_agent_id: "a1",
          deleted_at: null,
          created_at: "2026-03-26T09:00:00Z",
          updated_at: "2026-03-26T09:00:00Z",
          project_name: null,
          agent_name: "Nate Jones",
        },
      ],
    });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("Fix auth bug")).toBeInTheDocument();
      expect(screen.getByText("Agent chat")).toBeInTheDocument();
    });
    expect(screen.getByText("Kinetic")).toBeInTheDocument();
    expect(screen.getByText("Nate Jones")).toBeInTheDocument();
  });

  it("shows 'New conversation' when title is null", async () => {
    mockApiResponses({
      conversations: [
        {
          id: "conv1",
          user_id: "u1",
          company_id: "c1",
          project_id: null,
          title: null,
          active_agent_id: null,
          deleted_at: null,
          created_at: "2026-03-26T10:00:00Z",
          updated_at: "2026-03-26T10:00:00Z",
          project_name: null,
          agent_name: null,
        },
      ],
    });
    render(<AppSidebar />);
    await waitFor(() => {
      expect(screen.getByText("New conversation")).toBeInTheDocument();
    });
  });

  it("renders sign out button", () => {
    mockApiResponses();
    render(<AppSidebar />);
    expect(screen.getByTestId("sign-out-button")).toBeInTheDocument();
  });

  it("fetches projects and conversations when company loads", async () => {
    mockApiResponses();
    render(<AppSidebar />);
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/projects?company_id=c1")
      );
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/conversations?company_id=c1")
      );
    });
  });
});
