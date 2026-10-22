import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
from playwright.sync_api import sync_playwright
B = BASE; from umgebung import SH, FIX, REPO, WORK, XL44; res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
def login(pg, u, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', u); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('tr[data-id]')
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    a = br.new_page(viewport={'width': 1711, 'height': 1000}); a.on('pageerror', lambda e: errs.append(str(e)))
    login(a, 'admin', 'Sicheres-Passwort-1'); a.wait_for_timeout(300)
    boxes = [a.locator('#vt-' + v).bounding_box() for v in ['edit', 'hist', 'stock', 'master', 'users', 'log', 'sec']]
    check('tabs stacked vertically', all(boxes[i+1]['y'] > boxes[i]['y'] and abs(boxes[i+1]['x'] - boxes[i]['x']) < 1 for i in range(6)))
    main = a.locator('main.adm-page').bounding_box()
    check('nav left of content', boxes[0]['x'] + boxes[0]['width'] <= main['x'] + 1, (boxes[0], main['x']))
    check('Verwaltung heading for admin', a.locator('#side-admin').is_visible())
    a.screenshot(path=SH + '/sidenav.png')
    a.mouse.wheel(0, 1500); a.wait_for_timeout(300)
    b2 = a.locator('#vt-edit').bounding_box(); tb = a.locator('#topbar').bounding_box()
    check('nav sticky under topbar', b2['y'] >= tb['height'] - 1 and b2['y'] < tb['height'] + 40, (b2['y'], tb['height']))
    for v in ['hist', 'stock', 'master', 'users', 'log', 'sec', 'edit']:
        a.click('#vt-' + v); a.wait_for_timeout(250)
    check('switching views works', a.locator('#view-edit').is_visible() and a.get_attribute('#vt-edit', 'aria-selected') == 'true')
    a.click('#vt-hist'); a.wait_for_timeout(500)
    check('Daten button visible in Preisverlauf', a.locator('#hist-data').is_visible())
    a.click('#vt-stock'); a.wait_for_timeout(300); a.screenshot(path=SH + '/sidenav-stock.png')
    check('Daten button hidden elsewhere', not a.locator('#hist-data').is_visible())
    a.evaluate("async () => { const s = await (await fetch('/api/?action=status')).json(); await fetch('/api/?action=user_save', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify({name:'Eddi', username:'eddi', role:'editor', active:true, password:'Bearbeiter-Zugang-1', mustChange:false})}); }")
    e = br.new_page(viewport={'width': 1440, 'height': 900}); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    check('editor: under Verwaltung only Import (Importzentrale), no admin tabs', e.locator('#side-admin').is_visible() and e.locator('#vt-importe').is_visible()
          and not any(e.locator('#vt-' + v).is_visible() for v in ['users', 'log', 'sec', 'schutz', 'mail', 'auswertung']))
    overlap_js = '''() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
      const hit = (a, b) => a.width && b.width && a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
      const brand = r('#topbar .brand'), st = r('#save-state'), act = r('#topbar .actions');
      return hit(brand, st) || hit(brand, act) || hit(st, act); }'''
    for w in [1440, 1280, 1180, 1024, 768, 390]:
        m = br.new_page(viewport={'width': w, 'height': 844}, is_mobile=w < 500); m.on('pageerror', lambda x: errs.append(str(x)))
        login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_timeout(300)
        m.screenshot(path=SH + f'/sidenav-{w}.png')
        sw = m.evaluate('document.documentElement.scrollWidth'); check(f'{w}px no h-scroll', sw <= w, sw)
        check(f'{w}px top bar: name, save state and buttons do not overlap', not m.evaluate(overlap_js))
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
