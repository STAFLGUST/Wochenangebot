"""Angebotsliste (Standardansicht der Angebotsseite): Aufbau wie die gedruckte Liste – Abschnitte, Gruppen in Spalten,
Nr. · Bezeichnung · € / Kg. Tabelle und Karten bleiben über die Auswahl erreichbar (auch per Link)."""
import re as _re
import sys
from playwright.sync_api import sync_playwright
from umgebung import BASE as B, SH, storage_raw, storage_write

res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    pg = br.new_page(viewport={'width': 1440, 'height': 1000}); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_selector('.al tr.row')
    check('default view is the offer list', pg.is_visible('.al') and pg.get_attribute('.seg [data-view=liste]', 'aria-pressed') == 'true' and not pg.is_visible('table.grid'))
    check('title like the printed list', 'Freibleibendes Angebot für die KW 43 - 2026' in pg.inner_text('.al-head'))
    check('sections as headings', pg.locator('.al-st').count() == 4 and 'Eigene Zerlegung' in pg.locator('.al-st').first.inner_text(), pg.locator('.al-st').count())
    check('one block per group, every article exactly once', pg.locator('.al-grp').count() >= 30 and pg.locator('.al tr.row').count() == 276
          and len(set(pg.eval_on_selector_all('.al tr.row', 'rs => rs.map(r => r.dataset.id)'))) == 276, (pg.locator('.al-grp').count(), pg.locator('.al tr.row').count()))
    check('group header with € / kg over the price column and a rule', '€ / kg' in pg.locator('.al-h .al-eh').first.inner_text()
          and pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.al-h th')).borderBottomWidth)") >= 1)
    check('brand in quotes highlighted', pg.locator('.al-h .al-brand').first.inner_text() == '„Fleischmeister“')
    row = pg.locator('.al tr.row').first
    check('row: number, name, price without unit', row.locator('.c-code').inner_text() == '10601' and 'Roastbeef' in row.locator('.c-name').inner_text() and row.locator('.c-price').inner_text() == '25,54',
          row.inner_text())
    check('price on request shown as a. Anfr.', pg.locator('.al .c-price', has_text='a. Anfr.').count() >= 4)
    krone = pg.locator('.al tr.row', has_text='30090')
    check('labelled price lands in its column (Schiffsware)', krone.locator('.c-price').nth(0).inner_text() == '' and krone.locator('.c-price').nth(1).inner_text() == 'a. Anfr.', krone.inner_text())
    check('several price columns get their labels (e.g. Flugware/Schiffsware)', pg.locator('.al-sub').count() >= 1 and pg.locator('.al-sub th').filter(has_text='Flugware').count() >= 1)
    check('striped rows', pg.evaluate("getComputedStyle(document.querySelector('.al tbody tr:nth-child(1) td')).backgroundColor") != pg.evaluate("getComputedStyle(document.querySelector('.al tbody tr:nth-child(2) td')).backgroundColor"))
    check('three blocks side by side in every section', all(n == 3 for n in pg.eval_on_selector_all('.al-cols', 'cs => cs.map(c => c.querySelectorAll(":scope > .al-col").length)')))
    hs = pg.evaluate("[...document.querySelectorAll('.al-sec')[1].querySelectorAll('.al-col')].map(c => c.getBoundingClientRect().height)")
    check('columns balanced (similar height)', max(hs) - min(hs) <= max(hs) * 0.25, [round(h) for h in hs])
    xs = pg.evaluate("[...document.querySelectorAll('.al-sec:first-of-type tr.row td.c-price:last-of-type')].map(td => Math.round(td.getBoundingClientRect().right))")
    check('prices right-aligned on one edge per block', len(set(xs)) == 3, sorted(set(xs)))
    codes = pg.evaluate("[...document.querySelectorAll('.al-sec:first-of-type tr.row td.c-code')].map(td => Math.round(td.getBoundingClientRect().left))")
    check('numbers left-aligned on one edge per block', len(set(codes)) == 3, sorted(set(codes)))
    pg.screenshot(path=SH + '/angebotsliste.png')
    pg.screenshot(path=SH + '/angebotsliste-ganz.png', full_page=True)
    # Bedienung bleibt: Details, Merkliste
    row.locator('.name-btn').click(); pg.wait_for_selector('#dlg-detail[open]')
    check('name opens the detail view', 'Roastbeef' in pg.inner_text('#detail-body'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-detail', state='hidden')
    row.hover(); row.locator('.star').click()
    check('star adds to the watch list', pg.inner_text('#fav-count') == '1' and row.locator('.star').get_attribute('aria-pressed') == 'true')
    # Suche filtert, Gruppen ohne Treffer verschwinden
    pg.fill('#q', 'Entrecote'); pg.wait_for_function("document.querySelectorAll('.al tr.row').length < 50")
    n = pg.locator('.al tr.row').count()
    check('search filters rows and empty groups disappear', 0 < n < 50 and pg.locator('.al-grp').count() <= n and all('ntrecote' in t for t in pg.locator('.al .c-name').all_inner_texts()), n)
    pg.fill('#q', ''); pg.wait_for_function("document.querySelectorAll('.al tr.row').length === 276")
    pg.select_option('#sort', 'price-asc'); pg.wait_for_selector('.al-h:has-text("sortiert nach Preis")')
    check('other sort order: one sorted list over three blocks', pg.locator('.al-grp').count() == 3 and pg.locator('.al-cont').count() == 2 and pg.locator('.al tr.row').count() == 276)
    pg.select_option('#sort', 'offer-asc'); pg.wait_for_selector('.al-st')
    # Tabelle und Karten über die Auswahl, per Link wiederherstellbar
    pg.click('.seg [data-view=table]'); pg.wait_for_selector('table.grid')
    check('table view still available', pg.is_visible('table.grid thead') and not pg.is_visible('.al') and 'ansicht=tabelle' in pg.url)
    p2 = br.new_page(viewport={'width': 1440, 'height': 900}); p2.goto(pg.url); p2.wait_for_selector('table.grid tr.row')
    check('link keeps the table view', p2.get_attribute('.seg [data-view=table]', 'aria-pressed') == 'true'); p2.close()
    pg.click('.seg [data-view=cards]'); pg.wait_for_selector('.card')
    check('card view still available', 'ansicht=karten' in pg.url)
    pg.click('.seg [data-view=liste]'); pg.wait_for_selector('.al')
    check('back to the offer list, no view parameter', 'ansicht' not in pg.url)
    p3 = br.new_page(viewport={'width': 1440, 'height': 900}); p3.goto(B + '/#ansicht=karten'); p3.wait_for_selector('.card')
    check('old card links keep working', p3.is_visible('.card')); p3.close()
    # Breiten
    t = br.new_page(viewport={'width': 1024, 'height': 900}); t.goto(B + '/'); t.wait_for_selector('.al tr.row')
    check('1024 px: still three blocks side by side', t.locator('.al').get_attribute('data-k') == '3' and t.locator('.al-sec').first.locator('.al-col').count() == 3)
    t.screenshot(path=SH + '/angebotsliste-1024.png'); t.close()
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); m.on('pageerror', lambda e: errs.append(str(e)))
    m.goto(B + '/'); m.wait_for_selector('.al tr.row')
    check('mobile: one column, no horizontal scroll', m.locator('.al-sec').first.locator('.al-col').count() == 1 and m.evaluate('document.documentElement.scrollWidth') <= 390, m.evaluate('document.documentElement.scrollWidth'))
    m.evaluate("window.scrollTo(0, document.querySelector('.al').getBoundingClientRect().top + scrollY - 70)")
    m.screenshot(path=SH + '/angebotsliste-390.png')
    d = br.new_page(viewport={'width': 1440, 'height': 1000}, color_scheme='dark'); d.goto(B + '/'); d.wait_for_selector('.al tr.row')
    d.screenshot(path=SH + '/angebotsliste-dunkel.png'); d.close()
    # Export: Angebotsliste A4 quer als Standard
    e = br.new_page(viewport={'width': 1440, 'height': 900}); e.on('pageerror', lambda x: errs.append(str(x)))
    e.goto(B + '/'); e.wait_for_selector('.al tr.row')
    e.click('#btn-print'); e.wait_for_selector('#dlg-print[open]')
    check('export: offer list (A4 landscape) is the default layout', e.is_checked('#dlg-print input[name=layout][value=liste]'))
    e.click('#dlg-print [data-close]')
    e.evaluate("window.dispatchEvent(new Event('beforeprint'))")   # wie Strg+P: Standard-Layout
    pages = e.locator('#print-root .pl-page').count()
    check('export: a page per section at least, three blocks per page', pages >= 4 and all(n == 3 for n in e.eval_on_selector_all('#print-root .al-cols', 'cs => cs.map(c => c.children.length)')), pages)
    check('export: every article once', e.locator('#print-root tr.row').count() == 276 and e.locator('#print-root .star, #print-root .qty').count() == 0)
    e.emulate_media(media='print')
    pdf = e.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/angebotsliste-export.pdf', 'wb').write(pdf)
    boxes = [tuple(float(v) for v in m_.groups()) for m_ in _re.finditer(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)', pdf)]
    check('export PDF is landscape', boxes and all(w > h for w, h in boxes), boxes[:2])
    check('export fits: one PDF page per laid-out page', len(boxes) == pages, (len(boxes), pages))
    e.close()
    # Erweiterbar: sehr viele Artikel in einem Abschnitt – Druck verteilt über mehrere Seiten, nichts läuft über
    import json as _json
    raw = storage_raw('angebot'); doc = _json.loads(raw[raw.index('{'):])
    extra = []
    for n in range(1, 7):
        for it in [i for i in doc['items'] if i['groupId'] == 'g1']:
            extra.append(dict(it, id=f"{it['id']}x{n}", code=str(int(it['code']) + 1000 * n) if it.get('code') else None, name=it['name'] + f' Zuschnitt {n}'))
    pos = max(k for k, i in enumerate(doc['items']) if i['groupId'] == 'g1') + 1
    doc['items'][pos:pos] = extra
    storage_write('angebot', doc)
    total = 276 + len(extra)
    x = br.new_page(viewport={'width': 1440, 'height': 900}); x.on('pageerror', lambda q: errs.append(str(q)))
    x.goto(B + '/?r=gross'); x.wait_for_selector('.al tr.row')
    check('large offer on screen: every article once, three blocks', x.locator('.al tr.row').count() == total and x.locator('.al-sec').first.locator('.al-col').count() == 3, x.locator('.al tr.row').count())
    hs = x.evaluate("[...document.querySelectorAll('.al-sec')[0].querySelectorAll('.al-col')].map(c => c.getBoundingClientRect().height)")
    check('large offer: big group split, columns balanced', x.locator('.al-sec').first.locator('.al-cont').count() >= 1 and max(hs) - min(hs) <= max(hs) * 0.15, [round(h) for h in hs])
    x.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pages = x.locator('#print-root .pl-page').count()
    check('large offer export: section continues on further pages', pages >= 6 and x.locator('#print-root tr.row').count() == total and x.locator('#print-root .al-st .al-cont').count() >= 1, pages)
    x.emulate_media(media='print')
    pdf = x.pdf(prefer_css_page_size=True, print_background=True)
    n_pdf = len(_re.findall(rb'/Type\s*/Page[^s]', pdf))
    check('large offer export: nothing overflows (PDF pages = laid-out pages)', n_pdf == pages, (n_pdf, pages))
    x.close()
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
