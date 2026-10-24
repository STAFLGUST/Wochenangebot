#!/usr/bin/env python3
"""Lokaler Entwicklungsserver mit Testdaten – wie ein Testserver der E2E-Suite, aber zum Ausprobieren im Browser.

  python3 werkzeuge/lokal.py                  http://127.0.0.1:8080 mit Testdaten (tests/fixtures/data-seed)
  python3 werkzeuge/lokal.py --port 8090 --leer --sqlite

Legt eine Kopie von app/ in tests/.arbeit/lokal/ an (Versionsnummern und Prüfliste wie auf dem Server,
deploy/bereitstellen.py), blendet das Dashboard unter /dashboard/ ein, setzt den Zugang „admin“ mit dem Passwort aus
--passwort (Standard: das Testpasswort der E2E-Suite) und startet `php -S`. Nur Testdaten, nie echte Daten (GR-007);
Änderungen an app/ wirken erst nach einem Neustart (neue Kopie). Beenden mit Strg+C.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = REPO / "tests" / ".arbeit" / "lokal"
GUARD = "<?php http_response_code(404); exit; ?>\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--passwort", default="Sicheres-Passwort-1", help="Passwort des Zugangs „admin“ (nur lokal)")
    ap.add_argument("--leer", action="store_true", help="ohne Beispieldaten (tests/fixtures/data-seed-clean)")
    ap.add_argument("--sqlite", action="store_true", help="Speicher SQLite statt Dateien (wie WA_TEST_STORAGE=sqlite)")
    a = ap.parse_args(argv)

    if shutil.which("php") is None:
        print("PHP 8.3 (CLI) fehlt – siehe docs/entwickler/01-schnellstart.md")
        return 1
    app = WORK / "app"
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.copytree(REPO / "app", app)
    spec = importlib.util.spec_from_file_location("bereitstellen", REPO / "deploy" / "bereitstellen.py")
    bereitstellen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bereitstellen)
    bereitstellen.verzeichnis(app)                       # ?v=… und Prüfliste wie beim Einspielen
    shutil.copytree(REPO / "dashboard", app / "dashboard")  # Dashboard (auf dem Server ein eigener Alias)
    daten = app / "data"
    shutil.rmtree(daten)
    shutil.copytree(REPO / "tests" / "fixtures" / ("data-seed-clean" if a.leer else "data-seed"), daten)
    h = subprocess.run(["php", "-r", "echo password_hash($argv[1], PASSWORD_DEFAULT);", a.passwort],
                       capture_output=True, text=True, check=True).stdout
    (daten / "admin.php").write_text(GUARD + json.dumps({"hash": h, "created": "2026-10-01T00:00:00Z"}), encoding="utf-8")
    if a.sqlite:
        subprocess.run([sys.executable, str(REPO / "deploy" / "datenbank.py"), "migrate", str(daten), "--offline"], check=True)
    sitzungen = WORK / "sitzungen"
    sitzungen.mkdir(parents=True, exist_ok=True)
    adresse = f"http://127.0.0.1:{a.port}"
    print(f"Kundenseite {adresse}/ · Eingabebereich {adresse}/admin/ (admin / {a.passwort}) · Dashboard {adresse}/dashboard/")
    print("Ohne zentrale Anmeldung (Keycloak): Mitarbeiter melden sich hier mit Passwort an. Beenden mit Strg+C.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MAIL_")}
    try:
        return subprocess.call(["php", "-d", f"session.save_path={sitzungen}", "-S", f"127.0.0.1:{a.port}"], cwd=app, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
