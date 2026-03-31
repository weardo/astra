#!/usr/bin/env bash
# setup-venv.sh — Create and configure Python venv for astra plugin
# Usage: setup-venv.sh <target-directory>
set -euo pipefail

TARGET_DIR="${1:-.}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(dirname "$0")")")}"

VENV_DIR="${TARGET_DIR}/.venv"

if [ -d "$VENV_DIR" ]; then
  printf 'Venv already exists at %s\n' "$VENV_DIR"
else
  printf 'Creating venv at %s\n' "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

printf 'Installing dependencies...\n'
"${VENV_DIR}/bin/pip" install -q -r "${PLUGIN_ROOT}/requirements.txt"
printf 'Done.\n'
