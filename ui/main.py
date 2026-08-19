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

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    window = MainWindow(conn)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
