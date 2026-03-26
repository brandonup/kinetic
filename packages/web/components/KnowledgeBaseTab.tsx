"use client";

/**
 * KnowledgeBaseTab — document list with folder sidebar, tag filter, and status display.
 *
 * Features: flat folder navigation, tag filter chips, document status + retry.
 *
 * KIN-345 + KIN-346 · PRD §7
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentRow } from "@/components/DocumentRow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch, parseApiError } from "@/lib/api";
import type { DocumentStatus } from "@/lib/types/models";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Upload constants
// ---------------------------------------------------------------------------

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024; // 25 MB

const ACCEPTED_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "text/csv",
  "text/plain",
  "text/markdown",
  "text/x-markdown",
  "application/rtf",
  "application/json",
]);

const ACCEPT_STRING =
  ".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.csv,.txt,.md,.rtf,.json";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface KBDocument {
  id: string;
  title: string;
  file_type: string;
  status: DocumentStatus;
  folder_id: string | null;
  tags: string[];
  file_size_bytes: number;
  created_at: string;
}

interface KBFolder {
  id: string;
  knowledge_base_id: string;
  name: string;
  created_at: string;
}

interface KnowledgeBaseTabProps {
  knowledgeBaseId: string | null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function KnowledgeBaseTab({ knowledgeBaseId }: KnowledgeBaseTabProps) {
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [folders, setFolders] = useState<KBFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [folderError, setFolderError] = useState<string | null>(null);

  // Filters
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);

  // Folder management
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Upload
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Collect all unique tags from documents
  const allTags = Array.from(new Set(documents.flatMap((d) => d.tags))).sort();

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    if (!knowledgeBaseId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (activeFolderId) params.set("folder_id", activeFolderId);
      if (activeTag) params.set("tag", activeTag);
      const qs = params.toString() ? `?${params.toString()}` : "";

      const [docsRes, foldersRes] = await Promise.all([
        apiFetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents${qs}`),
        apiFetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/folders`),
      ]);

      if (!docsRes.ok) {
        const body = await docsRes.text().catch(() => "");
        console.error("[KnowledgeBaseTab] fetchDocuments HTTP %d: %s", docsRes.status, body);
        setError("Failed to load documents");
        return;
      }
      if (!foldersRes.ok) {
        const body = await foldersRes.text().catch(() => "");
        console.error("[KnowledgeBaseTab] fetchFolders HTTP %d: %s", foldersRes.status, body);
        setFolderError("Failed to load folders");
      } else {
        setFolderError(null);
      }

      const docsData = await docsRes.json();
      setDocuments(docsData.documents ?? docsData ?? []);

      if (foldersRes.ok) {
        const foldersData = await foldersRes.json();
        setFolders(foldersData.folders ?? []);
      }
    } catch (err) {
      console.error("[KnowledgeBaseTab] fetchData failed:", err);
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId, activeFolderId, activeTag]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // ---------------------------------------------------------------------------
  // Folder actions
  // ---------------------------------------------------------------------------

  const handleCreateFolder = useCallback(async () => {
    if (!knowledgeBaseId || !newFolderName.trim()) return;
    setCreatingFolder(true);
    try {
      const res = await apiFetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/folders`, {
        method: "POST",
        body: JSON.stringify({ name: newFolderName.trim() }),
      });
      if (res.ok) {
        setNewFolderName("");
        await fetchData();
      } else {
        const msg = await parseApiError(res);
        console.error("[KnowledgeBaseTab] createFolder failed:", msg);
      }
    } catch (err) {
      console.error("[KnowledgeBaseTab] createFolder error:", err);
    } finally {
      setCreatingFolder(false);
    }
  }, [knowledgeBaseId, newFolderName, fetchData]);

  const handleRenameFolder = useCallback(
    async (folderId: string) => {
      if (!knowledgeBaseId || !renameValue.trim()) return;
      try {
        const res = await apiFetch(
          `/api/v1/knowledge-bases/${knowledgeBaseId}/folders/${folderId}`,
          { method: "PATCH", body: JSON.stringify({ name: renameValue.trim() }) },
        );
        if (res.ok) {
          setRenamingFolderId(null);
          setRenameValue("");
          await fetchData();
        }
      } catch (err) {
        console.error("[KnowledgeBaseTab] renameFolder error:", err);
      }
    },
    [knowledgeBaseId, renameValue, fetchData],
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (!knowledgeBaseId) return;
      try {
        const res = await apiFetch(
          `/api/v1/knowledge-bases/${knowledgeBaseId}/folders/${folderId}`,
          { method: "DELETE" },
        );
        if (res.ok) {
          if (activeFolderId === folderId) setActiveFolderId(null);
          await fetchData();
        }
      } catch (err) {
        console.error("[KnowledgeBaseTab] deleteFolder error:", err);
      }
    },
    [knowledgeBaseId, activeFolderId, fetchData],
  );

  // ---------------------------------------------------------------------------
  // Document upload
  // ---------------------------------------------------------------------------

  const handleUploadFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0 || !knowledgeBaseId) return;
      setUploadError(null);

      // Client-side validation
      for (const file of Array.from(files)) {
        if (!ACCEPTED_TYPES.has(file.type)) {
          setUploadError(
            `Unsupported file type: ${file.name}. Accepted: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, RTF.`,
          );
          return;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          setUploadError(
            `File too large: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum is 25 MB.`,
          );
          return;
        }
      }

      setUploading(true);
      try {
        for (const file of Array.from(files)) {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("knowledge_base_id", knowledgeBaseId);

          const res = await apiFetch("/api/v1/documents/upload", {
            method: "POST",
            body: formData,
          });

          if (!res.ok) {
            const msg = await parseApiError(res);
            setUploadError(`Upload failed for ${file.name}: ${msg}`);
            break;
          }
        }
        // Refresh document list after uploads
        await fetchData();
      } catch (err) {
        console.error("[KnowledgeBaseTab] upload error:", err);
        setUploadError("Upload failed. Please try again.");
      } finally {
        setUploading(false);
        // Reset file input so same file can be re-selected
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [knowledgeBaseId, fetchData],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!knowledgeBaseId) {
    return (
      <p className="text-sm text-muted-foreground">
        No Knowledge Base attached to this agent.
      </p>
    );
  }

  if (loading && documents.length === 0 && folders.length === 0) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>;
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="flex gap-4">
      {/* Folder sidebar */}
      <div className="w-48 shrink-0 space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Folders
        </p>

        {folderError && (
          <p className="text-xs text-destructive">{folderError}</p>
        )}

        {/* All documents (no folder filter) */}
        <button
          onClick={() => setActiveFolderId(null)}
          className={cn(
            "w-full text-left text-sm px-2 py-1 rounded transition-colors",
            activeFolderId === null
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          All documents
        </button>

        {folders.map((folder) => (
          <div key={folder.id} className="group flex items-center gap-1">
            {renamingFolderId === folder.id ? (
              <form
                className="flex-1 flex gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleRenameFolder(folder.id);
                }}
              >
                <Input
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  className="h-7 text-xs"
                  autoFocus
                  aria-label={`Rename folder ${folder.name}`}
                />
                <Button type="submit" variant="ghost" size="sm" className="h-7 px-1.5 text-xs">
                  Save
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-1.5 text-xs"
                  onClick={() => setRenamingFolderId(null)}
                >
                  Cancel
                </Button>
              </form>
            ) : (
              <>
                <button
                  onClick={() => setActiveFolderId(folder.id)}
                  className={cn(
                    "flex-1 text-left text-sm px-2 py-1 rounded truncate transition-colors",
                    activeFolderId === folder.id
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted",
                  )}
                  title={folder.name}
                >
                  {folder.name}
                </button>
                <div className="hidden group-hover:flex gap-0.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-xs text-muted-foreground"
                    onClick={() => {
                      setRenamingFolderId(folder.id);
                      setRenameValue(folder.name);
                    }}
                    aria-label={`Rename ${folder.name}`}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-xs text-destructive"
                    onClick={() => void handleDeleteFolder(folder.id)}
                    aria-label={`Delete ${folder.name}`}
                  >
                    Delete
                  </Button>
                </div>
              </>
            )}
          </div>
        ))}

        {/* Create folder */}
        <form
          className="flex gap-1 pt-1"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreateFolder();
          }}
        >
          <Input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="New folder…"
            className="h-7 text-xs"
            aria-label="New folder name"
          />
          <Button
            type="submit"
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs shrink-0"
            disabled={creatingFolder || !newFolderName.trim()}
          >
            Add
          </Button>
        </form>
      </div>

      {/* Main content */}
      <div className="flex-1 space-y-3">
        {/* Upload button */}
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_STRING}
            className="hidden"
            onChange={(e) => void handleUploadFiles(e.target.files)}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {uploading ? "Uploading..." : "Upload documents"}
          </Button>
          {uploadError && (
            <p className="text-xs text-destructive">{uploadError}</p>
          )}
        </div>

        {/* Tag filter chips */}
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <Badge
              variant="secondary"
              className={cn(
                "cursor-pointer text-xs",
                activeTag === null && "bg-accent text-accent-foreground",
              )}
              onClick={() => setActiveTag(null)}
            >
              All tags
            </Badge>
            {allTags.map((tag) => (
              <Badge
                key={tag}
                variant="secondary"
                className={cn(
                  "cursor-pointer text-xs",
                  activeTag === tag && "bg-accent text-accent-foreground",
                )}
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
              >
                {tag}
              </Badge>
            ))}
          </div>
        )}

        {/* Document count */}
        <p className="text-xs text-muted-foreground">
          {documents.length} document{documents.length !== 1 ? "s" : ""}
          {activeFolderId && " in folder"}
          {activeTag && ` tagged "${activeTag}"`}
        </p>

        {/* Document list */}
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {activeFolderId || activeTag
              ? "No documents match the current filter."
              : "No documents uploaded yet."}
          </p>
        ) : (
          <div className="space-y-1.5">
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                documentId={doc.id}
                title={doc.title}
                fileType={doc.file_type}
                initialStatus={doc.status}
                initialTags={doc.tags}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
