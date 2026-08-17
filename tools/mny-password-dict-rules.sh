#!/usr/bin/env bash
# Dictionary attack with common suffix/prefix mutations (digits, years,
# punctuation) applied to each wordlist entry - e.g. "banana" also tries
# "banana1", "banana123", "banana2011", "1banana", etc. Much more likely to
# hit a real remembered password than the wordlist alone (see
# tools/mny-password-dict.sh), at the cost of ~180x more checks.
#
# Multi-threaded, streams the wordlist (bounded memory) so it's safe for
# large lists. Stops at the first confirmed hit.
#
# Usage: tools/mny-password-dict-rules.sh <path-to-money-file.mny> <wordlist-file>
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: tools/mny-password-dict-rules.sh <path-to-money-file.mny> <wordlist-file>" >&2
    exit 2
fi

MNY_FILE="$1"
WORDLIST="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -cp "$ROOT_DIR/extract-mny/target/extract-mny.jar" com.mymsm.extract.PasswordCracker dictrules "$MNY_FILE" "$WORDLIST"
