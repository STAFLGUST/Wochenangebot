# Funktionen: Container-Import (`containerimport`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

22 Dateien, 230 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/containerimport.php`

_Aktionen: Modul Container-Import – Container (im Code „sendung“) mit Lieferant, Partie-, Akten- und Containernummer und Stand; Reiter EUDR – Farmer (im Code „betrieb“) mit Geolokalisierung, Risikoprofil und …_

- `eudr_leser(post)` – Mitarbeiter mit Modulzugang und dem Recht anzusehen (lesende Aktionen; $post = Aktion kommt als POST mit CSRF)
- `eudr_bearbeiter()` – Mitarbeiter mit Modulzugang und dem Recht zu bearbeiten (schreibende Aktionen)
- `eudr_sendung_holen(doc, id)` – Gespeicherte Sendung nach id (404) samt ihrer Stelle im Dokument

## `app/api/module/containerimport/eudr.php`

_Container-Import: Container (ein Einkauf bei einem Lieferanten, eine Partienummer) mit ihren Farmern und der Prüfung nach der EUDR (Verordnung (EU) 2023/1115, entwaldungsfreie Lieferketten)_

**Speicher**

- `eudr_liste(d)` – Inhalt eines Dokuments als ['rev', 'liste'] (fehlt es, leer)
- `eudr_fortschreiben(doc)` – Dokument für das Schreiben fortschreiben: Revision erhöhen, Zeitstempel setzen
- `eudr_betriebe()` – Dokument der Herkunftsbetriebe mit der eigenen Farmer-Nummer „nr“ = Stelle + 1. Annahme: die Liste wächst nur am Ende, nichts wird gelöscht oder umsortiert …
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
- `eudr_bekannt_tabelle(liste)` – Nachschlagetabelle der gespeicherten Betriebe zum Wiedererkennen (einmal je Anfrage): Nummer aus den Papieren bzw. Umriss → Betrieb
- `eudr_bekannt(neu, tabelle)` – Gespeicherter Betrieb, der zu einem eingelesenen passt: gleiche Nummer aus den Papieren im selben Land, sonst dieselbe Geometrie
- `eudr_pruefungen_aktuell(b)` – Jüngste Gegenprüfung je Portal (nur diese zählt im Risikoprofil)
- `eudr_betrieb_sicht(b)` – Betrieb für die Oberfläche: gespeicherte Felder plus abgeleitete Kennzahlen und Befunde. stand: „fehler“ (Geolokalisierung so nicht einreichbar), „hinweis“ …
- `eudr_betrieb_bewertung(b, geoStand)` – Bewertung eines Betriebs je Thema (ok \| offen \| kritisch): das Risikoprofil der Sendung und die Farbe auf der Karte lesen sie hier ab. Was erst mit der …
- `eudr_pruefung_pruefen(b, me)` – Eine Gegenprüfung aus der Eingabe prüfen

**Dateien einlesen**

- `eudr_eigenschaft(eigenschaften, name, falsch)` – Eigenschaft eines GeoJSON-Features lesen.
- `eudr_geojson_lesen(text, datei)` – Lieferanten-GeoJSON lesen: je Feature ein Produktionsort (MultiPoint wird in Punkte zerlegt).
- `eudr_datei_pruefen(d, bekannt)` – Eine hochgeladene Datei prüfen, ohne zu speichern: Lieferanten-GeoJSON („text“) oder ein vom Browser gelesener Produktionsort („ort“: Bericht oder eingefügte …

**Sendungen**

- `eudr_sendung_pruefen(b, betriebe, alt)` – Felder einer Sendung aus der Eingabe prüfen (ohne id, rev, Zeitstempel und Abschluss); $betriebe = gespeicherte Farmer.
- `eudr_sendung_laufend(b, alt)` – Angaben, die sich mit der Reise des Containers ändern – sie bleiben auch nach dem Abschluss der Bewertung pflegbar.
- `ci_reise(b, alt)` – Stand und Containernummer aus der Eingabe (ohne Eingabe bleibt der gespeicherte Wert) – die eine Stelle für alle, die sie pflegen: das Fenster „Container“ …
- `eudr_sendung_nachtrag(b, alt)` – Was einem älteren Eintrag noch fehlt, lässt sich auch nach dem Abschluss der Bewertung nachtragen – einmal, solange das Feld leer ist: die Partienummer …
- `ci_lieferant_schluessel(x)` – Schlüssel des Lieferanten eines Eintrags (Container, Schlachthof): mit Nummer der Stammdaten die Nummer, sonst der Name ohne Rücksicht auf Groß- und …
- `eudr_lieferant(b, alt)` – Lieferant eines Containers: mit „lieferantNr“ aus den Stammdaten der Verwaltung (Schnittstelle lieferanten_kurz, GR-101).
- `eudr_lieferant_name(stamm)` – Name eines Lieferanten der Stammdaten; ohne Namen der Kurzname, ohne beides „Lieferant <Nummer>“
- `eudr_lieferanten()` – Lieferanten zur Auswahl am Container: nur Nummer und Name, nach Name sortiert
- `eudr_partie_vergeben(liste, partie, ausser)` – Ist die Partienummer schon bei einem anderen Container vergeben (auch bei einem archivierten)?
- `eudr_container_name(s)` – Wie ein Container heißt: seine Partienummer; ältere Einträge ohne Partienummer nach der Auftragsnummer
- `eudr_containernummer(text)` – Containernummer nach ISO 6346 (vier Buchstaben, sechs Ziffern, Prüfziffer) einordnen: '' leer, 'ok', 'pruefziffer' (Tippfehler?) oder 'format'.
- `eudr_dds_pruefen(dds)` – Angaben zur Sorgfaltserklärung im EU-Informationssystem (auch nach dem Abschluss änderbar)

**Risikoprofil**

- `eudr_namen(betriebe, bedingung)` – Namen der Betriebe, auf die eine Bedingung zutrifft
- `eudr_bewertet(betriebe, thema, stufe)` – Namen der Betriebe mit einer bestimmten Bewertung in einem Thema (eudr_betrieb_bewertung)
- `eudr_kriterium(id, titel, stand, text, betriebe)` – Ein Kriterium des Profils: stand ok \| hinweis \| offen \| kritisch
- `eudr_kriterien()` – Kriterien des Risikoprofils (Art. 10 der Verordnung) als Tabelle: jede Zeile bewertet die Sendung mit ihren Betrieben ($bs = Sichten der Betriebe) und …
- `eudr_profil(s, bs)` – Risikoprofil einer Sendung: alle Kriterien, Gesamtstand (das schlechteste Kriterium) und ein Vorschlag.
- `eudr_sendung_betriebe(s, sichten)` – Betriebe einer Sendung als Sichten: nach dem Abschluss der Schnappschuss, sonst der aktuelle Stand
- `eudr_abschluss(s, eingabe, sichten, me)` – Abschluss einer Bewertung aus der Eingabe: Ergebnis, Begründung, Bearbeiter und Schnappschuss von Profil und Betrieben (GR-106).
- `eudr_sendung_sicht(s, betriebe, hofNamen)` – Sendung für die Oberfläche: mit Profil – bei abgeschlossener Bewertung dem gespeicherten Schnappschuss; frühere Abschlüsse nur mit Ergebnis, Begründung und …

**GeoJSON für das EU-Informationssystem**

- `eudr_geojson(bs)` – FeatureCollection aus Betrieb-Sichten: Eigenschaften in der vorgeschriebenen Schreibweise, Fläche als Zahl.

**Stand für die Oberfläche**

- `eudr_stand()` – Alle Betriebe und Sendungen mit abgeleiteten Werten, dazu Länder und Portale

## `app/api/module/containerimport/farmer.php`

_STAFL-Plattform · Modul Container-Import – Farmer-Nummern am Container (Auftrag des Inhabers 19.11.2026)._

- `ci_farmer_nr(nr)` – Eigene Farmer-Nummer zum Anzeigen: „F-“ unterscheidet sie von den Nummern aus den Papieren (meist nur Ziffern)
- `ci_nummer_norm(nummer)` – Nummer zum Vergleichen: ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen, Punkte und Striche – „P-100“ und „p 100“, „12.345“ und „12 345“ sind …
- `ci_nummer_schluessel(land, nummer)` – Schlüssel einer Nummer aus den Papieren: im Herkunftsland eindeutig ('' = keine Nummer, auch bei „-“ oder „.“)
- `ci_nummern_index(liste)` – Nummern aus den Papieren der Farmer $liste: Schlüssel → Stelle des ersten Farmers damit (einmal je Anfrage bauen).
- `ci_nummer_vergeben(index, schluessel, ausser)` – Stelle eines anderen Farmers mit dieser Nummer aus den Papieren (archivierte zählen mit; null = keiner oder keine Nummer).
- `ci_nummern_lesen(v)` – Farmer-Nummern aus der Eingabe: Text (je Zeile, durch Komma, Semikolon oder Tabulator getrennt – so kommen sie aus einer Liste oder Tabelle) oder Liste.
- `ci_nummern_aufloesen(nummern, land, ids, offen, betriebe, index)` – Farmer-Nummern eines Containers im Land $land auflösen – dieselbe Regel für die Vorschau und das Speichern.
- `ci_nummern_anwenden(ids, zeilen)` – Aufgelöste Nummern ($zeilen) an einem Container mit den Farmern $ids übernehmen: gefundene Farmer kommen dazu, vermerkt bleiben nur die unbekannten Nummern → …
- `ci_offene_nummern_zuordnen(liste, betriebe, me)` – Gespeicherte Farmer ($betriebe) den Containern zuordnen, die ihre Nummer aus den Papieren vermerkt haben – nur Container mit offener Bewertung, die nicht …
- `ci_doppelte_nummern_melden(dateien)` – Neue Farmer eines Einlese-Durchgangs (alle Dateien, $dateien = Ergebnisse von eudr_datei_pruefen) mit derselben Nummer aus den Papieren: das zweite Vorkommen …
- `ci_farmer_pruefung(bs, offen)` – Gesamtprüfung der Farmer eines Containers ($bs = Sichten, nach dem Abschluss der Schnappschuss): wie viele in Ordnung (Ampel grün), wie viele Nummern ohne …
- `ci_offene_nummern(sendungen, index)` – Vermerkte Nummern aller Container für die Gesamtübersicht: je Nummer (im Land) einmal, mit den Containern, die sie nennen.

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

## `app/api/module/containerimport/hafen.php`

_STAFL-Plattform · Modul Container-Import – Tracking, zweite Stufe: bestätigte Ankunft in Hamburg aus der öffentlichen Liste „Expected vessels“ von Hafen Hamburg (Quelle dort_

- `ci_schiff_schluessel(name)` – Schiffsname für den Vergleich: nur Buchstaben und Ziffern, groß – „MSC San-Francisco“ = „msc san francisco“
- `ci_hafen_hh_lesen(html)` – Einträge aus dem HTML der Liste: je Schiff eine Überschrift „November 19, 2026, 3:00 pm \| Liegeplatz, Terminal“ und darunter der Name.
- `ci_hafen_hh_abrufen()` – Die Liste abrufen: [Einträge, Fehlertext].
- `ci_hafen_meldungen()` – Gespeicherte Meldungen: ['abgerufen' => Zeit des letzten beendeten Abrufs\|'', 'gelesen' => Zeit des letzten gelungenen\|'', 'fehler' => Text\|'', 'versuch' => …
- `ci_hafen_ablegen(neu)` – Felder des Dokuments ändern, der Rest bleibt stehen (unter Sperre gelesen und geschrieben)
- `ci_hafen_hh_betrifft(s)` – Gehört die Hamburger Liste zu diesem Container?
- `ci_hafen_noetig(sendungen)` – Braucht gerade ein Container die Liste?
- `ci_hafen_alter(t)` – Sekunden seit einem Zeitstempel aus now(); '' oder Unlesbares zählt als sehr lange her
- `ci_hafen_auffrischen(sendungen)` – Liste auffrischen, wenn sie gebraucht wird und die Frist um ist.
- `ci_hafen_sicht(sendungen)` – Meldungen für die Oberfläche: nur was zu unseren Containern gehört (Kennung des Containers → Schiff, Ankunft, Liegeplatz, Terminal), dazu Zeit und Ergebnis …

## `app/api/module/containerimport/schlachthoefe.php`

_STAFL-Plattform · Modul Container-Import – Schlachthöfe_

- `ci_schlachthoefe()` – Dokument der Schlachthöfe
- `ci_schlachthof_namen()` – Namen aller Schlachthöfe nach ihrer Kennung
- `ci_schlachthof_pruefen(b, alt)` – Felder eines Schlachthofs aus der Eingabe prüfen (ohne id, rev und Zeitstempel)
- `ci_schlachthof_speichern(b, me)` – Schlachthof anlegen oder ändern (innerhalb der Sperre EUDR_SPERRE aufrufen).
- `ci_schlachthof_lieferant_wechseln(alt, neu)` – Folgen eines Lieferantenwechsels am Schlachthof für seine Container (Regel siehe ci_schlachthof_speichern).
- `ci_schlachthof_am_container(b, lieferant, bisher)` – Schlachthof eines Containers aus der Eingabe: leer oder ein Schlachthof desselben Lieferanten ($lieferant = Eintrag mit lieferantNr und lieferant).

## `app/api/module/containerimport/tracking.php`

_STAFL-Plattform · Modul Container-Import – Tracking: wo ist der Container, wann kommt er an (Auftrag des Inhabers 19.11.2026: eigener Reiter neben EUDR; Schiffsname eintragen; wissen, wann der Container z._

- `ci_tracking_pruefen(b, alt)` – Angaben des Trackings aus der Eingabe prüfen (genau die Felder aus CI_TRACKING_VORGABEN).

## `app/api/module/containerimport/whisp.php`

_Container-Import · EUDR_

- `whisp_schluessel()`
- `whisp_eingerichtet()`
- `whisp_http(methode, pfad, inhalt)` – Eine Anfrage an Whisp: [Status, JSON\|null]; Status 0 = nicht erreichbar.
- `whisp_antwort(status, json)` – Antwort von Whisp für die Oberfläche: ['fertig' => true, 'ergebnis' => …] oder ['fertig' => false, 'token', 'prozent'].
- `whisp_starten(geometrie)` – Abfrage für einen Umriss starten – die Funktion bekommt nur die Geometrie, Namen kann sie nicht versenden
- `whisp_stand(token)` – Stand einer gestarteten Abfrage
- `whisp_ergebnis(daten)` – Eigenschaften der ersten Fläche aus dem Ergebnis – nur einfache Werte mit harmlosen Namen (die Oberfläche maskiert sie zusätzlich); der zurückgelieferte …

## `app/module/containerimport/containerimport.js`

_STAFL-Plattform · Modul Container-Import – Container (ein Einkauf bei einem Lieferanten, eine Partienummer) mit ihren Farmern; Reiter EUDR_

**Aufruf der API: wirft nie, liefert { status, data }**

- `api(action, body, query, sperre)`
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`
- `fokusBehalten(zeichne)` – Neu zeichnen, ohne die Tastatur zu stören: Fokus und Schreibmarke gehen an das Element mit derselben id zurück (Suchfeld beim Tippen, Listenzeile bei einer …
- `uebernehmen(r, fallback)` – Antwort einer speichernden Aktion: neuen Stand übernehmen. false = Fehler (Meldung gezeigt)

**Formate und Bezeichnungen**

- `schlachthofWahl(lieferant, aktuell)`

**Bausteine für Fenster und Formulare**

- `feld(label, name, wert, o)`
- `werte(form)` – Werte aller benannten Felder eines Formulars als Objekt (Kontrollkästchen mit gleichem Namen als Liste)
- `oeffnen(dlg)`
- `lieferantFeld(s, aus, neu, kennung)` – Feld „Lieferant“ mit den Vorschlägen der Stammdaten (Fenster „Container“ und „Schlachthof“); kennung = id der Vorschlagsliste

**Seite**

- `zeichnen()` – Kopf und der gewählte Reiter.
- `eudrZeichnen()`
- `sendungenSicht()`
- `betriebeSicht()` – Gesamtübersicht aller Farmer: Ampel, eigene Nummer und Nummer aus den Papieren, Prüfstand, Container (mit Lieferant); dazu je vermerkte Nummer ohne …
- `karteSicht()`

**Fenster „Farmer“**

- `betriebOeffnen(id)`
- `auswertungZeigen(b, darf)` – Bildauswertung im Fenster „Farmer“: Wald Ende 2020 und Waldverlust seit 2021 in der Fläche – eine Schätzung aus den Kartenbildern (eudr-auswertung.js).
- `vorschlagNehmen(d, portal)` – Vorschlag (Bildauswertung oder Whisp) in das Formular der Gegenprüfung schreiben; der Bearbeiter entscheidet und trägt selbst ein. dataset: ergebnis ('' = …
- `whispPruefen()` – Whisp für den geöffneten Betrieb abfragen (Server: containerimport_eudr_whisp).
- `whispZeigen(el, ergebnis, b)` – Ergebnis von Whisp als Vorschlag zeigen (Deutung: eudr-whisp.js); „Übernehmen“ füllt nur das Formular
- `betriebAusFenster(b, w)` – Felder des Fensters als Betrieb für den Server
- `betriebSpeichern(zusatz)`
- `pruefungEintragen()`

**Fenster „Container“**

- `farmerListe(s, ids, offen, aus)` – Farmer im Fenster „Container“: zugeordnete und vermerkte Nummern ohne Unterlagen (angehakt – abhaken und speichern entfernt sie), darunter aufgeklappt die …
- `nummernPruefen()` – Eingefügte Nummern prüfen lassen (speichert nichts) und als Vorschau zeigen
- `nummernUebernehmen()` – Vorschau ins Fenster übernehmen; gespeichert wird mit „Speichern“ (der Server löst die Nummern dabei erneut auf)
- `sendungOeffnen(id)`
- `sendungAusFenster()`
- `schlachthofWahlNeu()` – Lieferant im Fenster geändert: zur Wahl stehen nur seine Schlachthöfe; der gewählte bleibt, wenn er dazugehört
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

## `app/module/containerimport/eudr-auswertung.js`

_STAFL-Plattform · Container-Import · EUDR – Bildauswertung einer Fläche_

- `frist(ms)` – Abbruchsignal nach ms Millisekunden (AbortSignal.timeout fehlt in älteren Browsern)
- `bild(adresse)` – Bild ohne Farbanpassung laden – sonst könnte der Browser das Jahr im Blaukanal um eins verschieben.
- `leinwand(w, h)`
- `rechnen(geometrie, bis, quellen)`

## `app/module/containerimport/eudr-bericht.js`

_STAFL-Plattform · Container-Import · EUDR – Entwaldungsberichte der Lieferanten lesen (reine Funktionen, kein DOM)._

- `zeilen(stuecke)` – Zeilen einer Seite, von oben nach unten: je Zeile die Läufe von links nach rechts. pdf.js liefert Text oft in Stücken („500000“, „.“, „00“) – Stücke ohne …
- `punkte(text)` – Koordinatenpaare aus Text: „p0 500000.00 7400000.00, p1 …“, „p0,500000.00,7400000.00,p1,…“ oder je Zeile „x y“. Bei nummerierten Listen müssen die Nummern …
- `konform(text)` – „Compliant“ / „Non-compliant“ und die Zahl danach aus dem Text eines Abschnitts.
- `stammdaten(zeilenListe)` – Werte der Tabelle „Farm information summary“: jedes Textstück unter den Überschriften gehört zur nächstgelegenen Spalte
- `lesen(seiten)` – Bericht lesen. null, wenn die Datei keine Koordinatenliste enthält (dann ist es kein solcher Bericht); { fehler } wenn sie eine enthält, die sich nicht …

## `app/module/containerimport/eudr-karte.js`

_STAFL-Plattform · Container-Import · EUDR – Karte der Herkunftsbetriebe._

- `ausschnitt(betriebe, rand, minGrad, seite)` – Rahmen [x, y, Breite, Höhe] in Karteneinheiten um die Betriebe: Rand anteilig, Mindestbreite in Grad
- `rund(grenze)` – „Runde“ Strecke für den Maßstab: 1, 2 oder 5 mal Zehnerpotenz, höchstens grenze Meter
- `svg(box, inhalt, klasse)`
- `groessen(el)` – Größen, die mit dem Zoom mitgehen müssen (Marken, Eckpunkte), aus der aktuellen Breite des Ausschnitts setzen
- `bedienung(el, start, beiKlick)` – Zoomen (Rad, Knöpfe) und Verschieben (Ziehen) über die viewBox; ein Antippen ohne Ziehen auf einem Betrieb ruft beiKlick – das Ziel wird beim Drücken …
- `pruefeDienste()` – Welche Dienste antworten (Netz, Content-Security-Policy)?
- `auswerten(geometrie)` – Bildauswertung einer Fläche (eudr-auswertung.js) aus denselben Diensten – null, wenn sie nicht erreichbar sind
- `detail(el, opt, betriebe, dienst, vektor)` – Detailkarte: Bilder (wenn erreichbar), Straßen und Orte (wenn die Herkunftskarte geladen ist), darüber die Flächen in der Farbe ihrer Ampel; in der Übersicht …
- `zeichnen(el, opt)`

## `app/module/containerimport/eudr-whisp.js`

_Container-Import · EUDR_

- `deuten({…}, abHa)`

## `app/module/containerimport/schlachthoefe.js`

_STAFL-Plattform · Modul Container-Import – Schlachthöfe_

- `sicht()`
- `fenster(id)`
- `speichern(zusatz)`

## `app/module/containerimport/tracking.js`

_STAFL-Plattform · Modul Container-Import – Reiter „Tracking“: wo ist der Container, wann kommt er an (Auftrag des Inhabers 19.11.2026)._

- `ankunft(s)` – Ankunft in Worten: [Text, Farbe der Marke]
- `hafenHinweis()`
- `hafenAuffrischen()` – Server bitten, die Hafenliste aufzufrischen (wann: siehe Kopf).
- `zeichnen()`
- `fenster(id)`
- `speichern()`

## `tests/e2e/containerimport_hilfe.py`

_Gemeinsame Hilfen für die Testgruppen des Moduls Container-Import (containerimport_*)_

- `check(n, c, i)` – Eine Prüfung: Name, Ergebnis, bei Fehlschlag ein Hinweis zur Fehlersuche.
- `ende()` – Zusammenfassung ausgeben und mit dem Ergebnis der Gruppe enden.
- `nutzer_anlegen()` – Administrator anmelden und die beiden Nutzer des Moduls anlegen → (Administrator, Ina, Lea) als angemeldete Clients.
- `login(user)`
- `stand(client)` – Stand der Seite (containerimport_start) so, wie dieser Nutzer ihn sieht.
- `kalender(client)` – → tag(n): Datum n Tage ab heute (Datum des Servers) als JJJJ-MM-TT.
- `container_anlegen(client, partie, **mehr)` – Container mit dieser Partienummer anlegen – muss gelingen.
- `container(r, partie)` – Container mit dieser Partienummer aus einer Antwort ({} = nicht dabei).
- `seite(br, user, errs, fremd, vp, schema)` – Seite des Moduls für einen Nutzer öffnen; JavaScript-Fehler landen in errs, Anfragen nach außen in fremd.

## `tests/e2e/test_containerimport.py`

_Modul Container-Import, Reiter EUDR (app/module/containerimport/, Oberfläche containerimport.intern, Auftrag des Inhabers 18.11.2026)_

- `check(n, c, i)`
- `utm_nach_wgs84(rechts, hoch, zone, sued)` – Unabhängige Gegenrechnung (Krüger-Reihen nach Karney) – der Server rechnet mit einer anderen Formel.
- `pdf_bauen(seiten)` – Einfache PDF-Datei aus Textstücken je Seite [(x, y, Text), …] – für den erfundenen Bericht.

**Register: produktiv (Entscheidung des Inhabers 18.11.2026)**

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

- `png(punkt)` – PNG mit 512 × 512 Bildpunkten, punkt(x, y) → (R, G, B, A)
- `kartendienste(abrufe, ohne, verlust)` – Antwortet wie die drei Dienste, mit CORS-Freigabe: Kacheln der Karte als Testbild; für die Bildauswertung die Muster (Wald als WMS mit 512 Punkten, Verlust …
- `antwort(route)`
- `seite(user, vp, schema, dienste)`
- `kartendatei(route)`

**Originale im QM-System (Schnittstelle qs_eingang_hochladen)**

- `original(c, name, inhalt, lieferant, teil)` – Datei in Teilen an containerimport_eudr_original geben; Antwort des letzten Aufrufs.

## `tests/e2e/test_containerimport_farmer.py`

_Container-Import: Farmer je Container (Auftrag des Inhabers 19.11.2026) – eigene fortlaufende Farmer-Nummer neben der Nummer aus den Papieren (Kennung), Farmer über die Nummern aus den Papieren einem Container …_

- `farmer(name, kennung, x, land, y, **mehr)` – Farmer mit kleinem Umriss (Westecke x/y) und Nummer aus den Papieren.
- `betrieb(name, r)`
- `speichern(*betriebe, sendung)`

**Eigene Farmer-Nummer, Nummer aus den Papieren**

- `ort(name, kennung, x)`

## `tests/e2e/test_containerimport_hafen.py`

_Container-Import · Tracking: bestätigte Ankunft in Hamburg aus der öffentlichen Liste „Expected vessels“ von Hafen Hamburg (app/api/module/containerimport/hafen.php, Aktion containerimport_tracking_hafen, Anzeige in …_

- `im_format_der_seite(n)`
- `ankunft(n, uhr)` – Ankunft, wie der Server sie ablegt: Ortszeit Hamburg mit Zeitzone.

**nachgebaute Seite des Hafens**

- `log_message(*a)`
- `do_GET()`
- `anlegen(partie, **tracking)`
- `gespeichert(aendern)` – Das gespeicherte Dokument der Meldungen ändern (aendern bekommt es als dict).
- `faellig(modus)` – Der nächste Aufruf ruft wieder ab (letzter Abruf vor Jahren), der Nachbau antwortet im angegebenen Modus.
- `abruf(modus, wer)` – Aktion aufrufen → (Status, Antwort, neue Anfragen beim Hafen).
- `haengend()` – Solange der Block läuft, antwortet der Nachbau nicht. haengt_dort() wartet, bis eine Anfrage dort angekommen ist; am Ende des Blocks antwortet er wieder.
- `haengt_dort()`

**Rechte, kein Abruf ohne Bedarf**

**Abruf, Lesen, Zuordnen**

**Fehlschläge, Verfall**

**ein hängender Abruf hält nichts auf**

**Oberfläche**

- `seite(user, vp, schema)`

## `tests/e2e/test_containerimport_schlachthof.py`

_Container-Import: Schlachthöfe als Stammdaten unter dem Lieferanten (Aktion containerimport_schlachthof_save, app/api/module/containerimport/schlachthoefe.php, Oberfläche app/module/containerimport/schlachthoefe.js)._

- `check(n, c, i)`

**Nutzer und Stammdaten**

- `login(user)`
- `hoefe(r)`
- `container(r, partie)`
- `hof_speichern(daten)` – Schlachthof speichern → (Status, Antwort, der gespeicherte Eintrag).
- `abschliessen(c, **mehr)` – Bewertung eines Containers abschließen (oder mit oeffnen=True, grund=… wieder öffnen) → (Status, Antwort).

**Rechte**

**Anlegen und ändern**

**Schlachthof am Container**

**Archivieren**

**Umbenennen: offene Container folgen, abgeschlossene nicht (GR-106)**

**Ältere Container ohne das Feld (GR-006), Nachtragen nach dem Abschluss, Felder einer späteren Version**

**Oberfläche**

- `seite(user, vp, schema)`

## `tests/e2e/test_containerimport_tracking.py`

_Container-Import: Reiter „Tracking“ (Aktion containerimport_tracking_save, app/api/module/containerimport/tracking.php, Oberfläche app/module/containerimport/tracking.js) – erste Stufe ohne fremde Dienste._

- `anlegen(partie, **mehr)`
- `tracking(c, **angaben)` – Tracking speichern → (Status, Antwort, der Container danach).
- `vorbereiten(c, **angaben)` – Tracking für die Oberfläche unten setzen – muss gelingen.

**Stand und Rechte**

**Speichern**

**Zusammenspiel mit dem Reiter EUDR**

**Oberfläche**

- `seite(user, vp, schema)`

## `tests/e2e/test_containerimport_whisp.py`

_Container-Import · EUDR_

- `check(n, c, i)`

**nachgebautes Whisp**

- `log_message(*a)`
- `antwort(status, inhalt)`
- `bedienen()`

**Nutzer und Betriebe**

- `login(user)`

**Rechte**

**Abfrage: starten, nachfragen, Ergebnis**

**Fehler von Whisp**

- `seite(user, vp, schema)`
