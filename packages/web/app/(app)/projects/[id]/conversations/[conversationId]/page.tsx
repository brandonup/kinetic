"use client";

/**
 * Active Conversation Page — KIN-383
 *
 * Displays the full message thread for a conversation within a project.
 * Placeholder: full message thread + streaming will be wired in a follow-up.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export default function ConversationPage() {
  const params = useParams();
  const projectId = params.id as string;
  const conversationId = params.conversationId as string;

  return (
    <div className="flex flex-1 h-full overflow-hidden">
      <div className="flex-1 flex flex-col">
        {/* Header with back navigation */}
        <div className="border-b border-border px-6 py-3 flex items-center gap-3">
          <Link
            href={`/projects/${projectId}`}
            className="p-1 rounded-md hover:bg-muted/60 transition-colors"
          >
            <ArrowLeft className="h-4 w-4 text-muted-foreground" />
          </Link>
          <span className="text-sm font-medium text-foreground">
            Back to project
          </span>
        </div>

        {/* Message thread placeholder */}
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">
            Conversation {conversationId.slice(0, 8)}... — message thread coming soon
          </p>
        </div>

        {/* Chat input placeholder */}
        <div className="border-t border-border p-4">
          <div className="max-w-3xl mx-auto">
            <div className="border border-border rounded-lg px-4 py-3 text-sm text-muted-foreground">
              Chat input — will be wired with streaming in follow-up
            </div>
          </div>
        </div>
      </div>

      {/* Right panel will be shared via layout in follow-up */}
      <aside className="w-80 border-l border-border bg-[hsl(var(--sidebar-bg))] flex items-center justify-center">
        <p className="text-xs text-muted-foreground">Context panel</p>
      </aside>
    </div>
  );
}
