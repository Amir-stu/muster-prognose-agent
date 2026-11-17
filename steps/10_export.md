---
step: 10_export
title: Excel-Auswertung und PowerPoint-Briefing
kind: tool_llm
tool: export
inputs: ziel.json, 01_quality.interpretation.json, 04_patterns.json, 04_patterns.interpretation.json, 05_backtest.json, 06_forecast.json, 06_forecast.interpretation.json, 07_visualize.interpretation.json, 08_review.json
llm_first: true
---
# Rolle

Die Prognose ist freigegeben. Du schreibst die Kernaussagen für die letzte Folie des PowerPoint-Briefings.
Das Werkzeug `export` baut danach Excel und PowerPoint; alle Tabellenwerte kommen direkt aus den JSON-Dateien.

# Aufgabe

1. `summary`: Die Prognose in zwei bis drei Sätzen für eine Führungskraft: Richtung, Größenordnung am Ende
   des Horizonts, wie sicher (Bandbreite) und auf welchem Modell sie beruht.
2. `notes`: Höchstens vier Punkte: das wichtigste Muster, die wichtigste Einschränkung (Datenlage, Kalibrierung,
   Auffälligkeiten) und, falls vorhanden, der Kommentar aus der Prüfung (`08_review.json`).

# Nicht tun

- Keine Handlungsempfehlungen, die nicht aus den Daten folgen.
- Keine neuen Zahlen; die Prognosewerte stehen in `06_forecast.json`.
