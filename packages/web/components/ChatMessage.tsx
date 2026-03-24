"use client";

/**
 * ChatMessage — renders a single message in a conversation thread.
 *
 * Features:
 *  - Role-based styling (user vs assistant)
 *  - Agent name badge on assistant messages when an agent is active
 *  - Model label on assistant messages
 *  - Expandable RAG citations for assistant messages
 *
 * KIN-337 · PRD §6, §7, §10
 */

import { Badge } from "@/components/ui/badge";
import { CitationPanel, type Citation } from "@/components/CitationPanel";
import { cn } from "@/lib/utils";

export interface ChatMessageData {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agent_definition_id: string | null;
  agent_name: string | null;
  model: string | null;
  citations: Citation[];
  created_at: string;
}

interface ChatMessageProps {
  message: ChatMessageData;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <div
      className={cn(
        "flex flex-col gap-1 max-w-[80%]",
        isUser ? "ml-auto items-end" : "mr-auto items-start",
      )}
    >
      {/* Agent badge + model label (assistant only) */}
      {isAssistant && (
        <div className="flex items-center gap-1.5 px-1">
          {message.agent_name && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              {message.agent_name}
            </Badge>
          )}
          {message.model && (
            <span className="text-[10px] text-muted-foreground">{message.model}</span>
          )}
        </div>
      )}

      {/* Message bubble */}
      <div
        className={cn(
          "rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>

      {/* Citations (assistant with RAG sources only) */}
      {isAssistant && message.citations.length > 0 && (
        <CitationPanel citations={message.citations} />
      )}

      {/* Timestamp */}
      <span className="text-[10px] text-muted-foreground px-1">
        {new Date(message.created_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    </div>
  );
}
