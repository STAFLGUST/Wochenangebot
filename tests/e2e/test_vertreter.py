"""Stammdaten → Vertreter (Liste aus der Warenwirtschaft) und die Felder „Vertreter“ und „Vertreter 2“ in den Kunden:
Rechte, Prüfungen, Revision, CSV-Import Windows-1252, Zuordnung im Kunden (nur bekannte Vertreter), Anzahl Kunden je
Vertreter, Kundenimport mit Vertreter-Spalten, Anzeige, Filter, 390 px. Nur Testdaten (tests/fixtures/kunden)."""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, FIX, SH, storage_raw

PW = 'Sicheres-Passwort-1'
VT_CSV = FIX + '/kunden/vertreter.csv'
KG_CSV = FIX + '/kundengruppen/kundengruppen.csv'
KD_CSV = FIX + '/kunden/kundendaten.csv'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}

# ---------- Vertreter: Schnittstelle ----------
check('ohne Anmeldung gesperrt', Client().call('vertreter')[0] == 401)
st, r = L.call('vertreter')
check('Leser darf ansehen (leer)', st == 200 and r['groups'] == [] and 'kunden' not in r, r)
check('Leser darf nicht speichern', L.call('vertreter_save', {'rev': 0, 'groups': [{'nr': '3', 'name': 'X'}]})[0] == 403)
check('Speichern nur per POST', E.call('vertreter_save')[0] == 405)
check('Name fehlt → 422', E.call('vertreter_save', {'rev': 0, 'groups': [{'nr': '3', 'name': ''}]})[0] == 422)
check('doppelte Nummer → 422', E.call('vertreter_save', {'rev': 0, 'groups': [{'nr': '3', 'name': 'A'}, {'nr': '03', 'name': 'B'}]})[0] == 422)
st, r = E.call('vertreter_save', {'rev': 0, 'groups': [{'nr': '11', 'name': 'Jana Müller', 'kurz': 'Müller', 'telefon': '040-11', 'ort': '', 'klasse': 'x'}, {'nr': '3', 'name': 'Tom <Testmann>'}], 'quelle': 'Test'})
check('Bearbeiter speichert: Felder der Vertreter, sortiert, fremde Felder entfallen', st == 200 and [g['nr'] for g in r['groups']] == ['3', '11'] and r['groups'][1] == {'nr': '11', 'name': 'Jana Müller', 'kurz': 'Müller', 'telefon': '040-11', 'plz': '', 'ort': '', 'land': ''}, r)
check('veraltete Revision → 409', E.call('vertreter_save', {'rev': 0, 'groups': []})[0] == 409)
check('getrennt von Kunden- und VK-Gruppen', A.call('kundengruppen')[1]['groups'] == [] and A.call('vkgruppen')[1]['groups'] == [])
check('Protokoll: Vertreter übernommen', 'Vertreter aus „Test“ übernommen: 2 neu' in json.dumps(A.call('log')[1], ensure_ascii=False))
st, r = A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.sehen'], 'deny': ['stammdaten.sehen']})
check('nur Kundenrecht reicht zum Ansehen (für den Kunden-Dialog)', st == 200 and E.call('vertreter')[0] == 200)
A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': ['stammdaten.sehen']})
check('ohne Stammdaten- und Kundenrecht gesperrt', E.call('vertreter')[0] == 403)
A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': []})

# ---------- Vertreter im Kunden ----------
rev = A.call('kunden')[1]['rev']
base = {'firma': 'Vertretertest GmbH', 'nr': 'V-1', 'active': True, 'angebote': []}
check('unbekannter Vertreter abgewiesen', A.call('kunde_save', {**base, 'rev': rev, 'vertreter': '99'})[0] == 422)
check('unbekannter Vertreter 2 abgewiesen', A.call('kunde_save', {**base, 'rev': rev, 'vertreter': '3', 'vertreter2': '98'})[0] == 422)
st, r = A.call('kunde_save', {**base, 'rev': rev, 'vertreter': '3', 'vertreter2': '11'})
check('Vertreter und Vertreter 2 gespeichert', st == 200 and r['customer']['vertreter'] == '3' and r['customer']['vertreter2'] == '11', r)
kid = r['customer']['id']
check('Anzahl Kunden je Vertreter', A.call('vertreter')[1]['kunden'] == {'3': 1, '11': 1})
check('Protokoll: Vertreter am Kunden', 'Vertreter 2' in json.dumps(A.call('log')[1], ensure_ascii=False))
rv = A.call('vertreter')[1]['rev']
assert A.call('vertreter_save', {'rev': rv, 'groups': [{'nr': '3', 'name': 'Tom Testmann'}]})[0] == 200
rev = A.call('kunden')[1]['rev']
check('entfernter Vertreter bleibt beim unveränderten Kunden', A.call('kunde_save', {**base, 'id': kid, 'rev': rev, 'vertreter': '3', 'vertreter2': '11', 'firma': 'Vertretertest GmbH & Co'})[0] == 200)
rev = A.call('kunden')[1]['rev']
check('… aber nicht neu zuordenbar', A.call('kunde_save', {'firma': 'Anderer', 'nr': 'V-2', 'active': True, 'rev': rev, 'vertreter2': '11'})[0] == 422)

# ---------- Kundenimport mit Vertreter ----------
rows = [{'nr': 'V-1', 'firma': 'egal', 'vertreter': '3', 'vertreter2': ''}, {'nr': 'V-3', 'firma': 'Neu mit Vertreter', 'vertreter': '3', 'vertreter2': '77'}]
st, r = A.call('kunden_import', {'pruefen': True, 'rows': rows})
check('Import-Vorschau: unbekannter Vertreter gemeldet', st == 200 and r['vertreterUnbekannt'] == {'77': 1} and r['stat']['neu'] == 1, r)
st, r = A.call('kunden_import', {'rev': r['rev'], 'rows': rows})
cs = {c['nr']: c for c in doc('kunden')['customers']}
check('Import: Vertreter übernommen, unbekannter leer, leerer überschreibt nicht', st == 200 and cs['V-3']['vertreter'] == '3' and cs['V-3']['vertreter2'] == '' and cs['V-1']['vertreter2'] == '11', {k: (cs[k]['vertreter'], cs[k]['vertreter2']) for k in ('V-1', 'V-3')})
rv = A.call('vertreter')[1]['rev']
assert A.call('vertreter_save', {'rev': rv, 'groups': []})[0] == 200   # für den Oberflächentest leeren

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Vertreter unter Stammdaten nach Kundengruppen', a.locator('#vt-vertreter').is_visible() and y('#vt-gruppen') < y('#vt-vertreter') < y('#side-admin'))

    # ---------- Vertreter: Oberfläche ----------
    a.click('#vt-vertreter'); a.wait_for_selector('#view-vertreter .ed-empty')
    check('leere Liste nennt die erwarteten Spalten', 'Alpha; Name1' in a.inner_text('#view-vertreter'))
    a.set_input_files('#vt-file', KG_CSV); a.wait_for_selector('#toast.show:has-text("Gruppenliste")')
    check('falsche Datei (Kundengruppen) wird erkannt', not a.locator('#dlg-vt-import').evaluate('d => d.open'))
    a.set_input_files('#vt-file', KD_CSV); a.wait_for_selector('#toast.show:has-text("Kundendaten-Export")')
    check('falsche Datei (Kundendaten) wird erkannt', not a.locator('#dlg-vt-import').evaluate('d => d.open'))
    a.set_input_files('#vt-file', VT_CSV); a.wait_for_selector('#dlg-vt-import[open]')
    check('Vorschau: 4 neue Vertreter', a.inner_text('#vti-neu') == '4', a.inner_text('#vt-import-body'))
    a.click('#vti-ok'); a.wait_for_selector('#view-vertreter tr[data-kg="3"]')
    g = {x['nr']: x for x in doc('vertreter')['groups']}
    check('übernommen mit Umlauten (Windows-1252), Kurzname, Ort', len(g) == 4 and g['11']['name'] == 'Jana Müller' and g['26']['name'] == 'Großhandel Test GmbH' and g['26']['ort'] == 'Köln' and g['3']['kurz'] == 'Testmann', g.get('26'))
    t = a.inner_text('#view-vertreter thead')
    check('Liste: Name, Kurzname, Telefon, Ort, Kunden', all(s in t for s in ('Name', 'Kurzname', 'Telefon', 'Ort', 'Kunden')), t)
    a.click('#view-vertreter tr[data-kg="11"]'); a.wait_for_selector('#dlg-vtruppe[open]')
    check('Dialog mit allen Feldern', all(a.locator(f'#vtruppe-body [name="{f}"]').count() == 1 for f in ('nr', 'name', 'kurz', 'telefon', 'plz', 'ort', 'land')))
    a.fill('#vtruppe-body [name=telefon]', '040-999'); a.click('#vtruppe-body [type=submit]')
    a.wait_for_function("!document.querySelector('#dlg-vtruppe').open")
    check('Vertreter jederzeit änderbar', next(x for x in doc('vertreter')['groups'] if x['nr'] == '11')['telefon'] == '040-999')
    a.screenshot(path=SH + '/vertreter.png')

    # ---------- Vertreter im Kunden ----------
    a.click('#vt-kunden'); a.wait_for_selector('#k-list tr[data-kid]')
    a.click('#k-list tr[data-kid]:has-text("Vertretertest")'); a.wait_for_selector('#dlg-kunde[open]')
    check('Kunden-Dialog: Vertreter-Auswahl mit Namen', 'Tom Testmann (Testmann) · 3' in a.inner_text('#kunde-body [name="vertreter"]') and a.input_value('#kunde-body [name="vertreter"]') == '3'
          and a.input_value('#kunde-body [name="vertreter2"]') == '11')
    a.select_option('#kunde-body [name="vertreter2"]', '26'); a.click('#kunde-body [type=submit]')
    a.wait_for_function("!document.querySelector('#dlg-kunde').open", timeout=10000)
    check('Vertreter 2 im Kunden gespeichert', next(c for c in doc('kunden')['customers'] if c['id'] == kid)['vertreter2'] == '26')
    a.wait_for_selector('#k-list tr[data-kid]:has-text("Vertretertest") .k-vt')
    check('Kundenliste zeigt die Vertreter-Namen', 'Tom Testmann · Großhandel Test GmbH' in a.inner_text('#k-list tr[data-kid]:has-text("Vertretertest") .k-vt'))
    a.select_option('#k-v', '26'); a.wait_for_function("document.querySelector('#k-count').textContent.startsWith('1 Kunde')")
    check('Filter nach Vertreter', a.locator('#k-list tr[data-kid]').count() == 1)
    a.select_option('#k-v', '')
    a.fill('#k-q', 'jana'); a.wait_for_function("document.querySelectorAll('#k-list tr[data-kid]').length === 0")
    a.fill('#k-q', 'großhandel'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Vertretertest")')
    check('Suche findet Kunden über den Vertreter', a.locator('#k-list tr[data-kid]').count() == 1)
    a.fill('#k-q', '')
    a.set_input_files('#k-file', VT_CSV); a.wait_for_selector('#toast.show:has-text("Vertreter-Export")')
    check('Kundenimport erkennt den Vertreter-Export', not a.locator('#dlg-k-import').evaluate('d => d.open'))
    a.set_input_files('#k-file', KD_CSV); a.wait_for_selector('#dlg-k-import[open] #ki-neu')
    a.click('#k-import-body [data-ki="ok"]'); a.wait_for_selector('#toast.show:has-text("Kunden übernommen")', timeout=15000)
    check('Kundenimport übernimmt den Vertreter aus der Datei', all(c.get('vertreter') == '3' for c in doc('kunden')['customers'] if c.get('nr', '').startswith('100000')))
    a.wait_for_selector('#k-list tr[data-kid]')
    a.select_option('#k-v', '3'); a.wait_for_function("/^\\d+ Kunden/.test(document.querySelector('#k-count').textContent)")
    check('Filter: importierte Kunden beim Vertreter', a.locator('#k-list tr[data-kid]').count() >= 5, a.inner_text('#k-count'))
    a.screenshot(path=SH + '/kunden-vertreter.png')
    a.set_viewport_size({'width': 390, 'height': 820})
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Kundenliste 390 px: kein seitliches Scrollen', over <= 1, over)
    a.click('#vt-vertreter'); a.wait_for_selector('#view-vertreter tr[data-kg]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Vertreter 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/vertreter-mobil.png')
    lp = br.new_page(viewport={'width': 1280, 'height': 900})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#vt-vertreter:not([hidden])')
    lp.click('#vt-vertreter'); lp.wait_for_selector('#view-vertreter tr[data-kg]')
    check('Leser: Vertreter nur ansehen', lp.locator('#vt-import').count() == 0 and lp.locator('#vt-add').count() == 0)
    lp.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
