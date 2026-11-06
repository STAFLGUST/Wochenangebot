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
übernommen bei Fehlern, nur in leeres Modul oder mit „ersetzen“, Schnappschuss); WinAB-Bericht „Lademittelbewegungen Kunden“
(Rechte, Fehler je Beleg, Vorschau schreibt nichts, Kundenkonten mit Nummer im Namen, Kundennummer am Partner eindeutig und
nur Ziffern, Vorzeichen, Gutschrift als Abholung, erneuter Bericht unverändert, geändert → storniert und neu, fehlend →
ausgeglichen, nur Zeitraum und Kunden des Berichts; in der Oberfläche eine erfundene .XLS im WinAB-Aufbau: Sammelrechnungen,
Karton, Offerten und reiner Tausch weggelassen, Kunden zusammengefasst in Übersicht und Bilanz); Leergut bei Kunden (letzte
Lieferung und Rückgabe aus Buchungen und Bericht, unbekannt bei älteren WinAB-Buchungen, frühere Berichte bleiben gültig,
Abholliste als CSV mit Rechten, Übersicht nach Wert mit Ampel, Konten nach Wert); Dachser-Liste „Unterkonto-Vorspediteur“
(Rechte, Fälle je Sendung, REWE nur H1, mehrfach, unbekanntes Packmittel, Summe = Saldo laut Dachser, schon erfasst, ergänzt,
andere Menge, abgeschlossener Fall, .eml mit quoted-printable/ISO-8859-1, unlesbares Datum, überlange Zeile: langer Absatz
ohne Fall wird übergangen, überlange Fallzeile kommt als Fehler „Zeile zu lang“ zurück und die Antwort kommt in Sekunden
statt Minuten; Dialog mit Datei, 390 px); Protokoll; Oberfläche (Übersicht,
Konto mit Saldo-Karten und Journal, Eingabemasken für Bewegung, Auszug, Abschreibung, Inventur, Partner, Lademittel,
Import der Datei, nur ansehen; 1280 und 390 px, hell und dunkel, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import datetime
import json
import os
import tempfile
import time

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

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
check('Grundwerte Lademittel: E2 5,50 €, H1 36,00 €, neun Arten (mit Karton und WK2-Kiste aus WinAB)',
      [x['id'] for x in r['lademittel']] == ['e2', 'h1', 'eu', 'haken', 'e1', 'be2', 'kuebel', 'karton', 'wk2']
      and r['lademittel'][0]['wert'] == 5.5 and r['lademittel'][1]['wert'] == 36.0 and r['lademittel'][2]['wert'] is None, r['lademittel'])
check('WinAB-Stammdaten: Nummer und Kurzbezeichnung wie in WinAB („Lademittel suchen“), E1 und Blaue E2 ohne Nummer',
      {x['id']: (x.get('winabNr', ''), x.get('kurz', '')) for x in r['lademittel']} == {'e2': ('1', 'E2'), 'h1': ('2', 'H1'), 'kuebel': ('3', 'KÜ'), 'eu': ('4', 'EU'),
      'karton': ('5', 'KT'), 'haken': ('6', 'EH'), 'wk2': ('7', 'WK2'), 'e1': ('', ''), 'be2': ('', '')}, r['lademittel'])
check('Karton angelegt, aber inaktiv (kein Leergut); WK2-Kiste aktiv', {x['id']: x['aktiv'] for x in r['lademittel']}['karton'] is False
      and {x['id']: x['aktiv'] for x in r['lademittel']}['wk2'] is True and [x['name'] for x in r['lademittel'] if x['id'] == 'wk2'] == ['WK2-Kiste'])
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
V.call('leergut_partner_save', {'name': '\x01\t=HYPERLINK("http://x")', 'art': 'sonstige', 'lademittel': ['e2']})   # auch nach Steuerzeichen/Tabulator
st, _, raw = L.call('leergut_export', {'stichtag': '2026-02-28'}, raw=True)
check('CSV: BOM, Kopf mit Lademitteln, Summen', st == 200 and raw.startswith('﻿"Firma";"Partner";"Art";"E2-Kiste";"H1-Palette"') and '"Summe Konten"' in raw and '"Gesamt"' in raw, raw[:200])
check('CSV nur per POST', L.call('leergut_export')[0] == 405)
check('CSV: keine Formeln (Name mit „=“ wird entschärft), negative Zahlen bleiben Zahlen', '"\'=HYPERLINK' in raw and '"\t' not in raw and '"-2"' in raw, raw[:600])

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
check('Lademittel gespeichert: WinAB-Nummern bleiben (auch ergänzte), neues ohne Nummer', st == 200
      and {x['id']: x.get('winabNr', '') for x in r['lademittel']}.get('wk2') == '7' and {x['id']: x.get('winabNr', '') for x in r['lademittel']}.get('dolavbox', '') == '', r)
lm2 = r['lademittel']
for name, aend in (('WinAB-Nr. doppelt', {'winabNr': '1'}), ('WinAB-Nr. mit Buchstaben', {'winabNr': '7a'}), ('WinAB-Nr. zu lang', {'winabNr': '12345'}),
                   ('Kurzbezeichnung zu lang', {'kurz': 'X' * 9})):
    st, r = V.call('leergut_lademittel_save', {'lademittel': [({**x, **aend} if x['id'] == 'dolavbox' else x) for x in lm2]})
    check(f'Lademittel: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = V.call('leergut_lademittel_save', {'lademittel': [({**x, 'winabNr': '8', 'kurz': 'DB'} if x['id'] == 'dolavbox' else x) for x in lm2]})
check('Lademittel: eigene WinAB-Nr. und Kurzbezeichnung', st == 200 and [(x['winabNr'], x['kurz']) for x in r['lademittel'] if x['id'] == 'dolavbox'] == [('8', 'DB')], r)

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
check('ersetzt: alte Partner weg, Lademittel aus dem Paket, fehlende WinAB-Lademittel ergänzt (Kübel, Karton inaktiv, WK2-Kiste)',
      'Test-Spedition Nord' not in namen and set(namen) == {p['name'] for p in PAKET['partner']}
      and [x['id'] for x in s['lademittel']] == [x['id'] for x in PAKET['lademittel']] + ['kuebel', 'karton', 'wk2']
      and [x.get('winabNr') for x in s['lademittel'] if x['id'] in ('e2', 'haken')] == ['1', '6'], (namen, s['lademittel']))
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

# ── WinAB-Bericht „Lademittelbewegungen Kunden“ ──
# Erfundener Bericht im Aufbau des WinAB-Exports (BIFF wie die echte .XLS): Kopf je Kunde und Lademittel, Bewegungen,
# Summenzeilen, Sammelwerte oben, Auswertungszeitraum unten. Die Oberfläche liest ihn im Browser; die API-Prüfungen
# schicken dieselben Belege als JSON.
WLM = {1: 'E2 Kisten', 2: 'H1 Paletten', 4: 'Euro-Paletten', 5: 'Karton'}
WZEILEN = [  # Kd.-Nr., Name, Lademittel, Belegnr., Belegart, Datum (TTMMJJJJ), Bewegungsart, Menge
    (9100001, 'Testkunde Nord GmbH', 1, 500001, 'Lieferschein', 2032026, 'Abgang', -10),
    (9100001, 'Testkunde Nord GmbH', 1, 500001, 'Lieferschein', 2032026, 'Zugang', 4),
    (9100001, 'Testkunde Nord GmbH', 1, 900001, 'Sammelrechnun', 6032026, 'Abgang', -10),
    (9100001, 'Testkunde Nord GmbH', 1, 500002, 'Lieferschein', 9032026, 'Abgang', -5),
    (9100001, 'Testkunde Nord GmbH', 1, 500002, 'Lieferschein', 9032026, 'Zugang', 5),
    (9100001, 'Testkunde Nord GmbH', 2, 500001, 'Lieferschein', 2032026, 'Abgang', -1),
    (9100001, 'Testkunde Nord GmbH', 5, 500001, 'Lieferschein', 2032026, 'Abgang', -3),
    (9100002, 'Testkunde Süd', 1, 600001, 'Gutschrift', 1042026, 'Zugang', 7),
    (9100002, 'Testkunde Süd', 1, 700001, 'Rechnung', 2042026, 'Abgang', -2),
    (9100002, 'Testkunde Süd', 1, None, 'Offerte', 3042026, 'Zugang', 2),
    (9100003, 'Testkunde Nord GmbH', 1, 500010, 'Lieferschein', 15102026, 'Abgang', -3),
    (9100004, 'Nur Tausch KG', 4, 500020, 'Lieferschein', 5052026, 'Abgang', -2),
    (9100004, 'Nur Tausch KG', 4, 500020, 'Lieferschein', 5052026, 'Zugang', 2),
]


def winab_xls(zeilen=WZEILEN, stand='15.10.2026', titel='Lademittelbewegungen Kunden'):
    """BIFF-Datei (Datensätze BOF, LABEL, NUMBER, EOF wie im WinAB-Export) aus den Bewegungszeilen."""
    import struct
    reihen = [{0: 'Standard Fleisch HH', 7: titel, 21: 'Datum:' + stand},
              {1: 'Kunden-Nr.', 3: 'Name', 8: 'Belegnr.', 9: 'Belegart', 14: 'Datum', 16: 'Bewegungsart', 19: 'Menge'}]
    for nr, wert in ((1, -12), (5, 348)):   # Sammelwerte oben (nur zur Information)
        reihen += [{1: 'Hinweis: Ein Minuswert bedeutet,'}, {13: 'Summe', 17: 'Lademittel', 18: nr, 20: wert}, {1: 'dass mehr Lademittel an den Kunden abgegeben wie zurückgenommen wurden.'}]
    bloecke = {}
    for z in zeilen:
        bloecke.setdefault((z[0], z[2]), []).append(z)
    for (kd, lmnr), zz in bloecke.items():
        reihen += [{2: kd, 3: zz[0][1], 10: 'Lademittel', 11: lmnr, 12: WLM[lmnr]}, {}, {}]
        for z in zz:
            reihen.append({k: v for k, v in {2: z[0], 3: z[1], 8: z[3], 9: z[4], 14: z[5], 16: z[6], 20: z[7]}.items() if v is not None})
        reihen += [{1: 'Hinweis: Ein Minuswert bedeutet,'}, {13: 'Summe', 17: 'Lademittel', 18: lmnr, 20: sum(z[7] for z in zz)},
                   {1: 'dass mehr Lademittel an den Kunden abgegeben wie zurückgenommen wurden.'}]
    reihen += [{}, {0: 'Auswertungszeitraum', 4: 1012026, 5: 'bis', 6: 31122078}, {0: 'Sätze Gesamt:   99'}]
    out = bytearray(struct.pack('<HHHH', 0x0809, 4, 0, 0x10))
    for r, zellen in enumerate(reihen):
        for c, v in sorted(zellen.items()):
            if isinstance(v, str):
                t = v.encode('cp1252')
                out += struct.pack('<HHHH', 0x0004, 8 + len(t), r, c) + b'\0\0\0' + bytes([len(t)]) + t
            else:
                out += struct.pack('<HHHH', 0x0003, 15, r, c) + b'\0\0\0' + struct.pack('<d', float(v))
    out += struct.pack('<HH', 0x000a, 0)
    return bytes(out)


# Erfundene Datei im Aufbau des WinAB-Exports „Lademittelbewegungen komplett“ (CSV, Semikolon, Windows-1252): Kundenzeilen (auch
# mit zusätzlicher Lieferantennummer – zählt dort nicht), Sammelrechnung (wiederholt den Lieferschein), Karton, Korrekturzeilen mit
# Minus, älterer Beleg, Lieferanten mit und ohne Tausch, Offerte, Kübel.
WCSV = [  # Lademittel, Datum, Kunde, Lieferant, Menge, Bewegungsart, Belegnr., Belegart, Bezeichnung
    (1, '01.09.2026', '9100006', '4000017', 10, 'Abgang', '820001', 'Lieferschein', 'E2 Kisten'),
    (1, '01.09.2026', '9100006', '4000017', 6, 'Zugang', '820001', 'Lieferschein', 'E2 Kisten'),
    (1, '05.09.2026', '9100006', '4000017', 10, 'Abgang', '920001', 'Sammelrechnung', 'E2 Kisten'),
    (5, '01.09.2026', '9100006', '4000017', 5, 'Abgang', '820001', 'Lieferschein', 'Karton'),
    (1, '02.09.2026', '9100006', '', 8, 'Abgang', '820002', 'Lieferschein', 'E2 Kisten'),
    (1, '02.09.2026', '9100006', '', -8, 'Abgang', '820002', 'Lieferschein', 'E2 Kisten'),
    (1, '03.09.2026', '9100007', '', 6, 'Abgang', '820003', 'Lieferschein', 'E2 Kisten'),
    (1, '03.09.2026', '9100007', '', -2, 'Abgang', '820003', 'Lieferschein', 'E2 Kisten'),
    (2, '03.09.2026', '9100007', '', 1, 'Abgang', '820003', 'Lieferschein', 'H1 Paletten'),
    (1, '05.06.2021', '9100008', '', 9, 'Abgang', '120001', 'Lieferschein', 'E2 Kisten'),
    (1, '04.09.2026', '', '2930028', 15, 'Zugang', '44319', 'Lieferschein', 'E2 Kisten'),
    (1, '05.09.2026', '', '2850008', 5, 'Zugang', '44020', 'Lieferschein', 'E2 Kisten'),
    (1, '05.09.2026', '', '2850008', 5, 'Abgang', '44020', 'Lieferschein', 'E2 Kisten'),
    (1, '06.09.2026', '', '2300004', 4, 'Abgang', '44021', 'Lieferschein', 'E2 Kisten'),
    (1, '06.09.2026', '9100007', '', 3, 'Zugang', '0', 'Offerte', 'E2 Kisten'),
    (3, '07.09.2026', '9100007', '', 2, 'Abgang', '820004', 'Lieferschein', 'Kübel'),
]


def winab_csv(zeilen=WCSV):
    q = lambda v: '' if v == '' else f'"{v}"'
    kopf = '"Lademittel";"Datum";"Kunde";"Lieferant";"Menge";"Bewegungsart";"Belegnummer";"Belegart";"Bezeichnung";"Art"'
    return ('\r\n'.join([kopf] + [';'.join(q(x) for x in (*z, z[5][:2])) for z in zeilen]) + '\r\n').encode('cp1252')


WB = {'bericht': {'datei': 'Lademittel_Test.XLS', 'von': '2026-01-01', 'bis': '2026-10-15', 'datum': '2026-10-15'},
      'kunden': [{'nr': '9100001', 'name': 'Testkunde Nord GmbH'}, {'nr': '9100002', 'name': 'Testkunde Süd'},
                 {'nr': '9100003', 'name': 'Testkunde Nord GmbH'}, {'nr': '9100004', 'name': 'Nur Tausch KG'}],
      'belege': [{'kd': '9100001', 'art': 'Lieferschein', 'beleg': '500001', 'datum': '2026-03-02', 'abgang': {'e2': 10, 'h1': 1}, 'zugang': {'e2': 4}},
                 {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '500002', 'datum': '2026-03-09', 'abgang': {'e2': 5}, 'zugang': {'e2': 5}},
                 {'kd': '9100002', 'art': 'Gutschrift', 'beleg': '600001', 'datum': '2026-04-01', 'abgang': {}, 'zugang': {'e2': 7}},
                 {'kd': '9100002', 'art': 'Rechnung', 'beleg': '700001', 'datum': '2026-04-02', 'abgang': {'e2': 2}, 'zugang': {}},
                 {'kd': '9100003', 'art': 'Lieferschein', 'beleg': '500010', 'datum': '2026-10-15', 'abgang': {'e2': 3}, 'zugang': {}}]}


def wb(**aend):
    x = json.loads(json.dumps(WB)); x.update(aend); return x


check('WinAB: buchen-Recht reicht nicht (403), nur ansehen 403, ohne Anmeldung kein Zugang',
      Bb.call('leergut_winab_import', {**WB, 'vorschau': True})[0] == 403 and L.call('leergut_winab_import', {**WB, 'vorschau': True})[0] == 403
      and N.call('leergut_winab_import', {**WB, 'vorschau': True})[0] in (401, 403, 404))
for name, b in (('„bis“ vor „von“', wb(bericht={**WB['bericht'], 'von': '2026-11-01'})), ('Datum ungültig', wb(bericht={**WB['bericht'], 'bis': '2026-02-30'})),
                ('Kundennummer mit Buchstaben', wb(kunden=[{'nr': '10A', 'name': 'X'}])), ('Kundenliste fehlt', wb(kunden='alle'))):
    st, r = V.call('leergut_winab_import', {**b, 'vorschau': True})
    check(f'WinAB: {name} → 422', st == 422 and r.get('error'), (st, r))
schlecht = wb(belege=WB['belege'] + [{'kd': '1009999', 'art': 'Lieferschein', 'beleg': '1', 'datum': '2026-05-01', 'abgang': {'e2': 1}},
                                     {'kd': '9100001', 'art': 'Sammelrechnung', 'beleg': '2', 'datum': '2026-05-01', 'abgang': {'e2': 1}},
                                     {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '3', 'datum': '2026-10-20', 'abgang': {'e2': 1}},
                                     {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '500001', 'datum': '2026-03-02', 'abgang': {'e2': 1}},
                                     {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '4', 'datum': '2026-05-01', 'abgang': {'karton': 1}},
                                     {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '5', 'datum': '2026-05-01', 'abgang': {'e2': -1}}])
st, r = V.call('leergut_winab_import', {**schlecht, 'vorschau': True})
texte = [f['text'] for f in r.get('fehler', [])]
check('WinAB-Vorschau: Fehler je Beleg (Kunde fehlt, Sammelrechnung, außerhalb des Zeitraums, doppelt, Karton, negativ)', st == 200 and len(texte) == 6
      and 'fehlt in der Kundenliste' in texte[0] and 'Belegart' in texte[1] and 'außerhalb' in texte[2] and 'doppelt' in texte[3] and [f['zeile'] for f in r['fehler']][:1] == [6], r)
n_p = len(V.call('leergut_start')[1]['partner'])
st, r = V.call('leergut_winab_import', schlecht)
check('WinAB mit Fehlern übernehmen → 422, nichts angelegt', st == 422 and r.get('fehler') and len(V.call('leergut_start')[1]['partner']) == n_p, (st, r.get('error')))

# Kunde, der schon von Hand angelegt ist: die WinAB-Kundennummer verknüpft ihn
st, r = V.call('leergut_partner_save', {'name': 'Testkunde Süd (von Hand)', 'art': 'kunde', 'kundenNr': '9100002', 'lademittel': ['e2']})
hand = r.get('partner', {})
check('Partner mit WinAB-Kundennummer', st == 200 and hand.get('kundenNr') == '9100002', r)
check('WinAB-Kundennummer: nur Ziffern (422)', V.call('leergut_partner_save', {'name': 'Kunde X', 'art': 'kunde', 'kundenNr': '12-34', 'lademittel': ['e2']})[0] == 422)
st, r = V.call('leergut_partner_save', {'name': 'Kunde Y', 'art': 'kunde', 'kundenNr': '9100002', 'lademittel': ['e2']})
check('WinAB-Kundennummer doppelt → 422 mit Namen', st == 422 and 'Testkunde Süd (von Hand)' in r.get('error', ''), r)
# WinAB-Lieferantennummer (Lieferanten, Speditionen) – wie die Kundennummer: nur Ziffern, eindeutig, bleibt ohne Angabe
st, r = V.call('leergut_partner_save', {'name': 'Testlieferant WinAB', 'art': 'lieferant', 'lieferantNr': '2850008', 'lademittel': ['e2']})
lief = r.get('partner', {})
check('Partner mit WinAB-Lieferantennummer', st == 200 and lief.get('lieferantNr') == '2850008', r)
check('WinAB-Lieferantennummer: nur Ziffern (422)', V.call('leergut_partner_save', {'name': 'Lieferant X', 'art': 'lieferant', 'lieferantNr': '28-5', 'lademittel': ['e2']})[0] == 422)
st, r = V.call('leergut_partner_save', {'name': 'Lieferant Y', 'art': 'spedition', 'lieferantNr': '2850008', 'lademittel': ['e2']})
check('WinAB-Lieferantennummer doppelt → 422 mit Namen', st == 422 and 'Testlieferant WinAB' in r.get('error', ''), r)
st, r = V.call('leergut_partner_save', {'id': lief['id'], 'rev': lief['rev'], 'name': lief['name'], 'art': 'lieferant', 'lademittel': ['e2']})
check('Partner ändern ohne Lieferantennummer im Aufruf: Nummer bleibt', st == 200 and r['partner']['lieferantNr'] == '2850008', r)
st, r = V.call('leergut_partner_save', {'id': hand['id'], 'rev': hand['rev'], 'name': hand['name'], 'art': 'kunde', 'lademittel': ['e2'], 'notiz': 'ohne Nummer gesendet'})
check('Partner ändern ohne Kundennummer im Aufruf: Nummer bleibt', st == 200 and r['partner']['kundenNr'] == '9100002', r)

st, r = V.call('leergut_winab_import', {**WB, 'vorschau': True})
z = r.get('zahlen', {})
check('WinAB-Vorschau: 2 neue Kundenkonten, 4 neue Belege, 1 ohne Wirkung, Saldo danach', st == 200 and not r['fehler'] and z.get('kunden') == 2 and z['neu'] == 4
      and z['gleich'] == 0 and z['ohneWirkung'] == 1 and r['summe'] == {'e2': 4, 'h1': 1} and z['konten'] == 3, r)
check('WinAB-Vorschau schreibt nichts', len(V.call('leergut_start')[1]['partner']) == n_p + 2 and not any(b.get('quelle') == 'winab' for b in V.call('leergut_konto&partner=' + hand['id'])[1]['bewegungen']))
st, r = V.call('leergut_winab_import', WB)
check('WinAB übernommen', st == 200 and r['zahlen']['neu'] == 4 and sorted(r['neueKunden']) == ['Testkunde Nord GmbH (9100001)', 'Testkunde Nord GmbH (9100003)'], r)
s = V.call('leergut_start')[1]
wk = {p['kundenNr']: p for p in s['partner'] if p.get('kundenNr')}
salden = {x['id']: x['saldo'] for x in s['konten']}
check('WinAB: Kundenkonten mit Kundennummer im Namen (gleiche Namen unterscheidbar), Art Kunde, Herkunft winab', set(wk) == {'9100001', '9100002', '9100003'}
      and wk['9100001']['name'] == 'Testkunde Nord GmbH (9100001)' and wk['9100003']['name'] == 'Testkunde Nord GmbH (9100003)'
      and all(wk[k]['art'] == 'kunde' and wk[k]['quelle'] == 'winab' and wk[k]['mandant'] == 'standard' for k in ('9100001', '9100003')), wk)
check('WinAB: Salden – Abgang an den Kunden +, Rückgabe −, Gutschrift/Rechnung, nur Tausch zählt nicht', salden[wk['9100001']['id']] == {'e2': 6, 'h1': 1}
      and salden[wk['9100002']['id']] == {'e2': -5} and salden[wk['9100003']['id']] == {'e2': 3} and '9100004' not in wk, {k: salden[p['id']] for k, p in wk.items()})
check('WinAB: von Hand angelegter Kunde bleibt von Hand (nur verknüpft)', wk['9100002']['id'] == hand['id'] and wk['9100002'].get('quelle') != 'winab')
kb = V.call('leergut_konto&partner=' + wk['9100001']['id'])[1]['bewegungen']
gs = [b for b in V.call('leergut_konto&partner=' + hand['id'])[1]['bewegungen'] if b['beleg'] == 'Gutschrift 600001']
off = V.call('leergut_konto&partner=' + wk['9100003']['id'])[1]['bewegungen']
check('WinAB-Buchung: Beleg mit Art, Herkunft, Schlüssel, Abgang und Zugang getrennt', len(kb) == 1 and kb[0]['beleg'] == 'Lieferschein 500001' and kb[0]['quelle'] == 'winab'
      and kb[0]['winab'] == {'kd': '9100001', 'art': 'Lieferschein', 'beleg': '500001'} and kb[0]['abgang'] == {'e2': 10, 'h1': 1} and kb[0]['zugang'] == {'e2': 4}
      and 'Lademittel_Test.XLS' in kb[0]['text'], kb)
check('WinAB: Gutschrift als Abholung, Lieferschein am Berichtsdatum „noch nicht zurück“', len(gs) == 1 and gs[0]['typ'] == 'abholung'
      and 'noch nicht zurück' in off[0]['text'] and 'noch nicht zurück' not in kb[0]['text'], (gs, off))
st, r = V.call('leergut_winab_import', WB)
check('WinAB erneut: alles unverändert, keine neuen Konten', st == 200 and r['zahlen']['gleich'] == 4 and r['zahlen']['neu'] == 0 and r['zahlen']['kunden'] == 0
      and len(V.call('leergut_start')[1]['partner']) == n_p + 4, r)
for name, b, erw in (('Zeitraum ab 01.06.: frühere Belege bleiben', wb(bericht={**WB['bericht'], 'von': '2026-06-01'}, belege=WB['belege'][4:]), {'gleich': 1, 'ausgeglichen': 0}),
                     ('nur Kunde 9100003 im Bericht: andere bleiben', wb(kunden=WB['kunden'][2:3], belege=WB['belege'][4:]), {'gleich': 1, 'ausgeglichen': 0}),
                     ('Kunde 9100001 ohne Belege im Bericht: ausgeglichen', wb(kunden=WB['kunden'][::2], belege=WB['belege'][4:]), {'gleich': 1, 'ausgeglichen': 1})):
    st, r = V.call('leergut_winab_import', {**b, 'vorschau': True})
    check(f'WinAB-Vorschau {name}', st == 200 and all(r['zahlen'][k] == n for k, n in erw.items()), r.get('zahlen'))
geaendert = wb(belege=[{**WB['belege'][0], 'abgang': {'e2': 12, 'h1': 1}}] + WB['belege'][1:3] + WB['belege'][4:])
st, r = V.call('leergut_winab_import', geaendert)
check('WinAB geändert: Beleg geändert → storniert und neu, fehlender Beleg → ausgeglichen', st == 200 and r['zahlen']['geaendert'] == 1 and r['zahlen']['ausgeglichen'] == 1
      and r['zahlen']['gleich'] == 2 and r['zahlen']['neu'] == 0, r)
kb = V.call('leergut_konto&partner=' + wk['9100001']['id'])[1]['bewegungen']
re_ = [b for b in V.call('leergut_konto&partner=' + hand['id'])[1]['bewegungen'] if b['beleg'] == 'Rechnung 700001']
check('WinAB geändert: alter Beleg storniert mit Grund, neuer gebucht, Saldo neu', len(kb) == 2 and 'Beleg geändert' in kb[0]['storno']['grund'] and kb[1]['abgang'] == {'e2': 12, 'h1': 1}
      and not kb[1]['storno'] and re_ and 'ausgeglichen' in re_[0]['storno']['grund']
      and {x['id']: x['saldo'] for x in V.call('leergut_start')[1]['konten']}[hand['id']] == {'e2': -7}, (kb, re_))

# ── Leergut bei Kunden: letzte Lieferung und Rückgabe, Abholliste ──
s = V.call('leergut_start')[1]
ko = {x['id']: x for x in s['konten']}
check('Konto: letzte Lieferung aus den Buchungen; WinAB-Buchungen ohne Angaben aus dem Bericht → letzte Rückgabe unbekannt',
      ko[wk['9100001']['id']]['letzteAbgabe'] == '2026-03-02' and ko[wk['9100001']['id']]['rueckgabeUnbekannt'] is True and ko[hand['id']]['rueckgabeUnbekannt'] is True
      and ko[namen['Beispiel-Spedition']]['rueckgabeUnbekannt'] is False, ko[wk['9100001']['id']])
WBD = wb(kunden=[{**WB['kunden'][0], 'ersteLieferung': '2026-03-02', 'letzteLieferung': '2026-03-09', 'letzteRueckgabe': '2026-03-09'},
                 {**WB['kunden'][1], 'ersteLieferung': '2026-04-02', 'letzteLieferung': '2026-04-02', 'letzteRueckgabe': '2026-04-01'},
                 {**WB['kunden'][2], 'ersteLieferung': '2026-10-15', 'letzteLieferung': '2026-10-15', 'letzteRueckgabe': ''}, WB['kunden'][3]],
         belege=geaendert['belege'])
st, r = V.call('leergut_winab_import', {**WBD, 'vorschau': True})
check('WinAB-Vorschau: Lieferung/Rückgabe laut Bericht für 3 Konten, Belege unverändert', st == 200 and r['zahlen']['daten'] == 3 and r['zahlen']['gleich'] == 3
      and r['zahlen']['neu'] == 0 and r['zahlen']['ausgeglichen'] == 0, r.get('zahlen'))
st, r = V.call('leergut_winab_import', wb(kunden=[{**WBD['kunden'][0], 'letzteRueckgabe': '2026-10-20'}] + WBD['kunden'][1:], belege=geaendert['belege'], vorschau=True))
check('WinAB: Rückgabe nach dem Berichtsdatum → 422', st == 422 and 'außerhalb' in r.get('error', ''), r)
check('WinAB: Lieferdaten übernommen', V.call('leergut_winab_import', WBD)[0] == 200)
s = V.call('leergut_start')[1]
ko = {x['id']: x for x in s['konten']}; pa = {p['id']: p for p in s['partner']}
check('Konto: Lieferung und Rückgabe laut Bericht (auch aus reinem Tausch), nicht mehr unbekannt',
      ko[wk['9100001']['id']]['letzteAbgabe'] == '2026-03-09' and ko[wk['9100001']['id']]['letzteRueckgabe'] == '2026-03-09' and ko[wk['9100001']['id']]['rueckgabeUnbekannt'] is False
      and ko[wk['9100003']['id']]['letzteRueckgabe'] == '' and ko[wk['9100003']['id']]['ersteAbgabe'] == '2026-10-15'
      and pa[wk['9100001']['id']]['winab'] == {'ersteLieferung': '2026-03-02', 'letzteLieferung': '2026-03-09', 'letzteRueckgabe': '2026-03-09', 'bis': '2026-10-15'}, pa[wk['9100001']['id']].get('winab'))
st, r = V.call('leergut_winab_import', wb(kunden=[{**WBD['kunden'][0], 'ersteLieferung': '2026-01-05', 'letzteRueckgabe': '2026-02-01'}] + WBD['kunden'][1:], belege=geaendert['belege']))
pw = {p['id']: p for p in V.call('leergut_start')[1]['partner']}[wk['9100001']['id']]['winab']
check('WinAB: älterer Bericht – früheste erste Lieferung, späteste Rückgabe bleibt', st == 200 and r['zahlen']['daten'] == 1 and pw['ersteLieferung'] == '2026-01-05' and pw['letzteRueckgabe'] == '2026-03-09', (r.get('zahlen'), pw))
st, r = V.call('leergut_winab_import', {**WBD, 'vorschau': True})
check('WinAB: derselbe Bericht noch einmal – keine geänderten Lieferdaten', st == 200 and r['zahlen']['daten'] == 0, r.get('zahlen'))

check('Abholliste: ohne Anmeldung kein Zugang, ohne Leergut-Recht 403, unbekannte Liste 422',
      N.call('leergut_export', {'liste': 'kunden'})[0] in (401, 403, 404) and O.call('leergut_export', {'liste': 'kunden'})[0] == 403
      and L.call('leergut_export', {'liste': 'kreditoren'})[0] == 422)
st, _, raw = L.call('leergut_export', {'liste': 'kunden'}, raw=True)
zeilen_csv = raw.lstrip('﻿').rstrip('\r\n').split('\r\n')
heute_api = datetime.date.fromisoformat(s['heute'])
tage = lambda iso: str((heute_api - datetime.date.fromisoformat(iso)).days)
check('Abholliste (CSV): BOM, nur Kunden mit Saldo, nach Wert, Kundennummer, Lieferung/Rückgabe, Tage ohne Rückgabe nur bei Schuld',
      st == 200 and raw.startswith('﻿') and zeilen_csv == [
          '"Kunde";"WinAB-Kd.-Nr.";"Firma";"E2-Kiste";"H1-Palette";"Wert €";"Letzte Lieferung";"Letzte Rückgabe";"Ohne Rückgabe seit (Tage)"',
          f'"Testkunde Nord GmbH (9100001)";"9100001";"Standard-Fleisch";"8";"1";"80,00";"09.03.2026";"09.03.2026";"{tage("2026-03-09")}"',
          f'"Testkunde Nord GmbH (9100003)";"9100003";"Standard-Fleisch";"3";"";"16,50";"15.10.2026";"";"{tage("2026-10-15")}"',
          '"Testkunde Süd (von Hand)";"9100002";"Standard-Fleisch";"-7";"";"-38,50";"02.04.2026";"01.04.2026";""'], zeilen_csv)

# ── WinAB-Datei „Lademittelbewegungen komplett“ (.CSV): Kunden und Lieferanten ──
# Die Oberfläche liest die Datei (siehe unten) und schickt Belege mit Wirkung; Kunden-Namen kommen aus dem Kundenstamm der
# Verwaltung, Lieferanten werden nur auf zugeordnete Konten gebucht.
storage_write('kunden', {'rev': 1, 'customers': [{'id': 'klg000000001', 'nr': '9100006', 'firma': 'Fleischerei Beispiel', 'active': True}]})
WC = {'bericht': {'datei': 'Lademittelbewegungen_Test.csv', 'von': '2026-01-01', 'bis': '2026-10-20', 'datum': '2026-10-20', 'dateiVon': '2020-05-04', 'quelle': 'csv'},
      'kunden': [{'nr': '9100006', 'ersteLieferung': '2020-05-04', 'letzteLieferung': '2026-09-01', 'letzteRueckgabe': '2026-09-01'}],
      'lieferanten': [{'nr': '2850008', 'lieferscheine': 2}, {'nr': '2250053', 'lieferscheine': 1}, {'nr': '2300099', 'lieferscheine': 3}, {'nr': '2999999', 'lieferscheine': 4}],
      'belege': [{'kd': '9100006', 'art': 'Lieferschein', 'beleg': '810001', 'datum': '2026-09-01', 'abgang': {'e2': 20}, 'zugang': {'e2': 15}},
                 {'lf': '2300099', 'art': 'Gutschrift', 'beleg': '102900', 'datum': '2026-09-02', 'abgang': {}, 'zugang': {'h1': 1}},
                 {'lf': '2850008', 'art': 'Lieferschein', 'beleg': '44001', 'datum': '2026-08-03', 'abgang': {}, 'zugang': {'e2': 20}},
                 {'lf': '2250053', 'art': 'Lieferschein', 'beleg': '44010', 'datum': '2026-08-04', 'abgang': {'e2': 7}, 'zugang': {}}]}
wc = lambda **aend: {**json.loads(json.dumps(WC)), **aend}
st, r = V.call('leergut_winab_import', {**WC, 'vorschau': True})
lz = {x['nr']: x for x in r.get('lieferanten', [])}
check('CSV-Vorschau: neues Kundenkonto mit Namen aus dem Kundenstamm der Verwaltung, zugeordneter Lieferant gebucht, andere nur gezählt',
      st == 200 and not r['fehler'] and r['zahlen']['kunden'] == 1 and r['zahlen']['neu'] == 2 and r['zahlen']['ohneKonto'] == 2
      and r['neueKunden'] == ['Fleischerei Beispiel (9100006)'], r)
check('CSV-Vorschau: Lieferanten zur Zuordnung (reiner Tausch ohne Zuordnung entfällt)', set(lz) == {'2850008', '2250053', '2300099'}
      and lz['2250053']['partner'] is None and lz['2250053']['belege'] == 1 and lz['2250053']['saldo'] == {'e2': 7}
      and lz['2850008']['partner']['name'] == 'Testlieferant WinAB' and lz['2300099']['lieferscheine'] == 3, lz)
kunde_p = next(p for p in V.call('leergut_start')[1]['partner'] if p['art'] == 'kunde')
for name, zu, text in (('auf ein Kundenkonto', {'2250053': kunde_p['id']}, 'Kundenkonto'), ('auf einen Partner mit Nummer', {'2250053': lief['id']}, 'schon die WinAB-Lieferantennummer'),
                       ('auf einen unbekannten Partner', {'2250053': 'pxxxxxxxxxxxx'}, 'nicht gefunden')):
    st, r = V.call('leergut_winab_import', wc(zuordnung=zu, vorschau=True))
    check(f'CSV: Zuordnung {name} → 422', st == 422 and text in r.get('error', ''), (st, r.get('error')))
schlecht = wc(belege=WC['belege'] + [{'kd': '9100006', 'lf': '2850008', 'art': 'Lieferschein', 'beleg': '1', 'datum': '2026-09-02', 'abgang': {'e2': 1}},
                                     {'lf': '2777777', 'art': 'Lieferschein', 'beleg': '2', 'datum': '2026-09-02', 'abgang': {'e2': 1}}], vorschau=True)
st, r = V.call('leergut_winab_import', schlecht)
check('CSV: Beleg mit Kunde und Lieferant, Lieferant nicht in der Liste → Fehler je Beleg', st == 200 and len(r['fehler']) == 2
      and 'Kunde und Lieferant' in r['fehler'][0]['text'] and 'Lieferantenliste' in r['fehler'][1]['text'], r.get('fehler'))
st, r = V.call('leergut_winab_import', wc(kunden=[{**WC['kunden'][0], 'ersteLieferung': '2019-01-01'}], vorschau=True))
check('CSV: Lieferung vor dem Beginn der Datei → 422', st == 422 and 'außerhalb des Zeitraums der Datei' in r.get('error', ''), r)
st, r = V.call('leergut_winab_import', wc(zuordnung={'2250053': 'neu'}))
check('CSV übernommen: neues Lieferantenkonto aus der Zuordnung, 3 Belege', st == 200 and r['zahlen']['lieferantenNeu'] == 1 and r['zahlen']['neu'] == 3
      and r['lieferantenNeu'] == ['Lieferant 2250053 (WinAB)'] and r['summeLieferanten'] == {'e2': -13}, r)
s = V.call('leergut_start')[1]
pz = {p.get('lieferantNr') or p.get('kundenNr'): p for p in s['partner'] if p.get('lieferantNr') or p.get('kundenNr')}
sal = {x['id']: x['saldo'] for x in s['konten']}
check('CSV: Konten und Salden – Kunde +5, Lieferant ohne Tausch −20, neues Lieferantenkonto +7 (Art Lieferant, Nummer gemerkt)',
      sal[pz['9100006']['id']] == {'e2': 5} and sal[pz['2850008']['id']] == {'e2': -20} and sal[pz['2250053']['id']] == {'e2': 7}
      and pz['2250053']['art'] == 'lieferant' and pz['2250053']['quelle'] == 'winab' and pz['9100006']['name'] == 'Fleischerei Beispiel (9100006)', pz)
kb = V.call('leergut_konto&partner=' + pz['9100006']['id'])[1]['bewegungen']
check('CSV: Kundenbeleg mit Herkunft aus der Datei, Lieferung laut WinAB auch vor dem Zeitraum',
      len(kb) == 1 and kb[0]['text'] == 'Aus WinAB („Lademittelbewegungen“, Lademittelbewegungen_Test.csv)' and kb[0]['winab'] == {'kd': '9100006', 'art': 'Lieferschein', 'beleg': '810001'}
      and pz['9100006']['winab']['ersteLieferung'] == '2020-05-04' and 'spedition' not in pz['9100006']['winab'], (kb, pz['9100006'].get('winab')))
lb = V.call('leergut_konto&partner=' + pz['2850008']['id'])[1]['bewegungen']
check('CSV: Lieferantenbeleg mit eigenem Schlüssel', [b['winab'] for b in lb if b.get('quelle') == 'winab'] == [{'lf': '2850008', 'art': 'Lieferschein', 'beleg': '44001'}], lb)
st, r = V.call('leergut_winab_import', {**WC, 'vorschau': True})
check('CSV erneut: alles unverändert, nur der nicht zugeordnete Lieferant bleibt offen', st == 200 and r['zahlen']['gleich'] == 3 and r['zahlen']['neu'] == 0 and r['zahlen']['ohneKonto'] == 1
      and {x['nr']: x['partner']['name'] for x in r['lieferanten'] if x['partner']}.get('2250053') == 'Lieferant 2250053 (WinAB)', r.get('zahlen'))
# Lieferant einem bestehenden Konto zuordnen; ganze Geschichte: Übernehmen ab dem Beginn der Datei
best_p = next(p for p in s['partner'] if p['art'] in ('lieferant', 'spedition', 'kuehlhaus') and not p.get('lieferantNr'))
alt = {'kd': '9100006', 'art': 'Lieferschein', 'beleg': '100001', 'datum': '2020-05-04', 'abgang': {'e2': 12}, 'zugang': {}}
st, r = V.call('leergut_winab_import', wc(bericht={**WC['bericht'], 'von': '2020-05-04'}, belege=WC['belege'] + [alt], zuordnung={'2300099': best_p['id']}))
bk = [b for b in V.call('leergut_konto&partner=' + best_p['id'])[1]['bewegungen'] if b.get('quelle') == 'winab']
check('CSV ab Beginn der Datei: älterer Beleg und Beleg des zugeordneten Lieferanten neu, übrige unverändert; Nummer am bestehenden Konto',
      st == 200 and r['zahlen']['neu'] == 2 and r['zahlen']['gleich'] == 3 and r['zahlen']['lieferantenNeu'] == 0
      and {p['id']: p.get('lieferantNr') for p in V.call('leergut_start')[1]['partner']}[best_p['id']] == '2300099'
      and [b['zugang'] for b in bk] == [{'h1': 1}], (r.get('zahlen'), bk))
st, r = V.call('leergut_winab_import', {**WC, 'vorschau': True})
check('CSV wieder ab 2026: der ältere Beleg liegt außerhalb und bleibt', st == 200 and r['zahlen']['ausgeglichen'] == 0 and r['zahlen']['gleich'] == 4, r.get('zahlen'))
st, _, raw = L.call('leergut_export', {'liste': 'kunden'}, raw=True)
zeile6 = next((z for z in raw.split('\r\n') if '9100006' in z), '')
check('Abholliste: Kundenkonto aus der Datei mit ganzer Geschichte (+17 E2)', '"17"' in zeile6 and zeile6.startswith('"Fleischerei Beispiel (9100006)"'), zeile6)

# ── Lieferantenstamm der Verwaltung, Wareneingang ohne Tausch, Sammelkonto mit „WinAB ab“ (Wunsch des Inhabers 06.11.2026) ──
# Erfundene Stammdaten: Name und Versandart je WinAB-Lieferant (Verwaltung → Lieferanten / Versandarten)
storage_write('versandarten', {'rev': 1, 'groups': [{'nr': '1', 'name': 'Direktlieferung'}]})
storage_write('lieferanten', {'rev': 1, 'groups': [{'nr': '2550077', 'name': 'Musterfleisch GmbH & Co. KG', 'kurz': 'MUSTER', 'versandart': '1', 'umsatzJahr': '1,00 €'},
                                                   {'nr': '2550078', 'name': '', 'kurz': 'NURKURZ', 'versandart': ''}]})
st, r = V.call('leergut_partner_save', {'name': 'Musterfleisch', 'art': 'lieferant', 'lademittel': ['e2', 'h1']})
must = r.get('partner', {})
WL = {'bericht': {'datei': 'Lademittelbewegungen_Lief.csv', 'von': '2026-01-01', 'bis': '2026-10-20', 'datum': '2026-10-20', 'dateiVon': '2025-01-02', 'quelle': 'csv'},
      'kunden': [], 'lieferanten': [{'nr': '2550077', 'lieferscheine': 3}, {'nr': '2550078', 'lieferscheine': 1}],
      'belege': [{'lf': '2550077', 'art': 'Lieferschein', 'beleg': '45001', 'datum': '2026-08-04', 'abgang': {'e2': 5, 'h1': 1}, 'zugang': {'e2': 5, 'h1': 1}},   # Tausch laut WinAB
                 {'lf': '2550077', 'art': 'Lieferschein', 'beleg': '45002', 'datum': '2026-09-05', 'abgang': {}, 'zugang': {'e2': 3}},
                 {'lf': '2550077', 'art': 'Lieferschein', 'beleg': '45003', 'datum': '2026-09-10', 'abgang': {'e2': 9}, 'zugang': {'e2': 4}},                   # 4 getauscht, 5 zurück
                 {'lf': '2550078', 'art': 'Lieferschein', 'beleg': '45010', 'datum': '2026-09-11', 'abgang': {'e2': 2}, 'zugang': {'e2': 2}}]}
wl = lambda **aend: {**json.loads(json.dumps(WL)), **aend}
st, r = V.call('leergut_winab_import', wl(vorschau=True))
lz = {x['nr']: x for x in r.get('lieferanten', [])}
check('Lieferantenstamm: Name, Versandart und Vorschlag (Konto mit passendem Namen) in der Vorschau – ohne Umsätze',
      st == 200 and lz['2550077']['name'] == 'Musterfleisch GmbH & Co. KG' and lz['2550077']['versandart'] == '1 · Direktlieferung' and lz['2550077']['vorschlag'] == must.get('id')
      and lz['2550078']['name'] == 'NURKURZ' and lz['2550078']['vorschlag'] is None and 'umsatz' not in json.dumps(r).lower(), lz)
check('Wareneingang: Tausch laut WinAB zählt nicht – Zugang bleibt (−5/−1, −3, Rückgabe +5 −4), reiner Tausch eines anderen Lieferanten −2',
      lz['2550077']['saldo'] == {'e2': -7, 'h1': -1} and lz['2550077']['belege'] == 3 and lz['2550078']['saldo'] == {'e2': -2} and r['zahlen']['tausch'] == 3, (lz, r.get('zahlen')))
st, r = V.call('leergut_winab_import', wl(zuordnung={'2550077': must['id'], '2550078': 'neu'}))
s = V.call('leergut_start')[1]
pz = {p.get('lieferantNr'): p for p in s['partner'] if p.get('lieferantNr')}
sal = {x['id']: x['saldo'] for x in s['konten']}
check('Zugeordnet: Konto „Musterfleisch“ mit Nummer, neues Konto mit Namen aus dem Stamm', st == 200 and pz['2550077']['id'] == must['id'] and pz['2550078']['name'] == 'NURKURZ (2550078)'
      and sal[must['id']] == {'e2': -7, 'h1': -1} and r['lieferantenNeu'] == ['NURKURZ (2550078)'], (r.get('zahlen'), r.get('lieferantenNeu')))
mb = [b for b in V.call('leergut_konto&partner=' + must['id'])[1]['bewegungen'] if b.get('quelle') == 'winab']
check('Buchungstext nennt den nicht gezählten Tausch', len(mb) == 3 and 'Tausch laut WinAB nicht gezählt (5 E2, 1 H1)' in mb[0]['text'] and mb[0]['abgang'] in ({}, []) and mb[0]['zugang'] == {'e2': 5, 'h1': 1}
      and mb[2]['abgang'] == {'e2': 5} and 'Tausch' not in mb[1]['text'], [(b['beleg'], b['abgang'], b['zugang'], b['text'][-80:]) for b in mb])
check('Versandart am Konto (Start): laut Lieferantenstamm', s.get('versand', {}).get(must['id']) == '1 · Direktlieferung', s.get('versand'))
# Lademittelbestand laut WinAB-Stammdaten (Zähler der Warenwirtschaft) je Konto: Lieferanten- bzw. Kundenstamm, nur zur Anzeige
storage_write('lieferanten', {'rev': 2, 'groups': [{'nr': '2550077', 'name': 'Musterfleisch GmbH & Co. KG', 'kurz': 'MUSTER', 'versandart': '1', 'lademittelbestand': '-1.234'},
                                                   {'nr': '2550078', 'name': '', 'kurz': 'NURKURZ', 'versandart': '', 'lademittelbestand': 'unlesbar'}]})
storage_write('kunden', {'rev': 2, 'customers': [{'id': 'klg000000001', 'nr': '9100006', 'firma': 'Fleischerei Beispiel', 'active': True, 'versandart': '1', 'wawi': {'lademittelbestand': 17}}]})
s = V.call('leergut_start')[1]
p6 = next(p for p in s['partner'] if p.get('kundenNr') == '9100006')
wb = s.get('winabBestand', {})
check('WinAB-Lademittelbestand je Konto: Lieferant aus dem Lieferantenstamm (-1.234), Kunde aus dem Kundenstamm, unlesbar → keiner',
      wb.get(must['id']) == [['2550077', -1234]] and wb.get(p6['id']) == [['9100006', 17]] and pz['2550078']['id'] not in wb
      and s['versand'].get(p6['id']) == '1 · Direktlieferung', (wb, s.get('versand')))
check('WinAB-Lademittelbestand: Leser sieht ihn auch (nur Anzeige, keine Umsätze)', L.call('leergut_start')[1].get('winabBestand', {}).get(must['id']) == [['2550077', -1234]])
# Konto mit „Tausch laut WinAB zählt“: der reine Tausch fällt weg, der gebuchte Beleg wird storniert
mp = next(p for p in s['partner'] if p['id'] == must['id'])
st, r = V.call('leergut_partner_save', {'id': mp['id'], 'rev': mp['rev'], 'name': mp['name'], 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'wareneingangTausch': True})
check('Partner: „Tausch laut WinAB zählt“ gespeichert', st == 200 and r['partner']['wareneingangTausch'] is True and r['partner']['lieferantNr'] == '2550077', r)
st, r = V.call('leergut_winab_import', wl())
sal = {x['id']: x['saldo'] for x in V.call('leergut_start')[1]['konten']}
check('Tausch zählt: reiner Tausch ausgeglichen (storniert), teilweiser Tausch geändert (9 ab, 4 zu: +5)', st == 200 and r['zahlen']['ausgeglichen'] == 1 and r['zahlen']['geaendert'] == 1
      and r['zahlen']['gleich'] == 2 and sal[must['id']] == {'e2': 2}, (r.get('zahlen'), sal.get(must['id'])))
mp = next(p for p in V.call('leergut_start')[1]['partner'] if p['id'] == must['id'])
V.call('leergut_partner_save', {'id': mp['id'], 'rev': mp['rev'], 'name': mp['name'], 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'wareneingangTausch': False})
# Sammelkonto: weitere Nummer ab einem Tag – Belege ab dann dort, davor beim bisherigen Konto
st, r = V.call('leergut_partner_save', {'name': 'Sammelkonto Test', 'art': 'spedition', 'lademittel': ['e2', 'h1'], 'lieferantNrWeitere': '2550077, 2550077', 'winabAb': '2026-09-01'})
sk = r.get('partner', {})
check('Sammelkonto: weitere Nummer und „WinAB ab“ gespeichert (doppelte entfällt)', st == 200 and sk.get('lieferantNrWeitere') == ['2550077'] and sk.get('winabAb') == '2026-09-01', r)
st, r = V.call('leergut_partner_save', {'name': 'Sammelkonto Doppelt', 'art': 'spedition', 'lademittel': ['e2'], 'lieferantNrWeitere': '2550077', 'winabAb': '2026-09-01'})
check('Sammelkonto: gleiche Nummer mit gleichem „WinAB ab“ → 422', st == 422 and 'Sammelkonto Test' in r.get('error', ''), r)
check('Sammelkonto: Nummer nur aus Ziffern (422)', V.call('leergut_partner_save', {'name': 'Sammelkonto X', 'art': 'spedition', 'lademittel': ['e2'], 'lieferantNrWeitere': '25-5'})[0] == 422)
st, r = V.call('leergut_winab_import', wl())
konto = lambda pid: [b['beleg'] for b in V.call('leergut_konto&partner=' + pid)[1]['bewegungen'] if b.get('quelle') == 'winab' and not b.get('storno')]
check('Sammelkonto: Belege ab 01.09. umgebucht (storniert und neu), August bleibt beim bisherigen Konto',
      st == 200 and r['zahlen']['geaendert'] == 2 and konto(sk['id']) == ['Lieferschein 45002', 'Lieferschein 45003'] and konto(must['id']) == ['Lieferschein 45001'], (r.get('zahlen'), konto(sk['id']), konto(must['id'])))
# „WinAB ab“ vor dem Zeitraum: Lieferantenbelege ab diesem Tag (z. B. Bochumer 2025), Kunden weiter ab „von“
mp = next(p for p in V.call('leergut_start')[1]['partner'] if p['id'] == must['id'])
st, r = V.call('leergut_partner_save', {'id': mp['id'], 'rev': mp['rev'], 'name': mp['name'], 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'winabAb': '2025-11-01'})
alt25 = {'lf': '2550077', 'art': 'Lieferschein', 'beleg': '44001', 'datum': '2025-11-12', 'abgang': {'e2': 7}, 'zugang': {'e2': 7}}
check('Lieferantenbeleg vor „von“ ohne „lfVon“ (ältere Oberfläche) → Fehler', V.call('leergut_winab_import', wl(belege=WL['belege'] + [alt25], vorschau=True))[1].get('fehler'))
st, r = V.call('leergut_winab_import', wl(bericht={**WL['bericht'], 'lfVon': '2025-11-01'}, belege=WL['belege'] + [alt25]))
check('Sammelkonto: WinAB-Lademittelbestand der weiteren Nummer', V.call('leergut_start')[1]['winabBestand'].get(sk['id']) == [['2550077', -1234]])
check('„WinAB ab“ 01.11.2025: Wareneingang vom 12.11.2025 gebucht', st == 200 and r['zahlen']['neu'] == 1 and konto(must['id']) == ['Lieferschein 44001', 'Lieferschein 45001'], (r.get('zahlen'), konto(must['id'])))
mp = next(p for p in V.call('leergut_start')[1]['partner'] if p['id'] == must['id'])
V.call('leergut_partner_save', {'id': mp['id'], 'rev': mp['rev'], 'name': mp['name'], 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'winabAb': '2026-08-10'})
st, r = V.call('leergut_winab_import', wl(bericht={**WL['bericht'], 'lfVon': '2025-11-01'}, belege=WL['belege'] + [alt25]))
check('„WinAB ab“ später gesetzt: ältere Belege des Kontos werden storniert und nicht mehr gebucht', st == 200 and r['zahlen']['vorStart'] == 2 and r['zahlen']['vorBeginnStorniert'] == 2
      and r['zahlen']['ausgeglichen'] == 0 and konto(must['id']) == [], (r.get('zahlen'), konto(must['id'])))
grd = [b['storno']['grund'] for b in V.call('leergut_konto&partner=' + must['id'])[1]['bewegungen'] if b.get('quelle') == 'winab' and b.get('storno')]
check('„WinAB ab“ später gesetzt: Grund der Stornierung', any('vor „WinAB-Belege ab“ des Kontos' in g for g in grd), grd)

# ── Excel-Liste und WinAB: keine doppelten Buchungen (Wunsch des Inhabers 06.11.2026, Bochumer doppelt) ──
# Bis zur letzten Excel-Buchung eines Kontos gilt die Excel-Liste: WinAB-Belege mit gleicher Menge (±3 Tage) nicht buchen,
# am selben Tag mit anderer Menge nicht buchen und zeigen, ohne Gegenstück buchen („fehlt in der Excel-Liste“); früher doppelt gebuchte stornieren.
st, r = V.call('leergut_partner_save', {'name': 'Excel-Testlieferant', 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'lieferantNr': '2660001', 'winabAb': '2025-06-01'})
xl = r.get('partner', {})
ls = lambda nr, dt, zu: {'lf': '2660001', 'art': 'Lieferschein', 'beleg': nr, 'datum': dt, 'abgang': dict(zu), 'zugang': dict(zu)}   # Tausch laut WinAB
XW = {'bericht': {'datei': 'Lademittelbewegungen_Excel.csv', 'von': '2026-01-01', 'bis': '2026-10-20', 'datum': '2026-10-20', 'dateiVon': '2025-01-02', 'lfVon': '2025-06-01', 'quelle': 'csv'},
      'kunden': [], 'lieferanten': [{'nr': '2660001', 'lieferscheine': 6}],
      'belege': [ls('41330', '2025-07-04', {'e2': 27, 'h1': 1}), ls('41356', '2025-07-09', {'e2': 32, 'h1': 1}), ls('41400', '2025-07-15', {'e2': 10}),
                 ls('41500', '2025-07-20', {'e2': 5}), ls('41600', '2025-09-01', {'e2': 7})]}
st, r = V.call('leergut_winab_import', XW)
check('Excel-Abgleich: ohne Excel-Liste alle 5 Wareneingänge gebucht (Stand vor der Bereinigung)', st == 200 and r['zahlen']['neu'] == 5 and r['zahlen']['inExcel'] == 0, r.get('zahlen'))
# Excel-Liste des Kontos (wie aus dem Datenpaket, Quelle „import“): 04.07. ohne H1, 09.07. gleich, 14.07. (WinAB 15.07.), Rückgabe 01.08.
roh = storage_raw('leergut-bewegungen')
bd = json.loads(roh.split('\n', 1)[1] if roh.startswith('<?php') else roh)
xe = lambda i, dt, typ, ab, zu, beleg: {'id': 'bxl' + i, 'partner': xl['id'], 'datum': dt, 'typ': typ, 'abgang': ab, 'zugang': zu, 'beleg': beleg, 'text': 'Excel-Zeile ' + i,
                                         'quelle': 'import', 'erfasst': {'t': '2026-10-29T08:00:00Z', 'von': 'Test', 'vonId': 'u0'}, 'storno': None}
bd['liste'] += [xe('13', '2025-07-04', 'bewegung', {}, {'e2': 27}, '126717'), xe('14', '2025-07-09', 'bewegung', {}, {'e2': 32, 'h1': 1}, '126835'),
                xe('15', '2025-07-14', 'bewegung', {}, {'e2': 10}, '126900'), xe('16', '2025-08-01', 'abholung', {'e2': 50}, {}, 'Abholung')]
bd['rev'] = bd.get('rev', 0) + 1
storage_write('leergut-bewegungen', bd)
XW2 = {**XW, 'belege': XW['belege'] + [ls('41550', '2025-07-25', {'e2': 3})]}
st, r = V.call('leergut_winab_import', {**XW2, 'vorschau': True})
zz = r.get('zahlen', {})
check('Excel-Abgleich (Vorschau): 2 schon in der Excel-Liste (09.07. gleich, 15.07. ±1 Tag), 1 abweichend (04.07. ohne H1), 2 fehlen, 3 doppelte werden storniert',
      st == 200 and zz.get('inExcel') == 2 and zz.get('abweichend') == 1 and zz.get('nurWinab') == 2 and zz.get('doppeltStorniert') == 3 and zz.get('neu') == 1 and zz.get('gleich') == 2, zz)
ab = r.get('abweichend') or [{}]
check('Excel-Abgleich (Vorschau): abweichender Beleg mit beiden Mengen und Excel-Beleg', len(r.get('abweichend', [])) == 1 and ab[0].get('beleg') == 'Lieferschein 41330'
      and ab[0].get('winab') == {'e2': -27, 'h1': -1} and ab[0].get('excel') == {'e2': -27} and ab[0].get('excelBeleg') == '126717' and ab[0].get('name') == 'Excel-Testlieferant', ab)
st, r = V.call('leergut_winab_import', XW2)
kb = V.call('leergut_konto&partner=' + xl['id'])[1]['bewegungen']
aktiv = {b['beleg']: b for b in kb if b.get('quelle') == 'winab' and not b.get('storno')}
weg = {b['beleg']: b['storno']['grund'] for b in kb if b.get('quelle') == 'winab' and b.get('storno')}
sal = {x['id']: x['saldo'] for x in V.call('leergut_start')[1]['konten']}
check('Excel-Abgleich: doppelte storniert mit Grund, fehlende und spätere gebucht', st == 200 and set(aktiv) == {'Lieferschein 41500', 'Lieferschein 41550', 'Lieferschein 41600'}
      and 'steht schon in der Excel-Liste' in weg.get('Lieferschein 41356', '') and 'weicht von der Excel-Liste ab' in weg.get('Lieferschein 41330', '')
      and 'steht schon in der Excel-Liste' in weg.get('Lieferschein 41400', ''), (sorted(aktiv), weg))
check('Excel-Abgleich: Text „fehlt in der Excel-Liste“ nur im Excel-Zeitraum', 'fehlt in der Excel-Liste' in aktiv['Lieferschein 41550']['text'] and 'fehlt in der Excel-Liste' not in aktiv['Lieferschein 41600']['text'])
check('Excel-Abgleich: Saldo = Excel-Liste + fehlende + spätere WinAB-Belege (E2 −27 −32 −10 +50 −5 −3 −7 = −34, H1 −1)', sal.get(xl['id']) == {'e2': -34, 'h1': -1}, sal.get(xl['id']))
check('Excel-Abgleich: Excel-Buchungen bleiben unverändert', sum(1 for b in kb if b.get('quelle') == 'import' and not b.get('storno')) == 4)
st, r = V.call('leergut_winab_import', XW2)
zz = r.get('zahlen', {})
check('Excel-Abgleich: erneut dieselbe Datei – nichts mehr zu tun', st == 200 and zz.get('doppeltStorniert') == 0 and zz.get('neu') == 0 and zz.get('ausgeglichen') == 0 and zz.get('gleich') == 3 and zz.get('inExcel') == 2, zz)
check('Protokoll: Abgleich nennt die Excel-Liste', 'schon in der Excel-Liste (0 doppelte storniert)' in json.dumps(A.call('log')[1], ensure_ascii=False))
# Ohne eigenes „WinAB-Belege ab“: WinAB zählt erst nach der letzten Buchung der Excel-Liste (01.08.2025) – frühere WinAB-Buchungen werden storniert
xp = next(p for p in V.call('leergut_start')[1]['partner'] if p['id'] == xl['id'])
V.call('leergut_partner_save', {'id': xp['id'], 'rev': xp['rev'], 'name': xp['name'], 'art': 'lieferant', 'lademittel': ['e2', 'h1'], 'winabAb': ''})
st, r = V.call('leergut_winab_import', XW2)
zz = r.get('zahlen', {})
kb = V.call('leergut_konto&partner=' + xl['id'])[1]['bewegungen']
aktiv = sorted(b['beleg'] for b in kb if b.get('quelle') == 'winab' and not b.get('storno'))
sal = {x['id']: x['saldo'] for x in V.call('leergut_start')[1]['konten']}
check('Excel-Konto ohne „WinAB ab“: Belege bis zum Ende der Excel-Liste storniert (Grund), nur der spätere bleibt, Excel unverändert',
      st == 200 and zz.get('vorBeginnStorniert') == 2 and zz.get('vorStart') == 5 and aktiv == ['Lieferschein 41600'] and sal.get(xl['id']) == {'e2': -26, 'h1': -1}
      and any('vor dem Ende der Excel-Liste' in (b.get('storno') or {}).get('grund', '') for b in kb)
      and sum(1 for b in kb if b.get('quelle') == 'import' and not b.get('storno')) == 4, (zz, aktiv, sal.get(xl['id'])))
# Konto ohne Excel-Liste und ohne „WinAB ab“: ältere Buchungen vor „Übernehmen ab“ bleiben – nur mit „aeltereStornieren“ storniert
st, r = V.call('leergut_partner_save', {'name': 'Altlieferant Test', 'art': 'lieferant', 'lademittel': ['e2'], 'lieferantNr': '2660002', 'winabAb': '2025-03-01'})
al = r.get('partner', {})
AW = {'bericht': {**XW['bericht'], 'lfVon': '2025-01-02'}, 'kunden': [], 'lieferanten': [{'nr': '2660002', 'lieferscheine': 2}],
      'belege': [{**ls('47001', '2025-03-10', {'e2': 4}), 'lf': '2660002'}, {**ls('47002', '2026-02-10', {'e2': 6}), 'lf': '2660002'}]}
V.call('leergut_winab_import', AW)
ap = next(p for p in V.call('leergut_start')[1]['partner'] if p['id'] == al['id'])
V.call('leergut_partner_save', {'id': ap['id'], 'rev': ap['rev'], 'name': ap['name'], 'art': 'lieferant', 'lademittel': ['e2'], 'winabAb': ''})
st, r = V.call('leergut_winab_import', AW)
ak = lambda: sorted(b['beleg'] for b in V.call('leergut_konto&partner=' + al['id'])[1]['bewegungen'] if b.get('quelle') == 'winab' and not b.get('storno'))
check('Ohne Excel und „WinAB ab“: Buchung vor „Übernehmen ab“ bleibt ohne Option (nicht ausgeglichen)', st == 200 and r['zahlen']['vorBeginnStorniert'] == 0 and r['zahlen']['ausgeglichen'] == 0
      and ak() == ['Lieferschein 47001', 'Lieferschein 47002'], (r.get('zahlen'), ak()))
st, r = V.call('leergut_winab_import', {**AW, 'bericht': {**AW['bericht'], 'aeltereStornieren': True}, 'vorschau': True})
check('„Ältere stornieren“ (Vorschau): zählt die Buchung, schreibt nichts', st == 200 and r['zahlen']['vorBeginnStorniert'] >= 1 and ak() == ['Lieferschein 47001', 'Lieferschein 47002'], r.get('zahlen'))
st, r = V.call('leergut_winab_import', {**AW, 'bericht': {**AW['bericht'], 'aeltereStornieren': True}})
check('„Ältere stornieren“: Buchung vor „Übernehmen ab“ storniert, spätere bleibt', st == 200 and r['zahlen']['vorBeginnStorniert'] >= 1 and ak() == ['Lieferschein 47002'], (r.get('zahlen'), ak()))

# ── Dachser-Liste „Unterkonto-Vorspediteur“ (Mail „Infos von Fa. DACHSER“) ──
# Erfundene Liste im Aufbau der Dachser-Mail: Seitenkopf mit Anschrift, je Fall drei Zeilen, Saldo „zu Gunsten DA“.
def dachser_liste(faelle, per='31.10.26', saldo=None, seiten=2):
    kopf = lambda s: [f'\f      Unterkonto-Vorspediteur          404/09999999      UK                     Seite:   {s}',
                      f'      per   {per}     Letzter Abschluss: 30.09.2026                          14.11.2026', '',
                      '                                                       DACHSER SE', '         TESTKUNDE GMBH', '         TESTSTR. 1', '',
                      '         20000 TESTSTADT', '', '      ' + '-' * 84, '      Auft.Dat  Absender                                                SendungsNr.',
                      '                Empfänger', '      Zust.Dat  Anz   PM  Grund', '      ' + '-' * 84]
    z = kopf(1)
    for i, (auf, nr, name, ort, zug, anz, pm, kz, sendung) in enumerate(faelle):
        if seiten > 1 and i == len(faelle) // 2:
            z += kopf(2)
        z += [f'      {auf:>8}  09999999  TESTKUNDE GMBH        TESTSTADT', f'                {nr}  {name:<20}  {ort}', '',
              f'      {zug:>8}  {anz:>5} {pm}  {kz}  Abschreibung lt. Empfänger                 {sendung}', '      ' + '-' * 84]
    if saldo is not None:
        z += ['', f'      Unterkonto Saldo per {per[:6]}20{per[6:]}             - - -  Einzeldarstellung  - - -',
              '                                                   Einweg Schrott K-Eigen   Sonst']
        z += [f'      {pm:<2}   {n:>4}   zu Gunsten DA 404                                           {n:>5}' for pm, n in saldo.items()]
        z += ['', '      Dieser Saldo wird von uns auf Ihr Packmittelkonto 09999999 umgebucht.']
    return '\n'.join(z) + '\n'


def als_mail(text):
    """Gespeicherte Mail (.eml) wie vom Dachser-Mailprogramm: quoted-printable, ISO-8859-1, umgebrochene Zeilen."""
    import quopri
    rumpf = quopri.encodestring(text.replace('\n', '\r\n').encode('iso-8859-1')).decode('ascii')
    return ('From: <packmittel@example.invalid>\r\nSubject: Infos von Fa. DACHSER\r\nMIME-Version: 1.0\r\nContent-Type: text/plain;\r\n charset="iso-8859-1"\r\n'
            'Content-Transfer-Encoding: quoted-printable\r\n\r\n' + rumpf)


DF = [('2.10.26', '09900001', 'TESTMARKT NORD GMBH', 'MUSTERSTADT', '3.10.26', 12, 'E2', 'R', '09900000001'),
      ('2.10.26', '09900001', 'TESTMARKT NORD GMBH', 'MUSTERSTADT', '3.10.26', 2, 'H1', 'R', '09900000001'),
      ('5.10.26', '09900002', 'REWE TESTMARKT OHG', 'TESTHAUSEN', '6.10.26', 1, 'H1', 'R', '09900000002'),
      ('6.10.26', '09900003', 'FLEISCHEREI PROBE', 'BEISPIELORT', '7.10.26', 4, 'E2', 'K', '09900000003'),
      ('6.10.26', '09900003', 'FLEISCHEREI PROBE', 'BEISPIELORT', '7.10.26', 4, 'E2', 'K', '09900000003'),
      ('8.10.26', '09900004', 'GITTER UND CO', 'ORT', '9.10.26', 2, 'GB', 'R', '09900000004'),
      ('9.10.26', '09900005', 'BÄCKEREI MÜLLER', 'KÖLN', '10.10.26', 1, 'E2', 'R', '09900000005'),
      ('7.04.26', '46600001', 'BEISPIEL-SCHLACHTEREI', 'MUSTERDORF', '8.04.26', 72, 'E2', 'R', '04606394990')]
DL = dachser_liste(DF, saldo={'E2': 93, 'H1': 3, 'GB': 2})
abschr = lambda: Bb.call('leergut_start')[1]['abschreibungen']
nach_sendung = lambda: {d['sendung']: d for d in abschr()}
check('Dachser-Liste: nur ansehen 403, ohne Anmeldung kein Zugang', L.call('leergut_dachser_import', {'text': DL, 'vorschau': True})[0] == 403
      and N.call('leergut_dachser_import', {'text': DL, 'vorschau': True})[0] in (401, 403, 404))
check('Dachser-Liste: leerer Text 422, Text ohne Liste 422', Bb.call('leergut_dachser_import', {'text': '  ', 'vorschau': True})[0] == 422
      and 'keine Dachser-Liste' in Bb.call('leergut_dachser_import', {'text': 'Hallo, anbei die Liste.', 'vorschau': True})[1].get('error', ''))
n_d = len(abschr())
st, r = Bb.call('leergut_dachser_import', {'text': DL, 'vorschau': True})
z = r.get('zahlen', {})
check('Dachser-Vorschau: Zeilen, Sendungen, neu, schon erfasst, REWE nur H1, mehrfach, unbekanntes Packmittel, Summe = Saldo laut Dachser',
      st == 200 and r['per'] == '2026-10-31' and r['konto'] == '404/09999999' and z == {'zeilen': 7, 'sendungen': 5, 'neu': 4, 'ergaenzt': 0, 'schon': 1, 'abweichend': 0, 'ignoriert': 1, 'doppelt': 1}
      and r['summe'] == {'e2': 93, 'h1': 3} and r['saldo'] == {'e2': 93, 'h1': 3} and r['unbekannt'] == {'GB': 1}
      and r['doppelt'] == [{'sendung': '09900000003', 'empfaenger': 'Fleischerei Probe', 'lm': 'e2'}] and r['text'] is None, r)
check('Dachser-Vorschau schreibt nichts', len(abschr()) == n_d)
st, r = Bb.call('leergut_dachser_import', {'text': DL})
ns = nach_sendung()
d1, d2, d3, d5 = (ns.get(f'0990000000{i}', {}) for i in (1, 2, 3, 5))
check('Dachser übernommen: je Sendung ein Fall mit allen Lademitteln, Felder aus der Liste, Herkunft und Verlauf',
      st == 200 and r['zahlen']['neu'] == 4 and len(abschr()) == n_d + 4 and d1.get('menge') == {'e2': 12, 'h1': 2} and d1['empfaenger'] == 'Testmarkt Nord Gmbh'
      and d1['empfaengerNr'] == '09900001' and d1['ort'] == 'Musterstadt' and d1['auftrag'] == '2026-10-02' and d1['zugestellt'] == '2026-10-03'
      and d1['grund'] == 'Abschreibung lt. Empfänger (Kz. R)' and d1['status'] == 'offen' and d1['quelle'] == 'dachser'
      and 'Dachser-Liste per 31.10.2026' in d1['verlauf'][0]['was'] and d1['erfasst']['von'] == 'Bea Buchen', d1)
check('Dachser: REWE nur mit H1 → „Nicht zu beachten“, mehrfach genannte Menge addiert, Umlaute', d2.get('status') == 'ignoriert' and 'REWE' in d2.get('notiz', '')
      and d3.get('menge') == {'e2': 8} and d3['grund'].endswith('(Kz. K)') and d5.get('empfaenger') == 'Bäckerei Müller' and d5['ort'] == 'Köln'
      and '09900000004' not in ns and ns['04606394990']['menge'] == {'e2': 72, 'h1': 2}, (d2, d3, d5))
st, r = Bb.call('leergut_dachser_import', {'text': DL, 'vorschau': True})
check('Dachser: dieselbe Liste noch einmal – alles schon erfasst', st == 200 and r['zahlen']['neu'] == 0 and r['zahlen']['schon'] == 5 and r['zahlen']['ergaenzt'] == 0, r.get('zahlen'))
st, r = Bb.call('leergut_dachser_import', {'text': als_mail(DL), 'vorschau': True})
check('Dachser: gespeicherte Mail (.eml, quoted-printable, ISO-8859-1) – lesbarer Text zurück', st == 200 and r['zahlen']['schon'] == 5 and r['zahlen']['neu'] == 0
      and 'Unterkonto-Vorspediteur' in (r.get('text') or '') and 'BÄCKEREI MÜLLER' in r['text'] and 'Content-Transfer-Encoding' not in r['text'], r.get('zahlen'))
DL2 = dachser_liste([('6.10.26', '09900003', 'FLEISCHEREI PROBE', 'BEISPIELORT', '7.10.26', 1, 'H1', 'K', '09900000003'),
                     ('2.10.26', '09900001', 'TESTMARKT NORD GMBH', 'MUSTERSTADT', '3.10.26', 10, 'E2', 'R', '09900000001'),
                     ('5.10.26', '09900002', 'REWE TESTMARKT OHG', 'TESTHAUSEN', '6.10.26', 3, 'E2', 'R', '09900000002')], per='30.11.26', seiten=1)
st, r = Bb.call('leergut_dachser_import', {'text': DL2})
ns = nach_sendung(); neu2 = [d for d in abschr() if d['sendung'] == '09900000002']
check('Dachser: fehlendes Lademittel eines offenen Falls ergänzt, andere Menge nur gemeldet, abgeschlossener Fall → neuer Fall',
      st == 200 and r['zahlen'] == {'zeilen': 3, 'sendungen': 3, 'neu': 1, 'ergaenzt': 1, 'schon': 0, 'abweichend': 1, 'ignoriert': 0, 'doppelt': 0}
      and r['abweichend'] == [{'sendung': '09900000001', 'empfaenger': 'Testmarkt Nord Gmbh', 'lm': 'e2', 'erfasst': 12, 'dachser': 10}]
      and ns['09900000003']['menge'] == {'e2': 8, 'h1': 1} and 'ergänzt: H1 1' in ns['09900000003']['verlauf'][-1]['was'] and ns['09900000001']['menge'] == {'e2': 12, 'h1': 2}
      and len(neu2) == 2 and {d['status'] for d in neu2} == {'ignoriert', 'offen'} and [d['menge'] for d in neu2 if d['status'] == 'offen'] == [{'e2': 3}], (r.get('zahlen'), neu2))
kaputt = DL2.replace('      7.10.26      1 H1', '     31.02.26      1 H1')
st, r = Bb.call('leergut_dachser_import', {'text': kaputt, 'vorschau': True})
st2, r2 = Bb.call('leergut_dachser_import', {'text': kaputt})
check('Dachser: unlesbares Datum → Fehler mit Zeile, Übernehmen 422', st == 200 and len(r['fehler']) == 1 and 'Zustelldatum' in r['fehler'][0]['text'] and st2 == 422, (r, st2))

# Sehr lange Zeilen gehen nicht mehr durch die Zeilen-Regexe: die Fallzeile „… (.+?)\s+(\d{8,14})\s*$“ brauchte dafür
# quadratisch viel Rechenzeit (isoliert gemessen 15 s bei 100 KB, 79 s bei 200 KB; bei den zugelassenen 2 MB etwa eine
# halbe Stunde) und hielt dabei einen PHP-Prozess des gemeinsamen Mitarbeiter-Containers fest – preg_match läuft in C
# und wird von max_execution_time nicht unterbrochen. Geprüft wird nicht mit einer Wartezeit, sondern an der Antwortzeit.
DL3 = dachser_liste([('2.10.26', '09900001', 'TESTMARKT NORD GMBH', 'MUSTERSTADT', '3.10.26', 12, 'E2', 'R', '09900000001')], per='31.12.26', seiten=1)
lang_harmlos = '      Hinweis: ' + 'ein sehr langer Absatz ohne Fall ' * 3000          # kein Fall: wird wie jede andere Zeile übergangen
lang_fall = '      3.10.26     12 E2  R  ' + 'A' * 100000 + ' ' * 100000             # Fallzeile ohne Sendungsnummer: der teure Fall
vorher = len(abschr())
st, r = Bb.call('leergut_dachser_import', {'text': DL3 + lang_harmlos + '\n', 'vorschau': True})
check('Dachser: langer Absatz ohne Fall blockiert den Import nicht, echte Fallzeile weiter erkannt',
      st == 200 and not r.get('fehler') and r['zahlen']['zeilen'] == 1 and r['zahlen']['schon'] == 1, r)
t0 = time.monotonic()
st, r = Bb.call('leergut_dachser_import', {'text': DL3 + lang_fall + '\n', 'vorschau': True})
dauer = time.monotonic() - t0
check('Dachser: überlange Fallzeile wird nicht geparst – Fehler „Zeile zu lang“ mit Zeilennummer, Antwort in Sekunden',
      st == 200 and dauer < 10 and [f['text'] for f in r.get('fehler', [])] == ['Zeile zu lang (höchstens 300 Zeichen)']
      and r['fehler'][0]['zeile'] == len(DL3.split('\n')), (st, round(dauer, 2), r))
st, r = Bb.call('leergut_dachser_import', {'text': DL3 + lang_fall + '\n'})
check('Dachser: überlange Fallzeile beim Übernehmen 422, nichts gespeichert', st == 422 and len(abschr()) == vorher, (st, vorher, len(abschr())))

# ── Protokoll ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Buchung, Storno, Abstimmung, Export, Datenpaket, WinAB', all(t in log for t in ('Leergut: Bewegung gebucht – Test-Spedition Nord', 'Leergut: Bewegung storniert',
      'Leergut: Abstimmung Test-Spedition Nord zum 2026-01-31 gespeichert (Widersprochen)', 'Leergut: Bilanz zum 2026-02-28 als CSV', 'Leergut: Datenpaket übernommen (vorhandene Daten ersetzt)',
      'Leergut: WinAB-Lademittelbewegungen 2026-01-01 bis 2026-10-15 abgeglichen – 2 neue Kundenkonten, 4 neue Belege',
      'Leergut: WinAB-Lademittelbewegungen 2026-01-01 bis 2026-10-20 abgeglichen – 1 neues Kundenkonto, 1 neues Lieferantenkonto, 3 neue Belege',
      'Leergut: Leergut bei Kunden als CSV heruntergeladen (3 Kunden)',
      'Leergut: Dachser-Liste per 2026-10-31 eingelesen – 4 neue Abschreibungen, 0 ergänzt, 1 schon erfasst, 0 abweichend')))
check('Protokoll ohne Notizen, Belegnummern und Kundennamen', 'LS-1001' not in log and 'nicht verbucht' not in log and '500001' not in log and 'Testkunde Nord' not in log)


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
    check('Bewegung: alle aktiven Lademittel zeigen (ohne Karton), Eingaben bleiben', pg.locator('#bw-mengen tr').count() == len([x for x in s['lademittel'] if x['aktiv']]) and pg.input_value('#bw-mengen [data-seite="a"][data-lm="e2"]') == '1.200')
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

    # Dachser-Liste einlesen: gespeicherte Mail wählen → lesbarer Text, Vorschau, übernehmen
    eml = os.path.join(tempfile.mkdtemp(), 'Infos von Fa. DACHSER.eml')
    with open(eml, 'w', encoding='ascii', newline='') as f:
        f.write(als_mail(dachser_liste([('20.10.26', '09900011', 'UI-MARKT SÜD', 'TESTSTADT', '21.10.26', 6, 'E2', 'R', '09900000011'),
                                        ('20.10.26', '09900011', 'UI-MARKT SÜD', 'TESTSTADT', '21.10.26', 1, 'H1', 'R', '09900000011'),
                                        ('22.10.26', '09900012', 'UI-FLEISCHEREI', 'MUSTERHAUSEN', '23.10.26', 3, 'E2', 'E', '09900000012')], saldo={'E2': 9, 'H1': 1})))
    pg.click('#lg-d-dachser'); pg.wait_for_selector('#dlg-dachser[open]')
    pg.click('#dl-pruefen')
    check('Dachser-Dialog: ohne Text Hinweis', 'einfügen' in text(pg, '#dl-meldung') and pg.is_disabled('#dl-uebernehmen'))
    pg.set_input_files('#dl-datei', eml)
    pg.wait_for_selector('#dl-vorschau .lg-vorschau')
    vor = text(pg, '#dl-vorschau')
    check('Dachser-Dialog: Mail gelesen (lesbarer Text), Vorschau mit neuen Fällen und Saldo-Abgleich',
          'Unterkonto-Vorspediteur' in pg.input_value('#dl-text') and 'quoted-printable' not in pg.input_value('#dl-text') and 'UI-MARKT SÜD' in pg.input_value('#dl-text')
          and pg.inner_text('#dl-vorschau [data-z="neu"] b') == '2' and pg.inner_text('#dl-vorschau [data-z="zeilen"] b') == '3'
          and 'stimmt mit dem Saldo laut Dachser überein' in vor and pg.is_enabled('#dl-uebernehmen'), vor)
    pg.screenshot(path=os.path.join(SH, 'leergut_dachser_1280.png'))
    pg.fill('#dl-text', pg.input_value('#dl-text') + ' ')
    check('Dachser-Dialog: Text geändert → erst wieder prüfen', pg.is_disabled('#dl-uebernehmen') and not text(pg, '#dl-vorschau'))
    pg.click('#dl-pruefen'); pg.wait_for_selector('#dl-uebernehmen:not([disabled])')
    pg.click('#dl-uebernehmen'); zu(pg, '#dlg-dachser')
    pg.wait_for_function("(document.querySelector('#lg-d-liste')?.textContent || '').includes('Ui-Markt Süd')")
    neu_d = [d for d in V.call('leergut_start')[1]['abschreibungen'] if d['sendung'] in ('09900000011', '09900000012')]
    check('Oberfläche: Dachser-Liste übernommen (2 Fälle, E2 und H1 in einem Fall)', len(neu_d) == 2 and {tuple(sorted(d['menge'].items())) for d in neu_d} == {(('e2', 6), ('h1', 1)), (('e2', 3),)}, neu_d)

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
    check('Partner: Felder für Sammelkonto, „WinAB-Belege ab“ und Tausch beim Wareneingang (aus)', pg.input_value('#pa-lfweitere') == '' and pg.input_value('#pa-winab-ab') == '' and not pg.is_checked('#pa-tausch'))
    pg.fill('#pa-email', 'ui@example.invalid'); pg.fill('#pa-lfnr', '2300004'); pg.fill('#pa-lfweitere', '2550091; 2550092'); pg.fill('#pa-winab-ab', '2021-01-01')
    pg.click('#pa-form [type="submit"]'); zu(pg, '#dlg-partner')
    pa = [x for x in V.call('leergut_start')[1]['partner'] if x['name'] == 'UI-Kühlhaus']
    check('Oberfläche: Partner angelegt (mit WinAB-Lieferantennummer, weiteren Nummern und „WinAB-Belege ab“)', len(pa) == 1 and pa[0]['art'] == 'kuehlhaus' and pa[0]['fristTage'] == 14 and pa[0]['lademittel'] == ['e2', 'h1']
          and pa[0]['lieferantNr'] == '2300004' and pa[0]['lieferantNrWeitere'] == ['2550091', '2550092'] and pa[0]['winabAb'] == '2021-01-01' and pa[0]['wareneingangTausch'] is False, pa)
    pg.wait_for_function("(document.querySelector('#lg-e-partner')?.textContent || '').includes('UI-Kühlhaus')")
    check('Partnerliste zeigt die WinAB-Lieferantennummer', 'WinAB-Lief. 2300004' in text(pg, '#lg-e-partner'))
    check('Lademittel: WinAB-Nr. und Kurzbezeichnung je Zeile (WK2-Kiste 7, Karton 5 inaktiv)',
          pg.input_value('#lg-e-lm tr[data-id="wk2"] [data-f="winabNr"]') == '7' and pg.input_value('#lg-e-lm tr[data-id="wk2"] [data-f="kurz"]') == 'WK2'
          and pg.input_value('#lg-e-lm tr[data-id="karton"] [data-f="winabNr"]') == '5' and not pg.is_checked('#lg-e-lm tr[data-id="karton"] [data-f="aktiv"]'))
    pg.screenshot(path=os.path.join(SH, 'leergut_einstellungen_1280.png'), full_page=True)
    pg.fill('#lg-e-lm tr[data-id="e2"] [data-f="wert"]', '6,25'); pg.click('#lg-e-lm-form [type="submit"]')
    from umgebung import until as _until   # gespeicherten Stand abwarten (das Feld zeigt den Wert schon vor dem Speichern)
    check('Oberfläche: Wert E2 geändert (6,25 €)', _until(lambda: V.call('leergut_start')[1]['lademittel'][0]['wert'] == 6.25, timeout=10))
    pg.set_input_files('#lg-e-datei', PAKET_DATEI)
    pg.wait_for_selector('#lg-e-import-knoepfe:not([hidden])')
    vor = text(pg, '#lg-e-vorschau')
    check('Datenpaket: Vorschau mit Zahlen, „ersetzen“ nötig (Modul nicht leer)', str(len(PAKET['bewegungen'])) in vor and pg.is_visible('#lg-e-ersetzen-zeile') and pg.is_disabled('#lg-e-uebernehmen'), vor)
    pg.check('#lg-e-ersetzen'); pg.click('#lg-e-uebernehmen')
    pg.wait_for_selector('#lg-tabs [data-tab="uebersicht"][aria-selected="true"]')
    nach = V.call('leergut_start')[1]
    check('Oberfläche: Datenpaket übernommen (UI-Daten ersetzt)', {x['name'] for x in nach['partner']} == {x['name'] for x in PAKET['partner']} and nach['lademittel'][0]['wert'] == 5.5)
    SP = {x['name']: x['id'] for x in nach['partner']}['Beispiel-Spedition']   # neue Kennungen nach dem Ersetzen

    # WinAB-Bericht (.XLS) – liest der Browser, abgleichen macht der Server
    xls = os.path.join(tempfile.mkdtemp(), 'Lademittel_Test.XLS')
    with open(xls, 'wb') as f:
        f.write(winab_xls())
    n_p = len(nach['partner'])
    pg.click('#lg-tabs [data-tab="einstellungen"]')
    check('Einstellungen: ohne WinAB-Kunden kein Schalter dafür', pg.is_hidden('#lg-e-kunden-zeile'))
    pg.set_input_files('#lg-w-datei', xls)
    pg.wait_for_selector('#lg-w-knoepfe:not([hidden])')
    vor = text(pg, '#lg-w-vorschau')
    kachel = lambda k: pg.inner_text(f'#lg-w-vorschau [data-z="{k}"] b')
    check('WinAB-Vorschau: 4 Kunden im Bericht, 4 Belege mit Wirkung, 3 neue Konten, 4 neue Belege', [kachel(k) for k in ('kunden', 'belege', 'neuKd', 'neu', 'gleich')] == ['4', '4', '3', '4', '0'], vor)
    check('WinAB-Vorschau: Zeitraum bis Berichtsdatum, weggelassen (Sammelrechnung, Karton, Offerte, nur Tausch), Saldo, Gesamtwert nur zur Information',
          'Zeitraum 01.01.2026 bis 15.10.2026' in vor and '1 Zeile aus Sammelrechnungen' in vor and '1 Kartonzeile,' in vor and '1 × Offerte' in vor
          and '2 Belege ohne Wirkung' in vor and '(3 mit Saldo)' in vor and 'E2 Kisten −12 · Karton +348' in vor, vor)
    check('WinAB-Vorschau schreibt nichts', len(V.call('leergut_start')[1]['partner']) == n_p)
    pg.screenshot(path=os.path.join(SH, 'leergut_winab_1280.png'), full_page=True)
    # Kundenstamm der Verwaltung mit Versandart und Lademittelbestand laut WinAB (Anzeige im Kontokopf)
    storage_write('kunden', {'rev': 3, 'customers': [{'id': 'klg000000001', 'nr': '9100006', 'firma': 'Fleischerei Beispiel', 'active': True},
                                                     {'id': 'klg000000002', 'nr': '9100003', 'firma': 'Testkunde Nord GmbH', 'active': True, 'versandart': '1', 'wawi': {'lademittelbestand': -6}}]})
    pg.click('#lg-w-uebernehmen')
    pg.wait_for_function("(document.querySelector('#lg-w-meldung')?.textContent || '').startsWith('Übernommen')")
    check('WinAB aus der Oberfläche übernommen', 'Übernommen: 3 neue Kundenkonten, 4 neue Belege, 0 geändert, 0 ausgeglichen.' in text(pg, '#lg-w-meldung'), text(pg, '#lg-w-meldung'))
    s = V.call('leergut_start')[1]
    wk = {p['kundenNr']: p for p in s['partner'] if p.get('kundenNr')}
    salden = {x['id']: x['saldo'] for x in s['konten']}
    check('Oberfläche: WinAB-Salden wie aus dem Bericht berechnet', {k: salden[p['id']] for k, p in wk.items()} == {'9100001': {'e2': 6, 'h1': 1}, '9100002': {'e2': -5}, '9100003': {'e2': 3}}
          and wk['9100002']['name'] == 'Testkunde Süd (9100002)', wk)
    pg.wait_for_selector('#lg-e-kunden-zeile:not([hidden])')
    check('Einstellungen: WinAB-Kunden zunächst ausgeblendet, Schalter mit Anzahl', 'Testkunde' not in text(pg, '#lg-e-partner') and '(3)' in text(pg, '#lg-e-kunden-zeile'))
    pg.check('#lg-e-kunden')
    check('Einstellungen: WinAB-Kunden einblenden, mit Kundennummer', 'Testkunde Nord GmbH (9100003)' in text(pg, '#lg-e-partner') and 'WinAB-Kd. 9100003' in text(pg, '#lg-e-partner'))
    pg.set_input_files('#lg-w-datei', xls)
    pg.wait_for_function("(document.querySelector('#lg-w-meldung')?.textContent || '').includes('nichts Neues')")
    check('WinAB derselbe Bericht noch einmal: nichts Neues, kein Übernehmen-Knopf', pg.is_hidden('#lg-w-knoepfe') and kachel('gleich') == '4')
    kaputt = os.path.join(os.path.dirname(xls), 'falsch.XLS')
    with open(kaputt, 'wb') as f:
        f.write(winab_xls(titel='Lademittelbewegungen Lieferanten'))
    pg.set_input_files('#lg-w-datei', kaputt)
    pg.wait_for_function("(document.querySelector('#lg-w-meldung')?.textContent || '').includes('nicht der WinAB-Bericht')")
    check('WinAB: falscher Bericht wird erkannt', pg.is_hidden('#lg-w-knoepfe') and not text(pg, '#lg-w-vorschau'))
    pg.click('#lg-tabs [data-tab="uebersicht"]')
    zeile = text(pg, '#lg-u-salden tr[data-kunden]')
    check('Übersicht: Kunden aus WinAB in einer Zeile mit Summe', 'Kunden aus WinAB' in zeile and '3 von 3 Kundenkonten mit Saldo' in zeile and '+4' in zeile
          and 'Testkunde' not in text(pg, '#lg-u-salden'), zeile)
    # Leergut bei Kunden (Übersicht): nach Wert, Lieferung/Rückgabe laut Bericht, Ampel, Abholliste
    heute_d = datetime.date.fromisoformat(HEUTE)
    t1, t3 = (heute_d - datetime.date(2026, 3, 9)).days, (heute_d - datetime.date(2026, 10, 15)).days
    ampel = lambda t: 'rot' if t >= 60 else 'gelb' if t >= 30 else 'gruen'
    reihen = pg.locator('#lg-u-kunden tbody tr')
    namen_k = [reihen.nth(i).locator('.lg-name').inner_text() for i in range(reihen.count())]
    check('Leergut bei Kunden: alle Kundenkonten mit Saldo, nach Wert', namen_k == ['Testkunde Nord GmbH (9100001)', 'Testkunde Nord GmbH (9100003)', 'Testkunde Süd (9100002)'], namen_k)
    r1, r2, r3 = (text(pg, f'#lg-u-kunden tbody tr:nth-child({i})') for i in (1, 2, 3))
    check('Leergut bei Kunden: letzte Rückgabe laut Bericht (auch aus reinem Tausch) mit Ampel', '69,00 €' in r1 and '09.03.2026' in r1 and f'seit {t1} Tagen' in r1
          and pg.locator(f'#lg-u-kunden tbody tr:nth-child(1) .lg-chip.{ampel(t1)}').count() == 1, r1)
    check('Leergut bei Kunden: ohne Rückgabe seit der ersten Lieferung, Schuld von uns ohne Ampel', 'noch nie' in r2 and '15.10.2026' in r2
          and pg.locator(f'#lg-u-kunden tbody tr:nth-child(2) .lg-chip.{ampel(t3)}').count() == 1 and pg.locator('#lg-u-kunden tbody tr:nth-child(3) .lg-chip').count() == 0
          and '01.04.2026' in r3, (r2, r3))
    summe_k = text(pg, '#lg-u-kunden-sum')
    check('Leergut bei Kunden: Summe der Kunden, die uns schulden', summe_k.startswith('2 Kunden haben Leergut von uns im Wert von 85,50 €')
          and (f'{(t1 >= 60) + (t3 >= 60)} seit mindestens 60 Tagen' in summe_k if t1 >= 60 or t3 >= 60 else True), summe_k)
    with pg.expect_download() as dl:
        pg.click('#lg-u-kunden-csv')
    abhol = open(dl.value.path(), encoding='utf-8-sig').read().splitlines()
    check('Abholliste aus der Oberfläche (Dateiname, nach Wert)', dl.value.suggested_filename == f'Leergut-Kunden_{HEUTE}.csv' and abhol[1].startswith('"Testkunde Nord GmbH (9100001)"'), abhol[:2])
    pg.screenshot(path=os.path.join(SH, 'leergut_kunden_1280.png'), full_page=True)
    pg.click('#lg-u-salden tr[data-kunden]')
    pg.wait_for_selector('#lg-tabs [data-tab="konten"][aria-selected="true"]')
    check('Übersicht → Konten mit Filter Kunde', pg.input_value('#lg-k-art') == 'kunde' and pg.locator('#lg-k-liste [data-konto]').count() == 3)
    liste_k = [pg.locator('#lg-k-liste [data-konto] .lg-name').nth(i).inner_text() for i in range(3)]
    check('Konten: Kunden nach Wert sortiert, mit Wert', pg.input_value('#lg-k-sort') == 'wert' and liste_k[0] == 'Testkunde Nord GmbH (9100001)'
          and liste_k[2] == 'Testkunde Süd (9100002)' and '69,00 €' in text(pg, '#lg-k-liste'), liste_k)
    pg.select_option('#lg-k-sort', '')
    check('Konten: wieder nach Name', [pg.locator('#lg-k-liste [data-konto] .lg-name').nth(i).inner_text() for i in range(3)][1] == 'Testkunde Nord GmbH (9100003)'
          and '69,00 €' not in text(pg, '#lg-k-liste'))
    pg.fill('#lg-k-suche', '9100003')
    check('Konten: Suche nach WinAB-Kundennummer', pg.locator('#lg-k-liste [data-konto]').count() == 1)
    pg.click(f'#lg-k-liste [data-konto="{wk["9100003"]["id"]}"]'); pg.wait_for_selector('.lg-saldo')
    pg.wait_for_function("(document.querySelector('#lg-k-detail')?.textContent || '').includes('WinAB-Kd. 9100003')")
    check('Konto: WinAB-Kundennummer und Herkunft der Buchung', 'Lieferschein 500010' in text(pg, '#lg-k-detail') and 'noch nicht zurück' in text(pg, '#lg-k-detail'))
    kopf = text(pg, '#lg-k-detail .lg-winab-bestand')
    check('Kontokopf: Versandart und WinAB-Lademittelbestand laut Kundenstamm neben der Summe des Kontos', 'WinAB-Lademittelbestand −6 · Konto zusammen' in kopf
          and 'Versandart 1 · Direktlieferung' in text(pg, '#lg-k-detail'), kopf)
    pg.screenshot(path=os.path.join(SH, 'leergut_winab_konto_1280.png'), full_page=True)
    pg.fill('#lg-k-suche', '')
    pg.click('#lg-tabs [data-tab="einstellungen"]')
    pg.click(f'#lg-e-partner [data-partner="{wk["9100001"]["id"]}"]'); pg.wait_for_selector('#dlg-partner[open]')
    check('Partner-Dialog: WinAB-Kundennummer', pg.input_value('#pa-kdnr') == '9100001')
    pg.fill('#pa-kdnr', '9100003'); pg.click('#pa-form [type="submit"]'); pg.wait_for_selector('#pa-meldung:not(:empty)')
    check('Partner-Dialog: Kundennummer doppelt gemeldet', 'gehört schon' in text(pg, '#pa-meldung'))
    pg.click('#dlg-partner [data-schliessen]'); zu(pg, '#dlg-partner')
    pg.click('#lg-tabs [data-tab="bilanz"]')   # die Bilanz von vorhin zeigt noch die Kunden aus dem API-Teil
    # erst die neu berechnete Bilanz (die alte aus dem API-Teil hat ebenfalls 3 WinAB-Konten, aber „Test-Spedition Nord“)
    pg.wait_for_function("(() => { const t = document.querySelector('#lg-b-tabelle')?.textContent || ''; return t.includes('Beispiel-Spedition') && !t.includes('Test-Spedition Nord') && (document.querySelector('#lg-b-tabelle tr[data-kunden]')?.textContent || '').includes('(3 Konten)'); })()")
    try:   # die Bilanz wird nach dem Schließen des Dialogs im Hintergrund neu geladen – auf den fertigen Stand warten
        pg.wait_for_function("(() => { const t = document.querySelector('#lg-b-tabelle')?.textContent || ''; return t.includes('Kunden aus WinAB (3 Konten)') && !t.includes('Testkunde'); })()", timeout=15000)
        bil_ok = True
    except Exception:
        bil_ok = False
    check('Bilanz: Kunden aus WinAB in einer Zeile (CSV bleibt je Konto)', bil_ok, text(pg, '#lg-b-tabelle'))

    # WinAB-Datei „Lademittelbewegungen komplett“ (.CSV) – Kunden, Lieferanten, „Übernehmen ab“
    storage_write('lieferanten', {'rev': 2, 'groups': [{'nr': '2930028', 'name': 'Testgeflügel GmbH', 'kurz': 'TESTGEFL', 'versandart': '1'}]})   # Name und Versandart in der Vorschau
    csvd = os.path.join(os.path.dirname(xls), 'Lademittelbewegungen_komplett_.csv')
    with open(csvd, 'wb') as f:
        f.write(winab_csv())
    pg.click('#lg-tabs [data-tab="einstellungen"]')
    pg.set_input_files('#lg-w-datei', csvd)
    pg.wait_for_selector('#lg-w-knoepfe:not([hidden])')
    vor = text(pg, '#lg-w-vorschau')
    check('CSV-Vorschau: Übernehmen ab 01.01.2026 (Datei ab 05.06.2021), 3 Kunden, 6 Belege zum Abgleich (auch Wareneingang mit Tausch), 2 neue Kundenkonten, 3 neue Belege',
          pg.input_value('#lg-w-ab') == '2026-01-01' and pg.get_attribute('#lg-w-ab', 'min') == '2021-06-05' and [kachel(k) for k in ('kunden', 'belege', 'neuKd', 'neu')] == ['3', '6', '2', '3'], vor)
    check('CSV-Vorschau: weggelassen (Sammelrechnung, Karton, Offerte, ohne Wirkung), Korrekturen verrechnet, älterer Beleg genannt, Wareneingang mit Tausch',
          '1 Zeile aus Sammelrechnungen' in vor and '1 Kartonzeile' in vor and '1 × Offerte' in vor and '1 Beleg ohne Wirkung' in vor and '2 Korrekturzeilen mit Minus verrechnet' in vor
          and 'Vor dem 01.01.2026: 1 Kundenbeleg mit Wirkung' in vor and '+9' in text(pg, '#lg-w-vorher') and '1 Wareneingang mit Tausch laut WinAB – gezählt wird der Zugang' in vor, vor)
    lief_t = text(pg, '#lg-w-lief')
    check('CSV-Vorschau: Lieferanten ohne Konto (Saldo nicht gebucht) zur Zuordnung – Wareneingang mit Tausch zählt den Zugang (−5); Lieferantennummer an Kundenzeilen fehlt',
          '2930028' in lief_t and '2300004' in lief_t and '4000017' not in lief_t and '2850008' in lief_t and '−15' in lief_t and '−5' in lief_t and 'nicht gebucht' in lief_t
          and pg.input_value('[data-lf="2930028"]') == '' and '3 Lieferantenbelege werden nicht gebucht' in vor, lief_t)
    check('CSV-Vorschau: Name und Versandart aus dem Lieferantenstamm, neues Konto mit dem Namen',
          'Testgeflügel GmbH' in lief_t and '1 · Direktlieferung' in lief_t and 'Neues Konto anlegen („Testgeflügel GmbH“)' in text(pg, '[data-lf="2930028"]'), lief_t)
    pg.screenshot(path=os.path.join(SH, 'leergut_winab_csv_1280.png'), full_page=True)
    pg.select_option('[data-lf="2930028"]', 'neu')
    pg.wait_for_function("(document.querySelector('#lg-w-vorschau')?.textContent || '').includes('2 Lieferantenbelege werden nicht gebucht') && !document.querySelector('#lg-w-knoepfe').hidden")
    check('CSV-Vorschau: Zuordnung „neues Konto“ – Lieferantensaldo danach, Auswahl behält den Fokus', 'Saldo der zugeordneten Lieferantenkonten danach' in text(pg, '#lg-w-vorschau')
          and pg.evaluate("document.activeElement?.dataset?.lf") == '2930028', text(pg, '#lg-w-vorschau'))
    pg.select_option('[data-lf="2300004"]', SP)
    pg.wait_for_function("(document.querySelector('#lg-w-vorschau')?.textContent || '').includes('1 Lieferantenbeleg wird nicht gebucht') && !document.querySelector('#lg-w-knoepfe').hidden")
    pg.fill('#lg-w-ab', '2021-06-05'); pg.dispatch_event('#lg-w-ab', 'change')
    pg.wait_for_function("(document.querySelector('#lg-w-vorschau [data-z=\"belege\"] b')?.textContent || '') === '7'")
    check('CSV-Vorschau: ganze Geschichte – älterer Beleg dabei, Hinweis entfällt', [kachel(k) for k in ('belege', 'neuKd', 'neu')] == ['7', '3', '6'] and pg.locator('#lg-w-vorher').count() == 0)
    pg.click('#lg-w-uebernehmen')
    pg.wait_for_function("(document.querySelector('#lg-w-meldung')?.textContent || '').startsWith('Übernommen')")
    check('CSV übernommen aus der Oberfläche', 'Übernommen: 3 neue Kundenkonten, 1 neues Lieferantenkonto, 6 neue Belege, 0 geändert, 0 ausgeglichen.' in text(pg, '#lg-w-meldung'), text(pg, '#lg-w-meldung'))
    s = V.call('leergut_start')[1]
    pz = {p.get('kundenNr') or p.get('lieferantNr'): p for p in s['partner'] if p.get('kundenNr') or p.get('lieferantNr')}
    sal = {x['id']: x['saldo'] for x in s['konten']}
    check('CSV: Salden aus der Datei (Korrekturen verrechnet, Kübel), Namen aus dem Kundenstamm bzw. „Kunde“, Lieferant am bestehenden Konto',
          sal[pz['9100006']['id']] == {'e2': 4} and sal[pz['9100007']['id']] == {'e2': 4, 'h1': 1, 'kuebel': 2} and sal[pz['9100008']['id']] == {'e2': 9}
          and sal[pz['2930028']['id']] == {'e2': -15} and pz['9100006']['name'] == 'Fleischerei Beispiel (9100006)' and pz['9100007']['name'] == 'Kunde (9100007)'
          and pz['2300004']['id'] == SP and '4000017' not in pz and 'spedition' not in pz['9100006']['winab'], {k: (p['name'], sal.get(p['id'])) for k, p in pz.items()})
    pg.click('#lg-tabs [data-tab="uebersicht"]'); pg.wait_for_selector('#lg-u-kunden tbody tr')
    zeile6 = pg.locator('#lg-u-kunden tbody tr', has_text='9100006').inner_text()
    check('Leergut bei Kunden: letzte Lieferung aus saldierten Belegen (stornierte Lieferung vom 02.09. zählt nicht)', '01.09.2026' in zeile6 and '02.09.2026' not in zeile6, zeile6)
    ctx.close()

    # Einstellungen am Handy: Lademittel mit Kurzbezeichnung und WinAB-Nr. passen in die Breite
    ctx, pg = anmelden('vera', 'Verwalt-Konto-56', '198.51.100.12', 390, 'dark', 844)
    pg.click('#lg-tabs [data-tab="einstellungen"]'); pg.wait_for_selector('#lg-e-lm tr[data-id="wk2"]')
    check('390px verwalten: Einstellungen mit WinAB-Nr. ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    pg.screenshot(path=os.path.join(SH, 'leergut_einstellungen_390_dark.png'), full_page=True)
    # Excel-Liste der Spedition bis 06.09.2026 mit anderer Menge als WinAB-Beleg 44021 (Lieferant 2300004) → Abgleich in der Vorschau
    roh = storage_raw('leergut-bewegungen')
    bd_alt = json.loads(roh.split('\n', 1)[1] if roh.startswith('<?php') else roh)
    bd = json.loads(json.dumps(bd_alt))
    bd['liste'].append({'id': 'bxlui1', 'partner': SP, 'datum': '2026-09-06', 'typ': 'bewegung', 'abgang': {'e2': 6}, 'zugang': {}, 'beleg': 'LS-Excel-7', 'text': 'Excel-Zeile 99',
                        'quelle': 'import', 'erfasst': {'t': '2026-10-29T08:00:00Z', 'von': 'Test', 'vonId': 'u0'}, 'storno': None})
    bd['rev'] = bd_alt.get('rev', 0) + 1
    storage_write('leergut-bewegungen', bd)
    roh = storage_raw('leergut-stamm')
    sd_alt = json.loads(roh.split('\n', 1)[1] if roh.startswith('<?php') else roh)
    sd = json.loads(json.dumps(sd_alt))
    next(p for p in sd['partner'] if p['id'] == SP)['winabAb'] = '2026-01-01'   # WinAB ergänzt die Excel-Liste ab 2026
    sd['rev'] = sd_alt.get('rev', 0) + 1
    storage_write('leergut-stamm', sd)
    with open(csvd, 'wb') as f:
        f.write(winab_csv(WCSV + [(1, '08.09.2026', '', '2222222', 3, 'Abgang', '44400', 'Lieferschein', 'E2 Kisten')]))
    pg.set_input_files('#lg-w-datei', csvd)
    pg.wait_for_selector('#lg-w-lief [data-lf="2222222"]')
    exc = text(pg, '#lg-w-excel')
    check('CSV-Vorschau: Abgleich mit der Excel-Liste – abweichender Beleg nicht gebucht, früher gebuchter wird storniert, Tabelle mit beiden Mengen',
          '1 Beleg weicht am selben Tag von der Excel-Liste ab' in exc and '1 früher doppelt gebuchter Beleg wird storniert' in exc
          and 'Lieferschein 44021' in text(pg, '#lg-w-abweichend') and 'LS-Excel-7' in text(pg, '#lg-w-abweichend') and '+6' in text(pg, '#lg-w-abweichend'), (exc, text(pg, '#lg-w-abweichend')))
    check('390px: CSV-Vorschau mit Zuordnung und Excel-Abgleich ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    check('CSV-Vorschau: Option „ältere WinAB-Belege stornieren“ vorhanden, standardmäßig aus', pg.locator('#lg-w-aeltere').count() == 1 and not pg.is_checked('#lg-w-aeltere'))
    pg.locator('#lg-w-vorschau').screenshot(path=os.path.join(SH, 'leergut_winab_csv_390_dark.png'))
    bd_alt['rev'] = bd['rev'] + 1
    storage_write('leergut-bewegungen', bd_alt)   # nur Vorschau: Stand von vorher wiederherstellen
    sd_alt['rev'] = sd['rev'] + 1
    storage_write('leergut-stamm', sd_alt)
    ctx.close()

    # Buchen am Handy: Abschreibungen mit beiden Knöpfen, Dachser-Dialog
    ctx, pg = anmelden('bea', 'Buchung-Konto-34', '198.51.100.11', 390, 'light', 844)
    pg.click('#lg-tabs [data-tab="abschreibungen"]'); pg.wait_for_selector('#lg-d-dachser:not([hidden])')
    check('390px buchen: Abschreibungen mit „Dachser-Liste einlesen“ ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    pg.click('#lg-d-dachser'); pg.wait_for_selector('#dlg-dachser[open]')
    pg.fill('#dl-text', DL); pg.click('#dl-pruefen'); pg.wait_for_selector('#dl-vorschau .lg-vorschau')
    check('390px: Dachser-Dialog mit Vorschau passt in die Breite', pg.evaluate("(() => { const d = document.querySelector('#dlg-dachser'); return d.scrollWidth <= d.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; })()"))
    pg.screenshot(path=os.path.join(SH, 'leergut_dachser_390.png'))
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
