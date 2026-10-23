"""HR · Urlaubsverwaltung (Modul hr, Oberfläche hr.intern unter /module/hr/).

Geprüft: Freigabe (ohne Testfreigabe 404, nur eingetragene Tester), Rechte (hr.antrag für alle, hr.verwalten nur
Personalstelle, serverseitig – GR-103), Antrag → Genehmigung/Ablehnung/Zurückziehen, Grenzfälle (Vergangenheit,
Wochenende, Überschneidung, Urlaubssperre), Urlaubskonto mit Übertrag bis 31.03. und Verfall, 4-Tage-Woche,
Datenschutz im Kalender (Kollegen sehen nur „abwesend“, nie Art, Notiz oder offene Anträge; Protokoll ohne Art),
Excel-Export für den Steuerberater (Aufbau der bisherigen Planung, nur genehmigte Einträge), Übernahme der bisherigen
Excel-Planung (synthetische Datei tests/fixtures/hr/Urlaub_Muster_2025.xlsx) und die Oberfläche (Desktop, 390 px).
"""
import datetime as dt
import io
import json
import os
import sys
import zipfile

import openpyxl
from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, FIX, storage_raw

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def montag(jahr, monat, woche=1):
    """Montag der n-ten vollen Woche eines Monats (ohne Feiertage im Februar/August)."""
    d = dt.date(jahr, monat, 1)
    while d.weekday() != 0: d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=woche - 1)


def iso(d): return d.isoformat()


Y = dt.date.today().year + 1           # Anträge nur für die Zukunft: alles im nächsten Jahr
FEB = montag(Y, 2)                      # Montag der ersten vollen Februarwoche (vor dem 31.03.: verbraucht Übertrag)
AUG = montag(Y, 8, 2)

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('erika', 'Erika Editor', 'editor', 'Editor-Zugang-77', {}), ('lena', 'Lena Leser', 'viewer', 'Leser-Zugang-77', {}),
                          ('paul', 'Paul Personal', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.verwalten']}), ('otto', 'Otto Ohne', 'editor', 'Ohne-Zugang-77', {})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
L = Client('198.51.100.4'); L.call('login', {'username': 'lena', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.5'); P.call('login', {'username': 'paul', 'password': 'Personal-Zugang-77'})
O = Client('198.51.100.6'); O.call('login', {'username': 'otto', 'password': 'Ohne-Zugang-77'})
N = Client('198.51.100.7')

# ── Freigabe ──
check('vor der Testfreigabe: 404 auch für Administratoren', A.call('hr_start')[0] == 404 and P.call('hr_verwaltung')[0] == 404)
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['hr']
check('Register: HR in Entwicklung, Adresse /module/hr/', mod['oberflaechen'][0]['entwicklung'] == 'in_entwicklung' and mod['oberflaechen'][0]['adresse'].endswith('/module/hr/'), mod)
st, r = A.call('modul_freigabe_save', {'bereich': 'hr.intern', 'freigabe': 'test', 'grund': 'Abnahme Personalstelle'})
check('Testfreigabe gesetzt', st == 200, r)
st, r = A.call('modul_tester_save', {'bereich': 'hr.intern', 'tester': [ids['admin'], ids['erika'], ids['lena'], ids['paul']], 'grund': 'Abnahme'})
check('Tester eingetragen', st == 200, r)
check('nicht eingetragener Mitarbeiter: 404', O.call('hr_start')[0] == 404)
check('ohne Anmeldung: kein Zugang', N.call('hr_start')[0] in (401, 404))

# ── Rechte ──
check('Mitarbeiter ohne Personalrecht: hr_verwaltung 403', L.call('hr_verwaltung')[0] == 403 and E.call('hr_verwaltung')[0] == 403)
for a, b in (('hr_entscheiden', {'id': 'x', 'entscheidung': 'genehmigt'}), ('hr_eintrag_save', {'person': 'x', 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB)}),
             ('hr_person_save', {'person': {'vorname': 'X'}, 'rev': 0}), ('hr_export', {'jahr': Y, 'monate': [2]}), ('hr_einstellungen_save', {'sperren': []}),
             ('hr_import_pruefen', {'daten': {'blaetter': []}})):
    check(f'{a}: ohne Personalrecht 403', L.call(a, b)[0] == 403)
st, r = E.call('hr_start', None)
check('Mitarbeiter ohne Zuordnung: Start ok, ohne Konto', st == 200 and r['ich'] is None and r['verwalten'] is False, r)
check('Antrag ohne Zuordnung: 409 mit Hinweis', (lambda s: s[0] == 409 and 'Personalstelle' in s[1]['error'])(E.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG)})))

# ── Mitarbeiter anlegen (Personalstelle) ──
rev = P.call('hr_verwaltung')[1]['rev']


def person(daten):
    global rev
    st, r = P.call('hr_person_save', {'person': daten, 'rev': rev})
    assert st == 200, r
    rev += 1
    return r['person']['id']


PE = person({'vorname': 'Erika', 'nachname': 'Editor', 'abteilung': 'Verwaltung', 'pos': 1, 'nutzer': ids['erika'], 'jahre': {str(Y): {'anspruch': 30, 'uebertrag': 5}}})
PL = person({'vorname': 'Lena', 'nachname': 'Leser', 'abteilung': 'Verwaltung', 'pos': 2, 'nutzer': ids['lena'], 'jahre': {'2025': {'anspruch': 30, 'uebertrag': 4}}})
PA = person({'vorname': 'Andre', 'nachname': 'Vierzig', 'abteilung': 'Lager', 'pos': 3, 'arbeitstage': [1, 2, 3, 4], 'jahre': {str(Y): {'anspruch': 24}}})
st, r = P.call('hr_person_save', {'person': {'vorname': 'Doppelt', 'nutzer': ids['erika']}, 'rev': rev})
check('Mitarbeiterkonto nur einmal zuordenbar', st == 409, r)
st, r = P.call('hr_person_save', {'person': {'vorname': 'Alt'}, 'rev': rev - 1})
check('veralteter Stand der Mitarbeiterliste: 409', st == 409, r)
check('ungültiger Anspruch (Viertel-Tage): 422', P.call('hr_person_save', {'person': {'vorname': 'X', 'jahre': {str(Y): {'anspruch': 10.25}}}, 'rev': rev})[0] == 422)
check('ohne Arbeitstage: 422', P.call('hr_person_save', {'person': {'vorname': 'X', 'arbeitstage': []}, 'rev': rev})[0] == 422)

# ── Konto und Antrag ──
st, r = E.call('hr_start&jahr=' + str(Y))
k = r['konto']
check('Konto: Anspruch 30 + Übertrag 5 = 35 Resturlaub', st == 200 and k['anspruch'] == 30 and k['uebertrag'] == 5 and k['rest'] == 35, k)
st, r = E.call('hr_antrag', {'von': iso(FEB), 'bis': iso(FEB + dt.timedelta(days=2)), 'notiz': 'Skiurlaub', 'vertretung': PL})
check('Antrag gestellt (3 Arbeitstage, beantragt)', st == 200 and r['eintrag']['status'] == 'beantragt' and r['eintrag']['tage'] == 3 and r['konto']['beantragt'] == 3, r)
ANTRAG1 = r['eintrag']['id']
check('Überschneidung: 409', E.call('hr_antrag', {'von': iso(FEB + dt.timedelta(days=2)), 'bis': iso(FEB + dt.timedelta(days=4))})[0] == 409)
gestern = dt.date.today() - dt.timedelta(days=1)
check('Vergangenheit: 422', E.call('hr_antrag', {'von': iso(gestern), 'bis': iso(gestern)})[0] == 422)
samstag = FEB + dt.timedelta(days=5)
check('nur Wochenende: 422 mit Hinweis', (lambda s: s[0] == 422 and 'Arbeitstage' in s[1]['error'])(E.call('hr_antrag', {'von': iso(samstag), 'bis': iso(samstag + dt.timedelta(days=1))})))
check('Ende vor Beginn: 422', E.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG - dt.timedelta(days=1))})[0] == 422)
check('ungültige Vertretung: 422', E.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG), 'vertretung': PE})[0] == 422)

# Urlaubssperre
st, r = P.call('hr_einstellungen_save', {'sperren': [{'von': f'{Y}-12-14', 'bis': f'{Y}-12-31', 'text': 'Weihnachtsgeschäft'}], 'ferien': [{'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=11)), 'text': 'Sommerferien'}]})
check('Urlaubssperre und Ferien gespeichert', st == 200 and len(r['sperren']) == 1, r)
st, r = E.call('hr_antrag', {'von': f'{Y}-12-15', 'bis': f'{Y}-12-16'})
check('Antrag in der Urlaubssperre: 422 mit Bezeichnung', st == 422 and 'Weihnachtsgeschäft' in r['error'], r)
check('Sperre: Ende vor Beginn abgelehnt', P.call('hr_einstellungen_save', {'sperren': [{'von': f'{Y}-12-14', 'bis': f'{Y}-12-01'}]})[0] == 422)

# Krank für Lena (Personalstelle) – Gesundheitsdatum
st, r = P.call('hr_eintrag_save', {'person': PL, 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB + dt.timedelta(days=1)), 'notiz': 'Arztbesuch-Notiz'})
check('Krank eingetragen (genehmigt)', st == 200 and r['eintrag']['status'] == 'genehmigt' and r['eintrag']['tage'] == 2, r)
KRANK = r['eintrag']['id']
check('Überschneidung bei der Personalstelle: 409', P.call('hr_eintrag_save', {'person': PL, 'art': 'U', 'von': iso(FEB + dt.timedelta(days=1)), 'bis': iso(FEB + dt.timedelta(days=1))})[0] == 409)
check('unbekannte Art: 422', P.call('hr_eintrag_save', {'person': PL, 'art': 'Z', 'von': iso(AUG), 'bis': iso(AUG)})[0] == 422)

# ── Datenschutz im Kalender ──
st, r, raw = E.call(f'hr_monat&jahr={Y}&monat=2', raw=True)
zeilen = {p['id']: p['tage'] for p in r['personen']}
tag = str(FEB.day)
check('Kollege sieht bei Lena nur „abwesend“', st == 200 and zeilen[PL].get(tag) == 'A' and r['voll'] is False, zeilen[PL])
check('… nie Art oder Notiz', '"K"' not in raw and 'Arzt' not in raw and 'Krank' not in raw, raw[:300])
check('eigene Zeile: beantragt mit „U?“', zeilen[PE].get(tag) == 'U?', zeilen[PE])
st, r, raw = L.call(f'hr_monat&jahr={Y}&monat=2', raw=True)
zl = {p['id']: p['tage'] for p in r['personen']}
check('offener Antrag eines Kollegen ist unsichtbar', tag not in zl[PE] and 'Skiurlaub' not in raw, zl[PE])
check('eigene Krankheit sieht Lena selbst', zl[PL].get(tag) == 'K', zl[PL])
st, r = P.call(f'hr_monat&jahr={Y}&monat=2')
zp = {p['id']: p['tage'] for p in r['personen']}
check('Personalstelle sieht Art und offene Anträge', r['voll'] is True and zp[PL].get(tag) == 'K' and zp[PE].get(tag) == 'U?', (zp[PL], zp[PE]))

# ── Anträge entscheiden ──
st, r = P.call('hr_verwaltung&jahr=' + str(Y))
offen = {a['id']: a for a in r['offen']}
a = offen.get(ANTRAG1, {})
check('offener Antrag mit Konto, Vertretung und gleichzeitig Abwesenden', a.get('tage') == 3 and a.get('vertretungName') == 'Lena Leser'
      and any('Lena Leser' in x for x in a.get('kollegen', [])) and a.get('notiz') == 'Skiurlaub', a)
check('Ablehnen ohne Grund: 422', P.call('hr_entscheiden', {'id': ANTRAG1, 'entscheidung': 'abgelehnt'})[0] == 422)
check('Genehmigen', P.call('hr_entscheiden', {'id': ANTRAG1, 'entscheidung': 'genehmigt'})[0] == 200)
check('zweimal entscheiden: 409', P.call('hr_entscheiden', {'id': ANTRAG1, 'entscheidung': 'abgelehnt', 'grund': 'x'})[0] == 409)
k = E.call('hr_start&jahr=' + str(Y))[1]['konto']
check('Konto nach Genehmigung: geplant 3, Rest 32', k['geplant'] == 3 and k['rest'] == 32 and k['beantragt'] == 0, k)
check('Übertrag: 2 Tage verfallen nach dem 31.03., falls nicht genommen', k['verfaellt'] == 2 and k['frist'] == f'{Y}-03-31', k)

# Ablehnung mit Grund
st, r = E.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=4))})
A2 = r['eintrag']['id']
check('Ablehnen mit Grund', P.call('hr_entscheiden', {'id': A2, 'entscheidung': 'abgelehnt', 'grund': 'Inventur'})[0] == 200)
e = {x['id']: x for x in E.call('hr_start&jahr=' + str(Y))[1]['eintraege']}[A2]
check('Mitarbeiter sieht Ablehnung mit Grund', e['status'] == 'abgelehnt' and e['entscheidung']['grund'] == 'Inventur', e)

# Zurückziehen
st, r = E.call('hr_antrag', {'von': iso(AUG + dt.timedelta(days=7)), 'bis': iso(AUG + dt.timedelta(days=8))})
A3 = r['eintrag']['id']
check('fremden Antrag zurückziehen: 404', L.call('hr_antrag_zurueckziehen', {'id': A3})[0] == 404)
check('eigenen Antrag zurückziehen', E.call('hr_antrag_zurueckziehen', {'id': A3})[0] == 200)
check('zweimal zurückziehen: 409', E.call('hr_antrag_zurueckziehen', {'id': A3})[0] == 409)
check('genehmigten künftigen Urlaub zurückziehen', E.call('hr_antrag_zurueckziehen', {'id': ANTRAG1})[0] == 200)
k = E.call('hr_start&jahr=' + str(Y))[1]['konto']
check('… Konto wieder 35', k['rest'] == 35 and k['geplant'] == 0, k)
st, r = E.call('hr_antrag', {'von': iso(FEB), 'bis': iso(FEB + dt.timedelta(days=2))})
P.call('hr_entscheiden', {'id': r['eintrag']['id'], 'entscheidung': 'genehmigt'})
OFFEN = E.call('hr_antrag', {'von': iso(montag(Y, 2, 3)), 'bis': iso(montag(Y, 2, 3) + dt.timedelta(days=1))})[1]['eintrag']['id']

# 4-Tage-Woche
st, r = P.call('hr_eintrag_save', {'person': PA, 'art': 'U', 'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=4))})
check('4-Tage-Woche: Mo–Fr zählt 4 Urlaubstage', st == 200 and r['eintrag']['tage'] == 4, r)
zp = {p['id']: p['tage'] for p in P.call(f'hr_monat&jahr={Y}&monat=8')[1]['personen']}
fr = str((AUG + dt.timedelta(days=4)).day)
check('… Freitag als freier Tag „x“', zp[PA].get(fr) == 'x' and zp[PA].get(str(AUG.day)) == 'U', zp[PA])
zl = {p['id']: p['tage'] for p in L.call(f'hr_monat&jahr={Y}&monat=8')[1]['personen']}
check('… für Kollegen nur „abwesend“', zl[PA].get(fr) == 'A' and zl[PA].get(str(AUG.day)) == 'A', zl[PA])
check('Eintrag nur an freiem Tag (U): 422', P.call('hr_eintrag_save', {'person': PA, 'art': 'U', 'von': iso(AUG + dt.timedelta(days=11)), 'bis': iso(AUG + dt.timedelta(days=11))})[0] == 422)

# Übertrag aus einem vergangenen Jahr: verfallen und automatisch übertragen
for von, bis in (('2025-02-03', '2025-02-04'), ('2025-07-07', '2025-07-11')):
    assert P.call('hr_eintrag_save', {'person': PL, 'art': 'U', 'von': von, 'bis': bis})[0] == 200
pv = {p['id']: p for p in P.call('hr_verwaltung&jahr=2025')[1]['personen']}
k = pv[PL]['konto']
check('2025: 4 Tage Übertrag, 2 bis 31.03. genommen → 2 verfallen; Rest 25', k['uebertrag'] == 4 and k['verfallen'] == 2 and k['genommen'] == 7 and k['rest'] == 25, k)
pv = {p['id']: p for p in P.call('hr_verwaltung&jahr=2026')[1]['personen']}
k = pv[PL]['konto']
check('2026: Übertrag automatisch 25, Anspruch fortgeschrieben 30', k['uebertrag'] == 25 and k['anspruch'] == 30 and not k['uebertrag_manuell'], k)

# Stornieren
check('Krank stornieren', P.call('hr_eintrag_save', {'id': KRANK, 'stornieren': True})[0] == 200)
check('zweimal stornieren: 409', P.call('hr_eintrag_save', {'id': KRANK, 'stornieren': True})[0] == 409)
assert P.call('hr_eintrag_save', {'person': PL, 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB + dt.timedelta(days=1))})[0] == 200

# Protokoll ohne Art der Abwesenheit
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll nennt HR-Vorgänge, aber nie „Krank“', 'HR: Abwesenheit Lena Leser' in log and 'Krank' not in log and 'Arzt' not in log, log[:200])
raw = storage_raw('hr-abwesenheiten') or ''
check('Einträge bleiben erhalten (Status statt Löschen)', '"storniert"' in raw and '"zurueckgezogen"' in raw and '"abgelehnt"' in raw)

# ── Excel-Export ──
st, r, body = P.call('hr_export', {'jahr': Y, 'monate': [2]}, raw=True)
check('Export: 200, xlsx', st == 200 and body.startswith('PK'), (st, body[:80]))
import urllib.request
req = urllib.request.Request(B + '/api/?action=hr_export', data=json.dumps({'jahr': Y, 'monate': [2, 8]}).encode(),
                             headers={'Content-Type': 'application/json', 'X-CSRF-Token': P.csrf, 'X-Forwarded-For': P.ip})
antwort = P.http.open(req)
daten = antwort.read()
check('Dateiname und Typ', 'Urlaub_' in antwort.headers.get('Content-Disposition', '') and 'spreadsheetml' in antwort.headers.get('Content-Type', ''),
      antwort.headers.get('Content-Disposition'))
check('gültiges ZIP', zipfile.ZipFile(io.BytesIO(daten)).testzip() is None)
wb = openpyxl.load_workbook(io.BytesIO(daten))
check('je Monat ein Blatt', wb.sheetnames == [f'Februar {Y}', f'August {Y}'], wb.sheetnames)
ws = wb[f'Februar {Y}']
check('Aufbau wie die Planung: Legende, Titel K2, Pos. A8, Monat C8, Tag 1 in D8', ws['C2'].value == 'Urlaub' and ws['D2'].value == 'U' and ws['K2'].value == f'Februar {Y}'
      and ws['A8'].value == 'Pos.' and ws['C8'].value == 'Februar' and ws['D8'].value == 1 and ws.freeze_panes == 'D9',
      [ws['C2'].value, ws['K2'].value, ws['A8'].value, ws['D8'].value, ws.freeze_panes])
zeile = {ws.cell(z, 3).value: z for z in range(9, 20) if ws.cell(z, 3).value}
nt = 28 + (1 if Y % 4 == 0 and (Y % 100 or Y % 400 == 0) else 0)
spU = 3 + nt + 1
werte = lambda z: [ws.cell(z, c).value for c in range(4, 4 + nt)]
check('Erika: 3 × U (nur genehmigt, offener Antrag fehlt)', werte(zeile['Erika Editor']).count('U') == 3, werte(zeile['Erika Editor']))
check('Lena: 2 × K', werte(zeile['Lena Leser']).count('K') == 2)
check('Summenformeln wie in der Planung', str(ws.cell(zeile['Erika Editor'], spU).value).startswith('=COUNTIF(D') and ws.cell(7, spU).value == 'U', ws.cell(zeile['Erika Editor'], spU).value)
check('Abteilungen als senkrechte, verbundene Zellen', any(str(m).startswith('B') for m in ws.merged_cells.ranges) and ws.cell(zeile['Erika Editor'], 2).alignment.textRotation == 90)
ws8 = wb[f'August {Y}']
z8 = {ws8.cell(z, 3).value: z for z in range(9, 20) if ws8.cell(z, 3).value}
check('August: 4-Tage-Woche mit „x“', 'x' in [ws8.cell(z8['Andre Vierzig'], c).value for c in range(4, 35)])
check('Export ohne Monat: 422', P.call('hr_export', {'jahr': Y, 'monate': []})[0] == 422)

# ── Übernahme der Excel-Planung (synthetische Datei) im Browser ──
fehler = []
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.goto(B + '/module/hr/#mitarbeiter'); pg.wait_for_selector('#ma-tabelle tr[data-person]')
    check('Personalstelle: alle Bereiche sichtbar, offener Antrag gezählt', pg.is_visible('[data-tab="antraege"]') and pg.text_content('#hr-offen') == '1')
    pg.click('#ma-import'); pg.set_input_files('#import-datei', os.path.join(FIX, 'hr', 'Urlaub_Muster_2025.xlsx'))
    pg.wait_for_selector('#import-vorschau .zahlen'); pg.wait_for_function('!document.querySelector("#import-los").disabled')
    txt = pg.text_content('#import-vorschau')
    check('Vorschau: 5 neue Mitarbeiter, Einträge, unbekanntes Kürzel, regelmäßige freie Tage', 'Anna Beispiel' in txt and '„S“ (1×)' in txt and 'Dieter Test (meist Fr)' in txt, txt[:400])
    pg.screenshot(path=os.path.join(SH, 'hr_import_1280.png'))
    pg.click('#import-los'); pg.wait_for_selector('#import-meldung.ok')
    pg.click('#dlg-import [data-schliessen]')
    st, r = P.call('hr_verwaltung&jahr=2025')
    namen = {p_['name']: p_ for p_ in r['personen']}
    imp = [e for e in r['eintraege'] if e['quelle'] == 'import']
    check('Übernommen: Mitarbeiter mit Abteilung (verbundene Zellen fortgeführt)', namen.get('Emil Lager', {}).get('abteilung') == 'Lager' and namen.get('Bernd Muster', {}).get('abteilung') == 'Verwaltung'
          and namen.get('Carla Probe', {}).get('abteilung') == 'Verwaltung', {k: v['abteilung'] for k, v in namen.items()})
    arten = sorted((e['name'], e['art'], e['von'], e['bis']) for e in imp if e['art'] != 'X')
    check('Übernommen: Zeiträume zusammengefasst', arten == [('Anna Beispiel', 'U', '2025-01-13', '2025-01-17'), ('Bernd Muster', 'K', '2025-01-20', '2025-01-21'),
                                                          ('Carla Probe', 'G', '2025-01-31', '2025-01-31'), ('Carla Probe', 'U', '2025-02-03', '2025-02-04')], arten)
    check('Übernommen: freie Tage „x“ als einzelne Tage', len([e for e in imp if e['art'] == 'X']) == 9 and all(e['status'] == 'genehmigt' for e in imp))
    # erneute Übernahme ersetzt (keine Doppelten)
    pg.click('#ma-import'); pg.set_input_files('#import-datei', os.path.join(FIX, 'hr', 'Urlaub_Muster_2025.xlsx'))
    pg.wait_for_function('!document.querySelector("#import-los").disabled')
    check('erneute Übernahme: frühere Einträge werden ersetzt', '13 Einträge der letzten Übernahme werden ersetzt' in pg.text_content('#import-vorschau'), pg.text_content('#import-vorschau')[:300])
    pg.click('#import-los'); pg.wait_for_selector('#import-meldung.ok'); pg.click('#dlg-import [data-schliessen]')
    r = P.call('hr_verwaltung&jahr=2025')[1]
    check('… keine doppelten Einträge oder Mitarbeiter', len([e for e in r['eintraege'] if e['quelle'] == 'import']) == 13 and len(r['personen']) == 8, (len(r['eintraege']), len(r['personen'])))
    k26 = {p_['name']: p_['konto'] for p_ in P.call('hr_verwaltung&jahr=2026')[1]['personen']}
    check('ohne bekannten Anspruch im Vorjahr kein (negativer) automatischer Übertrag', k26['Anna Beispiel']['uebertrag'] == 0, k26['Anna Beispiel'])
    abt = [p_['abteilung'] for p_ in P.call(f'hr_monat&jahr={Y}&monat=1')[1]['personen']]
    bloecke = [x for i, x in enumerate(abt) if i == 0 or abt[i - 1] != x]
    check('Kalender: jede Abteilung ein Block (Reihenfolge nach Position)', len(bloecke) == len(set(bloecke)) and bloecke[0] == 'GF', abt)
    pg.goto(B + '/module/hr/#mitarbeiter'); pg.wait_for_selector('#ma-tabelle tr[data-person]')
    pg.screenshot(path=os.path.join(SH, 'hr_mitarbeiter_1280.png'), full_page=True)

    # Antrag genehmigen in der Oberfläche
    pg.click('[data-tab="antraege"]'); pg.wait_for_selector('.hr-antrag')
    pg.screenshot(path=os.path.join(SH, 'hr_antraege_1280.png'), full_page=True)
    pg.click('.hr-antrag [data-genehmigen]'); pg.wait_for_selector('.hr-leer')
    check('Oberfläche: Antrag genehmigt, keine offenen mehr', P.call('hr_verwaltung&jahr=' + str(Y))[1]['offen'] == [])

    # Kalender der Personalstelle: Eintrag per Klick
    pg.click('[data-tab="kalender"]'); pg.wait_for_selector('#kal-plan tbody tr')
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_1280.png'), full_page=True)
    pg.click('#kal-eintragen'); pg.wait_for_selector('#dlg-eintrag[open]')
    pg.select_option('#eintrag-person', PA); pg.select_option('#eintrag-art', 'G')
    gtag = montag(Y, 3, 2) + dt.timedelta(days=1)   # Dienstag im März (keine Feiertage)
    pg.fill('#eintrag-von', iso(gtag)); pg.dispatch_event('#eintrag-von', 'change')
    pg.click('#eintrag-speichern')
    pg.wait_for_selector('#dlg-eintrag[open]', state='hidden')
    gz = [e for e in P.call('hr_verwaltung&jahr=' + str(Y))[1]['eintraege'] if e['person'] == PA and e['art'] == 'G']
    check('Oberfläche: Gleittag eingetragen', len(gz) == 1 and gz[0]['von'] == iso(gtag) == gz[0]['bis'], gz)
    pg.click('#kal-eintragen'); pg.wait_for_selector('#dlg-eintrag[open]')
    pg.select_option('#eintrag-person', PA); pg.fill('#eintrag-von', iso(gtag + dt.timedelta(days=3))); pg.dispatch_event('#eintrag-von', 'change')
    pg.click('#eintrag-speichern'); pg.wait_for_selector('#eintrag-meldung.fehler')
    check('Oberfläche: Fehler im Dialog (freier Tag), Dialog bleibt offen', 'Arbeitstage' in pg.text_content('#eintrag-meldung') and pg.is_visible('#dlg-eintrag'))
    pg.click('#dlg-eintrag [data-schliessen]')

    # Export in der Oberfläche
    pg.click('[data-tab="export"]'); pg.wait_for_selector('#export-jahr option', state='attached')
    with pg.expect_download() as dl:
        pg.click('#export button[type="submit"]')
    check('Oberfläche: Excel-Download', dl.value.suggested_filename.startswith('Urlaub_') and dl.value.suggested_filename.endswith('.xlsx'), dl.value.suggested_filename)
    pg.screenshot(path=os.path.join(SH, 'hr_export_1280.png'))
    ctx.close()

    # Mitarbeiterin: Mein Urlaub, Antrag in der Oberfläche, Desktop und Handy
    for breite in (1280, 390):
        ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', breite)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-konto .hr-wert')
        check(f'{breite}px: Personalbereiche ausgeblendet', not pg.is_visible('[data-tab="antraege"]') and not pg.is_visible('[data-tab="export"]'))
        breit = pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        check(f'{breite}px: kein waagerechtes Scrollen der Seite', breit)
        pg.screenshot(path=os.path.join(SH, f'hr_mein_{breite}.png'), full_page=True)
        if breite == 1280:
            pg.click('[data-jahr="1"]')
            pg.wait_for_function(f'document.querySelector("#mein-titel").textContent.includes("{Y}")')
            tag_ = montag(Y, 9)
            pg.fill('#antrag-von', iso(tag_)); pg.dispatch_event('#antrag-von', 'change')
            pg.fill('#antrag-bis', iso(tag_ + dt.timedelta(days=4))); pg.dispatch_event('#antrag-bis', 'change')
            check('Vorschau: 5 Tage Urlaub', '5 Tage' in pg.text_content('#antrag-tage'), pg.text_content('#antrag-tage'))
            pg.click('#antrag-senden'); pg.wait_for_selector('#antrag-meldung.ok')
            check('Oberfläche: Antrag gestellt, in der Liste', 'beantragt' in pg.text_content('#mein-liste'))
        pg.click('[data-tab="kalender"]'); pg.wait_for_selector('#kal-plan tbody tr')
        check(f'{breite}px: Kalender ohne Gründe (nur „abwesend“ in der Legende)', 'Krank' not in pg.text_content('#kal-legende') and 'abwesend' in pg.text_content('#kal-legende'))
        pg.screenshot(path=os.path.join(SH, f'hr_kalender_mitarbeiter_{breite}.png'), full_page=True)
        ctx.close()

    # nicht freigegeben: Hinweis statt Fehler
    ctx, pg = anmelden('otto', 'Ohne-Zugang-77', '198.51.100.6')
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-err:not([hidden])')
    check('nicht eingetragener Tester: Hinweis „noch nicht freigegeben“', 'nicht freigegeben' in pg.text_content('#hr-err'))
    ctx.close()
    ctx = br.new_context(); pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis', pg.is_visible('#hr-login a'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
