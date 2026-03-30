# Kinetic + /nate — Test Setup Guide

**For:** Testing the Kinetic Brain MCP connection in Cowork (Claude Desktop)

---

## What You'll Get

After setup, you'll be able to type `/nate` in any Cowork conversation and get responses from Nate B. Jones — an AI advisory persona powered by Kinetic's context engine. Nate draws on a curated knowledge base, diagnostic frameworks, and a system prompt to reason like a well-briefed strategic advisor.

---

## Before You Start

Brandon will create your Kinetic account and send you:
- **Your email and temporary password**
- These instructions

You'll need:
- **Claude Desktop** (Cowork) installed on your Mac
- **An OpenAI API key** — get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) if you don't have one. Kinetic uses this for embeddings (framework matching + KB search). Even $5 in credits will last a long time.

---

## Step 1: Log Into Kinetic

1. Open your browser and go to: **https://kinetic-production-b568.up.railway.app**
2. Log in with the email and password Brandon gave you
3. You should see the Kinetic dashboard

---

## Step 2: Add Your OpenAI API Key

Kinetic uses your own API key (BYOK) to run embeddings for framework selection and knowledge base search.

1. In Kinetic, go to **Profile** (click your avatar or name in the top-left)
2. Find the **API Keys** section
3. Add your **OpenAI API key**
4. Save

---

## Step 3: Generate an MCP Token

This token lets Cowork connect to your Kinetic account.

1. Still on the **Profile** page, find the **MCP Tokens** section
2. Click **Generate new token**
3. Give it a name (e.g., `cowork`)
4. The UI will show your **full connection URL** — click **Copy** to copy it
5. Save it somewhere safe (a text file, password manager, etc.) — the URL is only shown once

---

## Step 4: Connect Kinetic to Cowork

1. Open **Claude Desktop** (Cowork)
2. Go to **Settings** (gear icon, bottom-left) **→ Connectors**
3. Click **Add custom connector**
4. **Name:** `Kinetic`
5. **Remote MCP server URL:** paste the connection URL you copied in Step 3
6. Click **Add**

The `/nate` command will appear automatically — no additional setup needed.

---

## Step 5: Test It

1. Start a **new conversation** in Cowork
2. Type: `/nate How should I think about pricing for an AI-powered SaaS?`
3. You should see Cowork call 4 tools (expand "Used Kinetic integration" to verify):

| Tool | What it does |
|------|-------------|
| `get_agent_persona` | Loads Nate's personality and reasoning style |
| `get_active_memory` | Loads memory from prior conversations (empty on first use — normal) |
| `select_framework` | Finds a matching diagnostic framework for your question |
| `search_knowledge_base` | Retrieves relevant chunks from Nate's published writing |

4. Nate should respond in character — direct, opinionated, conclusion-first.

---

## Troubleshooting

**Connector doesn't show tools or /nate doesn't appear:**
- Remove the connector and re-add it
- Make sure the URL includes `?key=mcp_...` at the end (no extra spaces or line breaks)
- Quit Cowork completely (Cmd+Q) and reopen

**Tools return errors:**
- "Missing required parameter agent" → Start a fresh conversation and try again
- "No OpenAI API key configured" → Go back to Step 2 and add your key
- 401 / unauthorized → Your MCP token may be wrong. Generate a new one (Step 3)

**Nate responds generically (not in character):**
- Make sure `get_agent_persona` returned content (expand the tool call in the conversation)
- Try a more specific question — Nate is sharpest with concrete business/product scenarios

---

*Questions? Message Brandon.*
