"""Leergut (Modul leergut, Oberfläche leergut.intern unter /module/leergut/) – Leergutkonten und Abstimmung.

Geprüft: Register (fertig und produktiv unter leergut.dashboard-stafl.de, Kachel verfügbar, ohne Testfreigabe erreichbar); Rechte serverseitig (GR-103): ohne
Anmeldung, ohne Leergut-Recht, nur ansehen, buchen, verwalten; ohne CSRF, GET auf schreibende Aktion; Grundwerte der
Lademittel (E2 5,50 €, H1 36,00 €); Partner (Pflichtfelder, doppelt, Art, Firma, Frist, E-Mail, Lademittel, ändern mit
Stand, veralteter Stand 409, deaktivieren); Bewegungen (Fehlerfälle, Vorzeichen Abgang +/Zugang −, Sortierung, stornieren
nur mit Grund, nicht doppelt, storniert zählt nicht, nie gelöscht); Abstimmungen (Frist aus Eingang + Tage des Partners,
Differenz zum eigenen Saldo zum Stichtag, Schnappschuss, Status mit Verlauf, veralteter Stand 409, Ampel, überfällig,
bestätigter Stand und „davon offen“ je Konto); Dachser-Abschreibungen (Fehlerfälle, Status mit Verlauf); Inventur;
Bilanz zum Stichtag (je Firma, Inventur, Wert, unvollständige Werte); CSV (BOM, keine Formeln, Protokoll); Lademittel
(umbenennen, Wert, neu, nicht entfernbar, deaktivieren); Datenpaket (Rechte, Vorschau mit Fehlern je Zeile, nichts
übernommen bei Fehlern, nur in leeres Modul oder mit „ersetzen“, Schnappschuss); Protokoll; Oberfläche (Übersicht,
Konto mit Saldo-Karten und Journal, Eingabemasken für Bewegung, Auszug, Abschreibung, Inventur, Partner, Lademittel,
Import der Datei, nur ansehen; 1280 und 390 px, hell und dunkel, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import json
import os

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'leergut', 'datenpaket.json')
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lea', 'Lea Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['leergut.sehen']}),
          ('bea', 'Bea Buchen', 'editor', 'Buchung-Konto-34', {'grant': ['leergut.bearbeiten']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-56', {'grant': ['leergut.verwalten']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-78', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Bb, V, O, N = K['lea'], K['bea'], K['vera'], K['otto'], Client('198.51.100.20')

# ── Register und Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['leergut']
ob = mod['oberflaechen'][0]
check('Register: Leergut fertig und produktiv (Auftrag des Inhabers 29.10.2026), Adresse leergut.dashboard-stafl.de/module/leergut/',
      ob['entwicklung'] == 'fertig' and ob['freigabe'] == 'produktiv' and ob['adresse'] == 'https://leergut.dashboard-stafl.de/module/leergut/', ob)
check('Kachel: verfügbar, Ziel leergut.intern', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True and mod['kachel']['ziel'] == 'leergut.intern', mod['kachel'])
check('produktiv ohne Testfreigabe: Administrator erreicht das Modul', A.call('leergut_start')[0] == 200)

# ── Rechte ──
check('ohne Anmeldung: kein Zugang (401/404)', N.call('leergut_start')[0] in (401, 404))
check('ohne Leergut-Recht (nur Modulzugang der Rolle): 403', O.call('leergut_start')[0] == 403)
st, r = L.call('leergut_start')
check('Ansehen: Start ok, ohne Bearbeiten und Verwalten, leer', st == 200 and r['rechte'] == {'bearbeiten': False, 'verwalten': False} and r['leer'] is True, r)
check('Grundwerte Lademittel: E2 5,50 €, H1 36,00 €, sieben Arten', [x['id'] for x in r['lademittel']] == ['e2', 'h1', 'eu', 'haken', 'e1', 'be2', 'kuebel']
      and r['lademittel'][0]['wert'] == 5.5 and r['lademittel'][1]['wert'] == 36.0 and r['lademittel'][2]['wert'] is None, r['lademittel'])
check('Buchen: bearbeiten ja, verwalten nein', Bb.call('leergut_start')[1]['rechte'] == {'bearbeiten': True, 'verwalten': False})
check('Verwalten: beides', V.call('leergut_start')[1]['rechte'] == {'bearbeiten': True, 'verwalten': True})

# ── Partner ──
P1 = {'name': 'Test-Spedition Nord', 'art': 'spedition', 'mandant': 'standard', 'kontoNr': '4711', 'fristTage': 14, 'email': 'leergut@example.invalid',
      'ansprechpartner': 'Frau Muster', 'lieferanten': 'Lieferant A, Lieferant B', 'lademittel': ['e2', 'h1', 'eu']}
check('Partner anlegen nur mit „verwalten“ (Buchen 403)', Bb.call('leergut_partner_save', P1)[0] == 403)
for name, b in (('ohne Name', {'name': ''}), ('Art unbekannt', {'art': 'freund'}), ('Firma unbekannt', {'mandant': 'xyz'}), ('Frist 100 Tage', {'fristTage': 100}),
                ('Frist Text', {'fristTage': 'bald'}), ('E-Mail ungültig', {'email': 'kein-at'}), ('Lademittel leer', {'lademittel': []}),
                ('Lademittel unbekannt', {'lademittel': ['zz']}), ('Name zu lang', {'name': 'x' * 101})):
    st, r = V.call('leergut_partner_save', {**P1, **b})
    check(f'Partner: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = V.call('leergut_partner_save', P1)
p1 = r.get('partner', {})
check('Partner angelegt (Kennung, Stand 1, Lademittel)', st == 200 and p1['id'].startswith('p') and p1['rev'] == 1 and p1['lademittel'] == ['e2', 'h1', 'eu']
      and p1['erstellt']['von'] == 'Vera Verwalten', r)
check('Partner doppelt (Groß/Klein egal) → 422', V.call('leergut_partner_save', {**P1, 'name': 'test-spedition nord'})[0] == 422)
st, r = V.call('leergut_partner_save', {'name': 'Kühlhaus Süd', 'art': 'kuehlhaus', 'mandant': 'matthies', 'fristTage': '', 'lademittel': ['e2', 'h1']})
p2 = r.get('partner', {})
check('zweiter Partner (Firma Matthies, ohne Frist = 0)', st == 200 and p2['mandant'] == 'matthies' and p2['fristTage'] == 0, r)
st, r = V.call('leergut_partner_save', {**P1, 'id': p1['id'], 'rev': 1, 'notiz': 'Abholung nur Mo–Fr'})
check('Partner ändern mit Stand', st == 200 and r['partner']['rev'] == 2 and r['partner']['notiz'] == 'Abholung nur Mo–Fr', r)
check('Partner: veralteter Stand 409', V.call('leergut_partner_save', {**P1, 'id': p1['id'], 'rev': 1})[0] == 409)
check('Partner: unbekannte Kennung 404', V.call('leergut_partner_save', {**P1, 'id': 'pnix', 'rev': 1})[0] == 404)

# ── Bewegungen ──
BW = {'partner': p1['id'], 'datum': '2026-01-10', 'typ': 'bewegung', 'abgang': {'e2': 10}, 'zugang': {'h1': 2}, 'beleg': 'LS-1001', 'text': 'Anlieferung'}
check('Bewegung: nur ansehen 403', L.call('leergut_bewegung_save', BW)[0] == 403)
csrf = Bb.csrf; Bb.csrf = ''
check('Bewegung ohne CSRF: 403', Bb.call('leergut_bewegung_save', BW)[0] == 403)
Bb.csrf = csrf
check('schreibende Aktion per GET: 405', Bb.call('leergut_bewegung_save')[0] == 405)
check('Bewegung: unbekannter Partner 404', Bb.call('leergut_bewegung_save', {**BW, 'partner': 'pnix'})[0] == 404)
for name, b in (('ohne Datum', {'datum': ''}), ('Datum 31.02.', {'datum': '2026-02-31'}), ('Datum deutsch', {'datum': '10.01.2026'}),
                ('negative Menge', {'abgang': {'e2': -3}}), ('Kommazahl', {'abgang': {'e2': 2.5}}), ('Text statt Zahl', {'zugang': {'h1': 'zwei'}}),
                ('unbekanntes Lademittel', {'abgang': {'zz': 1}}), ('keine Menge', {'abgang': {}, 'zugang': {'e2': 0}}), ('Art unbekannt', {'typ': 'geschenk'}),
                ('zu große Menge', {'abgang': {'e2': 2000000}})):
    st, r = Bb.call('leergut_bewegung_save', {**BW, **b})
    check(f'Bewegung: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Bb.call('leergut_bewegung_save', BW)
b1 = r.get('bewegung', {})
check('Bewegung gebucht (Abgang/Zugang, Herkunft von Hand, Name)', st == 200 and b1['abgang'] == {'e2': 10} and b1['zugang'] == {'h1': 2}
      and b1['quelle'] == 'hand' and b1['erfasst']['von'] == 'Bea Buchen' and b1['storno'] is None, r)
st, r = Bb.call('leergut_bewegung_save', {**BW, 'datum': '2026-02-01', 'abgang': {}, 'zugang': {'e2': '30'}, 'beleg': 'LS-1002'})
b2 = r.get('bewegung', {})
check('zweite Bewegung (Menge als Text „30“)', st == 200 and b2['zugang'] == {'e2': 30}, r)
st, r = Bb.call('leergut_bewegung_save', {**BW, 'datum': '2025-12-31', 'typ': 'anfang', 'abgang': {'eu': 5}, 'zugang': {}, 'beleg': '', 'text': 'Übernahme'})
b0 = r.get('bewegung', {})
check('Anfangsbestand', st == 200 and b0['typ'] == 'anfang', r)
st, k = L.call('leergut_konto&partner=' + p1['id'])
check('Konto: Bewegungen nach Datum', st == 200 and [b['id'] for b in k['bewegungen']] == [b0['id'], b1['id'], b2['id']], k)
konto = {x['id']: x for x in L.call('leergut_start')[1]['konten']}[p1['id']]
check('Saldo: + Abgang, − Zugang (E2 10 − 30 = −20, H1 −2, EU +5)', konto['saldo'] == {'e2': -20, 'h1': -2, 'eu': 5} and konto['letzteBewegung'] == '2026-02-01'
      and konto['bewegungen'] == 3, konto)
check('Stornieren ohne Grund → 422', Bb.call('leergut_bewegung_storno', {'id': b2['id'], 'grund': ''})[0] == 422)
check('Stornieren: nur ansehen 403', L.call('leergut_bewegung_storno', {'id': b2['id'], 'grund': 'Fehler'})[0] == 403)
st, r = Bb.call('leergut_bewegung_storno', {'id': b2['id'], 'grund': 'doppelt erfasst'})
check('storniert mit Grund und Name', st == 200 and r['bewegung']['storno']['grund'] == 'doppelt erfasst' and r['bewegung']['storno']['von'] == 'Bea Buchen', r)
check('nicht doppelt stornieren (409)', Bb.call('leergut_bewegung_storno', {'id': b2['id'], 'grund': 'nochmal'})[0] == 409)
check('Stornieren: unbekannt 404', Bb.call('leergut_bewegung_storno', {'id': 'bnix', 'grund': 'x'})[0] == 404)
st, k = L.call('leergut_konto&partner=' + p1['id'])
konto = {x['id']: x for x in L.call('leergut_start')[1]['konten']}[p1['id']]
check('storniert bleibt sichtbar, zählt aber nicht (E2 +10)', len(k['bewegungen']) == 3 and konto['saldo'] == {'e2': 10, 'h1': -2, 'eu': 5} and konto['bewegungen'] == 2, konto)
Bb.call('leergut_bewegung_save', {**BW, 'datum': '2026-03-05', 'abgang': {}, 'zugang': {'e2': 4}, 'beleg': 'LS-1003'})

# ── Abstimmungen ──
AB = {'partner': p1['id'], 'stichtag': '2026-01-31', 'eingang': '2026-02-10', 'saldo': {'e2': 8, 'h1': -2, 'eu': 5}, 'quelle': 'Mail vom 10.02.', 'notiz': ''}
check('Auszug: nur ansehen 403', L.call('leergut_abstimmung_save', AB)[0] == 403)
for name, b in (('ohne Stichtag', {'stichtag': ''}), ('Eingang vor Stichtag', {'eingang': '2026-01-01'}), ('Saldo Text', {'saldo': {'e2': 'acht'}}),
                ('Status unbekannt', {'status': 'egal'}), ('unbekanntes Lademittel', {'saldo': {'zz': 1}})):
    st, r = Bb.call('leergut_abstimmung_save', {**AB, **b})
    check(f'Auszug: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Bb.call('leergut_abstimmung_save', AB)
a1 = r.get('abstimmung', {})
check('Auszug erfasst: Frist = Eingang + 14 Tage, Status offen, negativer Saldo erlaubt', st == 200 and a1['fristBis'] == '2026-02-24' and a1['status'] == 'offen'
      and a1['saldo'] == {'e2': 8, 'h1': -2, 'eu': 5}, r)
check('Schnappschuss und Differenz zum eigenen Saldo zum Stichtag (E2 8 statt 10 → −2)', a1['eigen'] == {'e2': 10, 'h1': -2, 'eu': 5} and a1['differenz'] == {'e2': -2}, a1)
check('Ampel rot: Frist abgelaufen (gilt beim Partner als anerkannt)', a1['ampel'] == 'rot' and a1['restTage'] < 0, a1)
check('Verlauf: erfasst', a1['verlauf'][0]['was'] == 'erfasst (Offen)' and a1['verlauf'][0]['von'] == 'Bea Buchen', a1['verlauf'])
konto = {x['id']: x for x in L.call('leergut_start')[1]['konten']}[p1['id']]
check('Konto: eine offene, überfällige Abstimmung, Differenz', konto['abstimmungenOffen'] == 1 and konto['ueberfaellig'] == 1
      and konto['letzteAbstimmung']['differenz'] == {'e2': -2}, konto)
st, r = Bb.call('leergut_abstimmung_save', {**AB, 'id': a1['id'], 'rev': a1['rev'], 'status': 'widersprochen', 'notiz': 'LS-1001 nicht verbucht'})
check('Widersprochen: Status im Verlauf', st == 200 and r['abstimmung']['status'] == 'widersprochen' and r['abstimmung']['verlauf'][-1]['was'] == 'Status: Offen → Widersprochen'
      and r['abstimmung']['ampel'] == '', r)
check('Auszug: veralteter Stand 409 mit aktuellem Eintrag', (lambda s_r: s_r[0] == 409 and s_r[1]['eintrag']['status'] == 'widersprochen')(Bb.call('leergut_abstimmung_save', {**AB, 'id': a1['id'], 'rev': a1['rev']})))
st, r = Bb.call('leergut_abstimmung_save', {**AB, 'stichtag': '2026-02-28', 'eingang': '2026-03-02', 'saldo': {'e2': 10, 'h1': -2, 'eu': 5}, 'status': 'bestaetigt'})
check('zweiter Auszug sofort bestätigt (keine Differenz)', st == 200 and not r['abstimmung']['differenz'] and r['abstimmung']['status'] == 'bestaetigt', r)
konto = {x['id']: x for x in L.call('leergut_start')[1]['konten']}[p1['id']]
check('Konto: bestätigter Stand 28.02. und „davon offen“ seither (E2 −4)', konto['bestaetigt'] == {'stichtag': '2026-02-28', 'saldo': {'e2': 10, 'h1': -2, 'eu': 5}}
      and konto['offenSeitBestaetigung'] == {'e2': -4} and konto['saldo'] == {'e2': 6, 'h1': -2, 'eu': 5} and konto['abstimmungenOffen'] == 0, konto)
st, r = Bb.call('leergut_abstimmung_save', {'partner': p2['id'], 'stichtag': '2026-10-01', 'eingang': '2099-01-01', 'saldo': {'e2': -3}})
check('Partner ohne Frist: keine Frist, keine Ampel', st == 200 and r['abstimmung']['fristBis'] == '' and r['abstimmung']['ampel'] == '', r)
st, r = Bb.call('leergut_abstimmung_save', {**AB, 'stichtag': '2026-03-31', 'eingang': '2099-01-01', 'saldo': {}, 'fristBis': '2099-01-15'})
check('Frist von Hand, Ampel grün', st == 200 and r['abstimmung']['fristBis'] == '2099-01-15' and r['abstimmung']['ampel'] == 'gruen', r)

# ── Dachser-Abschreibungen ──
AS = {'zugestellt': '2026-04-08', 'auftrag': '2026-04-07', 'empfaenger': 'Testmarkt GmbH', 'empfaengerNr': '0001', 'ort': 'Teststadt', 'sendung': '0400000001',
      'menge': {'e2': 72, 'h1': 2}, 'grund': 'R Abschreibung lt. Empfänger'}
check('Abschreibung: nur ansehen 403', L.call('leergut_abschreibung_save', AS)[0] == 403)
for name, b in (('ohne Empfänger', {'empfaenger': ''}), ('ohne Menge', {'menge': {}}), ('ohne Zustelldatum', {'zugestellt': ''}), ('Status unbekannt', {'status': 'weg'})):
    st, r = Bb.call('leergut_abschreibung_save', {**AS, **b})
    check(f'Abschreibung: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Bb.call('leergut_abschreibung_save', AS)
d1 = r.get('abschreibung', {})
check('Abschreibung erfasst (offen)', st == 200 and d1['status'] == 'offen' and d1['menge'] == {'e2': 72, 'h1': 2}, r)
st, r = Bb.call('leergut_abschreibung_save', {**AS, 'id': d1['id'], 'rev': d1['rev'], 'status': 'berechnet', 'rechnung': 'Auftrag 760900'})
check('Abschreibung berechnet mit WinAB-Auftrag, Verlauf', st == 200 and r['abschreibung']['status'] == 'berechnet' and r['abschreibung']['rechnung'] == 'Auftrag 760900'
      and r['abschreibung']['verlauf'][-1]['was'] == 'Status: Offen → Berechnet', r)
check('Abschreibung: veralteter Stand 409', Bb.call('leergut_abschreibung_save', {**AS, 'id': d1['id'], 'rev': d1['rev']})[0] == 409)

# ── Inventur ──
check('Inventur: nur ansehen 403', L.call('leergut_inventur_save', {'stichtag': '2026-02-28', 'positionen': [{'name': 'Lager', 'werte': {'e2': 100}}]})[0] == 403)
for name, b in (('ohne Positionen', {'positionen': []}), ('Position ohne Name', {'positionen': [{'name': '', 'werte': {'e2': 1}}]}),
                ('negativer Bestand', {'positionen': [{'name': 'Lager', 'werte': {'e2': -1}}]})):
    st, r = Bb.call('leergut_inventur_save', {'stichtag': '2026-02-28', **b})
    check(f'Inventur: {name} → 422', st == 422, (st, r))
st, r = Bb.call('leergut_inventur_save', {'stichtag': '2026-02-28', 'positionen': [{'name': 'Lager gefüllt', 'werte': {'e2': 100, 'h1': 3}}, {'name': 'Kisten unbenutzt', 'werte': {'e2': 50}}],
                                          'notiz': 'Inventur Februar'})
check('Inventur erfasst', st == 200 and len(r['inventur']['positionen']) == 2, r)

# ── Bilanz ──
st, r = L.call('leergut_bilanz&stichtag=2026-02-28')
bil = r.get('bilanz', {})
check('Bilanz 28.02.: Konten, Firma Matthies ohne Buchung entfällt nicht (aktiver Partner)', st == 200 and [z['name'] for z in bil['zeilen']] == ['Test-Spedition Nord', 'Kühlhaus Süd'], bil)
check('Bilanz: Summe Konten, Inventur, Gesamt', bil['summe'] == {'e2': 10, 'h1': -2, 'eu': 5} and bil['bestand'] == {'e2': 150, 'h1': 3}
      and bil['gesamt'] == {'e2': 160, 'h1': 1, 'eu': 5} and bil['inventur']['stichtag'] == '2026-02-28', bil)
check('Bilanz: Wert (E2 10 × 5,50 − H1 2 × 36 = −17,00 €), Europalette ohne Wert → unvollständig',
      bil['zeilen'][0]['euro'] == {'betrag': -17.0, 'vollstaendig': False} and bil['euro']['gesamt']['betrag'] == 916.0, bil['euro'])
check('Bilanz: letzte Abstimmung bis Stichtag', bil['zeilen'][0]['abstimmung'] == {'stichtag': '2026-02-28', 'status': 'bestaetigt'}, bil['zeilen'][0])
check('Bilanz 31.01.: ohne Inventur', L.call('leergut_bilanz&stichtag=2026-01-31')[1]['bilanz']['inventur'] is None)
check('Bilanz: ungültiger Stichtag 422', L.call('leergut_bilanz&stichtag=gestern')[0] == 422)

# ── CSV ──
V.call('leergut_partner_save', {'name': '=HYPERLINK("http://x")', 'art': 'sonstige', 'lademittel': ['e2']})
st, _, raw = L.call('leergut_export', {'stichtag': '2026-02-28'}, raw=True)
check('CSV: BOM, Kopf mit Lademitteln, Summen', st == 200 and raw.startswith('﻿"Firma";"Partner";"Art";"E2-Kiste";"H1-Palette"') and '"Summe Konten"' in raw and '"Gesamt"' in raw, raw[:200])
check('CSV nur per POST', L.call('leergut_export')[0] == 405)
check('CSV: keine Formeln (Name mit „=“ wird entschärft), negative Zahlen bleiben Zahlen', '"\'=HYPERLINK' in raw and '"-2"' in raw, raw[:600])

# ── Lademittel ──
lm = L.call('leergut_start')[1]['lademittel']
check('Lademittel ändern: nur verwalten (403)', Bb.call('leergut_lademittel_save', {'lademittel': lm})[0] == 403)
neu = [{**x, 'wert': 4.5} if x['id'] == 'e2' else ({**x, 'name': 'H1 grau', 'wert': '45,00'} if x['id'] == 'h1' else x) for x in lm] + [{'name': 'Dolav-Box', 'wert': ''}]
st, r = V.call('leergut_lademittel_save', {'lademittel': neu})
check('Lademittel: Wert und Name geändert, neues mit Kennung aus dem Namen', st == 200 and r['lademittel'][0]['wert'] == 4.5 and r['lademittel'][1]['name'] == 'H1 grau'
      and r['lademittel'][1]['wert'] == 45.0 and r['lademittel'][-1]['id'] == 'dolavbox', r)
check('Lademittel entfernen → 422 (deaktivieren statt löschen)', V.call('leergut_lademittel_save', {'lademittel': r['lademittel'][1:]})[0] == 422)
check('Lademittel: doppelt → 422', V.call('leergut_lademittel_save', {'lademittel': r['lademittel'] + [{'id': 'e2', 'name': 'E2'}]})[0] == 422)
check('Lademittel: negativer Wert → 422', V.call('leergut_lademittel_save', {'lademittel': [{**r['lademittel'][0], 'wert': -1}] + r['lademittel'][1:]})[0] == 422)
st, r = V.call('leergut_lademittel_save', {'lademittel': [{**x, 'aktiv': x['id'] != 'kuebel'} for x in r['lademittel']]})
check('Lademittel deaktiviert', st == 200 and [x['aktiv'] for x in r['lademittel'] if x['id'] == 'kuebel'] == [False], r)

# ── Datenpaket ──
PAKET = json.load(open(PAKET_DATEI, encoding='utf-8'))
check('Datenpaket: buchen-Recht reicht nicht (403)', Bb.call('leergut_import', {'paket': PAKET, 'vorschau': True})[0] == 403)
check('Datenpaket: falsches Format → 422', V.call('leergut_import', {'paket': {'format': 'excel'}, 'vorschau': True})[0] == 422)
kaputt = json.loads(json.dumps(PAKET))
kaputt['bewegungen'].append({'partner': 'gibt-es-nicht', 'datum': '2026-01-01', 'abgang': {'e2': 1}})
kaputt['bewegungen'].append({'partner': PAKET['partner'][0]['schluessel'], 'datum': '2026-13-01', 'abgang': {'e2': 1}})
st, r = V.call('leergut_import', {'paket': kaputt, 'vorschau': True})
check('Vorschau: Zahlen und Fehler je Abschnitt und Zeile, Modul nicht leer', st == 200 and r['leer'] is False and len(r['fehler']) == 2
      and r['fehler'][0]['teil'] == 'bewegungen' and r['fehler'][0]['zeile'] == len(PAKET['bewegungen']) + 1 and 'unbekannter Partner' in r['fehler'][0]['text'], r)
st, r = V.call('leergut_import', {'paket': kaputt, 'ersetzen': True})
check('Übernahme mit Fehlern → 422, nichts übernommen', st == 422 and r['fehler'] and len(L.call('leergut_start')[1]['partner']) == 3, r)
st, r = V.call('leergut_import', {'paket': PAKET})
check('Übernahme in Modul mit Daten ohne „ersetzen“ → 409', st == 409, r)
st, r = V.call('leergut_import', {'paket': PAKET, 'ersetzen': True})
z = r.get('zahlen', {})
check('Übernahme mit „ersetzen“: Zahlen wie im Paket', st == 200 and z['partner'] == len(PAKET['partner']) and z['bewegungen'] == len(PAKET['bewegungen'])
      and z['abstimmungen'] == len(PAKET['abstimmungen']) and z['abschreibungen'] == len(PAKET['abschreibungen']) and z['inventur'] == len(PAKET['inventur']), r)
s = L.call('leergut_start')[1]
namen = {p['name']: p['id'] for p in s['partner']}
check('ersetzt: alte Partner weg, Lademittel aus dem Paket', 'Test-Spedition Nord' not in namen and set(namen) == {p['name'] for p in PAKET['partner']}
      and [x['id'] for x in s['lademittel']] == [x['id'] for x in PAKET['lademittel']], namen)
erw = {}
for b in PAKET['bewegungen']:
    if b['partner'] == 'spedition':
        for k, n in b.get('abgang', {}).items(): erw[k] = erw.get(k, 0) + n
        for k, n in b.get('zugang', {}).items(): erw[k] = erw.get(k, 0) - n
konto = {x['id']: x for x in s['konten']}[namen['Beispiel-Spedition']]
check('Saldo aus dem Paket nachgerechnet', konto['saldo'] == {k: n for k, n in erw.items() if n}, (konto['saldo'], erw))
abst = [a for a in s['abstimmungen'] if a['partner'] == namen['Beispiel-Spedition']]
check('Abstimmungen aus dem Paket mit Schnappschuss und Herkunft', abst and all(a.get('herkunft') == 'import' and isinstance(a['eigen'], dict) for a in abst), abst[:1])
check('Bewegungen aus dem Paket: Herkunft „import“', all(b['quelle'] == 'import' for b in L.call('leergut_konto&partner=' + namen['Beispiel-Spedition'])[1]['bewegungen']))

# ── Protokoll ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Buchung, Storno, Abstimmung, Export, Datenpaket', all(t in log for t in ('Leergut: Bewegung gebucht – Test-Spedition Nord', 'Leergut: Bewegung storniert',
      'Leergut: Abstimmung Test-Spedition Nord zum 2026-01-31 gespeichert (Widersprochen)', 'Leergut: Bilanz zum 2026-02-28 als CSV', 'Leergut: Datenpaket übernommen (vorhandene Daten ersetzt)')))
check('Protokoll ohne Notizen und Belegnummern', 'LS-1001' not in log and 'nicht verbucht' not in log)


# ── Oberfläche ──
s = V.call('leergut_start')[1]
HEUTE = s['heute']
HEUTE_DE = f'{HEUTE[8:10]}.{HEUTE[5:7]}.{HEUTE[:4]}'
namen = {p['name']: p['id'] for p in s['partner']}
SP = namen['Beispiel-Spedition']
saldo_sp = {x['id']: x for x in s['konten']}[SP]['saldo']


def vz(n):
    return ('+' if n > 0 else '−' if n < 0 else '') + f'{abs(n):,}'.replace(',', '.')


with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ').replace(' ', ' ')   # Zahlenformat: geschützte Leerzeichen vor €

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900, ziel='#lg-app:not([hidden])'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/leergut/'); pg.wait_for_selector(ziel)
        return ctx, pg

    def zu(pg, sel):
        pg.wait_for_selector(sel + '[open]', state='hidden')

    ctx, pg = anmelden('vera', 'Verwalt-Konto-56', '198.51.100.12')
    pg.wait_for_selector('#lg-u-kpis .lg-kpi')
    check('Übersicht: Adresse #uebersicht, Kennzahlen, Fristen, Salden mit Partnern', pg.url.endswith('#uebersicht') and pg.locator('#lg-u-kpis .lg-kpi').count() == 4
          and pg.locator('#lg-u-fristen .lg-frist').count() >= 2 and 'Beispiel-Schlachthof' in text(pg, '#lg-u-salden') and 'Summe aller Konten' in text(pg, '#lg-u-salden'))
    check('Verwalten: Schnellaktionen und Reiter Einstellungen sichtbar', pg.is_visible('#lg-neu-bewegung') and pg.is_visible('#lg-tabs [data-tab="einstellungen"]'))
    pg.screenshot(path=os.path.join(SH, 'leergut_uebersicht_1280.png'), full_page=True)

    # Konto mit Saldo-Karten
    pg.click('#lg-tabs [data-tab="konten"]')
    pg.click(f'#lg-k-liste [data-konto="{SP}"]'); pg.wait_for_selector('.lg-saldo')
    karten = text(pg, '#lg-k-detail .lg-salden')
    check('Konto: Adresse #konten/<Partner>, Karte je Lademittel mit Saldo, bestätigt (31.01.2026) und offen', pg.url.endswith('#konten/' + SP)
          and pg.locator('.lg-saldo').count() == 3 and vz(saldo_sp['e2']) in karten and 'davon bestätigt (31.01.2026)' in karten and 'davon offen' in karten, karten)
    check('Konto: Bewegungen mit laufendem Saldo und Herkunft', '= ' + vz(saldo_sp['e2']) in text(pg, '#lg-k-detail') and 'aus Excel' in text(pg, '#lg-k-detail'))
    pg.fill('#lg-k-suche', 'schlacht')
    check('Konten: Suche', pg.locator('#lg-k-liste [data-konto]').count() == 1)
    pg.fill('#lg-k-suche', '')
    pg.screenshot(path=os.path.join(SH, 'leergut_konto_1280.png'), full_page=True)

    # Eingabemaske Bewegung
    pg.click('[data-k-aktion="bewegung"]'); pg.wait_for_selector('#dlg-bewegung[open]')
    check('Bewegung: Partner vorausgewählt, Datum heute, Lademittel des Partners', pg.input_value('#bw-partner') == SP and pg.input_value('#bw-datum') == HEUTE
          and pg.locator('#bw-mengen tr').count() == 3)
    pg.fill('#bw-mengen [data-seite="a"][data-lm="e2"]', 'zwölf'); pg.click('#bw-form [type="submit"]')
    check('Bewegung: Text statt Zahl wird vor dem Senden gemeldet', 'ganze Stückzahlen' in text(pg, '#bw-meldung') and pg.get_attribute('#bw-mengen [data-seite="a"][data-lm="e2"]', 'aria-invalid') == 'true')
    pg.fill('#bw-mengen [data-seite="a"][data-lm="e2"]', '1.200'); pg.fill('#bw-mengen [data-seite="z"][data-lm="e2"]', '200'); pg.fill('#bw-beleg', 'UI-LS-1')
    check('Bewegung: Saldo danach rechnet mit', vz(saldo_sp['e2'] + 1000) in text(pg, '#bw-mengen [data-danach="e2"]'), text(pg, '#bw-mengen'))
    pg.check('#bw-alle')
    check('Bewegung: alle Lademittel zeigen, Eingaben bleiben', pg.locator('#bw-mengen tr').count() == len(s['lademittel']) and pg.input_value('#bw-mengen [data-seite="a"][data-lm="e2"]') == '1.200')
    pg.screenshot(path=os.path.join(SH, 'leergut_bewegung_1280.png'))
    pg.click('#bw-form [type="submit"]'); zu(pg, '#dlg-bewegung')
    pg.wait_for_function(f"(document.querySelector('#lg-k-detail .lg-salden')?.textContent || '').includes('{vz(saldo_sp['e2'] + 1000)}')")
    k = V.call('leergut_konto&partner=' + SP)[1]
    neu = [b for b in k['bewegungen'] if b['beleg'] == 'UI-LS-1']
    check('Oberfläche: Bewegung gebucht (deutsche Schreibweise 1.200)', len(neu) == 1 and neu[0]['abgang'] == {'e2': 1200} and neu[0]['zugang'] == {'e2': 200} and neu[0]['quelle'] == 'hand', neu)

    # Stornieren
    pg.click(f'[data-storno="{neu[0]["id"]}"]'); pg.wait_for_selector('#dlg-storno[open]')
    pg.click('#st-form [type="submit"]')
    check('Storno: ohne Grund gemeldet', 'Grund' in text(pg, '#st-meldung'))
    pg.fill('#st-grund', 'UI-Test doppelt'); pg.click('#st-form [type="submit"]'); zu(pg, '#dlg-storno')
    pg.wait_for_selector('#lg-k-detail tr.lg-storniert')
    check('Oberfläche: storniert, Saldo wieder wie vorher, Zeile durchgestrichen', {x['id']: x for x in V.call('leergut_start')[1]['konten']}[SP]['saldo'] == saldo_sp
          and 'UI-Test doppelt' in text(pg, '#lg-k-detail'))

    # Auszug erfassen mit umgekehrtem Vorzeichen
    pg.click('[data-k-aktion="auszug"]'); pg.wait_for_selector('#az-mengen [data-eigen]')
    check('Auszug: Stichtag und Eingang heute, unser Saldo zum Stichtag', pg.input_value('#az-stichtag') == HEUTE and pg.input_value('#az-eingang') == HEUTE
          and vz(saldo_sp['e2']) in text(pg, '#az-mengen [data-eigen="e2"]'))
    check('Auszug: Frist automatisch (Eingang + 14 Tage) als Hinweis', '14 Tage' in text(pg, '#az-frist-hilfe'))
    pg.fill('#az-mengen input[data-lm="e2"]', '120'); pg.click('#az-umkehren')
    check('Auszug: Vorzeichen umkehren', pg.input_value('#az-mengen input[data-lm="e2"]') == '-120')
    check('Auszug: Differenz rechnet mit', vz(-120 - saldo_sp['e2']) in text(pg, '#az-mengen [data-diff="e2"]'), text(pg, '#az-mengen'))
    pg.select_option('#az-status', 'widersprochen'); pg.fill('#az-quelle', 'UI-Auszug'); pg.fill('#az-notiz', 'Abholung fehlt')
    pg.screenshot(path=os.path.join(SH, 'leergut_auszug_1280.png'))
    pg.click('#az-form [type="submit"]'); zu(pg, '#dlg-auszug')
    a = [x for x in V.call('leergut_start')[1]['abstimmungen'] if x['quelle'] == 'UI-Auszug']
    check('Oberfläche: Auszug gespeichert (−120, widersprochen, Frist aus Eingang)', len(a) == 1 and a[0]['saldo'].get('e2') == -120 and a[0]['status'] == 'widersprochen'
          and a[0]['fristBis'] > HEUTE, a)
    pg.click('#lg-tabs [data-tab="uebersicht"]')
    pg.click(f'#lg-u-fristen [data-abst="{a[0]["id"]}"]'); pg.wait_for_selector('#dlg-auszug[open]')
    check('Auszug bearbeiten aus der Fristenliste: Werte und Verlauf', pg.input_value('#az-mengen input[data-lm="e2"]') == '-120' and pg.is_disabled('#az-partner')
          and 'erfasst (Widersprochen)' in text(pg, '#az-verlauf'))
    pg.select_option('#az-status', 'bestaetigt'); pg.click('#az-form [type="submit"]'); zu(pg, '#dlg-auszug')
    pg.wait_for_selector(f'#lg-u-fristen [data-abst="{a[0]["id"]}"]', state='detached')   # neu geladen: bestätigte stehen nicht mehr in der Fristenliste
    a = [x for x in V.call('leergut_start')[1]['abstimmungen'] if x['quelle'] == 'UI-Auszug'][0]
    check('Oberfläche: Status bestätigt mit Verlauf', a['status'] == 'bestaetigt' and any('Widersprochen → Bestätigt' in v['was'] for v in a['verlauf']), a['verlauf'])
    pg.click('#lg-tabs [data-tab="konten"]'); pg.wait_for_selector('.lg-saldo')
    pg.wait_for_function(f"(document.querySelector('#lg-k-detail .lg-salden')?.textContent || '').includes('({HEUTE_DE})')")
    check('Konto: bestätigter Stand jetzt heute', f'davon bestätigt ({HEUTE_DE})' in text(pg, '#lg-k-detail .lg-salden'), text(pg, '#lg-k-detail .lg-salden'))

    # Abstimmungen
    pg.click('#lg-tabs [data-tab="abstimmungen"]')
    offen = text(pg, '#lg-a-liste')
    pg.select_option('#lg-a-status', '')
    check('Abstimmungen: offen/widersprochen, „Alle“ zeigt auch bestätigte', 'Beispiel-Schlachthof' in offen and 'UI-Auszug' not in offen and 'UI-Auszug' in text(pg, '#lg-a-liste'))

    # Abschreibung
    pg.click('#lg-tabs [data-tab="abschreibungen"]')
    pg.click('#lg-d-neu'); pg.wait_for_selector('#dlg-abschr[open]')
    pg.fill('#ds-empfaenger', 'UI-Kunde'); pg.fill('#ds-zugestellt', '2026-10-01'); pg.fill('#ds-mengen [data-lm="e2"]', '5')
    check('Abschreibung: Wert bei Berechnung (5 × 5,50 €)', '27,50 €' in text(pg, '#ds-wert'), text(pg, '#ds-wert'))
    pg.click('#ds-form [type="submit"]'); zu(pg, '#dlg-abschr')
    pg.wait_for_function("(document.querySelector('#lg-d-liste')?.textContent || '').includes('UI-Kunde')")
    pg.click('#lg-d-liste [data-abschr] >> text=UI-Kunde'); pg.wait_for_selector('#dlg-abschr[open]')
    pg.select_option('#ds-status', 'ausgeglichen'); pg.fill('#ds-rechnung', 'WA-77'); pg.click('#ds-form [type="submit"]'); zu(pg, '#dlg-abschr')
    d = [x for x in V.call('leergut_start')[1]['abschreibungen'] if x['empfaenger'] == 'UI-Kunde']
    check('Oberfläche: Abschreibung erfasst und ausgeglichen', len(d) == 1 and d[0]['menge'] == {'e2': 5} and d[0]['status'] == 'ausgeglichen' and d[0]['rechnung'] == 'WA-77', d)
    pg.wait_for_function("!(document.querySelector('#lg-d-liste')?.textContent || '').includes('UI-Kunde')")
    check('Abschreibungen: Filter „Offen“ blendet ausgeglichene aus', 'UI-Kunde' not in text(pg, '#lg-d-liste'))

    # Bilanz, Inventur, CSV
    pg.click('#lg-tabs [data-tab="bilanz"]'); pg.wait_for_selector('#lg-b-tabelle table')
    check('Bilanz: Stichtag heute, je Firma, Gesamt', pg.input_value('#lg-b-tag') == HEUTE and 'Matthies Fleischwaren' in text(pg, '#lg-b-tabelle') and 'Gesamt' in text(pg, '#lg-b-tabelle'))
    n_inv = len(V.call('leergut_start')[1]['inventur'])
    pg.click('#lg-i-neu'); pg.wait_for_selector('#dlg-inventur[open]')
    check('Inventur: drei Positionen wie in der Excel-Liste', pg.locator('#iv-zeilen tr').count() == 3)
    pg.fill('#iv-zeilen tr:first-child [data-lm="e2"]', '100'); pg.click('#iv-form [type="submit"]'); zu(pg, '#dlg-inventur')
    pg.wait_for_function(f"(document.querySelector('#lg-b-tabelle')?.textContent || '').includes('Inventur {HEUTE_DE}')")
    check('Oberfläche: Inventur gespeichert, Bilanz zeigt eigenen Bestand', len(V.call('leergut_start')[1]['inventur']) == n_inv + 1)
    with pg.expect_download() as dl:
        pg.click('#lg-b-csv')
    datei = dl.value
    inhalt = open(datei.path(), 'rb').read()
    check('CSV aus der Oberfläche (Dateiname, BOM, Gesamt)', datei.suggested_filename == f'Leergut-Bilanz_{HEUTE}.csv' and inhalt.startswith(b'\xef\xbb\xbf') and 'Gesamt' in inhalt.decode('utf-8'))
    pg.screenshot(path=os.path.join(SH, 'leergut_bilanz_1280.png'), full_page=True)

    # Einstellungen: Partner, Lademittel, Datenpaket
    pg.click('#lg-tabs [data-tab="einstellungen"]')
    pg.click('#lg-e-partner-neu'); pg.wait_for_selector('#dlg-partner[open]')
    check('Partner: Frist 14 Tage und E2/H1 vorgeschlagen', pg.input_value('#pa-frist') == '14' and pg.is_checked('#pa-lm input[value="e2"]') and pg.is_checked('#pa-lm input[value="h1"]'))
    pg.fill('#pa-name', 'UI-Kühlhaus'); pg.select_option('#pa-art', 'kuehlhaus'); pg.fill('#pa-email', 'kein-at')
    pg.click('#pa-form [type="submit"]'); pg.wait_for_selector('#pa-meldung:not(:empty)')
    check('Partner: Fehler des Servers im Dialog', 'E-Mail' in text(pg, '#pa-meldung'))
    pg.fill('#pa-email', 'ui@example.invalid'); pg.click('#pa-form [type="submit"]'); zu(pg, '#dlg-partner')
    pa = [x for x in V.call('leergut_start')[1]['partner'] if x['name'] == 'UI-Kühlhaus']
    check('Oberfläche: Partner angelegt', len(pa) == 1 and pa[0]['art'] == 'kuehlhaus' and pa[0]['fristTage'] == 14 and pa[0]['lademittel'] == ['e2', 'h1'], pa)
    pg.wait_for_function("(document.querySelector('#lg-e-partner')?.textContent || '').includes('UI-Kühlhaus')")
    pg.fill('#lg-e-lm tr[data-id="e2"] [data-f="wert"]', '6,25'); pg.click('#lg-e-lm-form [type="submit"]')
    pg.wait_for_function("(document.querySelector('#lg-e-lm tr[data-id=\"e2\"] [data-f=\"wert\"]')?.value || '') === '6,25'")
    check('Oberfläche: Wert E2 geändert (6,25 €)', V.call('leergut_start')[1]['lademittel'][0]['wert'] == 6.25)
    pg.set_input_files('#lg-e-datei', PAKET_DATEI)
    pg.wait_for_selector('#lg-e-import-knoepfe:not([hidden])')
    vor = text(pg, '#lg-e-vorschau')
    check('Datenpaket: Vorschau mit Zahlen, „ersetzen“ nötig (Modul nicht leer)', str(len(PAKET['bewegungen'])) in vor and pg.is_visible('#lg-e-ersetzen-zeile') and pg.is_disabled('#lg-e-uebernehmen'), vor)
    pg.check('#lg-e-ersetzen'); pg.click('#lg-e-uebernehmen')
    pg.wait_for_selector('#lg-tabs [data-tab="uebersicht"][aria-selected="true"]')
    nach = V.call('leergut_start')[1]
    check('Oberfläche: Datenpaket übernommen (UI-Daten ersetzt)', {x['name'] for x in nach['partner']} == {x['name'] for x in PAKET['partner']} and nach['lademittel'][0]['wert'] == 5.5)
    SP = {x['name']: x['id'] for x in nach['partner']}['Beispiel-Spedition']   # neue Kennungen nach dem Ersetzen
    ctx.close()

    # Nur ansehen: Handy und dunkel
    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('lea', 'Leserin-Konto-12', '198.51.100.10', breite, thema, 844 if breite < 500 else 900)
        pg.wait_for_selector('#lg-u-kpis .lg-kpi')
        check(f'{breite}px {thema}: nur ansehen (keine Schnellaktionen, keine Einstellungen)', pg.is_hidden('#lg-schnell') and pg.is_hidden('#lg-tabs [data-tab="einstellungen"]'))
        breit = []
        for tab in ('uebersicht', 'konten', 'abstimmungen', 'abschreibungen', 'bilanz'):
            pg.click(f'#lg-tabs [data-tab="{tab}"]')
            if tab == 'konten':
                pg.click(f'#lg-k-liste [data-konto="{SP}"]'); pg.wait_for_selector('.lg-saldo')
            if tab == 'bilanz':
                pg.wait_for_selector('#lg-b-tabelle table')
            if not pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'):
                breit.append(tab)
            if breite == 390:
                pg.screenshot(path=os.path.join(SH, f'leergut_{tab}_{breite}_{thema}.png'), full_page=True)
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', not breit, breit)
        pg.click('#lg-tabs [data-tab="konten"]')
        check(f'{breite}px {thema}: Konto ohne Buchen-Knöpfe', pg.locator('[data-k-aktion="bewegung"], [data-storno]').count() == 0)
        if thema == 'dark':
            check(f'{breite}px: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)')
        ctx.close()

    ctx, pg = anmelden('otto', 'Ohne-Konto-78', '198.51.100.13', ziel='#lg-err:not([hidden])')
    check('ohne Leergut-Recht: Hinweis statt Inhalt', 'Berechtigung' in text(pg, '#lg-err') and pg.is_hidden('#lg-app'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
