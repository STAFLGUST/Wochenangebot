"""Qualitätssicherung – Dokumentenablage (QM-System Bauabschnitt 2): Dateien je Version gelenkter Dokumente bzw. am Ordner,
gespeichert über die Dateiablage des Plattformkerns (app/api/lib/dateiablage.php), mit ZIP-Export „QM-System/…“.

Geprüft: Rechte serverseitig (GR-103: ohne Anmeldung, ohne QM-Recht, ansehen, bearbeiten, freigeben; CSRF; GET auf schreibende
Aktion); Hochladen in Teilen (ein Teil, mehrere Teile, Reihenfolge, fremder Nutzer, anderes Ziel, abgelaufen nach 24 Stunden,
Teil zu groß, Datei zu groß, leer, größer als angegeben, Prüfsumme, Endung nicht erlaubt, Inhalt passt nicht zur Endung,
Dateiname ohne Pfad und verbotene Zeichen); Regeln je Zustand (Entwurf mit „bearbeiten“ und 4-Augen-Prinzip, in Prüfung
gesperrt, freigegebene und ersetzte Versionen nur mit „freigeben“ nachtragen/entfernen mit Grund, verworfen und eingezogen
gesperrt, Ordner ohne Versionen, höchstens 50 Dateien, Ordner mit Dateien wird nicht gelenkt); Entfernen (Entwurf endgültig
gelöscht, sonst nur vermerkt, doppelt 409, veralteter Stand 409); Download (Kopfzeilen attachment/nosniff/sandbox, UTF-8-Name,
Inhalt gleich, entfernt/unbekannt 404, fehlende Datei 404); ZIP (Aufbau QM-System/<Kapitel>/<Dokument>/<Datei>, Dokumentenliste,
gültige Version, mit „alle“ ältere Versionen/Entwurf/eingezogen, Kapitelfilter, gleiche Namen, fehlende Datei in Hinweise.txt,
UTF-8-Namen, unbekanntes Kapitel 422); Datenpaket ersetzt nicht mehr, sobald Dateien liegen; Speicherung (.bin unter
data/dateien/qs/, keine Reste unter .teile, auch mit SQLite im Dateisystem); Protokoll ohne Dateinamen und Gründe;
Oberfläche (Ablegen per Dateiauswahl und per Ziehen, Fortschritt in Teilen, Fehler je Datei, ungespeicherte Stichworte bleiben,
Herunterladen, Entfernen mit/ohne Grund, Nachtragen mit „freigeben“, Büroklammer in der Liste, Export-Dialog mit Umfang,
nur ansehen ohne Ablagefelder, 1280/390 px hell und dunkel ohne waagerechtes Scrollen, keine JavaScript-Fehler).
Nur erfundene Testdaten.
"""
import base64
import datetime
import glob
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH, storage_raw, storage_sqlite

PW = 'Sicheres-Passwort-1'
HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
UDATA = os.environ['UDATA']
ABLAGE = os.path.join(UDATA, 'dateien')
HEUTE = datetime.date.today().isoformat()
MB = 1024 * 1024
TEIL = 3 * MB
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


# Erfundene Dateien mit passendem Dateikopf
def pdf(text, groesse=0):
    kopf = b'%PDF-1.4\n% ' + text.encode() + b'\n'
    return kopf + b'x' * max(0, groesse - len(kopf) - 6) + b'\n%%EOF'


def docx(text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>'); z.writestr('word/document.xml', '<w:document>' + text + '</w:document>')
    return b.getvalue()


XLS = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1' + b'\0' * 504
PNG = b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + b'\0' * 20


def blob_pfad(did):
    return os.path.join(ABLAGE, 'qs', did[:2], did + '.bin')


def blobs():
    return sorted(glob.glob(os.path.join(ABLAGE, 'qs', '*', '*.bin')))


def teile_reste():
    return glob.glob(os.path.join(ABLAGE, '.teile', '*'))


def hochladen(cli, dok, ver, name, inhalt, teil=TEIL, sha=None, groesse=None, nur_erster=False):
    """Datei in Teilen hochladen wie die Oberfläche; Rückgabe (Status, Antwort des letzten Aufrufs, Zahl der Aufrufe)"""
    upload, pos, nr, n = '', 0, 0, 0
    pruef = hashlib.sha256(inhalt).hexdigest() if sha is None else sha
    while True:
        stueck = inhalt[pos:pos + teil]
        st, r = cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt) if groesse is None else groesse,
                                                'sha256': pruef, 'upload': upload, 'teil': nr, 'daten': base64.b64encode(stueck).decode()})
        n += 1
        if st != 200 or r.get('fertig') or nur_erster:
            return st, r, n
        upload = r['upload']; pos += len(stueck); nr += 1


def teil_senden(cli, dok, ver, name, groesse, upload, nr, stueck, sha=''):
    return cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': groesse, 'sha256': sha, 'upload': upload, 'teil': nr,
                                           'daten': base64.b64encode(stueck).decode()})


def roh(cli, query):
    """GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)"""
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def zip_lesen(inhalt):
    z = zipfile.ZipFile(io.BytesIO(inhalt))
    return z, {i.filename: i for i in z.infolist()}


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('fritz', 'Fritz Freigabe', 'editor', 'Freigabe-Konto-78', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, F, V, O, N = K['lisa'], K['bernd'], K['quinn'], K['fritz'], K['vera'], K['otto'], Client('198.51.100.30')
check('Testfreigabe und Tester', A.call('modul_freigabe_save', {'bereich': 'qs.intern', 'freigabe': 'test', 'grund': 'Abnahme Dokumentenablage'})[0] == 200
      and A.call('modul_tester_save', {'bereich': 'qs.intern', 'tester': [ids[x] for x in ('admin', 'lisa', 'bernd', 'quinn', 'fritz', 'vera', 'otto')], 'grund': 'Abnahme'})[0] == 200)
KAP = [{'id': '1.4', 'titel': 'Qualitätssicherung', 'zustaendig': 'QB'}, {'id': '2.1', 'titel': 'Einkauf / Wareneingang', 'zustaendig': 'QB'}]
PERS = [{'id': 'QB', 'name': 'Quinn Beispiel', 'funktion': 'QMB', 'mitarbeiter': ids['quinn']}]
check('Kapitel und Personen', V.call('qs_stamm_save', {'kapitel': KAP, 'personen': PERS})[0] == 200)

st, r = L.call('qs_start')
check('Start: Einstellungen der Ablage (Endungen, 25 MB je Datei, Teile zu 3 MB, 50 Dateien)', st == 200 and r['ablage']['max'] == 25 * MB and r['ablage']['teil'] == TEIL
      and r['ablage']['dateien'] == 50 and {'pdf', 'docx', 'xlsx', 'xls', 'msg', 'png', 'jpg'} <= set(r['ablage']['arten']) and 'exe' not in r['ablage']['arten'] and 'php' not in r['ablage']['arten'], r.get('ablage'))


def dok(did, cli=None):
    return {x['id']: x for x in (cli or L).call('qs_start')[1]['dokumente']}[did]


def schritt(cli, did, s, **extra):
    return cli.call('qs_version_schritt', {'dokument': did, 'rev': dok(did)['rev'], 'schritt': s, **extra})


st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F01', 'titel': 'Probenahmeprotokoll', 'zustaendig': 'QB'})
D1 = r['dokument']['id']; V1 = r['dokument']['versionen'][0]['id']
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Lieferantenzertifikate', 'ablage': 'https://intranet.example/zertifikate'})
O1 = r['dokument']['id']
check('Gelenktes Dokument (Entwurf) und Ordner angelegt', D1 and V1 and O1)

# ── Rechte ──
klein = pdf('Probenahme')
check('Hochladen: ohne Anmeldung kein Zugang (401/403/404)', hochladen(N, D1, V1, 'a.pdf', klein)[0] in (401, 403, 404))
check('Hochladen: ohne QM-Recht 403', hochladen(O, D1, V1, 'a.pdf', klein)[0] == 403)
check('Hochladen: nur ansehen 403', hochladen(L, D1, V1, 'a.pdf', klein)[0] == 403)
ohne_csrf = Client('198.51.100.40'); ohne_csrf.call('login', {'username': 'bernd', 'password': NUTZER[1][3]}); ohne_csrf.csrf = 'falsch'
check('Hochladen ohne gültiges CSRF-Token: 403', hochladen(ohne_csrf, D1, V1, 'a.pdf', klein)[0] == 403)
check('schreibende Aktion per GET: 405', Be.call('qs_datei_hochladen')[0] == 405 and Be.call('qs_datei_entfernen')[0] == 405)
check('Download/Export: ohne QM-Recht 403, ohne Anmeldung kein Zugang', roh(O, 'qs_datei&id=abcdefabcdefabcdefab')[0] == 403 and roh(O, 'qs_ablage_export')[0] == 403
      and roh(N, 'qs_ablage_export')[0] in (401, 403, 404))

# ── Prüfungen beim ersten Teil ──
for name, args, code, text in (
        ('unbekanntes Dokument', ('dnix', V1, 'a.pdf', klein), 404, ''),
        ('unbekannte Version', (D1, 'vnix', 'a.pdf', klein), 404, ''),
        ('Ordner mit Version', (O1, V1, 'a.pdf', klein), 422, 'keine Versionen'),
        ('gelenktes Dokument ohne Version', (D1, '', 'a.pdf', klein), 404, ''),
        ('Endung .exe', (D1, V1, 'setup.exe', b'MZ' + b'\0' * 100), 422, 'nicht erlaubt'),
        ('Endung .php', (D1, V1, 'test.php', b'<?php echo 1;'), 422, 'nicht erlaubt'),
        ('ohne Endung', (D1, V1, 'Protokoll', klein), 422, 'nicht erlaubt'),
        ('Name nur Punkte', (D1, V1, '...', klein), 422, ''),
        ('leere Datei', (D1, V1, 'leer.pdf', b''), 422, 'leer')):
    st, r, _ = hochladen(Be, *args)
    check(f'Hochladen: {name} → {code}', st == code and (not text or text in r.get('error', '')), (st, r))
st, r = teil_senden(Be, D1, V1, 'gross.pdf', 25 * MB + 1, '', 0, b'%PDF-')
check('Datei über 25 MB → 422 (schon beim ersten Teil)', st == 422 and '25 MB' in r.get('error', ''), r)
st, r = teil_senden(Be, D1, V1, 'a.pdf', 4 * MB, '', 0, b'%PDF-' + b'x' * TEIL)
check('Teil über 3 MB → 422', st == 422 and 'Teil zu groß' in r.get('error', ''), r)
st, r = teil_senden(Be, D1, V1, 'a.pdf', 100, '', 1, b'%PDF-')
check('Upload beginnt nicht mit Teil 0 → 422', st == 422 and 'ersten Teil' in r.get('error', ''), r)
st, r = Be.call('qs_datei_hochladen', {'dokument': D1, 'version': V1, 'name': 'a.pdf', 'groesse': 10, 'upload': '', 'teil': 0, 'daten': '***kein base64***'})
check('Daten kein Base64 → 422', st == 422, r)
st, r = Be.call('qs_datei_hochladen', {'dokument': D1, 'version': V1, 'name': 'a.pdf', 'groesse': 10, 'upload': '', 'teil': '0', 'daten': ''})
check('Teil als Text → 422', st == 422, r)
st, r = teil_senden(Be, D1, V1, 'a.pdf', 10, '', 0, b'%PDF-' + b'x' * 20)
check('mehr Daten als angegeben → 422', st == 422 and 'größer als angegeben' in r.get('error', ''), r)
st, r, _ = hochladen(Be, D1, V1, 'Bericht.pdf', b'MZ\x90\0' + b'\0' * 200)
check('Programm mit Endung .pdf → 422 (Inhalt passt nicht)', st == 422 and 'passt nicht' in r.get('error', ''), r)
st, r, _ = hochladen(Be, D1, V1, 'Notiz.txt', b'<html><script>alert(1)</script></html>')
check('HTML mit Endung .txt → 422', st == 422 and 'passt nicht' in r.get('error', ''), r)
st, r, _ = hochladen(Be, D1, V1, 'Liste.xlsx', XLS)
check('Office 97 mit Endung .xlsx → 422', st == 422, r)
st, r, _ = hochladen(Be, D1, V1, 'Falsch.pdf', pdf('x', 5000), sha='0' * 64)
check('falsche Prüfsumme → 422', st == 422 and 'Prüfsumme' in r.get('error', ''), r)
check('nach Fehlern: keine Datei in der Ablage, keine Reste der Teile', blobs() == [] and teile_reste() == [], (blobs(), teile_reste()))

# ── Hochladen in den Entwurf ──
st, r, n = hochladen(Be, D1, V1, 'Protokoll.pdf', klein)
f1 = r.get('datei')
v = r['dokument']['versionen'][0] if st == 200 else {}
e1 = (v.get('dateien') or [{}])[0]
check('Datei im Entwurf abgelegt (ein Teil): Name, Größe, Prüfsumme, Art, wer', st == 200 and r['fertig'] is True and n == 1 and e1.get('id') == f1 and e1['name'] == 'Protokoll.pdf'
      and e1['groesse'] == len(klein) and e1['sha256'] == hashlib.sha256(klein).hexdigest() and e1['mime'] == 'application/pdf' and e1['art'] == 'pdf'
      and e1['hochgeladen']['von'] == 'Bernd Bearbeiter' and 'nachgetragen' not in e1, r)
check('Verlauf der Version: Datei abgelegt', 'Datei abgelegt: Protokoll.pdf' in json.dumps(v.get('verlauf'), ensure_ascii=False))
check('gespeichert als .bin unter data/dateien/qs/<xx>/, Inhalt gleich, keine Reste', os.path.isfile(blob_pfad(f1)) and open(blob_pfad(f1), 'rb').read() == klein and teile_reste() == [])
check('keine .php-Dateien in der Ablage (Sicherungsprüfung und Datenbank-Umschaltung lesen nur *.php)', not glob.glob(os.path.join(ABLAGE, '**', '*.php'), recursive=True))
gross = pdf('Anhang', 7 * MB + 123)
st, r, n = hochladen(Be, D1, V1, 'Anhang groß.pdf', gross)
check('7 MB in drei Teilen (3 + 3 + 1 MB)', st == 200 and r['fertig'] and n == 3 and dok(D1)['versionen'][0]['dateien'][1]['groesse'] == len(gross), (st, n))
for name, inhalt in (('Formular.docx', docx('Probenahme')), ('Liste.xls', XLS), ('Foto.png', PNG), ('Hinweis.txt', 'Prüfhinweis: Kühlkette\n'.encode())):
    st, r, _ = hochladen(Be, D1, V1, name, inhalt)
    check(f'Dateiart {name.rsplit(".", 1)[1]} angenommen', st == 200, r)
st, r, _ = hochladen(Be, D1, V1, '..\\..\\Ordner/Prüf:bericht?.pdf', pdf('Bericht'))
check('Dateiname ohne Pfad, verbotene Zeichen ersetzt', st == 200 and r['dokument']['versionen'][0]['dateien'][-1]['name'] == 'Prüf-bericht-.pdf', r['dokument']['versionen'][0]['dateien'][-1]['name'] if st == 200 else r)
st, r, _ = hochladen(Be, D1, V1, 'Unbenannt.PDF', pdf('gross geschrieben'))
check('Endung in Großbuchstaben angenommen', st == 200 and r['dokument']['versionen'][0]['dateien'][-1]['art'] == 'pdf', r)

# Teile: Reihenfolge, fremder Nutzer, anderes Ziel, Ablauf
mittel = pdf('Mittel', TEIL + 500)
st, r = teil_senden(Be, D1, V1, 'Mittel.pdf', len(mittel), '', 0, mittel[:TEIL])
up = r.get('upload', '')
check('erster Teil angenommen: noch nicht fertig, Upload-Kennung', st == 200 and r['fertig'] is False and len(up) == 24 and r['empfangen'] == TEIL, r)
check('Teil übersprungen → 422', teil_senden(Be, D1, V1, 'Mittel.pdf', len(mittel), up, 2, mittel[TEIL:])[1].get('error', '').startswith('Teile in falscher Reihenfolge'))
st, r = teil_senden(Q, D1, V1, 'Mittel.pdf', len(mittel), up, 1, mittel[TEIL:])
check('fremder Nutzer setzt den Upload nicht fort (422)', st == 422 and 'anderen Datei' in r.get('error', ''), r)
st, r = teil_senden(Be, O1, '', 'Mittel.pdf', len(mittel), up, 1, mittel[TEIL:])
check('anderes Ziel (Dokument) → 422', st == 422 and 'anderen Datei' in r.get('error', ''), r)
st, r = teil_senden(Be, D1, V1, 'Mittel.pdf', len(mittel), 'f' * 24, 1, mittel[TEIL:])
check('unbekannte Upload-Kennung → 422 (abgelaufen)', st == 422 and 'abgelaufen' in r.get('error', ''), r)
st, r = teil_senden(Be, D1, V1, 'Mittel.pdf', len(mittel), up, 1, mittel[TEIL:], sha=hashlib.sha256(mittel).hexdigest())
check('richtiger zweiter Teil: fertig', st == 200 and r['fertig'] is True, r)
st, r = teil_senden(Be, D1, V1, 'Alt.pdf', len(mittel), '', 0, mittel[:TEIL])
alt = r.get('upload', '')
for f in teile_reste():
    os.utime(f, (time.time() - 25 * 3600, time.time() - 25 * 3600))
hochladen(Be, D1, V1, 'Neu.pdf', pdf('neu'))   # beginnt einen neuen Upload und räumt dabei auf
st, r = teil_senden(Be, D1, V1, 'Alt.pdf', len(mittel), alt, 1, mittel[TEIL:])
check('unvollständiger Upload nach 24 Stunden entfernt (422 abgelaufen)', st == 422 and 'abgelaufen' in r.get('error', '') and teile_reste() == [], (r, teile_reste()))

# ── 4-Augen-Prinzip, Prüfung, Freigabe ──
st, r, _ = hochladen(Q, D1, V1, 'Ergänzung Quinn.pdf', pdf('Quinn'))
check('Ablegen im Entwurf macht zum Bearbeiter (Quinn)', st == 200 and ids['quinn'] in r['dokument']['versionen'][0]['bearbeiter'], r.get('dokument', {}).get('versionen'))
check('Einreichen', schritt(Be, D1, 'einreichen')[0] == 200)
st, r = schritt(Q, D1, 'pruefen_freigeben')
check('4-Augen-Prinzip: wer Dateien abgelegt hat, prüft nicht (403)', st == 403 and '4-Augen' in r.get('error', ''), r)
st, r, _ = hochladen(F, D1, V1, 'Spaet.pdf', pdf('spät'))
check('in Prüfung: Hochladen gesperrt (409)', st == 409 and 'Prüfung' in r.get('error', ''), r)
x = dok(D1)
st, r = Be.call('qs_datei_entfernen', {'datei': f1, 'rev': x['rev'], 'grund': ''})
check('in Prüfung: Entfernen gesperrt (409)', st == 409, r)
st, h, inhalt = roh(L, 'qs_datei&id=' + f1)
check('in Prüfung: Prüfer und Leser laden herunter (200, Inhalt gleich)', st == 200 and inhalt == klein, st)
check('Fritz prüft und gibt frei', schritt(F, D1, 'pruefen_freigeben')[0] == 200 and dok(D1)['versionen'][0]['status'] == 'freigegeben')

# ── Freigegebene Version: nachtragen und entfernen nur mit „freigeben“ ──
st, r, _ = hochladen(Be, D1, V1, 'Unterschrift.pdf', pdf('Unterschrift'))
check('freigegeben: Bearbeiter trägt nicht nach (403)', st == 403, r)
st, r = Be.call('qs_datei_entfernen', {'datei': f1, 'grund': 'Versehen'})
check('freigegeben: Bearbeiter entfernt nicht (403)', st == 403, r)
vorher = dok(D1)['versionen'][0]['bearbeiter']
st, r, _ = hochladen(Q, D1, V1, 'Unterschrift.pdf', pdf('Unterschrift'))
v = r['dokument']['versionen'][0] if st == 200 else {}
un = v.get('dateien', [{}])[-1]
check('freigegeben: QMB trägt nach (vermerkt, Verlauf an Version und Dokument)', st == 200 and un['nachgetragen'] is True and 'Datei nachgetragen: Unterschrift.pdf' in json.dumps(v['verlauf'], ensure_ascii=False)
      and 'Datei zu Version 1 nachgetragen: Unterschrift.pdf' in json.dumps(r['dokument']['verlauf'], ensure_ascii=False), r)
check('Nachtragen ändert die Versionsnummer nicht, Bearbeiter unverändert', v.get('nr') == 1 and v.get('bearbeiter') == vorher)
st, r, _ = hochladen(Q, D1, V1, 'Protokoll.pdf', pdf('zweites Protokoll'))
check('zweite Datei mit gleichem Namen angenommen', st == 200)
st, r = Q.call('qs_datei_entfernen', {'datei': un['id'], 'grund': ''})
check('Entfernen aus freigegebener Version ohne Grund → 422', st == 422 and 'Grund' in r.get('error', ''), r)
st, r = Q.call('qs_datei_entfernen', {'datei': un['id'], 'rev': 1, 'grund': 'falsche Datei'})
check('veralteter Stand → 409', st == 409 and r.get('code') == 'konflikt', r)
st, r = Q.call('qs_datei_entfernen', {'datei': un['id'], 'rev': dok(D1)['rev'], 'grund': 'Falsche Unterschriftenseite'})
weg = [f for f in r['dokument']['versionen'][0]['dateien'] if f['id'] == un['id']] if st == 200 else [{}]
check('entfernt: nur vermerkt (wer, Grund), Datei bleibt in der Ablage', st == 200 and weg[0]['entfernt']['von'] == 'Quinn QMB' and weg[0]['entfernt']['grund'] == 'Falsche Unterschriftenseite'
      and os.path.isfile(blob_pfad(un['id'])), r)
check('entfernt: Download 404, nochmals entfernen 409', roh(L, 'qs_datei&id=' + un['id'])[0] == 404 and Q.call('qs_datei_entfernen', {'datei': un['id'], 'grund': 'x'})[0] == 409)

# ── Neue Überarbeitung: Entwurf löscht endgültig ──
st, r = Be.call('qs_version_save', {'dokument': D1, 'aenderungen': 'Probenahme neu geregelt', 'grund': 'Internes Audit'})
V2 = r['dokument']['versionen'][-1]['id'] if st == 200 else ''
check('Überarbeitung begonnen: neue Version ohne Dateien', st == 200 and r['dokument']['versionen'][-1].get('dateien', []) == [], r)
st, r, _ = hochladen(Be, D1, V2, 'Probenahme neu.docx', docx('neu'))
st2, r2, _ = hochladen(Be, D1, V2, 'Notiz.txt', b'Entwurfsnotiz\n')
notiz = r2['datei'] if st2 == 200 else ''
check('Dateien im neuen Entwurf', st == 200 and st2 == 200 and len(dok(D1)['versionen'][-1]['dateien']) == 2)
st, r = Be.call('qs_datei_entfernen', {'datei': notiz, 'rev': dok(D1)['rev'], 'grund': ''})
check('Entwurf: Entfernen ohne Grund, Eintrag und Datei endgültig gelöscht', st == 200 and [f['name'] for f in r['dokument']['versionen'][-1]['dateien']] == ['Probenahme neu.docx']
      and not os.path.isfile(blob_pfad(notiz)) and 'Datei entfernt: Notiz.txt' in json.dumps(r['dokument']['versionen'][-1]['verlauf'], ensure_ascii=False), r)
check('gelöschte Datei: Download 404', roh(L, 'qs_datei&id=' + notiz)[0] == 404)

# ── Ordner: Dateien am Dokument ──
z1 = pdf('Zertifikat A')
st, r, _ = hochladen(Be, O1, '', 'IFS-Zertifikat Lieferant A.pdf', z1)
oz = r.get('datei', '')
check('Ordner: Datei am Dokument (ohne Version)', st == 200 and r['dokument']['dateien'][0]['name'] == 'IFS-Zertifikat Lieferant A.pdf' and r['dokument']['versionen'] == [], r)
st2, r2, _ = hochladen(Be, O1, '', 'Zertifikat B.pdf', pdf('Zertifikat B'))
ozb = r2.get('datei', '')
st, r = Be.call('qs_datei_entfernen', {'datei': oz, 'grund': ''})
check('Ordner: Entfernen nur mit Grund (422)', st == 422)
x = dok(O1)
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'F', 'nr': '2.1-F01', 'titel': x['titel'], 'id': O1, 'rev': x['rev']})
check('Ordner mit Dateien wird nicht zum gelenkten Dokument (422)', st == 422 and 'Dateien' in r.get('error', ''), r)
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'X', 'nr': '', 'titel': x['titel'], 'id': O1, 'rev': x['rev']})
check('Ordner → externes Dokument (auch ohne Versionen) bleibt möglich', st == 200, r)
check('Datei nicht gefunden → 404', Be.call('qs_datei_entfernen', {'datei': 'abcdefabcdefabcdefab', 'grund': 'x'})[0] == 404)

# Höchstzahl je Stelle
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Massenablage'})
O2 = r['dokument']['id']
ok50 = all(hochladen(Be, O2, '', f'Beleg {i:02d}.txt', f'Beleg {i}\n'.encode())[0] == 200 for i in range(50))
st, r, _ = hochladen(Be, O2, '', 'Beleg 51.txt', b'Beleg 51\n')
check('höchstens 50 Dateien je Stelle (51. → 422)', ok50 and st == 422 and '50' in r.get('error', ''), r)

# ── Download ──
st, r, _ = hochladen(Q, D1, V1, 'Prüfbericht März.pdf', pdf('März'))
pm = r.get('datei', '')
st, h, inhalt = roh(L, 'qs_datei&id=' + pm)
check('Download: als Anhang mit UTF-8-Namen und Ersatznamen', st == 200 and h.get('content-disposition') == "attachment; filename=\"Pruefbericht Maerz.pdf\"; filename*=UTF-8''Pr%C3%BCfbericht%20M%C3%A4rz.pdf", h)
check('Download: Typ, nosniff, sandbox, nicht zwischenspeichern, Länge, Inhalt gleich', h.get('content-type') == 'application/pdf' and h.get('x-content-type-options') == 'nosniff'
      and 'sandbox' in h.get('content-security-policy', '') and 'no-store' in h.get('cache-control', '') and int(h.get('content-length', 0)) == len(inhalt) and inhalt == pdf('März'), h)
st, h, inhalt = roh(L, 'qs_datei&id=' + hochladen(Be, D1, V2, 'Ablauf.docx', docx('Ablauf'))[1]['datei'])
check('Download: Word mit Office-Typ', st == 200 and h.get('content-type') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' and inhalt == docx('Ablauf'), h)
check('Download: unbekannte und ungültige Kennung 404', roh(L, 'qs_datei&id=abcdefabcdefabcdefab')[0] == 404 and roh(L, 'qs_datei&id=ABC-def-0123456789')[0] == 404 and roh(L, 'qs_datei')[0] == 404)

# ── ZIP-Export ──
st, h, inhalt = roh(L, 'qs_ablage_export')
z, e = zip_lesen(inhalt) if st == 200 else (None, {})
W = 'QM-System/'
DK = W + '1.4 Qualitätssicherung/1.4-F01 Probenahmeprotokoll/'
OK_ = W + '2.1 Einkauf - Wareneingang/Lieferantenzertifikate/'
check('ZIP: Typ, Dateiname mit Datum, gültiges Archiv', st == 200 and h.get('content-type') == 'application/zip' and f'QM-System_{HEUTE}.zip' in h.get('content-disposition', '') and z.testzip() is None, h)
check('ZIP: Dokumentenliste zuerst', list(e)[:1] == [W + 'Dokumentenliste.csv'] and 'Probenahmeprotokoll' in z.read(W + 'Dokumentenliste.csv').decode('utf-8-sig'), list(e)[:3])
check('ZIP: gültige Version im Dokumentordner (Inhalt gleich, Umlaute, UTF-8-Kennzeichen)', z.read(DK + 'Protokoll.pdf') == klein and z.read(DK + 'Anhang groß.pdf') == gross
      and e[DK + 'Anhang groß.pdf'].flag_bits & 0x800 and DK + 'Prüf-bericht-.pdf' in e and DK + 'Prüfbericht März.pdf' in e, sorted(e))
check('ZIP: gleicher Name bekommt „ (2)“', z.read(DK + 'Protokoll (2).pdf') == pdf('zweites Protokoll'), sorted(e))
check('ZIP: entfernte Dateien und Entwurf nicht enthalten', not any('Unterschrift' in n or 'Probenahme neu' in n or '_Entwurf' in n for n in e), sorted(e))
check('ZIP: Ordner mit Dateien (Schrägstrich im Kapitel ersetzt)', z.read(OK_ + 'IFS-Zertifikat Lieferant A.pdf') == z1 and OK_ + 'Zertifikat B.pdf' in e, sorted(e))
check('ZIP: ohne Dateiattribute aus der Ablage (keine Pfade nach oben)', all(not n.startswith('/') and '..' not in n.split('/') for n in e))
os.remove(blob_pfad(ozb))
st, h, inhalt = roh(L, 'qs_ablage_export&kapitel=2.1')
z, e = zip_lesen(inhalt) if st == 200 else (None, {})
check('ZIP nach Kapitel: nur 2.1, Dateiname mit Kapitel', st == 200 and f'QM-System_2.1_{HEUTE}.zip' in h.get('content-disposition', '') and not any('1.4' in n for n in e) and OK_ + 'IFS-Zertifikat Lieferant A.pdf' in e, sorted(e))
check('ZIP: fehlende Datei in Hinweise.txt statt im Archiv', OK_ + 'Zertifikat B.pdf' not in e and 'Zertifikat B.pdf' in z.read(W + 'Hinweise.txt').decode('utf-8'), sorted(e))
check('Download einer fehlenden Datei: 404 mit Hinweis', (lambda s: s[0] == 404 and 'fehlt' in json.loads(s[2]).get('error', ''))(roh(L, 'qs_datei&id=' + ozb)))
check('ZIP: unbekanntes Kapitel 422', roh(L, 'qs_ablage_export&kapitel=9.9')[0] == 422)
st, r = Q.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'O', 'nr': '', 'titel': 'Massenablage', 'id': O2, 'rev': dok(O2)['rev'], 'eingezogen': True, 'einzugGrund': 'Belege archiviert'})
check('Ordner eingezogen', st == 200)
check('eingezogen: Hochladen gesperrt (409)', hochladen(Be, O2, '', 'Nachzügler.txt', b'spaet\n')[0] == 409)
check('ZIP ohne „alle“: eingezogene Dokumente fehlen', not any('Massenablage' in n for n in zip_lesen(roh(L, 'qs_ablage_export')[2])[1]))
# zweite Freigabe: Version 1 wird „ersetzt“
check('Version 2 eingereicht und freigegeben (Fritz)', schritt(Be, D1, 'einreichen')[0] == 200 and schritt(F, D1, 'pruefen_freigeben')[0] == 200
      and [v['status'] for v in dok(D1)['versionen']] == ['ersetzt', 'freigegeben'])
st, h, inhalt = roh(L, 'qs_ablage_export')
z, e = zip_lesen(inhalt)
check('ZIP: jetzt Version 2 im Dokumentordner, Version 1 nicht', DK + 'Probenahme neu.docx' in e and DK + 'Ablauf.docx' in e and DK + 'Protokoll.pdf' not in e, sorted(e))
st, h, inhalt = roh(L, 'qs_ablage_export&alle=1')
z, e = zip_lesen(inhalt)
check('ZIP mit „alle“: ältere Version im Unterordner, eingezogene Dokumente unter _eingezogen', z.read(DK + '_ältere Versionen/Version 1/Protokoll.pdf') == klein
      and W + '_eingezogen/2.1 Einkauf - Wareneingang/Massenablage/Beleg 07.txt' in e and DK + 'Probenahme neu.docx' in e, sorted(e)[:12])
st, r, _ = hochladen(Be, D1, V1, 'Scan alt.pdf', pdf('Scan'))
st2, r2, _ = hochladen(Q, D1, V1, 'Scan alt.pdf', pdf('Scan'))
check('ersetzte Version: nachtragen nur mit „freigeben“ (403 / 200)', st == 403 and st2 == 200, (r, r2))
st, r = Be.call('qs_version_save', {'dokument': D1, 'aenderungen': 'Versuch', 'grund': 'Test'})
V3 = r['dokument']['versionen'][-1]['id']
hochladen(Be, D1, V3, 'Entwurf3.pdf', pdf('Entwurf 3'))
check('ZIP mit „alle“: offener Entwurf unter _Entwurf', DK + '_Entwurf/Entwurf3.pdf' in zip_lesen(roh(L, 'qs_ablage_export&alle=1')[2])[1])
check('Entwurf verworfen', schritt(Be, D1, 'verwerfen', grund='doch nicht')[0] == 200)
st, r, _ = hochladen(Be, D1, V3, 'Danach.pdf', pdf('danach'))
check('verworfene Version: Hochladen gesperrt (409)', st == 409, r)
check('ZIP mit „alle“: verworfene Version nicht enthalten', not any('Entwurf3' in n for n in zip_lesen(roh(L, 'qs_ablage_export&alle=1')[2])[1]))

# ── Datenpaket, Speicherung, Protokoll ──
paket = json.load(open(PAKET_DATEI, encoding='utf-8'))
st, r = V.call('qs_import', {'paket': paket, 'vorschau': True})
check('Datenpaket-Vorschau nennt die Dateien der Ablage', st == 200 and r['dateien'] > 50, r.get('dateien'))
st, r = V.call('qs_import', {'paket': paket, 'ersetzen': True})
check('Datenpaket ersetzt nicht, sobald Dateien liegen (409), nichts geändert', st == 409 and 'Dokumentenablage' in r.get('error', '') and dok(D1)['nr'] == '1.4-F01', r)
roh_dok = storage_raw('qs-dokumente') or ''
check('Metadaten im Dokument qs-dokumente, Inhalte nicht' + (' (SQLite)' if storage_sqlite() else ' (Dateien)'), 'Protokoll.pdf' in roh_dok and '%PDF-1.4' not in roh_dok
      and base64.b64encode(klein).decode() not in roh_dok)
check('Dateien liegen auch mit SQLite im Dateisystem', os.path.isfile(blob_pfad(f1)) and len(blobs()) > 50)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: abgelegt, gelöscht, entfernt, ZIP', all(t in log for t in ('QM-System: Datei für 1.4-F01 Probenahmeprotokoll abgelegt', 'gelöscht (Entwurf)', 'entfernt (vermerkt)',
                                                                            'Dokumentenablage als ZIP heruntergeladen', 'Kapitel 2.1', 'mit älteren Versionen')), log[-2000:])
check('Protokoll ohne Dateinamen und Gründe', 'Unterschrift.pdf' not in log and 'Falsche Unterschriftenseite' not in log and 'IFS-Zertifikat' not in log)

# ── Oberfläche ──
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F02', 'titel': 'Reinigungsplan', 'zustaendig': 'QB'})
D2 = r['dokument']['id']; V21 = r['dokument']['versionen'][0]['id']
ZIEH = """([sel, dateien]) => {
  const dt = new DataTransfer();
  for (const [name, text, typ] of dateien) dt.items.add(new File([text], name, { type: typ }));
  const z = document.querySelector(sel);
  for (const t of ['dragenter', 'dragover', 'drop']) z.dispatchEvent(new DragEvent(t, { dataTransfer: dt, bubbles: true, cancelable: true }));
}"""
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

    def toast(pg, inhalt):
        pg.wait_for_function('t => document.querySelector("#qm-toast").classList.contains("zeigen") && document.querySelector("#qm-toast").textContent.includes(t)', arg=inhalt)
        return True

    def oeffne_dok(pg, did):
        pg.click('#qm-tabs [data-tab="dokumente"]'); pg.click(f'#qm-d-liste tr[data-dok="{did}"]'); pg.wait_for_selector('#qm-dk:not([hidden]) h2')

    def passt(pg):
        return pg.evaluate("(() => { const d = document.querySelector('#qm-dk'); const r = d.getBoundingClientRect(); return document.documentElement.scrollWidth <= window.innerWidth + 1"
                           " && d.scrollWidth <= d.clientWidth + 1 && r.right <= window.innerWidth + 1; })()")

    # Bernd: Entwurf mit Dateien
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    check('Liste: Büroklammer mit Zahl bei Dateien der gültigen Version', pg.locator(f'#qm-d-liste tr[data-dok="{D1}"] .qm-anz').count() == 1
          and pg.locator(f'#qm-d-liste tr[data-dok="{D2}"] .qm-anz').count() == 0)
    oeffne_dok(pg, D2)
    check('Entwurf: Ablagefeld mit Hinweis auf Größe', pg.locator(f'#qm-dk .qm-drop[data-drop="{V21}"]').count() == 1 and '25 MB' in text(pg, '#qm-dk .qm-drop'))
    pg.fill('#dk-aend', 'Reinigung Kühlhaus ergänzt')
    with pg.expect_file_chooser() as fc:
        pg.click('#qm-dk .qm-drop')
    fc.value.set_files([{'name': 'Plan.pdf', 'mimeType': 'application/pdf', 'buffer': pdf('Plan')},
                        {'name': 'Plan groß.pdf', 'mimeType': 'application/pdf', 'buffer': pdf('Plan groß', 7 * MB)}])
    toast(pg, '2 Dateien abgelegt')
    pg.wait_for_function("document.querySelectorAll('#qm-dk .qm-datei').length === 2")
    check('Dateiauswahl: zwei Dateien abgelegt (eine in drei Teilen), Fortschritt verschwunden', pg.locator('#qm-dk .qm-laden').count() == 0
          and [f['groesse'] for f in dok(D2)['versionen'][0]['dateien']] == [len(pdf('Plan')), 7 * MB])
    check('ungespeicherte Stichworte bleiben nach dem Ablegen', pg.input_value('#dk-aend') == 'Reinigung Kühlhaus ergänzt', pg.input_value('#dk-aend'))
    pg.evaluate(ZIEH, ['#qm-dk .qm-drop', [['Notiz.txt', 'Hinweis Reinigung', 'text/plain'], ['Werkzeug.exe', 'MZ', 'application/octet-stream']]])
    toast(pg, 'Werkzeug.exe')
    pg.wait_for_function("document.querySelectorAll('#qm-dk .qm-datei').length === 3")
    check('Ziehen und Ablegen: erlaubte Datei abgelegt, verbotene mit Grund in der Liste', 'nicht erlaubt' in text(pg, '#qm-dk .qm-laden li.fehler')
          and pg.locator('#qm-dk .qm-laden li.fertig').count() == 1, text(pg, '#qm-dk'))
    pg.screenshot(path=os.path.join(SH, 'qs_ablage_entwurf_1280.png'))
    with pg.expect_download() as dl:
        pg.click('#qm-dk .qm-datei-name:has-text("Plan.pdf")')
    check('Herunterladen: Dateiname und Inhalt', dl.value.suggested_filename == 'Plan.pdf' and open(dl.value.path(), 'rb').read() == pdf('Plan'), dl.value.suggested_filename)
    pg.click('#qm-dk .qm-datei:has-text("Notiz.txt") [data-datei-weg]'); pg.wait_for_selector('#dlg-grund[open]')
    check('Entfernen im Entwurf: Grund freiwillig', 'gelöscht' in text(pg, '#gr-text') and 'optional' in text(pg, '#gr-label'))
    pg.click('#gr-form [type="submit"]'); toast(pg, 'Datei entfernt')
    pg.wait_for_function("document.querySelectorAll('#qm-dk .qm-datei').length === 2")
    check('entfernt: zwei Dateien, Stichworte weiter da', 'Notiz.txt' not in text(pg, '#qm-dk .qm-dateien') and pg.input_value('#dk-aend') == 'Reinigung Kühlhaus ergänzt')
    pg.click('#qm-d-zip'); pg.wait_for_selector('#dlg-ablage[open]')
    ohne = text(pg, '#az-umfang')
    pg.check('#az-alle')
    mit = text(pg, '#az-umfang')
    check('Export-Dialog: Umfang mit und ohne ältere Versionen/Entwürfe', 'Dateien' in ohne and 'Dokumentenliste' in ohne and ohne != mit, (ohne, mit))
    pg.screenshot(path=os.path.join(SH, 'qs_ablage_export_1280.png'))
    with pg.expect_download() as dl:
        pg.click('#az-form [type="submit"]')
    z, e = zip_lesen(open(dl.value.path(), 'rb').read())
    check('Export aus der Oberfläche: ZIP mit Entwurf des Reinigungsplans', dl.value.suggested_filename == f'QM-System_{HEUTE}.zip'
          and W + '1.4 Qualitätssicherung/1.4-F02 Reinigungsplan/_Entwurf/Plan.pdf' in e, sorted(e)[:8])
    pg.wait_for_selector('#dlg-ablage', state='hidden')
    oeffne_dok(pg, D1)
    check('gültige Version: Dateien ohne Ablagefeld und ohne Entfernen (nur bearbeiten)', pg.locator('#qm-dk .qm-ablage .qm-datei').count() > 0
          and pg.locator('#qm-dk .qm-drop').count() == 0 and pg.locator('#qm-dk [data-datei-weg]').count() == 0)
    check('ältere Version: Dateien in der Versionszeile, entfernte nur als Vermerk', pg.locator('#qm-dk .qm-version-dateien .qm-datei').count() >= 5
          and 'entfernt' in text(pg, '#qm-dk .qm-version-dateien .qm-entfernt summary'))
    ctx.close()

    # Quinn: nachtragen und entfernen mit Grund
    ctx, pg = anmelden('quinn', 'Freigabe-Konto-56', '198.51.100.12')
    oeffne_dok(pg, D1)
    check('Freigaberecht: „Datei nachtragen“ an der gültigen und an älteren Versionen', 'Datei nachtragen' in text(pg, '#qm-dk .qm-ablage .qm-drop')
          and pg.locator('#qm-dk .qm-version-dateien .qm-drop.klein').count() == 1)
    pg.evaluate(ZIEH, ['#qm-dk section.qm-ablage .qm-drop', [['Freigabevermerk.pdf', '%PDF-1.4 Vermerk', 'application/pdf']]])
    toast(pg, 'Datei abgelegt')
    pg.wait_for_selector('#qm-dk .qm-datei:has-text("Freigabevermerk.pdf")')
    check('nachgetragen vermerkt', 'nachgetragen' in text(pg, '#qm-dk .qm-datei:has-text("Freigabevermerk.pdf")'))
    pg.click('#qm-dk .qm-datei:has-text("Freigabevermerk.pdf") [data-datei-weg]'); pg.wait_for_selector('#dlg-grund[open]')
    pg.click('#gr-form [type="submit"]')
    check('freigegeben: Entfernen nur mit Grund', 'Grund' in text(pg, '#gr-meldung') and pg.is_visible('#dlg-grund'))
    pg.fill('#gr-grund', 'doppelt abgelegt'); pg.click('#gr-form [type="submit"]'); toast(pg, 'Datei entfernt')
    pg.wait_for_selector('#qm-dk section.qm-ablage .qm-entfernt')
    check('entfernt mit Grund: als Vermerk sichtbar, nicht mehr in der Liste', 'Freigabevermerk.pdf' not in text(pg, '#qm-dk section.qm-ablage .qm-dateien')
          and 'doppelt abgelegt' in pg.inner_html('#qm-dk section.qm-ablage .qm-entfernt'))
    pg.screenshot(path=os.path.join(SH, 'qs_ablage_freigegeben_1280.png'))
    ctx.close()

    # Nur ansehen und Handy, hell und dunkel
    for user, pw, breite, thema in (('lisa', 'Leserin-Konto-12', 390, 'light'), ('lisa', 'Leserin-Konto-12', 390, 'dark'), ('bernd', 'Bearbeit-Konto-34', 390, 'dark'), ('lisa', 'Leserin-Konto-12', 1280, 'dark')):
        ctx, pg = anmelden(user, pw, '198.51.100.10' if user == 'lisa' else '198.51.100.11', breite, thema, 844 if breite < 500 else 900)
        oeffne_dok(pg, D2 if user == 'bernd' else D1)
        if user == 'lisa':
            check(f'{breite}px {thema}: nur ansehen – Dateien ladbar, keine Ablagefelder, kein Entfernen', pg.locator('#qm-dk .qm-datei-name').count() > 0
                  and pg.locator('#qm-dk .qm-drop').count() == 0 and pg.locator('#qm-dk [data-datei-weg]').count() == 0)
        else:
            check(f'{breite}px {thema}: Entwurf mit Ablagefeld und Entfernen', pg.locator('#qm-dk .qm-drop').count() == 1 and pg.locator('#qm-dk [data-datei-weg]').count() == 2)
        check(f'{breite}px {thema}: Seitenleiste mit Dateien passt in die Breite', passt(pg))
        pg.screenshot(path=os.path.join(SH, f'qs_ablage_{user}_{breite}_{thema}.png'))
        if breite == 390 and user == 'lisa':
            pg.click('#qm-dk [data-dk="schliessen"]'); pg.wait_for_selector('#qm-dk', state='hidden')
            pg.click('#qm-d-zip'); pg.wait_for_selector('#dlg-ablage[open]')
            check(f'{breite}px {thema}: Export-Dialog ohne waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
            pg.screenshot(path=os.path.join(SH, f'qs_ablage_export_{breite}_{thema}.png'))
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
