"""Kunden: Stammdaten, Freischaltung von Angeboten, Kunden-Anmeldung auf der Angebotsseite.
Regeln: Kunden sehen nur freigeschaltete Angebote, nie den Eingabebereich; Passwörter nie im Klartext/Hash nach außen."""
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright
from umgebung import SH

B = 'http://127.0.0.1:8790'
API = B + '/api/?action='
PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


class Client:
    """HTTP-Client mit eigener Sitzung; IP über X-Forwarded-For (lokaler Proxy-Fall)."""
    def __init__(self, ip='198.51.100.1'):
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
        self.ip = ip

    def call(self, action, data=None, raw=False):
        headers = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        req = urllib.request.Request(API + action, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            r = self.http.open(req)
        except urllib.error.HTTPError as e:
            r = e
        body = r.read()
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        if isinstance(j, dict) and j.get('csrf'):
            self.csrf = j['csrf']
        return (r.code, j, body.decode('utf-8', 'replace')) if raw else (r.code, j)


def admin():
    c = Client('198.51.100.2')
    assert c.call('login', {'username': 'admin', 'password': PW})[0] == 200
    return c


A = admin()
code, st = A.call('kunden')
check('kunden list (admin) starts empty', code == 200 and st['customers'] == [] and st['rev'] == 0, st)

# ---------- Stammdaten anlegen (API-Validierung) ----------
base = {'id': '', 'rev': 0, 'firma': 'Gasthaus Muster GmbH', 'nr': 'K-1001', 'ansprechpartner': 'Frau Beispiel', 'strasse': 'Musterweg 1',
        'plz': '20095', 'ort': 'Hamburg', 'land': 'Deutschland', 'email': 'einkauf@example.org', 'telefon': '040 000000', 'notiz': 'intern',
        'active': True, 'angebote': ['edeka', 'bela', 'gibts-nicht'],
        'login': {'username': 'gasthaus.muster', 'password': 'Start-Kennwort-42', 'mustChange': True, 'active': True}}
check('invalid email rejected', A.call('kunde_save', {**base, 'email': 'kein-mail'})[0] == 422)
check('missing firma rejected', A.call('kunde_save', {**base, 'firma': ' '})[0] == 422)
check('weak start password rejected', A.call('kunde_save', {**base, 'login': {**base['login'], 'password': 'passwort123'}})[0] == 422)
check('bad username rejected', A.call('kunde_save', {**base, 'login': {**base['login'], 'username': 'A B'}})[0] == 422)
check('login without password rejected', A.call('kunde_save', {**base, 'login': {**base['login'], 'password': ''}})[0] == 422)
check('stale rev rejected (409)', A.call('kunde_save', {**base, 'rev': 5})[0] == 409)
code, r, raw = A.call('kunde_save', base, raw=True)
check('customer created', code == 200 and r['customer']['firma'] == 'Gasthaus Muster GmbH', r)
K1 = r['customer']['id']; rev = r['rev']
check('unknown offer ids dropped', r['customer']['angebote'] == ['edeka', 'bela'], r['customer']['angebote'])
check('no password hash in save response', 'hash' not in raw and 'Start-Kennwort' not in raw and '$2y$' not in raw)
code, r = A.call('kunde_save', {**base, 'rev': rev, 'firma': 'Zweitkunde', 'nr': 'K-1001', 'login': {**base['login'], 'username': 'zweit.kunde'}})
check('duplicate customer number rejected', code == 422 and 'Kundennummer' in r.get('error', ''), r)
code, r = A.call('kunde_save', {**base, 'rev': rev, 'firma': 'Zweitkunde', 'nr': 'K-1002'})
check('duplicate username rejected', code == 422 and 'Benutzername' in r.get('error', ''), r)
code, r = A.call('kunde_save', {**base, 'rev': rev, 'firma': 'Ohne Zugang KG', 'nr': 'K-1002', 'angebote': ['chefs-culinar'], 'login': None})
check('customer without login allowed', code == 200 and r['customer']['login'] is None)
K2 = r['customer']['id']; rev = r['rev']
code, r, raw = A.call('kunden', raw=True)
check('list sorted by firma, no secrets', [c['firma'] for c in r['customers']] == ['Gasthaus Muster GmbH', 'Ohne Zugang KG'] and '$2y$' not in raw and '"hash"' not in raw)
c1 = r['customers'][0]
check('stored master data complete', all(c1[k] == base[k] for k in ['nr', 'ansprechpartner', 'strasse', 'plz', 'ort', 'land', 'email', 'telefon', 'notiz']))
check('login status: mustChange, never logged in', c1['login'] == {'username': 'gasthaus.muster', 'active': True, 'mustChange': True, 'lastLogin': None, 'pwSet': c1['login']['pwSet'], 'lockedUntil': 0})

# ---------- Rechte im Eingabebereich ----------
code, r = A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('editor cannot read customers', E.call('kunden')[0] == 403)
check('editor cannot save customers', E.call('kunde_save', {**base, 'rev': rev, 'nr': 'K-9', 'firma': 'X', 'login': None})[0] == 403)
check('editor cannot delete customers', E.call('kunde_delete', {'id': K2, 'rev': rev})[0] == 403)
check('anonymous cannot read customers', Client('198.51.100.4').call('kunden')[0] == 401)

# ---------- Kunden-Anmeldung (API) ----------
K = Client('198.51.100.10')
check('status before login: no customer', K.call('kunde_status')[1].get('kunde') is None)
check('wrong password rejected', K.call('kunde_login', {'username': 'gasthaus.muster', 'password': 'falsch-falsch'})[0] == 401)
check('unknown user rejected same message', K.call('kunde_login', {'username': 'niemand', 'password': 'falsch-falsch'})[1].get('error') == 'Benutzername oder Passwort ist nicht korrekt.')
K = Client('198.51.100.11')
code, r, raw = K.call('kunde_login', {'username': 'Gasthaus.Muster ', 'password': 'Start-Kennwort-42'}, raw=True)
check('customer login works (case-insensitive name)', code == 200 and r['kunde']['firma'] == 'Gasthaus Muster GmbH' and r['kunde']['mustChange'] is True, r)
check('login payload lists offer names, no secrets', [o['name'] for o in r['kunde']['angebote']] == ['Wochenangebot Edeka', 'Wochenangebot Bela'] and '$2y$' not in raw and 'notiz' not in raw)
check('mustChange blocks customer offers', K.call('offer&angebot=edeka')[0] == 403)
check('public offer still visible', K.call('offer')[0] == 200)
check('password change needs csrf', Client('198.51.100.11').call('kunde_passwort', {'current': 'x', 'password': 'y'})[0] == 401)
tok = K.csrf; K.csrf = 'falsch'
check('password change with wrong csrf rejected', K.call('kunde_passwort', {'current': 'Start-Kennwort-42', 'password': 'Eigenes-Kennwort-55'})[0] == 403)
K.csrf = tok
check('password change needs current password', K.call('kunde_passwort', {'current': 'falsch', 'password': 'Eigenes-Kennwort-55'})[0] == 422)
check('password change rejects username inside', K.call('kunde_passwort', {'current': 'Start-Kennwort-42', 'password': 'x-gasthaus.muster-1'})[0] == 422)
check('password change rejects same password', K.call('kunde_passwort', {'current': 'Start-Kennwort-42', 'password': 'Start-Kennwort-42'})[0] == 422)
code, r = K.call('kunde_passwort', {'current': 'Start-Kennwort-42', 'password': 'Eigenes-Kennwort-55'})
check('own password set', code == 200 and r['kunde']['mustChange'] is False)
code, r = K.call('offer&angebot=edeka')
check('assigned offer visible', code == 200 and r['offer']['meta']['offerName'] == 'Wochenangebot Edeka' and 'variants' not in json.dumps(r))
check('second assigned offer visible', K.call('offer&angebot=bela')[0] == 200)
check('other customer offer forbidden', K.call('offer&angebot=chefs-culinar')[0] == 403)
check('unknown offer: no information leak', K.call('offer&angebot=gibts-nicht')[0] == 403)
check('customer cannot read draft preview', K.call('offer&angebot=edeka&draft=1')[0] == 401)
for act in ['draft', 'status&x=1', 'offers', 'stock', 'versions', 'history_list', 'history_data', 'users', 'kunden', 'log', 'security_status', 'master']:
    c = K.call(act)
    ok = c[0] in (401, 403) or (act.startswith('status') and not c[1].get('user'))
    check(f'customer has no staff access: {act}', ok, c[0])
check('customer cannot write draft', K.call('save_draft', {'offer': {}, 'rev': 0})[0] in (401, 403))
check('customer cannot save customers', K.call('kunde_save', {**base, 'rev': rev})[0] in (401, 403))
code, r = A.call('kunden')
c1 = next(c for c in r['customers'] if c['id'] == K1)
check('admin sees last login + active session', c1['login']['lastLogin'] and c1['sessions'] == 1 and c1['login']['mustChange'] is False)

# ---------- Änderungen wirken sofort ----------
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': r['rev'], 'angebote': ['edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True}})
rev = r['rev']
check('removing an assignment takes effect immediately', code == 200 and K.call('offer&angebot=bela')[0] == 403 and K.call('offer&angebot=edeka')[0] == 200)
check('master-data edit keeps session + password', K.call('kunde_status')[1]['kunde']['angebote'] == [{'id': 'edeka', 'name': 'Wochenangebot Edeka'}])
# Wochenangebot nicht öffentlich
code, offs = A.call('offers')
check('offers report stdPublic (default true)', offs['stdPublic'] is True)
code, r = E.call('offers_save', {'rev': offs['rev'], 'offers': offs['offers'], 'stdPublic': False})
check('editor cannot change stdPublic', code == 403)
code, r = A.call('offers_save', {'rev': offs['rev'], 'offers': offs['offers'], 'stdPublic': False})
check('admin sets Wochenangebot non-public', code == 200 and r['stdPublic'] is False)
check('anonymous: Wochenangebot needs login', Client('198.51.100.20').call('offer')[0] == 401)
check('customer without std assignment: forbidden', K.call('offer')[0] == 403)
check('staff still sees Wochenangebot', E.call('offer')[0] == 200)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True}})
rev = r['rev']
check('customer with std assignment sees it', K.call('offer')[0] == 200)
code, r, raw = A.call('log', raw=True)
ents = r.get('entries', [])
check('audit: customer changes logged', any(e['a'] == 'customers' and 'angelegt' in e['s'] for e in ents) and any(e['a'] == 'customers' and 'bearbeitet' in e['s'] for e in ents))
check('audit: customer logins logged', any(e['a'] == 'kunde_login' for e in ents) and any(e['a'] == 'kunde_login_fail' for e in ents) and any(e['a'] == 'kunde_password' for e in ents))
check('audit: Wochenangebot visibility change logged', any(e['a'] == 'offers' and any(d.get('f') == 'Öffentlich ohne Anmeldung' for d in e.get('d', [])) for e in ents))
check('audit never contains passwords', 'Start-Kennwort-42' not in raw and 'Eigenes-Kennwort-55' not in raw and '$2y$' not in raw)

# Deaktivieren, Passwort zurücksetzen, Sperre
K2c = Client('198.51.100.12'); K2c.call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})
check('second device logged in', K2c.call('offer&angebot=edeka')[0] == 200)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': False}})
rev = r['rev']
check('deactivating access ends all sessions', K.call('offer&angebot=edeka')[0] == 401 and K2c.call('offer&angebot=edeka')[0] == 401)
check('deactivated access cannot log in', Client('198.51.100.13').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})[0] == 401)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True}})
rev = r['rev']
K = Client('198.51.100.14')
check('reactivated access works with own password', K.call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})[0] == 200 and K.call('offer&angebot=edeka')[0] == 200)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'active': False, 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True}})
rev = r['rev']
check('inactive customer: session ended', K.call('offer&angebot=edeka')[0] == 401)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': 'Neu-Gesetzt-Kennwort-9', 'mustChange': True, 'active': True}})
rev = r['rev']
check('admin password reset requires change again', r['customer']['login']['mustChange'] is True and Client('198.51.100.15').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})[0] == 401)
A.call('security_save', {'lockAfter': 3})
for i in range(3):
    c = Client('198.51.100.' + str(30 + i)).call('kunde_login', {'username': 'gasthaus.muster', 'password': 'falsch-' + str(i)})
check('account locked after failed attempts (across IPs)', c[0] == 429, c)
check('locked account rejects correct password', Client('198.51.100.40').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Neu-Gesetzt-Kennwort-9'})[0] == 429)
code, r = A.call('kunden')
c1 = next(c for c in r['customers'] if c['id'] == K1)
check('admin sees lock', c1['login']['lockedUntil'] > 0)
code, r = A.call('kunde_save', {**base, 'id': K1, 'rev': r['rev'], 'angebote': ['std', 'edeka'], 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True, 'unlock': True}})
rev = r['rev']
check('admin can unlock', r['customer']['login']['lockedUntil'] == 0 and Client('198.51.100.41').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Neu-Gesetzt-Kennwort-9'})[0] == 200)
A.call('security_save', {'lockAfter': 10})
# Wochenangebot wieder öffentlich
code, offs = A.call('offers')
A.call('offers_save', {'rev': offs['rev'], 'offers': offs['offers'], 'stdPublic': True})
check('Wochenangebot public again', Client('198.51.100.21').call('offer')[0] == 200)

# ---------- Oberfläche ----------
with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('nav: Kunden visible for admin', a.is_visible('#vt-kunden'))
    a.click('#vt-kunden'); a.wait_for_selector('#view-kunden tr[data-kid]')
    rows = a.locator('#view-kunden tr[data-kid]')
    check('list shows customers', rows.count() == 2 and 'Gasthaus Muster GmbH' in rows.first.inner_text(), rows.count())
    check('list shows offer chips', 'Edeka' in rows.first.inner_text() and 'Wochenangebot' in rows.first.inner_text())
    a.fill('#k-q', 'ohne'); a.wait_for_timeout(100)
    check('search filters list', a.locator('#view-kunden tr[data-kid]').count() == 1)
    a.fill('#k-q', '')
    a.click('#k-add'); a.wait_for_selector('#dlg-kunde[open]')
    a.fill('#kunde-body [name=firma]', 'Hotel Seeblick & Co. KG')
    check('username suggested from firma', a.input_value('#kunde-body [name=username]') == 'hotel.seeblick', a.input_value('#kunde-body [name=username]'))
    a.fill('#kunde-body [name=ansprechpartner]', 'Herr Test'); a.fill('#kunde-body [name=email]', 'kueche@example.org')
    a.fill('#kunde-body [name=plz]', '22111'); a.fill('#kunde-body [name=ort]', 'Hamburg')
    a.check('#kunde-body [name=angebot][value=bela]'); a.check('#kunde-body [name=angebot][value=handelshof-efs]')
    a.click('#kunde-body [data-kact=gen]')
    start_pw = a.input_value('#kunde-body [name=password]')
    check('password suggestion generated', len(start_pw) >= 12)
    a.screenshot(path=SH + '/kunden-dialog.png')
    a.click('#kunde-body [type=submit]'); a.wait_for_function("!document.querySelector('#dlg-kunde').open", timeout=8000)
    a.wait_for_selector('#view-kunden tr[data-kid]:has-text("Hotel Seeblick")')
    check('toast reminds to pass on credentials', 'weitergeben' in a.inner_text('#toast'))
    hrow = a.locator('#view-kunden tr[data-kid]:has-text("Hotel Seeblick")')
    check('new row: offers + must change', 'Bela' in hrow.inner_text() and 'Handelshof' in hrow.inner_text() and 'Startpasswort' in hrow.inner_text(), hrow.inner_text())
    a.screenshot(path=SH + '/kunden-liste.png')
    # Bearbeiten: Pflichtfeld + Zugang entfernen bestätigen
    a.locator('#view-kunden tr[data-kid]:has-text("Ohne Zugang")').click(); a.wait_for_selector('#dlg-kunde[open]')
    check('existing customer w/o login: login section collapsed', a.locator('#kunde-body .k-login').is_hidden())
    a.click('#kunde-body [data-close]'); a.wait_for_timeout(200)

    # Kunde im Browser
    cctx = br.new_context(viewport={'width': 1280, 'height': 900}); c = cctx.new_page(); cerr = []
    c.on('pageerror', lambda e: cerr.append(str(e)))
    c.goto(B + '/'); c.wait_for_selector('tr.row')
    check('public page: Kunden-Login button', c.is_visible('#btn-kunde-login'))
    c.click('#btn-kunde-login'); c.wait_for_selector('#dlg-kunde-login[open]')
    c.fill('#kl-form [name=username]', 'hotel.seeblick'); c.fill('#kl-form [name=password]', 'ganz-falsch-1'); c.click('#kl-form [type=submit]')
    c.wait_for_function("document.querySelector('#kl-err').textContent.length > 0")
    check('wrong password: message in dialog', 'nicht korrekt' in c.inner_text('#kl-err'))
    c.fill('#kl-form [name=password]', start_pw); c.click('#kl-form [type=submit]')
    c.wait_for_selector('#dlg-kunde-pw[open]')
    check('first login forces own password', c.inner_text('#kp-title') == 'Eigenes Passwort festlegen' and c.locator('#kp-close').is_hidden())
    c.keyboard.press('Escape'); c.wait_for_timeout(200)
    check('forced dialog cannot be dismissed', c.locator('#dlg-kunde-pw[open]').count() == 1)
    c.fill('#kp-form [name=current]', start_pw); c.fill('#kp-form [name=password]', 'Seeblick-Eigen-2026'); c.fill('#kp-form [name=password2]', 'Seeblick-Eigen-2027')
    c.click('#kp-form [type=submit]'); c.wait_for_timeout(200)
    check('mismatch detected', 'stimmen nicht' in c.inner_text('#kp-err'))
    c.fill('#kp-form [name=password2]', 'Seeblick-Eigen-2026'); c.click('#kp-form [type=submit]')
    c.wait_for_url(re.compile(r'angebot=handelshof-efs'), timeout=8000); c.wait_for_selector('tr.row')
    check('after password change: first assigned offer opens', 'angebot=handelshof-efs' in c.url, c.url)
    check('banner shows customer + switcher', 'Hotel Seeblick' in c.inner_text('#preview-banner') and c.locator('#preview-banner [data-kswitch]').count() == 2)
    check('title names the offer', 'Handelshof' in c.inner_text('#topbar h1'), c.inner_text('#topbar h1'))
    c.screenshot(path=SH + '/kunden-angebot.png')
    c.click('#preview-banner [data-kswitch=bela]'); c.wait_for_url(re.compile(r'angebot=bela')); c.wait_for_selector('tr.row')
    check('switch to second offer', 'Bela' in c.inner_text('#topbar h1'))
    c.goto(B + '/?angebot=edeka'); c.wait_for_selector('tr.row')
    check('not-assigned offer redirects to own offer', 'angebot=handelshof-efs' in c.url, c.url)
    c.goto(B + '/'); c.wait_for_selector('tr.row')
    check('public start page redirects logged-in customer to own offer', 'angebot=handelshof-efs' in c.url, c.url)
    c.click('#btn-kunde'); c.wait_for_selector('#menu-kunde:not([hidden])')
    check('customer menu: offers, password, logout', c.locator('#menu-kunde [data-kswitch]').count() == 2 and c.is_visible('#menu-kunde [data-kact=logout]'))
    c.click('#menu-kunde [data-kact=pw]'); c.wait_for_selector('#dlg-kunde-pw[open]')
    check('voluntary password dialog closable', c.inner_text('#kp-title') == 'Passwort ändern' and c.is_visible('#kp-close'))
    c.click('#kp-cancel'); c.wait_for_timeout(200)
    check('cancel closes', c.locator('#dlg-kunde-pw[open]').count() == 0)
    c.click('#btn-kunde'); c.click('#menu-kunde [data-kact=logout]')
    c.wait_for_selector('#btn-kunde-login'); c.wait_for_selector('tr.row')
    check('logout returns to public Wochenangebot', 'angebot=' not in c.url and c.is_visible('#btn-kunde-login'), c.url)
    r = c.evaluate("async () => (await fetch('/api/?action=offer&angebot=bela')).status")
    check('after logout customer offer locked', r == 401)
    # Ohne Anmeldung: Kundenangebot zeigt Login
    c.goto(B + '/?angebot=bela'); c.wait_for_selector('#dlg-kunde-login[open]')
    check('locked page offers login, no rows', 'nur nach Anmeldung' in c.inner_text('#list') and c.locator('tr.row').count() == 0)
    c.fill('#kl-form [name=username]', 'hotel.seeblick'); c.fill('#kl-form [name=password]', 'Seeblick-Eigen-2026'); c.click('#kl-form [type=submit]')
    c.wait_for_selector('tr.row')
    check('login from locked page opens requested assigned offer', 'angebot=bela' in c.url and 'Bela' in c.inner_text('#topbar h1'), c.url)
    # Mobil
    m = cctx.new_page(); m.set_viewport_size({'width': 390, 'height': 800}); m.goto(B + '/?angebot=bela'); m.wait_for_selector('tr.row, .card')
    check('mobile: no horizontal scroll', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    m.screenshot(path=SH + '/kunden-mobil.png')
    check('no JS errors (admin)', not errs, errs[:3])
    check('no JS errors (customer)', not cerr, cerr[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
