"""Testgruppe editor_aux: Hilfen im Angebotseditor – Vergleich mit der Vorwoche, Bestand im Editor und Suche in
„Artikel hinzufügen“ (ohne Vorauswahl „nur mit Bestand“; die frühere Leiste „Bestand ohne Preis“ ist entfallen)."""
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
    a.wait_for_function("document.querySelector('#groups:not(.no-stock):not(.no-prev)') && document.querySelector('#mhd-panel:not([hidden])')", timeout=10000)
    # Kopfzeile wird nach dem Laden von Bestand/Vorwoche nachgezogen – auf den fertigen Stand warten
    a.wait_for_function("(() => { const t = document.querySelector('.gcard thead'); return t && t.textContent.includes('Stand 16.10.2026') && t.textContent.includes('KW 42/2026'); })()", timeout=10000)
    th = a.locator('.gcard').first.locator('thead').inner_text()
    check('headers: Vorwoche KW 42/2026, Preis KW 43, Bestand', 'Vorwoche' in th and 'KW 42/2026' in th and 'KW 43' in th and 'Bestand' in th and 'Stand 16.10.2026' in th, re.sub(r'\s+', ' ', th))
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('10601 Vorwoche (Preis − 0,40) with +0,40', row.locator('td.e-prev').inner_text().replace('\n', ' ') == de(round(preis('10601') - 0.4, 2)) + ' +0,40', row.locator('td.e-prev').inner_text())
    check('10601 Bestand aus Bestandsliste', row.locator('td.e-stock').inner_text().strip() == de(bestand_kg('10601')), row.locator('td.e-stock').inner_text())
    order = row.locator('td').evaluate_all("tds => tds.map(t => t.className.split(' ')[0])")
    check('column order prev → price → stock', order.index('e-prev') + 1 == order.index('e-price') and order.index('e-price') + 1 == order.index('e-stock'), order)
    nost = a.locator('tr[data-id] td.e-stock.none').count(); check('articles without stock show —', nost > 0, nost)
    check('Leiste „Bestand ohne Preis“ entfallen, „Kurzes MHD“ beim Öffnen zugeklappt', a.locator('#noprice-panel').count() == 0
          and a.locator('#mhd-panel .np-card:not(.open)').count() == 1 and 'Bestand ohne Preis' not in a.inner_text('#view-edit'))
    a.screenshot(path=SH + '/editor-aux.png')
    # Artikel hinzufügen: „nur mit Bestand“ nicht vorausgewählt, Suche mit Nummer (auch mit führenden Nullen), Bezeichnung
    # zusammengeschrieben bzw. mit ue statt ü, Zustand ausgeschrieben
    np = next(x for x in exp_np if len(x[0].lstrip('0')) >= 4 and norm(x[0]) not in in_offer_none)   # Bestand, nicht im Angebot
    code = np[0].lstrip('0') or '0'; name = np[1]
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    check('Artikel hinzufügen: „nur mit Bestand“ nicht vorausgewählt', a.locator('#ezp-bestand').count() == 1 and not a.is_checked('#ezp-bestand'))
    def treffer(q):
        a.fill('#ezp-q', q)
        a.wait_for_function("q => document.querySelector('.ezp-lkopf h3, .ezp-start') && (document.querySelector('.ezp-lkopf h3') || {}).textContent?.includes(q)", arg=q)
        return a.eval_on_selector_all('#ezp-list tr[data-code]', 'e => e.map(x => x.dataset.code)')
    t = treffer('00' + code)
    check('Suche: Nummer mit führenden Nullen findet den Artikel', code in t, t[:5])
    lamm = [norm(i['code']) for i in offer['items'] if i['code'] and re.search(r'lamm\s+filet', i['name'], re.I)]
    t = treffer('lammfilet')
    check('Suche: „lammfilet“ findet „Lamm Filet“ (zusammengeschrieben)', lamm and all(c in t for c in lamm), (lamm, t[:6]))
    hufte = [norm(i['code']) for i in offer['items'] if i['code'] and 'hüfte' in i['name'].lower()]
    t = treffer('steakhuefte')
    check('Suche: ue statt ü', hufte and any(c in t for c in hufte), (hufte[:3], t[:6]))
    gefr = [norm(i['code']) for i in offer['items'] if i['code'] and i.get('condition') == 'gefroren' and 'gefr' not in i['name'].lower() and 'tk' not in i['name'].lower()]
    t = treffer('gefroren')
    check('Suche: Zustand „gefroren“ auch ohne das Wort in der Bezeichnung', not gefr or any(c in t for c in gefr), (gefr[:3], t[:6]))
    t = treffer(code)
    a.click(f'#ezp-list tr[data-code="{code}"] .ezp-n'); a.wait_for_selector(f'#ezp-list [data-preis="{code}"]')
    a.fill(f'#ezp-list [data-preis="{code}"]', '9,99x'); a.click('#ezp-ok'); a.wait_for_selector('#ezp-anz .ezp-err')
    check('invalid price rejected', 'nicht lesbar' in a.inner_text('#ezp-anz'))
    a.fill(f'#ezp-list [data-preis="{code}"]', '9,99'); a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); a.wait_for_timeout(1200)
    new = a.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])')
    check('article added with price + stock', new.count() == 1 and new.locator('input[data-f=price]').input_value() == '9,99' and new.locator('td.e-stock').inner_text().strip() != '—', code)
    exp = re.sub(r'[\s,]*\bfrisch\b\.?[\s,.]*$', '', name, flags=re.I).strip() or name
    # Vorschlag beim Anlegen: ohne „frisch“, in Gruppen der Eigenmarke mit „Fleischmeister“ (vorher erst beim nächsten Laden ergänzt)
    gk = new.evaluate("r => { const s = r.closest('section.gcard'); return s ? [...s.querySelectorAll('.ghead .g-name, .ghead .g-sec')].map((e) => e.value).join(' | ') : '' }")
    if re.search('fleischmeister', gk, re.I) and not re.search('fleischmeister', exp, re.I):
        exp = re.sub(r'^([^,]+?)(\s*,|$)', r'\1 Fleischmeister\2', exp, count=1)
    check('name taken from stock list (without frisch, Marke in Fleischmeister-Gruppen)', new.locator('input[data-f=name]').input_value() == exp, (new.locator('input[data-f=name]').input_value(), exp, gk[:80]))
    # Preis auf Vorwochenpreis → Differenz verschwindet
    pi = row.locator('input[data-f=price]'); pi.fill(de(round(preis('10601') - 0.4, 2))); pi.press('Tab'); a.wait_for_timeout(800)
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('delta disappears when equal to Vorwoche', row.locator('td.e-prev').inner_text().strip() == de(round(preis('10601') - 0.4, 2)))
    # Woche ändern → Vorwoche neu
    a.fill('#m-week', '42'); a.press('#m-week', 'Tab'); a.wait_for_timeout(1200)
    check('week change reloads Vorwoche (none before KW42 → column hidden)', not a.locator('tr[data-id] td.e-prev').first.is_visible())
    # Titel aus dem früheren Import zieht die Woche mit (gemeldet 05.11.2026: Kundenseite zeigte „KW 43“ im Angebot der KW 45)
    from umgebung import until as _until   # gespeicherten Entwurf abwarten (Python-seitig)
    _dm = _until(lambda: (lambda m: m if m and m.get('week') == 42 else None)(a.evaluate("async () => ((await (await fetch('../api/?action=draft')).json()).draft || {}).meta")), timeout=10) or {}
    check('week change: imported title follows the week', 'KW 42' in (_dm.get('title') or '') and 'KW 43' not in (_dm.get('title') or ''), _dm.get('title'))
    a.fill('#m-week', '43'); a.press('#m-week', 'Tab'); a.wait_for_timeout(1200)
    check('back to KW 43 shows Vorwoche again', a.locator('tr[data-id] td.e-prev').first.is_visible())
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_selector('#mhd-panel:not([hidden])'); m.wait_for_timeout(300)
    m.screenshot(path=SH + '/editor-aux-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
