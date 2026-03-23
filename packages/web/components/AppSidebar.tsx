"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Building2, ChevronDown, FolderOpen, Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { apiFetch } from "@/lib/api";
import type { Company } from "@/lib/types/models";

const NAV_ITEMS = [
  { label: "Companies", href: "/companies", icon: Building2 },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Agents", href: "/agents", icon: Bot },
  { label: "Profile", href: "/profile", icon: User },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

  const [companies, setCompanies] = useState<Company[]>([]);
  const [activeCompany, setActiveCompany] = useState<Company | null>(null);
  const [open, setOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement>(null);

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
      // Silent fail
    }
  }

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

      {/* Conversation history placeholder */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <span className="px-4 text-xs text-muted-foreground uppercase tracking-widest mb-2">
          Conversations
        </span>
        <ScrollArea className="flex-1 px-2">
          <div
            data-testid="conversation-history"
            className="flex flex-col gap-0.5"
          >
            <p className="px-3 py-2 text-xs text-muted-foreground italic">
              No conversations yet
            </p>
          </div>
        </ScrollArea>
      </div>
    </aside>
  );
}
