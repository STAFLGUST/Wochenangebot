#!/usr/bin/env python3
"""Dashboard-Hosts dürfen vor Freigabe keine interne Anwendung ausliefern."""
from pathlib import Path
import re

caddy = Path("Caddyfile").read_text(encoding="utf-8")
hosts = [
    "dashboard-stafl.de",
    "bestand.dashboard-stafl.de",
    "crm.dashboard-stafl.de",
    "rewe.dashboard-stafl.de",
    "qs.dashboard-stafl.de",
    "einkauf.dashboard-stafl.de",
    "verwaltung.dashboard-stafl.de",
    "test.dashboard-stafl.de",
]
for host in hosts:
    assert re.search(r"(?<![\w.-])" + re.escape(host) + r"(?![\w.-])", caddy), host

block = re.search(
    r"^dashboard-stafl\.de, bestand\.dashboard-stafl\.de, .*?\n\}",
    caddy,
    re.MULTILINE | re.DOTALL,
)
assert block, "Platzhalter-Siteblock fehlt"
assert all(host in block.group(0) for host in hosts)
assert 'respond "STAFL-Plattform: Dieser Bereich befindet sich in Vorbereitung." 503' in block.group(0)
assert 'X-Robots-Tag "noindex, nofollow"' in block.group(0)
assert 'Cache-Control "no-store"' in block.group(0)
assert "reverse_proxy" not in block.group(0)
assert "file_server" not in block.group(0)
assert "redir" not in block.group(0)

# Kundenportal und vorhandene Testumgebung behalten ihre separaten Routen.
assert "{$DOMAIN}, www.{$DOMAIN} {" in caddy
assert "test.{$DOMAIN} {" in caddy
print("OK: acht Dashboard-Hosts sind isolierte 503-Platzhalter.")
