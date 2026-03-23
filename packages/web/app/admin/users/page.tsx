"use client";

/**
 * Admin Users Page — KIN-264
 *
 * Sections:
 *  1. User list — email, name, role badge, status badge, created date, enable/disable actions
 *  2. Disable gate — 409 shows transfer modal listing public agents with Transfer To dropdown
 *  3. Transfer agent — resolves agent ownership before completing disable
 *
 * Schema ref: docs/db-schema-spec.md §1 (users), §8 (agent_definitions)
 * API: GET /api/v1/admin/users
 *      PATCH /api/v1/admin/users/{id}/disable
 *      PATCH /api/v1/admin/users/{id}/enable
 *      PATCH /api/v1/admin/users/{id}/transfer-agent
 */

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch, parseApiError } from "@/lib/api";
import type { AdminUser } from "@/lib/types/models";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function AdminUsersPage() {
  const { toast } = useToast();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Disable transfer modal state
  const [transferTarget, setTransferTarget] = useState<AdminUser | null>(null);
  const [publicAgentIds, setPublicAgentIds] = useState<string[]>([]);
  // Map of agentId → new_owner_id selection
  const [agentTransfers, setAgentTransfers] = useState<Record<string, string>>({});
  const [transferring, setTransferring] = useState(false);

  // Per-row action state
  const [actingId, setActingId] = useState<string | null>(null);

  useEffect(() => {
    void loadUsers();
  }, []);

  async function loadUsers() {
    try {
      const res = await apiFetch("/api/v1/admin/users");
      if (res.ok) {
        const data: { users: AdminUser[] } = await res.json();
        setUsers(data.users);
      }
    } catch {
      // Silent fail
    } finally {
      setLoaded(true);
    }
  }

  async function handleDisable(user: AdminUser) {
    setActingId(user.id);
    try {
      const res = await apiFetch(`/api/v1/admin/users/${user.id}/disable`, {
        method: "PATCH",
      });
      if (res.ok || res.status === 204) {
        setUsers((prev) =>
          prev.map((u) =>
            u.id === user.id ? { ...u, disabled_at: new Date().toISOString() } : u
          )
        );
        toast({ title: `${user.email} disabled` });
      } else if (res.status === 409) {
        const body = await res.json();
        setPublicAgentIds(body.detail?.public_agent_ids ?? []);
        setAgentTransfers({});
        setTransferTarget(user);
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to disable user", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to disable user", variant: "destructive" });
    } finally {
      setActingId(null);
    }
  }

  async function handleEnable(user: AdminUser) {
    setActingId(user.id);
    try {
      const res = await apiFetch(`/api/v1/admin/users/${user.id}/enable`, {
        method: "PATCH",
      });
      if (res.ok) {
        setUsers((prev) =>
          prev.map((u) => (u.id === user.id ? { ...u, disabled_at: null } : u))
        );
        toast({ title: `${user.email} enabled` });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to enable user", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to enable user", variant: "destructive" });
    } finally {
      setActingId(null);
    }
  }

  async function resolveTransfersAndDisable() {
    if (!transferTarget) return;

    // Validate all agents have a transfer target selected
    const unresolved = publicAgentIds.filter((id) => !agentTransfers[id]);
    if (unresolved.length > 0) {
      toast({
        title: "Select a new owner for each agent",
        variant: "destructive",
      });
      return;
    }

    setTransferring(true);
    try {
      // Transfer each agent
      for (const agentId of publicAgentIds) {
        const newOwnerId = agentTransfers[agentId];
        const res = await apiFetch(
          `/api/v1/admin/users/${transferTarget.id}/transfer-agent`,
          {
            method: "PATCH",
            body: JSON.stringify({ agent_id: agentId, new_owner_id: newOwnerId }),
          }
        );
        if (!res.ok) {
          const msg = await parseApiError(res);
          toast({ title: "Failed to transfer agent", description: msg, variant: "destructive" });
          return;
        }
      }

      // Retry disable
      const res = await apiFetch(
        `/api/v1/admin/users/${transferTarget.id}/disable`,
        { method: "PATCH" }
      );
      if (res.ok || res.status === 204) {
        setUsers((prev) =>
          prev.map((u) =>
            u.id === transferTarget.id
              ? { ...u, disabled_at: new Date().toISOString() }
              : u
          )
        );
        toast({ title: `${transferTarget.email} disabled` });
        setTransferTarget(null);
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to disable user", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to complete transfer", variant: "destructive" });
    } finally {
      setTransferring(false);
    }
  }

  // Other users available as transfer targets
  const otherUsers = users.filter((u) => transferTarget && u.id !== transferTarget.id);

  return (
    <div className="max-w-4xl mx-auto p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Users</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Manage user accounts. Users are created via auth signup.
        </p>
      </div>

      <Separator />

      {/* ── Transfer modal ── */}
      {transferTarget && (
        <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 px-4 py-4 space-y-4">
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
              Transfer required before disabling &ldquo;{transferTarget.email}&rdquo;
            </p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              This user owns {publicAgentIds.length} public agent
              {publicAgentIds.length !== 1 ? "s" : ""}. Transfer each to another user to continue.
            </p>
          </div>

          <div className="space-y-2">
            {publicAgentIds.map((agentId) => (
              <div key={agentId} className="flex items-center gap-3">
                <span className="text-xs font-mono text-muted-foreground flex-1 truncate">
                  {agentId}
                </span>
                <select
                  className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
                  value={agentTransfers[agentId] ?? ""}
                  onChange={(e) =>
                    setAgentTransfers((prev) => ({ ...prev, [agentId]: e.target.value }))
                  }
                >
                  <option value="" disabled>
                    Transfer to…
                  </option>
                  {otherUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.email || u.name}
                    </option>
                  ))}
                </select>
                {/* TODO Sprint 4: add "set to private" option when PATCH /api/v1/agents/{id} exists */}
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={transferring}
              onClick={resolveTransfersAndDisable}
            >
              {transferring ? "Transferring…" : "Transfer & disable"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={transferring}
              onClick={() => setTransferTarget(null)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* ── User list ── */}
      <div className="space-y-3">
        {loaded && users.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No users found.</p>
        )}

        {users.map((user) => {
          const isDisabled = user.disabled_at !== null;
          const isActing = actingId === user.id;

          return (
            <div
              key={user.id}
              className={`flex items-start gap-3 rounded-md border px-4 py-3 ${
                isDisabled ? "border-border opacity-60" : "border-border"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium text-foreground truncate">
                    {user.email || user.name}
                  </p>
                  {/* Role badge */}
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${
                      user.role === "admin"
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {user.role}
                  </span>
                  {/* Status badge */}
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${
                      isDisabled
                        ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                        : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    }`}
                  >
                    {isDisabled ? "Disabled" : "Active"}
                  </span>
                </div>
                {user.email && user.name && (
                  <p className="text-xs text-muted-foreground mt-0.5">{user.name}</p>
                )}
                <p className="text-xs text-muted-foreground mt-0.5">
                  Joined {formatDate(user.created_at)}
                </p>
              </div>

              <div className="flex gap-1 shrink-0">
                {isDisabled ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={isActing}
                    onClick={() => handleEnable(user)}
                  >
                    {isActing ? "Enabling…" : "Enable"}
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    disabled={isActing}
                    onClick={() => handleDisable(user)}
                  >
                    {isActing ? "Disabling…" : "Disable"}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
