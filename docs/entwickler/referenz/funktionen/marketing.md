# Funktionen: Marketing (`marketing`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

4 Dateien, 76 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/marketing.php`

_Aktionen: Marketing · Redaktionsplan (Oberfläche marketing.intern, Daten und Regeln in app/api/module/marketing/marketing.php) Rechte (GR-103): marketing.sehen – Übersicht, Kalender, Board, Liste, Kampagnen ansehen, …_

- `mkt_index(doc, id)` – Index eines Beitrags in der Liste oder 404

## `app/api/module/marketing/marketing.php`

_Marketing · Redaktionsplan_

**Grundwerte der Einstellungen**

- `mkt_grundwerte()`

**Laden und Schreiben**

- `mkt_beitraege_doc()`
- `mkt_kampagnen_doc()`
- `mkt_einstellungen()` – Einstellungen: gespeicherte Listen, fehlende Listen aus den Grundwerten
- `mkt_schreiben(name, doc)`
- `mkt_id(praefix)`
- `mkt_ids(liste)`
- `mkt_team()` – Mitarbeiter, die Beiträge bearbeiten dürfen (wählbar als Verantwortliche) – Schnittstelle der Plattform (users_load)

**Prüfen der Eingaben**

- `mkt_text(v, max, was)`
- `mkt_datum(v, was)`
- `mkt_termin(v, was)` – Veröffentlichung: Datum, optional mit Uhrzeit (Ortszeit), „JJJJ-MM-TT“ oder „JJJJ-MM-TTTHH:MM“
- `mkt_url(v, was)`
- `mkt_wahl(v, erlaubt, was, leer)`
- `mkt_zahl(v, was)`
- `mkt_farbe(v, was)`

**Beitrag**

- `mkt_beitrag_leer()` – Grundform eines Beitrags (für neue Beiträge und zum Auffüllen älterer Fassungen beim Lesen)
- `mkt_felder_pruefen(f, einst, kampagnen, team)` – Felder einer Anfrage prüfen – nur die mitgeschickten (Teiländerung, z. B. Termin beim Verschieben im Kalender)
- `mkt_verlauf(e, me, was)` – Verlaufseintrag (Name als Schnappschuss, GR-106)
- `mkt_status_setzen(e, neu, me)` – Statuswechsel nach den Regeln des Ablaufs.
- `mkt_beitrag_aus(e, teamNamen)` – Beitrag für die Oberfläche: Grundform aufgefüllt, Name der/des Verantwortlichen
- `mkt_team_namen()`

**Einstellungen und Kampagnen**

- `mkt_liste_pruefen(v, was, mitFarbe, kanal, alt)` – Eine Einstellungsliste prüfen; vorhandene Kennungen bleiben, neue entstehen aus dem Namen.
- `mkt_kampagne_pruefen(b, alt, einst)`

**Liste als CSV (Excel)**

- `mkt_csv(liste, einst, kampagnen)`

## `app/module/marketing/marketing.js`

_STAFL-Plattform · Marketing · Redaktionsplan Social-Media-Inhalte planen, produzieren, freigeben und veröffentlichen_

- `api(action, body, query)`
- `toast(text, fehler)`
- `frage(titel, text, ja)` – Rückfrage im eigenen Dialog (kein Browser-Dialog)

**Datum**

**Nachschlagen**

**Filter**

- `passt(e, ohneStatus)`
- `filterLeiste(mitStatus)`

**Kopf, Anmeldung, Thema**

- `fehler(text)`
- `zeigeAnmeldung(ziel)`
- `themaKnopf()`

**Reiter**

- `zeigeTab(tab)`
- `zeichne(nurInhalt)` – nurInhalt: beim Tippen in der Suche nur die Ergebnisse neu zeichnen, damit das Suchfeld den Fokus behält

**Daten**

- `setzeDaten(d)`
- `ersetze(e)`
- `speichere(e, felder, status)` – Teiländerung ohne Dialog (Kalender, Board): Konflikt → neue Fassung übernehmen und melden

**Bausteine**

- `kanalChips(e)`
- `karte(e, kompakt)`
- `zeile(e, wann)`
- `kpi(titel, w, zusatz, cls, ziel)`
- `balken(paare)`

**Übersicht**

- `uebersicht()`

**Kalender**

- `kalender(nurInhalt)`
- `tagesEintraege(tag)`
- `chip(e)`
- `terminChip([…])`
- `kalenderInhalt()`
- `agenda()` – Handy: Tagesliste des Monats bzw. der Woche statt Raster

**Ziehen und Ablegen (Kalender: Termin, Board: Status)**

**Board**

- `board(nurInhalt)`
- `boardInhalt()`

**Liste**

- `liste(nurInhalt)`
- `listeInhalt()`

**Kampagnen**

- `kampagnen()`
- `kampagneDialog(k)`

**Einstellungen**

- `einstellungen()`
- `einstZeile(art, x, farbe, istKanal, n)`

**Beitrag (Dialog)**

- `zeichneCheck()`
- `zeichneLinks()`
- `zeichneZaehler()`
- `zeichneVeroeff(e)`
- `zeichneAblauf(e)`
- `zeichneKommentare(e)`
- `fuelle(e, vorgabe)`
- `vorgabeBeitrag()`
- `sammle()`
- `oeffne(id, vorgabe)`
- `speichern(status)`
- `schliessen()`
- `kommentieren()`

**Klicks in den Ansichten**

- `exportieren()`

**Start**

- `laden()`

## `tests/e2e/test_marketing.py`

_Marketing · Redaktionsplan (Modul marketing, Oberfläche marketing.intern unter /module/marketing/)._

- `check(n, c, i)`
- `dokument(name)`
- `anmelden(user, pw, ip, breite, thema, hoehe)`
