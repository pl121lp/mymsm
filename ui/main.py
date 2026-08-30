"""Entry point for the Money Browser desktop UI."""

import sys
from pathlib import Path

import duckdb
from PySide6.QtWidgets import QApplication, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_window import MainWindow

DB_PATH = Path(__file__).resolve().parent.parent / "money.duckdb"


def main():
    app = QApplication(sys.argv)

    if not DB_PATH.exists():
        QMessageBox.critical(
            None,
            "Money Browser",
            f"No database found at {DB_PATH}.\n"
            'Run ./extract-data-to-db.sh "<file.mny>" first.',
        )
        sys.exit(1)

    try:
        conn = duckdb.connect(str(DB_PATH))
    except duckdb.IOException as exc:
        QMessageBox.critical(
            None,
            "Money Browser",
            f"Could not open {DB_PATH}:\n{exc}\n\n"
            "It may be locked by another running instance of this app.",
        )
        sys.exit(1)

    # Backfills is_favorite on a pre-existing money.duckdb (etl/schema.py's version
    # of this column is NOT NULL, but DuckDB can't add that constraint via ALTER
    # COLUMN on a table -- like accounts -- that other tables reference by
    # foreign key, so this column stays nullable on migrated databases; every
    # write path (add_account's INSERT, set_account_favorite) always supplies an
    # explicit boolean, so a NULL can't actually occur in practice).
    conn.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN DEFAULT FALSE")

    window = MainWindow(conn)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
