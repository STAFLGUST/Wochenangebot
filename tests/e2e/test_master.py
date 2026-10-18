import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
FR = re.compile(r'(^|[^a-zäöüß])frisch(?![a-zäöüß])', re.I)

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def names(pg):
    return pg.locator('tr[data-id] input[data-f=name]').evaluate_all('els => els.map(e => e.value)')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify(b)}); return [r.status, await r.json()]; }""", [action, body])
def wait_saved(pg):
    pg.wait_for_function("document.querySelector('#save-state').className.includes('saved')", timeout=8000)
def wait_master(pg):
    pg.wait_for_function("document.querySelector('#ms-state') && document.querySelector('#ms-state').className.includes('saved') && /Gespeichert/.test(document.querySelector('#ms-state').textContent)", timeout=8000)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.wait_for_timeout(500); wait_saved(a)
    left = [n for n in names(a) if FR.search(n)]
    check('frisch removed from names (except frisch/gefr.)', left == ['Backe, frisch/gefr.'], left)
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('10601 → "Roastbeef Fleischmeister", Zustand frisch, Herkunft 4xD', row.locator('input[data-f=name]').input_value() == 'Roastbeef Fleischmeister' and row.locator('select[data-f=condition]').input_value() == 'frisch' and row.locator('input[data-f=origin]').input_value() == '4xD', (row.locator('input[data-f=name]').input_value(), row.locator('input[data-f=origin]').input_value()))
    r10701 = a.locator('tr[data-id]:has(input[data-f="code"][value="10701"])').first
    check('10701 → "Entrecote Fleischmeister" / 4xD', r10701.locator('input[data-f=name]').input_value() == 'Entrecote Fleischmeister' and r10701.locator('input[data-f=origin]').input_value() == '4xD')
    origins = set(a.locator('tr[data-id] input[data-f=origin]').evaluate_all('els => els.map(e => e.value)'))
    check('origins are codes only', origins <= {'', '4xD', '3xD', 'D', 'EG', 'NZ', 'ARG', 'UY', 'PY', 'BR', 'AUS', 'IRL', 'DK', 'ES', 'Südamerika'}, origins)
    r_nz = a.locator('tr[data-id]:has(input[data-f="code"][value="10674"])').first
    check('Neuseeland → NZ, no brand outside Fleischmeister', r_nz.locator('input[data-f=origin]').input_value() == 'NZ' and 'Fleischmeister' not in r_nz.locator('input[data-f=name]').input_value())
    check('cleanup counts as unpublished change', 'noch nicht veröffentlicht' in a.inner_text('#save-state'))
    # manuelle Eingabe
    ni = row.locator('input[data-f=name]'); ni.fill('Roastbeef Fleischmeister frisch'); ni.press('Tab'); a.wait_for_timeout(300)
    check('typed "frisch" is stripped', a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f=name]').first.input_value() == 'Roastbeef Fleischmeister' and 'Zustand' in a.inner_text('#toast'))
    wait_saved(a)
    # Stammdaten: automatisch angelegt
    a.click('#vt-master'); a.wait_for_selector('.mtab'); wait_master(a)
    n = a.locator('.mtab tbody tr').count(); check('master seeded from offer (263 unique codes)', n == 263, n)
    check('dup-code hint', '6 Artikelnummern' in a.inner_text('#view-master'))
    check('all ✓ after seeding', a.locator('.mtab .m-diff').count() == 0 and a.locator('[data-ma=apply-all]').is_disabled())
    a.screenshot(path=SH + '/master.png')
    # Stammsatz ändern → abweichend → übernehmen
    a.fill('#ms-q', '10601'); a.wait_for_timeout(300)
    mi = a.locator('.mtab tr[data-mcode="10601"] input[data-mf=name]'); mi.fill('Roastbeef Färse Fleischmeister frisch'); mi.press('Tab'); wait_master(a)
    check('master name strips frisch', mi.input_value() == 'Roastbeef Färse Fleischmeister')
    check('offer status abweichend', a.locator('.mtab tr[data-mcode="10601"] .m-diff').count() == 1)
    a.click('.mtab tr[data-mcode="10601"] button.m-diff'); a.wait_for_timeout(500)
    check('apply single → ✓', a.locator('.mtab tr[data-mcode="10601"] .m-ok').count() == 1)
    a.click('#vt-edit'); wait_saved(a)
    check('draft item renamed from master', a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f=name]').first.input_value() == 'Roastbeef Färse Fleischmeister')
    # Neuer Stammsatz mit Vorschlag aus Bestand (Bestand importieren)
    master = json.load(open(FIX + '/bestand/master_stock.json'))
    arts = [{'code': x[0].lstrip('0') or '0', 'name': x[1], 'kg': x[2], 'mhd': x[3], 'mhdKg': x[4], 'lots': []} for x in master if x[2] and x[2] > 0]
    post(a, 'stock_import', {'date': '2026-10-16', 'source': 't', 'articles': arts})
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-master'); a.wait_for_selector('.mtab')
    a.click('[data-ma=new]'); a.wait_for_selector('#dlg-master-new[open]')
    a.fill('#master-new-body [name=code]', '11872'); a.press('#master-new-body [name=code]', 'Tab'); a.wait_for_timeout(200)
    check('new: name prefilled from stock without frisch', a.input_value('#master-new-body [name=name]') == 'Rinderfett, EG', a.input_value('#master-new-body [name=name]'))
    a.click('#master-new-body [type=submit]'); wait_master(a)
    check('new master row', a.locator('.mtab tr[data-mcode="11872"]').count() == 1)
    a.fill('#ms-q', '10012'); a.wait_for_timeout(300)
    check('WinAB name shown when different', 'WinAB:' in a.inner_text('.mtab tr[data-mcode="10012"]') if a.locator('.mtab tr[data-mcode="10012"]').count() else True)
    a.fill('#ms-q', '11872'); a.wait_for_timeout(300)
    a.click('.mtab tr[data-mcode="11872"] [data-ma=del]'); a.click('#dlg-confirm [data-v="1"]'); wait_master(a)
    check('master row deleted', a.locator('.mtab tr[data-mcode="11872"]').count() == 0)
    # Excel-Import übernimmt Stammdaten und entfernt frisch
    a.click('#vt-edit')
    with a.expect_file_chooser() as fc: a.click('#btn-import')
    fc.value.set_files(XL44); a.wait_for_selector('#dlg-import [data-ia=apply]', timeout=15000)
    a.click('#dlg-import [data-ia=apply]'); a.wait_for_timeout(600); wait_saved(a)
    left = [n for n in names(a) if FR.search(n)]
    check('import: no frisch in names', all('gefr' in x for x in left), left)
    check('import: master applied (10601 → Roastbeef Färse Fleischmeister)', a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f=name]').first.input_value() == 'Roastbeef Färse Fleischmeister')
    check('import: brand + origin codes applied', a.locator('tr[data-id]:has(input[data-f="code"][value="10701"]) input[data-f=name]').first.input_value() == 'Entrecote Fleischmeister' and a.locator('tr[data-id]:has(input[data-f="code"][value="10701"]) input[data-f=origin]').first.input_value() == '4xD')
    check('import toast mentions Stammdaten', 'Stammdaten' in a.inner_text('#toast'), a.inner_text('#toast'))
    # Artikel-Dialog → als Stammdaten speichern
    r10823 = a.locator('tr[data-id]:has(input[data-f="code"][value="10823"])').first
    r10823.locator('select[data-f=condition]').select_option('dry-aged'); a.wait_for_timeout(300)
    r10823.locator('[data-act=item]').click(); a.wait_for_selector('#dlg-item[open]')
    a.click('#item-body [data-ia=to-master]'); a.wait_for_timeout(1200)
    check('item saved to master', 'Stammdaten für 10823' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.keyboard.press('Escape')
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-master'); a.wait_for_selector('.mtab'); a.fill('#ms-q', '10823'); a.wait_for_timeout(300)
    check('master persisted after reload', a.locator('.mtab tr[data-mcode="10823"] select[data-mf=condition]').input_value() == 'dry-aged')
    # Protokoll
    a.click('#vt-log'); a.wait_for_selector('.ltab'); t = a.inner_text('#log-list')
    check('log: cleanup + Stammdaten', 'vereinheitlicht' in t and 'Stammdaten bearbeitet' in t)
    # Nur ansehen
    post(a, 'user_save', {'name': 'Vera', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    v = br.new_context(viewport={'width': 1440, 'height': 950}).new_page(); v.on('pageerror', lambda e: errs.append('v: ' + str(e)))
    login(v, 'vera', 'Leserin-Zugang-1'); v.click('#vt-master'); v.wait_for_selector('.mtab')
    check('viewer: master read-only', v.locator('.mtab input[data-mf=name]').first.is_disabled() and v.locator('[data-ma=new]').count() == 0)
    r = post(v, 'master_save', {'rev': 99, 'articles': []}); check('viewer cannot save master (403)', r[0] == 403, r[0])
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.click('#vt-master'); m.wait_for_selector('.mtab'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/master-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
