"""Einzelangebote (Angebot bearbeiten → Einzelangebote): Angebot für genau einen Kunden. Rechte, Prüfung, Artikelsuche mit
Bestand (eingelagert, erfasst, gesamt verfügbar) und Wochenangebotspreis, Freigabe im Portal, Bestellwunsch mit Preisen
vom Server, Zurückziehen, Ablauf, E-Mail (Test-Mailserver), Oberfläche mit Abweichungspunkt, Druck und Portalansicht.
Nur synthetische Testdaten; es werden keine echten E-Mails versendet."""
import json
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

import urllib.request

from auth_helpers import expire_session
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SH, SMTP_PORT, storage_raw, storage_write, until

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def bestaetigung_ablaufen(cl):
    jar = next(h.cookiejar for h in cl.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor))
    expire_session(next(c.value for c in jar if c.name == 'WA_ADMIN'))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}


def kunde(username, firma, email=None, zugang=True):
    rev = A.call('kunden')[1]['rev']
    body = {'rev': rev, 'firma': firma, 'nr': username.upper()[:10], 'ansprechpartner': 'Frau Probe', 'strasse': 'Testweg 1', 'plz': '20095', 'ort': 'Hamburg',
            'email': email if email is not None else username + '@example.org', 'active': True, 'angebote': ['std']}
    if zugang:
        body['login'] = {'username': username, 'password': KPW, 'mustChange': False, 'active': True}
    st, r = A.call('kunde_save', body)
    assert st == 200, r
    return r['customer']['id']


kid = kunde('kantine.einzel', 'Kantine <Einzel>')
kid2 = kunde('kantine.andere', 'Andere Kantine')
kid3 = kunde('ohne.mail', 'Ohne Mail GmbH', email='', zugang=False)
K = Client('203.0.113.10'); assert K.call('kunde_login', {'username': 'kantine.einzel', 'password': KPW})[0] == 200
K2 = Client('203.0.113.11'); assert K2.call('kunde_login', {'username': 'kantine.andere', 'password': KPW})[0] == 200
assert A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200

# synthetischer Bestand: 10601 eingelagert + erfasst, 10823 nur erfasst, 900001 nur Bestand (nicht im Wochenangebot)
STOCK = {'date': '2026-10-19', 'source': 'Synthetische Testdaten',
         'articles': [{'code': '10601', 'name': 'Roastbeef, frisch', 'kg': 40, 'mhd': '2026-11-20', 'mhdKg': 15,
                       'lots': [{'lot': 'P-0001', 'arrival': '2026-10-02', 'mhd': '2026-11-20', 'kolli': 3, 'kg': 15, 'ek': 18.5},
                                {'lot': 'P-0002', 'arrival': '2026-10-09', 'mhd': '2026-12-04', 'kolli': 5, 'kg': 25, 'ek': 19.25}]},
                      {'code': '900001', 'name': 'Test Nur Bestand', 'kg': 5.5, 'lots': []}],
         'incoming': [{'code': '10601', 'name': 'Roastbeef, frisch', 'kg': 10, 'arrival': '2026-10-22', 'lot': 'TEST-A'},
                      {'code': '10823', 'name': 'Steakhüfte, frisch', 'kg': 12, 'arrival': None, 'lot': 'TEST-B'}]}
assert A.call('stock_import', STOCK)[0] == 200
# synthetische VK-Gruppen und Zuordnung in den Artikelstammdaten
assert A.call('vkgruppen_save', {'rev': A.call('vkgruppen')[1]['rev'], 'groups': [{'nr': '1600', 'name': 'Rindfleisch, Argentinien, frisch'},
              {'nr': '1610', 'name': 'Rindfleisch, Uruguay, frisch'}, {'nr': '6150', 'name': 'Rindfleisch, Irland, gefroren'}, {'nr': '7000', 'name': 'Geflügel, ungenutzt'}]})[0] == 200
VK = {'10601': '1600', '10701': '1600', '10823': '1610', '900001': '6150'}
assert A.call('master_save', {'rev': A.call('master')[1]['master']['rev'], 'articles': [
    {'code': '10601', 'name': 'Roastbeef, frisch', 'category': 'Rind', 'origin': 'AR', 'condition': 'frisch', 'vkGruppe': '1600'},
    {'code': '10701', 'name': 'Entrecote, frisch', 'category': 'Rind', 'origin': 'AR', 'condition': 'frisch', 'vkGruppe': '1600'},
    {'code': '10823', 'name': 'Steakhüfte, frisch', 'category': 'Rind', 'origin': 'UY', 'condition': 'frisch', 'vkGruppe': '1610'},
    {'code': '900001', 'name': 'Test Nur Bestand', 'category': 'Rind', 'origin': 'IRL', 'condition': 'gefroren', 'vkGruppe': '6150'}]})[0] == 200

# ---------- Rechte ----------
check('ohne Anmeldung gesperrt', Client().call('einzel_liste')[0] == 401)
check('Bearbeiter (Standard) sieht keine Einzelangebote', E.call('einzel_liste')[0] == 403 and E.call('einzel_artikel')[0] == 403)
check('Bearbeiter (Standard) darf nicht anlegen', E.call('einzel_save', {'kid': kid, 'positions': []})[0] == 403)
check('Kunde kann Mitarbeiter-Aktionen nicht nutzen', K.call('einzel_liste')[0] == 401 and K.call('einzel_save', {'kid': kid})[0] in (401, 403))
st, r = A.call('einzel_liste')
check('Administrator: Liste leer', st == 200 and r['list'] == [])
check('Speichern nur per POST', A.call('einzel_save')[0] == 405)
st, r = A.call('user_save', {'id': uid['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': ['kunden.sehen', 'einzelangebote.sehen'], 'deny': []})
check('Leser bekommt Recht „Einzelangebote ansehen“', st == 200, r)
check('… sieht die Liste, darf aber nicht anlegen oder suchen', L.call('einzel_liste')[0] == 200 and L.call('einzel_save', {'kid': kid, 'positions': []})[0] == 403 and L.call('einzel_artikel')[0] == 403)

# ---------- Artikelsuche ----------
st, r = A.call('einzel_artikel')
art = {a['code']: a for a in r.get('articles', [])}
check('Artikelsuche: Bestand und Wochenangebot geladen', st == 200 and r['bestand']['date'] == '2026-10-19' and r['angebot']['week'] == 43, {k: r.get(k) for k in ('bestand', 'angebot')})
a = art.get('10601', {})
check('eingelagert, erfasst, gesamt verfügbar und Wochenpreis', a.get('kg') == 40 and a.get('incomingKg') == 10 and a.get('totalKg') == 50 and a.get('stdPrice', {}).get('value') == 25.54 and a.get('inOffer'), a)
a = art.get('10823', {})
check('nur erfasster Bestand zählt zu gesamt verfügbar', a.get('kg') == 0 and a.get('incomingKg') == 12 and a.get('totalKg') == 12, a)
a = art.get('10701', {})
check('Artikel ohne Bestand: gesamt 0', a.get('totalKg') == 0 and a.get('stdPrice', {}).get('value') == 27.21, a)
a = art.get('900001', {})
check('Artikel nur im Bestand (nicht im Wochenangebot)', a.get('totalKg') == 5.5 and not a.get('inOffer') and a.get('stdPrice') is None, a)
check('VK-Gruppe und Merkmale je Artikel aus den Stammdaten', all(art[c].get('vk') == v for c, v in VK.items()) and art['10823'].get('origin') == 'UY' and art['10701'].get('condition') == 'frisch',
      {c: art[c].get('vk') for c in VK})
check('ohne VK-Gruppe: vk leer', all(x.get('vk') is None for c, x in art.items() if c not in VK))
st, r = A.call('einzel_artikel')
check('VK-Gruppen mit Bezeichnung und Anzahl, nur vorkommende', r['vkGruppen'] == [{'nr': '1600', 'name': 'Rindfleisch, Argentinien, frisch', 'anzahl': 2},
      {'nr': '1610', 'name': 'Rindfleisch, Uruguay, frisch', 'anzahl': 1}, {'nr': '6150', 'name': 'Rindfleisch, Irland, gefroren', 'anzahl': 1}], r['vkGruppen'])
a = art['10601']
check('Partien je Artikel mit Eingang, MHD, Kolli, kg und EK (Administrator)', r['ek'] is True and a.get('lots') == [
      {'lot': 'P-0001', 'arrival': '2026-10-02', 'mhd': '2026-11-20', 'kolli': 3, 'kg': 15, 'ek': 18.5}, {'lot': 'P-0002', 'arrival': '2026-10-09', 'mhd': '2026-12-04', 'kolli': 5, 'kg': 25, 'ek': 19.25}], a.get('lots'))
check('erwartete Ankünfte je Artikel mit Partie und ETA', a.get('incoming') == [{'lot': 'TEST-A', 'arrival': '2026-10-22', 'kg': 10}]
      and art['10823'].get('incoming') == [{'lot': 'TEST-B', 'arrival': None, 'kg': 12}] and art['10701'].get('lots') == [] and art['10701'].get('incoming') == [], a.get('incoming'))
st, r = A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True,
                              'grant': ['kunden.sehen', 'einzelangebote.sehen', 'einzelangebote.bearbeiten'], 'deny': ['bestand.einkaufspreise']})
st, r = E.call('einzel_artikel')
e10601 = next((x for x in r.get('articles', []) if x['code'] == '10601'), {})
check('ohne Recht „Einkaufspreise“: Partien ohne EK', st == 200 and r['ek'] is False and len(e10601.get('lots', [])) == 2 and all('ek' not in l for l in e10601['lots'])
      and '18.5' not in json.dumps(r), e10601.get('lots'))
st, r = A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True,
                              'grant': ['kunden.sehen', 'einzelangebote.sehen', 'einzelangebote.bearbeiten'], 'deny': ['bestand.sehen']})
check('Bearbeiter bekommt Einzelangebote, aber keinen Bestand', st == 200, r)
st, r = E.call('einzel_artikel')
e10601 = next((x for x in r.get('articles', []) if x['code'] == '10601'), {})
check('ohne Bestandsrecht: Artikelsuche ohne Mengen', st == 200 and r['bestand'] is None and 'kg' not in e10601 and 'totalKg' not in e10601 and e10601.get('stdPrice', {}).get('value') == 25.54, e10601)
check('ohne Bestandsrecht: keine Partien, Ankünfte oder EK', 'lots' not in e10601 and 'incoming' not in e10601 and not r['ek'] and 'P-0001' not in json.dumps(r) and 'TEST-A' not in json.dumps(r)
      and e10601.get('vk') == '1600', e10601)

# ---------- Prüfung ----------
bis = (date.today() + timedelta(days=10)).isoformat()
POS = [{'code': '10601', 'name': 'Roastbeef, frisch', 'qty': 10, 'price': 23.9, 'notiz': 'gereift'}, {'code': '', 'name': 'Freie Position', 'qty': None, 'price': None}]
check('Kunde fehlt → 422', A.call('einzel_save', {'kid': '', 'positions': POS})[0] == 422)
check('unbekannter Kunde → 422', A.call('einzel_save', {'kid': 'kxxxxxx', 'positions': POS})[0] == 422)
check('ungültiges Datum → 422', A.call('einzel_save', {'kid': kid, 'gueltigBis': '2026-02-30', 'positions': POS})[0] == 422)
check('negativer Preis → 422', A.call('einzel_save', {'kid': kid, 'positions': [{'code': '1', 'name': 'X', 'price': -1}]})[0] == 422)
check('Menge 0 → 422', A.call('einzel_save', {'kid': kid, 'positions': [{'code': '1', 'name': 'X', 'qty': 0}]})[0] == 422)
check('Position ohne Bezeichnung → 422', A.call('einzel_save', {'kid': kid, 'positions': [{'code': '1', 'name': ' '}]})[0] == 422)
check('ungültige Artikelnummer → 422', A.call('einzel_save', {'kid': kid, 'positions': [{'code': '<b>', 'name': 'X'}]})[0] == 422)
check('zu viele Positionen → 422', A.call('einzel_save', {'kid': kid, 'positions': [{'code': '1', 'name': 'X'}] * 301})[0] == 422)

st, r = E.call('einzel_save', {'id': '', 'kid': kid, 'titel': 'Grillsaison <Spezial>', 'gueltigBis': bis, 'hinweis': 'Lieferung Dienstag', 'positions': POS})
e1 = r.get('angebot', {})
check('Bearbeiter legt Einzelangebot an (Nummer, Entwurf)', st == 200 and e1['nr'] == f'E-{date.today().year}-0001' and e1['status'] == 'entwurf' and e1['revision'] == 1
      and e1['firma'] == 'Kantine <Einzel>' and e1['positions'][0]['price'] == 23.9 and e1['positions'][1]['price'] is None and e1['summen'] == {'kg': 10, 'summe': 239.0}, e1)
EID = 'e-' + e1['id']
check('Liste zeigt Anzahl Positionen ohne Positionsdaten', (lambda l: len(l) == 1 and l[0]['positionCount'] == 2 and 'positions' not in l[0])(A.call('einzel_liste')[1]['list']))
check('Protokoll: Einzelangebot angelegt', 'Einzelangebot ' + e1['nr'] + ' für „Kantine <Einzel>“ angelegt' in json.dumps(A.call('log')[1], ensure_ascii=False))
check('Entwurf ist für den Kunden unsichtbar', not any(o['id'] == EID for o in K.call('kunde_status')[1]['kunde']['angebote']) and K.call('offer&angebot=' + EID)[0] == 403)
check('Freigabe ohne Positionen abgewiesen', (lambda r: A.call('einzel_status', {'id': r['angebot']['id'], 'revision': 1, 'status': 'freigegeben'})[0] == 422)(A.call('einzel_save', {'kid': kid2, 'positions': []})[1]))
st, r = E.call('einzel_save', {'id': e1['id'], 'revision': 7, 'kid': kid, 'positions': POS})
check('veraltete Revision → 409', st == 409)
check('veraltete Revision beim Status → 409', E.call('einzel_status', {'id': e1['id'], 'revision': 0, 'status': 'freigegeben'})[0] == 409)
check('unbekannter Status → 422', E.call('einzel_status', {'id': e1['id'], 'revision': 1, 'status': 'offen'})[0] == 422)

# ---------- Freigabe und Portal ----------
st, r = E.call('einzel_status', {'id': e1['id'], 'revision': 1, 'status': 'freigegeben'})
e1 = r.get('angebot', {})
check('im Portal freigegeben', st == 200 and e1['status'] == 'freigegeben' and e1['sichtbar'] and e1['freigegebenAt'], e1)
ang = K.call('kunde_status')[1]['kunde']['angebote']
check('Kunde sieht das Einzelangebot neben dem Wochenangebot', [o['id'] for o in ang] == ['std', EID] and ang[1]['name'] == 'Grillsaison <Spezial>' and ang[1]['gueltigBis'] == bis, ang)
st, r = K.call('offer&angebot=' + EID)
off = r.get('offer', {})
check('Angebot im Portal: Positionen mit Preis, Notiz am Namen', st == 200 and [i['price'] for i in off['items']] == [{'status': 'value', 'value': 23.9}, {'status': 'request'}]
      and off['items'][0]['name'] == 'Roastbeef, frisch – gereift' and off['meta']['einzel'] and off['publishedAt'] == e1['freigegebenAt'], off.get('items'))
txt = json.dumps(off, ensure_ascii=False)
check('Merkmale (Fleischart, Zustand) aus dem Wochenangebot ergänzt', off['items'][0]['category'] not in ('', 'Sonstiges') and off['items'][0]['condition'] != 'unbekannt', off['items'][0])
check('Regel 7: keine Mengen, kein Bestand, kein Wochenpreis im Kundenmodell', '"qty"' not in txt and 'kg' not in off['items'][0] and 'stdPrice' not in txt and '25.54' not in txt)
check('anderer Kunde: gesperrt', K2.call('offer&angebot=' + EID)[0] == 403 and EID not in json.dumps(K2.call('kunde_status')[1]))
check('ohne Anmeldung: Anmeldung nötig', Client().call('offer&angebot=' + EID)[0] == 401)
check('unbekannte Kennung: gesperrt', K.call('offer&angebot=e-0000000000')[0] == 403)
check('Leser mit Recht kann das Angebot ansehen', L.call('offer&angebot=' + EID)[0] == 200)
check('Mitarbeiter ohne Recht: gesperrt', Client('198.51.100.9').call('offer&angebot=' + EID)[0] == 401)

# ---------- Bestellwunsch ----------
order = {'angebot': EID, 'publishedAt': off['publishedAt'], 'positions': [{'id': 'p1', 'qty': 2.5, 'price': 0.01}, {'id': 'p2', 'qty': 1}], 'referenz': 'Einzel', 'requestId': 'einzel-request-000000001'}
st, r = K.call('kunde_bestellung', order)
check('Bestellwunsch aus dem Einzelangebot angenommen', st == 200 and r.get('nr'), r)
bst = [b for b in (doc('bestellungen') or []) if b.get('angebot') == EID]
check('Regel 10: Preise vom Server (23,90 €/kg × 2,5 kg = 59,75 €)', bst and bst[-1]['positions'][0]['price'] == 23.9 and bst[-1]['positions'][0]['sum'] == 59.75 and bst[-1]['positions'][1]['price'] is None, bst[-1] if bst else None)
check('anderer Kunde kann nicht daraus bestellen', K2.call('kunde_bestellung', {**order, 'requestId': 'einzel-request-000000002'})[0] == 403)
check('unbekannte Position → 409', K.call('kunde_bestellung', {**order, 'positions': [{'id': 'p9', 'qty': 1}], 'requestId': 'einzel-request-000000003'})[0] == 409)
POS2 = [{**POS[0], 'price': 24.5}, POS[1]]
st, r = E.call('einzel_save', {'id': e1['id'], 'revision': e1['revision'], 'kid': kid, 'titel': 'Grillsaison <Spezial>', 'gueltigBis': bis, 'hinweis': 'Lieferung Dienstag', 'positions': POS2})
e1 = r.get('angebot', {})
check('Änderung am freigegebenen Angebot: neuer Stand', st == 200 and e1['status'] == 'freigegeben' and e1['freigegebenAt'] > off['publishedAt'], e1.get('freigegebenAt'))
check('Bestellwunsch auf alten Stand → 409', K.call('kunde_bestellung', {**order, 'requestId': 'einzel-request-000000004'})[0] == 409)
check('Kunde sieht den neuen Preis', K.call('offer&angebot=' + EID)[1]['offer']['items'][0]['price']['value'] == 24.5)

# ---------- E-Mail ----------
bestaetigung_ablaufen(E)
check('E-Mail ohne Passwortbestätigung → Bestätigung verlangt', (lambda r: r[0] == 403 and r[1].get('code') == 'confirmation_required')(E.call('einzel_senden', {'id': e1['id']})))
check('Passwortbestätigung mit Recht „Einzelangebote bearbeiten“ möglich', E.call('reauth', {'password': 'Editor-Zugang-77'})[0] == 200)
n0 = len(smtp.messages)
st, r = E.call('einzel_senden', {'id': e1['id'], 'note': 'Wie besprochen.'})
check('E-Mail gesendet', st == 200 and len(r['angebot']['gesendet']) == 1 and r['angebot']['gesendet'][0]['ok'], r)
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
body = (m.get('text') or '') + (m.get('html') or '')
check('E-Mail an den Kunden mit Positionen, Preis, Nachricht und Portal-Link', m and 'kantine.einzel@example.org' in m.get('to', []) and e1['nr'] in m.get('subject', '')
      and '24,50 €/kg' in body and 'Preis auf Anfrage' in body and 'Wie besprochen.' in body and '/?angebot=' + EID in body, {k: m.get(k) for k in ('to', 'subject')})
check('E-Mail enthält keinen Bestand und keinen Wochenpreis', '25,54' not in body and '50 kg' not in body)
log = doc('mailversand') or []
check('E-Mail im Versandprotokoll (Typ Einzelangebot)', 'einzelangebot' in json.dumps(log), str(log)[:200])
st, r = A.call('einzel_save', {'kid': kid3, 'positions': POS})
e3 = r['angebot']
assert A.call('reauth', {'password': PW})[0] == 200
check('Kunde ohne E-Mail-Adresse → 422', A.call('einzel_senden', {'id': e3['id']})[0] == 422)

# ---------- Zurückziehen, Ablauf, Löschen ----------
st, r = E.call('einzel_status', {'id': e1['id'], 'revision': e1['revision'], 'status': 'zurueckgezogen'})
check('zurückgezogen: für den Kunden weg', st == 200 and K.call('offer&angebot=' + EID)[0] == 403 and EID not in json.dumps(K.call('kunde_status')[1]))
e1 = r['angebot']
st, r = E.call('einzel_status', {'id': e1['id'], 'revision': e1['revision'], 'status': 'freigegeben'})
e1 = r['angebot']
check('wieder freigegeben: sichtbar', st == 200 and K.call('offer&angebot=' + EID)[0] == 200)
d = doc('einzelangebote')
for x in d['list']:
    if x['id'] == e1['id']:
        x['gueltigBis'] = (date.today() - timedelta(days=1)).isoformat()
storage_write('einzelangebote', d)
check('abgelaufen: für den Kunden weg, Bestellung abgewiesen', K.call('offer&angebot=' + EID)[0] == 403 and EID not in json.dumps(K.call('kunde_status')[1])
      and K.call('kunde_bestellung', {**order, 'publishedAt': e1['freigegebenAt'], 'requestId': 'einzel-request-000000005'})[0] == 403)
check('abgelaufenes Angebot lässt sich nicht erneut freigeben', E.call('einzel_status', {'id': e1['id'], 'revision': e1['revision'], 'status': 'freigegeben'})[0] == 422)
for x in d['list']:
    if x['id'] == e1['id']:
        x['gueltigBis'] = bis
storage_write('einzelangebote', d)
check('Leser darf nicht löschen', L.call('einzel_loeschen', {'id': e3['id']})[0] == 403)
check('Löschen', A.call('einzel_loeschen', {'id': e3['id']})[0] == 200 and A.call('einzel_detail&id=' + e3['id'])[0] == 404)
check('Protokoll: Freigabe, Rückzug, Löschen', all(s in json.dumps(A.call('log')[1], ensure_ascii=False) for s in ('im Portal freigegeben', 'zurückgezogen', e3['nr'] + ' gelöscht')))

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script("window.print = () => { const i = document.querySelector('.kopf img'); window.__logo = i ? [i.naturalWidth, i.getAttribute('src').slice(0, 22)] : null; window.__gedruckt = true; };")
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Reiter „Einzelangebote erstellen“ direkt unter „Angebot bearbeiten“', a.locator('#vt-einzel').is_visible() and 'Einzelangebote erstellen' in a.inner_text('#vt-einzel')
          and y('#vt-edit') < y('#vt-einzel'), a.inner_text('#vt-einzel'))
    a.click('#vt-einzel'); a.wait_for_selector('#view-einzel tr[data-ez]')
    check('Übersicht: Nummer, Kunde, Status', 'E-' in a.inner_text('#view-einzel .eztab') and 'Kantine <Einzel>' in a.inner_text('#view-einzel .eztab') and 'Im Portal freigegeben' in a.inner_text('#view-einzel .eztab'))
    a.fill('#ez-lq', 'andere'); a.wait_for_function("document.querySelectorAll('#view-einzel tr[data-ez]').length === 1")
    check('Übersicht durchsuchbar', 'Andere Kantine' in a.inner_text('#view-einzel .eztab'))
    a.fill('#ez-lq', '')
    a.click('#ez-neu'); a.wait_for_selector('#ez-kunde')
    # Kundenauswahl mit Suche
    a.click('#ez-kunde'); a.wait_for_selector('#ez-kunde-list li[data-kid]')
    check('Kundensuche: beim Öffnen alle Kunden', a.locator('#ez-kunde-list li[data-kid]').count() == 3 and a.get_attribute('#ez-kunde', 'aria-expanded') == 'true')
    a.fill('#ez-kunde', 'ohne'); a.wait_for_function("document.querySelectorAll('#ez-kunde-list li[data-kid]').length === 1")
    check('Kundensuche: Firma, Hinweis „kein Portal“', 'Ohne Mail GmbH' in a.inner_text('#ez-kunde-list') and 'kein Portal' in a.inner_text('#ez-kunde-list'))
    a.fill('#ez-kunde', 'zzz-gibt-es-nicht'); a.wait_for_selector('#ez-kunde-list .ez-ko-mehr')
    check('Kundensuche: kein Treffer', 'Kein Kunde gefunden' in a.inner_text('#ez-kunde-list'))
    a.fill('#ez-kunde', 'hamburg kantine'); a.wait_for_function("document.querySelectorAll('#ez-kunde-list li[data-kid]').length === 2")
    check('Kundensuche: mehrere Wörter (Ort + Firma)', 'Andere Kantine' in a.inner_text('#ez-kunde-list') and 'Kantine <Einzel>' in a.inner_text('#ez-kunde-list'))
    a.screenshot(path=SH + '/einzelangebot-kundensuche.png')
    breit = a.evaluate('''() => { const t = document.querySelector('#ez-treffer'), r = t.getBoundingClientRect();
        const b = [...t.querySelectorAll('[data-add]')].slice(0, 30).map((x) => x.getBoundingClientRect().right);
        return [t.scrollWidth - t.clientWidth, Math.max(...b) - r.right, b.length]; }''')
    check('Treffertabelle passt ins Suchfeld (alle Knöpfe sichtbar)', breit[0] <= 1 and breit[1] <= 0 and breit[2] == 30, breit)
    a.press('#ez-kunde', 'Escape')
    check('Escape schließt die Liste, kein Kunde gewählt', a.locator('#ez-kunde-list').is_hidden() and a.input_value('#ez-kunde') == '')
    a.fill('#ez-kunde', 'KANTINE.AN'); a.wait_for_selector('#ez-kunde-list li.akt[data-kid]')
    check('Kundensuche: Kundennummer, bester Treffer zuerst', a.get_attribute('#ez-kunde-list li.akt', 'data-kid') == kid2)
    a.press('#ez-kunde', 'Enter'); a.wait_for_selector('#ez-kunde-list', state='hidden')
    check('Enter wählt den Kunden, Angaben darunter', a.input_value('#ez-kunde').startswith('Andere Kantine') and 'Testweg 1' in a.inner_text('.ez-kinfo') and a.locator('#ez-dirty').is_visible(), a.input_value('#ez-kunde'))
    a.click('#ez-kunde'); a.fill('#ez-kunde', 'einzel'); a.wait_for_selector('#ez-kunde-list li[data-kid]'); a.keyboard.press('Tab')
    check('Verlassen ohne Auswahl behält den gewählten Kunden', a.input_value('#ez-kunde').startswith('Andere Kantine') and a.locator('#ez-kunde-list').is_hidden())
    # Artikelsuche als Tabelle mit Details
    a.fill('#ez-q', '10601'); a.wait_for_selector('#ez-treffer tr[data-code="10601"]')
    t = a.inner_text('#ez-treffer tr[data-code="10601"]')
    check('Treffertabelle: gesamt verfügbar, davon erwartet, Wochenpreis', '50 kg' in t and 'davon 10 kg erwartet' in t and '25,54 €' in t, t)
    check('VK-Gruppe als Zwischenzeile', 'Rindfleisch, Argentinien, frisch' in a.inner_text('#ez-treffer tr.ez-grp'))
    a.click('#ez-treffer [data-info="10601"]'); a.wait_for_selector('#ez-treffer tr[data-det="10601"]')
    d = a.inner_text('#ez-treffer tr[data-det="10601"]')
    check('Details: Bestand eingelagert/erfasst/gesamt, kürzestes MHD', 'Eingelagert 40 kg' in d and 'Erfasst 10 kg' in d and 'Gesamt verfügbar 50 kg' in d and '20.11.2026' in d, d)
    check('Details: Partien mit Eingang, MHD, Kolli, kg und EK', 'P-0001' in d and 'P-0002' in d and '04.12.2026' in d and '19,25' in d and 'EK' in d, d)
    check('Details: erwartete Ankunft mit ETA', 'TEST-A' in d and '22.10.2026' in d, d)
    check('Details: VK-Gruppe, Herkunft, Zustand', '1600 · Rindfleisch, Argentinien, frisch' in d and 'AR' in d and 'frisch' in d, d)
    a.screenshot(path=SH + '/einzelangebot-artikeldetails.png')
    check('Detailknopf zeigt Zustand an', a.get_attribute('#ez-treffer [data-info="10601"]', 'aria-expanded') == 'true')
    a.click('#ez-treffer [data-info="10601"]'); a.wait_for_selector('#ez-treffer tr[data-det="10601"]', state='detached')
    a.fill('#ez-q', 'steakhüfte'); a.wait_for_selector('#ez-treffer tr[data-code="10823"]'); a.click('#ez-treffer [data-info="10823"]')
    a.wait_for_selector('#ez-treffer tr[data-det="10823"]')
    d = a.inner_text('#ez-treffer tr[data-det="10823"]')
    check('Details: nur erwartet, ETA unbekannt', 'ETA unbekannt' in d and 'TEST-B' in d and 'Kein eingelagerter Bestand' in d, d)
    a.fill('#ez-q', 'entrecote'); a.wait_for_selector('#ez-treffer tr[data-code="10701"]')
    check('Suche: „kein Bestand“ sichtbar', 'kein Bestand' in a.inner_text('#ez-treffer tr[data-code="10701"]'))
    a.check('#ez-f-bestand'); a.wait_for_function("!document.querySelector('#ez-treffer tr[data-code=\"10701\"]')")
    check('Filter „nur mit Bestand“', a.locator('#ez-treffer tr[data-code]').count() == 0)
    a.uncheck('#ez-f-bestand'); a.fill('#ez-q', '900001'); a.wait_for_selector('#ez-treffer tr[data-code="900001"]')
    a.click('#ez-treffer [data-info="900001"]'); a.wait_for_selector('#ez-treffer tr[data-det="900001"]')
    check('Artikel nur im Bestand: „nicht im Angebot“', 'nicht im Angebot' in a.inner_text('#ez-treffer tr[data-det="900001"]') and a.get_attribute('#ez-treffer tr[data-code="900001"] .ez-tt-p span', 'title') == 'nicht im Wochenangebot' and '5,5 kg' in a.inner_text('#ez-treffer tr[data-code="900001"]'))
    a.fill('#ez-q', 'irland'); a.wait_for_selector('#ez-treffer tr[data-code="900001"]')   # „Irland“ steht nur in der VK-Gruppe (Herkunft „IRL“)
    check('Textsuche findet auch die Bezeichnung der VK-Gruppe', '900001' in a.eval_on_selector_all('#ez-treffer tr[data-code]', 'e => e.map(x => x.dataset.code)'))
    a.fill('#ez-q', '10601'); a.wait_for_selector('#ez-treffer tr[data-code="10601"]'); a.click('#ez-treffer [data-add="10601"]'); a.wait_for_selector('#ez-pos tr[data-i="0"]')
    row = '#ez-pos tr[data-i="0"]'
    check('Position übernommen: Wochenpreis vorbelegt, Abweichung ±0 %', a.input_value(row + ' [data-f="price"]') == '25,54' and '±0 %' in a.inner_text(row + ' .ez-a')
          and '50 kg' in a.inner_text(row + ' .ez-b'), a.inner_text(row))
    check('bereits übernommener Artikel nicht doppelt hinzufügbar', a.locator('#ez-treffer [data-add="10601"]').is_disabled())
    a.fill(row + ' [data-f="price"]', '23,50')
    check('Abweichung unter Wochenpreis: Punkt und −8 %', a.get_attribute(row + ' .ez-abw', 'class').endswith('ab-unter') and '−8 %' in a.inner_text(row + ' .ez-a'), a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="price"]', '20')
    check('starke Abweichung (> 10 %) hervorgehoben', 'ab-stark' in a.get_attribute(row + ' .ez-abw', 'class') and '−22 %' in a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="price"]', '27,50')
    check('über Wochenpreis: +8 %', 'ab-ueber' in a.get_attribute(row + ' .ez-abw', 'class') and '+8 %' in a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="qty"]', '12'); a.press(row + ' [data-f="qty"]', 'Tab')
    a.wait_for_function("document.querySelector('#ez-summe') && document.querySelector('#ez-summe').textContent.includes('330,00')")
    check('Summe: 12 kg · 330,00 €', '12 kg' in a.inner_text('#ez-summe'))
    a.fill(row + ' [data-f="qty"]', 'abc')
    check('ungültige Menge markiert', 'invalid' in a.get_attribute(row + ' [data-f="qty"]', 'class'))
    a.fill(row + ' [data-f="qty"]', '12'); a.press(row + ' [data-f="qty"]', 'Tab')
    a.fill('#ez-q', 'Sonderschnitt'); a.click('#ez-frei'); a.wait_for_selector('#ez-pos tr[data-i="1"]')
    check('freie Position mit Suchbegriff als Bezeichnung', a.input_value('#ez-pos tr[data-i="1"] [data-f="name"]') == 'Sonderschnitt')
    check('ungespeichert-Hinweis', a.locator('#ez-dirty').is_visible())
    a.screenshot(path=SH + '/einzelangebot-bearbeiten.png', full_page=True)
    a.click('#ez-save'); a.wait_for_selector('#ez-freigeben')
    nr2 = a.inner_text('.ez-top h2')
    check('gespeichert: Nummer vergeben, Freigabe möglich', f'E-{date.today().year}-000' in nr2 and not a.locator('#ez-dirty').is_visible(), nr2)
    saved = [x for x in doc('einzelangebote')['list'] if x['kid'] == kid2 and len(x['positions']) == 2]
    check('gespeichert wie eingegeben', saved and saved[0]['positions'][0] == {'code': '10601', 'name': 'Roastbeef, frisch', 'qty': 12.0, 'price': 27.5, 'notiz': ''}
          and saved[0]['positions'][1]['price'] is None, saved[0]['positions'] if saved else None)
    a.click('#ez-freigeben'); a.wait_for_selector('#ez-entfreigeben')
    check('im Portal freigegeben (Oberfläche)', 'Im Portal freigegeben' in a.inner_text('.ez-top'))
    with ctx.expect_page() as pi:
        a.click('#ez-druck')
    w = pi.value; w.wait_for_load_state(); w.wait_for_function('window.__gedruckt === true')
    wt = w.inner_text('body')
    check('Drucken/PDF: Kunde, Nummer, Positionen, Summe, kein Bestand', 'Andere Kantine' in wt and nr2.split()[1] in wt and '27,50' in wt and '330,00 €' in wt and 'Sonderschnitt' in wt
          and 'auf Anfrage' in wt and 'Eingelagert' not in wt and '25,54' not in wt and 'P-0001' not in wt and 'TEST-A' not in wt, wt[:300])
    lg = w.evaluate('window.__logo')
    check('Drucken/PDF: Logo geladen, bevor gedruckt wird (eingebettet)', lg and lg[0] == 630 and lg[1].startswith('data:image/png'), lg)
    w.close()
    a.click('#ez-zurueck'); a.wait_for_selector('#view-einzel tr[data-ez]')
    check('zurück zur Übersicht: neues Angebot gelistet', a.locator('#view-einzel tr[data-ez]').count() >= 3)
    a.screenshot(path=SH + '/einzelangebote-liste.png')

    # VK-Gruppen: mehrere wählen, sortieren, alle Treffer übernehmen
    a.click('#ez-neu'); a.wait_for_selector('#ez-vk')
    check('VK-Gruppen: zunächst alle', 'VK-Gruppen: alle' in a.inner_text('#ez-vk') and a.locator('#ez-vk-chips .ez-chip').count() == 0)
    a.click('#ez-vk'); a.wait_for_selector('#ez-vk-pop:not([hidden]) [data-vk="1600"]')
    pt = a.inner_text('#ez-vk-pop')
    check('Auswahlfenster: vorkommende Gruppen mit Anzahl, „ohne VK-Gruppe“', '1600' in pt and 'Uruguay' in pt and 'Irland' in pt and 'ungenutzt' not in pt and 'ohne VK-Gruppe' in pt, pt)
    a.fill('#ez-vk-q', 'rind frisch'); a.wait_for_function("document.querySelectorAll('#ez-vk-pop [data-vk]').length === 2")
    check('Gruppensuche (mehrere Wörter)', 'Irland' not in a.inner_text('#ez-vk-pop'))
    a.screenshot(path=SH + '/einzelangebot-vk-auswahl.png')
    check('Auswahlfenster bleibt im Bild', a.evaluate("document.querySelector('#ez-vk-pop').getBoundingClientRect().right <= document.documentElement.clientWidth"))
    a.click('#ez-vk-alle'); a.wait_for_function("document.querySelectorAll('#ez-vk-chips .ez-chip').length === 2")
    a.press('#ez-vk-q', 'Escape'); a.wait_for_selector('#ez-vk-pop', state='hidden')
    codes = a.eval_on_selector_all('#ez-treffer tr[data-code]', 'e => e.map(x => x.dataset.code)')
    check('Filter: nur Artikel der gewählten Gruppen, nach VK-Gruppe sortiert', codes == ['10601', '10701', '10823'], codes)
    check('Knopf zeigt die Auswahl, Zwischenzeilen je Gruppe', '2 gewählt' in a.inner_text('#ez-vk') and a.locator('#ez-treffer tr.ez-grp').count() == 2)
    a.select_option('#ez-sort', 'bestand')
    codes = a.eval_on_selector_all('#ez-treffer tr[data-code]', 'e => e.map(x => x.dataset.code)')
    check('Sortierung nach Verfügbar, ohne Zwischenzeilen', codes == ['10601', '10823', '10701'] and a.locator('#ez-treffer tr.ez-grp').count() == 0, codes)
    a.select_option('#ez-sort', 'vk')
    a.click('#ez-vk-chips [data-vk-weg="1610"]'); a.wait_for_function("document.querySelectorAll('#ez-vk-chips .ez-chip').length === 1")
    check('Chip entfernt eine Gruppe', a.eval_on_selector_all('#ez-treffer tr[data-code]', 'e => e.map(x => x.dataset.code)') == ['10601', '10701'])
    check('„Alle hinzufügen“ mit Anzahl', 'Alle 2 hinzufügen' in a.inner_text('#ez-alle'))
    a.click('#ez-alle'); a.wait_for_selector('#ez-pos tr[data-i="1"]')
    check('alle Treffer der Gruppe übernommen, Wochenpreis vorbelegt', [a.inner_text(f'#ez-pos tr[data-i="{i}"] .ez-code') for i in (0, 1)] == ['10601', '10701']
          and a.input_value('#ez-pos tr[data-i="1"] [data-f="price"]') == '27,21' and a.locator('#ez-alle').count() == 0)
    a.click('#ez-vk'); a.wait_for_selector('#ez-vk-pop:not([hidden])')
    a.click('#ez-vk-pop [data-vk="–"]'); a.click('#ez-vk-pop [data-vk="1600"]')
    a.click('#ez-titel'); a.wait_for_selector('#ez-vk-pop', state='hidden')
    check('Klick daneben schließt das Auswahlfenster; „ohne VK-Gruppe“ filterbar', all(c not in VK for c in a.eval_on_selector_all('#ez-treffer tr[data-code]', 'e => e.map(x => x.dataset.code)'))
          and a.locator('#ez-treffer tr[data-code]').count() > 0)
    a.click('#ez-vk'); a.click('#ez-vk-keine'); a.press('#ez-vk-q', 'Escape')
    a.screenshot(path=SH + '/einzelangebot-vkgruppen.png', full_page=True)
    a.click('#ez-zurueck'); a.click('#dlg-confirm .btn.primary'); a.wait_for_selector('#view-einzel tr[data-ez]')
    a.set_viewport_size({'width': 390, 'height': 820}); a.emulate_media(color_scheme='dark')   # mobil im dunklen Modus
    a.locator('#view-einzel tr[data-ez]').first.click(); a.wait_for_selector('#ez-pos')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Mobil 390 px: kein seitliches Scrollen', over <= 1, over)
    a.fill('#ez-q', '10601'); a.click('#ez-treffer [data-info="10601"]'); a.wait_for_selector('#ez-treffer tr[data-det="10601"]')
    a.click('#ez-vk'); a.wait_for_selector('#ez-vk-pop:not([hidden])')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Mobil 390 px: Details und VK-Auswahl ohne seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/einzelangebot-mobil-vk.png')
    a.press('#ez-vk-q', 'Escape')
    a.screenshot(path=SH + '/einzelangebot-mobil.png', full_page=True)

    # Leser: nur ansehen
    lp = br.new_page(viewport={'width': 1280, 'height': 900})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#vt-einzel:not([hidden])')
    lp.click('#vt-einzel'); lp.wait_for_selector('#view-einzel tr[data-ez]')
    check('Leser: kein „Neues Einzelangebot“', lp.locator('#ez-neu').count() == 0)
    lp.locator('#view-einzel tr[data-ez]').first.click(); lp.wait_for_selector('#ez-pos')
    check('Leser: nur lesend, keine Suche', lp.locator('#ez-save').count() == 0 and lp.locator('#ez-q').count() == 0 and lp.locator('#ez-kunde').is_disabled())
    lp.close()

    # Portal: Kunde sieht sein Einzelangebot und kann bestellen
    kctx = br.new_context(viewport={'width': 1280, 'height': 900})
    c = kctx.new_page()
    c.on('pageerror', lambda e: errors.append(str(e)))
    c.goto(BASE + '/'); c.wait_for_selector('#btn-kunde-login'); c.click('#btn-kunde-login')
    c.fill('#kl-form [name=username]', 'kantine.andere'); c.fill('#kl-form [name=password]', KPW); c.click('#kl-form [type=submit]')
    c.wait_for_selector('.k-switch [data-kswitch^="e-"]')
    with c.expect_navigation():
        c.click('.k-switch [data-kswitch^="e-"]')
    c.wait_for_function("location.search.includes('angebot=e-') && document.body.classList.contains('can-order') && document.querySelector('#kw-pill').textContent.includes('gültig bis')")
    c.click('#modebar [data-mode=liste]'); c.wait_for_selector('tr.row .qty')
    lt = c.inner_text('#list')
    check('Portal: Einzelangebot mit eigenen Preisen', 'Roastbeef' in lt and '27,50' in lt and 'Sonderschnitt' in lt, lt[:300])
    check('Portal: kein Bestand/Wochenpreis sichtbar', '25,54' not in c.inner_text('body') and 'Eingelagert' not in c.inner_text('body'))
    check('Portal: Gültigkeit statt Kalenderwoche', 'gültig bis' in c.inner_text('#kw-pill') and 'KW ?' not in c.inner_text('#topbar'), c.inner_text('#kw-pill'))
    c.screenshot(path=SH + '/einzelangebot-portal.png')
    m = kctx.new_page(); m.set_viewport_size({'width': 390, 'height': 820})
    m.on('pageerror', lambda e: errors.append(str(e)))
    m.goto(c.url); m.wait_for_selector('#kw-pill'); m.wait_for_function("document.querySelector('#kw-pill').textContent.includes('gültig bis')")
    over = m.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Portal mobil 390 px: kein seitliches Scrollen', over <= 1, over)
    m.screenshot(path=SH + '/einzelangebot-portal-mobil.png')
    c.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
