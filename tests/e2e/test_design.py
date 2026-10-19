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
    check('brand mark shows company initials', d.inner_text('.brand-mark') == 'SF', d.inner_text('.brand-mark'))
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

    check('no requests to other servers', not ext, ext[:3])
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
