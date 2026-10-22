# Zentrale Anmeldung – Betriebskonfiguration (noch nicht aktiv)

Vorbereitet für die Inbetriebnahme nach [docs/plattform/inbetriebnahme-anmeldung.md](../../docs/plattform/inbetriebnahme-anmeldung.md).
Nichts hiervon wird durch ein Release aktiv: `docker-compose.yml` und `Caddyfile` bleiben unverändert.

| Datei | Inhalt |
| --- | --- |
| `docker-compose.anmeldung.yml` | Ergänzung zu `docker-compose.yml`: App mit dem Image aus `deploy/image` (mod_auth_openidc), Keycloak 26.8.1 und eigene PostgreSQL 17 – fest über Digest; Keycloak nur auf `127.0.0.1:8180`, Datenbank nur im internen Netz |
| `apache-oidc.conf` | Keycloak-Hosts `dashboard-stafl.de` und `angebot.dashboard-stafl.de` (wie `tests/oidc/apache.conf`); als `sites-enabled/zz-…` eingebunden, damit `angebot-stafl.de` Standard-Host bleibt |
| `Caddyfile.anmeldung` | neue Hosts für Caddy (Schritt 6) |
| `realm-mitarbeiter.json` | Realm für den Betrieb, **erzeugt** von `werkzeuge/realm_produktion.py` aus dem Test-Realm (ohne Testnutzer, Geheimnisse als Platzhalter) – nicht von Hand ändern |
| `pruefen.sh` | Prüfung mit Docker (CI-Auftrag „Anwendungs-Image prüfen“) |
| `einrichten.sh` | Schritt 2: Geheimnisse in `.env` ergänzen, Realm-Import vorbereiten (startet nichts) |
| `konten.sh` | Schritt 4 und Betrieb: Konten in der Serverkonsole verwalten (Verwaltungskonto, anlegen, Startpasswort, zweiten Faktor zurücksetzen, Passkey, sperren, Liste) |

## Geheimnisse (nur in `.env` auf dem Server)

`OIDC_SECRET_DASHBOARD`, `OIDC_SECRET_ANGEBOT` (Client-Geheimnisse), `OIDC_CRYPTO_DASHBOARD`, `OIDC_CRYPTO_ANGEBOT`
(Sitzungsschlüssel je Host), `KC_DB_PASSWORD`, einmalig `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD`
(entfernt `konten.sh verwaltung`), danach `KC_VERWALTUNG_PASSWORD` (Verwaltungskonto „verwaltung“ im Realm master).
Erzeugen z. B. mit `openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 40`.

Erzeugen und den Realm-Import vorbereiten übernimmt `deploy/anmeldung/einrichten.sh` (Schritt 2, im Installationsordner
auf dem Server): ergänzt nur fehlende Einträge in `.env` (nie überschreiben, nie anzeigen), schreibt
`daten-anmeldung/realm-import/realm-mitarbeiter.json` mit eingesetzten Client-Geheimnissen (nur für den Keycloak-Benutzer
lesbar) und startet nichts. `--pruefen` zeigt nur, was fehlt. Getestet: `tests/deploy/test_anmeldung_einrichten.sh`.

Der Import läuft nur beim ersten Start (vorhandener Realm wird nicht überschrieben). Spätere Änderungen am Realm nur
als eigener, geprüfter Schritt (`kcadm` im Container, wie in `konten.sh`).

## Konten (`konten.sh`, in der Serverkonsole)

Ruft `kcadm.sh` im Keycloak-Container auf (`docker compose … exec -T keycloak`), ohne Browser und ohne SSH-Tunnel.
Startpasswörter werden einmal angezeigt; bei der ersten Anmeldung verlangt Keycloak eigenes Passwort und Einmalcode
(Pflichtaktionen im Realm). Benutzernamen wie im Eingabebereich (2–32 Zeichen, a–z, Ziffern, `.`, `-`, `_`).
Getestet gegen echtes Keycloak in `tests/oidc/test_oidc.py` (Abschnitt „Konten über die Serverkonsole“).
