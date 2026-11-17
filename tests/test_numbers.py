from prognose.numbers import allowed_values, find_unsupported, parse_number_token


def test_parse_token_when_german_decimal_reads_comma():
    assert parse_number_token("0,8") == [(0.8, 1)]


def test_parse_token_when_german_thousands_reads_both():
    assert parse_number_token("1.250,5") == [(1250.5, 1)]


def test_parse_token_when_dot_with_three_digits_is_ambiguous():
    assert set(parse_number_token("1.250")) == {(1.25, 3), (1250.0, 0)}


def test_parse_token_when_plain_integer():
    assert parse_number_token("42") == [(42.0, 0)]


def test_unsupported_when_rounded_value_from_input_passes():
    allowed = allowed_values(['{"slope": 0.8123}'])
    assert find_unsupported("Der Trend steigt um 0,8 pro Monat.", allowed) == []


def test_unsupported_when_invented_value_is_flagged():
    allowed = allowed_values(['{"point": 130.62}'])
    assert find_unsupported("Wir erwarten 1234,5 Einheiten.", allowed) == ["1234,5"]


def test_unsupported_when_percentage_of_share_passes():
    allowed = allowed_values(['{"missing_share": 0.05}'])
    assert find_unsupported("Es fehlen 5 % der Werte.", allowed) == []


def test_unsupported_when_small_integer_passes_without_source():
    assert find_unsupported("Drei Modelle, 2 Zyklen, 12 Monate.", set()) == []


def test_unsupported_when_thirteen_without_source_flagged():
    assert find_unsupported("13 Ausreißer", set()) == ["13"]


def test_unsupported_when_date_year_from_input_passes():
    allowed = allowed_values(['{"date": "2026-01-01"}'])
    assert find_unsupported("Ab Januar 2026 steigt der Wert.", allowed) == []


def test_unsupported_when_approximate_within_one_percent_passes():
    allowed = allowed_values(['{"point": 130.62}'])
    assert find_unsupported("rund 130", allowed) == []
