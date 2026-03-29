"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Building2,
  ChevronDown,
  FolderOpen,
  Bot,
  User,
  LogOut,
  MessageSquare,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { apiFetch } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";
import type { Company, Project, ConversationListItem } from "@/lib/types/models";

const NAV_ITEMS = [
  { label: "Companies", href: "/companies", icon: Building2 },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Agents", href: "/agents", icon: Bot },
  { label: "Profile", href: "/profile", icon: User },
] as const;

const MAX_SIDEBAR_PROJECTS = 5;
const MAX_SIDEBAR_CONVERSATIONS = 10;

/** Skeleton placeholder row for loading states */
function SkeletonRow() {
  return (
    <div className="px-3 py-2 flex flex-col gap-1 animate-pulse">
      <div className="h-3 w-3/4 bg-muted rounded" />
    </div>
  );
}

/** Format relative timestamp (e.g., "2h ago", "3d ago") */
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

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();

  // Company state
  const [companies, setCompanies] = useState<Company[]>([]);
  const [activeCompany, setActiveCompany] = useState<Company | null>(null);
  const [open, setOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement>(null);

  // Projects state
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);

  // Conversations state
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);

  // Load companies on mount
  useEffect(() => {
    void loadCompanies();
  }, []);

  async function loadCompanies() {
    try {
      const res = await apiFetch("/api/v1/companies");
      if (res.ok) {
        const data: Company[] = await res.json();
        setCompanies(data);
        if (data.length > 0) setActiveCompany(data[0]);
      }
    } catch {
      // Silent fail — read-path fail-open
    }
  }

  // Load projects when active company changes
  const loadProjects = useCallback(async (companyId: string) => {
    setProjectsLoading(true);
    try {
      const res = await apiFetch(
        `/api/v1/projects?company_id=${companyId}`
      );
      if (res.ok) {
        const data = await res.json();
        setProjects((data.projects ?? data) as Project[]);
      }
    } catch {
      // Silent fail — read-path fail-open
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  // Load conversations when active company changes
  const loadConversations = useCallback(async (companyId: string) => {
    setConversationsLoading(true);
    try {
      const res = await apiFetch(
        `/api/v1/conversations?company_id=${companyId}&limit=${MAX_SIDEBAR_CONVERSATIONS}`
      );
      if (res.ok) {
        const data = await res.json();
        setConversations(
          (data.conversations ?? []) as ConversationListItem[]
        );
      }
    } catch {
      // Silent fail — read-path fail-open
    } finally {
      setConversationsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeCompany) {
      void loadProjects(activeCompany.id);
      void loadConversations(activeCompany.id);
    } else {
      setProjects([]);
      setConversations([]);
    }
  }, [activeCompany, loadProjects, loadConversations]);

  // Dismiss dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Derive truncated project list
  const visibleProjects = projects.slice(0, MAX_SIDEBAR_PROJECTS);
  const hasMoreProjects = projects.length > MAX_SIDEBAR_PROJECTS;

  /** Build the correct navigation URL for a conversation */
  function conversationHref(conv: ConversationListItem): string {
    if (conv.project_id) {
      return `/projects/${conv.project_id}/conversations/${conv.id}`;
    }
    if (conv.active_agent_id) {
      return `/agents/${conv.active_agent_id}/chat/${conv.id}`;
    }
    // Company-level conversation (no project, no agent) — fallback
    return `/conversations/${conv.id}`;
  }

  return (
    <aside className="flex flex-col w-[var(--sidebar-width)] h-screen border-r border-border bg-[hsl(var(--sidebar-bg))] shrink-0">
      {/* Company switcher */}
      <div ref={switcherRef} className="relative">
        <div
          data-testid="company-switcher"
          className="flex items-center justify-between px-4 py-3 border-b border-border cursor-pointer hover:bg-muted/50 transition-colors"
          onClick={() => setOpen((prev) => !prev)}
        >
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground uppercase tracking-widest">
              Company
            </span>
            <span className="text-sm font-medium text-foreground truncate max-w-[150px]">
              {activeCompany ? activeCompany.name : "— select company —"}
            </span>
          </div>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground shrink-0 transition-transform",
              open && "rotate-180"
            )}
          />
        </div>

        {open && companies.length > 0 && (
          <div className="absolute top-full left-0 right-0 z-50 border border-border rounded-b-md bg-[hsl(var(--sidebar-bg))] shadow-md">
            {companies.map((company) => (
              <button
                key={company.id}
                className={cn(
                  "w-full text-left px-4 py-2 text-sm hover:bg-muted/60 transition-colors",
                  activeCompany?.id === company.id
                    ? "font-medium text-foreground"
                    : "text-muted-foreground"
                )}
                onClick={() => {
                  setActiveCompany(company);
                  setOpen(false);
                }}
              >
                {company.name}
              </button>
            ))}
          </div>
        )}

        {open && companies.length === 0 && (
          <div className="absolute top-full left-0 right-0 z-50 border border-border rounded-b-md bg-[hsl(var(--sidebar-bg))] shadow-md px-4 py-3">
            <p className="text-xs text-muted-foreground italic">No companies yet</p>
          </div>
        )}
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

      {/* Projects list — KIN-380 */}
      <div className="px-2 mb-1">
        <span className="px-2 text-xs text-muted-foreground uppercase tracking-widest">
          Projects
        </span>
        <div
          data-testid="sidebar-projects"
          className="flex flex-col gap-0.5 mt-1"
        >
          {projectsLoading && (
            <>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </>
          )}
          {!projectsLoading && visibleProjects.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground italic">
              No projects yet
            </p>
          )}
          {!projectsLoading &&
            visibleProjects.map((project) => {
              const isActive = pathname === `/projects/${project.id}` ||
                pathname?.startsWith(`/projects/${project.id}/`);
              return (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors truncate",
                    isActive
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  )}
                >
                  <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{project.name}</span>
                </Link>
              );
            })}
          {!projectsLoading && hasMoreProjects && (
            <Link
              href="/projects"
              className="px-3 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              View all
            </Link>
          )}
        </div>
      </div>

      <Separator className="my-2" />

      {/* Conversations — KIN-380 */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <span className="px-4 text-xs text-muted-foreground uppercase tracking-widest mb-2">
          Conversations
        </span>
        <ScrollArea className="flex-1 px-2">
          <div
            data-testid="conversation-history"
            className="flex flex-col gap-0.5"
          >
            {conversationsLoading && (
              <>
                <SkeletonRow />
                <SkeletonRow />
                <SkeletonRow />
              </>
            )}
            {!conversationsLoading && conversations.length === 0 && (
              <p className="px-3 py-2 text-xs text-muted-foreground italic">
                No conversations yet
              </p>
            )}
            {!conversationsLoading &&
              conversations.map((conv) => (
                <Link
                  key={conv.id}
                  href={conversationHref(conv)}
                  className="flex items-start gap-2 px-3 py-2 rounded-md hover:bg-muted/60 transition-colors group"
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 mt-0.5 text-muted-foreground" />
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm text-foreground truncate">
                      {conv.title || "New conversation"}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-muted-foreground truncate">
                        {conv.project_name || conv.agent_name || "Company"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        · {relativeTime(conv.updated_at)}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
          </div>
        </ScrollArea>
      </div>

      {/* Sign out — KIN-369 */}
      <div className="px-2 pb-3 pt-1">
        <Separator className="mb-3" />
        <button
          data-testid="sign-out-button"
          className="flex items-center gap-3 w-full px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          onClick={() => {
            void supabase.auth.signOut().then(() => {
              router.push("/login");
            });
          }}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
