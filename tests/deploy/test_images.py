#!/usr/bin/env python3
"""Container-Images fest über Digest (Sicherheitsdurchsicht 26.10.2026, Befund 12): jedes fremde Image in den Compose-Dateien
und im Dockerfile ist mit @sha256 festgelegt – ein Release holt so nie unbemerkt eine andere Fassung. Kundenseite,
Anwendungs-Image und Testumgebung nutzen dasselbe PHP-Grundimage; die CI prüft und scannt genau die eingetragenen Images."""
from pathlib import Path
import re

FEST = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")


def images(pfad):
    return [m.group(1) for m in re.finditer(r"^\s*image:\s*(\S+)", Path(pfad).read_text(encoding="utf-8"), re.MULTILINE)]


fehler = []
alle = {}
for pfad in ("docker-compose.yml", "deploy/anmeldung/docker-compose.anmeldung.yml", "deploy/testumgebung/docker-compose.yml"):
    for img in images(pfad):
        if img.startswith("stafl-app:"):   # selbst gebaut aus deploy/image (Grundimage dort fest)
            continue
        alle.setdefault(pfad, []).append(img)
        if not FEST.match(img):
            fehler.append(f"{pfad}: {img} nicht über Version und Digest festgelegt")

dockerfile = re.search(r"^FROM\s+(\S+)", Path("deploy/image/Dockerfile").read_text(encoding="utf-8"), re.MULTILINE).group(1)
if not FEST.match(dockerfile):
    fehler.append(f"deploy/image/Dockerfile: {dockerfile} nicht fest")

php = [i for i in alle.get("docker-compose.yml", []) if i.startswith("php:")]
test_php = [i for i in alle.get("deploy/testumgebung/docker-compose.yml", []) if i.startswith("php:")]
skript = re.search(r"^PHP_IMAGE=(\S+)", Path("deploy/testumgebung.sh").read_text(encoding="utf-8"), re.MULTILINE).group(1)
if not (php and php == test_php and php[0] == dockerfile and skript == dockerfile):
    fehler.append(f"PHP-Grundimage uneinheitlich: Kundenseite {php}, Testumgebung {test_php}/{skript}, Dockerfile {dockerfile}")

ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
for img in alle.get("deploy/anmeldung/docker-compose.anmeldung.yml", []):
    if f"docker pull -q {img}" not in ci:
        fehler.append(f"CI lädt {img} nicht in derselben Fassung (Auftrag „image“)")
if "caddy:2 " in ci or "caddy:2 " in Path("deploy/anmeldung/pruefen.sh").read_text(encoding="utf-8"):
    fehler.append("Caddy-Prüfung nutzt noch das gleitende caddy:2 statt der Fassung aus docker-compose.yml")
if "deploy/anmeldung/docker-compose.anmeldung.yml" not in ci.split("Container-Images auf bekannte Lücken prüfen")[1].split("\n\n")[0]:
    fehler.append("Trivy-Bericht scannt die Images der zentralen Anmeldung (Keycloak, PostgreSQL) nicht")

assert not fehler, "\n".join(fehler)
print(f"OK: {sum(len(v) for v in alle.values()) + 1} Images fest über Digest, PHP-Grundimage einheitlich, CI prüft dieselben Fassungen.")
