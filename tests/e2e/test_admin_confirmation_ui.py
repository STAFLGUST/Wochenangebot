"""Abgelaufene Admin-Freigabe: Abbruch, Fehlversuch und einmalige Wiederholung im Browser."""
import sys
from playwright.sync_api import sync_playwright
from auth_helpers import expire_session, PW
results=[]
def check(name,value):
    results.append(bool(value)); print(('PASS ' if value else 'FAIL ')+name)
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':390,'height':844})
    errors=[]; saves=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r:saves.append(r.status) if 'action=security_save' in r.url else None)
    page.goto('http://127.0.0.1:8790/admin/')
    page.fill('#au-user','admin');page.fill('#pw1',PW);page.click('#auth-submit')
    page.wait_for_selector('tr[data-id]');page.click('#vt-sec');page.wait_for_selector('#sec-form')
    sid=next(c['value'] for c in page.context.cookies() if c['name']=='WA_ADMIN')
    expire_session(sid)
    page.locator('#sec-form [name="pwMin"]').fill('12')
    page.locator('#sec-form button[type="submit"]').click()
    page.wait_for_selector('#dlg-reauth[open]')
    check('confirmation dialog shown',page.locator('#reauth-password').is_visible())
    check('mobile dialog fits',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    page.locator('#dlg-reauth [data-close]').click()
    page.wait_for_selector('#sec-err:not(:empty)')
    check('cancel does not retry mutation',saves==[403])
    check('input retained after cancel',page.locator('#sec-form [name="pwMin"]').input_value()=='12')
    page.locator('#sec-form button[type="submit"]').click();page.wait_for_selector('#dlg-reauth[open]')
    page.fill('#reauth-password','Falsch-Geheimnis-123');page.click('#reauth-submit')
    page.wait_for_selector('#reauth-error:not(:empty)')
    check('wrong password keeps dialog open',page.locator('#dlg-reauth').is_visible())
    check('wrong password clears input',page.locator('#reauth-password').input_value()=='')
    check('wrong password never retries mutation',saves==[403,403])
    page.fill('#reauth-password',PW);page.click('#reauth-submit')
    page.wait_for_selector('#dlg-reauth',state='hidden')
    page.wait_for_function('document.querySelector("#toast").textContent.includes("Sicherheitseinstellungen gespeichert")')
    check('valid confirmation retries exactly once',saves==[403,403,200])
    check('password cleared after success',page.locator('#reauth-password').input_value()=='')
    check('original setting saved',page.locator('#sec-form [name="pwMin"]').input_value()=='12')
    check('no script errors',not errors)
    browser.close()
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
