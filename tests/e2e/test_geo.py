"""Testgruppe geo: Ländersperre im Modul Sicherheit (Einstellungen → Ländersperre, Dialog) – Länderliste nach Kontinenten,
Schnellauswahl (Kontinente, EU, EWR, DACH, Nachbarn, NATO, G7, BRICS), Suche, Selbstaussperr-Schutz, Zusammenfassung,
Statistik (Firewall & Sperren). Dazu die Daten der Schnellauswahl (app/module/sicherheit/laendergruppen.json)."""
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
def geo_dialog(pg):
    pg.goto(B + '/module/sicherheit/#einstellungen'); pg.wait_for_selector('[data-e="e-geo"]')
    pg.click('[data-e="e-geo"]'); pg.wait_for_selector('#sic-dlg[open] #geo-box')
def ja(pg):
    pg.click('#sic-dlg .sic-dfuss [type=submit]')
# ---------- Daten der Schnellauswahl: jedes Land der Länderliste genau einem Kontinent, Gruppen nur aus bekannten Ländern ----------
GRUPPEN = json.load(open(os.path.join(REPO, 'app', 'module', 'sicherheit', 'laendergruppen.json'), encoding='utf-8'))
LAENDER = re.findall(r"'([A-Z]{2})'", re.search(r"const GEO_COUNTRIES = \[(.*?)\];", open(os.path.join(REPO, 'app', 'api', 'geo.php'), encoding='utf-8').read(), re.S).group(1))
_kont = [c for k in GRUPPEN['kontinente'] for c in k['laender']]
check('Ländergruppen: jedes Land genau einem Kontinent', sorted(_kont) == sorted(LAENDER) and len(_kont) == len(set(_kont)), sorted(set(LAENDER) ^ set(_kont)))
_g = {x['id']: set(x['laender']) for x in GRUPPEN['gruppen']}
check('Ländergruppen: nur bekannte Länder, Größen stimmen (EU 27, EWR 30, NATO 32, G7 7, BRICS 10, DACH 3, Nachbarn 10)',
      all(v <= set(LAENDER) for v in _g.values()) and [len(_g[k]) for k in ('eu', 'ewr', 'nato', 'g7', 'brics', 'dach', 'nachbarn')] == [27, 30, 32, 7, 10, 3, 10]
      and _g['ewr'] == _g['eu'] | {'IS', 'LI', 'NO'} and _g['dach'] == {'DE', 'AT', 'CH'} and 'DE' in _g['nachbarn'] and 'SA' not in _g['brics'], {k: len(v) for k, v in _g.items()})
check('Ländergruppen: EU-Länder liegen in Europa', _g['eu'] <= set(next(k['laender'] for k in GRUPPEN['kontinente'] if k['id'] == 'europa')))
BASE = {'twofa': 'off', 'idleMinutes': 480, 'pwMin': 10, 'pwComplex': False, 'lockAfter': 10, 'lockMinutes': 15, 'ipEnabled': False, 'adminIps': []}

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.goto(B + '/module/sicherheit/#einstellungen'); a.wait_for_selector('#e-geo')
    check('summary card Ländersperre (aus)', 'aus' in a.inner_text('#e-geo'), a.inner_text('#e-geo'))
    check('db info shown', 'Stand 17.06.2026' in a.inner_text('#e-geo'), a.inner_text('#e-geo'))
    a.click('[data-e="e-geo"]'); a.wait_for_selector('#sic-dlg[open] #geo-box')
    check('unknown own country hint', 'nicht bekannt' in a.inner_text('#geo-me'))
    check('country list German names', a.locator('.geo-opt').count() > 240 and 'Deutschland' in a.inner_text('#geo-list'), a.locator('.geo-opt').count())
    a.fill('#geo-q', 'china'); a.wait_for_function("document.querySelectorAll('.geo-opt').length === 1")
    check('search filters', a.locator('.geo-opt').count() == 1 and 'China' in a.inner_text('#geo-list'), a.inner_text('#geo-list'))
    a.check('#geo-list [data-geo-cc=CN]')
    a.fill('#geo-q', 'RU'); a.wait_for_selector('#geo-list [data-geo-cc=RU]'); a.check('#geo-list [data-geo-cc=RU]')
    check('chips show selection', 'China' in a.inner_text('#geo-chips') and 'Russland' in a.inner_text('#geo-chips') and '2 ausgewählt' in a.inner_text('#geo-count'))
    a.click('#geo-chips [data-cc=RU]'); a.wait_for_function("!document.querySelector('#geo-chips').textContent.includes('Russland')")
    check('chip remove', 'Russland' not in a.inner_text('#geo-chips') and not a.locator('#geo-list [data-geo-cc=RU]').is_checked())
    # Schnellauswahl und Liste nach Kontinenten
    a.fill('#geo-q', ''); a.wait_for_selector('#geo-list [data-geo-teil="suedamerika"]')
    check('Schnellauswahl: Kontinente und Gruppen', a.eval_on_selector_all('#geo-gruppen [data-g]', 'l => l.map(e => e.dataset.g)')
          == ['europa', 'asien', 'afrika', 'nordamerika', 'suedamerika', 'ozeanien', 'antarktis', 'eu', 'ewr', 'dach', 'nachbarn', 'nato', 'g7', 'brics'])
    check('Liste nach Kontinenten gegliedert, Zähler je Kontinent', a.locator('#geo-list .geo-abschnitt').count() == 7 and '1 von 53 ausgewählt' in a.inner_text('#geo-list [data-geo-teil="asien"] .geo-akopf'),
          a.inner_text('#geo-list [data-geo-teil="asien"] .geo-akopf'))
    box = a.locator('#geo-list .geo-opt input').first.bounding_box()
    check('Auswahlkästchen in normaler Größe (nicht über die ganze Spalte)', box and box['width'] <= 20 and box['height'] <= 20, box)
    a.click('#geo-gruppen [data-g="eu"]'); a.wait_for_selector('#geo-gruppen [data-g="eu"].voll')
    check('EU mit einem Klick: alle 27 dazu (mit China 28), Knopf gedrückt', '28 ausgewählt' in a.inner_text('#geo-count') and a.get_attribute('#geo-gruppen [data-g="eu"]', 'aria-pressed') == 'true'
          and a.locator('#geo-chips .sic-chip').count() == 28, a.inner_text('#geo-count'))
    check('teilweise gewählte Gruppe gekennzeichnet (NATO, Zahl)', a.locator('#geo-gruppen [data-g="nato"].teil').count() == 1 and '/32' in a.inner_text('#geo-gruppen [data-g="nato"]')
          and '27 von 53 ausgewählt' in a.inner_text('#geo-list [data-geo-teil="europa"] .geo-akopf'), a.inner_text('#geo-gruppen [data-g="nato"]'))
    a.emulate_media(color_scheme='dark')
    a.screenshot(path=SH + '/geo-gruppen-dunkel.png')
    a.emulate_media(color_scheme='light')
    a.click('#geo-gruppen [data-g="eu"]'); a.wait_for_selector('#geo-gruppen [data-g="eu"]:not(.voll)')
    check('zweiter Klick nimmt die Gruppe wieder heraus (China bleibt)', '1 ausgewählt' in a.inner_text('#geo-count') and 'China' in a.inner_text('#geo-chips'))
    a.click('#geo-gruppen [data-g="suedamerika"]'); a.wait_for_function("document.querySelector('#geo-count').textContent.startsWith('16')")
    a.click('#geo-gruppen [data-g="brics"]'); a.wait_for_function("document.querySelector('#geo-count').textContent.startsWith('24')")
    check('Kontinent und Gruppe kombinierbar (Südamerika 15 + China + BRICS ohne Doppelte = 24)', '24 ausgewählt' in a.inner_text('#geo-count'), a.inner_text('#geo-count'))
    a.fill('#geo-q', 'brasil'); a.wait_for_function("document.querySelectorAll('#geo-list .geo-opt').length === 1")
    check('Suche zeigt den Treffer unter seinem Kontinent', a.locator('#geo-list .geo-abschnitt').count() == 1 and 'Südamerika' in a.inner_text('#geo-list')
          and a.locator('#geo-list [data-geo-cc=BR]').is_checked())
    a.screenshot(path=SH + '/geo-gruppen.png')
    a.click('#sic-dlg [data-d="geo-leer"]'); a.fill('#geo-q', 'china'); a.check('#geo-list [data-geo-cc=CN]'); a.fill('#geo-q', '')
    check('Leeren nimmt alles heraus, Gruppen wieder ohne Auswahl', '1 ausgewählt' in a.inner_text('#geo-count') and a.locator('#geo-gruppen .geo-gk.voll').count() == 0)
    # leere Auswahl → Fehler
    a.click('#sic-dlg [data-d="geo-leer"]'); a.check('#geo-box [name=geoEnabled]'); ja(a); a.wait_for_selector('#d-err:not(:empty)')
    check('empty selection rejected', 'mindestens ein Land' in a.inner_text('#d-err'))
    a.fill('#geo-q', 'china'); a.check('#geo-list [data-geo-cc=CN]')
    a.screenshot(path=SH + '/geo.png', full_page=True)
    ja(a); a.wait_for_selector('#sic-dlg h2:has-text("Ländersperre speichern?")')
    check('confirm explains (same dialog)', 'China' in a.inner_text('#sic-dlg') and 'nur für den Eingabebereich' in a.inner_text('#sic-dlg'))
    ja(a); a.wait_for_selector('#sic-dlg', state='hidden')
    S = settings(a)
    check('saved: block CN, admin scope', S['geoEnabled'] and S['geoMode'] == 'block' and S['geoCountries'] == ['CN'] and S['geoScope'] == 'admin', S)
    check('card shows 1 Land gesperrt', '1 Land gesperrt' in a.inner_text('#e-geo'), a.inner_text('#e-geo'))
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
    login(de, 'admin', 'Sicheres-Passwort-1'); geo_dialog(de)
    check('own country shown', 'Deutschland' in de.inner_text('#geo-me'))
    de.click('#sic-dlg [data-d="geo-leer"]'); de.fill('#geo-q', 'AT'); de.wait_for_selector('#geo-list [data-geo-cc=AT]'); de.check('#geo-list [data-geo-cc=AT]')
    check('live self-lockout warning', 'aussperren' in de.inner_text('#geo-me') and 'bad' in de.get_attribute('#geo-me', 'class'))
    ja(de); de.wait_for_selector('#sic-dlg h2:has-text("Ländersperre speichern?")'); ja(de); de.wait_for_selector('#d-err:not(:empty)')
    check('server rejects self-lockout (allow)', 'aussperren' in de.inner_text('#d-err'), de.inner_text('#d-err'))
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['DE'], geoScope='admin'), {'X-Forwarded-For': DE})
    check('server rejects self-lockout (block)', r[0] == 422 and 'aussperren' in r[1]['error'], r)
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['DE'], geoScope='admin', adminIps=[DE]), {'X-Forwarded-For': DE})
    check('allowed when own ip is allowlisted', r[0] == 200, r)
    r = post(de, 'security_save', dict(BASE, geoEnabled=True, geoMode='block', geoCountries=['XX', 'cn', 'CN'], geoScope='weird'), {'X-Forwarded-For': DE})
    S = settings(a); check('input sanitized', r[0] == 200 and S['geoCountries'] == ['CN'] and S['geoScope'] == 'admin', S)
    # Statistik
    a.goto(B + '/module/sicherheit/#firewall'); a.wait_for_selector('#fw-verkehr')
    st = get(a, 'security_status')[1]
    ccs = {x['cc']: x['n'] for x in st['geoStats']}
    check('stats counted per country', ccs.get('CN', 0) >= 3 and ccs.get('AU', 0) >= 1 and st['geoBlocked7'] >= 5, (ccs, st['geoBlocked7']))
    check('stats table shown (Firewall & Sperren)', 'Abgewiesene Zugriffe nach Land' in a.inner_text('#tab-firewall') and 'China' in a.inner_text('#tab-firewall'))
    a.click('[data-fw="geo-null"]'); a.wait_for_selector('#sic-dlg[open]'); ja(a); a.wait_for_function("!document.querySelector('#tab-firewall').textContent.includes('Abgewiesene Zugriffe nach Land')")
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
        a.goto(B + '/module/sicherheit/#einstellungen'); a.wait_for_selector('[data-e="geo-update"]')
        a.click('[data-e="geo-update"]')
        a.wait_for_function("document.querySelector('#sic-toast').textContent.includes('Länderdaten')", timeout=120000)
        check('geo_update ok', 'aktualisiert' in a.inner_text('#sic-toast'), a.inner_text('#sic-toast'))
        check('updated db in data dir', os.path.isfile(DATA + '/geo/laender.dat.php'))
        check('lookup after update', get(cn, 'status')[0] == 200)
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page(); m.on('pageerror', lambda e: errs.append('m: ' + str(e)))
    login(m, 'admin', 'Sicheres-Passwort-1'); geo_dialog(m)
    shot(m.locator('#sic-dlg'), SH + '/geo-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    breit = m.evaluate("(() => { const d = document.querySelector('#geo-box'); return d.scrollWidth - d.clientWidth; })()")
    check('mobil: Schnellauswahl und Liste ohne seitliches Scrollen im Dialog', breit <= 1 and m.locator('#geo-gruppen [data-g="eu"]').is_visible(), breit)
    m.locator('#geo-gruppen').scroll_into_view_if_needed()
    m.screenshot(path=SH + '/geo-gruppen-mobil.png')
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
