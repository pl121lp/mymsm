# Loan Amortization View — Design

Date: 2026-08-24
Status: Approved for implementation

## Problem

There's no way to see a loan account's balance trajectory: how it has
declined since the loan opened, or when it will be fully paid off. This
adds an "Amortization" view for loan accounts on the Accounts tab, showing
one chart with the actual historical balance (since the earliest recorded
transaction) and a projected future balance running to payoff, using the
loan's real interest rate, payment amount, and term as recorded in Money —
not user-entered assumptions.

## Constraints & context

Confirmed during brainstorming:

- **Account-specific view**, not a Reports tab entry: a new "Amortization"
  checkbox on the Accounts tab, next to the existing "Value" checkbox,
  following that exact toggle pattern (`ui/main_window.py`'s
  `value_checkbox` / `VALUE_PAGE` / `_on_value_checkbox_toggled`).
- **Real imported loan terms, not manual entry.** Money's raw `ACCT` table
  (confirmed against this repo's actual `data/raw/ACCT.csv`) has, for every
  loan account: `rateUser`/`rateCalc` (interest rate, populated for all 12
  loan accounts in the current export), `amtPI` (scheduled principal +
  interest payment — distinct from `amtPayment`, which can include escrow;
  e.g. Aynsley Way: `amtPayment=-2184.00` vs `amtPI=-1755.49`), and
  `iPmtMax` (total scheduled number of payments). None of this is currently
  imported into `accounts`. The ETL is extended to pull it in, following
  the exact existing pattern for `interest_category_id`.
- **Payment frequency is inferred from real transaction cadence, not
  Money's `frq` enum.** `frq`'s encoding isn't documented/verified in this
  codebase (see the caution in `etl/column_map.py`'s module docstring), and
  guessing wrong would silently corrupt the projection. Instead, the median
  gap between the loan's actual historical payment dates is snapped to the
  nearest of {monthly, quarterly, semi-annual, annual}. 11 of the 12 real
  loan accounts pay monthly; one (FSB Home Loan) is clearly quarterly —
  this approach gets both right without decoding `frq`.
- **A rebuild of `money.duckdb` is required** after this ships (rerun
  `etl/load.py` against the existing raw CSVs) — this is a deployment step
  for the user, not something the code needs to handle automatically.
- **Missing loan terms → checkbox disabled**, with a tooltip, same
  treatment as the disabled `starting_investment_value_spinbox` in
  `projection_controls.py`.
- Single chart, two series ("Actual" and "Projected") via the existing
  `charts.build_line_chart` — no new chart-builder code needed.
- ARM rate changes, extra/lump-sum future payments, escrow, and editing
  imported terms are all out of scope (see below).

## Architecture

```
etl/
  schema.py           accounts table gains 3 nullable columns:
                       loan_interest_rate DECIMAL(9,6)   (fraction, e.g. 0.05)
                       loan_payment_amount DECIMAL(18,4) (positive, P&I only)
                       loan_payment_count INTEGER
  column_map.py        ACCOUNTS gains:
                       "loan_interest_rate": "rateUser"
                       "loan_interest_rate_fallback": "rateCalc"
                       "loan_payment_amount": "amtPI"
                       "loan_payment_count": "iPmtMax"
  transform.py          build_accounts() parses the three fields into each
                       account dict (None for non-loan / blank-field rows).
  load.py               accounts INSERT extended to 10 columns.

ui/
  data.py               + get_loan_terms(conn, account_id) -> tuple | None
  amortization.py       (new) AmortizationInputs dataclass,
                       AmortizationPoint NamedTuple,
                       infer_payments_per_year(dates) -> int,
                       compute_future_amortization(inputs) -> list | None.
                       Pure, no Qt/DB dependency.
  main_window.py         + amortization_checkbox next to value_checkbox
                       + AMORTIZATION_PAGE = 2 in content_stack
                       + _on_amortization_checkbox_toggled
                       + amortization enable/disable logic in
                         _on_account_selected
```

### `etl/transform.py` — `build_accounts()`

```python
def _to_rate_fraction(raw_primary, raw_fallback):
    decimal_value = _to_decimal(raw_primary) or _to_decimal(raw_fallback)
    return decimal_value / Decimal(100) if decimal_value is not None else None
```

Added to each account dict:

```python
"loan_interest_rate": _to_rate_fraction(
    row.get(ACCOUNTS["loan_interest_rate"]), row.get(ACCOUNTS["loan_interest_rate_fallback"])
),
"loan_payment_amount": (
    abs(amt) if (amt := _to_decimal(row.get(ACCOUNTS["loan_payment_amount"]))) is not None else None
),
"loan_payment_count": _to_int(row.get(ACCOUNTS["loan_payment_count"])),
```

`rateUser`/`rateCalc`/`amtPI`/`iPmtMax` are blank strings (not `"0"`) for
non-loan accounts in the raw export, so `_to_decimal`/`_to_int` naturally
return `None` for them — no `account_type` branching needed in
`build_accounts`.

`loan_payment_count` is imported and stored now for completeness (it's
free — same source row, same INSERT) but isn't consumed by this
iteration's projection math or UI; `compute_future_amortization`'s own
`max_periods` safety cap is generous enough (100 years) that no real loan
term needs it as a cross-check. Reserved for a future display/validation
use.

### `ui/data.py`

```python
def get_loan_terms(conn, account_id) -> tuple | None:
    """(interest_rate, payment_amount, payment_count) for a loan account,
    or None if the account has no row. Any of the three fields may
    individually be None if that data wasn't available in the source."""
    return conn.execute(
        "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
        "FROM accounts WHERE account_id = ?", [account_id],
    ).fetchone()
```

### `ui/amortization.py`

```python
@dataclass
class AmortizationInputs:
    current_balance: Decimal     # liability convention: negative = owed
    annual_rate: Decimal         # fraction, e.g. Decimal("0.05")
    payment_amount: Decimal      # positive, P&I only
    payments_per_year: int
    start_date: date             # date of current_balance; first projected
                                  # point is one period after this

class AmortizationPoint(NamedTuple):
    point_date: date
    balance: Decimal


def infer_payments_per_year(dates: list[date]) -> int:
    """Median gap between sorted dates, snapped to the nearest of
    {12, 4, 2, 1} (monthly/quarterly/semi-annual/annual) payments per
    year. Defaults to 12 (monthly) when fewer than 2 dates are given --
    matches the overwhelming majority of real loan accounts and is a safe
    default for a brand-new loan with no payment history yet."""


def compute_future_amortization(
    inputs: AmortizationInputs, max_periods: int = 1200
) -> list[AmortizationPoint] | None:
    """Standard declining-balance amortization, one point per period,
    stepping from start_date. Each period: interest = -balance *
    (annual_rate / payments_per_year); principal_paid = payment_amount -
    interest; balance += principal_paid. Stops (clamping the final balance
    to exactly 0) once balance reaches 0. Returns None if principal_paid
    is never positive (payment doesn't cover interest) or payoff isn't
    reached within max_periods -- the loan doesn't amortize under its
    recorded terms.

    Dates step by 12 // payments_per_year calendar months (so monthly,
    quarterly, semi-annual, and annual periods all land on sensible
    calendar dates), using the same day-of-month clamping as
    models.py's _add_months.
    """
```

### `ui/main_window.py`

- `AMORTIZATION_PAGE = 2` alongside `TRANSACTIONS_PAGE`/`VALUE_PAGE`;
  `self.amortization_chart_view = QChartView()` added to `content_stack`.
- `self.amortization_checkbox = QCheckBox("Amortization")` added to
  `header_row` next to `value_checkbox`.
- `_on_account_selected`: after the existing `is_loan` check, fetches
  `loan_terms = data.get_loan_terms(self._conn, account_id) if is_loan else None`.
  `has_amortization = is_loan and loan_terms is not None and loan_terms[0] is not None and loan_terms[1]`.
  Sets `amortization_checkbox.setEnabled(has_amortization)`,
  `.setChecked(False)`, and a tooltip
  ("No interest rate/payment data available for this loan.") when disabled,
  clearing it when enabled.
- `_on_value_checkbox_toggled` and the new `_on_amortization_checkbox_toggled`
  each uncheck the other checkbox (signals blocked while doing so) before
  switching `content_stack`'s page, so only one of Transactions/Value/
  Amortization is ever active — same one-active-view invariant the app
  already has between Transactions and Value.
- `_on_amortization_checkbox_toggled(checked)`: mirrors
  `_on_value_checkbox_toggled`'s structure (independently re-fetches the
  selected account's transactions/opening balance/loan terms rather than
  reusing `_on_account_selected` locals, matching the existing pattern):
  1. Not checked, or no selection → `TRANSACTIONS_PAGE`.
  2. `history = compute_account_value_history(transactions, opening_balance, is_investment=False)`,
     converted to USD via `self.account_model.to_usd`.
  3. `last_date, current_balance = history[-1]` if `history` else
     `(date.today(), to_usd(currency, opening_balance or Decimal("0")))`.
  4. `payments_per_year = infer_payments_per_year([d for d, _ in history])`.
  5. Builds `AmortizationInputs` from the above plus
     `to_usd(currency, loan_terms[1])` for `payment_amount` and
     `loan_terms[0]` for `annual_rate`.
  6. `future_points = compute_future_amortization(inputs)`.
  7. If `future_points is None`: sets the chart to just the "Actual"
     series and shows a status bar message ("This loan's payment doesn't
     cover its interest — no projected payoff is possible.").
     Otherwise: prepends `(last_date, current_balance)` to
     `future_points` (so "Projected" visually starts exactly where
     "Actual" ends) and builds
     `build_line_chart(f"{name} — Amortization (USD)", [("Actual", history), ("Projected", projected)], mark_zero=True)`.
  8. `content_stack.setCurrentIndex(AMORTIZATION_PAGE)`.

## Data flow

1. User selects a loan account. `_on_account_selected` fetches its loan
   terms; the Amortization checkbox is enabled only if usable terms exist.
2. User checks "Amortization". `_on_amortization_checkbox_toggled` fetches
   the account's real transaction history, computes the actual balance
   series (existing `compute_account_value_history`), infers payment
   cadence from that series' dates, projects forward from the most recent
   known balance using the imported rate/payment/cadence, and renders both
   series on one chart.
3. Selecting a different account, or unchecking, returns to
   `TRANSACTIONS_PAGE` (existing behavior, extended to also cover the new
   checkbox).

## Error handling

- Loan account with no usable interest rate or payment amount imported
  (rare — a handful of very old/incomplete records): checkbox disabled,
  tooltip explains why, no computation attempted.
- Payment amount doesn't cover the interest owed each period (or payoff
  isn't reached within `max_periods`, a 100-year safety cap):
  `compute_future_amortization` returns `None`; the view still shows the
  real "Actual" history, with a status bar message instead of a
  "Projected" series — never a crash or a runaway/frozen UI.
- Loan with no transaction history yet (just opened): `history` is empty;
  the future projection starts from `opening_balance` at today's date with
  the default monthly cadence.
- Currency conversion of both the historical balance and the projected
  future payment amount uses the existing `to_usd` at today's live rate —
  same simplification already used everywhere else in the app (e.g. Net
  Worth Projection); no FX-drift modeling.

## Testing & packaging

- `etl/tests/test_transform.py`: `build_accounts` extracts
  `loan_interest_rate` (percent-to-fraction conversion; falls back to
  `rateCalc` when `rateUser` is blank), `loan_payment_amount` (absolute
  value), `loan_payment_count`; all three `None` for non-loan accounts and
  for loan rows with blank source fields.
- `etl/tests/test_load.py`: round-trips the three new columns through
  DuckDB with correct types/values.
- `etl/tests/test_schema.py`: schema declares the three new nullable
  columns.
- `ui/tests/test_data.py`: `get_loan_terms` returns the stored row for a
  loan account; `None` fields pass through as `None` when source data was
  incomplete.
- `ui/tests/test_amortization.py` (new): `infer_payments_per_year` for
  monthly and quarterly cadences, and the <2-dates fallback to monthly;
  `compute_future_amortization` for a standard payoff (balance reaches
  exactly 0, point count matches expectations for known inputs), a
  non-amortizing payment returning `None`, and the `max_periods` safety
  cap returning `None`.
- `ui/tests/test_main_window.py`: Amortization checkbox disabled for
  non-loan accounts and for loan accounts missing terms (with tooltip
  text asserted); enabled and renders an Actual+Projected chart for a
  loan account with full data and history; shows the status bar message
  (not a crash) when the loan doesn't amortize; switching account
  selection resets the checkbox and returns to `TRANSACTIONS_PAGE`;
  checking Amortization unchecks Value and vice versa.
- Manual verification: rerun `etl/load.py` against the existing raw CSVs
  to rebuild `money.duckdb`, launch the app (`./run-ui.sh`), select a real
  loan account, toggle Amortization, confirm the chart shows a declining
  balance curve to zero with a visible join point between the actual and
  projected series.
- No new dependencies.

## Out of scope (this iteration)

- ARM rate changes over time (`fARM` loans use their current recorded rate
  held constant for the entire future projection).
- Extra/lump-sum future payments, refinancing, or editable what-if payment
  amounts.
- Escrow/tax/insurance (only the P&I portion, `amtPI`, is modeled — the
  difference between `amtPayment` and `amtPI` is ignored).
- Editing or overriding imported loan terms in the UI.
- A Reports-tab cross-loan comparison view.
- Payment cadences other than {monthly, quarterly, semi-annual, annual} —
  a loan paid weekly/biweekly would be misclassified into the nearest of
  these four.
