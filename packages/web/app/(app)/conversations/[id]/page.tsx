"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ChatThread } from "@/components/ChatThread";
import { ChatInput } from "@/components/ChatInput";
import { AgentSelector } from "@/components/AgentSelector";
import { getConversation, updateConversation, apiFetch } from "@/lib/api";
import { createStreamEventSource } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";
import type { ConversationWithMessages, Message } from "@/lib/types/models";
import type { StreamEvent } from "@/lib/types/models";

export default function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  const [conversation, setConversation] =
    useState<ConversationWithMessages | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [enabledProviders, setEnabledProviders] = useState<string[]>([]);
  const [defaultModelId, setDefaultModelId] = useState<string | null>(null);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getConversation(id)
      .then((conv) => {
        setConversation(conv);
        setMessages(conv.messages);
        setActiveAgentId(conv.active_agent_id ?? null);
      })
      .catch(() => {});
  }, [id]);

  // Load user profile for enabled providers + default model
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      setUserId(session.user.id);

      apiFetch("/api/v1/profile/api-keys")
        .then((r) => r.json())
        .then((data: { provider: string }[]) => {
          setEnabledProviders((data ?? []).map((k) => k.provider));
        })
        .catch(() => {});

      apiFetch("/api/v1/profile")
        .then((r) => r.json())
        .then((data: { default_model_id?: string | null }) => {
          setDefaultModelId(data.default_model_id ?? null);
        })
        .catch(() => {});
    });
  }, []);

  const handleActivateAgent = useCallback(
    async (agentId: string) => {
      if (!id) return;
      try {
        await updateConversation(id, { active_agent_id: agentId });
        setActiveAgentId(agentId);
      } catch {
        // silent — agent selector will not reflect change
      }
    },
    [id]
  );

  const handleDeactivateAgent = useCallback(async () => {
    if (!id) return;
    try {
      await updateConversation(id, { active_agent_id: null });
      setActiveAgentId(null);
    } catch {
      // silent
    }
  }, [id]);

  const handleSend = useCallback(
    async (content: string, modelId: string | null) => {
      if (!id || streaming) return;

      // Optimistically add the user message
      const optimisticUserMsg: Message = {
        id: `optimistic-${Date.now()}`,
        role: "user",
        content,
        agent_definition_id: null,
        model: null,
        sequence: messages.length,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticUserMsg]);
      setStreamingContent("");
      setStreaming(true);

      const { data: { session } } = await supabase.auth.getSession();
      const accessToken = session?.access_token;

      const source = createStreamEventSource({
        conversationId: id,
        content,
        accessToken,
        modelId: modelId ?? undefined,
      });

      let accumulated = "";

      source.addEventListener("delta", (e) => {
        const event = JSON.parse(e.data) as StreamEvent;
        const chunk = event.data.text ?? "";
        accumulated += chunk;
        setStreamingContent(accumulated);
      });

      source.addEventListener("done", (e) => {
        const event = JSON.parse(e.data) as StreamEvent;
        source.close();
        setStreaming(false);
        setStreamingContent("");
        // Add the persisted assistant message
        const assistantMsg: Message = {
          id: event.generation_id,
          role: "assistant",
          content: accumulated,
          agent_definition_id: null,
          model: null,
          sequence: messages.length + 1,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => {
          // Replace optimistic user msg with the real conversation state
          const withoutOptimistic = prev.filter((m) =>
            !m.id.startsWith("optimistic-")
          );
          return [...withoutOptimistic, optimisticUserMsg, assistantMsg];
        });
      });

      source.addEventListener("error", () => {
        source.close();
        setStreaming(false);
        setStreamingContent("");
        // Remove optimistic message on error
        setMessages((prev) =>
          prev.filter((m) => !m.id.startsWith("optimistic-"))
        );
      });

      source.onerror = () => {
        source.close();
        setStreaming(false);
        setStreamingContent("");
      };
    },
    [id, streaming, messages]
  );

  const title = conversation?.title ?? "New conversation";

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="border-b border-border px-6 py-3 shrink-0 flex items-center justify-between gap-4">
        <h1 className="text-sm font-medium text-foreground truncate">
          {title}
        </h1>
        <AgentSelector
          activeAgentId={activeAgentId}
          userId={userId}
          onActivate={handleActivateAgent}
          onDeactivate={handleDeactivateAgent}
        />
      </div>

      {/* Thread */}
      <ChatThread
        messages={messages}
        streamingContent={streaming ? streamingContent : undefined}
      />

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        disabled={streaming}
        enabledProviders={enabledProviders}
        defaultModelId={defaultModelId}
      />
    </div>
  );
}
