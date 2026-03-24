"use client";

/**
 * ModelSelector — dropdown showing admin-enabled generation models.
 *
 * Models for which the user has no configured API key are visible but disabled (greyed out).
 * Disabled models show a tooltip: "Add an [Provider] API key to use this model".
 * Proper ARIA listbox pattern with keyboard navigation + outside click + Escape dismiss.
 *
 * KIN-337 · PRD §10
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api";
import type { ApiKeyEntry, ModelConfiguration, ModelProvider } from "@/lib/types/models";
import { cn } from "@/lib/utils";

interface ModelSelectorProps {
  selectedModelId: string | null;
  onModelChange: (modelId: string) => void;
}

const PROVIDER_LABELS: Record<ModelProvider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  groq: "Groq",
};

export function ModelSelector({ selectedModelId, onModelChange }: ModelSelectorProps) {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [userProviders, setUserProviders] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);

  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = "model-selector-listbox";

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [modelsRes, keysRes] = await Promise.all([
        apiFetch("/api/v1/admin/models"),
        apiFetch("/api/v1/profile/api-keys"),
      ]);

      if (modelsRes.ok) {
        const data = await modelsRes.json();
        const generationModels = (data.models ?? data ?? []).filter(
          (m: ModelConfiguration) => m.category === "generation" && m.enabled,
        );
        setModels(generationModels);
      }

      if (keysRes.ok) {
        const data = await keysRes.json();
        const keys: ApiKeyEntry[] = data.api_keys ?? data ?? [];
        setUserProviders(new Set(keys.map((k) => k.provider)));
      }
    } catch (err) {
      console.error("[ModelSelector] fetchData failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // ---------------------------------------------------------------------------
  // Outside click + Escape dismiss
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  // ---------------------------------------------------------------------------
  // Keyboard navigation
  // ---------------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!open) {
        if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setOpen(true);
          setFocusedIndex(0);
        }
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setFocusedIndex((prev) => Math.min(prev + 1, models.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setFocusedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "Enter":
        case " ": {
          e.preventDefault();
          const model = models[focusedIndex];
          if (model && userProviders.has(model.provider)) {
            onModelChange(model.id);
            setOpen(false);
          }
          break;
        }
        case "Escape":
          e.preventDefault();
          setOpen(false);
          break;
      }
    },
    [open, models, focusedIndex, userProviders, onModelChange],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const selectedModel = models.find((m) => m.id === selectedModelId);

  if (loading) {
    return <div className="h-8 w-40 rounded bg-muted animate-pulse" />;
  }

  return (
    <TooltipProvider>
      <div className="relative" ref={containerRef}>
        <button
          onClick={() => {
            setOpen(!open);
            if (!open) setFocusedIndex(models.findIndex((m) => m.id === selectedModelId));
          }}
          onKeyDown={handleKeyDown}
          className="flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-muted transition-colors"
          aria-label="Select model"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
        >
          <span className="truncate max-w-[200px]">
            {selectedModel?.display_name ?? "Select model"}
          </span>
          <svg
            className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {open && (
          <div
            id={listboxId}
            className="absolute left-0 top-full mt-1 z-50 w-64 rounded-md border bg-popover shadow-md"
            role="listbox"
            aria-label="Available models"
            aria-activedescendant={
              focusedIndex >= 0 && models[focusedIndex]
                ? `model-option-${models[focusedIndex].id}`
                : undefined
            }
            onKeyDown={handleKeyDown}
          >
            {models.map((model, index) => {
              const hasKey = userProviders.has(model.provider);
              const isSelected = model.id === selectedModelId;
              const isFocused = index === focusedIndex;

              const optionContent = (
                <div
                  id={`model-option-${model.id}`}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={!hasKey}
                  tabIndex={-1}
                  data-focused={isFocused || undefined}
                  onClick={() => {
                    if (hasKey) {
                      onModelChange(model.id);
                      setOpen(false);
                    }
                  }}
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm flex items-center justify-between transition-colors",
                    hasKey && !isSelected && "hover:bg-muted cursor-pointer",
                    hasKey && isSelected && "bg-accent text-accent-foreground",
                    !hasKey && "opacity-40 cursor-not-allowed",
                    isFocused && hasKey && "bg-muted",
                    isFocused && !hasKey && "ring-1 ring-inset ring-border",
                  )}
                >
                  <div className="flex flex-col min-w-0">
                    <span className="truncate">{model.display_name}</span>
                    <span className="text-[10px] text-muted-foreground capitalize">
                      {model.provider}
                    </span>
                  </div>
                  {isSelected && (
                    <svg
                      className="h-4 w-4 shrink-0 text-primary"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  )}
                </div>
              );

              return hasKey ? (
                <div key={model.id}>{optionContent}</div>
              ) : (
                <Tooltip key={model.id}>
                  <TooltipTrigger asChild>{optionContent}</TooltipTrigger>
                  <TooltipContent side="right">
                    Add an {PROVIDER_LABELS[model.provider]} API key to use this model
                  </TooltipContent>
                </Tooltip>
              );
            })}

            {models.length === 0 && (
              <p className="px-3 py-2 text-sm text-muted-foreground">No models available</p>
            )}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
