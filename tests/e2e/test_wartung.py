"""Wartungsmodus und erweiterte Übersicht im Eingabebereich."""
import re
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
P = Client('198.51.100.4')

code, st = A.call('security_status')
check('dashboard: maintenance off, storage + disk + mail + orders + customers', code == 200 and st['wartung'] is None and st['storage']['documents'] >= 1
      and st['disk']['free'] and 'sent7' in st['mail'] and 'n7' in st['orders'] and 'active' in st['customers'] and st['php'], {k: st.get(k) for k in ['storage', 'disk']})
check('public offer reachable before', P.call('offer')[0] == 200)
check('no test mailbox outside the test environment', A.call('testpostfach')[0] == 404 and A.call('status')[1].get('testumgebung') is False)
check('editor cannot switch maintenance', E.call('wartung_save', {'active': True})[0] == 403)
check('anonymous cannot switch maintenance', P.call('wartung_save', {'active': True})[0] == 401)
check('invalid end time rejected', A.call('wartung_save', {'active': True, 'until': 'morgen'})[0] == 422)
code, r = A.call('wartung_save', {'active': True, 'message': 'Kurze Pause <b>heute</b>', 'until': '2026-10-18T15:00'})
check('admin switches maintenance on', code == 200 and r['wartung']['active'] is True and r['wartung']['until'] == '2026-10-18T15:00', r)
code, r = P.call('offer')
check('public offer: 503 with maintenance note', code == 503 and r.get('wartung') is True and r.get('error') == 'Kurze Pause <b>heute</b>', (code, r))
check('customer login paused', P.call('kunde_login', {'username': 'x', 'password': 'y'})[0] == 503)
check('customer status reports maintenance', P.call('kunde_status')[1]['wartung']['active'] is True)
check('unsubscribe links keep working', P.call('kunde_abmelden_info', {'token': 'k000000000000.' + 'x' * 32})[0] == 404)
check('staff still sees the offer', A.call('offer')[0] == 200 and E.call('offer')[0] == 200)
check('staff status shows maintenance', E.call('status')[1]['wartung']['active'] is True)
check('dashboard shows maintenance', A.call('security_status')[1]['wartung']['active'] is True)
code, r = A.call('wartung_save', {'active': True, 'message': '', 'until': ''})
check('empty note falls back to default text', r['wartung']['message'].startswith('Wir aktualisieren') and P.call('offer')[1]['error'].startswith('Wir aktualisieren'))
code, r = A.call('wartung_save', {'active': False})
check('maintenance off: offer reachable again', code == 200 and r['wartung'] is None and P.call('offer')[0] == 200)
code, r = A.call('log')
check('audit: maintenance on/off logged', sum(1 for e in r['entries'] if e['a'] == 'wartung' and 'Wartungsmodus' in e['s']) >= 2)

with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('admin: no maintenance banner while off', a.locator('#adm-wartung').is_hidden())
    a.click('#vt-sec'); a.wait_for_selector('#wartung-form')
    t = a.inner_text('#view-sec .sec-grid')
    check('dashboard cards: maintenance, storage, disk, mail, orders, customers', all(x in t for x in ['Wartungsmodus', 'Datenablage', 'Speicherplatz', 'E-Mail-Versand', 'Bestellwünsche', 'Kunden']), t[:300])
    a.fill('#wartung-form [name=message]', 'Wir spielen gerade ein Update ein.')
    a.click('#wartung-form [data-wartung=on]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_selector('#adm-wartung:not([hidden])', timeout=8000)
    check('admin banner appears', 'Wartungsmodus aktiv' in a.inner_text('#adm-wartung'))
    a.wait_for_selector('#wartung-form.on'); a.screenshot(path=SH + '/wartung-dashboard.png')
    a.wait_for_selector('#wartung-form [data-wartung=off]')
    # Besucher
    v = br.new_page(viewport={'width': 1280, 'height': 900}); v.goto(B + '/'); v.wait_for_selector('.k-wartung')
    v.screenshot(path=SH + '/wartung-seite.png')
    check('visitor sees maintenance page, no articles', 'Wir spielen gerade ein Update ein.' in v.inner_text('#list') and v.locator('tr.row').count() == 0)
    # Darstellung der Wartungsseite: kein Ansichtsumschalter (ohne Funktion), keine leere doppelte Trennlinie im Fuß
    check('maintenance page: no view switch, no empty footer line', v.is_hidden('#modebar') and v.is_hidden('#foot') and v.is_visible('.legal-links'))
    vm = br.new_page(viewport={'width': 390, 'height': 844}); vm.goto(B + '/'); vm.wait_for_selector('.k-wartung')
    lage = vm.evaluate("[getComputedStyle(document.querySelector('#topbar .search')).display, document.querySelector('#topbar').getBoundingClientRect().height, document.documentElement.scrollWidth <= innerWidth]")
    check('maintenance page 390 px: no empty gap for the hidden search in the header', lage[0] == 'none' and lage[1] < 80 and lage[2], lage)
    vm.screenshot(path=SH + '/wartung-seite-390.png'); vm.close()
    # Mitarbeiter im selben Browser sieht die Seite
    a2 = actx.new_page(); a2.goto(B + '/'); a2.wait_for_selector('tr.row')
    check('staff sees offer + maintenance banner', a2.is_visible('#wartung-banner') and 'Wartungsmodus aktiv' in a2.inner_text('#wartung-banner'))
    a.click('#wartung-form [data-wartung=off]'); a.wait_for_selector('#wartung-form [data-wartung=on]', timeout=8000)
    check('admin banner gone after switching off', a.locator('#adm-wartung').is_hidden())
    v.reload(); v.wait_for_selector('tr.row')
    check('visitor sees offer again', v.locator('tr.row').count() > 10)
    check('no JS errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
