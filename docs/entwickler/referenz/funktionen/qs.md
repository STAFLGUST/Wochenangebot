# Funktionen: Qualitätssicherung (`qs`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

13 Dateien, 315 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/qs.php`

_Aktionen: QM-System (Oberfläche qs.intern, Daten und Regeln in app/api/module/qs/qs.php) Rechte (GR-103): qs.sehen – Übersicht, Dokumente mit Versionen, Handbuch, Prüfplan mit Nachweisen, Maßnahmen, CSV, …_

- `qs_index(doc, id, was)` – Index eines Eintrags einer Liste oder 404
- `qs_rev_pruefen(b, alt, was)` – Veralteter Stand eines Eintrags → 409 mit dem aktuellen Eintrag
- `qs_dok_name(d)`
- `qs_dok_antwort(d)`
- `qs_dok_ablegen(doc, i, d, me)` – Dokument speichern: Stand hochzählen, „geändert“ setzen

## `app/api/module/qs/bericht.php`

_QM-System · Audit-Bericht (Aktionen qs_bericht, qs_bericht_excel)_

- `qs_bericht_zeitraum(von, bis, heute)` – Zeitraum prüfen: [von, bis]
- `qs_bericht_monate(von, bis)`
- `qs_bericht_kalender(p, eigene, von, bis, heute)` – Kalender-Intervall: Perioden im Zeitraum, erfüllt/versäumt je Monat, versäumte Bereiche [erste, letzte, Anzahl]
- `qs_bericht_fristen(p, eigene, von, bis)` – Längere Intervalle: Fristenkette; Ereignis [faellig, erledigt, status, tage]
- `qs_bericht_abschluss(m)` – Abschluss einer Maßnahme (Datum) – wirksam: Wirksamkeitsprüfung, verworfen: letzte Änderung
- `qs_bericht_daten(stamm, dokumente, handbuch, plan, nachweise, massnahmen, namen, von, bis, heute)` – Der Bericht.

**Excel**

- `qs_bericht_periode(art, per)`
- `qs_bericht_monat(m)`
- `qs_xl_spalte(n)`
- `qs_xl_text(t)`
- `qs_xl_stile()` – Stile: 0 Standard, 1 Kopfzeile, 2 Titel, 3 Hinweis, 4 fett, 5 Prozent, 6 Text mit Umbruch
- `qs_xl_blatt(zeilen, breiten, kopf, umbruch)` – Blatt: Zeilen aus Zellen (Wert oder [Wert, Stil]); $kopf = Zeile der Kopfzeile (1-basiert, 0 = keine); $umbruch = Spalten mit Umbruch
- `qs_xl_mappe(blaetter, titel)`
- `qs_bericht_xlsx(b, wer)` – Arbeitsmappe: Zusammenfassung, Prüfplan (je Monat), Versäumnisse und Fristen, Abweichungen, Maßnahmen, Dokumente, Überprüfung fällig, Handbuch

## `app/api/module/qs/qs.php`

_Qualitätssicherung · QM-System (IFS Wholesale)_

**Laden und Schreiben**

- `qs_stamm()`
- `qs_doc(name)`
- `qs_schreiben(name, doc)`
- `qs_id(praefix)`
- `qs_wer(me)`
- `qs_verlauf(e, me, was)`
- `qs_heute()`
- `qs_leer()` – Ist das Modul noch leer (für den Import ohne „ersetzen“)?
- `qs_nat_cmp(a, b)` – Kapitel- und Abschnittsnummern natürlich sortieren („1.2“ vor „1.10“, „2.0.9“ vor „2.0.10“)

**Mitarbeiter (Plattformkern, nur lesen)**

- `qs_mitarbeiter()` – Wählbare Mitarbeiter: aktive Zugänge und Mitarbeiter ohne Anmeldung (z. B. Lager); deaktivierte Zugänge nicht
- `qs_kuerzel_von(stamm, userId)` – Kürzel, die mit einem Mitarbeiter verknüpft sind
- `qs_pruefung_meine(p, stamm, userId)` – Ist der Mitarbeiter für die Prüfung eingeteilt (ausführend oder über sein Kürzel zuständig/Vertreter)?

**Prüfen der Eingaben**

- `qs_text(v, max, was)`
- `qs_datum(v, was, pflicht)`
- `qs_wahl(v, erlaubt, was)`
- `qs_kuerzel(v, was, max)` – Kürzel einer Person (Zuständig, Vertreter, erstellt …): kurz, ohne Zeilenumbruch; muss nicht in der Personenliste stehen (ältere Einträge nennen auch …
- `qs_kapitel_pruefen(v, stamm, was, pflicht)`
- `qs_ablage(v)`
- `qs_verweise(v)`
- `qs_mitarbeiter_liste(v, erlaubt, was)` – Liste von Mitarbeiter-Kennungen (nur bekannte, ohne doppelte)

**Datum**

- `qs_dt(d)`
- `qs_plus_tage(d, n)`
- `qs_monatstage(j, m)`
- `qs_plus_monate(d, monate)` – Datum + Monate ohne Überlauf (31.01. + 1 Monat = 28./29.02.)
- `qs_tage_bis(von, bis)`
- `qs_feiertag(d)`
- `qs_arbeitstag(d)`

**Stammdaten: Kapitel, Personen, Einstellungen**

- `qs_kapitel_liste_pruefen(v, alt, benutzt)`
- `qs_personen_pruefen(v, alt, mitarbeiter)` – Personen mit Kürzel; „mitarbeiter“ verknüpft das Kürzel mit einem Mitarbeiterkonto der Plattform (je Mitarbeiter höchstens ein Kürzel).
- `qs_einstellungen_pruefen(v, alt)`
- `qs_kapitel_benutzt()` – Welche Kapitel werden von Dokumenten, Abschnitten, Prüfungen oder Maßnahmen verwendet?

**Dokumente und Versionen**

- `qs_dokument_pruefen(b, alt, stamm, alle, struktur)` – $struktur: Nummernstruktur durchsetzen (Anlegen und Ändern in der Oberfläche; nicht beim Datenpaket aus der Excel) – neue Dokumente der Arten A, F, L, E und …

**Nummernstruktur**

- `qs_nr_naechste(alle, kap, art, ohne)`
- `qs_nr_struktur(nr, kap, art, alle, alt)` – Nummer prüfen bzw. vergeben (leer = nächste freie); Art in Großbuchstaben
- `qs_dokument_index(doc, id)`
- `qs_ver_index(d, status)` – Index der gültigen (freigegebenen) bzw. der offenen Version (Entwurf, in Prüfung, geprüft) oder null
- `qs_naechste_nr(d)`
- `qs_dok_status(d)` – Zustand eines Dokuments für Übersicht und Filter
- `qs_ueberpruefung(d, monate, heute)` – Überprüfung: seit (letzte Freigabe oder „ohne Änderung überprüft“), fällig ab (+ N Monate), fällig ja/nein.
- `qs_dok_aus(d, monate, heute)`
- `qs_entwurf(me, aenderungen, grund)` – Neuer Entwurf (Version ohne Nummer)

**Dokumentenablage**

- `qs_dateien_aktiv(liste)`
- `qs_ablage_stelle(d, ver, me, was)` – Darf $me an dieser Stelle (Dokument, Version-ID oder '' für Ordner/externe Dokumente) Dateien ablegen bzw. entfernen?
- `qs_ablage_einstellungen()` – Einstellungen für die Oberfläche: erlaubte Dateiendungen, Höchstgröße je Datei und je Teilstück, Dateien je Stelle
- `qs_datei_finden(liste, id)` – Datei in allen Dokumenten suchen: [Dokument-Index, Version-Index oder null, Datei-Index] oder null
- `qs_datei_gleich(d, vi, sha)` – Liegt an dieser Stelle (Version bzw. Dokument) schon eine aktive Datei mit diesem Inhalt (SHA-256, auch Rohfassung)?
- `qs_dateien_zahl(liste)`
- `qs_ablage_eintraege(dokumente, stamm, kapitel, alle, heute)` – Einträge für den ZIP-Export „QM-System/<Kapitel>/<Dokument>/<Datei>“: gültige Version (bzw.

**Handbuch**

- `qs_abschnitt_felder(b, stamm)`
- `qs_abschnitte_sortieren(liste)`

**Prüfplan, Nachweise und Fälligkeit**

- `qs_pruefung_felder(b, stamm, mitarbeiter)`
- `qs_nachweise_nach_pruefung(nachweise)` – Nachweise je Prüfung (ohne stornierte), neueste zuerst
- `qs_periode(art, d)` – Kalender-Periode eines Datums: Tag „2026-10-30“, Woche „2026-W44“, Monat „2026-10“
- `qs_periode_ende(art, d)` – Letzter Tag der Periode (Fälligkeit)
- `qs_perioden(intervall, ab, bis)` – Fällige Perioden von $ab bis $bis (einschließlich): Liste [Periode, Ende]; bei „Arbeitstage“ ohne Wochenende/Feiertage
- `qs_monatsverlauf(eigene, heute, iv, ab, erledigt)` – Verlauf der letzten 6 Monate und des laufenden Monats für den Jahresplan: je Monat fällige Perioden (nur Kalender- Intervalle; die laufende, noch offene …
- `qs_faelligkeit(p, eigene, heute)`
- `qs_faelligkeit_kern(p, eigene, heute)`
- `qs_nachweis_felder(b, p, heute)`
- `qs_pruefung_finden(plan, id)`

**Maßnahmen (Aufbau des IFS-Maßnahmenplans)**

- `qs_massnahme_felder(b, stamm)`
- `qs_massnahme_nr(liste, jahr)` – Nächste Nummer „JJJJ-NNN“ je Jahr
- `qs_massnahme_aus(m, heute)`

**Übersicht für die Oberfläche**

- `qs_pruefungen_aus(plan, nachweise, heute)`
- `qs_startseite(me)` – Startseite des Dashboards („Heute für Sie“, lib/startseite.php): eigene Prüfungen (eingeteilt wie in „Ihre Aufgaben“ der Übersicht, qs_pruefung_meine) mit …

**CSV (Excel)**

- `qs_csv_zelle(v)`
- `qs_csv(kopf, zeilen)`
- `qs_de(iso)`
- `qs_csv_dokumente(dokumente, stamm, heute)`
- `qs_csv_pruefplan(pruefungen, namen)`
- `qs_csv_massnahmen(liste)`

**Datenpaket (bisherige Excel „QM-System“ und Maßnahmenpläne)**

- `qs_paket_pruefen(p, me)`

## `app/api/module/qs/verfahren-export.php`

_QM-System · Verfahrensdokumentation_

- `__construct(fuss, gesamt, marke)`
- `rahmen()`
- `seiten()`
- `neueSeite()`
- `platz(h)` – Platz für $h Punkt sichern (sonst neue Seite)
- `abstand(h)`
- `linie()`
- `text(t, size, bold, farbe, einzug, vor)` – Text mit Zeilenumbrüchen und Umbruch nach Wörtern; $einzug in Punkt, $vor = Zeichen vor der ersten Zeile (z. B. „•“)
- `paar(k, v)` – „Bezeichnung Wert“ (Wert mit Umbruch); leere Werte werden ausgelassen
- `qs_vf_pdf_name(inhalt, kuerzel)`
- `qs_vf_pdf_gueltig(ab, bis)`
- `qs_vf_pdf_inhalt(s, inhalt)` – Inhalt einer Fassung (oder des Arbeitsstands) setzen
- `qs_vf_pdf_lauf(doku, teile, alle, k, gesamt)` – Ein Durchlauf.
- `qs_vf_pdf(doku, teile, alle, k)`
- `qs_vf_export_dateien(teile, dokumente, wurzel)` – Dateien der verknüpften QM-Dokumente in den Versionen, die die Fassungen festgehalten haben (für das ZIP)
- `qs_vf_export(doku, q, me, dokumente, stamm)` – Export ausführen und senden (endet immer).
- `qs_vf_pdf_senden(pdf, name, inline)`

## `app/api/module/qs/verfahren.php`

_QM-System · Verfahrensdokumentation nach GoBD (Reiter „Verfahrensdoku“ der Oberfläche qs.intern, Aktionen qs_verfahren* in app/api/aktionen/qs.php; wird nur von diesen Aktionen geladen)._

- `qs_vf_muster()` – Mustergliederung: [Teil, Überschrift, Frage].

**Lesen und Ordnen**

- `qs_vf_normal(d)` – Gespeicherte Dokumentation mit allen Listen und Feldern (unvollständige Einträge bleiben lesbar, GR-006)
- `qs_vf_sortieren(abschnitte)`
- `qs_vf_nummern(sortiert)` – Nummern „<Teil>.<lfd.
- `qs_vf_naechste_pos(abschnitte, teil)`
- `qs_vf_index(liste, id, was)` – Index eines Eintrags (Abschnitt, System) in einer Liste der Dokumentation oder 404
- `qs_vf_system_in_fassung(doku, id)` – Steht das IT-System in einer freigegebenen Fassung?

**Prüfen der Eingaben**

- `qs_vf_zeile(v, max, was)`
- `qs_vf_kopf_felder(b)`
- `qs_vf_abschnitt_felder(b, doku)`
- `qs_vf_system_felder(b)`

**Verknüpfte QM-Dokumente**

- `qs_vf_dok_finden(dokumente, verweis)` – Verweis „2.5-A01 Rechnungsbearbeitung“ → Dokument, wenn die Dokumenten-Nr. vorne steht (wie verweisDok() in qs.js)
- `qs_vf_dok_stand(d)` – Stand eines verknüpften Dokuments: gültige Version mit Datum (leer, wenn keine gilt oder kein Dokument gefunden wurde)

**Schnappschuss, Abweichung, Überprüfung**

- `qs_vf_inhalt(doku, dokumente, stamm)` – Inhalt, wie er in eine Fassung eingeht: Kopf, Abschnitte mit Nummer und dem Stand der verknüpften QM-Dokumente, IT-Systeme, Liste der verknüpften …
- `qs_vf_abweichung(neu, alt)` – Was hat sich gegenüber einer Fassung geändert?
- `qs_vf_ueberpruefung(doku, heute)` – Überprüfung: seit (letzte Fassung oder „ohne Änderung überprüft“), fällig ab (+ 12 Monate).
- `qs_vf_gueltig_bis(fassungen, i)` – Letzter Tag, an dem die Fassung mit dem Index $i galt (Tag vor „gültig ab“ der nächsten); leer = gilt noch
- `qs_vf_fassung_bilden(doku, dokumente, stamm, me, grund, gueltigAb, heute)` – Neue Fassung bilden (prüft alle Voraussetzungen, schreibt nicht)

**Antwort für die Oberfläche**

- `qs_vf_aus(doku, dokumente, stamm, heute)` – Dokumentation für die Oberfläche: Abschnitte sortiert mit Nummer, Fassungen ohne Inhalt (den liefert der Export als PDF), Abweichung seit der letzten …
- `qs_vf_laden(id)` – Dokumentation für eine Änderung laden (unter der Sperre): [Speicher-Dokument, Index, Dokumentation] oder 404
- `qs_vf_antworten(doku)`
- `qs_vf_ablegen(doc, i, doku, me)` – Dokumentation nach einer Änderung speichern: Stand hochzählen, „geändert“ setzen

## `app/api/module/qs/vorlagen.php`

_Qualitätssicherung · Vorlagen und Lenkungsangaben in Word- und Excel-Dateien (Bauabschnitt 3, nur bei Bedarf geladen von app/api/aktionen/qs.php)._

**Werte der Platzhalter**

- `qs_platzhalter_feld(name)`
- `qs_werte_stamm(d, stamm)`
- `qs_wer_kurz(stamm, wer, kuerzel)` – Wer (Kürzel aus der Verknüpfung, sonst Schnappschuss-Kürzel, sonst Name)
- `qs_werte_lenkung(d, v, stamm)`

**ZIP lesen und schreiben (Office Open XML)**

- `qs_zip_lesen(z)` – Einträge in Reihenfolge: name → [methode, crc, komp, roh, flags, pos (Beginn der gepackten Daten in $z)] oder null, wenn kein lesbares ZIP.
- `qs_zip_inhalt(z, e)` – Inhalt eines Eintrags entpacken (Grenze gegen ZIP-Bomben, Prüfsumme) oder null
- `qs_zip_bauen(eintraege, z)` – ZIP schreiben: Einträge wie von qs_zip_lesen (gepackte Daten aus $z); mit 'neu' => Inhalt neu gepackt, sonst unverändert übernommen

**Platzhalter ersetzen**

- `qs_stuecke_ersetzen(seg, werte, offen)` – Textstücke einer Gruppe (Absatz, Zelle): $seg = [['t' => Text], …]; ersetzt Platzhalter auch über Stückgrenzen.
- `qs_xml_ersetzen(xml, gruppe, tt, werte, offen, n)` – XML mit Gruppen (<w:p>/<si>/<is>) und Textelementen (<w:t>/<t>): Platzhalter je Gruppe ersetzen
- `qs_excel_kopf_ersetzen(xml, werte, offen, n)` – Kopf- und Fußzeilen in Excel (Text mit Steuerzeichen „&“: ein echtes & wird „&&“)
- `qs_office_fuellen(daten, art, werte, alsDokument)` – Word-/Excel-Datei ausfüllen.
- `qs_office_platzhalter(daten, art)` – Welche bekannten Platzhalter enthält die Datei?

**Anwenden**

- `qs_vorlage_dateien(vd)` – Gültige Version einer Vorlage mit ihren Word-/Excel-Dateien (oder Fehler 422)
- `qs_vorlage_anwenden(vd, d, stamm, me, erzeugt)` – Neues Dokument aus der Vorlage: Dateien gefüllt mit den Stammangaben ablegen, Einträge für die erste Version zurückgeben.
- `qs_lenkung_eintragen(d, v, stamm, me, erzeugt)` – Bei der Freigabe: Lenkungsangaben in die Word-/Excel-Dateien der Version eintragen (nicht bei Vorlagen).
- `qs_lenkung_datei(d, v, f, stamm, me, erzeugt)` – Eine Datei einer freigegebenen Version ausfüllen (auch beim Nachtragen); unverändert, wenn nicht nötig oder nicht lesbar
- `qs_dateien_uebernehmen(g, me, erzeugt)` – Überarbeitung: Dateien der gültigen Version (Rohfassung mit Platzhaltern) als Kopie in den neuen Entwurf
- `qs_erzeugte_aufraeumen(erzeugt, fertig)` – Neu erzeugte Dateien wieder entfernen, wenn das Speichern scheitert (Aufruf am Ende der Anfrage)

## `app/module/qs/qs.js`

_STAFL-Plattform · Qualitätssicherung (QM-System) – Oberfläche nach dem Designvorschlag vom 30.10.2026._

**Aufruf der API: wirft nie, liefert { status, data, json }**

- `api(action, body, query)`
- `toast(text, fehlerhaft)`
- `fehler(text)`
- `zeigeAnmeldung()`

**Formate und Hilfen**

**Hell/Dunkel**

- `themaKnopf()`

**Reiter**

- `zeigeTab(tab)`

**Daten**

- `setzeDaten(d)`
- `neuLaden()`
- `renderAlles()`
- `filterOptionen()`

**Dokumente: Zustand**

- `zustandChip(d)`
- `beteiligte(v)` – erstellt · geprüft · freigegeben: Kürzel aus der Excel oder Initialen der Plattform-Namen

**Prüfungen: Fälligkeit**

- `faelligChip(p)`

**Übersicht**

- `renderUebersicht()`

**Dokumente**

- `passtZustand(x, z)`
- `renderDokumente()`
- `oeffneDok(id)` – Dokument in der Seitenleiste (unter 1100 px als Blatt von unten)
- `schliesseDok()`

**Dokumentenablage (Server: qs_datei_hochladen, qs_datei, qs_datei_entfernen, qs_ablage_export)**

- `ablageOffen(x, v)`
- `dateiHerkunft(f, v)`
- `dateiListe(x, v, leer)`
- `ablageZone(x, v, text, klein)`
- `ladenHtml(x, vid)`
- `ladenAktualisieren(i)`
- `pruefsumme(f)`
- `dateiSenden(f, dok, ver, nurNeu, beiTeil)` – Eine Datei in Teilen hochladen (der API-Einstieg nimmt nur JSON bis 6 MB an). nurNeu: gleicher Inhalt an dieser Stelle wird nicht noch einmal abgelegt …
- `hochladen(dateien, vid)` – Dateien nacheinander ablegen (Seitenleiste: Ziehen oder Auswählen)
- `waehleDateien(vid)`
- `dateiOrt(x, id)`
- `speichereDatei(blob, name)`
- `herunterladen(id)`
- `entferneDatei(id)`

**Sammel-Ablage: ganzer Ordner „QM-System“ oder ein ZIP davon**

- `saIndex()`
- `saNrIn(t, idx)`
- `saZiel(x)`
- `saPruefen(e, idx)`
- `saZeile(e, i)`
- `saZeigen()`
- `saZeileNeu(i)`
- `oeffneSammel()`
- `saLesenOrdner(eintrag, pfad, aus)`
- `saZipLesen(file)`
- `saZipEintrag(file, lokal, komp, methode, flags, name)`
- `saLaden(quelle)`
- `exportUmfang(kap, alle)` – Export der Ablage als ZIP: der Server erstellt das Archiv erst beim Herunterladen (direkt in die Antwort)
- `exportHinweis()`
- `oeffneExport()`
- `renderDok()`
- `vorlagePasst(x, art)`
- `dfVorlagen()`
- `naechsteNr(kap, art)`
- `oeffneDokForm(id)`
- `dfHilfe()`

**Handbuch**

- `abschnitteSichtbar()`
- `verweisDok(text)` – Verweis „1.3-L02 HACCP-Analyse“ → Dokument, wenn die Dokumenten-Nr. vorne steht
- `renderHandbuch()`
- `oeffneAbschnitt(id)`

**Prüfplan: Jahresplan (6 Monate zurück, aktueller Monat, 5 voraus)**

- `planZellen(p)`
- `renderPruefplan()`
- `oeffnePruefung(id)`
- `renderPruefung()`
- `maWahl(gewaehlt)`
- `oeffnePruefForm(id)`
- `oeffneNachweis(id)` – Nachweis erfassen (wer die Kontrolle zugewiesen hat oder „bearbeiten“ darf)
- `nwAbweichung()`
- `setzeErgebnis(e)`

**Maßnahmen**

- `massnTabelle(liste)`
- `renderMassnahmen()`
- `oeffneMassnahme(id)`
- `msNotiz()`

**Einstellungen: Personen, Kapitel, Überprüfung, Datenpaket**

- `renderEinstellungen()`

**Audit-Bericht**

- `berichtZeitraum(art)`
- `zeitraumSetzen()`
- `erstelleBericht()`
- `bMatrix(b)`
- `bVersaeumnisse(b)`
- `bAbweichungen(b)`
- `bMassnahmen(b)`
- `bDokumente(b)`
- `bHandbuch(b)`
- `renderBericht()`

**Eingabemasken: gemeinsame Hilfen**

- `oeffne(dlg)`
- `senden(form, action, body)`
- `frageGrund(titel, text, label, pflicht)` – Grund abfragen → Text oder null (abgebrochen)
- `ladeCsv(liste, dateiname)` – CSV vom Server herunterladen – der Server vermerkt es im Protokoll

**Start**

- `laden()`

## `app/module/qs/verfahren.js`

_STAFL-Plattform · Qualitätssicherung – Reiter „Verfahrensdoku“_

**Laden und Übernehmen**

- `zeigen()`
- `setze(dk)`

**Ansicht**

- `render()`
- `verweisHtml(d, v)`
- `renderTeile(d, b)`
- `renderSysteme(d, b)`
- `renderFassungen(d)`

**Export (PDF bzw. ZIP): lädt über fetch, damit Fehler als Text erscheinen**

- `lade(query)`
- `ladePdf(nr)`

**Dialog: allgemeine Angaben**

- `oeffneKopf(neu)`

**Dialog: Abschnitt**

- `oeffneAbschnitt(id, teil)`

**Dialog: IT-System**

- `oeffneSystem(id)`

**Dialog: Fassung freigeben oder „ohne Änderung überprüft“**

- `oeffneFreigabe()`

**Dialog: Export für Prüfungen**

- `enthalten()`
- `oeffneExport()`

## `tests/e2e/test_qs.py`

_Qualitätssicherung (Modul qs, Oberfläche qs.intern unter /module/qs/) – QM-System_

- `check(n, c, i)`
- `tag(delta)`
- `ostern(j)`
- `feiertag_hamburg(d)`
- `dok(cli, did)`
- `schritt(cli, did, s, **extra)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe, ziel)`
- `toast(pg, inhalt)`

## `tests/e2e/test_qs_ablage.py`

_Qualitätssicherung – Dokumentenablage (QM-System Bauabschnitt 2)_

- `check(n, c, i)`
- `pdf(text, groesse)` – Erfundene Dateien mit passendem Dateikopf
- `docx(text)`
- `docx_w(text)`
- `aktiv_(liste)`
- `blob_pfad(did)`
- `blobs()`
- `teile_reste()`
- `hochladen(cli, dok, ver, name, inhalt, teil, sha, groesse, nur_erster)` – Datei in Teilen hochladen wie die Oberfläche; Rückgabe (Status, Antwort des letzten Aufrufs, Zahl der Aufrufe)
- `teil_senden(cli, dok, ver, name, groesse, upload, nr, stueck, sha)`
- `roh(cli, query)` – GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)
- `zip_lesen(inhalt)`
- `dok(did, cli)`
- `schritt(cli, did, s, **extra)`
- `nur_neu(cli, dok_, ver, name, inhalt)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe)`
- `toast(pg, inhalt)`
- `oeffne_dok(pg, did)`
- `passt(pg)`
- `sa_status()`
- `sa_zahl(n)`

## `tests/e2e/test_qs_bericht.py`

_Qualitätssicherung – Audit-Bericht (app/api/module/qs/bericht.php, Aktionen qs_bericht und qs_bericht_excel, Reiter „Audit“)._

- `check(n, c, i)`
- `tag(n)`
- `kern(fall)`
- `nw(p, d, e, storno, massnahme)`
- `bericht(plan, nachweise, von, bis, heute, massnahmen, dokumente, handbuch, xlsx)`
- `zeitraum(von, bis)`
- `anmelden(user, pw_, ip, breite, thema, hoehe)`
- `text(pg, sel)`

## `tests/e2e/test_qs_verfahren.py`

_Qualitätssicherung – Verfahrensdokumentation nach GoBD (app/api/module/qs/verfahren.php und verfahren-export.php, Aktionen qs_verfahren*, Reiter „Verfahrensdoku“ in app/module/qs/verfahren.js)._

- `check(n, c, i)`
- `tag(n)`
- `de(iso)`
- `roh(cli, query)` – GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)
- `pdf_text(raw)` – Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi – je Seite eine Liste von Zeilen
- `fehlertext(inhalt)`
- `hochladen(cli, dok, ver, name, inhalt)`
- `doku(cli, did)`
- `abschnitt(nr)`
- `speichern(cli, a, **neu)`
- `anmelden(user, pw_, ip, breite, thema, hoehe, ziel)`

## `tests/e2e/test_qs_vorlagen.py`

_Qualitätssicherung – Vorlagen und Nummernstruktur (QM-System Bauabschnitt 3, app/api/module/qs/vorlagen.php)._

- `check(n, c, i)`
- `_x(t)`
- `docx(absaetze, kopf, vorlage)` – absaetze: Liste von Absätzen, je Liste von Textstücken (so zerlegt Word Text beim Tippen)
- `xltx(zellen, kopf, fuss)`
- `word_text(daten, teil)`
- `hochladen(cli, dok, ver, name, inhalt)`
- `roh(cli, query)`
- `blob(did)`
- `blobs()`
- `dok(did)`
- `schritt(cli, did, s, **extra)`
- `neu(cli, **b)`
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe)`
- `toast(pg, inhalt)`
- `oeffne_dok(pg, did)`
