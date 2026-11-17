"""German number formatting for reports."""

THOUSANDS_PLACEHOLDER = "\u0000"


def german_number(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "–"
    english = f"{value:,.{decimals}f}"
    return english.replace(",", THOUSANDS_PLACEHOLDER).replace(".", ",").replace(THOUSANDS_PLACEHOLDER, ".")


def german_percent(share: float | None, decimals: int = 1) -> str:
    if share is None:
        return "–"
    return f"{german_number(share * 100, decimals)} %"
