import sys
from umgebung import shot
from umgebung import BASE  # Testserver je Gruppe (parallel)
from playwright.sync_api import sync_playwright
from umgebung import SH
B = BASE; res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
with sync_playwright() as p:
    br = p.chromium.launch(); a = br.new_page(viewport={'width': 1440, 'height': 950}); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', 'Sicheres-Passwort-1'); a.click('#auth-submit'); a.wait_for_selector('tr[data-id]')
    a.click('#vt-sec'); a.wait_for_selector('#geo-box')
    a.fill('#geo-q', '1.0.1.1'); a.wait_for_selector('.geo-iphit', timeout=5000)
    check('IPv4 → China', 'China' in a.inner_text('#geo-list') and '1.0.1.1' in a.inner_text('#geo-list'), a.inner_text('#geo-list'))
    a.check('.geo-iphit input'); a.wait_for_timeout(100)
    check('select from IP hit adds chip', 'China' in a.inner_text('#geo-chips'))
    a.fill('#geo-q', '2003:e5:1234::1'); a.wait_for_function("document.querySelector('#geo-list').textContent.includes('Deutschland')", timeout=5000)
    check('IPv6 → Deutschland', True)
    a.fill('#geo-q', '192.168.1.5'); a.wait_for_function("document.querySelector('#geo-list').textContent.includes('interne Adresse')", timeout=5000)
    check('private ip hint', True)
    a.fill('#geo-q', '999.1.1.1'); a.wait_for_function("document.querySelector('#geo-list').textContent.includes('Keine gültige')", timeout=5000)
    check('invalid ip message', True)
    a.fill('#geo-q', 'chi'); a.wait_for_timeout(200)
    check('name search still works', 'China' in a.inner_text('#geo-list') and a.locator('.geo-iphit').count() == 0)
    a.fill('#geo-q', '77.88.8.8'); a.wait_for_selector('.geo-iphit'); shot(a.locator('#geo-box'), SH + '/geo-ip.png')
    c = br.new_page(); c.goto(B + '/admin/')
    r = c.evaluate("async () => (await fetch('/api/?action=geo_lookup&ip=1.1.1.1')).status")
    check('lookup requires admin login', r == 401, r)
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
