import json

from rsu_tax_settings import load_rsu_tax_settings, save_rsu_tax_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_rsu_tax_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "rsu_tax_settings.json"
    settings = {"tax_rate": 32.5}

    save_rsu_tax_settings(settings, path=path)

    assert load_rsu_tax_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "rsu_tax_settings.json"
    save_rsu_tax_settings({"tax_rate": 32.5}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"tax_rate": 32.5}
