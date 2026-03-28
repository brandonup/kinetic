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

const ACTIVE_INGESTION_STATUSES = new Set(["extracting", "chunking", "embedding"]);

interface DocumentRowProps {
  documentId: string;
  title: string;
  fileType?: string;
  initialStatus?: DocumentStatus;
  initialTags?: string[];
  onDeleted?: (documentId: string) => void;
}

export function DocumentRow({
  documentId,
  title,
  fileType,
  initialStatus,
  initialTags = [],
  onDeleted,
}: DocumentRowProps) {
  const { data, refetch } = useDocumentStatus(documentId, {
    enabled: Boolean(documentId),
  });

  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const status = data?.status ?? initialStatus ?? "pending";
  const errorStage = data?.error_stage ?? null;
  const errorMessage = data?.error_message ?? null;
  const isRetryable = data?.is_retryable ?? true;

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

  // Delete state (KIN-379)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const isActiveIngestion = ACTIVE_INGESTION_STATUSES.has(status);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      const res = await apiFetch(`/api/v1/documents/${documentId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const msg = await parseApiError(res);
        setDeleteError(msg);
        return;
      }
      onDeleted?.(documentId);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  }, [documentId, onDeleted]);

  const fileLabel = fileType
    ? fileType.split("/").pop()?.toUpperCase() ?? fileType
    : null;

  return (
    <>
      {/* Delete confirmation dialog (KIN-379) */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm w-full mx-4 space-y-4">
            <h2 className="text-base font-semibold">Delete document?</h2>
            <p className="text-sm text-muted-foreground">
              Delete &ldquo;{title}&rdquo;? This will permanently remove the document
              and all its data. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void handleDelete()}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}

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

          {status === "failed" && isRetryable && (
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

          {/* Delete button (KIN-379) */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isActiveIngestion || deleting}
            className="text-xs h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
            aria-label={`Delete ${title}`}
            title={isActiveIngestion ? "Cannot delete while processing" : `Delete ${title}`}
          >
            Delete
          </Button>
        </div>
      </div>

      {retryError && (
        <p className="text-xs text-destructive mt-1" role="alert">
          {retryError}
        </p>
      )}

      {deleteError && (
        <p className="text-xs text-destructive mt-1" role="alert">
          {deleteError}
        </p>
      )}

      {status === "failed" && (errorStage || errorMessage) && !retryError && (
        <p className="text-xs text-muted-foreground mt-1">
          {errorStage && <span className="font-medium">Failed at {errorStage}</span>}
          {errorStage && errorMessage && <span>: </span>}
          {errorMessage && <span>{errorMessage}</span>}
        </p>
      )}

      {status === "completed" && (
        <div className="mt-1.5">
          <TagEditor documentId={documentId} initialTags={stableTagsRef.current} />
        </div>
      )}
    </div>
    </>
  );
}
