# Funktionen: App (iOS/Android) (`mobile`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

2 Dateien, 8 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `tests/e2e/test_app_api.py`

_Schnittstelle für die App (docs/app-api.md)_

- `check(n, c)`
- `__init__(ip)`
- `call(action, data, client, send_sid)`
- `totp(secret)`

## `tests/e2e/test_app_web.py`

_App (mobile/) als Web-Build gegen den echten Testserver_

- `check(n, c)`
- `totp(secret)`
- `doc(name)`

**Web-Build der App neben die API der Testkopie legen (gleiche Herkunft wie in der App: /api/)**

**Gast**

**Kunde anmelden**

**Bestellwunsch**

**Wiederholung nach Verbindungsabbruch: keine Doppelbestellung**

- `antwort_verlieren(route)`
