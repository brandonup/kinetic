"use client";

/**
 * Agent Conversation Page — KIN-420
 *
 * Shows conversation messages and streams AI responses via the generate endpoint.
 * API:
 *   GET  /api/v1/conversations/{id}           — conversation metadata
 *   GET  /api/v1/conversations/{id}/messages   — message history (unused; generate stores messages)
 *   POST /api/v1/conversations/{id}/generate   — SSE streaming generation
 */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Send, User, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { apiFetch, parseApiError } from "@/lib/api";
import { ModelSelector } from "@/components/ModelSelector";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model?: string;
  created_at?: string;
}

interface Citation {
  document_title: string;
  snippet: string;
  similarity_score: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 py-4",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {!isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center mt-0.5">
          <Bot className="h-4 w-4 text-accent-foreground" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[75%] rounded-lg px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {message.model && !isUser && (
          <span className="text-[10px] text-muted-foreground mt-1 block opacity-60">
            {message.model}
          </span>
        )}
      </div>
      {isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center mt-0.5">
          <User className="h-4 w-4 text-primary" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Streaming indicator
// ---------------------------------------------------------------------------

function StreamingDots() {
  return (
    <div className="flex gap-3 py-4">
      <div className="shrink-0 w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center mt-0.5">
        <Bot className="h-4 w-4 text-accent-foreground" />
      </div>
      <div className="bg-muted rounded-lg px-4 py-3 flex items-center gap-1">
        <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 bg-muted-foreground/50 rounded-full animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AgentConversationPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();

  const agentId = params.id as string;
  const conversationId = params.conversationId as string;

  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentName, setAgentName] = useState<string>("Agent");
  const [convTitle, setConvTitle] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(
    searchParams.get("model"),
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initialMessageSent = useRef(false);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  // ---------------------------------------------------------------------------
  // Load agent name + existing messages
  // ---------------------------------------------------------------------------

  useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch(`/api/v1/agents/${agentId}`);
        if (res.ok) {
          const data = await res.json();
          setAgentName(data.name ?? "Agent");
        }
      } catch {
        // non-critical
      }
    })();
  }, [agentId]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await apiFetch(
          `/api/v1/conversations/${conversationId}/messages`
        );
        if (res.ok) {
          const data = await res.json();
          const loaded: Message[] = (data.messages ?? []).map(
            (m: { id: string; role: string; content: string; model?: string; created_at?: string }) => ({
              id: m.id,
              role: m.role as Message["role"],
              content: m.content,
              model: m.model ?? undefined,
              created_at: m.created_at,
            })
          );
          if (loaded.length > 0) {
            setMessages(loaded);
            // Existing conversation — don't re-send the initial message
            initialMessageSent.current = true;
          }
        }
      } catch {
        // non-critical
      }
    })();
  }, [conversationId]);

  // ---------------------------------------------------------------------------
  // Generate (stream AI response)
  // ---------------------------------------------------------------------------

  const generate = useCallback(
    async (message: string, modelId?: string | null) => {
      setStreaming(true);
      setError(null);

      // Add user message to UI immediately
      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content: message,
      };
      setMessages((prev) => [...prev, userMsg]);

      // Placeholder for assistant response
      const assistantId = generateId();
      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: "assistant", content: "" },
      ]);

      try {
        const body: Record<string, string> = { message };
        if (modelId) body.model_id = modelId;

        const res = await apiFetch(
          `/api/v1/conversations/${conversationId}/generate`,
          {
            method: "POST",
            body: JSON.stringify(body),
          }
        );

        if (!res.ok) {
          const errMsg = await parseApiError(res);
          setError(errMsg);
          // Remove the empty assistant placeholder
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
          setStreaming(false);
          return;
        }

        // Read SSE stream from fetch response
        const reader = res.body?.getReader();
        if (!reader) {
          setError("No response stream");
          setStreaming(false);
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE lines
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const event = JSON.parse(jsonStr);

              if (event.type === "delta") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + event.content }
                      : m
                  )
                );
              } else if (event.type === "done") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, id: event.message_id ?? m.id, model: event.model }
                      : m
                  )
                );
              } else if (event.type === "error") {
                setError(event.message ?? "Generation failed");
                setMessages((prev) =>
                  prev.filter((m) => m.id !== assistantId)
                );
              }
            } catch {
              // skip malformed SSE data
            }
          }
        }
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Failed to generate response"
        );
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      } finally {
        setStreaming(false);
      }
    },
    [conversationId]
  );

  // ---------------------------------------------------------------------------
  // Handle initial message from query params
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (initialMessageSent.current) return;
    const pendingMessage = searchParams.get("message");
    if (pendingMessage) {
      initialMessageSent.current = true;
      const modelId = searchParams.get("model");
      void generate(pendingMessage, modelId);
    }
  }, [searchParams, generate]);

  // ---------------------------------------------------------------------------
  // Submit handler
  // ---------------------------------------------------------------------------

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim() || streaming) return;
    const msg = chatInput;
    setChatInput("");
    void generate(msg, selectedModel);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="border-b border-border px-6 py-3 flex items-center gap-3 shrink-0">
        <Link
          href={`/agents/${agentId}/chat`}
          className="p-1 rounded-md hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-4 w-4 text-muted-foreground" />
        </Link>
        <Bot className="h-5 w-5 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">{agentName}</span>
        {convTitle && (
          <span className="text-xs text-muted-foreground">
            — {convTitle}
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6">
        <div className="max-w-3xl mx-auto w-full py-4">
          {messages.length === 0 && !streaming && (
            <div className="text-center py-16">
              <p className="text-muted-foreground text-sm">
                Start a conversation with {agentName}
              </p>
            </div>
          )}

          {messages.map((msg) =>
            msg.role === "assistant" && msg.content === "" && streaming ? (
              <StreamingDots key={msg.id} />
            ) : (
              <MessageBubble key={msg.id} message={msg} />
            )
          )}

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 my-2">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border px-6 py-4 shrink-0">
        <form
          onSubmit={handleSubmit}
          className="max-w-3xl mx-auto w-full"
        >
          <div className="border border-border rounded-lg bg-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1">
            <textarea
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder={`Message ${agentName}...`}
              className="w-full resize-none bg-transparent px-4 pt-3 pb-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none min-h-[44px] max-h-[160px]"
              rows={1}
              disabled={streaming}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <div className="flex items-center justify-between px-3 pb-2">
              <ModelSelector
                selectedModelId={selectedModel}
                onModelChange={setSelectedModel}
              />
              <button
                type="submit"
                disabled={!chatInput.trim() || streaming}
                className={cn(
                  "p-1.5 rounded-md transition-colors shrink-0",
                  chatInput.trim() && !streaming
                    ? "text-foreground hover:bg-muted"
                    : "text-muted-foreground/40 cursor-not-allowed"
                )}
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
