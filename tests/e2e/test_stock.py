import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, os, re, datetime
from decimal import Decimal, ROUND_HALF_UP
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
from testdaten import de, preis, preise, artikel, bestand_kg
SC = FIX + '/bestand'
XLS = SC + '/bestand.xls'
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

master = [a for a in json.load(open(SC + '/master_stock.json')) if a[2] and a[2] > 0]
today = datetime.date.today()
lim = (today + datetime.timedelta(days=14)).isoformat()
exp_mhd = [a for a in master if a[3] and a[3] <= lim]
# Summen exakt (Dezimal) und kaufmännisch gerundet wie die Anzeige – Gleitkomma-Summen kippen sonst bei ,xx5 je nach Datum
dsum = lambda xs: sum((Decimal(str(x)) for x in xs), Decimal(0))
exp_total = dsum(a[2] for a in master)
fmt = lambda v: f'{Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
past = [a for a in master if a[3] and a[3] < today.isoformat()]

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.click('#vt-stock'); a.wait_for_selector('#view-stock .ed-empty')
    check('empty state before import', 'Noch kein Bestand' in a.inner_text('#view-stock'))
    with a.expect_file_chooser() as fc: a.click('#view-stock [data-st=import]')
    fc.value.set_files(XLS)
    a.wait_for_selector('#dlg-stock-import [data-si=apply]', timeout=20000)
    t = a.inner_text('#dlg-stock-import')
    check('import preview: 283 articles, date', '283' in t and a.input_value('#si-date') == '2026-10-16', re.sub(r'\s+', ' ', t)[:300])
    check('preview mentions erfasst not counted', 'erfasst' in t and 'Etiketten' in t)
    a.screenshot(path=SH + '/stock-import.png')
    a.click('#dlg-stock-import [data-si=apply]'); a.wait_for_selector('.stab', timeout=10000)
    rows = a.locator('.stab tr.srow').count(); check('283 rows', rows >= 283, rows)
    heads = a.locator('.stab tr.wg-h').all_inner_texts()
    check('groups in range order, first Rind frisch, last Weitere', heads[0] == 'Rindfleisch, frisch' and 'Weitere Artikel' in heads and 'Rindfleisch, gefroren' in heads, heads)
    check('subtotal per group + gaps', a.locator('.stab tr.wg-sum').count() == len(heads) and a.locator('.stab tr.wg-gap').count() == len(heads) - 1)
    tot = a.inner_text('.stab tfoot .s-kg'); check('grand total kg', tot == fmt(exp_total) + ' kg', (tot, fmt(exp_total)))
    check('headers', 'Eingelagerter' in a.locator('.stab thead').inner_text() and 'Erwartete Zugänge' in a.locator('.stab thead').inner_text())
    # Sortierung im ersten Block: markierte zuerst, früheste oben
    first = a.locator('.stab tbody.wg').first
    cls = first.locator('tr.srow td.s-mhd').evaluate_all("els => els.map(e => [e.className.includes('mhd-'), e.textContent])")
    flags = [c[0] for c in cls]
    marked = [c[1] for c in cls if c[0]]
    iso = lambda s: '20' + s[6:8] + s[3:5] + s[0:2]
    check('marked MHD first, earliest first', flags == sorted(flags, reverse=True) and [iso(x) for x in marked] == sorted(iso(x) for x in marked), cls[:8])
    # Preis aus Angebot
    r = a.locator('.stab tr.srow:has(td.s-code:text-is("10601"))')
    check('price uses calendar week, not draft', 'Aktuell' in r.locator('.s-vk').get_attribute('data-l'))
    check('qty two decimals + kg', re.match(r'^[\d.]+,\d\d kg$', r.locator('.s-kg').inner_text()) is not None)
    a.screenshot(path=SH + '/stock.png')
    # Sortierung per Spaltenkopf
    def unmarked_codes():
        return first.locator('tr.srow').evaluate_all("rs => rs.filter(r => !r.querySelector('td.s-mhd').className.includes('mhd-')).map(r => +r.querySelector('td.s-code').textContent)")
    def marked_first():
        f = first.locator('tr.srow td.s-mhd').evaluate_all("els => els.map(e => e.className.includes('mhd-'))")
        return f == sorted(f, reverse=True)
    a.click('.stab th [data-ssort=code]'); a.wait_for_timeout(200); first = a.locator('.stab tbody.wg').first
    u = unmarked_codes(); check('sort Art. Nr ascending', u == sorted(u) and a.get_attribute('.stab th.s-code', 'aria-sort') == 'ascending' and marked_first())
    a.click('.stab th [data-ssort=code]'); a.wait_for_timeout(200); first = a.locator('.stab tbody.wg').first
    u = unmarked_codes(); check('sort Art. Nr descending (MHD-marked stay on top)', u == sorted(u, reverse=True) and marked_first(), u[:6])
    a.click('.stab th [data-ssort=kg]'); a.wait_for_timeout(200); first = a.locator('.stab tbody.wg').first
    kgs = first.locator('tr.srow').evaluate_all("rs => rs.filter(r => !r.querySelector('td.s-mhd').className.includes('mhd-') && !r.querySelector('td.s-kg').textContent.includes('kein')).map(r => parseFloat(r.querySelector('td.s-kg').textContent.replace(/\\./g,'').replace(',','.')))")
    check('sort Kg verfüg. (largest first)', kgs == sorted(kgs, reverse=True), kgs[:5])
    a.click('.stab th [data-ssort=kg]'); a.click('.stab th [data-ssort=kg]'); a.wait_for_timeout(200)
    check('third click resets sorting', a.locator('.stab th[aria-sort=ascending], .stab th[aria-sort=descending]').count() == 0)
    first = a.locator('.stab tbody.wg').first
    # Suche exakt
    a.fill('#st-q', 'Roastbeef'); a.wait_for_timeout(300)
    names = a.locator('.stab tr.srow td.s-name').all_inner_texts()
    check('search Roastbeef: only matching names', names and all('roastbeef' in n.lower() for n in names), names)
    a.fill('#st-q', '10601'); a.wait_for_timeout(300)
    check('search by number', a.locator('.stab tr.srow').count() == 1)
    # MHD-Sonderabfrage
    a.fill('#st-q', 'mhd'); a.wait_for_timeout(300)
    n = a.locator('.stab tr.srow').count()
    check('MHD query count', n == len(exp_mhd), (n, len(exp_mhd)))
    check('MHD query flat (no group rows)', a.locator('.stab tr.wg-h').count() == 0 and a.locator('.stab tr.wg-sum').count() == 0 and a.locator('.stab.flat').count() == 1)
    dates = [iso(x) for x in a.locator('.stab tr.srow td.s-mhd').all_inner_texts()]
    check('MHD query sorted ascending', dates == sorted(dates))
    tot = (a.inner_text('.stab tfoot .s-kg'), a.inner_text('.stab tfoot .s-mkg'))
    check('MHD query totals', tot == (fmt(dsum(x[2] for x in exp_mhd)) + ' kg', fmt(dsum(x[4] for x in exp_mhd)) + ' kg'), tot)
    if past:
        check('past MHD: skull + anthracite', a.locator('.stab td.s-mkg.mhd-past .mhd-skull').count() == len(past))
    else:
        check('no past MHD in data (skull n/a)', True)
    check('no pulsing animation', a.evaluate("[...document.querySelectorAll('.stab td')].every(td => getComputedStyle(td).animationName === 'none')"))
    a.screenshot(path=SH + '/stock-mhd.png')
    with a.expect_download() as dl: a.click('[data-st=csv]')
    csv = open(dl.value.path(), encoding='utf-8-sig').read().splitlines()
    check('CSV of MHD selection', len(csv) == len(exp_mhd) + 1 and csv[0].startswith('Art.-Nr.;Bezeichnung;Aktuell KW'), len(csv))
    with ctx.expect_page() as pp: a.click('[data-st=print]')
    pr = pp.value; pr.wait_for_load_state()
    check('print view', 'Bestand vom 16.10.2026' in pr.inner_text('h1') and pr.locator('tr.srow').count() == len(exp_mhd))
    pr.close()
    a.fill('#st-q', ''); a.wait_for_timeout(200)
    # Detail
    a.locator('.stab tr.srow:has(td.s-code:text-is("10022"))').click(); a.wait_for_selector('#dlg-stock-item[open]')
    check('detail: 7 lots for 10022', a.locator('#dlg-stock-item .lottab tbody tr').count() == 7, a.locator('#dlg-stock-item .lottab tbody tr').count())
    # Summe der Partien und EK-Preis (Administrator hat das Recht „bestand.einkaufspreise“)
    lots = a.evaluate("fetch('../api/?action=stock').then(r => r.json()).then(j => j.stock.articles.find(x => x.code === '10022').lots)")
    check('EK-Preis je Partie aus der Bestandsliste übernommen', len(lots) == 7 and all(isinstance(l.get('ek'), (int, float)) and l['ek'] > 0 for l in lots), lots[:2])
    foot = a.locator('#dlg-stock-item .lottab tfoot td').all_inner_texts()
    kg_sum = fmt(dsum(l['kg'] for l in lots)) + ' kg'
    gew = sum(Decimal(str(l['ek'])) * Decimal(str(l['kg'])) for l in lots) / dsum(l['kg'] for l in lots)
    check('Summenzeile: Kolli, Kg netto, Ø EK gewichtet', len(foot) == 6 and foot[0] == 'Summe' and foot[3] == str(int(sum(l['kolli'] for l in lots))) and foot[4] == kg_sum
          and foot[5] == 'Ø ' + fmt(gew) + ' €', (foot, kg_sum, fmt(gew)))
    ek1 = a.locator('#dlg-stock-item .lottab tbody tr').first.locator('td.lot-ek').inner_text()
    check('EK-Preis in der Partiezeile', ek1 == fmt(lots[0]['ek']) + ' €' and a.locator('#dlg-stock-item .lottab th:text-is("EK-Preis")').count() == 1, ek1)
    a.screenshot(path=SH + '/stock-detail.png')
    a.set_viewport_size({'width': 390, 'height': 844})
    a.wait_for_function("getComputedStyle(document.querySelector('#dlg-stock-item .lottab th.lot-ank')).display === 'none'")
    a.screenshot(path=SH + '/stock-detail-mobil.png')
    passt = a.evaluate("(() => { const w = document.querySelector('#dlg-stock-item .lot-scroll'); const d = document.querySelector('#dlg-stock-item'); return [w.scrollWidth <= w.clientWidth + 1, d.scrollWidth <= d.clientWidth + 1]; })()")
    check('Handy: Partien mit EK passen in den Dialog (Ankunft ausgeblendet)', a.evaluate('document.documentElement.scrollWidth') <= 390 and all(passt), passt)
    a.set_viewport_size({'width': 1440, 'height': 950})
    a.keyboard.press('Escape')
    # Artikel-Dialog im Angebot
    a.click('#vt-edit'); a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) [data-act="item"]').first.click()
    a.wait_for_function("document.querySelector('#item-stock') && /verfügbar|Kein/.test(document.querySelector('#item-stock').textContent)", timeout=8000)
    check('item dialog shows stock', 'verfügbar' in a.inner_text('#item-stock'), a.inner_text('#item-stock'))
    a.keyboard.press('Escape')
    # Öffentlich: keine Mengen/MHD
    o = ctx.request.get(B + '/api/?action=offer').text()
    check('public offer has no stock data', '"mhd"' not in o and '"kg"' not in o and 'lots' not in o)
    other = br.new_context()
    check('stock API needs login', other.request.get(B + '/api/?action=stock').status == 401)
    check('stock file not readable', other.request.get(B + '/data/bestand.php').status == 404)
    pub = other.new_page(); pub.goto(B + '/#suche=Roastbeef'); pub.wait_for_selector('tr.row, .empty')
    pn = pub.locator('tr.row td.c-name').all_inner_texts()
    check('public search Roastbeef: no Rippen/Tomahawk', pn and not any(('Rippen' in x or 'Tomahawk' in x) for x in pn), [x.split('\n')[0] for x in pn][:12])
    check('public page shows no MHD/kg', 'MHD' not in pub.inner_text('body') and 'verfüg' not in pub.inner_text('body'))
    other.close()
    # Protokoll
    a.click('#vt-log'); a.wait_for_selector('.ltab')
    check('log: stock import', 'Bestand übernommen' in a.inner_text('#log-list') and '283 Artikel' in a.inner_text('#log-list'))
    # Nur ansehen
    a.click('#vt-users'); a.wait_for_selector('.utab'); a.click('#user-add'); a.wait_for_selector('#dlg-user[open]')
    a.fill('#user-body [name=name]', 'Lea Leser'); a.fill('#user-body [name=username]', 'lea'); a.check('#user-body [name=role][value=viewer]')
    a.fill('#user-body [name=password]', 'Leserin-Zugang-2'); a.uncheck('#user-body [name=mustChange]'); a.click('#user-body [type=submit]'); a.wait_for_timeout(600)
    v = br.new_context(viewport={'width': 1440, 'height': 950}).new_page(); v.on('pageerror', lambda e: errs.append('v: ' + str(e)))
    login(v, 'lea', 'Leserin-Zugang-2'); v.click('#vt-stock'); v.wait_for_selector('.stab')
    check('viewer sees stock, no import', v.locator('.stab tr.srow').count() >= 283 and v.locator('[data-st=import]').count() == 0)
    vst = v.evaluate("fetch('../api/?action=stock').then(r => r.text())")
    check('Leser: keine Einkaufspreise in der Antwort', '"ek"' not in vst and '"lots"' in vst)
    v.locator('.stab tr.srow:has(td.s-code:text-is("10022"))').click(); v.wait_for_selector('#dlg-stock-item[open]')
    check('Leser: Partien mit Summe, ohne EK-Spalte', v.locator('#dlg-stock-item .lottab tfoot td').count() == 5 and v.locator('#dlg-stock-item .lottab th:text-is("EK-Preis")').count() == 0)
    v.keyboard.press('Escape')
    rr = v.evaluate("""async () => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=stock_import', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify({date:'2026-10-16', articles:[{code:'1',name:'x',kg:1,lots:[]}]})}); return r.status; }""")
    check('viewer cannot import stock (403)', rr == 403, rr)
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.click('#vt-stock'); m.wait_for_selector('.stab'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/stock-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
