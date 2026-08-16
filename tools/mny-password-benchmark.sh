#!/usr/bin/env bash
# Measures offline password-check throughput on this machine (see
# tools/mny-password-crack.sh and PasswordCracker.java for context), to
# estimate how long a full brute-force search would take before running one.
#
# Usage: tools/mny-password-benchmark.sh <path-to-money-file.mny> [seconds]
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: tools/mny-password-benchmark.sh <path-to-money-file.mny> [seconds]" >&2
    exit 2
fi

MNY_FILE="$1"
SECONDS_TO_RUN="${2:-5}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -cp "$ROOT_DIR/extract-mny/target/extract-mny.jar" com.mymsm.extract.PasswordCracker benchmark "$MNY_FILE" "$SECONDS_TO_RUN"
