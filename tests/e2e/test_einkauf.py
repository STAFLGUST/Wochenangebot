"""Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber dem Bestand, Rechte je Rolle (Ansehen für alle,
Kundennamen und Melden ab Bearbeiter), E-Mail an die Empfänger „Einkaufsbedarf“, Status „gemeldet“, Oberfläche."""
import json
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, shot, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'id': '', 'name': 'Lena Leserin', 'username': 'lena', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); check('editor login', E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})[0] == 200)
V = Client('198.51.100.4'); check('viewer login', V.call('login', {'username': 'lena', 'password': 'Leserin-Zugang-1'})[0] == 200)


def customer(username, firma):
    rev = A.call('kunden')[1]['rev']
    code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': firma, 'nr': username, 'email': username + '@example.org', 'active': True, 'angebote': ['std'],
                                    'login': {'username': username, 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
    assert code == 200, r
    c = Client('198.51.100.' + str(20 + len(username) % 50))
    assert c.call('kunde_login', {'username': username, 'password': 'Kantine-Kennwort-5'})[0] == 200
    return c


K1 = customer('kantine.nord', 'Kantine Nord')
K2 = customer('gasthaus.sued', 'Gasthaus <Süd>')
check('order settings', A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200)
pub = A.call('draft')[1]['published']
items = [x for x in pub['items'] if (x.get('price') or {}).get('status') == 'value' and x.get('code')]
I1, I2, I3 = items[0], items[1], items[2]


def order(k, pos, termin='', ref=''):
    p = A.call('draft')[1]['published']
    code, r = k.call('kunde_bestellung', {'angebot': 'std', 'publishedAt': p.get('publishedAt', p.get('savedAt', '')), 'termin': termin, 'referenz': ref,
                                           'positions': [{'id': i['id'], 'qty': q} for i, q in pos]})
    assert code == 200, r
    return r['nr']


# ---------- ohne Bestandsliste ----------
N1 = order(K1, [(I1, 8), (I2, 10), (I3, 2)], '2027-01-20')
code, r = A.call('einkauf')
check('without stock list: no items, hint data', code == 200 and r['stock'] is None and r['items'] == [] and r['openOrders'] == 1, r)
check('login required', Client('198.51.100.9').call('einkauf')[0] == 401)

# ---------- Bestand übernehmen ----------
arts = [{'code': I1['code'], 'name': I1['name'], 'kg': 5}, {'code': I2['code'], 'name': I2['name'], 'kg': 100}, {'code': I3['code'], 'name': I3['name'], 'kg': 1}]
check('stock imported', A.call('stock_import', {'date': '2026-10-18', 'source': 'Bestand.xls', 'articles': arts})[0] == 200)
N2 = order(K2, [(I1, 4)], '2027-01-10', 'Ref 7')
code, r = E.call('einkauf')
byc = {i['code']: i for i in r.get('items', [])}
check('editor sees shortfalls', code == 200 and set(byc) == {I1['code'], I3['code']}, list(byc))
check('shortfall = ordered − stock (summed over orders)', byc[I1['code']]['ordered'] == 12 and byc[I1['code']]['available'] == 5 and byc[I1['code']]['short'] == 7, byc.get(I1['code']))
check('covered article not listed', I2['code'] not in byc)
check('earliest wish date first', r['items'][0]['code'] == I1['code'] and byc[I1['code']]['termin'] == '2027-01-10')
check('order references with customer names for editor', [o['nr'] for o in byc[I1['code']]['orders']] == [N2, N1] and byc[I1['code']]['orders'][0]['firma'] == 'Gasthaus <Süd>')
check('totals', r['shortTotal'] == 8 and r['openOrders'] == 2 and r['canSend'] is True, r)
check('stock date shown', r['stock']['date'] == '2026-10-18')
check('new shortfalls marked new', all(i['neu'] and i['gemeldet'] is None for i in r['items']))
code, rv = V.call('einkauf')
check('viewer sees Einkauf', code == 200 and len(rv['items']) == 2)
check('viewer gets no customer names and cannot send', rv['canSend'] is False and all('firma' not in o for i in rv['items'] for o in i['orders']) and rv['recipients'] is None)
check('viewer cannot notify', V.call('einkauf_melden', {'codes': [I1['code']]})[0] == 403)
check('quantities never public', 'short' not in json.dumps(Client('198.51.100.8').call('offer')[1]))

# ---------- stornierte / erledigte zählen nicht ----------
code, d = A.call('bestellungen')
o2 = next(o for o in d['orders'] if o['nr'] == N2)
code, x = A.call('bestellung_save', {'nr': N2, 'workflow': 'storniert', 'assignee': '', 'note': '', 'revision': o2['revision']})
check('order cancelled', code == 200, x)
r = E.call('einkauf')[1]
byc = {i['code']: i for i in r['items']}
check('cancelled order no longer counted', byc[I1['code']]['ordered'] == 8 and byc[I1['code']]['short'] == 3 and r['openOrders'] == 1, byc.get(I1['code']))

# ---------- Benachrichtigen ----------
code, r = E.call('einkauf_melden', {'codes': [I1['code']]})
check('no recipients: clear message', code == 409 and 'Benachrichtigungen' in r['error'], r)
code, r = A.call('benachrichtigung_save', {'events': {'einkauf': {'to': 'einkauf@example.org, lager@example.org'}}})
check('recipients for Einkauf saved (no switch needed)', code == 200 and next(e for e in r['notify']['events'] if e['key'] == 'einkauf')['on'] is True, r)
check('nothing selected rejected', E.call('einkauf_melden', {'codes': ['999999']})[0] == 422)
check('CSRF required', E.call('einkauf_melden')[0] in (403, 405, 415))
code, r = E.call('einkauf_melden', {'codes': [I1['code']], 'note': 'Termin <fest> zugesagt'})
check('editor notifies purchasing', code == 200 and [x['ok'] for x in r['results']] == [True, True], r)
m = next((x for x in smtp.messages if 'einkauf@example.org' in x['to']), None)
check('mail to purchasing with item, shortfall, order and note', m is not None and I1['code'] in m['text'] and 'FEHLMENGE 3 kg' in m['text'] and N1 in m['text'] and 'Termin <fest> zugesagt' in m['text'] and 'Erika Editor' in m['text'], m and m['text'][:800])
check('html escaped', m is not None and '<fest>' not in m['html'] and '&lt;fest&gt;' in m['html'])
check('only selected article in mail', m is not None and ('— ' + I3['code']) not in m['text'] and (' ' + I3['code'] + ' ') not in m['text'])
check('both recipients got it', any('lager@example.org' in x['to'] for x in smtp.messages))
byc = {i['code']: i for i in r['items']}
check('item marked as reported', byc[I1['code']]['gemeldet']['by'] == 'Erika Editor' and byc[I1['code']]['neu'] is False and byc[I3['code']]['neu'] is True)
check('logged', 'Einkauf benachrichtigt' in json.dumps(A.call('log')[1], ensure_ascii=False))
check('mail log', any(x['typ'] == 'einkauf' for x in A.call('mail_status')[1]['log']))
N3 = order(K1, [(I1, 2)])
byc = {i['code']: i for i in E.call('einkauf')[1]['items']}
check('more than reported → flagged again', byc[I1['code']]['short'] == 5 and byc[I1['code']]['neu'] is True and byc[I1['code']]['gemeldet']['kg'] == 3)
n0 = len(smtp.messages)
code, r = A.call('einkauf_melden', {})
check('without selection: all shortfalls', code == 200 and len(smtp.messages) == n0 + 2 and I3['code'] in smtp.messages[-1]['text'] and I1['code'] in smtp.messages[-1]['text'])
check('after new stock: no shortfall', A.call('stock_import', {'date': '2026-10-19', 'source': 'Bestand.xls', 'articles': [dict(a, kg=500) for a in arts]})[0] == 200 and E.call('einkauf')[1]['items'] == [])

# ---------- Oberfläche ----------
A.call('stock_import', {'date': '2026-10-19', 'source': 'Bestand.xls', 'articles': arts})
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def login(user, password, w=1440, h=950):
        pg = br.new_page(viewport={'width': w, 'height': h}); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        return pg

    e = login('erika', 'Editor-Zugang-77')
    check('nav shows Einkauf', e.is_visible('#vt-einkauf'))
    e.click('#vt-einkauf'); e.wait_for_selector('#view-einkauf tr[data-ek]')
    check('table lists shortfalls', e.locator('#view-einkauf tr[data-ek]').count() == 2)
    check('kpis', '2' in e.inner_text('#view-einkauf .ek-kpis') and 'Fehlmenge gesamt' in e.inner_text('#view-einkauf .ek-kpis'))
    check('customer names visible for editor', 'Kantine Nord' in e.inner_text('#view-einkauf .ektab'))
    check('already reported items not preselected', e.locator('#view-einkauf [data-eksel]:checked').count() == 0 and e.is_disabled('#ek-send'))
    e.uncheck('#ek-all') if e.is_checked('#ek-all') else None
    e.click('#ek-all'); e.click('#ek-all')
    check('select none disables send', e.is_disabled('#ek-send') and 'auswählen' in e.inner_text('#ek-send'))
    e.check(f'#view-einkauf [data-eksel="{I3["code"]}"]')
    check('button counts selection', '1 Artikel melden' in e.inner_text('#ek-send') and not e.is_disabled('#ek-send'))
    n0 = len(smtp.messages)
    e.fill('#ek-form [name=note]', 'Bitte bis Freitag')
    e.click('#ek-send')
    e.wait_for_function("document.querySelector('#toast').textContent.includes('Einkauf benachrichtigt')", timeout=8000)
    check('UI sends mail for selection', until(lambda: len(smtp.messages) == n0 + 2, 5) and 'Bitte bis Freitag' in smtp.messages[-1]['text'] and I3['code'] in smtp.messages[-1]['text'])
    e.wait_for_selector(f'#view-einkauf tr[data-ek="{I3["code"]}"] .st-ok')
    check('row shows reported', 'gemeldet' in e.inner_text(f'#view-einkauf tr[data-ek="{I3["code"]}"] .ek-st'))
    shot(e.locator('#view-einkauf'), SH + '/einkauf.png')
    e.set_viewport_size({'width': 390, 'height': 844})
    check('mobile: page does not scroll sideways', e.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    shot(e.locator('#view-einkauf'), SH + '/einkauf-mobil.png')
    v = login('lena', 'Leserin-Zugang-1')
    check('viewer: nav shows Einkauf', v.is_visible('#vt-einkauf'))
    v.click('#vt-einkauf'); v.wait_for_selector('#view-einkauf tr[data-ek]')
    check('viewer: read-only (no checkboxes, no send form, no names)', v.locator('#view-einkauf [data-eksel]').count() == 0 and v.locator('#ek-form').count() == 0 and 'Kantine Nord' not in v.inner_text('#view-einkauf'))
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
