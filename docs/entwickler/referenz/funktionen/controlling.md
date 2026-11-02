# Funktionen: Controlling (`controlling`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

17 Dateien, 257 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/module/controlling/arbeitszeit.php`

_Controlling · Bereich Arbeitszeit (Auftrag des Inhabers 02.11.2026)_

**Werte lesen**

- `az_minuten(v)` – „HH:MM“ bzw. „-HH:MM“ (auch über 24 Stunden) oder Excel-Bruchteil eines Tages → Minuten; leer → null; ungültig → false
- `az_uhrzeit(v)` – Uhrzeit eines Stempels „HH:MM“ (00:00–23:59) bzw. Excel-Bruchteil → „HH:MM“; leer → null; ungültig → false
- `az_datum(v)` – Datum „TT-MM-JJJJ“, „TT.MM.JJJJ“, „JJJJ-MM-TT“ oder Excel-Seriennummer → „JJJJ-MM-TT“; ungültig → null
- `az_text(v, max)`
- `az_person_id(nr, name)` – Schlüssel eines Mitarbeiters: Personalnummer, sonst Name (klein) – als kurze, unveränderliche Kennung
- `az_fehler(t)` – Stempelfehler eines Tages (ohne „laufend“)

**Zeitbericht lesen (Importzentrale: daten = { blaetter: [{ name, grid }] })**

- `az_zeitbericht(e)` – Ergebnis: tage (Schlüssel „pid\|JJJJ-MM-TT“ → Tag), personen (pid → name, nr, abt), von, bis, fehler (Zeilen), zeilen (gelesen)
- `az_tag_speichern(t, laufend)` – Gespeicherte Form eines Tages: [Soll, Ist, Abwesenheit, Pause, Saldo, Stempel, Fehler, laufend] (Minuten)

**Speicher**

- `az_index()`
- `az_jahr_lesen(jahr)`
- `az_tag(d)`
- `az_anzahl(n)`
- `az_stunden(min)`
- `az_vergleich(in)` – Vergleich Datei ↔ gespeichert im Zeitraum der Datei: je Tag neu/geaendert/unveraendert, gespeicherte Tage ohne Gegenstück entfallen

**Importzentrale**

- `arbeitszeit_import_vorschau(e, me)`
- `arbeitszeit_import_uebernehmen(e, me)`

**Auswertung**

- `az_grunddaten(me)` – Grunddaten: Stand, Jahre, Abteilungen, Mitarbeiter (für Filter und Suche), Fehlerarten
- `az_anfrage(q, index)` – Anfrage: von/bis „JJJJ-MM“ (Standard: Jahr des jüngsten Tages), abt (kommagetrennt, „_“ = ohne Abteilung), p (Mitarbeiter)
- `az_tage(a, index)` – Tage des Zeitraums mit Filter: liefert [pid, datum, tag]
- `az_leer()`
- `az_addieren(s, t)`
- `az_auswertung(q, me)` – Auswertung: Summen, Monate, je Mitarbeiter, je Abteilung, Stempelfehler (alle Werte in Minuten)
- `az_detail(q, me)` – Pop-up: alle Tage eines Mitarbeiters im Zeitraum (?p=…&von&bis)

## `app/api/module/controlling/bestand.php`

_Controlling · Bereich Bestandsverlauf (Auftrag des Inhabers 02.11.2026)_

- `ctl_bestand_darf_ek(me)`
- `ctl_bestand_tagnr(d)`
- `ctl_bestand_datum(n)`
- `ctl_bestand_gueltig(v)`
- `ctl_bestand_merkmal(dim, code)` – Merkmal eines Artikels (Nummer wie in der Bestandsliste) für Filter und Gliederung
- `ctl_bestand_anfrage(q, tage)` – Anfrage prüfen: Zeitraum (tage=30\|90\|365 oder von/bis), Gliederung, Filter
- `ctl_bestand_umsatz_bis(index)` – Letzter Tag mit Umsatzdaten (JJJJ-MM-TT) oder null
- `ctl_bestand_bezeichnung(nach, key, code, listenname)` – Bezeichnung einer Zeile: Artikel nach den Stammdaten (sonst Name aus der Liste), Gruppen mit Namen
- `ctl_bestand_kennzahlen(r, listen, absatz, absatzTage, ek)` – Kennzahlen aus den Summen einer Zeile (bzw. aller Zeilen)
- `ctl_bestand_spark(kg, n)` – Mini-Verlauf: höchstens CTL_BESTAND_SPARK Punkte, gleichmäßig über die Listen
- `ctl_bestand_auswertung(q, me)` – Auswertung (Aktion controlling_bestand): Stand, Zeitraum, Summen, Tagesreihen und Zeilen der Gliederung
- `ctl_bestand_detail(q, me)` – Detail (Aktion controlling_bestand_detail): ein Artikel, eine Artikelgruppe oder Fleischart (?dim=…&wert=…) im Zeitraum der Seite – Kennzahlen und je Liste …
- `ctl_bestand_grunddaten(me)` – Grunddaten (Aktion controlling_bestand_daten): Stand des Verlaufs, Rechte, Auswahllisten für die Filter (nur Nummern und Namen)

## `app/api/module/controlling/controlling.php`

_Modul Controlling · gemeinsame Grundlage aller Bereiche (Umsatzstatistik; geplant_

- `controlling_bereiche(me)` – Bereiche, die dieser Mitarbeiter sehen darf, mit Bearbeitungsrecht (nur Anzeigehilfe – jede Aktion prüft selbst)
- `controlling_jahr(v)` – Jahr aus der Anfrage (2000–2100) als Text „JJJJ“

## `app/api/module/controlling/import.php`

_Importvertrag des Controllings – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md)._

- `import_arten_controlling()`

## `app/api/module/controlling/kundenbild.php`

_Controlling · Kundenbild – Schnittstelle für das CRM (GR-101; Leser „crm“ in regeln/datenverantwortung.toml)._

- `kundenbild_datum(t)` – Tagnummer → Datum (JJJJ-MM-TT)
- `kundenbild_vorjahr(d)` – Gleicher Tag ein Jahr früher (29.02. → 28.02.)
- `kundenbild_lesen(nur, mitArtikeln)` – Umsatzzeilen der zwei Jahre bis zum Stand zusammenfassen – je Kunde und (auf Wunsch) je Kunde und Artikel.
- `kundenbild_tage(set, von, bis)` – Kauftage (Tagnummern, aufsteigend) eines Bereichs
- `kundenbild_signale(k, L)` – Signale eines Kunden (Liste): pause, weniger, weg (Artikel), neu – mit Zahlen (Cent bzw. Tausendstel kg); das CRM blendet aus, was der Mitarbeiter nicht …
- `kundenbild_erster(tage, L)` – Erster Kauf, wenn er „neu“ ist: in den letzten 91 Tagen, die 365 Tage davor kein Kauf – und die Daten reichen so weit zurück (sonst wäre jeder Kunde am …
- `kundenbild_artikel_name(nr)` – Name und Fleischart eines Artikels aus den Artikelstammdaten (ohne Stammsatz „Artikel <Nr>“)
- `kundenbild_artikel_weg(k, L)` – Artikel, die der Kunde nicht mehr kauft (Regel oben), meistgekaufte (Umsatz der 365 Tage) zuerst
- `kundenbild_monate(stand)` – Monate (JJJJ-MM) der letzten 12 Monate bis zum Monat des Stands
- `kundenbild_zusammenfassung(k, L, mitSignalen)` – Kennzahlen eines Kunden für Cockpit und Liste: Fenster als [Umsatz, Menge], 12 Monate, letzter Kauf, Kauftage, Signale
- `kundenbild_kunden(nur)` – Cockpit: alle Kunden bzw. nur $nur (Kundennummern) mit Kennzahlen und Signalen.
- `kundenbild_kunde(nr)` – Kunden-Pop-up: ein Kunde mit Kennzahlen (365 Tage mit Vorjahr), Monaten mit Vorjahr, Rhythmus, Preisniveau, Top-Artikeln und „Auffällig bei Artikeln“ (nicht …

## `app/api/module/controlling/umsatz.php`

_Controlling · Bereich Umsatzstatistik, Reiter „Monatsmeldung“_

- `controlling_umsatz_jahre(index)` – Jahre mit importierten Umsätzen (neueste zuerst)
- `controlling_umsatz_vertreter(mitUmsatz)` – Vertreter für die Oberfläche: aktuelle aus den Stammdaten, dazu Nummern mit Umsatz, die dort nicht (mehr) stehen, und „ohne Vertreter“ (Nummer „_“), wenn es …
- `controlling_umsatz_jahr(index, jahr, ek)` – Kg, Umsatz und DB je Monat und Vertreter eines Jahres aus den Umsatzdaten: { "MM": { "<Vertreter>": { kg, umsatz, db } } }
- `controlling_umsatz_antwort(me, jahrRoh)` – Antwort für die Oberfläche: ein Jahr (Anfrage ?jahr=JJJJ, sonst das jüngste mit Umsatzdaten)

## `app/api/module/controlling/umsatzauswertung.php`

_Controlling · Umsatzauswertung aus den importierten Umsatzdaten (module/controlling/umsatzdaten.php)._

- `umsatz_stamm()` – Stammdaten für Zuordnung und Namen (nur lesend, Eigentümer Verwaltung)
- `umsatz_kunde(nr)`
- `umsatz_artikel(nr)`
- `umsatz_wert(v)`
- `umsatz_merkmal(dim, kunde, artikel)` – Merkmal eines Kunden bzw. Artikels für Filter und Gliederung
- `umsatz_anfrage(q, stand)` – Anfrage prüfen: Zeitraum, Gliederung, Vorjahr, Filter (kommagetrennt)
- `umsatz_monat_plus(m, n)`
- `umsatz_zeitschluessel(nach, m, tag, verschieben)` – Schlüssel einer zeitlichen Gliederung; $verschieben: Vorjahreswert dem Schlüssel des laufenden Jahres zuordnen
- `umsatz_leer()`
- `umsatz_zaehlen(a, index, von, bis, verschieben, bisTag, ziel, reihe, kunden, artikel)` – Zeilen eines Zeitraums zusammenzählen.
- `umsatz_summe(reihe)` – Summe über alle Monate der Reihe
- `umsatz_bezeichnung(nach, k)` – Name und Zusatz einer Zeile der Gliederung
- `umsatz_darf_ek(me)` – Einkaufswerte und Deckungsbeitrag: eigenes Recht des Controllings UND das EK-Recht (GR-008)
- `umsatz_werte(r, ek)` – Kennzahlen für die Antwort: ohne EK-Recht ohne EK-Wert und Umsatz mit EK
- `umsatz_rang_wert(w, rang)` – Wert einer Zeile für die Rangliste (null: keine Spanne, weil kein Umsatz mit EK)
- `umsatz_rang_sortieren(zeilen, rang, auf, schwelle, basis)` – Zeilen nach der Kennzahl ordnen (höchste zuerst, $auf: niedrigste zuerst); Spanne: Zeilen unter der Schwelle (Umsatz mit EK) und ohne Umsatz mit EK am Ende …
- `umsatz_abc(zeilen, rang)` – ABC-Klasse je Zeile (Feld „abc“) und Zusammenfassung [A\|B\|C => [anzahl, anteil]]; null, wenn die Kennzahl keine Summe ist
- `umsatz_auswertung(q, me)` – Auswertung: Gliederung mit Vorjahr, Monatsreihe, Summen

**Detail für die Pop-ups der Umsatzstatistik**

- `umsatz_detail_addieren(r, z, datum)`
- `umsatz_detail_zaehlen(a, index, von, bis, verschieben, bisTag, mitTagen, vergleichOhne)` – Summen eines Zeitraums je Monat, Kunde, Artikel und (auf Wunsch) Liefertag; $verschieben/$bisTag wie umsatz_zaehlen().
- `umsatz_detail_liste(nach, jetzt, vj, ek)` – Liste der Kunden bzw. Artikel des Details: umsatzstärkste zuerst, nur mit berechneten Positionen (sonst nur Leergut)
- `umsatz_detail(q, me)`

**Bestellpausen (Frühwarnung)**

- `umsatz_tagnummer(datum)` – Tageszahl eines Datums (für Abstände in Tagen)
- `umsatz_pause_pruefen(tage, ende)` – Bestellpause eines Kunden zum Tag $ende (Regel oben; auch Schnittstelle für das CRM, module/controlling/kundenbild.php).
- `umsatz_pausen(q)` – Stammkunden mit auffälliger Bestellpause zum Stichtag; Anfrage wie die Auswertung (von, bis, Filter)
- `umsatz_grunddaten(me)` – Grunddaten der Auswertung: Stand der Daten, Rechte, Auswahllisten (nur Nummern und Namen)

## `app/api/module/controlling/umsatzdaten.php`

_Controlling · Umsatzdaten aus der Warenwirtschaft (Kundenumsatztabelle_

- `umsatzdaten_index()` – Verzeichnis mit Standardwerten; unbekannte (neuere) Felder bleiben erhalten (GR-006)
- `umsatzdaten_monat(m)` – Zeilen eines gespeicherten Monats (leer, wenn es ihn nicht gibt)
- `umsatzdaten_hash(zeilen)` – Prüfsumme der Zeilen – identisch mit JSON.stringify im Browser (nur Ganzzahlen und ASCII-Nummern)
- `umsatzdaten_monat_gueltig(m)`
- `umsatzdaten_tage(m)`
- `umsatzdaten_datum(v)`
- `umsatzdaten_monatsfolge(von, bis)` – Monate von … bis (je „JJJJ-MM“, einschließlich)
- `umsatzdaten_schluessel_kleiner(a, b)` – Reihenfolge der Zeilen: Tag, Kunde, Artikel, berechnet (0 vor 1) – streng steigend, also ohne Doppelte
- `umsatzdaten_sortieren(z)`
- `umsatzdaten_zeilen_pruefen(m, zeilen)` – Zeilen eines Monats aus dem Browser prüfen (jede Zahl ganzzahlig, Nummern wie in der Warenwirtschaft)
- `umsatzdaten_summen(zeilen)` – Kennzahlen eines Monats (für Verzeichnis und Vorschau)
- `umsatzdaten_tagesbereich(zeilen, von, bis, innen)` – Zeilen eines Monats im Tagesbereich [von, bis] bzw. außerhalb
- `umsatzdaten_eingabe(e)` – Zusammenfassung des Lesers (daten der Vorschau und Übernahme) prüfen
- `umsatzdaten_vergleich(in, index)` – Vergleich der Datei mit dem gespeicherten Stand je Monat im Zeitraum der Datei: neu (bisher keine Umsätze), geaendert (andere Prüfsumme), unveraendert, …
- `umsatzdaten_monatsname(m)`
- `umsatzdaten_euro(cent)`
- `umsatzdaten_anzahl(n)`
- `umsatzdaten_zahlwort(n, eins, viele)`
- `umsatzdaten_tag(d)`
- `umsatzdaten_unbekannt(in)` – Nummern ohne Stammsatz (Hinweis in der Vorschau): Kunden der Verwaltung, Artikelstammdaten
- `umsatzdaten_import_vorschau(e, me)` – Vorschau für die Importzentrale (Vertrag: docs/plattform/schnittstellen/import.md)
- `umsatzdaten_import_teil(e, me)` – Ein Monat in die Zwischenablage (Importzentrale: import_teil).
- `umsatzdaten_teile_aufraeumen(upload)` – Zwischenablage aufräumen: Teile dieses Imports bzw. alle, die älter als UMSATZDATEN_TEIL_STUNDEN sind
- `umsatzdaten_import_uebernehmen(e, me)` – Übernahme: neue und geänderte Monate aus der Zwischenablage schreiben, entfallene löschen, Verzeichnis neu, Protokoll
- `umsatzdaten_stand(index)` – Stand der Umsatzdaten für die Oberfläche (ohne Beträge): Monate, erster und letzter Tag, letzte Importe

**Schnittstelle für andere Module (GR-101; Leser „crm“ in regeln/datenverantwortung.toml)**

- `umsatzdaten_kaeufer(artikel, von, bis)` – Käufer von Artikeln vom Tag $von bis $bis (JJJJ-MM-TT): je Artikel und Kunde Menge (Tausendstel, berechnete Positionen einschließlich Gutschriften), Käufe …
- `umsatzdaten_artikelliste()` – Artikel in den Umsatzdaten mit Namen aus den Artikelstammdaten (Nummer => Name; ohne Stammsatz „Artikel <Nr>“)

## `app/module/controlling/arbeitszeit.js`

_STAFL-Plattform · Controlling · Bereich Arbeitszeit (Auftrag des Inhabers 02.11.2026)_

**Formate (Werte in Minuten)**

**Gerüst**

- `anfrage(extra)`
- `laden()`

**Darstellung**

- `standText()`
- `kachel(name, wert, sub, extra)`
- `kennzahlen()`
- `verlauf()`
- `sortiert(liste)`
- `personenHtml()`
- `abteilungenHtml()`
- `fehlerHtml()`
- `liste()`
- `zeichne()`
- `listeNeu()`

**Pop-up: Tage eines Mitarbeiters**

- `detailOeffnen(pid)`

**CSV der Liste**

- `csv()`

**Ereignisse**

- `letzterMonat()` – jüngster vollständig importierter Monat: endet der Zeitbericht vor dem Monatsende, der Monat davor
- `verbinden()`

## `app/module/controlling/bestand.js`

_STAFL-Plattform · Controlling · Bereich Bestandsverlauf (Designvorschlag 02.11.2026)_

**Formate**

**Diagramm: Bestand je Liste (Linie, Punkte), darunter Absatz je Tag (Balken)**

- `schritt(spanne)`
- `diagramm(reihe, absatzReihe, z, wert, breite, H)`
- `spark(werte)`

**Gerüst**

- `anfrage(extra)`
- `laden()`

**Darstellung**

- `standText()`
- `kachel(name, wert, sub, extra)`
- `kennzahlen()`
- `entwicklung()`
- `sichtbareZeilen()`
- `zeilenHtml()`
- `liste()`
- `zeichne()`
- `diagrammZeichnen()`
- `chips()`

**Filter (Pop-up)**

- `filterOeffnen()`

**Detail (Pop-up)**

- `detailOeffnen(key)`
- `detailZeichnen(dlg)`

**CSV der Liste**

- `csv()`

**Ereignisse**

- `verbinden()`

## `app/module/controlling/controlling.js`

_STAFL-Plattform · Controlling – Grundgerüst der Seite_

- `api(action, body, query)` – Aufruf der API: wirft nie, liefert { status, data, json }
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`

**Hell/Dunkel**

- `themaKnopf()`

**Bereiche**

- `zeigeBereich(id)`

**Start**

- `laden()`

## `app/module/controlling/umsatz-auswertung.js`

_STAFL-Plattform · Controlling · Umsatzstatistik, Reiter „Auswertung“_

**Formate (auch für die Pop-ups)**

- `rangSortieren(liste, rang, auf)` – Liste nach Kennzahl ordnen (für die Pop-ups; die Rangliste der Seite ordnet der Server); setzt z.klein bei Spanne
- `csvLaden(datei, zeilen)`
- `monatsSvg(mon, k, mitVj, platz, H)` – Monatsbalken (Umsatz, Menge oder DB) mit Vorjahrespunkten als SVG – Seite und Pop-up

**Gerüst**

- `geruest()`

**Filter: Chips auf der Seite, Pop-up zum Wählen**

- `zeichneFilter()`
- `filterDialog()`
- `zeichneEntwurf()`
- `filterVerbinden()`
- `anfrage(extra)`
- `filterText(ohneDim)` – Text der aktiven Filter (ohne das Merkmal des Pop-ups)

**Suche: Kunde, Artikel, Vertreter, Kundengruppe, Artikelgruppe → Pop-up**

- `suchen(text)`
- `trefferWaehlen(i)`

**Laden und Zeichnen**

- `laden()`
- `pausenLaden()` – Bestellpausen zum Ende des Zeitraums mit den Filtern der Seite – nur neu laden, wenn sich Zeitraum oder Filter ändern
- `zeichnePausen()`
- `vjText()`
- `zeichneKennzahlen()` – Vier Kennzahlen (ohne EK-Recht drei): Umsatz, Menge mit Ø Preis, DB mit Spanne, Kunden – Einzelheiten im Hinweis
- `zeichneVerlauf()`
- `spalten()` – Spalten der Tabelle „Alle Spalten“ (ohne EK-Recht ohne DB)
- `sortiert()`
- `rangNebenwert(w, rang)` – Zweite Angabe unter dem Wert: was zur Kennzahl gehört (Umsatz zur Menge, Spanne zum DB …)
- `zeichneRangliste()`
- `zeichneRangfilter()` – Auswahl über der Rangliste: Alle · Neu · Verloren (mit Vorjahr, nicht bei Zeit) und ABC-Analyse der Kennzahl
- `zeichneTabelle()`
- `zeichneVeraenderung()` – Größte Veränderungen: je drei Zeilen mit dem größten Plus und Minus in der Kennzahl der Rangliste (Spanne → DB in Euro; nur Merkmale, nicht Zeit)
- `zeichneListe()`
- `zeichneZeitraum()`
- `zeichne()`

**Bedienung**

- `zeitraum(von, bis)`
- `gliederung(nach)`
- `rangliste(rang, auf)`
- `zeileGewaehlt(schluessel)` – Klick auf eine Zeile: Merkmal → Pop-up; Monat/Quartal/Jahr → dieser Zeitraum
- `details(dim, wert)`
- `csv()`
- `verbinden()`

**Ansicht merken (je Mitarbeiter im Browser; nur Bedienkomfort, ohne Speicher gilt die Standardansicht)**

- `ansichtJetzt()`
- `merken()`
- `gemerktUebernehmen()` – Gemerkte Ansicht übernehmen – nur gültige Werte (Gliederung, Kennzahl mit Recht, vorhandene Filterwerte, Monate mit Daten)
- `standardansicht()`
- `anzeigen(box)`

## `app/module/controlling/umsatz-details.js`

_STAFL-Plattform · Controlling · Umsatzstatistik_

- `oeffnen(dim, wert, ctx, neu)`

**Bausteine**

- `kachel(name, wert, sub, voll)`
- `kennzahlen()`
- `sortierwahl()` – Sortierung der Listen: Kennzahl (DB nur mit EK-Werten) und Richtung
- `kundenListe()` – Kunden einer Gruppe bzw. Käufer eines Artikels (mit EK-Recht mit DB je Kunde)
- `artikelBalken()` – Meistgekaufte Artikel (Gruppe, Vertreter …)
- `kundeArtikel()` – Kunde: seine Artikel
- `preisniveau(liste)` – Preisniveau des Kunden: was er gezahlt hat gegenüber dem Ø Preis aller Kunden für dieselben Mengen (nur Artikel mit Menge)
- `kundeLieferungen()`
- `zeichne()`
- `zeichneListe()` – Nur die Liste neu zeichnen (Suche, alle anzeigen, Reiter) – Eingabefeld behält den Fokus
- `csv()`
- `verbinden(dlg)`

## `app/module/controlling/umsatz-import.js`

_STAFL-Plattform · Controlling · Leser der Importart „umsatzdaten“ (Verwaltung → Import, window.WA.importLeser)._

- `felder(z)` – Felder einer CSV-Zeile (Semikolon, Anführungszeichen mit "" als Maskierung)
- `festkomma(s, stellen)` – Deutsche Zahl („1.347,25“, „-12“, „317,000“) als Ganzzahl in 10^-stellen; leer → null; ungültig → NaN
- `datum(s)` – „TT.MM.JJJJ“ → [JJJJ-MM, Tag] oder null
- `sha256(text)`
- `dekodieren(buf)`
- `lesen(dateien)`

## `app/module/controlling/umsatz.js`

_STAFL-Plattform · Controlling · Bereich Umsatzstatistik, Reiter „Monatsmeldung“_

**Gerüst des Bereichs**

**Filter**

- `jahre()` – Jahre mit importierten Umsätzen (ohne Daten: das laufende Jahr)
- `zeichneJahre()`
- `zeichneMonatsfilter()`
- `zeichneVertreterfilter()`

**Übersicht**

- `zeichneKennzahlen(monate, auswahl)`
- `zeichneVertreter(monate, auswahl)`
- `liniendiagramm(monate, k, auswahl, summen)`
- `zeichneMonate(monate, auswahl)`
- `zeichneUebersicht()`
- `zeigeTab(tab)`

**Laden**

- `setzeDaten(d)`
- `jahrLaden(jahr)` – Ein Jahr vom Server laden (die Werte rechnet der Server aus den Umsatzdaten)
- `anzeigen(box, rechte, tab)`

## `tests/e2e/test_controlling.py`

_Controlling (Modul controlling, Oberfläche controlling.intern unter /module/controlling/) – Bereich Umsatzstatistik, Reiter Monatsmeldung_

- `check(n, c, i)`
- `dokument(name)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe, ziel)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe)`
- `az_zeile(vor, nach, datum, k, g, soll, ist, saldo, nr, abt, abw, pause, bemerkung)`
- `zb(cl, daten, stand)`
- `text(pg, sel)`
- `neu(breite, thema, ip)`

## `tests/e2e/test_controlling_umsatzdaten.py`

_Controlling · Umsatzdaten der Warenwirtschaft_

> Testdaten: Vertreter V1 Vera Vertrieb, V2 Viktor Verkauf; Kundengruppen 10 Gastronomie, 20 Großhandel; Artikelgruppen 100 Rind und Kalb, 200 Schwein. Kunden 2000001 Gasthaus Eiche (V1, 10), 2000002 Handel Nord (V1, 20), 2000003 Kantine Süd (V2, 10), 2000004 Imbiss Ohne (ohne Vertreter und Gruppe), 2000005 ohne Stammsatz; Artikel 40100 Rinderhüfte, 40200 Schweinenacken, 40300 Kalbsrücken, 40400 ohne Stammsatz, 1 E2-Kiste (Leergut, ohne Berechnung). Positionen zufällig mit festem Startwert (positionen(): rund 4 % Gutschriften, 15 % ohne EK, 2 % doppelt). Importe nacheinander: POS_A 02.01.2025–30.10.2026; POS_B ersetzt 10.–20.10.2026 (Menge ×2, ohne 2000005); POS_C ersetzt März 2025 durch ein Drittel, April 2025 entfällt; POS_E ersetzt Juni 2026 (2000004 nur eine Gutschrift = verloren, 2000003 nur jede vierte Position); im Browser POS_D 01.09.–30.10.2026 (Menge ×1,5). POS_JETZT ist jeweils der gespeicherte Stand – Grundlage aller unabhängigen Rechnungen (erwartet(), letzte(), kaeufer(), abc_soll()). Nutzer: ina (importieren), sam (ansehen), eka (beide EK-Rechte), ede und bea (je nur eines), olaf (ohne).

- `check(n, c, i)` – Prüfung festhalten und als PASS/FAIL ausgeben (bei FAIL mit Ist-Wert).
- `dokument(name)` – Gespeichertes Dokument direkt aus der Speicherschicht (None = fehlt).
- `de(v, stellen)` – Zahl im deutschen Format wie die Warenwirtschaft („1.347,25“)
- `positionen(von, bis, faktor, ohne_kunden)` – Zufällige Positionen (Datum, Kunde, Artikel, Kolli, Menge, Preis, Betrag, EK) an Werktagen; Gutschriften, ohne EK, doppelt, Leergut.
- `csv_text(pos, kaputt)` – Kundenumsatztabelle wie aus der Warenwirtschaft (Belegköpfe, Leerzeile, kaputt = Zeilen mit ungültigem Datum).
- `cent(v)` – Euro → Cent (gerundet).
- `milli(v)` – Menge → Tausendstel (gerundet).
- `lesen(pos)` – Unabhängige Zusammenfassung wie der Leser (umsatz-import.js): je Monat sortierte Zeilen, Prüfsumme, Kennzahlen.
- `erwartet(pos, von, bis, dim, filt, bis_tag)` – Umsatz (Cent) je Gliederung aus den Positionen gerechnet (unabhängig vom Server)
- `pruefen(cl, daten, upload, **extra)` – Vorschau des Imports (import_pruefen).
- `teil(cl, monat, daten, upload)` – Einen Monat als Teil übertragen (import_teil).
- `uebernehmen(cl, daten, stand, upload)` – Import übernehmen (import_uebernehmen).
- `auswertung(cl, **q)` – controlling_umsatz_auswertung mit Anfrage q → (Status, Antwort).
- `je(r)` – Umsatz je Zeile der Rangliste {Schlüssel: Cent}.
- `kaeufer(pos, von, bis, dim)` – Merkmale mit Kauf (berechnete Position mit Menge > 0) im Zeitraum
- `abc_soll(werte)` – A: die größten bis 80 % (die Zeile über der Grenze zählt noch mit), B bis 95 %, Rest C; Werte ≤ 0 sind C
- `pausen_soll(pos, stichtag, filt)` – Stammkunden (≥ 4 Kauftage in 182 Tagen bis zum Stichtag) mit Pause ≥ 7 Tage, ≥ 2 × Ø Abstand und länger als jede frühere Pause
- `pausen(cl, **q)` – controlling_umsatz_pausen mit Anfrage q → (Status, Antwort)
- `pausen_gleich(r, soll)` – Antwort der Bestellpausen = unabhängig gerechnet (Monatsumsatz auf 1 Cent genau), Reihenfolge nach Monatsumsatz
- `detail(cl, **q)` – controlling_umsatz_detail (Pop-up) mit Anfrage q → (Status, Antwort).
- `letzte(pos, von, bis, nach, filt)` – Letzter Kauf (berechnete Position mit Menge > 0, keine Gutschrift) je Kunde bzw. Artikel (unabhängig gerechnet)
- `summe_je_artikel(pos, von, bis, filt)` – Umsatz (Cent) und Menge (Tausendstel) je Artikel über alle Kunden – Vergleichsgrundlage des Preisspiegels
- `offen(dim)` – Warten, bis das Pop-up des Merkmals offen ist; liefert seinen Text.
