"""Step 10a: Excel workbook. Forecast values are written exactly as they appear in 06_forecast.json."""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from prognose.schemas import BacktestResult, ForecastResult, PatternResult, QualityProfile

COLUMN_WIDTH = 22
NUMBER_FORMAT = "#,##0.00"
CHART_ANCHOR = "A1"


def _table(sheet: Worksheet, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    sheet.append(list(headers))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(list(row))
    for index in range(1, len(headers) + 1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = COLUMN_WIDTH


def _forecast_sheet(sheet: Worksheet, forecast: ForecastResult) -> None:
    headers = (
        "Datum",
        "Prognose",
        "Untergrenze 80 %",
        "Obergrenze 80 %",
        "Untergrenze 95 %",
        "Obergrenze 95 %",
    )
    rows = [
        (date.fromisoformat(p.date), p.point, p.lower_80, p.upper_80, p.lower_95, p.upper_95)
        for p in forecast.points
    ]
    _table(sheet, headers, rows)
    for row in sheet.iter_rows(min_row=2, min_col=2):
        for cell in row:
            cell.number_format = NUMBER_FORMAT


def _history_sheet(sheet: Worksheet, history: pd.Series, patterns: PatternResult) -> None:
    flagged = {anomaly.date for anomaly in patterns.anomalies}
    rows = [
        (stamp.date(), float(value), "ja" if str(stamp.date()) in flagged else "")
        for stamp, value in history.items()
    ]
    _table(sheet, ("Datum", "Wert (bereinigt)", "Auffälligkeit"), rows)


def _backtest_sheet(sheet: Worksheet, backtest: BacktestResult) -> None:
    headers = ("Modell", "Status", "MASE", "sMAPE %", "Abdeckung 80 %", "Abdeckung 95 %", "Fehler")
    rows = [
        (s.model, s.status, s.mean_mase, s.mean_smape, s.mean_coverage_80, s.mean_coverage_95, s.error or "")
        for s in backtest.models
    ]
    _table(sheet, headers, rows)


def _patterns_sheet(sheet: Worksheet, patterns: PatternResult) -> None:
    facts = [
        ("Trendrichtung", patterns.trend_direction),
        ("Trendsteigung pro Periode", patterns.trend_slope_per_period),
        ("Trendstärke (0–1)", patterns.trend_strength),
        ("Saisonstärke (0–1)", patterns.seasonal_strength),
        ("Saisonhoch (Beispieldatum)", patterns.peak_example_date),
        ("Saisontief (Beispieldatum)", patterns.trough_example_date),
        ("Anzahl Auffälligkeiten", len(patterns.anomalies)),
    ]
    profile = [
        (f"Saisonfaktor Position {position}", value)
        for position, value in enumerate(patterns.seasonal_profile)
    ]
    anomalies = [
        (f"Auffälligkeit {a.date}", f"Wert {a.value}, erwartet {a.expected}, z = {a.robust_z}")
        for a in patterns.anomalies
    ]
    _table(sheet, ("Kennzahl", "Wert"), [*facts, *profile, *anomalies])


def write_workbook(
    path: Path,
    history: pd.Series,
    quality: QualityProfile,
    patterns: PatternResult,
    backtest: BacktestResult,
    forecast: ForecastResult,
    chart_path: Path,
) -> None:
    workbook = Workbook()
    _forecast_sheet(workbook.active, forecast)
    workbook.active.title = "Prognose"
    _history_sheet(workbook.create_sheet("Historie"), history, patterns)
    _backtest_sheet(workbook.create_sheet("Backtest"), backtest)
    _patterns_sheet(workbook.create_sheet("Muster"), patterns)
    _table(workbook.create_sheet("Datenqualität"), ("Kennzahl", "Wert"), list(quality.model_dump().items()))
    workbook.create_sheet("Grafik").add_image(ExcelImage(str(chart_path)), CHART_ANCHOR)
    workbook.save(path)
