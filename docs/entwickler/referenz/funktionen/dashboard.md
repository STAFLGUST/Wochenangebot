# Funktionen: Dashboard (`dashboard`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

2 Dateien, 24 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `dashboard/dashboard.js`

_STAFL-Plattform · Dashboard (Startseite, Gestaltung „C2“) Kacheln und Seitenleiste kommen ausschließlich aus dem Modulregister (Aktion module_status, regeln/module.toml) – keine fest programmierte Liste._

- `api(action, body)`
- `status(m, alle)`
- `kachel(m, alle)` – Eine kompakte Kachel: Symbol und Name, keine Unterzeile.
- `render(module)`
- `wortGebrochen(el)` – true, wenn ein Wort über zwei Zeilen läuft – auch am Bindestrich („Container-Import“), den der Browser sonst trennt
- `namenEinpassen()`
- `einpassen()`
- `gruss(stunde)` – Begrüßung nach Tageszeit (Uhr des Geräts) mit Vornamen und Datum, z. B. „Guten Tag, Erika“ · „Donnerstag, 22. Oktober“
- `vorname(name)` – Vorname = erster Namensteil ohne Titel („Dr.
- `begruessung(name)`
- `fehler(text)`
- `zeigeAnmeldung(ziel)`
- `abmelden()`
- `laden()`
- `notfallHinweis(n)` – Notfallmodus (Modul Sicherheit): Hinweis über den Kacheln – Einzelheiten nur für Administratoren und Berechtigte
- `themaKnopf()`
- `darstellungKnopf()` – Einfache Darstellung (theme.js): an/aus, gespeichert am Konto; Hinweis unter der Begrüßung, solange sie an ist

## `tests/e2e/test_dashboard.py`

_Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6) im gemeinsamen Rahmen „C2“ (app/assets/rahmen.css, rahmen.js)_

- `check(n, c, i)`
- `anmelden(br, user, pw, ip, breite, dunkel, uhr)`
- `kacheln(pg)`
- `leiste(pg)`
- `kontrast_ok(pg, name)`
- `bilder(pg)`
- `lange_namen(route)`
