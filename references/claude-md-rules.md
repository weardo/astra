# CLAUDE.md Rules Catalog

Binary rules for generating CLAUDE.md. Every rule is imperative and unambiguous.

## Required Sections (always include)

1. **Tech Stack table** — Component | Technology | Location columns
2. **Build & Test commands** — exact shell commands, copy-paste ready
3. **AI Workflow section** — session lifecycle + compact rule + bug fix policy
4. `@AGENTS.md` import at end of file

## Hard Limits

- NEVER exceed 200 lines total
- NEVER include naming conventions (→ put in AGENTS.md)
- NEVER include architecture diagrams (→ put in AGENTS.md or docs/)
- NEVER include API documentation (→ link to docs/)
- ALWAYS use binary rules ("NEVER use console.log") not adjective guidelines ("avoid console.log where possible")

## Context Management Rules (always include)

```
## Context Window Management (MANDATORY)
1. Compact at 30% remaining — run /compact proactively
2. Use subagents for research/exploration to keep main context clean
3. Don't load what you don't need — read MEMORY.md "Read When" first
4. Session boundaries = git commits — commit and start fresh rather than exhausting context
5. NEVER run past 90% context — output quality degrades
```

## Workflow Rules (always include)

```
## Development Workflow (MANDATORY)
Follow: Explore → Plan → Implement → Commit
- NEVER write code before exploring existing patterns (grep/read first)
- NEVER skip planning for tasks touching more than 2 files
- ALWAYS run tests after every implementation change
- Atomic commits: each commit = one working, tested change
```

## Bug Fix Policy (always include)

```
## Bug Fix Policy (MANDATORY)
Every bug fix must include a test that:
- Fails before the fix
- Passes after the fix
NEVER mark a bug as fixed without a test proving it.
```

## Conditional Rules (driven by insights friction)

Apply these based on `read-insights.sh` output:

| Friction category | Threshold | Rule to inject |
|-------------------|-----------|----------------|
| `wrong_approach` | count > 2 | `IMPORTANT: Always explore codebase before writing code. Read existing patterns first.` |
| `context_exhaustion` | count > 2 | Front-load compact-at-30% with `YOU MUST` emphasis: `YOU MUST run /compact when context reaches 30% — do not wait.` |
| `buggy_code` | count > 2 | `NEVER skip writing tests. Every function gets a test before shipping.` |
| `wrong_file` | count > 1 | `ALWAYS read a file before editing it. No blind edits.` |
| `missed_pattern` | count > 1 | `ALWAYS grep for existing implementations before creating new ones.` |
| CI detected in infra | any | `Run tests before every commit. CI will reject untested changes.` |

## Stack-Specific Additions

**Node/TypeScript:**
- Add: `NEVER use console.log in production code — use structured logging`
- Add: TypeScript strict mode reminder if `tsconfig.json` has `strict: true`

**Python:**
- Add: `NEVER import * — always explicit imports`
- Add: Type hints required if `pyproject.toml` has mypy config

**Go:**
- Add: `ALWAYS handle errors explicitly — never use _ for errors`
- Add: `gofmt -w` in build commands

## Smart Merge Protocol

When existing CLAUDE.md found:
1. `missing` (no file) → generate from scratch
2. `identical` (SHA matches template) → skip, no changes
3. `different` → show 3-line diff summary, ask "update / keep"
   - In headless mode: NEVER overwrite existing CLAUDE.md without confirmation
   - When updating: inject insights rules + preserve existing custom sections
