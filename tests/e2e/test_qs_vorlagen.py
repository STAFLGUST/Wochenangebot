"""Qualitätssicherung – Vorlagen und Nummernstruktur (QM-System Bauabschnitt 3, app/api/module/qs/vorlagen.php).

Geprüft: Nummernstruktur <Kapitel>-<Art><Nr.> für Arbeitsanweisungen, Formblätter, Listen und Excel (leer = nächste freie,
Lücken nicht gefüllt, Art in Großbuchstaben, falsche Struktur 422 mit Vorschlag, Kapitel- oder Artwechsel verlangt eine neue
Nummer, alte Nummern aus dem Datenpaket bleiben bei anderen Änderungen, Vorlagen heißen frei); Dokument aus Vorlage (Word mit
über mehrere Textstücke verteilten Platzhaltern, Kopfzeile, Bild unverändert, .dotx wird .docx; Excel mit Zellen, Kopf-/Fußzeile
und „&“; Dateiname aus Nr. und Titel; Lenkungs-Platzhalter bleiben bis zur Freigabe; Fehler: unbekannt, keine Vorlage, ohne
Freigabe, nur PDF, nicht lesbar ohne Reste, Ordner, beim Ändern, eingezogen); Vorlagen werden bei Freigabe und Nachtragen nie
ausgefüllt; Freigabe trägt Version, Datum, Kürzel, Änderungen ein (ausgefüllte Fassung neu, Rohfassung bleibt, ZIP mit der
ausgefüllten); Datei ohne Platzhalter bleibt, nicht lesbare Datei hält die Freigabe nicht auf; Nachtragen in freigegebene Version
füllt sofort; Überarbeitung übernimmt die Rohfassungen als Kopie (Platzhalter erkannt, Löschen im Entwurf lässt die freigegebene
Version unberührt), zweite Freigabe mit Version 2; Rechte; Protokoll; Oberfläche (Anlegen mit vorgewählter Vorlage und Nummer,
Datei im Entwurf mit Herkunft und Platzhaltern, Kapitelwechsel schlägt neue Nummer vor, Vorlagen-Karte, „Dateien übernehmen“,
1280/390 px hell und dunkel, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import base64
import datetime
import glob
import hashlib
import html
import io
import json
import os
import re
import urllib.error
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH

HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
UDATA = os.environ['UDATA']
HEUTE = datetime.date.today()
HEUTE_DE = HEUTE.strftime('%d.%m.%Y')
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


# ── erfundene Word- und Excel-Dateien ──
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
BILD = b'\x89PNG\r\n\x1a\n' + bytes(range(256)) * 8


def _x(t):
    return html.escape(t, quote=False)


def docx(absaetze, kopf=None, vorlage=False):
    """absaetze: Liste von Absätzen, je Liste von Textstücken (so zerlegt Word Text beim Tippen)"""
    body = ''.join('<w:p>' + ''.join(f'<w:r><w:t xml:space="preserve">{_x(t)}</w:t></w:r>' for t in a) + '</w:p>' for a in absaetze)
    typ = 'template' if vorlage else 'document'
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   f'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{typ}.main+xml"/></Types>')
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body>{body}</w:body></w:document>')
        if kopf:
            z.writestr('word/header1.xml', f'<w:hdr {W}><w:p><w:r><w:t>{_x(kopf)}</w:t></w:r></w:p></w:hdr>')
        z.writestr('word/media/logo.png', BILD)
    return b.getvalue()


def xltx(zellen, kopf, fuss):
    ss = ''.join(f'<si><t>{_x(t)}</t></si>' for t in zellen)
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml"/></Types>')
        z.writestr('xl/sharedStrings.xml', f'<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{ss}</sst>')
        z.writestr('xl/worksheets/sheet1.xml', '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/>'
                   f'<headerFooter><oddHeader>{_x(kopf)}</oddHeader><oddFooter>{_x(fuss)}</oddFooter></headerFooter></worksheet>')
    return b.getvalue()


def word_text(daten, teil='word/document.xml'):
    xml = zipfile.ZipFile(io.BytesIO(daten)).read(teil).decode()
    return '\n'.join(html.unescape(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', p, re.S))) for p in re.findall(r'<w:p>.*?</w:p>', xml, re.S))


VORLAGE_F = docx([['Formblatt ', '{{', 'N', 'r}}'], ['Titel: {{Titel}} · Kapitel {{ Kapitel }} · Art {{Art}}'],
                  ['Version {{Version}} vom {{Freigabedatum}} · erstellt {{Erstellt}} · geprüft {{Geprüft}} · freigegeben {{Freigegeben}}'],
                  ['Änderungen: {{Änderungen}} – {{Grund}} · {{Unbekannt}}']], kopf='{{Nr}} · Seite 1', vorlage=True)
VORLAGE_E = xltx(['Liste {{Nr}}', '{{Titel}}', 'Stand {{Version}}'], '&L{{Nr}}&R{{Titel}}', '&CSeite &P · {{Datum}}')


def hochladen(cli, dok, ver, name, inhalt):
    return cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest(),
                                           'upload': '', 'teil': 0, 'daten': base64.b64encode(inhalt).decode()})


def roh(cli, query):
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, r.read()


def blob(did):
    return os.path.join(UDATA, 'dateien', 'qs', did[:2], did + '.bin')


def blobs():
    return sorted(glob.glob(os.path.join(UDATA, 'dateien', 'qs', '*', '*.bin')))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('fritz', 'Fritz Freigabe', 'editor', 'Freigabe-Konto-78', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten']}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, F, V = K['lisa'], K['bernd'], K['quinn'], K['fritz'], K['vera']
check('Testfreigabe und Tester', A.call('modul_freigabe_save', {'bereich': 'qs.intern', 'freigabe': 'test', 'grund': 'Abnahme Vorlagen'})[0] == 200
      and A.call('modul_tester_save', {'bereich': 'qs.intern', 'tester': [ids[x] for x in ('admin', 'lisa', 'bernd', 'quinn', 'fritz', 'vera')], 'grund': 'Abnahme'})[0] == 200)

# Datenpaket (erfunden) mit einer Altnummer, die nicht der Struktur folgt
paket = json.load(open(PAKET_DATEI, encoding='utf-8'))
paket['dokumente'].append({'nr': '1.4-F7a', 'kapitel': '1.4', 'art': 'F', 'titel': 'Altes Formblatt', 'versionen': [{'nr': 1, 'datum': '2023-05-02'}]})
check('Datenpaket übernommen (Struktur wird beim Datenpaket nicht geprüft)', V.call('qs_import', {'paket': paket})[0] == 200)
st, r = L.call('qs_start')
pers = [{**p_, 'mitarbeiter': {'QB': ids['quinn'], 'QV': ids['vera']}.get(p_['id'], '')} for p_ in r['personen']] + [
    {'id': 'BB', 'name': 'Bernd Bearbeiter', 'funktion': 'QM', 'mitarbeiter': ids['bernd']}, {'id': 'FF', 'name': 'Fritz Freigabe', 'funktion': 'GF', 'mitarbeiter': ids['fritz']}]
check('Kürzel verknüpft (QB, BB, FF)', V.call('qs_stamm_save', {'personen': pers})[0] == 200)
st, r = L.call('qs_start')
check('Start: Platzhalter, Arten mit Nummernstruktur, Word/Excel-Arten', r['ablage']['nrStruktur'] == ['A', 'F', 'L', 'E'] and r['ablage']['platzhalter']['geprueft'] == 'Geprüft'
      and set(r['ablage']['office']) == {'docx', 'dotx', 'xlsx', 'xltx', 'xlsm'}, r.get('ablage'))
dk = {x['nr'] or x['titel']: x for x in r['dokumente']}
VF = dk['Vorlage F']['id']; ALT = dk['1.4-F7a']


def dok(did):
    return {x['id']: x for x in L.call('qs_start')[1]['dokumente']}[did]


def schritt(cli, did, s, **extra):
    return cli.call('qs_version_schritt', {'dokument': did, 'rev': dok(did)['rev'], 'schritt': s, **extra})


def neu(cli, **b):
    return cli.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '', 'titel': 'Test', **b})


# ── Nummernstruktur ──
st, r = neu(Be, titel='Probenahmeplan Rind')
check('leer: nächste freie Nummer (1.4-F08 nach F07 und der Altnummer F7a)', st == 200 and r['dokument']['nr'] == '1.4-F08', r.get('dokument', {}).get('nr', r))
st, r = neu(Be, nr='1.4-f12', titel='Zwölf')
check('Nummer mit kleiner Art: als 1.4-F12 gespeichert', st == 200 and r['dokument']['nr'] == '1.4-F12', r)
st, r = neu(Be, titel='Dreizehn')
check('Lücken werden nicht gefüllt: nächste 1.4-F13', st == 200 and r['dokument']['nr'] == '1.4-F13', r)
for name, nr, vorschlag in (('eine Ziffer', '1.4-F7', '1.4-F14'), ('falsches Kapitel', '2.1-F01', '1.4-F14'), ('freier Text', 'Formular 3', '1.4-F14'),
                            ('andere Art', '1.4-A01', '1.4-F14'), ('vier Ziffern', '1.4-F0001', '1.4-F14')):
    st, r = neu(Be, nr=nr)
    check(f'Struktur: {name} → 422 mit Vorschlag', st == 422 and vorschlag in r.get('error', '') and 'Leer lassen' in r.get('error', ''), (st, r))
check('doppelte Nummer → 422', neu(Be, nr='1.4-F12')[0] == 422)
st, r = neu(Be, art='A', titel='Anweisung')
st2, r2 = neu(Be, kapitel='2.1', art='L', titel='Liste')
st3, r3 = neu(Be, kapitel='2.1', art='E', titel='Excel')
check('Arten A, L, E: 1.4-A02, 2.1-L01, 2.1-E02', (r['dokument']['nr'], r2['dokument']['nr'], r3['dokument']['nr']) == ('1.4-A02', '2.1-L01', '2.1-E02'), (r, r2, r3))
check('Vorlage ohne Bezeichnung → 422, mit freiem Namen erlaubt', neu(Be, kapitel='1.1', art='V')[0] == 422
      and neu(Be, kapitel='1.1', art='V', nr='Vorlage E', titel='Vorlage Excel-Liste')[1]['dokument']['nr'] == 'Vorlage E')
check('Ordner ohne Nummer', neu(Be, kapitel='2.1', art='O', titel='Zertifikate')[1]['dokument']['nr'] == '')
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F7a', 'titel': 'Altes Formblatt (umbenannt)', 'id': ALT['id'], 'rev': ALT['rev']})
check('Altnummer aus der Excel bleibt bei anderen Änderungen', st == 200 and r['dokument']['nr'] == '1.4-F7a', r)
alt = r['dokument']
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'F', 'nr': '1.4-F7a', 'titel': alt['titel'], 'id': alt['id'], 'rev': alt['rev']})
check('Kapitelwechsel mit alter Nummer → 422 mit Vorschlag 2.1-F01', st == 422 and '2.1-F01' in r.get('error', ''), r)
st, r = Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'F', 'nr': '', 'titel': alt['titel'], 'id': alt['id'], 'rev': alt['rev']})
check('Kapitelwechsel mit leerer Nummer: 2.1-F01, Verlauf', st == 200 and r['dokument']['nr'] == '2.1-F01' and 'Dokumenten-Nr. geändert' in json.dumps(r['dokument']['verlauf'], ensure_ascii=False), r)
check('Nummer wird nicht wiederverwendet (1.4 F: weiter 1.4-F14)', neu(Be, titel='Vierzehn')[1]['dokument']['nr'] == '1.4-F14')

# ── Vorlagen anlegen ──
st, r = hochladen(Be, VF, dok(VF)['versionen'][0]['id'], 'Vorlage Formblatt.dotx', VORLAGE_F)
check('Vorlage (freigegeben): Datei nachtragen nur mit Freigaberecht (403)', st == 403, r)
st, r = hochladen(Q, VF, dok(VF)['versionen'][0]['id'], 'Vorlage Formblatt.dotx', VORLAGE_F)
fv = [f for f in r['dokument']['versionen'][0]['dateien'] if f['id'] == r.get('datei')] if st == 200 else [{}]
check('Vorlagendatei nachgetragen: nicht ausgefüllt, Platzhalter erkannt', st == 200 and 'roh' not in fv[0] and 'ausgefuellt' not in fv[0]
      and set(fv[0]['platzhalter']) >= {'nr', 'titel', 'kapitel', 'art', 'version', 'datum', 'erstellt', 'geprueft', 'freigegeben', 'aenderungen', 'grund'}
      and open(blob(fv[0]['id']), 'rb').read() == VORLAGE_F, fv)
VE = {x['nr']: x for x in L.call('qs_start')[1]['dokumente']}['Vorlage E']
hochladen(Be, VE['id'], VE['versionen'][0]['id'], 'Liste.xltx', VORLAGE_E)
st, r = neu(Be, kapitel='2.1', art='E', titel='Lieferanten', vorlage=VE['id'])
check('Vorlage ohne freigegebene Version → 422', st == 422 and 'freigegebene' in r.get('error', ''), r)
check('Vorlage E eingereicht und von Fritz freigegeben', schritt(Be, VE['id'], 'einreichen')[0] == 200 and schritt(F, VE['id'], 'pruefen_freigeben')[0] == 200)
ve = dok(VE['id'])['versionen'][0]
check('Freigabe einer Vorlage füllt ihre Dateien nicht aus', ve['status'] == 'freigegeben' and 'roh' not in ve['dateien'][0] and open(blob(ve['dateien'][0]['id']), 'rb').read() == VORLAGE_E, ve['dateien'])

# Fehlerfälle beim Erzeugen
st, r = neu(Be, kapitel='1.1', art='V', nr='Vorlage P', titel='Nur PDF')
VP = r['dokument']
hochladen(Be, VP['id'], VP['versionen'][0]['id'], 'Vorlage.pdf', b'%PDF-1.4 Vorlage')
schritt(Be, VP['id'], 'einreichen'); schritt(F, VP['id'], 'pruefen_freigeben')
st, r = neu(Be, kapitel='1.1', art='V', nr='Vorlage A', titel='Kaputte Vorlage')
VA = r['dokument']
hochladen(Be, VA['id'], VA['versionen'][0]['id'], 'Vorlage.docx', b'PK\x03\x04' + b'kein echtes ZIP' * 20)
schritt(Be, VA['id'], 'einreichen'); schritt(F, VA['id'], 'pruefen_freigeben')
vorher = blobs(); anzahl = len(L.call('qs_start')[1]['dokumente'])
for name, b, text in (('unbekannte Vorlage', {'vorlage': 'dnix'}, 'gibt es nicht'), ('kein Vorlagen-Dokument', {'vorlage': ALT['id']}, 'keine Vorlage'),
                      ('Vorlage nur mit PDF', {'vorlage': VP['id']}, 'Word- oder Excel'), ('Vorlage nicht lesbar', {'vorlage': VA['id']}, 'keine lesbare'),
                      ('Ordner aus Vorlage', {'art': 'O', 'vorlage': VF}, 'Formblätter'), ('Vorlage aus Vorlage', {'art': 'V', 'nr': 'Vorlage X', 'vorlage': VF}, 'Formblätter')):
    st, r = neu(Be, **b)
    check(f'Erzeugen: {name} → 422', st == 422 and text in r.get('error', ''), (st, r))
check('nach Fehlern: kein Dokument angelegt, keine Dateien übrig', len(L.call('qs_start')[1]['dokumente']) == anzahl and blobs() == vorher, (len(blobs()), len(vorher)))
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F08', 'titel': 'X', 'id': alt['id'], 'rev': dok(alt['id'])['rev'], 'vorlage': VF})
check('Vorlage beim Ändern → 422', st == 422 and 'Anlegen' in r.get('error', ''), r)
check('ohne Recht: Lisa legt nicht an (403)', neu(L, vorlage=VF)[0] == 403)

# ── Dokument aus Vorlage (Word) ──
st, r = neu(Be, titel='Temperatur & Hygiene', zustaendig='QB', vertreter='BB', vorlage=VF, aenderungen='Neu aus Vorlage')
d1 = r.get('dokument', {}); v1 = (d1.get('versionen') or [{}])[0]; f1 = (v1.get('dateien') or [{}])[0]
check('aus Vorlage angelegt: Nummer 1.4-F15, eine Datei im Entwurf, Name aus Nr. und Titel, .docx', st == 200 and d1['nr'] == '1.4-F15' and len(v1['dateien']) == 1
      and f1['name'] == '1.4-F15 Temperatur & Hygiene.docx' and f1['art'] == 'docx' and f1['mime'].endswith('wordprocessingml.document') and f1['vorlage']['nr'] == 'Vorlage F', r)
check('offene Platzhalter: nur die Lenkungsangaben', set(f1.get('platzhalter', [])) == {'version', 'datum', 'erstellt', 'geprueft', 'freigegeben', 'aenderungen', 'grund'}, f1.get('platzhalter'))
check('Verlauf: aus Vorlage erzeugt', 'aus Vorlage „Vorlage F“ erzeugt' in json.dumps(v1.get('verlauf'), ensure_ascii=False) and 'aus Vorlage' in json.dumps(d1.get('verlauf'), ensure_ascii=False))
st, inhalt = roh(L, 'qs_datei&id=' + f1['id'])
z = zipfile.ZipFile(io.BytesIO(inhalt)) if st == 200 else None
t = word_text(inhalt) if z else ''
check('Datei: gültiges ZIP, Nr. über drei Textstücke ersetzt, Titel/Kapitel/Art, Kopfzeile', z and z.testzip() is None and t.startswith('Formblatt 1.4-F15\n')
      and 'Titel: Temperatur & Hygiene · Kapitel 1.4 Qualitätssicherung · Art Formblatt' in t and '1.4-F15 · Seite 1' in word_text(inhalt, 'word/header1.xml'), t)
check('Datei: Lenkungs-Platzhalter bleiben bis zur Freigabe, unbekannte bleiben stehen', '{{Version}}' in t and '{{Geprüft}}' in t and '{{Unbekannt}}' in t, t)
check('Datei: aus .dotx wird .docx (Inhaltstyp), Bild unverändert', z and 'wordprocessingml.document.main+xml' in z.read('[Content_Types].xml').decode()
      and 'template' not in z.read('[Content_Types].xml').decode() and z.read('word/media/logo.png') == BILD)
check('Vorlage selbst unverändert', open(blob(fv[0]['id']), 'rb').read() == VORLAGE_F)
D1 = d1['id']

# ── Excel aus Vorlage ──
st, r = neu(Be, kapitel='2.1', art='E', titel='Lieferanten & Preise', vorlage=VE['id'])
fe = r['dokument']['versionen'][0]['dateien'][0] if st == 200 else {}
ze = zipfile.ZipFile(io.BytesIO(roh(L, 'qs_datei&id=' + fe.get('id', 'x'))[1])) if st == 200 else None
ss = html.unescape(ze.read('xl/sharedStrings.xml').decode()) if ze else ''
blatt = ze.read('xl/worksheets/sheet1.xml').decode() if ze else ''
check('Excel aus Vorlage: 2.1-E03, .xlsx, Zellen ausgefüllt, Version offen', st == 200 and r['dokument']['nr'] == '2.1-E03' and fe['name'] == '2.1-E03 Lieferanten & Preise.xlsx'
      and 'Liste 2.1-E03' in ss and 'Lieferanten & Preise' in ss and 'Stand {{Version}}' in ss and 'spreadsheetml.sheet.main+xml' in ze.read('[Content_Types].xml').decode(), (r, ss))
check('Excel: Kopfzeile mit Nr. und Titel („&“ als „&&“), Fußzeile mit Datum offen', '&amp;L2.1-E03&amp;RLieferanten &amp;&amp; Preise' in blatt and '{{Datum}}' in blatt, blatt)

# ── Freigabe trägt Lenkungsangaben ein ──
st, r = hochladen(Be, D1, v1['id'], 'Anhang ohne Platzhalter.docx', docx([['Nur Text']]))
ohne = r.get('datei')
st, r = hochladen(Be, D1, v1['id'], 'Defekt.docx', b'PK\x03\x04' + b'defekt' * 30)
defekt = r.get('datei')
check('Einreichen (Bernd) und Freigabe (Fritz)', schritt(Be, D1, 'einreichen')[0] == 200 and schritt(F, D1, 'pruefen_freigeben')[0] == 200)
v = dok(D1)['versionen'][0]
fa = {f['name']: f for f in v['dateien']}
g1 = fa['1.4-F15 Temperatur & Hygiene.docx']
check('ausgefüllte Fassung: neue Kennung, Rohfassung bleibt, Felder gezählt, keine offenen Platzhalter', g1['id'] != f1['id'] and g1['roh'] == f1['id'] and g1['ausgefuellt']['felder'] == 7
      and 'platzhalter' not in g1 and os.path.isfile(blob(f1['id'])) and os.path.isfile(blob(g1['id'])), g1)
st, inhalt = roh(L, 'qs_datei&id=' + g1['id'])
t = word_text(inhalt)
check('Lenkungsangaben: Version 1, Freigabedatum, Kürzel erstellt BB, geprüft und freigegeben FF, Änderungen', st == 200
      and f'Version 1 vom {HEUTE_DE} · erstellt BB · geprüft FF · freigegeben FF' in t and 'Änderungen: Neu aus Vorlage – ' in t and '{{Unbekannt}}' in t, t)
check('Größe und Prüfsumme der ausgefüllten Fassung', g1['groesse'] == len(inhalt) and g1['sha256'] == hashlib.sha256(inhalt).hexdigest())
check('Datei ohne Platzhalter bleibt unverändert', fa['Anhang ohne Platzhalter.docx']['id'] == ohne and 'roh' not in fa['Anhang ohne Platzhalter.docx'])
check('nicht lesbare Datei hält die Freigabe nicht auf (Verlauf)', fa['Defekt.docx']['id'] == defekt and v['status'] == 'freigegeben'
      and 'Lenkungsangaben in „Defekt.docx“ nicht eingetragen' in json.dumps(v['verlauf'], ensure_ascii=False), v['verlauf'])
ez = zipfile.ZipFile(io.BytesIO(roh(L, 'qs_ablage_export&kapitel=1.4')[1]))
pfad = 'QM-System/1.4 Qualitätssicherung/1.4-F15 Temperatur & Hygiene/1.4-F15 Temperatur & Hygiene.docx'
check('ZIP-Export enthält die ausgefüllte Fassung', pfad in ez.namelist() and ez.read(pfad) == inhalt, ez.namelist()[:6])

# Nachtragen in die freigegebene Version füllt sofort aus
st, r = hochladen(Q, D1, v['id'], 'Aushang.docx', docx([['Aushang {{Nr}} – Version {{Version}}']]))
na = [f for f in r['dokument']['versionen'][0]['dateien'] if f['id'] == r.get('datei')] if st == 200 else [{}]
check('Nachtragen: sofort ausgefüllt, Antwort nennt die ausgefüllte Fassung', st == 200 and na[0].get('roh') and na[0].get('nachgetragen')
      and 'Aushang 1.4-F15 – Version 1' in word_text(roh(L, 'qs_datei&id=' + r['datei'])[1]), (st, na))

# ── Überarbeitung übernimmt die Rohfassungen ──
st, r = Be.call('qs_version_save', {'dokument': D1, 'aenderungen': 'Grenzwerte angepasst', 'grund': 'Kundenaudit', 'dateien': True})
v2 = r['dokument']['versionen'][-1] if st == 200 else {}
kop = {f['name']: f for f in v2.get('dateien', [])}
k1 = kop.get('1.4-F15 Temperatur & Hygiene.docx', {})
check('Überarbeitung mit Dateien: Kopien aller aktiven Dateien, aus Version 1', st == 200 and len(kop) == 4 and all(f.get('uebernommen') == 1 for f in kop.values())
      and 'Dateien aus Version 1 übernommen (4)' in json.dumps(v2['verlauf'], ensure_ascii=False), v2)
check('Kopie der Rohfassung: neue Kennung, gleicher Inhalt wie roh, Platzhalter erkannt', k1.get('id') not in (f1['id'], g1['id']) and k1.get('sha256') == hashlib.sha256(open(blob(f1['id']), 'rb').read()).hexdigest()
      and 'version' in k1.get('platzhalter', []), k1)
check('Bernd ist Bearbeiter des neuen Entwurfs', v2.get('bearbeiter') == [ids['bernd']])
st, r = Be.call('qs_datei_entfernen', {'datei': kop['Defekt.docx']['id'], 'grund': ''})
check('Kopie im Entwurf löschen: freigegebene Version unberührt', st == 200 and not os.path.isfile(blob(kop['Defekt.docx']['id'])) and os.path.isfile(blob(defekt)))
st, r = Q.call('qs_version_save', {'dokument': VF, 'aenderungen': 'x', 'grund': 'y'})
check('Überarbeitung ohne „dateien“: keine Dateien', st == 200 and not r['dokument']['versionen'][-1].get('dateien'))
check('Version 2 eingereicht und von Quinn freigegeben', schritt(Be, D1, 'einreichen')[0] == 200 and schritt(Q, D1, 'pruefen_freigeben')[0] == 200)
v2 = dok(D1)['versionen'][-1]
g2 = {f['name']: f for f in v2['dateien']}['1.4-F15 Temperatur & Hygiene.docx']
t = word_text(roh(L, 'qs_datei&id=' + g2['id'])[1])
check('zweite Freigabe: Version 2, freigegeben QB, Änderungen der Überarbeitung', f'Version 2 vom {HEUTE_DE} · erstellt BB · geprüft QB · freigegeben QB' in t
      and 'Änderungen: Grenzwerte angepasst – Kundenaudit' in t, t)
check('Version 1 behält ihre ausgefüllte Fassung', 'Version 1 vom' in word_text(roh(L, 'qs_datei&id=' + g1['id'])[1]))

# ── Protokoll ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: aus Vorlage angelegt', 'QM-System: Dokument 1.4-F15 Temperatur & Hygiene angelegt (aus Vorlage)' in log, log[-1500:])

# ── Oberfläche ──
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

    def oeffne_dok(pg, did):
        pg.click('#qm-tabs [data-tab="dokumente"]'); pg.click(f'#qm-d-liste tr[data-dok="{did}"]'); pg.wait_for_selector('#qm-dk:not([hidden]) h2')

    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    pg.click('#qm-d-neu'); pg.wait_for_selector('#dlg-dokform[open]')
    pg.select_option('#df-kapitel', '1.4'); pg.select_option('#df-art', 'F')
    check('Anlegen: Formblatt – Vorlage F vorgewählt, nächste Nummer vorgeschlagen', pg.is_visible('#df-vorlage') and pg.input_value('#df-vorlage') == VF
          and pg.input_value('#df-nr') == '1.4-F16' and 'leer gelassen' in text(pg, '#df-hilfe') and 'Datei der Vorlage' in text(pg, '#df-hilfe'), (pg.input_value('#df-nr'), text(pg, '#df-hilfe')))
    opts = pg.eval_on_selector_all('#df-vorlage option', 'o => o.map(x => x.textContent)')
    check('Auswahl: nur nutzbare Vorlagen (mit Word/Excel und Freigabe)', any('Vorlage F' in o for o in opts) and any('Vorlage E' in o for o in opts) and not any('Vorlage P' in o for o in opts), opts)
    pg.select_option('#df-art', 'E')
    check('Art Excel: Vorlage E vorgewählt', pg.input_value('#df-vorlage') == VE['id'])
    pg.select_option('#df-art', 'O')
    check('Ordner: keine Vorlage, keine Nummer', pg.is_hidden('#df-vorlage-z') and pg.input_value('#df-nr') == '')
    pg.select_option('#df-art', 'F')
    pg.fill('#df-titel-in', 'Reinigungsplan Kühlhaus')
    pg.screenshot(path=os.path.join(SH, 'qs_vorlage_anlegen_1280.png'))
    pg.click('#df-form [type="submit"]'); toast(pg, 'aus Vorlage angelegt')
    pg.wait_for_selector('#qm-dk .qm-datei')
    check('angelegt: Seitenleiste mit Datei aus der Vorlage und offenen Platzhaltern', '1.4-F16 Reinigungsplan Kühlhaus.docx' in text(pg, '#qm-dk .qm-dateien')
          and 'aus Vorlage F' in text(pg, '#qm-dk .qm-dateien') and 'Version' in text(pg, '#qm-dk .qm-platzhalter') and pg.is_visible('#qm-dk .qm-lenkung'), text(pg, '#qm-dk'))
    pg.screenshot(path=os.path.join(SH, 'qs_vorlage_entwurf_1280.png'))
    with pg.expect_download() as dl:
        pg.click('#qm-dk .qm-datei-name')
    check('Herunterladen der erzeugten Datei', dl.value.suggested_filename == '1.4-F16 Reinigungsplan Kühlhaus.docx'
          and word_text(open(dl.value.path(), 'rb').read()).startswith('Formblatt 1.4-F16'))
    pg.click('#qm-dk [data-schritt="angaben"]'); pg.wait_for_selector('#dlg-dokform[open]')
    check('Angaben ändern: keine Vorlage-Auswahl, Nummer bleibt', pg.is_hidden('#df-vorlage-z') and pg.input_value('#df-nr') == '1.4-F16')
    pg.select_option('#df-kapitel', '2.1')
    check('Kapitelwechsel: neue Nummer nach der Struktur vorgeschlagen', pg.input_value('#df-nr') == '2.1-F02', pg.input_value('#df-nr'))
    pg.select_option('#df-kapitel', '1.4')
    check('zurück: alte Nummer', pg.input_value('#df-nr') == '1.4-F16')
    pg.click('#dlg-dokform .qm-knopfreihe [data-schliessen]')
    oeffne_dok(pg, VF)
    check('Vorlage: Karte mit Platzhaltern, nutzbar', '{{Version}}' in text(pg, '#qm-dk .qm-vorlagenkarte') and 'Noch nicht nutzbar' not in text(pg, '#qm-dk .qm-vorlagenkarte'))
    oeffne_dok(pg, VP['id'])
    check('Vorlage nur mit PDF: Hinweis „noch nicht nutzbar“', 'Noch nicht nutzbar' in text(pg, '#qm-dk .qm-vorlagenkarte'))
    oeffne_dok(pg, D1)
    check('freigegebenes Dokument: Dateien mit „Lenkungsangaben eingetragen“, Überarbeiten mit „Dateien übernehmen“', 'Lenkungsangaben eingetragen' in text(pg, '#qm-dk section.qm-ablage')
          and pg.is_checked('#dk-dateien') and 'Version 2' in text(pg, '#qm-dk .qm-karte .qm-check'), text(pg, '#qm-dk'))
    pg.fill('#dk-aend', 'Tabelle erweitert'); pg.fill('#dk-grund', 'Hinweis aus der Praxis')
    pg.click('#qm-dk [data-schritt="neu"]'); toast(pg, 'Überarbeitung begonnen')
    pg.wait_for_selector('#qm-dk .qm-karte .qm-dateien')
    check('Überarbeitung: Dateien aus Version 2 im Entwurf', pg.locator('#qm-dk .qm-karte .qm-datei').count() == 3 and 'aus Version 2' in text(pg, '#qm-dk .qm-karte .qm-dateien'))
    pg.screenshot(path=os.path.join(SH, 'qs_vorlage_ueberarbeitung_1280.png'))
    ctx.close()

    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11', breite, thema, 844 if breite < 500 else 900)
        oeffne_dok(pg, D1)
        check(f'{breite}px {thema}: Seitenleiste mit Vorlagen-Dateien passt in die Breite', pg.evaluate("(() => { const d = document.querySelector('#qm-dk'); const r = d.getBoundingClientRect();"
              " return document.documentElement.scrollWidth <= window.innerWidth + 1 && d.scrollWidth <= d.clientWidth + 1 && r.right <= window.innerWidth + 1; })()"))
        pg.screenshot(path=os.path.join(SH, f'qs_vorlage_{breite}_{thema}.png'))
        if breite == 390:
            pg.click('#qm-dk [data-dk="schliessen"]'); pg.wait_for_selector('#qm-dk', state='hidden')
            pg.click('#qm-d-neu'); pg.wait_for_selector('#dlg-dokform[open]'); pg.select_option('#df-kapitel', '1.4')
            check(f'{breite}px {thema}: Anlegen-Dialog mit Vorlage ohne waagerechtes Scrollen', pg.is_visible('#df-vorlage') and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
            pg.screenshot(path=os.path.join(SH, f'qs_vorlage_anlegen_{breite}_{thema}.png'))
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
