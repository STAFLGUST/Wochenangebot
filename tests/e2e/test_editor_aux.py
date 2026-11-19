"""Testgruppe editor_aux: Hilfen im Angebotseditor – Vergleich mit der Vorwoche, Bestand im Editor und Suche in
„Artikel hinzufügen“ (ohne Vorauswahl „nur mit Bestand“; die frühere Leiste „Bestand ohne Preis“ ist entfallen) sowie
„Export für WinAB“ (Recht angebot.winab_export: Eintrag im Bereich Import, Datei „ImportPreise.csv“ aus dem veröffentlichten
Wochenangebot, je Nummer der höchste Preis)
sowie die Artikelkarte des Bestands im Angebot (Klick auf den Bestand oder eine freie Fläche der Artikelzeile)."""
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
# Artikelkarte: 10601 mit zwei Partien (EK) und einem erwarteten Zugang – Summe der Partien unabhängig vom gemeldeten Bestand
LOTS_10601 = [{'lot': '900001', 'marke': 'Testmarke A', 'arrival': '2026-09-15', 'mhd': '2026-11-04', 'kolli': 6, 'kg': 8.94, 'ek': 20.0},
              {'lot': '900002', 'marke': 'Testmarke B', 'arrival': '2026-10-02', 'mhd': '2026-12-01', 'kolli': 3, 'kg': 19.1, 'ek': 19.4}]
next(x for x in articles if x['code'] == '10601')['lots'] = LOTS_10601
ZUGANG_10601 = [{'code': '10601', 'name': 'Zugang Test', 'kg': 50.0, 'arrival': '2026-10-28', 'lot': '900099', 'kolli': 4, 'marke': 'Testmarke C'}]

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def get(pg, action):
    return pg.evaluate("""async (a) => { const r = await fetch('../api/?action=' + a); return [r.status, await r.json()]; }""", action)
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
    r = post(a, 'stock_import', {'date': '2026-10-16', 'source': 'Bestand_16.10.26.XLS', 'articles': articles, 'incoming': ZUGANG_10601}); check('stock stored', r[0] == 200, r[1] if r[0] != 200 else '')
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
    # ---------- Artikelkarte des Bestands im Angebot (Wunsch Inhaber 06.11.2026) ----------
    karte = '#dlg-stock-item'
    def karte_zu(pg):
        pg.click(karte + ' .dlg-head [data-close]'); pg.wait_for_selector(karte + ':not([open])', state='attached')
    def frei(zeile):   # freie Fläche der Artikelzeile: rechte untere Ecke der Bezeichnungsspalte (neben den Merkmalen)
        td = zeile.locator('td.e-name'); bx = td.bounding_box(); td.click(position={'x': bx['width'] - 4, 'y': bx['height'] - 3})
    btn = row.locator('td.e-stock button.e-bst')
    check('Karte: Bestandswert ist ein Knopf (Tastatur) mit Bestand als Text', btn.count() == 1 and btn.inner_text().strip() == de(bestand_kg('10601'))
          and 'Partien und Zugänge' in (btn.get_attribute('aria-label') or ''), btn.count())
    btn.click(); a.wait_for_selector(karte + '[open] .lottab')
    kt = a.inner_text(karte)
    check('Karte aus dem Angebot: Kopf mit Art.-Nr. und Stand, Kennzahlen wie im Bestand', 'Art.-Nr. 10601' in kt and 'Bestand vom 16.10.2026' in kt
          and a.locator(karte + ' .cmp-stats > div').count() == 7 and de(bestand_kg('10601')) + ' kg' in a.inner_text(karte + ' .cmp-stats > div:first-child'), kt[:200])
    lz = a.locator(karte + ' .lottab tbody tr'); zz = a.locator(karte + ' .zutab tbody tr')
    check('Karte: zwei Partien mit Marke und EK (Administrator), ein erwarteter Zugang', lz.count() == 2 and zz.count() == 1 and 'Testmarke A' in lz.first.inner_text()
          and '900002' in lz.nth(1).inner_text() and a.locator(karte + ' .lottab th:text-is("EK-Preis")').count() == 1 and '900099' in zz.first.inner_text(), (lz.count(), zz.count()))
    check('Karte: Summe der Partien (9 Kolli, 28,04 kg)', a.locator(karte + ' .lottab tfoot').inner_text().replace('\n', ' ').count('28,04 kg') == 1
          and '\t9\t' in a.locator(karte + ' .lottab tfoot tr').inner_text(), a.locator(karte + ' .lottab tfoot').inner_text())
    kx = a.text_content(karte)
    check('Karte: Abschnitt „Im Angebot (Entwurf KW 43)“ mit Preis', 'Im Angebot (Entwurf KW 43)' in kx and de(preis('10601')) in kx.split('Im Angebot')[1], kx.split('Im Angebot')[-1][:120])
    a.locator(karte).screenshot(path=SH + '/artikelkarte-angebot.png')
    karte_zu(a)
    frei(row); a.wait_for_selector(karte + '[open] .lottab')
    check('Karte: Klick auf eine freie Fläche der Artikelzeile öffnet sie ebenso', a.locator(karte + ' .lottab tbody tr').count() == 2)
    karte_zu(a)
    row.locator('input[data-f=name]').click()
    offen = a.evaluate("() => new Promise((r) => setTimeout(() => r(document.querySelector('#dlg-stock-item').open), 400))")
    check('Karte: Klick in die Bezeichnung bearbeitet sie weiter (keine Karte)', not offen and a.evaluate("document.activeElement.dataset.f") == 'name')
    row.locator('td.e-price').click(position={'x': 4, 'y': 4})
    offen = a.evaluate("() => new Promise((r) => setTimeout(() => r(document.querySelector('#dlg-stock-item').open), 400))")
    check('Karte: Klick in die Preisspalte öffnet sie nicht', not offen)
    leer = a.locator('tr[data-id]:has(td.e-stock.none button.e-bst)').first
    lc = leer.locator('input[data-f=code]').input_value()
    leer.locator('td.e-stock button.e-bst').click(); a.wait_for_selector(karte + '[open] .cmp-stats')
    kt = a.text_content(karte)
    check('Karte: Artikel ohne Bestand – leere Werte, „keine eingelagerten Partien“', f'Art.-Nr. {lc}' in kt and 'keine eingelagerten Partien' in kt and a.locator(karte + ' .lottab').count() == 0
          and a.inner_text(karte + ' .cmp-stats > div:first-child').strip().endswith('—'), (lc, kt[:160]))
    karte_zu(a)
    check('Karte: ohne Artikelnummer kein Knopf', a.locator('tr[data-id] td.e-stock.none:not(:has(button))').count() == a.locator('tr[data-id]:has(input[data-f=code][value=""])').count())
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
    # ---------- Export für WinAB (Recht angebot.winab_export): veröffentlichtes Wochenangebot, je Nummer der höchste Preis ----------
    lager = {norm(x['code']) for x in articles}
    wahl, gesehen = [], set()
    for i in offer['items']:
        if i['code'] and i['price']['status'] == 'value' and str(i['code']).isdigit() and norm(i['code']) not in gesehen:
            gesehen.add(norm(i['code'])); wahl.append(i)
    sp = next(i for i in wahl if norm(i['code']) in lager)          # Sonderposten mit Bestand (nicht ausverkauft)
    c = [i for i in wahl if i is not sp][:5]
    def art(src, nid, **f):
        x = {k: v for k, v in src.items() if k not in ('variants', 'sale', 'namen')}; x['id'] = nid; x['altPrices'] = []; x.update(f); return x
    wert = lambda v: {'status': 'value', 'value': v}
    wm = dict(offer); wm['meta'] = {k: v for k, v in offer['meta'].items() if k != 'werbung'}; wm['meta'].update(week=45, year=2026)
    wm['items'] = [art(c[0], 'w1', price=wert(10.0)), art(c[0], 'w2', price=wert(12.5)),                   # doppelt: höherer Preis
                   art(c[0], 'w2b', code='0' + c[0]['code'], price=wert(11.0)),                             # gleiche Nummer mit führender Null
                   art(c[1], 'w3', price=wert(8.0), altPrices=[wert(9.25)]),                                 # Zusatzpreis höher
                   art(c[2], 'w4', price=wert(7.5), variants={'std': {'status': 'hidden'}}),                 # im Wochenangebot ausgeblendet
                   art(c[3], 'w5', price={'status': 'request'}),                                             # auf Anfrage
                   art(c[4], 'w6', price=wert(5.1234)),                                                      # vier Nachkommastellen
                   art(sp, 'w7', price=wert(20.0), sale={'value': 15.5})]                                    # Sonderposten: Preis wie beim Kunden
    r = post(a, 'publish', {'model': wm, 'revision': get(a, 'draft')[1]['revision']}); check('WinAB: Testangebot KW 45/2026 veröffentlicht', r[0] == 200, r)
    nat = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', t)]
    def wb(v): t = f'{v:.4f}'.replace('.', ','); return re.sub(r'(,\d\d)0{1,2}$', r'\1', t)
    erw = {c[0]['code']: 12.5, c[1]['code']: 9.25, c[4]['code']: 5.1234, sp['code']: 15.5}
    soll = 'Artikelnummer;Preis\r\n' + ''.join(f'{k};{wb(erw[k])}\r\n' for k in sorted(erw, key=nat))
    # Entwurf der Folgewoche (Inhaber 19.11.2026: die Preise der neuen Woche exportieren, bevor sie veröffentlicht sind): andere KW, ein Preis höher
    wd = json.loads(json.dumps(wm)); wd['meta'].update(week=46); wd['items'][1]['price'] = wert(13.75)
    r = post(a, 'save_draft', {'model': wd, 'revision': get(a, 'draft')[1]['revision']}); check('WinAB: Entwurf KW 46/2026 gespeichert, nicht veröffentlicht', r[0] == 200, r)
    soll_e = soll.replace(f"{c[0]['code']};12,50", f"{c[0]['code']};13,75")
    post(a, 'user_save', {'name': 'Wina', 'username': 'wina', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False, 'grant': ['angebot.winab_export']})
    wina_id = next(u['id'] for u in get(a, 'users')[1]['users'] if u['username'] == 'wina')
    post(a, 'user_save', {'name': 'Eddi', 'username': 'eddi', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    w = br.new_page(viewport={'width': 1440, 'height': 950}); w.on('pageerror', lambda e: errs.append('wina: ' + str(e)))
    login(w, 'wina', 'Leserin-Zugang-1')
    check('WinAB: kein Knopf mehr in der Werkzeugleiste des Angebots (Inhaber 19.11.2026: im Bereich Import)', w.locator('#btn-winab').count() == 0 and 'WinAB' not in w.inner_text('.ed-toolbar'))
    w.wait_for_selector('#groups:not(.no-stock) tr[data-id]:has(input[data-f="code"][value="10601"]) button.e-bst')
    w.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) button.e-bst').first.click(); w.wait_for_selector('#dlg-stock-item[open] .lottab')
    check('Karte (Leserolle mit bestand.sehen): Partien ohne EK-Spalte, auch in der Nur-Ansicht', w.locator('#dlg-stock-item .lottab tbody tr').count() == 2
          and w.locator('#dlg-stock-item th:text-is("EK-Preis")').count() == 0 and '20,00' not in w.inner_text('#dlg-stock-item .lottab'))
    w.click('#dlg-stock-item .dlg-head [data-close]'); w.wait_for_selector('#dlg-stock-item:not([open])', state='attached')
    # Bereich Import: eigene Gruppe „Export“ – auch für jemanden, der sonst nichts importieren darf (Leserolle nur mit diesem Recht)
    w.click('#vt-importe'); w.wait_for_selector('#view-importe [data-imp-export="winab"]')
    titel = w.eval_on_selector_all('#view-importe .imp-gruppe:has([data-imp-export="winab"]) :is(h2, h3)', 'hs => hs.map((h) => h.textContent)')
    check('WinAB: im Bereich Import in der Gruppe „Export“ zwei Einträge mit ihrer Woche – Entwurf und Veröffentlicht (Leserolle mit dem Recht: Menüpunkt sichtbar, keine Importe, kein „Keine Importe verfügbar“)',
          titel == ['Export', 'Export für WinAB – Entwurf (KW 46/2026)', 'Export für WinAB – Veröffentlicht (KW 45/2026)']
          and 'noch nicht veröffentlicht' in w.inner_text('.imp-art[data-export="winab_entwurf"]') and 'Kunden' in w.inner_text('.imp-art[data-export="winab"]')
          and w.text_content('.imp-art[data-export="winab"] .imp-format') == 'CSV' and w.locator('#view-importe .imp-art[data-art]').count() == 0
          and w.locator('#view-importe .ed-empty, #view-importe .imp-intro').count() == 0, w.inner_text('#view-importe'))
    w.screenshot(path=SH + '/winab-export-import.png')
    with w.expect_download() as dl:
        w.click('[data-imp-export="winab_entwurf"]')
    d = dl.value; inhalt = open(d.path(), 'rb').read()
    check('WinAB Entwurf: Datei „ImportPreise.csv“ mit den Preisen des Entwurfs (13,75 statt 12,50)', d.suggested_filename == 'ImportPreise.csv' and inhalt == soll_e.encode('ascii'), (d.suggested_filename, inhalt.decode('latin-1')))
    w.wait_for_selector('#toast.show:has-text("KW 46/2026")')
    t = w.inner_text('#toast')
    check('WinAB Entwurf: Rückmeldung nennt den Entwurf, seine Woche und dass er noch nicht veröffentlicht ist', 'aus dem Entwurf KW 46/2026' in t and 'noch nicht veröffentlicht' in t and '4 Artikel' in t, t)
    w.wait_for_selector('[data-imp-export="winab_entwurf"]:not([disabled])')
    gesperrt = []   # Zustand des Knopfs, während der Server die Datei erzeugt
    def beim_abruf(route): gesperrt.append(w.locator('[data-imp-export="winab"]').is_disabled()); route.continue_()
    w.route('**/api/?action=angebot_winab_export*', beim_abruf)
    with w.expect_download() as dl:
        w.click('[data-imp-export="winab"]')
    d = dl.value; inhalt = open(d.path(), 'rb').read()
    w.unroute('**/api/?action=angebot_winab_export*')
    check('WinAB: Datei heißt immer „ImportPreise.csv“ (ohne KW)', d.suggested_filename == 'ImportPreise.csv', d.suggested_filename)
    check('WinAB: Kopfzeile, je Nummer eine Zeile mit höchstem Preis (auch führende Null, Zusatzpreis), Sonderpreis wie beim Kunden, ohne ausgeblendete und Preis auf Anfrage, Komma, CRLF, ohne BOM',
          inhalt == soll.encode('ascii'), (inhalt.decode('latin-1'), soll))
    w.wait_for_selector('#toast.show:has-text("veröffentlichten Wochenangebot KW 45/2026")')
    w.wait_for_selector('[data-imp-export="winab"]:not([disabled])')
    check('WinAB: Knopf während des Abrufs gesperrt (kein doppelter Export), danach wieder frei', gesperrt == [True], gesperrt)
    t = w.inner_text('#toast')
    check('WinAB: Rückmeldung mit Datei, Anzahl, doppelten und ausgelassenen Artikeln – und dass der Entwurf nicht enthalten ist', 'ImportPreise.csv' in t and '4 Artikel' in t and 'KW 45/2026' in t
          and '2× doppelt' in t and '1 Artikel ohne Preis' in t and 'unveröffentlichte Änderungen im Entwurf sind nicht enthalten' in t, t)
    r = post(w, 'angebot_winab_export', {})
    check('WinAB: Schnittstelle ohne Angabe liefert wie bisher den veröffentlichten Stand – Zahlen (4 Zeilen, 2 doppelt, 1 ohne Preis), fester Dateiname', r[0] == 200 and r[1]['anzahl'] == 4
          and r[1]['doppelt'] == 2 and r[1]['ohnePreis'] == 1 and r[1]['datei'] == 'ImportPreise.csv' and r[1]['entwurf'] is False and r[1]['woche'] == 'KW 45/2026' and r[1]['csv'] == soll,
          {k: v for k, v in (r[1] or {}).items() if k != 'csv'})
    r = post(w, 'angebot_winab_export', {'entwurf': True})
    check('WinAB: Schnittstelle mit „entwurf“ liefert den gespeicherten Entwurf (KW 46/2026)', r[0] == 200 and r[1]['entwurf'] is True and r[1]['woche'] == 'KW 46/2026' and r[1]['csv'] == soll_e
          and r[1]['datei'] == 'ImportPreise.csv', {k: v for k, v in (r[1] or {}).items() if k != 'csv'})
    post(a, 'user_save', {'name': 'Nobe', 'username': 'nobe', 'role': 'editor', 'active': True, 'password': 'Ohne-Bestand-Zugang-1', 'mustChange': False, 'deny': ['bestand.sehen']})
    nb = br.new_page(viewport={'width': 1440, 'height': 950}); nb.on('pageerror', lambda x: errs.append('nobe: ' + str(x))); login(nb, 'nobe', 'Ohne-Bestand-Zugang-1')
    nr = nb.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    td = nr.locator('td.e-name'); bx = td.bounding_box(); td.click(position={'x': bx['width'] - 4, 'y': bx['height'] - 3})
    offen = nb.evaluate("() => new Promise((r) => setTimeout(() => r(document.querySelector('#dlg-stock-item').open), 400))")
    check('Karte ohne „bestand.sehen“: kein Knopf, Zeile nicht klickbar, Bestand 403', not offen and nb.locator('button.e-bst').count() == 0
          and nb.locator('tr.e-karte').count() == 0 and nb.evaluate("async () => (await fetch('../api/?action=stock')).status") == 403)
    nb.close()
    e = br.new_page(viewport={'width': 1440, 'height': 950}); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    e.click('#vt-importe'); e.wait_for_selector('#view-importe .imp-art[data-art]')
    check('WinAB: ohne Recht kein Eintrag im Import (auch nicht als Bearbeiter mit Importen) und 403', e.locator('#view-importe [data-imp-export], #btn-winab').count() == 0
          and 'Export' not in e.eval_on_selector_all('#view-importe .imp-gruppe h2', 'hs => hs.map((h) => h.textContent)') and post(e, 'angebot_winab_export', {})[0] == 403)
    anon = br.new_page(); anon.goto(B + '/admin/'); anon.wait_for_selector('#screen-auth:not([hidden])')
    check('WinAB: ohne Anmeldung 401', anon.evaluate("async () => (await fetch('../api/?action=angebot_winab_export', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})).status") == 401)
    lg = json.dumps(a.evaluate("async () => (await (await fetch('../api/?action=log')).json())"), ensure_ascii=False)
    check('WinAB: Export im Protokoll – mit Woche, der Entwurf als Entwurf gekennzeichnet', 'Wochenangebot KW 45/2026 für WinAB exportiert – 4 Artikel' in lg
          and 'Entwurf des Wochenangebots KW 46/2026 für WinAB exportiert – 4 Artikel' in lg, re.findall(r'[^"]*WinAB[^"]*', lg)[:4])
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-importe'); a.wait_for_selector('#view-importe [data-imp-export="winab"]')
    check('WinAB: Administrator sieht beide Exporte im Import, als letzte Gruppe nach den Importen',
          a.eval_on_selector_all('#view-importe .imp-gruppe h2', 'hs => hs.map((h) => h.textContent)')[-1] == 'Export' and a.locator('#view-importe .imp-intro').count() == 1
          and a.locator('#view-importe .imp-gruppe:last-child [data-imp-export]').count() == 2)
    a.screenshot(path=SH + '/winab-export-import-admin.png', full_page=True)
    # Modulzugang Angebot entzogen: trotz Recht kein Eintrag und kein Menüpunkt Import (wie bei den Importarten), Server 403
    r = post(a, 'user_save', {'id': wina_id, 'name': 'Wina', 'role': 'viewer', 'active': True, 'grant': ['angebot.winab_export'], 'deny': ['angebot.zugang']})
    w.reload(); w.wait_for_function("document.querySelector('#menu-user') && document.querySelector('#menu-user').textContent.length > 0 && !!(window.WA && window.WA.importSichtbar)")
    check('WinAB: ohne Modulzugang Angebot kein Eintrag, kein Menüpunkt Import und 403 – trotz Recht', r[0] == 200 and w.evaluate('window.WA.importSichtbar()') is False
          and not w.locator('#vt-importe').is_visible() and post(w, 'angebot_winab_export', {})[0] == 403, r[0])
    for x in (w, e, anon): x.close()
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_selector('#mhd-panel:not([hidden])'); m.wait_for_timeout(300)
    m.screenshot(path=SH + '/editor-aux-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    mb = m.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) button.e-bst').first
    mb.scroll_into_view_if_needed(); mb.click(); m.wait_for_selector('#dlg-stock-item[open] .lottab')
    m.screenshot(path=SH + '/artikelkarte-angebot-mobil.png')
    check('mobil: Artikelkarte öffnet aus dem Angebot, ohne seitliches Scrollen der Seite', m.evaluate('document.documentElement.scrollWidth') <= 390
          and m.locator('#dlg-stock-item .lottab tbody tr').count() == 2)
    m.click('#dlg-stock-item .dlg-head [data-close]'); m.wait_for_selector('#dlg-stock-item:not([open])', state='attached')
    m.click('#vt-importe'); m.wait_for_selector('#view-importe [data-imp-export="winab"]')
    mx = m.locator('[data-imp-export="winab"]'); mx.scroll_into_view_if_needed(); bx = mx.bounding_box()
    check('mobil: „Export für WinAB“ im Import ohne seitliches Scrollen, Knopf ≥ 44 px mit Namen für Vorleser', m.evaluate('document.documentElement.scrollWidth') <= 390
          and bx['width'] >= 44 and bx['height'] >= 44 and 'Export für WinAB' in (mx.get_attribute('aria-label') or ''), bx)
    m.screenshot(path=SH + '/winab-export-import-390.png')
    # Ohne offenen Entwurf ist der Arbeitsstand der veröffentlichte: „Entwurf“ liefert ihn und sagt das
    post(a, 'publish', {'model': wd, 'revision': get(a, 'draft')[1]['revision']}); r = post(a, 'angebot_winab_export', {'entwurf': True})
    check('WinAB: nach dem Veröffentlichen liefert „Entwurf“ den veröffentlichten Stand (KW 46/2026, entwurf: false)', r[0] == 200 and r[1]['entwurf'] is False and r[1]['woche'] == 'KW 46/2026'
          and r[1]['csv'] == soll_e, {k: v for k, v in (r[1] or {}).items() if k != 'csv'})
    # Ohne Artikel mit Preis: keine Datei (422)
    wm['items'] = [art(c[3], 'w5', price={'status': 'request'})]
    post(a, 'publish', {'model': wm, 'revision': get(a, 'draft')[1]['revision']}); r = post(a, 'angebot_winab_export', {})
    check('WinAB: ohne Artikel mit Preis 422', r[0] == 422 and 'kein Artikel mit Preis' in r[1].get('error', ''), r)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
