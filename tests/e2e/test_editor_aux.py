"""Testgruppe editor_aux: Hilfen im Angebotseditor – Vergleich mit der Vorwoche und Bestand im Editor."""
import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
from testdaten import de, preis, preise, artikel, bestand_kg
SC = FIX
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

master = [a for a in json.load(open(SC + '/bestand/master_stock.json')) if a[2] and a[2] > 0]
raw = open(SC + '/data-seed/angebot.php', encoding='utf-8').read(); offer = json.loads(raw[raw.index('\n') + 1:])
norm = lambda c: (str(c).lstrip('0') or '0') if str(c).isdigit() else str(c).upper()
priced = {norm(i['code']) for i in offer['items'] if i['code'] and i['price']['status'] in ('value', 'request')}
in_offer_none = {norm(i['code']) for i in offer['items'] if i['code']} - priced
exp_np = [a for a in master if norm(a[0]) not in priced]
articles = [{'code': a[0].lstrip('0') or '0', 'name': a[1], 'kg': a[2], 'mhd': a[3], 'mhdKg': a[4], 'lots': []} for a in master]

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify(b)}); return [r.status, await r.json()]; }""", [action, body])

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    check('no stock/prev columns without data', not a.locator('tr[data-id] td.e-stock').first.is_visible() and not a.locator('tr[data-id] td.e-prev').first.is_visible())
    gn = {g['id']: g['name'] for g in offer['groups']}
    hist = []
    for it in offer['items']:
        pr = dict(it['price'])
        if it['code'] == '10601' and pr['status'] == 'value': pr['value'] = round(pr['value'] - 0.4, 2)
        hist.append({'code': it['code'], 'name': it['name'], 'group': gn[it['groupId']], 'category': it['category'], 'price': pr})
    r = post(a, 'history_import', {'week': 42, 'year': 2026, 'source': 'test', 'items': hist}); check('history KW42 stored', r[0] == 200, r[0])
    r = post(a, 'stock_import', {'date': '2026-10-16', 'source': 'Bestand_16.10.26.XLS', 'articles': articles}); check('stock stored', r[0] == 200, r[1] if r[0] != 200 else '')
    a.reload(); a.wait_for_selector('tr[data-id]')
    a.wait_for_function("document.querySelector('#groups:not(.no-stock):not(.no-prev)') && document.querySelector('#noprice-panel:not([hidden])')", timeout=10000)
    th = a.locator('.gcard').first.locator('thead').inner_text()
    check('headers: Vorwoche KW 42/26, Preis KW 43, Bestand', 'Vorwoche' in th and 'KW 42/26' in th and 'KW 43' in th and 'Bestand' in th and 'Stand 16.10.26' in th, re.sub(r'\s+', ' ', th))
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('10601 Vorwoche (Preis − 0,40) with +0,40', row.locator('td.e-prev').inner_text().replace('\n', ' ') == de(round(preis('10601') - 0.4, 2)) + ' +0,40', row.locator('td.e-prev').inner_text())
    check('10601 Bestand aus Bestandsliste', row.locator('td.e-stock').inner_text().strip() == de(bestand_kg('10601')), row.locator('td.e-stock').inner_text())
    order = row.locator('td').evaluate_all("tds => tds.map(t => t.className.split(' ')[0])")
    check('column order prev → price → stock', order.index('e-prev') + 1 == order.index('e-price') and order.index('e-price') + 1 == order.index('e-stock'), order)
    nost = a.locator('tr[data-id] td.e-stock.none').count(); check('articles without stock show —', nost > 0, nost)
    badge = a.inner_text('#noprice-panel .np-badge'); check('panel count = stock without price', badge == str(len(exp_np)), (badge, len(exp_np)))
    check('Leisten beim Öffnen zugeklappt', a.locator('#noprice-panel .np-card:not(.open)').count() == 1 and a.locator('#mhd-panel .np-card:not(.open)').count() == 1
          and a.locator('#noprice-panel .nptab').count() == 0)
    a.click('#noprice-panel [data-np=toggle]'); a.wait_for_selector('#noprice-panel .np-card.open .nptab')
    check('panel rows', a.locator('#noprice-panel .nptab tbody tr').count() == len(exp_np))
    a.screenshot(path=SH + '/editor-aux.png')
    # Suche filtert Panel mit
    a.fill('#ed-q', 'Roastbeef'); a.wait_for_timeout(500)
    names = a.locator('#noprice-panel .nptab tbody td.np-name').all_inner_texts()
    check('editor search filters panel', all('roastbeef' in n.lower() for n in names), names[:5])
    a.fill('#ed-q', ''); a.wait_for_timeout(500)
    # Ins Angebot übernehmen
    first = a.locator('#noprice-panel .nptab tbody tr:has([data-np=add])').first
    code = first.get_attribute('data-npcode'); name = first.locator('td.np-name').inner_text()
    first.locator('[data-np=add]').click(); a.wait_for_selector(f'#dlg-ez-pick[open] #ezp-list [data-preis="{code}"]')
    check('„Ins Angebot“ öffnet „Artikel hinzufügen“ mit dem Artikel markiert', a.is_checked(f'#ezp-list [data-sel="{code}"]') and a.input_value('#ezp-q') == code)
    a.fill(f'#ezp-list [data-preis="{code}"]', '9,99x'); a.click('#ezp-ok'); a.wait_for_selector('#ezp-anz .ezp-err')
    check('invalid price rejected', 'nicht lesbar' in a.inner_text('#ezp-anz'))
    a.fill(f'#ezp-list [data-preis="{code}"]', '9,99'); a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); a.wait_for_timeout(1200)
    new = a.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])')
    check('article added with price + stock', new.count() == 1 and new.locator('input[data-f=price]').input_value() == '9,99' and new.locator('td.e-stock').inner_text().strip() != '—', code)
    check('panel count decreased', a.inner_text('#noprice-panel .np-badge') == str(len(exp_np) - 1))
    exp = re.sub(r'[\s,]*\bfrisch\b\.?[\s,.]*$', '', name, flags=re.I).strip() or name
    check('name taken from stock list (without frisch)', new.locator('input[data-f=name]').input_value() == exp, (new.locator('input[data-f=name]').input_value(), exp))
    # Preis für Artikel im Angebot ohne Preis
    goto = a.locator('#noprice-panel .nptab [data-np=goto]')
    if goto.count():
        goto.first.click(); a.wait_for_timeout(600)
        check('"Preis eintragen" focuses price field', a.evaluate("document.activeElement && document.activeElement.dataset.f === 'price'"))
    else:
        check('no in-offer-without-price articles (n/a)', not (in_offer_none & {norm(x[0]) for x in master}))
    # Preis auf Vorwochenpreis → Differenz verschwindet
    pi = row.locator('input[data-f=price]'); pi.fill(de(round(preis('10601') - 0.4, 2))); pi.press('Tab'); a.wait_for_timeout(800)
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('delta disappears when equal to Vorwoche', row.locator('td.e-prev').inner_text().strip() == de(round(preis('10601') - 0.4, 2)))
    # Woche ändern → Vorwoche neu
    a.fill('#m-week', '42'); a.press('#m-week', 'Tab'); a.wait_for_timeout(1200)
    check('week change reloads Vorwoche (none before KW42 → column hidden)', not a.locator('tr[data-id] td.e-prev').first.is_visible())
    a.fill('#m-week', '43'); a.press('#m-week', 'Tab'); a.wait_for_timeout(1200)
    check('back to KW 43 shows Vorwoche again', a.locator('tr[data-id] td.e-prev').first.is_visible())
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_selector('#noprice-panel:not([hidden])'); m.wait_for_timeout(300)
    m.screenshot(path=SH + '/editor-aux-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
