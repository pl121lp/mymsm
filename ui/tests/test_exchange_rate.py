from decimal import Decimal

import pytest

from exchange_rate import parse_rate_response


def test_parses_usd_rate_from_frankfurter_response():
    body = b'{"amount":1.0,"base":"SEK","date":"2024-01-01","rates":{"USD":0.095}}'
    assert parse_rate_response(body) == Decimal("0.095")


def test_raises_when_usd_rate_missing():
    body = b'{"amount":1.0,"base":"SEK","date":"2024-01-01","rates":{}}'
    with pytest.raises(ValueError):
        parse_rate_response(body)


def test_raises_on_invalid_json():
    with pytest.raises(ValueError):
        parse_rate_response(b"not json")
