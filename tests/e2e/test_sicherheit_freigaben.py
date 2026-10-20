"""Freigegebene Sicherheitsänderungen: Besucher-IP nur vom eigenen Proxy (WA_TRUSTED_PROXIES), Fehlversuche je IPv6-/64,
gleiche Sperre für unbekannte Benutzernamen (Mitarbeiter und Kunden), gesperrter Zugang mit zweitem Faktor bleibt für den
Inhaber erreichbar, Kundenangebote für Mitarbeiter nur aus freigegebenen Netzen, Protokoll ohne Kundendaten für Nutzer ohne
Kundenrecht, keine IP bei erfolgreichen Kundenanmeldungen, Schutz-Header in .htaccess. Nur synthetische Testdaten."""
import base64
import hashlib
import hmac
import json
import os
import struct
import subprocess
import sys
import time

from kunden_hilfe import Client
from umgebung import storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def totp(secret, step):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    h = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    o = h[19] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)


# ---------- Besucher-IP nur vom eigenen Proxy ----------
PHP = r"""
define('WA_API', 1);
require $argv[1] . '/app/api/lib/sicherheit.php';
require $argv[1] . '/app/api/lib/protokoll.php';
[$env, $remote, $fwd] = json_decode($argv[2], true);
if ($env !== null) putenv('WA_TRUSTED_PROXIES=' . $env);
$_SERVER = ['REMOTE_ADDR' => $remote, 'HTTP_X_FORWARDED_FOR' => $fwd];
echo client_ip();
"""
FAELLE = [[None, '172.18.0.3', '203.0.113.7'],            # ohne Angabe: private Gegenstelle wie bisher
          ['10.0.0.5', '172.18.0.3', '203.0.113.7'],      # anderer Container: X-Forwarded-For ignoriert
          ['10.0.0.5', '10.0.0.5', '203.0.113.8'],        # eigener Proxy (IP)
          ['10.1.0.0/24', '10.1.0.9', '203.0.113.9'],     # eigener Proxy (Netz)
          ['localhost', '127.0.0.1', '203.0.113.10'],     # eigener Proxy (Name)
          ['gibt-es-nicht.invalid', '127.0.0.2', '203.0.113.11']]
env = {k: v for k, v in os.environ.items() if k != 'WA_TRUSTED_PROXIES'}
outs = [subprocess.run(['php', '-r', PHP, REPO, json.dumps(f)], capture_output=True, text=True, env=env).stdout.strip() or 'Fehler' for f in FAELLE]
check('ohne WA_TRUSTED_PROXIES: wie bisher (private Gegenstelle)', outs[0] == '203.0.113.7', outs[0])
check('fremder Container darf keine Besucher-IP vorgeben', outs[1] == '172.18.0.3', outs[1])
check('eigener Proxy per IP', outs[2] == '203.0.113.8', outs[2])
check('eigener Proxy per Netz', outs[3] == '203.0.113.9', outs[3])
check('eigener Proxy per Name (Docker-Dienst)', outs[4] == '203.0.113.10', outs[4])
check('unbekannter Name: nichts vertraut', outs[5] == '127.0.0.2', outs[5])
compose = open(os.path.join(REPO, 'docker-compose.yml'), encoding='utf-8').read()
test_compose = open(os.path.join(REPO, 'deploy/testumgebung/docker-compose.yml'), encoding='utf-8').read()
check('Echtbetrieb vertraut nur Caddy, Testumgebung nicht im Produktivnetz', 'WA_TRUSTED_PROXIES: caddy' in compose and 'PROD_NETWORK' not in test_compose
      and 'wochenangebot-edge' in test_compose and 'WA_TRUSTED_PROXIES: wa-caddy' in test_compose)

# ---------- Fehlversuche je IPv6-/64 ----------
for i in range(5):
    Client(f'2001:db8:aa:1::{i + 1:x}').call('login', {'username': 'admin', 'password': 'Falsches-Passwort-1'})
st, r = Client('2001:db8:aa:1:ffff::99').call('login', {'username': 'admin', 'password': PW})
check('IPv6: andere Adresse im selben /64 ist mitgesperrt', st == 429 and 'Fehlversuche' in r.get('error', ''), (st, r))
st, r = Client('2001:db8:aa:2::1').call('login', {'username': 'admin', 'password': PW})
check('IPv6: anderes /64 nicht betroffen', st == 200, (st, r))
storage_write('logins', {})

# ---------- Sperre für unbekannte Namen wie für echte Zugänge ----------
sec = doc('sicherheit') or {}
storage_write('sicherheit', {**sec, 'lockAfter': 3, 'lockMinutes': 5})
A = Client('198.51.100.2'); assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})


def versuche(name, n, start, aktion='login'):
    out = []
    for i in range(n):
        out.append(Client(f'198.18.{start}.{i + 1}').call(aktion, {'username': name, 'password': 'Falsches-Passwort-1'}))
    return out


echt = versuche('eddi', 4, 1)
fake = versuche('gibt.es.nicht', 4, 2)
check('echter Zugang: nach 3 Fehlversuchen gesperrt (429)', [s for s, _ in echt] == [401, 401, 429, 429], [s for s, _ in echt])
check('unbekannter Name: identisches Verhalten (401, 401, 429, 429)', [s for s, _ in fake] == [401, 401, 429, 429], [s for s, _ in fake])
norm = lambda t: t.split(' bis ')[0]   # noqa: E731 – Uhrzeit kann um eine Minute abweichen
check('… mit gleicher Meldung', norm(echt[2][1].get('error', '')) == norm(fake[2][1].get('error', '')) and 'gesperrt' in fake[2][1].get('error', ''), (echt[2][1], fake[2][1]))
check('Liste der Namen speichert nur Prüfsummen', 'gibt.es.nicht' not in (storage_raw('anmeldenamen') or ''))

# Kunden ebenso
rev = A.call('kunden')[1]['rev']
assert A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Freigabe', 'nr': 'KF-1', 'email': 'kf@example.org', 'active': True, 'angebote': ['edeka'],
                             'login': {'username': 'kantine.frei', 'password': KPW, 'mustChange': False, 'active': True}})[0] == 200
ke = versuche('kantine.frei', 4, 3, 'kunde_login')
kf = versuche('kunde.unbekannt', 4, 4, 'kunde_login')
check('Kunden: echter und unbekannter Name gleich gesperrt', [s for s, _ in ke] == [s for s, _ in kf] == [401, 401, 429, 429] and ke[3][1].get('error') == kf[3][1].get('error'),
      ([s for s, _ in ke], [s for s, _ in kf]))

# ---------- gesperrter Zugang mit zweitem Faktor ----------
A.call('user_save', {'username': 'zara', 'name': 'Zara Zweifaktor', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
Z = Client('198.51.100.40'); assert Z.call('login', {'username': 'zara', 'password': 'Bearbeiter-Zugang-1'})[0] == 200
secret = Z.call('twofa_begin', {})[1]['secret']
step = int(time.time() // 30)
assert Z.call('twofa_enable', {'code': totp(secret, step)})[0] == 200
versuche('zara', 3, 5)
st, r = Client('198.18.6.1').call('login', {'username': 'zara', 'password': 'Falsches-Passwort-1'})
check('Zugang mit zweitem Faktor nach Fehlversuchen gesperrt', st == 429, (st, r))
Z2 = Client('198.18.6.2')
st, r = Z2.call('login', {'username': 'zara', 'password': 'Bearbeiter-Zugang-1'})
check('gesperrt + richtiges Passwort → zweiter Schritt statt Aussperren', st == 200 and r.get('need2fa') is True, (st, r))
st, r = Z2.call('login_2fa', {'code': '000000'})
check('… falscher Code bleibt abgewiesen', st in (401, 429), (st, r))
st, r = Z2.call('login', {'username': 'zara', 'password': 'Bearbeiter-Zugang-1'})
st, r = Z2.call('login_2fa', {'code': totp(secret, step + 1)})
check('… richtiger Code meldet an und hebt die Sperre auf', st == 200 and r.get('user', {}).get('username') == 'zara', (st, r))
st, r = Client('198.18.6.3').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('Zugang ohne zweiten Faktor bleibt bei Sperre gesperrt', st == 429, (st, r))
storage_write('logins', {})

# ---------- Kundenangebote nur aus freigegebenen Netzen ----------
storage_write('sicherheit', {**sec, 'ipEnabled': True, 'adminIps': ['198.51.100.0/24']})
F = Client('203.0.113.77')
st, _ = F.call('login', {'username': 'admin', 'password': PW})
check('Anmeldung von außerhalb der IP-Freigabe gesperrt', st == 403)
storage_write('sicherheit', {**sec, 'ipEnabled': False})
assert F.call('login', {'username': 'admin', 'password': PW})[0] == 200   # Sitzung entsteht, dann Freigabe an
storage_write('sicherheit', {**sec, 'ipEnabled': True, 'adminIps': ['198.51.100.0/24']})
st, r = F.call('offer&angebot=edeka')
check('Mitarbeiter-Sitzung von außerhalb: Kundenangebot gesperrt', st == 403 and 'nicht freigegeben' in r.get('error', ''), (st, r))
check('… öffentliches Wochenangebot bleibt abrufbar', F.call('offer')[0] == 200)
check('von freigegebener Adresse: Kundenangebot abrufbar', A.call('offer&angebot=edeka')[0] == 200)
rev = A.call('kunden')[1]['rev']
assert A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Zwei', 'nr': 'KF-2', 'email': 'k2f@example.org', 'active': True, 'angebote': ['edeka'],
                             'login': {'username': 'kantine.zwei', 'password': KPW, 'mustChange': False, 'active': True}})[0] == 200
K = Client('203.0.113.78'); assert K.call('kunde_login', {'username': 'kantine.zwei', 'password': KPW})[0] == 200
check('Kunde selbst ist nicht betroffen', K.call('offer&angebot=edeka')[0] == 200)
storage_write('sicherheit', {**sec, 'ipEnabled': False})

# ---------- Protokoll ----------
log = A.call('log')[1]['entries']
kl = [e for e in log if e['a'] == 'kunde_login']
kf_ = [e for e in log if e['a'] == 'kunde_login_fail']
check('erfolgreiche Kundenanmeldung ohne IP gespeichert', kl and all(e.get('ip', '') == '' for e in kl), kl[:1])
check('fehlgeschlagene Kundenanmeldung mit IP (Sicherheit)', kf_ and all(e.get('ip') for e in kf_))
A.call('user_save', {'username': 'pia', 'name': 'Pia Protokoll', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False, 'grant': ['protokoll.sehen'], 'deny': []})
P = Client('198.51.100.41'); assert P.call('login', {'username': 'pia', 'password': 'Leserin-Zugang-1'})[0] == 200
pl = P.call('log')[1]['entries']
cust = [e for e in pl if e['a'] == 'customers' or e['r'] == 'kunde']
txt = json.dumps(pl, ensure_ascii=False)
check('ohne Kundenrecht: Kundenvorgänge nur als Vorgang (keine Firma, E-Mail, Details, IP)', cust and all(e.get('masked') and 'd' not in e and not e.get('ip') for e in cust)
      and 'Kantine Freigabe' not in txt and 'kf@example.org' not in txt and 'kantine.frei' not in txt, cust[:1])
check('… andere Vorgänge bleiben vollständig', any(e['a'] == 'user' and 'Eddi' in e['s'] for e in pl))
al = json.dumps(A.call('log')[1]['entries'], ensure_ascii=False)
check('mit Kundenrecht (Administrator) vollständig', 'Kantine Freigabe' in al)

# ---------- Schutz-Header ohne Caddy ----------
ht = open(os.path.join(REPO, 'app/.htaccess'), encoding='utf-8').read()
check('.htaccess: CSP, HSTS (nur HTTPS), Permissions-Policy', "Content-Security-Policy \"default-src 'self'; script-src 'self';" in ht and 'Strict-Transport-Security "max-age=31536000" env=HTTPS' in ht
      and 'Permissions-Policy' in ht)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
