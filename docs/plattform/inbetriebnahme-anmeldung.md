# Inbetriebnahme der zentralen Anmeldung (Keycloak) – Ablaufplan

Stand: vorbereitet, **nicht ausgeführt**. Jeder Schritt mit „Freigabe“ wird erst nach ausdrücklicher Zustimmung des
Inhabers ausgeführt (AGENTS.md: Server, DNS, Anmeldung). Grundlage: [ADR-003](adr-003-domains-anmeldung.md), in der CI
vollständig geprüft (`tests/oidc/`, 85 Prüfungen) und die Betriebskonfiguration in `deploy/anmeldung/` (`pruefen.sh`).

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
| 1 | **DNS:** A-/AAAA-Einträge `login.dashboard-stafl.de` und `angebot.dashboard-stafl.de` auf den Server (wie `dashboard-stafl.de`) | Inhaber | **DNS** | Einträge löschen |
| 2 | **Geheimnisse** auf dem Server erzeugen und in `.env` eintragen (Namen siehe `deploy/anmeldung/LIESMICH.md`); Realm mit eingesetzten Geheimnissen nach `daten-anmeldung/realm-import/` | Inhaber oder Claude per Anleitung | **Server** | Dateien löschen |
| 3 | **Keycloak und Datenbank starten:** `docker compose -f docker-compose.yml -f deploy/anmeldung/docker-compose.anmeldung.yml up -d keycloak keycloak-db` – noch ohne Caddy-Route, also nicht öffentlich | Inhaber | **Server** | `docker compose … stop keycloak keycloak-db` |
| 4 | **Einrichten über SSH-Tunnel** (`ssh -L 8180:127.0.0.1:8180 server`, dann `http://127.0.0.1:8180/admin/`): eigenes Verwaltungskonto mit zweitem Faktor anlegen, Start-Konto löschen (`KC_BOOTSTRAP_*` aus `.env` entfernen); Mitarbeiter mit **gleichem Benutzernamen** wie im Eingabebereich anlegen, Pflichtaktionen „Passwort festlegen“ und „Einmalcode/Passkey einrichten“ | Inhaber | – | Konten löschen |
| 5 | **Anwendungs-Image** auf dem Server bauen und die App mit Ergänzungsdatei neu starten (`… up -d app`). Ab hier lädt Apache die Keycloak-Hosts; `angebot-stafl.de` bleibt Standard-Host und verhält sich unverändert (in `pruefen.sh` geprüft) | Inhaber | **Server** | ohne Ergänzungsdatei neu starten (`docker compose up -d app`) |
| 6 | **Caddy:** Platzhalter für `dashboard-stafl.de` durch `deploy/anmeldung/Caddyfile.anmeldung` ersetzen (eigener PR mit Release) – damit werden Anmeldung, Dashboard und Mitarbeiter-Eingabe öffentlich erreichbar | Claude (PR), Inhaber (Release) | **Release** | Release zurück |
| 7 | **Sicherung** der Keycloak-Datenbank in `deploy/sichern.sh` ergänzen (`pg_dump`, verschlüsselt wie die Geschäftsdaten) und Rücksicherung einmal üben | Claude (PR) | Release | – |
| 8 | **Probe mit einem Konto** (Inhaber): Anmeldung mit Einmalcode und Passkey, Dashboard, Mitarbeiter-Eingabe, sensible Aktion (erneute Anmeldung), Abmelden für alle | Inhaber | – | – |
| 9 | **Mitarbeiter informieren:** neue Adresse `angebot.dashboard-stafl.de`; `/admin/` bleibt bis Roadmap 8 parallel | Inhaber | – | – |

Danach (eigene Schritte, je mit Freigabe): `/admin/` auf `angebot-stafl.de` auf die neue Adresse umleiten und die eigene
Mitarbeiteranmeldung dort abschalten (Roadmap 8); HSTS der Kundendomain auf ein Jahr; App-Anmeldung über Keycloak.

## Was im Betrieb gilt

- **Verwaltung von Keycloak** nur über den SSH-Tunnel; Caddy leitet auf `login.` ausschließlich `/realms/mitarbeiter/`
  und `/resources/` weiter (Master-Realm und Verwaltung: 404).
- **Rechte** bleiben in der Anwendung (Nutzer → Rollen und Rechte). Keycloak sagt nur „wer“; ein in der Anwendung
  gesperrtes Konto ist sofort ausgesperrt. Neue Mitarbeiter brauchen beides: Konto in Keycloak und Mitarbeiterkonto.
- **Abmelden / Sperren:** Abmelden in einer Anwendung meldet in allen ab (Back-Channel-Logout). Ein Konto zentral
  sperren: in Keycloak deaktivieren oder in der Anwendung sperren (wirkt sofort).
- **Updates von Keycloak:** Version und Digest in `deploy/anmeldung/docker-compose.anmeldung.yml` und
  `tests/oidc/umgebung.sh` gemeinsam erhöhen; erst wenn der CI-Auftrag grün ist (ADR-003: kritische Lücken in 72 Std.).
- **Notfall:** Keycloak nicht erreichbar → Mitarbeiter arbeiten übergangsweise über `angebot-stafl.de/admin/` weiter
  (solange Roadmap 8 nicht umgesetzt ist). Danach: Rückweg in Schritt 5/6.

## Offene Punkte vor Schritt 6

- Sicherung der Keycloak-Datenbank (Schritt 7) – vor der öffentlichen Freischaltung fertig.
- Datenschutz: Keycloak speichert Anmeldeereignisse (Realm-Einstellung „Events“); Aufbewahrung festlegen (Vorschlag 30 Tage).
