"use client";

/**
 * DocumentStatusBadge — displays document ingestion status with color-coded badge.
 *
 * Stages: pending → extracting → chunking → embedding → completed | failed
 * Failed state shows the error_stage in the badge tooltip.
 *
 * KIN-346 · PRD §7 (Knowledge Base & RAG)
 */

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { DocumentStatus } from "@/lib/types/models";
import { cn } from "@/lib/utils";

interface DocumentStatusBadgeProps {
  status: DocumentStatus;
  errorStage?: string | null;
  errorMessage?: string | null;
}

const STATUS_CONFIG: Record<
  DocumentStatus,
  { label: string; className: string }
> = {
  pending: {
    label: "Pending",
    className: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  },
  extracting: {
    label: "Extracting",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  },
  chunking: {
    label: "Chunking",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  },
  embedding: {
    label: "Embedding",
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  },
  completed: {
    label: "Completed",
    className: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  },
  failed: {
    label: "Failed",
    className: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  },
};

const PROCESSING_STATUSES: Set<DocumentStatus> = new Set([
  "pending",
  "extracting",
  "chunking",
  "embedding",
]);

export function DocumentStatusBadge({
  status,
  errorStage,
  errorMessage,
}: DocumentStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const isProcessing = PROCESSING_STATUSES.has(status);

  const ariaLabel =
    status === "failed" && errorStage
      ? `Failed at ${errorStage}${errorMessage ? `: ${errorMessage}` : ""}`
      : undefined;

  const badge = (
    <Badge
      variant="secondary"
      className={cn(
        "text-xs font-medium px-2 py-0.5 select-none",
        config.className,
      )}
      aria-label={ariaLabel}
    >
      {isProcessing && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse"
          aria-hidden="true"
        />
      )}
      {config.label}
    </Badge>
  );

  if (status === "failed" && (errorStage || errorMessage)) {
    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>{badge}</TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs text-xs">
            {errorStage && <p className="font-medium">Failed at: {errorStage}</p>}
            {errorMessage && <p className="mt-0.5 text-muted-foreground">{errorMessage}</p>}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badge;
}
