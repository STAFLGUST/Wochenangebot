"""Stammdaten → VK-Gruppen und Import der Artikelstammdaten (CSV-Export der Warenwirtschaft): VK-Gruppen-Liste (Rechte,
Prüfungen, Revision, CSV-Import Windows-1252, anlegen/ändern/löschen), VK-Gruppe und GTIN in den Artikelstammdaten
(Prüfung, Anzahl je Gruppe), Artikelimport mit Vorschau (neu/ergänzt/unverändert/übersprungen), gepflegte Merkmale bleiben,
EK/Bestand/Umsatz werden nicht übernommen, Filter nach VK-Gruppe, 390 px. Nur Testdaten (tests/fixtures/stammdaten)."""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, FIX, SH, storage_raw

PW = 'Sicheres-Passwort-1'
VK_CSV = FIX + '/stammdaten/vkgruppen.csv'
ART_CSV = FIX + '/stammdaten/artikelstammdaten.csv'
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

# ---------- VK-Gruppen: Schnittstelle ----------
check('ohne Anmeldung gesperrt', Client().call('vkgruppen')[0] == 401)
st, r = L.call('vkgruppen')
check('Leser darf ansehen (leer, Artikelanzahl)', st == 200 and r['groups'] == [] and r['rev'] == 0 and r['artikel'] == {}, r)
check('Leser darf nicht speichern', L.call('vkgruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'X'}]})[0] == 403)
check('Speichern nur per POST', E.call('vkgruppen_save')[0] == 405)
check('doppelte Nummer abgewiesen', E.call('vkgruppen_save', {'rev': 0, 'groups': [{'nr': '1600', 'name': 'A'}, {'nr': '01600', 'name': 'B'}]})[0] == 422)
check('fehlende Bezeichnung abgewiesen', E.call('vkgruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': ''}]})[0] == 422)
st, r = E.call('vkgruppen_save', {'rev': 0, 'groups': [{'nr': '6150', 'name': 'Rind gefroren'}, {'nr': '1600', 'name': 'Rind <frisch>', 'klasse': '11', 'kategorie': '1'}], 'quelle': 'Test'})
check('Bearbeiter speichert, sortiert nach Nummer', st == 200 and [g['nr'] for g in r['groups']] == ['1600', '6150'] and r['neu'] == 2 and r['groups'][0]['name'] == 'Rind <frisch>', r)
check('veraltete Revision abgewiesen', E.call('vkgruppen_save', {'rev': 0, 'groups': []})[0] == 409)
check('getrennt von den Kundengruppen', A.call('kundengruppen')[1]['groups'] == [] and doc('vkgruppen')['rev'] == 1)
check('Protokoll: VK-Gruppen übernommen', 'VK-Gruppen aus „Test“ übernommen: 2 neu' in json.dumps(A.call('log')[1], ensure_ascii=False))
st, r = A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.sehen'], 'deny': ['stammdaten.sehen']})
check('Nutzer ohne Stammdatenrecht (nur Kundenrecht) sieht keine VK-Gruppen', st == 200 and E.call('vkgruppen')[0] == 403 and E.call('kundengruppen')[0] == 200)
A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': []})

# ---------- VK-Gruppe und GTIN in den Artikelstammdaten ----------
m = A.call('master')[1]['master']
base = [{'code': '10601', 'name': 'Roastbeef', 'category': 'Rind', 'origin': 'AR', 'condition': 'frisch', 'vkGruppe': '1600', 'gtin': '4260000106010'}]
check('ungültige GTIN abgewiesen', E.call('master_save', {'rev': m['rev'], 'articles': [{**base[0], 'gtin': '12ab'}]})[0] == 422)
check('ungültige VK-Gruppe abgewiesen', E.call('master_save', {'rev': m['rev'], 'articles': [{**base[0], 'vkGruppe': '16 00'}]})[0] == 422)
st, r = E.call('master_save', {'rev': m['rev'], 'articles': base + [{'code': '10823', 'name': 'Steakhüfte', 'category': 'Rind', 'condition': 'frisch', 'vkGruppe': '', 'gtin': ''}]})
arts = {a['code']: a for a in A.call('master')[1]['master']['articles']}
check('VK-Gruppe und GTIN gespeichert, leere Felder entfallen', st == 200 and arts['10601'].get('vkGruppe') == '1600' and arts['10601'].get('gtin') == '4260000106010'
      and 'vkGruppe' not in arts['10823'] and 'gtin' not in arts['10823'], arts)
check('Artikelanzahl je VK-Gruppe', A.call('vkgruppen')[1]['artikel'] == {'1600': 1})
check('Protokoll: Änderung der VK-Gruppe erscheint', 'VK-Gruppe' in json.dumps(A.call('log')[1], ensure_ascii=False))
# für den Oberflächentest leeren (Stammdaten werden beim ersten Öffnen aus dem Angebot angelegt)
rv = A.call('vkgruppen')[1]['rev']
assert A.call('vkgruppen_save', {'rev': rv, 'groups': []})[0] == 200
assert A.call('master_save', {'rev': A.call('master')[1]['master']['rev'], 'articles': []})[0] == 200

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: VK-Gruppen unter Stammdaten direkt nach Artikelstammdaten', a.locator('#vt-vkgruppen').is_visible() and y('#vt-master') < y('#vt-vkgruppen') < y('#vt-kunden') < y('#vt-gruppen'))

    # ---------- VK-Gruppen: Oberfläche ----------
    a.click('#vt-vkgruppen'); a.wait_for_selector('#view-vkgruppen .ed-empty')
    check('leere Liste mit Hinweis zum Import', 'CSV' in a.inner_text('#view-vkgruppen'))
    a.set_input_files('#vg-file', ART_CSV); a.wait_for_selector('#toast.show:has-text("Artikelstammdaten-Export")')
    check('falsche Datei (Artikelexport) wird erkannt', not a.locator('#dlg-vg-import').evaluate('d => d.open'))
    a.set_input_files('#vg-file', VK_CSV); a.wait_for_selector('#dlg-vg-import[open]')
    check('Vorschau: 7 neue VK-Gruppen', a.inner_text('#vgi-neu') == '7' and a.inner_text('#vgi-weg') == '0', a.inner_text('#vg-import-body'))
    a.click('#vgi-ok'); a.wait_for_selector('#view-vkgruppen tr[data-kg="1600"]')
    g = {x['nr']: x for x in doc('vkgruppen')['groups']}
    check('übernommen mit Umlauten und Anführungszeichen (Windows-1252)', len(g) == 7 and g['1050']['name'] == 'Färse, HV, 4xD, Marke: "Testmarke"' and g['4100']['name'] == 'Geflügel DE frisch' and g['10050']['klasse'] == '', g.get('1050'))
    a.fill('#vg-q', 'geflügel'); a.wait_for_function("document.querySelectorAll('#view-vkgruppen tr[data-kg]').length === 1")
    check('Suche in den VK-Gruppen', 'Geflügel DE frisch' in a.inner_text('#vg-list'))
    a.fill('#vg-q', '')
    a.click('#view-vkgruppen tr[data-kg="1000"]'); a.wait_for_selector('#dlg-vgruppe[open]')
    a.fill('#vgruppe-body [name=name]', 'Diverses & Sonstiges'); a.click('#vgruppe-body [type=submit]')
    a.wait_for_function("!document.querySelector('#dlg-vgruppe').open")
    check('VK-Gruppe jederzeit änderbar', next(x for x in doc('vkgruppen')['groups'] if x['nr'] == '1000')['name'] == 'Diverses & Sonstiges')
    a.click('#vg-add'); a.wait_for_selector('#dlg-vgruppe[open]')
    a.fill('#vgruppe-body [name=nr]', '1600'); a.fill('#vgruppe-body [name=name]', 'Doppelt'); a.click('#vgruppe-body [type=submit]')
    a.wait_for_selector('#vg-err:has-text("bereits vergeben")')
    check('doppelte Nummer im Dialog abgewiesen', True)
    a.fill('#vgruppe-body [name=nr]', '8010'); a.fill('#vgruppe-body [name=name]', 'Lammfleisch, Neuseeland, gefroren'); a.click('#vgruppe-body [type=submit]')
    a.wait_for_selector('#view-vkgruppen tr[data-kg="8010"]')
    check('VK-Gruppe anlegen', any(x['nr'] == '8010' for x in doc('vkgruppen')['groups']))
    a.click('#view-vkgruppen tr[data-kg="8010"]'); a.wait_for_selector('#dlg-vgruppe[open]')
    a.click('#vgruppe-body [data-kg-del]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#confirm-body [data-v="1"]')
    a.wait_for_function("!document.querySelector('#view-vkgruppen tr[data-kg=\"8010\"]')")
    check('VK-Gruppe löschen', not any(x['nr'] == '8010' for x in doc('vkgruppen')['groups']))
    a.screenshot(path=SH + '/vkgruppen.png')

    # ---------- Artikelstammdaten importieren ----------
    a.click('#vt-master'); a.wait_for_selector('#ms-list tr[data-mcode]')
    vor = {x['code']: x for x in doc('stammdaten')['articles']}
    n0 = len(vor)
    check('Stammdaten aus dem Angebot angelegt (Ausgangslage)', n0 > 200, n0)
    a.set_input_files('#ms-file', VK_CSV); a.wait_for_selector('#toast.show:has-text("Gruppenliste")')
    check('falsche Datei (VK-Gruppen-Liste) wird erkannt', not a.locator('#dlg-ms-import').evaluate('d => d.open'))
    a.set_input_files('#ms-file', ART_CSV); a.wait_for_selector('#dlg-ms-import[open]')
    t = a.inner_text('#ms-import-body')
    check('Vorschau: 6 neu, 2 ergänzt, übersprungene Zeilen', a.inner_text('#msi-neu') == '6' and a.inner_text('#msi-erg') == '2'
          and '2 Zeilen ohne Bezeichnung' in t and '1× doppelte Nummer' in t and '1× keine gültige Artikelnummer (wek 19%)' in t, t)
    check('Vorschau: VK-Gruppe 7777 nicht in der Liste', '7777 (1)' in t)
    check('Vorschau: Merkmale vorgeschlagen (Lamm, NZ, frisch)', 'Testkeule, Neuseeland · Lamm & Schaf · Frisch · NZ · Lammfleisch, Neuseeland, frisch' in t, t)
    check('Vorschau: HTML in Bezeichnungen wird nicht ausgeführt', a.locator('#ms-import-body b').count() == 0 and 'Testwurst <b>fett</b>' in t)
    a.click('#msi-ok'); a.wait_for_function("!document.querySelector('#dlg-ms-import').open")
    a.wait_for_selector('#toast.show:has-text("Artikelstammdaten übernommen")'); a.wait_for_selector('#ms-list tr[data-mcode="90001"]')
    arts = {x['code']: x for x in doc('stammdaten')['articles']}
    k = arts.get('90001', {})
    check('neuer Artikel: Bezeichnung ohne „frisch“, Merkmale, VK-Gruppe, GTIN', k.get('name') == 'Testkeule, Neuseeland' and k.get('category') == 'Lamm & Schaf' and k.get('condition') == 'frisch'
          and k.get('origin') == 'NZ' and k.get('vkGruppe') == '3050' and k.get('gtin') == '4260000900010', k)
    k = arts.get('90002', {})
    check('Herkunft aus VK-Gruppe/Bezeichnung2, Zustand gefroren', k.get('category') == 'Rind' and k.get('origin') == 'IRL' and k.get('condition') == 'gefroren' and k.get('vkGruppe') == '6150', k)
    k = arts.get('90006', {})
    check('abgekürztes „fri“ der Warenwirtschaft entfernt, Zustand frisch', k.get('name') == 'Testfilet,Parag.' and k.get('condition') == 'frisch' and k.get('origin') == 'PY', k)
    check('ungültige GTIN nicht übernommen, ohne VK-Gruppe', 'gtin' not in arts.get('90003', {}) and 'vkGruppe' not in arts.get('90003', {}), arts.get('90003'))
    check('übersprungene Zeilen nicht angelegt', not any(c in arts for c in ('00004', '4', '180613', 'wek 19%')))
    k = arts.get('10601', {})
    check('bestehender Artikel: gepflegte Bezeichnung bleibt, VK-Gruppe/GTIN ergänzt', k.get('name') == vor['10601']['name'] and k.get('category') == vor['10601']['category'] and k.get('vkGruppe') == '1600' and k.get('gtin') == '4260000106010', k)
    raw = json.dumps(doc('stammdaten'), ensure_ascii=False)
    check('EK, Bestand, Umsatz und Lieferant nicht übernommen', not any(s in raw for s in ('18,68', '18.68', '205.367', '3.051', '1111111', 'ek"', 'Umsatz', 'Lieferant')))
    check('Artikelanzahl: alle bisherigen Artikel bleiben erhalten', len(arts) == n0 + 6, (len(arts), n0))
    check('Protokoll: Stammdaten bearbeitet mit neuen Artikeln', 'Neuer Stammsatz' in json.dumps(A.call('log')[1], ensure_ascii=False))
    a.set_input_files('#ms-file', ART_CSV); a.wait_for_selector('#dlg-ms-import[open]')
    check('erneuter Import: keine Änderungen', a.inner_text('#msi-neu') == '0' and a.inner_text('#msi-erg') == '0' and a.locator('#msi-ok').is_disabled())
    a.click('#ms-import-body [data-close]')

    # ---------- Filter und Bearbeiten ----------
    a.select_option('#ms-vk', '1600'); a.wait_for_function("document.querySelectorAll('#ms-list tr[data-mcode]').length === 3")
    check('Filter nach VK-Gruppe', sorted(a.eval_on_selector_all('#ms-list tr[data-mcode]', 'r => r.map(x => x.dataset.mcode)')) == ['10601', '10823', '90006'])
    check('Gruppenname unter der Nummer', 'Rindfleisch, Argentinien, frisch' in a.inner_text('#ms-list tr[data-mcode="10601"] .m-vk'))
    a.select_option('#ms-vk', '7777')
    check('Filter: VK-Gruppe nicht in der Liste wählbar', a.locator('#ms-list tr[data-mcode="90004"]').count() == 1 and 'nicht in der Liste' in a.inner_text('#ms-list tr[data-mcode="90004"] .m-vk'))
    a.select_option('#ms-vk', '-'); a.wait_for_function("!document.querySelector('#ms-list tr[data-mcode=\"10601\"]')")
    check('Filter: ohne VK-Gruppe', a.locator('#ms-list tr[data-mcode="90003"]').count() == 1)
    a.select_option('#ms-vk', '')
    a.fill('#ms-q', 'geflügel de'); a.wait_for_function("document.querySelectorAll('#ms-list tr[data-mcode]').length === 0 || !document.querySelector('#ms-list tr[data-mcode=\"10601\"]')")
    a.fill('#ms-q', 'testmarke'); a.wait_for_selector('#ms-list tr[data-mcode="90005"]')
    check('Suche findet Artikel über den Namen der VK-Gruppe', a.locator('#ms-list tr[data-mcode]').count() == 1)
    a.fill('#ms-q', '90003'); a.wait_for_selector('#ms-list tr[data-mcode="90003"]')
    inp = '#ms-list tr[data-mcode="90003"] [data-mf="vkGruppe"]'
    a.fill(inp, '5555'); a.press(inp, 'Tab'); a.wait_for_selector('#toast.show:has-text("gibt es nicht")')
    check('unbekannte VK-Gruppe im Feld abgewiesen', a.input_value(inp) == '')
    a.fill(inp, '4100'); a.press(inp, 'Tab'); a.wait_for_selector('#ms-state.saved:has-text("Gespeichert")', timeout=10000)
    a.wait_for_function("document.querySelector('#ms-list tr[data-mcode=\"90003\"] .m-vkname').textContent.includes('Geflügel')")
    check('VK-Gruppe im Artikel zuordnen (gespeichert)', next(x for x in doc('stammdaten')['articles'] if x['code'] == '90003').get('vkGruppe') == '4100')
    a.fill('#ms-q', '')
    a.screenshot(path=SH + '/stammdaten-vkgruppe.png')

    # ---------- Mobil und Leseansicht ----------
    a.set_viewport_size({'width': 390, 'height': 820})
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Artikelstammdaten 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/stammdaten-vkgruppe-mobil.png')
    a.click('#vt-vkgruppen'); a.wait_for_selector('#view-vkgruppen tr[data-kg]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('VK-Gruppen 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/vkgruppen-mobil.png')
    lp = br.new_page(viewport={'width': 1280, 'height': 900})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#vt-vkgruppen:not([hidden])')
    lp.click('#vt-vkgruppen'); lp.wait_for_selector('#view-vkgruppen tr[data-kg]')
    check('Leser: VK-Gruppen nur ansehen', lp.locator('#vg-import').count() == 0 and lp.locator('#vg-add').count() == 0 and 'Artikel' in lp.inner_text('#vg-list thead'))
    lp.click('#vt-master'); lp.wait_for_selector('#ms-list tr[data-mcode]')
    check('Leser: kein Artikelimport', lp.locator('[data-ma="import"]').count() == 0 and lp.locator('#ms-vk').count() == 1)
    lp.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
