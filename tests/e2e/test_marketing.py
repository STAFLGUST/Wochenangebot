"""Marketing · Redaktionsplan (Modul marketing, Oberfläche marketing.intern unter /module/marketing/).

Geprüft: Freigabe (produktiv seit 25.10.2026: jeder Mitarbeiter mit Marketing-Recht, keine Testfreigabe); Rechte marketing.sehen / bearbeiten /
freigeben / verwalten serverseitig (GR-103) inkl. ohne Anmeldung, ohne CSRF, falsche Methode; Beiträge (Pflichtfeld Titel,
Prüfungen und Grenzen, nur mitgeschickte Felder, unbekannte gespeicherte Felder bleiben, gleichzeitiges Bearbeiten → 409);
Ablauf (Freigeben nur mit Recht und mit Termin und Kanal, Veröffentlichen nur freigegeben, inhaltliche Änderung eines
freigegebenen Beitrags durch Bearbeiter → zurück in die Freigabe, Zurückstufen); Kommentare; Kennzahlen; Kampagnen;
Einstellungen (Kennungen bleiben, neue aus dem Namen, Doppelte, entfernte Einträge brechen keine Beiträge); CSV-Export
(BOM, keine Formeln); Löschen; Protokoll; Oberfläche (Übersicht, Idee, Kalender mit Verschieben per Ziehen, Beitrag mit
Zählern, Checklisten-Vorlage, Ablauf, ungespeicherte Änderungen, Board, Liste mit Suche, Kampagnen, Einstellungen,
nur ansehen, hell/dunkel; Desktop und 390 px). Nur synthetische Testdaten.
"""
import datetime as dt
import json
import os
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def dokument(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


HEUTE = dt.date.today()
TAG = lambda n: (HEUTE + dt.timedelta(days=n)).isoformat()   # noqa: E731

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('vera', 'Vera Sehen', 'viewer', 'Leserin-Zugang-1', {'grant': ['marketing.sehen']}),
                          ('bert', 'Bert Bearbeiter', 'editor', 'Bearbeiter-Zugang-1', {'grant': ['marketing.bearbeiten']}),
                          ('frieda', 'Frieda Freigabe', 'editor', 'Freigabe-Zugang-4', {'grant': ['marketing.freigeben']}),
                          ('otto', 'Otto Ohne', 'editor', 'Konto-Passwort-9', {}),
                          ('nora', 'Nora Nichttester', 'editor', 'Merk-Kennwort-31', {'grant': ['marketing.bearbeiten']})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
V = Client('198.51.100.3'); V.call('login', {'username': 'vera', 'password': 'Leserin-Zugang-1'})
Bb = Client('198.51.100.4'); Bb.call('login', {'username': 'bert', 'password': 'Bearbeiter-Zugang-1'})
F = Client('198.51.100.5'); F.call('login', {'username': 'frieda', 'password': 'Freigabe-Zugang-4'})
O = Client('198.51.100.6'); O.call('login', {'username': 'otto', 'password': 'Konto-Passwort-9'})
Nn = Client('198.51.100.7'); Nn.call('login', {'username': 'nora', 'password': 'Merk-Kennwort-31'})
N = Client('198.51.100.8')

# ── Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['marketing']
ob = mod['oberflaechen'][0]
check('Register: Marketing fertig und produktiv (Inhaber 25.10.2026), Adresse marketing.dashboard-stafl.de/module/marketing/', ob['entwicklung'] == 'fertig'
      and ob['freigabe'] == 'produktiv' and ob['zugang'] and ob['adresse'] == 'https://marketing.dashboard-stafl.de/module/marketing/', ob)
check('Kachel verfügbar', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True, mod['kachel'])
st, r = A.call('modul_freigabe_save', {'bereich': 'marketing.intern', 'freigabe': 'test', 'grund': 'Test'})
check('Produktivbereich: keine Testfreigabe über die Modulverwaltung (nur über ein Release)', st == 422, (st, r))
check('jeder Mitarbeiter mit Marketing-Recht: Start ok (nie als Tester eingetragen)', Nn.call('marketing_start')[0] == 200)
check('ohne Anmeldung: 401', N.call('marketing_start')[0] == 401 and N.call('marketing_beitrag_save', {'felder': {'titel': 'x'}})[0] == 401)

# ── Rechte (GR-103) ──
check('Mitarbeiter ohne Marketing-Recht: 403', O.call('marketing_start')[0] == 403 and O.call('marketing_export', {})[0] == 403)
st, d = V.call('marketing_start')
check('marketing.sehen: Start ok, ohne Bearbeiten/Freigeben/Verwalten', st == 200 and d['rechte'] == {'bearbeiten': False, 'freigeben': False, 'verwalten': False}, d.get('rechte'))
for a, b in (('marketing_beitrag_save', {'felder': {'titel': 'Nur ansehen'}}), ('marketing_kommentar', {'id': 'bx', 'text': 'x'}),
             ('marketing_kampagne_save', {'name': 'K'}), ('marketing_einstellungen_save', {}), ('marketing_beitrag_loeschen', {'id': 'bx'})):
    check(f'{a}: nur ansehen → 403', V.call(a, b)[0] == 403)
check('Bearbeiter: Einstellungen und Löschen 403', Bb.call('marketing_einstellungen_save', {})[0] == 403 and Bb.call('marketing_beitrag_loeschen', {'id': 'bx'})[0] == 403)
check('Speichern nur per POST (405)', Bb.call('marketing_beitrag_save')[0] == 405)
csrf = Bb.csrf; Bb.csrf = ''
check('ohne CSRF-Token: 403', Bb.call('marketing_beitrag_save', {'felder': {'titel': 'ohne Token'}})[0] == 403)
Bb.csrf = csrf
st, d = A.call('marketing_start')
check('Administrator: alle Rechte', st == 200 and d['rechte'] == {'bearbeiten': True, 'freigeben': True, 'verwalten': True}, d.get('rechte'))
check('Freigeber: bearbeiten und freigeben, nicht verwalten', F.call('marketing_start')[1]['rechte'] == {'bearbeiten': True, 'freigeben': True, 'verwalten': False})

# ── Grundwerte ──
st, d = Bb.call('marketing_start')
E = d['einstellungen']
kanal = {k['id']: k for k in E['kanaele']}
check('Grundwerte: zwei Marken, Kanäle mit Zeichengrenzen, Formate, Säulen', [m['id'] for m in E['marken']] == ['standard-fleisch', 'fleischmeister']
      and kanal['instagram']['limit'] == 2200 and kanal['instagram']['hashtags'] == 30 and 'reel' in [f['id'] for f in E['formate']] and len(E['saeulen']) == 6, E)
team = {t['id'] for t in d['team']}
check('Verantwortliche: nur Mitarbeiter mit Bearbeitungsrecht (und Zugang)', ids['bert'] in team and ids['frieda'] in team and ids['admin'] in team
      and ids['vera'] not in team and ids['otto'] not in team, d['team'])
check('Status-Liste mit „Freigegeben & geplant“', d['status']['geplant'] == 'Freigegeben & geplant' and list(d['status'])[0] == 'idee', d['status'])
check('noch keine Beiträge, Datum vom Server', d['beitraege'] == [] and d['heute'] == HEUTE.isoformat(), d['heute'])

# ── Beiträge anlegen und prüfen ──
check('ohne Titel: 422', Bb.call('marketing_beitrag_save', {'felder': {'hook': 'nur Hook'}})[0] == 422)
for name, felder in (('unbekannter Kanal', {'kanaele': ['myspace']}), ('Link ohne http(s)', {'links': [{'titel': 'x', 'url': 'javascript:alert(1)'}]}),
                     ('unbekanntes Feld', {'preis': 3}), ('ungültiges Datum', {'veroeffentlichung': '2026-13-01'}), ('ungültige Uhrzeit', {'veroeffentlichung': TAG(3) + 'T25:00'}),
                     ('Verantwortlich ohne Bearbeitungsrecht', {'verantwortlich': ids['vera']}), ('Titel zu lang', {'titel': 'x' * 141}),
                     ('KI-Kennzeichen kein Wahrheitswert', {'ki': 'ja'}), ('zu viele Checklistenpunkte', {'checkliste': [{'text': str(i)} for i in range(41)]})):
    st, r = Bb.call('marketing_beitrag_save', {'felder': {'titel': 'Prüfung', **felder}})
    check(f'Prüfung: {name} → 422', st == 422, (st, r))
st, r = Bb.call('marketing_beitrag_save', {'felder': {'titel': '  Reel: Woran erkennt man gutes Dry Aged?  ', 'marke': 'standard-fleisch', 'kanaele': ['instagram', 'tiktok', 'instagram'],
                                                      'format': 'reel', 'saeule': 'wissen', 'verantwortlich': ids['bert'], 'drehtermin': TAG(1), 'produktionBis': TAG(2),
                                                      'hook': 'Drei Zeichen, an denen Profis gutes Dry Aged erkennen', 'text': 'Kurzer Text.', 'hashtags': '#dryaged #fleisch',
                                                      'checkliste': [{'text': 'Skript', 'erledigt': True}, {'text': ''}, {'text': 'Dreh'}],
                                                      'links': [{'titel': 'Canva', 'url': 'https://www.canva.com/design/beispiel'}], 'ki': False}})
b1 = r.get('beitrag', {})
check('Beitrag angelegt: Titel getrimmt, Kanäle ohne Doppelte, Status Idee, Verlauf „angelegt“, rev 1', st == 200 and b1['titel'] == 'Reel: Woran erkennt man gutes Dry Aged?'
      and b1['kanaele'] == ['instagram', 'tiktok'] and b1['status'] == 'idee' and b1['verlauf'][0]['was'] == 'angelegt' and b1['rev'] == 1
      and b1['erstellt']['von'] == 'Bert Bearbeiter' and b1['verantwortlichName'] == 'Bert Bearbeiter', (st, r))
check('Checkliste: leere Punkte entfallen', b1['checkliste'] == [{'text': 'Skript', 'erledigt': True}, {'text': 'Dreh', 'erledigt': False}], b1.get('checkliste'))
st, r = Bb.call('marketing_beitrag_save', {'felder': {'titel': 'Karussell: 4 Grillfehler'}, 'status': 'planung'})
b2 = r.get('beitrag', {})
check('Beitrag mit Startstatus Planung', st == 200 and b2['status'] == 'planung' and any('Planung' in v['was'] for v in b2['verlauf']), (st, r))

# unbekannte gespeicherte Felder bleiben, nur mitgeschickte Felder ändern sich
doc = dokument('marketing-beitraege')
for e in doc['liste']:
    if e['id'] == b1['id']:
        e['zukunftsfeld'] = {'von': 'späterer Version'}
storage_write('marketing-beitraege', doc)
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'rev': 1, 'felder': {'veroeffentlichung': TAG(3) + 'T18:30'}})
b1 = r.get('beitrag', {})
gesp = [e for e in dokument('marketing-beitraege')['liste'] if e['id'] == b1.get('id')][0]
check('Teiländerung (Termin): übrige Felder und unbekannte Felder bleiben', st == 200 and b1['veroeffentlichung'] == TAG(3) + 'T18:30' and b1['hook'].startswith('Drei Zeichen')
      and b1['kanaele'] == ['instagram', 'tiktok'] and gesp.get('zukunftsfeld') == {'von': 'späterer Version'} and b1['rev'] == 2, (st, r))
check('Verlauf nennt die geänderten Felder', b1['verlauf'][-1]['was'] == 'geändert: veroeffentlichung', b1['verlauf'][-1])
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'rev': 2, 'felder': {'hook': b1['hook'], 'titel': b1['titel']}})
check('unverändert gespeichert: kein neuer Stand', st == 200 and r['beitrag']['rev'] == 2, r.get('beitrag', {}).get('rev'))

# gleichzeitiges Bearbeiten
st, r = F.call('marketing_beitrag_save', {'id': b1['id'], 'rev': 1, 'felder': {'cta': 'Link in der Bio'}})
check('veralteter Stand: 409 mit aktuellem Beitrag, nichts überschrieben', st == 409 and r.get('code') == 'konflikt' and r['beitrag']['rev'] == 2
      and 'Bert Bearbeiter' in r.get('error', '') and r['beitrag']['cta'] == '', (st, r))
check('unbekannter Beitrag: 404', Bb.call('marketing_beitrag_save', {'id': 'bnichtda', 'felder': {'cta': 'x'}})[0] == 404)

# ── Ablauf ──
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'rev': 2, 'felder': {}, 'status': 'geplant'})
check('Bearbeiter darf nicht freigeben (403)', st == 403, (st, r))
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {}, 'status': 'freigabe'})
check('Bearbeiter: „Zur Freigabe“', st == 200 and r['beitrag']['status'] == 'freigabe', (st, r))
check('Bearbeiter: Veröffentlichen ohne Freigabe → 409', Bb.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {}, 'status': 'veroeffentlicht'})[0] == 409)
st, r = F.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {}, 'status': 'geplant'})
check('Freigeben ohne Termin: 422 mit Hinweis', st == 422 and 'Veröffentlichungstermin' in r.get('error', ''), (st, r))
st, r = F.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {'veroeffentlichung': TAG(5)}, 'status': 'geplant'})
check('Freigeben ohne Kanal: 422', st == 422 and 'Kanal' in r.get('error', ''), (st, r))
st, r = F.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {}, 'status': 'geplant'})
b1 = r.get('beitrag', {})
check('Freigeberin gibt frei: Status geplant, Freigabe mit Name (Schnappschuss)', st == 200 and b1['status'] == 'geplant' and b1['freigabe']['von'] == 'Frieda Freigabe', (st, r))
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'rev': b1['rev'], 'felder': {'notizen': 'Szene 1: Reifekammer'}})
check('Bearbeiter ändert Skript (kein Freigabefeld): bleibt freigegeben', st == 200 and r['beitrag']['status'] == 'geplant' and r['beitrag']['freigabe'], r.get('beitrag', {}).get('status'))
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'rev': r['beitrag']['rev'], 'felder': {'text': 'Neuer Text nach der Freigabe.'}})
b1 = r.get('beitrag', {})
check('Bearbeiter ändert Text eines freigegebenen Beitrags → zurück „Zur Freigabe“, Freigabe gelöscht', st == 200 and b1['status'] == 'freigabe' and b1['freigabe'] is None
      and any('Freigabe zurückgenommen' in v['was'] for v in b1['verlauf']), (st, r))
F.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {}, 'status': 'geplant'})
st, r = F.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {'text': 'Freigeberin korrigiert selbst.'}})
check('Freigeberin ändert Text: bleibt freigegeben', st == 200 and r['beitrag']['status'] == 'geplant', r.get('beitrag', {}).get('status'))
st, r = F.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {'veroeffentlichung': ''}})
check('freigegebener Beitrag ohne Termin: 422', st == 422, (st, r))
st, r = Bb.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {'veroeffentlicht': {'instagram': 'https://www.instagram.com/p/beispiel/'},
                                                                     'ergebnisse': {'instagram': {'reichweite': '1200', 'interaktionen': 85, 'aufrufe': None}, 'tiktok': {}}},
                                           'status': 'veroeffentlicht'})
b1 = r.get('beitrag', {})
check('Bearbeiter markiert freigegebenen Beitrag als veröffentlicht, mit Link und Kennzahlen', st == 200 and b1['status'] == 'veroeffentlicht' and b1.get('veroeffentlichtAm')
      and b1['veroeffentlicht'] == {'instagram': 'https://www.instagram.com/p/beispiel/'} and b1['ergebnisse'] == {'instagram': {'reichweite': 1200, 'interaktionen': 85, 'aufrufe': None}}, (st, r))
check('Kennzahl negativ: 422', Bb.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {'ergebnisse': {'instagram': {'reichweite': -5}}}})[0] == 422)
check('Bearbeiter darf Veröffentlichtes nicht zurückstufen (403)', Bb.call('marketing_beitrag_save', {'id': b1['id'], 'felder': {}, 'status': 'produktion'})[0] == 403)
st, r = Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {}, 'status': 'verworfen'})
check('Verwerfen', st == 200 and r['beitrag']['status'] == 'verworfen')
st, r = Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {}, 'status': 'idee'})
check('Wieder aufnehmen', st == 200 and r['beitrag']['status'] == 'idee')
check('unbekannter Status: 422', Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {}, 'status': 'archiv'})[0] == 422)

# ── Kommentare ──
check('leerer Kommentar: 422', Bb.call('marketing_kommentar', {'id': b2['id'], 'text': '  '})[0] == 422)
rev = [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['id'] == b2['id']][0]['rev']
st, r = V.call('marketing_kommentar', {'id': b2['id'], 'text': 'Darf ich nicht'})
st, r = F.call('marketing_kommentar', {'id': b2['id'], 'text': 'Bitte Hook kürzer.'})
check('Kommentar gespeichert (Name, neuer Stand)', st == 200 and r['beitrag']['kommentare'][-1]['von'] == 'Frieda Freigabe' and r['beitrag']['kommentare'][-1]['text'] == 'Bitte Hook kürzer.'
      and r['beitrag']['rev'] == rev + 1, (st, r))
check('Kommentar zu unbekanntem Beitrag: 404', F.call('marketing_kommentar', {'id': 'bnichtda', 'text': 'x'})[0] == 404)

# ── Kampagnen ──
check('Kampagne ohne Name: 422', Bb.call('marketing_kampagne_save', {'name': ' '})[0] == 422)
check('Kampagne Ende vor Beginn: 422', Bb.call('marketing_kampagne_save', {'name': 'Grillsaison', 'von': TAG(10), 'bis': TAG(2)})[0] == 422)
st, r = Bb.call('marketing_kampagne_save', {'name': 'Grillsaison', 'ziel': 'Mehr Grillpakete', 'von': TAG(0), 'bis': TAG(30), 'marke': 'fleischmeister', 'farbe': '#c27a1a'})
k1 = r.get('kampagne', {})
check('Kampagne angelegt', st == 200 and k1['name'] == 'Grillsaison' and k1['farbe'] == '#c27a1a' and k1['archiviert'] is False and len(r['kampagnen']) == 1, (st, r))
check('Kampagne mit ungültiger Farbe: 422', Bb.call('marketing_kampagne_save', {'id': k1['id'], 'name': 'Grillsaison', 'farbe': 'red'})[0] == 422)
st, r = Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {'kampagne': k1['id'], 'kanaele': ['instagram'], 'veroeffentlichung': TAG(5)}})
check('Beitrag einer Kampagne zuordnen', st == 200 and r['beitrag']['kampagne'] == k1['id'], (st, r))
check('unbekannte Kampagne: 422', Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {'kampagne': 'knichtda'}})[0] == 422)
st, r = Bb.call('marketing_kampagne_save', {'id': k1['id'], 'name': 'Grillsaison 2026', 'ziel': 'Mehr Grillpakete', 'von': TAG(0), 'bis': TAG(30), 'marke': 'fleischmeister',
                                            'farbe': '#c27a1a', 'archiviert': False})
check('Kampagne umbenannt (gleiche Kennung)', st == 200 and r['kampagne']['id'] == k1['id'] and r['kampagne']['name'] == 'Grillsaison 2026', (st, r))

# ── Einstellungen ──
E = A.call('marketing_start')[1]['einstellungen']
kan = [dict(k) for k in E['kanaele']]
kan[0]['name'] = 'Instagram (Feed)'
kan.append({'name': 'Pinterest', 'limit': 500, 'hashtags': 20})
kan.append({'name': 'Tik Tok', 'limit': 0})
st, r = A.call('marketing_einstellungen_save', {'kanaele': kan})
neu = {k['name']: k for k in r.get('einstellungen', {}).get('kanaele', [])}
check('Einstellungen: umbenannt mit gleicher Kennung, neue Kennung aus dem Namen, belegte Kennung nicht doppelt', st == 200 and neu['Instagram (Feed)']['id'] == 'instagram'
      and neu['Pinterest']['id'] == 'pinterest' and neu['Pinterest']['limit'] == 500 and neu['Tik Tok']['id'] not in ('tiktok', '') and len(neu) == 9, (st, r))
check('übrige Listen unverändert', r['einstellungen']['marken'] == E['marken'] and r['einstellungen']['formate'] == E['formate'])
check('Einstellungen: doppelte Kennung 422', A.call('marketing_einstellungen_save', {'formate': E['formate'] + [dict(E['formate'][0])]})[0] == 422)
check('Einstellungen: leere Liste 422', A.call('marketing_einstellungen_save', {'saeulen': []})[0] == 422)
check('Einstellungen: Grenze zu hoch 422', A.call('marketing_einstellungen_save', {'kanaele': [{'name': 'X', 'limit': 999999}]})[0] == 422)
st, r = Bb.call('marketing_beitrag_save', {'felder': {'titel': 'Pin: Rezeptkarte Rinderbrühe', 'kanaele': ['pinterest'], 'marke': 'fleischmeister', 'veroeffentlichung': TAG(4)}})
b3 = r.get('beitrag', {})
check('neuer Kanal sofort wählbar', st == 200 and b3['kanaele'] == ['pinterest'], (st, r))
# Marke „fleischmeister“ entfernen: Beitrag bleibt lesbar, Teiländerung anderer Felder geht weiter
st, r = A.call('marketing_einstellungen_save', {'marken': [m for m in E['marken'] if m['id'] != 'fleischmeister']})
check('Marke entfernt', st == 200 and [m['id'] for m in r['einstellungen']['marken']] == ['standard-fleisch'])
st, r = Bb.call('marketing_beitrag_save', {'id': b3['id'], 'felder': {'marke': 'fleischmeister', 'cta': 'Rezept speichern'}})
check('entfernte Marke unverändert mitgeschickt: Speichern anderer Felder geht', st == 200 and r['beitrag']['marke'] == 'fleischmeister' and r['beitrag']['cta'] == 'Rezept speichern', (st, r))
check('entfernte Marke neu wählen: 422', Bb.call('marketing_beitrag_save', {'id': b2['id'], 'felder': {'marke': 'fleischmeister'}})[0] == 422)
A.call('marketing_einstellungen_save', {'marken': E['marken']})

# ── CSV ──
Bb.call('marketing_beitrag_save', {'felder': {'titel': '=HYPERLINK("https://beispiel.example","klick")', 'veroeffentlichung': TAG(6)}})
st, d, raw = V.call('marketing_export', {}, raw=True)
zeilen = raw.lstrip('﻿').strip().split('\n')
check('CSV (auch nur mit Ansehrecht): BOM, Kopf, alle Beiträge', st == 200 and raw.startswith('﻿') and zeilen[0].startswith('"') and ';' in zeilen[0] and len(zeilen) == 1 + 4, (st, zeilen[:2]))
check('CSV: Werte (Titel, Kanalnamen, Kennzahlen)', any('Woran erkennt man gutes Dry Aged' in z and 'Instagram (Feed)' in z and '"1200"' in z for z in zeilen), zeilen)
check('CSV: keine Formeln', any('"\'=HYPERLINK' in z for z in zeilen) and not any(';"=' in z for z in zeilen))
check('CSV nur per POST', V.call('marketing_export')[0] == 405)

# ── Löschen ──
st, r = A.call('marketing_beitrag_loeschen', {'id': b3['id']})
check('Löschen (verwalten)', st == 200 and b3['id'] not in [e['id'] for e in A.call('marketing_start')[1]['beitraege']])
check('erneut löschen: 404', A.call('marketing_beitrag_loeschen', {'id': b3['id']})[0] == 404)

# ── Protokoll und Datenverantwortung ──
log = dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []
mlog = [e for e in log if e.get('a') == 'marketing']
txt = json.dumps(mlog, ensure_ascii=False)
check('Protokoll: Beiträge, Kampagnen, Einstellungen, Export, Löschen', 'Beitrag „Reel: Woran erkennt man gutes Dry Aged?“ gespeichert' in txt and 'Kampagne' in txt
      and 'Einstellungen gespeichert' in txt and 'CSV' in txt and 'gelöscht' in txt, txt[:400])
check('Protokoll ohne Texte, Skripte und Kommentare', 'Szene 1' not in txt and 'Hook kürzer' not in txt and 'Neuer Text' not in txt)
check('eigene Dokumente geschrieben (Beiträge, Kampagnen, Einstellungen)', all(dokument(n) for n in ('marketing-beitraege', 'marketing-kampagnen', 'marketing-einstellungen')))

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1440, thema=None, hoehe=900):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema or 'light')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/marketing/'); pg.wait_for_selector('#mkt-app:not([hidden])')
        return ctx, pg

    ctx, pg = anmelden('bert', 'Bearbeiter-Zugang-1', '198.51.100.4')
    ub = pg.inner_text('#tab-uebersicht')
    check('Übersicht: Kennzahlen, nächste Veröffentlichungen, Kanal-Mix', 'Diese Woche' in ub and 'Zur Freigabe' in ub and 'Nächste Veröffentlichungen' in ub
          and 'Karussell: 4 Grillfehler' in ub and 'Kanäle – nächste 4 Wochen' in ub, ub[:600])
    check('Einstellungen-Reiter für Bearbeiter ausgeblendet', pg.is_hidden('#mkt-tabs [data-tab="einstellungen"]'))
    pg.fill('#idee-titel', 'Story: Frage der Woche an die Community'); pg.click('#idee-form button[type="submit"]')
    pg.wait_for_function("document.querySelector('#mkt-toast').textContent.includes('Idee gespeichert')")
    check('Idee festhalten (Schnelleingabe)', any(e['titel'] == 'Story: Frage der Woche an die Community' and e['status'] == 'idee' for e in Bb.call('marketing_start')[1]['beitraege']))
    pg.screenshot(path=os.path.join(SH, 'marketing_uebersicht_1440.png'), full_page=True)

    pg.click('#mkt-tabs button[data-tab="kalender"]'); pg.wait_for_selector('.mkt-monat')
    chip = pg.locator(f'.mkt-chip[data-oeffnen="{b2["id"]}"]')
    check('Kalender: Beitrag am geplanten Tag', chip.count() == 1 and pg.locator(f'.mkt-tag[data-tag="{TAG(5)}"] .mkt-chip[data-oeffnen="{b2["id"]}"]').count() == 1
          or TAG(5)[:7] != HEUTE.isoformat()[:7], chip.count())
    check('Kalender: „Ohne Termin“ mit der neuen Idee', 'Story: Frage der Woche' in pg.inner_text('.mkt-ohne'))
    pg.screenshot(path=os.path.join(SH, 'marketing_kalender_1440.png'), full_page=True)
    pg.click('.mkt-umschalter button[data-kal="woche"]'); pg.wait_for_selector('.mkt-woche')
    ziel_tag = pg.locator('.mkt-woche .mkt-tag').nth(0).get_attribute('data-tag')
    if ziel_tag < HEUTE.isoformat():
        ziel_tag = pg.locator('.mkt-woche .mkt-tag').nth(6).get_attribute('data-tag')
    idee = pg.locator('.mkt-ohne .mkt-kartei').filter(has_text='Story: Frage der Woche')
    idee.drag_to(pg.locator(f'.mkt-woche .mkt-tag[data-tag="{ziel_tag}"]'))
    pg.wait_for_selector(f'.mkt-woche .mkt-tag[data-tag="{ziel_tag}"] .mkt-chip:has-text("Story: Frage der Woche")')
    ideeneu = [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['titel'].startswith('Story: Frage')][0]
    check('Kalender: Ziehen aus „Ohne Termin“ auf einen Tag setzt den Termin', ideeneu['veroeffentlichung'] == ziel_tag, ideeneu['veroeffentlichung'])
    pg.screenshot(path=os.path.join(SH, 'marketing_woche_1440.png'), full_page=False)

    # Beitrag öffnen und bearbeiten
    pg.click(f'.mkt-chip:has-text("Story: Frage der Woche")'); pg.wait_for_selector('#dlg-beitrag[open]')
    check('Beitrag: Titel und Status im Dialog', pg.input_value('#bt-titel') == 'Story: Frage der Woche an die Community' and 'Idee' in pg.inner_text('#bt-status'))
    pg.click('#bt-kanaele label:has-text("Instagram")')
    pg.fill('#bt-text', 'x' * 2300)
    check('Zeichenzähler je Kanal, Überschreitung markiert', '2.300/2.200' in pg.inner_text('#bt-zaehler') and pg.locator('#bt-zaehler .zuviel').count() == 1, pg.inner_text('#bt-zaehler'))
    pg.fill('#bt-text', 'Welche Grillfrage sollen wir nächste Woche beantworten?')
    pg.click('[data-vorlage="reel"]')
    check('Checklisten-Vorlage Reel', pg.locator('#bt-check li input[type="checkbox"]').count() == 9)
    pg.locator('#bt-check li input[type="checkbox"]').nth(0).check()
    check('Checkliste: Stand', '1 von 9 erledigt' in pg.inner_text('#bt-check-stand'))
    pg.fill('#bt-link-titel', 'Rohmaterial'); pg.fill('#bt-link-url', 'https://drive.google.com/beispiel'); pg.click('#bt-link-add')
    pg.check('#bt-ki')
    check('KI-Hinweis (Kennzeichnungspflicht) erscheint', pg.is_visible('#bt-ki-hinweis') and 'Art. 50' in pg.inner_text('#bt-ki-hinweis'))
    pg.screenshot(path=os.path.join(SH, 'marketing_beitrag_1440.png'), full_page=False)
    pg.click('#bt-speichern'); pg.wait_for_function("document.querySelector('#bt-meldung').textContent.startsWith('Gespeichert')")
    ideeneu = [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['titel'].startswith('Story: Frage')][0]
    check('Beitrag gespeichert (Kanal, Text, Checkliste, Link, KI)', ideeneu['kanaele'] == ['instagram'] and ideeneu['text'].startswith('Welche Grillfrage')
          and len(ideeneu['checkliste']) == 9 and ideeneu['checkliste'][0]['erledigt'] and ideeneu['links'][0]['titel'] == 'Rohmaterial' and ideeneu['ki'] is True, ideeneu)
    pg.click('#bt-schritte button[data-status="planung"]'); pg.wait_for_function("document.querySelector('#bt-status').textContent.includes('Planung')")
    check('Ablauf-Knopf: nächste Stufe', 'Planung' in pg.inner_text('#bt-status') and pg.locator('#bt-schritte button[data-status="produktion"]').count() == 1)
    pg.click('#bt-kommentar'); pg.fill('#bt-kommentar', 'Bitte bis Donnerstag drehen.'); pg.click('#bt-kommentar-add')
    pg.wait_for_selector('#bt-kommentare li:has-text("Bitte bis Donnerstag drehen.")')
    check('Kommentar im Dialog', 'Bert Bearbeiter' in pg.inner_text('#bt-kommentare'))
    pg.fill('#bt-hook', 'Neuer Hook, nicht gespeichert'); pg.click('#dlg-beitrag .mkt-dfuss [data-schliessen]')
    check('ungespeicherte Änderungen: Rückfrage statt Schließen', pg.is_visible('#bt-verwerfen') and pg.locator('#dlg-beitrag[open]').count() == 1)
    pg.click('#bt-verwerfen-ja'); pg.wait_for_selector('#dlg-beitrag', state='hidden')
    check('Verwerfen schließt ohne Speichern', not [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['titel'].startswith('Story: Frage')][0]['hook'])

    # Konflikt im Dialog: jemand anderes speichert dazwischen
    pg.click('.mkt-umschalter button[data-kal="monat"]'); pg.wait_for_selector('.mkt-monat')
    pg.click(f'.mkt-chip:has-text("Story: Frage der Woche")'); pg.wait_for_selector('#dlg-beitrag[open]')
    F.call('marketing_beitrag_save', {'id': ideeneu['id'], 'felder': {'cta': 'Frage in die Kommentare'}})
    pg.fill('#bt-hashtags', '#grillen'); pg.click('#bt-speichern'); pg.wait_for_selector('#bt-konflikt:not([hidden])')
    check('Konflikt: Hinweis mit Namen, nichts überschrieben', 'Frieda Freigabe' in pg.inner_text('#bt-konflikt')
          and [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['id'] == ideeneu['id']][0]['cta'] == 'Frage in die Kommentare')
    pg.click('#bt-neu-laden'); pg.wait_for_selector('#bt-konflikt', state='hidden')
    check('neue Fassung geladen', pg.input_value('#bt-cta') == 'Frage in die Kommentare')
    pg.click('#dlg-beitrag .mkt-dfuss [data-schliessen]'); pg.wait_for_selector('#dlg-beitrag', state='hidden')

    pg.click('#mkt-tabs button[data-tab="board"]'); pg.wait_for_selector('.mkt-board')
    check('Board: Spalten je Status, Verworfene ausgeblendet', pg.locator('.mkt-spalte').count() == 6 and 'Veröffentlicht' in pg.inner_text('.mkt-board'))
    karte = pg.locator(f'.mkt-spalte[data-spalte="planung"] .mkt-kartei[data-oeffnen="{ideeneu["id"]}"]')
    check('Board: Beitrag in „Planung“', karte.count() == 1)
    karte.drag_to(pg.locator('.mkt-spalte[data-spalte="produktion"]'))
    pg.wait_for_selector(f'.mkt-spalte[data-spalte="produktion"] .mkt-kartei[data-oeffnen="{ideeneu["id"]}"]')
    check('Board: Ziehen in „In Produktion“ ändert den Status', [e for e in Bb.call('marketing_start')[1]['beitraege'] if e['id'] == ideeneu['id']][0]['status'] == 'produktion')
    pg.screenshot(path=os.path.join(SH, 'marketing_board_1440.png'), full_page=False)

    pg.click('#mkt-tabs button[data-tab="liste"]'); pg.wait_for_selector('.mkt-tabelle')
    pg.fill('#tab-liste input[data-f="q"]', 'grillfehler')
    pg.wait_for_function("document.querySelectorAll('.mkt-tabelle tbody tr').length === 1")
    check('Liste: Suche, Fokus bleibt im Suchfeld', 'Karussell: 4 Grillfehler' in pg.inner_text('.mkt-tabelle') and pg.evaluate("document.activeElement.dataset.f") == 'q')
    pg.fill('#tab-liste input[data-f="q"]', '')
    pg.select_option('#tab-liste select[data-f="status"]', 'veroeffentlicht')
    pg.wait_for_function("document.querySelectorAll('.mkt-tabelle tbody tr').length === 1")
    check('Liste: Filter Status', 'Dry Aged' in pg.inner_text('.mkt-tabelle'))
    pg.click('[data-filter-leeren]')
    pg.screenshot(path=os.path.join(SH, 'marketing_liste_1440.png'), full_page=False)

    pg.click('#mkt-tabs button[data-tab="kampagnen"]'); pg.wait_for_selector('.mkt-kampagne')
    kt = pg.inner_text('#tab-kampagnen')
    check('Kampagnen: Karte mit Ziel und Fortschritt', 'Grillsaison 2026' in kt and 'Mehr Grillpakete' in kt and '0 von 1 veröffentlicht' in kt, kt[:300])
    pg.click('[data-kampagne-neu]'); pg.fill('#kp-name', 'Weihnachtsbraten'); pg.fill('#kp-von', TAG(20)); pg.fill('#kp-bis', TAG(10)); pg.click('#kp-speichern')
    pg.wait_for_function("document.querySelector('#kp-meldung').textContent.includes('Ende')")
    check('Kampagnen-Dialog: Fehler vom Server sichtbar', 'vor dem Beginn' in pg.inner_text('#kp-meldung'))
    pg.fill('#kp-bis', TAG(40)); pg.click('#kp-speichern'); pg.wait_for_selector('#dlg-kampagne', state='hidden')
    check('Kampagne über die Oberfläche angelegt', 'Weihnachtsbraten' in pg.inner_text('#tab-kampagnen'))
    pg.screenshot(path=os.path.join(SH, 'marketing_kampagnen_1440.png'), full_page=False)
    ctx.close()

    # Administrator: Einstellungen; dunkles Design
    ctx, pg = anmelden('admin', PW, '198.51.100.2', thema='dark')
    pg.click('#mkt-tabs button[data-tab="einstellungen"]'); pg.wait_for_selector('#einst-form')
    check('Einstellungen: vier Listen', pg.locator('[data-liste]').count() == 4 and pg.locator('[data-liste="kanaele"] .mkt-einst-zeile').count() == 9)
    pg.click('[data-zeile-neu="formate"]'); pg.locator('[data-liste="formate"] .mkt-einst-zeile').last.locator('input[data-k="name"]').fill('Podcast')
    pg.click('#einst-speichern'); pg.wait_for_function("document.querySelector('#mkt-toast').textContent.includes('Einstellungen gespeichert')")
    check('Einstellungen über die Oberfläche gespeichert', 'podcast' in [f['id'] for f in A.call('marketing_start')[1]['einstellungen']['formate']])
    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design', bg == 'rgb(18, 16, 17)', bg)
    pg.screenshot(path=os.path.join(SH, 'marketing_einstellungen_dunkel_1440.png'), full_page=False)
    pg.click('#mkt-tabs button[data-tab="uebersicht"]')
    pg.screenshot(path=os.path.join(SH, 'marketing_uebersicht_dunkel_1440.png'), full_page=True)
    ctx.close()

    # nur ansehen
    ctx, pg = anmelden('vera', 'Leserin-Zugang-1', '198.51.100.3')
    check('nur ansehen: kein „+ Beitrag“, keine Idee-Eingabe', pg.is_hidden('#mkt-neu') and pg.locator('#idee-form').count() == 0)
    pg.click('.mkt-zeilen .mkt-titelknopf >> nth=0'); pg.wait_for_selector('#dlg-beitrag[open]')
    check('nur ansehen: Felder gesperrt, kein Speichern', pg.is_disabled('#bt-titel') and pg.is_disabled('#bt-text') and pg.is_hidden('#bt-speichern')
          and pg.locator('#bt-schritte button').count() == 0)
    ctx.close()

    # Handy
    ctx, pg = anmelden('bert', 'Bearbeiter-Zugang-1', '198.51.100.4', breite=390, hoehe=844)
    check('390 px: Übersicht ohne seitliches Scrollen', pg.evaluate("document.documentElement.scrollWidth") <= 390, pg.evaluate("document.documentElement.scrollWidth"))
    pg.screenshot(path=os.path.join(SH, 'marketing_uebersicht_390.png'), full_page=True)
    pg.click('#mkt-tabs button[data-tab="kalender"]'); pg.wait_for_selector('.mkt-agenda')
    check('390 px: Kalender als Tagesliste, ohne seitliches Scrollen', pg.evaluate("document.documentElement.scrollWidth") <= 390)
    pg.screenshot(path=os.path.join(SH, 'marketing_kalender_390.png'), full_page=True)
    pg.click('.mkt-agenda .mkt-chip >> nth=0'); pg.wait_for_selector('#dlg-beitrag[open]')
    check('390 px: Beitrag passt in die Breite', pg.evaluate("document.querySelector('#dlg-beitrag').scrollWidth <= document.querySelector('#dlg-beitrag').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'marketing_beitrag_390.png'), full_page=False)
    pg.click('#dlg-beitrag .mkt-dfuss [data-schliessen]'); pg.wait_for_selector('#dlg-beitrag', state='hidden')
    pg.click('#mkt-tabs button[data-tab="board"]'); pg.wait_for_selector('.mkt-board')
    check('390 px: Board scrollt nur in sich', pg.evaluate("document.documentElement.scrollWidth") <= 390)
    pg.screenshot(path=os.path.join(SH, 'marketing_board_390.png'), full_page=False)
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
