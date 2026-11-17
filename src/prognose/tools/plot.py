"""Step 07: chart of history, forecast, 80/95 % bands and flagged anomalies."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from prognose.schemas import Anomaly, ForecastResult  # noqa: E402

HISTORY_COLOR = "#2b2b2b"
FORECAST_COLOR = "#1f6fb2"
ANOMALY_COLOR = "#d9622b"
BOUNDARY_COLOR = "#9a9a9a"
FIGURE_SIZE = (11, 5.2)
FIGURE_DPI = 150


def render_chart(
    history: pd.Series, forecast: ForecastResult, anomalies: list[Anomaly], path: Path, title: str
) -> None:
    dates = pd.to_datetime([point.date for point in forecast.points])
    column = {
        name: [getattr(point, name) for point in forecast.points]
        for name in ("point", "lower_80", "upper_80", "lower_95", "upper_95")
    }
    figure, axis = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
    axis.plot(history.index, history.to_numpy(), color=HISTORY_COLOR, linewidth=1.6, label="Historie")
    axis.fill_between(
        dates,
        column["lower_95"],
        column["upper_95"],
        color=FORECAST_COLOR,
        alpha=0.15,
        linewidth=0,
        label="95 %-Band",
    )
    axis.fill_between(
        dates,
        column["lower_80"],
        column["upper_80"],
        color=FORECAST_COLOR,
        alpha=0.30,
        linewidth=0,
        label="80 %-Band",
    )
    axis.plot(
        dates, column["point"], color=FORECAST_COLOR, linewidth=2.0, label=f"Prognose ({forecast.model})"
    )
    if anomalies:
        axis.scatter(
            pd.to_datetime([anomaly.date for anomaly in anomalies]),
            [anomaly.value for anomaly in anomalies],
            color=ANOMALY_COLOR,
            s=40,
            zorder=5,
            label="Auffälligkeit",
        )
    axis.axvline(history.index[-1], color=BOUNDARY_COLOR, linestyle=":", linewidth=1)
    axis.set_title(title, loc="left", fontsize=13)
    axis.grid(alpha=0.25)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, loc="upper left", fontsize=9)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
