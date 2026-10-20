"""Passkeys (WebAuthn) für Mitarbeiter-Zugänge.

Browser: virtueller Authenticator über CDP (Chromium) – Einrichtung, Anmeldung ohne Benutzername, zweiter Schritt,
Pflicht-Einrichtung, Entfernen, Nutzerverwaltung, Oberfläche. Schnittstelle: eigener Software-Authenticator
(ES256/RS256 mit `cryptography`) für manipulierte Antworten (Herkunft, Challenge, Flags, Signatur, Zähler).
WebAuthn erlaubt keine IP-Adressen als rpId – deshalb läuft alles über http://localhost:<Port>.
"""
import base64, hashlib, hmac, http.cookiejar, json, os, re, struct, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from umgebung import BASE, WORK, storage_raw, storage_write, until, wait_text
from auth_helpers import read_users

B = BASE.replace('127.0.0.1', 'localhost')          # sichere Umgebung ohne HTTPS, gültige rpId
PORT = urllib.parse.urlparse(BASE).port
HOST = f'localhost:{PORT}'
ORIGIN = B
RP = 'localhost'
API = BASE + '/api/?action='
PW = 'Sicheres-Passwort-1'
SHOTS = os.path.join(WORK, 'passkeys')
os.makedirs(SHOTS, exist_ok=True)

res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b'=').decode()
def unb64u(s): return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
def sha(b): return hashlib.sha256(b).digest()
def totp(secret, step=None):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    step = int(time.time() // 30) if step is None else step
    h = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    o = h[19] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)

def doc(name):
    raw = storage_raw(name)
    if raw is None: return None
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)
def user(name): return next(u for u in read_users()['users'] if u['username'] == name)
def log(): return doc('protokoll/' + time.strftime('%Y-%m', time.gmtime())) or []
def logged(a, text, who=None):
    return any(e['a'] == a and text in e['s'] and (who is None or e['u'] == who) for e in log())
def set_user(name, **kw):
    data = read_users()
    for u in data['users']:
        if u['username'] == name: u.update(kw)
    storage_write('nutzer', data)
def session_set(sid, php):
    subprocess.run(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-r',
                    'session_id($argv[1]); session_start(); ' + php + ' session_write_close();', sid], check=True)

# ---------- CBOR (nur Kodieren) und Software-Authenticator ----------
def _head(m, n):
    if n < 24: return bytes([m << 5 | n])
    for ai, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if n < 256 ** size: return bytes([m << 5 | ai]) + n.to_bytes(size, 'big')
def cbor(v):
    if isinstance(v, bool): return b'\xf5' if v else b'\xf4'
    if isinstance(v, int): return _head(0, v) if v >= 0 else _head(1, -1 - v)
    if isinstance(v, bytes): return _head(2, len(v)) + v
    if isinstance(v, str): return _head(3, len(v.encode())) + v.encode()
    if isinstance(v, list): return _head(4, len(v)) + b''.join(cbor(x) for x in v)
    if isinstance(v, dict): return _head(5, len(v)) + b''.join(cbor(k) + cbor(x) for k, x in v.items())
    raise TypeError(v)

class SoftKey:
    def __init__(self, alg=-7):
        self.alg, self.cid, self.count = alg, os.urandom(32), 0
        if alg == -7:
            self.key = ec.generate_private_key(ec.SECP256R1())
            n = self.key.public_key().public_numbers()
            self.cose = {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, 'big'), -3: n.y.to_bytes(32, 'big')}
        else:
            self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            n = self.key.public_key().public_numbers()
            self.cose = {1: 3, 3: -257, -1: n.n.to_bytes(256, 'big'), -2: n.e.to_bytes(3, 'big')}
    @property
    def id(self): return b64u(self.cid)
    def sign(self, data):
        if self.alg == -7: return self.key.sign(data, ec.ECDSA(hashes.SHA256()))
        return self.key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    def register(self, opts, origin=ORIGIN, rp=RP, flags=0x45, typ='webauthn.create', challenge=None, fmt='none', cose=None, name=''):
        cd = json.dumps({'type': typ, 'challenge': challenge or opts['challenge'], 'origin': origin, 'crossOrigin': False}).encode()
        ad = sha(rp.encode()) + bytes([flags]) + (0).to_bytes(4, 'big') + bytes(16) + len(self.cid).to_bytes(2, 'big') + self.cid + cbor(cose or self.cose)
        att = cbor({'fmt': fmt, 'attStmt': {}, 'authData': ad})
        return {'id': self.id, 'clientDataJSON': b64u(cd), 'attestationObject': b64u(att), 'transports': ['internal', 'quatsch'], 'name': name}
    def assertion(self, opts, origin=ORIGIN, rp=RP, flags=0x05, typ='webauthn.get', challenge=None, count=None, handle=None, bad_sig=False):
        if count is None:
            self.count += 1; count = self.count
        ad = sha(rp.encode()) + bytes([flags]) + count.to_bytes(4, 'big')
        cd = json.dumps({'type': typ, 'challenge': challenge or opts['challenge'], 'origin': origin, 'crossOrigin': False}).encode()
        sig = self.sign(b'anderes' if bad_sig else ad + sha(cd))
        return {'id': self.id, 'clientDataJSON': b64u(cd), 'authenticatorData': b64u(ad), 'signature': b64u(sig), 'userHandle': b64u(handle.encode()) if handle else None}

class PkClient:
    """Schnittstelle mit Host „localhost:<Port>“ (wie der Browser), eigene IP je Client (Anmeldeversuche je IP)."""
    def __init__(self, ip='192.0.2.1', app=False):
        self.cookies = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf, self.ip, self.app, self.sid = '', ip, app, ''
    def call(self, action, data=None):
        h = {'Host': HOST, 'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        if self.app:
            h['X-WA-Client'] = 'app'
            if self.sid: h['X-WA-Sitzung'] = self.sid
        req = urllib.request.Request(API + action, data=None if data is None else json.dumps(data).encode(), headers=h)
        try: r = self.http.open(req, timeout=30)
        except urllib.error.HTTPError as e: r = e
        if r.headers.get('X-WA-Sitzung') is not None: self.sid = r.headers.get('X-WA-Sitzung')
        out = json.loads(r.read())
        if out.get('csrf'): self.csrf = out['csrf']
        return r.code, out
    def login(self, name, pw): return self.call('login', {'username': name, 'password': pw})
    def cookie(self): return next(c.value for c in self.cookies if c.name == 'WA_ADMIN')
    def pk_login(self, key, second=False, **kw):
        st, o = self.call('passkey_login_begin', {'second': second})
        if st != 200: return st, o
        return self.call('passkey_login', key.assertion(o['options'], **kw))
    def pk_register(self, key, password=PW, **kw):
        st, o = self.call('passkey_begin', {'password': password})
        if st != 200: return st, o
        return self.call('passkey_register', key.register(o['options'], **kw))

# ---------- Browser-Hilfen ----------
def vauth(pg):
    cdp = pg.context.new_cdp_session(pg)
    cdp.send('WebAuthn.enable')
    cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
                                                              'hasUserVerification': True, 'isUserVerified': True}})
    return cdp
def login(pg, name, pw, wait=True):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', name); pg.fill('#pw1', pw); pg.click('#auth-submit')
    if wait: pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def logout(pg):
    pg.click('#btn-more'); pg.click('[data-act="logout"]'); pg.wait_for_selector('#screen-auth:not([hidden]) #auth-submit')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, body: JSON.stringify(b)});
      let j = null; try { j = await r.json(); } catch (e) {} return [r.status, j]; }""", [action, body])
def get(pg, action):
    return pg.evaluate("async (a) => { const r = await fetch('../api/?action=' + a); let j = null; try { j = await r.json(); } catch (e) {} return [r.status, j]; }", action)
def status(pg): return get(pg, 'status')[1]
def confirm(pg): return post(pg, 'reauth', {'password': PW})   # Verwaltungsaktionen bestätigen (gilt 5 Minuten)
def open_pk(pg):
    pg.click('#btn-more'); pg.click('[data-act="passkeys"]'); pg.wait_for_selector('#dlg-passkeys #pk-form')
def no_overflow(pg, sel='body'):
    return pg.evaluate("(s) => { const e = document.querySelector(s); return e.scrollWidth <= e.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; }", sel)

errs = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    a.on('pageerror', lambda e: errs.append(str(e)))
    vauth(a)

    # ===== Anmeldemaske und Einrichtung (Administrator) =====
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    check('login screen offers passkey login', a.locator('#auth-passkey').is_visible() and 'Mit Passkey anmelden' in a.inner_text('#auth-passkey'))
    a.screenshot(path=SHOTS + '/login-desktop.png')
    login(a, 'admin', PW)
    other = br.new_context().new_page(); login(other, 'admin', PW)
    check('menu has passkey item next to two-factor', a.locator('#menu-more [data-act="passkeys"]').count() == 1
          and a.evaluate("document.querySelector('[data-act=twofa]').nextElementSibling.dataset.act") == 'passkeys')
    open_pk(a)
    check('dialog shows empty state', 'Noch kein Passkey' in a.inner_text('#dlg-passkeys'))
    a.fill('#pk-form [name="name"]', 'Laptop Büro'); a.fill('#pk-form [name="password"]', 'Falsches-Passwort-1'); a.click('#pk-submit')
    wait_text(a, '#pk-err', 'nicht korrekt')
    check('registration needs the correct password', 'nicht korrekt' in a.inner_text('#pk-err') and not user('admin').get('passkeys'))
    a.fill('#pk-form [name="name"]', 'Laptop Büro'); a.fill('#pk-form [name="password"]', PW); a.click('#pk-submit')
    a.wait_for_selector('#dlg-passkeys .pk-item')
    check('passkey listed with name', a.input_value('#dlg-passkeys .pk-name') == 'Laptop Büro')
    check('list shows created date and unused', 'Hinzugefügt' in a.inner_text('#dlg-passkeys .pk-item') and 'noch nicht verwendet' in a.inner_text('#dlg-passkeys .pk-item'))
    pk = (user('admin').get('passkeys') or [{}])[0]
    check('stored: id, PEM key, ES256, counter, dates', isinstance(pk.get('id'), str) and len(unb64u(pk['id'])) >= 16 and pk.get('publicKey', '').startswith('-----BEGIN PUBLIC KEY-----')
          and pk.get('alg') == -7 and isinstance(pk.get('signCount'), int) and pk.get('created') and pk.get('lastUsed') is None, {k: v for k, v in pk.items() if k != 'publicKey'})
    check('registration ends other sessions', get(other, 'draft')[0] == 401)
    check('registering session stays', get(a, 'draft')[0] == 200)
    check('audit: passkey added', logged('twofa', 'Passkey „Laptop Büro“ hinzugefügt', 'admin'))
    st, us = get(a, 'users'); raw = json.dumps(us)
    check('user list shows only the count', st == 200 and next(u for u in us['users'] if u['username'] == 'admin')['passkeys'] == 1 and 'BEGIN PUBLIC KEY' not in raw and pk['id'] not in raw)
    st, pl = get(a, 'passkey_list'); raw = json.dumps(pl)
    check('own list without key material', st == 200 and len(pl['passkeys']) == 1 and set(pl['passkeys'][0]) == {'ref', 'name', 'created', 'lastUsed'} and pk['id'] not in raw and 'BEGIN' not in raw)
    check('status reports passkey count', status(a)['user']['passkeys'] == 1)
    st, r = post(a, 'passkey_begin', {})
    check('another passkey needs the password', st == 422 and r.get('code') == 'confirmation_invalid', (st, r))
    for scheme, w in (('light', 1440), ('dark', 1440), ('light', 390), ('dark', 390)):
        a.emulate_media(color_scheme=scheme); a.set_viewport_size({'width': w, 'height': 900 if w > 400 else 844})
        a.screenshot(path=f'{SHOTS}/dialog-{w}-{scheme}.png')
        if w == 390: check(f'dialog fits 390 px ({scheme})', a.evaluate("(() => { const d = document.querySelector('#dlg-passkeys'); return d.scrollWidth <= d.clientWidth + 1 && d.getBoundingClientRect().right <= innerWidth + 1; })()"))
    a.emulate_media(color_scheme='light'); a.set_viewport_size({'width': 1440, 'height': 950})
    a.fill('#dlg-passkeys .pk-name', 'Laptop Büro 2'); a.press('#dlg-passkeys .pk-name', 'Enter')
    wait_text(a, '#toast', 'Name gespeichert')
    check('rename saved', until(lambda: user('admin')['passkeys'][0]['name'] == 'Laptop Büro 2'))
    a.press('#dlg-passkeys .pk-name', 'Escape')

    # ===== Anmeldung ohne Benutzername =====
    logout(a)
    a.click('#auth-passkey'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('passkey login without username or code', status(a)['user']['username'] == 'admin' and a.locator('#au-code-wrap').is_hidden())
    check('audit: login with passkey', logged('login', 'Angemeldet (mit Passkey)', 'admin'))
    pk = user('admin')['passkeys'][0]
    check('last used and counter updated', pk['lastUsed'] and pk['signCount'] > 0, pk['signCount'])
    n = br.new_context().new_page()
    n.add_init_script('delete window.PublicKeyCredential;')
    n.goto(B + '/admin/'); n.wait_for_selector('#screen-auth:not([hidden])')
    check('passkey button hidden without browser support', n.locator('#auth-passkey').is_hidden())
    n.context.close()

    # ===== Authenticator-App + Passkey: Passkey als zweiter Schritt =====
    st, r = post(a, 'twofa_begin', {'password': PW}); secret = r['secret']
    st, r = post(a, 'twofa_enable', {'code': totp(secret)})
    check('admin also sets up TOTP', st == 200 and r['user']['twofa'] and r['user']['passkeys'] == 1)
    logout(a)
    login(a, 'admin', PW, wait=False); a.wait_for_selector('#au-code-wrap:not([hidden])')
    check('code step offers passkey instead', a.locator('#auth-passkey').is_visible() and 'Stattdessen Passkey verwenden' in a.inner_text('#auth-passkey'))
    a.click('#auth-passkey'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('second step with passkey', status(a)['user']['username'] == 'admin')
    check('audit: password and passkey', logged('login', 'Angemeldet (mit Passwort und Passkey)', 'admin'))
    st, r = PkClient('192.0.2.2').login('admin', PW)
    check('password login names both methods', r.get('need2fa') and r.get('methods') == ['totp', 'passkey'], r)
    st, r = PkClient('192.0.2.3', app=True).login('admin', PW)
    check('app gets only the code step', r.get('need2fa') and r.get('methods') == ['totp'], r)

    # ===== Nur Passkey: Passwort-Anmeldung verlangt den Passkey =====
    confirm(a)
    st, r = post(a, 'user_save', {'name': 'Pia Muster', 'username': 'pia', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
    check('editor created', st == 200, r)
    pctx = br.new_context(viewport={'width': 390, 'height': 844})
    pg = pctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e))); vauth(pg)
    login(pg, 'pia', 'Editor-Zugang-77')
    open_pk(pg); pg.fill('#pk-form [name="password"]', 'Editor-Zugang-77'); pg.click('#pk-submit'); pg.wait_for_selector('#dlg-passkeys .pk-item')
    check('default name "Passkey 1"', pg.input_value('#dlg-passkeys .pk-name') == 'Passkey 1')
    pg.screenshot(path=SHOTS + '/dialog-390-list.png')
    check('dialog with entry fits 390 px', no_overflow(pg))
    pg.keyboard.press('Escape')
    logout(pg)
    pg.fill('#au-user', 'pia'); pg.fill('#pw1', 'Editor-Zugang-77'); pg.click('#auth-submit')
    pg.wait_for_selector('#auth-submit:has-text("Mit Passkey bestätigen")')
    check('passkey-only user: passkey step after password', pg.locator('#au-code-wrap').is_hidden() and 'Passkey' in pg.inner_text('#auth-intro') and pg.locator('#auth-passkey').is_hidden())
    pg.screenshot(path=SHOTS + '/passkey-step-390.png')
    check('passkey step fits 390 px', no_overflow(pg))
    pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('passkey step completes login', status(pg)['user']['username'] == 'pia')
    c = PkClient('192.0.2.4')
    st, r = c.login('pia', 'Editor-Zugang-77')
    check('API: passkey-only → need2fa with passkey', st == 200 and r.get('need2fa') and r.get('methods') == ['passkey'], r)
    check('password alone is no login', c.call('draft')[0] == 401)
    check('TOTP step impossible without app', c.call('login_2fa', {'code': '123456'})[0] == 401)
    st, r = PkClient('192.0.2.5', app=True).login('pia', 'Editor-Zugang-77')
    check('app: passkey-only user gets clear error', st == 403 and r.get('code') == 'app_totp_required' and 'Authenticator-App' in r.get('error', ''), r)
    st, r = PkClient('192.0.2.6', app=True).call('passkey_login_begin', {})
    check('app: no passkey login', st == 403 and 'App' in r.get('error', ''), r)

    # ===== Zwei-Faktor-Pflicht: Passkey genügt =====
    confirm(a)
    st, r = post(a, 'security_save', {'twofa': 'all'})
    check('2FA requirement for all saved', st == 200, r)
    check('passkey-only user satisfies requirement', get(pg, 'draft')[0] == 200 and status(pg)['user']['needTwofa'] is False)
    st, r = post(a, 'user_save', {'name': 'Lea Muster', 'username': 'lea', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    lctx = br.new_context(viewport={'width': 1440, 'height': 950}); lg = lctx.new_page(); lg.on('pageerror', lambda e: errs.append(str(e))); vauth(lg)
    login(lg, 'lea', 'Leserin-Zugang-1', wait=False); lg.wait_for_selector('#auth-twofa .tf-qr svg')
    check('required setup offers passkey', lg.locator('#auth-passkey').is_visible() and 'Stattdessen Passkey einrichten' in lg.inner_text('#auth-passkey'))
    check('API blocked before setup', get(lg, 'draft')[0] == 403)
    lg.screenshot(path=SHOTS + '/required-setup.png')
    lg.click('#auth-passkey'); lg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('passkey fulfils requirement', get(lg, 'draft')[0] == 200 and status(lg)['user']['needTwofa'] is False and status(lg)['user']['passkeys'] == 1)
    ref = get(pg, 'passkey_list')[1]['passkeys'][0]['ref']
    st, r = post(pg, 'passkey_delete', {'ref': ref, 'password': 'Editor-Zugang-77'})
    check('last factor cannot be removed under requirement', st == 422 and 'vorgeschrieben' in r['error'], r)
    confirm(a)
    st, r = post(a, 'security_save', {'twofa': 'off'})
    check('requirement switched off', st == 200, r)

    # ===== Eigenen Passkey entfernen =====
    open_pk(pg); pg.click('#dlg-passkeys [data-pkdel]')
    check('removal asks for password', pg.locator('#pk-form [name="password"]').is_visible() and 'entfernen' in pg.inner_text('#pk-form .pk-h'))
    pg.fill('#pk-form [name="password"]', 'Falsches-Passwort-1'); pg.click('#pk-submit'); wait_text(pg, '#pk-err', 'nicht korrekt')
    check('wrong password keeps passkey', 'nicht korrekt' in pg.inner_text('#pk-err') and len(user('pia').get('passkeys', [])) == 1)
    pg.fill('#pk-form [name="password"]', 'Editor-Zugang-77'); pg.click('#pk-submit')
    pg.wait_for_selector('#dlg-passkeys .hint:has-text("Noch kein Passkey")')
    check('passkey removed', 'passkeys' not in user('pia'))
    check('audit: passkey removed', logged('twofa', 'Passkey „Passkey 1“ entfernt', 'pia'))
    st, r = PkClient('192.0.2.7').login('pia', 'Editor-Zugang-77')
    check('without passkey: password login again', st == 200 and not r.get('need2fa') and r.get('user', {}).get('passkeys') == 0, r)

    # ===== Administrator entfernt Passkeys eines Nutzers =====
    a.click('#vt-users'); a.wait_for_selector('#view-users tr[data-uid]')
    row = a.locator('#view-users tr[data-uid]', has_text='lea')
    check('user list shows passkey badge', row.locator('.pk-badge').inner_text().strip() == 'Passkey')
    row.locator('[data-uedit]').click(); a.wait_for_selector('#dlg-user [name="resetPasskeys"]')
    a.check('#dlg-user [name="resetPasskeys"]'); a.click('#dlg-user [type="submit"]')
    a.wait_for_function("document.querySelector('#dlg-reauth').open || !document.querySelector('#dlg-user').open")
    if a.locator('#dlg-reauth[open]').count():
        a.fill('#reauth-password', PW); a.click('#reauth-submit')
    a.wait_for_function("!document.querySelector('#dlg-user').open")
    check('admin removed all passkeys', until(lambda: 'passkeys' not in user('lea')))
    check('user sessions ended', get(lg, 'draft')[0] == 401)
    check('audit: passkeys removed by admin', any(e['a'] == 'user' and any(d.get('f') == 'Passkeys' and d.get('to') == 'alle entfernt' for d in e.get('d', [])) for e in log()))
    me_id = status(a)['user']['id']
    confirm(a)
    st, r = post(a, 'user_save', {'id': me_id, 'name': 'Administrator', 'role': 'admin', 'active': True, 'resetPasskeys': True})
    check('own passkeys not via user management', st == 403 and len(user('admin')['passkeys']) == 1, (st, r))
    a.screenshot(path=SHOTS + '/users.png')

    # ===== Schnittstelle mit Software-Authenticator =====
    confirm(a)
    st, r = post(a, 'user_save', {'name': 'Tom Muster', 'username': 'tom', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    t = PkClient('192.0.2.10')
    st, r = t.login('tom', 'Bearbeiter-Zugang-1'); tom_id = r['user']['id']
    st, r = t.call('passkey_begin', {})
    check('right after login without factor: no password (like TOTP)', st == 200, r)
    session_set(t.cookie(), '$_SESSION["authAt"] = time() - 301;')
    st, r = t.call('passkey_begin', {})
    check('later: password required', st == 422 and r.get('code') == 'confirmation_invalid', r)
    st, r = t.call('passkey_begin', {'password': 'Bearbeiter-Zugang-1'}); o = r['options']
    check('options: rp, user, algorithms, resident key, UV, none',
          o['rp']['id'] == 'localhost' and unb64u(o['user']['id']).decode() == tom_id and o['user']['name'] == 'tom' and [x['alg'] for x in o['pubKeyCredParams']] == [-7, -257]
          and o['authenticatorSelection']['residentKey'] == 'required' and o['authenticatorSelection']['userVerification'] == 'required' and o['attestation'] == 'none'
          and len(unb64u(o['challenge'])) == 32, o)
    k1 = SoftKey(-7)
    bad_regs = [('wrong origin', {'origin': 'http://evil.example'}), ('wrong challenge', {'challenge': b64u(os.urandom(32))}), ('wrong type', {'typ': 'webauthn.get'}),
                ('no user verification', {'flags': 0x41}), ('no attested data', {'flags': 0x05}), ('other rpId', {'rp': 'example.org'}),
                ('unsupported algorithm', {'cose': {1: 1, 3: -8, -1: 6, -2: os.urandom(32)}})]
    st, r = t.call('passkey_register', k1.register(o))
    check('register with ES256 key', st == 200 and r['user']['passkeys'] == 1, r)
    for why, kw in bad_regs:
        st, r = t.call('passkey_begin', {'password': 'Bearbeiter-Zugang-1'})
        st, r = t.call('passkey_register', SoftKey(-7).register(r['options'], **kw))
        check('registration rejected: ' + why, st == 422, (st, r))
    st, r = t.call('passkey_begin', {'password': 'Bearbeiter-Zugang-1'})
    reg = k1.register(r['options']); reg['attestationObject'] = b64u(b'\xbf\x61\x61\x01\xff')
    st, r = t.call('passkey_register', reg)
    check('broken CBOR → 422, no server error', st == 422, (st, r))
    st, r = t.call('passkey_register', SoftKey(-7).register(o))
    check('register without fresh begin rejected', st == 409, (st, r))
    st, r = t.pk_register(k1, 'Bearbeiter-Zugang-1')
    check('same credential twice rejected', st == 409, r)
    k2 = SoftKey(-257)
    st, r = t.pk_register(k2, 'Bearbeiter-Zugang-1', name='Sicherheitsschlüssel')
    check('register with RS256 key', st == 200 and user('tom')['passkeys'][1]['alg'] == -257 and user('tom')['passkeys'][1]['name'] == 'Sicherheitsschlüssel', r)
    check('transports filtered', user('tom')['passkeys'][0].get('transports') == ['internal'], user('tom')['passkeys'][0].get('transports'))

    d = PkClient('192.0.2.11')
    st, r = d.call('passkey_login_begin', {}); o = r['options']
    check('login options: discoverable, UV, rpId', o['allowCredentials'] == [] and o['userVerification'] == 'required' and o['rpId'] == 'localhost', o)
    good = k1.assertion(o, handle=tom_id)
    st, r = d.call('passkey_login', good)
    check('API login with ES256 passkey', st == 200 and r['user']['username'] == 'tom' and d.call('draft')[0] == 200, r)
    st, r = PkClient('192.0.2.12').call('passkey_login', good)
    check('replay without challenge rejected', st == 401, r)
    st, r = d.call('passkey_login', good)
    check('challenge is single-use', st == 401, r)
    st, r = PkClient('192.0.2.13').pk_login(k2)
    check('API login with RS256 passkey', st == 200 and r['user']['username'] == 'tom', r)
    bad = [('wrong origin', {'origin': 'http://localhost:1'}, 'anderen Seite'), ('wrong challenge', {'challenge': b64u(os.urandom(32))}, 'Anfrage passt nicht'),
           ('wrong type', {'typ': 'webauthn.create'}, 'Ungültige'), ('no user verification', {'flags': 0x01}, 'nicht geprüft'),
           ('no user presence', {'flags': 0x04}, 'Anwesenheit'), ('other rpId', {'rp': 'example.org'}, 'anderen Adresse'),
           ('bad signature', {'bad_sig': True}, 'nicht bestätigt'), ('user handle mismatch', {'handle': 'u000000000000'}, 'nicht bekannt')]
    for i, (why, kw, msg) in enumerate(bad):
        st, r = PkClient(f'192.0.2.{20 + i}').pk_login(k1, **kw)
        check('login rejected: ' + why, st == 401 and msg in r.get('error', ''), (st, r))
    check('bad signature counts as account failure', int(user('tom').get('failCount', 0)) >= 1, user('tom').get('failCount'))
    st, r = PkClient('192.0.2.30').pk_login(SoftKey(-7))
    check('unknown passkey rejected', st == 401 and 'nicht bekannt' in r['error'], r)
    check('audit: unknown passkey', logged('login_fail', 'unbekanntem Passkey'))
    stored = user('tom')['passkeys'][0]['signCount']
    st, r = PkClient('192.0.2.31').pk_login(k1, count=stored)
    check('sign counter not increased → rejected (possible clone)', st == 401 and 'Zähler' in r['error'], (stored, r))
    check('audit: possible clone', logged('login_fail', 'möglicherweise kopiert', 'tom'))
    st, r = PkClient('192.0.2.32').pk_login(k1, count=0)
    check('counter 0 (device without counter) accepted', st == 200, r)
    check('stored counter not reset', user('tom')['passkeys'][0]['signCount'] == stored, user('tom')['passkeys'][0]['signCount'])
    x = PkClient('192.0.2.33')
    st, r = x.call('passkey_login_begin', {})
    session_set(x.cookie(), '$_SESSION["pkAuth"]["t"] = time() - 301;')
    st, r = x.call('passkey_login', k1.assertion(r['options']))
    check('challenge older than 5 minutes rejected', st == 401 and 'abgelaufen' in r['error'], r)
    lim = PkClient('192.0.2.40')
    for i in range(5): lim.pk_login(k1, bad_sig=True)
    st, r = lim.call('passkey_login_begin', {})
    check('passkey failures count towards the IP limit', st == 429 and 'Fehlversuche' in r['error'], (st, r))
    set_user('tom', failCount=0, lockedUntil=0)

    # zweiter Schritt über die Schnittstelle
    s2 = PkClient('192.0.2.41')
    st, r = s2.login('tom', 'Bearbeiter-Zugang-1')
    check('password step for tom', r.get('need2fa') and r.get('methods') == ['passkey'], r)
    st, r = s2.call('passkey_login_begin', {'second': True})
    check('second step lists own credentials', sorted(c['id'] for c in r['options']['allowCredentials']) == sorted([k1.id, k2.id]), r)
    st, r = s2.call('passkey_login', k1.assertion(r['options']))
    check('second step with passkey (API)', st == 200 and r['user']['username'] == 'tom', r)
    s3 = PkClient('192.0.2.42')
    s3.login('admin', PW)
    st, r = s3.pk_login(k1, second=True)
    check("other user's passkey rejected in second step", st == 401 and 'nicht zu diesem Zugang' in r['error'], r)
    check('second step without password step rejected', PkClient('192.0.2.43').call('passkey_login_begin', {'second': True})[0] == 401)

    # Sperren und Zustände
    confirm(a)
    st, r = post(a, 'user_save', {'id': tom_id, 'name': 'Tom Muster', 'role': 'editor', 'active': False})
    st, r = PkClient('192.0.2.50').pk_login(k1)
    check('inactive user rejected', st == 401 and 'deaktiviert' in r['error'], r)
    check('audit: inactive', logged('login_fail', 'Zugang deaktiviert', 'tom'))
    post(a, 'user_save', {'id': tom_id, 'name': 'Tom Muster', 'role': 'editor', 'active': True})
    set_user('tom', lockedUntil=int(time.time()) + 600)
    st, r = PkClient('192.0.2.51').pk_login(k1)
    check('locked user rejected', st == 429 and 'gesperrt' in r['error'], r)
    set_user('tom', lockedUntil=0, mustChange=True)
    st, r = PkClient('192.0.2.52').pk_login(k1)
    check('password change pending → passkey login refused', st == 403 and 'neues Passwort' in r['error'], r)
    set_user('tom', mustChange=False)
    check('user without passkeys field logs in normally', PkClient('192.0.2.53').login('pia', 'Editor-Zugang-77')[1].get('user', {}).get('username') == 'pia')

    # Höchstzahl
    t2 = PkClient('192.0.2.60'); t2.pk_login(k1)
    for i in range(8): t2.pk_register(SoftKey(-7), 'Bearbeiter-Zugang-1')
    check('ten passkeys stored', len(user('tom')['passkeys']) == 10, len(user('tom')['passkeys']))
    st, r = t2.call('passkey_begin', {'password': 'Bearbeiter-Zugang-1'})
    check('no more than 10 passkeys', st == 422 and 'höchstens 10' in r['error'], r)
    raw = json.dumps(get(a, 'users')[1]) + json.dumps(get(a, 'security_status')[1])
    check('no key material in admin APIs', 'BEGIN PUBLIC KEY' not in raw and k1.id not in raw)
    check('no JavaScript errors', not errs, errs[:3])

    # ===== Bildschirmfotos Anmeldung: 390 px, dunkel =====
    v = br.new_context(viewport={'width': 390, 'height': 844}, color_scheme='dark').new_page()
    v.goto(B + '/admin/'); v.wait_for_selector('#screen-auth:not([hidden]) #auth-passkey')
    v.screenshot(path=SHOTS + '/login-390-dark.png')
    check('login screen fits 390 px (dark)', no_overflow(v))
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
