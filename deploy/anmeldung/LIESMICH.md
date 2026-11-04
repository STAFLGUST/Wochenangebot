# Zentrale Anmeldung – Betriebskonfiguration

Vorbereitet für die Inbetriebnahme nach [docs/plattform/inbetriebnahme-anmeldung.md](../../docs/plattform/inbetriebnahme-anmeldung.md).
`docker-compose.yml` bleibt unverändert; aktiv wird die Ergänzungsdatei erst über `COMPOSE_FILE` in `.env` (Schritt 5).
Die öffentlichen Hosts stehen im `Caddyfile` (Schritt 6) und führen nur zu Zielen, die es ausschließlich mit der
Ergänzungsdatei gibt (`keycloak`, Container `app-mitarbeiter`) – ohne sie antworten sie mit 502. Seit ADR-007 laufen
Kundenseite (`app`) und Mitarbeiter-Hosts (`app-mitarbeiter`) in getrennten Containern aus demselben Image; nur
`app-mitarbeiter` kennt die Anmelde-Geheimnisse und erreicht Keycloak. E-Mails verschickt die Kundenseite nicht mehr selbst:
Sie legt Versandaufträge ab, der Dienst `postausgang` (gleiches Image, kein Port, eigenes Netz nur zum Postfach) verschickt
sie. Postfach-Zugangsdaten und den Schlüssel des hinterlegten Postfach-Passworts (`./daten-geheim`) haben nur
`app-mitarbeiter` und `postausgang` (ADR-007, Abschnitt „Postausgang von innen“).

| Datei | Inhalt |
| --- | --- |
| `docker-compose.anmeldung.yml` | Ergänzung zu `docker-compose.yml`: App mit dem Image aus `deploy/image` (mod_auth_openidc), Keycloak 26.8.1 und eigene PostgreSQL 17 – fest über Digest; Keycloak nur auf `127.0.0.1:8180`, Datenbank nur im internen Netz |
| `apache-oidc.conf` | Keycloak-Hosts `dashboard-stafl.de`, `angebot.dashboard-stafl.de`, `verwaltung.dashboard-stafl.de` (dort `/import/` → Importzentrale), `bestand.dashboard-stafl.de`, `hr.dashboard-stafl.de`, `sicherheit.dashboard-stafl.de` (`/` und `/admin/` → `/module/sicherheit/`), `controlling.dashboard-stafl.de` (`/` und `/admin/` → `/module/controlling/`), `leergut.dashboard-stafl.de` (`/` und `/admin/` → `/module/leergut/`), `rewe.dashboard-stafl.de` (`/` und `/admin/` → `/module/rewe/`), `qs.dashboard-stafl.de` (`/` und `/admin/` → `/module/qs/`) (`/` und `/admin/` → `/module/hr/`) , `crm.dashboard-stafl.de` (`/` und `/admin/` → `/module/crm/`) und `marketing.dashboard-stafl.de` (`/` und `/admin/` → `/module/marketing/`) (wie `tests/oidc/apache.conf`); je Host eigener Client, eigene Sitzung und `WA_OBERFLAECHE`; als `sites-enabled/zz-…` eingebunden, damit `angebot-stafl.de` Standard-Host bleibt |
| `realm-mitarbeiter.json` | Realm für den Betrieb, **erzeugt** von `werkzeuge/realm_produktion.py` aus dem Test-Realm (ohne Testnutzer, Geheimnisse als Platzhalter) – nicht von Hand ändern |
| `pruefen.sh` | Prüfung mit Docker (CI-Auftrag „Anwendungs-Image prüfen“) |
| `einrichten.sh` | Schritt 2: Geheimnisse in `.env` ergänzen, Realm-Import vorbereiten (startet nichts) |
| `app-abfrage.php` | von `konten.sh` im App-Container ausgeführt: Postfach der Anwendung (für den Mailversand von Keycloak) und ob es ein Mitarbeiterkonto gibt |
| `ruecksicherung-probe.sh` | Schritt 7: Rücksicherung der Keycloak-Sicherung in eine Probedatenbank üben (Konten zählen, danach löschen) |
| `konten.sh` | Schritt 4 und Betrieb: Konten in der Serverkonsole verwalten (Verwaltungskonto, anlegen, Startpasswort, zweiten Faktor zurücksetzen, Passkey, sperren, Liste, „Passwort vergessen“ ein/aus) |
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
Danach liest die Anwendung die neuen Werte erst nach `docker compose up -d app-mitarbeiter` (der Befehl weist darauf hin). Bis dahin
startet die Anwendung trotzdem (Compose nimmt für die Verwaltung den Schlüssel des Eingabebereichs; ohne Client in
Keycloak ist dort keine Anmeldung möglich).
Stand 4 (22.10.2026): Client `bestand` für `bestand.dashboard-stafl.de` – gleiches Vorgehen wie Stand 3 (`OIDC_SECRET_BESTAND`/
`OIDC_CRYPTO_BESTAND`, danach `docker compose up -d app-mitarbeiter`). Der Befehl geht jetzt alle Clients der Realm-Datei durch (fehlende
anlegen, Anmeldestärke und Claim `amr` einheitlich setzen) – ein künftiger Modul-Host braucht dort keine Codeänderung mehr.
Stand 5 (23.10.2026, Freigabe des Inhabers): Client `hr` für `hr.dashboard-stafl.de` (Urlaubsverwaltung) – gleiches Vorgehen
(`OIDC_SECRET_HR`/`OIDC_CRYPTO_HR`, danach `docker compose up -d app-mitarbeiter`). Voraussetzung: DNS-Eintrag `hr` (CNAME →
`dashboard-stafl.de`, wie `bestand.`/`login.`), sonst bekommt Caddy kein Zertifikat für den Host.
Stand 6 (23.10.2026, Freigabe des Inhabers): Client `crm` für `crm.dashboard-stafl.de` (CRM · Vertrieb) – gleiches Vorgehen
(`OIDC_SECRET_CRM`/`OIDC_CRYPTO_CRM`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `crm` besteht seit 21.10.2026.
Stand 7 (25.10.2026, Freigabe des Inhabers): Client `marketing` für `marketing.dashboard-stafl.de` (Marketing · Redaktionsplan) –
gleiches Vorgehen (`OIDC_SECRET_MARKETING`/`OIDC_CRYPTO_MARKETING`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `marketing` besteht seit 25.10.2026.
Stand 9 (26.10.2026, Freigabe des Inhabers): Client `sicherheit` für `sicherheit.dashboard-stafl.de` (Modul Sicherheit mit Notfallmodus) –
gleiches Vorgehen (`OIDC_SECRET_SICHERHEIT`/`OIDC_CRYPTO_SICHERHEIT`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `sicherheit` (CNAME) besteht seit 26.10.2026.

Stand 10 (28.10.2026, Freigabe des Inhabers): Client `controlling` für `controlling.dashboard-stafl.de` (Modul Controlling) – gleiches
Vorgehen (`OIDC_SECRET_CONTROLLING`/`OIDC_CRYPTO_CONTROLLING`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `controlling` (CNAME) besteht seit 25.10.2026.

Stand 11 (29.10.2026, Auftrag des Inhabers): Client `leergut` für `leergut.dashboard-stafl.de` (Modul Leergut) – gleiches Vorgehen
(`OIDC_SECRET_LEERGUT`/`OIDC_CRYPTO_LEERGUT`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `leergut` besteht seit 25.10.2026.

Stand 12 (30.10.2026, Auftrag des Inhabers): Client `rewe` für `rewe.dashboard-stafl.de` (Modul REWE · Vordisposition Dry Aged) – gleiches
Vorgehen (`OIDC_SECRET_REWE`/`OIDC_CRYPTO_REWE`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `rewe` besteht seit 21.10.2026.

Stand 13 (30.10.2026, Entscheidung des Inhabers „gleich produktiv“): Client `qs` für `qs.dashboard-stafl.de` (Modul Qualitätssicherung ·
QM-System) – gleiches Vorgehen (`OIDC_SECRET_QS`/`OIDC_CRYPTO_QS`, danach `docker compose up -d app-mitarbeiter`). Der DNS-Eintrag `qs` besteht seit 21.10.2026.

Stand 14 (03.11.2026, Härtung nach der Anmeldeprüfung): kein Client des Realms erlaubt den Passwort-Grant, auch keiner der
Clients, die Keycloak selbst anlegt – Anmeldungen laufen nur über die Anmeldeseite. Einmal auf dem Server ausführen:
`sh deploy/anmeldung/konten.sh realm-aktualisieren` (kein Neustart nötig; die Ausgabe nennt jeden umgestellten Client).
Ab diesem Stand sperrt das Caddyfile außerdem Keycloaks Kontokonsole (`/realms/mitarbeiter/account`, 404) – Konten pflegt
die Verwaltung.

Stand 15 (04.11.2026, Auftrag des Inhabers): Passwortregeln und Kontosperre der zentralen Anmeldung kommen aus der
Anwendung (Sicherheit → Einstellungen → Anmeldung und Passwörter): Mindestlänge (nie unter 12), „gemischte Zeichen“ (dann
Groß-, Kleinbuchstabe und Ziffer), Sperre nach Fehlversuchen und deren Dauer je Konto; weiter wie bisher: nicht Benutzername
oder E-Mail, keins der letzten 3 Passwörter. Übernehmen mit `sh deploy/anmeldung/konten.sh richtlinien` (läuft auch in
`realm-aktualisieren`; zeigt die übernommenen Werte, zweiter Lauf „aktuell“) – nach jeder Änderung dieser Einstellungen
einmal ausführen. Bestehende Passwörter bleiben gültig. Die Anwendung bekommt dafür keine zusätzlichen Rechte in Keycloak.
Außerdem löscht die Anwendung beim Löschen eines Mitarbeiters dessen Konto in Keycloak mit. Konten gelöschter Mitarbeiter aus
der Zeit davor (oder wenn Keycloak beim Löschen nicht erreichbar war): `sh deploy/anmeldung/konten.sh verwaist` zeigt sie
(nur lesen), `sh deploy/anmeldung/konten.sh verwaist --loeschen` löscht genau diese Konten. Rückweg: Werte in den
Einstellungen ändern und `richtlinien` erneut ausführen.

Stand 8 (26.10.2026, Wunsch des Inhabers „ein Passwort“): Client `konten` – kein Host, nur ein Service-Account, mit dem die
Verwaltung (Verwaltung → Mitarbeiter → „Zentrale Anmeldung“, nur Administratoren, immer mit Bestätigung) Passwörter setzt,
Sperren nach Fehlversuchen aufhebt, den Link zum Passwort-Festlegen schickt und fehlende Konten anlegt
(`app/api/lib/anmeldekonten.php`). Rechte seit Stand 16 (ADR-007 Stufe 1b): lesen `view-users`, ändern und anlegen nur
Konten der Gruppe `anwendungskonten` (feingranulare Verwaltungsrechte) – keine Realm-, Client- oder Rollenverwaltung, kein
Anmelden im Namen anderer, kein Passwort-Grant; `realm-aktualisieren` entfernt zusätzliche Rollen (auch das frühere
`manage-users`). Legt `OIDC_SECRET_KONTEN` in `.env` an (nie angezeigt); danach `docker compose up -d app-mitarbeiter`. Die Anwendung
spricht Keycloak im internen Netz an (`WA_KONTEN_URL=http://keycloak:8080`, nicht über Caddy). Ohne das Geheimnis zeigt die
Verwaltung „noch nicht eingerichtet“ – sonst ändert sich nichts. Rückweg: Client `konten` in Keycloak deaktivieren oder die
Zeile `OIDC_SECRET_KONTEN` aus `.env` entfernen und `docker compose up -d app-mitarbeiter`.

Stand 16 (04.11.2026, ADR-007 Stufe 1b): Die Verwaltung der Anwendung ändert nur noch Konten der Gruppe
`anwendungskonten` – das sind die Konten der Mitarbeiter **ohne** Administratorrolle. Administratoren, Konten mit
Verwaltungsrollen von Keycloak und Service-Accounts stehen nie darin. `realm-aktualisieren` legt Gruppe, Regel
„Dienstkonto der Anwendung (Client konten)“ und Berechtigung „Anwendung verwaltet Mitarbeiterkonten (Gruppe
anwendungskonten)“ an, gleicht die Gruppe ab und entfernt erst danach `manage-users`. Danach:

- `sh deploy/anmeldung/konten.sh gruppe-abgleichen [<benutzername>]` – nach jeder Beförderung zum Administrator (oder
  Rückstufung). Bis dahin meldet sich ein frisch beförderter Administrator nicht an (Hinweis mit diesem Befehl), und die
  Verwaltung warnt in „Zentrale Anmeldung“.
- Administratoren: Passwort, Sperre und Einladung nur hier (`startpasswort`, `entsperren`, `einladen`); die Verwaltung zeigt
  den Befehl statt der Knöpfe. `anlegen` und `einladen` nehmen neue Konten von Nicht-Administratoren gleich in die Gruppe.
- Altes Konto eines gelöschten Mitarbeiters außerhalb der Gruppe: `verwaist --loeschen`, dann in der Verwaltung „Konto anlegen“.
- Rückweg: `kcadm.sh add-roles -r mitarbeiter --uusername service-account-konten --cclientid realm-management --rolename
  manage-users` (über `docker compose exec keycloak /opt/keycloak/bin/kcadm.sh …` mit dem Verwaltungskonto) – die Anwendung
  arbeitet dann wieder wie vor Stand 16 (Administratoren lehnt sie weiter selbst ab).

## Alter Eingabebereich (angebot-stafl.de/admin/) stillgelegt

Seit dem 23.10.2026 setzt diese Datei `WA_EIGENE_ANMELDUNG=aus`: Auf dem Host ohne zentrale Anmeldung gibt es keine
Mitarbeiteranmeldung, keine Mitarbeitersitzung und keine Mitarbeiteraktion mehr (Antwort 410 `umgezogen` mit `ziel`,
`/admin/` zeigt einen Hinweis und leitet nach `angebot.dashboard-stafl.de/admin/` weiter). Unverändert: Kundenseite,
öffentliches Angebot, Kundenanmeldung und -bestellungen, `status` (Healthcheck), `logout`. Mails an Mitarbeiter
verweisen auf die neue Adresse (`WA_EINGABE_ADRESSE`, Standard `https://angebot.dashboard-stafl.de/admin/`).

Notzugang bei gestörter Anmeldung (seit 04.11.2026 nur über einen SSH-Tunnel, ADR-007): `sh deploy/notzugang.sh an` setzt
`WA_NOTZUGANG=an` in `.env` und erstellt `app-mitarbeiter` neu. Erreichbar ist er nur auf `127.0.0.1` des Servers
(`NOTZUGANG_PORT`, Standard 8190) – vom eigenen Rechner `ssh -L 8190:127.0.0.1:8190 <benutzer>@<server>`, dann im Browser
`http://localhost:8190/admin/` (bisherige Passwörter der Anwendung; Passkeys der alten Anmeldung gelten dort nicht, Einmalcode
schon). Die IP-Freigabe des Eingabebereichs gilt im Notzugang nicht. Danach `sh deploy/notzugang.sh aus`. Die Kundenseite
öffnet den alten Eingabebereich nicht mehr; eine frühere Zeile `WA_EIGENE_ANMELDUNG=an` wirkt nicht und wird beim Umschalten
entfernt.

## Postausgang (E-Mails der Kundenseite)

Seit dem Postausgang von innen (ADR-007) legt die Kundenseite Bestellwünsche, Benachrichtigungen und Abmeldehinweise nur als
Auftrag ab; der Dienst `postausgang` verschickt sie alle paar Sekunden. Einmalig nach dem Release, das ihn einführt:

```sh
sh deploy/postfach-schluessel.sh umziehen   # Schlüssel nach daten-geheim, hinterlegte Passwörter an Server/Benutzer binden
sh deploy/postfach-schluessel.sh status     # Kontrolle
```

Zustand: `docker compose ps postausgang` („healthy“), Protokoll: `docker compose logs postausgang`. Läuft der Dienst länger als
15 Minuten nicht, nimmt das Portal keine Bestellwünsche an (sonst blieben sie unbemerkt liegen). Nicht zugestellte Mails stehen
wie bisher in den Bestellwünschen zum Nachsenden. Vor einem Rückfall auf ein älteres Release: `sh deploy/postfach-schluessel.sh
zurueck` (Passwörter zurück auf das alte Format, Schlüssel zurück in den Datenordner), danach
`docker compose up -d --remove-orphans`.

## Daten trennen (ADR-007 Stufe 2a)

Mit dem Release ändert sich noch nichts: `app-mitarbeiter` und `postausgang` binden `./daten-intern` ein, nutzen ihn aber erst
nach dem Serverschritt (nur mit Freigabe des Inhabers, im Wartungsfenster – die Anwendung steht dabei kurz):

```sh
sh deploy/daten-trennen.sh status            # Plan: welche internen Dokumente umziehen (ändert nichts)
sh deploy/daten-trennen.sh trennen           # Sicherung → Stopp → trennen → Start
```

Danach sieht die Kundenseite Personal, Mitarbeiterkonten, CRM, Controlling, QS-Dokumente usw. nicht mehr. Sicherungen enthalten
zusätzlich `intern-<Zeit>.tar.gz`. Vor einem Rückfall auf ein Release vor der Trennung: `sh deploy/daten-trennen.sh zusammenfuehren`.

## Design der Anmeldeseite und der E-Mails

Keycloak liest das Theme aus `deploy/anmeldung/theme/stafl` (Volume in `docker-compose.anmeldung.yml`, nur lesend):
`login/` für die Anmeldeseite, `email/` für die Einladung bzw. den Link zum Passwort-Festlegen (Vorlage `executeActions`)
und „Passwort vergessen“ (Vorlage `password-reset`; gleicher Stil wie die Plattform-Mails, keine Bilder). Aktiv wird es erst mit `sh deploy/anmeldung/konten.sh design-setzen`
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

## Passwort vergessen (konten.sh passwort-vergessen)

Seit 03.11.2026 (Wunsch des Inhabers) kann ein Mitarbeiter sein Passwort selbst zurücksetzen: Anmeldeseite → „Passwort
vergessen?“ → Benutzername → Mail mit Link (15 Minuten gültig, einmal verwendbar, Vorlage `password-reset` im
Plattform-Design). Die Bestätigung ist neutral (verrät nicht, ob es den Benutzernamen gibt); ohne hinterlegte E-Mail-Adresse
kommt keine Mail.

Sicherheit: Keycloaks eingebauter Ablauf „reset credentials“ enthält „Reset OTP“ – er entfernt den Einmalcode, wer an das
Postfach kommt, könnte dann ein Administratorkonto samt zweitem Faktor übernehmen. `konten.sh passwort-vergessen an` legt
deshalb den eigenen Ablauf `mitarbeiter-passwort-vergessen` an (Benutzer wählen → Mail → **Passkey bzw. Einmalcode, wenn
eingerichtet** → neues Passwort; kein „Reset OTP“) und setzt ihn als Ablauf zum Zurücksetzen. Einmalcode und Passkeys
bleiben, die Anmeldemethode (amr `otp`/`hwk`) wird gemeldet – Pflicht-Konten kommen danach ohne zweite Code-Abfrage ins
Dashboard. Der Befehl prüft den Aufbau: weicht der Ablauf ab (von Hand geändert), schaltet er nicht ein.

```sh
sh deploy/anmeldung/konten.sh passwort-vergessen status   # an/aus, Ablauf abgesichert?, Mailversand eingerichtet?
sh deploy/anmeldung/konten.sh passwort-vergessen an       # Voraussetzung: konten.sh mail-einrichten
sh deploy/anmeldung/konten.sh passwort-vergessen aus      # Rückweg: Link weg, Ablauf bleibt
```

Neue Installationen bekommen Ablauf, Link-Gültigkeit und `resetPasswordAllowed` über `realm-mitarbeiter.json`; die CI
vergleicht den von `konten.sh` angelegten Ablauf mit der Datei (`tests/oidc/test_oidc.py`).
