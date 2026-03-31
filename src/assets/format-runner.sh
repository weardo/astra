#!/usr/bin/env bash
# format-runner.sh — PostToolUse Write|Edit hook: auto-detect + run formatter
# Exit 0 always (non-blocking)
set -uo pipefail

# Read tool_input from stdin JSON to get the modified file
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

# Walk up to find project root
find_root() {
  local dir="$1"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/.prettierrc" ] || [ -f "$dir/.prettierrc.js" ] || \
       [ -f "$dir/.prettierrc.json" ] || [ -f "$dir/.prettierrc.yml" ] || \
       [ -f "$dir/pyproject.toml" ] || [ -f "$dir/go.mod" ] || \
       [ -f "$dir/package.json" ]; then
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  printf '%s' "$(dirname "$FILE_PATH")"
}

ROOT="$(find_root "$(dirname "$FILE_PATH")")"

# Prettier (Node/TypeScript/JS)
if [ -f "$ROOT/.prettierrc" ] || [ -f "$ROOT/.prettierrc.js" ] || \
   [ -f "$ROOT/.prettierrc.json" ] || [ -f "$ROOT/.prettierrc.yml" ]; then
  if command -v prettier >/dev/null 2>&1; then
    prettier --write "$FILE_PATH" 2>&1 || true
  elif [ -f "$ROOT/node_modules/.bin/prettier" ]; then
    "$ROOT/node_modules/.bin/prettier" --write "$FILE_PATH" 2>&1 || true
  fi
  exit 0
fi

# Black (Python)
if command -v black >/dev/null 2>&1; then
  case "$FILE_PATH" in
    *.py)
      if [ -f "$ROOT/pyproject.toml" ] && grep -q '\[tool.black\]' "$ROOT/pyproject.toml" 2>/dev/null; then
        black "$FILE_PATH" 2>&1 || true
        exit 0
      fi
      ;;
  esac
fi

# gofmt (Go)
if command -v gofmt >/dev/null 2>&1 && [ -f "$ROOT/go.mod" ]; then
  case "$FILE_PATH" in
    *.go)
      gofmt -w "$FILE_PATH" 2>&1 || true
      exit 0
      ;;
  esac
fi

exit 0
