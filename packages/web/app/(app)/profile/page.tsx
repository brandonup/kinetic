"use client";

/**
 * User Profile Settings Page — KIN-261, KIN-325
 *
 * Sections:
 *  1. Name + bio (PATCH /api/v1/profile)
 *  2. API keys per provider (GET/POST/DELETE /api/v1/profile/api-keys)
 *  3. Default model selector (PATCH /api/v1/profile/default-model)
 *  4. Linked Upload button (UI-only in Sprint 2; backend wired Sprint 5)
 *  5. MCP Tokens (GET/POST/PATCH /api/v1/mcp/tokens) — KIN-325
 *
 * Schema ref: docs/db-schema-spec.md §1 (users), §2 (user_api_keys), §18 (mcp_tokens)
 * All snake_case from API is mapped to camelCase in local state manually.
 */

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  CreateMcpTokenResponse,
  McpToken,
  McpTokenListResponse,
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
  const [modelsError, setModelsError] = useState(false);

  // MCP tokens state — KIN-325
  const [mcpTokens, setMcpTokens] = useState<McpToken[]>([]);
  const [showGenerateForm, setShowGenerateForm] = useState(false);
  const [generateLabel, setGenerateLabel] = useState("");
  const [generatingToken, setGeneratingToken] = useState(false);
  const [newToken, setNewToken] = useState<CreateMcpTokenResponse | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [revokeConfirmId, setRevokeConfirmId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

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
      const [profileRes, keysRes, modelsRes, mcpRes] = await Promise.all([
        apiFetch("/api/v1/profile"),
        apiFetch("/api/v1/profile/api-keys"),
        apiFetch("/api/v1/admin/models"),
        apiFetch("/api/v1/mcp/tokens"),
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
        setModelsError(false);
      } else {
        setModelsError(true);
      }

      if (mcpRes.ok) {
        const data: McpTokenListResponse = await mcpRes.json();
        setMcpTokens(data.tokens);
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

  async function generateToken() {
    const label = generateLabel.trim();
    if (!label) return;
    setGeneratingToken(true);
    try {
      const res = await apiFetch("/api/v1/mcp/tokens", {
        method: "POST",
        body: JSON.stringify({ name: label }),
      });
      if (res.ok) {
        const data: CreateMcpTokenResponse = await res.json();
        // Add masked entry to the list immediately
        setMcpTokens((prev) => [
          ...prev,
          { id: data.id, name: data.name, last_used_at: null, created_at: data.created_at },
        ]);
        setNewToken(data);
        setGenerateLabel("");
        setShowGenerateForm(false);
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to generate token", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to generate token", variant: "destructive" });
    } finally {
      setGeneratingToken(false);
    }
  }

  async function revokeToken(id: string) {
    setRevokingId(id);
    try {
      const res = await apiFetch(`/api/v1/mcp/tokens/${id}/revoke`, { method: "PATCH" });
      if (res.ok) {
        // Optimistic removal
        setMcpTokens((prev) => prev.filter((t) => t.id !== id));
        setRevokeConfirmId(null);
        toast({ title: "Token revoked" });
      } else {
        const msg = await parseApiError(res);
        toast({ title: "Failed to revoke token", description: msg, variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to revoke token", variant: "destructive" });
    } finally {
      setRevokingId(null);
    }
  }

  function formatLastUsed(ts: string | null): string {
    if (!ts) return "Never";
    return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  async function copyToken(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setTokenCopied(true);
      setTimeout(() => setTokenCopied(false), 2000);
    } catch {
      toast({ title: "Copy failed — please copy manually", variant: "destructive" });
    }
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

        {/* ── Linked Upload (Auto-fill) ── */}
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

          {modelsError ? (
            <p className="text-sm text-destructive">
              Failed to load models. Try refreshing the page.
            </p>
          ) : models.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No generation models available. An admin must add and enable models in the{" "}
              <a href="/admin/models" className="underline text-foreground hover:text-foreground/80">
                LLM Models
              </a>{" "}
              settings first.
            </p>
          ) : (
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
          )}
        </section>

        <Separator />

        {/* ── MCP Tokens ── */}
        <section className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-medium text-foreground">MCP Tokens</h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Bearer tokens for connecting Claude Desktop, Cursor, and other MCP clients.
              </p>
            </div>
            {!showGenerateForm && (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={() => setShowGenerateForm(true)}
              >
                Generate new token
              </Button>
            )}
          </div>

          {/* Inline generate form */}
          {showGenerateForm && (
            <div className="flex items-center gap-2 rounded-md border border-border px-4 py-3">
              <Input
                className="flex-1 h-8 text-sm"
                placeholder="Label, e.g. Claude Desktop, Cursor"
                value={generateLabel}
                onChange={(e) => setGenerateLabel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void generateToken();
                  if (e.key === "Escape") {
                    setShowGenerateForm(false);
                    setGenerateLabel("");
                  }
                }}
                maxLength={64}
                autoFocus
              />
              <Button
                size="sm"
                disabled={!generateLabel.trim() || generatingToken}
                onClick={() => void generateToken()}
              >
                {generatingToken ? "Generating…" : "Generate"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowGenerateForm(false);
                  setGenerateLabel("");
                }}
              >
                Cancel
              </Button>
            </div>
          )}

          {/* Token list */}
          {mcpTokens.length > 0 && (
            <div className="rounded-md border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Label</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Created</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Last used</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {mcpTokens.map((token) => (
                    <tr key={token.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">{token.name}</div>
                        <div className="text-xs text-muted-foreground font-mono mt-0.5">mcp_••••••••</div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(token.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatLastUsed(token.last_used_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRevokeConfirmId(token.id)}
                        >
                          Revoke
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {mcpTokens.length === 0 && !showGenerateForm && (
            <p className="text-sm text-muted-foreground">No tokens yet.</p>
          )}
        </section>
      </div>

      {/* ── One-time token modal ── */}
      {newToken && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setNewToken(null);
              setTokenCopied(false);
            }
          }}
        >
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Token generated</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <p className="text-sm text-destructive font-medium">
                Copy this token now. You won&apos;t be able to see it again.
              </p>
              <div className="flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2">
                <code className="flex-1 text-xs font-mono break-all text-foreground select-all">
                  {newToken.token}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={() => void copyToken(newToken.token)}
                >
                  {tokenCopied ? "Copied!" : "Copy"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Token label: <span className="font-medium text-foreground">{newToken.name}</span>
              </p>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" size="sm">
                  Done
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* ── Revoke confirm dialog ── */}
      {revokeConfirmId && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setRevokeConfirmId(null);
          }}
        >
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Revoke token?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground py-2">
              Revoke &ldquo;
              {mcpTokens.find((t) => t.id === revokeConfirmId)?.name ?? "this token"}
              &rdquo;? Any client using this token will immediately lose access.
            </p>
            <DialogFooter>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRevokeConfirmId(null)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={revokingId === revokeConfirmId}
                onClick={() => void revokeToken(revokeConfirmId)}
              >
                {revokingId === revokeConfirmId ? "Revoking…" : "Revoke"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </TooltipProvider>
  );
}
