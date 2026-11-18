---
step: 07_visualize
title: Ergebnisse mit Unsicherheitsband visualisieren
kind: tool_llm
tool: visualize
inputs: ziel.json, 04_patterns.json, 06_forecast.json, 07_visualize.json
---
# Rolle

Das Werkzeug `visualize` hat `07_chart.png` gezeichnet: Historie (dunkelgrau), Prognose (blau), 80- und
95-%-Band (blau, hell), Auffälligkeiten (orange Punkte), senkrechte Linie am Ende der Historie.

# Aufgabe

Schreibe die Bildunterschrift für eine Person, die die Prognose prüfen und freigeben soll.

1. `summary`: Was die Grafik zeigt, in zwei Sätzen — Verlauf der Prognose und wie breit das Band am Ende
   des Horizonts ist.
2. `notes`: Höchstens drei Punkte, worauf die prüfende Person achten sollte (z. B. Band wird stark breiter,
   Auffälligkeit kurz vor Prognosebeginn, Prognose setzt eine Saisonspitze fort).

# Nicht tun

- Nichts beschreiben, was nicht aus den Eingaben folgt (du siehst das Bild nicht, nur seine Daten).
