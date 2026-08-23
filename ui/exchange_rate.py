"""Fetching the SEK->USD exchange rate from the Frankfurter API."""

import json
from decimal import Decimal, InvalidOperation

FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=SEK&to=USD"


def parse_rate_response(body):
    """Parse a Frankfurter API response body into the SEK->USD rate."""
    try:
        payload = json.loads(body)
        return Decimal(str(payload["rates"]["USD"]))
    except (json.JSONDecodeError, KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid exchange rate response: {body!r}") from exc
