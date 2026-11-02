# Funktionen: HR (`hr`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

9 Dateien, 143 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/hr.php`

_Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/) Rechte (GR-103): hr.antrag – eigener Urlaub, Anträge (nur wenn in Verwaltung → Urlaub eingeschaltet), Abwesenheitskalender (nur …_

- `hr_jahr_param(v)` – Jahr aus der Anfrage (Standard: aktuelles Jahr)
- `hr_person_aus(p, eintraege, jahr)` – Angaben einer Person für die Personalstelle

## `app/api/module/hr/export.php`

_Modul HR · Excel-Export für den Steuerberater: ein Blatt je Monat in Aufbau und Gestaltung der bisherigen Planungsdatei „Urlaub 2026“ (Legende, Monatstitel, Wochentage, Tageszahlen, Abteilungen senkrecht, Kürzel …_

**ZIP (Methode „stored“)**

- `hr_zip(dateien)`

**Formate**

- `__construct()`
- `liste(l, xml)`
- `id(s)` – $s: fett, gr (Schriftgröße), farbe (RGB der Schrift), fill (RGB), rand [links, rechts, oben, unten] (thin\|medium\|''), h (left\|center), v (center), dreh (Grad)
- `xml()`
- `hr_xl_spalte(n)`
- `hr_xl_text(t)`
- `hr_xl_blatt(m, st)` – Ein Monatsblatt (sheet-XML)
- `hr_xlsx(monate)` – Arbeitsmappe aus Monatsplänen (hr_monat mit voller Sicht, aber nur genehmigte Einträge)
- `hr_export_monat(jahr, monat)` – Monatsplan für den Export: alle aktiven Mitarbeiter, nur genehmigte Einträge, Kürzel U/K/G/x.
- `hr_export_dateiname(jahr, monate)`

## `app/api/module/hr/import.php`

_Modul HR · Importe für die Importzentrale (Verwaltung → Import, docs/plattform/schnittstellen/import.md)_

- `hr_import_zeitraeume(tage)` – Kürzel zu Zeiträumen zusammenfassen: aufeinanderfolgende Arbeitstage (Mo–Fr ohne Feiertage) mit gleichem Kürzel
- `import_arten_hr()` – Importart für die Importzentrale (Verwaltung → Import).
- `hr_import_stand(personal, abw, mitarbeiter)` – Stand der HR-Daten für Vorschau und Übernahme (veralteter Stand → 409)

## `app/api/module/hr/urlaub.php`

_Modul HR · Urlaubsverwaltung – Fachlogik (Daten, Feiertage, Urlaubskonto, Anträge, Korrekturmeldungen, Monatsplan)._

**Datum**

- `hr_heute()`
- `hr_ts(d)`
- `hr_plus(d, n)`
- `hr_wochentag(d)`
- `hr_datum(v)`
- `hr_de(d)`
- `hr_zeitraum_text(von, bis)`
- `hr_ostern(j)` – Ostersonntag (gregorianisch, Verfahren nach Meeus/Jones/Butcher) – ohne PHP-Erweiterung „calendar“
- `hr_feiertage(j)` – Gesetzliche Feiertage in Hamburg: Datum → Name
- `hr_feiertag(d)`
- `hr_arbeitstag(p, d)` – Arbeitstag der Person (Wochentag laut Arbeitstagen, kein Feiertag)
- `hr_tage(p, von, bis, ab, bis2, frei)` – Arbeitstage einer Person im Zeitraum (optional nur innerhalb [$ab, $bis2]; ohne freie Tage aus $frei: Datum → true)
- `hr_freie_tage(eintraege, person)` – Einzeln eingetragene freie Tage („x“) einer Person: Datum → true

**Daten lesen und prüfen**

- `hr_person_norm(p)`
- `hr_name(p)`

**Mitarbeiter = Nutzer**

- `hr_personal_roh()` – Gespeicherte HR-Angaben (Rohdaten zum Schreiben)
- `hr_nutzer_namen(u)` – Vor- und Nachname eines Mitarbeiters (ältere Konten haben nur „name“: letztes Wort = Nachname)
- `hr_personal()` – Alle Mitarbeiter mit ihren HR-Angaben, sortiert nach Position
- `hr_angaben_setzen(roh, uid, werte, u)` – HR-Angaben eines Mitarbeiters speichern (anlegen oder ändern; unter der Sperre „hr-personal“ aufrufen).
- `hr_abwesenheiten_umhaengen(von, nach)` – Abwesenheiten von einer Personenkennung auf eine andere umhängen (Übernahme eines Altbestands-Eintrags)
- `hr_abwesenheiten()`
- `hr_einstellungen()`

**Verfallstag des Resturlaubs aus dem Vorjahr**

- `hr_uebertrag_bis_norm(v)`
- `hr_uebertrag_bis(neu)`
- `hr_nach_abteilung(personen)` – Reihenfolge für Kalender und Export: Abteilungen nach der kleinsten Position ihrer Mitarbeiter, darin nach Position (wie in der Planungsdatei: jede Abteilung …
- `hr_personen_index(personal)`
- `hr_namekey(n)`

**Altbestand: Einträge ohne Mitarbeiter übernehmen**

- `hr_konto_namen(u)`
- `hr_altbestand_ids(roh, users)` – Kennungen der Einträge ohne gültigen Mitarbeiter (genau die, die hr_personal() als „altbestand“ zeigt): kein „nutzer“, der verknüpfte Mitarbeiter wurde …
- `hr_eintrag_des_nutzers(roh, uid)` – Erster gespeicherter Eintrag eines Mitarbeiters (seine HR-Angaben) – Index in $roh['personen'] oder null
- `hr_altbestand_zuordnen(roh, eintragId, u)` – Altbestands-Eintrag einem Mitarbeiter zuordnen (unter der Sperre „hr-personal“): Abwesenheiten, die schon unter der Mitarbeiter-Kennung stehen, wandern zum …
- `hr_altbestand_zusammenfuehren(roh, eintragId, u)`
- `hr_personal_uebernehmen(me)` – Altbestands-Einträge dem gleichnamigen Mitarbeiter ohne HR-Angaben zuordnen (eindeutiger Name).
- `hr_ich(personal, me)` – Person des angemeldeten Mitarbeiters (im Urlaubsplan)
- `hr_eigen(personal, me, e)` – Gehört der Eintrag dem angemeldeten Mitarbeiter?
- `hr_eigene_angaben_pruefen(werte, jahr, jv, uid, u)` – Eigene HR-Angaben (mitarbeiter_hr_save für sich selbst): Felder mit Einfluss auf das Urlaubskonto dürfen sich nicht ändern – unveränderte Werte werden …
- `hr_eigene_ids(personal, me)` – Kennungen der eigenen Person(en) des angemeldeten Mitarbeiters (verknüpft, auch nicht im Urlaubsplan) – für das Vier-Augen-Prinzip bei Angaben, Zuordnung und …
- `hr_eigene_person(personal, me, person)`
- `hr_offene_antraege(personal, abw, me)` – Offene Urlaubsanträge für die Entscheidung (hr_verwaltung, hr_offen): Konto, Vertretung, wer aus derselben Abteilung gleichzeitig weg ist (ohne Grund), …
- `hr_zeitraeume_pruefen(l, was)` – Zeiträume (Urlaubssperren, Ferien) prüfen: [{von, bis, text}]
- `hr_in_zeitraum(liste, d)`
- `hr_ueberschneidung(liste, von, bis)`

**Urlaubskonto**

- `hr_anspruch(p, jahr)` – Anspruch eines Jahres: Eintrag des Jahres, sonst der letzte frühere Eintrag (gleichbleibender Anspruch)
- `hr_konto(p, eintraege, jahr, heute, tiefe)` – Urlaubskonto einer Person für ein Jahr.

**Urlaubsübersicht (Recht hr.uebersicht oder hr.verwalten)**

- `hr_tage_je_art(p, eintraege, jahr)`
- `hr_uebersicht(jahr)`

**Einträge (Anträge und Eintragungen der Personalstelle)**

- `hr_eintrag_aus(e, p, frei)` – Eintrag für die Ausgabe.
- `hr_kollision(eintraege, person, von, bis, ohne, art)` – Überschneidung mit einem aktiven Eintrag derselben Person (außer $ohne).
- `hr_zeitraum_pruefen(b)`
- `hr_neue_id(prefix)`
- `hr_abwesenheiten_schreiben(d)` – Abwesenheiten speichern (unter Sperre aufrufen)

**Korrekturmeldungen (Dokument hr-korrekturen)**

- `hr_korrekturen()`
- `hr_korrekturen_schreiben(d)`
- `hr_korrektur_aus(m, p)` – Meldung für die Ausgabe (Person selbst oder Personalstelle); $p: Person der Meldung (für den Namen), sonst „ehemalig“
- `hr_personal_schreiben(d)`

**Monatsplan und Kalender**

- `hr_monatstage(jahr, monat, einst)` – Tageskopf eines Monats: Wochentag, Wochenende, Feiertag, Ferien, Urlaubssperre
- `hr_zeile(p, eintraege, tage, sicht)` – Kürzel je Person und Tag eines Monats.
- `hr_monat(jahr, monat, me, voll)` – Monatsplan: alle aktiven Mitarbeiter, gruppiert nach Abteilung (Reihenfolge laut Position)

## `app/api/module/hr/zeiterfassung.php`

_Modul HR · Import „Abwesenheiten aus der Zeiterfassung“ (Abwesenheitsbericht, .xlsx) – Importvorlage für die Urlaubstage (Entscheidung des Inhabers, 23.10.2026)._

- `hr_zeit_datum(v)` – Datum aus einer Zelle: Excel-Seriennummer (mit Uhrzeit als Bruchteil) oder Text „TT-MM-JJJJ“, „TT.MM.JJJJ“, „JJJJ-MM-TT“
- `hr_zeit_art(art)` – Art der Abwesenheit → Kürzel (null = nicht übernehmen, z. B. Feiertag; false = unbekannt)
- `hr_zeit_lesen(e)` – Bericht lesen (Zellen vom Leser im Browser): Mitarbeiter und Abwesenheiten
- `hr_zeit_zuordnen(l, personal, users)` – Mitarbeiter zuordnen: Personalnummer, sonst Name (Anzeigename, Vor-/Nachname, Benutzername)
- `hr_zeit_planen(e, me)` – $me: wer übernimmt – Abwesenheiten der eigenen Person werden nicht übernommen, ihre früheren Einträge nicht ersetzt und ihre Angaben nicht geändert …
- `hr_zeit_vorschau(e, me)`
- `hr_zeit_uebernehmen(e, me)`

## `app/module/hr/hr.js`

_STAFL-Plattform · HR · Urlaub Mitarbeiter: eigenes Urlaubskonto (nur Urlaub, nie Krankheit), Urlaubsantrag (ausblendbar_

- `api(action, body, query)`

**Datum und Zahlen**

- `meldung(el, text, art)`

**Kopf, Anmeldung**

- `initialen(name)`
- `fehler(text)`
- `zeigeAnmeldung(ziel)`
- `themaKnopf()`

**Reiter**

- `zeigeTab(tab)`

**Mein Urlaub**

- `ladeStart()`
- `wert(titel, n, cls, zusatz)`
- `zeigeMein()`

**Mein Jahr: Mini-Kalender aller eigenen Abwesenheiten**

- `zeigeMiniKalender()`

**Korrektur melden (an die Personalstelle)**

- `korrekturDialog(v)`
- `zeigeKorrekturen()`
- `antragTage()` – Arbeitstage des Antrags (Vorschau im Browser; verbindlich rechnet der Server)

**Kalender / Monatsplan**

- `kalLegende(voll)`
- `heuteSichtbar()` – Spalte „heute“ in den sichtbaren Bereich holen (am Handy scrollt die Tabelle waagerecht): nur wenn sie verdeckt ist, dann mittig rechts neben die festen Namen
- `kalZusammen(daten, von, bis)` – Monatsdaten zu einem Plan zusammenführen: Tage im Zeitraum, Mitarbeiter je Abteilung in der Reihenfolge des Servers, Kürzel je Datum (der Server liefert je …
- `ladeKalender()`
- `kalFilter(alle)`
- `zeigeKalender()`

**Personalstelle: Daten**

- `ladeVerwaltung(jahr)`
- `ladeAntraege()` – Offene Anträge: Personalstelle über hr_verwaltung, sonst (nur „Urlaub genehmigen“) über hr_offen
- `zahlOffen()` – Zahl am Reiter: entscheidbare Anträge (ohne eigene); ohne Genehmigungsrecht alle offenen
- `fehlerVerwaltung(text)`

**Anträge**

- `zeigeAntraege()`
- `zeigeEintraege()`
- `zeigeKorrekturenVerwaltung()` – Korrekturmeldungen der Mitarbeiter (Personalstelle): offene mit Antwortfeld und „Erledigt“, zuletzt erledigte gedämpft
- `alertKarte(karte, text)`

**Abwesenheit eintragen / ändern**

- `eintragDialog(e)`
- `nachEintrag()`

**Urlaubsübersicht (hr.uebersicht oder Personalstelle): nur Summen**

- `ladeUebersicht()`
- `zeigeUebersicht()`

**Export**

- `zeigeExport()`

**Start**

- `laden()`

## `app/module/hr/verwaltung-hr.js`

_STAFL-Plattform · HR im Eingabebereich der Verwaltung - Verwaltung → Mitarbeiter_

- `laden()`

**Spalten der Mitarbeiterliste (Administratoren)**

- `zelle(uid)`

**HR-Teil im Dialog**

- `formular(uid)`
- `speichern(uid, form)` – HR-Angaben aus dem Formular speichern (nach dem Speichern des Mitarbeiters, mit dessen Kennung)
- `altbestand()` – Hinweis: Einträge der Urlaubsliste ohne Mitarbeiter (Altbestand) übernehmen
- `vorschlag(e, ps)`
- `altDialogInhalt()`
- `altDialog(nachher)`
- `altbestandUebernehmen(btn, nachher)`

**Personalstelle ohne Administratorrechte: nur HR-Angaben**

- `renderNurHr(host)`
- `nurHrDialog(uid, host)`

**Verwaltung → Urlaub: Urlaubssperren und Ferien**

- `renderUrlaub()`

## `tests/e2e/test_hr.py`

_HR · Urlaubsverwaltung (Modul hr, Oberfläche hr.intern unter /module/hr/)._

- `check(n, c, i)`
- `montag(jahr, monat, woche)` – Montag der n-ten vollen Woche eines Monats (ohne Feiertage im Februar/August).
- `iso(d)`
- `dokument(name)` – Gespeichertes Dokument lesen (Dateien: ohne Schutzzeile).
- `hr(uid, **werte)`
- `person_zeile(v, n)`
- `urlaub(d1, d2)`
- `zimp(cl, uebernehmen, stand)`
- `anmelden(user, pw, ip, breite)`
- `zeit(cl, uebernehmen, stand, **opt)`

## `tests/e2e/test_hr_uebersicht.py`

_HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht, Personalstelle hr.verwalten sieht sie auch)._

- `check(n, c, i)`
- `montag(jahr, monat, woche)`
- `iso(d)`
- `hr(uid, **werte)`
- `eintrag(person, art, von, bis, notiz)` – ── Daten (Personalstelle trägt ein, Lena beantragt) ──
- `anmelden(user, pw, ip, breite)`
