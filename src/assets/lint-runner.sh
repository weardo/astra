#!/usr/bin/env bash
# lint-runner.sh — PostToolUse Write|Edit hook: auto-detect + run linter
# Exit 0 always (advisory, not blocking)
set -uo pipefail

# Read tool_input from stdin JSON to get the modified file
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
  exit 0
fi

PROJECT_ROOT="$(dirname "$FILE_PATH")"

# Auto-detect linter by walking up to find config
detect_root() {
  local dir="$1"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/package.json" ] || [ -f "$dir/.eslintrc.js" ] || \
       [ -f "$dir/.eslintrc.json" ] || [ -f "$dir/.eslintrc.yml" ] || \
       [ -f "$dir/.eslintrc" ] || [ -f "$dir/ruff.toml" ] || \
       [ -f "$dir/pyproject.toml" ] || [ -f "$dir/.golangci.yml" ]; then
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  printf '%s' "$(dirname "$FILE_PATH")"
}

ROOT="$(detect_root "$(dirname "$FILE_PATH")")"

# ESLint (Node/TypeScript)
if [ -f "$ROOT/.eslintrc.js" ] || [ -f "$ROOT/.eslintrc.json" ] || \
   [ -f "$ROOT/.eslintrc.yml" ] || [ -f "$ROOT/.eslintrc" ] || \
   ([ -f "$ROOT/package.json" ] && grep -q '"eslint"' "$ROOT/package.json" 2>/dev/null); then
  if command -v eslint >/dev/null 2>&1; then
    eslint "$FILE_PATH" 2>&1 || true
  elif [ -f "$ROOT/node_modules/.bin/eslint" ]; then
    "$ROOT/node_modules/.bin/eslint" "$FILE_PATH" 2>&1 || true
  fi
  exit 0
fi

# Ruff (Python)
if command -v ruff >/dev/null 2>&1; then
  case "$FILE_PATH" in
    *.py) ruff check "$FILE_PATH" 2>&1 || true; exit 0 ;;
  esac
fi

# golangci-lint (Go)
if command -v golangci-lint >/dev/null 2>&1 && [ -f "$ROOT/go.mod" ]; then
  case "$FILE_PATH" in
    *.go) golangci-lint run "$FILE_PATH" 2>&1 || true; exit 0 ;;
  esac
fi

exit 0
