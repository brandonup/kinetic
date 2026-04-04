# Kinetic Brain — Deployment Guide

How to build and deploy the Kinetic Brain MCP server so that `/nate` works in Cowork with live Supabase data.

---

## Prerequisites

- Python 3.11+
- A Kinetic Supabase project with agent data (persona, frameworks, KB chunks)
- An OpenAI API key (for `text-embedding-3-large` embeddings)
- Claude Desktop app (Cowork mode)

---

## Step 1: Set up the Python environment

Open Terminal and run:

```bash
cd ~/son_of_anton/projects/kinetic/packages/mcp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs `mcp`, `supabase`, `openai`, and `pydantic` into an isolated virtualenv.

---

## Step 2: Gather your credentials

You need 6 values. Here's where to find each one:

| Variable | Where to find it |
|----------|-----------------|
| `SUPABASE_URL` | Supabase dashboard > Project Settings > API > Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard > Project Settings > API > `service_role` key (not `anon`) |
| `OPENAI_API_KEY` | OpenAI dashboard > API keys |
| `NATE_AGENT_ID` | Supabase > Table Editor > `agent_definitions` > find the Nate row > copy the `id` column (UUID format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) |
| `NATE_INSTANCE_ID` | Supabase > Table Editor > `agent_instances` > find the row matching your agent + user > copy its `id` |
| `KINETIC_USER_ID` | Supabase > Table Editor > `profiles` > your user row > copy its `id` |

**Important:** `NATE_AGENT_ID` must be a UUID from the `agent_definitions` table, not an MCP hash or any other format.

---

## Step 3: Verify the server starts

Test the server in your terminal before configuring Cowork. In the same terminal where you activated the venv:

```bash
SUPABASE_URL="your-url" SUPABASE_SERVICE_ROLE_KEY="your-key" OPENAI_API_KEY="your-key" NATE_AGENT_ID="your-uuid" NATE_INSTANCE_ID="your-uuid" KINETIC_USER_ID="your-uuid" python ~/son_of_anton/projects/kinetic/packages/mcp/server.py
```

Replace each value with your actual credentials. Put them all on one line.

- **If the terminal hangs with no output** — the server started successfully. Press `Ctrl+C` to stop it.
- **If you see `RuntimeError: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set`** — the env vars didn't reach Python. Make sure the values are not empty and are on the same line as the `python` command.

---

## Step 4: Ensure Supabase RPC functions exist

The MCP server calls two Supabase RPC functions for vector search. If they don't exist, `select_framework` and `search_knowledge_base` will fail.

Go to your Supabase dashboard > **SQL Editor** and run each of these:

### 4a: Framework trigger matching

```sql
CREATE OR REPLACE FUNCTION public.match_framework_triggers(
  query_embedding extensions.vector(3072),
  p_agent_id uuid,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  framework_db_id uuid,
  trigger_text text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  RETURN QUERY
  SELECT
    fte.framework_db_id,
    fte.trigger_text,
    1 - (fte.embedding <=> query_embedding) AS similarity
  FROM public.framework_trigger_embeddings fte
  WHERE fte.agent_definition_id = p_agent_id
  ORDER BY fte.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

### 4b: Knowledge base chunk matching

```sql
CREATE OR REPLACE FUNCTION public.match_chunks(
  query_embedding extensions.vector(3072),
  scope_column text,
  scope_value text,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  document_title text,
  section_path text,
  text text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
BEGIN
  RETURN QUERY EXECUTE format(
    'SELECT c.id, d.title AS document_title, c.section_path, c.text,
            1 - (c.embedding <=> $1) AS similarity
     FROM public.knowledge_base_chunks c
     JOIN public.knowledge_base_documents d ON d.id = c.document_id
     WHERE c.%I = $2
     ORDER BY c.embedding <=> $1
     LIMIT $3',
    scope_column
  )
  USING query_embedding, scope_value::uuid, match_count;
END;
$$;
```

**Note on vector types:** Supabase stores the pgvector extension in the `extensions` schema. Both functions must use `extensions.vector(3072)` (not `vector(3072)`) and include `SET search_path = public, extensions`. Without this, you'll get `operator does not exist: extensions.vector <=> extensions.vector`.

---

## Step 5: Configure the MCP server in Cowork

This is the step that connects the server to Cowork. Do not use Cowork's "Custom Connectors" feature — that requires a remote HTTPS URL with OAuth and does not work for local servers.

### 5a: Open the config file

In the Claude Desktop app: **Settings > Developer** (under the "Desktop app" section at the bottom of the sidebar) > click **Edit Config**.

This opens the file at:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

### 5b: Add the MCP server entry

Add a `mcpServers` section with your credentials. If the file already has content, merge the `mcpServers` key into the existing JSON.

```json
{
  "mcpServers": {
    "kinetic-brain": {
      "command": "/Users/YOUR_USERNAME/son_of_anton/projects/kinetic/packages/mcp/.venv/bin/python",
      "args": ["/Users/YOUR_USERNAME/son_of_anton/projects/kinetic/packages/mcp/server.py"],
      "env": {
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "your-service-role-key",
        "OPENAI_API_KEY": "your-openai-key",
        "NATE_AGENT_ID": "your-agent-uuid",
        "NATE_INSTANCE_ID": "your-instance-uuid",
        "KINETIC_USER_ID": "your-user-uuid"
      }
    }
  }
}
```

**Important:**
- The `command` path must point to the Python binary **inside the virtualenv** (`.venv/bin/python`), not the system Python. This ensures the MCP dependencies are available.
- Replace `YOUR_USERNAME` with your actual macOS username.
- All 6 env var values must be filled in.

### 5c: Restart Cowork

Quit Cowork completely (`Cmd+Q`) and reopen it. The server will appear under **Customize > Connectors > Desktop** as `kinetic-brain` with the label `LOCAL DEV`.

### 5d: Verify the tools loaded

Click on `kinetic-brain` in the Connectors panel. You should see the tools:
- Get Agent Persona
- Get Active Memory
- Select Framework
- Search Knowledge Base
- Assemble Context

If the server doesn't appear or shows an error, check:
1. The Python path is correct and the venv has the packages installed
2. The env var values are not empty
3. The `server.py` path is correct

---

## Step 6: Create the `/nate` skill in Cowork

The MCP server provides the tools, but you also need a skill that tells Claude how to use them.

### 6a: Open the skill editor

In Cowork: **Customize > Skills > click the + button > Write skill instructions**

### 6b: Fill in the fields

**Name:** `nate`

**Description:**
```
Invoke Nate B. Jones as an expert AI advisor for strategic reasoning about AI strategy, competitive positioning, product decisions, or technology adoption.
```

**Instructions:** Paste the full content of the `/nate` skill instructions.

### 6c: Save

The skill is now available as `/nate` in any Cowork chat.

---

## Step 7: Test the full pipeline

Start a new chat in Cowork and type:

```
/nate How should I think about pricing for an AI-powered SaaS?
```

Expand the "Used kinetic-brain integration, loaded tools" section to verify the tools returned data:

| Tool | Expected result |
|------|----------------|
| `get_agent_persona` | Nate's full system prompt (starts with "# Nate B Jones") |
| `get_active_memory` | "No active memories" (normal for first use) or memory entries |
| `select_framework` | A matched framework with principles and steps, or "No matching framework found" |
| `search_knowledge_base` | KB chunks with relevance scores and source titles |

If a tool returns an error, check:
- **"agent not configured"** — `NATE_AGENT_ID` is empty or missing from the config
- **"invalid input syntax for type uuid"** — The ID value is not in UUID format
- **"column does not exist"** — The Supabase table schema doesn't match the code's expectations. Check table/column names.
- **"operator does not exist: extensions.vector"** — The RPC functions need `SET search_path = public, extensions` (see Step 4)
- **"Could not find the function"** — The RPC function hasn't been created yet (see Step 4)

---

## Architecture

```
User types /nate in Cowork
        |
        v
+-------------------+
|  /nate Skill      |  Tells Claude to call tools,
|  (in Cowork)      |  adopt Nate's persona, reason with context
+--------+----------+
         | calls tools
         v
+---------------------------------------+
|  kinetic-brain MCP Server (server.py) |
|  packages/mcp/server.py              |
|                                       |
|  get_agent_persona --> agent_definitions
|  get_active_memory --> active_memory
|  select_framework  --> framework RPCs
|  search_knowledge_base --> KB RPCs
|  assemble_context  --> all of the above
+--------+------------------------------+
         | Supabase client (service role)
         v
+-------------------+
|   Supabase        |
|   (Kinetic DB)    |
+-------------------+
```

The MCP server runs locally via stdio. Cowork launches it automatically when a chat starts, using the config in `claude_desktop_config.json`. No separate server process needs to be running.

---

## Troubleshooting

**Server doesn't start:**
- Check that the venv Python path in `claude_desktop_config.json` is correct
- Verify packages are installed: `source .venv/bin/activate && pip list | grep mcp`

**Tools return errors in Cowork but server works standalone:**
- The Desktop config may have different env var values than what you tested with
- Open `~/Library/Application Support/Claude/claude_desktop_config.json` and verify all 6 values

**"No matching framework found" every time:**
- Check that `framework_trigger_embeddings` table has rows for your agent ID
- The confidence gate is 0.55 — triggers below this threshold are filtered out

**KB search returns empty:**
- Check that `knowledge_base_chunks` and `knowledge_base_documents` tables have data
- Verify the chunks have an `agent_definition_id` column matching your agent UUID
