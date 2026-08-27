import json

from app_settings import load_app_settings, save_app_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_app_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "app_settings.json"
    settings = {"dark_mode": True, "sek_to_usd_rate": 0.095}

    save_app_settings(settings, path=path)

    assert load_app_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "app_settings.json"
    save_app_settings({"dark_mode": True}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"dark_mode": True}
