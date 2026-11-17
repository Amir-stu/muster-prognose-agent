---
step: 09_handover
title: Daten und Prognoseziel übergeben
kind: human
---
# Übergabe – kein Subagent

Ein Mensch übergibt neue Daten und/oder ein geändertes Prognoseziel. Danach beginnt eine neue Iteration bei
Schritt 01 in einem eigenen Ordner (`iter_02`, `iter_03`, …); frühere Iterationen bleiben unverändert.

## Zwei Wege hierher

| Von | Befehl |
|---|---|
| 03 (Daten reichen nicht) | `prognose handover <run_id> --data <neue-datei> [--horizon N] [--comment "..."]` |
| 08 (Anpassen) | `prognose review <run_id> --adjust "<text>" [--data <datei>] [--horizon N]` |

Die Übergabe landet in `09_handover.json` der alten Iteration. Ist `max_iterations` erreicht, endet der Lauf
mit `stopped_max_loops` statt einer neuen Iteration.
