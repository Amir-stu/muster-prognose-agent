---
step: 06_forecast
title: Geeignetes Modell auswählen und Prognose erstellen
kind: tool_llm
tool: forecast
inputs: ziel.json, 05_backtest.json, 06_forecast.json
---
# Rolle

Das Werkzeug `forecast` hat das Modell nach fester Regel gewählt: niedrigster mittlerer MASE im Backtest;
bei Gleichstand oder wenn kein Modell die saisonal-naive Referenz schlägt, bleibt es bei der Referenz.
Dann wurde das Modell auf der ganzen Historie neu geschätzt und die Prognose mit 80- und 95-%-Band erstellt.

# Aufgabe

1. `summary`: Welches Modell, warum (MASE gegen Referenz, Verbesserung in Prozent), und ob es die Referenz
   schlägt (`beats_baseline`). Wenn nicht: klar sagen, dass die Prognose nur die letzte Saison fortschreibt.
2. `notes`: Erster und letzter Prognosewert mit 95-%-Band; wie gut das Band im Backtest kalibriert war
   (`backtest_coverage_80`, `backtest_coverage_95`); ein Hinweis, wenn die Abdeckung deutlich unter dem
   Nennwert lag (Band dann eher zu schmal).

# Nicht tun

- Kein anderes Modell empfehlen als das gewählte.
- Keine Prognosewerte nennen, die nicht in `06_forecast.json` stehen.
