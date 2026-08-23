"""Persisted assumptions for the Net Worth Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(birth year, return rates, retirement age, etc.), not financial records,
so they're kept in a sibling JSON file instead -- same pattern as
payee_aliases.py. starting_investment_value is deliberately never stored
here: it's always recomputed live from current account data.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "projection_settings.json"


def load_projection_settings(path=DEFAULT_SETTINGS_PATH):
    """Returns a flat dict of saved projection input fields, or {} if unset."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_projection_settings(settings, path=DEFAULT_SETTINGS_PATH):
    """settings: flat dict of projection input fields (JSON-serializable)."""
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
