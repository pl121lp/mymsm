import json

from projection_settings import load_projection_settings, save_projection_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_projection_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "projection_settings.json"
    settings = {"retirement_age": 62, "annual_income": 90000.0}

    save_projection_settings(settings, path=path)

    assert load_projection_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "projection_settings.json"
    save_projection_settings({"retirement_age": 62}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"retirement_age": 62}
