"use client";

import { useEffect, useRef } from "react";
import type { Message } from "@/lib/types/models";
import { cn } from "@/lib/utils";

interface ChatThreadProps {
  messages: Message[];
  /** Content of the in-flight AI response being streamed */
  streamingContent?: string;
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm"
        )}
      >
        {/* Agent attribution stub (Sprint 4) */}
        {!isUser && message.agent_definition_id && (
          <p className="text-xs text-muted-foreground mb-1">Agent</p>
        )}
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {!isUser && message.model && (
          <p className="text-xs text-muted-foreground mt-1 opacity-60">
            {message.model}
          </p>
        )}
      </div>
    </div>
  );
}

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex w-full justify-start">
      <div className="max-w-[75%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm bg-muted text-foreground">
        <p className="whitespace-pre-wrap break-words">
          {content}
          <span className="inline-block w-1.5 h-3.5 bg-foreground/60 ml-0.5 animate-pulse rounded-sm" />
        </p>
      </div>
    </div>
  );
}

export function ChatThread({ messages, streamingContent }: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  if (messages.length === 0 && !streamingContent) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">Start a conversation…</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {streamingContent !== undefined && streamingContent !== "" && (
          <StreamingBubble content={streamingContent} />
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
