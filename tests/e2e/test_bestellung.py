"""Bestellwunsch aus dem Portal: Mengen eingeben, Preise des Kunden (serverseitig), E-Mail an die eingestellten
Empfänger + Kopie an den Kunden. Läuft gegen den Test-Mailserver – es werden keine echten E-Mails versendet."""
from umgebung import storage_raw
from umgebung import SMTP_PORT  # Testserver je Gruppe (parallel)
import json
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright
from smtp_test import TestSmtp
from umgebung import SH, shot
from kunden_hilfe import Client, B

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
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
check('freight added below the minimum weight (server side, default tiers)', r.get('fracht') == {'kosten': 35.0, 'unter': 200, 'frei': 300}, r.get('fracht'))
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
check('order mail: freight line and grand total', 'Frachtanteil (unter 200 kg): 35,00 €' in m['text'] and 'Gesamt (ca.): 284,88 €' in m['text'] and 'Frachtanteil' in m['html'], m['text'][-500:])
check('order mail: HTML escaped', '<b>vakuumiert</b>' not in m['html'] and '&lt;b&gt;vakuumiert' in m['html'] and 'Kantine Süd &lt;GmbH&gt;' in m['html'])
check('confirmation copy to customer', len(copy) == 1 and 'Ihr Bestellwunsch' in copy[0]['subject'] and NR in copy[0]['text'] and 'verbindlich' in copy[0]['text'] and 'Benutzerkennung' not in copy[0]['text'])
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 1}]})
check('order numbers count up', r['nr'] == NR[:-4] + '0002')
# ---------- Fracht und Hinweis (Verwaltung) ----------
pub = K.call('offer&angebot=edeka')[1].get('fracht') or {}
check('offer carries freight rule and note', pub.get('frei') == 300 and any('300 kg' in l for l in pub.get('hinweis', [])) and any('35 €' in l for l in pub.get('hinweis', [])), pub)
check('freight settings: customer/staff without admin cannot change', K.call('fracht_save', {'aktiv': False, 'staffeln': []})[0] in (401, 403))
check('freight settings: invalid tier rejected', A.call('fracht_save', {'aktiv': True, 'staffeln': [{'unter': 0, 'kosten': 5}], 'zusatz': ''})[0] == 422)
check('freight settings: active needs a tier', A.call('fracht_save', {'aktiv': True, 'staffeln': [], 'zusatz': ''})[0] == 422)
code, fr = A.call('fracht_save', {'aktiv': True, 'staffeln': [{'unter': 100, 'kosten': '20.5'}], 'zusatz': 'Telefon 040 000'})
check('freight settings saved, note follows', code == 200 and fr['fracht']['staffeln'] == [{'unter': 100, 'kosten': 20.5}] and any('100 kg' in l for l in fr['hinweis']) and fr['hinweis'][-1] == 'Telefon 040 000', fr)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 50}]})
check('new tier applies', code == 200 and r['fracht']['kosten'] == 20.5 and r['fracht']['unter'] == 100)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 120}]})
check('at/above the limit: delivered freight-free', code == 200 and r['fracht']['kosten'] == 0)
A.call('fracht_save', {'aktiv': False, 'staffeln': [{'unter': 100, 'kosten': 20.5}], 'zusatz': ''})
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 1}]})
check('freight rule off: nothing added, note without minimum', code == 200 and r['fracht']['kosten'] == 0 and r['fracht']['frei'] is None and 'Mindestbestellmenge' not in str(K.call('offer&angebot=edeka')[1]['fracht']['hinweis']))
check('freight change logged', 'Fracht und Hinweis im Angebot geändert' in str(A.call('log')[1].get('entries')))
import urllib.request as _ur
def _pub_offer(etag=None):
    rq = _ur.Request(B + '/api/?action=offer', headers={'If-None-Match': etag} if etag else {})
    try:
        r = _ur.urlopen(rq); return r.status, r.headers.get('ETag'), json.loads(r.read())
    except Exception as ex:
        return getattr(ex, 'code', 0), None, None
st0, et0, _ = _pub_offer()
check('public offer cached via ETag (unchanged → 304)', st0 == 200 and et0 and _pub_offer(et0)[0] == 304)
A.call('fracht_save', {'aktiv': True, 'staffeln': [{'unter': 300, 'kosten': 30}, {'unter': 200, 'kosten': 35}], 'zusatz': ''})
st1, et1, body1 = _pub_offer(et0)
check('changing freight/note invalidates the cached offer (browser gets the new note)', st1 == 200 and et1 != et0 and any('35 €' in l for l in body1['fracht']['hinweis']), (st1, et0, et1))
A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org', 'copy': False})
n0 = len(smtp.messages)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 2}]})
check('without copy setting: only internal mail', code == 200 and r['copy'] is None and len(smtp.messages) == n0 + 1)
smtp.close(); time.sleep(0.2)
code, r = K.call('kunde_bestellung', {**order, 'positions': [{'id': I1['id'], 'qty': 2}]})
check('mail server down: clear error for customer', code == 502 and 'gespeichert' in r.get('error', '') and 'nicht bestätigt' in r.get('error', ''), r)
stored = storage_raw('bestellungen')
check('failed order kept on the server', '"status":"fehler"' in stored.replace(' ', ''))
smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
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
    check('public page: note under the offer', 'Mindestbestellmenge' in pub.inner_text('.al-note'))
    pub.click('#modebar [data-mode=liste]'); pub.wait_for_selector('table.grid tr.row')
    check('public order view: explains login, offers login button', 'als Kunde anmelden' in pub.inner_text('#order-hint') and pub.locator('#order-hint [data-kact=login]').count() == 1 and 'Mindestbestellmenge' in pub.inner_text('.list-note'))
    ctx = br.new_context(viewport={'width': 1360, 'height': 900}); c = ctx.new_page(); errs = []
    c.on('pageerror', lambda e: errs.append(str(e))); c.on('dialog', lambda dlg: dlg.accept())
    c.goto(B + '/'); c.wait_for_selector('#btn-kunde-login'); c.click('#btn-kunde-login')
    c.fill('#kl-form [name=username]', 'kantine.sued'); c.fill('#kl-form [name=password]', 'Kantine-Kennwort-5'); c.click('#kl-form [type=submit]')
    c.wait_for_url(re.compile(r'angebot=edeka')); c.wait_for_selector('.al tr.row')
    check('customer: offer view first, without quantity inputs', c.locator('.al').count() == 1 and c.locator('#list .qty').count() == 0 and c.get_attribute('#modebar [data-mode=angebot]', 'aria-checked') == 'true')
    check('switch names the order view', 'Bestellansicht' in c.inner_text('#modebar') and 'Mengen eintragen' in c.inner_text('#modebar'))
    c.click('#modebar [data-mode=liste]'); c.wait_for_selector('tr.row .qty')
    check('customer: order view with quantity column, no hint', 'Menge kg' in c.inner_text('thead') and c.locator('tr.row .qty').count() > 10 and c.locator('#order-hint').is_hidden())
    q1 = c.locator(f'#list .qty[data-qty="{I1["id"]}"]')
    q1.click(); c.wait_for_timeout(250)
    check('clicking the quantity field does not open the article details', c.locator('#dlg-detail[open]').count() == 0)
    c.locator(f'tr.row[data-id="{I1["id"]}"] td.c-qty').click(position={'x': 4, 'y': 4}); c.wait_for_timeout(250)
    check('click next to the field does not open details either', c.locator('#dlg-detail[open]').count() == 0)
    c.locator(f'tr.row[data-id="{I1["id"]}"] td.c-price').click(); c.wait_for_timeout(250)
    check('click elsewhere in the row does not open details', c.locator('#dlg-detail[open]').count() == 0)
    c.locator(f'tr.row[data-id="{I1["id"]}"] .name-btn').click(); c.wait_for_selector('#dlg-detail[open]')
    check('click on the name opens details', c.locator('#dlg-detail[open]').count() == 1)
    c.click('#dlg-detail [data-close]'); c.wait_for_timeout(200)
    q1.fill('2,5'); q1.press('Tab'); c.wait_for_selector('#orderbar:not([hidden])')
    t = c.inner_text('#orderbar')
    check('order bar: positions, kg, total with customer price', '1 Position' in t and '2,5 kg' in t and '49,98' in t, t)
    q2 = c.locator(f'#list .qty[data-qty="{I2["id"]}"]'); q2.fill('abc'); q2.press('Tab')
    check('invalid quantity marked', 'invalid' in q2.get_attribute('class'))
    q2.fill('1.000'); q2.press('Tab'); c.wait_for_timeout(100)
    check('German thousands separator understood', '2 Positionen' in c.inner_text('#orderbar') and '1.002,5 kg' in c.inner_text('#orderbar'), c.inner_text('#orderbar'))
    q2.fill('4'); q2.press('Tab')
    c.screenshot(path=SH + '/bestellung-liste.png')
    check('order summary also in Merkliste column', '2 Positionen' in c.inner_text('#merk .merk-order') and c.locator('#merk [data-merk=order]').count() == 1, c.inner_text('#merk'))
    c.click('#merk [data-merk=order]'); c.wait_for_selector('#dlg-order[open]')
    check('column button opens the order check', 'Bestellwunsch prüfen' in c.inner_text('#order-body'))
    c.keyboard.press('Escape'); c.wait_for_selector('#dlg-order', state='hidden')
    c.reload(); c.wait_for_selector('tr.row .qty')
    check('quantities kept after reload', c.input_value(f'#list .qty[data-qty="{I1["id"]}"]') == '2,5' and '2 Positionen' in c.inner_text('#orderbar'))
    c.locator(f'tr.row[data-id="{I2["id"]}"] .name-btn').click(); c.wait_for_selector('#dlg-detail[open] .qty')
    check('detail view offers quantity field (synced)', c.input_value('#dlg-detail .qty') == '4')
    c.fill('#dlg-detail .qty', '5'); c.press('#dlg-detail .qty', 'Tab'); c.wait_for_timeout(150)
    check('quantity from detail view updates list', c.input_value(f'#list .qty[data-qty="{I2["id"]}"]') == '5')
    c.click('#dlg-detail [data-close]'); c.wait_for_timeout(150)
    c.locator(f'#list .qty[data-qty="{I2["id"]}"]').fill('4'); c.locator(f'#list .qty[data-qty="{I2["id"]}"]').press('Tab')
    c.click('.seg [data-view=cards]'); c.wait_for_selector('.card .qty')
    c.locator(f'.card .qty[data-qty="{I1["id"]}"]').click(); c.wait_for_timeout(200)
    check('card view: clicking quantity does not open details', c.locator('#dlg-detail[open]').count() == 0)
    check('card view: quantity input synced', c.input_value(f'.card .qty[data-qty="{I1["id"]}"]') == '2,5')
    c.click('.seg [data-view=table]'); c.wait_for_selector('tr.row .qty')
    c.click('#orderbar [data-order=open]'); c.wait_for_selector('#dlg-order[open]')
    t = c.inner_text('#order-body')
    check('order dialog lists positions + total', 'Bestellwunsch prüfen' in t and 'auf Anfrage' in t and '49,98 €' in t, t[:400])
    check('order dialog: weight notice and freight added automatically', 'Mindestmenge nicht erreicht' in t and 'Frachtanteil' in t and '35,00 €' in t and '84,98 €' in t, t[-600:])
    check('order bar shows freight and missing weight', 'Fracht' in c.inner_text('#orderbar') and 'bis frachtfrei' in c.inner_text('#orderbar'))
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
    check('after sending: cart cleared', c.locator('#orderbar').is_hidden() and c.input_value(f'#list .qty[data-qty="{I1["id"]}"]') == '')
    c.reload(); c.wait_for_selector('tr.row .qty')
    check('cleared cart stays cleared', c.locator('#orderbar').is_hidden())
    # Mobil
    mpg = ctx.new_page(); mpg.set_viewport_size({'width': 390, 'height': 820}); mpg.goto(B + '/?angebot=edeka'); mpg.wait_for_selector('html[data-bereit]'); mpg.click('#modebar [data-mode=liste]'); mpg.wait_for_selector('tr.row .qty')
    mpg.locator(f'#list .qty[data-qty="{I1["id"]}"]').fill('7'); mpg.locator(f'#list .qty[data-qty="{I1["id"]}"]').press('Tab'); mpg.wait_for_selector('#orderbar:not([hidden])')
    check('mobile: quantity usable, no horizontal scroll', mpg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    mpg.screenshot(path=SH + '/bestellung-mobil.png')
    # Einstellungen im Eingabebereich
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-mail'); a.wait_for_selector('#ml-orders')
    check('settings card shows order recipients', 'bestellung@example.org' in a.inner_text('#ml-orders .ml-oto') and a.is_checked('#ml-orders [name=enabled]'))
    check('recipients edited under notifications', a.input_value('#ml-notify [name=to-bestellung]') == 'bestellung@example.org')
    a.fill('#ml-notify [name=to-bestellung]', 'bestellung@example.org, chef@example.org'); a.click('#ml-notify [type=submit]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('gespeichert')", timeout=8000)
    check('recipients saved from UI', A.call('mail_status')[1]['orders']['to'] == ['bestellung@example.org', 'chef@example.org'])
    a.click('#ml-orders [type=submit]'); a.wait_for_function("document.querySelector('#toast').textContent.includes('Gespeichert')", timeout=8000)
    check('saving order form keeps recipients', A.call('mail_status')[1]['orders']['to'] == ['bestellung@example.org', 'chef@example.org'])
    shot(a.locator('#ml-orders'), SH + '/bestellung-einstellungen.png')
    # Fracht und Hinweis in der Verwaltung
    a.wait_for_selector('#ml-fracht')
    check('freight card: tiers and note preview', a.locator('#ml-fracht .fr-row').count() == 2 and '300 kg' in a.inner_text('#ml-fracht .fr-prev'))
    a.click('#ml-fracht [data-fr=add]')
    row3 = a.locator('#ml-fracht .fr-row').nth(2)
    row3.locator('[name=fr-unter]').fill('100'); row3.locator('[name=fr-kosten]').fill('40')
    a.fill('#ml-fracht [name=zusatz]', 'Telefon Büro: 040 000 00')
    a.click('#ml-fracht [type=submit]'); a.wait_for_function("document.querySelector('#toast').textContent.includes('Fracht und Hinweis gespeichert')", timeout=8000)
    a.wait_for_selector('#ml-fracht .fr-prev:has-text("unter 100 kg")')
    fr = A.call('mail_status')[1]['fracht']
    check('freight card: saved through the UI', [x['unter'] for x in fr['staffeln']] == [300, 200, 100] and fr['zusatz'] == 'Telefon Büro: 040 000 00', fr)
    shot(a.locator('#ml-fracht'), SH + '/fracht-einstellungen.png')
    a.locator('#ml-fracht .fr-row').nth(2).locator('[data-fr=rm]').click()
    a.click('#ml-fracht [type=submit]'); a.wait_for_selector('#ml-fracht .fr-prev:not(:has-text("unter 100 kg"))')
    check('freight card: tier removed', [x['unter'] for x in A.call('mail_status')[1]['fracht']['staffeln']] == [300, 200])
    # Mitarbeiter und Kunde im selben Browser: Startseite führt trotzdem zum Kundenangebot mit Mengen
    a.goto(B + '/#ansicht=tabelle'); a.wait_for_selector('table.grid tr.row')
    check('staff order view: says only customers can order', 'Mitarbeiter-Ansicht' in a.inner_text('#order-hint'))
    a.click('#btn-kunde-login'); a.fill('#kl-form [name=username]', 'kantine.sued'); a.fill('#kl-form [name=password]', 'Kantine-Kennwort-5'); a.click('#kl-form [type=submit]')
    a.wait_for_url(re.compile(r'angebot=edeka')); a.wait_for_selector('tr.row .qty')   # Ansicht (Bestellansicht) bleibt beim Wechsel erhalten
    check('staff + customer in one browser: own offer with quantities', a.locator('tr.row .qty').count() > 10)
    a.goto(B + '/?angebot=bela'); a.wait_for_selector('tr.row')
    check('staff + customer: explicitly linked foreign offer stays, hint + switch, no quantities', 'nicht für Sie freigeschaltet' in a.inner_text('#preview-banner') and a.locator('.qty').count() == 0 and a.locator('#preview-banner [data-kswitch=edeka]').count() == 1)
    check('no JS errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
