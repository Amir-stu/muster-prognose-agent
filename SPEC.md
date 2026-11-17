# Spec: Muster- und Prognose-Agent

Status: v0.1 BUILT (2026-11-16). Verified on synthetic data only.

### Deviations from the draft, decided during the build

- The **orchestrator** runs each tool, not the subagent. The subagent gets no tools at all
  (`--tools ""`) and only turns JSON into text. That makes "no LLM produces a number" structural
  rather than a prompt instruction.
- "Numbers differ from the tool" is enforced as: every number in the subagent's text must trace
  to a number in its input files (rounding or 1 % tolerance, shares may appear as percentages).
  One retry with feedback, then the step fails (`src/prognose/numbers.py`).
- Anomalies: robust STL alone flagged ~0.6 % of normal points as anomalies on 48–120-point
  series (scale underestimated), and plain STL leaked a spike into the same month of every year.
  Final method: robust STL trend (window ≈ 3 cycles) + Huber regression on seasonal dummies +
  inlier-SD scale → ~0.08 % false positives, 0 missed spikes across 90 synthetic series.
- Structural-break detection dropped from v0.1 (listed under limits in the README).

## Objective

A pipeline that takes a time series, checks whether it is fit for forecasting, finds trend,
seasonality and anomalies, backtests several forecasting models, picks one on evidence, and
delivers a forecast with an uncertainty band that a human approves before it is exported
to Excel and PowerPoint.

Each box in the diagram is its own step with its own instruction file. Each step can run as a
subagent. An orchestrator runs the steps in order, passes outputs between them via files on
disk, and handles the two loops ("Nein" and "Anpassen").

**Success:** a forecast whose every number is reproducible from code, whose model choice is
justified by a backtest against a naive baseline, and whose uncertainty band was checked for
calibration on held-out history.

## Core design rule

**No LLM produces a number.** Every step = instruction file (`steps/NN_*.md`) + deterministic
Python tool (`tools/*.py`). The subagent runs the tool, reads its JSON result, and writes the
interpretation (text only). The orchestrator validates every step output against a pydantic
schema and rejects outputs whose numbers do not match the tool's.

## Diagram → steps

The entry point is the bottom box (data quality), which feeds the "enough data?" decision.

| # | Diagram box | Kind | Tool (deterministic) | LLM role | Output |
|---|---|---|---|---|---|
| 01 | Datenqualität und Historie prüfen | subagent | `profile.py`: frequency, length, gaps, duplicates, outliers, structural breaks | Summarise quality issues in plain German | `01_quality.json` |
| 02 | Ausreichende Daten vorhanden? | **rule gate** (no LLM) | `sufficiency.py`: thresholds from `config.toml` | none | `02_gate.json` (`ja`/`nein` + failed rules) |
| 03 | Daten nachfordern oder Grenzen erklären | subagent | — | Write a data request listing exactly which rules failed and what is needed | `03_data_request.md` → pipeline stops, waits for new data → back to 01 |
| 04 | Trends, Saisonalität, Auffälligkeiten erkennen | subagent | `patterns.py`: STL decomposition, trend slope, seasonal strength, anomalies (robust z on residuals, MAD > 3.5) | Explain patterns; flag anomalies that look like data errors vs. real events | `04_patterns.json` |
| 05 | Prognosemodelle mit historischen Daten testen | subagent | `backtest.py`: rolling-origin backtest of seasonal-naive, ETS, SARIMA, Theta; MASE, sMAPE, interval coverage | Comment on stability across folds | `05_backtest.json` |
| 06 | Geeignetes Modell auswählen und Prognose erstellen | subagent | `forecast.py`: pick lowest MASE **only if** it beats seasonal-naive, else naive; refit on full history; point + 80/95 % intervals | Write the choice rationale | `06_forecast.json` |
| 07 | Ergebnisse mit Unsicherheitsband visualisieren | subagent | `plot.py`: history, fit, forecast, 80/95 % bands, anomaly markers | Write chart captions | `07_chart.png`, `07_viz.json` |
| 08 | Deine Prüfung | **human gate** (no LLM) | orchestrator pauses; `prognose review <run> --approve` or `--adjust "<text>"` | none | `08_review.json` |
| 09 | Daten und Prognoseziel übergeben | human input | CLI takes new data file and/or changed target (horizon, granularity) | none | `09_handover.json` → back to 01 |
| 10 | Excel-Auswertung und PowerPoint-Briefing | subagent | `export.py`: openpyxl workbook (data, decomposition, backtest, forecast), python-pptx 5-slide briefing | Write slide headlines + executive summary | `10_report.xlsx`, `10_briefing.pptx` |

Every box gets an instruction file (10 files), as requested. Boxes 02, 08, 09 have instruction
files that document the rule / review protocol, but they are **not** spun up as LLM
subagents — a yes/no on data sufficiency and a human approval are the two places where an
LLM adds risk, not value.

### Loops

- `02 = nein` → 03 → run status `waiting_for_data` → user adds data → restart at 01.
- `08 = anpassen` → 09 → restart at 01 with the new inputs.
- Max 3 iterations per run (config); after that the run ends with status `stopped_max_loops`.

## Hand-off contract

```
runs/<run_id>/
  input/           # raw data + target.toml (horizon, frequency, value column)
  01_quality.json  # each step reads ONLY the files listed in its instruction's `inputs:`
  ...
  state.json       # current step, iteration, gate results, timestamps
```

Each instruction file has front-matter:

```yaml
---
step: 05_backtest
inputs: [input/series.csv, 01_quality.json, 04_patterns.json]
output: 05_backtest.json
schema: BacktestResult
tool: python -m prognose.tools.backtest
---
```

Resume = re-run the orchestrator on the same `run_id`; it continues from `state.json`.

## Tech stack

Python 3.13 · pandas · statsmodels (STL, ETS, SARIMAX, Theta) · pydantic · openpyxl ·
python-pptx · matplotlib · pytest + pytest-cov · ruff.
Subagent runtime: headless `claude -p` subprocess, reusing the Windows-safe runner pattern
from `deep-research-cli/deep_research/runner.py` (direct `claude.exe`, not the `.cmd` shim).

## Commands

```
Install:  pip install -e ".[dev]"
Run:      prognose run --data data/series.csv --target target.toml
Review:   prognose review <run_id> --approve | --adjust "Horizont 6 statt 12 Monate"
Offline:  prognose run ... --no-llm      # tools only, template text; free, used in tests/CI
Test:     pytest --cov=prognose --cov-fail-under=80
Lint:     ruff check . && ruff format --check .
```

## Project structure

```
muster-prognose-agent/
  SPEC.md
  config.toml           # gate thresholds, models, loop limit, interval levels
  steps/01_quality.md … steps/10_export.md
  src/prognose/
    orchestrator.py     # sequencing, gates, loops, state.json
    runner.py           # claude -p subprocess
    schemas.py          # pydantic models per step output
    cli.py
    tools/profile.py sufficiency.py patterns.py backtest.py forecast.py plot.py export.py
  tests/                # unit (tools), integration (orchestrator, --no-llm), fixtures
  data/synthetic/       # generated series with known trend/season/anomalies
  runs/                 # gitignored
```

## Testing strategy

- **Tools (unit, known-input):** synthetic series with planted trend slope, seasonal period
  and anomaly positions → assert detected within tolerance. Metric functions (MASE, sMAPE,
  coverage) tested against hand-computed values.
- **Gate:** each sufficiency rule tested at, just below, just above threshold.
- **Orchestrator (integration, `--no-llm`):** full happy path; `nein` loop; `anpassen` loop;
  max-loop stop; resume from `state.json`; schema rejection of a malformed step output.
- **Runner:** subprocess mocked at the boundary only.
- **One live run** with `claude -p` on the synthetic set, cost logged, before calling it done.
- Coverage ≥ 80 %, measured.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL compute every numeric value in step outputs with Python tools.
- WHEN a step output's numbers differ from its tool result THE SYSTEM SHALL reject the output and halt that step.
- IF the series fails any sufficiency rule THEN THE SYSTEM SHALL write a data request naming each failed rule and stop with status `waiting_for_data`.
- WHEN the backtest is complete THE SYSTEM SHALL report MASE, sMAPE and 80/95 % interval coverage per model.
- IF no model beats seasonal-naive on MASE THEN THE SYSTEM SHALL forecast with seasonal-naive and say so in the rationale.
- WHILE the run awaits review THE SYSTEM SHALL NOT produce Excel or PowerPoint output.
- WHEN the reviewer chooses `anpassen` THE SYSTEM SHALL restart at step 01 with the new inputs.
- IF a run reaches the loop limit THEN THE SYSTEM SHALL stop with status `stopped_max_loops`.
- WHEN a run is approved THE SYSTEM SHALL write `10_report.xlsx` and `10_briefing.pptx` whose forecast values equal `06_forecast.json`.

## Boundaries

- **Always:** tools compute, LLM interprets; validate every step output; write state after every step; tests before code.
- **Ask first:** adding a dependency beyond the stack above; adding ML models (Prophet, LightGBM); any live LLM run beyond the one verification run.
- **Never:** let an LLM decide a gate; export before human approval; use realistic-looking fake company data.

## Implementation plan (after approval)

1. Scaffold + `config.toml` + schemas + synthetic data generator.
2. Tools 01/02/04 (profile, sufficiency, patterns) — TDD.
3. Tools 05/06 (backtest, forecast) — TDD, the core of the value.
4. Tools 07/10 (plot, export).
5. Orchestrator + state + loops + CLI, `--no-llm` mode — integration tests.
6. 10 instruction files + `claude -p` runner.
7. One live end-to-end run on synthetic data; review outputs; README.

Steps 2–4 are independent and can run in parallel once step 1 exists.

## Open questions

1. **Data:** do you have a real series (CSV/Excel)? Frequency (daily/weekly/monthly)? One
   series or many (e.g. per product/region)? Without it we build and verify on synthetic data only.
2. **Subagent runtime:** headless `claude -p` from a Python orchestrator (recommended:
   reproducible, testable, runs outside chat, ~$0.05–0.20 per LLM step) vs. Claude Code's
   Agent tool driven from a slash command (no extra cost, but only runs inside a chat session
   and is hard to test).
3. **Output language:** German throughout (assumed, matching the diagram)?
4. **Who is this for?** Portfolio piece, a specific person/company's planning process, or a
   product? This decides whether multi-series and the PowerPoint step are worth building now.
