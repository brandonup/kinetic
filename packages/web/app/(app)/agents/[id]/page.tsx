"use client";

/**
 * Agent Profile Page — KIN-319, KIN-366, KIN-367
 *
 * Route: /agents/:id
 * Tabs: Instructions | Knowledge Base | Framework Library | Settings
 * API:  GET /api/v1/agents/:id (agent)
 *       GET /api/v1/profile    (current user — owner check)
 *       GET /api/v1/agents/:id/knowledge-base (KB lookup)
 *       POST /api/v1/agents/:id/knowledge-base (create KB)
 *       PATCH /api/v1/agents/:id (save instructions)
 *       POST /api/v1/agents/:id/generate-instructions (regenerate from KB)
 */

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { FrameworkLibraryTab } from "@/components/FrameworkLibraryTab";
import { KnowledgeBaseTab } from "@/components/KnowledgeBaseTab";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch } from "@/lib/api";
import type { AgentDefinition, UserProfile } from "@/lib/types/models";
import { cn } from "@/lib/utils";

type Tab = "instructions" | "kb" | "frameworks" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "instructions", label: "Instructions" },
  { id: "kb", label: "Knowledge Base" },
  { id: "frameworks", label: "Framework Library" },
  { id: "settings", label: "Settings" },
];

export default function AgentProfilePage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { toast } = useToast();

  const [agent, setAgent] = useState<AgentDefinition | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [kbId, setKbId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("instructions");

  // Instructions editing state
  const [editedInstructions, setEditedInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [creatingKb, setCreatingKb] = useState(false);

  // Visibility toggle state (KIN-374)
  const [showVisibilityConfirm, setShowVisibilityConfirm] = useState(false);
  const [togglingVisibility, setTogglingVisibility] = useState(false);

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function loadData() {
    setLoading(true);
    setNotFound(false);
    setLoadError(false);
    try {
      const [agentRes, profileRes, kbRes] = await Promise.all([
        apiFetch(`/api/v1/agents/${id}`),
        apiFetch("/api/v1/profile"),
        apiFetch(`/api/v1/agents/${id}/knowledge-base`),
      ]);

      if (agentRes.status === 404) {
        setNotFound(true);
        return;
      }

      if (!agentRes.ok) {
        setLoadError(true);
        return;
      }

      const data: AgentDefinition = await agentRes.json();
      setAgent(data);
      setEditedInstructions(data.instructions || "");

      if (profileRes.ok) {
        const profile: UserProfile = await profileRes.json();
        setCurrentUserId(profile.id);
      }

      if (kbRes.ok) {
        const kb: { id: string } = await kbRes.json();
        setKbId(kb.id);
      } else {
        setKbId(null);
      }
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  const isOwner = Boolean(agent && currentUserId && agent.owner_id === currentUserId);
  const isDirty = agent ? editedInstructions !== (agent.instructions || "") : false;

  async function handleSaveInstructions() {
    if (!agent) return;
    setSaving(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instructions: editedInstructions }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast({
          variant: "destructive",
          title: "Error",
          description: err?.detail || "Failed to save instructions.",
        });
        return;
      }
      const updated: AgentDefinition = await res.json();
      setAgent(updated);
      toast({ title: "Saved", description: "Instructions updated." });
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "An unexpected error occurred.",
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleRegenerateInstructions() {
    setGenerating(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${id}/generate-instructions`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast({
          variant: "destructive",
          title: "Generation failed",
          description: err?.detail || "Could not generate instructions.",
        });
        return;
      }
      const data: { instructions: string } = await res.json();
      setEditedInstructions(data.instructions);
      toast({ title: "Generated", description: "Review the instructions below, then save." });
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "An unexpected error occurred.",
      });
    } finally {
      setGenerating(false);
    }
  }

  async function handleCreateKnowledgeBase() {
    setCreatingKb(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${id}/knowledge-base`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast({
          variant: "destructive",
          title: "Error",
          description: err?.detail || "Failed to create knowledge base.",
        });
        return;
      }
      const data: { id: string } = await res.json();
      setKbId(data.id);
      toast({ title: "Created", description: "Knowledge base ready. Upload documents to get started." });
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "An unexpected error occurred.",
      });
    } finally {
      setCreatingKb(false);
    }
  }

  async function handleToggleVisibility() {
    if (!agent) return;
    const newVisibility = agent.visibility === "private" ? "public" : "private";

    // Require confirmation before making public
    if (newVisibility === "public" && !showVisibilityConfirm) {
      setShowVisibilityConfirm(true);
      return;
    }

    setShowVisibilityConfirm(false);
    setTogglingVisibility(true);
    try {
      const res = await apiFetch(`/api/v1/agents/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visibility: newVisibility }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast({
          variant: "destructive",
          title: "Error",
          description: err?.detail || "Failed to update visibility.",
        });
        return;
      }
      const updated: AgentDefinition = await res.json();
      setAgent(updated);
      toast({
        title: "Visibility updated",
        description: `Agent is now ${updated.visibility}.`,
      });
    } catch {
      toast({
        variant: "destructive",
        title: "Error",
        description: "An unexpected error occurred.",
      });
    } finally {
      setTogglingVisibility(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-muted-foreground">Something went wrong. Please try again.</p>
      </div>
    );
  }

  if (notFound || !agent) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-muted-foreground">Agent not found.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      {/* Visibility confirmation dialog (KIN-374) */}
      {showVisibilityConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-sm w-full mx-4 space-y-4">
            <h2 className="text-base font-semibold">Make agent public?</h2>
            <p className="text-sm text-muted-foreground">
              This will make your agent visible to all users. They can invoke it
              in their conversations and access it via MCP.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowVisibilityConfirm(false)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => void handleToggleVisibility()}
                disabled={togglingVisibility}
              >
                {togglingVisibility ? "Updating…" : "Make public"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
          <p className="text-xs text-muted-foreground mt-1 capitalize">
            {agent.type.replace("_", " ")} · {agent.visibility}
          </p>
        </div>
        {isOwner && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleToggleVisibility()}
            disabled={togglingVisibility}
          >
            {togglingVisibility
              ? "Updating…"
              : agent.visibility === "private"
                ? "Make public"
                : "Make private"}
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="pt-2">
        {activeTab === "instructions" && (
          <div className="space-y-4">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                Name
              </p>
              <p className="text-sm">{agent.name}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                Instructions
              </p>
              {isOwner ? (
                <textarea
                  className="w-full min-h-[200px] rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={editedInstructions}
                  onChange={(e) => setEditedInstructions(e.target.value)}
                  placeholder="Enter system prompt instructions..."
                />
              ) : (
                <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
                  {agent.instructions}
                </pre>
              )}
            </div>
            {isOwner && (
              <div className="flex gap-2">
                <Button
                  onClick={handleSaveInstructions}
                  disabled={saving || !isDirty}
                >
                  {saving ? "Saving..." : "Save"}
                </Button>
                {agent.type === "thought_leader" && (
                  <Button
                    variant="outline"
                    onClick={handleRegenerateInstructions}
                    disabled={generating}
                  >
                    {generating ? "Generating..." : "Regenerate from corpus"}
                  </Button>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === "kb" && (
          kbId ? (
            <KnowledgeBaseTab knowledgeBaseId={kbId} />
          ) : isOwner ? (
            <div className="flex flex-col items-center justify-center py-12 space-y-3">
              <p className="text-sm text-muted-foreground">
                No knowledge base attached to this agent.
              </p>
              <Button
                onClick={handleCreateKnowledgeBase}
                disabled={creatingKb}
              >
                {creatingKb ? "Creating..." : "Create Knowledge Base"}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No knowledge base attached to this agent.
            </p>
          )
        )}

        {activeTab === "frameworks" && (
          <FrameworkLibraryTab agentId={id} isOwner={isOwner} />
        )}

        {activeTab === "settings" && (
          <p className="text-sm text-muted-foreground">Coming soon.</p>
        )}
      </div>
    </div>
  );
}
