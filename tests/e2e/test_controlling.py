"""Controlling (Modul controlling, Oberfläche controlling.intern unter /module/controlling/) – Bereich Umsatzstatistik, Reiter
Monatsmeldung: Kg, Umsatz und Rohmarge (früher DB) je Vertreter und Monat aus den importierten Umsatzdaten (keine Erfassung von Hand mehr).

Geprüft: Register (fertig, produktiv, Modulzugang standardmäßig niemand); Rechte serverseitig (GR-103): ohne Anmeldung,
ohne Modulzugang, Modulzugang ohne Bereichsrecht (keine Bereiche, Umsatz 403), Ansehen; frühere Erfassung entfernt (Aktion
und Recht gibt es nicht mehr); Werte je Monat und Vertreter aus den Umsatzdaten (Hauptvertreter des Kunden, „ohne Vertreter“,
Nummer nicht in den Stammdaten, ohne Berechnung zählt nicht), Jahr wählbar (jüngstes vorausgewählt, ungültiges Jahr 422),
DB nur mit controlling.umsatz_ek und bestand.einkaufspreise (GR-008); Vertreter aus den Stammdaten entfernt → Werte bleiben
mit Nummer; Oberfläche (Reiter Auswertung und Monatsmeldung, kein Reiter Datenpflege, Kennzahlen, Anteile, Liniendiagramm,
Jahreswechsel, Hinweis ohne EK-Recht, kein Bereich; 1280 und 390 px, hell und dunkel, keine JavaScript-Fehler).
Nur synthetische Testdaten.
"""
import datetime as dt
import json
import os
import re

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_sqlite, storage_write

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def dokument(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lea', 'Lea Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['controlling.umsatz_sehen']}),
          ('bea', 'Bea Einkauf', 'viewer', 'Pflege-Konto-34', {'grant': ['controlling.umsatz_ek', 'bestand.einkaufspreise']}),
          ('zoe', 'Zoe Zugang', 'editor', 'Zugang-Konto-56', {'grant': ['controlling.zugang']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-78', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Bb, Z, O, N = K['lea'], K['bea'], K['zoe'], K['otto'], Client('198.51.100.20')

# ── Register und Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['controlling']
ob = mod['oberflaechen'][0]
check('Register: Controlling fertig und produktiv (Freigabe des Inhabers 28.10.2026), Adresse controlling.dashboard-stafl.de/module/controlling/',
      ob['entwicklung'] == 'fertig' and ob['freigabe'] == 'produktiv' and ob['adresse'] == 'https://controlling.dashboard-stafl.de/module/controlling/', ob)
check('Kachel: verfügbar für den Administrator, Ziel controlling.intern', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True
      and mod['kachel']['ziel'] == 'controlling.intern', mod['kachel'])
check('produktiv ohne Testfreigabe: Administrator erreicht das Modul', A.call('controlling_start')[0] == 200 and A.call('controlling_umsatz')[0] == 200)

# ── Rechte ──
check('ohne Anmeldung: kein Zugang (401/404)', N.call('controlling_start')[0] in (401, 404) and N.call('controlling_umsatz')[0] in (401, 404))
check('Bearbeiterrolle ohne Modulzugang (Standard: niemand): 403', O.call('controlling_start')[0] == 403 and O.call('controlling_umsatz')[0] == 403)
st, r = Z.call('controlling_start')
check('nur Modulzugang: Start ok, aber kein Bereich', st == 200 and r['bereiche'] == [], (st, r))
check('nur Modulzugang: Umsatzstatistik 403', Z.call('controlling_umsatz')[0] == 403)
st, r = L.call('controlling_start')
check('Ansehen-Recht: Bereich Umsatzstatistik ohne Bearbeiten (Modulzugang als Voraussetzung)', st == 200
      and r['bereiche'] == [{'id': 'umsatz', 'name': 'Umsatzstatistik', 'bearbeiten': False}], (st, r))
st, r = Bb.call('controlling_start')
check('EK-Recht: Bereich ohne Bearbeiten (Werte nur aus dem Import)', st == 200 and r['bereiche'] == [{'id': 'umsatz', 'name': 'Umsatzstatistik', 'bearbeiten': False}], r)
check('frühere Erfassung von Hand entfernt: Aktion unbekannt, Recht nicht mehr im Katalog', A.call('controlling_umsatz_monat_save', {'rev': 0})[0] == 404
      and 'controlling.umsatz_bearbeiten' not in json.dumps(A.call('rechte')[1], ensure_ascii=False) and 'controlling.umsatz_sehen' in json.dumps(A.call('rechte')[1], ensure_ascii=False))
check('Administrator: alle Bereiche', [b['id'] for b in A.call('controlling_start')[1]['bereiche']] == ['umsatz'])

# ── Stammdaten und importierte Umsatzdaten (synthetisch, direkt gespeichert wie nach einem Import) ──
rev_v = A.call('vertreter')[1].get('rev', 0)
st, r = A.call('vertreter_save', {'rev': rev_v, 'groups': [{'nr': 'V1', 'name': 'Vera Vertrieb', 'kurz': 'VV'}, {'nr': 'V2', 'name': 'Viktor Verkauf'},
                                                           {'nr': '7', 'name': 'Sieben Test', 'kurz': 'ST'}, {'nr': 'V10', 'name': 'Zehn Test'}]})
check('Vertreter in den Stammdaten angelegt', st == 200, r)
rev_v = r.get('rev', rev_v + 1)
storage_write('kunden', {'rev': 1, 'customers': [{'id': 'k1', 'nr': 'K1', 'firma': 'Eins', 'vertreter': 'V1', 'active': True, 'angebote': []},
                                                  {'id': 'k2', 'nr': 'K2', 'firma': 'Zwei', 'vertreter': 'V2', 'active': True, 'angebote': []},
                                                  {'id': 'k3', 'nr': 'K3', 'firma': 'Drei ohne Vertreter', 'vertreter': '', 'active': True, 'angebote': []},
                                                  {'id': 'k4', 'nr': 'K4', 'firma': 'Vier', 'vertreter': 'V99', 'active': True, 'angebote': []}]})
# Zeile: [Tag, Kunde, Artikel, Kolli, Menge (1/1000), Umsatz (Cent), EK-Wert (Cent), Umsatz mit EK (Cent), Positionen, berechnet]
MONATE_D = {'2026-01': [[5, 'K1', 'A1', 10, 1250500, 2500000, 2150000, 2500000, 3, 1], [5, 'K1', 'L1', 0, 20000, 0, 0, 0, 2, 0],
                        [6, 'K2', 'A1', 4, 400000, 1200000, 1140000, 1200000, 2, 1], [7, 'K3', 'A2', 1, 50000, 100000, 0, 0, 1, 1],
                        [8, 'K4', 'A2', 1, 25000, 50000, 40000, 50000, 1, 1], [9, 'K9', 'A2', 1, 10000, 30000, 20000, 30000, 1, 1]],
            '2026-02': [[3, 'K1', 'A1', 1, 100000, 100000, 90000, 100000, 1, 1]],
            '2025-12': [[1, 'K1', 'A1', 2, 800000, 2000000, 1800000, 2000000, 2, 1]]}
if not storage_sqlite():
    os.makedirs(os.path.join(os.environ['UDATA'], 'controlling-umsatzdaten'), exist_ok=True)
for m, z in MONATE_D.items():
    storage_write('controlling-umsatzdaten/' + m, {'monat': m, 'hash': '0' * 64, 'zeilen': z})
storage_write('controlling-umsatzdaten', {'rev': 1, 'monate': {m: {'hash': '0' * 64, 'zeilen': len(z), 'pos': 1, 'umsatz': 1, 'menge': 1, 'posOhne': 0, 'kunden': 1, 'artikel': 1,
                                                                   'ersterTag': z[0][0], 'letzterTag': z[-1][0]} for m, z in sorted(MONATE_D.items())},
                                          'kunden': ['K1', 'K2', 'K3', 'K4', 'K9'], 'artikel': ['A1', 'A2', 'L1'],
                                          'importe': [{'t': '2026-11-01T10:00:00Z', 'vonName': 'Ina Import', 'quelle': 'Test.csv', 'zeitraum': ['2025-12-01', '2026-02-03']}]})

st, d = L.call('controlling_umsatz')
jan = d['jahre'].get('2026', {}).get('01', {}) if st == 200 else {}
check('Monatsmeldung aus den Umsatzdaten: jüngstes Jahr, Werte je Hauptvertreter, ohne Berechnung zählt nicht', st == 200 and d['jahr'] == '2026' and d['jahreListe'] == ['2026', '2025']
      and jan.get('V1') == {'kg': 1250.5, 'umsatz': 25000, 'db': None} and jan.get('V2') == {'kg': 400, 'umsatz': 12000, 'db': None}, d)
check('Kunden ohne Vertreter und ohne Stammsatz unter „ohne Vertreter“, Nummer nicht in den Stammdaten eigene Zeile', jan.get('_', {}).get('umsatz') == 1300 and jan.get('V99', {}).get('umsatz') == 500, jan)
check('Monate sortiert, leere Monate fehlen', list(d['jahre']['2026']) == ['01', '02'])
check('Vertreterliste: Stammdaten (natürlich sortiert), dann Nummern ohne Stammsatz, „ohne Vertreter“ zuletzt', [v['nr'] for v in d['vertreter']] == ['7', 'V1', 'V2', 'V10', 'V99', '_']
      and {v['nr']: v['anzeige'] for v in d['vertreter']}['V1'] == 'V1 – VV' and {v['nr']: v['anzeige'] for v in d['vertreter']}['V2'] == 'V2 – Viktor Verkauf'
      and {v['nr']: v['anzeige'] for v in d['vertreter']}['V99'] == 'Vertreter V99 (nicht in den Stammdaten)' and d['vertreter'][-1]['anzeige'] == 'ohne Vertreter', d['vertreter'])
check('Monate 01–12, Stand des letzten Imports, Rechte ohne EK', [m['nr'] for m in d['monate']] == [f'{i:02d}' for i in range(1, 13)] and d['monate'][2]['name'] == 'März'
      and d['geaendert'] == {'t': '2026-11-01T10:00:00Z', 'vonName': 'Ina Import'} and d['rechte'] == {'ek': False, 'importieren': False} and d['umsatzdaten'] == {'vorhanden': True}, d)
st, d = Bb.call('controlling_umsatz')
jan = d['jahre']['2026']['01']
check('mit controlling.umsatz_ek und bestand.einkaufspreise: DB = Umsatz mit EK − EK-Wert', d['rechte']['ek'] is True and jan['V1']['db'] == 3500 and jan['V2']['db'] == 600
      and jan['_']['db'] == 100 and jan['V99']['db'] == 100, jan)
st, d = L.call('controlling_umsatz&jahr=2025')
check('Jahr wählbar: 2025', st == 200 and d['jahr'] == '2025' and d['jahre']['2025']['12']['V1'] == {'kg': 800, 'umsatz': 20000, 'db': None}, d.get('jahre'))
st, d = L.call('controlling_umsatz&jahr=2024')
check('Jahr ohne Umsatzdaten: leer', st == 200 and d['jahre'] == {} and d['jahr'] == '2024')
check('ungültiges Jahr: 422', L.call('controlling_umsatz&jahr=1999')[0] == 422 and L.call('controlling_umsatz&jahr=abc')[0] == 422)

# ── Vertreter aus den Stammdaten entfernt: Werte bleiben mit Nummer ──
st, r = A.call('vertreter_save', {'rev': rev_v, 'groups': [{'nr': 'V1', 'name': 'Vera Vertrieb', 'kurz': 'VV'}, {'nr': '7', 'name': 'Sieben Test', 'kurz': 'ST'},
                                                           {'nr': 'V10', 'name': 'Zehn Test'}]})
check('V2 aus den Stammdaten entfernt', st == 200, r)
st, d = L.call('controlling_umsatz')
v2 = next((v for v in d['vertreter'] if v['nr'] == 'V2'), None)
check('entfernter Vertreter bleibt mit seinen Umsätzen (Nummer, nicht aktiv)', v2 is not None and v2['aktiv'] is False and v2['anzeige'] == 'Vertreter V2 (nicht in den Stammdaten)'
      and d['jahre']['2026']['01']['V2']['umsatz'] == 12000, d['vertreter'])
check('kein Dokument der früheren Erfassung angelegt', dokument('controlling-umsatz') is None)

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ').replace('\u202f', ' ')   # Zahlenformat: geschützte Leerzeichen vor € und %

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900, ziel='#ctl-app:not([hidden])'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin', color_scheme=thema)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/controlling/'); pg.wait_for_selector(ziel)
        return ctx, pg

    ctx, pg = anmelden('bea', 'Pflege-Konto-34', '198.51.100.11')
    pg.wait_for_selector('#ctl-u-tabs [data-tab="auswertung"][aria-selected="true"]')
    check('Bereich Umsatzstatistik aktiv, mit Umsatzdaten zuerst Reiter Auswertung, Adresse #umsatz', pg.get_attribute('#ctl-bereiche [data-bereich="umsatz"]', 'aria-selected') == 'true'
          and pg.url.endswith('#umsatz'))
    check('kein Reiter Datenpflege mehr', pg.locator('#ctl-u-tabs [data-tab="datenpflege"]').count() == 0 and pg.locator('#ctl-u-dialog').count() == 0)
    pg.click('#ctl-u-tabs [data-tab="uebersicht"]'); pg.wait_for_selector('#ctl-u-kpis .ctl-kpi')
    check('Reiter Monatsmeldung, Adresse #umsatz/uebersicht, Jahr 2026 vorausgewählt', pg.url.endswith('#umsatz/uebersicht') and pg.input_value('#ctl-u-jahr') == '2026'
          and [o for o in pg.locator('#ctl-u-jahr option').all_inner_texts()] == ['2026', '2025'])
    kpi = text(pg, '#ctl-u-kpis')
    check('Kennzahlen: Umsatz und Rohmarge des Jahres aus den Umsatzdaten (Bezeichnung wie in der Auswertung)', '39.800,00 €' in kpi and '4.400,00 €' in kpi
          and 'rohmarge %' in kpi.lower() and not re.search(r'\bDB\b|spanne', kpi, re.I) and 'rohmarge %' in text(pg, '.ctl-vertretertabelle thead').lower(), kpi)
    zeilen = text(pg, '#ctl-u-vertreterzeilen')
    check('Anteile berechnet (V1 26.000 von 39.800 € = 65,33 %), ohne Vertreter und Nummer ohne Stammsatz als Zeilen', '65,33 %' in zeilen and 'ohne Vertreter' in zeilen
          and 'Vertreter V2 (nicht in den Stammdaten)' in zeilen, zeilen[:600])
    check('Stand: aus den importierten Umsatzdaten mit letztem Import', 'importierten Umsatzdaten' in text(pg, '#ctl-u-stand') and 'Ina Import' in text(pg, '#ctl-u-stand'))
    pg.select_option('#ctl-u-diagrammart', 'linie'); pg.wait_for_selector('#ctl-u-diagramm polyline')
    check('Liniendiagramm', pg.locator('#ctl-u-diagramm svg[role="img"]').count() == 1)
    pg.click('#ctl-u-vertreterfilter summary'); pg.uncheck('#ctl-u-vertreteroptionen [data-vertreter="V2"]')
    pg.wait_for_function("!document.querySelector('#ctl-u-vertreterzeilen').textContent.includes('V2')")
    check('Vertreterfilter wirkt auf Kennzahlen', '27.800,00 €' in text(pg, '#ctl-u-kpis'), text(pg, '#ctl-u-kpis'))
    pg.screenshot(path=os.path.join(SH, 'controlling_umsatz_1280.png'), full_page=True)
    pg.select_option('#ctl-u-jahr', '2025')
    pg.wait_for_function("document.querySelector('#ctl-u-kpis').textContent.includes('20.000,00')")
    check('Jahreswechsel lädt 2025 vom Server', '20.000,00 €' in text(pg, '#ctl-u-kpis') and pg.input_value('#ctl-u-jahr') == '2025')
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('lea', 'Leserin-Konto-12', '198.51.100.10', breite, thema)
        pg.wait_for_selector('#ctl-u-tabs [data-tab="uebersicht"]'); pg.click('#ctl-u-tabs [data-tab="uebersicht"]'); pg.wait_for_selector('#ctl-u-kpis .ctl-kpi')
        check(f'{breite}px {thema}: ohne EK-Recht Rohmarge leer mit Hinweis', 'Rohmarge und Rohmarge % nur mit den Rechten' in text(pg, '#ctl-u-fussnote') and '–' in text(pg, '#ctl-u-kpis'))
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        if thema == 'dark':
            check(f'{breite}px: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)')
        pg.screenshot(path=os.path.join(SH, f'controlling_umsatz_{breite}_{thema}.png'), full_page=True)
        ctx.close()

    ctx, pg = anmelden('zoe', 'Zugang-Konto-56', '198.51.100.12', ziel='#ctl-kein-bereich:not([hidden])')
    check('nur Modulzugang: Hinweis „kein Bereich freigeschaltet“', 'kein Bereich' in pg.inner_text('#ctl-kein-bereich'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
