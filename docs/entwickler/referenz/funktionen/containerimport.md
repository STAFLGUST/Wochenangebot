# Funktionen: Container-Import (`containerimport`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

34 Dateien, 374 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/containerimport.php`

_Aktionen: Modul Container-Import – Container (im Code „sendung“) mit Lieferant, Partie-, Akten- und Containernummer und Stand; Reiter EUDR – Farmer (im Code „betrieb“) mit Geolokalisierung, Risikoprofil und …_

- `eudr_leser(post)` – Mitarbeiter mit Modulzugang und dem Recht anzusehen (lesende Aktionen; $post = Aktion kommt als POST mit CSRF)
- `eudr_bearbeiter()` – Mitarbeiter mit Modulzugang und dem Recht zu bearbeiten (schreibende Aktionen)

## `app/api/aktionen/containerimport_kalkulation.php`

_Aktionen: Modul Container-Import – Kalkulation je Container (Auftrag des Inhabers 20.11.2026; Rechenkern und Fassungen in app/api/module/containerimport/kalkulation.php)._

- `ci_kalk_container(id)` – Container (404) mit dem Schnappschuss, den eine endgültige Fassung festhält

## `app/api/module/containerimport/dokumente.php`

_STAFL-Plattform · Modul Container-Import – Dokumente je Container (Auftrag des Inhabers 20.11.2026: alle Unterlagen eines Containerordners – Kaufbestätigung, Rechnungen, Zertifikate, B/L, Versicherung, Spedition, …_

**Speicher**

- `ci_dokumente()` – Dokument mit Vorgaben; Felder einer späteren Version bleiben beim Schreiben erhalten (GR-006)
- `ci_dokumente_schreiben(doc)` – Schreiben (unter EUDR_SPERRE) zählt containerimport-dokumente-zahlen neu – immer beide (Muster qs-ablage-zahlen)
- `ci_dokumente_zahlen_lesen()` – Zahlen je Container für den Stand der Seite; fehlt das Dokument (vor dem ersten Schreiben), aus containerimport-dokumente
- `ci_dok_wer(me)` – Stempel mit Nutzer-Kennung: ein Name kann sich ändern, die Kennung nicht
- `ci_dok_arten(v)` – Arten aus der Eingabe: mindestens eine, alle bekannt; Ergebnis in der Reihenfolge der Liste, ohne Doppelte
- `ci_dok_artname(art)`
- `ci_dok_artnamen(arten)`
- `ci_dok_holen(doc, id)` – Datei nach Kennung (404) samt Stelle
- `ci_dok_container(sendung)` – Container nach Kennung oder null
- `ci_dok_grenzen(liste, sendung)` – Grenzen vor dem Hochladen und noch einmal unter der Sperre (zwei gleichzeitige Uploads)
- `ci_dok_von(liste, sendung)`

**Sichten**

- `ci_dok_regeln()` – Was die Oberfläche zum Hochladen und Anzeigen braucht
- `ci_dok_nicht_noetig(checkliste, sendung)` – Als „nicht nötig“ vermerkte Arten eines Containers: der letzte Vermerk je Art gilt
- `ci_dokumente_zahlen(doc)` – Je Container mit Dokumenten oder Vermerken: {anzahl, arten: {art: n}, nichtNoetig: [art]} – aktive Dateien; eine Datei zählt bei jeder ihrer Arten.
- `ci_dokumente_antwort(doc, sendung)` – Antwort der Aktionen: Zahlen aller Container (leer als {}), Dateien (auch entfernte, älteste zuerst) und Vermerke der Checkliste des einen

**Hochladen, Arten ändern, Entfernen, Checkliste**

- `ci_dokument_hochladen(me, b)` – Einen Teil annehmen ($b wie ablage_teil, dazu sendung und arten).
- `ci_dokument_arten_aendern(b, me)` – Arten einer Datei ändern: Vermerk im Verlauf (alte und neue Arten); entfernte Dateien bleiben, wie sie sind (409).
- `ci_dokument_entfernen(b, me)` – Datei als entfernt vermerken (Grund Pflicht); sie bleibt in der Ablage und für Berechtigte abrufbar.
- `ci_dokument_checkliste(b, me)` – Punkt der Checkliste als „nicht nötig“ vermerken oder wieder als nötig (noetig: true/false) – nur anhängen.

**ZIP für Betriebsprüfung und Datenträgerüberlassung**

- `ci_csv(zeilen)` – shortcut: Kopie von qs_csv_zelle (module/qs) – gehört in eine Plattform-PR als lib/csv.php, dann beide umstellen
- `ci_dok_zip_name(name)` – Dateiname im ZIP: nur der Stamm wird gekürzt (ablage_zip_pfad, 100 Zeichen), die Endung bleibt
- `ci_dokumente_zip_eintraege(s, dateien, vermerke)` – Einträge für ablage_zip_senden: <Container>/<erste Art>/<Datei>, entfernte unter <Container>/_entfernt/<erste Art>/, dazu index.csv mit allen Angaben je …

## `app/api/module/containerimport/eudr.php`

_Container-Import: Container (ein Einkauf bei einem Lieferanten, eine Partienummer) mit ihren Farmern und der Prüfung nach der EUDR (Verordnung (EU) 2023/1115, entwaldungsfreie Lieferketten)_

**Speicher**

- `eudr_liste(d)` – Inhalt eines Dokuments als ['rev', 'liste'] (fehlt es, leer)
- `eudr_fortschreiben(doc)` – Dokument für das Schreiben fortschreiben: Revision erhöhen, Zeitstempel setzen
- `eudr_betriebe()` – Dokument der Herkunftsbetriebe mit der eigenen Farmer-Nummer „nr“ = Stelle + 1. Annahme: die Liste wächst nur am Ende, nichts wird gelöscht oder umsortiert …
- `eudr_sendungen()` – Dokument der Sendungen
- `eudr_betriebe_schreiben(doc)` – Herkunftsbetriebe speichern.
- `eudr_sendungen_schreiben(doc)` – Sendungen speichern
- `eudr_id(praefix)` – Neue Kennung mit Vorsilbe (b = Betrieb, s = Sendung)
- `eudr_wer(me)` – Stempel „wann und von wem“
- `eudr_stelle(liste, id)` – Stelle eines Eintrags in einer Liste nach seiner id (null = nicht vorhanden)
- `eudr_holen(doc, id, fehlt)` – Eintrag eines Dokuments nach id samt seiner Stelle (404 mit $fehlt): Container, Dateien am Container
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
- `eudr_geo_befunde(b)` – Befunde des Umrisses eines Betriebs.
- `eudr_bekannt_tabelle(liste)` – Nachschlagetabelle der gespeicherten Betriebe zum Wiedererkennen (einmal je Anfrage): Nummer aus den Papieren bzw. Umriss → Betrieb
- `eudr_bekannt(neu, tabelle)` – Gespeicherter Betrieb, der zu einem eingelesenen passt: gleiche Nummer aus den Papieren im selben Land, sonst dieselbe Geometrie
- `eudr_pruefungen_aktuell(b)` – Jüngste Gegenprüfung je Portal (nur diese zählt im Risikoprofil)
- `eudr_betrieb_sicht(b)` – Betrieb für die Oberfläche: gespeicherte Felder plus abgeleitete Kennzahlen und Befunde. stand: „fehler“ (Geolokalisierung so nicht einreichbar), „hinweis“ …
- `eudr_betrieb_bewertung(b, geoStand)` – Bewertung eines Betriebs je Thema (ok \| offen \| kritisch): das Risikoprofil der Sendung und die Farbe auf der Karte lesen sie hier ab. Was erst mit der …
- `eudr_pruefung_pruefen(b, me)` – Eine Gegenprüfung aus der Eingabe prüfen

**Dateien einlesen**

- `eudr_eigenschaft(eigenschaften, name, falsch)` – Eigenschaft eines GeoJSON-Features lesen.
- `eudr_geojson_lesen(text, datei)` – Lieferanten-GeoJSON lesen: je Feature ein Produktionsort (MultiPoint wird in Punkte zerlegt).
- `eudr_datei_pruefen(d, bekannt, punkte)` – Eine hochgeladene Datei prüfen, ohne zu speichern: Lieferanten-GeoJSON („text“) oder ein vom Browser gelesener Produktionsort („ort“: Bericht oder eingefügte …

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
- `eudr_sendung_betriebe(s, sichten, stelle)` – Betriebe einer Sendung als Sichten: nach dem Abschluss der Schnappschuss (seit 23.11.2026 ohne Umriss, mit Umriss: eudr_schnappschuss_betriebe), sonst der …
- `eudr_abschluss(s, eingabe, sichten, me)` – Abschluss einer Bewertung aus der Eingabe: Ergebnis, Begründung, Bearbeiter und Schnappschuss von Profil und Betrieben (GR-106).
- `eudr_schnappschuss_ablegen(sendung, a)` – Farmer eines Abschlusses (eudr_abschluss) mit Umriss in ein eigenes Dokument legen – neue Kennung, nie überschrieben – und den Abschluss für das Dokument der …
- `eudr_schnappschuss_betriebe(a)` – Farmer eines Abschlusses samt Umriss: aus seinem Dokument, nur wenn die Prüfsumme stimmt; Abschlüsse von vor dem 23.11.2026 tragen sie eingebettet
- `eudr_schnappschuss_summe(betriebe)` – Prüfsumme über die gespeicherte Form: −0 schreibt json_encode als „-0“, gelesen wird daraus 0 (Fläche am Äquator)
- `eudr_ohne_umriss(betriebe)`
- `eudr_sendung_sicht(s, betriebe, hofNamen, stelle)` – Sendung für die Oberfläche: mit Profil – bei abgeschlossener Bewertung dem gespeicherten Schnappschuss, dessen Farmer ohne Umriss (die Karte holt ihn mit …

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
- `geo_selbstschnitt(ring, abbruch)` – Erste Selbstüberschneidung eines geschlossenen Rings als [Kante i, Kante j] (Nummern ab 1) oder null.
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

## `app/api/module/containerimport/kalkulation.php`

_STAFL-Plattform · Modul Container-Import – Kalkulation je Container (Auftrag des Inhabers 20.11.2026)_

**Eingabe prüfen (Grenze: alles, was vom Browser kommt)**

- `ci_kalk_zahl(v, was, max)` – Zahl von 0 bis $max oder null (leer); Text auch deutsch („1.234,5“, zahl_text_de).
- `ci_kalk_tage(v)` – Zinstage: ganze Zahl (ein Komma würde sonst still abgeschnitten)
- `ci_kalk_kn(v)` – KN-Code: acht Ziffern (Leerzeichen erlaubt) oder leer
- `ci_kalkulation_eingabe(b)` – Rohe Eingabe → geprüfte Eingabe.
- `ci_kalk_liste(v, max, was)` – Liste aus der Eingabe (höchstens $max Einträge, jeder ein Objekt)

**Rechnen (reine Funktionen)**

- `ci_kalkulation_rechnen(e, saetze)` – Kalkulation rechnen: geprüfte Eingabe (ci_kalkulation_eingabe) + Sätze (CI_KALK_SAETZE oder Schnappschuss) → Ergebnis.
- `ci_kalk_hinweis(stufe, text, pos)` – Prüfhinweis: stufe fehler (Kalkulation unvollständig) \| warnung \| hinweis; pos = Stelle der Position oder null
- `ci_kalk_saetze_anwenden(saetze, ueberschrieben)` – Schritt 1 – Sätze anwenden: überschriebene Sätze der Kalkulation über die Tabelle legen.
- `ci_kalk_pruefen(e, tab)` – Schritt 2 – Prüfen: was fehlt oder nicht zusammenpasst, bevor gerechnet wird
- `ci_kalk_position_pruefen(p, i, datum, tab)` – Ursprung ↔ Zollregime ↔ Datum ↔ KN-Code einer Position
- `ci_kalk_satz(p, datum, tab)` – Wirksamer Satz einer Position mit Schlüssel; null, wenn keiner wählbar ist (ci_kalk_position_pruefen meldet den Grund)
- `ci_kalk_drittland_satz(kn, tab)` – Drittlandszoll nach KN-Code (auch für den Vergleich mit dem Mercosur-Kontingent); null für einen nicht hinterlegten Code
- `ci_kalk_zoll_kg(zollwertKg, satz)` – Zoll je kg: Wertzoll % vom Zollwert + spezifischer Zoll €/100 kg
- `ci_kalk_satz_text(s)`
- `ci_kalk_kn_text()`
- `ci_kalk_tag(d)`
- `ci_kalk_teilen(a, b)` – Quotient, 0 bei Nenner 0 (nur wo 0 die richtige Anzeige ist und ein Hinweis den Grund nennt)
- `ci_kalk_eur(betrag, waehrung, kurs)`
- `ci_kalk_kosten(e)` – Schritt 3 – Kosten des Containers: Seefracht, Provision und Nebenkosten je kg (für alle Positionen gleich)
- `ci_kalk_position(p, kopf, kosten, teil, satz)` – Schritt 4 – Position: Einstand je kg und Werte ($teil = Teil der Eingabe, $satz = ci_kalk_satz)
- `ci_kalk_auswertung(e, pos, kosten)` – Schritt 5 – Auswertung je Teil und gesamt: Summen, Versicherungswert und Prämie, Ertrag.
- `ci_kalk_summe(eingabe, pos, ids)` – Summen über Positionen ($ids = Stellen): Kartons, Gewichte, Beträge; Soll und VK nur, wenn jede Position sie hat
- `ci_kalk_ertrag(x, rueckverguetung, wkz)` – Rohertrag (VK − Ist), Marge (vom VK), Aufschlag (vom Ist, wie „% Marge“ der bisherigen Excel), € je kg, Rückvergütung, WKZ und Rohgewinn – alles null ohne …
- `ci_kalk_ergebnis_pruefen(e, pos, teile)` – Prüfhinweise zum Ergebnis: Imag.
- `ci_kalk_kontingente(e, pos, tab)` – Zoll und Netto je Zollregime, Schlachtkörperäquivalent im Mercosur-Kontingent (null, wenn es für eine Position nicht bekannt ist) und Vergleich mit/ohne …
- `ci_kalk_anteilig(positionen)` – Anteilig Hilton: Artikel (Schreibweise egal) in mehr als einem Zollregime, mit kg je Regime und Anteil im Hilton-Kontingent

**Fassungen (Dokument containerimport-kalkulationen)**

- `ci_kalk_dokument()`
- `ci_kalk_positionen(fassungen)` – Positionen aller Fassungen einer Kalkulation bzw. aller Einträge des Dokuments (ohne den Eintrag an der Stelle $ausser – dessen neue Fassungsliste zählt der …
- `ci_kalk_positionen_gesamt(doc, ausser)`
- `ci_kalk_holen(doc, sendung)` – Kalkulation eines Containers aus dem Dokument [Stelle, Eintrag] oder [null, null]
- `ci_kalk_speichern(doc, sendung, eingabe, rev, grund, me)` – Entwurf speichern.
- `ci_kalk_festschreiben(doc, sendung, rev, container, me)` – Letzte Fassung endgültig festschreiben (GR-106): die Fassung hält dann ihre geprüfte Eingabe (Felder späterer Versionen mit ihrer Vorgabe), ihr Ergebnis …
- `ci_kalk_sicht(k)` – Kalkulation für die Seite: je Fassung Eingabe und Ergebnis (mit den wirksamen Sätzen) – ein Entwurf frisch gerechnet mit den aktuellen Sätzen, eine …
- `ci_kalk_uebersicht(doc)` – Übersicht für den Reiter: je Container Stand und Nummer der letzten Fassung

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
- `schnappschussKarte(id, el)` – Karte einer abgeschlossenen Bewertung: der Stand bringt die Farmer des Schnappschusses ohne Umriss mit, die Umrisse holt erst das Fenster
- `sendungAusFenster()`
- `schlachthofWahlNeu()` – Lieferant im Fenster geändert: zur Wahl stehen nur seine Schlachthöfe; der gewählte bleibt, wenn er dazugehört
- `sendungSpeichern(zusatz)`
- `abschlussOeffnen(id, wiederOeffnen)` – Fenster „Bewertung abschließen“ bzw. „wieder öffnen“
- `abschlussSenden()`

**GeoJSON-Datei und Druck**

- `exportieren(query)`
- `herunterladen(name, blob)` – Datei zum Speichern anbieten (GeoJSON für TRACES, CSV der Kalkulation)
- `drucken(id)`

**Fenster „Unterlagen einlesen“**

- `lesenOeffnen(sendungId)`
- `pdfjs()` – pdf.js vom eigenen Server, erst bei der ersten PDF geladen (Berichte, Vorschau der Dokumente)
- `pdfSeiten(bytes)` – Textstücke einer PDF-Datei mit ihrer Lage, je Seite
- `dateiVorbereiten(datei, gemeinsam)` – Eine gewählte Datei in die Form bringen, die der Server prüft; { fehler } bei Dateien, die sich nicht lesen lassen
- `eingefuegt(w, gemeinsam)`
- `lesenPruefen()`
- `lesenZahl()`
- `lesenUebernehmen()`
- `base64(bytes)` – Bytes als Base64 (in Stücken, damit lange Dateien den Aufrufstapel nicht sprengen)
- `teileHochladen(action, datei, felder, beiTeil, sperre)` – Eine Datei in Teilen an eine Aktion der Dateiablage geben (felder: z. B. sha256, name statt datei.name); beiTeil(data) nach jedem angenommenen Teil.
- `originalAblegen(datei, sha256, lieferant)` – Originaldatei im Eingang des QM-Systems ablegen: '' oder die Fehlermeldung.

**Laden und Ereignisse**

- `laden(still)`
- `themaKnopf()`

## `app/module/containerimport/dokumente.js`

_STAFL-Plattform · Modul Container-Import – Bereich „Dokumente“ im Fenster eines Containers (Auftrag des Inhabers 20.11.2026): alle Unterlagen des Containerordners ablegen – PDF, Word, Excel (auch .xls), E-Mail (.eml, …_

- `vorschlag(name)` – Arten aus dem Dateinamen: die erste passende Regel, sonst keine (der Nutzer wählt)

**Zähler in der Liste der Container**

**Fenster „Container“**

- `nachAktion(d, sid)` – Der eine Weg nach jeder Antwort: Zahlen aller Container, Dateien und Vermerke des Containers sid übernehmen, dann die Liste (Zähler) und den Bereich neu …
- `checkliste(darf)`
- `warteZeile(w, i)`
- `kachel(f, darf)`
- `verlauf()` – Verlauf: Hochladen, Arten geändert, Entfernt, Checkliste – neueste zuerst
- `zeichnen()`

**Mini-Vorschau: erste Seite einer PDF oder das verkleinerte Bild, nur sichtbare, nacheinander**

- `vorschauBeobachten(el)`
- `einsetzen(id)`
- `abarbeiten()`
- `leinwand(b, h)`
- `miniatur(id, art)`
- `pdfSeite(puffer)`
- `bild(blob)` – Bild über eine Blob-Adresse (der Download ist sandbox/nosniff), gezeichnet auf höchstens BREITE Punkte

**Warteschlange und Hochladen**

- `aufnehmen(dateien)` – Gewählte Dateien in die Warteschlange des Containers sid; wechselt der Container während der Prüfsummen, bricht es ab (die Warteschlange gehört dem vorigen …
- `hochladen()` – Dateien nacheinander in Teilen (ohne Eingabesperre: der Container bleibt bedienbar); beendete Sitzung → Anmeldung

**Arten ändern, Entfernen, Checkliste**

- `senden(action, body, erfolg)`

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

## `app/module/containerimport/eudr-geodaten.js`

_STAFL-Plattform · Container-Import · EUDR – Geodaten-Katalog: die offene Metadatenbank GEOS-EUDR des Thünen-Instituts (MIT-Lizenz, https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR) beschreibt …_

- `links(liste)`
- `sicht()`
- `fenster(id)` – Fenster mit einem Eintrag (aus einem Verweis, auch über dem Fenster „Farmer“)
- `beleg(ids)` – „GEOS-EUDR-Katalog (Thünen-Institut) ForestCover_TreeExtent v1.0: FNF01, FNF17“ – je Thema mit seiner Fassung

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

- `deuten({…}, abHa, quellen)`

## `app/module/containerimport/kalkulation.js`

_STAFL-Plattform · Modul Container-Import – Reiter „Kalkulation“ (Auftrag des Inhabers 20.11.2026)_

- `standText()` – Stand in einem Satz (Druckkopf, erste Zeile der CSV)
- `antwortOk(r, fallback)`

**Reiter: Liste der Container**

- `startLaden()`
- `zeichnen()`

**Container öffnen, neue Eingabe**

- `oeffnen(id)`
- `zeigeFassung(nr)`
- `neueEingabe()`

**Eingabe**

- `editor()`
- `lesen()` – Eingabe aus den Feldern (Zahlen als Text – der Server liest auch „1.234,5“)
- `geaendert(neuZeichnen)`
- `rechnen()`

**Ergebnis**

- `hinweise(erg)`
- `ergebnis()`

**Speichern, Fassungen**

- `speichern()`
- `nachSpeichern(d)`
- `festschreiben()`

**CSV und Druck**

- `csv()`
- `druckInhalt()` – Druckfassung in #ci-druck als eigener Block .kk-druck (A4 quer); false ohne Ergebnis
- `drucken()`

**Ereignisse**

- `geaendertStruktur()`

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

- `kamm(zacken)` – Umriss mit vielen sich überlappenden Kanten (dünne, schräge Zacken) – ohne echte Selbstüberschneidung, aber quadratisch teuer zu prüfen (erfundene …
- `kreis(punkte, mitte, radius)` – Gutartiger Umriss gleicher Größe (Gegenprobe zum Kamm).
- `flaechen(umrisse)`

**Sendung und Betriebe speichern**

- `stand(c)`
- `profil(s)`
- `betrieb(name)`

**Eigene Gegenprüfung**

**Abschluss**

- `punktzahl(g)`
- `gespeicherte_sendung(i)`

**Oberfläche**

- `png(punkt)` – PNG mit 512 × 512 Bildpunkten, punkt(x, y) → (R, G, B, A)
- `kartendienste(abrufe, ohne, verlust)` – Antwortet wie die drei Dienste, mit CORS-Freigabe: Kacheln der Karte als Testbild; für die Bildauswertung die Muster (Wald als WMS mit 512 Punkten, Verlust …
- `antwort(route)`
- `seite(user, vp, schema, dienste)`
- `kartendatei(route)`

**Originale im QM-System (Schnittstelle qs_eingang_hochladen)**

- `original(c, name, inhalt, lieferant, teil)` – Datei in Teilen an containerimport_eudr_original geben; Antwort des letzten Aufrufs.

## `tests/e2e/test_containerimport_dokumente.py`

_Container-Import: Dokumente je Container (app/api/module/containerimport/dokumente.php, Oberfläche dokumente.js; Auftrag des Inhabers 20.11.2026)._

**selbst erzeugte Beispieldateien (kein echter Inhalt)**

- `pdf(seiten, text, fuellen)` – Gültige PDF mit Text und farbiger Fläche je Seite; fuellen = Bytes eines unbenutzten Datenstroms (große Datei)
- `ooxml(teil, text)`
- `ole(merkmal, n)`
- `png(breite, hoehe)`
- `eml()`
- `hochladen(cli, sendung, name, inhalt, arten, teil, sha)` – In Teilen hochladen wie die Oberfläche → (Status, Antwort des letzten Aufrufs, Zahl der Aufrufe)
- `roh(cli, query)`
- `blobs()`
- `teile_reste()`
- `liste(cli, sid)`

**Rechte**

**alle Dateiarten des Containerordners**

**falsche und getarnte Arten**

**Checkliste**

**Arten ändern**

**Entfernen**

**Leser, Download**

**ZIP**

**GR-106, Rückfall, Sicherung**

**Bilder, Namen im ZIP, CSV-Injection, fremde Uploads, Zahlen-Dokument**

**Oberfläche**

- `vorschlag(name)`

## `tests/e2e/test_containerimport_farmer.py`

_Container-Import: Farmer je Container (Auftrag des Inhabers 19.11.2026) – eigene fortlaufende Farmer-Nummer neben der Nummer aus den Papieren (Kennung), Farmer über die Nummern aus den Papieren einem Container …_

- `farmer(name, kennung, x, land, y, **mehr)` – Farmer mit kleinem Umriss (Westecke x/y) und Nummer aus den Papieren.
- `betrieb(name, r)`
- `speichern(*betriebe, sendung)`

**Eigene Farmer-Nummer, Nummer aus den Papieren**

- `ort(name, kennung, x)`

## `tests/e2e/test_containerimport_geodaten.py`

_Container-Import · EUDR_

**Rechte und Aufbau der echten Datei**

**Oberfläche**

- `seite(user, vp, schema, katalog)` – Seite mit erfundenem Katalog: die Seite lädt ihn erst bei Bedarf, die Umleitung greift also vor dem ersten Abruf.
- `katalog_zeigen(p)`

## `tests/e2e/test_containerimport_hafen.py`

_Container-Import · Tracking: bestätigte Ankunft in Hamburg aus der öffentlichen Liste „Expected vessels“ von Hafen Hamburg (app/api/module/containerimport/hafen.php, Aktion containerimport_tracking_hafen, Anzeige in …_

- `im_format_der_seite(n)`
- `ankunft(n, uhr)` – Ankunft, wie der Server sie ablegt: Ortszeit Hamburg mit Zeitzone.

**nachgebaute Seite des Hafens**

- `log_message(*a)`
- `roh(bytes_)` – Antwort Byte für Byte selbst schreiben (für Modi, die send_response nicht abbilden kann).
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

## `tests/e2e/test_containerimport_kalkulation.py`

_Container-Import: Kalkulation je Container (Aktionen containerimport_kalkulation_*, app/api/module/containerimport/kalkulation.php, Oberfläche app/module/containerimport/kalkulation.js)._

- `laden(client, c)`
- `speichern(c, rev, eingabe, **mehr)`

**Rechte**

**Rechnen**

**Entwurf, Revision, Festschreiben, Fassungen**

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

## `tests/unit/test_ci_kalkulation.py`

_Rechenkern der Kalkulation je Container (app/api/module/containerimport/kalkulation.php) gegen von Hand nachgerechnete Erwartungen – jede Formel einzeln, mit erfundenen Zahlen (GR-007)._

- `check(name, ok, info)`
- `rechnen(eingabe, saetze)`
- `nahe(a, b, eps)`
- `texte(r, stufe)`

**Grundfall**

- `fall(**aenderung)` – Kopie des Grundfalls mit Änderungen: kopf={…}, pos={stelle: {…}}, teile=[…], positionen=[…], ueberschrieben={…}

**Provision im Zollwert**

**Unvollständig**

**Teil und Position ohne Gewicht**

**VK vollständig → Gesamtertrag**

**Gekühlt / gefroren, EU-Ursprung, falsche Länder, Stichtag**

- `fehler_an(r, pos, text)` – unvollständig (nicht festschreibbar) mit genau diesem Fehler an der Position

## `tests/unit/test_eudr_geodatenkatalog.py`

_Geodaten-Katalog des Container-Imports (werkzeuge/eudr_geodatenkatalog.py) – ohne Netz, mit einer kleinen erfundenen Tabelle im Aufbau der Metadatenbank GEOS-EUDR (tests/fixtures/containerimport/geodatenkatalog/). …_

- `ok(name, cond, info)`
- `lauf(*args)` – Werkzeug aufrufen → (Exit-Code, Fehlerausgabe).
- `abbruch(name, dateiname, aendern, erwartet)`

## `werkzeuge/eudr_geodatenkatalog.py`

_Übernimmt eine Fassung der offenen Metadatenbank GEOS-EUDR (Thünen-Institut, MIT-Lizenz) in den Geodaten-Katalog des Container-Imports (app/api/module/containerimport/geodatenkatalog.json)._

- `text(roh)` – Zelle als Text: Tabulatoren und Mehrfach-Leerzeichen weg, Aufzählungspunkte je auf eine eigene Zeile; leer → None.
- `verweise(roh)` – Verweise einer Zelle → [{text, url}]; text ist die Beschriftung vor der Adresse („V2 ->“ → „V2“), Rest am Ende hängt an der letzten.
- `beschriftung(stueck)`
- `eintrag(zeile, thema, nr)`
- `lesen(pfad)` – Tabelle eines Themas → (Thema mit Version, Einträge).
- `main(argv)`
