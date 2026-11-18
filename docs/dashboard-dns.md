# STAFL-Dashboard: DNS und Caddy-Vorbereitung

Stand 21.10.2026. Die DNS-Verwaltung bei Hostinger zeigt für `dashboard-stafl.de` den A-Eintrag zum vorhandenen VPS. Die Subdomains `bestand`, `crm`, `rewe`, `qs`, `einkauf`, `verwaltung` und `test` sind als CNAME zum Dashboard eingetragen. Die Auflösung wurde vom VPS aus geprüft.

Dieser PR fügt **ausschließlich** Caddy-Hosts für die Domain und sieben Subdomains hinzu. Alle antworten vorerst mit HTTP 503 und einem einfachen Text „in Vorbereitung“, ohne Reverse Proxy zu den internen Anwendungen. Kein zusätzlicher Docker-Dienst und keine Anmeldung werden hier bereitgestellt. `www.dashboard-stafl.de` leitet auf die Hauptadresse weiter.

Die Kundenwebsite `angebot-stafl.de` behält ihren bestehenden Caddy-Siteblock (die Testadresse `test.angebot-stafl.de` ist am 15.11.2026 entfernt worden).

## Sicherheit und Freigabe

- Die DNS-Einträge allein stellen keine Mitarbeiteranmeldung bereit; 503-Platzhalter sind bewusst öffentlich lesbar, verraten aber keine internen Daten.
- `test.dashboard-stafl.de` ist nicht mehr im `Caddyfile` und stellt keine Testumgebung bereit (GR-111); eine Integrationsumgebung kommt später auf einer eigenen Testdomain (Roadmap 9).
- Caddy fordert erst beim späteren produktiven Einspielen für die neuen Hosts Zertifikate an. Öffentliche DNS-Auflösung und Erreichbarkeit auf Port 80/443 sind Voraussetzung.
- Bei GitHub `main` wurde ein neuerer Stand beobachtet als auf dem VPS. Ein Release würde neben diesem PR möglicherweise weitere freigegebene Commits einspielen. Vor Freigabe die Release-Differenz prüfen.
- Die produktive Änderung erfolgt ausschließlich über den vorhandenen freigabepflichtigen Release-Prozess. Dieser PR allein verändert den VPS nicht.
- Rückfall: vorherigen freigegebenen Release wiederherstellen; der neue DNS-Eintrag darf stehen bleiben.
- Keine Produktivdaten und keine Zugangsdaten im Repository.

## Weiterarbeit

Claude-/Plattform-Agenten sollen diese Hostnamen später durch echte Module ersetzen, **erst nachdem** Authentifizierung, Berechtigungen, Routing, Schutz vor unberechtigten API-Zugriffen, Integrationstests und die separate QS-Portal-Domain geklärt sind. `/eingabe/` liegt auf der bestehenden Angebotsdomain, nicht unter dem Dashboard. (Neue Empfehlung: Mitarbeiter-Eingabe unter `angebot.dashboard-stafl.de` mit eigener Sitzung, siehe `docs/plattform/adr-003-domains-anmeldung.md` – entschieden, noch nicht umgesetzt; DNS dafür fehlt noch.)

Status 21.10.2026: eingespielt (von außen geprüft: `dashboard-stafl.de` und Subdomains antworten mit 503). Welche Oberfläche
zu welchem Host gehört, steht jetzt in `regeln/module.toml`; die CI prüft Caddy-Hosts gegen das Register (GR-105).

Stand 25.10.2026 (Übersicht der DNS-Verwaltung vom Inhaber): CNAME → `dashboard-stafl.de` für `www`, `angebot`, `login`,
`verwaltung`, `bestand`, `hr`, `crm`, `marketing`, `rewe`, `qs`, `einkauf`, `controlling`, `leergut`, `container-import` und
`test`; A-Eintrag `@` zum VPS. Freigegeben (über Keycloak): `angebot`, `verwaltung`, `bestand`, `hr`, `crm`, `marketing`, später `sicherheit` (26.10.), `controlling` (28.10.)
`leergut` (29.10.2026), `rewe` (30.10.2026) und `qs` (Qualitätssicherung, Entscheidung des Inhabers 30.10.2026). 503-Platzhalter bis zur Freigabe (GR-105): `einkauf`, `test`.

Stand 13.11.2026: neue Adresse `versand.dashboard-stafl.de` (Modul Versand, freigegeben mit dem Merge). Der DNS-Eintrag
`versand` besteht noch nicht; weil der Server inzwischen hinter bunny.net steht (`docs/bunny-cdn.md`), gilt für ihn eine eigene
Reihenfolge – `docs/plattform/inbetriebnahme-versand.md`.

Stand 18.11.2026: `container-import.dashboard-stafl.de` freigegeben (Modul Container-Import · EUDR, Entscheidung des Inhabers,
produktiv mit dem Merge). Der DNS-Eintrag besteht seit 25.10.2026 und zeigt seit der Umstellung auf bunny.net auf die Zone
`stafl-dashboard-2`; am DNS ändert sich nichts – Ablauf: `docs/plattform/inbetriebnahme-containerimport.md`.
