"""Bestellwunsch aus dem Portal: Mengen eingeben, Preise des Kunden (serverseitig), E-Mail an die eingestellten
Empfänger + Kopie an den Kunden. Läuft gegen den Test-Mailserver – es werden keine echten E-Mails versendet."""
import json
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright
from smtp_test import TestSmtp
from umgebung import SH
from kunden_hilfe import Client, B

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


smtp = TestSmtp(2526, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)

# Kundenpreise für Edeka setzen und veröffentlichen
code, d = A.call('draft')
model = d['draft'] or d['published']
items = model['items']
I1, I2, I3 = items[0], items[1], items[2]
I1.setdefault('variants', {})['edeka'] = {'status': 'value', 'value': 19.99}
I2.setdefault('variants', {})['edeka'] = {'status': 'request'}
I3.setdefault('variants', {})['edeka'] = {'status': 'hidden'}
code, r = A.call('publish', {'model': model})
check('offer with customer prices published', code == 200, r)

code, r = A.call('kunden')
code, r = A.call('kunde_save', {'id': '', 'rev': r['rev'], 'firma': 'Kantine Süd <GmbH>', 'nr': 'K-77', 'ansprechpartner': 'Frau Koch', 'strasse': 'Hafenweg 3', 'plz': '20457', 'ort': 'Hamburg',
                                'land': '', 'email': 'kantine@example.org', 'telefon': '040 123', 'notiz': '', 'active': True, 'angebote': ['edeka'],
                                'login': {'username': 'kantine.sued', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
KID = r['customer']['id']
K = Client('198.51.100.20')
check('customer login', K.call('kunde_login', {'username': 'kantine.sued', 'password': 'Kantine-Kennwort-5'})[0] == 200)
check('ordering off by default', K.call('kunde_status')[1]['bestellung'] is False)

# ---------- Einstellungen ----------
E = None
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('editor cannot change order settings', E.call('bestell_settings_save', {'enabled': True, 'to': 'x@example.org'})[0] == 403)
check('enabled without recipient rejected', A.call('bestell_settings_save', {'enabled': True, 'to': ''})[0] == 422)
check('invalid recipient rejected', A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org, kein-mail'})[0] == 422)
check('max 5 recipients', A.call('bestell_settings_save', {'enabled': True, 'to': ','.join(f'a{i}@example.org' for i in range(6))})[0] == 422)
code, r = A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org; Verkauf@example.org bestellung@example.org', 'copy': True})
check('settings saved (dedup, separators)', code == 200 and r['orders']['to'] == ['bestellung@example.org', 'Verkauf@example.org'] and r['active'] is True, r)
check('settings in mail status', A.call('mail_status')[1]['orders']['enabled'] is True)
check('customer sees ordering enabled', K.call('kunde_status')[1]['bestellung'] is True)

# ---------- Bestellwunsch per API ----------
code, off = K.call('offer&angebot=edeka')
PUB = off['offer'].get('publishedAt') or off['offer'].get('savedAt') or ''
ids = {it['id'] for it in off['offer']['items']}
check('customer offer resolved (hidden item absent)', I3['id'] not in ids and I1['id'] in ids)
order = {'angebot': 'edeka', 'publishedAt': PUB, 'termin': '', 'referenz': 'PO-4711', 'bemerkung': 'Bitte <b>vakuumiert</b>\nDanke',
         'positions': [{'id': I1['id'], 'qty': 12.5, 'price': 0.01}, {'id': I2['id'], 'qty': 3}, {'id': I1['id'], 'qty': 99}]}
check('staff session cannot order as customer', A.call('kunde_bestellung', order)[0] == 401)
tok = K.csrf; K.csrf = 'x'
check('order needs customer csrf', K.call('kunde_bestellung', order)[0] == 403)
K.csrf = tok
check('outdated offer version rejected (409)', K.call('kunde_bestellung', {**order, 'publishedAt': '2000-01-01T00:00:00Z'})[0] == 409)
check('offer not assigned rejected', K.call('kunde_bestellung', {**order, 'angebot': 'bela'})[0] == 403)
check('hidden/unknown item rejected', K.call('kunde_bestellung', {**order, 'positions': [{'id': I3['id'], 'qty': 1}]})[0] == 409)
check('zero quantity rejected', K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 0}]})[0] == 422)
check('too large quantity rejected', K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 100000}]})[0] == 422)
check('empty order rejected', K.call('kunde_bestellung', {**order, 'positions': []})[0] == 422)
check('date in the past rejected', K.call('kunde_bestellung', {**order, 'termin': '2020-01-01'})[0] == 422)
n0 = len(smtp.messages)
code, r = K.call('kunde_bestellung', order)
check('order accepted', code == 200 and re.match(r'^B-\d{4}-0001$', r.get('nr', '')) and r['positions'] == 2 and r['onRequest'] == 1, r)
check('total from server prices (customer price, not client value)', r['total'] == 249.88 and r['totalQty'] == 15.5, r)
check('copy address reported', r['copy'] == 'kantine@example.org')
NR = r['nr']
new = smtp.messages[n0:]
inner = [m for m in new if m['to'] != ['kantine@example.org']]
copy = [m for m in new if m['to'] == ['kantine@example.org']]
check('mail to each configured recipient', sorted(m['to'][0] for m in inner) == ['Verkauf@example.org', 'bestellung@example.org'], [m['to'] for m in new])
m = inner[0]
check('order mail: subject with number + customer', NR in m['subject'] and 'Kantine Süd' in m['subject'] and 'KW 43' in m['subject'], m['subject'])
check('order mail: reply goes to customer', str(m['msg']['reply-to']) == 'kantine@example.org')
check('order mail: customer data', all(x in m['text'] for x in ['K-77', 'Frau Koch', 'Hafenweg 3', '040 123', 'kantine.sued', 'PO-4711']))
check('order mail: customer prices + quantities', '12,5 kg × 19,99 €/kg = 249,88 €' in m['text'] and 'auf Anfrage' in m['text'] and '25,54' not in m['text'], m['text'][:600])
check('order mail: HTML escaped', '<b>vakuumiert</b>' not in m['html'] and '&lt;b&gt;vakuumiert' in m['html'] and 'Kantine Süd &lt;GmbH&gt;' in m['html'])
check('confirmation copy to customer', len(copy) == 1 and 'Ihr Bestellwunsch' in copy[0]['subject'] and NR in copy[0]['text'] and 'verbindlich' in copy[0]['text'] and 'Benutzerkennung' not in copy[0]['text'])
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 1}]})
check('order numbers count up', r['nr'] == NR[:-4] + '0002')
A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org', 'copy': False})
n0 = len(smtp.messages)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 2}]})
check('without copy setting: only internal mail', code == 200 and r['copy'] is None and len(smtp.messages) == n0 + 1)
smtp.close(); time.sleep(0.2)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 2}]})
check('mail server down: clear error for customer', code == 502 and 'nicht übermittelt' in r.get('error', ''), r)
stored = open(os.path.join(os.environ['UDATA'], 'bestellungen.php'), encoding='utf-8').read()
check('failed order kept on the server', '"status":"fehler"' in stored.replace(' ', ''))
smtp = TestSmtp(2526, password='Test-Postfach-1')
A.call('bestell_settings_save', {'enabled': False, 'to': 'bestellung@example.org', 'copy': True})
check('disabled: orders refused', K.call('kunde_bestellung', order)[0] == 409 and K.call('kunde_status')[1]['bestellung'] is False)
A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org', 'copy': True})
code, r = A.call('log')
check('audit: orders logged', sum(1 for e in r['entries'] if e['a'] == 'bestellung') >= 4 and any(NR in e['s'] for e in r['entries']))
check('mail log lists order mails', any(x['typ'] == 'bestellung' for x in A.call('mail_status')[1]['log']))

# ---------- Oberfläche ----------
with sync_playwright() as p:
    br = p.chromium.launch()
    # öffentlich: keine Mengen
    pub = br.new_page(); pub.goto(B + '/'); pub.wait_for_selector('tr.row')
    check('public page: no quantity column', pub.locator('.qty').count() == 0 and pub.locator('#orderbar').is_hidden())
    ctx = br.new_context(viewport={'width': 1360, 'height': 900}); c = ctx.new_page(); errs = []
    c.on('pageerror', lambda e: errs.append(str(e))); c.on('dialog', lambda dlg: dlg.accept())
    c.goto(B + '/'); c.wait_for_selector('#btn-kunde-login'); c.click('#btn-kunde-login')
    c.fill('#kl-form [name=username]', 'kantine.sued'); c.fill('#kl-form [name=password]', 'Kantine-Kennwort-5'); c.click('#kl-form [type=submit]')
    c.wait_for_url(re.compile(r'angebot=edeka')); c.wait_for_selector('tr.row .qty')
    check('customer: quantity column', 'Menge kg' in c.inner_text('thead') and c.locator('tr.row .qty').count() > 10)
    q1 = c.locator(f'.qty[data-qty="{I1["id"]}"]')
    q1.fill('2,5'); q1.press('Tab'); c.wait_for_selector('#orderbar:not([hidden])')
    t = c.inner_text('#orderbar')
    check('order bar: positions, kg, total with customer price', '1 Position' in t and '2,5 kg' in t and '49,98' in t, t)
    q2 = c.locator(f'.qty[data-qty="{I2["id"]}"]'); q2.fill('abc'); q2.press('Tab')
    check('invalid quantity marked', 'invalid' in q2.get_attribute('class'))
    q2.fill('1.000'); q2.press('Tab'); c.wait_for_timeout(100)
    check('German thousands separator understood', '2 Positionen' in c.inner_text('#orderbar') and '1.002,5 kg' in c.inner_text('#orderbar'), c.inner_text('#orderbar'))
    q2.fill('4'); q2.press('Tab')
    c.screenshot(path=SH + '/bestellung-liste.png')
    c.reload(); c.wait_for_selector('tr.row .qty')
    check('quantities kept after reload', c.input_value(f'.qty[data-qty="{I1["id"]}"]') == '2,5' and '2 Positionen' in c.inner_text('#orderbar'))
    c.click('.seg [data-view=cards]'); c.wait_for_selector('.card .qty')
    check('card view: quantity input synced', c.input_value(f'.card .qty[data-qty="{I1["id"]}"]') == '2,5')
    c.click('.seg [data-view=table]'); c.wait_for_selector('tr.row .qty')
    c.click('#orderbar [data-order=open]'); c.wait_for_selector('#dlg-order[open]')
    t = c.inner_text('#order-body')
    check('order dialog lists positions + total', 'Bestellwunsch prüfen' in t and 'auf Anfrage' in t and '49,98 €' in t, t[:400])
    c.fill('#order-body .qty[data-qty="%s"]' % I1['id'], '3'); c.press('#order-body .qty[data-qty="%s"]' % I1['id'], 'Tab')
    check('quantity editable in dialog (sum updates)', '59,97 €' in c.inner_text('#order-body') and c.input_value(f'#list .qty[data-qty="{I1["id"]}"]') == '3')
    c.fill('#or-ref', 'Woche 43'); c.fill('#or-bem', 'Bitte bis 10 Uhr liefern')
    c.screenshot(path=SH + '/bestellung-dialog.png')
    n0 = len(smtp.messages)
    c.click('#order-body [data-order=send]'); c.wait_for_selector('#order-body .o-done', timeout=10000)
    check('success message with order number', re.search(r'B-\d{4}-\d{4}', c.inner_text('#order-body')) and 'kantine@example.org' in c.inner_text('#order-body'))
    sent = smtp.messages[n0:]
    check('mails sent from UI', len(sent) == 2 and any('Bitte bis 10 Uhr liefern' in x['text'] and '3 kg × 19,99 €/kg = 59,97 €' in x['text'] for x in sent))
    c.click('#order-body [data-close]'); c.wait_for_timeout(200)
    check('after sending: cart cleared', c.locator('#orderbar').is_hidden() and c.input_value(f'.qty[data-qty="{I1["id"]}"]') == '')
    c.reload(); c.wait_for_selector('tr.row .qty')
    check('cleared cart stays cleared', c.locator('#orderbar').is_hidden())
    # Mobil
    mpg = ctx.new_page(); mpg.set_viewport_size({'width': 390, 'height': 820}); mpg.goto(B + '/?angebot=edeka'); mpg.wait_for_selector('tr.row .qty')
    mpg.locator(f'.qty[data-qty="{I1["id"]}"]').fill('7'); mpg.locator(f'.qty[data-qty="{I1["id"]}"]').press('Tab'); mpg.wait_for_selector('#orderbar:not([hidden])')
    check('mobile: quantity usable, no horizontal scroll', mpg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    mpg.screenshot(path=SH + '/bestellung-mobil.png')
    # Einstellungen im Eingabebereich
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-mail'); a.wait_for_selector('#ml-orders')
    check('settings card shows order recipients', a.input_value('#ml-orders [name=to]') == 'bestellung@example.org' and a.is_checked('#ml-orders [name=enabled]'))
    a.fill('#ml-orders [name=to]', 'bestellung@example.org, chef@example.org'); a.click('#ml-orders [type=submit]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Gespeichert')", timeout=8000)
    check('recipients saved from UI', A.call('mail_status')[1]['orders']['to'] == ['bestellung@example.org', 'chef@example.org'])
    a.locator('#ml-orders').screenshot(path=SH + '/bestellung-einstellungen.png')
    check('no JS errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
