"""Stammdaten → Lieferanten und Versandarten (Wunsch des Inhabers 06.11.2026): vollständiger Lieferanten-Export der
Warenwirtschaft (alle Spalten, Name darf fehlen, Umsätze nur für Bearbeiter), Versandarten (Nummer, Text), Versandart am
Kunden (Kundenimport und Kunden-Dialog), Anzahl Kunden und Lieferanten je Versandart, Rechte, Revision, CSV-Import in
Windows-1252 über die Ansicht und die Importzentrale, Protokoll, Anzeige, 390 px. Kundenimport mit dem Export „Kundenstammdaten
komplett“ (alle 60 Spalten: Name 2/3, Angebot und Verband laut WinAB, Hermes, Lademittelbestand, Ansprechpartner der Warenwirtschaft).
Nur Testdaten (tests/fixtures/lieferanten, tests/fixtures/kunden)."""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, FIX, SH, storage_raw

PW = 'Sicheres-Passwort-1'
LF_CSV = FIX + '/lieferanten/lieferanten.csv'
VA_CSV = FIX + '/lieferanten/versandarten.csv'
KD_CSV = FIX + '/kunden/kundendaten.csv'
KS_CSV = FIX + '/kunden/kundenstamm-komplett.csv'
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

# ---------- Versandarten: Schnittstelle ----------
check('Versandarten: ohne Anmeldung gesperrt', Client().call('versandarten')[0] == 401)
st, r = L.call('versandarten')
check('Versandarten: Leser darf ansehen (leer)', st == 200 and r['groups'] == [], r)
check('Versandarten: Leser darf nicht speichern', L.call('versandarten_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'X'}]})[0] == 403)
check('Versandarten: Text fehlt → 422', E.call('versandarten_save', {'rev': 0, 'groups': [{'nr': '1', 'name': ''}]})[0] == 422)
st, r = E.call('versandarten_save', {'rev': 0, 'groups': [{'nr': '24', 'name': 'Spedition Nordtest'}, {'nr': '1', 'name': 'Direktlieferung', 'fremd': 'x'}], 'quelle': 'Test'})
check('Versandarten: gespeichert, sortiert, nur Nummer und Text', st == 200 and r['groups'] == [{'nr': '1', 'name': 'Direktlieferung'}, {'nr': '24', 'name': 'Spedition Nordtest'}], r)
check('Versandarten: veraltete Revision → 409', E.call('versandarten_save', {'rev': 0, 'groups': []})[0] == 409)

# ---------- Lieferanten: Schnittstelle ----------
check('Lieferanten: ohne Anmeldung gesperrt', Client().call('lieferanten')[0] == 401)
LIEF = [{'nr': '2550077', 'name': 'Musterfleisch GmbH & Co. KG', 'kurz': 'MUSTER', 'versandart': '1', 'ort': 'Hamburg', 'umsatzJahr': '12.345,67 €', 'kwUmsatzVorjahr': '23.456,78 €', 'lademittelbestand': '-12'},
        {'nr': '4000099', 'name': ''}]
check('Lieferanten: Leser darf nicht speichern', L.call('lieferanten_save', {'rev': 0, 'groups': LIEF})[0] == 403)
st, r = E.call('lieferanten_save', {'rev': 0, 'groups': LIEF, 'quelle': 'Test'})
check('Lieferanten: Bearbeiter speichert – Name darf fehlen, alle Felder', st == 200 and len(r['groups']) == 2 and r['groups'][1]['nr'] == '4000099' and r['groups'][1]['name'] == ''
      and r['groups'][0]['umsatzJahr'] == '12.345,67 €' and r['groups'][0]['lademittelbestand'] == '-12' and r['groups'][0]['versandart'] == '1', r)
st, r = L.call('lieferanten')
g = (r.get('groups') or [{}])[0]
check('Lieferanten: Leser sieht Name, Versandart und Ort – keine Umsätze', st == 200 and g.get('name') == 'Musterfleisch GmbH & Co. KG' and g.get('versandart') == '1'
      and 'umsatzJahr' not in g and 'kwUmsatzVorjahr' not in g, g)
check('Lieferanten: Bearbeiter sieht Umsätze', E.call('lieferanten')[1]['groups'][0].get('kwUmsatzVorjahr') == '23.456,78 €')
A.call('user_save', {'id': {u['username']: u['id'] for u in A.call('users')[1]['users']}['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': ['kunden.sehen'], 'deny': ['stammdaten.sehen']})
check('Lieferanten: nur Kundenrecht reicht nicht, Versandarten schon (Kunden-Dialog)', L.call('lieferanten')[0] == 403 and L.call('versandarten')[0] == 200)
A.call('user_save', {'id': {u['username']: u['id'] for u in A.call('users')[1]['users']}['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': [], 'deny': []})
check('Protokoll: Lieferanten und Versandarten übernommen', all(t in json.dumps(A.call('log')[1], ensure_ascii=False) for t in ('Lieferanten aus „Test“ übernommen: 2 neu', 'Versandarten aus „Test“ übernommen: 2 neu')))

# ---------- Versandart am Kunden ----------
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'firma': 'Versandtest GmbH', 'nr': 'VS-1', 'active': True, 'angebote': [], 'rev': rev, 'versandart': '24'})
check('Kunde: Versandart gespeichert', st == 200 and r['customer']['versandart'] == '24', r)
kid = r['customer']['id']
rows = [{'nr': 'VS-1', 'firma': 'egal', 'versandart': '1'}, {'nr': 'VS-2', 'firma': 'Neu mit Versandart', 'versandart': '24'}]
st, r = A.call('kunden_import', {'pruefen': True, 'rows': rows})
st, r = A.call('kunden_import', {'rev': r['rev'], 'rows': rows})
kd = {c['nr']: c for c in A.call('kunden')[1]['customers'] if c.get('nr', '').startswith('VS-')}
check('Kundenimport: Versandart aus der Datei (neu und geändert)', st == 200 and kd['VS-1'].get('versandart') == '1' and kd['VS-2'].get('versandart') == '24', {k: v.get('versandart') for k, v in kd.items()})
check('Versandarten: Anzahl Kunden und Lieferanten je Versandart', A.call('versandarten')[1].get('zuordnung') == {'1': 2, '24': 1}, A.call('versandarten')[1].get('zuordnung'))
check('Versandarten: Zuordnung nur mit Kundenrecht', 'zuordnung' not in E.call('versandarten')[1] or E.call('versandarten')[1]['zuordnung'] is not None)
for liste in ('lieferanten', 'versandarten'):
    rv = A.call(liste)[1]['rev']
    assert A.call(liste + '_save', {'rev': rv, 'groups': []})[0] == 200   # für den Oberflächentest leeren

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Lieferanten und Versandarten unter Stammdaten nach den Vertretern', a.locator('#vt-lieferanten').is_visible() and a.locator('#vt-versandarten').is_visible()
          and y('#vt-vertreter') < y('#vt-lieferanten') < y('#vt-versandarten') < y('#side-admin'))

    # ---------- Versandarten: Oberfläche ----------
    a.click('#vt-versandarten'); a.wait_for_selector('#view-versandarten .ed-empty')
    check('Versandarten leer: nennt die erwarteten Spalten', 'Nummer; Text' in a.inner_text('#view-versandarten'))
    a.set_input_files('#va-file', LF_CSV); a.wait_for_selector('#toast.show:has-text("Versandarten")')
    check('Versandarten: Lieferanten-Export wird erkannt', not a.locator('#dlg-va-import').evaluate('d => d.open'))
    a.set_input_files('#va-file', VA_CSV); a.wait_for_selector('#dlg-va-import[open]')
    check('Versandarten: Vorschau 6 neu', a.inner_text('#vai-neu') == '6', a.inner_text('#va-import-body'))
    a.click('#vai-ok'); a.wait_for_selector('#view-versandarten tr[data-kg="19"]')
    v = {x['nr']: x['name'] for x in doc('versandarten')['groups']}
    check('Versandarten übernommen (Windows-1252, Umlaute)', len(v) == 6 and v['19'] == 'Testspedition ex Kühlhaus' and v['1'] == 'Direktlieferung', v)
    t = a.inner_text('#view-versandarten thead')
    check('Versandarten-Liste: Text und Kunden und Lieferanten', 'Text' in t and 'Kunden und Lieferanten' in t, t)

    # ---------- Lieferanten: Oberfläche ----------
    a.click('#vt-lieferanten'); a.wait_for_selector('#view-lieferanten .ed-empty')
    check('Lieferanten leer: nennt die Spalten des Exports', 'Lademittelbestände' in a.inner_text('#view-lieferanten') and 'Versandart' in a.inner_text('#view-lieferanten'))
    a.set_input_files('#lf-file', KD_CSV); a.wait_for_selector('#toast.show:has-text("Kundendaten-Export")')
    check('Lieferanten: Kundendaten-Export wird erkannt', not a.locator('#dlg-lf-import').evaluate('d => d.open'))
    a.set_input_files('#lf-file', LF_CSV); a.wait_for_selector('#dlg-lf-import[open]')
    check('Lieferanten: Vorschau 5 neu (auch ohne Namen und mit „*“)', a.inner_text('#lfi-neu') == '5', a.inner_text('#lf-import-body'))
    a.click('#lfi-ok'); a.wait_for_selector('#view-lieferanten tr[data-kg="2550077"]')
    lf = {x['nr']: x for x in doc('lieferanten')['groups']}
    m = lf.get('2550077', {})
    check('Lieferanten: alle Spalten übernommen (Windows-1252)', len(lf) == 5 and m.get('name') == 'Musterfleisch GmbH & Co. KG' and m.get('kurz') == 'MUSTER' and m.get('strasse') == 'Teststraße 1'
          and m.get('konto') == '79999' and m.get('kondition') == '56' and m.get('vertreter') == '15' and m.get('vertreterName') == 'Tina Testerin' and m.get('versandart') == '1'
          and m.get('umsatzJahr') == '12.345,67 €' and m.get('kwUmsatzVorjahr') == '23.456,78 €' and m.get('lademittelbestand') == '-12' and m.get('angelegtAm') == '03.11.2021'
          and lf['2150099'].get('gln') == '4000000 00000 1' and lf['2150099']['name'] == 'Kühlhaus Test GmbH' and lf['4000099']['name'] == '', m)
    zeile = a.inner_text('#view-lieferanten tr[data-kg="2550077"]')
    check('Lieferanten-Liste: Versandart mit Text', '1 · Direktlieferung' in zeile and 'Hamburg' in zeile and 'Musterfleisch' in zeile, zeile)
    check('Lieferant ohne Namen: Liste zeigt die Nummer', a.locator('#view-lieferanten tr[data-kg="4000099"]').count() == 1)
    a.fill('#lf-q', 'nordtest'); a.wait_for_function("document.querySelectorAll('#view-lieferanten tr[data-kg]').length === 1")
    check('Lieferanten-Suche', a.locator('#view-lieferanten tr[data-kg="4000098"]').count() == 1)
    a.fill('#lf-q', '')
    a.click('#view-lieferanten tr[data-kg="2550077"]'); a.wait_for_selector('#dlg-lfruppe[open]')
    check('Lieferanten-Dialog mit allen Feldern', all(a.locator(f'#lfruppe-body [name="{f}"]').count() == 1 for f in ('nr', 'name', 'kurz', 'versandart', 'strasse', 'konto', 'kondition', 'vertreterName', 'gln', 'lademittelbestand', 'umsatzJahr', 'angelegtAm')))
    a.fill('#lfruppe-body [name=telefon]', '0400 999'); a.click('#lfruppe-body [type=submit]')
    a.wait_for_function("!document.querySelector('#dlg-lfruppe').open")
    check('Lieferant änderbar, übrige Felder bleiben', next(x for x in doc('lieferanten')['groups'] if x['nr'] == '2550077')['telefon'] == '0400 999'
          and next(x for x in doc('lieferanten')['groups'] if x['nr'] == '2550077')['umsatzJahr'] == '12.345,67 €')
    a.click('#view-lieferanten tr[data-kg="4000099"]'); a.wait_for_selector('#dlg-lfruppe[open]')
    check('Lieferant ohne Namen: Dialog-Titel mit Nummer', 'Lieferant 4000099' in a.inner_text('#lf-title'), a.inner_text('#lf-title'))
    a.click('#lfruppe-body [data-close]'); a.wait_for_function("!document.querySelector('#dlg-lfruppe').open")
    a.screenshot(path=SH + '/lieferanten.png')
    a.click('#vt-versandarten')   # die Liste wird neu geladen – bis dahin steht der alte Stand (ohne Lieferanten) noch da
    a.wait_for_function("(document.querySelector('#view-versandarten tr[data-kg=\"1\"] .kg-n') || {}).textContent === '3'")
    check('Versandarten: Anzahl zugeordneter Kunden und Lieferanten (Kunde + 2 Lieferanten bzw. Kunde + 1 Lieferant)', a.inner_text('#view-versandarten tr[data-kg="24"] .kg-n').strip() == '2',
          (a.inner_text('#view-versandarten tr[data-kg="1"]'), a.inner_text('#view-versandarten tr[data-kg="24"]')))

    # ---------- Versandart im Kunden-Dialog ----------
    a.click('#vt-kunden'); a.wait_for_selector('#k-list tr[data-kid]')
    a.fill('#k-q', 'Versandtest'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Versandtest")')
    a.click('#k-list tr[data-kid]:has-text("Versandtest")'); a.wait_for_selector('#dlg-kunde[open]')
    check('Kunden-Dialog: Versandart mit Text, gespeicherter Wert gewählt', '1 · Direktlieferung' in a.inner_text('#kunde-body [name="versandart"]') and a.input_value('#kunde-body [name="versandart"]') == '1')
    a.select_option('#kunde-body [name="versandart"]', '2')
    a.evaluate("document.querySelector('#k-file').dataset.alt = '1'")   # nach dem Speichern zeichnet die Ansicht neu – erst danach importieren
    a.click('#kunde-body [type=submit]')
    a.wait_for_function("!document.querySelector('#dlg-kunde').open", timeout=10000)
    a.wait_for_function("document.querySelector('#k-file') && !document.querySelector('#k-file').dataset.alt")
    check('Kunden-Dialog: Versandart gespeichert', next(c for c in A.call('kunden')[1]['customers'] if c['id'] == kid).get('versandart') == '2')

    # ---------- Kundenimport: Export „Kundenstammdaten komplett“ (alle Spalten) ----------
    a.set_input_files('#k-file', LF_CSV); a.wait_for_selector('#toast.show:has-text("Lieferanten-Export")')
    check('Kundenimport: Lieferanten-Export wird erkannt', not a.locator('#dlg-k-import').evaluate('d => d.open'))
    a.set_input_files('#k-file', KS_CSV); a.wait_for_selector('#dlg-k-import[open] #ki-neu')
    check('Kundenstamm komplett: Vorschau 2 neu', a.inner_text('#ki-neu') == '2', a.inner_text('#k-import-body'))
    check('Kundenstamm komplett: Hinweis nennt die weiteren Spalten', 'Hermes, Lademittelbestand, Ansprechpartner der Warenwirtschaft' in a.inner_text('#k-import-body'))
    a.click('#k-import-body [data-ki="ok"]'); a.wait_for_selector('#toast.show:has-text("Kunden übernommen")', timeout=15000)
    kd = {c.get('nr'): c for c in A.call('kunden')[1]['customers']}
    w1, w2 = kd.get('1000201', {}).get('wawi', {}), kd.get('1000202', {}).get('wawi', {})
    check('Kundenstamm komplett: alle weiteren Spalten als Daten der Warenwirtschaft', w1.get('lademittelbestand') == 37 and w1.get('hermesDeckung') == 25000 and w1.get('hermesId') == '0070000001'
          and w1.get('name2') == '- Fleischtheke -' and w1.get('name3') == 'Lager Teststadt' and w1.get('winabAngebot') == 'ANGEBOT 1' and w1.get('verband') == '4'
          and w1.get('steuernummer') == '12/345/67890' and w1.get('partnerName') == 'Herr Probe' and w1.get('partner2') == 'Frau Muster (Buchhaltung)' and w1.get('partnerAbteilung') == 'Einkauf'
          and w1.get('partnerEmail') == 'probe@komplett.example' and w1.get('partnerTelefon') == '040-208' and w1.get('partnerTelefax') == '040-209' and w1.get('abPerMail') is True
          and kd['1000201'].get('versandart') == '1' and kd['1000201'].get('firma') == 'Komplett Testmarkt GmbH', w1)
    check('Kundenstamm komplett: negativer Lademittelbestand mit Tausenderpunkt, Angebot ohne Leerzeichen, Versandart', w2.get('lademittelbestand') == -1250 and w2.get('winabAngebot') == 'KEIN Angebot'
          and w2.get('abPerMail') is False and 'hermesId' not in w2 and kd['1000202'].get('versandart') == '24' and kd['1000202'].get('land') == 'Österreich', (w2, kd.get('1000202', {}).get('land')))
    check('Kundenstamm komplett: Leser sieht keine Daten der Warenwirtschaft', all('wawi' not in c for c in L.call('kunden')[1].get('customers', [])) if L.call('kunden')[0] == 200 else True)
    a.fill('#k-q', '1000201'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Komplett Testmarkt")')
    a.click('#k-list tr[data-kid]:has-text("Komplett Testmarkt")'); a.wait_for_selector('#dlg-kunde[open]')
    ww = a.locator('#kunde-body .k-wawi').text_content()
    check('Kunden-Dialog: Daten der Warenwirtschaft mit Lademittelbestand, Hermes, Name 2 und Ansprechpartner', all(t in ww for t in ('Lademittelbestand (WinAB)37', 'Hermes-ID0070000001', 'Name 2- Fleischtheke -',
          'Ansprechpartner (WinAB)Herr Probe', 'Angebot (WinAB)ANGEBOT 1', 'AB per Mailja')) and 'Hermes-Deckung25.000,00' in ww.replace('\u00a0', ' ').replace(' €', ''), ww)
    a.locator('#kunde-body [data-close]').first.click()
    a.wait_for_function("!document.querySelector('#dlg-kunde').open")
    a.fill('#k-q', '')
    a.set_viewport_size({'width': 390, 'height': 820})
    a.click('#vt-lieferanten'); a.wait_for_selector('#view-lieferanten tr[data-kg]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Lieferanten 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/lieferanten-mobil.png')
    a.click('#vt-versandarten'); a.wait_for_selector('#view-versandarten tr[data-kg]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Versandarten 390 px: kein seitliches Scrollen', over <= 1, over)

    # ---------- Leser ----------
    lp = br.new_page(viewport={'width': 1280, 'height': 900})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#vt-lieferanten:not([hidden])')
    lp.click('#vt-lieferanten'); lp.wait_for_selector('#view-lieferanten tr[data-kg]')
    check('Leser: Lieferanten nur ansehen, ohne Umsätze im Speicher des Browsers', lp.locator('#lf-import').count() == 0 and lp.locator('#lf-add').count() == 0
          and 'umsatz' not in json.dumps(lp.evaluate("fetch('../api/?action=lieferanten').then((r) => r.json())")).lower())
    lp.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
