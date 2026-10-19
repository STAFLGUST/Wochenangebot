import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import re, json, os, sys
from playwright.sync_api import sync_playwright, expect
URL = BASE + '/#ansicht=tabelle'   # prüft die Tabellenansicht (Standard ist die Angebotsliste, eigener Test)
from umgebung import SH as OUT, FIX, REPO
from testdaten import de, preis, preise, artikel, bestand_kg
results = []
def check(name, cond, info=''):
    results.append((name, bool(cond), info)); print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(info)) if info else ''))

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1440, 'height': 960}, accept_downloads=True)
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL); pg.wait_for_selector('tr.row')
    rows = lambda: pg.locator('tr.row').count()

    check('load: 276 rows', rows() == 276, rows())
    check('KW pill', pg.inner_text('#kw-pill').strip() == 'KW 43 · 2026', pg.inner_text('#kw-pill'))
    check('validity text', 'Mo 19.10. – So 25.10.2026' in pg.inner_text('#subbar'), pg.inner_text('#subbar'))
    check('KPI bar removed', pg.locator('#kpis, .kpi').count() == 0)
    check('price format (10601 first row)', de(preis('10601')) in pg.inner_text('tr.row >> nth=0'))

    # search
    pg.fill('#q', 'Filet Argentinien'); pg.wait_for_timeout(100)
    names = pg.locator('tr.row .name-btn').all_inner_texts()
    origins = pg.locator('tr.row td.c-origin').all_inner_texts()
    check('search "Filet Argentinien" = 4', rows() == 4 and all('filet' in n.lower() for n in names) and all('Argentinien' in o for o in origins), list(zip(names, origins)))
    check('hits text', '4 von 276' in pg.inner_text('#hits'), pg.inner_text('#hits'))
    check('highlight marks', pg.locator('tr.row mark').count() >= 4)
    pg.fill('#q', 'gefroren entrecote'); pg.wait_for_timeout(80)
    t = pg.locator('tr.row .name-btn').all_inner_texts()
    check('search "gefroren entrecote"', rows() >= 2 and all('entrecote' in x.lower() for x in t), t)
    pg.fill('#q', '10601'); check('search by Art.-Nr.', rows() == 1)
    pg.fill('#q', 'fleischmeister'); check('search brand', rows() == 73, rows())
    pg.fill('#q', 'hufte'); check('search umlaut-insensitive (hufte)', rows() > 5, rows())
    pg.fill('#q', 'xyzqq'); pg.wait_for_timeout(80)
    check('empty state', pg.locator('.empty h3').inner_text() == 'Keine Artikel gefunden')
    pg.click('[data-act="clear-q"]'); check('clear search from empty state', rows() == 276)

    # filters (Desktop: Aufklappmenüs in der Filterleiste)
    def drop(fd):
        if not pg.locator(f'.fdrop[data-fd="{fd}"]').evaluate('d => d.open'): pg.click(f'.fdrop[data-fd="{fd}"] summary')
    check('filter groups closed by default (desktop)', pg.locator('.fdrop[open]').count() == 0 and pg.locator('.fdrop').count() == 6)
    drop('cat')
    pg.click('#filters-body label.opt:has-text("Kalb")'); pg.wait_for_timeout(80)
    check('filter Kalb = 24', rows() == 24, rows())
    check('dropdown label shows choice', pg.inner_text('.fdrop[data-fd="cat"] .fd-val') == 'Kalb' and 'on' in pg.get_attribute('.fdrop[data-fd="cat"]', 'class'))
    drop('cond')
    check('only one dropdown open', pg.locator('.fdrop[open]').count() == 1)
    pg.click('#filters-body fieldset[data-facet="cond"] label.opt:has-text("Frisch / gefroren")')
    check('Kalb + frisch/gefroren = 1', rows() == 1, rows())
    pg.keyboard.press('Escape'); check('Escape closes dropdown', pg.locator('.fdrop[open]').count() == 0)
    check('chips shown', pg.locator('#chips .chip').count() == 2)
    pg.click('#btn-reset'); check('reset', rows() == 276)
    drop('pstat'); pg.click('#filters-body fieldset[data-facet="pstat"] label.opt:has-text("Auf Anfrage")'); check('Preisangabe auf Anfrage = 4', rows() == 4, rows())
    pg.click('#btn-reset')
    drop('price'); pg.fill('#pmin', '10'); pg.fill('#pmax', '12,5'); pg.wait_for_timeout(400)
    vals = [float(x.replace('.', '').replace(',', '.')) for x in pg.locator('tr.row .pv').all_inner_texts()]
    check('price range 10–12,5', rows() > 0 and all(10 <= v <= 12.5 for v in vals[:rows()]), (rows(), min(vals), max(vals)))
    check('price dropdown shows range', '10' in pg.inner_text('.fdrop[data-fd="price"] .fd-val'), pg.inner_text('.fdrop[data-fd="price"] summary'))
    pg.click('#btn-reset')
    check('click outside closes dropdown', pg.locator('.fdrop[open]').count() == 0)
    drop('feat'); pg.click('#filters-body .pill:has-text("Grain Fed")'); check('Merkmal Grain Fed = 19 (17 + 2 ex chilled)', rows() == 19, rows())
    pg.click('#btn-reset')
    pg.click('.qn[data-cat="Geflügel"]'); check('quicknav Geflügel', rows() == 10, rows())
    pg.click('.qn[data-cat="Geflügel"]'); check('quicknav toggle off', rows() == 276)

    # sorting
    pg.select_option('#sort', 'price-asc'); pg.wait_for_timeout(80)
    pv = [float(x.replace(',', '.')) for x in pg.locator('tr.row .pv').all_inner_texts()]
    check('sort price asc', pv == sorted(pv[:len(pv)]) and pv[0] == min(preise()), pv[:4])
    check('flat mode shows group line', pg.locator('tr.row td.c-origin .sub').count() == 276)
    pg.click('th.c-price button'); pv = [float(x.replace(',', '.')) for x in pg.locator('tr.row .pv').all_inner_texts()]
    check('header click → price desc', pv[0] == max(preise()), pv[:3])
    pg.click('th.c-code button'); codes = [c for c in pg.locator('tr.row td.c-code').all_inner_texts() if c.strip() != '—']
    check('sort code asc', codes == sorted(codes, key=int), codes[:3])
    pg.select_option('#sort', 'offer-asc')

    # cards
    pg.click('.seg button[data-view="cards"]'); pg.wait_for_timeout(100)
    check('cards view', pg.locator('article.card').count() == 276)
    pg.fill('#q', 'lamm lachs'); pg.wait_for_timeout(100)
    pg.screenshot(path=f'{OUT}/cards.png')
    pg.fill('#q', ''); pg.click('.seg button[data-view="table"]')

    # favourites
    for i in range(3): pg.locator('tr.row .star').nth(i * 5).click()
    check('fav count 3', pg.inner_text('#fav-count') == '3')
    check('Merkliste column lists favourites', pg.locator('#merk li').count() == 3 and '3 Artikel' in pg.inner_text('#merk .merk-h'))
    pg.reload(); pg.wait_for_selector('tr.row')
    check('favs persisted after reload', pg.inner_text('#fav-count') == '3')
    pg.click('#tab-fav'); check('fav tab rows', rows() == 3, rows())
    with pg.expect_download() as d: pg.click('[data-act="fav-csv"]')
    dl = d.value; path = dl.path(); csv = open(path, encoding='utf-8-sig').read().splitlines()
    check('fav CSV', len(csv) == 4 and csv[0].startswith('Artikelnummer;Bezeichnung') and dl.suggested_filename == 'Wochenangebot_KW43_2026_Merkliste.csv', (dl.suggested_filename, csv[1]))
    pg.click('#tab-all')

    # CSV all
    pg.click('#btn-more')
    with pg.expect_download() as d: pg.click('[data-action="csv-all"]')
    raw = open(d.value.path(), encoding='utf-8').read()
    lines = raw.lstrip('﻿').splitlines()
    check('CSV all: BOM + 277 lines + decimal comma', raw.startswith('﻿') and len(lines) == 277 and ';' + de(preis('10601')) + ';' in raw, len(lines))
    lamb = [l for l in lines if l.startswith('30028;')][0]
    check('CSV lamb alt price', 'Flugware: ' + de(artikel('30028')['altPrices'][0]['value']) + ' €/kg' in lamb and 'Schiffsware: Mit Preis' in lamb, lamb)

    # detail
    pg.fill('#q', '10919'); pg.click('tr.row .name-btn')
    expect(pg.locator('#dlg-detail')).to_be_visible()
    check('detail title', pg.inner_text('#d-title') == 'Filet 4/5 lbs., frisch')
    check('detail compare list', pg.locator('#dlg-detail .cmp li').count() >= 10, pg.locator('#dlg-detail .cmp li').count())
    pg.screenshot(path=f'{OUT}/detail.png')
    pg.click('#dlg-detail [data-fav-detail]'); check('detail fav toggles', pg.inner_text('#fav-count') == '4')
    pg.click('#dlg-detail [data-cmp]'); expect(pg.locator('#dlg-compare')).to_be_visible()
    check('compare from detail = Rind/Filet', pg.locator('#cmp-cut').input_value() == 'Filet')
    pg.select_option('#cmp-cat', 'Lamm & Schaf'); pg.wait_for_timeout(80)
    check('compare cat switch', pg.locator('#dlg-compare .cmp li').count() >= 2, pg.locator('#cmp-cut').input_value())
    pg.screenshot(path=f'{OUT}/compare.png')
    pg.keyboard.press('Escape'); pg.fill('#q', '')

    # duplicate code notice
    pg.fill('#q', '11598'); check('dup code both rows', rows() == 2)
    pg.locator('tr.row .name-btn').first.click()
    check('dup notice in detail', 'steht 2× in der Liste' in pg.inner_text('#dlg-detail'))
    pg.keyboard.press('Escape'); pg.fill('#q', '')

    # url state
    pg.fill('#q', 'roastbeef'); drop('origin'); pg.click('#filters-body label.opt:has-text("Uruguay")'); pg.select_option('#sort', 'price-desc'); pg.wait_for_timeout(100)
    h = pg.evaluate('location.hash'); n = rows()
    p2 = ctx.new_page(); p2.goto(BASE + '/' + h); p2.wait_for_selector('tr.row')
    check('shared link restores state', p2.locator('tr.row').count() == n and p2.input_value('#q') == 'roastbeef' and p2.input_value('#sort') == 'price-desc', (h, n))
    p2.close()
    pg.click('#btn-more'); pg.click('[data-action="copy-link-state"]'); pg.wait_for_timeout(200)
    check('copy link toast', 'kopiert' in pg.inner_text('#toast') or 'Kopieren nicht' in pg.inner_text('#toast'), pg.inner_text('#toast'))
    pg.evaluate("location.hash='ansicht=tabelle'"); pg.wait_for_timeout(150)
    check('hash cleared → full list', rows() == 276, rows())

    # print
    pg.evaluate('() => { window.print = () => { window.__printed = (window.__printed||0) + 1; }; }')
    pg.click('#btn-print'); expect(pg.locator('#dlg-print')).to_be_visible()
    pg.screenshot(path=f'{OUT}/print-dialog.png')
    pg.check('input[name="scope"][value="all"]'); pg.click('#print-go'); pg.wait_for_timeout(200)
    check('print called', pg.evaluate('window.__printed') == 1)
    check('print root: 276 rows', pg.locator('#print-root .p-row').count() == 276, pg.locator('#print-root .p-row').count())
    check('print root: 32 groups, 4 sections', pg.locator('#print-root .p-group').count() == 32 and pg.locator('#print-root .p-section').count() == 4)
    pg.emulate_media(media='print'); pg.pdf(path=f'{OUT}/print-all.pdf', format='A4', prefer_css_page_size=True); pg.emulate_media(media='screen')
    pg.click('#tab-fav'); pg.click('#btn-print'); pg.check('input[name="layout"][value="table"]'); pg.click('#print-go'); pg.wait_for_timeout(150)
    check('print fav table', pg.locator('#print-root .p-table tbody tr:not(.gr):not(.sr)').count() == 4)
    pg.emulate_media(media='print'); pg.pdf(path=f'{OUT}/print-fav.pdf', format='A4', prefer_css_page_size=True); pg.emulate_media(media='screen')
    pg.click('#tab-all')

    # keyboard
    pg.keyboard.press('/'); check('"/" focuses search', pg.evaluate('document.activeElement.id') == 'q')
    pg.keyboard.press('Escape')

    # dark mode
    pg.click('#btn-theme'); check('dark mode on', pg.evaluate('document.documentElement.dataset.theme') == 'dark')
    pg.screenshot(path=f'{OUT}/dark.png')
    pg.reload(); pg.wait_for_selector('tr.row'); check('dark persisted', pg.evaluate('document.documentElement.dataset.theme') == 'dark')
    pg.click('#btn-theme')

    check('no JS errors', not errs, errs)

    # mobile
    m = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    mp = m.new_page(); me = []; mp.on('pageerror', lambda e: me.append(str(e)))
    mp.goto(URL); mp.wait_for_selector('tr.row')
    mp.screenshot(path=f'{OUT}/mobile.png')
    sw = mp.evaluate('document.documentElement.scrollWidth')
    check('mobile no horizontal scroll', sw <= 390, sw)
    mp.click('#btn-filters-open'); mp.wait_for_timeout(300); mp.screenshot(path=f'{OUT}/mobile-filters.png')
    mp.click('#filters-body label.opt:has-text("Schwein")'); mp.click('#btn-filters-apply'); mp.wait_for_timeout(300)
    check('mobile filter works', mp.locator('tr.row').count() == 29)
    mp.locator('tr.row .name-btn').first.click(); mp.wait_for_timeout(300); mp.screenshot(path=f'{OUT}/mobile-detail.png')
    check('mobile no errors', not me, me)
    m.close()
    b.close()

fails = [r for r in results if not r[1]]
print(f'\n{len(results) - len(fails)}/{len(results)} passed')
sys.exit(0 if not fails else 1)
