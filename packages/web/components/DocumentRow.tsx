"use client";

/**
 * DocumentRow — displays a single document with status badge and retry button.
 *
 * Shows: document title, file type, status badge (with polling), retry button for failed docs.
 * Used inside the KB tab of agent/project pages.
 *
 * KIN-346 · PRD §7
 */

import { useCallback, useRef, useState } from "react";

import { DocumentStatusBadge } from "@/components/DocumentStatusBadge";
import { TagEditor } from "@/components/TagEditor";
import { Button } from "@/components/ui/button";
import { apiFetch, parseApiError } from "@/lib/api";
import { useDocumentStatus } from "@/lib/hooks/useDocumentStatus";
import type { DocumentStatus } from "@/lib/types/models";

interface DocumentRowProps {
  documentId: string;
  title: string;
  fileType?: string;
  initialStatus?: DocumentStatus;
  initialTags?: string[];
}

export function DocumentRow({
  documentId,
  title,
  fileType,
  initialStatus,
  initialTags = [],
}: DocumentRowProps) {
  const { data, refetch } = useDocumentStatus(documentId, {
    enabled: Boolean(documentId),
  });

  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const status = data?.status ?? initialStatus ?? "pending";
  const errorStage = data?.error_stage ?? null;
  const errorMessage = data?.error_message ?? null;

  // Memoize initial tags to avoid re-initializing TagEditor on poll cycles (I5)
  const stableTagsRef = useRef<string[]>(initialTags);
  if (data?.tags && stableTagsRef.current === initialTags) {
    stableTagsRef.current = data.tags;
  }

  const handleRetry = useCallback(async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      const res = await apiFetch(`/api/v1/documents/${documentId}/retry`, {
        method: "POST",
      });
      if (!res.ok) {
        const msg = await parseApiError(res);
        setRetryError(msg);
        return;
      }
      // Re-fetch status after retry initiated
      await refetch();
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetrying(false);
    }
  }, [documentId, refetch]);

  const fileLabel = fileType
    ? fileType.split("/").pop()?.toUpperCase() ?? fileType
    : null;

  return (
    <div className="rounded-md border px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* File type indicator */}
          {fileLabel && (
            <span className="shrink-0 text-[10px] font-mono uppercase text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {fileLabel}
            </span>
          )}

          {/* Title */}
          <span className="text-sm truncate" title={title}>
            {title}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <DocumentStatusBadge
            status={status}
            errorStage={errorStage}
            errorMessage={errorMessage}
          />

          {status === "failed" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRetry}
              disabled={retrying}
              className="text-xs h-7 px-2"
              aria-label={`Retry ingestion for ${title}`}
            >
              {retrying ? "Retrying…" : "Retry"}
            </Button>
          )}
        </div>
      </div>

      {retryError && (
        <p className="text-xs text-destructive mt-1" role="alert">
          {retryError}
        </p>
      )}

      {status === "completed" && (
        <div className="mt-1.5">
          <TagEditor documentId={documentId} initialTags={stableTagsRef.current} />
        </div>
      )}
    </div>
  );
}
