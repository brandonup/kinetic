"use client";

/**
 * Agents List Page — KIN-365
 *
 * Route: /agents
 * Sections:
 *   - My Agents: AgentDefinitions owned by the current user
 *   - Public Agents: all public agents from other users
 *
 * Create flow: "New Agent" button opens CreateAgentModal (modal, not a route).
 * On creation: POST /api/v1/agents → navigate to /agents/:id.
 *
 * Agent split is done client-side from the merged GET /api/v1/agents response
 * using owner_id === currentUserId (Gilfoyle review constraint §4).
 *
 * Spec ref: agents spec §4, §5, §8
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

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
          mcp_enabled: false,
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
// AgentCard
// ---------------------------------------------------------------------------

interface AgentCardProps {
  agent: AgentDefinition;
}

function AgentCard({ agent }: AgentCardProps) {
  const router = useRouter();
  const hasInstructions = agent.instructions.trim().length > 0;

  return (
    <button
      onClick={() => router.push(`/agents/${agent.id}`)}
      className={cn(
        "w-full text-left rounded-lg border bg-card p-4 transition-colors",
        "hover:bg-accent hover:text-accent-foreground focus-visible:outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring",
        !hasInstructions && "opacity-60"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium leading-snug truncate">{agent.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5 capitalize">
            {agent.type.replace("_", " ")} · {agent.visibility}
          </p>
        </div>
        {!hasInstructions && (
          <span className="shrink-0 text-xs text-muted-foreground bg-muted rounded px-1.5 py-0.5">
            No instructions
          </span>
        )}
      </div>
    </button>
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

  const isLoading = profileLoading || loading;

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

      {/* Content */}
      {!isLoading && !error && !profileError && (
        <>
          {/* My Agents section */}
          <section className="space-y-3">
            <h2 className="text-base font-medium">My Agents</h2>
            {myAgents.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center space-y-3">
                <p className="text-sm text-muted-foreground">
                  You haven&apos;t created any agents yet.
                </p>
                <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
                  Create your first agent
                </Button>
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {myAgents.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </div>
            )}
          </section>

          {/* Public Agents section */}
          <section className="space-y-3">
            <h2 className="text-base font-medium">Public Agents</h2>
            {publicAgents.length === 0 ? (
              <div className="rounded-lg border border-dashed p-6 text-center">
                <p className="text-sm text-muted-foreground">
                  No public agents available yet.
                </p>
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {publicAgents.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
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
    </div>
  );
}
