"use client";

/**
 * ActiveMemoryPanel — KIN-309
 *
 * Displays active memory entries for a project scope with inline CRUD.
 * Calls: GET/POST/PATCH/DELETE /api/v1/active-memory
 *
 * Spec: docs/specs/active-memory-spec.md §Part 5 (UI)
 */

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { ActiveMemoryEntry, ActiveMemoryUsage } from "@/lib/types/models";
import { cn } from "@/lib/utils";

interface ActiveMemoryPanelProps {
  projectId: string;
  capTokens?: number;
}

const PROJECT_CAP = 1000;
const CHAR_SOFT_WARN = 400;
const TOKEN_RED_PCT = 0.9;

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export function ActiveMemoryPanel({ projectId, capTokens = PROJECT_CAP }: ActiveMemoryPanelProps) {
  const [entries, setEntries] = useState<ActiveMemoryEntry[]>([]);
  const [usage, setUsage] = useState<ActiveMemoryUsage>({ current_tokens: 0, cap_tokens: capTokens });
  const [loading, setLoading] = useState(true);

  // Inline edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  // Add entry state
  const [addContent, setAddContent] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [addingEntry, setAddingEntry] = useState(false);

  // Delete state
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/v1/active-memory?project_id=${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setEntries(data.entries ?? []);
        setUsage(data.token_usage ?? { current_tokens: 0, cap_tokens: capTokens });
      }
    } catch {
      // silent — user sees empty state
    } finally {
      setLoading(false);
    }
  }, [projectId, capTokens]);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(entry: ActiveMemoryEntry) {
    setEditingId(entry.id);
    setEditContent(entry.content);
    setEditError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditContent("");
    setEditError(null);
  }

  async function saveEdit(entryId: string) {
    if (!editContent.trim()) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      const res = await apiFetch(`/api/v1/active-memory/${entryId}`, {
        method: "PATCH",
        body: JSON.stringify({ content: editContent.trim() }),
      });
      if (res.ok) {
        const updated: ActiveMemoryEntry = await res.json();
        setEntries((prev) => prev.map((e) => (e.id === entryId ? updated : e)));
        // Refresh token usage
        const usageRes = await apiFetch(`/api/v1/active-memory?project_id=${projectId}`);
        if (usageRes.ok) {
          const data = await usageRes.json();
          setUsage(data.token_usage);
        }
        cancelEdit();
      } else if (res.status === 422) {
        const data = await res.json();
        setEditError(
          `Memory is full (${data.current_tokens ?? "?"}/${data.cap_tokens ?? capTokens} tokens). Remove an entry before saving this one.`
        );
      } else {
        setEditError("Failed to save. Try again.");
      }
    } catch {
      setEditError("Failed to save. Try again.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteEntry(entryId: string) {
    setDeletingId(entryId);
    try {
      const res = await apiFetch(`/api/v1/active-memory/${entryId}`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        // Capture content before state update for accurate interim estimate
        const deletedContent = entries.find((e) => e.id === entryId)?.content ?? "";
        setEntries((prev) => prev.filter((e) => e.id !== entryId));
        setUsage((prev) => ({
          ...prev,
          current_tokens: Math.max(0, prev.current_tokens - estimateTokens(deletedContent)),
        }));
        // Re-fetch for accurate token count
        const usageRes = await apiFetch(`/api/v1/active-memory?project_id=${projectId}`);
        if (usageRes.ok) {
          const data = await usageRes.json();
          setUsage(data.token_usage);
        }
      }
    } catch {
      // silent
    } finally {
      setDeletingId(null);
    }
  }

  async function addEntry() {
    if (!addContent.trim()) return;
    setAddingEntry(true);
    setAddError(null);
    try {
      const res = await apiFetch("/api/v1/active-memory", {
        method: "POST",
        body: JSON.stringify({
          content: addContent.trim(),
          project_id: projectId,
          source_conversation_id: null,
        }),
      });
      if (res.ok) {
        const created: ActiveMemoryEntry = await res.json();
        setEntries((prev) => [created, ...prev]);
        setAddContent("");
        // Refresh token usage
        const usageRes = await apiFetch(`/api/v1/active-memory?project_id=${projectId}`);
        if (usageRes.ok) {
          const data = await usageRes.json();
          setUsage(data.token_usage);
        }
      } else if (res.status === 422) {
        const data = await res.json();
        setAddError(
          `Memory is full (${data.current_tokens ?? "?"}/${data.cap_tokens ?? capTokens} tokens). Remove an entry before adding more.`
        );
      } else {
        setAddError("Failed to add entry. Try again.");
      }
    } catch {
      setAddError("Failed to add entry. Try again.");
    } finally {
      setAddingEntry(false);
    }
  }

  const usagePct = usage.cap_tokens > 0 ? usage.current_tokens / usage.cap_tokens : 0;
  const barColor = usagePct >= TOKEN_RED_PCT ? "bg-destructive" : "bg-primary";

  if (loading) {
    return <p className="text-xs text-muted-foreground py-2">Loading memory…</p>;
  }

  return (
    <div className="space-y-3">
      {/* Token usage bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground">Token usage</span>
          <span
            className={cn(
              "text-xs tabular-nums",
              usagePct >= TOKEN_RED_PCT ? "text-destructive font-medium" : "text-muted-foreground/60"
            )}
          >
            {usage.current_tokens} / {usage.cap_tokens}
          </span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", barColor)}
            style={{ width: `${Math.min(usagePct * 100, 100)}%` }}
          />
        </div>
        {usagePct >= TOKEN_RED_PCT && (
          <p className="text-xs text-destructive">
            Memory is almost full — remove old entries to make room.
          </p>
        )}
      </div>

      {/* Entry list */}
      <div className="space-y-2">
        {entries.length === 0 && (
          <p className="text-xs text-muted-foreground italic">
            No memory entries yet. Add one below.
          </p>
        )}

        {entries.map((entry) => {
          const isEditing = editingId === entry.id;
          const isDeleting = deletingId === entry.id;

          return (
            <div
              key={entry.id}
              className="rounded-md border border-border bg-muted/30 px-3 py-2 space-y-1.5"
            >
              {isEditing ? (
                <>
                  <Textarea
                    value={editContent}
                    onChange={(e) => {
                      setEditContent(e.target.value);
                      setEditError(null);
                    }}
                    rows={3}
                    autoFocus
                    className="text-sm"
                  />
                  {editContent.length > CHAR_SOFT_WARN && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      Keep entries short for best injection quality.
                    </p>
                  )}
                  {editError && (
                    <p className="text-xs text-destructive">{editError}</p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={!editContent.trim() || savingEdit}
                      onClick={() => saveEdit(entry.id)}
                    >
                      {savingEdit ? "Saving…" : "Save"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={cancelEdit}>
                      Cancel
                    </Button>
                  </div>
                </>
              ) : (
                <div className="flex items-start gap-2">
                  <button
                    className="flex-1 text-left text-sm text-foreground hover:text-primary transition-colors"
                    onClick={() => startEdit(entry)}
                    title="Click to edit"
                  >
                    {entry.content}
                  </button>
                  <button
                    className="shrink-0 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                    disabled={isDeleting}
                    onClick={() => deleteEntry(entry.id)}
                    aria-label="Delete memory entry"
                    title="Delete"
                  >
                    {isDeleting ? (
                      <span className="text-xs">…</span>
                    ) : (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                        <path d="M10 11v6M14 11v6" />
                        <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                      </svg>
                    )}
                  </button>
                </div>
              )}
              {!isEditing && (
                <p className="text-xs text-muted-foreground/60">
                  {new Date(entry.created_at).toLocaleDateString()}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Add entry */}
      <div className="space-y-1.5">
        <Textarea
          value={addContent}
          onChange={(e) => {
            setAddContent(e.target.value);
            setAddError(null);
          }}
          placeholder="Add a memory entry…"
          rows={2}
          className="text-sm"
        />
        {addContent.length > CHAR_SOFT_WARN && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Keep entries short for best injection quality.
          </p>
        )}
        {addError && <p className="text-xs text-destructive">{addError}</p>}
        <Button
          size="sm"
          variant="outline"
          disabled={!addContent.trim() || addingEntry}
          onClick={addEntry}
        >
          {addingEntry ? "Adding…" : "Add entry"}
        </Button>
      </div>
    </div>
  );
}
