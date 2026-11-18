# Funktionen: Container-Import (`containerimport`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

7 Dateien, 112 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/containerimport.php`

_Aktionen: Modul Container-Import, Reiter EUDR – Herkunftsbetriebe mit Geolokalisierung, Sendungen, Risikoprofil und GeoJSON-Datei für das EU-Informationssystem (Oberfläche containerimport.intern; Funktionen in …_

- `eudr_leser(post)` – Mitarbeiter mit Modulzugang und dem Recht anzusehen (lesende Aktionen; $post = Aktion kommt als POST mit CSRF)
- `eudr_bearbeiter()` – Mitarbeiter mit Modulzugang und dem Recht zu bearbeiten (schreibende Aktionen)
- `eudr_sendung_holen(doc, id)` – Gespeicherte Sendung nach id (404) samt ihrer Stelle im Dokument

## `app/api/module/containerimport/eudr.php`

_Container-Import · EUDR (Verordnung (EU) 2023/1115, entwaldungsfreie Lieferketten)_

**Speicher**

- `eudr_liste(d)` – Inhalt eines Dokuments als ['rev', 'liste'] (fehlt es, leer)
- `eudr_fortschreiben(doc)` – Dokument für das Schreiben fortschreiben: Revision erhöhen, Zeitstempel setzen
- `eudr_betriebe()` – Dokument der Herkunftsbetriebe
- `eudr_sendungen()` – Dokument der Sendungen
- `eudr_betriebe_schreiben(doc)` – Herkunftsbetriebe speichern
- `eudr_sendungen_schreiben(doc)` – Sendungen speichern
- `eudr_id(praefix)` – Neue Kennung mit Vorsilbe (b = Betrieb, s = Sendung)
- `eudr_wer(me)` – Stempel „wann und von wem“
- `eudr_stelle(liste, id)` – Stelle eines Eintrags in einer Liste nach seiner id (null = nicht vorhanden)
- `eudr_rev_pruefen(eingabe, alt, was)` – Stand, den der Bearbeiter gesehen hat, mit dem gespeicherten vergleichen (409, wenn inzwischen jemand gespeichert hat)

**Prüfen der Eingaben**

- `eudr_text(v, max, was, pflicht)` – Text ohne Steuerzeichen, höchstens $max Zeichen; $pflicht = darf nicht leer sein
- `eudr_datum(v, was, bisHeute)` – Datum JJJJ-MM-TT oder leer; $bisHeute = ein Datum in der Zukunft ist ein Eingabefehler
- `eudr_wahl(v, erlaubt, was, standard)` – Einer der erlaubten Werte; leer ergibt den Standard, wenn einer genannt ist
- `eudr_zahl(v, was)` – Zahl ab 0 oder null (leer); Text auch in deutscher Schreibweise („1.234,5“)
- `eudr_land(v)` – Zweistelliger Ländercode in Großbuchstaben

**Betriebe (Produktionsorte)**

- `eudr_geometrie_aus(b)` – Geometrie eines Betriebs aus der Eingabe: fertige GeoJSON-Geometrie in WGS84 oder Punktliste mit Bezugssystem („utm“ mit Zone und Halbkugel bzw. „wgs84“).
- `eudr_betrieb_pruefen(b, alt)` – Felder eines Betriebs aus der Eingabe prüfen (ohne id, rev, Zeitstempel und Gegenprüfungen).
- `eudr_original_vermerken(liste, ablage, me)` – An allen Betrieben, die aus der Datei mit dieser Prüfsumme stammen, vermerken, wo ihr Original im QM-System liegt ($ablage = Antwort von qs_eingang_hochladen).
- `eudr_geo_kennung(g)` – Kennung der Geometrie zum Wiedererkennen derselben Fläche
- `eudr_bekannt_tabelle(liste)` – Nachschlagetabelle der gespeicherten Betriebe zum Wiedererkennen (einmal je Anfrage): Land und Kennung bzw. Umriss → Betrieb
- `eudr_bekannt(neu, tabelle)` – Gespeicherter Betrieb, der zu einem eingelesenen passt: gleiche Kennung im selben Land, sonst dieselbe Geometrie
- `eudr_pruefungen_aktuell(b)` – Jüngste Gegenprüfung je Portal (nur diese zählt im Risikoprofil)
- `eudr_betrieb_sicht(b)` – Betrieb für die Oberfläche: gespeicherte Felder plus abgeleitete Kennzahlen und Befunde. stand: „fehler“ (Geolokalisierung so nicht einreichbar), „hinweis“ …
- `eudr_betrieb_bewertung(b, geoStand)` – Bewertung eines Betriebs je Thema (ok \| offen \| kritisch): das Risikoprofil der Sendung und die Farbe auf der Karte lesen sie hier ab. Was erst mit der …
- `eudr_pruefung_pruefen(b, me)` – Eine Gegenprüfung aus der Eingabe prüfen

**Dateien einlesen**

- `eudr_eigenschaft(eigenschaften, name, falsch)` – Eigenschaft eines GeoJSON-Features lesen.
- `eudr_geojson_lesen(text, datei)` – Lieferanten-GeoJSON lesen: je Feature ein Produktionsort (MultiPoint wird in Punkte zerlegt).
- `eudr_datei_pruefen(d, bekannt)` – Eine hochgeladene Datei prüfen, ohne zu speichern: Lieferanten-GeoJSON („text“) oder ein vom Browser gelesener Produktionsort („ort“: Bericht oder eingefügte …

**Sendungen**

- `eudr_sendung_pruefen(b, betriebIds)` – Felder einer Sendung aus der Eingabe prüfen (ohne id, rev, Zeitstempel und Abschluss)
- `eudr_dds_pruefen(dds)` – Angaben zur Sorgfaltserklärung im EU-Informationssystem (auch nach dem Abschluss änderbar)

**Risikoprofil**

- `eudr_namen(betriebe, bedingung)` – Namen der Betriebe, auf die eine Bedingung zutrifft
- `eudr_bewertet(betriebe, thema, stufe)` – Namen der Betriebe mit einer bestimmten Bewertung in einem Thema (eudr_betrieb_bewertung)
- `eudr_kriterium(id, titel, stand, text, betriebe)` – Ein Kriterium des Profils: stand ok \| hinweis \| offen \| kritisch
- `eudr_kriterien()` – Kriterien des Risikoprofils (Art. 10 der Verordnung) als Tabelle: jede Zeile bewertet die Sendung mit ihren Betrieben ($bs = Sichten der Betriebe) und …
- `eudr_profil(s, bs)` – Risikoprofil einer Sendung: alle Kriterien, Gesamtstand (das schlechteste Kriterium) und ein Vorschlag.
- `eudr_sendung_betriebe(s, sichten)` – Betriebe einer Sendung als Sichten: nach dem Abschluss der Schnappschuss, sonst der aktuelle Stand
- `eudr_abschluss(s, eingabe, sichten, me)` – Abschluss einer Bewertung aus der Eingabe: Ergebnis, Begründung, Bearbeiter und Schnappschuss von Profil und Betrieben (GR-106).
- `eudr_sendung_sicht(s, betriebe)` – Sendung für die Oberfläche: mit Profil – bei abgeschlossener Bewertung dem gespeicherten Schnappschuss; frühere Abschlüsse nur mit Ergebnis, Begründung und …

**GeoJSON für das EU-Informationssystem**

- `eudr_geojson(bs)` – FeatureCollection aus Betrieb-Sichten: Eigenschaften in der vorgeschriebenen Schreibweise, Fläche als Zahl.

**Stand für die Oberfläche**

- `eudr_stand()` – Alle Betriebe und Sendungen mit abgeleiteten Werten, dazu Länder und Portale

## `app/api/module/containerimport/geometrie.php`

_Container-Import · Geometrie der Produktionsorte (EUDR): reine Rechenfunktionen ohne Speicherzugriff._

- `geo_utm_nach_wgs84(rechts, hoch, zone, sued)` – UTM (Rechtswert, Hochwert in Metern, Zone 1–60, Südhalbkugel ja/nein) → [Längengrad, Breitengrad] in WGS84
- `geo_ring_ha(ring)` – Fläche eines Rings in Hektar auf dem WGS84-Ellipsoid, mit Vorzeichen: positiv = gegen den Uhrzeigersinn.
- `geo_ring_eben(ring)` – Fläche eines Rings in der Ebene (Quadratgrad, mit Vorzeichen) – nur zum Erkennen entarteter Umrisse
- `geo_schnitt(p, q, r, s)` – Schneiden sich die Strecken p–q und r–s echt (nicht nur an einem gemeinsamen Endpunkt)?
- `geo_selbstschnitt(ring)` – Erste Selbstüberschneidung eines geschlossenen Rings als [Kante i, Kante j] (Nummern ab 1) oder null.
- `geo_dorn(ring)` – Kleinster Innenwinkel an einer Ecke unter GEO_DORN_GRAD: Nummer des Punktes (ab 0) oder null
- `geo_position(v)` – Ist der Wert eine Position [Längengrad, Breitengrad] aus zwei Zahlen in vernünftiger Größe?
- `geo_ring_normal(ring)` – Ring normalisieren: auf 6 Stellen runden, aufeinanderfolgende Doppelte entfernen, schließen, gegen den Uhrzeigersinn drehen.
- `geo_lesen(g)` – Geometrie aus fremder Eingabe lesen und normalisieren.
- `geo_polygone(g)` – Polygone einer gespeicherten Geometrie als Liste von Ringlisten (Point: leer)
- `geo_kennzahlen(g)` – Kennzahlen einer normalisierten Geometrie: Fläche in Hektar (Point: null), Mittelpunkt, Rahmen, Zahl der Punkte
- `geo_pruefen(g)` – Geometrie nach den Regeln des EU-Informationssystems prüfen.
- `geo_punktzahl(g)` – Zahl der Punkte einer Geometrie (für die Obergrenzen je Anfrage und im Speicher)

## `app/module/containerimport/containerimport.js`

_STAFL-Plattform · Modul Container-Import, Reiter EUDR – Hilfen und Kontrollen zur EU-Verordnung über entwaldungsfreie Lieferketten (Auftrag des Inhabers 18.11.2026; Gestaltung „C2“)._

**Aufruf der API: wirft nie, liefert { status, data }**

- `api(action, body, query)`
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`
- `uebernehmen(r, fallback)` – Antwort einer speichernden Aktion: neuen Stand übernehmen. false = Fehler (Meldung gezeigt)

**Formate und Bezeichnungen**

**Bausteine für Fenster und Formulare**

- `feld(label, name, wert, o)`
- `werte(form)` – Werte aller benannten Felder eines Formulars als Objekt (Kontrollkästchen mit gleichem Namen als Liste)
- `oeffnen(dlg)`

**Seite**

- `zeichnen()`
- `sendungenSicht()`
- `betriebeSicht()`
- `karteSicht()`

**Fenster „Herkunftsbetrieb“**

- `betriebOeffnen(id)`
- `betriebAusFenster(b, w)` – Felder des Fensters als Betrieb für den Server
- `betriebSpeichern(zusatz)`
- `pruefungEintragen()`

**Fenster „Sendung“**

- `sendungOeffnen(id)`
- `sendungAusFenster()`
- `sendungSpeichern(zusatz)`
- `abschlussOeffnen(id, wiederOeffnen)` – Fenster „Bewertung abschließen“ bzw. „wieder öffnen“
- `abschlussSenden()`

**GeoJSON-Datei und Druck**

- `exportieren(query)`
- `drucken(id)`

**Fenster „Unterlagen einlesen“**

- `lesenOeffnen(sendungId)`
- `pdfSeiten(bytes)` – Textstücke einer PDF-Datei mit ihrer Lage, je Seite (pdf.js vom eigenen Server, erst beim ersten Bericht geladen)
- `dateiVorbereiten(datei, gemeinsam)` – Eine gewählte Datei in die Form bringen, die der Server prüft; { fehler } bei Dateien, die sich nicht lesen lassen
- `eingefuegt(w, gemeinsam)`
- `lesenPruefen()`
- `lesenZahl()`
- `lesenUebernehmen()`
- `base64(bytes)` – Bytes als Base64 (in Stücken, damit lange Dateien den Aufrufstapel nicht sprengen)
- `originalAblegen(datei, sha256, lieferant)` – Eine Originaldatei in Teilen an den Server geben, der sie im Eingang des QM-Systems ablegt. '' oder die Fehlermeldung.

**Laden und Ereignisse**

- `laden(still)`
- `themaKnopf()`

## `app/module/containerimport/eudr-bericht.js`

_STAFL-Plattform · Container-Import · EUDR – Entwaldungsberichte der Lieferanten lesen (reine Funktionen, kein DOM)._

- `zeilen(stuecke)` – Zeilen einer Seite, von oben nach unten: je Zeile die Läufe von links nach rechts. pdf.js liefert Text oft in Stücken („500000“, „.“, „00“) – Stücke ohne …
- `punkte(text)` – Koordinatenpaare aus Text: „p0 500000.00 7400000.00, p1 …“, „p0,500000.00,7400000.00,p1,…“ oder je Zeile „x y“. Bei nummerierten Listen müssen die Nummern …
- `konform(text)` – „Compliant“ / „Non-compliant“ und die Zahl danach aus dem Text eines Abschnitts.
- `stammdaten(zeilenListe)` – Werte der Tabelle „Farm information summary“: jedes Textstück unter den Überschriften gehört zur nächstgelegenen Spalte
- `lesen(seiten)` – Bericht lesen. null, wenn die Datei keine Koordinatenliste enthält (dann ist es kein solcher Bericht); { fehler } wenn sie eine enthält, die sich nicht …

## `app/module/containerimport/eudr-karte.js`

_STAFL-Plattform · Container-Import · EUDR – Karte der Herkunftsbetriebe, ohne fremde Kartendienste._

- `ausschnitt(betriebe, rand, minGrad, seite)` – Rahmen [x, y, Breite, Höhe] in Karteneinheiten um die Betriebe: Rand anteilig, Mindestbreite in Grad
- `rund(grenze)` – „Runde“ Strecke für den Maßstab: 1, 2 oder 5 mal Zehnerpotenz, höchstens grenze Meter
- `svg(box, inhalt, klasse)`
- `groessen(el)` – Größen, die mit dem Zoom mitgehen müssen (Marken, Eckpunkte), aus der aktuellen Breite des Ausschnitts setzen
- `bedienung(el, start, beiKlick)` – Zoomen (Rad, Knöpfe) und Verschieben (Ziehen) über die viewBox; ein Antippen ohne Ziehen auf einem Betrieb ruft beiKlick – das Ziel wird beim Drücken …
- `detail(el, opt, betriebe)` – Detailkarte mit Straßen und Orten: Flächen in der Farbe ihrer Ampel, in der Übersicht zusätzlich eine Marke je Betrieb (zusammengefasste Marken grau – eine …
- `zeichnen(el, opt)`

## `tests/e2e/test_containerimport.py`

_Modul Container-Import, Reiter EUDR (app/module/containerimport/, Oberfläche containerimport.intern, Auftrag des Inhabers 18.11.2026)_

- `check(n, c, i)`
- `utm_nach_wgs84(rechts, hoch, zone, sued)` – Unabhängige Gegenrechnung (Krüger-Reihen nach Karney) – der Server rechnet mit einer anderen Formel.
- `pdf_bauen(seiten)` – Einfache PDF-Datei aus Textstücken je Seite [(x, y, Text), …] – für den erfundenen Bericht.

**Register und Testfreigabe**

- `login(user)`

**Rechte**

**Dateien prüfen (ohne zu speichern)**

**Sendung und Betriebe speichern**

- `stand(c)`
- `profil(s)`
- `betrieb(name)`

**Eigene Gegenprüfung**

**Abschluss**

**Oberfläche**

- `seite(user, vp, schema)`
- `kartendatei(route)`

**Originale im QM-System (Schnittstelle qs_eingang_hochladen)**

- `original(c, name, inhalt, lieferant, teil)` – Datei in Teilen an containerimport_eudr_original geben; Antwort des letzten Aufrufs.
