"use client";

import { useEffect, useState } from "react";
import { listEnabledGenerationModels } from "@/lib/api";
import type { ModelConfiguration } from "@/lib/types/models";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { ChevronDown, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModelSelectorProps {
  /** Currently selected model id */
  value: string | null;
  /** Called when the user picks a model */
  onChange: (modelId: string) => void;
  /** Providers for which the user has a BYOK key configured */
  enabledProviders: string[];
  className?: string;
}

export function ModelSelector({
  value,
  onChange,
  enabledProviders,
  className,
}: ModelSelectorProps) {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    listEnabledGenerationModels()
      .then(setModels)
      .catch(() => {});
  }, []);

  const selected = models.find((m) => m.id === value);
  const label = selected?.name ?? "Select model";

  return (
    <div className={cn("relative", className)}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="flex items-center gap-1.5 h-7 text-xs px-2"
        onClick={() => setOpen((o) => !o)}
      >
        <Cpu className="h-3.5 w-3.5" />
        <span className="max-w-[120px] truncate">{label}</span>
        <ChevronDown className="h-3 w-3" />
      </Button>

      {open && (
        <div className="absolute bottom-full mb-1 left-0 z-50 w-56 rounded-md border border-border bg-popover shadow-md py-1">
          {models.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">
              No models available
            </p>
          )}
          {models.map((model) => {
            const hasKey = enabledProviders.includes(model.provider);
            return (
              <Tooltip key={model.id}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    disabled={!hasKey}
                    onClick={() => {
                      if (!hasKey) return;
                      onChange(model.id);
                      setOpen(false);
                    }}
                    className={cn(
                      "w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left",
                      hasKey
                        ? "hover:bg-accent cursor-pointer"
                        : "opacity-40 cursor-not-allowed",
                      value === model.id && "bg-accent"
                    )}
                  >
                    <span className="flex-1 truncate">{model.name}</span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {model.provider}
                    </span>
                  </button>
                </TooltipTrigger>
                {!hasKey && (
                  <TooltipContent side="right">
                    Add an API key to enable.
                  </TooltipContent>
                )}
              </Tooltip>
            );
          })}
        </div>
      )}
    </div>
  );
}
