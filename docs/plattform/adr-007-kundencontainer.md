# ADR-007: Kundenseite in eigenem Container

**Status:** angenommen am 04.11.2026 (Inhaber). **Stufe 1** in diesem Schritt umgesetzt (Betrieb erst mit Merge und
Release-Freigabe), **Stufe 1b** (Dienstkonto in Keycloak) und **Stufe 2** (Daten) geplant.
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
- **Notzugang** (`deploy/notzugang.sh`, Keycloak gestört): unverändert auf `angebot-stafl.de/admin/` im Container `app`.
  Konten der zentralen Anmeldung lassen sich dort nicht verwalten – im Notfall ist Keycloak ohnehin gestört.
- Geprüft in der CI: `deploy/anmeldung/pruefen.sh` (Konfiguration und echter Start beider Container: Netze, Umgebung,
  nur lesbares Dateisystem, Grenzen), `tests/deploy/test_freigabe.sh` (Release), `tests/deploy/test_datenbank_umschalten.sh`.

### Stufe 1b – Dienstkonto in Keycloak beschneiden (geplant, eigener Schritt)

Stufe 1 nimmt das Dienstkonto aus dem öffentlich erreichbaren Prozess und aus dessen Netz. In Keycloak selbst hat es
weiter `manage-users` für alle Konten des Realms `mitarbeiter`. Ziel: Rechte nur für die Konten, die die Verwaltung
wirklich ändern soll, nie für Administratorkonten. Weg: feingranulare Verwaltungsrechte von Keycloak (Version 2) statt
`manage-users`. Das braucht eine Prüfung mit echtem Keycloak in der CI und einen Konsolenschritt (`konten.sh
realm-aktualisieren`) mit Freigabe – deshalb ein eigener Pull Request.

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

## Alternativen

| Alternative | Bewertung |
| --- | --- |
| Nur das Dienstkonto beschneiden | sinnvoll und als Stufe 1b vorgesehen, ersetzt aber die Trennung nicht |
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
