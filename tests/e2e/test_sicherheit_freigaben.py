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
import tempfile
import time

from kunden_hilfe import Client
from umgebung import BASE, storage_raw, storage_write

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
          ['gibt-es-nicht.invalid', '127.0.0.2', '203.0.113.11'],  # Name nicht auflösbar (DNS-Störung): wie ohne Angabe
          ['localhost', '172.18.0.3', '203.0.113.12'],              # Name auflösbar, andere Gegenstelle: nicht vertraut
          ['2001:db8::1', '2001:db8:0:0:0:0:0:1', '203.0.113.14'],  # IPv6 in anderer Schreibweise: gleiche Adresse
          ['schon-mal-aufgeloest.invalid', '127.0.0.5', '203.0.113.15'],  # DNS-Störung, früher aufgelöst: gemerkte Adresse gilt
          ['schon-mal-aufgeloest.invalid', '172.18.0.3', '203.0.113.16'],  # … andere Container bleiben ausgeschlossen
          ['10.1, 10.0.0.5', '10.0.0.1', '203.0.113.17']]  # Tippfehler „10.1“ ist kein Name (würde sonst als 10.0.0.1 aufgelöst)
TMP = tempfile.mkdtemp(prefix='wa-proxy-')
with open(os.path.join(TMP, 'wa-proxy-4-' + hashlib.sha256(b'schon-mal-aufgeloest.invalid').hexdigest() + '.json'), 'w') as fh:
    json.dump(['127.0.0.5'], fh)
env = {k: v for k, v in os.environ.items() if k != 'WA_TRUSTED_PROXIES'}
env['TMPDIR'] = TMP
outs = [subprocess.run(['php', '-r', PHP, REPO, json.dumps(f)], capture_output=True, text=True, env=env).stdout.strip() or 'Fehler' for f in FAELLE]
check('ohne WA_TRUSTED_PROXIES: wie bisher (private Gegenstelle)', outs[0] == '203.0.113.7', outs[0])
check('fremder Container darf keine Besucher-IP vorgeben', outs[1] == '172.18.0.3', outs[1])
check('eigener Proxy per IP', outs[2] == '203.0.113.8', outs[2])
check('eigener Proxy per Netz', outs[3] == '203.0.113.9', outs[3])
check('eigener Proxy per Name (Docker-Dienst)', outs[4] == '203.0.113.10', outs[4])
check('Name nicht auflösbar: wie ohne Angabe – Besucher fallen nicht auf die Proxy-Adresse zusammen', outs[5] == '203.0.113.11', outs[5])
check('Name auflösbar, andere Gegenstelle: X-Forwarded-For ignoriert', outs[6] == '172.18.0.3', outs[6])
check('IPv6-Proxy in anderer Schreibweise wird erkannt', outs[7] == '203.0.113.14', outs[7])
check('Name gerade nicht auflösbar: zuletzt aufgelöste Adresse gilt weiter (kein Rückfall auf alle privaten Adressen)', outs[8] == '203.0.113.15' and outs[9] == '172.18.0.3', outs[8:10])
check('Proxy-Angabe ohne Buchstaben wird nicht als Name aufgelöst', outs[10] == '10.0.0.1', outs[10])
DUMMY = r"""define('WA_API', 1); require $argv[1] . '/app/api/lib/nutzer.php';
echo json_encode([dummy_kosten([password_hash('x', PASSWORD_BCRYPT, ['cost' => 12])]), dummy_kosten([null, password_hash('x', PASSWORD_BCRYPT, ['cost' => 11])]), dummy_kosten([]), dummy_kosten(['kein-hash'])]);"""
aus = subprocess.run(['php', '-r', DUMMY, REPO], capture_output=True, text=True).stdout
check('Vergleichswert für unbekannte Namen mit denselben Kosten wie die gespeicherten Passwörter (z. B. PHP 8.4: 12)', aus == '[12,11,10,10]', aus)
check('aufgelöste Proxy-Adresse wird gemerkt', any(f.startswith('wa-proxy-') and f.endswith('.json') and f != 'wa-proxy-4-' + hashlib.sha256(b'schon-mal-aufgeloest.invalid').hexdigest() + '.json' for f in os.listdir(TMP)), os.listdir(TMP))
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
check('echter Zugang: nach 3 Fehlversuchen gesperrt (429), danach Code-Schritt mit Sperrhinweis', [s for s, _ in echt] == [401, 401, 429, 200] and echt[3][1].get('need2fa') and echt[3][1].get('gesperrtBis'), echt)
check('unbekannter Name: identisches Verhalten (401, 401, 429, Code-Schritt)', [s for s, _ in fake] == [401, 401, 429, 200] and set(fake[3][1]) == set(echt[3][1]), fake)
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
Zf = Client('198.18.6.1')
st, r = Zf.call('login', {'username': 'zara', 'password': 'Falsches-Passwort-1'})
check('gesperrt + falsches Passwort: Code-Schritt mit Sperrhinweis (Antwort verrät das Passwort nicht)', st == 200 and r.get('need2fa') and r.get('gesperrtBis'), (st, r))
falsch = r
st, r = Zf.call('login_2fa', {'code': totp(secret, step + 1)})
check('… dort hilft auch der richtige Code nicht (falsches Passwort bleibt falsch)', st == 401 and 'nicht korrekt' in r.get('error', ''), (st, r))
Z2 = Client('198.18.6.2')
st, r = Z2.call('login', {'username': 'zara', 'password': 'Bearbeiter-Zugang-1'})
check('gesperrt + richtiges Passwort → zweiter Schritt statt Aussperren', st == 200 and r.get('need2fa') is True, (st, r))
check('… mit genau derselben Antwort wie bei falschem Passwort', r == falsch, (r, falsch))
st, r = Z2.call('login_2fa', {'code': '000000'})
check('… falscher Code abgewiesen (gleiche Meldung wie sonst)', st == 401 and 'nicht korrekt' in r.get('error', ''), (st, r))
st, r = Z2.call('login_2fa', {'code': totp(secret, step + 1)})
check('… richtiger Code meldet an und hebt die Sperre auf', st == 200 and r.get('user', {}).get('username') == 'zara', (st, r))
E = Client('198.18.6.3')
st, r = E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
eddi_login = r
check('Zugang ohne zweiten Faktor, gesperrt, richtiges Passwort: gleiche Antwort wie jedes andere Passwort', st == 200 and r.get('need2fa') and r.get('gesperrtBis'), (st, r))
st, r = E.call('login_2fa', {'code': '123456'})
eddi_code = r
check('… aber keine Anmeldung möglich (bleibt bis zum Ablauf gesperrt)', st == 401 and 'user' not in r and E.call('status')[1].get('loggedIn') is False, (st, r))
G = Client('198.18.6.4')
st, r = G.call('login', {'username': 'gibt.es.nicht', 'password': 'Falsches-Passwort-1'})
st2, r2 = G.call('login_2fa', {'code': '123456'})
check('unbekannter gesperrter Name: gleicher Code-Schritt, gleiche Ablehnung', st == 200 and set(r) == set(eddi_login) and r.get('need2fa') and st2 == 401 and r2 == eddi_code, (st, r, st2, r2, eddi_code))
storage_write('logins', {})


def zweifaktor(name, ip):
    A.call('user_save', {'username': name, 'name': name.title() + ' Test', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    c = Client(ip); assert c.call('login', {'username': name, 'password': 'Bearbeiter-Zugang-1'})[0] == 200
    sek = c.call('twofa_begin', {})[1]['secret']
    stp = int(time.time() // 30)
    assert c.call('twofa_enable', {'code': totp(sek, stp)})[0] == 200
    return sek, stp


def nutzer(name):
    d = doc('nutzer')
    return next(x for x in (d['users'] if isinstance(d, dict) else d) if x.get('username') == name)


# Höchstens 3 Code-Versuche je Sperre – auch mit mehreren parallel geöffneten Anmeldevorgängen
ysek, ystep = zweifaktor('yara', '198.51.100.42')
versuche('yara', 3, 7)
offen = []
for i in range(4):
    c = Client(f'198.18.8.{i + 1}')
    st, r = c.call('login', {'username': 'yara', 'password': 'Bearbeiter-Zugang-1'})
    offen.append((c, st, r.get('need2fa')))
check('gesperrt: mehrere Anmeldevorgänge gleichzeitig geöffnet (je Code-Schritt)', all(st == 200 and n for _, st, n in offen), [(st, n) for _, st, n in offen])
codes = [c.call('login_2fa', {'code': '000000'})[0] for c, _, _ in offen[:3]]
st4, r4 = offen[3][0].call('login_2fa', {'code': totp(ysek, ystep + 1)})
check('nach 3 falschen Codes (verteilt auf Vorgänge) hilft auch der richtige Code nicht mehr', codes == [401, 401, 401] and st4 == 401 and nutzer('yara').get('lockTries') == 3, (codes, st4, r4, nutzer('yara').get('lockTries')))
Y = Client('198.18.8.9')
st, r = Y.call('login', {'username': 'yara', 'password': 'Bearbeiter-Zugang-1'})
st2, _ = Y.call('login_2fa', {'code': totp(ysek, ystep + 2)})
check('… Passwort-Schritt antwortet unverändert (verrät nicht, dass die Codes verbraucht sind), Anmeldung bleibt gesperrt', st == 200 and r.get('need2fa') and st2 == 401, (st, r, st2))
storage_write('logins', {})

# Falsche Passwörter während der Sperre: kein Raten (gleiche Antwort) und kein Aussperren des Inhabers
xsek, xstep = zweifaktor('xena', '198.51.100.43')
versuche('xena', 3, 9)
andere = versuche('xena', 8, 11)
check('viele falsche Passwörter während der Sperre: immer dieselbe Antwort', all(st == 200 and r.get('need2fa') for st, r in andere) and len({json.dumps(r, sort_keys=True) for _, r in andere}) == 1, andere[:2])
X = Client('198.18.12.1')
st, r = X.call('login', {'username': 'xena', 'password': 'Bearbeiter-Zugang-1'})
st2, r2 = X.call('login_2fa', {'code': totp(xsek, xstep + 1)})
check('… der Inhaber kommt mit richtigem Passwort und Code trotzdem hinein', st == 200 and st2 == 200 and r2.get('user', {}).get('username') == 'xena', (st, r, st2, r2))
check('… und die Sperre samt Zählern ist aufgehoben', not nutzer('xena').get('lockedUntil') and 'lockTries' not in nutzer('xena'), nutzer('xena'))
storage_write('logins', {})

# Neue Sperre beginnt ohne Reste der früheren (Code-Versuche neu gezählt)
nu = doc('nutzer')
for x in (nu['users'] if isinstance(nu, dict) else nu):
    if x.get('username') == 'xena': x.update({'lockTries': 3, 'lockedUntil': int(time.time()) - 5, 'failCount': 0})
storage_write('nutzer', nu)
versuche('xena', 3, 14)
X2 = Client('198.18.15.1')
st, r = X2.call('login', {'username': 'xena', 'password': 'Bearbeiter-Zugang-1'})
while int(time.time() // 30) + 1 <= xstep + 1: time.sleep(1)   # noch nicht benutzter Code im gültigen Fenster
check('neue Sperre beginnt ohne alte Code-Versuche', nutzer('xena').get('lockedUntil', 0) > time.time() and 'lockTries' not in nutzer('xena'), nutzer('xena'))
st2, r2 = X2.call('login_2fa', {'code': totp(xsek, int(time.time() // 30) + 1)})
check('neue Sperre: alte Code-Versuche zählen nicht mit', st == 200 and st2 == 200 and r2.get('user', {}).get('username') == 'xena', (st, r, st2, r2))
storage_write('logins', {})

# Code-Schritte aus einer Sperre enden mit ihr – echte und wirkungslose gleich, ohne Folgen für die Zähler
storage_write('sicherheit', {**sec, 'lockAfter': 3, 'lockMinutes': 1})
vsek, vstep = zweifaktor('vera', '198.51.100.45')
versuche('vera', 3, 18)
V1, V2 = Client('198.18.19.1'), Client('198.18.19.2')
a1 = V1.call('login', {'username': 'vera', 'password': 'Bearbeiter-Zugang-1'})
a2 = V2.call('login', {'username': 'vera', 'password': 'Falsches-Passwort-1'})
check('Sperre (1 Min.): echter und wirkungsloser Code-Schritt gleich', a1 == a2 and a1[0] == 200, (a1, a2))
bis = nutzer('vera')['lockedUntil']
while time.time() <= bis + 1: time.sleep(1)
vor = {k: nutzer('vera').get(k) for k in ('failCount', 'lockedUntil', 'lockTries')}
b1 = V1.call('login_2fa', {'code': '000000'})
b2 = V2.call('login_2fa', {'code': '000000'})
nach_v = {k: nutzer('vera').get(k) for k in ('failCount', 'lockedUntil', 'lockTries')}
check('nach Ablauf der Sperre: beide Vorgänge gleich beendet („abgelaufen“), Zähler unverändert', b1 == b2 and b1[0] == 401 and 'abgelaufen' in b1[1].get('error', '') and vor == nach_v, (b1, b2, vor, nach_v))
storage_write('sicherheit', {**sec, 'lockAfter': 3, 'lockMinutes': 5})
storage_write('logins', {})

# Fehlgeschlagene Anmeldungen dauern gleich lang – auch bei aufwendigerem Prüfwert (bcrypt-Kosten 12, z. B. nach PHP 8.4)
storage_write('logins', {})
A.call('user_save', {'username': 'teo', 'name': 'Teo Teuer', 'role': 'viewer', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
h12 = subprocess.run(['php', '-r', 'echo password_hash("Bearbeiter-Zugang-1", PASSWORD_BCRYPT, ["cost" => 12]);'], capture_output=True, text=True).stdout
nu = doc('nutzer')
for x in nu['users']:
    if x['username'] == 'teo': x['hash'] = h12
storage_write('nutzer', nu)


def dauer(name, netz):
    t = []
    for i in range(3):
        t0 = time.time(); Client(f'198.18.{netz}.{i + 1}').call('login', {'username': name, 'password': 'Falsches-Passwort-1'}); t.append(time.time() - t0)
    return sorted(t)[1]


d_teo, d_fremd = dauer('teo', 20), dauer('niemand.hier', 21)
check('fehlgeschlagene Anmeldung: bekannter Name (Kosten 12) und unbekannter Name gleich lang (ca. 0,6 s)', 0.55 <= d_fremd <= 1.0 and 0.55 <= d_teo <= 1.0 and abs(d_teo - d_fremd) < 0.15, (round(d_teo, 3), round(d_fremd, 3)))
storage_write('logins', {})

# Liste unbekannter Namen: laufende Sperren werden beim Kürzen nie entfernt
jetzt = int(time.time())
viele = {f'u:{i:064x}': {'n': 1, 'until': 0, 't': jetzt - 10} for i in range(5001)}
aktiv_key = 'u:' + hashlib.sha256(b'gesperrt.unbekannt').hexdigest()
viele[aktiv_key] = {'n': 0, 'until': jetzt + 300, 't': jetzt - 3600}   # älteste, aber gesperrt
storage_write('anmeldenamen', viele)
Client('198.18.16.1').call('login', {'username': 'noch.ein.name', 'password': 'Falsches-Passwort-1'})
nach = doc('anmeldenamen')
check('Kürzen der Namensliste behält laufende Sperren', len(nach) <= 4001 and aktiv_key in nach, len(nach))
st, r = Client('198.18.16.2').call('login', {'username': 'gesperrt.unbekannt', 'password': 'Falsches-Passwort-1'})
check('… der gesperrte unbekannte Name bleibt gesperrt (Code-Schritt)', st == 200 and r.get('need2fa'), (st, r))
storage_write('anmeldenamen', {})
storage_write('logins', {})

# Fehlversuche verfallen nach 24 Stunden – bei echten und unbekannten Namen gleich
nu = doc('nutzer')
lst = nu['users'] if isinstance(nu, dict) and 'users' in nu else nu
for x in lst:
    if x.get('username') == 'eddi': x.update({'failCount': 2, 'failAt': int(time.time()) - 90000, 'lockedUntil': 0})
storage_write('nutzer', nu)
st, r = Client('198.18.13.1').call('login', {'username': 'eddi', 'password': 'Falsches-Passwort-1'})
check('alte Fehlversuche (älter als 24 h) zählen nicht mehr: nur 1 Fehlversuch, keine Sperre', st == 401 and next(x for x in (doc('nutzer')['users'] if isinstance(doc('nutzer'), dict) else doc('nutzer')) if x.get('username') == 'eddi')['failCount'] == 1, (st, r))
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
check('.htaccess: CSP, HSTS (nur HTTPS), Permissions-Policy', "Content-Security-Policy \"default-src 'self'; script-src 'self';" in ht and 'Strict-Transport-Security "max-age=31536000; includeSubDomains" env=HTTPS' in ht
      and 'Permissions-Policy' in ht)
check('.htaccess: X-Powered-By (PHP-Version) wird entfernt', 'Header unset X-Powered-By' in ht)
cf_haupt = open(os.path.join(REPO, 'Caddyfile'), encoding='utf-8').read().split('test.{$DOMAIN} {')[0]
check('Caddy: HTTPS-Pflicht (HSTS) 1 Jahr, auch für alle Subdomains, ohne preload', 'Strict-Transport-Security "max-age=31536000; includeSubDomains"' in cf_haupt
      and not any('preload' in z for z in cf_haupt.splitlines() if 'Strict-Transport-Security' in z))
cf = open(os.path.join(REPO, 'Caddyfile'), encoding='utf-8').read()
bloecke = cf.split('test.{$DOMAIN} {')
check('Caddy: versionierte Skripte/Stylesheets (?v=…) ein Jahr zwischenspeichern, alles andere weiter „no-cache“ – Echtbetrieb und Testumgebung',
      len(bloecke) == 2 and all('@versioniert {\n\t\tpath /assets/*\n\t\tquery v=*\n\t}' in b and 'header @versioniert >Cache-Control "public, max-age=31536000, immutable"' in b
                               and '?Cache-Control "no-cache"' in b for b in bloecke))

# ---------- Oberfläche: Hinweis im Code-Schritt bei gesperrtem Zugang ----------
storage_write('sicherheit', {**sec, 'ipEnabled': False, 'lockAfter': 3, 'lockMinutes': 5})
storage_write('logins', {})
zweifaktor('wanda', '198.51.100.44')
versuche('wanda', 3, 17)
storage_write('logins', {})
from playwright.sync_api import sync_playwright  # noqa: E402
with sync_playwright() as p:
    br = p.chromium.launch()
    for breite in (1440, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900})
        pg = ctx.new_page(); fehler = []; pg.on('pageerror', lambda ex: fehler.append(str(ex)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'wanda'); pg.fill('#pw1', 'Falsches-Passwort-1'); pg.click('#auth-submit')
        pg.wait_for_selector('#au-code-wrap:not([hidden])')
        intro = pg.inner_text('#auth-intro')
        breit = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        pg.screenshot(path=os.path.join(REPO, 'tests', '.arbeit', f'sperre-code-{breite}.png'))
        check(f'{breite} px: Code-Schritt erklärt die Sperre (Uhrzeit, App, Administrator), kein waagrechtes Scrollen, keine Skriptfehler',
              'gesperrt' in intro and 'Uhr' in intro and 'Authenticator-App' in intro and 'Administrator' in intro and not breit and not fehler, (intro, breit, fehler))
        ctx.close()
    br.close()
storage_write('logins', {})

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
