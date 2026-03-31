#!/usr/bin/env bash
# auto_fix_deps.sh — PostToolUse Write hook: auto-fix work plan conflicts
# Runs after work_plan.json is written to detect and fix file conflicts.
# Exit 0 always (non-blocking).
set -uo pipefail

# Read sentinel file to get active run directory
SENTINEL="${PROJECT_DIR:-.}/.astra-active-run"
if [ ! -f "$SENTINEL" ]; then
  exit 0
fi
RUN_DIR="$(cat "$SENTINEL")"
if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
  exit 0
fi

# Parse file_path from stdin JSON
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Only act on work_plan files
case "$FILE_PATH" in
  *work_plan*) ;;
  *) exit 0 ;;
esac

# Run auto-fix
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "$0")")")}"
python3 "${PLUGIN_ROOT}/src/core/auto_fix_deps.py" "$FILE_PATH" 2>&1 || true

exit 0
