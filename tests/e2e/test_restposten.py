"""Sonderposten (kurzes MHD, solange der Vorrat reicht), Ausblenden in jedem Angebot, eigene Artikelliste (Sonderposten nur
für eigene Artikel), Kein-Bestand-Zeichen und Sonderposten-Mail je Angebot. Läuft gegen den Test-Mailserver – es werden keine echten E-Mails versendet."""
import json
from umgebung import SMTP_PORT  # Testserver je Gruppe (parallel)
import re
import sys
from playwright.sync_api import sync_playwright
from smtp_test import TestSmtp
from umgebung import SH, FIX
from kunden_hilfe import Client, B

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


norm = lambda c: (str(c).lstrip('0') or '0') if str(c).isdigit() else str(c).upper()
master = [a for a in json.load(open(FIX + '/bestand/master_stock.json')) if a[2] and a[2] > 0]
articles = [{'code': a[0].lstrip('0') or '0', 'name': a[1], 'kg': a[2], 'mhd': a[3], 'mhdKg': a[4], 'lots': []} for a in master]
in_stock = {norm(a[0]) for a in master}

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
check('stock stored', A.call('stock_import', {'date': '2026-10-16', 'source': 'Bestand.xls', 'articles': articles})[0] == 200)

model = A.call('draft')[1]['published']
priced = [i for i in model['items'] if i['code'] and i['price']['status'] == 'value']
withs = [i for i in priced if norm(i['code']) in in_stock]
without = [i for i in priced if norm(i['code']) not in in_stock]
IA, IB, ID = withs[0], withs[1], withs[2]
IC = without[0]
PA = IA['price']['value']
IA['sale'] = {'value': 5.55}
IA.setdefault('variants', {})['bela'] = {'status': 'hidden'}
IB['sale'] = {'value': 6.66, 'offers': {'edeka': {'value': 6.11}, 'bela': {'status': 'none'}, 'gibtsnicht': {'value': 1}}}
IC['sale'] = {'value': 1.11}
ID.setdefault('variants', {})['std'] = {'status': 'hidden'}
code, r = A.call('save_draft', {'model': model, 'revision': A.call('draft')[1]['revision']})
check('draft with sale prices saved', code == 200, r)
d = A.call('draft')[1]['draft']
byid = {i['id']: i for i in d['items']}
check('unknown offer dropped from sale, rest kept', byid[IB['id']]['sale'] == {'value': 6.66, 'offers': {'edeka': {'value': 6.11}, 'bela': {'status': 'none'}}}, byid[IB['id']].get('sale'))
check('hidden in Wochenangebot stored', byid[ID['id']]['variants'] == {'std': {'status': 'hidden'}})
bad = json.loads(json.dumps(d)); bad['items'][0]['sale'] = {'value': -3}
check('invalid sale price rejected', A.call('save_draft', {'model': bad, 'revision': A.call('draft')[1]['revision']})[0] == 422)
bad = json.loads(json.dumps(d)); bad['items'][0]['variants'] = {'std': {'status': 'value', 'value': 3}}
code, r = A.call('save_draft', {'model': bad, 'revision': A.call('draft')[1]['revision']})
check('Wochenangebot accepts only "hidden" as own setting', code == 200 and 'std' not in (A.call('draft')[1]['draft']['items'][0].get('variants') or {}))
code, r = A.call('save_draft', {'model': d, 'revision': A.call('draft')[1]['revision']})
code, r = A.call('publish', {'model': d, 'revision': A.call('draft')[1]['revision']})
check('published', code == 200, r)
log = A.call('log')[1]['entries']
check('audit names sale price and visibility', any('Sonderpreis' in json.dumps(e, ensure_ascii=False) for e in log) and any('Sichtbar im Wochenangebot' in json.dumps(e, ensure_ascii=False) for e in log))

# --- Auslieferung je Angebot
P = Client('198.51.100.9')
code, o, raw = P.call('offer', raw=True)
items = {i['id']: i for i in o['offer']['items']}
check('public: hidden article missing', ID['id'] not in items)
check('public: sale price with regular price', items[IA['id']]['price']['value'] == 5.55 and items[IA['id']]['sale'] is True and items[IA['id']].get('regular') == PA, items.get(IA['id']))
check('public: base sale price', items[IB['id']]['price']['value'] == 6.66)
check('public: sold-out sale article hidden automatically', IC['id'] not in items)
check('public: no customer prices or sale details leak', '6.11' not in raw and '"variants"' not in raw and '"offers"' not in raw)


def customer(firma, user, offers, email, mail=True):
    rev = A.call('kunden')[1]['rev']
    code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': firma, 'nr': '', 'ansprechpartner': '', 'strasse': '', 'plz': '', 'ort': '', 'land': '', 'email': email,
                                    'telefon': '', 'notiz': '', 'active': True, 'angebote': offers, 'mailAngebot': mail,
                                    'login': {'username': user, 'password': 'Kunden-Kennwort-5', 'mustChange': False, 'active': True}})
    return r['customer']['id']


KE = customer('Edeka Markt Nord', 'edeka.nord', ['edeka'], 'edeka@example.org')
KB = customer('Bela Gastro', 'bela.gastro', ['bela'], 'bela@example.org')
KS = customer('Kantine Wochenangebot', 'kantine.std', ['std'], 'kantine@example.org')
KX = customer('Edeka Abgemeldet', 'edeka.ab', ['edeka'], 'ab@example.org', mail=False)


def offer_as(user, oid):
    c = Client('198.51.100.30'); c.call('kunde_login', {'username': user, 'password': 'Kunden-Kennwort-5'})
    return {i['id']: i for i in c.call('offer&angebot=' + oid)[1]['offer']['items']}


ed = offer_as('edeka.nord', 'edeka')
check('edeka: own sale price per offer', ed[IB['id']]['price']['value'] == 6.11 and ed[IB['id']]['sale'] is True)
check('edeka: base sale price', ed[IA['id']]['price']['value'] == 5.55)
check('edeka: article hidden only in Wochenangebot is visible', ID['id'] in ed)
be = offer_as('bela.gastro', 'bela')
check('bela: eye hides article despite sale price', IA['id'] not in be)
check('bela: "no sale price" keeps the normal price', not be[IB['id']].get('sale') and be[IB['id']]['price']['value'] == IB['price']['value'])

# Bestand weg → Sonderposten verschwindet, wieder da → erscheint
less = [a for a in articles if norm(a['code']) != norm(IA['code'])]
import urllib.request as _ur, urllib.error as _ue
def _etag_abruf(etag=None):
    rq = _ur.Request(B + '/api/?action=offer', headers={'If-None-Match': etag} if etag else {})
    try:
        r = _ur.urlopen(rq); return r.status, r.headers.get('ETag')
    except _ue.HTTPError as e:
        return e.code, e.headers.get('ETag')
st0, et0 = _etag_abruf()
A.call('stock_import', {'date': '2026-10-17', 'source': 'Bestand.xls', 'articles': less})
st1, et1 = _etag_abruf(et0)
check('ETag: Sonderposten ausverkauft → neue Antwort statt 304 (Bestand gehört zur ETag)', st0 == 200 and et0 and st1 == 200 and et1 != et0, (st0, st1, et0, et1))
check('stock gone: sale article hidden everywhere', IA['id'] not in {i['id'] for i in P.call('offer')[1]['offer']['items']} and IA['id'] not in offer_as('edeka.nord', 'edeka'))
A.call('stock_import', {'date': '2026-10-17', 'source': 'Bestand.xls', 'articles': articles})
check('stock back: sale article shown again', IA['id'] in {i['id'] for i in P.call('offer')[1]['offer']['items']})

# --- Sonderposten-Mail je Angebot
E = Client('198.51.100.3')
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('editor cannot see recipients', E.call('restposten_info&offer=edeka')[0] == 403)
code, info = A.call('restposten_info&offer=edeka')
names = {c['firma']: c['reason'] for c in info['recipients']}
check('info: only customers of this offer', set(names) == {'Edeka Markt Nord', 'Edeka Abgemeldet'}, names)
check('info: unsubscribed customer marked', names['Edeka Abgemeldet'] != '' and names['Edeka Markt Nord'] == '')
check('info: sale items of this offer (no sold-out)', sorted((x['code'], x['price']) for x in info['items']) == sorted([(IA['code'], 5.55), (IB['code'], 6.11)]), info['items'])
code, r = A.call('kunden_restposten', {'offer': 'edeka', 'ids': [KE], 'publishedAt': '2000-01-01T00:00:00Z'})
check('stale publication rejected', code == 409)
n0 = len(smtp.messages)
code, r = A.call('kunden_restposten', {'offer': 'edeka', 'ids': [KE, KB, KX], 'note': 'Nur diese Woche.', 'publishedAt': info['publishedAt']})
out = {x['id']: x for x in r.get('results', [])}
check('sent to customer of this offer', code == 200 and out[KE]['ok'] is True, r)
check('customer of another offer refused', out[KB]['ok'] is False and 'nicht freigeschaltet' in out[KB]['error'])
check('unsubscribed customer refused', out[KX]['ok'] is False)
new = smtp.messages[n0:]
check('exactly one mail, to that customer only', len(new) == 1 and new[0]['to'] == ['edeka@example.org'], [m['to'] for m in new])
msg = new[0] if new else {'text': '', 'html': '', 'msg': {}}
body = msg['text'] + msg['html']
check('mail: own prices of this offer, not the base price', '6,11' in body and '5,55' in body and '6,66' not in body, re.findall(r'\d+,\d\d', body)[:8])
check('mail: subject and note', 'Sonderposten' in str(msg['msg']['Subject']) and 'Nur diese Woche.' in body)
check('mail: unsubscribe header', bool(msg['msg']['List-Unsubscribe']))
code, r = A.call('kunden_restposten', {'offer': 'std', 'ids': [KS], 'publishedAt': info['publishedAt']})
check('Wochenangebot customers get the Wochenangebot sale prices', code == 200 and r['results'][0]['ok'] and '6,66' in smtp.messages[-1]['text'])
code, r = A.call('kunden_mail_vorschau', {'type': 'restposten', 'offer': 'edeka', 'id': KE})
check('preview of sale mail', code == 200 and '6,11' in r['html'])

# --- Eigene Artikelliste (Regel „hidden“): nur Artikel mit eigenem Eintrag – Sonderposten anderer Artikel erscheinen dort
# nicht (früher: Sonderposten in jedem Angebot mit dieser Regel); Sonderpreis gilt für die eigenen Artikel (GR-005)
o = A.call('offers')[1]
code, r = A.call('offers_save', {'rev': o['rev'], 'offers': [{'id': x['id'], 'name': x['name']} for x in o['offers']] + [{'id': 'metro', 'name': 'Wochenangebot Metro'}]})
check('neues Angebot ohne Angabe der Regel: eigene Artikelliste', code == 200 and next(x for x in r['offers'] if x['id'] == 'metro').get('fallback') == 'hidden', r)
d = A.call('draft')
mdl = d[1]['draft'] or d[1]['published']
for it in mdl['items']:
    if it['id'] == IB['id']: it.setdefault('variants', {})['metro'] = {'status': 'value', 'value': 7.0}
code, r = A.call('publish', {'model': mdl, 'revision': d[1]['revision']})
check('Metro-Preis veröffentlicht', code == 200, r)
KM = customer('Metro Markt', 'metro.markt', ['metro'], 'metro@example.org')
me = offer_as('metro.markt', 'metro')
check('Metro: nur der eigene Artikel – Sonderposten anderer Artikel fehlen', set(me) == {IB['id']}, sorted(me)[:6])
check('Metro: Sonderpreis gilt für den eigenen Artikel, Normalpreis durchgestrichen', me[IB['id']]['price']['value'] == 6.66 and me[IB['id']].get('sale') is True and me[IB['id']].get('regular') == 7.0, me.get(IB['id']))
code, info_m = A.call('restposten_info&offer=metro')
check('Sonderposten-Mail Metro: nur der eigene Sonderposten', code == 200 and [x['code'] for x in info_m['items']] == [IB['code']], info_m.get('items'))

# --- Oberfläche
with sync_playwright() as p:
    br = p.chromium.launch()
    errs = []
    actx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = actx.new_page(); a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.wait_for_function("document.querySelector('#groups:not(.no-stock)') && document.querySelector('#mhd-panel:not([hidden])')", timeout=10000)
    row = lambda iid: a.locator(f'tr[data-id="{iid}"]')
    ns = row(IC['id']).locator('.nostock')
    check('red no-stock mark with hover text', ns.count() == 1 and 'Kein verfügbarer Bestand' in (ns.get_attribute('title') or ''))
    check('no red mark when stock exists', row(IA['id']).locator('.nostock').count() == 0)
    check('Wochenangebot: Artikel, der nicht im Wochenangebot steht, fehlt in seiner Liste', row(ID['id']).count() == 0)
    check('sale tag in row', 'Sonderpreis 5,55' in row(IA['id']).locator('.sale-tag').inner_text())
    check('sold-out sale shown as hidden', 'ohne Bestand' in row(IC['id']).locator('.sale-tag').inner_text())
    row(IA['id']).scroll_into_view_if_needed(); a.mouse.wheel(0, -120); a.screenshot(path=SH + '/restposten-zeilen.png')
    # ✕ entfernt nur aus dem Wochenangebot (andere Angebote folgen ihm hier noch, der Artikel bleibt im Entwurf)
    X = withs[3]
    row(X['id']).locator('[data-act=remove]').click()
    a.wait_for_function("document.querySelector('#save-state').classList.contains('saved')", timeout=10000)
    check('✕ entfernt aus dem Wochenangebot', row(X['id']).count() == 0 and next(i for i in A.call('draft')[1]['draft']['items'] if i['id'] == X['id'])['variants'] == {'std': {'status': 'hidden'}})
    check('change shown for Wochenangebot', 'im Wochenangebot hinzugefügt/entfernt' in (a.get_attribute('#btn-publish', 'title') or ''))
    a.click('#btn-undo'); a.wait_for_selector(f'tr[data-id="{X["id"]}"]')
    a.wait_for_function("document.querySelector('#save-state').classList.contains('saved') || /Keine Änderungen/.test(document.querySelector('#save-state').textContent)", timeout=10000)
    # Kurzes MHD → Sonderpreis (Leiste beim Öffnen zugeklappt)
    check('Leiste „Kurzes MHD“ zugeklappt', a.locator('#mhd-panel .np-card:not(.open)').count() == 1 and a.locator('#mhd-panel tbody tr').count() == 0)
    a.click('#mhd-panel [data-mp=toggle]'); a.wait_for_selector('#mhd-panel .np-card.open')
    t = a.inner_text('#mhd-panel')
    check('short MHD panel', 'Kurzes MHD' in t and a.locator('#mhd-panel tbody tr').count() > 0, t[:120])
    btn = a.locator('#mhd-panel tr[data-mid]:not(:has(.sp-val)) [data-mp=sale]').first
    mid = btn.locator('xpath=ancestor::tr').get_attribute('data-mid')
    btn.click(); a.wait_for_selector('#dlg-sale[open]')
    a.fill('#sale-body [name=value]', '7,77')
    a.select_option('#sale-body tr[data-soid="edeka"] [data-sm]', 'own'); a.fill('#sale-body tr[data-soid="edeka"] [data-sv]', '7,50')
    a.screenshot(path=SH + '/restposten-dialog.png')
    a.click('#sale-body button[type=submit]')
    a.wait_for_function("document.querySelector('#save-state').classList.contains('saved')", timeout=10000)
    sv = next(i for i in A.call('draft')[1]['draft']['items'] if i['id'] == mid).get('sale') or {}
    check('sale price set from MHD list', sv.get('value') == 7.77 and sv.get('offers') == {'edeka': {'value': 7.5}}, sv)
    check('changes show sale price', 'Sonderpreis' in (a.get_attribute('#btn-publish', 'title') or ''))
    a.screenshot(path=SH + '/restposten-editor.png')
    # Sonderposten senden (Edeka)
    a.click('#offer-bar [data-offer="edeka"]')
    check('edeka view shows own sale price', 'Sonderpreis 6,11' in row(IB['id']).locator('.sale-tag').inner_text())
    a.click('#offer-head [data-ob=restposten]'); a.wait_for_selector('#dlg-rest[open]')
    t = a.inner_text('#rest-body')
    check('send dialog: items, only this offer\'s customers', 'Edeka Markt Nord' in t and 'Bela' not in t and '6,11' in t and 'unveröffentlichte' in t, t[:300])
    a.screenshot(path=SH + '/restposten-senden.png')
    n0 = len(smtp.messages)
    a.click('#rest-body [data-rp=send]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_selector('#rest-body .st-ok', timeout=15000)
    check('sent from the dialog', len(smtp.messages) == n0 + 1 and smtp.messages[-1]['to'] == ['edeka@example.org'])
    a.keyboard.press('Escape')
    # Angebotsseite: Sonderposten-Anzeige
    pg = br.new_page(viewport={'width': 1300, 'height': 900}); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/'); pg.wait_for_selector('tr.row')
    r1 = pg.locator(f'tr.row[data-id="{IA["id"]}"]')
    check('offer list: sale price, crossed-out price, tag', '5,55' in r1.inner_text() and r1.locator('s.p-was').count() == 1 and r1.locator('.tag.sale').count() == 1, r1.inner_text())
    pg.click('#modebar [data-mode=liste]'); pg.wait_for_selector('table.grid tr.row')
    r1 = pg.locator(f'tr.row[data-id="{IA["id"]}"]')
    check('table view: sale price, crossed-out price, note', '5,55' in r1.inner_text() and 'solange der Vorrat reicht' in r1.inner_text() and r1.locator('s.p-was').count() == 1, r1.inner_text())
    check('table view: tag Sonderposten', r1.locator('.tag.sale').count() == 1)
    check('public page: hidden article missing', pg.locator(f'tr.row[data-id="{ID["id"]}"]').count() == 0)
    r1.scroll_into_view_if_needed(); pg.screenshot(path=SH + '/restposten-seite.png')
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
