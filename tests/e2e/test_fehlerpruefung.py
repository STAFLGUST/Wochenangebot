"""Regressionstests der Design- und Fehlerprüfung: Angebots-IDs, Kundenpreise unter Zahlen-IDs, Einzelangebote
(Senden, Leeren, Mengen, Hinweis/Titel/CSV im Portal), Kundenimport (Nummern ohne führende Null, Zeilen ohne Nummer),
Rechte von mail_info und history_prev, Bestellwunsch mit verschobenen Positionen, Filter-Schublade (inert) und
mobile Darstellung im Eingabebereich. Nur synthetische Testdaten; es werden keine echten E-Mails versendet."""
import csv
import io
import json
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SMTP_PORT, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200

# ---------- Angebots-IDs ----------
o = A.call('offers')[1]
base = [dict(x) for x in o['offers']]
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': base + [{'id': 'e-center', 'name': 'Wochenangebot E-Center', 'fallback': 'standard'}]})
check('neue Angebots-ID „e-…“ abgewiesen (gehört Einzelangeboten)', st == 422 and 'e-' in r.get('error', ''), r)
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': base + [{'id': '24', 'name': 'Wochenangebot 24', 'fallback': 'standard'}]})
check('neue Angebots-ID nur aus Ziffern abgewiesen', st == 422, r)
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': base + [{'id': 'angebot-24', 'name': 'Wochenangebot 24', 'fallback': 'standard'}]})
check('erlaubte ID wird gespeichert', st == 200 and any(x['id'] == 'angebot-24' for x in r['offers']), r)

# bestehendes Angebot mit Zahlen-ID (ältere Daten): Kundenpreise dürfen beim Speichern nicht verloren gehen
ang = doc('angebote')
ang['offers'].append({'id': '77', 'name': 'Altes Angebot 77', 'fallback': 'standard'})
storage_write('angebote', ang)
o = A.call('offers')[1]
check('bestehende Zahlen-ID bleibt speicherbar', E.call('offers_save', {'rev': o['rev'], 'offers': o['offers']})[0] == 200)
d = A.call('draft')[1]
model = d['draft'] or d['published']
it0 = model['items'][0]
it0['variants'] = {**(it0.get('variants') or {}), '77': {'status': 'value', 'value': 19.5}}
st, r = E.call('save_draft', {'revision': d['revision'], 'model': model})
saved = next(i for i in doc('entwurf')['items'] if i['id'] == it0['id'])
check('Kundenpreis unter Zahlen-ID bleibt im Entwurf erhalten', st == 200 and saved.get('variants', {}).get('77') == {'status': 'value', 'value': 19.5}, saved.get('variants'))

# ---------- Rechte: mail_info, history_prev ----------
check('mail_info ohne Anmeldung gesperrt', Client().call('mail_info')[0] == 401)
check('mail_info ohne Kunden-/Senderecht gesperrt', E.call('mail_info')[0] == 403)
check('mail_status bleibt Administratoren vorbehalten', E.call('mail_status')[0] == 403)
assert A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.sehen', 'einzelangebote.sehen', 'einzelangebote.bearbeiten'], 'deny': []})[0] == 200
st, r = E.call('mail_info')
check('mail_info mit Kundenrecht: nur Status, keine Zugangsdaten', st == 200 and set(r) == {'ok', 'configured', 'week', 'testumgebung'}, r)
check('history_prev für Leser (Preisverlauf ansehen) erlaubt', L.call('history_prev&week=40&year=2026')[0] == 200)
assert A.call('user_save', {'id': uid['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': [], 'deny': ['preisverlauf.sehen']})[0] == 200
check('history_prev ohne Preisverlauf- und Bearbeitungsrecht gesperrt', L.call('history_prev&week=40&year=2026')[0] == 403)
assert A.call('user_save', {'id': uid['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': [], 'deny': []})[0] == 200


# ---------- Einzelangebote ----------
def kunde(username, firma):
    rev = A.call('kunden')[1]['rev']
    st, r = A.call('kunde_save', {'rev': rev, 'firma': firma, 'nr': username.upper()[:10], 'email': username + '@example.org', 'active': True, 'angebote': ['std'],
                                  'login': {'username': username, 'password': KPW, 'mustChange': False, 'active': True}})
    assert st == 200, r
    return r['customer']['id']


kid = kunde('kantine.pruef', 'Kantine Prüfung')
bis = (date.today() + timedelta(days=10)).isoformat()
POS = [{'code': '10601', 'name': 'Roastbeef, frisch', 'qty': 5, 'price': 23.9}, {'code': '10823', 'name': 'Steakhüfte, frisch', 'qty': 0.004 + 2, 'price': 18.5}]
st, r = E.call('einzel_save', {'kid': kid, 'positions': [{'code': '1', 'name': 'X', 'qty': 0.004}]})
check('Menge 0,004 kg (gerundet 0) abgewiesen statt als 0 kg gespeichert', st == 422, r)
st, r = E.call('einzel_save', {'kid': kid, 'titel': 'Prüfangebot', 'gueltigBis': bis, 'hinweis': 'Lieferung nur dienstags\nAbholung möglich', 'positions': POS})
e = r['angebot']
check('Menge wird gerundet gespeichert', st == 200 and e['positions'][1]['qty'] == 2.0, e['positions'])
st, r = E.call('einzel_status', {'id': e['id'], 'revision': e['revision'], 'status': 'freigegeben'})
e = r['angebot']
st, r = E.call('einzel_save', {'id': e['id'], 'revision': e['revision'], 'kid': kid, 'titel': 'Prüfangebot', 'gueltigBis': bis, 'positions': []})
check('freigegebenes Einzelangebot kann nicht geleert werden', st == 422 and 'Position' in r.get('error', ''), r)
check('… Positionen bleiben unverändert', len(next(x for x in doc('einzelangebote')['list'] if x['id'] == e['id'])['positions']) == 2)
EID = 'e-' + e['id']

# zweites Angebot: zurückgezogen bzw. abgelaufen → kein Versand
st, r = E.call('einzel_save', {'kid': kid, 'titel': 'Zurückgezogen', 'gueltigBis': bis, 'positions': POS[:1]})
z = r['angebot']
z = E.call('einzel_status', {'id': z['id'], 'revision': z['revision'], 'status': 'freigegeben'})[1]['angebot']
z = E.call('einzel_status', {'id': z['id'], 'revision': z['revision'], 'status': 'zurueckgezogen'})[1]['angebot']
assert E.call('reauth', {'password': 'Editor-Zugang-77'})[0] == 200
n0 = len(smtp.messages)
st, r = E.call('einzel_senden', {'id': z['id']})
check('zurückgezogenes Einzelangebot wird nicht versendet', st == 422 and 'zurückgezogen' in r.get('error', '') and len(smtp.messages) == n0, r)
ez = doc('einzelangebote')
for x in ez['list']:
    if x['id'] == z['id']:
        x['status'] = 'freigegeben'; x['gueltigBis'] = (date.today() - timedelta(days=1)).isoformat()
storage_write('einzelangebote', ez)
st, r = E.call('einzel_senden', {'id': z['id']})
check('abgelaufenes Einzelangebot wird nicht versendet', st == 422 and 'abgelaufen' in r.get('error', '') and len(smtp.messages) == n0, r)

assert A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
K = Client('203.0.113.20'); assert K.call('kunde_login', {'username': 'kantine.pruef', 'password': KPW})[0] == 200
off = K.call('offer&angebot=' + EID)[1]['offer']
check('Portalmodell enthält den Hinweis des Einzelangebots', off['meta'].get('hinweis') == 'Lieferung nur dienstags\nAbholung möglich', off['meta'])

# ---------- Kundenimport ----------
assert A.call('kundengruppen_save', {'rev': A.call('kundengruppen')[1]['rev'], 'groups': [{'nr': '07', 'name': 'Handel'}]})[0] == 200
assert A.call('vertreter_save', {'rev': A.call('vertreter')[1]['rev'], 'groups': [{'nr': '3', 'name': 'Tom Test'}]})[0] == 200
ROWS = [{'nr': '', 'firma': 'Ohne Nummer Imbiss', 'plz': '20095', 'ort': 'Hamburg', 'gruppe': '7', 'vertreter': '003'},
        {'nr': '', 'firma': 'Ohne Nummer Imbiss', 'plz': '20095', 'ort': 'Hamburg', 'gruppe': '7', 'vertreter': '003'},
        {'nr': '4711', 'firma': 'Unbekannte Gruppe AG', 'gruppe': '99'}]
rev0 = A.call('kunden')[1]['rev']
st, r = A.call('kunden_import', {'rev': rev0, 'rows': ROWS, 'quelle': 'synthetisch.csv'})
cs = [c for c in doc('kunden')['customers'] if c['firma'] == 'Ohne Nummer Imbiss']
check('gleiche Zeile ohne Kundennummer nur einmal angelegt', st == 200 and len(cs) == 1 and r['stat']['neu'] == 2, (r.get('stat'), len(cs)))
check('Kundengruppe „7“ passt zu „07“, Vertreter „003“ zu „3“ (Schreibweise der Liste)', cs and cs[0].get('gruppe') == '07' and cs[0].get('vertreter') == '3', cs[:1])
check('unbekannte Gruppen als Objekt (auch bei Zahlen-Schlüsseln)', r.get('gruppenUnbekannt') == {'99': 1} and r.get('vertreterUnbekannt') == {}, r.get('gruppenUnbekannt'))

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()

    # Portal: Einzelangebot mit Hinweis, Titel ohne Doppelung, CSV mit „Gültig bis“
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    k = ctx.new_page()
    k.on('pageerror', lambda ex: errors.append(str(ex)))
    k.goto(BASE + '/'); k.wait_for_selector('#modebar')
    k.click('#btn-kunde-login'); k.wait_for_selector('#kl-form')
    k.fill('#kl-form [name=username]', 'kantine.pruef'); k.fill('#kl-form [name=password]', KPW); k.click('#kl-form [type=submit]')
    k.wait_for_selector('.k-switch, .k-banner')
    k.goto(BASE + '/?angebot=' + EID); k.wait_for_selector('#kw-pill'); k.wait_for_timeout(500)
    note = k.locator('aside[aria-label="Hinweis zum Angebot"]').first
    check('Hinweis des Einzelangebots wird im Portal angezeigt', note.count() and 'Lieferung nur dienstags' in note.inner_text() and 'Abholung möglich' in note.inner_text())
    k.click('#modebar [data-mode=angebot]'); k.wait_for_selector('.al-head h2')
    h2 = k.locator('.al-head h2').first.inner_text()
    check('Angebotsliste: Titel nicht doppelt', h2.count('Prüfangebot') == 1, h2)
    check('Fenstertitel mit „gültig bis“', 'Prüfangebot' in k.title() and 'gültig bis' in k.title(), k.title())
    with k.expect_download() as dl:
        k.evaluate("document.querySelector('[data-action=csv-all]').click()")
    path = dl.value.path()
    rows = list(csv.reader(io.StringIO(open(path, encoding='utf-8-sig').read()), delimiter=';'))
    check('CSV: Spalte „Gültig bis“ statt Kalenderwoche', rows and rows[0][-1] == 'Gültig bis' and rows[1][-1] == '.'.join(reversed(bis.split('-'))), rows[:2])
    check('CSV-Dateiname mit Angebotsnummer', e['nr'] in dl.value.suggested_filename, dl.value.suggested_filename)

    # Bestellwunsch: gemerkte Menge folgt dem Artikel, auch wenn sich die Positionskennung verschoben hat
    k.goto(BASE + '/'); k.wait_for_selector('.k-switch, .k-banner')
    k.click('#modebar [data-mode=liste]'); k.wait_for_selector('tr.row .qty'); k.wait_for_timeout(300)
    info = k.evaluate("""() => { const r = [...document.querySelectorAll('input.qty[data-qty]')].slice(0, 2).map((i) => i.dataset.qty); return r; }""")
    key = k.evaluate("(id) => { const r = document.querySelector(`input.qty[data-qty='${id}']`).closest('tr'); const b = r && r.querySelector('[data-fav]'); return b ? b.dataset.fav : null; }", info[0]) if info else None
    if key:
        k.evaluate("([user, key]) => localStorage.setItem('wochenangebot.bestellung.' + user + '.std', JSON.stringify({ 'alt-999': { q: 3, k: key } }))", ['kantine.pruef', key])
        k.reload(); k.wait_for_selector(f'input.qty[data-qty="{info[0]}"]'); k.wait_for_timeout(400)
        check('gemerkte Menge dem richtigen Artikel zugeordnet (Schlüssel statt Positionskennung)', k.locator(f'input.qty[data-qty="{info[0]}"]').first.input_value() == '3')
        k.evaluate("([user, id]) => localStorage.setItem('wochenangebot.bestellung.' + user + '.std', JSON.stringify({ [id]: 2 }))", ['kantine.pruef', info[1]])
        k.reload(); k.wait_for_selector(f'input.qty[data-qty="{info[1]}"]'); k.wait_for_timeout(400)
        check('älteres Format (nur Menge) wird weiter gelesen', k.locator(f'input.qty[data-qty="{info[1]}"]').first.input_value() == '2')
        k.locator(f'input.qty[data-qty="{info[1]}"]').first.fill('4'); k.keyboard.press('Tab'); k.wait_for_timeout(300)
        saved = k.evaluate("(user) => JSON.parse(localStorage.getItem('wochenangebot.bestellung.' + user + '.std'))", 'kantine.pruef')
        check('nach einer Änderung mit Artikelschlüssel gespeichert', isinstance(saved, dict) and all(isinstance(v, dict) and v.get('k') for v in saved.values()) if saved else True, saved)
    else:
        check('Bestellwunsch-Eingabe im Portal vorhanden', False, info)
    ctx.close()

    # Portal mobil: geschlossene Filter-Schublade ist für Tastatur/Screenreader inaktiv
    m = br.new_page(viewport={'width': 390, 'height': 820})
    m.on('pageerror', lambda ex: errors.append(str(ex)))
    m.goto(BASE + '/'); m.wait_for_selector('#modebar'); m.wait_for_timeout(300)
    check('mobil: geschlossene Filter inert', m.evaluate("document.querySelector('#filters').inert") is True)
    m.click('#btn-filters-open'); m.wait_for_timeout(300)
    check('mobil: geöffnete Filter bedienbar', m.evaluate("document.querySelector('#filters').inert") is False)
    m.keyboard.press('Escape'); m.wait_for_timeout(300)
    check('mobil: nach dem Schließen Fokus zurück auf „Filter“', m.evaluate("document.activeElement && document.activeElement.id") == 'btn-filters-open'
          and m.evaluate("document.querySelector('#filters').inert") is True)
    m.set_viewport_size({'width': 1440, 'height': 900}); m.wait_for_timeout(300)
    check('Desktop: Filter nie inert', m.evaluate("document.querySelector('#filters').inert") is False)
    m.close()

    # Eingabebereich mobil (390 px): kein waagrechtes Scrollen, Angebotskarten mit beschrifteten Feldern
    a = br.new_page(viewport={'width': 390, 'height': 820})
    a.on('pageerror', lambda ex: errors.append(str(ex)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    over = {}
    for v in ('einzel', 'kunden', 'angebote', 'master', 'auswertung'):
        a.evaluate(f"document.querySelector('#vt-{v}').click()")
        a.wait_for_function(f"!document.querySelector('#view-{v}').hidden && !document.querySelector('#view-{v} .spinner')", timeout=10000); a.wait_for_timeout(400)
        over[v] = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('mobil: kein waagrechtes Scrollen (Einzelangebote, Kunden, Angebote, Artikelstammdaten, Auswertung)', all(x <= 1 for x in over.values()), over)
    a.evaluate("document.querySelector('#vt-angebote').click()"); a.wait_for_timeout(400)
    lab = a.evaluate("getComputedStyle(document.querySelector('#view-angebote .oftab tr[data-oi] td.of-fb'), '::before').content")
    check('mobil: Auswahl „Artikel ohne eigenen Preis“ beschriftet', 'Artikel ohne eigenen Preis' in lab, lab)
    a.evaluate("document.querySelector('#vt-einzel').click()"); a.wait_for_selector('#view-einzel tr[data-i], #view-einzel tbody tr'); a.wait_for_timeout(300)
    check('mobil: Einzelangebote-Liste zeigt „bis …“ unter dem Status', a.locator('#view-einzel .ez-bis-m').first.is_visible())
    a.close()

    # Leser: „Auf Angebot anwenden“ erscheint nicht (Entwurf nur lesbar)
    lp = br.new_page(viewport={'width': 1440, 'height': 950})
    lp.on('pageerror', lambda ex: errors.append(str(ex)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#screen-editor:not([hidden])')
    lp.evaluate("document.querySelector('#vt-master').click()")
    lp.wait_for_function("!document.querySelector('#view-master').hidden && !document.querySelector('#view-master .spinner')"); lp.wait_for_timeout(400)
    check('Leser: kein „Auf Angebot anwenden“ in den Artikelstammdaten', lp.locator('[data-ma=apply-all]').count() == 0)
    lp.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
# ---------- Zeitzone: Server rechnet in deutscher Zeit (Mails, Ausdrucke, Gültigkeit) ----------
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402
st, r = A.call('security_diag', {'check': 'php'})
zeile = next((x['value'] for x in (r.get('result') or {}).get('items', []) if x['label'] == 'Serverzeit'), '')
try:
    abw = abs((datetime.strptime(zeile[:19], '%d.%m.%Y %H:%M:%S').replace(tzinfo=ZoneInfo('Europe/Berlin')) - datetime.now(ZoneInfo('Europe/Berlin'))).total_seconds())
except ValueError:
    abw = 9999
check('Serverzeit in deutscher Zeit (Europe/Berlin), nicht UTC', st == 200 and 'Europe/Berlin' in zeile and abw < 120, (st, zeile, abw))

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
