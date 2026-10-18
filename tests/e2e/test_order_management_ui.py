import sys
from playwright.sync_api import sync_playwright
from order_setup import setup, PW
from kunden_hilfe import B

results=[]
def check(name,condition):
    results.append(bool(condition));print(('PASS ' if condition else 'FAIL ')+name)
smtp,a,k,other,kid,payload,nr=setup()
with sync_playwright() as p:
    browser=p.chromium.launch();errors=[]
    page=browser.new_page(viewport={'width':1440,'height':950});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(B+'/admin/');page.fill('#au-user','admin');page.fill('#pw1',PW);page.click('#auth-submit');page.wait_for_selector('tr[data-id]')
    page.click('#vt-orders');page.wait_for_selector('[data-order-nr]')
    check('order listed and escaped', 'Kantine <Test>' in page.locator('#view-orders').inner_text())
    page.click('[data-order-nr]');page.wait_for_selector('#order-edit-form')
    check('snapshot positions shown',page.locator('#order-edit-form li').count()>0)
    page.select_option('#order-edit-form [name=workflow]','in_bearbeitung');page.fill('#order-edit-form [name=note]','Internal <script>window.orderXss=true</script>')
    page.click('#order-edit-form [type=submit]');page.wait_for_selector('#dlg-order-admin:not([open])')
    page.click('[data-order-nr]');page.wait_for_selector('#order-edit-form')
    check('workflow persisted',page.input_value('#order-edit-form [name=workflow]')=='in_bearbeitung')
    check('note rendered safely',page.evaluate('window.orderXss') is None)
    page.click('#order-edit-form [data-close]');page.set_viewport_size({'width':390,'height':844})
    check('mobile orders no horizontal overflow',page.evaluate('document.documentElement.scrollWidth')<=390)
    customer=browser.new_page(viewport={'width':390,'height':844});customer.on('pageerror',lambda e:errors.append(str(e)))
    customer.goto(B+'/');customer.click('#btn-kunde-login');customer.fill('#kl-form [name=username]','kantine.test');customer.fill('#kl-form [name=password]','Kantine-Kennwort-5');customer.click('#kl-form [type=submit]')
    customer.wait_for_selector('#btn-kunde');customer.click('#btn-kunde');customer.click('[data-kact=orders]');customer.wait_for_selector('[data-customer-order]')
    check('customer history shows order',nr in customer.locator('#dlg-customer-orders').inner_text())
    customer.click('[data-customer-order]');customer.wait_for_selector('[data-customer-orders-page]')
    check('customer sees processing status','In Bearbeitung' in customer.locator('#dlg-customer-orders').inner_text())
    check('internal note not shown','Internal' not in customer.locator('#dlg-customer-orders').inner_text())
    check('customer mobile no overflow',customer.evaluate('document.documentElement.scrollWidth')<=390)
    check('no JavaScript errors',not errors)
    browser.close()
smtp.close()
print(f'{sum(results)}/{len(results)} passed');sys.exit(0 if all(results) else 1)
