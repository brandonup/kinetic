"use client";

/**
 * ProposalReviewPanel — KIN-309
 *
 * Shown when pending memory proposals exist for a project scope.
 * Calls: GET /api/v1/active-memory/proposals, POST /api/v1/active-memory/proposals/review
 *
 * Spec: docs/specs/active-memory-spec.md §Part 3 (Proposal Queue + Review Flow)
 */

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { MemoryProposal, ProposalDecision } from "@/lib/types/models";

interface ProposalReviewPanelProps {
  projectId: string;
  onDismiss: () => void;
}

type DecisionState = "accept" | "reject";

export function ProposalReviewPanel({ projectId, onDismiss }: ProposalReviewPanelProps) {
  const [proposals, setProposals] = useState<MemoryProposal[]>([]);
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [capExceededIds, setCapExceededIds] = useState<Set<string>>(new Set());
  const [submitError, setSubmitError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/v1/active-memory/proposals?project_id=${projectId}`);
      if (res.ok) {
        const data = await res.json();
        const pending: MemoryProposal[] = data.proposals ?? [];
        setProposals(pending);
        // Default all to accept
        const initial: Record<string, DecisionState> = {};
        for (const p of pending) initial[p.id] = "accept";
        setDecisions(initial);
      }
    } catch {
      // silent — panel renders empty, parent re-checks on next settings open
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggle(proposalId: string) {
    setDecisions((prev) => ({
      ...prev,
      [proposalId]: prev[proposalId] === "accept" ? "reject" : "accept",
    }));
    // Clear cap exceeded for this proposal if user changes decision
    setCapExceededIds((prev) => {
      const next = new Set(prev);
      next.delete(proposalId);
      return next;
    });
  }

  function setAll(action: DecisionState) {
    const next: Record<string, DecisionState> = {};
    for (const p of proposals) next[p.id] = action;
    setDecisions(next);
    setCapExceededIds(new Set());
  }

  async function submit() {
    setSubmitting(true);
    setSubmitError(null);
    setCapExceededIds(new Set());

    const payload: ProposalDecision[] = proposals.map((p) => ({
      proposal_id: p.id,
      action: decisions[p.id] ?? "reject",
    }));

    try {
      const res = await apiFetch("/api/v1/active-memory/proposals/review", {
        method: "POST",
        body: JSON.stringify({ decisions: payload }),
      });

      if (res.ok) {
        const data = await res.json();
        const exceeded = new Set<string>();
        for (const result of data.results ?? []) {
          if (result.action === "skipped_cap_exceeded") {
            exceeded.add(result.proposal_id);
          }
        }
        if (exceeded.size > 0) {
          setCapExceededIds(exceeded);
          // Don't dismiss — let user see which ones were skipped
        } else {
          onDismiss();
        }
      } else {
        setSubmitError("Failed to submit review. Try again.");
      }
    } catch {
      setSubmitError("Failed to submit review. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <p className="text-xs text-muted-foreground py-2">Loading suggestions…</p>;
  }

  if (proposals.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-muted/20 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-foreground">
          Memory suggestions from recent conversations
        </p>
        <div className="flex gap-1.5">
          <button
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setAll("accept")}
          >
            Accept all
          </button>
          <span className="text-muted-foreground/40 text-xs">·</span>
          <button
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setAll("reject")}
          >
            Reject all
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {proposals.map((proposal) => {
          const isAccepted = decisions[proposal.id] === "accept";
          const wasExceeded = capExceededIds.has(proposal.id);

          return (
            <div
              key={proposal.id}
              className="flex items-start gap-2.5 rounded-md border border-border px-3 py-2 bg-background"
            >
              <button
                className="mt-0.5 shrink-0 w-4 h-4 rounded border border-border flex items-center justify-center transition-colors"
                style={{
                  backgroundColor: isAccepted ? "hsl(var(--primary))" : "transparent",
                  borderColor: isAccepted ? "hsl(var(--primary))" : undefined,
                }}
                onClick={() => toggle(proposal.id)}
                aria-label={isAccepted ? "Uncheck to reject" : "Check to accept"}
                title={isAccepted ? "Will accept" : "Will reject"}
              >
                {isAccepted && (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="hsl(var(--primary-foreground))"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
              <div className="flex-1 min-w-0 space-y-0.5">
                <p className="text-sm text-foreground">{proposal.proposed_content}</p>
                {wasExceeded && (
                  <p className="text-xs text-destructive">
                    Memory is full — this wasn&apos;t saved. Remove an entry first.
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {submitError && (
        <p className="text-xs text-destructive">{submitError}</p>
      )}

      <div className="flex gap-2">
        <Button size="sm" disabled={submitting} onClick={submit}>
          {submitting ? "Saving…" : "Done"}
        </Button>
        {capExceededIds.size > 0 && (
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        )}
      </div>
    </div>
  );
}
