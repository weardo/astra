#!/usr/bin/env bash
# track_files_touched.sh — PostToolUse Write|Edit hook: track files touched during a run
# Appends file_path to ${RUN_DIR}/files_touched.txt for scope drift detection.
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

# Append to tracking file
printf '%s\n' "$FILE_PATH" >> "${RUN_DIR}/files_touched.txt"

exit 0
