# Microsoft Money Extraction to DuckDB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract accounts, transactions, categories, and payees from the user's Microsoft Money `.mny` file into a DuckDB database, with no dependency on Microsoft Money and no manual/GUI steps.

**Architecture:** Two independently-rerunnable stages orchestrated by `run.sh`: a Java/Maven tool (`extract-mny/`) that opens the `.mny` file directly via `jackcess`/`jackcess-encrypt` and dumps every internal table to raw CSVs plus a schema manifest; and a Python tool (`etl/`, run in a project-local `.venv`) that transforms those raw CSVs into a normalized schema and loads them into `money.duckdb`.

**Tech Stack:** Java 17 + Maven + Jackcess/Jackcess Encrypt (extraction); Python 3.10+ + DuckDB + pytest (transform/load); Bash (orchestration).

**Spec:** `docs/superpowers/specs/2026-08-15-money-extraction-design.md`

## Global Constraints

- Java dependencies pinned exactly: `com.healthmarketscience.jackcess:jackcess:4.0.8`, `com.healthmarketscience.jackcess:jackcess-encrypt:4.0.3`.
- Python dependencies install only into a project-local `.venv` — never globally.
- Target database is DuckDB (file `money.duckdb` at repo root).
- Data scope is accounts, transactions, categories, payees only — no investments/securities, budgets, or scheduled transactions.
- `*.mny`, `*.mbf`, `data/raw/`, and `money.duckdb` must never be committed to git (sensitive personal financial data).
- The Java extraction stage must be fully scriptable (no GUI, no manual steps) — this is the reason the plan uses `jackcess`/`jackcess-encrypt` directly rather than a GUI tool.
- Money's internal table/column names (`ACCT`, `TRN`, `CAT`, `PAY`, etc.) are undocumented, community-reverse-engineered best guesses — the transform layer must be defensive (skip and log malformed rows rather than crash) and its column mapping must be easy to correct after seeing the real file's manifest.

---

### Task 1: Java extractor scaffold + CSV writer

**Files:**
- Create: `extract-mny/pom.xml`
- Create: `extract-mny/src/main/java/com/mymsm/extract/CsvWriter.java`
- Create: `extract-mny/src/test/java/com/mymsm/extract/CsvWriterTest.java`

**Interfaces:**
- Produces: `CsvWriter.escapeField(Object value) -> String` and `CsvWriter.writeRow(Writer out, List<Object> fields) -> void` (throws `IOException`), used by Task 2's `Main.java`.

- [ ] **Step 1: Write `pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.mymsm</groupId>
  <artifactId>extract-mny</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <junit.version>5.10.2</junit.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.healthmarketscience.jackcess</groupId>
      <artifactId>jackcess</artifactId>
      <version>4.0.8</version>
    </dependency>
    <dependency>
      <groupId>com.healthmarketscience.jackcess</groupId>
      <artifactId>jackcess-encrypt</artifactId>
      <version>4.0.3</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <finalName>extract-mny</finalName>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.2</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>com.mymsm.extract.Main</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

- [ ] **Step 2: Write the failing test**

```java
package com.mymsm.extract;

import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.io.StringWriter;
import java.util.Arrays;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CsvWriterTest {

    @Test
    void escapesFieldsContainingComma() {
        assertEquals("\"a,b\"", CsvWriter.escapeField("a,b"));
    }

    @Test
    void escapesFieldsContainingQuotes() {
        assertEquals("\"say \"\"hi\"\"\"", CsvWriter.escapeField("say \"hi\""));
    }

    @Test
    void leavesPlainFieldsUnquoted() {
        assertEquals("plain", CsvWriter.escapeField("plain"));
    }

    @Test
    void nullBecomesEmptyString() {
        assertEquals("", CsvWriter.escapeField(null));
    }

    @Test
    void writeRowJoinsFieldsWithCommaAndNewline() throws IOException {
        StringWriter sw = new StringWriter();
        CsvWriter.writeRow(sw, Arrays.asList("a", "b,c", 3));
        assertEquals("a,\"b,c\",3\n", sw.toString());
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd extract-mny && mvn -q test`
Expected: FAIL — compile error, `CsvWriter` does not exist.

- [ ] **Step 4: Implement `CsvWriter`**

```java
package com.mymsm.extract;

import java.io.IOException;
import java.io.Writer;
import java.util.List;

public final class CsvWriter {

    private CsvWriter() {}

    public static String escapeField(Object value) {
        String s = value == null ? "" : value.toString();
        boolean needsQuoting = s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r");
        if (!needsQuoting) {
            return s;
        }
        return "\"" + s.replace("\"", "\"\"") + "\"";
    }

    public static void writeRow(Writer out, List<Object> fields) throws IOException {
        for (int i = 0; i < fields.size(); i++) {
            if (i > 0) {
                out.write(",");
            }
            out.write(escapeField(fields.get(i)));
        }
        out.write("\n");
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd extract-mny && mvn -q test`
Expected: PASS (5 tests, 0 failures)

- [ ] **Step 6: Commit**

```bash
git add extract-mny/pom.xml extract-mny/src/main/java/com/mymsm/extract/CsvWriter.java extract-mny/src/test/java/com/mymsm/extract/CsvWriterTest.java
git commit -m "Add Java extractor scaffold with CSV writer"
```

---

### Task 2: Java `.mny` extractor (`Main`)

**Files:**
- Create: `extract-mny/src/main/java/com/mymsm/extract/Main.java`

**Interfaces:**
- Consumes: `CsvWriter.writeRow(Writer, List<Object>)` from Task 1.
- Produces: an executable jar (`extract-mny/target/extract-mny.jar`) invoked as `java -jar extract-mny.jar <input.mny> <output_dir>`, which writes `<output_dir>/<TABLE>.csv` for every table plus `<output_dir>/manifest.csv` with columns `table,row_count,column_name,column_type`. Task 6/8 (the pipeline) and `run.sh` (Task 7) depend on this exact CLI contract and manifest format.

There is no real `.mny` fixture to unit test against (it's sensitive user data, and the encryption is only meaningfully testable against a real file) — this task's verification is a manual run against the real file already present in the repo root (`My Money.mny`), per Step 3 below.

- [ ] **Step 1: Implement `Main.java`**

```java
package com.mymsm.extract;

import com.healthmarketscience.jackcess.CryptCodecProvider;
import com.healthmarketscience.jackcess.Database;
import com.healthmarketscience.jackcess.DatabaseBuilder;
import com.healthmarketscience.jackcess.Column;
import com.healthmarketscience.jackcess.Table;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class Main {

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: extract-mny <input.mny> <output_dir>");
            System.exit(2);
            return;
        }
        File input = new File(args[0]);
        File outputDir = new File(args[1]);
        if (!outputDir.exists() && !outputDir.mkdirs()) {
            throw new IOException("Could not create output directory: " + outputDir);
        }

        try (Database db = new DatabaseBuilder(input)
                .setReadOnly(true)
                .setCodecProvider(new CryptCodecProvider())
                .open()) {

            File manifestFile = new File(outputDir, "manifest.csv");
            try (Writer manifest = new BufferedWriter(new FileWriter(manifestFile, StandardCharsets.UTF_8))) {
                List<Object> header = new ArrayList<>();
                header.add("table");
                header.add("row_count");
                header.add("column_name");
                header.add("column_type");
                CsvWriter.writeRow(manifest, header);

                for (String tableName : db.getTableNames()) {
                    Table table = db.getTable(tableName);
                    int rowCount = dumpTable(table, tableName, outputDir);
                    for (Column column : table.getColumns()) {
                        List<Object> manifestRow = new ArrayList<>();
                        manifestRow.add(tableName);
                        manifestRow.add(rowCount);
                        manifestRow.add(column.getName());
                        manifestRow.add(column.getType().toString());
                        CsvWriter.writeRow(manifest, manifestRow);
                    }
                    System.out.println("Dumped " + tableName + ": " + rowCount + " rows");
                }
            }
        }
    }

    private static int dumpTable(Table table, String tableName, File outputDir) throws IOException {
        List<String> columnNames = new ArrayList<>();
        for (Column column : table.getColumns()) {
            columnNames.add(column.getName());
        }

        File tableFile = new File(outputDir, tableName + ".csv");
        int rowCount = 0;
        try (Writer out = new BufferedWriter(new FileWriter(tableFile, StandardCharsets.UTF_8))) {
            List<Object> header = new ArrayList<>(columnNames);
            CsvWriter.writeRow(out, header);
            for (Map<String, Object> row : table) {
                List<Object> values = new ArrayList<>();
                for (String columnName : columnNames) {
                    values.add(row.get(columnName));
                }
                CsvWriter.writeRow(out, values);
                rowCount++;
            }
        }
        return rowCount;
    }
}
```

- [ ] **Step 2: Build the jar**

Run: `cd extract-mny && mvn -q package`
Expected: BUILD SUCCESS, `target/extract-mny.jar` exists.

- [ ] **Step 3: Manually verify against the real file**

Run (from repo root):
```bash
java -jar extract-mny/target/extract-mny.jar "My Money.mny" data/raw
```
Expected: exits 0, prints one `Dumped <TABLE>: <N> rows` line per table, and `data/raw/manifest.csv` plus one CSV per table exist and are non-empty. If it fails to open/decrypt the file, the jackcess exception message will explain why (e.g. wrong codec, corrupt file) — do not proceed until this succeeds.

- [ ] **Step 4: Commit**

```bash
git add extract-mny/src/main/java/com/mymsm/extract/Main.java
git commit -m "Add Main extractor: dumps all Money tables to CSV plus a manifest"
```

(`data/raw/` itself is gitignored — see Task 7 — so this commit is code only.)

---

### Task 3: Python project scaffold + `moneytypes.py`

**Files:**
- Create: `etl/requirements.txt`
- Create: `etl/requirements-dev.txt`
- Create: `etl/tests/conftest.py`
- Create: `etl/moneytypes.py`
- Create: `etl/tests/test_moneytypes.py`

**Interfaces:**
- Produces: `convert_date(raw: str) -> date`, `convert_currency(raw: str, scale: Decimal = MONEY_SCALE) -> Decimal`, and the module-level `MONEY_SCALE: Decimal` constant, all in `etl/moneytypes.py`. Task 5 (`transform.py`) imports and uses these.
- Produces: `etl/tests/conftest.py`, which every later `etl/tests/*` file relies on to make `etl/*.py` importable during `pytest` runs.

- [ ] **Step 1: Create the venv and dependency files**

```bash
python3 -m venv .venv
```

`etl/requirements.txt`:
```
duckdb>=1.1.0
```

`etl/requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0.0
```

```bash
.venv/bin/pip install -q -r etl/requirements-dev.txt
```

- [ ] **Step 2: Write `etl/tests/conftest.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 3: Write the failing tests**

```python
# etl/tests/test_moneytypes.py
from datetime import date
from decimal import Decimal

import pytest

from moneytypes import convert_currency, convert_date


def test_convert_date_from_iso_string():
    assert convert_date("2024-03-15") == date(2024, 3, 15)


def test_convert_date_from_iso_datetime_string():
    assert convert_date("2024-03-15T00:00:00") == date(2024, 3, 15)


def test_convert_date_from_ole_serial_epoch():
    assert convert_date("0") == date(1899, 12, 30)


def test_convert_date_from_ole_serial_one_day_later():
    assert convert_date("2") == date(1900, 1, 1)


def test_convert_date_rejects_empty():
    with pytest.raises(ValueError):
        convert_date("")


def test_convert_currency_from_decimal_string():
    assert convert_currency("1234.56") == Decimal("1234.56")


def test_convert_currency_from_scaled_integer():
    assert convert_currency("12345600") == Decimal("1234.56")


def test_convert_currency_rejects_garbage():
    with pytest.raises(ValueError):
        convert_currency("not-a-number")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest etl/tests/test_moneytypes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'moneytypes'`.

- [ ] **Step 5: Implement `etl/moneytypes.py`**

```python
"""Type conversions for values pulled from Money's raw exported tables.

Money's on-disk representation for dates and currency amounts is not
officially documented. The jackcess extractor may have already decoded
DATETIME/MONEY columns to plain ISO strings / decimal strings (if Money
used Jet's native DATETIME/MONEY column types), or the raw CSV may contain
bare integers (if Money stored these as scaled integers in generic NUMBER
columns instead). These functions handle both cases; MONEY_SCALE should be
verified against a known real balance the first time this runs against
real data (see README.md).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

OLE_AUTOMATION_EPOCH = date(1899, 12, 30)

MONEY_SCALE = Decimal(10000)


def convert_date(raw: str) -> date:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty date value")

    try:
        return datetime.fromisoformat(raw.split(" ")[0].split("T")[0]).date()
    except ValueError:
        pass

    try:
        serial = float(raw)
    except ValueError as exc:
        raise ValueError(f"unrecognized date value: {raw!r}") from exc
    return OLE_AUTOMATION_EPOCH + timedelta(days=serial)


def convert_currency(raw: str, scale: Decimal = MONEY_SCALE) -> Decimal:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty currency value")

    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"unrecognized currency value: {raw!r}") from exc

    if "." in raw:
        return value

    return value / scale
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest etl/tests/test_moneytypes.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Commit**

```bash
git add etl/requirements.txt etl/requirements-dev.txt etl/tests/conftest.py etl/moneytypes.py etl/tests/test_moneytypes.py
git commit -m "Add Python scaffold and Money date/currency type conversions"
```

---

### Task 4: DuckDB schema + column mapping config

**Files:**
- Create: `etl/schema.py`
- Create: `etl/tests/test_schema.py`
- Create: `etl/column_map.py`

**Interfaces:**
- Produces: `apply_schema(conn: duckdb.DuckDBPyConnection) -> None` in `etl/schema.py`, applying DDL for `accounts`, `categories`, `payees`, `transactions`. Used by Task 6 (`load.py`).
- Produces: `ACCOUNTS`, `CATEGORIES`, `PAYEES`, `TRANSACTIONS` dicts in `etl/column_map.py`, mapping normalized field names to Money's raw table/column names. Used by Task 5 (`transform.py`).

- [ ] **Step 1: Write the failing test**

```python
# etl/tests/test_schema.py
import duckdb

from schema import apply_schema


def test_apply_schema_creates_expected_tables():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert tables == {"accounts", "categories", "payees", "transactions"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest etl/tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'schema'`.

- [ ] **Step 3: Implement `etl/schema.py`**

```python
"""DuckDB schema for the extracted Money data."""

import duckdb

SCHEMA_SQL = """
CREATE TABLE accounts (
    account_id    BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL,
    account_type  VARCHAR,
    is_closed     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE categories (
    category_id   BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL
);

CREATE TABLE payees (
    payee_id      BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL
);

CREATE TABLE transactions (
    transaction_id  BIGINT PRIMARY KEY,
    account_id      BIGINT NOT NULL REFERENCES accounts(account_id),
    category_id     BIGINT REFERENCES categories(category_id),
    payee_id        BIGINT REFERENCES payees(payee_id),
    txn_date        DATE NOT NULL,
    amount          DECIMAL(18,4) NOT NULL,
    memo            VARCHAR
);

CREATE INDEX idx_transactions_date ON transactions(txn_date);
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_category ON transactions(category_id);
"""


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_SQL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest etl/tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Create `etl/column_map.py`**

```python
"""Mapping from Money's raw internal table/column names to normalized
fields.

These names come from prior community reverse-engineering of the Money
file format (not official documentation) and are the best known guesses
as of writing. THE FIRST TIME this runs against a real .mny export,
compare these against data/raw/manifest.csv (which lists every real
table, column, and jackcess-reported column type) and correct any
mismatches here before trusting the output. See README.md.
"""

ACCOUNTS = {
    "table": "ACCT",
    "id": "hacct",
    "name": "szFull",
    "account_type": "at",
    "is_closed": "fClosed",
}

CATEGORIES = {
    "table": "CAT",
    "id": "hcat",
    "name": "szFull",
}

PAYEES = {
    "table": "PAY",
    "id": "hpay",
    "name": "szFull",
}

TRANSACTIONS = {
    "table": "TRN",
    "id": "htrn",
    "account_id": "hacct",
    "category_id": "hcat",
    "payee_id": "hpay",
    "date": "dt",
    "amount": "amt",
    "memo": "mem",
}
```

- [ ] **Step 6: Commit**

```bash
git add etl/schema.py etl/tests/test_schema.py etl/column_map.py
git commit -m "Add DuckDB schema and Money column-name mapping config"
```

---

### Task 5: `transform.py` — raw CSVs to normalized rows

**Files:**
- Create: `etl/tests/fixtures/ACCT.csv`
- Create: `etl/tests/fixtures/CAT.csv`
- Create: `etl/tests/fixtures/PAY.csv`
- Create: `etl/tests/fixtures/TRN.csv`
- Create: `etl/transform.py`
- Create: `etl/tests/test_transform.py`

**Interfaces:**
- Consumes: `ACCOUNTS`, `CATEGORIES`, `PAYEES`, `TRANSACTIONS` from `etl/column_map.py` (Task 4); `convert_date`, `convert_currency` from `etl/moneytypes.py` (Task 3).
- Produces: `build_accounts(raw_dir: Path) -> list[dict]`, `build_categories(raw_dir: Path) -> list[dict]`, `build_payees(raw_dir: Path) -> list[dict]`, `build_transactions(raw_dir: Path, known_account_ids: set[int], known_category_ids: set[int], known_payee_ids: set[int]) -> list[dict]`. Used by Task 6 (`load.py`).

- [ ] **Step 1: Create fixture CSVs**

`etl/tests/fixtures/ACCT.csv`:
```
hacct,szFull,at,fClosed
1,Checking,Bank,0
2,Savings,Bank,0
3,Old Card,Credit,1
```

`etl/tests/fixtures/CAT.csv`:
```
hcat,szFull
10,Groceries
11,Rent
```

`etl/tests/fixtures/PAY.csv`:
```
hpay,szFull
100,Whole Foods
101,Landlord Inc
```

`etl/tests/fixtures/TRN.csv`:
```
htrn,hacct,hcat,hpay,dt,amt,mem
1000,1,10,100,2024-01-05,-52.30,Weekly groceries
1001,1,11,101,2024-01-01,-1200.00,January rent
1002,1,999,100,2024-01-06,-10.00,Unknown category should be nulled
1003,999,10,100,2024-01-07,-5.00,Unknown account should be skipped
```

- [ ] **Step 2: Write the failing tests**

```python
# etl/tests/test_transform.py
from pathlib import Path

from transform import build_accounts, build_categories, build_payees, build_transactions

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_accounts():
    accounts = build_accounts(FIXTURES)
    assert len(accounts) == 3
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["name"] == "Checking"
    assert checking["is_closed"] is False
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["is_closed"] is True


def test_build_categories():
    categories = build_categories(FIXTURES)
    assert {c["category_id"] for c in categories} == {10, 11}


def test_build_payees():
    payees = build_payees(FIXTURES)
    assert {p["payee_id"] for p in payees} == {100, 101}


def test_build_transactions_resolves_known_ids_and_amount():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    ids = {t["transaction_id"] for t in transactions}
    assert ids == {1000, 1001, 1002}
    groceries = next(t for t in transactions if t["transaction_id"] == 1000)
    assert str(groceries["amount"]) == "-52.30"
    assert groceries["category_id"] == 10


def test_build_transactions_nulls_unknown_category():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    unknown_cat_txn = next(t for t in transactions if t["transaction_id"] == 1002)
    assert unknown_cat_txn["category_id"] is None


def test_build_transactions_skips_unknown_account():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    assert all(t["transaction_id"] != 1003 for t in transactions)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest etl/tests/test_transform.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'transform'`.

- [ ] **Step 4: Implement `etl/transform.py`**

```python
"""Reads Money's raw exported CSV tables and builds normalized rows for
loading into DuckDB. Defensive: rows that don't match the expected shape
are logged and skipped rather than aborting the whole load.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

from column_map import ACCOUNTS, CATEGORIES, PAYEES, TRANSACTIONS
from moneytypes import convert_currency, convert_date

logger = logging.getLogger(__name__)


def read_raw_table(raw_dir: Path, table_name: str) -> list[dict]:
    path = raw_dir / f"{table_name}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    return int(float(raw))


def build_accounts(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, ACCOUNTS["table"])
    result = []
    skipped = 0
    for row in rows:
        account_id = _to_int(row.get(ACCOUNTS["id"]))
        name = row.get(ACCOUNTS["name"])
        if account_id is None or not name:
            skipped += 1
            continue
        result.append({
            "account_id": account_id,
            "name": name,
            "account_type": row.get(ACCOUNTS["account_type"]) or None,
            "is_closed": (row.get(ACCOUNTS["is_closed"]) or "").strip() in ("1", "true", "True"),
        })
    logger.info("accounts: built %d, skipped %d", len(result), skipped)
    return result


def build_categories(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, CATEGORIES["table"])
    result = []
    skipped = 0
    for row in rows:
        category_id = _to_int(row.get(CATEGORIES["id"]))
        name = row.get(CATEGORIES["name"])
        if category_id is None or not name:
            skipped += 1
            continue
        result.append({"category_id": category_id, "name": name})
    logger.info("categories: built %d, skipped %d", len(result), skipped)
    return result


def build_payees(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, PAYEES["table"])
    result = []
    skipped = 0
    for row in rows:
        payee_id = _to_int(row.get(PAYEES["id"]))
        name = row.get(PAYEES["name"])
        if payee_id is None or not name:
            skipped += 1
            continue
        result.append({"payee_id": payee_id, "name": name})
    logger.info("payees: built %d, skipped %d", len(result), skipped)
    return result


def build_transactions(
    raw_dir: Path,
    known_account_ids: set[int],
    known_category_ids: set[int],
    known_payee_ids: set[int],
) -> list[dict]:
    rows = read_raw_table(raw_dir, TRANSACTIONS["table"])
    result = []
    skipped = 0
    for row in rows:
        txn_id = _to_int(row.get(TRANSACTIONS["id"]))
        account_id = _to_int(row.get(TRANSACTIONS["account_id"]))
        raw_date = row.get(TRANSACTIONS["date"])
        raw_amount = row.get(TRANSACTIONS["amount"])

        if txn_id is None or account_id is None or account_id not in known_account_ids:
            skipped += 1
            continue
        if not raw_date or not raw_amount:
            skipped += 1
            continue

        try:
            txn_date = convert_date(raw_date)
            amount = convert_currency(raw_amount)
        except ValueError:
            skipped += 1
            continue

        category_id = _to_int(row.get(TRANSACTIONS["category_id"]))
        if category_id is not None and category_id not in known_category_ids:
            category_id = None

        payee_id = _to_int(row.get(TRANSACTIONS["payee_id"]))
        if payee_id is not None and payee_id not in known_payee_ids:
            payee_id = None

        result.append({
            "transaction_id": txn_id,
            "account_id": account_id,
            "category_id": category_id,
            "payee_id": payee_id,
            "txn_date": txn_date,
            "amount": amount,
            "memo": row.get(TRANSACTIONS["memo"]) or None,
        })
    logger.info("transactions: built %d, skipped %d", len(result), skipped)
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest etl/tests/test_transform.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add etl/tests/fixtures etl/transform.py etl/tests/test_transform.py
git commit -m "Add transform layer mapping raw Money CSVs to normalized rows"
```

---

### Task 6: `load.py` — orchestrates transform + DuckDB load

**Files:**
- Create: `etl/load.py`
- Create: `etl/tests/test_load.py`

**Interfaces:**
- Consumes: `apply_schema` (Task 4), `build_accounts`/`build_categories`/`build_payees`/`build_transactions` (Task 5).
- Produces: `load(raw_dir: Path, db_path: Path) -> dict` (returns row-count summary per table) and a `main()` CLI entry point invoked as `python load.py <raw_dir> <output_duckdb_path>`. `run.sh` (Task 7) depends on this exact CLI contract.

- [ ] **Step 1: Write the failing test**

```python
# etl/tests/test_load.py
from pathlib import Path

from load import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_writes_expected_row_counts(tmp_path):
    db_path = tmp_path / "test.duckdb"
    summary = load(FIXTURES, db_path)
    assert summary == {"accounts": 3, "categories": 2, "payees": 2, "transactions": 3}
    assert db_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest etl/tests/test_load.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'load'`.

- [ ] **Step 3: Implement `etl/load.py`**

```python
"""Loads Money data from raw exported CSVs (produced by extract-mny) into
a DuckDB database.

Usage:
    python load.py <raw_dir> <output_duckdb_path>
"""

import logging
import sys
from pathlib import Path

import duckdb

from schema import apply_schema
from transform import build_accounts, build_categories, build_payees, build_transactions


def load(raw_dir: Path, db_path: Path) -> dict:
    accounts = build_accounts(raw_dir)
    categories = build_categories(raw_dir)
    payees = build_payees(raw_dir)
    transactions = build_transactions(
        raw_dir,
        known_account_ids={a["account_id"] for a in accounts},
        known_category_ids={c["category_id"] for c in categories},
        known_payee_ids={p["payee_id"] for p in payees},
    )

    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    try:
        apply_schema(conn)
        conn.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?)",
            [(a["account_id"], a["name"], a["account_type"], a["is_closed"]) for a in accounts],
        )
        conn.executemany(
            "INSERT INTO categories VALUES (?, ?)",
            [(c["category_id"], c["name"]) for c in categories],
        )
        conn.executemany(
            "INSERT INTO payees VALUES (?, ?)",
            [(p["payee_id"], p["name"]) for p in payees],
        )
        conn.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    t["transaction_id"], t["account_id"], t["category_id"], t["payee_id"],
                    t["txn_date"], t["amount"], t["memo"],
                )
                for t in transactions
            ],
        )
    finally:
        conn.close()

    return {
        "accounts": len(accounts),
        "categories": len(categories),
        "payees": len(payees),
        "transactions": len(transactions),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) != 3:
        print("Usage: python load.py <raw_dir> <output_duckdb_path>")
        sys.exit(2)

    raw_dir = Path(sys.argv[1])
    db_path = Path(sys.argv[2])
    summary = load(raw_dir, db_path)

    print("Loaded into", db_path)
    for table, count in summary.items():
        print(f"  {table}: {count} rows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest etl/tests/test_load.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add etl/load.py etl/tests/test_load.py
git commit -m "Add load.py: orchestrates transform and DuckDB load with a row-count summary"
```

---

### Task 7: Orchestration script, gitignore, README

**Files:**
- Create: `.gitignore`
- Create: `run.sh` (executable)
- Create: `README.md`

**Interfaces:**
- Consumes: the Java jar CLI contract from Task 2 and the `load.py` CLI contract from Task 6.

- [ ] **Step 1: Write `.gitignore`**

```
*.mny
*.mbf
data/raw/
money.duckdb
.venv/
extract-mny/target/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Write `run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: ./run.sh <path-to-money-file.mny>" >&2
    exit 2
fi

MNY_FILE="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_DIR="$ROOT_DIR/data/raw"
DB_PATH="$ROOT_DIR/money.duckdb"
VENV_DIR="$ROOT_DIR/.venv"

echo "== Stage 1: extracting raw tables from $MNY_FILE =="
mkdir -p "$RAW_DIR"
( cd "$ROOT_DIR/extract-mny" && mvn -q package )
java -jar "$ROOT_DIR/extract-mny/target/extract-mny.jar" "$MNY_FILE" "$RAW_DIR"

echo "== Stage 2: loading raw tables into DuckDB =="
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$ROOT_DIR/etl/requirements.txt"
fi
"$VENV_DIR/bin/python" "$ROOT_DIR/etl/load.py" "$RAW_DIR" "$DB_PATH"

echo "== Done: $DB_PATH =="
```

```bash
chmod +x run.sh
```

- [ ] **Step 3: Write `README.md`**

```markdown
# mymsm — Microsoft Money data extraction

Extracts accounts, transactions, categories, and payees out of a
Microsoft Money `.mny` file into a DuckDB database, without needing
Microsoft Money installed.

## How it works

Two stages, orchestrated by `run.sh`:

1. **`extract-mny/`** (Java) opens the `.mny` file directly — it's an
   MSISAM-encrypted Jet/Access database — using the open-source
   [Jackcess](https://jackcess.sourceforge.io/) and
   [Jackcess Encrypt](https://jackcessencrypt.sourceforge.io/) libraries,
   and dumps every internal table to `data/raw/<TABLE>.csv`, plus a
   `data/raw/manifest.csv` listing every table's row count and column
   names/types.
2. **`etl/`** (Python) reads those raw CSVs, maps Money's internal
   schema (best-effort, see caveat below) to a clean relational schema,
   and loads it into `money.duckdb`.

## Prerequisites

- JDK 17+ and Maven (for the extraction stage)
- Python 3.10+ (for the load stage)

## Dependencies

**Java** (`extract-mny/pom.xml`, resolved automatically by Maven):
- `com.healthmarketscience.jackcess:jackcess:4.0.8` — reads Jet/Access database files
- `com.healthmarketscience.jackcess:jackcess-encrypt:4.0.3` — adds the MSISAM decryption codec Money uses
- `org.junit.jupiter:junit-jupiter:5.10.2` (test only)

**Python** (`etl/requirements.txt`, installed into a project-local `.venv`):
- `duckdb` — the target database, plus its Python bindings
- `pytest` (dev only, `etl/requirements-dev.txt`) — test runner

## Running

    ./run.sh "My Money.mny"

This builds the Java extractor if needed, runs it against your file into
`data/raw/`, creates `.venv` and installs Python dependencies if needed,
and produces `money.duckdb` in the project root.

Neither the source `.mny`/`.mbf` files nor any generated output
(`data/raw/`, `money.duckdb`) are committed to git — see `.gitignore`.
They all contain your personal financial data.

## Querying the result

    .venv/bin/python -c "
    import duckdb
    conn = duckdb.connect('money.duckdb')
    print(conn.execute('SELECT * FROM accounts').fetchdf())
    "

## Important caveat: column mapping may need adjustment

Money's internal table/column names (`ACCT`, `TRN`, `CAT`, `PAY`, etc.)
are not officially documented — the mapping in `etl/column_map.py` is
based on prior community reverse-engineering and is a best-effort guess.
**The first time you run this against your real file**, open
`data/raw/manifest.csv` and compare it against `etl/column_map.py`: if
any table/column name doesn't match, or if `load.py`'s printed summary
shows more skipped rows than expected, update `etl/column_map.py`
(and, if currency amounts look off by a factor, `MONEY_SCALE` in
`etl/moneytypes.py`) and rerun — no need to redo the Java extraction
step, `etl/load.py` alone can be rerun directly against the existing
`data/raw/`:

    .venv/bin/python etl/load.py data/raw money.duckdb

## Running tests

    cd extract-mny && mvn test && cd ..
    .venv/bin/pip install -r etl/requirements-dev.txt
    .venv/bin/pytest etl/tests
```

- [ ] **Step 4: Verify `run.sh` syntax**

Run: `bash -n run.sh`
Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add .gitignore run.sh README.md
git commit -m "Add orchestration script, gitignore, and README"
```

---

### Task 8: Run against the real file and calibrate the column mapping

**Files:**
- Modify (if needed): `etl/column_map.py`
- Modify (if needed): `etl/moneytypes.py` (`MONEY_SCALE`)

**Interfaces:**
- Consumes: `run.sh` (Task 7) end to end.

This task requires the user's judgment — comparing extracted data against
what they know their real accounts/balances/transactions look like — so
it cannot be fully delegated to an agent without the user reviewing the
output.

- [ ] **Step 1: Run the full pipeline**

```bash
./run.sh "My Money.mny"
```

- [ ] **Step 2: Inspect the manifest**

Open `data/raw/manifest.csv` and compare table names and column names
against `etl/column_map.py`'s `ACCOUNTS`, `CATEGORIES`, `PAYEES`,
`TRANSACTIONS` dicts. Note any mismatches.

- [ ] **Step 3: Check the load summary**

Look at the row counts `load.py` printed (accounts/categories/payees/
transactions). Compare the account count and rough transaction count
against what you'd expect from your real Money file. A big gap (e.g.
most transactions skipped) means `etl/column_map.py` needs correcting —
check the log lines emitted by `transform.py` (`built N, skipped M`) to
see which table is dropping rows.

- [ ] **Step 4: Fix mismatches and reload without re-extracting**

If `etl/column_map.py` needed changes, or if `MONEY_SCALE` in
`etl/moneytypes.py` looks wrong (currency amounts off by a factor of
10/100/1000), edit those files, then rerun just the load stage:

```bash
.venv/bin/python etl/load.py data/raw money.duckdb
```

Repeat Steps 2-4 until the summary counts and a few spot-checked
transactions/balances (query `money.duckdb` directly) look right.

- [ ] **Step 5: Commit any calibration changes**

```bash
git add etl/column_map.py etl/moneytypes.py
git commit -m "Calibrate Money column mapping against real export"
```

(Skip this step if no changes were needed.)
