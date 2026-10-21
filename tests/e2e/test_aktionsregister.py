"""Aktionsregister (regeln/aktionen/*.toml → app/api/lib/aktionen-liste.php) wirkt im API-Einstieg für jede Aktion.

Anfragen von einer internen Adresse (10.x): die Fehlerbremse der Firewall sperrt solche Adressen nie, sodass alle
Aktionen nacheinander geprüft werden können.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from umgebung import BASE

API = BASE + '/api/?action='
REPO = Path(__file__).resolve().parents[2]
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


php = "define('WA_API', 1); require $argv[1]; echo json_encode(AKTIONEN);"
AKT = json.loads(subprocess.run(['php', '-r', php, str(REPO / 'app/api/lib/aktionen-liste.php')], capture_output=True, text=True, check=True).stdout)


def anfrage(action, methode='GET', typ=None, daten=None):
    h = {'X-Forwarded-For': '10.9.8.7'}
    if typ:
        h['Content-Type'] = typ
    req = urllib.request.Request(API + action, data=daten, headers=h, method=methode)
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        r = e
    body = r.read()
    try:
        return r.code, json.loads(body)
    except ValueError:
        return r.code, {}


schreibend = sorted(a for a, x in AKT.items() if x['schreibend'] is True)
check('Register enthält die Schreibaktionen', len(schreibend) >= 70, len(schreibend))
falsch_get = [a for a in schreibend if anfrage(a)[0] != 405]
check('jede schreibende Aktion: GET → 405', not falsch_get, falsch_get)
falsch_typ = [a for a in schreibend if anfrage(a, 'POST', 'text/plain', b'{}')[0] != 415]
check('jede schreibende Aktion: POST ohne JSON → 415', not falsch_typ, falsch_typ)

check('security_integrity („post“): GET ohne Anmeldung 401 statt 405', anfrage('security_integrity')[0] == 401)
check('security_integrity („post“): POST ohne JSON → 415', anfrage('security_integrity', 'POST', 'text/plain', b'{}')[0] == 415)
check('abmelden1 (Formular aus dem E-Mail-Programm) nicht als JSON-Pflicht abgewiesen', anfrage('abmelden1', 'POST', 'application/x-www-form-urlencoded', b'List-Unsubscribe=One-Click')[0] not in (405, 415))

st, j = anfrage('gibt_es_nicht')
check('unbekannte Aktion → 404', st == 404 and j.get('error') == 'Unbekannte Aktion.', (st, j))
check('lesende Aktion per GET nicht abgewiesen (status)', anfrage('status')[0] == 200)
check('öffentliche Aktion ohne Anmeldung erreichbar (offer, app_info)', anfrage('offer')[0] == 200 and anfrage('app_info')[0] == 200)
check('Mitarbeiter-Aktion ohne Anmeldung abgewiesen (stock)', anfrage('stock')[0] == 401)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
