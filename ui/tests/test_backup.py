from unittest.mock import MagicMock, patch

from backup import backup_on_exit


def test_creates_timestamped_subfolder(conn, tmp_path):
    with patch("backup.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "20260826_120000"
        backup_on_exit(conn, backups_dir=tmp_path / "backups", db_path=tmp_path / "money.duckdb")

    assert (tmp_path / "backups" / "20260826_120000").is_dir()


def test_copies_db_and_existing_configs(conn, tmp_path):
    db_path = tmp_path / "money.duckdb"
    db_path.write_bytes(b"fake db contents")

    with (
        patch("backup.CONFIG_PATHS", [tmp_path / "projection_settings.json"]),
    ):
        (tmp_path / "projection_settings.json").write_text("{}")
        backup_on_exit(conn, backups_dir=tmp_path / "backups", db_path=db_path)

    [destination] = (tmp_path / "backups").iterdir()
    assert (destination / "money.duckdb").read_bytes() == b"fake db contents"
    assert (destination / "projection_settings.json").read_text() == "{}"


def test_skips_missing_config_files(conn, tmp_path):
    db_path = tmp_path / "money.duckdb"
    db_path.write_bytes(b"fake db contents")

    with patch("backup.CONFIG_PATHS", [tmp_path / "missing.json"]):
        backup_on_exit(conn, backups_dir=tmp_path / "backups", db_path=db_path)

    [destination] = (tmp_path / "backups").iterdir()
    assert [p.name for p in destination.iterdir()] == ["money.duckdb"]


def test_checkpoints_connection_before_copying(tmp_path):
    mock_conn = MagicMock()

    backup_on_exit(mock_conn, backups_dir=tmp_path / "backups", db_path=tmp_path / "money.duckdb")

    mock_conn.execute.assert_any_call("CHECKPOINT")


def test_logs_and_does_not_raise_on_failure(conn, tmp_path):
    unwritable_parent = tmp_path / "not_a_directory"
    unwritable_parent.write_text("")  # a file, so mkdir underneath it fails

    backup_on_exit(
        conn,
        backups_dir=unwritable_parent / "backups",
        db_path=tmp_path / "money.duckdb",
    )
