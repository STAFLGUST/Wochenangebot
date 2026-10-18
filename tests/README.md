# Automatische Tests

Alle Tests laufen gegen **Testkopien mit anonymisierten Testdaten** – nie gegen die Produktivseite oder echte Daten.

| Ebene | Aufruf | Inhalt |
| --- | --- | --- |
| Unit | `node tests/unit/bestand_parser.test.js` | Bestands-Parser der App gegen unabhängige Referenzauswertung |
| Unit | `node tests/unit/merge.test.js` | Abgleich beim gemeinsamen Bearbeiten des Entwurfs (feldweise, Kundenpreise, neue/gelöschte Artikel) |
| Versionsnummern | `python3 werkzeuge/asset_versionen.py` | Skripte/Stylesheets tragen die Prüfsumme ihres Inhalts (sonst laden Browser alte Kopien) |
| Ende-zu-Ende | `python3 tests/run_e2e.py [gruppe …]` | rund 45 Gruppen, über 1.100 Prüfungen im echten Browser gegen frische PHP-Testserver; 4 Gruppen parallel mit eigenen Ports (`WA_JOBS`, zur Fehlersuche `WA_JOBS=1`), volle Ausgabe je Gruppe in `tests/.arbeit/test-<gruppe>.log` |
| Betrieb | `sh tests/deploy/test_sichern.sh`, `sh tests/deploy/test_freigabe.sh` | Datensicherung; Release-Modus mit Healthcheck und automatischem Rückfall |

Voraussetzungen lokal: PHP 8.3, Node.js, Python 3.12, `pip install -r tests/requirements.txt`, `python -m playwright install chromium`.
In GitHub laufen alle Ebenen automatisch bei jedem Pull Request und jedem Commit auf `main` (`.github/workflows/ci.yml`).

## Testdaten

`tests/fixtures/` enthält nur anonymisierte Daten (Erzeugung: `werkzeuge/testdaten_erzeugen.py`):
Verkaufspreise je Artikel mit festem Faktor verändert, Bestandsmengen und Einkaufspreise erfunden, Partie- und
Gruppennummern ersetzt. Erwartungswerte in den Tests werden aus diesen Daten berechnet (`tests/e2e/testdaten.py`),
nicht fest eingetragen. **Echte Angebots-, Bestands- oder Nutzerdaten gehören nie ins Repository.**

## Gruppen und Aussagekraft (Stand 17.10.2026)

| Gruppe | Prüfungen | Schwerpunkt |
| --- | --- | --- |
| sys | 52 | Ersteinrichtung, Editor, Import, Veröffentlichen, Versionen, Passwort |
| frontend | 55 | öffentliche Seite: Filter, Suche, Sortierung, CSV, Druck, keine internen Daten |
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
| restposten | 52 | Sonderposten (Sonderpreis je Angebot, statt-Preis, automatisch ausgeblendet ohne Bestand), Ausblenden im Wochenangebot, rotes Kein-Bestand-Zeichen, Kurzes-MHD-Liste, Sonderposten-Mail nur an Kunden des jeweiligen Angebots, Angebotsseite |
| gemeinsam | 34 | Mehrere Bearbeiter gleichzeitig: Revisionen, 409 mit Namen, Anwesenheit, Hintergrundabfragen verlängern keine Sitzung, Abgleich in der Oberfläche, angefangene Eingaben bleiben, Veröffentlichen mit Konflikt |
| wartung | 25 | Wartungsmodus (Rechte, Sperre der Kundenfunktionen, Mitarbeiter arbeiten weiter, Abmeldelinks frei, Protokoll, Oberfläche) und erweiterte Übersicht |
| order_management | 41 | Bestellverwaltung (API): Rechte, Statusübergänge, Revision, Kundenansicht ohne interne Felder („Bestätigt“ erscheint Kunden als „In Bearbeitung“), Wiederholungsschutz per requestId, Mailausfall |
| order_management_ui | 10 | Bestellverwaltung im Eingabebereich und „Meine Bestellwünsche“ für Kunden (inkl. Mobil, sichere Darstellung) |
| order_outbox | 40 | Dauerhafte Versandaufträge, Teilfehler, SMTP-Ausfall, verlorene Bestätigung, Sperren, Rechte und gezielter Neuversand |
| order_outbox_ui | 9 | Mobile Empfängeranzeige, Bestätigungsdialog, Abbrechen und Neuversand ohne Duplikate erfolgreicher Nachrichten |
| bestellung | 64 | Bestellwunsch aus dem Portal: Einstellungen, serverseitige Kundenpreise, Prüfungen (Version, Freischaltung, Mengen, Datum), E-Mail an Empfänger + Kopie, Ausfall des Mailservers, Oberfläche (Mengen, Leiste, Dialog, Mobil) |
| kunden_mail | 137 | E-Mail-Versand gegen Test-Mailserver: Einladung mit Einmal-Link, Passwort-Link, Angebotslink, Wochenversand, Testmail, Rechte, Header-Injection, Ausfall des Mailservers, Postfach im Eingabebereich (verschlüsselt, Vorrang vor .env), Abmelden vom Wochenangebot (Link + Ein-Klick) |
| p0 | 17 | Ersteinrichtung gesperrt, CSV-Formel-Schutz, Sicherungs- und Bereitstellungsanzeige, Server-Module nicht direkt abrufbar |

Bewertung bei der Übernahme ins Repository: Alle Prüfungen sind ausführbar. Zwei Platzhalter ohne Aussage wurden
entfernt. Neun Prüfungen der Form `check(…, True)` folgen auf ein `wait_for_selector`, das bei Fehlern mit Ausnahme
abbricht – sie sind wirksam, aber nur indirekt formuliert (zur späteren Umstellung vorgemerkt). Fest eingetragene
Preise und Mengen der Originaldaten wurden durch berechnete Erwartungswerte ersetzt. Die früheren Varianten
`test_sys_https` und `test_sys_pkg` (ZIP-Paket für Webhosting) sind mit dem Docker-Betrieb überholt und nicht übernommen.
