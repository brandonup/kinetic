"use client";

/**
 * Company Settings Page — KIN-262
 *
 * Sections:
 *  1. Company list — inline edit (name + description), delete with cascade warning
 *  2. Create company — inline form
 *  3. Linked Upload stub — disabled without companies (extraction Sprint 5)
 *
 * Schema ref: docs/db-schema-spec.md §3 (companies)
 * API: GET/POST/PATCH/DELETE /api/v1/companies
 */

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch, parseApiError } from "@/lib/api";
import type { Company } from "@/lib/types/models";

export default function CompaniesPage() {
  const { toast } = useToast();

  const [companies, setCompanies] = useState<Company[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Inline edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  // Create form state
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [savingNew, setSavingNew] = useState(false);

  // Delete confirm state
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Linked upload state (per-company)
  const [uploadingCompanyId, setUploadingCompanyId] = useState<string | null>(null);
  const [uploadCompanyErrorId, setUploadCompanyErrorId] = useState<string | null>(null);
  const [companyExtracted, setCompanyExtracted] = useState<{
    companyId: string;
    name: string;
    description: string;
  } | null>(null);
  const companyFileRef = useRef<HTMLInputElement>(null);
  const activeUploadCompanyId = useRef<string | null>(null);

  useEffect(() => {
    void loadCompanies();
  }, []);

  async function loadCompanies() {
    try {
      const res = await apiFetch("/api/v1/companies");
      if (res.ok) {
        const data: Company[] = await res.json();
        setCompanies(data);
      }
    } catch {
      // Silent fail — user sees empty state
    } finally {
      setLoaded(true);
    }
  }

  async function createCompany() {
    if (!newName.trim()) return;
    setSavingNew(true);
    try {
      const res = await apiFetch("/api/v1/companies", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          description: newDesc.trim() || null,
        }),
      });
      if (res.ok) {
        const company: Company = await res.json();
        setCompanies((prev) => [company, ...prev]);
        setNewName("");
        setNewDesc("");
        setCreating(false);
        toast({ title: "Company created" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to create company", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to create company", variant: "destructive" });
    } finally {
      setSavingNew(false);
    }
  }

  function startEdit(company: Company) {
    setEditingId(company.id);
    setEditName(company.name);
    setEditDesc(company.description ?? "");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditName("");
    setEditDesc("");
  }

  async function saveEdit(company: Company) {
    setSavingEdit(true);
    try {
      const res = await apiFetch(`/api/v1/companies/${company.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editName.trim() || undefined,
          description: editDesc.trim() || undefined,
        }),
      });
      if (res.ok) {
        const updated: Company = await res.json();
        setCompanies((prev) => prev.map((c) => (c.id === company.id ? updated : c)));
        cancelEdit();
        toast({ title: "Company updated" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to update company", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to update company", variant: "destructive" });
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteCompany(companyId: string) {
    setConfirmingDelete(true);
    try {
      const res = await apiFetch(`/api/v1/companies/${companyId}`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        setCompanies((prev) => prev.filter((c) => c.id !== companyId));
        setDeletingId(null);
        toast({ title: "Company deleted" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to delete company", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to delete company", variant: "destructive" });
    } finally {
      setConfirmingDelete(false);
    }
  }

  async function handleCompanyFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    const companyId = activeUploadCompanyId.current;
    if (!f || !companyId) return;
    setUploadingCompanyId(companyId);
    setUploadCompanyErrorId(null);
    const form = new FormData();
    form.append("file", f);
    try {
      const res = await apiFetch(`/api/company/${companyId}/upload-document`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        setUploadCompanyErrorId(companyId);
        setUploadingCompanyId(null);
        return;
      }
      const data = await res.json();
      setCompanyExtracted({
        companyId,
        name: data.name ?? "",
        description: data.description ?? "",
      });
      setUploadingCompanyId(null);
    } catch {
      setUploadCompanyErrorId(companyId);
      setUploadingCompanyId(null);
    } finally {
      e.target.value = "";
    }
  }

  return (
    <TooltipProvider>
      <input
        type="file"
        ref={companyFileRef}
        accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md"
        className="hidden"
        onChange={handleCompanyFileSelect}
      />
      <div className="max-w-2xl mx-auto p-8 space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Companies</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your companies. Projects and conversations are scoped to a company.
          </p>
        </div>

        <Separator />

        {/* ── Company List ── */}
        <section className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-base font-medium text-foreground">Your Companies</h2>
            {!creating && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCreating(true)}
                disabled={!loaded}
              >
                New company
              </Button>
            )}
          </div>

          {loaded && companies.length === 0 && !creating && (
            <p className="text-sm text-muted-foreground italic">
              No companies yet. Create one to get started.
            </p>
          )}

          <div className="space-y-3">
            {companies.map((company) => {
              const isEditing = editingId === company.id;
              const isDeleting = deletingId === company.id;

              if (isDeleting) {
                return (
                  <div
                    key={company.id}
                    className="rounded-md border border-destructive/50 bg-destructive/5 px-4 py-3 space-y-2"
                  >
                    <p className="text-sm font-medium text-destructive">
                      Delete &ldquo;{company.name}&rdquo;?
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Deleting this company will permanently remove all its projects, conversations,
                      and data. This cannot be undone.
                    </p>
                    <div className="flex gap-2 pt-1">
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={confirmingDelete}
                        onClick={() => deleteCompany(company.id)}
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
                    key={company.id}
                    className="rounded-md border border-border px-4 py-3 space-y-3"
                  >
                    <div className="space-y-1.5">
                      <Label htmlFor={`edit-name-${company.id}`}>Name</Label>
                      <Input
                        id={`edit-name-${company.id}`}
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        autoFocus
                      />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-baseline">
                        <Label htmlFor={`edit-desc-${company.id}`}>Description</Label>
                        <span
                          className={`text-xs tabular-nums ${
                            editDesc.length > 1000
                              ? "text-destructive"
                              : "text-muted-foreground/60"
                          }`}
                        >
                          {editDesc.length} / 1000
                        </span>
                      </div>
                      <Textarea
                        id={`edit-desc-${company.id}`}
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        rows={3}
                      />
                    </div>
                    <div className="pt-1">
                      {companyExtracted?.companyId === company.id ? (
                        <div className="space-y-2 rounded-md border border-border p-3">
                          <p className="text-xs text-muted-foreground font-medium">
                            Review extracted fields
                          </p>
                          <div className="space-y-1">
                            <Label className="text-xs">Name</Label>
                            <Input
                              className="h-8 text-sm"
                              value={companyExtracted.name}
                              onChange={(e) =>
                                setCompanyExtracted({ ...companyExtracted, name: e.target.value })
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs">Description</Label>
                            <Textarea
                              rows={2}
                              className="text-sm"
                              value={companyExtracted.description}
                              onChange={(e) =>
                                setCompanyExtracted({
                                  ...companyExtracted,
                                  description: e.target.value,
                                })
                              }
                            />
                          </div>
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => {
                                setEditName(companyExtracted.name ?? editName);
                                setEditDesc(companyExtracted.description ?? editDesc);
                                setCompanyExtracted(null);
                              }}
                            >
                              Use this
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setCompanyExtracted(null)}
                            >
                              Discard
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={uploadingCompanyId === company.id}
                          onClick={() => {
                            activeUploadCompanyId.current = company.id;
                            companyFileRef.current?.click();
                          }}
                        >
                          {uploadingCompanyId === company.id ? "Extracting…" : "Auto-fill from document"}
                        </Button>
                      )}
                      {uploadCompanyErrorId === company.id && (
                        <p className="text-xs text-destructive mt-1">
                          Couldn&apos;t extract. Try a different file.
                        </p>
                      )}
                    </div>

                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={!editName.trim() || savingEdit || editDesc.length > 1000}
                        onClick={() => saveEdit(company)}
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
                  key={company.id}
                  className="flex items-start gap-3 rounded-md border border-border px-4 py-3"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{company.name}</p>
                    {company.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                        {company.description}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button variant="ghost" size="sm" onClick={() => startEdit(company)}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setDeletingId(company.id)}
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
                <h3 className="text-sm font-medium text-foreground">New Company</h3>
                <div className="space-y-1.5">
                  <Label htmlFor="new-company-name">Name</Label>
                  <Input
                    id="new-company-name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Company name"
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between items-baseline">
                    <Label htmlFor="new-company-desc">Description</Label>
                    <span
                      className={`text-xs tabular-nums ${
                        newDesc.length > 1000 ? "text-destructive" : "text-muted-foreground/60"
                      }`}
                    >
                      {newDesc.length} / 1000
                    </span>
                  </div>
                  <Textarea
                    id="new-company-desc"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    placeholder="Optional description of this company's context"
                    rows={3}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!newName.trim() || savingNew || newDesc.length > 1000}
                    onClick={createCompany}
                  >
                    {savingNew ? "Creating…" : "Create"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setCreating(false);
                      setNewName("");
                      setNewDesc("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </section>

      </div>
    </TooltipProvider>
  );
}
