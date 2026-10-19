"""Exakte Wochenpreise, separate erfasste Zugänge, Validierung, Rechte und Anzeige."""
import copy
import json
import os
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import FIX, SH, storage_docs

results = []
def check(name, ok, info=''):
    results.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + name + (' ' + str(info) if info else ''))

with open(os.path.join(FIX, 'bestand', 'overview.json'), encoding='utf-8') as f:
    fixture = json.load(f)
A = Client()
assert A.call('login', {'username':'admin', 'password':'Sicheres-Passwort-1'})[0] == 200
payload = {k:fixture[k] for k in ('date','source','articles','incoming')}
check('import separates stock and incoming', A.call('stock_import', payload)[0] == 200)
before = storage_docs('historie')
r = A.call('stock')[1]
check('stock read never writes history', storage_docs('historie') == before)
check('incoming persisted individually; not counted as stock', r['stock']['incoming'] == payload['incoming'] and r['stock']['articles'][0]['kg'] == 12.5 and len(r['stock']['articles']) == 4)
for which in ('current','previous'):
    week = r['prices'][which]
    items = [{'code':fixture['articles'][i]['code'], 'name':fixture['articles'][i]['name'], 'price':{'status':'value','value':v}} for i,v in enumerate(fixture[which])]
    assert A.call('history_import', {'week':week['week'], 'year':week['year'], 'source':'Synthetische Testpreise', 'items':items})[0] == 200
check('only standard prices returned', all(set(i) == {'code','price'} for i in A.call('stock')[1]['prices']['current']['items']))
for bad in (-1, 0, '12', 10000001):
    p = copy.deepcopy(payload); p['incoming'][0]['kg'] = bad
    check('invalid quantity rejected: ' + str(bad), A.call('stock_import', p)[0] == 422)
p = copy.deepcopy(payload); p['incoming'][0]['arrival'] = '2026-02-30'
check('invalid ETA rejected', A.call('stock_import', p)[0] == 422)
check('failed import keeps previous state', A.call('stock')[1]['stock']['incoming'] == payload['incoming'])
check('anonymous cannot see stock or ETA', Client('198.51.100.4').call('stock')[0] == 401)
public = json.dumps(Client('198.51.100.4').call('offer')[1])
check('public offer contains no incoming/ETA', 'incoming' not in public and 'TEST-A' not in public and 'arrival' not in public)
assert A.call('user_save', {'id':'','name':'Test Leserin','username':'stockreader','role':'viewer','active':True,'password':'Leserin-Zugang-1','mustChange':False,'deny':['preisverlauf.sehen']})[0] == 200
V = Client('198.51.100.5'); assert V.call('login', {'username':'stockreader','password':'Leserin-Zugang-1'})[0] == 200
check('history permission respected in stock response', V.call('stock')[1]['prices'] == {'allowed':False})
check('viewer cannot import incoming', V.call('stock_import', payload)[0] == 403)
assert A.call('user_save', {'id':'','name':'Test Ohne Bestand','username':'nostock','role':'viewer','active':True,'password':'Leserin-Zugang-1','mustChange':False,'deny':['bestand.sehen']})[0] == 200
N = Client('198.51.100.6'); assert N.call('login', {'username':'nostock','password':'Leserin-Zugang-1'})[0] == 200
check('stock permission required', N.call('stock')[0] == 403)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={'width':1440,'height':1000})
    errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(B + '/admin/')
    page.fill('#au-user','admin'); page.fill('#pw1','Sicheres-Passwort-1'); page.click('#auth-submit')
    page.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    page.click('#vt-stock'); page.wait_for_selector('.stab tr.srow')
    def row(code):
        return page.locator('.stab tr.srow').filter(has=page.locator('td.s-code', has_text=code))
    check('current and previous prices visible', '12,00' in row('900001').locator('.s-vk').inner_text() and '10,00' in row('900001').locator('.s-prev').inner_text())
    check('increase red and plus', row('900001').locator('.st-price-change.up').inner_text() == '+2,00 €')
    check('decrease green and minus', row('900002').locator('.st-price-change.down').inner_text() == '−2,00 €')
    check('unchanged neutral', row('900003').locator('.st-price-change.same').inner_text() == 'unverändert')
    check('missing history explicit', row('900004').locator('.s-change').inner_text() == 'keine Vergleichsdaten')
    check('recorded stock with unit', row('900001').locator('.s-kg').inner_text() == '12,50 kg')
    check('requested column order', [x.replace('\n', ' ') for x in page.locator('.stab thead th').all_inner_texts()] == ['Art.-Nr.', 'Art. Bezeichnung', 'Aktueller Preis KW ' + str(r['prices']['current']['week']) + '/' + str(r['prices']['current']['year']), 'Preis Vorwoche KW ' + str(r['prices']['previous']['week']) + '/' + str(r['prices']['previous']['year']), 'Preisänderung', 'Kürz. MHD', 'Kg kürz. MHD', 'Erfasster Bestand', 'Erwartete Zugänge'])
    check('bold headings', page.locator('.stab thead th').evaluate_all("els => els.every(e => +getComputedStyle(e).fontWeight >= 700)"))
    check('missing price is dash', row('900004').locator('.s-prev').inner_text() == '—' and row('900005').locator('.s-vk').inner_text() == '—')
    check('deliveries collapsed to button', row('900001').locator('.s-incoming button').inner_text() == 'Zugänge (2)' and page.locator('.stab .st-incoming').count() == 0)
    row('900001').locator('[data-incoming]').click(); page.wait_for_selector('#dlg-stock-item[open]')
    check('arrival button opens focused dialog', page.locator('#sa-title').inner_text() == 'Erwartete Zugänge' and page.locator('#dlg-stock-item .st-incoming li').count() == 2 and '22.10.2026' in page.locator('#dlg-stock-item').inner_text() and '30,00 kg' in page.locator('#dlg-stock-item').inner_text() and page.locator('#dlg-stock-item .lottab').count() == 0)
    page.screenshot(path=os.path.join(SH, 'stock-incoming-dialog.png'))
    page.keyboard.press('Escape')
    row('900005').locator('[data-incoming]').focus(); page.keyboard.press('Enter'); page.wait_for_selector('#dlg-stock-item[open]')
    check('keyboard dialog, missing ETA and escaped text', 'ETA unbekannt' in page.locator('#dlg-stock-item').inner_text() and 'kein eingelagerter Bestand erfasst' in row('900005').inner_text() and page.locator('#dlg-stock-item img, #dlg-stock-item b').count() == 0)
    page.locator('#dlg-stock-item .dlg-foot [data-close]').click()
    with page.expect_download() as download: page.click('[data-st=csv]')
    with open(download.value.path(), encoding='utf-8-sig') as f: csv = f.read()
    check('CSV contains price comparison and separate deliveries', 'Vorwoche KW' in csv and 'TEST-A' in csv and 'TEST-B' in csv and 'keine Vergleichsdaten' in csv)
    with page.context.expect_page() as popup: page.click('[data-st=print]')
    printpage = popup.value; printpage.wait_for_load_state()
    check('print includes comparison and deliveries', 'TEST-A' in printpage.inner_text('body') and 'Vorwoche' in printpage.inner_text('body'))
    printpage.close()
    page.wait_for_function("!document.querySelector('#toast').classList.contains('show')")
    for width in (1440,390):
        page.set_viewport_size({'width':width,'height':1000})
        for theme in ('light','dark'):
            page.evaluate('(t) => document.documentElement.dataset.theme=t', theme)
            page.screenshot(path=os.path.join(SH, f'stock-overview-{width}-{theme}.png'), full_page=True, animations='disabled')
            check(f'no horizontal page overflow {width}/{theme}', page.evaluate('document.documentElement.scrollWidth') <= width)
    row('900001').locator('[data-incoming]').click(); page.wait_for_selector('#dlg-stock-item[open]')
    check('mobile arrival button works', page.locator('#sa-title').inner_text() == 'Erwartete Zugänge')
    page.screenshot(path=os.path.join(SH, 'stock-incoming-mobile.png'), animations='disabled')
    page.keyboard.press('Escape')
    row('900001').locator('.s-name').click(); page.wait_for_selector('#dlg-stock-item[open]')
    check('detail shows both deliveries', page.locator('#dlg-stock-item .st-incoming li').count() == 2)
    page.keyboard.press('Escape')
    check('no JavaScript errors', not errors, errors)
    browser.close()

# Older documents remain valid; subsequent import clears obsolete ETA rows.
legacy = {k:v for k,v in payload.items() if k != 'incoming'}
check('legacy import accepted without invented incoming', A.call('stock_import', legacy)[1]['stock']['incoming'] == [])
only = {**payload, 'articles':[]}
check('incoming-only import valid, no available stock', A.call('stock_import', only)[1]['stock']['articles'] == [])
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
