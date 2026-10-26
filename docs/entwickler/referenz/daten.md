# Referenz: Speicher-Dokumente

<!-- ERZEUGT von `python3 werkzeuge/doku.py erzeugen` – nicht von Hand ändern. Quelle: regeln/datenverantwortung.toml. Die CI prüft, dass diese Datei zum Code passt. -->

Gelesen und geschrieben über `app/api/storage.php` (`store_read`, `store_write`, `with_lock`). Eigentümer und erlaubte Querzugriffe prüft `werkzeuge/regeln.py` (GR-101). Aufbau der wichtigsten Dokumente: [05-daten.md](../05-daten.md).

| Dokument | Eigentümer | Schutz | Leser | Schreiber | Beschreibung |
| --- | --- | --- | --- | --- | --- |
| `abmelde-schluessel` | Angebot | geheim | – | – | Schlüssel für Abmelde-Links in Kunden-E-Mails |
| `angebot` | Angebot | oeffentlich | bestand, plattform | – | Veröffentlichtes Wochenangebot; öffentlich nur gefiltert über offer_resolve (GR-001, GR-002) – Historie: Jede Veröffentlichung legt eine Version an (versionen/*) und den Preisverlauf (historie/*) |
| `angebote` | Angebot | vertraulich | crm | – | Kundenangebote mit Kundenpreisen (variants), Sichtbarkeit und Sonderpreisen |
| `anwesenheit` | Angebot | intern | – | – | Wer bearbeitet gerade den Entwurf (gemeinsames Bearbeiten) |
| `bestellung` | Angebot | intern | – | plattform | Einstellungen der Bestellfunktion (an/aus, Empfänger) |
| `bestellungen` | Angebot | vertraulich | einkauf, plattform | – | Bestellwünsche der Kunden (Bestell-API v1) mit Verlauf – Historie: Positionen, Preise, Firma und Angebotswoche werden beim Absenden als Schnappschuss gespeichert |
| `einzelangebote` | Angebot | vertraulich | – | – | Einzelangebote für genau einen Kunden (E-JJJJ-0001) |
| `entwurf` | Angebot | intern | – | – | Bearbeitungsstand des nächsten Wochenangebots (gemeinsames Bearbeiten mit Revisionen) |
| `entwurf-stand` | Angebot | intern | – | – | Revisionszähler des Entwurfs |
| `fracht` | Angebot | intern | – | – | Frachtregel (Staffeln, Hinweis unter dem Angebot) |
| `historie/*` | Angebot | intern | bestand | – | Preisverlauf je Kalenderwoche – Historie: Schnappschuss je Woche, ohne Kunden- und Einkaufspreise |
| `historie_geloescht` | Angebot | intern | bestand | – | Bewusst gelöschte Wochen des Preisverlaufs |
| `mailvorlage` | Angebot | intern | – | plattform | Signatur der Kunden-E-Mails |
| `merklisten` | Angebot | vertraulich | – | verwaltung | Merklisten angemeldeter Kunden (geräteübergreifend) |
| `versionen/*` | Angebot | intern | bestand | – | Frühere veröffentlichte Angebote (unveränderliche Schnappschüsse) – Historie: Schnappschuss je Veröffentlichung; Anzahl begrenzt (keep_versions) |
| `bestand` | Bestand | vertraulich | angebot, einkauf | – | Bestandsliste: Partien, Mengen, MHD, Einkaufspreise, erwartete Zugänge (nie öffentlich, GR-001) |
| `crm-aktivitaeten` | CRM | vertraulich | – | – | Aktivitätenverlauf (Telefonat, E-Mail, Besuch, Muster, Angebot, Bestellung, Notiz) je Kunde – Historie: Firma und Kundennummer werden beim Erfassen als Schnappschuss gespeichert (GR-106); höchstens 50 000 Einträge, älteste fallen weg |
| `crm-interessenten` | CRM | vertraulich | – | – | Interessenten ohne Kundennummer mit eigenen Adress- und Kontaktangaben (Kunden selbst pflegt die Verwaltung) |
| `crm-kunden` | CRM | vertraulich | – | – | Kundenblätter des CRM je Kunde (Kunden-ID der Verwaltung) bzw. Interessent: Ansprechpartner, Segment, Phase, Anruf-Rhythmus und -Status, Potenzial, nächster Schritt, Wiedervorlage, Notiz |
| `einkauf-meldungen` | Einkauf | intern | – | – | Versandte Meldungen an den Einkauf (Fehlmengen) |
| `hr-abwesenheiten` | HR | vertraulich | – | – | Urlaubsanträge und Abwesenheiten (Urlaub, Krank, Gleittag, freie Tage) mit Status und Entscheidung; Art und Notiz nur für die Person selbst und die Personalstelle (hr.verwalten); wer Urlaub genehmigt (hr.genehmigen), sieht nur offene Urlaubsanträge mit Konto; die Urlaubsübersicht (hr.uebersicht) zeigt nur Summen je Mitarbeiter und Jahr, auch Krank- und Gleittage als Anzahl, nie Zeiträume oder Notizen; Kollegen sehen nur „abwesend“ – Historie: Einträge werden nie gelöscht: Ablehnen, Zurückziehen und Stornieren ändern nur den Status (mit Zeitpunkt und Person) |
| `hr-einstellungen` | HR | intern | – | – | Urlaubssperren, Ferienzeiträume und Verfallstag des Resturlaubs (uebertragBis, MM-TT; fehlt: 31.03.) der Urlaubsverwaltung |
| `hr-personal` | HR | vertraulich | – | – | Mitarbeiter der Urlaubsverwaltung: Name, Abteilung, Reihenfolge, Arbeitstage, Urlaubsanspruch und Übertrag je Jahr, Verknüpfung zum Mitarbeiterkonto |
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
| `laendersperre` | Plattformkern | intern | – | – | Statistik der Länder-/IP-Sperre |
| `logins` | Plattformkern | intern | – | – | Fehlversuche und Sperren bei der Anmeldung |
| `mail-schluessel*` | Plattformkern | geheim | – | – | Schlüssel für das Postfach-Passwort – nie in Sicherungen (Konstante MAIL_KEY_STORE) |
| `mailkonto` | Plattformkern | geheim | – | – | Postfach-Zugang (Passwort verschlüsselt) |
| `mailversand` | Plattformkern | vertraulich | – | angebot, einkauf | Versandaufträge und Versandprotokoll aller E-Mails |
| `module` | Plattformkern | intern | dashboard, verwaltung | – | Laufzeitzustand je Oberfläche: Wartung (aktiv oder geplant, Grund, Hinweis, bis), Freigabe aus der Modulverwaltung (innerhalb des Entwicklungsstands im Code), Tester und Verlauf der Änderungen (lib/module.php) – Historie: Verlauf der letzten 100 Änderungen (wer, wann, Bereich, alt, neu, Grund, Beginn, bis) zusätzlich zum Protokoll |
| `nutzer` | Plattformkern | geheim | angebot, hr, marketing | hr | Mitarbeiterzugänge, Rollen, Rechte-Ausnahmen, Zwei-Faktor, Passkeys, vertraute Geräte |
| `oidc-abmeldungen` | Plattformkern | intern | – | – | Beendete Sitzungen der zentralen Anmeldung (Keycloak-Sitzung bzw. Mitarbeiter → Zeitpunkt, höchstens 11 Stunden): weiter erst nach erneuter Anmeldung bei Keycloak |
| `protokoll/*` | Plattformkern | vertraulich | – | – | Änderungsprotokoll je Monat (audit) – Historie: Nur anhängen; Einträge werden nicht geändert. Aufbewahrung: laufender Monat und 6 Monate davor – ältere Monatsdokumente löscht audit() (PROTOKOLL_MONATE, lib/protokoll.php) |
| `rechte` | Plattformkern | intern | – | – | Rechte der Standardrollen (Katalog PERMS und Modulzugang in lib/rechte.php), „bekannt“ = Katalog beim Speichern |
| `rollen` | Plattformkern | intern | – | – | Eigene Rollen (Name, Beschreibung, Rechte) und Namen der Standardrollen (lib/rechte.php) |
| `sicherheit` | Plattformkern | intern | – | – | Sicherheitseinstellungen (Zwei-Faktor-Pflicht, IP-/Ländersperre, Passwortbestätigungen) |
| `sicherung` | Plattformkern | intern | – | – | Status der Datensicherung (Datei neben der Datenbank) |
| `sitzungen` | Plattformkern | geheim | – | – | Sitzungsregister der Mitarbeiter |
| `sperrliste` | Plattformkern | intern | – | – | Gesperrte Adressen |
| `testpostfach` | Plattformkern | vertraulich | – | angebot | Abgefangene E-Mails der Testumgebung (WA_TESTUMGEBUNG=1) |
| `verkehr` | Plattformkern | intern | – | – | Live-Verkehr (Ringpuffer) der Schutzzentrale |
| `wartung` | Plattformkern | intern | – | – | Heutiger globaler Wartungsmodus der Angebotsseite (nur Kundenfunktionen) |
| `anmeldeorte` | Verwaltung | vertraulich | – | – | Anmeldeorte der Kunden für die Auswertung (90 Tage, ohne IP) |
| `kunden` | Verwaltung | vertraulich | angebot, crm | angebot, plattform | Kundenstammdaten und Kundenzugänge des Portals (Passwort nur als Hash, GR-003) |
| `kundengruppen*` | Verwaltung | intern | angebot, crm | – | Kundengruppen (GRUPPEN_LISTEN in lib/kunden.php) |
| `kundensitzungen` | Verwaltung | geheim | – | angebot | Sitzungen der Kunden im Portal; Ziel: zentraler Identitätsdienst (Phase 6) |
| `stammdaten` | Verwaltung | intern | angebot, bestand | – | Artikelstammdaten (Bezeichnung, Fleischart, Herkunft, Zustand, VK-Gruppe, GTIN) |
| `vertreter*` | Verwaltung | vertraulich | crm | – | Vertreter mit Kontaktdaten |
| `vkgruppen*` | Verwaltung | intern | angebot, bestand | – | VK-Gruppen der Artikel |

`*` Name wird im Code berechnet (z. B. je Monat oder je Angebot).
