import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "etl"))

import duckdb
import pytest

from schema import apply_schema


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE, 100.00, 'USD'), "
        "(2, 'Old Card', 'Credit', TRUE, 0.00, 'USD'), "
        "(3, 'Brokerage', '5', FALSE, 0.00, 'SEK')"
    )
    connection.execute("INSERT INTO categories VALUES (10, 'Groceries')")
    connection.execute("INSERT INTO payees VALUES (100, 'Store A')")
    connection.execute("INSERT INTO securities VALUES (500, 'Vanguard Total Stock Market Index')")
    connection.execute(
        "INSERT INTO transactions VALUES "
        "(1000, 1, 10, 100, '2024-03-15', -52.30, 'weekly shop', NULL, NULL, NULL, NULL), "
        "(1001, 1, NULL, NULL, '2024-03-10', 1000.00, NULL, NULL, NULL, NULL, NULL), "
        "(3000, 3, NULL, NULL, '2024-01-10', 147.12, NULL, 500, '1', 8.0, 18.39), "
        "(3001, 3, NULL, NULL, '2024-02-10', 64.62, NULL, 500, '1', 3.0, 21.54), "
        "(3002, 3, NULL, NULL, '2024-03-01', -22.63, NULL, 500, '2', 1.0, 22.63), "
        "(3003, 3, NULL, NULL, '2024-03-05', 0.00, 'RSU grant', 500, '17', 5.0, 100.00)"
    )
    yield connection
    connection.close()


@pytest.fixture
def dict_conn():
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE, 0.00, 'USD'), "
        "(2, 'Savings', 'Bank', FALSE, 0.00, 'USD'), "
        "(3, 'Brokerage A', '5', FALSE, 0.00, 'USD'), "
        "(4, 'Brokerage B', '5', FALSE, 0.00, 'USD')"
    )
    connection.execute(
        "INSERT INTO categories VALUES (10, 'Utilities'), (20, 'Groceries')"
    )
    connection.execute(
        "INSERT INTO payees VALUES (100, 'Store A'), (101, 'Store B')"
    )
    connection.execute(
        "INSERT INTO securities VALUES "
        "(500, 'Vanguard Total Stock Market Index'), (501, 'Apple Inc')"
    )
    connection.execute(
        "INSERT INTO transactions VALUES "
        "(1000, 1, 20, 100, '2024-03-15', -52.30, 'weekly shop', NULL, NULL, NULL, NULL), "
        "(1001, 2, 20, 101, '2024-03-10', -20.00, 'snacks', NULL, NULL, NULL, NULL), "
        "(1002, 1, 10, NULL, '2024-03-01', -75.00, 'electric bill', NULL, NULL, NULL, NULL), "
        "(3000, 3, NULL, NULL, '2024-01-10', 147.12, NULL, 500, '1', 8.0, 18.39), "
        "(3001, 3, NULL, NULL, '2024-02-10', 64.62, NULL, 500, '1', 3.0, 21.54), "
        "(3002, 3, NULL, NULL, '2024-03-01', -22.63, NULL, 500, '2', 1.0, 22.63), "
        "(4000, 4, NULL, NULL, '2024-01-15', 200.00, NULL, 500, '1', 10.0, 20.00), "
        "(4001, 4, NULL, NULL, '2024-02-20', -50.00, NULL, 500, '2', 2.0, 25.00)"
    )
    yield connection
    connection.close()
