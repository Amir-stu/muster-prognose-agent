"""Read real-world exports and reduce them to the two columns the pipeline works on.

Ambiguous formats are never guessed: "1.234" or "01/02/2024" stop the run with the option that resolves them.
`inspect_file` describes a file's structure without returning any measure values.
"""

import re
from numbers import Number
from pathlib import Path
from typing import Any

import pandas as pd

from prognose.schemas import DataMapping

__all__ = [
    "DataMapping",
    "detect_date_order",
    "detect_decimal",
    "inspect_file",
    "normalize_file",
    "parse_numbers",
]

EXCEL_SUFFIXES = (".xlsx", ".xlsm", ".xls")
TEXT_ENCODINGS = ("utf-8-sig", "cp1252")
DELIMITERS = (";", "\t", ",")
MAX_CATEGORIES = 30
MIN_KIND_SHARE = 0.9
MONTHS_PER_YEAR = 12

NUMBER_TOKEN = re.compile(r"^[+-]?\d[\d.,]*$")
THOUSANDS_TOKEN = re.compile(r"^[+-]?\d{1,3}[.,]\d{3}$")
DAY_MONTH_TOKEN = re.compile(r"^(\d{1,2})([./-])(\d{1,2})\2\d{2,4}")
ISO_DATE_TOKEN = re.compile(r"^\d{4}-\d{1,2}(-\d{1,2})?")
SPACES = re.compile(r"[\s ']")


def _tokens(series: pd.Series) -> list[str]:
    return [SPACES.sub("", str(value)) for value in series.dropna()]


def _token_decimal(token: str) -> str | None:
    commas, dots = token.count(","), token.count(".")
    if commas and dots:
        return "komma" if token.rfind(",") > token.rfind(".") else "punkt"
    if commas > 1:
        return "punkt"
    if dots > 1:
        return "komma"
    if not commas and not dots:
        return None
    if THOUSANDS_TOKEN.match(token):
        return "mehrdeutig"
    return "komma" if commas else "punkt"


def detect_decimal(series: pd.Series) -> str:
    """Return komma, punkt, keine (integers only) or mehrdeutig for a column of numbers."""
    if pd.api.types.is_numeric_dtype(series):
        return "keine"
    votes = {_token_decimal(token) for token in _tokens(series) if NUMBER_TOKEN.match(token)} - {None}
    definite = votes - {"mehrdeutig"}
    if len(definite) == 1:
        return definite.pop()
    return "mehrdeutig" if votes else "keine"


def _parse_number(value: Any, decimal: str) -> float:
    if isinstance(value, Number):
        return float(value)
    thousands, mark = (".", ",") if decimal == "komma" else (",", ".")
    try:
        return float(SPACES.sub("", str(value)).replace(thousands, "").replace(mark, "."))
    except ValueError:
        return float("nan")


def parse_numbers(series: pd.Series, decimal: str) -> pd.Series:
    return series.map(lambda value: _parse_number(value, decimal), na_action="ignore").astype(float)


def detect_date_order(series: pd.Series) -> str:
    """Return tag_zuerst, monat_zuerst, eindeutig (ISO or typed dates) or mehrdeutig."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "eindeutig"
    matches = [match for token in _tokens(series) if (match := DAY_MONTH_TOKEN.match(token))]
    if not matches:
        return "eindeutig"
    if any(match.group(2) == "." for match in matches):
        return "tag_zuerst"
    day_first = any(int(match.group(1)) > MONTHS_PER_YEAR for match in matches)
    month_first = any(int(match.group(3)) > MONTHS_PER_YEAR for match in matches)
    if day_first == month_first:
        return "mehrdeutig"
    return "tag_zuerst" if day_first else "monat_zuerst"


def _read_text_table(path: Path) -> pd.DataFrame:
    for encoding in TEXT_ENCODINGS:
        try:
            header = path.read_text(encoding=encoding).splitlines()[0]
        except UnicodeDecodeError:
            continue
        delimiter = max(DELIMITERS, key=header.count)
        return pd.read_csv(path, sep=delimiter, dtype=str, encoding=encoding, skipinitialspace=True)
    raise ValueError(f"Zeichensatz von {path.name} nicht lesbar")


def _read_table(path: Path, sheet: str | None) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    table = (
        pd.read_excel(path, sheet_name=sheet or 0)
        if path.suffix.lower() in EXCEL_SUFFIXES
        else _read_text_table(path)
    )
    return table.rename(columns=lambda name: str(name).strip())


def _require_columns(table: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in table.columns]
    if missing:
        available = ", ".join(table.columns)
        raise ValueError(f"Spalte fehlt: {', '.join(missing)}. Vorhanden: {available}")


def _apply_filters(table: pd.DataFrame, filters: dict[str, str]) -> pd.DataFrame:
    selected = table
    for column, wanted in filters.items():
        selected = selected[selected[column].astype(str).str.strip() == wanted]
    if selected.empty:
        raise ValueError("Der Filter lässt keine Zeilen übrig")
    return selected


def _parse_dates(series: pd.Series, order: str | None) -> pd.Series:
    resolved = order or detect_date_order(series)
    if resolved == "mehrdeutig":
        raise ValueError(
            f"Datumsformat in '{series.name}' ist mehrdeutig. Bitte --date-order tag_zuerst oder monat_zuerst"
        )
    parsed = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=resolved == "tag_zuerst")
    unreadable = int(parsed.isna().sum())
    if unreadable:
        raise ValueError(f"{unreadable} Datumswert(e) in '{series.name}' nicht lesbar")
    return parsed


def _parse_values(series: pd.Series, decimal: str | None) -> pd.Series:
    resolved = decimal or detect_decimal(series)
    if resolved == "mehrdeutig":
        raise ValueError(
            f"Zahlenformat in '{series.name}' ist mehrdeutig (z. B. 1.234). Bitte --decimal komma oder punkt"
        )
    return parse_numbers(series, resolved)


def _combine(frame: pd.DataFrame, rule: str, date_column: str, value_column: str) -> pd.DataFrame:
    if not frame[date_column].duplicated().any():
        return frame
    if rule == "keine":
        raise ValueError(
            "Mehrere Zeilen je Datum. Bitte eine Reihe mit --filter wählen oder --aggregate summe|mittelwert"
        )
    grouped = frame.groupby(date_column, as_index=False)[value_column]
    return grouped.sum(min_count=1) if rule == "summe" else grouped.mean()


def normalize_file(path: Path, mapping: DataMapping, date_column: str, value_column: str) -> pd.DataFrame:
    """Return one sorted series with the pipeline's column names."""
    table = _read_table(path, mapping.sheet)
    _require_columns(table, [mapping.date_column, mapping.value_column, *mapping.filters])
    selected = _apply_filters(table, mapping.filters)
    frame = pd.DataFrame(
        {
            date_column: _parse_dates(selected[mapping.date_column], mapping.date_order),
            value_column: _parse_values(selected[mapping.value_column], mapping.decimal),
        }
    ).sort_values(date_column, kind="stable")
    return _combine(frame, mapping.aggregate, date_column, value_column).reset_index(drop=True)


def _share(tokens: list[str], pattern: re.Pattern[str]) -> float:
    return sum(bool(pattern.match(token)) for token in tokens) / len(tokens) if tokens else 0.0


def _date_details(series: pd.Series) -> dict[str, Any]:
    order = detect_date_order(series)
    if order == "mehrdeutig":
        return {"kind": "datum", "date_order": order}
    parsed = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=order == "tag_zuerst").dropna()
    return {
        "kind": "datum",
        "date_order": order,
        "first": str(parsed.min().date()),
        "last": str(parsed.max().date()),
    }


def _column_details(series: pd.Series) -> dict[str, Any]:
    tokens = _tokens(series)
    if pd.api.types.is_datetime64_any_dtype(series):
        return _date_details(series)
    if _share(tokens, ISO_DATE_TOKEN) + _share(tokens, DAY_MONTH_TOKEN) >= MIN_KIND_SHARE:
        return _date_details(series)
    if pd.api.types.is_numeric_dtype(series) or _share(tokens, NUMBER_TOKEN) >= MIN_KIND_SHARE:
        return {"kind": "zahl", "decimal": detect_decimal(series)}
    categories = sorted({str(value).strip() for value in series.dropna()})
    if len(categories) <= MAX_CATEGORIES:
        return {"kind": "kategorie", "categories": categories}
    return {"kind": "text"}


def _sheet_names(path: Path) -> list[str]:
    if path.suffix.lower() not in EXCEL_SUFFIXES:
        return []
    with pd.ExcelFile(path) as workbook:
        return [str(name) for name in workbook.sheet_names]


def inspect_file(path: Path, sheet: str | None) -> dict[str, Any]:
    """Describe sheets and columns so the user can be asked which series to forecast."""
    table = _read_table(path, sheet)
    columns = [
        {
            "name": name,
            "non_empty": int(table[name].notna().sum()),
            "distinct": int(table[name].nunique()),
            **_column_details(table[name]),
        }
        for name in table.columns
    ]
    return {"file": path.name, "sheets": _sheet_names(path), "rows": len(table), "columns": columns}
