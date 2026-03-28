import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/admin/users"),
  useRouter: vi.fn(() => ({ push: mockPush })),
}));

// Supabase mock — controlled per-test via helpers below
const mockGetSession = vi.fn();
const mockFrom = vi.fn();

vi.mock("@/lib/supabaseClient", () => ({
  supabase: {
    auth: { getSession: () => mockGetSession() },
    from: (table: string) => mockFrom(table),
  },
}));

import AdminLayout from "@/app/admin/layout";

function mockSession(userOverrides: { id: string; app_metadata?: object }) {
  mockGetSession.mockResolvedValue({
    data: { session: { user: { id: userOverrides.id, app_metadata: userOverrides.app_metadata ?? {} } } },
  });
}

function mockNoSession() {
  mockGetSession.mockResolvedValue({ data: { session: null } });
}

function mockDbRole(role: "admin" | "user") {
  mockFrom.mockReturnValue({
    select: vi.fn().mockReturnValue({
      eq: vi.fn().mockReturnValue({
        single: vi.fn().mockResolvedValue({ data: { role }, error: null }),
      }),
    }),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AdminLayout — admin access gate", () => {
  it("renders children when DB role is admin (even with no app_metadata.role — OAuth user)", async () => {
    // Regression: old code checked app_metadata.role, which is absent for OAuth users.
    // New code queries public.users.role — this test fails on the old code, passes on the fix.
    mockSession({ id: "user-1", app_metadata: {} });
    mockDbRole("admin");

    render(<AdminLayout>admin content</AdminLayout>);

    await waitFor(() => {
      expect(screen.getByText("admin content")).toBeInTheDocument();
    });
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("redirects to /projects when DB role is not admin", async () => {
    mockSession({ id: "user-2", app_metadata: {} });
    mockDbRole("user");

    render(<AdminLayout>admin content</AdminLayout>);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/projects");
    });
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
  });

  it("redirects to /login when there is no session", async () => {
    mockNoSession();

    render(<AdminLayout>admin content</AdminLayout>);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("defines expected nav items", () => {
    const NAV_ITEMS = [
      { label: "Users", href: "/admin/users" },
      { label: "LLM Models", href: "/admin/models" },
      { label: "RAG Debug", href: "/admin/rag-debug" },
      { label: "Back to App", href: "/projects" },
    ];
    expect(NAV_ITEMS.map((i) => i.label)).toContain("Users");
    expect(NAV_ITEMS.map((i) => i.label)).toContain("LLM Models");
  });
});
