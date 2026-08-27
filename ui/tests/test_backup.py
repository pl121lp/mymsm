from unittest.mock import MagicMock, patch

from backup import backup_on_exit


def test_creates_timestamped_subfolder(conn, tmp_path):
    with patch("backup.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "20260826_120000"
        backup_on_exit(
            conn,
            backups_dir=tmp_path / "backups",
            db_path=tmp_path / "money.duckdb",
            config_dir=tmp_path / "config",
        )

    assert (tmp_path / "backups" / "20260826_120000").is_dir()


def test_copies_db_and_config_folder(conn, tmp_path):
    db_path = tmp_path / "money.duckdb"
    db_path.write_bytes(b"fake db contents")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "projection_settings.json").write_text("{}")
    (config_dir / "app_settings.json").write_text('{"dark_mode": true}')

    backup_on_exit(conn, backups_dir=tmp_path / "backups", db_path=db_path, config_dir=config_dir)

    [destination] = (tmp_path / "backups").iterdir()
    assert (destination / "money.duckdb").read_bytes() == b"fake db contents"
    assert (destination / "config" / "projection_settings.json").read_text() == "{}"
    assert (destination / "config" / "app_settings.json").read_text() == '{"dark_mode": true}'


def test_skips_missing_config_dir(conn, tmp_path):
    db_path = tmp_path / "money.duckdb"
    db_path.write_bytes(b"fake db contents")

    backup_on_exit(
        conn,
        backups_dir=tmp_path / "backups",
        db_path=db_path,
        config_dir=tmp_path / "missing_config",
    )

    [destination] = (tmp_path / "backups").iterdir()
    assert [p.name for p in destination.iterdir()] == ["money.duckdb"]


def test_checkpoints_connection_before_copying(tmp_path):
    mock_conn = MagicMock()

    backup_on_exit(
        mock_conn,
        backups_dir=tmp_path / "backups",
        db_path=tmp_path / "money.duckdb",
        config_dir=tmp_path / "config",
    )

    mock_conn.execute.assert_any_call("CHECKPOINT")


def test_logs_and_does_not_raise_on_failure(conn, tmp_path):
    unwritable_parent = tmp_path / "not_a_directory"
    unwritable_parent.write_text("")  # a file, so mkdir underneath it fails

    backup_on_exit(
        conn,
        backups_dir=unwritable_parent / "backups",
        db_path=tmp_path / "money.duckdb",
        config_dir=tmp_path / "config",
    )
