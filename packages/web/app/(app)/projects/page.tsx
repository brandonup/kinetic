"use client";

/**
 * Projects Page — KIN-263
 *
 * Sections:
 *  1. Company filter tabs — filter project list by company
 *  2. Project list — inline settings (name, instructions, company reassignment), delete
 *  3. Create project — inline form (name + instructions, auto-assigned company)
 *
 * Spec ref: docs/specs/kin-257-projects-conversations-spec.md §1.4
 * Schema ref: docs/db-schema-spec.md §4 (projects)
 * API: GET/POST/PATCH/DELETE /api/v1/projects, GET /api/v1/companies
 */

import { useEffect, useState } from "react";

import { ActiveMemoryPanel } from "@/components/ActiveMemoryPanel";
import { ProposalReviewPanel } from "@/components/ProposalReviewPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch, parseApiError } from "@/lib/api";
import type { Company, Project } from "@/lib/types/models";
import { cn } from "@/lib/utils";

const INSTRUCTIONS_ADVISORY_THRESHOLD = 2000;

export default function ProjectsPage() {
  const { toast } = useToast();

  const [companies, setCompanies] = useState<Company[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [filterCompanyId, setFilterCompanyId] = useState<string | null>(null);

  // Create form
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newInstructions, setNewInstructions] = useState("");
  const [savingNew, setSavingNew] = useState(false);

  // Inline settings
  const [settingsId, setSettingsId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editInstructions, setEditInstructions] = useState("");
  const [editCompanyId, setEditCompanyId] = useState("");
  const [pendingCompanyName, setPendingCompanyName] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  // Delete confirm
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Active Memory proposal review (per-project, lazy-loaded when settings open)
  const [pendingProposalCount, setPendingProposalCount] = useState(0);
  const [showProposalReview, setShowProposalReview] = useState(false);

  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    try {
      const [companiesRes, projectsRes] = await Promise.all([
        apiFetch("/api/v1/companies"),
        apiFetch("/api/v1/projects"),
      ]);

      if (companiesRes.ok) {
        const data: Company[] = await companiesRes.json();
        setCompanies(data);
        if (data.length > 0) setFilterCompanyId(data[0].id);
      }

      if (projectsRes.ok) {
        const data: { projects: Project[] } = await projectsRes.json();
        setProjects(data.projects);
      }
    } catch {
      // Silent fail
    } finally {
      setLoaded(true);
    }
  }

  // Filtered list — apply company tab filter
  const visibleProjects = filterCompanyId
    ? projects.filter((p) => p.company_id === filterCompanyId)
    : projects;

  // Company used for new project creation — active tab's company or first company
  const createCompanyId = filterCompanyId ?? companies[0]?.id ?? null;
  const createCompanyName = companies.find((c) => c.id === createCompanyId)?.name;

  function getCompanyName(companyId: string): string {
    return companies.find((c) => c.id === companyId)?.name ?? "Unknown company";
  }

  async function createProject() {
    if (!newName.trim() || !createCompanyId) return;
    setSavingNew(true);
    try {
      const res = await apiFetch("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          company_id: createCompanyId,
          instructions: newInstructions.trim() || null,
        }),
      });
      if (res.ok) {
        const project: Project = await res.json();
        setProjects((prev) => [project, ...prev]);
        setNewName("");
        setNewInstructions("");
        setCreating(false);
        toast({ title: "Project created" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to create project", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to create project", variant: "destructive" });
    } finally {
      setSavingNew(false);
    }
  }

  function startSettings(project: Project) {
    setSettingsId(project.id);
    setEditName(project.name);
    setEditInstructions(project.instructions ?? "");
    setEditCompanyId(project.company_id);
    setPendingCompanyName(null);
    setPendingProposalCount(0);
    setShowProposalReview(false);
    // Lazy-check for pending memory proposals
    void apiFetch(`/api/v1/active-memory/proposals?project_id=${project.id}`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data?.proposals) setPendingProposalCount(data.proposals.length);
      })
      .catch(() => {});
  }

  function cancelSettings() {
    setSettingsId(null);
    setPendingCompanyName(null);
    setPendingProposalCount(0);
    setShowProposalReview(false);
  }

  function handleCompanyChange(newCompanyId: string, currentCompanyId: string) {
    setEditCompanyId(newCompanyId);
    if (newCompanyId !== currentCompanyId) {
      setPendingCompanyName(getCompanyName(newCompanyId));
    } else {
      setPendingCompanyName(null);
    }
  }

  async function saveSettings(project: Project) {
    setSavingEdit(true);
    try {
      const body: Record<string, string | null> = {};
      if (editName.trim() !== project.name) body.name = editName.trim();
      if (editCompanyId !== project.company_id) body.company_id = editCompanyId;
      // Always send instructions (null clears it)
      body.instructions = editInstructions.trim() || null;

      const res = await apiFetch(`/api/v1/projects/${project.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const updated: Project = await res.json();
        setProjects((prev) => prev.map((p) => (p.id === project.id ? updated : p)));
        cancelSettings();
        toast({ title: "Project updated" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to update project", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to update project", variant: "destructive" });
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteProject(projectId: string) {
    setConfirmingDelete(true);
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        setProjects((prev) => prev.filter((p) => p.id !== projectId));
        setDeletingId(null);
        toast({ title: "Project deleted" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to delete project", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to delete project", variant: "destructive" });
    } finally {
      setConfirmingDelete(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-8 space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Projects</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Workspace units that hold instructions, a Knowledge Base, and conversations.
          </p>
        </div>
        {!creating && loaded && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCreating(true)}
            disabled={companies.length === 0}
          >
            New project
          </Button>
        )}
      </div>

      <Separator />

      {/* ── Company filter tabs ── */}
      {companies.length > 0 && (
        <div className="flex gap-1 flex-wrap">
          <button
            className={cn(
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              filterCompanyId === null
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            )}
            onClick={() => setFilterCompanyId(null)}
          >
            All
          </button>
          {companies.map((c) => (
            <button
              key={c.id}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                filterCompanyId === c.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              )}
              onClick={() => setFilterCompanyId(c.id)}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      {/* ── Project list ── */}
      <div className="space-y-3">
        {loaded && visibleProjects.length === 0 && !creating && (
          <p className="text-sm text-muted-foreground italic">
            {companies.length === 0
              ? "Create a company first, then add projects."
              : "No projects yet. Click \u201cNew project\u201d to get started."}
          </p>
        )}

        {visibleProjects.map((project) => {
          const isSettings = settingsId === project.id;
          const isDeleting = deletingId === project.id;

          if (isDeleting) {
            return (
              <div
                key={project.id}
                className="rounded-md border border-destructive/50 bg-destructive/5 px-4 py-3 space-y-2"
              >
                <p className="text-sm font-medium text-destructive">
                  Delete &ldquo;{project.name}&rdquo;?
                </p>
                <p className="text-xs text-muted-foreground">
                  This will also delete all conversations in this project. This cannot be undone.
                </p>
                <div className="flex gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={confirmingDelete}
                    onClick={() => deleteProject(project.id)}
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

          if (isSettings) {
            return (
              <div
                key={project.id}
                className="rounded-md border border-border px-4 py-3 space-y-3"
              >
                <h3 className="text-sm font-medium text-foreground">Project Settings</h3>

                <div className="space-y-1.5">
                  <Label htmlFor={`edit-name-${project.id}`}>Name</Label>
                  <Input
                    id={`edit-name-${project.id}`}
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    autoFocus
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex justify-between items-baseline">
                    <Label htmlFor={`edit-instructions-${project.id}`}>Instructions</Label>
                    <span
                      className={cn(
                        "text-xs tabular-nums",
                        editInstructions.length >= INSTRUCTIONS_ADVISORY_THRESHOLD
                          ? "text-amber-600 dark:text-amber-400"
                          : "text-muted-foreground/60"
                      )}
                    >
                      {editInstructions.length} chars
                    </span>
                  </div>
                  <Textarea
                    id={`edit-instructions-${project.id}`}
                    value={editInstructions}
                    onChange={(e) => setEditInstructions(e.target.value)}
                    placeholder="Static context for this project's AI sessions (optional)"
                    rows={5}
                  />
                  {editInstructions.length >= INSTRUCTIONS_ADVISORY_THRESHOLD && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      Instructions are getting long — keep them focused for best results.
                    </p>
                  )}
                </div>

                {/* ── Active Memory ── */}
                <Separator />
                <div className="space-y-2">
                  <div>
                    <Label>Active Memory</Label>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Facts and preferences from past conversations — injected into every AI session.
                    </p>
                  </div>
                  {pendingProposalCount > 0 && !showProposalReview && (
                    <div className="flex items-center justify-between rounded-md bg-muted/60 border border-border px-3 py-2">
                      <p className="text-xs text-muted-foreground">
                        {pendingProposalCount} memory suggestion{pendingProposalCount !== 1 ? "s" : ""} from recent conversations.
                      </p>
                      <Button size="sm" variant="outline" onClick={() => setShowProposalReview(true)}>
                        Review
                      </Button>
                    </div>
                  )}
                  {showProposalReview && (
                    <ProposalReviewPanel
                      projectId={project.id}
                      onDismiss={() => {
                        setShowProposalReview(false);
                        // Re-fetch count — skipped_cap_exceeded proposals may still be pending
                        void apiFetch(`/api/v1/active-memory/proposals?project_id=${project.id}`)
                          .then((r) => r.ok ? r.json() : null)
                          .then((d) => setPendingProposalCount(d?.proposals?.length ?? 0))
                          .catch(() => setPendingProposalCount(0));
                      }}
                    />
                  )}
                  <ActiveMemoryPanel projectId={project.id} />
                </div>
                <Separator />

                <div className="space-y-1.5">
                  <Label htmlFor={`edit-company-${project.id}`}>Company</Label>
                  <select
                    id={`edit-company-${project.id}`}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={editCompanyId}
                    onChange={(e) => handleCompanyChange(e.target.value, project.company_id)}
                  >
                    {companies.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  {pendingCompanyName && (
                    <p className="text-xs text-muted-foreground">
                      All conversations and memory in this project will move to{" "}
                      <strong>{pendingCompanyName}</strong>.
                    </p>
                  )}
                </div>

                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!editName.trim() || savingEdit}
                    onClick={() => saveSettings(project)}
                  >
                    {savingEdit ? "Saving…" : "Save"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={cancelSettings}>
                    Cancel
                  </Button>
                </div>
              </div>
            );
          }

          return (
            <div
              key={project.id}
              className="flex items-start gap-3 rounded-md border border-border px-4 py-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{project.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {getCompanyName(project.company_id)}
                </p>
                {project.instructions && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2 italic">
                    {project.instructions}
                  </p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <Button variant="ghost" size="sm" onClick={() => startSettings(project)}>
                  Settings
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDeletingId(project.id)}
                >
                  Delete
                </Button>
              </div>
            </div>
          );
        })}

        {/* ── Create form ── */}
        {creating && (
          <div className="rounded-md border border-border px-4 py-3 space-y-3">
            <div>
              <h3 className="text-sm font-medium text-foreground">New Project</h3>
              {createCompanyName && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Will be created under <strong>{createCompanyName}</strong>
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new-project-name">Name</Label>
              <Input
                id="new-project-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Project name"
                autoFocus
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-baseline">
                <Label htmlFor="new-project-instructions">Instructions</Label>
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    newInstructions.length >= INSTRUCTIONS_ADVISORY_THRESHOLD
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-muted-foreground/60"
                  )}
                >
                  {newInstructions.length} chars
                </span>
              </div>
              <Textarea
                id="new-project-instructions"
                value={newInstructions}
                onChange={(e) => setNewInstructions(e.target.value)}
                placeholder="Optional context for this project's AI sessions (target ≤500 tokens)"
                rows={4}
              />
              {newInstructions.length >= INSTRUCTIONS_ADVISORY_THRESHOLD && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Instructions are getting long — keep them focused for best results.
                </p>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!newName.trim() || !createCompanyId || savingNew}
                onClick={createProject}
              >
                {savingNew ? "Creating…" : "Create"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setCreating(false);
                  setNewName("");
                  setNewInstructions("");
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
