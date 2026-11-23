"""Zentrale Anmeldung – Verhalten der Anwendung ohne Keycloak (lib/oidc.php, GR-110).

Der Testserver läuft mit WA_OIDC=1 (wie ein Keycloak-Host), aber ohne Webserver-Modul: Es gibt also nie eine geprüfte
Identität. Geprüft wird, dass sich eine Identität nicht über Kopfzeilen unterschieben lässt, dass eigene Anmeldeverfahren
gesperrt sind und dass ohne WA_OIDC (heutiger Betrieb) alles beim Alten bleibt (eigene Gruppe „aktionsregister“ u. a.).
Der Server meldet sich als Host der Mitarbeiter-Eingabe (WA_OBERFLAECHE=angebot.eingabe): Aktionen einer eigenen Modulseite
(hr.intern, crm.intern, marketing.intern) werden hier abgewiesen (GR-109).
CSRF-Token bei stiller Neuanmeldung: oidc_nutzer im CLI mit einer Identität als Server-Umgebung (wie vom Webserver-Modul).
Den vollständigen Ablauf mit Keycloak prüft tests/oidc/ (CI-Auftrag „Anmeldung über Keycloak“).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from kunden_hilfe import Client
from umgebung import REPO

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

# Aktion ↔ Host (GR-109): der Testserver meldet sich wie angebot.dashboard-stafl.de (WA_OBERFLAECHE=angebot.eingabe).
# Aktionen der HR-Seite (hr.intern) gibt es nur auf ihrem eigenen Host – hier 404 noch vor der Anmeldeprüfung
for a, b in (('hr_start', None), ('hr_monat', None), ('hr_antrag', {'von': '2030-01-07', 'bis': '2030-01-07'})):
    code, r = P.call(a, b)
    check(f'HR-Aktion auf fremdem Host: {a} → 404', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
for a, b in (('crm_start', None), ('crm_kunde_save', {'key': 'kx', 'felder': {'segment': 'Catering'}}), ('crm_export', {})):
    code, r = P.call(a, b)
    check(f'CRM-Aktion auf fremdem Host: {a} → 404', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
for a, b in (('marketing_start', None), ('marketing_beitrag_save', {'felder': {'titel': 'x'}}), ('marketing_export', {})):
    code, r = P.call(a, b)
    check(f'Marketing-Aktion auf fremdem Host: {a} → 404', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
# Startseite des Dashboards (dashboard.start) nur auf dem Dashboard-Host – hier 404 noch vor der Anmeldeprüfung
for a, b in (('start_heute', None), ('start_favoriten_save', {'favoriten': []})):
    code, r = P.call(a, b)
    check(f'Dashboard-Aktion auf fremdem Host: {a} → 404', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
code, r = P.call('anmeldung_pruefen')
check('Prüfung vor der Anmeldeseite nur auf deren Host: hier 404', code == 404 and 'Adresse' in r.get('error', ''), (code, r))
check('Aktionen des Eingabebereichs hier weiter wie bisher (status 200, users 401)', P.call('status')[0] == 200 and P.call('users')[0] == 401)
F2 = Client('198.51.100.32')
F2.headers = {'WA_OBERFLAECHE': 'hr.intern', 'WA-OBERFLAECHE': 'hr.intern'}
check('Oberfläche des Hosts lässt sich nicht über Kopfzeilen unterschieben', F2.call('hr_start')[0] == 404)

# CSRF-Token bei stiller Neuanmeldung (lib/oidc.php, oidc_nutzer): echte Funktionen im CLI, die Identität wie vom Webserver als
# Server-Umgebung (OIDC_CLAIM_*), eigener Datenordner mit erfundenen Konten. Fehlt nur der Registereintrag (aufgeräumt nach
# Leerlauf auf diesem Host), bleibt das Token der offenen Seite gültig; jede andere Identität, eine neue Keycloak-Sitzung, eine
# erhöhte Sitzungsversion, eine beendete oder abgelaufene Sitzung bekommen ein neues Token, das alte gibt 403 mit code „csrf“.
DATEN = tempfile.mkdtemp(prefix='oidc-csrf-')
os.makedirs(os.path.join(DATEN, 'sess'))
UMG = {k: v for k, v in os.environ.items() if not k.startswith(('WA_DATEN_INTERN', 'WA_POSTAUSGANG', 'WA_OIDC'))}


def php(code):
    pre = ("define('WA_API', true); define('WA_CLI', true); require " + json.dumps(os.path.join(REPO, 'app', 'api', 'lib', 'laden.php')) + "; "
           f"$DATA = {json.dumps(DATEN)}; ini_set('session.save_path', {json.dumps(os.path.join(DATEN, 'sess'))}); ")
    p = subprocess.run(['php', '-d', 'display_errors=stderr', '-r', pre + code], capture_output=True, text=True, env=UMG)
    return p.stdout.strip() + p.stderr.strip()


def anfrage(cookie, sub, kc, token, vor=1000):
    """Schreibende Anfrage (require_auth(true)) eines Keycloak-Hosts mit Sitzungs-Cookie, Identität und CSRF-Kopfzeile"""
    umgebung = {'WA_OIDC': '1', 'WA_OIDC_ISSUER': 'https://login.example/realms/mitarbeiter', 'REMOTE_ADDR': '198.51.100.40',
                'OIDC_CLAIM_iss': 'https://login.example/realms/mitarbeiter', 'OIDC_CLAIM_sub': sub, 'REMOTE_USER': sub, 'OIDC_CLAIM_sid': kc,
                'OIDC_CLAIM_auth_time': str(int(time.time()) - vor), 'OIDC_CLAIM_amr': 'pwd,otp', 'HTTP_X_CSRF_TOKEN': token}
    roh = php(f"foreach (json_decode({json.dumps(json.dumps(umgebung))}, true) as $k => $v) $_SERVER[$k] = $v; "
              f"if ({json.dumps(cookie)} !== '') {{ $_COOKIE[sitzung_cookie_name()] = {json.dumps(cookie)}; session_id({json.dumps(cookie)}); }} "
              "try { require_auth(true); $st = 200; $r = []; } catch (WaAntwort $e) { $st = $e->status; $r = $e->daten; } "
              "echo json_encode(['st' => $st, 'code' => $r['code'] ?? '', 'csrf' => $_SESSION['csrf'] ?? '', 'cookie' => session_id(), 'reg' => $_SESSION['sid'] ?? '']);")
    try:
        return json.loads(roh)
    except ValueError:
        return {'st': 0, 'code': '', 'csrf': '', 'cookie': '', 'reg': '', 'roh': roh[:400]}


def neues_token(a, alt):
    return a['st'] == 403 and a['code'] == 'csrf' and a['csrf'] not in ('', alt)


php("store_write('nutzer', ['users' => [['id' => 'u1', 'username' => 'erika', 'name' => 'Erika', 'role' => 'editor', 'active' => true, 'sv' => 1, 'oidcSub' => 'sub-erika', 'hash' => ''],"
    " ['id' => 'u2', 'username' => 'vera', 'name' => 'Vera', 'role' => 'editor', 'active' => true, 'sv' => 1, 'oidcSub' => 'sub-vera', 'hash' => '']]]);")
a = anfrage('', 'sub-erika', 'kc1', '')
check('Keycloak-Host: angemeldet, ohne Token kein Schreiben (403 mit code „csrf“)', a['st'] == 403 and a['code'] == 'csrf' and a['csrf'], a)
tok, ck = a['csrf'], a['cookie']
b = anfrage(ck, 'sub-erika', 'kc1', tok)
check('… mit dem Token der Seite gespeichert', b['st'] == 200 and b['csrf'] == tok, b)
php("store_write('sitzungen', []);")
c = anfrage(ck, 'sub-erika', 'kc1', tok)
check('Registereintrag aufgeräumt, gleiche Anmeldung: Speichern mit dem Token der offenen Seite gelingt, Token unverändert', c['st'] == 200 and c['csrf'] == tok, c)
check('… dabei neue Sitzungskennung und neuer Registereintrag (keine Sitzungsfixierung)', c['cookie'] not in ('', ck) and c['reg'] not in ('', b['reg']), (ck, c))
ck = c['cookie']
php("store_write('sitzungen', []);")
d = anfrage(ck, 'sub-erika', 'kc2', tok)
check('neue Keycloak-Sitzung (ab- und wieder angemeldet): neues Token, das alte 403', neues_token(d, tok), d)
tok, ck = d['csrf'], d['cookie']
php("store_write('sitzungen', []);")
e = anfrage(ck, 'sub-vera', 'kc2', tok)
check('andere Person mit dieser Sitzung: neues Token, das alte 403', neues_token(e, tok), e)
f = anfrage('', 'sub-erika', 'kc3', '')
tok, ck = f['csrf'], f['cookie']
php("$u = users_load(); $u[0]['sv'] = 2; users_save($u);")
g = anfrage(ck, 'sub-erika', 'kc3', tok)
check('Sitzungsversion erhöht (z. B. zweiter Faktor zurückgesetzt): neues Token, das alte 403', neues_token(g, tok), g)
tok, ck = g['csrf'], g['cookie']
php("oidc_abmeldung_merken(['kc3'], []); store_write('sitzungen', []);")   # wie session_end
h = anfrage(ck, 'sub-erika', 'kc3', tok)
check('Sitzung beendet: erneute Anmeldung verlangt', h['st'] == 403 and h['code'] == 'reauth_required', h)
time.sleep(1.1)   # auth_time in ganzen Sekunden: die erneute Anmeldung liegt nach dem Ende
i = anfrage(ck, 'sub-erika', 'kc3', tok, vor=0)
check('… nach erneuter Anmeldung: neues Token, das alte 403', neues_token(i, tok), i)
tok, ck = i['csrf'], i['cookie']
check('… mit dem neuen Token weiter', anfrage(ck, 'sub-erika', 'kc3', tok, vor=0)['st'] == 200)
php("store_write('oidc-aktivitaet', ['kc3' => time() - 9 * 3600]); store_write('sitzungen', []);")   # 9 Stunden ohne Aktivität (Standard 8)
k = anfrage(ck, 'sub-erika', 'kc3', tok, vor=5)
check('Inaktivität: erneute Anmeldung verlangt', k['st'] == 403 and k['code'] == 'reauth_required', k)
time.sleep(1.1)
m = anfrage(ck, 'sub-erika', 'kc3', tok, vor=0)
check('… nach erneuter Anmeldung: neues Token, das alte 403', neues_token(m, tok), m)
shutil.rmtree(DATEN, ignore_errors=True)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
