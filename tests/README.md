# Automatische Tests

Alle Tests laufen gegen **Testkopien mit anonymisierten Testdaten** – nie gegen die Produktivseite oder echte Daten.

| Ebene | Aufruf | Inhalt |
| --- | --- | --- |
| Unit | `node tests/unit/bestand_parser.test.js` | Bestands-Parser der App gegen unabhängige Referenzauswertung |
| Ende-zu-Ende | `python3 tests/run_e2e.py [gruppe …]` | 14 Gruppen, über 400 Prüfungen im echten Browser gegen frische PHP-Testserver |
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
| p0 | 13 | Ersteinrichtung gesperrt, CSV-Formel-Schutz, Sicherungs- und Bereitstellungsanzeige |

Bewertung bei der Übernahme ins Repository: Alle Prüfungen sind ausführbar. Zwei Platzhalter ohne Aussage wurden
entfernt. Neun Prüfungen der Form `check(…, True)` folgen auf ein `wait_for_selector`, das bei Fehlern mit Ausnahme
abbricht – sie sind wirksam, aber nur indirekt formuliert (zur späteren Umstellung vorgemerkt). Fest eingetragene
Preise und Mengen der Originaldaten wurden durch berechnete Erwartungswerte ersetzt. Die früheren Varianten
`test_sys_https` und `test_sys_pkg` (ZIP-Paket für Webhosting) sind mit dem Docker-Betrieb überholt und nicht übernommen.
