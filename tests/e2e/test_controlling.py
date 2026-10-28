"""Controlling (Modul controlling, Oberfläche controlling.intern unter /module/controlling/) – erster Bereich Umsatzstatistik.

Geprüft: Register (in Entwicklung, ohne Freigabe, Modulzugang standardmäßig niemand), Freigabe nur als Test mit Testern;
Rechte serverseitig (GR-103): ohne Anmeldung, ohne Modulzugang, Modulzugang ohne Bereichsrecht (keine Bereiche, Umsatz 403),
nur ansehen, bearbeiten; ohne CSRF, GET auf schreibende Aktion; Eingaben (Jahr, Monat 01–12, Zahlen, negative Kg/Umsatz,
negativer DB erlaubt, unbekannte/doppelte Vertreter, leere Liste); Speichern (Monat als „MM“, leere Vertreter nicht
gespeichert, nur mitgeschickte Vertreter ändern sich, Sortierung der Monate, veralteter Stand 409); ausgeschiedene Vertreter
(bleiben mit Werten und Namen aus dem Schnappschuss, nicht mehr erfassbar); Protokoll ohne Beträge; Oberfläche (Bereiche,
Kennzahlen, Anteile, Liniendiagramm, Datenpflege im Dialog, nur ansehen, kein Bereich; 1280 und 390 px, hell und dunkel,
keine JavaScript-Fehler). Nur synthetische Testdaten.
"""
import datetime as dt
import json
import os

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw

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
          ('bea', 'Bea Bearbeiten', 'editor', 'Pflege-Konto-34', {'grant': ['controlling.umsatz_bearbeiten']}),
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
check('Bearbeiten-Recht: Bereich mit Bearbeiten', st == 200 and r['bereiche'] == [{'id': 'umsatz', 'name': 'Umsatzstatistik', 'bearbeiten': True}], r)
check('Administrator: alle Bereiche', [b['id'] for b in A.call('controlling_start')[1]['bereiche']] == ['umsatz'])

# ── Vertreter (Stammdaten der Verwaltung) ──
rev_v = A.call('vertreter')[1].get('rev', 0)
st, r = A.call('vertreter_save', {'rev': rev_v, 'groups': [{'nr': 'V1', 'name': 'Vera Vertrieb', 'kurz': 'VV'}, {'nr': 'V2', 'name': 'Viktor Verkauf'},
                                                           {'nr': '7', 'name': 'Sieben Test', 'kurz': 'ST'}, {'nr': 'V10', 'name': 'Zehn Test'}]})
check('Vertreter in den Stammdaten angelegt', st == 200, r)
rev_v = r.get('rev', rev_v + 1)
st, d = L.call('controlling_umsatz')
check('Umsatzstatistik leer, Vertreter aus den Stammdaten (natürliche Sortierung), Monate 01–12', st == 200 and d['rev'] == 0 and d['jahre'] == {}
      and [v['nr'] for v in d['vertreter']] == ['7', 'V1', 'V2', 'V10'] and all(v['aktiv'] for v in d['vertreter'])
      and [m['nr'] for m in d['monate']] == [f'{i:02d}' for i in range(1, 13)] and d['monate'][2]['name'] == 'März' and d['rechte'] == {'bearbeiten': False}, d)
check('Anzeige mit Kürzel, sonst Name', {v['nr']: v['anzeige'] for v in d['vertreter']}['V1'] == 'V1 – VV' and {v['nr']: v['anzeige'] for v in d['vertreter']}['V2'] == 'V2 – Viktor Verkauf')

# ── Eingaben ──
JAN = [{'vertreterNr': 'V1', 'kg': 1250.5, 'umsatz': 25000, 'db': 3500}, {'vertreterNr': 'V2', 'kg': '400', 'umsatz': '10000.5', 'db': -200},
       {'vertreterNr': '7', 'kg': None, 'umsatz': '', 'db': None}]
save = lambda c, b, **kw: c.call('controlling_umsatz_monat_save', {'rev': 0, 'jahr': 2026, 'monat': '01', 'werte': JAN, **b}, **kw)   # noqa: E731
check('nur ansehen: Speichern 403', save(L, {})[0] == 403)
csrf = Bb.csrf; Bb.csrf = ''
check('ohne CSRF: 403', save(Bb, {})[0] == 403)
Bb.csrf = csrf
check('schreibende Aktion per GET: 405', Bb.call('controlling_umsatz_monat_save')[0] == 405)
for name, b in (('Jahr 1999', {'jahr': 1999}), ('Jahr als Text', {'jahr': 'zwanzig'}), ('Monat 13', {'monat': '13'}), ('Monat „Januar“', {'monat': 'Januar'}),
                ('negative Kg', {'werte': [{'vertreterNr': 'V1', 'kg': -1}]}), ('negativer Umsatz', {'werte': [{'vertreterNr': 'V1', 'umsatz': -5}]}),
                ('Text statt Zahl', {'werte': [{'vertreterNr': 'V1', 'umsatz': 'viel'}]}), ('unbekannter Vertreter', {'werte': [{'vertreterNr': 'V99', 'kg': 1}]}),
                ('doppelter Vertreter', {'werte': [{'vertreterNr': 'V1', 'kg': 1}, {'vertreterNr': 'V1', 'kg': 2}]}), ('leere Werteliste', {'werte': []}),
                ('zu große Zahl', {'werte': [{'vertreterNr': 'V1', 'umsatz': 1e13}]})):
    st, r = save(Bb, b)
    check(f'Eingabe: {name} → 422', st == 422 and r.get('error'), (st, r))
check('nach abgewiesenen Eingaben nichts gespeichert', Bb.call('controlling_umsatz')[1]['rev'] == 0)

# ── Speichern ──
st, d = save(Bb, {})
jan = d['jahre'].get('2026', {}).get('01', {}) if st == 200 else {}
check('Januar gespeichert: Werte je Vertreter, Zahlen gerundet, negativer DB erlaubt, leerer Vertreter nicht gespeichert', st == 200 and d['rev'] == 1
      and jan.get('V1') == {'kg': 1250.5, 'umsatz': 25000, 'db': 3500} and jan.get('V2') == {'kg': 400, 'umsatz': 10000.5, 'db': -200} and '7' not in jan, d)
check('letzte Änderung mit Name', d.get('geaendert', {}).get('vonName') == 'Bea Bearbeiten')
check('veralteter Stand: 409', save(Bb, {'monat': '02'})[0] == 409)
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': 1, 'jahr': 2026, 'monat': 2, 'werte': [{'vertreterNr': 'V1', 'umsatz': 1000}]})
check('Monat als Zahl 2 → „02“', st == 200 and d['jahre']['2026'].get('02') == {'V1': {'kg': None, 'umsatz': 1000, 'db': None}}, d)
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': 2, 'jahr': 2026, 'monat': '01', 'werte': [{'vertreterNr': 'V2', 'umsatz': 12000, 'db': 600}]})
check('nur mitgeschickte Vertreter ändern sich (V1 im Januar bleibt)', st == 200 and d['jahre']['2026']['01']['V1']['umsatz'] == 25000
      and d['jahre']['2026']['01']['V2'] == {'kg': None, 'umsatz': 12000, 'db': 600}, d)
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': 3, 'jahr': 2026, 'monat': '10', 'werte': [{'vertreterNr': 'V10', 'kg': 5, 'umsatz': 99, 'db': 9}]})
check('Monate sortiert (01, 02, 10)', st == 200 and list(d['jahre']['2026']) == ['01', '02', '10'], list(d['jahre'].get('2026', {})))
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': 4, 'jahr': 2026, 'monat': '10', 'werte': [{'vertreterNr': 'V10', 'kg': None, 'umsatz': None, 'db': None}]})
check('alle Werte eines Monats geleert → Monat entfällt', st == 200 and '10' not in d['jahre']['2026'], d['jahre'])
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': 5, 'jahr': 2025, 'monat': '12', 'werte': [{'vertreterNr': 'V1', 'umsatz': 20000, 'db': 2000}]})
check('Vorjahr gespeichert', st == 200 and d['jahre']['2025']['12']['V1']['umsatz'] == 20000)

# ── Ausgeschiedener Vertreter (nicht mehr in den Stammdaten) ──
st, r = A.call('vertreter_save', {'rev': rev_v, 'groups': [{'nr': 'V1', 'name': 'Vera Vertrieb', 'kurz': 'VV'}, {'nr': '7', 'name': 'Sieben Test', 'kurz': 'ST'},
                                                           {'nr': 'V10', 'name': 'Zehn Test'}]})
check('V2 aus den Stammdaten entfernt', st == 200, r)
st, d = L.call('controlling_umsatz')
v2 = next((v for v in d['vertreter'] if v['nr'] == 'V2'), None)
check('ausgeschiedener Vertreter bleibt mit Werten und Namen aus dem Schnappschuss (am Ende der Liste)', v2 is not None and v2['aktiv'] is False
      and v2['anzeige'] == 'V2 – Viktor Verkauf (ausgeschieden)' and d['vertreter'][-1]['nr'] == 'V2' and d['jahre']['2026']['01']['V2']['umsatz'] == 12000, d['vertreter'])
check('ausgeschiedenen Vertreter erfassen: 422', Bb.call('controlling_umsatz_monat_save', {'rev': d['rev'], 'jahr': 2026, 'monat': '03', 'werte': [{'vertreterNr': 'V2', 'kg': 1}]})[0] == 422)
st, d = Bb.call('controlling_umsatz_monat_save', {'rev': d['rev'], 'jahr': 2026, 'monat': '01', 'werte': [{'vertreterNr': 'V1', 'kg': 1250.5, 'umsatz': 25000, 'db': 3500}]})
check('Januar neu gespeichert: Werte des ausgeschiedenen Vertreters bleiben', st == 200 and d['jahre']['2026']['01'].get('V2', {}).get('umsatz') == 12000, d['jahre'])

# ── Protokoll und Datenverantwortung ──
log = dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []
txt = json.dumps([e for e in log if e.get('a') == 'controlling'], ensure_ascii=False)
check('Protokoll: Monat und Jahr, keine Beträge', 'Umsatzstatistik: Monatswerte Januar 2026 gespeichert' in txt and '25000' not in txt and '12000' not in txt and '1250' not in txt, txt[:300])
doc = dokument('controlling-umsatz') or {}
check('eigenes Dokument mit Namens-Schnappschuss (GR-106)', doc.get('vertreter', {}).get('V2', {}).get('name') == 'Viktor Verkauf' and doc.get('rev') == d['rev'], doc.get('vertreter'))

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
    pg.wait_for_selector('#ctl-u-kpis .ctl-kpi')
    check('Bereich Umsatzstatistik aktiv, Adresse #umsatz', pg.get_attribute('#ctl-bereiche [data-bereich="umsatz"]', 'aria-selected') == 'true' and pg.url.endswith('#umsatz'))
    check('Jahr 2026 vorausgewählt (jüngstes mit Werten)', pg.input_value('#ctl-u-jahr') == '2026')
    kpi = text(pg, '#ctl-u-kpis')
    check('Kennzahlen: Umsatz und DB des Jahres', '38.000,00 €' in kpi and '4.100,00 €' in kpi, kpi)
    zeilen = text(pg, '#ctl-u-vertreterzeilen')
    check('Anteile berechnet (V1 26.000 von 38.000 € = 68,42 %)', '68,42 %' in zeilen and 'V2 – Viktor Verkauf (ausgeschieden)' in zeilen, zeilen[:500])
    pg.select_option('#ctl-u-diagrammart', 'linie'); pg.wait_for_selector('#ctl-u-diagramm polyline')
    check('Liniendiagramm', pg.locator('#ctl-u-diagramm svg[role="img"]').count() == 1)
    pg.click('#ctl-u-vertreterfilter summary'); pg.uncheck('#ctl-u-vertreteroptionen [data-vertreter="V2"]')
    pg.wait_for_function("!document.querySelector('#ctl-u-vertreterzeilen').textContent.includes('ausgeschieden')")
    check('Vertreterfilter wirkt auf Kennzahlen', '26.000,00 €' in text(pg, '#ctl-u-kpis'), text(pg, '#ctl-u-kpis'))
    pg.screenshot(path=os.path.join(SH, 'controlling_umsatz_1280.png'), full_page=True)
    pg.click('#ctl-u-tabs [data-tab="datenpflege"]')
    check('Reiter Datenpflege, Adresse #umsatz/datenpflege', pg.is_visible('#ctl-u-datenpflege') and pg.url.endswith('#umsatz/datenpflege'))
    pg.fill('#ctl-u-pflege-jahr', '2026'); pg.select_option('#ctl-u-pflege-monat', '03')
    pg.click('#ctl-u-bearbeiten'); pg.wait_for_selector('#ctl-u-dialog[open]')
    check('Dialog: nur aktuelle Vertreter', pg.locator('#ctl-u-editorzeilen tr').count() == 3 and 'Viktor' not in pg.inner_text('#ctl-u-editorzeilen'))
    pg.fill('#ctl-u-editorzeilen [data-rep="V1"][data-feld="umsatz"]', 'abc'); pg.click('#ctl-u-form [type="submit"]')
    pg.wait_for_selector('#ctl-u-meldung:not(:empty)')
    check('Dialog: Text statt Zahl wird vor dem Senden gemeldet', 'Zahlen' in pg.inner_text('#ctl-u-meldung'))
    pg.fill('#ctl-u-editorzeilen [data-rep="V1"][data-feld="umsatz"]', '1.234,50'); pg.fill('#ctl-u-editorzeilen [data-rep="V1"][data-feld="db"]', '234,5')
    pg.wait_for_function("document.querySelector('#ctl-u-editorzeilen [data-spanne=\"V1\"]').textContent.includes('19')")
    check('Dialog: Spanne rechnet mit (234,5 ÷ 1.234,5 = 19,00 %)', '19,00 %' in text(pg, '#ctl-u-editorzeilen [data-spanne="V1"]'))
    pg.screenshot(path=os.path.join(SH, 'controlling_datenpflege_1280.png'))
    pg.click('#ctl-u-form [type="submit"]'); pg.wait_for_selector('#ctl-u-dialog[open]', state='hidden')
    check('Oberfläche: März gespeichert (deutsche Schreibweise)', Bb.call('controlling_umsatz')[1]['jahre']['2026']['03']['V1'] == {'kg': None, 'umsatz': 1234.5, 'db': 234.5})
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('lea', 'Leserin-Konto-12', '198.51.100.10', breite, thema)
        pg.wait_for_selector('#ctl-u-kpis .ctl-kpi')
        check(f'{breite}px {thema}: nur ansehen (kein Reiter Datenpflege)', pg.is_hidden('#ctl-u-tabs [data-tab="datenpflege"]'))
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
