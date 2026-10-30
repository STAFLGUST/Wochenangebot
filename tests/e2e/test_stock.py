import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, os, re, datetime
from decimal import Decimal, ROUND_HALF_UP
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
from testdaten import de, preis, preise, artikel, bestand_kg
from kunden_hilfe import Client
from umgebung import storage_raw
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
    # Kopf der Bestandskarte: „· n Tage alt“ steht in der Zeile des Datums, nicht allein in einer eigenen Zeile (Liste vom 16.10.)
    kopf = a.evaluate("""(() => { const s = document.querySelector('#view-stock .st-info strong').getBoundingClientRect(), g = document.querySelector('#view-stock .st-info .st-age');
      return g ? [Math.round(s.top), Math.round(g.getBoundingClientRect().top), g.textContent] : null; })()""")
    check('stock card: age next to the date (same line)', kopf and abs(kopf[0] - kopf[1]) <= 2 and 'Tage alt' in kopf[2], kopf)
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
    # Erwartete Zugänge: dieselbe Tabelle wie die Partien (Spalte ETA statt Ankunft), Kolli und EK aus der Zeile „erfasst“
    kz = a.locator('#dlg-stock-item .zutab thead th').all_inner_texts(); kp = a.locator('#dlg-stock-item .lottab thead th').all_inner_texts()
    zz = a.locator('#dlg-stock-item .zutab tbody tr').first.locator('td').all_inner_texts()
    check('Zugänge: gleiche Spalten wie die Partien, ETA statt Ankunft', [x.upper() for x in kz] == [('ETA' if x.upper() == 'ANKUNFT' else x.upper()) for x in kp], (kz, kp))
    check('Zugang 10022: Partie, ETA, MHD „—“, Kolli 8, 186,12 kg, EK 24,48 €', a.locator('#dlg-stock-item .zutab tbody tr').count() == 1
          and zz[-5:] == ['15.10.2026', '—', '8', '186,12 kg', '24,48 €'], zz)
    zf = a.locator('#dlg-stock-item .zutab tfoot td').all_inner_texts()
    check('Zugänge: Summenzeile wie bei den Partien', len(zf) == len(kz) and 'Summe' in zf and '186,12 kg' in zf and 'Ø 24,48 €' in zf, zf)
    titel = a.locator('#dlg-stock-item h3.d-h > span:first-child')
    check('Abschnittstitel deutlich: fett, Textfarbe, ≥ 13 px', titel.count() == 3 and titel.evaluate_all(
          "els => els.every(e => +getComputedStyle(e).fontWeight >= 700 && parseFloat(getComputedStyle(e).fontSize) >= 13 && getComputedStyle(e).color === getComputedStyle(document.body).color)"),
          titel.all_inner_texts())
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
    a.fill('#user-body [name=vorname]', 'Lea'); a.fill('#user-body [name=nachname]', 'Leser'); a.fill('#user-body [name=username]', 'lea'); a.locator('#user-body [name=rollen]').evaluate_all("(els, v) => els.forEach((e) => { if (e.checked !== (e.value === v)) e.click(); })", 'viewer')
    a.fill('#user-body [name=password]', 'Leserin-Zugang-2'); a.uncheck('#user-body [name=mustChange]'); a.click('#user-body [type=submit]')
    a.wait_for_selector('#user-body .us-fertig'); a.click('#user-body .dlg-foot [data-close]'); a.wait_for_function("!document.querySelector('#dlg-user').open")
    v = br.new_context(viewport={'width': 1440, 'height': 950}).new_page(); v.on('pageerror', lambda e: errs.append('v: ' + str(e)))
    login(v, 'lea', 'Leserin-Zugang-2'); v.click('#vt-stock'); v.wait_for_selector('.stab')
    check('viewer sees stock, no import', v.locator('.stab tr.srow').count() >= 283 and v.locator('[data-st=import]').count() == 0)
    vst = v.evaluate("fetch('../api/?action=stock').then(r => r.text())")
    check('Leser: keine Einkaufspreise in der Antwort', '"ek"' not in vst and '"lots"' in vst)
    v.locator('.stab tr.srow:has(td.s-code:text-is("10022"))').click(); v.wait_for_selector('#dlg-stock-item[open]')
    check('Leser: Partien mit Summe, ohne EK-Spalte', v.locator('#dlg-stock-item .lottab tfoot td').count() == 5 and v.locator('#dlg-stock-item .lottab th:text-is("EK-Preis")').count() == 0)
    check('Leser: erwartete Zugänge ohne EK-Spalte', v.locator('#dlg-stock-item .zutab tfoot td').count() == 5 and v.locator('#dlg-stock-item .zutab th:text-is("EK-Preis")').count() == 0)
    v.keyboard.press('Escape')
    rr = v.evaluate("""async () => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=stock_import', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify({date:'2026-10-16', articles:[{code:'1',name:'x',kg:1,lots:[]}]})}); return r.status; }""")
    check('viewer cannot import stock (403)', rr == 403, rr)
    # ---------- Bezeichnung aus den Artikelstammdaten, VK-Gruppen, Spaltenfilter ----------
    A = Client('198.51.100.40'); A.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})
    check('VK-Gruppen gespeichert', A.call('vkgruppen_save', {'rev': A.call('vkgruppen')[1]['rev'], 'groups': [{'nr': '1100', 'name': 'Rind frisch (Test)'}, {'nr': '1200', 'name': 'Färse (Test)'}]})[0] == 200)
    stamm = {'10000': ('Oberschale aus Stammdaten', '1100'), '10001': ('Oberschale JB aus Stammdaten', '1100'), '10002': ('Oberschale Färse aus Stammdaten', '1200')}
    roh = {x[0]: x for x in master}
    # Merkmale (Fleischart · Herkunft · Zustand, Entscheidung Inhaber 30.10.2026): ein Artikel nur mit Merkmalen (Name wie in
    # der Bestandsliste, „Dry Aged“ steht nicht im Namen) und einer ganz ohne Merkmale (Sonstiges, unbekannt, ohne Herkunft)
    im_bestand = {x['code'] for x in A.call('stock')[1]['stock']['articles']}
    frei = [c for c, x in roh.items() if c in im_bestand and c not in stamm and not any(w in x[1].lower() for w in ('oberschale', 'dry', 'schwein', 'aus stammdaten'))]
    c_dry, c_ohne = frei[0], frei[1]
    extra = [{'code': c_dry, 'name': ' '.join(roh[c_dry][1].split()), 'category': 'Schwein', 'origin': 'DE', 'condition': 'dry-aged'},
             {'code': c_ohne, 'name': ' '.join(roh[c_ohne][1].split()), 'category': 'Sonstiges', 'condition': 'unbekannt'}]
    st_, r_ = A.call('master_save', {'rev': A.call('master')[1]['master']['rev'], 'articles': [{'code': c, 'name': n, 'category': 'Rind', 'origin': 'AR', 'condition': 'frisch', 'vkGruppe': g} for c, (n, g) in stamm.items()] + extra})
    check('Artikelstammdaten gespeichert', st_ == 200, r_)
    sj = A.call('stock')[1]['stock']
    s1 = next(x for x in sj['articles'] if x['code'] == '10000')
    sx = lambda c: next(x for x in sj['articles'] if x['code'] == c)   # noqa: E731
    check('API: Merkmale aus den Stammdaten (Fleischart · Herkunft · Zustand, Sonstiges/unbekannt/leer weggelassen)', s1.get('merkmale') == 'Rind · AR · frisch'
          and sx(c_dry).get('merkmale') == 'Schwein · DE · Dry Aged' and 'nameImport' not in sx(c_dry) and 'merkmale' not in sx(c_ohne),
          [s1.get('merkmale'), sx(c_dry).get('merkmale'), sx(c_ohne).get('merkmale')])
    soll = {**{c: 'Rind · AR · frisch' for c in stamm}, c_dry: 'Schwein · DE · Dry Aged'}
    check('API: ohne Stammdatensatz keine Merkmale; Zugänge tragen dieselben Merkmale wie der Artikel', all(x.get('merkmale') == soll.get(x['code']) for x in sj['articles'] + sj['incoming']),
          [(x['code'], x.get('merkmale')) for x in sj['articles'] + sj['incoming'] if x.get('merkmale') != soll.get(x['code'])][:5])
    check('gespeicherter Bestand ohne Merkmale (nur beim Lesen ergänzt)', 'merkmale' not in storage_raw('bestand'))
    check('API: Bezeichnung und VK-Gruppe aus den Stammdaten, Name der Bestandsliste als nameImport', s1['name'] == 'Oberschale aus Stammdaten' and s1['nameImport'] == roh['10000'][1]
          and s1['vk'] == '1100' and sj['vkgruppen'] == {'1100': 'Rind frisch (Test)', '1200': 'Färse (Test)'}, {k: s1.get(k) for k in ('name', 'nameImport', 'vk')})
    check('API: ohne Stammdatensatz bleibt der Name der Bestandsliste', all(x['name'] == ' '.join(roh[x['code']][1].split()) and 'nameImport' not in x and 'vk' not in x for x in sj['articles'] if x['code'] in roh and x['code'] not in stamm))
    check('gespeicherter Bestand unverändert (Name der Bestandsliste)', roh['10000'][1] in storage_raw('bestand') and 'aus Stammdaten' not in storage_raw('bestand'))
    a.click('#vt-edit'); a.wait_for_selector('tr[data-id]'); a.click('#vt-stock'); a.wait_for_selector('.stab tr.srow')
    zeile = lambda c: a.locator(f'.stab tr.srow:has(td.s-code:text-is("{c}"))')   # noqa: E731
    name_txt = lambda c: zeile(c).locator('td.s-name').evaluate('td => td.firstChild.textContent')   # noqa: E731
    check('Liste: Bezeichnung aus den Stammdaten, Name der Bestandsliste im Hinweis', name_txt('10000') == 'Oberschale aus Stammdaten'
          and roh['10000'][1] in zeile('10000').locator('td.s-name').get_attribute('title'))
    unter = zeile('10000').locator('.s-merk').evaluate("e => { const r = document.createRange(); r.selectNodeContents(e.parentElement.firstChild); return e.getBoundingClientRect().top >= r.getBoundingClientRect().bottom - 1; }")
    check('Liste: Merkmale als zweite Zeile unter der Bezeichnung (auch im Hinweis), ohne Merkmale keine Zeile', zeile('10000').locator('.s-merk').inner_text() == 'Rind · AR · frisch' and unter
          and 'Rind · AR · frisch' in zeile('10000').locator('td.s-name').get_attribute('title') and zeile(c_dry).locator('.s-merk').inner_text() == 'Schwein · DE · Dry Aged'
          and zeile(c_ohne).locator('.s-merk').count() == 0, unter)
    a.fill('#st-q', 'dry aged'); a.wait_for_function(f"[...document.querySelectorAll('.stab tr.srow td.s-code')].some((t) => t.textContent === '{c_dry}')")
    check('Suche findet auch die Merkmale („dry aged“ steht nur in den Stammdaten)', name_txt(c_dry) == ' '.join(roh[c_dry][1].split()))
    a.fill('#st-q', '10000'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 1")
    zeile('10000').locator('td.s-name').click(); a.wait_for_selector('#dlg-stock-item[open] h2')
    check('Artikeldetail: Merkmale unter dem Titel', a.inner_text('#dlg-stock-item h2') == 'Oberschale aus Stammdaten' and a.inner_text('#dlg-stock-item .s-merk-d') == 'Rind · AR · frisch')
    a.keyboard.press('Escape'); a.wait_for_function("!document.querySelector('#dlg-stock-item').open")
    with a.expect_download() as dl: a.click('[data-st=csv]')
    zeilen_csv = open(dl.value.path(), encoding='utf-8-sig').read().splitlines()
    check('CSV: Bezeichnung mit Merkmalen („Name · Fleischart · Herkunft · Zustand“)', len(zeilen_csv) == 2 and zeilen_csv[1].split(';')[1].strip('"') == 'Oberschale aus Stammdaten · Rind · AR · frisch', zeilen_csv[1:])
    a.fill('#st-q', 'aus Stammdaten'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 3")
    a.screenshot(path=SH + '/stock-merkmale.png')
    a.emulate_media(color_scheme='dark'); a.screenshot(path=SH + '/stock-merkmale-dunkel.png'); a.emulate_media(color_scheme='light')
    a.fill('#st-q', roh['10002'][1]); a.wait_for_function("[...document.querySelectorAll('.stab tr.srow td.s-code')].some((t) => t.textContent === '10002')")
    check('Suche findet auch den Namen der Bestandsliste', name_txt('10002') == 'Oberschale Färse aus Stammdaten')
    a.fill('#st-q', ''); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length >= 283")
    gesamt = a.locator('.stab tr.srow').count()
    check('jede Überschrift mit Trichter (10 Spalten)', a.locator('.stab thead [data-sfilter]').count() == 10)
    # Text: Bezeichnung enthält
    a.click('.stab th [data-sfilter=name]'); a.wait_for_selector('#st-pop:not([hidden]) input[data-ff=q]')
    a.fill('#st-pop input[data-ff=q]', 'oberschale'); a.wait_for_function("document.querySelector('.stab th.s-name .st-fbtn.on')")
    namen = a.locator('.stab tr.srow td.s-name').all_inner_texts()
    check('Filter Bezeichnung: nur passende Zeilen, Trichter hervorgehoben, Leiste mit Filter', namen and all('oberschale' in n.lower() for n in namen) and len(namen) < gesamt
          and 'Art. Bezeichnung enthält „oberschale“' in a.inner_text('.st-fleiste'), len(namen))
    a.click('#st-pop [data-pop=zu]'); a.wait_for_selector('#st-pop', state='hidden')
    # Zahlenbereich: Eingelagerter Bestand ab 300 kg, Summe = gezeigte Zeilen
    a.click('.stab th [data-sfilter=kg]'); a.fill('#st-pop input[data-ff=min]', '300')
    erwart = [x for x in master if 'oberschale' in x[1].lower() and x[2] >= 300 and x[0] not in stamm] + [x for x in master if x[0] in stamm and 'oberschale' in stamm[x[0]][0].lower() and x[2] >= 300]
    a.wait_for_function(f"document.querySelectorAll('.stab tr.srow').length === {len(erwart)}")
    check('Filter Zahlenbereich (UND mit Bezeichnung), Gesamtsumme der gefilterten Zeilen', a.inner_text('.stab tfoot .s-kg') == fmt(dsum(x[2] for x in erwart)) + ' kg', (a.inner_text('.stab tfoot .s-kg'), len(erwart)))
    a.keyboard.press('Escape'); a.wait_for_selector('#st-pop', state='hidden')
    # Sortieren aus dem Fenster
    a.click('.stab th [data-sfilter=totalKg]'); a.click('#st-pop [data-pop=ab]'); a.wait_for_function("document.querySelector('.stab th.s-total-kg').getAttribute('aria-sort') === 'descending'")
    a.click('#st-pop [data-pop=zu]')
    check('Sortieren aus dem Filterfenster (absteigend)', a.get_attribute('.stab th.s-total-kg', 'aria-sort') == 'descending')
    a.screenshot(path=SH + '/stock-filter.png')
    a.click('.stab th [data-sfilter=mhd]'); a.wait_for_selector('#st-pop:not([hidden])')
    a.emulate_media(color_scheme='dark'); a.screenshot(path=SH + '/stock-filter-dunkel.png'); a.emulate_media(color_scheme='light')
    a.click('#st-pop [data-pop=zu]')
    # Filter einzeln entfernen, dann MHD-Stufe und Zugänge
    a.click('.st-fleiste [data-fweg=kg]'); a.wait_for_function("!document.querySelector('.stab th.s-kg .st-fbtn.on')")
    a.click('.st-fleiste [data-fweg="*"]'); a.wait_for_function(f"document.querySelectorAll('.stab tr.srow').length === {gesamt}")
    check('„Alle Filter entfernen“: alle Artikel, keine Leiste', a.locator('.st-fleiste').count() == 0)
    a.click('.stab th [data-sfilter=mhd]'); a.check('#st-pop input[data-ff=stufe][value="ohne"]')
    a.wait_for_function("document.querySelectorAll('.stab tr.srow').length > 0 && [...document.querySelectorAll('.stab tr.srow td.s-mhd')].every((t) => t.textContent === '—')")
    ohne = a.locator('.stab tr.srow').count()
    check('Filter MHD „ohne MHD“: nur Zeilen ohne MHD', ohne == len([x for x in master if not x[3]]) + a.evaluate("fetch('../api/?action=stock').then(r => r.json()).then(j => new Set(j.stock.incoming.map(z => z.code).filter(c => !j.stock.articles.some(x => x.code === c))).size)"), ohne)
    a.click('#st-pop [data-pop=leeren]'); a.click('#st-pop [data-pop=zu]')
    a.click('.stab th [data-sfilter=zugaenge]'); a.select_option('#st-pop select[data-ff=art]', 'mit')
    a.wait_for_function("document.querySelectorAll('.stab tr.srow').length > 0 && [...document.querySelectorAll('.stab tr.srow td.s-incoming')].every((t) => t.querySelector('[data-incoming]'))")
    check('Filter Zugänge „nur mit“: jede Zeile mit Zugängen', a.locator('.stab tr.srow').count() < gesamt)
    a.click('#st-pop [data-pop=zu]')
    with ctx.expect_page() as pp: a.click('[data-st=print]')
    pr = pp.value; pr.wait_for_load_state()
    check('Druck: gefilterte Auswahl, Filter in der Überschrift, ohne Trichter', 'Filter: Erwartete Zugänge: mit Zugängen' in pr.inner_text('h1') and pr.locator('tr.srow').count() == a.locator('.stab tr.srow').count()
          and pr.locator('svg').count() == 0, pr.inner_text('h1'))
    pr.close()
    a.click('.st-fleiste [data-fweg="*"]'); a.wait_for_function(f"document.querySelectorAll('.stab tr.srow').length === {gesamt}")
    # Fenster „VK-Gruppen“
    a.click('[data-st=vk]'); a.wait_for_selector('#dlg-stock-vk[open] tbody[data-vk]')
    gr = a.eval_on_selector_all('#dlg-stock-vk tbody[data-vk]', "els => els.map((e) => [e.dataset.vk, e.querySelector('.vk-auf').textContent, e.querySelectorAll('tr.vk-a').length])")
    check('VK-Gruppen: 1100 (2 Artikel), 1200 (1), „Ohne VK-Gruppe“ zuletzt', [g[0] for g in gr] == ['1100', '1200', ''] and gr[0][2] == 2 and gr[1][2] == 1 and 'Rind frisch (Test)' in gr[0][1]
          and 'Ohne VK-Gruppe' in gr[2][1] and gr[2][2] == gesamt - 3, gr)
    kg1100 = a.inner_text('#dlg-stock-vk tbody[data-vk="1100"] tr.vk-h td.s-kg')
    check('VK-Gruppe 1100: Summe des eingelagerten Bestands', kg1100 == fmt(dsum([roh['10000'][2], roh['10001'][2]])) + ' kg', kg1100)
    check('Gesamtsumme im Fenster = Gesamtsumme der Liste', a.inner_text('#dlg-stock-vk tfoot td.s-kg') == a.inner_text('.stab tfoot .s-kg'))
    check('Gruppen zugeklappt', a.locator('#dlg-stock-vk tr.vk-a:visible').count() == 0)
    a.click('#dlg-stock-vk [data-vkauf="1100"]'); a.wait_for_function("document.querySelectorAll('#dlg-stock-vk tbody[data-vk=\"1100\"] tr.vk-a:not([hidden])').length === 2")
    check('Aufklappen zeigt die Artikel mit Bezeichnung und Merkmalen aus den Stammdaten', 'Oberschale aus Stammdaten' in a.inner_text('#dlg-stock-vk tbody[data-vk="1100"]')
          and a.locator('#dlg-stock-vk tbody[data-vk="1100"] tr.vk-a .s-merk').all_inner_texts() == ['Rind · AR · frisch'] * 2
          and a.get_attribute('#dlg-stock-vk [data-vkauf="1100"]', 'aria-expanded') == 'true')
    a.select_option('#vk-sort', 'totalKg'); a.wait_for_function("document.querySelector('#vk-sort').value === 'totalKg'")
    a.screenshot(path=SH + '/stock-vkgruppen.png')
    a.keyboard.press('Escape'); a.wait_for_function("!document.querySelector('#dlg-stock-vk').open")
    a.click('.stab th [data-sfilter=name]'); a.fill('#st-pop input[data-ff=q]', 'aus Stammdaten'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 3")
    a.keyboard.press('Escape'); a.click('[data-st=vk]'); a.wait_for_selector('#dlg-stock-vk[open] tbody[data-vk]')
    check('VK-Gruppen: nur die gefilterte Auswahl (ohne „Ohne VK-Gruppe“)', a.eval_on_selector_all('#dlg-stock-vk tbody[data-vk]', 'els => els.map((e) => e.dataset.vk)') == ['1100', '1200'])
    a.keyboard.press('Escape'); a.click('.st-fleiste [data-fweg="*"]')
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    m.on('pageerror', lambda e: errs.append('m: ' + str(e)))
    login(m, 'admin', 'Sicheres-Passwort-1'); m.click('#vt-stock'); m.wait_for_selector('.stab'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/stock-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('Handy: Merkmale unter der Bezeichnung sichtbar', m.locator('.stab tr.srow:has(td.s-code:text-is("10000")) .s-merk').is_visible())
    m.click('[data-st=filter]'); m.wait_for_selector('#dlg-stock-filter[open]')
    m.fill('#dlg-stock-filter input[data-fk=name]', 'aus Stammdaten'); m.wait_for_function("document.querySelector('#sf-zahl').textContent === '3 Artikel'")
    m.screenshot(path=SH + '/stock-filter-mobil.png')
    m.click('#dlg-stock-filter .dlg-foot [data-close]'); m.wait_for_function("!document.querySelector('#dlg-stock-filter').open")
    check('Handy: Filter über den Knopf „Filter“, Zahl am Knopf', m.locator('.stab tr.srow').count() == 3 and m.inner_text('#st-fzahl') == '1')
    m.screenshot(path=SH + '/stock-merkmale-mobil.png')
    m.click('[data-st=vk]'); m.wait_for_selector('#dlg-stock-vk[open] tbody[data-vk]')
    m.screenshot(path=SH + '/stock-vkgruppen-mobil.png')
    check('Handy: VK-Gruppen ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390
          and m.evaluate("(() => { const d = document.querySelector('#dlg-stock-vk'); return d.scrollWidth <= d.clientWidth + 1; })()"))
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
