"use client";

/**
 * Agent Profile Page — KIN-319
 *
 * Route: /agents/:id
 * Tabs: Instructions | Knowledge Base | Framework Library | Settings
 * API:  GET /api/v1/agents/:id (agent)
 *       GET /api/v1/profile    (current user — owner check)
 */

import { useEffect, useState } from "react";

import { FrameworkLibraryTab } from "@/components/FrameworkLibraryTab";
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

  const [agent, setAgent] = useState<AgentDefinition | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("instructions");

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function loadData() {
    setLoading(true);
    setNotFound(false);
    setLoadError(false);
    try {
      const [agentRes, profileRes] = await Promise.all([
        apiFetch(`/api/v1/agents/${id}`),
        apiFetch("/api/v1/profile"),
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

      if (profileRes.ok) {
        const profile: UserProfile = await profileRes.json();
        setCurrentUserId(profile.id);
      }
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  const isOwner = Boolean(agent && currentUserId && agent.owner_id === currentUserId);

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
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">{agent.name}</h1>
        <p className="text-xs text-muted-foreground mt-1 capitalize">
          {agent.type.replace("_", " ")} · {agent.visibility}
        </p>
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
              <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">
                {agent.instructions}
              </pre>
            </div>
          </div>
        )}

        {activeTab === "kb" && (
          <p className="text-sm text-muted-foreground">Coming soon.</p>
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
