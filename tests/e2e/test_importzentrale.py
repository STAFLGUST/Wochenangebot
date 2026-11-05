"""Importzentrale (Verwaltung → Import, Roadmap 10b): eine Stelle für alle Importe mit einheitlichem Ablauf
(Importart → Datei → Vorschau neu/geändert/entfällt/Fehler je Zeile → Übernahme → Ergebnis und Protokoll).

Geprüft: Registrierung beim Daten-Eigentümer (Verwaltung, Bestand, Angebot), Rechte je Importart serverseitig (403) und
in der Anzeige, Wartung der Oberfläche (503, Administratoren arbeiten weiter), Vorschau und Übernahme für Kunden
(Verwaltung, mit Passwortbestätigung) und Bestand (anderer Eigentümer), Kundengruppen, Artikelstammdaten und Preisverlauf
über die Oberfläche, Fehlerfälle (falsche Datei, falsche Kodierung, leere Datei, veralteter Stand), Protokoll, keine
Einkaufspreise in der Vorschau, Bildschirmfotos Desktop und 390 px. Nur Testdaten aus tests/fixtures."""
import base64
import json
import os
import re
import sys
import tomllib
import urllib.request

from playwright.sync_api import sync_playwright

from auth_helpers import expire_session
from kunden_hilfe import Client
from umgebung import BASE, FIX, REPO, SH, WORK, storage_raw

PW = 'Sicheres-Passwort-1'
ZUGANG = {'eddi': 'Editor-Zugang-77', 'lea': 'Leserin-Zugang-1', 'kai': 'Kunden-Zugang-42'}   # nur Testzugänge
KUNDEN_CSV = FIX + '/kunden/kundendaten.csv'
GRUPPEN_CSV = FIX + '/kundengruppen/kundengruppen.csv'
ARTIKEL_CSV = FIX + '/stammdaten/artikelstammdaten.csv'
VK_CSV = FIX + '/stammdaten/vkgruppen.csv'
BESTAND_XLS = FIX + '/bestand/bestand.xls'
BESTAND_CSV = FIX + '/bestand/bestand.csv'   # CSV-Ausgabe der Bestandsliste (synthetisch)
KW = [FIX + '/angebote/Wochenangebot KW 37 2026.xlsx', FIX + '/angebote/Wochenangebot KW 38 2026.xlsx']
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def log_text(cl):
    return json.dumps(cl.call('log')[1], ensure_ascii=False)


def bestaetigung_ablaufen(cl):
    jar = next(h.cookiejar for h in cl.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor))
    expire_session(next(c.value for c in jar if c.name == 'WA_ADMIN'))


# Testdateien für Fehlerfälle (nur im Arbeitsordner, aus den Testdaten erzeugt)
UTF16_CSV = os.path.join(WORK, 'importzentrale-kunden-utf16.csv')
with open(KUNDEN_CSV, encoding='windows-1252') as f, open(UTF16_CSV, 'w', encoding='utf-16') as g:
    g.write(f.read())
LEER_CSV = os.path.join(WORK, 'importzentrale-leer.csv')
open(LEER_CSV, 'wb').close()
NUR_KOPF_CSV = os.path.join(WORK, 'importzentrale-nur-leerzeilen.csv')
with open(NUR_KOPF_CSV, 'w', encoding='utf-8') as g:
    g.write('﻿\r\n;;;\r\n\r\n')

A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': ZUGANG['eddi'], 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': ZUGANG['lea'], 'mustChange': False})
A.call('user_save', {'username': 'kai', 'name': 'Kai Kunden', 'role': 'viewer', 'active': True, 'password': ZUGANG['kai'], 'mustChange': False,
                     'grant': ['kunden.sehen', 'kunden.bearbeiten']})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': ZUGANG['eddi']})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': ZUGANG['lea']})[0] == 200
K = Client('198.51.100.5'); assert K.call('login', {'username': 'kai', 'password': ZUGANG['kai']})[0] == 200
ids = lambda cl: sorted(a['id'] for a in cl.call('import_arten')[1].get('arten', []))   # noqa: E731

# ---------- Registrierung: jede Importart gehört dem Daten-Eigentümer ----------
st, r = A.call('import_arten')
arten = {a['id']: a for a in r.get('arten', [])}
ALLE = ['angebot_preise', 'bestand', 'kunden', 'kundengruppen', 'preisverlauf', 'stammdaten', 'umsatzdaten', 'vertreter', 'vkgruppen', 'zeitbericht', 'zeiterfassung']
check('Administrator sieht alle heutigen Importe', st == 200 and sorted(arten) == ALLE, sorted(arten))
EIG = {'kunden': 'verwaltung', 'kundengruppen': 'verwaltung', 'vkgruppen': 'verwaltung', 'vertreter': 'verwaltung', 'stammdaten': 'verwaltung',
       'bestand': 'bestand', 'preisverlauf': 'angebot', 'angebot_preise': 'angebot', 'zeiterfassung': 'hr',
       'umsatzdaten': 'controlling', 'zeitbericht': 'controlling'}
check('Eigentümer je Importart wie in der Datenverantwortung', all(arten[k]['eigentuemer'] == v for k, v in EIG.items()), {k: a['eigentuemer'] for k, a in arten.items()})
daten = tomllib.load(open(os.path.join(REPO, 'regeln/datenverantwortung.toml'), 'rb'))
eig_doc = {d['name']: d['eigentuemer'] for d in daten['dokument']}
check('Eigentümer = Eigentümer der importierten Daten', all(eig_doc[d] == EIG[k] for k, d in
      {'kunden': 'kunden', 'kundengruppen': 'kundengruppen', 'vkgruppen': 'vkgruppen', 'vertreter': 'vertreter', 'stammdaten': 'stammdaten', 'bestand': 'bestand', 'preisverlauf': 'historie/*',
       'umsatzdaten': 'controlling-umsatzdaten', 'zeitbericht': 'controlling-arbeitszeit'}.items()))
check('große Dateien nur mit Teilen: Umsatzdaten in Teilen bis 200 MB, alle anderen bis 30 MB ohne Teile', arten['umsatzdaten']['inTeilen'] is True and arten['umsatzdaten']['maxMb'] == 200
      and all(a['inTeilen'] is False and a['maxMb'] == 30 for k, a in arten.items() if k != 'umsatzdaten'), {k: (a['inTeilen'], a['maxMb']) for k, a in arten.items()})
zentrale = open(os.path.join(REPO, 'app/api/module/verwaltung/importzentrale.php'), encoding='utf-8').read() + open(os.path.join(REPO, 'app/api/aktionen/importzentrale.php'), encoding='utf-8').read()
check('Zentrale liest und schreibt selbst keine Daten (nur über den Eigentümer)', not re.search(r'store_(read|write|delete|names)\(|with_lock\(', zentrale))
check('Zentrale liest keine Dateiformate selbst (Leser beim Eigentümer)', not re.search(r'csvZeilen|parseStockWorkbook|parseOfferWorkbook|xlsxReadWorkbook|TextDecoder', open(os.path.join(REPO, 'app/assets/admin-import.js'), encoding='utf-8').read().split('/* ---------- Darstellung')[1]))
check('Dateitypen und Optionen angegeben', arten['kunden']['dateien'] == ['csv'] and arten['bestand']['dateien'] == ['csv', 'xls', 'xlsx'] and arten['preisverlauf']['mehrere'] is True
      and arten['kunden']['bestaetigung'] is True and [o['id'] for o in arten['bestand']['optionen']] == ['datum'], arten['kunden'])
import datetime, zoneinfo   # noqa: E401
_j = datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Berlin')).isocalendar()
ap = {o['id']: o for o in arten['angebot_preise']['optionen']}
check('Artikelpreise (Auftrag 04.11.2026): in der Zentrale (kein Editor-Ablauf), Angebotswoche = aktuelle KW (Auswahl −4 bis +8), neue Angebote je Kundengruppe einzeln wählbar (Standard: keine)',
      arten['angebot_preise']['ablauf'] == 'zentrale' and list(ap) == ['woche', 'gruppen'] and ap['woche']['typ'] == 'auswahl' and ap['woche']['standard'] == f'{_j[0]:04d}-{_j[1]:02d}'
      and len(ap['woche']['werte']) == 13 and ap['woche']['werte'][4]['wert'] == ap['woche']['standard'] and '(aktuelle Woche)' in ap['woche']['werte'][4]['text']
      and ap['gruppen']['typ'] == 'liste' and ap['gruppen']['standard'] == [] and not any(a['ablauf'] == 'editor' for a in arten.values()), arten['angebot_preise'])
_erg = zentrale.split('function import_ergebnis')[1].split('\nfunction ')[0]
check('Zentrale wertet „details“ nicht aus (nur in import_ergebnis begrenzt durchgereicht)', zentrale.count("'details'") == _erg.count("'details'") > 0 and 'IMPORT_DETAILS_MAX' in _erg)
check('Kurztext je Importart (eine Zeile in der Liste, höchstens 60 Zeichen), ausführliche Beschreibung bleibt', all(0 < len(a['kurz']) <= 60 and len(a['beschreibung']) > len(a['kurz']) for a in arten.values())
      and arten['bestand']['kurz'] == 'Bestandsliste aus WinAB – ersetzt den Bestand', {k: a['kurz'] for k, a in arten.items()})
check('keine internen Funktionsnamen an den Browser', 'vorschau' not in json.dumps(r) and 'uebernahme' not in json.dumps(r))

# ---------- Rechte: Anzeige und Prüfung je Importart (GR-103) ----------
check('ohne Anmeldung 401', Client().call('import_arten')[0] == 401 and Client().call('import_pruefen', {'art': 'kunden'})[0] == 401)
check('Leser: keine Importart', ids(L) == [])
check('Bearbeiter: alles außer Kunden-, HR- und Controlling-Importen (kein Kunden-/Personal-/Controllingrecht)', ids(E) == [x for x in ALLE if x not in ('kunden', 'zeiterfassung', 'umsatzdaten', 'zeitbericht')], ids(E))
check('Teil: ohne Anmeldung 401, ohne Recht 403, Importart ohne Teile 422', Client().call('import_teil', {'art': 'umsatzdaten'})[0] == 401
      and E.call('import_teil', {'art': 'umsatzdaten', 'upload': 'a' * 32, 'schluessel': '2026-01', 'daten': {}})[0] == 403
      and A.call('import_teil', {'art': 'stammdaten', 'upload': 'a' * 32, 'schluessel': 'x', 'daten': {}})[0] == 422
      and A.call('import_teil', {'art': 'angebot_preise', 'upload': 'a' * 32, 'schluessel': 'x', 'daten': {}})[0] == 422)
check('nur Kundenrecht: nur Kunden', ids(K) == ['kunden'], ids(K))
ROWS = [{'nr': '2000001', 'firma': 'Zentrale Eins GmbH', 'plz': '20095', 'ort': 'Hamburg', 'zeile': 2}]
check('Leser: Kundenimport 403', L.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': ROWS}})[0] == 403)
check('Bearbeiter ohne Kundenrecht: Kundenimport 403 (Vorschau und Übernahme)', E.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': ROWS}})[0] == 403
      and E.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': ROWS}, 'stand': 0})[0] == 403)
check('nur Kundenrecht: Bestand 403', K.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': []}, 'optionen': {'datum': '2026-10-16'}})[0] == 403)
check('Leser: Preisverlauf 403', L.call('import_pruefen', {'art': 'preisverlauf', 'daten': {'wochen': []}})[0] == 403)
check('nur per POST', A.call('import_pruefen')[0] == 405)
check('unbekannte Importart 404', A.call('import_pruefen', {'art': 'gibt_es_nicht'})[0] == 404)
st, r = E.call('import_pruefen', {'art': 'angebot_excel'})
check('Wochenangebot (Excel) gibt es nicht mehr (Auftrag 04.11.2026)', st == 404, r)
check('Artikelpreise: Leser 403', L.call('import_pruefen', {'art': 'angebot_preise', 'daten': {'preise': [{'zeile': 2, 'code': '10601', 'gruppe': '', 'preis': 1.0}]}})[0] == 403)
st, r = A.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': []}})
check('leere Zeilenliste 422', st == 422 and 'Keine Kunden' in r.get('error', ''), r)
check('Übernahme ohne Vorschau-Stand 422', A.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': ROWS}})[0] == 422)

# ---------- Kunden über die Schnittstelle der Zentrale ----------
assert A.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'Gastronomie'}, {'nr': '5', 'name': 'Kantinen'}, {'nr': '7', 'name': 'Handel'}]})[0] == 200
# Option „liste“ (Kennungen; ob sie passen, prüft der Eigentümer) und eigene Darstellung („details“, „fuss“, „knopf“ nur durchgereicht)
_d = A.call('draft')[1]
_code = next(i['code'] for i in ((_d.get('draft') or _d['published'])['items']) if i.get('code'))
_pz = [{'zeile': 2, 'code': str(_code), 'gruppe': '1', 'preis': 23.0}]
_g = lambda opt: A.call('import_pruefen', {'art': 'angebot_preise', 'daten': {'preise': _pz}, 'optionen': opt})[1]
_r0, _r1, _rx = _g({}), _g({'gruppen': ['1', 'a;b', '1', None, {'x': 1}]}), _g({'gruppen': 'kein-array'})
check('Option „liste“: ungültige Einträge und Doppelte verworfen, gewählte Gruppe angelegt; ohne Auswahl keine', _r0['zahlen']['neu'] == 0 and _r1['zahlen']['neu'] == 2
      and _r1['details']['ohne'][0]['an'] is True and _r0['details']['ohne'][0]['an'] is False and _rx['zahlen']['neu'] == 0, (_r0.get('zahlen'), _r1.get('zahlen'), _rx.get('zahlen')))
check('Vorschau mit eigener Darstellung: details, fuss und knopf durchgereicht (übrige Arten ohne)', isinstance(_r1.get('details'), dict) and '1 neues Angebot' in _r1['fuss'] and _r1['knopf'] == '1 Preis übernehmen'
      and _r0['fuss'].startswith('0 Preise') and _r0['knopf'] == 'Übernehmen', (_r1.get('fuss'), _r1.get('knopf'), _r0.get('fuss')))
rev0 = K.call('kunden')[1]['rev']
KR = [{'nr': '3000001', 'firma': 'API Eins GmbH', 'plz': '20095', 'ort': 'Hamburg', 'gruppe': '1', 'zeile': 2},
      {'nr': '3000002', 'firma': 'API Zwei KG', 'gruppe': '99', 'zeile': 3},
      {'nr': '3000001', 'firma': 'Doppelt', 'zeile': 4},
      {'nr': '3000003', 'firma': '', 'zeile': 5},
      {'nr': '3000004', 'firma': 'Gelöscht', 'stern': True, 'zeile': 6}]
st, r = K.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': KR}, 'quelle': 'api.csv'})
zl = {(z['art'], z['zeile']) for z in r.get('zeilen', [])}
check('Vorschau Kunden: 2 neu, 2 Fehler, nichts gespeichert', st == 200 and r['zahlen'] == {'neu': 2, 'geaendert': 0, 'entfaellt': 0, 'unveraendert': 0, 'fehler': 2}
      and K.call('kunden')[1]['rev'] == rev0, r.get('zahlen'))
check('Vorschau: Fehler je Zeile mit Zeilennummer', ('fehler', 4) in zl and ('fehler', 5) in zl and ('neu', 2) in zl and ('neu', 3) in zl, zl)
check('Vorschau: Fehler zuerst sortiert', [z['art'] for z in r['zeilen']][:2] == ['fehler', 'fehler'])
check('Vorschau: unbekannte Kundengruppe und *-Kunde als Hinweis', any('99 (1)' in h['text'] for h in r['hinweise']) and any('„*“' in h['text'] for h in r['hinweise']), r['hinweise'])
st2, r2 = K.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': KR}, 'optionen': {'ohneStern': False, 'anlegen': True}})
check('Option „*“-Kunden mitnehmen: 3 neu', st2 == 200 and r2['zahlen']['neu'] == 3, r2.get('zahlen'))
check('Option „nicht anlegen“: 0 neu', K.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': KR}, 'optionen': {'anlegen': False}})[1]['zahlen']['neu'] == 0)
bestaetigung_ablaufen(K)
st3, r3 = K.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': KR}, 'quelle': 'api.csv', 'stand': r['stand']})
check('Übernahme verlangt Passwortbestätigung (wie kunden_import)', st3 == 403 and r3.get('code') == 'confirmation_required', r3)
assert K.call('reauth', {'password': ZUGANG['kai']})[0] == 200
check('veralteter Stand → 409, nichts gespeichert', K.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': KR}, 'stand': r['stand'] - 1})[0] == 409 and K.call('kunden')[1]['rev'] == rev0)
st, r = K.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': KR}, 'quelle': 'api.csv', 'stand': r['stand']})
cs = {c.get('nr'): c for c in doc('kunden')['customers']}
check('Übernahme Kunden: Ergebnis und gespeichert (ohne *-Kunde)', st == 200 and r['zahlen']['neu'] == 2 and cs.get('3000001', {}).get('gruppe') == '1' and '3000002' in cs
      and '3000004' not in cs and cs['3000001'].get('login') is None, r.get('zahlen'))
check('Protokoll: Kundenimport mit Dateiname', 'Kunden aus „api.csv“ importiert: 2 neu' in log_text(A))
check('alte Aktion kunden_import unverändert nutzbar (Vorschau)', A.call('kunden_import', {'pruefen': True, 'rows': [{'nr': '3000001', 'firma': 'API Eins GmbH'}]})[1].get('stat', {}).get('unveraendert') == 1)
check('Option Aktiv-Regel registriert (Standard an)', any(o['id'] == 'aktivRegel' and o['standard'] is True and '18 Monaten' in o['label'] for o in arten['kunden']['optionen']), arten['kunden']['optionen'])
ALT = {'rows': [{'nr': '3000009', 'firma': 'Zentrale Alt GmbH', 'wawi': {'letzteRechnung': '2020-01-15', 'kreditlimit': 1000}, 'zeile': 2}], 'wawiFelder': ['letzteRechnung', 'kreditlimit']}
st, r = K.call('import_pruefen', {'art': 'kunden', 'daten': ALT})
check('Zentrale: Aktiv-Regel als Standard, Zeile mit Grund, Hinweis', st == 200 and r['zahlen']['neu'] == 1 and 'inaktiv: keine Rechnung seit 18 Monaten (letzte 15.01.2020)' in r['zeilen'][0]['text']
      and any('Aktiv-Status nach der Warenwirtschaft' in h['text'] for h in r['hinweise']), (r.get('zeilen'), r.get('hinweise')))
st, r = K.call('import_pruefen', {'art': 'kunden', 'daten': ALT, 'optionen': {'aktivRegel': False}})
check('Zentrale: Aktiv-Regel abschaltbar', st == 200 and 'inaktiv' not in r['zeilen'][0]['text'] and not any('Aktiv-Status' in h['text'] for h in r['hinweise']), r.get('zeilen'))

# ---------- Bestand (Eigentümer Bestand) über die Schnittstelle ----------
ART = [{'code': '10601', 'name': 'Roastbeef', 'kg': 120.5, 'mhd': '2026-11-02', 'mhdKg': 20.0, 'lots': [{'lot': 'P1', 'kg': 120.5, 'mhd': '2026-11-02', 'ek': 18.68}]},
       {'code': '10823', 'name': 'Steakhüfte', 'kg': 40.0, 'mhd': None, 'mhdKg': None, 'lots': [{'lot': 'P2', 'kg': 40.0, 'ek': 12.1}]}]
INC = [{'code': '90001', 'name': 'Testkeule', 'kg': 50.0, 'arrival': '2026-10-30', 'lot': 'E1'}]
st, r = E.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': ART, 'incoming': INC}, 'quelle': 'bestand-api.xls'})
check('Bestand: Bestandsdatum ist Pflicht', st == 422 and 'Bestandsdatum' in r.get('error', ''), r)
st, r = E.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': ART, 'incoming': INC}, 'quelle': 'bestand-api.xls', 'optionen': {'datum': '2026-10-16'}})
check('Vorschau Bestand: 2 neu, nichts gespeichert', st == 200 and r['zahlen']['neu'] == 2 and storage_raw('bestand') is None, r.get('zahlen'))
check('Vorschau Bestand: keine Einkaufspreise in der Antwort', '18.68' not in json.dumps(r) and '"ek"' not in json.dumps(r))
st, r = E.call('import_uebernehmen', {'art': 'bestand', 'daten': {'articles': ART, 'incoming': INC}, 'quelle': 'bestand-api.xls', 'optionen': {'datum': '2026-10-16'}, 'stand': r['stand']})
b = doc('bestand')
check('Übernahme Bestand: gespeichert mit Datum, Quelle, Zugängen', st == 200 and b['date'] == '2026-10-16' and b['source'] == 'bestand-api.xls' and len(b['articles']) == 2
      and len(b['incoming']) == 1 and b['importedBy'] == 'Eddi Editor', b.get('source'))
ART2 = [dict(ART[0], kg=99.0, lots=[{'lot': 'P1', 'kg': 99.0, 'mhd': '2026-11-02'}]), {'code': '90009', 'name': 'Neu', 'kg': 5.0, 'mhd': None, 'mhdKg': None, 'lots': []}]
st, r = E.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': ART2}, 'optionen': {'datum': '2026-10-17'}})
z = {x['schluessel']: x for x in r.get('zeilen', [])}
check('zweite Vorschau: 1 neu, 1 geändert (Menge), 1 entfällt', r['zahlen']['neu'] == 1 and r['zahlen']['geaendert'] == 1 and r['zahlen']['entfaellt'] == 1
      and 'Menge: 120,50 kg → 99,00 kg' in z['10601']['text'] and z['10823']['art'] == 'entfaellt', r.get('zahlen'))
E2 = Client('198.51.100.6'); assert E2.call('login', {'username': 'eddi', 'password': ZUGANG['eddi']})[0] == 200
assert E2.call('stock_import', {'date': '2026-10-17', 'source': 'parallel.xls', 'articles': ART2, 'incoming': []})[0] == 200
check('Bestand inzwischen anderswo übernommen → 409', E.call('import_uebernehmen', {'art': 'bestand', 'daten': {'articles': ART2}, 'optionen': {'datum': '2026-10-17'}, 'stand': r['stand']})[0] == 409
      and doc('bestand')['source'] == 'parallel.xls')
check('Protokoll: Bestand übernommen', 'Bestand übernommen: bestand-api.xls – Stand 16.10.2026, 2 Artikel' in log_text(A))

# ---------- Wartung der Oberfläche (GR-107): Importe pausieren, Administratoren arbeiten weiter ----------
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Importzentrale'})
if st == 403 and r.get('code') == 'confirmation_required':
    assert A.call('reauth', {'password': PW})[0] == 200
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Importzentrale'})
check('Wartung der Eingabe gestartet', st == 200, r)
st, r = E.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': ART}, 'optionen': {'datum': '2026-10-16'}})
check('Wartung: Importe für Bearbeiter pausiert (503)', st == 503 and r.get('wartung') is True, (st, r))
check('Wartung: auch die Liste der Importarten', E.call('import_arten')[0] == 503)
check('Wartung: Administrator arbeitet weiter', A.call('import_pruefen', {'art': 'bestand', 'daten': {'articles': ART}, 'optionen': {'datum': '2026-10-16'}})[0] == 200)
assert A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': ''})[0] == 200
check('nach der Wartung wieder verfügbar', E.call('import_arten')[0] == 200)

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Import als erster Punkt unter Verwaltung', a.locator('#vt-importe').is_visible() and y('#side-admin') < y('#vt-importe') < y('#vt-orders'))
    a.click('#vt-importe'); a.wait_for_selector('#view-importe .imp-art[data-art="kunden"]')
    gruppen = a.eval_on_selector_all('#view-importe .imp-gruppe', 'gs => gs.map((g) => [g.querySelector("h2").textContent, [...g.querySelectorAll(".imp-art")].map((x) => x.dataset.art)])')
    check('Liste: alle Importarten, nach Bereich gruppiert', a.locator('#view-importe .imp-art').count() == len(ALLE) and [g for g, _ in gruppen] == ['Stammdaten', 'Angebot und Bestand', 'Personal', 'Controlling']
          and dict(gruppen)['Stammdaten'] == ['kunden', 'kundengruppen', 'vertreter', 'stammdaten', 'vkgruppen'] and 'bestand' in dict(gruppen)['Angebot und Bestand'], gruppen)
    zb = a.inner_text('#view-importe .imp-art[data-art="bestand"]')
    check('Zeile: Name, Kurztext (ganze Beschreibung im Hinweis), Dateiart, Knopf', 'Bestandsliste aus WinAB' in zb and a.text_content('.imp-art[data-art="bestand"] .imp-format') == 'CSV / Excel'
          and a.text_content('.imp-art[data-art="kunden"] .imp-format') == 'CSV' and 'WinAB' in (a.get_attribute('.imp-art[data-art="bestand"] p', 'title') or '')
          and a.locator('.imp-art[data-art="kunden"] .imp-schloss').count() == 1 and a.locator('.imp-art[data-art="bestand"] .imp-schloss').count() == 0
          and a.locator('[data-imp-waehlen="preisverlauf"]').inner_text() == 'Dateien wählen' and a.locator('[data-imp-editor]').count() == 0
          and a.locator('[data-imp-waehlen="angebot_preise"]').inner_text() == 'Datei wählen', zb)
    check('eine Zeile je Import (Desktop)', a.evaluate("[...document.querySelectorAll('#view-importe .imp-art')].every((z) => z.getBoundingClientRect().height < 70)"))
    check('Hinweis unten: nur das Schloss erklärt, kein Fenster offen', 'Übernahme mit Passwortbestätigung' in a.inner_text('.imp-hinweis') and a.locator('.imp-fenster').count() == 0)
    a.screenshot(path=SH + '/importzentrale-liste.png', full_page=True)

    # ---------- Ablagefenster je Import und Drag & Drop ----------
    def ziehen(sel, pfade, arten_=('dragenter', 'dragover', 'drop')):
        dateien = [[os.path.basename(x), base64.b64encode(open(x, 'rb').read()).decode()] for x in pfade]
        return a.evaluate('''([sel, dateien, arten]) => {
          const dt = new DataTransfer();
          for (const [name, b64] of dateien) dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], name));
          const el = document.querySelector(sel); let verhindert = null;
          for (const t of arten) { const ev = new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt }); el.dispatchEvent(ev); if (t === 'drop') verhindert = ev.defaultPrevented; }
          return verhindert;
        }''', [sel, dateien, list(arten_)])
    a.click('[data-imp-waehlen="kundengruppen"]'); a.wait_for_selector('.imp-art[data-art="kundengruppen"] .imp-fenster')
    fe = a.inner_text('.imp-art[data-art="kundengruppen"] .imp-fenster')
    check('Klick auf „Datei wählen“: Ablagefenster direkt darunter (hineinziehen oder auswählen, Beschreibung, Format)', 'Datei hierher ziehen' in fe and 'Datei auswählen' in fe
          and 'Liste der Kundengruppen' in fe and 'Semikolon' in fe and a.get_attribute('[data-imp-waehlen="kundengruppen"]', 'aria-expanded') == 'true'
          and 'Schließen' in a.inner_text('[data-imp-waehlen="kundengruppen"]')
          and a.evaluate("document.activeElement && document.activeElement.dataset.impAuswahl === 'kundengruppen'"), fe)
    check('Fenster liegt direkt unter seiner Zeile', a.evaluate('''() => { const z = document.querySelector('.imp-art[data-art="kundengruppen"] .imp-zeile').getBoundingClientRect();
          const f = document.querySelector('.imp-art[data-art="kundengruppen"] .imp-fenster').getBoundingClientRect(); return f.top >= z.bottom - 1 && f.top - z.bottom < 8; }'''))
    a.screenshot(path=SH + '/importzentrale-fenster.png', full_page=True)
    a.click('.imp-art[data-art="vertreter"] .imp-text'); a.wait_for_selector('.imp-art[data-art="vertreter"] .imp-fenster')
    check('Klick auf eine andere Zeile: deren Fenster auf, das bisherige zu (immer nur eines)', a.locator('.imp-fenster').count() == 1
          and a.get_attribute('[data-imp-waehlen="kundengruppen"]', 'aria-expanded') == 'false')
    a.keyboard.press('Escape'); a.wait_for_selector('.imp-fenster', state='detached')
    check('Escape schließt das Fenster, Fokus zurück auf den Knopf', a.evaluate("document.activeElement && document.activeElement.dataset.impWaehlen === 'vertreter'"))
    a.click('[data-imp-waehlen="kundengruppen"]'); a.wait_for_selector('.imp-art[data-art="kundengruppen"] .imp-fenster')
    a.click('[data-imp-waehlen="kundengruppen"]'); a.wait_for_selector('.imp-fenster', state='detached')
    check('Knopf „Schließen“ klappt wieder zu', a.get_attribute('[data-imp-waehlen="kundengruppen"]', 'aria-expanded') == 'false')
    a.click('[data-imp-waehlen="kundengruppen"]'); a.wait_for_selector('[data-imp-auswahl="kundengruppen"]')
    with a.expect_file_chooser() as fc:
        a.click('[data-imp-auswahl="kundengruppen"]')
    fc.value.set_files(GRUPPEN_CSV); a.wait_for_selector('#imp-neu')
    check('„Datei auswählen“ im Fenster: Vorschau dieses Imports', 'Kundengruppen importieren' in a.inner_text('#imp-titel'))
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kundengruppen"]')
    check('zurück zur Liste: kein Fenster mehr offen', a.locator('.imp-fenster').count() == 0)
    a.click('[data-imp-waehlen="vkgruppen"]'); a.wait_for_selector('.imp-art[data-art="vkgruppen"] .imp-fenster')
    ziehen('.imp-art[data-art="vkgruppen"] .imp-ablage', [VK_CSV], ('dragenter', 'dragover'))
    check('Ziehen über das Fenster: Ziel markiert', a.locator('.imp-art[data-art="vkgruppen"].imp-ueber').count() == 1 and a.locator('.imp-ueber').count() == 1)
    a.evaluate("document.querySelector('#view-importe').dispatchEvent(new DragEvent('dragleave', { bubbles: true, relatedTarget: null }))")
    check('… beim Verlassen zurückgesetzt', a.locator('.imp-ueber').count() == 0)
    ziehen('.imp-art[data-art="vkgruppen"] .imp-ablage', [VK_CSV]); a.wait_for_selector('#imp-neu')
    check('Datei ins Fenster gezogen: Vorschau dieses Imports', 'VK-Gruppen importieren' in a.inner_text('#imp-titel') and 'vkgruppen.csv' in a.inner_text('#view-importe .imp-kopf'))
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kundengruppen"]')
    ziehen('.imp-art[data-art="kundengruppen"] .imp-text', [GRUPPEN_CSV]); a.wait_for_selector('#imp-neu')
    check('Datei direkt auf eine geschlossene Zeile gezogen: dieser Import', 'Kundengruppen importieren' in a.inner_text('#imp-titel'))
    ziehen('#view-importe', [ARTIKEL_CSV]); a.wait_for_function("document.querySelector('#view-importe .imp-kopf') && document.querySelector('#view-importe .imp-kopf').textContent.includes('artikelstammdaten.csv')")
    a.wait_for_selector('#imp-neu, #imp-fehler')
    check('Datei auf die Vorschau gezogen: ersetzt die Datei desselben Imports', 'Kundengruppen importieren' in a.inner_text('#imp-titel'))
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kunden"]')
    ziehen('.imp-art[data-art="kunden"]', [BESTAND_XLS]); a.wait_for_selector('#imp-fehler')
    check('falsche Datei auf einen Import: Hinweis im Ablauf, nichts übernommen', 'Falsche Datei' in a.inner_text('#imp-fehler'))
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kunden"]')
    ziehen('.imp-liste', [GRUPPEN_CSV]); a.wait_for_function("document.querySelector('#toast').textContent.includes('auf einen Import ziehen')")
    check('Datei zwischen die Gruppen (kein Fenster offen): Hinweis, kein Import gestartet', a.locator('#imp-titel').count() == 0)
    a.click('[data-imp-waehlen="vertreter"]'); a.wait_for_selector('.imp-art[data-art="vertreter"] .imp-fenster')
    ziehen('.imp-hinweis', [FIX + '/kunden/vertreter.csv']); a.wait_for_selector('#imp-titel')
    check('Datei neben die Zeilen, Fenster offen: geht in den offenen Import', 'Vertreter importieren' in a.inner_text('#imp-titel'))
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kunden"]')
    ziehen('.imp-art[data-art="bestand"]', [BESTAND_CSV]); a.wait_for_selector('#imp-neu')
    tb = a.inner_text('#view-importe')
    check('Bestand als CSV (Ablage auf „Bestand“): Vorschau, Bestandsdatum = Tag des Hochladens (heute)', 'Bestand importieren' in a.inner_text('#imp-titel')
          and 'Tag des Hochladens' in tb and a.input_value('[data-imp-opt="datum"]') == __import__('datetime').date.today().isoformat() and 'verkauft' in tb, tb[:500])
    a.click('[data-imp="liste"]'); a.wait_for_selector('.imp-art[data-art="kunden"]')
    check('neben die Liste fallen gelassen: Browser öffnet die Datei nicht', ziehen('#side-admin', [GRUPPEN_CSV]) is True and a.locator('#imp-titel').count() == 0)

    def datei(art, pfad):
        a.set_input_files(f'#view-importe input[data-imp-datei="{art}"]', pfad)

    def fehler_text():
        a.wait_for_selector('#imp-fehler')
        return a.inner_text('#imp-fehler')

    # Fehlerfälle: falsche Datei, falsche Kodierung, leere Datei
    datei('kunden', BESTAND_XLS)
    t = fehler_text()
    check('falsche Datei (Excel statt CSV) erkannt', 'Falsche Datei' in t and 'erwartet wird CSV' in t, t)
    a.click('[data-imp="liste"]'); datei('kunden', ARTIKEL_CSV)
    t = fehler_text()
    check('falsche Datei (Artikelexport statt Kundenexport) vom Leser des Eigentümers erkannt', 'Spalten „Nummer“ und „Name1“ nicht gefunden' in t, t)
    a.click('[data-imp="liste"]'); datei('kunden', UTF16_CSV)
    t = fehler_text()
    check('falsche Kodierung (UTF-16) erkannt', 'Falsche Kodierung' in t and 'UTF-16' in t, t)
    a.click('[data-imp="liste"]'); datei('kunden', LEER_CSV)
    check('leere Datei erkannt', 'ist leer' in fehler_text())
    a.click('[data-imp="liste"]'); datei('vkgruppen', NUR_KOPF_CSV)
    check('Datei nur mit Leerzeilen gilt als leer', 'leer' in fehler_text())
    a.click('[data-imp="liste"]'); datei('bestand', KUNDEN_CSV)
    check('andere CSV statt Bestandsliste erkannt (keine Partien mit Status „eingelagert“)', 'Keine Bestandszeilen' in fehler_text())
    check('Fehlerfälle: nichts übernommen', doc('vkgruppen') is None and doc('bestand')['source'] == 'parallel.xls')
    a.screenshot(path=SH + '/importzentrale-fehler.png')

    # Kunden: Vorschau mit Fehlern je Zeile, Option, Übernahme mit Passwortbestätigung
    a.click('[data-imp="liste"]'); datei('kunden', KUNDEN_CSV)
    a.wait_for_selector('#imp-neu')
    t = a.inner_text('#view-importe')
    check('Kunden-Vorschau: 6 neu, 2 Fehler (Doppelte Nummer, ohne Firma)', a.inner_text('#imp-neu') == '6' and a.inner_text('#imp-fehler') == '2' and a.inner_text('#imp-entfaellt') == '0', t[:400])
    check('Kunden-Vorschau: Zeilennummern und Text', a.locator('#imp-zeilen tr[data-imp-art="fehler"]').count() == 2 and 'mehrfach' in t and 'Firma fehlt' in t)
    check('HTML aus der Datei wird nicht ausgeführt', a.locator('#imp-zeilen b, #imp-zeilen test').count() == 0 and 'Kantine Süd <Test>' in t)
    check('Kunden-Vorschau: Option Aktiv-Regel gewählt, Hinweise zu Aktiv-Status und Warenwirtschaft', a.locator('[data-imp-opt="aktivRegel"]').is_checked()
          and 'Aktiv-Status nach der Warenwirtschaft' in t and 'Daten der Warenwirtschaft' in t, t[-900:])
    a.click('[data-imp-filter="fehler"]'); a.wait_for_function("document.querySelectorAll('#imp-zeilen tr[data-imp-art]').length === 2")
    check('Filter: nur Fehler', a.locator('#imp-zeilen tr[data-imp-art="neu"]').count() == 0)
    a.uncheck('[data-imp-opt="ohneStern"]'); a.wait_for_function("document.querySelector('#imp-neu') && document.querySelector('#imp-neu').textContent === '7'")
    check('Option *-Kunden: Vorschau neu geladen (7 neu)', a.inner_text('#imp-neu') == '7')
    a.check('[data-imp-opt="ohneStern"]'); a.wait_for_function("document.querySelector('#imp-neu') && document.querySelector('#imp-neu').textContent === '6'")
    a.screenshot(path=SH + '/importzentrale-vorschau.png', full_page=True)
    expire_session(next(c['value'] for c in ctx.cookies() if c['name'] == 'WA_ADMIN'))
    a.click('#imp-ok'); a.wait_for_selector('#dlg-reauth[open]')
    a.fill('#reauth-password', PW); a.click('#reauth-submit')
    a.wait_for_selector('#imp-ergebnis')
    t = a.inner_text('#imp-ergebnis')
    cs = {c.get('nr'): c for c in doc('kunden')['customers']}
    check('Kunden übernommen nach Passwortbestätigung: Ergebnis', 'Import übernommen' in t and '6 neu' in t and 'Protokoll' in t, t)
    check('Kunden gespeichert (ohne *-Kunde, Umlaute)', '1000008' in cs and cs['1000008']['firma'] == 'Bäckerei Größe & Söhne' and '1000005' not in cs, sorted(cs))
    check('Kunden gespeichert mit Daten der Warenwirtschaft (Leser der Verwaltung)', cs['1000001'].get('wawi', {}).get('kreditlimit') == 3000 and cs['1000008'].get('active') is False, cs['1000001'].get('wawi'))
    check('Protokoll: Kundenimport aus kundendaten.csv', 'Kunden aus „kundendaten.csv“ importiert: 6 neu' in log_text(A))
    a.screenshot(path=SH + '/importzentrale-ergebnis.png')
    a.click('[data-imp="ansicht"]'); a.wait_for_selector('#view-kunden:not([hidden]) tr')
    check('Ergebnis führt zur Kundenliste (aktualisiert)', 'Bäckerei Größe' in a.inner_text('#view-kunden'))

    # Kundengruppen: neu / geändert / entfällt
    a.click('#vt-importe'); a.wait_for_selector('#view-importe .imp-art[data-art="kundengruppen"]')
    datei('kundengruppen', GRUPPEN_CSV); a.wait_for_selector('#imp-neu')
    check('Kundengruppen-Vorschau: neu, geändert, entfällt (Gruppe 7 mit Kunden)', a.inner_text('#imp-geaendert') == '2' and a.inner_text('#imp-entfaellt') == '1'
          and 'zugeordnet' in a.inner_text('#imp-zeilen'), a.inner_text('#view-importe')[:500])
    neu_gruppen = int(a.inner_text('#imp-neu'))
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    g = {x['nr']: x for x in doc('kundengruppen')['groups']}
    check('Kundengruppen übernommen (ganze Liste)', '7' not in g and g['1']['name'] == 'Fleisch-Großhandel oh. Kondi.' and len(g) == neu_gruppen + 2, sorted(g))
    check('Protokoll: Kundengruppen aus Datei', 'Kundengruppen aus „kundengruppen.csv“ übernommen' in log_text(A))

    # VK-Gruppen (Grundlage für die Vorschläge der Artikelstammdaten)
    a.click('[data-imp="liste"]'); datei('vkgruppen', VK_CSV); a.wait_for_selector('#imp-neu')
    check('VK-Gruppen-Vorschau: 7 neu', a.inner_text('#imp-neu') == '7' and a.inner_text('#imp-entfaellt') == '0')
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    check('VK-Gruppen übernommen (Windows-1252, Anführungszeichen)', next(x for x in doc('vkgruppen')['groups'] if x['nr'] == '1050')['name'] == 'Färse, HV, 4xD, Marke: "Testmarke"')

    # Artikelstammdaten (Leser in admin.js, Stammdaten der Verwaltung)
    a.click('[data-imp="liste"]'); datei('stammdaten', ARTIKEL_CSV); a.wait_for_selector('#imp-neu')
    t = a.inner_text('#view-importe')
    check('Artikel-Vorschau: 8 neu, 4 fehlerhafte Zeilen mit Nummer', a.inner_text('#imp-neu') == '8' and a.inner_text('#imp-fehler') == '4' and 'wek 19%' in t and 'Bezeichnung fehlt' in t, t[:600])
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    arts = {x['code']: x for x in doc('stammdaten')['articles']}
    check('Artikelstammdaten übernommen mit Vorschlägen (Lamm, NZ, frisch)', arts.get('90001', {}).get('category') == 'Lamm & Schaf' and arts['90001'].get('origin') == 'NZ'
          and arts['90001'].get('vkGruppe') == '3050' and 'wek 19%' not in arts, arts.get('90001'))
    check('Protokoll: Artikelstammdaten importiert', 'Artikelstammdaten aus „artikelstammdaten.csv“ importiert: 8 neu' in log_text(A))
    a.click('[data-imp="liste"]'); datei('stammdaten', ARTIKEL_CSV); a.wait_for_selector('#imp-neu')
    check('erneuter Import: keine Änderungen, Übernehmen gesperrt', a.inner_text('#imp-neu') == '0' and a.inner_text('#imp-geaendert') == '0' and a.locator('#imp-ok').is_disabled())

    # Bestand (anderer Eigentümer, .xls) mit Datum aus der Datei
    a.click('[data-imp="liste"]'); datei('bestand', BESTAND_XLS); a.wait_for_selector('#imp-neu', timeout=20000)
    check('Bestand-Vorschau: Datum aus der Datei, neu/entfällt gegen den gespeicherten Bestand', a.input_value('[data-imp-opt="datum"]') == '2026-10-16'
          and int(a.inner_text('#imp-neu')) > 250 and a.inner_text('#imp-entfaellt') == '1', a.inner_text('#view-importe')[:400])
    check('Bestand-Vorschau: Hinweise des Lesers (Etiketten, erfasst)', 'Etiketten' in a.inner_text('#view-importe') and 'erwartete Zugänge' in a.inner_text('#view-importe'))
    with a.expect_response(lambda r: 'action=import_pruefen' in r.url):
        a.fill('[data-imp-opt="datum"]', '2026-10-15')
    a.wait_for_selector('#imp-ok:not([disabled])')
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    b = doc('bestand')
    check('Bestand übernommen (Quelle, gewähltes Datum, 283 Artikel)', b['source'] == 'bestand.xls' and b['date'] == '2026-10-15' and len(b['articles']) == 283, (b['source'], b['date'], len(b['articles'])))
    vz = (doc('bestand-verlauf') or {}).get('tage', {})
    check('Bestand über die Importzentrale: Tagesstand im Bestandsverlauf (gewähltes Datum)', vz.get('2026-10-15', {}).get('quelle') == 'bestand.xls'
          and vz['2026-10-15']['artikel'] == 283 and len((doc('bestand-verlauf/2026-10-15') or {}).get('artikel', {})) >= 283, vz.get('2026-10-15'))
    a.click('[data-imp="ansicht"]'); a.wait_for_selector('.stab', timeout=10000)
    check('Ergebnis führt zum Bestand (neu geladen)', '15.10.2026' in a.inner_text('#view-stock'))

    # Preisverlauf: mehrere Dateien (Eigentümer Angebot)
    a.click('#vt-importe'); a.wait_for_selector('#view-importe .imp-art[data-art="preisverlauf"]')
    a.set_input_files('#view-importe input[data-imp-datei="preisverlauf"]', KW); a.wait_for_selector('#imp-neu', timeout=20000)
    check('Preisverlauf-Vorschau: zwei Wochen neu', a.inner_text('#imp-neu') == '2' and 'KW 37/2026' in a.inner_text('#imp-zeilen'), a.inner_text('#view-importe')[:300])
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    check('Preisverlauf übernommen', doc('historie/2026-37') is not None and doc('historie/2026-38')['origin'] == 'Import')
    check('Protokoll: Wochen hochgeladen', 'Preisverlauf: KW 37/2026 hochgeladen' in log_text(A))

    # Artikelpreise: Auswahl der Angebotswoche und Schalter in der Vorschau (Ablauf und Übernahme: Gruppe kundenimport)
    a.click('[data-imp="liste"]'); a.wait_for_selector('#view-importe .imp-art[data-art="angebot_preise"]')
    a.set_input_files('#view-importe input[data-imp-datei="angebot_preise"]', FIX + '/angebote/artikelpreise.csv')
    a.wait_for_selector('#view-importe [data-pi] #pi-hoch')
    check('Artikelpreise-Vorschau: Auswahl „Angebotswoche“ (aktuelle KW), eigene Darstellung des Eigentümers, Kundengruppen nicht angehakt',
          a.locator('#view-importe select[data-imp-opt="woche"]').count() == 1 and '(aktuelle Woche)' in a.inner_text('#view-importe [data-imp-opt="woche"] option:checked')
          and a.locator('#view-importe [data-imp-opt="gruppen"]').count() == 0 and a.locator('#view-importe [data-pi-gruppe]').count() >= 1
          and not a.locator('#view-importe [data-pi-gruppe]:checked').count() and a.locator('#imp-zeilen').count() == 0)
    a.click('[data-imp="liste"]')

    # Mobil 390 px
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    m.on('pageerror', lambda e: errors.append(str(e)))
    m.goto(BASE + '/admin/'); m.wait_for_selector('#screen-auth:not([hidden])')
    m.fill('#au-user', 'admin'); m.fill('#pw1', PW); m.click('#auth-submit'); m.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    m.click('#vt-importe'); m.wait_for_selector('#view-importe .imp-art')
    check('390 px: Liste ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390)
    m.click('[data-imp-waehlen="kunden"]'); m.wait_for_selector('.imp-art[data-art="kunden"] .imp-fenster')
    check('390 px: Ablagefenster ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390)
    m.screenshot(path=SH + '/importzentrale-390-fenster.png', full_page=True)
    m.click('[data-imp-waehlen="kunden"]'); m.wait_for_selector('.imp-fenster', state='detached')
    kb = m.locator('[data-imp-waehlen="kunden"]').bounding_box()
    check('390 px: runder Knopf je Import (44 px, Name im Knopftext für Screenreader)', abs(kb['width'] - 44) < 1 and abs(kb['height'] - 44) < 1
          and m.get_attribute('[data-imp-waehlen="kunden"]', 'aria-label') == 'Datei wählen: Kunden', kb)
    m.screenshot(path=SH + '/importzentrale-390-liste.png', full_page=True)
    m.set_input_files('#view-importe input[data-imp-datei="kunden"]', KUNDEN_CSV); m.wait_for_selector('#imp-neu')
    check('390 px: Vorschau ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390, m.evaluate('document.documentElement.scrollWidth'))
    m.screenshot(path=SH + '/importzentrale-390-vorschau.png', full_page=True)
    m.emulate_media(color_scheme='dark'); m.wait_for_function("getComputedStyle(document.body).backgroundColor !== 'rgb(243, 243, 241)'")
    check('dunkel: Kennzeichen „Fehler“ lesbar (eigene Farbe, nicht Hintergrund)', m.evaluate(
        "() => { const b = document.querySelector('.imp-badge.fehler'); const s = b && getComputedStyle(b); return !!s && s.color !== s.backgroundColor; }"))
    m.screenshot(path=SH + '/importzentrale-390-dunkel.png', full_page=True)

    # Anzeige je Recht (Menüpunkt passt zur Liste des Servers)
    def sicht(user):
        pg = br.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', ZUGANG[user]); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.wait_for_function("document.querySelector('#menu-user') && document.querySelector('#menu-user').textContent.length > 0")
        return pg
    lp = sicht('lea')
    check('Leser: kein Menüpunkt Import (keine Importart)', not lp.locator('#vt-importe').is_visible())
    ep = sicht('eddi')
    ep.click('#vt-importe'); ep.wait_for_selector('#view-importe .imp-art')
    check('Bearbeiter: Import sichtbar, ohne Kunden', ep.locator('#view-importe .imp-art').count() == 7 and ep.locator('.imp-art[data-art="kunden"]').count() == 0
          and ep.locator('.imp-art[data-art="angebot_preise"]').count() == 1)
    kp = sicht('kai')
    kp.click('#vt-importe'); kp.wait_for_selector('#view-importe .imp-art')
    check('nur Kundenrecht: Import sichtbar, nur Kunden', kp.locator('#view-importe .imp-art').count() == 1)
    check('keine JavaScript-Fehler', not errors, errors)
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
