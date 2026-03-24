"use client";

/**
 * useDocumentStatus — polls document ingestion status while processing.
 *
 * Polls GET /api/v1/documents/{id} every `intervalMs` (default 3s) while
 * the document is in a processing state. Stops polling once completed or failed.
 *
 * KIN-346 · PRD §7
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { DocumentStatus, DocumentStatusResponse } from "@/lib/types/models";

const PROCESSING_STATUSES: Set<DocumentStatus> = new Set([
  "pending",
  "extracting",
  "chunking",
  "embedding",
]);

interface UseDocumentStatusOptions {
  /** Polling interval in ms. Default 3000. */
  intervalMs?: number;
  /** Whether polling is enabled. Default true. */
  enabled?: boolean;
}

interface UseDocumentStatusResult {
  data: DocumentStatusResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useDocumentStatus(
  documentId: string | null,
  options: UseDocumentStatusOptions = {},
): UseDocumentStatusResult {
  const { intervalMs = 3000, enabled = true } = options;

  const [data, setData] = useState<DocumentStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!documentId) return;
    try {
      setLoading(true);
      const res = await apiFetch(`/api/v1/documents/${documentId}`);
      if (!res.ok) {
        const text = await res.text();
        console.error("[useDocumentStatus] HTTP %d: %s", res.status, text);
        setError(text || "Failed to fetch document status");
        return;
      }
      const body: DocumentStatusResponse = await res.json();
      setData(body);
      setError(null);
    } catch (err) {
      console.error("[useDocumentStatus] fetch failed:", err);
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  // Start/stop polling based on status
  useEffect(() => {
    if (!enabled || !documentId) return;

    // Initial fetch
    void fetchStatus();

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [documentId, enabled, fetchStatus]);

  // Manage polling interval based on current data status
  useEffect(() => {
    if (!enabled || !documentId) return;

    const shouldPoll = data === null || PROCESSING_STATUSES.has(data.status);

    if (shouldPoll) {
      if (!intervalRef.current) {
        intervalRef.current = setInterval(() => void fetchStatus(), intervalMs);
      }
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [data, enabled, documentId, fetchStatus, intervalMs]);

  return { data, loading, error, refetch: fetchStatus };
}
