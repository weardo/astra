#!/usr/bin/env bash
# test-runner.sh — PostToolUse Write|Edit hook: auto-detect + run test suite
# Exit 0 always (informational, not blocking)
set -uo pipefail

# Read tool_input from stdin JSON to get the modified file
INPUT="$(cat)"
FILE_PATH="$(printf '%s' "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"' || true)"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Walk up from file to find project root with test runner
find_root() {
  local dir="$1"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/package.json" ] || [ -f "$dir/pytest.ini" ] || \
       [ -f "$dir/pyproject.toml" ] || [ -f "$dir/go.mod" ] || \
       [ -f "$dir/Cargo.toml" ]; then
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

ROOT="$(find_root "$(dirname "$FILE_PATH")")" || exit 0

# npm/vitest/jest (Node)
if [ -f "$ROOT/package.json" ]; then
  TEST_CMD=$(grep -o '"test"[[:space:]]*:[[:space:]]*"[^"]*"' "$ROOT/package.json" | head -1 | grep -o '"[^"]*"$' | tr -d '"' || true)
  if [ -n "$TEST_CMD" ]; then
    printf '[test-runner] Running: npm test\n' >&2
    (cd "$ROOT" && npm test --silent 2>&1 || true)
    exit 0
  fi
fi

# pytest (Python)
if [ -f "$ROOT/pytest.ini" ] || ([ -f "$ROOT/pyproject.toml" ] && grep -q '\[tool.pytest' "$ROOT/pyproject.toml" 2>/dev/null); then
  if command -v pytest >/dev/null 2>&1; then
    printf '[test-runner] Running: pytest\n' >&2
    (cd "$ROOT" && pytest -q 2>&1 || true)
    exit 0
  fi
fi

# go test (Go)
if [ -f "$ROOT/go.mod" ]; then
  if command -v go >/dev/null 2>&1; then
    printf '[test-runner] Running: go test ./...\n' >&2
    (cd "$ROOT" && go test ./... 2>&1 || true)
    exit 0
  fi
fi

exit 0
