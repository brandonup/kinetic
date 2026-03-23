/**
 * Login page tests — KIN-252
 *
 * Verifies the login page renders the magic link form and Google OAuth button.
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
      signInWithOtp: vi.fn().mockResolvedValue({ error: null }),
      signInWithOAuth: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}));

// Mock useToast — not under test here
vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the email input", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/email/i)).toBeDefined();
  });

  it("renders the Send magic link button", () => {
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /send magic link/i })).toBeDefined();
  });

  it("renders the Continue with Google button", () => {
    render(<LoginPage />);
    expect(screen.getByRole("button", { name: /continue with google/i })).toBeDefined();
  });

  it("shows confirmation state after magic link is sent", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.click(screen.getByRole("button", { name: /send magic link/i }));

    // After successful OTP send, shows "Check your email" card
    expect(await screen.findByText(/check your email/i)).toBeDefined();
    expect(screen.getByText("test@example.com")).toBeDefined();
  });
});
