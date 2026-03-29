"use client";

/**
 * Agents List Page — KIN-365, KIN-381
 *
 * Route: /agents
 * Sections:
 *   - My Agents: AgentDefinitions owned by the current user
 *   - Public Agents: all public agents from other users
 *
 * Create flow: "New Agent" button opens CreateAgentModal (modal, not a route).
 * On creation: POST /api/v1/agents → navigate to /agents/:id.
 *
 * KIN-381: Each agent card shows Chat, Settings, and Delete actions.
 *   - Chat → /agents/:id/chat
 *   - Settings → /agents/:id (existing profile page)
 *   - Delete → confirmation dialog → soft-delete
 *
 * Agent split is done client-side from the merged GET /api/v1/agents response
 * using owner_id === currentUserId (Gilfoyle review constraint §4).
 *
 * UI Reference: docs/ui-reference-guide-claude-cowork.md
 * Spec ref: agents spec §4, §5, §8
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, Settings, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, parseApiError } from "@/lib/api";
import { useAgents } from "@/lib/hooks/useAgents";
import type {
  AgentDefinition,
  AgentType,
  AgentVisibility,
  UserProfile,
} from "@/lib/types/models";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// CreateAgentModal
// ---------------------------------------------------------------------------

interface CreateAgentModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (agent: AgentDefinition) => void;
}

function CreateAgentModal({ open, onOpenChange, onCreated }: CreateAgentModalProps) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AgentType>("custom");
  const [visibility, setVisibility] = useState<AgentVisibility>("private");
  const [submitting, setSubmitting] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  // Reset form when modal opens
  useEffect(() => {
    if (open) {
      setName("");
      setType("custom");
      setVisibility("private");
      setFieldError(null);
      // Focus name field after render
      setTimeout(() => nameRef.current?.focus(), 50);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setFieldError("Name is required.");
      return;
    }
    if (trimmedName.length > 100) {
      setFieldError("Name must be 100 characters or fewer.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await apiFetch("/api/v1/agents", {
        method: "POST",
        body: JSON.stringify({
          name: trimmedName,
          instructions: "",
          type,
          visibility,
        }),
      });

      if (!res.ok) {
        const msg = await parseApiError(res);
        // Surface 422 name-uniqueness errors as inline field error
        setFieldError(msg || "Failed to create agent.");
        return;
      }

      const created: AgentDefinition = await res.json();
      onCreated(created);
      onOpenChange(false);
    } catch (err) {
      console.error("[CreateAgentModal] submit failed:", err);
      setFieldError(err instanceof Error ? err.message : "Network error.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Agent</DialogTitle>
        </DialogHeader>
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 pt-2">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="agent-name">Name</Label>
            <Input
              id="agent-name"
              ref={nameRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Strategist, Nate Jones"
              maxLength={100}
              autoComplete="off"
            />
            {fieldError && (
              <p className="text-xs text-destructive">{fieldError}</p>
            )}
          </div>

          {/* Type */}
          <div className="space-y-1.5">
            <Label htmlFor="agent-type">Type</Label>
            <select
              id="agent-type"
              value={type}
              onChange={(e) => setType(e.target.value as AgentType)}
              className={cn(
                "w-full rounded-md border border-input bg-background px-3 py-2",
                "text-sm ring-offset-background focus-visible:outline-none",
                "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              )}
            >
              <option value="custom">Custom</option>
              <option value="thought_leader">Thought Leader</option>
            </select>
          </div>

          {/* Visibility */}
          <div className="space-y-1.5">
            <Label htmlFor="agent-visibility">Visibility</Label>
            <select
              id="agent-visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as AgentVisibility)}
              className={cn(
                "w-full rounded-md border border-input bg-background px-3 py-2",
                "text-sm ring-offset-background focus-visible:outline-none",
                "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              )}
            >
              <option value="private">Private</option>
              <option value="public">Public</option>
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Creating…" : "Create Agent"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// AgentCard — KIN-381
// ---------------------------------------------------------------------------

interface AgentCardProps {
  agent: AgentDefinition;
  isOwner: boolean;
  onDelete: (agent: AgentDefinition) => void;
}

function AgentCard({ agent, isOwner, onDelete }: AgentCardProps) {
  const router = useRouter();
  const hasInstructions = agent.instructions.trim().length > 0;
  const description = hasInstructions
    ? agent.instructions.slice(0, 100) + (agent.instructions.length > 100 ? "…" : "")
    : "No instructions";

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 transition-colors",
        "hover:border-border/80"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className="text-sm font-medium leading-snug truncate">{agent.name}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5 capitalize">
              {agent.type.replace("_", " ")}
            </span>
            <span className="text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5 capitalize">
              {agent.visibility}
            </span>
          </div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2 mb-3">
        {description}
      </p>
      <div className="flex items-center gap-1">
        <button
          data-testid={`agent-chat-${agent.id}`}
          onClick={() => router.push(`/agents/${agent.id}/chat`)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Chat
        </button>
        <button
          data-testid={`agent-settings-${agent.id}`}
          onClick={() => router.push(`/agents/${agent.id}`)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          Settings
        </button>
        {isOwner && (
          <button
            data-testid={`agent-delete-${agent.id}`}
            onClick={() => onDelete(agent)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors ml-auto"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeleteAgentDialog — KIN-381
// ---------------------------------------------------------------------------

interface DeleteAgentDialogProps {
  agent: AgentDefinition | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  deleting: boolean;
}

function DeleteAgentDialog({ agent, open, onOpenChange, onConfirm, deleting }: DeleteAgentDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete {agent?.name ?? "agent"}?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          This will remove the agent and all its data. This action cannot be undone.
        </p>
        <div className="flex justify-end gap-2 pt-4">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// AgentsPage
// ---------------------------------------------------------------------------

export default function AgentsPage() {
  const router = useRouter();
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  // Delete state — KIN-381
  const [deleteTarget, setDeleteTarget] = useState<AgentDefinition | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Fetch current user id for client-side agent split
  const fetchProfile = useCallback(async () => {
    setProfileLoading(true);
    setProfileError(false);
    try {
      const res = await apiFetch("/api/v1/profile");
      if (res.ok) {
        const profile: UserProfile = await res.json();
        setCurrentUserId(profile.id);
      } else {
        console.error("[AgentsPage] profile HTTP %d", res.status);
        setProfileError(true);
      }
    } catch (err) {
      console.error("[AgentsPage] profile fetch failed:", err);
      setProfileError(true);
    } finally {
      setProfileLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchProfile();
  }, [fetchProfile]);

  const { myAgents, publicAgents, loading, error, refetch } = useAgents(currentUserId);

  function handleCreated(agent: AgentDefinition) {
    void router.push(`/agents/${agent.id}`);
  }

  function handleDeleteClick(agent: AgentDefinition) {
    setDeleteTarget(agent);
    setDeleteOpen(true);
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${deleteTarget.id}`, {
        method: "DELETE",
      });
      if (res.ok || res.status === 204) {
        setDeleteOpen(false);
        setDeleteTarget(null);
        void refetch();
      }
    } catch (err) {
      console.error("[AgentsPage] delete failed:", err);
    } finally {
      setDeleting(false);
    }
  }

  const isLoading = profileLoading || loading;

  // Client-side search filter — KIN-381
  const filteredMyAgents = searchQuery
    ? myAgents.filter((a) => a.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : myAgents;
  const filteredPublicAgents = searchQuery
    ? publicAgents.filter((a) => a.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : publicAgents;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Agents</h1>
        <Button onClick={() => setCreateOpen(true)}>New Agent</Button>
      </div>

      {/* Profile error state */}
      {profileError && !profileLoading && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
          <p className="text-sm text-destructive">
            Failed to load your profile. Agents cannot be displayed.
          </p>
          <button
            onClick={() => void fetchProfile()}
            className="mt-1 text-xs text-destructive underline-offset-2 hover:underline"
          >
            Try again
          </button>
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
          <p className="text-sm text-destructive">{error}</p>
          <button
            onClick={() => void refetch()}
            className="mt-1 text-xs text-destructive underline-offset-2 hover:underline"
          >
            Try again
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-16 rounded-lg border bg-muted animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Search filter — KIN-381 */}
      {!isLoading && !error && !profileError && (myAgents.length > 0 || publicAgents.length > 0) && (
        <div>
          <Input
            data-testid="agent-search"
            placeholder="Search agents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-xs"
          />
        </div>
      )}

      {/* Content */}
      {!isLoading && !error && !profileError && (
        <>
          {/* My Agents section */}
          <section className="space-y-3">
            <h2 className="text-base font-medium">My Agents</h2>
            {filteredMyAgents.length === 0 && myAgents.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center space-y-3">
                <p className="text-sm text-muted-foreground">
                  You haven&apos;t created any agents yet.
                </p>
                <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
                  Create your first agent
                </Button>
              </div>
            ) : filteredMyAgents.length === 0 ? (
              <p className="text-sm text-muted-foreground px-1">
                No matching agents
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {filteredMyAgents.map((agent) => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    isOwner={true}
                    onDelete={handleDeleteClick}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Public Agents section */}
          <section className="space-y-3">
            <h2 className="text-base font-medium">Public Agents</h2>
            {filteredPublicAgents.length === 0 && publicAgents.length === 0 ? (
              <div className="rounded-lg border border-dashed p-6 text-center">
                <p className="text-sm text-muted-foreground">
                  No public agents available yet.
                </p>
              </div>
            ) : filteredPublicAgents.length === 0 ? (
              <p className="text-sm text-muted-foreground px-1">
                No matching agents
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {filteredPublicAgents.map((agent) => (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    isOwner={false}
                    onDelete={handleDeleteClick}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {/* Create Agent Modal */}
      <CreateAgentModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />

      {/* Delete Agent Dialog — KIN-381 */}
      <DeleteAgentDialog
        agent={deleteTarget}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onConfirm={() => void handleDeleteConfirm()}
        deleting={deleting}
      />
    </div>
  );
}
