---
step: 02_gate
title: Ausreichende Daten vorhanden
kind: gate
tool: sufficiency
inputs: 01_quality.json
---
# Regelbasierte Entscheidung – kein Subagent

Dieser Schritt ist absichtlich **kein** LLM-Schritt. Ob die Daten für eine Prognose reichen, entscheiden
feste Regeln aus `config.toml` (`[gate]`), damit dieselben Daten immer dieselbe Antwort bekommen.

| Regel | Bedingung |
|---|---|
| frequenz_erkannt | täglich, wöchentlich, monatlich oder quartalsweise erkennbar |
| beobachtungen | gültige Beobachtungen ≥ `min_observations` |
| saisonzyklen | volle Saisonzyklen ≥ `min_seasonal_cycles` |
| fehlanteil | fehlende Perioden und Werte ≤ `max_missing_share` |
| doppelte_daten | doppelte Datumswerte ≤ `max_duplicate_dates` |
| datum_ausserhalb_raster | Datumswerte außerhalb des Rasters ≤ `max_off_grid_dates` |
| streuung_vorhanden | Standardabweichung > 0 |

Ausgabe: `02_gate.json` mit `sufficient` und jeder Regel samt Ist-Wert und Grenzwert.

- **Ja** (alle Regeln erfüllt) → weiter mit 04.
- **Nein** → 03 schreibt eine Datenanforderung, der Lauf wartet auf neue Daten (`prognose handover`).

Grenzwerte ändert man in `config.toml`, nicht hier.
