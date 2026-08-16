#!/usr/bin/env bash
# Standalone Money (.mny) password recovery helper. Runs outside Claude Code
# too - just needs JDK 17+ and Maven, same as the rest of this project.
#
# Tries a list of seed words/variants (tools/mny-password-seeds.txt by
# default) against the file, expanding each seed with nearby typos,
# substitutions, and insertions (edit-distance search) rather than pure
# brute force. Case never matters - Money's password check uppercases
# before comparing, so the seed list doesn't need case variants.
#
# Every candidate the fast checker accepts is re-verified against the real
# jackcess-encrypt library before being reported, so a hit here is a real
# hit, not a false positive from the fast check's 32-bit comparison.
#
# Usage:
#   tools/mny-password-crack.sh <path-to-money-file.mny> [seeds-file] [maxEditDistance] [mutationAlphabet]
#
# Defaults: seeds-file=tools/mny-password-seeds.txt, maxEditDistance=2,
# mutationAlphabet=abcdefghijklmnopqrstuvwxyz0123456789 (letters+digits;
# override to add symbols, e.g. 'abcdefghijklmnopqrstuvwxyz0123456789!@#-_.').
#
# If nothing in the seed list is close enough, this prints the exact
# command to run a full brute-force search instead (not run automatically -
# it can take hours, see the benchmark line it prints).
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: tools/mny-password-crack.sh <path-to-money-file.mny> [seeds-file] [maxEditDistance] [mutationAlphabet]" >&2
    exit 2
fi

MNY_FILE="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEEDS_FILE="${2:-$ROOT_DIR/tools/mny-password-seeds.txt}"
MAX_DISTANCE="${3:-2}"
ALPHABET="${4:-abcdefghijklmnopqrstuvwxyz0123456789}"

if [ ! -f "$SEEDS_FILE" ]; then
    echo "Seeds file not found: $SEEDS_FILE" >&2
    exit 2
fi

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
JAR="$ROOT_DIR/extract-mny/target/extract-mny.jar"

FOUND=0
TRIED=0
while IFS= read -r SEED || [ -n "$SEED" ]; do
    # skip blank lines and comments
    [[ -z "$SEED" || "$SEED" =~ ^[[:space:]]*# ]] && continue

    TRIED=$((TRIED + 1))
    echo "== Seed: [$SEED] (edit distance <= $MAX_DISTANCE, alphabet=$ALPHABET) =="
    OUTPUT="$(java -cp "$JAR" com.mymsm.extract.PasswordCracker near "$MNY_FILE" "$SEED" "$MAX_DISTANCE" "$ALPHABET")"
    echo "$OUTPUT"

    if echo "$OUTPUT" | grep -q "^CONFIRMED"; then
        echo
        echo "== FOUND IT (seed: [$SEED]) =="
        FOUND=1
        break
    fi
done < "$SEEDS_FILE"

echo
if [ "$FOUND" -eq 1 ]; then
    exit 0
fi

echo "No match after trying $TRIED seed(s) from $SEEDS_FILE (edit distance <= $MAX_DISTANCE)."
echo
echo "Next steps:"
echo "  - Add more candidate words to $SEEDS_FILE and re-run this script."
echo "  - Widen the mutation alphabet, e.g.:"
echo "      tools/mny-password-crack.sh \"$MNY_FILE\" \"$SEEDS_FILE\" $MAX_DISTANCE 'abcdefghijklmnopqrstuvwxyz0123456789!@#-_.'"
echo "  - Increase edit distance (slower, grows fast):"
echo "      tools/mny-password-crack.sh \"$MNY_FILE\" \"$SEEDS_FILE\" 3"
echo "  - Full exhaustive search of all-letter passwords of a given length"
echo "    (check throughput first with tools/mny-password-benchmark.sh):"
echo "      tools/mny-password-bruteforce.sh \"$MNY_FILE\" 8"
