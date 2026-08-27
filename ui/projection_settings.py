"""Persisted assumptions for the Net Worth Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(birth year, return rates, retirement age, etc.), not financial records,
so they're kept in a JSON file under config/ instead -- same pattern as
payee_aliases.py. starting_investment_value is deliberately never stored
here: it's always recomputed live from current account data.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "projection_settings.json"


def load_projection_settings(path=None):
    """Returns a flat dict of saved projection input fields, or {} if unset."""
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_projection_settings(settings, path=None):
    """settings: flat dict of projection input fields (JSON-serializable)."""
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
