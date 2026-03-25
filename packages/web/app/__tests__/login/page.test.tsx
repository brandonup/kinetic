/**
 * Login page tests — KIN-252, KIN-363
 *
 * Verifies the login page renders the Google OAuth button (Google-only auth for MVP).
 * Supabase client is mocked to prevent real network calls.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock next/navigation — useSearchParams returns null in jsdom without this
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

// Mock Supabase client before importing the component
vi.mock("@/lib/supabaseClient", () => ({
  supabase: {
    auth: {
      signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}));

// Mock useToast — not under test here
vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import LoginPage from "@/app/login/page";
import { supabase } from "@/lib/supabaseClient";

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the Continue with Google button", () => {
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /continue with google/i })).toBeDefined();
  });

  it("does not render a magic link form or email input", () => {
    render(<LoginPage />);
    expect(screen.queryByLabelText(/email/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /magic link/i })).toBeNull();
  });

  it("calls signInWithOAuth on button click", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole("button", { name: /continue with google/i }));

    expect(supabase.auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: expect.stringContaining("/auth/callback"),
      },
    });
  });
});
