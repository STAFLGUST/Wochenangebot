"""Stammdaten → Abteilungen (Auftrag des Inhabers 10.11.2026): Abteilungen als eigene Stammdaten der Verwaltung (Nummer,
Bezeichnung) – Rechte (Leser nur ansehen, Bearbeiter der Stammdaten ändern, ohne Anmeldung gesperrt), Prüfungen (Bezeichnung
Pflicht und eindeutig ohne Groß-/Kleinschreibung, Nummer doppelt, Revision), Protokoll; Übernahme der bisher bei den
Mitarbeitern eingetragenen Abteilungen (Vorschau, Reihenfolge wie im Urlaubsplan, nichts entfernt); in den HR-Angaben der
Mitarbeiter Auswahl aus den Stammdaten (Nummer, Name als Kopie), Umbenennen wirkt überall – auch bei Angaben, die noch nur
den Namen tragen (frühere Bezeichnungen) –, gelöschte Abteilung bleibt als Name stehen, ältere Oberfläche mit Text, ohne
Stammdaten freier Text wie bisher; Import „Abwesenheiten aus der Zeiterfassung“ ordnet Abteilungen den Stammdaten zu
(unbekannte nur als Hinweis); Oberfläche (Liste mit Mitarbeiteranzahl, Anlegen mit Nummernvorschlag, Fehler im Dialog,
Auswahl im Mitarbeiter-Dialog, Leseansicht, 390 px, keine JavaScript-Fehler). Nur Testdaten."""
import datetime as dt
import json
import os
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
for u, n, r, p, extra in (('eddi', 'Eddi Editor', 'editor', 'Editor-Zugang-77', {}), ('lea', 'Lea Leser', 'viewer', 'Leserin-Zugang-1', {}),
                          ('paul', 'Paul Personal', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.verwalten']})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
for vor, nach in (('Max', 'Muster'), ('Vera', 'Versand'), ('Wilma', 'Weiss')):
    st, r_ = A.call('user_save', {'id': '', 'vorname': vor, 'nachname': nach, 'role': 'viewer', 'active': True, 'zugang': False})
    assert st == 200, r_
ids = {u['name']: u['id'] for u in A.call('users')[1]['users']}
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200
P = Client('198.51.100.5'); assert P.call('login', {'username': 'paul', 'password': 'Personal-Zugang-77'})[0] == 200


def personen():
    return {p_['name']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}


def hr(name, **werte):
    st, r = P.call('mitarbeiter_hr_save', {'nutzer': ids[name], 'rev': P.call('mitarbeiter_hr')[1]['rev'], **werte})
    return st, r


def roh(name):
    return next((x for x in doc('hr-personal').get('personen', []) if x.get('nutzer') == ids[name]), {})


# ---------- vor den Stammdaten: freier Text wie bisher ----------
st, r = P.call('mitarbeiter_hr')
check('ohne Stammdaten: Liste der Abteilungen leer', st == 200 and r['abteilungen'] == [], r.get('abteilungen'))
for name, abt, pos in (('Eddi Editor', 'Verwaltung', 1), ('Max Muster', 'Lager', 2), ('Vera Versand', 'Versand', 3), ('Wilma Weiss', 'lager', 4)):
    st, r = hr(name, abteilung=abt, pos=pos)
    assert st == 200, r
check('ohne Stammdaten: Abteilung als freier Text gespeichert (ohne Nummer)', roh('Max Muster').get('abteilung') == 'Lager' and roh('Max Muster').get('abteilungNr') is None, roh('Max Muster'))
st, r = hr('Max Muster', abteilungNr='10')
check('ohne Stammdaten: Nummer abgewiesen (422 mit Hinweis auf Stammdaten → Abteilungen)', st == 422 and 'Stammdaten' in r.get('error', ''), (st, r))

# ---------- Schnittstelle der Liste ----------
check('Abteilungen: ohne Anmeldung gesperrt', Client().call('abteilungen')[0] == 401)
st, r = L.call('abteilungen')
check('Abteilungen: Leser darf ansehen (leer)', st == 200 and r['groups'] == [] and r['rev'] == 0, r)
check('Abteilungen: Leser darf nicht speichern', L.call('abteilungen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'X'}]})[0] == 403)
check('Abteilungen: Personalstelle ohne Stammdatenrecht darf nicht speichern', P.call('abteilungen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'X'}]})[0] == 403)
st, r = E.call('abteilungen_save', {'rev': 0, 'groups': [{'nr': '10', 'name': ''}]})
check('Abteilungen: Bezeichnung fehlt → 422', st == 422 and 'Bezeichnung fehlt' in r.get('error', ''), r)
st, r = E.call('abteilungen_save', {'rev': 0, 'groups': [{'nr': '10', 'name': 'Lager'}, {'nr': '20', 'name': ' lager '}]})
check('Abteilungen: Bezeichnung doppelt (ohne Groß-/Kleinschreibung) → 422', st == 422 and 'doppelt' in r.get('error', ''), r)
check('Abteilungen: Nummer doppelt → 422', E.call('abteilungen_save', {'rev': 0, 'groups': [{'nr': '10', 'name': 'A'}, {'nr': '010', 'name': 'B'}]})[0] == 422)

# ---------- Oberfläche: leere Liste, Übernahme aus den Mitarbeiterangaben ----------
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    ctx, pg = anmelden('admin', PW, '198.51.100.2')
    y = lambda sel: pg.locator(sel).bounding_box()['y']
    check('Navigation: Abteilungen unter Stammdaten nach den Versandarten', pg.locator('#vt-abteilungen').is_visible() and y('#vt-versandarten') < y('#vt-abteilungen') < y('#side-admin'))
    pg.click('#vt-abteilungen'); pg.wait_for_selector('#view-abteilungen .ed-empty')
    t = pg.inner_text('#view-abteilungen')
    check('leer: Hinweis zum Anlegen und Übernehmen, kein CSV-Import', 'Noch keine Abteilungen' in t and 'übernehmen' in t and pg.locator('#ab-import').count() == 0
          and pg.locator('#ab-uebern').is_visible() and pg.locator('#ab-add').is_visible(), t)
    pg.click('#ab-uebern'); pg.wait_for_selector('#dlg-ab-import[open]')
    t = pg.inner_text('#dlg-ab-import')
    check('Übernahme: Vorschau mit den bisherigen Abteilungen (Groß-/Kleinschreibung zusammengefasst)', pg.text_content('#abi-neu').strip() == '3' and pg.text_content('#abi-weg').strip() == '0'
          and 'Abteilungen aus den Mitarbeiterangaben' in t, t)
    check('Übernahme: Reihenfolge wie im Urlaubsplan, Nummern in Zehnerschritten', [x.strip() for x in pg.locator('#dlg-ab-import .kg-prev li').all_inner_texts()] == ['10 Verwaltung', '20 Lager', '30 Versand'],
          pg.locator('#dlg-ab-import .kg-prev li').all_inner_texts())
    pg.screenshot(path=os.path.join(SH, 'abteilungen_uebernehmen_1280.png'))
    check('Übernahme: erst mit „Übernehmen“ gespeichert', L.call('abteilungen')[1]['groups'] == [])
    pg.click('#abi-ok'); pg.wait_for_selector('#view-abteilungen tr[data-kg="30"]')
    st, r = L.call('abteilungen')
    check('Übernahme: gespeichert', [(g['nr'], g['name']) for g in r['groups']] == [('10', 'Verwaltung'), ('20', 'Lager'), ('30', 'Versand')], r['groups'])
    check('Protokoll: Abteilungen aus „Mitarbeiterangaben“ übernommen', 'Abteilungen aus „Mitarbeiterangaben“ übernommen: 3 neu' in json.dumps(A.call('log')[1], ensure_ascii=False))
    pg.wait_for_function("(document.querySelector('#view-abteilungen tr[data-kg=\"20\"] .kg-n') || {}).textContent === '2'")
    check('Liste: Anzahl Mitarbeiter je Abteilung (Lager: Max und Wilma, über den Namen)', pg.inner_text('#view-abteilungen tr[data-kg="10"] .kg-n').strip() == '1'
          and 'Mitarbeiter' in pg.inner_text('#view-abteilungen thead'), pg.inner_text('#view-abteilungen tbody'))
    pg.click('#ab-uebern'); pg.wait_for_selector('#dlg-ab-import[open]')
    check('Übernahme erneut: keine Änderungen', pg.locator('#abi-ok').is_disabled() and 'Keine Änderungen' in pg.inner_text('#dlg-ab-import'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-ab-import[open]', state='detached')
    # anlegen mit Nummernvorschlag, doppelte Bezeichnung im Dialog
    pg.click('#ab-add'); pg.wait_for_selector('#dlg-abruppe[open]')
    check('Anlegen: nächste Nummer vorgeschlagen, Fokus auf der Bezeichnung', pg.input_value('#abruppe-body [name="nr"]') == '40'
          and pg.evaluate("document.activeElement.name") == 'name' and 'Reihenfolge' in pg.inner_text('#abruppe-body .dlg-head'))
    pg.fill('#abruppe-body [name="name"]', 'versand'); pg.click('#abruppe-body [type="submit"]')
    pg.wait_for_function("document.querySelector('#ab-err').textContent.includes('doppelt')")
    check('Anlegen: doppelte Bezeichnung → Fehler im Dialog', 'Versand' in pg.text_content('#ab-err') or 'versand' in pg.text_content('#ab-err'), pg.text_content('#ab-err'))
    pg.fill('#abruppe-body [name="name"]', 'Produktion'); pg.click('#abruppe-body [type="submit"]')
    pg.wait_for_selector('#view-abteilungen tr[data-kg="40"]')
    check('Anlegen: gespeichert', ('40', 'Produktion') in [(g['nr'], g['name']) for g in L.call('abteilungen')[1]['groups']])
    pg.screenshot(path=os.path.join(SH, 'abteilungen_1280.png'), full_page=True)

    # ---------- HR: Auflösen über Nummer, Name und frühere Namen ----------
    pp = personen()
    check('HR: Liste der Abteilungen für die Auswahl (Nummer und Name)', P.call('mitarbeiter_hr')[1]['abteilungen'][:2] == [{'nr': '10', 'name': 'Verwaltung'}, {'nr': '20', 'name': 'Lager'}])
    check('HR: Angaben ohne Nummer finden ihre Abteilung über den Namen (auch andere Schreibweise)', pp['Max Muster']['abteilungNr'] == '20' and pp['Wilma Weiss']['abteilungNr'] == '20'
          and pp['Wilma Weiss']['abteilung'] == 'Lager', (pp['Max Muster'], pp['Wilma Weiss']))
    rv = L.call('abteilungen')[1]['rev']
    gr = [{'nr': '10', 'name': 'Verwaltung'}, {'nr': '20', 'name': 'Logistik'}, {'nr': '30', 'name': 'Versand'}, {'nr': '40', 'name': 'Produktion'}]
    st, r = E.call('abteilungen_save', {'rev': rv, 'groups': gr})
    check('Umbenennen: frühere Bezeichnung gemerkt (nur vom Server)', st == 200 and r['groups'][1].get('frueher') == ['Lager'] and 'frueher' not in r['groups'][0], r)
    pp = personen()
    check('Umbenennen wirkt bei Angaben ohne Nummer (über den früheren Namen)', pp['Max Muster']['abteilung'] == 'Logistik' and pp['Wilma Weiss']['abteilung'] == 'Logistik', pp['Max Muster'])
    st, r = hr('Max Muster', abteilungNr='20')
    check('HR: Nummer gespeichert, Name als Kopie (Rückfall auf die Vorversion)', st == 200 and roh('Max Muster').get('abteilungNr') == '20' and roh('Max Muster').get('abteilung') == 'Logistik', roh('Max Muster'))
    check('HR: unbekannte Nummer → 422', hr('Max Muster', abteilungNr='99')[0] == 422 and hr('Max Muster', abteilungNr=['20'])[0] == 422)
    st, r = hr('Vera Versand', abteilungNr='')
    check('HR: leere Nummer = keine Abteilung', st == 200 and r['person']['abteilung'] == '' and r['person']['abteilungNr'] is None, r.get('person'))
    st, r = hr('Vera Versand', abteilung='versand')
    check('ältere Oberfläche (Text): bekannter Name wird zur Nummer', st == 200 and roh('Vera Versand').get('abteilungNr') == '30' and r['person']['abteilung'] == 'Versand', roh('Vera Versand'))
    gr[1]['name'] = 'Lager & Logistik'
    st, r = E.call('abteilungen_save', {'rev': L.call('abteilungen')[1]['rev'], 'groups': gr})
    check('erneut umbenannt: beide früheren Namen gemerkt', st == 200 and r['groups'][1].get('frueher') == ['Lager', 'Logistik'], r['groups'][1])
    pp = personen()
    check('Umbenennen wirkt überall: Nummer (Max) und früherer Name (Wilma)', pp['Max Muster']['abteilung'] == 'Lager & Logistik' and pp['Wilma Weiss']['abteilung'] == 'Lager & Logistik')
    Y = dt.date.today().year
    st, m = P.call(f'hr_monat&jahr={Y}&monat=1')
    km = {x['name']: x['abteilung'] for x in m.get('personen', [])}
    check('Kalender: Name aus den Stammdaten', st == 200 and km.get('Max Muster') == 'Lager & Logistik' and km.get('Vera Versand') == 'Versand', km)
    st, r = E.call('abteilungen_save', {'rev': L.call('abteilungen')[1]['rev'], 'groups': gr + [{'nr': '50', 'name': 'lager'}]})
    check('neue Abteilung mit früherem Namen einer anderen: gilt nur noch für sie', st == 200 and r['groups'][1].get('frueher') == ['Logistik'], r['groups'])
    check('… Angaben mit diesem Namen gehören jetzt zur neuen Abteilung', personen()['Wilma Weiss']['abteilungNr'] == '50')
    st, r = hr('Eddi Editor', abteilung='Fantasie')
    check('ältere Oberfläche: unbekannter Text bleibt Text (ohne Nummer)', st == 200 and roh('Eddi Editor').get('abteilung') == 'Fantasie' and roh('Eddi Editor').get('abteilungNr') is None)
    hr('Eddi Editor', abteilungNr='10')
    st, r = E.call('abteilungen_save', {'rev': L.call('abteilungen')[1]['rev'], 'groups': [g for g in gr if g['nr'] != '10'] + [{'nr': '50', 'name': 'lager'}]})
    pe = personen()['Eddi Editor']
    check('gelöschte Abteilung: Name bleibt beim Mitarbeiter stehen', st == 200 and pe['abteilung'] == 'Verwaltung' and pe['abteilungNr'] == '10', pe)

    # ---------- Oberfläche: Auswahl im Mitarbeiter-Dialog ----------
    pg.click('#vt-users'); pg.wait_for_selector(f'#view-users tr[data-uid="{ids["Max Muster"]}"]')
    check('Mitarbeiterliste: Abteilung aus den Stammdaten', 'Lager & Logistik' in pg.inner_text(f'#view-users tr[data-uid="{ids["Max Muster"]}"]'))
    pg.click(f'#view-users tr[data-uid="{ids["Max Muster"]}"]'); pg.wait_for_selector('#dlg-user[open] #hr-teil select[name="hr_abteilungNr"]')
    opts = pg.locator('#user-body [name="hr_abteilungNr"] option').all_inner_texts()
    check('Dialog: Auswahl statt freiem Text, gewählt die eigene Abteilung', pg.locator('#user-body [name="hr_abteilung"]').count() == 0
          and pg.input_value('#user-body [name="hr_abteilungNr"]') == '20' and opts[0].startswith('– keine') and 'Produktion' in opts, opts)
    pg.select_option('#user-body [name="hr_abteilungNr"]', '40')
    pg.screenshot(path=os.path.join(SH, 'abteilungen_mitarbeiter_1280.png'))
    pg.click('#user-body [type="submit"]'); pg.wait_for_selector('#dlg-user[open]', state='hidden')
    check('Dialog: gewählte Abteilung gespeichert', roh('Max Muster').get('abteilungNr') == '40' and roh('Max Muster').get('abteilung') == 'Produktion', roh('Max Muster'))
    pg.wait_for_function(f"document.querySelector('#view-users tr[data-uid=\"{ids['Eddi Editor']}\"]')")
    pg.click(f'#view-users tr[data-uid="{ids["Eddi Editor"]}"]'); pg.wait_for_selector('#dlg-user[open] #hr-teil select[name="hr_abteilungNr"]')
    check('Dialog: Abteilung ohne Eintrag in den Stammdaten bleibt gewählt und gekennzeichnet', pg.input_value('#user-body [name="hr_abteilungNr"]') == '='
          and 'Verwaltung (nicht in den Stammdaten)' in pg.locator('#user-body [name="hr_abteilungNr"] option').all_inner_texts())
    pg.click('#user-body [type="submit"]'); pg.wait_for_selector('#dlg-user[open]', state='hidden')
    check('… Speichern lässt sie unverändert', roh('Eddi Editor').get('abteilungNr') == '10' and roh('Eddi Editor').get('abteilung') == 'Verwaltung', roh('Eddi Editor'))
    # Bearbeiten in der Liste: frühere Bezeichnungen im Dialog
    pg.click('#vt-abteilungen'); pg.wait_for_selector('#view-abteilungen tr[data-kg="20"]')
    pg.click('#view-abteilungen tr[data-kg="20"]'); pg.wait_for_selector('#dlg-abruppe[open]')
    check('Bearbeiten: Anzahl Mitarbeiter und früherer Name', '„Logistik“' in pg.inner_text('#abruppe-body .dlg-head'), pg.inner_text('#abruppe-body .dlg-head'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-abruppe[open]', state='detached')
    ctx.close()

    # Leseansicht und Handy
    ctx, pg = anmelden('lea', 'Leserin-Zugang-1', '198.51.100.4', 390)
    pg.goto(B + '/admin/#abteilungen'); pg.wait_for_selector('#view-abteilungen tr[data-kg="20"]')
    check('Leser: Liste ohne Anlegen und Übernehmen', pg.locator('#ab-add').count() == 0 and pg.locator('#ab-uebern').count() == 0)
    check('390 px: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    pg.screenshot(path=os.path.join(SH, 'abteilungen_390.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden('admin', PW, '198.51.100.2', 390)
    pg.goto(B + '/admin/#abteilungen'); pg.wait_for_selector('#view-abteilungen tr[data-kg="20"]')
    pg.click('#view-abteilungen tr[data-kg="20"]'); pg.wait_for_selector('#dlg-abruppe[open]')
    check('390 px: Dialog passt ins Bild', pg.evaluate("(() => { const r = document.querySelector('#dlg-abruppe').getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1; })()"))
    pg.screenshot(path=os.path.join(SH, 'abteilungen_dialog_390.png'))
    ctx.close()
    br.close()

# ---------- Import „Abwesenheiten aus der Zeiterfassung“ ----------
hr('Max Muster', abteilungNr='', personalnummer='501')
KOPF = ['Vorname', 'Nachname', 'Name (Abwesenheit)', 'Abwesenheitsvergütung', 'Startdatum', 'Enddatum', 'Dauer', 'Mitarbeiternummer', 'Zweite Mitarbeiternummer', 'Abteilung', 'Standort', 'Gesamt']
GRID = [KOPF]
for vor, nach, nr, abt, tag in (('Max', 'Muster', '501', 'logistik', '13.01.2025'), ('Nina', 'Neu', '502', 'Lager & Logistik', '14.01.2025'),
                                ('Udo', 'Unbekannt', '503', 'Marketing', '15.01.2025')):
    GRID.append([vor, nach, None, None, None, None, None, nr, None, abt, 'STAFL', '8:00'])
    GRID.append([None, None, 'Urlaub ', 'Abgezogen vom Urlaub', tag, tag, '08:00', None, None, None, None, None])
D = {'blaetter': [{'name': 'Abwesenheiten', 'grid': GRID}]}
st, v = P.call('import_pruefen', {'art': 'zeiterfassung', 'daten': D, 'quelle': 'Bericht.xlsx', 'optionen': {'abteilungen': True}})
hw = ' '.join(h['text'] for h in v.get('hinweise', []))
zl = {(z['art'], z['name']): z['text'] for z in v.get('zeilen', []) if z['schluessel'] != 'Abwesenheiten'}
check('Zeiterfassung: Abteilung über den früheren Namen zugeordnet', st == 200 and 'Abteilung Lager & Logistik' in zl.get(('geaendert', 'Max Muster'), ''), zl)
check('Zeiterfassung: neuer Mitarbeiter mit Abteilung aus den Stammdaten, unbekannte ohne', '(Lager & Logistik)' in zl.get(('neu', 'Nina Neu'), '') and '(' not in zl.get(('neu', 'Udo Unbekannt'), '('), zl)
check('Zeiterfassung: unbekannte Abteilung als Hinweis', '„Marketing“' in hw and 'Stammdaten' in hw, hw)
st, _ = P.call('import_uebernehmen', {'art': 'zeiterfassung', 'daten': D, 'quelle': 'Bericht.xlsx', 'optionen': {'abteilungen': True}, 'stand': v['stand']})
pp = personen()
check('Zeiterfassung übernommen: Nummern gespeichert, unbekannte ohne Abteilung', st == 200 and roh('Max Muster').get('abteilungNr') == '20' and pp['Nina Neu']['abteilungNr'] == '20'
      and pp['Udo Unbekannt']['abteilung'] == '' and pp['Udo Unbekannt']['abteilungNr'] is None, (st, pp.get('Nina Neu'), pp.get('Udo Unbekannt')))

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
