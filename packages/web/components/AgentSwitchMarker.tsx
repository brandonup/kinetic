"use client";

/**
 * AgentSwitchMarker — visual divider shown between messages when the active agent changes.
 *
 * Renders: "Switched to [Agent Name]" or "Agent disconnected" when agent_id goes to null.
 *
 * KIN-337 · PRD §6, §10
 */

interface AgentSwitchMarkerProps {
  agentName: string | null;
}

export function AgentSwitchMarker({ agentName }: AgentSwitchMarkerProps) {
  return (
    <div
      className="flex items-center gap-3 py-2"
      role="status"
      aria-label={agentName ? `Switched to ${agentName}` : "Agent disconnected"}
    >
      <div className="flex-1 h-px bg-border" />
      <span className="text-[11px] text-muted-foreground whitespace-nowrap">
        {agentName ? `Switched to ${agentName}` : "Agent disconnected"}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}
