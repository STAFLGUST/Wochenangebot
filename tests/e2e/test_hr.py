"""HR · Urlaubsverwaltung (Modul hr, Oberfläche hr.intern unter /module/hr/).

Geprüft: Freigabe (produktiv seit 23.10.2026: jeder Mitarbeiter mit hr.antrag, keine Testfreigabe), Mitarbeiter = Nutzer
(jeder Mitarbeiter ist sofort in der Urlaubsverwaltung; Mitarbeiter ohne Anmeldung; HR-Angaben in der Verwaltung;
Übernahme alter Einträge ohne Mitarbeiter), Rechte (hr.antrag für alle, hr.verwalten nur Personalstelle, hr.genehmigen als eigenes
zuweisbares Recht, nie der eigene Antrag und nie eigene Abwesenheiten – auch nicht als Administrator; serverseitig – GR-103), Antrag → Genehmigung/Ablehnung/Zurückziehen, Grenzfälle (Vergangenheit,
Wochenende, Überschneidung, Urlaubssperre), Urlaubskonto mit Übertrag bis 31.03. und Verfall, 4-Tage-Woche,
Datenschutz im Kalender (Kollegen sehen nur „abwesend“, nie Art, Notiz oder offene Anträge; Protokoll ohne Art),
Excel-Export für den Steuerberater (Aufbau der bisherigen Planung, nur genehmigte Einträge), Schalter „Urlaubsanträge über
die Plattform“ (Verwaltung → Urlaub, Standard an; aus: Server lehnt Anträge ab, Formular ausgeblendet), Übernahme der bisherigen
Excel-Planung entfällt (Auftrag des Inhabers 02.11.2026: nicht mehr nötig – Importart und Aktionen fehlen, frühere Einträge
bleiben), Abwesenheiten aus der Zeiterfassung (Importvorlage, tests/fixtures/hr/Abwesenheitsbericht_Muster.xlsx: Personalnummer, Schreibweisen, vom Urlaub
abgezogene Krankheit – zählt hier nie gegen den Urlaub –, Ersetzen, veralteter Stand), Korrektur melden (Mitarbeiter → Personalstelle,
nie die eigene erledigen), Mini-Kalender „Mein Jahr“ und die Oberflächen
(HR-Seite, Verwaltung → Mitarbeiter und Urlaub; Desktop, 390 px).
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
from smtp_test import TestSmtp
from umgebung import SH, FIX, SMTP_PORT, storage_raw, storage_write, until

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


def dokument(name):
    """Gespeichertes Dokument lesen (Dateien: ohne Schutzzeile)."""
    raw = storage_raw(name)
    if not raw:
        return {}
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


Y = dt.date.today().year + 1           # Anträge nur für die Zukunft: alles im nächsten Jahr
FEB = montag(Y, 2)                      # Montag der ersten vollen Februarwoche (vor dem 31.03.: verbraucht Übertrag)
AUG = montag(Y, 8, 2)

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('erika', 'Erika Editor', 'editor', 'Editor-Zugang-77', {}), ('lena', 'Lena Leser', 'viewer', 'Leser-Zugang-77', {}),
                          ('paul', 'Paul Personal', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.verwalten', 'hr.genehmigen']}), ('otto', 'Otto Ohne', 'editor', 'Ohne-Zugang-77', {})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
st, r_ = A.call('user_save', {'id': '', 'vorname': 'Andre', 'nachname': 'Vierzig', 'role': 'editor', 'active': True, 'zugang': False})
check('Mitarbeiter ohne Anmeldung: ohne Passwort angelegt, deaktiviert, Rolle Leser', st == 200 and r_['user']['zugang'] is False and r_['user']['active'] is False
      and r_['user']['role'] == 'viewer' and r_['user']['username'] == 'andre-vierzig', r_)
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
check('… kann sich nicht anmelden', Client('198.51.100.30').call('login', {'username': 'andre-vierzig', 'password': 'Urlaub-Konto-4711'})[0] in (401, 403))
st, r_ = A.call('user_save', {'id': ids['andre-vierzig'], 'vorname': 'Andre', 'nachname': 'Vierzig', 'role': 'viewer', 'active': True, 'zugang': True})
check('Anmeldung einrichten nur mit Passwort (422)', st == 422 and 'Passwort' in r_.get('error', ''), r_)
check('eigenen Zugang nicht auf „ohne Anmeldung“ (422)', A.call('user_save', {'id': ids['admin'], 'name': 'Administrator', 'role': 'admin', 'active': True, 'zugang': False})[0] == 422)
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
L = Client('198.51.100.4'); L.call('login', {'username': 'lena', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.5'); P.call('login', {'username': 'paul', 'password': 'Personal-Zugang-77'})
O = Client('198.51.100.6'); O.call('login', {'username': 'otto', 'password': 'Ohne-Zugang-77'})
N = Client('198.51.100.7')

# ── Freigabe ──
# Produktiv seit der Freigabe des Inhabers (23.10.2026): kein Testbetrieb, keine Tester – jeder Mitarbeiter mit hr.antrag
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['hr']
check('Register: HR fertig und produktiv, Adresse hr.dashboard-stafl.de/module/hr/', (lambda o: o['entwicklung'] == 'fertig' and o['freigabe'] == 'produktiv'
      and o['zugang'] and o['adresse'] == 'https://hr.dashboard-stafl.de/module/hr/')(mod['oberflaechen'][0]), mod)
check('Kachel verfügbar', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True, mod['kachel'])
st, r = A.call('modul_freigabe_save', {'bereich': 'hr.intern', 'freigabe': 'test', 'grund': 'Test'})
check('Produktivbereich: keine Testfreigabe über die Modulverwaltung (nur über ein Release)', st == 422, (st, r))
st, r = O.call('hr_start')
check('jeder Mitarbeiter mit hr.antrag: Start ok (otto, nie als Tester eingetragen)', st == 200 and r.get('ok'), (st, r))
check('Administrator und Personalstelle: Start ok', A.call('hr_start')[0] == 200 and P.call('hr_start')[0] == 200)
check('ohne Anmeldung: 401', N.call('hr_start')[0] == 401 and N.call('hr_verwaltung')[0] == 401 and N.call('mitarbeiter_hr')[0] == 401)

# ── Rechte ──
check('Mitarbeiter ohne Personalrecht: hr_verwaltung 403', L.call('hr_verwaltung')[0] == 403 and E.call('hr_verwaltung')[0] == 403 and L.call('mitarbeiter_hr')[0] == 403)
for a, b in (('hr_entscheiden', {'id': 'x', 'entscheidung': 'genehmigt'}), ('hr_eintrag_save', {'person': 'x', 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB)}),
             ('mitarbeiter_hr_save', {'nutzer': 'x', 'rev': 0}), ('hr_export', {'jahr': Y, 'monate': [2]}), ('hr_einstellungen_save', {'sperren': []}),
             ('hr_personal_uebernehmen', {})):
    check(f'{a}: ohne Personalrecht 403', L.call(a, b)[0] == 403)
check('hr_offen: ohne „Urlaub genehmigen“ 403', L.call('hr_offen')[0] == 403 and E.call('hr_offen')[0] == 403 and N.call('hr_offen')[0] == 401)
check('hr_start: Rechte-Hinweise für die Oberfläche', E.call('hr_start')[1]['genehmigen'] is False and P.call('hr_start')[1]['genehmigen'] is True)
kat = {x['key']: x for x in A.call('rechte')[1]['catalog']}
check('Recht „Urlaub genehmigen“ im Katalog: zuweisbar, keine Standardrollen, setzt hr.antrag voraus', kat['hr.genehmigen']['default'] == [] and kat['hr.genehmigen']['requires'] == ['hr.antrag']
      and kat['hr.genehmigen']['group'] == 'HR' and 'hr.verwalten' in kat, kat.get('hr.genehmigen'))

# ── Mitarbeiter = Nutzer ──
st, r = E.call('hr_start')
check('jeder Mitarbeiter ist sofort in der Urlaubsverwaltung (ohne Zuordnung)', st == 200 and r['ich'] and r['ich']['id'] == ids['erika'] and r['konto']['anspruch'] == 0, r.get('ich'))
v = P.call('mitarbeiter_hr')[1]
pv = {p_['nutzer']: p_ for p_ in v['personen'] if p_['nutzer']}
check('Verwaltung: alle Mitarbeiter mit HR-Angaben (Standard: Mo–Fr, im Urlaubsplan)', set(ids.values()) <= set(pv) and pv[ids['otto']]['arbeitstage'] == [1, 2, 3, 4, 5]
      and pv[ids['otto']]['aktiv'] is True and pv[ids['andre-vierzig']]['zugang'] is False, sorted(pv))
rev = v['rev']


def hr(uid, **werte):
    global rev
    # eigene Urlaubsangaben ändert eine andere Person der Personalstelle (Vier-Augen-Prinzip) – für Paul der Administrator
    st, r = (A if uid == ids['paul'] else P).call('mitarbeiter_hr_save', {'nutzer': uid, 'rev': rev, **werte})
    assert st == 200, r
    rev = r['rev']
    return r['person']['id']


PE = hr(ids['erika'], abteilung='Verwaltung', pos=1, jahr=Y, anspruch=30, uebertrag=5)
PL = hr(ids['lena'], abteilung='Verwaltung', pos=2, jahr=2025, anspruch=30, uebertrag=4)
PA = hr(ids['andre-vierzig'], abteilung='Lager', pos=3, arbeitstage=[1, 2, 3, 4], jahr=Y, anspruch=24)
check('Person = Mitarbeiter-Kennung', (PE, PL, PA) == (ids['erika'], ids['lena'], ids['andre-vierzig']))
check('veralteter Stand: 409', P.call('mitarbeiter_hr_save', {'nutzer': ids['erika'], 'rev': rev - 1, 'pos': 1})[0] == 409)
check('ungültiger Anspruch (Viertel-Tage): 422', P.call('mitarbeiter_hr_save', {'nutzer': ids['erika'], 'rev': rev, 'jahr': Y, 'anspruch': 10.25})[0] == 422)
check('ohne Arbeitstage: 422', P.call('mitarbeiter_hr_save', {'nutzer': ids['erika'], 'rev': rev, 'arbeitstage': []})[0] == 422)
check('unbekannter Mitarbeiter: 404', P.call('mitarbeiter_hr_save', {'nutzer': 'u-gibt-es-nicht', 'rev': rev})[0] == 404)
hr(ids['otto'], aktiv=False)
check('nicht im Urlaubsplan: kein eigenes Konto, Antrag 409', O.call('hr_start')[1]['ich'] is None and O.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG)})[0] == 409)
check('… und nicht im Kalender', ids['otto'] not in [p_['id'] for p_ in P.call(f'hr_monat&jahr={Y}&monat=2')[1]['personen']])
hr(ids['admin'], aktiv=False); hr(ids['paul'], aktiv=False)
check('Namen kommen aus dem Mitarbeiter (Verwaltung → Mitarbeiter)', {p_['id']: p_['name'] for p_ in P.call('hr_verwaltung')[1]['personen']}[PA] == 'Andre Vierzig')

# ── Jahresplanung (Inhaber 03.11.2026): Standard der Einstellungen; Vertretung bei Urlaubsanträgen Pflicht – für die
#    Antragstests bis zum Abschnitt „Jahresplanung“ unten ausgeschaltet (dort und in der Oberfläche geprüft) ──
v_ = P.call('mitarbeiter_hr')[1]
PLAN_STD = v_['planung']
check('Jahresplanung: Standard Beginn 01.10., Stichtag 01.12., 90 %, Vertretung Pflicht', PLAN_STD == {'start': '10-01', 'stichtag': '12-01', 'prozent': 90, 'vertretungPflicht': True}, PLAN_STD)
st, r = E.call('hr_antrag', {'von': iso(FEB), 'bis': iso(FEB)})
check('… Urlaubsantrag ohne Vertretung: 422 mit Hinweis', st == 422 and 'Vertretung' in r.get('error', ''), (st, r))
assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'planung': {**PLAN_STD, 'vertretungPflicht': False}})[0] == 200

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

# ── Sperren aus den Urlaubsregeln und Text der Urlaubsregeln (Inhaber 03.11.2026) ──
def ostern(j):
    a, b, c = j % 19, j // 100, j % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m_ = (a + 11 * h + 22 * l_) // 451
    return dt.date(j, (h + l_ - 7 * m_ + 114) // 31, (h + l_ - 7 * m_ + 114) % 31 + 1)
def regel_sperren(j):
    kf, n30 = ostern(j) - dt.timedelta(days=2), dt.date(j, 11, 30)
    return [('Ostergeschäft', iso(kf - dt.timedelta(days=14)), iso(kf - dt.timedelta(days=1))), ('Weihnachtsgeschäft', iso(n30 - dt.timedelta(days=n30.weekday())), f'{j}-12-24')]
KF = ostern(Y) - dt.timedelta(days=2)
v = P.call('mitarbeiter_hr')[1]
J0 = dt.date.today().year
check('Standard: Sperren aus den Urlaubsregeln an; Vorschau dieses und nächstes Jahr (Karfreitag − 14 bis Gründonnerstag, Montag der letzten Novemberwoche bis 24.12.)',
      v['regelSperren'] is True and [(z['text'], z['von'], z['bis']) for z in v['sperrenAuto']] == regel_sperren(J0) + regel_sperren(J0 + 1)
      and all(z['auto'] for z in v['sperrenAuto']) and len(v['sperren']) == 1, v.get('sperrenAuto'))
sp = E.call(f'hr_start&jahr={Y}')[1]['sperren']
check('… gelten wie eingetragene Sperren (Start: eigene und automatische)', [(z['text'], z['von'], z['bis']) for z in sp if z.get('auto') and z['von'][:4] == str(Y)] == regel_sperren(Y)
      and any(z['text'] == 'Weihnachtsgeschäft' and not z.get('auto') for z in sp), sp)
st, r = E.call('hr_antrag', {'von': iso(KF - dt.timedelta(days=11)), 'bis': iso(KF - dt.timedelta(days=10))})
check('Antrag im Ostergeschäft: 422 mit Bezeichnung', st == 422 and 'Ostergeschäft' in r.get('error', ''), (st, r))
tage_m = {t['datum']: t['sperre'] for t in P.call(f'hr_monat&jahr={Y}&monat={KF.month}')[1]['tage']}
check('… Kalender markiert die Tage', tage_m.get(iso(KF - dt.timedelta(days=1))) is True and tage_m.get(iso(KF + dt.timedelta(days=4)), False) is False)
base = {'sperren': v['sperren'], 'ferien': v['ferien']}
check('Schalter nur ja/nein: 422', P.call('hr_einstellungen_save', {**base, 'regelSperren': 'nein'})[0] == 422)
st, r = P.call('hr_einstellungen_save', {**base, 'regelSperren': False})
check('ausgeschaltet: keine automatischen Sperren mehr, eigene bleiben', st == 200 and r['regelSperren'] is False and len(r['sperren']) == 1
      and not any(z.get('auto') for z in E.call(f'hr_start&jahr={Y}')[1]['sperren']), r)
st, r = E.call('hr_antrag', {'von': iso(KF - dt.timedelta(days=11)), 'bis': iso(KF - dt.timedelta(days=10))})
check('… Antrag im Ostergeschäft dann möglich', st == 200, (st, r))
if st == 200: E.call('hr_antrag_zurueckziehen', {'id': r['eintrag']['id']})
check('… Speichern ohne Angabe lässt den Schalter', P.call('hr_einstellungen_save', base)[0] == 200 and P.call('mitarbeiter_hr')[1]['regelSperren'] is False)
check('… wieder eingeschaltet', P.call('hr_einstellungen_save', {**base, 'regelSperren': True})[1]['regelSperren'] is True)
d0 = E.call('hr_start')[1]
check('Urlaubsregeln: Vorlage mit 6 Punkten für jeden Mitarbeiter (Planung bis 31.03.)', d0['regeln'].startswith('1. Urlaubsanspruch') and d0['regeln'].count('\n\n') == 5
      and 'bis zum 31.03. eines jeden Kalenderjahres' in d0['regeln'] and '31.02' not in d0['regeln'] and v['regelnStandard'] == d0['regeln'])
st, r = P.call('hr_einstellungen_save', {**base, 'regeln': 'Unsere Regeln\r\n\n1. Planung\nBitte früh planen.\x07\ufeff'})
check('eigener Text gespeichert (ohne Steuerzeichen) und für Mitarbeiter sichtbar', st == 200 and r['regeln'] == 'Unsere Regeln\n\n1. Planung\nBitte früh planen.'
      and E.call('hr_start')[1]['regeln'] == r['regeln'], r.get('regeln'))
check('… zu lang oder kein Text: 422; ohne Personalrecht 403', P.call('hr_einstellungen_save', {**base, 'regeln': 'x' * 6001})[0] == 422
      and P.call('hr_einstellungen_save', {**base, 'regeln': 5})[0] == 422 and L.call('hr_einstellungen_save', {**base, 'regeln': 'x'})[0] == 403)
check('… Speichern ohne Text lässt ihn unverändert', P.call('hr_einstellungen_save', base)[0] == 200 and E.call('hr_start')[1]['regeln'] == 'Unsere Regeln\n\n1. Planung\nBitte früh planen.')
check('… leer = keine Regeln', P.call('hr_einstellungen_save', {**base, 'regeln': ''})[0] == 200 and E.call('hr_start')[1]['regeln'] == '')
check('… Vorlage wieder eingesetzt', P.call('hr_einstellungen_save', {**base, 'regeln': v['regelnStandard']})[0] == 200 and E.call('hr_start')[1]['regeln'] == d0['regeln'])
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Schalter und Regeltext', 'Sperren aus den Urlaubsregeln ausgeschaltet' in log_ and 'Sperren aus den Urlaubsregeln eingeschaltet' in log_ and 'HR: Urlaubsregeln geändert' in log_)

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

# ── Urlaub genehmigen: eigenes, zuweisbares Recht (Inhaber 25.10.2026); nie der eigene Antrag, nie eigene Abwesenheiten ──
OKT = montag(Y, 10, 2)
for u, n, extra in (('gina', 'Gina Genehmigt', ['hr.genehmigen']), ('vera', 'Vera Verwalten', ['hr.verwalten'])):
    assert A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': 'Genehmigen-Zugang-77', 'mustChange': False, 'grant': extra})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
G = Client('198.51.100.8'); G.call('login', {'username': 'gina', 'password': 'Genehmigen-Zugang-77'})
V = Client('198.51.100.9'); V.call('login', {'username': 'vera', 'password': 'Genehmigen-Zugang-77'})
st, r = G.call('hr_offen')
og = {a['id']: a for a in r.get('offen', [])}
check('nur „Urlaub genehmigen“: offene Anträge mit Konto, ohne Personaldaten', st == 200 and OFFEN in og and 'konto' in og[OFFEN] and og[OFFEN]['eigen'] is False
      and 'personen' not in r and 'eintraege' not in r, (st, list(r)))
check('… nur Urlaubsanträge, keine Krankheiten', all(a['art'] == 'U' for a in r['offen']) and 'Arzt' not in json.dumps(r), [a['art'] for a in r['offen']])
check('… keine Personalstelle: hr_verwaltung, Einträge und Export 403', G.call('hr_verwaltung')[0] == 403
      and G.call('hr_eintrag_save', {'person': PL, 'art': 'K', 'von': iso(OKT), 'bis': iso(OKT)})[0] == 403 and G.call('hr_export', {'jahr': Y, 'monate': [2]})[0] == 403)
st, r = E.call('hr_antrag', {'von': iso(OKT), 'bis': iso(OKT + dt.timedelta(days=1))})
A_OKT = r['eintrag']['id']
check('fremden Antrag genehmigen mit „Urlaub genehmigen“', G.call('hr_entscheiden', {'id': A_OKT, 'entscheidung': 'genehmigt'})[0] == 200)
check('… Mitarbeiterin zieht den künftigen Urlaub wieder zurück (Konto unverändert)', E.call('hr_antrag_zurueckziehen', {'id': A_OKT})[0] == 200)
st, r = V.call('hr_verwaltung&jahr=' + str(Y))
check('Personalstelle ohne Genehmigungsrecht: sieht offene Anträge', st == 200 and OFFEN in [a['id'] for a in r['offen']], st)
check('… darf aber nicht entscheiden (403) und hr_offen nicht (403)', V.call('hr_entscheiden', {'id': OFFEN, 'entscheidung': 'genehmigt'})[0] == 403 and V.call('hr_offen')[0] == 403)
check('… Start: Zahl offener Anträge trotzdem', (lambda x: x['verwalten'] is True and x['genehmigen'] is False and x['offen'] >= 1)(V.call('hr_start')[1]))
# Vier-Augen-Prinzip
st, r = G.call('hr_antrag', {'von': iso(OKT + dt.timedelta(days=7)), 'bis': iso(OKT + dt.timedelta(days=8))})
A_GINA = r['eintrag']['id']
og = {a['id']: a for a in G.call('hr_offen')[1]['offen']}
check('eigener Antrag als „eigen“ markiert, zählt nicht am Reiter', og[A_GINA]['eigen'] is True and G.call('hr_start')[1]['offen'] == len(og) - 1, (og.get(A_GINA), G.call('hr_start')[1]['offen']))
st, r = G.call('hr_entscheiden', {'id': A_GINA, 'entscheidung': 'genehmigt'})
check('eigenen Antrag genehmigen: 403', st == 403 and 'eigenen Antrag' in r.get('error', ''), (st, r))
check('eigenen Antrag ablehnen: 403', G.call('hr_entscheiden', {'id': A_GINA, 'entscheidung': 'abgelehnt', 'grund': 'x'})[0] == 403)
check('… Antrag bleibt offen', {x['id']: x for x in G.call('hr_start&jahr=' + str(Y))[1]['eintraege']}[A_GINA]['status'] == 'beantragt')
check('Administrator darf ihn entscheiden (andere Person)', A.call('hr_entscheiden', {'id': A_GINA, 'entscheidung': 'abgelehnt', 'grund': 'Test'})[0] == 200)
hr(ids['admin'], aktiv=True)
st, r = A.call('hr_antrag', {'von': iso(OKT + dt.timedelta(days=14)), 'bis': iso(OKT + dt.timedelta(days=14))})
A_ADMIN = r['eintrag']['id']
check('Administrator: eigenen Antrag nicht genehmigen (403, alle Rechte reichen nicht)', A.call('hr_entscheiden', {'id': A_ADMIN, 'entscheidung': 'genehmigt'})[0] == 403)
check('… Paul genehmigt ihn', P.call('hr_entscheiden', {'id': A_ADMIN, 'entscheidung': 'genehmigt'})[0] == 200)
check('Administrator: eigenen Urlaub nicht direkt eintragen (403)', A.call('hr_eintrag_save', {'person': ids['admin'], 'art': 'U', 'von': iso(OKT + dt.timedelta(days=21)), 'bis': iso(OKT + dt.timedelta(days=21))})[0] == 403)
check('… und den genehmigten nicht ändern oder stornieren (403)', A.call('hr_eintrag_save', {'id': A_ADMIN, 'person': ids['admin'], 'art': 'U', 'von': iso(OKT + dt.timedelta(days=14)), 'bis': iso(OKT + dt.timedelta(days=16))})[0] == 403
      and A.call('hr_eintrag_save', {'id': A_ADMIN, 'stornieren': True})[0] == 403)
check('… Paul storniert ihn (andere Person)', P.call('hr_eintrag_save', {'id': A_ADMIN, 'stornieren': True})[0] == 200)
hr(ids['admin'], aktiv=False)
st, r = P.call('hr_eintrag_save', {'person': ids['paul'], 'art': 'U', 'von': iso(OKT), 'bis': iso(OKT)})
check('Personalstelle: sich selbst Urlaub eintragen 403 (auch nicht im Urlaubsplan)', st == 403 and 'andere Person' in r.get('error', ''), (st, r))
for art in ('K', 'G', 'X'):
    check(f'… auch {art} für sich selbst 403', P.call('hr_eintrag_save', {'person': ids['paul'], 'art': art, 'von': iso(OKT), 'bis': iso(OKT)})[0] == 403)
st, r = A.call('hr_eintrag_save', {'person': ids['paul'], 'art': 'K', 'von': iso(OKT), 'bis': iso(OKT)})
EP = r.get('eintrag', {}).get('id')
check('Eintrag einer anderen Person für Paul: Paul darf ihn nicht ändern oder umhängen (403)', st == 200
      and P.call('hr_eintrag_save', {'id': EP, 'person': PL, 'art': 'K', 'von': iso(OKT), 'bis': iso(OKT)})[0] == 403
      and P.call('hr_eintrag_save', {'id': EP, 'stornieren': True})[0] == 403, (st, r))
r = P.call('hr_verwaltung&jahr=' + str(Y))[1]
check('… in „Alle Einträge“ als eigen markiert', {e['id']: e for e in r['eintraege']}.get(EP, {}).get('eigen') is True)
check('… Administrator storniert ihn', A.call('hr_eintrag_save', {'id': EP, 'stornieren': True})[0] == 200)
hr(ids['gina'], aktiv=False); hr(ids['vera'], aktiv=False)

# 4-Tage-Woche
st, r = P.call('hr_eintrag_save', {'person': PA, 'art': 'U', 'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=4))})
check('4-Tage-Woche: Mo–Fr zählt 4 Urlaubstage', st == 200 and r['eintrag']['tage'] == 4, r)
zp = {p['id']: p['tage'] for p in P.call(f'hr_monat&jahr={Y}&monat=8')[1]['personen']}
fr = str((AUG + dt.timedelta(days=4)).day)
check('… Freitag als freier Tag „x“', zp[PA].get(fr) == 'x' and zp[PA].get(str(AUG.day)) == 'U', zp[PA])
zl = {p['id']: p['tage'] for p in L.call(f'hr_monat&jahr={Y}&monat=8')[1]['personen']}
check('… für Kollegen nur „abwesend“', zl[PA].get(fr) == 'A' and zl[PA].get(str(AUG.day)) == 'A', zl[PA])
check('Eintrag nur an freiem Tag (U): 422', P.call('hr_eintrag_save', {'person': PA, 'art': 'U', 'von': iso(AUG + dt.timedelta(days=11)), 'bis': iso(AUG + dt.timedelta(days=11))})[0] == 422)

# Eingetragener freier Tag („X“) sperrt keine Abwesenheit: er zählt nur nicht mit
SEP = montag(Y, 9, 2)
st, r = P.call('hr_eintrag_save', {'person': PE, 'art': 'X', 'von': iso(SEP + dt.timedelta(days=4)), 'bis': iso(SEP + dt.timedelta(days=4))})
check('freier Tag (X) eingetragen', st == 200, r)
FREI_X = r['eintrag']['id']
check('zweiter freier Tag am selben Tag: 409', P.call('hr_eintrag_save', {'person': PE, 'art': 'X', 'von': iso(SEP + dt.timedelta(days=4)), 'bis': iso(SEP + dt.timedelta(days=4))})[0] == 409)
st, r = E.call('hr_antrag', {'von': iso(SEP), 'bis': iso(SEP + dt.timedelta(days=4))})
check('Antrag über eine Woche mit freiem Tag: 200, zählt 4 Tage', st == 200 and r['eintrag']['tage'] == 4, (st, r))
ANTRAG_X = r['eintrag']['id'] if st == 200 else None
st, r = P.call('hr_eintrag_save', {'person': PE, 'art': 'K', 'von': iso(SEP + dt.timedelta(days=4)), 'bis': iso(SEP + dt.timedelta(days=4))})
check('… Krank am freien Tag: weiter 409 wegen des Antrags, nicht wegen „X“', st == 409 and 'Eintrag' in r.get('error', ''), (st, r))
check('… aufräumen', E.call('hr_antrag_zurueckziehen', {'id': ANTRAG_X})[0] == 200 and P.call('hr_eintrag_save', {'id': FREI_X, 'stornieren': True})[0] == 200)

# Antrag über den Jahreswechsel: „Resturlaub danach“ rechnet nur die Tage im Jahr des Kontos
st, r = E.call('hr_antrag', {'von': f'{Y + 1}-12-28', 'bis': f'{Y + 2}-01-08'})
check('Antrag über den Jahreswechsel', st == 200, (st, r))
JW = r['eintrag']['id'] if st == 200 else None
jw = next((a for a in P.call('hr_verwaltung')[1]['offen'] if a['id'] == JW), {})
check('… Tage im Jahr des Kontos getrennt ausgewiesen', jw.get('tageImJahr', 0) > 0 and jw['tageImJahr'] < jw['tage'] and jw['konto']['jahr'] == Y + 1, jw)
check('… zurückgezogen', E.call('hr_antrag_zurueckziehen', {'id': JW})[0] == 200)

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

# ── Altbestand: Einträge der Urlaubsliste ohne Mitarbeiter (vor „Mitarbeiter = Nutzer“) ──
for u, n in (('gerda-gleich', 'Gerda Gleich'), ('hans', 'Hans Doppelt')):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': 'Urlaub-Konto-4711', 'mustChange': False})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
alt = dokument('hr-personal')
alt['personen'] += [{'id': 'pgerda', 'vorname': 'Gerda', 'nachname': 'Gleich', 'abteilung': 'Lager', 'pos': 4, 'aktiv': True, 'jahre': {str(Y): {'anspruch': 28}}},
                    {'id': 'phans1', 'vorname': 'Hans', 'nachname': 'Doppelt', 'abteilung': 'Lager', 'pos': 5, 'aktiv': True},
                    {'id': 'phans2', 'vorname': 'Hans', 'nachname': 'Doppelt', 'abteilung': 'GF', 'pos': 6, 'aktiv': True},
                    {'id': 'pkarl', 'vorname': 'Karl', 'nachname': 'Alt', 'abteilung': 'Lager', 'pos': 7, 'aktiv': True}]
alt['rev'] = alt.get('rev', 0) + 1
storage_write('hr-personal', alt)
ab = dokument('hr-abwesenheiten')
ab['eintraege'] += [{'id': 'aalt1', 'person': 'pgerda', 'art': 'U', 'von': iso(montag(Y, 6)), 'bis': iso(montag(Y, 6)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'personalstelle'},
                    {'id': 'aalt2', 'person': 'pkarl', 'art': 'U', 'von': iso(montag(Y, 6)), 'bis': iso(montag(Y, 6)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'personalstelle'}]
ab['rev'] = ab.get('rev', 0) + 1
storage_write('hr-abwesenheiten', ab)
v = P.call('mitarbeiter_hr')[1]
check('Verwaltung zeigt den Altbestand (ohne Mitarbeiter)', sorted(p_['id'] for p_ in v['personen'] if p_['altbestand']) == ['pgerda', 'phans1', 'phans2', 'pkarl'])
G = Client('198.51.100.8'); G.call('login', {'username': 'gerda-gleich', 'password': 'Urlaub-Konto-4711'})
rev_vorher = dokument('hr-personal').get('rev')
st, r = G.call('hr_start&jahr=' + str(Y))
# Keine automatische Verknüpfung mehr (Sicherheitsdurchsicht 26.10.2026): nur die Personalstelle ordnet zu
check('erster Aufruf: gleichnamiger Eintrag wird NICHT automatisch übernommen, nichts gespeichert', st == 200 and r['neuVerknuepft'] is False
      and r['ich']['id'] == ids['gerda-gleich'] and not any(e['id'] == 'aalt1' for e in r['eintraege']) and dokument('hr-personal').get('rev') == rev_vorher, r.get('ich'))
H = Client('198.51.100.9'); H.call('login', {'username': 'hans', 'password': 'Urlaub-Konto-4711'})
st, r = H.call('hr_start')
check('gleicher Name zweimal im Altbestand: keine automatische Übernahme', st == 200 and r['neuVerknuepft'] is False and r['ich']['id'] == ids['hans'], r.get('ich'))
# Ohne Mitarbeiter = ehemaliger Mitarbeiter (Inhaber 26.10.2026): nicht im Urlaubsplan, Einträge bleiben, keine neuen Mitarbeiter
v = P.call('mitarbeiter_hr')[1]
pv = {p_['id']: p_ for p_ in v['personen']}
check('ehemalige Mitarbeiter: markiert, nicht im Urlaubsplan', pv['pkarl']['ehemalig'] is True and pv['pkarl']['aktiv'] is False, pv['pkarl'])
check('… nicht im Kalender, nicht als Vertretung', 'pkarl' not in [p_['id'] for p_ in P.call(f'hr_monat&jahr={Y}&monat=6')[1]['personen']]
      and 'pkarl' not in [k['id'] for k in E.call('hr_start')[1]['kollegen']])
check('… ihre Einträge bleiben in „Alle Einträge“', any(e['person'] == 'pkarl' for e in P.call('hr_verwaltung&jahr=' + str(Y))[1]['eintraege']))
anzahl_nutzer = len(A.call('users')[1]['users'])
st, r = P.call('hr_personal_uebernehmen', {})
check('Gleichnamige zuordnen: nur eindeutig gleichnamige Mitarbeiter, keine neuen Mitarbeiter', st == 200 and r['anzahl'] == 2 and len(A.call('users')[1]['users']) == anzahl_nutzer, r)
st, r = G.call('hr_start&jahr=' + str(Y))
check('… Gerda Gleich jetzt durch die Personalstelle zugeordnet (mit Urlaub und Anspruch)', st == 200 and r['ich']['id'] == 'pgerda' and r['konto']['anspruch'] == 28
      and any(e['id'] == 'aalt1' for e in r['eintraege']), r.get('ich'))
v = P.call('mitarbeiter_hr')[1]
rev = v['rev']
pv = {p_['id']: p_ for p_ in v['personen']}
check('… Hans Doppelt: einer beim Mitarbeiter, der zweite bleibt ehemalig; Karl Alt bleibt ehemalig', pv['phans1']['nutzer'] == ids['hans']
      and sorted(p_['id'] for p_ in v['personen'] if p_['altbestand']) == ['phans2', 'pkarl'], sorted(p_['id'] for p_ in v['personen'] if p_['altbestand']))
hr(ids['hans'], aktiv=False)

# ── Altbestand einzeln zuordnen (abweichender Name, Mitarbeiter mit HR-Angaben: zusammenführen) ──
for u, n in (('mara', 'Mara Konto'), ('nina', 'Nina Neu')):
    assert A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': 'Urlaub-Konto-4711', 'mustChange': False})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
rev = P.call('mitarbeiter_hr')[1]['rev']
PM = hr(ids['mara'], abteilung='Vertrieb', pos=40, jahr=Y, anspruch=20)
JUL = montag(Y, 7)
alt = dokument('hr-personal')
alt['personen'] += [{'id': 'pmarlene', 'vorname': 'Marlene', 'nachname': 'Konto-Alt', 'abteilung': 'Lager', 'pos': 41, 'aktiv': True, 'personalnummer': '9901',
                     'jahre': {str(Y): {'anspruch': 25, 'uebertrag': 3}, str(Y - 1): {'anspruch': 24}}},
                    {'id': 'pmarlene2', 'vorname': 'Marlene', 'nachname': 'Zwei', 'abteilung': 'Lager', 'pos': 42, 'aktiv': True, 'personalnummer': '9902'}]
alt['rev'] = alt.get('rev', 0) + 1
storage_write('hr-personal', alt)
ab = dokument('hr-abwesenheiten')
ab['eintraege'] += [{'id': 'am1', 'person': 'pmarlene', 'art': 'U', 'von': iso(JUL), 'bis': iso(JUL + dt.timedelta(days=1)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'zeiterfassung'},
                    {'id': 'am2', 'person': 'pmarlene', 'art': 'K', 'von': iso(JUL + dt.timedelta(days=7)), 'bis': iso(JUL + dt.timedelta(days=7)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'zeiterfassung'},
                    {'id': 'am3', 'person': 'pmarlene', 'art': 'U', 'von': iso(JUL + dt.timedelta(days=14)), 'bis': iso(JUL + dt.timedelta(days=15)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'zeiterfassung'}]
ab['rev'] = ab.get('rev', 0) + 1
storage_write('hr-abwesenheiten', ab)
# Mara hat schon denselben Urlaub (doppelt) und einen überschneidenden
assert P.call('hr_eintrag_save', {'person': PM, 'art': 'U', 'von': iso(JUL), 'bis': iso(JUL + dt.timedelta(days=1))})[0] == 200
st, r = P.call('hr_eintrag_save', {'person': PM, 'art': 'U', 'von': iso(JUL + dt.timedelta(days=15)), 'bis': iso(JUL + dt.timedelta(days=16))})
UEBER = r['eintrag']['id']
v = P.call('mitarbeiter_hr')[1]
rev = v['rev']
st, r = P.call('mitarbeiter_hr_save', {'nutzer': ids['mara'], 'rev': rev, 'personalnummer': '9901'})
check('Personalnummer schon beim Eintrag ohne Mitarbeiter: 409 mit Hinweis auf „Einzeln zuordnen“', st == 409 and 'Einzeln zuordnen' in r.get('error', ''), r)
check('Zuordnen ohne Personalrecht: 403', L.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': ids['mara'], 'rev': rev})[0] == 403)
check('Zuordnen: unbekannter Mitarbeiter 422, veralteter Stand 409', P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': 'u-gibt-es-nicht', 'rev': rev})[0] == 422
      and P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': ids['mara'], 'rev': rev - 1})[0] == 409)
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': ids['mara'], 'rev': rev})
check('Überschneidung mit vorhandener Abwesenheit: 409, nichts geändert', st == 409 and 'Überschneidende' in r.get('error', '')
      and 'pmarlene' in [p_['id'] for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['altbestand']], r)
assert P.call('hr_eintrag_save', {'id': UEBER, 'stornieren': True})[0] == 200
anzahl_vorher = len(dokument('hr-abwesenheiten')['eintraege'])
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': ids['mara'], 'rev': rev})
check('zusammengeführt: 2 Abwesenheiten übernommen, 1 doppelte storniert', st == 200 and r['abwesenheiten'] == 2 and r['doppelt'] == 1, (st, r))
v = P.call('mitarbeiter_hr')[1]
pm = {p_['id']: p_ for p_ in v['personen']}[PM]
check('… Angaben: Mitarbeiter gilt, leere Felder aus dem Eintrag (Personalnummer, Übertrag, Vorjahr)', pm['personalnummer'] == '9901' and pm['abteilung'] == 'Vertrieb'
      and pm['jahre'][str(Y)] == {'anspruch': 20, 'uebertrag': 3} and pm['jahre'][str(Y - 1)]['anspruch'] == 24 and pm['nutzer'] == ids['mara'], pm)
check('… Eintrag ohne Mitarbeiter verschwunden', 'pmarlene' not in [p_['id'] for p_ in v['personen']])
abw = dokument('hr-abwesenheiten')['eintraege']
am = {e['id']: e for e in abw if e['id'] in ('am1', 'am2', 'am3')}
check('… Abwesenheiten beim Mitarbeiter, doppelte storniert mit Grund, nichts gelöscht', len(abw) == anzahl_vorher and all(e['person'] == PM for e in am.values())
      and am['am1']['status'] == 'storniert' and 'doppelt' in am['am1']['entscheidung']['grund'] and am['am2']['status'] == 'genehmigt', am)
check('… im Protokoll', 'Eintrag der Urlaubsliste „Marlene Konto-Alt“ dem Mitarbeiter Mara Konto zugeordnet' in json.dumps(A.call('log')[1], ensure_ascii=False))
rev = v['rev']
check('schon zugeordneter Eintrag: 404', P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene', 'nutzer': ids['mara'], 'rev': rev})[0] == 404)
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene2', 'nutzer': ids['mara'], 'rev': rev})
check('unterschiedliche Personalnummern: 409', st == 409 and 'Personalnummern' in r.get('error', ''), r)
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pmarlene2', 'nutzer': ids['nina'], 'rev': rev})
v = P.call('mitarbeiter_hr')[1]
pn = [p_ for p_ in v['personen'] if p_['nutzer'] == ids['nina']]
check('Mitarbeiter ohne HR-Angaben: Eintrag wird seine Person (Personalnummer bleibt)', st == 200 and len(pn) == 1 and pn[0]['id'] == 'pmarlene2' and pn[0]['personalnummer'] == '9902', (st, r, pn))
rev = v['rev']
hr(ids['mara'], aktiv=False); hr(ids['nina'], aktiv=False)

# ── Verwaiste Einträge: verknüpfter Mitarbeiter gelöscht bzw. zweiter Eintrag desselben Mitarbeiters (Fehler aus dem Betrieb
#    26.10.2026: „schon einem Mitarbeiter zugeordnet“, obwohl der Eintrag als „ohne Mitarbeiter“ angezeigt wurde) ──
for u, n in (('paula', 'Paula Platz'), ('quentin', 'Quentin Quer')):
    assert A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': 'Urlaub-Konto-4711', 'mustChange': False})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
alt = dokument('hr-personal')
alt['personen'] += [{'id': 'pverwaist', 'nutzer': 'u-geloescht-1', 'vorname': 'Paula', 'nachname': 'Alt', 'abteilung': 'Lager', 'pos': 44, 'aktiv': True, 'personalnummer': '9910'},
                    {'id': 'pdoppel', 'nutzer': ids['erika'], 'vorname': 'Erika', 'nachname': 'Doppelt', 'abteilung': '', 'pos': 45, 'aktiv': True},
                    {'id': 'pquentin', 'nutzer': 'u-geloescht-2', 'vorname': 'Quentin', 'nachname': 'Quer', 'abteilung': 'Lager', 'pos': 46, 'aktiv': True}]
alt['rev'] = alt.get('rev', 0) + 1
storage_write('hr-personal', alt)
ab = dokument('hr-abwesenheiten')
ab['eintraege'].append({'id': 'av1', 'person': 'pverwaist', 'art': 'U', 'von': iso(montag(Y, 9, 2)), 'bis': iso(montag(Y, 9, 2)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'zeiterfassung'})
ab['rev'] = ab.get('rev', 0) + 1
storage_write('hr-abwesenheiten', ab)
v = P.call('mitarbeiter_hr')[1]
rev = v['rev']
altb = sorted(p_['id'] for p_ in v['personen'] if p_['altbestand'])
check('verwaiste Einträge erscheinen als „ohne Mitarbeiter“ (gelöschter Mitarbeiter, zweiter Eintrag)', altb == ['pdoppel', 'phans2', 'pkarl', 'pquentin', 'pverwaist'], altb)
pe_vorher = {p_['id']: p_ for p_ in v['personen']}[PE]
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pverwaist', 'nutzer': ids['paula'], 'rev': rev})
v = P.call('mitarbeiter_hr')[1]
pp = [p_ for p_ in v['personen'] if p_['nutzer'] == ids['paula']]
check('Eintrag eines gelöschten Mitarbeiters zuordnen (Mitarbeiter ohne Angaben): ok, Personalnummer und Urlaub kommen mit', st == 200
      and len(pp) == 1 and pp[0]['id'] == 'pverwaist' and pp[0]['personalnummer'] == '9910' and r['abwesenheiten'] == 1, (st, r, pp))
rev = v['rev']
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'pdoppel', 'nutzer': ids['erika'], 'rev': rev})
v = P.call('mitarbeiter_hr')[1]
pe = {p_['id']: p_ for p_ in v['personen']}.get(PE, {})
check('zweiter Eintrag desselben Mitarbeiters: in seine Angaben zusammengeführt, Angaben unverändert', st == 200 and 'pdoppel' not in [p_['id'] for p_ in v['personen']]
      and pe.get('abteilung') == pe_vorher['abteilung'] and pe.get('jahre') == pe_vorher['jahre'], (st, r))
st, r = P.call('hr_personal_uebernehmen', {})
v = P.call('mitarbeiter_hr')[1]
pq = [p_ for p_ in v['personen'] if p_['nutzer'] == ids['quentin']]
check('„Gleichnamige zuordnen“ erfasst auch verwaiste Einträge', st == 200 and r['anzahl'] == 1 and len(pq) == 1 and pq[0]['id'] == 'pquentin'
      and sorted(p_['id'] for p_ in v['personen'] if p_['altbestand']) == ['phans2', 'pkarl'], (r, pq))
rev = v['rev']
hr(ids['paula'], aktiv=False); hr(ids['quentin'], aktiv=False)

# ── Vier-Augen-Prinzip auch bei Angaben, Zuordnung und Importen (Sicherheitsdurchsicht 26.10.2026) ──
for u, n, g in (('pia', 'Pia Personal', ['hr.verwalten']), ('olga', 'Olga Protokoll', ['protokoll.sehen'])):
    assert A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'viewer', 'active': True, 'password': 'Urlaub-Konto-4711', 'mustChange': False, 'grant': g})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
PI = Client('198.51.100.10'); PI.call('login', {'username': 'pia', 'password': 'Urlaub-Konto-4711'})
OL = Client('198.51.100.11'); OL.call('login', {'username': 'olga', 'password': 'Urlaub-Konto-4711'})
# (a) eigene Urlaubsangaben
v = P.call('mitarbeiter_hr')[1]
rev = v['rev']
pp = {p_['nutzer']: p_ for p_ in v['personen'] if p_['nutzer']}[ids['paul']]
nein = []
for werte in ({'jahr': Y, 'anspruch': 99}, {'jahr': Y, 'uebertrag': 5}, {'arbeitstage': [1, 2, 3]}, {'aktiv': not pp['aktiv']}, {'personalnummer': '777'}, {'verfall': not pp['verfall']}):
    st, r = P.call('mitarbeiter_hr_save', {'nutzer': ids['paul'], 'rev': rev, **werte})
    nein.append((st, 'andere Person' in r.get('error', '')))
check('eigene Urlaubsangaben (Anspruch, Übertrag, Arbeitstage, Urlaubsplan, Personalnummer, Verfall): 403', nein == [(403, True)] * 6, nein)
st, r = P.call('mitarbeiter_hr_save', {'nutzer': ids['paul'], 'rev': rev, 'abteilung': 'Personal', 'pos': 9, 'personalnummer': pp['personalnummer'],
                                        'arbeitstage': pp['arbeitstage'], 'aktiv': pp['aktiv'], 'verfall': pp['verfall'], 'jahr': Y, 'anspruch': '', 'uebertrag': ''})
check('… Abteilung und Position der eigenen Person bleiben änderbar (Dialog schickt unveränderte Werte mit)', st == 200 and r['person']['abteilung'] == 'Personal'
      and r['person']['jahre'] == pp['jahre'], (st, r))
rev = r['rev']
st, r = A.call('mitarbeiter_hr_save', {'nutzer': ids['paul'], 'rev': rev, 'jahr': Y, 'anspruch': 25})
check('… eine andere Person (Administrator) ändert sie', st == 200 and r['person']['jahre'][str(Y)]['anspruch'] == 25, (st, r))
rev = r['rev']
# (b) Zuordnung ehemaliger Mitarbeiter
alt = dokument('hr-personal')
alt['personen'] += [{'id': 'ppia', 'vorname': 'Pia', 'nachname': 'Personal', 'abteilung': 'Personal', 'pos': 47, 'aktiv': True},
                    {'id': 'ppaulalt', 'vorname': 'Paul', 'nachname': 'Früher', 'abteilung': 'Personal', 'pos': 48, 'aktiv': True}]
alt['rev'] = alt.get('rev', 0) + 1
storage_write('hr-personal', alt)
ab = dokument('hr-abwesenheiten')
ab['eintraege'] += [{'id': 'apia', 'person': 'ppia', 'art': 'U', 'von': iso(montag(Y, 12, 1)), 'bis': iso(montag(Y, 12, 1)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'personalstelle'},
                    {'id': 'apaul', 'person': 'ppaulalt', 'art': 'U', 'von': iso(montag(Y, 12, 1)), 'bis': iso(montag(Y, 12, 1)), 'status': 'genehmigt', 'notiz': '', 'quelle': 'personalstelle'}]
ab['rev'] = ab.get('rev', 0) + 1
storage_write('hr-abwesenheiten', ab)
rev = P.call('mitarbeiter_hr')[1]['rev']
st, r = P.call('hr_altbestand_zuordnen', {'eintrag': 'ppaulalt', 'nutzer': ids['paul'], 'rev': rev})
check('Eintrag sich selbst zuordnen: 403', st == 403 and 'andere Person' in r.get('error', ''), (st, r))
st, r = A.call('hr_altbestand_zuordnen', {'eintrag': 'ppaulalt', 'nutzer': ids['paul'], 'rev': rev})
check('… eine andere Person ordnet zu', st == 200 and r['abwesenheiten'] == 1, (st, r))
st, r = PI.call('hr_personal_uebernehmen', {})
altb = [p_['id'] for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['altbestand']]
check('„Gleichnamige zuordnen“ trifft nie die eigene Person', st == 200 and r['anzahl'] == 0 and 'ppia' in altb, (r, altb))
st, r = P.call('hr_personal_uebernehmen', {})
pv = {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}
check('… eine andere Person ordnet gleichnamig zu', st == 200 and r['anzahl'] == 1 and pv[ids['pia']]['id'] == 'ppia', r)
# (c) Importe: eigene Zeilen werden nicht übernommen, der Rest schon
NOV = montag(Y, 11, 2)
ser = lambda d: (dt.datetime(d.year, d.month, d.day) - dt.datetime(1899, 12, 30)).days
KOPF = ['Vorname', 'Nachname', 'Name (Abwesenheit)', 'Abwesenheitsvergütung', 'Startdatum', 'Enddatum', 'Dauer', 'Mitarbeiternummer', 'Zweite Mitarbeiternummer', 'Abteilung', 'Standort', 'Gesamt']
def person_zeile(v, n): return [v, n, None, None, None, None, None, '', None, 'Personal', 'STAFL', '16:00']
def urlaub(d1, d2): return [None, None, 'Urlaub ', 'Bezahlte Abwesenheit', ser(d1), ser(d2), '16:00', None, None, None, None, None]
DZ = {'blaetter': [{'name': 'Bericht', 'grid': [KOPF, person_zeile('Pia', 'Personal'), urlaub(NOV, NOV + dt.timedelta(days=1)),
                                                person_zeile('Quentin', 'Quer'), urlaub(NOV + dt.timedelta(days=2), NOV + dt.timedelta(days=3))]}]}
def zimp(cl, uebernehmen=False, stand=None):
    b = {'art': 'zeiterfassung', 'daten': DZ, 'quelle': 'test.xlsx', 'optionen': {}}
    if uebernehmen: b['stand'] = stand
    return cl.call('import_uebernehmen' if uebernehmen else 'import_pruefen', b)
st, v = zimp(PI)
eig = [z for z in v.get('zeilen', []) if z['name'] == 'Pia Personal' and z['art'] == 'fehler']
neu = [z['name'] for z in v.get('zeilen', []) if z['art'] == 'neu' and z['schluessel'] == 'Abwesenheiten']
check('Zeiterfassung: eigene Zeilen in der Vorschau als „eigene Person“ markiert, Rest wird übernommen', st == 200 and eig and 'eigene Person' in eig[0]['text'] and neu == ['Quentin Quer'], (st, v.get('zeilen')))
st, _ = zimp(PI, True, v['stand'])
ze = lambda name: [e for e in P.call('hr_verwaltung&jahr=' + str(Y))[1]['eintraege'] if e['name'] == name and e['quelle'] == 'zeiterfassung' and e['von'] >= iso(NOV)]
check('… übernommen: Quentin ja, eigene nicht', st == 200 and len(ze('Quentin Quer')) == 1 and ze('Pia Personal') == [], (ze('Quentin Quer'), ze('Pia Personal')))
st, v = zimp(P)
st, _ = zimp(P, True, v['stand'])
check('… eine andere Person übernimmt die Zeile', st == 200 and len(ze('Pia Personal')) == 1 and len(ze('Quentin Quer')) == 1)
st, v = zimp(PI)
check('… eigene frühere Übernahme wird bei erneutem Import nicht ersetzt', st == 200 and v['zahlen']['entfaellt'] == 1, v['zahlen'])
# Excel-Planung (Urlaubsplanung) gibt es nicht mehr: weder als Importart noch als Aktion
weg = (PI.call('import_pruefen', {'art': 'urlaubsplanung', 'daten': {'blaetter': []}}), P.call('hr_import_pruefen', {'daten': {'blaetter': []}})[0],
       P.call('hr_import_uebernehmen', {'daten': {'blaetter': []}})[0], [x['id'] for x in P.call('import_arten')[1]['arten']])
check('Excel-Planung entfernt: Importart unbekannt (404), Aktionen hr_import_* unbekannt (404), nicht in der Importzentrale',
      weg[0][0] == 404 and 'Importart' in weg[0][1].get('error', '') and weg[1] == 404 and weg[2] == 404 and 'urlaubsplanung' not in weg[3] and 'zeiterfassung' in weg[3], weg)
# Protokoll: Vorgänge der Urlaubsverwaltung ohne „HR verwalten“ nur als Vorgang
st, r = OL.call('log')
hr_e = [e for e in r.get('entries', []) if e.get('a') == 'hr']
check('Protokoll ohne HR-Recht: Vorgänge der Urlaubsverwaltung maskiert (keine Namen, keine Zeiträume)', st == 200 and hr_e and all(e.get('masked') and e['s'] == 'Vorgang der Urlaubsverwaltung' for e in hr_e)
      and 'Quentin' not in json.dumps(hr_e, ensure_ascii=False), hr_e[:2])
check('… mit HR-Recht (Administrator) vollständig', any(e.get('a') == 'hr' and not e.get('masked') and 'Urlaubsliste' in e['s'] for e in A.call('log')[1]['entries']))
rev = P.call('mitarbeiter_hr')[1]['rev']
hr(ids['pia'], aktiv=False)

# ── Excel-Export ──
# Lena nicht mehr im Urlaubsplan (z. B. ausgeschieden): im Februar (genehmigte Krankheit) weiter im Export, im August nicht
hr(ids['lena'], aktiv=False)
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
check('nicht mehr im Urlaubsplan: nur in Monaten mit genehmigten Abwesenheiten im Export', 'Lena Leser' in zeile and 'Lena Leser' not in z8, (sorted(zeile), sorted(z8)))
hr(ids['lena'], aktiv=True)
check('Export ohne Monat: 422', P.call('hr_export', {'jahr': Y, 'monate': []})[0] == 422)

# ── Verfallstag des Resturlaubs einstellbar (Verwaltung → Urlaub; Standard 31.03.) ──
assert A.call('user_save', {'id': '', 'name': 'Fritz Frist', 'username': 'fritz', 'role': 'viewer', 'active': True, 'password': 'Urlaub-Konto-4711', 'mustChange': False})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
rev = P.call('mitarbeiter_hr')[1]['rev']
PF = hr(ids['fritz'], abteilung='Lager', pos=50, jahr=Y, anspruch=20, uebertrag=5)
APR = montag(Y, 4, 2)
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'U', 'von': iso(APR), 'bis': iso(APR + dt.timedelta(days=4))})
NAPR = r['eintrag']['tage']
konto_f = lambda: next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={Y}')[1]['personen'] if p_['id'] == PF)['konto']
v = P.call('mitarbeiter_hr')[1]
check('Standard: Verfallstag 31.03.', v['uebertragBis'] == '03-31' and E.call('hr_start')[1]['uebertragBis'] == '03-31', v.get('uebertragBis'))
k = konto_f()
check('… Urlaub im April verbraucht den Übertrag nicht (verfällt ganz)', k['frist'] == f'{Y}-03-31' and k['verfaellt'] == 5, k)
einst = {'sperren': v['sperren'], 'ferien': v['ferien']}
for falsch in ('02-29', f'{Y}-13-01', '31.04.', 'x'):
    st, r = P.call('hr_einstellungen_save', {**einst, 'uebertragBis': falsch})
    check(f'ungültiger Verfallstag {falsch}: 422', st == 422 and 'Verfallstag' in r.get('error', ''), (st, r))
check('ohne Personalrecht: 403', L.call('hr_einstellungen_save', {**einst, 'uebertragBis': '04-30'})[0] == 403)
st, r = P.call('hr_einstellungen_save', {**einst, 'uebertragBis': f'{Y}-04-30'})
check('Verfallstag 30.04. gespeichert (aus dem Datumsfeld nur Tag und Monat)', st == 200 and r['uebertragBis'] == '04-30', r)
k = konto_f()
check('… Konto: Frist 30.04., Urlaub im April verbraucht den Übertrag zuerst', k['frist'] == f'{Y}-04-30' and k['verfaellt'] == max(0, 5 - NAPR), (k, NAPR))
check('… gilt überall (Start, Verwaltung, Übersicht)', E.call('hr_start')[1]['uebertragBis'] == '04-30'
      and P.call(f'hr_uebersicht&jahr={Y}')[1]['uebertragBis'] == '04-30')
st, r = P.call('hr_einstellungen_save', einst)
check('Speichern ohne Verfallstag lässt ihn unverändert', st == 200 and r['uebertragBis'] == '04-30' and P.call('mitarbeiter_hr')[1]['uebertragBis'] == '04-30', r)
check('Änderung im Protokoll', 'Verfallstag Resturlaub auf 30.04. geändert' in json.dumps(A.call('log')[1], ensure_ascii=False))
st, r = P.call('hr_einstellungen_save', {**einst, 'uebertragBis': '03-31'})
check('Rückweg auf 31.03.', st == 200 and r['uebertragBis'] == '03-31' and konto_f()['verfaellt'] == 5, r)

# ── Übergangsregel „Verfällt erstmals“ (Inhaber 03.11.2026: im ersten Jahr wird nichts gestrichen, erst im Jahr danach) ──
v = P.call('mitarbeiter_hr')[1]
check('Übergangsregel: Standard jedes Jahr (verfallAb null)', v['verfallAb'] is None, v.get('verfallAb'))
falsch = [P.call('hr_einstellungen_save', {**einst, 'verfallAb': w})[0] for w in (str(Y), 1999, 2101, Y + 0.5, True)]
check('… nur eine Jahreszahl 2000–2100 oder null: sonst 422', falsch == [422] * 5, falsch)
check('… ohne Personalrecht 403', L.call('hr_einstellungen_save', {**einst, 'verfallAb': Y + 1})[0] == 403 and P.call('mitarbeiter_hr')[1]['verfallAb'] is None)
k0 = konto_f()
k0n = next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={Y + 1}')[1]['personen'] if p_['id'] == PF)['konto']
st, r = P.call('hr_einstellungen_save', {**einst, 'verfallAb': Y + 1})
k = konto_f()
kn = next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={Y + 1}')[1]['personen'] if p_['id'] == PF)['konto']
check(f'verfällt erstmals {Y + 1}: in {Y} verfällt nichts (Konto ohne Verfall), Rest unverändert', st == 200 and r['verfallAb'] == Y + 1 and k['verfall'] is False
      and k['verfaellt'] == 0 and k['verfallen'] == 0 and k['rest'] == k0['rest'] and k0['verfaellt'] == 5, (r.get('verfallAb'), k))
check(f'… {Y + 1}: Übertrag um den sonst verfallenen Rest höher, Verfall gilt dort wieder', kn['uebertrag'] == k0n['uebertrag'] + 5 and kn['verfall'] is True, (kn, k0n))
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
check('… Protokoll nennt den ersten Verfall', f'Resturlaub verfällt erstmals am 31.03.{Y + 1}' in log_)
st, r = P.call('hr_einstellungen_save', einst)
check('… Speichern ohne Angabe lässt die Regel unverändert', st == 200 and r['verfallAb'] == Y + 1 and P.call('mitarbeiter_hr')[1]['verfallAb'] == Y + 1)
check('… gilt auch für die Startseite und die Übersicht (Konto ohne Verfall)', next(z for z in P.call(f'hr_uebersicht&jahr={Y}')[1]['zeilen'] if z['id'] == PF)['verfaellt'] == 0)
st, r = P.call('hr_einstellungen_save', {**einst, 'verfallAb': Y})
check(f'verfällt erstmals {Y}: Verfall in {Y} wie ohne Regel', st == 200 and konto_f()['verfaellt'] == 5)
st, r = P.call('hr_einstellungen_save', {**einst, 'verfallAb': None})
check('… zurück auf „jedes Jahr“ (null), Protokoll', st == 200 and r['verfallAb'] is None and konto_f()['verfaellt'] == 5
      and 'Resturlaub verfällt jedes Jahr' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ── Resturlaub verfällt je Mitarbeiter abschaltbar (Verwaltung → Mitarbeiter; Inhaber 03.11.2026, Standard: verfällt) ──
person_f = lambda j=Y: next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={j}')[1]['personen'] if p_['id'] == PF)   # noqa: E731
check('Standard: Resturlaub verfällt (Angabe und Konto)', person_f()['verfall'] is True and konto_f()['verfall'] is True)
k0, k0n = konto_f(), person_f(Y + 1)['konto']
rev = P.call('mitarbeiter_hr')[1]['rev']
falsch = [P.call('mitarbeiter_hr_save', {'nutzer': ids['fritz'], 'rev': rev, 'verfall': w}) for w in ('nein', 0, None)]
check('Verfall nur ja/nein: sonst 422, nichts gespeichert', all(st == 422 and 'Resturlaub verfällt' in r.get('error', '') for st, r in falsch)
      and person_f()['verfall'] is True, [x[0] for x in falsch])
check('… ohne Personalrecht 403', L.call('mitarbeiter_hr_save', {'nutzer': ids['fritz'], 'rev': rev, 'verfall': False})[0] == 403)
hr(ids['fritz'], verfall=False)
k, kn = konto_f(), person_f(Y + 1)['konto']
check('ohne Verfall: nichts verfällt, der Übertrag bleibt ganz (Rest unverändert)', person_f()['verfall'] is False and k['verfall'] is False
      and k['verfaellt'] == 0 and k['verfallen'] == 0 and k['rest'] == k0['rest'] and k['uebertrag'] == 5, k)
check('… Folgejahr: Übertrag enthält den sonst verfallenen Rest', kn['uebertrag'] == k0n['uebertrag'] + 5 and k0n['uebertrag'] == k0['rest_jahresende'], (kn, k0n))
check('… Protokoll nennt die Änderung', 'Resturlaub verfällt nicht mehr' in json.dumps(A.call('log')[1], ensure_ascii=False))
hr(ids['fritz'], abteilung='Lager')
check('… Speichern ohne Angabe lässt den Verfall unverändert', person_f()['verfall'] is False)
hr(ids['fritz'], verfall=True)
check('… wieder einschalten: verfällt wie vorher, Protokoll', konto_f()['verfaellt'] == 5 and person_f(Y + 1)['konto']['uebertrag'] == k0n['uebertrag']
      and 'Resturlaub verfällt wieder am Verfallstag' in json.dumps(A.call('log')[1], ensure_ascii=False))
# vergangenes Jahr: schon verfallener Übertrag kommt zurück (das Konto wird berechnet, gilt für alle Jahre)
kl = lambda j: next(p_ for p_ in P.call(f'hr_verwaltung&jahr={j}')[1]['personen'] if p_['id'] == PL)['konto']   # noqa: E731
v25, v26 = kl(2025), kl(2026)
hr(ids['lena'], verfall=False)
n25, n26 = kl(2025), kl(2026)
check('ohne Verfall rückwirkend: 2025 nichts verfallen, Rest und Übertrag 2026 um den Verfall höher', v25['verfallen'] > 0 and n25['verfallen'] == 0
      and n25['rest'] == v25['rest'] + v25['verfallen'] and n26['uebertrag'] == v26['uebertrag'] + v25['verfallen'], (v25, n25, v26['uebertrag'], n26['uebertrag']))
hr(ids['lena'], verfall=True)
check('… zurückgesetzt', kl(2025)['verfallen'] == v25['verfallen'])

# ── Schalter „Urlaubsanträge über die Plattform“ (Verwaltung → Urlaub; Inhaber 30.10.2026, Standard an) ──
F = Client('198.51.100.31'); assert F.call('login', {'username': 'fritz', 'password': 'Urlaub-Konto-4711'})[0] == 200
JUN = montag(Y, 6, 2)
check('Standard: Urlaubsanträge eingeschaltet (Start und Verwaltung)', F.call('hr_start')[1]['antraege'] is True and P.call('mitarbeiter_hr')[1]['antraege'] is True)
st, r = F.call('hr_antrag', {'von': iso(JUN), 'bis': iso(JUN + dt.timedelta(days=1))})
check('… Antrag möglich', st == 200, (st, r))
OFFEN_F = r['eintrag']['id']
check('Schalter: ohne Personalrecht 403, ohne Anmeldung 401', L.call('hr_antraege_save', {'an': False})[0] == 403 and E.call('hr_antraege_save', {'an': False})[0] == 403
      and N.call('hr_antraege_save', {'an': False})[0] == 401)
check('Schalter: nur ja/nein (422)', all(P.call('hr_antraege_save', b)[0] == 422 for b in ({}, {'an': 'nein'}, {'an': 0}, {'an': None})))
einst_vorher = dokument('hr-einstellungen')
st, r = P.call('hr_antraege_save', {'an': False})
check('Personalstelle schaltet Urlaubsanträge aus', st == 200 and r['antraege'] is False, (st, r))
check('… Start und Verwaltung melden „aus“', F.call('hr_start')[1]['antraege'] is False and P.call('mitarbeiter_hr')[1]['antraege'] is False)
einst_nachher = dokument('hr-einstellungen')
check('… Sperren, Ferien und Verfallstag bleiben unverändert (nur das Feld antraege, GR-006)',
      {k: v_ for k, v_ in einst_nachher.items() if k not in ('rev', 'antraege')} == {k: v_ for k, v_ in einst_vorher.items() if k not in ('rev', 'antraege')}
      and einst_nachher['antraege'] is False, (einst_vorher, einst_nachher))
st, r = F.call('hr_antrag', {'von': iso(JUN + dt.timedelta(days=3)), 'bis': iso(JUN + dt.timedelta(days=3))})
check('ausgeschaltet: neuer Antrag 409 mit Hinweis auf die Personalstelle (serverseitig, GR-103)', st == 409 and 'nicht über die Plattform' in r.get('error', ''), (st, r))
check('… nichts gespeichert', not [e for e in dokument('hr-abwesenheiten')['eintraege'] if e['person'] == PF and e['von'] == iso(JUN + dt.timedelta(days=3))])
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'K', 'von': iso(JUN + dt.timedelta(days=7)), 'bis': iso(JUN + dt.timedelta(days=7))})
check('… Personalstelle trägt weiter ein', st == 200, (st, r))
check('… offener Antrag lässt sich weiter zurückziehen', F.call('hr_antrag_zurueckziehen', {'id': OFFEN_F})[0] == 200)
check('… Sperren und Ferien speichern schaltet nicht wieder ein', P.call('hr_einstellungen_save', einst)[0] == 200 and F.call('hr_start')[1]['antraege'] is False)
check('… nochmal „aus“: kein doppelter Protokolleintrag', P.call('hr_antraege_save', {'an': False})[0] == 200
      and json.dumps(A.call('log')[1], ensure_ascii=False).count('Urlaubsanträge über die Plattform ausgeschaltet') == 1)
st, r = P.call('hr_antraege_save', {'an': True})
st2, r2 = F.call('hr_antrag', {'von': iso(JUN + dt.timedelta(days=3)), 'bis': iso(JUN + dt.timedelta(days=3))})
check('wieder eingeschaltet: Antrag möglich, Protokoll', st == 200 and r['antraege'] is True and st2 == 200
      and 'Urlaubsanträge über die Plattform eingeschaltet' in json.dumps(A.call('log')[1], ensure_ascii=False), (st2, r2))
assert F.call('hr_antrag_zurueckziehen', {'id': r2['eintrag']['id']})[0] == 200   # keine offenen Anträge für die folgenden Prüfungen

# ── Krankheit zählt nie gegen den Urlaub (Inhaber 30.10.2026) – auch mit „vom Urlaub abgezogen“ aus der Zeiterfassung ──
vorher_k = konto_f()
ab = dokument('hr-abwesenheiten')
ab['eintraege'].append({'id': 'kabzug', 'person': PF, 'art': 'K', 'von': iso(JUN + dt.timedelta(days=8)), 'bis': iso(JUN + dt.timedelta(days=9)),
                        'status': 'genehmigt', 'notiz': '', 'quelle': 'zeiterfassung', 'urlaubAbzug': True})
ab['rev'] = ab.get('rev', 0) + 1
storage_write('hr-abwesenheiten', ab)
k = konto_f()
check('Krank (auch „vom Urlaub abgezogen“) ändert das Urlaubskonto nicht', (k['genommen'], k['geplant'], k['rest']) == (vorher_k['genommen'], vorher_k['geplant'], vorher_k['rest']), (vorher_k, k))
check('… Hinweis bleibt für die Personalstelle sichtbar', next(e for e in P.call(f'hr_verwaltung&jahr={Y}')[1]['eintraege'] if e['id'] == 'kabzug')['urlaubAbzug'] is True)

# ── Korrektur melden (Mitarbeiter → Personalstelle, Inhaber 30.10.2026) ──
KF = next(e for e in F.call(f'hr_start&jahr={Y}')[1]['eintraege'] if e['art'] == 'K' and e['von'] == iso(JUN + dt.timedelta(days=7)))
fremd = next(e for e in P.call(f'hr_verwaltung&jahr={Y}')[1]['eintraege'] if e['person'] != PF)
check('Korrektur: ohne Anmeldung 401, nicht im Urlaubsplan 409', N.call('hr_korrektur', {'text': 'Bitte prüfen'})[0] == 401
      and O.call('hr_korrektur', {'text': 'Bitte prüfen'})[0] == 409)
check('Korrektur: Text zu kurz, ungültiges Datum, Ende vor Beginn 422', F.call('hr_korrektur', {'text': 'x'})[0] == 422
      and F.call('hr_korrektur', {'text': 'Bitte prüfen', 'von': f'{Y}-13-01'})[0] == 422
      and F.call('hr_korrektur', {'text': 'Bitte prüfen', 'von': iso(JUN), 'bis': iso(JUN - dt.timedelta(days=1))})[0] == 422)
check('Korrektur: Eintrag einer anderen Person 404', F.call('hr_korrektur', {'text': 'Bitte prüfen', 'eintrag': fremd['id']})[0] == 404)
st, r = F.call('hr_korrektur', {'text': 'Am Tag war ich nicht krank, sondern im Urlaub.', 'von': KF['von'], 'bis': KF['bis'], 'eintrag': KF['id']})
check('Korrektur zu einem eigenen Eintrag gemeldet (offen)', st == 200 and r['meldung']['status'] == 'offen' and r['meldung']['eintrag'] == KF['id'] and r['meldung']['von'] == KF['von'], (st, r))
K1 = r['meldung']['id']
st, r = F.call('hr_korrektur', {'text': 'Mein Übertrag aus dem Vorjahr fehlt.'})
check('Korrektur ohne Zeitraum gemeldet', st == 200 and r['meldung']['von'] is None, (st, r))
K2 = r['meldung']['id']
s_ = F.call(f'hr_start&jahr={Y}')[1]
check('Start: eigene Meldungen (neueste zuerst), keine Zahl für Mitarbeiter ohne Personalrecht', [m['id'] for m in s_['korrekturen']][:2] == [K2, K1] and s_['korrekturenOffen'] is None, s_.get('korrekturen'))
check('Start der Personalstelle: Zahl offener Meldungen', P.call('hr_start')[1]['korrekturenOffen'] == 2)
check('Erledigen: ohne Personalrecht 403', E.call('hr_korrektur_erledigt', {'id': K1})[0] == 403 and L.call('hr_korrektur_erledigt', {'id': K1})[0] == 403)
kv = {m['id']: m for m in P.call(f'hr_verwaltung&jahr={Y}')[1]['korrekturen']}
check('Personalstelle sieht die Meldungen mit Name, Text und Bezug', kv[K1]['name'] == 'Fritz Frist' and 'nicht krank' in kv[K1]['text'] and kv[K1]['eigen'] is False and K2 in kv, kv.get(K1))
st, r = P.call('hr_korrektur_erledigt', {'id': K1, 'antwort': 'Auf Urlaub korrigiert.'})
check('Personalstelle erledigt mit Antwort', st == 200 and r['meldung']['status'] == 'erledigt' and r['meldung']['erledigt']['antwort'] == 'Auf Urlaub korrigiert.', (st, r))
check('… nochmal erledigen 409, unbekannt 404', P.call('hr_korrektur_erledigt', {'id': K1})[0] == 409 and P.call('hr_korrektur_erledigt', {'id': 'kgibtsnicht'})[0] == 404)
m1 = next(m for m in F.call('hr_start')[1]['korrekturen'] if m['id'] == K1)
check('… Mitarbeiter sieht „erledigt“ und die Antwort', m1['status'] == 'erledigt' and m1['erledigt']['antwort'] == 'Auf Urlaub korrigiert.' and 'byId' not in m1['erledigt'], m1)
kd = dokument('hr-korrekturen')
kd['meldungen'].append({'id': 'kpaul', 'person': ids['paul'], 'text': 'Eigene Meldung', 'status': 'offen', 'erfasst': {'t': '2026-10-30T08:00:00Z', 'by': 'Paul Personal', 'byId': ids['paul']}})
kd['rev'] = kd.get('rev', 0) + 1
storage_write('hr-korrekturen', kd)
check('Vier-Augen-Prinzip: eigene Meldung erledigt nicht die Personalstelle selbst (403), eine andere Person schon',
      P.call('hr_korrektur_erledigt', {'id': 'kpaul'})[0] == 403 and next(m for m in P.call('hr_verwaltung')[1]['korrekturen'] if m['id'] == 'kpaul')['eigen'] is True
      and A.call('hr_korrektur_erledigt', {'id': 'kpaul'})[0] == 200)
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Meldung und Erledigung ohne den Text', 'HR: Korrektur gemeldet' in log_ and 'HR: Korrekturmeldung erledigt (Fritz Frist)' in log_ and 'nicht krank' not in log_)
offen_f = 1
while True:
    st, r = F.call('hr_korrektur', {'text': f'Meldung {offen_f}'})
    if st != 200: break
    offen_f += 1
check('höchstens 20 offene Meldungen je Person (429)', st == 429 and offen_f == 20, (st, offen_f))
for m in P.call('hr_verwaltung')[1]['korrekturen']:   # aufräumen: alle offenen erledigen
    if m['status'] == 'offen': assert P.call('hr_korrektur_erledigt', {'id': m['id']})[0] == 200
rev = P.call('mitarbeiter_hr')[1]['rev']
hr(ids['fritz'], aktiv=False)

# ── Oberfläche: Testdaten 2025, Zeiterfassung, Verwaltung (im Browser) ──
fehler = []
# ── E-Mails der Urlaubsverwaltung (Inhaber 03.11.2026): Erinnerung, Monatsübersicht, Steuerberater, Testmodus, Automatik ──
smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
MAIL_HTML = {}   # HTML-Fassungen der Mails, unten im Browser als Bild geprüft (600 px und 390 px)


def mail_html(m_):
    for t_ in m_['msg'].walk():
        if t_.get_content_type() == 'text/html':
            return t_.get_payload(decode=True).decode(t_.get_content_charset() or 'utf-8')
    return ''


uu = {u['username']: u for u in A.call('users')[1]['users']}
for un_, adr_ in (('fritz', 'fritz@example.org'), ('erika', 'erika@example.org')):
    u_ = uu[un_]
    st, r = A.call('user_save', {'id': u_['id'], 'name': u_['name'], 'username': u_['username'], 'role': u_['role'], 'active': u_['active'], 'email': adr_})
    assert st == 200, r
F_AKTIV = next(p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['id'] == PF)['aktiv']
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['fritz'], aktiv=True)   # Fritz für diesen Abschnitt im Urlaubsplan (am Ende wie vorher)
heute_ = dt.date.today()
VOR = (heute_.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
DIES = heute_.replace(day=1)
ym = lambda d: d.strftime('%Y-%m')   # noqa: E731
MON = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
mtext = lambda d: f'{MON[d.month - 1]} {d.year}'   # noqa: E731
# Urlaub (2 Arbeitstage) und Krankheit im Vormonat für Fritz
u1 = VOR + dt.timedelta(days=9)
while u1.weekday() > 3 or dt.date(u1.year, 1, 1) == u1: u1 += dt.timedelta(days=1)   # Mo–Do, dann zwei Tage am Stück
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'U', 'von': iso(u1), 'bis': iso(u1 + dt.timedelta(days=1))})
assert st == 200, r
U_VOR = r['eintrag']['id']; N_VOR = r['eintrag']['tage']
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'K', 'von': iso(u1 + dt.timedelta(days=7)), 'bis': iso(u1 + dt.timedelta(days=7))})
K_VOR = r['eintrag']['id'] if st == 200 else None
mv = P.call('mitarbeiter_hr')[1]['mail']
check('E-Mails ohne Postfach: Hinweis, Senden 409', mv['postfach'] is False and P.call('hr_monatsuebersicht_senden', {})[0] == 409, mv['postfach'])
konto_ = {'konto': 'intern', 'host': '127.0.0.1', 'port': SMTP_PORT, 'secure': 'none', 'user': 'portal@example.org', 'password': 'Test-Postfach-1',
          'from': 'verwaltung@example.org', 'fromName': 'STAFL Verwaltung', 'replyTo': ''}
st, r = A.call('mail_konto_save', konto_)
assert st == 200, r
mv = P.call('mitarbeiter_hr')[1]['mail']
pp_ = {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}
check('E-Mails: Standard alles aus, Postfach eingerichtet, Empfänger mit Adresse gezählt, Monate Vormonat/laufend',
      mv['einst']['monat']['an'] is False and mv['einst']['steuerberater']['an'] is False and mv['einst']['test']['an'] is False and mv['einst']['steuerberater']['tag'] == 5
      and mv['postfach'] is True and mv['empfaenger'] == 2 and mv['ohneAdresse'] > 0 and mv['monate'] == [ym(VOR), ym(DIES)],
      ({k: mv[k] for k in ('empfaenger', 'ohneAdresse', 'monate')}, [(n_, pp_[uu[n_]['id']]['aktiv']) for n_ in ('fritz', 'erika')], [u_.get('email') for u_ in A.call('users')[1]['users'] if u_['username'] in ('fritz', 'erika')]))
kein = [L.call(a_, b_)[0] for a_, b_ in (('hr_mail_save', {}), ('hr_erinnerung_senden', {}), ('hr_monatsuebersicht_senden', {}), ('hr_steuerberater_senden', {}))]
check('E-Mails: ohne Personalrecht 403 (Einstellungen und alle Knöpfe)', kein == [403] * 4, kein)
falsch_ = [P.call('hr_mail_save', b_)[0] for b_ in ({'test': {'an': True, 'adresse': ''}}, {'test': {'an': False, 'adresse': 'kein-mail'}}, {'steuerberater': {'an': True, 'adresse': ''}},
            {'steuerberater': {'adresse': 'a@example.org, b@example.org'}}, {'steuerberater': {'tag': 29}}, {'steuerberater': {'tag': '5'}}, {'monat': {'an': 'ja'}})]
check('E-Mails: Prüfungen 422 (Testadresse fehlt/ungültig, Steuerberater ohne/mit zwei Adressen, Tag 29 oder Text, ja/nein)', falsch_ == [422] * 7, falsch_)
check('Steuerberater ohne Adresse senden: 409', P.call('hr_steuerberater_senden', {})[0] == 409)
check('Erinnerung ohne verfallenden Resturlaub: 409', P.call('hr_erinnerung_senden', {})[0] == 409)
check('Monatsübersicht: ungültiger oder zukünftiger Monat 422', P.call('hr_monatsuebersicht_senden', {'monat': '2026-13'})[0] == 422
      and P.call('hr_monatsuebersicht_senden', {'monat': ym(DIES + dt.timedelta(days=40))})[0] == 422)
n0 = len(smtp.messages)
st, r = P.call('hr_monatsuebersicht_senden', {})
check('Monatsübersicht auf Knopfdruck (Vormonat): an jeden Mitarbeiter mit Adresse', st == 200 and r['ergebnis']['gesendet'] == 2 and r['ergebnis']['monat'] == ym(VOR), (st, r))
until(lambda: len(smtp.messages) >= n0 + 2)
mm = {m['to'][0]: m for m in smtp.messages[n0:]}
mf = mm.get('fritz@example.org', {})
check('… Inhalt: Urlaub im Vormonat mit Tagen, Stand im Jahr, Link – nie Krankheit', mf.get('subject') == f'Ihr Urlaub im {mtext(VOR)}' and f'{N_VOR} Tage Urlaub' in mf.get('text', '')
      and u1.strftime('%d.%m.') in mf.get('text', '') and 'Resturlaub' in mf.get('text', '') and 'hr.dashboard-stafl.de' in mf.get('text', '')
      and 'rank' not in mf.get('text', '') and 'Hallo Fritz' in mf.get('text', ''), mf.get('text', '')[:400])
check('… Erika ohne Urlaub im Vormonat: „keinen Urlaub“', 'keinen Urlaub' in mm.get('erika@example.org', {}).get('text', ''))
MAIL_HTML['monat'] = mail_html(mf)
check('… Aufbau (Inhaber 03.11.2026): Tabelle des Monats, Urlaubskonto, Jahr auf einen Blick, Knopf und Adresse des Portals',
      all(x_ in MAIL_HTML['monat'] for x_ in (f'Urlaub im {mtext(VOR)}', f'Urlaubskonto {VOR.year}', 'auf einen Blick', 'Zum Urlaubsportal', 'hr.dashboard-stafl.de', '>Jan<', '>Dez<'))
      and all(x_ in mf.get('text', '') for x_ in (f'Urlaubskonto {VOR.year}', 'Resturlaub', 'auf einen Blick', 'Urlaubsportal: https://')), mf.get('text', '')[:600])
# Erinnerung: Verfallstag in 20 Tagen, Fritz mit Übertrag im laufenden Jahr
J = heute_.year
frist_ = min(heute_ + dt.timedelta(days=20), dt.date(J, 12, 31))
if (frist_.month, frist_.day) == (2, 29): frist_ = dt.date(J, 2, 28)
v_ = P.call('mitarbeiter_hr')[1]
assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'uebertragBis': frist_.strftime('%m-%d')})[0] == 200
pf_ = next(p_ for p_ in v_['personen'] if p_['id'] == PF)
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['fritz'], jahr=J, anspruch=(pf_['jahre'].get(str(J)) or {}).get('anspruch'), uebertrag=6)
kf_ = next(p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['id'] == PF)['konto']
mv = P.call('mitarbeiter_hr')[1]['mail']
check('Erinnerung: Vorschau zählt nur Mitarbeiter mit verfallendem Resturlaub', kf_['verfaellt'] > 0 and mv['erinnerung'] == 1, (kf_['verfaellt'], mv['erinnerung']))
n0 = len(smtp.messages)
st, r = P.call('hr_erinnerung_senden', {})
until(lambda: len(smtp.messages) >= n0 + 1)
me_ = smtp.messages[n0]
tage_ = (f"{kf_['verfaellt']:g}".replace('.', ',')) + (' Tag' if kf_['verfaellt'] == 1 else ' Tage')
MAIL_HTML['erinnerung'] = mail_html(me_)
check('Erinnerung gesendet: Betreff mit Verfallstag, Tage im Text', st == 200 and r['ergebnis']['gesendet'] == 1 and me_['to'] == ['fritz@example.org']
      and me_['subject'] == f'Erinnerung: Ihr Resturlaub verfällt am {frist_.strftime("%d.%m.%Y")}' and tage_ in me_['text'], (st, me_.get('subject'), me_.get('text', '')[:300]))
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['fritz'], jahr=J, anspruch=(pf_['jahre'].get(str(J)) or {}).get('anspruch'), uebertrag=(pf_['jahre'].get(str(J)) or {}).get('uebertrag'))
v_ = P.call('mitarbeiter_hr')[1]
assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'uebertragBis': '03-31'})[0] == 200
# Steuerberater auf Knopfdruck: Excel mit Vormonat und laufendem Monat
st, r = P.call('hr_mail_save', {'steuerberater': {'an': False, 'adresse': 'Kanzlei@Example.org', 'tag': 7}})
check('Steuerberater-Adresse gespeichert (klein geschrieben), Tag 7', st == 200 and r['mail']['einst']['steuerberater']['adresse'] == 'kanzlei@example.org'
      and r['mail']['einst']['steuerberater']['tag'] == 7, r)
n0 = len(smtp.messages)
st, r = P.call('hr_steuerberater_senden', {})
until(lambda: len(smtp.messages) >= n0 + 1)
ms_ = smtp.messages[n0]
xl_ = [t_ for t_ in ms_['msg'].walk() if t_.get_content_type() == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
blaetter = zipfile.ZipFile(io.BytesIO(xl_[0].get_payload(decode=True))).read('xl/workbook.xml').decode() if xl_ else ''
check('Steuerberater: Mail mit Excel (Vormonat und laufender Monat als Blätter)', st == 200 and ms_['to'] == ['kanzlei@example.org'] and len(xl_) == 1
      and xl_[0].get_filename() == f'Urlaub_{ym(VOR)}_bis_{ym(DIES)}.xlsx' and mtext(VOR) in blaetter and mtext(DIES) in blaetter
      and mtext(VOR) in ms_['subject'] and mtext(DIES) in ms_['subject'], (ms_.get('subject'), xl_[0].get_filename() if xl_ else None))
# Testmodus: alles an die Testadresse
st, r = P.call('hr_mail_save', {'test': {'an': True, 'adresse': 'test@example.org'}, 'steuerberater': {'an': False, 'adresse': 'kanzlei@example.org', 'tag': 7}})
n0 = len(smtp.messages)
st1, r1 = P.call('hr_monatsuebersicht_senden', {}); st2, r2 = P.call('hr_steuerberater_senden', {})
until(lambda: len(smtp.messages) >= n0 + 3)
tm_ = smtp.messages[n0:]
check('Testmodus: Monatsübersicht und Steuerberater nur an die Testadresse, Betreff nennt den Empfänger', st1 == 200 and st2 == 200 and r1['ergebnis']['test'] is True
      and all(m_['to'] == ['test@example.org'] for m_ in tm_) and any(m_['subject'].startswith('[Test – für Fritz Frist] Ihr Urlaub') for m_ in tm_)
      and any(m_['subject'].startswith('[Test – für Steuerberater]') for m_ in tm_), [m_['subject'] for m_ in tm_])
# Automatik: Einschalten sendet nicht sofort; fällig (Stand zurückgesetzt) genau einmal beim nächsten HR-Aufruf
st, r = P.call('hr_mail_save', {'monat': {'an': True}, 'test': {'an': False, 'adresse': ''}, 'steuerberater': {'an': True, 'adresse': 'kanzlei@example.org', 'tag': 1}})
nx_ = r['mail']['naechste']
check('Automatik an: nächster Versand Monatsübersicht am 1. des nächsten Monats, Steuerberater nächster Monat (Tag 1 schon vorbei)', st == 200
      and nx_['monat'] == iso((DIES + dt.timedelta(days=32)).replace(day=1)) and nx_['steuerberater'] == iso((DIES + dt.timedelta(days=32)).replace(day=1)), nx_)
n0 = len(smtp.messages)
E.call('hr_start'); P.call('mitarbeiter_hr')
check('… kein sofortiger Versand beim Einschalten', len(smtp.messages) == n0)
d_ = dokument('hr-einstellungen'); d_['mail']['monat']['stand'] = '2000-01'; d_['mail']['steuerberater']['stand'] = '2000-01'; d_['rev'] = d_.get('rev', 0) + 1
storage_write('hr-einstellungen', d_)
E.call('hr_start')
until(lambda: len(smtp.messages) >= n0 + 3)
am_ = smtp.messages[n0:]
check('fällig: beim nächsten HR-Aufruf Monatsübersicht an alle und Übersicht an den Steuerberater', len(am_) == 3 and sorted(m_['to'][0] for m_ in am_) == ['erika@example.org', 'fritz@example.org', 'kanzlei@example.org'], [m_['to'] for m_ in am_])
E.call('hr_start'); E.call(f'hr_monat&jahr={Y}&monat=3'); P.call('mitarbeiter_hr')
mv = P.call('mitarbeiter_hr')[1]['mail']
check('… genau einmal je Monat (weitere Aufrufe senden nichts), Stand vermerkt', len(smtp.messages) == n0 + 3 and mv['einst']['monat']['stand'] == ym(VOR)
      and mv['einst']['steuerberater']['stand'] == ym(DIES), (len(smtp.messages) - n0, mv['einst']))
check('Verlauf: automatische und manuelle Versände mit Zahlen', [v_['art'] for v_ in mv['verlauf'][:2]] == ['steuerberater', 'monat'] and mv['verlauf'][0]['wie'] == 'automatisch'
      and mv['verlauf'][1]['gesendet'] == 2 and any(v_['art'] == 'erinnerung' and v_['wie'] == 'manuell' for v_ in mv['verlauf']), mv['verlauf'][:3])
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Einstellungen, Versände (automatisch als System, Testmodus)', 'HR: E-Mail-Einstellungen geändert' in log_ and 'HR: Monatsübersicht (automatisch): 2 gesendet' in log_
      and 'System (automatisch)' in log_ and 'HR: Übersicht an den Steuerberater (Testmodus): 1 gesendet' in log_ and 'HR: Erinnerung „Resturlaub verfällt“: 1 gesendet' in log_)
assert P.call('hr_mail_save', {'monat': {'an': False}, 'steuerberater': {'an': False, 'adresse': 'kanzlei@example.org', 'tag': 5}})[0] == 200
# ── Unentschuldigtes Fehlen (F, Inhaber 03.11.2026): nur Personalstelle, E-Mail an den Mitarbeiter mit Urlaubsübersicht ──
up_ = uu['paul']
assert A.call('user_save', {'id': up_['id'], 'name': up_['name'], 'username': up_['username'], 'role': up_['role'], 'active': up_['active'], 'email': 'personal@example.org'})[0] == 200
FT = montag(Y, 5, 3) + dt.timedelta(days=1)   # Dienstag im Mai
kv_ = next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={Y}')[1]['personen'] if p_['id'] == PF)['konto']
n0 = len(smtp.messages)
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'F', 'von': iso(FT), 'bis': iso(FT), 'notiz': 'nicht erschienen'})
F1 = r['eintrag']['id'] if st == 200 else None
check('Unentschuldigt (F) eingetragen, E-Mail an den Mitarbeiter gesendet', st == 200 and r['eintrag']['art'] == 'F' and r['eintrag']['artText'] == 'Unentschuldigt'
      and (r.get('mail') or {}).get('gesendet') is True and r['mail']['an'] == 'fritz@example.org', (st, r))
until(lambda: len(smtp.messages) >= n0 + 1)
mfe = smtp.messages[n0]
check('… Mail: Datum, Bitte um unverzügliche Erklärung per E-Mail, Urlaubsübersicht des Jahres, Antwort geht an die Personalstelle',
      mfe['to'] == ['fritz@example.org'] and mfe['subject'] == f'Abwesenheit am {FT:%d.%m.%Y} – bitte um Rückmeldung' and 'unverzüglich per E-Mail' in mfe['text']
      and f'Ihre Urlaubsübersicht {Y}' in mfe['text'] and APR.strftime('%d.%m.') in mfe['text'] and mfe['msg']['Reply-To'] == 'personal@example.org'
      and 'nicht erschienen' not in mfe['text'] and 'rank' not in mfe['text'], (mfe.get('subject'), mfe['msg']['Reply-To'], mfe.get('text', '')[:500]))
MAIL_HTML['fehlen'] = mail_html(mfe)
check('… Mail als HTML: Bitte hervorgehoben, Urlaubskonto, Urlaubszeiträume, Jahr auf einen Blick, Portal', all(x_ in MAIL_HTML['fehlen'] for x_ in (
      'unverzüglich per E-Mail', f'Ihre Urlaubsübersicht {Y}', f'Ihr Urlaub {Y}', 'auf einen Blick', 'Zum Urlaubsportal')))
kn_ = next(p_ for p_ in P.call(f'mitarbeiter_hr&jahr={Y}')[1]['personen'] if p_['id'] == PF)['konto']
check('… zählt nicht gegen den Urlaub', (kn_['genommen'], kn_['geplant'], kn_['rest']) == (kv_['genommen'], kv_['geplant'], kv_['rest']))
mon_ = {p_['id']: p_ for p_ in E.call(f'hr_monat&jahr={Y}&monat={FT.month}')[1]['personen']}
monp_ = {p_['id']: p_ for p_ in P.call(f'hr_monat&jahr={Y}&monat={FT.month}')[1]['personen']}
check('… Kollegen sehen nur „abwesend“, die Personalstelle „F“', mon_[PF]['tage'].get(str(FT.day)) == 'A' and monp_[PF]['tage'].get(str(FT.day)) == 'F',
      (mon_[PF]['tage'].get(str(FT.day)), monp_[PF]['tage'].get(str(FT.day))))
ub_ = {z['id']: z for z in P.call(f'hr_uebersicht&jahr={Y}')[1]['zeilen']}
check('… Übersicht: Spalte „unentschuldigt“', ub_[PF]['unentschuldigt'] == 1 and ub_[PE]['unentschuldigt'] == 0, ub_[PF].get('unentschuldigt'))
req = urllib.request.Request(B + '/api/?action=hr_export', data=json.dumps({'jahr': Y, 'monate': [FT.month]}).encode(),
                             headers={'Content-Type': 'application/json', 'X-CSRF-Token': P.csrf, 'X-Forwarded-For': P.ip})
wsf = openpyxl.load_workbook(io.BytesIO(P.http.open(req).read()))[f'Mai {Y}']
spF = 31 + 7   # nach den Tagen: U, K, G, F
zf = {wsf.cell(z, 3).value: z for z in range(9, 40) if wsf.cell(z, 3).value}
wf = [wsf.cell(zf['Fritz Frist'], c).value for c in range(4, 35)]
check('… Excel: „F“ am Tag, Legende „Unentschuldigt“, eigene Zählspalte F', wf.count('F') == 1 and wf[FT.day - 1] == 'F' and (wsf['F3'].value, wsf['G3'].value) == ('F', 'Unentschuldigt')
      and wsf.cell(7, spF).value == 'F' and str(wsf.cell(zf['Fritz Frist'], spF).value).startswith('=COUNTIF(') and str(wsf.cell(zf['Fritz Frist'], spF).value).endswith(',"F")'),
      (wf.count('F'), wsf['F3'].value, wsf['G3'].value, wsf.cell(7, spF).value, wsf.cell(zf['Fritz Frist'], spF).value))
n0 = len(smtp.messages)
st, r = P.call('hr_eintrag_save', {'id': F1, 'person': PF, 'art': 'F', 'von': iso(FT), 'bis': iso(FT), 'notiz': 'geändert'})
check('… Ändern eines F-Eintrags sendet keine neue Mail', st == 200 and r.get('mail') is None and len(smtp.messages) == n0, (st, r.get('mail')))
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'F', 'von': iso(FT + dt.timedelta(days=1)), 'bis': iso(FT + dt.timedelta(days=1)), 'mail': False})
F2 = r['eintrag']['id'] if st == 200 else None
check('… ohne Haken „E-Mail“: eingetragen, keine Mail', st == 200 and r.get('mail') is None and len(smtp.messages) == n0, (st, r.get('mail')))
st, r = P.call('hr_eintrag_save', {'person': PL, 'art': 'F', 'von': iso(FT), 'bis': iso(FT)})
F3 = r['eintrag']['id'] if st == 200 else None
check('… Mitarbeiter ohne E-Mail-Adresse: eingetragen, Hinweis statt Mail', st == 200 and r['mail']['gesendet'] is False and 'keine E-Mail-Adresse' in r['mail']['grund'], (st, r.get('mail')))
check('… nur die Personalstelle (Mitarbeiter 403), nie für sich selbst', E.call('hr_eintrag_save', {'person': PF, 'art': 'F', 'von': iso(FT), 'bis': iso(FT)})[0] == 403
      and P.call('hr_eintrag_save', {'person': ids['paul'], 'art': 'F', 'von': iso(FT), 'bis': iso(FT)})[0] == 403)
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
check('… Protokoll: E-Mail zur Abwesenheit (ohne Notiz)', 'E-Mail zur Abwesenheit an Fritz Frist (Bitte um Erklärung): 1 gesendet' in log_ and 'nicht erschienen' not in log_)
vf_ = P.call('mitarbeiter_hr')[1]['mail']['verlauf'][0]
check('… Verlauf der E-Mails: Art „fehlen“ mit Namen, ohne Inhalt', vf_['art'] == 'fehlen' and vf_['name'] == 'Fritz Frist' and vf_['gesendet'] == 1 and vf_['wie'] == 'manuell'
      and 'nicht erschienen' not in json.dumps(vf_, ensure_ascii=False), vf_)
assert P.call('hr_mail_save', {'test': {'an': True, 'adresse': 'test@example.org'}, 'steuerberater': {'an': False, 'adresse': 'kanzlei@example.org', 'tag': 5}})[0] == 200
n0 = len(smtp.messages)
st, r = P.call('hr_eintrag_save', {'person': PF, 'art': 'F', 'von': iso(FT + dt.timedelta(days=2)), 'bis': iso(FT + dt.timedelta(days=3))})
F4 = r['eintrag']['id'] if st == 200 else None
until(lambda: len(smtp.messages) >= n0 + 1)
check('… Testmodus: nur an die Testadresse, Betreff nennt den Mitarbeiter, Zeitraum „vom … bis …“', st == 200 and r['mail']['test'] is True and r['mail']['an'] == 'test@example.org'
      and smtp.messages[n0]['to'] == ['test@example.org']
      and smtp.messages[n0]['subject'] == f'[Test – für Fritz Frist] Abwesenheit vom {FT + dt.timedelta(days=2):%d.%m.%Y} bis {FT + dt.timedelta(days=3):%d.%m.%Y} – bitte um Rückmeldung',
      (r.get('mail'), smtp.messages[n0].get('subject')))
assert P.call('hr_mail_save', {'test': {'an': False, 'adresse': ''}, 'steuerberater': {'an': False, 'adresse': 'kanzlei@example.org', 'tag': 5}})[0] == 200
# ── Jahresplanung (Inhaber 03.11.2026): Einstellungen, Stand je Mitarbeiter, Konflikte, gesammelt genehmigen, Erinnerung,
#    Abschluss mit Jahresübersicht per E-Mail. Planungsjahr = Y (nächstes Jahr); Testdaten in den ersten Novemberwochen von Y ──
v_ = P.call('mitarbeiter_hr')[1]
EINST_ = {'sperren': v_['sperren'], 'ferien': v_['ferien']}
falsch_ = [P.call('hr_einstellungen_save', {**EINST_, 'planung': b_})[0] for b_ in (
    {'start': '12-01', 'stichtag': '10-01', 'prozent': 90, 'vertretungPflicht': True}, {'start': '10-01', 'stichtag': '12-01', 'prozent': 5, 'vertretungPflicht': True},
    {'start': '10-01', 'stichtag': '12-01', 'prozent': 90.5, 'vertretungPflicht': True}, {'start': '10-01', 'stichtag': '02-29', 'prozent': 90, 'vertretungPflicht': True},
    {'start': '10-01', 'stichtag': '12-01', 'prozent': 90, 'vertretungPflicht': 'ja'}, 'x')]
check('Jahresplanung einstellen: 422 bei Beginn nach Stichtag, Anteil 5 % oder krumm, 29.02., ja/nein, kein Objekt', falsch_ == [422] * 6, falsch_)
check('… ohne Personalrecht 403', L.call('hr_einstellungen_save', {**EINST_, 'planung': PLAN_STD})[0] == 403)
PLAN_T = {'start': '01-01', 'stichtag': '12-31', 'prozent': 90, 'vertretungPflicht': True}   # Hinweis an jedem Tag des Jahres sichtbar
st, r = P.call('hr_einstellungen_save', {**EINST_, 'planung': PLAN_T})
check('… gespeichert (Antwort und Verwaltung), Protokoll', st == 200 and r['planung'] == PLAN_T and P.call('mitarbeiter_hr')[1]['planung'] == PLAN_T
      and 'Jahresplanung eingestellt (ab 01.01., Stichtag 31.12., 90 %, Vertretung Pflicht)' in json.dumps(A.call('log')[1], ensure_ascii=False), r.get('planung'))
check('… Speichern ohne Angabe lässt sie unverändert', P.call('hr_einstellungen_save', EINST_)[1]['planung'] == PLAN_T)
st, r = E.call('hr_start')
pl_ = r.get('planung') or {}
check(f'Mitarbeiter: Hinweis Jahresplanung {Y} – Ziel 90 % des Anspruchs (27 von 30), Stichtag, Stand aus Anträgen', st == 200 and pl_.get('jahr') == Y and pl_.get('ziel') == 27
      and pl_.get('anspruch') == 30 and pl_.get('stichtag') == f'{Y - 1}-12-31' and pl_.get('vorbei') is False and pl_['geplant'] == pl_['genehmigt'] + pl_['beantragt']
      and pl_['fehlt'] == max(0, 27 - pl_['geplant']) and pl_['erreicht'] == (pl_['geplant'] >= 27) and r['vertretungPflicht'] is True, pl_)
check('… nicht im Urlaubsplan: kein Hinweis', O.call('hr_start')[1].get('planung') is None)
N1 = montag(Y, 11, 1); N3 = N1 + dt.timedelta(days=14)   # erste und dritte Novemberwoche (Weihnachtssperre erst ab der letzten)
st, r = F.call('hr_antrag', {'von': iso(N1), 'bis': iso(N1 + dt.timedelta(days=2))})
check('Urlaubsantrag ohne Vertretung (Pflicht): 422', st == 422 and 'Vertretung' in r.get('error', ''), (st, r))
st, r = F.call('hr_antrag', {'von': iso(N1), 'bis': iso(N1 + dt.timedelta(days=2)), 'vertretung': PA})
PA_ = r['eintrag']['id'] if st == 200 else None   # a) Fritz, Vertretung Andre – konfliktfrei
check('… mit Vertretung: gestellt, ohne Hinweis', st == 200 and not r.get('hinweis'), (st, r))
st, r = E.call('hr_antrag', {'von': iso(N1), 'bis': iso(N1 + dt.timedelta(days=1)), 'vertretung': PL})
PB_ = r['eintrag']['id'] if st == 200 else None   # b) Erika, Vertretung Lena – Lena ist dann selbst weg
st, r = P.call('hr_eintrag_save', {'person': PL, 'art': 'U', 'von': iso(N1 + dt.timedelta(days=1)), 'bis': iso(N1 + dt.timedelta(days=1))})
PC_ = r['eintrag']['id'] if st == 200 else None
st, r = P.call('hr_eintrag_save', {'person': PA, 'art': 'U', 'von': iso(N3), 'bis': iso(N3 + dt.timedelta(days=4))})
PD0_ = r['eintrag']['id'] if st == 200 else None
st, r = F.call('hr_antrag', {'von': iso(N3), 'bis': iso(N3 + dt.timedelta(days=1)), 'vertretung': PE})
PD_ = r['eintrag']['id'] if st == 200 else None   # d) Fritz, Vertretung Erika – Andre (gleiche Abteilung) ist weg
st, r = F.call('hr_antrag', {'von': iso(N3 + dt.timedelta(days=2)), 'bis': iso(N3 + dt.timedelta(days=2)), 'vertretung': PA})
PE_ = r['eintrag']['id'] if st == 200 else None   # e) Fritz, Vertretung Andre – Andre ist selbst weg
check('Vertretung selbst abwesend: Antrag gestellt, Hinweis ohne Grund', st == 200 and 'Andre Vierzig ist in dieser Zeit selbst abwesend' in (r.get('hinweis') or '')
      and 'Urlaub' not in (r.get('hinweis') or '').split('abwesend')[1], r.get('hinweis'))
check('Jahresplanung: ohne Recht 403 (Mitarbeiter, Leser)', E.call('hr_planung')[0] == 403 and L.call('hr_planung')[0] == 403)
GI = Client('198.51.100.9'); assert GI.call('login', {'username': 'gina', 'password': 'Genehmigen-Zugang-77'})[0] == 200
st, gp_ = GI.call('hr_planung')
check('… „Urlaub genehmigen“ sieht sie (Standard: nächstes Jahr), ohne Personalrecht', st == 200 and gp_['jahr'] == Y and gp_['genehmigen'] is True and gp_['verwalten'] is False, (st, gp_.get('jahr')))
st, r, raw_ = P.call(f'hr_planung&jahr={Y}', raw=True)
an_ = {a_['id']: a_ for a_ in r['antraege']}
pp_ = {p_['id']: p_ for p_ in r['personen']}
arten_ = lambda i: [k_['art'] for k_ in an_.get(i, {}).get('konflikte', [])]   # noqa: E731
texte_ = lambda i: ' | '.join(k_['text'] for k_ in an_.get(i, {}).get('konflikte', []))   # noqa: E731
check('Personalstelle: Stand je Mitarbeiter (Ziel 90 % des Anspruchs), Stichtag, kein Abschluss', st == 200 and pp_[PE]['ziel'] == 27 and pp_[PF]['ziel'] == 18
      and r['stichtag'] == f'{Y - 1}-12-31' and r['prozent'] == 90 and r['abschluss'] is None and r['verwalten'] is True, (pp_.get(PF), r.get('stichtag')))
check('… a) Vertretung da, niemand aus der Abteilung weg: konfliktfrei, gesammelt genehmigbar', an_.get(PA_, {}).get('frei') is True and arten_(PA_) == [] and an_[PA_]['vertretung'] == 'Andre Vierzig', an_.get(PA_))
check('… b) Vertretung selbst abwesend (ohne Grund)', arten_(PB_) == ['vertretung'] and 'Lena Leser ist selbst abwesend' in texte_(PB_) and an_[PB_]['frei'] is False, texte_(PB_))
check('… d) gleiche Abteilung gleichzeitig weg', 'abteilung' in arten_(PD_) and 'Gleichzeitig weg: Andre Vierzig' in texte_(PD_), texte_(PD_))
check('… e) Vertretung selbst abwesend, nicht doppelt als Abteilung', arten_(PE_) == ['vertretung'] and 'Andre Vierzig ist selbst abwesend' in texte_(PE_), texte_(PE_))
check('… genehmigte Einträge der Personalstelle ohne Vertretung: kein Konflikt „keine Vertretung“', 'Keine Vertretung' not in texte_(PC_) and an_[PC_]['status'] == 'genehmigt', texte_(PC_))
check('… alte offene Anträge ohne Vertretung: Konflikt „Keine Vertretung angegeben“', any(a_['status'] == 'beantragt' and any(k_['text'] == 'Keine Vertretung angegeben' for k_ in a_['konflikte']) for a_ in r['antraege']))
check('… nie Gründe oder Notizen anderer Abwesenheiten (Krankheit)', 'Arztbesuch' not in raw_ and '"K"' not in raw_ and 'Krank' not in raw_)
check('… Zahlen passen zur Liste („Ziel erreicht“ nur mit Anspruch im Jahr)', r['zahlen']['frei'] == sum(1 for a_ in r['antraege'] if a_['frei']) and r['zahlen']['offen'] == sum(1 for a_ in r['antraege'] if a_['status'] == 'beantragt')
      and r['zahlen']['erinnern'] == sum(1 for p_ in r['personen'] if not p_['erreicht'] and p_['adresse'])
      and r['zahlen']['personen'] == sum(1 for p_ in r['personen'] if p_['anspruch'] > 0) and r['zahlen']['erreicht'] == sum(1 for p_ in r['personen'] if p_['anspruch'] > 0 and p_['erreicht']), r['zahlen'])
# gesammelt genehmigen: nur konfliktfreie, nie die eigenen (Gina vorübergehend im Urlaubsplan mit eigenem Antrag)
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['gina'], aktiv=True)
st, r = GI.call('hr_antrag', {'von': iso(N1 + dt.timedelta(days=7)), 'bis': iso(N1 + dt.timedelta(days=7)), 'vertretung': PE})
PG_ = r['eintrag']['id'] if st == 200 else None
falsch_ = [L.call('hr_planung_freigeben', {'jahr': Y, 'ids': [PA_]})[0], P.call('hr_planung_freigeben', {'jahr': Y, 'ids': []})[0], P.call('hr_planung_freigeben', {'jahr': Y, 'ids': 'x'})[0],
           P.call('hr_planung_freigeben', {'jahr': Y, 'ids': ['a b']})[0], P.call('hr_planung_freigeben', {'jahr': 1999, 'ids': [PA_]})[0] >= 400]
check('Gesammelt genehmigen: ohne Recht 403, ohne/ungültige Anträge 422, ungültiges Jahr abgelehnt', falsch_ == [403, 422, 422, 422, True], falsch_)
st, r = GI.call('hr_planung_freigeben', {'jahr': Y, 'ids': [PA_, PD_, PG_, 'agibtsnicht']})
weg_ = {w_['id']: w_['grund'] for w_ in r.get('uebersprungen', [])}
check('… genehmigt nur den konfliktfreien; Konflikt, eigener Antrag und Unbekanntes bleiben', st == 200 and r['genehmigt'] == [PA_]
      and weg_ == {PD_: 'Konflikt', PG_: 'eigener Antrag', 'agibtsnicht': 'nicht gefunden'}, (st, r))
e_ = next(x_ for x_ in P.call(f'hr_verwaltung&jahr={Y}')[1]['eintraege'] if x_['id'] == PA_)
check('… Entscheidung „Jahresplanung“ mit Namen, Protokoll', e_['status'] == 'genehmigt' and e_['entscheidung']['grund'] == f'Jahresplanung {Y}' and e_['entscheidung']['by'] == 'Gina Genehmigt'
      and f'Jahresplanung {Y}: 1 Urlaubsanträge gesammelt genehmigt' in json.dumps(A.call('log')[1], ensure_ascii=False), e_.get('entscheidung'))
check('… nochmals: schon entschieden', GI.call('hr_planung_freigeben', {'jahr': Y, 'ids': [PA_]})[1]['uebersprungen'] == [{'id': PA_, 'grund': 'nicht offen'}])
A.call('hr_eintrag_save', {'id': PG_, 'stornieren': True})   # Gina ist bei Paul nicht „eigen“, aber Administrator reicht
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['gina'], aktiv=False)
# Erinnerung: an alle mit Adresse, die das Ziel noch nicht erreicht haben (Fritz, Erika)
check('Erinnerung Jahresplanung: ohne Personalrecht 403', GI.call('hr_planung_erinnern', {'jahr': Y})[0] == 403 and L.call('hr_planung_erinnern', {'jahr': Y})[0] == 403)
n0 = len(smtp.messages)
st, r = P.call('hr_planung_erinnern', {'jahr': Y})
until(lambda: len(smtp.messages) >= n0 + 2)
pm_ = {m_['to'][0]: m_ for m_ in smtp.messages[n0:]}
mfp_ = pm_.get('fritz@example.org', {})
check('… an Fritz und Erika: Stichtag, Ziel, was fehlt, Vertretung, bisherige Zeiträume mit Vertretung', st == 200 and r['ergebnis']['gesendet'] == 2 and r['ergebnis']['ohneAdresse'] > 0
      and set(pm_) == {'fritz@example.org', 'erika@example.org'} and mfp_.get('subject') == f'Bitte planen Sie Ihren Urlaub {Y} bis zum 31.12.{Y - 1}'
      and 'es fehlen noch' in mfp_.get('text', '') and 'Vertretung' in mfp_.get('text', '') and 'Andre Vierzig' in mfp_.get('text', ''), (st, r, mfp_.get('text', '')[:500]))
MAIL_HTML['planung'] = mail_html(mfp_)
# Abschluss: Jahresübersicht an alle mit Adresse, Hinweis bei den Mitarbeitern verschwindet; wieder öffnen
falsch_ = [GI.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': True})[0], P.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': 'ja'})[0],
           P.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': False})[0]]
check('Abschluss: ohne Personalrecht 403, ja/nein 422, Öffnen ohne Abschluss 409', falsch_ == [403, 422, 409], falsch_)
n0 = len(smtp.messages)
st, r = P.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': True})
until(lambda: len(smtp.messages) >= n0 + 2)
jm_ = {m_['to'][0]: m_ for m_ in smtp.messages[n0:]}
jf_ = jm_.get('fritz@example.org', {})
check('… abgeschlossen: Jahresübersicht an Fritz und Erika (genehmigter Zeitraum mit Vertretung, Konto, Jahr auf einen Blick)', st == 200 and r['ergebnis']['gesendet'] == 2
      and jf_.get('subject') == f'Ihre Urlaubsplanung {Y}' and f'{N1:%d.%m.%Y}' in jf_.get('text', '') and 'Vertretung: Andre Vierzig' in jf_.get('text', '')
      and 'auf einen Blick' in jf_.get('text', '') and 'Noch nicht verplant' in jf_.get('text', ''), (st, r, jf_.get('text', '')[:600]))
MAIL_HTML['jahresuebersicht'] = mail_html(jf_)
check('… Hinweis bei den Mitarbeitern weg, Zusammenfassung zeigt den Abschluss, doppelt 409', E.call('hr_start')[1].get('planung') is None
      and P.call('hr_planung')[1]['abschluss']['by'] == 'Paul Personal' and P.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': True})[0] == 409)
n0 = len(smtp.messages)
st, r = P.call('hr_planung_uebersicht_senden', {'jahr': Y, 'person': PF})
until(lambda: len(smtp.messages) >= n0 + 1)
check('Jahresübersicht einzeln erneut senden (nur Fritz); ohne Recht 403', st == 200 and r['ergebnis']['gesendet'] == 1 and smtp.messages[n0]['to'] == ['fritz@example.org']
      and GI.call('hr_planung_uebersicht_senden', {'jahr': Y})[0] == 403, (st, r))
st, r = P.call('hr_planung_abschluss', {'jahr': Y, 'abgeschlossen': False})
check('… wieder geöffnet: Hinweis wieder da, keine Mail', st == 200 and r['ergebnis'] is None and E.call('hr_start')[1].get('planung', {}).get('jahr') == Y)
log_ = json.dumps(A.call('log')[1], ensure_ascii=False)
mv_ = P.call('mitarbeiter_hr')[1]['mail']['verlauf']
check('Protokoll und Verlauf: Erinnerung, Abschluss, Jahresübersicht, wieder geöffnet', all(x_ in log_ for x_ in (f'Erinnerung Jahresplanung {Y}: 2 gesendet', f'Jahresplanung {Y} abgeschlossen',
      f'Jahresübersicht {Y}: 2 gesendet', f'Jahresplanung {Y} wieder geöffnet'))
      and [(v2_['art'], v2_.get('jahr')) for v2_ in mv_[:3]] == [('jahresuebersicht', Y), ('jahresuebersicht', Y), ('planung', Y)], [(v2_['art'], v2_.get('jahr')) for v2_ in mv_[:3]])
for id_ in (PA_, PB_, PC_, PD0_, PD_, PE_):
    if id_: P.call('hr_eintrag_save', {'id': id_, 'stornieren': True})
assert P.call('hr_einstellungen_save', {**EINST_, 'planung': {**PLAN_STD, 'vertretungPflicht': False}})[0] == 200   # spätere Antragstests ohne Vertretung

for id_ in (U_VOR, K_VOR, F1, F2, F3, F4):
    if id_: P.call('hr_eintrag_save', {'id': id_, 'stornieren': True})
rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['fritz'], aktiv=F_AKTIV)

with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280, verfall_hinweis=False):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin')
        if not verfall_hinweis:   # Pop-up „Resturlaub verfällt bald“ (Feb./März möglich) nur im eigenen Test – sonst als heute gesehen
            ctx.add_init_script("try { localStorage.setItem('hr-verfall-gesehen', 'hr-verfall-' + new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Berlin'}).format(new Date())); } catch (e) {}")
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    # ── HR-Mails als Bild (Inhaber 03.11.2026: ordentlich, Tabellen, Link zum Portal): 600 px und Handy 390 px ohne waagerechtes Scrollen ──
    mctx = br.new_context(viewport={'width': 600, 'height': 900}, locale='de-DE')
    mpg = mctx.new_page()
    for art_, html_ in MAIL_HTML.items():
        breit_ = {}
        for w_ in (600, 390):
            mpg.set_viewport_size({'width': w_, 'height': 900}); mpg.set_content(html_)
            breit_[w_] = mpg.evaluate('document.documentElement.scrollWidth')
            mpg.screenshot(path=os.path.join(SH, f'hr_mail_{art_}_{w_}.png'), full_page=True)
        check(f'Mail „{art_}“: Kopfband „Urlaubsverwaltung“, passt auf 390 px', bool(html_) and 'Urlaubsverwaltung' in html_ and breit_[390] <= 391, breit_)
    mctx.close()

    # ── Testdaten 2025 (früher aus der Excel-Planung): Mitarbeiter ohne Anmeldung mit Abteilung und Position, Einträge der Personalstelle ──
    for vor, nach, abt_, pos_ in (('Anna', 'Beispiel', 'GF', 1), ('Bernd', 'Muster', 'Verwaltung', 2), ('Carla', 'Probe', 'Verwaltung', 3),
                                  ('Dieter', 'Test', 'Lager', 4), ('Emil', 'Lager', 'Lager', 5)):
        st, r_ = A.call('user_save', {'id': '', 'vorname': vor, 'nachname': nach, 'role': 'editor', 'active': True, 'zugang': False})
        assert st == 200, r_
        rev = P.call('mitarbeiter_hr')[1]['rev']
        hr(r_['user']['id'], abteilung=abt_, pos=pos_, aktiv=True)
    nutzer = {u['name']: u for u in A.call('users')[1]['users']}
    for name, art, von, bis in (('Anna Beispiel', 'U', '2025-01-13', '2025-01-17'), ('Bernd Muster', 'K', '2025-01-20', '2025-01-21'),
                                ('Carla Probe', 'G', '2025-01-31', '2025-01-31'), ('Carla Probe', 'U', '2025-02-03', '2025-02-04')):
        st, r_ = P.call('hr_eintrag_save', {'person': nutzer[name]['id'], 'art': art, 'von': von, 'bis': bis})
        assert st == 200, (name, r_)
    anzahl_personen = len(P.call('hr_verwaltung&jahr=2025')[1]['personen'])
    k26 = {p_['name']: p_['konto'] for p_ in P.call('hr_verwaltung&jahr=2026')[1]['personen']}
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.click('#vt-importe'); pg.wait_for_selector('#view-importe .imp-art[data-art="zeiterfassung"]')
    check('Importzentrale (Personalstelle): Abwesenheiten aus der Zeiterfassung unter „Personal“, keine Urlaubsplanung mehr',
          pg.text_content('#view-importe .imp-gruppe:has(.imp-art[data-art="zeiterfassung"]) h2') == 'Personal' and pg.locator('.imp-art[data-art="urlaubsplanung"]').count() == 0)
    check('ohne bekannten Anspruch im Vorjahr kein (negativer) automatischer Übertrag', k26['Anna Beispiel']['uebertrag'] == 0, k26['Anna Beispiel'])
    abt = [p_['abteilung'] for p_ in P.call(f'hr_monat&jahr={Y}&monat=1')[1]['personen']]
    bloecke = [x for i, x in enumerate(abt) if i == 0 or abt[i - 1] != x]
    check('Kalender: jede Abteilung ein Block (Reihenfolge nach Position)', len(bloecke) == len(set(bloecke)) and bloecke[0] == 'GF', abt)

    # ── Abwesenheiten aus der Zeiterfassung (Importvorlage, synthetischer Abwesenheitsbericht passend zu den Testdaten 2025) ──
    BERICHT = os.path.join(FIX, 'hr', 'Abwesenheitsbericht_Muster.xlsx')
    wsb = openpyxl.load_workbook(BERICHT).active
    D = {'blaetter': [{'name': wsb.title, 'grid': [[(v - dt.datetime(1899, 12, 30)).days if isinstance(v, dt.datetime) else v for v in z]
                                                   for z in wsb.iter_rows(values_only=True)]}]}

    def zeit(cl, uebernehmen=False, stand=None, **opt):
        b = {'art': 'zeiterfassung', 'daten': D, 'quelle': 'Abwesenheitsbericht_Muster.xlsx', 'optionen': opt}
        if uebernehmen: b['stand'] = stand
        return cl.call('import_uebernehmen' if uebernehmen else 'import_pruefen', b)

    check('Zeiterfassung: ohne Personalrecht 403', zeit(L)[0] == 403 and zeit(E)[0] == 403)
    st, r = P.call('import_pruefen', {'art': 'zeiterfassung', 'daten': {'blaetter': [{'name': 'x', 'grid': [['Artikel', 'Preis'], ['A', 1]]}]}})
    check('Zeiterfassung: andere Datei 422 mit Hinweis', st == 422 and 'Abwesenheitsbericht' in r.get('error', ''), (st, r))
    st, v = zeit(P)
    zl = {(z['art'], z['name']): z for z in v['zeilen'] if z['schluessel'] != 'Abwesenheiten'}
    hw = ' '.join(h['text'] for h in v['hinweise'])
    check('Vorschau: unbekannte Mitarbeiter neu (mit/ohne Personalnummer), Feiertage nicht übernommen', st == 200 and ('neu', 'Hans Neumann') in zl
          and 'Nr. 105' == zl[('neu', 'Hans Neumann')]['schluessel'] and ('neu', 'Ina Ohnenummer') in zl, sorted(zl))
    check('Vorschau: ähnliche Schreibweise als Hinweis, nie automatisch zugeordnet', 'ähnlich: Carla Probe' in zl.get(('neu', 'Karla Probe'), {}).get('text', ''), zl.get(('neu', 'Karla Probe')))
    check('Vorschau: schon gleich eingetragene Tage bleiben (5 Tage Anna)', v['zahlen']['unveraendert'] == 5, v['zahlen'])
    check('Vorschau: im System anders eingetragen → Fehlerzeile, bleibt unverändert', '20.01.2025 (K statt U)' in zl.get(('fehler', 'Bernd Muster'), {}).get('text', ''), zl.get(('fehler', 'Bernd Muster')))
    check('Vorschau: ungültiges Datum und unbekannte Art gemeldet', any('Hans Neumann: Start- oder Enddatum' in z['text'] for z in v['zeilen']) and '„Elternzeit“ (1×)' in hw, hw)
    # gleiche Person, andere Schreibweise: Personalnummer am Mitarbeiter eintragen → Zuordnung über die Nummer
    rev = P.call('mitarbeiter_hr')[1]['rev']
    hr(nutzer['Carla Probe']['id'], personalnummer='103')
    check('Personalnummer eindeutig (409)', P.call('mitarbeiter_hr_save', {'nutzer': ids['erika'], 'rev': rev, 'personalnummer': '103'})[0] == 409)
    check('Personalnummer: ungültige Zeichen 422', P.call('mitarbeiter_hr_save', {'nutzer': ids['erika'], 'rev': rev, 'personalnummer': 'ab cd'})[0] == 422)
    st, v2 = zeit(P, abteilungen=True)
    check('Option Abteilungen: Abteilung aus der Zeiterfassung als Änderung', any(z['art'] == 'geaendert' and z['name'] == 'Anna Beispiel' and 'Abteilung Geschäftsführung' in z['text'] for z in v2['zeilen']), v2['zeilen'][:6])
    # Übernahme in der Oberfläche (Importzentrale)
    pg.click('#vt-importe'); pg.wait_for_selector('#view-importe input[data-imp-datei="zeiterfassung"]', state='attached')
    check('Importzentrale: Importart „Abwesenheiten aus der Zeiterfassung“', 'Zeiterfassung' in pg.text_content('#view-importe .imp-art[data-art="zeiterfassung"]'))
    pg.set_input_files('#view-importe input[data-imp-datei="zeiterfassung"]', BERICHT)
    pg.wait_for_selector('#imp-neu', timeout=20000)
    txt = pg.inner_text('#view-importe')
    check('Oberfläche: Vorschau über die Personalnummer (Carla statt neuer Karla)', 'Hans Neumann' in txt and 'Karla' not in txt and 'Carla Probe' in txt, txt[:700])
    pg.screenshot(path=os.path.join(SH, 'hr_zeiterfassung_1280.png'), full_page=True)
    pg.set_viewport_size({'width': 390, 'height': 844})
    check('390px: Vorschau ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    pg.screenshot(path=os.path.join(SH, 'hr_zeiterfassung_390.png'), full_page=True)
    pg.set_viewport_size({'width': 1280, 'height': 900})
    pg.click('#imp-ok'); pg.wait_for_selector('#imp-ergebnis')
    r = P.call('hr_verwaltung&jahr=2025')[1]
    ze = sorted((e['name'], e['art'], e['von'], e['bis'], e['urlaubAbzug'], e['status']) for e in r['eintraege'] if e['quelle'] == 'zeiterfassung')
    check('Übernommen: Zeiträume (über Wochenenden zusammengefasst), genehmigt', ze == [
        ('Bernd Muster', 'K', '2025-03-05', '2025-03-05', True, 'genehmigt'), ('Carla Probe', 'U', '2025-03-17', '2025-03-18', False, 'genehmigt'),
        ('Erika Editor', 'K', '2025-02-10', '2025-02-14', False, 'genehmigt'), ('Erika Editor', 'U', '2025-03-24', '2025-03-28', False, 'genehmigt'),
        ('Hans Neumann', 'U', '2025-02-27', '2025-03-04', False, 'genehmigt')], ze)
    kk = {p_['name']: p_['konto'] for p_ in r['personen']}
    check('Konto: Krankheit zählt nie gegen den Urlaub – auch „Krank ohne AU / vom Urlaub abgezogen“ nicht (Inhaber 30.10.2026), Hinweis bleibt gespeichert', kk['Bernd Muster']['genommen'] == 0 and kk['Erika Editor']['genommen'] == 5
          and kk['Hans Neumann']['genommen'] == 4, {k: kk[k]['genommen'] for k in ('Bernd Muster', 'Erika Editor', 'Hans Neumann')})
    check('Eintrag der Personalstelle (K 20.–21.01.) unverändert', any(e['name'] == 'Bernd Muster' and e['art'] == 'K' and e['von'] == '2025-01-20' and e['quelle'] == 'personalstelle' for e in r['eintraege']))
    pm = {p_['name']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen']}
    check('Übernommen: Personalnummern gespeichert, neue Mitarbeiter mit Abteilung, bestehende Abteilung unverändert (Option aus)',
          [pm[n]['personalnummer'] for n in ('Anna Beispiel', 'Bernd Muster', 'Carla Probe', 'Erika Editor', 'Hans Neumann', 'Ina Ohnenummer')] == ['101', '102', '103', '104', '105', '']
          and pm['Hans Neumann']['abteilung'] == 'Produktion' and pm['Anna Beispiel']['abteilung'] == 'GF' and pm['Hans Neumann']['zugang'] is False,
          {n: (pm[n]['personalnummer'], pm[n]['abteilung']) for n in pm if n in ('Anna Beispiel', 'Hans Neumann', 'Ina Ohnenummer')})
    # erneute Übernahme ersetzt die frühere, veralteter Stand wird abgewiesen
    st, v3 = zeit(P)
    check('erneut: 5 frühere Einträge ersetzt, keine neuen Mitarbeiter, 7 Tage unverändert', v3['zahlen']['entfaellt'] == 5 and not any(z['art'] == 'neu' and z['schluessel'] != 'Abwesenheiten' for z in v3['zeilen'])
          and v3['zahlen']['unveraendert'] == 7, v3['zahlen'])
    rev = P.call('mitarbeiter_hr')[1]['rev']
    hr(nutzer['Carla Probe']['id'], pos=3)
    check('Übernahme mit veraltetem Stand: 409', zeit(P, True, v3['stand'])[0] == 409)
    st, v3 = zeit(P)
    check('Übernahme mit aktuellem Stand: 200', zeit(P, True, v3['stand'])[0] == 200)
    r = P.call('hr_verwaltung&jahr=2025')[1]
    check('… keine doppelten Einträge oder Mitarbeiter', len([e for e in r['eintraege'] if e['quelle'] == 'zeiterfassung']) == 5 and len(r['personen']) == anzahl_personen + 2, (len(r['personen']), anzahl_personen))
    # gleicher Name, andere Personalnummer: andere Person – nie automatisch zuordnen, Personalnummer nicht überschreiben
    D2 = json.loads(json.dumps(D))
    for z in D2['blaetter'][0]['grid']:
        if z[0] == 'Anna' and z[1] == 'Beispiel': z[7] = '199'
    b2 = {'art': 'zeiterfassung', 'daten': D2, 'quelle': 'Abwesenheitsbericht_Muster.xlsx', 'optionen': {}}
    st, v4 = P.call('import_pruefen', b2)
    z4 = {(z['art'], z['name']): z for z in v4.get('zeilen', []) if z['schluessel'] != 'Abwesenheiten'}
    check('gleicher Name, andere Personalnummer: als neu mit Hinweis, nicht der bestehenden Anna zugeordnet',
          st == 200 and ('neu', 'Anna Beispiel') in z4 and 'Nr. 199' == z4[('neu', 'Anna Beispiel')]['schluessel']
          and 'ähnlich: Anna Beispiel' in z4[('neu', 'Anna Beispiel')]['text']
          and not any(z['art'] == 'geaendert' and z['name'] == 'Anna Beispiel' for z in v4['zeilen']), (st, sorted(z4)))

    # Personalstelle ändert die Art: der Hinweis „vom Urlaub abgezogen“ entfällt
    eb = next(e for e in r['eintraege'] if e['quelle'] == 'zeiterfassung' and e['name'] == 'Bernd Muster')
    st, x = P.call('hr_eintrag_save', {'id': eb['id'], 'person': eb['person'], 'art': 'G', 'von': eb['von'], 'bis': eb['bis']})
    r = P.call('hr_verwaltung&jahr=2025')[1]
    eb2 = next(e for e in r['eintraege'] if e['id'] == eb['id'])
    check('Art geändert: Hinweis „vom Urlaub abgezogen“ entfällt, zählt weiter nicht gegen den Urlaub', st == 200 and eb2['urlaubAbzug'] is False and {p_['name']: p_['konto'] for p_ in r['personen']}['Bernd Muster']['genommen'] == 0, (st, x, eb2))

    # ── Verwaltung → Mitarbeiter (Personalstelle ohne Administratorrechte): nur HR-Angaben ──
    pg.click('#vt-users'); pg.wait_for_selector('#view-users tr[data-hr-uid]')
    check('Personalstelle: Mitarbeiterliste mit HR-Angaben, ohne Rollen/Rechte', 'Rest' in pg.text_content('#view-users') and pg.locator('#us-zu-rollen').count() == 0
          and pg.locator('#user-add').count() == 0)
    pg.click(f'#view-users tr[data-hr-uid="{ids["erika"]}"]'); pg.wait_for_selector('#dlg-hr-person[open]')
    pg.fill('#dlg-hr-person [name="hr_abteilung"]', 'Vertrieb'); pg.fill('#dlg-hr-person [name="hr_anspruch"]', '31')
    check('Dialog: „Resturlaub verfällt“ mit Verfallstag, Standard angehakt', pg.is_checked('#dlg-hr-person [name="hr_verfall"]')
          and 'verfällt am 31.03.' in pg.text_content('#dlg-hr-person #hr-teil'))
    pg.uncheck('#dlg-hr-person [name="hr_verfall"]')
    pg.locator('#dlg-hr-person').screenshot(path=os.path.join(SH, 'hr_verwaltung_verfall_dialog_1280.png'))
    pg.click('#dlg-hr-person [type="submit"]'); pg.wait_for_selector('#dlg-hr-person[open]', state='hidden')
    pg.wait_for_selector(f'#view-users tr[data-hr-uid="{ids["erika"]}"] .hr-kein-verfall')   # Liste nach dem Speichern neu geladen
    pe = {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}[ids['erika']]
    check('Oberfläche: Abteilung und Anspruch gespeichert', pe['abteilung'] == 'Vertrieb' and pe['jahre'][str(dt.date.today().year)]['anspruch'] == 31, pe)
    check('Oberfläche: „Resturlaub verfällt“ abgehakt gespeichert, Liste zeigt „kein Verfall“', pe['verfall'] is False
          and pg.locator(f'#view-users tr[data-hr-uid="{ids["erika"]}"] .hr-kein-verfall').count() == 1
          and pg.locator('#view-users .hr-kein-verfall').count() == 1, pe.get('verfall'))
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_kein_verfall_1280.png'), full_page=True)
    pg.click(f'#view-users tr[data-hr-uid="{ids["erika"]}"]'); pg.wait_for_selector('#dlg-hr-person[open]')
    check('… beim nächsten Öffnen ohne Haken', not pg.is_checked('#dlg-hr-person [name="hr_verfall"]'))
    pg.check('#dlg-hr-person [name="hr_verfall"]')
    pg.click('#dlg-hr-person [type="submit"]'); pg.wait_for_selector('#dlg-hr-person[open]', state='hidden')
    pg.wait_for_function("document.querySelectorAll('#view-users .hr-kein-verfall').length === 0")
    check('… wieder angehakt: verfällt, kein Kennzeichen', {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}[ids['erika']]['verfall'] is True
          and pg.locator('#view-users .hr-kein-verfall').count() == 0)
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_personal_1280.png'), full_page=True)
    pg.click('#vt-urlaub'); pg.wait_for_selector('#hr-einst')
    check('Verwaltung → Urlaub: Sperren und Ferien aus der HR', pg.locator('#hr-sperren .hr-zr').count() == 1 and pg.locator('#hr-ferien .hr-zr').count() == 1)
    J0_ = dt.date.today().year
    check('Verwaltung → Urlaub: Sperren aus den Urlaubsregeln angehakt mit Vorschau (dieses und nächstes Jahr), Regeltext vorbelegt',
          pg.is_checked('#hr-regelsperren') and pg.locator('#hr-autosperren li').count() == 4 and f'Ostergeschäft {J0_}' in pg.text_content('#hr-autosperren')
          and pg.input_value('#hr-regeln').startswith('1. Urlaubsanspruch'))
    pg.uncheck('#hr-regelsperren')
    check('… abgehakt: Vorschau ausgeblendet', not pg.is_visible('#hr-autosperren'))
    pg.fill('#hr-regeln', '1. Test\nNur ein Test.')
    with pg.expect_response(lambda r_: 'action=hr_einstellungen_save' in r_.url) as antwort:
        pg.click('#hr-einst [type="submit"]')
    pg.wait_for_selector('#hr-regelsperren')
    v_ = P.call('mitarbeiter_hr')[1]
    check('Oberfläche: Schalter und Regeltext gespeichert', antwort.value.status == 200 and v_['regelSperren'] is False and v_['regeln'] == '1. Test\nNur ein Test.'
          and not pg.is_checked('#hr-regelsperren'), antwort.value.status)
    pg.check('#hr-regelsperren'); pg.click('#hr-regeln-vorlage')
    check('… „Vorlage einsetzen“ füllt den Standardtext', pg.input_value('#hr-regeln') == v_['regelnStandard'])
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_urlaubsregeln_1280.png'), full_page=True)
    pg.click('[data-plus="hr-ferien"]')
    zr = pg.locator('#hr-ferien .hr-zr').nth(1).locator('input')
    zr.nth(0).fill(f'{Y}-10-05'); zr.nth(1).fill(f'{Y}-10-16'); zr.nth(2).fill('Herbstferien')
    with pg.expect_response(lambda r_: 'action=hr_einstellungen_save' in r_.url) as antwort:   # auf die Antwort warten, nicht nur auf die Zeilen
        pg.click('#hr-einst [type="submit"]')
    check('Verwaltung → Urlaub: Speichern ohne Fehler', antwort.value.status == 200 and not pg.text_content('#hr-einst-err'), antwort.value.status)
    check('Verwaltung → Urlaub: Ferien gespeichert', len(P.call('mitarbeiter_hr')[1]['ferien']) == 2)
    check('Verwaltung → Urlaub: Verfallstag vorbelegt (31.03.)', pg.input_value('#hr-uebertrag-bis').endswith('-03-31') and '31.03.' in pg.text_content('#hr-uebertrag-anzeige'))
    pg.fill('#hr-uebertrag-bis', f'{Y}-04-15')
    with pg.expect_response(lambda r_: 'action=hr_einstellungen_save' in r_.url):
        pg.click('#hr-einst [type="submit"]')
    pg.wait_for_function('document.querySelector("#hr-uebertrag-anzeige") && document.querySelector("#hr-uebertrag-anzeige").textContent.includes("15.04.")')
    check('Oberfläche: Verfallstag 15.04. gespeichert, Ferien bleiben', P.call('mitarbeiter_hr')[1]['uebertragBis'] == '04-15' and len(P.call('mitarbeiter_hr')[1]['ferien']) == 2)
    # Übergangsregel „Verfällt erstmals“: Auswahl mit „jedes Jahr“, gespeichert mit den übrigen Einstellungen
    check('Verwaltung → Urlaub: „Verfällt erstmals“ vorbelegt mit „jedes Jahr“', pg.input_value('#hr-verfall-ab') == '' and 'jedes Jahr am 15.04.' in pg.text_content('#hr-uebertrag-anzeige'))
    pg.select_option('#hr-verfall-ab', str(heute_.year + 1))
    with pg.expect_response(lambda r_: 'action=hr_einstellungen_save' in r_.url) as antwort:
        pg.click('#hr-einst [type="submit"]')
    pg.wait_for_function(f'document.querySelector("#hr-uebertrag-anzeige") && document.querySelector("#hr-uebertrag-anzeige").textContent.includes("erstmals am 15.04.{heute_.year + 1}")')
    check('Oberfläche: Übergangsregel gespeichert, Hinweis nennt das Jahr ohne Verfall', antwort.value.status == 200 and P.call('mitarbeiter_hr')[1]['verfallAb'] == heute_.year + 1
          and f'Resturlaub aus {heute_.year - 1} bleibt {heute_.year} ganz erhalten' in pg.text_content('#hr-uebertrag-anzeige'), pg.text_content('#hr-uebertrag-anzeige'))
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_urlaub_1280.png'), full_page=True)
    v_ = P.call('mitarbeiter_hr')[1]
    assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'uebertragBis': '03-31', 'verfallAb': None})[0] == 200
    # E-Mails: gespeicherte Steuerberater-Adresse, ändern sperrt die Knöpfe bis zum Speichern, senden mit Rückfrage
    check('E-Mails-Karte: Steuerberater-Adresse und Tag aus den Einstellungen, Erinnerung ohne Kandidaten gesperrt', pg.input_value('#hrm-stb-adresse') == 'kanzlei@example.org'
          and pg.input_value('#hrm-stb-tag') == '5' and pg.is_disabled('#hr-mail [data-hr-mail="erinnerung"]') and pg.is_enabled('#hr-mail [data-hr-mail="steuerberater"]'))
    pg.fill('#hrm-stb-adresse', 'neu@example.org'); pg.select_option('#hrm-stb-tag', '12')
    check('… Änderung: Knöpfe gesperrt mit Hinweis „bitte speichern“', pg.is_disabled('#hr-mail [data-hr-mail="steuerberater"]') and 'speichern' in pg.text_content('#hr-mail-hinweis'))
    with pg.expect_response(lambda r_: 'action=hr_mail_save' in r_.url) as antwort:
        pg.click('#hr-mail [type="submit"]')
    pg.wait_for_function("document.querySelector('#hr-mail [data-hr-mail=steuerberater]') && !document.querySelector('#hr-mail [data-hr-mail=steuerberater]').disabled")
    me_ = P.call('mitarbeiter_hr')[1]['mail']['einst']['steuerberater']
    check('Oberfläche: E-Mail-Einstellungen gespeichert, Knöpfe wieder frei', antwort.value.status == 200 and me_['adresse'] == 'neu@example.org' and me_['tag'] == 12, me_)
    n0 = len(smtp.messages)
    pg.click('#hr-mail [data-hr-mail="steuerberater"]'); pg.wait_for_selector('#dlg-confirm[open]')
    check('… Senden fragt nach (Adresse und Monate)', 'neu@example.org' in pg.text_content('#confirm-body') and mtext(VOR) in pg.text_content('#confirm-body'))
    with pg.expect_response(lambda r_: 'action=hr_steuerberater_senden' in r_.url) as antwort:
        pg.click('#confirm-body .btn.primary')
    until(lambda: len(smtp.messages) >= n0 + 1)
    pg.wait_for_selector('#hrm-verlauf li')
    check('Oberfläche: Übersicht an den Steuerberater gesendet, Verlauf zeigt den Versand', antwort.value.status == 200 and smtp.messages[n0]['to'] == ['neu@example.org']
          and 'Steuerberater' in pg.text_content('#hrm-verlauf li'))
    check('… Verlauf nennt die Bitte um Erklärung (unentschuldigt) mit Namen', 'Unentschuldigt: Bitte um Erklärung an Fritz Frist' in pg.text_content('#hrm-verlauf'), pg.text_content('#hrm-verlauf')[:300])
    pg.locator('#hr-mail').screenshot(path=os.path.join(SH, 'hr_verwaltung_mails_1280.png'))
    assert P.call('hr_mail_save', {'steuerberater': {'an': False, 'adresse': 'kanzlei@example.org', 'tag': 5}})[0] == 200
    # Schalter „Urlaubsanträge über die Plattform“: sofort wirksam, ohne „Speichern“
    check('Verwaltung → Urlaub: Schalter „Urlaubsanträge“ eingeschaltet', pg.is_checked('#hr-antraege') and pg.text_content('#hr-antraege-t') == 'Eingeschaltet')
    pg.click('#hr-antraege'); pg.wait_for_function('document.querySelector("#hr-antraege-t").textContent === "Ausgeschaltet" && !document.querySelector("#hr-antraege").disabled')
    check('Oberfläche: Urlaubsanträge per Schalter ausgeschaltet', P.call('mitarbeiter_hr')[1]['antraege'] is False and not pg.is_checked('#hr-antraege'))
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_urlaub_antraege_aus_1280.png'), full_page=True)
    ctx.close()
    # Mitarbeiterin sieht kein Antragsformular, sondern den Hinweis (Desktop und Handy)
    for breite in (1280, 390):
        ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', breite)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-konto .hr-wert')
        check(f'{breite}px: Urlaubsanträge aus – Formular ausgeblendet, Hinweis sichtbar, „Meine Einträge“ bleibt',
              pg.is_hidden('#antrag') and pg.is_visible('#antrag-aus') and 'Personalstelle' in pg.text_content('#antrag-aus')
              and pg.is_hidden('#antrag-aus a') and pg.is_visible('#mein-liste')
              and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_mein_antraege_aus_{breite}.png'), full_page=True)
        ctx.close()
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5', 390)
    pg.goto(B + '/admin/#urlaub'); pg.wait_for_selector('#hr-uebertrag-bis')
    check('390px Verwaltung → Urlaub: Verfallstag und Schalter ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
          and pg.is_visible('#hr-antraege-t') and pg.text_content('#hr-antraege-t') == 'Ausgeschaltet')
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_urlaub_390.png'), full_page=True)
    pg.locator('#hr-mail').screenshot(path=os.path.join(SH, 'hr_verwaltung_mails_390.png'))
    pg.click('#hr-antraege'); pg.wait_for_function('document.querySelector("#hr-antraege-t").textContent === "Eingeschaltet" && !document.querySelector("#hr-antraege").disabled')
    check('Oberfläche: Urlaubsanträge wieder eingeschaltet', P.call('mitarbeiter_hr')[1]['antraege'] is True and pg.is_checked('#hr-antraege'))
    pg.goto(B + '/admin/#users'); pg.wait_for_selector(f'#view-users tr[data-hr-uid="{ids["erika"]}"]')
    pg.click(f'#view-users tr[data-hr-uid="{ids["erika"]}"]'); pg.wait_for_selector('#dlg-hr-person[open] [name="hr_verfall"]')
    check('390px Mitarbeiter-Dialog: „Resturlaub verfällt“ sichtbar, ohne waagerechtes Scrollen', pg.is_visible('#dlg-hr-person [name="hr_verfall"]')
          and pg.evaluate("(() => { const d = document.querySelector('#dlg-hr-person'); return d.scrollWidth <= d.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; })()"))
    pg.locator('#dlg-hr-person').screenshot(path=os.path.join(SH, 'hr_verwaltung_verfall_dialog_390.png'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-hr-person[open]', state='hidden')
    pg.goto(B + '/module/hr/#kalender'); pg.wait_for_selector('#kal-eintragen:not([hidden])')
    pg.click('#kal-eintragen'); pg.wait_for_selector('#dlg-eintrag[open]')
    pg.select_option('#eintrag-art', 'F'); pg.wait_for_selector('#eintrag-mail-feld:not([hidden])')
    check('390px Dialog „Abwesenheit eintragen“ mit „Unentschuldigt“: Haken sichtbar, ohne waagerechtes Scrollen', pg.is_visible('#eintrag-mail')
          and pg.evaluate("(() => { const d = document.querySelector('#dlg-eintrag'); return d.scrollWidth <= d.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; })()"))
    pg.locator('#dlg-eintrag').screenshot(path=os.path.join(SH, 'hr_eintrag_unentschuldigt_390.png'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-eintrag[data-warnung]')   # geändert: erst Rückfrage, dann schließen
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-eintrag[open]', state='hidden')
    ctx.close()

    # ── Verwaltung → Mitarbeiter: Eintrag ohne Mitarbeiter einzeln zuordnen (abweichender Name) ──
    alt = dokument('hr-personal')
    alt['personen'].append({'id': 'pute', 'vorname': 'Ute', 'nachname': 'Neu', 'abteilung': 'Lager', 'pos': 43, 'aktiv': True, 'personalnummer': '9903'})
    alt['rev'] = alt.get('rev', 0) + 1
    storage_write('hr-personal', alt)
    for breite in (390, 1280):
        ctx, pg = anmelden('admin', PW, '198.51.100.2', breite)
        pg.goto(B + '/admin/#users'); pg.wait_for_selector('#hr-alt [data-hr-alt-einzeln]')
        check(f'{breite}px: Hinweis nennt ehemalige Mitarbeiter, „Einzeln zuordnen“ vorne', 'ehemalige Mitarbeiter' in pg.text_content('#hr-alt')
              and pg.locator('#hr-alt .btn.primary[data-hr-alt-einzeln]').count() == 1)
        pg.locator('#hr-alt').screenshot(path=os.path.join(SH, f'hr_ehemalige_hinweis_{breite}.png'))
        pg.click('#hr-alt [data-hr-alt-einzeln]'); pg.wait_for_selector('#dlg-hr-alt[open] li[data-eintrag="pute"]')
        breit = pg.evaluate("document.querySelector('#dlg-hr-alt').scrollWidth <= document.querySelector('#dlg-hr-alt').clientWidth + 1")
        check(f'{breite}px: Dialog „Einzeln zuordnen“ mit Eintrag und Mitarbeiterauswahl, ohne waagerechtes Scrollen', breit and pg.locator('#dlg-hr-alt li[data-eintrag="pute"] select option').count() > 3)
        pg.screenshot(path=os.path.join(SH, f'hr_alt_zuordnen_{breite}.png'))
        if breite == 1280:
            check('Vorschlag: eindeutig gleicher Nachname vorausgewählt (Nina Neu)', pg.input_value('#dlg-hr-alt li[data-eintrag="pute"] select') == ids['nina'])
            pg.click('#dlg-hr-alt li[data-eintrag="pute"] [data-zuordnen]'); pg.wait_for_selector('#dlg-hr-alt li[data-eintrag="pute"] .form-err:not(:empty)')
            check('Fehler des Servers im Dialog (verschiedene Personalnummern)', 'Personalnummern' in pg.text_content('#dlg-hr-alt li[data-eintrag="pute"] .form-err'))
            pg.select_option('#dlg-hr-alt li[data-eintrag="pute"] select', '')
            pg.click('#dlg-hr-alt li[data-eintrag="pute"] [data-zuordnen]'); pg.wait_for_function("document.querySelector('#dlg-hr-alt li[data-eintrag=\"pute\"] .form-err').textContent.includes('wählen')")
            check('ohne Auswahl: Hinweis im Dialog', 'Mitarbeiter wählen' in pg.text_content('#dlg-hr-alt li[data-eintrag="pute"] .form-err'))
            pg.select_option('#dlg-hr-alt li[data-eintrag="pute"] select', ids['otto'])
            pg.click('#dlg-hr-alt li[data-eintrag="pute"] [data-zuordnen]')
            pg.wait_for_selector('#dlg-hr-alt li[data-eintrag="pute"]', state='detached')
            pn = [p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer'] == ids['otto']]
            check('Oberfläche: Eintrag dem gewählten Mitarbeiter zugeordnet (zusammengeführt, Personalnummer übernommen)', len(pn) == 1 and pn[0]['personalnummer'] == '9903'
                  and 'pute' not in [p_['id'] for p_ in P.call('mitarbeiter_hr')[1]['personen']], pn)
        ctx.close()

    # ── Verwaltung → Mitarbeiter (Administrator): anlegen ohne Anmeldung, HR-Teil im Dialog ──
    ctx, pg = anmelden('admin', PW, '198.51.100.2')
    pg.click('#vt-users'); pg.wait_for_selector('#view-users tr[data-uid]')
    check('Navigation heißt „Mitarbeiter“, Spalten Abteilung und Urlaub', pg.text_content('#vt-users').strip() == 'Mitarbeiter' and 'Abteilung' in pg.text_content('#view-users thead')
          and 'Urlaub' in pg.text_content('#view-users thead'))
    pg.click('#user-add'); pg.wait_for_selector('#dlg-user[open]')
    pg.check('#user-body [name="zugang"][value="0"]')
    check('ohne Anmeldung: keine Felder für Passwort, Rolle, Rechte', pg.is_hidden('#user-body [name="password"]') and pg.is_hidden('#user-body .role-pick:not(.us-zugang)') and pg.is_visible('#hr-teil'))
    pg.fill('#user-body [name="vorname"]', 'Lisa'); pg.fill('#user-body [name="nachname"]', 'Lager')
    pg.fill('#user-body [name="hr_abteilung"]', 'Lager'); pg.uncheck('#user-body [name="hr_tag"][value="5"]'); pg.fill('#user-body [name="hr_anspruch"]', '25')
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_mitarbeiter_neu_1280.png'), full_page=True)
    pg.click('#user-body [type="submit"]'); pg.wait_for_selector('#dlg-user[open]', state='hidden')
    lisa = next(u for u in A.call('users')[1]['users'] if u['name'] == 'Lisa Lager')
    pl = {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}[lisa['id']]
    check('Oberfläche: Mitarbeiter ohne Anmeldung mit HR-Angaben angelegt', lisa['zugang'] is False and pl['abteilung'] == 'Lager' and pl['arbeitstage'] == [1, 2, 3, 4]
          and pl['jahre'][str(dt.date.today().year)]['anspruch'] == 25, (lisa, pl))
    pg.wait_for_selector(f'#view-users tr[data-uid="{lisa["id"]}"]')
    check('Liste: „ohne Anmeldung“ statt Benutzername und Rolle', 'ohne Anmeldung' in pg.text_content(f'#view-users tr[data-uid="{lisa["id"]}"]'))
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_mitarbeiter_1280.png'), full_page=True)
    # eigener Eintrag: Urlaubsangaben gesperrt (Vier-Augen-Prinzip), Speichern des Dialogs funktioniert trotzdem
    pg.click(f'#view-users tr[data-uid="{ids["admin"]}"]'); pg.wait_for_selector('#dlg-user[open] #hr-teil')
    gesperrt = pg.evaluate('''["hr_anspruch", "hr_uebertrag", "hr_personalnummer", "hr_aktiv", "hr_verfall"].every((n) => document.querySelector(`#hr-teil [name="${n}"]`).disabled)
        && [...document.querySelectorAll('#hr-teil [name="hr_tag"]')].every((x) => x.disabled) && !document.querySelector('#hr-teil [name="hr_abteilung"]').disabled''')
    check('eigener Eintrag: Urlaubsangaben gesperrt mit Hinweis, Abteilung frei', gesperrt and 'andere Person der Personalstelle' in pg.text_content('#hr-teil'))
    sicht = pg.evaluate('''(() => { const a = getComputedStyle(document.querySelector('#hr-teil [name="hr_anspruch"]')), f = getComputedStyle(document.querySelector('#hr-teil [name="hr_abteilung"]'));
        const h = document.querySelector('#hr-teil .hr-eigen-hinweis'), l = document.querySelector('#hr-teil legend');
        return { grau: a.backgroundColor !== f.backgroundColor, cursor: a.cursor, oben: !!h && !!(l.compareDocumentPosition(h) & 4) && !!(h.compareDocumentPosition(document.querySelector('#hr-teil [name="hr_abteilung"]')) & 4) }; })()''')
    check('… gesperrte Felder sehen gesperrt aus (anderer Grund, Zeiger „nicht erlaubt“), Hinweis oben', sicht['grau'] and sicht['cursor'] == 'not-allowed' and sicht['oben'], sicht)
    pg.locator('#hr-teil').screenshot(path=os.path.join(SH, 'hr_verwaltung_eigene_angaben_1280.png'))
    pg.fill('#hr-teil [name="hr_abteilung"]', 'Geschäftsführung')
    pg.click('#user-body [type="submit"]'); pg.wait_for_selector('#dlg-user[open]', state='hidden')
    check('… Speichern des eigenen Dialogs klappt (Abteilung geändert)', {p_['nutzer']: p_ for p_ in P.call('mitarbeiter_hr')[1]['personen'] if p_['nutzer']}[ids['admin']]['abteilung'] == 'Geschäftsführung')
    ctx.close()
    # Nur „Urlaub genehmigen“ (Gina): Reiter Anträge mit Knöpfen, ohne Personalstelle (Alle Einträge, Export, Verwaltungs-Links)
    for breite in (1280, 390):
        ctx, pg = anmelden('gina', 'Genehmigen-Zugang-77', '198.51.100.8', breite)
        pg.goto(B + '/module/hr/#antraege'); pg.wait_for_selector('.hr-antrag [data-genehmigen]')
        check(f'{breite}px Genehmigende: Anträge mit Knöpfen, ohne Export und „Alle Einträge“', pg.is_visible('[data-tab="antraege"]') and not pg.is_visible('[data-tab="export"]')
              and not pg.is_visible('#eintraege-tabelle') and not pg.is_visible('[data-verwaltung-link="users"]'))
        check(f'{breite}px Genehmigende: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_genehmigen_{breite}.png'), full_page=True)
        ctx.close()
    # Personalstelle ohne Genehmigungsrecht (Vera): Anträge sichtbar, aber ohne Knöpfe, mit Hinweis
    ctx, pg = anmelden('vera', 'Genehmigen-Zugang-77', '198.51.100.9')
    pg.goto(B + '/module/hr/#antraege'); pg.wait_for_selector('.hr-antrag .hr-hinweis')
    check('Personalstelle ohne „Urlaub genehmigen“: Hinweis statt Knöpfe, „Alle Einträge“ sichtbar', pg.locator('.hr-antrag [data-genehmigen]').count() == 0
          and 'Urlaub genehmigen' in pg.text_content('.hr-antrag .hr-hinweis') and pg.is_visible('#eintraege-tabelle'))
    pg.screenshot(path=os.path.join(SH, 'hr_antraege_ohne_genehmigen_1280.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.goto(B + '/module/hr/')
    pg.wait_for_selector('#hr-app:not([hidden])')
    # Antrag genehmigen in der Oberfläche
    pg.click('[data-tab="antraege"]'); pg.wait_for_selector('.hr-antrag')
    pg.screenshot(path=os.path.join(SH, 'hr_antraege_1280.png'), full_page=True)
    pg.click('.hr-antrag [data-genehmigen]'); pg.wait_for_selector('.hr-leer')
    check('Oberfläche: Antrag genehmigt, keine offenen mehr', P.call('hr_verwaltung&jahr=' + str(Y))[1]['offen'] == [])

    # Kalender der Personalstelle: Krankheit über den Monatswechsel nahe heute (für „± 2 Wochen“)
    heute_ = dt.date.today()
    grenze = dt.date(heute_.year + (heute_.month == 12), heute_.month % 12 + 1, 1)   # erster Tag des nächsten Monats
    if (grenze - heute_).days > 14: grenze = heute_.replace(day=1)
    PO = PE   # aktiv im Urlaubsplan, ohne Einträge in diesen Wochen
    st, r = P.call('hr_eintrag_save', {'person': PO, 'art': 'K', 'von': iso(grenze - dt.timedelta(days=3)), 'bis': iso(grenze + dt.timedelta(days=3))})
    check('Krankheit über den Monatswechsel eingetragen', st == 200, r)
    pg.click('[data-tab="kalender"]'); pg.wait_for_selector('#kal-plan tbody tr')
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_1280.png'), full_page=True)
    # Abteilungen als durchgehender, dunklerer Balken mit Anzahl
    balken = pg.evaluate('''(() => {
      const rows = [...document.querySelectorAll('#kal-plan tbody tr')], spalten = document.querySelectorAll('#kal-plan thead th').length;
      let ok = true, cur = null, n = 0;
      const fertig = () => { if (cur && Number(cur.querySelector('small').textContent) !== n) ok = false; };
      for (const r of rows) { if (r.classList.contains('abt')) { fertig(); cur = r; n = 0; } else n++; }
      fertig();
      // Balken = alle Zellen der Zeile (im Monat mit „heute“ geteilt: Titel · Heute-Säule · Rest), zusammen volle Breite in der Balkenfarbe
      const tr = document.querySelector('#kal-plan tr.abt'), th = tr.querySelector('th'), name = document.querySelector('#kal-plan tbody th.name');
      const zellen = [...tr.children], breite = zellen.reduce((s, c) => s + c.getBoundingClientRect().width, 0);
      return { ok, volle: zellen.reduce((s, c) => s + c.colSpan, 0) === spalten && Math.abs(breite - document.querySelector('#kal-plan').getBoundingClientRect().width) < 2
                 && zellen.every((c) => getComputedStyle(c).backgroundColor === getComputedStyle(th).backgroundColor),
               farbe: getComputedStyle(th).backgroundColor !== getComputedStyle(name).backgroundColor };
    })()''')
    check('Kalender: Abteilung als Balken über die volle Breite, abgesetzte Farbe, Anzahl der Mitarbeiter', balken['ok'] and balken['volle'] and balken['farbe'], balken)
    # Filter nach Abteilungen (mehrere wählbar, merkt sich der Browser)
    baender = lambda: pg.eval_on_selector_all('#kal-plan tr.abt th > span', 'e => e.map((x) => x.firstChild.textContent)')   # noqa: E731
    alle_abt = baender()
    check('Filter: „Alle“ und je Abteilung ein Knopf', pg.locator('#kal-filter [data-abt]').count() == len(alle_abt) + 1 and pg.get_attribute('#kal-filter [data-abt="*"]', 'aria-pressed') == 'true', alle_abt)
    pg.click('#kal-filter [data-abt="Lager"]'); pg.wait_for_function("document.querySelectorAll('#kal-plan tr.abt').length === 1")
    check('Filter: nur Lager', baender() == ['Lager'] and pg.get_attribute('#kal-filter [data-abt="Lager"]', 'aria-pressed') == 'true'
          and pg.get_attribute('#kal-filter [data-abt="*"]', 'aria-pressed') == 'false', baender())
    pg.click('#kal-filter [data-abt="Verwaltung"]'); pg.wait_for_function("document.querySelectorAll('#kal-plan tr.abt').length === 2")
    pg.reload(); pg.wait_for_selector('#kal-plan tr.abt')
    check('Filter: Lager und Verwaltung, nach Neuladen erhalten', sorted(baender()) == ['Lager', 'Verwaltung'], baender())
    pg.click('#kal-filter [data-abt="*"]'); pg.wait_for_function(f"document.querySelectorAll('#kal-plan tr.abt').length === {len(alle_abt)}")
    check('Filter: „Alle“ zeigt wieder alle Abteilungen', baender() == alle_abt)
    # Ansicht „± 2 Wochen“: heute in der Mitte, über den Monatswechsel, Pfeile je eine Woche
    erster = lambda: pg.get_attribute('#kal-plan thead th:nth-child(2)', 'title')[:10]   # noqa: E731
    de_ = lambda d: d.strftime('%d.%m.%Y')   # noqa: E731
    pg.click('#kal-modus [data-modus="zeitraum"]'); pg.wait_for_function("document.querySelectorAll('#kal-plan thead th').length === 30")
    check('± 2 Wochen: 29 Tage, beginnt 14 Tage vor heute, heute in der Mitte', erster() == de_(heute_ - dt.timedelta(days=14))
          and pg.evaluate("[...document.querySelectorAll('#kal-plan thead th')].findIndex((th) => th.classList.contains('heute'))") == 15, erster())
    von_, bis_ = heute_ - dt.timedelta(days=14), heute_ + dt.timedelta(days=14)
    erwartet = 0
    for j, m in sorted({(von_.year, von_.month), (bis_.year, bis_.month)}):
        zeile = next(p_ for p_ in P.call(f'hr_monat&jahr={j}&monat={m}')[1]['personen'] if p_['id'] == PO)
        erwartet += sum(1 for tag, k in zeile['tage'].items() if k == 'K' and von_ <= dt.date(j, m, int(tag)) <= bis_)
    ui = pg.evaluate(f"document.querySelector('#kal-plan td[data-person=\"{PO}\"]').closest('tr').querySelectorAll('.hr-art.K').length")
    wechsel = von_.month != bis_.month
    check('± 2 Wochen: Einträge aus beiden Monaten (wie der Server je Monat), Trennlinie am Monatswechsel', ui == erwartet and (ui > 0 or not wechsel)
          and pg.locator('#kal-plan thead th.mstart').count() == (1 if wechsel else 0), (ui, erwartet, wechsel))
    # Heute-Säule (Inhaber 30.10.2026): Kopf „Heute“ mit Datum im Kreis, Kanten durch alle Zeilen und Abteilungsbalken, Legende
    hs = pg.evaluate('''() => {
      const th = document.querySelector('#kal-plan thead th.heute'), abt = [...document.querySelectorAll('#kal-plan tr.abt')];
      const breite = (tr) => [...tr.children].reduce((s, c) => s + (c.colSpan || 1), 0);
      const td = document.querySelector('#kal-plan tbody tr:not(.abt) td.heute');
      return { aktuell: th.getAttribute('aria-current'), klein: th.querySelector('small').textContent, kreis: th.querySelector('.hr-heute-tag').textContent,
               abtHeute: abt.every((tr) => tr.querySelectorAll('td.heute').length === 1 && breite(tr) === 30), kante: getComputedStyle(td).boxShadow,
               monat: (document.querySelector('#kal-plan thead th.mstart') ? getComputedStyle(document.querySelector('#kal-plan thead th.mstart')).borderLeftColor : '') };
    }''')
    check('Heute-Säule: Kopf „Heute“ mit Datum im Kreis (aria-current), Kanten in jeder Zeile, Abteilungsbalken durchlaufend',
          hs['aktuell'] == 'date' and hs['klein'] == 'Heute' and hs['kreis'] in (str(heute_.day), f'1.{heute_.month:02d}.') and hs['abtHeute']
          and hs['kante'].count('inset') == 2, hs)
    check('Monatswechsel neutral grau (Bordeaux nur für „heute“), Legende nennt „Heute“', (not wechsel or hs['monat'] == 'rgba(28, 26, 25, 0.28)')
          and 'Heute' in pg.text_content('#kal-legende'), hs['monat'])
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_2wochen_1280.png'), full_page=True)
    pg.emulate_media(color_scheme='dark')
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_1280_dunkel.png'), full_page=True)
    check('dunkles Design: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)', pg.evaluate('getComputedStyle(document.body).backgroundColor'))
    pg.emulate_media(color_scheme='light')
    pg.click('#tab-kalender [data-monat="1"]'); pg.wait_for_function(f"document.querySelector('#kal-plan thead th:nth-child(2)').title.startsWith('{de_(heute_ - dt.timedelta(days=7))}')")
    check('± 2 Wochen: Pfeil verschiebt um eine Woche', erster() == de_(heute_ - dt.timedelta(days=7)))
    pg.click('#kal-heute'); pg.wait_for_function(f"document.querySelector('#kal-plan thead th:nth-child(2)').title.startsWith('{de_(heute_ - dt.timedelta(days=14))}')")
    pg.reload(); pg.wait_for_selector('#kal-plan tbody tr')
    check('„Heute“ zurück zur Mitte, Ansicht nach Neuladen erhalten', pg.locator('#kal-plan thead th').count() == 30 and erster() == de_(heute_ - dt.timedelta(days=14)))
    pg.click('#kal-modus [data-modus="monat"]')
    tage_monat = ((dt.date(heute_.year + (heute_.month == 12), heute_.month % 12 + 1, 1)) - heute_.replace(day=1)).days
    pg.wait_for_function(f"document.querySelectorAll('#kal-plan thead th').length === {tage_monat + 1}")
    check('zurück zur Monatsansicht (aktueller Monat)', erster() == de_(heute_.replace(day=1)))
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
    # Unentschuldigt (F): Haken „E-Mail an den Mitarbeiter“ nur bei F (vorausgewählt), Ergebnis als Meldung im Kalender
    pg.click('#kal-eintragen'); pg.wait_for_selector('#dlg-eintrag[open]')
    check('Oberfläche: Haken „E-Mail“ nur bei „Unentschuldigt“', pg.is_hidden('#eintrag-mail-feld') and pg.locator('#eintrag-art option[value="F"]').count() == 1)
    ftag = montag(Y, 3, 3) + dt.timedelta(days=2)   # Mittwoch im März
    pg.select_option('#eintrag-person', PE); pg.select_option('#eintrag-art', 'F')
    pg.fill('#eintrag-von', iso(ftag)); pg.dispatch_event('#eintrag-von', 'change')
    pg.wait_for_selector('#eintrag-mail-feld:not([hidden])')
    check('… bei F sichtbar und vorausgewählt', pg.is_checked('#eintrag-mail'))
    pg.screenshot(path=os.path.join(SH, 'hr_eintrag_unentschuldigt_1280.png'))
    n0 = len(smtp.messages)
    pg.click('#eintrag-speichern'); pg.wait_for_selector('#dlg-eintrag[open]', state='hidden')
    pg.wait_for_selector('#kal-meldung.ok')
    until(lambda: len(smtp.messages) >= n0 + 1)
    fz = [e for e in P.call(f'hr_verwaltung&jahr={Y}')[1]['eintraege'] if e['person'] == PE and e['art'] == 'F']
    check('Oberfläche: F eingetragen, Meldung „E-Mail … gesendet“, Mail an Erika', len(fz) == 1 and fz[0]['von'] == iso(ftag)
          and 'erika@example.org gesendet' in pg.text_content('#kal-meldung') and smtp.messages[n0]['to'] == ['erika@example.org'], (fz, pg.text_content('#kal-meldung')))
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_unentschuldigt_meldung_1280.png'))
    for _ in range(24):   # Monatsansicht bis März des Testjahres weiterblättern
        alt_ = pg.text_content('#kal-titel')
        if alt_ == f'März {Y}': break
        pg.click('#tab-kalender [data-monat="1"]'); pg.wait_for_function(f"document.querySelector('#kal-titel').textContent !== {json.dumps(alt_)}")
    pg.wait_for_selector(f'#kal-plan td[data-person="{PE}"][data-datum="{iso(ftag)}"] .hr-art')
    fzl = pg.locator(f'#kal-plan td[data-person="{PE}"][data-datum="{iso(ftag)}"] .hr-art')
    check('Kalender der Personalstelle: Tag als „F“ mit Titel „Unentschuldigt“, Legende nennt es', fzl.get_attribute('class') == 'hr-art F' and fzl.text_content() == 'F'
          and fzl.get_attribute('title') == 'Unentschuldigt' and 'unentschuldigt' in pg.text_content('#kal-legende'), (fzl.get_attribute('class'), fzl.get_attribute('title')))
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_unentschuldigt_1280.png'), full_page=True)
    pg.emulate_media(color_scheme='dark')
    pg.wait_for_function("getComputedStyle(document.body).backgroundColor === 'rgb(18, 16, 17)'")
    check('… dunkel: F in hellem Lila', fzl.evaluate('e => getComputedStyle(e).color') == 'rgb(196, 181, 253)', fzl.evaluate('e => getComputedStyle(e).color'))
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_unentschuldigt_1280_dunkel.png'), full_page=True)
    pg.emulate_media(color_scheme='light')
    for e_ in fz: P.call('hr_eintrag_save', {'id': e_['id'], 'stornieren': True})

    # Export in der Oberfläche
    pg.click('[data-tab="export"]'); pg.wait_for_selector('#export-jahr option', state='attached')
    with pg.expect_download() as dl:
        pg.click('#export button[type="submit"]')
    check('Oberfläche: Excel-Download', dl.value.suggested_filename.startswith('Urlaub_') and dl.value.suggested_filename.endswith('.xlsx'), dl.value.suggested_filename)
    pg.screenshot(path=os.path.join(SH, 'hr_export_1280.png'))
    ctx.close()

    # ── Jahresplanung (Oberfläche, Inhaber 03.11.2026): Hinweis mit Stand für Mitarbeiter, Vertretung Pflicht im Antrag, Reiter
    #    „Jahresplanung“ für Personalstelle und Genehmigende (Kennzahlen, Zeitleiste, Konflikte, Filter, gesammelt genehmigen,
    #    ablehnen, Erinnerung, Abschluss mit Jahresübersicht, wieder öffnen), Einstellungen in Verwaltung → Urlaub ──
    PLAN_ALT = P.call('mitarbeiter_hr')[1]['planung']

    def plan_setzen(**w):
        v2 = P.call('mitarbeiter_hr')[1]
        st_, r_ = P.call('hr_einstellungen_save', {'sperren': v2['sperren'], 'ferien': v2['ferien'], 'planung': {**v2['planung'], **w}})
        assert st_ == 200, r_
    plan_setzen(start='01-01', stichtag='12-31', prozent=90, vertretungPflicht=True)   # Hinweis an jedem Tag sichtbar, Planungsjahr = Y
    planung = lambda: P.call(f'hr_planung&jahr={Y}')[1]   # noqa: E731
    JP1, JP2 = montag(Y, 11, 1), montag(Y, 11, 2)          # erste zwei Novemberwochen (Weihnachtssperre erst in der letzten)
    # Erika (Personalstelle trägt ein, genehmigt) in Woche 2 am Dienstag; Lena beantragt Woche 2 mit Erika als Vertretung → Konflikt
    st, r = P.call('hr_eintrag_save', {'person': PE, 'art': 'U', 'von': iso(JP2 + dt.timedelta(days=1)), 'bis': iso(JP2 + dt.timedelta(days=1))})
    JP_E = r['eintrag']['id'] if st == 200 else None
    st, r = L.call('hr_antrag', {'von': iso(JP2), 'bis': iso(JP2 + dt.timedelta(days=2)), 'vertretung': PE})
    JP_L = r['eintrag']['id'] if st == 200 else None
    check('Jahresplanung: Daten für die Oberfläche (Eintrag Erika, Antrag Lena mit Vertretung)', JP_E and JP_L, r)
    vor_ = E.call('hr_start')[1]['planung']
    for breite in (1280, 390):
        ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', breite)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-planung:not([hidden]) .hr-mp-balken')
        txt = pg.text_content('#mein-planung')
        sp_ = E.call('hr_start')[1]['planung']
        check(f'{breite}px Mitarbeiter: Hinweis „Urlaubsplanung {Y}“ mit Ziel ({sp_["prozent"]} %, {sp_["ziel"]:g} von {sp_["anspruch"]:g} Tagen), Stand und Knopf',
              f'Urlaubsplanung {Y}' in txt and '90 %' in txt and f'31.12.{Y - 1}' in txt and f'{sp_["ziel"]:g} von {sp_["anspruch"]:g} Tagen'.replace('.', ',') in txt
              and pg.is_visible('#mp-planen') and pg.locator('#mein-planung .ziel').count() >= 1
              and (('Ziel erreicht' in txt) if sp_['erreicht'] else (f'noch {sp_["fehlt"]:g}'.replace('.', ',') in txt)), txt[:300])
        check(f'{breite}px Mitarbeiter: Reiter „Jahresplanung“ nicht sichtbar (ohne Personal- oder Genehmigungsrecht)', not pg.is_visible('[data-tab="planung"]'))
        check(f'{breite}px Mitarbeiter: Seite ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_mein_planung_{breite}.png'), full_page=False)
        if breite == 1280:
            pg.click('#mp-planen')
            pg.wait_for_function(f"document.querySelector('#mein-titel').textContent.includes('{Y}') && document.activeElement && document.activeElement.id === 'antrag-von'")
            check('„Urlaub planen“: Ansicht des Planungsjahres, Fokus im Antrag; Vertretung ist Pflicht (ohne „optional“)', pg.text_content('#antrag-vertretung-opt') == ''
                  and pg.evaluate("document.querySelector('#antrag-vertretung').required") and 'bitte wählen' in pg.text_content('#antrag-vertretung option'))
            pg.fill('#antrag-von', iso(JP1)); pg.dispatch_event('#antrag-von', 'change')
            pg.fill('#antrag-bis', iso(JP1 + dt.timedelta(days=1))); pg.dispatch_event('#antrag-bis', 'change')
            pg.click('#antrag-senden'); pg.wait_for_selector('#antrag-meldung.fehler')
            check('ohne Vertretung: Hinweis im Formular, nichts gesendet', 'Vertretung' in pg.text_content('#antrag-meldung')
                  and E.call('hr_start')[1]['planung']['geplant'] == vor_['geplant'], pg.text_content('#antrag-meldung'))
            pg.select_option('#antrag-vertretung', PA)
            pg.click('#antrag-senden'); pg.wait_for_selector('#antrag-meldung.ok, #antrag-meldung.warn')
            nach_ = E.call('hr_start')[1]['planung']
            JP_A = next((e_['id'] for e_ in E.call(f'hr_start&jahr={Y}')[1]['eintraege'] if e_['von'] == iso(JP1) and e_['status'] == 'beantragt'), None)
            pg.wait_for_function(f"document.querySelector('#mp-stand') && document.querySelector('#mp-stand').textContent.includes('{nach_['geplant']:g}'.replace('.', ','))")
            check('Antrag mit Vertretung gestellt: Stand der Planung zählt die beantragten Tage mit', JP_A and nach_['beantragt'] == vor_['beantragt'] + 2 and nach_['geplant'] == vor_['geplant'] + 2,
                  (vor_, nach_))
        ctx.close()
    pl_ = planung()
    a_ = {a['id']: a for a in pl_['antraege']}
    check('Server: Erikas Antrag ohne Konflikt (gesammelt genehmigbar), Lenas mit Konflikt „Vertretung selbst abwesend“', a_.get(JP_A, {}).get('frei') is True
          and any('selbst abwesend' in k['text'] for k in a_.get(JP_L, {}).get('konflikte', [])), (a_.get(JP_A), a_.get(JP_L)))
    # Personalstelle (Paul, auch „Urlaub genehmigen“)
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.goto(B + f'/module/hr/#planung'); pg.wait_for_selector('#jp-zeitleiste .hr-jp-zl')
    if not pg.text_content('#jp-titel').endswith(str(Y)):   # Standard ist das nächste Jahr – sicherheitshalber
        pg.click('[data-pjahr="1"]'); pg.wait_for_function(f"document.querySelector('#jp-titel').textContent.endsWith('{Y}')")
    z_ = pl_['zahlen']
    check('Reiter „Jahresplanung“: Titel, Infozeile (Stichtag, Ziel), Kennzahlen wie der Server', pg.text_content('#jp-titel') == f'Jahresplanung {Y}'
          and f'Stichtag 31.12.{Y - 1}' in pg.text_content('#jp-info') and '90 %' in pg.text_content('#jp-info')
          and f'{z_["erreicht"]} / {z_["personen"]}' in pg.text_content('#jp-zahlen') and pg.locator('#jp-zahlen .hr-wert').count() == 4, pg.text_content('#jp-zahlen'))
    check('Zeitleiste: eine Zeile je Mitarbeiter, ein Balken je Antrag, Konflikte rot umrandet, Monatsköpfe', pg.locator('#jp-zeitleiste .hr-jp-zeile[data-jp-person]').count() == len(pl_['personen'])
          and pg.locator('#jp-zeitleiste .hr-jp-balken').count() == len(pl_['antraege'])
          and pg.locator(f'#jp-zeitleiste .hr-jp-balken.konflikt[data-jp-antrag="{JP_L}"]').count() == 1
          and pg.locator(f'#jp-zeitleiste .hr-jp-balken.konflikt[data-jp-antrag="{JP_A}"]').count() == 0 and pg.locator('#jp-zeitleiste .hr-jp-kopf .hr-jp-spur span').count() == 12,
          (pg.locator('#jp-zeitleiste .hr-jp-balken').count(), len(pl_['antraege'])))
    check('Aktionen der Personalstelle: Erinnerung, konfliktfreie genehmigen, abschließen', all(pg.locator(f'#jp-aktionen [data-jp="{k}"]').count() == 1 for k in ('erinnern', 'freigeben', 'abschliessen')))
    pg.screenshot(path=os.path.join(SH, 'hr_planung_1280.png'), full_page=True)
    pg.click(f'#jp-zeitleiste .hr-jp-balken[data-jp-antrag="{JP_L}"]'); pg.wait_for_selector(f'#jp-a-{JP_L}.hervor')
    check('Klick auf einen Balken: Antrag in der Liste hervorgehoben, Konflikt als Hinweis', 'selbst abwesend' in pg.text_content(f'#jp-a-{JP_L}') and pg.is_visible(f'#jp-a-{JP_L}'))
    pg.click('#jp-filter [data-jp-filter="konflikt"]'); pg.wait_for_selector('#jp-filter [data-jp-filter="konflikt"][aria-pressed="true"]')
    n_k = sum(1 for a in pl_['antraege'] if a['konflikte'])
    check('Filter „Mit Konflikt“: nur Anträge mit Konflikt', pg.locator('#jp-antraege .hr-jp-antrag').count() == n_k == pg.locator('#jp-antraege .hr-jp-antrag.konflikt').count()
          and pg.locator(f'#jp-a-{JP_A}').count() == 0, (pg.locator('#jp-antraege .hr-jp-antrag').count(), n_k))
    pg.click('#jp-filter [data-jp-filter="frei"]'); pg.wait_for_selector(f'#jp-a-{JP_A}')
    check('Filter „Konfliktfrei“: Erikas Antrag, ohne Konflikt-Hinweis', pg.locator('#jp-antraege .hr-jp-antrag.konflikt').count() == 0 and 'Kein Konflikt' in pg.text_content(f'#jp-a-{JP_A}'))
    pg.click('#jp-filter [data-jp-filter="alle"]')
    # Erinnerung (Erika hat eine Adresse und ist unter dem Ziel)
    n0 = len(smtp.messages)
    pg.click('#jp-aktionen [data-jp="erinnern"]'); pg.wait_for_selector('#dlg-frage[open]')
    check('Erinnerung: Rückfrage nennt die Zahl der Empfänger', str(z_['erinnern']) in pg.text_content('#fr-text') and 'Erinnerung' in pg.text_content('#fr-titel'))
    pg.click('#fr-ja'); pg.wait_for_selector('#jp-meldung.ok')
    until(lambda: len(smtp.messages) >= n0 + z_['erinnern'])
    check('… gesendet: Meldung mit Zahl, Mail an Erika', 'Erinnerung' in pg.text_content('#jp-meldung')
          and any(m_['to'] == ['erika@example.org'] and m_['subject'].startswith(f'Bitte planen Sie Ihren Urlaub {Y}') for m_ in smtp.messages[n0:]), [m_['subject'] for m_ in smtp.messages[n0:]])
    # Konfliktfreie gesammelt genehmigen
    pg.click('#jp-aktionen [data-jp="freigeben"]'); pg.wait_for_selector('#dlg-frage[open]')
    pg.click('#fr-ja'); pg.wait_for_selector('#jp-meldung.ok, #jp-meldung.warn')
    st_ = {e_['id']: e_['status'] for e_ in E.call(f'hr_start&jahr={Y}')[1]['eintraege']}
    check('„Konfliktfreie genehmigen“ (mit Rückfrage): Erikas Antrag genehmigt, Lenas mit Konflikt bleibt offen', st_.get(JP_A) == 'genehmigt'
          and next(a for a in planung()['antraege'] if a['id'] == JP_L)['status'] == 'beantragt' and 'genehmigt' in pg.text_content('#jp-meldung'), pg.text_content('#jp-meldung'))
    # Ablehnen mit Grund: Dialog, Planung lädt neu
    pg.click(f'#jp-a-{JP_L} [data-jp-ablehnen]'); pg.wait_for_selector('#dlg-ablehnen[open]')
    pg.fill('#ablehnen-grund', 'Vertretung ist in der Woche selbst nicht da')
    pg.click('#ablehnen-form [type="submit"]'); pg.wait_for_selector('#dlg-ablehnen[open]', state='hidden')
    pg.wait_for_function(f"!document.getElementById('jp-a-{JP_L}') && document.querySelector('#jp-meldung').textContent.includes('abgelehnt')")
    check('Ablehnen in der Jahresplanung: Antrag abgelehnt, Liste und Zeitleiste neu geladen', not any(a['id'] == JP_L for a in planung()['antraege'])
          and pg.locator(f'.hr-jp-balken[data-jp-antrag="{JP_L}"]').count() == 0)
    # Abschluss mit Jahresübersicht, danach wieder öffnen
    n0 = len(smtp.messages)
    pg.click('#jp-aktionen [data-jp="abschliessen"]'); pg.wait_for_selector('#dlg-frage[open]')
    check('Abschluss: Rückfrage nennt die Jahresübersicht', 'Jahresübersicht' in pg.text_content('#fr-text'))
    pg.click('#fr-ja'); pg.wait_for_function("document.querySelector('#jp-meldung').textContent.includes('abgeschlossen')")
    until(lambda: any(m_['to'] == ['erika@example.org'] and m_['subject'] == f'Ihre Urlaubsplanung {Y}' for m_ in smtp.messages[n0:]))
    check('… abgeschlossen: Infozeile, Knöpfe „erneut senden“ und „Wieder öffnen“, Mitarbeiter ohne Hinweis, Jahresübersicht an Erika',
          'abgeschlossen am' in pg.text_content('#jp-info') and pg.locator('#jp-aktionen [data-jp="oeffnen"]').count() == 1 and pg.locator('#jp-aktionen [data-jp="senden"]').count() == 1
          and pg.locator('#jp-aktionen [data-jp="abschliessen"]').count() == 0 and E.call('hr_start')[1]['planung'] is None)
    pg.emulate_media(color_scheme='dark')
    pg.wait_for_function('getComputedStyle(document.body).backgroundColor === "rgb(18, 16, 17)"')
    pg.screenshot(path=os.path.join(SH, 'hr_planung_1280_dunkel.png'), full_page=True)
    pg.emulate_media(color_scheme='light')
    pg.click('#jp-aktionen [data-jp="oeffnen"]'); pg.wait_for_selector('#dlg-frage[open]'); pg.click('#fr-ja')
    pg.wait_for_selector('#jp-aktionen [data-jp="abschliessen"]')
    check('Wieder öffnen: Planung offen, Mitarbeiter sehen den Hinweis wieder', E.call('hr_start')[1]['planung'] is not None and 'wieder geöffnet' in pg.text_content('#jp-meldung'))
    # Verwaltung → Urlaub: Einstellungen der Jahresplanung
    pg.goto(B + '/admin/#urlaub'); pg.wait_for_selector('#hr-plan-prozent')
    check('Verwaltung → Urlaub: Jahresplanung mit gespeicherten Werten (Hinweis ab, Stichtag, Anteil, Vertretung Pflicht)', pg.input_value('#hr-plan-start').endswith('-01-01')
          and pg.input_value('#hr-plan-stichtag').endswith('-12-31') and pg.input_value('#hr-plan-prozent') == '90' and pg.is_checked('#hr-plan-vertretung'))
    pg.fill('#hr-plan-prozent', '80')
    with pg.expect_response(lambda r_: 'action=hr_einstellungen_save' in r_.url) as antwort:
        pg.click('#hr-einst [type="submit"]')
    pg.wait_for_selector('#hr-plan-prozent')
    pg.locator('#hr-plan-prozent').scroll_into_view_if_needed()
    pg.screenshot(path=os.path.join(SH, 'hr_verwaltung_planung_1280.png'))
    check('… Anteil 80 % gespeichert, Werte bleiben nach dem Neuladen', antwort.value.status == 200 and P.call('mitarbeiter_hr')[1]['planung']['prozent'] == 80
          and pg.input_value('#hr-plan-prozent') == '80')
    pg.fill('#hr-plan-prozent', '5')
    check('… Anteil unter 10 % ist im Formular ungültig, gespeichert bleibt 80 %', not pg.evaluate("document.querySelector('#hr-plan-prozent').checkValidity()")
          and P.call('mitarbeiter_hr')[1]['planung']['prozent'] == 80)
    ctx.close()
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5', 390)
    pg.goto(B + '/module/hr/#planung'); pg.wait_for_selector('#jp-zeitleiste .hr-jp-zl')
    check('390px Jahresplanung: Seite ohne waagerechtes Scrollen, Zeitleiste in sich wischbar mit festen Namen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
          and pg.evaluate("(() => { const r = document.querySelector('#jp-zeitleiste'); return r.scrollWidth > r.clientWidth; })()")
          and pg.evaluate("getComputedStyle(document.querySelector('#jp-zeitleiste .hr-jp-zeile[data-jp-person] .hr-jp-name')).position") == 'sticky')
    pg.screenshot(path=os.path.join(SH, 'hr_planung_390.png'), full_page=True)
    ctx.close()
    # Nur „Urlaub genehmigen“ (Gina): Reiter sichtbar, nur gesammelt genehmigen – kein Erinnern, kein Abschluss
    ctx, pg = anmelden('gina', 'Genehmigen-Zugang-77', '198.51.100.8')
    pg.goto(B + '/module/hr/#planung'); pg.wait_for_selector('#jp-zeitleiste .hr-jp-zl')
    check('Genehmigende: Reiter „Jahresplanung“ mit „Konfliktfreie genehmigen“, ohne Erinnern und Abschluss', pg.is_visible('[data-tab="planung"]')
          and pg.locator('#jp-aktionen [data-jp="freigeben"]').count() == 1 and pg.locator('#jp-aktionen [data-jp="erinnern"], #jp-aktionen [data-jp="abschliessen"]').count() == 0)
    ctx.close()
    check('Jahresplanung: keine JavaScript-Fehler', not fehler, fehler)
    # Aufräumen: eigene Einträge stornieren, Planung zurück (Vertretung freiwillig für die folgenden Antragstests)
    for id_ in (JP_A, JP_E):
        if id_: P.call('hr_eintrag_save', {'id': id_, 'stornieren': True})
    plan_setzen(start=PLAN_ALT['start'], stichtag=PLAN_ALT['stichtag'], prozent=PLAN_ALT['prozent'], vertretungPflicht=False)

    # Hinweis „Resturlaub verfällt bald“: Verfallstag in 20 Tagen (laufendes Jahr), 3 Tage Übertrag
    J = dt.date.today().year
    frist = min(dt.date.today() + dt.timedelta(days=20), dt.date(J, 12, 31))
    if (frist.month, frist.day) == (2, 29): frist = dt.date(J, 2, 28)
    v_ = P.call('mitarbeiter_hr')[1]
    assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'uebertragBis': frist.strftime('%m-%d')})[0] == 200
    pe_ = next(p_ for p_ in v_['personen'] if p_['nutzer'] == ids['erika'])
    rev = v_['rev']; hr(ids['erika'], jahr=J, anspruch=(pe_['jahre'].get(str(J)) or {}).get('anspruch'), uebertrag=3)
    k_e = E.call('hr_start')[1]['konto']
    check('Konto: 3 Tage Übertrag verfallen in 20 Tagen', k_e['verfaellt'] == 3 and k_e['frist'] == frist.isoformat(), k_e)
    for breite in (1280, 390):
        ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', breite, verfall_hinweis=True)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#dlg-verfall[open]')
        t_ = pg.text_content('#verfall-text')
        check(f'{breite}px: Pop-up „Resturlaub verfällt bald“ mit Tagen und Datum, ohne waagerechtes Scrollen', '3 Tage' in t_ and frist.strftime('%d.%m.%Y') in t_
              and pg.is_visible('#verfall-planen') and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), t_)
        pg.screenshot(path=os.path.join(SH, f'hr_verfall_hinweis_{breite}.png'))
        if breite == 1280:
            pg.click('#dlg-verfall .hr-knoepfe [data-schliessen]'); pg.wait_for_selector('#dlg-verfall[open]', state='hidden')
            pg.reload(); pg.wait_for_selector('#hr-app:not([hidden]) #mein-konto .hr-wert')
            check('… höchstens einmal am Tag', not pg.evaluate("document.querySelector('#dlg-verfall').open"))
        else:
            pg.click('#verfall-planen'); pg.wait_for_selector('#dlg-verfall[open]', state='hidden')
            check('… „Urlaub beantragen“ schließt und springt ins Formular', pg.evaluate("document.activeElement && document.activeElement.id === 'antrag-von'"))
        ctx.close()
    rev = P.call('mitarbeiter_hr')[1]['rev']; hr(ids['erika'], jahr=J, anspruch=(pe_['jahre'].get(str(J)) or {}).get('anspruch'), uebertrag=(pe_['jahre'].get(str(J)) or {}).get('uebertrag'))
    v_ = P.call('mitarbeiter_hr')[1]
    assert P.call('hr_einstellungen_save', {'sperren': v_['sperren'], 'ferien': v_['ferien'], 'uebertragBis': '03-31'})[0] == 200
    ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', 1280, verfall_hinweis=True)
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-app:not([hidden]) #mein-konto .hr-wert')
    check('… ohne verfallenden Übertrag kein Pop-up', not pg.evaluate("document.querySelector('#dlg-verfall').open"))
    ctx.close()

    # Mitarbeiterin: Mein Urlaub, Antrag in der Oberfläche, Desktop und Handy
    KRANK_UI = montag(Y, 11, 3)
    assert P.call('hr_eintrag_save', {'person': PE, 'art': 'K', 'von': iso(KRANK_UI), 'bis': iso(KRANK_UI + dt.timedelta(days=1))})[0] == 200
    for breite in (1280, 390):
        ctx, pg = anmelden('erika', 'Editor-Zugang-77', '198.51.100.3', breite)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-konto .hr-wert')
        check(f'{breite}px: Personalbereiche ausgeblendet', not pg.is_visible('[data-tab="antraege"]') and not pg.is_visible('[data-tab="export"]'))
        check(f'{breite}px: Urlaubsregeln beim Antrag (6 Punkte mit Überschrift, Hinweis im Formular)', pg.is_visible('#regeln-text') and pg.locator('#regeln-text h3').count() == 6
              and '31.03.' in pg.text_content('#regeln-text') and pg.is_visible('#antrag-regeln'))
        if breite == 1280:
            pg.click('#regeln > summary'); pg.wait_for_function("!document.querySelector('#regeln').open && localStorage.getItem('hr-regeln-zu') === '1'")
            pg.reload(); pg.wait_for_selector('#hr-app:not([hidden]) #mein-konto .hr-wert')
            check('Urlaubsregeln zugeklappt bleiben zugeklappt (je Browser), Link im Formular klappt auf', not pg.evaluate("document.querySelector('#regeln').open"))
            pg.click('#antrag-regeln a'); pg.wait_for_function("document.querySelector('#regeln').open")
        breit = pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        check(f'{breite}px: kein waagerechtes Scrollen der Seite', breit)
        pg.screenshot(path=os.path.join(SH, f'hr_mein_{breite}.png'), full_page=True)
        if breite == 1280:
            pg.click('[data-jahr="1"]')
            pg.wait_for_function(f'document.querySelector("#mein-titel").textContent.includes("{Y}")')
            tag_ = montag(Y, 9)
            pg.evaluate("document.querySelectorAll('#antrag input[required]').forEach((i) => i.removeAttribute('required'))")   # eigene Meldung statt Browserhinweis
            pg.click('#antrag-senden'); pg.wait_for_selector('#antrag-meldung.fehler')
            pg.fill('#antrag-von', iso(tag_)); pg.dispatch_event('#antrag-von', 'change')
            check('Meldung zum leeren Antrag verschwindet nach Eingabe der Daten', pg.text_content('#antrag-meldung') == '', pg.text_content('#antrag-meldung'))
            pg.fill('#antrag-bis', iso(tag_ - dt.timedelta(days=3))); pg.dispatch_event('#antrag-bis', 'change')
            pg.click('#antrag-senden')
            pg.wait_for_function("document.activeElement && document.activeElement.id === 'antrag-bis'")
            check('Ende vor Beginn: Hinweis nur einmal, kein Antrag gesendet', pg.text_content('#antrag-tage') == 'Das Ende liegt vor dem Beginn.' and pg.text_content('#antrag-meldung') == '',
                  (pg.text_content('#antrag-tage'), pg.text_content('#antrag-meldung')))
            pg.fill('#antrag-bis', iso(tag_ + dt.timedelta(days=4))); pg.dispatch_event('#antrag-bis', 'change')
            check('Vorschau: 5 Tage Urlaub', '5 Tage' in pg.text_content('#antrag-tage'), pg.text_content('#antrag-tage'))
            pg.click('#antrag-senden'); pg.wait_for_selector('#antrag-meldung.ok')
            check('Oberfläche: Antrag gestellt, in der Liste', 'beantragt' in pg.text_content('#mein-liste'))
            # Liste nur Urlaub; Krank steht im Mini-Kalender „Mein Jahr“
            check('Liste „Mein Urlaub und Anträge“: nur Urlaub, keine Krankheit', pg.locator('#mein-liste .hr-art.K').count() == 0 and pg.locator('#mein-liste .hr-art.U').count() > 0)
            check('Mini-Kalender: 12 Monate, Krank-Tage und beantragter Urlaub markiert', pg.locator('#mini-kalender .hr-mini-monat').count() == 12
                  and pg.locator(f'#mini-kalender button.t.K[data-korr-tag="{iso(KRANK_UI)}"]').count() == 1
                  and pg.locator(f'#mini-kalender button.t.U.offen[data-korr-tag="{iso(tag_)}"]').count() == 1)
            pg.click(f'#mini-kalender button.t.K[data-korr-tag="{iso(KRANK_UI)}"]'); pg.wait_for_selector('#dlg-korrektur[open]')
            check('Klick auf einen Tag: „Korrektur melden“ mit Bezug und Zeitraum', 'Krank' in pg.text_content('#korrektur-bezug')
                  and pg.input_value('#korrektur-von') == iso(KRANK_UI) and pg.input_value('#korrektur-bis') == iso(KRANK_UI + dt.timedelta(days=1)))
            pg.click('#korrektur-senden'); pg.wait_for_selector('#korrektur-meldung.fehler')
            check('ohne Text: Hinweis im Dialog, nichts gesendet', pg.is_visible('#dlg-korrektur') and not E.call('hr_start')[1]['korrekturen'])
            pg.fill('#korrektur-text', 'Am zweiten Tag war ich wieder im Büro.')
            pg.screenshot(path=os.path.join(SH, 'hr_korrektur_dialog_1280.png'))
            pg.click('#korrektur-senden'); pg.wait_for_selector('#korrektur-info.ok')
            check('Oberfläche: Korrektur gesendet, unter „Meine Korrekturmeldungen“ offen', pg.is_visible('#korrektur-eigene') and 'offen' in pg.text_content('#korrektur-liste')
                  and 'wieder im Büro' in pg.text_content('#korrektur-liste'))
            pg.screenshot(path=os.path.join(SH, 'hr_mein_jahr_1280.png'), full_page=True)
            pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')"); pg.wait_for_function('getComputedStyle(document.body).backgroundColor === "rgb(18, 16, 17)"')
            pg.screenshot(path=os.path.join(SH, 'hr_mein_jahr_1280_dunkel.png'), full_page=True)
            pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        pg.click('[data-tab="kalender"]'); pg.wait_for_selector('#kal-plan tbody tr')
        check(f'{breite}px: Kalender ohne Gründe (nur „abwesend“ in der Legende)', 'Krank' not in pg.text_content('#kal-legende') and 'abwesend' in pg.text_content('#kal-legende'))
        pg.screenshot(path=os.path.join(SH, f'hr_kalender_mitarbeiter_{breite}.png'), full_page=True)
        pg.click('#kal-modus [data-modus="zeitraum"]'); pg.wait_for_function("document.querySelectorAll('#kal-plan thead th').length === 30")
        sichtbar = pg.evaluate('''() => { const th = document.querySelector('#kal-plan thead th.heute'), box = document.querySelector('#kal-plan').parentElement;
          const n = document.querySelector('#kal-plan thead th.name').getBoundingClientRect(), r = th.getBoundingClientRect(), b = box.getBoundingClientRect();
          return r.left >= n.right - 1 && r.right <= b.right + 1; }''')
        check(f'{breite}px: Spalte „heute“ ohne Wischen sichtbar (rechts neben den Namen)', sichtbar)
        check(f'{breite}px: ± 2 Wochen und Filter auch für Mitarbeiter, Seite ohne waagerechtes Scrollen', pg.locator('#kal-filter [data-abt]').count() > 1
              and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_kalender_mitarbeiter_2wochen_{breite}.png'), full_page=True)
        ctx.close()

    # Personalstelle: Korrekturmeldung unter „Anträge“ erledigen (Desktop, dann Handy-Ansicht)
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.goto(B + '/module/hr/#antraege'); pg.wait_for_selector('#korrekturen-liste [data-korr] [data-korr-erledigt]')
    check('Personalstelle: Korrekturmeldung mit Name und Text, Zahl am Reiter', 'Erika Editor' in pg.text_content('#korrekturen-liste')
          and 'wieder im Büro' in pg.text_content('#korrekturen-liste') and pg.text_content('#korr-zahl') == '1' and int(pg.text_content('#hr-offen') or 0) >= 1)
    pg.screenshot(path=os.path.join(SH, 'hr_korrekturen_personalstelle_1280.png'), full_page=True)
    karte = pg.locator('#korrekturen-liste [data-korr]', has=pg.locator('[data-korr-erledigt]')).first
    karte.locator('input').fill('Eintrag auf einen Tag gekürzt.')
    karte.locator('[data-korr-erledigt]').click(); pg.wait_for_function('!document.querySelector("#korrekturen-liste [data-korr-erledigt]")')
    check('Oberfläche: erledigt, Antwort beim Mitarbeiter', 'Eintrag auf einen Tag gekürzt.' in pg.text_content('#korrekturen-liste')
          and any(m['erledigt'] and m['erledigt']['antwort'] == 'Eintrag auf einen Tag gekürzt.' for m in E.call('hr_start')[1]['korrekturen']))
    pg.set_viewport_size({'width': 390, 'height': 844})
    check('390px Personalstelle: Korrekturmeldungen ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    pg.screenshot(path=os.path.join(SH, 'hr_korrekturen_personalstelle_390.png'), full_page=True)
    ctx.close()

    # produktiv: jeder Mitarbeiter sieht die normale Seite (otto war nie Tester)
    ctx, pg = anmelden('otto', 'Ohne-Zugang-77', '198.51.100.6')
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-app:not([hidden]), #hr-err:not([hidden])')
    check('Mitarbeiter ohne Tester-Eintrag: normale Seite (Mein Urlaub), kein Hinweis „nicht freigegeben“',
          pg.is_visible('#hr-app') and pg.is_hidden('#hr-err') and pg.is_hidden('[data-tab="antraege"]'), pg.text_content('#hr-err'))
    ctx.close()
    ctx = br.new_context(); pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis', pg.is_visible('#hr-login a'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
