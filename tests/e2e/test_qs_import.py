"""QM-System – Ordner-Import (qs_sammel_plan, qs_import_eintragen, module/qs/ablage.php) und Ordnerbaum (qs_archiv, qs_archiv_zip).

Geprüft: Regeln nur auf dem Server – ganze Fallliste aus dem Review als Tabelle (Nummer nur direkt im erkannten Kapitelordner mit
leerem Rest oder Titel, oder im Ordner exakt „Nr Titel“; nie unter „_…“/„alt…“, nie in fremden obersten Ordnern; Archiv je Kapitel
und Unterordner der ersten Ebene mit pfad, „Weitere Dateien“, Systemdateien, Export-Listen und ältere Versionen eines Exports,
Dateiart, leer); Wurzel weglassen; Zuordnung der obersten Ordner (Eingang, nicht übernehmen, Kapitel, neuer Bereich nur mit
„verwalten“, im Bereich nie per Nummer); Anlegen von Bereichen und Ordner-Dokumenten, Wiederverwenden (Titel normalisiert),
eingezogene → Eingang; gebündeltes Eintragen (fertiger Upload bleibt liegen, bis 100 je Aufruf, fremder Upload, gleiche Datei,
früher gelöscht, gesperrtes Ziel → Eingang mit Herkunft, gültige Version nur mit „freigeben“, 4-Augen-Prinzip, ein Verlaufseintrag);
Fortsetzen (Plan erkennt Abgelegtes, auch nach Zuordnen aus dem Eingang); Grenzen (30 000 je Lauf, 10 000 je Ordner); ältere
Dateien am Ordner (GR-006: Baum, Download, ZIP, Entfernen, Plan); Ordnerbaum und ZIP je Unterordner; ZIP-Export mit Unterordnern;
Rechte; Protokoll mit Anzahl. Oberfläche: Vorschau (Wurzel, erkannte Kapitel, Zuordnung, Häkchen für gültige Versionen),
Fortschritt, Bericht als CSV, Fortsetzen, Abbruch, Ordnerbaum (aufklappen, Suche, ZIP), 1280/390 px hell und dunkel, keine
JavaScript-Fehler. Nur erfundene Testdaten.
"""
import base64
import csv
import glob
import hashlib
import io
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH, ablageordner, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
ABLAGE = os.path.join(ablageordner(), 'dateien')
TEIL = 3 * 1024 * 1024
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:600]) if i else ''))


def pdf(text):
    return b'%PDF-1.4\n% ' + text.encode() + b'\n%%EOF'


def speicher(name):
    return json.loads((storage_raw(name) or '{}').split('?>\n', 1)[-1] or '{}')


def blob_pfad(did):
    return os.path.join(ABLAGE, 'qs', did[:2], did + '.bin')


def roh(cli, query):
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, r.read()


def hochladen(cli, dok, ver, name, inhalt, extra=None):
    upload, pos, nr = '', 0, 0
    while True:
        st, r = cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest(),
                                                'upload': upload, 'teil': nr, 'daten': base64.b64encode(inhalt[pos:pos + TEIL]).decode(), **(extra or {})})
        if st != 200 or r.get('fertig'):
            return st, r
        upload = r['upload']; pos += TEIL; nr += 1


def sammeln(cli, e, name, inhalt):
    """Upload für den Ordner-Import nach dem Plan-Eintrag e – Rückgabe der fertige Upload (noch nicht eingetragen)"""
    ein = e['status'] == 'eingang'
    st, r = hochladen(cli, 'eingang' if ein else e['ziel'], '' if ein else e.get('ver', ''), name, inhalt,
                      {'sammeln': True, 'pfad': e.get('pfad', ''), 'herkunft': e.get('herkunft', '')})
    assert st == 200 and r.get('upload'), r
    return r['upload']


def plan(cli, pfade, wahl=None, anlegen=False):
    """Plan für Pfade („Ordner/…/Datei“ oder (Pfad, Größe)); Rückgabe (Status, Antwort, {Pfad: Eintrag})"""
    je = {}
    for p in pfade:
        p, g = p if isinstance(p, tuple) else (p, 1000)
        o, _, n = p.rpartition('/')
        je.setdefault(o, []).append((n, g, p))
    st, r = cli.call('qs_sammel_plan', {'ordner': [[o, [[n, g] for n, g, _ in l]] for o, l in je.items()], 'wahl': wahl or {}, 'anlegen': anlegen})
    flach = [p for l in je.values() for _, _, p in l]
    return st, r, ({p: e for p, e in zip(flach, r['dateien'])} if st == 200 else {})


def dok(did):
    return {x['id']: x for x in L.call('qs_start')[1]['dokumente']}[did]


def dok_titel(titel, kap):
    return next((x for x in L.call('qs_start')[1]['dokumente'] if x['titel'] == titel and x['kapitel'] == kap), None)


def archiv(did, cli=None):
    return (cli or L).call(f'qs_archiv&dok={did}')[1].get('dateien', [])


def eingang():
    return {f['id']: f for f in Be.call('qs_eingang')[1].get('dateien', [])}


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten', 'qs.freigeben']}))
for u, n, r, p, extra in NUTZER:
    assert A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})[0] == 200
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, V = K['lisa'], K['bernd'], K['quinn'], K['vera']
KAP = [{'id': '1.4', 'titel': 'Qualitätssicherung'}, {'id': '2.2', 'titel': 'Lager'}, {'id': '2.4', 'titel': 'Versand'}]
check('Kapitel', V.call('qs_stamm_save', {'kapitel': KAP})[0] == 200)


def gelenkt(kap, art, nr, titel, gueltig=True):
    r = Be.call('qs_dokument_save', {'kapitel': kap, 'art': art, 'nr': '', 'titel': titel})[1]['dokument']
    if nr:
        d_ = speicher('qs-dokumente'); next(x for x in d_['liste'] if x['id'] == r['id'])['nr'] = nr; storage_write('qs-dokumente', d_)
    if gueltig:
        hochladen(Be, r['id'], r['versionen'][0]['id'], 'Erstfassung.pdf', pdf(titel))
        assert Be.call('qs_version_schritt', {'dokument': r['id'], 'rev': dok(r['id'])['rev'], 'schritt': 'einreichen'})[0] == 200
        assert Q.call('qs_version_schritt', {'dokument': r['id'], 'rev': dok(r['id'])['rev'], 'schritt': 'pruefen_freigeben'})[0] == 200
    return dok(r['id'])


D1 = gelenkt('1.4', 'F', '1.4-F01', 'Temperaturkontrolle')
D2 = gelenkt('2.2', 'F', '2.2-F03', 'Wareneingang')
D3 = gelenkt('2.2', 'A', '2.2.1.1-A01', 'Reinigung Kühlhaus')
D4 = gelenkt('1.4', 'L', 'HACCP-Plan', 'HACCP-Plan')
D5 = gelenkt('1.4', 'F', '', 'Probenahme', gueltig=False)   # nur Entwurf (1.4-F02)
O1 = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Reinigungsnachweise'})[1]['dokument']['id']
check('gelenkte Dokumente mit gültiger Version, Entwurf, Ordner', D1['nr'] == '1.4-F01' and D5['nr'] == '1.4-F02' and D3['nr'] == '2.2.1.1-A01' and O1)
DOK = {D1['id']: 'd1', D2['id']: 'd2', D3['id']: 'd3', D4['id']: 'd4', D5['id']: 'd5', O1: 'o1'}

# ── Regeln: ganze Fallliste aus dem Review (Erwartung: Status, Ziel, pfad) – alle in einem Lauf, Wurzel „QM-System“ fällt weg ──
NEU = 'neu'   # Ziel: neues Ordner-Dokument (Titel im dritten Feld)
FAELLE = [
    ('QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'eingang', 'eingang', '_Firma/HACCP/1.4 QS'),
    ('QM-System/1.4 QS/Checkliste/1.4-F01_2023.pdf', 'ablage', (NEU, '1.4', 'Checkliste'), ''),
    ('QM-System/2.4 Lager/2.2-F03_Kunde.pdf', 'ablage', (NEU, '2.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/_alt/1.4-F01.doc', 'ablage', (NEU, '1.4', '_alt'), ''),
    ('QM-System/2.2 Lager/2.2.1.1-A01.docx', 'nachtragen', 'd3', None),
    ('QM-System/2.2 Lager/2.2.1.1.5-A01.docx', 'ablage', (NEU, '2.2', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-f01.pdf', 'nachtragen', 'd1', None),
    ('QM-System/1.4 qs/1.4-F1.pdf', 'nachtragen', 'd1', None),
    ('QM-System/Handbuch/1.4 QS/1.4-F01.pdf', 'eingang', 'eingang', 'Handbuch/1.4 QS'),
    ('QM-System/1.4 QS/1.4-F01_2023.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 alt.doc', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/Kopie von 1.4-F01.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 ausgefüllt KW12 2023.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 Temperaturkontrolle/KW01-2023.pdf', 'nachtragen', 'd1', None),   # Aufbau des eigenen Exports: Ordner exakt „Nr Titel“
    ('QM-System/1.4 QS/1.4-F01 Aufzeichnungen 2019-2023/Januar.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Aufzeichnungen 2019-2023'), ''),
    ('QM-System/1.4 QS/1.4-F01 Firma B/1.4-F01.xlsx', 'ablage', (NEU, '1.4', '1.4-F01 Firma B'), ''),
    ('QM-System/1.4 QS/1.4-F01 alt/1.4-F01.doc', 'ablage', (NEU, '1.4', '1.4-F01 alt'), ''),
    ('QM-System/1.4 QS/1.4-F01 Archiv/1.4-F01 v3.doc', 'ablage', (NEU, '1.4', '1.4-F01 Archiv'), ''),
    ('QM-System/1.4 QS/HACCP-Plan 2019.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/HACCP-Plan/2019.pdf', 'ablage', (NEU, '1.4', 'HACCP-Plan'), ''),
    ('QM-System/1.4 QS/Alt/1.4-F01.doc', 'ablage', (NEU, '1.4', 'Alt'), ''),
    ('QM-System/1.4 QS/alte Stände/1.4-F01.doc', 'ablage', (NEU, '1.4', 'alte Stände'), ''),
    ('QM-System/1.4 QS/Archiv/1.4-F01.doc', 'ablage', (NEU, '1.4', 'Archiv'), ''),
    ('QM-System/1.4 QS/1.4-F01.pdf', 'nachtragen', 'd1', None),
    ('QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'eingang', 'eingang', 'Firma B/1.4 QS'),
    ('QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf', 'ablage', 'o1', '2023'),
    ('QM-System/1.4 QS/reinigungsnachweise/2024/KW1.pdf', 'ablage', 'o1', '2024'),   # Titel normalisiert: vorhandener Ordner
    ('QM-System/1.4 QS/Firma B Reinigungsnachweise/KW1.pdf', 'ablage', (NEU, '1.4', 'Firma B Reinigungsnachweise'), ''),
    ('QM-System/_Firma B/Reinigungsnachweise/KW1.pdf', 'eingang', 'eingang', '_Firma B/Reinigungsnachweise'),
    ('QM-System/1.4 QS/~$1.4-F01.docx', 'system', None, None),
    ('QM-System/1.4 QS/.~lock.1.4-F01.docx#', 'system', None, None),
    ('QM-System/1.4 QS/1.4-F01 (1).pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 - Kopie.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01_ALT.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 Entwurf.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/1.4-F01 Temperaturkontrolle.pdf', 'nachtragen', 'd1', None),
    ('QM-System/1.4 QS/1.4-F01_Temperaturkontrolle.docx', 'nachtragen', 'd1', None),
    ('QM-System/1.4 QS/1.4-F01-Temperatur-Kontrolle.xlsx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    ('QM-System/1.4 QS/HACCP-Plan.pdf', 'nachtragen', 'd4', None),
    ('QM-System/1.4 QS/1.4-F02 Probenahme.pdf', 'dokument', 'd5', None),
    ('QM-System/1.4 QS/1.4-F01 Temperaturkontrolle/_ältere Versionen/Version 1/a.pdf', 'export', None, None),
    ('QM-System/1.4 QS/1.4-F01 Temperaturkontrolle/Messungen/a.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Temperaturkontrolle'), 'Messungen'),
    ('QM-System/1.4 QS/Befunde/2023/Labor A/Teil 1/Teil 2/tief.pdf', 'ablage', (NEU, '1.4', 'Befunde'), '2023/Labor A/Teil 1/Teil 2'),
    ('QM-System/Zertifikat.pdf', 'eingang', 'eingang', ''),
    ('QM-System/Dokumentenliste.csv', 'export', None, None),
    ('QM-System/1.4 QS/setup.exe', 'art', None, None),
    (('QM-System/1.4 QS/leer.pdf', 0), 'leer', None, None),
]
st, r, pl = plan(Q, [f[0] for f in FAELLE])
check('Plan: 200, Wurzel „QM-System“ weggelassen', st == 200 and r['wurzel'] == 'QM-System', (st, r.get('error'), r.get('wurzel')))
neu_titel = {f'neu:{i}': (n['kapitel'], n['titel']) for i, n in enumerate(r.get('neu', []))}


def ist(p):
    e = pl.get(p, {})
    z = e.get('ziel')
    return e.get('status'), (DOK.get(z) or ((NEU,) + neu_titel[z] if z in neu_titel else z)) if z else None, e.get('pfad') if e.get('status') in ('ablage', 'eingang') else None


for pfad_, status_, ziel_, p_ in FAELLE:
    schluessel = pfad_[0] if isinstance(pfad_, tuple) else pfad_
    erw = (status_, ziel_, p_)
    check(f'Regel: {schluessel} → {status_} {ziel_ or ""}', ist(schluessel) == erw, (ist(schluessel), erw, pl.get(schluessel)))
check('Plan: Gründe für Eingang und Art', pl['QM-System/Zertifikat.pdf'].get('grund') == 'lose Datei' and pl['QM-System/1.4 QS/setup.exe'].get('grund') == '.exe')
ob = {z['name']: z for z in r['oberste']}
check('oberste Ordner: Kapitelordner automatisch, andere Eingang mit Vorschlag für einen Bereich (nächste freie Nummer ab 90)', ob['1.4 QS']['art'] == 'auto' and ob['1.4 qs']['kapitel'] == '1.4'
      and ob['_Firma']['art'] == 'eingang' and ob['_Firma']['vorschlag'] == {'kapitel': '90', 'titel': 'Firma'} and ob['Handbuch']['vorschlag'] == {'kapitel': '90', 'titel': 'Handbuch'}, ob)
st, r2, pl2 = plan(Be, ['QM-System/1.4 QS/1.4-F01.pdf', 'QM-System/1.4 QS/1.4-F02 Probenahme.pdf'])
check('ohne Freigaberecht: gültige Version → Eingang mit Grund, Entwurf möglich', pl2['QM-System/1.4 QS/1.4-F01.pdf'] == {'status': 'eingang', 'ziel': 'eingang', 'pfad': '1.4 QS', 'grund': 'gültige Version nur mit Freigaberecht'}
      and pl2['QM-System/1.4 QS/1.4-F02 Probenahme.pdf']['status'] == 'dokument', pl2)
st, r2, pl2 = plan(Q, ['_Firma/HACCP/1.4 QS/1.4-F01.xlsx', '_Firma/x.pdf'])
check('gewählter „_“-Ordner bleibt oberster Ordner (nie per Nummer)', r2['wurzel'] == '' and pl2['_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['status'] == 'eingang', r2.get('oberste'))
st, r2, pl2 = plan(Q, ['HACCP/1.4 QS/1.4-F01.xlsx'])
check('Unterordner einer Fremdfirma gewählt (Grenze): Wurzel und erkannte Kapitel stehen im Plan, die Vorschau zeigt sie, Nachtragen nur mit Häkchen', r2['wurzel'] == 'HACCP'
      and r2['oberste'][0]['art'] == 'auto' and pl2['HACCP/1.4 QS/1.4-F01.xlsx']['status'] == 'nachtragen', r2)
st, r2, _ = plan(Q, ['1.4 QS/a.pdf', '1.4 QS/b.pdf'])
check('Kapitelordner selbst gewählt: bleibt erhalten', r2['wurzel'] == '' and r2['oberste'][0]['art'] == 'auto')

# ── Zuordnung oberster Ordner, Bereich ──
W = {'_Firma': {'art': 'neu', 'kapitel': '90', 'titel': 'Firma'}, 'Handbuch': {'art': 'kapitel', 'kapitel': '1.4'}, 'Firma B': {'art': 'aus'}}
check('neuer Bereich nur mit „verwalten“ (403)', plan(Q, [f[0] for f in FAELLE[:9]], W)[0] == 403)
st, r, pl = plan(V, [f[0] for f in FAELLE[:9]] + ['QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'QM-System/_Firma/1.4-F01.pdf'], W)
n_ = {f'neu:{i}': (n['kapitel'], n['titel']) for i, n in enumerate(r.get('neu', []))}
e1, e2, e3, e4 = (pl[p] for p in ('QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'QM-System/Handbuch/1.4 QS/1.4-F01.pdf', 'QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'QM-System/_Firma/1.4-F01.pdf'))
check('Bereich: Ordner-Dokument je Unterordner, nie per Nummer; direkt darin „Weitere Dateien“', st == 200 and r['bereiche'] == {'90': 'Firma'}
      and e1['status'] == 'ablage' and n_[e1['ziel']] == ('90', 'HACCP') and e1['pfad'] == '1.4 QS' and n_[e4['ziel']] == ('90', 'Weitere Dateien'), (r.get('error'), e1, e4))
check('von Hand einem Kapitel zugeordnet: Archiv, nie per Nummer', e2['status'] == 'ablage' and n_[e2['ziel']] == ('1.4', '1.4 QS') and e2['pfad'] == '', e2)
check('„nicht übernehmen“', e3 == {'status': 'aus'}, e3)
check('Bereich: Nummer schon vergeben, unbekanntes Kapitel → 422', plan(V, ['_Firma/a.pdf', 'X/b.pdf'], {'_Firma': {'art': 'neu', 'kapitel': '1.4', 'titel': 'X'}})[0] == 422
      and plan(V, ['_Firma/a.pdf', 'X/b.pdf'], {'_Firma': {'art': 'kapitel', 'kapitel': '7.7'}})[0] == 422)
st, r, pl = plan(V, [f[0] for f in FAELLE[:9]] + ['QM-System/_Firma/1.4-F01.pdf'], W, anlegen=True)
stamm = speicher('qs-stamm')['kapitel']
haccp = dok_titel('HACCP', '90')
check('anlegen: Bereich 90 (Kapitel mit „bereich“), Ordner-Dokumente, Plan mit ihren Kennungen', st == 200 and any(k['id'] == '90' and k.get('bereich') for k in stamm) and haccp
      and pl['QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['ziel'] == haccp['id'] and not any(e.get('ziel', '').startswith('neu:') for e in r['dateien']), (st, r.get('error')))
check('angelegte Ordner im Verlauf „angelegt (Ordner-Import)“', 'angelegt (Ordner-Import)' in json.dumps(haccp['verlauf'], ensure_ascii=False))
st, r, pl = plan(Q, ['_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'Y/a.pdf'], {'_Firma': {'art': 'kapitel', 'kapitel': '90'}})
check('Bereich danach wählbar, im Bereich weiter nie per Nummer, nie automatisch', pl['_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['ziel'] == haccp['id']
      and plan(Q, ['90 Firma/1.4-F01.pdf', 'Y/a.pdf'])[2]['90 Firma/1.4-F01.pdf']['status'] == 'eingang')

# ── Gebündeltes Eintragen ──
st, r, pl = plan(Q, ['QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf', 'QM-System/1.4 QS/Reinigungsnachweise/2023/KW2.pdf', 'QM-System/1.4 QS/1.4-F01.pdf',
                     'QM-System/1.4 QS/1.4-F02 Probenahme.pdf', 'QM-System/Lose.pdf'])
KW1, KW2 = pdf('KW1'), pdf('KW2')
ab_vorher = speicher('qs-ablage').get('rev', 0)
u1 = sammeln(Q, pl['QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf'], 'KW1.pdf', KW1)
check('sammeln: fertiger Upload bleibt liegen, noch nichts eingetragen', speicher('qs-ablage').get('rev', 0) == ab_vorher and glob.glob(os.path.join(ABLAGE, '.teile', u1 + '*')))
check('fremder Upload: Fehler, nichts eingetragen', Be.call('qs_import_eintragen', {'uploads': [u1]})[1]['uploads'][u1]['status'] == 'fehler' and speicher('qs-ablage').get('rev', 0) == ab_vorher)
u2 = sammeln(Q, pl['QM-System/1.4 QS/Reinigungsnachweise/2023/KW2.pdf'], 'KW2.pdf', KW2)
u3 = sammeln(Q, pl['QM-System/1.4 QS/1.4-F01.pdf'], '1.4-F01.pdf', pdf('F01 neu'))
u4 = sammeln(Q, pl['QM-System/1.4 QS/1.4-F02 Probenahme.pdf'], '1.4-F02 Probenahme.pdf', pdf('F02 Entwurf'))
u5 = sammeln(Q, {**pl['QM-System/Lose.pdf'], 'pfad': ''}, 'Lose.pdf', pdf('lose'))
verlauf_d1 = len(dok(D1['id'])['verlauf'])
st, r = Q.call('qs_import_eintragen', {'uploads': [u1, u2, u3, u4, u5, 'f' * 24]})
u = r.get('uploads', {})
check('ein Aufruf trägt alle ein (Archiv, gültige Version, Entwurf, Eingang); unbekannter Upload → Fehler', st == 200 and [u[x]['status'] for x in (u1, u2, u3, u4, u5)] == ['abgelegt'] * 5
      and u['f' * 24]['status'] == 'fehler', r)
a1 = {f['name']: f for f in archiv(O1)}
check('Archiv: Unterordner als pfad, ein Schreibvorgang für qs-ablage', a1['KW1.pdf']['pfad'] == '2023' and a1['KW2.pdf']['pfad'] == '2023' and speicher('qs-ablage')['rev'] == ab_vorher + 1, a1)
d1 = dok(D1['id']); g1 = [f for f in d1['versionen'][0]['dateien'] if f['name'] == '1.4-F01.pdf']
check('gültige Version: nachgetragen, ein Verlaufseintrag am Dokument', g1 and g1[0].get('nachgetragen') and len(d1['verlauf']) == verlauf_d1 + 1
      and d1['verlauf'][-1]['was'] == 'Datei zu Version 1 nachgetragen: 1.4-F01.pdf', d1['verlauf'][-1:])
d5 = dok(D5['id'])
check('Entwurf: wer hochgeladen hat, ist Bearbeiter (4-Augen-Prinzip)', ids['quinn'] in d5['versionen'][0]['bearbeiter'], d5['versionen'][0]['bearbeiter'])
u6 = sammeln(Q, pl['QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf'], 'KW1.pdf', KW1)
st, r = Q.call('qs_import_eintragen', {'uploads': [u6]})
check('gleiche Datei (Ziel, pfad, Name, Prüfsumme) → „vorhanden“, Datei wieder weg', r['uploads'][u6] == {'status': 'vorhanden', 'datei': a1['KW1.pdf']['id']} and len(archiv(O1)) == 2, r)
lid = next(i for i, f in eingang().items() if f['name'] == 'Lose.pdf')
Be.call('qs_eingang_loeschen', {'dateien': [lid]})
u7 = sammeln(Q, {**pl['QM-System/Lose.pdf'], 'pfad': ''}, 'Lose.pdf', pdf('lose'))
check('früher im Eingang gelöscht → „verworfen“, nicht wieder abgelegt', Q.call('qs_import_eintragen', {'uploads': [u7]})[1]['uploads'][u7]['status'] == 'verworfen'
      and not any(f['name'] == 'Lose.pdf' for f in eingang().values()))
O2 = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Gleich zu'})[1]['dokument']['id']
u8 = sammeln(Q, {'status': 'ablage', 'ziel': O2, 'pfad': 'Unter', 'herkunft': '1.4 QS/Gleich zu/Unter'}, 'Spaet.pdf', pdf('spät'))
Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Gleich zu', 'id': O2, 'rev': dok(O2)['rev'], 'eingezogen': True, 'einzugGrund': 'zu'})
u9 = sammeln(Be, {'status': 'nachtragen', 'ziel': D1['id'], 'ver': D1['versionen'][0]['id'], 'herkunft': '1.4 QS'}, '1.4-F01 Temperaturkontrolle.pdf', pdf('Bernd'))
r8 = Q.call('qs_import_eintragen', {'uploads': [u8]})[1]['uploads'][u8]; r9 = Be.call('qs_import_eintragen', {'uploads': [u9]})[1]['uploads'][u9]
e8 = eingang().get(r8.get('datei'), {})
check('Ziel inzwischen gesperrt → Eingang mit Grund und ganzem Ordnerpfad (Herkunft)', r8['status'] == 'eingang' and 'eingezogen' in r8['grund'] and e8.get('pfad') == '1.4 QS/Gleich zu/Unter', (r8, e8))
check('gültige Version ohne Freigaberecht → Eingang', r9['status'] == 'eingang' and 'freigeben' in r9['grund'], r9)
check('Bündel: höchstens 100 Uploads, nur Text → 422; nur ansehen 403', Q.call('qs_import_eintragen', {'uploads': [f'{i:024x}' for i in range(101)]})[0] == 422
      and Q.call('qs_import_eintragen', {'uploads': [1]})[0] == 422 and L.call('qs_import_eintragen', {'uploads': [u1]})[0] == 403 and L.call('qs_sammel_plan', {'ordner': []})[0] == 403)
check('keine Reste unter .teile', not [x for x in glob.glob(os.path.join(ABLAGE, '.teile', '*')) if any(u_ in x for u_ in (u1, u2, u3, u4, u5, u6, u7, u8, u9))])

# ── Fortsetzen: der Plan erkennt Abgelegtes – auch Dateien, die aus dem Eingang zugeordnet wurden ──
st, r, pl = plan(Q, [('QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf', len(KW1)), ('QM-System/1.4 QS/Reinigungsnachweise/2023/KW3.pdf', 10),
                     ('QM-System/1.4 QS/1.4-F01.pdf', len(pdf('F01 neu'))), ('QM-System/Notizen/a.pdf', len(pdf('Notiz')))])
check('erneuter Plan: abgelegte Datei „schon da“, neue nicht', pl['QM-System/1.4 QS/Reinigungsnachweise/2023/KW1.pdf'].get('schonDa') and not pl['QM-System/1.4 QS/Reinigungsnachweise/2023/KW3.pdf'].get('schonDa')
      and pl['QM-System/1.4 QS/1.4-F01.pdf'].get('schonDa'), pl)
un = sammeln(Q, pl['QM-System/Notizen/a.pdf'], 'a.pdf', pdf('Notiz'))
nid = Q.call('qs_import_eintragen', {'uploads': [un]})[1]['uploads'][un]['datei']
Be.call('qs_datei_zuordnen', {'dateien': [nid], 'dokument': O1})
check('aus dem Eingang zugeordnet: der Plan erkennt sie trotzdem (Befund 5)', plan(Q, [('QM-System/Notizen/a.pdf', len(pdf('Notiz'))), 'QM-System/x/y.pdf'])[2]['QM-System/Notizen/a.pdf'].get('schonDa'))

# ── Grenzen ──
check('höchstens 30 000 Dateien je Lauf (422)', Q.call('qs_sammel_plan', {'ordner': [['A', [[f'{i}.pdf', 1] for i in range(30001)]]]})[0] == 422)
ab = speicher('qs-ablage')
ab['liste'] += [{'id': f'fuellung{i:012d}', 'name': f'F{i}.pdf', 'art': 'pdf', 'mime': 'application/pdf', 'groesse': 1, 'sha256': '0' * 64,
                 'hochgeladen': {'t': '2026-11-01T08:00:00+01:00', 'von': 'Test', 'vonId': 'test'}, 'ziel': O1} for i in range(10000 - len(archiv(O1)))]
storage_write('qs-ablage', ab)
e_ = plan(Q, ['1.4 QS/Reinigungsnachweise/neu.pdf', 'X/y.pdf'])[2]['1.4 QS/Reinigungsnachweise/neu.pdf']
check('Ordner voll (10 000) → der Plan legt in den Eingang', e_['status'] == 'eingang' and e_['grund'] == 'Ordner voll', e_)
check('Hochladen in einen vollen Ordner → 422', hochladen(Be, O1, '', 'Zuviel.pdf', pdf('zu viel'))[0] == 422)
ab['liste'] = [f for f in ab['liste'] if not f['id'].startswith('fuellung')]
storage_write('qs-ablage', ab)

# ── Ältere Dateien am Ordner (GR-006: dateien in qs-dokumente ohne pfad) ──
alt_id = hochladen(Be, 'eingang', '', 'Alt-Zertifikat.pdf', pdf('alt'))[1]['datei']
ab = speicher('qs-ablage'); alt = next(f for f in ab['liste'] if f['id'] == alt_id)
ab['liste'] = [f for f in ab['liste'] if f['id'] != alt_id]; storage_write('qs-ablage', ab)
d_ = speicher('qs-dokumente'); x_ = next(x for x in d_['liste'] if x['id'] == O1)
x_['dateien'] = [{k: v for k, v in alt.items() if k not in ('ziel', 'pfad')}]; storage_write('qs-dokumente', d_)
a1 = {f['name']: f for f in archiv(O1)}
check('ältere Datei am Ordner: im Baum (ohne pfad), Download, Plan erkennt sie', a1['Alt-Zertifikat.pdf']['pfad'] == '' and roh(L, 'qs_datei&id=' + alt_id) == (200, pdf('alt'))
      and plan(Q, [('1.4 QS/Reinigungsnachweise/Alt-Zertifikat.pdf', len(pdf('alt'))), 'X/y.pdf'])[2]['1.4 QS/Reinigungsnachweise/Alt-Zertifikat.pdf'] != {}
      and plan(Q, [('1.4 QS/Alt-Zertifikat.pdf', 1), ('1.4 QS/Reinigungsnachweise/Alt-Zertifikat.pdf', len(pdf('alt')))])[2]['1.4 QS/Reinigungsnachweise/Alt-Zertifikat.pdf'].get('schonDa'))

# ── Ordnerbaum, ZIP je Unterordner, ZIP-Export ──
st, z = roh(L, f'qs_archiv_zip&dok={O1}&pfad=2023')
namen = sorted(zipfile.ZipFile(io.BytesIO(z)).namelist()) if st == 200 else []
check('ZIP eines Unterordners: Aufbau Ordner/pfad/Datei, nur dieser Unterordner, Inhalt gleich', namen == ['Reinigungsnachweise/2023/KW1.pdf', 'Reinigungsnachweise/2023/KW2.pdf']
      and zipfile.ZipFile(io.BytesIO(z)).read('Reinigungsnachweise/2023/KW1.pdf') == KW1, (st, namen))
st, z = roh(L, f'qs_archiv_zip&dok={O1}')
check('ZIP des ganzen Ordners mit älterer Datei', st == 200 and 'Reinigungsnachweise/Alt-Zertifikat.pdf' in zipfile.ZipFile(io.BytesIO(z)).namelist())
check('Ordnerbaum und ZIP: unbekanntes Dokument 404, leerer Unterordner 404, ohne Anmeldung kein Zugang', L.call('qs_archiv&dok=dnix')[0] == 404
      and roh(L, f'qs_archiv_zip&dok={O1}&pfad=gibtsnicht')[0] == 404 and Client('198.51.100.40').call(f'qs_archiv&dok={O1}')[0] in (401, 403, 404))
st, z = roh(L, 'qs_ablage_export')
namen = zipfile.ZipFile(io.BytesIO(z)).namelist()
check('ZIP-Export des QM-Systems: Archivdateien mit Unterordnern, ältere am Ordner, nichts aus dem Eingang', 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2023/KW1.pdf' in namen
      and 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/Alt-Zertifikat.pdf' in namen and not any('Spaet.pdf' in n for n in namen), [n for n in namen if 'Reinigung' in n])
kw2 = next(f for f in archiv(O1) if f['name'] == 'KW2.pdf')['id']
check('Archivdatei entfernen: nur mit Grund, dann vermerkt (nicht gelöscht), nicht im Export', Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': ''})[0] == 422
      and Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': 'doppelt'})[0] == 200 and next(f for f in archiv(O1) if f['id'] == kw2)['entfernt']['grund'] == 'doppelt'
      and os.path.isfile(blob_pfad(kw2)) and roh(L, 'qs_datei&id=' + kw2)[0] == 404 and Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': 'x'})[0] == 409)
check('ältere Datei am Ordner entfernen (vermerkt in qs-dokumente)', Be.call('qs_datei_entfernen', {'datei': alt_id, 'grund': 'ersetzt'})[0] == 200
      and next(f for f in archiv(O1) if f['id'] == alt_id).get('entfernt'))
st, r = L.call('qs_start')
check('qs_start: Zahl und Bytes je Ordner aus qs-ablage-zahlen', r['ablageZahlen'][O1] == {'dateien': 2, 'bytes': len(KW1) + len(pdf('Notiz'))}, r['ablageZahlen'].get(O1))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Ordner-Import mit Anzahl, ohne Datei- und Ordnernamen', 'Ordner-Import: 5 Dateien abgelegt' in log and 'Ordner-Dokumente und 1 Bereiche angelegt' in log
      and 'KW1.pdf' not in log and 'Reinigungsnachweise (Unterordner)' in log and '2023' not in log.split('Reinigungsnachweise (Unterordner)')[0][-200:], log[-1500:])

# ── Oberfläche ──
tmp = tempfile.mkdtemp(prefix='qs-import-')
QMS = os.path.join(tmp, 'QM-System')
DATEIEN = {'1.4 Qualitätssicherung/1.4-F01 Temperaturkontrolle.pdf': pdf('F01 Fassung'),            # gültige Version → nur mit Häkchen
           '1.4 Qualitätssicherung/1.4-F02 Probenahme.docx': b'MZ' + pdf('F02 neu'),   # Inhalt passt nicht: Fehler, Lauf geht weiter
           '1.4 Qualitätssicherung/1.4-F02 Probenahme.pdf': pdf('F02 Entwurf 2'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Januar/KW1.pdf': pdf('2025 KW1'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Januar/KW2.pdf': pdf('2025 KW2'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Februar/KW5.pdf': pdf('2025 KW5'),
           '1.4 Qualitätssicherung/_alt/1.4-F01 alt.pdf': pdf('F01 alt'),
           '2.2 Lager/Temperaturlisten/2025/Juli.pdf': pdf('Juli'),
           '_Matthies Fleischwaren/HACCP-Matthies/1.4 Qualitätssicherung/1.4-F01.pdf': pdf('Matthies'),
           '_in Bearbeitung/Entwurf Hygieneplan.pdf': pdf('Hygiene'),
           'Zertifikat IFS.pdf': pdf('IFS'), '.DS_Store': b'\0\0', 'Sonstiges/setup.exe': b'MZ' + b'\0' * 50}
for pfad_, inhalt in DATEIEN.items():
    os.makedirs(os.path.dirname(os.path.join(QMS, pfad_)), exist_ok=True)
    with open(os.path.join(QMS, pfad_), 'wb') as f_:
        f_.write(inhalt)

with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ')

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/qs/#dokumente'); pg.wait_for_selector('#qm-app:not([hidden])')
        return ctx, pg

    def ohne_scrollen(pg, dlg):
        return pg.evaluate("s => { const d = document.querySelector(s); return d.scrollWidth <= d.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; }", dlg)

    def zahl(pg, n):
        return pg.evaluate("n => { const d = [...document.querySelectorAll('#im-zahlen div')].find(x => x.querySelector('span').textContent === n); return d ? Number(d.querySelector('b').textContent.replace(/\\./g, '')) : -1; }", n)

    def zeilen(pg):
        return pg.evaluate("Object.fromEntries([...document.querySelectorAll('#im-liste tbody tr')].filter(t => t.querySelector('.qm-name')).map(t => [t.querySelector('.qm-name').textContent, t.querySelector('.qm-sa-status').textContent.trim()]))")

    def oberste(pg):
        return pg.evaluate("Object.fromEntries([...document.querySelectorAll('#im-oberste tbody tr')].map(t => [t.querySelector('.qm-name').textContent, t.querySelector('.qm-im-wahl').textContent.trim()]))")

    def warte_ende(pg):
        pg.wait_for_function("!document.querySelector('#im-csv').hidden")

    ctx, pg = anmelden('vera', 'Verwalt-Konto-90', '198.51.100.13')
    pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
    pg.set_input_files('#im-ordner', QMS)
    pg.wait_for_selector('#im-liste tr .qm-name')
    check('Vorschau: gewählter Ordner, erkannte Kapitel, Warnung', 'Gewählter Ordner: QM-System' in text(pg, '#im-wurzel') and 'erkannte Kapitel: 1.4, 2.2' in text(pg, '#im-wurzel')
          and pg.is_visible('#im-warnung'), (text(pg, '#im-wurzel'), pg.evaluate("(() => { const w = document.querySelector('#im-warnung'); return [w.hidden, getComputedStyle(w).display, w.textContent.length]; })()")))
    ob_ = oberste(pg)
    check('Vorschau: Kapitelordner erkannt, andere mit Auswahl (Vorgabe Eingang), lose Dateien in den Eingang', 'Kapitel 1.4' in ob_.get('1.4 Qualitätssicherung', '') or '1.4 Qualitätssicherung' in ob_.get('1.4 Qualitätssicherung', '')
          and pg.input_value('#im-oberste [data-im-wahl="_Matthies Fleischwaren"]') == 'eingang' and ob_.get('lose Dateien') == 'Eingang', ob_)
    check('Häkchen für gültige Versionen: Vorgabe aus, mit Zahl', pg.is_visible('#im-nachtragen') and not pg.is_checked('#im-nachtragen-an')
          and text(pg, '#im-nachtragen-text') == '1 Datei als aktuelle Fassung in gültige Versionen nachtragen', text(pg, '#im-nachtragen-text'))
    z_ = zeilen(pg)
    check('Vorschau je Datei: Archiv, Entwurf, Eingang, übersprungen', z_.get('KW5.pdf') == 'ins Archiv' and z_.get('1.4-F02 Probenahme.pdf') == 'in den Entwurf'
          and z_.get('Zertifikat IFS.pdf') == 'in den Eingang · lose Datei' and z_.get('.DS_Store') == 'Systemdatei' and z_.get('setup.exe', '').startswith('Dateiart'), z_)
    pg.select_option('#im-oberste [data-im-wahl="_Matthies Fleischwaren"]', 'neu')
    pg.wait_for_selector('#im-oberste [data-im-nr="_Matthies Fleischwaren"]')
    check('neuer Bereich: Nummer und Titel vorgeschlagen, Plan zählt ihn', pg.input_value('#im-oberste [data-im-nr="_Matthies Fleischwaren"]') == '91'
          and pg.input_value('#im-oberste [data-im-titel="_Matthies Fleischwaren"]') == 'Matthies Fleischwaren' and zahl(pg, 'neue Bereiche') == 1, zahl(pg, 'neue Bereiche'))
    neu_ = zahl(pg, 'neu')
    pg.screenshot(path=os.path.join(SH, 'qs_import_vorschau_1280.png'), full_page=True)
    pg.evaluate("""() => { const f = window.fetch; window.__weiter = new Promise((ok) => { window.__frei = ok; });
      window.fetch = async (...a) => { if (String(a[0]).includes('qs_import_eintragen') && !window.__gehalten) { window.__gehalten = true; await window.__weiter; } return f(...a); }; }""")
    pg.click('#im-los')
    pg.wait_for_function("document.querySelector('#im-stand').textContent.includes('von')")
    pg.wait_for_function("[...document.querySelectorAll('#im-liste .qm-sa-status')].some(t => t.textContent.includes('wird eingetragen'))")
    check('Lauf: Fortschritt mit Dateien und Größe, Abbrechen sichtbar, Auswahl gesperrt', ' von ' in text(pg, '#im-stand') and 'KB' in text(pg, '#im-stand') and pg.is_visible('#im-stopp') and pg.is_disabled('#im-oberste select'))
    pg.screenshot(path=os.path.join(SH, 'qs_import_fortschritt_1280.png'), full_page=True)
    pg.evaluate('window.__frei()')
    warte_ende(pg)
    z_ = zeilen(pg)
    meldung = text(pg, '#im-meldung')
    check('Bericht: abgelegt, im Eingang, Fehler hält den Lauf nicht an', z_.get('KW5.pdf') == 'abgelegt' and z_.get('1.4-F01 Temperaturkontrolle.pdf') == 'im Eingang'
          and 'passt nicht' in z_.get('1.4-F02 Probenahme.docx', '') and z_.get('Juli.pdf') == 'abgelegt' and 'Dateien abgelegt' in meldung, (meldung, z_))
    pg.screenshot(path=os.path.join(SH, 'qs_import_bericht_1280.png'), full_page=True)
    with pg.expect_download() as dl:
        pg.click('#im-csv')
    zeilen_csv = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8-sig').read()), delimiter=';'))
    check('Bericht als CSV: eine Zeile je Datei mit Ergebnis und Ziel', dl.value.suggested_filename.startswith('QM-Ordner-Import_') and len(zeilen_csv) == len(DATEIEN) + 1
          and ['QM-System/2.2 Lager/Temperaturlisten/2025', 'Juli.pdf', str(len(pdf('Juli'))), 'abgelegt', 'Temperaturlisten'] in [z[:5] for z in zeilen_csv], zeilen_csv[:4])
    rn = {f['name']: f for f in archiv(O1)}
    tl = dok_titel('Temperaturlisten', '2.2'); mh = dok_titel('HACCP-Matthies', '91')
    check('Server: Ordnerstruktur erhalten, Bereich 91 mit Ordner der Fremdfirma, gültige Version ohne Häkchen unberührt',
          rn['KW1.pdf']['pfad'] == '2025/Januar' and rn['KW5.pdf']['pfad'] == '2025/Februar' and tl and [f['pfad'] for f in archiv(tl['id'])] == ['2025']
          and mh and [f['pfad'] for f in archiv(mh['id'])] == ['1.4 Qualitätssicherung'] and not any(f['name'] == '1.4-F01 Temperaturkontrolle.pdf' for f in dok(D1['id'])['versionen'][0]['dateien'])
          and any(f['name'] == '1.4-F01 Temperaturkontrolle.pdf' and f['pfad'] == '1.4 Qualitätssicherung' for f in eingang().values()), (rn, tl, mh))
    pg.eval_on_selector('#im-ordner', 'e => { e.value = ""; }')
    pg.set_input_files('#im-ordner', QMS)
    pg.wait_for_function("document.querySelector('#im-liste tr .qm-name') && !document.querySelector('#im-csv').offsetParent")
    z_ = zeilen(pg)
    check('denselben Ordner noch einmal: Abgelegtes „schon abgelegt“, offen nur der Fehler', z_.get('KW5.pdf') == 'schon abgelegt' and z_.get('1.4-F01 Temperaturkontrolle.pdf') == 'schon abgelegt'
          and z_.get('Entwurf Hygieneplan.pdf') == 'schon abgelegt' and text(pg, '#im-los') == '1 Datei importieren', (z_, text(pg, '#im-los')))
    pg.click('#dlg-import .qm-knopfreihe [data-im-zu]'); pg.wait_for_selector('#dlg-import', state='hidden')
    ctx.close()

    # Abbruch: der erste Upload wird festgehalten, bis „Abbrechen“ gedrückt ist; danach Neuladen und fortsetzen
    NACHW = os.path.join(tmp, 'Nachweise')
    for k in (1, 2, 3, 4):
        os.makedirs(os.path.join(NACHW, 'Labor A'), exist_ok=True)
        with open(os.path.join(NACHW, 'Labor A', f'Befund {k}.pdf'), 'wb') as f_:
            f_.write(pdf(f'Befund {k}'))
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
    pg.set_input_files('#im-ordner', NACHW)
    pg.wait_for_function("document.querySelector('#im-los').textContent.startsWith('4 ')")
    check('ohne „verwalten“ kein neuer Bereich', pg.locator('#im-oberste option[value="neu"]').count() == 0)
    pg.evaluate("""() => { const f = window.fetch; window.__weiter = new Promise((ok) => { window.__frei = ok; });
      window.fetch = async (...a) => { if (String(a[0]).includes('qs_datei_hochladen')) await window.__weiter; return f(...a); }; }""")
    pg.click('#im-los'); pg.wait_for_selector('#im-stopp:not([hidden])'); pg.click('#im-stopp'); pg.evaluate('window.__frei()')
    warte_ende(pg)
    check('abgebrochen: die drei laufenden Dateien fertig, der Rest nicht hochgeladen', '3 im Eingang' in text(pg, '#im-meldung') and 'abgebrochen, 1 nicht hochgeladen' in text(pg, '#im-meldung'), text(pg, '#im-meldung'))
    ctx.close()
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
    pg.set_input_files('#im-ordner', NACHW)
    pg.wait_for_selector('#im-liste tr .qm-name')
    offen = int(text(pg, '#im-los').split()[0])
    check('nach Neuladen: nur der Rest ist offen', offen == 1, text(pg, '#im-los'))
    pg.click('#im-los'); warte_ende(pg)
    befunde = sorted((f['name'], f['pfad']) for f in eingang().values() if f['name'].startswith('Befund '))
    check('fortgesetzt: jede Datei genau einmal im Eingang, Pfad ohne den gewählten Ordner', befunde == [(f'Befund {k}.pdf', 'Labor A') for k in (1, 2, 3, 4)], befunde)
    ctx.close()

    # Ordnerbaum in der Seitenleiste
    for user, pw, ip, breite, thema in (('bernd', 'Bearbeit-Konto-34', '198.51.100.11', 1280, 'light'), ('lisa', 'Leserin-Konto-12', '198.51.100.10', 390, 'light'),
                                        ('lisa', 'Leserin-Konto-12', '198.51.100.10', 390, 'dark'), ('bernd', 'Bearbeit-Konto-34', '198.51.100.11', 1280, 'dark')):
        ctx, pg = anmelden(user, pw, ip, breite, thema, 844 if breite < 500 else 900)
        pg.click(f'#qm-d-liste tr[data-dok="{O1}"]'); pg.wait_for_selector('#dk-baum .qm-baum-ordner')
        if user == 'bernd' and thema == 'light':
            check('Liste: Zahl der Dateien des Ordners aus qs_start', '5' in text(pg, f'#qm-d-liste tr[data-dok="{O1}"] .qm-anz'), text(pg, f'#qm-d-liste tr[data-dok="{O1}"]'))
            check('Baum: oberste Unterordner mit Zahl und ZIP, entfernte als Vermerk', pg.locator('#dk-baum-inhalt > .qm-baum-ordner').count() == 3
                  and pg.locator('#dk-baum-inhalt > .qm-baum-ordner .qm-baum-zip').count() == 3 and '2 Dateien entfernt' in text(pg, '#dk-baum'), text(pg, '#dk-baum'))
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] .qm-datei-name:has-text("KW2.pdf")')
            check('Baum: Unterordner füllen sich beim Aufklappen, Dateien mit Entfernen', pg.locator('#dk-baum [data-pfad="2025/Januar"] [data-datei-weg]').count() == 2)
            with pg.expect_download() as dl:
                pg.click('#dk-baum [data-pfad="2025/Januar"] .qm-datei-name:has-text("KW2.pdf")')
            check('Baum: Herunterladen über einen direkten Link', dl.value.suggested_filename == 'KW2.pdf' and open(dl.value.path(), 'rb').read() == pdf('2025 KW2'))
            with pg.expect_download() as dl:
                pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] > summary .qm-baum-zip')
            check('Baum: Unterordner als ZIP', sorted(zipfile.ZipFile(dl.value.path()).namelist()) == ['Reinigungsnachweise/2025/Januar/KW1.pdf', 'Reinigungsnachweise/2025/Januar/KW2.pdf'])
            pg.fill('#dk-baum-suche', 'KW5')
            pg.wait_for_function("document.querySelectorAll('#dk-baum-inhalt .qm-datei').length === 1")
            check('Suche: Treffer mit Ordnerpfad', '2025 / Februar' in text(pg, '#dk-baum-inhalt'))
            pg.fill('#dk-baum-suche', '')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025"]')
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
        else:
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
            if user == 'lisa':
                check(f'{breite}px {thema}: nur ansehen – Baum ohne Entfernen und Ablagefeld, kein Import', pg.locator('#dk-baum [data-datei-weg]').count() == 0
                      and pg.locator('#qm-dk .qm-drop').count() == 0 and pg.is_hidden('#qm-d-import'))
        check(f'{breite}px {thema}: Ordnerbaum ohne waagerechtes Scrollen', ohne_scrollen(pg, '#qm-dk'))
        pg.screenshot(path=os.path.join(SH, f'qs_ordnerbaum_{user}_{breite}_{thema}.png'))
        ctx.close()
    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('vera', 'Verwalt-Konto-90', '198.51.100.13', breite, thema, 844 if breite < 500 else 900)
        pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
        pg.set_input_files('#im-ordner', QMS)
        pg.wait_for_selector('#im-liste tr .qm-name')
        check(f'{breite}px {thema}: Vorschau ohne waagerechtes Scrollen', ohne_scrollen(pg, '#dlg-import'))
        pg.screenshot(path=os.path.join(SH, f'qs_import_vorschau_{breite}_{thema}.png'))
        ctx.close()
    shutil.rmtree(tmp, ignore_errors=True)
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
