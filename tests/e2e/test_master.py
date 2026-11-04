"""Testgruppe master: Artikelstammdaten und Bezeichnungsregeln (Fleischart, Herkunft, Zustand, VK-Gruppe)."""
import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
FR = re.compile(r'(^|[^a-zäöüß])frisch(?![a-zäöüß])', re.I)

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def names(pg):
    return pg.locator('tr[data-id] input[data-f=name]').evaluate_all('els => els.map(e => e.value)')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('../api/?action=status')).json();
      const r = await fetch('../api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf}, body: JSON.stringify(b)}); return [r.status, await r.json()]; }""", [action, body])
def wait_saved(pg):
    pg.wait_for_function("document.querySelector('#save-state').className.includes('saved')", timeout=8000)
def get(pg, q):
    return pg.evaluate("async (q) => { const r = await fetch('../api/?action=' + q); return await r.json(); }", q)
def master_ent(pg, code):
    return next((x for x in get(pg, 'master')['master']['articles'] if x['code'] == code), None)
def offer_names(pg, oid, code):
    o = get(pg, f'offer&angebot={oid}&draft=1')
    return [i['name'] for i in o['offer']['items'] if i.get('code') == code], o
def until_names(pg, oid, code, soll, sek=8):   # Entwurf wird im Hintergrund gespeichert: auf den Stand warten
    import time
    ende = time.time() + sek
    while True:
        n = offer_names(pg, oid, code)[0]
        if n == soll or time.time() > ende: return n
        pg.wait_for_timeout(200)
def open_art(pg, code):
    pg.fill('#ms-q', code); pg.wait_for_selector(f'.mtab tr[data-mcode="{code}"]')
    pg.click(f'.mtab tr[data-mcode="{code}"] .m-code'); pg.wait_for_selector('#dlg-master-art[open]')
def save_art(pg):
    pg.click('#master-art-body [type=submit]'); pg.wait_for_function("!document.querySelector('#dlg-master-art').open", timeout=8000)
def wait_master(pg):
    pg.wait_for_function("document.querySelector('#ms-state') && document.querySelector('#ms-state').className.includes('saved') && /Gespeichert/.test(document.querySelector('#ms-state').textContent)", timeout=8000)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.wait_for_timeout(500); wait_saved(a)
    left = [n for n in names(a) if FR.search(n)]
    check('frisch removed from names (except frisch/gefr.)', left == ['Backe, frisch/gefr.'], left)
    row = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('10601 → "Roastbeef Fleischmeister", Zustand frisch, Herkunft 4xD', row.locator('input[data-f=name]').input_value() == 'Roastbeef Fleischmeister' and row.locator('select[data-f=condition]').input_value() == 'frisch' and row.locator('input[data-f=origin]').input_value() == '4xD', (row.locator('input[data-f=name]').input_value(), row.locator('input[data-f=origin]').input_value()))
    r10701 = a.locator('tr[data-id]:has(input[data-f="code"][value="10701"])').first
    check('10701 → "Entrecote Fleischmeister" / 4xD', r10701.locator('input[data-f=name]').input_value() == 'Entrecote Fleischmeister' and r10701.locator('input[data-f=origin]').input_value() == '4xD')
    origins = set(a.locator('tr[data-id] input[data-f=origin]').evaluate_all('els => els.map(e => e.value)'))
    check('origins are codes only', origins <= {'', '4xD', '3xD', 'D', 'EG', 'NZ', 'ARG', 'UY', 'PY', 'BR', 'AUS', 'IRL', 'DK', 'ES', 'Südamerika'}, origins)
    r_nz = a.locator('tr[data-id]:has(input[data-f="code"][value="10674"])').first
    check('Neuseeland → NZ, no brand outside Fleischmeister', r_nz.locator('input[data-f=origin]').input_value() == 'NZ' and 'Fleischmeister' not in r_nz.locator('input[data-f=name]').input_value())
    check('cleanup counts as unpublished change', 'noch nicht veröffentlicht' in a.inner_text('#save-state'))
    # manuelle Eingabe
    ni = row.locator('input[data-f=name]'); ni.fill('Roastbeef Fleischmeister frisch'); ni.press('Tab'); a.wait_for_timeout(300)
    check('typed "frisch" is stripped', a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f=name]').first.input_value() == 'Roastbeef Fleischmeister' and 'Zustand' in a.inner_text('#toast'))
    wait_saved(a)
    # Stammdaten: automatisch angelegt
    a.click('#vt-master'); a.wait_for_selector('.mtab'); wait_master(a)
    n = a.locator('.mtab tbody tr').count(); check('master seeded from offer (263 unique codes)', n == 263, n)
    check('dup-code hint', '6 Artikelnummern' in a.inner_text('#view-master'))
    check('all ✓ after seeding', a.locator('.mtab .m-diff').count() == 0 and a.locator('[data-ma=apply-all]').is_disabled())
    a.screenshot(path=SH + '/master.png')
    # Liste nur zum Ansehen, Klick auf den Artikel öffnet das Pop-up (Auftrag des Inhabers 03.11.2026)
    check('list read-only (no inputs in rows)', a.locator('.mtab tbody input, .mtab tbody select').count() == 0)
    open_art(a, '10601')
    check('popup: Originalbezeichnung, Basiswert und je Kundenangebot ein Feld', a.locator('#ma-orig').count() == 1 and a.input_value('#master-art-body [name=name]') == 'Roastbeef Fleischmeister'
          and a.locator('#master-art-body [name=oname]').count() == 4 and a.get_attribute('#master-art-body [name=oname][data-on="edeka"]', 'placeholder') == 'Roastbeef Fleischmeister')
    a.fill('#master-art-body [name=name]', 'Roastbeef Färse Fleischmeister frisch')
    check('popup: Platzhalter folgt dem Basiswert', a.get_attribute('#master-art-body [name=oname][data-on="edeka"]', 'placeholder') == 'Roastbeef Färse Fleischmeister frisch')
    a.fill('#master-art-body [name=oname][data-on="edeka"]', 'Roastbeef Edeka-Spezial')
    a.screenshot(path=SH + '/master-popup.png')
    save_art(a); wait_master(a)
    ent = master_ent(a, '10601')
    check('popup: Basiswert ohne „frisch“, Bezeichnung je Angebot gespeichert', ent['name'] == 'Roastbeef Färse Fleischmeister' and ent.get('namen') == {'edeka': 'Roastbeef Edeka-Spezial'} and ent['condition'] == 'frisch', ent)
    a.wait_for_selector('.mtab tr[data-mcode="10601"] .m-ok')
    check('popup: Änderung in den Entwurf übernommen (✓, Hinweis)', 'Entwurf' in a.inner_text('#toast') and a.locator('.mtab tr[data-mcode="10601"] .m-eigen').count() == 1, a.inner_text('#toast'))
    a.fill('#ms-q', 'roastbeef'); a.wait_for_function("document.querySelectorAll('.mtab tr[data-mcode]').length > 3"); a.screenshot(path=SH + '/master-liste.png')
    a.click('#vt-edit'); wait_saved(a)
    check('draft item renamed from master', a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f=name]').first.input_value() == 'Roastbeef Färse Fleischmeister')
    # je Angebot aufgelöst (Server, offer_resolve) – jedes Angebot für sich
    ed, ro_ = offer_names(a, 'edeka', '10601'); st_, ro2 = offer_names(a, 'std', '10601'); cc, _ = offer_names(a, 'chefs-culinar', '10601')
    check('offer_resolve: eigene Bezeichnung nur im Angebot Edeka', ed == ['Roastbeef Edeka-Spezial'] and st_ == ['Roastbeef Färse Fleischmeister'] and cc == ['Roastbeef Färse Fleischmeister'], (ed, st_, cc))
    check('offer_resolve: Bezeichnungen je Angebot nie ausgeliefert', '"namen"' not in json.dumps(ro_) and '"namen"' not in json.dumps(ro2))
    # direkt im Angebot: Bezeichnung im Kundenangebot ändern (nur dort)
    a.click('#offer-bar [data-offer="chefs-culinar"]'); a.wait_for_selector('#offer-bar [data-offer="chefs-culinar"][aria-selected="true"]')
    rcc = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    check('Kundenangebot: Zeile zeigt den Basiswert, Feld für dieses Angebot', rcc.locator('input[data-f=oname]').input_value() == 'Roastbeef Färse Fleischmeister' and rcc.locator('.e-eigen').count() == 0)
    rcc.locator('input[data-f=oname]').fill('Roastbeef für Chefs'); rcc.locator('input[data-f=oname]').press('Tab'); wait_saved(a)
    rcc = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    cc, _ = offer_names(a, 'chefs-culinar', '10601'); st_, _ = offer_names(a, 'std', '10601'); ed, _ = offer_names(a, 'edeka', '10601')
    check('Kundenangebot: eigene Bezeichnung nur dort', cc == ['Roastbeef für Chefs'] and st_ == ['Roastbeef Färse Fleischmeister'] and ed == ['Roastbeef Edeka-Spezial'] and rcc.locator('.e-eigen').count() == 1, (cc, st_, ed))
    a.screenshot(path=SH + '/master-kundenangebot.png')
    rcc.locator('input[data-f=oname]').fill(''); rcc.locator('input[data-f=oname]').press('Tab'); wait_saved(a)
    rcc = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"])').first
    cc, _ = offer_names(a, 'chefs-culinar', '10601')
    check('Kundenangebot: leeren = wieder Basiswert', cc == ['Roastbeef Färse Fleischmeister'] and rcc.locator('input[data-f=oname]').input_value() == 'Roastbeef Färse Fleischmeister' and rcc.locator('.e-eigen').count() == 0, cc)
    # Artikel-Dialog: Feld je Angebot
    rcc.locator('[data-act=item]').click(); a.wait_for_selector('#dlg-item[open]')
    check('Artikel-Dialog: Basiswert und Felder je Kundenangebot', a.locator('#item-body [name=oname]').count() == 4 and a.input_value('#item-body [name=oname][data-on="edeka"]') == 'Roastbeef Edeka-Spezial')
    a.fill('#item-body [name=oname][data-on="bela"]', 'Roastbeef Bela'); a.press('#item-body [name=oname][data-on="bela"]', 'Tab'); wait_saved(a)
    bl, _ = offer_names(a, 'bela', '10601')
    check('Artikel-Dialog: Bezeichnung in Bela', bl == ['Roastbeef Bela'], bl)
    a.keyboard.press('Escape'); a.wait_for_function("!document.querySelector('#dlg-item').open")
    a.click('#offer-bar [data-offer="std"]'); a.wait_for_selector('#offer-bar [data-offer="std"][aria-selected="true"]')
    # Entwurf weicht ab (Bela) → in den Stammdaten „abweichend“ → übernehmen
    a.click('#vt-master'); a.fill('#ms-q', '10601'); a.wait_for_selector('.mtab tr[data-mcode="10601"] .m-diff')
    check('offer status abweichend', a.locator('.mtab tr[data-mcode="10601"] .m-diff').count() == 1)
    a.click('.mtab tr[data-mcode="10601"] button.m-diff'); a.wait_for_selector('.mtab tr[data-mcode="10601"] .m-ok')
    bl = until_names(a, 'bela', '10601', ['Roastbeef Färse Fleischmeister'])
    check('apply single → ✓ (Stammdaten gelten wieder)', bl == ['Roastbeef Färse Fleischmeister'], bl)
    a.click('#vt-edit'); wait_saved(a)
    # Neuer Stammsatz mit Vorschlag aus Bestand (Bestand importieren)
    master = json.load(open(FIX + '/bestand/master_stock.json'))
    arts = [{'code': x[0].lstrip('0') or '0', 'name': x[1], 'kg': x[2], 'mhd': x[3], 'mhdKg': x[4], 'lots': []} for x in master if x[2] and x[2] > 0]
    post(a, 'stock_import', {'date': '2026-10-16', 'source': 't', 'articles': arts})
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-master'); a.wait_for_selector('.mtab')
    a.click('[data-ma=new]'); a.wait_for_selector('#dlg-master-new[open]')
    a.fill('#master-new-body [name=code]', '11872'); a.press('#master-new-body [name=code]', 'Tab'); a.wait_for_timeout(200)
    check('new: name prefilled from stock without frisch', a.input_value('#master-new-body [name=name]') == 'Rinderfett, EG', a.input_value('#master-new-body [name=name]'))
    a.click('#master-new-body [type=submit]'); wait_master(a)
    try: a.wait_for_selector('.mtab tr[data-mcode="11872"]', timeout=8000)   # Liste wird nach dem Speichern neu gezeichnet
    except Exception: pass
    check('new master row', a.locator('.mtab tr[data-mcode="11872"]').count() == 1)
    open_art(a, '11872')
    check('popup: Bezeichnung der Warenwirtschaft aus der Bestandsliste (noch ohne Artikelimport)', a.inner_text('#ma-orig') == 'Rinderfett, EG, frisch' and 'Bestandsliste' in a.inner_text('#master-art-body'), a.inner_text('#ma-orig'))
    check('Liste: Spalte Bezeichnung (Warenwirtschaft) mit Herkunft „Bestandsliste“', 'Rinderfett, EG, frisch' in a.inner_text('.mtab tr[data-mcode="11872"] .m-orig') and 'Bestandsliste' in a.inner_text('.mtab tr[data-mcode="11872"] .m-orig'))
    a.click('#master-art-body [data-ma-del]'); a.click('#dlg-confirm [data-v="1"]'); wait_master(a)
    try: a.wait_for_function("!document.querySelector('.mtab tr[data-mcode=\"11872\"]')", timeout=8000)   # Liste wird nach dem Speichern neu gezeichnet
    except Exception: pass
    check('master row deleted', a.locator('.mtab tr[data-mcode="11872"]').count() == 0)
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) tr[data-id]')
    # Artikel-Dialog → als Stammdaten speichern
    r10823 = a.locator('tr[data-id]:has(input[data-f="code"][value="10823"])').first
    r10823.locator('select[data-f=condition]').select_option('dry-aged'); a.wait_for_timeout(300)
    r10823.locator('[data-act=item]').click(); a.wait_for_selector('#dlg-item[open]')
    a.click('#item-body [data-ia=to-master]'); a.wait_for_timeout(1200)
    check('item saved to master', 'Stammdaten für 10823' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.keyboard.press('Escape')
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-master'); a.wait_for_selector('.mtab'); a.fill('#ms-q', '10823'); a.wait_for_selector('.mtab tr[data-mcode="10823"]')
    check('master persisted after reload', master_ent(a, '10823')['condition'] == 'dry-aged' and 'Dry' in a.inner_text('.mtab tr[data-mcode="10823"] .m-cond'))
    # Server prüft die Bezeichnungen je Angebot (Format, leer, Wochenangebot) – Liste per API
    m_ = get(a, 'master')['master']
    arts_ = [dict(x, namen={'std': 'nie', 'edeka': '', 'Böse ID': 'x', 'bela': '  Roastbeef   Bela  ', 'chefs-culinar': 'y' * 250}) if x['code'] == '10701' else x for x in m_['articles']]
    r = post(a, 'master_save', {'rev': m_['rev'], 'articles': arts_})
    e_ = master_ent(a, '10701')
    check('master_save: nur gültige Bezeichnungen je Angebot (ohne Wochenangebot, leere, ungültige IDs; gekürzt)', r[0] == 200 and e_.get('namen') == {'bela': 'Roastbeef Bela', 'chefs-culinar': 'y' * 200}, (r[0], e_.get('namen')))
    a.reload(); a.wait_for_selector('tr[data-id]')
    # Protokoll
    a.click('#vt-log'); a.wait_for_selector('.ltab'); t = a.inner_text('#log-list')
    check('log: cleanup + Stammdaten', 'vereinheitlicht' in t and 'Stammdaten bearbeitet' in t)
    # Nachtmodus: Pop-up mit eigener Bezeichnung (Farben aus den Variablen)
    a.click('#vt-master'); a.wait_for_selector('.mtab')
    a.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    open_art(a, '10701'); a.screenshot(path=SH + '/master-popup-dunkel.png'); a.keyboard.press('Escape')
    a.evaluate("document.documentElement.removeAttribute('data-theme')")
    # Nur ansehen
    post(a, 'user_save', {'name': 'Vera', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    v = br.new_context(viewport={'width': 1440, 'height': 950}).new_page(); v.on('pageerror', lambda e: errs.append('v: ' + str(e)))
    login(v, 'vera', 'Leserin-Zugang-1'); v.click('#vt-master'); v.wait_for_selector('.mtab')
    open_art(v, '10601')
    check('viewer: master read-only (Pop-up ohne Speichern)', v.locator('#master-art-body [name=name]').is_disabled() and v.locator('#master-art-body [type=submit]').count() == 0
          and v.locator('#master-art-body [data-ma-del]').count() == 0 and v.locator('[data-ma=new]').count() == 0)
    v.keyboard.press('Escape')
    r = post(v, 'master_save', {'rev': 99, 'articles': []}); check('viewer cannot save master (403)', r[0] == 403, r[0])
    # Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1'); m.click('#vt-master'); m.wait_for_selector('.mtab'); m.wait_for_timeout(200)
    m.screenshot(path=SH + '/master-mobile.png')
    open_art(m, '10601'); m.screenshot(path=SH + '/master-popup-mobile.png')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile popup no h-scroll', sw <= 390, sw)
    m.keyboard.press('Escape')
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
