"""Intake turns real-world exports (German CSV, Excel, long tables) into the pipeline's two-column format."""

import pandas as pd
import pytest

from prognose.intake import (
    DataMapping,
    detect_date_order,
    detect_decimal,
    inspect_file,
    normalize_file,
    parse_numbers,
)


def _mapping(**overrides) -> DataMapping:
    return DataMapping(**{"date_column": "Monat", "value_column": "Menge", **overrides})


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["1.234,50", "2.000,00"], "komma"),
        (["1,234.50", "2,000.00"], "punkt"),
        (["12,5", "3,75"], "komma"),
        (["12.5", "3.75"], "punkt"),
        (["1.234.567", "2.345.678"], "komma"),
        (["1,234,567", "2,345,678"], "punkt"),
        (["1.234", "5.678"], "mehrdeutig"),
        (["1,234", "5,678"], "mehrdeutig"),
        (["12", "30"], "keine"),
    ],
)
def test_detect_decimal_when_given_tokens_returns_separator(tokens, expected):
    assert detect_decimal(pd.Series(tokens)) == expected


@pytest.mark.parametrize(
    ("tokens", "decimal", "expected"),
    [
        (["1.234,50", "-2,5"], "komma", [1234.5, -2.5]),
        (["1,234.50", "2.5"], "punkt", [1234.5, 2.5]),
        (["1.234", "5.678"], "komma", [1234.0, 5678.0]),
        (["1.234", "5.678"], "punkt", [1.234, 5.678]),
    ],
)
def test_parse_numbers_when_decimal_known_returns_floats(tokens, decimal, expected):
    assert parse_numbers(pd.Series(tokens), decimal).tolist() == expected


def test_parse_numbers_when_text_value_returns_nan():
    parsed = parse_numbers(pd.Series(["12,5", "k.A."]), "komma")
    assert parsed.iloc[0] == 12.5
    assert pd.isna(parsed.iloc[1])


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["31.01.2024", "29.02.2024"], "tag_zuerst"),
        (["31/01/2024", "29/02/2024"], "tag_zuerst"),
        (["01/31/2024", "02/29/2024"], "monat_zuerst"),
        (["01/02/2024", "03/04/2024"], "mehrdeutig"),
        (["2024-01-31", "2024-02-29"], "eindeutig"),
    ],
)
def test_detect_date_order_when_given_tokens_returns_order(tokens, expected):
    assert detect_date_order(pd.Series(tokens)) == expected


def test_normalize_when_german_semicolon_csv_returns_clean_series(tmp_path):
    path = tmp_path / "export.csv"
    path.write_bytes("Monat;Menge\n31.01.2024;1.234,50\n29.02.2024;2.000,00\n".encode("cp1252"))
    frame = normalize_file(path, _mapping(), "datum", "wert")
    assert list(frame.columns) == ["datum", "wert"]
    assert frame["wert"].tolist() == [1234.5, 2000.0]
    assert frame["datum"].iloc[1] == pd.Timestamp("2024-02-29")


def test_normalize_when_decimal_ambiguous_raises_with_option_name(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text('Monat,Menge\n2024-01-01,"1,234"\n2024-02-01,"5,678"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="--decimal"):
        normalize_file(path, _mapping(), "datum", "wert")


def test_normalize_when_date_order_ambiguous_raises_with_option_name(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text("Monat,Menge\n01/02/2024,1\n03/04/2024,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="--date-order"):
        normalize_file(path, _mapping(), "datum", "wert")


def test_normalize_when_date_unreadable_raises_with_count(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text("Monat,Menge\n2024-01-01,1\nkein Datum,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="1 Datumswert"):
        normalize_file(path, _mapping(), "datum", "wert")


def test_normalize_when_column_missing_lists_available_columns(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text("Periode,Menge\n2024-01-01,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Periode"):
        normalize_file(path, _mapping(), "datum", "wert")


def _long_table(tmp_path):
    path = tmp_path / "lang.xlsx"
    pd.DataFrame(
        {
            "Monat": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01"]),
            "Werk": ["A", "B", "A", "B"],
            "Menge": [10.0, 20.0, 30.0, 40.0],
        }
    ).to_excel(path, sheet_name="Daten", index=False)
    return path


def test_normalize_when_duplicate_dates_without_rule_raises(tmp_path):
    with pytest.raises(ValueError, match="--aggregate"):
        normalize_file(_long_table(tmp_path), _mapping(sheet="Daten"), "datum", "wert")


def test_normalize_when_filter_given_keeps_matching_rows(tmp_path):
    mapping = _mapping(sheet="Daten", filters={"Werk": "B"})
    assert normalize_file(_long_table(tmp_path), mapping, "datum", "wert")["wert"].tolist() == [20.0, 40.0]


@pytest.mark.parametrize(("rule", "expected"), [("summe", [30.0, 70.0]), ("mittelwert", [15.0, 35.0])])
def test_normalize_when_aggregate_given_combines_rows(tmp_path, rule, expected):
    mapping = _mapping(sheet="Daten", aggregate=rule)
    assert normalize_file(_long_table(tmp_path), mapping, "datum", "wert")["wert"].tolist() == expected


def test_normalize_when_filter_matches_nothing_raises(tmp_path):
    mapping = _mapping(sheet="Daten", filters={"Werk": "Z"})
    with pytest.raises(ValueError, match="keine Zeilen"):
        normalize_file(_long_table(tmp_path), mapping, "datum", "wert")


def test_inspect_when_excel_describes_structure_without_measure_values(tmp_path):
    report = inspect_file(_long_table(tmp_path), None)
    columns = {column["name"]: column for column in report["columns"]}
    assert report["sheets"] == ["Daten"]
    assert report["rows"] == 4
    assert columns["Monat"]["kind"] == "datum"
    assert columns["Werk"]["kind"] == "kategorie"
    assert columns["Werk"]["categories"] == ["A", "B"]
    assert columns["Menge"]["kind"] == "zahl"
    assert "40" not in str(columns["Menge"])


def test_inspect_when_german_csv_reports_open_format_questions(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text("Monat;Menge\n01/02/2024;1.234\n03/04/2024;5.678\n", encoding="utf-8")
    columns = {column["name"]: column for column in inspect_file(path, None)["columns"]}
    assert columns["Monat"]["date_order"] == "mehrdeutig"
    assert columns["Menge"]["decimal"] == "mehrdeutig"
