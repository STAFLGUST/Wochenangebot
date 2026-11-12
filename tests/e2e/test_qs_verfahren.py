"""Qualitätssicherung – Verfahrensdokumentation nach GoBD (app/api/module/qs/verfahren.php und verfahren-export.php, Aktionen
qs_verfahren*, Reiter „Verfahrensdoku“ in app/module/qs/verfahren.js).

Geprüft über die Schnittstelle: Rechte (ohne Anmeldung 401, ohne Recht 403 – auch mit „QM ansehen“; ansehen ≠ pflegen ≠
freigeben; Katalog: drei sensible Rechte mit Voraussetzungen; schreibend nur per POST); Anlegen mit Mustergliederung (13
Abschnitte in fünf Teilen, Nummern, Fragen); Abschnitt ändern, anlegen, verschieben, entfernen, „fertig“ nur mit Inhalt,
veralteter Stand 409; IT-Systeme (Pflichtfelder, Datum, Zuordnung, Entfernen räumt Zuordnungen ab); Freigabe (nur wenn alles
fertig, Anlass Pflicht, Erstfassung, Schnappschuss mit Version des verknüpften QM-Dokuments und Namen zu den Kürzeln, nichts
geändert → 422, „ohne Änderung überprüft“ mit Frist 12 Monate); nach der Fassung: Abweichung in Worten, System in Fassung
nicht löschbar (außer Betrieb), neue Version eines QM-Dokuments zählt als Änderung, „gültig ab“ nie vor der vorigen Fassung,
Fassung 1 bleibt unverändert, Dokumentation mit Fassung nicht löschbar; Export: PDF je Fassung (Text der Fassung, nicht der
heutige), Entwurf gekennzeichnet, Export für Prüfungen (Zeitraum, Fassungen im Zeitraum, Änderungshistorie, Fehler 422/404),
ZIP mit der Datei des QM-Dokuments in der damaligen Version, Protokoll.
Oberfläche: Reiter nur mit Recht, Anlegen mit Muster, Abschnitt bearbeiten, IT-System, Freigabe-Dialog, Export-Dialog mit
Download, nur ansehen ohne Knöpfe, 1280/390 px hell und dunkel ohne waagerechtes Scrollen, keine JavaScript-Fehler.
Nur erfundene Testdaten.
"""
import base64
import datetime
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH

HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
HEUTE = datetime.date.today()
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:500]) if i else ''))


def tag(n):
    return (HEUTE + datetime.timedelta(days=n)).isoformat()


def de(iso):
    return f'{iso[8:10]}.{iso[5:7]}.{iso[0:4]}'


def roh(cli, query):
    """GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)"""
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def pdf_text(raw):
    """Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi – je Seite eine Liste von Zeilen"""
    seiten = []
    for m in re.finditer(rb'stream\n(.*?)\nendstream', raw, re.S):
        try:
            s = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        seiten.append([re.sub(rb'\\(.)', rb'\1', t.group(1)).decode('cp1252') for t in re.finditer(rb'\(((?:\\.|[^\\)])*)\) Tj', s)])
    return seiten


def fehlertext(inhalt):
    try:
        return json.loads(inhalt).get('error', '')
    except ValueError:
        return ''


def hochladen(cli, dok, ver, name, inhalt):
    return cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest(),
                                           'upload': '', 'teil': 0, 'daten': base64.b64encode(inhalt).decode()})


# ── Nutzer und Grunddaten ──
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}),
          ('viola', 'Viola Ansehen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.verfahren_sehen']}),
          ('bodo', 'Bodo Buchhaltung', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.verfahren_bearbeiten']}),
          ('gerda', 'Gerda Geschäftsführung', 'editor', 'Freigabe-Konto-78', {'grant': ['qs.verfahren_freigeben']}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, V, O, Vi, Bo, G, N = K['lisa'], K['bernd'], K['quinn'], K['vera'], K['otto'], K['viola'], K['bodo'], K['gerda'], Client('198.51.100.40')
paket = json.load(open(PAKET_DATEI, encoding='utf-8'))
check('Datenpaket (erfunden) übernommen', V.call('qs_import', {'paket': paket, 'ersetzen': True})[0] == 200)

# ── Rechte ──
kat = {p['key']: p for p in A.call('rechte')[1]['catalog']}
check('Katalog: drei eigene Rechte, sensibel (einzeln freizugeben), ohne Standardrollen, mit Erklärung',
      all(kat[k]['stufe'] == 'sensibel' and kat[k]['default'] == [] and kat[k]['modul'] == 'qs' and len(kat[k]['hilfe']) > 60
          for k in ('qs.verfahren_sehen', 'qs.verfahren_bearbeiten', 'qs.verfahren_freigeben')), {k: v for k, v in kat.items() if 'verfahren' in k})
check('Katalog: freigeben setzt pflegen voraus, pflegen ansehen, ansehen das QM-System', kat['qs.verfahren_freigeben']['requires'] == ['qs.verfahren_bearbeiten']
      and kat['qs.verfahren_bearbeiten']['requires'] == ['qs.verfahren_sehen'] and kat['qs.verfahren_sehen']['requires'] == ['qs.sehen'])
check('ohne Anmeldung: 401 (Ansicht und Export)', N.call('qs_verfahren')[0] == 401 and N.call('qs_verfahren_export&doku=x&fassung=0')[0] == 401)
check('ohne QM-Recht: 403', O.call('qs_verfahren')[0] == 403)
check('„QM ansehen“ und „QM freigeben“ genügen nicht: 403 (eigenes Recht)', L.call('qs_verfahren')[0] == 403 and Q.call('qs_verfahren')[0] == 403
      and Q.call('qs_verfahren_save', {'titel': 'X'})[0] == 403 and L.call('qs_verfahren_export&doku=x&fassung=0')[0] == 403)
st, r = Vi.call('qs_verfahren')
check('ansehen: leere Liste, Teile und Auswahllisten, keine Schreibrechte', st == 200 and r['dokus'] == [] and list(r['teile']) == ['allgemein', 'anwender', 'technik', 'betrieb', 'iks']
      and r['rechte'] == {'bearbeiten': False, 'freigeben': False} and r['ueberpruefungMonate'] == 12 and set(r['systemArten']) == {'haupt', 'vor', 'neben', 'archiv'}, r)
check('QM-Start meldet das Recht für den Reiter (nur mit Recht)', Vi.call('qs_start')[1]['rechte']['verfahren'] is True and L.call('qs_start')[1]['rechte']['verfahren'] is False
      and G.call('qs_start')[1]['rechte']['verfahren'] is True)
check('ansehen darf nicht anlegen, pflegen nicht freigeben (403)', Vi.call('qs_verfahren_save', {'titel': 'X'})[0] == 403 and Bo.call('qs_verfahren_freigeben', {'doku': 'x'})[0] == 403)
check('schreibende Aktionen nur per POST (405)', all(Bo.call(a)[0] == 405 for a in ('qs_verfahren_save', 'qs_verfahren_abschnitt_save', 'qs_verfahren_ordnen', 'qs_verfahren_system_save'))
      and G.call('qs_verfahren_freigeben')[0] == 405)

# ── Anlegen mit Mustergliederung ──
check('Anlegen ohne Bezeichnung: 422', Bo.call('qs_verfahren_save', {'titel': ' ', 'muster': True})[0] == 422)
st, r = Bo.call('qs_verfahren_save', {'titel': 'Verfahrensdokumentation Buchführung', 'gesellschaft': 'Muster Fleisch GmbH', 'verantwortlich': 'GF', 'muster': True})
D = r.get('doku', {})
DID = D.get('id', '')
ab = D.get('abschnitte', [])
check('Mustergliederung: 13 Abschnitte in fünf Teilen, nummeriert, mit Frage, noch leer und offen', st == 200 and len(ab) == 13
      and [a['nr'] for a in ab] == ['1.1', '1.2', '2.1', '2.2', '2.3', '2.4', '2.5', '3.1', '3.2', '4.1', '4.2', '5.1', '5.2']
      and all(len(a['hinweis']) > 40 and a['text'] == '' and a['fertig'] is False for a in ab) and ab[2]['titel'] == 'Eingangsrechnungen', [(a['nr'], a['titel']) for a in ab])
check('neu: keine Fassung, keine Abweichung, keine Überprüfungsfrist', D['fassungen'] == [] and D['seitFassung'] is None and D['ueberpruefung'] is None and D['systeme'] == [])
st, r = Bo.call('qs_verfahren_save', {'titel': 'Zweite ohne Muster', 'gesellschaft': 'Muster Handel KG'})
D2 = r['doku']
check('Anlegen ohne Muster: keine Abschnitte', st == 200 and D2['abschnitte'] == [])


def doku(cli=Vi, did=None):
    return {x['id']: x for x in cli.call('qs_verfahren')[1]['dokus']}[did or DID]


def abschnitt(nr):
    return {a['nr']: a for a in doku()['abschnitte']}[nr]


def speichern(cli, a, **neu):
    felder = {k: a[k] for k in ('teil', 'titel', 'text', 'verweise', 'zustaendig', 'systeme', 'fertig')}
    return cli.call('qs_verfahren_abschnitt_save', {'doku': DID, 'id': a['id'], 'rev': a['rev'], **felder, **neu})


# ── IT-Systeme ──
check('IT-System ohne Name: 422', Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': ''})[0] == 422)
check('IT-System: „außer Betrieb“ vor „im Einsatz“ → 422', Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'X', 'seit': '2026-02-01', 'bis': '2026-01-01'})[0] == 422)
check('IT-System: unbekannte Art → 422, ansehen 403', Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'X', 'art': 'geheim'})[0] == 422
      and Vi.call('qs_verfahren_system_save', {'doku': DID, 'name': 'X'})[0] == 403)
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'Warenwirtschaft Beispiel', 'art': 'vor', 'zweck': 'Aufträge, Lieferscheine, Rechnungen', 'anbieter': 'Beispiel Soft 12',
                                              'betrieb': 'lokal', 'ort': 'Server im Haus', 'zustaendig': 'QB', 'sicherung': 'täglich auf ein zweites Gerät', 'seit': '2019-01-01'})
S1 = r['doku']['systeme'][0]
check('IT-System angelegt (noch in keiner Fassung)', st == 200 and S1['name'] == 'Warenwirtschaft Beispiel' and S1['inFassung'] is False and S1['rev'] == 1, r)
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'Altes Archiv', 'art': 'archiv', 'betrieb': 'cloud'})
S2 = r['doku']['systeme'][1]
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'Probe', 'art': 'neben'})
S3 = r['doku']['systeme'][2]
check('IT-System: veralteter Stand → 409', Bo.call('qs_verfahren_system_save', {'doku': DID, 'id': S1['id'], 'rev': 0, 'name': 'Y'})[0] == 409)

# ── Abschnitte ──
a21 = abschnitt('2.1')
check('„fertig“ ohne Inhalt: 422', 'braucht Inhalt' in speichern(Bo, a21, fertig=True)[1].get('error', ''))
check('unbekanntes IT-System am Abschnitt: 422, ansehen 403', speichern(Bo, a21, systeme=['nichtda'])[0] == 422 and speichern(Vi, a21, text='x')[0] == 403)
st, r = speichern(Bo, a21, text='Rechnungen kommen per E-Mail an rechnung@example.invalid.\nPrüfung sachlich durch den Einkauf, Freigabe durch die Geschäftsführung.',
                  verweise='1.3-L02 HACCP-Analyse\nOrdner Buchhaltung\n1.3-L02 HACCP-Analyse', zustaendig='QB', systeme=[S1['id'], S3['id']], fertig=True)
a21n = {a['nr']: a for a in r['doku']['abschnitte']}['2.1']
check('Abschnitt gespeichert: Text, Verweise ohne doppelte, Systeme, fertig, Stand zählt hoch', st == 200 and a21n['fertig'] is True and a21n['verweise'] == ['1.3-L02 HACCP-Analyse', 'Ordner Buchhaltung']
      and a21n['systeme'] == [S1['id'], S3['id']] and a21n['rev'] == a21['rev'] + 1 and a21n['geaendert']['von'] == 'Bodo Buchhaltung', a21n)
check('veralteter Stand: 409 mit Hinweis', speichern(Bo, a21, text='überschreibt')[0] == 409)
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'id': S3['id'], 'rev': S3['rev'], 'loeschen': True})
check('IT-System ohne Fassung entfernt – Zuordnung am Abschnitt mit entfernt', st == 200 and len(r['doku']['systeme']) == 2 and abschnitt('2.1')['systeme'] == [S1['id']], r)
st, r = Bo.call('qs_verfahren_abschnitt_save', {'doku': DID, 'teil': 'anwender', 'titel': 'Reisekosten', 'text': 'Kommt bei uns nicht vor.', 'fertig': True})
neu = r['doku']['abschnitte']
check('neuer Abschnitt steht am Ende seines Teils (2.6)', st == 200 and [a['titel'] for a in neu if a['teil'] == 'anwender'][-1] == 'Reisekosten' and abschnitt('2.6')['titel'] == 'Reisekosten')
rk = abschnitt('2.6')
st, r = Bo.call('qs_verfahren_ordnen', {'doku': DID, 'id': rk['id'], 'richtung': 'auf'})
check('Verschieben nach oben: 2.5, der bisherige wird 2.6', st == 200 and abschnitt('2.5')['titel'] == 'Reisekosten' and abschnitt('2.6')['titel'].startswith('Belegablage'))
erster = abschnitt('2.1')
st, r = Bo.call('qs_verfahren_ordnen', {'doku': DID, 'id': erster['id'], 'richtung': 'auf'})
check('Verschieben am Rand ändert nichts; unbekannte Richtung 422; ansehen 403', st == 200 and abschnitt('2.1')['id'] == erster['id']
      and Bo.call('qs_verfahren_ordnen', {'doku': DID, 'id': erster['id'], 'richtung': 'quer'})[0] == 422 and Vi.call('qs_verfahren_ordnen', {'doku': DID, 'id': erster['id'], 'richtung': 'ab'})[0] == 403)
rk = abschnitt('2.5')
st, r = Bo.call('qs_verfahren_abschnitt_save', {'doku': DID, 'id': rk['id'], 'rev': rk['rev'], 'loeschen': True})
check('Abschnitt entfernt (Arbeitsstand frei änderbar), Nummern rücken nach', st == 200 and len(r['doku']['abschnitte']) == 13 and abschnitt('2.5')['titel'].startswith('Belegablage'))
check('unbekannter Abschnitt bzw. unbekannte Dokumentation: 404', Bo.call('qs_verfahren_abschnitt_save', {'doku': DID, 'id': 'gibtsnicht', 'titel': 'x', 'teil': 'iks'})[0] == 404
      and Bo.call('qs_verfahren_abschnitt_save', {'doku': 'gibtsnicht', 'titel': 'x', 'teil': 'iks'})[0] == 404)

# ── Freigabe ──
st, r = G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': 'Erstfassung'})
check('Freigabe mit offenen Abschnitten: 422 nennt sie', st == 422 and 'Noch nicht fertig (12)' in r['error'] and '1.1 Unternehmen' in r['error'] and 'weitere' in r['error'], r)
for a in doku()['abschnitte']:
    if not a['fertig']:
        assert speichern(Bo, a, text=f'Beschreibung zu {a["titel"]}.', fertig=True)[0] == 200
d = doku()
check('alle Abschnitte fertig', all(a['fertig'] for a in d['abschnitte']))
check('Freigabe ohne Anlass: 422; ungültiges Datum: 422; veralteter Stand: 409', G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': ' '})[0] == 422
      and G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': 'x', 'gueltigAb': '2026-02-30'})[0] == 422 and G.call('qs_verfahren_freigeben', {'doku': DID, 'rev': 1, 'grund': 'x'})[0] == 409)
check('„ohne Änderung überprüft“ vor der ersten Fassung: 422', G.call('qs_verfahren_freigeben', {'doku': DID, 'ohneAenderung': True})[0] == 422)
AB1 = tag(-400)
st, r = G.call('qs_verfahren_freigeben', {'doku': DID, 'rev': d['rev'], 'grund': 'Erstfassung', 'gueltigAb': AB1})
d = r.get('doku', {})
f1 = (d.get('fassungen') or [{}])[0]
check('Fassung 1 freigegeben: Datum heute, gültig ab wie angegeben, Name, Änderung „Erstfassung“', st == 200 and f1['nr'] == 1 and f1['datum'] == HEUTE.isoformat() and f1['gueltigAb'] == AB1
      and f1['gueltigBis'] == '' and f1['von'] == 'Gerda Geschäftsführung' and f1['aenderungen'] == ['Erstfassung'] and 'inhalt' not in f1, r)
check('nach der Freigabe: keine Abweichung, Überprüfung in 12 Monaten, System steht in der Fassung', d['seitFassung']['offen'] is False and d['seitFassung']['zeilen'] == []
      and d['ueberpruefung']['seit'] == HEUTE.isoformat() and d['ueberpruefung']['faellig'] is False and d['ueberpruefung']['faelligAb'][:4] == str(HEUTE.year + 1)
      and all(s['inFassung'] for s in d['systeme']), (d['seitFassung'], d['ueberpruefung']))
st, r = G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': 'noch einmal'})
check('zweite Freigabe ohne Änderung: 422 mit Hinweis auf die Überprüfung', st == 422 and 'nichts geändert' in r['error'] and 'überprüft' in r['error'], r)
check('„ohne Änderung überprüft“: pflegen 403', Bo.call('qs_verfahren_freigeben', {'doku': DID, 'ohneAenderung': True})[0] == 403)
st, r = G.call('qs_verfahren_freigeben', {'doku': DID, 'ohneAenderung': True, 'notiz': 'mit dem Steuerberater durchgesehen'})
check('„ohne Änderung überprüft“ vermerkt (Datum, Name, Bemerkung), keine neue Fassung', st == 200 and len(r['doku']['fassungen']) == 1 and r['doku']['pruefungen'][0]['datum'] == HEUTE.isoformat()
      and r['doku']['pruefungen'][0]['von'] == 'Gerda Geschäftsführung' and r['doku']['pruefungen'][0]['notiz'].startswith('mit dem Steuerberater'), r)

# ── Nach der Fassung: Abweichung, Systeme, QM-Dokument mit neuer Version ──
ALT_TEXT = abschnitt('2.1')['text']
st, r = speichern(Bo, abschnitt('2.1'), text='Rechnungen kommen über das Portal. Freigabe ab 5.000 € durch zwei Personen.')
ab = r['doku']['seitFassung']
check('Änderung nach der Fassung: Abweichung in Worten, Abschnitt markiert', st == 200 and ab['offen'] is True and ab['zeilen'] == ['Geändert: 2.1 Eingangsrechnungen'] and ab['abschnitte'] == [abschnitt('2.1')['id']], ab)
check('„ohne Änderung überprüft“ bei abweichendem Arbeitsstand: 422', 'weicht' in G.call('qs_verfahren_freigeben', {'doku': DID, 'ohneAenderung': True})[1].get('error', ''))
s2 = {s['id']: s for s in doku()['systeme']}[S2['id']]
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'id': s2['id'], 'rev': s2['rev'], 'loeschen': True})
check('IT-System aus einer Fassung nicht löschbar (409, Hinweis „außer Betrieb“)', st == 409 and 'Außer Betrieb' in r['error'], r)
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'id': s2['id'], 'rev': s2['rev'], 'name': s2['name'], 'art': s2['art'], 'betrieb': s2['betrieb'], 'bis': tag(-30)})
check('IT-System außer Betrieb gesetzt → eigene Zeile in der Abweichung', st == 200 and 'IT-System außer Betrieb: Altes Archiv' in r['doku']['seitFassung']['zeilen'], r['doku']['seitFassung'])
st, r = Bo.call('qs_verfahren_system_save', {'doku': DID, 'name': 'Bank-Zugang', 'art': 'neben', 'betrieb': 'cloud'})
st, r = Bo.call('qs_verfahren_abschnitt_save', {'doku': DID, 'teil': 'iks', 'titel': 'Jahresabschluss', 'text': 'Abstimmung mit dem Steuerberater.', 'fertig': True})
kopf = doku()
st, r = Bo.call('qs_verfahren_save', {'id': DID, 'kopfRev': kopf['kopfRev'], 'titel': kopf['titel'], 'gesellschaft': 'Muster Fleisch GmbH & Co. KG', 'verantwortlich': 'GF'})
check('allgemeine Angaben geändert; veralteter Stand 409', st == 200 and r['doku']['gesellschaft'].endswith('Co. KG') and Bo.call('qs_verfahren_save', {'id': DID, 'kopfRev': kopf['kopfRev'], 'titel': 'X'})[0] == 409)
# QM-Dokument 1.3-L02 bekommt Version 3 (Entwurf Bernd, Prüfung und Freigabe Quinn); vorher Datei an Version 2
qd = {x['nr']: x for x in A.call('qs_start')[1]['dokumente']}['1.3-L02']
v2 = [v for v in qd['versionen'] if v['status'] == 'freigegeben'][0]
INHALT_V2 = b'%PDF-1.4\n% HACCP-Analyse Version 2 (erfunden)\n%%EOF'
st, r = hochladen(Q, qd['id'], v2['id'], 'HACCP-Analyse V2.pdf', INHALT_V2)
check('Datei an der gültigen Version 2 des QM-Dokuments abgelegt', st == 200 and r.get('fertig'), r)
assert Be.call('qs_version_save', {'dokument': qd['id'], 'aenderungen': 'Gefahrenliste ergänzt', 'grund': 'Jahresüberprüfung'})[0] == 200
assert Be.call('qs_version_schritt', {'dokument': qd['id'], 'schritt': 'einreichen'})[0] == 200
st, r = Q.call('qs_version_schritt', {'dokument': qd['id'], 'schritt': 'pruefen_freigeben'})
check('QM-Dokument 1.3-L02: Version 3 freigegeben', st == 200 and r['dokument']['zustand'] == 'gueltig', r)
ab = doku()['seitFassung']
check('neue Version des verknüpften QM-Dokuments zählt als Änderung (bisher 2, jetzt 3)', ab['dokumente'] == [{'dok': qd['id'], 'nr': '1.3-L02', 'titel': 'HACCP-Analyse', 'alt': '2', 'neu': '3'}]
      and 'QM-Dokument 1.3-L02 HACCP-Analyse: jetzt Version 3 (bisher Version 2)' in ab['zeilen'], ab)
check('Abweichung nennt alles: Kopf, geändert, neu, Systeme, QM-Dokument', {z.split(':')[0] for z in ab['zeilen']} >= {'Geändert', 'Neu', 'IT-System neu', 'IT-System außer Betrieb', 'QM-Dokument 1.3-L02 HACCP-Analyse'}
      and any(z.startswith('Allgemeine Angaben geändert') for z in ab['zeilen']), ab['zeilen'])
check('Fassung 2: „gültig ab“ vor Fassung 1 → 422', 'liegt vor der Fassung 1' in G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': 'Portal', 'gueltigAb': tag(-401)})[1].get('error', ''))
AB2 = tag(-100)
st, r = G.call('qs_verfahren_freigeben', {'doku': DID, 'grund': 'Rechnungseingang über Portal, neues Bank-System', 'gueltigAb': AB2})
d = r.get('doku', {})
fs = d.get('fassungen', [{}, {}])
check('Fassung 2 freigegeben; Fassung 1 gilt bis zum Vortag; Änderungsliste gespeichert', st == 200 and [f['nr'] for f in fs] == [1, 2] and fs[0]['gueltigBis'] == tag(-101) and fs[1]['gueltigBis'] == ''
      and fs[1]['aenderungen'] == ab['zeilen'] and fs[0]['aenderungen'] == ['Erstfassung'] and d['seitFassung']['offen'] is False, fs)
check('Dokumentation mit Fassung nicht löschbar (409); ohne Fassung löschbar; ansehen 403', Bo.call('qs_verfahren_save', {'id': DID, 'loeschen': True})[0] == 409
      and Vi.call('qs_verfahren_save', {'id': D2['id'], 'loeschen': True})[0] == 403 and Bo.call('qs_verfahren_save', {'id': D2['id'], 'loeschen': True})[1].get('geloescht') is True
      and [x['id'] for x in Vi.call('qs_verfahren')[1]['dokus']] == [DID])

# ── Export: PDF je Fassung, Entwurf, Export für Prüfungen ──
E = 'qs_verfahren_export&doku=' + DID
st, kopfz, raw = roh(Vi, E + '&fassung=1')
t1 = pdf_text(raw)
alles1 = '\n'.join('\n'.join(s) for s in t1)
check('PDF Fassung 1: PDF mit Namen, im Browser anzeigbar', st == 200 and raw[:5] == b'%PDF-' and kopfz['content-type'] == 'application/pdf' and kopfz['content-disposition'].startswith('inline;')
      and 'Fassung-1.pdf' in kopfz['content-disposition'], kopfz)
check('PDF Fassung 1: Deckblatt (Fassung, gültig ab/bis, Verantwortlich mit Name aus dem Schnappschuss, Grundlage GoBD)', 'Verfahrensdokumentation' in t1[0] and 'Fassung 1' in t1[0]
      and f'Gültig ab {de(AB1)} bis {de(tag(-101))}' in t1[0] and any('GF (Geschäftsführung' in z for z in t1[0]) and 'Rz. 151–155' in '\n'.join(t1[0]), t1[0][:14])
check('PDF Fassung 1: Text der Fassung (nicht der heutige), QM-Dokument in Version 2 mit Datum, Unternehmen wie damals',
      ALT_TEXT.split('\n')[0] in alles1 and 'über das Portal' not in alles1 and '1.3-L02 HACCP-Analyse – Version 2 vom 02.03.2023' in alles1
      and 'Muster Fleisch GmbH' in alles1 and 'Co. KG' not in alles1 and 'Jahresabschluss' not in alles1 and 'Bank-Zugang' not in alles1, alles1[:600])
check('PDF Fassung 1: Historie nur bis zu dieser Fassung (Freigabe, Anlass, Änderung „Erstfassung“), Überprüfung ohne Änderung, Seitenzahlen',
      'Fassungen und Änderungen' in alles1 and f'Freigegeben am {de(HEUTE.isoformat())} von Gerda Geschäftsführung · Anlass: Erstfassung' in alles1
      and 'Fassung 2' not in alles1 and 'Geändert: 2.1 Eingangsrechnungen' not in alles1 and 'Ohne Änderung überprüft' in alles1 and 'mit dem Steuerberater durchgesehen' in alles1 and f'Seite 1 von {len(t1)}' in t1[0] and f'Seite {len(t1)} von {len(t1)}' in t1[-1], t1[0])
check('PDF Fassung 1: Teile, IT-Systeme mit Feldern, Zuständiger mit Name, kein Entwurfsvermerk', '2 Anwenderdokumentation' in alles1 and '5 Internes Kontrollsystem' in alles1
      and 'Warenwirtschaft Beispiel · Vorsystem' in alles1 and 'Im Haus – Server im Haus' in alles1 and 'Zuständig: QB (Quinn Beispiel, QMB) · IT-Systeme: Warenwirtschaft Beispiel' in alles1
      and 'ENTWURF' not in alles1 and 'außer Betrieb' not in alles1, '')
st, _, raw = roh(Vi, E + '&fassung=2')
alles2 = '\n'.join('\n'.join(s) for s in pdf_text(raw))
check('PDF Fassung 2: neuer Text, QM-Dokument in Version 3, neues Unternehmen, System außer Betrieb', st == 200 and 'über das Portal' in alles2 and ALT_TEXT.split('\n')[0] not in alles2
      and '1.3-L02 HACCP-Analyse – Version 3 vom ' + de(HEUTE.isoformat()) in alles2 and 'Co. KG' in alles2 and f'Altes Archiv · Archiv / Ablage · außer Betrieb seit {de(tag(-30))}' in alles2
      and 'Jahresabschluss' in alles2, alles2[:500])
assert speichern(Bo, abschnitt('1.1'), text='Noch nicht freigegebener Zusatz im Arbeitsstand.')[0] == 200
st, kopfz, raw = roh(Vi, E + '&fassung=0')
te = pdf_text(raw)
allese = '\n'.join('\n'.join(s) for s in te)
check('PDF Arbeitsstand: auf jeder Seite als Entwurf gekennzeichnet, enthält den neuen Text', st == 200 and all('ENTWURF – nicht freigegeben' in s for s in te)
      and 'Noch nicht freigegebener Zusatz' in allese and '_Entwurf_' in kopfz['content-disposition'], te[0][:8])
check('unbekannte Fassung bzw. Dokumentation: 404', roh(Vi, E + '&fassung=9')[0] == 404 and roh(Vi, 'qs_verfahren_export&doku=gibtsnicht&fassung=1')[0] == 404 and roh(Vi, E + '&fassung=abc')[0] == 404)
for name, q, hinweis in (('ohne Zeitraum', '', 'bitte ein Datum'), ('Bis vor Von', f'&von={tag(-10)}&bis={tag(-20)}', 'endet vor'), ('ungültiges Datum', f'&von=2026-13-01&bis={tag(0)}', 'gültiges Datum'),
                         ('vor der ersten Fassung', f'&von={tag(-900)}&bis={tag(-500)}', 'galt noch keine Fassung')):
    st, _, raw = roh(Vi, E + q)
    check(f'Export für Prüfungen {name}: 422 mit Hinweis', st == 422 and hinweis in fehlertext(raw), (st, raw[:200]))
st, kopfz, raw = roh(Vi, E + f'&von={tag(-300)}&bis={tag(-150)}')
tp = pdf_text(raw)
allesp = '\n'.join('\n'.join(s) for s in tp)
check('Export für Prüfungen (Zeitraum nur Fassung 1): Download, Deckblatt mit Zeitraum, nur Fassung 1 im Volltext – ohne den Arbeitsstand', st == 200 and kopfz['content-disposition'].startswith('attachment;')
      and f'_Pruefung_{tag(-300)}_{tag(-150)}.pdf' in kopfz['content-disposition'] and 'Export für die Prüfung' in tp[0] and f'Prüfungszeitraum {de(tag(-300))} – {de(tag(-150))}' in tp[0]
      and ALT_TEXT.split('\n')[0] in allesp and 'über das Portal' not in allesp and 'Noch nicht freigegebener Zusatz' not in allesp and 'ENTWURF' not in allesp, tp[0][:10])
check('Export für Prüfungen: Übersicht nennt alle Fassungen mit ihren Änderungen, markiert die im Zeitraum', 'Geändert: 2.1 Eingangsrechnungen' in allesp
      and 'QM-Dokument 1.3-L02 HACCP-Analyse: jetzt Version 3 (bisher Version 2)' in allesp and any(z.startswith('Fassung 1') and z.endswith('im Prüfungszeitraum') for z in tp[0])
      and any(z.startswith('Fassung 2') and 'im Prüfungszeitraum' not in z for s in tp for z in s if z.startswith('Fassung 2 ·')), [z for z in tp[0] if z.startswith('Fassung')])
st, _, raw = roh(Vi, E + f'&von={tag(-300)}&bis={tag(0)}')
allesb = '\n'.join('\n'.join(s) for s in pdf_text(raw))
check('Export für Prüfungen (Zeitraum über beide Fassungen): beide im Volltext', st == 200 and ALT_TEXT.split('\n')[0] in allesb and 'über das Portal' in allesb
      and allesb.count('im Prüfungszeitraum') == 2, '')
st, kopfz, raw = roh(Vi, E + f'&von={tag(-300)}&bis={tag(0)}&dokumente=1')
z = zipfile.ZipFile(io.BytesIO(raw)) if st == 200 else None
namen = z.namelist() if z else []
check('Export als ZIP: PDF und die Datei des QM-Dokuments in der Version der Fassung 1 (Version 2), unverändert', st == 200 and kopfz['content-type'] == 'application/zip'
      and any(n.endswith('/Verfahrensdokumentation.pdf') for n in namen) and any(n.endswith('/QM-Dokumente/1.3-L02 HACCP-Analyse/Version 2/HACCP-Analyse V2.pdf') for n in namen)
      and z.read([n for n in namen if n.endswith('HACCP-Analyse V2.pdf')][0]) == INHALT_V2 and z.read([n for n in namen if n.endswith('Verfahrensdokumentation.pdf')][0])[:5] == b'%PDF-', namen)
check('Export nur mit Recht: „QM ansehen“ 403', roh(L, E + '&fassung=1')[0] == 403 and roh(L, E + f'&von={tag(-300)}&bis={tag(0)}')[0] == 403)
st, r = Bo.call('qs_verfahren_save', {'titel': 'Ohne Fassung'})
check('Export für Prüfungen ohne freigegebene Fassung: 422', 'noch keine freigegebene Fassung' in fehlertext(roh(Vi, f'qs_verfahren_export&doku={r["doku"]["id"]}&von={tag(-10)}&bis={tag(0)}')[2]))
assert Bo.call('qs_verfahren_save', {'id': r['doku']['id'], 'loeschen': True})[0] == 200
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Anlegen, Abschnitt, IT-System, Freigabe, Überprüfung, Export mit Zeitraum und Fassungen', all(t in log for t in (
      'Verfahrensdokumentation „Verfahrensdokumentation Buchführung“ angelegt (mit Mustergliederung)', 'Abschnitt „Eingangsrechnungen“ geändert', 'IT-System „Warenwirtschaft Beispiel“ angelegt',
      'Fassung 1 freigegeben (gültig ab ' + de(AB1), 'ohne Änderung überprüft (Fassung 1)', 'Export für Prüfungen', '(Fassung 1, 2) als ZIP mit 1 Dateien', 'Fassung 1 als PDF geöffnet')), '')

# ── Oberfläche ──
with sync_playwright() as pw:
    br = pw.chromium.launch()

    def anmelden(user, pw_, ip, breite=1280, thema='light', hoehe=900, ziel='#verfahren'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw_); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/qs/' + ziel); pg.wait_for_selector('#qm-app:not([hidden])')
        return ctx, pg

    # nur „QM ansehen“: kein Reiter
    ctx, pg = anmelden('lisa', 'Leserin-Konto-12', '198.51.100.10')
    check('ohne Recht: Reiter „Verfahrensdoku“ fehlt, Adresse #verfahren zeigt die Übersicht', pg.is_hidden('#qm-tabs [data-tab="verfahren"]') and pg.is_visible('#qm-t-uebersicht') and pg.is_hidden('#qm-t-verfahren'))
    ctx.close()

    # nur ansehen: Inhalt ohne Knöpfe zum Ändern, PDF und Export vorhanden
    ctx, pg = anmelden('viola', 'Leserin-Konto-12', '198.51.100.15')
    pg.wait_for_selector('#vf-teile .vf-abschnitt')
    check('ansehen: Titel, fünf Teile, 14 Abschnitte, Stand als Marken', pg.text_content('#vf-titel') == 'Verfahrensdokumentation Buchführung' and pg.locator('#vf-teile .vf-teil').count() == 5
          and pg.locator('#vf-teile .vf-abschnitt').count() == 14 and f'Fassung 2 · gültig ab {de(AB2)}' in pg.text_content('#vf-status') and 'weicht von Fassung 2 ab' in pg.text_content('#vf-status')
          and 'Geändert: 1.1' in pg.text_content('#vf-offen'), pg.text_content('#vf-status'))
    check('ansehen: keine Knöpfe zum Ändern oder Freigeben', pg.is_hidden('#vf-freigeben') and pg.is_hidden('#vf-kopf-aendern') and pg.is_hidden('#vf-system-neu') and pg.locator('[data-vf-neu]').count() == 0
          and pg.is_visible('#vf-export') and pg.is_visible('#vf-entwurf') and pg.is_hidden('#vf-wahl'))
    pg.locator('.vf-abschnitt', has_text='Eingangsrechnungen').locator('summary').click()
    a = pg.locator('.vf-abschnitt', has_text='Eingangsrechnungen')
    check('ansehen: Abschnitt aufgeklappt – Text, verknüpftes QM-Dokument mit gültiger Version, Zuständig, IT-System; kein „Bearbeiten“', 'über das Portal' in a.text_content()
          and '1.3-L02 HACCP-Analyse · V3' in a.text_content() and 'Warenwirtschaft Beispiel' in a.text_content() and a.locator('[data-vf-abschnitt]').count() == 0, a.text_content()[:300])
    check('Fassungen: zwei, neueste zuerst, mit Änderungen', pg.locator('.vf-fassung').count() == 2 and 'Fassung 2' in pg.locator('.vf-fassung').first.text_content()
          and 'Ohne Änderung überprüft (1)' in pg.text_content('#vf-fassungen'))
    with pg.expect_download() as dl:
        pg.locator('.vf-fassung [data-vf-pdf="1"]').click()
    check('PDF einer Fassung über die Oberfläche geladen', dl.value.suggested_filename.endswith('_Fassung-1.pdf') and open(dl.value.path(), 'rb').read(5) == b'%PDF-', dl.value.suggested_filename)
    pg.click('#vf-export'); pg.wait_for_selector('#dlg-vf-export[open]')
    check('Export-Dialog: Zeitraum vorbelegt (drei Jahre zurück bis heute), nennt die Fassungen im Zeitraum', pg.input_value('#ve-von') == f'{HEUTE.year - 3}-01-01' and pg.input_value('#ve-bis') == HEUTE.isoformat()
          and 'galten die Fassungen 1, 2' in pg.text_content('#ve-enthalten'), pg.text_content('#ve-enthalten'))
    pg.fill('#ve-von', tag(-900)); pg.fill('#ve-bis', tag(-500)); pg.click('#ve-form [type=submit]')
    pg.wait_for_function("() => document.querySelector('#ve-meldung').textContent.includes('galt noch keine Fassung')")
    check('Export-Dialog: Zeitraum ohne Fassung → Hinweis im Dialog, Dialog bleibt offen', pg.is_visible('#dlg-vf-export') and 'galt noch keine Fassung' in pg.text_content('#ve-enthalten'))
    pg.fill('#ve-von', tag(-300)); pg.fill('#ve-bis', tag(0)); pg.check('#ve-dokumente')
    with pg.expect_download() as dl:
        pg.click('#ve-form [type=submit]')
    pg.wait_for_selector('#dlg-vf-export', state='hidden')
    check('Export-Dialog: ZIP heruntergeladen, Dialog geschlossen', dl.value.suggested_filename.endswith('.zip') and zipfile.is_zipfile(dl.value.path()), dl.value.suggested_filename)
    pg.locator('.vf-abschnitt', has_text='Eingangsrechnungen').locator('.qm-verweis[data-dok]').click()
    pg.wait_for_selector('#qm-t-dokumente:not([hidden])')
    check('Klick auf das verknüpfte QM-Dokument öffnet es im Reiter „Dokumente“', '1.3-L02' in pg.text_content('#qm-dk'))
    ctx.close()

    # pflegen: zweite Dokumentation anlegen, Abschnitt bearbeiten, IT-System – freigeben darf er nicht
    ctx, pg = anmelden('bodo', 'Bearbeit-Konto-34', '198.51.100.16')
    pg.wait_for_selector('#vf-teile .vf-abschnitt')
    check('pflegen: Knöpfe zum Ändern, aber kein „Freigeben“', pg.is_visible('#vf-kopf-aendern') and pg.is_visible('#vf-system-neu') and pg.locator('[data-vf-neu]').count() == 5 and pg.is_hidden('#vf-freigeben'))
    pg.select_option('#vf-wahl', '+'); pg.wait_for_selector('#dlg-vf-kopf[open]')
    pg.fill('#vk-titel-in', ''); pg.click('#vk-form [type=submit]')
    pg.wait_for_function("() => document.querySelector('#vk-meldung').textContent.includes('Bezeichnung')")
    pg.fill('#vk-titel-in', 'Verfahrensdokumentation Handel'); pg.fill('#vk-gesellschaft', 'Muster Handel KG'); pg.click('#vk-form [type=submit]')
    pg.wait_for_selector('#dlg-vf-kopf', state='hidden')
    pg.wait_for_function("() => document.querySelector('#vf-titel').textContent === 'Verfahrensdokumentation Handel'")
    check('Oberfläche: zweite Dokumentation mit Mustergliederung angelegt und gewählt; Export erst nach der ersten Fassung', pg.locator('#vf-teile .vf-abschnitt').count() == 13
          and 'Noch keine Fassung freigegeben' in pg.text_content('#vf-status') and '0 von 13 Abschnitten fertig' in pg.text_content('#vf-status') and pg.is_disabled('#vf-export')
          and pg.locator('#vf-wahl option').count() == 3)
    erster = pg.locator('.vf-abschnitt').first
    erster.locator('summary').click()
    check('offener Abschnitt zeigt die Frage aus dem Muster', 'Zu beschreiben:' in erster.text_content() and 'Rechtsform' in erster.text_content())
    erster.locator('[data-vf-abschnitt]').click(); pg.wait_for_selector('#dlg-vf-abschnitt[open]')
    check('Abschnitt-Dialog: Frage, Auswahl der QM-Dokumente, IT-Systeme ausgeblendet (noch keine)', 'Rechtsform' in pg.text_content('#va-hinweis') and pg.locator('#va-dok option').count() > 3 and pg.is_hidden('#va-systeme-z'))
    pg.check('#va-fertig'); pg.click('#va-form [type=submit]')
    pg.wait_for_function("() => document.querySelector('#va-meldung').textContent.includes('braucht Inhalt')")
    pg.fill('#va-text', 'Großhandel mit Lebensmitteln, Buchführung im Haus.')
    pg.select_option('#va-dok', index=2)
    verweis = pg.input_value('#va-verweise')
    pg.click('#va-form [type=submit]'); pg.wait_for_selector('#dlg-vf-abschnitt', state='hidden')
    pg.wait_for_function("() => document.querySelector('#vf-status').textContent.includes('1 von 13 Abschnitten fertig')")
    erster = pg.locator('.vf-abschnitt').first
    check('Abschnitt gespeichert: bleibt aufgeklappt, Text und QM-Dokument sichtbar, als fertig markiert', erster.get_attribute('open') is not None and 'Großhandel mit Lebensmitteln' in erster.text_content()
          and verweis.split(' ')[0] in erster.text_content() and erster.locator('.vf-stand.fertig').count() == 1 and verweis != '', (verweis, erster.text_content()[:200]))
    pg.click('#vf-system-neu'); pg.wait_for_selector('#dlg-vf-system[open]')
    pg.fill('#vs-name', 'Buchhaltung Beispiel'); pg.select_option('#vs-art', 'haupt'); pg.fill('#vs-zweck', 'Finanzbuchhaltung'); pg.click('#vs-form [type=submit]')
    pg.wait_for_selector('#dlg-vf-system', state='hidden')
    pg.wait_for_selector('.vf-system')
    check('IT-System angelegt und in der Liste', 'Buchhaltung Beispiel' in pg.text_content('#vf-systeme') and 'Hauptsystem' in pg.text_content('#vf-systeme'))
    zweiter = pg.locator('.vf-abschnitt').nth(1)
    zweiter.locator('summary').click(); zweiter.locator('[data-vf-schieben="auf"]').click()
    pg.wait_for_function("() => document.querySelector('.vf-abschnitt .vf-name').textContent.startsWith('Belegfluss')")
    check('„Nach oben“ tauscht die Abschnitte, Nummern folgen', pg.locator('.vf-abschnitt .vf-nr').first.text_content() == '1.1' and pg.locator('.vf-abschnitt').first.locator('[data-vf-schieben="auf"]').is_disabled())
    pg.screenshot(path=os.path.join(SH, 'qs_verfahren_pflegen_1280.png'), full_page=True)
    ctx.close()

    # freigeben: Dialog nennt offene Abschnitte; in der ersten Dokumentation Fassung 3 freigeben, danach „Überprüft vermerken“
    ctx, pg = anmelden('gerda', 'Freigabe-Konto-78', '198.51.100.17')
    pg.wait_for_selector('#vf-teile .vf-abschnitt')
    pg.select_option('#vf-wahl', label='Muster Handel KG')
    pg.wait_for_function("() => document.querySelector('#vf-titel').textContent === 'Verfahrensdokumentation Handel'")
    pg.click('#vf-freigeben'); pg.wait_for_selector('#dlg-vf-freigabe[open]')
    check('Freigabe-Dialog mit offenen Abschnitten: nennt sie, Knopf gesperrt', 'Noch nicht fertig' in pg.text_content('#vg-text') and pg.is_disabled('#vg-ok') and pg.text_content('#vg-titel') == 'Fassung 1 freigeben')
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-vf-freigabe', state='hidden')
    pg.select_option('#vf-wahl', label='Muster Fleisch GmbH & Co. KG')
    pg.wait_for_function("() => document.querySelector('#vf-freigeben-text').textContent === 'Fassung 3 freigeben'")
    pg.click('#vf-freigeben'); pg.wait_for_selector('#dlg-vf-freigabe[open]')
    check('Freigabe-Dialog: nennt die Änderungen seit Fassung 2, „gültig ab“ heute', 'Geändert: 1.1' in pg.text_content('#vg-zeilen') and pg.input_value('#vg-ab') == HEUTE.isoformat() and pg.is_enabled('#vg-ok'))
    pg.mouse.click(5, 5)
    check('Klick neben den Dialog schließt ihn nicht', pg.is_visible('#dlg-vf-freigabe'))
    pg.click('#vg-ok')
    pg.wait_for_function("() => document.querySelector('#vg-meldung').textContent.includes('Anlass')")
    pg.fill('#vg-grund', 'Ergänzung zur Organisation'); pg.click('#vg-ok')
    pg.wait_for_selector('#dlg-vf-freigabe', state='hidden')
    pg.wait_for_function("() => document.querySelector('#vf-freigeben-text').textContent === 'Überprüft vermerken'")
    check('Fassung 3 freigegeben: Stand aktualisiert, keine Abweichung mehr, drei Fassungen', f'Fassung 3 · gültig ab {de(HEUTE.isoformat())}' in pg.text_content('#vf-status') and 'weicht' not in pg.text_content('#vf-status')
          and pg.locator('.vf-fassung').count() == 3 and pg.text_content('#vf-offen') == '')
    pg.click('#vf-freigeben'); pg.wait_for_selector('#dlg-vf-freigabe[open]')
    check('ohne Abweichung: Dialog „Ohne Änderung überprüft“ mit Bemerkung statt Anlass', pg.text_content('#vg-titel') == 'Ohne Änderung überprüft' and pg.is_hidden('#vg-fassung') and pg.is_visible('#vg-notiz'))
    pg.keyboard.press('Escape')
    pg.screenshot(path=os.path.join(SH, 'qs_verfahren_1280_light.png'), full_page=True)
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('gerda', 'Freigabe-Konto-78', '198.51.100.17', breite, thema, 844 if breite < 500 else 900)
        pg.wait_for_selector('#vf-teile .vf-abschnitt')
        pg.locator('.vf-abschnitt', has_text='Eingangsrechnungen').locator('summary').click()
        breit = pg.evaluate('() => document.documentElement.scrollWidth - window.innerWidth')
        check(f'{breite} px {thema}: Verfahrensdoku ohne waagerechtes Scrollen der Seite', breit <= 0, breit)
        pg.screenshot(path=os.path.join(SH, f'qs_verfahren_{breite}_{thema}.png'), full_page=True)
        if breite == 390:
            pg.locator('.vf-abschnitt', has_text='Eingangsrechnungen').locator('[data-vf-abschnitt]').click(); pg.wait_for_selector('#dlg-vf-abschnitt[open]')
            innen = pg.evaluate("() => { const d = document.querySelector('#dlg-vf-abschnitt'); return d.scrollWidth - d.clientWidth; }")
            check(f'{breite} px {thema}: Abschnitt-Dialog passt in die Breite', innen <= 0 and pg.evaluate("() => document.querySelector('#dlg-vf-abschnitt').getBoundingClientRect().width") <= 390, innen)
            pg.screenshot(path=os.path.join(SH, f'qs_verfahren_dialog_{breite}_{thema}.png'))
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler[:5])

print(f'{sum(res)}/{len(res)} passed')
