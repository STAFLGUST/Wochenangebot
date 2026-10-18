import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import base64, hmac, hashlib, struct, time, json, os, re, subprocess
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
DATA = os.environ['UDATA']
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def totp(secret, step=None):
    key = base64.b32decode(secret.replace(' ', '') + '=' * (-len(secret.replace(' ', '')) % 8))
    step = int(time.time() // 30) if step is None else step
    h = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    o = h[19] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)
def next_step():
    s = int(time.time() // 30)
    while int(time.time() // 30) == s: time.sleep(0.5)

def login(pg, user, pw, wait=True):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
    if wait: pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body, headers=None):
    return pg.evaluate("""async ([a, b, h]) => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=' + a, {method:'POST', headers:Object.assign({'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, h || {}), body: JSON.stringify(b)}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, body, headers or {}])

CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
def add_csp(route):
    r = route.fetch()
    h = dict(r.headers); h['content-security-policy'] = CSP
    route.fulfill(response=r, headers=h)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    ctx.route(re.compile(r'.*/(admin/)?(\?.*)?$'), add_csp)
    a = ctx.new_page(); errs = []; csp = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.on('console', lambda m: csp.append(m.text) if 'Content Security Policy' in m.text else None)
    a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    check('security tab visible for admin', a.locator('#vt-sec').is_visible())
    a.click('#vt-sec'); a.wait_for_selector('.sec-grid')
    check('status cards', a.locator('.sec-card').count() == 15, a.locator('.sec-card').count())
    check('own session listed', 'diese Sitzung' in a.inner_text('#view-sec'))
    a.screenshot(path=SH + '/security.png', full_page=True)
    # --- 2FA einrichten
    a.click('#btn-more'); a.click('[data-act="twofa"]'); a.wait_for_selector('#dlg-twofa .tf-qr svg')
    check('QR code rendered', a.locator('#dlg-twofa .tf-qr svg').count() == 1)
    secret = a.text_content('#dlg-twofa .tf-secret').replace(' ', '')
    a.fill('#dlg-twofa [data-tf=code]', '000000'); a.click('#dlg-twofa [data-tf=enable]'); a.wait_for_timeout(300)
    check('wrong setup code rejected', 'stimmt nicht' in a.inner_text('#dlg-twofa [data-tf=err]'))
    a.fill('#dlg-twofa [data-tf=code]', totp(secret)); a.click('#dlg-twofa [data-tf=enable]'); a.wait_for_selector('#dlg-twofa .tf-codes')
    codes = a.locator('#dlg-twofa .tf-codes code').all_inner_texts()
    check('10 recovery codes', len(codes) == 10, codes[:2])
    a.screenshot(path=SH + '/twofa-codes.png')
    a.check('#dlg-twofa [data-tf=ack]'); a.click('#dlg-twofa [data-tf=done]'); a.wait_for_timeout(300)
    # --- Anmeldung mit Code (zweites Fenster)
    b = br.new_context(viewport={'width': 1440, 'height': 950}).new_page()
    login(b, 'admin', 'Sicheres-Passwort-1', wait=False); b.wait_for_selector('#au-code-wrap:not([hidden])')
    check('login asks for code', 'Authenticator' in b.inner_text('#auth-intro'))
    b.fill('#au-code', '123456'); b.click('#auth-submit'); b.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('wrong code rejected', 'nicht korrekt' in b.inner_text('#auth-err'))
    next_step()
    b.fill('#au-code', totp(secret)); b.click('#auth-submit'); b.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('login with TOTP works', True)
    c = br.new_context(viewport={'width': 1440, 'height': 950}).new_page()
    login(c, 'admin', 'Sicheres-Passwort-1', wait=False); c.wait_for_selector('#au-code-wrap:not([hidden])')
    c.fill('#au-code', codes[0]); c.click('#auth-submit'); c.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('login with recovery code', 'Wiederherstellungscode' in c.inner_text('#toast'))
    c2 = br.new_context().new_page()
    login(c2, 'admin', 'Sicheres-Passwort-1', wait=False); c2.wait_for_selector('#au-code-wrap:not([hidden])')
    c2.fill('#au-code', codes[0]); c2.click('#auth-submit'); c2.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('recovery code works only once', 'nicht korrekt' in c2.inner_text('#auth-err'))
    c2.context.close()
    # --- Sitzungen
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_selector('.sec-grid')
    try: a.wait_for_function("document.querySelectorAll('[data-sec=end]').length === 2", timeout=10000)
    except Exception: pass
    n = a.locator('[data-sec=end]').count(); check('other sessions listed', n == 2, n)
    a.locator('[data-sec=end]').first.click(); a.wait_for_timeout(600)
    a.locator('[data-sec=end]').first.click(); a.wait_for_timeout(600)
    st_b = b.evaluate("fetch('../api/?action=draft').then(r => r.status)"); st_c = c.evaluate("fetch('../api/?action=draft').then(r => r.status)")
    check('ended sessions are logged out (401)', st_b == 401 and st_c == 401, (st_b, st_c))
    # --- Passwortregeln + Pflicht
    a.select_option('#sec-form [name=twofa]', 'all'); a.fill('#sec-form [name=pwMin]', '12'); a.check('#sec-form [name=pwComplex]')
    a.select_option('#sec-form [name=idleMinutes]', '30'); a.fill('#sec-form [name=lockAfter]', '3')
    a.click('#sec-form [type=submit]'); a.wait_for_timeout(600)
    check('settings saved', 'gespeichert' in a.inner_text('#toast'), a.inner_text('#toast'))
    for pw, why in [('Standard-Fleisch', 'leicht'), ('vicvicvicvic1A', 'Benutzernamen'), ('nurkleinbuchstaben', 'Zeichenarten'), ('Kurz1!', 'mindestens 12')]:
        r = post(a, 'user_save', {'name': 'Vic', 'username': 'vic', 'role': 'viewer', 'active': True, 'password': pw})
        check(f'weak password rejected ({why})', r[0] == 422 and why in r[1]['error'], r[1]['error'] if r[1] else r)
    r = post(a, 'user_save', {'name': 'Vic', 'username': 'vic', 'role': 'viewer', 'active': True, 'password': 'Gut-Passwort-2026', 'mustChange': False})
    check('strong password accepted', r[0] == 200, r)
    v = br.new_context(viewport={'width': 1440, 'height': 950}).new_page()
    login(v, 'vic', 'Gut-Passwort-2026', wait=False); v.wait_for_selector('#auth-twofa .tf-qr svg')
    check('2FA required → setup on login', 'vorgeschrieben' in v.inner_text('#auth-intro'))
    rs = v.evaluate("fetch('../api/?action=draft').then(r => r.status)"); check('API blocked until 2FA set up (403)', rs == 403, rs)
    vsec = v.text_content('#auth-twofa .tf-secret').replace(' ', '')
    v.fill('#auth-twofa [data-tf=code]', totp(vsec)); v.click('#auth-twofa [data-tf=enable]'); v.wait_for_selector('#auth-twofa .tf-codes')
    v.check('#auth-twofa [data-tf=ack]'); v.click('#auth-twofa [data-tf=done]'); v.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('after setup editor opens', True)
    v.context.close()
    # --- Kontosperre
    for k in range(3):
        x = br.new_context().new_page(); login(x, 'vic', 'Falsch-Passwort-1', wait=False); x.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
        msg = x.inner_text('#auth-err'); x.context.close()
    check('account locked after 3 failures', 'gesperrt' in msg, msg)
    x = br.new_context().new_page(); login(x, 'vic', 'Gut-Passwort-2026', wait=False); x.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('locked account rejects correct password', 'gesperrt' in x.inner_text('#auth-err')); x.context.close()
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_selector('.sec-grid')
    check('locked user shown', a.locator('[data-sec=unlock]').count() == 1)
    a.click('[data-sec=unlock]'); a.wait_for_timeout(600)
    x = br.new_context().new_page(); login(x, 'vic', 'Gut-Passwort-2026', wait=False); x.wait_for_selector('#au-code-wrap:not([hidden])')
    check('unlocked user can log in again (code step)', True); x.context.close()
    # --- IP-Freigabe
    a.check('#sec-form [name=ipEnabled]'); a.fill('#sec-form [name=adminIps]', '10.9.9.9')
    a.click('#sec-form [type=submit]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(600)
    check('self-lockout prevented', 'aussperren' in a.inner_text('#sec-err'), a.inner_text('#sec-err'))
    a.click('[data-sec=addip]'); a.click('#sec-form [type=submit]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(800)
    check('IP allowlist saved', 'gespeichert' in a.inner_text('#toast'))
    other = br.new_context(extra_http_headers={'X-Forwarded-For': '203.0.113.7'}); op = other.new_page()
    r1 = op.request.get(B + '/api/?action=status'); r2 = op.request.get(B + '/api/?action=offer')
    check('foreign IP blocked from admin API', r1.status == 403 and '203.0.113.7' in r1.text(), r1.status)
    check('public offer still reachable', r2.status == 200)
    op.goto(B + '/admin/'); op.wait_for_selector('main.auth')
    check('admin page shows block message', 'nicht freigegeben' in op.inner_text('body'))
    other.close()
    subprocess.run(['php', REPO + '/deploy/ip-freigabe-aus.php'], env={**os.environ, 'DATA_DIR': DATA}, check=True, capture_output=True)
    other = br.new_context(extra_http_headers={'X-Forwarded-For': '203.0.113.7'})
    check('emergency script disables allowlist', other.request.get(B + '/api/?action=status').status == 200); other.close()
    # --- Nutzer: 2FA-Reset
    a.click('#vt-users'); a.wait_for_selector('.utab')
    check('2FA badge in user list', a.locator('.utab .tf-badge').count() == 2)
    a.locator('.utab tbody tr:has-text("Vic")').click(); a.wait_for_selector('#dlg-user[open]')
    a.check('#user-body [name=reset2fa]'); a.click('#user-body [type=submit]'); a.wait_for_timeout(600)
    check('2FA reset by admin', a.locator('.utab .tf-badge').count() == 1)
    # --- Protokoll
    a.click('#vt-log'); a.wait_for_selector('.ltab'); t = a.inner_text('#log-list')
    check('log: 2FA + security entries', 'Zwei-Faktor-Anmeldung eingerichtet' in t and 'Sicherheitseinstellungen geändert' in t and 'Sitzung' in t and 'entsperrt' in t)
    # --- CSP: Druckfenster + öffentliche Seite
    a.click('#vt-stock'); a.wait_for_timeout(500)
    pub = ctx.new_page(); pub.on('console', lambda m: csp.append('pub: ' + m.text) if 'Content Security Policy' in m.text else None)
    pub.goto(B + '/#suche=Entrecote'); pub.wait_for_selector('tr.row'); pub.locator('tr.row .name-btn').first.click(); pub.wait_for_timeout(300)
    check('no CSP violations (admin + public)', not csp, csp[:3])
    # --- Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1', wait=False); m.wait_for_selector('#au-code-wrap:not([hidden])')
    next_step(); m.fill('#au-code', totp(secret)); m.click('#auth-submit'); m.wait_for_selector('tr[data-id]')
    m.click('#vt-sec'); m.wait_for_selector('.sec-grid'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/security-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth')
    over = m.evaluate("""() => { const out=[]; for (const el of document.querySelectorAll('body *')) { const r=el.getBoundingClientRect(); if (r.right>392 && r.width>0 && !el.closest('.view-tabs')) out.push(el.tagName+'#'+el.id+'.'+String(el.className).slice(0,30)+' '+Math.round(r.right)); } return out.slice(0,8); }""")
    check('mobile no h-scroll', sw <= 390, (sw, over))
    check('no JS errors', not errs, errs)
    # Faktorwechsel auch über die echte Oberfläche testen (Pflicht bleibt aktiv).
    a.click('#btn-more'); a.click('[data-act="twofa"]'); a.wait_for_selector('[data-tfd="renew"]')
    a.click('[data-tfd="renew"]')
    check('renewal asks for password', a.locator('#tf-pw').is_visible())
    a.fill('#tf-pw', 'Sicheres-Passwort-1'); a.click('[data-tfd="renew-go"]')
    a.wait_for_selector('#dlg-twofa .tf-qr svg')
    renewed_secret = a.text_content('#dlg-twofa .tf-secret').replace(' ', '')
    a.fill('#dlg-twofa [data-tf=code]', totp(renewed_secret)); a.click('#dlg-twofa [data-tf=enable]')
    a.wait_for_selector('#dlg-twofa .tf-codes')
    check('UI renewal produces new recovery codes', a.locator('#dlg-twofa .tf-codes code').count() == 10)
    check('UI renewal revokes mobile session', m.evaluate("fetch('../api/?action=draft').then(r => r.status)") == 401)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
