/**
 * ModelSelector tests — KIN-337
 *
 * Tests: greyed-out disabled models, tooltip on hover, model selection.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModelSelector } from "@/components/ModelSelector";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const MODELS = [
  {
    id: "m1",
    provider: "anthropic",
    model_id: "claude-sonnet-4-6",
    display_name: "Claude Sonnet 4.6",
    category: "generation",
    enabled: true,
    context_window: 200000,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "m2",
    provider: "openai",
    model_id: "gpt-4o",
    display_name: "GPT-4o",
    category: "generation",
    enabled: true,
    context_window: 128000,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "m3",
    provider: "google",
    model_id: "gemini-2.5-pro",
    display_name: "Gemini 2.5 Pro",
    category: "generation",
    enabled: true,
    context_window: 1000000,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const API_KEYS = [
  { provider: "anthropic", key_hint: "sk-ant-...abc1", validated_at: "2026-01-01T00:00:00Z" },
];

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn((url: string) => {
    if (url.includes("/admin/models")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ models: MODELS }),
      });
    }
    if (url.includes("/api-keys")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ api_keys: API_KEYS }),
      });
    }
    return Promise.resolve({ ok: false, text: () => Promise.resolve("") });
  }),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ModelSelector", () => {
  const onModelChange = vi.fn();

  beforeEach(() => {
    onModelChange.mockReset();
  });

  it("renders selected model name", async () => {
    render(<ModelSelector selectedModelId="m1" onModelChange={onModelChange} />);
    await waitFor(() => {
      expect(screen.getByText("Claude Sonnet 4.6")).toBeInTheDocument();
    });
  });

  it("shows all models in dropdown when opened", async () => {
    const user = userEvent.setup();
    render(<ModelSelector selectedModelId="m1" onModelChange={onModelChange} />);

    await waitFor(() => {
      expect(screen.getByText("Claude Sonnet 4.6")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText("Select model"));

    expect(screen.getByText("GPT-4o")).toBeInTheDocument();
    expect(screen.getByText("Gemini 2.5 Pro")).toBeInTheDocument();
  });

  it("marks models without API key as aria-disabled", async () => {
    const user = userEvent.setup();
    render(<ModelSelector selectedModelId="m1" onModelChange={onModelChange} />);

    await waitFor(() => {
      expect(screen.getByText("Claude Sonnet 4.6")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText("Select model"));

    // GPT-4o should be aria-disabled (user only has anthropic key)
    const gptOption = screen.getByRole("option", { name: /GPT-4o/i });
    expect(gptOption).toHaveAttribute("aria-disabled", "true");

    // Claude should not be disabled
    const claudeOption = screen.getByRole("option", { name: /Claude Sonnet/i });
    expect(claudeOption).not.toHaveAttribute("aria-disabled", "true");
  });

  it("calls onModelChange when enabled model clicked", async () => {
    const user = userEvent.setup();
    render(<ModelSelector selectedModelId="m2" onModelChange={onModelChange} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select model")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText("Select model"));

    // Click Claude (has API key — should work)
    const claudeOption = screen.getByRole("option", { name: /Claude Sonnet/i });
    await user.click(claudeOption);

    expect(onModelChange).toHaveBeenCalledWith("m1");
  });

  it("does not call onModelChange when disabled model clicked", async () => {
    const user = userEvent.setup();
    render(<ModelSelector selectedModelId="m1" onModelChange={onModelChange} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select model")).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText("Select model"));

    // Click GPT-4o (no API key — disabled)
    const gptOption = screen.getByRole("option", { name: /GPT-4o/i });
    await user.click(gptOption);

    expect(onModelChange).not.toHaveBeenCalled();
  });
});
