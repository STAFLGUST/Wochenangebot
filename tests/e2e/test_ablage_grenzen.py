"""Dateiablage des Plattformkerns (app/api/lib/dateiablage.php): Dateiarten und Größe für das ganze QM-System (Inhaber 16.11.2026).

Geprüft über das Hochladen im QM-System (qs_datei_hochladen): Einstellungen für die Oberfläche (250 MB je Datei, neue Arten, keine
ausführbaren Arten); Kopfprüfung jeder neuen Art (Videos mp4/m4v/mov auch als ältere QuickTime-Datei, Fotos heic/heif/tif/tiff/bmp,
zip auch leer, xlsb, opus/ogg, json, ics, ttv) gültig abgelegt mit MIME-Typ und gefälscht abgelehnt (z. B. .mp4 mit PDF-Kopf, .heic
mit fremder Marke, .json mit HTML, .ttv mit Programm); html, svg, js, exe, lnk, bat und Ähnliches bleiben abgelehnt; Grenze
genau 250 MB abgelegt (in Teilen, Prüfsumme, Download gleich) und 250 MB + 1 Byte abgelehnt; Word/Excel über 25 MB werden nicht
in den Speicher gelesen (keine Platzhalter), kleine weiterhin. Der Testserver läuft mit memory_limit 128M wie im Betrieb
(tests/fixtures/php/produktion.ini): lädt der Server eine große Datei ganz in den Speicher, scheitert die Gruppe. Nur erfundene Testdaten.
"""
import base64
import hashlib
import io
import os
import struct
import time
import urllib.error
import urllib.request
import zipfile

from kunden_hilfe import Client, API
from umgebung import ablageordner

PW = 'Sicheres-Passwort-1'
MB = 1024 * 1024
TEIL = 3 * MB
GRENZE = 250 * MB
ABLAGE = os.path.join(ablageordner(), 'dateien')
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def hochladen(cli, dok, ver, name, inhalt, groesse=None):
    """In Teilen hochladen wie die Oberfläche: (Status, letzte Antwort)"""
    upload, pos, nr, sha = '', 0, 0, hashlib.sha256(inhalt).hexdigest()
    while True:
        stueck = inhalt[pos:pos + TEIL]
        st, r = cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt) if groesse is None else groesse,
                                                'sha256': sha, 'upload': upload, 'teil': nr, 'daten': base64.b64encode(stueck).decode()})
        if st != 200 or r.get('fertig'):
            return st, r
        upload = r['upload']; pos += len(stueck); nr += 1


def roh(cli, query):
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def box(typ, inhalt=b''):
    return struct.pack('>I', 8 + len(inhalt)) + typ + inhalt


def zip_mit(eintraege, stored=False):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED) as z:
        for n, d in eintraege.items():
            z.writestr(n, d)
    return b.getvalue()


def xlsx(text, fuellung=0):
    """Excel-Datei mit Platzhalter in sharedStrings; fuellung = Bytes eines ungepackten Bildes (macht die Datei groß)"""
    e = {'[Content_Types].xml': '<Types/>', 'xl/sharedStrings.xml': f'<sst><si><t>{text}</t></si></sst>'}
    if fuellung:
        e['xl/media/bild.bin'] = bytes(fuellung)
    return zip_mit(e, stored=True)


def pdf(text):
    return b'%PDF-1.4\n% ' + text.encode() + b'\n%%EOF'


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
K = {}
for i, (u, n, p, rechte) in enumerate((('bernd', 'Bernd Bearbeiter', 'Bearbeit-Konto-34', ['qs.bearbeiten']), ('vera', 'Vera Verwalten', 'Verwalt-Konto-90', ['qs.verwalten']))):
    st, r = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'editor', 'active': True, 'password': p, 'mustChange': False, 'grant': rechte})
    assert st == 200, r
    K[u] = Client(f'198.51.100.{11 + i}'); K[u].call('login', {'username': u, 'password': p})
Be, V = K['bernd'], K['vera']
check('Kapitel', V.call('qs_stamm_save', {'kapitel': [{'id': '1.4', 'titel': 'Qualitätssicherung', 'zustaendig': ''}], 'personen': []})[0] == 200)

NEU = {'mov', 'mp4', 'm4v', 'heic', 'heif', 'tif', 'tiff', 'bmp', 'zip', 'xlsb', 'opus', 'ogg', 'json', 'ics', 'ttv'}
GEFAEHRLICH = ['html', 'htm', 'xhtml', 'svg', 'js', 'exe', 'com', 'scr', 'msi', 'bat', 'cmd', 'ps1', 'vbs', 'jar', 'hta', 'lnk', 'reg', 'php']
st, r = Be.call('qs_start')
a = r.get('ablage', {})
check('Einstellungen für die Oberfläche: 250 MB je Datei, Teile zu 3 MB', st == 200 and a.get('max') == GRENZE and a.get('teil') == TEIL, a)
check('Einstellungen: neue Arten erlaubt, ausführbare nie', NEU <= set(a.get('arten', [])) and not set(GEFAEHRLICH) & set(a.get('arten', [])), a.get('arten'))

st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Sammelordner'})
O = r['dokument']['id']
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F01', 'titel': 'Temperaturliste', 'zustaendig': ''})
D, DV = r['dokument']['id'], r['dokument']['versionen'][0]['id']
check('Ordner und gelenktes Dokument angelegt', O and D and DV)

# ── Kopfprüfung der neuen Arten: gültig → abgelegt mit MIME-Typ, gefälscht → 422 ──
GUELTIG = {
    'Rundgang.mp4': (box(b'ftyp', b'isom\0\0\x02\0isomiso2mp41') + box(b'mdat', bytes(64)), 'video/mp4'),
    'Schulung.m4v': (box(b'ftyp', b'M4V \0\0\0\x01M4V mp42isom') + box(b'mdat', bytes(64)), 'video/x-m4v'),
    'Kamera.mov': (box(b'ftyp', b'qt  \0\0\x02\0qt  ') + box(b'moov', bytes(32)), 'video/quicktime'),
    'Alt.mov': (box(b'wide') + box(b'mdat', bytes(64)), 'video/quicktime'),   # ältere QuickTime-Datei ohne ftyp
    'Etikett.heic': (box(b'ftyp', b'heic\0\0\0\0mif1heic') + box(b'meta', bytes(32)), 'image/heic'),
    'Etikett.heif': (box(b'ftyp', b'mif1\0\0\0\0mif1heic') + box(b'meta', bytes(32)), 'image/heif'),
    'Scan.tif': (b'II*\0\x08\0\0\0' + bytes(64), 'image/tiff'),
    'Scan.tiff': (b'MM\0*\0\0\0\x08' + bytes(64), 'image/tiff'),
    'Skizze.bmp': (b'BM' + struct.pack('<I', 66) + bytes(60), 'image/bmp'),
    'Sprachnachricht.opus': (b'OggS\0\x02' + bytes(20) + b'\x01\x13OpusHead\x01\x01', 'audio/ogg'),
    'Ton.ogg': (b'OggS\0\x02' + bytes(20) + b'\x01\x1e\x01vorbis', 'audio/ogg'),
    'Archiv.zip': (zip_mit({'Hinweis.txt': 'Prüfung'}), 'application/zip'),
    'Leer.zip': (zip_mit({}), 'application/zip'),
    'Mappe.xlsb': (zip_mit({'[Content_Types].xml': '<Types/>', 'xl/workbook.bin': b'\x83\x01\0'}), 'application/vnd.ms-excel.sheet.binary.macroEnabled.12'),
    'Messwerte.json': (b'{"messung": [3.5, 4.0]}\n', 'application/json'),
    'Termin.ics': (b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n', 'text/calendar'),
    'Kuehlhaus.ttv': (b'wd2\xcd{#\0\x01' + bytes(range(256)), 'application/octet-stream'),
}
assert GUELTIG['Leer.zip'][0][:4] == b'PK\x05\x06', 'leeres ZIP: nur das Ende des Verzeichnisses'
ids = {}
for name, (inhalt, mime) in GUELTIG.items():
    st, r = hochladen(Be, O, '', name, inhalt)
    ids[name] = r.get('datei')
    e = next((f for f in (r.get('dokument') or {}).get('dateien', []) if f['id'] == r.get('datei')), {})
    check(f'{name}: abgelegt als {mime}', st == 200 and e.get('mime') == mime and e.get('groesse') == len(inhalt), (st, r.get('error'), e.get('mime')))

HTML = b'<html><script>alert(1)</script></html>'
GEFAELSCHT = {name: pdf('kein ' + name) for name in GUELTIG if not name.endswith(('.json', '.ics', '.ttv'))}
GEFAELSCHT.update({'Marke.heic': box(b'ftyp', b'isom\0\0\0\0isom') + bytes(32), 'Messwerte.json': HTML, 'Termin.ics': HTML,
                   'Programm.ttv': b'MZ\x90\0' + bytes(200), 'Seite.ttv': HTML})
for name, inhalt in GEFAELSCHT.items():
    st, r = hochladen(Be, O, '', name, inhalt)
    check(f'{name} mit fremdem Inhalt → 422', st == 422 and 'passt nicht' in r.get('error', ''), (st, r))

for ext in GEFAEHRLICH + ['xyz']:
    st, r = hochladen(Be, O, '', f'Datei.{ext}', HTML if ext in ('html', 'htm', 'xhtml', 'svg') else b'MZ\x90\0' + bytes(100))
    check(f'.{ext} bleibt abgelehnt', st == 422 and 'nicht erlaubt' in r.get('error', ''), (st, r))

st, h, inhalt = roh(Be, 'qs_datei&id=' + str(ids['Rundgang.mp4']))
check('Download eines Videos: video/mp4 als Anhang, nosniff', st == 200 and h.get('content-type') == 'video/mp4' and h.get('content-disposition', '').startswith('attachment')
      and h.get('x-content-type-options') == 'nosniff' and inhalt == GUELTIG['Rundgang.mp4'][0], h)

# ── Größe: genau 250 MB als Excel im Entwurf (in Teilen), 250 MB + 1 Byte abgelehnt ──
klein = xlsx('{{Nr}} {{Titel}}')
st, r = hochladen(Be, D, DV, 'Liste klein.xlsx', klein)
e = r['dokument']['versionen'][0]['dateien'][-1] if st == 200 else {}
check('kleine Excel-Datei: Platzhalter erkannt (wird gelesen)', st == 200 and e.get('platzhalter') == ['nr', 'titel'], e)

gross = xlsx('{{Nr}} {{Titel}}', 1)
gross = xlsx('{{Nr}} {{Titel}}', GRENZE - len(gross) + 1)
assert len(gross) == GRENZE, len(gross)
t0 = time.time()
st, r = hochladen(Be, D, DV, 'Liste groß.xlsx', gross)
dauer = time.time() - t0
e = r['dokument']['versionen'][0]['dateien'][-1] if st == 200 else {}
pfad = os.path.join(ABLAGE, 'qs', str(r.get('datei', ''))[:2], f"{r.get('datei')}.bin")
check(f'genau 250 MB in {-(-GRENZE // TEIL)} Teilen abgelegt ({dauer:.1f} s)', st == 200 and e.get('groesse') == GRENZE and e.get('sha256') == hashlib.sha256(gross).hexdigest()
      and os.path.getsize(pfad) == GRENZE, (st, r.get('error')))
check('Excel über 25 MB: nicht in den Speicher gelesen, keine Platzhalter', st == 200 and 'platzhalter' not in e, e)
check('keine Reste der Teile', not [f for f in os.listdir(os.path.join(ABLAGE, '.teile'))])
st, h, inhalt = roh(Be, 'qs_datei&id=' + str(r.get('datei')))
check('Download der 250-MB-Datei: vollständig und gleich', st == 200 and h.get('content-length') == str(GRENZE) and hashlib.sha256(inhalt).digest() == hashlib.sha256(gross).digest())
del gross, inhalt

st, r = Be.call('qs_datei_hochladen', {'dokument': D, 'version': DV, 'name': 'zu groß.mp4', 'groesse': GRENZE + 1, 'sha256': '', 'upload': '', 'teil': 0,
                                       'daten': base64.b64encode(GUELTIG['Rundgang.mp4'][0]).decode()})
check('250 MB + 1 Byte → 422 schon beim ersten Teil', st == 422 and '250 MB' in r.get('error', ''), r)

print(f'{sum(res)}/{len(res)} passed')
