# AGENTS.md Specification — TechSpokes v3.0

Standard by TechSpokes (github.com/TechSpokes/agency-specifications-files-agents-md). Discovered via OpenAI Codex discovery rules. 40k+ repos.

## Hard Limits (STRICT — never violate)

- NEVER exceed 100 lines total
- NEVER use bold (`**text**`) or italic (`*text*`)
- NEVER use nested lists (no indented bullets)
- NEVER use emojis
- NEVER use triple-dash section dividers (`---`)
- ALWAYS use dashes for list items (not asterisks `*`)
- ALWAYS write rules in imperative voice ("Do X", "Never Y")
- ALWAYS keep rule items ≤ 120 characters each

## Required Sections (7, in this exact order)

### 1. `# Agent Instructions for {ProjectName} – {purpose}`
First line of the file. `{purpose}` is a short noun phrase (e.g., "TypeScript REST API"). No content below this line.

### 2. `## Summary`
- 1-3 sentences describing what the project does
- Include read-depth guidance: "Scan Summary+Must-follow for quick context. Read all sections for full agent setup."
- Agents use this to decide how deeply to read the file

### 3. `## Must-follow rules`
- Flat dash list (no nesting)
- Imperative rules only
- Maximum 10 rules
- Each rule ≤ 120 characters
- Examples:
  - `- Never modify files outside the project directory`
  - `- Run tests before marking any task complete`
  - `- Use existing patterns before creating new abstractions`

### 4. `## Must-read documents`
- Flat dash list of files the agent must read before working
- Include relative paths: `- CLAUDE.md — project conventions and commands`
- Include key reference files: `- docs/reference/MEMORY.md — navigation index`

### 5. `## Agent guidelines`
- Behavioral rules beyond the must-follows
- Style preferences, communication patterns
- Flat dash list, imperative

### 6. `## Context`
- Project background: purpose, users, key constraints
- Technology decisions that affect agent behavior
- What NOT to change (stability zones)

### 7. `## References`
- External documentation links
- Related specs or standards documents
- Flat dash list: `- [Name](URL) — description`

## Generation from Detection

Map detect.sh output to AGENTS.md content:

| Detection | AGENTS.md content |
|-----------|------------------|
| `stack: ["typescript"]` | Add TypeScript conventions to guidelines |
| `infra: ["docker"]` | Add Docker build constraints to must-follow |
| `infra: ["github-actions"]` | Add CI rules (run tests, don't skip checks) |
| `existing.claudeMd: true` | Reference CLAUDE.md in must-read documents |
| `existing.goalMd: true` | Reference GOAL.md in must-read documents |
| `size: "brownfield"` | Add "Use existing patterns" must-follow rule |

## Avoiding CLAUDE.md Duplication

AGENTS.md is for multi-tool context (Cursor, Codex, Gemini, Cline).
CLAUDE.md is for Claude Code-specific behavior.

- DO NOT repeat CLAUDE.md commands in AGENTS.md
- DO reference CLAUDE.md as a must-read document
- AGENTS.md covers: project purpose, coding standards, file structure, API contracts
- CLAUDE.md covers: Claude Code commands, MCP tools, session lifecycle, context rules
