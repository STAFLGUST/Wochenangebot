"""REWE (Modul rewe, Oberfläche rewe.intern unter /module/rewe/) – Vordisposition Dry Aged für REWE-Märkte.

Geprüft: Register (fertig und produktiv unter rewe.dashboard-stafl.de, Kachel verfügbar, ohne Testfreigabe erreichbar); Rechte serverseitig (GR-103):
ohne Anmeldung, ohne REWE-Recht, nur ansehen, bearbeiten (nur eigene Märkte, fremde wie nicht vorhanden), alle Listen, verwalten,
Wochenabschluss (Recht oder Team des Moduls); ohne CSRF, GET auf schreibende Aktion; Grundwerte (Direktbelieferung mit Bestellschluss
Freitag früh, Artikel Roastbeef/Filetkopf/Vac. Set); Lieferwege und Artikel (Pflichtfelder, doppelt, nicht entfernbar, WinAB-Nummer);
Märkte (anlegen nur verwalten, Pflichtfelder, Kd.-Nr. eindeutig, Name/Anschrift aus dem Kundenstamm der Verwaltung, Stammfelder nur
verwalten, Stand 409, Ansprechpartner, Kaufbereitschaft und Dauerauftrag mit Verlauf); Wochenabfrage (Standard = nächste Lieferwoche,
eigene Liste, gruppiert Zentrallager vor Direkt, alle Listen nur mit Recht/Team, ruhende Märkte als eigene Liste); Antworten
(Fehlerfälle, Mengen je Artikel, Stand 409, zurücknehmen, höchstens zwölf Wochen voraus, Schnappschuss von Lieferweg und
Zuständigkeit); Daueraufträge (fällig nach Rhythmus und ab-KW, Pause, übernehmen nur ohne Antwort, mit Filetkopf; seit 12.11.2026 Rhythmus 6/8,
Pause von–bis, Enddatum, Rechte, automatisch zum Bestellschluss – idempotent, nie über eine ausdrückliche Antwort, Schnappschuss, nicht in
älteren Wochen, Export bestellt spätestens, Excel-Spalte „Dauerauftrag“); Zuweisung und
Lieferweg ab KW (frühere Wochen unverändert, Verlauf mit Namen); Notizen und Wiedervorlagen; Wochenabschluss (Einzelaufträge je Markt,
Summen je Lieferweg und Mitarbeiter, offene Märkte, Artikel ohne Nummer, Nachträge nach dem Export, in WinAB erfasst) und Excel
(Blätter, Kopf, Auftragsnummern, Texte bleiben Text, Protokoll); Datenpaket (Rechte, Fehler je Markt, Vorschau schreibt nichts, nur in
leeres Modul oder mit „ersetzen“, Listen den Mitarbeitern zugeordnet, Verlauf über mehrere Jahre); Oberfläche (Meine Woche mit Antwort
per Klick und Mengen, „Rückgängig“ und Zurücksetzen, Bestellungen zugeklappt, Verlauf mit Vorbestellungen, Marktkarte mit Hinweis und Notizen, Reiter
Daueraufträge (Liste mit Wochenleiste, Pop-up aus Reiter, Marktkarte, Marktakte und Woche – Klick daneben schließt nicht –,
Marktsuche beim Anlegen, Pause von–bis, Ende, Filter, beenden; automatische Bestellung als erledigt, Kachel als Filter), Marktakte mit Notiz, Zuweisung, Wochenabschluss mit Excel, Einstellungen mit Datenpaket; 1280 und 390 px, hell
und dunkel, kein waagerechtes Scrollen, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import datetime
import io
import json
import os

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
HIER = os.path.dirname(os.path.abspath(__file__))
PAKET = json.load(open(os.path.join(HIER, '..', 'fixtures', 'rewe', 'datenpaket.json'), encoding='utf-8'))
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def kw_von(d):
    j, w, _ = d.isocalendar(); return f'{j}-{w:02d}'


def kw_plus(kw, n):
    return kw_von(datetime.date.fromisocalendar(int(kw[:4]), int(kw[5:]), 1) + datetime.timedelta(weeks=n))


HEUTE = datetime.date.today()
ABSCHLUSS = kw_von(HEUTE + datetime.timedelta(days=3))   # Woche des zuletzt erreichten Bestellschlusses (Freitag früh)
ABFRAGE = kw_plus(ABSCHLUSS, 1)
kw_text = f'KW {int(ABFRAGE[5:])}/{ABFRAGE[:4]}'

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lena', 'Lena Leitung', 'editor', 'Leitung-Konto-11', {'grant': ['rewe.verwalten', 'rewe.exportieren']}),
          ('mark', 'Mark Markt', 'editor', 'Laden-Konto-22', {'grant': ['rewe.bearbeiten']}),
          ('evi', 'Evi Eins', 'editor', 'Eins-Konto-33', {'grant': ['rewe.bearbeiten']}),
          ('lea', 'Lea Lesen', 'viewer', 'Leserin-Konto-44', {'grant': ['rewe.sehen']}),
          ('sabi', 'Sabi Summe', 'editor', 'Summe-Konto-55', {'grant': ['rewe.bearbeiten']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-66', {}),
          ('nina', 'Nina Neu', 'editor', 'Nicht-Konto-77', {'grant': ['rewe.bearbeiten']}),
          ('pia', 'Pia Plus', 'editor', 'Plus-Konto-88', {}),                          # ohne REWE-Recht, wird im Modul ergänzt
          ('udo', 'Udo Ohnezugang', 'editor', 'Zugang-Konto-99', {'deny': ['rewe.zugang']}),   # ohne Modulzugang
          ('vera', 'Vera Verbot', 'editor', 'Verbot-Konto-98', {'deny': ['rewe.sehen']}))      # „REWE ansehen“ verboten
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
LE, M, E, L, SA, O, NI, PI, N = K['lena'], K['mark'], K['evi'], K['lea'], K['sabi'], K['otto'], K['nina'], K['pia'], Client('198.51.100.30')

# ── Register und Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['rewe']
ob = mod['oberflaechen'][0]
check('Register: REWE fertig und produktiv (Auftrag des Inhabers 30.10.2026), Adresse rewe.dashboard-stafl.de/module/rewe/',
      ob['entwicklung'] == 'fertig' and ob['freigabe'] == 'produktiv' and ob['adresse'] == 'https://rewe.dashboard-stafl.de/module/rewe/', ob)
check('Kachel: verfügbar, Ziel rewe.intern', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True and mod['kachel']['ziel'] == 'rewe.intern', mod['kachel'])
check('produktiv ohne Testfreigabe: Administrator und Mitarbeiter mit REWE-Recht erreichen das Modul', A.call('rewe_start')[0] == 200 and NI.call('rewe_start')[0] == 200)

# ── Rechte ──
check('ohne Anmeldung: kein Zugang (401/404)', N.call('rewe_start')[0] in (401, 404))
check('ohne REWE-Recht (nur Modulzugang der Rolle): 403', O.call('rewe_start')[0] == 403)
st, d = L.call('rewe_start')
check('Ansehen: Start ok, keine weiteren Rechte, keine Mitarbeiterliste', st == 200 and d['rechte'] == {'bearbeiten': False, 'alle': False, 'verwalten': False, 'exportieren': False}
      and d['personen'] == [], d.get('rechte'))
check('Kalenderwochen: Abfrage = Woche nach dem nächsten Bestellschluss, Abschluss = Woche davor', d['abfrage'] == ABFRAGE and d['abschlussKw'] == ABSCHLUSS, (d['abfrage'], d['abschlussKw']))
check('Grundwerte: nur Direktbelieferung (Bestellschluss Freitag früh der Vorwoche), Artikel Roastbeef, Filetkopf, Vac. Set (Stück)',
      [(x['id'], x['art'], x['bestellschluss']) for x in d['lieferwege']] == [('direkt', 'direkt', 'Freitag früh der Vorwoche')]
      and [x['id'] for x in d['artikel']] == ['rb', 'fk', 'set'] and all(x['einheit'] == 'Stück' and x['nr'] == '' for x in d['artikel']), d['lieferwege'])
check('Bearbeiten: nur bearbeiten', M.call('rewe_start')[1]['rechte'] == {'bearbeiten': True, 'alle': False, 'verwalten': False, 'exportieren': False})
st, d = LE.call('rewe_start')
check('Verwalten + Wochenabschluss: alle Rechte, Mitarbeiter mit „REWE ansehen“ (ohne Otto)', d['rechte'] == {'bearbeiten': True, 'alle': True, 'verwalten': True, 'exportieren': True}
      and {p['name'] for p in d['personen']} >= {'Mark Markt', 'Evi Eins', 'Lea Lesen'} and 'Otto Ohne' not in {p['name'] for p in d['personen']} and d['leer'] is True, d)

# ── Lieferwege und Artikel ──
check('Stammdaten nur mit „verwalten“ (Bearbeiten 403)', M.call('rewe_stamm_save', {'lieferwege': [{'name': 'X', 'art': 'lager'}]})[0] == 403)
LW = [{'id': 'direkt', 'name': 'Direktbelieferung', 'art': 'direkt', 'bestellschluss': 'Freitag früh der Vorwoche', 'aktiv': True},
      {'name': 'Zentrallager Nord', 'art': 'lager'}, {'name': 'Zentrallager Süd', 'art': 'lager', 'bestellschluss': 'Donnerstag 12 Uhr'}]
for name, b in (('ohne Name', {'lieferwege': [LW[0], {'name': '', 'art': 'lager'}]}), ('Name doppelt', {'lieferwege': [LW[0], LW[1], {'name': 'zentrallager nord', 'art': 'lager'}]}),
                ('Art unbekannt', {'lieferwege': [LW[0], {'name': 'A', 'art': 'rakete'}]}), ('Direkt entfernt', {'lieferwege': [LW[1]]}),
                ('Artikelnummer mit Leerzeichen', {'artikel': [{'id': 'rb', 'name': 'Roastbeef Dry Aged', 'nr': '10 01'}, {'id': 'fk', 'name': 'Filetkopf'}, {'id': 'set', 'name': 'Vac. Set'}]}),
                ('kein Artikel aktiv', {'artikel': [{'id': 'rb', 'name': 'R', 'aktiv': False}, {'id': 'fk', 'name': 'F', 'aktiv': False}, {'id': 'set', 'name': 'S', 'aktiv': False}]})):
    st, r = LE.call('rewe_stamm_save', b)
    check(f'Stammdaten: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = LE.call('rewe_stamm_save', {'lieferwege': LW, 'artikel': [{'id': 'rb', 'name': 'Roastbeef Dry Aged', 'einheit': 'Stück', 'nr': '10001'},
                                                                    {'id': 'fk', 'name': 'Filetkopf', 'einheit': 'Stück'}, {'id': 'set', 'name': 'Vac. Set', 'einheit': 'Stück'}]})
lw = {x['name']: x['id'] for x in r.get('lieferwege', [])}
check('Lieferwege und Artikel gespeichert (neue Kennungen, Bestellschluss Standard, WinAB-Nummer)', st == 200 and len(lw) == 3
      and r['lieferwege'][1]['bestellschluss'] == 'Freitag früh der Vorwoche' and r['lieferwege'][2]['bestellschluss'] == 'Donnerstag 12 Uhr' and r['artikel'][0]['nr'] == '10001', r)
NORD, SUED = lw['Zentrallager Nord'], lw['Zentrallager Süd']

# ── Filetkopf extra (Inhaber 12.11.2026: bei jedem Roastbeef ist schon ein Filetkopf dabei – bestellte sind zusätzlich) ──
HINWEIS_FK = '1 Filetkopf ist bei jedem Roastbeef Dry Aged schon dabei'
art = {a['id']: a for a in r['artikel']}
roh_art = {a['id']: a for a in json.loads(storage_raw('rewe-stamm').split('?>\n', 1)[-1])['artikel']}
check('Filetkopf extra als Vorgabe für bestehende Daten: extra und Hinweis aufgelöst, gespeichert unverändert ohne neue Felder (GR-006)',
      [(a['id'], a['extra'], a['anzeige']) for a in r['artikel']] == [('rb', False, 'Roastbeef Dry Aged'), ('fk', True, 'Filetkopf extra'), ('set', False, 'Vac. Set')]
      and art['fk']['extraHinweis'] == HINWEIS_FK and art['fk']['name'] == 'Filetkopf'
      and not any(k in a for a in roh_art.values() for k in ('extra', 'extraHinweis', 'anzeige')), (r['artikel'], roh_art))
ART = [{'id': 'rb', 'name': 'Roastbeef Dry Aged', 'einheit': 'Stück', 'nr': '10001'}, {'id': 'fk', 'name': 'Filetkopf', 'einheit': 'Stück'}, {'id': 'set', 'name': 'Vac. Set', 'einheit': 'Stück'}]
st, r = LE.call('rewe_stamm_save', {'artikel': [ART[0], {**ART[1], 'extraHinweis': 'x' * 121}, ART[2]]})
check('Filetkopf extra: Hinweis über 120 Zeichen → 422', st == 422 and '120' in r.get('error', ''), (st, r))
st, r = LE.call('rewe_stamm_save', {'artikel': [ART[0], {**ART[1], 'extra': False}, {**ART[2], 'extra': True, 'extraHinweis': 'Testhinweis'}]})
art = {a['id']: a for a in r.get('artikel', [])}
check('Merkmal extra pflegbar: Filetkopf abgewählt → „Filetkopf“, Hinweis bleibt gespeichert; Vac. Set → „Vac. Set extra“ mit eigenem Hinweis',
      st == 200 and art['fk']['extra'] is False and art['fk']['anzeige'] == 'Filetkopf' and art['set']['anzeige'] == 'Vac. Set extra'
      and art['set']['extraHinweis'] == 'Testhinweis' and LE.call('rewe_start')[1]['artikel'][2]['anzeige'] == 'Vac. Set extra', r)
st, r = LE.call('rewe_stamm_save', {'artikel': [ART[0], {**ART[1], 'name': 'Filetkopf Extra', 'extra': True}, {**ART[2], 'extra': False}]})
check('Name trägt schon „Extra“: kein doppeltes „extra“', st == 200 and r['artikel'][1]['anzeige'] == 'Filetkopf Extra', r.get('artikel'))
st, r = LE.call('rewe_stamm_save', {'artikel': [ART[0], {**ART[1], 'extra': True, 'extraHinweis': HINWEIS_FK}, ART[2]]})
art = {a['id']: a for a in r.get('artikel', [])}
check('Ohne Angabe bleibt gespeichert (ältere Oberfläche): Filetkopf wieder „Filetkopf extra“, Vac. Set ohne extra',
      st == 200 and art['fk']['anzeige'] == 'Filetkopf extra' and art['fk']['extraHinweis'] == HINWEIS_FK and art['set']['anzeige'] == 'Vac. Set'
      and LE.call('rewe_stamm_save', {'artikel': ART})[1]['artikel'][1]['anzeige'] == 'Filetkopf extra', r.get('artikel'))

# ── Kundenstamm der Verwaltung ──
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'REWE Markt GmbH', 'nr': '1799003', 'strasse': 'Stammstraße 3', 'plz': '20095', 'ort': 'Stammstadt',
                              'telefon': '040 333', 'email': 'markt3@example.org', 'active': True})
check('Kunde im Kundenstamm angelegt (WinAB-Kd.-Nr. 1799003)', st == 200, (st, r))

# ── Märkte ──
M1 = {'name': 'REWE Musterstadt', 'kdNr': '1799001', 'reweNr': '40001001', 'strasse': 'Marktplatz 1', 'plz': '20001', 'ort': 'Musterstadt', 'lieferweg': NORD, 'zustaendig': ids['mark']}
check('Markt anlegen nur mit „verwalten“ (Bearbeiten 403)', M.call('rewe_markt_save', M1)[0] == 403)
for name, b in (('ohne Ort', {'ort': ''}), ('ohne Name', {'name': ''}), ('ohne Lieferweg', {'lieferweg': ''}), ('Lieferweg unbekannt', {'lieferweg': 'lzzz'}),
                ('Kd.-Nr. mit Buchstaben', {'kdNr': '17A9'}), ('PLZ zu lang', {'plz': '123456'}), ('Kaufbereitschaft unbekannt', {'kauf': 'vielleicht'}),
                ('Zuständig unbekannt', {'zustaendig': 'uzzz'}), ('Abfragetag Sonntag', {'abfragetag': 'so'}), ('Dauerauftrag ohne Menge', {'dauer': {'rhythmus': 2, 'mengen': {}, 'ab': ABFRAGE}}),
                ('Dauerauftrag ohne ab', {'dauer': {'rhythmus': 1, 'mengen': {'rb': 1}}}), ('E-Mail des Ansprechpartners', {'ansprechpartner': [{'name': 'Frau X', 'email': 'kein-at'}]}),
                ('Ansprechpartner ohne Name', {'ansprechpartner': [{'telefon': '040 1'}]}), ('13 Ansprechpartner', {'ansprechpartner': [{'name': f'P{i}'} for i in range(13)]})):
    st, r = LE.call('rewe_markt_save', {**M1, **b})
    check(f'Markt: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = LE.call('rewe_markt_save', M1)
m1 = r.get('markt', {})
check('Markt 1 angelegt (Nord, Mark, ab Abfragewoche, nicht im Kundenstamm)', st == 200 and m1['lieferwegName'] == 'Zentrallager Nord' and m1['zustaendigName'] == 'Mark Markt'
      and m1['zustaendigHist'][0]['ab'] == ABFRAGE and m1['winab'] is False and m1['kauf'] == 'regelmaessig', r)
check('Kd.-Nr. doppelt → 422', LE.call('rewe_markt_save', {**M1, 'ort': 'Anderswo'})[0] == 422)
st, r = LE.call('rewe_markt_save', {'kdNr': '1799002', 'name': 'REWE Evistadt', 'ort': 'Evistadt', 'strasse': 'Evi-Weg 2', 'lieferweg': SUED, 'zustaendig': ids['evi'], 'kauf': 'interessiert'})
m2 = r.get('markt', {})
check('Markt 2 angelegt (Süd, Evi, Kaufbereitschaft beim Anlegen „interessiert“)', st == 200 and m2['zustaendigName'] == 'Evi Eins' and m2['kauf'] == 'interessiert', r)
st, r = LE.call('rewe_markt_save', {'kdNr': '1799003', 'lieferweg': NORD, 'zustaendig': ids['mark']})
m3 = r.get('markt', {})
check('Markt 3 nur mit Kd.-Nr.: Name, Anschrift und Telefon aus dem Kundenstamm', st == 200 and m3['winab'] is True and m3['name'] == 'REWE Markt GmbH'
      and m3['ort'] == 'Stammstadt' and m3['strasse'] == 'Stammstraße 3' and m3['telefon'] == '040 333', r)
st, r = LE.call('rewe_markt_save', {'kdNr': '1799004', 'name': 'REWE Dauerdorf', 'ort': 'Dauerdorf', 'lieferweg': 'direkt', 'zustaendig': ids['mark'],
                                    'dauer': {'rhythmus': 2, 'mengen': {'rb': 1, 'fk': 1}, 'ab': ABFRAGE}, 'abfragetag': 'do',
                                    'ansprechpartner': [{'name': 'Frau Dauer', 'rolle': 'Metzgerei', 'telefon': '040 4', 'email': 'dauer@example.org'}]})
m4 = r.get('markt', {})
check('Markt 4 (Direkt) mit Dauerauftrag alle 2 Wochen 1 Roastbeef + 1 Filetkopf, Abfragetag, Ansprechpartner', st == 200 and m4['dauer'] == {'rhythmus': 2, 'mengen': {'rb': 1, 'fk': 1}, 'ab': ABFRAGE, 'pauseBis': '', 'pauseVon': '', 'bis': ''}
      and m4['ansprechpartner'][0]['email'] == 'dauer@example.org' and m4['abfragetag'] == 'do', r)

# ── Wochenabfrage ──
st, r = M.call('rewe_woche')
w = r.get('woche', {})
check('Woche: Standard = Abfragewoche', st == 200 and w['kw'] == ABFRAGE, (st, w.get('kw')))
gr = [(g['name'], [x['id'] for x in g['maerkte']]) for g in w.get('gruppen', [])]
check('Woche: nur eigene Märkte, Zentrallager vor Direktbelieferung', gr == [('Zentrallager Nord', sorted([m1['id'], m3['id']], key=lambda i: {m1['id']: 'Musterstadt', m3['id']: 'Stammstadt'}[i])),
                                                                              ('Direktbelieferung', [m4['id']])], gr)
x4 = w['gruppen'][1]['maerkte'][0]
check('Woche: Dauerauftrag fällig, Text, Verlauf acht Wochen, darf antworten', x4['dauerFaellig'] is True and 'Dauerauftrag alle 2 Wochen' in x4['dauerText']
      and len(x4['verlauf']) == 8 and x4['verlauf'][-1]['kw'] == kw_plus(ABFRAGE, -1) and x4['darfAntworten'] is True, x4)
check('Woche: Vorschau der drei folgenden Wochen (Vorbestellungen), Zahl der Notizen', [v['kw'] for v in x4['vorschau']] == [kw_plus(ABFRAGE, i) for i in (1, 2, 3)]
      and all(v['status'] == '' for v in x4['vorschau']) and x4['notizen'] == 0, (x4.get('vorschau'), x4.get('notizen')))
check('Woche: Evi sieht nur Markt 2', [x['id'] for g in E.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte']] == [m2['id']])
check('Woche: Lesen ohne eigene Märkte → leer', L.call('rewe_woche')[1]['woche']['gruppen'] == [])
check('andere Liste ohne „alle“ → 403', M.call('rewe_woche&wer=*')[0] == 403 and M.call('rewe_woche&wer=' + ids['evi'])[0] == 403)
st, r = LE.call('rewe_woche&wer=*')
check('Leitung: alle Listen (4 Märkte), Liste von Evi (1 Markt)', st == 200 and sum(len(g['maerkte']) for g in r['woche']['gruppen']) == 4
      and [x['id'] for g in LE.call('rewe_woche&wer=' + ids['evi'])[1]['woche']['gruppen'] for x in g['maerkte']] == [m2['id']], r)
check('Woche: ungültige KW → 422', M.call('rewe_woche&kw=2026-60')[0] == 422 and M.call('rewe_woche&kw=morgen')[0] == 422)

# ── Antworten ──
AW = {'markt': m1['id'], 'kw': ABFRAGE, 'status': 'bestellt', 'mengen': {'rb': 2}}
check('Antwort: nur ansehen → 403', L.call('rewe_antwort', AW)[0] == 403)
csrf = M.csrf; M.csrf = ''
check('Antwort ohne CSRF: 403', M.call('rewe_antwort', AW)[0] == 403)
M.csrf = csrf
check('Antwort per GET: 405', M.call('rewe_antwort')[0] == 405)
check('fremder Markt (Evi) für Mark: 404', M.call('rewe_antwort', {**AW, 'markt': m2['id']})[0] == 404)
check('unbekannter Markt: 404', M.call('rewe_antwort', {**AW, 'markt': 'mzzz'})[0] == 404)
for name, b in (('bestellt ohne Menge', {'mengen': {}}), ('Menge 0', {'mengen': {'rb': 0}}), ('negative Menge', {'mengen': {'rb': -1}}), ('Kommazahl', {'mengen': {'rb': 1.5}}),
                ('Menge 1000', {'mengen': {'rb': 1000}}), ('unbekannter Artikel', {'mengen': {'lachs': 1}}), ('Antwort unbekannt', {'status': 'vielleicht'}),
                ('KW ungültig', {'kw': '2026-54'}), ('13 Wochen voraus', {'kw': kw_plus(kw_von(HEUTE), 13)}), ('Notiz zu lang', {'notiz': 'x' * 301})):
    st, r = M.call('rewe_antwort', {**AW, **b})
    check(f'Antwort: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = M.call('rewe_antwort', {**AW, 'r': 0, 'notiz': '=SUMME(A1)'})
a1 = r.get('antwort', {})
check('Antwort bestellt (2 Roastbeef, Stand 1, Schnappschuss Lieferweg und Zuständigkeit, Name)', st == 200 and a1['status'] == 'bestellt' and a1['mengen'] == {'rb': 2}
      and a1['r'] == 1 and a1['lieferweg'] == NORD and a1['zustaendig'] == 'Mark Markt' and a1['von'] == 'Mark Markt' and a1['quelle'] == 'hand', r)
check('Antwort: veralteter Stand → 409 mit aktueller Antwort', (lambda x: x[0] == 409 and x[1]['antwort']['r'] == 1)(M.call('rewe_antwort', {**AW, 'r': 0})))
st, r = M.call('rewe_antwort', {**AW, 'status': 'kein', 'mengen': {'rb': 5}, 'r': 1})
check('Kein Bedarf: Mengen entfallen', st == 200 and r['antwort']['status'] == 'kein' and r['antwort']['mengen'] == [] or r['antwort']['mengen'] == {}, r)
st, r = M.call('rewe_antwort', {**AW, 'status': '', 'r': 2})
check('Antwort zurückgenommen (offen)', st == 200 and r['antwort'] is None, r)
st, r = M.call('rewe_antwort', {**AW, 'mengen': {'rb': 2, 'set': 1}, 'ohneBerechnung': True, 'notiz': '=SUMME(A1)'})
check('wieder bestellt: 2 Roastbeef + 1 Vac. Set, ohne Berechnung', st == 200 and r['antwort']['mengen'] == {'rb': 2, 'set': 1} and r['antwort']['ohneBerechnung'] is True, r)
check('Mark beantwortet Markt 3 (kein Bedarf) und vergangene Woche bei Markt 1', M.call('rewe_antwort', {'markt': m3['id'], 'kw': ABFRAGE, 'status': 'kein'})[0] == 200
      and M.call('rewe_antwort', {'markt': m1['id'], 'kw': kw_plus(ABFRAGE, -1), 'status': 'bestellt', 'mengen': {'rb': 1}})[0] == 200)
x1 = next(x for g in M.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m1['id'])
check('Verlauf zeigt die Vorwoche (1 bestellt)', x1['verlauf'][-1] == {'kw': kw_plus(ABFRAGE, -1), 'status': 'bestellt', 'menge': 1}, x1['verlauf'][-1])
st, r = LE.call('rewe_antwort', {'markt': m2['id'], 'kw': ABFRAGE, 'status': 'ne'})
check('Leitung (alle + bearbeiten) antwortet für Evis Markt (Vertretung), Schnappschuss Zuständig Evi', st == 200 and r['antwort']['zustaendig'] == 'Evi Eins' and r['antwort']['von'] == 'Lena Leitung', r)

# ── Daueraufträge ──
check('Dauerauftrag übernehmen: nur ansehen 403', L.call('rewe_dauer_uebernehmen', {'kw': ABFRAGE})[0] == 403)
st, r = M.call('rewe_dauer_uebernehmen', {'kw': ABFRAGE})
check('fällige Daueraufträge übernommen (1)', st == 200 and r['uebernommen'] == 1, r)
x4 = next(x for g in M.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m4['id'])
check('Dauerauftrag als Bestellung: 1 Roastbeef + 1 Filetkopf, Herkunft Dauerauftrag', x4['antwort']['mengen'] == {'rb': 1, 'fk': 1} and x4['antwort']['quelle'] == 'dauer', x4['antwort'])
check('Texte mit „Filetkopf extra“ (Dauerauftrag), gespeicherte Mengen unverändert (1 Filetkopf, nichts dazugerechnet)',
      x4['dauerText'] == 'Dauerauftrag alle 2 Wochen · 1 Roastbeef Dry Aged + 1 Filetkopf extra' and x4['dauer']['mengen'] == {'rb': 1, 'fk': 1}, (x4['dauerText'], x4['dauer']))
check('zweites Übernehmen ändert nichts (nur ohne Antwort)', M.call('rewe_dauer_uebernehmen', {'kw': ABFRAGE})[1]['uebernommen'] == 0)
x4n = next(x for g in M.call(f'rewe_woche&kw={kw_plus(ABFRAGE, 1)}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m4['id'])
check('Folgewoche: nicht fällig, nächste Lieferung in zwei Wochen', x4n['dauerFaellig'] is False and x4n['dauerNaechste'] == kw_plus(ABFRAGE, 2), x4n)
st, r = M.call('rewe_markt_save', {'id': m4['id'], 'dauer': {'rhythmus': 2, 'mengen': {'rb': 1, 'fk': 1}, 'ab': ABFRAGE, 'pauseBis': kw_plus(ABFRAGE, 2)}})
x4p = next(x for g in M.call(f'rewe_woche&kw={kw_plus(ABFRAGE, 2)}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m4['id'])
check('Pause bis zur fälligen Woche: nächste Lieferung danach im Rhythmus', st == 200 and x4p['dauerFaellig'] is False and x4p['dauerNaechste'] == kw_plus(ABFRAGE, 4), x4p.get('dauerNaechste'))
l4 = next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['id'] == m4['id'])
check('Märkteliste für den Reiter „Daueraufträge“: Dauerauftrag, nächste Lieferung (Abfragewoche), Stand, darf pflegen',
      l4['dauer']['rhythmus'] == 2 and l4['dauer']['pauseBis'] == kw_plus(ABFRAGE, 2) and l4['dauerNaechste'] == kw_plus(ABFRAGE, 4) and l4['darfPflegen'] is True and l4['rev'] >= 1, l4)
check('Märkteliste: „nur ansehen“ darf nicht pflegen', all(m['darfPflegen'] is False for m in L.call('rewe_maerkte')[1]['maerkte']))

# ── Markt pflegen ──
st, r = M.call('rewe_markt_save', {'id': m1['id'], 'rev': m1['rev'], 'kauf': 'gelegentlich', 'hinweis': 'nur gereifte Ware'})
check('Mark ändert Kaufbereitschaft und Hinweis seines Marktes', st == 200 and r['markt']['kauf'] == 'gelegentlich' and r['markt']['rev'] == m1['rev'] + 1, r)
check('veralteter Stand → 409', M.call('rewe_markt_save', {'id': m1['id'], 'rev': m1['rev'], 'kauf': 'regelmaessig'})[0] == 409)
check('Stammfelder nur mit „verwalten“ (403)', M.call('rewe_markt_save', {'id': m1['id'], 'ort': 'Woanders'})[0] == 403)
check('fremden Markt pflegen → 404', M.call('rewe_markt_save', {'id': m2['id'], 'kauf': 'ruhend'})[0] == 404)
check('Leitung ändert Stammfelder', LE.call('rewe_markt_save', {'id': m1['id'], 'strasse': 'Marktplatz 1a'})[1]['markt']['strasse'] == 'Marktplatz 1a')

# ── Notizen und Wiedervorlagen ──
NZ = {'markt': m1['id'], 'art': 'telefonat', 'text': 'Möchte ab nächster Woche wieder wöchentlich', 'wiedervorlage': HEUTE.isoformat()}
check('Notiz: nur ansehen 403', L.call('rewe_notiz_save', NZ)[0] == 403)
for name, b in (('ohne Text', {'text': ' '}), ('Art Änderung', {'art': 'system'}), ('Datum ungültig', {'wiedervorlage': '2026-02-30'}), ('Datum in drei Jahren', {'wiedervorlage': (HEUTE + datetime.timedelta(days=1100)).isoformat()})):
    st, r = M.call('rewe_notiz_save', {**NZ, **b})
    check(f'Notiz: {name} → 422', st == 422, (st, r))
check('Notiz an fremdem Markt → 404', M.call('rewe_notiz_save', {**NZ, 'markt': m2['id']})[0] == 404)
st, r = M.call('rewe_notiz_save', NZ)
n1 = r.get('notiz', {})
check('Notiz mit Wiedervorlage heute', st == 200 and n1['wv'] == HEUTE.isoformat() and n1['von'] == 'Mark Markt', r)
x1 = next(x for g in M.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m1['id'])
check('Woche zeigt die fällige Wiedervorlage', [v['id'] for v in x1['wiedervorlagen']] == [n1['id']], x1['wiedervorlagen'])
check('Woche zählt die Notizen ohne automatische Änderungen (1 Telefonat)', x1['notizen'] == 1, x1.get('notizen'))
# Vorbestellung in zwei Wochen erscheint in der Vorschau der Abfragewoche; danach wieder zurückgenommen
st, r = M.call('rewe_antwort', {'markt': m1['id'], 'kw': kw_plus(ABFRAGE, 2), 'status': 'bestellt', 'mengen': {'rb': 2}})
v1 = next(x for g in M.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m1['id'])['vorschau']
check('Vorbestellung KW+2 in der Vorschau (bestellt, 2 Stück)', st == 200 and v1[1] == {'kw': kw_plus(ABFRAGE, 2), 'status': 'bestellt', 'menge': 2, 'dauer': 0} and v1[0]['status'] == '', v1)
check('Vorbestellung zurückgenommen', M.call('rewe_antwort', {'markt': m1['id'], 'kw': kw_plus(ABFRAGE, 2), 'status': '', 'r': r['antwort']['r']})[0] == 200)
# Hinweis bis 4.000 Zeichen (vorher 1.000)
akt = M.call('rewe_markt&id=' + m1['id'])[1]['markt']
st, r = M.call('rewe_markt_save', {'id': m1['id'], 'rev': akt['rev'], 'hinweis': 'Wichtig ' * 500})
check('Hinweis mit 4.000 Zeichen gespeichert, mehrzeilig', st == 200 and len(r['markt']['hinweis']) == 3999, (st, len(r.get('markt', {}).get('hinweis', ''))))
check('Hinweis über 4.000 Zeichen → 422', M.call('rewe_markt_save', {'id': m1['id'], 'hinweis': 'x' * 4001})[0] == 422)
M.call('rewe_markt_save', {'id': m1['id'], 'hinweis': 'nur gereifte Ware\nvorher anrufen'})
st, r = M.call('rewe_notiz_save', {'id': n1['id'], 'erledigt': True})
check('Wiedervorlage erledigt (mit Namen)', st == 200 and r['notiz']['erledigt']['von'] == 'Mark Markt', r)
st, r = M.call('rewe_markt&id=' + m1['id'])
arten = [n['art'] for n in r.get('notizen', [])]
check('Marktakte: Wochen, Notizen und Änderungen (Kaufbereitschaft, Anlage) im Verlauf, Kennzahlen', st == 200 and r['wochen'][ABFRAGE]['status'] == 'bestellt'
      and 'telefonat' in arten and arten.count('system') >= 2 and any('Kaufbereitschaft: Kauft regelmäßig → Gelegentlich' in n['text'] for n in r['notizen']), r.get('notizen'))
check('Marktakte eines fremden Marktes → 404, mit „alle“ sichtbar', M.call('rewe_markt&id=' + m2['id'])[0] == 404 and LE.call('rewe_markt&id=' + m2['id'])[0] == 200)

# ── Zuweisung und Lieferweg ab KW ──
ZW = {'maerkte': [m1['id']], 'ab': kw_plus(ABFRAGE, 1), 'nutzer': ids['evi'], 'lieferweg': SUED}
check('Zuweisen nur mit „verwalten“ (403)', M.call('rewe_zuweisen', ZW)[0] == 403)
for name, b in (('ohne Märkte', {'maerkte': []}), ('KW ungültig', {'ab': 'bald'}), ('Mitarbeiter unbekannt', {'nutzer': 'uzzz'}), ('Lieferweg unbekannt', {'lieferweg': 'lzzz', 'nutzer': None}),
                ('nichts gewählt', {'nutzer': None, 'lieferweg': None})):
    body = {**ZW, **b}
    body = {k: v for k, v in body.items() if v is not None}
    st, r = LE.call('rewe_zuweisen', body)
    check(f'Zuweisen: {name} → 422', st == 422, (st, r))
st, r = LE.call('rewe_zuweisen', ZW)
check('Markt 1 ab nächster Woche zu Evi und Lager Süd', st == 200 and r['geaendert'] == 1, r)
check('Abfragewoche bleibt bei Mark (Lager Nord), Folgewoche bei Evi (Lager Süd)', m1['id'] in [x['id'] for g in M.call('rewe_woche')[1]['woche']['gruppen'] for x in g['maerkte']]
      and m1['id'] not in [x['id'] for g in M.call(f'rewe_woche&kw={kw_plus(ABFRAGE, 1)}')[1]['woche']['gruppen'] for x in g['maerkte']]
      and [(g['name'], [x['id'] for x in g['maerkte']]) for g in E.call(f'rewe_woche&kw={kw_plus(ABFRAGE, 1)}')[1]['woche']['gruppen']] == [('Zentrallager Süd', sorted([m1['id'], m2['id']], key=lambda i: {m1['id']: 'Musterstadt', m2['id']: 'Evistadt'}[i]))])
akte = LE.call('rewe_markt&id=' + m1['id'])[1]
check('Akte: Historie Zuständig und Lieferweg, Verlauf mit Namen, alte Antwort mit altem Schnappschuss', [h['name'] for h in akte['markt']['zustaendigHist']] == ['Mark Markt', 'Evi Eins']
      and [h['name'] for h in akte['markt']['lieferwegHist']] == ['Zentrallager Nord', 'Zentrallager Süd']
      and any('Zuständig Mark Markt → Evi Eins' in n['text'] and 'Lieferweg Zentrallager Nord → Zentrallager Süd' in n['text'] for n in akte['notizen']), akte['markt'])
check('dieselbe Zuweisung noch einmal ändert nichts', LE.call('rewe_zuweisen', ZW)[1]['geaendert'] == 0)

# ── Ruhende Märkte ──
check('Evi setzt Markt 2 auf ruhend', E.call('rewe_markt_save', {'id': m2['id'], 'kauf': 'ruhend'})[0] == 200)
w2 = E.call(f'rewe_woche&kw={kw_plus(ABFRAGE, 2)}')[1]['woche']
check('ruhender Markt nicht in der Abfrage, aber in der eigenen Liste „ruhend“', m2['id'] not in [x['id'] for g in w2['gruppen'] for x in g['maerkte']]
      and [x['id'] for x in w2['ruhend']] == [m2['id']] and w2['ruhend'][0]['darfPflegen'] is True, w2.get('ruhend'))
w2b = E.call('rewe_woche')[1]['woche']
check('mit Antwort in der Woche bleibt er dort in der Abfrage', m2['id'] in [x['id'] for g in w2b['gruppen'] for x in g['maerkte']] and not w2b['ruhend'])

# ── Team und Wochenabschluss ──
check('Wochenabschluss ohne Recht/Team → 403', SA.call('rewe_abschluss')[0] == 403 and M.call('rewe_abschluss')[0] == 403)
check('Team nur mit „verwalten“ (403)', M.call('rewe_team_save', {'team': {}})[0] == 403)
check('Team: unbekannter Mitarbeiter / ohne REWE-Recht → 422', LE.call('rewe_team_save', {'team': {'uzzz': {'alle': True}}})[0] == 422
      and LE.call('rewe_team_save', {'team': {ids['otto']: {'alle': True}}})[0] == 422)
st, r = LE.call('rewe_team_save', {'team': {ids['sabi']: {'export': True}, ids['lea']: {'alle': True}}})
check('Team gespeichert: Sabi Wochenabschluss, Lea alle Listen', st == 200, r)
check('Team wirkt: Sabi sieht den Abschluss, Lea alle Listen (ohne bearbeiten)', SA.call('rewe_abschluss')[0] == 200 and SA.call('rewe_start')[1]['rechte']['exportieren'] is True
      and L.call('rewe_woche&wer=*')[0] == 200 and L.call('rewe_start')[1]['rechte'] == {'bearbeiten': False, 'alle': True, 'verwalten': False, 'exportieren': False}
      and L.call('rewe_antwort', AW)[0] == 403)
pers = {p['name']: p for p in LE.call('rewe_start')[1]['personen']}
check('Mitarbeiterliste zeigt Team und Rechte getrennt', pers['Sabi Summe']['teamExport'] is True and pers['Sabi Summe']['rechtExport'] is False and pers['Lena Leitung']['rechtExport'] is True, pers.get('Sabi Summe'))

st, r = SA.call(f'rewe_abschluss&kw={ABFRAGE}')
ab = r.get('abschluss', {})
pos = [(z['auftrag'], z['lieferweg'], z['kdNr'], z['artikel'], z['menge']) for z in ab.get('zeilen', [])]
check('Abschluss: Einzelaufträge je Markt, Zentrallager vor Direkt, Artikel in Reihenfolge, „Filetkopf extra“ mit der gespeicherten Menge', pos == [(1, 'Zentrallager Nord', '1799001', 'Roastbeef Dry Aged', 2), (1, 'Zentrallager Nord', '1799001', 'Vac. Set', 1),
                                                                                              (2, 'Direktbelieferung', '1799004', 'Roastbeef Dry Aged', 1), (2, 'Direktbelieferung', '1799004', 'Filetkopf extra', 1)], pos)
check('Abschluss: Summen je Lieferweg und Mitarbeiter, Artikel ohne WinAB-Nummer, ohne Kundenstamm', ab['maerkte'] == 2 and [x['name'] for x in ab['lieferwege']] == ['Zentrallager Nord', 'Direktbelieferung']
      and [(x['name'], x['maerkte']) for x in ab['personen']] == [('Mark Markt', 2)] and ab['ohneNr'] == ['Filetkopf extra', 'Vac. Set'] and ab['ohneStamm'] == 2
      and ab['zeilen'][0]['ohneBerechnung'] is True and ab['exportiert'] is None, ab)
check('Abschluss: „in WinAB erfasst“ erst nach dem Excel (422)', SA.call('rewe_erfasst', {'kw': ABFRAGE, 'erfasst': True})[0] == 422)
check('Excel: Woche ohne Bestellung (und ohne fälligen Dauerauftrag) → 422', SA.call('rewe_export', {'kw': kw_plus(ABFRAGE, 9)})[0] == 422)
st, r, roh = SA.call('rewe_export', {'kw': ABFRAGE}, raw=True)
check('Excel erstellt (200, keine JSON-Antwort)', st == 200 and not r, st)
import urllib.request  # noqa: E402  (für die Binärantwort)
req = urllib.request.Request(B + '/api/?action=rewe_export', data=json.dumps({'kw': ABFRAGE}).encode(),
                             headers={'X-Forwarded-For': SA.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': SA.csrf})
antwort = SA.http.open(req)
daten = antwort.read()
check('Excel: Dateiname und Typ', 'REWE_WinAB_' + ABFRAGE.replace('-', '_KW') + '.xlsx' in antwort.headers.get('Content-Disposition', '')
      and antwort.headers.get('Content-Type', '').startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), antwort.headers.get('Content-Disposition'))
wb = load_workbook(io.BytesIO(daten))
ws = wb['WinAB-Erfassung']
kopf = [c.value for c in ws[4]]
zeilen = [[c.value for c in row] for row in ws.iter_rows(min_row=5, max_row=8)]
check('Excel: Blätter und Kopfzeile', wb.sheetnames == ['WinAB-Erfassung', 'Je Lieferweg', 'Je Mitarbeiter'] and kopf[:6] == ['Auftrag', 'Lieferweg', 'Liefer-KW', 'Kd.-Nr. (WinAB)', 'REWE-Markt-Nr.', 'Markt'], kopf)
check('Excel: vier Positionen in zwei Aufträgen, Kd.-Nr. als Zahl, WinAB-Nummer, Menge, ohne Berechnung', [z[0] for z in zeilen] == [1, 1, 2, 2] and zeilen[0][3] == 1799001
      and zeilen[0][9] == '10001' and zeilen[0][11] == 2 and zeilen[0][13] == 'ja' and zeilen[3][10] == 'Filetkopf extra' and zeilen[3][11] == 1, zeilen)
lw_kopf = [c.value for c in wb['Je Lieferweg'][3]][:6]
check('Excel: Spaltenköpfe „Je Lieferweg“ mit „Filetkopf extra“, Mengen wie gespeichert (kein enthaltener Filetkopf dazugerechnet)',
      lw_kopf == ['Lieferweg', 'Märkte', 'Roastbeef Dry Aged', 'Filetkopf extra', 'Vac. Set', None][:len(lw_kopf)]
      and [c.value for c in wb['Je Lieferweg'][5]][:5] == ['Direktbelieferung', 1, 1, 1, 0], (lw_kopf, [[c.value for c in r] for r in wb['Je Lieferweg'].iter_rows(min_row=4, max_row=6)]))
notiz = ws.cell(row=5, column=16)
check('Excel: Notiz „=SUMME(A1)“ bleibt Text (keine Formel)', notiz.value == '=SUMME(A1)' and notiz.data_type == 's', (notiz.value, notiz.data_type))
summen = {row[0].value: row[1].value for row in wb['Je Lieferweg'].iter_rows(min_row=4) if row[0].value}
check('Excel: Je Lieferweg mit Summe', summen.get('Zentrallager Nord') == 1 and summen.get('Direktbelieferung') == 1 and summen.get('Summe') == 2, summen)
ab = SA.call(f'rewe_abschluss&kw={ABFRAGE}')[1]['abschluss']
check('nach dem Export: exportiert mit Name, Zeilen und Stück', ab['exportiert']['von'] == 'Sabi Summe' and ab['exportiert']['zeilen'] == 4 and ab['exportiert']['stueck'] == 5, ab['exportiert'])
st, r = M.call('rewe_antwort', {'markt': m3['id'], 'kw': ABFRAGE, 'status': 'bestellt', 'mengen': {'rb': 1}})
check('Änderung nach dem Export ist ein Nachtrag', st == 200 and r['antwort']['nachtrag'] is True, r)
check('Abschluss zählt den Nachtrag', SA.call(f'rewe_abschluss&kw={ABFRAGE}')[1]['abschluss']['nachtraege'] == 1)
st, r = SA.call('rewe_erfasst', {'kw': ABFRAGE, 'erfasst': True})
check('in WinAB erfasst (mit Name), zurücknehmbar', st == 200 and r['erfasst']['von'] == 'Sabi Summe' and SA.call('rewe_erfasst', {'kw': ABFRAGE, 'erfasst': False})[1]['erfasst'] is None, r)
prot = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Antworten, Dauerauftrag, Zuweisung, Excel, erfasst', all(t in prot for t in ('REWE: REWE Musterstadt, ' + kw_text, 'Daueraufträge für', 'Märkte ab', 'neu zugewiesen',
      'REWE: Excel für WinAB erstellt – ' + kw_text + ', 2 Einzelaufträge, 4 Positionen', 'als in WinAB erfasst markiert')), prot[:400])
check('Protokoll ohne Notizen', 'SUMME' not in prot and 'Möchte ab nächster Woche' not in prot)

# ── Daueraufträge neu (Inhaber 12.11.2026): Rhythmus 6/8, Pause von–bis, Enddatum, Rechte, automatisch zum Bestellschluss ──
# Eigene Testmärkte bei Nina (nicht bei Mark: dessen Märkte zählt die Team-Prüfung weiter unten)
def neuer_markt(ort, kd, dauer=None, **extra):
    b = {'kdNr': kd, 'name': 'REWE ' + ort, 'ort': ort, 'lieferweg': NORD, 'zustaendig': ids['nina'], 'ab': kw_plus(ABSCHLUSS, -3), **extra}
    if dauer:
        b['dauer'] = dauer
    st_, r_ = LE.call('rewe_markt_save', b)
    assert st_ == 200, r_
    return r_['markt']


def wochenmarkt(kw, mid, wer='*'):
    return next((x for g in LE.call(f'rewe_woche&kw={kw}&wer={wer}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == mid), None)


for name, d in (('Rhythmus 5', {'rhythmus': 5, 'mengen': {'rb': 1}, 'ab': ABFRAGE}),
                ('Pause „von“ ohne „bis“', {'rhythmus': 1, 'mengen': {'rb': 1}, 'ab': ABFRAGE, 'pauseVon': kw_plus(ABFRAGE, 1)}),
                ('Pause „von“ nach „bis“', {'rhythmus': 1, 'mengen': {'rb': 1}, 'ab': ABFRAGE, 'pauseVon': kw_plus(ABFRAGE, 3), 'pauseBis': kw_plus(ABFRAGE, 2)}),
                ('Ende vor der ersten Lieferung', {'rhythmus': 1, 'mengen': {'rb': 1}, 'ab': ABFRAGE, 'bis': kw_plus(ABFRAGE, -1)})):
    st, r = LE.call('rewe_markt_save', {'id': m4['id'], 'dauer': d})
    check(f'Dauerauftrag: {name} → 422', st == 422 and r.get('error'), (st, r))
takt = neuer_markt('Taktdorf', '1799011', {'rhythmus': 1, 'mengen': {'rb': 1, 'fk': 1}, 'ab': ABFRAGE, 'pauseVon': kw_plus(ABFRAGE, 1),
                                           'pauseBis': kw_plus(ABFRAGE, 2), 'bis': kw_plus(ABFRAGE, 4)})
check('Dauerauftrag mit geplanter Pause und Ende gespeichert', takt['dauer'] == {'rhythmus': 1, 'mengen': {'rb': 1, 'fk': 1}, 'ab': ABFRAGE, 'pauseBis': kw_plus(ABFRAGE, 2),
      'pauseVon': kw_plus(ABFRAGE, 1), 'bis': kw_plus(ABFRAGE, 4)}, takt['dauer'])
x = wochenmarkt(ABFRAGE, takt['id'])
check('Pause von–bis: Abfragewoche fällig, KW+1 und +2 Pause, +3 geplant (Verlauf voraus)', x['dauerFaellig'] is True and [v['dauer'] for v in x['vorschau']] == [0, 0, 2], x['vorschau'])
x1, x4, x5 = (wochenmarkt(kw_plus(ABFRAGE, i), takt['id']) for i in (1, 4, 5))
check('… in der Pause nicht fällig, nächste Lieferung nach der Pause; Enddatum: KW+4 fällig, danach keine mehr', x1['dauerFaellig'] is False
      and x1['dauerNaechste'] == kw_plus(ABFRAGE, 3) and x4['dauerFaellig'] is True and (x5 is None or (x5['dauerFaellig'] is False and x5['dauerNaechste'] == '')), (x1['dauerNaechste'], x5 and x5['dauerNaechste']))
sechs = neuer_markt('Sechsdorf', '1799012', {'rhythmus': 6, 'mengen': {'rb': 2}, 'ab': ABFRAGE})
check('Rhythmus alle 6 Wochen: Text, fällig in der Abfragewoche und nach 6 Wochen, nicht dazwischen', wochenmarkt(ABFRAGE, sechs['id'])['dauerText'].startswith('Dauerauftrag alle 6 Wochen')
      and wochenmarkt(kw_plus(ABFRAGE, 6), sechs['id'])['dauerFaellig'] is True and wochenmarkt(kw_plus(ABFRAGE, 3), sechs['id'])['dauerNaechste'] == kw_plus(ABFRAGE, 6))
st, r = LE.call('rewe_markt_save', {'id': sechs['id'], 'rev': sechs['rev'], 'dauer': {'rhythmus': 8, 'mengen': {'rb': 2}, 'ab': ABFRAGE}})
check('Rhythmus alle 8 Wochen: nächste Lieferung nach der Abfragewoche in 8 Wochen', st == 200 and r['markt']['dauer']['rhythmus'] == 8
      and wochenmarkt(kw_plus(ABFRAGE, 1), sechs['id'])['dauerNaechste'] == kw_plus(ABFRAGE, 8), r)
check('Rhythmen in rewe_start: 1–4, 6, 8 Wochen, einheitliche Begriffe', {k: v for k, v in LE.call('rewe_start')[1]['rhythmen'].items() if k != '0'}
      == {'1': 'jede Woche', '2': 'alle 2 Wochen', '3': 'alle 3 Wochen', '4': 'alle 4 Wochen', '6': 'alle 6 Wochen', '8': 'alle 8 Wochen'})
roh_m = {m_['id']: m_ for m_ in json.loads(storage_raw('rewe-maerkte').split('?>\n', 1)[-1])['liste']}
check('Speicher nur erweitert: neue Felder nur, wenn gesetzt; ältere Aufträge ohne pauseVon/bis werden mit leeren Werten gelesen',
      set(roh_m[takt['id']]['dauer']) == {'rhythmus', 'mengen', 'ab', 'pauseBis', 'pauseVon', 'bis'} and 'pauseVon' not in roh_m[m4['id']]['dauer']
      and 'bis' not in roh_m[m4['id']]['dauer'] and l4['dauer']['pauseVon'] == '' and l4['dauer']['bis'] == '', roh_m[m4['id']]['dauer'])
# Rechte wie bisher: Verkäufer nur eigene Märkte (fremde wie nicht vorhanden), Leitung alle, nur ansehen gar nicht
DA = {'rhythmus': 1, 'mengen': {'rb': 1}, 'ab': ABFRAGE}
check('Rechte: Verkäufer Dauerauftrag an fremdem Markt → 404, nur ansehen → 403', M.call('rewe_markt_save', {'id': takt['id'], 'dauer': DA})[0] == 404
      and L.call('rewe_markt_save', {'id': takt['id'], 'dauer': DA})[0] == 403)
check('Rechte: Verkäuferin am eigenen Markt (bearbeiten) ok, Leitung an jedem Markt ok', NI.call('rewe_markt_save', {'id': takt['id'], 'dauer': DA})[0] == 200
      and LE.call('rewe_markt_save', {'id': sechs['id'], 'dauer': DA})[0] == 200)

# Automatisch zum Bestellschluss (KW ≤ Abschlusswoche): nur ohne Antwort, idempotent, mit Schnappschuss
W1 = {'rhythmus': 1, 'mengen': {'rb': 2}, 'ab': kw_plus(ABSCHLUSS, -3)}
auto_m = neuer_markt('Autodorf', '1799013', W1)
anders_m = neuer_markt('Andersdorf', '1799014', {**W1, 'mengen': {'rb': 1}})
kein_m = neuer_markt('Keindorf', '1799015', W1)
ruhe_m = neuer_markt('Ruhedorf', '1799016', W1, kauf='ruhend')
check('vor dem Lesen: „Diese Woche anders“ – Andersdorf 3 Stück, Keindorf Kein Bedarf', NI.call('rewe_antwort', {'markt': anders_m['id'], 'kw': ABSCHLUSS, 'status': 'bestellt', 'mengen': {'rb': 3}})[0] == 200
      and NI.call('rewe_antwort', {'markt': kein_m['id'], 'kw': ABSCHLUSS, 'status': 'kein'})[0] == 200)
wa = {x_['id']: x_ for g in LE.call(f'rewe_woche&kw={ABSCHLUSS}&wer=*')[1]['woche']['gruppen'] for x_ in g['maerkte']}
aa = wa[auto_m['id']]['antwort']
check('nach dem Bestellschluss: fälliger Dauerauftrag automatisch bestellt (Herkunft dauer, auto, Schnappschuss Lieferweg/Zuständig)', aa and aa['status'] == 'bestellt'
      and aa['mengen'] == {'rb': 2} and aa['quelle'] == 'dauer' and aa['auto'] is True and aa['von'] == 'automatisch (Dauerauftrag)' and aa['zustaendig'] == 'Nina Neu'
      and aa['lieferweg'] == NORD and LE.call(f'rewe_woche&kw={ABSCHLUSS}')[1]['woche']['bestellschluss'] is True, aa)
check('… ausdrückliche Antworten bleiben (3 Stück, Kein Bedarf), ruhender Markt nicht automatisch', wa[anders_m['id']]['antwort']['mengen'] == {'rb': 3}
      and wa[anders_m['id']]['antwort']['auto'] is False and wa[kein_m['id']]['antwort']['status'] == 'kein' and wa[ruhe_m['id']]['antwort'] is None,
      {k: wa[v['id']]['antwort'] for k, v in (('anders', anders_m), ('kein', kein_m), ('ruhe', ruhe_m))})
st, r = SA.call(f'rewe_abschluss&kw={ABSCHLUSS}')
aa2 = wochenmarkt(ABSCHLUSS, auto_m['id'])['antwort']
check('idempotent: erneutes Lesen und Wochenabschluss schreiben nichts doppelt (gleicher Stand, gleiche Zeit)', st == 200 and aa2['r'] == aa['r'] == 1 and aa2['t'] == aa['t'])
prot = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: genau einmal „automatisch bestellt (Bestellschluss)“ für die Woche', prot.count('für ' + f'KW {int(ABSCHLUSS[5:])}/{ABSCHLUSS[:4]}' + ' automatisch bestellt (Bestellschluss)') == 1, prot[:200])
ab = r['abschluss']
check('Wochenabschluss: automatische Bestellung als „auto“, ruhender Markt als Dauerauftrag ohne Bestellung', any(z['markt'] == 'REWE Autodorf' and z['auto'] for z in ab['zeilen'])
      and ab['auto'] >= 1 and [(x_['ort'], x_['art']) for x_ in ab['dauerOffen']] == [('Ruhedorf', 'ohne')] and ab['bestellschluss'] is True, (ab['dauerOffen'], ab['auto']))
LE.call('rewe_markt_save', {'id': auto_m['id'], 'dauer': {**W1, 'mengen': {'rb': 5}}})
LE.call('rewe_zuweisen', {'maerkte': [auto_m['id']], 'ab': kw_plus(ABSCHLUSS, -3), 'nutzer': ids['evi']})
aa3 = wochenmarkt(ABSCHLUSS, auto_m['id'])['antwort']
check('Schnappschuss (GR-106): spätere Änderung von Menge und Zuständigkeit ändert die abgeschlossene Woche nicht', aa3['mengen'] == {'rb': 2} and aa3['zustaendig'] == 'Nina Neu' and aa3['r'] == 1, aa3)
alt_w = wochenmarkt(kw_plus(ABSCHLUSS, -2), auto_m['id'])
check('ältere Wochen (vor der vorigen Abschlusswoche) bleiben, wie sie waren: keine nachträgliche Bestellung', alt_w['antwort'] is None
      and [x_['art'] for x_ in SA.call(f'rewe_abschluss&kw={kw_plus(ABSCHLUSS, -2)}')[1]['abschluss']['dauerOffen'] if x_['ort'] == 'Autodorf'] == ['ohne'], alt_w['antwort'])
offen_w = wochenmarkt(ABFRAGE, auto_m['id'])
check('vor dem Bestellschluss (Abfragewoche): nichts geschrieben, „wird automatisch bestellt“', offen_w['antwort'] is None and offen_w['dauerFaellig'] is True
      and offen_w['dauerAuto'] is True and LE.call(f'rewe_woche&kw={ABFRAGE}')[1]['woche']['bestellschluss'] is False
      and [x_['art'] for x_ in SA.call(f'rewe_abschluss&kw={ABFRAGE}')[1]['abschluss']['dauerOffen'] if x_['ort'] == 'Autodorf'] == ['geplant'])
KW5 = kw_plus(ABFRAGE, 5)
st, r, roh = SA.call('rewe_export', {'kw': KW5}, raw=True)
check('Excel-Export vor dem Bestellschluss bestellt fällige Daueraufträge spätestens jetzt', st == 200 and wochenmarkt(KW5, auto_m['id'])['antwort']['auto'] is True)
req = urllib.request.Request(B + '/api/?action=rewe_export', data=json.dumps({'kw': ABSCHLUSS}).encode(),
                             headers={'X-Forwarded-For': SA.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': SA.csrf})
ws = load_workbook(io.BytesIO(SA.http.open(req).read()))['WinAB-Erfassung']
xl = {(row[5].value, row[17].value) for row in ws.iter_rows(min_row=5) if row[5].value and row[0].value}
check('Excel enthält die automatischen Bestellungen (Spalte „Dauerauftrag“: automatisch), ausdrückliche ohne Vermerk', ws.cell(row=4, column=18).value == 'Dauerauftrag'
      and ('REWE Autodorf', 'automatisch') in xl and ('REWE Andersdorf', None) in xl and not any(m_ == 'REWE Ruhedorf' for m_, _ in xl), xl)
# Testmärkte wieder ohne Dauerauftrag (die folgenden Prüfungen zählen Märkte und Wochen)
for mm in (takt, sechs, auto_m, anders_m, kein_m, ruhe_m):
    LE.call('rewe_markt_save', {'id': mm['id'], 'dauer': {'rhythmus': 0}, 'kauf': 'ausgelistet'})

# ── Team: Mitarbeiter hinzufügen und entfernen (Wunsch des Inhabers 11.11.2026) ──
def namen(liste):
    return {p['name'] for p in liste}


def person(name, liste=None):
    return next((p for p in (liste if liste is not None else LE.call('rewe_start')[1]['personen']) if p['name'] == name), {})


def stamm_roh():
    return json.loads(storage_raw('rewe-stamm').split('?>\n', 1)[-1])


st, d = LE.call('rewe_start')
check('Hinzufügen: Auswahl = aktive Mitarbeiter mit Modulzugang, noch nicht im Team (ohne Modulzugang oder mit Verbot nicht)',
      st == 200 and {'Otto Ohne', 'Pia Plus'} <= namen(d['kandidaten']) and not ({'Udo Ohnezugang', 'Vera Verbot', 'Mark Markt', 'Lena Leitung'} & namen(d['kandidaten']))
      and 'Pia Plus' not in namen(d['personen']), (namen(d['kandidaten']), namen(d['personen'])))
check('Auswahl nur mit „verwalten“', M.call('rewe_start')[1]['kandidaten'] == [] and L.call('rewe_start')[1]['kandidaten'] == [])
check('Hinzufügen/Entfernen ohne „verwalten“ → 403', M.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})[0] == 403 and L.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})[0] == 403
      and PI.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})[0] == 403 and M.call('rewe_team_entfernen', {'nutzer': ids['sabi']})[0] == 403)
csrf = LE.csrf; LE.csrf = ''
check('Hinzufügen ohne CSRF: 403', LE.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})[0] == 403)
LE.csrf = csrf
check('Hinzufügen/Entfernen per GET: 405', LE.call('rewe_team_ergaenzen')[0] == 405 and LE.call('rewe_team_entfernen')[0] == 405)
check('vor dem Hinzufügen: Pia ohne REWE-Recht 403, Zuweisen an Pia 422 (nicht im Team)', PI.call('rewe_start')[0] == 403
      and LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': ABFRAGE, 'nutzer': ids['pia']})[0] == 422)
for name, b in (('unbekannt', {'nutzer': 'uzzz'}), ('ohne Angabe', {}), ('ohne Modulzugang', {'nutzer': ids['udo']}), ('Verbot „REWE ansehen“', {'nutzer': ids['vera']}),
                ('schon im Team', {'nutzer': ids['mark']})):
    st, r = LE.call('rewe_team_ergaenzen', b)
    check(f'Hinzufügen: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = LE.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})
pia = person('Pia Plus', r.get('personen', []))
check('Pia hinzugefügt: in der Liste (ergänzt, bearbeiten, ohne Rollenrecht, 0 Märkte), nicht mehr in der Auswahl', st == 200 and pia.get('ergaenzt') is True
      and pia['bearbeiten'] is True and pia['rechtSehen'] is False and pia['maerkte'] == 0 and pia['alle'] is False and 'Pia Plus' not in namen(r['kandidaten']), r)
check('Pia: Start mit „bearbeiten“, keine weiteren Rechte, andere Listen 403', PI.call('rewe_start')[1]['rechte'] == {'bearbeiten': True, 'alle': False, 'verwalten': False, 'exportieren': False}
      and PI.call('rewe_woche&wer=*')[0] == 403 and PI.call('rewe_abschluss')[0] == 403)
st, r = LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': ABFRAGE, 'nutzer': ids['pia']})
check('Markt 3 ab Abfragewoche an Pia (jetzt in der Personenauswahl)', st == 200 and r['geaendert'] == 1, r)
w = PI.call('rewe_woche')[1]['woche']
check('Pia sieht ihren Markt (Woche, Märkte, Akte) und darf antworten; fremde Märkte wie nicht vorhanden (404)', [x['id'] for g in w['gruppen'] for x in g['maerkte']] == [m3['id']]
      and w['gruppen'][0]['maerkte'][0]['darfAntworten'] is True and [m['id'] for m in PI.call('rewe_maerkte')[1]['maerkte']] == [m3['id']]
      and PI.call('rewe_markt&id=' + m3['id'])[0] == 200 and PI.call('rewe_markt&id=' + m1['id'])[0] == 404, w.get('gruppen'))
KW1 = kw_plus(ABFRAGE, 1)
st, r = PI.call('rewe_antwort', {'markt': m3['id'], 'kw': KW1, 'status': 'bestellt', 'mengen': {'rb': 1}})
check('Pia speichert eine Antwort (Schnappschuss Zuständig Pia)', st == 200 and r['antwort']['zustaendig'] == 'Pia Plus' and r['antwort']['von'] == 'Pia Plus', r)
check('Pia: fremder Markt → 404; Notiz und Abfragetag am eigenen Markt ok, Stammfelder 403',
      PI.call('rewe_antwort', {'markt': m2['id'], 'kw': KW1, 'status': 'kein'})[0] == 404 and PI.call('rewe_notiz_save', {'markt': m3['id'], 'art': 'telefonat', 'text': 'Rückruf am Montag'})[0] == 200
      and PI.call('rewe_markt_save', {'id': m3['id'], 'abfragetag': 'di'})[0] == 200 and PI.call('rewe_markt_save', {'id': m3['id'], 'ort': 'Woanders'})[0] == 403)
st, r = LE.call('rewe_team_entfernen', {'nutzer': ids['pia']})
check('Entfernen mit Markt → 422 „erst den Markt umverteilen“', st == 422 and 'erst den Markt umverteilen' in r.get('error', ''), (st, r))
mk = person('Mark Markt')
st, r = LE.call('rewe_team_entfernen', {'nutzer': ids['mark']})
check('Mark mit 2 Märkten → 422 „erst die 2 Märkte umverteilen“, bleibt im Team', st == 422 and mk['maerkte'] == 2 and 'erst die 2 Märkte umverteilen' in r.get('error', '')
      and person('Mark Markt'), (mk.get('maerkte'), r))
LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': KW1, 'nutzer': ids['mark']})
check('Markt ab KW+1 zurück an Mark: Pia ist in der Abfragewoche noch zuständig → 422', LE.call('rewe_team_entfernen', {'nutzer': ids['pia']})[0] == 422)
LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': ABFRAGE, 'nutzer': ids['mark']})
LE.call('rewe_zuweisen', {'maerkte': [m2['id']], 'ab': kw_plus(ABFRAGE, 3), 'nutzer': ids['pia']})
check('künftige Zuständigkeit (ab KW+3) zählt mit → 422, Zahl 1', LE.call('rewe_team_entfernen', {'nutzer': ids['pia']})[0] == 422 and person('Pia Plus')['maerkte'] == 1)
LE.call('rewe_zuweisen', {'maerkte': [m2['id']], 'ab': kw_plus(ABFRAGE, 3), 'nutzer': ids['evi']})
st, r = LE.call('rewe_team_entfernen', {'nutzer': ids['pia']})
check('Pia ohne Märkte entfernt: nicht mehr in der Liste, wieder in der Auswahl', st == 200 and 'Pia Plus' not in namen(r['personen']) and 'Pia Plus' in namen(r['kandidaten']), r)
check('ehemals Ergänzte ohne Recht verliert den Inhaltszugang (403)', PI.call('rewe_start')[0] == 403 and PI.call('rewe_woche')[0] == 403 and PI.call('rewe_markt&id=' + m3['id'])[0] == 403
      and PI.call('rewe_antwort', {'markt': m3['id'], 'kw': KW1, 'status': 'kein'})[0] == 403)
check('Zuweisen an die Entfernte → 422', LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': ABFRAGE, 'nutzer': ids['pia']})[0] == 422)
akte = LE.call('rewe_markt&id=' + m3['id'])[1]
aw = next(x for g in M.call(f'rewe_woche&kw={KW1}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['id'] == m3['id'])['antwort']
check('Schnappschuss und Verlauf bleiben (GR-106): Antwort KW+1 von Pia mit Zuständig Pia, Zuweisung im Verlauf', aw['von'] == 'Pia Plus' and aw['zustaendig'] == 'Pia Plus'
      and akte['wochen'][KW1]['von'] == 'Pia Plus' and any('Mark Markt → Pia Plus' in n['text'] for n in akte['notizen']), (aw, akte['wochen'].get(KW1)))
# Rollen-Inhaberin („REWE ansehen“ über die Rolle) wird nur ausgeblendet; erneutes Hinzufügen hebt das auf
st, r = LE.call('rewe_team_entfernen', {'nutzer': ids['lea']})
check('Lea (Recht über die Rolle) ausgeblendet: nicht in der Liste, in der Auswahl', st == 200 and 'Lea Lesen' not in namen(r['personen'])
      and person('Lea Lesen', r['kandidaten']).get('rechtSehen') is True, r)
check('… Rechte der Rolle bleiben (Start 200), Team „alle Listen“ entfällt, Zuweisen und Team speichern 422', L.call('rewe_start')[0] == 200 and L.call('rewe_start')[1]['rechte']['alle'] is False
      and L.call('rewe_woche&wer=*')[0] == 403 and LE.call('rewe_zuweisen', {'maerkte': [m3['id']], 'ab': ABFRAGE, 'nutzer': ids['lea']})[0] == 422
      and LE.call('rewe_team_save', {'team': {ids['lea']: {'alle': True}}})[0] == 422)
st, r = LE.call('rewe_team_ergaenzen', {'nutzer': ids['lea']})
lea = person('Lea Lesen', r.get('personen', []))
check('Lea erneut hinzugefügt: wieder in der Liste, nicht „ergänzt“ (Recht der Rolle), bleibt bei „nur ansehen“', st == 200 and lea.get('ergaenzt') is False and lea['bearbeiten'] is False
      and lea['rechtSehen'] is True and L.call('rewe_start')[1]['rechte']['bearbeiten'] is False, r)
st, r = LE.call('rewe_team_ergaenzen', {'nutzer': ids['pia']})
roh = stamm_roh()
check('Pia erneut hinzugefügt; gespeichert als Listen von Nutzer-IDs (mitglieder, ausgeblendet)', st == 200 and roh['mitglieder'] == [ids['pia']] and roh['ausgeblendet'] == []
      and PI.call('rewe_start')[0] == 200, roh)
# Rückfall: Daten ohne die neuen Felder (wie vor dieser Fassung) werden gelesen – Ergänzte fehlen dann, alles andere bleibt
storage_write('rewe-stamm', {k: v for k, v in roh.items() if k not in ('mitglieder', 'ausgeblendet')})
d = LE.call('rewe_start')[1]
check('alte Daten ohne mitglieder/ausgeblendet: Start ok, Rollen-Inhaber und Team wie bisher, Ergänzte nicht im Team (403)', 'Pia Plus' not in namen(d['personen'])
      and {'Mark Markt', 'Lea Lesen', 'Sabi Summe'} <= namen(d['personen']) and person('Sabi Summe', d['personen'])['teamExport'] is True
      and 'Pia Plus' in namen(d['kandidaten']) and PI.call('rewe_start')[0] == 403, namen(d['personen']))
storage_write('rewe-stamm', roh)
st, r = LE.call('rewe_team_save', {'team': {ids['sabi']: {'export': True}, ids['lea']: {'alle': True}}})
check('Team speichern behält die neuen Felder; Pia wieder im Team', st == 200 and stamm_roh()['mitglieder'] == [ids['pia']] and PI.call('rewe_start')[0] == 200
      and person('Lea Lesen')['teamAlle'] is True, stamm_roh())
prot = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Hinzufügen und Entfernen mit Namen', all(t in prot for t in ('REWE: Pia Plus ins Team aufgenommen (eigene Märkte ansehen und bearbeiten)', 'REWE: Pia Plus aus dem Team entfernt',
      'REWE: Lea Lesen aus dem Team entfernt (ausgeblendet, Rechte der Rolle bleiben)', 'REWE: Lea Lesen ins Team aufgenommen (wieder eingeblendet)')), prot[:300])

# ── Datenpaket ──
anzahl_maerkte = len(LE.call('rewe_maerkte')[1]['maerkte'])
check('Datenpaket nur mit „verwalten“ (403)', M.call('rewe_import', {'paket': PAKET, 'vorschau': True})[0] == 403)
st, r = LE.call('rewe_import', {'paket': {'format': 'falsch'}, 'vorschau': True})
check('falsches Format: Fehler', st == 200 and r['fehler'] and not r['zahlen'], r)
kaputt = json.loads(json.dumps(PAKET))
kaputt['maerkte'][1]['lieferweg'][0]['id'] = 'gibtsnicht'
kaputt['maerkte'][2]['kdNr'] = kaputt['maerkte'][0]['kdNr']
kaputt['maerkte'][3]['wochen'] = {'2026-05': {'s': 'bestellt', 'm': {}}}
st, r = LE.call('rewe_import', {'paket': kaputt, 'vorschau': True})
check('Vorschau mit Fehlern je Markt (Lieferweg, Kd.-Nr. doppelt, bestellt ohne Menge)', st == 200 and len(r['fehler']) == 3 and 'Musterdorf' in r['fehler'][0]
      and 'doppelt' in r['fehler'][1] and 'ohne Menge' in r['fehler'][2], r['fehler'])
check('mit Fehlern nichts übernommen (422)', LE.call('rewe_import', {'paket': kaputt, 'ersetzen': True})[0] == 422)
zu = {'Liste A': ids['mark'], 'Liste B': ids['evi']}
st, r = LE.call('rewe_import', {'paket': PAKET, 'zuordnung': zu, 'vorschau': True})
check('Vorschau: Zahlen, Listen, nicht leer', st == 200 and r['zahlen']['maerkte'] == 4 and r['zahlen']['antworten'] == 11 and r['zahlen']['bestellungen'] == 6
      and r['zahlen']['stueck'] == 8 and r['zahlen']['dauerauftraege'] == 1 and r['listen'] == {'Liste A': 2, 'Liste B': 2, 'Liste C': 1} and r['leer'] is False and not r['fehler'], r)
check('Vorschau schreibt nichts', len(LE.call('rewe_maerkte')[1]['maerkte']) == anzahl_maerkte)
check('Liste einem Mitarbeiter ohne „REWE ansehen“ zuordnen → Fehler', LE.call('rewe_import', {'paket': PAKET, 'zuordnung': {'Liste A': ids['otto']}, 'vorschau': True})[1]['fehler'])
check('Liste einer im Modul ergänzten Mitarbeiterin zuordnen → ohne Fehler', LE.call('rewe_import', {'paket': PAKET, 'zuordnung': {'Liste A': ids['pia']}, 'vorschau': True})[1]['fehler'] == [])
check('nicht leer ohne „ersetzen“ → 409', LE.call('rewe_import', {'paket': PAKET, 'zuordnung': zu})[0] == 409)
st, r = LE.call('rewe_import', {'paket': PAKET, 'zuordnung': zu, 'ersetzen': True})
check('Datenpaket übernommen (ersetzt)', st == 200 and r['zahlen']['maerkte'] == 4, r)
d = LE.call('rewe_start')[1]
check('Lieferwege aus dem Paket (mit Direkt), Team bleibt', [x['id'] for x in d['lieferwege']] == ['nordlager', 'suedlager', 'direkt']
      and next(p for p in d['personen'] if p['name'] == 'Sabi Summe')['teamExport'] is True, d['lieferwege'])
check('Datenpaket „ersetzen“ behält ergänzte Mitarbeiter (Pia im Team)', person('Pia Plus', d['personen']).get('ergaenzt') is True and stamm_roh()['mitglieder'] == [ids['pia']])
maerkte = {m['ort']: m for m in LE.call('rewe_maerkte')[1]['maerkte']}
check('Märkte: Zuständigkeit aus den Listen (Liste C → niemand), Kaufbereitschaft, Name fehlt → „REWE <Ort>“', maerkte['Beispielstadt']['zustaendigName'] == 'Mark Markt'
      and maerkte['Neustadt']['zustaendigName'] == '' and maerkte['Stillhausen']['kauf'] == 'ruhend' and maerkte['Musterdorf']['name'] == 'REWE Musterdorf',
      {o: (x['zustaendigName'], x['kauf'], x['name']) for o, x in maerkte.items()})
wa = M.call(f'rewe_woche&kw=2026-43')[1]['woche']
check('Lagerwechsel KW 42: Musterdorf ab KW 42 bei Mark über Lager Nord', [(g['id'], [x['ort'] for x in g['maerkte']]) for g in wa['gruppen']] == [('nordlager', ['Beispielstadt', 'Musterdorf'])], wa['gruppen'])
ev = E.call('rewe_woche&kw=2026-41')
check('vor KW 42 bei Evi über Lager Süd', [(g['id'], [x['ort'] for x in g['maerkte']]) for g in ev[1]['woche']['gruppen']] == [('suedlager', ['Musterdorf'])], ev)
akte = M.call('rewe_markt&id=' + maerkte['Beispielstadt']['id'])[1]
check('Akte: Verlauf über zwei Jahre, Kennzahlen, Notiz aus Excel, Herkunft Excel', akte['wochen']['2025-50']['status'] == 'bestellt' and akte['wochen']['2026-06']['status'] == 'pause'
      and akte['zahlen']['2026']['lieferungen'] == 2 and akte['zahlen']['2026']['mengen'] == {'rb': 3, 'fk': 1} and akte['notizen'][0]['q'] == 'datenpaket'
      and akte['wochen']['2026-04']['quelle'] == 'excel', akte['zahlen'])
ev = E.call('rewe_woche')[1]['woche']
check('Ruhend: Stillhausen in Evis Liste „ruhend“ mit letzter Bestellung', [(x['ort'], x['letzte']) for x in ev['ruhend']] == [('Stillhausen', '2024-10')], (ev['ruhend'], [[x['ort'] for x in g['maerkte']] for g in ev['gruppen']]))
a43, a44 = (SA.call(f'rewe_abschluss&kw={k}')[1]['abschluss'] for k in ('2026-43', '2026-44'))
check('Abschluss: ohne Antwort nur abzufragende Märkte (ruhend und nicht fälliger Dauerauftrag zählen nicht), fälliger Dauerauftrag als Hinweis',
      [x['ort'] for x in a43['offen']] == ['Musterdorf', 'Neustadt'] and a43['dauerOffen'] == [] and [x['ort'] for x in a44['dauerOffen']] == ['Beispielstadt']
      and 'Beispielstadt' not in [x['ort'] for x in a44['offen']], ([x['ort'] for x in a43['offen']], a43['dauerOffen'], a44['dauerOffen']))
check('ohne Zuständigkeit: niemandem außer „alle“ sichtbar', LE.call('rewe_markt&id=' + maerkte['Neustadt']['id'])[0] == 200 and M.call('rewe_markt&id=' + maerkte['Neustadt']['id'])[0] == 404)

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ')

    def warte_auf(pg, js, ms=8000):   # auf einen Zustand warten; False statt Abbruch, damit die Prüfung den Fehler meldet
        try:
            pg.wait_for_function(js, timeout=ms)
            return True
        except Exception:
            return False

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900, ziel='#rw-app:not([hidden])', pfad='/module/rewe/'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + pfad); pg.wait_for_selector(ziel)
        return ctx, pg

    WOCHE = '2026-43'
    ctx, pg = anmelden('mark', 'Laden-Konto-22', '198.51.100.11', pfad=f'/module/rewe/#woche/{WOCHE}')
    pg.wait_for_selector('.rw-gruppe')
    check('Meine Woche: Adresse #woche/<KW>, Titel, Gruppe Lager Nord, nur Mark-Reiter', pg.url.endswith('#woche/' + WOCHE) and 'KW 43' in text(pg, '#rw-w-titel')
          and 'Zentrallager Nordheim' in text(pg, '#rw-w-gruppen') and pg.is_hidden('#rw-tabs [data-tab="zuweisung"]') and pg.is_hidden('#rw-tabs [data-tab="abschluss"]'))
    # Filter „Offen“ (Standard): nach „Bestellt“ bleibt die Zeile mit den Mengen stehen; Übersicht der Bestellungen
    zeile = '.rw-zeile:has-text("Musterdorf")'
    check('Filter „Offen“: nur offene Märkte (Musterdorf), keine Bestellübersicht', pg.locator('.rw-zeile').count() == 1 and pg.is_visible(zeile) and pg.is_hidden('#rw-w-bestellt'))
    pg.click(f'{zeile} [data-s="bestellt"]'); pg.wait_for_selector(f'{zeile} [data-menge="rb"]')
    check('„Bestellt“ im Filter „Offen“: Zeile bleibt mit Mengen stehen (markiert), 1 Roastbeef vorgeschlagen',
          pg.is_visible(f'{zeile}.gerade') and pg.locator(f'{zeile} .rw-mzahl').first.input_value() == '1')
    pg.click(f'{zeile} [data-menge="rb"][data-d="1"]')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('.rw-mzahl').value === '2' && !z.querySelector('[data-s][disabled]'))")
    check('Menge erhöht, Zeile weiter sichtbar', pg.is_visible(zeile))
    # Filetkopf extra: Beschriftung und Hinweis an der Mengeneingabe, Texte mit „Filetkopf extra“, Mengen wie eingegeben
    fk = f'{zeile} .rw-menge.extra'
    check('Mengeneingabe: „Filetkopf extra“ mit Hinweis „zusätzlich – 1 Filetkopf ist bei jedem Roastbeef Dry Aged schon dabei“ (nur dort)',
          pg.locator(fk).count() == 1 and 'Filetkopf extra' in text(pg, fk) and 'zusätzlich – 1 Filetkopf ist bei jedem Roastbeef Dry Aged schon dabei' in text(pg, fk)
          and pg.locator(f'{zeile} .rw-mextra').count() == 1 and pg.get_attribute(f'{fk} .rw-mzahl', 'aria-label') == 'Filetkopf extra: Menge', text(pg, f'{zeile} .rw-mengen-eingabe'))
    pg.click(f'{zeile} [data-menge="fk"][data-d="1"]')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('[data-mzahl=\"fk\"]') && z.querySelector('[data-mzahl=\"fk\"]').value === '1' && !z.querySelector('[data-s][disabled]'))")
    warte_auf(pg, "document.querySelector('#rw-w-kpis').innerText.includes('Filetkopf extra') && !!document.querySelector('#rw-w-bestellt summary')")
    aw = next(x for g in M.call(f'rewe_woche&kw={WOCHE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Musterdorf')['antwort']
    check('Kennzahl „Bestellt“ und „Bestellungen KW 43“: „2 Roastbeef Dry Aged + 1 Filetkopf extra“; gespeichert genau 1 Filetkopf (nichts dazugerechnet)',
          '2 Roastbeef Dry Aged + 1 Filetkopf extra' in text(pg, '#rw-w-kpis') and '2 Roastbeef Dry Aged + 1 Filetkopf extra' in text(pg, '#rw-w-bestellt summary')
          and aw['mengen'] == {'rb': 2, 'fk': 1}, (text(pg, '#rw-w-kpis'), aw))
    pg.click(f'{zeile} [data-menge="fk"][data-d="-1"]')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('[data-mzahl=\"fk\"]') && z.querySelector('[data-mzahl=\"fk\"]').value === '0' && !z.querySelector('[data-s][disabled]'))")
    pg.wait_for_selector('#rw-w-bestellt summary')
    check('Übersicht „Bestellungen“ ist zugeklappt (Voreinstellung)', not pg.evaluate("document.querySelector('#rw-w-bestellt details').open") and pg.is_hidden('#rw-w-bestellt .rw-beintrag'))
    pg.click('#rw-w-bestellt summary'); pg.wait_for_selector('#rw-w-bestellt .rw-beintrag')
    check('Übersicht „Bestellungen KW 43“: Markt, Lieferweg, Mengen, Summe', 'Bestellungen KW 43' in text(pg, '#rw-w-bestellt summary')
          and '1 Markt · 2 Roastbeef Dry Aged' in text(pg, '#rw-w-bestellt summary')
          and 'Musterdorf' in text(pg, '#rw-w-bestellt .rw-beintrag') and 'Zentrallager Nordheim' in text(pg, '#rw-w-bestellt .rw-beintrag')
          and '2 Roastbeef Dry Aged' in text(pg, '#rw-w-bestellt .rw-beintrag'), text(pg, '#rw-w-bestellt'))
    pg.screenshot(path=os.path.join(SH, 'rewe_woche_bestellt_1280.png'), full_page=True)
    pg.click('#rw-w-filter [data-f="offen"]'); pg.wait_for_selector(zeile, state='detached')
    check('Filter neu gewählt: erledigter Markt verschwindet, Übersicht bleibt', 'Alle Märkte dieser Gruppe sind erledigt' in text(pg, '#rw-w-gruppen') and pg.is_visible('#rw-w-bestellt .rw-beintrag'))
    pg.click('#rw-w-bestellt [data-zeige]'); pg.wait_for_selector(f'{zeile} [data-menge="rb"]')
    check('Klick in der Übersicht zeigt die Zeile wieder (zum Ändern)', pg.is_visible(zeile))
    pg.click('#rw-w-bestellt summary'); pg.wait_for_function("!document.querySelector('#rw-w-bestellt details').open")
    pg.click(f'{zeile} [data-menge="rb"][data-d="-1"]')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('.rw-mzahl').value === '1' && !z.querySelector('[data-s][disabled]'))")
    check('Übersicht bleibt zugeklappt, Summe aktuell', not pg.evaluate("document.querySelector('#rw-w-bestellt details').open") and '1 Roastbeef Dry Aged' in text(pg, '#rw-w-bestellt summary'))
    pg.click('#rw-w-bestellt summary')
    pg.click('#rw-w-filter [data-f="alle"]')
    zeile = '.rw-zeile:has-text("Musterdorf")'
    pg.click(f'{zeile} [data-s="kein"]'); pg.wait_for_selector(f'{zeile} [data-s="kein"][aria-pressed="true"]')
    pg.click(f'{zeile} [data-s="bestellt"]'); pg.wait_for_selector(f'{zeile} [data-menge="rb"]')
    pg.click(f'{zeile} [data-menge="rb"][data-d="1"]'); pg.wait_for_function("document.querySelector('.rw-zeile[data-id] .rw-mzahl') && [...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('.rw-mzahl') && z.querySelector('.rw-mzahl').value === '2')")
    pg.fill(f'{zeile} [data-notiz]', 'Kunde ruft zurück'); pg.press(f'{zeile} [data-notiz]', 'Tab')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('[data-notiz]') && z.querySelector('[data-notiz]').value === 'Kunde ruft zurück' && !z.querySelector('[data-s][disabled]'))")
    aw = next(x for g in M.call(f'rewe_woche&kw={WOCHE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Musterdorf')['antwort']
    check('Antwort per Klick: bestellt, 2 Roastbeef, Notiz gespeichert', aw['status'] == 'bestellt' and aw['mengen'] == {'rb': 2} and aw['notiz'] == 'Kunde ruft zurück', aw)
    # Versehentlich geklickt: der Hinweis bietet „Rückgängig“ an und stellt die vorige Antwort samt Mengen und Notiz wieder her
    # auf den neuen Hinweis warten – der vorige („Bestellt · …“) kann noch sichtbar sein, bis die Antwort gespeichert ist
    pg.click(f'{zeile} [data-s="kein"]')
    pg.wait_for_function("(() => { const t = document.querySelector('#rw-toast.zeigen'); return !!t && !!t.querySelector('[data-rueck]') && t.textContent.replace(/\\u00a0/g, ' ').includes('Musterdorf: Kein Bedarf'); })()")
    check('Antwort geändert → Hinweis mit „Rückgängig“', 'Musterdorf: Kein Bedarf' in text(pg, '#rw-toast'), text(pg, '#rw-toast'))
    pg.screenshot(path=os.path.join(SH, 'rewe_rueckgaengig_1280.png'))
    pg.click('#rw-toast [data-rueck]')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('[data-s=\"bestellt\"][aria-pressed=\"true\"]') && z.querySelector('.rw-mzahl') && z.querySelector('.rw-mzahl').value === '2' && !z.querySelector('[data-s][disabled]'))")
    aw = next(x for g in M.call(f'rewe_woche&kw={WOCHE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Musterdorf')['antwort']
    check('„Rückgängig“: wieder bestellt, 2 Roastbeef, Notiz erhalten', aw['status'] == 'bestellt' and aw['mengen'] == {'rb': 2} and aw['notiz'] == 'Kunde ruft zurück', aw)
    kws = pg.locator(f'{zeile} .rw-zw span').all_inner_texts()
    check('Verlauf: acht Wochen, diese Woche (Ring) und drei Wochen voraus mit KW-Zahlen, Legende', pg.locator(f'{zeile} .rw-z').count() == 12
          and kws == [str(i) for i in range(35, 47)] and pg.locator(f'{zeile} .rw-z.jetzt').count() == 1 and pg.locator(f'{zeile} button[data-vor]').count() == 3
          and pg.is_visible('.rw-legende'), kws)
    check('Markt groß: Name, Adresse und Kd.-Nr. (Schrift ≥ 14 px)', pg.evaluate(f"(() => {{ const z = [...document.querySelectorAll('.rw-zeile')].find(x => x.textContent.includes('Musterdorf')); return parseFloat(getComputedStyle(z.querySelector('.rw-mname')).fontSize) >= 18 && parseFloat(getComputedStyle(z.querySelector('.rw-madresse') || z.querySelector('.rw-mkd')).fontSize) >= 14; }})()"))
    # Marktkarte: Klick auf den Namen; Hinweis speichert von selbst, Notiz mit Art, Escape schließt
    pg.click(f'{zeile} .rw-mname'); pg.wait_for_selector('#dlg-karte[open] #kt-hinweis')
    check('Marktkarte: Name, Reiter Notizen/Verlauf/Wiedervorlagen, Hinweis, Ansprechpartner, Dauerauftrag', 'Musterdorf' in text(pg, '#kt-titel')
          and pg.locator('#dlg-karte [data-kreiter]').count() == 3 and pg.is_visible('#kt-ntext') and 'Ansprechpartner' in text(pg, '#dlg-karte') and 'Dauerauftrag' in text(pg, '#dlg-karte'))
    pg.click('#dlg-karte [data-kdauer]'); pg.wait_for_selector('#dlg-dauer[open] #dd-titel:has-text("Musterdorf")')
    check('Pop-up aus der Marktkarte: „Neuer Dauerauftrag · Musterdorf“ über der Karte', 'Neuer Dauerauftrag' in text(pg, '#dd-titel') and pg.is_visible('#dlg-karte[open]'))
    pg.click('#dlg-dauer .rw-ddfuss [data-dd-zu]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
    pg.fill('#kt-hinweis', 'Nur donnerstags anrufen\nAnlieferung über die Rampe')
    pg.wait_for_function("document.querySelector('#kt-hstatus').textContent.includes('gespeichert') && !document.querySelector('#kt-hstatus').textContent.includes('noch nicht')", timeout=8000)
    mid = next(x['id'] for g in M.call(f'rewe_woche&kw={WOCHE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Musterdorf')
    check('Hinweis automatisch gespeichert (mehrzeilig)', M.call('rewe_markt&id=' + mid)[1]['markt']['hinweis'] == 'Nur donnerstags anrufen\nAnlieferung über die Rampe')
    pg.click('#dlg-karte [data-kart="telefonat"]'); pg.fill('#kt-ntext', 'Will ab KW 45 zwei Stück')
    pg.click('#kt-nsave'); pg.wait_for_selector('#dlg-karte .rw-verlaufsliste li:has-text("Will ab KW 45 zwei Stück")')
    check('Notiz in der Marktkarte (Telefonat), Feld wieder leer', 'Telefonat' in text(pg, '#dlg-karte .rw-verlaufsliste') and pg.input_value('#kt-ntext') == ''
          and 'Notizen · 1' in text(pg, '#dlg-karte [data-kreiter="notizen"]'))
    pg.click('#dlg-karte [data-kreiter="verlauf"]'); pg.wait_for_selector('#dlg-karte [data-kpanel="verlauf"]:not([hidden]) .rw-heat')
    check('Marktkarte: Reiter „Verlauf der Wochen“ mit Jahresraster', pg.is_hidden('#dlg-karte [data-kpanel="notizen"]'))
    pg.screenshot(path=os.path.join(SH, 'rewe_marktkarte_1280.png'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-karte', state='hidden')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('.rw-mhinweis') && z.querySelector('.rw-mhinweis').textContent.includes('1 Notiz'))")
    check('Wochenliste: Hinweis unter der Adresse mit Zahl der Notizen', 'Nur donnerstags anrufen' in text(pg, f'{zeile} .rw-mhinweis'))
    # Vorbestellung: Klick auf eine künftige Woche im Verlauf öffnet diese Woche mit der Zeile
    naechste = kw_plus(WOCHE, 1)
    pg.click(f'{zeile} button[data-vor="{naechste}"]')
    pg.wait_for_function(f"location.hash === '#woche/{naechste}' && document.querySelector('#rw-w-titel').textContent.includes('KW {int(naechste[5:])}')")
    pg.wait_for_selector(f'{zeile} [data-s="bestellt"]')
    pg.click(f'{zeile} [data-s="bestellt"]'); pg.wait_for_selector(f'{zeile} .rw-mzahl')
    pg.fill(f'{zeile} .rw-mzahl >> nth=0', '3'); pg.press(f'{zeile} .rw-mzahl >> nth=0', 'Enter')
    pg.wait_for_function("[...document.querySelectorAll('.rw-zeile')].some(z => z.textContent.includes('Musterdorf') && z.querySelector('.rw-mzahl') && z.querySelector('.rw-mzahl').value === '3' && !z.querySelector('[data-s][disabled]'))")
    vb = next(x for g in M.call(f'rewe_woche&kw={naechste}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Musterdorf')['antwort']
    check('Menge eingetippt (3) und gespeichert', vb['status'] == 'bestellt' and vb['mengen'] == {'rb': 3}, vb)
    pg.click('#rw-w-zurueck'); pg.wait_for_function(f"location.hash === '#woche/{WOCHE}'")
    pg.wait_for_selector(f'{zeile} .rw-z.b.vor')
    check('Zurück in KW 43: Vorbestellung KW 44 im Verlauf (3) und im Text', pg.inner_text(f'{zeile} .rw-z.vor') == '3' and f'vorbestellt KW {int(naechste[5:])}: 3' in text(pg, f'{zeile} .rw-vtext'), text(pg, f'{zeile} .rw-vtext'))
    pg.screenshot(path=os.path.join(SH, 'rewe_woche_1280.png'), full_page=True)
    pg.click('#rw-w-heute'); pg.wait_for_function(f"location.hash === '#woche/{ABFRAGE}' && document.querySelector('#rw-w-titel').textContent.includes('KW {int(ABFRAGE[5:])}')")
    bsp = next(x for g in M.call(f'rewe_woche&kw={ABFRAGE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Beispielstadt')
    if bsp['dauerFaellig']:   # Dauerauftrag alle 2 Wochen ab KW 2: in geraden Wochen fällig
        pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") .rw-dauerbox')
        check('Abfragewoche: Dauerauftrag fällig → „wird zum Bestellschluss automatisch bestellt“, „Diese Woche anders“, „Dauerauftrag ändern“, keine Antwortknöpfe',
              'wird zum Bestellschluss automatisch bestellt' in text(pg, '.rw-zeile:has-text("Beispielstadt") .rw-dauerbox')
              and pg.is_visible('.rw-zeile:has-text("Beispielstadt") .rw-dauerbox [data-dauer-dlg]') and pg.locator('.rw-zeile:has-text("Beispielstadt") [data-s]').count() == 0)
        pg.click('.rw-zeile:has-text("Beispielstadt") .rw-dauerbox [data-offen]')
    else:
        pg.wait_for_selector(f'.rw-dkompakt [data-offen="{bsp["id"]}"]')
        check('Abfragewoche: Dauerauftrag nicht fällig → kompakt „Diese Woche keine Lieferung nach Dauerauftrag“ mit nächster Lieferung, keine volle Zeile',
              'Diese Woche keine Lieferung nach Dauerauftrag' in text(pg, '.rw-dkompakt') and f'nächste KW {int(bsp["dauerNaechste"][5:])}' in text(pg, '.rw-dkompakt')
              and pg.locator('.rw-zeile:has-text("Beispielstadt")').count() == 0, text(pg, '.rw-dkompakt'))
        pg.click(f'.rw-dkompakt [data-offen="{bsp["id"]}"]')
    pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") [data-s="bestellt"]')
    check('„Diese Woche anders“ bzw. „trotzdem abfragen“: normale Antworten, „Markt pausiert“ statt „Pause“', 'Markt pausiert' in text(pg, '.rw-zeile:has-text("Beispielstadt") [data-s="pause"]'))
    # Pop-up „Dauerauftrag“ aus „Meine Woche“ (Chip am Markt): schließt nur über × oder Abbrechen
    pg.click('.rw-zeile:has-text("Beispielstadt") [data-dauer-dlg]'); pg.wait_for_selector('#dlg-dauer[open] #dd-titel:has-text("Beispielstadt")')
    pg.mouse.click(5, 5)
    check('Pop-up aus „Meine Woche“: Beispielstadt, ein Klick daneben schließt nicht', pg.is_visible('#dlg-dauer[open]') and 'alle 2 Wochen' in text(pg, '#dlg-dauer [aria-pressed="true"][data-dd-rh]'))
    pg.click('#dlg-dauer .rw-dialogkopf [data-dd-zu]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
    # Antwort zurücksetzen (wieder offen): erster Klick fragt nach, zweiter setzt zurück; „Rückgängig“ holt sie zurück
    if not pg.locator('.rw-zeile:has-text("Beispielstadt") [data-zurueck]').count():
        pg.click('.rw-zeile:has-text("Beispielstadt") [data-s="kein"]'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") [data-zurueck]')
    vor_reset = next(x for g in M.call(f'rewe_woche&kw={ABFRAGE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Beispielstadt')['antwort']
    pg.click('.rw-zeile:has-text("Beispielstadt") [data-zurueck]'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") [data-zurueck].frage')
    check('Zurücksetzen fragt erst nach', 'Wirklich zurücksetzen?' in text(pg, '.rw-zeile:has-text("Beispielstadt") [data-zurueck]'))
    pg.click('.rw-zeile:has-text("Beispielstadt") [data-zurueck]'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") [data-zurueck]', state='detached')
    nach = next(x for g in M.call(f'rewe_woche&kw={ABFRAGE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Beispielstadt')['antwort']
    check('Antwort zurückgesetzt (wieder offen), Hinweis mit „Rückgängig“', nach is None and 'zurückgesetzt' in text(pg, '#rw-toast') and pg.is_visible('#rw-toast [data-rueck]'), nach)
    pg.click('#rw-toast [data-rueck]'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") [data-zurueck]')
    wieder = next(x for g in M.call(f'rewe_woche&kw={ABFRAGE}')[1]['woche']['gruppen'] for x in g['maerkte'] if x['ort'] == 'Beispielstadt')['antwort']
    check('„Rückgängig“ nach dem Zurücksetzen: vorige Antwort wieder da', wieder and wieder['status'] == vor_reset['status'] and wieder['mengen'] == vor_reset['mengen'], (vor_reset, wieder))
    # Marktakte mit Notiz
    pg.click('#rw-tabs [data-tab="maerkte"]'); pg.wait_for_selector('#rw-m-tabelle tbody tr')
    check('Märkte: nur eigene (2)', pg.locator('#rw-m-tabelle tbody tr').count() == 2 and pg.is_hidden('#rw-m-neu'))
    pg.click('#rw-m-tabelle tr:has-text("Beispielstadt")'); pg.wait_for_selector('.rw-heat')
    check('Marktakte: Adresse #markt/<id>, Jahre im Verlauf, Kennzahlen, Ansprechpartner', '#markt/' in pg.url and pg.locator('.rw-heat .jahr').count() >= 2
          and 'Frau Test' in text(pg, '#rw-akte') and 'Nur gereifte Ware' in text(pg, '#rw-akte'))
    pg.click('#rw-a-notiz'); pg.wait_for_selector('#dlg-notiz[open]')
    pg.select_option('#nz-art', 'telefonat'); pg.fill('#nz-text', 'Vac. Set angeboten'); pg.click('#nz-form button[type="submit"]')
    pg.wait_for_selector('#dlg-notiz[open]', state='hidden'); pg.wait_for_selector('.rw-verlaufsliste li:has-text("Vac. Set angeboten")')
    check('Notiz über die Eingabemaske', 'Telefonat' in text(pg, '.rw-verlaufsliste'))
    pg.click('#rw-a-bearbeiten'); pg.wait_for_selector('#dlg-markt[open]')
    check('Bearbeiten ohne Stammdaten (nur verwalten) und ohne Dauerauftrag (nur noch im Pop-up)', pg.is_hidden('#mk-stamm') and 'Dauerauftrag' not in text(pg, '#dlg-markt'))
    pg.select_option('#mk-tag', 'mi'); pg.click('#mk-form button[type="submit"]'); pg.wait_for_selector('#dlg-markt[open]', state='hidden')
    pg.wait_for_selector('.rw-kv:has-text("Mittwoch")')
    check('Abfragetag geändert', 'Mittwoch' in text(pg, '.rw-kv'))
    check('Marktakte: Dauerauftrag „… + 1 Filetkopf extra“, Wochenverlauf KW 2 „Bestellt 1 Roastbeef Dry Aged + 1 Filetkopf extra“',
          '1 Roastbeef Dry Aged + 1 Filetkopf extra' in text(pg, '.rw-kv') and pg.locator('.rw-heat i[title="KW 2: Bestellt 1 Roastbeef Dry Aged + 1 Filetkopf extra"]').count() == 1, text(pg, '.rw-kv'))
    pg.screenshot(path=os.path.join(SH, 'rewe_akte_1280.png'), full_page=True)
    pg.click('#rw-a-dauer'); pg.wait_for_selector('#dlg-dauer[open] #dd-titel:has-text("Beispielstadt")')
    check('Pop-up aus der Marktakte: „Dauerauftrag · Beispielstadt“', 'Dauerauftrag · Beispielstadt' in text(pg, '#dd-titel'))
    pg.click('#dlg-dauer .rw-ddfuss [data-dd-zu]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
    # Reiter „Daueraufträge“: ruhige Liste mit Wochenleiste, Pop-up zum Ändern, Anlegen mit Marktsuche, Pause von–bis, Ende, beenden
    pg.click('#rw-tabs [data-tab="dauer"]'); pg.wait_for_selector('#rw-d-liste [data-dauer]')
    check('Daueraufträge: Beispielstadt alle 2 Wochen, Menge, Wochenleiste mit 8 Wochen, Zusammenfassung, Filter „KW n fällig“', pg.locator('#rw-d-liste [data-dauer]').count() == 1
          and 'alle 2 Wochen' in text(pg, '#rw-d-liste') and '1 Roastbeef Dry Aged + 1 Filetkopf extra' in text(pg, '#rw-d-liste') and pg.locator('#rw-d-liste [data-dauer] .rw-dwz').count() == 8
          and 'aktiv' in text(pg, '#rw-d-sub') and '#dauer' in pg.url and f'KW {int(ABFRAGE[5:])} fällig' in text(pg, '#rw-d-filter'), text(pg, '#rw-d-liste'))
    pg.click('#rw-d-liste [data-dauer]:has-text("Beispielstadt")'); pg.wait_for_selector('#dlg-dauer[open] [data-dd-rh]')
    check('Pop-up „Dauerauftrag“: Titel, sechs Rhythmen (1–4, 6, 8 Wochen), Lieferwochen, Vorschau', 'Beispielstadt' in text(pg, '#dd-titel') and pg.locator('#dlg-dauer [data-dd-rh]').count() == 6
          and 'alle 8 Wochen' in text(pg, '#dlg-dauer .rw-ddrh') and pg.locator('#dlg-dauer [data-dd-ab]').count() == 12 and 'Nächste Lieferungen' in text(pg, '#dd-vorschau'))
    dfk = '#dlg-dauer .rw-menge.extra'
    check('Pop-up: Mengeneingabe „Filetkopf extra“ mit Hinweis (nur dort), Menge wie gespeichert (1)', pg.locator(dfk).count() == 1 and 'Filetkopf extra' in text(pg, dfk)
          and 'zusätzlich – 1 Filetkopf ist bei jedem Roastbeef Dry Aged schon dabei' in text(pg, dfk) and pg.locator('#dlg-dauer .rw-mextra').count() == 1
          and pg.input_value('#dlg-dauer [data-dd-mzahl="fk"]') == '1' and pg.get_attribute('#dlg-dauer [data-dd-mzahl="fk"]', 'aria-label') == 'Filetkopf extra: Menge', text(pg, '#dlg-dauer .rw-mengen-eingabe'))
    pg.mouse.click(5, 5)
    check('Pop-up: ein Klick daneben schließt nicht (Escape schließt wie überall, Prüfung „einheit“)', pg.is_visible('#dlg-dauer[open]'))
    pg.click('#dlg-dauer [data-dd-rh="1"]'); pg.wait_for_selector('#dlg-dauer [data-dd-rh="1"][aria-pressed="true"]')
    pg.click('#dlg-dauer [data-dd-menge="rb"][data-d="1"]'); pg.wait_for_function("document.querySelector('#dlg-dauer [data-dd-mzahl=\"rb\"]').value === '2'")
    pg.screenshot(path=os.path.join(SH, 'rewe_dauer_1280.png'))
    pg.click('#dlg-dauer [data-dd-speichern]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
    pg.wait_for_selector('#rw-d-liste [data-dauer]:has-text("Beispielstadt"):has-text("jede Woche")')
    bd = next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['ort'] == 'Beispielstadt')['dauer']
    check('Dauerauftrag geändert: jede Woche, 2 Roastbeef + 1 Filetkopf', bd['rhythmus'] == 1 and bd['mengen'] == {'rb': 2, 'fk': 1}, bd)
    bsp_id = next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['ort'] == 'Beispielstadt')['id']
    check('Verlauf der Marktakte: „Dauerauftrag jede Woche · 2 Roastbeef Dry Aged + 1 Filetkopf extra“',
          any('jede Woche · 2 Roastbeef Dry Aged + 1 Filetkopf extra' in n['text'] for n in M.call('rewe_markt&id=' + bsp_id)[1]['notizen']))
    pg.click('#rw-d-neu'); pg.wait_for_selector('#dlg-dauer[open] #dd-suche')
    check('Anlegen: Speichern erst nach der Marktwahl', pg.is_disabled('#dlg-dauer [data-dd-speichern]'))
    pg.fill('#dd-suche', 'muster'); pg.wait_for_selector('#dd-maerkte [data-dd-markt]')
    check('Marktsuche beim Anlegen: nur eigene Märkte ohne Dauerauftrag (Musterdorf)', pg.locator('#dd-maerkte [data-dd-markt]').count() == 1 and 'Musterdorf' in text(pg, '#dd-maerkte'))
    pg.click('#dd-maerkte [data-dd-markt]'); pg.wait_for_selector('#dd-titel:has-text("Musterdorf")')
    pg.click('#dlg-dauer [data-dd-rh="4"]'); pg.wait_for_selector('#dlg-dauer [data-dd-rh="4"][aria-pressed="true"]')
    pg.check('#dd-pause'); pg.wait_for_selector('#dd-pvon')
    pg.select_option('#dd-pvon', kw_plus(ABFRAGE, 4)); pg.wait_for_selector('#dd-pbis'); pg.select_option('#dd-pbis', kw_plus(ABFRAGE, 5))
    pg.check('#dd-ende'); pg.wait_for_selector('#dd-bis'); pg.select_option('#dd-bis', kw_plus(ABFRAGE, 20))
    pg.wait_for_function("document.querySelector('#dd-vorschau').textContent.includes('Pause') && document.querySelector('#dd-vorschau').textContent.includes('endet nach')")
    check('Vorschau mit Pause (bis einschließlich) und Ende', 'bis einschließlich' in text(pg, '#dlg-dauer') and 'läuft bis einschließlich' in text(pg, '#dlg-dauer'), text(pg, '#dd-vorschau'))
    pg.click('#dlg-dauer [data-dd-speichern]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
    pg.wait_for_selector('#rw-d-liste [data-dauer]:has-text("Musterdorf"):has-text("alle 4 Wochen")')
    md = next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['ort'] == 'Musterdorf')['dauer']
    check('Neuer Dauerauftrag: Musterdorf alle 4 Wochen, Pause von–bis einschließlich, läuft bis', md['rhythmus'] == 4 and md['pauseVon'] == kw_plus(ABFRAGE, 4)
          and md['pauseBis'] == kw_plus(ABFRAGE, 5) and md['bis'] == kw_plus(ABFRAGE, 20) and pg.locator('#rw-d-liste [data-dauer]').count() == 2, md)
    mdm = next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['ort'] == 'Musterdorf')
    check('Verlauf der Marktakte nennt Rhythmus, Pause und Ende', any('alle 4 Wochen' in n['text'] and 'bis einschließlich' in n['text'] and 'läuft bis einschließlich' in n['text']
          for n in M.call('rewe_markt&id=' + mdm['id'])[1]['notizen']))
    pg.click('#rw-d-filter [data-df="pause"]'); pg.wait_for_function("document.querySelectorAll('#rw-d-liste [data-dauer]').length === 1")
    check('Filter „Pausiert“: auch eine geplante Pause (Musterdorf)', 'Musterdorf' in text(pg, '#rw-d-liste') and 'Pause' in text(pg, '#rw-d-liste'))
    pg.click('#rw-d-filter [data-df=""]'); pg.wait_for_function("document.querySelectorAll('#rw-d-liste [data-dauer]').length === 2")
    pg.click('#rw-d-liste [data-dauer]:has-text("Musterdorf")'); pg.wait_for_selector('#dlg-dauer[open] [data-dd-ende]')
    pg.click('#dlg-dauer [data-dd-ende]'); pg.wait_for_selector('#dlg-dauer [data-dd-ende]:has-text("Wirklich beenden?")')
    pg.click('#dlg-dauer [data-dd-ende]'); pg.wait_for_selector('#rw-d-liste [data-dauer]:has-text("Musterdorf")', state='detached')
    check('Dauerauftrag beendet (Rückfrage mit zweitem Klick)', next(m for m in M.call('rewe_maerkte')[1]['maerkte'] if m['ort'] == 'Musterdorf')['dauer']['rhythmus'] == 0)
    # Folgewoche: Beispielstadt (jetzt jede Woche) wird automatisch bestellt – zählt als erledigt, Kachel filtert auf diese Märkte
    KWN = kw_plus(ABFRAGE, 1)
    pg.goto(B + f'/module/rewe/#woche/{KWN}'); pg.wait_for_selector('#rw-w-kpis [data-kpi-dauer]')
    pg.click('#rw-w-filter [data-f="offen"]'); pg.wait_for_selector('#rw-w-filter [data-f="offen"][aria-pressed="true"]')
    check('Folgewoche, Filter „Offen“: automatisch bestellter Dauerauftrag ist erledigt (nicht in der Liste), Kachel „Daueraufträge diese Woche: 1 · automatisch“',
          pg.locator('.rw-zeile:has-text("Beispielstadt")').count() == 0 and '1' in text(pg, '#rw-w-kpis [data-kpi-dauer] b')
          and 'automatisch bestellt' in text(pg, '#rw-w-kpis [data-kpi-dauer]'), text(pg, '#rw-w-kpis'))
    pg.click('#rw-w-kpis [data-kpi-dauer]'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt") .rw-dauerbox')
    check('Klick auf die Kachel: nur Märkte mit Dauerauftrag, Kasten „wird zum Bestellschluss automatisch bestellt“ mit „Diese Woche anders“',
          pg.get_attribute('#rw-w-kpis [data-kpi-dauer]', 'aria-pressed') == 'true' and pg.locator('.rw-zeile').count() == 1
          and 'Dauerauftrag KW' in text(pg, '.rw-dauerbox') and 'wird zum Bestellschluss automatisch bestellt' in text(pg, '.rw-dauerbox')
          and pg.is_visible('.rw-dauerbox [data-offen]') and pg.locator('.rw-zeile:has-text("Beispielstadt") .rw-z.d.jetzt').count() == 1)
    check('Dauerauftrag-Kasten: „2 Roastbeef Dry Aged + 1 Filetkopf extra“', '2 Roastbeef Dry Aged + 1 Filetkopf extra' in text(pg, '.rw-dauerbox'), text(pg, '.rw-dauerbox'))
    pg.screenshot(path=os.path.join(SH, 'rewe_dauer_woche_1280.png'), full_page=True)
    pg.click('#rw-w-kpis [data-kpi-dauer]'); pg.wait_for_selector('#rw-w-filter [data-f="offen"][aria-pressed="true"]')
    check('erneuter Klick: wieder Filter „Offen“', pg.get_attribute('#rw-w-kpis [data-kpi-dauer]', 'aria-pressed') == 'false')
    ctx.close()

    ctx, pg = anmelden('lena', 'Leitung-Konto-11', '198.51.100.10')
    pg.wait_for_selector('.rw-gruppe, .rw-leer')
    check('Leitung: alle Reiter, Listenwahl', pg.is_visible('#rw-tabs [data-tab="zuweisung"]') and pg.is_visible('#rw-tabs [data-tab="abschluss"]') and pg.is_visible('#rw-w-wer'))
    pg.select_option('#rw-w-wer', '*'); pg.wait_for_function("document.querySelector('#rw-w-titel').textContent.startsWith('Alle Listen')")
    pg.click('#rw-tabs [data-tab="zuweisung"]'); pg.wait_for_selector('#rw-z-tabelle tbody tr [data-wahl]')
    check('Zuweisung: Team-Karten, alle Märkte', pg.locator('#rw-z-personen [data-person]').count() >= 4 and pg.locator('#rw-z-tabelle [data-wahl]').count() == 4)
    pg.check('#rw-z-tabelle tr:has-text("Neustadt") [data-wahl]'); pg.wait_for_selector('#rw-z-bulk:not([hidden])')
    pg.select_option('#rw-z-nutzer', ids['evi']); pg.fill('#rw-z-ab', ABFRAGE); pg.click('#rw-z-los')
    pg.wait_for_selector('#rw-z-tabelle tr:has-text("Neustadt"):has-text("Evi Eins")')
    check('Zuweisung über die Oberfläche: Neustadt → Evi', any(m['ort'] == 'Neustadt' and m['zustaendigName'] == 'Evi Eins' for m in LE.call('rewe_maerkte')[1]['maerkte']))
    pg.screenshot(path=os.path.join(SH, 'rewe_zuweisung_1280.png'), full_page=True)
    # Team: Entfernen mit Märkten nur Hinweis, sonst zweiter Klick; Hinzufügen über die Auswahl
    karte, mark_knopf = f'#rw-z-personen [data-person="{ids["pia"]}"]', f'#rw-z-personen [data-person="{ids["mark"]}"] [data-entfernen]'
    check('Zuweisung: Karte „Mitarbeiter hinzufügen“, Pia „im Modul ergänzt“, Mark mit Märkten nicht entfernbar', pg.is_visible('#rw-z-kandidat') and pg.is_visible('#rw-z-ergaenzen')
          and 'im Modul ergänzt' in text(pg, karte) and pg.get_attribute(mark_knopf, 'aria-disabled') == 'true', text(pg, '#rw-z-personen'))
    pg.click(mark_knopf, force=True); pg.wait_for_selector('#rw-toast.zeigen.fehler')
    check('Entfernen mit Märkten: Hinweis „erst … umverteilen“, Mark bleibt', 'umverteilen' in text(pg, '#rw-toast') and pg.is_visible(mark_knopf), text(pg, '#rw-toast'))
    pg.click(f'{karte} [data-entfernen]'); pg.wait_for_selector(f'{karte} [data-entfernen].frage')
    check('Entfernen fragt erst nach (im Seitenstil, kein Browser-Dialog)', 'Wirklich entfernen?' in text(pg, f'{karte} [data-entfernen]') and 'keine REWE-Listen mehr' in text(pg, karte))
    pg.screenshot(path=os.path.join(SH, 'rewe_team_entfernen_1280.png'))
    pg.click(f'{karte} [data-entfernen]'); pg.wait_for_selector(karte, state='detached')
    check('Pia entfernt: Karte weg, in der Auswahl „Mitarbeiter hinzufügen“, nicht mehr in der Personenauswahl', pg.locator(f'#rw-z-kandidat option[value="{ids["pia"]}"]').count() == 1
          and pg.locator(f'#rw-z-nutzer option[value="{ids["pia"]}"]').count() == 0 and 'Pia Plus' not in namen(LE.call('rewe_start')[1]['personen']))
    pg.select_option('#rw-z-kandidat', ids['pia']); pg.click('#rw-z-ergaenzen'); pg.wait_for_selector(karte)
    check('Pia wieder hinzugefügt (Karte, Personenauswahl der Zuweisung, Hinweis)', 'Pia Plus' in pg.text_content(karte) and pg.locator(f'#rw-z-nutzer option[value="{ids["pia"]}"]').count() == 1
          and 'ist jetzt im Team' in text(pg, '#rw-toast') and person('Pia Plus').get('ergaenzt') is True)
    pg.screenshot(path=os.path.join(SH, 'rewe_team_1280.png'), full_page=True)
    pg.goto(B + f'/module/rewe/#abschluss/{WOCHE}'); pg.wait_for_selector('.rw-schritte')
    check('Wochenabschluss: Schritte, Vorschau mit Aufträgen', pg.locator('.rw-schritte li').count() == 4 and 'Vorschau Excel für WinAB' in text(pg, '#rw-a-inhalt'))
    with pg.expect_download() as dl:
        pg.click('#rw-a-export')
    check('Excel über die Oberfläche (KW 43, Bestellung aus der Oberfläche)', dl.value.suggested_filename == 'REWE_WinAB_2026_KW43.xlsx', dl.value.suggested_filename)
    pg.wait_for_selector('#rw-a-erfasst:not([hidden])')
    pg.screenshot(path=os.path.join(SH, 'rewe_abschluss_1280.png'), full_page=True)
    pg.goto(B + f'/module/rewe/#abschluss/{kw_plus(ABFRAGE, 1)}'); pg.wait_for_selector('.rw-schritte')
    pg.wait_for_function(f"document.querySelector('#rw-a-titel').textContent.includes('KW {int(kw_plus(ABFRAGE, 1)[5:])}')")
    try:   # der Titel steht schon vor dem Laden – auf den Inhalt der neuen Woche warten
        pg.wait_for_function("document.querySelector('#rw-a-inhalt').innerText.includes('werden automatisch bestellt')", timeout=8000)
    except Exception:
        pass
    check('Wochenabschluss vor dem Bestellschluss: Daueraufträge „werden automatisch bestellt“, Excel trotzdem möglich (bestellt sie dabei)',
          'werden automatisch bestellt' in text(pg, '#rw-a-inhalt') and pg.is_enabled('#rw-a-export'), text(pg, '#rw-a-inhalt')[:300])
    pg.goto(B + '/module/rewe/#abschluss/2026-02')   # KW 2: Bestellung aus dem Datenpaket (1 Roastbeef + 1 Filetkopf)
    ok = warte_auf(pg, "document.querySelector('#rw-a-inhalt').innerText.includes('Filetkopf extra') && !!document.querySelector('#rw-a-inhalt .rw-tabelle')")
    check('Wochenabschluss: Vorschau (Spalte Artikel) und Kennzahl „Stück gesamt“ mit „Filetkopf extra“, Menge wie gespeichert (1)', ok and 'Filetkopf extra' in text(pg, '#rw-a-inhalt .rw-tabelle')
          and '1 Filetkopf extra' in text(pg, '#rw-a-inhalt .rw-kpis') and '1 Roastbeef Dry Aged' in text(pg, '#rw-a-inhalt .rw-kpis'), text(pg, '#rw-a-inhalt')[:600])
    pg.click('#rw-tabs [data-tab="einstellungen"]'); pg.wait_for_selector('#rw-e-lw tbody tr')
    pg.wait_for_selector('#rw-e-art tr[data-art="fk"] [data-f="extra"]')
    check('Einstellungen: Artikel mit „extra“ und „Hinweis bei der Eingabe“ (Filetkopf vorbelegt)', pg.is_checked('#rw-e-art tr[data-art="fk"] [data-f="extra"]')
          and not pg.is_checked('#rw-e-art tr[data-art="rb"] [data-f="extra"]')
          and pg.input_value('#rw-e-art tr[data-art="fk"] [data-f="extraHinweis"]') == '1 Filetkopf ist bei jedem Roastbeef Dry Aged schon dabei')
    namen = json.loads(json.dumps(PAKET).replace('"Liste A"', '"Liste Mark"').replace('"Liste B"', '"Evi"'))
    pg.set_input_files('#rw-e-datei', files=[{'name': 'paket.json', 'mimeType': 'application/json', 'buffer': json.dumps(namen).encode()}])
    pg.wait_for_selector('#rw-e-vorschau .rw-vorschau')
    wahl = {s.get_attribute('data-liste'): s.input_value() for s in pg.locator('#rw-e-vorschau [data-liste]').all()}
    check('Einstellungen: Lieferwege, Artikel, Datenpaket-Vorschau mit Listen-Zuordnung', pg.locator('#rw-e-lw tbody tr').count() == 3
          and len(wahl) == 3 and pg.is_visible('#rw-e-ersetzen'), wahl)
    check('Datenpaket: Listen nach Vornamen vorgeschlagen („Liste Mark“ → Mark, „Evi“ → Evi, „Liste C“ → niemand)',
          wahl == {'Evi': ids['evi'], 'Liste C': '', 'Liste Mark': ids['mark']} and '2 Listen wurden' in text(pg, '#rw-e-vorschlag'), wahl)
    pg.screenshot(path=os.path.join(SH, 'rewe_einstellungen_1280.png'), full_page=True)
    ctx.close()

    # ── Suche in „Meine Woche“ (Wunsch des Inhabers 12.11.2026): groß, immer über alle Listen, nur Lager mit Treffern ──
    wa = {x['ort']: x for g in LE.call(f'rewe_woche&kw={ABFRAGE}&wer=*')[1]['woche']['gruppen'] for x in g['maerkte']}
    check('Suche – Ausgangslage: Beispielstadt (Mark, Nordheim) beantwortet = erledigt, Neustadt (Evi) direkt', wa['Beispielstadt']['antwort'] is not None
          and wa['Beispielstadt']['lieferweg'] == 'nordlager' and wa['Neustadt']['lieferweg'] == 'direkt' and wa['Neustadt']['zustaendigName'] == 'Evi Eins', {o: x['zustaendigName'] for o, x in wa.items()})
    gruppen = lambda pg: pg.eval_on_selector_all('#rw-w-gruppen .rw-gruppe', 'els => els.map(e => e.dataset.gruppe)')
    zeilen = lambda pg: pg.eval_on_selector_all('#rw-w-gruppen .rw-zeile .rw-mname', 'els => els.map(e => e.textContent.trim())')
    ctx, pg = anmelden('lena', 'Leitung-Konto-11', '198.51.100.10', pfad=f'/module/rewe/#woche/{ABFRAGE}', ziel='#rw-w-gruppen .rw-leer')
    breite_suche = pg.evaluate("document.querySelector('#rw-w-suche').getBoundingClientRect().width")
    check('Suchfeld groß (≥ 500 px bei 1280), mit Lupe, × erst mit Text, Hinweis verborgen', breite_suche >= 500 and pg.is_visible('.rw-suche > .i')
          and pg.is_hidden('#rw-w-suche-leeren') and pg.is_hidden('#rw-w-suchinfo') and 'Keine Märkte in dieser Liste' in text(pg, '#rw-w-gruppen'), breite_suche)
    pg.fill('#rw-w-suche', 'beispielstadt'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt")')
    check('Leitung (eigene Liste leer): Suche findet Marks Markt in allen Listen – nur das Lager mit Treffer, „1 Treffer“, Zuständig sichtbar',
          gruppen(pg) == ['nordlager'] and zeilen(pg) == ['Beispielstadt'] and '1 Treffer' in text(pg, '.rw-gruppe .rw-gzahl')
          and 'Suche in allen Listen · 1 Treffer' in text(pg, '#rw-w-suchinfo') and 'Mark Markt' in text(pg, '.rw-zeile:has-text("Beispielstadt") .rw-hinweise'), (gruppen(pg), zeilen(pg)))
    check('… erledigter Markt trotz Filter „Offen“ gefunden, Filter ruht, × sichtbar', pg.is_visible('.rw-zeile.erledigt:has-text("Beispielstadt")')
          and pg.get_attribute('#rw-w-filter [data-f="offen"]', 'aria-pressed') == 'true' and 'ruht' in pg.get_attribute('#rw-w-filter', 'class')
          and pg.is_visible('#rw-w-suche-leeren') and 'Alle Märkte dieser Gruppe' not in text(pg, '#rw-w-gruppen'))
    pg.screenshot(path=os.path.join(SH, 'rewe_suche_1280.png'), full_page=True)
    pg.fill('#rw-w-suche', 'Neustadt'); pg.wait_for_function("document.querySelector('#rw-w-suchinfo').textContent.includes('1 Treffer') && !!document.querySelector('.rw-zeile[data-id] .rw-mname') && document.querySelector('.rw-zeile .rw-mname').textContent.includes('Neustadt')")
    check('Suche „Neustadt“: nur Direktbelieferung, Lager Nordheim ausgeblendet', gruppen(pg) == ['direkt'] and zeilen(pg) == ['Neustadt'], (gruppen(pg), zeilen(pg)))
    pg.fill('#rw-w-suche', '40000001'); pg.wait_for_function("[...document.querySelectorAll('.rw-zeile .rw-mname')].map(e => e.textContent.trim()).join() === 'Beispielstadt'")
    check('Suche nach der REWE-Marktnummer findet den Markt', gruppen(pg) == ['nordlager'])
    pg.fill('#rw-w-suche', 'Stillhausen'); pg.wait_for_selector('#rw-ruhend[open] .rw-mname:has-text("Stillhausen")')
    check('ruhender Markt: nur „Ruhende Märkte“ (aufgeklappt, 1 Treffer), keine Lager', gruppen(pg) == [] and '1 Treffer' in text(pg, '#rw-ruhend summary'))
    pg.fill('#rw-w-suche', 'Gibtsnichtdorf'); pg.wait_for_selector('#rw-w-keintreffer')
    check('kein Treffer: Hinweis „Kein Markt gefunden“, keine Lager', 'Kein Markt gefunden' in text(pg, '#rw-w-keintreffer') and gruppen(pg) == [] and pg.locator('#rw-ruhend').count() == 0
          and 'Suche in allen Listen · 0 Treffer' in text(pg, '#rw-w-suchinfo'))
    pg.click('#rw-w-suche-leeren'); pg.wait_for_selector('#rw-w-suchinfo', state='hidden')
    check('× leert: eigene (leere) Liste wieder, Filter wieder aktiv, Fokus im Feld', pg.input_value('#rw-w-suche') == '' and 'Keine Märkte in dieser Liste' in text(pg, '#rw-w-gruppen')
          and 'ruht' not in pg.get_attribute('#rw-w-filter', 'class') and pg.evaluate("document.activeElement.id") == 'rw-w-suche' and pg.is_hidden('#rw-w-suche-leeren'))
    pg.select_option('#rw-w-wer', ids['mark']); pg.wait_for_function("document.querySelector('#rw-w-titel').textContent.startsWith('Mark Markt')")
    pg.wait_for_selector('.rw-gruppe')
    vor = zeilen(pg)
    pg.fill('#rw-w-suche', 'neustadt'); pg.wait_for_function("[...document.querySelectorAll('.rw-zeile .rw-mname')].map(e => e.textContent.trim()).join() === 'Neustadt'")
    check('Liste von Mark gewählt: Suche findet trotzdem Evis Markt (alle Listen)', gruppen(pg) == ['direkt'] and 'Mark Markt' in text(pg, '#rw-w-titel'))
    pg.fill('#rw-w-suche', ''); pg.wait_for_selector('#rw-w-suchinfo', state='hidden')
    check('Suchfeld geleert: Liste von Mark mit Filter „Offen“ wie vorher (erledigte Beispielstadt nicht sichtbar)', zeilen(pg) == vor and 'Beispielstadt' not in vor
          and gruppen(pg) == ['nordlager'], (vor, zeilen(pg)))
    ctx.close()

    ctx, pg = anmelden('mark', 'Laden-Konto-22', '198.51.100.11', pfad=f'/module/rewe/#woche/{ABFRAGE}', ziel='.rw-gruppe')
    anfragen = []
    pg.on('request', lambda r: anfragen.append(r.url) if 'rewe_woche' in r.url else None)
    pg.fill('#rw-w-suche', 'Neustadt'); pg.wait_for_selector('#rw-w-keintreffer')
    check('ohne „alle Listen“: Suche nur in den eigenen Märkten – Evis Markt nicht gefunden, kein Abruf anderer Listen',
          'Suche in Ihren Märkten · 0 Treffer' in text(pg, '#rw-w-suchinfo') and not any('wer=' in u for u in anfragen), anfragen)
    pg.fill('#rw-w-suche', 'Beispielstadt'); pg.wait_for_selector('.rw-zeile.erledigt:has-text("Beispielstadt")')
    check('ohne „alle Listen“: eigener erledigter Markt trotz „Offen“ gefunden', zeilen(pg) == ['Beispielstadt'] and gruppen(pg) == ['nordlager'])
    pg.keyboard.press('Escape'); pg.wait_for_selector('#rw-w-suchinfo', state='hidden')
    check('Escape leert die Suche, Filter „Offen“ gilt wieder', 'Beispielstadt' not in zeilen(pg) and pg.input_value('#rw-w-suche') == '')
    ctx.close()

    for thema in ('light', 'dark'):
        ctx, pg = anmelden('lena', 'Leitung-Konto-11', '198.51.100.10', 390, thema, 844, pfad=f'/module/rewe/#woche/{ABFRAGE}', ziel='#rw-w-gruppen .rw-leer')
        pg.fill('#rw-w-suche', 'Beispielstadt'); pg.wait_for_selector('.rw-zeile:has-text("Beispielstadt")')
        r_ = pg.evaluate("(() => { const r = document.querySelector('#rw-w-suche').getBoundingClientRect(); return [r.width, r.left, innerWidth]; })()")
        check(f'390px {thema}: Suchfeld in voller Breite, Treffer ohne waagerechtes Scrollen', r_[0] >= r_[2] - 2 * 16 - 2 and r_[1] <= 17
              and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), r_)
        pg.screenshot(path=os.path.join(SH, f'rewe_suche_390_{thema}.png'), full_page=True)
        ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('mark', 'Laden-Konto-22', '198.51.100.11', breite, thema, 844 if breite < 500 else 900, pfad=f'/module/rewe/#woche/{WOCHE}')
        pg.wait_for_selector('.rw-gruppe')
        breit = []
        for ziel, warte in ((f'#woche/{WOCHE}', '.rw-gruppe'), ('#dauer', '#rw-d-liste [data-dauer]'), ('#maerkte', '#rw-m-tabelle tbody tr'), ('#markt/' + maerkte['Beispielstadt']['id'], '.rw-heat')):
            pg.goto(B + '/module/rewe/' + ziel); pg.wait_for_selector(warte)
            if not pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'):
                breit.append(ziel)
            if breite == 390:
                pg.screenshot(path=os.path.join(SH, f'rewe_{ziel.split("/")[0][1:]}_{breite}_{thema}.png'), full_page=True)
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', not breit, breit)
        pg.goto(B + '/module/rewe/#dauer'); pg.wait_for_selector('#rw-d-liste [data-dauer]')
        pg.click('#rw-d-liste [data-dauer] >> nth=0'); pg.wait_for_selector('#dlg-dauer[open] [data-dd-rh]')
        lage = pg.evaluate("(() => { const d = document.querySelector('#dlg-dauer'), r = d.getBoundingClientRect(); return [d.scrollWidth - d.clientWidth, Math.round(r.left), Math.round(r.right), Math.round(r.bottom), innerWidth, innerHeight]; })()")
        check(f'{breite}px {thema}: Pop-up „Dauerauftrag“ ohne seitliches Scrollen' + (', am Handy als Blatt von unten' if breite <= 560 else ''),
              lage[0] <= 1 and lage[2] <= lage[4] + 1 and (breite > 560 or (lage[1] <= 0 and lage[2] >= lage[4] - 1 and lage[3] >= lage[5] - 1)), lage)
        if breite == 390:
            pg.screenshot(path=os.path.join(SH, f'rewe_dauer_popup_{breite}_{thema}.png'))
            hin = pg.evaluate("(() => { const e = document.querySelector('#dlg-dauer .rw-menge.extra .rw-mextra'); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.width), innerWidth]; })()")
            check(f'{breite}px {thema}: „Filetkopf extra“ mit Hinweis im Pop-up sichtbar, nichts ragt heraus', bool(hin) and hin[0] >= 0 and hin[1] <= hin[3] and hin[2] > 0
                  and pg.is_visible('#dlg-dauer .rw-mextra') and 'Filetkopf extra' in text(pg, '#dlg-dauer .rw-menge.extra'), hin)
        pg.click('#dlg-dauer .rw-dialogkopf [data-dd-zu]'); pg.wait_for_selector('#dlg-dauer', state='hidden')
        # Suche: am Handy (≤ 560 px) Kennzahlen und „Bestellungen KW …“ aus, damit die Treffer direkt unter dem Feld stehen
        pg.goto(B + f'/module/rewe/#woche/{WOCHE}'); pg.wait_for_selector('#rw-w-bestellt .rw-bestellt')
        handy, sichtbar_ = breite <= 560, lambda: (pg.is_visible('#rw-w-kpis'), pg.is_visible('#rw-w-bestellt .rw-bestellt'))
        vorher_ = sichtbar_()
        pg.fill('#rw-w-suche', 'Musterdorf'); pg.wait_for_selector('#rw-w-suchinfo:not([hidden])'); pg.wait_for_selector('.rw-zeile:has-text("Musterdorf")')
        waehrend = sichtbar_()
        abstand = pg.evaluate("document.querySelector('.rw-gruppe').getBoundingClientRect().top - document.querySelector('#rw-w-suche').getBoundingClientRect().bottom")
        if handy:
            pg.screenshot(path=os.path.join(SH, f'rewe_suche_handy_{breite}_{thema}.png'))
        pg.click('#rw-w-suche-leeren'); pg.wait_for_selector('#rw-w-suchinfo', state='hidden')
        check(f'{breite}px {thema}: Kennzahlen und „Bestellungen“ ' + ('während der Suche aus, Treffer direkt unter dem Feld' if handy else 'auch während der Suche sichtbar (wie #344)') + ', nach dem Leeren wieder da',
              vorher_ == (True, True) and waehrend == ((False, False) if handy else (True, True)) and sichtbar_() == (True, True) and (abstand < 120 if handy else abstand > 150),
              (vorher_, waehrend, sichtbar_(), abstand))
        pg.goto(B + f'/module/rewe/#woche/{WOCHE}'); pg.wait_for_selector('.rw-gruppe')
        pg.click('#rw-w-filter [data-f="alle"]'); pg.wait_for_selector('.rw-zeile .rw-mname')
        pg.click('.rw-zeile .rw-mname >> nth=0'); pg.wait_for_selector('#dlg-karte[open] #kt-hinweis')
        weite = pg.evaluate("(() => { const d = document.querySelector('#dlg-karte'); return [d.scrollWidth - d.clientWidth, d.getBoundingClientRect().right <= innerWidth + 1]; })()")
        check(f'{breite}px {thema}: Marktkarte ohne seitliches Scrollen, im Bild', weite[0] <= 1 and weite[1], weite)
        if breite == 390:
            pg.screenshot(path=os.path.join(SH, f'rewe_marktkarte_{breite}_{thema}.png'))
        pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-karte', state='hidden')
        if thema == 'dark':
            check(f'{breite}px: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)')
        ctx.close()

    for thema in ('light', 'dark'):
        ctx, pg = anmelden('lena', 'Leitung-Konto-11', '198.51.100.10', 390, thema, 844, pfad='/module/rewe/#zuweisung', ziel='#rw-z-tabelle tbody tr [data-wahl]')
        pg.wait_for_selector('#rw-z-kandidat')
        check(f'390px {thema}: Zuweisung mit Team-Karten ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
              and pg.is_visible(f'#rw-z-personen [data-person="{ids["pia"]}"] [data-entfernen]'))
        pg.screenshot(path=os.path.join(SH, f'rewe_zuweisung_390_{thema}.png'), full_page=True)
        ctx.close()

    ctx, pg = anmelden('pia', 'Plus-Konto-88', '198.51.100.17', ziel='#rw-w-gruppen .rw-leer')
    check('im Modul ergänzt (ohne Rollenrecht): Seite mit eigener Woche, ohne Zuweisung', pg.is_visible('#rw-app') and pg.is_hidden('#rw-tabs [data-tab="zuweisung"]')
          and 'Keine Märkte in dieser Liste' in text(pg, '#rw-w-gruppen'))
    ctx.close()

    ctx, pg = anmelden('otto', 'Ohne-Konto-66', '198.51.100.15', ziel='#rw-err:not([hidden])')
    check('ohne REWE-Recht: Hinweis statt Inhalt', 'Berechtigung' in text(pg, '#rw-err') and pg.is_hidden('#rw-app'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
