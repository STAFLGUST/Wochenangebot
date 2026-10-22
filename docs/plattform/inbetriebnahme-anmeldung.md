# Inbetriebnahme der zentralen Anmeldung (Keycloak) – Ablaufplan

Stand: vorbereitet, **nicht ausgeführt**. Jeder Schritt mit „Freigabe“ wird erst nach ausdrücklicher Zustimmung des
Inhabers ausgeführt (AGENTS.md: Server, DNS, Anmeldung). Grundlage: [ADR-003](adr-003-domains-anmeldung.md), in der CI
vollständig geprüft (`tests/oidc/`, 111 Prüfungen) und die Betriebskonfiguration in `deploy/anmeldung/` (`pruefen.sh`).

## Ziel nach der Inbetriebnahme

| Adresse | Inhalt | Anmeldung |
| --- | --- | --- |
| `angebot-stafl.de` | Kundenseite und – übergangsweise – `/admin/` wie heute | unverändert (eigene Anmeldung) |
| `login.dashboard-stafl.de` | Keycloak, nur Realm `mitarbeiter` | Passwort + Einmalcode oder Passkey |
| `dashboard-stafl.de` | Mitarbeiter-Dashboard | über Keycloak |
| `angebot.dashboard-stafl.de` | Mitarbeiter-Eingabe (dieselbe Anwendung wie `/admin/`) | über Keycloak |
| übrige `*.dashboard-stafl.de` | 503-Platzhalter bis zur Freigabe des Moduls (GR-105) | – |

Kunden merken nichts. Mitarbeiter können während der Übergangszeit beides nutzen; die alte Anmeldung unter
`angebot-stafl.de/admin/` wird erst in einem späteren, eigenen Schritt abgeschaltet (Roadmap 8).

## Voraussetzungen

- Server Hostinger KVM 2 (2 vCPU, 8 GB): Keycloak braucht etwa 0,7–1 GB, die eigene PostgreSQL-Datenbank etwa 0,2 GB.
  Reicht; ein Upgrade auf KVM 4 ist nicht nötig, solange die Auslastung unauffällig bleibt.
- Aktueller Stand von `main` auf dem Server (Release), CI grün einschließlich „Anmeldung über Keycloak“ und
  „Anwendungs-Image prüfen“.
- Sicherung der Geschäftsdaten wie gewohnt (`deploy/sichern.sh`). Die Keycloak-Datenbank kommt in Schritt 7 dazu.

## Schritte

| # | Schritt | Wer | Freigabe | Rückweg |
| --- | --- | --- | --- | --- |
| 1 | **DNS:** CNAME `login` und `angebot` → `dashboard-stafl.de` (wie `bestand.`/`www.`) – **erledigt 21.10.2026**, von außen geprüft | Inhaber | **DNS** | Einträge löschen |
| 2 | **Geheimnisse** erzeugen und Realm-Import vorbereiten: im Installationsordner `sh deploy/anmeldung/einrichten.sh` (ergänzt nur fehlende Einträge in `.env`, zeigt keine Werte, startet nichts; `--pruefen` vorher/nachher) | Inhaber | **Server** | neue Zeilen in `.env` und `daten-anmeldung/` löschen |
| 3 | **Keycloak und Datenbank starten:** `docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml up -d keycloak keycloak-db` – noch ohne Caddy-Route, also nicht öffentlich; Kontrolle: `curl -s http://127.0.0.1:8180/realms/mitarbeiter/.well-known/openid-configuration` | Inhaber | **Server** | `docker compose -f … -f … stop keycloak keycloak-db` |
| 4 | **Konten in der Serverkonsole** (kein SSH, kein Browser): `sh deploy/anmeldung/konten.sh verwaltung` (dauerhaftes Verwaltungskonto mit Zufallspasswort in `.env`, Start-Konto gelöscht, `KC_BOOTSTRAP_*` aus `.env` entfernt), dann je Mitarbeiter `sh deploy/anmeldung/konten.sh anlegen <benutzername> <e-mail> <vorname> <nachname>` mit dem **gleichen Benutzernamen** wie im Eingabebereich – Startpasswort wird einmal angezeigt; bei der ersten Anmeldung sind eigenes Passwort und Einmalcode Pflicht. Zunächst nur das eigene Konto (Probe in Schritt 8), die übrigen danach | Inhaber | – | `konten.sh sperren <name>` |
| 5 | **Ergänzungsdatei dauerhaft aktivieren** – in `.env`: `COMPOSE_FILE=docker-compose.yml:deploy/anmeldung/docker-compose.anmeldung.yml` (sonst würde ein späteres Release die App wieder ohne Keycloak-Hosts starten) –, dann Anwendungs-Image bauen und App neu starten (`docker compose build app && docker compose up -d app`, wenige Sekunden Unterbrechung). `angebot-stafl.de` bleibt Standard-Host und verhält sich unverändert (in `pruefen.sh` geprüft) | Inhaber | **Server** | Zeile `COMPOSE_FILE` entfernen, `docker compose up -d app` |
| 6 | **Caddy:** Platzhalter für `dashboard-stafl.de` durch `deploy/anmeldung/Caddyfile.anmeldung` ersetzen (eigener PR mit Release) – damit werden Anmeldung, Dashboard und Mitarbeiter-Eingabe öffentlich erreichbar | Claude (PR), Inhaber (Release) | **Release** | Release zurück |
| 7 | **Sicherung** der Keycloak-Datenbank in `deploy/sichern.sh` ergänzen (`pg_dump`, verschlüsselt wie die Geschäftsdaten) und Rücksicherung einmal üben | Claude (PR) | Release | – |
| 8 | **Probe mit einem Konto** (Inhaber): Anmeldung mit Einmalcode und Passkey, Dashboard, Mitarbeiter-Eingabe, sensible Aktion (erneute Anmeldung), Abmelden für alle | Inhaber | – | – |
| 9 | **Mitarbeiter informieren:** neue Adresse `angebot.dashboard-stafl.de`; `/admin/` bleibt bis Roadmap 8 parallel | Inhaber | – | – |

Danach (eigene Schritte, je mit Freigabe): `/admin/` auf `angebot-stafl.de` auf die neue Adresse umleiten und die eigene
Mitarbeiteranmeldung dort abschalten (Roadmap 8); HSTS der Kundendomain auf ein Jahr; App-Anmeldung über Keycloak.

## Was im Betrieb gilt

- **Verwaltung von Keycloak** nur in der Serverkonsole mit `deploy/anmeldung/konten.sh` (anlegen, Startpasswort,
  Passkey, sperren/entsperren, Liste); die Verwaltungsoberfläche ist nur auf dem Server selbst erreichbar
  (`127.0.0.1:8180`). Caddy leitet auf `login.` ausschließlich `/realms/mitarbeiter/` und `/resources/` weiter
  (Master-Realm und Verwaltung: 404).
- **Passwort vergessen:** `konten.sh startpasswort <name>` – der Einmalcode bleibt Pflicht, danach eigenes Passwort.
  Handy oder Passkey verloren: nach persönlicher Prüfung `konten.sh zuruecksetzen <name>` (löscht Einmalcode und
  Passkeys, meldet überall ab, neues Startpasswort). Konten nie löschen und neu anlegen – die Verknüpfung mit dem
  Mitarbeiterkonto hängt an der Keycloak-Kennung.
- **Anmeldeereignisse** (Anmeldungen, Fehlversuche) speichert Keycloak 30 Tage, danach werden sie gelöscht
  (Realm-Einstellung `eventsExpiration`; Änderung als eigener Schritt).
- **Rechte** bleiben in der Anwendung (Nutzer → Rollen und Rechte). Keycloak sagt nur „wer“; ein in der Anwendung
  gesperrtes Konto ist sofort ausgesperrt. Neue Mitarbeiter brauchen beides: Konto in Keycloak und Mitarbeiterkonto.
- **Abmelden / Sperren:** Abmelden in einer Anwendung meldet in allen ab (Back-Channel-Logout). Ein Konto zentral
  sperren: `konten.sh sperren <name>` (deaktiviert und meldet überall ab) oder in der Anwendung sperren (wirkt sofort).
- **Updates von Keycloak:** Version und Digest in `deploy/anmeldung/docker-compose.anmeldung.yml` und
  `tests/oidc/umgebung.sh` gemeinsam erhöhen; erst wenn der CI-Auftrag grün ist (ADR-003: kritische Lücken in 72 Std.).
- **Notfall:** Keycloak nicht erreichbar → Mitarbeiter arbeiten übergangsweise über `angebot-stafl.de/admin/` weiter
  (solange Roadmap 8 nicht umgesetzt ist). Danach: Rückweg in Schritt 5/6.

## Offene Punkte vor Schritt 6

- Sicherung der Keycloak-Datenbank (Schritt 7) – vor der öffentlichen Freischaltung fertig.
