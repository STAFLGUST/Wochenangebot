# ADR-007: Kundenseite in eigenem Container

**Status:** angenommen am 04.11.2026 (Inhaber). **Stufe 1** umgesetzt und eingespielt (PR #281), **Stufe 1b**
(Dienstkonto in Keycloak, Realm Stand 16) umgesetzt und eingespielt (PR #283), **Notzugang über einen SSH-Tunnel**
(Regel 6 der Zielarchitektur Kundenseite) umgesetzt – wirksam mit dem Release; **Stufe 2** (Daten) geplant.
**Anlass:** Sicherheitsdurchsicht vom 26.10.2026, Befund 5, und Durchsicht aus Kundensicht vom 04.11.2026 (ohne Befund,
aber mit diesem Restrisiko). Umsetzung der Vorgabe aus [ADR-003](adr-003-domains-anmeldung.md): Trennung
Kunden/Mitarbeiter; eine kompromittierte Anwendung darf nicht automatisch andere Fachbereiche öffnen.

Ergänzt die [Zielarchitektur](zielarchitektur.md) §1 und §3: Der Code bleibt ein modularer Monolith (ein Image, ein
API-Einstieg, gemeinsame Dienste). Getrennt wird nur der **Betrieb**: Die öffentliche Seite bekommt ihren eigenen Container.

## Ausgangslage

Bisher beantwortete ein Container `app` die öffentliche Seite `angebot-stafl.de`, die jeder ohne Anmeldung aufrufen kann,
**und** alle Mitarbeiter-Hosts. Der Name `app-mitarbeiter` war nur ein zweiter Netzwerkname desselben Containers. Darin
lagen gleichzeitig:

- alle Geheimnisse der Mitarbeiteranmeldung (je Host ein Keycloak-Client),
- das Dienstkonto `konten` (Keycloak-Rollen `view-users`, `manage-users`: Mitarbeiterkonten anlegen, Passwörter setzen),
- der Zugang zum Postfach,
- der vollständige Datenordner (Personal, Nutzer, Kunden mit Warenwirtschaftszahlen, Protokolle),
- eine Netzverbindung zu Keycloak.

Die Trennung im Code (GR-003, GR-104, GR-109) hält – die Durchsicht vom 04.11.2026 fand keine Lücke. Gäbe es aber
einmal eine Lücke, die Code im Prozess der öffentlichen Seite ausführt (zum Beispiel in einer künftigen PHP-Version), stünde
der Angreifer neben allem anderen.

## Entscheidung

### Stufe 1 – Prozesse, Geheimnisse und Netze trennen (umgesetzt)

| | `app` (Kundenseite) | `app-mitarbeiter` (Mitarbeiter-Hosts) |
| --- | --- | --- |
| Hosts | `angebot-stafl.de` | `dashboard-stafl.de`, `*.dashboard-stafl.de`, Prüfung vor der Anmeldeseite |
| Image und Code | `stafl-app` (baut dieser Dienst) | dasselbe Image, nie aus dem Netz geholt |
| Apache | nur Standard-Host, `mod_auth_openidc` nicht geladen | zusätzlich `apache-oidc.conf` (Keycloak-Hosts) |
| Geheimnisse | Postfach (für Bestellwünsche und Passwort-Links) | alle Anmelde-Geheimnisse, Dienstkonto `konten`, Postfach |
| Netz | `default` – nur mit Caddy | `intern` – mit Caddy und Keycloak |
| Dateisystem | nur lesbar; `/tmp` und `/run` im Speicher | wie bisher |
| Grenzen | `no-new-privileges`; CPU, Speicher, Prozesse (über `.env` anpassbar) | keine |
| Datenordner | gemeinsam (Stufe 1) | gemeinsam |

- Konfiguration: `deploy/anmeldung/docker-compose.anmeldung.yml` (aktiv über `COMPOSE_FILE` in `.env`). Ohne
  Ergänzungsdatei bleibt es bei einem Container wie bisher (lokale Entwicklung).
- Caddy bleibt unverändert: `angebot-stafl.de` → `app`, alle Mitarbeiter-Hosts → `app-mitarbeiter`. Caddy hängt zusätzlich
  im Netz `intern`; Keycloak hängt nur noch in `intern` und `anmeldung`.
- Der Server weist Mitarbeiter-Aktionen auf der Kundenseite schon heute ab (alter Eingabebereich stillgelegt, 410). Im
  eigenen Container fehlen dort zusätzlich die Keycloak-Hosts, die Geheimnisse und der Netzweg.
- **Notzugang** (`deploy/notzugang.sh`, Keycloak gestört): bis 04.11.2026 auf `angebot-stafl.de/admin/` im Container `app`,
  seitdem nur noch über einen SSH-Tunnel (Abschnitt „Notzugang über einen SSH-Tunnel“ unten). Die Kundenseite öffnet den
  alten Eingabebereich nie mehr. Konten der zentralen Anmeldung lassen sich im Notzugang nicht verwalten – im Notfall ist
  Keycloak ohnehin gestört.
- Geprüft in der CI: `deploy/anmeldung/pruefen.sh` (Konfiguration und echter Start beider Container: Netze, Umgebung,
  nur lesbares Dateisystem, Grenzen), `tests/deploy/test_freigabe.sh` (Release), `tests/deploy/test_datenbank_umschalten.sh`.

### Stufe 1b – Dienstkonto in Keycloak beschneiden (umgesetzt 04.11.2026, Realm Stand 16)

Stufe 1 nimmt das Dienstkonto aus dem öffentlich erreichbaren Prozess und aus dessen Netz. In Keycloak selbst hatte es bis
dahin `manage-users` für **alle** Konten des Realms `mitarbeiter` – wer sein Geheimnis erbeutete, konnte das Passwort jedes
Administrators setzen. Seit Stand 16 gilt:

- **Lesen** darf der Client `konten` alle Konten (`view-users`), damit die Verwaltung Zustand und Administratoren erkennt.
- **Ändern und anlegen** nur Konten der Gruppe `anwendungskonten` – feingranulare Verwaltungsrechte von Keycloak
  (Version 2, ab Keycloak 26.2): eine Regel „Dienstkonto der Anwendung (Client konten)“ und eine Berechtigung auf die Gruppe
  mit `view-members`, `manage-members`, `manage-membership`. Neue Konten legt der Client nur in dieser Gruppe an. Jemanden in
  die Gruppe aufnehmen oder daraus entfernen, Rollen vergeben oder sich als jemand anderes anmelden kann er nicht (geprüft
  mit echtem Keycloak 26.8.1, `tests/oidc/test_oidc.py`).
- **In der Gruppe** stehen genau die Konten der Mitarbeiter ohne Administratorrolle (verknüpft oder gleicher Benutzername) –
  nie Administratoren, nie Konten mit Verwaltungsrollen von Keycloak, nie Service-Accounts, nie Konten gelöschter Mitarbeiter.
  Den Abgleich macht nur die Serverkonsole: `sh deploy/anmeldung/konten.sh gruppe-abgleichen` (auch in
  `realm-aktualisieren`; `anlegen` und `einladen` nehmen neue Konten von Nicht-Administratoren gleich auf).
- **Die Anwendung** ändert Konten von Administratoren selbst dann nicht, wenn Keycloak es noch zuließe, legt für
  Administratoren keine Konten an und nennt in der Verwaltung stattdessen den Befehl der Serverkonsole.
- **Anmeldung:** Ein Administrator meldet sich nie mit einem Konto der Gruppe an (`lib/oidc.php`,
  `oidc_admin_konto_pruefen`). Sonst könnte, wer das Geheimnis hat, ein Konto mit dem Benutzernamen eines noch nicht
  verknüpften Administrators anlegen (die erste Anmeldung verknüpft über den Benutzernamen) oder das Passwort eines frisch
  beförderten Administrators setzen.
- **Folgen im Alltag:** Wird jemand Administrator (oder nicht mehr), danach `konten.sh gruppe-abgleichen <name>` – bis dahin
  meldet sich ein frisch beförderter Administrator nicht an, und die Verwaltung warnt. Passwort, Sperre und Einladung von
  Administratoren nur noch in der Konsole (`startpasswort`, `entsperren`, `einladen`). Der Notfallmodus meldet die
  Keycloak-Sitzungen anderer Administratoren nicht mehr ab (die Anwendung verlangt von ihnen trotzdem eine erneute Anmeldung).
  Alte Konten gelöschter Mitarbeiter außerhalb der Gruppe löscht nur `konten.sh verwaist --loeschen`.
- **Einführung:** nach Merge und Release einmal `sh deploy/anmeldung/konten.sh realm-aktualisieren` (Freigabe Inhaber). Die
  Reihenfolge darin schließt jede Lücke aus: erst Gruppe und Berechtigung, dann Abgleich, zuletzt `manage-users` entfernen.
  Neuer Code vor dem Konsolenschritt arbeitet wie bisher (ohne Gruppe keine Gruppenangabe beim Anlegen).
- **Rückweg:** `kc add-roles … manage-users` für den Service-Account von `konten` gibt den alten Zustand zurück
  (`docs/plattform/inbetriebnahme-anmeldung.md`); Gruppe, Regel und Berechtigung stören dann nicht.

### Notzugang über einen SSH-Tunnel (umgesetzt 04.11.2026)

Der alte Eingabebereich mit eigener Anmeldung ist der Notzugang, wenn Keycloak gestört ist. Bis dahin lag er auf der
Kundenseite: `notzugang.sh an` öffnete `angebot-stafl.de/admin/` im öffentlich erreichbaren Container `app` – für alle im
Internet, mit den alten Passwörtern. Seitdem:

- **Eigener Host im Container `app-mitarbeiter`:** Apache-Port 8090 (`deploy/anmeldung/apache-oidc.conf`), von Docker nur
  auf `127.0.0.1:${NOTZUGANG_PORT:-8190}` des Servers veröffentlicht – Caddy kennt ihn nicht. Erreichbar nur über einen
  SSH-Tunnel vom eigenen Rechner (`ssh -L 8190:127.0.0.1:8190 <benutzer>@<server>`, dann `http://localhost:8190/admin/`),
  wie die Keycloak-Verwaltung auf `127.0.0.1:8180`.
- **Offen nur mit `WA_NOTZUGANG=an`** in `.env` (`sh deploy/notzugang.sh an`, erstellt nur `app-mitarbeiter` neu);
  sonst antwortet der Host wie `angebot-stafl.de` (Mitarbeiteraktionen 410). `WA_EIGENE_ANMELDUNG` steht in beiden
  Anwendungs-Containern fest auf `aus`; eine frühere Zeile `WA_EIGENE_ANMELDUNG=an` in `.env` öffnet nichts mehr und
  entfernt `notzugang.sh` beim Umschalten.
- **Erkennung in der Anwendung:** `notzugang_host()` (`lib/oidc.php`) – der Webserver setzt `WA_NOTZUGANG_HOST` (nie aus
  Kopfzeilen), die Anfrage kommt direkt von einer internen Adresse (Docker-Netz des Tunnels) und ohne weitergereichte
  Besucheradresse. Nur dort gilt die **IP-Freigabe** des Eingabebereichs nicht: Die Besucheradresse ist die interne Adresse
  des Tunnels und stünde nie in der Liste; hinkommt ohnehin nur, wer sich am Server anmelden kann.
- **Nur http über den Tunnel:** Der Host nimmt `upgrade-insecure-requests` aus der Inhaltsrichtlinie (`.htaccess`), sonst
  holte der Browser Skripte über https; `localhost` gilt im Browser als sichere Umgebung (Cookies, Einmalcode).
  Passkeys der alten Anmeldung gehören zu `angebot-stafl.de` und gelten im Notzugang nicht – Passwort und Einmalcode schon.
- **Geprüft:** `tests/deploy/test_notzugang.sh` (Skript), `deploy/anmeldung/pruefen.sh` (echter Start: Port nur auf
  127.0.0.1, geschlossen/offen, Kundenseite bleibt zu, Kopfzeilen), `tests/oidc/test_oidc.py` (Anmeldung im Browser über
  http, keine Skriptfehler, IP-Freigabe-Ausnahme nur für diesen Host).
- **Rückfall:** Ein Release auf den Vorgänger stellt den alten Notzugang auf der Kundenseite wieder her (dann gilt wieder
  `WA_EIGENE_ANMELDUNG` in `.env`); `WA_NOTZUGANG` und `NOTZUGANG_PORT` werden dann ignoriert.

### Stufe 2 – Daten trennen (geplant)

- Die Kundenseite sieht nur noch, was sie braucht: veröffentlichtes Angebot, Angebotsliste, Kundenzugänge, Sitzungen,
  Merklisten, einen Eingang für Bestellwünsche und eine Liste ausverkaufter Artikelnummern (ohne Mengen).
- Das Kundendokument wird in **Zugangsdaten** und **Stammdaten mit Warenwirtschaftszahlen** geteilt – eine Datenmigration
  mit eigener Freigabe (GR-006).
- E-Mails verschickt nur noch die Mitarbeiterseite über den vorhandenen Postausgang; die Kundenseite kennt dann kein
  Postfach-Passwort mehr.
- Am besten zusammen mit PostgreSQL (Zielarchitektur §5, ADR-4): eigener Datenbanknutzer der Kundenseite mit Rechten nur
  auf Kundentabellen.

## Wirkung

| Wenn die Kundenseite geknackt würde | vorher | nach Stufe 1 | nach Stufe 2 |
| --- | --- | --- | --- |
| Personaldaten, Nutzer, Protokolle lesen | ja | ja (gemeinsamer Datenordner) | nein |
| Mitarbeiterkonten in Keycloak übernehmen | ja | nein (kein Geheimnis, kein Netzweg) | nein |
| Anmelde-Geheimnisse der Mitarbeiter-Hosts | ja | nein | nein |
| Postfach-Passwort | ja | ja | nein |
| Dateien der Anwendung verändern | nein (nur lesend) | nein | nein |
| Mitarbeiter-Hosts durch Überlast ausbremsen | ja | nein (Grenzen) | nein |

Unabhängig von der Kundenseite – mit erbeutetem Geheimnis des Dienstkontos `konten`: vor Stufe 1b jedes Konto des Realms
`mitarbeiter` übernehmbar, danach nur noch Konten ohne Administratorrolle; als Administrator anmelden kann sich damit
niemand (Stufe 1b).

## Alternativen

| Alternative | Bewertung |
| --- | --- |
| Nur das Dienstkonto beschneiden | sinnvoll und als Stufe 1b umgesetzt, ersetzt aber die Trennung nicht |
| Eigene Kunden-Anwendung mit eigenem Code | verworfen: Angebots- und Preislogik (`offer_resolve`) gäbe es doppelt und liefe auseinander |
| Container je Modul | verworfen (Zielarchitektur §1): vervielfacht Betrieb ohne Gewinn – die Grenze, die zählt, ist öffentlich ↔ intern |

## Betrieb

- **Einführung:** Mit dem Release ändert sich die Ergänzungsdatei – der Release-Modus erstellt dann wie bei jeder solchen
  Änderung alle Container neu (`docker compose up -d --force-recreate`); kein eigener Konsolenschritt. Keycloak startet dabei
  wegen des neuen Netzes neu (rund eine Minute keine neue Mitarbeiteranmeldung; laufende Sitzungen bleiben). Die Prüfung nach
  dem Einspielen fragt beim ersten Mal nur die Kundenseite ab (es läuft noch das Release-Skript des alten Stands); danach
  einmal `dashboard-stafl.de` aufrufen und anmelden.
- **Ab dem folgenden Release** prüft der Release-Modus nach dem Einspielen auch die Mitarbeiter-Hosts und kehrt zurück, wenn
  ihr Container nicht antwortet. Neues Image: beide Anwendungs-Container neu; nur `apache-oidc.conf`: nur `app-mitarbeiter`.
- **Rückfall:** Ein automatischer oder manueller Rückfall auf einen Stand vor ADR-007 lässt den Container `app-mitarbeiter`
  als verwaisten Container stehen (keine Wirkung, Caddy erreicht ihn dann nicht mehr). Aufräumen:
  `docker compose up -d --remove-orphans`.
- **Geänderte Anmelde-Werte in `.env`** liest die Anwendung nach `docker compose up -d app-mitarbeiter` (bisher `app`).
- **Speicher umschalten** (`deploy/datenbank-umschalten.sh`) stoppt beide Anwendungs-Container.
- **Ressourcen:** Server Hostinger KVM 8 (8 vCPU, 32 GB). Grenzen der Kundenseite: 3 CPU, 4 GB, 1024 Prozesse
  (`KUNDEN_CPUS`, `KUNDEN_SPEICHER` in `.env`). Der zweite Container braucht im Leerlauf rund 100–200 MB.
