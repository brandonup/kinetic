"use client";

/**
 * TagEditor — inline tag management for a single document.
 *
 * Displays current tags as removable chips + an input to add new tags.
 * Saves immediately via PATCH /api/v1/documents/{id}/tags.
 *
 * KIN-345 · PRD §7
 */

import { useCallback, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";

interface TagEditorProps {
  documentId: string;
  initialTags: string[];
  onTagsChanged?: (tags: string[]) => void;
}

export function TagEditor({ documentId, initialTags, onTagsChanged }: TagEditorProps) {
  const [tags, setTags] = useState<string[]>(initialTags);
  const [inputValue, setInputValue] = useState("");
  const [saving, setSaving] = useState(false);

  const saveTags = useCallback(
    async (newTags: string[]) => {
      setSaving(true);
      try {
        const res = await apiFetch(`/api/v1/documents/${documentId}/tags`, {
          method: "PATCH",
          body: JSON.stringify({ tags: newTags }),
        });
        if (res.ok) {
          setTags(newTags);
          onTagsChanged?.(newTags);
        } else {
          console.error("[TagEditor] save failed: HTTP %d", res.status);
        }
      } catch (err) {
        console.error("[TagEditor] save error:", err);
      } finally {
        setSaving(false);
      }
    },
    [documentId, onTagsChanged],
  );

  const handleAddTag = useCallback(() => {
    const trimmed = inputValue.trim().toLowerCase();
    if (!trimmed || tags.includes(trimmed)) {
      setInputValue("");
      return;
    }
    const newTags = [...tags, trimmed];
    setInputValue("");
    void saveTags(newTags);
  }, [inputValue, tags, saveTags]);

  const handleRemoveTag = useCallback(
    (tag: string) => {
      const newTags = tags.filter((t) => t !== tag);
      void saveTags(newTags);
    },
    [tags, saveTags],
  );

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((tag) => (
        <Badge
          key={tag}
          variant="secondary"
          className="text-xs gap-1 pr-1"
        >
          {tag}
          <button
            onClick={() => handleRemoveTag(tag)}
            className="ml-0.5 text-muted-foreground hover:text-foreground"
            aria-label={`Remove tag ${tag}`}
            disabled={saving}
          >
            x
          </button>
        </Badge>
      ))}
      <form
        className="inline-flex"
        onSubmit={(e) => {
          e.preventDefault();
          handleAddTag();
        }}
      >
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Add tag…"
          className="h-6 w-24 text-xs px-1.5"
          disabled={saving}
          aria-label="Add tag"
        />
      </form>
    </div>
  );
}
