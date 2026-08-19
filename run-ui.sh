#!/usr/bin/env bash
# run-ui.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q -r "$ROOT_DIR/etl/requirements.txt" -r "$ROOT_DIR/ui/requirements.txt"
"$VENV_DIR/bin/python" "$ROOT_DIR/ui/main.py"
