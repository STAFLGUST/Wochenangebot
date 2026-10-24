"""Dashboard-Host (dashboard-stafl.de): nur Grundaktionen (lib/herkunft.php, host_nur_grundaktionen, GR-109).

Der Testserver meldet sich wie das Dashboard (WA_OIDC=1, WA_OBERFLAECHE=dashboard.start), ohne Keycloak – es gibt also
keine geprüfte Identität. Das Dashboard braucht nur Status, Modulübersicht, Darstellung (Hell/Dunkel) und Abmelden.
Aktionen des gemeinsamen Eingabebereichs (Angebot, Bestand, Verwaltung) und der Modulseiten gibt es dort nicht (404,
noch vor der Anmeldeprüfung): Das Modul „dashboard“ hat keinen eigenen Zugang, über diese Adresse ließe sich sonst ein
entzogener Modulzugang umgehen. Den Ablauf mit echter Anmeldung prüft tests/oidc/test_oidc.py.
"""
import sys

from kunden_hilfe import Client

res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


P = Client('198.51.100.40')
code, r = P.call('status')
check('Status erreichbar (nicht angemeldet)', code == 200 and r.get('loggedIn') is False, (code, r))
check('Modulübersicht: Anmeldung verlangt (401, nicht 404)', P.call('module_status')[0] == 401)
check('Darstellung speichern: Anmeldung verlangt (nicht 404)', P.call('theme_save', {'theme': 'dark'})[0] in (401, 403))
check('Abmelden möglich', P.call('logout', {})[0] == 200)
for a, b in (('draft', None), ('bestellungen', None), ('kunden', None), ('stock', None), ('history_list', None), ('master', None),
             ('users', None), ('security_status', None), ('auswertung', None), ('save_draft', {'model': {}}), ('kunde_save', {'id': ''}),
             ('stock_import', {'date': '2026-10-16', 'articles': []}), ('mitarbeiter_hr', None), ('hr_start', None), ('crm_start', None),
             ('offer', None), ('kunde_status', None)):
    code, r = P.call(a, b)
    check(f'Dashboard-Host: {a} → 404 (gibt es hier nicht)', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
F = Client('198.51.100.41')
F.headers = {'WA_OBERFLAECHE': 'angebot.eingabe', 'WA-OBERFLAECHE': 'angebot.eingabe'}
check('Oberfläche lässt sich nicht über Kopfzeilen umstellen', F.call('draft')[0] == 404)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
