"""Importzentrale (Verwaltung → Import, Roadmap 10b): eine Stelle für alle Importe mit einheitlichem Ablauf
(Importart → Datei → Vorschau neu/geändert/entfällt/Fehler je Zeile → Übernahme → Ergebnis und Protokoll).

Geprüft: Registrierung beim Daten-Eigentümer (Verwaltung, Bestand, Angebot), Rechte je Importart serverseitig (403) und
in der Anzeige, Wartung der Oberfläche (503, Administratoren arbeiten weiter), Vorschau und Übernahme für Kunden
(Verwaltung, mit Passwortbestätigung) und Bestand (anderer Eigentümer), Kundengruppen, Artikelstammdaten und Preisverlauf
über die Oberfläche, Fehlerfälle (falsche Datei, falsche Kodierung, leere Datei, veralteter Stand), Protokoll, keine
Einkaufspreise in der Vorschau, Bildschirmfotos Desktop und 390 px. Nur Testdaten aus tests/fixtures."""
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
ALLE = ['angebot_excel', 'angebot_preise', 'bestand', 'kunden', 'kundengruppen', 'preisverlauf', 'stammdaten', 'urlaubsplanung', 'vertreter', 'vkgruppen', 'zeiterfassung']
check('Administrator sieht alle heutigen Importe', st == 200 and sorted(arten) == ALLE, sorted(arten))
EIG = {'kunden': 'verwaltung', 'kundengruppen': 'verwaltung', 'vkgruppen': 'verwaltung', 'vertreter': 'verwaltung', 'stammdaten': 'verwaltung',
       'bestand': 'bestand', 'preisverlauf': 'angebot', 'angebot_excel': 'angebot', 'angebot_preise': 'angebot', 'urlaubsplanung': 'hr', 'zeiterfassung': 'hr'}
check('Eigentümer je Importart wie in der Datenverantwortung', all(arten[k]['eigentuemer'] == v for k, v in EIG.items()), {k: a['eigentuemer'] for k, a in arten.items()})
daten = tomllib.load(open(os.path.join(REPO, 'regeln/datenverantwortung.toml'), 'rb'))
eig_doc = {d['name']: d['eigentuemer'] for d in daten['dokument']}
check('Eigentümer = Eigentümer der importierten Daten', all(eig_doc[d] == EIG[k] for k, d in
      {'kunden': 'kunden', 'kundengruppen': 'kundengruppen', 'vkgruppen': 'vkgruppen', 'vertreter': 'vertreter', 'stammdaten': 'stammdaten', 'bestand': 'bestand', 'preisverlauf': 'historie/*'}.items()))
zentrale = open(os.path.join(REPO, 'app/api/module/verwaltung/importzentrale.php'), encoding='utf-8').read() + open(os.path.join(REPO, 'app/api/aktionen/importzentrale.php'), encoding='utf-8').read()
check('Zentrale liest und schreibt selbst keine Daten (nur über den Eigentümer)', not re.search(r'store_(read|write|delete|names)\(|with_lock\(', zentrale))
check('Zentrale liest keine Dateiformate selbst (Leser beim Eigentümer)', not re.search(r'csvZeilen|parseStockWorkbook|parseOfferWorkbook|xlsxReadWorkbook|TextDecoder', open(os.path.join(REPO, 'app/assets/admin-import.js'), encoding='utf-8').read().split('/* ---------- Darstellung')[1]))
check('Dateitypen und Optionen angegeben', arten['kunden']['dateien'] == ['csv'] and arten['bestand']['dateien'] == ['xls', 'xlsx'] and arten['preisverlauf']['mehrere'] is True
      and arten['kunden']['bestaetigung'] is True and [o['id'] for o in arten['bestand']['optionen']] == ['datum'] and arten['angebot_excel']['ablauf'] == 'editor', arten['kunden'])
check('keine internen Funktionsnamen an den Browser', 'vorschau' not in json.dumps(r) and 'uebernahme' not in json.dumps(r))

# ---------- Rechte: Anzeige und Prüfung je Importart (GR-103) ----------
check('ohne Anmeldung 401', Client().call('import_arten')[0] == 401 and Client().call('import_pruefen', {'art': 'kunden'})[0] == 401)
check('Leser: keine Importart', ids(L) == [])
check('Bearbeiter: alles außer Kunden und HR-Importen (kein Kunden-/Personalrecht)', ids(E) == [x for x in ALLE if x not in ('kunden', 'urlaubsplanung', 'zeiterfassung')], ids(E))
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
check('Angebot (Excel) läuft im Editor, nicht in der Zentrale', st == 422 and 'Angebotseditor' in r.get('error', ''), r)
st, r = A.call('import_pruefen', {'art': 'kunden', 'daten': {'rows': []}})
check('leere Zeilenliste 422', st == 422 and 'Keine Kunden' in r.get('error', ''), r)
check('Übernahme ohne Vorschau-Stand 422', A.call('import_uebernehmen', {'art': 'kunden', 'daten': {'rows': ROWS}})[0] == 422)

# ---------- Kunden über die Schnittstelle der Zentrale ----------
assert A.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '1', 'name': 'Gastronomie'}, {'nr': '5', 'name': 'Kantinen'}, {'nr': '7', 'name': 'Handel'}]})[0] == 200
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
    check('Liste: alle Importarten mit Eigentümer', a.locator('#view-importe .imp-art').count() == len(ALLE) and a.text_content('#view-importe .imp-art[data-art="bestand"] .imp-eig') == 'Bestand')
    a.screenshot(path=SH + '/importzentrale-liste.png', full_page=True)

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
    check('CSV statt Bestandsliste erkannt', 'Falsche Datei' in fehler_text())
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
    a.click('[data-imp="ansicht"]'); a.wait_for_selector('.stab', timeout=10000)
    check('Ergebnis führt zum Bestand (neu geladen)', '15.10.2026' in a.inner_text('#view-stock'))

    # Preisverlauf: mehrere Dateien (Eigentümer Angebot)
    a.click('#vt-importe'); a.wait_for_selector('#view-importe .imp-art[data-art="preisverlauf"]')
    a.set_input_files('#view-importe input[data-imp-datei="preisverlauf"]', KW); a.wait_for_selector('#imp-neu', timeout=20000)
    check('Preisverlauf-Vorschau: zwei Wochen neu', a.inner_text('#imp-neu') == '2' and 'KW 37/2026' in a.inner_text('#imp-zeilen'), a.inner_text('#view-importe')[:300])
    a.click('#imp-ok'); a.wait_for_selector('#imp-ergebnis')
    check('Preisverlauf übernommen', doc('historie/2026-37') is not None and doc('historie/2026-38')['origin'] == 'Import')
    check('Protokoll: Wochen hochgeladen', 'Preisverlauf: KW 37/2026 hochgeladen' in log_text(A))

    # Angebot (Excel) ist aufgeführt und öffnet den Editor
    a.click('[data-imp="liste"]')
    with a.expect_file_chooser() as fc:
        a.click('[data-imp-editor="angebot_excel"]')
    check('Wochenangebot (Excel): öffnet den Editor mit Dateiauswahl', a.locator('#view-edit').is_visible() and fc.value is not None)

    # Mobil 390 px
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    m.on('pageerror', lambda e: errors.append(str(e)))
    m.goto(BASE + '/admin/'); m.wait_for_selector('#screen-auth:not([hidden])')
    m.fill('#au-user', 'admin'); m.fill('#pw1', PW); m.click('#auth-submit'); m.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    m.click('#vt-importe'); m.wait_for_selector('#view-importe .imp-art')
    check('390 px: Liste ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth') <= 390)
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
    check('Bearbeiter: Import sichtbar, ohne Kunden', ep.locator('#view-importe .imp-art').count() == 8 and ep.locator('.imp-art[data-art="kunden"]').count() == 0)
    kp = sicht('kai')
    kp.click('#vt-importe'); kp.wait_for_selector('#view-importe .imp-art')
    check('nur Kundenrecht: Import sichtbar, nur Kunden', kp.locator('#view-importe .imp-art').count() == 1)
    check('keine JavaScript-Fehler', not errors, errors)
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
