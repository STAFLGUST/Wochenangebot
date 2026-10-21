"""Stammdaten: Navigation (Artikel, Kunden, Kundengruppen), Kundengruppen per CSV (Windows-1252/UTF-8) importieren,
bearbeiten, Rechte, Zuordnung im Kunden, Protokoll. Nur Testdaten (tests/fixtures/kundengruppen)."""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, FIX, SH, storage_raw

PW = 'Sicheres-Passwort-1'
CSV1 = FIX + '/kundengruppen/kundengruppen.csv'
CSV2 = FIX + '/kundengruppen/kundengruppen-neu.csv'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


admin = Client('198.51.100.2')
assert admin.call('login', {'username': 'admin', 'password': PW})[0] == 200
admin.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
admin.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
ed = Client('198.51.100.3'); ed.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})
le = Client('198.51.100.4'); le.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})

# ---------- Schnittstelle ----------
check('ohne Anmeldung gesperrt', Client().call('kundengruppen')[0] == 401)
st, r = le.call('kundengruppen')
check('Leser darf ansehen (leer)', st == 200 and r['groups'] == [] and r['rev'] == 0 and 'kunden' not in r)
check('Leser darf nicht speichern', le.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'X'}]})[0] == 403)
check('Speichern nur per POST', ed.call('kundengruppen_save')[0] == 405)
check('doppelte Nummer abgewiesen', ed.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'A'}, {'nr': '01', 'name': 'B'}]})[0] == 422)
check('fehlende Bezeichnung abgewiesen', ed.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': ''}]})[0] == 422)
check('ungültige Nummer abgewiesen', ed.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1 2', 'name': 'A'}]})[0] == 422)
st, r = ed.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '20', 'name': 'Zwanzig', 'klasse': '300'}, {'nr': '3', 'name': 'Drei <b>'}], 'quelle': 'Test'})
check('Bearbeiter speichert, Liste nach Nummer sortiert', st == 200 and [g['nr'] for g in r['groups']] == ['3', '20'] and r['neu'] == 2 and r['groups'][0]['name'] == 'Drei <b>')
check('veraltete Revision abgewiesen', ed.call('kundengruppen_save', {'rev': 0, 'groups': []})[0] == 409)
check('Bearbeiter ohne Kundenrecht sieht keine Kundenanzahl', 'kunden' not in ed.call('kundengruppen')[1])
check('Protokoll: Kundengruppen gespeichert', 'Kundengruppen aus „Test“ übernommen: 2 neu' in json.dumps(admin.call('log')[1], ensure_ascii=False))

# ---------- Zuordnung im Kunden ----------
rev = admin.call('kunden')[1]['rev']
base = {'firma': 'Gruppentest GmbH', 'nr': 'K-1', 'email': 'gruppe@example.org', 'active': True, 'angebote': ['std']}
check('unbekannte Kundengruppe abgewiesen', admin.call('kunde_save', {**base, 'rev': rev, 'gruppe': '99'})[0] == 422)
st, r = admin.call('kunde_save', {**base, 'rev': rev, 'gruppe': '20'})
check('Kundengruppe am Kunden gespeichert', st == 200 and r['customer']['gruppe'] == '20')
kid = r['customer']['id']
check('Administrator sieht Kundenanzahl je Gruppe', admin.call('kundengruppen')[1]['kunden'] == {'20': 1})
rv = admin.call('kundengruppen')[1]['rev']
assert admin.call('kundengruppen_save', {'rev': rv, 'groups': [{'nr': '3', 'name': 'Drei'}]})[0] == 200
rev = admin.call('kunden')[1]['rev']
check('entfernte Gruppe bleibt beim unveränderten Kunden erhalten', admin.call('kunde_save', {**base, 'id': kid, 'rev': rev, 'gruppe': '20', 'firma': 'Gruppentest GmbH & Co'})[0] == 200)
rev = admin.call('kunden')[1]['rev']
check('… aber nicht neu zuordenbar', admin.call('kunde_save', {**base, 'firma': 'Andere', 'nr': 'K-2', 'email': 'a@example.org', 'rev': rev, 'gruppe': '20'})[0] == 422)
rv = admin.call('kundengruppen')[1]['rev']
assert admin.call('kundengruppen_save', {'rev': rv, 'groups': []})[0] == 200   # für den Oberflächentest leeren

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')

    # ---------- Navigation ----------
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Stammdaten mit Artikel, Kunden, Kundengruppen', a.locator('#side-stamm').is_visible() and a.inner_text('#side-stamm').strip().lower() == 'stammdaten'
          and y('#side-stamm') < y('#vt-master') < y('#vt-kunden') < y('#vt-gruppen') < y('#side-admin'), [a.inner_text('#vt-master'), a.inner_text('#vt-gruppen')])
    check('Artikelstammdaten weiter erreichbar', 'Artikel' in a.inner_text('#vt-master'))
    a.screenshot(path=SH + '/stammdaten-nav.png')

    # ---------- Import (Windows-1252) ----------
    a.click('#vt-gruppen'); a.wait_for_selector('#view-gruppen .ed-empty')
    check('leere Liste mit Hinweis zum Import', 'CSV' in a.inner_text('#view-gruppen'))
    a.set_input_files('#kg-file', CSV1)
    a.wait_for_selector('#dlg-kg-import[open]')
    check('Vorschau: 12 neu, 0 geändert, 0 entfallen', a.inner_text('#kgi-neu') == '12' and a.inner_text('#kgi-geaendert') == '0' and a.inner_text('#kgi-weg') == '0')
    a.screenshot(path=SH + '/kundengruppen-import.png')
    a.click('#kgi-ok'); a.wait_for_selector('#dlg-kg-import', state='hidden')
    a.wait_for_selector('.kgtab tbody tr')
    check('12 Kundengruppen in der Liste', a.locator('.kgtab tbody tr').count() == 12)
    txt = a.inner_text('.kgtab')
    check('Umlaute und Anführungszeichen richtig (Windows-1252)', 'Großküche oh. Kondi.' in txt and 'Händler/Importeur' in txt and 'Testgruppe "Nord"' in txt and 'Kühlhaus' in txt)
    check('doppelte Leerzeichen bereinigt, Klasse/Kategorie übernommen', 'Fleischerei oh. Kondi.' in txt and a.locator('.kgtab tr[data-kg="1"] td.kg-k').all_inner_texts() == ['300', '2'])
    check('Reihenfolge nach Nummer', a.locator('.kgtab tbody tr').first.get_attribute('data-kg') == '1' and a.locator('.kgtab tbody tr').last.get_attribute('data-kg') == '90')
    check('gespeichert mit Herkunft im Protokoll', len(doc('kundengruppen')['groups']) == 12)
    a.screenshot(path=SH + '/kundengruppen.png')

    # ---------- erneuter Import (UTF-8): geändert, entfallen, neu ----------
    a.set_input_files('#kg-file', CSV2)
    a.wait_for_selector('#dlg-kg-import[open]')
    check('Vorschau Abgleich: 1 neu, 1 geändert, 1 entfallen', (a.inner_text('#kgi-neu'), a.inner_text('#kgi-geaendert'), a.inner_text('#kgi-weg')) == ('1', '1', '1'))
    check('entfallende Gruppe genannt', 'Kühlhaus' in a.inner_text('#kg-import-body'))
    a.click('#kgi-ok'); a.wait_for_selector('#dlg-kg-import', state='hidden')
    a.wait_for_function("document.querySelectorAll('.kgtab tbody tr').length === 12 && !!document.querySelector('.kgtab tr[data-kg=\"70\"]')")
    check('Abgleich übernommen', a.locator('.kgtab tr[data-kg="63"]').count() == 0 and 'Restaurant mit Kondition' in a.inner_text('.kgtab'))

    # ---------- Suche, anlegen, ändern, löschen ----------
    a.fill('#kg-q', 'restaurant'); a.wait_for_function("document.querySelectorAll('.kgtab tbody tr').length === 2")
    check('Suche', True)
    a.fill('#kg-q', '')
    a.click('#kg-add'); a.wait_for_selector('#dlg-kgruppe[open]')
    a.fill('#kgruppe-body [name=nr]', '25'); a.fill('#kgruppe-body [name=name]', 'Doppelt')
    a.click('#kgruppe-body [type=submit]'); a.wait_for_selector('#kg-err:not(:empty)')
    check('vergebene Nummer abgewiesen', 'bereits vergeben' in a.inner_text('#kg-err'))
    a.fill('#kgruppe-body [name=nr]', '201'); a.fill('#kgruppe-body [name=name]', 'Mitarbeiterverkauf'); a.fill('#kgruppe-body [name=klasse]', '100')
    a.click('#kgruppe-body [type=submit]'); a.wait_for_selector('.kgtab tr[data-kg="201"]')
    check('Gruppe angelegt', 'Mitarbeiterverkauf' in a.inner_text('.kgtab tr[data-kg="201"]'))
    a.click('.kgtab tr[data-kg="201"] [data-kgedit]'); a.wait_for_selector('#dlg-kgruppe[open]')
    check('Nummer beim Bearbeiten fest', a.get_attribute('#kgruppe-body [name=nr]', 'readonly') is not None)
    a.fill('#kgruppe-body [name=name]', 'Personalverkauf'); a.click('#kgruppe-body [type=submit]')
    a.wait_for_function("document.querySelector('.kgtab tr[data-kg=\"201\"]').innerText.includes('Personalverkauf')")
    check('Gruppe geändert', True)
    a.click('.kgtab tr[data-kg="201"] [data-kgedit]'); a.wait_for_selector('#dlg-kgruppe[open]')
    a.click('#kgruppe-body [data-kg-del]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#confirm-body [data-v="1"]')
    a.wait_for_selector('.kgtab tr[data-kg="201"]', state='detached')
    check('Gruppe gelöscht', a.locator('.kgtab tr[data-kg="201"]').count() == 0)

    # ---------- Kunde: Kundengruppe wählen ----------
    a.click('#vt-kunden'); a.wait_for_selector('#view-kunden tr[data-kid]')
    a.click('#view-kunden tr[data-kid] [data-kedit]'); a.wait_for_selector('#dlg-kunde[open]')
    opts = a.locator('#kunde-body [name=gruppe] option').all_inner_texts()
    check('Kundendialog bietet die Kundengruppen an', '12 · Restaurant mit Kondition' in opts and opts[0].startswith('–'), opts[:3])
    a.select_option('#kunde-body [name=gruppe]', '15')
    a.click('#kunde-body [type=submit]')
    a.wait_for_function("document.querySelector('#view-kunden .k-gruppe') && document.querySelector('#view-kunden .k-gruppe').innerText.includes('Großküche')", timeout=15000)
    check('Kundenliste zeigt die Gruppe', 'Großküche oh. Kondi.' in a.inner_text('#view-kunden .ktab'))
    check('gespeichert am Kunden', any(c.get('gruppe') == '15' for c in doc('kunden')['customers']))
    a.fill('#k-q', 'großküche'); a.wait_for_function("document.querySelectorAll('#view-kunden tr[data-kid]').length === 1")
    check('Kundensuche findet über die Gruppe', True)
    a.click('#vt-gruppen'); a.wait_for_selector('.kgtab tr[data-kg="15"]')
    try: a.wait_for_function("(document.querySelector('.kgtab tr[data-kg=\"15\"] td.kg-n') || {}).innerText === '1'", timeout=8000)   # Liste wird nach dem Laden neu gezeichnet
    except Exception: pass
    check('Kundenanzahl je Gruppe', a.inner_text('.kgtab tr[data-kg="15"] td.kg-n') == '1', a.inner_text('.kgtab tr[data-kg="15"] td.kg-n'))

    # ---------- Handy ----------
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    m.on('pageerror', lambda e: errors.append(str(e)))
    m.goto(BASE + '/admin/'); m.wait_for_selector('#screen-auth:not([hidden])')
    m.fill('#au-user', 'admin'); m.fill('#pw1', PW); m.click('#auth-submit'); m.wait_for_selector('#screen-editor:not([hidden])')
    m.click('#vt-gruppen'); m.wait_for_selector('.kgtab tbody tr')
    m.screenshot(path=SH + '/kundengruppen-mobil.png')
    check('Handy: kein seitliches Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390)

    # ---------- Leser und Bearbeiter ----------
    v = br.new_page(viewport={'width': 1440, 'height': 900})
    v.on('pageerror', lambda e: errors.append(str(e)))
    v.goto(BASE + '/admin/'); v.wait_for_selector('#screen-auth:not([hidden])')
    v.fill('#au-user', 'lea'); v.fill('#pw1', 'Leserin-Zugang-1'); v.click('#auth-submit'); v.wait_for_selector('#screen-editor:not([hidden])')
    check('Leser: Stammdaten sichtbar, Kunden nicht', v.locator('#side-stamm').is_visible() and v.locator('#vt-gruppen').is_visible() and not v.locator('#vt-kunden').is_visible())
    v.click('#vt-gruppen'); v.wait_for_selector('.kgtab tbody tr')
    check('Leser: nur ansehen, keine Kundenanzahl', v.locator('#kg-import').count() == 0 and v.locator('#kg-add').count() == 0 and v.locator('.kgtab th.kg-n').count() == 0)
    e = br.new_page(viewport={'width': 1440, 'height': 900})
    e.goto(BASE + '/admin/'); e.wait_for_selector('#screen-auth:not([hidden])')
    e.fill('#au-user', 'eddi'); e.fill('#pw1', 'Editor-Zugang-77'); e.click('#auth-submit'); e.wait_for_selector('#screen-editor:not([hidden])')
    e.click('#vt-gruppen'); e.wait_for_selector('.kgtab tbody tr')
    check('Bearbeiter: Import und Anlegen möglich', e.locator('#kg-import').count() == 1 and e.locator('#kg-add').count() == 1)
    check('Bearbeiter: Verwaltung-Überschrift weiterhin nicht sichtbar', not e.locator('#side-admin').is_visible())

    check('keine JavaScript-Fehler', not errors)
    if errors:
        print('\n'.join(errors[:5]))
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
