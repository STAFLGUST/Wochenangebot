"""Datenleck-Prüfung der Passwörter („Pwned Passwords“, nachgebauter Dienst auf AUX_PORT): standardmäßig aus; eingeschaltet
werden betroffene Passwörter beim Festlegen abgelehnt (Mitarbeiter, Kunden), bestehende bei der Anmeldung einmal geprüft
(muss sofort geändert werden, mit Grund), übertragen werden nur 5 Zeichen des Prüfwerts; Ausfall blockiert nicht und
erscheint in der Konfigurationsprüfung; Protokoll; Oberfläche 1440/390 px. Nur synthetische Testdaten."""
import hashlib
import http.server
import json
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import AUX_PORT, BASE, WORK, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
GELEAKT = 'Konto-Passwort-9'       # gilt im nachgebauten Dienst als 42-mal geleakt
SAUBER = 'Gut-Passwort-2026'
NEU = 'Neues-Kennwort-66'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


ANFRAGEN = []
AUSFALL = {'an': False}
GELEAKT2 = 'Merk-Kennwort-31'        # ebenfalls geleakt (3-mal)
LEAK = hashlib.sha1(GELEAKT.encode()).hexdigest().upper()
LEAKS = {LEAK: 42, hashlib.sha1(GELEAKT2.encode()).hexdigest().upper(): 3}


class Dienst(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ANFRAGEN.append({'pfad': self.path, 'padding': self.headers.get('Add-Padding')})
        if AUSFALL['an']:
            self.send_response(503); self.end_headers(); return
        pre = self.path.rsplit('/', 1)[-1].upper()
        zeilen = [f'{os.urandom(18).hex()[:35].upper()}:0' for _ in range(5)]   # Auffüllung
        for h, n in LEAKS.items():
            if pre == h[:5]:
                zeilen.insert(2, f'{h[5:]}:{n}')
        body = '\r\n'.join(zeilen).encode()
        self.send_response(200); self.send_header('Content-Type', 'text/plain'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Dienst)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def protokoll():
    return doc('protokoll/' + time.strftime('%Y-%m', time.gmtime())) or []


def nutzer(name):
    return next(x for x in doc('nutzer')['users'] if x['username'] == name)


A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200

# ---------- aus (Standard) ----------
S = A.call('security_status')[1]['settings']
check('Datenleck-Prüfung ist standardmäßig aus', S.get('pwLeak') is False, S.get('pwLeak'))
st, r = A.call('user_save', {'username': 'lena', 'name': 'Lena Leck', 'role': 'editor', 'active': True, 'password': GELEAKT, 'mustChange': False})
check('ausgeschaltet: kein Kontakt zum Dienst, Passwort wird angenommen', st == 200 and ANFRAGEN == [], (st, r, ANFRAGEN))
rev = A.call('kunden')[1]['rev']
assert A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Leck', 'nr': 'KL-1', 'email': 'kl@example.org', 'active': True, 'angebote': ['edeka'],
                             'login': {'username': 'kantine.leck', 'password': GELEAKT, 'mustChange': False, 'active': True}})[0] == 200

# ---------- einschalten ----------
st, r = A.call('security_save', {**S, 'pwLeak': True})
check('einschalten über die Sicherheitseinstellungen (mit Protokoll)', st == 200 and r['settings']['pwLeak'] is True
      and any(e['a'] == 'security' and 'Datenlecks' in json.dumps(e.get('d', []), ensure_ascii=False) for e in protokoll()), (st, r))
S2 = r['settings']
st, r = A.call('security_save', {k: v for k, v in S2.items() if k != 'pwLeak'})
check('ältere Oberfläche ohne Feld schaltet nicht versehentlich aus', st == 200 and r['settings']['pwLeak'] is True, r.get('settings', {}).get('pwLeak'))

st, r = A.call('user_save', {'username': 'mia', 'name': 'Mia Muster', 'role': 'editor', 'active': True, 'password': GELEAKT, 'mustChange': False})
check('neues Passwort aus einem Datenleck wird abgelehnt (mit Anzahl)', st == 422 and 'Datenlecks' in r.get('error', '') and '42' in r.get('error', ''), (st, r))
st, r = A.call('user_save', {'username': 'mia', 'name': 'Mia Muster', 'role': 'editor', 'active': True, 'password': SAUBER, 'mustChange': False})
check('unbekanntes Passwort wird angenommen', st == 200, (st, r))
check('übertragen werden nur 5 Zeichen des Prüfwerts (aufgefüllte Antwort angefordert), nie Passwort oder ganzer Prüfwert',
      ANFRAGEN and all(len(a['pfad'].rsplit('/', 1)[-1]) == 5 and a['padding'] == 'true' for a in ANFRAGEN)
      and not any(GELEAKT in a['pfad'] or LEAK in a['pfad'].upper() or LEAK[5:] in a['pfad'].upper() for a in ANFRAGEN), ANFRAGEN)

# ---------- Anmeldung mit bestehendem, betroffenem Passwort ----------
n0 = len(ANFRAGEN)
L = Client('198.51.100.20')
st, r = L.call('login', {'username': 'lena', 'password': GELEAKT})
check('Anmeldung mit betroffenem Passwort: angemeldet, muss sofort ändern (Grund: Datenleck)', st == 200 and r['user']['mustChange'] is True and r['user'].get('mustChangeGrund') == 'datenleck', (st, r))
check('… Sicherheitsereignis im Protokoll', any(e['a'] == 'security' and 'lena' in e['s'] and 'Datenlecks' in e['s'] for e in protokoll()))
check('… geprüft wurde genau einmal', len(ANFRAGEN) == n0 + 1, ANFRAGEN[n0:])
L.call('logout', {})
st, r = Client('198.51.100.21').call('login', {'username': 'lena', 'password': GELEAKT})
check('erneute Anmeldung: keine zweite Prüfung desselben Passworts, Pflicht bleibt', st == 200 and r['user']['mustChange'] and len(ANFRAGEN) == n0 + 1, (len(ANFRAGEN), r.get('user')))
L2 = Client('198.51.100.22')
L2.call('login', {'username': 'lena', 'password': GELEAKT})
st, r = L2.call('change_password', {'current': GELEAKT, 'password': GELEAKT2})
st2, r2 = L2.call('change_password', {'current': GELEAKT, 'password': NEU})
check('… neues Passwort wird ebenfalls geprüft; danach ist die Pflicht weg', st == 422 and '3-mal' in r.get('error', '') and st2 == 200 and not nutzer('lena').get('mustChange') and 'mustChangeGrund' not in nutzer('lena'), (st, r, st2, r2))
st, r = Client('198.51.100.23').call('login', {'username': 'mia', 'password': SAUBER})
check('unauffälliges Passwort: keine Pflicht', st == 200 and not r['user']['mustChange'], r.get('user'))

# ---------- Kunden ----------
K = Client('203.0.113.30')
st, r = K.call('kunde_login', {'username': 'kantine.leck', 'password': GELEAKT})
check('Kunde mit betroffenem Passwort: muss sofort ändern (Grund: Datenleck)', st == 200 and r['kunde']['mustChange'] is True and r['kunde'].get('mustChangeGrund') == 'datenleck', (st, r))
st, r = K.call('kunde_passwort', {'current': GELEAKT, 'password': GELEAKT})
check('… Kunde kann kein Passwort aus einem Datenleck wählen', st == 422, (st, r))
st, r = K.call('kunde_passwort', {'current': GELEAKT, 'password': NEU})
kl = next(c for c in doc('kunden')['customers'] if (c.get('login') or {}).get('username') == 'kantine.leck')['login']
check('… mit sauberem Passwort ist die Pflicht weg', st == 200 and not kl.get('mustChange') and 'mustChangeGrund' not in kl, (st, r))

# ---------- Ausfall des Dienstes ----------
AUSFALL['an'] = True
storage_write('datenleck', {'ok': True, 't': 0})
st, r = A.call('user_save', {'username': 'ole', 'name': 'Ole Ohne', 'role': 'viewer', 'active': True, 'password': GELEAKT, 'mustChange': False})
check('Dienst nicht erreichbar: Passwort wird nicht blockiert', st == 200, (st, r))
cfg = A.call('security_status')[1]
dl = [x for x in cfg.get('config', []) if 'Datenleck' in x.get('title', '')]
check('… Konfigurationsprüfung warnt „zuletzt nicht erreichbar“', len(dl) == 1 and dl[0]['level'] == 'warn' and 'nicht erreichbar' in dl[0]['text'], dl)
st, r = Client('198.51.100.24').call('login', {'username': 'ole', 'password': GELEAKT})
check('… Anmeldung ohne Pflicht, Prüfung beim nächsten Mal', st == 200 and not r['user']['mustChange'] and not nutzer('ole').get('leakGeprueft'), r.get('user'))
n1 = len(ANFRAGEN)
A.call('user_save', {'username': 'pia', 'name': 'Pia Pause', 'role': 'viewer', 'active': True, 'password': GELEAKT, 'mustChange': False})
check('… nach einem Ausfall 10 Minuten Pause (kein Warten bei jeder Anmeldung)', len(ANFRAGEN) == n1, ANFRAGEN[n1:])
AUSFALL['an'] = False
storage_write('datenleck', {'ok': True, 't': 0})   # Pause beenden (wie nach 10 Minuten)

# ---------- Oberfläche ----------
A.call('user_save', {'id': nutzer('mia')['id'], 'name': 'Mia Muster', 'role': 'editor', 'active': True})
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    for breite in (1440, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900})
        pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'ole'); pg.fill('#pw1', GELEAKT); pg.click('#auth-submit')
        pg.wait_for_function("document.querySelector('#auth-intro') && /Datenlecks/.test(document.querySelector('#auth-intro').textContent)")
        breit = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        pg.screenshot(path=os.path.join(WORK, f'datenleck-anmeldung-{breite}.png'))
        check(f'{breite} px: Aufforderung nennt den Grund (Datenleck), kein waagrechtes Scrollen', not breit, breit)
        ctx.close()
        ctx = br.new_context(viewport={'width': breite, 'height': 900})
        pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.evaluate("document.querySelector('#vt-sec').click()")
        box = pg.locator('[name=pwLeak]')
        box.wait_for()
        box.scroll_into_view_if_needed()
        pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
        pg.screenshot(path=os.path.join(WORK, f'datenleck-einstellung-{breite}.png'))
        check(f'{breite} px: Einstellung „Gegen bekannte Datenlecks prüfen“ angehakt, kein waagrechtes Scrollen', box.is_checked() and not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
        ctx.close()
        nu = doc('nutzer')
        for x in nu['users']:
            if x['username'] == 'ole':
                x['mustChange'] = False
                x.pop('leakGeprueft', None)
        storage_write('nutzer', nu)
        storage_write('logins', {})
    br.close()
check('keine JavaScript-Fehler', not errors, errors)

srv.shutdown()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
