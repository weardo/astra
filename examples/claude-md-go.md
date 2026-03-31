# Project Name — Go

Brief description of what this project does.

## Tech Stack

| Component | Technology | Location |
|-----------|-----------|----------|
| Service | Go | `cmd/`, `internal/` |
| Tests | go test | `*_test.go` |
| Build | go build | `bin/` |

## Build & Test

```bash
go build ./...
go test ./...
gofmt -w .
```

## AI Workflow (MANDATORY)

Follow: Explore → Plan → Implement → Commit

### Context Window Management
1. Compact at 30% remaining — run `/compact` proactively
2. Session boundaries = git commits
3. NEVER run past 90% context

### Development Rules
- NEVER write code before reading existing patterns (grep first)
- ALWAYS handle errors explicitly — never use `_` to discard errors
- ALWAYS run `go test ./...` after every change
- ALWAYS run `gofmt -w .` before committing

### Bug Fix Policy
Every bug fix must include a test that fails before the fix, passes after.

<!-- INSIGHTS-DRIVEN RULES: bootstrap-project injects personalized rules here -->

@AGENTS.md
