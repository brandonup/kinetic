"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ModelSelector } from "@/components/ModelSelector";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (content: string, modelId: string | null) => void;
  disabled?: boolean;
  /** Providers for which the user has a BYOK key configured */
  enabledProviders: string[];
  /** Default model id from user profile */
  defaultModelId: string | null;
}

export function ChatInput({
  onSend,
  disabled = false,
  enabledProviders,
  defaultModelId,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(
    defaultModelId
  );
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, selectedModelId);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border bg-background p-3">
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message…"
          rows={1}
          disabled={disabled}
          className="resize-none border-0 bg-transparent p-1 text-sm shadow-none focus-visible:ring-0 min-h-[32px] max-h-[200px] overflow-y-auto"
          style={{ fieldSizing: "content" } as React.CSSProperties}
        />
        <div className="flex items-center justify-between">
          <ModelSelector
            value={selectedModelId}
            onChange={setSelectedModelId}
            enabledProviders={enabledProviders}
          />
          <Button
            type="button"
            size="icon"
            className="h-7 w-7"
            disabled={!value.trim() || disabled}
            onClick={handleSubmit}
          >
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
