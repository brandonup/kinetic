/**
 * ProfilePage loading-state tests — KIN-499
 *
 * Verifies API Keys and Default Model sections show a loading placeholder
 * before the fetch resolves, rather than flashing the "Not configured" /
 * "No generation models available" empty states.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn(),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { apiFetch } from "@/lib/api";
import ProfilePage from "@/app/(app)/profile/page";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

function mockOk(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

beforeEach(() => {
  mockApiFetch.mockReset();
});

describe("ProfilePage loading states (KIN-499)", () => {
  it("shows skeleton placeholders for API Keys and Default Model before fetch resolves", () => {
    // Return promises that never resolve so we capture the pre-fetch render.
    mockApiFetch.mockImplementation(() => new Promise(() => {}));

    render(<ProfilePage />);

    expect(screen.getByText("Loading API keys…")).toBeInTheDocument();
    expect(screen.getByText("Loading models…")).toBeInTheDocument();

    // The alarming empty-state messages must not appear during load.
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/No generation models available/i)
    ).not.toBeInTheDocument();
  });

  it("renders empty states only after the fetches resolve", async () => {
    // All four loadAll fetches resolve with empty payloads.
    mockApiFetch.mockImplementation((url: string) => {
      if (url === "/api/v1/profile") {
        return Promise.resolve(
          mockOk({ id: "u1", name: "", email: "", bio: null, default_model_id: null })
        );
      }
      if (url === "/api/v1/profile/api-keys") {
        return Promise.resolve(mockOk([]));
      }
      if (url === "/api/v1/admin/models") {
        return Promise.resolve(mockOk({ models: [] }));
      }
      if (url === "/api/v1/mcp/tokens") {
        return Promise.resolve(mockOk({ tokens: [] }));
      }
      return Promise.resolve(mockOk({}));
    });

    render(<ProfilePage />);

    // After fetch settles, the empty-state messages should appear.
    await waitFor(() => {
      expect(screen.getAllByText("Not configured").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByText(/No generation models available/i)
    ).toBeInTheDocument();

    // And the loading placeholders should be gone.
    expect(screen.queryByText("Loading API keys…")).not.toBeInTheDocument();
    expect(screen.queryByText("Loading models…")).not.toBeInTheDocument();
  });

  it("clears loading state even when fetches reject (no infinite spinner)", async () => {
    mockApiFetch.mockRejectedValue(new Error("network down"));

    render(<ProfilePage />);

    await waitFor(() => {
      expect(screen.queryByText("Loading API keys…")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Loading models…")).not.toBeInTheDocument();
  });
});
