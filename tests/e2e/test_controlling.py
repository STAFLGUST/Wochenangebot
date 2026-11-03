"""Controlling (Modul controlling, Oberfläche controlling.intern unter /module/controlling/) – Bereich Umsatzstatistik, Reiter
Monatsmeldung: Kg, Umsatz und DB je Vertreter und Monat aus den importierten Umsatzdaten (keine Erfassung von Hand mehr).

Geprüft: Register (fertig, produktiv, Modulzugang standardmäßig niemand); Rechte serverseitig (GR-103): ohne Anmeldung,
ohne Modulzugang, Modulzugang ohne Bereichsrecht (keine Bereiche, Umsatz 403), Ansehen; frühere Erfassung entfernt (Aktion
und Recht gibt es nicht mehr); Werte je Monat und Vertreter aus den Umsatzdaten (Hauptvertreter des Kunden, „ohne Vertreter“,
Nummer nicht in den Stammdaten, ohne Berechnung zählt nicht), Jahr wählbar (jüngstes vorausgewählt, ungültiges Jahr 422),
DB nur mit controlling.umsatz_ek und bestand.einkaufspreise (GR-008); Vertreter aus den Stammdaten entfernt → Werte bleiben
mit Nummer; Oberfläche (Reiter Auswertung und Monatsmeldung, kein Reiter Datenpflege, Kennzahlen, Anteile, Liniendiagramm,
Jahreswechsel, Hinweis ohne EK-Recht, kein Bereich; 1280 und 390 px, hell und dunkel, keine JavaScript-Fehler).
Bereich Bestandsverlauf (02.11.2026): eigenes Recht controlling.bestand_sehen (Umsatz-Recht genügt nicht), leer ohne Verlauf;
aus synthetischen Tagesständen und Umsatzdaten: Zeitraum (30/90 Tage, eigener, Stichtag), Summen, Ø Bestand, Absatz nur der
Lagerartikel im Zeitraum (führende Null, ohne Berechnung, vor dem Zeitraum), Reichweite, Umschlag, Hinweise lange/knapp/kein
Absatz, Gliederung nach Artikelgruppe und Fleischart, Filter, Detail, 422 bei ungültiger Anfrage; Lagerwert nur mit
controlling.bestand_ek und bestand.einkaufspreise (GR-008); Oberfläche mit Diagramm, Sortierung, Suche, CSV, Pop-up, Filter,
eigener Zeitraum, ohne EK-Recht kein Lagerwert (1280 und 390 px, hell und dunkel).
Bereich Arbeitszeit (02.11.2026): Rechte controlling.arbeitszeit_sehen / _importieren (Umsatz-Recht genügt nicht); Import des
Zeitberichts über die Importzentrale (synthetische .xlsx, Leser im Browser): Folgezeilen mit weiteren Stempeln, unlesbare und
doppelte Zeilen, Stempelfehler (Kommen/Gehen fehlt, Kommen = Gehen, unplausibel lang, ohne Stempel, Saldo passt nicht) markiert
und nicht im bereinigten Saldo, heutiger Tag „laufend“, Abteilung des jüngsten Tages, Gründe von Abwesenheiten nicht gespeichert;
Auswertung je Monat, Mitarbeiter und Abteilung, Filter, Fehlerliste, Pop-up; neuer Import ersetzt nur seinen Zeitraum, 409 bei
veraltetem Stand, 422 bei falscher Datei oder Anfrage; Oberfläche mit Ansichten, Fehlerart, CSV, Pop-up (1280 und 390 px).
Nur synthetische Testdaten.
"""
import datetime as dt
import hashlib
import json
import os
import re
from datetime import date

import openpyxl
from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, WORK, storage_raw, storage_sqlite, storage_write

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
check('Administrator: alle Bereiche (Umsatzstatistik, Bestandsverlauf, Arbeitszeit)', [b['id'] for b in A.call('controlling_start')[1]['bereiche']] == ['umsatz', 'bestand', 'arbeitszeit'])

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
    check('Kennzahlen: Umsatz und DB des Jahres aus den Umsatzdaten; „DB-Anteil am Umsatz“ statt „Spanne“ (andere Rechnung als die Spanne der Auswertung)', '39.800,00 €' in kpi and '4.400,00 €' in kpi
          and re.search(r'\bDB\b', kpi) and 'db-anteil am umsatz' in kpi.lower() and 'spanne' not in kpi.lower() and 'rohmarge' not in kpi.lower()
          and 'db-anteil am umsatz' in text(pg, '.ctl-vertretertabelle thead').lower() and 'spanne' not in text(pg, '.ctl-vertretertabelle thead').lower()
          and 'DB-Anteil am Umsatz = DB ÷ gesamter Umsatz' in text(pg, '#ctl-u-fussnote'), kpi)
    zeilen = text(pg, '#ctl-u-vertreterzeilen')
    check('Anteile berechnet (V1 26.000 von 39.800 € = 65,3 %, Prozent mit 1 Stelle wie überall), ohne Vertreter und Nummer ohne Stammsatz als Zeilen', '65,3 %' in zeilen and 'ohne Vertreter' in zeilen
          and 'Vertreter V2 (nicht in den Stammdaten)' in zeilen, zeilen[:600])
    check('Stand: aus den importierten Umsatzdaten mit letztem Import', 'importierten Umsatzdaten' in text(pg, '#ctl-u-stand') and 'Ina Import' in text(pg, '#ctl-u-stand'))
    pg.select_option('#ctl-u-diagrammart', 'linie'); pg.wait_for_selector('#ctl-u-diagramm polyline')
    check('Liniendiagramm', pg.locator('#ctl-u-diagramm svg[role="img"]').count() == 1)
    pg.click('#ctl-u-vertreterfilter summary'); pg.uncheck('#ctl-u-vertreteroptionen [data-vertreter="V2"]')
    pg.wait_for_function("!document.querySelector('#ctl-u-vertreterzeilen').textContent.includes('V2')")
    check('Vertreterfilter wirkt auf Kennzahlen', '27.800,00 €' in text(pg, '#ctl-u-kpis'), text(pg, '#ctl-u-kpis'))
    pg.screenshot(path=os.path.join(SH, 'controlling_umsatz_1280.png'), full_page=True)
    # Filter „Vertreter“/„Monate“ bedienen sich wie jedes Menü: Escape schließt, ein anderes Menü schließt das offene
    pg.keyboard.press('Escape'); pg.wait_for_function("!document.querySelector('#ctl-u-vertreterfilter').open")
    check('Vertreterfilter: Escape schließt die Auswahl', pg.evaluate("document.activeElement.matches('#ctl-u-vertreterfilter summary')"))
    pg.click('#ctl-u-zeitfilter summary'); pg.wait_for_selector('#ctl-u-zeitfilter[open]')
    pg.click('#ctl-u-vertreterfilter summary'); pg.wait_for_selector('#ctl-u-vertreterfilter[open]')
    check('Monatsfilter schließt beim Öffnen des Vertreterfilters', not pg.evaluate("document.querySelector('#ctl-u-zeitfilter').open"))
    pg.keyboard.press('Escape'); pg.wait_for_function("!document.querySelector('#ctl-u-vertreterfilter').open")
    pg.select_option('#ctl-u-jahr', '2025')
    pg.wait_for_function("document.querySelector('#ctl-u-kpis').textContent.includes('20.000,00')")
    check('Jahreswechsel lädt 2025 vom Server', '20.000,00 €' in text(pg, '#ctl-u-kpis') and pg.input_value('#ctl-u-jahr') == '2025')
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('lea', 'Leserin-Konto-12', '198.51.100.10', breite, thema)
        pg.wait_for_selector('#ctl-u-tabs [data-tab="uebersicht"]'); pg.click('#ctl-u-tabs [data-tab="uebersicht"]'); pg.wait_for_selector('#ctl-u-kpis .ctl-kpi')
        check(f'{breite}px {thema}: ohne EK-Recht DB leer mit Hinweis', 'DB und DB-Anteil am Umsatz nur mit den Rechten' in text(pg, '#ctl-u-fussnote') and '—' in text(pg, '#ctl-u-kpis'))
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        if thema == 'dark':
            check(f'{breite}px: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)')
        pg.screenshot(path=os.path.join(SH, f'controlling_umsatz_{breite}_{thema}.png'), full_page=True)
        ctx.close()

    ctx, pg = anmelden('zoe', 'Zugang-Konto-56', '198.51.100.12', ziel='#ctl-kein-bereich:not([hidden])')
    check('nur Modulzugang: Hinweis „kein Bereich freigeschaltet“', 'kein Bereich' in pg.inner_text('#ctl-kein-bereich'))
    ctx.close()
    br.close()
# ══ Bereich Bestandsverlauf (module/controlling/bestand.php, bestand.js; Auftrag des Inhabers 02.11.2026) ══
BV_NUTZER = (('bert', 'Bert Bestand', 'viewer', 'Bestand-Konto-90', {'grant': ['controlling.bestand_sehen']}),
             ('bernd', 'Bernd Lagerwert', 'viewer', 'Lagerwert-Konto-91', {'grant': ['controlling.bestand_sehen', 'controlling.bestand_ek', 'bestand.einkaufspreise']}),
             ('ella', 'Ella Halb', 'viewer', 'Halb-Konto-92', {'grant': ['controlling.bestand_sehen', 'controlling.bestand_ek']}))
for i, (u, n, r_, p, extra) in enumerate(BV_NUTZER):
    st, rr = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r_, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, rr
    K[u] = Client(f'198.51.100.{30 + i}'); K[u].call('login', {'username': u, 'password': p})
BT, BE, EH = K['bert'], K['bernd'], K['ella']

st, r = BT.call('controlling_start')
check('Bestandsverlauf: eigener Bereich mit controlling.bestand_sehen (ohne Umsatzstatistik)', st == 200
      and r['bereiche'] == [{'id': 'bestand', 'name': 'Bestandsverlauf', 'bearbeiten': False}], r)
check('Bestandsverlauf: ohne Recht 403 (Umsatz-Recht genügt nicht), ohne Modulzugang 403, ohne Anmeldung kein Zugang',
      all(L.call(a)[0] == 403 and O.call(a)[0] == 403 and N.call(a)[0] in (401, 404) for a in ('controlling_bestand', 'controlling_bestand_daten', 'controlling_bestand_detail&dim=artikel&wert=1')))
st, r = BT.call('controlling_bestand')
check('noch kein Verlauf gespeichert: leere Auswertung ohne Fehler', st == 200 and dokument('bestand-verlauf') is None and r['stand']['listen'] == 0
      and r['zeilen'] == [] and r['summen']['kg'] == 0 and r['reihe'] == [], (st, r))

# Synthetische Tagesstände (Format von module/bestand/verlauf.php), Stammdaten und Umsatzdaten der Lagerartikel
STAMM = dokument('stammdaten') or {'rev': 1, 'articles': []}
STAMM['articles'] = [a for a in STAMM.get('articles', []) if str(a.get('code')) not in ('10601', '10823')] + [
    {'code': '10601', 'name': 'Nacken Test', 'category': 'Schwein', 'origin': None, 'condition': 'frisch', 'vkGruppe': 'G10'},
    {'code': '10823', 'name': 'Hüfte Test', 'category': 'Rind', 'origin': None, 'condition': 'frisch', 'vkGruppe': 'G20'}]
storage_write('stammdaten', STAMM)
VKG = dokument('vkgruppen') or {'rev': 1, 'groups': []}
VKG['groups'] = [g for g in VKG.get('groups', []) if g.get('nr') not in ('G10', 'G20')] + [{'nr': 'G10', 'name': 'Schwein frisch'}, {'nr': 'G20', 'name': 'Rind Test'}]
storage_write('vkgruppen', VKG)
# je Artikel [kg, erwartet, Lagerwert EK, kg mit EK, Partien]
BV = {'2026-10-01': {'10601': [100, 0, 500, 100, 1], '10823': [400, 0, 4800, 400, 2]},
      '2026-10-15': {'10601': [200, 0, 1000, 200, 2], '10823': [300, 0, 3600, 300, 2]},
      '2026-10-29': {'10601': [300, 50, 1500, 300, 3], '99999': [10, 0, 0, 0, 1]}}
if not storage_sqlite():
    os.makedirs(os.path.join(os.environ['UDATA'], 'bestand-verlauf'), exist_ok=True)
for d, art in BV.items():
    storage_write('bestand-verlauf/' + d, {'datum': d, 'quelle': 'Test.csv', 'um': d + 'T08:00:00Z', 'von': 'Test', 'felder': ['kg', 'zugang', 'ekWert', 'ekKg', 'partien'],
                                          'artikel': art, 'namen': {'10601': 'Nacken Liste', '10823': 'Hüfte Liste', '99999': 'Unbekannt Test'}})
storage_write('bestand-verlauf', {'v': 1, 'tage': {d: {'kg': sum(w[0] for w in art.values()), 'quelle': 'Test.csv'} for d, art in BV.items()}})
# Zeile: [Tag, Kunde, Artikel, Kolli, Menge (1/1000), Umsatz, EK-Wert, Umsatz mit EK, Positionen, berechnet] – Umsatz 0, damit die Monatsmeldung gleich bleibt
BV_UMSATZ = {'2026-09': [[29, 'K1', '10601', 1, 1000000, 0, 0, 0, 1, 1]],                       # vor dem Zeitraum
             '2026-10': [[5, 'K1', '010601', 1, 30000, 0, 0, 0, 1, 1],                          # Nummer mit führender Null
                         [10, 'K2', '10823', 1, 140000, 0, 0, 0, 1, 1],
                         [12, 'K1', 'A1', 1, 1000000, 0, 0, 0, 1, 1],                            # nie im Bestand: zählt nicht
                         [20, 'K1', '10601', 1, 40000, 0, 0, 0, 1, 1],
                         [20, 'K2', '10601', 0, 500000, 0, 0, 0, 1, 0]]}                        # ohne Berechnung: zählt nicht
UIX = dokument('controlling-umsatzdaten')
for m, z in BV_UMSATZ.items():
    storage_write('controlling-umsatzdaten/' + m, {'monat': m, 'hash': '0' * 64, 'zeilen': z})
    UIX['monate'][m] = {'hash': '0' * 64, 'zeilen': len(z), 'pos': 1, 'umsatz': 0, 'menge': 1, 'posOhne': 0, 'kunden': 1, 'artikel': 1, 'ersterTag': z[0][0], 'letzterTag': z[-1][0]}
UIX['monate'] = dict(sorted(UIX['monate'].items()))
storage_write('controlling-umsatzdaten', UIX)

st, r = BT.call('controlling_bestand')
zz = {z['key']: z for z in r.get('zeilen', [])}
check('Zeitraum: 30 Tage bis zur jüngsten Liste, drei Listen, Absatz bis zum letzten Tag mit Umsatzdaten', st == 200
      and r['zeitraum'] == {'von': '2026-09-30', 'bis': '2026-10-29', 'tage': 30, 'art': '30', 'listen': 3, 'erste': '2026-10-01', 'letzte': '2026-10-29',
                            'absatzBis': '2026-10-20', 'absatzTage': 21}
      and r['stand'] == {'listen': 3, 'erste': '2026-10-01', 'letzte': '2026-10-29', 'umsatzBis': '2026-10-20'}, (st, r.get('zeitraum'), r.get('stand')))
s = r['summen']
check('Summen: Bestand heute, Veränderung, Ø Bestand, Absatz nur der Lagerartikel im Zeitraum, Reichweite, Umschlag', s['kg'] == 310 and s['kgStart'] == 500 and s['delta'] == -38.0
      and s['oKg'] == 436.7 and s['absatz'] == 210 and s['reichweite'] == 31.0 and s['umschlag'] == 0.48 and s['umschlagJahr'] == 8.4 and s['absatzJeTag'] == 10.0
      and s['zugang'] == 50 and s['partien'] == 4 and s['artikel'] == 2 and s['lange'] == 1 and s['knapp'] == 1, s)
check('ohne EK-Recht: kein Lagerwert in der Antwort (GR-008)', r['rechte'] == {'ek': False} and 'ekWert' not in json.dumps(r) and 'ekKg' not in json.dumps(r))
check('Zeilen nach Bestand, Name aus den Stammdaten, sonst aus der Liste; nie im Bestand gewesene Artikel fehlen', [z['key'] for z in r['zeilen']] == ['10601', '99999', '10823']
      and zz['10601']['name'] == 'Nacken Test' and zz['10601']['sub'] == '10601 · Schwein frisch' and zz['99999']['name'] == 'Unbekannt Test' and 'A1' not in zz, r['zeilen'])
z = zz['10601']
check('Artikel: Bestand 300 kg (+200 %), Ø 200 kg, Absatz 70 kg (führende Null, ohne Berechnung und vor dem Zeitraum zählen nicht), Reichweite 90 Tage → lange am Lager',
      z['kg'] == 300 and z['kgStart'] == 100 and z['delta'] == 200.0 and z['oKg'] == 200 and z['absatz'] == 70 and z['reichweite'] == 90.0 and z['umschlag'] == 0.35
      and z['umschlagJahr'] == 6.1 and z['hinweis'] == 'lange' and z['spark'] == [100, 200, 300] and z['zugang'] == 50 and z['partien'] == 3, z)
check('Artikel nicht mehr in der Liste: 0 kg, −100 %, Reichweite 0 → knapp; ohne Absatz: keine Reichweite → kein Absatz', zz['10823']['kg'] == 0 and zz['10823']['delta'] == -100.0
      and zz['10823']['reichweite'] == 0.0 and zz['10823']['hinweis'] == 'knapp' and zz['10823']['absatz'] == 140 and zz['10823']['spark'] == [400, 300, 0]
      and zz['99999']['delta'] is None and zz['99999']['absatz'] == 0 and zz['99999']['reichweite'] is None and zz['99999']['hinweis'] == 'ohne', (zz['10823'], zz['99999']))
check('Tagesreihe je Liste und Absatz je Tag', [(t['d'], t['kg'], t['zugang'], t['partien'], t['artikel']) for t in r['reihe']]
      == [('2026-10-01', 500, 0, 3, 2), ('2026-10-15', 500, 0, 4, 2), ('2026-10-29', 310, 50, 4, 2)]
      and r['absatzReihe'] == [{'d': '2026-10-05', 'kg': 30}, {'d': '2026-10-10', 'kg': 140}, {'d': '2026-10-20', 'kg': 40}]
      and r['grenzen'] == {'lange': 45, 'knapp': 3}, (r['reihe'], r['absatzReihe']))
st, r = BE.call('controlling_bestand')
zz = {z['key']: z for z in r['zeilen']}
check('mit controlling.bestand_ek und bestand.einkaufspreise: Lagerwert gesamt, je Zeile und je Liste', st == 200 and r['rechte']['ek'] is True and r['summen']['ekWert'] == 1500
      and r['summen']['ekKg'] == 300 and zz['10601']['ekWert'] == 1500 and zz['10823']['ekWert'] == 0 and [t['ekWert'] for t in r['reihe']] == [5300, 4600, 1500], r.get('summen'))
st, r = EH.call('controlling_bestand')
check('controlling.bestand_ek ohne bestand.einkaufspreise: kein Lagerwert', st == 200 and r['rechte']['ek'] is False and 'ekWert' not in json.dumps(r))

st, r = BT.call('controlling_bestand&nach=vkgruppe')
zz = {z['key']: z for z in r['zeilen']}
check('nach Artikelgruppe (VK-Gruppe der Stammdaten), ohne Gruppe als eigene Zeile', st == 200 and set(zz) == {'G10', 'G20', '_'} and zz['G10']['name'] == 'Schwein frisch'
      and zz['G10']['kg'] == 300 and zz['G10']['artikel'] == 1 and zz['_']['name'] == 'ohne Artikelgruppe' and zz['_']['kg'] == 10 and zz['G20']['hinweis'] == 'knapp', r.get('zeilen'))
st, r = BT.call('controlling_bestand&nach=fleischart')
check('nach Fleischart', st == 200 and {z['key']: z['kg'] for z in r['zeilen']} == {'Schwein': 300, 'Rind': 0, '_': 10}, r.get('zeilen'))
st, r = BT.call('controlling_bestand&fa=Schwein')
check('Filter Fleischart wirkt auf Summen, Reihe und Absatz', st == 200 and [z['key'] for z in r['zeilen']] == ['10601'] and r['summen']['kg'] == 300 and r['summen']['absatz'] == 70
      and [t['kg'] for t in r['reihe']] == [100, 200, 300] and r['absatzReihe'] == [{'d': '2026-10-05', 'kg': 30}, {'d': '2026-10-20', 'kg': 40}], r.get('summen'))
check('Filter „ohne Artikelgruppe“ und Artikelnummer (führende Null)', [z['key'] for z in BT.call('controlling_bestand&ag=_')[1]['zeilen']] == ['99999']
      and [z['key'] for z in BT.call('controlling_bestand&a=010601')[1]['zeilen']] == ['10601'])
st, r = BT.call('controlling_bestand&tage=90')
check('90 Tage', st == 200 and r['zeitraum']['von'] == '2026-08-01' and r['zeitraum']['listen'] == 3 and r['zeitraum']['art'] == '90')
st, r = BT.call('controlling_bestand&von=2026-10-10&bis=2026-10-20')
check('eigener Zeitraum: eine Liste, Absatz vom ersten Tag des Zeitraums an', st == 200 and r['zeitraum']['listen'] == 1 and r['zeitraum']['erste'] == '2026-10-15'
      and r['zeitraum']['art'] == 'eigen' and r['summen']['kg'] == 500 and r['summen']['delta'] == 0.0 and r['zeitraum']['absatzTage'] == 11 and r['summen']['absatz'] == 180, r.get('summen'))
st, r = BT.call('controlling_bestand&bis=2026-10-15')
check('Stichtag vor dem letzten Umsatztag: Absatz endet am Stichtag (Umsatz vom 29.09. liegt jetzt im Zeitraum)', st == 200 and r['zeitraum']['listen'] == 2 and r['summen']['kg'] == 500
      and r['zeitraum']['absatzBis'] == '2026-10-15' and r['zeitraum']['absatzTage'] == 30 and r['summen']['absatz'] == 1170, r.get('summen'))
check('ungültige Anfragen: 422', all(BT.call('controlling_bestand' + q)[0] == 422 for q in ('&tage=7', '&nach=kunde', '&von=2026-10-20&bis=2026-10-10', '&von=2025-01-01&bis=2026-10-29',
                                                                                          '&bis=2026-13-01', '&von=abc&bis=2026-10-10')))

st, r = BT.call('controlling_bestand_detail&dim=artikel&wert=10601')
check('Detail Artikel: Kennzahlen, jede Liste mit Partien, Absatz je Tag, ohne Lagerwert', st == 200 and r['zeile']['name'] == 'Nacken Test' and r['zeile']['kg'] == 300
      and [(t['kg'], t['partien']) for t in r['reihe']] == [(100, 1), (200, 2), (300, 3)] and r['absatzReihe'] == [{'d': '2026-10-05', 'kg': 30}, {'d': '2026-10-20', 'kg': 40}]
      and 'ekWert' not in json.dumps(r), r)
st, r = BE.call('controlling_bestand_detail&dim=artikel&wert=10601')
check('Detail mit EK-Recht: Lagerwert je Liste', st == 200 and [t['ekWert'] for t in r['reihe']] == [500, 1000, 1500] and r['zeile']['ekWert'] == 1500)
st, r = BT.call('controlling_bestand_detail&dim=vkgruppe&wert=G20')
check('Detail Artikelgruppe: Verlauf bis 0 kg', st == 200 and r['zeile']['name'] == 'Rind Test' and [t['kg'] for t in r['reihe']] == [400, 300, 0])
st, r = BT.call('controlling_bestand_detail&dim=artikel&wert=55555')
check('Detail unbekannter Artikel: leer mit Nummer', st == 200 and r['zeile']['name'] == 'Artikel 55555' and [t['kg'] for t in r['reihe']] == [0, 0, 0], r.get('zeile'))
check('Detail ungültig: 422', BT.call('controlling_bestand_detail&dim=kunde&wert=K1')[0] == 422 and BT.call('controlling_bestand_detail&dim=artikel&wert=')[0] == 422)
st, r = BT.call('controlling_bestand_daten')
check('Grunddaten: Stand, Rechte, Auswahllisten (Gruppen, Fleischarten, Artikel der jüngsten Liste)', st == 200 and r['stand']['listen'] == 3 and r['stand']['umsatzBis'] == '2026-10-20'
      and r['rechte'] == {'ek': False} and {'nr': 'G10', 'name': 'Schwein frisch'} in r['optionen']['vkgruppen'] and 'Schwein' in r['optionen']['fleischarten']
      and {a['nr'] for a in r['optionen']['artikel']} == {'10601', '99999'} and r['zeitraeume'] == [30, 90, 365], r)
check('Auswertung schreibt nichts: Verlauf unverändert', set(dokument('bestand-verlauf')['tage']) == set(BV))

with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ').replace(' ', ' ')

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/controlling/#bestand'); pg.wait_for_selector('#ctl-b-kpis .ctl-kpi')
        return ctx, pg

    ctx, pg = anmelden('bernd', 'Lagerwert-Konto-91', '198.51.100.31')
    check('Oberfläche: Bereich Bestandsverlauf aktiv (#bestand)', pg.get_attribute('#ctl-bereiche [data-bereich="bestand"]', 'aria-selected') == 'true' and pg.url.endswith('#bestand'))
    kpi = text(pg, '#ctl-b-kpis')
    check('Kennzahlen: Bestand, Reichweite, Umschlag, Lagerwert (EK)', '310 kg' in kpi and '31 Tage' in kpi and '0,5 ×' in kpi and '1.500,00 €' in kpi and 'lagerwert' in kpi.lower()
          and '1 lange am Lager, 1 knapp' in kpi, kpi)
    check('Stand: jüngste Liste und letzter Tag mit Umsatzdaten', '29.10.2026' in text(pg, '#ctl-b-stand') and '20.10.2026' in text(pg, '#ctl-b-stand'))
    check('Diagramm: ein Punkt je Liste, ein Balken je Tag mit Absatz', pg.locator('#ctl-b-diagramm .ctl-b-punkt').count() == 3 and pg.locator('#ctl-b-diagramm .ctl-b-balken').count() == 3)
    zeilen = pg.locator('#ctl-b-zeilen > li')
    check('Liste: drei Artikel mit Hinweisen', zeilen.count() == 3 and 'Nacken Test' in zeilen.nth(0).inner_text() and 'lange am Lager' in zeilen.nth(0).inner_text()
          and 'kein Absatz' in zeilen.nth(1).inner_text() and 'knapp' in zeilen.nth(2).inner_text() and '1.500,00 €' in text(pg, '#ctl-b-zeilen'), text(pg, '#ctl-b-zeilen')[:500])
    pg.click('#ctl-b-wert [data-wert="ekWert"]'); pg.wait_for_selector('#ctl-b-wert [data-wert="ekWert"][aria-pressed="true"]')
    check('Diagramm wahlweise Lagerwert (ohne Absatzbalken)', '1.500,00 €' in text(pg, '#ctl-b-diagramm') and pg.locator('#ctl-b-diagramm .ctl-b-balken').count() == 0)
    pg.select_option('#ctl-b-sort', 'reichweiteAuf')
    check('Sortierung: kürzeste Reichweite zuerst, ohne Reichweite ans Ende', 'Hüfte Test' in zeilen.nth(0).inner_text() and 'Unbekannt Test' in zeilen.nth(2).inner_text())
    pg.fill('#ctl-b-suche', 'hüfte')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 1")
    check('Suche in der Liste', 'Hüfte Test' in text(pg, '#ctl-b-zeilen'))
    pg.fill('#ctl-b-suche', '')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 3")
    with pg.expect_download() as dl:
        pg.click('#ctl-b-csv')
    inhalt = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV der Liste mit Reichweite und Lagerwert', 'Reichweite Tage' in inhalt and 'Lagerwert €' in inhalt and 'Nacken Test' in inhalt and '"90,0"' in inhalt, inhalt[:300])
    pg.click('#ctl-b-zeilen [data-key="10601"]')
    pg.wait_for_selector('#ctl-b-dialog[open] .ctl-b-tabelle tbody tr')
    dt = text(pg, '#ctl-b-dialog')
    check('Pop-up Artikel: Kennzahlen, jede Liste (neueste zuerst), Absatz seit voriger Liste bis zum letzten Umsatztag', 'Nacken Test' in dt and pg.locator('#ctl-b-dialog tbody tr').count() == 3
          and '40 kg bis 20.10.' in pg.locator('#ctl-b-dialog tbody tr').nth(0).inner_text().replace('\xa0', ' ') and '30 kg' in pg.locator('#ctl-b-dialog tbody tr').nth(1).inner_text().replace('\xa0', ' ') and 'lagerwert' in dt.lower() and pg.locator('#ctl-b-d-diagramm svg').count() == 1, pg.locator('#ctl-b-dialog tbody').inner_text())
    pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
    pg.screenshot(path=os.path.join(SH, 'controlling_bestand_detail_1280.png'))
    pg.click('#ctl-b-dialog [data-zu]')
    pg.click('#ctl-b-nach [data-nach="vkgruppe"]')
    pg.wait_for_function("document.querySelector('#ctl-b-zeilen') && document.querySelector('#ctl-b-zeilen').textContent.includes('Schwein frisch')")
    pg.click('#ctl-b-zeilen [data-key="G10"]')
    pg.wait_for_selector('#ctl-b-dialog [data-als-filter]')
    pg.click('#ctl-b-dialog [data-als-filter]')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 1 && document.querySelector('#ctl-b-chips').textContent.includes('Schwein frisch')")
    check('Gruppe als Filter übernommen: Chip, Liste wieder je Artikel', 'Nacken Test' in text(pg, '#ctl-b-zeilen') and text(pg, '#ctl-b-filterzahl') == '1'
          and pg.get_attribute('#ctl-b-nach [data-nach="artikel"]', 'aria-pressed') == 'true')
    pg.click('#ctl-b-chips [data-chip="ag"]')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 3")
    pg.click('#ctl-b-filterknopf'); pg.wait_for_selector('#ctl-b-filterdialog[open]')
    pg.check('#ctl-b-filterdialog input[data-f="fa"][value="Rind"]'); pg.click('#ctl-b-filterdialog [data-uebernehmen]')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 1")
    check('Filter-Pop-up: Fleischart Rind', 'Hüfte Test' in text(pg, '#ctl-b-zeilen') and 'Fleischart: Rind' in text(pg, '#ctl-b-chips'))
    pg.click('#ctl-b-chips [data-chip="fa"]')
    pg.wait_for_function("document.querySelectorAll('#ctl-b-zeilen > li').length === 3")
    pg.click('#ctl-b-zeit [data-zeit="eigen"]'); pg.wait_for_selector('#ctl-b-eigen:not([hidden])')
    pg.fill('#ctl-b-von', '2026-10-10'); pg.fill('#ctl-b-bis', '2026-10-20'); pg.dispatch_event('#ctl-b-bis', 'change')
    pg.wait_for_function("document.querySelector('#ctl-b-kpis').textContent.includes('500 kg')")
    check('eigener Zeitraum über die Datumsfelder', '1 Liste im Zeitraum' in text(pg, '#ctl-b-stand'), text(pg, '#ctl-b-stand'))
    pg.click('#ctl-b-zeit [data-zeit="30"]')
    pg.wait_for_function("document.querySelector('#ctl-b-kpis').textContent.includes('310 kg')")
    pg.screenshot(path=os.path.join(SH, 'controlling_bestand_1280.png'), full_page=True)
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('bert', 'Bestand-Konto-90', '198.51.100.30', breite, thema)
        ganz = pg.inner_text('#ctl-b-bestand')
        check(f'{breite}px {thema}: ohne EK-Recht kein Lagerwert, stattdessen Artikel am Lager', 'lagerwert' not in ganz.lower() and 'artikel am lager' in text(pg, '#ctl-b-kpis').lower()
              and pg.locator('#ctl-b-wert').count() == 0 and pg.locator('#ctl-b-sort option[value="ekWert"]').count() == 0)
        check(f'{breite}px {thema}: kein waagerechtes Scrollen, ein Bereich ohne Bereichsleiste', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1') and pg.is_hidden('#ctl-bereiche'))
        if breite == 390:
            pg.click('#ctl-b-zeilen [data-key="10823"]'); pg.wait_for_selector('#ctl-b-dialog[open] .ctl-b-tabelle tbody tr')
            check(f'390px {thema}: Pop-up ohne waagerechtes Scrollen, Reichweite „knapp“', 'knapp' in text(pg, '#ctl-b-dialog')
                  and pg.evaluate("(() => { const d = document.querySelector('#ctl-b-dialog'); return d.scrollWidth <= d.clientWidth + 1; })()"))
            pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
            pg.screenshot(path=os.path.join(SH, f'controlling_bestand_detail_{breite}_{thema}.png'))
            pg.click('#ctl-b-dialog [data-zu]')
        pg.screenshot(path=os.path.join(SH, f'controlling_bestand_{breite}_{thema}.png'), full_page=True)
        ctx.close()
    br.close()
# ── Bereich Arbeitszeit: Zeitbericht der Zeiterfassung (synthetisch) ──
AZ_NUTZER = (('aron', 'Aron Arbeitszeit', 'Arbeitszeit-Konto-21', ['controlling.arbeitszeit_sehen']),
             ('ida', 'Ida Import', 'Zeitimport-Konto-22', ['controlling.arbeitszeit_importieren']))
AZ_PW = {u: pw for u, _, pw, _ in AZ_NUTZER}
for u, n, pw, grant in AZ_NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': pw, 'mustChange': False, 'grant': grant})
    assert st == 200, r_
AR = Client('198.51.100.40'); AR.call('login', {'username': 'aron', 'password': AZ_PW['aron']})
ID = Client('198.51.100.41'); ID.call('login', {'username': 'ida', 'password': AZ_PW['ida']})
pid = lambda q: 'p' + hashlib.sha256(q.encode()).hexdigest()[:12]   # noqa: E731  Schlüssel wie arbeitszeit.php
P_ANNA, P_BERND, P_CARLA = pid('n:101'), pid('n:102'), pid('m:carla ohnenr')

KOPF = ['Vorname', 'Nachname', 'Datum', 'Hinein', 'In Origin', 'Hinaus', 'Out Origin', 'Dauer', 'Projekt', 'Mitarbeiternummer', 'Zweite Mitarbeiternr.', 'Geplant',
        'Gearbeitete Stunden', 'Geplante Pause', 'Pause', 'Saldo', 'Abwesenheit', 'Remarks', 'Buchungsstandort', 'Department', 'Comments']


def az_zeile(vor, nach, datum, k, g, soll, ist, saldo, nr='', abt='', abw='00:00', pause='00:00', bemerkung=''):
    return [vor, nach, datum, k, 'RFID' if k else '', g, 'RFID' if g else '', '', '', nr or None, None, soll, ist, '00:30', pause, saldo, abw, bemerkung or None, 'Werk', abt, '']


folge = lambda k, g: ['', '', '', k, 'RFID', g, 'RFID', '', '', None, None, '', '', '', '', '', '', None, '', '', '']   # noqa: E731  weiterer Stempel des Vortags
heute = date.today()
ZB = [KOPF,
      az_zeile('Anna', 'Muster', '01-09-2026', '06:00', '14:30', '08:00', '08:00', '00:00', '101', 'Zerlegung', pause='00:30'),
      az_zeile('Anna', 'Muster', '02-09-2026', '06:00', '15:30', '08:00', '09:00', '01:00', '101', 'Zerlegung'),
      az_zeile('Anna', 'Muster', '03-09-2026', '06:00', '', '08:00', '00:00', '-08:00', '101', 'Zerlegung'),                      # Gehen fehlt
      az_zeile('Anna', 'Muster', '04-09-2026', '06:00', '10:00', '08:00', '08:00', '00:00', '101', 'Zerlegung'), folge('10:30', '14:30'),
      az_zeile('Anna', 'Muster', '05-09-2026', '', '', '00:00', '00:00', '00:00', '101', 'Zerlegung'),                             # Samstag: kein Soll
      az_zeile('Anna', 'Muster', '01-10-2026', '', '', '08:00', '00:00', '00:00', '101', 'Zerlegung', abw='08:00', bemerkung='Urlaub'),
      az_zeile('Anna', 'Muster', '02-10-2026', '06:00', '06:00', '08:00', '00:00', '-08:00', '101', 'Zerlegung'),                  # Kommen = Gehen
      az_zeile('Anna', 'Muster', '05-10-2026', '06:00', '14:00', '08:00', '08:00', '00:00', '101', 'Zerlegung'),
      az_zeile('Anna', 'Muster', heute.strftime('%d-%m-%Y'), '06:00', '', '08:00', '00:00', '-08:00', '101', 'Zerlegung'),       # heute: laufend
      az_zeile('Bernd', 'Beispiel', '01-09-2026', '', '', '08:00', '00:00', '-08:00', '102', 'Zerlegung'),                         # ohne Stempel
      az_zeile('Bernd', 'Beispiel', '02-09-2026', '22:00', '12:00', '08:00', '14:00', '06:00', '102', 'Versand'),                  # unplausibel lang
      az_zeile('Bernd', 'Beispiel', '03-09-2026', '07:00', '15:00', '08:00', '07:30', '-00:30', '102', 'Versand'),
      az_zeile('Bernd', 'Beispiel', '04-09-2026', '07:00', '15:00', '08:00', '08:00', '02:00', '102', 'Versand'),                  # Saldo passt nicht
      az_zeile('Carla', 'Ohnenr', '02-09-2026', '', '14:00', '04:00', '04:00', '00:00'),                                           # Kommen fehlt
      az_zeile('Carla', 'Ohnenr', '03-09-2026', '08:00', '12:00', '04:00', '04:00', '00:00'),
      az_zeile('Carla', 'Ohnenr', '03-09-2026', '08:00', '12:00', '04:00', '04:00', '00:00'),                                      # doppelt
      az_zeile('Dora', 'Defekt', 'gestern', '08:00', '12:00', '04:00', '04:00', '00:00'),                                          # Datum unlesbar
      az_zeile('Emil', 'Fehl', '03-09-2026', '25:30', '12:00', '04:00', '04:00', '00:00')]                                         # Uhrzeit unlesbar
os.makedirs(WORK, exist_ok=True)
DATEI = os.path.join(WORK, 'Zeitbericht_Test.xlsx')
wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Zeitbericht'
for z in ZB:
    ws.append(z)
wb.save(DATEI)
DZ = {'blaetter': [{'name': 'Zeitbericht', 'grid': ZB}]}


def zb(cl, daten=DZ, stand=None):
    b = {'art': 'zeitbericht', 'daten': daten, 'quelle': 'Zeitbericht_Test.xlsx', 'optionen': {}}
    if stand is not None:
        b['stand'] = stand
    return cl.call('import_uebernehmen' if stand is not None else 'import_pruefen', b)


check('Arbeitszeit: eigenes Recht – Umsatz-Recht genügt nicht (Bereich fehlt, 403)', 'arbeitszeit' not in [b['id'] for b in L.call('controlling_start')[1]['bereiche']]
      and L.call('controlling_arbeitszeit')[0] == 403 and L.call('controlling_arbeitszeit_daten')[0] == 403 and Z.call('controlling_arbeitszeit')[0] == 403)
check('Arbeitszeit: ohne Anmeldung kein Zugang', N.call('controlling_arbeitszeit')[0] in (401, 404) and N.call('controlling_arbeitszeit_detail&p=' + P_ANNA)[0] in (401, 404))
st, r = AR.call('controlling_start')
check('Ansehen-Recht: nur Bereich Arbeitszeit (Modulzugang als Voraussetzung)', st == 200 and r['bereiche'] == [{'id': 'arbeitszeit', 'name': 'Arbeitszeit', 'bearbeiten': False}], r)
st, r = AR.call('controlling_arbeitszeit_daten')
check('vor dem ersten Import: leer, kein Importrecht', st == 200 and r['stand']['bis'] is None and r['personen'] == [] and r['rechte'] == {'importieren': False}
      and r['grenzen'] == {'lang': 720} and set(r['fehlerarten']) == {'kommen', 'gehen', 'null', 'lang', 'ohne', 'saldo'}, r)
check('Import: nur mit controlling.arbeitszeit_importieren (403), Importart nur für Berechtigte', zb(AR)[0] == 403 and zb(L)[0] == 403
      and 'zeitbericht' not in [a['id'] for a in AR.call('import_arten')[1].get('arten', [])] and 'zeitbericht' in [a['id'] for a in ID.call('import_arten')[1]['arten']])
st, r = zb(ID, {'blaetter': [{'name': 'x', 'grid': [['Artikel', 'Preis'], ['A', 1]]}]})
check('andere Datei: 422 mit Hinweis', st == 422 and 'kein Zeitbericht' in r.get('error', ''), (st, r))
check('leere Datei und zu viele Zeilen: 422', zb(ID, {'blaetter': []})[0] == 422 and zb(ID, {'blaetter': [{'name': 'x', 'grid': [KOPF] + [[]] * 60001}]})[0] == 422)
st, v = zb(ID)
hw = ' '.join(h['text'] for h in v.get('hinweise', []))
fz = [z for z in v.get('zeilen', []) if z['art'] == 'fehler']
check('Vorschau: 15 Tage neu (einer davon heute), 3 Zeilen nicht lesbar (doppelt, Datum, Uhrzeit)', st == 200 and v['zahlen'] == {'neu': 15, 'geaendert': 0, 'entfaellt': 0, 'unveraendert': 0, 'fehler': 3}
      and sorted(z['zeile'] for z in fz) == [18, 19, 20] and any('doppelt' in z['text'] for z in fz) and any('Datum' in z['text'] for z in fz) and any('Uhrzeit' in z['text'] for z in fz), (st, v))
check('Vorschau: Stempelfehler je Art, laufender Tag, ohne Mitarbeiternummer, Abwesenheitsgründe nicht gespeichert',
      '6 Tage mit Stempelfehlern' in hw and 'nichts wird geschätzt' in hw and '1 Tag ab heute gilt' in hw and '1 Mitarbeiter ohne Mitarbeiternummer' in hw and 'nicht gespeichert' in hw
      and v['hinweise'][0]['stufe'] == 'warn', hw)
check('Vorschau schreibt nichts', dokument('controlling-arbeitszeit') is None)
STAND0 = v['stand']

with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ').replace(' ', ' ')

    def neu(breite=1280, thema='light', ip='198.51.100.42'):
        ctx = br.new_context(viewport={'width': breite, 'height': 900 if breite > 500 else 844}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE',
                             timezone_id='Europe/Berlin', color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        return ctx, pg

    # Import in der Oberfläche (Importzentrale, Leser im Browser)
    ctx, pg = neu(ip='198.51.100.43')
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'ida'); pg.fill('#pw1', AZ_PW['ida']); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
    pg.click('#vt-importe'); pg.wait_for_selector('#view-importe .imp-art[data-art="zeitbericht"]')
    check('Importzentrale: Importart „Arbeitszeit (Zeitbericht)“ für den Importberechtigten', 'Zeitbericht' in pg.text_content('#view-importe .imp-art[data-art="zeitbericht"]'))
    pg.set_input_files('#view-importe input[data-imp-datei="zeitbericht"]', DATEI)
    pg.wait_for_selector('#imp-neu', timeout=20000)
    txt = text(pg, '#view-importe')
    check('Oberfläche: Vorschau aus der Excel-Datei (Leser liest das erste Blatt wie die Zeiterfassung)', 'Stempelfehlern' in txt and 'Anna Muster' in txt and 'doppelt' in txt, txt[:600])
    pg.click('#imp-ok'); pg.wait_for_selector('#imp-ergebnis')
    ctx.close()

    idx = dokument('controlling-arbeitszeit')
    jahr = dokument('controlling-arbeitszeit/2026') or {'tage': {}}
    check('übernommen: Index mit Mitarbeitern, Jahr, Import (Zeitraum bis heute)', idx and idx['rev'] == STAND0 + 1 and set(idx['personen']) == {P_ANNA, P_BERND, P_CARLA}
          and idx['importe'][0]['von'] == '2026-09-01' and idx['importe'][0]['bis'] == heute.isoformat() and idx['importe'][0]['neu'] == 15 and idx['importe'][0]['wer'] == 'Ida Import', idx)
    check('Abteilung = jüngste Angabe; ohne Nummer über den Namen', idx['personen'][P_BERND] == {'name': 'Bernd Beispiel', 'nr': '102', 'abt': 'Versand'}
          and idx['personen'][P_CARLA] == {'name': 'Carla Ohnenr', 'nr': '', 'abt': ''}, idx['personen'])
    tg = jahr['tage'] if heute.year == 2026 else {**jahr['tage'], **(dokument(f'controlling-arbeitszeit/{heute.year}') or {'tage': {}})['tage']}
    check('gespeicherter Tag: Minuten, Stempel mit Folgezeile, Fehlercodes, laufend', tg[P_ANNA + '|2026-09-04'] == [480, 480, 0, 0, 0, [['06:00', '10:00'], ['10:30', '14:30']], [], 0]
          and tg[P_ANNA + '|2026-09-03'][6] == ['gehen'] and tg[P_ANNA + '|2026-10-02'][6] == ['null'] and tg[P_BERND + '|2026-09-01'][6] == ['ohne']
          and tg[P_BERND + '|2026-09-02'][6] == ['lang'] and tg[P_BERND + '|2026-09-04'][6] == ['saldo'] and tg[P_CARLA + '|2026-09-02'][6] == ['kommen']
          and tg[P_ANNA + '|' + heute.isoformat()][6:] == [[], 1], {k[-10:]: t for k, t in tg.items() if k.startswith(P_ANNA)})
    check('Gründe von Abwesenheiten nicht gespeichert (nur Stunden)', 'Urlaub' not in json.dumps(jahr) and 'Urlaub' not in json.dumps(idx) and tg[P_ANNA + '|2026-10-01'][2] == 480)

    st, r = AR.call('controlling_arbeitszeit&von=2026-09&bis=2026-10')
    s, pp = r.get('summe', {}), {x['id']: x for x in r.get('personen', [])}
    check('Summe: bereinigt nur Tage ohne Stempelfehler, laut Zeiterfassung alle Tage', st == 200 and s['sollOk'] == 3120 and s['istOk'] == 2670 and s['abwOk'] == 480 and s['saldoOk'] == 30
          and s['saldo'] == -930 and s['saldoFehler'] == -960 and s['fehlerTage'] == 6 and s['ohne'] == 1 and s['tage'] == 14 and s['tageOk'] == 8 and s['laufend'] == 0, s)
    check('je Mitarbeiter (nach Name)', [x['name'] for x in r['personen']] == ['Anna Muster', 'Bernd Beispiel', 'Carla Ohnenr']
          and (pp[P_ANNA]['saldoOk'], pp[P_ANNA]['saldo'], pp[P_ANNA]['fehlerTage'], pp[P_ANNA]['arbeitstage']) == (60, -900, 2, 7)
          and (pp[P_BERND]['saldoOk'], pp[P_BERND]['saldoFehler'], pp[P_BERND]['fehlerTage']) == (-30, 0, 3) and pp[P_CARLA]['abt'] == '', r.get('personen'))
    check('je Monat', [(m['m'], m['saldoOk'], m['fehlerTage']) for m in r['monate']] == [('2026-09', 30, 5), ('2026-10', 0, 1)], r.get('monate'))
    check('je Abteilung, „ohne Abteilung“ zuletzt', [(a['id'], a['personen']) for a in r['abteilungen']] == [('Versand', 1), ('Zerlegung', 1), ('_', 1)]
          and r['abteilungen'][2]['name'] == 'ohne Abteilung', r.get('abteilungen'))
    check('Stempelfehler-Liste: jüngste zuerst, mit Stempeln', [(f['d'][5:], f['p'], f['fehler']) for f in r['fehler']] == [
        ('10-02', P_ANNA, ['null']), ('09-04', P_BERND, ['saldo']), ('09-03', P_ANNA, ['gehen']), ('09-02', P_BERND, ['lang']), ('09-02', P_CARLA, ['kommen']), ('09-01', P_BERND, ['ohne'])]
          and r['fehlerGesamt'] == 6 and r['fehler'][2]['stempel'] == [['06:00', None]], r.get('fehler'))
    st, r = AR.call('controlling_arbeitszeit&von=2026-09&bis=2026-10&abt=Versand')
    check('Filter Abteilung', st == 200 and [x['name'] for x in r['personen']] == ['Bernd Beispiel'] and r['summe']['saldoOk'] == -30)
    st, r = AR.call('controlling_arbeitszeit&von=2026-09&bis=2026-10&abt=_')
    check('Filter „ohne Abteilung“', st == 200 and [x['name'] for x in r['personen']] == ['Carla Ohnenr'])
    st, r = AR.call('controlling_arbeitszeit_detail&p=' + P_ANNA + '&von=2026-09&bis=' + heute.strftime('%Y-%m'))
    check('Pop-up: alle Tage des Mitarbeiters (neueste zuerst), heute „laufend“ ohne Fehler, zählt nicht', st == 200 and r['person']['name'] == 'Anna Muster' and len(r['tage']) == 9
          and r['tage'][0]['d'] == heute.isoformat() and r['tage'][0]['laufend'] is True and r['tage'][0]['fehler'] == [] and r['summe']['laufend'] == 1 and r['summe']['saldoOk'] == 60, r.get('tage', [])[:1])
    check('ungültige Anfragen: 422', all(AR.call(q)[0] == 422 for q in ('controlling_arbeitszeit&von=2026-13', 'controlling_arbeitszeit&von=2026-10&bis=2026-09',
                                                                          'controlling_arbeitszeit&von=2023-01&bis=2026-01', 'controlling_arbeitszeit_detail&p=' + 'p' + '0' * 12,
                                                                          'controlling_arbeitszeit_detail&p=../x')))
    st, r = AR.call('controlling_arbeitszeit_daten')
    check('Grunddaten: Stand bis heute, Abteilungen, Mitarbeiter', st == 200 and r['stand']['bis'] == heute.isoformat() and r['abteilungen'] == ['Versand', 'Zerlegung']
          and len(r['personen']) == 3 and r['stand']['importe'][0]['wer'] == 'Ida Import', r)

    # Oberfläche Arbeitszeit
    ctx, pg = neu()
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'aron'); pg.fill('#pw1', AZ_PW['aron']); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
    pg.goto(B + '/module/controlling/#arbeitszeit'); pg.wait_for_selector('#ctl-az-kpis .ctl-kpi')
    pg.fill('#ctl-az-von', '2026-09'); pg.fill('#ctl-az-bis', '2026-10'); pg.dispatch_event('#ctl-az-bis', 'change')
    pg.wait_for_function("document.querySelector('#ctl-az-kpis') && document.querySelector('#ctl-az-kpis').textContent.includes('52:00')")
    kpi = text(pg, '#ctl-az-kpis')
    check('Kennzahlen: Soll, Ist, Saldo bereinigt und laut Zeiterfassung, Stempelfehler', '52:00' in kpi and '44:30' in kpi and '+0:30' in kpi and '−15:30' in kpi and '6 Tage' in kpi
          and 'ohne jeden Stempel' in kpi, kpi)
    check('Monatsverlauf: zwei Monate', pg.locator('#ctl-az-verlauf .ctl-az-mon').count() == 2 and 'Sep 2026' in text(pg, '#ctl-az-verlauf'))
    zl = pg.locator('#ctl-az-zeilen > li')
    check('Mitarbeiterliste: drei, „lückenhaft“ bei vielen Stempelfehlern (Bernd, Carla), nicht bei Anna', zl.count() == 3 and 'lückenhaft' not in zl.nth(0).inner_text()
          and 'lückenhaft' in zl.nth(1).inner_text() and 'lückenhaft' in zl.nth(2).inner_text() and 'ohne Nummer' in zl.nth(2).inner_text(), text(pg, '#ctl-az-zeilen'))
    pg.select_option('#ctl-az-sort', 'fehlerTage')
    check('Sortierung: meiste Stempelfehler zuerst', 'Bernd Beispiel' in zl.nth(0).inner_text())
    pg.fill('#ctl-az-suche', '102')
    pg.wait_for_function("document.querySelectorAll('#ctl-az-zeilen > li').length === 1")
    check('Suche nach Nummer', 'Bernd Beispiel' in text(pg, '#ctl-az-zeilen'))
    pg.fill('#ctl-az-suche', '')
    pg.wait_for_function("document.querySelectorAll('#ctl-az-zeilen > li').length === 3")
    with pg.expect_download() as dl:
        pg.click('#ctl-az-csv')
    inhalt = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV der Mitarbeiter (Stunden dezimal)', 'Saldo bereinigt Std.' in inhalt and 'Anna Muster' in inhalt and '"1,00"' in inhalt, inhalt[:300])
    pg.click('#ctl-az-zeilen [data-p="' + P_ANNA + '"]')
    pg.wait_for_selector('#ctl-az-dialog[open] #ctl-az-tage tbody tr')
    check('Pop-up: Tage mit Stempeln, Fehlertage markiert', pg.locator('#ctl-az-tage tbody tr').count() == 8 and pg.locator('#ctl-az-tage tbody tr.fehler').count() == 2
          and '06:00–10:00, 10:30–14:30' in text(pg, '#ctl-az-tage') and 'Gehen fehlt' in text(pg, '#ctl-az-tage'), text(pg, '#ctl-az-dialog')[:600])
    pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
    pg.screenshot(path=os.path.join(SH, 'controlling_arbeitszeit_detail_1280.png'))
    pg.click('#ctl-az-dialog [data-zu]')
    pg.click('#ctl-az-ansicht [data-ansicht="abteilungen"]')
    pg.wait_for_function("document.querySelector('#ctl-az-listenbox').textContent.includes('ohne Abteilung')")
    check('Ansicht Abteilungen', pg.locator('#ctl-az-listenbox .ctl-az-liste > li').count() == 3 and 'Versand' in text(pg, '#ctl-az-listenbox'))
    pg.click('#ctl-az-ansicht [data-ansicht="fehler"]')
    pg.wait_for_selector('#ctl-az-fehlerliste')
    check('Ansicht Stempelfehler: sechs Tage mit Fehlerart', pg.locator('#ctl-az-fehlerliste > li').count() == 6 and 'Kommen = Gehen' in text(pg, '#ctl-az-fehlerliste'))
    pg.select_option('#ctl-az-art', 'ohne')
    pg.wait_for_function("document.querySelectorAll('#ctl-az-fehlerliste > li').length === 1")
    check('Filter Fehlerart „ohne Stempel“', 'Bernd Beispiel' in text(pg, '#ctl-az-fehlerliste') and 'kein Stempel' in text(pg, '#ctl-az-fehlerliste'))
    with pg.expect_download() as dl:
        pg.click('#ctl-az-csv')
    inhalt = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV der Stempelfehler (gefiltert)', inhalt.count('\n') in (1, 2) and 'kein Stempel, keine Abwesenheit' in inhalt, inhalt)
    pg.select_option('#ctl-az-art', '')
    pg.select_option('#ctl-az-abt', 'Versand')
    pg.wait_for_function("document.querySelectorAll('#ctl-az-fehlerliste > li').length === 3")
    check('Filter Abteilung in der Oberfläche', 'Anna' not in text(pg, '#ctl-az-fehlerliste'))
    pg.select_option('#ctl-az-abt', '')
    pg.wait_for_function("document.querySelectorAll('#ctl-az-fehlerliste > li').length === 6")
    pg.click('#ctl-az-ansicht [data-ansicht="personen"]'); pg.wait_for_selector('#ctl-az-zeilen')
    pg.screenshot(path=os.path.join(SH, 'controlling_arbeitszeit_1280.png'), full_page=True)
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = neu(breite, thema, '198.51.100.44')
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'aron'); pg.fill('#pw1', AZ_PW['aron']); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/controlling/#arbeitszeit'); pg.wait_for_selector('#ctl-az-kpis .ctl-kpi')
        pg.fill('#ctl-az-von', '2026-09'); pg.fill('#ctl-az-bis', '2026-10'); pg.dispatch_event('#ctl-az-bis', 'change')
        pg.wait_for_function("document.querySelector('#ctl-az-kpis').textContent.includes('52:00')")
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        if breite == 390:
            pg.click('#ctl-az-zeilen [data-p="' + P_BERND + '"]'); pg.wait_for_selector('#ctl-az-dialog[open] #ctl-az-tage tbody tr')
            pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
            pg.screenshot(path=os.path.join(SH, f'controlling_arbeitszeit_detail_{breite}_{thema}.png'))
            pg.click('#ctl-az-dialog [data-zu]')
            pg.click('#ctl-az-ansicht [data-ansicht="fehler"]'); pg.wait_for_selector('#ctl-az-fehlerliste')
            check(f'{breite}px {thema}: Stempelfehler-Liste ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'controlling_arbeitszeit_{breite}_{thema}.png'), full_page=True)
        ctx.close()
    br.close()

# neuer Import ersetzt nur seinen Zeitraum; veralteter Stand 409
STAND1 = dokument('controlling-arbeitszeit')['rev']
D2 = {'blaetter': [{'name': 'Zeitbericht', 'grid': [KOPF, az_zeile('Anna', 'Muster', '01-09-2026', '06:00', '14:30', '08:00', '08:00', '00:00', '101', 'Zerlegung', pause='00:30'),
                                                    az_zeile('Anna', 'Muster', '02-09-2026', '06:00', '15:00', '08:00', '08:30', '00:30', '101', 'Zerlegung')]}]}
st, v = zb(ID, D2)
check('zweiter Import, Vorschau: Zeitraum 01.–02.09., ein Tag geändert, einer gleich, drei entfallen (mit Warnung)', st == 200
      and v['zahlen'] == {'neu': 0, 'geaendert': 1, 'entfaellt': 3, 'unveraendert': 1, 'fehler': 0} and '3 gespeicherte Tage' in ' '.join(h['text'] for h in v['hinweise']), v)
check('veralteter Stand: 409, nichts geschrieben', zb(ID, D2, STAND0)[0] == 409 and dokument('controlling-arbeitszeit')['rev'] == STAND1)
st, r = zb(ID, D2, v['stand'])
check('zweiter Import übernommen', st == 200 and r['zahlen']['entfaellt'] == 3 and r['stand'] == STAND1 + 1, (st, r))
st, r = AR.call('controlling_arbeitszeit&von=2026-09&bis=2026-10')
check('nur der Zeitraum der Datei ersetzt: Tage davor/danach bleiben', st == 200 and r['fehlerGesamt'] == 3
      and {(f['d'], f['p']) for f in r['fehler']} == {('2026-10-02', P_ANNA), ('2026-09-04', P_BERND), ('2026-09-03', P_ANNA)}
      and {x['id']: x['saldoOk'] for x in r['personen']}[P_ANNA] == 30, r.get('fehler'))

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
