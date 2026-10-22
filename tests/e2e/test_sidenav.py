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
    # Design „Liquid Glass“ (nur Eingabebereich, admin.css): Glas, dunkles Design, Fallbacks, Druck, Kundenseite unberührt
    g = br.new_page(viewport={'width': 1440, 'height': 900}); g.on('pageerror', lambda x: errs.append(str(x)))
    login(g, 'admin', 'Sicheres-Passwort-1')
    css = lambda sel, prop, pseudo='': g.evaluate('([s, p, ps]) => getComputedStyle(document.querySelector(s), ps || null)[p]', [sel, prop, pseudo])
    check('glass: warm ground', css('body', 'backgroundColor') == 'rgb(244, 241, 238)', css('body', 'backgroundColor'))
    blobs = g.evaluate("(() => { const c = getComputedStyle(document.body, '::before'); return [c.position, c.pointerEvents, c.zIndex, c.backgroundImage]; })()")
    check('glass: three soft colour fields fixed behind the content, no red', blobs[0] == 'fixed' and blobs[1] == 'none' and blobs[2] == '-1'
          and blobs[3].count('radial-gradient') == 3 and '143, 167, 196' in blobs[3] and '226, 165, 74' in blobs[3] and '63, 122, 90' in blobs[3], blobs)
    bf = css('#topbar .topbar-inner', 'backdropFilter', '::before')
    check('glass: top bar capsule blurs the page behind it', 'blur(30px)' in bf and 'saturate(1.8)' in bf, bf)
    check('glass: top bar is a rounded capsule, header itself transparent', css('#topbar .topbar-inner', 'borderTopLeftRadius') == '30px'
          and css('#topbar', 'backgroundColor') == 'rgba(0, 0, 0, 0)', (css('#topbar .topbar-inner', 'borderTopLeftRadius'), css('#topbar', 'backgroundColor')))
    check('glass: side navigation is a glass card', 'blur(30px)' in css('.side-nav', 'backdropFilter') and css('.side-nav', 'borderTopLeftRadius') == '28px')
    check('glass: active nav entry 44 px with 14 px radius', g.locator('#vt-edit').bounding_box()['height'] == 44 and css('#vt-edit', 'borderTopLeftRadius') == '14px')
    check('glass: Veröffentlichen is the coloured button (bordeaux gradient)', 'linear-gradient' in css('#btn-publish', 'backgroundImage')
          and '163, 32, 47' in css('#btn-publish', 'backgroundImage') and css('#btn-publish', 'borderTopLeftRadius') == '999px')
    check('glass: other top bar buttons are neutral pills', css('#btn-preview', 'backgroundImage') == 'none' and css('#btn-preview', 'borderTopLeftRadius') == '999px')
    check('glass: group cards 28 px, offer chips as segment track', css('#groups .gcard', 'borderTopLeftRadius') == '28px'
          and css('#offer-bar .ob-tabs', 'backgroundColor') != 'rgba(0, 0, 0, 0)' and css('#offer-bar .ob-tabs button[aria-selected="true"]', 'borderTopLeftRadius') == '999px')
    check('glass: dense table cards stay mostly opaque', float(css('#groups .gcard', 'backgroundColor').split(',')[-1].strip(' )')) >= .7, css('#groups .gcard', 'backgroundColor'))
    check('glass: price fields 10 px radius', css('#groups tr[data-id] .e-price .in.num', 'borderTopLeftRadius') == '10px')
    sticky = g.evaluate("(() => { const t = document.querySelector('#view-edit .ed-toolbar'); return [getComputedStyle(t).position, getComputedStyle(t).backgroundColor]; })()")
    check('glass: sticky bars dense enough to read without blur', sticky[0] == 'sticky' and float(sticky[1].split(',')[-1].strip(' )')) >= .85, sticky)
    g.click('#btn-more'); g.wait_for_selector('#menu-more:not([hidden])')
    check('glass: menu is glass of its own (not nested in the capsule blur)', 'blur(30px)' in css('#menu-more', 'backdropFilter') and css('#topbar .topbar-inner', 'backdropFilter') == 'none')
    g.keyboard.press('Escape')
    g.evaluate("document.documentElement.dataset.theme = 'dark'")
    check('glass: dark theme via switch', css('body', 'backgroundColor') == 'rgb(18, 16, 17)' and 'blur(30px)' in css('.side-nav', 'backdropFilter'), css('body', 'backgroundColor'))
    g.evaluate("document.documentElement.dataset.theme = 'light'")
    cdp = g.context.new_cdp_session(g)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-transparency', 'value': 'reduce'}]})
    g.wait_for_function("matchMedia('(prefers-reduced-transparency: reduce)').matches")
    check('reduced transparency: no blur, opaque surfaces', css('#topbar .topbar-inner', 'backdropFilter', '::before') == 'none'
          and css('.side-nav', 'backdropFilter') == 'none' and css('#topbar .topbar-inner', 'backgroundColor', '::before') == 'rgb(255, 255, 255)'
          and css('#groups .gcard', 'backgroundColor') == 'rgb(255, 255, 255)', (css('#topbar .topbar-inner', 'backgroundColor', '::before'), css('#groups .gcard', 'backgroundColor')))
    g.evaluate("document.documentElement.dataset.theme = 'dark'")
    check('reduced transparency also in the dark theme', css('#groups .gcard', 'backgroundColor') == 'rgb(29, 26, 26)', css('#groups .gcard', 'backgroundColor'))
    g.evaluate("document.documentElement.dataset.theme = 'light'")
    cdp.send('Emulation.setEmulatedMedia', {'features': []})
    g.emulate_media(media='print')
    check('print: light and without glass', css('body', 'backgroundColor') == 'rgb(255, 255, 255)' and css('#groups .gcard', 'backdropFilter') == 'none'
          and css('body', 'content', '::before') in ('none', 'normal'), (css('body', 'backgroundColor'), css('#groups .gcard', 'backdropFilter')))
    g.emulate_media(media='screen')
    k = br.new_page(viewport={'width': 1440, 'height': 900}); k.on('pageerror', lambda x: errs.append(str(x)))
    k.goto(B + '/'); k.wait_for_selector('#topbar')
    kc = k.evaluate("""(() => { const b = getComputedStyle(document.body), t = getComputedStyle(document.querySelector('#topbar'));
      return [b.backgroundColor, getComputedStyle(document.body, '::before').content, t.backdropFilter, t.backgroundColor,
              [...document.styleSheets].map((s) => s.href || '').filter((h) => /admin/.test(h)).length]; })()""")
    check('customer page unchanged: design „Klar“, no admin stylesheet, no glass', kc == ['rgb(243, 243, 241)', 'none', 'saturate(1.6) blur(14px)', 'rgba(255, 255, 255, 0.9)', 0], kc)
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
