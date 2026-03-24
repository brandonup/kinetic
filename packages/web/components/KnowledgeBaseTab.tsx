"use client";

/**
 * KnowledgeBaseTab — document list with status display for a Knowledge Base.
 *
 * Fetches documents for a given KB, displays each with DocumentRow (status badge + retry).
 * Supports polling for in-progress documents.
 *
 * KIN-346 · PRD §7
 */

import { useCallback, useEffect, useState } from "react";

import { DocumentRow } from "@/components/DocumentRow";
import { apiFetch } from "@/lib/api";
import type { DocumentStatus } from "@/lib/types/models";

interface KBDocument {
  id: string;
  title: string;
  file_type: string;
  status: DocumentStatus;
  file_size_bytes: number;
  created_at: string;
}

interface KnowledgeBaseTabProps {
  knowledgeBaseId: string | null;
}

export function KnowledgeBaseTab({ knowledgeBaseId }: KnowledgeBaseTabProps) {
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    if (!knowledgeBaseId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents`);
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        console.error("[KnowledgeBaseTab] fetchDocuments HTTP %d: %s", res.status, body);
        setError("Failed to load documents");
        return;
      }
      const data = await res.json();
      setDocuments(data.documents ?? data ?? []);
    } catch (err) {
      console.error("[KnowledgeBaseTab] fetchDocuments failed:", err);
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  if (!knowledgeBaseId) {
    return (
      <p className="text-sm text-muted-foreground">
        No Knowledge Base attached to this agent.
      </p>
    );
  }

  if (loading && documents.length === 0) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>;
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  if (documents.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No documents uploaded yet. Upload documents to build the Knowledge Base.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {documents.length} document{documents.length !== 1 ? "s" : ""}
      </p>
      <div className="space-y-1.5">
        {documents.map((doc) => (
          <DocumentRow
            key={doc.id}
            documentId={doc.id}
            title={doc.title}
            fileType={doc.file_type}
            initialStatus={doc.status}
          />
        ))}
      </div>
    </div>
  );
}
