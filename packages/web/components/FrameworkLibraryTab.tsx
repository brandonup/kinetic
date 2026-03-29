"use client";

/**
 * FrameworkLibraryTab — KIN-319 / KIN-320
 *
 * Displays the framework library for an agent definition.
 * Supports search, category filter, table, delete with confirmation,
 * inline edit/add form, and JSON bulk upload.
 *
 * API:
 *   GET    /api/v1/agents/:agentId/frameworks
 *   POST   /api/v1/agents/:agentId/frameworks
 *   PATCH  /api/v1/agents/:agentId/frameworks/:frameworkId
 *   DELETE /api/v1/agents/:agentId/frameworks/:frameworkId
 *   DELETE /api/v1/agents/:agentId/frameworks          (delete all)
 *   POST   /api/v1/agents/:agentId/frameworks/upload
 */

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch } from "@/lib/api";
import type {
  CreateFrameworkRequest,
  Framework,
  FrameworkListResponse,
  FrameworkOverrides,
  UpdateFrameworkRequest,
  UploadFrameworksResponse,
} from "@/lib/types/models";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// FrameworkForm — inline component (not exported)
// ---------------------------------------------------------------------------

interface FrameworkFormProps {
  initial: Framework | null; // null = add mode
  saving: boolean;
  onSave: (body: CreateFrameworkRequest | UpdateFrameworkRequest) => void;
  onCancel: () => void;
}

function FrameworkForm({ initial, saving, onSave, onCancel }: FrameworkFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [whenToApply, setWhenToApply] = useState<string[]>(initial?.when_to_apply ?? [""]);
  const [principles, setPrinciples] = useState<string[]>(initial?.principles ?? [""]);
  const [steps, setSteps] = useState<string[]>(initial?.steps ?? [""]);

  const whenToApplyChanged =
    initial !== null &&
    JSON.stringify(whenToApply) !== JSON.stringify(initial.when_to_apply);

  function handleSubmit() {
    if (initial) {
      // PATCH — only include changed fields
      const body: UpdateFrameworkRequest = {};
      if (name !== initial.name) body.name = name;
      if (category !== (initial.category ?? "")) body.category = category || undefined;
      if (description !== (initial.description ?? "")) body.description = description || undefined;
      if (JSON.stringify(whenToApply.filter(Boolean)) !== JSON.stringify(initial.when_to_apply))
        body.when_to_apply = whenToApply.filter(Boolean);
      if (JSON.stringify(principles.filter(Boolean)) !== JSON.stringify(initial.principles))
        body.principles = principles.filter(Boolean);
      if (JSON.stringify(steps.filter(Boolean)) !== JSON.stringify(initial.steps))
        body.steps = steps.filter(Boolean);
      onSave(body);
    } else {
      // POST — full body
      const body: CreateFrameworkRequest = {
        name,
        when_to_apply: whenToApply.filter(Boolean),
        principles: principles.filter(Boolean),
        category: category || undefined,
        description: description || undefined,
        steps: steps.filter(Boolean).length > 0 ? steps.filter(Boolean) : undefined,
      };
      onSave(body);
    }
  }

  return (
    <div className="space-y-4">
      {/* Name */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Name *</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" placeholder="e.g., Coordination Tax Diagnostic" />
      </div>

      {/* Category */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Category</label>
        <Input value={category} onChange={(e) => setCategory(e.target.value)} className="mt-1" placeholder="e.g., strategy, org-design" />
      </div>

      {/* Description */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Brief description of what this framework does…"
          rows={3}
          className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
        />
      </div>

      {/* When to apply */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">When to apply *</label>
        <div className="mt-1 space-y-1">
          {whenToApply.map((phrase, i) => (
            <div key={i} className="flex gap-1">
              <Input
                value={phrase}
                onChange={(e) => {
                  const next = [...whenToApply];
                  next[i] = e.target.value;
                  setWhenToApply(next);
                }}
                placeholder="When facing a complex problem…"
                className="h-8 text-sm"
              />
              {whenToApply.length > 1 && (
                <Button
                  variant="ghost" size="sm" className="h-8 px-2 text-destructive hover:text-destructive"
                  onClick={() => setWhenToApply(whenToApply.filter((_, j) => j !== i))}
                >×</Button>
              )}
            </div>
          ))}
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setWhenToApply([...whenToApply, ""])}>
            + Add trigger
          </Button>
        </div>
        {whenToApplyChanged && (
          <p className="text-xs text-muted-foreground mt-1">Trigger embeddings will be updated in the background.</p>
        )}
      </div>

      {/* Principles — shown in both add and edit modes (KIN-371) */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Principles {!initial && "*"}</label>
        <div className="mt-1 space-y-1">
          {principles.map((p, i) => (
            <div key={i} className="flex gap-1">
              <Input
                value={p}
                onChange={(e) => {
                  const next = [...principles];
                  next[i] = e.target.value;
                  setPrinciples(next);
                }}
                placeholder="Core idea or rule…"
                className="h-8 text-sm"
              />
              {principles.length > 1 && (
                <Button
                  variant="ghost" size="sm" className="h-8 px-2 text-destructive hover:text-destructive"
                  onClick={() => setPrinciples(principles.filter((_, j) => j !== i))}
                >×</Button>
              )}
            </div>
          ))}
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setPrinciples([...principles, ""])}>
            + Add principle
          </Button>
        </div>
      </div>

      {/* Steps */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Steps</label>
        <div className="mt-1 space-y-1">
          {steps.map((s, i) => (
            <div key={i} className="flex gap-1">
              <span className="flex items-center text-xs text-muted-foreground w-5 shrink-0 justify-center">{i + 1}.</span>
              <Input
                value={s}
                onChange={(e) => {
                  const next = [...steps];
                  next[i] = e.target.value;
                  setSteps(next);
                }}
                placeholder="Step description…"
                className="h-8 text-sm"
              />
              {steps.length > 1 && (
                <Button
                  variant="ghost" size="sm" className="h-8 px-2 text-destructive hover:text-destructive"
                  onClick={() => setSteps(steps.filter((_, j) => j !== i))}
                >×</Button>
              )}
            </div>
          ))}
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setSteps([...steps, ""])}>
            + Add step
          </Button>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>Cancel</Button>
        <Button size="sm" onClick={handleSubmit} disabled={saving || !name.trim()}>
          {saving ? "Saving…" : initial ? "Save changes" : "Add framework"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FrameworkLibraryTab
// ---------------------------------------------------------------------------

interface FrameworkLibraryTabProps {
  agentId: string;
  isOwner: boolean;
}

export function FrameworkLibraryTab({ agentId, isOwner }: FrameworkLibraryTabProps) {
  const { toast } = useToast();

  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

  // Delete confirm state — no alert-dialog component available; using inline modal
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Ref for restoring optimistically removed row on error
  const deletedRowRef = useRef<Framework | null>(null);

  // Edit/add form
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<Framework | null>(null); // null = add mode
  const [formSaving, setFormSaving] = useState(false);

  // Delete all
  const [showDeleteAllConfirm, setShowDeleteAllConfirm] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);

  // Upload
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadSummary, setUploadSummary] = useState<UploadFrameworksResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Pin/exclude overrides (KIN-372)
  const [overrides, setOverrides] = useState<FrameworkOverrides>({ pinned: [], excluded: [] });
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    void loadFrameworks();
    void loadOverrides();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  async function loadFrameworks() {
    setLoading(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${agentId}/frameworks`);
      if (res.ok) {
        const data: FrameworkListResponse = await res.json();
        setFrameworks(data.frameworks);
      }
    } catch {
      // Silent — empty state rendered
    } finally {
      setLoading(false);
    }
  }

  async function loadOverrides() {
    try {
      const res = await apiFetch(`/api/v1/agents/${agentId}/instance`);
      if (res.ok) {
        const data = await res.json();
        setOverrides(data.framework_overrides ?? { pinned: [], excluded: [] });
      }
    } catch {
      // Silent — defaults to empty overrides
    }
  }

  async function handleToggleOverride(
    frameworkId: string,
    action: "pin" | "exclude" | "clear",
  ) {
    setTogglingId(frameworkId);
    const prev = { ...overrides };
    // Compute new state
    let pinned = overrides.pinned.filter((id) => id !== frameworkId);
    let excluded = overrides.excluded.filter((id) => id !== frameworkId);
    if (action === "pin") pinned = [...pinned, frameworkId];
    if (action === "exclude") excluded = [...excluded, frameworkId];

    const next: FrameworkOverrides = { pinned, excluded };
    // Optimistic update
    setOverrides(next);
    try {
      const res = await apiFetch(`/api/v1/agents/${agentId}/instance`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ framework_overrides: next }),
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data = await res.json();
      setOverrides(data.framework_overrides ?? next);
    } catch {
      // Rollback
      setOverrides(prev);
      toast({ title: "Failed to update override", variant: "destructive" });
    } finally {
      setTogglingId(null);
    }
  }

  // Computed values
  const distinctCategories = [
    ...new Set(frameworks.map((f) => f.category).filter((c): c is string => c !== null)),
  ];

  const filteredFrameworks = frameworks.filter((f) => {
    const matchesSearch = search.trim() === "" || f.name.toLowerCase().includes(search.toLowerCase().trim());
    const matchesCategory = categoryFilter === null || f.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  async function handleDeleteConfirm() {
    if (!confirmDeleteId) return;

    const target = frameworks.find((f) => f.id === confirmDeleteId);
    if (!target) return;

    // Optimistic remove
    deletedRowRef.current = target;
    setFrameworks((prev) => prev.filter((f) => f.id !== confirmDeleteId));
    setDeletingId(confirmDeleteId);
    setConfirmDeleteId(null);

    try {
      const res = await apiFetch(`/api/v1/agents/${agentId}/frameworks/${target.id}`, {
        method: "DELETE",
      });

      if (res.ok || res.status === 204) {
        toast({ title: "Framework deleted" });
      } else {
        throw new Error(`Unexpected status ${res.status}`);
      }
    } catch {
      toast({ title: "Failed to delete framework", variant: "destructive" });
      // Restore optimistically removed row
      if (deletedRowRef.current) {
        setFrameworks((prev) => [...prev, deletedRowRef.current!]);
      }
    } finally {
      setDeletingId(null);
      deletedRowRef.current = null;
    }
  }

  async function handleDeleteAll() {
    setDeletingAll(true);
    setShowDeleteAllConfirm(false);
    const prevFrameworks = [...frameworks];
    // Optimistic clear
    setFrameworks([]);
    try {
      const res = await apiFetch(`/api/v1/agents/${agentId}/frameworks`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data = await res.json();
      toast({ title: `Deleted ${data.deleted_count} framework${data.deleted_count === 1 ? "" : "s"}` });
    } catch {
      // Restore on failure
      setFrameworks(prevFrameworks);
      toast({ title: "Failed to delete frameworks", variant: "destructive" });
    } finally {
      setDeletingAll(false);
    }
  }

  async function handleFormSave(body: CreateFrameworkRequest | UpdateFrameworkRequest) {
    // Guard: skip spurious PATCH when no fields changed
    if (editTarget && Object.keys(body).length === 0) {
      setShowForm(false);
      setEditTarget(null);
      return;
    }
    setFormSaving(true);
    try {
      const url = editTarget
        ? `/api/v1/agents/${agentId}/frameworks/${editTarget.id}`
        : `/api/v1/agents/${agentId}/frameworks`;
      const res = await apiFetch(url, {
        method: editTarget ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const saved: Framework = await res.json();
      if (editTarget) {
        setFrameworks((prev) => prev.map((f) => (f.id === saved.id ? saved : f)));
      } else {
        setFrameworks((prev) => [...prev, saved]);
      }
      toast({ title: editTarget ? "Framework saved" : "Framework added" });
      setShowForm(false);
      setEditTarget(null);
    } catch {
      toast({ title: "Failed to save framework", variant: "destructive" });
    } finally {
      setFormSaving(false);
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadLoading(true);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as unknown;
      const frameworks = Array.isArray(parsed)
        ? parsed
        : (parsed as { frameworks: unknown[] }).frameworks;
      const res = await apiFetch(`/api/v1/agents/${agentId}/frameworks/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frameworks }),
      });
      if (res.ok) {
        const summary: UploadFrameworksResponse = await res.json();
        setUploadSummary(summary);
        loadFrameworks().catch(() => {
          toast({ title: "Framework list failed to refresh", variant: "destructive" });
        });
      } else {
        toast({ title: "Upload failed", variant: "destructive" });
      }
    } catch {
      toast({ title: "Invalid JSON file", variant: "destructive" });
    } finally {
      setUploadLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const confirmTarget = confirmDeleteId
    ? frameworks.find((f) => f.id === confirmDeleteId) ?? null
    : null;

  return (
    <div className="space-y-4">
      {/* Edit/add form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-lg w-full mx-4 overflow-y-auto max-h-[90vh]">
            <h2 className="text-base font-semibold mb-4">
              {editTarget ? `Edit "${editTarget.name}"` : "Add framework"}
            </h2>
            <FrameworkForm
              initial={editTarget}
              saving={formSaving}
              onSave={(body) => void handleFormSave(body)}
              onCancel={() => { setShowForm(false); setEditTarget(null); }}
            />
          </div>
        </div>
      )}

      {/* Upload summary modal */}
      {uploadSummary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm w-full mx-4 space-y-3">
            <h2 className="text-base font-semibold">Import Summary</h2>
            <ul className="text-sm space-y-1">
              <li>{uploadSummary.added} frameworks added</li>
              <li>{uploadSummary.updated} frameworks updated</li>
              <li>{uploadSummary.retained} frameworks retained</li>
              {uploadSummary.failed.length > 0 && (
                <li className="text-destructive">{uploadSummary.failed.length} failed</li>
              )}
            </ul>
            {uploadSummary.failed.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Errors</p>
                {uploadSummary.failed.map((f, i) => (
                  <p key={i} className="text-xs text-destructive">• {f.framework_id}: {f.error}</p>
                ))}
              </div>
            )}
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setUploadSummary(null)}>OK</Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm delete modal — inline (no alert-dialog component available) */}
      {confirmDeleteId && confirmTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm w-full mx-4 space-y-4">
            <h2 className="text-base font-semibold">Delete framework?</h2>
            <p className="text-sm text-muted-foreground">
              Delete &ldquo;{confirmTarget.name}&rdquo;? This will remove the framework and its
              trigger vectors. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDeleteId(null)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void handleDeleteConfirm()}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm delete-all modal */}
      {showDeleteAllConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm w-full mx-4 space-y-4">
            <h2 className="text-base font-semibold">Delete all frameworks?</h2>
            <p className="text-sm text-muted-foreground">
              This will permanently delete all {frameworks.length} framework{frameworks.length === 1 ? "" : "s"} and
              their trigger vectors. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowDeleteAllConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void handleDeleteAll()}
              >
                Delete all
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search frameworks…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 text-sm max-w-xs"
        />

        {isOwner && (
          <>
            <Button variant="outline" size="sm" onClick={() => { setEditTarget(null); setShowForm(true); }}>
              Add framework
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={uploadLoading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadLoading ? "Validating…" : "Upload JSON"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => void handleUpload(e)}
            />
            {frameworks.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                disabled={deletingAll}
                onClick={() => setShowDeleteAllConfirm(true)}
              >
                {deletingAll ? "Deleting..." : "Delete all"}
              </Button>
            )}
          </>
        )}

        {distinctCategories.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <button
              onClick={() => setCategoryFilter(null)}
              className={cn(
                "text-xs rounded px-2 py-1 border transition-colors",
                categoryFilter === null
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted text-muted-foreground border-transparent hover:border-border"
              )}
            >
              All
            </button>
            {distinctCategories.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat === categoryFilter ? null : cat)}
                className={cn(
                  "text-xs rounded px-2 py-1 border transition-colors",
                  categoryFilter === cat
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-transparent hover:border-border"
                )}
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <p className="text-xs text-muted-foreground py-2">Loading frameworks…</p>
      )}

      {/* Empty state */}
      {!loading && frameworks.length === 0 && (
        <div className="space-y-3 py-6 text-center">
          <p className="text-sm text-muted-foreground">
            No frameworks yet. Upload a JSON file or add one manually.
          </p>
          {isOwner && (
            <div className="flex justify-center gap-2">
              <Button variant="outline" size="sm" disabled={uploadLoading} onClick={() => fileInputRef.current?.click()}>
                {uploadLoading ? "Validating…" : "Upload JSON"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setEditTarget(null); setShowForm(true); }}>
                Add manually
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Table */}
      {!loading && frameworks.length > 0 && (
        <div className="overflow-x-auto rounded border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">Name</th>
                <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">Category</th>
                <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">When to apply</th>
                <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">Origin</th>
                {isOwner && (
                  <th className="text-left px-3 py-2 font-medium text-xs text-muted-foreground">Actions</th>
                )}
              </tr>
            </thead>
            <tbody>
              {filteredFrameworks.length === 0 ? (
                <tr>
                  <td
                    colSpan={isOwner ? 5 : 4}
                    className="px-3 py-4 text-center text-xs text-muted-foreground"
                  >
                    No frameworks match your filter.
                  </td>
                </tr>
              ) : (
                filteredFrameworks.map((f) => {
                  const isPinned = overrides.pinned.includes(f.framework_id);
                  const isExcluded = overrides.excluded.includes(f.framework_id);
                  return (
                  <tr
                    key={f.id}
                    className={cn(
                      "border-b last:border-0 transition-colors hover:bg-muted/20",
                      deletingId === f.id && "opacity-40 pointer-events-none",
                      isExcluded && "opacity-50"
                    )}
                  >
                    <td className="px-3 py-2 font-medium">
                      <span className={cn(isExcluded && "line-through text-muted-foreground")}>
                        {f.name}
                      </span>
                      {isPinned && (
                        <span className="ml-1.5 inline-flex items-center text-xs rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 px-1.5 py-0.5 font-medium">
                          Pinned
                        </span>
                      )}
                      {isExcluded && (
                        <span className="ml-1.5 inline-flex items-center text-xs rounded bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 px-1.5 py-0.5 font-medium">
                          Excluded
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {f.category ? (
                        <span className="text-xs rounded bg-muted px-1.5 py-0.5">
                          {f.category}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {f.when_to_apply.length}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={cn(
                          "text-xs rounded px-1.5 py-0.5",
                          f.origin === "extracted"
                            ? "bg-muted text-muted-foreground"
                            : "bg-secondary text-secondary-foreground"
                        )}
                      >
                        {f.origin}
                      </span>
                    </td>
                    {isOwner && (
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className={cn(
                              "h-6 px-2 text-xs",
                              isPinned
                                ? "text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20"
                                : "hover:bg-muted"
                            )}
                            onClick={() => void handleToggleOverride(f.framework_id, isPinned ? "clear" : "pin")}
                            disabled={togglingId === f.framework_id || deletingId === f.id}
                            title={isPinned ? "Unpin framework" : "Pin framework (always inject)"}
                          >
                            {isPinned ? "Unpin" : "Pin"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className={cn(
                              "h-6 px-2 text-xs",
                              isExcluded
                                ? "text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                                : "hover:bg-muted"
                            )}
                            onClick={() => void handleToggleOverride(f.framework_id, isExcluded ? "clear" : "exclude")}
                            disabled={togglingId === f.framework_id || deletingId === f.id}
                            title={isExcluded ? "Include framework" : "Exclude framework (remove from pool)"}
                          >
                            {isExcluded ? "Include" : "Exclude"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs hover:bg-muted"
                            onClick={() => { setEditTarget(f); setShowForm(true); }}
                            disabled={deletingId === f.id}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
                            onClick={() => setConfirmDeleteId(f.id)}
                            disabled={deletingId === f.id}
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
