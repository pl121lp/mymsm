"""Persisted tax-rate assumption for the RSU Vesting Forecast report.

money.duckdb is opened read-only; the expected tax rate is a planning
assumption, not a financial record, so it's kept in a JSON file under
config/ instead -- same pattern as projection_settings.py.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "rsu_tax_settings.json"


def load_rsu_tax_settings(path=None):
    """Returns a flat dict of saved RSU tax settings, or {} if unset."""
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_rsu_tax_settings(settings, path=None):
    """settings: flat dict of RSU tax settings fields (JSON-serializable)."""
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
