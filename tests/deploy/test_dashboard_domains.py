#!/usr/bin/env python3
"""Dashboard-Hosts: Modul-Hosts bleiben 503-Platzhalter bis zur Freigabe (GR-105); die Hosts der zentralen Anmeldung
(ADR-003, Inbetriebnahme Schritt 6) führen nur zu Zielen, die es ausschließlich mit der Ergänzungsdatei
deploy/anmeldung/docker-compose.anmeldung.yml gibt – nie zur Anwendung ohne Keycloak-Anmeldung."""
from pathlib import Path
import re

caddy = Path("Caddyfile").read_text(encoding="utf-8")
ergaenzung = Path("deploy/anmeldung/docker-compose.anmeldung.yml").read_text(encoding="utf-8")
basis = Path("docker-compose.yml").read_text(encoding="utf-8")


def site(kopf):
    m = re.search(r"^" + re.escape(kopf) + r" \{\n.*?\n\}", caddy, re.MULTILINE | re.DOTALL)
    assert m, f"Siteblock fehlt: {kopf}"
    return m.group(0)


hosts = [
    "crm.dashboard-stafl.de",
    "rewe.dashboard-stafl.de",
    "qs.dashboard-stafl.de",
    "einkauf.dashboard-stafl.de",
    "test.dashboard-stafl.de",
]
block = site(", ".join(hosts))
assert 'respond "STAFL-Plattform: Dieser Bereich befindet sich in Vorbereitung." 503' in block
assert 'X-Robots-Tag "noindex, nofollow"' in block
assert 'Cache-Control "no-store"' in block
for verboten in ("reverse_proxy", "file_server", "redir"):
    assert verboten not in block, verboten

# Anmeldung: nur Realm „mitarbeiter“ und statische Dateien an Keycloak, sonst 404 (Verwaltung, Master-Realm)
login = site("login.dashboard-stafl.de")
assert "@anmeldung path /realms/mitarbeiter/* /resources/*" in login
assert re.search(r"handle @anmeldung \{\s*reverse_proxy keycloak:8080\s*\}", login)
assert login.count("reverse_proxy") == 1 and login.rstrip("}").rstrip().endswith("respond 404")
assert "/admin" not in login and "master" not in login

# Dashboard, Mitarbeiter-Eingabe, Verwaltung, Bestand und HR (freigegeben): nur über den Netzwerknamen der App mit Keycloak-Hosts
mitarbeiter = site("dashboard-stafl.de, angebot.dashboard-stafl.de, verwaltung.dashboard-stafl.de, bestand.dashboard-stafl.de, hr.dashboard-stafl.de")
assert re.findall(r"reverse_proxy (\S+)", mitarbeiter) == ["app-mitarbeiter:80"]
assert "respond @private 404" in mitarbeiter and "Strict-Transport-Security" in mitarbeiter
assert "form-action 'self' https://login.dashboard-stafl.de" in mitarbeiter
assert "app-mitarbeiter" in ergaenzung and "app-mitarbeiter" not in basis and "keycloak" not in basis

# Kein anderer Siteblock erwähnt die Anmelde-Hosts; jeder Dashboard-Host genau einmal
for h in hosts + ["dashboard-stafl.de", "angebot.dashboard-stafl.de", "verwaltung.dashboard-stafl.de", "bestand.dashboard-stafl.de", "hr.dashboard-stafl.de", "login.dashboard-stafl.de"]:
    kopfzeilen = [z for z in caddy.splitlines() if z.endswith("{") and not z.startswith(("\t", " ", "#"))]
    assert sum(1 for z in kopfzeilen if re.search(r"(?<![\w.-])" + re.escape(h) + r"(?![\w.-])", z)) == 1, h
assert caddy.count("app-mitarbeiter:80") == 1 and caddy.count("keycloak:8080") == 1

# Kundenportal und vorhandene Testumgebung behalten ihre separaten Routen.
assert "{$DOMAIN}, www.{$DOMAIN} {" in caddy
assert "test.{$DOMAIN} {" in caddy
print("OK: fünf Modul-Hosts sind 503-Platzhalter; Anmeldung, Dashboard, Mitarbeiter-Eingabe, Verwaltung, Bestand und HR nur mit der Ergänzungsdatei.")
