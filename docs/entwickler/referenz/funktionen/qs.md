# Funktionen: Qualitätssicherung (`qs`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

22 Dateien, 484 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/qs.php`

_Aktionen: QM-System (Oberfläche qs.intern, Daten und Regeln in app/api/module/qs/qs.php) Rechte (GR-103): qs.sehen – Übersicht, Dokumente mit Versionen, Handbuch, Prüfplan mit Nachweisen, Maßnahmen, CSV, …_

- `qs_index(doc, id, was)` – Index eines Eintrags einer Liste oder 404
- `qs_rev_pruefen(b, alt, was)` – Veralteter Stand eines Eintrags → 409 mit dem aktuellen Eintrag
- `qs_dok_name(d)`
- `qs_dok_antwort(d)`

## `app/api/module/qs/ablage.php`

_QM-System · Dokumentenablage_

- `qs_dateien_aktiv(liste)`

**Regeln je Stelle**

- `qs_ablage_regel(d, ver, me, was, belegt, neu)` – Darf $me an dieser Stelle Dateien ablegen ('hochladen'), aus dem Eingang zuordnen ('zuordnen') oder entfernen ('entfernen')?
- `qs_ablage_stelle(d, ver, me, was, belegt, neu)`
- `qs_ablage_einstellungen()` – Einstellungen für die Oberfläche: erlaubte Dateiendungen und Größen (vom Plattformkern), Grenzen je Stelle und je Bündel

**Leser beider Ablageorte: ältere Dateien am Ordner (qs-dokumente, „dateien“) und qs-ablage**

- `qs_ablage_nach_ziel(ablage)` – Einträge von qs-ablage je Ziel (Index für qs_ordner_dateien)
- `qs_ordner_dateien(d, index)` – Alle Dateien eines Ordners/externen Dokuments, auch entfernte: ältere am Dokument und die aus $index (qs_ablage_nach_ziel; leer = nur die älteren)
- `qs_ablage_belegt(d, je)` – Aktive Dateien eines Ordners/externen Dokuments (ältere und $je aus qs_ablage_je bzw. qs-ablage-zahlen) bzw. des Eingangs ($d = null)
- `qs_datei_suchen(liste, id)` – Datei suchen – in qs-dokumente (Versionen, ältere am Ordner), sonst in qs-ablage: [Datei, Dokument-Index, Version-Index, Index] oder null.

**qs-ablage und qs-ablage-zahlen**

- `qs_im_eingang(f)`
- `qs_ablage_je(liste)` – Zahl und Bytes der aktiven Dateien je Ziel
- `qs_ablage_schreiben(ab)` – qs-ablage schreiben und qs-ablage-zahlen neu zählen – immer beide, unter der Sperre „qs-dokumente“
- `qs_ablage_zahlen()`
- `qs_ablage_uebersicht(dokumente)` – Zahl und Bytes je Ordner/externem Dokument für qs_start – nur für $dokumente (die sichtbaren): qs-ablage-zahlen und die älteren Dateien am Dokument
- `qs_datei_eintrag(datei, me, pfad)` – Eintrag einer hochgeladenen Datei (Version oder qs-ablage); pfad nur, wenn gesetzt
- `qs_pfad(v)` – Ordnerpfad „pfad“ (Anzeige, Ordnerbaum, Suche – nie ein Pfad im Dateisystem), Format in 05-daten.md
- `qs_ablage_auswahl(v)` – Auswahl im Eingang: eindeutige Datei-Kennungen (als Text, auch wenn sie nur aus Ziffern bestehen)
- `qs_dokumente_dateien(liste)` – Kennungen aller Dateien in qs-dokumente (auch Rohfassungen ausgefüllter Dateien)
- `qs_ablage_aufraeumen(abgelegt, erzeugt, gespeichert)` – Am Ende der Anfrage die hier abgelegten bzw. erzeugten Dateien entfernen, die nicht gespeichert sind – registriert vor dem Ablegen, damit auch ein Abbruch …

**Eintragen: Version (qs-dokumente) oder qs-ablage**

- `qs_datei_eintragen(d, vi, me, f, erzeugt)` – Datei $f in die Version $vi eintragen.
- `qs_ablage_vermerk(d, vi, me, namen, wie)` – Ein Verlaufseintrag je Vorgang: im Entwurf an der Version, an freigegebenen Versionen auch am Dokument (nachgetragen)
- `qs_ablage_eintragen(neu, me, wie, erzeugt)` – Hochgeladene Dateien eintragen (Kern für Upload und Ordner-Import, ohne fail()).
- `qs_datei_gleich(d, vi, sha)` – Liegt in dieser Version schon eine aktive Datei mit diesem Inhalt (SHA-256, auch Rohfassung)?

**Eingang**

- `qs_eingang_dateien()` – Dateien im Eingang für die Oberfläche (qs_eingang)
- `qs_eingang_ziele(dokumente, me)` – Ziele, denen $me aus dem Eingang zuordnen darf (qs_ablage_regel 'zuordnen'): Ordner, externe Dokumente, Entwürfe – je {dok, ver}
- `qs_eingang_platzhalter(ids)` – Platzhalter der Word-/Excel-Dateien im Eingang, die in einen Entwurf zugeordnet werden – vor der Sperre gelesen
- `qs_eingang_zuordnen(ids, dok, ver, me, platzhalter, erzeugt)` – Dateien aus dem Eingang zuordnen: an einen Ordner/ein externes Dokument ändert sich nur „ziel“ (ein Schreibvorgang), in einen Entwurf wandert der Eintrag …
- `qs_eingang_loeschen(ids)` – Dateien im Eingang endgültig löschen: Einträge weg, Prüfsummen gemerkt (ein erneuter Import legt sie nicht wieder in den Eingang).

**Archiv: Dateien eines Ordners/externen Dokuments**

- `qs_archiv_dateien(d)` – Dateien eines Ordners/externen Dokuments (ältere und qs-ablage, auch entfernte) – für Ordnerbaum, ZIP
- `qs_archiv_antwort(f)` – Datei für Ordnerbaum und Eingang (ohne Prüfsumme und Dateiart – hält die Antwort klein)
- `qs_archiv_entfernen(doc, id, b, me)` – Datei eines Ordners/externen Dokuments in qs-ablage als „entfernt“ vermerken (mit Grund; die Datei bleibt).
- `qs_dateien_text(n)`
- `qs_dateien_zahl(liste)` – Zahl der aktiven Dateien in qs-dokumente und qs-ablage (Datenpaket: ersetzt nicht, sobald Dateien liegen) – qs-ablage direkt gezählt
- `qs_archiv_zip_pfad(f)` – ZIP-Pfad einer Archivdatei unter dem Ordner des Dokuments: <pfad>/<Datei>
- `qs_ablage_eintraege(dokumente, stamm, kapitel, alle, heute)` – Einträge für den ZIP-Export „QM-System/<Kapitel>/<Dokument>/<Datei>“: gültige Version bzw. Archivdateien (mit Unterordnern aus pfad); mit $alle zusätzlich …

**Ordner-Import (Regeln in 05-daten.md, nur hier berechnet)**

- `qs_norm(t)`
- `qs_norm_trenner(t)`
- `qs_import_schluessel(...teile)` – Schlüssel aus mehreren Teilen (Ordner-Dokument, schon Abgelegtes, gleiche Datei)
- `qs_nr_schluessel(nr)` – Dokumenten-Nr.
- `qs_import_teile(pfad)` – Ordnernamen eines Pfads aus dem Browser („/“ oder „\“ getrennt); kein Text oder zu lang → 422
- `qs_import_ordner_lesen(ordner)` – Ordnerliste der Anfrage [[Ordnerpfad wie gewählt, [[Name, Größe], …]], …] prüfen → [[Ordnerpfad, Ordnernamen, [[Name, Größe], …]], …]
- `qs_import_angaben(b)` – Angaben des Nutzers (Plan und Eintragen): wurzel {name, art sf\|kapitel\|neu\|'' (keine Antwort), kapitel, titel}, wahl und freigaben {nachtragen, entwurf} je …
- `qs_import_kapitel(stamm)`
- `qs_import_erkannt(name, kap)` – Kapitel (kein Bereich), dessen Nummer vorn im Ordnernamen steht, oder null
- `qs_import_exakt(name, k)` – Heißt der Ordner genau wie das Kapitel („<Nr>“, „<Nr> <Titel>“) bzw. wie der Bereich (auch nur der Titel, auch mit „_“ vorn)?
- `qs_import_bereich_name(name, kap)`
- `qs_import_weglassbar(name, kap)` – Darf der gemeinsame erste Ordner wegfallen?
- `qs_import_oben(t, A, kap)` – Ordnernamen ab dem obersten Ordner.
- `qs_import_zuordnung(name, x, offen, A, kap)` – Zuordnung eines obersten Ordners: die Wahl des Nutzers ($x bzw. $A['wahl'][$name]) gilt immer; ohne Wahl ein Kapitelordner (genau „<Nr>“ oder „<Nr> <Titel>“: …
- `qs_import_verzeichnis(dokumente, kap)` – Verzeichnisse aus qs-dokumente (beim Eintragen unter der Sperre neu gebaut): Nummern gelenkter Dokumente – ohne Bereiche, dort nie per Nummer –, Ordnernamen …
- `qs_import_rest_passt(rest, d)` – Passt der Rest hinter der Nummer zum Dokument?
- `qs_import_kapitel_passt(d, kap)`
- `qs_import_nr_dok(name, kap, V)` – Datei direkt im Kapitelordner: Name ohne Endung beginnt mit der Nummer, der Rest ist leer oder der Titel
- `qs_import_gelenkt(d, name, groesse, voll, me)` – Ziel eines gelenkten Dokuments: ein offener Entwurf geht vor (dokument), sonst die gültige Version (nachtragen, nur mit Freigaberecht); gesperrt → Eingang
- `qs_import_archiv(z, t, voll, V)` – Archiv: Ordner-Dokument je (Kapitel, Unterordner der ersten Ebene bzw. „Weitere Dateien“), tiefere Ebenen als pfad; der Name des obersten Ordners steht vorn …
- `qs_import_ueberspringen(name, groesse, oben)` – Grund zum Überspringen (Systemdatei, Liste eines eigenen Exports, Dateiart, leer, zu groß) oder null
- `qs_import_datei(t, name, groesse, z, ohne, V, export, me)` – Entscheidung für eine Datei (rein; Plan und Eintragen).
- `qs_import_plan(ordner, A, me, stamm, dokumente, ablage)` – Zuordnungsplan (Aktion qs_sammel_plan).
- `qs_import_anlegen(plan, me, stamm, doc)` – Bereiche und Ordner-Dokumente des Plans anlegen (unter der Sperre): erst alle Grenzen prüfen, dann schreiben; danach zeigen die Einträge des Plans auf die …
- `qs_import_planen(b, me)` – Ordner-Import, Schritt 1 (Aktion qs_sammel_plan): Plan; mit anlegen unter der Sperre einmal gerechnet und danach Bereiche und Ordner-Dokumente angelegt.
- `qs_import_uploads(v)` – Uploads eines Bündels aus der Anfrage: [[upload, erwarteter Status (QS_IMPORT_ABLEGEN), Version, abgewählt], …], 1 bis QS_IMPORT_BUENDEL
- `qs_import_eintragen(ups, A, me)` – Ordner-Import, Schritt 2 (Aktion qs_import_eintragen): fertige Uploads (qs_datei_hochladen mit sammeln) in einem Schreibvorgang eintragen.

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

## `app/api/module/qs/organigramm.php`

_QM-System · Organigramm als gelenktes Dokument (Entscheidung des Inhabers 16.11.2026 „Im QM-System zeichnen“; nur bei Bedarf geladen von app/api/aktionen/qs.php)._

- `qs_organigramm_pruefen(v, alt, stamm)` – Eingabe → gültige Struktur ohne Namens-Schnappschuss; null bei leerer Liste (Organigramm aus dem Entwurf nehmen).
- `qs_organigramm_speichern()` – Aktion qs_organigramm_save: Struktur im offenen Entwurf speichern, mit leerer Liste entfernen (Stand „rev“ wie bei qs_version_save).
- `qs_organigramm_uebernehmen(gueltig, neu)` – „Überarbeitung beginnen“: Struktur der gültigen Version in den neuen Entwurf – ohne Namens-Schnappschuss (im Entwurf gelten die heutigen Namen)
- `qs_organigramm_schritt(d, v, me, erzeugt)` – Nach jedem Schritt in qs_version_schritt: ab dem Einreichen hält die Version die Namen fest – der Prüfer prüft genau diese, die Freigabe übernimmt sie …
- `qs_organigramm_namen(og, stamm)`
- `qs_organigramm_vorschau()` – Aktion qs_organigramm_vorschau (GET): dieselbe PDF wie bei der Freigabe für die offene Version, als ENTWURF gekennzeichnet – der Prüfer sieht vorher, was …
- `qs_organigramm_lage(knoten, hoehe)` – Lage aller Kästen und Linien in pt, Ursprung oben links: ['b', 'h', 'kaesten' => [id => ['x', 'y']], 'linien' => [[x1, y1, x2, y2]]].
- `qs_og_teilbaum(id, unter, hoehe)` – Teilbaum ab $id mit Ursprung oben links: Stabsstellen paarweise links und rechts der Linie unter der Stelle; Unterstellen nebeneinander – oder senkrecht …
- `qs_og_verschieben(ziel, teil, dx, dy)`
- `qs_organigramm_kasten(k, namen)` – Kasten einer Stelle: Textzeilen mit Grundlinie y (pt ab Oberkante) und Höhe h – Stelle, Person(en) oder „unbesetzt“, Vertretung, Hinweis
- `qs_og_trennen(wort, g, innen, fett)` – Wort, das auch verkleinert nicht in die Zeile passt, mit Trennstrich zerlegen (Teile mit Leerzeichen für Pdf::wrap)
- `qs_og_einpassen(t, g, max, fett)` – Text auf $max pt Breite: erst verkleinern (bis QS_OG_MIN_SCHRIFT), dann mit „…“ kürzen → [Text, Größe]
- `qs_organigramm_pdf(d, v, stamm, marke)` – Eine Seite A4 quer: Logo, Titel und Firma im Kopf, Lenkungsangaben im Fuß (wie die Platzhalter in Word-/Excel-Dateien).

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
- `qs_dok_ablegen(doc, i, d, me)` – Dokument in qs-dokumente speichern: Stand hochzählen, „geändert“ setzen (unter der Sperre)

**Geschützte Kapitel (1.5 „Mitarbeiter“, Entscheidung des Inhabers 16.11.2026)**

- `qs_kapitel_geschuetzt(k)`
- `qs_sichtbar(me, ...namen)` – Die eine Stelle für alle Lesewege (Liste, Suche, Zahlen, CSV, Dateien, Ordnerbaum, ZIP, Bericht, Verfahrensdoku): lädt die genannten Listen (dokumente, …
- `qs_dok_sichtbar(d, me)`
- `qs_protokoll_name(e, name)` – Name im Protokoll: aus geschützten Kapiteln nur die Kapitelnummer – das Protokoll sieht, wer „protokoll.sehen“ hat, nicht nur „bearbeiten“
- `qs_leer()` – Ist das Modul noch leer (für den Import ohne „ersetzen“)?
- `qs_nat_cmp(a, b)` – Kapitel- und Abschnittsnummern natürlich sortieren („1.2“ vor „1.10“, „2.0.9“ vor „2.0.10“)

**Mitarbeiter (Plattformkern, nur lesen)**

- `qs_mitarbeiter()` – Wählbare Mitarbeiter: aktive Zugänge und Mitarbeiter ohne Anmeldung (z. B. Lager); deaktivierte Zugänge nicht
- `qs_kuerzel_von(stamm, userId)` – Kürzel, die mit einem Mitarbeiter verknüpft sind
- `qs_pruefung_meine(p, stamm, userId)` – Ist der Mitarbeiter für die Prüfung eingeteilt (ausführend oder über sein Kürzel zuständig/Vertreter)?
- `qs_massnahme_meine(m, kuerzel)` – Ist die Maßnahme einem der Kürzel $kuerzel (qs_kuerzel_von) zugewiesen – „Zuständig“ kann mehrere nennen („QB / TE“)?

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
- `qs_vf_antworten(doku, me)`
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
- `qs_xml_ersetzen(xml, gruppe, tt, werte, offen, n)` – XML mit Gruppen (<w:p>/<si>/<is>) und Textelementen (<w:t>/<t>): Platzhalter je Gruppe ersetzen. null, wenn der Teil größer als QS_XML_BYTES_MAX ist oder …
- `qs_excel_kopf_ersetzen(xml, werte, offen, n)` – Kopf- und Fußzeilen in Excel (Text mit Steuerzeichen „&“: ein echtes & wird „&&“)
- `qs_office_fuellen(daten, art, werte, alsDokument)` – Word-/Excel-Datei ausfüllen.
- `qs_office_platzhalter(daten, art)` – Welche bekannten Platzhalter enthält die Datei?
- `qs_platzhalter_vorab(datei)` – Platzhalter einer hochgeladenen Word-/Excel-Datei (für die Anzeige im Entwurf) – vor der Sperre gelesen; null bei anderen Arten oder nicht lesbar.

**Anwenden**

- `qs_vorlage_dateien(vd)` – Gültige Version einer Vorlage mit ihren Word-/Excel-Dateien (oder Fehler 422)
- `qs_vorlage_anwenden(vd, d, stamm, me, erzeugt)` – Neues Dokument aus der Vorlage: Dateien gefüllt mit den Stammangaben ablegen, Einträge für die erste Version zurückgeben.
- `qs_lenkung_eintragen(d, v, stamm, me, erzeugt)` – Bei der Freigabe: Lenkungsangaben in die Word-/Excel-Dateien der Version eintragen (nicht bei Vorlagen).
- `qs_lenkung_datei(d, v, f, stamm, me, erzeugt)` – Eine Datei einer freigegebenen Version ausfüllen (auch beim Nachtragen); unverändert, wenn nicht nötig oder nicht lesbar
- `qs_dateien_uebernehmen(g, me, erzeugt)` – Überarbeitung: Dateien der gültigen Version (Rohfassung mit Platzhaltern) als Kopie in den neuen Entwurf
- `qs_erzeugte_aufraeumen(erzeugt, fertig)` – Neu erzeugte Dateien wieder entfernen, wenn das Speichern scheitert (Aufruf am Ende der Anfrage)

## `app/module/qs/archiv.js`

_STAFL-Plattform · QM-System_

**Ordnerbaum: Map pfad → Knoten, <details> erst beim Aufklappen gefüllt**

- `baumBauen(dateien)`
- `dateiZeile(f, offen, mitPfad)`
- `knotenInhalt(k, offen)`
- `baumZeichnen()`
- `inhaltZeichnen(w, offen)`
- `baumLaden(dok)`
- `baumHtml(x)` – HTML des Ordnerbaums für die Seitenleiste (qs.js renderDok); lädt beim ersten Öffnen eines Dokuments
- `neu(dok)` – Nach Hochladen/Entfernen neu laden: Eingang bzw. Ordner des Dokuments
- `ladeEingang()`
- `eingangSicht()`
- `eingangZiele(ziele)`
- `eingangKnoepfe()`
- `eingangZeichnen()`
- `oeffneEingang()`
- `eingangWeg(ids)`
- `eingangFehler(r, text)`

## `app/module/qs/ordnerimport.js`

_STAFL-Plattform · QM-System_

**Ordner, Ziehen und ZIP lesen: Liste { pfad (Ordner), name, groesse, holen }**

- `ordnerLesen(e, pfad, aus)`
- `zipLesen(file)`
- `zipEintrag(file, lokal, komp, methode, flags, name)`

**Plan vom Server: Dateien je Ordner gebündelt (hält die Anfrage unter 6 MB)**

- `planen(anlegen)`
- `laden(quelle)`

**Vorschau**

- `meldung(text, ok)`
- `wurzelHtml(P)` – Wohin gehört der gewählte Ordner?
- `wahlHtml(z)`
- `zahlen(liste)`
- `freigabenHtml(P)` – Freigaben je oberstem Ordner: Nachtragen in gültige Versionen (Vorgabe aus), Entwürfe (Vorgabe an); Dateien je Dokument gruppiert, einzeln abwählbar
- `zeichnen()`
- `dateiZeile(e)`
- `listeZeichnen()`

**Lauf: LAUFEND Uploads gleichzeitig, fertige Uploads gebündelt eintragen, Fehler halten nicht an**

- `fortschritt()`
- `buendelZahl(l)` – So viele fertige Uploads passen in ein Bündel: Zahl, Bytes und Word/Excel-Nachträge (Lenkung unter der Sperre) – Grenzen vom Server
- `eintragenJetzt(alle)`
- `arbeiter()`
- `starten()`
- `berichtCsv()`

**Ereignisse**

- `oeffnen()`
- `neuPlanen()`

## `app/module/qs/organigramm.js`

_STAFL-Plattform · QM-System – Organigramm in einem gelenkten Dokument_

- `sichern()` – Ungespeicherte Zeichnung je Person und Entwurf im Tab sichern: übersteht Ablauf der Anmeldung, Neuladen und das Schließen bei einem Konflikt. sessionStorage …
- `gesichert()`
- `sicherungWeg()`

**Karte in der Seitenleiste des Dokuments**

- `karte(x)`
- `vorschau(id)` – dieselbe PDF, die die Freigabe ablegt, mit „ENTWURF“ gekennzeichnet; liefert '' oder den Fehlertext

**Diagramm**

- `kastenHtml(k)`
- `knotenHtml(k)`
- `zeichnen()`
- `zoom(z)`
- `einpassen()`

**Felder der gewählten Stelle**

- `felder()`
- `waehle(id)`
- `geaendert()`
- `neu(teil)`
- `tauschen(k, schritt)`
- `loeschen(k)`

**Fenster**

- `fenster()`
- `oeffnen(id, art)` – art: 'ansehen' = gültige Version, 'entwurf' = offene Version nur lesen, 'bearbeiten' = offener Entwurf.
- `schliessen()`
- `sperren(an)` – Während der Anfrage samt Konfliktbehandlung ist die Zeichnung gesperrt: die Antwort überschreibt keine neuen Eingaben, Schließen und ein zweiter Lauf warten
- `speichern()`
- `uebertragen(tokenHolen)` – Zeichnung senden → [Meldung, gespeichert?]; nach einer Anmeldung in einem anderen Tab einmal mit neuem CSRF-Token erneut

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
- `dateiSenden(f, dok, ver, beiTeil, extra)` – Eine Datei in Teilen hochladen (der API-Einstieg nimmt nur JSON bis 6 MB an); extra: pfad, sammeln, herkunft (Ordner-Import).
- `hochladen(dateien, vid, dok)`
- `waehleDateien(vid, dok)`
- `dateiOrt(x, id)`
- `speichereDatei(blob, name)`
- `herunterladen(id)` – Herunterladen über einen direkten Link wie der ZIP-Export: große Dateien landen nicht im Speicher des Browsers, der Browser zeigt den Fortschritt
- `entferneDatei(id)`
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
- `csrfNeu()` – Jede Anmeldung erzeugt ein neues CSRF-Token (sign_in) – nach einer Anmeldung in einem anderen Tab hier nachholen; true = geändert.

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
- `archiv(did, cli)` – ── Ordner: Dateien im Archiv (qs-ablage, geladen über qs_archiv) ──
- `text(pg, sel)`
- `anmelden(user, pw, ip, breite, thema, hoehe)`
- `toast(pg, inhalt)`
- `oeffne_dok(pg, did)`
- `passt(pg)`

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

## `tests/e2e/test_qs_eingang.py`

_QM-System – Eingang (Dateien ohne Ziel, Dokument qs-ablage mit ziel „eingang“, module/qs/ablage.php)._

- `hoch_e(cli, name, inhalt, pfad)`
- `eingang(cli)`
- `archiv(did)`
- `dok(did)`
- `schritt(cli, did, s, **extra)`
- `halb_zugeordnet(name, did, vi)`
- `toast(pg, inhalt)`
- `ei_warte(pg, n)`

## `tests/e2e/test_qs_import.py`

_QM-System – Ordner-Import (qs_sammel_plan, qs_import_eintragen, module/qs/ablage.php) und Ordnerbaum (qs_archiv, qs_archiv_zip)._

- `plan(cli, pfade, angaben, anlegen)` – Plan für Pfade („Ordner/…/Datei“ oder (Pfad, Größe)); Rückgabe (Status, Antwort, {Pfad: Eintrag})
- `sammeln(cli, pfad, inhalt)` – Upload für den Ordner-Import: nur Name und Herkunft (Ordnerpfad wie gewählt) – Rückgabe der fertige Upload (noch nicht eingetragen)
- `eintragen(cli, ups, angaben, **extra)` – ups: [(Upload, Plan-Eintrag)] – erwarteter Status und Version wie im Plan
- `dok(did)`
- `dok_titel(titel, kap)`
- `archiv(did, cli)`
- `eingang()`
- `benutzt()` – Kennungen, auf die qs-dokumente (auch Rohfassungen) und qs-ablage zeigen
- `gelenkt(kap, art, nr, titel, gueltig)`
- `ist(e, neu)`
- `gross_docx(mb)`
- `lange_absaetze(n, laenge)` – Word-Datei mit Platzhalter: entpackt rund 28 MB in 19.800 Textelementen (unter der Elementgrenze), gepackt rund 0,1 MB
- `zahl(pg, n)`
- `zeilen(pg)`
- `oberste(pg)`
- `warte_ende(pg)`
- `neu_geplant(pg, aktion)` – Aktion, die einen neuen Plan anfordert – wartet auf dessen Antwort
- `qm_waehlen(pg, wurzel_beantworten)`

## `tests/e2e/test_qs_kapitel15.py`

_QM-System – Kapitel 1.5 „Mitarbeiter“ samt Unterkapiteln 1.5.x (personenbezogene Unterlagen, Entscheidung des Inhabers 16.11.2026): alles daraus sieht nur, wer „bearbeiten“ darf (qs_sichtbar, qs_dok_sichtbar in …_

- `dok(did, cli)`
- `schritt(did, s, cli)`
- `ordner(kap, titel, datei)`
- `drin(raw, liste)`
- `excel(cli)`

## `tests/e2e/test_qs_organigramm.py`

_Qualitätssicherung – Organigramm im QM-System (app/api/module/qs/organigramm.php, Aktionen qs_organigramm_save und qs_organigramm_vorschau, Oberfläche app/module/qs/organigramm.js)._

- `check(n, c, i)`
- `de(iso)`
- `roh(cli, query)` – GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)
- `pdf_text(raw)` – Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi – je Seite eine Liste von Zeilen
- `dok(cli, did)`
- `knoten(id_, titel, ueber, art, personen, vertretung, hinweis)`
- `speichern(cli, liste, d)`
- `schritt(cli, s, **mehr)`
- `vorschau(cli, did)`
- `fehler_bei(name, liste, teil)`
- `antwort(ja)`
- `baum(pg)`
- `lage(pg)`
- `meldung(pg, teil)`
- `anmelden(user, pw_, ip, breite, thema, hoehe)`
- `oeffne_dok(pg, did)`
- `andere_person_speichert(hinweis)` – zwei Personen am selben Entwurf: Rückfrage statt Sackgasse
- `gf_hinweis()`
- `abgelaufen(url)`

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
