# Muster- und Prognose-Agent

Erkennt Trends, saisonale Schwankungen und Auffälligkeiten in einer Zeitreihe und erstellt daraus
überprüfbare Prognosen, die ein Mensch freigibt, bevor sie als Excel und PowerPoint exportiert werden.

Jeder Kasten des Ablaufdiagramms ist ein eigener Schritt mit eigener Anweisungsdatei in `steps/`.
Ein Orchestrator führt die Schritte der Reihe nach aus, übergibt die Ergebnisse als Dateien und setzt
die beiden Schleifen ("Nein" → Daten nachfordern, "Anpassen" → neu übergeben) um.

## Grundregel: kein LLM erzeugt eine Zahl

Jeder Analyseschritt hat zwei Teile:

1. **Werkzeug** (`src/prognose/tools/`): deterministisches Python, berechnet alle Zahlen.
2. **Subagent**: die Anweisungsdatei `steps/NN_*.md` wird als System-Prompt eines `claude -p`-Laufs
   verwendet. Der Subagent liest die JSON-Ausgaben und schreibt nur Text (`summary`, `notes`).

Jede Zahl im Text des Subagenten muss sich auf eine Zahl in seinen Eingaben zurückführen lassen
(Rundung bzw. 1 % Toleranz, Anteile auch als Prozent). Sonst wird die Antwort einmal mit Rückmeldung
wiederholt und danach der Schritt abgebrochen (`src/prognose/numbers.py`).

## Schritte

| # | Kasten im Diagramm | Art | Ausgabe |
|---|---|---|---|
| 01 | Datenqualität und Historie prüfen | Werkzeug + Subagent | `01_quality.json` |
| 02 | Ausreichende Daten vorhanden? | **Regel**, kein LLM | `02_gate.json` |
| 03 | Daten nachfordern oder Grenzen erklären | Subagent + Werkzeug | `03_data_request.md` |
| 04 | Trends, Saisonalität und Auffälligkeiten erkennen | Werkzeug + Subagent | `04_patterns.json` |
| 05 | Prognosemodelle mit historischen Daten testen | Werkzeug + Subagent | `05_backtest.json` |
| 06 | Geeignetes Modell auswählen und Prognose erstellen | Werkzeug + Subagent | `06_forecast.json` |
| 07 | Ergebnisse mit Unsicherheitsband visualisieren | Werkzeug + Subagent | `07_chart.png` |
| 08 | Deine Prüfung | **Mensch** | `08_review.json` |
| 09 | Daten und Prognoseziel übergeben | **Mensch** | `09_handover.json` |
| 10 | Excel-Auswertung und PowerPoint-Briefing | Subagent + Werkzeug | `10_report.xlsx`, `10_briefing.pptx` |

Methoden: Frequenz und Lücken aus dem Datumsabstand; Trend aus robuster STL-Zerlegung; Saisonprofil und
Auffälligkeiten aus einer robusten Huber-Regression auf Saison-Dummies (|z| > 3,5); Backtest mit
rollierendem Ursprung für saisonal-naiv, ETS (gedämpft, additiv), SARIMA(1,1,1)(0,1,1) und Theta;
Modellwahl nach niedrigstem mittleren MASE, bei Gleichstand bleibt die saisonal-naive Referenz.

## Benutzung

```bash
pip install -e ".[dev]"
prognose synth --out data/synthetic/synthetische_reihe.csv
prognose run --data data/synthetic/synthetische_reihe.csv --horizon 12
prognose review <run_id> --approve
prognose review <run_id> --adjust "nur 6 Monate" --horizon 6
prognose handover <run_id> --data neue_daten.csv
prognose resume <run_id>      # fehlgeschlagenen Lauf an der Fehlerstelle fortsetzen
prognose status <run_id>
```

`--no-llm` ersetzt die Subagenten durch Vorlagentext (kostenlos, für Tests). Daten: CSV oder Excel mit
den Spalten `datum` und `wert` (änderbar in `config.toml`, `[run]`). Alle Schwellenwerte stehen in
`config.toml`; jeder Lauf speichert eine Kopie davon.

Ein Lauf liegt in `runs/<run_id>/`: `state.json` (wird nach jedem Schritt geschrieben, ein abgebrochener
Lauf läuft beim nächsten Aufruf an derselben Stelle weiter), `input/` (Kopien der Daten) und je
Schleifendurchlauf ein Ordner `iter_01/`, `iter_02/`, …

## Tests

```bash
pytest --cov=prognose --cov-report=term-missing
ruff check . && ruff format --check .
```

Die Werkzeuge werden mit synthetischen Reihen getestet, deren Trend, Saison und Ausreißer bekannt sind.
Der Orchestrator wird ohne LLM mit echten Werkzeugen durchlaufen: Ja-Pfad, Nein-Pfad mit Übergabe,
Anpassen-Schleife, Schleifenlimit, Wiederaufnahme und Abbruch bei Zahlen ohne Beleg.

## Grenzen

- Nur eine Reihe pro Lauf; keine Mehrfachreihen (Produkte, Regionen).
- Bisher nur mit synthetischen Daten geprüft.
- Keine erklärenden Variablen (Preise, Aktionen, Feiertage) und keine Strukturbruch-Erkennung.
- Jährliche Daten werden nicht unterstützt (keine Saisonalität bestimmbar).
