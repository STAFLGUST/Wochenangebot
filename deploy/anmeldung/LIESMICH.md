# Zentrale Anmeldung – Betriebskonfiguration

Vorbereitet für die Inbetriebnahme nach [docs/plattform/inbetriebnahme-anmeldung.md](../../docs/plattform/inbetriebnahme-anmeldung.md).
`docker-compose.yml` bleibt unverändert; aktiv wird die Ergänzungsdatei erst über `COMPOSE_FILE` in `.env` (Schritt 5).
Die öffentlichen Hosts stehen im `Caddyfile` (Schritt 6) und führen nur zu Zielen, die es ausschließlich mit der
Ergänzungsdatei gibt (`keycloak`, Netzwerkname `app-mitarbeiter`) – ohne sie antworten sie mit 502.

| Datei | Inhalt |
| --- | --- |
| `docker-compose.anmeldung.yml` | Ergänzung zu `docker-compose.yml`: App mit dem Image aus `deploy/image` (mod_auth_openidc), Keycloak 26.8.1 und eigene PostgreSQL 17 – fest über Digest; Keycloak nur auf `127.0.0.1:8180`, Datenbank nur im internen Netz |
| `apache-oidc.conf` | Keycloak-Hosts `dashboard-stafl.de`, `angebot.dashboard-stafl.de`, `verwaltung.dashboard-stafl.de` (dort `/import/` → Importzentrale), `bestand.dashboard-stafl.de`, `hr.dashboard-stafl.de`, `sicherheit.dashboard-stafl.de` (`/` und `/admin/` → `/module/sicherheit/`), `controlling.dashboard-stafl.de` (`/` und `/admin/` → `/module/controlling/`) (`/` und `/admin/` → `/module/hr/`) , `crm.dashboard-stafl.de` (`/` und `/admin/` → `/module/crm/`) und `marketing.dashboard-stafl.de` (`/` und `/admin/` → `/module/marketing/`) (wie `tests/oidc/apache.conf`); je Host eigener Client, eigene Sitzung und `WA_OBERFLAECHE`; als `sites-enabled/zz-…` eingebunden, damit `angebot-stafl.de` Standard-Host bleibt |
| `realm-mitarbeiter.json` | Realm für den Betrieb, **erzeugt** von `werkzeuge/realm_produktion.py` aus dem Test-Realm (ohne Testnutzer, Geheimnisse als Platzhalter) – nicht von Hand ändern |
| `pruefen.sh` | Prüfung mit Docker (CI-Auftrag „Anwendungs-Image prüfen“) |
| `einrichten.sh` | Schritt 2: Geheimnisse in `.env` ergänzen, Realm-Import vorbereiten (startet nichts) |
| `app-abfrage.php` | von `konten.sh` im App-Container ausgeführt: Postfach der Anwendung (für den Mailversand von Keycloak) und ob es ein Mitarbeiterkonto gibt |
| `ruecksicherung-probe.sh` | Schritt 7: Rücksicherung der Keycloak-Sicherung in eine Probedatenbank üben (Konten zählen, danach löschen) |
| `konten.sh` | Schritt 4 und Betrieb: Konten in der Serverkonsole verwalten (Verwaltungskonto, anlegen, Startpasswort, zweiten Faktor zurücksetzen, Passkey, sperren, Liste) |
| `theme/stafl/login/` | Design der Anmeldeseite („Liquid Glass“ wie Dashboard und Eingabebereich, Logo aus `app/assets/`): erbt von `keycloak.v2`; eigen sind `stafl.css`, `stafl-otp.js` (Einmalcode-Felder), `messages_de.properties` und zwei Vorlagen (`login-otp.ftl`, `login-config-totp.ftl`, Grundlage Keycloak 26.8.1). Per Volume nur lesend in Keycloak |

**Releases:** Ändert ein Release `deploy/image/` (z. B. neuer Digest des Basis-Images), baut `deploy/freigabe-einspielen.sh`
das Image vor dem Einspielen neu (`docker compose build --pull app`) und erstellt die App neu – nur solange `COMPOSE_FILE`
die Ergänzungsdatei enthält. Bau-Fehler → nicht eingespielt; Rückfall (automatisch und von Hand mit
`deploy/release-zurueck.sh`) → altes Image (`stafl-app:release-vorher`, fehlt es: Neubau aus dem alten Bauplan).
Nach erfolgreichem Release werden hängende Images ohne Namen entfernt (`docker image prune -f`).
Ablauf: [docs/release-freigabe.md](../../docs/release-freigabe.md).

## Geheimnisse (nur in `.env` auf dem Server)

`OIDC_SECRET_DASHBOARD`, `OIDC_SECRET_ANGEBOT`, `OIDC_SECRET_VERWALTUNG`, `OIDC_SECRET_BESTAND`, `OIDC_SECRET_HR`, `OIDC_SECRET_CRM`, `OIDC_SECRET_MARKETING`, `OIDC_SECRET_KONTEN` (Client-Geheimnisse; `KONTEN` = Mitarbeiterkonten aus der Verwaltung, ohne Sitzungsschlüssel), `OIDC_CRYPTO_DASHBOARD`,
`OIDC_CRYPTO_ANGEBOT`, `OIDC_CRYPTO_VERWALTUNG`, `OIDC_CRYPTO_BESTAND`, `OIDC_CRYPTO_HR`, `OIDC_CRYPTO_CRM`, `OIDC_CRYPTO_MARKETING` (Sitzungsschlüssel je Host), `KC_DB_PASSWORD`, nach der Einrichtung `KC_VERWALTUNG_PASSWORD` (Verwaltungskonto „verwaltung“
im Realm master). Das Start-Konto (`KC_BOOTSTRAP_ADMIN_*`) steht nur während der Einrichtung in
`daten-anmeldung/einrichtung.env` (Compose liest die Datei nur, wenn sie existiert; `konten.sh verwaltung` löscht sie).
Nie leer in `.env` setzen: Keycloak 26.8 startet mit leerem Start-Konto-Namen nicht.
Erzeugen z. B. mit `openssl rand -base64 36 | tr -dc 'A-Za-z0-9' | head -c 40`.

Erzeugen und den Realm-Import vorbereiten übernimmt `deploy/anmeldung/einrichten.sh` (Schritt 2, im Installationsordner
auf dem Server): ergänzt nur fehlende Einträge in `.env` (nie überschreiben, nie anzeigen), schreibt
`daten-anmeldung/realm-import/realm-mitarbeiter.json` mit eingesetzten Client-Geheimnissen (nur für den Keycloak-Benutzer
lesbar) und startet nichts. `--pruefen` zeigt nur, was fehlt. Getestet: `tests/deploy/test_anmeldung_einrichten.sh`.

Der Import läuft nur beim ersten Start (vorhandener Realm wird nicht überschrieben). Spätere Änderungen am Realm nur
als eigener, geprüfter Schritt (`kcadm` im Container, wie in `konten.sh`).

## Sitzungen: Ablauf und Beenden

Die Sitzung des Webserver-Moduls (4 Stunden Leerlauf, höchstens 10 Stunden – wie der Realm nach `realm-aktualisieren`) ist die
äußere Grenze. Zusätzlich gelten die Einstellungen der Anwendung auch auf den Keycloak-Hosts (seit 26.10.2026,
`lib/oidc.php`): Nach der eingestellten Inaktivität (Verwaltung → Sicherheit) und nach „Sitzung beenden“ (Verwaltung →
Sitzungen) geht es erst nach erneuter Anmeldung bei Keycloak weiter (Passwort erneut, `max_age=0`) – die Sitzung entsteht
nicht mehr stillschweigend neu. Kein Konsolenbefehl nötig.

## Realm im Betrieb ändern

Der Realm wird nur beim ersten Start importiert. Spätere Änderungen bringt `sh deploy/anmeldung/konten.sh realm-aktualisieren`
auf den laufenden Realm (idempotent, ohne Kontenverlust); die Testumgebung (`tests/oidc/umgebung.sh`) führt denselben
Befehl nach dem Import aus, die CI prüft also genau diesen Weg. Stand 2 (22.10.2026): zweiter Faktor nur für
Pflicht-Konten (entscheidet die Anwendung), Anmeldemethoden im Claim `amr`, Leerlauf 4 Stunden.
Stand 3 (22.10.2026): Client `verwaltung` für `verwaltung.dashboard-stafl.de` – legt ihn an, falls er fehlt (Definition aus
`realm-mitarbeiter.json`), und ergänzt fehlende `OIDC_SECRET_VERWALTUNG`/`OIDC_CRYPTO_VERWALTUNG` in `.env` (nie angezeigt).
Danach liest die Anwendung die neuen Werte erst nach `docker compose up -d app` (der Befehl weist darauf hin). Bis dahin
startet die Anwendung trotzdem (Compose nimmt für die Verwaltung den Schlüssel des Eingabebereichs; ohne Client in
Keycloak ist dort keine Anmeldung möglich).
Stand 4 (22.10.2026): Client `bestand` für `bestand.dashboard-stafl.de` – gleiches Vorgehen wie Stand 3 (`OIDC_SECRET_BESTAND`/
`OIDC_CRYPTO_BESTAND`, danach `docker compose up -d app`). Der Befehl geht jetzt alle Clients der Realm-Datei durch (fehlende
anlegen, Anmeldestärke und Claim `amr` einheitlich setzen) – ein künftiger Modul-Host braucht dort keine Codeänderung mehr.
Stand 5 (23.10.2026, Freigabe des Inhabers): Client `hr` für `hr.dashboard-stafl.de` (Urlaubsverwaltung) – gleiches Vorgehen
(`OIDC_SECRET_HR`/`OIDC_CRYPTO_HR`, danach `docker compose up -d app`). Voraussetzung: DNS-Eintrag `hr` (CNAME →
`dashboard-stafl.de`, wie `bestand.`/`login.`), sonst bekommt Caddy kein Zertifikat für den Host.
Stand 6 (23.10.2026, Freigabe des Inhabers): Client `crm` für `crm.dashboard-stafl.de` (CRM · Vertrieb) – gleiches Vorgehen
(`OIDC_SECRET_CRM`/`OIDC_CRYPTO_CRM`, danach `docker compose up -d app`). Der DNS-Eintrag `crm` besteht seit 21.10.2026.
Stand 7 (25.10.2026, Freigabe des Inhabers): Client `marketing` für `marketing.dashboard-stafl.de` (Marketing · Redaktionsplan) –
gleiches Vorgehen (`OIDC_SECRET_MARKETING`/`OIDC_CRYPTO_MARKETING`, danach `docker compose up -d app`). Der DNS-Eintrag `marketing` besteht seit 25.10.2026.
Stand 9 (26.10.2026, Freigabe des Inhabers): Client `sicherheit` für `sicherheit.dashboard-stafl.de` (Modul Sicherheit mit Notfallmodus) –
gleiches Vorgehen (`OIDC_SECRET_SICHERHEIT`/`OIDC_CRYPTO_SICHERHEIT`, danach `docker compose up -d app`). Der DNS-Eintrag `sicherheit` (CNAME) besteht seit 26.10.2026.

Stand 10 (28.10.2026, Freigabe des Inhabers): Client `controlling` für `controlling.dashboard-stafl.de` (Modul Controlling) – gleiches
Vorgehen (`OIDC_SECRET_CONTROLLING`/`OIDC_CRYPTO_CONTROLLING`, danach `docker compose up -d app`). Der DNS-Eintrag `controlling` (CNAME) besteht seit 25.10.2026.
Stand 8 (26.10.2026, Wunsch des Inhabers „ein Passwort“): Client `konten` – kein Host, nur ein Service-Account, mit dem die
Verwaltung (Verwaltung → Mitarbeiter → „Zentrale Anmeldung“, nur Administratoren, immer mit Bestätigung) Passwörter setzt,
Sperren nach Fehlversuchen aufhebt, den Link zum Passwort-Festlegen schickt und fehlende Konten anlegt
(`app/api/lib/anmeldekonten.php`). Rechte genau `view-users` und `manage-users` von `realm-management` – keine Realm-,
Client- oder Rollenverwaltung, kein Anmelden im Namen anderer, kein Passwort-Grant; `realm-aktualisieren` entfernt
zusätzliche Rollen. Legt `OIDC_SECRET_KONTEN` in `.env` an (nie angezeigt); danach `docker compose up -d app`. Die Anwendung
spricht Keycloak im internen Netz an (`WA_KONTEN_URL=http://keycloak:8080`, nicht über Caddy). Ohne das Geheimnis zeigt die
Verwaltung „noch nicht eingerichtet“ – sonst ändert sich nichts. Rückweg: Client `konten` in Keycloak deaktivieren oder die
Zeile `OIDC_SECRET_KONTEN` aus `.env` entfernen und `docker compose up -d app`.

## Alter Eingabebereich (angebot-stafl.de/admin/) stillgelegt

Seit dem 23.10.2026 setzt diese Datei `WA_EIGENE_ANMELDUNG=aus`: Auf dem Host ohne zentrale Anmeldung gibt es keine
Mitarbeiteranmeldung, keine Mitarbeitersitzung und keine Mitarbeiteraktion mehr (Antwort 410 `umgezogen` mit `ziel`,
`/admin/` zeigt einen Hinweis und leitet nach `angebot.dashboard-stafl.de/admin/` weiter). Unverändert: Kundenseite,
öffentliches Angebot, Kundenanmeldung und -bestellungen, `status` (Healthcheck), `logout`. Mails an Mitarbeiter
verweisen auf die neue Adresse (`WA_EINGABE_ADRESSE`, Standard `https://angebot.dashboard-stafl.de/admin/`).

Notzugang bei gestörter Anmeldung: `sh deploy/notzugang.sh an` (setzt `WA_EIGENE_ANMELDUNG=an` in `.env`, erstellt die App
neu), danach `sh deploy/notzugang.sh aus`. Rückfall auf das alte Verhalten dauerhaft: dieselbe Zeile `=an`.

## Design der Anmeldeseite und der E-Mails

Keycloak liest das Theme aus `deploy/anmeldung/theme/stafl` (Volume in `docker-compose.anmeldung.yml`, nur lesend):
`login/` für die Anmeldeseite, `email/` für die Einladung bzw. den Link zum Passwort-Festlegen (Vorlage `executeActions`,
gleicher Stil wie die Plattform-Mails, keine Bilder). Aktiv wird es erst mit `sh deploy/anmeldung/konten.sh design-setzen`
(setzt `loginTheme=stafl` und `emailTheme=stafl` im Realm „mitarbeiter“, idempotent, ändert sonst nichts – keine Abläufe,
Richtlinien oder Clients; einmal erneut ausführen, wenn bisher nur die Anmeldeseite gesetzt war). Neuinstallationen bekommen es schon über
`realm-mitarbeiter.json`. Der Befehl bricht ab, wenn Keycloak das Theme nicht kennt (Container noch ohne Volume: zuerst
`docker compose … up -d keycloak`). Rückfall: `sh deploy/anmeldung/konten.sh design-setzen standard` (mitgelieferte
Designs von Keycloak für Anmeldeseite und E-Mails, sofort wirksam).

- **Einmalcode:** Feld mit `autocomplete="one-time-code"`, Ziffernblock, Muster für 6 Ziffern und Hinweis auf die App
  „STAFL-Plattform“. Keycloak vergleicht den Code genau so, wie er ankommt – „123 456“ wäre ein Fehlversuch. Das kleine
  Skript `stafl-otp.js` entfernt deshalb beim Tippen und Einfügen alles außer Ziffern (ohne Skript verhindert das Muster
  das Absenden). Bei der Einrichtung weist ein Kasten darauf hin, alte Einträge in der Authenticator-App zu löschen.
- **Abgelehnter Code und Sperre:** Jeder Code gilt nur einmal; zwei Fehlversuche in unter einer Sekunde sperren 60 s.
  Keycloak zeigt bei einer Sperre dieselbe Meldung wie bei einem falschen Code (verrät sie nicht). Der deutsche Text nennt
  deshalb beides („nur einmal … neuen Code abwarten … nach mehreren Fehlversuchen gesperrt“), und `stafl-otp.js` schickt
  jedes Anmeldeformular nur einmal ab (Doppelklick, Eingabetaste plus Klick). Aufheben: `konten.sh entsperren <name>`.
- **Zwischenspeicher:** `KC_SPI_THEME__CACHE_THEMES/…CACHE_TEMPLATES=false`, `…STATIC_MAX_AGE=3600` – ein Release mit
  geändertem Theme wirkt ohne Neustart von Keycloak, Browser holen Stylesheet und Skript spätestens nach einer Stunde neu.
- **Keycloak-Update:** die beiden Vorlagen mit der neuen Fassung von `keycloak.v2` vergleichen und die Versionsangabe
  darin anpassen (der CI-Auftrag „Anmeldung über Keycloak“ prüft, dass sie zur Version in `tests/oidc/umgebung.sh` passt).

## Einladungen per Mail

Einmalig `sh deploy/anmeldung/konten.sh mail-einrichten <eigene-adresse>`: Keycloak verschickt über das Postfach der
Anwendung – ist unter Verwaltung → E-Mail ein „Postfach für interne E-Mails“ eingerichtet (z. B. `verwaltung@…`), dieses,
sonst das Postfach für Kunden-E-Mails bzw. `MAIL_SMTP_*` in `.env` – und schickt eine Testmail. Nach dem Einrichten oder
Ändern des internen Postfachs `mail-einrichten` erneut ausführen. Das
Postfach-Passwort liegt nur im Tresor von Keycloak (`daten-anmeldung/vault/`, nur Keycloak liest es); die Datenbank und
ihre Sicherung enthalten nur den Verweis `${vault.smtp_password}`. Ändert sich das Postfach-Passwort oder nach einer
Wiederherstellung auf neuem Server: `mail-einrichten` erneut ausführen.

Neue Mitarbeiter: zuerst das Mitarbeiterkonto im Eingabebereich anlegen (Rolle, Rechte), dann
`sh deploy/anmeldung/konten.sh einladen <benutzername> <e-mail> <vorname> <nachname>`. Die Mail enthält einen Link
(72 Stunden gültig, nur einmal verwendbar); darüber legt der Mitarbeiter selbst Passwort und Einmalcode fest – kein
Passwort per Mail. Abgelaufen: `konten.sh einladen <benutzername>` schickt eine neue Einladung.

## Konten (`konten.sh`, in der Serverkonsole)

Ruft `kcadm.sh` im Keycloak-Container auf (`docker compose … exec -T keycloak`), ohne Browser und ohne SSH-Tunnel.
Startpasswörter werden einmal angezeigt; bei der ersten Anmeldung verlangt Keycloak eigenes Passwort und Einmalcode
(Pflichtaktionen im Realm). Benutzernamen wie im Eingabebereich (2–32 Zeichen, a–z, Ziffern, `.`, `-`, `_`).
Getestet gegen echtes Keycloak in `tests/oidc/test_oidc.py` (Abschnitt „Konten über die Serverkonsole“).
