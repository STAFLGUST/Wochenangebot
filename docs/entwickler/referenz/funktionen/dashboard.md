# Funktionen: Dashboard (`dashboard`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

2 Dateien, 25 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `dashboard/dashboard.js`

_STAFL-Plattform · Dashboard Kacheln kommen ausschließlich aus dem Modulregister (Aktion module_status, regeln/module.toml) – keine fest programmierte Liste._

- `api(action, body)`
- `kachelZiel(k, alle, host)` – Ziel einer Kachel.
- `status(m, alle)`
- `kachel(m, alle, breit)` – Eine Kachel. breit: Bereich „Verwaltung & Daten“ (Symbol links, Text rechts; am Handy mit Pfeil statt grüner Pille)
- `render(module)`
- `wortGebrochen(el)` – true, wenn ein Wort über zwei Zeilen läuft – auch am Bindestrich („Container-Import“), den der Browser sonst trennt
- `namenEinpassen()`
- `bandLage(t)`
- `baenderLegen()`
- `einpassen()`
- `gruss(stunde)` – Begrüßung nach Tageszeit (Uhr des Geräts) und Datum, z. B. „Donnerstag, 22. Oktober“
- `begruessung()`
- `initialen(name)` – Initialen für den Nutzer-Chip: erste Buchstaben der ersten beiden Namensteile („Erika Editor“ → „EE“)
- `fehler(text)`
- `zeigeAnmeldung(ziel)`
- `laden()`
- `notfallHinweis(n)` – Notfallmodus (Modul Sicherheit): Hinweis über den Kacheln – Einzelheiten nur für Administratoren und Berechtigte
- `themaKnopf()`

## `tests/e2e/test_dashboard.py`

_Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6)_

- `check(n, c, i)`
- `anmelden(br, user, pw, ip, breite, dunkel, uhr)`
- `kacheln(pg)`
- `kontrast_ok(pg, name)`
- `bilder(pg)`
- `band_frei(pg, name)`
- `lange_namen(route)`
