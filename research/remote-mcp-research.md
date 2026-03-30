# Remote MCP Server Hosting & Deployment Patterns

**Research date:** 2026-03-29
**Query:** How do SaaS products deploy MCP servers for remote access? Transport protocols, auth patterns, discovery, and real-world examples.

---

## 1. Transport Protocol: Streamable HTTP

**Streamable HTTP** is the standard transport for remote MCP servers, introduced in the March 2025 MCP specification revision. It replaced the earlier SSE (Server-Sent Events) transport, which is now deprecated.

### How it works
- The MCP server runs as an independent HTTP service (not a child process)
- Clients communicate via HTTP POST (for requests) and GET (for server-initiated events)
- Supports multiple concurrent client connections
- The protocol itself is stateless, but applications can build stateful sessions on top (similar to how HTTP uses cookies)

### Current limitations (surfaced at scale)
- Stateful sessions conflict with load balancers
- Horizontal scaling requires workarounds
- No standard way for registries/crawlers to discover server capabilities without connecting

### 2026 roadmap
- Cookie-like session mechanism to decouple state from transport
- Finalization of related SEPs targeted for June 2026 spec release
- Server Cards for static capability advertisement

### Transport comparison

| Transport | Use case | Status |
|-----------|----------|--------|
| **stdio** | Local tools needing system access | Active, primary for local |
| **SSE** | Legacy remote connections | **Deprecated** |
| **Streamable HTTP** | Remote servers, cloud deployment | **Current standard** |

---

## 2. Authentication Patterns

### OAuth 2.1 (spec-mandated for public remote servers)

The MCP spec (November 2025 revision) **mandates OAuth 2.1 + PKCE** for public-facing remote MCP servers.

**Standard flow:**
1. Client calls MCP endpoint without a token
2. Server returns `401` with `WWW-Authenticate` header pointing to Protected Resource Metadata (RFC 9728)
3. Client discovers the authorization server from that metadata
4. Client runs OAuth 2.1 Authorization Code flow with PKCE
5. Client retries MCP call with the obtained access token
6. Server enforces audience and scopes

**Key spec requirements:**
- PKCE is non-negotiable for all clients
- All endpoints must be HTTPS
- Protected Resource Metadata (RFC 9728) is required for auth server discovery
- Client ID Metadata Documents (CIMD) are the standard registration method (November 2025)

### Alternative patterns (internal/private servers)

| Pattern | When to use |
|---------|-------------|
| **Bearer token / API key** | Internal tools, private servers, trusted environments |
| **Cloudflare Access** | Teams already on Cloudflare, internal tools |
| **OAuth 2.1** | Public-facing SaaS MCP servers (spec-mandated) |

### Security notes
- November 2025 spec update added explicit security guidance after vulnerabilities were discovered in authorization URL handling
- Authorization URLs must be validated carefully to prevent redirect attacks

---

## 3. Client Connection Patterns

### Claude Code
- Supports **stdio**, **SSE** (deprecated), and **Streamable HTTP** transports natively
- Can connect to both local and remote MCP servers directly

### Claude Desktop
- Primarily uses **stdio** (launches MCP servers as child processes)
- Remote server support via **Integrations** on Pro, Max, Team, and Enterprise plans
- For other cases, a local proxy server (stdio to HTTP bridge) can be used
- With Anthropic's Integrations feature, remote MCP servers work like websites: type a URL and connect

### Other clients
- VS Code / Cursor: Support remote HTTP connections; VS Code added "Install" buttons for one-click MCP server setup
- Copilot: Supports remote MCP via GitHub's own MCP server infrastructure

---

## 4. Discovery & Registry

### Official MCP Registry
- Available at **registry.modelcontextprotocol.io**
- Open catalog and API for publicly available MCP servers
- Does not host code -- stores metadata describing where to find servers and how to install them

### Server Discovery via `.well-known`

Two active Spec Enhancement Proposals:

**SEP-1649: Server Cards**
- Servers expose `/.well-known/mcp/server-card.json`
- Structured metadata document advertising capabilities, transport config, and available tools
- Enables browsers, crawlers, and registries to discover capabilities without connecting

**SEP-1960: Discovery Endpoint**
- Standardized `/.well-known/mcp` endpoint
- Server metadata discovery, capability advertisement, and security policy declaration

**Status:** Both SEPs have broad community support and are actively being implemented (as of March 2026). The Server Card WG and Transports WG own this work.

### Auto-discovery examples
- **Replicate** (February 2026): Implemented MCP server auto-discovery
- **Azure API Center**: Register and discover MCP servers within API inventory

### Simplified setup patterns
- **`mcp.json` / `server.json`**: Configuration files that specify server connection details (URL for HTTP, command/args for stdio)
- **One-click install**: VS Code supports "Install" buttons; Cloudflare offers "Deploy to Workers" buttons
- **Integrations**: Claude Desktop's Integrations feature lets users connect to remote MCP servers by URL (no local setup)

---

## 5. Deployment Infrastructure

### Cloudflare Workers (dominant platform)
- **First platform to support remote MCP server deployment** (GA April 7, 2025)
- Edge deployment -- servers run in data centers closest to users worldwide
- No cold start problem
- Built-in OAuth Provider Library for auth
- Two deployment paths:
  - **One-click "Deploy to Workers"** button (creates repo with CI/CD)
  - **Wrangler CLI** for more control

### Cloudflare MCP Demo Day participants
Built remote MCP servers on Cloudflare:
- Anthropic, Asana, Atlassian, Block, Intercom, Linear, PayPal, Sentry, Stripe, Webflow

### Other hosting options
- **Vercel**: Serverless MCP server hosting
- **Northflank**: Container-based MCP deployment
- **Azure**: ACA (Azure Container Apps) with OAuth 2.1 + Azure AD
- **Self-hosted**: Any HTTP server that implements the Streamable HTTP transport

---

## 6. SaaS Companies Shipping Remote MCP Servers

### Tier 1: Full remote MCP with OAuth

| Company | Capabilities | Notes |
|---------|-------------|-------|
| **Stripe** | Balances, customers, invoices, subscriptions, payment activity | Agents interact with real revenue data |
| **Linear** | Issues, projects, comments (find/create/update) | Remote server hosted and managed by Linear; tooling tuned for agent workflows |
| **Notion** | Pages, databases, comments (read) | Gives AI organizational memory |
| **Sentry** | Error monitoring, issue management | Built on Cloudflare |
| **Webflow** | Site management, CMS operations | Built on Cloudflare |
| **Asana** | Project/task management | Built on Cloudflare |
| **Atlassian** | Jira, Confluence integration | Built on Cloudflare |
| **PayPal** | Payment operations | Built on Cloudflare |
| **Intercom** | Customer messaging | Built on Cloudflare |
| **Block** | Financial services | Built on Cloudflare |

### Tier 2: Official MCP servers (may be local or remote)

| Company | Capabilities |
|---------|-------------|
| **GitHub** | Repos, issues, PRs, actions |
| **Slack** | Messaging, channels |
| **Google** | Drive, Docs, various APIs |
| **Salesforce** | CRM operations |
| **HubSpot** | Marketing/sales automation |
| **Shopify** | E-commerce operations |
| **Figma** | Design file access |
| **Postman** | API testing/documentation |

### Key pattern
The trend is moving from local stdio servers (user installs and runs) to **remote hosted servers** (vendor hosts, user connects via URL + OAuth). Linear's approach -- a hosted remote server managed by the vendor -- is becoming the standard model for SaaS MCP.

---

## 7. Key Takeaways for Kinetic

1. **Streamable HTTP is the only forward-looking transport** for remote MCP. SSE is deprecated, stdio is local-only.

2. **OAuth 2.1 + PKCE is non-negotiable** for public-facing remote MCP servers per spec. For internal/private use, Bearer tokens are acceptable.

3. **Cloudflare Workers is the dominant deployment platform** for remote MCP. Edge deployment, built-in OAuth provider, and one-click deploy make it the path of least resistance.

4. **Server Cards (`.well-known/mcp/server-card.json`) are coming** but not yet finalized. Publishing one early would put Kinetic ahead of most servers on discoverability.

5. **The SaaS model is converging**: vendor hosts the MCP server, user connects via URL + OAuth, no local installation required. This is how Linear, Stripe, and the Cloudflare Demo Day cohort all work.

6. **Claude Desktop Integrations** are the primary way non-technical users connect to remote MCP servers -- type a URL, authorize via OAuth, done.

---

## Sources

- [The 2026 MCP Roadmap](http://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
- [MCP Transports Specification (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Exploring the Future of MCP Transports](https://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/)
- [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [MCP Authorization Specification (Draft)](https://modelcontextprotocol.io/specification/draft/basic/authorization)
- [MCP OAuth 2.1 Complete Guide](https://dev.to/composiodev/mcp-oauth-21-a-complete-guide-3g91)
- [Remote MCP in the Real World: OAuth 2.1](https://medium.com/@yagmur.sahin/remote-mcp-in-the-real-world-oauth-2-1-9d149de6e475)
- [Cloudflare MCP Authorization](https://developers.cloudflare.com/agents/model-context-protocol/authorization/)
- [Microsoft: Building Secure MCP Server with OAuth 2.1 and Azure AD](https://devblogs.microsoft.com/ise/aca-secure-mcp-server-oauth21-azure-ad/)
- [Everything Your Team Needs to Know About MCP in 2026 (WorkOS)](https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026)
- [Cloudflare MCP Demo Day](https://blog.cloudflare.com/mcp-demo-day/)
- [Build and Deploy Remote MCP Servers to Cloudflare](https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/)
- [Introducing the MCP Registry](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)
- [Official MCP Registry](https://registry.modelcontextprotocol.io/)
- [SEP-1649: MCP Server Cards](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1649)
- [SEP-1960: .well-known/mcp Discovery Endpoint](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1960)
- [MCP Server Discovery: Implement .well-known/mcp.json](https://www.ekamoira.com/blog/mcp-server-discovery-implement-well-known-mcp-json-2026-guide)
- [Connect Claude Code to Tools via MCP](https://code.claude.com/docs/en/mcp)
- [Top 15 Remote MCP Servers (DataCamp)](https://www.datacamp.com/blog/top-remote-mcp-servers)
- [19,000 Companies Have a Docs MCP Server (Left Hook)](https://lefthook.com/blog/docs-mcp-servers-who-ships-them)
- [Cloudflare: One-Click Remote MCP Servers](https://community.cloudflare.com/t/introducing-one-click-remote-mcp-servers-with-cloudflare/795791)
