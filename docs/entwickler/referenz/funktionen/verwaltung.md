# Funktionen: Verwaltung (`verwaltung`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

17 Dateien, 196 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/lib/auswertung.php`

_Auswertung: Anmeldeorte der Kunden (ungefährer Ort aus der IP-Adresse, ort.php)._

- `anmeldeorte_prune(list)`
- `anmeldeorte_load()`
- `geraet_typ(ua)`
- `anmeldeort_record(c, via)` – Anmeldung eines Kunden festhalten; Fehler dürfen die Anmeldung nie verhindern
- `anmeldeorte_remove_customer(kid)`

## `app/api/lib/kunden.php`

_Kundenstammdaten und Kunden-Sitzung_

**Kunden**

- `customers_load()`
- `customer_offers_direct(c)` – Freigeschaltete Angebote: direkt beim Kunden eingetragen (angebote) oder über seine Kundengruppe (Stammdaten → Angebote)
- `customer_offers_gruppe(c)` – Über die Kundengruppe: das Angebot, dem die Gruppe zugeordnet ist (Stammdaten → Angebote).
- `customer_offers(c)`
- `customer_public(c, wawi)` – Kunde für den Eingabebereich (ohne Passwort-Hash und Geräteschlüssel).
- `kunde_clear()`
- `ksess_prune(list)`
- `ksess_remove(match)`
- `current_customer()`
- `require_customer_csrf()`
- `kunde_payload(c)`

**Listen der Stammdaten (Kundengruppen, VK-Gruppen, Vertreter)**

- `gruppen_load(liste)`
- `gruppen_clean(liste, list, alt)` – $alt: gespeicherte Einträge nach Nummer – Felder, die ein Eintrag der Anfrage nicht enthält, und Felder, die dieser Stand nicht kennt (neuere Fassung), …
- `kundengruppen_load()`
- `kundengruppen_clean(list)`
- `vertreter_load()`

## `app/api/module/verwaltung/import.php`

_Importvertrag der Verwaltung – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md)._

- `import_arten_verwaltung()` – Registrierung für die Importzentrale (Felder: docs/plattform/schnittstellen/import.md)
- `import_zeilennr(r)` – Zeilennummer aus dem Leser (Zeile in der Datei, Kopfzeile = 1) – nur zur Anzeige

**Kunden**

- `kunden_wawi_wert(typ, v)` – Wert eines WaWi-Felds prüfen; null = leer bzw. ungültig (dann nicht gespeichert)
- `kunden_wawi_neu(alt, roh, felder)` – WaWi-Daten nach einer Zeile der Datei: Felder, die die Datei enthält ($felder), werden übernommen bzw. geleert; die übrigen (ältere Exporte ohne die Spalte, …
- `kunden_aktiv_stichtag()` – Stichtag der Aktiv-Regel (JJJJ-MM-TT, Ortszeit): heute vor KUNDEN_AKTIV_MONATE Monaten
- `kunden_letztes_datum(w)` – Jüngstes Datum aus letzter Rechnung, letztem Lieferschein (Rechnung ggf. an einen Rechnungsempfänger) und Anlage; '' = keines
- `kunden_dmy(iso)`
- `kunden_import_lauf(b, pruefen, details)` – Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen): Abgleich über die Kundennummer, sonst über Firma + PLZ bei Kunden ohne Nummer.
- `kunden_import_vorschau(e, me)`
- `kunden_import_uebernehmen(e, me)`
- `kunden_import_zentrale(e, pruefen)`

**Listen der Stammdaten: Kundengruppen, VK-Gruppen, Vertreter**

- `gruppen_zuordnungen(liste)` – Anzahl zugeordneter Kunden (Kundengruppen, Vertreter) bzw. Artikel (VK-Gruppen) je Nummer
- `gruppen_speichern(liste, groups, rev, me, quelle)` – Ganze Liste speichern (Revision, Protokoll) – Aktionen kundengruppen_save/vkgruppen_save/vertreter_save und Importzentrale
- `gruppen_import_liste(e)` – Liste der Importart (Registrierung: kundengruppen, vkgruppen, vertreter)
- `gruppen_import_vorschau(e, me)` – Vorschau: neu / geändert / entfällt gegenüber der gespeicherten Liste (gespeichert wird immer die ganze Liste)
- `gruppen_import_uebernehmen(e, me)`

**Artikelstammdaten**

- `stammdaten_speichern(articles, rev, me)` – Ganze Stammdatenliste speichern (Revision) – Aktion master_save und Importzentrale.
- `stammdaten_import_vorschau(e, me)` – Der Leser (admin.js) liefert die vollständige neue Liste: bestehende Artikel mit ergänzter VK-Gruppe/GTIN plus neue Artikel mit vorgeschlagenen Merkmalen – …
- `stammdaten_import_uebernehmen(e, me)`

## `app/api/module/verwaltung/importzentrale.php`

_Importzentrale (Verwaltung → Import, Roadmap 10b) – ein Ablauf für alle Importe_

- `import_registry()` – Alle registrierten Importarten (id → Eintrag mit Standardwerten).
- `import_darf(me, a)` – Recht der Importart: alle eingetragenen Rechte (Administrator: alle)
- `import_art_anzeige(id, a, me)` – Angaben für die Oberfläche (keine Funktionsnamen)
- `import_optionen(a, roh)` – Optionen der Importart aus der Anfrage: nur registrierte, mit Standardwert
- `import_ergebnis(r)` – Antwort des Eigentümers vereinheitlichen: Zahlen, höchstens IMPORT_ZEILEN_MAX Zeilen (Fehler zuerst), Hinweise
- `import_upload(v, pflicht)` – Kennung eines Importlaufs (vom Browser zufällig gewählt, 32 Hex-Zeichen) – nur bei Importarten mit Teilen nötig
- `import_vorbereiten(b)` – Gemeinsame Prüfung vor Vorschau, Teil und Übernahme: Anmeldung (mit CSRF), Importart, Recht, Ablauf, Wartung
- `import_teil_ausfuehren()` – Ein Teil einer großen Datei an den Eigentümer (Zwischenablage).
- `import_ausfuehren(uebernehmen)` – Vorschau oder Übernahme einer Importart.

## `app/api/ort.php`

_Ungefährer Ort (Stadt) einer IP-Adresse – für die Karte der Kunden-Anmeldungen (Auswertung) Datenquelle_

- `ort_file()`
- `ort_head(fh)`
- `ort_info()`
- `ort_lookup(ip)` – Ort einer IP-Adresse: ['city','region','cc','lat','lon'] oder null (privat/unbekannt)
- `ort_cut(s, n)` – gekürzt auf höchstens $n Byte, ohne ein UTF-8-Zeichen zu zerschneiden
- `ort_build(in, out, date)` – CSV (start,ende,Kontinent,Land,Region,Stadt,Breite,Länge) → Binärdatei; benachbarte Bereiche desselben Orts werden zusammengefasst
- `ort_download(out)` – aktuelle Ortsdaten herunterladen (dieser oder letzter Monat) und in den Datenordner schreiben

## `app/assets/admin-auswertung.js`

_Wochenangebot – Eingabebereich, Auswertung Karte der Kunden-Anmeldungen: ungefährer Ort (aus der IP-Adresse) je Anmeldung, Liste, Filter nach Zeitraum und Kunde._

- `loadKarte()`
- `gruppen(list)` – Anmeldungen am selben Ort zu einem Punkt zusammenfassen
- `filtered()`
- `fitBox(gs)`
- `aspect(b)` – Ausschnitt an das Seitenverhältnis der Kartenfläche anpassen
- `render()`
- `detailkarteZeigen(gs)` – Detailkarte (Straßen, Gebäude) statt eigener Zeichnung, wenn die Kartendatei bereitsteht und der Browser WebGL kann
- `scale()`
- `drawPoints(gs)`
- `applyVb()` – Ausschnitt anwenden: Punktgröße, Schrift und Orientierungsstädte an den Zoom anpassen
- `clamp(b)`
- `zoom(f, cx, cy)`
- `toMap(ev)`
- `openPop(key)` – Hinweisfeld zu einem Ort
- `closePop()`
- `placePop()`
- `focusPt(key)`
- `updateOrt(btn)`

## `app/assets/admin-import.js`

_Wochenangebot – Eingabebereich, Importzentrale (Verwaltung → Import, Roadmap 10b) Ein Ablauf für alle Importe_

**Einheitliche Vorprüfung der Datei (Dateityp, Kodierung, leer) – vor dem Leser des Eigentümers**

- `utf16(b)`
- `dateiPruefen(art, file)`

**Darstellung**

- `schritte(n)`
- `zeileHTML(a)`
- `umschalten(id)` – Ablagefenster auf- bzw. zuklappen (immer nur eines offen)
- `renderListe()`
- `kopf(titel)`
- `optionenHTML()`
- `alleZeilen()` – Zeilen der Vorschau: Fehler aus dem Leser (Datei) + Ergebnis des Servers
- `zahlen()`
- `zahlenHTML(z, ids)`
- `zeilenHTML()`
- `hinweiseHTML(list)`
- `renderLauf()`

**Ablauf**

- `datenAnfrage()`
- `teileSenden(l, btn)` – Teile, die die Vorschau für die Übernahme verlangt, einzeln schicken (Fortschritt im Knopf)
- `lesen()`
- `pruefen(nochmal)`
- `uebernehmen(btn)`
- `starten(art, files)`
- `zurListe()`

**Drag & Drop: auf einen Import oder in sein Ablagefenster ziehen**

- `ablegen(files, art)`
- `ziehenAus()`
- `render()`

## `app/assets/admin-verwaltung.js`

_Wochenangebot – Eingabebereich, Verwaltung Mitarbeiter, Bestellungen, Kunden, E-Mail, Protokoll._

**Mitarbeiter (Administrator; Personalstelle: nur HR-Angaben)**

- `renderUsersView()`
- `genPassword(n)`
- `userRightsRows(u, rollen)`
- `pflichtZeigen(role)`
- `unameVorschlag(vor, nach)` – Benutzername aus Vor- und Nachname wie auf dem Server (benutzername_vorschlag): „vorname-nachname“, Umlaute ae/oe/ue/ss

**Zentrale Anmeldung (Keycloak): Zustand und Aktionen für ein Mitarbeiterkonto**

- `kaZeigen(k)`
- `kaLaden(id)`
- `kaAktion(was, knopf)`
- `vertreterFeld(u)` – Vertreter im CRM: mit der Zuordnung zeigt das CRM „Mein Cockpit“ mit seinen Kunden (Vertreter oder Vertreter 2)
- `openUser(id)`
- `zugangZeigen()` – Mit/ohne Anmeldung: Felder für Anmeldung, Rolle, Passwort, zweiten Faktor und Rechte nur mit Anmeldung
- `zeigeFertig(u, pw, neu)` – Nach dem Anlegen (bzw. neuem Passwort): Zusammenfassung und „Zugangsdaten per E-Mail senden“
- `sendeZugang(id, pw)`
- `renderOrdersView()`

**Einkauf: Fehlmengen offener Bestellwünsche (alle Mitarbeiter; Melden ab Bearbeiter)**

- `renderEinkaufView()`
- `ekCount()`
- `openOrder(nr)`

**Kunden (Administrator)**

- `kVertreterOpts()`
- `kStatusOpts()`
- `kGruppenOpts()`
- `renderKundenView()`
- `renderKundenList()`
- `mailLine(c)`
- `openKunde(id)`
- `kundeWawi(w)`

**Kundenstammdaten aus der Warenwirtschaft importieren (CSV)**

- `kAusCsv(buf)`
- `kImportDatei(file)`
- `kImportPruefen()`

**E-Mail an Kunden**

- `kundeMail(c, type)`

**E-Mail-Einstellungen (Administrator)**

- `openMailCfg()`
- `renderMailView()`
- `kontoForm(m, intern)` – Postfach-Formular: Kunden-E-Mails (id ml-form) oder interne E-Mails an Mitarbeiter (id ml-form-int, z. B. verwaltung@…)
- `frachtCard(m)`
- `notifyCard(m)` – Benachrichtigungen an Mitarbeiter: je Ereignis an/aus und Empfänger
- `renderTestpost()`
- `openRund()`
- `rundCount()`

**Protokoll (Administrator)**

- `draftSummary(d)`
- `loadLog(month)`
- `renderLogView(reload)`
- `logFiltered()`
- `changesTable(d)`
- `renderLogList()`
- `logCSV()`

**Stammdaten → Gruppenlisten (Kundengruppen, VK-Gruppen)**

- `csvZeilen(text)` – CSV lesen: UTF-8, sonst Windows-1252 (Export der Warenwirtschaft); Semikolon, Anführungszeichen
- `csvText(buf)`
- `gruppenListe(cfg)`

## `tests/e2e/test_auswertung.py`

_Auswertung: Karte der Kunden-Anmeldungen._

- `check(n, c, i)`
- `ortsdaten()`
- `do_GET()`
- `log_message(*a)`
- `kunde_login(user, ip, ua)`
- `page(user, password, w)`

## `tests/e2e/test_importzentrale.py`

_Importzentrale (Verwaltung → Import, Roadmap 10b): eine Stelle für alle Importe mit einheitlichem Ablauf (Importart → Datei → Vorschau neu/geändert/entfällt/Fehler je Zeile → Übernahme → Ergebnis und Protokoll)._

- `check(n, c, i)`
- `doc(name)`
- `log_text(cl)`
- `bestaetigung_ablaufen(cl)`

**Registrierung: jede Importart gehört dem Daten-Eigentümer**

**Rechte: Anzeige und Prüfung je Importart (GR-103)**

**Kunden über die Schnittstelle der Zentrale**

**Bestand (Eigentümer Bestand) über die Schnittstelle**

**Wartung der Oberfläche (GR-107): Importe pausieren, Administratoren arbeiten weiter**

**Oberfläche**

**Ablagefenster je Import und Drag & Drop**

- `ziehen(sel, pfade, arten_)`
- `datei(art, pfad)`
- `fehler_text()`
- `sicht(user)` – Anzeige je Recht (Menüpunkt passt zur Liste des Servers)

## `tests/e2e/test_kunden.py`

_Kunden: Stammdaten, Freischaltung von Angeboten, Kunden-Anmeldung auf der Angebotsseite._

- `check(n, c, i)`
- `__init__(ip)`
- `call(action, data, raw)`
- `admin()`

**Stammdaten anlegen (API-Validierung)**

**Speichern mit Teilangaben (älterer/anderer Client): nichts geht verloren (GR-006)**

- `kdoc()`

**Rechte im Eingabebereich**

**Kunden-Anmeldung (API)**

**Änderungen wirken sofort**

**Merkliste je Kunde**

**Oberfläche**

- `falscher_schluessel(route)`

## `tests/e2e/test_kundengruppen.py`

_Stammdaten: Navigation (Artikel, Kunden, Kundengruppen), Kundengruppen per CSV (Windows-1252/UTF-8) importieren, bearbeiten, Rechte, Zuordnung im Kunden, Protokoll._

- `check(n, c, i)`
- `doc(name)`

## `tests/e2e/test_kundenimport.py`

_Stammdaten → Angebote mit Kundengruppen (Freischaltung über die Gruppe), Import der Kundenstammdaten aus der Warenwirtschaft (CSV, alle Spalten, Aktiv-Regel 18 Monate) und Passwort-Auswahl im Kunden-Dialog._

- `vor(monate, tag)` – Datum vor n Monaten (JJJJ-MM-TT). tag=False: wie PHP modify('-n months') – ein zu großer Tag läuft in den Folgemonat.
- `dmy(iso)`
- `datei_mit_daten()` – Kopie der Testdatei mit Rechnungs-, Lieferschein- und Anlagedaten relativ zu heute (Aktiv-Regel unabhängig vom Testtag)
- `check(n, c, i)`
- `doc(name)`
- `bestaetigung_ablaufen(cl)`
- `kunde(body)`

**Angebote ↔ Kundengruppen**

**Kundenimport: Schnittstelle**

**Kundenimport: alle Spalten (Daten der Warenwirtschaft) und Aktiv-Regel (18 Monate)**

- `importiere(rows, felder, quelle)`
- `speichern(nr, aktiv)`

**Stammdaten → Angebote**

**Kundengruppe nur einmal zuordenbar**

**Preise importieren**

- `entwurf_ok()`

## `tests/e2e/test_master.py`

_Testgruppe master: Artikelstammdaten und Bezeichnungsregeln (Fleischart, Herkunft, Zustand, VK-Gruppe)._

- `check(n, c, i)`
- `login(pg, user, pw)`
- `names(pg)`
- `post(pg, action, body)`
- `wait_saved(pg)`
- `wait_master(pg)`

## `tests/e2e/test_vertreter.py`

_Stammdaten → Vertreter (Liste aus der Warenwirtschaft) und die Felder „Vertreter“ und „Vertreter 2“ in den Kunden_

- `check(n, c, i)`
- `doc(name)`

## `tests/e2e/test_vkgruppen.py`

_Stammdaten → VK-Gruppen und Import der Artikelstammdaten (CSV-Export der Warenwirtschaft)_

- `check(n, c, i)`
- `doc(name)`

## `werkzeuge/karte_bauen.py`

_Baut die Landkarte für die Auswertung (app/assets/karte.json) aus Natural Earth (gemeinfrei), weitergegeben als TopoJSON im npm-Paket „world-atlas“ (ISC)._

- `proj(lon, lat)`
- `decode(topo)`
- `ring(arcs, idx)`
- `polygons(geom)`
- `bbox(pts)`
- `inside(b, area)`
- `path(pts)`
- `countries(topo, keep)`
- `main()`
