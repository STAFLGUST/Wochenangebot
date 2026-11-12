# Funktionen: REWE (`rewe`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

5 Dateien, 164 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/rewe.php`

_Aktionen: REWE · Vordisposition Dry Aged (Oberfläche rewe.intern, Daten und Regeln in app/api/module/rewe/rewe.php, Wochenabschluss und Excel in app/api/module/rewe/export.php) Rechte (GR-103): rewe.sehen – eigene …_

- `rw_rechte(me)`
- `rw_kw_param(standard)`
- `rw_export_pruefen(schreibend)`
- `rw_xlsx_senden(inhalt, datei)`

## `app/api/module/rewe/export.php`

_REWE · Wochenabschluss und Excel für die Warenwirtschaft (Aktionen rewe_abschluss, rewe_export, rewe_erfasst). rw_abschluss: alle Bestellungen einer KW über alle Listen – Zeilen je Markt und Artikel, Summen je …_

- `rw_abschluss(kw)`
- `rw_abschluss_setzen(kw, feld, wert)` – Wochenabschluss vermerken (unter der Sperre): exportiert bzw. in WinAB erfasst

**Excel**

- `rw_zip(dateien)`
- `rw_xl_spalte(n)`
- `rw_xl_text(t)`
- `rw_xl_stile()` – Stile: 0 Standard, 1 Kopfzeile (fett, weiß auf Bordeaux), 2 Titel (fett, groß), 3 Hinweis (kursiv grau), 4 fett
- `rw_xl_blatt(zeilen, breiten, kopf)` – Ein Blatt: $zeilen = Liste von Zeilen, Zelle = Wert oder [Wert, Stil]; $kopf = Zeilennummer (1-basiert) der Kopfzeile
- `rw_xlsx(blaetter, titel)`
- `rw_export_xlsx(a, stamm, wer)` – Arbeitsmappe des Wochenabschlusses; Texte, die mit = + - @ beginnen, bleiben Text (inlineStr, keine Formeln)

## `app/api/module/rewe/rewe.php`

_REWE · Vordisposition Dry Aged_

**Grundwerte**

- `rw_grund_lieferwege()`
- `rw_grund_artikel()`

**Laden und Schreiben**

- `rw_stamm()`
- `rw_id_liste(v)` – Liste von Nutzer-IDs: nur nicht leere Texte, jede einmal (fehlende oder fremde Werte → leere Liste)
- `rw_maerkte_doc()`
- `rw_verlauf_doc()`
- `rw_wochen_doc(jahr)` – Wochen eines ISO-Jahres: maerkte[<Markt-ID>][<WW>] = Antwort, abschluss[<WW>] = Wochenabschluss
- `rw_wochen_schreiben(jahr, doc)`
- `rw_wochen_jahre()` – Jahre mit Wochendaten (für die Akte und die Leerprüfung)
- `rw_schreiben(name, doc)`
- `rw_id(praefix)`
- `rw_wer(me)`
- `rw_leer()` – Ist das Modul noch leer (für die Übernahme des Datenpakets ohne „ersetzen“)?

**Kalenderwochen (ISO, „JJJJ-WW“)**

- `rw_kw_heute()`
- `rw_kw_abschluss()` – Woche, deren Bestellschluss (Freitag früh) zuletzt war bzw. gerade läuft: ab Freitag zählt schon die nächste Woche
- `rw_kw_abfrage()` – Lieferwoche, für die gerade abgefragt wird (die Woche nach dem nächsten Bestellschluss)
- `rw_kw_montag(kw)`
- `rw_kw(v, was)`
- `rw_kw_plus(kw, n)`
- `rw_kw_abstand(von, bis)`
- `rw_kw_text(kw)`
- `rw_kw_zeitraum(kw)`

**Prüfen der Eingaben**

- `rw_text(v, max, was, mehrzeilig)`
- `rw_wahl(v, erlaubt, was)`
- `rw_ziffern(v, max, was)`
- `rw_ganz(v, was, max)`
- `rw_mengen(v, stamm, was)` – Mengen je Artikel { rb: 1, fk: 2 } – nur bekannte Artikel, 0 entfällt
- `rw_artikel_name(stamm, id)`
- `rw_lieferweg(stamm, id)`

**Mitarbeiter (Verwaltung, nur lesend)**

- `rw_namen()` – Alle Mitarbeiter: ID → Name (auch gesperrte, damit alte Zuweisungen lesbar bleiben)
- `rw_personen()` – Mitarbeiter, denen Märkte zugewiesen werden können (Team des Moduls, rw_im_team) – dieselbe Liste für die Karten der Zuweisung, die Personenauswahl, die …
- `rw_kandidaten()` – Mitarbeiter, die sich ins Team aufnehmen lassen: aktiv, mit Zugang und Modulzugang „rewe.zugang“, noch nicht im Team (auch ausgeblendete Rollen-Inhaber), …
- `rw_aufnehmbar(u)`
- `rw_zustaendig_zahlen(doc)` – Zuständige Märkte je Mitarbeiter in der Abfragewoche und danach (aktuelle und künftige Einträge der „ab KW“-Historie)
- `rw_mitglied_ergaenzen(nutzer)` – Mitarbeiter ins Team aufnehmen (Aufruf unter der Sperre): hebt ein Ausblenden auf; ohne „REWE ansehen“ aus den Rollen wird er ausdrücklich ergänzt (mitglieder).
- `rw_mitglied_entfernen(nutzer)` – Mitarbeiter aus dem Team entfernen (Aufruf unter der Sperre): nur ohne Märkte ab der Abfragewoche (sonst 422).
- `rw_nutzer(v)`
- `rw_name(u)`
- `rw_team_pruefen(v)` – Team speichern: {Nutzer-ID: {alle, export}} – nur Mitarbeiter im Team (rw_personen)

**Kundenstamm der Verwaltung (nur lesend, customers_load): WinAB-Kd.-Nr. → Kunde**

- `rw_kunden()`
- `rw_anzeige(m)` – Anzeige eines Marktes: Kundenstamm vor eigenen Feldern (nur leere Stammfelder füllt der Markt auf)
- `rw_person_pruefen(v)`

**Historie „ab KW“ (Zuständigkeit, Lieferweg)**

- `rw_ab(hist, kw, feld)` – Wert zur KW: letzter Eintrag mit ab ≤ KW; vor dem ersten Eintrag gilt der erste
- `rw_ab_setzen(hist, kw, feld, wert)` – Neuer Wert ab KW: spätere Einträge entfallen, gleicher Wert wie vorher → keine Änderung
- `rw_zustaendig(m, kw)`
- `rw_lw(m, kw)`

**Team und Sichtbarkeit (GR-103, serverseitig je Markt)**

- `rw_team_daten(neu)`
- `rw_verboten(u, recht)`
- `rw_ausgeblendet(u)`
- `rw_ergaenzt(u)`
- `rw_sehen(u)`
- `rw_bearbeiten(u)`
- `rw_im_team(u)`
- `rw_require_perm(recht, schreibend)` – Wie require_perm für die Aktionen des Moduls: „rewe.sehen“ und „rewe.bearbeiten“ gelten auch für im Team ergänzte Mitarbeiter (rw_sehen, rw_bearbeiten), alle …
- `rw_team(me)` – Alle Listen / Wochenabschluss: Recht der Plattform oder Zuweisung im Team des Moduls (nur im Team, nicht ausgeblendet)
- `rw_alle(me)`
- `rw_export(me)`
- `rw_eigen(m, me, kw)`
- `rw_darf_sehen(m, me, kw)`
- `rw_darf_pflegen(m, me, kw)`
- `rw_markt_index(doc, id)`
- `rw_markt_finden(doc, id, me, kw)`

**Dauerauftrag**

- `rw_dauer(m)`
- `rw_dauer_naechste(m, kw)` – Ist der Dauerauftrag in der KW fällig?
- `rw_dauer_faellig(m, kw)`
- `rw_dauer_text(m, stamm)`
- `rw_mengen_text(mengen, stamm)`

**Antworten**

- `rw_antwort(wochen, markt, kw)`
- `rw_antwort_aus(e)` – Antwort für die Oberfläche (Kurzform im Speicher → lesbare Felder)
- `rw_wochen_cache(cache, jahr)` – Wochen mehrerer Jahre auf einmal (Verlauf über den Jahreswechsel)
- `rw_antwort_kw(cache, markt, kw)`
- `rw_antwort_setzen(b, me, stamm, quelle)` – Antwort setzen (Aufruf unter der Sperre).

**Verlauf (Notizen und Änderungen)**

- `rw_notiz_neu(doc, markt, art, text, me, wv, quelle)`
- `rw_system_notiz(markt, text, me)`
- `rw_wiedervorlagen(verlauf, heute)` – Offene Wiedervorlagen je Markt (fällig bis heute)

**Märkte prüfen**

- `rw_kontakte(v)`
- `rw_dauer_pruefen(v, stamm)`
- `rw_markt_felder(b, stamm, alt)`
- `rw_kdnr_frei(doc, kdNr, id)`
- `rw_markt_aus(m, stamm, namen, kw)` – Markt für die Oberfläche

**Wochenabfrage**

- `rw_woche(kw, me, wer)` – $wer: '' = eigene Liste, Nutzer-ID = Liste dieser Person (nur mit „alle“), '*' = alle Listen (nur mit „alle“)
- `rw_startseite(me)` – Startseite des Dashboards („Heute für Sie“, lib/startseite.php): Märkte der eigenen Liste in der laufenden Wochenabfrage, die noch keine Antwort haben – …
- `rw_dauer_uebernehmen(kw, me, wer, nurIds)` – Fällige Daueraufträge einer KW als Bestellung übernehmen (eigene Märkte bzw. mit „alle“ die gewählte Liste)
- `rw_letzte_bestellungen()` – Letzte Bestellung je Markt über alle Jahre (Märkteübersicht, ruhende Märkte)

**Marktakte**

- `rw_akte(m, me)`

**Zuweisung**

- `rw_zuweisen(ids, kw, nutzer, lieferweg, me)` – Zuständigkeit und/oder Lieferweg mehrerer Märkte ab KW ändern; Änderung im Verlauf mit Namen

**Stammdaten (Lieferwege, Artikel)**

- `rw_stamm_pruefen(b, alt)`
- `rw_stamm_liste(liste, alt, was, extra, praefix)` – Gemeinsame Prüfung für Lieferwege und Artikel: Kennung bleibt, nichts wird entfernt (nur deaktiviert), Namen eindeutig

**Datenpaket (Übernahme der Excel-Listen)**

- `rw_paket_pruefen(paket, zuordnung, me)` – Paket prüfen: { format: "stafl-rewe", version: 1, lieferwege: [{id, name, art}], artikel?: [...], maerkte: [{kdNr, reweNr, name, strasse, plz, ort, region, …
- `rw_ab_liste(p, kw)`
- `rw_paket_uebernehmen(erg, ersetzen)`

## `app/module/rewe/rewe.js`

_STAFL-Plattform · REWE – Oberfläche der Vordisposition Dry Aged_

**Aufruf der API: wirft nie, liefert { status, data, json }**

- `api(action, body, query)`
- `toast(text, fehlerhaft, aktion)` – Hinweis unten; mit aktion ({text, fn}) zusätzlich ein Knopf (z. B. „Rückgängig“), dann länger sichtbar
- `fehler(text)`
- `zeigeAnmeldung()`

**Kalenderwochen (ISO, „JJJJ-WW“)**

- `montag(kw)`
- `isoKw(d)`
- `zeitraum(kw)`

**Bezeichnungen**

- `mengenText(m)`

**Hell/Dunkel**

- `themaKnopf()`

**Reiter und Adresse**

- `zeigeTab(tab, teil)`

**Meine Woche**

- `ladeWoche()`
- `ladeAlle()`
- `setzeSuche(text)`
- `renderWoche()`
- `bestelltHtml(w, best, mengen)` – Übersicht der Bestellungen dieser Woche (eigene bzw. gewählte Liste): Markt, Lieferweg, Mengen – Klick zeigt die Zeile
- `zelleHtml(v, art, m)` – Verlauf: acht Wochen davor, diese Woche (Rahmen) und drei Wochen danach (Vorbestellungen), die KW darunter.
- `verlaufText(m)`
- `zeileHtml(m)`
- `ruhendHtml(liste, q, suche)`
- `sende(id, teil, mitRueck)` – Antwort senden; bei Erfolg Zeile aktualisieren, bei Konflikt neu laden.

**Märkte und Marktakte**

- `ladeMaerkte()`
- `renderMaerkte()`
- `ladeAkte(id)`
- `heatHtml(A)` – Wochenraster je Jahr (Marktakte und Marktkarte): eine Zelle je KW, Farbe nach Antwort
- `renderAkte()`

**Eingabemaske Markt**

- `kontaktZeile(k)`
- `oeffneMarkt(m)`

**Eingabemaske Notiz**

- `oeffneNotiz(markt)`

**Marktkarte (Fenster: Klick auf Name oder Adresse eines Marktes)**

- `oeffneKarte(id)`
- `ladeKarte()`
- `renderKarte(hinweisText)`
- `hinweisSpeichern()` – Hinweis speichern (nach kurzer Pause beim Tippen, beim Verlassen des Feldes und beim Schließen)

**Daueraufträge (alle sichtbaren Märkte mit Dauerauftrag; bearbeiten nur eigene, GR-103 prüft der Server)**

- `naechsteLieferungen(e, n)`
- `kwWahl(wert, leer)`
- `renderDauer()`
- `dauerBearbeiten(m)`
- `renderDauerEdit()`
- `dauerSpeichern(ende)`

**Zuweisung und Team**

- `personKarte(p, anzahl)`
- `neuKarte()`
- `renderZuweisung()`
- `teamGeaendert(r, text)` – Team ändern: Mitarbeiter hinzufügen/entfernen liefern das neue Team; danach Start neu laden (Listenwahl, Auswahlfelder)

**Wochenabschluss**

- `ladeAbschluss()`
- `balken(liste, cls)`
- `renderAbschluss()`

**Einstellungen**

- `renderEinstellungen()`
- `paketVorschau()`
- `listenVorschlag(liste)`
- `renderPaket()`

**Start**

- `setzeStart(d)`
- `neuStart()`
- `laden()`

## `tests/e2e/test_rewe.py`

_REWE (Modul rewe, Oberfläche rewe.intern unter /module/rewe/) – Vordisposition Dry Aged für REWE-Märkte._

- `check(n, c, i)`
- `kw_von(d)`
- `kw_plus(kw, n)`
- `namen(liste)` – ── Team: Mitarbeiter hinzufügen und entfernen (Wunsch des Inhabers 11.11.2026) ──
- `person(name, liste)`
- `stamm_roh()`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe, ziel, pfad)`
