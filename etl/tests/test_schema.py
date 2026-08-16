import duckdb

from schema import apply_schema


def test_apply_schema_creates_expected_tables():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert tables == {"accounts", "categories", "payees", "transactions"}
