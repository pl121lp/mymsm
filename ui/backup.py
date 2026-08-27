"""Backs up the database and config folder on program exit.

Each backup goes into its own timestamped subfolder under backups/, so
past backups are never overwritten.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "money.duckdb"
CONFIG_DIR = REPO_ROOT / "config"
BACKUPS_DIR = REPO_ROOT / "backups"


def backup_on_exit(conn, backups_dir=BACKUPS_DIR, db_path=DB_PATH, config_dir=CONFIG_DIR):
    """Copies the database and the config/ folder into a new timestamped
    subfolder of backups_dir. Errors are logged rather than raised, so a
    failed backup never blocks the app from closing."""
    try:
        destination = backups_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        destination.mkdir(parents=True, exist_ok=True)

        conn.execute("CHECKPOINT")
        if db_path.exists():
            shutil.copy2(db_path, destination / db_path.name)

        if config_dir.exists():
            shutil.copytree(config_dir, destination / config_dir.name)
    except (OSError, duckdb.Error):
        logger.exception("Backup on exit failed")
