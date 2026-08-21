"""Fuzzy-cluster near-duplicate payee names into merge suggestions.

Groups payees whose names are minor variants of the same underlying
merchant (store-location suffixes, order/confirmation codes, statement
noise like "Advance "/"Withdrawal " prefixes) so the Dictionaries > Payees
tab can offer them as one-click merges. Pure data-in/data-out: no Qt, no
database access.
"""

import difflib
import re
from collections import defaultdict, namedtuple

# Generic transaction-type / processor tokens that say nothing about *who*
# was paid. Left in place, they dominate short strings and make unrelated
# merchants look alike -- every "Advance ..." cash-advance transaction
# shares that prefix regardless of merchant.
NOISE_WORDS = {
    "DATE", "PAYMENT", "PYMT", "PURCHASE", "DEBIT", "CREDIT", "POS", "WWW", "COM",
    "INC", "CO", "CORP", "LLC", "THE", "AND", "OR",
    "ADVANCE", "WITHDRAWAL", "DEPOSIT", "CHECK", "INTERNET", "CARD", "UNKNOWN", "TO",
    "SQ", "TST", "WPY", "PY", "WL", "CKCD", "RECURRING", "AUTOPAY", "ONLINE",
}

# Word-level similarity (not character-level): avoids short strings looking
# alike just because they share a common substring/prefix.
SIMILARITY_THRESHOLD = 0.55

MergeGroup = namedtuple("MergeGroup", ["canonical_payee_id", "canonical_name", "members"])
# members: [(payee_id, name, txn_count), ...], including the canonical
# itself, sorted by txn_count descending.


def normalize(name: str) -> str:
    s = name.upper()
    s = re.sub(r"[^A-Z0-9\s]", " ", s)  # drop punctuation
    s = re.sub(r"\d+", " ", s)          # drop digits (store #s, dates, amounts, ids)
    tokens = [t for t in s.split() if t and t not in NOISE_WORDS]
    return " ".join(tokens)


def _token_ratio(a: str, b: str) -> float:
    tokens_a, tokens_b = a.split(), b.split()
    shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    if shorter and longer[: len(shorter)] == shorter:
        # A bare merchant name ("Subway") is often just a truncation of a
        # location-suffixed variant ("Subway San Diego Ca") -- treat that
        # as a full match rather than penalizing it for the extra tokens.
        return 1.0
    return difflib.SequenceMatcher(None, tokens_a, tokens_b).ratio()


def _leading_noise_word_count(name: str) -> int:
    count = 0
    for token in name.upper().split():
        if re.sub(r"[^A-Z0-9]", "", token) in NOISE_WORDS:
            count += 1
        else:
            break
    return count


def _pick_canonical(members, txn_counts):
    def score(member):
        payee_id, name, _norm = member
        n_digit_tokens = sum(1 for t in name.split() if any(c.isdigit() for c in t))
        return (_leading_noise_word_count(name), n_digit_tokens, -txn_counts.get(payee_id, 0), len(name))

    return min(members, key=score)


def find_merge_groups(payees, txn_counts=None):
    """payees: iterable of (payee_id, name). txn_counts: optional {payee_id: count}.

    Returns a list of MergeGroup, largest group first, one per cluster of
    2+ payees whose names look like the same merchant.
    """
    txn_counts = txn_counts or {}

    # Bucket by first normalized token to keep pairwise comparisons cheap.
    buckets = defaultdict(list)
    for payee_id, name in payees:
        norm = normalize(name)
        if not norm:
            continue
        buckets[norm.split()[0]].append((payee_id, name, norm))

    groups = []
    for items in buckets.values():
        clusters = []  # [{"norms": [...], "members": [(id, name, norm), ...]}]
        for payee_id, name, norm in items:
            best_cluster, best_ratio = None, 0.0
            for cluster in clusters:
                ratio = max(_token_ratio(norm, rep) for rep in cluster["norms"])
                if ratio > best_ratio:
                    best_cluster, best_ratio = cluster, ratio
            if best_cluster is not None and best_ratio >= SIMILARITY_THRESHOLD:
                best_cluster["norms"].append(norm)
                best_cluster["members"].append((payee_id, name, norm))
            else:
                clusters.append({"norms": [norm], "members": [(payee_id, name, norm)]})

        for cluster in clusters:
            members = cluster["members"]
            if len(members) < 2:
                continue
            canonical_id, canonical_name, _ = _pick_canonical(members, txn_counts)
            member_rows = sorted(
                ((pid, nm, txn_counts.get(pid, 0)) for pid, nm, _norm in members),
                key=lambda m: -m[2],
            )
            groups.append(MergeGroup(canonical_id, canonical_name, member_rows))

    groups.sort(key=lambda g: (-len(g.members), -sum(m[2] for m in g.members)))
    return groups
