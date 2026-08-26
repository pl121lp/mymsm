"""Backs up the database and JSON configs on program exit.

Each backup goes into its own timestamped subfolder under backups/, so
past backups are never overwritten.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

import duckdb

from college_tuition_settings import DEFAULT_SETTINGS_PATH as COLLEGE_TUITION_SETTINGS_PATH
from payee_aliases import DEFAULT_ALIASES_PATH as PAYEE_ALIASES_PATH
from projection_settings import DEFAULT_SETTINGS_PATH as PROJECTION_SETTINGS_PATH

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "money.duckdb"
BACKUPS_DIR = REPO_ROOT / "backups"

CONFIG_PATHS = [
    PAYEE_ALIASES_PATH,
    PROJECTION_SETTINGS_PATH,
    COLLEGE_TUITION_SETTINGS_PATH,
]


def backup_on_exit(conn, backups_dir=BACKUPS_DIR, db_path=DB_PATH):
    """Copies the database and any existing JSON configs into a new
    timestamped subfolder of backups_dir. Errors are logged rather than
    raised, so a failed backup never blocks the app from closing."""
    try:
        destination = backups_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        destination.mkdir(parents=True, exist_ok=True)

        conn.execute("CHECKPOINT")
        if db_path.exists():
            shutil.copy2(db_path, destination / db_path.name)

        for config_path in CONFIG_PATHS:
            if config_path.exists():
                shutil.copy2(config_path, destination / config_path.name)
    except (OSError, duckdb.Error):
        logger.exception("Backup on exit failed")
