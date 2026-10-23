"""Gestaltung „Klar“ der Angebotsseite: lokale Schriften (keine fremden Server), Kopf, Filterleiste mit Aufklappmenüs
(Desktop) bzw. Seitenleiste (schmal), Merkliste als Spalte ab 1280 px, hell/dunkel, kein seitliches Scrollen."""
import sys
import urllib.request
from playwright.sync_api import sync_playwright
from umgebung import BASE as B, SH, until

res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


for f in ['geist-latin-wght-normal.woff2', 'geist-latin-ext-wght-normal.woff2', 'geist-mono-latin-wght-normal.woff2']:
    r = urllib.request.urlopen(B + '/assets/fonts/' + f)
    body = r.read()
    check(f'font served locally: {f}', r.status == 200 and body[:4] == b'wOF2', (r.status, body[:4]))
css = urllib.request.urlopen(B + '/assets/app.css').read().decode()
check('no external font or stylesheet hosts', 'fonts.googleapis' not in css and 'fonts.gstatic' not in css and 'url("http' not in css)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, ext = [], []

    def page(w, h, scheme='light'):
        ctx = br.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('request', lambda r: ext.append(r.url) if not r.url.startswith(B) and not r.url.startswith('data:') else None)
        pg.goto(B + '/'); pg.wait_for_selector('tr.row')
        return pg

    d = page(1440, 950)
    check('Geist font used', 'Geist' in d.evaluate("getComputedStyle(document.body).fontFamily"))
    check('Geist actually loaded', until(lambda: d.evaluate("document.fonts.check('14px Geist')"), 5))
    check('logo in the header (loaded, links home)', d.evaluate("(() => { const i = document.querySelector('#topbar .brand-logo'); return !!i && i.complete && i.naturalWidth > 0 && i.closest('a').getAttribute('href') === './'; })()") and d.get_attribute('#topbar .brand-logo', 'alt') == 'Standard-Fleisch')
    check('filter bar: six closed dropdowns, no side column', d.locator('.fdrop').count() == 6 and d.locator('.fdrop[open]').count() == 0 and d.locator('#filters').evaluate("e => getComputedStyle(e).position") == 'static')
    check('offer view: full width, no side column', not d.is_visible('#merk'))
    d.click('#modebar [data-mode=liste]'); d.wait_for_selector('table.grid tr.row')
    check('Merkliste column visible ≥ 1280 px (list view)', d.is_visible('#merk') and 'Noch nichts gemerkt' in d.inner_text('#merk'))
    d.locator('tr.row .star').first.click()
    check('Merkliste column updates on star', d.locator('#merk li').count() == 1)
    d.click('#merk [data-merk=show]')
    check('column button switches to Merkliste tab', d.get_attribute('#tab-fav', 'aria-selected') == 'true')
    d.click('#merk [data-merk-open]'); d.wait_for_selector('#dlg-detail[open]')
    check('name in column opens details', d.locator('#dlg-detail[open]').count() == 1)
    d.keyboard.press('Escape')
    d.screenshot(path=SH + '/design-desktop.png')
    check('no horizontal scroll at 1440', d.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))

    m = page(1100, 900)
    check('Merkliste column hidden below 1280 px', not m.is_visible('#merk'))
    check('no horizontal scroll at 1100', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))

    s = page(390, 844)
    check('mobile: filter groups open in side panel', s.locator('.fdrop[open]').count() == 6)
    s.click('#btn-filters-open'); s.wait_for_selector('#filters.open')
    check('mobile: group headings visible, dropdown buttons hidden', s.is_visible('#filters-body fieldset[data-facet="cat"] legend') and not s.is_visible('.fdrop[data-fd="cat"] summary'))
    s.screenshot(path=SH + '/design-mobil-filter.png')
    s.click('#btn-filters-close')
    check('no horizontal scroll at 390', s.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    s.screenshot(path=SH + '/design-mobil.png')

    k = page(1440, 950, 'dark')
    bg = k.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dark mode uses dark ground', bg in ('rgb(14, 14, 13)',), bg)
    k.screenshot(path=SH + '/design-dunkel.png')

    # ── Darstellungsprüfung 10/2026: Tippflächen, Kontrast, abgeschnittener Platzhalter, Leerzustand ──
    # Tippflächen am Handy: alle sichtbaren Bedienelemente im Bild mindestens 36 × 36 px (Kontrollkästchen zählen über ihr Label)
    KLEIN = """() => [...document.querySelectorAll('button, a[href], input:not([type=checkbox]):not([type=radio]), select, summary')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.right > 0 && r.left < innerWidth && r.top < innerHeight && r.bottom > 0
        && getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden], .sr-only, .skip, label'); })
      .map(e => { const r = e.getBoundingClientRect(); return [(e.id || e.className || e.tagName) + ':' + (e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 24), Math.round(r.width), Math.round(r.height)]; })
      .filter(([, w, h]) => w < 36 || h < 36)"""
    KONTRAST = """(sels) => { const rgba = (s) => { const m = s.match(/[\\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
      const ueber = (o, u) => [0, 1, 2].map((i) => o[i] * o[3] + u[i] * (1 - o[3])).concat(1);
      const grund = (el) => { const s = []; for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c[3] > 0) s.push(c); if (c[3] >= 1) break; } return s.reverse().reduce((u, o) => ueber(o, u), [255, 255, 255, 1]); };
      const lum = (c) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
      return sels.map((s) => { const el = document.querySelector(s); if (!el) return [s, 0]; const g = grund(el), t = ueber(rgba(getComputedStyle(el).color), g), [h, d] = [lum(t), lum(g)].sort((x, y) => y - x);
        return [s, Math.round((h + .05) / (d + .05) * 100) / 100]; }); }"""
    for breite, schema in ((390, 'light'), (360, 'dark')):
        t = page(breite, 844, schema)
        t.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        klein = t.evaluate(KLEIN)
        check(f'{breite} px {schema}: Tippflächen im Bild mindestens 36 px (Chips, Reiter, Sterne, Artikelnamen, Logo)', not klein, klein[:6])
        t.click('#modebar [data-mode=liste]'); t.wait_for_selector('table.grid tr.row')
        klein = t.evaluate(KLEIN)
        check(f'{breite} px {schema}: Bestellansicht – Tippflächen mindestens 36 px (Sterne, Ansicht Tabelle/Karten, Kunden-Login)', not klein, klein[:6])
        t.click('#btn-kunde-login'); t.wait_for_selector('#dlg-kunde-login[open]')
        zu = t.evaluate("document.querySelector('#dlg-kunde-login [data-close].icon').offsetWidth")
        check(f'{breite} px: Schließen-Knopf im Anmeldefenster nicht zusammengedrückt (≥ 36 px)', zu >= 36, zu)
        t.keyboard.press('Escape')
        ph = t.evaluate("getComputedStyle(document.querySelector('#q')).textOverflow")
        check(f'{breite} px: langer Platzhalter im Suchfeld endet mit „…“', ph == 'ellipsis', ph)
        t.close()
    for schema in ('light', 'dark'):
        t = page(1280, 900, schema)
        werte = t.evaluate(KONTRAST, ['.al-st > span'])
        t.click('#modebar [data-mode=liste]'); t.wait_for_selector('table.grid tr.row .cond-unbekannt')
        werte += t.evaluate(KONTRAST, ['.g-row .g-meta', '.cond-unbekannt'])
        check(f'{schema}: kleine graue Zusätze (Artikelzahl, „Nicht angegeben“) mit Kontrast ≥ 4,5:1', all(w >= 4.5 for _, w in werte), werte)
        t.close()
    # Angebot ohne Artikel: eigener Hinweis statt „Prüfen Sie die Schreibweise …“ (Antwort nachgestellt, ohne Offline-Speicher)
    import json as _json
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, service_workers='block')
    t = ctx.new_page(); t.on('pageerror', lambda e: errs.append(str(e)))
    def _leer(route):
        r = route.fetch(); d = r.json(); d['offer']['items'] = []; route.fulfill(response=r, body=_json.dumps(d))
    t.route(lambda u: 'action=offer' in u, _leer)
    t.goto(B + '/'); t.wait_for_selector('#list .empty')
    txt = t.inner_text('#list .empty')
    check('leeres Angebot: Hinweis „Noch keine Artikel im Angebot“ ohne Such-/Filtertipp', 'Noch keine Artikel im Angebot' in txt and 'Schreibweise' not in txt, txt)
    t.fill('#q', 'Roastbeef'); t.wait_for_function("document.querySelector('#list .empty h3').textContent.includes('Noch keine')")
    check('leeres Angebot: auch mit Suchbegriff kein irreführender Tipp', 'Schreibweise' not in t.inner_text('#list .empty'))
    t.screenshot(path=SH + '/design-leer-390.png')
    ctx.close()
    s = page(390, 844)
    s.fill('#q', 'gibtesnichtxyz'); s.wait_for_selector('#list .empty h3')
    check('Suche ohne Treffer: weiter „Keine Artikel gefunden“', s.inner_text('#list .empty h3') == 'Keine Artikel gefunden')
    s.close()

    check('no requests to other servers', not ext, ext[:3])
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
