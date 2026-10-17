import sys
import re
from playwright.sync_api import sync_playwright
B = 'http://127.0.0.1:8790'; from umgebung import SH, FIX, REPO, WORK, XL44; res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
def row(pg, code): return pg.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])').first
def wait_saved(pg): pg.wait_for_function("document.querySelector('#save-state').className.includes('saved') || /Keine Änderungen/.test(document.querySelector('#save-state').textContent)", timeout=8000)
def open_pub(pg): pg.click('#btn-publish'); pg.wait_for_selector('#dlg-publish[open]')
def pub_text(pg): return pg.inner_text('#publish-body')
def offer(pg):
    return pg.evaluate("async () => (await (await fetch('/api/?action=offer')).json()).offer")
with sync_playwright() as p:
    br = p.chromium.launch(); a = br.new_page(viewport={'width': 1440, 'height': 950}); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', 'Sicheres-Passwort-1'); a.click('#auth-submit'); a.wait_for_selector('tr[data-id]')
    a.wait_for_timeout(500); wait_saved(a)
    # sauberer Ausgangspunkt: einmal veröffentlichen
    open_pub(a); a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000); a.wait_for_timeout(400)
    pub0 = offer(a); p10601 = next(i for i in pub0['items'] if i['code'] == '10601')
    # Änderungen
    pi = row(a, '10601').locator('input[data-f=price]'); old_price = pi.input_value(); pi.fill('99,99'); pi.press('Tab')
    ni = row(a, '10701').locator('input[data-f=name]'); old_name = ni.input_value(); ni.fill('Entrecote Test'); ni.press('Tab')
    row(a, '10823').locator('[data-act=item]').click(); a.wait_for_selector('#dlg-item[open]'); a.click('#item-body [data-ia=del]'); a.wait_for_timeout(300)
    a.fill('#m-week', str(int(a.input_value('#m-week')) + 1)); a.press('#m-week', 'Tab')
    wait_saved(a)
    open_pub(a); t = pub_text(a)
    check('dialog lists 4 kinds with Rückgängig', a.locator('#publish-body [data-rv]').count() == 4 and 'preisänderungen (1)' in t.lower() and 'entfernt (1)' in t.lower() and 'bearbeitet (1)' in t.lower() and 'kopfdaten' in t.lower(), (a.locator('#publish-body [data-rv]').count(), t[:400]))
    check('changed fields shown', 'Bezeichnung: ' + old_name + ' → Entrecote Test' in t, t)
    a.screenshot(path=SH + '/revert-dialog.png')
    # Abbrechen → nichts passiert
    a.click('#publish-body [data-rv=price]'); a.wait_for_selector('#dlg-confirm[open]')
    ct = a.inner_text('#dlg-confirm')
    check('confirm shows old/new price', '99,99' in ct and 'Ja, rückgängig machen' in ct, ct)
    a.screenshot(path=SH + '/revert-confirm.png')
    a.click('#dlg-confirm [data-v="0"]'); a.wait_for_timeout(200)
    check('cancel keeps change', a.locator('#publish-body [data-rv=price]').count() == 1 and row(a, '10601').locator('input[data-f=price]').input_value() == '99,99')
    check('publish dialog still open after cancel', a.locator('#dlg-publish[open]').count() == 1)
    # Bestätigen
    a.click('#publish-body [data-rv=price]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('price reverted', row(a, '10601').locator('input[data-f=price]').input_value() == old_price and 'Preisänderungen' not in pub_text(a))
    a.click('#publish-body [data-rv=changed]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('name reverted', row(a, '10701').locator('input[data-f=name]').input_value() == old_name)
    a.click('#publish-body [data-rv=removed]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('removed item restored', row(a, '10823').count() == 1)
    ids = a.locator('tr[data-id] input[data-f=code]').evaluate_all('e => e.map(x => x.value)')
    pids = [i['code'] for i in pub0['items']]
    check('restored at original position', ids.index('10823') > 0 and ids[ids.index('10823') - 1] == pids[pids.index('10823') - 1], (ids[ids.index('10823')-1], pids[pids.index('10823')-1]))
    a.click('#publish-body [data-rv=meta]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('meta reverted → no changes', 'Keine Änderungen' in pub_text(a), pub_text(a)[:200])
    a.click('#publish-body [data-close]')
    # neuer Artikel → entfernen
    a.locator('[data-act=add-item]').first.click(); a.wait_for_timeout(300)
    if a.locator('#dlg-item[open]').count(): a.fill('#item-body [name=name]', 'Testartikel Neu') if a.locator('#item-body [name=name]').count() else None; a.keyboard.press('Escape')
    a.wait_for_timeout(300); wait_saved(a)
    open_pub(a)
    check('added listed', a.locator('#publish-body [data-rv=added]').count() == 1, pub_text(a)[:300])
    if a.locator('#publish-body [data-rv=added]').count():
        a.click('#publish-body [data-rv=added]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
        check('added removed', 'Keine Änderungen' in pub_text(a))
    a.click('#publish-body [data-close]'); wait_saved(a)
    # Toolbar-Rückgängig stellt die Rücknahme wieder her
    a.click('#btn-undo'); a.wait_for_timeout(300)
    check('toolbar undo restores reverted state', a.locator('tr[data-id]').count() == len(pub0['items']) + 1)
    # Live unverändert, Entwurf gespeichert
    check('published untouched', offer(a)['items'][0]['id'] == pub0['items'][0]['id'] and next(i for i in offer(a)['items'] if i['code'] == '10601')['price'] == p10601['price'])
    # Mobil
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    m.goto(B + '/admin/'); m.wait_for_selector('#screen-auth:not([hidden])')
    m.fill('#au-user', 'admin'); m.fill('#pw1', 'Sicheres-Passwort-1'); m.click('#auth-submit'); m.wait_for_selector('tr[data-id]')
    r = row(m, '10601').locator('input[data-f=price]'); r.fill('12,34'); r.press('Tab'); m.wait_for_timeout(900)
    m.click('#btn-publish'); m.wait_for_selector('#dlg-publish[open]'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/revert-mobile.png')
    sw = m.evaluate("document.querySelector('#dlg-publish').scrollWidth <= document.querySelector('#dlg-publish').clientWidth + 1")
    check('mobile dialog no overflow', sw)
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
