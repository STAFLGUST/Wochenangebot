# Funktionen: Leergut (`leergut`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

4 Dateien, 122 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/leergut.php`

_Aktionen: Leergut · Leergutkonten und Abstimmung (Oberfläche leergut.intern, Daten und Regeln in app/api/module/leergut/leergut.php) Rechte (GR-103): leergut.sehen – Übersicht, Konten mit Bewegungen, Abstimmungen, …_

- `lg_index(doc, id, was)` – Index eines Eintrags einer Liste oder 404
- `lg_rev_pruefen(b, alt, was)` – Veralteter Stand eines Eintrags → 409 mit dem aktuellen Eintrag
- `lg_partner_name(stamm, id)`

## `app/api/module/leergut/leergut.php`

_Leergut · Leergutkonten und Abstimmung_

**Grundwerte**

- `lg_grund_lademittel()` – Lademittel der Excel-Liste; Werte je Stück laut Leitfaden (änderbar unter Einstellungen)

**Laden und Schreiben**

- `lg_stamm()`
- `lg_lademittel_winab(liste)` – WinAB-Stammdaten ergänzen: Lademittel ohne Angabe bekommen Nummer und Kurzbezeichnung aus WinAB (über Kennung oder gleichen Namen), fehlende WinAB-Lademittel …
- `lg_doc(name)`
- `lg_schreiben(name, doc)`
- `lg_id(praefix)`
- `lg_ids(liste)`
- `lg_wer(me)`
- `lg_verlauf(e, me, was)`
- `lg_leer()` – Ist das Modul noch leer (für den Import ohne „ersetzen“)?

**Prüfen der Eingaben**

- `lg_text(v, max, was)`
- `lg_datum(v, was, pflicht)`
- `lg_wahl(v, erlaubt, was)`
- `lg_ganz(v, was, negativ)` – Ganze Zahl (Stück).
- `lg_mengen(v, lmIds, was, negativ)` – Mengen je Lademittel: { e2: 12, h1: 1 } – nur bekannte Lademittel, leere und 0 entfallen
- `lg_betrag(v, was)`
- `lg_email(v, was)`
- `lg_frist(eingang, tage)` – Frist: Eingang + Tage (Kalendertage)

**Stammdaten: Lademittel und Partner**

- `lg_lademittel_pruefen(v, alt)`
- `lg_partner_pruefen(b, alt, stamm)`
- `lg_partner_finden(stamm, id)`

**Bewegungen**

- `lg_bewegung_pruefen(b, stamm)`
- `lg_delta(b)` – Saldo einer Bewegung je Lademittel (+ Abgang, − Zugang)
- `lg_addiere(s, d)`
- `lg_ohne_null(s)`
- `lg_nach_partner(bewegungen)` – Bewegungen je Partner nach Datum (ohne stornierte)
- `lg_saldo_bis(liste, stichtag)` – Saldo eines Partners bis einschließlich Stichtag ('' = alle)
- `lg_minus(a, b)`

**Abstimmungen**

- `lg_abstimmung_pruefen(b, alt, stamm)`
- `lg_abstimmung_aus(a, nachPartner, heute)` – Abstimmung für die Oberfläche: unser Saldo zum Stichtag (heute gerechnet), Differenz, Fristampel

**Konten (Übersicht je Partner)**

- `lg_konten(stamm, bewegungen, abstimmungen, heute)`

**Abschreibungen (Dachser „lt. Empfänger“)**

- `lg_abschreibung_pruefen(b, alt, stamm)`

**Inventur**

- `lg_inventur_pruefen(b, alt, stamm)`

**Bilanz zum Stichtag**

- `lg_bilanz(stichtag, stamm, bewegungen, abstimmungen, inventur)`

**CSV (Excel)**

- `lg_csv_zelle(v)`
- `lg_csv_bilanz(bil, stamm)`
- `lg_kunden_leergut(stamm, bewegungen, heute)` – „Leergut bei Kunden“ (Abholliste): Konten der Art Kunde mit Saldo, nach Wert absteigend.
- `lg_csv_kunden(zeilen, stamm)`

**Datenpaket (Übernahme der bisherigen Excel-Liste und der Partnerauszüge)**

- `lg_paket_pruefen(p, me)`

**WinAB: Lademittelbewegungen (CSV „Lademittelbewegungen komplett“ oder Bericht „… Kunden“ als .XLS)**

- `lg_winab_nr(v, was)`
- `lg_winab_pruefen(b, stamm)`
- `lg_kundenstamm_namen()` – Firma je WinAB-Kundennummer aus dem Kundenstamm der Verwaltung (nur lesend, regeln/datenverantwortung.toml)
- `lg_lf_index(partner)` – Konten je WinAB-Lieferantennummer: Nummer => [[Index, „WinAB ab“], …] (lieferantNr und lieferantNrWeitere)
- `lg_lf_konto(idx, nr, datum)` – Konto eines Lieferantenbelegs: unter den Konten mit der Nummer das, dessen „WinAB ab“ am Datum erreicht ist – bei mehreren das mit dem spätesten Beginn …
- `lg_wareneingang(b, tausch)` – Wareneingang (Lieferschein eines Lieferanten): WinAB bucht dort fast immer einen Tausch (Abgang = Zugang; bei allen Lieferanten 9.620 von 9.668 …
- `lg_namensteile(n)` – Namensteile für den Vorschlag „Konto für WinAB-Lieferant“ (ohne Rechtsform)
- `lg_lieferantenstamm()` – Name und Versandart der WinAB-Lieferanten aus den Stammdaten der Verwaltung (nur lesend: lieferanten_kurz, versandarten_namen)
- `lg_versand_text(nr, va)`
- `lg_partner_versand(partner)` – Versandart je Partner (Anzeige): Lieferanten laut Lieferantenstamm (Hauptnummer), Kunden laut Kundenstamm
- `lg_winab_abgleich(w, stamm, bew, me)` – Abgleich je Beleg im Zeitraum (von–bis): neu → buchen, gleich → nichts, geändert → alten stornieren und neu buchen, nicht mehr in der Datei (ausgeglichen) → …

**Dachser-Liste „Unterkonto-Vorspediteur“ (Mail „Infos von Fa. DACHSER“)**

- `lg_mail_text(roh, tiefe)` – Text einer gespeicherten Mail (.eml): erster text/plain-Teil (sonst text/html ohne Auszeichnung), Transfer-Kodierung und Zeichensatz aufgelöst.
- `lg_dachser_datum(d)` – Datum „1.09.26“ / „30.09.2026“ → ISO
- `lg_dachser_lesen(text, stamm)` – Liest die Liste: Fälle je Zeile, Stichtag(e), Saldo laut Dachser; Zeilen, die wie ein Fall aussehen, aber nicht lesbar sind, kommen als Fehler zurück.
- `lg_dachser_abgleich(l, liste, me)` – Abgleich mit den erfassten Abschreibungen über die Sendungsnummer: je Sendung ein Fall (Mengen je Lademittel addiert).

## `app/module/leergut/leergut.js`

_STAFL-Plattform · Leergut – Oberfläche der Leergutkonten_

**Aufruf der API: wirft nie, liefert { status, data, json }**

- `api(action, body, query)`
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`

**Formate**

- `mengen(m, {…})` – Mengen „E2 +12 · H1 −3“ (nur Werte ≠ 0)
- `ganz(v)` – Ganze Zahl aus einer Eingabe („1.200“, „−15“); '' → 0, ungültig → NaN
- `saldoBis(bewegungen, stichtag)`
- `fristChip(a)`
- `kundenLeergut()` – Leergut bei Kunden: Konten der Art Kunde mit Saldo, nach Wert.

**Hell/Dunkel**

- `themaKnopf()`

**Reiter**

- `zeigeTab(tab, teil)`

**Daten**

- `setzeDaten(d)`
- `neuLaden()`
- `kontoLaden(id)`
- `renderAlles()`

**Übersicht**

- `renderUebersicht()`

**Konten**

- `fuelleFilter()`
- `renderKontoliste()`
- `zeigeKonto(id, hash)`
- `saldoMail(p, ko)`
- `bewegungsTabelle(k, lms)`

**Abstimmungen**

- `abstTabelle(liste, mitPartner)`
- `renderAbstimmungen()`

**Abschreibungen**

- `renderAbschreibungen()`
- `dachserZuruecksetzen()`
- `dachserPruefen()`

**Bilanz und Inventur**

- `ladeBilanz()`
- `ladeCsv(body, dateiname)` – CSV vom Server (Bilanz oder Abholliste) herunterladen – der Server vermerkt es im Protokoll
- `renderInventur()`

**Einstellungen**

- `renderEinstellungen()`

**WinAB-Bericht „Lademittelbewegungen Kunden“ (.XLS)**

- `winabLm(name, nr)` – Lademittel des Berichts → Modul: zuerst über die WinAB-Nummer (Stammdaten), sonst über den Namen.
- `winabDatum(v)`
- `leseWinab(sheets, datei)`

**WinAB-Datei „Lademittelbewegungen komplett“ (.CSV)**

- `csvZeilen(text)`
- `leseWinabCsv(buf, datei)`
- `winabAnfrage(w, ab, zuordnung)` – Was an den Server geht: CSV ab „Übernehmen ab“ (Belege davor nur gezählt), Bericht (.XLS) unverändert
- `winabVorher(w, ab)`
- `zeigeWinabVorschau(st, r)`
- `winabPruefen(fokus)` – Vorschau beim Server anfragen (Abgleich ohne Speichern) – nach Dateiwahl, „Übernehmen ab“ und Zuordnung

**Eingabemasken: gemeinsame Hilfen**

- `oeffne(dlg)`
- `senden(form, action, body)`
- `sammle(inputs, negativ)` – Mengen aus Eingaben mit data-lm (und optional data-seite) einsammeln; ungültige markieren
- `nachSpeichern(text, partner)`

**Bewegung buchen**

- `oeffneBewegung(partner)`
- `bwZeilen()`
- `bwDanach()`

**Stornieren**

- `oeffneStorno(id)`

**Auszug (Abstimmung) erfassen / bearbeiten**

- `oeffneAuszug({…})`
- `azZeilen(werte)`
- `azRechnen()`

**Dachser-Abschreibung**

- `oeffneAbschreibung(id)`
- `dsWert()`

**Inventur**

- `oeffneInventur(id)`

**Partner**

- `oeffnePartner(id)`

**Start**

- `laden()`

## `tests/e2e/test_leergut.py`

_Leergut (Modul leergut, Oberfläche leergut.intern unter /module/leergut/) – Leergutkonten und Abstimmung._

- `check(n, c, i)`
- `winab_xls(zeilen, stand, titel)` – BIFF-Datei (Datensätze BOF, LABEL, NUMBER, EOF wie im WinAB-Export) aus den Bewegungszeilen.
- `winab_csv(zeilen)`
- `wb(**aend)`
- `dachser_liste(faelle, per, saldo, seiten)` – ── Dachser-Liste „Unterkonto-Vorspediteur“ (Mail „Infos von Fa. DACHSER“) ── Erfundene Liste im Aufbau der Dachser-Mail: Seitenkopf mit Anschrift, je Fall …
- `als_mail(text)` – Gespeicherte Mail (.eml) wie vom Dachser-Mailprogramm: quoted-printable, ISO-8859-1, umgebrochene Zeilen.
- `vz(n)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe, ziel)`
- `zu(pg, sel)`
