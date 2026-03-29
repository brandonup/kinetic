/**
 * MCP Tokens section tests — KIN-325
 *
 * Tests the MCP Tokens section within the Profile page:
 *  - Empty state rendering
 *  - Token list (label, created, last used)
 *  - "Never" display for null last_used_at
 *  - Generate form open/close
 *  - Generate token → POST → one-time modal appears
 *  - Modal contains token value + copy button + warning
 *  - Dismissing modal removes token from modal state (not from list)
 *  - Revoke confirm dialog opens with token name
 *  - Confirming revoke calls PATCH + removes token from list
 *
 * Strategy: render full ProfilePage with mocked apiFetch. Focus assertions
 * on the MCP Tokens section only. No real HTTP calls.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mocks — must come before component import
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  parseApiError: vi.fn().mockResolvedValue("Something went wrong"),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { apiFetch } from "@/lib/api";
import ProfilePage from "@/app/(app)/profile/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

function makeToken(overrides: Partial<{
  id: string;
  name: string;
  last_used_at: string | null;
  created_at: string;
}> = {}) {
  return {
    id: "token-uuid-1",
    name: "Claude Desktop",
    last_used_at: null,
    created_at: "2026-03-23T10:00:00.000Z",
    ...overrides,
  };
}

function makeOkResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

/**
 * Set up apiFetch to return sensible defaults for the 4 parallel loadAll() calls,
 * plus any extra URL→response mappings passed in `extras`.
 */
function setupLoadAll(
  mcpTokens: ReturnType<typeof makeToken>[] = [],
  extras: Record<string, Response | (() => Response)> = {}
) {
  mockApiFetch.mockImplementation((url: string) => {
    if (url in extras) {
      const v = extras[url];
      return Promise.resolve(typeof v === "function" ? v() : v);
    }
    if (url === "/api/v1/profile") return Promise.resolve(makeOkResponse({ id: "u1", name: "Test User", bio: null, default_model_id: null }));
    if (url === "/api/v1/profile/api-keys") return Promise.resolve(makeOkResponse([]));
    if (url === "/api/v1/admin/models") return Promise.resolve(makeOkResponse({ models: [] }));
    if (url === "/api/v1/mcp/tokens") return Promise.resolve(makeOkResponse({ tokens: mcpTokens }));
    return Promise.resolve(makeOkResponse({}));
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("McpTokensSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock clipboard
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    });
  });

  it("renders empty state when no tokens", async () => {
    setupLoadAll([]);
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("MCP Tokens")).toBeInTheDocument();
    });
    expect(screen.getByText("No tokens yet.")).toBeInTheDocument();
  });

  it("renders token list with label, created date, and last used", async () => {
    const token = makeToken({
      name: "Claude Desktop",
      last_used_at: "2026-03-20T08:00:00.000Z",
      created_at: "2026-03-15T10:00:00.000Z",
    });
    setupLoadAll([token]);
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Claude Desktop")).toBeInTheDocument();
    });
    // Header columns
    expect(screen.getByText("Label")).toBeInTheDocument();
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Last used")).toBeInTheDocument();
  });

  it("shows Never for null last_used_at", async () => {
    setupLoadAll([makeToken({ last_used_at: null })]);
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.getByText("Never")).toBeInTheDocument();
    });
  });

  it("shows a non-Never date for a token that has been used", async () => {
    setupLoadAll([makeToken({ last_used_at: "2026-03-22T12:00:00.000Z" })]);
    render(<ProfilePage />);
    await waitFor(() => {
      expect(screen.queryByText("Never")).not.toBeInTheDocument();
    });
  });

  it("generate form appears on button click and hides on Cancel", async () => {
    const user = userEvent.setup();
    setupLoadAll([]);
    render(<ProfilePage />);
    await waitFor(() => screen.getByText("Generate new token"));

    // Form not visible initially
    expect(screen.queryByPlaceholderText(/Label, e.g. Claude Desktop/i)).not.toBeInTheDocument();

    await user.click(screen.getByText("Generate new token"));
    expect(screen.getByPlaceholderText(/Label, e.g. Claude Desktop/i)).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByPlaceholderText(/Label, e.g. Claude Desktop/i)).not.toBeInTheDocument();
  });

  it("submitting generate form calls POST and shows one-time modal", async () => {
    const user = userEvent.setup();
    const newTokenResp = {
      id: "new-token-id",
      name: "Cursor",
      token: "mcp_abc123def456",
      created_at: "2026-03-23T15:00:00.000Z",
    };
    setupLoadAll([], {
      // POST will hit /api/v1/mcp/tokens but apiFetch is called with url + opts;
      // we handle it via the mock implementation below
    });
    // Override POST separately
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === "/api/v1/mcp/tokens" && opts?.method === "POST") {
        return Promise.resolve(makeOkResponse(newTokenResp));
      }
      if (url === "/api/v1/profile") return Promise.resolve(makeOkResponse({ id: "u1", name: "Test", bio: null, default_model_id: null }));
      if (url === "/api/v1/profile/api-keys") return Promise.resolve(makeOkResponse([]));
      if (url === "/api/v1/admin/models") return Promise.resolve(makeOkResponse({ models: [] }));
      if (url === "/api/v1/mcp/tokens") return Promise.resolve(makeOkResponse({ tokens: [] }));
      return Promise.resolve(makeOkResponse({}));
    });

    render(<ProfilePage />);
    await waitFor(() => screen.getByText("Generate new token"));

    await user.click(screen.getByText("Generate new token"));
    await user.type(screen.getByPlaceholderText(/Label, e.g. Claude Desktop/i), "Cursor");
    await user.click(screen.getByText("Generate"));

    await waitFor(() => {
      expect(screen.getByText("Token generated")).toBeInTheDocument();
    });
    expect(screen.getByText("mcp_abc123def456")).toBeInTheDocument();
    expect(screen.getByText(/Copy this token now/i)).toBeInTheDocument();
  });

  it("modal contains a copy button", async () => {
    const user = userEvent.setup();
    const newTokenResp = {
      id: "new-token-id",
      name: "Cursor",
      token: "mcp_abc123def456",
      created_at: "2026-03-23T15:00:00.000Z",
    };
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === "/api/v1/mcp/tokens" && opts?.method === "POST") {
        return Promise.resolve(makeOkResponse(newTokenResp));
      }
      if (url === "/api/v1/profile") return Promise.resolve(makeOkResponse({ id: "u1", name: "Test", bio: null, default_model_id: null }));
      if (url === "/api/v1/profile/api-keys") return Promise.resolve(makeOkResponse([]));
      if (url === "/api/v1/admin/models") return Promise.resolve(makeOkResponse({ models: [] }));
      if (url === "/api/v1/mcp/tokens") return Promise.resolve(makeOkResponse({ tokens: [] }));
      return Promise.resolve(makeOkResponse({}));
    });

    render(<ProfilePage />);
    await waitFor(() => screen.getByText("Generate new token"));
    await user.click(screen.getByText("Generate new token"));
    await user.type(screen.getByPlaceholderText(/Label, e.g. Claude Desktop/i), "Cursor");
    await user.click(screen.getByText("Generate"));

    await waitFor(() => screen.getByText("Token generated"));
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
  });

  it("dismissing modal removes it from view but token remains in list", async () => {
    const user = userEvent.setup();
    const newTokenResp = {
      id: "new-token-id",
      name: "Cursor",
      token: "mcp_abc123",
      created_at: "2026-03-23T15:00:00.000Z",
    };
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === "/api/v1/mcp/tokens" && opts?.method === "POST") {
        return Promise.resolve(makeOkResponse(newTokenResp));
      }
      if (url === "/api/v1/profile") return Promise.resolve(makeOkResponse({ id: "u1", name: "Test", bio: null, default_model_id: null }));
      if (url === "/api/v1/profile/api-keys") return Promise.resolve(makeOkResponse([]));
      if (url === "/api/v1/admin/models") return Promise.resolve(makeOkResponse({ models: [] }));
      if (url === "/api/v1/mcp/tokens") return Promise.resolve(makeOkResponse({ tokens: [] }));
      return Promise.resolve(makeOkResponse({}));
    });

    render(<ProfilePage />);
    await waitFor(() => screen.getByText("Generate new token"));
    await user.click(screen.getByText("Generate new token"));
    await user.type(screen.getByPlaceholderText(/Label, e.g. Claude Desktop/i), "Cursor");
    await user.click(screen.getByText("Generate"));

    await waitFor(() => screen.getByText("Token generated"));

    // Dismiss with Done
    await user.click(screen.getByRole("button", { name: "Done" }));

    await waitFor(() => {
      expect(screen.queryByText("Token generated")).not.toBeInTheDocument();
    });
    // Token still in list (added optimistically before modal shown)
    expect(screen.getByText("Cursor")).toBeInTheDocument();
  });

  it("revoke button opens confirm dialog with token name", async () => {
    const user = userEvent.setup();
    setupLoadAll([makeToken({ name: "Claude Desktop" })]);
    render(<ProfilePage />);

    await waitFor(() => screen.getByText("Claude Desktop"));
    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() => {
      expect(screen.getByText("Revoke token?")).toBeInTheDocument();
    });
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Claude Desktop/)).toBeInTheDocument();
    expect(within(dialog).getByText(/immediately lose access/i)).toBeInTheDocument();
  });

  it("cancel in revoke dialog closes without revoking", async () => {
    const user = userEvent.setup();
    setupLoadAll([makeToken({ name: "Claude Desktop" })]);
    render(<ProfilePage />);

    await waitFor(() => screen.getByText("Claude Desktop"));
    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => screen.getByText("Revoke token?"));

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByText("Revoke token?")).not.toBeInTheDocument();
    });
    // Token still in list
    expect(screen.getByText("Claude Desktop")).toBeInTheDocument();
  });

  it("confirming revoke calls PATCH and removes token from list", async () => {
    const user = userEvent.setup();
    const token = makeToken({ id: "token-to-revoke", name: "Claude Desktop" });
    setupLoadAll([token]);
    mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === `/api/v1/mcp/tokens/${token.id}/revoke` && opts?.method === "PATCH") {
        return Promise.resolve(makeOkResponse({ id: token.id, revoked_at: "2026-03-23T16:00:00.000Z" }));
      }
      if (url === "/api/v1/profile") return Promise.resolve(makeOkResponse({ id: "u1", name: "Test", bio: null, default_model_id: null }));
      if (url === "/api/v1/profile/api-keys") return Promise.resolve(makeOkResponse([]));
      if (url === "/api/v1/admin/models") return Promise.resolve(makeOkResponse({ models: [] }));
      if (url === "/api/v1/mcp/tokens") return Promise.resolve(makeOkResponse({ tokens: [token] }));
      return Promise.resolve(makeOkResponse({}));
    });

    render(<ProfilePage />);
    await waitFor(() => screen.getByText("Claude Desktop"));

    await user.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => screen.getByText("Revoke token?"));

    // Click the destructive Revoke button in the dialog
    const dialogRevokeBtn = screen.getAllByRole("button", { name: /^Revoke$/i }).find(
      (btn) => btn.closest("[role=dialog]")
    );
    if (!dialogRevokeBtn) throw new Error("Dialog revoke button not found");
    await user.click(dialogRevokeBtn);

    await waitFor(() => {
      expect(screen.queryByText("Claude Desktop")).not.toBeInTheDocument();
    });
    expect(mockApiFetch).toHaveBeenCalledWith(
      `/api/v1/mcp/tokens/${token.id}/revoke`,
      expect.objectContaining({ method: "PATCH" })
    );
  });
});
