# Referenz: Speicher-Dokumente

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: regeln/datenverantwortung.toml. Die CI prüft, dass diese Datei zum Code passt. -->

Gelesen und geschrieben über `app/api/storage.php` (`store_read`, `store_write`, `with_lock`). Eigentümer und erlaubte Querzugriffe prüft `werkzeuge/regeln.py` (GR-101). Aufbau der wichtigsten Dokumente: [05-daten.md](../05-daten.md).

| Dokument | Eigentümer | Schutz | Leser | Schreiber | Beschreibung |
| --- | --- | --- | --- | --- | --- |
| `abmelde-schluessel` | Angebot | geheim | – | – | Schlüssel für Abmelde-Links in Kunden-E-Mails |
| `angebot` | Angebot | oeffentlich | bestand, plattform | – | Veröffentlichtes Wochenangebot; öffentlich nur gefiltert über offer_resolve (GR-001, GR-002) – Historie: Jede Veröffentlichung legt eine Version an (versionen/*) und den Preisverlauf (historie/*) |
| `angebote` | Angebot | vertraulich | crm | – | Kundenangebote mit Kundenpreisen (variants), Sichtbarkeit und Sonderpreisen |
| `anwesenheit` | Angebot | intern | – | – | Wer bearbeitet gerade den Entwurf (gemeinsames Bearbeiten) |
| `bestellung` | Angebot | intern | – | plattform | Einstellungen der Bestellfunktion (an/aus, Kopie an den Kunden); ab Trennstufe 2 nur die Anzahl der Empfänger – die Adressen stehen in bestellung-empfaenger |
| `bestellung-empfaenger` | Angebot | intern | plattform | plattform | Empfänger der Bestellwünsche (ab Trennstufe 2, ADR-007 Stufe 2b): nur innen – der Postausgang verschickt Bestellwünsche nur an diese Adressen |
| `bestellungen` | Angebot | vertraulich | einkauf, plattform | – | Bestellwünsche der Kunden (Bestell-API v1) mit Verlauf – Historie: Positionen, Preise, Firma und Angebotswoche werden beim Absenden als Schnappschuss gespeichert |
| `einzelangebote` | Angebot | vertraulich | crm | crm | Einzelangebote für genau einen Kunden (E-JJJJ-0001) |
| `entwurf` | Angebot | intern | – | – | Bearbeitungsstand des nächsten Wochenangebots (gemeinsames Bearbeiten mit Revisionen) |
| `entwurf-stand` | Angebot | intern | – | – | Revisionszähler des Entwurfs |
| `fracht` | Angebot | intern | – | – | Frachtregel (Staffeln, Hinweis unter dem Angebot) |
| `historie/*` | Angebot | intern | bestand | – | Preisverlauf je Kalenderwoche – Historie: Schnappschuss je Woche, ohne Kunden- und Einkaufspreise |
| `historie_geloescht` | Angebot | intern | bestand | – | Bewusst gelöschte Wochen des Preisverlaufs |
| `mailvorlage` | Angebot | intern | – | plattform | Signatur der Kunden-E-Mails |
| `merklisten` | Angebot | vertraulich | – | verwaltung | Merklisten angemeldeter Kunden (geräteübergreifend) |
| `versionen/*` | Angebot | intern | bestand | – | Frühere veröffentlichte Angebote (unveränderliche Schnappschüsse) – Historie: Schnappschuss je Veröffentlichung; Anzahl begrenzt (keep_versions) |
| `artikelauszug` | Bestand | oeffentlich | angebot | – | Auszug aus Bestand und Stammdaten für die Kundenseite (ab Trennstufe 2, ADR-007 Stufe 2b): Artikelnummern mit Lagerbestand ohne Mengen, Fleischart/Herkunft/Zustand je Artikel – nie Mengen, Partien, MHD oder Einkaufspreise (GR-001, GR-008) – Historie: Wird bei jeder Änderung von Bestand oder Stammdaten neu erzeugt (lib/bestand.php artikelauszug_aktualisieren) |
| `bestand` | Bestand | vertraulich | angebot, einkauf, crm | – | Bestandsliste: Partien, Mengen, MHD, Einkaufspreise, erwartete Zugänge (nie öffentlich, GR-001) |
| `bestand-verlauf*` | Bestand | vertraulich | controlling | – | Bestandsverlauf – Verzeichnis: je Tag die Summen (kg eingelagert, erwartete Zugänge, Lagerwert zum EK, Artikel, Partien) und die Herkunft (Datei, wer, wann) – Historie: Tagesstand beim Hochladen der Bestandsliste (Schnappschuss); erneutes Hochladen für denselben Tag ersetzt ihn, frühere Tage bleiben |
| `bestand-verlauf/**` | Bestand | vertraulich | controlling | – | Bestandsverlauf je Tag (JJJJ-MM-TT): je Artikel kg eingelagert, erwartete Zugänge, Lagerwert zum EK, kg mit EK, Partien und Bezeichnung – Historie: Schnappschuss des Tages; spätere Stammdatenänderungen ändern ihn nicht (GR-106) |
| `controlling-arbeitszeit*` | Controlling | vertraulich | – | – | Arbeitszeit aus dem Zeitbericht der Zeiterfassung – Verzeichnis: Mitarbeiter (Schlüssel, Name, Personalnummer, Abteilung), gespeicherte Jahre mit Zeitraum, Importverlauf (Zeitraum, Datei, wer, wann, Tage neu/geändert/entfallen); Personaldaten – Historie: Importierte Tage bleiben, wie sie im Zeitbericht standen; ein neuer Import ersetzt nur den Zeitraum seiner Datei |
| `controlling-arbeitszeit/**` | Controlling | vertraulich | – | – | Arbeitszeit je Jahr (JJJJ): je Mitarbeiter und Tag Soll, Ist, Abwesenheit (nur Stunden, ohne Grund), Pause, Saldo laut Zeiterfassung, Stempel (Kommen/Gehen) und erkannte Stempelfehler; Personaldaten |
| `controlling-umsatzdaten*` | Controlling | vertraulich | crm | – | Umsatzdaten der Warenwirtschaft – Verzeichnis: Monate mit Prüfsumme und Kennzahlen, Kunden- und Artikelnummern mit Umsatz, Importverlauf (Zeitraum, wer, wann, Monate neu/geändert/entfallen) – Historie: Importierte Umsätze bleiben, wie sie in der Datei standen; Zuordnung zu Vertreter, Kundengruppe und Artikelgruppe erst in der Auswertung nach heutigen Stammdaten |
| `controlling-umsatzdaten/**` | Controlling | vertraulich | crm | – | Umsatzdaten je Monat (JJJJ-MM): Kunde, Artikel und Tag mit Kolli, Menge, Umsatz, EK-Wert, Umsatz mit EK, Positionen, berechnet/ohne Berechnung |
| `controlling-umsatzteile/**` | Controlling | vertraulich | – | – | Zwischenablage eines Umsatzdaten-Imports (je Importlauf und Monat), gelöscht mit der Übernahme bzw. nach einem Tag |
| `crm-aktivitaeten` | CRM | vertraulich | – | – | Aktivitätenverlauf (Telefonat, E-Mail, Besuch, Muster, Angebot, Bestellung, Notiz) je Kunde – Historie: Firma und Kundennummer werden beim Erfassen als Schnappschuss gespeichert (GR-106); höchstens 50 000 Einträge, älteste fallen weg |
| `crm-interessenten` | CRM | vertraulich | – | – | Interessenten ohne Kundennummer mit eigenen Adress- und Kontaktangaben (Kunden selbst pflegt die Verwaltung) |
| `crm-kunden` | CRM | vertraulich | – | – | Kundenblätter des CRM je Kunde (Kunden-ID der Verwaltung) bzw. Interessent: Ansprechpartner, Segment, Phase, Anruf-Rhythmus und -Status, Potenzial, nächster Schritt, Wiedervorlage, Notiz |
| `einkauf-meldungen` | Einkauf | intern | – | – | Versandte Meldungen an den Einkauf (Fehlmengen) |
| `hr-abwesenheiten` | HR | vertraulich | – | – | Urlaubsanträge und Abwesenheiten (Urlaub, Krank, Gleittag, freie Tage) mit Status und Entscheidung; Art und Notiz nur für die Person selbst und die Personalstelle (hr.verwalten); wer Urlaub genehmigt (hr.genehmigen), sieht nur offene Urlaubsanträge mit Konto; die Urlaubsübersicht (hr.uebersicht) zeigt nur Summen je Mitarbeiter und Jahr, auch Krank- und Gleittage als Anzahl, nie Zeiträume oder Notizen; Kollegen sehen nur „abwesend“ – Historie: Einträge werden nie gelöscht: Ablehnen, Zurückziehen und Stornieren ändern nur den Status (mit Zeitpunkt und Person) |
| `hr-einstellungen` | HR | intern | – | – | Urlaubssperren, Ferienzeiträume, Verfallstag des Resturlaubs (uebertragBis, MM-TT; fehlt: 31.03.) und Schalter „Urlaubsanträge über die Plattform“ (antraege; fehlt: an) der Urlaubsverwaltung |
| `hr-korrekturen` | HR | vertraulich | – | – | Korrekturmeldungen der Mitarbeiter zu ihren Einträgen bzw. ihrem Urlaubskonto (Text, optional Zeitraum und Eintrag) mit Status und Antwort der Personalstelle; sichtbar nur für die Person selbst und die Personalstelle (hr.verwalten), Protokoll ohne Text – Historie: Meldungen werden nie gelöscht: Erledigen ändert nur den Status (mit Zeitpunkt, Person und Antwort) |
| `hr-personal` | HR | vertraulich | – | – | Mitarbeiter der Urlaubsverwaltung: Name, Abteilung, Reihenfolge, Arbeitstage, Urlaubsanspruch und Übertrag je Jahr, Verknüpfung zum Mitarbeiterkonto |
| `leergut-abschreibungen*` | Leergut | intern | – | – | Dachser-Abschreibungen für nicht getauschtes Leergut unserer Kunden: Empfänger, Sendung, Mengen, Status (offen, widersprochen, berechnet, ausgeglichen, nicht zu beachten), WinAB-Auftrag, Notiz, Verlauf |
| `leergut-abstimmungen*` | Leergut | intern | – | – | Auszüge der Partner zum Stichtag: Saldo laut Partner, Eingang, Frist, Status (offen, bestätigt, widersprochen, zur Info), Quelle, Notiz, Verlauf – Historie: Unser Saldo zum Stichtag als Schnappschuss beim Erfassen (GR-106); Statuswechsel im Verlauf mit Name |
| `leergut-bewegungen` | Leergut | intern | – | – | Leergut-Bewegungen je Partner: Datum, Art, Abgang/Zugang je Lademittel, Beleg, Text, Herkunft (von Hand/Datenpaket) – Historie: Nie geändert oder gelöscht; Fehler werden storniert (mit Grund, Name und Zeitpunkt) und neu gebucht |
| `leergut-inventur*` | Leergut | intern | – | – | Eigener Leergutbestand zum Stichtag (Positionen wie Lager gefüllt, Kisten unbenutzt, Abholer) für die Bilanz |
| `leergut-stamm` | Leergut | intern | – | – | Leergut: Lademittel mit Wert je Stück und Partner (Art, Firma, Konto-Nr. beim Partner, Frist, E-Mail für die Abstimmung, Lieferanten hinter einem Sammelkonto, genutzte Lademittel, aktiv) |
| `marketing-beitraege` | Marketing | intern | – | – | Redaktionsplan: Beiträge mit Marke, Kanälen, Format, Content-Säule, Kampagne, Verantwortlichen, Terminen, Text, Hashtags, Skript, Checkliste, Material-Links, KI-Kennzeichen, Status mit Freigabe, Veröffentlichungs-Links und Kennzahlen je Kanal, Kommentare – Historie: Verlauf und Kommentare mit Namen als Schnappschuss (GR-106), Freigabe mit Name und Zeitpunkt; höchstens 20 000 Beiträge |
| `marketing-einstellungen` | Marketing | intern | – | – | Marken, Kanäle (mit Zeichengrenze und Hashtag-Empfehlung), Formate und Content-Säulen des Redaktionsplans |
| `marketing-kampagnen` | Marketing | intern | – | – | Kampagnen mit Zeitraum, Ziel, Marke und Farbe (archivieren statt löschen) |
| `admin` | Plattformkern | geheim | – | – | Altformat des ersten Administratorzugangs (wird beim Lesen in „nutzer“ übernommen) |
| `anmeldenamen` | Plattformkern | intern | – | – | Vergebene Benutzernamen |
| `bedrohungsliste` | Plattformkern | intern | – | – | Externe Bedrohungsliste (Spamhaus DROP) mit Suchindex |
| `benachrichtigung-stand` | Plattformkern | intern | – | – | Bündelungsstand der Benachrichtigungen |
| `benachrichtigungen` | Plattformkern | intern | – | – | Einstellungen der Benachrichtigungen an Mitarbeiter |
| `datenleck` | Plattformkern | intern | – | – | Ergebnis der Datenleck-Prüfung von Passwörtern (ohne Passwort) |
| `deployment` | Plattformkern | intern | – | – | Status des Release-Einspielens (Datei neben der Datenbank) |
| `firewall` | Plattformkern | intern | – | – | Firewall-Einstellungen der Schutzzentrale |
| `fw_zaehler` | Plattformkern | intern | – | – | Zähler der Firewall |
| `integritaet` | Plattformkern | intern | – | – | Ergebnisse der Dateiprüfung |
| `kundenprotokoll/*` | Plattformkern | vertraulich | – | – | Protokoll der Kundenseite je Monat (ab Trennstufe 4, ADR-007 Stufe 2d): Anmeldungen, Bestellwünsche, Abmeldungen, Passwörter der Kunden – die Mitarbeiterseite zeigt es zusammen mit protokoll/* – Historie: Nur anhängen; Aufbewahrung wie protokoll/* (audit() löscht ältere Monate) |
| `laendersperre` | Plattformkern | intern | – | – | Statistik der Länder-/IP-Sperre |
| `logins` | Plattformkern | intern | – | – | Fehlversuche und Sperren bei der Anmeldung |
| `mail-schluessel*` | Plattformkern | geheim | – | – | Schlüssel für das Postfach-Passwort – nie in Sicherungen (Konstante MAIL_KEY_STORE) |
| `mailkonto` | Plattformkern | geheim | – | – | Postfach-Zugang (Passwort verschlüsselt) |
| `mailkonto-intern` | Plattformkern | geheim | – | – | Postfach-Zugang für interne E-Mails an Mitarbeiter, z. B. verwaltung@… (Passwort verschlüsselt; ohne Eintrag gilt mailkonto) |
| `mailversand` | Plattformkern | vertraulich | – | angebot, einkauf, bestand | Versandaufträge und Versandprotokoll aller E-Mails |
| `module` | Plattformkern | intern | dashboard, verwaltung | – | Laufzeitzustand je Oberfläche: Wartung (aktiv oder geplant, Grund, Hinweis, bis), Freigabe aus der Modulverwaltung (innerhalb des Entwicklungsstands im Code), Tester und Verlauf der Änderungen (lib/module.php) – Historie: Verlauf der letzten 100 Änderungen (wer, wann, Bereich, alt, neu, Grund, Beginn, bis) zusätzlich zum Protokoll |
| `nutzer` | Plattformkern | geheim | angebot, hr, marketing, qs | hr | Mitarbeiterzugänge, Rollen, Rechte-Ausnahmen, Zwei-Faktor, Passkeys, vertraute Geräte, Anzeige-Einstellungen (Design, Darstellung, Seitenleiste festgestellt, Favoriten der Startseite) |
| `oidc-abmeldungen` | Plattformkern | intern | – | – | Beendete Sitzungen der zentralen Anmeldung (Keycloak-Sitzung bzw. Mitarbeiter → Zeitpunkt, höchstens 11 Stunden): weiter erst nach erneuter Anmeldung bei Keycloak |
| `oidc-aktivitaet` | Plattformkern | intern | – | – | Letzte Aktivität je Anmeldung bei Keycloak (Keycloak-Sitzung → Zeitpunkt, höchstens 13 Stunden): Abmelden nach Inaktivität gilt über alle Adressen der Plattform |
| `oidc-geloescht` | Plattformkern | intern | – | – | Kennungen der Keycloak-Konten gelöschter Mitarbeiter → Zeitpunkt: verknüpfen nie mit einem neuen, gleich benannten Mitarbeiter (lib/oidc.php, konten.sh verwaist) |
| `postausgang` | Plattformkern | vertraulich | – | – | Postausgang von innen (ADR-007, lib/postausgang.php): Versandaufträge der Kundenseite – Bestellnummer, Benachrichtigungen, Abmeldehinweise mit Firma und E-Mail; nie Postfachdaten oder Mailinhalte – Historie: Kurzlebig: der Dienst postausgang entnimmt fällige Aufträge; höchstens 500 offen |
| `postausgang-stand` | Plattformkern | intern | – | – | Lebenszeichen des Dienstes postausgang und ob ein Postfach eingerichtet ist (die Kundenseite prüft damit die Bestellfunktion) |
| `protokoll/*` | Plattformkern | vertraulich | – | – | Änderungsprotokoll je Monat (audit); ab Trennstufe 4 nur noch Einträge der Mitarbeiterseite und des Postausgangs – Historie: Nur anhängen; Einträge werden nicht geändert. Aufbewahrung: laufender Monat und 6 Monate davor – ältere Monatsdokumente löscht audit() (PROTOKOLL_MONATE, lib/protokoll.php) |
| `rechte` | Plattformkern | intern | – | – | Rechte der Standardrollen (Katalog PERMS und Modulzugang in lib/rechte.php), „bekannt“ = Katalog beim Speichern |
| `rollen` | Plattformkern | intern | – | – | Eigene Rollen (Name, Beschreibung, Rechte) und Namen der Standardrollen (lib/rechte.php) |
| `sicherheit` | Plattformkern | intern | – | – | Sicherheitseinstellungen (Zwei-Faktor-Pflicht, IP-/Ländersperre, Passwortbestätigungen) |
| `sicherheit-bereitschaft` | Plattformkern | intern | – | – | Bereitschaft (Modul Sicherheit, lib/bereitschaft.php): Leitfaden für den Ernstfall mit Ansprechpartnern, im Notfall abgehakte Schritte, Probealarme mit Bestätigungen, Wochenbericht (an/aus, Wochentag, Versandverlauf) – Historie: Probealarme (letzte 20) und abgehakte Leitfäden je Notfall (letzte 20) als Schnappschuss; Leitfaden selbst ohne Versionen |
| `sicherheit-notfall` | Plattformkern | intern | – | – | Notfallmodus (Modul Sicherheit): Zustand, Grund, Kundenhinweis, Wirkung, gesicherte Sicherheits- und Firewall-Einstellungen, Verlauf |
| `sicherung` | Plattformkern | intern | – | – | Status der Datensicherung (Datei neben der Datenbank) |
| `sitzungen` | Plattformkern | geheim | – | – | Sitzungsregister der Mitarbeiter |
| `sperrliste` | Plattformkern | intern | – | – | Gesperrte Adressen |
| `testpostfach` | Plattformkern | vertraulich | – | angebot | Abgefangene E-Mails der Testumgebung (WA_TESTUMGEBUNG=1) |
| `verkehr` | Plattformkern | intern | – | – | Live-Verkehr (Ringpuffer) der Schutzzentrale |
| `wartung` | Plattformkern | intern | – | – | Heutiger globaler Wartungsmodus der Angebotsseite (nur Kundenfunktionen) |
| `qs-dokumente*` | Qualitätssicherung | intern | – | – | Gelenkte Dokumente (Nummer, Kapitel, Art, Titel, Ablage, Zuständig, Vertreter, eingezogen, ohne Änderung überprüft) mit Versionen: Nummer, Freigabedatum, Änderungen, Änderungsgrund, Status Entwurf/in Prüfung/geprüft/freigegeben/ersetzt/verworfen, erstellt/geprüft/freigegeben, Verlauf – Historie: Versionen werden nie gelöscht: eine neue Freigabe setzt die vorige auf „ersetzt“; Namen und Kürzel als Schnappschuss (GR-106) |
| `qs-handbuch*` | Qualitätssicherung | intern | – | – | QM-Handbuch: Abschnitte je Kapitel (Nummer, Prozessschritt, „Worauf kommt es an“, Verweise „Wo? Womit?“, IFS-Bezug, Zuständig, Vertreter, entfallen) mit Änderungen (Datum, was, Grund, von) – Historie: Abschnitte werden nicht gelöscht, sondern als entfallen markiert; jede Änderung mit Grund in der Änderungsliste |
| `qs-massnahmen*` | Qualitätssicherung | intern | – | – | Maßnahmen im Aufbau des IFS-Maßnahmenplans: Nummer je Jahr, Quelle (Audit, Prüfung, Reklamation …), Bezug, Kapitel, IFS-Anforderung und Bewertung, Feststellung, Korrektur (verantwortlich, Frist, erledigt, Nachweis), Ursache, Korrekturmaßnahme, Zuständig, Frist, umgesetzt am, Status, Freigabe durch den Auditor, Wirksamkeitsprüfung, Verlauf – Historie: Statuswechsel im Verlauf mit Name; Abschluss als wirksam mit Datum, Name und Notiz |
| `qs-nachweise*` | Qualitätssicherung | intern | – | – | Nachweise des Prüfplans: Prüfung, Datum, Ergebnis (in Ordnung/Abweichung), Bemerkung, durchgeführt von, verknüpfte Maßnahme, erfasst, Storno – Historie: Nie geändert oder gelöscht; Fehler werden storniert (mit Grund, Name und Zeitpunkt) und neu erfasst |
| `qs-pruefplan*` | Qualitätssicherung | intern | – | – | Prüfplan: Prüfungen je Kapitel mit Durchführung, Intervall, ab wann, Sollwert, Maßnahme bei Abweichung, Wo? Womit?, Zuständig, Vertreter, ausführende Mitarbeiter (Kennungen), aktiv, Verlauf |
| `qs-stamm` | Qualitätssicherung | intern | – | – | QM-System: Kapitel (Nummer, Titel, Zuständig, Vertreter, aktiv), Personen mit Kürzel, Name, Funktion, verknüpftem Mitarbeiter (Kennung) und aktiv, Einstellungen (Überprüfung der Dokumente nach Monaten) |
| `rewe-maerkte` | REWE | vertraulich | – | – | REWE-Märkte: Kd.-Nr. (WinAB), REWE-Marktnummer, Anschrift, Telefon, Ansprechpartner, Kaufbereitschaft, Dauerauftrag, Abfragetag, Hinweis; Zuständigkeit und Lieferweg mit „ab KW“-Historie – Historie: Zuständigkeit und Lieferweg werden nie überschrieben, sondern ab einer KW fortgeschrieben; Änderungen stehen mit Namen in rewe-verlauf |
| `rewe-stamm` | REWE | intern | – | – | REWE: Lieferwege (Zentrallager oder Direktbelieferung, Bestellschluss) und Artikel (Name, Einheit, WinAB-Artikelnummer) |
| `rewe-verlauf` | REWE | vertraulich | – | – | REWE-Marktakte: Notizen, Telefonate, Besuche, Reklamationen, Ware ohne Berechnung, Wiedervorlagen (erledigt mit Namen) und Änderungen (Kaufbereitschaft, Dauerauftrag, Zuweisung, Lieferweg) – Historie: Nur anfügen; Wiedervorlagen werden als erledigt markiert, nichts wird gelöscht |
| `rewe-wochen/*` | REWE | vertraulich | – | – | REWE-Wochenabfrage je ISO-Jahr: Antwort je Markt und KW (bestellt mit Mengen je Artikel, kein Bedarf, nicht erreicht, Pause), ohne Berechnung, Notiz, wer/wann, Herkunft; Wochenabschluss (exportiert, in WinAB erfasst) – Historie: Jede Antwort speichert Lieferweg und Zuständigkeit der KW als Schnappschuss (GR-106); Änderungen nach dem Export sind als Nachtrag gekennzeichnet |
| `angebotskategorien*` | Verwaltung | intern | angebot | – | Angebotskategorien: Abschnitte des Angebots mit zugeordneten VK-Gruppen in fester Reihenfolge |
| `anmeldeorte` | Verwaltung | vertraulich | – | – | Anmeldeorte der Kunden für die Auswertung (90 Tage, ohne IP) |
| `kunden` | Verwaltung | vertraulich | angebot, crm, rewe, controlling, leergut | angebot, plattform | Kundenzugänge des Portals (Passwort nur als Hash, GR-003); bis Trennstufe 2 auch alle Stammdaten, danach nur die Felder unter felder_kundenseite |
| `kundengruppen*` | Verwaltung | intern | angebot, crm, controlling | – | Kundengruppen (GRUPPEN_LISTEN in lib/kunden.php) |
| `kundensitzungen` | Verwaltung | geheim | – | angebot | Sitzungen der Kunden im Portal; Ziel: zentraler Identitätsdienst (Phase 6) |
| `kundenstamm` | Verwaltung | vertraulich | angebot, crm, rewe, controlling, plattform, leergut | – | Ab Trennstufe 2 (ADR-007 Stufe 2b): alle Kundenfelder außer den Portalfeldern – Anschrift, E-Mail, Telefon, Notiz, Vertreter, Daten der Warenwirtschaft |
| `lieferanten*` | Verwaltung | vertraulich | leergut | – | Lieferanten aus dem Lieferanten-Export der Warenwirtschaft (Adresse, Konto, Kondition, Umsätze, Versandart, GLN) |
| `stammdaten` | Verwaltung | intern | angebot, bestand, controlling | – | Artikelstammdaten (Bezeichnung, Fleischart, Herkunft, Zustand, VK-Gruppe, GTIN) |
| `versandarten*` | Verwaltung | intern | leergut | – | Versandarten der Warenwirtschaft (Kunden und Lieferanten verweisen darauf) |
| `vertreter*` | Verwaltung | vertraulich | crm, controlling | – | Vertreter mit Kontaktdaten |
| `vkgruppen*` | Verwaltung | intern | angebot, bestand, controlling | – | VK-Gruppen der Artikel |

`*` Name wird im Code berechnet (z. B. je Monat oder je Angebot).
