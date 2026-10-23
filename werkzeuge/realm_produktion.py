#!/usr/bin/env python3
"""Realm „mitarbeiter“ für den Betrieb aus dem geprüften Test-Realm erzeugen (eine Quelle, kein Auseinanderlaufen).

    python3 werkzeuge/realm_produktion.py            # schreibt deploy/anmeldung/realm-mitarbeiter.json
    python3 werkzeuge/realm_produktion.py --pruefen  # CI: Datei aktuell?

Grundlage ist tests/oidc/realm-mitarbeiter.json – dieselben Richtlinien, Abläufe und Clients, die der CI-Auftrag
„Anmeldung über Keycloak“ prüft. Für den Betrieb werden nur die Adressen ersetzt (*.stafl.test:8443 → die echten Hosts)
und die Testnutzer entfernt; Mitarbeiter legt der Administrator in Keycloak an (docs/plattform/inbetriebnahme-anmeldung.md).
Client-Geheimnisse bleiben Platzhalter (@GEHEIM_…@) und werden erst auf dem Server eingesetzt – nie im Repository.
"""
import json
import pathlib
import sys

WURZEL = pathlib.Path(__file__).resolve().parents[1]
QUELLE = WURZEL / 'tests' / 'oidc' / 'realm-mitarbeiter.json'
ZIEL = WURZEL / 'deploy' / 'anmeldung' / 'realm-mitarbeiter.json'
HOSTS = {'https://dashboard.stafl.test:8443': 'https://dashboard-stafl.de',
         'https://angebot.stafl.test:8443': 'https://angebot.dashboard-stafl.de',
         'https://verwaltung.stafl.test:8443': 'https://verwaltung.dashboard-stafl.de',
         'https://bestand.stafl.test:8443': 'https://bestand.dashboard-stafl.de',
         'https://hr.stafl.test:8443': 'https://hr.dashboard-stafl.de'}


def ersetzen(wert):
    if isinstance(wert, str):
        for alt, neu in HOSTS.items():
            wert = wert.replace(alt, neu)
        if 'stafl.test' in wert:
            raise SystemExit(f'Testadresse ohne Zuordnung: {wert}')
        return wert
    if isinstance(wert, list):
        return [ersetzen(x) for x in wert]
    if isinstance(wert, dict):
        return {k: ersetzen(v) for k, v in wert.items()}
    return wert


def erzeugen() -> str:
    r = json.loads(QUELLE.read_text(encoding='utf-8'))
    r.pop('users', None)                       # keine Testnutzer im Betrieb
    r['displayName'] = 'STAFL-Plattform'
    r = ersetzen(r)
    for c in r.get('clients', []):
        if not str(c.get('secret', '')).startswith('@GEHEIM_'):
            raise SystemExit(f"Client {c.get('clientId')}: Geheimnis muss ein Platzhalter sein")
    # (kein Hinweisfeld in der Datei selbst – Keycloak lehnt unbekannte Felder beim Import ab; Hinweis: deploy/anmeldung/LIESMICH.md)
    return json.dumps(r, ensure_ascii=False, indent=2) + '\n'


def main() -> int:
    text = erzeugen()
    if '--pruefen' in sys.argv:
        if not ZIEL.is_file() or ZIEL.read_text(encoding='utf-8') != text:
            print('deploy/anmeldung/realm-mitarbeiter.json ist veraltet – python3 werkzeuge/realm_produktion.py ausführen.')
            return 1
        print('Realm für den Betrieb aktuell.')
        return 0
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    ZIEL.write_text(text, encoding='utf-8')
    print(f'geschrieben: {ZIEL.relative_to(WURZEL)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
