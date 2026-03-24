"use client";

/**
 * ChatThread — renders a conversation's message list with agent switch markers.
 *
 * Inserts an AgentSwitchMarker between messages where agent_definition_id changes.
 *
 * KIN-337 · PRD §6, §10
 */

import { AgentSwitchMarker } from "@/components/AgentSwitchMarker";
import { ChatMessage, type ChatMessageData } from "@/components/ChatMessage";

interface ChatThreadProps {
  messages: ChatMessageData[];
}

export function ChatThread({ messages }: ChatThreadProps) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-muted-foreground">No messages yet. Start a conversation.</p>
      </div>
    );
  }

  const elements: React.ReactNode[] = [];
  let prevAgentId: string | null | undefined = undefined; // undefined = not yet set

  for (const msg of messages) {
    // Only track agent switches on assistant messages
    if (msg.role === "assistant") {
      if (prevAgentId !== undefined && msg.agent_definition_id !== prevAgentId) {
        elements.push(
          <AgentSwitchMarker
            key={`switch-${msg.id}`}
            agentName={msg.agent_name}
          />,
        );
      }
      prevAgentId = msg.agent_definition_id;
    }

    elements.push(<ChatMessage key={msg.id} message={msg} />);
  }

  return <div className="space-y-3 py-4">{elements}</div>;
}
