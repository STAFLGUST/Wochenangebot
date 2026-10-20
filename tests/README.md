# Automatische Tests

Alle Tests laufen gegen **Testkopien mit anonymisierten Testdaten** – nie gegen die Produktivseite oder echte Daten.

| Ebene | Aufruf | Inhalt |
| --- | --- | --- |
| Unit | `node tests/unit/bestand_parser.test.js` | Bestands-Parser der App gegen unabhängige Referenzauswertung |
| Unit | `node tests/unit/merge.test.js` | Abgleich beim gemeinsamen Bearbeiten des Entwurfs (feldweise, Kundenpreise, neue/gelöschte Artikel) |
| Versionsnummern | `python3 werkzeuge/asset_versionen.py` | Skripte/Stylesheets tragen die Prüfsumme ihres Inhalts (sonst laden Browser alte Kopien) |
| Ende-zu-Ende | `python3 tests/run_e2e.py [gruppe …]` | rund 45 Gruppen, über 1.100 Prüfungen im echten Browser gegen frische PHP-Testserver; 4 Gruppen parallel mit eigenen Ports (`WA_JOBS`, zur Fehlersuche `WA_JOBS=1`), volle Ausgabe je Gruppe in `tests/.arbeit/test-<gruppe>.log` |
| App | `cd mobile && npm ci && npm run pruefen` | TypeScript, Unit-Tests der App-Logik (Jest, u. a. gleiche Merklisten-Schlüssel wie die Website, Fracht wie der Server, Statusübergänge wie `orders.php`), iOS- und Android-Bundle |
| Betrieb | `sh tests/deploy/test_sichern.sh`, `sh tests/deploy/test_freigabe.sh`, `sh tests/deploy/test_release_pruefen.sh` | Datensicherung; Release-Modus mit Healthcheck und automatischem Rückfall; Prüfungen des Release-Laufs (Freigabepflicht, aktueller Stand, CI) |

Voraussetzungen lokal: PHP 8.3, Node.js, Python 3.12, `pip install -r tests/requirements.txt`, `python -m playwright install chromium`.
In GitHub laufen alle Ebenen automatisch bei jedem Pull Request und jedem Commit auf `main` (`.github/workflows/ci.yml`).

## Testdaten

Neue Gruppe `stock_overview`: exakte aktuelle KW/Vorwoche, Bestands- und Zugangssummen/fehlende
Historie, Bestand und mehrere erwartete Lieferungen, fehlendes ETA, Rechte, Validierung,
CSV/Druck, Desktop und 390 px in hell/dunkel. Synthetische Daten: `fixtures/bestand/overview.json`.
Zusätzliche Unit-Tests: `node tests/unit/stock_prices.test.js` und `php tests/unit/stock_prices.php`
(ISO-Jahreswechsel, Berlin-Zeit, fehlende/gelöschte Wochen, Preisbasis/Mehrdeutigkeit).
Der Parser-Test prüft auch „erfasst“ in J und Ankunft in M sowie reine Zugangsdateien.

Windows: Der Teststarter beendet PHP-Prozesse plattformgerecht und erzeugt frische SQLite-Testdaten
direkt mit dem vorhandenen Schema. Dies prüft **nicht** die Linux-Produktionsmigration (weiterhin
unverändert in Linux/CI). Einige ältere Gruppen benötigen `fcntl`, Unix-Prozessbefehle oder
Linux-Dateirechte; deshalb ist die vollständige CI unter Linux weiterhin erforderlich.

`tests/fixtures/` enthält nur anonymisierte Daten (Erzeugung: `werkzeuge/testdaten_erzeugen.py`):
Verkaufspreise je Artikel mit festem Faktor verändert, Bestandsmengen und Einkaufspreise erfunden, Partie- und
Gruppennummern ersetzt. Erwartungswerte in den Tests werden aus diesen Daten berechnet (`tests/e2e/testdaten.py`),
nicht fest eingetragen. **Echte Angebots-, Bestands- oder Nutzerdaten gehören nie ins Repository.**

## Gruppen und Aussagekraft (Stand 17.10.2026)

| Gruppe | Prüfungen | Schwerpunkt |
| --- | --- | --- |
| sys | 52 | Ersteinrichtung, Editor, Import, Veröffentlichen, Versionen, Passwort |
| frontend | 62 | öffentliche Seite (Tabellenansicht): Filter (Aufklappmenüs: nur eines offen, Escape, Klick daneben), Suche, Sortierung, CSV, Druck, keine internen Daten |
| design | 21 | Gestaltung „Klar“: Schriften lokal (keine fremden Server), Kopf mit Kürzel, Filterleiste/Seitenleiste je Breite, Merkliste-Spalte ab 1280 px, dunkles Design, kein seitliches Scrollen |
| hist | 35 | Preisverlauf, Import alter Listen, Datendialog |
| users | 48 | Rollen, Rechte serverseitig, Protokoll, Sperren |
| auth_hardening | 38 | direkte HTTP-Regressionen für Faktorwechsel, Sitzungswiderruf und Kontosperre |
| security | 41 | 2FA, Wiederherstellungscodes, Sitzungen, IP-Freigabe, CSP |
| geo, geo_ip | 42 + 8 | Ländersperre, Selbstaussperr-Schutz, IP-Suche |
| stock | 37 | Bestandsimport, MHD-Regeln, keine Mengen öffentlich |
| master | 29 | Stammdaten, Bezeichnungsregeln |
| editor_aux | 21 | Vorwoche, Bestand im Editor |
| revert | 16 | einzelne Änderung mit Bestätigung zurücknehmen |
| sidenav | 12 | Navigation, Rechte je Rolle |
| angebote | 38 | Kundenangebote: eigene Preise, Ausblenden, Übernahme, Verwaltung, Rechte, keine Kundenpreise öffentlich |
| kunden | 125 | Kundenstammdaten, Freischaltung, Kunden-Login mit Pflicht-Passwortwechsel, Sperre, Sitzungsende, kein Zugriff auf den Eingabebereich, Merkliste je Kunde (geräteübergreifend, Übernahme der Browser-Merkliste), Oberfläche |
| testumgebung | 17 | Testumgebung (`WA_TESTUMGEBUNG=1`): Kennzeichen, E-Mails und Bestellwünsche nur ins Testpostfach, Rechte, Oberfläche |
| restposten | 53 | Sonderposten (Sonderpreis je Angebot, statt-Preis, automatisch ausgeblendet ohne Bestand), Ausblenden im Wochenangebot, rotes Kein-Bestand-Zeichen, Kurzes-MHD-Liste, Sonderposten-Mail nur an Kunden des jeweiligen Angebots, Angebotsseite |
| gemeinsam | 34 | Mehrere Bearbeiter gleichzeitig: Revisionen, 409 mit Namen, Anwesenheit, Hintergrundabfragen verlängern keine Sitzung, Abgleich in der Oberfläche, angefangene Eingaben bleiben, Veröffentlichen mit Konflikt |
| wartung | 25 | Wartungsmodus (Rechte, Sperre der Kundenfunktionen, Mitarbeiter arbeiten weiter, Abmeldelinks frei, Protokoll, Oberfläche) und erweiterte Übersicht |
| auswertung | 44 | Auswertung: Ortsdaten laden (Test-Quelle, nur Administrator, Fehlerfall), Anmeldeort je Kunden-Anmeldung (IPv4, IPv6, privat, Gerätetyp), keine IP gespeichert, Zeitraum, Löschen nach 90 Tagen und mit dem Kunden, Rechte, Karte/Punkte/Hinweisfeld/Filter/Liste/Ziehen/Zoom, 390 px |
| rechte | 47 | Nutzerrechte: Standards wie bisher, Ausnahmen je Nutzer (erlauben/verbieten, verboten hat Vorrang), Voraussetzungen, Durchsetzung auf dem Server, Passwortbestätigung nur für Berechtigte, Administratorrechte nicht vergebbar, Protokoll, Rechte-Tabelle und Nutzer-Dialog, Sichtbarkeit für Leser und Bearbeiter, 390 px |
| angebotsliste | 49 | Angebotsansicht wie die Druckliste: Umschalter Angebots-/Listenansicht, Abschnitte, immer drei gleich hohe Blöcke über die volle Breite (auch 1024 px; Handy 1), Gruppenköpfe einzeilig, Nummern schwarz und bündig, Preise rechtsbündig, „Fleischmeister“ nicht doppelt, Hinweis (Bildschirm, Liste, Druck), Logo, Details, Merkliste, Suche, Sortierung, Tabelle/Karten per Link; Export A4 quer (PDF quer, Seitenzahl = geplante Seiten), großes Angebot ohne Überlauf, 390 px, dunkel |
| versand | 11 | Wochenangebot senden: Knopf „An Kunden senden“ (nur Berechtigte), Hinweis direkt nach dem Veröffentlichen, Versand der neuen Woche |
| sicherheit_it | 52 | Sicherheit für IT-Administratoren: Verlauf und auffällige Adressen, Konfigurationsprüfung, Diagnosen (beschädigter Datensatz erkannt, Mailanmeldung ohne Versand, nur lesend), CSV-Export (Formeln entschärft, keine Hashes, protokolliert), Rechte, Browser-Prüfungen, Oberfläche |
| einkauf | 49 | Einkauf: Fehlmenge = offene Bestellmengen − Bestand (stornierte zählen nicht), ohne Bestandsliste kein Ergebnis, Ansehen für alle / Kundennamen und Melden ab Bearbeiter, E-Mail an „Einkaufsbedarf“ mit Hinweis (escaped), Status gemeldet / mehr als gemeldet, Oberfläche Desktop und Mobil |
| benachrichtigung | 55 | Benachrichtigungen: nur Administrator, Prüfung der Adressen, Sicherheitsereignis mit Wer/IP, Bündelung mit Zähler, Anmeldesperre, Abmeldehinweis an eingestellte bzw. Antwortadresse, ausgeschaltet = keine E-Mail, Test-Knopf, Oberfläche |
| order_management | 41 | Bestellverwaltung (API): Rechte, Statusübergänge, Revision, Kundenansicht ohne interne Felder („Bestätigt“ erscheint Kunden als „In Bearbeitung“), Wiederholungsschutz per requestId, Mailausfall |
| order_management_ui | 10 | Bestellverwaltung im Eingabebereich und „Meine Bestellwünsche“ für Kunden (inkl. Mobil, sichere Darstellung) |
| order_outbox | 40 | Dauerhafte Versandaufträge, Teilfehler, SMTP-Ausfall, verlorene Bestätigung, Sperren, Rechte und gezielter Neuversand |
| order_outbox_ui | 9 | Mobile Empfängeranzeige, Bestätigungsdialog, Abbrechen und Neuversand ohne Duplikate erfolgreicher Nachrichten |
| bestellung | 91 | Bestellwunsch aus dem Portal: Angebots-/Bestellansicht, Frachtanteil unter der Mindestmenge (Server, E-Mail, Dialog, Leiste, Einstellungen in der Verwaltung), Einstellungen, serverseitige Kundenpreise, Prüfungen (Version, Freischaltung, Mengen, Datum), E-Mail an Empfänger + Kopie, Ausfall des Mailservers, Oberfläche (Mengen, Leiste, Dialog, Mobil) |
| kunden_mail | 137 | E-Mail-Versand gegen Test-Mailserver: Einladung mit Einmal-Link, Passwort-Link, Angebotslink, Wochenversand, Testmail, Rechte, Header-Injection, Ausfall des Mailservers, Postfach im Eingabebereich (verschlüsselt, Vorrang vor .env), Abmelden vom Wochenangebot (Link + Ein-Klick) |
| app_api | 40 | Schnittstelle für die App: `app_info` (öffentlich, Wartung ohne Mitarbeitername), Sitzung über `X-WA-Sitzung` statt Cookie (neue Kennung nach Anmeldung, erfundene/ungültige Kennungen verworfen, ohne `X-WA-Client` nicht angenommen, Browser-Cookie unberührt), CSRF, Merkliste, Bestellwunsch mit Fracht und Wiederholungsschutz, eigene Vorgänge ohne interne Felder, Gerätetyp „App“ in der Auswertung, Widerruf (Passwortwechsel, Abmelden, Administrator), Mitarbeiter mit Zwei-Faktor, Revision |
| app_web | 38 | App als Web-Build gegen den Testserver (390 px und Tablet): Angebot, Suche, Bereiche, Merkliste (Gast → Kunde), Vermerk, Anmeldung, Menge/Schnellwahl/ungültige Eingabe, Bestellleiste, Frachthinweis, Datum, Senden, gespeicherte Werte, verlorene Antwort ohne Doppelbestellung, offline mit Hinweis, Neustart, abgelaufene Sitzung, Mitarbeiter mit Code, Suche, Bearbeiten, gleichzeitige Änderung, keine JavaScript-Fehler. **Nur wenn `mobile/dist-web` gebaut ist** (`cd mobile && npm run export:web`), sonst überspringt der volle Lauf die Gruppe mit Hinweis |
| web_app | 25 | Web-App: Manifest und Symbole (Größen, maskable, iPhone), Favicon auf allen Seiten, Offline-Speicher (nur Startseite, Dateien, öffentliches Angebot; nie Kundenstatus, Kundenangebote, Eingabebereich; eine Fassung je Datei), offline mit Hinweis „Preise ohne Gewähr“ (Server wird dafür wirklich beendet), wieder online, Hinweis „Zum Home-Bildschirm“ auf iPhone (schließen bleibt gespeichert), Android-Installationsabfrage, nicht am Computer und nicht in der installierten Web-App, 390 px |
| p0 | 17 | Ersteinrichtung gesperrt, CSV-Formel-Schutz, Sicherungs- und Bereitstellungsanzeige, Server-Module nicht direkt abrufbar |

Bewertung bei der Übernahme ins Repository: Alle Prüfungen sind ausführbar. Zwei Platzhalter ohne Aussage wurden
entfernt. Neun Prüfungen der Form `check(…, True)` folgen auf ein `wait_for_selector`, das bei Fehlern mit Ausnahme
abbricht – sie sind wirksam, aber nur indirekt formuliert (zur späteren Umstellung vorgemerkt). Fest eingetragene
Preise und Mengen der Originaldaten wurden durch berechnete Erwartungswerte ersetzt. Die früheren Varianten
`test_sys_https` und `test_sys_pkg` (ZIP-Paket für Webhosting) sind mit dem Docker-Betrieb überholt und nicht übernommen.
