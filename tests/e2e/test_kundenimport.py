"""Stammdaten → Angebote mit Kundengruppen (Freischaltung über die Gruppe), Import der Kundenstammdaten aus der
Warenwirtschaft (CSV) und Passwort-Auswahl im Kunden-Dialog. Nur synthetische Testdaten (tests/fixtures/kunden)."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from auth_helpers import expire_session
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, FIX, SH, SMTP_PORT, storage_raw

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
CSV = FIX + '/kunden/kundendaten.csv'
PREISE = FIX + '/angebote/artikelpreise.csv'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def bestaetigung_ablaufen(cl):
    jar = next(h.cookiejar for h in cl.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor))
    expire_session(next(c.value for c in jar if c.name == 'WA_ADMIN'))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200
assert A.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'Gastronomie'}, {'nr': '5', 'name': 'Kantinen'}, {'nr': '7', 'name': 'Handel'}]})[0] == 200


def kunde(body):
    rev = A.call('kunden')[1]['rev']
    st, r = A.call('kunde_save', {'rev': rev, 'active': True, **body})
    assert st == 200, r
    return r['customer']


k5 = kunde({'firma': 'Kantine Gruppe Fünf', 'nr': 'T-5', 'gruppe': '5', 'email': 'k5@example.org', 'angebote': [],
            'login': {'username': 'kantine.fuenf', 'password': KPW, 'mustChange': False, 'active': True}})
k7 = kunde({'firma': 'Handel Gruppe Sieben', 'nr': 'T-7', 'gruppe': '7', 'email': 'k7@example.org', 'angebote': ['bela'],
            'login': {'username': 'handel.sieben', 'password': KPW, 'mustChange': False, 'active': True}})
K5 = Client('203.0.113.5'); assert K5.call('kunde_login', {'username': 'kantine.fuenf', 'password': KPW})[0] == 200
K7 = Client('203.0.113.7'); assert K7.call('kunde_login', {'username': 'handel.sieben', 'password': KPW})[0] == 200
ids = lambda cl: [o['id'] for o in cl.call('kunde_status')[1]['kunde']['angebote']]   # noqa: E731

# ---------- Angebote ↔ Kundengruppen ----------
o = A.call('offers')[1]
check('Angebote ohne Kundengruppen (Ausgangslage)', all('gruppen' not in x for x in o['offers']) and 'stdGruppen' not in o)
check('Ausgangslage: Gruppe ohne Angebot bekommt das Wochenangebot, Kunde ohne Gruppe nicht', ids(K5) == ['std'] and ids(K7) == ['std', 'bela'], (ids(K5), ids(K7)))
offers = [{**x} for x in o['offers']]
edeka = next(x for x in offers if x['id'] == 'edeka')
check('Leser darf Angebote nicht ändern', L.call('offers_save', {'rev': o['rev'], 'offers': offers})[0] == 403)
edeka['gruppen'] = ['5', '99']
check('unbekannte Kundengruppe abgewiesen', E.call('offers_save', {'rev': o['rev'], 'offers': offers})[0] == 422)
edeka['gruppen'] = ['x y']
check('ungültige Kundengruppe abgewiesen', E.call('offers_save', {'rev': o['rev'], 'offers': offers})[0] == 422)
edeka['gruppen'] = ['5', '5']
bela = next(x for x in offers if x['id'] == 'bela')
bela['gruppen'] = ['5']
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': offers})
check('Kundengruppe nur einem Angebot zuordenbar', st == 422 and 'bereits dem Angebot' in r.get('error', ''), r)
del bela['gruppen']
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': offers, 'stdGruppen': ['1']})
check('Bearbeiter ordnet Kundengruppen zu (doppelte entfallen, Wochenangebot nicht zuordenbar)', st == 200 and next(x for x in r['offers'] if x['id'] == 'edeka')['gruppen'] == ['5'] and 'stdGruppen' not in r and 'stdGruppen' not in doc('angebote'), r)
check('Kunde der Gruppe sieht das Angebot ohne eigene Freischaltung', ids(K5) == ['edeka'] and K5.call('offer&angebot=edeka')[0] == 200, ids(K5))
check('Gruppe mit Angebot: kein automatisches Wochenangebot mehr', 'std' not in ids(K5))
check('Kunde anderer Gruppe nicht', 'edeka' not in ids(K7) and K7.call('offer&angebot=edeka')[0] == 403 and ids(K7) == ['std', 'bela'], ids(K7))
kl = {c['id']: c for c in A.call('kunden')[1]['customers']}
check('Kundenliste: wirksam, direkt und über Gruppe getrennt', kl[k5['id']]['angebote'] == ['edeka'] and kl[k5['id']]['angeboteDirekt'] == [] and kl[k5['id']]['angeboteGruppe'] == ['edeka']
      and kl[k7['id']]['angeboteDirekt'] == ['bela'], {k: kl[k5['id']][k] for k in ('angebote', 'angeboteDirekt', 'angeboteGruppe')})
assert A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
pub = A.call('draft')[1]['published']
st, r = K5.call('kunde_bestellung', {'angebot': 'edeka', 'publishedAt': pub.get('publishedAt', ''), 'positions': [{'id': pub['items'][0]['id'], 'qty': 1}], 'requestId': 'gruppen-request-00000001'})
check('Bestellwunsch aus dem Gruppen-Angebot möglich', st == 200, r)
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {**{k: kl[k5['id']].get(k, '') for k in ('firma', 'nr', 'gruppe', 'email')}, 'id': k5['id'], 'rev': rev, 'active': True, 'angebote': [],
                              'login': {'username': 'kantine.fuenf', 'password': '', 'active': True}})
check('Speichern des Kunden schreibt Gruppen-Angebote nicht fest', st == 200 and next(c for c in doc('kunden')['customers'] if c['id'] == k5['id'])['angebote'] == [], r)
o = A.call('offers')[1]
st, r = E.call('offers_save', {'rev': o['rev'], 'offers': [{k: v for k, v in x.items() if k != 'gruppen'} for x in o['offers']]})
check('ohne Angabe bleiben Kundengruppen erhalten (ältere Oberfläche)', st == 200 and next(x for x in r['offers'] if x['id'] == 'edeka').get('gruppen') == ['5'], r.get('offers'))
check('Protokoll: Kundengruppen am Angebot', 'Kundengruppen' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ---------- Kundenimport: Schnittstelle ----------
ROWS = [{'nr': '2000001', 'firma': 'Import Eins GmbH', 'strasse': 'Weg 1', 'plz': '20095', 'ort': 'Hamburg', 'land': 'Deutschland', 'telefon': '040-1', 'email': 'eins@example.org', 'gruppe': '1'},
        {'nr': 'T-7', 'firma': 'Anderer Name aus WaWi', 'strasse': 'Neue Straße 7', 'plz': '10115', 'ort': 'Berlin', 'land': '', 'telefon': '', 'email': 'wawi@example.org', 'gruppe': '1'},
        {'nr': '2000002', 'firma': 'X', 'gruppe': ''}]
check('Leser darf nicht importieren', L.call('kunden_import', {'pruefen': True, 'rows': ROWS})[0] == 403)
check('Bearbeiter ohne Kundenrecht darf nicht importieren', E.call('kunden_import', {'pruefen': True, 'rows': ROWS})[0] == 403)
rev0 = A.call('kunden')[1]['rev']
st, r = A.call('kunden_import', {'pruefen': True, 'rows': ROWS})
check('Vorschau: 1 neu, 1 aktualisiert, 1 ohne Firma – nichts gespeichert', st == 200 and r['stat']['neu'] == 1 and r['stat']['aktualisiert'] == 1 and r['stat']['ohneFirma'] == 1
      and A.call('kunden')[1]['rev'] == rev0 and r['beispiele']['aktualisiert'][0]['felder'] == ['Kundengruppe', 'Straße', 'PLZ', 'Ort'], r)
bestaetigung_ablaufen(A)
st, r = A.call('kunden_import', {'rev': rev0, 'rows': ROWS})
check('Übernehmen verlangt Passwortbestätigung', st == 403 and r.get('code') == 'confirmation_required')
assert A.call('reauth', {'password': PW})[0] == 200
check('veraltete Revision → 409', A.call('kunden_import', {'rev': rev0 - 1, 'rows': ROWS})[0] == 409)
st, r = A.call('kunden_import', {'rev': rev0, 'rows': ROWS, 'quelle': 'test.csv'})
cs = {c.get('nr'): c for c in doc('kunden')['customers']}
c7 = cs.get('T-7', {})
check('bestehender Kunde: Gruppe/Adresse übernommen; Firma, E-Mail, Zugang, Freischaltung bleiben', st == 200 and c7.get('gruppe') == '1' and c7.get('strasse') == 'Neue Straße 7'
      and c7.get('firma') == 'Handel Gruppe Sieben' and c7.get('email') == 'k7@example.org' and c7.get('login', {}).get('username') == 'handel.sieben' and c7.get('angebote') == ['bela'], c7)
n1 = cs.get('2000001', {})
check('neuer Kunde: aktiv, ohne Zugang, kein Wochenangebot per E-Mail', n1.get('active') is True and n1.get('login') is None and n1.get('mailAngebot') is False and n1.get('angebote') == [] and n1.get('gruppe') == '1', n1)
check('neuer Kunde der Gruppe 1 sieht das Wochenangebot über die Gruppe', next(c for c in A.call('kunden')[1]['customers'] if c.get('nr') == '2000001')['angeboteGruppe'] == ['std'])
st2 = A.call('kunden_import', {'pruefen': True, 'rows': ROWS})[1]['stat']
check('erneuter Import: unverändert', st2['neu'] == 0 and st2['aktualisiert'] == 0 and st2['unveraendert'] == 2, st2)
check('Protokoll: Kunden importiert', 'Kunden aus „test.csv“ importiert: 1 neu, 1 aktualisiert' in json.dumps(A.call('log')[1], ensure_ascii=False))
st, r = A.call('kunden_import', {'pruefen': True, 'anlegen': False, 'rows': [{'nr': '2999999', 'firma': 'Nicht anlegen'}]})
check('„nur aktualisieren“: neue Kunden werden nicht angelegt', r['stat']['neu'] == 0 and r['stat']['nichtAngelegt'] == 1)
check('Zeilenzahl begrenzt', A.call('kunden_import', {'pruefen': True, 'rows': [{'nr': '1', 'firma': 'AB'}] * 10001})[0] == 422)
# Ausgangslage für den Oberflächentest: Bestandskunde mit Nummer 1000003 (hat schon Zugang und Freischaltung) und einer ohne Nummer
kunde({'firma': 'Bestandskunde Gepflegt', 'nr': '1000003', 'email': 'bestand@example.org', 'angebote': ['edeka'],
       'login': {'username': 'bestand.kunde', 'password': KPW, 'mustChange': False, 'active': True}})
kunde({'firma': 'Ohne Nummer KG', 'plz': '50667', 'ort': 'Köln', 'angebote': []})

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Angebote unter Stammdaten', a.locator('#vt-angebote').is_visible() and y('#vt-vkgruppen') < y('#vt-angebote') < y('#vt-kunden'))

    # ---------- Stammdaten → Angebote ----------
    a.click('#vt-angebote'); a.wait_for_selector('#view-angebote tr[data-oi]')
    row = '#view-angebote tr[data-oi]:has(input[value="Wochenangebot Bela"])'
    check('Angebote-Ansicht mit Kundengruppen und Kundenanzahl', '5 · Kantinen' in a.inner_text('#view-angebote tr[data-oi]:has(input[value="Wochenangebot Edeka"])')
          and 'alle übrigen Kundengruppen' in a.inner_text('#view-angebote tr.of-std') and a.locator('#view-angebote tr.of-std [data-ofa="gruppen"]').count() == 0, a.inner_text('#view-angebote tbody')[:300])
    a.click(row + ' [data-ofa="gruppen"]'); a.wait_for_selector('#dlg-of-gruppen[open]')
    a.fill('#ofg-q', 'handel'); a.wait_for_function("[...document.querySelectorAll('#of-gruppen-body .ofg-list li')].filter(l => !l.hidden).length === 1")
    check('Gruppenauswahl durchsuchbar', 'Handel' in a.inner_text('#of-gruppen-body .ofg-list li:not([hidden])'))
    a.check('#of-gruppen-body .ofg-list input[value="7"]'); a.click('#of-gruppen-body [data-ofg="ok"]')
    a.wait_for_selector(row + ' .of-chip:has-text("Handel")')
    check('ungespeichert-Hinweis und Speichern aktiv', 'Nicht gespeichert' in a.inner_text('#of-state') and a.locator('#view-angebote [data-ofa="save"]').is_enabled())
    a.screenshot(path=SH + '/stammdaten-angebote.png')
    a.click('#view-angebote [data-ofa="save"]'); a.wait_for_selector('#toast.show:has-text("Angebote gespeichert")')
    check('gespeichert: Bela für Kundengruppe 7', next(x for x in doc('angebote')['offers'] if x['id'] == 'bela').get('gruppen') == ['7'])
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden])')
    a.click('[data-ob=manage]'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    check('„Angebote verwalten“ im Angebot öffnet Stammdaten → Angebote', a.get_attribute('#vt-angebote', 'aria-selected') == 'true')

    # ---------- Kundengruppe nur einmal zuordenbar ----------
    a.click('#view-angebote tr[data-oi]:has(input[value="Wochenangebot Edeka"]) [data-ofa="gruppen"]'); a.wait_for_selector('#dlg-of-gruppen[open]')
    g7 = '#of-gruppen-body .ofg-list li:has(input[value="7"])'
    check('Gruppenauswahl: Gruppe eines anderen Angebots gesperrt', a.locator(g7 + ' input').is_disabled() and 'bei „Wochenangebot Bela“' in a.inner_text(g7), a.inner_text(g7))
    a.click('#of-gruppen-body [data-close]')

    # ---------- Preise importieren ----------
    a.set_input_files('#of-file', PREISE); a.wait_for_selector('#dlg-of-preise[open]')
    t = a.inner_text('#of-preise-body')
    zeile = lambda z: a.inner_text(f'#of-preise-body tr[data-ofp-ziel="{z}"]').split('\t')   # noqa: E731
    check('Preis-Vorschau: Wochenangebot 2 Preise, 1 geändert', zeile('std')[2:5] == ['2', '1', '0'], zeile('std'))
    check('Preis-Vorschau: Gruppenpreise beim Angebot der Gruppe', zeile('edeka')[2:5] == ['1', '0', '1'] and zeile('bela')[2:5] == ['1', '0', '1'], (zeile('edeka'), zeile('bela')))
    check('Preis-Vorschau: Gruppe ohne Angebot, neues Angebot vorgeschlagen', '1 Gastronomie (2)' in t and a.locator('#of-preise-body [data-ofp="anlegen"]').is_checked() and zeile('neu:1')[0] == 'Wochenangebot Gastronomie (neu)', t)
    check('Preis-Vorschau: übersprungen (nicht im Angebot, ohne Preis)', '1 Artikelnummer steht nicht im Angebot' in t and '1 Zeilen ohne Preis' in t, t)
    a.uncheck('#of-preise-body [data-ofp="anlegen"]'); a.wait_for_function("!document.querySelector('#of-preise-body tr[data-ofp-ziel=\"neu:1\"]')")
    check('ohne Anlegen: Gruppe 1 entfällt', a.locator('#of-preise-body tr[data-ofp-ziel]').count() == 3)
    a.check('#of-preise-body [data-ofp="anlegen"]'); a.wait_for_selector('#of-preise-body tr[data-ofp-ziel="neu:1"]')
    a.screenshot(path=SH + '/angebote-preisimport.png')
    a.click('#of-preise-body [data-ofp="ok"]'); a.wait_for_selector('#toast.show:has-text("Preise im Entwurf eingetragen")', timeout=15000)
    neu = next((x for x in doc('angebote')['offers'] if x.get('gruppen') == ['1']), {})
    check('neues Angebot für Kundengruppe 1 angelegt', neu.get('name') == 'Wochenangebot Gastronomie', neu)
    def entwurf_ok():
        d = A.call('draft')[1].get('draft') or {}
        it = next((i for i in d.get('items', []) if i.get('code') == '10601'), {})
        return it if it.get('price', {}).get('value') == 26.1 else None
    import time
    it = None
    for _ in range(80):
        it = entwurf_ok()
        if it: break
        time.sleep(0.25)
    v = (it or {}).get('variants', {})
    check('Entwurf: Wochenpreis und Gruppenpreise eingetragen', it and v.get('edeka', {}).get('value') == 22.0 and v.get('bela', {}).get('value') == 24.0 and v.get(neu.get('id'), {}).get('value') == 23.0, it)
    check('veröffentlichtes Angebot noch unverändert', next(i for i in A.call('draft')[1]['published']['items'] if i.get('code') == '10601')['price']['value'] == 25.54)

    # ---------- Kunden importieren ----------
    a.click('#vt-kunden'); a.wait_for_selector('#k-list tr[data-kid]')
    a.set_input_files('#k-file', CSV); a.wait_for_selector('#dlg-k-import[open] #ki-neu')
    t = a.inner_text('#k-import-body')
    check('Vorschau: 4 neu, 2 aktualisiert (Nummer bzw. Firma+PLZ)', a.inner_text('#ki-neu') == '4' and a.inner_text('#ki-akt') == '2', t)
    check('Vorschau: übersprungen und Hinweise', '1 ohne Firma übersprungen' in t and '1× doppelte Kundennummer' in t and '1× ungültige E-Mail' in t and '999 (1)' in t, t)
    check('Vorschau: „*“-Kunden standardmäßig übersprungen', '1 in der Datei' in t and 'Gelöschter Kunde' not in t)
    a.uncheck('#k-import-body [data-ki="stern"]'); a.wait_for_function("document.querySelector('#ki-neu') && document.querySelector('#ki-neu').textContent === '5'")
    check('ohne Überspringen: 5 neu', True)
    a.check('#k-import-body [data-ki="stern"]'); a.wait_for_function("document.querySelector('#ki-neu') && document.querySelector('#ki-neu').textContent === '4'")
    a.screenshot(path=SH + '/kunden-import.png')
    a.click('#k-import-body [data-ki="ok"]'); a.wait_for_selector('#toast.show:has-text("Kunden übernommen")', timeout=15000)
    cs = {c.get('nr'): c for c in doc('kunden')['customers']}
    check('importiert: Umlaute, Land als Name, erste gültige E-Mail', cs.get('1000008', {}).get('firma') == 'Bäckerei Größe & Söhne' and cs.get('1000003', {}).get('land') == 'Österreich'
          and cs.get('1000002', {}).get('email') == 'kantine@example.org' and cs.get('1000006', {}).get('land') == 'Frankreich', {k: cs.get(k, {}).get('land') for k in ('1000003', '1000006')})
    check('unbekannte Gruppe leer, ungültige E-Mail leer', cs.get('1000006', {}).get('gruppe') == '' and cs.get('1000006', {}).get('email') == '')
    b = cs.get('1000003', {})
    check('Bestandskunde: Firma, E-Mail, Zugang, Freischaltung bleiben', b.get('firma') == 'Bestandskunde Gepflegt' and b.get('email') == 'bestand@example.org' and b.get('login', {}).get('username') == 'bestand.kunde' and b.get('angebote') == ['edeka'] and b.get('gruppe') == '7')
    check('Kunde ohne Nummer über Firma+PLZ gefunden und Nummer ergänzt', cs.get('1000004', {}).get('firma') == 'Ohne Nummer KG' and cs.get('1000004', {}).get('gruppe') == '5')
    check('„*“-Kunde nicht angelegt, Umsatz/Kredit nicht übernommen', '1000005' not in cs and not any(s in json.dumps(doc('kunden'), ensure_ascii=False) for s in ('12.345', '3.000,00', 'Testvertreter', '4000000000017')))
    a.wait_for_selector('#k-list tr[data-kid]')
    a.select_option('#k-g', '5'); a.wait_for_function("document.querySelector('#k-count').textContent.startsWith('3 Kunden')")
    check('Filter nach Kundengruppe', a.locator('#k-list tr[data-kid]').count() == 3, a.inner_text('#k-count'))
    check('Angebot über die Kundengruppe in der Liste gekennzeichnet', a.locator('#k-list tr[data-kid] .k-chip.grp:has-text("Edeka")').count() == 3)
    a.select_option('#k-g', '')
    a.fill('#k-q', 'Bestandskunde'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Bestandskunde")')
    a.click('#k-list tr[data-kid]:has-text("Bestandskunde")'); a.wait_for_selector('#dlg-kunde[open]')
    check('Kunden-Dialog: Angebot direkt freigeschaltet, Gruppen-Angebot gekennzeichnet', a.locator('#kunde-body [name="angebot"][value="edeka"]').is_checked()
          and a.locator('#kunde-body label:has(input[value="bela"]) .k-viagr').count() == 1)
    check('Bestandskunde der Gruppe 7 sieht Bela über die Gruppe', 'bela' in next(c for c in A.call('kunden')[1]['customers'] if c.get('nr') == '1000003')['angeboteGruppe'])
    a.click('#kunde-body [data-close]')

    # ---------- Neuer Kunde: Passwort-Auswahl ----------
    a.fill('#k-q', ''); a.click('#k-add'); a.wait_for_selector('#dlg-kunde[open]')
    check('Passwort-Auswahl als zwei Karten', a.locator('#kunde-body .k-pwopt').count() == 2 and 'Einladung per E-Mail' in a.inner_text('#kunde-body .k-pwmode') and 'Startpasswort vergeben' in a.inner_text('#kunde-body .k-pwmode'))
    box = a.locator('#kunde-body .k-pwopt').first.bounding_box()
    check('Karten in normaler Höhe (keine leeren Eingabefelder)', box and box['height'] < 140 and a.locator('#kunde-body .k-pwopt input[type=radio]').first.evaluate('e => getComputedStyle(e).opacity') == '0', box)
    manual = a.locator('#kunde-body .k-pwopt:has(input[value="manual"])')
    check('mit E-Mail-Versand: Einladung vorgewählt, kein Passwortfeld', a.locator('#kunde-body .k-pwopt input[value="invite"]').is_checked() and not a.locator('#kunde-body .k-pwfld').first.is_visible())
    manual.click()
    check('Karte „Startpasswort vergeben“ wählen zeigt das Passwortfeld', manual.locator('input').is_checked() and a.locator('#kunde-body .k-pwfld').first.is_visible())
    a.fill('#kunde-body [name=firma]', 'Kartentest GmbH')
    a.locator('#kunde-body .k-pwmode').scroll_into_view_if_needed()
    a.screenshot(path=SH + '/kunde-neu-passwort.png')
    a.set_viewport_size({'width': 390, 'height': 820})
    a.locator('#kunde-body .k-pwmode').scroll_into_view_if_needed()
    a.screenshot(path=SH + '/kunde-neu-passwort-mobil.png')
    a.click('#kunde-body [data-close]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    wide = a.evaluate("[...document.querySelectorAll('#view-kunden *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0, 4).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right))")
    check('Kundenliste 390 px: kein seitliches Scrollen', over <= 1, (over, wide))
    a.click('#vt-angebote'); a.wait_for_selector('#view-angebote tr[data-oi]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Angebote 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/stammdaten-angebote-mobil.png')
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
