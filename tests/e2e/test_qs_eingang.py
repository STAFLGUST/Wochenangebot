"""QM-System – Eingang (Dateien ohne Ziel, Dokument qs-ablage mit ziel „eingang“, module/qs/ablage.php).

Geprüft: Rechte serverseitig (Liste, Download, Hochladen, Zuordnen, Löschen nur mit „bearbeiten“; ansehen sieht weder Liste noch
Zahl noch Datei); Hochladen ohne Ziel mit bereinigtem Ordnerpfad (Backslash teilt, Steuerzeichen, 12 Teile, 120 Zeichen, 500 Byte);
der Eingang ist kein Dokument (nicht in qs_start, CSV, ZIP, Bericht); Zuordnen an Ordner (nur „ziel“ ändert sich, ein
Schreibvorgang), externe Dokumente und Entwürfe (Eintrag wandert nach qs-dokumente, Platzhalter, ein Verlaufseintrag je Vorgang,
4-Augen-Prinzip: wer hochgeladen hat, zählt als Bearbeiter), nie in freigegebene Versionen, Prüfung, eingezogene, unbekannte Ziele;
alles oder nichts; Grenze am Ziel (10 000 je Ordner) und im Eingang (20 000); Kennungen nur aus Ziffern; Löschen endgültig mit
gemerkter Prüfsumme, nie eine Datei, die qs-dokumente noch verwendet; große Auswahl (15 000) in einem Durchlauf; Protokoll mit
Anzahl, ohne Dateinamen; Oberfläche (Knopf mit Zahl, Hochladen per Auswahl und Ziehen, Suche, Ordner-Filter, Zuordnen, Löschen,
Herunterladen, 1280/390 px hell und dunkel, ohne Knopf für Leser, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import SH, storage_write
from qs_hilfe import (PW, check, ende, fehler, pdf, docx_w, blob_pfad, speicher, hochladen, roh, nutzer, fuellen, leeren, neu_zaehlen, anmelden, text,
                      ohne_scrollen)


def hoch_e(cli, name, inhalt, pfad=None):
    return hochladen(cli, 'eingang', '', name, inhalt, {'pfad': pfad} if pfad is not None else None)


def eingang(cli=None):
    st_, r_ = (cli or Be).call('qs_eingang')
    return {f['id']: f for f in r_.get('dateien', [])} if st_ == 200 else None


def archiv(did):
    return {f['id']: f for f in L.call(f'qs_archiv&dok={did}')[1].get('dateien', [])}


def dok(did):
    return {x['id']: x for x in L.call('qs_start')[1]['dokumente']}[did]


def schritt(cli, did, s, **extra):
    return cli.call('qs_version_schritt', {'dokument': did, 'rev': dok(did)['rev'], 'schritt': s, **extra})


leser = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), '..', '..', 'werkzeuge', 'qs_ablage_leser.py')], capture_output=True, text=True)
check('Code: „dateien“ an Ordnern nur über die Leser in module/qs/ablage.php (werkzeuge/qs_ablage_leser.py)', leser.returncode == 0, leser.stdout[-600:])

NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('anna', 'Anna Ablage', 'editor', 'Ablage-Konto-35', {'grant': ['qs.bearbeiten', 'qs.freigeben']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}))
A, K, ids = nutzer(NUTZER)
L, Be, An, Q, O, N = K['lisa'], K['bernd'], K['anna'], K['quinn'], K['otto'], Client('198.51.100.30')
V = Client('198.51.100.20'); V.call('login', {'username': 'admin', 'password': PW})
KAP = [{'id': '1.4', 'titel': 'Qualitätssicherung', 'zustaendig': 'QB'}, {'id': '1.5', 'titel': 'Mitarbeiter', 'zustaendig': 'QB'},
       {'id': '2.1', 'titel': 'Einkauf / Wareneingang', 'zustaendig': 'QB'}]
check('Kapitel', V.call('qs_stamm_save', {'kapitel': KAP})[0] == 200)
O1 = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Laborbefunde'})[1]['dokument']['id']
X1 = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'X', 'nr': '', 'titel': 'Lieferantenzertifikate'})[1]['dokument']['id']
r = Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F05', 'titel': 'Wareneingangskontrolle'})[1]['dokument']
D3, V31 = r['id'], r['versionen'][0]['id']

# ── Kapitel 1.5 „Mitarbeiter“ (personenbezogene Unterlagen, Entscheidung des Inhabers 16.11.2026): nur mit „bearbeiten“ sichtbar ──
P15 = Be.call('qs_dokument_save', {'kapitel': '1.5', 'art': 'O', 'nr': '', 'titel': 'Personalakten'})[1]['dokument']['id']
akte = hochladen(Be, P15, '', 'Akte Muster.pdf', pdf('Akte'))[1]['datei']
r15 = An.call('qs_dokument_save', {'kapitel': '1.5', 'art': 'F', 'nr': '', 'titel': 'Unterweisung'})[1]['dokument']
unterw = hochladen(An, r15['id'], r15['versionen'][0]['id'], 'Unterweisung.pdf', pdf('Unterweisung'))[1]['datei']
rev15 = lambda: {x['id']: x for x in Be.call('qs_start')[1]['dokumente']}[r15['id']]['rev']
An.call('qs_version_schritt', {'dokument': r15['id'], 'rev': rev15(), 'schritt': 'einreichen'})
check('Kapitel 1.5: Ordner mit Datei und freigegebenes Formblatt angelegt', Q.call('qs_version_schritt', {'dokument': r15['id'], 'rev': rev15(), 'schritt': 'pruefen_freigeben'})[0] == 200)
st, r = L.call('qs_start')
check('Kapitel 1.5 mit nur „ansehen“: nicht in der Liste (also auch nicht in der Suche), keine Zahl je Ordner', st == 200 and not any(d['kapitel'] == '1.5' for d in r['dokumente'])
      and P15 not in r['ablageZahlen'] and any(d['kapitel'] == '1.5' for d in Be.call('qs_start')[1]['dokumente']), [d['titel'] for d in r['dokumente']])
st, _, csv15 = L.call('qs_export', {'liste': 'dokumente'}, raw=True)
check('… nicht in der Dokumentenliste (CSV)', st == 200 and 'Personalakten' not in csv15 and 'Unterweisung' not in csv15)
for was, abruf in (('Datei am Ordner', 'qs_datei&id=' + akte), ('Datei der gültigen Version', 'qs_datei&id=' + unterw), ('Ordnerbaum', f'qs_archiv&dok={P15}'),
                   ('Ordner als ZIP', f'qs_archiv_zip&dok={P15}')):
    check(f'… kein direkter Abruf ({was}): 403; mit „bearbeiten“ 200', roh(L, abruf)[0] == 403 and roh(Be, abruf)[0] == 200)
for q in ('qs_ablage_export&alle=1', 'qs_ablage_export&kapitel=1.5&alle=1'):
    st, z = roh(L, q)
    n15 = zipfile.ZipFile(io.BytesIO(z)).namelist() if st == 200 else ['?']
    check(f'… nicht im ZIP-Export ({q.split("&", 1)[1]}), mit „bearbeiten“ schon', not any('Mitarbeiter' in x for x in n15)
          and any('Mitarbeiter' in x for x in zipfile.ZipFile(io.BytesIO(roh(Be, q)[1])).namelist()), n15)
heute = r['heute']
b15 = lambda cli: json.dumps(cli.call(f'qs_bericht&von={heute[:8]}01&bis={heute}')[1], ensure_ascii=False)
check('… nicht im Audit-Bericht, mit „bearbeiten“ schon', 'Unterweisung' not in b15(L) and 'Unterweisung' in b15(Be))

# ── Rechte ──
EIN1 = pdf('Eingang Befund 1')
check('Hochladen in den Eingang: ohne Anmeldung, ohne QM-Recht, nur ansehen → kein Zugang', hoch_e(N, 'a.pdf', EIN1)[0] in (401, 403, 404) and hoch_e(O, 'a.pdf', EIN1)[0] == 403
      and hoch_e(L, 'a.pdf', EIN1)[0] == 403)
check('Liste: nur ansehen 403 (unsortierte Unterlagen nur für Bearbeiter), ohne Recht 403, ohne Anmeldung kein Zugang, Bearbeiter leer 200',
      L.call('qs_eingang')[0] == 403 and O.call('qs_eingang')[0] == 403 and N.call('qs_eingang')[0] in (401, 403, 404) and eingang() == {})
check('Zuordnen/Löschen: per GET 405, nur ansehen 403', Be.call('qs_datei_zuordnen')[0] == 405 and Be.call('qs_eingang_loeschen')[0] == 405
      and L.call('qs_datei_zuordnen', {'dateien': ['abcdefabcdefabcdefab'], 'dokument': O1})[0] == 403 and L.call('qs_eingang_loeschen', {'dateien': ['abcdefabcdefabcdefab']})[0] == 403)

# ── Hochladen mit Ordnerpfad (nur der Server bereinigt) ──
st, r = hoch_e(Be, 'Befund Labor 01.pdf', EIN1, pfad=' QM-System\\1.4 Qualitätssicherung//Befunde/../ Labor  A\tab 2025 ﻿/\u0085')
e1 = r.get('datei', '')
check('Hochladen ohne Ziel: kein Dokument in der Antwort', st == 200 and e1 and 'dokument' not in r, r)
x1 = eingang().get(e1, {})
check('Liste: Name, Größe, wer, Pfad bereinigt (Backslash teilt, ohne leere/„..“-Teile, Leerraum zusammengefasst, ohne Steuerzeichen), ohne Prüfsumme',
      x1.get('name') == 'Befund Labor 01.pdf' and x1.get('groesse') == len(EIN1) and x1.get('hochgeladen', {}).get('von') == 'Bernd Bearbeiter'
      and x1.get('pfad') == 'QM-System/1.4 Qualitätssicherung/Befunde/Labor A ab 2025' and 'sha256' not in x1, x1)
lang = '/'.join(f'Ebene {i} ' + 'ä' * 150 for i in range(15))
tid = hoch_e(Be, 'Tief.pdf', pdf('tief'), pfad=lang)[1]['datei']
tief = eingang()[tid]['pfad']
check('Pfad: höchstens 12 Ordner zu je 120 Zeichen und 500 Byte (ganze Ordner)', len(tief.encode()) <= 500 and all(len(t) == 120 for t in tief.split('/')) and len(tief.split('/')) == 2, tief)
oh = hoch_e(Be, 'Ohne Pfad.pdf', pdf('ohne'))[1]['datei']
gesp = [f for f in speicher('qs-ablage')['liste'] if f['id'] == oh]
check('Speicher: Eintrag in qs-ablage mit ziel „eingang“, ohne pfad kein Feld; mit Version → 422', gesp and gesp[0]['ziel'] == 'eingang' and 'pfad' not in gesp[0]
      and hochladen(Be, 'eingang', V31, 'v.pdf', pdf('v'))[0] == 422, gesp)
st, r = L.call('qs_start'); st2, r2 = Be.call('qs_start')
check('qs_start: Zahl nur für Bearbeiter, nie die Liste, Eingang ist kein Dokument und keine Zahl je Ziel', r['eingangZahl'] == 0 and r2['eingangZahl'] == 3
      and 'eingang' not in json.dumps(r2.get('ablageZahlen')) and not any(d['id'] == 'eingang' for d in r2['dokumente']), (r['eingangZahl'], r2['eingangZahl']))
check('Download: Bearbeiter 200 mit Inhalt, nur ansehen 403, Datei unter data/dateien/qs', roh(Be, 'qs_datei&id=' + e1) == (200, EIN1) and roh(L, 'qs_datei&id=' + e1)[0] == 403
      and os.path.isfile(blob_pfad(e1)))
check('Entfernen gilt im Eingang nicht (409: zuordnen oder löschen)', Q.call('qs_datei_entfernen', {'datei': e1, 'grund': 'weg'})[0] == 409)
st, _, csv_ = L.call('qs_export', {'liste': 'dokumente'}, raw=True)
st2, zipdaten = roh(L, 'qs_ablage_export&alle=1')
namen = zipfile.ZipFile(io.BytesIO(zipdaten)).namelist()
check('Eingang nicht in Dokumentenliste und ZIP', st == 200 and 'Befund Labor' not in csv_ and not any('Befund Labor' in n or 'Eingang' in n for n in namen), namen[:5])

# ── Zuordnen ──
rev_ab = speicher('qs-ablage')['rev']; rev_dok = dok(O1)['rev']
st, r = Be.call('qs_datei_zuordnen', {'dateien': [e1], 'dokument': O1, 'version': ''})
z = speicher('qs-ablage')
gz = [f for f in z['liste'] if f['id'] == e1]
check('Zuordnen an einen Ordner: nur „ziel“ ändert sich (ein Schreibvorgang, Dokument unverändert), Pfad und wer bleiben',
      st == 200 and gz and gz[0]['ziel'] == O1 and gz[0]['pfad'] == x1['pfad'] and z['rev'] == rev_ab + 1 and dok(O1)['rev'] == rev_dok and r.get('eingangZahl') == 2, (st, gz))
check('Zuordnen: im Ordnerbaum, nicht mehr im Eingang, Inhalt gleich, Zahl je Ordner in qs_start', e1 in archiv(O1) and e1 not in eingang() and roh(L, 'qs_datei&id=' + e1) == (200, EIN1)
      and L.call('qs_start')[1]['ablageZahlen'][O1] == {'dateien': 1, 'bytes': len(EIN1)})
mehr = [hoch_e(Be, f'Zertifikat {c}.pdf', pdf('Zertifikat ' + c))[1]['datei'] for c in 'DEF']
st, r = Be.call('qs_datei_zuordnen', {'dateien': mehr, 'dokument': X1})
check('Mehrfach zuordnen an ein externes Dokument', st == 200 and set(mehr) <= set(archiv(X1)) and not set(mehr) & set(eingang()), r)
# 4-Augen-Prinzip: Bernd lädt hoch, Anna ordnet in Quinns Entwurf zu → Bernd ist Bearbeiter
forms = [hoch_e(Be, f'Formular {k}.docx', docx_w(f'Formular {k} {{{{Version}}}}'))[1]['datei'] for k in (1, 2, 3)]
verlauf_vorher = len(dok(D3)['versionen'][0]['verlauf'])
st, r = An.call('qs_datei_zuordnen', {'dateien': forms, 'dokument': D3, 'version': V31})
v31 = r['dokument']['versionen'][0] if st == 200 else {}
f31 = [f for f in v31.get('dateien', []) if f['id'] in forms]
check('Zuordnen in einen Entwurf: Eintrag nach qs-dokumente, Platzhalter erkannt, Datei bleibt liegen', st == 200 and len(f31) == 3 and all('version' in f.get('platzhalter', []) for f in f31)
      and not set(forms) & {f['id'] for f in speicher('qs-ablage')['liste']} and all(os.path.isfile(blob_pfad(i)) for i in forms), (r, f31))
check('4-Augen-Prinzip: wer zuordnet und wer hochgeladen hat, sind Bearbeiter', {ids['anna'], ids['bernd']} <= set(v31.get('bearbeiter', [])), v31.get('bearbeiter'))
check('ein Verlaufseintrag je Zuordnen (nicht je Datei)', len(v31['verlauf']) == verlauf_vorher + 1 and v31['verlauf'][-1]['was'] == '3 Dateien aus dem Eingang zugeordnet', v31['verlauf'][-2:])
check('Entwurf zur Prüfung (Quinn)', schritt(Q, D3, 'einreichen')[0] == 200)
check('Bernd (nur hochgeladen) kann ihn trotzdem nicht prüfen – Anna auch nicht', Be.call('qs_version_schritt', {'dokument': D3, 'rev': dok(D3)['rev'], 'schritt': 'pruefen_freigeben'})[0] == 403
      and schritt(An, D3, 'pruefen_freigeben')[0] == 403)
st, r = Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F06', 'titel': 'Probenahme'})
D4, V41 = r['dokument']['id'], r['dokument']['versionen'][0]['id']
hoch_e(An, 'Probenahme.pdf', pdf('Probe'))
ef = next(i for i, f in eingang().items() if f['name'] == 'Probenahme.pdf')
check('Zuordnen durch Quinn: Anna (hochgeladen) wird Bearbeiter und darf nicht prüfen', Q.call('qs_datei_zuordnen', {'dateien': [ef], 'dokument': D4, 'version': V41})[0] == 200
      and schritt(Q, D4, 'einreichen')[0] == 200 and schritt(An, D4, 'pruefen_freigeben')[0] == 403 and ids['anna'] in dok(D4)['versionen'][0]['bearbeiter'])
D5 = Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F07', 'titel': 'Gültig'})[1]['dokument']
v51 = D5['versionen'][0]['id']
hochladen(Q, D5['id'], v51, 'Gültig.pdf', pdf('gültig'))
check('Version freigegeben (Quinn reicht ein, Anna gibt frei)', schritt(Q, D5['id'], 'einreichen')[0] == 200 and schritt(An, D5['id'], 'pruefen_freigeben')[0] == 200)
e2 = hoch_e(Be, 'Nachtrag.pdf', pdf('Nachtrag'))[1]['datei']
st, r = An.call('qs_datei_zuordnen', {'dateien': [e2], 'dokument': D5['id'], 'version': v51})
check('nie in eine freigegebene Version (409 mit Hinweis auf nachtragen), Datei bleibt im Eingang', st == 409 and 'nachtragen' in r.get('error', '') and e2 in eingang(), r)
O9 = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Eingezogen'})[1]['dokument']['id']
Q.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Eingezogen', 'id': O9, 'rev': dok(O9)['rev'], 'eingezogen': True, 'einzugGrund': 'alt'})
for fall, ziel, ver, erwartet in (('Entwurf liegt zur Prüfung', D3, V31, 409), ('eingezogener Ordner', O9, '', 409), ('unbekanntes Dokument', 'dnix', '', 404),
                                  ('Eingang als Ziel', 'eingang', '', 404), ('freigegebene Version', D5['id'], v51, 409)):
    st, r = Be.call('qs_datei_zuordnen', {'dateien': [e2], 'dokument': ziel, 'version': ver})
    check(f'Zuordnen gesperrt – {fall}: {erwartet}, Datei bleibt im Eingang', st == erwartet and e2 in eingang(), (st, r))
zl = Be.call('qs_eingang')[1].get('ziele', [])
check('Ziele vom Server (qs_ablage_regel „zuordnen“): Ordner, externe Dokumente, Entwürfe – nie freigegebene Versionen, Prüfung, Eingezogenes',
      {'dok': O1, 'ver': ''} in zl and {'dok': X1, 'ver': ''} in zl and {'dok': D4, 'ver': V41} not in zl and not any(z['dok'] in (D3, D5['id'], O9) for z in zl), zl)
st, r = Be.call('qs_datei_zuordnen', {'dateien': [e2, 'abcdefabcdefabcdefab'], 'dokument': O1})
check('alles oder nichts: eine unbekannte Datei → 404, die andere bleibt', st == 404 and e2 in eingang() and e2 not in archiv(O1), r)
check('zugeordnete Datei ist nicht mehr im Eingang (404)', Be.call('qs_datei_zuordnen', {'dateien': [e1], 'dokument': X1})[0] == 404)
st, r = Be.call('qs_datei_zuordnen', {'dateien': ['123456789012', '123456789013'], 'dokument': O1})
check('Kennungen nur aus Ziffern: 404 statt Serverfehler', st == 404, (st, r))
check('Auswahl leer, keine Liste, ungültige Kennung → 422', Be.call('qs_datei_zuordnen', {'dateien': [], 'dokument': O1})[0] == 422
      and Be.call('qs_datei_zuordnen', {'dateien': 'x', 'dokument': O1})[0] == 422 and Be.call('qs_eingang_loeschen', {'dateien': ['../etc']})[0] == 422)
e3 = hoch_e(Be, 'Grenze.pdf', pdf('Grenze'))[1]['datei']
fuellen(Be, 10000 - len(archiv(O1)) - 1, O1, 'grenzeziel')
st, r = Be.call('qs_datei_zuordnen', {'dateien': [e2, e3], 'dokument': O1})
check('Grenze am Ordner (10 000): zwei Dateien auf den letzten Platz → 422, beide bleiben', st == 422 and '10000' in r.get('error', '') and {e2, e3} <= set(eingang()), r)
check('eine passt noch', Be.call('qs_datei_zuordnen', {'dateien': [e3], 'dokument': O1})[0] == 200)
leeren(Be, 'grenzeziel')

# ── Löschen ──
weg = [hoch_e(Be, f'Weg {k}.pdf', pdf(f'Weg {k}'))[1]['datei'] for k in (1, 2)]
st, r = Be.call('qs_eingang_loeschen', {'dateien': [weg[0], 'abcdefabcdefabcdefab']})
check('Löschen: unbekannte Datei → 404, nichts gelöscht', st == 404 and weg[0] in eingang() and os.path.isfile(blob_pfad(weg[0])), r)
check('zugeordnete Datei lässt sich über den Eingang nicht löschen (404)', Be.call('qs_eingang_loeschen', {'dateien': [e1]})[0] == 404 and os.path.isfile(blob_pfad(e1)))
sha_weg = hashlib.sha256(pdf('Weg 1')).hexdigest()
st, r = Be.call('qs_eingang_loeschen', {'dateien': weg})
check('Löschen: Einträge und Dateien weg, Prüfsumme gemerkt, Download 404, Zahl in der Antwort', st == 200 and not set(weg) & set(eingang()) and r.get('eingangZahl') == len(eingang())
      and not any(os.path.isfile(blob_pfad(i)) for i in weg) and sha_weg in speicher('qs-ablage').get('verworfen', []) and roh(Be, 'qs_datei&id=' + weg[0])[0] == 404, r)
# Abbruch zwischen den Schreibvorgängen beim Zuordnen in einen Entwurf: der Eintrag steht im Entwurf und noch im Eingang (wie nach dem Abbruch)
D6 = Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F08', 'titel': 'Abbruch'})[1]['dokument']
V61 = D6['versionen'][0]['id']


def halb_zugeordnet(name, did, vi=0):
    eid = hoch_e(Be, name, pdf(name))[1]['datei']
    d_ = speicher('qs-dokumente'); f_ = next(f for f in speicher('qs-ablage')['liste'] if f['id'] == eid)
    next(x for x in d_['liste'] if x['id'] == did)['versionen'][vi].setdefault('dateien', []).append({k: v for k, v in f_.items() if k != 'ziel'})
    storage_write('qs-dokumente', d_)
    return eid


nochmal = halb_zugeordnet('Nochmal.pdf', D6['id'])
st, r = Be.call('qs_datei_zuordnen', {'dateien': [nochmal], 'dokument': D6['id'], 'version': V61})
check('nach einem Abbruch erneut zugeordnet: genau ein Verweis im Entwurf, nicht mehr im Eingang (Fehler 13)', st == 200
      and [f['id'] for f in dok(D6['id'])['versionen'][0]['dateien']].count(nochmal) == 1 and nochmal not in eingang(), (st, r))
im_entwurf = halb_zugeordnet('Im Entwurf gelöscht.pdf', D6['id'])
st, r = Be.call('qs_datei_entfernen', {'datei': im_entwurf, 'rev': dok(D6['id'])['rev']})
check('im Entwurf gelöscht, aber noch im Eingang: die Datei selbst bleibt (Fehler 13)', st == 200 and im_entwurf in eingang() and os.path.isfile(blob_pfad(im_entwurf))
      and roh(Be, 'qs_datei&id=' + im_entwurf)[0] == 200 and im_entwurf not in [f['id'] for f in dok(D6['id'])['versionen'][0]['dateien']], (st, r))
doppelt = halb_zugeordnet('Doppelt.pdf', D4)
check('Löschen im Eingang entfernt nie eine Datei, die qs-dokumente noch verwendet', Be.call('qs_eingang_loeschen', {'dateien': [doppelt]})[0] == 200 and doppelt not in eingang()
      and os.path.isfile(blob_pfad(doppelt)) and roh(L, 'qs_datei&id=' + doppelt)[0] == 200)
check('Zuordnen in einen Entwurf: erst die Grenze (1 000 je Version), dann das Lesen der Dateien – 1 001 Kennungen → 422',
      Be.call('qs_datei_zuordnen', {'dateien': [f'grenze{i:012d}' for i in range(1001)], 'dokument': D6['id'], 'version': V61})[0] == 422)

# Datenpaket-Sperre zählt qs-ablage selbst (Fehler 16): auch wenn qs-ablage-zahlen veraltet ist (Abbruch zwischen den beiden Schreibvorgängen)
storage_write('qs-ablage-zahlen', {'rev': 0, 'je': {}})
paket = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'qs', 'datenpaket.json'), encoding='utf-8'))
st, r = V.call('qs_import', {'paket': paket, 'vorschau': True})
alle_ = sum(1 for f in speicher('qs-ablage')['liste'] if not f.get('entfernt')) + sum(1 for x in speicher('qs-dokumente')['liste'] for f in x.get('dateien', [])
          + [f for v in x.get('versionen', []) for f in v.get('dateien', [])] if not f.get('entfernt'))
check('Datenpaket: zählt die Dateien in qs-ablage direkt, nicht über die abgeleiteten Zahlen', st == 200 and r['dateien'] == alle_ and len(eingang()) > 0, (st, r.get('dateien'), alle_))
neu_zaehlen(Be)

# ── Große Auswahl in einem Durchlauf, Grenze des Eingangs ──
fuellen(Be, 9990, 'eingang', 'gross')
gross = [i for i in eingang() if i.startswith('gross')]
t0 = time.time()
st, r = Be.call('qs_datei_zuordnen', {'dateien': gross, 'dokument': X1})
t1 = time.time() - t0
check(f'9 990 Dateien auf einmal zuordnen: ein Durchlauf ({t1:.1f} s)', st == 200 and t1 < 10 and len(archiv(X1)) >= 9990, (st, r.get('error'), t1))
leeren(Be, 'gross')
fuellen(Be, 15000, 'eingang', 'gross')
t0 = time.time()
st, r = Be.call('qs_eingang_loeschen', {'dateien': [i for i in eingang() if i.startswith('gross')]})
t2 = time.time() - t0
check(f'15 000 Dateien auf einmal löschen: ein Durchlauf ({t2:.1f} s)', st == 200 and t2 < 10 and not any(i.startswith('gross') for i in eingang()), (st, t2))
fuellen(Be, 20000 - len(eingang()) - 1, 'eingang', 'grenzeeingang')
st, r = hoch_e(Be, 'Letzte.pdf', pdf('letzte'))
st2, r2 = hoch_e(Be, 'Zuviel.pdf', pdf('zu viel'))
check('Eingang: höchstens 20 000 Dateien (20 000. abgelegt, danach 422 „voll“)', st == 200 and st2 == 422 and 'voll' in r2.get('error', ''), (st, r2))
leeren(Be, 'grenzeeingang')
ab = speicher('qs-ablage')
ab['verworfen'] = []
storage_write('qs-ablage', ab)

# ── Protokoll ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: hochgeladen, zugeordnet und gelöscht mit Anzahl', all(t in log for t in ('Datei für den Eingang abgelegt', '1 Datei aus dem Eingang Laborbefunde zugeordnet',
                                                                                         '3 Dateien aus dem Eingang 1.4-F05 Wareneingangskontrolle zugeordnet', '2 Dateien im Eingang gelöscht')), log[-1500:])
check('Protokoll ohne Dateinamen', not any(n in log for n in ('Befund Labor 01.pdf', 'Formular 1.docx', 'Zertifikat D.pdf')))

# ── Oberfläche ──
ZIEH = """([sel, dateien]) => {
  const dt = new DataTransfer();
  for (const [name, text, typ] of dateien) dt.items.add(new File([text], name, { type: typ }));
  const z = document.querySelector(sel);
  for (const t of ['dragenter', 'dragover', 'drop']) z.dispatchEvent(new DragEvent(t, { dataTransfer: dt, bubbles: true, cancelable: true }));
}"""
with sync_playwright() as p:
    br = p.chromium.launch()

    def toast(pg, inhalt):
        pg.wait_for_function('t => document.querySelector("#qm-toast").classList.contains("zeigen") && document.querySelector("#qm-toast").textContent.includes(t)', arg=inhalt)

    def ei_warte(pg, n):
        pg.wait_for_function('n => document.querySelectorAll("#ei-liste tr[data-ei]").length === n', arg=n)

    hoch_e(Be, '1.4-F01_2023-11-21.pdf', pdf('Nachweis'), pfad='1.4 Qualitätssicherung/Checkliste Probenahme')
    hoch_e(Be, '1.4-F01 Probenahmeprotokoll.pdf', pdf('Firma B'), pfad='_Firma B/1.4 Qualitätssicherung')
    n_e = len(eingang())
    ctx, pg = anmelden(br, 'lisa', 'Leserin-Konto-12', '198.51.100.10')
    check('nur ansehen: kein Eingang-Knopf', pg.is_hidden('#qm-d-eingang'))
    ctx.close()
    ctx, pg = anmelden(br, 'bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    check('Eingang-Knopf in „Dokumente“: Zahl, hervorgehoben', pg.is_visible('#qm-d-eingang') and text(pg, '#qm-d-eingang-zahl') == str(n_e)
          and 'voll' in (pg.get_attribute('#qm-d-eingang', 'class') or ''), text(pg, '#qm-d-eingang'))
    pg.click('#qm-d-eingang'); ei_warte(pg, n_e)
    check('Liste mit Ordnerpfad und wer', '_Firma B / 1.4 Qualitätssicherung' in text(pg, '#ei-liste') and 'Bernd Bearbeiter' in text(pg, '#ei-liste') and f'{n_e} Dateien' in text(pg, '#ei-titel'))
    with pg.expect_file_chooser() as fc:
        pg.click('#ei-drop')
    fc.value.set_files([{'name': 'Scan Wareneingang 1.pdf', 'mimeType': 'application/pdf', 'buffer': pdf('Scan WE 1')},
                        {'name': 'Scan Wareneingang 2.pdf', 'mimeType': 'application/pdf', 'buffer': pdf('Scan WE 2')}])
    toast(pg, '2 Dateien abgelegt'); ei_warte(pg, n_e + 2)
    pg.evaluate(ZIEH, ['#ei-drop', [['Lieferschein.pdf', '%PDF-1.4 Lieferschein', 'application/pdf'], ['Werkzeug.exe', 'MZ', 'application/octet-stream']]])
    toast(pg, 'Werkzeug.exe'); ei_warte(pg, n_e + 3)
    check('per Auswahl und Ziehen hochgeladen (verbotene Art mit Grund), Zahl im Knopf', text(pg, '#qm-d-eingang-zahl') == str(n_e + 3) and len(eingang()) == n_e + 3
          and 'nicht erlaubt' in text(pg, '#ei-laden'), text(pg, '#ei-laden'))
    pg.fill('#ei-suche', 'Scan Wareneingang'); ei_warte(pg, 2)
    pg.fill('#ei-suche', 'Checkliste Probenahme'); ei_warte(pg, 1)
    check('Suche findet auch den Ordnerpfad', '1.4-F01_2023-11-21.pdf' in text(pg, '#ei-liste'))
    pg.fill('#ei-suche', ''); pg.select_option('#ei-ordner', '_Firma B'); ei_warte(pg, 1)
    check('Ordner-Filter (erste Ebene, mit Zahl)', '1.4-F01 Probenahmeprotokoll.pdf' in text(pg, '#ei-liste') and '_Firma B (1)' in text(pg, '#ei-ordner'))
    pg.select_option('#ei-ordner', ''); ei_warte(pg, n_e + 3)
    pg.screenshot(path=os.path.join(SH, 'qs_eingang_1280.png'))
    pg.fill('#ei-suche', 'Scan Wareneingang'); ei_warte(pg, 2)
    pg.check('#ei-alle'); pg.wait_for_function("document.querySelector('#ei-gewaehlt').textContent.startsWith('2 Dateien')")
    check('ohne Ziel kein Zuordnen', pg.is_disabled('#ei-zuordnen') and pg.is_enabled('#ei-loeschen'))
    pg.fill('#ei-ziel', 'Laborbefunde (2.1)'); pg.wait_for_selector('#ei-zuordnen:enabled')
    scans = {f['id'] for f in eingang().values() if f['name'].startswith('Scan Wareneingang')}
    pg.click('#ei-zuordnen'); toast(pg, '2 Dateien zugeordnet: Laborbefunde (2.1)'); ei_warte(pg, 0)
    check('Zuordnen: im Ordner, nicht mehr im Eingang, Zahl im Knopf', scans <= set(archiv(O1)) and not scans & set(eingang()) and text(pg, '#qm-d-eingang-zahl') == str(n_e + 1))
    pg.fill('#ei-suche', 'Lieferschein'); ei_warte(pg, 1)
    lid = next(i for i, f in eingang().items() if f['name'] == 'Lieferschein.pdf')
    pg.check(f'#ei-liste [data-ei-an="{lid}"]'); pg.click('#ei-loeschen')
    check('Löschen fragt nach (zweiter Klick)', 'endgültig löschen?' in text(pg, '#ei-loeschen') and lid in eingang())
    pg.click('#ei-loeschen'); toast(pg, '1 Datei gelöscht'); ei_warte(pg, 0)
    check('gelöscht: nicht mehr im Eingang, Datei weg', lid not in eingang() and not os.path.isfile(blob_pfad(lid)))
    pg.fill('#ei-suche', 'Checkliste'); ei_warte(pg, 1)
    with pg.expect_download() as dl:
        pg.click('#ei-liste [data-ei-datei]')
    check('Herunterladen über einen direkten Link: Name und Inhalt', dl.value.suggested_filename == '1.4-F01_2023-11-21.pdf' and open(dl.value.path(), 'rb').read() == pdf('Nachweis'))
    pg.fill('#ei-suche', '')
    check('1280 px: ohne waagerechtes Scrollen', ohne_scrollen(pg, '#dlg-eingang'))
    ctx.close()
    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden(br, 'bernd', 'Bearbeit-Konto-34', '198.51.100.11', breite, thema, 844 if breite < 500 else 900)
        pg.click('#qm-d-eingang'); pg.wait_for_selector('#ei-liste tr[data-ei]')
        check(f'{breite}px {thema}: Eingang ohne waagerechtes Scrollen', ohne_scrollen(pg, '#dlg-eingang'))
        pg.screenshot(path=os.path.join(SH, f'qs_eingang_{breite}_{thema}.png'))
        ctx.close()
    br.close()
ende()
