# College Tuition Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "College Tuition Projection" report to the Reports tab: a control panel (college savings account multi-select, expected investment return, a joint quarterly contribution, and per-person tuition/housing/timeline inputs for two people) driving a single-line chart of a shared college fund balance, projected quarter-by-quarter into the future.

**Architecture:** A pure calculation module (`college_tuition.py`) computes the quarter-by-quarter projection from a plain dataclass of inputs — no Qt or DB dependency, fully unit-testable, mirroring `projection.py`'s shape but stepping quarterly instead of yearly. A small JSON-persistence module (`college_tuition_settings.py`) mirrors the existing `projection_settings.py` sibling-file pattern. A new Qt widget (`college_tuition_controls.py`) owns the input spinboxes plus an id-keyed multi-select account picker (`AccountFilterDialog`, added to `category_filter_dialog.py`). `reports_tab.py` wires these together as a new entry in the existing report list, reusing the shared `chart_view` and `charts.build_line_chart`. A first task extracts the three spinbox factories duplicated by `projection_controls.py` into a shared `form_controls.py` module so the new panel doesn't re-duplicate them.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets + QtCharts), DuckDB (read-only), pytest, `decimal.Decimal` for all money/rate arithmetic (matching the rest of `ui/`).

**Spec:** `docs/superpowers/specs/2026-08-23-college-tuition-projection-design.md`

## Global Constraints

- All money and rate arithmetic in the calculation engine uses `Decimal`, never `float` — Qt spinbox `float` values are converted via `Decimal(str(value))` at the UI/engine boundary, matching the existing pattern in `reports_tab.py`'s `_render_projection_chart`.
- Single shared fund: both people's tuition + housing costs are withdrawn from, and the one joint contribution is added to, the same combined `fund_value` — there are no per-person sub-balances.
- `fund_value` is allowed to go negative; it is never floored at zero.
- The projection steps **quarterly** (fields: year + quarter 1-4), not yearly — the one structural difference from Net Worth Projection.
- A person is active (their tuition + housing apply) in every quarter of every year in `[start_year, end_year]` inclusive; `start_year > end_year` means never active (no validation, matching the app's existing "degenerate but well-defined" convention).
- The joint contribution applies every quarter through Q4 of `contribution_end_year`; it is not tied to either person's start/end year.
- The account picker offers Investment-type accounts only (`data.INVESTMENT_ACCOUNT_TYPE`); selected account IDs persist across restarts, the computed `starting_fund_value` never does (always recomputed live from current balances).
- Projection inputs persist to a git-ignored sibling JSON file (`college_tuition_settings.json`), following the existing `projection_settings.py` pattern, including the same defensive `try/except (json.JSONDecodeError, OSError)` on load.
- Recomputation of the chart happens only when the panel's "Update" button is clicked, not on every keystroke — matching the existing `update_range_button` convention. Changing the account selection via "Select Accounts..." does immediately update the read-only starting fund value display (not persisted or charted until "Update" is clicked), the same way the account list itself is only refreshed on report selection.
- No per-quarter data table in this iteration — chart only.

---

### Task 1: Extract shared spinbox factories into `form_controls.py`

**Files:**
- Create: `ui/form_controls.py`
- Modify: `ui/projection_controls.py:1-70` (remove local `_year_spinbox`/`_percent_spinbox`/`_dollar_spinbox`, import and use the shared versions)
- No new test file — this is a pure refactor; the existing `ui/tests/test_projection_controls.py` suite is the regression check.

**Interfaces:**
- Produces: `year_spinbox(value) -> QSpinBox`, `percent_spinbox(value) -> QDoubleSpinBox`, `dollar_spinbox(value) -> QDoubleSpinBox` — same behavior as the three private helpers currently in `projection_controls.py` (year range 1900-2200; percent range -20.0-100.0, 2 decimals, `%` suffix; dollar range 0.0-100,000,000.0, 2 decimals, step 1000, `$` prefix).

- [ ] **Step 1: Run the existing projection controls tests to record the baseline**

Run: `pytest ui/tests/test_projection_controls.py -v`
Expected: PASS (all existing tests green before the refactor)

- [ ] **Step 2: Create `ui/form_controls.py`**

```python
"""Shared spinbox factories for report control panels (Net Worth
Projection, College Tuition Projection): year, percentage, and dollar
inputs with consistent ranges and formatting.
"""

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


def year_spinbox(value):
    spinbox = QSpinBox()
    spinbox.setRange(1900, 2200)
    spinbox.setValue(value)
    return spinbox


def percent_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(-20.0, 100.0)
    spinbox.setDecimals(2)
    spinbox.setSuffix("%")
    spinbox.setValue(value)
    return spinbox


def dollar_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(0.0, 100_000_000.0)
    spinbox.setDecimals(2)
    spinbox.setSingleStep(1000.0)
    spinbox.setPrefix("$")
    spinbox.setValue(value)
    return spinbox
```

- [ ] **Step 3: Update `ui/projection_controls.py` to use the shared factories**

Remove these three function definitions from `ui/projection_controls.py` (currently lines 47-70):

```python
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
```

Add this import near the top (alongside the existing `PySide6.QtWidgets` import block):

```python
from form_controls import dollar_spinbox, percent_spinbox, year_spinbox
```

Then replace every call site in the file: `_year_spinbox(` → `year_spinbox(`, `_percent_spinbox(` → `percent_spinbox(`, `_dollar_spinbox(` → `dollar_spinbox(`. There are 4 call sites for `_year_spinbox` (birth_year, end_year, social_security_start_year, house_sale_year spinboxes plus the two inline `QSpinBox` age spinboxes are untouched — only the three factory-built ones), 4 for `_percent_spinbox`, and 5 for `_dollar_spinbox` — use a project-wide search to confirm every call site in the file is updated (`grep -n "_year_spinbox(\|_percent_spinbox(\|_dollar_spinbox(" ui/projection_controls.py` should return zero matches after this step).

- [ ] **Step 4: Run the projection controls tests again to confirm no regression**

Run: `pytest ui/tests/test_projection_controls.py -v`
Expected: PASS (identical results to Step 1)

- [ ] **Step 5: Commit**

```bash
git add ui/form_controls.py ui/projection_controls.py
git commit -m "refactor: extract shared spinbox factories into form_controls.py"
```

---

### Task 2: College tuition calculation engine

**Files:**
- Create: `ui/college_tuition.py`
- Test: `ui/tests/test_college_tuition.py`

**Interfaces:**
- Produces:
  - `PersonCollegeCosts` — a `dataclasses.dataclass` with fields: `start_year: int`, `end_year: int`, `tuition_per_quarter: Decimal`, `housing_per_quarter: Decimal`.
  - `CollegeTuitionInputs` — a `dataclasses.dataclass` with fields: `starting_fund_value: Decimal`, `annual_return_rate: Decimal`, `contribution_per_quarter: Decimal`, `contribution_end_year: int`, `person1: PersonCollegeCosts`, `person2: PersonCollegeCosts`.
  - `QuarterlyProjection` — a `typing.NamedTuple` with fields: `year: int`, `quarter: int`, `person1_cost: Decimal`, `person2_cost: Decimal`, `contribution: Decimal`, `net_cash_flow: Decimal`, `fund_value: Decimal`.
  - `compute_college_tuition_projection(inputs: CollegeTuitionInputs, current_year: int | None = None, current_quarter: int | None = None) -> list[QuarterlyProjection]` — one row per calendar quarter from the current quarter (defaults derived from `date.today()`) through Q4 of `max(person1.end_year, person2.end_year, contribution_end_year)`.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_college_tuition.py`:

```python
from decimal import Decimal

from college_tuition import CollegeTuitionInputs, PersonCollegeCosts, compute_college_tuition_projection


def _inactive_person():
    return PersonCollegeCosts(
        start_year=9999,
        end_year=0,
        tuition_per_quarter=Decimal("0"),
        housing_per_quarter=Decimal("0"),
    )


def _inputs(**overrides):
    defaults = dict(
        starting_fund_value=Decimal("0"),
        annual_return_rate=Decimal("0"),
        contribution_per_quarter=Decimal("0"),
        contribution_end_year=0,
        person1=_inactive_person(),
        person2=_inactive_person(),
    )
    defaults.update(overrides)
    return CollegeTuitionInputs(**defaults)


def test_quarter_zero_is_a_snapshot_with_no_growth_or_cash_flow():
    inputs = _inputs(starting_fund_value=Decimal("5000"))

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=2)

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    assert row.quarter == 2
    assert row.person1_cost == Decimal("0")
    assert row.person2_cost == Decimal("0")
    assert row.contribution == Decimal("0")
    assert row.net_cash_flow == Decimal("0")
    assert row.fund_value == Decimal("5000")


def test_person_active_only_within_start_and_end_year_inclusive():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025,
            end_year=2026,
            tuition_per_quarter=Decimal("1000"),
            housing_per_quarter=Decimal("500"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2024, 4)].person1_cost == Decimal("0")
    assert by_yq[(2025, 1)].person1_cost == Decimal("1500")
    assert by_yq[(2025, 4)].person1_cost == Decimal("1500")
    assert by_yq[(2026, 1)].person1_cost == Decimal("1500")
    assert by_yq[(2026, 4)].person1_cost == Decimal("1500")
    assert (2027, 1) not in by_yq


def test_both_people_active_in_same_quarter_costs_are_summed():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2026,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("500"),
        ),
        person2=PersonCollegeCosts(
            start_year=2026, end_year=2027,
            tuition_per_quarter=Decimal("800"), housing_per_quarter=Decimal("400"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    overlap = by_yq[(2026, 2)]
    assert overlap.person1_cost == Decimal("1500")
    assert overlap.person2_cost == Decimal("1200")
    assert overlap.net_cash_flow == Decimal("-2700")


def test_contribution_stops_after_contribution_end_year():
    inputs = _inputs(
        contribution_per_quarter=Decimal("2000"),
        contribution_end_year=2025,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2025, 1)].contribution == Decimal("2000")
    assert by_yq[(2025, 4)].contribution == Decimal("2000")
    assert (2026, 1) not in by_yq


def test_quarterly_compounding_applies_quarter_root_of_annual_rate():
    inputs = _inputs(
        starting_fund_value=Decimal("1000"),
        annual_return_rate=Decimal("0.21550625"),  # exactly 5% compounded per quarter
        contribution_end_year=2025,
        contribution_per_quarter=Decimal("0"),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    values = [row.fund_value for row in rows]

    assert len(values) == 5
    assert values[0] == Decimal("1000")
    assert abs(values[1] - Decimal("1050.00000")) < Decimal("0.01")
    assert abs(values[2] - Decimal("1102.50000")) < Decimal("0.01")
    assert abs(values[3] - Decimal("1157.62500")) < Decimal("0.01")
    assert abs(values[4] - Decimal("1215.50625")) < Decimal("0.01")


def test_fund_goes_negative_without_flooring_when_costs_exceed_resources():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2025,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("0"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2025, 1)].fund_value == Decimal("-1000")
    assert by_yq[(2025, 4)].fund_value == Decimal("-4000")


def test_end_year_is_the_max_of_both_people_and_contribution_end_year():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2025,
            tuition_per_quarter=Decimal("0"), housing_per_quarter=Decimal("0"),
        ),
        person2=PersonCollegeCosts(
            start_year=2030, end_year=2031,
            tuition_per_quarter=Decimal("0"), housing_per_quarter=Decimal("0"),
        ),
        contribution_end_year=2027,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=1)

    assert rows[-1].year == 2031
    assert rows[-1].quarter == 4


def test_person_never_active_when_start_year_after_end_year():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2027, end_year=2025,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("1000"),
        ),
        contribution_end_year=2026,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=1)

    assert all(row.person1_cost == Decimal("0") for row in rows)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest ui/tests/test_college_tuition.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'college_tuition'`

- [ ] **Step 3: Write the implementation**

Create `ui/college_tuition.py`:

```python
"""Forward-looking college fund projection, driven by user-entered
assumptions rather than real transaction data (contrast with
models.compute_net_worth_series, which is historical). Steps quarter by
quarter, unlike projection.py's yearly Net Worth Projection.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional


@dataclass
class PersonCollegeCosts:
    start_year: int
    end_year: int
    tuition_per_quarter: Decimal
    housing_per_quarter: Decimal


@dataclass
class CollegeTuitionInputs:
    starting_fund_value: Decimal
    annual_return_rate: Decimal
    contribution_per_quarter: Decimal
    contribution_end_year: int
    person1: PersonCollegeCosts
    person2: PersonCollegeCosts


class QuarterlyProjection(NamedTuple):
    year: int
    quarter: int
    person1_cost: Decimal
    person2_cost: Decimal
    contribution: Decimal
    net_cash_flow: Decimal
    fund_value: Decimal


def _person_cost(person: PersonCollegeCosts, year: int) -> Decimal:
    if person.start_year <= year <= person.end_year:
        return person.tuition_per_quarter + person.housing_per_quarter
    return Decimal("0")


def _next_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year + 1, 1) if quarter == 4 else (year, quarter + 1)


def compute_college_tuition_projection(
    inputs: CollegeTuitionInputs,
    current_year: Optional[int] = None,
    current_quarter: Optional[int] = None,
) -> list[QuarterlyProjection]:
    """Quarter-by-quarter projection from the current quarter through Q4 of
    the latest of person1.end_year, person2.end_year, and
    contribution_end_year.

    Quarter 0 (the current quarter) is a snapshot at starting_fund_value
    with no cash flow or growth applied yet. Each later quarter adds that
    quarter's joint contribution (0 once past contribution_end_year) and
    subtracts each person's tuition + housing cost (0 unless
    person.start_year <= year <= person.end_year), then compounds the
    resulting fund_value at the quarterly-equivalent of annual_return_rate.
    fund_value is never floored at zero -- a shortfall keeps compounding as
    a negative balance, same convention as projection.py's net_worth.
    """
    today = date.today()
    if current_year is None:
        current_year = today.year
    if current_quarter is None:
        current_quarter = (today.month - 1) // 3 + 1

    end_year = max(inputs.person1.end_year, inputs.person2.end_year, inputs.contribution_end_year)
    quarterly_rate = (Decimal(1) + inputs.annual_return_rate) ** Decimal("0.25") - Decimal(1)
    zero = Decimal("0")

    rows = [
        QuarterlyProjection(
            year=current_year,
            quarter=current_quarter,
            person1_cost=zero,
            person2_cost=zero,
            contribution=zero,
            net_cash_flow=zero,
            fund_value=inputs.starting_fund_value,
        )
    ]

    year, quarter = current_year, current_quarter
    while (year, quarter) < (end_year, 4):
        year, quarter = _next_quarter(year, quarter)
        prior = rows[-1]

        person1_cost = _person_cost(inputs.person1, year)
        person2_cost = _person_cost(inputs.person2, year)
        contribution = inputs.contribution_per_quarter if year <= inputs.contribution_end_year else zero
        net_cash_flow = contribution - person1_cost - person2_cost
        fund_value = (prior.fund_value + net_cash_flow) * (Decimal(1) + quarterly_rate)

        rows.append(
            QuarterlyProjection(
                year=year,
                quarter=quarter,
                person1_cost=person1_cost,
                person2_cost=person2_cost,
                contribution=contribution,
                net_cash_flow=net_cash_flow,
                fund_value=fund_value,
            )
        )

    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest ui/tests/test_college_tuition.py -v`
Expected: PASS (all 8 tests green)

- [ ] **Step 5: Commit**

```bash
git add ui/college_tuition.py ui/tests/test_college_tuition.py
git commit -m "feat: add college tuition projection calculation engine"
```

---

### Task 3: College tuition settings persistence

**Files:**
- Create: `ui/college_tuition_settings.py`
- Test: `ui/tests/test_college_tuition_settings.py`
- Modify: `.gitignore` (add `college_tuition_settings.json`)

**Interfaces:**
- Produces: `DEFAULT_SETTINGS_PATH`, `load_college_tuition_settings(path=DEFAULT_SETTINGS_PATH) -> dict`, `save_college_tuition_settings(settings, path=DEFAULT_SETTINGS_PATH) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_college_tuition_settings.py`:

```python
import json

from college_tuition_settings import load_college_tuition_settings, save_college_tuition_settings


def test_load_missing_file_returns_empty(tmp_path):
    assert load_college_tuition_settings(tmp_path / "missing.json") == {}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    settings = {"contribution_end_year": 2036, "annual_return_rate": 6.0}

    save_college_tuition_settings(settings, path=path)

    assert load_college_tuition_settings(path) == settings


def test_saved_file_is_readable_json(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    save_college_tuition_settings({"contribution_end_year": 2036}, path=path)

    raw = json.loads(path.read_text())
    assert raw == {"contribution_end_year": 2036}


def test_load_malformed_file_returns_empty(tmp_path):
    path = tmp_path / "college_tuition_settings.json"
    path.write_text("{not valid json")

    assert load_college_tuition_settings(path) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest ui/tests/test_college_tuition_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'college_tuition_settings'`

- [ ] **Step 3: Write the implementation**

Create `ui/college_tuition_settings.py`:

```python
"""Persisted assumptions for the College Tuition Projection report.

money.duckdb is opened read-only; these are the user's projection inputs
(expected return, contribution, per-person tuition/housing/timeline, and
which accounts feed the fund), not financial records, so they're kept in
a sibling JSON file instead -- same pattern as projection_settings.py.
starting_fund_value is deliberately never stored here: it's always
recomputed live from currently selected accounts' balances.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "college_tuition_settings.json"


def load_college_tuition_settings(path=DEFAULT_SETTINGS_PATH):
    """Returns a flat dict of saved college tuition input fields, or {} if unset."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_college_tuition_settings(settings, path=DEFAULT_SETTINGS_PATH):
    """settings: flat dict of college tuition input fields (JSON-serializable)."""
    with open(path, "w") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
```

Add `college_tuition_settings.json` to `.gitignore`, alongside the existing `projection_settings.json` line (line 6):

```
projection_settings.json
college_tuition_settings.json
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest ui/tests/test_college_tuition_settings.py -v`
Expected: PASS (all 4 tests green)

- [ ] **Step 5: Commit**

```bash
git add ui/college_tuition_settings.py ui/tests/test_college_tuition_settings.py .gitignore
git commit -m "feat: add college tuition projection settings persistence"
```

---

### Task 4: `AccountFilterDialog` for multi-selecting accounts by id

**Files:**
- Modify: `ui/category_filter_dialog.py` (add `AccountFilterDialog`)
- Test: `ui/tests/test_category_filter_dialog.py` (append tests)

**Interfaces:**
- Produces: `AccountFilterDialog(QDialog)` — constructor `(accounts, selected_ids, parent=None)` where `accounts` is an iterable of `(account_id, name)` pairs and `selected_ids` is a `set` of currently-selected `account_id`; method `selected_account_ids() -> set`. Same visual shape as `CategoryFilterDialog` (`list_widget`, `select_all_button`, `select_none_button`, OK/Cancel `QDialogButtonBox`), but selection is keyed by `account_id` (via `QListWidgetItem.setData(Qt.UserRole, account_id)`), not by display name — two accounts can share a name without selection ambiguity.

- [ ] **Step 1: Write the failing tests**

Append to `ui/tests/test_category_filter_dialog.py`:

```python
from category_filter_dialog import AccountFilterDialog


def test_account_dialog_initializes_checkstate_from_selected_ids(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1})

    assert dialog.selected_account_ids() == {1}


def test_account_dialog_select_all_checks_every_account(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], set())

    dialog.select_all_button.click()

    assert dialog.selected_account_ids() == {1, 2}


def test_account_dialog_select_none_unchecks_every_account(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1, 2})

    dialog.select_none_button.click()

    assert dialog.selected_account_ids() == set()


def test_account_dialog_unchecking_one_account_removes_it_from_selection(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage A"), (2, "Brokerage B")], {1, 2})

    dialog.list_widget.item(1).setCheckState(Qt.Unchecked)

    assert dialog.selected_account_ids() == {1}


def test_account_dialog_selects_by_id_not_name_when_names_collide(qapp):
    dialog = AccountFilterDialog([(1, "Brokerage"), (2, "Brokerage")], {2})

    assert dialog.selected_account_ids() == {2}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest ui/tests/test_category_filter_dialog.py -v -k account_dialog`
Expected: FAIL with `ImportError: cannot import name 'AccountFilterDialog'`

- [ ] **Step 3: Write the implementation**

Append to `ui/category_filter_dialog.py`:

```python
class AccountFilterDialog(QDialog):
    def __init__(self, accounts, selected_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Accounts")

        self.list_widget = QListWidget()
        for account_id, name in accounts:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, account_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if account_id in selected_ids else Qt.Unchecked)
            self.list_widget.addItem(item)

        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(Qt.Checked))
        self.select_none_button = QPushButton("Select None")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(Qt.Unchecked))

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.select_all_button)
        buttons_row.addWidget(self.select_none_button)
        buttons_row.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons_row)
        layout.addWidget(self.list_widget)
        layout.addWidget(button_box)

    def _set_all_checked(self, state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)

    def selected_account_ids(self):
        return {
            self.list_widget.item(i).data(Qt.UserRole)
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        }
```

This reuses the module's existing imports (`Qt`, `QDialog`, `QDialogButtonBox`, `QHBoxLayout`, `QListWidget`, `QListWidgetItem`, `QPushButton`, `QVBoxLayout`) — no new imports needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest ui/tests/test_category_filter_dialog.py -v`
Expected: PASS (all tests, existing + new, green)

- [ ] **Step 5: Commit**

```bash
git add ui/category_filter_dialog.py ui/tests/test_category_filter_dialog.py
git commit -m "feat: add id-keyed AccountFilterDialog for multi-selecting accounts"
```

---

### Task 5: College tuition controls panel

**Files:**
- Create: `ui/college_tuition_controls.py`
- Test: `ui/tests/test_college_tuition_controls.py`

**Interfaces:**
- Consumes: `year_spinbox`, `percent_spinbox`, `dollar_spinbox` from `ui/form_controls.py` (Task 1); `AccountFilterDialog` from `ui/category_filter_dialog.py` (Task 4).
- Produces:
  - `default_college_tuition_values(today=None) -> dict` — built-in defaults for a first-time load.
  - `CollegeTuitionControlsPanel(QWidget)` — constructor `(parent=None, today=None)`; `updated` Signal; methods `set_accounts(accounts, balances)`, `values() -> dict`, `set_values(values)`. Widget attributes later tasks rely on: `starting_fund_value_spinbox`, `select_accounts_button`, `annual_return_rate_spinbox`, `contribution_per_quarter_spinbox`, `contribution_end_year_spinbox`, `person1_start_year_spinbox`, `person1_end_year_spinbox`, `person1_tuition_per_quarter_spinbox`, `person1_housing_per_quarter_spinbox`, `person2_start_year_spinbox`, `person2_end_year_spinbox`, `person2_tuition_per_quarter_spinbox`, `person2_housing_per_quarter_spinbox`, `update_button`.
  - `values()` dict keys: `starting_fund_value`, `selected_account_ids` (sorted list), `annual_return_rate`, `contribution_per_quarter`, `contribution_end_year`, `person1_start_year`, `person1_end_year`, `person1_tuition_per_quarter`, `person1_housing_per_quarter`, `person2_start_year`, `person2_end_year`, `person2_tuition_per_quarter`, `person2_housing_per_quarter`.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_college_tuition_controls.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog

from college_tuition_controls import CollegeTuitionControlsPanel, default_college_tuition_values


def test_default_college_tuition_values_are_relative_to_today():
    values = default_college_tuition_values(today=date(2024, 6, 15))
    assert values == {
        "annual_return_rate": 6.0,
        "contribution_per_quarter": 0.0,
        "contribution_end_year": 2036,
        "person1_start_year": 2029,
        "person1_end_year": 2033,
        "person1_tuition_per_quarter": 10000.0,
        "person1_housing_per_quarter": 4000.0,
        "person2_start_year": 2032,
        "person2_end_year": 2036,
        "person2_tuition_per_quarter": 10000.0,
        "person2_housing_per_quarter": 4000.0,
    }


def test_panel_initializes_widgets_from_defaults(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    assert panel.annual_return_rate_spinbox.value() == pytest.approx(6.0)
    assert panel.contribution_per_quarter_spinbox.value() == pytest.approx(0.0)
    assert panel.contribution_end_year_spinbox.value() == 2036
    assert panel.person1_start_year_spinbox.value() == 2029
    assert panel.person1_end_year_spinbox.value() == 2033
    assert panel.person1_tuition_per_quarter_spinbox.value() == pytest.approx(10000.0)
    assert panel.person1_housing_per_quarter_spinbox.value() == pytest.approx(4000.0)
    assert panel.person2_start_year_spinbox.value() == 2032
    assert panel.person2_end_year_spinbox.value() == 2036
    assert panel.person2_tuition_per_quarter_spinbox.value() == pytest.approx(10000.0)
    assert panel.person2_housing_per_quarter_spinbox.value() == pytest.approx(4000.0)


def test_starting_fund_value_spinbox_is_not_editable(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    assert not panel.starting_fund_value_spinbox.isEnabled()


def test_set_accounts_defaults_to_all_selected_and_sums_balances(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2500.50")},
    )

    assert panel.values()["selected_account_ids"] == [1, 2]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(3500.50)


def test_set_accounts_keeps_only_intersection_of_prior_selection(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts([(1, "529 Plan"), (2, "Brokerage")], {1: Decimal("1000.00"), 2: Decimal("2000.00")})
    panel.set_values({"selected_account_ids": [2]})

    panel.set_accounts([(2, "Brokerage")], {2: Decimal("2000.00")})

    assert panel.values()["selected_account_ids"] == [2]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(2000.00)


def test_set_values_restores_selected_account_ids_and_recomputes_total(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    panel.set_values({"selected_account_ids": [1]})

    assert panel.values()["selected_account_ids"] == [1]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(1000.00)


def test_values_and_set_values_round_trip(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_values(
        {
            "annual_return_rate": 5.5,
            "contribution_per_quarter": 1500.0,
            "contribution_end_year": 2040,
            "person1_start_year": 2030,
            "person1_end_year": 2034,
            "person1_tuition_per_quarter": 12000.0,
            "person1_housing_per_quarter": 5000.0,
            "person2_start_year": 2033,
            "person2_end_year": 2037,
            "person2_tuition_per_quarter": 13000.0,
            "person2_housing_per_quarter": 5500.0,
        }
    )
    values = panel.values()

    assert values["annual_return_rate"] == pytest.approx(5.5)
    assert values["contribution_per_quarter"] == pytest.approx(1500.0)
    assert values["contribution_end_year"] == 2040
    assert values["person1_start_year"] == 2030
    assert values["person1_end_year"] == 2034
    assert values["person1_tuition_per_quarter"] == pytest.approx(12000.0)
    assert values["person1_housing_per_quarter"] == pytest.approx(5000.0)
    assert values["person2_start_year"] == 2033
    assert values["person2_end_year"] == 2037
    assert values["person2_tuition_per_quarter"] == pytest.approx(13000.0)
    assert values["person2_housing_per_quarter"] == pytest.approx(5500.0)


def test_set_values_updates_only_the_given_keys(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_values({"contribution_end_year": 2050})

    assert panel.contribution_end_year_spinbox.value() == 2050
    assert panel.person1_start_year_spinbox.value() == 2029


def test_select_accounts_button_opens_dialog_and_applies_selection(qapp, monkeypatch):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    class _FakeDialog:
        def __init__(self, accounts, selected_ids, parent=None):
            self.accounts = accounts
            self.selected_ids = selected_ids

        def exec(self):
            return QDialog.Accepted

        def selected_account_ids(self):
            return {1}

    import college_tuition_controls

    monkeypatch.setattr(college_tuition_controls, "AccountFilterDialog", _FakeDialog)
    panel.select_accounts_button.click()

    assert panel.values()["selected_account_ids"] == [1]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(1000.00)


def test_canceling_select_accounts_dialog_leaves_selection_unchanged(qapp, monkeypatch):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    class _FakeDialog:
        def __init__(self, accounts, selected_ids, parent=None):
            pass

        def exec(self):
            return QDialog.Rejected

        def selected_account_ids(self):
            return {1}

    import college_tuition_controls

    monkeypatch.setattr(college_tuition_controls, "AccountFilterDialog", _FakeDialog)
    panel.select_accounts_button.click()

    assert panel.values()["selected_account_ids"] == [1, 2]


def test_clicking_update_button_emits_updated_signal(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    calls = []
    panel.updated.connect(lambda: calls.append(True))

    panel.update_button.click()

    assert calls == [True]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest ui/tests/test_college_tuition_controls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'college_tuition_controls'`

- [ ] **Step 3: Write the implementation**

Create `ui/college_tuition_controls.py`:

```python
"""Controls panel for the College Tuition Projection report: college
savings account selection, expected investment return, a joint quarterly
contribution, and per-person (Person 1 / Person 2) tuition/housing/
timeline inputs, laid out in labeled sections with an Update button.
"""

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from category_filter_dialog import AccountFilterDialog
from form_controls import dollar_spinbox, percent_spinbox, year_spinbox


def default_college_tuition_values(today=None):
    """Built-in defaults for a first-time (no saved settings) load."""
    today = today or date.today()
    return {
        "annual_return_rate": 6.0,
        "contribution_per_quarter": 0.0,
        "contribution_end_year": today.year + 12,
        "person1_start_year": today.year + 5,
        "person1_end_year": today.year + 9,
        "person1_tuition_per_quarter": 10000.0,
        "person1_housing_per_quarter": 4000.0,
        "person2_start_year": today.year + 8,
        "person2_end_year": today.year + 12,
        "person2_tuition_per_quarter": 10000.0,
        "person2_housing_per_quarter": 4000.0,
    }


class CollegeTuitionControlsPanel(QWidget):
    updated = Signal()

    def __init__(self, parent=None, today=None):
        super().__init__(parent)
        defaults = default_college_tuition_values(today)

        self._accounts = []
        self._balances = {}
        self._selected_account_ids = None

        self.starting_fund_value_spinbox = dollar_spinbox(0.0)
        self.starting_fund_value_spinbox.setEnabled(False)
        self.starting_fund_value_spinbox.setToolTip(
            "Sum of the selected College Savings Accounts; not editable."
        )
        self.select_accounts_button = QPushButton("Select Accounts...")
        self.select_accounts_button.clicked.connect(self._on_select_accounts_clicked)

        self.annual_return_rate_spinbox = percent_spinbox(defaults["annual_return_rate"])

        self.contribution_per_quarter_spinbox = dollar_spinbox(defaults["contribution_per_quarter"])
        self.contribution_end_year_spinbox = year_spinbox(defaults["contribution_end_year"])

        self.person1_start_year_spinbox = year_spinbox(defaults["person1_start_year"])
        self.person1_end_year_spinbox = year_spinbox(defaults["person1_end_year"])
        self.person1_tuition_per_quarter_spinbox = dollar_spinbox(defaults["person1_tuition_per_quarter"])
        self.person1_housing_per_quarter_spinbox = dollar_spinbox(defaults["person1_housing_per_quarter"])

        self.person2_start_year_spinbox = year_spinbox(defaults["person2_start_year"])
        self.person2_end_year_spinbox = year_spinbox(defaults["person2_end_year"])
        self.person2_tuition_per_quarter_spinbox = dollar_spinbox(defaults["person2_tuition_per_quarter"])
        self.person2_housing_per_quarter_spinbox = dollar_spinbox(defaults["person2_housing_per_quarter"])

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.updated.emit)

        layout = QVBoxLayout(self)

        accounts_form = QFormLayout()
        accounts_form.addRow("College savings total:", self.starting_fund_value_spinbox)
        accounts_row = QHBoxLayout()
        accounts_row.addWidget(self.select_accounts_button)
        accounts_row.addStretch()

        returns_form = QFormLayout()
        returns_form.addRow("Expected yearly return:", self.annual_return_rate_spinbox)

        contribution_form = QFormLayout()
        contribution_form.addRow("Joint contribution per quarter:", self.contribution_per_quarter_spinbox)
        contribution_form.addRow("Contribution end year:", self.contribution_end_year_spinbox)

        person1_form = QFormLayout()
        person1_form.addRow("Start year:", self.person1_start_year_spinbox)
        person1_form.addRow("End year:", self.person1_end_year_spinbox)
        person1_form.addRow("Tuition per quarter:", self.person1_tuition_per_quarter_spinbox)
        person1_form.addRow("Housing per quarter:", self.person1_housing_per_quarter_spinbox)

        person2_form = QFormLayout()
        person2_form.addRow("Start year:", self.person2_start_year_spinbox)
        person2_form.addRow("End year:", self.person2_end_year_spinbox)
        person2_form.addRow("Tuition per quarter:", self.person2_tuition_per_quarter_spinbox)
        person2_form.addRow("Housing per quarter:", self.person2_housing_per_quarter_spinbox)

        layout.addWidget(QLabel("<b>College Savings Accounts</b>"))
        layout.addLayout(accounts_form)
        layout.addLayout(accounts_row)
        layout.addWidget(QLabel("<b>Investment Return</b>"))
        layout.addLayout(returns_form)
        layout.addWidget(QLabel("<b>Contribution</b>"))
        layout.addLayout(contribution_form)
        layout.addWidget(QLabel("<b>Person 1</b>"))
        layout.addLayout(person1_form)
        layout.addWidget(QLabel("<b>Person 2</b>"))
        layout.addLayout(person2_form)
        layout.addWidget(self.update_button)
        layout.addStretch()

    def set_accounts(self, accounts, balances):
        """accounts: iterable of (account_id, name) Investment-type pairs.
        balances: dict of account_id -> Decimal USD value. Recomputes the
        read-only starting fund value display; selects every account the
        first time this is called (selection unset), and thereafter keeps
        only the intersection of the current selection with the accounts
        given (an account removed/closed since drops out silently).
        """
        self._accounts = list(accounts)
        self._balances = dict(balances)
        known_ids = {account_id for account_id, _name in self._accounts}
        if self._selected_account_ids is None:
            self._selected_account_ids = set(known_ids)
        else:
            self._selected_account_ids &= known_ids
        self._update_starting_fund_value()

    def _update_starting_fund_value(self):
        total = sum(
            (self._balances.get(account_id, Decimal("0")) for account_id in self._selected_account_ids),
            start=Decimal("0"),
        )
        self.starting_fund_value_spinbox.setValue(float(total))

    def _on_select_accounts_clicked(self):
        dialog = AccountFilterDialog(self._accounts, self._selected_account_ids or set(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._selected_account_ids = dialog.selected_account_ids()
        self._update_starting_fund_value()

    def values(self):
        return {
            "starting_fund_value": self.starting_fund_value_spinbox.value(),
            "selected_account_ids": sorted(self._selected_account_ids or []),
            "annual_return_rate": self.annual_return_rate_spinbox.value(),
            "contribution_per_quarter": self.contribution_per_quarter_spinbox.value(),
            "contribution_end_year": self.contribution_end_year_spinbox.value(),
            "person1_start_year": self.person1_start_year_spinbox.value(),
            "person1_end_year": self.person1_end_year_spinbox.value(),
            "person1_tuition_per_quarter": self.person1_tuition_per_quarter_spinbox.value(),
            "person1_housing_per_quarter": self.person1_housing_per_quarter_spinbox.value(),
            "person2_start_year": self.person2_start_year_spinbox.value(),
            "person2_end_year": self.person2_end_year_spinbox.value(),
            "person2_tuition_per_quarter": self.person2_tuition_per_quarter_spinbox.value(),
            "person2_housing_per_quarter": self.person2_housing_per_quarter_spinbox.value(),
        }

    def set_values(self, values):
        widgets = {
            "annual_return_rate": self.annual_return_rate_spinbox,
            "contribution_per_quarter": self.contribution_per_quarter_spinbox,
            "contribution_end_year": self.contribution_end_year_spinbox,
            "person1_start_year": self.person1_start_year_spinbox,
            "person1_end_year": self.person1_end_year_spinbox,
            "person1_tuition_per_quarter": self.person1_tuition_per_quarter_spinbox,
            "person1_housing_per_quarter": self.person1_housing_per_quarter_spinbox,
            "person2_start_year": self.person2_start_year_spinbox,
            "person2_end_year": self.person2_end_year_spinbox,
            "person2_tuition_per_quarter": self.person2_tuition_per_quarter_spinbox,
            "person2_housing_per_quarter": self.person2_housing_per_quarter_spinbox,
        }
        for key, widget in widgets.items():
            if key not in values:
                continue
            try:
                widget.setValue(values[key])
            except TypeError:
                continue
        if "selected_account_ids" in values:
            known_ids = {account_id for account_id, _name in self._accounts}
            self._selected_account_ids = set(values["selected_account_ids"]) & known_ids
            self._update_starting_fund_value()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest ui/tests/test_college_tuition_controls.py -v`
Expected: PASS (all tests green)

- [ ] **Step 5: Commit**

```bash
git add ui/college_tuition_controls.py ui/tests/test_college_tuition_controls.py
git commit -m "feat: add college tuition projection controls panel widget"
```

---

### Task 6: Wire College Tuition Projection into the Reports tab

**Files:**
- Modify: `ui/reports_tab.py` (imports, `REPORTS`, `ReportsPane.__init__`, `_on_selected`, three new methods)
- Test: `ui/tests/test_reports_tab.py` (append tests)

**Interfaces:**
- Consumes: `PersonCollegeCosts`, `CollegeTuitionInputs`, `compute_college_tuition_projection` from `ui/college_tuition.py` (Task 2); `load_college_tuition_settings`, `save_college_tuition_settings` from `ui/college_tuition_settings.py` (Task 3); `CollegeTuitionControlsPanel`, `default_college_tuition_values` from `ui/college_tuition_controls.py` (Task 5); existing `data.list_accounts`, `data.INVESTMENT_ACCOUNT_TYPE`, `charts.build_line_chart`.
- Produces: `COLLEGE_TUITION_PROJECTION_REPORT_ID` module constant; `ReportsPane.college_tuition_controls` (the panel instance) and `ReportsPane.college_tuition_controls_scroll_area` (its `QScrollArea`), used directly by tests.

- [ ] **Step 1: Write the failing tests**

Append to `ui/tests/test_reports_tab.py`. First, add this import near the top of the file, alongside the existing `projection_settings` import (after line 12):

```python
from college_tuition_settings import (
    load_college_tuition_settings as _real_load_college_tuition_settings,
    save_college_tuition_settings as _real_save_college_tuition_settings,
)
```

Add this helper near the other `_select_*_report` helpers (after `_select_investment_report`, around line 38):

```python
def _select_college_tuition_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(5, 0), QItemSelectionModel.ClearAndSelect
    )
```

Then append these tests at the end of the file:

```python
def test_reports_list_shows_college_tuition_projection_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(5, 0)) == "College Tuition Projection"


def test_selecting_college_tuition_report_shows_controls_and_chart_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls_scroll_area.isVisible()
    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_selecting_other_report_after_college_tuition_hides_its_controls(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_college_tuition_report(pane)
    _select_net_worth_report(pane)

    assert not pane.college_tuition_controls_scroll_area.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()


def test_selecting_college_tuition_report_autofills_starting_fund_value(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls.starting_fund_value_spinbox.value() == pytest.approx(426.30)


def test_selecting_college_tuition_report_loads_persisted_settings(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        lambda: {"contribution_end_year": 2050, "annual_return_rate": 4.5},
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls.contribution_end_year_spinbox.value() == 2050
    assert pane.college_tuition_controls.annual_return_rate_spinbox.value() == pytest.approx(4.5)


def test_selecting_college_tuition_report_renders_a_fund_balance_line_series(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    chart = pane.chart_view.chart()
    series = chart.series()
    assert [s.name() for s in series if s.name()] == ["College Fund Balance"]
    fund_series = series[0]
    assert fund_series.count() > 1
    assert fund_series.at(0).y() == pytest.approx(426.30)


def test_clicking_update_in_college_tuition_panel_saves_settings_and_rerenders(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    saved = {}
    monkeypatch.setattr(reports_tab, "save_college_tuition_settings", saved.update)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_college_tuition_report(pane)

    pane.college_tuition_controls.contribution_end_year_spinbox.setValue(2050)
    pane.college_tuition_controls.update_button.click()

    assert saved["contribution_end_year"] == 2050
    assert "starting_fund_value" not in saved


def test_persisted_settings_round_trip_through_college_tuition_panel(qapp, dict_conn, monkeypatch, tmp_path):
    settings_path = tmp_path / "college_tuition_settings.json"
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        functools.partial(_real_load_college_tuition_settings, path=settings_path),
    )
    monkeypatch.setattr(
        reports_tab, "save_college_tuition_settings",
        functools.partial(_real_save_college_tuition_settings, path=settings_path),
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_college_tuition_report(pane)
    pane.college_tuition_controls.contribution_end_year_spinbox.setValue(2050)
    pane.college_tuition_controls.set_values({"selected_account_ids": [3]})
    pane.college_tuition_controls.update_button.click()

    pane2 = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        functools.partial(_real_load_college_tuition_settings, path=settings_path),
    )
    _select_college_tuition_report(pane2)

    assert pane2.college_tuition_controls.contribution_end_year_spinbox.value() == 2050
    assert pane2.college_tuition_controls.values()["selected_account_ids"] == [3]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest ui/tests/test_reports_tab.py -v -k college_tuition`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` (`college_tuition_settings` not imported in `reports_tab.py` yet) and `AttributeError: 'ReportsPane' object has no attribute 'college_tuition_controls_scroll_area'`.

- [ ] **Step 3: Write the implementation**

In `ui/reports_tab.py`, add these imports after the existing `projection_settings` import (currently line 46):

```python
from college_tuition import CollegeTuitionInputs, PersonCollegeCosts, compute_college_tuition_projection
from college_tuition_controls import CollegeTuitionControlsPanel, default_college_tuition_values
from college_tuition_settings import load_college_tuition_settings, save_college_tuition_settings
```

Replace the report-id/`REPORTS` block (currently lines 49-60):

```python
NET_WORTH_REPORT_ID = "net_worth_over_time"
SPENDING_BY_CATEGORY_REPORT_ID = "spending_by_category"
INCOME_BY_CATEGORY_REPORT_ID = "income_by_category"
INVESTMENT_ANALYSIS_REPORT_ID = "investment_analysis"
NET_WORTH_PROJECTION_REPORT_ID = "net_worth_projection"
COLLEGE_TUITION_PROJECTION_REPORT_ID = "college_tuition_projection"
REPORTS = [
    (NET_WORTH_REPORT_ID, "Net worth over time"),
    (SPENDING_BY_CATEGORY_REPORT_ID, "Spending by category"),
    (INCOME_BY_CATEGORY_REPORT_ID, "Income by category"),
    (INVESTMENT_ANALYSIS_REPORT_ID, "Investment analysis"),
    (NET_WORTH_PROJECTION_REPORT_ID, "Net Worth Projection"),
    (COLLEGE_TUITION_PROJECTION_REPORT_ID, "College Tuition Projection"),
]
```

In `ReportsPane.__init__`, after the existing `projection_controls_scroll_area` block (currently lines 118-131), add:

```python
self.college_tuition_controls = CollegeTuitionControlsPanel()
self.college_tuition_controls.updated.connect(self._on_college_tuition_updated)

self.college_tuition_controls_scroll_area = QScrollArea()
self.college_tuition_controls_scroll_area.setWidgetResizable(True)
self.college_tuition_controls_scroll_area.setWidget(self.college_tuition_controls)
self.college_tuition_controls_scroll_area.setSizePolicy(
    QSizePolicy.Expanding, QSizePolicy.Ignored
)
self.college_tuition_controls_scroll_area.setVisible(False)
```

In the `chart_layout` assembly (currently line 189, `chart_layout.addWidget(self.projection_controls_scroll_area, 1)`), add immediately after:

```python
chart_layout.addWidget(self.college_tuition_controls_scroll_area, 1)
```

In `_on_selected`, in the "no selection" early-return branch (currently lines 202-214), add alongside the existing `self.projection_controls_scroll_area.setVisible(False)`:

```python
self.college_tuition_controls_scroll_area.setVisible(False)
```

Further down in `_on_selected` (currently lines 215-240), change:

```python
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
        self.projection_controls_scroll_area.setVisible(is_projection_report)
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

to:

```python
        report_id = self.list_model.id_at(indexes[0].row())
        self._active_report_id = report_id
        is_category_report = report_id in self._category_reports
        is_investment_report = report_id == INVESTMENT_ANALYSIS_REPORT_ID
        is_projection_report = report_id == NET_WORTH_PROJECTION_REPORT_ID
        is_college_tuition_report = report_id == COLLEGE_TUITION_PROJECTION_REPORT_ID
        self.view_selector_row.setVisible(is_category_report)
        if is_category_report:
            self.view_selector.blockSignals(True)
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
            self.category_table_view.setModel(self._category_reports[report_id]["model"])
        self.chart_view.setVisible(
            report_id
            in (NET_WORTH_REPORT_ID, NET_WORTH_PROJECTION_REPORT_ID, COLLEGE_TUITION_PROJECTION_REPORT_ID)
        )
        self.category_table_view.setVisible(is_category_report)
        self.investment_table_view.setVisible(is_investment_report)
        self.investment_controls_row.setVisible(is_investment_report)
        self.projection_controls_scroll_area.setVisible(is_projection_report)
        self.college_tuition_controls_scroll_area.setVisible(is_college_tuition_report)
        self.range_controls_row.setVisible(not is_projection_report and not is_college_tuition_report)
        self.range_label.setVisible(not is_projection_report and not is_college_tuition_report)
        if report_id == NET_WORTH_REPORT_ID:
            self._load_net_worth_report()
        elif is_category_report:
            self._load_category_report(report_id)
        elif is_investment_report:
            self._load_investment_report()
        elif is_projection_report:
            self._load_projection_report()
        elif is_college_tuition_report:
            self._load_college_tuition_report()
```

Add three new methods after `_render_projection_chart` (currently ending at line 476):

```python
    def _load_college_tuition_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=False)
        except Exception as exc:
            self._report_error(f"Failed to load college tuition projection report: {exc}")
            return

        investment_accounts = [
            (account_id, name)
            for account_id, name, account_type, _currency, _balance, _is_closed in accounts
            if account_type == INVESTMENT_ACCOUNT_TYPE
        ]
        balances = {
            account_id: self._to_usd(currency, balance)
            for account_id, _name, account_type, currency, balance, _is_closed in accounts
            if account_type == INVESTMENT_ACCOUNT_TYPE
        }
        self.college_tuition_controls.set_accounts(investment_accounts, balances)

        values = default_college_tuition_values()
        values.update(load_college_tuition_settings())
        self.college_tuition_controls.set_values(values)
        self._render_college_tuition_chart()

    def _on_college_tuition_updated(self):
        values = self.college_tuition_controls.values()
        save_college_tuition_settings(
            {key: value for key, value in values.items() if key != "starting_fund_value"}
        )
        self._render_college_tuition_chart()

    def _render_college_tuition_chart(self):
        values = self.college_tuition_controls.values()
        hundred = Decimal("100")
        inputs = CollegeTuitionInputs(
            starting_fund_value=Decimal(str(values["starting_fund_value"])),
            annual_return_rate=Decimal(str(values["annual_return_rate"])) / hundred,
            contribution_per_quarter=Decimal(str(values["contribution_per_quarter"])),
            contribution_end_year=values["contribution_end_year"],
            person1=PersonCollegeCosts(
                start_year=values["person1_start_year"],
                end_year=values["person1_end_year"],
                tuition_per_quarter=Decimal(str(values["person1_tuition_per_quarter"])),
                housing_per_quarter=Decimal(str(values["person1_housing_per_quarter"])),
            ),
            person2=PersonCollegeCosts(
                start_year=values["person2_start_year"],
                end_year=values["person2_end_year"],
                tuition_per_quarter=Decimal(str(values["person2_tuition_per_quarter"])),
                housing_per_quarter=Decimal(str(values["person2_housing_per_quarter"])),
            ),
        )
        rows = compute_college_tuition_projection(inputs)
        quarter_start_month = {1: 1, 2: 4, 3: 7, 4: 10}
        series = [
            (
                "College Fund Balance",
                [(date(row.year, quarter_start_month[row.quarter], 1), row.fund_value) for row in rows],
            )
        ]
        chart = build_line_chart("College Tuition Projection (USD)", series, mark_zero=True)
        self.chart_view.setChart(chart)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest ui/tests/test_reports_tab.py -v`
Expected: PASS (all tests, existing + new, green — confirms no regression to the other six reports)

- [ ] **Step 5: Run the full test suite**

Run: `pytest ui/tests/ -v`
Expected: PASS (every test in the project green)

- [ ] **Step 6: Commit**

```bash
git add ui/reports_tab.py ui/tests/test_reports_tab.py
git commit -m "feat: wire college tuition projection report into Reports tab"
```

---

### Task 7: Manual verification

**Files:** None (manual QA pass — no code changes).

- [ ] **Step 1: Launch the app**

Run: `./run-ui.sh`

- [ ] **Step 2: Verify the new report end-to-end**

- Open the Reports tab, select "College Tuition Projection" — confirm it appears below "Net Worth Projection" in the list.
- Confirm "College savings total" matches the sum of your Investment-type accounts.
- Click "Select Accounts...", uncheck an account, click OK — confirm the total updates immediately.
- Adjust the expected return, joint contribution, contribution end year, and both people's start/end year, tuition, and housing fields; click "Update" — confirm the chart re-renders and reflects the change (e.g. a lower total when both people's college years overlap).
- Set a person's tuition high enough that the balance goes negative — confirm the line dips below the dashed zero-reference line rather than flattening at zero.
- Restart the app (`./run-ui.sh` again) and reselect the report — confirm every input, including the account selection, was remembered.

- [ ] **Step 3: Report results**

No commit for this task — it's verification only. If any issue is found, fix it under a new small task following the same TDD steps as above before considering the feature complete.
