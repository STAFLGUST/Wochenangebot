# Funktionen: Angebot (`angebot`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

50 Dateien, 780 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

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
- `werbung_bloecke(e)` – Blöcke eines Eintrags in Reihenfolge: erster Block, danach „weitere“ (ungeprüft)
- `werbung_eintrag(bloecke)` – Blöcke wieder zu einem Eintrag zusammensetzen (leere fallen weg, ein späterer rückt nach vorn); null = keine Werbung
- `werbung_block_clean(e, iids)`
- `clean_werbung(w, known, iids)`
- `clean_money(x, what)` – Empfehlung (bis 11/2026 „Sonderpreis“) je Artikel und Angebot: $item['sale'] = {value: Empfehlungspreis für alle Angebote \| mark: true (ohne Preisänderung), …
- `clean_sale(v, where, known)`
- `empfehlung_fuer(it, oid)` – Empfehlung eines Artikels in einem Angebot: null = keine, sonst ['preis' => Empfehlungspreis \| null (nur hervorheben)]
- `sale_for(it, oid)` – Empfehlungspreis (Sonderposten „solange der Vorrat reicht“) eines Artikels in einem Angebot, sonst null
- `stock_codes()` – Artikelnummern mit eingelagertem Bestand (null = keine Bestandsliste vorhanden)
- `sold_out(it)`
- `offer_resolve(m, def, ausverkauftAusblenden)` – Angebot für die Auslieferung: nur Preise dieses Angebots, keine Kundenpreise anderer Angebote, keine ausgeblendeten Artikel, Sonderpreise aufgelöst (ohne …
- `kw_gueltig(woche, jahr)` – Kalenderwoche nach ISO 8601: KW 53 gibt es nur in Jahren mit 53 Wochen (der 28.12. liegt immer in der letzten)
- `clean_model(m, strict)` – Übernimmt nur bekannte Felder in bekannten Formaten

**Gemeinsames Bearbeiten des Entwurfs**

- `draft_rev(draft)`
- `draft_end(draft, why)`
- `draft_conflict(draft)`

**Veröffentlichen und Änderungsliste (Schnittstelle des Angebots)**

- `angebot_veroeffentlichen(modell, revision)`
- `angebot_aufbau_geaendert(pub, neu)` – Weicht der Aufbau (Reihenfolge der Gruppen, Bereich je Gruppe, Gruppe und Reihenfolge der Artikel) vom veröffentlichten Stand ab? Gleiche Regel wie …
- `angebot_aenderungen(pub, dr)` – Unveröffentlichte Änderungen des Entwurfs als Zeilen für die Liste „Veröffentlichen“ (Modul Versand).
- `angebot_stand()` – Stand des Angebots für das Modul Versand – nur Zahlen und Namen, keine Preise: veröffentlichter Stand und Entwurf (Woche, Zeitpunkt, wer zuletzt gespeichert …

## `app/api/lib/einzelangebote.php`

_Einzelangebote: ein Angebot für genau einen Kunden (Angebot bearbeiten → Einzelangebote)._

- `einzel_load()`
- `einzel_find(d, id)`
- `einzel_titel(e)`
- `einzel_gueltig(e)`
- `einzel_sichtbar(e)`
- `einzel_stand(prev)` – Stand der Freigabe (Millisekunden, immer später als der vorige): Bestellwünsche auf einen älteren Stand werden abgewiesen
- `einzel_clean(b)` – Eingaben prüfen (Kopf und Positionen)

**Partien (Entscheidung des Inhabers 13.11.2026, GR-001 Version 2)**

- `einzel_bestand_partien()`
- `einzel_partien_aufloesen(pos, alt, me)` – Partien der Positionen auflösen ($alt: bisher gespeichertes Einzelangebot oder null).
- `einzel_partie_menge(p)` – Für den Kunden angebotene Menge einer Partie-Position: eingetragene Menge, sonst die ganze Partie (Schnappschuss, auf zwei Stellen abgerundet – angezeigt …
- `einzel_partie_teile(p, mitMenge)` – Partieangaben für Kunde, Druck, PDF und E-Mail: „Charge P-0002 · MHD 04.12.2026 · 25,00 kg“
- `einzel_partie_text(p, mitMenge)`
- `einzel_summe(e)` – Summen (Positionen mit Menge und Preis; Partie ohne eingetragene Menge zählt mit der ganzen Partie)
- `einzel_view(e, kunden)` – Ansicht für den Eingabebereich (mit Kundenname)
- `einzel_kunden_map()`

**Schnittstelle für Eingabebereich und CRM (regeln/datenverantwortung.toml: CRM liest und schreibt nur hierüber)**

- `einzel_liste(kid)` – Liste ohne Positionen (mit Anzahl), zuletzt geändert zuerst – alle bzw. nur die eines Kunden ($kid)
- `einzel_holen(id)` – Ein Einzelangebot (Rohdaten) oder null
- `einzel_speichern(b, me)` – Anlegen ($b['id'] leer: neue Nummer E-JJJJ-0001) oder ändern (mit revision, sonst 409); Protokoll; Ansicht zurück
- `einzel_status_setzen(b, me)` – Status setzen: entwurf, freigegeben (Portal, braucht Positionen und Gültigkeit), zurueckgezogen; Ansicht zurück
- `einzel_entfernen(id)` – Löschen (mit Protokoll)
- `einzel_mail(b, me, cfg)` – Per E-Mail an den Kunden ($b: id, note, format liste\|pdf); Versand im Verlauf des Angebots und im Protokoll; Ansicht zurück.
- `einzel_pdf_senden(e)` – PDF eines Einzelangebots ausliefern (Vorschau des E-Mail-Anhangs) – beendet die Anfrage

**Portal**

- `einzel_fuer_kunde(c)` – Für den Kunden sichtbare Einzelangebote (freigegeben, noch gültig)
- `einzel_von_kennung(oid)`
- `einzel_model(e)` – Angebotsmodell wie offer_resolve() – nur Name, Merkmale und Preis, kein Bestand.

**Artikelsuche im Eingabebereich**

- `einzel_artikel(mitBestand, mitEk)` – Alle bekannten Artikel: Stammdaten (mit Merkmalen und VK-Gruppe), Bestand (eingelagert, erfasst, gesamt; je Partie und je erwarteter Lieferung) und Preis im …

**PDF im Design der Angebotsansicht (A4 quer, drei Spalten)**

- `einzel_pdf(e, c)` – Wie die Druckliste der Angebotsseite: Logo und Titel, Blöcke mit Kopfzeile „€/kg“, Zebrastreifen, Seitenzahlen, am Seitenfuß die Fußzeile des Briefbogens …
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
- `fracht_public(angemeldet)` – $angemeldet: Mitarbeiter oder Kunde – nur dann enthält die Fußzeile geschützte Bankangaben (module/angebot/druck.php)

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
- `abmelde_hinweis_senden(c, ab, t)` – Hinweis an das Team über eine Ab- bzw. Wiederanmeldung ($t: Zeitpunkt der Änderung, UTC)

**Bestellwünsche**

- `order_settings()` – Einstellungen der Bestellfunktion.
- `order_settings_speichern(neu, wer)` – Einstellungen speichern ($neu: enabled, copy und/oder to – fehlende bleiben).
- `order_enabled()` – Bestellfunktion nutzbar?
- `de_num(v, dec)`
- `de_qty(v)` – Menge immer mit 2 Nachkommastellen wie überall (12,50 kg; app/assets/format.js)
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

**Versand an Kunden (Schnittstelle des Angebots)**

- `wochenmail_grund(c)` – Warum bekommt ein Kunde die Wochen-Mail nicht? '' = er bekommt sie
- `versand_kunde_zeile(c, grund, wk)` – Empfänger als Zeile der Liste: nur, was die Auswahl braucht (keine Anschrift, keine Zugangsdaten)
- `wochenmail_empfaenger()` – Empfänger des Wochenangebots: woche (mail_week oder null), empfaenger (bekommen die Mail), ausgeschlossen (mit Grund)
- `wochenmail_senden(cfg, ids, note, week, year)` – Wochenangebot an höchstens 20 Kunden senden (ein Teil): Ergebnis je Kunden-ID in der Reihenfolge von $ids.
- `sonderposten_empfaenger(def)` – Sonderposten eines Angebots: Artikel (wie veröffentlicht), Empfänger (nur Kunden dieses Angebots, GR-005) mit Grund, Stand
- `sonderposten_senden(cfg, def, ids, note, publishedAt)` – Sonderposten an höchstens 200 Kunden des Angebots senden (ein Teil): Ergebnis je Kunden-ID.
- `ksess_begrenzen(r, kid)` – Register auf die Obergrenzen kürzen: erst je Zugang, dann insgesamt (die zuletzt benutzten bleiben)
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

## `app/api/module/angebot/druck.php`

_Druck der Angebote: Fußzeile des Briefbogens unter jedem gedruckten Angebot (Wunsch des Inhabers 13.11.2026)._

- `druck_fuss_text(v, zeilen, laenge)` – Text einer Spalte: höchstens DRUCK_FUSS_ZEILEN Zeilen, ohne Steuerzeichen, Leerzeichen bereinigt
- `druck_fuss_clean(in)` – Eingabe prüfen: drei Spalten, zwei Zeilen, Modus – unbekannte Felder fallen weg
- `druck_fuss_gespeichert()` – Gespeicherte Einstellung (roh) oder null
- `druck_fuss()` – Wirksame Fußzeile: eigene Texte, sonst die Vorgabe; „eigen“ sagt, ob Texte hinterlegt sind
- `druck_angemeldet()` – Angemeldet im Sinne der Fußzeile: Mitarbeiter oder Kunde mit eigenem Passwort.
- `druck_fuss_public(angemeldet)` – Für die Angebotsseite (Druck): nur Texte und Modus.
- `druck_fuss_speichern(in, me)` – Speichern (nur das Feld „druck“; Fracht und Hinweis bleiben unverändert).

**Fußzeile im PDF des Einzelangebots (lib/pdf.php)**

- `druck_fuss_ordnen(t)` – „ * “ als Trenner → „ · “, kein Leerzeichen vor Doppelpunkt und innerhalb von Klammern (wie ordnen() in angebot-druck.js)
- `druck_fuss_pdf_satz(f, w)` – Aufbau der Fußzeile für die Breite $w: Spalten (Zeilen je Spalte), umbrochene Registerzeilen, Siegelbreite, Höhen
- `druck_fuss_pdf_hoehe(f, w)` – Höhe der Fußzeile in pt (0 = keine); $w: Breite wie beim Zeichnen
- `druck_fuss_pdf(pdf, f, x, y, w)` – Fußzeile zeichnen: $x linker Rand, $y Oberkante (Linie), $w Breite

## `app/api/module/angebot/import.php`

_Importvertrag des Moduls Angebot – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md). - Preisverlauf: frühere Angebotslisten (.xlsx) als Wochen im Preisverlauf._

- `import_arten_angebot()`

**Artikelpreise (CSV)**

- `angebot_preise_aktuelle_woche()` – Aktuelle Kalenderwoche (ISO 8601, Zeitzone der Anwendung) als „JJJJ-WW“ – Standard der Option „Angebotswoche“
- `angebot_preise_wochen()` – Auswahl der Angebotswoche: vier Wochen zurück bis acht Wochen voraus, die aktuelle gekennzeichnet
- `angebot_code_key(c)` – Schlüssel einer Artikelnummer wie im Browser (StockCore.normCode): reine Zahlen ohne führende Nullen, sonst Großbuchstaben
- `angebot_slug(name)` – Kennung eines neuen Angebots aus dem Namen (wie slug() im Eingabebereich)
- `angebot_preis_text(v)` – Preise eintragen in 2 Nachkommastellen, mehr nur wenn vorhanden
- `angebot_preise_zeilen(e)` – Zeilen des Lesers prüfen: {zeile, code, gruppe, preis}.
- `angebot_preise_woche(v)` – Gewählte Angebotswoche „JJJJ-WW“ → [Woche, Jahr] (nur gültige ISO-Wochen; sonst die aktuelle)
- `angebot_preise_basis()` – Ausgangsstand: Entwurf, sonst veröffentlichtes Angebot; Stand = Revision des Entwurfs und der Angebotsliste
- `angebot_preise_plan(model, offers, rows, gewaehlt)` – Zuordnung der Preise zu Angeboten und Artikeln (ohne zu schreiben).
- `angebot_preise_ergebnis(plan, model, fehler, woche, opt, stand)` – Vorschau/Ergebnis im Format der Importzentrale aus Plan, Fehlerzeilen und Angebotswoche
- `angebot_preise_vorschau(e, me)`
- `angebote_fuer_gruppen_anlegen(neuName, rev, me)` – Neue Angebote für Kundengruppen ohne Angebot (eigene Artikelliste, Gruppe zugeordnet) – Regeln wie offers_save: eindeutige Namen, nie die ID eines gelöschten …
- `angebot_preise_uebernehmen(e, me)`
- `preisverlauf_woche_speichern(week, year, items, source)` – Eine Woche speichern (ersetzt eine vorhandene Woche) und protokollieren – Aktion history_import und Importzentrale
- `preisverlauf_import_wochen(e)` – Wochen der Dateien prüfen: gültige Woche, Artikel; doppelte Woche → die spätere Datei zählt (wie im Preisverlauf)
- `preisverlauf_import_vorschau(e, me)`
- `preisverlauf_import_uebernehmen(e, me)`

## `app/api/module/angebot/winab-export.php`

_Export des Wochenangebots für WinAB (Auftrag des Inhabers 05.11.2026)_

- `winab_preis(v)` – Preis für WinAB: 26,1 → „26,10“, 12.345 → „12,345“
- `winab_zeilen(pub)` – Zeilen [Artikelnummer, Preis] aus einem veröffentlichten Angebotsmodell (höchster Preis je Nummer) und Zählung
- `winab_export()` – Datei für den Download: Name, Inhalt und Zahlen; 422 ohne veröffentlichtes Angebot oder ohne Preise

## `app/api/module/angebot/wochen.php`

_Angebot · Frühere Wochen ansehen und Wochenablage (Wünsche des Inhabers 13.11.2026): das veröffentlichte Angebot einer Kalenderwoche – Wochenangebot oder ein Kundenangebot – nur für Mitarbeiter mit Modulzugang …_

- `angebot_woche_kw(m)` – KW eines gespeicherten Angebots als „JJJJ-WW“ (nur gültige ISO-Wochen), sonst null
- `angebot_woche_definitionen()` – Angebotsdefinitionen als Schnappschuss (GR-106): ID, Name und Regel der Artikelliste je Kundenangebot – ohne Kundengruppen
- `angebot_woche_ablegen(model)` – Beim Veröffentlichen (angebot_veroeffentlichen, unter der Sperre „entwurf“): neuen Stand je KW ablegen, ersetzt dieselbe KW
- `angebot_woche_retten(v)` – Vor dem Löschen einer alten Version (keep_versions): in die Ablage retten, wenn diese KW dort keinen neueren Stand hat
- `angebot_wochen_verzeichnis()` – Gespeicherte Wochen (aufsteigend) und je KW der späteste Stand aus aktuellem Angebot und versionen/*: [Wochen => true, 'JJJJ-WW' => ['art' => …
- `angebot_woche_aus_historie(h)` – Preisstand des Preisverlaufs als Angebotsmodell für offer_resolve: Angebotsgruppen aus den gespeicherten Gruppennamen (Reihenfolge wie gespeichert), ohne …
- `angebot_woche(woche, oid)` – Aktion angebot_woche: KW „JJJJ-WW“ und Angebot (leer = Wochenangebot) → aufgelöstes Angebot dieser Woche oder null

## `app/api/order_outbox.php`

_Versandaufträge eines Bestellwunschs: je Empfänger ein Auftrag im selben Dokument (bestellungen) wie der Vorgang._

- `order_outbox_job(kind, to, name)`
- `order_outbox_create(o)` – Aufträge eines neuen Bestellwunschs; ohne Sicht auf die internen Daten (Kundenseite ab Trennstufe 2) nur der offene Auftrag
- `order_outbox_empfaenger(o)` – Aufträge je Empfänger aus den aktuellen Einstellungen (Team) und den Stammdaten des Kunden (Kopie).
- `order_kopie_name(o)`
- `order_kunden_email(kid)` – Adresse eines Kunden aus den Stammdaten (null: unbekannt, inaktiv oder ohne gültige Adresse) – nie aus dem Vorgang
- `order_outbox_vorbereiten(nr)` – Offenen Auftrag der Kundenseite ausführen (unter der Versandsperre des Vorgangs): Schnappschuss ergänzen, Aufträge je Empfänger anlegen.
- `order_outbox_pruefen(o, j, ausdruecklich)` – Darf dieser Auftrag jetzt verschickt werden? null = ja, sonst der Grund (Auftrag wird verworfen, nicht wiederholt).
- `order_tageszahl(kid, typ, to)` – Zugestellte E-Mails dieser Art an diese Adresse für diesen Kunden in den letzten 24 Stunden (Versandprotokoll)
- `order_outbox_summary(o)`
- `order_outbox_view(o)`
- `order_outbox_cleanup_locks(own)` – Sperrdateien abgeschlossener Vorgänge gelegentlich entfernen (älter als 2 Tage, nicht die eigene).
- `order_outbox_send(nr, jobId, expected, by, ausdruecklich)` – No SQLite transaction spans SMTP.

## `app/api/orders.php`

_Shared order operations for the website and future app clients._

- `order_request_hash(body)`
- `angebot_startseite(me)` – Startseite des Dashboards („Heute für Sie“, lib/startseite.php): für Mitarbeiter, die Bestellwünsche bearbeiten dürfen, die neuen (noch nicht angenommenen) …
- `order_state(o, staff)` – „Bestätigt“ ist eine interne Kennzeichnung und keine Auftragsbestätigung – Kunden sehen dort weiter „In Bearbeitung“.
- `order_view(o, staff)`
- `order_receipt(o, replayed)`
- `order_replay(all, kid, key, hash)`
- `orders_action(action)`

## `app/assets/admin-artikelwahl.js`

_Eingabebereich – Fenster „Artikel hinzufügen“ (gemeinsam für „Angebot bearbeiten“ und Einzelangebote) Links die VK-Gruppen (mit Anzahl), rechts die Artikel der gewählten Gruppe als Tabelle mit Häkchen, eingelagertem …_

- `bestandHTML(a, kurz)`
- `naechsteEta(a)` – Nächste erwartete Ankunft (frühestes Datum; ohne Datum: keine Angabe)
- `hayVon(a)` – Suchtext eines Artikels (einmal je Öffnen berechnet): Nummer mit und ohne führende Nullen, Bezeichnung (auch die der Stammdaten/Bestandsliste), Herkunft und …
- `passt(a, toks)`
- `pickBasis()` – Treffer der Filter/Suche (ohne Gruppenwahl) und Anzahl je Gruppe
- `pickZeilen(basis)` – Angezeigte Artikel: gewählte Gruppe, sonst (bei Suche) alle Gruppen; sortiert nach Gruppe und Artikelnummer
- `oeffnen(c)`
- `renderPick()`
- `suchPlatzhalter()` – Suchfeld oben: sucht in der gewählten Gruppe, ohne gewählte Gruppe in allen Gruppen
- `gruppenFiltern()` – Gruppenleiste nach dem Suchtext links filtern (Nummer oder Name); die gewählte Gruppe bleibt sichtbar
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

**Partien**

- `partienVon(a)` – Eingelagerte Partien eines Artikels (nur mit Nummer und Menge; gleiche Nummer zusammengefasst wie auf dem Server), frühestes MHD zuerst
- `belegt(code, ausser)` – Partien desselben Artikels, die schon in anderen Positionen stehen: Partienummer → Positionsnummer (1-basiert)
- `partieHTML(p, i, a, ro)`
- `partieWaehlen(i, lot)`
- `weiterePartie(i)`
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

_Eingabebereich – Fenster „Werbung schalten“ (Angebot bearbeiten, Knopf „Werbung“ in der Werkzeugleiste) Bis zu zwei Werbungen je Angebot (Reiter „Werbung 1“/„Werbung 2“, „Weitere Werbung“ legt die zweite an): je …_

- `listeHTML()`
- `reiterHTML()` – Reiter der Werbungen (nur ab zwei Werbungen) und Knopf „Weitere Werbung“
- `blockHTML()` – Felder und Liste der angezeigten Werbung
- `zeigen(i)`
- `ausAuswahl(ids, artikel)` – Rückkehr aus der Artikelauswahl: ids = gewählte Artikel (Reihenfolge der Auswahl), artikel = aktuelle Liste des Angebots.
- `oeffnen(c)` – cfg: { angebot, eintrag: {titel, text?, artikel: [{id, text?}], weitere?: [{titel, text?, artikel}]} \| null, artikel: [{id, code, name, merkmale, preis}], …

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
- `empfehlungNichtUebernehmen(it, oid)` – Empfehlung gilt nur, wo sie gesetzt wurde: kommt ein Artikel mit Empfehlung neu in ein Angebot, steht er dort auf „keine Empfehlung“ (sonst übernähme er den …
- `nurIn(it, oid)` – Neuer Artikel nur für dieses Angebot: im Wochenangebot und in Angeboten, die ihm folgen, nicht enthalten
- `entfernen(it, oid)` – Aus einem Angebot entfernen.
- `namenBekannt(n)` – nur Einträge bestehender Kundenangebote; null, wenn keiner
- `setzeName(x, oid, text)` – eigene Bezeichnung setzen; leer oder gleich dem Basiswert = keine eigene
- `werbungBereinigen()` – Artikel, die nicht mehr im Angebot stehen, fallen aus dessen Werbung (unbekannte Angebote prüft der Server)
- `aufbauGeaendert()` – Weicht der Aufbau (Reihenfolge der Gruppen, Bereich je Gruppe, Gruppe und Reihenfolge der Artikel; gilt für alle Angebote) von der veröffentlichten Fassung …
- `artikelOrdnen(ziel)` – Artikel neu ordnen: ziel = Map(Gruppen-ID → Artikel-IDs in gewünschter Reihenfolge) für die „Anker“ (z. B. alle Artikel des gewählten Angebots); jeder Anker …
- `gruppenOrdnen(anker, reihe)` – Gruppen neu ordnen: „anker“ (IDs) kommen in die Reihenfolge „reihe“; jede andere Gruppe bleibt hinter ihrem Anker davor (Gruppen, die im gewählten Angebot …

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

**Angebotskategorien (Stammdaten der Verwaltung, Inhaber 05.11.2026)**

- `nachKategorienOrdnen()`
- `kategorienLaden(opts)` – Kategorien holen und den Entwurf danach ordnen; Rückgabe: ob der Entwurf neu geordnet wurde (still: ohne Hinweis)
- `vkOptionen(cur)` – VK-Gruppe einer Angebotsgruppe wählen (Gruppenkopf, nur mit Angebotskategorien): Nummer · Name → Kategorie
- `kategorienVorschlag()` – Vorschlag für die Stammdaten-Ansicht (Schnittstelle W.angebot): heutige Abschnitte des Angebots als Kategorien in ihrer Reihenfolge, darin die VK-Gruppen der …
- `normalizeNames(m)` – Merkmale vereinheitlichen: Herkunft als Kürzel, unbekannter Zustand aus „frisch“ in der Bezeichnung – die Bezeichnung bleibt unverändert
- `showEingabeWartung(w)`
- `renderWartungBanner()`
- `refreshWartung()`
- `openEditor()`

**Speichern**

- `setSaveState(st, msg)`
- `offenHTML()`
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
- `renderChanges()`
- `updatePublishBtn()` – früher Zahl am Knopf „Veröffentlichen“: jetzt die Zahl in der Statuszeile (nur wenn dort gerade der gespeicherte Stand steht)
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

**Angebote (Standard + Kundenangebote)**

- `loadOffers()`
- `angebotsseite(abfrage)` – Adresse der Angebotsseite auf diesem Host (Angebotsseite, Vorschau, Kundenangebot).
- `renderOfferBar()`
- `offerBarPlatzieren()`
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
- `preiseAusCsv(buf)` – Artikelpreise der Warenwirtschaft (CSV „Artikelpreise“: Preis-Art; Kundengruppe; Artikel; Preis) – Leser der Importart „angebot_preise“ der Importzentrale …
- `openCopy()`

**Vorschau**

- `pvFuss()`
- `pvLaden()`
- `openVorschau(oid)`

**Liste der unveröffentlichten Änderungen**

- `openPublish()`
- `changedFields(o, it)`
- `revertChange(kind, id)` – Eine einzelne Änderung gegenüber der veröffentlichten Fassung zurücknehmen
- `revertText(kind, id)`

**Versionen**

- `openVersions()`

**Menü & Kopf**

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
- `stockZeile(a, idx, m)` – Eine Zeile der Bestandsliste (auch für die Artikelkarte im Angebot): Preise, Angebot, Zugänge, Summen
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
- `zeigeStockKarte(a)` – Artikelkarte des Bestands – aus der Bestandsliste und aus dem Angebot (openBestandKarte)
- `bestandKarteMoeglich(it)` – Dieselbe Karte im Angebot (Wunsch Inhaber 06.11.2026): Klick auf den Bestand oder eine freie Fläche der Artikelzeile.
- `openBestandKarte(it)`
- `fillItemStock(it)` – Bestand im Artikel-Dialog des Angebots
- `stockAusDatei(file)` – Bestandsliste lesen (Leser des Moduls Bestand: stock-core.js) – hier und in der Importzentrale
- `stockImportFile(file)`
- `stockCSV()` – CSV (aktuelle Auswahl)
- `stockPDF(btn)` – PDF zum Weitergeben (Server, lib/bestand-pdf.php): nur Art.-Nr., Bezeichnung, eingelagerter Bestand, kürzestes MHD, Menge kürz.

**MHD-Liste an den Verkauf (Server: stock_mhd_senden, lib/bestand-mhd.php)**

- `mhdBild(list)` – Bild für die E-Mail: Schrift wie in der Anwendung (14 px), Spalten knapp, damit das Bild in der E-Mail in Originalgröße (Breite = Rückgabe „breite“, …
- `mhdAnVerkauf(btn)`
- `printStock()` – Druck / PDF (DIN A4)

**Angebot: Vorwoche, Bestand**

- `loadPrev()`
- `loadAux()`
- `auxGemerkt()` – Stand von Bestand/Vorwoche, mit dem der Editor zuletzt gezeichnet wurde (renderGroups, refreshAux)
- `stockOf(code)`
- `prevOf(it)`
- `auxHeadHTML()`
- `prevCellHTML(it)`
- `stockCellHTML(it)`
- `refreshAux()` – Spalten nach dem Laden von Bestand/Vorwoche aktualisieren, ohne Eingabefelder neu zu zeichnen

**Artikel hinzufügen (Fenster wie im Einzelangebot)**

- `ladeArtikelwahl()`
- `zielGruppe(a, anlegen)` – Ziel-Angebotsgruppe eines Artikels (anlegen = fehlende Gruppe neu anlegen, sonst nur Name für die Anzeige)
- `preiseLesen(liste, preise, K)` – Preise aus der Artikelauswahl lesen: Map(key → Preis \| null) oder Fehlertext
- `artikelAufnehmen(liste, ps, pool, K)` – Artikel der Auswahl in das gewählte Angebot aufnehmen (andere Angebote bleiben unverändert): steht der Artikel schon in einem anderen Angebot, wird dieser …
- `openArtikelwahl(opt)`
- `werbKandidaten(oid)` – Artikel eines Angebots für das Fenster „Werbung schalten“ (Reihenfolge wie im Editor)
- `werbungAuswahl(oid, ids, fertig)`
- `openWerbung()`

**Aufbau des Angebots (Knopf „Editor“, Fenster app/module/angebot/aufbau.js)**

- `aufbauSperre()`
- `aufbauKnopf()` – Knopf „Editor“: nur mit Bearbeitungsrecht; ohne eigenen Aufbau gekennzeichnet (Fenster nur zum Ansehen)
- `aufbauDaten()` – Gruppen des gewählten Angebots in Angebotsreihenfolge mit ihren Artikeln (nur die dieses Angebots); stand = Reihenfolge, Bereiche und Artikel je Gruppe …
- `aufbauUebernehmen(neu, stand)` – neu = [{id, bereich, artikel: [Artikel-IDs]}] in der gewünschten Reihenfolge (alle Gruppen und Artikel des Angebots); stand = aufbauDaten().stand beim Öffnen.

**Empfehlung (früher „Sonderpreis“; mit Preis: Sonderposten solange der Vorrat reicht)**

- `openSale(id)`
- `mhdList()`
- `renderMhd()`

**Stammdaten (je Artikelnummer)**

- `loadVkGruppen()`
- `loadMaster(force)`
- `masterOf(code)`
- `draftByCode(m)`
- `namenSetzen(it, e)` – Bezeichnungen je Angebot eines Stammsatzes auf einen Artikel des Angebots übertragen (nur bestehende Angebote)
- `applyMasterTo(m, onlyCode)` – Stammdaten auf Artikel anwenden (nur eindeutige Artikelnummern)
- `migrateMaster()` – Stammdaten an die Regeln anpassen (einmalig je Änderung der Regeln, danach ohne Wirkung)
- `addFromDraft()`
- `setMasterState(st, msg)`
- `masterChanged()`
- `saveMaster()` – Rückgabe: true = gespeichert, false = Fehler (bei 409 ist danach der aktuelle Stand geladen), undefined = eingereiht
- `offerStatus(e, by)`
- `renderMasterView()`
- `vkFilterOpts()`
- `masterOrig(e)` – Originalbezeichnung eines Stammsatzes: Bezeichnung1 aus dem Artikelstammdaten-Import, sonst der Name der Bestandsliste (WinAB).
- `renderMasterList()` – Liste nur zum Ansehen (Vorgabe des Inhabers 03.11.2026): Klick auf einen Artikel öffnet das Pop-up zum Ändern

**Pop-up „Artikel“ der Artikelstammdaten (Auftrag des Inhabers 03.11.2026)**

- `maDraftItem(code)`
- `openMasterArt(code)`
- `masterAusCsv(buf)`
- `masterNeuAus(r)`
- `masterZusammenfuehren(res, basis)` – Gelesene Zeilen mit den Stammdaten zusammenführen: neue Artikel mit vorgeschlagenen Merkmalen, bestehende nur um Originalbezeichnung (Bezeichnung1), …
- `masterImportDatei(file)`
- `openMasterNew(code)`
- `saveItemToMaster(it)` – Artikel-Dialog: aktuellen Artikel als Stammdaten speichern

**Schnittstelle für admin-verwaltung.js**

- `zeigeUmgezogen(ziel)` – Alter Eingabebereich stillgelegt: nur ein Hinweis mit Verweis, danach Weiterleitung (Adresse vom Server, nur https)
- `zeigeKeinZugang(name)` – Kein Modulzugang (Rolle ohne „<modul>.zugang“): der Server sperrt alle Aktionen dieses Bereichs; hier nur der Hinweis

## `app/assets/angebot-druck.js`

_Angebot · Satz der Druckfassung „Angebotsansicht“ (A4 quer) für die Angebotsseite (frontend.js, Wunsch des Inhabers 13.11.2026)._

- `fussHTML(fuss, hinweis, art)`

**Messen: Bausteine unsichtbar in Druckgröße setzen (eine Stufe)**

- `messen(host, cfg, fuss, st)`

**Verteilen**

- `setzen(m, modus)`
- `liste(cfg)` – cfg: { host (#print-root), bereiche: [{ name, balken(forts), gruppen: [{ n, block(von, bis, forts), verteilen? }] }], kopf(seite, seiten), werbung?, fuss?: …

## `app/assets/frontend.js`

_Wochenangebot – öffentliches Frontend_

**Hilfsfunktionen**

- `frage(titel, text, ja)` – Rückfrage im eigenen Fenster statt Browser-Dialog (gleiches Aussehen wie alle Fenster).
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

- `werbungHTML(eigeneKarte, druck)`

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
- `plOhneTeilen(units, c)` – Blöcke in fester Reihenfolge ohne Teilen auf c Spalten: die höchste Spalte so niedrig wie möglich (lineare Aufteilung).
- `plGleichTeilen(u, k)` – Sortierte Gesamtliste (ohne Gruppen) ist ein einziger Block: er wird gleichmäßig auf die k Spalten verteilt (ab der zweiten Spalte mit „Forts.“) – sonst …
- `plBaender(secs, k)`
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
- `bilderBereit(root, ms)` – Bilder der Druckfassung (Logo, Siegel der Fußzeile) erst laden lassen – sonst fehlen sie im Druck, wenn sie noch nicht im Zwischenspeicher sind.
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
- `empfehlungFor(it, oid)` – Empfehlung (früher „Sonderpreis“) je Artikel: sale = {value: Empfehlungspreis \| mark: true (ohne Preisänderung), offers?: {<Angebot>: {value} \| {status: …
- `saleFor(it, oid)`
- `diffOffers(oldM, newM)`
- `validateModel(m)` – Prüft ein Modell vor dem Speichern/Veröffentlichen
- `stripFrisch(name)` – „frisch“ gehört in den Zustand, nicht in die Bezeichnung.
- `titelMitKw(meta)` – Überschrift der Angebotsliste (Bildschirm und Druck): Titel der früher importierten Excel-Liste, aber immer mit der Kalenderwoche des Angebots – der Titel …
- `nachKategorien(model, kategorien, vkVon)` – Aufbau nach Angebotskategorien (Stammdaten der Verwaltung, Inhaber 05.11.2026): Reihenfolge der Kategorien, darin der VK-Gruppen, bestimmt die Reihenfolge …
- `nameVorschlag(name, group)` – Vorschlag für die Bezeichnung eines neu aufgenommenen Artikels (z. B. aus der Bestandsliste der Warenwirtschaft): – „frisch“ gehört in den Zustand …
- `normalizeItem(it, group)` – Merkmale vereinheitlichen (beim Laden des Entwurfs, Wiederherstellen einer Version, Stammdaten): – Herkunft als Kürzel; von Hand gesetzte Kürzel bleiben – …

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

## `app/module/angebot/aufbau.js`

_STAFL-Plattform · Angebot · Fenster „Aufbau des Angebots“ (Knopf „Editor“ in der Werkzeugleiste von „Angebot bearbeiten“, Wunsch des Inhabers 11.11.2026, Artikel 12.11.2026)._

- `bloecke(gruppen)` – Aufeinanderfolgende Gruppen mit gleichem Bereich bilden einen Block (wie die Überschriften im Editor und auf der Seite)
- `normalisieren()` – leere Blöcke entfernen, benachbarte mit gleichem Bereich zusammenfassen
- `zuHTML(aid, gid)` – Auswahl „In Gruppe …“: alle anderen Gruppen des Angebots, nach Bereich gegliedert
- `artikelHTML(gid)`
- `listeHTML()`
- `standZeigen(meldung)` – Stand unten links; mit Änderungen schützt data-geaendert vor versehentlichem Escape (theme.js)
- `fokussieren(f)` – Fokus nach einer Aktion: derselbe Knopf an der neuen Stelle, am Rand der andere Pfeil
- `zeichnen(fokus, meldung)`
- `fehler(t)`
- `aufleuchten(sel)`
- `laden(daten)`
- `oeffnen()`
- `uebernehmen()`
- `artikelNach(aid, ziel)` – Artikel ans Ende einer anderen Gruppe (Auswahl „In Gruppe …“, Ziehen auf eine zugeklappte Gruppe)

**Pfeile, Aufklappen, Auswahl**

**Ziehen (Maus und Touch)**

- `rollbar(el)`
- `einfuegen(ol, y)`
- `platzieren()`
- `rollen()`
- `bewegen(e)`
- `loslassen(e)`

## `app/module/angebot/druck.js`

_STAFL-Plattform · Angebot · Drucken aus „Angebot bearbeiten“ und Einstellung „Fußzeile im Druck“ (Wunsch des Inhabers 13.11.2026)._

**Drucken**

- `fertig()`
- `drucken(opt)`

**Fußzeile im Druck (nur Administratoren)**

- `fussForm()`
- `fussOeffnen()`

## `app/module/angebot/fruehere-wochen.js`

_STAFL-Plattform · Angebot · Fenster „Frühere Wochen“ (Wunsch des Inhabers 13.11.2026): frühere Wochenangebote ansehen und die KW wechseln wie in der REWE-Liste – Pfeile ‹ ›, Titel „<Angebot> · KW 43/2026“, „Diese …_

**Kalenderwochen (ISO, „JJJJ-WW“) wie in der REWE-Liste**

- `montag(kw)`
- `isoKw(d)`
- `zeitraum(kw)`
- `geruest()`
- `kopf()`
- `hinweis(text)`
- `laden()`
- `oeffnen(kw)`
- `gehe(kw)`

## `app/module/angebot/preisimport.js`

_STAFL-Plattform · Angebot · Darstellung der Vorschau „Artikelpreise (CSV)“ in der Importzentrale (Verwaltung → Import)._

- `zeile(r)` – Zeile der Details [Artikelnummer, Artikel, bisher\|null, neu, Dateizeile, prüfen 1/0] → Anzeige
- `zustand(ctx)`

**Kopf: Angebotswoche und Kacheln**

- `wocheHTML(w)`
- `kachelnHTML(k, fehler)`
- `fehlerHTML(list)` – Fehlerhafte Zeilen (Leser und Server) – aufklappbar, werden nicht übernommen

**Kundengruppen ohne Angebot: einzeln anhaken**

- `gruppenHTML(d, ctx)`

**Preisänderungen je Angebot**

- `listeHTML(d, z)`
- `aenderungenHTML(d, z)`

**Vertrag mit der Importzentrale**

- `html(ctx)`
- `binden(root, ctx)`

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
- `art(n, gid, nr)`

## `tests/e2e/test_aufbau.py`

_Aufbau des Angebots (Knopf „Editor“ in „Angebot bearbeiten“, Wunsch des Inhabers 11.11.2026, Artikel 12.11.2026)_

- `check(n, c, i)`
- `entwurf(cl)`
- `im_angebot(it, oid)`
- `bloecke(m, oid)` – Erwarteter Aufbau: [(Bereich, [Gruppen-IDs])] der Gruppen mit Artikeln des Angebots, aufeinanderfolgend gleicher Bereich
- `fenster(pg)`
- `editor(pg)` – Editor: Gruppen-IDs in Reihenfolge und Bereichsüberschriften
- `quoten(t)`
- `art_reihe(m, gid, oid)` – Artikel-IDs einer Gruppe im Angebot in Reihenfolge des Entwurfs
- `angebot_reihe(m, oid)` – Artikel in Angebotsreihenfolge wie OfferCore.enrichOffer (Gruppe, dann Stelle); oid=None: alle Artikel des Modells
- `dlg_art(pg, gid)`
- `flach(bl)`
- `gruppen_reihe(model)`
- `ziehen(pg, quelle, ziel, oben, steps)` – Am Griff „quelle“ ziehen und über dem Element „ziel“ loslassen (obere bzw. untere Hälfte)
- `touch_ziehen(pg, cdp, quelle, ziel)`
- `login(pg, user, pw)`
- `gespeichert(pg)`
- `oeffnen(pg)`

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

## `tests/e2e/test_druck.py`

_Druck der Angebote (Wunsch des Inhabers 13.11.2026): die Druckfassung „Angebotsansicht“ (A4 quer) zeigt alles, was die Vorschau zeigt – fortlaufend und kompakt._

- `check(n, c, i)`
- `doc(name)`
- `roh(cl, action, headers)` – GET ohne JSON-Auswertung: (Status, Kopfzeilen, Bytes)
- `pdf_stroeme(data)` – Entpackte Inhaltsströme (FlateDecode) eines PDF
- `pdf_text(data)`
- `norm(t)` – Text ohne Leerraum und Trennstriche (im PDF trennt der Browser lange Bezeichnungen am Zeilenende)
- `norm_titel(name)` – Gruppenname, wie die Angebotsansicht ihn zeigt: "Marke" → „Marke“
- `pdf_chromium_text(data)` – Text eines vom Browser gedruckten PDF in Zeichenreihenfolge, ohne Leerraum und Trennstriche.
- `strom(o)`
- `pdf_seiten(data)`
- `pdf_farbig(data)` – Anzahl farbiger (nicht grauer) Füllfarben in den Seiteninhalten

**Einstellung „Fußzeile im Druck“: Rechte, Vorgabe, Bereinigung**

**Bankangaben nur für angemeldete Nutzer (der Server entscheidet)**

**Angebot für den Druck: Werbung, Sonderposten, „auf Anfrage“, Zusatzpreis**

- `satz(pg, wie)` – Druckfassung setzen (wie Strg+P) und im Druckmedium vermessen
- `zurueck(pg)`
- `laden(pg, pfad)`
- `heil(s, modus)` – Feste Vorgaben des Satzes, die für jede Druckfassung gelten: Liste der Verstöße (leer = in Ordnung)
- `pdf_alles(data, s)` – Zeilen (Nummer + Bezeichnung) der Druckfassung, die im PDF fehlen

**Angebotsseite (öffentlich): Druck = Angebotsansicht am Bildschirm**

**Viele Bereiche (wie mit Angebotskategorien): fortlaufend statt einer Seite je Bereich**

**Einzelangebot: Druck der Angebotsseite und PDF des Servers**

**Eingabebereich: Knopf „Drucken“, Vorschau, Fenster „Fußzeile im Druck“**

- `anmelden(c, user, pw)`
- `drucke(a, ausloesen)` – Druck auslösen und auf den neuen unsichtbaren Rahmen mit der Druckfassung warten (ein früherer Rahmen bleibt stehen, bis der Entwurf gespeichert ist – er …

## `tests/e2e/test_editor_aux.py`

_Testgruppe editor_aux_

- `check(n, c, i)`
- `login(pg, user, pw)`
- `post(pg, action, body)`

**Artikelkarte des Bestands im Angebot (Wunsch Inhaber 06.11.2026)**

- `karte_zu(pg)`
- `frei(zeile)`
- `treffer(q)`

**Export für WinAB (Recht angebot.winab_export): veröffentlichtes Wochenangebot, je Nummer der höchste Preis**

- `art(src, nid, **f)`
- `wb(v)`

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

**E-Mail aus dem CRM (Kunden-Pop-up, Reiter „Angebote“: crm_einzel_senden, gleiche Funktion und Bestätigung)**

- `pdf_inhalt(data)` – Text der Seiteninhalte (FlateDecode) eines PDF, als Windows-1252 gelesen.
- `hole(cl, action)`

**Zurückziehen, Ablauf, Löschen**

**Partien im Einzelangebot (Entscheidung des Inhabers 13.11.2026, GR-001 Version 2)**

- `ps(**kw)`
- `anzahl()`

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

_Testgruppe hist: Preisverlauf – Import alter Angebotslisten, Zeiträume, Datendialog; Frühere Wochen ansehen (KW wechseln, Angebot wählen, Quelle Wochenablage/Veröffentlichung/Version/Preisverlauf, Rechte); …_

- `check(n, c, i)`
- `api_get(pg, q)`
- `api_post(pg, action, body)`
- `api_post_bestaetigt(pg, action, body)`
- `woche(pg, kw, oid)`
- `dok(name)` – Gespeichertes Dokument (ohne PHP-Schutzzeile) oder None – so, wie der Testserver es liest
- `ablage_namen()` – Wochen in der Wochenablage angebot-woche/* (Dateien oder Datenbank)
- `rahmen_hat(pg, text)` – warten, bis die Angebotsseite im Fenster den Text zeigt (während des Ladens gibt es kurz kein body)
- `preis_von(antwort, code)`
- `fruehere_wochen_pruefen(a, br, errs)` – Frühere Wochen ansehen (nur Mitarbeiter mit Modulzugang Angebot, nur lesend): Quelle je KW, Auflösung auf dem Server, Rechte, Grenzfälle, Fenster mit …
- `wochenablage_pruefen(a)` – Wochenablage angebot-woche/<JJJJ-WW>: damalige Angebotsdefinitionen, Angebot, das es damals nicht gab, alte Versionen werden vor dem Löschen gerettet, nie …

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

_Testgruppe p0: Ersteinrichtung gesperrt (leeres System, WA_INSTALLED, kaputte Nutzerdatei – kein Übernehmen), CSV-Formel-Schutz im Protokoll, Sicherungs- und Bereitstellungsanzeige (Sicherheit → System) und …_

- `check(n, c, i)`
- `srv(port, data, env)`
- `st(url)`
- `system_neu()` – 5) Sicherungs-Status im Modul Sicherheit, Reiter System (bis 27.10.2026 Verwaltung → System)

## `tests/e2e/test_restposten.py`

_Empfehlung (früher „Sonderpreis“): mit Preis Sonderposten (kurzes MHD, solange der Vorrat reicht), ohne Preis nur hervorgehoben; neu gesetzt nur im bearbeiteten Angebot._

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
