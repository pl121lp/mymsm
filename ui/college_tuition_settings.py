"""Persisted assumptions for the College Tuition Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(expected return, contribution, per-person tuition/housing/timeline, and
which accounts feed the fund), not financial records, so they're kept in
a sibling JSON file instead -- same pattern as projection_settings.py.
starting_fund_value is deliberately never stored here: it's always
recomputed live from currently selected accounts' balances.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "college_tuition_settings.json"


def load_college_tuition_settings(path=DEFAULT_SETTINGS_PATH):
    """Returns a flat dict of saved college tuition input fields, or {} if unset."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_college_tuition_settings(settings, path=DEFAULT_SETTINGS_PATH):
    """settings: flat dict of college tuition input fields (JSON-serializable)."""
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
