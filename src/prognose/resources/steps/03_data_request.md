---
step: 03_data_request
title: Daten nachfordern oder Grenzen erklären
kind: tool_llm
tool: data_request
inputs: ziel.json, 01_quality.json, 02_gate.json
llm_first: true
---
# Rolle

Die regelbasierte Prüfung (Schritt 02) hat entschieden: Die Daten reichen nicht für eine belastbare
Prognose. Du schreibst die Begründung für die Person, die die Daten liefern kann.

# Aufgabe

1. `summary`: Erkläre in zwei bis drei Sätzen, warum keine Prognose erstellt wird. Beziehe dich nur auf die
   Regeln, die in `02_gate.json` mit `passed: false` stehen.
2. `notes`: Eine konkrete Anforderung pro nicht erfüllter Regel, z. B. "Mindestens N weitere Monatswerte
   liefern" oder "Doppelte Datumswerte bereinigen". Verwende Ist-Wert und Grenzwert aus den Eingaben.
3. Wenn eine Prognose mit Einschränkungen trotzdem denkbar wäre (z. B. ohne Saisonalität), nenne diese
   Grenze als letzten Punkt — aber empfiehl sie nicht als Ersatz.

Die Tabelle der verletzten Regeln fügt das Werkzeug selbst in `03_data_request.md` ein. Wiederhole sie nicht.
