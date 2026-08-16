#!/usr/bin/env bash
# Exhaustive Money (.mny) password search - tries every combination of a
# given length and alphabet. Case never matters (Money's password check
# uppercases before comparing), so the default alphabet is uppercase
# letters only; see tools/mny-password-crack.sh for a much cheaper
# seed+mutation search to try first, and tools/mny-password-benchmark.sh to
# estimate how long this will take before running it.
#
# Any hit is re-verified against the real jackcess-encrypt library before
# being reported.
#
# Usage: tools/mny-password-bruteforce.sh <path-to-money-file.mny> <length> [alphabet]
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: tools/mny-password-bruteforce.sh <path-to-money-file.mny> <length> [alphabet]" >&2
    exit 2
fi

MNY_FILE="$1"
LENGTH="$2"
ALPHABET="${3:-ABCDEFGHIJKLMNOPQRSTUVWXYZ}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -cp "$ROOT_DIR/extract-mny/target/extract-mny.jar" com.mymsm.extract.PasswordCracker bruteforce "$MNY_FILE" "$LENGTH" "$ALPHABET"
