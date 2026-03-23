"use client";

import { useEffect, useState } from "react";
import { Bot, ChevronDown, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { listAgents } from "@/lib/api";
import type { AgentDefinition } from "@/lib/types/models";

interface AgentSelectorProps {
  /** Currently active agent definition id, or null */
  activeAgentId: string | null;
  /** Authenticated user id — used to split "My Agents" from "Public Agents" */
  userId: string | null;
  onActivate: (agentId: string) => void;
  onDeactivate: () => void;
}

export function AgentSelector({
  activeAgentId,
  userId,
  onActivate,
  onDeactivate,
}: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  // Load agents when the dropdown opens for the first time
  useEffect(() => {
    if (!open || agents.length > 0) return;
    setLoading(true);
    listAgents()
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, agents.length]);

  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;

  const myAgents = agents.filter(
    (a) => a.owner_id === userId && !!a.instructions
  );
  const publicAgents = agents.filter(
    (a) => a.owner_id !== userId && a.visibility === "public" && !!a.instructions
  );

  const handleSelect = (agentId: string) => {
    setOpen(false);
    if (agentId === activeAgentId) {
      onDeactivate();
    } else {
      onActivate(agentId);
    }
  };

  return (
    <div className="flex items-center gap-1">
      {activeAgent ? (
        <>
          <div className="flex items-center gap-1.5 rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
            <Bot className="h-3 w-3" />
            <span>{activeAgent.name}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onDeactivate}
            title="Deactivate agent"
          >
            <X className="h-3 w-3" />
          </Button>
        </>
      ) : null}

      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs">
            <Bot className="h-3.5 w-3.5" />
            {activeAgent ? "Switch agent" : "Add agent"}
            <ChevronDown className="h-3 w-3 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          {loading && (
            <DropdownMenuItem disabled>Loading agents…</DropdownMenuItem>
          )}

          {!loading && myAgents.length > 0 && (
            <>
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                My Agents
              </DropdownMenuLabel>
              <DropdownMenuGroup>
                {myAgents.map((agent) => (
                  <DropdownMenuItem
                    key={agent.id}
                    onSelect={() => handleSelect(agent.id)}
                    className="flex items-center gap-2"
                  >
                    <Bot className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="truncate">{agent.name}</span>
                    {agent.id === activeAgentId && (
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        active
                      </span>
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}

          {!loading && publicAgents.length > 0 && (
            <>
              {myAgents.length > 0 && <DropdownMenuSeparator />}
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                Public Agents
              </DropdownMenuLabel>
              <DropdownMenuGroup>
                {publicAgents.map((agent) => (
                  <DropdownMenuItem
                    key={agent.id}
                    onSelect={() => handleSelect(agent.id)}
                    className="flex items-center gap-2"
                  >
                    <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{agent.name}</span>
                    {agent.id === activeAgentId && (
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        active
                      </span>
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </>
          )}

          {!loading && myAgents.length === 0 && publicAgents.length === 0 && (
            <DropdownMenuItem disabled>No agents available</DropdownMenuItem>
          )}

          {activeAgentId && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  setOpen(false);
                  onDeactivate();
                }}
                className="text-muted-foreground"
              >
                <X className="h-3.5 w-3.5 mr-2" />
                Deactivate agent
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
