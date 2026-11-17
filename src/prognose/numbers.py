"""Check that every number an LLM writes can be traced to a number in its inputs.

Numbers are matched within rounding of the written precision or 1 % relative, so "rund 130" passes
for 130.62 but an invented 1234,5 does not. Shares may be written as percentages.
"""

import re
from collections.abc import Iterable

NUMBER_PATTERN = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")
THOUSANDS_DOT_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
SMALL_INTEGER_LIMIT = 12
RELATIVE_TOLERANCE = 0.01
PERCENT_FACTOR = 100.0


def parse_number_token(token: str) -> list[tuple[float, int]]:
    """Return every plausible (value, decimals) reading of a German- or English-formatted number."""
    if "." in token and "," in token:
        integer_part, decimals = token.replace(".", "").split(",")
        return [(float(f"{integer_part}.{decimals}"), len(decimals))]
    if "," in token:
        integer_part, decimals = token.split(",")
        return [(float(f"{integer_part}.{decimals}"), len(decimals))]
    if "." in token:
        readings = [(float(token), len(token.split(".")[-1]))]
        if THOUSANDS_DOT_PATTERN.match(token):
            readings = [*readings, (float(token.replace(".", "")), 0)]
        return readings
    return [(float(token), 0)]


def allowed_values(texts: Iterable[str]) -> set[float]:
    values = {
        value
        for text in texts
        for token in NUMBER_PATTERN.findall(text)
        for value, _ in parse_number_token(token)
    }
    return values | {value * PERCENT_FACTOR for value in values}


def _matches(value: float, decimals: int, allowed: set[float]) -> bool:
    if decimals == 0 and value <= SMALL_INTEGER_LIMIT:
        return True
    absolute_tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return any(
        abs(value - candidate) <= max(absolute_tolerance, RELATIVE_TOLERANCE * abs(candidate))
        for candidate in allowed
    )


def find_unsupported(text: str, allowed: set[float]) -> list[str]:
    return [
        token
        for token in NUMBER_PATTERN.findall(text)
        if not any(_matches(value, decimals, allowed) for value, decimals in parse_number_token(token))
    ]
