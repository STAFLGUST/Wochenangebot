# Testumgebung `test.<Domain>`

Eine zweite, vollständig getrennte Instanz auf demselben Server zum Durchklicken neuer Funktionen **vor** dem Release.

| | Echtbetrieb | Testumgebung |
| --- | --- | --- |
| Adresse | `https://<Domain>` | `https://test.<Domain>` (zusätzlicher Passwortschutz, keine Suchmaschinen) |
| Ordner | `/opt/wochenangebot` | `/opt/wochenangebot-test` (`src/` Code, `daten/` Testdaten) |
| Code-Stand | freigegebenes Release | beliebiger GitHub-Zweig, von Hand eingespielt |
| Daten | echte Daten | nur Testdaten aus `tests/fixtures` (nie echte Daten kopieren) |
| E-Mails | Versand | **kein Versand** – alles landet im „Testpostfach“ (Verwaltung → E-Mail) |
| Kennzeichen | – | Streifen „TESTUMGEBUNG“ unten auf jeder Seite |

Der Echtbetrieb wird nicht verändert: Sein Caddy leitet `test.<Domain>` nur an den Container `app-test` weiter.
Läuft die Testumgebung nicht, ist nur `test.<Domain>` nicht erreichbar.

## Einmalig einrichten

1. DNS: A-Eintrag `test` → IP des Servers (Hostinger → Domains → DNS).
2. Release mit dieser Funktion einspielen (enthält den Eintrag für `test.<Domain>` im `Caddyfile`).
3. Auf dem Server im Ordner des Echtbetriebs: `sh deploy/testumgebung.sh einrichten`
   – fragt Benutzername/Passwort für den Zugang zur Testumgebung (wird nur als Hash gespeichert).
4. `https://test.<Domain>` öffnen → Zugangsdaten → Ersteinrichtung (eigener Test-Administrator).

## Benutzen

- Zweig einspielen: `sh deploy/testumgebung.sh einspielen feature/xyz` (oder `main`). Nur Zweige des eigenen
  Repositorys, keine fremden Forks. Testdaten bleiben erhalten.
- Testdaten neu: `sh deploy/testumgebung.sh zuruecksetzen` (danach wieder Ersteinrichtung).
- Zugangspasswort ändern: `sh deploy/testumgebung.sh passwort`
- Übersicht/Start/Stopp: `sh deploy/testumgebung.sh status | starten | stoppen`
- Bestandsliste zum Ausprobieren: `tests/fixtures/bestand/bestand.xls` (Testdaten) im Eingabebereich importieren.

## Sicherheit

- Ganze Seite hinter Benutzername/Passwort (Apache im Test-Container, `deploy/testumgebung/apache-schutz.conf`),
  zusätzlich zu den Anmeldungen der Anwendung; `X-Robots-Tag: noindex`.
- `WA_TESTUMGEBUNG=1`: E-Mails gehen nie an einen Mailserver (auch nicht, wenn dort ein Postfach eingetragen wird),
  sondern ins Testpostfach (die letzten 100).
- Keine Zugangsdaten oder Daten des Echtbetriebs werden übernommen (nur `DOMAIN` für die Adresse).

## Hinweis für Wartungsarbeiten

Der Test-Container hängt nur im Netz `wochenangebot-edge`, das der Echtbetrieb für Caddy anlegt – nicht im Netz der
Produktiv-App. Code aus einem Testzweig erreicht die Produktiv-App also nicht direkt, und die App übernimmt die
Besucher-IP (`X-Forwarded-For`) nur von Caddy (`WA_TRUSTED_PROXIES`). Ein manuelles `docker compose down` im
Echtbetrieb scheitert, solange die Testumgebung läuft – vorher `sh deploy/testumgebung.sh stoppen`. Releases sind
davon nicht betroffen (sie verwenden kein `down`).

**Umstellung (einmalig nach dem Release mit dem Netz `wochenangebot-edge`):** Das Release erstellt Caddy und App neu und
legt das Netz an. Danach im Ordner des Echtbetriebs `sh deploy/testumgebung.sh einspielen main` (oder den gewünschten
Zweig) – der Test-Container wird dabei neu erstellt und wechselt ins neue Netz. Bis dahin läuft er unverändert weiter.
