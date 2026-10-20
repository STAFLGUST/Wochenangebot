"""Sicherheit, Druck und Formatierung: Zwei-Faktor-Ersteinrichtung nur mit Passwort (außer direkt nach der Anmeldung),
Raten des Kundenpassworts begrenzt, kein Browser-Cache für angemeldete Antworten, keine internen Importangaben im
ausgelieferten Angebot, Bestell-E-Mail (Betreff mit Jahr, „Warenwert“), Einzelangebot-PDF (lange Titel/Nummern, Stand),
Portal-Druck (Dunkelmodus, Kopf mit Logo und Angebotsname, Stand der Veröffentlichung, Anführungszeichen, kleine Gruppen
nicht geteilt, Hinweis, Sortierung, leere Auswahl), Preise mit zwei Nachkommastellen, Eingabebereich-Druck (Ansicht bzw.
offenes Fenster), deckende Anmeldung nach Sitzungsende, Bestellwunsch-Entwurf beim Abmelden entfernt.
Nur synthetische Testdaten; es werden keine echten E-Mails versendet."""
import json
import os
import re
import subprocess
import sys
import urllib.request
import zlib
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SMTP_PORT, storage_raw, storage_write, until

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def sid_of(cl, name='WA_ADMIN'):
    jar = next(h.cookiejar for h in cl.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor))
    return next(c.value for c in jar if c.name == name)


def session_set(sid, php):
    subprocess.run(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-r',
                    'session_id($argv[1]); session_start(); ' + php + ' session_write_close();', sid], check=True)


def headers(cl, action):
    req = urllib.request.Request(BASE + '/api/?action=' + action, headers={'X-Forwarded-For': cl.ip})
    try:
        r = cl.http.open(req)
    except urllib.error.HTTPError as ex:
        r = ex
    return r.code, r.headers, r.read()


def pdf_inhalt(data):
    out = b''
    for mm in re.finditer(rb'/Filter /FlateDecode >>\nstream\n', data):
        n = int(re.search(rb'/Length (\d+)', data[max(0, mm.start() - 60):mm.start()]).group(1))
        out += zlib.decompress(data[mm.end():mm.end() + n])
    return out.decode('cp1252', 'replace')


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200

# ---------- Zwei-Faktor: Ersteinrichtung ----------
A.call('user_save', {'username': 'tina', 'name': 'Tina Test', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
T = Client('198.51.100.5'); assert T.call('login', {'username': 'tina', 'password': 'Bearbeiter-Zugang-1'})[0] == 200
check('Ersteinrichtung direkt nach der Anmeldung ohne erneutes Passwort', T.call('twofa_begin', {})[0] == 200)
session_set(sid_of(T), '$_SESSION["authAt"] = time() - 400;')
st, r = T.call('twofa_begin', {})
check('Ersteinrichtung später verlangt das Passwort', st == 422 and r.get('code') == 'confirmation_invalid', r)
check('… mit Passwort möglich', T.call('twofa_begin', {'password': 'Bearbeiter-Zugang-1'})[0] == 200)

# ---------- Kein Browser-Cache für angemeldete Antworten ----------
for act in ('draft', 'versions', 'offer&angebot=std&draft=1', 'kunden'):
    st, h, _ = headers(A, act)
    check(f'„{act}“: Cache-Control no-store', st == 200 and 'no-store' in (h.get('Cache-Control') or ''), (st, h.get('Cache-Control')))
st, h, body = headers(Client('203.0.113.50'), 'offer')
check('öffentliches Angebot bleibt zwischenspeicherbar (Offline)', st == 200 and 'no-store' not in (h.get('Cache-Control') or ''), h.get('Cache-Control'))

# ---------- Keine internen Importangaben im ausgelieferten Angebot ----------
pub = A.call('draft')[1]['published']
pub['meta']['source'] = 'Interne-Datei_KW43.xlsx'; pub['meta']['sheetName'] = 'Blatt Intern'
pub['items'][0]['cell'] = 'B12'
assert A.call('publish', {'model': pub})[0] == 200
off = Client('203.0.113.51').call('offer')[1]['offer']
txt = json.dumps(off, ensure_ascii=False)
check('öffentlich: kein Dateiname, kein Blattname, keine Zelladresse', 'Interne-Datei' not in txt and 'Blatt Intern' not in txt and '"cell"' not in txt)
check('Mitarbeiter-Entwurf behält die Angaben', A.call('draft')[1]['published']['meta'].get('source') == 'Interne-Datei_KW43.xlsx')


# ---------- Kunde: Passwort raten begrenzt ----------
def kunde(username, firma, angebote, gruppe=''):
    rev = A.call('kunden')[1]['rev']
    st, r = A.call('kunde_save', {'rev': rev, 'firma': firma, 'nr': username.upper()[:10], 'email': username + '@example.org', 'active': True, 'angebote': angebote, 'gruppe': gruppe,
                                  'login': {'username': username, 'password': KPW, 'mustChange': False, 'active': True}})
    assert st == 200, r
    return r['customer']['id']


kid = kunde('kantine.druck', 'Kantine Druck GmbH', ['edeka'])
K = Client('203.0.113.30'); assert K.call('kunde_login', {'username': 'kantine.druck', 'password': KPW})[0] == 200
codes = [K.call('kunde_passwort', {'current': f'Falsch-{i}-Kennwort', 'password': 'Neues-Kennwort-77'})[0] for i in range(5)]
check('4 Fehlversuche → 422, der 5. meldet ab (401)', codes == [422, 422, 422, 422, 401], codes)
check('… danach ist die Sitzung beendet', K.call('kunde_merkliste')[0] == 401)
K = Client('203.0.113.31'); assert K.call('kunde_login', {'username': 'kantine.druck', 'password': KPW})[0] == 200

# ---------- Bestell-E-Mail: Betreff mit Jahr, „Warenwert (ca.)“ ----------
assert A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
o = K.call('offer&angebot=edeka')[1]['offer']
it = next(i for i in o['items'] if i['price']['status'] == 'value')
n0 = len(smtp.messages)
st, r = K.call('kunde_bestellung', {'angebot': 'edeka', 'publishedAt': o.get('publishedAt', ''), 'positions': [{'id': it['id'], 'qty': 2}], 'requestId': 'druck-request-000000001'})
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
check('Bestell-E-Mail: Betreff mit KW und Jahr', st == 200 and re.search(r'\(KW \d+/\d{4}\)', m.get('subject', '')), m.get('subject'))
check('Bestell-E-Mail: „Warenwert (ca.)“ in Text und HTML', 'Warenwert (ca.)' in (m.get('text') or '') and 'Warenwert (ca.)' in (m.get('html') or '') and 'Summe (ca.)' not in (m.get('html') or ''))

# ---------- Einzelangebot-PDF: lange Texte ----------
TITEL = 'Sonderaktion Grill- und Herbstsaison mit Färse, Kalb und Lamm aus eigener Zerlegung für die Kantine (Teil 2)'
bis = (date.today() + timedelta(days=20)).isoformat()
st, r = A.call('einzel_save', {'kid': kid, 'titel': TITEL, 'gueltigBis': bis, 'hinweis': 'Nur dienstags',
                               'positions': [{'code': 'ABCDEFGHIJ-1234567', 'name': 'Lange Nummer', 'qty': 3, 'price': 12.5}, {'code': '10601', 'name': 'Roastbeef', 'qty': None, 'price': 23.9}]})
e = r['angebot']
e = A.call('einzel_status', {'id': e['id'], 'revision': e['revision'], 'status': 'freigegeben'})[1]['angebot']
st, h, pdf = headers(A, 'einzel_pdf&id=' + e['id'])
inh = pdf_inhalt(pdf) if st == 200 else ''
check('PDF: langer Titel gekürzt (…) statt über den Rand', st == 200 and '…' in inh and TITEL not in inh, st)
check('PDF: lange Artikelnummer vollständig', 'ABCDEFGHIJ-1234567' in inh)
stand = date.fromisoformat(e['freigegebenAt'][:10]).strftime('%d.%m.%Y')
check('PDF: Stand = Freigabe des Angebots', 'Stand ' + stand in inh, stand)

# kleines Einzelangebot (2 Positionen) für den Portal-Druck
st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Kurzangebot', 'gueltigBis': bis, 'hinweis': 'Lieferung nur dienstags',
                               'positions': [{'code': '10601', 'name': 'Roastbeef', 'qty': None, 'price': 23.9}, {'code': '', 'name': 'Freie Position', 'qty': None, 'price': None}]})
k2 = r['angebot']
k2 = A.call('einzel_status', {'id': k2['id'], 'revision': k2['revision'], 'status': 'freigegeben'})[1]['angebot']

# Preis mit drei Nachkommastellen im Angebot (Anzeige wie Abrechnung: zwei Stellen)
pub = A.call('draft')[1]['published']
pub['items'][0]['price'] = {'status': 'value', 'value': 4.125}
PCODE = pub['items'][0]['code']
assert A.call('publish', {'model': pub})[0] == 200
PUB_DATE = date.fromisoformat(A.call('draft')[1]['published']['publishedAt'][:10]).strftime('%d.%m.%Y')

errors = []
INIT = 'window.print = () => { window.__printed = (window.__printed || 0) + 1; };'


def drucken(pg, layout, grouped=True, scope='all'):
    pg.evaluate("""([l, g, s]) => { const f = document.querySelector('#print-form');
      f.querySelector(`input[name=scope][value=${s}]`).checked = true; f.querySelector(`input[name=layout][value=${l}]`).checked = true;
      f.querySelector('input[name=grouped]').checked = g; f.requestSubmit(); }""", [layout, grouped, scope])
    pg.wait_for_timeout(250)


with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- Portal: Druck im Dunkelmodus ----------
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, color_scheme='dark')
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    pg.goto(BASE + '/'); pg.wait_for_selector('#modebar'); pg.wait_for_timeout(300)
    check('Bildschirm: Dunkelmodus aktiv', pg.evaluate("getComputedStyle(document.body).backgroundColor") != 'rgb(255, 255, 255)')
    drucken(pg, 'liste')
    pg.emulate_media(media='print', color_scheme='dark')
    col = pg.evaluate("(() => { const e = document.querySelector('#print-root .al-brand'); return e ? getComputedStyle(e).color : null; })()")
    cs = pg.evaluate("getComputedStyle(document.documentElement).colorScheme")
    logo = pg.evaluate("(() => { const e = document.querySelector('#print-root .al-logo'); return e ? getComputedStyle(e).backgroundColor : null; })()")
    check('Druck im Dunkelmodus: helle Farben (Marke bordeaux, color-scheme light, Logo ohne Kasten)', col == 'rgb(140, 29, 44)' and cs == 'light' and logo in ('rgba(0, 0, 0, 0)', 'transparent'), (col, cs, logo))
    pg.emulate_media(media='screen')
    ctx.close()

    # ---------- Portal: Kunde, Kompaktdruck, Einzelangebot ----------
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    k = ctx.new_page(); k.on('pageerror', lambda ex: errors.append(str(ex)))
    k.goto(BASE + '/'); k.wait_for_selector('#modebar')
    k.click('#modebar [data-mode=liste]'); k.wait_for_selector('tr.row')
    ptxt = k.locator(f'tr.row:has-text("{PCODE}") .c-price').first.inner_text()
    check('Preis 4,125 wird wie abgerechnet mit 4,13 angezeigt', '4,13' in ptxt and '4,125' not in ptxt, ptxt)
    k.click('#btn-kunde-login'); k.wait_for_selector('#kl-form')
    k.fill('#kl-form [name=username]', 'kantine.druck'); k.fill('#kl-form [name=password]', KPW); k.click('#kl-form [type=submit]')
    k.wait_for_selector('.k-switch, .k-banner'); k.wait_for_timeout(400)
    if k.locator('.k-switch [data-kswitch="edeka"]').count():
        with k.expect_navigation():
            k.click('.k-switch [data-kswitch="edeka"]')
        k.wait_for_selector('#kw-pill'); k.wait_for_timeout(300)
    drucken(k, 'compact')
    head = k.locator('#print-root .p-head')
    check('Kompaktdruck: Logo im Kopf', head.locator('img.p-logo').count() == 1)
    check('Kompaktdruck: Name des Kundenangebots im Titel', 'Wochenangebot Edeka' in head.locator('.p-title').inner_text(), head.locator('.p-title').inner_text())
    check('Kompaktdruck: Stand = Veröffentlichung (wie Angebotsliste)', 'Stand: ' + PUB_DATE in head.inner_text(), head.inner_text())
    gtxt = ' '.join(k.locator('#print-root .p-gh').all_inner_texts()[:40])
    check('Kompaktdruck: Gruppen mit „…“ statt "…"', '"' not in gtxt, gtxt[:200])
    drucken(k, 'table')
    check('Tabellendruck: Logo und Angebotsname', k.locator('#print-root .p-head img.p-logo').count() == 1 and 'Wochenangebot Edeka' in k.locator('#print-root .p-title').inner_text())
    # ungegliedert nach Preis: Überschrift und Reihenfolge passen zusammen
    k.select_option('#sort', 'price-asc'); k.wait_for_timeout(200)
    drucken(k, 'liste', grouped=False)
    gt = k.locator('#print-root .al-gt').first.inner_text()
    prices = [float(x.replace('.', '').replace(',', '.')) for x in k.locator('#print-root .al-tab td.c-price').all_inner_texts()[:30] if re.match(r'^[\d.]+,\d\d$', x.strip())]
    check('ungegliederter Druck: Überschrift „nach Preis“ und aufsteigende Preise', 'sortiert nach Preis' in gt and len(prices) > 5 and prices == sorted(prices), (gt, prices[:5]))
    k.select_option('#sort', 'offer-asc'); k.wait_for_timeout(200)
    # leere Auswahl + Strg+P: ganzes Angebot statt leerer Seiten
    k.fill('#q', 'zzzz-kein-treffer'); k.wait_for_timeout(400)
    k.evaluate("window.dispatchEvent(new Event('beforeprint'))"); k.wait_for_timeout(200)
    check('Strg+P bei leerer Auswahl druckt das ganze Angebot', k.locator('#print-root tr.row').count() > 10, k.locator('#print-root tr.row').count())
    k.evaluate("window.dispatchEvent(new Event('afterprint'))")
    k.fill('#q', ''); k.wait_for_timeout(300)

    # Einzelangebot mit zwei Positionen
    k.goto(BASE + '/?angebot=e-' + k2['id']); k.wait_for_selector('#kw-pill'); k.wait_for_timeout(400)
    k.click('#btn-print'); k.wait_for_selector('#dlg-print[open]')
    check('Druckdialog im Einzelangebot: „Alle Positionen dieses Angebots“', k.inner_text('#print-all-desc') == 'Alle Positionen dieses Angebots', k.inner_text('#print-all-desc'))
    k.keyboard.press('Escape')
    drucken(k, 'liste')
    check('Einzelangebot-Druck: zwei Positionen nicht auf zwei Spalten verteilt', k.locator('#print-root .al-cont').count() == 0 and k.locator('#print-root .al-grp').count() == 1,
          k.locator('#print-root .al-grp').count())
    sub = k.locator('#print-root .pl-pt > span').first.inner_text()
    check('Einzelangebot-Druck: Kopf mit Angebotsnummer und Kunde', k2['nr'] in sub and 'Kantine Druck GmbH' in sub, sub)
    check('Einzelangebot-Druck: Hinweis auf dem Blatt', 'Lieferung nur dienstags' in k.locator('#print-root').inner_text())
    k.evaluate("window.dispatchEvent(new Event('afterprint'))")
    # Abmelden entfernt angefangene Bestellwünsche
    k.goto(BASE + '/'); k.wait_for_selector('.k-switch, .k-banner')
    k.evaluate("localStorage.setItem('wochenangebot.bestellung.kantine.druck.edeka', JSON.stringify({ x: { q: 2, k: 'a' } }))")
    with k.expect_navigation():
        k.evaluate("document.querySelector('[data-kact=logout]').click()")
    k.wait_for_selector('#modebar')
    left = k.evaluate("Object.keys(localStorage).filter((x) => x.startsWith('wochenangebot.bestellung.kantine.druck.'))")
    check('Abmelden: Bestellwunsch-Entwurf des Kunden entfernt', left == [], left)
    ctx.close()

    # ---------- Eingabebereich: Druck und Sitzungsende ----------
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); a.on('pageerror', lambda ex: errors.append(str(ex)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.evaluate("document.querySelector('#vt-kunden').click()"); a.wait_for_selector('#view-kunden .ktab, #view-kunden table'); a.wait_for_timeout(300)
    a.emulate_media(media='print')
    vis = a.evaluate("""(() => { const v = (s) => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0; };
      return { view: v('#view-kunden'), nav: v('.side-nav'), actions: v('.topbar .actions') }; })()""")
    check('Strg+P im Eingabebereich: Ansicht sichtbar, Navigation und Knöpfe nicht', vis == {'view': True, 'nav': False, 'actions': False}, vis)
    a.emulate_media(media='screen')
    a.locator('#view-kunden [data-k-edit], #view-kunden button:has-text("Bearbeiten")').first.click(); a.wait_for_selector('#dlg-kunde[open]')
    a.emulate_media(media='print')
    vis = a.evaluate("""(() => ({ dlg: getComputedStyle(document.querySelector('#dlg-kunde')).display !== 'none', editor: getComputedStyle(document.querySelector('#screen-editor')).display }))()""")
    check('Strg+P mit offenem Fenster: nur das Fenster', vis['dlg'] and vis['editor'] == 'none', vis)
    a.emulate_media(media='screen'); a.keyboard.press('Escape'); a.wait_for_timeout(200)
    # Sitzung endet → Anmeldung deckt die Daten ab
    ctx.clear_cookies()
    a.evaluate("document.querySelector('#vt-orders').click()"); a.wait_for_selector('#screen-auth.overlay:not([hidden])', timeout=10000)
    check('nach Sitzungsende: Daten hinter der Anmeldung verborgen', a.evaluate("getComputedStyle(document.querySelector('#screen-editor')).visibility") == 'hidden'
          and a.evaluate("getComputedStyle(document.querySelector('#screen-auth')).backgroundColor") not in ('rgba(0, 0, 0, 0)',))
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
