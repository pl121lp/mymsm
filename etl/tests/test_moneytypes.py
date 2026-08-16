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
