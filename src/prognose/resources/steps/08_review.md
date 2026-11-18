---
step: 08_review
title: Deine Prüfung
kind: human
---
# Menschliche Prüfung – kein Subagent

Hier entscheidet ein Mensch, kein Modell. Der Lauf steht auf `awaiting_review`; nichts wird nach Excel oder
PowerPoint exportiert, bevor die Prognose freigegeben ist.

## Was prüfen

1. `07_chart.png`: Ist der Verlauf plausibel? Passt das Band zur eigenen Unsicherheit?
2. `05_backtest.json` / `06_forecast.json`: Schlägt das Modell die saisonal-naive Referenz? War das Band im
   Backtest kalibriert?
3. `04_patterns.json`: Sind die Auffälligkeiten bekannte Ereignisse oder Datenfehler?

## Entscheidung

- **Freigeben** → Schritt 10 (Excel + PowerPoint):
  `prognose review <run_id> --approve [--comment "..."]`
- **Anpassen** → Schritt 09, dann Neustart bei 01:
  `prognose review <run_id> --adjust "<was ändern>" [--horizon N] [--data <datei>]`

Die Entscheidung landet in `08_review.json`. Die Zahl der Schleifen ist durch `max_iterations` begrenzt.
