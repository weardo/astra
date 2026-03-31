#!/usr/bin/env bash
# read-insights.sh — Parse Claude Code session history for personalized insights
# Usage: read-insights.sh
# Output: JSON on stdout, exit 0 always
# Override data dir for testing: CLAUDE_USAGE_DIR=/path
set -euo pipefail

USAGE_DIR="${CLAUDE_USAGE_DIR:-$HOME/.claude/usage-data}"

# Graceful degradation — if no data, output minimal response
if [ ! -d "$USAGE_DIR" ]; then
  printf '{"available":false}\n'
  exit 0
fi

# ── Parse session metadata ────────────────────────────────────────────────────
SESSION_COUNT=0
TOP_LANGUAGES=""

# Count sessions from session files or facets
if [ -d "$USAGE_DIR/sessions" ]; then
  SESSION_COUNT=$(find "$USAGE_DIR/sessions" -name "*.json" -type f 2>/dev/null | wc -l | tr -d ' ')
fi

# ── Parse facets for friction categories ─────────────────────────────────────
WRONG_APPROACH=0
CONTEXT_EXHAUSTION=0
BUGGY_CODE=0
WRONG_FILE=0
MISSED_PATTERN=0

FACETS_DIR="$USAGE_DIR/facets"
if [ -d "$FACETS_DIR" ]; then
  for facet_file in "$FACETS_DIR"/*.json; do
    [ -f "$facet_file" ] || continue
    # Extract friction category counts using grep + awk
    content="$(cat "$facet_file" 2>/dev/null)" || continue

    # wrong_approach
    count=$(printf '%s' "$content" | grep -o '"wrong_approach"[^,}]*' | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$count" ] && WRONG_APPROACH=$((WRONG_APPROACH + count))

    # context_exhaustion
    count=$(printf '%s' "$content" | grep -o '"context_exhaustion"[^,}]*' | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$count" ] && CONTEXT_EXHAUSTION=$((CONTEXT_EXHAUSTION + count))

    # buggy_code
    count=$(printf '%s' "$content" | grep -o '"buggy_code"[^,}]*' | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$count" ] && BUGGY_CODE=$((BUGGY_CODE + count))

    # wrong_file
    count=$(printf '%s' "$content" | grep -o '"wrong_file"[^,}]*' | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$count" ] && WRONG_FILE=$((WRONG_FILE + count))

    # missed_pattern
    count=$(printf '%s' "$content" | grep -o '"missed_pattern"[^,}]*' | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$count" ] && MISSED_PATTERN=$((MISSED_PATTERN + count))
  done
fi

# ── Compute prioritized rules from friction ───────────────────────────────────
PRIORITIZED_RULES=""
add_rule() {
  if [ -z "$PRIORITIZED_RULES" ]; then
    PRIORITIZED_RULES="\"$1\""
  else
    PRIORITIZED_RULES="$PRIORITIZED_RULES,\"$1\""
  fi
}

[ "$WRONG_APPROACH" -gt 2 ] && add_rule "Explore before implementing"
[ "$CONTEXT_EXHAUSTION" -gt 2 ] && add_rule "YOU MUST compact at 30% context remaining"
[ "$BUGGY_CODE" -gt 2 ] && add_rule "Write tests before implementation"
[ "$WRONG_FILE" -gt 1 ] && add_rule "Read file before editing"
[ "$MISSED_PATTERN" -gt 1 ] && add_rule "Grep for existing patterns before creating new ones"

# ── Compute prioritized hooks from friction ───────────────────────────────────
PRIORITIZED_HOOKS=""
add_hook() {
  if [ -z "$PRIORITIZED_HOOKS" ]; then
    PRIORITIZED_HOOKS="\"$1\""
  else
    PRIORITIZED_HOOKS="$PRIORITIZED_HOOKS,\"$1\""
  fi
}

[ "$WRONG_APPROACH" -gt 2 ] && add_hook "path-guard"
[ "$BUGGY_CODE" -gt 2 ] && add_hook "test-runner"
[ "$MISSED_PATTERN" -gt 1 ] && add_hook "lint-runner"

# ── Build topFriction list (sorted by count desc, names only) ─────────────────
TOP_FRICTION=""
add_top_friction() {
  local key="$1" count="$2"
  [ "$count" -gt 2 ] || return 0
  if [ -z "$TOP_FRICTION" ]; then
    TOP_FRICTION="\"$key\""
  else
    TOP_FRICTION="$TOP_FRICTION,\"$key\""
  fi
}
add_top_friction "wrong_approach" "$WRONG_APPROACH"
add_top_friction "context_exhaustion" "$CONTEXT_EXHAUSTION"
add_top_friction "buggy_code" "$BUGGY_CODE"
add_top_friction "wrong_file" "$WRONG_FILE"
add_top_friction "missed_pattern" "$MISSED_PATTERN"

# ── Build frictionCounts object ───────────────────────────────────────────────
FRICTION_COUNTS="{\"wrong_approach\":$WRONG_APPROACH,\"context_exhaustion\":$CONTEXT_EXHAUSTION,\"buggy_code\":$BUGGY_CODE,\"wrong_file\":$WRONG_FILE,\"missed_pattern\":$MISSED_PATTERN}"

# ── Output JSON (matches spec section 4.3 schema) ─────────────────────────────
printf '{"available":true,"sessionCount":%s,"topLanguages":[],"topFriction":[%s],"frictionCounts":%s,"prioritizedRules":[%s],"prioritizedHooks":[%s]}\n' \
  "$SESSION_COUNT" \
  "$TOP_FRICTION" \
  "$FRICTION_COUNTS" \
  "$PRIORITIZED_RULES" \
  "$PRIORITIZED_HOOKS"
