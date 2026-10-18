import sys
from umgebung import shot
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, os, re, subprocess, time
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
DATA = os.environ['UDATA']
CN, AU, DE, RU = '1.0.1.1', '1.0.0.1', '46.114.0.1', '77.88.8.8'
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body, headers=None):
    return pg.evaluate("""async ([a, b, h]) => { const s = await (await fetch('/api/?action=status', {headers: h || {}})).json();
      const r = await fetch('/api/?action=' + a, {method:'POST', headers:Object.assign({'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, h || {}), body: JSON.stringify(b)}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, body, headers or {}])
def get(pg, action, headers=None):
    return pg.evaluate("""async ([a, h]) => { const r = await fetch('/api/?action=' + a, {headers: h || {}}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, headers or {}])
def settings(pg):
    return get(pg, 'security_status')[1]['settings']
BASE = {'twofa': 'off', 'idleMinutes': 480, 'pwMin': 10, 'pwComplex': False, 'lockAfter': 10, 'lockMinutes': 15, 'ipEnabled': False, 'adminIps': []}

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.click('#vt-sec'); a.wait_for_selector('#geo-box')
    check('15 status cards incl. Ländersperre', a.locator('.sec-card').count() == 15 and 'Ländersperre' in a.inner_text('.sec-grid'))
    check('db info shown', 'Stand 17.06.2026' in a.inner_text('#geo-box'), a.inner_text('.geo-db'))
    check('unknown own country hint', 'nicht bekannt' in a.inner_text('#geo-me'))
    check('country list German names', a.locator('.geo-opt').count() > 240 and 'Deutschland' in a.inner_text('#geo-list'), a.locator('.geo-opt').count())
    a.fill('#geo-q', 'china'); a.wait_for_timeout(150)
    check('search filters', a.locator('.geo-opt').count() == 1 and 'China' in a.inner_text('#geo-list'), a.inner_text('#geo-list'))
    a.check('#geo-list [data-geo-cc=CN]')
    a.fill('#geo-q', 'RU'); a.wait_for_timeout(150); a.check('#geo-list [data-geo-cc=RU]')
    check('chips show selection', 'China' in a.inner_text('#geo-chips') and 'Russland' in a.inner_text('#geo-chips') and '2 ausgewählt' in a.inner_text('#geo-count'))
    a.click('[data-geo-del=RU]'); a.wait_for_timeout(100)
    check('chip remove', 'Russland' not in a.inner_text('#geo-chips') and not a.locator('#geo-list [data-geo-cc=RU]').is_checked())
    # leere Auswahl → Fehler
    a.click('[data-sec=geo-none]'); a.check('#sec-form [name=geoEnabled]'); a.click('#sec-form [type=submit]'); a.wait_for_timeout(200)
    check('empty selection rejected', 'mindestens ein Land' in a.inner_text('#sec-err'))
    a.fill('#geo-q', 'china'); a.check('#geo-list [data-geo-cc=CN]')
    a.screenshot(path=SH + '/geo.png', full_page=True)
    a.click('#sec-form [type=submit]'); a.wait_for_selector('#dlg-confirm[open]')
    check('confirm explains', 'China' in a.inner_text('#dlg-confirm') and 'nur für den Eingabebereich' in a.inner_text('#dlg-confirm'))
    a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(800)
    S = settings(a)
    check('saved: block CN, admin scope', S['geoEnabled'] and S['geoMode'] == 'block' and S['geoCountries'] == ['CN'] and S['geoScope'] == 'admin', S)
    check('card shows 1 Land gesperrt', '1 Land gesperrt' in a.inner_text('.sec-grid'))
    # Zugriff aus China
    cn = br.new_context(extra_http_headers={'X-Forwarded-For': CN}).new_page()
    cn.goto(B + '/admin/'); cn.wait_for_selector('h1'); t = cn.inner_text('body')
    check('CN: admin blocked with message', 'Eingabebereich nicht erreichbar' in t and 'Land' in t and 'PHP' not in t, t[:200])
    r = get(cn, 'offer'); check('CN: public offer still open (scope admin)', r[0] == 200 and r[1]['ok'])
    r = post(cn, 'login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'}); check('CN: login blocked', r[0] == 403, r)
    au = br.new_context(extra_http_headers={'X-Forwarded-For': AU}).new_page(); au.goto(B + '/admin/'); au.wait_for_selector('#screen-auth:not([hidden])')
    check('AU: admin reachable', True)
    # ganze Seite
    body = dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['CN', 'RU'], geoScope='all')
    r = post(a, 'security_save', body); check('save scope all', r[0] == 200, r)
    r = get(cn, 'offer'); check('CN: public offer blocked (scope all)', r[0] == 403 and 'Land' in r[1]['error'], r)
    cn.goto(B + '/'); cn.wait_for_timeout(1200); t = cn.inner_text('body')
    check('CN: frontend shows message', 'Land' in t and 'nicht möglich' in t, t[:120])
    ru = br.new_context(extra_http_headers={'X-Forwarded-For': RU}).new_page(); ru.goto(B + '/')
    r = get(ru, 'offer'); check('RU blocked too', r[0] == 403)
    r = get(au, 'offer'); check('AU public allowed', r[0] == 200)
    r = get(a, 'offer'); check('local (unknown) allowed', r[0] == 200)
    # IPv6 / IPv4-in-IPv6
    r = get(au, 'offer', {})
    v6 = br.new_context(extra_http_headers={'X-Forwarded-For': '::ffff:' + CN}).new_page(); v6.goto(B + '/')
    check('IPv4-mapped IPv6 blocked', get(v6, 'offer')[0] == 403)
    # Freigabeliste hat Vorrang
    r = post(a, 'security_save', dict(body, adminIps=[CN + '/32'])); check('save with allowlisted CN ip', r[0] == 200, r)
    check('allowlisted CN ip passes', get(cn, 'offer')[0] == 200 and get(cn, 'status')[0] == 200)
    # Nur erlauben
    r = post(a, 'security_save', dict(BASE, geoEnabled=True, geoMode='allow', geoCountries=['DE', 'AT', 'CH'], geoScope='admin'))
    check('save allow-mode', r[0] == 200, r)
    dep = br.new_context(extra_http_headers={'X-Forwarded-For': DE}).new_page(); dep.goto(B + '/')
    check('allow: AU blocked, DE ok, CN blocked', get(au, 'status')[0] == 403 and get(cn, 'status')[0] == 403 and get(dep, 'status')[0] == 200)
    check('allow: AU public offer open (scope admin)', get(au, 'offer')[0] == 200)
    # Selbstaussperrung (Admin aus Deutschland)
    de = br.new_context(viewport={'width': 1440, 'height': 950}, extra_http_headers={'X-Forwarded-For': DE}).new_page(); de.on('pageerror', lambda e: errs.append('de: ' + str(e)))
    login(de, 'admin', 'Sicheres-Passwort-1'); de.click('#vt-sec'); de.wait_for_selector('#geo-box')
    check('own country shown', 'Deutschland' in de.inner_text('#geo-me'))
    de.click('[data-sec=geo-none]'); de.fill('#geo-q', 'AT'); de.check('#geo-list [data-geo-cc=AT]'); de.wait_for_timeout(100)
    check('live self-lockout warning', 'aussperren' in de.inner_text('#geo-me') and 'bad' in de.get_attribute('#geo-me', 'class'))
    de.click('#sec-form [type=submit]'); de.wait_for_selector('#dlg-confirm[open]'); de.click('#dlg-confirm [data-v="1"]'); de.wait_for_timeout(500)
    check('server rejects self-lockout (allow)', 'aussperren' in de.inner_text('#sec-err'), de.inner_text('#sec-err'))
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['DE'], geoScope='admin'), {'X-Forwarded-For': DE})
    check('server rejects self-lockout (block)', r[0] == 422 and 'aussperren' in r[1]['error'], r)
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['DE'], geoScope='admin', adminIps=[DE]), {'X-Forwarded-For': DE})
    check('allowed when own ip is allowlisted', r[0] == 200, r)
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['XX', 'cn', 'CN'], geoScope='weird'), {'X-Forwarded-For': DE})
    S = settings(a); check('input sanitized', r[0] == 200 and S['geoCountries'] == ['CN'] and S['geoScope'] == 'admin', S)
    # Statistik
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-sec'); a.wait_for_selector('#geo-box')
    st = get(a, 'security_status')[1]
    ccs = {x['cc']: x['n'] for x in st['geoStats']}
    check('stats counted per country', ccs.get('CN', 0) >= 3 and ccs.get('AU', 0) >= 1 and st['geoBlocked7'] >= 5, (ccs, st['geoBlocked7']))
    check('stats table shown', 'Abgewiesene Zugriffe nach Land' in a.inner_text('#view-sec') and 'China' in a.inner_text('#view-sec'))
    a.click('[data-sec=geo-clear]'); a.wait_for_timeout(600)
    check('stats cleared', not get(a, 'security_status')[1]['geoStats'])
    # Protokoll
    log = get(a, 'log')[1]
    txt = json.dumps(log, ensure_ascii=False)
    check('audit: Ländersperre changes', 'Ländersperre – Länder' in txt and 'nur ausgewählte Länder erlauben' in txt)
    # Rechte
    post(a, 'user_save', {'name': 'Eddi', 'username': 'eddi', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    e = br.new_context().new_page(); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    check('editor cannot geo_update / clear', post(e, 'geo_update', {})[0] == 403 and post(e, 'geo_clear_stats', {})[0] == 403)
    check('db file not downloadable', a.request.get(B + '/api/geo/laender.dat.php').status == 404 and len(a.request.get(B + '/api/geo/laender.dat.php').body()) == 0)
    # Notfall-Skript
    r = post(a, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['CN'], geoScope='all'))
    out = subprocess.run(['php', REPO + '/deploy/ip-freigabe-aus.php'], env={**os.environ, 'DATA_DIR': DATA}, capture_output=True, text=True).stdout
    check('emergency script disables geo', 'Ländersperre' in out and not settings(a)['geoEnabled'] and get(cn, 'offer')[0] == 200, out)
    # Datenbank aktualisieren (echter Download)
    if os.environ.get('GEO_DL'):
        a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-sec'); a.wait_for_selector('#geo-box')
        a.click('[data-sec=geo-update]')
        a.wait_for_function("document.querySelector('#toast').textContent.includes('Länderdaten')", timeout=120000)
        check('geo_update ok', 'aktualisiert' in a.inner_text('#toast'), a.inner_text('#toast'))
        check('updated db in data dir', os.path.isfile(DATA + '/geo/laender.dat.php'))
        check('lookup after update', get(cn, 'status')[0] == 200)
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page(); m.on('pageerror', lambda e: errs.append('m: ' + str(e)))
    login(m, 'admin', 'Sicheres-Passwort-1'); m.click('#vt-sec'); m.wait_for_selector('#geo-box'); m.wait_for_timeout(200)
    shot(m.locator('#geo-box'), SH + '/geo-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
