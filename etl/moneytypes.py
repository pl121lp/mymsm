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
