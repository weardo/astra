---
name: astra-init
description: "Use when setting up a project for AI-driven development with astra. Detects stack, reads user insights, generates CLAUDE.md + AGENTS.md + GOAL.md + astra.yaml, installs hooks, skills, MCP servers, and agents. Do NOT use for ongoing development — use /astra-run instead."
user-invokable: true
argument-hint: "[project-path]"
---

# /astra-init — Project Setup

Initialize a project for AI-driven development with astra.

## Input

- `$ARGUMENTS` — optional project path (defaults to current directory)

## Steps

### 1. Resolve Project Directory

```
PROJECT_DIR = $ARGUMENTS or current working directory
cd $PROJECT_DIR
```

### 2. Run Stack Detection

Run the detection script to identify the project's stack, test command, build command, and structure.

```bash
bash ${CLAUDE_PLUGIN_ROOT}/src/scripts/detect.sh $PROJECT_DIR
```

Parse the JSON output into `detection.json`. Save to `${PROJECT_DIR}/.claude/detection.json`.

### 3. Read User Insights (optional)

If `~/.claude/usage-data/report.html` exists, extract friction patterns:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/src/scripts/read-insights.sh
```

Parse output into `insights.json`. These drive personalized CLAUDE.md rules.

### 4. Confirm With User

Present detected stack, test command, build command. Ask user to confirm or adjust.

**HITL Gate: confirm_detection** — User must confirm before generation proceeds.

### 5. Generate Config Files

Use Python generators to create files. For each file, use smart_merge to handle re-runs:

```python
from src.core.generators import generate_claude_md, generate_agents_md, generate_goal_md, generate_astra_yaml, smart_merge
```

Generate these files:
1. `CLAUDE.md` — stack-aware, ≤200 lines, with friction rules from insights
2. `AGENTS.md` — universal context for all AI tools
3. `GOAL.md` — mission + priorities + success criteria
4. `astra.yaml` — plugin configuration with detection defaults

For each:
- Call `smart_merge(path, content, hashes_path)` to check if update is safe
- If `action == "create"`: write the file
- If `action == "update"`: write the file (user didn't modify it)
- If `action == "skip"`: log and skip
- If `action == "conflict"`: show diff and ask user

### 6. Install Agents

Use the installers module to scaffold `.claude/agents/`:

```python
from src.core.installers import install_agents
```

This installs agent templates with placeholder substitution based on detection.

### 7. Install MCP Servers

Generate `.mcp.json` with stack-appropriate MCP servers:

```python
from src.core.installers import generate_mcp_json, merge_mcp_json
```

### 8. Check Rulesync

If `rulesync` is installed, suggest running `rulesync generate` to create cross-tool config files.

### 9. Cache Hashes

Write SHA256 hashes of all generated files to `.claude/agents/.hashes` for idempotent re-runs.

### 10. Summary

Output a summary of what was created/updated/skipped.

## Rules

- NEVER overwrite user-modified files without confirmation
- ALWAYS use smart_merge for idempotent re-runs
- CLAUDE.md MUST be ≤200 lines
- AGENTS.md MUST be ≤100 lines
- Generated files use detection results, not hardcoded values
