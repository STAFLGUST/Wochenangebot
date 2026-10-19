"""Schnittstelle für die App (docs/app-api.md): Grunddaten, Sitzung über Kopfzeile statt Cookie, gleiche Regeln wie im Browser."""
import base64
import hashlib
import hmac
import json
import struct
import sys
import time
import urllib.error
import urllib.request

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SMTP_PORT, storage_raw

API = BASE + '/api/?action='
PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
res = []


def check(n, c):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n)


class App:
    """Verhält sich wie die App: kein Cookie-Speicher, Sitzungskennung aus der Antwort-Kopfzeile X-WA-Sitzung."""
    def __init__(self, ip='203.0.113.7'):
        self.sid = ''
        self.csrf = ''
        self.ip = ip
        self.extra = {}
        self.last = {}

    def call(self, action, data=None, client='app', send_sid=True):
        h = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf,
             'User-Agent': 'StandardFleischApp/1.0 (iOS 19)', **self.extra}
        if client:
            h['X-WA-Client'] = client
        if send_sid and self.sid:
            h['X-WA-Sitzung'] = self.sid
        req = urllib.request.Request(API + action, data=None if data is None else json.dumps(data).encode(), headers=h)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            r = e
        self.last = {k.lower(): v for k, v in r.headers.items()}
        if 'x-wa-sitzung' in self.last:
            self.sid = self.last['x-wa-sitzung']
        body = r.read()
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        if isinstance(j, dict) and j.get('csrf'):
            self.csrf = j['csrf']
        return r.code, j


def totp(secret):
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', int(time.time() // 30)), hashlib.sha1).digest()
    o = digest[-1] & 15
    return '%06d' % ((struct.unpack('>I', digest[o:o + 4])[0] & 0x7fffffff) % 1000000)


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
admin = Client('198.51.100.2')
assert admin.call('login', {'username': 'admin', 'password': PW})[0] == 200

# ---------- Grunddaten ----------
st, info = App().call('app_info')
check('app_info öffentlich erreichbar', st == 200 and info.get('ok'))
check('app_info nennt Version und Mindestversion', info.get('apiVersion') == 1 and info.get('minAppVersion', '').count('.') == 2)
check('app_info nennt Bestellfunktion (aus) und Links', info.get('bestellfunktion') is False and info['links']['datenschutz'] == '/datenschutz/')
a0 = App(); a0.call('app_info')
check('app_info setzt kein Cookie und keine Sitzung', 'set-cookie' not in a0.last and 'x-wa-sitzung' not in a0.last)

# ---------- Kunde und Bestellfunktion vorbereiten ----------
rev = admin.call('kunden')[1]['rev']
r = admin.call('kunde_save', {'rev': rev, 'firma': 'App Kantine', 'nr': 'app.kantine', 'email': 'app.kantine@example.org', 'active': True, 'angebote': ['std'],
                              'login': {'username': 'app.kantine', 'password': KPW, 'mustChange': False, 'active': True}})
assert r[0] == 200, r
kid = r[1]['customer']['id']
assert admin.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
check('app_info zeigt eingeschaltete Bestellfunktion', App().call('app_info')[1]['bestellfunktion'] is True)

# ---------- Sitzung über Kopfzeile ----------
k = App()
st, s = k.call('kunde_status')
first = k.sid
check('Kopfzeile X-WA-Sitzung statt Cookie', st == 200 and len(first) >= 22 and 'set-cookie' not in k.last)
check('Antworten mit Sitzung nicht zwischenspeichern', 'no-store' in k.last.get('cache-control', ''))
st, j = k.call('kunde_login', {'username': 'app.kantine', 'password': KPW})
check('Kunden-Anmeldung in der App', st == 200 and j['kunde']['firma'] == 'App Kantine' and k.csrf)
check('Anmeldung vergibt neue Kennung (keine Sitzungsfixierung)', k.sid and k.sid != first and 'set-cookie' not in k.last)
st, s = k.call('kunde_status')
check('Folgeanfrage mit Kennung ist angemeldet', s.get('kunde') and s['kunde']['username'] == 'app.kantine' and s.get('csrf') == k.csrf and s.get('bestellung') is True)

ohne = App(); ohne.sid = k.sid
check('Kennung ohne X-WA-Client wird nicht angenommen', ohne.call('kunde_status', client=None)[1].get('kunde') is None)
falsch = App(); falsch.sid = 'a' * 26
st, s = falsch.call('kunde_status')
check('erfundene Kennung wird verworfen und ersetzt', s.get('kunde') is None and falsch.sid != 'a' * 26)
kaputt = App(); kaputt.sid = '../../etc/passwd'
st, s = kaputt.call('kunde_status')
check('ungültige Kennung abgewiesen', st == 200 and s.get('kunde') is None and kaputt.sid != '../../etc/passwd')

browser = Client('203.0.113.8')
browser.call('kunde_login', {'username': 'app.kantine', 'password': KPW})
st, body, raw = browser.call('kunde_status', raw=True)
check('Browser bleibt bei Cookie (unverändert)', body.get('kunde') is not None and 'X-WA-Sitzung' not in raw)
browser.headers['X-WA-Client'] = 'app'
check('Cookie wird in der App-Betriebsart nicht gelesen', browser.call('kunde_status')[1].get('kunde') is None)
del browser.headers['X-WA-Client']
check('Browser-Sitzung danach weiter gültig', browser.call('kunde_status')[1].get('kunde') is not None)

# ---------- Kundenfunktionen über die App ----------
old = k.csrf; k.csrf = 'falsch'
check('CSRF-Prüfung gilt auch in der App', k.call('kunde_merkliste_save', {'keys': ['x']})[0] == 403)
k.csrf = old
check('Merkliste speichern und lesen', k.call('kunde_merkliste_save', {'keys': ['10601|roastbeef|x']})[0] == 200 and
      k.call('kunde_merkliste')[1].get('keys') == ['10601|roastbeef|x'])
st, off = k.call('offer')
check('Angebot in der App', st == 200 and off['offer']['items'] and off['fracht']['frei'] == 300)
item = off['offer']['items'][0]
payload = {'angebot': 'std', 'publishedAt': off['offer']['publishedAt'], 'positions': [{'id': item['id'], 'qty': 120}],
           'referenz': 'App-Test', 'requestId': 'app-request-0001-abcdef'}
st, o = k.call('kunde_bestellung', payload)
check('Bestellwunsch aus der App gespeichert', st == 200 and o.get('nr'))
check('Frachtanteil serverseitig berechnet (120 kg → 35 €)', isinstance(o.get('fracht'), dict) and o['fracht'].get('kosten') == 35)
st, o2 = k.call('kunde_bestellung', payload)
check('Wiederholung nach Verbindungsabbruch ohne zweite Bestellung', st == 200 and o2.get('replayed') and o2['nr'] == o['nr'])
st, lst = k.call('kunde_bestellungen')
check('eigene Bestellwünsche in der App', st == 200 and lst['total'] == 1 and lst['orders'][0]['nr'] == o['nr'])
st, det = k.call('kunde_bestellung_detail&nr=' + o['nr'])
check('Detail ohne interne Felder', st == 200 and all(x not in det['order'] for x in ['note', 'history', 'assignee', 'kunde', 'requestId']))
time.sleep(0.2)
raw_orte = storage_raw('anmeldeorte') or ''
check('Auswertung kennzeichnet Anmeldungen aus der App', '"dev":"app"' in raw_orte.replace(' ', ''))

# ---------- Widerruf ----------
assert browser.call('kunde_passwort', {'current': KPW, 'password': 'Neues-Kennwort-66'})[0] == 200
check('Passwortwechsel auf anderem Gerät meldet die App ab', k.call('kunde_status')[1].get('kunde') is None)
k2 = App()
k2.call('kunde_login', {'username': 'app.kantine', 'password': 'Neues-Kennwort-66'})
sid_vorher = k2.sid
st, j = k2.call('kunde_logout', {})
check('Abmelden in der App', st == 200 and k2.last.get('x-wa-sitzung', 'x') in ('', sid_vorher))
k2.sid = sid_vorher
check('nach dem Abmelden ist die Kennung wertlos', k2.call('kunde_status')[1].get('kunde') is None)

# ---------- Mitarbeiter mit Zwei-Faktor ----------
admin.call('user_save', {'username': 'app.editor', 'name': 'App Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
web = Client('198.51.100.9')
assert web.call('login', {'username': 'app.editor', 'password': 'Editor-Zugang-77'})[0] == 200
st, pend = web.call('twofa_begin', {})
assert st == 200, pend
assert web.call('twofa_enable', {'code': totp(pend['secret'])})[0] == 200
used_step = int(time.time() // 30)
m = App('203.0.113.20')
st, j = m.call('login', {'username': 'app.editor', 'password': 'Editor-Zugang-77'})
step1 = m.sid
check('Mitarbeiter: Passwort allein reicht nicht', st == 200 and j.get('need2fa') and not m.csrf)
check('Mitarbeiter: Liste vor dem zweiten Faktor gesperrt', m.call('bestellungen')[0] == 401)
falsch2 = App('203.0.113.21')
check('zweiter Schritt braucht die Sitzung des ersten', falsch2.call('login_2fa', {'code': totp(pend['secret'])})[0] == 401)
while int(time.time() // 30) <= used_step or int(time.time()) % 30 > 27:   # ein Code gilt nur einmal; nicht kurz vor dem Wechsel
    time.sleep(0.5)
st, j = m.call('login_2fa', {'code': totp(pend['secret'])})
check('Mitarbeiter: Anmeldung mit Code in der App', st == 200 and j['user']['role'] == 'editor' and m.csrf and m.sid != step1)
st, lst = m.call('bestellungen')
check('Mitarbeiter: Bestellwünsche in der App', st == 200 and any(x['nr'] == o['nr'] for x in lst['orders']))
st, d = m.call('bestellung&nr=' + o['nr'])
st, sv = m.call('bestellung_save', {'nr': o['nr'], 'revision': d['order']['revision'], 'workflow': 'in_bearbeitung', 'assignee': '', 'note': 'aus der App'})
check('Mitarbeiter: Status aus der App ändern', st == 200 and sv['order']['workflow'] == 'in_bearbeitung')
check('Mitarbeiter: veraltete Revision abgewiesen', m.call('bestellung_save', {'nr': o['nr'], 'revision': d['order']['revision'], 'workflow': 'neu', 'assignee': '', 'note': ''})[0] == 409)
k3 = App()
k3.call('kunde_login', {'username': 'app.kantine', 'password': 'Neues-Kennwort-66'})
check('Kunde sieht den Stand aus der App', k3.call('kunde_bestellung_detail&nr=' + o['nr'])[1]['order']['workflow'] == 'in_bearbeitung')
check('Mitarbeiter-Sitzung erscheint im Sitzungsregister', 'StandardFleischApp' in (storage_raw('sitzungen') or ''))
raw_reg = storage_raw('sitzungen') or '{}'
reg = json.loads(raw_reg.split('\n', 1)[1] if raw_reg.startswith('<?php') else raw_reg)
uid = next(v['uid'] for v in reg.values() if 'StandardFleischApp' in v.get('ua', ''))
st, j = admin.call('session_end', {'uid': uid})
check('Administrator beendet die App-Sitzung', st == 200 and j['ended'] >= 1 and m.call('bestellungen')[0] == 401)

# ---------- Wartung ----------
assert admin.call('wartung_save', {'active': True, 'message': 'Kurze Pause', 'until': ''})[0] == 200
st, info = App().call('app_info')
check('Wartung in app_info (ohne Namen des Mitarbeiters)', info['wartung'] and info['wartung']['message'] == 'Kurze Pause' and 'by' not in info['wartung'])
st, j = App().call('kunde_login', {'username': 'app.kantine', 'password': 'Neues-Kennwort-66'})
check('Kunden-Anmeldung während Wartung pausiert', st == 503 and j.get('wartung'))
admin.call('wartung_save', {'active': False, 'message': '', 'until': ''})

smtp.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
