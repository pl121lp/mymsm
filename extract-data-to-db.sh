#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: ./run.sh <path-to-money-file.mny>" >&2
    exit 2
fi

MNY_FILE="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_DIR="$ROOT_DIR/data/raw"
DB_PATH="$ROOT_DIR/money.duckdb"
VENV_DIR="$ROOT_DIR/.venv"

echo "== Stage 1: extracting raw tables from $MNY_FILE =="
mkdir -p "$RAW_DIR"
( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -jar "$ROOT_DIR/extract-mny/target/extract-mny.jar" "$MNY_FILE" "$RAW_DIR"

echo "== Stage 2: loading raw tables into DuckDB =="
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$ROOT_DIR/etl/requirements.txt"
fi
"$VENV_DIR/bin/python" "$ROOT_DIR/etl/load.py" "$RAW_DIR" "$DB_PATH"

echo "== Done: $DB_PATH =="
