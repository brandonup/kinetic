# Code Review: KIN-454 — assemble_context single-tool MCP optimization

**Reviewer:** Gilfoyle
**Date:** 2026-04-03
**Ticket:** KIN-454
**Status:** In Progress (implementation complete, awaiting deploy + E2E test)

---

## Files Reviewed

| File | Lines | Change Summary |
|---|---|---|
| `kinetic-mcp/tools.ts` | 1-911 | Added `assembleContext()` + 3 internal helpers (`fetchActiveMemory`, `fetchFramework`, `fetchKnowledgeBase`). Tool definition + executor dispatch. Query param validation for all query-dependent tools. |
| `kinetic-mcp/prompts.ts` | 1-156 | Updated `buildPromptBody()` to call `assemble_context` instead of 4 separate tools. |
| `kinetic-mcp/index.ts` | 1-313 | Updated tool count in header comment (5 → 6). |
| `kinetic-mcp/embedding.ts` | 1-122 | Unchanged — reviewed for context. |

---

## Spec Compliance

| Done-when | Status |
|---|---|
| `assemble_context` tool implemented in `kinetic-mcp/tools.ts` | PASS |
| Prompt template updated to use single tool call | PASS |
| Individual tools still work independently | PASS |
| Tested end-to-end via Cowork `/nate` invocation | NOT YET — awaiting deploy |

---

## Findings

### 1. [Important] Debug console.log in production code — `index.ts:183-184`

```typescript
console.log("[prompts/list] userId:", userId);
console.log("[prompts/list] result:", JSON.stringify(prompts));
```

These log the authenticated user ID and full prompt list to Edge Function logs on every `prompts/list` call. Minor info leak. Remove before production deploy.

**Fix:** Delete both lines. If structured logging is needed later, use a proper logger with log levels.

### 2. [Note] `debug_prompts_list` tool still registered — `tools.ts:697-739, 828`

Comment says "Remove after KIN-454." Correct to keep until E2E verification passes. Track removal as part of deploy checklist.

### 3. [Note] Code duplication between individual tools and internal helpers

`fetchFramework` duplicates `selectFramework` logic. `fetchKnowledgeBase` duplicates `searchKnowledgeBase` logic. `fetchActiveMemory` duplicates `getActiveMemory` logic. The individual tools don't call the helpers — they have their own inline implementations.

Not a KIN-454 spec violation (the "extract shared helpers" requirement is on KIN-456 for the Python server). But creates divergence risk if either path is modified independently. Flag for future cleanup — refactor individual tools to call the helpers + resolveAgent + embedQuery.

---

## Architecture Assessment

**Positive:**
- Single `resolveAgent` eliminates 3 redundant DB lookups per invocation
- Single `embedQuery` eliminates 1 redundant OpenAI API call (~200-500ms saved)
- `Promise.allSettled` fan-out is correct — memory, framework, KB run in parallel with independent failure boundaries
- Null-embedding case handled properly: framework + KB get descriptive error, memory proceeds independently
- Tool definition schema matches spec exactly (`agent` + `query`, both required)
- `executeTool` dispatch and param validation correctly include `assemble_context` in both `agentTools` and `queryTools` arrays
- Prompt template cleanly instructs single-tool invocation with numbered post-processing steps
- Output format uses `---` separators matching spec
- Backward compatibility preserved — all 5 individual tools unchanged and functional

**No security issues found.** Access control via `resolveAgent` (ownership + public visibility check) applies to the single agent lookup. BYOK key handling unchanged.

---

## Verdict

**Architecture approved.** 0 Critical, 1 Important (debug logs). Deploy-ready after removing the console.log statements and completing E2E verification.
