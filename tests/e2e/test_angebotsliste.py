"""Angebotsliste (Standardansicht der Angebotsseite): Aufbau wie die gedruckte Liste – Abschnitte, Gruppen in Spalten,
Nr. · Bezeichnung · € / Kg. Tabelle und Karten bleiben über die Auswahl erreichbar (auch per Link)."""
import sys
from playwright.sync_api import sync_playwright
from umgebung import BASE as B, SH

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
    check('one block per group, all articles listed', pg.locator('.al-grp').count() >= 30 and pg.locator('.al tr.row').count() == 276, (pg.locator('.al-grp').count(), pg.locator('.al tr.row').count()))
    check('group header with € / Kg and double rule', '€ / Kg' in pg.locator('.al-h').first.inner_text()
          and 'double' in pg.evaluate("getComputedStyle(document.querySelector('.al-h th')).borderBottomStyle"))
    check('brand in quotes highlighted', pg.locator('.al-h .al-brand').first.inner_text() == '„Fleischmeister“')
    row = pg.locator('.al tr.row').first
    check('row: number, name, price without unit', row.locator('.c-code').inner_text() == '10601' and 'Roastbeef' in row.locator('.c-name').inner_text() and row.locator('.c-price').inner_text() == '25,54',
          row.inner_text())
    check('price on request shown as a. Anfr.', pg.locator('.al .c-price', has_text='a. Anfr.').count() >= 4)
    krone = pg.locator('.al tr.row', has_text='30090')
    check('labelled price lands in its column (Schiffsware)', krone.locator('.c-price').nth(0).inner_text() == '' and krone.locator('.c-price').nth(1).inner_text() == 'a. Anfr.', krone.inner_text())
    check('several price columns get their labels (e.g. Flugware/Schiffsware)', pg.locator('.al-sub').count() >= 1 and pg.locator('.al-sub th').filter(has_text='Flugware').count() >= 1)
    check('striped rows', pg.evaluate("getComputedStyle(document.querySelector('.al tbody tr:nth-child(1) td')).backgroundColor") != pg.evaluate("getComputedStyle(document.querySelector('.al tbody tr:nth-child(2) td')).backgroundColor"))
    cols = pg.evaluate("[...document.querySelectorAll('.al-sec:first-of-type .al-grp')].map(g => Math.round(g.getBoundingClientRect().left))")
    check('groups arranged in three columns on desktop', len(set(cols)) == 3, sorted(set(cols)))
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
    pg.select_option('#sort', 'price-asc'); pg.wait_for_selector('.al-flow')
    check('other sort order: one sorted list', pg.locator('.al-grp').count() == 1 and 'sortiert nach Preis' in pg.inner_text('.al-h'))
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
    pg.set_viewport_size({'width': 1024, 'height': 900}); pg.wait_for_timeout(200)
    cols = pg.evaluate("[...document.querySelectorAll('.al-sec:first-of-type .al-grp')].map(g => Math.round(g.getBoundingClientRect().left))")
    check('1024 px: two columns', len(set(cols)) == 2, sorted(set(cols)))
    pg.screenshot(path=SH + '/angebotsliste-1024.png')
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True); m.on('pageerror', lambda e: errs.append(str(e)))
    m.goto(B + '/'); m.wait_for_selector('.al tr.row')
    cols = m.evaluate("[...document.querySelectorAll('.al-sec:first-of-type .al-grp')].map(g => Math.round(g.getBoundingClientRect().left))")
    check('mobile: one column, no horizontal scroll', len(set(cols)) == 1 and m.evaluate('document.documentElement.scrollWidth') <= 390, (sorted(set(cols)), m.evaluate('document.documentElement.scrollWidth')))
    m.evaluate("window.scrollTo(0, document.querySelector('.al').getBoundingClientRect().top + scrollY - 70)")
    m.screenshot(path=SH + '/angebotsliste-390.png')
    d = br.new_page(viewport={'width': 1440, 'height': 1000}, color_scheme='dark'); d.goto(B + '/'); d.wait_for_selector('.al tr.row')
    d.screenshot(path=SH + '/angebotsliste-dunkel.png'); d.close()
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
