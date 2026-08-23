# Net Worth Projection — Design

Date: 2026-08-23
Status: Approved for implementation

## Problem

The app's existing "Net worth over time" report (`ui/reports_tab.py`) is
purely historical — it plots real transaction data up to today. There's no
way to see where things are headed: what the current investment portfolio
grows to, and what overall net worth looks like, under assumptions about
retirement age, investment returns, income, spending, taxes, inflation, and
Social Security. This adds a forward-looking "Net Worth Projection" report
alongside the existing ones.

## Constraints & context

Confirmed during brainstorming:

- Lives as a new entry in the existing Reports tab's report list (not a new
  top-level tab), alongside "Net worth over time", "Spending by category",
  etc.
- Two line series on one chart, not two separate charts: **Investment
  Value** (the starting investment portfolio compounding at the return rate
  alone — pure market growth, no contributions or withdrawals) and **Net
  Worth** (that same starting value, but with each year's net cash flow —
  income minus tax minus spending, plus Social Security once it starts —
  added in and invested too). `charts.build_line_chart` already supports
  multiple named series on a shared date axis, so no new chart-builder code
  is needed.
- Starting investment value auto-fills from real data (sum of current
  investment-account balances, USD-converted) but is shown as an editable
  field, so it can be overridden.
- No existing data tracks age, so a new **birth year** input is added,
  used only to translate "retirement age" into a calendar year
  (`retirement_year = birth_year + retirement_age`).
- Tax is a single flat rate applied to *all* cash inflows — pre-retirement
  income and Social Security — not to investment growth or withdrawals.
- Inflation is a single flat rate that escalates income and spending
  figures year over year. It does not apply to the investment return rate,
  which is already meant to be a real-world/nominal return as entered.
- If projected spending exceeds available resources, net worth is allowed
  to go **negative** (the shortfall keeps compounding at the same return
  rate, as if borrowed) rather than being floored at zero — this makes a
  plan that runs out of money visually obvious, and by how much.
- Inputs persist across app restarts in a sibling git-ignored JSON file,
  following the existing `payee_aliases.json` pattern (`ui/payee_aliases.py`)
  — not `QSettings` (used for the SEK/USD rate), since that pattern isn't
  reusable for a data blob 13 fields wide, and this app's precedent for a
  richer persisted blob is already the JSON-sibling-file approach.
- No per-year table view for this first version — chart only, matching the
  existing "Net worth over time" report's own chart-only layout.
- Update-on-click, not live recompute per keystroke, matching the existing
  range-row "Update" button convention used by other reports.

## Architecture

```
ui/
  projection.py       (new) ProjectionInputs dataclass, YearlyProjection
                       namedtuple, compute_projection(inputs) -> list of
                       YearlyProjection. Pure, no Qt/DB dependency.
  projection_settings.py (new) load_projection_settings(path) /
                       save_projection_settings(settings, path) — JSON
                       sibling file, same shape as payee_aliases.py.
  reports_tab.py       + NET_WORTH_PROJECTION_REPORT_ID in REPORTS.
                       + ProjectionControlsPanel widget (new class in this
                         file): QFormLayout grouped into Timeline,
                         Income & Tax, Spending, Investment Returns, and
                         Social Security sections, plus an "Update" button.
                       + _load_projection_report / _render_projection_chart
                         following the same shape as the existing
                         _load_net_worth_report / _render_net_worth_chart.
  data.py              (no changes — reuses existing list_accounts /
                       list_transactions / compute_account_value_history
                       already used by the historical net worth report to
                       derive today's investment-account total)
```

### `projection.py`

```python
@dataclass
class ProjectionInputs:
    birth_year: int
    end_year: int
    retirement_age: int
    starting_investment_value: Decimal
    return_rate_before_retirement: Decimal   # e.g. Decimal("0.07") = 7%
    return_rate_after_retirement: Decimal
    annual_income: Decimal                   # stops entirely at retirement
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
    income: Decimal            # after inflation, 0 if retired
    social_security: Decimal   # after inflation, 0 before start year
    tax: Decimal
    spending: Decimal          # after inflation
    net_cash_flow: Decimal
    investment_value: Decimal
    net_worth: Decimal

def compute_projection(inputs: ProjectionInputs) -> list[YearlyProjection]:
    ...
```

**Recurrence**, one row per calendar year from the current year through
`end_year` inclusive:

- **Year 0** (current year): a snapshot row — `investment_value =
  net_worth = starting_investment_value`, `income`/`social_security`/
  `spending`/`tax`/`net_cash_flow` all `0` (no growth or cash flow has
  happened yet this year).
- **Each subsequent year** `y` (`years_elapsed = y - current_year`):
  - `retired = y >= birth_year + retirement_age`
  - `inflation_factor = (1 + inflation_rate) ** years_elapsed`
  - `income = 0 if retired else annual_income * inflation_factor`
  - `social_security = social_security_annual_amount * inflation_factor if y >= social_security_start_year else 0`
  - `spending = (spending_after_retirement if retired else spending_before_retirement) * inflation_factor`
  - `tax = (income + social_security) * tax_rate`
  - `net_cash_flow = income + social_security - tax - spending`
  - `return_rate = return_rate_after_retirement if retired else return_rate_before_retirement`
  - `investment_value = prior.investment_value * (1 + return_rate)`
  - `net_worth = (prior.net_worth + net_cash_flow) * (1 + return_rate)`

All arithmetic in `Decimal`, matching the rest of the codebase's handling
of money.

### `projection_settings.py`

Mirrors `payee_aliases.py`'s shape exactly:

```python
DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "projection_settings.json"

def load_projection_settings(path=DEFAULT_SETTINGS_PATH) -> dict:
    """Returns a flat dict of the 13 input fields, or {} if unset."""

def save_projection_settings(settings: dict, path=DEFAULT_SETTINGS_PATH) -> None:
    """settings: flat dict of the 13 input fields (JSON-serializable —
    Decimal fields stored as strings, same as elsewhere in the app)."""
```

Added to `.gitignore` alongside `payee_aliases.json`.

### `reports_tab.py`

- `ProjectionControlsPanel(QWidget)`: owns the 13 input widgets
  (`QSpinBox` for years/ages, `QDoubleSpinBox` for rates/percentages and
  dollar amounts) laid out in a `QFormLayout` with section header labels,
  plus an "Update" button. Exposes `values() -> dict` and
  `set_values(dict)` for load/save, and an `updated` signal emitted on the
  button click.
- Shown/hidden in `_on_selected` the same way `investment_controls_row`
  and `view_selector_row` already are — visible only when
  `NET_WORTH_PROJECTION_REPORT_ID` is selected; `chart_view` visibility
  extends to include this report id alongside `NET_WORTH_REPORT_ID`.
- `_load_projection_report()`: computes `starting_investment_value` as the
  USD-converted sum of current investment-account values (same accounts
  loop and `to_usd` conversion the existing `_load_net_worth_report`
  already performs, filtered to `INVESTMENT_ACCOUNT_TYPE`), loads saved
  settings via `load_projection_settings()` (falling back to sensible
  built-in defaults — e.g. `end_year = current_year + 40`,
  `retirement_age = 65` — for any field not yet saved), populates the
  panel, and renders.
- `ProjectionControlsPanel.updated` → `_on_projection_updated()`: reads
  `panel.values()`, calls `save_projection_settings(values)`, builds
  `ProjectionInputs` from the dict, and re-renders.
- `_render_projection_chart(inputs)`: calls `compute_projection(inputs)`,
  builds `[("Investment Value", [(row_date, row.investment_value) for
  row in rows]), ("Net Worth", [(row_date, row.net_worth) for row in
  rows])]` (using Jan 1 of each `row.year` as the plotted date), passes to
  `build_line_chart("Net Worth Projection (USD)", series)`, sets on the
  shared `chart_view`.

## Data flow

1. User selects "Net Worth Projection" in the report list.
2. `_load_projection_report()` fires: computes today's investment total
   from `data.list_accounts` + `data.list_transactions` +
   `compute_account_value_history` (same calls the historical report
   already makes), loads persisted settings (or defaults), populates
   `ProjectionControlsPanel`, renders the initial chart.
3. User edits any control(s) and clicks "Update".
4. `_on_projection_updated()` fires: reads panel values, persists them to
   `projection_settings.json`, recomputes via `compute_projection`, and
   re-renders the chart.

## Error handling

- `end_year` before the current year, or `retirement_age` that would put
  `retirement_year` before the current year: treated as "already retired
  from year 0" rather than rejected — `compute_projection` doesn't
  validate this, it just produces a (degenerate but well-defined) result.
  The panel's spinboxes use sane `setMinimum`/`setMaximum` bounds to make
  these cases hard to reach by accident, matching how other numeric
  inputs in this app rely on spinbox bounds rather than explicit
  validation.
- Negative or missing `money.duckdb` investment data (no investment
  accounts at all): `starting_investment_value` defaults to `0`, same as
  the existing historical report's handling of an all-zero account set —
  the projection still renders, just flat until cash flow moves it.
- Malformed/missing `projection_settings.json`: `load_projection_settings`
  returns `{}` (same as `payee_aliases.py`'s `_read`), and every missing
  field falls back to its built-in default.

## Testing & packaging

- `ui/tests/test_projection.py` (new): unit tests for `compute_projection`
  — pre/post-retirement transition (income stops, return rate switches),
  Social Security start year, inflation compounding on income/spending,
  tax applied to income + Social Security only, and a shortfall scenario
  asserting `net_worth` goes negative and keeps compounding rather than
  clamping at zero.
- `ui/tests/test_projection_settings.py` (new): round-trip save/load,
  missing-file returns `{}`, matching `test_payee_aliases.py`'s existing
  coverage style for the sibling-JSON pattern.
- Extend `ui/tests/test_reports_tab.py`: selecting the new report shows
  the controls panel and chart, hides the other reports' widgets;
  clicking "Update" triggers a re-render.
- Manual verification: run the app (`./run-ui.sh`), select "Net Worth
  Projection", confirm the starting investment value matches the sum
  shown on the Accounts tab, adjust a few inputs and confirm the chart
  updates, restart the app and confirm inputs were remembered.
- No new dependencies.

## Out of scope (this iteration)

- Per-year data table alongside the chart.
- Any asset types beyond investment accounts feeding the starting value
  (cash/checking balances, real estate, debt) — "net worth" here means
  investment value plus projected cash flow, not the full historical
  report's all-account definition.
- Editable/steppable assumptions mid-projection (e.g. a return rate that
  changes in a specific future year, a one-time expense) — every rate is
  constant across its before/after-retirement phase.
- Monte Carlo / range-of-outcomes projections — single deterministic path
  only.
- Multiple named scenarios or side-by-side comparison.
- Withdrawal-specific tax treatment (e.g. capital gains, required minimum
  distributions) — investment growth and withdrawals are untaxed in this
  model, only income and Social Security are.
