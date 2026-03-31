#!/usr/bin/env bash
# path-guard.sh — PreToolUse Write hook: block writes to wrong directories
# Reads blocked path patterns from $PROJECT_ROOT/.bootstrap-paths.conf
# Exit 0 = allow, Exit 2 = block silently (Claude Code convention)
set -euo pipefail

# Read file_path from stdin JSON
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Find project root (look for CLAUDE.md, .git, or .claude/)
PROJECT_ROOT=""
dir="$(dirname "$FILE_PATH")"
while [ "$dir" != "/" ] && [ "$dir" != "." ]; do
  if [ -f "$dir/CLAUDE.md" ] || [ -d "$dir/.git" ] || [ -d "$dir/.claude" ]; then
    PROJECT_ROOT="$dir"
    break
  fi
  dir="$(dirname "$dir")"
done

CONF_FILE="${PROJECT_ROOT:-.}/.bootstrap-paths.conf"

# No conf file = no-op
if [ ! -f "$CONF_FILE" ]; then
  exit 0
fi

# Check file_path against blocked patterns
while IFS= read -r pattern || [ -n "$pattern" ]; do
  # Skip empty lines and comments
  [[ -z "$pattern" || "$pattern" == \#* ]] && continue
  # Expand ~ in pattern
  pattern="${pattern/#\~/$HOME}"
  # Use case statement for glob matching
  case "$FILE_PATH" in
    $pattern)
      printf "Blocked: %s matches blocked pattern '%s'\n" "$FILE_PATH" "$pattern" >&2
      exit 2
      ;;
  esac
done < "$CONF_FILE"

exit 0
