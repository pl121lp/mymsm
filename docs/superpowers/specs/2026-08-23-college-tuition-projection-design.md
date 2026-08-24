# College Tuition Projection — Design

Date: 2026-08-23
Status: Approved for implementation

## Problem

There's no way to see whether current college savings will cover two
upcoming college educations. This adds a forward-looking "College Tuition
Projection" report to the Reports tab, alongside "Net Worth Projection",
projecting a combined college-savings fund balance quarter by quarter
against tuition, housing, and contribution assumptions for two people.

## Constraints & context

Confirmed during brainstorming:

- Lives as a new entry in the existing Reports tab's report list, following
  the exact pattern of "Net Worth Projection" (`ui/reports_tab.py`,
  `ui/projection.py`, `ui/projection_settings.py`, `ui/projection_controls.py`).
- **Single shared pool**: the selected college savings accounts sum to one
  combined starting balance. Both people's tuition and housing costs are
  withdrawn from that same pool each quarter they're active; there is no
  per-person sub-balance.
- **Single joint contribution**, not per-person: one "additional investment
  contribution per quarter" amount, applied every quarter from now through
  a selectable end year (not tied to either person's start/end year).
- Fund balance is **allowed to go negative** if costs exceed what's
  available in a quarter — matches Net Worth Projection's convention of
  making a shortfall visually obvious (via `mark_zero=True`) rather than
  flooring at zero.
- Projection steps **quarterly**, not yearly (the one structural difference
  from Net Worth Projection) — tuition, housing, and contribution are all
  per-quarter figures.
- Each person has a **start year** and **end year** (whole years); they are
  "active" — their tuition + housing costs apply — in all four quarters of
  every year in `[start_year, end_year]` inclusive. No sub-year (which
  quarter within a year) granularity.
- Contribution end is **year-granularity**, matching the person fields:
  contribution applies through Q4 of `contribution_end_year`.
- Account picker is restricted to **Investment-type accounts** (account
  type `"5"`), the same type Net Worth Projection sums for
  `starting_investment_value` — 529/brokerage-style accounts live here in
  this schema.
- Starting fund value auto-fills from the sum of selected accounts'
  USD-converted balances, shown as a disabled/tooltipped field (never
  persisted, always recomputed live) — same treatment as
  `starting_investment_value` in Net Worth Projection.
- Selected account IDs **are** persisted (unlike the computed sum) since
  they're a user choice, not derived data.
- Inputs persist across restarts in a sibling git-ignored JSON file
  (`college_tuition_settings.json`), following the exact
  `projection_settings.py` pattern.
- Update-on-click, not live recompute per keystroke, matching the existing
  convention.
- No per-quarter table view — chart only.
- No new chart-builder code: `charts.build_line_chart` already supports a
  single date/value series with `mark_zero=True`.

## Architecture

```
ui/
  college_tuition.py          (new) PersonCollegeCosts dataclass,
                               CollegeTuitionInputs dataclass,
                               QuarterlyProjection NamedTuple,
                               compute_college_tuition_projection(inputs)
                               -> list of QuarterlyProjection. Pure, no
                               Qt/DB dependency.
  college_tuition_settings.py (new) load_college_tuition_settings(path) /
                               save_college_tuition_settings(settings, path)
                               — JSON sibling file, same shape as
                               projection_settings.py.
  college_tuition_controls.py (new) CollegeTuitionControlsPanel(QWidget),
                               default_college_tuition_values().
  category_filter_dialog.py   + AccountFilterDialog(QDialog): id-keyed
                               (not name-keyed) checkbox-list dialog, since
                               CategoryFilterDialog/InvestmentFilterDialog
                               key selection by display name and account
                               names aren't guaranteed unique.
  reports_tab.py               + COLLEGE_TUITION_PROJECTION_REPORT_ID in
                               REPORTS.
                               + college_tuition_controls widget instance,
                               wired into _on_selected visibility exactly
                               like projection_controls_scroll_area /
                               chart_view are for NET_WORTH_PROJECTION_REPORT_ID.
                               + _load_college_tuition_report /
                               _on_college_tuition_updated /
                               _render_college_tuition_chart, following the
                               same shape as the existing
                               _load_projection_report / _on_projection_updated
                               / _render_projection_chart.
  data.py                      (no changes — reuses list_accounts,
                               INVESTMENT_ACCOUNT_TYPE)
```

### `college_tuition.py`

```python
@dataclass
class PersonCollegeCosts:
    start_year: int
    end_year: int
    tuition_per_quarter: Decimal
    housing_per_quarter: Decimal

@dataclass
class CollegeTuitionInputs:
    starting_fund_value: Decimal
    annual_return_rate: Decimal      # e.g. Decimal("0.06") = 6%
    contribution_per_quarter: Decimal
    contribution_end_year: int
    person1: PersonCollegeCosts
    person2: PersonCollegeCosts

class QuarterlyProjection(NamedTuple):
    year: int
    quarter: int               # 1-4
    person1_cost: Decimal      # tuition + housing, 0 if not active this year
    person2_cost: Decimal
    contribution: Decimal      # 0 once past contribution_end_year
    net_cash_flow: Decimal
    fund_value: Decimal

def compute_college_tuition_projection(
    inputs: CollegeTuitionInputs,
    current_year: int | None = None,
    current_quarter: int | None = None,
) -> list[QuarterlyProjection]:
    ...
```

**Recurrence**, one row per calendar quarter from the current quarter
through the last relevant quarter:

- `current_quarter` defaults to `(date.today().month - 1) // 3 + 1`.
- **Quarter 0** (current quarter): a snapshot row — `fund_value =
  starting_fund_value`, `person1_cost`/`person2_cost`/`contribution`/
  `net_cash_flow` all `0` (no growth or cash flow has happened yet this
  quarter, matching Net Worth Projection's year-0 snapshot row).
- `end_year = max(person1.end_year, person2.end_year, contribution_end_year)`;
  iteration continues through Q4 of `end_year`.
- **Each subsequent quarter** `(year, quarter)`, stepping quarter-by-quarter
  from the snapshot (wrapping quarter 4→1 and incrementing year):
  - `person1_active = person1.start_year <= year <= person1.end_year`
  - `person1_cost = (person1.tuition_per_quarter + person1.housing_per_quarter) if person1_active else 0`
    (symmetric for `person2`)
  - `contribution = inputs.contribution_per_quarter if year <= inputs.contribution_end_year else 0`
  - `net_cash_flow = contribution - person1_cost - person2_cost`
  - `quarterly_rate = (1 + inputs.annual_return_rate) ** Decimal("0.25") - 1`
    (computed once; `Decimal.__pow__` with a `Decimal` exponent is
    correctly-rounded per the decimal module's IEEE 854 support)
  - `fund_value = (prior.fund_value + net_cash_flow) * (1 + quarterly_rate)`

No flooring at zero — `fund_value` can go negative and keeps compounding,
same as Net Worth Projection's `net_worth`.

A person whose `start_year > end_year` is simply never active (degenerate
but well-defined), same philosophy as Net Worth Projection's handling of
out-of-order year inputs — no explicit validation, spinbox bounds only.

### `college_tuition_settings.py`

Mirrors `projection_settings.py` exactly:

```python
DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "college_tuition_settings.json"

def load_college_tuition_settings(path=DEFAULT_SETTINGS_PATH) -> dict:
    """Returns a flat dict of saved input fields, or {} if unset/malformed."""

def save_college_tuition_settings(settings, path=DEFAULT_SETTINGS_PATH) -> None:
    """settings: flat dict of input fields (JSON-serializable)."""
```

Same defensive `try/except (json.JSONDecodeError, OSError)` on load as the
existing module (per the malformed-settings-file fix already applied to
`projection_settings.py`). Added to `.gitignore` alongside
`projection_settings.json`.

### `category_filter_dialog.py` — `AccountFilterDialog`

```python
class AccountFilterDialog(QDialog):
    def __init__(self, accounts, selected_ids, parent=None):
        """accounts: iterable of (account_id, name) pairs.
        selected_ids: set of currently-selected account_id.
        """
        ...
    def selected_account_ids(self) -> set:
        ...
```

Same visual shape as `CategoryFilterDialog` (checkbox `QListWidget`,
Select All/None buttons, OK/Cancel), but each `QListWidgetItem` stores
`account_id` via `setData(Qt.UserRole, account_id)` instead of keying
selection by item text, so it's correct even if two accounts share a
display name.

### `college_tuition_controls.py`

- `default_college_tuition_values(today=None)`: built-in defaults for a
  first-time load — e.g. `annual_return_rate=6.0`,
  `contribution_per_quarter=0.0`, `contribution_end_year=today.year+12`,
  `person1_start_year=today.year+5`, `person1_end_year=today.year+9`,
  `person1_tuition_per_quarter=10000.0`,
  `person1_housing_per_quarter=4000.0`, `person2_start_year=today.year+8`,
  `person2_end_year=today.year+12`, same tuition/housing defaults as
  person1.
- `CollegeTuitionControlsPanel(QWidget)`: `QVBoxLayout` of labeled
  `QFormLayout` sections — **College Savings Accounts** (a disabled/
  tooltipped `starting_fund_value` dollar field + a "Select Accounts..."
  button opening `AccountFilterDialog`), **Investment Return**
  (`annual_return_rate` percent spinbox), **Contribution**
  (`contribution_per_quarter` dollar spinbox, `contribution_end_year` year
  spinbox), **Person 1** and **Person 2** (each: `start_year`, `end_year`
  year spinboxes, `tuition_per_quarter`, `housing_per_quarter` dollar
  spinboxes), plus an "Update" button. Reuses the existing
  `_year_spinbox`/`_percent_spinbox`/`_dollar_spinbox` factories (moved to
  a shared location or duplicated locally — implementation detail for the
  plan) from `projection_controls.py`.
- `set_accounts(accounts)`: `accounts` = iterable of `(account_id, name)`
  Investment-type pairs, stored for the "Select Accounts..." dialog;
  called from `reports_tab.py` the same way `set_house_accounts` is today.
- `values() -> dict` / `set_values(values)`: same flat-dict, partial-update,
  `try/except TypeError: continue`-per-key shape as
  `ProjectionControlsPanel`. `values()` includes `selected_account_ids`
  (list, JSON-serializable) and the live `starting_fund_value`;
  `set_values` restores the checkbox selection state (defaulting to **all**
  Investment accounts selected if `selected_account_ids` is absent, i.e.
  first-time load) and populates every other field.
- `updated` signal, emitted on the Update button click.

### `reports_tab.py`

- `COLLEGE_TUITION_PROJECTION_REPORT_ID = "college_tuition_projection"`,
  added to `REPORTS` as `("College Tuition Projection")`.
- `self.college_tuition_controls = CollegeTuitionControlsPanel()`, wrapped
  in its own `QScrollArea` exactly like `projection_controls_scroll_area`,
  connected `updated -> self._on_college_tuition_updated`.
- `_on_selected`: adds `is_college_tuition_report = report_id ==
  COLLEGE_TUITION_PROJECTION_REPORT_ID`; extends `chart_view` visibility to
  include this id; toggles the new scroll area's visibility; dispatches to
  `_load_college_tuition_report()`.
- `_load_college_tuition_report()`: loads Investment-type accounts via
  `data.list_accounts(self._conn, include_closed=False)`, filtered to
  `INVESTMENT_ACCOUNT_TYPE`, calls
  `self.college_tuition_controls.set_accounts(...)`; loads
  `default_college_tuition_values()` merged with
  `load_college_tuition_settings()`; computes `starting_fund_value` as the
  USD-converted sum of the accounts whose id is in the loaded/defaulted
  `selected_account_ids` (all Investment accounts if unset); populates the
  panel; renders.
- `_on_college_tuition_updated()`: reads `panel.values()`, saves everything
  except `starting_fund_value` via `save_college_tuition_settings`,
  re-derives `starting_fund_value` from the (possibly just-changed)
  `selected_account_ids` against the cached account balances, and
  re-renders.
- `_render_college_tuition_chart()`: builds `CollegeTuitionInputs` from
  panel values, calls `compute_college_tuition_projection`, maps each row
  to a plotted date (`Q1→Jan 1`, `Q2→Apr 1`, `Q3→Jul 1`, `Q4→Oct 1` of
  `row.year`), builds a single `[("College Fund Balance", points)]` series,
  passes to `build_line_chart("College Tuition Projection (USD)", series,
  mark_zero=True)`, sets on the shared `chart_view`.

## Data flow

1. User selects "College Tuition Projection" in the report list.
2. `_load_college_tuition_report()` fires: loads Investment accounts,
   loads persisted settings (or defaults, with all accounts selected),
   computes the starting fund value, populates
   `CollegeTuitionControlsPanel`, renders the initial chart.
3. User edits inputs and/or changes account selection via "Select
   Accounts...", clicks "Update".
4. `_on_college_tuition_updated()` fires: persists inputs (account
   selection included), recomputes the starting fund value from the
   current selection, recomputes the projection, re-renders the chart.

## Error handling

- Same philosophy as Net Worth Projection: spinbox `setRange` bounds are
  the only input constraint; out-of-order years produce a degenerate but
  well-defined (never-active) person rather than a validation error.
- No Investment accounts at all, or none selected: `starting_fund_value`
  defaults to `0`; the projection still renders, driven purely by
  contribution/cost cash flow.
- Malformed/missing `college_tuition_settings.json`: `{}`, same as
  `projection_settings.py`; every missing field falls back to its
  built-in default.

## Testing & packaging

- `ui/tests/test_college_tuition.py` (new): unit tests for
  `compute_college_tuition_projection` — quarter-0 snapshot, a person
  becoming active/inactive at their start/end year boundaries, both
  people overlapping in the same quarter, contribution stopping after
  `contribution_end_year`, quarterly compounding math, and a shortfall
  scenario asserting `fund_value` goes negative and keeps compounding.
- `ui/tests/test_college_tuition_settings.py` (new): round-trip save/load,
  missing-file returns `{}`, malformed-file returns `{}` — same coverage
  style as `test_projection_settings.py`.
- `ui/tests/test_college_tuition_controls.py` (new): `values()`/
  `set_values()` round-trip including `selected_account_ids`, partial
  `set_values` updates only given keys, default-all-selected behavior when
  `selected_account_ids` is absent.
- Extend `ui/tests/test_category_filter_dialog.py` (or create it if it
  doesn't exist yet): `AccountFilterDialog` selects/deselects by id, not
  name, and Select All/None work.
- Extend `ui/tests/test_reports_tab.py`: selecting the new report shows
  its controls panel and chart, hides other reports' widgets; clicking
  "Update" triggers a re-render; end-to-end settings round-trip through
  two separate `ReportsPane` instances (mirroring
  `test_persisted_settings_round_trip_through_panel`).
- Manual verification: run the app (`./run-ui.sh`), select "College
  Tuition Projection", confirm the starting fund value matches the sum of
  selected Investment accounts, narrow the account selection and confirm
  the value updates, adjust inputs and confirm the chart updates, restart
  the app and confirm inputs (including account selection) were
  remembered.
- No new dependencies.

## Out of scope (this iteration)

- Per-quarter data table alongside the chart.
- Per-person sub-balances or separate fund tracking.
- Sub-year (which specific quarter within a year) activity granularity for
  a person's start/end window.
- Quarter-level precision on the contribution end date.
- Editable/steppable assumptions mid-projection (e.g. a return rate that
  changes in a specific future year).
- Monte Carlo / range-of-outcomes projections — single deterministic path
  only.
- Multiple named scenarios or side-by-side comparison.
- Named/labeled people beyond "Person 1" / "Person 2" section headers.
- Account types beyond Investment feeding the fund (Bank/Asset accounts
  are not offered in the picker).
