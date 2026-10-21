# STAFL-Dashboard: DNS und Caddy-Vorbereitung

Stand 21.10.2026. Die DNS-Verwaltung bei Hostinger zeigt für `dashboard-stafl.de` den A-Eintrag zum vorhandenen VPS. Die Subdomains `bestand`, `crm`, `rewe`, `qs`, `einkauf`, `verwaltung` und `test` sind als CNAME zum Dashboard eingetragen. Die Auflösung wurde vom VPS aus geprüft.

Dieser PR fügt **ausschließlich** Caddy-Hosts für die Domain und sieben Subdomains hinzu. Alle antworten vorerst mit HTTP 503 und einem einfachen Text „in Vorbereitung“, ohne Reverse Proxy zu den internen Anwendungen. Kein zusätzlicher Docker-Dienst und keine Anmeldung werden hier bereitgestellt. `www.dashboard-stafl.de` leitet auf die Hauptadresse weiter.

Die Kundenwebsite `angebot-stafl.de` und `test.angebot-stafl.de` behalten ihre bestehenden Caddy-Siteblöcke.

## Sicherheit und Freigabe

- Die DNS-Einträge allein stellen keine Mitarbeiteranmeldung bereit; 503-Platzhalter sind bewusst öffentlich lesbar, verraten aber keine internen Daten.
- `test.dashboard-stafl.de` stellt **noch keine** integrierte Testumgebung bereit. Dafür sind später eigene isolierte Testdienste und ein Passwort-/Zugriffsschutz erforderlich.
- Caddy fordert erst beim späteren produktiven Einspielen für die neuen Hosts Zertifikate an. Öffentliche DNS-Auflösung und Erreichbarkeit auf Port 80/443 sind Voraussetzung.
- Bei GitHub `main` wurde ein neuerer Stand beobachtet als auf dem VPS. Ein Release würde neben diesem PR möglicherweise weitere freigegebene Commits einspielen. Vor Freigabe die Release-Differenz prüfen.
- Die produktive Änderung erfolgt ausschließlich über den vorhandenen freigabepflichtigen Release-Prozess. Dieser PR allein verändert den VPS nicht.
- Rückfall: vorherigen freigegebenen Release wiederherstellen; der neue DNS-Eintrag darf stehen bleiben.
- Keine Produktivdaten und keine Zugangsdaten im Repository.

## Weiterarbeit

Claude-/Plattform-Agenten sollen diese Hostnamen später durch echte Module ersetzen, **erst nachdem** Authentifizierung, Berechtigungen, Routing, Schutz vor unberechtigten API-Zugriffen, Integrationstests und die separate QS-Portal-Domain geklärt sind. `/eingabe/` liegt auf der bestehenden Angebotsdomain, nicht unter dem Dashboard. (Neue Empfehlung: Mitarbeiter-Eingabe unter `angebot.dashboard-stafl.de` mit eigener Sitzung, siehe `docs/plattform/adr-003-domains-anmeldung.md` – Entscheidung offen.)

Status 21.10.2026: eingespielt (von außen geprüft: `dashboard-stafl.de` und Subdomains antworten mit 503). Welche Oberfläche
zu welchem Host gehört, steht jetzt in `regeln/module.toml`; die CI prüft Caddy-Hosts gegen das Register (GR-105).
