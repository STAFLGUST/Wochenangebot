# Funktionen: Bestand (`bestand`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

9 Dateien, 64 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/lib/bestand-pdf.php`

_Bestand als PDF (Verwaltung → Bestand → „PDF“)_

- `stock_pdf_stufe(mhd)` – MHD-Stufe relativ zu heute (deutsche Zeit) – wie mhdClass() im Eingabebereich
- `stock_pdf(st, zeilen, zusatz, mhdListe)` – $zeilen: [['g' => Warengruppe] \| ['c' => Artikelnummer], …] in der Reihenfolge der Ansicht; $zusatz: Suche/MHD-Auswahl für den Titel; $mhdListe: Suche „MHD“ …
- `stock_pdf_name(st, art)`

## `app/api/lib/bestand.php`

_Bestandsliste und Stammdaten_

**Bestand**

- `stock_week_prices(today)` – Nur lesend: exakte ISO-Wochen, keine Entwurfspreise und kein Rückgriff auf ältere Wochen.
- `clean_date(v)`
- `clean_kg(v, where)`
- `clean_incoming(rows)`
- `clean_stock(b, allowEmpty)`
- `stock_ohne_ek(st)` – Einkaufspreise aus einem Bestand entfernen (für Nutzer ohne Recht „bestand.einkaufspreise“)
- `bestand_merkmale(s)`
- `bestand_bezeichnung(a)` – Bezeichnung mit Merkmalen in einer Zeile (Excel und Text der MHD-Mail; die CSV der Ansicht setzt sie genauso zusammen): „Lachs · Schwein · DE · frisch“
- `bestand_originalname(a)` – Originalbezeichnung eines Bestandsartikels (MHD-Liste, Auftrag des Inhabers 03.11.2026): Bezeichnung1 aus dem Artikelstammdaten-Import der Warenwirtschaft, …
- `bestand_mit_stammdaten(st)`

**Auszug für die Kundenseite (ADR-007 Stufe 2b)**

- `artikelauszug_erzeugen(bestand, stamm)`
- `artikelauszug_aktualisieren(immer)` – Auszug neu schreiben, wenn er nicht zum Stand von Bestand und Stammdaten passt (nur ab Trennstufe 2, nur mit Sicht auf die internen Daten).
- `artikelauszug()` – Kundenseite: Auszug lesen (null, wenn es noch keinen gibt)

**Stammdaten**

- `code_key(c)`
- `clean_master(list)`
- `angebotsnamen_clean(v, wo, known)` – Eigene Bezeichnungen je Angebot (Stammsatz und Artikel des Angebots): Angebots-ID → Text, höchstens OFFER_MAX Einträge.
- `angebotsnamen_text(v)` – Vergleichstext der Bezeichnungen je Angebot (Protokoll, Vorschau): „edeka: Rinderhüfte · bela: …“
- `master_changes(old, new)`

## `app/api/module/bestand/import.php`

_Importvertrag des Moduls Bestand – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md)._

- `import_arten_bestand()`
- `bestand_speichern(date, source, articles, incoming, me)` – Bestand speichern und protokollieren (Aktion stock_import und Importzentrale)
- `bestand_import_pruefen(e)` – Gelesene Bestandsliste prüfen: Partien, erwartete Zugänge, Bestandsdatum (Pflicht in der Importzentrale)
- `bestand_import_vorschau(e, me)`
- `bestand_stand(st)` – Kennung des gespeicherten Bestands für die Übernahme (ändert sich mit jedem Speichern, auch innerhalb einer Sekunde)
- `bestand_import_uebernehmen(e, me)`

## `app/api/module/bestand/verlauf.php`

_Modul Bestand · Bestandsverlauf (Auftrag des Inhabers 02.11.2026): bei jedem Übernehmen der Bestandsliste (Bestand → Bestandsliste hochladen, Aktion stock_import, Importzentrale) wird ein Tagesstand gespeichert – je …_

- `bestand_verlauf_stand(articles, incoming)` – Tagesstand aus der übernommenen Bestandsliste: artikel[code] = [kg, zugang, ekWert, ekKg, partien], namen[code]
- `bestand_verlauf_summen(stand)` – Summen eines Tagesstands für das Verzeichnis
- `bestand_verlauf_schreiben(datum, articles, incoming, quelle, me)` – Tagesstand speichern (ersetzt einen früheren desselben Tags); ohne gültiges Datum: heute

**Schnittstelle für das Controlling (nur lesen; enthält Lagerwerte zum EK – der Aufrufer prüft die Rechte)**

- `bestand_verlauf_index()` – Verzeichnis: Datum => Summen (kg, zugang, ekWert, ekKg, artikel, partien) und Herkunft (quelle, um, von), aufsteigend
- `bestand_verlauf_tag(datum)` – Tagesstand eines Tags oder null: datum, quelle, um, von, felder, artikel[code] = [kg, zugang, ekWert, ekKg, partien], namen

## `app/assets/stock-core.js`

_Bestand – Einlesen der WinAB-Bestandsliste („Partieliste … verfügbar“) Liest die CSV-Ausgabe (Semikolon, Windows-1252 oder UTF-8; Spalten „Art._

**Warengruppen nach Artikelnummer**

- `warengruppe(code)`

**.xls (BIFF)**

- `u16(b, o)`
- `u32(b, o)`
- `f64(b, o)`
- `rk(v)`
- `cfbStream(b)` – OLE-/CFB-Container: Datenstrom „Workbook“ bzw. „Book“ herauslösen
- `biffSheets(b)` – BIFF-Datensätze in Tabellenraster umsetzen

**.csv (WinAB-Bestandsliste als CSV)**

- `csvRows(text)` – Zeilen und Zellen: Semikolon, Anführungszeichen (verdoppelt im Text), Zeilenende CRLF oder LF
- `csvZelle(v)`
- `readStockCsv(buffer)`
- `readStockWorkbook(buffer, fileName)` – Datei lesen: .csv nach Name oder Inhalt (Text mit Semikolon), sonst Excel (.xlsx, .xls)

**Bestandsliste auswerten**

- `toDate(v, allowSerial)`
- `toNum(v)`
- `parseSheet(grid)`
- `findDate(sheets, fileName)`
- `parseStockWorkbook(sheets, fileName)`
- `weekPriceMap(week)` – Mehrdeutige Artikelnummern nie mit einem zufällig gewählten Preis vergleichen.
- `priceComparison(current, previous)`

## `tests/e2e/test_bestand_pdf.py`

_Bestand: Marke je Partie (Spalte E der WinAB-Liste, Überschrift „Marke“ eine Spalte rechts davon), dezente MHD-Farben (hell/dunkel) und PDF ohne Preise, erfassten Bestand, Gesamt verfügbar und erwartete Zugänge._

- `check(n, c, i)`

**synthetische WinAB-Bestandsliste**

- `pdf_text(raw)` – Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi
- `pdf_roh(c, data)` – stock_pdf als Bytes (Client.call liefert Text)

## `tests/e2e/test_stock.py`

_Summen exakt (Dezimal) und kaufmännisch gerundet wie die Anzeige – Gleitkomma-Summen kippen sonst bei ,xx5 je nach Datum_

- `check(n, c, i)`
- `login(pg, user, pw)`
- `unmarked_codes()` – Sortierung per Spaltenkopf
- `marked_first()`

**Bezeichnung aus den Artikelstammdaten, VK-Gruppen, Spaltenfilter**

- `doc_(name)` – ── Bestandsverlauf: Tagesstand je Übernahme (Daten des Bestands, Auswertung später im Controlling) ──

## `tests/e2e/test_stock_overview.py`

_Exakte Wochenpreise, separate erfasste Zugänge, Validierung, Rechte und Anzeige._

- `check(name, ok, info)`
- `row(code)`

## `tests/unit/stock_prices.php`

_Isolated calendar/history selection tests, no server or production storage._

- `store_read(name)`
- `store_names(prefix)`
- `now()`
- `check(name, ok)`
