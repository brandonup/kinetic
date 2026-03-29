"use client";

/**
 * Admin RAG Debug Page — KIN-326
 *
 * Trace list with scope filter + expandable detail panel.
 * API: GET /api/v1/admin/rag-debug, GET /api/v1/admin/rag-debug/{id}
 * Spec ref: docs/specs/rag-debug-tab-spec.md §3
 */

import React, { useEffect, useState, useCallback } from "react";

import { apiFetch, parseApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ScopeFilter = "all" | "project_kb" | "agent_kb";
type GatingDecision = "injected" | "below_threshold" | "error";

interface RagTraceSummary {
  id: string;
  message_id: string;
  scope: string;
  query_text: string;
  gating_decision: string;
  created_at: string;
  injected_chunk_count: number;
  vector_candidate_count: number;
}

interface VectorCandidate {
  chunk_id: string;
  score: number;
}

interface InjectedChunk {
  chunk_id: string;
  score: number;
  text_preview: string;
  document_title?: string;
  section_path?: string;
}

interface RagTraceDetail extends RagTraceSummary {
  query_variants: string[] | null;
  vector_candidates: VectorCandidate[] | null;
  mmr_selections: VectorCandidate[] | null;
  rerank_scores: null;
  injected_chunks: InjectedChunk[] | null;
  error_message: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "…" : text;
}

const SCOPE_LABELS: Record<string, string> = {
  project_kb: "Project KB",
  agent_kb: "Agent KB",
};

const GATING_COLORS: Record<string, string> = {
  injected:
    "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  below_threshold:
    "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  error: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
};

function GatingBadge({ decision }: { decision: string }) {
  const color =
    GATING_COLORS[decision] ??
    "bg-muted text-muted-foreground";
  const label =
    decision === "below_threshold"
      ? "below threshold"
      : decision;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        color
      )}
    >
      {label}
    </span>
  );
}

function ScopeBadge({ scope }: { scope: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-0.5 text-xs font-medium">
      {SCOPE_LABELS[scope] ?? scope}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Collapsible section
// ---------------------------------------------------------------------------

function CollapsibleSection({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-foreground bg-muted/50 hover:bg-muted transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        {title}
        <span className="text-muted-foreground">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="p-3 space-y-2">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trace detail panel
// ---------------------------------------------------------------------------

function TraceDetailPanel({ traceId }: { traceId: string }) {
  const [trace, setTrace] = useState<RagTraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);

    apiFetch(`/api/v1/admin/rag-debug/${traceId}`)
      .then(async (res) => {
        if (!mounted) return;
        if (!res.ok) {
          setError(await parseApiError(res));
          return;
        }
        setTrace(await res.json());
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load trace");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [traceId]);

  if (loading) {
    return (
      <p className="text-muted-foreground text-xs py-4 text-center">
        Loading trace…
      </p>
    );
  }

  if (error || !trace) {
    return (
      <p className="text-destructive text-xs py-4 text-center">
        {error ?? "Trace not found"}
      </p>
    );
  }

  const isError = trace.gating_decision === "error";
  const mmrSelectedIds = new Set(
    (trace.mmr_selections ?? []).map((c) => c.chunk_id)
  );

  return (
    <div className="space-y-2 pt-2">
      {/* Query */}
      <CollapsibleSection title="Query">
        <p className="text-sm text-foreground break-words">{trace.query_text}</p>
        <div className="flex gap-2 mt-1">
          <ScopeBadge scope={trace.scope} />
          <span className="text-xs text-muted-foreground">
            {formatTimestamp(trace.created_at)}
          </span>
        </div>
      </CollapsibleSection>

      {isError ? (
        /* Error state */
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="text-sm font-medium text-destructive">Retrieval error</p>
          <p className="text-xs text-muted-foreground mt-1">
            {trace.error_message ?? "Unknown error"}
          </p>
        </div>
      ) : (
        <>
          {/* Vector Search */}
          <CollapsibleSection title={`Vector Search — ${(trace.vector_candidates ?? []).length} candidates`} defaultOpen={false}>
            {(trace.vector_candidates ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">No candidates retrieved.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="text-left pb-1 pr-4">Chunk ID</th>
                    <th className="text-right pb-1">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {(trace.vector_candidates ?? []).map((c) => (
                    <tr
                      key={c.chunk_id}
                      className={cn(
                        "border-b border-border/50",
                        mmrSelectedIds.has(c.chunk_id) ? "font-medium" : "text-muted-foreground"
                      )}
                    >
                      <td className="py-0.5 pr-4 font-mono">
                        {c.chunk_id.slice(0, 8)}…
                      </td>
                      <td className="py-0.5 text-right">{c.score.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CollapsibleSection>

          {/* MMR Selection */}
          <CollapsibleSection title={`MMR Selection — ${(trace.mmr_selections ?? []).length} selected`} defaultOpen={false}>
            {(trace.mmr_selections ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">No chunks survived MMR.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="text-left pb-1 pr-4">Chunk ID</th>
                    <th className="text-right pb-1">Score</th>
                  </tr>
                </thead>
                <tbody>
                  {(trace.mmr_selections ?? []).map((c) => (
                    <tr key={c.chunk_id} className="border-b border-border/50">
                      <td className="py-0.5 pr-4 font-mono">
                        {c.chunk_id.slice(0, 8)}…
                      </td>
                      <td className="py-0.5 text-right">{c.score.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CollapsibleSection>

          {/* Threshold Gate */}
          <CollapsibleSection title="Threshold Gate">
            {(trace.injected_chunks ?? []).length === 0 ? (
              <div className="rounded-md bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 p-2">
                <p className="text-xs text-amber-800 dark:text-amber-300 font-medium">
                  Below threshold — nothing injected.
                </p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                {(trace.injected_chunks ?? []).length} chunk
                {(trace.injected_chunks ?? []).length !== 1 ? "s" : ""} cleared the
                similarity threshold.
              </p>
            )}
          </CollapsibleSection>

          {/* Injected Chunks */}
          <CollapsibleSection
            title={`Injected Chunks — ${(trace.injected_chunks ?? []).length}`}
          >
            {(trace.injected_chunks ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">No chunks injected.</p>
            ) : (
              <div className="space-y-3">
                {(trace.injected_chunks ?? []).map((c, i) => (
                  <div
                    key={c.chunk_id}
                    className="border border-border rounded p-2 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-foreground">
                        {c.document_title ?? "Unknown document"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        score {c.score.toFixed(4)}
                      </span>
                    </div>
                    {c.section_path && (
                      <p className="text-xs text-muted-foreground">{c.section_path}</p>
                    )}
                    <p className="text-xs text-foreground/80 break-words leading-relaxed">
                      {c.text_preview}
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {c.chunk_id.slice(0, 8)}…
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleSection>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AdminRagDebugPage() {
  const [traces, setTraces] = useState<RagTraceSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>("all");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchTraces = useCallback(
    async (cursor?: string, append = false) => {
      try {
        const params = new URLSearchParams({ limit: "50" });
        if (scopeFilter !== "all") params.set("scope", scopeFilter);
        if (cursor) params.set("cursor", cursor);

        const res = await apiFetch(`/api/v1/admin/rag-debug?${params}`);
        if (!res.ok) {
          setError(await parseApiError(res));
          return;
        }
        const data = await res.json();
        setTraces((prev) =>
          append ? [...prev, ...(data.traces ?? [])] : data.traces ?? []
        );
        setNextCursor(data.next_cursor ?? null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load traces");
      } finally {
        setLoaded(true);
        setLoadingMore(false);
      }
    },
    [scopeFilter]
  );

  useEffect(() => {
    setLoaded(false);
    setExpandedId(null);
    fetchTraces();
  }, [fetchTraces]);

  function handleLoadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    fetchTraces(nextCursor, true);
  }

  function toggleExpand(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">RAG Debug</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Retrieval traces from recent queries. Click a row to inspect the
            pipeline steps.
          </p>
        </div>

        {/* Scope filter */}
        <select
          value={scopeFilter}
          onChange={(e) => setScopeFilter(e.target.value as ScopeFilter)}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground"
        >
          <option value="all">All scopes</option>
          <option value="project_kb">Project KB</option>
          <option value="agent_kb">Agent KB</option>
        </select>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 mb-4">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {!loaded ? (
        <p className="text-muted-foreground text-sm">Loading traces…</p>
      ) : traces.length === 0 ? (
        <div className="rounded-md border border-border p-8 text-center">
          <p className="text-muted-foreground text-sm">No traces found.</p>
          <p className="text-muted-foreground text-xs mt-1">
            Traces appear here after queries are made with RAG retrieval enabled.
          </p>
        </div>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border text-muted-foreground text-xs">
                <th className="text-left px-4 py-2 font-medium">Timestamp</th>
                <th className="text-left px-4 py-2 font-medium">Query</th>
                <th className="text-left px-4 py-2 font-medium">Scope</th>
                <th className="text-left px-4 py-2 font-medium">Outcome</th>
                <th className="text-right px-4 py-2 font-medium">Injected</th>
                <th className="text-right px-4 py-2 font-medium">Candidates</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((trace) => (
                <React.Fragment key={trace.id}>
                  <tr
                    className={cn(
                      "border-b border-border cursor-pointer hover:bg-muted/30 transition-colors",
                      expandedId === trace.id && "bg-muted/20"
                    )}
                    onClick={() => toggleExpand(trace.id)}
                  >
                    <td className="px-4 py-2.5 text-muted-foreground text-xs whitespace-nowrap">
                      {formatTimestamp(trace.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-foreground max-w-xs">
                      {truncate(trace.query_text, 80)}
                    </td>
                    <td className="px-4 py-2.5">
                      <ScopeBadge scope={trace.scope} />
                    </td>
                    <td className="px-4 py-2.5">
                      <GatingBadge decision={trace.gating_decision} />
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">
                      {trace.injected_chunk_count}
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">
                      {trace.vector_candidate_count}
                    </td>
                  </tr>

                  {/* Inline expanded detail row */}
                  {expandedId === trace.id && (
                    <tr key={`${trace.id}-detail`} className="border-b border-border bg-muted/10">
                      <td colSpan={6} className="px-6 pb-4">
                        <TraceDetailPanel traceId={trace.id} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>

          {nextCursor && (
            <div className="p-4 text-center border-t border-border">
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              >
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
