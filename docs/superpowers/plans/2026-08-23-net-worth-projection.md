# Net Worth Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Net Worth Projection" report to the Reports tab: a control panel of 13 assumption inputs (birth year, retirement age, investment returns, income, tax, inflation, spending, Social Security) driving a two-line chart (Investment Value vs. Net Worth) projected year-by-year into the future.

**Architecture:** A pure calculation module (`projection.py`) computes the year-by-year projection from a plain dataclass of inputs — no Qt or DB dependency, fully unit-testable. A small JSON-persistence module (`projection_settings.py`) mirrors the existing `payee_aliases.py` sibling-file pattern. A new Qt widget (`projection_controls.py`) owns the 13 input spinboxes. `reports_tab.py` wires these three together as a new entry in the existing report list, reusing the existing shared `chart_view` and `charts.build_line_chart`.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets + QtCharts), DuckDB (read-only), pytest, `decimal.Decimal` for all money/rate arithmetic (matching the rest of `ui/`).

**Spec:** `docs/superpowers/specs/2026-08-23-net-worth-projection-design.md`

## Global Constraints

- All money and rate arithmetic in the calculation engine uses `Decimal`, never `float` — Qt spinbox `float` values are converted via `Decimal(str(value))` at the UI/engine boundary, matching the existing `Decimal(str(self.sek_rate_spinbox.value()))` pattern in `main_window.py`.
- Tax applies only to income + Social Security, never to investment growth or withdrawals.
- Net worth is allowed to go negative; it is never floored at zero.
- The "Investment Value" series is pure compounding of the starting balance alone (no contributions/withdrawals); the "Net Worth" series additionally compounds each year's net cash flow (income − tax − spending + Social Security).
- Projection inputs persist to a git-ignored sibling JSON file (`projection_settings.json`), following the existing `payee_aliases.py` pattern — except `starting_investment_value`, which is always recomputed live from current investment-account balances on each report selection and is never read from or written to the persisted file.
- Recomputation happens only when the panel's "Update" button is clicked, not on every keystroke — matching the existing `update_range_button` convention used by other reports.
- No per-year data table in this iteration — chart only, matching the existing "Net worth over time" report's chart-only layout.

---

### Task 1: Projection calculation engine

**Files:**
- Create: `ui/projection.py`
- Test: `ui/tests/test_projection.py`

**Interfaces:**
- Produces:
  - `ProjectionInputs` — a `dataclasses.dataclass` with fields: `birth_year: int`, `end_year: int`, `retirement_age: int`, `starting_investment_value: Decimal`, `return_rate_before_retirement: Decimal`, `return_rate_after_retirement: Decimal`, `annual_income: Decimal`, `tax_rate: Decimal`, `inflation_rate: Decimal`, `spending_before_retirement: Decimal`, `spending_after_retirement: Decimal`, `social_security_annual_amount: Decimal`, `social_security_start_year: int`.
  - `YearlyProjection` — a `typing.NamedTuple` with fields: `year: int`, `age: int`, `retired: bool`, `income: Decimal`, `social_security: Decimal`, `tax: Decimal`, `spending: Decimal`, `net_cash_flow: Decimal`, `investment_value: Decimal`, `net_worth: Decimal`.
  - `compute_projection(inputs: ProjectionInputs, current_year: int | None = None) -> list[YearlyProjection]` — one row per calendar year from `current_year` (defaults to `date.today().year`) through `inputs.end_year` inclusive.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_projection.py`:

```python
from decimal import Decimal

from projection import ProjectionInputs, compute_projection


def _inputs(**overrides):
    defaults = dict(
        birth_year=2000,
        end_year=2024,
        retirement_age=100,
        starting_investment_value=Decimal("0"),
        return_rate_before_retirement=Decimal("0"),
        return_rate_after_retirement=Decimal("0"),
        annual_income=Decimal("0"),
        tax_rate=Decimal("0"),
        inflation_rate=Decimal("0"),
        spending_before_retirement=Decimal("0"),
        spending_after_retirement=Decimal("0"),
        social_security_annual_amount=Decimal("0"),
        social_security_start_year=9999,
    )
    defaults.update(overrides)
    return ProjectionInputs(**defaults)


def test_year_zero_is_a_snapshot_with_no_growth_or_cash_flow():
    inputs = _inputs(
        birth_year=1990,
        end_year=2024,
        retirement_age=40,
        starting_investment_value=Decimal("5000"),
    )

    rows = compute_projection(inputs, current_year=2024)

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    assert row.age == 34
    assert row.retired is False
    assert row.income == Decimal("0")
    assert row.social_security == Decimal("0")
    assert row.tax == Decimal("0")
    assert row.spending == Decimal("0")
    assert row.net_cash_flow == Decimal("0")
    assert row.investment_value == Decimal("5000")
    assert row.net_worth == Decimal("5000")


def test_pre_and_post_retirement_transition_switches_income_and_return_rate():
    inputs = _inputs(
        birth_year=2000,
        end_year=2027,
        retirement_age=26,
        starting_investment_value=Decimal("1000"),
        return_rate_before_retirement=Decimal("0.10"),
        return_rate_after_retirement=Decimal("0.05"),
        annual_income=Decimal("1000"),
        spending_before_retirement=Decimal("200"),
        spending_after_retirement=Decimal("300"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2024].retired is False
    assert by_year[2024].investment_value == Decimal("1000")
    assert by_year[2024].net_worth == Decimal("1000")

    assert by_year[2025].retired is False
    assert by_year[2025].income == Decimal("1000")
    assert by_year[2025].net_cash_flow == Decimal("800")
    assert by_year[2025].investment_value == Decimal("1100")
    assert by_year[2025].net_worth == Decimal("1980")

    assert by_year[2026].retired is True
    assert by_year[2026].income == Decimal("0")
    assert by_year[2026].net_cash_flow == Decimal("-300")
    assert by_year[2026].investment_value == Decimal("1155")
    assert by_year[2026].net_worth == Decimal("1764")

    assert by_year[2027].retired is True
    assert by_year[2027].investment_value == Decimal("1212.75")
    assert by_year[2027].net_worth == Decimal("1537.20")


def test_inflation_escalates_income_and_spending():
    inputs = _inputs(
        birth_year=2000,
        end_year=2026,
        retirement_age=100,
        annual_income=Decimal("1000"),
        spending_before_retirement=Decimal("100"),
        inflation_rate=Decimal("0.10"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].income == Decimal("1100")
    assert by_year[2025].spending == Decimal("110")
    assert by_year[2025].net_worth == Decimal("990")

    assert by_year[2026].income == Decimal("1210")
    assert by_year[2026].spending == Decimal("121")
    assert by_year[2026].net_worth == Decimal("2079")


def test_social_security_starts_only_at_configured_year():
    inputs = _inputs(
        birth_year=1950,
        end_year=2027,
        retirement_age=200,
        social_security_annual_amount=Decimal("500"),
        social_security_start_year=2026,
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].social_security == Decimal("0")
    assert by_year[2025].net_worth == Decimal("0")
    assert by_year[2026].social_security == Decimal("500")
    assert by_year[2026].net_worth == Decimal("500")
    assert by_year[2027].net_worth == Decimal("1000")


def test_tax_applies_to_income_and_social_security_only():
    inputs = _inputs(
        birth_year=1950,
        end_year=2025,
        retirement_age=200,
        annual_income=Decimal("1000"),
        social_security_annual_amount=Decimal("500"),
        social_security_start_year=2024,
        tax_rate=Decimal("0.20"),
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.tax == Decimal("300")
    assert row.net_cash_flow == Decimal("1200")
    assert row.net_worth == Decimal("1200")


def test_net_worth_goes_negative_without_flooring_when_spending_exceeds_resources():
    inputs = _inputs(
        birth_year=2000,
        end_year=2026,
        retirement_age=100,
        spending_before_retirement=Decimal("1000"),
        return_rate_before_retirement=Decimal("0.10"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].net_worth == Decimal("-1100")
    assert by_year[2026].net_worth == Decimal("-2310")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projection'`

- [ ] **Step 3: Write the implementation**

Create `ui/projection.py`:

```python
"""Forward-looking net worth projection, driven by user-entered
assumptions rather than real transaction data (contrast with
models.compute_net_worth_series, which is historical).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional


@dataclass
class ProjectionInputs:
    birth_year: int
    end_year: int
    retirement_age: int
    starting_investment_value: Decimal
    return_rate_before_retirement: Decimal
    return_rate_after_retirement: Decimal
    annual_income: Decimal
    tax_rate: Decimal
    inflation_rate: Decimal
    spending_before_retirement: Decimal
    spending_after_retirement: Decimal
    social_security_annual_amount: Decimal
    social_security_start_year: int


class YearlyProjection(NamedTuple):
    year: int
    age: int
    retired: bool
    income: Decimal
    social_security: Decimal
    tax: Decimal
    spending: Decimal
    net_cash_flow: Decimal
    investment_value: Decimal
    net_worth: Decimal


def compute_projection(
    inputs: ProjectionInputs, current_year: Optional[int] = None
) -> list[YearlyProjection]:
    """Year-by-year projection from current_year through inputs.end_year.

    Year 0 (current_year) is a snapshot at starting_investment_value with
    no cash flow or growth applied yet. Each later year escalates income,
    Social Security, and spending by inflation_rate, stops income (but not
    Social Security) once retired, applies tax_rate to income + Social
    Security only, and compounds both investment_value (market growth
    alone) and net_worth (market growth plus that year's net cash flow) at
    the before/after-retirement return rate. net_worth is never floored at
    zero -- a shortfall keeps compounding as a negative balance.
    """
    if current_year is None:
        current_year = date.today().year

    retirement_year = inputs.birth_year + inputs.retirement_age
    zero = Decimal("0")
    one = Decimal("1")

    rows = [
        YearlyProjection(
            year=current_year,
            age=current_year - inputs.birth_year,
            retired=current_year >= retirement_year,
            income=zero,
            social_security=zero,
            tax=zero,
            spending=zero,
            net_cash_flow=zero,
            investment_value=inputs.starting_investment_value,
            net_worth=inputs.starting_investment_value,
        )
    ]

    for year in range(current_year + 1, inputs.end_year + 1):
        prior = rows[-1]
        years_elapsed = year - current_year
        retired = year >= retirement_year
        inflation_factor = (one + inputs.inflation_rate) ** years_elapsed

        income = zero if retired else inputs.annual_income * inflation_factor
        social_security = (
            inputs.social_security_annual_amount * inflation_factor
            if year >= inputs.social_security_start_year
            else zero
        )
        spending = (
            inputs.spending_after_retirement if retired else inputs.spending_before_retirement
        ) * inflation_factor
        tax = (income + social_security) * inputs.tax_rate
        net_cash_flow = income + social_security - tax - spending

        return_rate = (
            inputs.return_rate_after_retirement if retired else inputs.return_rate_before_retirement
        )
        investment_value = prior.investment_value * (one + return_rate)
        net_worth = (prior.net_worth + net_cash_flow) * (one + return_rate)

        rows.append(
            YearlyProjection(
                year=year,
                age=year - inputs.birth_year,
                retired=retired,
                income=income,
                social_security=social_security,
                tax=tax,
                spending=spending,
                net_cash_flow=net_cash_flow,
                investment_value=investment_value,
                net_worth=net_worth,
            )
        )

    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add ui/projection.py ui/tests/test_projection.py
git commit -m "feat: add net worth projection calculation engine"
```

---

### Task 2: Projection settings persistence

**Files:**
- Create: `ui/projection_settings.py`
- Modify: `.gitignore`
- Test: `ui/tests/test_projection_settings.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SETTINGS_PATH` — `Path`, project root / `projection_settings.json`.
  - `load_projection_settings(path=DEFAULT_SETTINGS_PATH) -> dict` — returns `{}` if the file doesn't exist.
  - `save_projection_settings(settings: dict, path=DEFAULT_SETTINGS_PATH) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_projection_settings.py`:

```python
import json

from projection_settings import load_projection_settings, save_projection_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_projection_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "projection_settings.json"
    settings = {"retirement_age": 62, "annual_income": 90000.0}

    save_projection_settings(settings, path=path)

    assert load_projection_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "projection_settings.json"
    save_projection_settings({"retirement_age": 62}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"retirement_age": 62}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projection_settings'`

- [ ] **Step 3: Write the implementation**

Create `ui/projection_settings.py`:

```python
"""Persisted assumptions for the Net Worth Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(birth year, return rates, retirement age, etc.), not financial records,
so they're kept in a sibling JSON file instead -- same pattern as
payee_aliases.py. starting_investment_value is deliberately never stored
here: it's always recomputed live from current account data.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "projection_settings.json"


def load_projection_settings(path=DEFAULT_SETTINGS_PATH):
    """Returns a flat dict of saved projection input fields, or {} if unset."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_projection_settings(settings, path=DEFAULT_SETTINGS_PATH):
    """settings: flat dict of projection input fields (JSON-serializable)."""
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
```

Modify `.gitignore` — add `projection_settings.json` alongside the existing `payee_aliases.json` entry.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection_settings.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ui/projection_settings.py ui/tests/test_projection_settings.py .gitignore
git commit -m "feat: add projection settings persistence"
```

---

### Task 3: Projection controls panel widget

**Files:**
- Create: `ui/projection_controls.py`
- Test: `ui/tests/test_projection_controls.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure Qt widget).
- Produces:
  - `default_projection_values(today: date | None = None) -> dict` — 12 keys (all `ProjectionInputs` fields except `starting_investment_value`): `birth_year`, `end_year`, `retirement_age`, `return_rate_before_retirement`, `return_rate_after_retirement`, `annual_income`, `tax_rate`, `inflation_rate`, `spending_before_retirement`, `spending_after_retirement`, `social_security_annual_amount`, `social_security_start_year`. Values are plain `int`/`float` (percentages as whole numbers, e.g. `7.0` meaning 7%), suitable for `QSpinBox`/`QDoubleSpinBox.setValue()`.
  - `ProjectionControlsPanel(parent=None, today: date | None = None)` — a `QWidget`. Attributes: `birth_year_spinbox`, `end_year_spinbox`, `retirement_age_spinbox`, `starting_investment_value_spinbox`, `return_rate_before_spinbox`, `return_rate_after_spinbox`, `annual_income_spinbox`, `tax_rate_spinbox`, `inflation_rate_spinbox`, `spending_before_spinbox`, `spending_after_spinbox`, `social_security_amount_spinbox`, `social_security_start_year_spinbox`, `update_button` (all `QSpinBox`/`QDoubleSpinBox`/`QPushButton`).
    - `.values() -> dict` — 13 keys, the 12 above plus `starting_investment_value` (`float`).
    - `.set_values(values: dict) -> None` — applies whichever of the 13 keys are present in `values`; others keep their current widget value.
    - `.updated` — `Signal()`, emitted when `update_button` is clicked.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_projection_controls.py`:

```python
from datetime import date

import pytest

from projection_controls import ProjectionControlsPanel, default_projection_values


def test_default_projection_values_are_relative_to_today():
    values = default_projection_values(today=date(2024, 6, 15))
    assert values == {
        "birth_year": 1984,
        "end_year": 2064,
        "retirement_age": 65,
        "return_rate_before_retirement": 7.0,
        "return_rate_after_retirement": 5.0,
        "annual_income": 80000.0,
        "tax_rate": 20.0,
        "inflation_rate": 3.0,
        "spending_before_retirement": 60000.0,
        "spending_after_retirement": 50000.0,
        "social_security_annual_amount": 20000.0,
        "social_security_start_year": 2051,
    }


def test_panel_initializes_widgets_from_defaults(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    assert panel.birth_year_spinbox.value() == 1984
    assert panel.end_year_spinbox.value() == 2064
    assert panel.retirement_age_spinbox.value() == 65
    assert panel.starting_investment_value_spinbox.value() == pytest.approx(0.0)
    assert panel.return_rate_before_spinbox.value() == pytest.approx(7.0)
    assert panel.return_rate_after_spinbox.value() == pytest.approx(5.0)
    assert panel.annual_income_spinbox.value() == pytest.approx(80000.0)
    assert panel.tax_rate_spinbox.value() == pytest.approx(20.0)
    assert panel.inflation_rate_spinbox.value() == pytest.approx(3.0)
    assert panel.spending_before_spinbox.value() == pytest.approx(60000.0)
    assert panel.spending_after_spinbox.value() == pytest.approx(50000.0)
    assert panel.social_security_amount_spinbox.value() == pytest.approx(20000.0)
    assert panel.social_security_start_year_spinbox.value() == 2051


def test_values_reflects_current_widget_state(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))
    panel.retirement_age_spinbox.setValue(70)
    panel.annual_income_spinbox.setValue(95000.0)

    values = panel.values()

    assert values["retirement_age"] == 70
    assert values["annual_income"] == pytest.approx(95000.0)


def test_set_values_updates_only_the_given_keys(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    panel.set_values({"retirement_age": 62})

    assert panel.retirement_age_spinbox.value() == 62
    assert panel.end_year_spinbox.value() == 2064


def test_clicking_update_button_emits_updated_signal(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))
    calls = []
    panel.updated.connect(lambda: calls.append(True))

    panel.update_button.click()

    assert calls == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection_controls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'projection_controls'`

- [ ] **Step 3: Write the implementation**

Create `ui/projection_controls.py`:

```python
"""Controls panel for the Net Worth Projection report: birth year,
retirement age, investment returns, income/spending, tax, inflation, and
Social Security inputs, laid out in labeled sections with an Update
button.
"""

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def default_projection_values(today=None):
    """Built-in defaults for a first-time (no saved settings) load."""
    today = today or date.today()
    return {
        "birth_year": today.year - 40,
        "end_year": today.year + 40,
        "retirement_age": 65,
        "return_rate_before_retirement": 7.0,
        "return_rate_after_retirement": 5.0,
        "annual_income": 80000.0,
        "tax_rate": 20.0,
        "inflation_rate": 3.0,
        "spending_before_retirement": 60000.0,
        "spending_after_retirement": 50000.0,
        "social_security_annual_amount": 20000.0,
        "social_security_start_year": today.year + 27,
    }


def _year_spinbox(value):
    spinbox = QSpinBox()
    spinbox.setRange(1900, 2200)
    spinbox.setValue(value)
    return spinbox


def _percent_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(-20.0, 100.0)
    spinbox.setDecimals(2)
    spinbox.setSuffix("%")
    spinbox.setValue(value)
    return spinbox


def _dollar_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(0.0, 100_000_000.0)
    spinbox.setDecimals(2)
    spinbox.setSingleStep(1000.0)
    spinbox.setPrefix("$")
    spinbox.setValue(value)
    return spinbox


class ProjectionControlsPanel(QWidget):
    updated = Signal()

    def __init__(self, parent=None, today=None):
        super().__init__(parent)
        defaults = default_projection_values(today)

        self.birth_year_spinbox = _year_spinbox(defaults["birth_year"])
        self.end_year_spinbox = _year_spinbox(defaults["end_year"])
        self.retirement_age_spinbox = QSpinBox()
        self.retirement_age_spinbox.setRange(1, 120)
        self.retirement_age_spinbox.setValue(defaults["retirement_age"])
        self.starting_investment_value_spinbox = _dollar_spinbox(0.0)

        self.return_rate_before_spinbox = _percent_spinbox(defaults["return_rate_before_retirement"])
        self.return_rate_after_spinbox = _percent_spinbox(defaults["return_rate_after_retirement"])

        self.annual_income_spinbox = _dollar_spinbox(defaults["annual_income"])
        self.tax_rate_spinbox = _percent_spinbox(defaults["tax_rate"])
        self.inflation_rate_spinbox = _percent_spinbox(defaults["inflation_rate"])

        self.spending_before_spinbox = _dollar_spinbox(defaults["spending_before_retirement"])
        self.spending_after_spinbox = _dollar_spinbox(defaults["spending_after_retirement"])

        self.social_security_amount_spinbox = _dollar_spinbox(defaults["social_security_annual_amount"])
        self.social_security_start_year_spinbox = _year_spinbox(defaults["social_security_start_year"])

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.updated.emit)

        layout = QVBoxLayout(self)

        timeline_form = QFormLayout()
        timeline_form.addRow("Birth year:", self.birth_year_spinbox)
        timeline_form.addRow("Projection end year:", self.end_year_spinbox)
        timeline_form.addRow("Retirement age:", self.retirement_age_spinbox)
        timeline_form.addRow("Starting investment value:", self.starting_investment_value_spinbox)

        returns_form = QFormLayout()
        returns_form.addRow("Return before retirement:", self.return_rate_before_spinbox)
        returns_form.addRow("Return after retirement:", self.return_rate_after_spinbox)

        income_form = QFormLayout()
        income_form.addRow("Annual income:", self.annual_income_spinbox)
        income_form.addRow("Tax rate:", self.tax_rate_spinbox)
        income_form.addRow("Inflation rate:", self.inflation_rate_spinbox)

        spending_form = QFormLayout()
        spending_form.addRow("Spending before retirement:", self.spending_before_spinbox)
        spending_form.addRow("Spending after retirement:", self.spending_after_spinbox)

        ss_form = QFormLayout()
        ss_form.addRow("Social Security annual amount:", self.social_security_amount_spinbox)
        ss_form.addRow("Social Security start year:", self.social_security_start_year_spinbox)

        layout.addWidget(QLabel("<b>Timeline</b>"))
        layout.addLayout(timeline_form)
        layout.addWidget(QLabel("<b>Investment Returns</b>"))
        layout.addLayout(returns_form)
        layout.addWidget(QLabel("<b>Income &amp; Tax</b>"))
        layout.addLayout(income_form)
        layout.addWidget(QLabel("<b>Spending</b>"))
        layout.addLayout(spending_form)
        layout.addWidget(QLabel("<b>Social Security</b>"))
        layout.addLayout(ss_form)
        layout.addWidget(self.update_button)
        layout.addStretch()

    def values(self):
        return {
            "birth_year": self.birth_year_spinbox.value(),
            "end_year": self.end_year_spinbox.value(),
            "retirement_age": self.retirement_age_spinbox.value(),
            "starting_investment_value": self.starting_investment_value_spinbox.value(),
            "return_rate_before_retirement": self.return_rate_before_spinbox.value(),
            "return_rate_after_retirement": self.return_rate_after_spinbox.value(),
            "annual_income": self.annual_income_spinbox.value(),
            "tax_rate": self.tax_rate_spinbox.value(),
            "inflation_rate": self.inflation_rate_spinbox.value(),
            "spending_before_retirement": self.spending_before_spinbox.value(),
            "spending_after_retirement": self.spending_after_spinbox.value(),
            "social_security_annual_amount": self.social_security_amount_spinbox.value(),
            "social_security_start_year": self.social_security_start_year_spinbox.value(),
        }

    def set_values(self, values):
        widgets = {
            "birth_year": self.birth_year_spinbox,
            "end_year": self.end_year_spinbox,
            "retirement_age": self.retirement_age_spinbox,
            "starting_investment_value": self.starting_investment_value_spinbox,
            "return_rate_before_retirement": self.return_rate_before_spinbox,
            "return_rate_after_retirement": self.return_rate_after_spinbox,
            "annual_income": self.annual_income_spinbox,
            "tax_rate": self.tax_rate_spinbox,
            "inflation_rate": self.inflation_rate_spinbox,
            "spending_before_retirement": self.spending_before_spinbox,
            "spending_after_retirement": self.spending_after_spinbox,
            "social_security_annual_amount": self.social_security_amount_spinbox,
            "social_security_start_year": self.social_security_start_year_spinbox,
        }
        for key, widget in widgets.items():
            if key in values:
                widget.setValue(values[key])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_projection_controls.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add ui/projection_controls.py ui/tests/test_projection_controls.py
git commit -m "feat: add projection controls panel widget"
```

---

### Task 4: Wire the projection report into the Reports tab

**Files:**
- Modify: `ui/reports_tab.py`
- Test: `ui/tests/test_reports_tab.py`

**Interfaces:**
- Consumes:
  - From Task 1: `ProjectionInputs`, `compute_projection(inputs, current_year=None)`.
  - From Task 2: `load_projection_settings()`, `save_projection_settings(settings)`.
  - From Task 3: `ProjectionControlsPanel()`, `default_projection_values()`, panel `.values()`/`.set_values()`/`.updated`.
  - Existing: `data.list_accounts(conn, include_closed=False)` (returns `(account_id, name, account_type, currency, balance, is_closed)` tuples), `data.INVESTMENT_ACCOUNT_TYPE` (already imported in this file as `INVESTMENT_ACCOUNT_TYPE`), `charts.build_line_chart(title, series)` where `series` is `[(label, [(date, value), ...]), ...]`.

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_reports_tab.py` — first add `import pytest` alongside the existing imports at the top of the file, then append:

```python
def _select_projection_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(4, 0), QItemSelectionModel.ClearAndSelect
    )


def test_reports_list_shows_net_worth_projection_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(4, 0)) == "Net Worth Projection"


def test_selecting_projection_report_shows_controls_and_chart_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    assert pane.projection_controls.isVisible()
    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_selecting_other_report_after_projection_restores_range_controls(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)
    _select_net_worth_report(pane)

    assert not pane.projection_controls.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()


def test_selecting_projection_report_autofills_starting_investment_value(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.starting_investment_value_spinbox.value() == pytest.approx(426.30)


def test_selecting_projection_report_loads_persisted_settings(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "load_projection_settings", lambda: {"retirement_age": 70, "annual_income": 12345.0}
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.retirement_age_spinbox.value() == 70
    assert pane.projection_controls.annual_income_spinbox.value() == pytest.approx(12345.0)


def test_selecting_projection_report_renders_two_line_series(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    chart = pane.chart_view.chart()
    series = chart.series()
    assert [s.name() for s in series] == ["Investment Value", "Net Worth"]
    assert series[0].count() == series[1].count() > 1
    assert series[0].at(0).y() == pytest.approx(426.30)
    assert series[1].at(0).y() == pytest.approx(426.30)


def test_clicking_update_in_projection_panel_saves_settings_and_rerenders(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    saved = {}
    monkeypatch.setattr(reports_tab, "save_projection_settings", saved.update)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.retirement_age_spinbox.setValue(70)
    pane.projection_controls.update_button.click()

    assert saved["retirement_age"] == 70
    assert "starting_investment_value" not in saved
```

Note: `426.30` is the expected USD-converted sum of the `dict_conn` fixture's two investment accounts as of their latest priced trades — Brokerage A: `(8.0 + 3.0 - 1.0) shares * 22.63 (latest price) = 226.30`; Brokerage B: `(10.0 - 2.0) shares * 25.00 (latest price) = 200.00`; total `426.30`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_reports_tab.py -v -k projection`
Expected: FAIL — `AttributeError: 'ReportsPane' object has no attribute 'projection_controls'` (and similar) since the report doesn't exist yet.

- [ ] **Step 3: Write the implementation**

In `ui/reports_tab.py`:

1. Update imports — add `from datetime import date` near the top; extend the `charts` import to include `build_line_chart`; add the three new module imports:

```python
from datetime import date
```

```python
from charts import build_bar_chart, build_line_chart, build_pie_chart
```

```python
from projection import ProjectionInputs, compute_projection
from projection_controls import ProjectionControlsPanel, default_projection_values
from projection_settings import load_projection_settings, save_projection_settings
```

2. Add a new report id and list entry:

```python
NET_WORTH_PROJECTION_REPORT_ID = "net_worth_projection"
```

Add `(NET_WORTH_PROJECTION_REPORT_ID, "Net Worth Projection")` as the last tuple in the `REPORTS` list.

3. In `ReportsPane.__init__`, after the existing `self.investment_controls_row` block, construct the panel:

```python
        self.projection_controls = ProjectionControlsPanel()
        self.projection_controls.setVisible(False)
        self.projection_controls.updated.connect(self._on_projection_updated)
```

4. In `ReportsPane.__init__`, replace the `range_row` construction so it's wrapped in a widget (needed to toggle its visibility as a unit):

Replace:
```python
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("From:"))
        range_row.addWidget(self.start_date_edit)
        range_row.addWidget(QLabel("To:"))
        range_row.addWidget(self.end_date_edit)
        range_row.addWidget(self.update_range_button)
        range_row.addStretch()
```

With:
```python
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("From:"))
        range_row.addWidget(self.start_date_edit)
        range_row.addWidget(QLabel("To:"))
        range_row.addWidget(self.end_date_edit)
        range_row.addWidget(self.update_range_button)
        range_row.addStretch()
        self.range_controls_row = QWidget()
        self.range_controls_row.setLayout(range_row)
```

5. In `ReportsPane.__init__`, update `chart_layout` to include the projection panel and use `range_controls_row` instead of `range_row`:

Replace:
```python
        chart_layout.addWidget(self.investment_controls_row)
        chart_layout.addWidget(self.view_selector_row)
        chart_layout.addWidget(self.range_label)
        chart_layout.addLayout(range_row)
```

With:
```python
        chart_layout.addWidget(self.investment_controls_row)
        chart_layout.addWidget(self.view_selector_row)
        chart_layout.addWidget(self.projection_controls)
        chart_layout.addWidget(self.range_label)
        chart_layout.addWidget(self.range_controls_row)
```

6. Replace `_on_selected` entirely:

```python
    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self._active_report_id = None
            self.chart_view.setChart(QChart())
            self.spending_table_model.set_categories([])
            self.income_table_model.set_categories([])
            self.investment_table_model.set_investments([])
            self.range_label.setText("")
            self.view_selector_row.setVisible(False)
            self.investment_controls_row.setVisible(False)
            self.projection_controls.setVisible(False)
            return
        report_id = self.list_model.id_at(indexes[0].row())
        self._active_report_id = report_id
        is_category_report = report_id in self._category_reports
        is_investment_report = report_id == INVESTMENT_ANALYSIS_REPORT_ID
        is_projection_report = report_id == NET_WORTH_PROJECTION_REPORT_ID
        self.view_selector_row.setVisible(is_category_report)
        if is_category_report:
            self.view_selector.blockSignals(True)
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
            self.category_table_view.setModel(self._category_reports[report_id]["model"])
        self.chart_view.setVisible(report_id in (NET_WORTH_REPORT_ID, NET_WORTH_PROJECTION_REPORT_ID))
        self.category_table_view.setVisible(is_category_report)
        self.investment_table_view.setVisible(is_investment_report)
        self.investment_controls_row.setVisible(is_investment_report)
        self.projection_controls.setVisible(is_projection_report)
        self.range_controls_row.setVisible(not is_projection_report)
        self.range_label.setVisible(not is_projection_report)
        if report_id == NET_WORTH_REPORT_ID:
            self._load_net_worth_report()
        elif is_category_report:
            self._load_category_report(report_id)
        elif is_investment_report:
            self._load_investment_report()
        elif is_projection_report:
            self._load_projection_report()
```

7. Add three new methods (placed after `_render_investment_table`, before `_on_custom_investments_clicked`):

```python
    def _load_projection_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=False)
        except Exception as exc:
            self._report_error(f"Failed to load net worth projection report: {exc}")
            return

        starting_value = sum(
            (
                self._to_usd(currency, balance)
                for _account_id, _name, account_type, currency, balance, _is_closed in accounts
                if account_type == INVESTMENT_ACCOUNT_TYPE
            ),
            start=Decimal("0"),
        )

        values = default_projection_values()
        values.update(load_projection_settings())
        values["starting_investment_value"] = float(starting_value)
        self.projection_controls.set_values(values)
        self._render_projection_chart()

    def _on_projection_updated(self):
        values = self.projection_controls.values()
        save_projection_settings(
            {key: value for key, value in values.items() if key != "starting_investment_value"}
        )
        self._render_projection_chart()

    def _render_projection_chart(self):
        values = self.projection_controls.values()
        hundred = Decimal("100")
        inputs = ProjectionInputs(
            birth_year=values["birth_year"],
            end_year=values["end_year"],
            retirement_age=values["retirement_age"],
            starting_investment_value=Decimal(str(values["starting_investment_value"])),
            return_rate_before_retirement=Decimal(str(values["return_rate_before_retirement"])) / hundred,
            return_rate_after_retirement=Decimal(str(values["return_rate_after_retirement"])) / hundred,
            annual_income=Decimal(str(values["annual_income"])),
            tax_rate=Decimal(str(values["tax_rate"])) / hundred,
            inflation_rate=Decimal(str(values["inflation_rate"])) / hundred,
            spending_before_retirement=Decimal(str(values["spending_before_retirement"])),
            spending_after_retirement=Decimal(str(values["spending_after_retirement"])),
            social_security_annual_amount=Decimal(str(values["social_security_annual_amount"])),
            social_security_start_year=values["social_security_start_year"],
        )
        rows = compute_projection(inputs)
        series = [
            ("Investment Value", [(date(row.year, 1, 1), row.investment_value) for row in rows]),
            ("Net Worth", [(date(row.year, 1, 1), row.net_worth) for row in rows]),
        ]
        chart = build_line_chart("Net Worth Projection (USD)", series)
        self.chart_view.setChart(chart)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_reports_tab.py -v`
Expected: PASS (all tests, including the existing ones — confirms the shared `range_row`→`range_controls_row` change didn't break other reports)

- [ ] **Step 5: Manual verification**

Run: `./run-ui.sh` (requires `money.duckdb` to exist)
- Open the Reports tab, select "Net Worth Projection".
- Confirm the starting investment value matches the investment accounts' total shown on the Accounts tab.
- Adjust a few inputs (e.g. retirement age, spending) and click "Update" — confirm the chart redraws with two lines.
- Restart the app, reselect the report — confirm the edited inputs (except starting investment value, which recomputes fresh) were remembered.
- Select another report and back — confirm the range/date controls reappear for other reports and disappear for the projection report.

- [ ] **Step 6: Commit**

```bash
git add ui/reports_tab.py ui/tests/test_reports_tab.py
git commit -m "feat: wire net worth projection report into Reports tab"
```

---

## Self-Review Notes

- **Spec coverage:** two-line chart (Task 4 step 3.7 `_render_projection_chart`) — covered; auto-filled editable starting value (Task 4 `_load_projection_report`) — covered; birth-year control (Task 3) — covered; flat tax on income+SS (Task 1) — covered; inflation on income/spending (Task 1) — covered; negative net worth without flooring (Task 1) — covered; JSON persistence excluding starting value (Task 2 + Task 4) — covered; report list placement (Task 4) — covered; update-on-click (Task 3 `updated` signal + Task 4 wiring) — covered; no per-year table (no table added anywhere) — covered.
- **Placeholder scan:** none found — every step has concrete code or an exact shell command.
- **Type consistency:** `ProjectionInputs`/`YearlyProjection` field names match exactly between Task 1's definition and Task 4's construction/consumption; `ProjectionControlsPanel` attribute names and `.values()`/`.set_values()` keys match exactly between Task 3's definition and Task 4's usage; `load_projection_settings`/`save_projection_settings` signatures match between Task 2 and Task 4's monkeypatching and real usage.
