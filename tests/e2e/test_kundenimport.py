"""Stammdaten → Angebote mit Kundengruppen (Freischaltung über die Gruppe), Import der Kundenstammdaten aus der
Warenwirtschaft (CSV, alle Spalten, Aktiv-Regel 18 Monate) und Passwort-Auswahl im Kunden-Dialog. Nur synthetische
Testdaten (tests/fixtures/kunden); Datumswerte für die Aktiv-Regel relativ zu heute."""
import calendar
import csv
import datetime
import io
import json
import os
import sys
import urllib.request
import zoneinfo

from playwright.sync_api import sync_playwright

from auth_helpers import expire_session
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, FIX, SH, SMTP_PORT, WORK, storage_raw

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
CSV = FIX + '/kunden/kundendaten.csv'
PREISE = FIX + '/angebote/artikelpreise.csv'
res = []
HEUTE = datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Berlin')).date()   # Ortszeit des Servers (index.php)


def vor(monate, tag=True):
    """Datum vor n Monaten (JJJJ-MM-TT). tag=False: wie PHP modify('-n months') – ein zu großer Tag läuft in den Folgemonat."""
    y, m = divmod(HEUTE.year * 12 + HEUTE.month - 1 - monate, 12)
    if tag:
        return datetime.date(y, m + 1, min(HEUTE.day, 28)).isoformat()
    tage = calendar.monthrange(y, m + 1)[1]
    return (datetime.date(y, m + 1, 1) + datetime.timedelta(days=HEUTE.day - 1)).isoformat() if HEUTE.day > tage else datetime.date(y, m + 1, HEUTE.day).isoformat()


def dmy(iso):
    return '.'.join(reversed(iso.split('-')))


def datei_mit_daten():
    """Kopie der Testdatei mit Rechnungs-, Lieferschein- und Anlagedaten relativ zu heute (Aktiv-Regel unabhängig vom Testtag)"""
    rows = list(csv.reader(io.StringIO(open(CSV, 'rb').read().decode('cp1252'), newline=''), delimiter=';'))
    ix = {k: i for i, k in enumerate(rows[0])}
    neu = {'1000001': {'LetzteRechnung': vor(1), 'LetzterLieferschein': vor(1)}, '1000002': {'LetzteRechnung': vor(30)},
           '1000003': {'LetzteRechnung': vor(40), 'LetzterLieferschein': vor(40)}, '1000004': {'LetzterLieferschein': vor(2)},
           '1000005': {'LetzteRechnung': vor(1)}, '1000006': {'AngelegtAm': vor(1)}}
    for r in rows[1:]:
        if r[ix['Alpha']] != 'DOPPELT':
            for k, v in neu.get(r[ix['Nummer']], {}).items():
                r[ix[k]] = dmy(v)
    os.makedirs(os.path.join(WORK, 'kundenimport'), exist_ok=True)
    ziel = os.path.join(WORK, 'kundenimport', 'kundendaten.csv')
    with open(ziel, 'wb') as f:
        f.write(''.join(';'.join('"' + c.replace('"', '""') + '"' if c else '' for c in r) + '\r\n' for r in rows).encode('cp1252'))
    return ziel


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

# ---------- Kundenimport: alle Spalten (Daten der Warenwirtschaft) und Aktiv-Regel (18 Monate) ----------
# Datumswerte relativ zu heute – nie genau auf dem Stichtag (Zeitzone, Monatsende)
WF = ['alpha', 'konto', 'letzteRechnung', 'letzterLieferschein', 'angelegtAm', 'angelegtUm', 'kreditlimit', 'umsatzJahr', 'rohgewinnJahr', 'gln', 'rgSperre', 'mailAB', 'weitereEmails']
REGEL = [
    {'nr': '2500001', 'firma': 'Regel Aktiv GmbH', 'wawi': {'alpha': 'REGELAKTIV', 'konto': '10001', 'letzteRechnung': vor(2), 'kreditlimit': 5000, 'umsatzJahr': 12345.67, 'rohgewinnJahr': -12.3,
                                                         'gln': '4000000000017', 'rgSperre': False, 'mailAB': 'ab@example.org; falsch', 'angelegtUm': '09:05'}},
    {'nr': '2500002', 'firma': 'Regel Alt KG', 'wawi': {'letzteRechnung': vor(19), 'angelegtAm': vor(60)}},
    {'nr': '2500003', 'firma': 'Regel Knapp OHG', 'wawi': {'letzteRechnung': vor(17)}},
    {'nr': '2500004', 'firma': 'Nur Lieferschein GmbH', 'wawi': {'letzteRechnung': vor(30), 'letzterLieferschein': vor(1)}},
    {'nr': '2500005', 'firma': 'Neu Angelegt GmbH', 'wawi': {'angelegtAm': vor(1)}},
    {'nr': '2500006', 'firma': 'Ohne Datum e.K.', 'wawi': {}},
    {'nr': '2500007', 'firma': 'Stern Kunde KG', 'stern': True, 'wawi': {'letzteRechnung': vor(1)}},
    {'nr': '2500008', 'firma': 'Ungültig GmbH', 'wawi': {'letzteRechnung': '2024-02-30', 'kreditlimit': 'abc', 'gln': '12ab', 'angelegtUm': '25:00', 'rgSperre': 'Ja', 'angelegtAm': vor(2), 'unbekannt': 'x'}},
]
st, r = A.call('kunden_import', {'pruefen': True, 'rows': REGEL, 'wawiFelder': WF})
check('ohne Aktiv-Regel: alle neuen Kunden aktiv', st == 200 and r['regel'] is False and r['stat']['neuInaktiv'] == 0 and r['stat']['neu'] == 8, r.get('stat'))
st, r = A.call('kunden_import', {'pruefen': True, 'rows': REGEL, 'aktivRegel': True, 'wawiFelder': [f for f in WF if f != 'letzteRechnung']})
check('Aktiv-Regel ohne Spalte LetzteRechnung: nicht angewendet, Hinweis', st == 200 and r['regel'] is False and r['stat']['neuInaktiv'] == 0
      and any(h['stufe'] == 'warn' and 'LetzteRechnung' in h['text'] for h in r['hinweise']), r.get('hinweise'))
st, r = A.call('kunden_import', {'pruefen': True, 'rows': REGEL, 'aktivRegel': True, 'wawiFelder': WF})
check('Vorschau mit Aktiv-Regel: 3 neue Kunden inaktiv (alt, ohne Datum, „*“), nichts gespeichert', st == 200 and r['regel'] is True and r['stat']['neu'] == 8 and r['stat']['neuInaktiv'] == 3
      and [x['aktiv'] for x in r['beispiele']['neu']] == [True, False, True, True, True, False, False, True] and r['stichtag'] == vor(18, tag=False), (r.get('stat'), r.get('beispiele', {}).get('neu')))
check('Vorschau: Hinweise zu Aktiv-Status und Daten der Warenwirtschaft', any('Aktiv-Status nach der Warenwirtschaft' in h['text'] and '3 neue Kunden' in h['text'] for h in r['hinweise'])
      and any('Kreditlimit' in h['text'] and 'Kunden bearbeiten' in h['text'] for h in r['hinweise']), r['hinweise'])
st, r = A.call('kunden_import', {'rev': r['rev'], 'rows': REGEL, 'aktivRegel': True, 'wawiFelder': WF, 'quelle': 'regel.csv'})
cs = {c.get('nr'): c for c in doc('kunden')['customers']}
akt = {nr: cs.get(nr, {}).get('active') for nr in ('2500001', '2500002', '2500003', '2500004', '2500005', '2500006', '2500007', '2500008')}
check('Aktiv-Regel: Rechnung < 18 Monate, Lieferschein oder Neuanlage → aktiv; sonst inaktiv', st == 200 and akt == {'2500001': True, '2500002': False, '2500003': True, '2500004': True,
      '2500005': True, '2500006': False, '2500007': False, '2500008': True}, akt)
check('inaktiv angelegt mit Grund (letzte Rechnung bzw. „*“)', 'keine Rechnung seit 18 Monaten (letzte ' + dmy(vor(19)) + ')' == cs['2500002'].get('autoInaktiv', {}).get('grund')
      and cs['2500006']['autoInaktiv']['grund'] == 'keine Rechnung seit 18 Monaten' and '„*“' in cs['2500007']['autoInaktiv']['grund'] and 'autoInaktiv' not in cs['2500001'], cs['2500002'].get('autoInaktiv'))
w1 = cs['2500001'].get('wawi', {})
check('Daten der Warenwirtschaft gespeichert (Zahl, Ja/Nein, Uhrzeit, gültige E-Mail)', w1.get('kreditlimit') == 5000 and w1.get('umsatzJahr') == 12345.67 and w1.get('rohgewinnJahr') == -12.3
      and w1.get('gln') == '4000000000017' and w1.get('rgSperre') is False and w1.get('mailAB') == 'ab@example.org' and w1.get('angelegtUm') == '09:05' and w1.get('alpha') == 'REGELAKTIV'
      and w1.get('stand'), w1)
check('ungültige und unbekannte Werte nicht gespeichert', set(cs['2500008'].get('wawi', {})) == {'angelegtAm', 'stand'} and 'wawi' not in cs['2500006'], cs['2500008'].get('wawi'))
lg = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Import mit inaktiven Kunden, ohne Umsätze', 'Kunden aus „regel.csv“ importiert: 8 neu, 0 aktualisiert (3 neu als inaktiv)' in lg and '12345.67' not in lg and 'REGELAKTIV' not in lg)
A.call('user_save', {'username': 'ken', 'name': 'Ken Kundensicht', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False, 'grant': ['kunden.sehen']})
KS = Client('198.51.100.6'); assert KS.call('login', {'username': 'ken', 'password': 'Leserin-Zugang-1'})[0] == 200
sieht = lambda cl: next(c for c in cl.call('kunden')[1]['customers'] if c.get('nr') == '2500001')   # noqa: E731
check('Daten der Warenwirtschaft nur mit „Kunden bearbeiten“; Status-Grund für alle mit Kundenrecht', sieht(A).get('wawi', {}).get('umsatzJahr') == 12345.67 and 'wawi' not in sieht(KS)
      and next(c for c in KS.call('kunden')[1]['customers'] if c.get('nr') == '2500002').get('autoInaktiv', {}).get('grund', '').startswith('keine Rechnung'))
check('Kundenimport mit Kundenrecht nur zum Ansehen: 403', KS.call('kunden_import', {'pruefen': True, 'rows': REGEL})[0] == 403)
st, r = A.call('kunden_import', {'pruefen': True, 'rows': REGEL, 'aktivRegel': True, 'wawiFelder': WF})
check('erneuter Import mit WaWi-Daten: unverändert', st == 200 and r['stat']['unveraendert'] == 8 and r['stat']['aktualisiert'] == 0, r.get('stat'))
# Ältere Exporte ohne die Spalten lassen die gespeicherten Werte stehen; eine leere Zelle leert den Wert
st, r = A.call('kunden_import', {'pruefen': True, 'rows': [{'nr': '2500001', 'firma': 'Regel Aktiv GmbH'}]})
check('Export ohne WaWi-Spalten: Werte bleiben', r['stat']['unveraendert'] == 1, r.get('stat'))


def importiere(rows, felder=WF, quelle='regel.csv'):
    st, r = A.call('kunden_import', {'pruefen': True, 'rows': rows, 'aktivRegel': True, 'wawiFelder': felder})
    assert st == 200, r
    st, r2 = A.call('kunden_import', {'rev': r['rev'], 'rows': rows, 'aktivRegel': True, 'wawiFelder': felder, 'quelle': quelle})
    assert st == 200, r2
    return r, {c.get('nr'): c for c in doc('kunden')['customers']}


r, cs = importiere([{'nr': '2500001', 'firma': 'Regel Aktiv GmbH', 'wawi': {'letzteRechnung': vor(2), 'kreditlimit': 7500}}])
check('geänderte WaWi-Daten: aktualisiert, leere Zelle leert, Stand neu', r['stat']['aktualisiert'] == 1 and r['stat']['wawi'] == 1 and r['beispiele']['aktualisiert'][0]['felder'] == ['Daten der Warenwirtschaft']
      and cs['2500001']['wawi'].get('kreditlimit') == 7500 and 'umsatzJahr' not in cs['2500001']['wawi'] and cs['2500001']['wawi']['stand'] >= w1['stand'], cs['2500001'].get('wawi'))
r, cs = importiere([{'nr': '2500002', 'firma': 'Regel Alt KG', 'wawi': {'letzteRechnung': vor(1)}}])
check('neue Rechnung: automatisch deaktivierter Kunde wieder aktiv', r['stat']['reaktiviert'] == 1 and cs['2500002']['active'] is True and 'autoInaktiv' not in cs['2500002'], r['stat'])
r, cs = importiere([{'nr': '2500003', 'firma': 'Regel Knapp OHG', 'wawi': {'letzteRechnung': vor(19)}}])
check('bestehender Kunde, Rechnung älter als 18 Monate: inaktiv', r['stat']['inaktiv'] == 1 and r['stat']['inaktivZugang'] == 0 and cs['2500003']['active'] is False
      and r['beispiele']['inaktiv'][0]['nr'] == '2500003' and 'Kunde aktiv' in r['beispiele']['aktualisiert'][0]['felder'], r)
check('Protokoll: Aktiv-Status mit Grund', 'inaktiv gesetzt' in json.dumps(A.call('log')[1], ensure_ascii=False) and 'nein (keine Rechnung seit 18 Monaten' in json.dumps(A.call('log')[1], ensure_ascii=False))
# von Hand: deaktiviert bleibt deaktiviert, wieder aktiviert bleibt aktiv
alle = {c.get('nr'): c for c in A.call('kunden')[1]['customers']}
def speichern(nr, aktiv):
    c = alle[nr]
    st, r = A.call('kunde_save', {'id': c['id'], 'rev': A.call('kunden')[1]['rev'], 'firma': c['firma'], 'nr': nr, 'active': aktiv, 'angebote': [], 'login': None})
    assert st == 200, r
speichern('2500001', False)
speichern('2500006', True)
cs = {c.get('nr'): c for c in doc('kunden')['customers']}
check('von Hand aktiviert: Kennzeichen „aktivVonHand“, „autoInaktiv“ entfällt; WaWi-Daten bleiben beim Speichern', cs['2500006']['active'] is True and 'autoInaktiv' not in cs['2500006']
      and cs['2500006'].get('aktivVonHand') and cs['2500001']['active'] is False and 'aktivVonHand' not in cs['2500001'] and cs['2500001']['wawi'].get('kreditlimit') == 7500, cs['2500006'])
r, cs = importiere([{'nr': '2500001', 'firma': 'Regel Aktiv GmbH', 'wawi': {'letzteRechnung': vor(1), 'kreditlimit': 7500}}, {'nr': '2500006', 'firma': 'Ohne Datum e.K.', 'wawi': {}}])
check('von Hand deaktiviert bleibt inaktiv, von Hand aktiviert bleibt aktiv', r['stat']['bleibtInaktiv'] == 1 and r['stat']['bleibtAktivHand'] == 1 and cs['2500001']['active'] is False and cs['2500006']['active'] is True
      and any('von Hand deaktivierter Kunde' in h['text'] for h in r['hinweise']) and any('von Hand aktivierter Kunde' in h['text'] for h in r['hinweise']), r['stat'])
# Kunden mit Zugang: angemeldet in den 18 Monaten → bleibt aktiv; Zugang ohne Anmeldung → inaktiv (Zugang bleibt), Warnung
zg = kunde({'firma': 'Zugang Ungenutzt GmbH', 'nr': '2500009', 'email': 'ungenutzt@example.org', 'angebote': [], 'login': {'username': 'zugang.ungenutzt', 'password': KPW, 'mustChange': False, 'active': True}})
r, cs = importiere([{'nr': 'T-5', 'firma': 'Kantine Gruppe Fünf', 'wawi': {'letzteRechnung': vor(30)}}, {'nr': '2500009', 'firma': 'Zugang Ungenutzt GmbH', 'wawi': {'letzteRechnung': vor(30)}}])
check('Kunde meldet sich an: bleibt aktiv; Zugang nie genutzt: inaktiv, Zugang bleibt gespeichert', r['stat']['bleibtAktivZugang'] == 1 and r['stat']['inaktivZugang'] == 1 and cs['T-5']['active'] is True
      and cs['2500009']['active'] is False and cs['2500009']['login']['username'] == 'zugang.ungenutzt' and r['beispiele']['inaktiv'][0]['zugang'] is True
      and any(h['stufe'] == 'warn' and 'Zugang zur Angebotsseite' in h['text'] for h in r['hinweise']), r['stat'])
check('Warnung: Empfänger des Wochenangebots werden inaktiv', r['stat']['inaktivMail'] == 1 and r['beispiele']['inaktiv'][0]['mail'] is True
      and any(h['stufe'] == 'warn' and 'Wochenangebot per E-Mail' in h['text'] for h in r['hinweise']), r['stat'])
check('angemeldeter Kunde weiter angemeldet', ids(K5) == ['edeka'])
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
    a.set_input_files('#k-file', datei_mit_daten()); a.wait_for_selector('#dlg-k-import[open] #ki-neu')
    t = a.inner_text('#k-import-body')
    check('Vorschau: 4 neu, 2 aktualisiert (Nummer bzw. Firma+PLZ)', a.inner_text('#ki-neu') == '4' and a.inner_text('#ki-akt') == '2', t)
    check('Vorschau: Aktiv-Regel gewählt, 3 werden inaktiv (2 neue, 1 bestehender mit Zugang)', a.locator('#k-import-body [data-ki="regel"]').is_checked() and a.inner_text('#ki-inaktiv') == '3'
          and 'Bestandskunde Gepflegt' in a.inner_text('#ki-inaktiv-liste') and 'hat Zugang' in a.inner_text('#ki-inaktiv-liste') and 'Zugang zur Angebotsseite' in t, t)
    a.uncheck('#k-import-body [data-ki="regel"]'); a.wait_for_function("document.querySelector('#ki-neu') && !document.querySelector('#ki-inaktiv')")
    check('ohne Aktiv-Regel: keine Inaktiv-Zahl', a.locator('#ki-inaktiv-liste').count() == 0)
    a.check('#k-import-body [data-ki="regel"]'); a.wait_for_selector('#ki-inaktiv')
    check('Vorschau: übersprungen und Hinweise', '1 ohne Firma übersprungen' in t and '1× doppelte Kundennummer' in t and '1× ungültige E-Mail' in t and '999 (1)' in t, t)
    check('Vorschau: „*“-Kunden standardmäßig übersprungen', '1 in der Datei' in t and 'Gelöschter Kunde' not in t)
    a.uncheck('#k-import-body [data-ki="stern"]'); a.wait_for_function("document.querySelector('#ki-neu') && document.querySelector('#ki-neu').textContent === '5'")
    check('ohne Überspringen: 5 neu, „*“-Kunde trotz neuer Rechnung inaktiv', a.inner_text('#ki-inaktiv') == '4', a.inner_text('#ki-inaktiv'))
    a.check('#k-import-body [data-ki="stern"]'); a.wait_for_function("document.querySelector('#ki-neu') && document.querySelector('#ki-neu').textContent === '4'")
    a.screenshot(path=SH + '/kunden-import.png')
    a.click('#k-import-body [data-ki="ok"]'); a.wait_for_selector('#toast.show:has-text("Kunden übernommen")', timeout=15000)
    cs = {c.get('nr'): c for c in doc('kunden')['customers']}
    check('importiert: Umlaute, Land als Name, erste gültige E-Mail', cs.get('1000008', {}).get('firma') == 'Bäckerei Größe & Söhne' and cs.get('1000003', {}).get('land') == 'Österreich'
          and cs.get('1000002', {}).get('email') == 'kantine@example.org' and cs.get('1000006', {}).get('land') == 'Frankreich', {k: cs.get(k, {}).get('land') for k in ('1000003', '1000006')})
    a.wait_for_selector('#k-list .nobr')
    nb = a.evaluate("(() => { const e = document.querySelector('#k-list .nobr'); return [e.textContent, getComputedStyle(e).whiteSpace, e.getClientRects().length]; })()")
    check('Kundenliste: „E-Mail“ wird nicht am Bindestrich getrennt', nb == ['E-Mail', 'nowrap', 1], nb)
    check('unbekannte Gruppe leer, ungültige E-Mail leer', cs.get('1000006', {}).get('gruppe') == '' and cs.get('1000006', {}).get('email') == '')
    b = cs.get('1000003', {})
    check('Bestandskunde: Firma, E-Mail, Zugang, Freischaltung bleiben', b.get('firma') == 'Bestandskunde Gepflegt' and b.get('email') == 'bestand@example.org' and b.get('login', {}).get('username') == 'bestand.kunde' and b.get('angebote') == ['edeka'] and b.get('gruppe') == '7')
    check('Kunde ohne Nummer über Firma+PLZ gefunden und Nummer ergänzt', cs.get('1000004', {}).get('firma') == 'Ohne Nummer KG' and cs.get('1000004', {}).get('gruppe') == '5')
    w = cs.get('1000001', {}).get('wawi', {})
    check('„*“-Kunde nicht angelegt; alle weiteren Spalten als Daten der Warenwirtschaft (Vertreter.Alpha nicht doppelt)', '1000005' not in cs and 'Testvertreter' not in json.dumps(doc('kunden'), ensure_ascii=False)
          and w.get('kreditlimit') == 3000 and w.get('umsatzJahr') == 12345.67 and w.get('rohgewinnMonat') == -12.3 and w.get('umsatzVorvorjahr') == 1234567.89 and w.get('gln') == '4000000000017'
          and w.get('abgabeCitti') is True and w.get('dfb') is False and w.get('mailAB') == 'ab@testhof.example' and w.get('mailERechnung') == 're@testhof.example' and w.get('angelegtUm') == '09:05'
          and w.get('angelegtAm') == '2019-02-03' and w.get('konto') == '10001' and w.get('rgEmpf') == '1000004' and w.get('kondition') == '1' and w.get('alpha') == 'TESTHOF' and w.get('letzteRechnung') == vor(1), w)
    check('weitere E-Mail-Adressen und Rechnungssperre', cs.get('1000002', {}).get('wawi', {}).get('weitereEmails') == 'zweite@example.org' and cs['1000002']['wawi'].get('rgSperre') is True)
    akt = {nr: cs.get(nr, {}).get('active') for nr in ('1000001', '1000002', '1000003', '1000004', '1000006', '1000008')}
    check('Aktiv-Status: Rechnung, Lieferschein bzw. Neuanlage in 18 Monaten aktiv, sonst inaktiv', akt == {'1000001': True, '1000002': False, '1000003': False, '1000004': True, '1000006': True, '1000008': False}, akt)
    check('Bestandskunde mit ungenutztem Zugang: inaktiv, Zugang bleibt gespeichert', cs['1000003'].get('autoInaktiv', {}).get('grund', '').startswith('keine Rechnung seit 18 Monaten') and cs['1000003']['login']['username'] == 'bestand.kunde')
    a.wait_for_selector('#k-list tr[data-kid]')
    a.select_option('#k-g', '5'); a.wait_for_function("document.querySelector('#k-count').textContent.startsWith('3 Kunden')")
    check('Filter nach Kundengruppe', a.locator('#k-list tr[data-kid]').count() == 3, a.inner_text('#k-count'))
    check('Angebot über die Kundengruppe in der Liste gekennzeichnet', a.locator('#k-list tr[data-kid] .k-chip.grp:has-text("Edeka")').count() == 3)
    a.select_option('#k-g', '')
    a.fill('#k-q', 'Bestandskunde'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Bestandskunde")')
    check('Kundenliste: Grund der Deaktivierung beim Status', 'keine Rechnung seit 18 Monaten' in a.inner_text('#k-list tr[data-kid]:has-text("Bestandskunde")'))
    a.click('#k-list tr[data-kid]:has-text("Bestandskunde")'); a.wait_for_selector('#dlg-kunde[open]')
    check('Kunden-Dialog: Hinweis „vom Kundenimport deaktiviert“', a.locator('#kunde-body .k-autoinaktiv').is_visible() and not a.locator('#kunde-body [name="active"]').is_checked())
    check('Kunden-Dialog: Angebot direkt freigeschaltet, Gruppen-Angebot gekennzeichnet', a.locator('#kunde-body [name="angebot"][value="edeka"]').is_checked()
          and a.locator('#kunde-body label:has(input[value="bela"]) .k-viagr').count() == 1)
    check('Bestandskunde der Gruppe 7 sieht Bela über die Gruppe', 'bela' in next(c for c in A.call('kunden')[1]['customers'] if c.get('nr') == '1000003')['angeboteGruppe'])
    a.click('#kunde-body [data-close]')

    # ---------- Kunden-Dialog: Daten der Warenwirtschaft, Filter nach Status ----------
    a.fill('#k-q', 'Testhof'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Testhof")')
    a.click('#k-list tr[data-kid]:has-text("Testhof")'); a.wait_for_selector('#dlg-kunde[open] details.k-wawi')
    check('Daten der Warenwirtschaft zunächst zugeklappt', not a.locator('#kunde-body .k-wawi-dl').is_visible())
    a.click('#kunde-body details.k-wawi summary'); a.wait_for_selector('#kunde-body .k-wawi-dl')
    t = a.inner_text('#kunde-body details.k-wawi').replace('\xa0', ' ').replace('\u202f', ' ')
    check('Daten der Warenwirtschaft: Werte deutsch formatiert, Umsatz und Rohgewinn', all(x in t for x in ('Kreditlimit', '3.000,00 €', 'Letzte Rechnung', dmy(vor(1)), 'Rechnungsempfänger', '1000004',
          'Angelegt', '03.02.2019 09:05 Uhr von TST', 'Abgabe CITTI', 'ja', '1.234.567,89 €', '-12,30 €', 'GLN', '4000000000017')), t)
    a.locator('#kunde-body details.k-wawi').scroll_into_view_if_needed()
    a.screenshot(path=SH + '/kunde-wawi.png')
    a.click('#kunde-body [data-close]')
    a.fill('#k-q', '')
    a.select_option('#k-s', 'inaktiv'); a.wait_for_function("document.querySelectorAll('#k-list tr[data-kid]').length > 0 && !document.querySelector('#k-list tr[data-kid]:not(.inactive)')")
    n_in = a.locator('#k-list tr[data-kid]').count()
    a.select_option('#k-s', 'aktiv'); a.wait_for_function("document.querySelectorAll('#k-list tr[data-kid]').length > 0 && !document.querySelector('#k-list tr[data-kid].inactive')")
    n_an = a.locator('#k-list tr[data-kid]').count()
    gesamt = len(doc('kunden')['customers'])
    check('Filter nach Status: nur aktive bzw. nur inaktive, zusammen alle', n_in + n_an == gesamt and n_in == sum(1 for c in doc('kunden')['customers'] if not c.get('active'))
          and f'Nur inaktive ({n_in})' in a.evaluate("[...document.querySelectorAll('#k-s option')].map((o) => o.textContent).join('|')"), (n_in, n_an, gesamt))
    a.select_option('#k-s', '')

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
    breite = "(() => { const d = document.querySelector('dialog[open] .dlg-body'); return d.scrollWidth - d.clientWidth; })()"
    a.fill('#k-q', 'Testhof'); a.wait_for_selector('#k-list tr[data-kid]:has-text("Testhof")')
    a.click('#k-list tr[data-kid]:has-text("Testhof")'); a.wait_for_selector('#dlg-kunde[open] details.k-wawi')
    a.click('#kunde-body details.k-wawi summary'); a.wait_for_selector('#kunde-body .k-wawi-dl')
    a.locator('#kunde-body .k-wawi-ums').scroll_into_view_if_needed()
    a.screenshot(path=SH + '/kunde-wawi-mobil.png')
    check('Daten der Warenwirtschaft 390 px: kein seitliches Scrollen im Dialog', a.evaluate(breite) <= 1, a.evaluate(breite))
    a.click('#kunde-body [data-close]'); a.fill('#k-q', '')
    a.set_input_files('#k-file', datei_mit_daten()); a.wait_for_selector('#dlg-k-import[open] #ki-inaktiv')
    a.screenshot(path=SH + '/kunden-import-mobil.png')
    check('Import-Vorschau 390 px: kein seitliches Scrollen, nichts mehr zu übernehmen', a.evaluate(breite) <= 1 and a.inner_text('#ki-neu') == '0', a.evaluate(breite))
    a.click('#k-import-body [data-close]')
    a.click('#vt-angebote'); a.wait_for_selector('#view-angebote tr[data-oi]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Angebote 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/stammdaten-angebote-mobil.png')
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
