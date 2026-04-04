# Kinetic Brain — Local MCP Server

A local MCP server that connects Claude (Cowork/Desktop) to Kinetic's Supabase backend, assembling a rich context stack — persona, active memory, frameworks, and knowledge base — for the Nate B. Jones AI advisor.

## What it does

When you type `/nate` in a Cowork chat, the system:

1. Calls MCP tools against Kinetic's Supabase
2. Assembles Nate's persona, memory, best-matching framework, and relevant KB chunks
3. Claude adopts Nate's persona and reasons with the full context stack

## How it works

Two components work together:

- **MCP server** (`server.py`) — A Python stdio server that Claude Desktop launches automatically. Provides read-only tools that query Supabase.
- **`/nate` skill** — Created directly in Cowork via Customize > Skills. Tells Claude how to call the tools, adopt the persona, and reason with the assembled context.

The MCP server is configured in Claude Desktop's `claude_desktop_config.json` under the Desktop > Developer settings. It runs locally — no remote deployment needed.

## Tools

| Tool | Kinetic Layer | What it returns |
|------|--------------|-----------------|
| `get_agent_persona` | L5 | Nate's system prompt from `agent_definitions` |
| `get_active_memory` | L6 | Recent memory entries from `active_memory_entries` |
| `select_framework` | L7 | Best-matching framework via embedding similarity + multi-trigger boost |
| `search_knowledge_base` | L9 | Relevant KB chunks via vector search on `knowledge_base_chunks` |
| `assemble_context` | All | Single-call context assembly: persona + memory + framework + KB |

## Setup

Full step-by-step instructions: **[docs/deployment-guide.md](docs/deployment-guide.md)**

Quick summary:

1. Create a Python venv and install dependencies
2. Gather 6 credentials from Supabase and OpenAI
3. Verify the server starts locally
4. Create two Supabase RPC functions (`match_framework_triggers`, `match_chunks`)
5. Add the MCP server to `~/Library/Application Support/Claude/claude_desktop_config.json`
6. Create the `/nate` skill in Cowork via Customize > Skills > Write skill instructions
7. Test with `/nate` in a Cowork chat

## Credentials

| Variable | Where to find it |
|----------|-----------------|
| `SUPABASE_URL` | Supabase > Project Settings > API > Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase > Project Settings > API > `service_role` key |
| `OPENAI_API_KEY` | OpenAI dashboard > API keys |
| `NATE_AGENT_ID` | Supabase > Table Editor > `agent_definitions` > Nate's `id` (must be UUID) |
| `NATE_INSTANCE_ID` | Supabase > Table Editor > `agent_instances` > matching row `id` |
| `KINETIC_USER_ID` | Supabase > Table Editor > `profiles` > your `id` |

## Architecture

```
User types /nate in Cowork
        |
        v
+-------------------+
|   /nate Skill     |  Orchestrates tool calls,
|   (in Cowork)     |  persona adoption, layered reasoning
+--------+----------+
         | calls tools
         v
+---------------------------------------+
|  kinetic-brain MCP Server (stdio)     |
|  server.py — launched by Claude       |
|                                       |
|  get_agent_persona --> agent_definitions
|  get_active_memory --> active_memory_entries
|  select_framework  --> match_framework_triggers RPC
|  search_knowledge_base --> match_chunks RPC
|  assemble_context  --> all of the above
+--------+------------------------------+
         | Supabase client (service role)
         v
+-------------------+
|    Supabase       |
|   (Kinetic DB)    |
+-------------------+
```

## File structure

```
packages/mcp/
├── docs/
│   └── deployment-guide.md      # Full setup instructions
├── server.py                    # Python MCP server
├── requirements.txt             # mcp, supabase, openai, pydantic
├── .mcp.json                    # MCP server config
├── .claude-plugin/
│   └── plugin.json              # Plugin metadata
└── README.md
```

## Key technical details

- **Embedding model:** `text-embedding-3-large` (3072 dimensions)
- **Framework selection:** Vector search on trigger phrases > group by framework > multi-trigger boost (+0.05 per additional trigger) > confidence gate (0.55)
- **KB retrieval:** Vector search > similarity threshold (0.3) > top 8 results
- **Vector schema:** Supabase stores pgvector in the `extensions` schema. RPC functions must use `extensions.vector(3072)` and `SET search_path = public, extensions`
- **Client init:** Module-level globals (not FastMCP lifespan pattern) for compatibility with `mcp` v1.26.0+
