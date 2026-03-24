"use client";

/**
 * CitationPanel — expandable source references for RAG-augmented AI responses.
 *
 * Shows document title, chunk snippet, and similarity score for each injected chunk.
 * Collapsed by default; user can expand to see sources.
 *
 * KIN-337 · PRD §7
 */

import { useState } from "react";

import { cn } from "@/lib/utils";

/** Maps to retrieval_debug_logs.injected_chunks + document join. */
export interface Citation {
  chunk_id: string;
  document_title: string | null;
  text_preview: string;
  score: number;
}

interface CitationPanelProps {
  citations: Citation[];
}

export function CitationPanel({ citations }: CitationPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={expanded}
        aria-label={`${citations.length} source${citations.length !== 1 ? "s" : ""}`}
      >
        <svg
          className={cn("h-3 w-3 transition-transform", expanded && "rotate-90")}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span>
          {citations.length} source{citations.length !== 1 ? "s" : ""}
        </span>
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-1.5 pl-4" role="list" aria-label="Source citations">
          {citations.map((cite) => (
            <div
              key={cite.chunk_id}
              className="rounded border px-3 py-2 text-xs space-y-1"
              role="listitem"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium truncate">{cite.document_title ?? "Unknown document"}</span>
                <span className="shrink-0 text-muted-foreground">
                  {(cite.score * 100).toFixed(0)}% match
                </span>
              </div>
              <p className="text-muted-foreground line-clamp-2">{cite.text_preview}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
