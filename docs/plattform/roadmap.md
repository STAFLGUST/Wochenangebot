# Roadmap – priorisierte Pull Requests

Jeder Schritt ist ein eigener, kleiner PR mit voller CI. Kein Schritt ändert Produktion ohne Release-Freigabe;
Datenbank-, DNS- und Serveränderungen sind gesondert markiert und brauchen zusätzlich Ihre ausdrückliche Freigabe.

| # | Inhalt | Phase | Produktivwirkung nach Release | Status |
| --- | --- | --- | --- | --- |
| 1 | Regelwerk `regeln/`, Prüfwerkzeug, CI-Schritt, Architektur-Doku, AGENTS.md | 1–3 | keine (nichts unter `app/` geändert) | **produktiv** |
| 2 | Aktions-Register je Bereich: jede Aktion gehört genau einer Oberfläche; Einstieg liest die Listen daraus statt `$writeActions`/`$isPublic`/`WARTUNG_GESPERRT`; CI prüft Vollständigkeit | 3 | keine (gleiches Verhalten, gleiche E2E-Tests) | **produktiv** (PR #66) |
| 3 | Modulregister zur Laufzeit: aus `regeln/` erzeugte PHP-Liste (`app/api/lib/module-liste.php`), Lese-Aktion `module_status` (nur angemeldet), Entscheidungstabelle in PHP mit denselben Vertragstests | 4–5 | keine sichtbare | **produktiv** (PR #67) |
| 4 | Wartung je Oberfläche serverseitig (Dokument `module`, Protokoll, Bestätigung, Notfallskript); heutiger Wartungsmodus wird `angebot.kunden` | 5 | Verwaltung → Wartung zeigt Oberflächen statt eines Schalters | **produktiv** (PR #69, Release 20261021-153029) – Eingabebereich; weitere Oberflächen, sobald sie freigegeben sind |
| 5 | Modulverwaltung im heutigen Eingabebereich (Liste, Freigabe, Wartung planen, Historie, Tester) | 5 | neue Ansicht für Administratoren | geplant |
| 6 | Dashboard-Oberfläche `dashboard/` (Kacheln aus dem Register, Status, Wartung, hell/dunkel, 390 px) – außerhalb der Dokumentwurzel, nur in Tests | 4 | keine (Caddy bleibt 503) | **gemergt** (PR #71) – bewusst nicht ausgeliefert |
| 7a | Herkunftsprüfung im API-Einstieg (`Sec-Fetch-Site`, `Origin`, GR-109) – wirkt sofort auch für `angebot-stafl.de` | 6 | Anfragen fremder Seiten (auch `test.angebot-stafl.de`) werden abgewiesen; eigene Seite, App unverändert | **produktiv** (PR #72) |
| 7b | Anmeldung nach ADR-003: OIDC-Client und hostgebundene Sitzungen im Plattformkern, Modulzugang `<modul>.zugang`, Back-Channel-Logout – zuerst nur in der CI (Keycloak + PostgreSQL als CI-Dienste) | 6 | **Server (Keycloak, PostgreSQL), DNS – mit Freigabe** | **implementiert (nur CI), PR offen** – OIDC-Client: mod_auth_openidc; Server, DNS erst mit Freigabe |
| 8 | Angebot-Eingabe unter `angebot.dashboard-stafl.de` (ADR-003), `/admin/` übergangsweise parallel, danach Weiterleitung | 7 | Mitarbeiter-Adresse ändert sich; Kundenseite unverändert | geplant (E-2 entschieden) |
| 9 | Integrationsumgebung `test.dashboard-stafl.de` (Container wie `app-test`, synthetische Daten) | 3 | **Serveränderung (mit Freigabe)** | geplant |
| 10 | Verwaltung: Stammdaten- und Importzentrale; Importleser bleiben beim Daten-Eigentümer | 8 | neue Oberfläche | geplant |
| 11 | PostgreSQL in CI/Testumgebung, dritter Speichertreiber, Migrationswerkzeug | 8 | **keine, bis Migration freigegeben** | geplant |
| 12 | Fachmodule Bestand → Einkauf → CRM → REWE (je eigener Agent, eigene PR-Serie) | 9 | je Modul, Freigabe einzeln | geplant |
| 13 | QS-Großprojekt (IFS Wholesale) – separater Auftrag | 10 | – | nicht begonnen |

Reihenfolge-Begründung: PR 2 und 3 entfernen die Sammelstellen, an denen parallele Agenten sich heute blockieren würden;
erst danach lohnt paralleles Arbeiten an Fachmodulen. Wartung (4–5) kommt vor dem Dashboard, weil sie den bestehenden
Echtbetrieb sofort verbessert und für die schrittweise Freigabe der Module gebraucht wird.

## Offene Entscheidungen

| Nr. | Frage | Empfehlung |
| --- | --- | --- |
| E-1 | Wer pflegt Kundenstammdaten – Verwaltung oder CRM? | Verwaltung (Nummer, Name, Anschrift, Gruppe, Zugang); CRM ergänzt Ansprechpartner, Aktivitäten, Vorgänge |
| E-2 | Domain- und Anmeldestruktur | **entschieden 21.10.2026:** Subdomains, eigener Anmelde-Host, Keycloak – [ADR-003](adr-003-domains-anmeldung.md) |
| E-3 | SQLite jetzt produktiv aktivieren? | ja, im Wartungsfenster mit dem vorhandenen Werkzeug – nach Ihrer Freigabe; vorher Status auf dem Server prüfen |
| E-4 | Repository privat stellen, bevor interne Module (Einkauf, QS) entstehen? | ja; Code darf zwar nie Sicherheit tragen, aber interne Abläufe müssen nicht öffentlich sein |
| E-8 | Testdomain (eigene registrierbare Domain) und eigener Test-Server | **entschieden:** mittelfristig; bis dahin Übergangsregeln GR-111 – [ADR-003 §3](adr-003-domains-anmeldung.md#3-testumgebung) |
| E-5 | Vorschauumgebungen je PR? | vorerst nein (Last und Fremdcode auf dem Produktiv-VPS); später ggf. getrennter Test-VPS |
| E-6 | Domain `qs-stafl.de` für das QS-Portal? | im QS-Auftrag entscheiden; Register führt sie mit Vorbehalt |
| E-7 | Externe Datensicherung | weiterhin zurückgestellt (Ihr Wunsch) – Risiko in [bestandsaufnahme.md](bestandsaufnahme.md#risiken-dokumentiert-nicht-behoben) |
