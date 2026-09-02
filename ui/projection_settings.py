"""Persisted assumptions for the Net Worth Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(birth year, return rates, retirement age, etc.), not financial records,
so they're kept in a JSON file under config/ instead -- same pattern as
payee_aliases.py. starting_investment_value is deliberately never stored
here: it's always recomputed live from current account data.

The user can maintain multiple named profiles (e.g. "Default", "Retire
Early"), each with its own full set of projection inputs. The file stores
all profiles plus which one was last active, keyed as:
    {"active_profile": "<name>", "profiles": {"<name>": {...}, ...}}

Files written before profiles existed are a flat dict of input fields;
loading one migrates it into a single "Default" profile.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "projection_settings.json"
DEFAULT_PROFILE_NAME = "Default"


def load_projection_profiles(path=None):
    """Returns (active_profile_name, {profile_name: flat dict of input fields}).

    Returns (DEFAULT_PROFILE_NAME, {}) if the file is missing, corrupt, or
    was migrated from an old flat format with no fields saved.
    """
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not path.exists():
        return DEFAULT_PROFILE_NAME, {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_PROFILE_NAME, {}
    if not isinstance(data, dict) or "profiles" not in data:
        profiles = {DEFAULT_PROFILE_NAME: data} if data else {}
        return DEFAULT_PROFILE_NAME, profiles
    return data.get("active_profile", DEFAULT_PROFILE_NAME), data.get("profiles", {})


def save_projection_profiles(profiles, active_profile, path=None):
    """profiles: {profile_name: flat dict of input fields (JSON-serializable)}."""
    path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"active_profile": active_profile, "profiles": profiles}, f, indent=2, sort_keys=True)
