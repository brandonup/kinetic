"use client";

/**
 * Admin LLM Models Page — KIN-265
 *
 * Sections:
 *  1. Model list — display_name, model_id, provider, category badge, enabled toggle, edit, delete
 *  2. Inline edit panel — display_name, context_window
 *  3. Delete confirm
 *  4. Add model form (inline) — provider, model_id, display_name, category, context_window
 *
 * Schema ref: docs/db-schema-spec.md §19 (llm_models)
 * API: GET/POST/PATCH/DELETE /api/v1/admin/models
 */

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch, parseApiError } from "@/lib/api";
import type { ModelCategory, ModelConfiguration, ModelProvider } from "@/lib/types/models";
import { cn } from "@/lib/utils";

const PROVIDERS: ModelProvider[] = ["anthropic", "openai", "google", "groq"];
const CATEGORIES: ModelCategory[] = ["generation", "embedding", "reranking"];

const CATEGORY_COLORS: Record<ModelCategory, string> = {
  generation: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  embedding: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
  reranking: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
};

export default function AdminModelsPage() {
  const { toast } = useToast();

  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Add form
  const [adding, setAdding] = useState(false);
  const [addProvider, setAddProvider] = useState<ModelProvider>("anthropic");
  const [addModelId, setAddModelId] = useState("");
  const [addDisplayName, setAddDisplayName] = useState("");
  const [addCategory, setAddCategory] = useState<ModelCategory>("generation");
  const [addContextWindow, setAddContextWindow] = useState("");
  const [savingAdd, setSavingAdd] = useState(false);

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editContextWindow, setEditContextWindow] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  // Delete confirm
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Toggling enabled
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    void loadModels();
  }, []);

  async function loadModels() {
    try {
      const res = await apiFetch("/api/v1/admin/models");
      if (res.ok) {
        const data: { models: ModelConfiguration[] } = await res.json();
        setModels(data.models);
      }
    } catch {
      // Silent fail
    } finally {
      setLoaded(true);
    }
  }

  function resetAddForm() {
    setAdding(false);
    setAddProvider("anthropic");
    setAddModelId("");
    setAddDisplayName("");
    setAddCategory("generation");
    setAddContextWindow("");
  }

  async function addModel() {
    if (!addModelId.trim() || !addDisplayName.trim()) return;
    setSavingAdd(true);
    try {
      const res = await apiFetch("/api/v1/admin/models", {
        method: "POST",
        body: JSON.stringify({
          provider: addProvider,
          model_id: addModelId.trim(),
          display_name: addDisplayName.trim(),
          category: addCategory,
          context_window: addContextWindow ? parseInt(addContextWindow, 10) : null,
        }),
      });
      if (res.ok) {
        const model: ModelConfiguration = await res.json();
        setModels((prev) => [...prev, model].sort((a, b) => a.display_name.localeCompare(b.display_name)));
        resetAddForm();
        toast({ title: "Model added" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to add model", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to add model", variant: "destructive" });
    } finally {
      setSavingAdd(false);
    }
  }

  function startEdit(model: ModelConfiguration) {
    setEditingId(model.id);
    setEditDisplayName(model.display_name);
    setEditContextWindow(model.context_window != null ? String(model.context_window) : "");
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit(model: ModelConfiguration) {
    setSavingEdit(true);
    try {
      const body: Record<string, string | number | null> = {};
      if (editDisplayName.trim() !== model.display_name) body.display_name = editDisplayName.trim();
      const newCtx = editContextWindow ? parseInt(editContextWindow, 10) : null;
      if (newCtx !== model.context_window) body.context_window = newCtx;

      if (Object.keys(body).length === 0) {
        cancelEdit();
        return;
      }

      const res = await apiFetch(`/api/v1/admin/models/${model.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const updated: ModelConfiguration = await res.json();
        setModels((prev) => prev.map((m) => (m.id === model.id ? updated : m)));
        cancelEdit();
        toast({ title: "Model updated" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to update model", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to update model", variant: "destructive" });
    } finally {
      setSavingEdit(false);
    }
  }

  async function toggleEnabled(model: ModelConfiguration) {
    setTogglingId(model.id);
    try {
      const res = await apiFetch(`/api/v1/admin/models/${model.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !model.enabled }),
      });
      if (res.ok) {
        const updated: ModelConfiguration = await res.json();
        setModels((prev) => prev.map((m) => (m.id === model.id ? updated : m)));
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to update model", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to update model", variant: "destructive" });
    } finally {
      setTogglingId(null);
    }
  }

  async function deleteModel(modelId: string) {
    setConfirmingDelete(true);
    try {
      const res = await apiFetch(`/api/v1/admin/models/${modelId}`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        setModels((prev) => prev.filter((m) => m.id !== modelId));
        setDeletingId(null);
        toast({ title: "Model deleted" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to delete model", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to delete model", variant: "destructive" });
    } finally {
      setConfirmingDelete(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">LLM Models</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage the model library available to users.
          </p>
        </div>
        {!adding && loaded && (
          <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
            Add model
          </Button>
        )}
      </div>

      <Separator />

      {/* ── Model list ── */}
      <div className="space-y-3">
        {loaded && models.length === 0 && !adding && (
          <p className="text-sm text-muted-foreground italic">
            No models yet. Click &ldquo;Add model&rdquo; to add one.
          </p>
        )}

        {models.map((model) => {
          const isEditing = editingId === model.id;
          const isDeleting = deletingId === model.id;
          const isToggling = togglingId === model.id;

          if (isDeleting) {
            return (
              <div
                key={model.id}
                className="rounded-md border border-destructive/50 bg-destructive/5 px-4 py-3 space-y-2"
              >
                <p className="text-sm font-medium text-destructive">
                  Delete &ldquo;{model.display_name}&rdquo;?
                </p>
                <p className="text-xs text-muted-foreground">
                  This removes the model from the library. This cannot be undone.
                </p>
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={confirmingDelete}
                    onClick={() => deleteModel(model.id)}
                  >
                    {confirmingDelete ? "Deleting…" : "Delete permanently"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={confirmingDelete}
                    onClick={() => setDeletingId(null)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            );
          }

          if (isEditing) {
            return (
              <div
                key={model.id}
                className="rounded-md border border-border px-4 py-3 space-y-3"
              >
                <h3 className="text-sm font-medium text-foreground">Edit Model</h3>
                <div className="space-y-1.5">
                  <Label htmlFor={`edit-name-${model.id}`}>Display name</Label>
                  <Input
                    id={`edit-name-${model.id}`}
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor={`edit-ctx-${model.id}`}>Context window (tokens)</Label>
                  <Input
                    id={`edit-ctx-${model.id}`}
                    type="number"
                    value={editContextWindow}
                    onChange={(e) => setEditContextWindow(e.target.value)}
                    placeholder="e.g. 200000"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!editDisplayName.trim() || savingEdit}
                    onClick={() => saveEdit(model)}
                  >
                    {savingEdit ? "Saving…" : "Save"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={cancelEdit}>
                    Cancel
                  </Button>
                </div>
              </div>
            );
          }

          return (
            <div
              key={model.id}
              className={cn(
                "flex items-start gap-3 rounded-md border px-4 py-3",
                model.enabled ? "border-border" : "border-border opacity-60"
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium text-foreground">{model.display_name}</p>
                  <span
                    className={cn(
                      "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium",
                      CATEGORY_COLORS[model.category]
                    )}
                  >
                    {model.category}
                  </span>
                  {!model.enabled && (
                    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                      disabled
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {model.provider} &middot; <span className="font-mono">{model.model_id}</span>
                  {model.context_window != null && (
                    <> &middot; {model.context_window.toLocaleString()} ctx</>
                  )}
                </p>
              </div>
              <div className="flex gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={isToggling}
                  onClick={() => toggleEnabled(model)}
                >
                  {model.enabled ? "Disable" : "Enable"}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => startEdit(model)}>
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDeletingId(model.id)}
                >
                  Delete
                </Button>
              </div>
            </div>
          );
        })}

        {/* ── Add form ── */}
        {adding && (
          <div className="rounded-md border border-border px-4 py-3 space-y-3">
            <h3 className="text-sm font-medium text-foreground">Add Model</h3>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="add-provider">Provider</Label>
                <select
                  id="add-provider"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                  value={addProvider}
                  onChange={(e) => setAddProvider(e.target.value as ModelProvider)}
                >
                  {PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="add-category">Category</Label>
                <select
                  id="add-category"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                  value={addCategory}
                  onChange={(e) => setAddCategory(e.target.value as ModelCategory)}
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="add-model-id">Model ID</Label>
              <Input
                id="add-model-id"
                value={addModelId}
                onChange={(e) => setAddModelId(e.target.value)}
                placeholder="e.g. claude-sonnet-4-6"
                autoFocus
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="add-display-name">Display name</Label>
              <Input
                id="add-display-name"
                value={addDisplayName}
                onChange={(e) => setAddDisplayName(e.target.value)}
                placeholder="e.g. Claude Sonnet 4.6"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="add-context-window">
                Context window (tokens){" "}
                <span className="text-muted-foreground font-normal">optional</span>
              </Label>
              <Input
                id="add-context-window"
                type="number"
                value={addContextWindow}
                onChange={(e) => setAddContextWindow(e.target.value)}
                placeholder="e.g. 200000"
              />
            </div>

            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!addModelId.trim() || !addDisplayName.trim() || savingAdd}
                onClick={addModel}
              >
                {savingAdd ? "Adding…" : "Add model"}
              </Button>
              <Button size="sm" variant="ghost" onClick={resetAddForm}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
