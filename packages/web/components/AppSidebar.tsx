"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderOpen, Bot, User, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const NAV_ITEMS = [
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Agents", href: "/agents", icon: Bot },
  { label: "Profile", href: "/profile", icon: User },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

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
