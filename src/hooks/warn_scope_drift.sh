#!/usr/bin/env bash
# warn_scope_drift.sh — PostToolUse Write|Edit hook: warn on scope drift
# If the file being modified is NOT in the current task's target_files, emit a warning.
# Exit 0 always (advisory, not blocking).
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

# Check if current_task.json exists
TASK_FILE="${RUN_DIR}/current_task.json"
if [ ! -f "$TASK_FILE" ]; then
  exit 0
fi

# Parse file_path from stdin JSON
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Check if file_path is in target_files
if command -v python3 >/dev/null 2>&1; then
  IN_TARGET=$(python3 -c "
import json, sys
try:
    task = json.load(open('${TASK_FILE}'))
    targets = task.get('target_files', [])
    path = '${FILE_PATH}'
    # Check exact match or if path ends with any target
    for t in targets:
        if path.endswith(t) or t.endswith(path.split('/')[-1]):
            sys.exit(0)
    if targets:
        sys.exit(1)
    sys.exit(0)
except Exception:
    sys.exit(0)
" 2>/dev/null; echo $?)
  if [ "$IN_TARGET" = "1" ]; then
    printf '[scope-drift] WARNING: %s is not in current task target_files\n' "$FILE_PATH" >&2
  fi
fi

exit 0
