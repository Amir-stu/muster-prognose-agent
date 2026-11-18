---
step: 05_backtest
title: Prognosemodelle mit historischen Daten testen
kind: tool_llm
tool: backtest
inputs: ziel.json, 04_patterns.json, 05_backtest.json
---
# Rolle

Du bewertest einen Backtest. Das Werkzeug `backtest` hat jedes Modell (saisonal-naiv als Referenz, ETS,
SARIMA, Theta) mehrfach auf zurückgehaltener Historie getestet (rollierender Ursprung) und gemessen:

- **MASE**: Fehler relativ zum saisonal-naiven Fehler in der Trainingsphase. Unter 1 = besser als naiv.
- **sMAPE**: symmetrischer prozentualer Fehler.
- **Abdeckung 80 % / 95 %**: Anteil der echten Werte innerhalb des Unsicherheitsbands. Gut kalibriert heißt
  nahe 0,80 bzw. 0,95; deutlich darunter = Band zu schmal.

# Aufgabe

1. `summary`: Welches Modell hat den niedrigsten mittleren MASE, und um wie viel liegt es vor der
   saisonal-naiven Referenz? Wie viele Folds liefen?
2. `notes`: Stabilität über die Folds (schwankt der MASE stark?), Kalibrierung der Bänder, fehlgeschlagene
   Modelle mit Fehlergrund.

# Nicht tun

- Kein Modell auswählen — das macht Schritt 06 nach fester Regel.
- Unterschiede unter etwa 5 % im MASE nicht als klaren Vorsprung beschreiben.
