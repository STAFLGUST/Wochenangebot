"""Mehrere Angebote: Kundenangebote mit eigenen Preisen, Verwaltung, Übernahme, Veröffentlichen,
Auslieferung nur an Berechtigte (Regel: Kundenpreise nie öffentlich)."""
import sys
from umgebung import shot
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
from umgebung import SH
from testdaten import de, preis
B = BASE
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('/api/?action=status')).json();
      const r = await fetch('/api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, body: JSON.stringify(b)}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, body])
def get(pg, q):
    return pg.evaluate("""async (q) => { const r = await fetch('/api/?action=' + q); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", q)
def row(pg, code): return pg.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])').first
def wait_saved(pg): pg.wait_for_function("document.querySelector('#save-state').className.includes('saved') || /Keine Änderungen/.test(document.querySelector('#save-state').textContent)", timeout=8000)
def tab(pg, label): return pg.locator(f'#offer-bar [data-offer]:has-text("{label}")').first
def item(offer, code): return next((i for i in offer['items'] if i['code'] == code), None)

P10601, P10823 = preis('10601'), preis('10823')

with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.wait_for_timeout(600); wait_saved(a)
    # sauberer Ausgangspunkt
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]'); a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    labels = a.locator('#offer-bar [data-offer]').all_inner_texts()
    check('offer bar: Standard + 4 Kundenangebote', [re.sub(r'\d+$', '', l).strip() for l in labels] == ['Wochenangebot', 'Chefs Culinar', 'Handelshof, EFS', 'Edeka', 'Bela'], labels)
    check('standard selected by default', a.get_attribute('#offer-bar [data-offer="std"]', 'aria-selected') == 'true')
    # Edeka: eigene Preise
    tab(a, 'Edeka').click(); a.wait_for_timeout(200)
    th = a.locator('.gcard').first.locator('thead').inner_text()
    check('price header names offer', 'Edeka' in th, re.sub(r'\s+', ' ', th))
    vi = row(a, '10601').locator('input[data-f=vprice]')
    check('empty variant shows standard as placeholder', vi.input_value() == '' and vi.get_attribute('placeholder') == 'Std. ' + de(P10601), vi.get_attribute('placeholder'))
    vi.fill('22'); vi.press('Tab'); wait_saved(a)
    check('own price saved + formatted', row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00')
    check('row marked as price change', 'is-price' in row(a, '10601').get_attribute('class'))
    check('changes bar counts offer price', '1 Angebotspreis geändert' in re.sub(r'\s+', ' ', a.inner_text('#changes')), a.inner_text('#changes'))
    check('tab shows count of own prices', tab(a, 'Edeka').inner_text().strip().endswith('1'), tab(a, 'Edeka').inner_text())
    row(a, '10823').locator('[data-act=v-hide]').click(); wait_saved(a)
    check('hide in this offer only', 'is-hidden' in row(a, '10823').locator('td.e-price').get_attribute('class') and row(a, '10823').locator('input[data-f=vprice]').is_disabled())
    bad = row(a, '10701').locator('input[data-f=vprice]'); bad.fill('abc'); bad.press('Tab'); a.wait_for_timeout(200)
    check('invalid offer price rejected', 'invalid' in bad.get_attribute('class') and 'nicht lesbar' in a.inner_text('#toast'))
    bad.fill(''); bad.press('Tab'); wait_saved(a)
    a.screenshot(path=SH + '/angebote-edeka.png')
    # Standard unverändert
    tab(a, 'Wochenangebot').click(); a.wait_for_timeout(200)
    check('standard price untouched', row(a, '10601').locator('input[data-f=price]').input_value() == de(P10601))
    # Veröffentlichen mit Einzel-Rücknahme
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    t = a.inner_text('#publish-body').lower()
    check('publish dialog lists offer prices', 'angebotspreise (2)' in t and 'edeka' in t, t[:300])
    a.click('#publish-body li:has-text("10823") [data-rv=variant]')
    a.wait_for_selector('#dlg-confirm[open]'); check('confirm names offer', 'Edeka' in a.inner_text('#dlg-confirm')); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('revert removes hidden flag', 'angebotspreise (1)' in a.inner_text('#publish-body').lower())
    a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    # Auslieferung
    pub = br.new_page()
    pub.goto(B + '/'); pub.wait_for_selector('tr.row')
    r = get(pub, 'offer')
    raw = json.dumps(r[1])
    check('public offer: no customer prices at all', r[0] == 200 and '"variants"' not in raw and item(r[1]['offer'], '10601')['price']['value'] == P10601, item(r[1]['offer'], '10601')['price'])
    r = get(pub, 'offer&angebot=edeka'); check('customer offer needs login (401)', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=edeka&draft=1'); check('customer draft needs login', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=../x'); check('invalid offer id rejected', r[0] in (401, 404), r[0])
    pub.goto(B + '/?angebot=edeka'); pub.wait_for_timeout(1200)
    check('frontend without login: hint, no prices', 'nur nach Anmeldung' in pub.inner_text('body') and pub.locator('tr.row').count() == 0)
    r = get(a, 'offer&angebot=edeka')
    o = r[1]['offer'] if r[0] == 200 else {'items': [], 'meta': {}}
    check('customer offer resolved for logged-in user', r[0] == 200 and item(o, '10601')['price'] == {'status': 'value', 'value': 22} and o['meta'].get('offerName') == 'Wochenangebot Edeka' and '"variants"' not in json.dumps(o), item(o, '10601'))
    check('fallback: other items show standard price', item(o, '10823') and item(o, '10823')['price']['value'] == P10823)
    f = actx.new_page(); f.goto(B + '/?angebot=edeka'); f.wait_for_selector('tr.row')
    check('frontend shows offer name + own price', 'Wochenangebot Edeka' in f.inner_text('#topbar h1') and '22,00' in f.inner_text('tr.row >> nth=0'), f.inner_text('#topbar h1'))
    f.screenshot(path=SH + '/angebote-frontend.png')
    # Neues Angebot mit Regel „nicht anzeigen“
    a.click('[data-ob=manage]'); a.wait_for_selector('#dlg-offers[open]')
    a.click('[data-ofa=add]'); a.locator('#offers-body [data-of=name]').last.fill('Wochenangebot Metro')
    a.locator('#offers-body tr[data-oi]').last.locator('[data-of=fallback]').select_option('hidden')
    a.click('[data-ofa=save]'); a.wait_for_function("!document.querySelector('#dlg-offers').open", timeout=8000)
    check('new offer tab appears', tab(a, 'Metro').count() == 1)
    tab(a, 'Metro').click(); a.wait_for_timeout(200)
    check('rule hidden: placeholder ausgeblendet', row(a, '10601').locator('input[data-f=vprice]').get_attribute('placeholder') == 'ausgeblendet')
    mi = row(a, '10601').locator('input[data-f=vprice]'); mi.fill('19,5'); mi.press('Tab'); wait_saved(a)
    # Preise übernehmen in Bela (+10 %, auf 0,05)
    tab(a, 'Bela').click(); a.click('[data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open]')
    a.fill('#offer-copy-body [name=pct]', '10'); a.click('#offer-copy-body [type=submit]'); wait_saved(a)
    exp = round(round(P10823 * 1.1 / 0.05) * 0.05, 2)
    check('copy with surcharge + rounding', row(a, '10823').locator('input[data-f=vprice]').input_value() == de(exp), (row(a, '10823').locator('input[data-f=vprice]').input_value(), de(exp)))
    check('copy toast', 'übernommen' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.click('#btn-undo'); a.wait_for_timeout(300)
    check('copy undoable', row(a, '10823').locator('input[data-f=vprice]').input_value() == '')
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]'); a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    ids = {x['id']: x['name'] for x in get(a, 'offers')[1]['offers']}
    metro = next(k for k, v in ids.items() if 'Metro' in v)
    r = get(a, f'offer&angebot={metro}')
    check('rule hidden: only own prices delivered', r[0] == 200 and [i['code'] for i in r[1]['offer']['items']] == ['10601'], len(r[1]['offer']['items']) if r[0] == 200 else r)
    # Vorwoche je Angebot
    tab(a, 'Edeka').click(); a.fill('#m-week', str(int(a.input_value('#m-week')) + 1)); a.press('#m-week', 'Tab'); a.wait_for_timeout(1500)
    pc = row(a, '10601').locator('td.e-prev').inner_text().strip()
    check('Vorwoche shows previous offer price', pc.startswith('22,00'), pc)
    a.fill('#m-week', str(int(a.input_value('#m-week')) - 1)); a.press('#m-week', 'Tab'); wait_saved(a)
    # Rechte
    post(a, 'user_save', {'name': 'Eddi', 'username': 'eddi', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    post(a, 'user_save', {'name': 'Vera', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    e = br.new_page(viewport={'width': 1440, 'height': 950}); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    cur = get(e, 'offers')[1]
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': [o for o in cur['offers'] if o['id'] != metro]})
    check('editor cannot delete offers (403)', r[0] == 403, r)
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': 'test', 'name': 'Wochenangebot', 'fallback': 'standard'}]})
    check('duplicate/reserved name rejected', r[0] == 422, r)
    r = post(e, 'offers_save', {'rev': cur['rev'] - 1, 'offers': cur['offers']})
    check('stale revision rejected (409)', r[0] == 409, r[0])
    v = br.new_page(viewport={'width': 1440, 'height': 950}); login(v, 'vera', 'Leserin-Zugang-1')
    tv = v.locator('#offer-bar [data-offer]:has-text("Edeka")').first; tv.click(); v.wait_for_timeout(200)
    check('viewer: can switch, inputs locked, no manage', v.locator('tr[data-id] input[data-f=vprice]').first.is_disabled() and v.locator('[data-ob=manage]').count() == 0)
    # Admin löscht Angebot
    a.click('[data-ob=manage]'); a.wait_for_selector('#dlg-offers[open]')
    a.locator('#offers-body tr[data-oi]:has(input[value*="Metro"]) [data-ofa=del]').click(); a.click('#dlg-confirm [data-v="1"]')
    a.click('[data-ofa=save]'); a.wait_for_function("!document.querySelector('#dlg-offers').open", timeout=8000)
    check('admin deletes offer: tab gone', tab(a, 'Metro').count() == 0)
    r = get(a, f'offer&angebot={metro}'); check('deleted offer not deliverable (404)', r[0] == 404, r[0])
    # Protokoll
    log = json.dumps(get(a, 'log')[1], ensure_ascii=False)
    check('audit: offers + offer prices logged', 'Angebote geändert' in log and 'Preis Wochenangebot Edeka' in log)
    # Mobil
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); m.on('pageerror', lambda x: errs.append('m: ' + str(x)))
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_timeout(300)
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    shot(m.locator('#offer-bar'), SH + '/angebote-mobil.png')
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
