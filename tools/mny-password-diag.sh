#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: tools/mny-password-diag.sh <path-to-money-file.mny>" >&2
    exit 2
fi

MNY_FILE="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -cp "$ROOT_DIR/extract-mny/target/extract-mny.jar" com.mymsm.extract.PasswordDiag "$MNY_FILE"
