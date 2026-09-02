import json

from projection_settings import (
    DEFAULT_PROFILE_NAME,
    load_projection_profiles,
    save_projection_profiles,
)


def test_load_missing_file_returns_no_profiles(tmp_path):
    active_profile, profiles = load_projection_profiles(tmp_path / "missing.json")

    assert active_profile == DEFAULT_PROFILE_NAME
    assert profiles == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "projection_settings.json"
    profiles = {
        "Default": {"retirement_age": 62, "annual_income": 90000.0},
        "Retire Early": {"retirement_age": 50, "annual_income": 120000.0},
    }

    save_projection_profiles(profiles, "Retire Early", path=path)
    active_profile, loaded_profiles = load_projection_profiles(path)

    assert active_profile == "Retire Early"
    assert loaded_profiles == profiles


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "projection_settings.json"
    save_projection_profiles({"Default": {"retirement_age": 62}}, "Default", path=path)

    raw = json.loads(path.read_text())
    assert raw == {"active_profile": "Default", "profiles": {"Default": {"retirement_age": 62}}}


def test_load_migrates_old_flat_format_into_default_profile(tmp_path):
    path = tmp_path / "projection_settings.json"
    path.write_text(json.dumps({"retirement_age": 62, "annual_income": 90000.0}))

    active_profile, profiles = load_projection_profiles(path)

    assert active_profile == DEFAULT_PROFILE_NAME
    assert profiles == {DEFAULT_PROFILE_NAME: {"retirement_age": 62, "annual_income": 90000.0}}


def test_load_migrates_old_empty_flat_format_into_no_profiles(tmp_path):
    path = tmp_path / "projection_settings.json"
    path.write_text(json.dumps({}))

    active_profile, profiles = load_projection_profiles(path)

    assert active_profile == DEFAULT_PROFILE_NAME
    assert profiles == {}


def test_load_corrupt_file_returns_no_profiles(tmp_path):
    path = tmp_path / "projection_settings.json"
    path.write_text("not json")

    active_profile, profiles = load_projection_profiles(path)

    assert active_profile == DEFAULT_PROFILE_NAME
    assert profiles == {}
