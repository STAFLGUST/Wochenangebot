# Funktionen: HR (`hr`)

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: Funktionen und Kommentare im Code. Die CI prüft, dass diese Datei zum Code passt. -->

11 Dateien, 280 Funktionen – in der Reihenfolge der Datei, **fett** die Abschnitte. Text = erste Aussage des Kommentars direkt über der Funktion (Python: Docstring). Übersicht aller Module: [README.md](README.md).

## `app/api/aktionen/hr.php`

_Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/) Rechte (GR-103): hr.antrag – eigener Urlaub und Gleittage, Anträge (nur wenn in Verwaltung → Urlaub eingeschaltet; Gleittage nur …_

- `hr_jahr_param(v)` – Jahr aus der Anfrage (Standard: aktuelles Jahr)
- `hr_person_aus(p, eintraege, jahr)` – Angaben einer Person für die Personalstelle
- `hr_einstellungen_aus(einst)` – Einstellungen für Verwaltung → Urlaub: eingetragene Sperren (zum Bearbeiten), Sperren aus den Regeln (nur Anzeige, dieses und nächstes Jahr), Schalter, …

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

## `app/api/module/hr/mail.php`

_Modul HR · E-Mails der Urlaubsverwaltung (Inhaber 03.11.2026)._

- `hr_mail_adresse(v)` – Gültige E-Mail-Adresse (eine, ohne Zeilenumbruch) oder ''
- `hr_mail_einst(d)` – Einstellungen (fehlende Felder: aus)
- `hr_mail_monate(jetzt)` – Monate relativ zu heute (deutsche Zeit des Servers): [Vormonat, laufender Monat] als „JJJJ-MM“
- `hr_ym_text(ym)`
- `hr_mail_naechste(m, jetzt)` – Nächste automatische Termine (für die Anzeige)
- `hr_mail_empfaenger()` – Mitarbeiter im Urlaubsplan mit Anmeldungskonto und E-Mail-Adresse: [[Person, Adresse], …] und Zahl ohne Adresse
- `hr_mail_ziel(m, an, name, betreff)` – Testmodus: Empfänger und Betreff umlenken

**Aufbau der HR-Mails (Inhaber 03.11.2026: ordentlich, mit kurzen Tabellen und Link zum Portal)**

- `hr_mail_rahmen(betreff, text, html, ueberschrift)`
- `hr_mail_link()`
- `hr_mail_knopf()` – Link zum Urlaubsportal: großer Knopf und darunter die Adresse zum Abtippen; Text: Adresse in eigener Zeile
- `hr_zahl_text(n)`
- `hr_tage_text(n)`
- `hr_mail_h2(t)` – Zwischenüberschrift (HTML)
- `hr_mail_box(t)` – Hervorgehobener Hinweis (HTML)
- `hr_mail_tabelle(zeilen)` – Kurze Tabelle aus Zeilen [Bezeichnung, Wert, fett?, Zusatzzeile?] (HTML) – Werte rechtsbündig, Zusatzzeile klein unter der Bezeichnung
- `hr_mail_tabelle_text(zeilen)` – Dieselbe Tabelle als Text (Spalten mit Leerzeichen ausgerichtet)
- `hr_mail_konto_zeilen(k)` – Urlaubskonto eines Jahres als Zeilen für hr_mail_tabelle: Anspruch, Übertrag, Verfallen, Genommen, Geplant, Resturlaub
- `hr_mail_jahr_monate(p, eintraege, jahr, heute)` – Genehmigte Urlaubstage je Monat eines Jahres (Arbeitstage wie im Konto): [1..12 => ['genommen' => n, 'geplant' => n]]
- `hr_mail_jahr_html(m, hervor)` – Jahr auf einen Blick: zwei Reihen mit je sechs Monaten, Urlaubstage je Monat (grau = nur geplant), $hervor = Monat der Mail
- `hr_mail_jahr_text(m)`
- `hr_mail_zeitraeume(p, eintraege, von, bis, beantragt)` – Urlaubszeiträume eines Jahres (genehmigt, auf Wunsch auch beantragt) als Zeilen [Zeitraum, Tage]
- `hr_mail_vorname(p)`
- `hr_mail_verfall_satz(k)`
- `hr_mail_monat_inhalt(p, eintraege, ym)` – Monatsübersicht einer Person: Urlaub (genehmigt) im Monat mit Arbeitstagen, Urlaubskonto des Jahres als kurze Tabelle, das Jahr auf einen Blick (Urlaubstage …
- `hr_mail_erinnerung_inhalt(p, k)` – Erinnerung „Resturlaub verfällt“
- `hr_mail_versenden(jobs, art, wie, me, zusatz, antwortAn, verlauf)` – Versand: Jobs senden, Verlauf und Protokoll schreiben.
- `hr_monat_senden(ym, wie, me)` – Monatsübersicht für „JJJJ-MM“ an alle Mitarbeiter mit Adresse (Testmodus: an die Testadresse)
- `hr_erinnerung_kandidaten()` – Erinnerung an alle, bei denen im laufenden Jahr Übertrag verfallen würde
- `hr_erinnerung_senden(me)`
- `hr_mail_fehlen_inhalt(p, e, eintraege)` – Unentschuldigtes Fehlen: Zeitraum, Bitte um unverzügliche Erklärung per E-Mail und Urlaubsübersicht des Jahres (Konto als kurze Tabelle, Urlaubszeiträume – …
- `hr_fehlen_mail(p, e, eintraege, me)` – E-Mail nach dem Eintragen von unentschuldigtem Fehlen.
- `hr_mail_vertretung_inhalt(ich, vp, zeitraeume, eintraege, haupt)` – E-Mail an die Vertretung: wer nicht da ist, wann (Zeiträume mit Arbeitstagen des Antragstellers) und in welcher Rolle – ohne Art, Notiz oder Grund.
- `hr_vertretung_benachrichtigen(ich, neu, personal, eintraege, me)` – Vertretung benachrichtigen (Inhaber 10.11.2026): nach einem Antrag oder einer Vorplanung bekommt jede eingetragene Vertretung – auch die zusätzliche – eine …
- `hr_stb_senden(wie, me)` – Excel-Übersicht des Vormonats und des laufenden Monats an den Steuerberater
- `hr_mail_anstossen()` – Automatischer Versand: von HR-Aufrufen angemeldeter Mitarbeiter angestoßen.
- `hr_mail_speichern(b)` – Einstellungen speichern (Verwaltung → Urlaub).
- `hr_mail_aus()` – Für Verwaltung → Urlaub: Einstellungen, Vorschau (Empfänger), nächste Termine, Verlauf, Postfach eingerichtet?

## `app/api/module/hr/planung.php`

_Modul HR · Jahresplanung des Urlaubs (Inhaber 03.11.2026, Vorplanung und Einzeltage 10.11.2026)._

- `hr_planung_einst(d)` – Einstellungen der Jahresplanung (fehlende oder ungültige Felder: Standard)
- `hr_planung_einst_pruefen(b)` – Einstellungen aus der Verwaltung prüfen (hr_einstellungen_save, Feld „planung“): {start, stichtag, prozent, vertretungPflicht, einzeltageMax (optional – ohne …
- `hr_planung_jahr(heute)` – Das Jahr, das geplant wird: das nächste Kalenderjahr
- `hr_planung_daten(pe, jahr)` – Stichtag und Beginn als Datum (im Jahr vor dem Planungsjahr)
- `hr_planung_person(p, eintraege, jahr, pe, zusatz)` – Stand einer Person: Anspruch, Ziel (Anteil des Anspruchs, auf halbe Tage aufgerundet), geplant = beantragt + genehmigt (dazu der Betriebsurlaub 24.12./31.12. …
- `hr_vorplanung_eintrag(e, jahr, pe)` – Entstand der Eintrag in der Vorplanung des Jahres? = bis zum Stichtag erfasst (UTC-Zeit, ohne Erfassungszeit: nein)
- `hr_einzeltage_hinweis(p, eintraege, e)` – Hinweis beim einzelnen Antrag (hr_antrag): liegt er in der Vorplanung seines Jahres und sind es damit mehr einzelne Urlaubstage als vorgesehen?
- `hr_einzeltage(p, eintraege, jahr, pe, zusatz)` – Einzelne Urlaubstage der Vorplanung eines Jahres (Inhaber 10.11.2026: höchstens einzeltageMax, der übrige Urlaub möglichst zusammenhängend).
- `hr_planung_ich(ich, eintraege, heute)` – Hinweis auf der Urlaubsseite des Mitarbeiters: nur in der Planungsphase (ab Beginn, bis die Planung abgeschlossen ist)
- `hr_planung_schnitt(a, b)` – Überschneidung zweier Zeiträume
- `hr_vertretung_luecken(e, p, vp, eintraege, nurGenehmigt)` – Wann ist die Vertretung im Zeitraum eines Antrags nicht da? Arbeitstage des Antragstellers, an denen die Vertretung abwesend ist (jede Abwesenheit außer …
- `hr_antrag_zeitraum(ich, personal, eintraege, einst, art, von, bis, vertretung, andere, vertretung2)` – Prüfung eines Zeitraums für einen eigenen Antrag – gemeinsam für hr_antrag, hr_vorplanung und die Vorschau hr_antrag_pruefen.
- `hr_feste_vertretung(ich, personal)` – Feste Vertretung eines Mitarbeiters aus den Stammdaten (hr-personal.vertretung, Verwaltung → Mitarbeiter; Inhaber 10.11.2026): steht im Antrag fest und muss …
- `hr_vertretung_text(e, idx)` – Vertretungen eines Eintrags als Text: „A“, „A, zusätzlich B“ oder ''
- `hr_meine_vertretungen(ich, personal, eintraege)` – Wen vertritt der Mitarbeiter?
- `hr_zeitraeume_anfrage(l)` – Zeiträume aus der Anfrage (Vorplanung und Vorschau): [{von, bis, vertretung}] – höchstens HR_VORPLANUNG_MAX
- `hr_vorplanung_pruefen(ich, personal, eintraege, einst, zr, jahr)` – Vorplanung prüfen (ohne zu speichern): jeder Zeitraum wie ein Antrag (hr_antrag_zeitraum), nur im Vorplanungsjahr.
- `hr_daten_text(daten)` – Daten als kurze Zeiträume (aufeinanderfolgende Kalendertage zusammengefasst, höchstens vier, dann „…“)
- `hr_planung_konflikte(e, p, idx, eintraege, sperren, pe, verfuegbar, einzel)` – Konflikte eines Urlaubsantrags in der Jahresplanung.
- `hr_planung(jahr, me)` – Zusammenfassung eines Jahres für die Personalstelle und „Urlaub genehmigen“: Mitarbeiter im Urlaubsplan mit Stand, alle Urlaubsanträge des Jahres (beantragt, …
- `hr_planung_freigeben(jahr, ids, me)` – Konfliktfreie Anträge gesammelt genehmigen (unter der Sperre hr-abwesenheiten): jeder Antrag wird neu geprüft; eigene, bereits entschiedene und solche mit …

**E-Mails der Jahresplanung (Aufbau wie die übrigen HR-Mails, module/hr/mail.php)**

- `hr_planung_mail_zeilen(p, eintraege, jahr, idx)` – Zeilen [Zeitraum (+ beantragt), Tage, –, Vertretung] eines Jahres für hr_mail_tabelle
- `hr_planung_erinnerung_inhalt(p, eintraege, jahr, pe, idx)` – Erinnerung „Bitte planen Sie Ihren Urlaub“
- `hr_planung_uebersicht_inhalt(p, eintraege, jahr, idx)` – Jahresübersicht nach dem Abschluss der Planung
- `hr_planung_empfaenger(jahr, nurOffen, person)` – Empfänger: Mitarbeiter im Urlaubsplan mit E-Mail-Adresse; $nurOffen: nur wer das Ziel noch nicht erreicht hat; $person: nur diese Person.
- `hr_planung_senden(art, jahr, me, person)` – Versand: art „planung“ (Erinnerung) oder „jahresuebersicht“
- `hr_planung_abschluss_setzen(jahr, zu, me)` – Abschluss setzen oder aufheben – geprüft und geschrieben unter der Sperre hr-einstellungen (zwei gleichzeitige Klicks schließen nur einmal ab, die …

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

**Sonderregelung Dezember: Schließtage (Inhaber 10.11.2026)**

- `hr_schliesstage_an(neu)`
- `hr_schliesstag(d)` – Schließtag?
- `hr_schliesstage(j)` – Schließtage eines Jahres: Datum → Text (für Kalender und Vorplanung)
- `hr_tag_wert(d, art)` – Gewicht eines Tages in einem Eintrag: Urlaub und Gleittag zählen an einem Schließtag nicht – dort gilt der Betriebsurlaub
- `hr_betriebsurlaub(p, eintraege, jahr)` – Betriebsurlaub einer Person in einem Jahr (verpflichtend, Inhaber 10.11.2026): Schließtage, die für sie Arbeitstage sind (kein Feiertag), ohne freie Tage und …
- `hr_tage_summe(tage, art)` – Summe der Gewichte einer Liste von Tagen (hr_tage)
- `hr_schnitt_ohne_schliesstage(a, b)` – Tage im Schnitt zweier Zeiträume ohne Schließtage (Kalendertage) – an Schließtagen ist ohnehin jeder weg

**Daten lesen und prüfen**

- `hr_person_norm(p)`
- `hr_name(p)`

**Abteilungen**

- `hr_abteilungen()`
- `hr_abteilung_aufloesen(p, liste)`
- `hr_abteilung_werte(nr, liste)` – Werte zum Speichern aus einer Nummer der Stammdaten ('' = keine Abteilung); unbekannte Nummer → Fehler

**Mitarbeiter = Nutzer**

- `hr_personal_roh()` – Gespeicherte HR-Angaben (Rohdaten zum Schreiben)
- `hr_nutzer_namen(u)` – Vor- und Nachname eines Mitarbeiters (ältere Konten haben nur „name“: letztes Wort = Nachname)
- `hr_personal()` – Alle Mitarbeiter mit ihren HR-Angaben, sortiert nach Position
- `hr_angaben_setzen(roh, uid, werte, u)` – HR-Angaben eines Mitarbeiters speichern (anlegen oder ändern; unter der Sperre „hr-personal“ aufrufen).
- `hr_abwesenheiten_umhaengen(von, nach)` – Abwesenheiten von einer Personenkennung auf eine andere umhängen (Übernahme eines Altbestands-Eintrags)
- `hr_abwesenheiten()`
- `hr_einstellungen()`
- `hr_ueberziehen_norm(v)`
- `hr_ueberzug(p, eintraege, neu)` – Überzug eines Urlaubsantrags (Inhaber 10.11.2026): um wie viele Tage gehen die verfügbaren Tage (Rest − offene Anträge) mit den neuen Einträgen ins Minus?
- `hr_ueberzug_text(u, max)` – Text zum Überzug für Antragsteller: über der Grenze (abgelehnt) oder darunter (Rückfrage „Trotzdem absenden“)

**Urlaubsregeln und Sperren aus den Regeln (Inhaber 03.11.2026)**

- `hr_regeln_text(t)` – Gespeicherter Text der Urlaubsregeln für die Anzeige: ohne Feld oder als unveränderte frühere Vorlage die aktuelle Vorlage
- `hr_regeln_pruefen(t)` – Text der Urlaubsregeln prüfen: Zeichenkette, höchstens HR_REGELN_MAX Zeichen, ohne Steuerzeichen (Zeilenumbrüche bleiben)
- `hr_regel_sperren(j, schliess)` – Sperren aus den Urlaubsregeln für ein Jahr: Ostergeschäft = die zwei Wochen vor Karfreitag (Karfreitag − 14 bis Gründonnerstag), Weihnachtsgeschäft = Montag …

**Verfallstag des Resturlaubs aus dem Vorjahr**

- `hr_uebertrag_bis_norm(v)`
- `hr_uebertrag_bis(neu)`
- `hr_verfall_ab_norm(v)`
- `hr_verfall_ab(neu)` – Erstes Jahr mit Verfall (0 = jedes Jahr)
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

**Gleittage-Konto (Inhaber 02.11.2026)**

- `hr_gleit_norm(l)`
- `hr_gleit_wirksam(p)` – Wirksame Gewährungen und Beginn des Kontos (Tag der ersten wirksamen Gewährung)
- `hr_gleit_beginn(p)`
- `hr_gleit_konto(p, eintraege, jahr, heute)` – Gleittage-Konto einer Person für ein Jahr: Übertrag (Rest des Vorjahres, ohne Verfall) + gewährt − genommen − geplant = Rest; verfügbar = Rest − beantragt.
- `hr_gleit_aus(p, voll)` – Gewährungen für die Ausgabe (neueste zuerst); $voll: mit Kennung der gewährenden Person (nur Personalstelle)
- `hr_gleittage_setzen(b, me)` – Gleittage gewähren oder eine Gewährung stornieren (Personalstelle, nie für sich selbst).

**Urlaubsübersicht (Recht hr.uebersicht oder hr.verwalten)**

- `hr_tage_je_art(p, eintraege, jahr)`
- `hr_gleit_summen(k)` – Gleittage-Konto in der Übersicht: gewährt (mit Übertrag) und Rest – ohne Konto beides leer
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
- `hr_startseite(me)` – Startseite des Dashboards („Heute für Sie“, lib/startseite.php): was dieser Mitarbeiter in HR entscheiden kann – dieselben Zahlen wie am Reiter „Anträge“ …

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

_STAFL-Plattform · HR · Urlaub Gleittage-Konto (02.11.2026)_

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

**Gleittage-Konto des Mitarbeiters: Rest, gewährt, genommen und die Gewährungen**

- `zeigeGleitMein()`
- `artSetzen(art)`
- `vertretungFeld()`
- `vt2Zeigen(an)`
- `zeigeVertreten()` – Sie vertreten: laufende und kommende Anträge anderer, in denen man (zusätzliche) Vertretung ist

**Jahresplanung: Stand der Vorplanung des nächsten Jahres (Mitarbeiter)**

- `zeigePlanungMein()`

**Mein Jahr: Mini-Kalender aller eigenen Abwesenheiten**

- `zeigeMiniKalender()`

**Korrektur melden (an die Personalstelle)**

- `korrekturDialog(v)`
- `zeigeKorrekturen()`
- `antragTage()` – Arbeitstage des Antrags (Vorschau im Browser; verbindlich rechnet der Server)
- `antragPruefen()`

**Vorplanung (Inhaber 10.11.2026): mehrere Zeiträume des nächsten Jahres auf einmal**

- `vpBereit()`
- `vpSchalten(an)`
- `vpZeile(von, bis, vertretung)`
- `vpNummern()`
- `vpKnopf()`
- `vpPruefen(sofort)`
- `vpPruefenJetzt()`
- `vpStatus(li, z)`
- `vpRegelZeilen(st)` – Regeln der Vorplanung als kurze Zeilen (Stand beim Mitarbeiter und in der Vorplanung)
- `vpStand(st, v)`
- `vpSenden()`
- `frage(titel, text, ja)` – Rückfrage im eigenen Fenster: Escape oder „Abbrechen“ = nein, der Fokus liegt auf „Abbrechen“

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
- `mailFeld()` – Unentschuldigt (F): Haken „E-Mail an den Mitarbeiter“ (Standard an); beim Ändern eines F-Eintrags keine neue Mail
- `nachEintrag()`

**Urlaubsübersicht (hr.uebersicht oder Personalstelle): nur Summen**

- `ladeUebersicht()`
- `zeigeUebersicht()`

**Gleittage gewähren (Personalstelle)**

- `gleitOeffnen(person)`
- `gleitZeigen()`
- `gleitSpeichern(body)`

**Export**

- `zeigeExport()`

**Jahresplanung (nur Personalstelle; gesammelt genehmigen zusätzlich mit „Urlaub genehmigen“)**

- `ladePlanung()`
- `zeigePlanung()`
- `zeigeZeitleiste()` – Zeitleiste: je Mitarbeiter (nach Abteilung) eine Jahresleiste; Balken = Anträge, Sperren und Monate als Hintergrund
- `zeigePlanungListe()`
- `planungAktion(was, knopf)`

**Urlaubsregeln (Text der Personalstelle, Verwaltung → Urlaub)**

- `zeigeRegeln(text)`

**Hinweis „Resturlaub verfällt bald“**

- `verfallHinweis()`

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

- `planungFelder()` – Jahresplanung (03.11.2026): Mitarbeiter planen bis zum Stichtag einen Anteil ihres Urlaubs des nächsten Jahres vor; Hinweis in der Urlaubsverwaltung ab dem …
- `renderUrlaub()`

**Verwaltung → Urlaub: E-Mails (Server: module/hr/mail.php)**

- `mailKarte()`
- `mailNeu(m)`

**Importzentrale**

**Importzentrale: Leser „Abwesenheiten aus der Zeiterfassung“ (Abwesenheitsbericht)**

- `abteilungenAusAngaben()` – Für Stammdaten → Abteilungen (admin-verwaltung.js): Abteilungen aus den Mitarbeiterangaben (Reihenfolge wie im Urlaubsplan) und Anzahl der Mitarbeiter je …
- `abteilungZahlen()`

## `tests/e2e/test_hr.py`

_HR · Urlaubsverwaltung (Modul hr, Oberfläche hr.intern unter /module/hr/)._

- `check(n, c, i)`
- `montag(jahr, monat, woche)` – Montag der n-ten vollen Woche eines Monats (ohne Feiertage im Februar/August).
- `iso(d)`
- `dokument(name)` – Gespeichertes Dokument lesen (Dateien: ohne Schutzzeile).
- `hr(uid, **werte)`
- `_call_mit_bestaetigung(action, data, raw)`
- `ostern(j)` – ── Sperren aus den Urlaubsregeln und Text der Urlaubsregeln (Inhaber 03.11.2026) ──
- `regel_sperren(j, schliess)`
- `person_zeile(v, n)`
- `urlaub(d1, d2)`
- `zimp(cl, uebernehmen, stand)`
- `mail_html(m_)`
- `freie_wochen(ab, wochen, *clients)` – Erster Montag ab „ab“, an dem die Personen der Clients in den nächsten Wochen nichts eingetragen haben.
- `neue_offen(vorher)`
- `anmelden(user, pw, ip, breite, verfall_hinweis)`
- `zeit(cl, uebernehmen, stand, **opt)`
- `plan_setzen(**w)`
- `zr_setzen(i, von, bis)`
- `anmelden_handy(user, pw, ip, hoehe)` – ── Handy (Prüfung 10.11.2026): echte Mobil-Simulation (390 px, Touch, mobiles Ansichtsfenster, 3-fache Pixeldichte) – im Browser (Höhe 664 mit Leisten) und …

## `tests/e2e/test_hr_uebersicht.py`

_HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht, Personalstelle hr.verwalten sieht sie auch)._

- `check(n, c, i)`
- `montag(jahr, monat, woche)`
- `iso(d)`
- `hr(uid, **werte)`
- `eintrag(person, art, von, bis, notiz)` – ── Daten (Personalstelle trägt ein, Lena beantragt) ──
- `bu(arbeitstage, krank)` – Betriebsurlaub 24./31.12.
- `gewaehren(tage, grund, person, wer)`
- `anmelden(user, pw, ip, breite)`
