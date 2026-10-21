"""Vertraute Geräte: Ein Browser, auf dem sich ein Zugang schon erfolgreich angemeldet hat, kommt auch während einer fremd
ausgelösten Kontosperre mit dem richtigen Passwort durch (Mitarbeiter mit und ohne Zwei-Faktor, Kunden); ohne bzw. mit
gefälschter Kennung bleibt die Sperre unverändert; Fehlversuche zählen je Gerät; Entfernen in der Verwaltung, beim neuen
Passwort und beim eigenen Passwortwechsel; Meldung bei Administrator-Anmeldung von neuem Gerät; Oberfläche 1440/390 px.
Nur synthetische Testdaten."""
import base64
import copy
import hashlib
import hmac
import json
import os
import struct
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, WORK, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
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


def jar(c):
    return next(h for h in c.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor)).cookiejar


def kennung(c):
    return next((x for x in jar(c) if x.name == 'WA_GERAET'), None)


def gleicher_browser(c, ip):
    """Neuer Client (neue Sitzung, andere Adresse) mit der Gerätekennung des Browsers c – wie nach dem Schließen des Browsers"""
    n = Client(ip)
    k = kennung(c)
    if k is not None:
        jar(n).set_cookie(copy.copy(k))
    return n


def mit_kennung(c, wert, ip):
    n = gleicher_browser(c, ip)
    for x in jar(n):
        if x.name == 'WA_GERAET':
            x.value = wert
    return n


def nutzer(name):
    d = doc('nutzer')
    return next(x for x in (d['users'] if isinstance(d, dict) else d) if x.get('username') == name)


def nutzer_setzen(name, **kw):
    d = doc('nutzer')
    for x in (d['users'] if isinstance(d, dict) else d):
        if x.get('username') == name:
            x.update(kw)
    storage_write('nutzer', d)


def kunde(uname):
    return next(c for c in doc('kunden')['customers'] if (c.get('login') or {}).get('username') == uname)


def kunde_setzen(uname, **kw):
    d = doc('kunden')
    for c in d['customers']:
        if (c.get('login') or {}).get('username') == uname:
            c['login'].update(kw)
    storage_write('kunden', d)


def versuche(name, n, netz, aktion='login'):
    return [Client(f'198.18.{netz}.{i + 1}').call(aktion, {'username': name, 'password': 'Falsches-Passwort-1'}) for i in range(n)]


sec = doc('sicherheit') or {}
storage_write('sicherheit', {**sec, 'lockAfter': 3, 'lockMinutes': 5})
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})

# ---------- Mitarbeiter ohne zweiten Faktor ----------
E1 = Client('198.51.100.10')
st, r = E1.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
k = kennung(E1)
check('nach der Anmeldung: Gerätekennung als Cookie (nur Server, SameSite=Strict, 180 Tage)', st == 200 and k is not None and k.has_nonstandard_attr('HttpOnly')
      and k.expires and k.expires > time.time() + 170 * 86400 and len(k.value) == 43, (st, k and k.__dict__))
g = nutzer('eddi').get('geraete', [])
check('beim Zugang nur Prüfsumme und Gerätename gespeichert', len(g) == 1 and g[0]['h'] != k.value and k.value not in json.dumps(g) and g[0]['name'], g)

versuche('eddi', 3, 1)
check('Zugang durch fremde Fehlversuche gesperrt', nutzer('eddi').get('lockedUntil', 0) > time.time())
st, r = Client('198.18.2.1').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('ohne vertrautes Gerät: richtiges Passwort hilft nicht (Code-Schritt ohne Wirkung wie bisher)', st == 200 and r.get('need2fa') and 'user' not in r, (st, r))
st, r = mit_kennung(E1, 'A' * 43, '198.18.2.2').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('gefälschte Kennung: wie ohne Gerät', st == 200 and r.get('need2fa') and 'user' not in r, (st, r))
E2 = gleicher_browser(E1, '198.51.100.11')
st, r = E2.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('vertrautes Gerät: Inhaber kommt trotz Sperre hinein (auch von neuer Adresse)', st == 200 and r.get('user', {}).get('username') == 'eddi', (st, r))
check('… und die Sperre ist aufgehoben', not nutzer('eddi').get('lockedUntil'), nutzer('eddi').get('lockedUntil'))
check('… kein zweites Gerät angelegt', len(nutzer('eddi').get('geraete', [])) == 1)

versuche('eddi', 3, 3)
E3 = gleicher_browser(E1, '198.51.100.12')
falsch = [E3.call('login', {'username': 'eddi', 'password': 'Falsches-Passwort-1'})[0] for _ in range(5)]
check('vertrautes Gerät während der Sperre: falsches Passwort → normale Meldung, zählt nur für das Gerät', falsch == [401] * 5 and nutzer('eddi')['geraete'][0]['f'] == 5, (falsch, nutzer('eddi')['geraete']))
st, r = gleicher_browser(E1, '198.51.100.18').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('nach 5 Fehlversuchen ist das Gerät nicht mehr vertraut (Sperre gilt wieder)', st == 200 and r.get('need2fa') and 'user' not in r, (st, r))
storage_write('logins', {})
A.call('user_unlock', {'id': nutzer('eddi')['id']})
st, r = gleicher_browser(E1, '198.51.100.13').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('nach erfolgreicher Anmeldung (ohne Sperre) ist das Gerät wieder vertraut (Zähler zurückgesetzt)', st == 200 and nutzer('eddi')['geraete'][0]['f'] == 0, nutzer('eddi')['geraete'])
storage_write('logins', {})

# ---------- Mitarbeiter mit Authenticator-App ----------
A.call('user_save', {'username': 'zora', 'name': 'Zora Zweifaktor', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
Z1 = Client('198.51.100.20')
assert Z1.call('login', {'username': 'zora', 'password': 'Bearbeiter-Zugang-1'})[0] == 200
sek = Z1.call('twofa_begin', {})[1]['secret']
step = int(time.time() // 30)
assert Z1.call('twofa_enable', {'code': totp(sek, step)})[0] == 200
Z1.call('logout', {})
Z1b = gleicher_browser(Z1, '198.51.100.21')
st, r = Z1b.call('login', {'username': 'zora', 'password': 'Bearbeiter-Zugang-1'})
while int(time.time() // 30) + 1 <= step: time.sleep(1)
st, r = Z1b.call('login_2fa', {'code': totp(sek, int(time.time() // 30) + 1)})
check('Anmeldung mit Code merkt das Gerät', st == 200 and len(nutzer('zora').get('geraete', [])) == 1, (st, r))
zstep = int(time.time() // 30) + 1
versuche('zora', 3, 4)
Z2 = gleicher_browser(Z1, '198.51.100.22')
st, r = Z2.call('login', {'username': 'zora', 'password': 'Bearbeiter-Zugang-1'})
check('gesperrt, vertrautes Gerät: normaler Code-Schritt (ohne Sperrhinweis)', st == 200 and r.get('need2fa') and not r.get('gesperrtBis'), (st, r))
st, r = Z2.call('login_2fa', {'code': '000000'})
check('… falscher Code zählt für das Gerät, nicht gegen die 3 Codes der Sperre', st == 401 and 'lockTries' not in nutzer('zora') and nutzer('zora')['geraete'][0]['f'] == 1, (st, nutzer('zora')))
while int(time.time() // 30) + 1 <= zstep: time.sleep(1)
st, r = Z2.call('login_2fa', {'code': totp(sek, int(time.time() // 30) + 1)})
check('… richtiger Code meldet an und hebt die Sperre auf', st == 200 and r.get('user', {}).get('username') == 'zora' and not nutzer('zora').get('lockedUntil'), (st, r))
storage_write('logins', {})

# ---------- Administrator: Meldung bei neuem Gerät ----------
def meldungen():
    return [e for e in (doc('protokoll/' + time.strftime('%Y-%m', time.gmtime())) or []) if e['a'] == 'security' and 'neuen Gerät' in e['s']]


vorher = len(meldungen())
B1 = gleicher_browser(A, '198.51.100.30')
assert B1.call('login', {'username': 'admin', 'password': PW})[0] == 200
check('bekanntes Gerät des Administrators: keine Meldung', len(meldungen()) == vorher, meldungen()[vorher:])
B2 = Client('198.51.100.31')
B2.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'
assert B2.call('login', {'username': 'admin', 'password': PW})[0] == 200
neu = meldungen()[vorher:]
check('neues Gerät des Administrators: Sicherheitsereignis mit Gerätename', len(neu) == 1 and 'Chrome · Windows' in neu[0]['s'], neu)
assert Client('198.51.100.32').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
check('neues Gerät eines Bearbeiters: keine Meldung', len(meldungen()) == vorher + 1)
# Fremde Kennung (z. B. von einer Subdomain untergeschoben) wird nie übernommen
mitk = mit_kennung(E1, 'C' * 43, '198.51.100.34')
st, r = mitk.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
neu_k = kennung(mitk)
check('unbekannte Kennung im Browser wird bei der Anmeldung nicht übernommen, sondern durch eine neue ersetzt', st == 200 and neu_k is not None and neu_k.value != 'C' * 43
      and all(g['h'] != hashlib.sha256(b'wa-geraet|' + b'C' * 43).hexdigest() for g in nutzer('eddi').get('geraete', [])), (st, neu_k and neu_k.value))
storage_write('logins', {})
storage_write('logins', {})

# ---------- Verwaltung: anzeigen und entfernen ----------
st, r = A.call('users')
eu = next(u for u in r['users'] if u['username'] == 'eddi')
check('Nutzerliste zeigt vertraute Geräte ohne Prüfsummen', len(eu['geraete']) == 3 and all(set(x) == {'name', 'seit', 'zuletzt'} for x in eu['geraete']), eu['geraete'])
st, r = A.call('user_save', {'id': eu['id'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'resetGeraete': True})
check('Administrator entfernt vertraute Geräte (mit Protokoll)', st == 200 and not nutzer('eddi').get('geraete')
      and any('Vertraute Geräte' in json.dumps(e.get('d', []), ensure_ascii=False) for e in doc('protokoll/' + time.strftime('%Y-%m', time.gmtime())) or []), (st, r))
versuche('eddi', 3, 5)
st, r = gleicher_browser(E1, '198.51.100.14').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
check('… danach kommt das Gerät während einer Sperre nicht mehr durch', st == 200 and 'user' not in r, (st, r))
A.call('user_unlock', {'id': eu['id']})
storage_write('logins', {})
E4 = gleicher_browser(E1, '198.51.100.15')
assert E4.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
assert Client('198.51.100.16').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
check('zwei Geräte vertraut', len(nutzer('eddi').get('geraete', [])) == 2)
st, r = E4.call('change_password', {'current': 'Editor-Zugang-77', 'password': 'Neues-Kennwort-66'})
check('eigener Passwortwechsel: nur dieses Gerät bleibt vertraut', st == 200 and len(nutzer('eddi').get('geraete', [])) == 1, (st, nutzer('eddi').get('geraete')))
A.call('user_save', {'id': eu['id'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
check('neues Passwort durch den Administrator: kein Gerät mehr vertraut', not nutzer('eddi').get('geraete'))
storage_write('logins', {})
for i in range(12):
    Client(f'198.51.101.{i + 1}').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
    storage_write('logins', {})
check('höchstens 10 Geräte je Zugang (die zuletzt benutzten)', len(nutzer('eddi').get('geraete', [])) == 10)
nutzer_setzen('eddi', geraete=[{**x, 'zuletzt': int(time.time()) - 181 * 86400} for x in nutzer('eddi')['geraete']])
check('unbenutzte Geräte verfallen nach 180 Tagen', next(u for u in A.call('users')[1]['users'] if u['username'] == 'eddi')['geraete'] == [])

# ---------- Kunden ----------
rev = A.call('kunden')[1]['rev']
assert A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Gerät', 'nr': 'KG-1', 'email': 'kg@example.org', 'active': True, 'angebote': ['edeka'],
                             'login': {'username': 'kantine.geraet', 'password': KPW, 'mustChange': False, 'active': True}})[0] == 200
K1 = Client('203.0.113.10')
st, r = K1.call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})
check('Kunde: Anmeldung merkt das Gerät', st == 200 and kennung(K1) is not None and len(kunde('kantine.geraet')['login'].get('geraete', [])) == 1, (st, r))
versuche('kantine.geraet', 3, 6, 'kunde_login')
st, r = Client('203.0.113.11').call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})
check('Kunde gesperrt: ohne vertrautes Gerät weiter gesperrt (429)', st == 429, (st, r))
K2 = gleicher_browser(K1, '203.0.113.12')
st, r = K2.call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})
check('Kunde gesperrt: vertrautes Gerät kommt mit richtigem Passwort hinein', st == 200 and r.get('kunde'), (st, r))
storage_write('logins', {})
versuche('kantine.geraet', 3, 7, 'kunde_login')
K3 = gleicher_browser(K1, '203.0.113.13')
f = [K3.call('kunde_login', {'username': 'kantine.geraet', 'password': 'Falsches-Passwort-1'})[0] for _ in range(5)]
storage_write('logins', {})
st, r = K3.call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})
check('Kunde: 5 falsche Passwörter auf dem Gerät → Gerät nicht mehr vertraut', f == [401] * 5 and st == 429, (f, st))
kunde_setzen('kantine.geraet', lockedUntil=0, failCount=0)
storage_write('logins', {})
assert gleicher_browser(K1, '203.0.113.14').call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})[0] == 200
kd = next(c for c in A.call('kunden')[1]['customers'] if c['nr'] == 'KG-1')
check('Kundenliste zeigt vertraute Geräte ohne Prüfsummen', len(kd['login']['geraete']) == 1 and set(kd['login']['geraete'][0]) == {'name', 'seit', 'zuletzt'}, kd['login'])
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'id': kd['id'], 'firma': kd['firma'], 'nr': kd['nr'], 'email': kd['email'], 'active': True, 'angebote': ['edeka'],
                              'login': {'username': 'kantine.geraet', 'password': '', 'mustChange': False, 'active': True, 'geraeteEntfernen': True}})
check('Verwaltung entfernt die vertrauten Geräte des Kunden', st == 200 and not kunde('kantine.geraet')['login'].get('geraete'), (st, r))
storage_write('logins', {})

# ---------- Oberfläche ----------
assert gleicher_browser(E1, '198.51.100.17').call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
assert gleicher_browser(K1, '203.0.113.15').call('kunde_login', {'username': 'kantine.geraet', 'password': KPW})[0] == 200
storage_write('logins', {})
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    for breite in (1440, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900})
        pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.evaluate("document.querySelector('#vt-users').click()")
        pg.wait_for_selector(f'[data-uedit="{eu["id"]}"]')
        pg.click(f'[data-uedit="{eu["id"]}"]')
        pg.wait_for_selector('#user-body [name=resetGeraete]')
        lab = pg.locator('label:has([name=resetGeraete])')
        lab.scroll_into_view_if_needed()
        pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
        txt = lab.inner_text()
        breit = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        pg.screenshot(path=os.path.join(WORK, f'geraete-nutzer-{breite}.png'))
        check(f'{breite} px: Nutzer-Dialog zeigt „Vertraute Geräte entfernen“ mit Gerät und Zeit, kein waagrechtes Scrollen', '1 Gerät' in txt and 'zuletzt' in txt and not breit, (txt, breit))
        pg.keyboard.press('Escape')
        pg.evaluate("document.querySelector('#vt-kunden').click()")
        pg.wait_for_selector(f'[data-kedit="{kd["id"]}"]')
        pg.click(f'[data-kedit="{kd["id"]}"]')
        lab = pg.locator('label:has([name=geraeteEntfernen])')
        lab.wait_for()
        lab.scroll_into_view_if_needed()
        pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
        ktxt = lab.inner_text()
        pg.screenshot(path=os.path.join(WORK, f'geraete-kunde-{breite}.png'))
        check(f'{breite} px: Kunden-Dialog zeigt „Vertraute Geräte entfernen“', '1 Gerät' in ktxt and not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'), ktxt)
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not errors, errors)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
