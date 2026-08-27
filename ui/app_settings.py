"""Persisted UI preferences (dark mode, SEK/USD exchange rate).

Kept in a JSON file under config/ instead of QSettings so they live
inside the repo -- alongside the other settings files -- and get picked
up by the exit-time backup, instead of being invisible OS-level config.
Same pattern as projection_settings.py.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "app_settings.json"


def load_app_settings(path=DEFAULT_SETTINGS_PATH):
    """Returns a flat dict of saved app settings, or {} if unset."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_app_settings(settings, path=DEFAULT_SETTINGS_PATH):
    """settings: flat dict of app setting fields (JSON-serializable)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
