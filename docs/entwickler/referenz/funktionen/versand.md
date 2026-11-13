# Funktionen: Versand (`versand`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

4 Dateien, 31 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/versand.php`

_Aktionen: Modul Versand – Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden (Oberfläche versand.intern; Funktionen in app/api/module/versand/versand.php, Daten und Regeln beim Angebot: …_

- `vs_art(v)` – Art der Sendung aus der Anfrage: 'woche' oder 'sonderposten' (sonst 422)
- `vs_angebot(v)` – Angebot der Sonderposten aus der Anfrage (404, wenn es das Angebot nicht gibt)

## `app/api/module/versand/versand.php`

_Modul Versand: Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden (Oberfläche versand.intern, Seite app/module/versand/, Aktionen app/api/aktionen/versand.php; Auftrag des Inhabers …_

- `vs_rechte(me)` – Was darf dieser Mitarbeiter im Modul?
- `vs_woche(week, year)` – Angebotswoche als Text-Bausteine (Montag bis Sonntag)
- `vs_stand(me)` – Stand für die Seite: Entwurf und veröffentlichtes Angebot, Zahl der Änderungen (gesamt, je Angebot, je Art – ohne Zeilen), Angebote der Woche mit Kunden und …
- `vs_verlauf(monate)` – Verlauf: Veröffentlichungen und Sendungen aus dem Protokoll des Plattformkerns (Vorgänge „publish“ und „mail“ mit den Schlüsseln …\|woche bzw. …\|restposten).
- `versand_startseite(me)` – Offene Punkte für „Heute für Sie“ auf dem Dashboard (lib/startseite.php): unveröffentlichte Änderungen und ein noch nicht versendetes Wochenangebot – jeweils …

## `app/module/versand/versand.js`

_STAFL-Plattform · Modul Versand – Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden (Auftrag des Inhabers 13.11.2026; Gestaltung „C2“, Variante A: zwei Schritte oben, Angebote zur …_

**Aufruf der API: wirft nie, liefert { status, data }**

- `api(action, body, query)`
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`

**Formate**

- `zeit(t)` – „heute, 10:42 Uhr“ bzw. „Do 05.11.2026, 14:10 Uhr“
- `wochenText(w)`

**Darstellung**

- `themaKnopf()`

**Seite**

- `schritt(o)`
- `zeichnen()`
- `verlaufZeichnen()`
- `verlaufLaden()`
- `laden(still)`

**Fenster „Veröffentlichen“**

- `pubZeichnen(filter)`
- `pubOeffnen()`
- `veroeffentlichen(knopf)`

**Fenster „Senden“ (Wochenangebot bzw. Sonderposten eines Angebots)**

- `sendZeichnen()`
- `sendZahl()`
- `sendOeffnen(art, angebot, merk)`
- `vorschau()`
- `senden()`

## `tests/e2e/test_versand.py`

_Modul Versand (app/module/versand/, Oberfläche versand.intern, Auftrag des Inhabers 13.11.2026)_

- `check(n, c, i)`

**Register**

**Mitarbeiter, Kunden, Angebote**

- `login(user)`
- `entwurf()`

**Rechte: Stand und Liste**

**Veröffentlichen**

**Empfänger, Vorschau, Senden: Wochenangebot**

**Sonderposten**

**Verlauf**

**Startseite**

**Wartung der Oberfläche**

**Oberfläche**

- `seite(user, password, pfad, vp, schema)`
