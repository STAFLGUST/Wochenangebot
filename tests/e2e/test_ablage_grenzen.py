"""Dateiablage des Plattformkerns (app/api/lib/dateiablage.php): Dateiarten und Größe für das ganze QM-System (Inhaber 16.11.2026).

Geprüft über das QM-System (qs_datei_hochladen, qs_datei, qs_ablage_export, Freigabe und Überarbeitung): Einstellungen für die
Oberfläche (250 MB je Datei, neue Arten, keine ausführbaren Arten); Kopfprüfung jeder neuen Art (Videos mp4/m4v/mov auch als ältere
QuickTime-Datei und mit langem ftyp-Block, Fotos heic/heif/tif/tiff/bmp, zip auch leer, xlsb, opus/ogg, json, ics, ttv, Word und
Excel mit Kennwort als OLE-Container) gültig
abgelegt mit MIME-Typ und gefälscht abgelehnt (z. B. .mp4 mit PDF-Kopf, Windows-Programm als .mp4/.heic, leeres ZIP als .docx,
.heic mit fremder Marke, .json mit HTML, .ttv mit Programm oder HTML nach Leerraum); html, svg, js, exe, lnk, bat und Ähnliches
bleiben abgelehnt, auch als Eintrag eines ZIP (Großbuchstaben, Unterordner, Zip64), beschädigtes ZIP-Verzeichnis abgelehnt; Grenze
genau 250 MB abgelegt (in Teilen, Prüfsumme, Download gleich) und 250 MB + 1 Byte abgelehnt; Download und ZIP-Export sperren die
Sitzung nicht; Word/Excel über 25 MB werden nicht in den Speicher gelesen (keine Platzhalter, die Freigabe vermerkt den Grund), kleine
weiterhin; die Überarbeitung übernimmt 250 MB ohne Kopie, Löschen der Übernahme lässt das Original. Der Testserver läuft mit
memory_limit 128M wie im Betrieb (tests/fixtures/php/produktion.ini): lädt der Server eine große Datei ganz in den Speicher, scheitert
die Gruppe. Nur erfundene Testdaten.
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


def roh(cli, query, timeout=None):
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req, timeout=timeout)
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


def zip64(daten):
    """Ende des Verzeichnisses als Zip64 mit Höchstwerten im klassischen Ende, wie es Packer ab 65535 Einträgen bzw. 4 GB schreiben"""
    p = daten.rfind(b'PK\x05\x06')
    _, _, _, n, laenge, start, _ = struct.unpack('<HHHHIIH', daten[p + 4:p + 22])
    ende64 = b'PK\x06\x06' + struct.pack('<QHHIIQQQQ', 44, 45, 45, 0, 0, n, n, laenge, start)
    return daten[:p] + ende64 + b'PK\x06\x07' + struct.pack('<IQI', 0, p, 1) + b'PK\x05\x06' + struct.pack('<HHHHIIH', 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)


# Kopf einer OLE-/CFB-Datei (MS-CFB 2.2): so speichert Microsoft Office eine docx/xlsx mit Kennwort
CFB = (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + bytes(16) + struct.pack('<5H', 0x3E, 3, 0xFFFE, 9, 6) + bytes(6)
       + struct.pack('<10I', 0, 1, 1, 0, 0x1000, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0, 0) + b'\xff' * 432 + bytes(1024))


def dok(did):
    return {x['id']: x for x in Be.call('qs_start')[1]['dokumente']}[did]


def sitzung_frei(query):
    """Läuft ein Download (Antwort noch nicht gelesen), antwortet eine weitere Anfrage derselben Sitzung trotzdem"""
    laeuft = Be.http.open(urllib.request.Request(API + query, headers={'X-Forwarded-For': Be.ip}))
    try:
        st = roh(Be, 'qs_start', timeout=10)[0]
    except OSError:
        st = None
    laeuft.close()
    return st == 200


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
K = {}
for i, (u, n, p, rechte) in enumerate((('bernd', 'Bernd Bearbeiter', 'Bearbeit-Konto-34', ['qs.bearbeiten']), ('vera', 'Vera Verwalten', 'Verwalt-Konto-90', ['qs.verwalten']),
                                       ('fritz', 'Fritz Freigabe', 'Freigabe-Konto-78', ['qs.freigeben']))):
    st, r = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': 'editor', 'active': True, 'password': p, 'mustChange': False, 'grant': rechte})
    assert st == 200, r
    K[u] = Client(f'198.51.100.{11 + i}'); K[u].call('login', {'username': u, 'password': p})
Be, V, F = K['bernd'], K['vera'], K['fritz']
check('Kapitel', V.call('qs_stamm_save', {'kapitel': [{'id': '1.4', 'titel': 'Qualitätssicherung', 'zustaendig': ''}], 'personen': []})[0] == 200)

NEU = {'mov', 'mp4', 'm4v', 'heic', 'heif', 'tif', 'tiff', 'bmp', 'zip', 'xlsb', 'opus', 'ogg', 'json', 'ics', 'ttv'}
GEFAEHRLICH = ['html', 'htm', 'xhtml', 'svg', 'js', 'exe', 'com', 'scr', 'msi', 'bat', 'cmd', 'ps1', 'vbs', 'jar', 'hta', 'lnk', 'reg', 'php']
st, r = Be.call('qs_start')
a = r.get('ablage', {})
check('Einstellungen für die Oberfläche: 250 MB je Datei, Teile zu 3 MB', st == 200 and a.get('max') == GRENZE and a.get('teil') == TEIL, a)
check('Einstellungen: neue Arten erlaubt, ausführbare nie', NEU <= set(a.get('arten', [])) and not set(GEFAEHRLICH) & set(a.get('arten', [])), a.get('arten'))

st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Sammelordner'})
O = r['dokument']['id']
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F01', 'titel': 'Temperaturliste', 'zustaendig': '', 'aenderungen': 'Neu'})
D, DV = r['dokument']['id'], r['dokument']['versionen'][0]['id']
check('Ordner und gelenktes Dokument angelegt', O and D and DV)

# ── Kopfprüfung der neuen Arten: gültig → abgelegt mit MIME-Typ, gefälscht → 422 ──
GUELTIG = {
    'Rundgang.mp4': (box(b'ftyp', b'isom\0\0\x02\0isomiso2mp41') + box(b'mdat', bytes(64)), 'video/mp4'),
    'Schulung.m4v': (box(b'ftyp', b'M4V \0\0\0\x01M4V mp42isom') + box(b'mdat', bytes(64)), 'video/x-m4v'),
    'Kamera.mov': (box(b'ftyp', b'qt  \0\0\x02\0qt  ') + box(b'moov', bytes(32)), 'video/quicktime'),
    'Lang.mp4': (box(b'ftyp', b'isom\0\0\x02\0' + b'isom' * 11) + box(b'mdat', bytes(64)), 'video/mp4'),   # beginnt mit \0\0\0<
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
    'Ordner.zip': (zip_mit({'Unterordner/tief/Plan.pdf': pdf('Plan'), 'Unterordner/Liste.csv': 'a;b'}), 'application/zip'),
    'Zip64.zip': (zip64(zip_mit({'Hinweis.txt': 'Prüfung', 'Bilder/Foto.jpg': b'\xff\xd8\xff'})), 'application/zip'),
    'Mappe.xlsb': (zip_mit({'[Content_Types].xml': '<Types/>', 'xl/workbook.bin': b'\x83\x01\0'}), 'application/vnd.ms-excel.sheet.binary.macroEnabled.12'),
    'Geschützt.docx': (CFB, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    'Geschützt.xlsx': (CFB, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    'Messwerte.json': (b'{"messung": [3.5, 4.0]}\n', 'application/json'),
    'Termin.ics': (b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n', 'text/calendar'),
    'Kuehlhaus.ttv': (b'wd2\xcd{#\0\x01' + bytes(range(256)), 'application/octet-stream'),
    'Messung.ttv': (b'\0\0\0<' + bytes(range(256)), 'application/octet-stream'),
}
assert GUELTIG['Leer.zip'][0][:4] == b'PK\x05\x06', 'leeres ZIP: nur das Ende des Verzeichnisses'
assert GUELTIG['Lang.mp4'][0][:4] == b'\0\0\0<', 'ftyp-Block mit 60 Bytes'
assert len(CFB) == 512 + 1024, 'CFB-Kopf hat 512 Bytes'
assert zipfile.ZipFile(io.BytesIO(GUELTIG['Zip64.zip'][0])).namelist() == ['Hinweis.txt', 'Bilder/Foto.jpg'], 'Zip64-Ende lesbar'
ids = {}
for name, (inhalt, mime) in GUELTIG.items():
    st, r = hochladen(Be, O, '', name, inhalt)
    ids[name] = r.get('datei')
    e = next((f for f in (r.get('dokument') or {}).get('dateien', []) if f['id'] == r.get('datei')), {})
    check(f'{name}: abgelegt als {mime}', st == 200 and e.get('mime') == mime and e.get('groesse') == len(inhalt), (st, r.get('error'), e.get('mime')))

HTML = b'<html><script>alert(1)</script></html>'
GEFAELSCHT = {name: pdf('kein ' + name) for name in GUELTIG if not name.endswith(('.json', '.ics', '.ttv'))}
GEFAELSCHT.update({'Marke.heic': box(b'ftyp', b'isom\0\0\0\0isom') + bytes(32), 'Messwerte.json': HTML, 'Termin.ics': HTML,
                   'Programm.ttv': b'MZ\x90\0' + bytes(200), 'Seite.ttv': HTML, 'Programm.mp4': b'MZ\x90\0ftypisom' + bytes(64),
                   'Programm.heic': b'MZ\x90\0ftypheic' + bytes(16), 'Leer.docx': zip_mit({}), 'Leerraum.ttv': b' \n\t' + HTML,
                   'Nul.json': b'\0\0' + HTML})
for name, inhalt in GEFAELSCHT.items():
    st, r = hochladen(Be, O, '', name, inhalt)
    check(f'{name} mit fremdem Inhalt → 422', st == 422 and 'passt nicht' in r.get('error', ''), (st, r))

MZ = b'MZ\x90\0' + bytes(100)
for name, eintraege in (('Programm.zip', {'setup.exe': MZ}), ('Seite.zip', {'Ordner/SEITE.HTML': HTML}), ('Tief.zip', {'a/b/c/skript.js': 'x'}),
                        ('Punkt.zip', {'Rechnung.exe.': MZ}), ('Zip64 mit Programm.zip', zip64(zip_mit({'tools/run.bat': 'x'})))):
    st, r = hochladen(Be, O, '', name, eintraege if isinstance(eintraege, bytes) else zip_mit(eintraege))
    check(f'{name}: gesperrte Art im ZIP → 422', st == 422 and 'gesperrte Dateiart' in r.get('error', ''), (st, r))
gut = zip_mit({'Hinweis.txt': 'x'})
verschoben = gut[:-6] + struct.pack('<I', 5) + gut[-2:]
for name, inhalt in (('Kaputt.zip', b'PK\x03\x04' + bytes(100)), ('Verschoben.zip', verschoben)):
    st, r = hochladen(Be, O, '', name, inhalt)
    check(f'{name}: Verzeichnis nicht lesbar → 422', st == 422 and 'beschädigt' in r.get('error', ''), (st, r))

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
GROSS, GROSS_SHA = r.get('datei'), hashlib.sha256(gross).hexdigest()
check(f'genau 250 MB in {-(-GRENZE // TEIL)} Teilen abgelegt ({dauer:.1f} s)', st == 200 and e.get('groesse') == GRENZE and e.get('sha256') == GROSS_SHA, (st, r.get('error')))
check('Excel über 25 MB: nicht in den Speicher gelesen, keine Platzhalter', st == 200 and 'platzhalter' not in e, e)
check('keine Reste der Teile', not [f for f in os.listdir(os.path.join(ABLAGE, '.teile'))])
st, h, inhalt = roh(Be, 'qs_datei&id=' + str(GROSS))
check('Download der 250-MB-Datei: vollständig und gleich', st == 200 and h.get('content-length') == str(GRENZE) and hashlib.sha256(inhalt).hexdigest() == GROSS_SHA)
del gross, inhalt
check('Download einer großen Datei: weitere Anfragen derselben Sitzung warten nicht', sitzung_frei('qs_datei&id=' + str(GROSS)))
check('ZIP-Export mit Entwürfen (enthält die 250-MB-Datei): weitere Anfragen derselben Sitzung warten nicht', sitzung_frei('qs_ablage_export&alle=1'))

# ── Freigabe mit Excel über 25 MB: Lenkungsangaben nur in die kleine Datei, Grund im Verlauf ──
check('eingereicht', Be.call('qs_version_schritt', {'dokument': D, 'rev': dok(D)['rev'], 'schritt': 'einreichen'})[0] == 200)
st, r = F.call('qs_version_schritt', {'dokument': D, 'rev': dok(D)['rev'], 'schritt': 'pruefen_freigeben'})
v = r['dokument']['versionen'][0] if st == 200 else {}
verlauf = ' | '.join(x.get('was', '') for x in v.get('verlauf', []))
check('Freigabe: große Datei bleibt unverändert, Verlauf nennt den Grund (zu groß zum Ausfüllen, nicht „nicht lesbar“)', st == 200 and v['status'] == 'freigegeben'
      and 'Lenkungsangaben in „Liste groß.xlsx“ nicht eingetragen (Datei ist über' in verlauf and 'zu groß zum Ausfüllen' in verlauf and 'nicht lesbar' not in verlauf, verlauf)

# ── Überarbeitung übernimmt die Dateien als festen Verweis: keine Kopie von 250 MB, Löschen der Übernahme lässt das Original ──
t0 = time.time()
st, r = Be.call('qs_version_save', {'dokument': D, 'aenderungen': 'Grenzwerte', 'grund': 'Audit', 'dateien': True})
dauer = time.time() - t0
kop = {f['name']: f for f in r['dokument']['versionen'][-1].get('dateien', [])} if st == 200 else {}
k = kop.get('Liste groß.xlsx', {})
check(f'Überarbeitung: 250 MB übernommen ({dauer:.1f} s), neue Kennung, Größe und Prüfsumme gleich, keine Platzhalter', st == 200 and k.get('id') not in (None, GROSS)
      and k.get('groesse') == GRENZE and k.get('sha256') == GROSS_SHA and 'platzhalter' not in k, (st, r.get('error'), k))
check('Übernahme der kleinen Datei: Platzhalter erkannt', 'nr' in kop.get('Liste klein.xlsx', {}).get('platzhalter', []), kop.get('Liste klein.xlsx'))
st, r = Be.call('qs_datei_entfernen', {'datei': k.get('id'), 'rev': dok(D)['rev'], 'grund': ''})
st2, _, inhalt = roh(Be, 'qs_datei&id=' + str(GROSS))
check('Übernahme im Entwurf gelöscht: Original vollständig, Übernahme weg', st == 200 and st2 == 200 and hashlib.sha256(inhalt).hexdigest() == GROSS_SHA
      and roh(Be, 'qs_datei&id=' + str(k.get('id')))[0] == 404, (st, r.get('error'), st2))
del inhalt

st, r = Be.call('qs_datei_hochladen', {'dokument': O, 'version': '', 'name': 'zu groß.mp4', 'groesse': GRENZE + 1, 'sha256': '', 'upload': '', 'teil': 0,
                                       'daten': base64.b64encode(GUELTIG['Rundgang.mp4'][0]).decode()})
check('250 MB + 1 Byte → 422 schon beim ersten Teil', st == 422 and '250 MB' in r.get('error', ''), r)

print(f'{sum(res)}/{len(res)} passed')
