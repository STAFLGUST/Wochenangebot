"""Container-Import: Dokumente je Container (app/api/module/containerimport/dokumente.php, Oberfläche dokumente.js; Auftrag
des Inhabers 20.11.2026). Alle Dateiarten eines echten Containerordners werden abgelegt – mit selbst erzeugten Beispieldateien
ohne echten Inhalt (GR-007).

Geprüft: Rechte (ohne Anmeldung 401, ohne „EUDR ansehen“ 403 für Liste, Download und ZIP; nur ansehen: alles sehen und
herunterladen, auch die Kalkulation, aber nicht hochladen, Arten ändern, entfernen oder die Checkliste ändern; GET auf
schreibende Aktion); Hochladen in Teilen (PDF mehrseitig über 5 MB, .xls und .doc und .msg mit OLE-Kopf, .xlsx, .docx, .eml
mit Base64-Bild, Bilder .png und .jpg) mit SHA-256, Größe, MIME-Typ, wer/wann und Schnappschuss von Partie, Akte, Containernummer und Lieferant
(GR-106, bleibt nach einer Änderung des Containers); falsche und getarnte Arten abgelehnt (Programm als .pdf, HTML als .eml,
ZIP als .xls, .zip und .exe am Container) ohne Reste; doppelte Datei; mehrere Arten je Datei (Sammel-PDF) und Zähler je Art;
ungültige Arten; Checkliste mit „nicht nötig“ und „wieder nötig“ als Vermerk; Arten ändern im Verlauf; Entfernen nur mit
Grund, Datei bleibt abrufbar, doppelt 409, danach keine Art-Änderung; Nachreichen an archivierten Containern; Download
(attachment, nosniff, Inhalt gleich, unbekannt 404); ZIP mit Ordner je erster Art, _entfernt, index.csv mit allen Arten und
Prüfsummen; Protokoll ohne Dateinamen und Gründe; Speicherung unter dateien/containerimport/ ohne Reste in .teile, Verweise
für die Sicherung erkannt (deploy/dateien_sichern.py verweise und aufbauen); Rückfall: das Dokument der Container bleibt
unberührt, Felder einer späteren Version bleiben; „upload“ als Zahl; Upload-Kennung eines anderen Containers oder Nutzers;
ZIP mit checkliste.csv, langen Namen (Endung bleibt) und gleichen Namen, CSV-Injection in index.csv neutralisiert;
containerimport-dokumente-zahlen (mitgeführt, gelesen, fehlt → aus dem Hauptdokument). Vorschlag der Arten aus dem Dateinamen
(Tabelle gegen die Regeln des Servers). Oberfläche: Auswahl und Ziehen-und-Ablegen mehrerer Dateien, Pflicht zur Art,
Fortschritt, Kacheln, PDF- und Bild-Vorschau gezeichnet, Arten ändern, Entfernen mit und ohne Grund, „Entfernte anzeigen“,
Zähler in der Liste folgt den Aktionen, 401 beim Hochladen zeigt die Anmeldung, Leseransicht, 1280 und 390 px (hell und
dunkel, Miniatur sichtbar), keine JavaScript-Fehler.
"""
import base64
import csv
import glob
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from email.message import EmailMessage
from pathlib import Path

from playwright.sync_api import sync_playwright

from containerimport_hilfe import check, ende, nutzer_anlegen, container, container_anlegen, seite as seite_oeffnen
from kunden_hilfe import Client, API
from umgebung import REPO, SH, ablageordner, shot, storage_raw, storage_write, _json

MB = 1024 * 1024
TEIL = 2 * MB   # wie die Oberfläche
ABLAGE = os.path.join(ablageordner(), 'dateien')


# ---------- selbst erzeugte Beispieldateien (kein echter Inhalt) ----------
def pdf(seiten, text, fuellen=0):
    """Gültige PDF mit Text und farbiger Fläche je Seite; fuellen = Bytes eines unbenutzten Datenstroms (große Datei)"""
    objekte = [b'<< /Type /Catalog /Pages 2 0 R >>', None, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kinder = []
    for s in range(seiten):
        inhalt = f'0.15 0.35 0.7 rg 60 520 470 260 re f BT /F1 28 Tf 72 460 Td ({text} Seite {s + 1}) Tj ET'.encode()
        objekte.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {len(objekte) + 2} 0 R >>'.encode())
        kinder.append(len(objekte))
        objekte.append(b'<< /Length %d >>\nstream\n' % len(inhalt) + inhalt + b'\nendstream')
    objekte[1] = ('<< /Type /Pages /Kids [' + ' '.join(f'{k} 0 R' for k in kinder) + f'] /Count {seiten} >>').encode()
    if fuellen:
        objekte.append(b'<< /Length %d >>\nstream\n' % fuellen + os.urandom(fuellen) + b'\nendstream')
    aus, lagen = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'), []
    for i, o in enumerate(objekte):
        lagen.append(len(aus)); aus += f'{i + 1} 0 obj\n'.encode() + o + b'\nendobj\n'
    xref = len(aus)
    aus += f'xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n'.encode() + b''.join(f'{l:010d} 00000 n \n'.encode() for l in lagen)
    aus += f'trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return bytes(aus)


def ooxml(teil, text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr(teil, f'<?xml version="1.0"?><x>{text}</x>')
    return b.getvalue()


def ole(merkmal, n=6144):   # Kopf eines OLE-Containers (altes .xls, .doc, Outlook-.msg), danach ein Merkmal, damit die Dateien verschieden sind
    kopf = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1' + b'\0' * 16 + struct.pack('<HH', 0x3E, 3) + b'\xFE\xFF' + b'\0' * 482 + merkmal.encode()
    return kopf + b'\0' * (n - len(kopf))


def png(breite=120, hoehe=120):
    zeilen = b''.join(b'\0' + os.urandom(breite * 3) for _ in range(hoehe))
    block = lambda art, d: struct.pack('>I', len(d)) + art + d + struct.pack('>I', zlib.crc32(art + d))
    return b'\x89PNG\r\n\x1a\n' + block(b'IHDR', struct.pack('>IIBBBBB', breite, hoehe, 8, 2, 0, 0, 0)) + block(b'IDAT', zlib.compress(zeilen)) + block(b'IEND', b'')


def eml():
    m = EmailMessage()
    m['From'] = 'spedition@example.org'; m['To'] = 'import@example.org'; m['Subject'] = 'Buchungsbestätigung Testcontainer'
    m.set_content('Guten Tag,\nanbei die Unterlagen zum Testcontainer.\n')
    m.add_attachment(png(), maintype='image', subtype='png', filename='foto.png')
    return bytes(m)


GROSS = pdf(36, 'Sammeldokument', fuellen=5 * MB + 300 * 1024)
DATEIEN = {   # Name → (Inhalt, Arten)
    'G-CONF-0001.pdf': (pdf(2, 'Kaufbestaetigung'), ['kaufbestaetigung']),
    'DOCS_TEST_0001.pdf': (GROSS, ['bl', 'handelsrechnung', 'packliste', 'gesundheit', 'ursprung']),   # Reihenfolge der Eingabe egal
    'shipment_details.xls': (ole('xls'), ['shipment']),
    'Meldung_Containerversicherung.docx': (ooxml('word/document.xml', 'Versicherung'), ['versicherung']),
    'Kalkulation Test.xlsx': (ooxml('xl/workbook.xml', 'Kalkulation'), ['kalkulation']),
    'Spedition Mail.eml': (eml(), ['email', 'spedition']),
    'Nachricht.msg': (ole('msg'), ['email']),
    'Altes Zertifikat.doc': (ole('doc'), ['echtheit']),
}


def hochladen(cli, sendung, name, inhalt, arten, teil=TEIL, sha=None):
    """In Teilen hochladen wie die Oberfläche → (Status, Antwort des letzten Aufrufs, Zahl der Aufrufe)"""
    upload, nr, n = '', 0, 0
    pruef = hashlib.sha256(inhalt).hexdigest() if sha is None else sha
    while True:
        st, r = cli.call('containerimport_dokument_hochladen', {'sendung': sendung, 'arten': arten, 'name': name, 'groesse': len(inhalt), 'sha256': pruef,
                                                               'upload': upload, 'teil': nr, 'daten': base64.b64encode(inhalt[nr * teil:(nr + 1) * teil]).decode()})
        n += 1
        if st != 200 or r.get('fertig'):
            return st, r, n
        upload = r['upload']; nr += 1


def roh(cli, query):
    import urllib.error, urllib.request
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def blobs():
    return sorted(glob.glob(os.path.join(ABLAGE, 'containerimport', '*', '*.bin')))


def teile_reste():
    return glob.glob(os.path.join(ABLAGE, '.teile', '*'))


def liste(cli, sid):
    return cli.call('containerimport_dokumente&sendung=' + sid)


A, I, L = nutzer_anlegen()
A.call('user_save', {'id': '', 'name': 'Ole Ohne', 'username': 'ole', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
O = Client('198.51.100.30')
assert O.call('login', {'username': 'ole', 'password': 'Leserin-Zugang-1'})[0] == 200
c1 = container_anlegen(I, 'P-DOK-1', akte='A-7001', container='MSKU 907032 3')
c2 = container_anlegen(I, 'P-DOK-2')
arch = container_anlegen(I, 'P-DOK-ARCH', aktiv=False)
sendungen_vorher = storage_raw('containerimport-eudr-sendungen')

# ---------- Rechte ----------
check('ohne Anmeldung: Liste 401', Client('198.51.100.31').call('containerimport_dokumente&sendung=' + c1['id'])[0] == 401)
check('ohne „EUDR ansehen“: Liste, ZIP und Hochladen 403', [liste(O, c1['id'])[0], roh(O, 'containerimport_dokumente_zip&sendung=' + c1['id'])[0],
      hochladen(O, c1['id'], 'a.pdf', pdf(1, 'x'), ['sonst'])[0]] == [403, 403, 403])
check('nur ansehen: Hochladen 403', hochladen(L, c1['id'], 'a.pdf', pdf(1, 'x'), ['sonst'])[0] == 403)
check('GET auf eine schreibende Aktion wird abgelehnt', I.call('containerimport_dokument_hochladen')[0] in (403, 405))
check('unbekannter Container: Liste 404, Hochladen 404', liste(I, 'gibt-es-nicht')[0] == 404 and hochladen(I, 'gibt-es-nicht', 'a.pdf', pdf(1, 'x'), ['sonst'])[0] == 404)
check('leere Liste eines neuen Containers (Zahlen als Objekt)', liste(I, c1['id']) == (200, {'ok': True, 'dokumente': {}, 'dokDateien': [], 'dokVermerke': []}), liste(I, c1['id']))
check('Stand der Seite ohne Dokumente: Zahlen als Objekt', I.call('containerimport_start')[1]['dokumente'] == {})

# ---------- alle Dateiarten des Containerordners ----------
ids = {}
for name, (inhalt, arten) in DATEIEN.items():
    st, r, n = hochladen(I, c1['id'], name, inhalt, arten)
    e = next((f for f in r.get('dokDateien', []) if f['id'] == r.get('id')), {})
    ids[name] = e.get('id')
    soll_teile = -(-len(inhalt) // TEIL)
    check(f'abgelegt: {name} ({len(inhalt) // 1024} KB in {n} Teilen)', st == 200 and n == soll_teile and e.get('sha256') == hashlib.sha256(inhalt).hexdigest()
          and e.get('groesse') == len(inhalt) and e.get('name') == name and e.get('endung') == name.rsplit('.', 1)[1], (st, r.get('error'), n))
d = liste(I, c1['id'])[1]
gross = next(f for f in d['dokDateien'] if f['name'] == 'DOCS_TEST_0001.pdf')
check('Sammel-PDF über 5 MB mit fünf Arten in fester Reihenfolge der Liste', len(GROSS) > 5 * MB and gross['arten'] == ['handelsrechnung', 'packliste', 'gesundheit', 'ursprung', 'bl'], gross['arten'])
check('Metadaten: MIME-Typ, wer (Name und Kennung), wann, Schnappschuss des Containers',
      gross['mime'] == 'application/pdf' and gross['hochgeladen']['von'] == 'Ina Import' and gross['hochgeladen']['vonId'] and gross['hochgeladen']['t'].endswith('Z')
      and gross['schnappschuss'] == {'partie': 'P-DOK-1', 'akte': 'A-7001', 'container': 'MSKU 907032 3', 'lieferant': 'Frigorifico Beispiel', 'nummer': ''}
      and gross['verlauf'] == [] and 'entfernt' not in gross, gross)
check('MIME-Typen der übrigen Arten', {f['endung']: f['mime'] for f in d['dokDateien']} == {'pdf': 'application/pdf', 'xls': 'application/vnd.ms-excel',
      'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'eml': 'message/rfc822', 'msg': 'application/vnd.ms-outlook', 'doc': 'application/msword'})
z = d['dokumente'][c1['id']]
check('Zähler je Art: eine Datei zählt bei jeder ihrer Arten', z['anzahl'] == 8 and z['arten'] == {'kaufbestaetigung': 1, 'handelsrechnung': 1, 'packliste': 1, 'gesundheit': 1, 'ursprung': 1, 'bl': 1,
      'shipment': 1, 'versicherung': 1, 'kalkulation': 1, 'email': 2, 'spedition': 1, 'echtheit': 1} and z['nichtNoetig'] == [], z)
check('Stand der Seite bringt Zähler und Regeln (Arten, Vorschläge, Endungen)', (lambda s: s['dokumente'][c1['id']]['anzahl'] == 8 and len(s['dokRegeln']['arten']) == 19
      and {'eml', 'jpg', 'jpeg', 'png'} <= set(s['dokRegeln']['endungen']) and s['dokRegeln']['vorschlaege'][0][1] == ['email'])(I.call('containerimport_start')[1]))
check('Dateien liegen als .bin unter dateien/containerimport/, keine Reste unter .teile', len(blobs()) == 8 and not teile_reste()
      and all(open(os.path.join(ABLAGE, 'containerimport', i[:2], i + '.bin'), 'rb').read() == DATEIEN[n][0] for n, i in ids.items()), (len(blobs()), teile_reste()))

# ---------- falsche und getarnte Arten ----------
for name, inhalt, text in [('rechnung.pdf', b'MZ\x90\0' + b'\0' * 2000, 'passt nicht'), ('mail.eml', b'<html><script>alert(1)</script></html>', 'passt nicht'),
                           ('foto.png', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', 'passt nicht'), ('foto.jpg', b'GIF89a' + b'\0' * 100, 'passt nicht'),
                           ('tabelle.xls', ooxml('xl/workbook.xml', 'x'), 'passt nicht'), ('archiv.zip', ooxml('a.xml', 'x'), 'PDF-, Word-, Excel-'),
                           ('programm.exe', b'MZ' + b'\0' * 100, 'PDF-, Word-, Excel-'), ('notiz.txt', b'Text', 'PDF-, Word-, Excel-')]:
    st, r, _ = hochladen(I, c1['id'], name, inhalt, ['sonst'])
    check(f'abgelehnt: {name}', st == 422 and text in r.get('error', ''), (st, r))
st, r = I.call('containerimport_dokument_hochladen', {'sendung': c1['id'], 'arten': ['sonst'], 'name': 'archiv.zip', 'groesse': 200, 'upload': 0, 'teil': 0,
                                                      'daten': base64.b64encode(ooxml('a.xml', 'x')[:200]).decode()})
check('„upload“ als Zahl umgeht die Prüfung des ersten Teils nicht (Endung)', st == 422 and 'PDF-, Word-, Excel-' in r.get('error', ''), (st, r))
check('abgelehnte Dateien hinterlassen nichts', len(blobs()) == 8 and not teile_reste() and liste(I, c1['id'])[1]['dokumente'][c1['id']]['anzahl'] == 8)
st, r, _ = hochladen(I, c1['id'], 'Kopie.pdf', DATEIEN['G-CONF-0001.pdf'][0], ['kaufbestaetigung'])
check('dieselbe Datei noch einmal am selben Container: 422, nichts abgelegt', st == 422 and 'liegt schon' in r.get('error', '') and len(blobs()) == 8, r)
check('dieselbe Datei an einem anderen Container ist erlaubt', hochladen(I, c2['id'], 'G-CONF-0001.pdf', DATEIEN['G-CONF-0001.pdf'][0], ['kaufbestaetigung'])[0] == 200)
for arten, was in [([], 'keine Art'), (['gibtsnicht'], 'unbekannte Art'), ('kalkulation', 'Text statt Liste')]:
    check(f'Arten ungültig ({was}): 422', hochladen(I, c1['id'], 'x.pdf', pdf(1, 'y'), arten)[0] == 422)
check('Prüfsumme passt nicht: 422', hochladen(I, c1['id'], 'x.pdf', pdf(1, 'z'), ['sonst'], sha='0' * 64)[0] == 422)
check('archivierter Container: Unterlagen lassen sich nachreichen', hochladen(I, arch['id'], 'Nachgereicht.pdf', pdf(1, 'spaet'), ['eudr'])[0] == 200)

# ---------- Checkliste ----------
cl = lambda b, cli=I: cli.call('containerimport_dokument_checkliste', {'sendung': c1['id'], **b})
st, r = cl({'art': 'lot', 'noetig': False})
check('Checkliste: „nicht nötig“ vermerkt', st == 200 and r['dokumente'][c1['id']]['nichtNoetig'] == ['lot'] and r['dokVermerke'][-1]['art'] == 'lot' and r['dokVermerke'][-1]['noetig'] is False
      and r['dokVermerke'][-1]['von'] == 'Ina Import', r)
check('Checkliste: doppelt 422, Art ohne Platzhalter 422, ohne Angabe 422, nur ansehen 403',
      [cl({'art': 'lot', 'noetig': False})[0], cl({'art': 'halal', 'noetig': False})[0], cl({'art': 'lot'})[0], cl({'art': 'eudr', 'noetig': False}, L)[0]] == [422, 422, 422, 403])
cl({'art': 'eudr', 'noetig': False}); st, r = cl({'art': 'eudr', 'noetig': True})
check('Checkliste: „wieder nötig“ hebt auf, alle Vermerke bleiben', st == 200 and r['dokumente'][c1['id']]['nichtNoetig'] == ['lot'] and [v['art'] for v in r['dokVermerke']] == ['lot', 'eudr', 'eudr'], r.get('dokVermerke'))

# ---------- Arten ändern ----------
xid = ids['shipment_details.xls']
st, r = I.call('containerimport_dokument_arten', {'id': xid, 'arten': ['sonst', 'shipment']})
f = next(x for x in r['dokDateien'] if x['id'] == xid)
check('Arten geändert, Verlauf mit alt/neu und wer', st == 200 and f['arten'] == ['shipment', 'sonst'] and len(f['verlauf']) == 1
      and f['verlauf'][0]['alt'] == ['shipment'] and f['verlauf'][0]['neu'] == ['shipment', 'sonst'] and f['verlauf'][0]['von'] == 'Ina Import', f)
check('Arten ändern: gleich 422, leer 422, unbekannt 404, nur ansehen 403', [I.call('containerimport_dokument_arten', {'id': xid, 'arten': ['shipment', 'sonst']})[0],
      I.call('containerimport_dokument_arten', {'id': xid, 'arten': []})[0], I.call('containerimport_dokument_arten', {'id': 'x' * 20, 'arten': ['sonst']})[0],
      L.call('containerimport_dokument_arten', {'id': xid, 'arten': ['sonst']})[0]] == [422, 422, 404, 403])

# ---------- Entfernen ----------
mid = ids['Nachricht.msg']
check('Entfernen ohne Grund 422, nur ansehen 403', I.call('containerimport_dokument_entfernen', {'id': mid, 'grund': '  '})[0] == 422
      and L.call('containerimport_dokument_entfernen', {'id': mid, 'grund': 'x'})[0] == 403)
st, r = I.call('containerimport_dokument_entfernen', {'id': mid, 'grund': 'Doppelt abgelegt (Test)'})
f = next(x for x in r['dokDateien'] if x['id'] == mid)
check('entfernt vermerkt mit Grund, wer und wann; Zähler ohne die Datei', st == 200 and f['entfernt']['grund'] == 'Doppelt abgelegt (Test)' and f['entfernt']['von'] == 'Ina Import'
      and r['dokumente'][c1['id']]['anzahl'] == 7 and r['dokumente'][c1['id']]['arten']['email'] == 1, f)
code, kopf, inhalt = roh(L, 'containerimport_dokument&id=' + mid)
check('entfernte Datei bleibt abrufbar (Leser) und liegt in der Ablage', code == 200 and inhalt == DATEIEN['Nachricht.msg'][0] and len(blobs()) == 10)
check('nochmals entfernen 409, Arten einer entfernten Datei ändern 409', I.call('containerimport_dokument_entfernen', {'id': mid, 'grund': 'x'})[0] == 409
      and I.call('containerimport_dokument_arten', {'id': mid, 'arten': ['sonst']})[0] == 409)

# ---------- Leser, Download ----------
st, r = liste(L, c1['id'])
kid = ids['Kalkulation Test.xlsx']
check('nur ansehen: sieht alle Dateien samt entfernter und Kalkulation', st == 200 and len(r['dokDateien']) == 8 and any(f['id'] == kid for f in r['dokDateien']))
code, kopf, inhalt = roh(L, 'containerimport_dokument&id=' + kid)
check('Download der Kalkulation für Leser: Inhalt gleich, attachment mit Namen, nosniff, sandbox', code == 200 and inhalt == DATEIEN['Kalkulation Test.xlsx'][0]
      and kopf.get('content-disposition', '').startswith('attachment;') and 'Kalkulation%20Test.xlsx' in kopf.get('content-disposition', '')
      and kopf.get('x-content-type-options') == 'nosniff' and 'sandbox' in kopf.get('content-security-policy', ''), kopf)
check('Download ohne Recht 403, unbekannt 404', roh(O, 'containerimport_dokument&id=' + kid)[0] == 403 and roh(L, 'containerimport_dokument&id=' + 'a' * 20)[0] == 404)

# ---------- ZIP ----------
code, kopf, inhalt = roh(L, 'containerimport_dokumente_zip&sendung=' + c1['id'])
zf = zipfile.ZipFile(io.BytesIO(inhalt))
namen = sorted(zf.namelist())
w = 'Dokumente P-DOK-1/'
check('ZIP: Ordner je erster Art, entfernte unter _entfernt, index.csv', code == 200 and namen == sorted([w + 'index.csv', w + 'checkliste.csv', w + 'Kaufbestätigung/G-CONF-0001.pdf', w + 'Handelsrechnung/DOCS_TEST_0001.pdf',
      w + 'Shipment details/shipment_details.xls', w + 'Versicherungsanmeldung/Meldung_Containerversicherung.docx', w + 'Kalkulation/Kalkulation Test.xlsx',
      w + 'Spedition - Buchungsbestätigung/Spedition Mail.eml', w + '_entfernt/E-Mail - Schriftverkehr/Nachricht.msg', w + 'Echtheitszertifikat (Hilton, Angus)/Altes Zertifikat.doc']), namen)
check('ZIP: Inhalte unverändert (Originalformat)', zf.read(w + 'Handelsrechnung/DOCS_TEST_0001.pdf') == GROSS and zf.read(w + '_entfernt/E-Mail - Schriftverkehr/Nachricht.msg') == DATEIEN['Nachricht.msg'][0])
idx = list(csv.reader(io.StringIO(zf.read(w + 'index.csv').decode('utf-8-sig')), delimiter=';'))
zeile = {r[1]: r for r in idx[1:]}
check('index.csv: alle Arten, Prüfsumme, Schnappschuss, Verlauf, Entfernen mit Grund, Pfad im ZIP', len(idx) == 9
      and zeile['DOCS_TEST_0001.pdf'][2] == 'Handelsrechnung, Packliste, Gesundheitszertifikat, Ursprungszeugnis, B/L (Konnossement)'
      and zeile['DOCS_TEST_0001.pdf'][5] == hashlib.sha256(GROSS).hexdigest() and zeile['DOCS_TEST_0001.pdf'][9] == 'A-7001'
      and 'Shipment details → Shipment details, Sonstiges' in zeile['shipment_details.xls'][12] and zeile['Nachricht.msg'][15] == 'Doppelt abgelegt (Test)'
      and zeile['Nachricht.msg'][16] == '_entfernt/E-Mail - Schriftverkehr/Nachricht.msg', idx[:3])
ckl = list(csv.reader(io.StringIO(zf.read(w + 'checkliste.csv').decode('utf-8-sig')), delimiter=';'))
check('checkliste.csv: alle Vermerke der Checkliste mit Art, nötig/nicht nötig, wer und wann', ckl[0] == ['Dokumentart', 'Vermerk', 'vermerkt von', 'vermerkt am (UTC)']
      and [r[:3] for r in ckl[1:]] == [['Lot-Nummernliste / Rückverfolgbarkeit', 'nicht nötig', 'Ina Import'], ['EUDR-Dokument (Sorgfaltserklärung)', 'nicht nötig', 'Ina Import'],
                                       ['EUDR-Dokument (Sorgfaltserklärung)', 'nötig', 'Ina Import']] and all(r[3].endswith('Z') for r in ckl[1:]), ckl)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Ablegen, Arten ändern, Entfernen, Checkliste, ZIP – ohne Dateinamen und Gründe',
      all(t in log for t in ('am Container „P-DOK-1“ abgelegt', 'Arten von Shipment details zu Shipment details, Sonstiges geändert', 'als entfernt vermerkt',
                             'Checkliste der Dokumente am Container „P-DOK-1“: Lot-Nummernliste / Rückverfolgbarkeit nicht nötig', 'Dokumente des Containers „P-DOK-1“ als ZIP exportiert (8 Dateien)'))
      and 'Doppelt abgelegt' not in log and 'DOCS_TEST_0001' not in log)

# ---------- GR-106, Rückfall, Sicherung ----------
check('Rückfall: Hochladen, Arten, Checkliste und Entfernen lassen das Dokument der Container unberührt', storage_raw('containerimport-eudr-sendungen') == sendungen_vorher)
s1 = container(I.call('containerimport_start')[1], 'P-DOK-1')
st, r = I.call('containerimport_eudr_sendung_save', {**s1, 'akte': 'A-7999'})
check('Schnappschuss bleibt nach Änderung der Akte (GR-106)', st == 200 and next(f for f in liste(I, c1['id'])[1]['dokDateien'] if f['id'] == ids['G-CONF-0001.pdf'])['schnappschuss']['akte'] == 'A-7001', (st, r.get('error')))
roh_dok = _json(storage_raw('containerimport-dokumente'))
check('alle Dateien (auch entfernte) im eigenen Dokument containerimport-dokumente', len(roh_dok['liste']) == 10, len(roh_dok['liste']))
roh_dok['zukunft'] = {'feld': 1}
roh_dok['liste'][0]['spaeter'] = 'bleibt'
storage_write('containerimport-dokumente', roh_dok)
I.call('containerimport_dokument_arten', {'id': roh_dok['liste'][0]['id'], 'arten': ['kaufbestaetigung', 'sonst']})
nach = _json(storage_raw('containerimport-dokumente'))
check('Felder einer späteren Version bleiben beim Schreiben erhalten (GR-006)', nach.get('zukunft') == {'feld': 1} and nach['liste'][0].get('spaeter') == 'bleibt')
sys.path.insert(0, os.path.join(REPO, 'deploy'))
import dateien_sichern  # noqa: E402
verweise = {}
for ordner in {os.environ['UDATA'], os.environ.get('UINTERN') or os.environ['UDATA']}:
    verweise.update(dateien_sichern.verweise(Path(ordner))[0])
alle_ids = [f['id'] for f in nach['liste']]
check('Sicherung erkennt jede Datei als Verweis des Dokuments containerimport-dokumente', all(verweise.get(i, ('',))[0] == 'containerimport-dokumente' for i in alle_ids), [verweise.get(i) for i in alle_ids[:2]])
ziel = tempfile.mkdtemp(prefix='ci-sicherung-')
try:
    p = subprocess.run([sys.executable, os.path.join(REPO, 'deploy', 'dateien_sichern.py'), 'aufbauen', ABLAGE, ziel, '2026-11-20_120000'], capture_output=True, text=True)
    stand = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(ziel, '2026-11-20_120000.tmp', 'containerimport', '*', '*.bin'))}
    check('Sicherung (dateien_sichern.py aufbauen) nimmt den Bereich containerimport auf', p.returncode == 0 and set(alle_ids) <= stand, (p.returncode, p.stderr[-300:], len(stand)))
finally:
    shutil.rmtree(ziel, ignore_errors=True)

# ---------- Bilder, Namen im ZIP, CSV-Injection, fremde Uploads, Zahlen-Dokument ----------
c3 = container_anlegen(I, 'P-DOK-3')
st, r, _ = hochladen(I, c3['id'], 'Foto Zertifikat.png', png(300, 200), ['echtheit'])
st2, r2, _ = hochladen(I, c3['id'], 'Foto Zertifikat.jpg', b'\xff\xd8\xff\xe0' + os.urandom(800), ['echtheit'])   # Kopf eines JPEG
check('Bilder (.png, .jpg) werden angenommen', st == 200 and st2 == 200 and [f['mime'] for f in r2['dokDateien']] == ['image/png', 'image/jpeg'], (st, st2, r2.get('error')))
LANG = 'Nachricht der Spedition zum Container ' + 'Ablage ' * 10 + 'Nachtrag Nr. 1234567.msg'
LANG = LANG[:109] + '.msg'
check('Testname hat 113 Zeichen', len(LANG) == 113)
hochladen(I, c3['id'], LANG, ole('lang'), ['email'])
hochladen(I, c3['id'], 'Rechnung.pdf', pdf(1, 'Rechnung eins'), ['handelsrechnung'])
hochladen(I, c3['id'], 'rechnung.PDF', pdf(1, 'Rechnung zwei'), ['handelsrechnung', 'packliste'])
st, r, _ = hochladen(I, c3['id'], '=HYPERLINK(1+1).pdf', pdf(1, 'Formel'), ['sonst'])
fid = r.get('id')
I.call('containerimport_dokument_entfernen', {'id': fid, 'grund': '=HYPERLINK(2+2)'})
I.call('containerimport_dokument_checkliste', {'sendung': c3['id'], 'art': 'lot', 'noetig': False})
zf3 = zipfile.ZipFile(io.BytesIO(roh(L, 'containerimport_dokumente_zip&sendung=' + c3['id'])[2]))
w3 = 'Dokumente P-DOK-3/'
idx3 = {r[0]: r for r in csv.reader(io.StringIO(zf3.read(w3 + 'index.csv').decode('utf-8-sig')), delimiter=';')}
pfade = {r[1]: r[16] for r in idx3.values()}
check('ZIP: langer Name behält die Endung (nur der Stamm gekürzt), Pfad im ZIP = Spalte in index.csv',
      pfade[LANG].endswith('.msg') and pfade[LANG] == 'E-Mail - Schriftverkehr/' + LANG[:100].rstrip(' .') + '.msg' and w3 + pfade[LANG] in zf3.namelist(), pfade.get(LANG))
check('ZIP: gleich benannte Dateien derselben ersten Art werden unterschieden, index.csv nennt den Pfad',
      {pfade['Rechnung.pdf'], pfade['rechnung.PDF']} == {'Handelsrechnung/Rechnung.pdf', 'Handelsrechnung/rechnung (2).PDF'}
      and all(w3 + pfade[n] in zf3.namelist() for n in ('Rechnung.pdf', 'rechnung.PDF')), pfade)
check('index.csv: Formeln im Dateinamen und im Grund neutralisiert (CSV-Injection)', idx3[fid][1] == "'=HYPERLINK(1+1).pdf" and idx3[fid][15] == "'=HYPERLINK(2+2)", idx3.get(fid))
ckl3 = list(csv.reader(io.StringIO(zf3.read(w3 + 'checkliste.csv').decode('utf-8-sig')), delimiter=';'))
check('checkliste.csv nur mit den Vermerken dieses Containers', [r[:2] for r in ckl3[1:]] == [['Lot-Nummernliste / Rückverfolgbarkeit', 'nicht nötig']], ckl3)
# Upload-Kennung gehört zu Nutzer, Container und Arten
inhalt = pdf(1, 'fremder Upload')
kopf = {'arten': ['sonst'], 'name': 'fremd.pdf', 'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest()}
st, r = I.call('containerimport_dokument_hochladen', {**kopf, 'sendung': c3['id'], 'upload': '', 'teil': 0, 'daten': base64.b64encode(inhalt[:300]).decode()})
weiter = lambda cli, sid: cli.call('containerimport_dokument_hochladen', {**kopf, 'sendung': sid, 'upload': r['upload'], 'teil': 1, 'daten': base64.b64encode(inhalt[300:]).decode()})
fremd_c, fremd_n = weiter(I, c2['id']), weiter(A, c3['id'])
check('Upload-Kennung eines anderen Containers oder Nutzers wird abgelehnt', fremd_c[0] == 422 and fremd_n[0] == 422 and 'anderen Datei' in fremd_c[1].get('error', '')
      and 'anderen Datei' in fremd_n[1].get('error', ''), (fremd_c, fremd_n))
check('… derselbe Upload mit eigenem Container gelingt danach', (lambda x: x[0] == 200 and x[1].get('fertig'))(weiter(I, c3['id'])))
# Zahlen-Dokument: der Stand der Seite liest nur containerimport-dokumente-zahlen
zahlen = _json(storage_raw('containerimport-dokumente-zahlen'))
start = I.call('containerimport_start')[1]['dokumente']
check('containerimport-dokumente-zahlen wird beim Schreiben mitgeführt (gleich dem Stand der Seite)', zahlen['je'] == start and start[c3['id']]['anzahl'] == 6
      and start[c3['id']]['nichtNoetig'] == ['lot'] and zahlen['rev'] == _json(storage_raw('containerimport-dokumente'))['rev'], (zahlen, start.get(c3['id'])))
storage_write('containerimport-dokumente-zahlen', {'rev': 1, 'je': {c3['id']: {'anzahl': 99, 'arten': {}, 'nichtNoetig': []}}})
check('Stand der Seite liest das Zahlen-Dokument, nicht alle Dateien', I.call('containerimport_start')[1]['dokumente'][c3['id']]['anzahl'] == 99)
storage_write('containerimport-dokumente-zahlen', {})
check('fehlt das Zahlen-Dokument (Altbestand), zählt der Stand aus containerimport-dokumente', I.call('containerimport_start')[1]['dokumente'] == start)
I.call('containerimport_dokument_checkliste', {'sendung': c3['id'], 'art': 'lot', 'noetig': True})
check('nächstes Schreiben legt es wieder an', _json(storage_raw('containerimport-dokumente-zahlen'))['je'][c3['id']]['nichtNoetig'] == [])

# ---------- Oberfläche ----------
VORSCHLAEGE = {
    'G-CONF-2026-0001.pdf': ['kaufbestaetigung'], 'Order confirmation 4711.pdf': ['kaufbestaetigung'], 'proforma_invoice_123.pdf': ['proforma'],
    'DOCS_C123_LOTE.pdf': ['handelsrechnung', 'packliste', 'gesundheit', 'ursprung', 'bl'], 'House_Bill_of_Lading_ABC.pdf': ['bl'], 'B_L 12345.pdf': ['bl'], 'BL-12345.pdf': ['bl'],
    'Booking confirmation 123.pdf': ['spedition'], 'Buchungsbestätigung.pdf': ['spedition'], 'shipment_details.xls': ['shipment'],
    'Meldung_Containerversicherung_1.docx': ['versicherung'], 'Kalkulation Container 12.xlsx': ['kalkulation'], 'Mail Spedition.eml': ['email'], 'Nachricht.msg': ['email'],
    'Health certificate.pdf': ['gesundheit'], 'certificado sanitario.pdf': ['gesundheit'], 'Hilton certificate.pdf': ['echtheit'], 'Angus authenticity.pdf': ['echtheit'],
    'Certificado cupo Mercosur.pdf': ['quote'], 'Certificate of origin.pdf': ['ursprung'], 'Original Invoice.pdf': ['handelsrechnung'], 'Salmonella.pdf': ['salmonellen'],
    'Halal.pdf': ['halal'], 'Commercial invoice 99.pdf': ['handelsrechnung'], 'factura 1.pdf': ['handelsrechnung'], 'Packing list.pdf': ['packliste'],
    'Romaneo lote 5.pdf': ['lot'], 'Trazabilidad.pdf': ['lot'], 'EUDR DDS 2026.pdf': ['eudr'], 'scan_0001.pdf': [], 'Pilot.pdf': [], 'Tabelle.xlsx': [],
    # „Hilton“/„Angus“ stehen auch auf anderen Papieren: die Art des Papiers gewinnt; „confirm“ allein ist keine Kaufbestätigung
    'Commercial Invoice Hilton 2026-11.pdf': ['handelsrechnung'], 'Packing list Angus.pdf': ['packliste'], 'Bill of Lading Hilton.pdf': ['bl'],
    'Certificado de origen Hilton.pdf': ['ursprung'], 'Mercosur quota certificate Hilton.pdf': ['quote'], 'Insurance confirmation.pdf': ['versicherung'],
    'Angus certificate No 1.pdf': ['echtheit'], 'Payment confirmation.pdf': [], 'Purchase confirmation 12.pdf': ['kaufbestaetigung'], 'IMG_0001.jpg': [],
}
REGELN = I.call('containerimport_start')[1]['dokRegeln']['vorschlaege']   # Muster in der Schreibweise von JavaScript, hier mit re geprüft


def vorschlag(name):
    return next((arten for muster, arten in REGELN if re.search(muster, name.lower())), [])


vor = {n: vorschlag(n) for n in VORSCHLAEGE}
check('Vorschlag der Arten aus dem Dateinamen (Tabelle)', vor == VORSCHLAEGE, {k: v for k, v in vor.items() if VORSCHLAEGE[k] != v})
errs, fremd = [], []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    p = seite_oeffnen(br, 'ina', errs, fremd)
    zeile = lambda sid: p.inner_text(f'tr[data-sendung="{sid}"] .ci-dok-zahl')
    check('Liste: Zähler am Container (Dokumente, fehlende Platzhalter)', zeile(c1['id']) == '7 Dokumente · 1 fehlt' and zeile(c2['id']).startswith('1 Dokument · '), [zeile(c1['id']), zeile(c2['id'])])
    p.click(f'tr[data-sendung="{c2["id"]}"]'); p.wait_for_selector('#dlg-sendung[open] .ci-dok-kachel')
    check('Fenster: Checkliste mit „fehlt“ und „vorhanden“', 'Kaufbestätigung' in p.inner_text('.ci-dok-check') and p.locator('.ci-dok-check .ci-marke.warn').count() == 10
          and p.locator('.ci-dok-check .ci-marke.ok').count() == 1)
    p.set_input_files('#dok-dateien', [{'name': 'DOCS_C9_LOTE.pdf', 'mimeType': 'application/pdf', 'buffer': pdf(3, 'Sammel')},
                                        {'name': 'Kalkulation Test.xlsx', 'mimeType': 'application/octet-stream', 'buffer': DATEIEN['Kalkulation Test.xlsx'][0]},
                                        {'name': 'Spedition Mail.eml', 'mimeType': 'message/rfc822', 'buffer': DATEIEN['Spedition Mail.eml'][0]},
                                        {'name': 'scan_0001.pdf', 'mimeType': 'application/pdf', 'buffer': pdf(1, 'Scan')},
                                        {'name': 'G-CONF-0001.pdf', 'mimeType': 'application/pdf', 'buffer': DATEIEN['G-CONF-0001.pdf'][0]},
                                        {'name': 'notiz.txt', 'mimeType': 'text/plain', 'buffer': b'Notiz'}])
    p.wait_for_selector('.ci-dok-warte >> nth=5')
    warte = p.locator('.ci-dok-warte')
    check('Warteschlange: Vorschläge gesetzt (Sammel-PDF mit fünf Arten), ohne Treffer Pflicht zur Wahl, Doppelte und fremde Art gesperrt',
          warte.nth(0).locator('input:checked').count() == 5 and warte.nth(1).locator('input[data-art=kalkulation]').is_checked()
          and warte.nth(3).locator('details[open]').count() == 1 and 'Liegt schon' in warte.nth(4).inner_text() and 'Dateiart kann nicht' in warte.nth(5).inner_text()
          and p.is_disabled('#dok-hochladen') and p.inner_text('#dok-hochladen').strip() == '4 Dateien hochladen')
    warte.nth(3).locator('input[data-art=sonst]').check()
    p.wait_for_function("!document.querySelector('#dok-hochladen').disabled")
    shot(p, os.path.join(SH, 'containerimport-dokumente-warteschlange-1280.png'))
    p.click('#dok-hochladen')
    p.wait_for_selector('#ci-toast.zeigen:not(.fehler)')
    check('Hochgeladen: vier neue Kacheln, Warteschlange behält nur die gesperrten', p.locator('.ci-dok-kachel').count() == 5 and p.locator('.ci-dok-warte').count() == 2
          and len(liste(I, c2['id'])[1]['dokDateien']) == 5, p.locator('.ci-dok-kachel').count())
    p.click('#dok-warte-leeren')
    p.wait_for_selector('.ci-dok-bild.gezeichnet canvas')
    gezeichnet = p.evaluate("""() => { const c = document.querySelector('.ci-dok-bild.gezeichnet canvas'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let farbig = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 2] > 120 && d[i] < 90) farbig++; return [c.width, farbig]; }""")
    check('PDF-Vorschau: erste Seite gezeichnet (Fläche der Testseite sichtbar)', gezeichnet[0] == 240 and gezeichnet[1] > 1000, gezeichnet)
    check('Word/Excel/E-Mail: Symbol mit Endung, Arten, Größe und Datum', any(t.startswith('XLSX') for t in p.locator('.ci-dok-endung').all_inner_texts())
          and 'Kalkulation' in p.inner_text('.ci-dok-kacheln') and 'KB' in p.inner_text('.ci-dok-kacheln'))
    # Ziehen und Ablegen
    p.evaluate("""(b64) => { const dt = new DataTransfer(), bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        dt.items.add(new File([bytes], 'Health certificate.pdf', { type: 'application/pdf' }));
        document.querySelector('.ci-dok-ablage').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""", base64.b64encode(pdf(1, 'Gesundheit')).decode())
    p.wait_for_selector('.ci-dok-warte input[data-art=gesundheit]:checked', state='attached')
    p.click('#dok-hochladen'); p.wait_for_function("document.querySelectorAll('.ci-dok-kachel').length === 6")
    check('Ziehen und Ablegen: Datei mit vorgeschlagener Art abgelegt', any(f['name'] == 'Health certificate.pdf' and f['arten'] == ['gesundheit'] for f in liste(I, c2['id'])[1]['dokDateien']))
    # Foto eines Zertifikats (vom Browser erzeugtes JPEG): Vorschlag aus „Hilton“, Miniatur verkleinert gezeichnet
    jpg = p.evaluate("""() => { const c = document.createElement('canvas'); c.width = 900; c.height = 600; const g = c.getContext('2d');
        g.fillStyle = '#2050c0'; g.fillRect(0, 0, 900, 600); g.fillStyle = '#ffffff'; g.fillRect(100, 100, 300, 200); return c.toDataURL('image/jpeg', 0.9).split(',')[1]; }""")
    p.set_input_files('#dok-dateien', [{'name': 'Foto Hilton certificate.jpg', 'mimeType': 'image/jpeg', 'buffer': base64.b64decode(jpg)}])
    p.wait_for_selector('.ci-dok-warte input[data-art=echtheit]:checked', state='attached')
    p.click('#dok-hochladen'); p.wait_for_function("document.querySelectorAll('.ci-dok-kachel').length === 7")
    p.locator('.ci-dok-bild[data-endung=jpg]').scroll_into_view_if_needed()
    p.wait_for_selector('.ci-dok-bild.gezeichnet[data-endung=jpg] canvas')
    foto = p.evaluate("""() => { const c = document.querySelector('.ci-dok-bild[data-endung=jpg] canvas'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let blau = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 2] > 150 && d[i] < 80) blau++; return [c.width, c.height, blau]; }""")
    check('Bild: Miniatur verkleinert gezeichnet (240 × 160, Inhalt sichtbar)', foto[:2] == [240, 160] and foto[2] > 5000, foto)
    shot(p, os.path.join(SH, 'containerimport-dokumente-1280.png'))
    # Arten ändern, Entfernen
    kachel = p.locator('.ci-dok-kachel', has_text='scan_0001.pdf')
    kachel.locator('[data-arten]').click(); kachel.locator('input[data-art=lot]').check(); kachel.locator('[data-arten-speichern]').click()
    p.wait_for_function("[...document.querySelectorAll('.ci-dok-kachel')].some((k) => k.innerText.includes('scan_0001.pdf') && k.innerText.includes('Lot-Nummernliste'))")
    kachel = p.locator('.ci-dok-kachel', has_text='scan_0001.pdf')
    kachel.locator('[data-entfernen]').click(); p.keyboard.press('Enter'); p.wait_for_selector('#ci-toast.zeigen.fehler')
    check('Entfernen ohne Grund: Hinweis, Container wird nicht gespeichert', 'Grund' in p.inner_text('#ci-toast') and p.evaluate("document.querySelector('#dlg-sendung').open"))
    p.fill('#dok-grund', 'Falscher Container (Test)'); p.click('[data-entfernen-ok]'); p.wait_for_selector('#dok-entfernte')
    check('Entfernt: Kachel verschwindet, „Entfernte anzeigen“ zeigt sie mit Grund', p.locator('.ci-dok-kachel').count() == 6)
    p.check('#dok-entfernte'); p.wait_for_selector('.ci-dok-kachel.weg')
    check('Entfernte anzeigen: Grund sichtbar, Verlauf mit allen Vorgängen', 'Falscher Container (Test)' in p.inner_text('.ci-dok-kachel.weg')
          and all(t in p.text_content('.ci-dok-verlauf') for t in ('abgelegt', '„scan_0001.pdf“: Arten Sonstiges → Lot-Nummernliste', 'entfernt: Falscher Container')))
    fehlen_vorher = int(re.search(r'(\d+) fehl', zeile(c2['id'])).group(1))
    p.locator('.ci-dok-check li', has_text='Versicherungsanmeldung').locator('[data-noetig]').click()
    p.wait_for_function("[...document.querySelectorAll('.ci-dok-check li')].some((li) => li.innerText.includes('Versicherungsanmeldung') && li.innerText.includes('wieder nötig'))")
    check('Checkliste: „nicht nötig“ in der Oberfläche vermerkt', 'versicherung' in liste(I, c2['id'])[1]['dokumente'][c2['id']]['nichtNoetig'])
    check('ZIP-Knopf verweist auf den Export des Containers', p.get_attribute('#dok-zip', 'href').endswith('containerimport_dokumente_zip&sendung=' + c2['id']))
    check('Zähler in der Liste folgt den Aktionen im Fenster („nicht nötig“ ohne neues Laden)', f'{fehlen_vorher - 1} fehl' in zeile(c2['id']), zeile(c2['id']))
    # beendete Sitzung während des Hochladens: Anmeldung statt „fehlgeschlagen (401)“
    p.route(lambda url: 'action=containerimport_dokument_hochladen' in url,
            lambda route: route.fulfill(status=401, content_type='application/json', body='{"ok":false,"error":"Nicht angemeldet."}'))
    p.set_input_files('#dok-dateien', [{'name': 'Halal.pdf', 'mimeType': 'application/pdf', 'buffer': pdf(1, 'Halal')}])
    p.wait_for_selector('.ci-dok-warte input[data-art=halal]:checked', state='attached')
    p.click('#dok-hochladen'); p.wait_for_selector('#ci-login:not([hidden])')
    check('401 beim Hochladen: Anmeldung gezeigt, keine Fehlermeldung mit Statuscode', p.is_hidden('#ci-app') and '401' not in (p.text_content('#ci-toast') or ''))
    p.context.close()

    le = seite_oeffnen(br, 'lea', errs, fremd)
    le.click(f'tr[data-sendung="{c1["id"]}"]'); le.wait_for_selector('#dlg-sendung[open] .ci-dok-kachel')
    check('Leser: Kacheln (auch Kalkulation) und ZIP, aber keine Ablage, kein Ändern oder Entfernen', le.locator('#dok-dateien').count() == 0 and le.locator('[data-entfernen], [data-arten], [data-noetig]').count() == 0
          and 'Kalkulation Test.xlsx' in le.inner_text('.ci-dok-kacheln') and le.locator('#dok-zip').count() == 1)
    shot(le, os.path.join(SH, 'containerimport-dokumente-leser-1280.png'))
    le.context.close()

    m = seite_oeffnen(br, 'ina', errs, fremd, {'width': 390, 'height': 844}, 'dark')
    m.click(f'tr[data-sendung="{c1["id"]}"]'); m.wait_for_selector('#dlg-sendung[open] .ci-dok-kachel')
    m.locator('#sendung-dokumente .ci-dok-kachel >> nth=0').scroll_into_view_if_needed()
    m.wait_for_selector('#sendung-dokumente .ci-dok-bild.gezeichnet canvas')
    check('Handy 390 px: Bereich ohne waagerechtes Scrollen, Kacheln einspaltig', m.evaluate("""() => { const d = document.querySelector('#sendung-dokumente'), k = [...d.querySelectorAll('.ci-dok-kachel')];
        return document.documentElement.scrollWidth <= window.innerWidth && d.scrollWidth <= d.clientWidth && k.every((x) => Math.abs(x.offsetWidth - k[0].offsetWidth) <= 1 && x.offsetLeft === k[0].offsetLeft); }"""))
    shot(m, os.path.join(SH, 'containerimport-dokumente-390-dunkel.png'))
    m.context.close()
    h = seite_oeffnen(br, 'lea', errs, fremd, {'width': 390, 'height': 844})
    h.click(f'tr[data-sendung="{c3["id"]}"]'); h.wait_for_selector('#dlg-sendung[open] .ci-dok-kachel')
    h.locator('#sendung-dokumente .ci-dok-kachel >> nth=0').scroll_into_view_if_needed()
    h.wait_for_selector('#sendung-dokumente .ci-dok-bild.gezeichnet[data-endung=png] canvas')
    check('Handy 390 px hell (Leser): Miniatur des Bildes gezeichnet', h.locator('.ci-dok-bild.gezeichnet').count() >= 1)
    shot(h, os.path.join(SH, 'containerimport-dokumente-390-hell-leser.png'))
    h.context.close()
    br.close()
check('die Seite hat keine fremden Server abgerufen', fremd == [], fremd)
check('keine JavaScript-Fehler', not errs, errs)
ende()
