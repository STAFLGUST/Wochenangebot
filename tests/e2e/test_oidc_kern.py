"""Zentrale Anmeldung – Verhalten der Anwendung ohne Keycloak (lib/oidc.php, GR-110).

Der Testserver läuft mit WA_OIDC=1 (wie ein Keycloak-Host), aber ohne Webserver-Modul: Es gibt also nie eine geprüfte
Identität. Geprüft wird, dass sich eine Identität nicht über Kopfzeilen unterschieben lässt, dass eigene Anmeldeverfahren
gesperrt sind und dass ohne WA_OIDC (heutiger Betrieb) alles beim Alten bleibt (eigene Gruppe „aktionsregister“ u. a.).
Den vollständigen Ablauf mit Keycloak prüft tests/oidc/ (CI-Auftrag „Anmeldung über Keycloak“).
"""
import sys

from kunden_hilfe import Client

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


P = Client('198.51.100.30')
code, r = P.call('status')
check('status ohne Identität: nicht angemeldet', code == 200 and r.get('loggedIn') is False, r)
for a in ('login', 'login_2fa', 'setup', 'passkey_login_begin', 'passkey_login', 'kunde_login', 'kunde_passwort', 'kunde_token_set'):
    code, r = P.call(a, {'username': 'admin', 'password': PW})
    check(f'eigenes Anmeldeverfahren gesperrt: {a} → 403', code == 403 and 'zentral' in r.get('error', ''), (code, r))
check('Abmelden bleibt möglich', P.call('logout', {})[0] == 200)

# Untergeschobene Identität über Kopfzeilen (landen als HTTP_* beim Server und werden nie gelesen)
F = Client('198.51.100.31')
F.headers = {'OIDC_CLAIM_sub': 'x', 'OIDC-CLAIM-sub': 'x', 'OIDC_CLAIM_iss': 'https://login.example/realms/mitarbeiter',
             'OIDC_CLAIM_preferred_username': 'admin', 'Remote-User': 'x', 'REMOTE_USER': 'x', 'WA_OIDC': '0', 'WA-OIDC-ISSUER': 'x'}
code, r = F.call('status')
check('Kopfzeilen mit Anmeldedaten melden nicht an', code == 200 and r.get('loggedIn') is False, r)
check('… und schalten die zentrale Anmeldung nicht ab', F.call('login', {'username': 'admin', 'password': PW})[0] == 403)
check('… geschützte Aktion bleibt 401', F.call('users')[0] == 401)
check('Modulübersicht ohne Identität 401', P.call('module_status')[0] == 401)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
