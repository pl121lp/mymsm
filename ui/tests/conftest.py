import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "etl"))

import duckdb
import pytest

from schema import apply_schema


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE), "
        "(2, 'Old Card', 'Credit', TRUE)"
    )
    connection.execute("INSERT INTO categories VALUES (10, 'Groceries')")
    connection.execute("INSERT INTO payees VALUES (100, 'Store A')")
    connection.execute(
        "INSERT INTO transactions VALUES "
        "(1000, 1, 10, 100, '2024-03-15', -52.30, 'weekly shop'), "
        "(1001, 1, NULL, NULL, '2024-03-10', 1000.00, NULL)"
    )
    yield connection
    connection.close()
