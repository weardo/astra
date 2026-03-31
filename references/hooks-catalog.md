# Hooks Catalog

## All 21 Hook Events (5 categories)

### Session (2)
- `SessionStart` — fires when Claude Code session begins
- `SessionStop` — fires when session ends normally

### Tool (2)
- `PreToolUse` — fires before any tool call (can block with exit 1 or 2)
- `PostToolUse` — fires after any tool call completes

### Agent (3)
- `SubagentStart` — fires when a subagent session begins
- `SubagentStop` — fires when a subagent session ends
- `PreAgentSpawn` — fires before spawning a new agent (can block)

### Isolation / Worktree (4)
- `PreWorktreeCreate` — fires before creating a git worktree
- `PostWorktreeCreate` — fires after worktree is created
- `PreWorktreeDelete` — fires before deleting a worktree
- `PostWorktreeDelete` — fires after worktree deletion

### MCP (3)
- `PreMcpToolUse` — fires before any MCP tool call
- `PostMcpToolUse` — fires after MCP tool call
- `Elicitation` — fires when Claude requests additional information

### Failure (1)
- `StopFailure` — fires when turn ends due to API error (rate limit, auth) [v2.1.78+]

*Note: Some community docs cite fewer events — official count is 21 (March 2026).*

## Hook Types

| Type | Description |
|------|-------------|
| `command` | Shell script or command to run |
| `intercept` | Reads stdin, can modify tool input |
| `notification` | Fires but cannot block |
| `validation` | Returns allow/deny decision |

## Exit Codes

| Code | Effect |
|------|--------|
| `0` | Proceed normally |
| `1` | Block + show stderr message to user |
| `2` | Block silently (no message) |

## settings.json Format

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{ "type": "command", "command": "/path/to/hook.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{ "type": "command", "command": "/path/to/hook.sh" }]
      }
    ]
  }
}
```

Matcher supports: exact tool name (`Write`), pipe-separated (`Write|Edit`), wildcard (`*`).

## BREAKING Changes

- **v2.1.77:** `PreToolUse "allow"` return no longer bypasses `deny` rules — `deny` takes precedence
- **v2.1.77:** Agent tool `resume` parameter removed
- **v2.1.78:** `deny` now strips tools from model view (not just execution block)
- **v2.1.78:** `StopFailure` hook event added

## Bootstrap Asset Hooks

| Hook | Event | Matcher | Purpose |
|------|-------|---------|---------|
| `path-guard.sh` | PreToolUse | Write | Block writes to wrong directories |
| `lint-runner.sh` | PostToolUse | Write\|Edit | Auto-detect + run linter |
| `test-runner.sh` | PostToolUse | Write\|Edit | Auto-detect + run tests |
| `format-runner.sh` | PostToolUse | Write\|Edit | Auto-detect + run formatter |

## Selection Logic

- `path-guard` — always recommend for brownfield projects
- `lint-runner` — if ESLint, ruff, or golangci-lint detected
- `test-runner` — if test framework detected (vitest, jest, pytest, go test)
- `format-runner` — if prettier, black, or gofmt config detected
- Insights `prioritizedHooks` — override with friction-driven recommendations

## Installation

Use `install-hooks.sh` (Phase 2 script) — handles copy + settings.json merge automatically.
