#!/usr/bin/env bash
# detect.sh — Stack + existing setup detection for bootstrap-project
# Usage: detect.sh <project-path>
# Output: JSON on stdout, exit 0 always (errors as {"error":"..."})
set -euo pipefail

PROJECT="${1:-}"
if [ -z "$PROJECT" ]; then
  printf '{"error":"missing required argument: project path"}\n'
  exit 0
fi

if [ ! -d "$PROJECT" ]; then
  printf '{"error":"path does not exist: %s"}\n' "$PROJECT"
  exit 0
fi

PROJECT="$(cd "$PROJECT" && pwd)"

# ── Stack detection ───────────────────────────────────────────────────────────
STACK=""
FRAMEWORKS=""
INFRA=""

add_to() {
  local var="$1" val="$2"
  if [ -z "${!var}" ]; then printf '%s' "$val"
  else printf '%s,%s' "${!var}" "$val"; fi
}

# Node/TypeScript — check root and one level deep (monorepos)
PKG_FILES=""
[ -f "$PROJECT/package.json" ] && PKG_FILES="$PROJECT/package.json"
for sub_pkg in "$PROJECT"/*/package.json; do
  [ -f "$sub_pkg" ] && PKG_FILES="$PKG_FILES $sub_pkg"
done

if [ -n "$PKG_FILES" ]; then
  STACK="$(add_to STACK '"node"')"
  # Check for TypeScript
  FOUND_TS="false"
  for pkg in $PKG_FILES; do
    grep -q '"typescript"' "$pkg" 2>/dev/null && FOUND_TS="true"
  done
  if [ "$FOUND_TS" = "true" ] || [ -f "$PROJECT/tsconfig.json" ] || \
     ls "$PROJECT"/*/tsconfig.json 2>/dev/null | grep -q .; then
    STACK="$(add_to STACK '"typescript"')"
  fi
  # Frameworks from dependencies (search all package.json files)
  COMBINED_PKGS="$(cat $PKG_FILES 2>/dev/null)"
  if printf '%s' "$COMBINED_PKGS" | grep -qE '"(express|fastify|koa)"'; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"express"')"
  fi
  if printf '%s' "$COMBINED_PKGS" | grep -qE '"(next|nextjs)"'; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"next"')"
  fi
  if printf '%s' "$COMBINED_PKGS" | grep -qE '"react"'; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"react"')"
  fi
  if printf '%s' "$COMBINED_PKGS" | grep -qE '"(vitest|jest)"'; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"vitest"')"
  fi
  if printf '%s' "$COMBINED_PKGS" | grep -qE '"(@playwright/test|playwright)"'; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"playwright"')"
  fi
fi

# Python
if [ -f "$PROJECT/requirements.txt" ] || \
   [ -f "$PROJECT/pyproject.toml" ] || \
   [ -f "$PROJECT/setup.py" ]; then
  STACK="$(add_to STACK '"python"')"
  if [ -f "$PROJECT/pyproject.toml" ] && grep -q 'fastapi' "$PROJECT/pyproject.toml" 2>/dev/null; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"fastapi"')"
  fi
  if [ -f "$PROJECT/requirements.txt" ] && grep -qi 'fastapi' "$PROJECT/requirements.txt" 2>/dev/null; then
    FRAMEWORKS="$(add_to FRAMEWORKS '"fastapi"')"
  fi
fi

# Go
if [ -f "$PROJECT/go.mod" ]; then
  STACK="$(add_to STACK '"go"')"
fi

# Rust
if [ -f "$PROJECT/Cargo.toml" ]; then
  STACK="$(add_to STACK '"rust"')"
fi

# Infra
if [ -f "$PROJECT/Dockerfile" ] || ls "$PROJECT"/docker-compose*.yml 2>/dev/null | grep -q .; then
  INFRA="$(add_to INFRA '"docker"')"
fi
if [ -d "$PROJECT/.github/workflows" ]; then
  INFRA="$(add_to INFRA '"github-actions"')"
fi

# ── File count + size ─────────────────────────────────────────────────────────
FILE_COUNT=$(find "$PROJECT" -type f \
  ! -path '*/node_modules/*' \
  ! -path '*/.git/*' \
  ! -path '*/__pycache__/*' \
  ! -path '*/.venv/*' \
  2>/dev/null | wc -l | tr -d ' ')

if [ "$FILE_COUNT" -lt 5 ]; then
  SIZE="greenfield"
else
  SIZE="brownfield"
fi

# ── Existing AI setup ─────────────────────────────────────────────────────────
CLAUDE_MD="false"
AGENTS_MD="false"
GOAL_MD="false"
MCP_JSON="false"
DOT_CLAUDE="false"
RULESYNC="false"
SKILLS_LIST=""
HOOKS_LIST=""

[ -f "$PROJECT/CLAUDE.md" ] && CLAUDE_MD="true"
[ -f "$PROJECT/AGENTS.md" ] && AGENTS_MD="true"
[ -f "$PROJECT/GOAL.md" ] && GOAL_MD="true"
[ -f "$PROJECT/.mcp.json" ] && MCP_JSON="true"
[ -d "$PROJECT/.claude" ] && DOT_CLAUDE="true"
[ -d "$PROJECT/.rulesync" ] && RULESYNC="true"

# Skills: list SKILL.md files
if [ -d "$PROJECT/.claude/skills" ]; then
  for skill_file in "$PROJECT/.claude/skills"/*/SKILL.md; do
    if [ -f "$skill_file" ]; then
      skill_name="$(basename "$(dirname "$skill_file")")"
      if [ -z "$SKILLS_LIST" ]; then
        SKILLS_LIST="\"$skill_name\""
      else
        SKILLS_LIST="$SKILLS_LIST,\"$skill_name\""
      fi
    fi
  done
fi

# Hooks: list .sh files
if [ -d "$PROJECT/.claude/hooks" ]; then
  for hook_file in "$PROJECT/.claude/hooks"/*.sh; do
    if [ -f "$hook_file" ]; then
      hook_name="$(basename "$hook_file")"
      if [ -z "$HOOKS_LIST" ]; then
        HOOKS_LIST="\"$hook_name\""
      else
        HOOKS_LIST="$HOOKS_LIST,\"$hook_name\""
      fi
    fi
  done
fi

# Agents: list .md files, extract name from frontmatter
AGENTS_LIST=""
if [ -d "$PROJECT/.claude/agents" ]; then
  for agent_file in "$PROJECT/.claude/agents"/*.md; do
    [ -f "$agent_file" ] || continue
    agent_name="$(grep -m1 '^name:' "$agent_file" | sed 's/^name:[[:space:]]*//' | tr -d '"' || true)"
    [ -z "$agent_name" ] && continue
    if [ -z "$AGENTS_LIST" ]; then
      AGENTS_LIST="\"$agent_name\""
    else
      AGENTS_LIST="$AGENTS_LIST,\"$agent_name\""
    fi
  done
fi

# ── Headless detection ────────────────────────────────────────────────────────
HEADLESS="false"
if [ ! -t 0 ] || [ "${CI:-}" = "true" ] || [ "${BOOTSTRAP_HEADLESS:-}" = "1" ]; then
  HEADLESS="true"
fi

# ── Output JSON ───────────────────────────────────────────────────────────────
printf '{"stack":[%s],"frameworks":[%s],"infra":[%s],"size":"%s","fileCount":%s,"headless":%s,"existing":{"claudeMd":%s,"agentsMd":%s,"goalMd":%s,"mcpJson":%s,"dotClaude":%s,"skills":[%s],"hooks":[%s],"rulesync":%s,"agents":[%s]}}\n' \
  "$STACK" \
  "$FRAMEWORKS" \
  "$INFRA" \
  "$SIZE" \
  "$FILE_COUNT" \
  "$HEADLESS" \
  "$CLAUDE_MD" \
  "$AGENTS_MD" \
  "$GOAL_MD" \
  "$MCP_JSON" \
  "$DOT_CLAUDE" \
  "$SKILLS_LIST" \
  "$HOOKS_LIST" \
  "$RULESYNC" \
  "$AGENTS_LIST"
