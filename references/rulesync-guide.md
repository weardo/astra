# Rulesync Guide

Generates 25+ tool-specific context files from one source. One set of rules → CLAUDE.md, .cursorrules, GEMINI.md, .windsurfrules, .clinerules, .github/copilot-instructions.md, and more.

## Installation

```bash
npm install -g rulesync
```

## Workflow

```bash
# 1. Initialize (creates .rulesync/ directory)
rulesync init

# 2. Import existing CLAUDE.md rules as starting point
rulesync import --from claudecode

# 3. Write rules in .rulesync/rules/*.md
# 4. Generate all tool-specific files
rulesync generate

# 5. Add generated files to .gitignore (optional, recommended)
rulesync gitignore
```

## Directory Structure

```
.rulesync/
├── config.yaml        # rulesync configuration
└── rules/
    ├── universal.md   # applies to all tools (targets: ["*"])
    ├── claude.md      # Claude Code only (targets: ["claudecode"])
    └── cursor.md      # Cursor only (targets: ["cursor"])
```

## Rule Frontmatter

Each rule file uses YAML frontmatter to specify targets:

```markdown
---
targets: ["*"]         # universal — all tools
description: "Core coding rules"
---

- Never use console.log in production code
- Always write tests before implementation
```

```markdown
---
targets: ["claudecode"]   # Claude Code only
description: "Claude-specific session rules"
---

- Compact at 30% context remaining
- Use /implement skill for TDD sessions
```

## Supported Targets (25+)

`claudecode`, `cursor`, `windsurf`, `cline`, `codex`, `gemini`, `copilot`, `aider`, `continue`, `devin`, `openai-codex`, `roomodes`, `bolt`, `lovable`, `v0`, `zed`, `vscode`, `jetbrains`, `amp`, `goose`, `agentflow`, `mcp`, `claude-desktop`, `jules`, `tabnine`

## Gotchas

- Target-specific rules via `targets: ["claudecode"]` — these go ONLY to Claude Code
- Universal rules via `targets: ["*"]` — safe for all tools (no Claude Code-specific syntax)
- `rulesync import --from claudecode` reads existing CLAUDE.md and creates universal equivalents
- Generated files go to project root — each tool reads its own file automatically
- Run `rulesync generate` again after editing rules (not automatic)
- `rulesync gitignore` adds generated tool files to `.gitignore` (if you don't want to commit them)

## Integration with Bootstrap

When running bootstrap Phase 5 (rulesync):
1. `check-rulesync.sh` verifies rulesync is installed
2. If installed: `rulesync init`, then `rulesync import --from claudecode`, then `rulesync generate`
3. This creates baseline rules from any existing CLAUDE.md content
4. User can then add project-specific rules in `.rulesync/rules/`
