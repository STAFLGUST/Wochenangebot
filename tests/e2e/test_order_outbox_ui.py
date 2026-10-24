"""Testgruppe order_outbox_ui: Versand von Bestellwunsch-Mails in der Oberfläche – Empfängeranzeige, Bestätigung, Neuversand ohne Duplikate."""
import sys
from umgebung import shot
from playwright.sync_api import sync_playwright
from order_setup import setup, PW
from kunden_hilfe import B
from umgebung import SH
results=[]
def check(n,c):
    results.append(bool(c));print(('PASS ' if c else 'FAIL ')+n)
smtp,a,k,other,kid,payload,nr=setup()
a.call('bestell_settings_save',dict(enabled=True,to='orders@example.org;abgelehnt@example.org',copy=False))
nr=k.call('kunde_bestellung',{**payload,'requestId':'ui-partial-request-123'})[1]['nr']
with sync_playwright() as p:
    browser=p.chromium.launch();page=browser.new_page(viewport={'width':390,'height':844});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(B+'/admin/');page.fill('#au-user','admin');page.fill('#pw1',PW);page.click('#auth-submit');page.wait_for_selector('tr[data-id]')
    page.click('#vt-orders');page.wait_for_selector('[data-order-nr]')
    check('list flags outstanding recipient','offen' in page.locator('#view-orders').inner_text())
    page.click('[data-order-nr="'+nr+'"]');page.wait_for_selector('.ord-mailjob')
    check('individual recipients displayed',page.locator('.ord-mailjob').count()==2)
    check('only failed recipient offers retry',page.locator('[data-order-mail]').count()==1)
    count=len(smtp.messages);page.click('[data-order-mail]');page.wait_for_selector('#dlg-confirm[open]')
    check('confirmation names recipient and duplicate risk','abgelehnt@example.org' in page.locator('#confirm-body').inner_text() and 'bereits angekommen' in page.locator('#confirm-body').inner_text())
    page.click('#confirm-body [data-v="0"]')
    check('cancel sends no mail',len(smtp.messages)==count)
    page.click('[data-order-mail]');page.click('#confirm-body [data-v="1"]')
    page.wait_for_function("document.querySelector('.ord-outbox').textContent.includes('Versuche: 2')")
    check('failed retry visible','Versand nicht bestätigt' in page.locator('.ord-outbox').inner_text())
    check('successful recipient not duplicated',len(smtp.messages)==count)
    check('mobile no horizontal overflow',page.evaluate('document.documentElement.scrollWidth')<=390)
    shot(page.locator('.ord-outbox'), SH+'/bestellung-versandauftraege.png')
    check('no JavaScript errors',not errors)
    browser.close()
smtp.close();print(f'{sum(results)}/{len(results)} passed');sys.exit(0 if all(results) else 1)
