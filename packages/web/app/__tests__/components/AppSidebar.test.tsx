import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/projects"),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

import { AppSidebar } from "@/components/AppSidebar";

describe("AppSidebar", () => {
  it("renders nav items: Projects, Agents, Profile", () => {
    render(<AppSidebar />);
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("Agents")).toBeInTheDocument();
    expect(screen.getByText("Profile")).toBeInTheDocument();
  });

  it("renders company switcher placeholder", () => {
    render(<AppSidebar />);
    expect(screen.getByTestId("company-switcher")).toBeInTheDocument();
  });

  it("renders conversation history placeholder", () => {
    render(<AppSidebar />);
    expect(screen.getByTestId("conversation-history")).toBeInTheDocument();
  });

  it("highlights active nav item based on pathname", () => {
    render(<AppSidebar />);
    const projectsLink = screen.getByRole("link", { name: /projects/i });
    expect(projectsLink).toHaveClass("bg-accent");
  });
});
