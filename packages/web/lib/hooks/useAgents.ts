"use client";

/**
 * useAgents — fetches owned + public agents and splits them client-side.
 *
 * Calls GET /api/v1/agents which returns a merged, deduplicated list of:
 *   - agents owned by the current user
 *   - all public agents from other users
 *
 * Client-side split: owner_id === currentUserId → myAgents; the rest → publicAgents.
 *
 * Designed for reuse by both the Agents list page (KIN-365) and the future
 * chat-side Agent Selector dropdown (spec §5 / N2 from 2026-03-25 review).
 *
 * KIN-365 · agents spec §5
 */

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { AgentDefinition } from "@/lib/types/models";

interface UseAgentsResult {
  myAgents: AgentDefinition[];
  publicAgents: AgentDefinition[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useAgents(currentUserId: string | null): UseAgentsResult {
  const [myAgents, setMyAgents] = useState<AgentDefinition[]>([]);
  const [publicAgents, setPublicAgents] = useState<AgentDefinition[]>([]);
  const [loading, setLoading] = useState(currentUserId !== null);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    if (!currentUserId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/v1/agents");
      if (!res.ok) {
        const text = await res.text();
        console.error("[useAgents] HTTP %d: %s", res.status, text);
        setError(text || "Failed to load agents");
        return;
      }
      const agents: AgentDefinition[] = await res.json();
      setMyAgents(agents.filter((a) => a.owner_id === currentUserId));
      setPublicAgents(agents.filter((a) => a.owner_id !== currentUserId));
    } catch (err) {
      console.error("[useAgents] fetch failed:", err);
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  }, [currentUserId]);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  return { myAgents, publicAgents, loading, error, refetch: fetchAgents };
}
