"""Direkte HTTP-Regressionen: Faktorwechsel, Sitzungswiderruf und eigene Zugangsdaten."""
import base64
from umgebung import BASE  # Testserver je Gruppe (parallel)
import hashlib
import hmac
import http.cookiejar
import json
import struct
import sys
import time
import urllib.error
import urllib.request

BASE = BASE + '/api/?action='
PW = 'Sicheres-Passwort-1'
results = []


def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name)


class Client:
    def __init__(self, ip='127.0.0.1'):
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
        self.ip = ip

    def call(self, action, data=None):
        headers = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        req = urllib.request.Request(BASE + action, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            response = self.http.open(req)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        try:
            result = json.loads(raw)
        except ValueError:
            raise AssertionError(f'{action}: HTTP {response.code}, invalid JSON: {raw[:1000]!r}')
        if result.get('csrf'):
            self.csrf = result['csrf']
        return response.code, result

    def login(self):
        return self.call('login', {'username': 'admin', 'password': PW})


def code(secret):
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', int(time.time() // 30)), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return '%06d' % ((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000)


a, old = Client(), Client()
check('two independent password sessions', a.login()[0] == 200 and old.login()[0] == 200)
status, pending_old = old.call('twofa_begin', {})
status, pending = a.call('twofa_begin', {})
check('first setup allowed without extra password', status == 200)
status, enabled = a.call('twofa_enable', {'code': code(pending['secret'])})
check('first factor enabled', status == 200 and len(enabled['recovery']) == 10)
check('confirming session remains usable', a.call('draft')[0] == 200)
check('pre-factor session revoked', old.call('draft')[0] == 401)
check('old pending setup cannot overwrite factor', old.call('twofa_enable', {'code': code(pending_old['secret'])})[0] == 401)
check('renewal requires password', a.call('twofa_begin', {})[0] == 422)
check('wrong renewal password rejected', a.call('twofa_begin', {'password': 'Wrong-Password-123'})[0] == 422)
check('enable without authorized setup rejected', a.call('twofa_enable', {'code': code(pending['secret'])})[0] == 409)

me = a.call('status')[1]['user']
profile = {'id': me['id'], 'name': me['name'], 'role': 'admin', 'active': True}
check('own password reset via users rejected', a.call('user_save', {**profile, 'password': 'Changed-Password-123'})[0] == 403)
check('own factor reset via users rejected', a.call('user_save', {**profile, 'reset2fa': True})[0] == 403)
check('own profile edit remains allowed', a.call('user_save', profile)[0] == 200)

other, challenge = Client(), Client()
check('factor required for new login', other.login()[1].get('need2fa') is True)
check('recovery login works', other.call('login_2fa', {'code': enabled['recovery'][0]})[0] == 200)
check('pending login created', challenge.login()[1].get('need2fa') is True)
status, renewal = a.call('twofa_begin', {'password': PW})
check('renewal with password allowed', status == 200)
status, renewed = a.call('twofa_enable', {'code': code(renewal['secret'])})
check('renewal succeeds', status == 200)
check('renewal revokes other full session', other.call('draft')[0] == 401)
check('renewal revokes pending login', challenge.call('login_2fa', {'code': enabled['recovery'][1]})[0] == 401)
check('renewal keeps confirming session', a.call('draft')[0] == 200)
other = Client()
other.login()
check('old recovery code invalid after renewal', other.call('login_2fa', {'code': enabled['recovery'][1]})[0] == 401)
check('new recovery code works', other.call('login_2fa', {'code': renewed['recovery'][0]})[0] == 200)
check('disable requires correct password', a.call('twofa_disable', {'password': 'Wrong-Password-123'})[0] == 422)
check('failed disable preserves other session', other.call('draft')[0] == 200)
check('disable with password succeeds', a.call('twofa_disable', {'password': PW})[0] == 200)
check('disable revokes other session', other.call('draft')[0] == 401)
check('disable keeps confirming session', a.call('draft')[0] == 200)
check('normal login works after disable', Client().login()[1].get('user', {}).get('twofa') is False)
# Bekannte Passwörter dürfen durch neue Sitzungen/IPs keine unbegrenzten 2FA-Versuche ermöglichen.
a.call('security_save', {'lockAfter': 3})
pending = a.call('twofa_begin', {})[1]
enabled = a.call('twofa_enable', {'code': code(pending['secret'])})[1]
waiting = Client('192.0.2.10')
waiting.login()
for i in range(3):
    attacker = Client('192.0.2.' + str(20 + i))
    check('new password step preserves failure count ' + str(i), attacker.login()[1].get('need2fa') is True)
    expected = 429 if i == 2 else 401
    check('account counts factor failure ' + str(i), attacker.call('login_2fa', {'code': 'invalid'})[0] == expected)
# Gesperrt: richtiges Passwort führt zum Code-Schritt (Inhaber nicht aussperrbar), aber nur 3 Code-Versuche je Sperre
for i in range(3):
    attacker = Client('192.0.2.' + str(30 + i))
    check('locked account: password step offers factor ' + str(i), attacker.login()[1].get('need2fa') is True)
    attacker.call('login_2fa', {'code': 'invalid'})
fresh = Client('192.0.2.40')
st, r = fresh.login()
check('after 3 factor tries during lock: password step answers unchanged (reveals nothing)', st == 200 and r.get('need2fa') is True)
check('… but even a valid recovery code is refused (no factor tries left)', fresh.call('login_2fa', {'code': enabled['recovery'][0]})[0] == 401)
check('account lock blocks existing challenge and valid recovery', waiting.call('login_2fa', {'code': enabled['recovery'][0]})[0] == 429)
check('existing authenticated session can unlock account', a.call('user_unlock', {'id': me['id']})[0] == 200)
recovered = Client('192.0.2.31')
recovered.login()
check('blocked recovery was not consumed', recovered.call('login_2fa', {'code': enabled['recovery'][0]})[0] == 200)
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
