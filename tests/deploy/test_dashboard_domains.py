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
    "einkauf.dashboard-stafl.de",
]
block = site(", ".join(hosts))
assert 'respond "STAFL-Plattform: Dieser Bereich befindet sich in Vorbereitung." 503' in block
assert 'X-Robots-Tag "noindex, nofollow"' in block
assert 'Cache-Control "no-store"' in block
assert 'Strict-Transport-Security "max-age=31536000"' in block   # HTTPS-Pflicht auch für Platzhalter (Sicherheitsdurchsicht 26.10.2026)
for verboten in ("reverse_proxy", "file_server", "redir"):
    assert verboten not in block, verboten

# Anmeldung: nur Realm „mitarbeiter“ und statische Dateien an Keycloak, sonst 404 (Verwaltung, Master-Realm)
login = site("login.dashboard-stafl.de")
assert "@anmeldung path /realms/mitarbeiter/* /resources/*" in login
handle = re.search(r"\thandle @anmeldung \{\n(.*?)\n\t\}\n", login, re.DOTALL)
assert handle, "handle @anmeldung fehlt"
innen = handle.group(1)
# Keycloak als letztes Ziel; Besucher-IP wie bei der Anwendung (bunny.net, Abschnitt „cdn“), Schlüssel nie weiter
assert re.search(r"\treverse_proxy keycloak:8080 \{\n\t\t\theader_up X-Forwarded-For \{besucher_ip\}\n\t\t\theader_up -X-Stafl-Cdn\n\t\t\}$", innen.rstrip()), \
    "Keycloak muss das letzte Ziel sein"
assert login.count("reverse_proxy") == 1 and "\trespond 404\n" in login
assert "/admin" not in login and "master" not in login
# Vor jeder Seite der Anmeldung prüft die Anwendung Firewall, Länder- und IP-Sperre (forward_auth, Aktion anmeldung_pruefen);
# ausgenommen nur Dateien und die Abrufe der Anwendung selbst – nie die Seiten mit Passwort und Einmalcode
fa = re.search(r"forward_auth @seite app-mitarbeiter:80 \{\n(.*?)\n\t\t\}", innen, re.DOTALL)
assert fa, "forward_auth vor Keycloak fehlt"
assert "uri /api/index.php?action=anmeldung_pruefen" in fa.group(1)
for kopf in ("-Cookie", "-Authorization", "-Origin", "-Sec-Fetch-*"):
    assert f"header_up {kopf}" in fa.group(1), kopf   # Browser-Cookies und Herkunftsangaben gehen nicht an die Anwendung
assert re.search(r"@gesperrt status 403\s*handle_response @gesperrt \{\s*respond \"[^\"]+\" 403", fa.group(1))
assert re.search(r"@fehler status 4xx 5xx\s*handle_response @fehler \{\s*respond \"[^\"]+\" 503", fa.group(1))
seite = next(z for z in innen.splitlines() if z.strip().startswith("@seite "))
ausgenommen = seite.split("not path", 1)[1].split()
assert ausgenommen == ["/resources/*", "/realms/mitarbeiter/.well-known/*", "/realms/mitarbeiter/protocol/openid-connect/token",
                       "/realms/mitarbeiter/protocol/openid-connect/token/introspect", "/realms/mitarbeiter/protocol/openid-connect/certs",
                       "/realms/mitarbeiter/protocol/openid-connect/userinfo", "/realms/mitarbeiter/protocol/openid-connect/revoke"], ausgenommen
assert innen.index("forward_auth") < innen.index("reverse_proxy keycloak:8080")
# Kontokonsole von Keycloak nicht öffentlich (Härtung 03.11.2026)
assert "@konsole path /realms/mitarbeiter/account /realms/mitarbeiter/account/*" in innen and "respond @konsole 404" in innen
# Startseite des Anmelde-Hosts: zum Dashboard statt leerer 404-Seite (nur genau „/“)
assert "\tredir / https://dashboard-stafl.de/ 302\n" in login and login.index("redir /") < login.index("\trespond 404\n")
assert re.search(r"handle_errors 502 503 504 \{\s*respond \"[^\"]+\" 503", login)

# Dashboard, Mitarbeiter-Eingabe, Verwaltung, Bestand, HR, CRM, Marketing, Sicherheit, Controlling, Leergut, REWE, Qualitätssicherung, Versand und Container-Import (freigegeben): nur über den Netzwerknamen der App mit Keycloak-Hosts
mitarbeiter = site("dashboard-stafl.de, angebot.dashboard-stafl.de, verwaltung.dashboard-stafl.de, bestand.dashboard-stafl.de, hr.dashboard-stafl.de, crm.dashboard-stafl.de, marketing.dashboard-stafl.de, sicherheit.dashboard-stafl.de, controlling.dashboard-stafl.de, leergut.dashboard-stafl.de, rewe.dashboard-stafl.de, qs.dashboard-stafl.de, versand.dashboard-stafl.de, container-import.dashboard-stafl.de")
assert re.findall(r"reverse_proxy (\S+)", mitarbeiter) == ["app-mitarbeiter:80"]
assert "respond @private 404" in mitarbeiter and "Strict-Transport-Security" in mitarbeiter
assert "form-action 'self' https://login.dashboard-stafl.de" in mitarbeiter
assert "app-mitarbeiter" in ergaenzung and "app-mitarbeiter" not in basis and "keycloak" not in basis

# Kein anderer Siteblock erwähnt die Anmelde-Hosts; jeder Dashboard-Host genau einmal
for h in hosts + ["dashboard-stafl.de", "angebot.dashboard-stafl.de", "verwaltung.dashboard-stafl.de", "bestand.dashboard-stafl.de", "hr.dashboard-stafl.de", "crm.dashboard-stafl.de", "marketing.dashboard-stafl.de", "sicherheit.dashboard-stafl.de", "controlling.dashboard-stafl.de", "leergut.dashboard-stafl.de", "rewe.dashboard-stafl.de", "qs.dashboard-stafl.de", "versand.dashboard-stafl.de", "container-import.dashboard-stafl.de", "login.dashboard-stafl.de"]:
    kopfzeilen = [z for z in caddy.splitlines() if z.endswith("{") and not z.startswith(("\t", " ", "#"))]
    assert sum(1 for z in kopfzeilen if re.search(r"(?<![\w.-])" + re.escape(h) + r"(?![\w.-])", z)) == 1, h
assert caddy.count("app-mitarbeiter:80") == 2 and caddy.count("keycloak:8080") == 1   # Mitarbeiter-Hosts und Prüfung vor der Anmeldung

# HTTPS-Pflicht (HSTS, 1 Jahr) für jeden Dashboard-Host, auch für die Weiterleitung von www
for kopf in ("login.dashboard-stafl.de", "www.dashboard-stafl.de"):
    assert 'Strict-Transport-Security "max-age=31536000"' in site(kopf), kopf
assert 'Strict-Transport-Security "max-age=31536000"' in mitarbeiter

# Kundenportal behält seine separate Route; eine Testadresse gibt es nicht mehr (GR-111, 15.11.2026).
assert "{$DOMAIN}, www.{$DOMAIN} {" in caddy
assert "test.{$DOMAIN}" not in caddy and "test.dashboard-stafl.de" not in caddy
# Fremde Kartendienste (Satellitenbild, Wald 2020, Waldverlust): nur der Container-Import lässt sie zu, nur für Bilder und
# Abrufe, und genau die Adressen, die seine Karte nutzt (Entscheidung des Inhabers 18.11.2026).
karte_js = Path("app/module/containerimport/eudr-karte.js").read_text(encoding="utf-8")
genutzt = sorted(set(re.findall(r"['`](https://[a-z0-9.-]+)/", karte_js)))   # Adressen der Abrufe; Verweise der Quellenangaben stehen in href="…"
zuordnung = re.search(r"map \{host\} \{csp_karten\} \{\n\t\t(\S+) \"([^\"]*)\"\n\t\tdefault \"\"\n\t\}", caddy)
assert zuordnung, "Caddyfile: Zuordnung csp_karten fehlt"
assert zuordnung.group(1) == "container-import.dashboard-stafl.de", zuordnung.group(1)
assert sorted(zuordnung.group(2).split()) == genutzt == ["https://ies-ows.jrc.ec.europa.eu", "https://tiles.globalforestwatch.org", "https://tiles.maps.eox.at"], (zuordnung.group(2), genutzt)
assert caddy.count("map {host}") == 1 and caddy.count("{csp_karten}") == 3   # die Zuordnung selbst, img-src, connect-src
richtlinien = re.findall(r'Content-Security-Policy "([^"]+)"', caddy)
mit = [r for r in richtlinien if "{csp_karten}" in r]
assert len(mit) == 1 and "img-src 'self' data: blob:{csp_karten};" in mit[0] and "connect-src 'self'{csp_karten};" in mit[0] and "script-src 'self';" in mit[0], mit
for r in richtlinien:   # nirgends eine fremde Adresse fest eingetragen – außer der Anmeldung als Formularziel
    assert set(re.findall(r"https://[^\s;\"]+", r)) <= {"https://login.dashboard-stafl.de"}, r
assert "csp_karten" not in site("einkauf.dashboard-stafl.de") and "csp_karten" not in site("{$DOMAIN}, www.{$DOMAIN}")
# Kante setzt ihre Richtlinie nur als Vorgabe – Begründung im Caddyfile
gesetzt = re.findall(r'^\s*(\??)Content-Security-Policy "', caddy, re.M)
assert gesetzt and set(gesetzt) == {"?"}, "Caddyfile: Content-Security-Policy nur als Vorgabe setzen (?Content-Security-Policy)"

print("OK: ein Modul-Host ist 503-Platzhalter; Anmeldung (mit Prüfung vor jeder Seite), Dashboard, Mitarbeiter-Eingabe, Verwaltung, Bestand, HR, CRM, Marketing, Sicherheit, Controlling, Leergut, REWE, Qualitätssicherung, Versand und Container-Import nur mit der Ergänzungsdatei; fremde Kartendienste nur beim Container-Import.")
