# 10 · Konventionen

Was im ganzen Repository gleich gemacht wird. Verbindliche Regeln stehen in [`AGENTS.md`](../../AGENTS.md); hier die
Gewohnheiten, die den Code lesbar und sicher halten.

## Sprache

- **Deutsch** für Bezeichner der Fachlogik und neuen Code (`kunden_wartung`, `rolle_save`, `modul_zugang_frei`),
  Kommentare, Fehlermeldungen, Oberflächentexte, Dokumentation, Commit-Nachrichten und Pull-Request-Texte. Ältere
  Teile sind englisch benannt (`respond`, `store_read`, `user_perms`) – bestehende Namen bleiben, neue Namen sind deutsch.
- Oberflächentexte in Alltagssprache, Anrede „Sie“ (Mitarbeiter- und Kundenseiten), deutsche Anführungszeichen
  „…“, Gedankenstrich –, Datum `TT.MM.JJJJ`, Zahlen mit Komma.
- Fehlermeldungen sagen, was zu tun ist („Bitte erneut anmelden.“, „Dafür fehlt Ihnen die Berechtigung. Bitte an
  einen Administrator wenden.“).

## Namen

| Was | Muster | Beispiel |
| --- | --- | --- |
| Rechte | `<modul>.<recht>` (GR-103), Modulzugang `<modul>.zugang` | `crm.bearbeiten` |
| Aktionen | Kleinbuchstaben mit `_`, Präfix des Moduls bei neuen Modulen | `hr_antrag`, `crm_export` |
| Speicher-Dokumente | Kleinbuchstaben, `-` | `hr-abwesenheiten`, `crm-kunden` |
| Branches | `plattform/<thema>` (Kern), `agent/<modul>/<thema>` (Fachmodul) | `plattform/eigene-rollen` |
| Testgruppen / Testdateien | `<gruppe>` / `tests/e2e/test_<gruppe>.py` | `rollen` |
| IDs im HTML | kurz, mit Bereichspräfix | `#vt-rollen`, `#view-rollen`, `#hr-zurueck` |
| CSS-Klassen | Bereichspräfix je Seite (`db-`, `hr-`, `crm-`, `rl-`); gemeinsame Bausteine `stafl-` | `.stafl-zurueck` |

## Code-Stil

**PHP:** `declare(strict_types=1);`, Schutzzeile `if (!defined('WA_API')) { http_response_code(404); exit; }` in
jeder eingebundenen Datei, Funktionen statt Klassen, Eingaben immer prüfen (`s()`, Typprüfungen), Antworten nur über
`respond()`/`fail()`, Schreiben nur in `with_lock`. Keine Ausgabe außer JSON (bzw. Dateien wie PDF/CSV mit passenden
Kopfzeilen).

**JavaScript:** ohne Framework, ohne Build, `'use strict'` in einer selbst aufrufenden Funktion je Datei, keine
Inline-Skripte und keine `on…`-Attribute (Content-Security-Policy `script-src 'self'`). Texte vom Server immer mit
`esc()` einsetzen. Gemeinsames im Eingabebereich über `window.WA`.

**CSS:** Farben über Variablen (hell/dunkel über `prefers-color-scheme` und `data-theme`), Mobil ab 390 px Breite
prüfen, Tippflächen ≥ 36 px, Kontrast ≥ 4,5 : 1. Gemeinsame Bausteine in `app/assets/app.css`
([06 Oberflächen](06-oberflaechen.md)).

**Python (Werkzeuge, Tests):** nur Standardbibliothek in `werkzeuge/` (läuft auch auf dem Server), Tests dürfen
`tests/requirements.txt` nutzen.

**Shell:** `set -euo pipefail`, shellcheck-sauber (die CI prüft), keine Geheimnisse in Ausgaben.

## Kommentare und Dokumentation

- **Jede Datei beginnt mit einem Kopfkommentar**, dessen erster Satz sagt, was sie tut – daraus entsteht die
  [Dateikarte](referenz/dateien.md); die CI lehnt Dateien ohne ab (`werkzeuge/doku.py pruefen`).
- Kommentare erklären das **Warum** (Regel, Sicherheitsgrund, Rückfallverhalten), Regeln mit Kennung (`GR-103`).
- **Dokumentationspflicht:** Jede Änderung bringt ihre Dokumentation im selben Pull Request mit – Referenz neu
  erzeugen (`python3 werkzeuge/doku.py erzeugen`), betroffene Kapitel in `docs/entwickler/`, `docs/architektur.md`
  und `LIESMICH.md` anpassen (Definition of Done).

## Sicherheit (Kurzfassung)

- Jede Aktion prüft selbst Anmeldung und Recht; schreibende Aktionen zusätzlich CSRF (`require_…(…, true)`).
- Kein Vertrauen in Werte aus dem Browser für Preise, Rechte, Rollen, IDs anderer Nutzer (GR-004, GR-103).
- Öffentliche Ausgaben ohne Mengen, Chargen, MHD, Einkaufspreise und Kundenpreise (GR-001, GR-002, GR-008).
- Passwörter nur als Hash; Geheimnisse nie in Antworten, Protokoll oder Repository (GR-007).
- Cookies nur `__Host-`, keine Freigaben für fremde Herkunft, Aktionen nur auf ihrem Host (GR-108, GR-109).
- Protokoll (`audit`) ohne Kontaktdaten und Freitexte von Kunden.
Ausführlich: [04 Anmeldung und Rechte](04-anmeldung-rechte.md).

## Commits und Pull Requests

- Ein Branch = ein Thema = ein Pull Request; koordinationspflichtige Bereiche im eigenen Pull Request.
- Commit-Nachricht: erste Zeile kurz, was sich ändert; darunter warum.
- Pull-Request-Text nach Vorlage in Alltagssprache, mit „geplant · implementiert · getestet · gemergt · produktiv“.
- Merge und Release macht ausschließlich der Inhaber.

Stand: 2026-10-24
