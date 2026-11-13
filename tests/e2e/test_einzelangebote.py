"""Einzelangebote (Angebot bearbeiten → Einzelangebote): Angebot für genau einen Kunden. Rechte, Prüfung, Artikelsuche mit
Bestand (eingelagert, erfasst, gesamt verfügbar) und Wochenangebotspreis, Freigabe im Portal, Bestellwunsch mit Preisen
vom Server, Zurückziehen, Ablauf, E-Mail (Test-Mailserver, auch aus dem CRM über crm_einzel_senden), Oberfläche mit Abweichungspunkt, Druck und Portalansicht.
Nur synthetische Testdaten; es werden keine echten E-Mails versendet."""
import json
import re
import sys
import urllib.error
import zlib
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
check('ohne Wahl: Format „Liste“ vermerkt, kein Anhang', r['angebot']['gesendet'][-1].get('format') == 'liste' and not list(m['msg'].iter_attachments()))

# ---------- E-Mail aus dem CRM (Kunden-Pop-up, Reiter „Angebote“: crm_einzel_senden, gleiche Funktion und Bestätigung) ----------
A.call('user_save', {'username': 'vera', 'name': 'Vera Vertrieb', 'role': 'viewer', 'active': True, 'password': 'Weg-Kennwort-42', 'mustChange': False,
                     'grant': ['crm.sehen', 'einzelangebote.bearbeiten']})
V = Client('198.51.100.5'); assert V.call('login', {'username': 'vera', 'password': 'Weg-Kennwort-42'})[0] == 200
bestaetigung_ablaufen(V)
check('CRM: E-Mail ohne Passwortbestätigung → Bestätigung verlangt', (lambda x: x[0] == 403 and x[1].get('code') == 'confirmation_required')(V.call('crm_einzel_senden', {'key': kid, 'id': e1['id']})))
check('CRM: Passwortbestätigung möglich', V.call('reauth', {'password': 'Weg-Kennwort-42'})[0] == 200)
check('CRM: Einzelangebot über das Pop-up eines anderen Kunden → 404', V.call('crm_einzel_senden', {'key': kid2, 'id': e1['id']})[0] == 404)
check('CRM: ohne „CRM ansehen“ → 403 (auch nach Bestätigung)', E.call('crm_einzel_senden', {'key': kid, 'id': e1['id']})[0] == 403)
n0 = len(smtp.messages)
st, r = V.call('crm_einzel_senden', {'key': kid, 'id': e1['id'], 'note': 'Aus dem CRM.'})
check('CRM: E-Mail gesendet und am Angebot vermerkt', st == 200 and r['angebot']['gesendet'][-1]['ok'] and r['angebot']['gesendet'][-1]['format'] == 'liste'
      and len(r['angebot']['gesendet']) == 2, r.get('angebot', {}).get('gesendet'))
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
body = (m.get('text') or '') + (m.get('html') or '')
check('CRM: E-Mail an die Adresse des Kunden mit Positionen und Nachricht', m and 'kantine.einzel@example.org' in m.get('to', []) and e1['nr'] in m.get('subject', '')
      and '24,50 €/kg' in body and 'Aus dem CRM.' in body, {k: m.get(k) for k in ('to', 'subject')})


def pdf_inhalt(data):
    """Text der Seiteninhalte (FlateDecode) eines PDF, als Windows-1252 gelesen."""
    out = b''
    for mm in re.finditer(rb'/Filter /FlateDecode >>\nstream\n', data):
        n = int(re.search(rb'/Length (\d+)', data[max(0, mm.start() - 60):mm.start()]).group(1))
        out += zlib.decompress(data[mm.end():mm.end() + n])
    return out.decode('cp1252', 'replace')


def hole(cl, action):
    req = urllib.request.Request(BASE + '/api/?action=' + action, headers={'X-Forwarded-For': cl.ip})
    try:
        r = cl.http.open(req)
    except urllib.error.HTTPError as ex:
        r = ex
    return r.code, r.headers.get('Content-Type', ''), r.read()


check('unbekanntes Format → 422', E.call('einzel_senden', {'id': e1['id'], 'format': 'docx'})[0] == 422)
n0 = len(smtp.messages)
st, r = E.call('einzel_senden', {'id': e1['id'], 'note': 'Als PDF, wie gewünscht.', 'format': 'pdf'})
check('E-Mail mit PDF-Anhang gesendet, Format vermerkt', st == 200 and r['angebot']['gesendet'][-1]['format'] == 'pdf' and r['angebot']['gesendet'][-1]['ok'], r.get('angebot', {}).get('gesendet'))
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
att = list(m['msg'].iter_attachments()) if m else []
pdf = att[0].get_content() if att else b''
check('Anhang: ein PDF mit Dateiname der Angebotsnummer', len(att) == 1 and att[0].get_content_type() == 'application/pdf' and att[0].get_filename() == f'Angebot_{e1["nr"]}.pdf'
      and pdf.startswith(b'%PDF-1.4') and pdf.rstrip().endswith(b'%%EOF'), [a.get_filename() for a in att])
inhalt = pdf_inhalt(pdf)
check('PDF im Design der Angebotsansicht: A4 quer, Logo, Titel, Kunde, Positionen, Preise, Seitenzahl', b'/MediaBox [0 0 841.89 595.28]' in pdf and b'/DCTDecode' in pdf
      and 'Grillsaison <Spezial>' in inhalt and 'Kantine <Einzel>' in inhalt and 'Roastbeef, frisch' in inhalt and '24,50' in inhalt and 'auf Anfrage' in inhalt
      and 'Seite 1 von 1' in inhalt and '€/kg' in inhalt, inhalt[:300])
check('PDF ohne Bestand, Partien und Wochenpreis', '25,54' not in inhalt and 'P-0001' not in inhalt and 'TEST-A' not in inhalt and 'Eingelagert' not in inhalt)
body = (m.get('text') or '') + (m.get('html') or '')
check('E-Mail-Text bei PDF: Hinweis auf den Anhang, keine Positionsliste, Nachricht', f'Angebot_{e1["nr"]}.pdf' in body and '24,50 €/kg' not in body and 'Als PDF, wie gewünscht.' in body, (m.get('text') or '')[:300])
check('Protokoll: „als PDF versendet“', 'als PDF versendet' in json.dumps(A.call('log')[1], ensure_ascii=False))
code, typ, data = hole(E, 'einzel_pdf&id=' + e1['id'])
check('PDF-Vorschau im Eingabebereich (gleiches PDF)', code == 200 and typ == 'application/pdf' and data.startswith(b'%PDF') and 'Grillsaison <Spezial>' in pdf_inhalt(data))
check('PDF-Vorschau: ohne Recht bzw. Anmeldung gesperrt, unbekannt → 404', hole(Client('198.51.100.9'), 'einzel_pdf&id=' + e1['id'])[0] == 401
      and hole(K, 'einzel_pdf&id=' + e1['id'])[0] == 401 and hole(E, 'einzel_pdf&id=0000000000')[0] == 404)
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

# ---------- Partien im Einzelangebot (Entscheidung des Inhabers 13.11.2026, GR-001 Version 2) ----------
# Der Kunde sieht zu einer ausdrücklich angebotenen Partie Charge, MHD und Menge (Schnappschuss) – nie EK, nie weitere Partien,
# nie den Bestand. Zuordnen nur mit „Bestand ansehen“; Werte übernimmt der Server aus dem Bestand.
check('alte Positionen ohne Partie bleiben im bisherigen Format', all(set(p) == {'code', 'name', 'qty', 'price', 'notiz'} for x in doc('einzelangebote')['list'] for p in x['positions']))
PP = [{'code': '10601', 'name': 'Roastbeef, frisch', 'qty': 10, 'price': 24.9, 'notiz': '', 'partie': {'lot': 'P-0002', 'mhd': '1999-01-01', 'kg': 999, 'ek': 1}},
      {'code': '10601', 'name': 'Roastbeef, frisch', 'qty': None, 'price': 23.5, 'notiz': 'kurzes MHD', 'partie': {'lot': 'P-0001'}},
      {'code': '10701', 'name': 'Entrecote, frisch', 'qty': 3, 'price': 27, 'notiz': ''}]


def ps(**kw):
    return {'kid': kid, 'titel': 'Partien <Test>', 'gueltigBis': bis, 'hinweis': '', 'positions': PP, **kw}


def anzahl():
    return len(doc('einzelangebote')['list'])


n0 = anzahl()
check('Partie zuordnen ohne Recht „Bestand ansehen“ → 403', E.call('einzel_save', ps())[0] == 403)
check('Kunde kann keine Partie zuordnen', K.call('einzel_save', ps())[0] in (401, 403))
FEHLER = [('unbekannte Partie', [{**PP[0], 'partie': {'lot': 'P-9999'}}]),
          ('Partie eines anderen Artikels', [{**PP[2], 'partie': {'lot': 'P-0001'}}]),
          ('erwartete (nicht eingelagerte) Partie', [{**PP[0], 'partie': {'lot': 'TEST-A'}}]),
          ('Partie an freier Position', [{'code': '', 'name': 'Frei', 'partie': {'lot': 'P-0001'}}]),
          ('Partie als Text', [{**PP[0], 'partie': 'P-0001'}]),
          ('Partie ohne Nummer', [{**PP[0], 'partie': {}}]),
          ('Partie mit leerer Nummer', [{**PP[0], 'partie': {'lot': ' '}}]),
          ('Menge größer als die Partie (15,01 > 15 kg)', [{**PP[1], 'qty': 15.01}]),
          ('dieselbe Partie zweimal', [PP[0], {**PP[0], 'qty': 1}])]
for name, pos in FEHLER:
    st, r = A.call('einzel_save', ps(positions=pos))
    check(f'Partie: {name} → 422', st == 422, (st, r.get('error')))
st, r = A.call('einzel_save', ps(positions=[{**PP[1], 'qty': 16}]))
check('Meldung nennt Partie und Menge', st == 422 and 'größer als die Partie P-0001 (15,00 kg)' in r.get('error', ''), r.get('error'))
check('abgewiesene Partien legen nichts an', anzahl() == n0)

st, r = A.call('einzel_save', ps())
e5 = r.get('angebot', {})
p5 = e5.get('positions', [{}, {}, {}])
check('Partien zugeordnet: Schnappschuss aus dem Bestand, Werte des Browsers ignoriert', st == 200 and p5[0].get('partie') == {'lot': 'P-0002', 'mhd': '2026-12-04', 'kg': 25}
      and p5[1].get('partie') == {'lot': 'P-0001', 'mhd': '2026-11-20', 'kg': 15} and 'partie' not in p5[2], p5)
check('zwei Partien desselben Artikels als getrennte Positionen; Summe zählt Partie ohne Menge ganz', e5.get('summen') == {'kg': 28, 'summe': 682.5}, e5.get('summen'))
gesp = next((x for x in doc('einzelangebote')['list'] if x['id'] == e5.get('id')), {})
check('gespeichert ohne EK, Eingang oder Kolli', all(set(p['partie']) == {'lot', 'mhd', 'kg'} for p in gesp.get('positions', [])[:2])
      and not re.search(r'18\.5|19\.25|"ek"|arrival|kolli', json.dumps(gesp)), gesp.get('positions'))
check('Protokoll: Positionen mit Partie', f"{e5.get('nr')} für „Kantine <Einzel>“ angelegt (3 Positionen, davon 2 mit Partie)" in json.dumps(A.call('log')[1], ensure_ascii=False))
EID5 = 'e-' + e5['id']

# Schnappschuss (GR-106): neuer Bestand ändert das Angebot nicht; bekannte Partie bleibt auch verkauft gültig
STOCK2 = json.loads(json.dumps(STOCK))
STOCK2['articles'][0].update({'kg': 5, 'lots': [{'lot': 'P-0002', 'arrival': '2026-10-09', 'mhd': '2026-11-30', 'kolli': 1, 'kg': 5, 'ek': 19.25}]})
assert A.call('stock_import', STOCK2)[0] == 200
d5 = A.call('einzel_detail&id=' + e5['id'])[1]['angebot']
check('Bestand geändert: Partien im Angebot unverändert', [p.get('partie') for p in d5['positions'][:2]] == [p5[0]['partie'], p5[1]['partie']], [p.get('partie') for p in d5['positions']])
st, r = A.call('einzel_save', ps(id=e5['id'], revision=d5['revision'], positions=[PP[0], {**PP[1], 'qty': 15}, PP[2]]))
check('erneut gespeichert: Schnappschuss bleibt (verkaufte Partie, alte Menge), Menge = Partie erlaubt', st == 200 and r['angebot']['positions'][1]['partie'] == {'lot': 'P-0001', 'mhd': '2026-11-20', 'kg': 15}
      and r['angebot']['positions'][0]['partie']['kg'] == 25 and r['angebot']['positions'][1]['qty'] == 15, r.get('angebot', {}).get('positions'))
e5 = r.get('angebot', e5)
check('neue Zuordnung einer verkauften Partie → 422', A.call('einzel_save', ps(positions=[PP[1]]))[0] == 422 and anzahl() == n0 + 1)
assert A.call('stock_import', STOCK)[0] == 200   # Bestand wie zu Beginn (Oberfläche unten)

# Ohne „Bestand ansehen“: vorhandene Partien bleiben beim Speichern erhalten, neue Zuordnung 403, Entfernen erlaubt
POS5 = [{'code': p['code'], 'name': p['name'], 'qty': p['qty'], 'price': p['price'], 'notiz': p['notiz'], **({'partie': {'lot': p['partie']['lot']}} if 'partie' in p else {})} for p in e5['positions']]
st, r = E.call('einzel_save', ps(id=e5['id'], revision=e5['revision'], positions=POS5[:2] + [{**POS5[2], 'price': 26}]))
check('Bearbeiter ohne Bestandsrecht: Partien bleiben beim Speichern erhalten', st == 200 and [p.get('partie') for p in r['angebot']['positions']] == [p.get('partie') for p in e5['positions']]
      and r['angebot']['positions'][2]['price'] == 26, r)
e5 = r.get('angebot', e5)
st, r = E.call('einzel_save', ps(id=e5['id'], revision=e5['revision'], positions=POS5[:2] + [{**POS5[2], 'price': 26, 'partie': {'lot': 'P-0001'}}]))
check('… neue Partie zuordnen → 403', st == 403)
st, r = E.call('einzel_save', ps(id=e5['id'], revision=e5['revision'], positions=[POS5[0], {**POS5[1], 'partie': None}, {**POS5[2], 'price': 26}]))
check('… Partie entfernen erlaubt', st == 200 and 'partie' not in r['angebot']['positions'][1] and r['angebot']['positions'][1]['qty'] == 15)
e5 = r.get('angebot', e5)
st, r = A.call('einzel_save', ps(id=e5['id'], revision=e5['revision'], positions=[POS5[0], POS5[1], {**POS5[2], 'price': 26}]))
e5 = r.get('angebot', e5)
check('Administrator ordnet die Partie wieder zu (aus dem Bestand)', st == 200 and e5['positions'][1].get('partie') == {'lot': 'P-0001', 'mhd': '2026-11-20', 'kg': 15})

# CRM (Kunden-Pop-up): gleiche Funktionen; die Oberfläche schickt nur die Partienummer zurück
st, r = V.call(f'crm_einzel_detail&key={kid}&id={e5["id"]}')
check('CRM: Einzelangebot mit Partien (Schnappschuss, ohne EK)', st == 200 and r['angebot']['positions'][0].get('partie') == {'lot': 'P-0002', 'mhd': '2026-12-04', 'kg': 25} and '19.25' not in json.dumps(r), r.get('angebot', {}).get('positions'))
st, r = V.call('crm_einzel_save', {'key': kid, 'id': e5['id'], 'revision': e5['revision'], 'titel': 'Partien <Test>', 'gueltigBis': bis, 'hinweis': '', 'positions': POS5[:2] + [{**POS5[2], 'price': 26.5}]})
check('CRM: Speichern behält die Partien', st == 200 and [p.get('partie') for p in r['angebot']['positions']] == [p.get('partie') for p in e5['positions']] and r['angebot']['positions'][2]['price'] == 26.5, r.get('error'))
e5 = r.get('angebot', e5)
check('CRM: Menge über der Partie → 422', V.call('crm_einzel_save', {'key': kid, 'id': e5['id'], 'revision': e5['revision'], 'positions': [{**POS5[0], 'qty': 30}]})[0] == 422)

# Kunde: nur im eigenen, freigegebenen Einzelangebot; Menge = angebotene Menge (nicht die Größe der Partie)
check('Entwurf mit Partien: Kunde gesperrt', K.call('offer&angebot=' + EID5)[0] == 403)
st, r = A.call('einzel_status', {'id': e5['id'], 'revision': e5['revision'], 'status': 'freigegeben'})
e5 = r.get('angebot', e5)
st, r = K.call('offer&angebot=' + EID5)
off5 = r.get('offer', {})
it5 = off5.get('items', [{}, {}, {}])
check('Kunde sieht Charge, MHD und angebotene Menge', st == 200 and it5[0].get('partie') == {'lot': 'P-0002', 'mhd': '2026-12-04', 'kg': 10}
      and it5[1].get('partie') == {'lot': 'P-0001', 'mhd': '2026-11-20', 'kg': 15} and 'partie' not in it5[2], it5)
txt5 = json.dumps(off5)
check('GR-001/GR-008: im Kundenmodell nie EK, Eingang, Kolli, weitere Partien oder Bestand', not re.search(r'18\.5|19\.25|"ek"|arrival|kolli|"lots"|incoming|TEST-A|"qty"|stdPrice|"kg": 25\b|"kg": 40\b', txt5), txt5[:400])
check('anderer Kunde: Einzelangebot mit Partien gesperrt', K2.call('offer&angebot=' + EID5)[0] == 403 and 'P-0002' not in json.dumps(K2.call('kunde_status')[1]))
check('ohne Anmeldung: gesperrt', Client().call('offer&angebot=' + EID5)[0] == 401)
WOCHE = [K.call('offer'), Client().call('offer')] + [A.call('offer&angebot=' + o) for o in ('chefs-culinar', 'handelshof-efs', 'edeka', 'bela')]
check('GR-001: Wochenangebot und Kundenangebote weiterhin ohne Partien, Chargen, MHD und Mengen', all(s == 200 for s, _ in WOCHE)
      and not any(re.search(r'partie|P-000|"mhd"|"lot"|"kg"', json.dumps(x)) for _, x in WOCHE), [s for s, _ in WOCHE])

# Bestellwunsch: Charge und MHD stehen am Namen (zwei Partien desselben Artikels unterscheidbar), Preise vom Server
st, r = K.call('kunde_bestellung', {'angebot': EID5, 'publishedAt': off5.get('publishedAt'), 'positions': [{'id': 'p1', 'qty': 4, 'price': 0.01}, {'id': 'p2', 'qty': 2}], 'requestId': 'einzel-request-000000010'})
b5 = [b for b in (doc('bestellungen') or []) if b.get('angebot') == EID5]
check('Bestellwunsch: Charge und MHD am Artikel, Preis vom Server', st == 200 and b5 and [p['name'] for p in b5[-1]['positions']] == ['Roastbeef, frisch (Charge P-0002, MHD 04.12.2026)', 'Roastbeef, frisch – kurzes MHD (Charge P-0001, MHD 20.11.2026)']
      and b5[-1]['positions'][0]['sum'] == 99.6, b5[-1]['positions'] if b5 else r)

# PDF und E-Mail an den Kunden
code, typ, data = hole(A, 'einzel_pdf&id=' + e5['id'])
inh5 = pdf_inhalt(data)
with open(SH + '/einzelangebot-partien.pdf', 'wb') as fh:   # zum Ansehen (Ergebnisordner der Tests)
    fh.write(data)
check('PDF: je Partie Charge, MHD und Menge', code == 200 and 'Charge P-0002 · MHD 04.12.2026 · 10,00 kg' in inh5 and 'Charge P-0001 · MHD 20.11.2026 · 15,00 kg' in inh5 and 'Menge 3,00 kg' in inh5, inh5[:600])
check('PDF: ohne EK, Bestand und weitere Partien', not re.search(r'18,50|19,25|TEST-A|Eingelagert|25,00 kg', inh5))
n0m = len(smtp.messages)
st, r = A.call('einzel_senden', {'id': e5['id'], 'note': 'Partien wie besprochen.'})
until(lambda: len(smtp.messages) > n0m)
m5 = smtp.messages[-1] if len(smtp.messages) > n0m else {}
b5t, b5h = m5.get('text') or '', m5.get('html') or ''
b5x = re.sub(r'<[^>]+>', '', b5h)   # sichtbarer Text der HTML-Fassung
check('E-Mail (Liste): je Partie Charge, MHD und Menge', st == 200 and '10601 Roastbeef, frisch: 24,90 €/kg, Charge P-0002 · MHD 04.12.2026 · 10,00 kg' in b5t
      and 'Charge P-0001 · MHD 20.11.2026 · 15,00 kg' in b5t and 'Charge P-0002 · MHD 04.12.2026' in b5x and '15,00 kg' in b5x, b5t[:600])
check('E-Mail: ohne EK, Bestand und weitere Partien', not re.search(r'18,50|19,25|TEST-A|Eingelagert|25,00 kg', b5t + b5h))

# ---------- Oberfläche ----------
errors = []


def ed_count(pg):
    return pg.locator('#ez-pos tr[data-i]').count()

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script('window.print = () => { window.__gedruckt = true; };')
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
    a.press('#ez-kunde', 'Escape')
    check('Escape schließt die Liste, kein Kunde gewählt', a.locator('#ez-kunde-list').is_hidden() and a.input_value('#ez-kunde') == '')
    a.fill('#ez-kunde', 'KANTINE.AN'); a.wait_for_selector('#ez-kunde-list li.akt[data-kid]')
    check('Kundensuche: Kundennummer, bester Treffer zuerst', a.get_attribute('#ez-kunde-list li.akt', 'data-kid') == kid2)
    a.press('#ez-kunde', 'Enter'); a.wait_for_selector('#ez-kunde-list', state='hidden')
    check('Enter wählt den Kunden, Angaben darunter', a.input_value('#ez-kunde').startswith('Andere Kantine') and 'Testweg 1' in a.inner_text('.ez-kinfo') and a.locator('#ez-dirty').is_visible(), a.input_value('#ez-kunde'))
    a.click('#ez-kunde'); a.fill('#ez-kunde', 'einzel'); a.wait_for_selector('#ez-kunde-list li[data-kid]'); a.keyboard.press('Tab')
    check('Verlassen ohne Auswahl behält den gewählten Kunden', a.input_value('#ez-kunde').startswith('Andere Kantine') and a.locator('#ez-kunde-list').is_hidden())
    # Kopfleiste: im Einzelangebot Drucken/E-Mail des Einzelangebots statt „Drucken“ des Wochenangebots
    kl = [a.locator('#btn-drucken').is_hidden(), a.locator('#btn-ez-druck').is_visible(), a.locator('#btn-ez-mail').is_hidden(), a.locator('#btn-publish').count() == 0, a.locator('#btn-send').count() == 0]
    check('Kopfleiste im Einzelangebot: oben „Drucken / PDF“ des Einzelangebots, nicht „Drucken“ des Wochenangebots', all(kl), kl)   # E-Mail erst nach dem Speichern
    check('kein Suchfeld mehr neben dem Angebot, dafür „Artikel hinzufügen“', a.locator('#ez-q').count() == 0 and a.locator('#ez-add').is_visible())

    # Fenster „Artikel hinzufügen“: zuerst VK-Gruppe, dann Artikel; Suche über alle Gruppen
    a.click('#ez-add'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-grp [data-grp]')
    pk = '#dlg-ez-pick'
    check('Fenster: Kunde im Kopf, Startansicht „zuerst eine VK-Gruppe wählen“, Suchfeld hat den Fokus', 'Andere Kantine' in a.inner_text(pk + ' .ezp-head')
          and 'Zuerst eine VK-Gruppe wählen' in a.inner_text('#ezp-list') and a.evaluate("document.activeElement.id") == 'ezp-q')
    grp = lambda: {b['nr']: b for b in a.eval_on_selector_all('#ezp-grp [data-grp]', 'e => e.map(x => ({nr: x.dataset.grp, t: x.innerText, n: +x.querySelector(".ezp-g-z").textContent, on: x.getAttribute("aria-pressed")}))')}   # noqa: E731
    g = grp()
    check('Gruppenleiste: Alle, vorkommende VK-Gruppen mit Anzahl (nur mit Bestand), „ohne VK-Gruppe“', list(g)[:4] == ['*', '1600', '1610', '6150'] and '–' in g and '7000' not in g
          and g['1600']['n'] == 1 and g['1610']['n'] == 1 and g['6150']['n'] == 1 and 'Rindfleisch, Argentinien, frisch' in g['1600']['t'], {k: v['n'] for k, v in g.items()})
    a.uncheck('#ezp-bestand'); a.wait_for_function("+document.querySelector('#ezp-grp [data-grp=\"1600\"] .ezp-g-z').textContent === 2")
    check('ohne „nur mit Bestand“: alle Artikel der Gruppe zählen', grp()['1600']['n'] == 2)
    a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10701"]')
    codes = a.eval_on_selector_all('#ezp-list tr[data-code]', 'e => e.map(x => x.dataset.code)')
    check('Gruppe gewählt: nur deren Artikel, Gruppe markiert', codes == ['10601', '10701'] and grp()['1600']['on'] == 'true' and 'Rindfleisch, Argentinien, frisch' in a.inner_text('.ezp-lkopf'), codes)
    t = a.inner_text('#ezp-list tr[data-code="10601"]')
    check('Zeile: eingelagert, erwartet, kürzestes MHD, Wochenpreis, Herkunft', '40,00 kg' in t and '10,00 kg' in t and '20.11.2026' in t and '25,54 €' in t and 'AR' in t, t)
    check('ohne Bestand: „kein Bestand“', 'kein Bestand' in a.inner_text('#ezp-list tr[data-code="10701"]'))
    a.click('#ezp-list [data-info="10601"]'); a.wait_for_selector('#ezp-list tr[data-det="10601"]')
    d = a.inner_text('#ezp-list tr[data-det="10601"]')
    check('Details: Bestand eingelagert/erfasst/gesamt, kürzestes MHD', 'Eingelagert 40,00 kg' in d and 'Erfasst 10,00 kg' in d and 'Gesamt verfügbar 50,00 kg' in d and '20.11.2026' in d, d)
    check('Details: Partien mit Eingang, MHD, Kolli, kg und EK', 'P-0001' in d and 'P-0002' in d and '04.12.2026' in d and '19,25' in d and 'EK' in d, d)
    check('Details: erwartete Ankunft mit ETA, VK-Gruppe, Merkmale', 'TEST-A' in d and '22.10.2026' in d and '1600 · Rindfleisch, Argentinien, frisch' in d and 'frisch' in d, d)
    check('Detailknopf zeigt Zustand an', a.get_attribute('#ezp-list [data-info="10601"]', 'aria-expanded') == 'true')
    a.screenshot(path=SH + '/einzelangebot-auswahl.png')
    box = a.evaluate("(() => { const r = document.querySelector('#dlg-ez-pick').getBoundingClientRect(), l = document.querySelector('#ezp-list'); return [r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight, l.scrollWidth - l.clientWidth]; })()")
    check('Fenster passt ins Bild, Tabelle ohne seitliches Scrollen', box[0] and box[1] <= 1, box)
    a.click('#ezp-list [data-info="10601"]'); a.wait_for_selector('#ezp-list tr[data-det="10601"]', state='detached')
    # Suche oben sucht in der gewählten Gruppe (Wunsch des Inhabers: erst Gruppe, dann Artikel); Treffer anderswo per Knopf
    check('Suchfeld nennt die gewählte Gruppe', 'Rindfleisch, Argentinien, frisch' in (a.get_attribute('#ezp-q', 'placeholder') or ''), a.get_attribute('#ezp-q', 'placeholder'))
    a.fill('#ezp-q', 'steakhüfte'); a.wait_for_selector('#ezp-list .ezp-anderswo [data-grp="*"]')
    check('Suche in der gewählten Gruppe: kein Treffer dort, Knopf „In allen Gruppen suchen“ mit Anzahl', a.locator('#ezp-list tr[data-code]').count() == 0
          and grp()['1600']['on'] == 'true' and 'Keine Treffer in dieser Gruppe' in a.inner_text('#ezp-list') and re.search(r'In allen Gruppen suchen \(\d+ weitere(r)? Treffer\)', a.inner_text('#ezp-list .ezp-anderswo')), a.inner_text('#ezp-list')[-200:])
    a.click('#ezp-list .ezp-anderswo [data-grp="*"]'); a.wait_for_selector('#ezp-list tr[data-code="10823"]')
    sx = [a.eval_on_selector_all('#ezp-list tr.ezp-gr', 'e => e.map(x => x.innerText)'), grp()['*']['on'], a.eval_on_selector_all('#ezp-list tr[data-code]', 'e => e.map(x => x.dataset.code)')]
    check('Suche über alle Gruppen mit Gruppen-Zwischenzeile, Leiste zeigt „Alle“', any('Rindfleisch, Uruguay, frisch' in x for x in sx[0]) and sx[1] == 'true' and '10823' in sx[2], sx)
    # Gruppensuche links: filtert die Leiste (Nummer oder Name), Enter wählt die erste Gruppe und springt in die Artikelsuche
    a.fill('#ezp-q', ''); a.fill('#ezp-gq', 'urugu')
    vis = a.eval_on_selector_all('#ezp-grp [data-grp]', 'e => e.filter(x => !x.hidden).map(x => x.dataset.grp)')
    check('Gruppensuche: nur passende Gruppen (und „Alle“)', vis == ['*', '1610'], vis)
    a.press('#ezp-gq', 'Enter'); a.wait_for_function("document.querySelector('#ezp-grp [data-grp=\"1610\"]').getAttribute('aria-pressed') === 'true'")
    check('… Enter wählt die Gruppe, Fokus in der Artikelsuche', a.evaluate('document.activeElement.id') == 'ezp-q' and '10823' in a.eval_on_selector_all('#ezp-list tr[data-code]', 'e => e.map(x => x.dataset.code)'))
    a.fill('#ezp-gq', '6150'); vis = a.eval_on_selector_all('#ezp-grp [data-grp]', 'e => e.filter(x => !x.hidden).map(x => x.dataset.grp)')
    check('Gruppensuche nach Nummer; gewählte Gruppe bleibt sichtbar', vis == ['*', '1610', '6150'], vis)
    a.fill('#ezp-gq', 'gibtesnicht'); check('Gruppensuche ohne Treffer: Hinweis', a.locator('#ezp-gleer').is_visible())
    a.fill('#ezp-gq', ''); a.click('#ezp-grp [data-grp="*"]'); a.fill('#ezp-q', 'steakhüfte'); a.wait_for_selector('#ezp-list tr[data-code="10823"]')
    a.click('#ezp-list [data-info="10823"]'); a.wait_for_selector('#ezp-list tr[data-det="10823"]')
    d = a.inner_text('#ezp-list tr[data-det="10823"]')
    check('Details: nur erwartet, ETA unbekannt', 'ETA unbekannt' in d and 'TEST-B' in d and 'Kein eingelagerter Bestand' in d, d)
    a.fill('#ezp-q', 'irland'); a.wait_for_selector('#ezp-list tr[data-code="900001"]')   # „Irland“ steht nur in der VK-Gruppe (Herkunft „IRL“)
    check('Suche findet auch die Bezeichnung der VK-Gruppe; „nicht im Wochenangebot“', a.get_attribute('#ezp-list tr[data-code="900001"] .ezp-p span', 'title') == 'nicht im Wochenangebot')
    a.fill('#ezp-q', ''); a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    a.click('#ezp-list tr[data-code="10601"] .ezp-n')   # Klick auf die Zeile markiert
    check('Zeile markiert, Fuß zeigt Anzahl', a.is_checked('#ezp-list [data-sel="10601"]') and '1 Artikel ausgewählt' in a.inner_text('#ezp-anz') and '1 Artikel hinzufügen' in a.inner_text('#ezp-ok'))
    a.click('#ezp-grp [data-grp="6150"]'); a.wait_for_selector('#ezp-list tr[data-code="900001"]'); a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    check('Auswahl bleibt beim Gruppenwechsel erhalten', a.is_checked('#ezp-list [data-sel="10601"]'))
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); a.wait_for_selector('#ez-pos tr[data-i="0"]')
    row = '#ez-pos tr[data-i="0"]'
    check('Position übernommen: Wochenpreis vorbelegt, Abweichung ±0,0 %', a.input_value(row + ' [data-f="price"]') == '25,54' and '±0,0 %' in a.inner_text(row + ' .ez-a')
          and '50,00 kg' in a.inner_text(row + ' .ez-b') and ed_count(a) == 1, a.inner_text(row))
    a.click('#ez-add'); a.wait_for_selector('#dlg-ez-pick[open]'); a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    check('bereits übernommener Artikel nicht doppelt wählbar („im Angebot“)', a.is_disabled('#ezp-list [data-sel="10601"]') and 'im Angebot' in a.inner_text('#ezp-list tr[data-code="10601"]'))
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    check('Escape schließt das Fenster ohne Änderung', ed_count(a) == 1)
    a.fill(row + ' [data-f="price"]', '23,50')
    check('Abweichung unter Wochenpreis: Punkt und −8,0 % (eine Nachkommastelle wie alle Prozente)', a.get_attribute(row + ' .ez-abw', 'class').endswith('ab-unter') and '−8,0 %' in a.inner_text(row + ' .ez-a'), a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="price"]', '20')
    check('starke Abweichung (> 10 %) hervorgehoben', 'ab-stark' in a.get_attribute(row + ' .ez-abw', 'class') and '−21,7 %' in a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="price"]', '27,50')
    check('über Wochenpreis: +7,7 %', 'ab-ueber' in a.get_attribute(row + ' .ez-abw', 'class') and '+7,7 %' in a.inner_text(row + ' .ez-a'))
    a.fill(row + ' [data-f="qty"]', '12'); a.press(row + ' [data-f="qty"]', 'Tab')
    a.wait_for_function("document.querySelector('#ez-summe') && document.querySelector('#ez-summe').textContent.includes('330,00')")
    check('Summe: 12,00 kg · 330,00 € (Menge mit 2 Stellen)', '12,00 kg' in a.inner_text('#ez-summe'), a.inner_text('#ez-summe'))
    a.fill(row + ' [data-f="qty"]', 'abc')
    check('ungültige Menge markiert', 'invalid' in a.get_attribute(row + ' [data-f="qty"]', 'class'))
    a.fill(row + ' [data-f="qty"]', '12'); a.press(row + ' [data-f="qty"]', 'Tab')
    a.click('#ez-frei'); a.wait_for_selector('#ez-pos tr[data-i="1"]')
    check('freie Position: Bezeichnung markiert zum Überschreiben', a.input_value('#ez-pos tr[data-i="1"] [data-f="name"]') == 'Freie Position' and a.evaluate("document.activeElement.dataset.f") == 'name')
    a.keyboard.type('Sonderschnitt')
    check('ungespeichert-Hinweis', a.locator('#ez-dirty').is_visible())
    a.screenshot(path=SH + '/einzelangebot-bearbeiten.png', full_page=True)
    a.click('#ez-save'); a.wait_for_selector('#ez-freigeben')
    nr2 = a.inner_text('.ez-top h2')
    check('gespeichert: Nummer vergeben, Freigabe möglich', f'E-{date.today().year}-000' in nr2 and not a.locator('#ez-dirty').is_visible(), nr2)
    saved = [x for x in doc('einzelangebote')['list'] if x['kid'] == kid2 and len(x['positions']) == 2]
    check('gespeichert wie eingegeben', saved and saved[0]['positions'][0] == {'code': '10601', 'name': 'Roastbeef, frisch', 'qty': 12.0, 'price': 27.5, 'notiz': ''}
          and saved[0]['positions'][1] == {'code': '', 'name': 'Sonderschnitt', 'qty': None, 'price': None, 'notiz': ''}, saved[0]['positions'] if saved else None)
    check('nach dem Speichern oben auch „Per E-Mail senden“', a.locator('#btn-ez-mail').is_visible() and a.locator('#btn-ez-druck').is_visible())
    a.click('#ez-freigeben'); a.wait_for_selector('#ez-entfreigeben')
    check('im Portal freigegeben (Oberfläche)', 'Im Portal freigegeben' in a.inner_text('.ez-top'), a.inner_text('.ez-top'))

    # Drucken / PDF: Angebotsseite mit deren Druckdialog (wie in der Kundenansicht)
    with ctx.expect_page() as pi:
        a.click('#btn-ez-druck')
    w = pi.value; w.on('pageerror', lambda e: errors.append(str(e)))
    w.wait_for_selector('#dlg-print[open]')
    check('Drucken öffnet die Angebotsseite des Einzelangebots mit dem Druckdialog', '?angebot=e-' in w.url and 'drucken' not in w.url and w.is_checked('#dlg-print input[name="layout"][value="liste"]'), w.url)
    w.click('#print-go'); w.wait_for_function('window.__gedruckt === true')
    w.wait_for_function("(() => { const i = document.querySelector('#print-root .pl-ph img'); return i && i.complete && i.naturalWidth > 0; })()")
    wt = w.inner_text('#print-root')
    check('Ausdruck „Angebotsliste“: Logo, Kunde, Positionen, eigene Preise', 'für Andere Kantine' in wt and 'Roastbeef' in wt and '27,50' in wt and 'Sonderschnitt' in wt, wt[:300])
    check('Ausdruck ohne Bestand, Partien und Wochenpreis', '25,54' not in wt and 'P-0001' not in wt and 'TEST-A' not in wt and 'Eingelagert' not in wt)
    w.close()
    with ctx.expect_page() as pi:
        a.click('#ez-druck')
    w = pi.value; w.wait_for_selector('#dlg-print[open]')
    check('auch der Knopf unten öffnet den Druckdialog der Angebotsseite', '?angebot=e-' in w.url)
    w.close()

    # E-Mail-Dialog: Format wählbar, PDF-Vorschau
    a.click('#btn-ez-mail'); a.wait_for_selector('#dlg-einzel-mail[open]')
    check('E-Mail-Dialog: Liste oder PDF-Anhang, Liste vorgewählt, PDF-Vorschau', a.is_checked('#dlg-einzel-mail input[value="liste"]') and a.locator('#dlg-einzel-mail input[value="pdf"]').count() == 1
          and 'einzel_pdf' in a.get_attribute('#dlg-einzel-mail .ez-pdf-vorschau a', 'href'))
    a.screenshot(path=SH + '/einzelangebot-mail.png')
    a.click('#dlg-einzel-mail [data-close]'); a.wait_for_selector('#dlg-einzel-mail', state='hidden')
    a.click('#ez-zurueck'); a.wait_for_selector('#view-einzel tr[data-ez]')
    kl = [a.locator('#btn-ez-druck').is_hidden(), a.locator('#btn-drucken').is_hidden()]
    check('Übersicht: oben weder Drucken des Einzelangebots noch des Wochenangebots', all(kl), kl)
    check('zurück zur Übersicht: neues Angebot gelistet', a.locator('#view-einzel tr[data-ez]').count() >= 3)
    a.screenshot(path=SH + '/einzelangebote-liste.png')
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden])')
    kl = [a.locator('#btn-drucken').is_visible(), a.locator('#btn-ez-druck').is_hidden()]
    check('außerhalb der Einzelangebote wieder „Drucken“ des Wochenangebots', all(kl), kl)
    a.click('#vt-einzel'); a.wait_for_selector('#view-einzel tr[data-ez]')

    # Alle Artikel einer Gruppe markieren und auf einmal übernehmen
    a.click('#ez-neu'); a.wait_for_selector('#ez-add')
    a.click('#ez-add'); a.wait_for_selector('#dlg-ez-pick[open]')
    a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10701"]')
    a.click('#ezp-alle')
    check('„Alle dieser Gruppe markieren“', '2 Artikel ausgewählt' in a.inner_text('#ezp-anz') and 'Markierung aufheben' in a.inner_text('#ezp-alle'))
    a.click('#ezp-alle')
    check('Markierung aufheben', a.is_disabled('#ezp-ok') and 'Alle dieser Gruppe markieren' in a.inner_text('#ezp-alle'))
    a.click('#ezp-alle'); a.click('#ezp-grp [data-grp="1610"]'); a.wait_for_selector('#ezp-list tr[data-code="10823"]'); a.check('#ezp-list [data-sel="10823"]')
    a.click('#ezp-ok'); a.wait_for_selector('#ez-pos tr[data-i="2"]')
    codes = a.eval_on_selector_all('#ez-pos tr[data-i] .ez-code', 'e => e.map(x => x.textContent)')
    check('drei Artikel aus zwei Gruppen übernommen (nach Gruppe sortiert), Wochenpreise vorbelegt', codes == ['10601', '10701', '10823'] and a.input_value('#ez-pos tr[data-i="1"] [data-f="price"]') == '27,21', codes)
    a.click('#ez-zurueck'); a.click('#dlg-confirm .btn.primary'); a.wait_for_selector('#view-einzel tr[data-ez]')

    # Partien (Inhaber 13.11.2026): je Position eine Partie wählen, weitere Partie als eigene Position, Menge ≤ Partie
    a.click(f'#view-einzel tr[data-ez="{e5["id"]}"]'); a.wait_for_selector('#ez-pos tr[data-i="1"] [data-f="partie"]')
    check('Partie-Auswahl zeigt die gespeicherte Partie', a.input_value('#ez-pos tr[data-i="0"] [data-f="partie"]') == 'P-0002' and a.input_value('#ez-pos tr[data-i="1"] [data-f="partie"]') == 'P-0001'
          and a.locator('#ez-pos tr[data-i="2"] [data-f="partie"]').count() == 0)
    with ctx.expect_page() as pi:
        a.click('#btn-ez-druck')
    w = pi.value; w.on('pageerror', lambda e: errors.append(str(e)))
    w.wait_for_selector('#dlg-print[open]'); w.click('#print-go'); w.wait_for_function('window.__gedruckt === true')
    wt = w.inner_text('#print-root')
    check('Druck (Angebotsansicht): je Partie Charge, MHD und Menge, kein EK', 'Charge P-0002 · MHD 04.12.2026 · 10,00 kg' in wt and 'Charge P-0001 · MHD 20.11.2026 · 15,00 kg' in wt
          and not re.search(r'18,50|19,25|TEST-A|Eingelagert', wt), wt[:400])
    w.emulate_media(media='print'); w.screenshot(path=SH + '/einzelangebot-partien-druck.png', full_page=True)
    w.close()
    a.click('#ez-zurueck'); a.wait_for_selector('#view-einzel tr[data-ez]')
    a.click('#ez-neu'); a.wait_for_selector('#ez-kunde')
    a.click('#ez-kunde'); a.fill('#ez-kunde', 'kantine einzel'); a.wait_for_selector('#ez-kunde-list li.akt[data-kid]'); a.press('#ez-kunde', 'Enter'); a.wait_for_selector('#ez-kunde-list', state='hidden')
    a.click('#ez-add'); a.wait_for_selector('#dlg-ez-pick[open]'); a.click('#ezp-grp [data-grp="1600"]'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    a.check('#ezp-list [data-sel="10601"]'); a.click('#ezp-ok'); a.wait_for_selector('#ez-pos tr[data-i="0"] [data-f="partie"]')
    r0 = '#ez-pos tr[data-i="0"]'
    opts = a.eval_on_selector_all(r0 + ' [data-f="partie"] option', 'e => e.map(x => x.value + "|" + x.textContent)')
    check('Partien zur Wahl: ohne, frühestes MHD zuerst, mit MHD und kg, ohne EK', opts == ['|ohne Partie', 'P-0001|P-0001 · MHD 20.11.2026 · 15,00 kg', 'P-0002|P-0002 · MHD 04.12.2026 · 25,00 kg'], opts)
    a.select_option(r0 + ' [data-f="partie"]', 'P-0001'); a.wait_for_selector(r0 + ' [data-partie-plus]')
    check('Partie gewählt: Menge mit der Partie vorbelegt, „+ Partie“ für weitere', a.input_value(r0 + ' [data-f="qty"]') == '15' and a.locator(r0 + ' [data-partie-plus]').is_visible())
    a.click(r0 + ' [data-partie-plus]'); a.wait_for_selector('#ez-pos tr[data-i="1"] [data-f="partie"]')
    r1 = '#ez-pos tr[data-i="1"]'
    check('weitere Partie als eigene Position (nächste freie Partie, Menge, gleicher Preis)', a.input_value(r1 + ' [data-f="partie"]') == 'P-0002' and a.input_value(r1 + ' [data-f="qty"]') == '25'
          and a.input_value(r1 + ' [data-f="price"]') == a.input_value(r0 + ' [data-f="price"]') and ed_count(a) == 2)
    gesperrt = a.eval_on_selector(r0 + ' [data-f="partie"] option[value="P-0002"]', 'o => [o.disabled, o.textContent]')
    check('vergebene Partie in der anderen Position gesperrt, kein weiteres „+ Partie“', gesperrt == [True, 'P-0002 · MHD 04.12.2026 · 25,00 kg (Position 2)'] and a.locator('#ez-pos [data-partie-plus]').count() == 0,
          (gesperrt, a.locator('#ez-pos [data-partie-plus]').count()))
    a.fill(r1 + ' [data-f="qty"]', '30')
    check('Menge über der Partie markiert', 'invalid' in a.get_attribute(r1 + ' [data-f="qty"]', 'class'))
    a.click('#ez-save'); a.wait_for_function("document.body.innerText.includes('größer als die Partie P-0002')")
    check('Speichern mit zu großer Menge abgewiesen (Hinweis)', a.locator('#ez-dirty').is_visible())
    a.fill(r1 + ' [data-f="qty"]', '20'); a.press(r1 + ' [data-f="qty"]', 'Tab')
    a.screenshot(path=SH + '/einzelangebot-partien.png', full_page=True)
    a.click('#ez-save'); a.wait_for_selector('#ez-freigeben')
    neu6 = max((x for x in doc('einzelangebote')['list'] if x['kid'] == kid), key=lambda x: x['changed'])
    check('über die Oberfläche gespeichert: zwei Positionen mit Partie (Schnappschuss)', [(p['qty'], p.get('partie')) for p in neu6['positions']]
          == [(15, {'lot': 'P-0001', 'mhd': '2026-11-20', 'kg': 15}), (20, {'lot': 'P-0002', 'mhd': '2026-12-04', 'kg': 25})], neu6['positions'])
    a.select_option(r0 + ' [data-f="partie"]', ''); a.wait_for_selector(r0 + ' [data-partie-plus]', state='detached')
    check('„ohne Partie“ entfernt die Zuordnung (Menge bleibt)', a.input_value(r0 + ' [data-f="qty"]') == '15' and a.locator('#ez-dirty').is_visible())
    a.select_option(r0 + ' [data-f="partie"]', 'P-0001'); a.click('#ez-save'); a.wait_for_function("!document.querySelector('#ez-dirty') || document.querySelector('#ez-dirty').hidden")
    a.click('#ez-zurueck'); a.wait_for_selector('#view-einzel tr[data-ez]')

    a.set_viewport_size({'width': 390, 'height': 820}); a.emulate_media(color_scheme='dark')   # mobil im dunklen Modus
    a.locator('#view-einzel tr[data-ez]').first.click(); a.wait_for_selector('#ez-pos')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Mobil 390 px: kein seitliches Scrollen', over <= 1, over)
    sel = a.evaluate("[...document.querySelectorAll('#ez-pos [data-f=\"partie\"]')].map(s => { const r = s.getBoundingClientRect(); return r.width > 80 && r.left >= 0 && r.right <= innerWidth; })")
    check('Mobil 390 px: Partie-Auswahl je Position sichtbar und im Bild', sel == [True, True], sel)
    a.screenshot(path=SH + '/einzelangebot-mobil.png', full_page=True)
    a.click('#ez-add'); a.wait_for_selector('#dlg-ez-pick[open]')
    check('Mobil: Gruppenwahl als Auswahlliste', a.locator('#ezp-grp-sel').is_visible() and a.locator('.ezp-nav').is_hidden())
    a.select_option('#ezp-grp-sel', '1600'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    a.click('#ezp-list [data-info="10601"]'); a.wait_for_selector('#ezp-list tr[data-det="10601"]')
    m = a.evaluate("(() => { const l = document.querySelector('#ezp-list'), r = document.querySelector('#dlg-ez-pick').getBoundingClientRect(); return [l.scrollWidth - l.clientWidth, r.width <= innerWidth]; })()")
    check('Mobil 390 px: Fenster füllt den Bildschirm, kein seitliches Scrollen', m[0] <= 1 and m[1], m)
    a.screenshot(path=SH + '/einzelangebot-auswahl-mobil.png')
    a.keyboard.press('Escape')

    # Leser: nur ansehen
    lp = br.new_page(viewport={'width': 1280, 'height': 900})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    lp.goto(BASE + '/admin/'); lp.wait_for_selector('#screen-auth:not([hidden])')
    lp.fill('#au-user', 'lea'); lp.fill('#pw1', 'Leserin-Zugang-1'); lp.click('#auth-submit'); lp.wait_for_selector('#vt-einzel:not([hidden])')
    lp.click('#vt-einzel'); lp.wait_for_selector('#view-einzel tr[data-ez]')
    check('Leser: kein „Neues Einzelangebot“', lp.locator('#ez-neu').count() == 0)
    lp.locator('#view-einzel tr[data-ez]').first.click(); lp.wait_for_selector('#ez-pos')
    check('Leser: nur lesend, kein „Artikel hinzufügen“', lp.locator('#ez-save').count() == 0 and lp.locator('#ez-add').count() == 0 and lp.locator('#ez-kunde').is_disabled())
    check('Leser: oben nur Drucken, kein E-Mail-Versand', lp.locator('#btn-ez-druck').is_visible() and lp.locator('#btn-ez-mail').is_hidden() and lp.locator('#ez-mail').count() == 0)
    pt = lp.eval_on_selector_all('#ez-pos .ez-partie-t', 'e => e.map(x => x.textContent)')
    check('Leser: Partien nur als Text', pt == ['Partie P-0001 · MHD 20.11.2026 · 15,00 kg', 'Partie P-0002 · MHD 04.12.2026 · 25,00 kg'] and lp.locator('#ez-pos [data-f="partie"]').count() == 0, pt)
    lp.close()

    # E-Mail an den Kunden mit Partien (Liste) als Bild: 600 und 390 px
    mp = br.new_page(viewport={'width': 600, 'height': 900})
    mp.set_content(b5h)
    mp.screenshot(path=SH + '/einzelangebot-partien-mail.png', full_page=True)
    mp.set_viewport_size({'width': 390, 'height': 900})
    over = mp.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('E-Mail mit Partien bei 390 px ohne seitliches Scrollen', over <= 1, over)
    mp.screenshot(path=SH + '/einzelangebot-partien-mail-mobil.png', full_page=True)
    mp.close()

    # Bearbeiter ohne „Bestand ansehen“: Partien sichtbar, aber keine Auswahl (Server: 403 bei neuer Zuordnung)
    ep = br.new_page(viewport={'width': 1280, 'height': 900})
    ep.on('pageerror', lambda e: errors.append(str(e)))
    ep.goto(BASE + '/admin/'); ep.wait_for_selector('#screen-auth:not([hidden])')
    ep.fill('#au-user', 'eddi'); ep.fill('#pw1', 'Editor-Zugang-77'); ep.click('#auth-submit'); ep.wait_for_selector('#vt-einzel:not([hidden])')
    ep.click('#vt-einzel'); ep.wait_for_selector(f'#view-einzel tr[data-ez="{e5["id"]}"]')
    ep.click(f'#view-einzel tr[data-ez="{e5["id"]}"]'); ep.wait_for_selector('#ez-pos .ez-partie-t')
    pt = ep.eval_on_selector_all('#ez-pos .ez-partie-t', 'e => e.map(x => x.textContent)')
    check('ohne Bestandsrecht: Partien als Text, keine Auswahl, Bearbeiten möglich', pt == ['Partie P-0002 · MHD 04.12.2026 · 25,00 kg', 'Partie P-0001 · MHD 20.11.2026 · 15,00 kg']
          and ep.locator('#ez-pos [data-f="partie"]').count() == 0 and ep.locator('#ez-save').is_visible(), pt)
    ep.screenshot(path=SH + '/einzelangebot-partien-ohne-bestandsrecht.png')
    ep.close()

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

    # Portal: Kunde sieht in seinem Einzelangebot je Partie Charge, MHD und Menge (Angebotsansicht, Bestellansicht, Details, 390 px)
    pctx = br.new_context(viewport={'width': 1280, 'height': 900})
    c = pctx.new_page()
    c.on('pageerror', lambda e: errors.append(str(e)))
    c.goto(BASE + '/'); c.wait_for_selector('#btn-kunde-login'); c.click('#btn-kunde-login')
    c.fill('#kl-form [name=username]', 'kantine.einzel'); c.fill('#kl-form [name=password]', KPW); c.click('#kl-form [type=submit]')
    c.wait_for_selector('.k-switch [data-kswitch^="e-"]')
    c.goto(BASE + '/?angebot=' + EID5); c.wait_for_selector('#list .al-partie')
    at = c.inner_text('#list')
    check('Portal (Angebotsansicht): Charge, MHD und Menge je Partie', 'Charge P-0002 · MHD 04.12.2026 · 10,00 kg' in at and 'Charge P-0001 · MHD 20.11.2026 · 15,00 kg' in at
          and c.locator('#list .al-partie').count() == 2, at[:400])
    check('Portal: kein EK, kein Bestand, keine weiteren Partien', not re.search(r'18,50|19,25|TEST-A|Eingelagert|25,00 kg|P-0003', c.inner_text('body')))
    c.screenshot(path=SH + '/einzelangebot-partien-portal.png')
    c.click('#modebar [data-mode=liste]'); c.wait_for_selector('#list .t-partie')
    check('Portal (Bestellansicht): Partie unter der Bezeichnung', 'Charge P-0002 · MHD 04.12.2026 · 10,00 kg' in c.inner_text('#list .grid'))
    c.click('#list .name-btn >> nth=0'); c.wait_for_selector('#dlg-detail[open]')
    dt = c.inner_text('#dlg-detail')
    check('Portal (Details): Charge, MHD und Menge', 'Charge' in dt and 'P-0002' in dt and '04.12.2026' in dt and '10,00 kg' in dt, dt[:300])
    c.keyboard.press('Escape')
    m = pctx.new_page(); m.set_viewport_size({'width': 390, 'height': 820})
    m.on('pageerror', lambda e: errors.append(str(e)))
    m.goto(BASE + '/?angebot=' + EID5); m.wait_for_selector('#list .partie')
    over = m.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    vis = m.evaluate("[...document.querySelectorAll('#list .partie')].filter(x => x.offsetParent).map(x => { const r = x.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 1; })")
    check('Portal mobil 390 px: Partien sichtbar, kein seitliches Scrollen', over <= 1 and len(vis) == 2 and all(vis), (over, vis))
    m.screenshot(path=SH + '/einzelangebot-partien-portal-mobil.png', full_page=True)
    pctx.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
