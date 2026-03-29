"use client";

/**
 * Project Chat Page — KIN-383
 *
 * The primary project view. Displays a chat-first layout with:
 * - Center panel: project title, chat input, recent conversations
 * - Right panel: agents, instructions, active memory, knowledge base
 *
 * UI Reference: docs/ui-reference-guide-claude-cowork.md
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  MessageSquare,
  Pencil,
  Plus,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { ModelSelector } from "@/components/ModelSelector";
import { useAgents } from "@/lib/hooks/useAgents";
import type {
  Project,
  ConversationListItem,
  AgentDefinition,
  ActiveMemoryListResponse,
} from "@/lib/types/models";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AccordionSectionProps {
  title: string;
  badge?: string;
  action?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Accordion Section (reusable right panel section)
// ---------------------------------------------------------------------------

function AccordionSection({
  title,
  badge,
  action,
  defaultOpen = true,
  children,
}: AccordionSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        className="flex items-center justify-between w-full px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/30 transition-colors"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <div className="flex items-center gap-2">
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span>{title}</span>
          {badge && (
            <span className="text-xs text-muted-foreground font-normal">
              · {badge}
            </span>
          )}
        </div>
        {action && (
          <div onClick={(e) => e.stopPropagation()}>{action}</div>
        )}
      </button>
      {isOpen && <div className="px-4 pb-3">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Relative time helper
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("bg-muted rounded animate-pulse", className)} />;
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function ProjectChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  // State
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [convsLoading, setConvsLoading] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Right panel state
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string>("");
  const [editingInstructions, setEditingInstructions] = useState(false);
  const [memory, setMemory] = useState<ActiveMemoryListResponse | null>(null);
  const [memoryLoading, setMemoryLoading] = useState(true);

  // Agents hook
  const { myAgents, publicAgents } = useAgents(null);
  const allAgents = [...(myAgents ?? []), ...(publicAgents ?? [])];

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const loadProject = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/v1/projects/${projectId}`);
      if (res.ok) {
        const data: Project = await res.json();
        setProject(data);
        setInstructions(data.instructions ?? "");
      }
    } catch {
      // read-path fail-open
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadConversations = useCallback(async () => {
    setConvsLoading(true);
    try {
      const res = await apiFetch(
        `/api/v1/conversations?project_id=${projectId}&limit=20`
      );
      if (res.ok) {
        const data = await res.json();
        setConversations(data.conversations ?? []);
      }
    } catch {
      // read-path fail-open
    } finally {
      setConvsLoading(false);
    }
  }, [projectId]);

  const loadMemory = useCallback(async () => {
    setMemoryLoading(true);
    try {
      const res = await apiFetch(
        `/api/v1/active-memory?project_id=${projectId}`
      );
      if (res.ok) {
        const data: ActiveMemoryListResponse = await res.json();
        setMemory(data);
      }
    } catch {
      // read-path fail-open
    } finally {
      setMemoryLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
    void loadConversations();
    void loadMemory();
  }, [loadProject, loadConversations, loadMemory]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleSubmitChat(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim() || submitting || !project) return;

    setSubmitting(true);
    try {
      // Create conversation
      const convRes = await apiFetch("/api/v1/conversations", {
        method: "POST",
        body: JSON.stringify({
          company_id: project.company_id,
          project_id: projectId,
          active_agent_id: activeAgentId,
        }),
      });
      if (!convRes.ok) return;
      const conv = await convRes.json();

      // Store the user message
      await apiFetch(`/api/v1/conversations/${conv.id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          role: "user",
          content: chatInput,
          model: selectedModel,
        }),
      });

      // Navigate to the conversation
      router.push(`/projects/${projectId}/conversations/${conv.id}`);
    } catch {
      // error handling — will show toast in future
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveInstructions() {
    if (!project) return;
    try {
      await apiFetch(`/api/v1/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify({ instructions }),
      });
      setEditingInstructions(false);
      setProject({ ...project, instructions });
    } catch {
      // will show toast in future
    }
  }

  function handleAgentToggle(agentId: string) {
    setActiveAgentId((prev) => (prev === agentId ? null : agentId));
  }

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex flex-1 h-full">
        <div className="flex-1 p-8">
          <SkeletonBlock className="h-8 w-48 mb-6" />
          <SkeletonBlock className="h-12 w-full mb-8" />
          <SkeletonBlock className="h-4 w-32 mb-3" />
          <SkeletonBlock className="h-16 w-full mb-2" />
          <SkeletonBlock className="h-16 w-full mb-2" />
        </div>
        <div className="w-80 border-l border-border p-4">
          <SkeletonBlock className="h-6 w-24 mb-4" />
          <SkeletonBlock className="h-20 w-full mb-4" />
          <SkeletonBlock className="h-6 w-32 mb-4" />
          <SkeletonBlock className="h-20 w-full" />
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground">Project not found</p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-1 h-full overflow-hidden">
      {/* Center Panel */}
      <div className="flex-1 flex flex-col overflow-y-auto">
        <div className="max-w-3xl mx-auto w-full px-8 py-8">
          {/* Project title */}
          <h1 className="text-2xl font-semibold text-foreground mb-6">
            {project.name}
          </h1>

          {/* Chat input */}
          <form onSubmit={handleSubmitChat} className="mb-8">
            <div className="border border-border rounded-lg bg-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="What would you like to work on in this project?"
                className="w-full resize-none bg-transparent px-4 pt-4 pb-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none min-h-[60px]"
                rows={2}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSubmitChat(e);
                  }
                }}
              />
              <div className="flex items-center justify-between px-3 pb-2">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-xs text-muted-foreground">
                    <FileText className="h-3 w-3" />
                    {project.name}
                  </span>
                  {activeAgentId && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-accent/20 rounded text-xs text-accent-foreground">
                      <Bot className="h-3 w-3" />
                      {allAgents.find((a) => a.id === activeAgentId)?.name ??
                        "Agent"}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <ModelSelector
                    selectedModelId={selectedModel}
                    onModelChange={setSelectedModel}
                  />
                  <button
                    type="submit"
                    disabled={!chatInput.trim() || submitting}
                    className={cn(
                      "p-1.5 rounded-md transition-colors",
                      chatInput.trim() && !submitting
                        ? "text-foreground hover:bg-muted"
                        : "text-muted-foreground/40 cursor-not-allowed"
                    )}
                  >
                    <Send className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </form>

          {/* Recent conversations */}
          {convsLoading && (
            <div className="space-y-2">
              <SkeletonBlock className="h-4 w-20 mb-3" />
              <SkeletonBlock className="h-14 w-full" />
              <SkeletonBlock className="h-14 w-full" />
            </div>
          )}
          {!convsLoading && conversations.length > 0 && (
            <div>
              <h2 className="text-xs text-muted-foreground uppercase tracking-widest mb-3">
                Recents
              </h2>
              <div className="flex flex-col gap-1">
                {conversations.map((conv) => (
                  <Link
                    key={conv.id}
                    href={`/projects/${projectId}/conversations/${conv.id}`}
                    className="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-muted/60 transition-colors group"
                  >
                    <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">
                        {conv.title || "New conversation"}
                      </p>
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {relativeTime(conv.updated_at)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Panel */}
      <aside className="w-80 border-l border-border bg-[hsl(var(--sidebar-bg))] overflow-y-auto shrink-0">
        {/* Agents section */}
        <AccordionSection title="Agents">
          {allAgents.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              No agents yet — create one in the Agents section
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {allAgents.map((agent) => (
                <button
                  key={agent.id}
                  onClick={() => handleAgentToggle(agent.id)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left transition-colors w-full",
                    activeAgentId === agent.id
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  )}
                >
                  <Bot className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate flex-1">{agent.name}</span>
                  <span className="text-xs opacity-60">{agent.type}</span>
                  {activeAgentId === agent.id && (
                    <span className="text-xs bg-accent-foreground/10 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </AccordionSection>

        {/* Instructions section */}
        <AccordionSection
          title="Instructions"
          action={
            !editingInstructions ? (
              <button
                onClick={() => setEditingInstructions(true)}
                className="p-1 rounded hover:bg-muted/60 transition-colors"
              >
                <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            ) : null
          }
        >
          {editingInstructions ? (
            <div className="space-y-2">
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                className="w-full bg-muted/30 border border-border rounded-md px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-ring min-h-[100px]"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  ~{Math.ceil(instructions.length / 4)} tokens
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setInstructions(project.instructions ?? "");
                      setEditingInstructions(false);
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleSaveInstructions()}
                    className="text-xs text-foreground bg-accent px-2 py-1 rounded hover:bg-accent/80"
                  >
                    Save
                  </button>
                </div>
              </div>
            </div>
          ) : instructions ? (
            <div>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-6">
                {instructions}
              </p>
              <span className="text-xs text-muted-foreground mt-1 block">
                ~{Math.ceil(instructions.length / 4)} tokens
              </span>
            </div>
          ) : (
            <button
              onClick={() => setEditingInstructions(true)}
              className="text-xs text-muted-foreground italic hover:text-foreground transition-colors"
            >
              Add instructions for this project
            </button>
          )}
        </AccordionSection>

        {/* Active Memory section */}
        <AccordionSection
          title="Active Memory"
          badge={
            memory
              ? `${memory.token_usage.current_tokens} / ${memory.token_usage.cap_tokens} tokens`
              : undefined
          }
        >
          {memoryLoading ? (
            <div className="space-y-2">
              <SkeletonBlock className="h-8 w-full" />
              <SkeletonBlock className="h-8 w-full" />
            </div>
          ) : memory && memory.entries.length > 0 ? (
            <div className="flex flex-col gap-2">
              {memory.entries.map((entry) => (
                <div
                  key={entry.id}
                  className="px-3 py-2 bg-muted/30 rounded-md text-xs text-muted-foreground"
                >
                  <p className="text-foreground">{entry.content}</p>
                  <span className="text-[10px] mt-1 block">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
              {memory.token_usage.current_tokens < memory.token_usage.cap_tokens && (
                <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  <Plus className="h-3 w-3" />
                  Add memory
                </button>
              )}
              {memory.token_usage.current_tokens >= memory.token_usage.cap_tokens && (
                <p className="text-xs text-red-400">Memory cap reached</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">
              No active memory yet — memories will be created as you chat
            </p>
          )}
        </AccordionSection>

        {/* Knowledge Base section */}
        <AccordionSection
          title="Knowledge Base"
          action={
            <button className="p-1 rounded hover:bg-muted/60 transition-colors">
              <Plus className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          }
        >
          {/* KB will be populated when document APIs are wired */}
          <p className="text-xs text-muted-foreground italic">
            Upload documents to ground this project in your data
          </p>
        </AccordionSection>
      </aside>
    </div>
  );
}
