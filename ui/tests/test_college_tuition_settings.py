import json

from college_tuition_settings import load_college_tuition_settings, save_college_tuition_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_college_tuition_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    settings = {"contribution_end_year": 2036, "annual_return_rate": 6.0}

    save_college_tuition_settings(settings, path=path)

    assert load_college_tuition_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    save_college_tuition_settings({"contribution_end_year": 2036}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"contribution_end_year": 2036}


def test_load_malformed_file_returns_empty(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    path.write_text("{not valid json")

    assert load_college_tuition_settings(path) == {}
