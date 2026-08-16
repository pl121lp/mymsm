from pathlib import Path

from load import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_writes_expected_row_counts(tmp_path):
    db_path = tmp_path / "test.duckdb"
    summary = load(FIXTURES, db_path)
    assert summary == {"accounts": 3, "categories": 2, "payees": 2, "transactions": 3}
    assert db_path.exists()
