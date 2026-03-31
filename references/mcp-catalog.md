# MCP Server Catalog

Curated servers per stack. Transport rule: ALWAYS use `stdio` for local, `http` for remote. NEVER use `sse` for new integrations (deprecated).

## Always Recommended

| Server | Package | Purpose |
|--------|---------|---------|
| `sequential-thinking` | `@anthropic-ai/claude-code-mcp-sequential-thinking` | Structured reasoning chains |

## Stack Triggers

| Detection | Server | Package |
|-----------|--------|---------|
| any git repo | `git` | `@modelcontextprotocol/server-git` |
| `GITHUB_TOKEN` in env | `github` | `@modelcontextprotocol/server-github` |
| node/typescript | `filesystem` | `@modelcontextprotocol/server-filesystem` |
| python | `filesystem` | `@modelcontextprotocol/server-filesystem` |
| python | `fetch` | `@modelcontextprotocol/server-fetch` |
| web/react/next | `playwright` | `@playwright/mcp` |
| sqlite detected | `sqlite` | `@modelcontextprotocol/server-sqlite` |

## .mcp.json Format

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@package/name", "--arg"],
      "transport": "stdio",
      "env": {
        "ENV_VAR": ""
      }
    }
  }
}
```

- `transport: "stdio"` for local servers (default, omit if possible)
- `transport: "http"` for remote Streamable HTTP servers
- NEVER use `transport: "sse"` for new servers (SSE is deprecated)

## MCP Scope Terms (changed in 2026)

| Term | Where stored | Who sees it |
|------|-------------|-------------|
| `local` | `~/.claude.json` | You only, this project |
| `project` | `.mcp.json` | Team (committed to git) |
| `user` | `~/.claude.json` | You only, all projects |

Bootstrap generates `.mcp.json` → team-shared project scope.

## Install Commands

```bash
# sequential-thinking
npx -y @anthropic-ai/claude-code-mcp-sequential-thinking

# filesystem
npx -y @modelcontextprotocol/server-filesystem /path/to/allow

# github (requires GITHUB_TOKEN)
npx -y @modelcontextprotocol/server-github

# playwright (web testing)
npx -y @playwright/mcp

# sqlite
npx -y @modelcontextprotocol/server-sqlite /path/to/db.sqlite
```

## Smart Merge Protocol

When `.mcp.json` already exists:
- NEVER remove existing server entries
- Add new servers only (append)
- If server name conflicts: warn user, skip

## Registry Query (Optional)

If network available, query for additional matches:
```
GET https://registry.modelcontextprotocol.io/v0.1/servers?q={stack}
```
Fall back to catalog-only if unreachable. Log whether registry was queried in checkpoint.
