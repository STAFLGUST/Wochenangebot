"""Testgruppe sidenav: Navigation des Eingabebereichs, Sichtbarkeit je Rolle, Kopfzeile ohne Überlappung und Darstellung je Bildschirmbreite."""
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
    check('eigene Anmeldung (ohne zentrale Anmeldung): kein Dashboard-Knopf', a.locator('#btn-dashboard').count() == 1 and a.locator('#btn-dashboard').is_hidden())
    boxes = [a.locator('#vt-' + v).bounding_box() for v in ['edit', 'hist', 'stock', 'master', 'users', 'log']]
    check('tabs stacked vertically', all(boxes[i+1]['y'] > boxes[i]['y'] and abs(boxes[i+1]['x'] - boxes[i]['x']) < 1 for i in range(len(boxes) - 1)))
    main = a.locator('main.adm-page').bounding_box()
    check('nav left of content', boxes[0]['x'] + boxes[0]['width'] <= main['x'] + 1, (boxes[0], main['x']))
    check('Verwaltung heading for admin', a.locator('#side-admin').is_visible())
    a.screenshot(path=SH + '/sidenav.png')
    a.mouse.wheel(0, 1500); a.wait_for_timeout(300)
    b2 = a.locator('#vt-edit').bounding_box(); tb = a.locator('#topbar').bounding_box()
    check('nav sticky under topbar', b2['y'] >= tb['height'] - 1 and b2['y'] < tb['height'] + 40, (b2['y'], tb['height']))
    for v in ['hist', 'stock', 'master', 'users', 'log', 'edit']:
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
      const h1 = r('#topbar h1');
      return hit(brand, st) || hit(brand, act) || hit(st, act) || hit(h1, act) || hit(h1, st); }'''
    for w in [1536, 1440, 1401, 1366, 1361, 1280, 1180, 1024, 768, 390]:
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
    # Rückweg zum Dashboard: Antwort des Servers unter zentraler Anmeldung nachgestellt (echter Ablauf: tests/oidc/)
    def zentral(route, adresse):
        r = route.fetch(); j = r.json()
        if j.get('user'):
            j['user'].update({'zentral': True, 'bereich': 'angebot.eingabe', 'dashboard': adresse})
        route.fulfill(response=r, json=j)
    for w in (1920, 1601, 1440, 1366, 1361, 1280, 1181, 1024, 390):
        z = br.new_page(viewport={'width': w, 'height': 844}, is_mobile=w < 500); z.on('pageerror', lambda x: errs.append(str(x)))
        login(z, 'admin', 'Sicheres-Passwort-1')
        z.route('**/api/?action=status*', lambda route: zentral(route, 'https://dashboard-stafl.de/'))
        z.reload(); z.wait_for_selector('#btn-dashboard:not([hidden])')
        zb = z.locator('#btn-dashboard').bounding_box(); lb = z.locator('#topbar .brand-logo').bounding_box()
        check(f'{w}px zentrale Anmeldung: Knopf „Dashboard“ links vor dem Logo, Ziel vom Server', z.get_attribute('#btn-dashboard', 'href') == 'https://dashboard-stafl.de/'
              and zb['x'] + zb['width'] <= lb['x'] + 1 and abs((zb['y'] + zb['height'] / 2) - (lb['y'] + lb['height'] / 2)) < 4, (zb, lb))
        lbl = z.locator('#btn-dashboard .lbl').bounding_box()
        if w > 1600:
            check(f'{w}px breit: Pfeil und Beschriftung „Dashboard“ sichtbar', lbl['width'] > 40 and z.locator('#btn-dashboard svg use[href="#i-back"]').is_visible(), lbl)
        else:
            check(f'{w}px Beschriftung „Dashboard“ nur für Screenreader, Pfeil (wie auf allen Modulseiten), Fläche ≥ 36 px', lbl['width'] <= 1 and zb['width'] >= 36 and zb['height'] >= 36
                  and z.locator('#btn-dashboard svg use[href="#i-back"]').is_visible(), (lbl, zb))
        check(f'{w}px mit Knopf: Kopfzeile ohne Überlappung, kein waagerechtes Scrollen', not z.evaluate(overlap_js)
              and z.evaluate('document.documentElement.scrollWidth') <= w)
        z.screenshot(path=SH + f'/dashboard-knopf-{w}.png')
        z.evaluate("document.documentElement.dataset.theme = 'dark'")
        z.screenshot(path=SH + f'/dashboard-knopf-{w}-dunkel.png')
        z.unroute('**/api/?action=status*')
        z.route('**/api/?action=status*', lambda route: zentral(route, 'javascript:alert(1)'))
        z.reload(); z.wait_for_function("document.querySelector('#menu-user').textContent.includes('admin')")
        check(f'{w}px ungültige Dashboard-Adresse: Knopf bleibt verborgen', z.locator('#btn-dashboard').is_hidden())
        z.close()
    # Darstellungsfehler des Eingabebereichs (Prüfung aller Ansichten, PR „layout-eingabebereich“)
    KONTRAST = '''(sel) => { const el = document.querySelector(sel); if (!el) return null;
      const p = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
      const L = (c) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
      const lagen = []; for (let a = el; a; a = a.parentElement) { const c = p(getComputedStyle(a).backgroundColor); if (c[3] > 0) { lagen.push(c); if (c[3] >= 1) break; } }
      let g = p(getComputedStyle(document.body).backgroundColor).slice(0, 3);
      for (let i = lagen.length - 1; i >= 0; i--) g = g.map((v, k) => v * (1 - lagen[i][3]) + lagen[i][k] * lagen[i][3]);
      const t = p(getComputedStyle(el).color), f = t.slice(0, 3).map((v, k) => g[k] * (1 - t[3]) + v * t[3]);
      const a = L(f), b = L(g); return Math.round((Math.max(a, b) + .05) / (Math.min(a, b) + .05) * 100) / 100; }'''
    innen = lambda pg, sel, box: pg.evaluate('''([s, b]) => { const r = document.querySelector(s).getBoundingClientRect(), c = document.querySelector(b).getBoundingClientRect();
      return r.top >= c.top - 1 && r.bottom <= c.bottom + 1 && r.left >= c.left - 1 && r.right <= c.right + 1; }''', [sel, box])
    d = br.new_page(viewport={'width': 1440, 'height': 900}); d.on('pageerror', lambda x: errs.append(str(x)))
    d.on('console', lambda m: errs.append('Konsole: ' + m.text) if m.type == 'error' else None)
    login(d, 'admin', 'Sicheres-Passwort-1')
    # Leser-Konto mit der frischen Anmeldung anlegen: user_save braucht eine Bestätigung jünger als 5 Minuten – mit der
    # Sitzung vom Testbeginn scheiterte das unter Last still (danach fehlte das Leser-Konto in der Liste)
    d.evaluate("async () => { const s = await (await fetch('/api/?action=status')).json(); await fetch('/api/?action=user_save', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify({name:'Lea', username:'lea', role:'viewer', active:true, password:'Leserin-Zugang-11', mustChange:false})}); }")
    d.click('#vt-log'); d.wait_for_selector('#vt-log[aria-selected="true"]')
    check('1440×900: side navigation scrolls the active entry (Protokoll, last) into view', d.evaluate("document.querySelector('.side-nav').scrollHeight > document.querySelector('.side-nav').clientHeight")
          and innen(d, '#vt-log', '.side-nav'))
    d.click('#vt-edit'); d.wait_for_selector('#offer-bar .ob-tabs button small')
    for th in ('light', 'dark'):
        d.evaluate(f"document.documentElement.dataset.theme = '{th}'")
        k = d.evaluate(KONTRAST, '#offer-bar .ob-tabs button:not([aria-selected="true"]) small')
        check(f'{th}: counter in the „Preise für“ segment has contrast ≥ 4.5:1', k is not None and k >= 4.5, k)
    d.evaluate("document.documentElement.dataset.theme = 'dark'")
    d.evaluate("document.querySelector('#groups').insertAdjacentHTML('afterbegin', '<span class=\"nostock\" id=\"t-nostock\">0</span><div class=\"mhd-card\"><span class=\"np-badge\" id=\"t-badge\">65</span></div>')")
    k = [d.evaluate(KONTRAST, '#t-nostock'), d.evaluate(KONTRAST, '#t-badge')]
    check('dark: no-stock mark and short-MHD count readable on their light fill (≥ 4.5:1)', all(x and x >= 4.5 for x in k), k)
    d.evaluate("document.querySelectorAll('#t-nostock, #t-badge').forEach((e) => e.closest('.mhd-card') ? e.closest('.mhd-card').remove() : e.remove())")
    d.click('#vt-users'); d.wait_for_selector('#view-users .role-b.r-viewer')
    for th in ('light', 'dark'):
        d.evaluate(f"document.documentElement.dataset.theme = '{th}'")
        k = d.evaluate(KONTRAST, '#view-users .role-b.r-viewer')
        check(f'{th}: role badge „Nur ansehen“ has contrast ≥ 4.5:1', k is not None and k >= 4.5, k)
    d.evaluate("document.documentElement.dataset.theme = 'light'")
    d.click('#vt-angebote'); d.wait_for_selector('#view-angebote .of-card')
    gap = d.evaluate("document.querySelector('#view-angebote .of-card').getBoundingClientRect().top - document.querySelector('#view-angebote > .st-info').getBoundingClientRect().bottom")
    check('Stammdaten → Angebote: gap between explanation card and table card', gap >= 12, gap)
    d.set_viewport_size({'width': 960, 'height': 900}); d.click('#vt-edit'); d.wait_for_selector('#groups .gcard table')
    d.wait_for_function("document.querySelector('#groups .gcard table').getBoundingClientRect().width > 0")
    sw = d.evaluate('[document.documentElement.scrollWidth, getComputedStyle(document.querySelector("#groups .gcard")).overflowX]')
    check('960 px (navigation beside the content): wide tables scroll inside their card, not the page', sw[0] <= 960 and sw[1] == 'auto', sw)
    d.close()
    # Handy mit Fingerbedienung: aktive Ansicht in der Spur sichtbar, Zielgrößen ≥ 36 px, Kontrast, Dialogkopf, Fußleisten
    h = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); h.on('pageerror', lambda x: errs.append(str(x)))
    login(h, 'admin', 'Sicheres-Passwort-1')
    h.click('#vt-log'); h.wait_for_selector('#vt-log[aria-selected="true"]')
    check('390 px: active entry (Protokoll, last) scrolled into view in the navigation track', innen(h, '#vt-log', '.side-tabs'))
    hs = h.evaluate("[...document.querySelectorAll('.side-tabs button')].filter((e) => e.offsetParent).map((e) => Math.round(e.getBoundingClientRect().height))")
    check('390 px touch: navigation entries at least 36 px high', hs and min(hs) >= 36, hs)
    k = h.evaluate(KONTRAST, '.side-tabs button[aria-selected="false"]:not([hidden])')
    check('390 px: inactive navigation entries have contrast ≥ 4.5:1 on the track', k is not None and k >= 4.5, k)
    h.click('#vt-edit'); h.wait_for_selector('#offer-bar .ob-tabs button')
    hs = h.evaluate("[...document.querySelectorAll('#offer-bar .ob-tabs button, #offer-bar .btn.sm, #groups .gfoot .btn')].filter((e) => e.offsetParent).map((e) => Math.round(e.getBoundingClientRect().height))")
    check('390 px touch: segment buttons and small buttons at least 36 px high', hs and min(hs) >= 36, hs)
    h.click('#btn-more'); h.click('#menu-more [data-act="password"]'); h.wait_for_selector('#dlg-password[open]')
    xb = h.evaluate("(() => { const b = document.querySelector('#dlg-password .dlg-head .btn.icon'); return [b.offsetWidth, b.offsetHeight]; })()")   # Layoutgröße (Öffnungsanimation skaliert)
    check('390 px: dialog close button keeps its size next to the title (≥ 36 px)', min(xb) >= 36, xb)
    h.keyboard.press('Escape')
    h.click('#vt-rollen'); h.wait_for_selector('#view-rollen .rl-foot [data-rl-akt="speichern"]')
    fb = h.evaluate("[...document.querySelectorAll('#view-rollen .rl-foot .btn, #view-rollen .rl-det-akt .btn')].map((b) => { const r = b.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right)]; })")
    check('390 px: buttons of roles and rights wrap inside the screen', all(l >= 0 and r <= 390 for l, r in fb), fb)
    h.click('#vt-angebote'); h.wait_for_selector('#view-angebote tr.of-std')
    st = h.evaluate("(() => { const r = document.querySelector('#view-angebote tr.of-std'); return [getComputedStyle(r).backgroundColor, [...r.children].filter((t) => t.offsetParent).map((t) => getComputedStyle(t).backgroundColor)]; })()")
    check('390 px: standard offer card evenly shaded (row, not stripes per cell)', st[0] != 'rgba(0, 0, 0, 0)' and all(c == 'rgba(0, 0, 0, 0)' for c in st[1]), st)
    h.screenshot(path=SH + '/sidenav-390-angebote.png')
    h.close()
    # Bereichs-Host Verwaltung: Seitenleiste beginnt mit der Überschrift „Stammdaten“ – ohne Trennlinie darüber
    v = br.new_page(viewport={'width': 1440, 'height': 900}); v.on('pageerror', lambda x: errs.append(str(x)))
    login(v, 'admin', 'Sicheres-Passwort-1')
    def verwaltung(route):
        r = route.fetch(); j = r.json()
        if j.get('user'):
            j['user'].update({'zentral': True, 'bereich': 'verwaltung.verwaltung', 'dashboard': 'https://dashboard-stafl.de/'})
        route.fulfill(response=r, json=j)
    v.route('**/api/?action=status*', verwaltung)
    v.reload(); v.wait_for_selector('#btn-dashboard:not([hidden])'); v.wait_for_selector('#vt-edit[hidden]', state='attached')
    sep = v.evaluate("[getComputedStyle(document.querySelector('#side-stamm')).borderTopWidth, getComputedStyle(document.querySelector('#side-admin')).borderTopWidth]")
    check('area host Verwaltung: first heading without a separator line above, later headings with one', sep == ['0px', '1px'], sep)
    v.screenshot(path=SH + '/sidenav-bereich-verwaltung.png')
    v.close()
    # Kachel „Import“ (verwaltung…/import/ → ?ansicht=importe&nur=import): nur die Importzentrale, ohne Seitenleiste
    sichtbar_js = "[...document.querySelectorAll('[role=tab][id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))"
    for w in (1440, 390):
        v = br.new_page(viewport={'width': w, 'height': 844}, is_mobile=w < 500); v.on('pageerror', lambda x: errs.append(str(x)))
        login(v, 'admin', 'Sicheres-Passwort-1')
        v.route('**/api/?action=status*', verwaltung)
        v.goto(B + '/admin/?ansicht=importe&nur=import'); v.wait_for_selector('#view-importe:not([hidden])')
        v.wait_for_function("document.title.startsWith('Import')")
        check(f'{w}px Kachel „Import“: nur die Importzentrale (keine Nutzer, Protokoll, Sicherheit, Schutz), ohne Seitenleiste, Titel „Import“',
              v.evaluate(sichtbar_js) == ['importe'] and v.is_hidden('.side-nav') and v.text_content('#topbar h1') == 'Import'
              and v.is_hidden('#btn-publish'), (v.evaluate(sichtbar_js), v.title()))
        check(f'{w}px Kachel „Import“: kein waagerechtes Scrollen, Kopfzeile ohne Überlappung', v.evaluate('document.documentElement.scrollWidth') <= w and not v.evaluate(overlap_js))
        v.screenshot(path=SH + f'/import-bereich-{w}.png', full_page=True)
        v.evaluate("location.hash = 'users'"); v.wait_for_function("location.hash === '#users'")
        check(f'{w}px … #users in der Adresse öffnet keine Nutzerverwaltung', v.is_hidden('#view-users') and v.is_visible('#view-importe'))
        v.goto(B + '/admin/'); v.wait_for_function("!document.querySelector('#vt-users').hidden")
        check(f'{w}px Kachel „Verwaltung“: alle Verwaltungsbereiche mit Seitenleiste', {'importe', 'users', 'log'} <= set(v.evaluate(sichtbar_js)) and not {'schutz', 'sec'} & set(v.evaluate(sichtbar_js))
              and v.is_visible('.side-nav') and v.text_content('#topbar h1') == 'Verwaltung', v.evaluate(sichtbar_js))
        v.close()
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
