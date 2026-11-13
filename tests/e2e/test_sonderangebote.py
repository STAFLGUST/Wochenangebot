"""Sonderangebote (Angebot → Sonderangebote, module/angebot/sonderangebote.php): Angebot für ganze Kundengruppen mit
Gültigkeit (Zeitraum oder KW). Schnittstelle mit Rechten (401/403), Prüfung der Eingaben (Zeitraum, KW, KW 53, Gruppen,
Namen), Stand vor/während/nach der Gültigkeit und an der Wochengrenze Sonntag → Montag, Sichtbarkeit nur für Kunden der
Gruppen und erst nach Veröffentlichung (andere Gruppe, ohne Gruppe, direkte Freischaltung wirkungslos, nicht angemeldet),
Gruppe zugleich mit Kundenangebot, öffentliches Wochenangebot ohne Sonderpreise, Bestellwunsch mit Serverpreis, Versand
(„Angebote dieser Woche“, Link in der Wochen-Mail), ältere Fenster (offers_save) und unbekannte Felder (GR-006), Löschen
mit Bestätigung. Oberfläche: Reiter unter „Einzelangebote“, Anlegen mit Kippschalter Zeitraum ↔ KW, Bearbeiten im Editor,
Artikel aus einem anderen Angebot übernehmen (Auswahl einzelner Artikel), Kundenseite, 390 px, hell/dunkel, keine
JavaScript-Fehler. Nur Testdaten."""
import datetime
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SH, SMTP_PORT, shot, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
KPW = 'Start-Kennwort-42'   # vorhandenes Test-Passwort (.gitleaks.toml)
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


heute = datetime.date.today()   # run_e2e.py: TZ=Europe/Berlin wie der Server
iso = lambda d: d.isoformat()   # noqa: E731
tag = lambda n: iso(heute + datetime.timedelta(days=n))   # noqa: E731
naechste = heute + datetime.timedelta(days=7)
kw_naechste = naechste.isocalendar()
kw_jetzt = heute.isocalendar()
kw_vorige = (heute - datetime.timedelta(days=7)).isocalendar()

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200

# Kundengruppen, Kundenangebot „Edeka“ für Gruppe 20, Kunden je Gruppe
assert A.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '10', 'name': 'Gastronomie'}, {'nr': '20', 'name': 'Handel'}, {'nr': '30', 'name': 'Großhandel'}]})[0] == 200
offs = A.call('offers')[1]
st, r = A.call('offers_save', {'rev': offs['rev'], 'offers': [dict(o, gruppen=['20'] if o['id'] == 'edeka' else []) for o in offs['offers']]})
assert st == 200, r


KUNDEN = []


def kunde(nr, gruppe, angebote=None):
    rev = A.call('kunden')[1]['rev']
    st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Testkunde ' + nr, 'nr': nr, 'email': nr.lower() + '@example.org', 'active': True, 'gruppe': gruppe,
                                  'angebote': angebote or [], 'login': {'username': nr.lower(), 'password': KPW, 'mustChange': False, 'active': True}})
    assert st == 200, r
    c = Client('198.51.100.' + str(50 + len(KUNDEN)))
    KUNDEN.append(nr)
    assert c.call('kunde_login', {'username': nr.lower(), 'password': KPW})[0] == 200
    return c, r['customer']['id']


K10, K10id = kunde('K10', '10')
K20, _ = kunde('K20', '20')
K30, _ = kunde('K30', '30')
K0, K0id = kunde('K0', '', ['std'])

# ---------- Rechte der Schnittstelle ----------
NEU = {'name': 'Grillwoche', 'gruppen': ['10', '20'], 'gueltig': {'modus': 'zeitraum', 'von': tag(0), 'bis': tag(3)}}
check('Liste ohne Anmeldung: 401', Client('198.51.100.9').call('sonderangebote')[0] == 401)
check('Liste für Kunden gesperrt (Kunde ist kein Mitarbeiter, GR-104)', K10.call('sonderangebote')[0] == 401)
st, lst = L.call('sonderangebote')
check('Leser sieht die (leere) Liste mit Kundengruppen, ohne Kundenzahl', st == 200 and lst['sonder'] == [] and [g['nr'] for g in lst['gruppen']] == ['10', '20', '30']
      and 'kunden' not in lst['gruppen'][0] and lst['kundenZahl'] is False, lst)
check('Leser darf nicht anlegen (403)', L.call('sonderangebot_save', {**NEU, 'rev': lst['rev']})[0] == 403)
check('Kunde darf nicht anlegen', K10.call('sonderangebot_save', {**NEU, 'rev': lst['rev']})[0] in (401, 403))
check('Anlegen nur per POST (405)', E.call('sonderangebot_save')[0] == 405)
tok = E.csrf; E.csrf = 'falsch'
check('Anlegen ohne gültiges CSRF-Zeichen abgewiesen', E.call('sonderangebot_save', {**NEU, 'rev': lst['rev']})[0] == 403)
E.csrf = tok

# ---------- Prüfung der Eingaben ----------
rev = lst['rev']
fehler = {
    'ohne Kundengruppe': {**NEU, 'gruppen': []},
    'unbekannte Kundengruppe': {**NEU, 'gruppen': ['99']},
    'Name zu kurz': {**NEU, 'name': 'X'},
    'Name „Wochenangebot“': {**NEU, 'name': 'Wochenangebot'},
    'Name eines Kundenangebots': {**NEU, 'name': 'wochenangebot edeka'},
    'Ende vor Beginn': {**NEU, 'gueltig': {'modus': 'zeitraum', 'von': tag(3), 'bis': tag(0)}},
    'Zeitraum in der Vergangenheit': {**NEU, 'gueltig': {'modus': 'zeitraum', 'von': tag(-9), 'bis': tag(-2)}},
    'Datum, das es nicht gibt': {**NEU, 'gueltig': {'modus': 'zeitraum', 'von': '2031-02-30', 'bis': '2031-03-02'}},
    'Zeitraum über ein Jahr': {**NEU, 'gueltig': {'modus': 'zeitraum', 'von': tag(0), 'bis': tag(400)}},
    'KW 53 in einem Jahr mit 52 Wochen': {**NEU, 'gueltig': {'modus': 'kw', 'jahr': 2031, 'kw': 53}},
    'KW 0': {**NEU, 'gueltig': {'modus': 'kw', 'jahr': 2031, 'kw': 0}},
    'ohne Gültigkeit': {**NEU, 'gueltig': None},
    'unbekannte Art der Gültigkeit': {**NEU, 'gueltig': {'modus': 'monat', 'monat': 3}},
}
for n, b in fehler.items():
    st, r = E.call('sonderangebot_save', {**b, 'rev': rev})
    check(f'abgewiesen (422): {n}', st == 422 and r.get('error'), (st, r))

# ---------- Anlegen: Zeitraum (läuft), KW (geplant), KW 53 und KW 1 (Wochengrenze), Rechte für Kunden ----------
st, r = E.call('sonderangebot_save', {**NEU, 'rev': rev})
check('Bearbeiter legt Sonderangebot mit Zeitraum an', st == 200 and r['neu'] is True and r['id'] == 'sonder-grillwoche', r)
S1 = r['id']; rev = r['rev']
check('veraltete Revision abgewiesen (409)', E.call('sonderangebot_save', {**NEU, 'name': 'Anders', 'rev': rev - 1})[0] == 409)
st, r = E.call('sonderangebot_save', {'name': 'Nächste Woche', 'gruppen': ['10'], 'gueltig': {'modus': 'kw', 'jahr': kw_naechste[0], 'kw': kw_naechste[1]}, 'rev': rev})
S2 = r.get('id'); rev = r.get('rev', rev)
check('Sonderangebot für die nächste KW angelegt (ID ohne Umlaute)', st == 200 and S2 == 'sonder-naechste-woche', r)
st, r = E.call('sonderangebot_save', {'name': 'Jahreswechsel', 'gruppen': ['30'], 'gueltig': {'modus': 'kw', 'jahr': '2032', 'kw': '53'}, 'rev': rev})
S53 = r.get('id'); rev = r.get('rev', rev)
st2, r2 = E.call('sonderangebot_save', {'name': 'Neujahr', 'gruppen': ['30'], 'gueltig': {'modus': 'kw', 'jahr': 2033, 'kw': 1}, 'rev': rev})
S01 = r2.get('id'); rev = r2.get('rev', rev)
check('KW 53/2032 (Jahr mit 53 Wochen) und KW 1/2033 angelegt', st == 200 and st2 == 200, (r, r2))
st, lst = A.call('sonderangebote')
row = {z['id']: z for z in lst['sonder']}
check('KW 53/2032: Montag 27.12.2032 bis Sonntag 02.01.2033', row[S53]['von'] == '2032-12-27' and row[S53]['bis'] == '2033-01-02'
      and row[S53]['text'] == 'KW 53/2032 (27.12.2032–02.01.2033)' and row[S53]['gueltig'] == {'modus': 'kw', 'jahr': 2032, 'kw': 53}, row.get(S53))
check('Wochengrenze: KW 1/2033 beginnt am Montag nach dem Sonntag von KW 53', row[S01]['von'] == '2033-01-03' and row[S01]['bis'] == '2033-01-09')
check('Stand: läuft (heute im Zeitraum), geplant (nächste KW)', row[S1]['status'] == 'laeuft' and row[S2]['status'] == 'geplant' and row[S53]['status'] == 'geplant', [(z['name'], z['status']) for z in lst['sonder']])
check('Administrator sieht Kundenzahl je Gruppe und Sonderangebot', lst['kundenZahl'] is True and {g['nr']: g['kunden'] for g in lst['gruppen']} == {'10': 1, '20': 1, '30': 1}
      and row[S1]['kunden'] == 2 and row[S1]['gruppen'] == ['10', '20'], lst['gruppen'])
check('noch ohne Artikel (Entwurf und veröffentlicht)', row[S1]['artikel'] == 0 and row[S1]['veroeffentlicht'] == 0)
ang = doc('angebote')
s1doc = next(o for o in ang['offers'] if o['id'] == S1)
check('gespeichert als Angebot mit eigener Artikelliste, Gruppen nur in sonderGruppen (nie „gruppen“, Rückfall)', s1doc['art'] == 'sonder' and s1doc['fallback'] == 'hidden'
      and s1doc['sonderGruppen'] == ['10', '20'] and 'gruppen' not in s1doc and s1doc['angelegt']['von'] == 'Eddi Editor', s1doc)
check('Kundengruppe 20 behält ihr Kundenangebot (keine 1:1-Regel für Sonderangebote)', next(o for o in ang['offers'] if o['id'] == 'edeka')['gruppen'] == ['20'])
check('doppelter Name abgewiesen', E.call('sonderangebot_save', {**NEU, 'name': 'GRILLWOCHE', 'rev': rev})[0] == 422)

# Grenzen des Stands: Ende heute = läuft, Beginn morgen = geplant, Ende gestern = abgelaufen; vorige KW (endete am Sonntag) abgelaufen
ang = doc('angebote')
ang['offers'] += [
    {'id': 'sonder-t-heute', 'name': 'Ende heute', 'fallback': 'hidden', 'art': 'sonder', 'gueltig': {'modus': 'zeitraum', 'von': tag(-5), 'bis': tag(0)}, 'sonderGruppen': ['10']},
    {'id': 'sonder-t-morgen', 'name': 'Ab morgen', 'fallback': 'hidden', 'art': 'sonder', 'gueltig': {'modus': 'zeitraum', 'von': tag(1), 'bis': tag(4)}, 'sonderGruppen': ['10']},
    {'id': 'sonder-t-gestern', 'name': 'Bis gestern', 'fallback': 'hidden', 'art': 'sonder', 'gueltig': {'modus': 'zeitraum', 'von': tag(-5), 'bis': tag(-1)}, 'sonderGruppen': ['10']},
    {'id': 'sonder-t-vorwoche', 'name': 'Vorige Woche', 'fallback': 'hidden', 'art': 'sonder', 'gueltig': {'modus': 'kw', 'jahr': kw_vorige[0], 'kw': kw_vorige[1]}, 'sonderGruppen': ['10']},
    {'id': 'sonder-t-woche', 'name': 'Diese Woche', 'fallback': 'hidden', 'art': 'sonder', 'gueltig': {'modus': 'kw', 'jahr': kw_jetzt[0], 'kw': kw_jetzt[1]}, 'sonderGruppen': ['10'],
     'zukunft': {'feld': 1}},   # Feld einer neueren Fassung (GR-006)
]
ang['rev'] += 1
storage_write('angebote', ang)
st, lst = E.call('sonderangebote')
stand = {z['id']: z['status'] for z in lst['sonder']}
check('Zeitraum: Ende heute läuft, Beginn morgen geplant, Ende gestern abgelaufen', (stand['sonder-t-heute'], stand['sonder-t-morgen'], stand['sonder-t-gestern']) == ('laeuft', 'geplant', 'abgelaufen'), stand)
check('KW: diese Woche läuft, vorige Woche (Sonntag vorbei) abgelaufen', stand['sonder-t-woche'] == 'laeuft' and stand['sonder-t-vorwoche'] == 'abgelaufen', stand)
check('Bearbeiter ohne Kundenrecht: keine Kundenzahl', lst['kundenZahl'] is False and all(z['kunden'] is None for z in lst['sonder']))
st, r = E.call('sonderangebot_save', {'id': 'sonder-t-woche', 'name': 'Diese Woche', 'gruppen': ['10'], 'gueltig': {'modus': 'kw', 'jahr': kw_jetzt[0], 'kw': kw_jetzt[1]}, 'rev': lst['rev']})
tw = next(o for o in doc('angebote')['offers'] if o['id'] == 'sonder-t-woche')
check('Ändern behält Felder einer neueren Fassung (GR-006)', st == 200 and tw.get('zukunft') == {'feld': 1} and tw['geaendert']['von'] == 'Eddi Editor', tw)
check('Ändern eines unbekannten Sonderangebots: 404', E.call('sonderangebot_save', {**NEU, 'id': 'sonder-gibt-es-nicht', 'rev': r['rev']})[0] == 404)
check('Kundenangebot lässt sich nicht als Sonderangebot ändern (404)', E.call('sonderangebot_save', {**NEU, 'id': 'edeka', 'rev': r['rev']})[0] == 404)
rev = r['rev']

# ---------- Sichtbarkeit vor dem Veröffentlichen ----------
st, ks = K10.call('kunde_status')
check('vor dem Veröffentlichen: Kunde der Gruppe sieht das Sonderangebot nicht', S1 not in [o['id'] for o in ks['kunde']['angebote']], ks['kunde']['angebote'])
check('… und bekommt es nicht ausgeliefert (403)', K10.call('offer&angebot=' + S1)[0] == 403)

# ---------- Artikel ins Sonderangebot (Entwurf) und veröffentlichen ----------
d = A.call('draft')[1]
m = d['draft'] or d['published']
it1, it2 = m['items'][0], m['items'][1]
it1.setdefault('variants', {})[S1] = {'status': 'value', 'value': 9.99}
it2.setdefault('variants', {})[S1] = {'status': 'request'}
neu = {'id': 'sonderX1', 'code': '99001', 'name': 'Grillspieß Sonder', 'category': 'Schwein', 'origin': None, 'condition': 'frisch', 'groupId': it1['groupId'],
       'price': {'status': 'value', 'value': 7.5}, 'altPrices': [], 'variants': {'std': {'status': 'hidden'}, S1: {'status': 'value', 'value': 6.25}, 'sonder-t-woche': {'status': 'value', 'value': 5}}}
m['items'].insert(2, neu)
m.setdefault('meta', {}).setdefault('werbung', {})[S1] = {'titel': 'Grillzeit', 'artikel': [{'id': 'sonderX1'}]}
st, r = A.call('save_draft', {'model': m, 'revision': d['revision']})
check('Entwurf mit Sonderangebotspreisen gespeichert', st == 200, r)
check('Liste zählt Artikel im Entwurf', next(z for z in A.call('sonderangebote')[1]['sonder'] if z['id'] == S1)['artikel'] == 3)
vs = A.call('versand_start')[1]
st, r = A.call('versand_veroeffentlichen', {'revision': vs['aenderungen']['revision']})
check('veröffentlicht (Modul Versand)', st == 200, r)
check('Liste zählt veröffentlichte Artikel', next(z for z in A.call('sonderangebote')[1]['sonder'] if z['id'] == S1)['veroeffentlicht'] == 3)

# ---------- Sichtbarkeit nach dem Veröffentlichen ----------
st, ks = K10.call('kunde_status')
eintrag = next((o for o in ks['kunde']['angebote'] if o['id'] == S1), None)
check('Kunde der Gruppe 10: Sonderangebot in der Angebotsliste mit Kennzeichen und letztem Tag', eintrag == {'id': S1, 'name': 'Grillwoche', 'sonder': True, 'gueltigBis': tag(3)}, ks['kunde']['angebote'])
check('Gruppe 10 ohne eigenes Kundenangebot: Wochenangebot bleibt', ks['kunde']['angebote'][0]['id'] == 'std')
check('KW-Sonderangebot der laufenden Woche ebenfalls sichtbar', 'sonder-t-woche' in [o['id'] for o in ks['kunde']['angebote']])
check('ohne Artikel (Ende heute) bzw. geplant/abgelaufen: nicht gelistet', not {'sonder-t-heute', 'sonder-t-morgen', 'sonder-t-gestern', 'sonder-t-vorwoche', S2} & {o['id'] for o in ks['kunde']['angebote']})
st, r, raw = K10.call('offer&angebot=' + S1, raw=True)
o = r.get('offer', {})
byc = {i['code']: i for i in o.get('items', [])}
check('Kunde bekommt das Sonderangebot aufgelöst (eigene Preise, nur seine Artikel)', st == 200 and len(o['items']) == 3 and byc[it1['code']]['price'] == {'status': 'value', 'value': 9.99}
      and byc[it2['code']]['price'] == {'status': 'request'} and byc['99001']['price']['value'] == 6.25, (st, [(i['code'], i['price']) for i in o.get('items', [])]))
check('… ohne Preisstruktur anderer Angebote (GR-002/GR-005)', '"variants"' not in raw and 'sonder-t-woche' not in raw and '"sale"' not in raw)
check('Kopf: Kennzeichen, Gültigkeit statt Wochen-KW, Werbung des Sonderangebots', o['meta'].get('sonder') is True and o['meta'].get('gueltigVon') == tag(0) and o['meta'].get('gueltigBis') == tag(3)
      and o['meta'].get('week') is None and o['meta']['offerName'] == 'Grillwoche' and ' vom ' in o['meta']['title'] and o['meta'].get('werbung', {}).get('titel') == 'Grillzeit', o['meta'])
st, r = K10.call('offer&angebot=sonder-t-woche')
check('KW-Sonderangebot: Kopf mit dessen KW', st == 200 and r['offer']['meta']['week'] == kw_jetzt[1] and r['offer']['meta']['year'] == kw_jetzt[0]
      and r['offer']['meta']['title'].endswith(f'für die KW {kw_jetzt[1]}/{kw_jetzt[0]}'), r.get('offer', {}).get('meta'))
st, ks20 = K20.call('kunde_status')
ids20 = [o['id'] for o in ks20['kunde']['angebote']]
check('Gruppe 20: Kundenangebot UND Sonderangebot', ids20 == ['edeka', S1], ids20)
check('Gruppe 20 bekommt das Sonderangebot ausgeliefert', K20.call('offer&angebot=' + S1)[0] == 200 and K20.call('offer&angebot=edeka')[0] == 200)
check('andere Kundengruppe (30): nicht gelistet, 403', S1 not in [x['id'] for x in K30.call('kunde_status')[1]['kunde']['angebote']] and K30.call('offer&angebot=' + S1)[0] == 403)
check('Kunde ohne Gruppe: 403', K0.call('offer&angebot=' + S1)[0] == 403)
# direkte Freischaltung beim Kunden (älterer Client) wirkt für Sonderangebote nie
rev_k = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'id': K0id, 'rev': rev_k, 'firma': 'Testkunde K0', 'angebote': ['std', S1]})
check('direkte Freischaltung eines Sonderangebots ist wirkungslos', st == 200 and K0.call('offer&angebot=' + S1)[0] == 403
      and S1 not in r['customer']['angebote'] and S1 not in r['customer']['angeboteDirekt'], r.get('customer', {}).get('angebote'))
anon = Client('198.51.100.30')
check('nicht angemeldet: 401', anon.call('offer&angebot=' + S1)[0] == 401)
st, r, raw = anon.call('offer', raw=True)
pubcodes = {i['code'] for i in r['offer']['items']}
check('öffentliches Wochenangebot unverändert: ohne Sonderpreise und ohne nur-Sonder-Artikel', st == 200 and '99001' not in pubcodes and S1 not in raw and '"variants"' not in raw
      and next(i for i in r['offer']['items'] if i['id'] == it1['id'])['price'] == it1['price'], (pubcodes & {'99001'}, S1 in raw))
check('Mitarbeiter mit Modulzugang sieht jedes Sonderangebot (auch geplant)', L.call('offer&angebot=' + S2)[0] == 200 and L.call('offer&angebot=' + S1)[0] == 200)

# ---------- Bestellwunsch: Preis vom Server aus dem Sonderangebot ----------
assert A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
pub = A.call('draft')[1]['published']
best = {'angebot': S1, 'publishedAt': pub['publishedAt'], 'positions': [{'id': it1['id'], 'qty': 2, 'price': 0.01}], 'requestId': 'sonder-bestellung-0001'}
st, r = K10.call('kunde_bestellung', best)
o1 = next((x for x in doc('bestellungen') if x.get('nr') == r.get('nr')), {}) if st == 200 else {}
check('Bestellwunsch aus dem Sonderangebot: Preis aus dem Sonderangebot (nicht vom Browser)', st == 200 and o1.get('angebot') == S1 and o1['positions'][0]['price'] == 9.99
      and o1['total'] == 19.98, (st, r, o1.get('positions')))
check('Bestellwunsch einer anderen Gruppe abgewiesen (403)', K30.call('kunde_bestellung', {**best, 'requestId': 'sonder-bestellung-0002'})[0] == 403)

# ---------- Versand: „Angebote dieser Woche“ und Wochen-Mail ----------
vs = A.call('versand_start')[1]
va = {a['id']: a for a in vs['angebote']}
check('Versand: laufende Sonderangebote in „Angebote dieser Woche“, mit Gültigkeit', S1 in va and va[S1].get('sonder') is True and va[S1]['von'] == tag(0) and va[S1]['bis'] == tag(3)
      and va[S1]['artikel'] == 3 and va[S1]['kunden'] == 2, va.get(S1))
check('Versand: geplante (andere Woche) und abgelaufene Sonderangebote nicht dabei', not {S2, S53, 'sonder-t-gestern', 'sonder-t-vorwoche', 'sonder-t-morgen'} & set(va))
st, r = A.call('kunden_mail_vorschau', {'type': 'woche', 'id': K10id})
check('Wochen-Mail an Gruppe 10 enthält den Link zum Sonderangebot', st == 200 and '?angebot=' + S1 in r['html'] and 'Grillwoche ansehen' in r['html'], (st, r.get('error')))

# ---------- Beenden und fortsetzen ----------
lst = A.call('sonderangebote')[1]
st, r = E.call('sonderangebot_save', {'id': S1, 'name': 'Grillwoche', 'gruppen': ['10', '20'], 'gueltig': NEU['gueltig'], 'beendet': True, 'rev': lst['rev']})
check('Bearbeiter beendet vorzeitig: sofort nicht mehr sichtbar', st == 200 and K10.call('offer&angebot=' + S1)[0] == 403
      and next(z for z in E.call('sonderangebote')[1]['sonder'] if z['id'] == S1)['status'] == 'beendet', r)
check('beendetes Sonderangebot nicht im Versand', S1 not in {a['id'] for a in A.call('versand_start')[1]['angebote']})
st, r = E.call('sonderangebot_save', {'id': S1, 'name': 'Grillwoche', 'gruppen': ['10', '20'], 'gueltig': NEU['gueltig'], 'beendet': False, 'rev': r['rev']})
check('fortsetzen: wieder sichtbar', st == 200 and K10.call('offer&angebot=' + S1)[0] == 200)
st, r = E.call('sonderangebot_save', {'id': S1, 'name': 'Grillwoche', 'gruppen': ['20'], 'gueltig': NEU['gueltig'], 'rev': r['rev']})
check('Gruppe 10 entfernt: Kunde verliert den Zugang sofort', st == 200 and K10.call('offer&angebot=' + S1)[0] == 403 and K20.call('offer&angebot=' + S1)[0] == 200)
st, r = E.call('sonderangebot_save', {'id': S1, 'name': 'Grillwoche', 'gruppen': ['10', '20'], 'gueltig': NEU['gueltig'], 'rev': r['rev']})

# ---------- Ältere Fenster (offers_save) ----------
offs = A.call('offers')[1]
alt = [dict(o, gruppen=['30'] if o['id'] == S1 else o.get('gruppen', [])) for o in offs['offers']]   # älteres Fenster: Sonderangebot als Kundenangebot mit Gruppe
st, r = A.call('offers_save', {'rev': offs['rev'], 'offers': alt})
s1 = next(o for o in doc('angebote')['offers'] if o['id'] == S1)
check('offers_save ändert Sonderangebote nie (Gruppe aus älterem Fenster ignoriert)', st == 200 and 'gruppen' not in s1 and s1['sonderGruppen'] == ['10', '20']
      and K30.call('offer&angebot=' + S1)[0] == 403, s1)
offs = A.call('offers')[1]
nur = [o for o in offs['offers'] if o.get('art') != 'sonder']
st, r = A.call('offers_save', {'rev': offs['rev'], 'offers': nur})
check('offers_save ohne Sonderangebote löscht sie nicht (keine Bestätigung nötig)', st == 200 and len([o for o in r['offers'] if o.get('art') == 'sonder']) == 9, (st, r.get('error')))
offs = A.call('offers')[1]
st, r = A.call('offers_save', {'rev': offs['rev'], 'offers': nur + [{'id': '', 'name': 'Grillwoche', 'fallback': 'hidden', 'gruppen': []}]})
check('Kundenangebot mit dem Namen eines Sonderangebots abgewiesen', st == 422)
st, r = A.call('offers_save', {'rev': offs['rev'], 'offers': nur + [{'id': 'sonder-neu', 'name': 'Neu', 'fallback': 'hidden', 'gruppen': []}]})
check('neues Kundenangebot mit „sonder-“-ID abgewiesen', st == 422 and 'vorbehalten' in r.get('error', ''), r)

# ---------- Löschen ----------
lst = A.call('sonderangebote')[1]
check('Bearbeiter darf nicht löschen (403)', E.call('sonderangebot_loeschen', {'id': 'sonder-t-gestern', 'rev': lst['rev']})[0] == 403)
check('Leser darf nicht löschen (403)', L.call('sonderangebot_loeschen', {'id': 'sonder-t-gestern', 'rev': lst['rev']})[0] == 403)
st, r = A.call('sonderangebot_loeschen', {'id': 'sonder-t-gestern', 'rev': lst['rev']})
if st == 403 and r.get('code') == 'confirmation_required':   # Lauf unter Last länger als die Bestätigung gilt
    A.call('reauth', {'password': PW}); st, r = A.call('sonderangebot_loeschen', {'id': 'sonder-t-gestern', 'rev': lst['rev']})
check('Administrator löscht (mit Bestätigung)', st == 200 and 'sonder-t-gestern' not in [o['id'] for o in r['offers']] and 'sonder-t-gestern' in doc('angebote')['geloescht'], (st, r))
check('Kundenangebot lässt sich hier nicht löschen (404)', A.call('sonderangebot_loeschen', {'id': 'edeka', 'rev': r['rev']})[0] == 404)
st, r2 = E.call('sonderangebot_save', {'name': 'T Gestern', 'gruppen': ['10'], 'gueltig': NEU['gueltig'], 'rev': r['rev']})
check('gelöschte ID wird nie wieder vergeben', st == 200 and r2['id'] == 'sonder-t-gestern-2', r2.get('id'))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: angelegt, geändert, gelöscht', 'Sonderangebot angelegt: Grillwoche' in log and 'Sonderangebot geändert: Grillwoche' in log and 'Sonderangebot gelöscht: Bis gestern' in log)


# ======================= Oberfläche =======================
def login(pg, user='admin', pw=PW):
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) #offer-bar:not([hidden])')


def wait_saved(pg):
    pg.wait_for_function("!/pending|saving/.test(document.querySelector('#save-state').className)", timeout=15000)


def karte(pg, name):
    return pg.locator(f'#view-sonder .so-k:has(h3:text-is("{name}"))')


def zeilen(pg):   # Artikelzeilen der Liste (ohne die Werbung oben)
    return pg.evaluate("[...document.querySelectorAll('tr.row')].filter((r) => !r.closest('.werb-sec, .werb-al')).length")


def kein_ueberlauf(pg):
    return pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append('admin: ' + str(e)))
    login(a)

    # ---------- Navigation: Reiter direkt unter „Einzelangebote“ ----------
    reihe = a.evaluate("[...document.querySelectorAll('.side-tabs [role=tab]')].filter((b) => !b.hidden).map((b) => b.id)")
    check('Reiter „Sonderangebote“ direkt unter „Einzelangebote“', reihe.index('vt-sonder') == reihe.index('vt-einzel') + 1 and a.locator('#vt-sonder').is_visible()
          and a.inner_text('#vt-sonder').strip() == 'Sonderangebote', reihe)
    check('Angebotsleiste: Abschnitt „Sonderangebote“ mit laufenden und geplanten, ohne abgelaufene', a.locator('#offer-bar .ob-sonder [data-offer="sonder-grillwoche"]').count() == 1
          and a.locator('#offer-bar .ob-sonder [data-offer="sonder-naechste-woche"]').count() == 1 and a.locator('#offer-bar [data-offer="sonder-t-vorwoche"]').count() == 0
          and 'sonderangebote' in a.inner_text('#offer-bar').lower(), a.locator('#offer-bar [data-offer]').evaluate_all('e => e.map(x => x.dataset.offer + ":" + (x.closest(".ob-tabs") || {}).className)'))

    # ---------- Liste ----------
    a.click('#vt-sonder'); a.wait_for_selector('#view-sonder .so-k')
    check('Liste nach Stand: läuft, geplant, abgelaufen (zugeklappt)', karte(a, 'Grillwoche').locator('.so-st').inner_text() == 'läuft'
          and a.locator('#view-sonder .so-sec.laeuft .so-k:has-text("Grillwoche")').count() == 1 and a.locator('#view-sonder .so-sec.geplant .so-k:has-text("Nächste Woche")').count() == 1
          and a.locator('#view-sonder details.so-sec.vorbei:not([open])').count() == 1)
    g = karte(a, 'Grillwoche')
    check('Karte: Gültigkeit, Gruppen mit Namen, Artikel, veröffentlicht, Kunden', g.locator('.so-zeit').inner_text().strip() == f'{tag(0)[8:]}.{tag(0)[5:7]}.{tag(0)[:4]} – {tag(3)[8:]}.{tag(3)[5:7]}.{tag(3)[:4]}'
          and '10 · Gastronomie' in g.inner_text() and '20 · Handel' in g.inner_text() and g.locator('.so-zahlen dd').all_inner_texts() == ['3', '3', '2'], g.inner_text())
    check('Karte ohne Artikel: Hinweis zum Hinzufügen', 'Noch keine Artikel' in karte(a, 'T Gestern').inner_text())
    a.fill('#so-q', 'großhandel')
    a.wait_for_function("document.querySelectorAll('#view-sonder .so-k').length === 2")
    check('Suche nach Kundengruppe (Name)', sorted(a.locator('#view-sonder .so-k h3').all_inner_texts()) == ['Jahreswechsel', 'Neujahr'])
    a.fill('#so-q', ''); a.wait_for_function("document.querySelectorAll('#view-sonder .so-k').length > 2")
    shot(a, SH + '/sonderangebote-liste.png')

    # ---------- Neues Sonderangebot: Kippschalter Zeitraum ↔ KW ----------
    a.click('#so-neu'); a.wait_for_selector('#dlg-sonder[open] #so-name')
    check('Fenster: Zeitraum vorgewählt (Schalter aus), Beginn heute', a.get_attribute('#so-modus', 'aria-checked') == 'false' and a.input_value('#sonder-body [name=von]') == tag(0)
          and a.locator('#sonder-body [name=kw]').count() == 0)
    a.fill('#so-name', 'Wurstwoche')
    a.fill('#sonder-body [name=von]', tag(2)); a.fill('#sonder-body [name=bis]', tag(1))
    a.wait_for_function("document.querySelector('#so-tage').classList.contains('warn')")
    check('Hinweis: Ende vor Beginn', 'Ende liegt vor dem Beginn' in a.inner_text('#so-tage'))
    a.click('#so-modus'); a.wait_for_selector('#sonder-body [name=kw]')
    kwb = datetime.date.fromisoformat(tag(2)).isocalendar()
    check('Kippschalter → Kalenderwoche des Beginns, Montag bis Sonntag', a.get_attribute('#so-modus', 'aria-checked') == 'true' and a.input_value('#sonder-body [name=kw]') == str(kwb[1])
          and a.input_value('#sonder-body [name=jahr]') == str(kwb[0]) and a.inner_text('#so-tage').startswith('Mo ') and ' bis So ' in a.inner_text('#so-tage') and '7 Tage' in a.inner_text('#so-tage'), a.inner_text('#so-tage'))
    a.fill('#sonder-body [name=kw]', str(kw_naechste[1])); a.fill('#sonder-body [name=jahr]', str(kw_naechste[0]))
    a.click('#sonder-body [data-modus=zeitraum]'); a.wait_for_selector('#sonder-body [name=von]')
    mo = naechste - datetime.timedelta(days=naechste.weekday())
    check('zurück zum Zeitraum: Montag bis Sonntag der gewählten KW übernommen', a.input_value('#sonder-body [name=von]') == iso(mo) and a.input_value('#sonder-body [name=bis]') == iso(mo + datetime.timedelta(days=6)))
    a.click('#sonder-body [data-modus=kw]'); a.wait_for_selector('#sonder-body [name=kw]')
    a.click('#sonder-body [type=submit]'); a.wait_for_function("document.querySelector('#so-err').textContent.length > 0")
    check('ohne Kundengruppe: Hinweis, nichts gespeichert', 'Kundengruppe' in a.inner_text('#so-err') and not any(o['name'] == 'Wurstwoche' for o in doc('angebote')['offers']))
    a.fill('#so-gq', 'gastro'); a.wait_for_function("[...document.querySelectorAll('#sonder-body .so-glist li')].filter((l) => !l.hidden).length === 1")
    a.check('#sonder-body .so-glist input[value="10"]')
    check('Gruppen: Anzahl und Kunden', '1 Gruppe gewählt · 1 Kunde' in a.inner_text('#so-gn'), a.inner_text('#so-gn'))
    shot(a, SH + '/sonderangebote-neu.png')
    a.click('#sonder-body [type=submit]')
    a.wait_for_selector('#view-edit:not([hidden]) #offer-head:has-text("Wurstwoche")')
    neu = next((o for o in doc('angebote')['offers'] if o['name'] == 'Wurstwoche'), {})
    check('angelegt mit KW und Gruppe, Editor öffnet das neue Sonderangebot', neu.get('gueltig') == {'modus': 'kw', 'jahr': kw_naechste[0], 'kw': kw_naechste[1]} and neu.get('sonderGruppen') == ['10']
          and a.get_attribute(f'#offer-bar [data-offer="{neu.get("id")}"]', 'aria-selected') == 'true' and a.inner_text('#offer-head .oh-art').lower() == 'sonderangebot',
          (neu, a.get_attribute(f'#offer-bar [data-offer="{neu.get("id")}"]', 'aria-selected'), a.inner_text('#offer-head .oh-art')))
    SW = neu['id']
    check('Kopf: Gültigkeit und Stand, leere Artikelliste', f'KW {kw_naechste[1]}/{kw_naechste[0]} · geplant' in a.inner_text('#offer-head') and 'Noch keine Artikel in diesem Angebot' in a.inner_text('#groups'))

    # ---------- Artikel aus einem anderen Angebot übernehmen (Auswahl einzelner Artikel) ----------
    a.click('#offer-head [data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open] #oc-list li[data-hay]')
    check('Übernehmen: für ein Sonderangebot ist zunächst nichts gewählt, Knopf gesperrt', a.locator('#oc-list input:checked').count() == 0 and a.is_disabled('#offer-copy-body [type=submit]')
          and '0 von ' in a.inner_text('#oc-n'))
    check('Quellen: Wochenangebot, Kundenangebote, laufende/geplante Sonderangebote – ohne abgelaufene', a.locator('#offer-copy-body [name=src] option[value=std]').count() == 1
          and a.locator('#offer-copy-body [name=src] option[value=edeka]').count() == 1 and a.locator('#offer-copy-body [name=src] option[value="sonder-t-vorwoche"]').count() == 0)
    c1, c2 = it1['code'], m['items'][3]['code']
    a.fill('#oc-q', c1); a.wait_for_function("[...document.querySelectorAll('#oc-list li[data-hay]')].filter((l) => !l.hidden).length >= 1")
    a.locator('#oc-list li[data-hay]:not([hidden]) input').first.check()
    a.fill('#oc-q', c2); a.wait_for_function("[...document.querySelectorAll('#oc-list li[data-hay]')].filter((l) => !l.hidden).length >= 1")
    a.locator('#oc-list li[data-hay]:not([hidden]) input').first.check()
    check('zwei Artikel gewählt (Suche behält die Auswahl)', '2 von ' in a.inner_text('#oc-n') and a.is_enabled('#offer-copy-body [type=submit]'), a.inner_text('#oc-n'))
    a.fill('#offer-copy-body [name=pct]', '-10')
    shot(a, SH + '/sonderangebote-uebernehmen.png')
    a.click('#offer-copy-body [type=submit]'); a.wait_for_selector('#dlg-offer-copy', state='hidden')
    a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 2")
    wait_saved(a)
    ent = A.call('draft')[1]['draft']
    vs_ = {i['code']: i['variants'][SW] for i in ent['items'] if SW in (i.get('variants') or {})}
    erw = round(round(it1['price']['value'] * 0.9 / 0.05) * 0.05, 2)
    check('übernommen: nur die gewählten Artikel mit Abschlag, Wochenangebot unverändert', set(vs_) == {c1, c2} and abs(vs_[c1]['value'] - erw) < 0.001
          and not any(i.get('variants', {}).get('std', {}).get('status') == 'hidden' for i in ent['items'] if i['code'] in (c1, c2)), vs_)
    pin = a.locator(f'#groups tr[data-id]:has(input[data-f="code"][value="{c1}"]) input[data-f=vprice]')
    pin.fill('12,34'); pin.press('Tab'); wait_saved(a)
    check('Preis im Sonderangebot geändert (wie bei Kundenangeboten)', next(i for i in A.call('draft')[1]['draft']['items'] if i['code'] == c1)['variants'][SW]['value'] == 12.34)
    shot(a, SH + '/sonderangebote-editor.png')
    st, r = A.call('offer&angebot=' + SW + '&draft=1')   # Vorschau und Drucken des Editors lesen den Entwurf so
    check('Vorschau des Entwurfs: nur die übernommenen Artikel, Kopf mit der KW des Sonderangebots', st == 200 and r.get('preview') is True and len(r['offer']['items']) == 2
          and r['offer']['meta'].get('sonder') is True and r['offer']['meta']['week'] == kw_naechste[1] and '"variants"' not in json.dumps(r), (st, r.get('offer', {}).get('meta')))
    check('Vorschau des Entwurfs nur für Mitarbeiter (Kunde 403/401)', K10.call('offer&angebot=' + SW + '&draft=1')[0] in (401, 403) and anon.call('offer&angebot=' + SW + '&draft=1')[0] == 401)

    # ---------- Kopf → „Gültigkeit und Gruppen“ ----------
    a.click('#offer-head [data-ob=sonder]'); a.wait_for_selector('#dlg-sonder[open] #so-name')
    check('Knopf im Kopf öffnet das Fenster des Sonderangebots', a.input_value('#so-name') == 'Wurstwoche' and a.get_attribute('#so-modus', 'aria-checked') == 'true'
          and a.get_attribute('#vt-sonder', 'aria-selected') == 'true')
    a.fill('#so-name', 'Wurstwoche Gastro'); a.click('#sonder-body [type=submit]'); a.wait_for_selector('#dlg-sonder', state='hidden')
    a.wait_for_selector('#view-sonder .so-k h3:text-is("Wurstwoche Gastro")')
    w = karte(a, 'Wurstwoche Gastro')
    check('umbenannt; Karte: 2 Artikel im Entwurf, noch nicht veröffentlicht', w.locator('.so-zahlen dd').all_inner_texts()[:2] == ['2', '0'] and 'Noch nicht veröffentlicht' in w.inner_text())

    # ---------- Beenden, fortsetzen, löschen ----------
    w.locator('[data-so=beenden]').click(); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_selector('#view-sonder details.so-sec.vorbei .so-k:has(h3:text-is("Wurstwoche Gastro")) .so-st.beendet', state='attached')
    check('beendet: unter „Abgelaufen und beendet“, Knopf „Fortsetzen“', karte(a, 'Wurstwoche Gastro').locator('[data-so=fortsetzen]').count() == 1)
    a.locator('#view-sonder details.so-sec.vorbei summary').click()
    karte(a, 'Wurstwoche Gastro').locator('[data-so=fortsetzen]').click()
    a.wait_for_selector('#view-sonder .so-sec.geplant .so-k:has(h3:text-is("Wurstwoche Gastro"))')
    check('fortgesetzt: wieder geplant', 'beendet' not in next(o for o in doc('angebote')['offers'] if o['id'] == SW))
    karte(a, 'Ab morgen').locator('[data-so=loeschen]').click(); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("(() => { const t = document.querySelector('#toast'); return t && t.classList.contains('show') && /gelöscht|bestätigen|Passwort/.test(t.textContent) || !!document.querySelector('#dlg-reauth[open]'); })()")
    if a.locator('#dlg-reauth[open]').count():
        a.fill('#reauth-password', PW); a.click('#reauth-submit')
    a.wait_for_function("!document.querySelector('#view-sonder .so-k h3') || ![...document.querySelectorAll('#view-sonder .so-k h3')].some((h) => h.textContent === 'Ab morgen')")
    check('gelöscht (Administrator)', not any(o['id'] == 'sonder-t-morgen' for o in doc('angebote')['offers']) and a.locator('#offer-bar [data-offer="sonder-t-morgen"]').count() == 0)

    # ---------- Stammdaten → Angebote und Kunden: ohne Sonderangebote ----------
    a.click('#vt-angebote'); a.wait_for_selector('#view-angebote tr[data-oi]')
    check('Angebote verwalten zeigt keine Sonderangebote', 'Grillwoche' not in a.inner_text('#view-angebote') and a.locator('#view-angebote tr[data-oi]').count() == 4)
    a.locator('#view-angebote [data-of=name]').first.fill('Wochenangebot Chefs Culinar 2')
    a.click('[data-ofa=save]'); a.wait_for_selector('#toast.show:has-text("Angebote gespeichert")')
    check('… Speichern dort lässt alle Sonderangebote stehen', len([o for o in doc('angebote')['offers'] if o.get('art') == 'sonder']) == 9)
    a.click('#vt-kunden'); a.wait_for_selector('#view-kunden tr[data-kid]')
    a.locator('#view-kunden tr[data-kid]:has-text("Testkunde K10")').click(); a.wait_for_selector('#dlg-kunde[open]')
    werte = a.locator('#kunde-body [name=angebot]').evaluate_all('e => e.map(x => x.value)')
    check('Kunde: Sonderangebote nicht direkt freischaltbar', werte and not any(v.startswith('sonder-') for v in werte), werte)
    a.click('#kunde-body [data-close]'); a.wait_for_selector('#dlg-kunde', state='hidden')

    # ---------- Handy 390 px, hell und dunkel ----------
    for schema in ('light', 'dark'):
        mctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, color_scheme=schema)
        mp = mctx.new_page(); mp.on('pageerror', lambda e: errors.append('mobil: ' + str(e)))
        login(mp)
        mp.goto(BASE + '/admin/#sonder'); mp.wait_for_selector('#view-sonder:not([hidden]) .so-k')
        check(f'390 px ({schema}): Liste ohne waagerechtes Scrollen, Karten einspaltig', kein_ueberlauf(mp)
              and mp.evaluate("(() => { const k = [...document.querySelectorAll('#view-sonder .so-sec:not(details) .so-k')]; return k.length > 1 && k[0].getBoundingClientRect().left === k[1].getBoundingClientRect().left; })()"))
        shot(mp, SH + f'/sonderangebote-390-{schema}.png')
        karte(mp, 'Grillwoche').locator('[data-so=einstellungen]').click(); mp.wait_for_selector('#dlg-sonder[open] #so-name')
        knopf = mp.locator('#so-modus').bounding_box()
        check(f'390 px ({schema}): Fenster passt, Kippschalter groß genug', kein_ueberlauf(mp) and knopf['height'] >= 28 and mp.evaluate("document.querySelector('#dlg-sonder').getBoundingClientRect().right <= window.innerWidth + 1"), knopf)
        shot(mp, SH + f'/sonderangebote-390-fenster-{schema}.png')
        mp.click('#sonder-body [data-close]')
        mctx.close()

    # ---------- Kundenseite ----------
    for breite, schema in ((1280, 'light'), (390, 'dark')):
        cctx = br.new_context(viewport={'width': breite, 'height': 900}, color_scheme=schema, is_mobile=breite < 500, has_touch=breite < 500)
        c = cctx.new_page(); c.on('pageerror', lambda e: errors.append('kunde: ' + str(e)))
        c.goto(BASE + '/?angebot=' + S1); c.wait_for_selector('#dlg-kunde-login[open]')
        c.fill('#kl-form [name=username]', 'k10'); c.fill('#kl-form [name=password]', KPW); c.click('#kl-form [type=submit]')
        c.wait_for_selector('tr.row')
        check(f'Kundenseite {breite} px: Sonderangebot mit Name, Gültigkeit statt KW, nur seine Artikel', 'Grillwoche' in c.inner_text('#topbar h1') and c.inner_text('#kw-pill').startswith('gültig ')
              and zeilen(c) == 3 and kein_ueberlauf(c), (c.inner_text('#kw-pill'), zeilen(c)))
        check(f'Kundenseite {breite} px: Werbung des Sonderangebots, Umschalter mit Enddatum', 'Grillzeit' in c.inner_text('body') and c.locator(f'[data-kswitch="{S1}"] .k-bis').count() >= 1)
        shot(c, SH + f'/sonderangebote-kunde-{breite}-{schema}.png')
        cctx.close()

    check('keine JavaScript-Fehler', not errors, errors[:5])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
