"use client";

/**
 * User Profile Settings Page — KIN-261
 *
 * Sections:
 *  1. Name + bio (PATCH /api/v1/profile)
 *  2. API keys per provider (GET/POST/DELETE /api/v1/profile/api-keys)
 *  3. Default model selector (PATCH /api/v1/profile/default-model)
 *  4. Linked Upload button (UI-only in Sprint 2; backend wired Sprint 5)
 *
 * Schema ref: docs/db-schema-spec.md §1 (users), §2 (user_api_keys)
 * All snake_case from API is mapped to camelCase in local state manually.
 */

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/use-toast";
import { apiFetch, parseApiError } from "@/lib/api";
import type {
  ApiKeyEntry,
  ApiKeyProvider,
  ModelConfiguration,
  UserProfile,
} from "@/lib/types/models";

const PROVIDERS: ApiKeyProvider[] = ["anthropic", "openai", "google", "groq"];

const PROVIDER_LABELS: Record<ApiKeyProvider, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google",
  groq: "Groq",
};

// Maps provider name to the model provider field for matching API keys to models
const PROVIDER_MODEL_MAP: Record<ApiKeyProvider, string> = {
  anthropic: "anthropic",
  openai: "openai",
  google: "google",
  groq: "groq",
};

export default function ProfilePage() {
  const { toast } = useToast();

  // Profile state
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [defaultModelId, setDefaultModelId] = useState<string | null>(null);
  const [profileLoaded, setProfileLoaded] = useState(false);

  // API keys state
  const [apiKeys, setApiKeys] = useState<Partial<Record<ApiKeyProvider, ApiKeyEntry>>>({});
  const [editingProvider, setEditingProvider] = useState<ApiKeyProvider | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [savingKey, setSavingKey] = useState<ApiKeyProvider | null>(null);

  // Models state
  const [models, setModels] = useState<ModelConfiguration[]>([]);

  // Linked upload state
  const [uploadState, setUploadState] = useState<"idle" | "loading" | "review" | "error">("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [reviewName, setReviewName] = useState("");
  const [reviewBio, setReviewBio] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load all data on mount
  useEffect(() => {
    void loadAll();
  }, []);

  async function loadAll() {
    try {
      const [profileRes, keysRes, modelsRes] = await Promise.all([
        apiFetch("/api/v1/profile"),
        apiFetch("/api/v1/profile/api-keys"),
        apiFetch("/api/v1/admin/models"),
      ]);

      if (profileRes.ok) {
        const profile: UserProfile = await profileRes.json();
        setName(profile.name ?? "");
        setBio(profile.bio ?? "");
        setDefaultModelId(profile.default_model_id);
        setProfileLoaded(true);
      }

      if (keysRes.ok) {
        const keys: ApiKeyEntry[] = await keysRes.json();
        const keyMap: Partial<Record<ApiKeyProvider, ApiKeyEntry>> = {};
        for (const entry of keys) {
          keyMap[entry.provider] = entry;
        }
        setApiKeys(keyMap);
      }

      if (modelsRes.ok) {
        const data = await modelsRes.json();
        // Filter to only generation models
        const generationModels = (data.models ?? data ?? []).filter(
          (m: ModelConfiguration) => m.category === "generation" && m.enabled
        );
        setModels(generationModels);
      }
    } catch {
      // Silent fail on load — user sees empty state
    }
  }

  async function saveProfile() {
    try {
      const res = await apiFetch("/api/v1/profile", {
        method: "PATCH",
        body: JSON.stringify({ name, bio }),
      });
      if (!res.ok) {
        const msg = await parseApiError(res);
        toast({ title: "Failed to save profile", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to save profile", variant: "destructive" });
    }
  }

  async function saveApiKey(provider: ApiKeyProvider, key: string) {
    setSavingKey(provider);
    try {
      const res = await apiFetch("/api/v1/profile/api-keys", {
        method: "POST",
        body: JSON.stringify({ provider, api_key: key }),
      });
      if (res.ok) {
        const data: { provider: ApiKeyProvider; key_hint: string } = await res.json();
        setApiKeys((prev) => ({
          ...prev,
          [provider]: { provider, key_hint: data.key_hint, validated_at: null },
        }));
        setEditingProvider(null);
        setEditingValue("");
        toast({ title: "API key saved" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to save API key", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to save API key", variant: "destructive" });
    } finally {
      setSavingKey(null);
    }
  }

  async function removeApiKey(provider: ApiKeyProvider) {
    try {
      const res = await apiFetch(`/api/v1/profile/api-keys/${provider}`, {
        method: "DELETE",
      });
      if (res.ok || res.status === 204) {
        setApiKeys((prev) => {
          const next = { ...prev };
          delete next[provider];
          return next;
        });
        toast({ title: "API key removed" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to remove API key", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to remove API key", variant: "destructive" });
    }
  }

  async function setDefaultModel(modelId: string) {
    try {
      const res = await apiFetch("/api/v1/profile/default-model", {
        method: "PATCH",
        body: JSON.stringify({ model_id: modelId }),
      });
      if (res.ok) {
        setDefaultModelId(modelId);
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to set default model", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to set default model", variant: "destructive" });
    }
  }

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploadState("loading");
    setUploadError(null);
    const form = new FormData();
    form.append("file", f);
    try {
      const res = await apiFetch("/api/profile/upload-document", { method: "POST", body: form });
      if (!res.ok) {
        setUploadError("Couldn't extract content. Try a different file.");
        setUploadState("error");
        return;
      }
      const data = await res.json();
      setReviewName(data.name ?? "");
      setReviewBio(data.bio ?? "");
      setUploadState("review");
    } catch {
      setUploadError("Upload failed. Please try again.");
      setUploadState("error");
    } finally {
      e.target.value = "";
    }
  }

  async function handleUseExtracted() {
    setName(reviewName);
    setBio(reviewBio);
    try {
      const res = await apiFetch("/api/v1/profile", {
        method: "PATCH",
        body: JSON.stringify({ name: reviewName, bio: reviewBio }),
      });
      if (!res.ok) {
        const msg = await parseApiError(res);
        toast({ title: "Failed to save profile", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to save profile", variant: "destructive" });
    }
    setUploadState("idle");
  }

  const hasAnyKey = Object.keys(apiKeys).length > 0;

  // A model is selectable only if the user has a configured key for that provider
  function isModelEnabled(model: ModelConfiguration): boolean {
    return !!apiKeys[model.provider as ApiKeyProvider];
  }

  return (
    <TooltipProvider>
      <div className="max-w-2xl mx-auto p-8 space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Profile</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Your name, bio, API keys, and default model.
          </p>
        </div>

        <Separator />

        {/* ── Name + Bio ── */}
        <section className="space-y-4">
          <h2 className="text-base font-medium text-foreground">Identity</h2>

          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={saveProfile}
              placeholder="Your full name"
              disabled={!profileLoaded}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between items-baseline">
              <Label htmlFor="bio">Bio</Label>
              <span
                className={`text-xs tabular-nums ${
                  bio.length > 1000
                    ? "text-destructive"
                    : bio.length > 500
                    ? "text-muted-foreground"
                    : "text-muted-foreground/60"
                }`}
              >
                {bio.length} / 1000
              </span>
            </div>
            <Textarea
              id="bio"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              onBlur={saveProfile}
              placeholder="A short description of your background and expertise (optional)"
              rows={4}
              disabled={!profileLoaded}
            />
          </div>
        </section>

        <Separator />

        {/* ── API Keys ── */}
        <section className="space-y-4">
          <div>
            <h2 className="text-base font-medium text-foreground">API Keys</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Bring your own keys. Keys are encrypted at rest and never returned in full.
            </p>
          </div>

          <div className="space-y-3">
            {PROVIDERS.map((provider) => {
              const entry = apiKeys[provider];
              const isEditing = editingProvider === provider;
              const isSaving = savingKey === provider;

              return (
                <div
                  key={provider}
                  className="flex items-center gap-3 rounded-md border border-border px-4 py-3"
                >
                  <span className="w-24 text-sm font-medium text-foreground">
                    {PROVIDER_LABELS[provider]}
                  </span>

                  {entry && !isEditing ? (
                    <>
                      <span className="flex-1 text-sm text-muted-foreground font-mono">
                        {entry.key_hint}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingProvider(provider);
                          setEditingValue("");
                        }}
                      >
                        Update
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => removeApiKey(provider)}
                      >
                        Remove
                      </Button>
                    </>
                  ) : isEditing ? (
                    <>
                      <Input
                        className="flex-1 text-sm font-mono h-8"
                        placeholder="Paste API key…"
                        value={editingValue}
                        onChange={(e) => setEditingValue(e.target.value)}
                        autoFocus
                      />
                      <Button
                        size="sm"
                        disabled={!editingValue || isSaving}
                        onClick={() => saveApiKey(provider, editingValue)}
                      >
                        {isSaving ? "Saving…" : "Save"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingProvider(null);
                          setEditingValue("");
                        }}
                      >
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-sm text-muted-foreground">Not configured</span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditingProvider(provider);
                          setEditingValue("");
                        }}
                      >
                        Add key
                      </Button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <Separator />

        {/* ── Default Model ── */}
        <section className="space-y-3">
          <div>
            <h2 className="text-base font-medium text-foreground">Default Model</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Used for new conversations unless overridden at query time. Models without a
              matching API key are disabled.
            </p>
          </div>

          <select
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground disabled:opacity-50"
            value={defaultModelId ?? ""}
            onChange={(e) => {
              if (e.target.value) void setDefaultModel(e.target.value);
            }}
          >
            <option value="">Select a model…</option>
            {models.map((model) => {
              const enabled = isModelEnabled(model);
              return (
                <option
                  key={model.id}
                  value={model.id}
                  disabled={!enabled}
                  title={enabled ? undefined : "Add an API key to enable"}
                >
                  {model.display_name}
                  {!enabled ? " (add API key to enable)" : ""}
                </option>
              );
            })}
          </select>
        </section>

        <Separator />

        {/* ── Linked Upload ── */}
        <section className="space-y-3">
          <div>
            <h2 className="text-base font-medium text-foreground">Auto-fill from Document</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Upload a PDF, DOCX, or TXT to auto-fill your name and bio. Requires an API key.
            </p>
          </div>

          <input
            type="file"
            ref={fileInputRef}
            accept=".pdf,.docx,.doc,.txt"
            className="hidden"
            onChange={handleFileSelect}
          />

          {uploadState === "review" ? (
            <div className="space-y-3 rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground font-medium">Review extracted fields</p>
              <div className="space-y-1.5">
                <Label htmlFor="review-name">Name</Label>
                <Input
                  id="review-name"
                  value={reviewName}
                  onChange={(e) => setReviewName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="review-bio">Bio</Label>
                <Textarea
                  id="review-bio"
                  value={reviewBio}
                  onChange={(e) => setReviewBio(e.target.value)}
                  rows={3}
                />
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleUseExtracted}>
                  Use this
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setUploadState("idle")}>
                  Discard
                </Button>
              </div>
            </div>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    variant="outline"
                    disabled={!hasAnyKey || uploadState === "loading"}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploadState === "loading" ? "Extracting…" : "Upload document"}
                  </Button>
                </span>
              </TooltipTrigger>
              {!hasAnyKey && (
                <TooltipContent>Add an API key to enable auto-fill</TooltipContent>
              )}
            </Tooltip>
          )}

          {uploadState === "error" && uploadError && (
            <p className="text-sm text-destructive">{uploadError}</p>
          )}
        </section>
      </div>
    </TooltipProvider>
  );
}
