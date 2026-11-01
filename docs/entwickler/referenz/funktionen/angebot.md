# Funktionen: Angebot (`angebot`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

41 Dateien, 586 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/lib/angebote.php`

_Angebote, Kundenpreise, Sonderpreise, Datenmodell, gemeinsames Bearbeiten_

**Mehrere Angebote**

- `offers_load()`
- `offer_ids()`
- `angebot_ids_mit_resten(vorhanden)` – IDs nicht (mehr) vorhandener Angebote, unter denen noch Daten stehen: Kundenpreise/Sonderpreise im veröffentlichten Angebot oder Entwurf, direkte …
- `offer_gruppen_clean(v, name)` – Kundengruppen eines Angebots (Stammdaten → Angebote): Kunden dieser Gruppen sehen das Angebot ohne eigene Freischaltung
- `std_public()` – Ist das Standard-Wochenangebot ohne Anmeldung sichtbar?
- `offer_def(id)`
- `clean_variants(v, where, known)`
- `clean_werbung(w, known, iids)`
- `clean_money(x, what)` – Sonderpreis „solange der Vorrat reicht“ (Artikel mit kurzem oder überschrittenem MHD): $item['sale'] = {value: Grundsonderpreis für alle Angebote, offers?: …
- `clean_sale(v, where, known)`
- `sale_for(it, oid)`
- `stock_codes()` – Artikelnummern mit eingelagertem Bestand (null = keine Bestandsliste vorhanden)
- `sold_out(it)`
- `offer_resolve(m, def)` – Angebot für die Auslieferung: nur Preise dieses Angebots, keine Kundenpreise anderer Angebote, keine ausgeblendeten Artikel, Sonderpreise aufgelöst (ohne …
- `kw_gueltig(woche, jahr)` – Kalenderwoche nach ISO 8601: KW 53 gibt es nur in Jahren mit 53 Wochen (der 28.12. liegt immer in der letzten)
- `clean_model(m, strict)` – Übernimmt nur bekannte Felder in bekannten Formaten

**Gemeinsames Bearbeiten des Entwurfs**

- `draft_rev(draft)`
- `draft_end(draft, why)`
- `draft_conflict(draft)`

## `app/api/lib/einzelangebote.php`

_Einzelangebote: ein Angebot für genau einen Kunden (Angebot bearbeiten → Einzelangebote)._

- `einzel_load()`
- `einzel_find(d, id)`
- `einzel_titel(e)`
- `einzel_gueltig(e)`
- `einzel_sichtbar(e)`
- `einzel_stand(prev)` – Stand der Freigabe (Millisekunden, immer später als der vorige): Bestellwünsche auf einen älteren Stand werden abgewiesen
- `einzel_clean(b)` – Eingaben prüfen (Kopf und Positionen)
- `einzel_summe(e)` – Summen (Positionen mit Menge und Preis)
- `einzel_view(e, kunden)` – Ansicht für den Eingabebereich (mit Kundenname)
- `einzel_kunden_map()`

**Portal**

- `einzel_fuer_kunde(c)` – Für den Kunden sichtbare Einzelangebote (freigegeben, noch gültig)
- `einzel_von_kennung(oid)`
- `einzel_model(e)` – Angebotsmodell wie offer_resolve() – nur Name, Merkmale und Preis, kein Bestand

**Artikelsuche im Eingabebereich**

- `einzel_artikel(mitBestand, mitEk)` – Alle bekannten Artikel: Stammdaten (mit Merkmalen und VK-Gruppe), Bestand (eingelagert, erfasst, gesamt; je Partie und je erwarteter Lieferung) und Preis im …

**PDF im Design der Angebotsansicht (A4 quer, drei Spalten)**

- `einzel_pdf(e, c)` – Wie die Druckliste der Angebotsseite: Logo und Titel, Blöcke mit Kopfzeile „€ / kg“, Zebrastreifen, Seitenzahlen.
- `plural_de(n, eins, viele)`
- `einzel_pdf_name(e)`

**E-Mail an den Kunden**

- `mail_tpl_einzel(c, e, note, format)` – $format: „liste“ = Positionen als Tabelle in der E-Mail (bisher), „pdf“ = kurze Nachricht, Angebot als PDF im Anhang

## `app/api/lib/fracht.php`

_Fracht: Mindestmenge für frachtfreie Lieferung, Frachtanteil je Staffel (unter X kg → Y € pro Sendung) und der Hinweis („Vermerk“) unter dem Angebot._

- `fracht_clean_staffeln(in)`
- `fracht_settings()`
- `fracht_frei(s)` – frachtfrei ab (kg) oder null
- `fracht_kosten(kg, s)` – Frachtanteil für eine Gesamtmenge: kleinste Grenze, die noch über der Menge liegt
- `fracht_eur(v)`
- `fracht_hinweis(s)` – Vermerk unter dem Angebot (Bildschirm und Druck), Zeile für Zeile
- `fracht_public()`

## `app/api/lib/kundenmail.php`

_E-Mails an Kunden, Abmelden, Bestellwunsch-Vorlagen, Einmal-Links, Versand_

**E-Mail an Kunden**

- `mail_settings()`
- `require_mail(intern)` – $intern: E-Mail nur an Mitarbeiter → internes Postfach (ohne eigenes: Kunden-Postfach), mail_cfg_intern()
- `mail_week()`
- `mail_offer_links(c)`
- `mail_footer(kind)`

**Abmelden vom Wochenangebot**

- `abmelde_key()`
- `abmelde_token(kid)`
- `abmelde_kunde(tok)`
- `abmelde_url(c)`
- `abmelde_setzen(c, ab, via)` – Abmelden/Wiederanmelden speichern; true, wenn sich der Status geändert hat
- `abmelde_melden(c, ab, via)`

**Bestellwünsche**

- `order_settings()`
- `order_enabled()`
- `de_num(v, dec)`
- `de_qty(v)`
- `mail_tpl_bestellung(o, copy)` – Mail an uns bzw. Kopie an den Kunden: [Betreff, Text, HTML]
- `mail_tpl_angebot(c, note, wk)` – Wochenangebot / Angebotslink: [Betreff, Text, HTML]
- `restposten_items(def)` – Sonderposten eines Angebots – nur dessen Artikel und Preise: [Betreff, Text, HTML]
- `mail_tpl_restposten(c, def, items, note)`
- `restposten_reason(c, oid)` – Wer bekommt die Sonderposten eines Angebots?
- `mail_tpl_zugang(c, url, purpose, exp)` – Einladung / Passwort zurücksetzen – eigenes Layout (mail_layout_einladung): Überschrift, Benutzerkennung, großer Knopf, Schritte.
- `kunde_token_new(kid, purpose)` – Einmal-Link erzeugen (gespeichert wird nur der Hash)
- `kunde_by_token(tok)`
- `testpost_ablegen(cfg, jobs)` – Testumgebung: Nachrichten nur speichern (Testpostfach, die letzten 100) – nie an echte Empfänger
- `mail_send_many(cfg, jobs)` – Mehrere Nachrichten über eine Verbindung; Ergebnis je Auftrag
- `mail_record(entries, wk)` – Versand an Kunden vermerken (letzte E-Mail, Wochenversand) und ins Versandprotokoll schreiben
- `mail_job_for(c, typ, note, wk)`
- `kunde_sign_in(c, via)` – Kunde anmelden (nach Passwortprüfung oder Einmal-Link)

## `app/api/lib/preisverlauf.php`

_Preisverlauf (Wochenstände)_

**Preisverlauf**

- `history_id(week, year)`
- `history_ids()`
- `history_from_model(m, origin, at)` – Preis-Stand einer Woche aus einem veröffentlichten Angebot
- `history_backfill()` – Bisherige Veröffentlichungen einmalig in den Preisverlauf übernehmen (gelöschte Wochen ausgenommen)
- `history_undelete(id)`
- `clean_history_items(items)`

## `app/api/module/angebot/import.php`

_Importvertrag des Moduls Angebot – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md). - Preisverlauf: frühere Angebotslisten (.xlsx) als Wochen im Preisverlauf._

- `import_arten_angebot()`
- `preisverlauf_woche_speichern(week, year, items, source)` – Eine Woche speichern (ersetzt eine vorhandene Woche) und protokollieren – Aktion history_import und Importzentrale
- `preisverlauf_import_wochen(e)` – Wochen der Dateien prüfen: gültige Woche, Artikel; doppelte Woche → die spätere Datei zählt (wie im Preisverlauf)
- `preisverlauf_import_vorschau(e, me)`
- `preisverlauf_import_uebernehmen(e, me)`

## `app/api/order_outbox.php`

_Durable per-recipient jobs live in the same document/transaction as the order._

- `order_outbox_create(o)`
- `order_outbox_summary(o)`
- `order_outbox_view(o)`
- `order_outbox_cleanup_locks(own)` – Sperrdateien abgeschlossener Vorgänge gelegentlich entfernen (älter als 2 Tage, nicht die eigene).
- `order_outbox_send(nr, jobId, expected, by)` – No SQLite transaction spans SMTP.

## `app/api/orders.php`

_Shared order operations for the website and future app clients._

- `order_request_hash(body)`
- `order_state(o, staff)` – „Bestätigt“ ist eine interne Kennzeichnung und keine Auftragsbestätigung – Kunden sehen dort weiter „In Bearbeitung“.
- `order_view(o, staff)`
- `order_receipt(o, replayed)`
- `order_replay(all, kid, key, hash)`
- `orders_action(action)`

## `app/assets/admin-artikelwahl.js`

_Eingabebereich – Fenster „Artikel hinzufügen“ (gemeinsam für „Angebot bearbeiten“ und Einzelangebote) Links die VK-Gruppen (mit Anzahl), rechts die Artikel der gewählten Gruppe als Tabelle mit Häkchen, eingelagertem …_

- `bestandHTML(a, kurz)`
- `naechsteEta(a)` – Nächste erwartete Ankunft (frühestes Datum; ohne Datum: keine Angabe)
- `passt(a, toks)`
- `pickBasis()` – Treffer der Filter/Suche (ohne Gruppenwahl) und Anzahl je Gruppe
- `pickZeilen(basis)` – Angezeigte Artikel: gewählte Gruppe, sonst (bei Suche) alle Gruppen; sortiert nach Gruppe und Artikelnummer
- `oeffnen(c)`
- `renderPick()`
- `renderPickNav(basis)`
- `detailHTML(a)`
- `preisFeld(a, k)`
- `renderPickList(basis)`
- `spannen()` – Gruppen- und Detailzeilen überspannen nur die sichtbaren Spalten: auf dem Handy blendet das Stylesheet Spalten aus – ein zu großes colspan erzeugt sonst …
- `renderPickFoot(fehler)`
- `pickUebernehmen()`
- `pickGruppe(g)`
- `preiseMerken()` – Preisfelder behalten ihre Eingabe beim Neuzeichnen (Gruppenwechsel, Suche)

## `app/assets/admin-einzel.js`

_Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde) Kunde über eine Suche wählen (Firma, Kundennummer, Ort, Ansprechpartner …)._

- `abw(price, std)` – Abweichung vom Wochenangebotspreis: Punkt + Prozent
- `laden()`
- `ladeIndex()`
- `koerper()`
- `render()`

**Übersicht**

- `renderListe()`
- `statusChip(e)`

**Bearbeiten**

- `neu()`
- `oeffnen(id)`

**Kundenauswahl mit Suche**

- `kundenTreffer(text)` – Treffer: alle Suchwörter in Firma, Nummer, Ort, PLZ, Ansprechpartner, E-Mail, Straße; Nummer genau > Firma beginnt > Wortanfang > enthalten
- `renderKundenListe()`
- `kundeSchliessen()`
- `kundeWaehlen(id)`
- `renderEditor()`
- `renderPos()`
- `summen()`
- `summeHTML()`

**Fenster „Artikel hinzufügen“ (gemeinsames Fenster: admin-artikelwahl.js)**

- `pickOeffnen()`
- `markDirty()`
- `kopfLesen()`
- `speichern()`
- `status(s)`

**Drucken / PDF: wie auf der Angebotsseite (deren Druckdialog, z. B. Angebotsliste A4 quer)**

- `drucken()`

**E-Mail**

- `mailDialog()`

## `app/assets/admin-werbung.js`

_Eingabebereich – Fenster „Werbung schalten“ (Angebot bearbeiten, Knopf „Werbung“ in der Werkzeugleiste) Überschrift, optionaler Werbetext und bis zu 12 Artikel des gewählten Angebots (Reihenfolge, je Artikel ein …_

- `listeHTML()`
- `ausAuswahl(ids, artikel)` – Rückkehr aus der Artikelauswahl: ids = gewählte Artikel (Reihenfolge der Auswahl), artikel = aktuelle Liste des Angebots.
- `oeffnen(c)` – cfg: { angebot, eintrag: {titel, text?, artikel: [{id, text?}]} \| null, artikel: [{id, code, name, merkmale, preis}], max, ro, auswaehlen(ids, fertig(ids, …

## `app/assets/admin.js`

_Wochenangebot – Eingabebereich Bearbeitet einen Entwurf auf dem Server (automatisch gespeichert)._

**Hilfen**

- `priceToInput(p)`
- `inputToPrice(v, label)`

**Zustand**

- `effPrice(it, oid)`
- `variantShort(v, oid)`
- `inOffer(it, oid)`
- `aufnehmen(it, oid, p)` – In ein Angebot aufnehmen; p = Preis ({status, value?}) oder null (Preis bleibt, in eigener Liste „auf Anfrage“)
- `nurIn(it, oid)` – Neuer Artikel nur für dieses Angebot: im Wochenangebot und in Angeboten, die ihm folgen, nicht enthalten
- `entfernen(it, oid)` – Aus einem Angebot entfernen.
- `werbungBereinigen()` – Artikel, die nicht mehr im Angebot stehen, fallen aus dessen Werbung (unbekannte Angebote prüft der Server)

**API**

- `api(action, opts)`
- `bestaetigenPerFenster(adresse, erneut)`
- `confirmAdminAction()`

**Toast**

- `toast(msg, ms)`

**Bestätigungsdialog**

- `confirmBox(title, text, okLabel, danger)`

**Anmeldung**

- `bereich()`
- `startAnsicht()` – Startansicht aus der Adresse (#importe oder ?ansicht=importe, z. B. verwaltung…/import/) – nur erlaubte Ansichten
- `viewAllowed(v)`
- `showAuth(mode)`
- `afterLogin(r, pw)`
- `finishLogin()`
- `renderTwofaSetup(host, onDone, password)` – Zwei-Faktor einrichten (Anmeldeschirm und Dialog)
- `showRecovery(host, codes, onDone)`
- `openTwofaDialog()` – Menü: eigene Zwei-Faktor-Anmeldung verwalten

**Passkeys (WebAuthn)**

- `pkError(ex)`
- `passkeyRegister(password, name)` – Neuen Passkey einrichten (immer mit aktuellem Passwort)
- `passkeyLogin(second)` – Anmelden mit Passkey: ohne Benutzername oder (second) als zweiter Schritt nach dem Passwort
- `openPasskeyDialog()`
- `renderPasskeys()`
- `applyRole()` – Rolle auf die Oberfläche anwenden
- `lockInputs(root)` – Nur-Ansicht: Eingabefelder sperren (Suche/Filter bleiben bedienbar)

**Editor laden**

- `emptyModel()`
- `strip(m)`
- `normalizeNames(m)` – Bezeichnungen/Herkunft vereinheitlichen: „frisch“ nur im Zustand, Marke „Fleischmeister“ in der Bezeichnung, Herkunft als Kürzel
- `showEingabeWartung(w)`
- `renderWartungBanner()`
- `refreshWartung()`
- `openEditor()`

**Speichern**

- `setSaveState(st, msg)`
- `editorsHTML()`
- `changed(opts)`
- `saveNow()`

**Gemeinsames Bearbeiten**

- `startSync()`
- `syncTick()`
- `pullRemote()` – Laufenden Abgleich abwarten und danach frisch holen – wer gerade einen Konflikt auflöst, braucht den Stand nach der fremden Speicherung, nicht den eines …
- `pullOnce()`
- `editingNow()` – Neu zeichnen, ohne eine angefangene Eingabe zu zerstören
- `renderRemote(ids)`

**Rückgängig**

- `pushUndo()`
- `undo()`

**Darstellung**

- `metaChanged()`
- `renderAll()`
- `renderMeta()`
- `renderMetaInfo()`
- `renderChanges()` – Unveröffentlichte Änderungen: Zahl am Knopf „Veröffentlichen“, Aufstellung als Hinweis beim Darüberfahren (die Leiste über dem Editor entfällt; die …
- `updatePublishBtn()`
- `rowState(it)`
- `matchesFilter(it)`
- `wasHTML(it, st, before)`
- `altsHTML(it)`
- `rowHTML(it)`
- `saleBtnHTML(it)`
- `saleTagHTML(it)`
- `stdCellHTML(it, bad, label, was, alts)`
- `variantCellHTML(it, st)` – Preis in einem Kundenangebot: eigene Artikelliste = immer eigener Preis (oder „a. Anfr.“); folgt dem Wochenangebot = leer heißt Standardpreis
- `updateRow(id)`
- `renderWerbungBtn()`
- `renderGroups()`
- `bereicheZeigen(host)` – Bereichsüberschrift nur, wenn mindestens eine ihrer Gruppen sichtbar ist (Suche, „Nur Änderungen“)
- `filterAnwenden()` – Leistung: Suche und „Nur Änderungen“ blenden vorhandene Zeilen und Gruppen nur aus/ein, statt den Editor (~12 000 Elemente) neu zu zeichnen.

**Bearbeiten**

- `applyField(it, f, el)`
- `newItem(groupId, after)` – Neue (freie) Position im gewählten Angebot – in anderen Angeboten erscheint sie nicht
- `ausAngebot(id)` – Artikel aus dem gewählten Angebot entfernen (andere Angebote bleiben unverändert)

**Artikel-Dialog**

- `openItem(id)`

**Excel-Import**

- `pickFile()`
- `importFile(file)`
- `importError(msg)`
- `issuesHTML(issues)`
- `renderImport(d)`
- `werbungUebernehmen(alt, neu)` – Werbung geht beim Excel-Import auf den Artikel mit derselben Artikelnummer über (ohne Nummer: gleiche Bezeichnung)
- `importKundenangebote(alt, neu)`

**Angebote (Standard + Kundenangebote)**

- `loadOffers()`
- `angebotsseite(abfrage)` – Adresse der Angebotsseite auf diesem Host (Angebotsseite, Vorschau, Kundenangebot).
- `renderOfferBar()`
- `obFilter()`
- `renderOfferHead()` – Kopf des gewählten Angebots: Art, Name, Artikelliste, Anzahl, Aktionen; Hinweis bei „folgt dem Wochenangebot“
- `setOffer(id)`
- `obAktion(b)`
- `umstellen(oid)` – „Folgt dem Wochenangebot“ → eigene Artikelliste (wirkt sofort für die Kunden des Angebots; Recht angebote.verwalten)
- `openOffers()`
- `ofReset()`
- `renderOffersView()`
- `ofKundenZahl(id, gruppen)`
- `ofChips(gruppen, key)`
- `renderOffersBody(err)`
- `ofArtikel(id, fallback)` – Artikel eines Angebots mit der (noch nicht gespeicherten) Regel aus der Eingabe
- `ofMark()`
- `openOfGruppen(key)`
- `ofgCount()`
- `preiseAusCsv(buf)`
- `ofPreisPlan()`
- `ofPreiseDatei(file)`
- `renderOfPreise(err)`
- `openCopy()`

**Vorschau**

- `pvFuss()`
- `pvLaden()`
- `openVorschau(oid)`

**Veröffentlichen**

- `openPublish()`
- `changedFields(o, it)`
- `revertChange(kind, id)` – Eine einzelne Änderung gegenüber der veröffentlichten Fassung zurücknehmen
- `revertText(kind, id)`

**Versionen**

- `openVersions()`

**Menü & Kopf**

- `showSendHint(week, year)` – Versand an Kunden: Knopf oben und Hinweis direkt nach dem Veröffentlichen (an jedem Tag möglich)

**Preisverlauf**

- `seriesKey(it, dup)` – Artikel-Schlüssel über alle Wochen: Artikelnummer; bei mehrfach vergebenen Nummern zusätzlich Bezeichnung + Gruppe
- `buildHistory(weeks)`
- `rangeIdx(H)` – Wochen-Indizes im gewählten Zeitraum
- `statsFor(s, idx)` – Kennzahlen eines Artikels im Zeitraum
- `setRange(k)`
- `loadHistory(force)`
- `sparkSVG(vals, w, h)` – Mini-Verlauf
- `navSichtbar(btn)` – Aktiven Eintrag in der Seitenleiste sichtbar halten: am Computer scrollt die Leiste senkrecht (mehr Einträge als Bildschirmhöhe), schmal ist sie eine …
- `setView(v)`
- `renderHistView()`
- `renderHistList()`

**Daten: gespeicherte Wochen verwalten**

- `renderHistData()`

**Detail: Diagramm + Wochentabelle**

- `chartSVG(s, weeks, vals)`
- `openSeries(key)`
- `fillItemHistory(it)` – Verlauf im Artikel-Dialog des Editors

**Alte Angebote hochladen (mehrere Dateien)**

- `histAusDatei(file)` – Eine Angebotsliste als Woche lesen (Angebotsleser offer-core.js) – hier und in der Importzentrale
- `histImportFiles(files)`
- `hiFlags()`
- `renderHistImport()`

**Bestand (Mengen, MHD – nur im Eingabebereich)**

- `isoToday(plus)`
- `mhdClass(iso)` – MHD-Kennzeichnung relativ zum heutigen Datum
- `loadStock(force)`
- `offerPriceMap()` – Verkaufspreise der Angebotswoche (aktueller Entwurf) je Artikelnummer
- `stockItems()`
- `naechsteEta(list)` – Nächste ETA der erfassten Zugänge: frühestes Ankunftsdatum ab heute; liegen alle in der Vergangenheit, das späteste (überfällig).
- `colCompare(a, b)`
- `stockResult(q)`

**Spaltenfilter (Trichter an jeder Überschrift; am Handy über den Knopf „Filter“)**

- `filterPasst(a)`
- `filterText(k)` – Kurztext eines Filters (Leiste, Druck, PDF)
- `filterLesen(k, host)` – Eingaben eines Filters → gespeicherter Filter (leer = kein Filter)
- `filterFelder(k)` – Eingabefelder eines Filters (Fenster am Kopf und Filterdialog am Handy)
- `stPopZeigen(k, btn)`
- `stPopPlatz(btn)` – Lage am Trichter der Spalte; nach dem Neuzeichnen (kürzere Liste, Seite rollt nach) neu ausrichten statt schließen
- `stPopZu(fokus)`
- `openStockFilter()`

**Fenster „VK-Gruppen“: aktuelle Auswahl (Suche und Filter) je VK-Gruppe der Artikelstammdaten**

- `openStockVk()`
- `stockTableHTML(res, print)`
- `renderStockView()`
- `renderStockList()`
- `openStockIncoming(idx)`
- `lotTableHTML(lots, zugang, marke)` – zugang = erwartete Zugänge (Status „erfasst“): dieselbe Tabelle, Datumsspalte „ETA“ (auch am Handy sichtbar), fehlendes MHD als „—“ (meist noch nicht …
- `openStockItem(idx)`
- `fillItemStock(it)` – Bestand im Artikel-Dialog des Angebots
- `stockAusDatei(file)` – Bestandsliste lesen (Leser des Moduls Bestand: stock-core.js) – hier und in der Importzentrale
- `stockImportFile(file)`
- `stockCSV()` – CSV (aktuelle Auswahl)
- `stockPDF(btn)` – PDF zum Weitergeben (Server, lib/bestand-pdf.php): nur Art.-Nr., Bezeichnung, eingelagerter Bestand, kürzestes MHD, Kg kürz.

**MHD-Liste an den Verkauf (Server: stock_mhd_senden, lib/bestand-mhd.php)**

- `mhdBild(list)` – Bild für die E-Mail: Schrift wie in der Anwendung (14 px), Spalten knapp, damit das Bild in der E-Mail in Originalgröße (Breite = Rückgabe „breite“, …
- `mhdAnVerkauf(btn)`
- `printStock()` – Druck / PDF (DIN A4)

**Angebot: Vorwoche, Bestand, Bestand ohne Preis**

- `loadPrev()`
- `loadAux()`
- `auxGemerkt()` – Stand von Bestand/Vorwoche, mit dem der Editor zuletzt gezeichnet wurde (renderGroups, refreshAux)
- `stockOf(code)`
- `prevOf(it)`
- `auxHeadHTML()`
- `prevCellHTML(it)`
- `stockCellHTML(it)`
- `refreshAux()` – Spalten nach dem Laden von Bestand/Vorwoche aktualisieren, ohne Eingabefelder neu zu zeichnen
- `noPriceList()`
- `renderNoPrice()`
- `panelLayout()` – Beide Leisten nebeneinander; eine aufgeklappte Leiste nimmt die volle Breite ein
- `gotoPrice(it)`

**Artikel hinzufügen (Fenster wie im Einzelangebot)**

- `ladeArtikelwahl()`
- `zielGruppe(a, anlegen)` – Ziel-Angebotsgruppe eines Artikels (anlegen = fehlende Gruppe neu anlegen, sonst nur Name für die Anzeige)
- `preiseLesen(liste, preise, K)` – Preise aus der Artikelauswahl lesen: Map(key → Preis \| null) oder Fehlertext
- `artikelAufnehmen(liste, ps, pool, K)` – Artikel der Auswahl in das gewählte Angebot aufnehmen (andere Angebote bleiben unverändert): steht der Artikel schon in einem anderen Angebot, wird dieser …
- `openArtikelwahl(opt)`
- `werbKandidaten(oid)` – Artikel eines Angebots für das Fenster „Werbung schalten“ (Reihenfolge wie im Editor)
- `werbungAuswahl(oid, ids, fertig)`
- `openWerbung()`

**Sonderposten (kurzes MHD, solange der Vorrat reicht)**

- `openSale(id)`
- `mhdList()`
- `renderMhd()`
- `openRestposten(oid)`
- `restCount()`

**Stammdaten (je Artikelnummer)**

- `loadVkGruppen()`
- `loadMaster(force)`
- `masterOf(code)`
- `draftByCode(m)`
- `applyMasterTo(m, onlyCode)` – Stammdaten auf Artikel anwenden (nur eindeutige Artikelnummern)
- `migrateMaster()` – Stammdaten an die Regeln anpassen (einmalig je Änderung der Regeln, danach ohne Wirkung)
- `addFromDraft()`
- `setMasterState(st, msg)`
- `masterChanged()`
- `saveMaster()`
- `offerStatus(e, by)`
- `renderMasterView()`
- `vkFilterOpts()`
- `renderMasterList()`
- `masterAusCsv(buf)`
- `masterNeuAus(r)`
- `masterZusammenfuehren(res, basis)` – Gelesene Zeilen mit den Stammdaten zusammenführen: neue Artikel mit vorgeschlagenen Merkmalen, bestehende nur um VK-Gruppe/GTIN ergänzt (leere Felder in der …
- `masterImportDatei(file)`
- `openMasterNew(code)`
- `saveItemToMaster(it)` – Artikel-Dialog: aktuellen Artikel als Stammdaten speichern

**Schnittstelle für admin-verwaltung.js**

- `zeigeUmgezogen(ziel)` – Alter Eingabebereich stillgelegt: nur ein Hinweis mit Verweis, danach Weiterleitung (Adresse vom Server, nur https)
- `zeigeKeinZugang(name)` – Kein Modulzugang (Rolle ohne „<modul>.zugang“): der Server sperrt alle Aktionen dieses Bereichs; hier nur der Hinweis

## `app/assets/frontend.js`

_Wochenangebot – öffentliches Frontend_

**Hilfsfunktionen**

- `fold(s)` – Zeichenweise, längenerhaltende Normalisierung (für Suche und Hervorhebung)

**Daten**

- `frachtFuer(kg)` – Frachtanteil wie auf dem Server (lib/fracht.php) – nur zur Anzeige, berechnet wird beim Absenden auf dem Server
- `prepare(raw)`
- `offlineHinweis(stand)` – Web-App ohne Verbindung: sw.js liefert das zuletzt geladene öffentliche Angebot mit „X-WA-Offline: <Zeitpunkt>“
- `loadData()`

**Zustand**

- `optionLabel(f, v)`
- `facetOptions(f)`
- `activeFilterCount()`

**Filtern & Sortieren**

- `passes(it, skip)`
- `sortItems(list, key, dir)`
- `compute()`

**Bausteine**

- `hl(text, toks)`
- `starHTML(it)`
- `tagHTML(it, withBrand)`
- `priceMain(p)`
- `priceHTML(it)`

**Werbung: vom Angebot hervorgehobene Artikel (meta.werbung, je Angebot vom Server aufgelöst)**

- `werbungHTML(eigeneKarte)`

**Kopf, Kennzahlen, Navigation**

- `renderStatic()`
- `offerTitle()`
- `renderBanner()`

**Filter-Panel**

- `syncDrops()`
- `buildFilters()`
- `updateFacetUI()`

**Ergebnisliste**

- `describeFilters()`
- `renderChips()`
- `renderHits()`
- `renderFavbar()`
- `thHTML(key, label, cls)`
- `groupHeaderInfo(list)`
- `renderTable(list, grouped)`

**Angebotsliste (Standard): Aufbau wie die gedruckte Liste – Abschnitte, Gruppen in Spalten, Nr. · Bezeichnung · € / Kg**

- `plName(it)` – „Fleischmeister“ in der Bezeichnung weglassen, wenn Gruppe oder Abschnitt die Marke schon nennen (dort ist sie Überschrift)
- `plLabels(items)`
- `plCells(it, labels)`
- `plFill(units, k, H)` – Verteilung auf k Spalten. units: [{key, items, weight(i), head}]; cap = feste Spaltenhöhe (Druck) oder null (ausgleichen)
- `plBalance(units, k)`
- `plUnits(list, grouped, charsPerLine)`
- `plSections(units)`
- `plBlockHTML(b, mode)` – Ein Block: Nummer \| Bezeichnung \| Preis(e) \| [Merken].
- `renderListe(list, grouped)`
- `buildPrintListe(list, grouped, scopeText)`
- `cardHTML(it, grouped)`
- `renderCards(list, grouped)`
- `renderEmpty()`
- `renderList()`
- `render()`
- `renderOrderHint()` – Bestellansicht ohne Mengen-Spalte: sagen, warum und wie es geht

**Merkliste**

- `updateFavCount()`
- `renderMerk()` – Merkliste als Spalte neben der Liste (breite Fenster)
- `saveFavs()`
- `kundeMerklisteLaden()` – Beim ersten Anmelden wird eine im Browser angelegte Merkliste ins Kundenkonto übernommen
- `toggleFav(key)`

**Detailansicht**

- `comparables(it)`
- `cmpListHTML(list, curId)`
- `setDetailFavBtn(b, on)`
- `openDetail(id)`

**Preisvergleich**

- `validCompareSets()`
- `openCompare(key)`
- `renderCompare(sets)`

**Druck**

- `openPrint(scope)`
- `printPriceCell(p)`
- `printAltNote(it)`
- `buildPrint({…})`
- `doPrint(opts)`
- `renderStaticTitle()`

**CSV**

- `csvCell(v)`
- `exportCSV(list, suffix)`
- `download(name, content, type)`

**Teilen**

- `copyText(text)`
- `shareLink(withState)`

**URL-Zustand**

- `syncUrl()`
- `readUrl()`

**Toast**

- `toast(msg, ms)`

**Design (hell/dunkel)**

- `effectiveTheme()`
- `updateThemeBtn()`

**Mobile Filter**

- `setFiltersOpen(open)`
- `syncFilterInert()` – Geschlossene Filterleiste (Schublade auf Tablet/Handy) aus der Tab-Reihenfolge nehmen

**Ereignisse**

- `resetFilters(alsoSearch)`
- `parseDec(v)`
- `priceHint(err)`
- `onPriceInput()`
- `scrollToResults()`
- `bind()`

**Bestellwunsch (nur angemeldete Kunden, wenn freigeschaltet)**

- `parseQty(v)`
- `qtyHTML(it)`
- `orderKey()` – Kennung und Fingerabdruck des Bestellwunsches (Schutz vor Doppelversand). crypto.subtle/randomUUID gibt es nur über HTTPS – ohne sie ein einfacher Ersatz, …
- `orderFingerprint(text)`
- `loadCart()` – Gemerkt wird je Position die Menge und der Artikelschlüssel: verschiebt sich eine Position (neue Woche, geändertes Einzelangebot), wird die Menge dem …
- `saveCart()`
- `cartTotals()`
- `renderOrderbar()`
- `setQty(id, q, input)`
- `orderLines()`
- `openOrder()`
- `orderFootHTML(t)`
- `frachtMsgHTML(t)` – Meldung zum Gewicht: unter der Frachtfreigrenze wird der Frachtanteil automatisch aufgeschlagen
- `refreshOrderDialog()`
- `sendOrder(btn)`
- `bindOrder()`
- `openCustomerOrders(offset, nr)`

**Kunden-Anmeldung**

- `kundeApi(action, body)`
- `setOfferParam(id)`
- `kundeStart()`
- `renderKundeBtn()`
- `renderLocked(msg, withLogin)`
- `openKundeLogin()`
- `openKundePw(forced)`
- `kundeLogout()`
- `bindKunde()`
- `kundeLinkStart()` – Link aus Einladung / Passwort zurücksetzen: …/#zugang=<Einmal-Code>.
- `abmeldenStart()` – Abmeldelink aus der Angebotsmail: …/#abmelden=<Code>.
- `renderWartung(w)` – Wartungsseite für Kunden und Besucher

## `app/assets/offer-core.js`

_Wochenangebot – gemeinsamer Kern für Frontend und Eingabebereich - Excel-Leser (ohne externe Bibliothek) - Parser der Angebotsliste → editierbares Datenmodell - Anreicherung (Merkmale, Teilstück, Merklisten-Schlüssel …_

**Konstanten**

**Excel lesen**

- `xlsxReadWorkbook(arrayBuffer)`
- `attr(s, name)`
- `decodeXml(s)`
- `textOf(frag)`
- `parseSharedStrings(xml)`
- `colIndex(letters)`
- `parseSheet(xml, shared)`
- `unzip(buffer, filter)`
- `inflateRaw(data)`

**Hilfen**

- `colName(c)`
- `parsePrice(v)` – Preis aus Zelle oder Eingabefeld: Zahl, „23,30“, „a. Anfr.“, „-“, leer
- `speciesFromName(t)`
- `speciesFromHeader(t)`
- `originFrom(t)`
- `conditionFrom(t)`
- `suggestAttributes(name, groupName, sectionName)` – Vorschläge für neue/umbenannte Artikel (Eingabebereich)

**Parser**

- `parseOfferWorkbook(sheets, fileName)`
- `parseOfferGrid(grid, meta)`

**Anreicherung**

- `cutFrom(t)`
- `isoWeekRange(week, year)`
- `enrichOffer(model)` – Liefert eine angereicherte Kopie für die Anzeige; das Modell bleibt unverändert.

**Vergleich & Prüfung**

- `matchKey(it, groups)`
- `saleFor(it, oid)` – Sonderpreis „solange der Vorrat reicht“: Grundpreis für alle Angebote, je Angebot änderbar
- `diffOffers(oldM, newM)`
- `validateModel(m)` – Prüft ein Modell vor dem Speichern/Veröffentlichen
- `stripFrisch(name)` – „frisch“ gehört in den Zustand, nicht in die Bezeichnung.
- `normalizeItem(it, group)` – Bezeichnung und Herkunft vereinheitlichen: – „frisch“ nur im Zustand – Eigenmarke „Fleischmeister“ (Gruppe/Bereich) steht in der Bezeichnung – Herkunft als …

**Gemeinsames Bearbeiten**

- `canon(v)`
- `merge3(b, m, t, onConflict)`
- `mergeFields(b, m, t, skip, onConflict)`
- `mergeOrder(baseIds, mineIds, theirIds, keep)`
- `mergeList(bl, ml, tl, label, conflicts, mergeOne)`
- `mergeModels(base, mine, theirs)`

## `app/assets/webapp.js`

_Web-App: Offline-Speicher (sw.js) anmelden und Hinweis „Als App auf den Home-Bildschirm“._

- `zeigen(inhalt)`

## `app/sw.js`

_Web-App (zum Home-Bildschirm hinzugefügt)_

- `art(req)`
- `oeffentlich(res)` – öffentlich speicherbar: keine privaten Antworten (Kundenangebote sind „private, no-store“)
- `aufraeumen(cache, key)` – ältere Fassungen derselben Datei (anderes ?v=) entfernen, damit der Speicher nicht wächst

## `tests/e2e/order_setup.py`

_Gemeinsame Vorbereitung der Bestell-Testgruppen_

- `setup()`
- `customer(username, firma)`

## `tests/e2e/test_angebote.py`

_Mehrere Angebote: Kundenangebote mit eigenen Preisen, eigene Artikelliste je Angebot (Artikel hinzufügen wie im Einzelangebot, entfernen nur im gewählten Angebot, Umstellung „folgt dem Wochenangebot“ → eigene Liste), …_

- `check(n, c, i)`
- `login(pg, user, pw)`
- `post(pg, action, body)`
- `get(pg, q)`
- `bestaetigt(pg, toast_text, timeout)`
- `post_bestaetigt(pg, action, body)`
- `row(pg, code)`
- `wait_saved(pg)`
- `tab(pg, label)`
- `zahl(pg, label)`
- `codes(pg)`
- `hinzufuegen(pg, q, preise)` – „Artikel hinzufügen“: Suche, markieren, Preis je Artikel, übernehmen
- `item(offer, code)`

## `tests/e2e/test_angebotsliste.py`

_Angebotsliste (Standardansicht der Angebotsseite)_

- `check(n, c, i)`

## `tests/e2e/test_bestellung.py`

_Bestellwunsch aus dem Portal_

- `check(n, c, i)`

**Einstellungen**

**Bestellwunsch per API**

**Fracht und Hinweis (Verwaltung)**

- `_pub_offer(etag)`

## `tests/e2e/test_design.py`

_Gestaltung der Angebotsseite („Klar“ mit dem Design „Liquid Glass“: schwebende Glas-Kopfzeile, Kapseln, Liste als Glaskarte): lokale Schriften (keine fremden Server), Kopf, Filterleiste mit Aufklappmenüs (Desktop) bzw._

- `check(n, c, i)`
- `page(w, h, scheme)`
- `_leer(route)`

## `tests/e2e/test_editor_aux.py`

_Testgruppe editor_aux_

- `check(n, c, i)`
- `login(pg, user, pw)`
- `post(pg, action, body)`

## `tests/e2e/test_einzelangebote.py`

_Einzelangebote (Angebot bearbeiten → Einzelangebote)_

- `check(n, c, i)`
- `bestaetigung_ablaufen(cl)`
- `doc(name)`
- `kunde(username, firma, email, zugang)`

**Rechte**

**Artikelsuche**

**Prüfung**

**Freigabe und Portal**

**Bestellwunsch**

**E-Mail**

- `pdf_inhalt(data)` – Text der Seiteninhalte (FlateDecode) eines PDF, als Windows-1252 gelesen.
- `hole(cl, action)`

**Zurückziehen, Ablauf, Löschen**

**Oberfläche**

- `ed_count(pg)`

## `tests/e2e/test_fehlerpruefung.py`

_Regressionstests der Design- und Fehlerprüfung_

- `check(n, c, i)`
- `doc(name)`

**Angebots-IDs**

**KW 53 nur in Jahren mit 53 ISO-Wochen**

**Rechte: mail_info, history_prev**

**Einzelangebote**

- `kunde(username, firma)`

## `tests/e2e/test_frontend.py`

_search_

- `check(name, cond, info)`
- `drop(fd)` – filters (Desktop: Aufklappmenüs in der Filterleiste)

## `tests/e2e/test_gemeinsam.py`

_Mehrere Mitarbeiter bearbeiten den Entwurf gleichzeitig_

- `check(n, c, i)`
- `sess_seen(cli, value)` – Liest (bzw. setzt) den Zeitpunkt der letzten Aktivität in der getrennten Test-Sitzungsablage.
- `price(m, iid)`
- `set_price(m, iid, v)`
- `open_editor(user, password)`
- `sync(pg)`
- `pin(pg, iid)`
- `wait_saved(pg)`

## `tests/e2e/test_hist.py`

_Testgruppe hist: Preisverlauf – Import alter Angebotslisten, Zeiträume, Datendialog._

- `check(n, c, i)`

## `tests/e2e/test_kunden_mail.py`

_E-Mail an Kunden: Einladung mit Einmal-Link, Passwort-Link, Angebotslink, Wochenversand, Testmail._

- `check(n, c, i)`
- `link_of(m)`

**Status**

**Einladung**

**Einmal-Link**

**Passwort zurücksetzen**

**Angebotslink**

**Header-Injection, Signatur**

**Wochenversand**

- `mk(firma, nr, email, user, **kw)`

**Abmelden vom Wochenangebot**

- `oneclick(method, tok)`

## `tests/e2e/test_legal_pages.py`

_Öffentlich erreichbar, Navigation ohne JavaScript und mobile Darstellung._

- `check(name, value)`

## `tests/e2e/test_order_management.py`

_Testgruppe order_management_

- `check(n, c)`

## `tests/e2e/test_order_management_ui.py`

_Artikelnummer als normale Tabellenzelle (Klasse „mono“ ist in app.css das runde Kategorie-Monogramm)_

- `check(name, condition)`

## `tests/e2e/test_order_outbox.py`

_Testgruppe order_outbox: dauerhafte Versandaufträge für Bestellwunsch-Mails – Teilfehler, SMTP-Ausfall, Sperren, Neuversand._

- `check(name, ok)`
- `detail(n)`
- `retry(n, j, **extra)`
- `mutate(fn)`
- `stored_jobs(n)`
- `grab(data)`
- `interrupted(all)` – Simulate process death after persisting a claim, before recording an outcome.
- `legacy(all)` – Old orders have no reconstructed recipients or guessed copy state.

## `tests/e2e/test_order_outbox_ui.py`

_Testgruppe order_outbox_ui_

- `check(n, c)`

## `tests/e2e/test_p0.py`

_1) leeres System ohne WA_INSTALLED → Ersteinrichtung erlaubt_

- `check(n, c, i)`
- `srv(port, data, env)`
- `st(url)`
- `system_neu()` – 5) Sicherungs-Status im Modul Sicherheit, Reiter System (bis 27.10.2026 Verwaltung → System)

## `tests/e2e/test_restposten.py`

_Sonderposten (kurzes MHD, solange der Vorrat reicht), Ausblenden in jedem Angebot, eigene Artikelliste (Sonderposten nur für eigene Artikel), Kein-Bestand-Zeichen und Sonderposten-Mail je Angebot._

- `check(n, c, i)`
- `customer(firma, user, offers, email, mail)`
- `offer_as(user, oid)`
- `_etag_abruf(etag)`

## `tests/e2e/test_revert.py`

_sauberer Ausgangspunkt: einmal veröffentlichen_

- `check(n, c, i)`
- `row(pg, code)`
- `wait_saved(pg)`
- `open_pub(pg)`
- `pub_text(pg)`
- `offer(pg)`

## `tests/e2e/test_sidenav.py`

_Testgruppe sidenav: Navigation des Eingabebereichs, Sichtbarkeit je Rolle, Kopfzeile ohne Überlappung und Darstellung je Bildschirmbreite._

- `check(n, c, i)`
- `login(pg, u, pw)`
- `zentral(route, adresse)` – Rückweg zum Dashboard: Antwort des Servers unter zentraler Anmeldung nachgestellt (echter Ablauf: tests/oidc/)
- `verwaltung(route)`

## `tests/e2e/test_sys.py`

_Setup_

- `check(n, c, info)`
- `pub_price(code)`
- `wait_saved()`
- `row(code)`

**Setup**

**Manual price edit**

- `sichtbar(n)` – search/filter in editor – auf das erwartete Ergebnis warten statt fester Wartezeit (Filter greift verzögert)

## `tests/e2e/test_versand.py`

_Wochenangebot an Kunden senden_

- `check(n, c, i)`
- `login(user, password)`

## `tests/e2e/test_wartung.py`

_Wartungsmodus und erweiterte Übersicht im Eingabebereich._

- `check(n, c, i)`

## `tests/e2e/test_web_app.py`

_Web-App (zum Home-Bildschirm)_

- `check(n, c)`
- `png_groesse(daten)` – Breite und Höhe aus dem PNG-Kopf (ohne Bildbibliothek, wie in der CI verfügbar).
- `get(path)`

**Manifest und Symbole**

- `server(an)`
