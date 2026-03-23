"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  FolderOpen,
  Bot,
  User,
  ChevronDown,
  Plus,
  MessageSquare,
  Pencil,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import {
  createConversation,
  deleteConversation,
  listConversations,
  updateConversation,
} from "@/lib/api";
import type { Conversation } from "@/lib/types/models";
import { useCallback, useEffect, useRef, useState } from "react";

const NAV_ITEMS = [
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Agents", href: "/agents", icon: Bot },
  { label: "Profile", href: "/profile", icon: User },
] as const;

interface ConversationGroup {
  label: string;
  projectId: string | null;
  items: Conversation[];
}

function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const companyLevel: Conversation[] = [];
  const byProject: Record<string, Conversation[]> = {};

  for (const c of conversations) {
    if (!c.project_id) {
      companyLevel.push(c);
    } else {
      if (!byProject[c.project_id]) byProject[c.project_id] = [];
      byProject[c.project_id].push(c);
    }
  }

  const groups: ConversationGroup[] = [];
  if (companyLevel.length > 0) {
    groups.push({ label: "General", projectId: null, items: companyLevel });
  }
  for (const [projectId, items] of Object.entries(byProject)) {
    groups.push({ label: `Project ${projectId.slice(0, 8)}`, projectId, items });
  }
  return groups;
}

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onDeleted: (id: string) => void;
  onRenamed: (id: string, title: string) => void;
}

function ConversationItem({
  conversation,
  isActive,
  onDeleted,
  onRenamed,
}: ConversationItemProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(
    conversation.title ?? "New conversation"
  );
  const [hovering, setHovering] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const handleRename = async () => {
    setEditing(false);
    const trimmed = editValue.trim();
    if (!trimmed || trimmed === (conversation.title ?? "New conversation")) return;
    await updateConversation(conversation.id, { title: trimmed });
    onRenamed(conversation.id, trimmed);
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    await deleteConversation(conversation.id);
    onDeleted(conversation.id);
    router.push("/");
  };

  const displayTitle = conversation.title ?? "New conversation";

  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 px-3 py-1.5 rounded-md text-sm cursor-pointer transition-colors",
        isActive
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
      )}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => {
        setHovering(false);
        setConfirmDelete(false);
      }}
    >
      <MessageSquare className="h-3.5 w-3.5 shrink-0" />

      {editing ? (
        <input
          ref={inputRef}
          className="flex-1 bg-transparent text-sm outline-none border-b border-border"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleRename();
            if (e.key === "Escape") {
              setEditing(false);
              setEditValue(conversation.title ?? "New conversation");
            }
          }}
        />
      ) : (
        <Link
          href={`/conversations/${conversation.id}`}
          className="flex-1 truncate"
        >
          {displayTitle}
        </Link>
      )}

      {hovering && !editing && (
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={(e) => {
              e.preventDefault();
              setEditing(true);
            }}
            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title="Rename"
          >
            <Pencil className="h-3 w-3" />
          </button>
          <button
            onClick={(e) => {
              e.preventDefault();
              handleDelete();
            }}
            className={cn(
              "p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground",
              confirmDelete && "text-destructive hover:text-destructive"
            )}
            title={confirmDelete ? "Click again to confirm" : "Delete"}
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);

  const loadConversations = useCallback(async () => {
    setLoading(true);
    try {
      const { conversations: list } = await listConversations();
      setConversations(list);
    } catch {
      // no-op — sidebar degrades gracefully until user is authed
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleNewConversation = async () => {
    // Derive project_id from current path if inside a project
    const projectMatch = pathname?.match(/^\/projects\/([^/]+)/);
    const projectId = projectMatch ? projectMatch[1] : null;

    // company_id: ideally from active company store; stub with first conversation's company
    const companyId =
      conversations[0]?.company_id ??
      "00000000-0000-0000-0000-000000000000"; // placeholder until company switcher is wired

    try {
      const conv = await createConversation({
        company_id: companyId,
        project_id: projectId,
      });
      setConversations((prev) => [conv, ...prev]);
      router.push(`/conversations/${conv.id}`);
    } catch {
      // TODO: toast error
    }
  };

  const groups = groupConversations(conversations);
  const activeConvId = pathname?.match(/^\/conversations\/([^/]+)/)?.[1];

  return (
    <aside className="flex flex-col w-[var(--sidebar-width)] h-screen border-r border-border bg-[hsl(var(--sidebar-bg))] shrink-0">
      {/* Company switcher placeholder */}
      <div
        data-testid="company-switcher"
        className="flex items-center justify-between px-4 py-3 border-b border-border cursor-pointer hover:bg-muted/50 transition-colors"
      >
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-muted-foreground uppercase tracking-widest">
            Company
          </span>
          <span className="text-sm font-medium text-foreground truncate max-w-[150px]">
            — select company —
          </span>
        </div>
        <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
      </div>

      {/* Primary nav */}
      <nav className="flex flex-col gap-1 px-2 pt-4">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const isActive = pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      <Separator className="my-3" />

      {/* Conversation history */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-4 mb-2">
          <span className="text-xs text-muted-foreground uppercase tracking-widest">
            Conversations
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={handleNewConversation}
            title="New conversation"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>

        <ScrollArea className="flex-1 px-2">
          <div
            data-testid="conversation-history"
            className="flex flex-col gap-0.5"
          >
            {loading && (
              <p className="px-3 py-2 text-xs text-muted-foreground italic">
                Loading…
              </p>
            )}

            {!loading && conversations.length === 0 && (
              <p className="px-3 py-2 text-xs text-muted-foreground italic">
                No conversations yet
              </p>
            )}

            {groups.map((group) => (
              <div key={group.label} className="mb-2">
                <p className="px-3 py-1 text-xs text-muted-foreground font-medium">
                  {group.label}
                </p>
                {group.items.map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={conv.id === activeConvId}
                    onDeleted={(id) =>
                      setConversations((prev) =>
                        prev.filter((c) => c.id !== id)
                      )
                    }
                    onRenamed={(id, title) =>
                      setConversations((prev) =>
                        prev.map((c) => (c.id === id ? { ...c, title } : c))
                      )
                    }
                  />
                ))}
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </aside>
  );
}
