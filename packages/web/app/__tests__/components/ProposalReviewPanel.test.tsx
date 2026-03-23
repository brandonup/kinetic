/**
 * ProposalReviewPanel component tests — KIN-334
 *
 * Spec: docs/specs/active-memory-spec.md §Part 3 (Proposal Queue + Review Flow)
 * Component: packages/web/components/ProposalReviewPanel.tsx
 *
 * Strategy: mock `apiFetch` at module level; verify API calls and UI state.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// ---------------------------------------------------------------------------
// Module-level mock
// ---------------------------------------------------------------------------

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";
import { ProposalReviewPanel } from "@/components/ProposalReviewPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

const PROJECT_ID = "proj-uuid-1";

function makeProposal(overrides: Partial<{
  id: string;
  proposed_content: string;
  trigger_type: string;
  conversation_id: string;
  created_at: string;
}> = {}) {
  return {
    id: "proposal-1",
    proposed_content: "User prefers bullet points over paragraphs",
    trigger_type: "periodic",
    conversation_id: "conv-uuid-1",
    created_at: "2026-03-23T10:00:00.000Z",
    ...overrides,
  };
}

function mockFetchProposals(proposals: ReturnType<typeof makeProposal>[]) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ proposals }),
  });
}

function mockFetchReviewOk(results: { proposal_id: string; action: string }[]) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ results, token_usage: { current_tokens: 50, cap_tokens: 1000 } }),
  });
}

function mockFetchError() {
  return Promise.resolve({
    ok: false,
    status: 500,
    json: () => Promise.resolve({}),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ProposalReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("empty state", () => {
    it("renders nothing when proposal list is empty", async () => {
      mockApiFetch.mockImplementation(() => mockFetchProposals([]));
      const { container } = render(
        <ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />
      );

      await waitFor(() => {
        expect(container.firstChild).toBeNull();
      });
    });
  });

  describe("rendering proposals", () => {
    it("renders proposal content for each pending proposal", async () => {
      const proposals = [
        makeProposal({ id: "p1", proposed_content: "Prefers async comms" }),
        makeProposal({ id: "p2", proposed_content: "Works in short sprints" }),
      ];
      mockApiFetch.mockImplementation(() => mockFetchProposals(proposals));

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => {
        expect(screen.getByText("Prefers async comms")).toBeInTheDocument();
        expect(screen.getByText("Works in short sprints")).toBeInTheDocument();
      });
    });

    it("all proposals default to accept state on load", async () => {
      const proposals = [
        makeProposal({ id: "p1", proposed_content: "Proposal A" }),
        makeProposal({ id: "p2", proposed_content: "Proposal B" }),
      ];
      mockApiFetch.mockImplementation(() => mockFetchProposals(proposals));

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByText("Proposal A"));

      // Both checkboxes should be in "accept" state (aria-label "Uncheck to reject")
      const acceptButtons = screen.getAllByRole("button", { name: /Uncheck to reject/i });
      expect(acceptButtons).toHaveLength(2);
    });
  });

  describe("decision controls", () => {
    it("clicking checkbox toggles proposal from accept to reject", async () => {
      const proposal = makeProposal({ id: "p1", proposed_content: "Toggle me" });
      mockApiFetch.mockImplementation(() => mockFetchProposals([proposal]));

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByText("Toggle me"));

      // Initially accept — click to reject
      const checkbox = screen.getByRole("button", { name: /Uncheck to reject/i });
      await userEvent.click(checkbox);

      expect(screen.getByRole("button", { name: /Check to accept/i })).toBeInTheDocument();
    });

    it("'Reject all' sets all proposals to reject", async () => {
      const proposals = [
        makeProposal({ id: "p1", proposed_content: "A" }),
        makeProposal({ id: "p2", proposed_content: "B" }),
      ];
      mockApiFetch.mockImplementation(() => mockFetchProposals(proposals));

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByText("A"));
      await userEvent.click(screen.getByRole("button", { name: /Reject all/i }));

      const acceptButtons = screen.queryAllByRole("button", { name: /Uncheck to reject/i });
      expect(acceptButtons).toHaveLength(0);
      expect(screen.getAllByRole("button", { name: /Check to accept/i })).toHaveLength(2);
    });

    it("'Accept all' sets all proposals to accept", async () => {
      const proposals = [
        makeProposal({ id: "p1", proposed_content: "A" }),
        makeProposal({ id: "p2", proposed_content: "B" }),
      ];
      mockApiFetch.mockImplementation(() => mockFetchProposals(proposals));

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByText("A"));

      // First reject all
      await userEvent.click(screen.getByRole("button", { name: /Reject all/i }));
      // Then accept all
      await userEvent.click(screen.getByRole("button", { name: /Accept all/i }));

      expect(screen.getAllByRole("button", { name: /Uncheck to reject/i })).toHaveLength(2);
    });
  });

  describe("submit behavior", () => {
    it("'Done' submits POST /api/v1/active-memory/proposals/review with decisions payload", async () => {
      const proposal = makeProposal({ id: "p1", proposed_content: "A" });
      mockApiFetch
        .mockImplementationOnce(() => mockFetchProposals([proposal]))
        .mockImplementationOnce(() =>
          mockFetchReviewOk([{ proposal_id: "p1", action: "accepted" }])
        );

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByText("A"));
      await userEvent.click(screen.getByRole("button", { name: /Done/i }));

      await waitFor(() => {
        const postCall = mockApiFetch.mock.calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("/proposals/review") &&
            opts?.method === "POST"
        );
        expect(postCall).toBeDefined();
        const body = JSON.parse(postCall![1].body as string);
        expect(body.decisions).toHaveLength(1);
        expect(body.decisions[0]).toEqual({ proposal_id: "p1", action: "accept" });
      });
    });

    it("calls onDismiss after successful submit with no cap-exceeded results", async () => {
      const proposal = makeProposal({ id: "p1" });
      const onDismiss = vi.fn();

      mockApiFetch
        .mockImplementationOnce(() => mockFetchProposals([proposal]))
        .mockImplementationOnce(() =>
          mockFetchReviewOk([{ proposal_id: "p1", action: "accepted" }])
        );

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={onDismiss} />);

      await waitFor(() => screen.getByRole("button", { name: /Done/i }));
      await userEvent.click(screen.getByRole("button", { name: /Done/i }));

      await waitFor(() => {
        expect(onDismiss).toHaveBeenCalledOnce();
      });
    });

    it("shows cap-exceeded error inline and does NOT call onDismiss", async () => {
      const proposal = makeProposal({ id: "p1", proposed_content: "Long entry" });
      const onDismiss = vi.fn();

      mockApiFetch
        .mockImplementationOnce(() => mockFetchProposals([proposal]))
        .mockImplementationOnce(() =>
          mockFetchReviewOk([{ proposal_id: "p1", action: "skipped_cap_exceeded" }])
        );

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={onDismiss} />);

      await waitFor(() => screen.getByRole("button", { name: /Done/i }));
      await userEvent.click(screen.getByRole("button", { name: /Done/i }));

      await waitFor(() => {
        expect(screen.getByText(/Memory is full/i)).toBeInTheDocument();
      });
      expect(onDismiss).not.toHaveBeenCalled();
    });

    it("shows error message on network failure during submit", async () => {
      const proposal = makeProposal({ id: "p1" });

      mockApiFetch
        .mockImplementationOnce(() => mockFetchProposals([proposal]))
        .mockImplementationOnce(() => mockFetchError());

      render(<ProposalReviewPanel projectId={PROJECT_ID} onDismiss={vi.fn()} />);

      await waitFor(() => screen.getByRole("button", { name: /Done/i }));
      await userEvent.click(screen.getByRole("button", { name: /Done/i }));

      await waitFor(() => {
        expect(screen.getByText(/Failed to submit review/i)).toBeInTheDocument();
      });
    });
  });
});
