"""Mehrere Angebote: Kundenangebote mit eigenen Preisen, eigene Artikelliste je Angebot (Artikel hinzufügen wie im
Einzelangebot, entfernen nur im gewählten Angebot, Umstellung „folgt dem Wochenangebot“ → eigene Liste), Verwaltung,
Übernahme, Excel-Import ohne Verlust der Kundenangebote, Veröffentlichen, Auslieferung nur an Berechtigte (Regel:
Kundenpreise nie öffentlich)."""
import sys
from umgebung import shot
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
from umgebung import SH, XL44, storage_raw, storage_write
from testdaten import de, preis
B = BASE
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('/api/?action=status')).json();
      const r = await fetch('/api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, body: JSON.stringify(b)}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, body])
def get(pg, q):
    return pg.evaluate("""async (q) => { const r = await fetch('/api/?action=' + q); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", q)
def bestaetigt(pg, toast_text, timeout=15000):
    # Löschen braucht eine Bestätigung jünger als 5 Minuten (Anmeldung zählt). Läuft der Test unter Last länger, fragt
    # die Oberfläche nach dem Passwort – dann bestätigen, statt am Zeitfenster zu scheitern.
    sel = f'#toast.show:has-text("{toast_text}")'
    pg.wait_for_function("""(t) => document.querySelector('#dlg-reauth[open]')
        || ((x) => x && x.classList.contains('show') && x.textContent.includes(t))(document.querySelector('#toast'))""", arg=toast_text, timeout=timeout)
    if pg.locator('#dlg-reauth[open]').count():
        pg.fill('#reauth-password', 'Sicheres-Passwort-1'); pg.click('#reauth-submit')
        pg.wait_for_selector(sel, timeout=timeout)
def post_bestaetigt(pg, action, body):
    r = post(pg, action, body)
    if r[0] == 403 and (r[1] or {}).get('code') == 'confirmation_required':
        post(pg, 'reauth', {'password': 'Sicheres-Passwort-1'}); r = post(pg, action, body)
    return r
def row(pg, code): return pg.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])').first
def wait_saved(pg): pg.wait_for_function("document.querySelector('#save-state').className.includes('saved') || /Keine Änderungen/.test(document.querySelector('#save-state').textContent)", timeout=8000)
def tab(pg, label): return pg.locator(f'#offer-bar [data-offer]:has-text("{label}")').first
def zahl(pg, label): return int(tab(pg, label).locator('.ob-z').inner_text().replace('.', ''))
def codes(pg): return pg.locator('#groups tr[data-id] input[data-f=code]').evaluate_all('e => e.map(x => x.value)')
def hinzufuegen(pg, q, preise):
    """„Artikel hinzufügen“: Suche, markieren, Preis je Artikel, übernehmen"""
    pg.click('#btn-add-art'); pg.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    pg.fill('#ezp-q', q)
    for code, pr in preise.items():
        pg.wait_for_selector(f'#ezp-list tr[data-code="{code}"]'); pg.click(f'#ezp-list tr[data-code="{code}"] .ezp-n')
        if pr is not None: pg.fill(f'#ezp-list [data-preis="{code}"]', pr)
    pg.click('#ezp-ok'); pg.wait_for_selector('#dlg-ez-pick', state='hidden')
def item(offer, code): return next((i for i in offer['items'] if i['code'] == code), None)

P10601, P10823 = preis('10601'), preis('10823')

with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.wait_for_timeout(600); wait_saved(a)
    # sauberer Ausgangspunkt
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]'); a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    ids0 = a.locator('#offer-bar [data-offer]').evaluate_all('e => e.map(x => x.dataset.offer)')
    check('Angebotsliste links: Wochenangebot + 4 Kundenangebote', ids0 == ['std', 'chefs-culinar', 'handelshof-efs', 'edeka', 'bela'], ids0)
    check('standard selected by default', a.get_attribute('#offer-bar [data-offer="std"]', 'aria-selected') == 'true')
    n_std = len(codes(a))
    check('Liste zeigt Artikelzahl je Angebot; bestehende Angebote folgen dem Wochenangebot', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std
          and 'folgt dem Wochenangebot' in tab(a, 'Edeka').inner_text(), (zahl(a, 'Wochenangebot'), zahl(a, 'Edeka'), n_std))
    check('Leisten „Kurzes MHD“/„Bestand ohne Preis“ zugeklappt (ohne Bestand: ausgeblendet)', a.locator('#ed-panels .np-card.open').count() == 0)
    # Edeka: eigene Preise
    tab(a, 'Edeka').click(); a.wait_for_timeout(200)
    th = a.locator('.gcard').first.locator('thead').inner_text()
    check('price header names offer', 'Edeka' in th, re.sub(r'\s+', ' ', th))
    vi = row(a, '10601').locator('input[data-f=vprice]')
    check('empty variant shows standard as placeholder', vi.input_value() == '' and vi.get_attribute('placeholder') == 'Std. ' + de(P10601), vi.get_attribute('placeholder'))
    vi.fill('22'); vi.press('Tab'); wait_saved(a)
    check('own price saved + formatted', row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00')
    check('row marked as price change', 'is-price' in row(a, '10601').get_attribute('class'))
    check('changes bar counts offer price', '1 Angebotspreis geändert' in re.sub(r'\s+', ' ', a.inner_text('#changes')), a.inner_text('#changes'))
    check('Kopf: Angebot „folgt dem Wochenangebot“ mit Hinweis zur Umstellung', 'Folgt dem Wochenangebot' in a.inner_text('#offer-head') and a.locator('#offer-head [data-ob=umstellen]').count() == 1)
    row(a, '10823').locator('[data-act=remove]').click(); wait_saved(a)
    check('✕ entfernt nur aus diesem Angebot', row(a, '10823').count() == 0 and zahl(a, 'Edeka') == n_std - 1 and zahl(a, 'Wochenangebot') == n_std)
    bad = row(a, '10701').locator('input[data-f=vprice]'); bad.fill('abc'); bad.press('Tab'); a.wait_for_timeout(200)
    check('invalid offer price rejected', 'invalid' in bad.get_attribute('class') and 'nicht lesbar' in a.inner_text('#toast'))
    bad.fill(''); bad.press('Tab'); wait_saved(a)
    a.screenshot(path=SH + '/angebote-edeka.png')
    # Standard unverändert
    tab(a, 'Wochenangebot').click(); a.wait_for_timeout(200)
    check('standard price untouched', row(a, '10601').locator('input[data-f=price]').input_value() == de(P10601))
    # Veröffentlichen mit Einzel-Rücknahme
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    t = a.inner_text('#publish-body').lower()
    check('publish dialog lists offer prices', 'angebotspreise (2)' in t and 'edeka' in t, t[:300])
    a.click('#publish-body li:has-text("10823") [data-rv=variant]')
    a.wait_for_selector('#dlg-confirm[open]'); check('confirm names offer', 'Edeka' in a.inner_text('#dlg-confirm')); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('revert removes hidden flag', 'angebotspreise (1)' in a.inner_text('#publish-body').lower())
    a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    # Auslieferung
    pub = br.new_page()
    pub.goto(B + '/'); pub.wait_for_selector('tr.row')
    r = get(pub, 'offer')
    raw = json.dumps(r[1])
    check('public offer: no customer prices at all', r[0] == 200 and '"variants"' not in raw and item(r[1]['offer'], '10601')['price']['value'] == P10601, item(r[1]['offer'], '10601')['price'])
    r = get(pub, 'offer&angebot=edeka'); check('customer offer needs login (401)', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=edeka&draft=1'); check('customer draft needs login', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=../x'); check('invalid offer id rejected', r[0] in (401, 404), r[0])
    pub.goto(B + '/?angebot=edeka'); pub.wait_for_timeout(1200)
    check('frontend without login: hint, no prices', 'nur nach Anmeldung' in pub.inner_text('body') and pub.locator('tr.row').count() == 0)
    r = get(a, 'offer&angebot=edeka')
    o = r[1]['offer'] if r[0] == 200 else {'items': [], 'meta': {}}
    check('customer offer resolved for logged-in user', r[0] == 200 and item(o, '10601')['price'] == {'status': 'value', 'value': 22} and o['meta'].get('offerName') == 'Wochenangebot Edeka' and '"variants"' not in json.dumps(o), item(o, '10601'))
    check('fallback: other items show standard price', item(o, '10823') and item(o, '10823')['price']['value'] == P10823)
    f = actx.new_page(); f.goto(B + '/?angebot=edeka'); f.wait_for_selector('tr.row')
    check('frontend shows offer name + own price', 'Wochenangebot Edeka' in f.inner_text('#topbar h1') and '22,00' in f.inner_text('tr.row >> nth=0'), f.inner_text('#topbar h1'))
    f.screenshot(path=SH + '/angebote-frontend.png')
    # Neues Angebot: eigene Artikelliste (Voreinstellung)
    a.click('[data-ob=manage]'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    check('Angebote verwalten führt zu Stammdaten → Angebote', a.get_attribute('#vt-angebote', 'aria-selected') == 'true')
    a.click('[data-ofa=add]'); a.locator('#view-angebote [data-of=name]').last.fill('Wochenangebot Metro')
    check('neues Angebot: Voreinstellung „Eigene Artikelliste“', a.locator('#view-angebote tr[data-oi]').last.locator('[data-of=fallback]').input_value() == 'hidden')
    a.click('[data-ofa=save]'); a.wait_for_selector('#toast.show:has-text("Angebote gespeichert")', timeout=8000)
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) #offer-bar:not([hidden])')
    check('new offer tab appears', tab(a, 'Metro').count() == 1)
    tab(a, 'Metro').click(); a.wait_for_selector('#groups .ed-empty')
    check('eigene Artikelliste: leer, Hinweis und „Artikel hinzufügen“', 'Noch keine Artikel in diesem Angebot' in a.inner_text('#groups') and zahl(a, 'Metro') == 0
          and 'Eigene Artikelliste' in a.inner_text('#offer-head'))
    a.screenshot(path=SH + '/angebote-leer.png')
    # Artikel hinzufügen (Fenster wie im Einzelangebot): Preis je Artikel, Gruppe automatisch
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    check('Fenster: Ziel-Angebot im Kopf, Preisspalte „Preis hier“', 'Metro' in a.inner_text('#ez-pick-body .ezp-head') and a.locator('#ezp-angebot').count() == 1)
    a.fill('#ezp-q', '10601'); a.wait_for_selector('#ezp-list tr[data-code="10601"]'); a.click('#ezp-list tr[data-code="10601"] .ezp-n')
    check('markierter Artikel: Preisfeld mit Wochenpreis vorbelegt, Zielgruppe im Fuß', a.input_value('#ezp-list [data-preis="10601"]') == de(P10601) and 'landet in:' in a.inner_text('#ezp-anz'), a.inner_text('#ezp-anz'))
    a.fill('#ezp-list [data-preis="10601"]', '19x'); a.click('#ezp-ok'); a.wait_for_selector('#ezp-anz .ezp-err')
    check('unlesbarer Preis: Fenster bleibt offen mit Hinweis', 'nicht lesbar' in a.inner_text('#ezp-anz') and a.locator('#dlg-ez-pick[open]').count() == 1)
    a.fill('#ezp-list [data-preis="10601"]', '19,5')
    a.screenshot(path=SH + '/angebote-hinzufuegen.png')
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); wait_saved(a)
    check('übernommen: nur dieser Artikel mit eigenem Preis', codes(a) == ['10601'] and row(a, '10601').locator('input[data-f=vprice]').input_value() == '19,50' and zahl(a, 'Metro') == 1, codes(a))
    check('andere Angebote unverändert', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std)
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q'); a.fill('#ezp-q', '10601'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    check('bereits enthaltener Artikel nicht erneut wählbar', a.is_disabled('#ezp-list [data-sel="10601"]') and 'schon enthalten' in a.inner_text('#ezp-list tr[data-code="10601"]'))
    # Freie Position nur in diesem Angebot
    a.click('#dlg-ez-pick [data-pick-extra="frei"]'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    a.wait_for_function("document.activeElement && document.activeElement.dataset.f === 'name'")
    a.keyboard.type('Metro-Spezial Testartikel'); a.keyboard.press('Tab')
    neu = a.locator('tr[data-id]:has(input[data-f=name][value="Metro-Spezial Testartikel"])')
    neu.locator('input[data-f=vprice]').fill('8,8'); neu.locator('input[data-f=vprice]').press('Tab'); wait_saved(a)
    check('freie Position im Angebot', zahl(a, 'Metro') == 2 and neu.locator('input[data-f=vprice]').input_value() == '8,80')
    check('… erscheint in keinem anderen Angebot', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std and zahl(a, 'Bela') == n_std)
    vi = neu.locator('input[data-f=vprice]'); vi.fill(''); vi.press('Tab'); a.wait_for_timeout(200)
    check('eigene Liste: leerer Preis wird nicht übernommen (Hinweis auf ✕)', vi.input_value() == '8,80' and '✕' in a.inner_text('#toast'))
    # ✕: Artikel, der nur hier steht, wird gelöscht; Rückgängig holt ihn zurück
    neu.locator('[data-act=remove]').click(); a.wait_for_selector('#toast.show:has-text("gelöscht")')
    check('✕ in eigener Liste: nur hier → gelöscht', zahl(a, 'Metro') == 1 and 'in keinem anderen Angebot' in a.inner_text('#toast'))
    a.click('#btn-undo'); a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 2"); wait_saved(a)
    check('Rückgängig stellt die Position wieder her', zahl(a, 'Metro') == 2)
    # Vorschau des gewählten Kundenangebots (Entwurf, noch nicht veröffentlicht) im Fenster; Angebot umschaltbar
    a.click('#btn-preview'); a.wait_for_selector('#dlg-vorschau[open] #pv-stage:not(.laden)', timeout=15000)
    fr = a.frame_locator('#pv-frame')
    fr.locator('#list').get_by_text('Metro-Spezial').first.wait_for(timeout=10000)
    mid = a.input_value('#pv-offer')
    check('Vorschau zeigt das gewählte Kundenangebot (Entwurf)', mid != 'std' and f'&angebot={mid}' in (a.get_attribute('#pv-frame', 'src') or '') and '19,50' in fr.locator('#list').inner_text(), mid)
    a.select_option('#pv-offer', 'std'); a.wait_for_selector('#pv-stage:not(.laden)')
    fr.locator('#list').get_by_text(de(P10601)).first.wait_for(timeout=10000)
    check('… umgeschaltet aufs Wochenangebot: ohne die Metro-Position', 'Metro-Spezial' not in fr.locator('#list').inner_text())
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-vorschau', state='hidden')
    # Umstellen „folgt dem Wochenangebot“ → eigene Artikelliste (Edeka hat einen eigenen Preis: 10601 = 22,00)
    tab(a, 'Edeka').click(); a.wait_for_selector('#offer-head [data-ob=umstellen]')
    a.click('#offer-head [data-ob=umstellen]'); a.wait_for_selector('#dlg-confirm[open]')
    t = a.inner_text('#dlg-confirm')
    check('Umstellung: Hinweis „sofort“ und Zahl der Artikel mit eigenem Preis', 'sofort' in t and '1 Artikel' in t, t)
    a.click('#dlg-confirm [data-v="1"]'); a.wait_for_selector('#toast.show:has-text("eigene Artikelliste")')
    check('Edeka: eigene Artikelliste mit dem einen eigenen Artikel', codes(a) == ['10601'] and zahl(a, 'Edeka') == 1 and 'Eigene Artikelliste' in a.inner_text('#offer-head')
          and next(o for o in get(a, 'offers')[1]['offers'] if o['id'] == 'edeka')['fallback'] == 'hidden', codes(a))
    r = get(a, 'offer&angebot=edeka')
    check('… Kunden sehen sofort nur noch diesen Artikel', r[0] == 200 and [i['code'] for i in r[1]['offer']['items']] == ['10601'], [i['code'] for i in r[1]['offer']['items']][:5] if r[0] == 200 else r)
    # Aus anderem Angebot übernehmen: Wochenangebot −5 % in die eigene Liste
    a.click('#offer-head [data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open]')
    a.select_option('#offer-copy-body [name=src]', 'std'); a.fill('#offer-copy-body [name=pct]', '-5'); a.click('#offer-copy-body [type=submit]'); wait_saved(a)
    exp = round(round(P10823 * 0.95 / 0.05) * 0.05, 2)
    check('Übernahme füllt die eigene Liste, eigener Preis bleibt', zahl(a, 'Edeka') > 100 and row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00'
          and row(a, '10823').locator('input[data-f=vprice]').input_value() == de(exp), (zahl(a, 'Edeka'), de(exp)))
    check('… Wochenangebot und Metro unverändert', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Metro') == 2)
    a.click('#btn-undo'); a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 1"); wait_saved(a)
    check('Übernahme mit Rückgängig zurückgenommen', zahl(a, 'Edeka') == 1)
    # Server: Gruppe mit VK-Gruppe bleibt im Entwurf, geht nie an Kunden; neue Angebote ohne Regel = eigene Liste
    d = get(a, 'draft')[1]; mdl = d['draft']
    mdl['groups'][0]['vk'] = '1600'; mdl['groups'][1]['vk'] = '<b>'
    r = post(a, 'save_draft', {'model': mdl, 'revision': d['revision']})
    d2 = get(a, 'draft')[1]['draft']
    check('Gruppe: VK-Gruppe gespeichert, ungültige verworfen', r[0] == 200 and d2['groups'][0].get('vk') == '1600' and 'vk' not in d2['groups'][1], d2['groups'][:2])
    r = get(a, 'offer&angebot=edeka&draft=1')
    check('… nicht in der Auslieferung (Vorschau Kundenangebot)', r[0] == 200 and '"vk"' not in json.dumps(r[1]), r[0])
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) #offer-bar:not([hidden])'); wait_saved(a)
    r = get(a, 'angebot_artikel')
    check('Artikel für „Artikel hinzufügen“: Stammdaten/Wochenangebot, ohne Einkaufspreise', r[0] == 200 and any(x['code'] == '10601' for x in r[1]['articles']) and r[1].get('ek') is False, r[0])
    # Preise übernehmen in Bela (+10 %, auf 0,05)
    tab(a, 'Bela').click(); a.click('[data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open]')
    a.fill('#offer-copy-body [name=pct]', '10'); a.click('#offer-copy-body [type=submit]'); wait_saved(a)
    exp = round(round(P10823 * 1.1 / 0.05) * 0.05, 2)
    check('copy with surcharge + rounding', row(a, '10823').locator('input[data-f=vprice]').input_value() == de(exp), (row(a, '10823').locator('input[data-f=vprice]').input_value(), de(exp)))
    check('copy toast', 'übernommen' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.click('#btn-undo'); a.wait_for_timeout(300)
    check('copy undoable', row(a, '10823').locator('input[data-f=vprice]').input_value() == '')
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]'); a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    ids = {x['id']: x['name'] for x in get(a, 'offers')[1]['offers']}
    metro = next(k for k, v in ids.items() if 'Metro' in v)
    r = get(a, f'offer&angebot={metro}')
    mo = r[1]['offer']['items'] if r[0] == 200 else []
    check('eigene Artikelliste: nur ihre Artikel ausgeliefert', sorted(i['code'] or '' for i in mo) == ['', '10601'] and any(i['name'].startswith('Metro-Spezial') for i in mo)
          and next(i for i in mo if i['code'] == '10601')['price'] == {'status': 'value', 'value': 19.5}, [(i['code'], i['name']) for i in mo] or r)
    pubo = get(a, 'offer')[1]['offer']
    check('… freie Position nicht im Wochenangebot', not any(i['name'].startswith('Metro-Spezial') for i in pubo['items']))
    r = get(a, 'offer&angebot=bela')
    check('… nicht in Angeboten, die dem Wochenangebot folgen', r[0] == 200 and not any(i['name'].startswith('Metro-Spezial') for i in r[1]['offer']['items']))
    # Vorwoche je Angebot
    tab(a, 'Edeka').click(); a.fill('#m-week', str(int(a.input_value('#m-week')) + 1)); a.press('#m-week', 'Tab'); a.wait_for_timeout(1500)
    pc = row(a, '10601').locator('td.e-prev').inner_text().strip()
    check('Vorwoche shows previous offer price', pc.startswith('22,00'), pc)
    a.fill('#m-week', str(int(a.input_value('#m-week')) - 1)); a.press('#m-week', 'Tab'); wait_saved(a)
    # Excel-Import ersetzt nur das Wochenangebot: Kundenangebote behalten Artikel und Preise
    tab(a, 'Wochenangebot').click(); a.wait_for_timeout(200)
    with a.expect_file_chooser() as fc: a.click('#btn-import')
    fc.value.set_files(XL44); a.wait_for_selector('#dlg-import [data-ia="apply"]')
    check('Import-Vorschau: Kundenangebote bleiben erhalten', 'Kundenangebote bleiben erhalten' in a.inner_text('#dlg-import'), a.inner_text('#dlg-import')[:300])
    a.click('#dlg-import [data-ia="apply"]'); wait_saved(a)
    check('nach dem Import: Metro und Edeka behalten ihre Artikel', zahl(a, 'Metro') == 2 and zahl(a, 'Edeka') == 1 and a.input_value('#m-week') == '44', (zahl(a, 'Metro'), zahl(a, 'Edeka')))
    tab(a, 'Edeka').click(); a.wait_for_timeout(200)
    check('… eigener Preis wandert auf den importierten Artikel', row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00')
    tab(a, 'Metro').click(); a.wait_for_timeout(200)
    check('… Position nur im Kundenangebot bleibt', any(x.startswith('Metro-Spezial') for x in a.locator('#groups input[data-f=name]').evaluate_all('e => e.map(x => x.value)')))
    a.click('#btn-undo'); wait_saved(a)
    check('Import mit Rückgängig zurückgenommen', a.input_value('#m-week') != '44')
    # Rechte
    post(a, 'user_save', {'name': 'Eddi', 'username': 'eddi', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    post(a, 'user_save', {'name': 'Vera', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    e = br.new_page(viewport={'width': 1440, 'height': 950}); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    cur = get(e, 'offers')[1]
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': [o for o in cur['offers'] if o['id'] != metro]})
    check('editor cannot delete offers (403)', r[0] == 403, r)
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': 'test', 'name': 'Wochenangebot', 'fallback': 'standard'}]})
    check('duplicate/reserved name rejected', r[0] == 422, r)
    r = post(e, 'offers_save', {'rev': cur['rev'] - 1, 'offers': cur['offers']})
    check('stale revision rejected (409)', r[0] == 409, r[0])
    v = br.new_page(viewport={'width': 1440, 'height': 950}); login(v, 'vera', 'Leserin-Zugang-1')
    tv = v.locator('#offer-bar [data-offer]:has-text("Edeka")').first; tv.click(); v.wait_for_timeout(200)
    check('viewer: can switch, inputs locked, no manage', v.locator('tr[data-id] input[data-f=vprice]').first.is_disabled() and v.locator('[data-ob=manage]').count() == 0)
    check('viewer: kein „Artikel hinzufügen“, keine Artikelauswahl (403)', not v.locator('#btn-add-art').is_visible() and get(v, 'angebot_artikel')[0] == 403
          and not v.locator('tr[data-id] [data-act=remove]').first.is_visible())
    check('editor: Artikelauswahl erlaubt', get(e, 'angebot_artikel')[0] == 200)
    # Admin löscht Angebot
    a.click('[data-ob=manage]'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    a.locator('#view-angebote tr[data-oi]:has(input[value*="Metro"]) [data-ofa=del]').click(); a.click('#dlg-confirm [data-v="1"]')
    a.click('[data-ofa=save]'); bestaetigt(a, 'Angebote gespeichert')
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) tr[data-id]')
    check('admin deletes offer: tab gone', tab(a, 'Metro').count() == 0)
    r = get(a, f'offer&angebot={metro}'); check('deleted offer not deliverable (404)', r[0] == 404, r[0])
    # Gleichnamiges Angebot neu anlegen: die alte ID (mit Kundenpreis 19,50 im veröffentlichten Angebot) wird nie wiederverwendet
    cur = get(a, 'offers')[1]
    r = post(a, 'offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': metro, 'name': 'Wochenangebot Metro', 'fallback': 'hidden'}]})
    neu = next((o for o in (r[1] or {}).get('offers', []) if o['name'] == 'Wochenangebot Metro'), {})
    check('neues Angebot mit Namen eines gelöschten: neue ID statt der alten', r[0] == 200 and neu.get('id') not in (None, metro) and neu['id'].startswith(metro + '-'), (r[0], neu))
    r = get(a, f"offer&angebot={neu.get('id')}")
    check('… keine alten Kundenpreise (Regel „ausblenden“: keine Artikel)', r[0] == 200 and r[1]['offer']['items'] == [], r[1]['offer']['items'][:2] if r[0] == 200 else r)
    check('… alte ID bleibt unbekannt (404)', get(a, f'offer&angebot={metro}')[0] == 404)
    cur = get(a, 'offers')[1]
    doc = json.loads(storage_raw('angebote')[storage_raw('angebote').index('{'):])
    check('… gelöschte ID vermerkt (geloescht)', metro in doc.get('geloescht', []), doc.get('geloescht'))
    # Speichern ohne „fallback“ (älterer Client): Einstellung bleibt; Felder einer neueren Fassung bleiben erhalten
    doc['zukunft'] = {'x': 1}
    for o in doc['offers']:
        if o['id'] == neu.get('id'): o['zukunftsfeld'] = 'bleibt'
    storage_write('angebote', doc)
    cur = get(a, 'offers')[1]
    r = post(a, 'offers_save', {'rev': cur['rev'], 'offers': [{'id': o['id'], 'name': o['name']} for o in cur['offers']]})
    nach = {o['id']: o for o in (r[1] or {}).get('offers', [])}
    check('ohne „fallback“: bisherige Einstellung bleibt (ausblenden)', r[0] == 200 and nach.get(neu.get('id'), {}).get('fallback') == 'hidden', r)
    doc = json.loads(storage_raw('angebote')[storage_raw('angebote').index('{'):])
    check('unbekannte Felder (Angebot und Dokument) bleiben erhalten', doc.get('zukunft') == {'x': 1} and next(o for o in doc['offers'] if o['id'] == neu.get('id')).get('zukunftsfeld') == 'bleibt' and metro in doc.get('geloescht', []), doc)
    cur = get(a, 'offers')[1]
    r = post_bestaetigt(a, 'offers_save', {'rev': cur['rev'], 'offers': [o for o in cur['offers'] if o['id'] != neu.get('id')]})
    check('… wieder gelöscht', r[0] == 200, r)
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    # Protokoll
    log = json.dumps(get(a, 'log')[1], ensure_ascii=False)
    check('audit: offers + offer prices logged', 'Angebote geändert' in log and 'Preis Wochenangebot Edeka' in log)
    # Zwei Veröffentlichungen direkt nacheinander: verschiedene, steigende Stände (Bestellwünsche prüfen gegen genau diesen)
    d = get(a, 'draft')[1]
    mdl = d['draft'] or d['published']
    r1 = post(a, 'publish', {'revision': d['revision'], 'model': mdl})
    r2 = post(a, 'publish', {'revision': r1[1].get('revision') if r1[1] else None, 'model': mdl})
    p1, p2 = (r1[1] or {}).get('publishedAt', ''), (r2[1] or {}).get('publishedAt', '')
    check('zweimal in derselben Sekunde veröffentlicht: verschiedene, steigende Stände', r1[0] == 200 and r2[0] == 200 and p1 and p2 and p2 > p1 and p1[:19] <= p2[:19], (r1[0], r2[0], p1, p2))
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    # Mobil
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); m.on('pageerror', lambda x: errs.append('m: ' + str(x)))
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_timeout(300)
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    shot(m.locator('#offer-bar'), SH + '/angebote-mobil.png')
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
