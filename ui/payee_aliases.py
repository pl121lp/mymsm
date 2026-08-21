"""Non-destructive payee merge overlay.

money.duckdb is opened read-only (see data.py) and is never written to.
Payee merges accepted from the Dictionaries > Payees tab are instead
recorded here, in a sibling JSON file, and applied to the payee list and
transaction lookups at read time.
"""

import json
from pathlib import Path

DEFAULT_ALIASES_PATH = Path(__file__).resolve().parent.parent / "payee_aliases.json"


def _read(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_aliases(path=DEFAULT_ALIASES_PATH):
    """Returns {canonical_payee_id: [absorbed_payee_id, ...]}."""
    raw = _read(path)
    return {int(k): list(v) for k, v in raw.get("groups", {}).items()}


def load_canonical_names(path=DEFAULT_ALIASES_PATH):
    """Returns {canonical_payee_id: overridden display name}."""
    raw = _read(path)
    return {int(k): v for k, v in raw.get("names", {}).items()}


def save_aliases(groups, names, path=DEFAULT_ALIASES_PATH):
    """groups: {canonical_payee_id: [absorbed_payee_id, ...]}
    names: {canonical_payee_id: display name}"""
    payload = {
        "groups": {str(k): v for k, v in groups.items()},
        "names": {str(k): v for k, v in names.items()},
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def merge_groups(existing, additional):
    """Combine two {canonical: [absorbed, ...]} maps, unioning members for
    a shared canonical payee_id."""
    merged = {k: list(v) for k, v in existing.items()}
    for canonical_id, absorbed_ids in additional.items():
        members = merged.setdefault(canonical_id, [])
        for payee_id in absorbed_ids:
            if payee_id not in members:
                members.append(payee_id)
    return merged


def apply_aliases(payees, groups, names=None):
    """payees: [(payee_id, name), ...] from data.list_payees().

    Returns the same shape with absorbed payee_ids dropped and canonical
    rows relabeled with their override name, if any.
    """
    names = names or {}
    absorbed = {payee_id for members in groups.values() for payee_id in members}
    result = [
        (payee_id, names.get(payee_id, name))
        for payee_id, name in payees
        if payee_id not in absorbed
    ]
    return sorted(result, key=lambda row: row[1])


def resolve_payee_ids(payee_id, groups):
    """All real payee_ids a canonical (or standalone) payee_id represents."""
    return [payee_id] + list(groups.get(payee_id, []))
