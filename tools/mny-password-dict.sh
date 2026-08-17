#!/usr/bin/env bash
# Dictionary attack against a Money (.mny) file: checks every line of a
# wordlist file as a candidate password, in order, and stops at the first
# confirmed hit. Reads the wordlist one line at a time (bounded memory),
# so it's safe to point at multi-million-line lists.
#
# Useful when you don't have a specific password in mind to mutate (see
# tools/mny-password-crack.sh for that instead) - e.g. after learning your
# Money file's password may be an old online-account password rather than
# something you chose specifically for Money (see README's "Recovering a
# forgotten/misremembered password" section). Common leaked-password lists
# like SecLists' rockyou.txt (github.com/danielmiessler/SecLists, under
# Passwords/Leaked-Databases/) are a reasonable place to start; on Kali
# Linux one is already at /usr/share/wordlists/rockyou.txt.gz.
#
# Usage: tools/mny-password-dict.sh <path-to-money-file.mny> <wordlist-file>
set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "Usage: tools/mny-password-dict.sh <path-to-money-file.mny> <wordlist-file>" >&2
    exit 2
fi

MNY_FILE="$1"
WORDLIST="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -cp "$ROOT_DIR/extract-mny/target/extract-mny.jar" com.mymsm.extract.PasswordCracker dict "$MNY_FILE" "$WORDLIST"
