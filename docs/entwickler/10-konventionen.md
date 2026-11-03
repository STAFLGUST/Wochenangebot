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

## Zahlen und Einheiten (Vorgabe des Inhabers 02.11.2026: „überall gleich“)

Alle Seiten formatieren über **`window.STAFL_FORMAT`** aus `app/assets/format.js` (lädt jede Seite direkt nach
`theme.js`); keine eigenen Formatierer mehr in Modulen. Geprüft in der Testgruppe `einheit`.

| Größe | Funktion | Ausgabe |
| --- | --- | --- |
| Betrag | `euro(v)` | `1.234,50 €` – immer 2 Nachkommastellen |
| Betrag in einer Kennzahl-Kachel | `euroKachel(v)` | wie `euro`, erst ab 100 Mio. kurz: `123,46 Mio. €` (voller Wert im Tooltip) |
| Preis je kg | `euroKg(v)` | `12,35 €/kg` – immer 2 Nachkommastellen, wie Bestellwunsch, E-Mail und Abrechnung (4,125 → 4,13) |
| Menge | `kg(v)` | `1.782,50 kg` – immer kg (nie „t“), 2 Nachkommastellen wie Bestand und PDF |
| Menge als Summe (Auswertung, Kachel) | `kgSumme(v)` | `1.783 kg` ab 100 kg ganz, darunter bis 1 Nachkommastelle |
| Anteil | `prozent(anteil)` | `12,3 %` (Eingabe als Bruch 0,123) |
| Veränderung | `veraenderung(anteil)`, `pp(anteil)`, `differenz(v, einheit)` | `+12,3 %`, `−5,0 %`, `±0,0 %`; `+1,2 Pp`; `+0,50 €/kg` |
| Datum | `datum(d)`, `datumZeit(d)`, `kw(w, j)` | `02.11.2026`, `02.11.2026, 14:05`, `KW 45/2026` (Diagrammachse kurz `KW 45`) |

- Minus als echtes Minuszeichen `−`, zwischen Zahl und Einheit ein Leerzeichen; fehlender Wert `—`, Null ist ein Wert.
- Mengen auch in E-Mails, PDFs, Bestellleiste und „Meine Bestellwünsche“ mit 2 Stellen; nur in Eingabefeldern ohne
  Endnullen („2,5“). Grenzen wie „unter 200 kg“ und Kalendertage ganz. Stunden `128:00 Std.` (in Tabellen mit Spaltenkopf
  ohne „Std.“). Rundung kaufmännisch wie der Server (`format.js` rundet 12,345 → 12,35).
- Zeitstempel aus der API (UTC) nie per `slice(0, 10)` zum Datum kürzen – `datum(t)` rechnet in deutsche Ortszeit um.
- **Tabellen:** Die Einheit steht am Wert, nicht im Spaltenkopf („Menge“, „Preis“, „Summe“). Ausnahme: Eingabespalten und
  dichte Bearbeitungstabellen (Editor) – dort steht sie im Kopf („Preis €/kg“, „Menge kg“) und nicht zusätzlich in der Zelle.
- Beschriftungen ausgeschrieben: „Menge“ statt „Kg“, „auf Anfrage“ (nur die gedruckte Angebotsliste kürzt „a. Anfr.“).
- **CSV und Excel** bleiben maschinenlesbar: Zahl ohne Tausenderpunkt und ohne Einheit, die Einheit im Spaltenkopf.

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
- **Funktionen:** Kommentar direkt über die Funktion (ohne Leerzeile; Python: Docstring), erster Satz = was sie tut bzw.
  liefert. Abschnitte großer Dateien als eigene Zeile `/* ---------- Name ---------- */` (Python: `# ──── Name ────`).
  Beides ergibt die [Funktionsübersicht je Modul](referenz/funktionen/README.md) – die Karte, mit der man eine große Datei
  versteht, ohne sie ganz zu lesen.
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
