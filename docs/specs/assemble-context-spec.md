# assemble_context — Single-Call Context Assembly

**Ticket:** KIN-454
**Status:** Implemented
**Blocks:** KIN-452 (MCP conversation logging)

---

## Problem

The current MCP prompt template instructs the LLM to call 4 tools in parallel:

1. `get_agent_persona` — fetch agent persona
2. `get_active_memory` — fetch active memory entries
3. `select_framework` — embed query + vector search framework triggers
4. `search_knowledge_base` — embed query + vector search KB chunks

Each tool call is a separate HTTP request to the Edge Function, each performing its own:
- `authenticate()` — token lookup + rate limit check
- `resolveAgent()` — agent definition lookup + instance lookup/creation
- `embedQuery()` — decrypt BYOK key + OpenAI API call (tools 3 and 4)

**Redundancy:**
- 4x auth cycles (same token, same user)
- 4x agent resolution (same slug, same user)
- 2x identical OpenAI embedding calls (same query, same model, same dimensions)

**Estimated critical path:** ~450-750ms

---

## Solution

A single `assemble_context` tool that:

1. **One HTTP request** to the Edge Function
2. **One `authenticate()`** (handled by the MCP server entry point)
3. **One `resolveAgent()`** — returns persona as a side effect (no extra query)
4. **One `embedQuery()`** — shared between framework + KB search
5. **`Promise.allSettled` fan-out** — memory, framework, KB run in parallel
6. **Graceful degradation** — each layer returns its result or a graceful empty message; one layer's failure never cascades to others

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "agent": { "type": "string", "description": "Agent slug (e.g., 'nate')" },
    "query": { "type": "string", "description": "The user's question" }
  },
  "required": ["agent", "query"]
}
```

### Output Format

Structured markdown with 4 sections separated by `---`:

```
## Persona

# Agent Name

[system prompt instructions]

---

## Active Memory

- **2026-03-30:** [memory entry]
- **2026-03-29:** [memory entry]

---

## Framework

# Framework: [name]
[description, when_to_apply, principles, steps, example_application]

---

## Knowledge Base

### [1] Document Title > Section (relevance: 0.87)
[chunk text]
```

Each section degrades to a descriptive empty message if no data is available:
- Persona: omitted if no instructions
- Memory: "No active memories"
- Framework: "No matching framework found" or "No framework library configured..."
- KB: "No relevant knowledge base entries found" or "No knowledge base configured..."

---

## Latency Analysis

| Operation | Before (4 calls) | After (1 call) | Saved |
|---|---|---|---|
| Auth | ~100ms x 4 | ~100ms x 1 | ~300ms |
| Agent resolution | ~50ms x 4 | ~50ms x 1 | ~150ms |
| OpenAI embedding | ~200-500ms x 2 | ~200-500ms x 1 | ~200-500ms |
| DB fan-out | sequential per tool | parallel `Promise.allSettled` | varies |

**Estimated critical path after:** ~300-550ms (down from ~450-750ms)

---

## Postgres Best Practices Applied

Per `supabase-postgres-best-practices` skill:

- **N+1 elimination** (`data-n-plus-one`): 4 separate tool calls each making redundant auth + agent resolution queries = classic N+1 pattern. Collapsed to 1 request with shared resolution.
- **Connection pooling awareness** (`conn-pooling`): Fewer Supabase client instantiations per user interaction. Edge Functions share the connection pool — fewer concurrent requests = lower pool pressure.

---

## Implementation

### Files Changed

| File | Change |
|---|---|
| `kinetic-mcp/tools.ts` | Added `assembleContext()` function + 3 internal helpers (`fetchActiveMemory`, `fetchFramework`, `fetchKnowledgeBase`). Added tool definition + executor dispatch. |
| `kinetic-mcp/prompts.ts` | Updated `buildPromptBody()` to call `assemble_context` instead of 4 separate tools. |

### Architecture

```
assemble_context(agent, query)
  │
  ├─ resolveAgent(slug) ──→ persona (from instructions field)
  │
  ├─ embedQuery(query) ──→ number[3072]
  │
  └─ Promise.allSettled([
       fetchActiveMemory(instanceId),
       fetchFramework(definitionId, embedding),
       fetchKnowledgeBase(definitionId, embedding)
     ])
  │
  └─ Format 4 sections → return markdown
```

### Backward Compatibility

All 5 individual tools remain available and unchanged. The `assemble_context` tool is additive — existing integrations continue to work. Individual tools are useful for:
- Debugging specific layers in isolation
- Selective context assembly (e.g., persona-only for lightweight interactions)
- Testing framework/KB matching independently

---

## Verification

- [ ] `assemble_context` returns all 4 layers in structured markdown
- [ ] Individual tools (`get_agent_persona`, `get_active_memory`, `select_framework`, `search_knowledge_base`) still work independently
- [ ] Prompt template calls `assemble_context` instead of 4 tools
- [ ] Embedding failure degrades gracefully (framework + KB show error, persona + memory still return)
- [ ] Agent resolution failure throws descriptive error
- [ ] End-to-end test via Cowork `/nate` invocation
