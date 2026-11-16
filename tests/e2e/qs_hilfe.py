"""Gemeinsame Hilfen der Tests zur Dokumentenablage des QM-Systems (test_qs_eingang.py, test_qs_import.py): Prüfung, Testdateien,
Speicher, Hochladen in Teilen, direkter Abruf, Nutzer anlegen, Browser-Anmeldung. Nur erfundene Testdaten."""
import base64
import hashlib
import io
import json
import os
import urllib.error
import urllib.request
import zipfile

from kunden_hilfe import Client, B, API
from umgebung import ablageordner, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
ABLAGE = os.path.join(ablageordner(), 'dateien')
TEIL = 3 * 1024 * 1024
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:600]) if i else ''))


def ende():
    check('keine JavaScript-Fehler', not fehler, fehler)
    print(f'{sum(res)}/{len(res)} passed')


def pdf(text):
    return b'%PDF-1.4\n% ' + text.encode() + b'\n%%EOF'


def docx_w(text):
    """Word-Datei mit Absatz und Textstück (wie Word), damit Platzhalter erkannt werden"""
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                   + text + '</w:t></w:r></w:p></w:body></w:document>')
    return b.getvalue()


def blob_pfad(did):
    return os.path.join(ABLAGE, 'qs', did[:2], did + '.bin')


def blobs():
    """Kennungen aller Dateien der QS-Ablage auf der Platte"""
    aus = set()
    for wurzel, _, namen in os.walk(os.path.join(ABLAGE, 'qs')):
        aus |= {n[:-4] for n in namen if n.endswith('.bin')}
    return aus


def speicher(name):
    return json.loads((storage_raw(name) or '{}').split('?>\n', 1)[-1] or '{}')


def hochladen(cli, dok, ver, name, inhalt, extra=None):
    upload, pos, nr = '', 0, 0
    while True:
        stueck = inhalt[pos:pos + TEIL]
        st, r = cli.call('qs_datei_hochladen', {'dokument': dok, 'version': ver, 'name': name, 'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest(),
                                                'upload': upload, 'teil': nr, 'daten': base64.b64encode(stueck).decode(), **(extra or {})})
        if st != 200 or r.get('fertig'):
            return st, r
        upload = r['upload']; pos += len(stueck); nr += 1


def roh(cli, query):
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, r.read()


def nutzer(nutzer_liste, ip_ab=10):
    """Administrator anmelden, Nutzer (Name, Anzeigename, Rolle, Passwort, Rechte) anlegen und anmelden: (Admin, {Name: Client}, {Name: Kennung})"""
    a = Client('198.51.100.2')
    check('Administrator angemeldet', a.call('login', {'username': 'admin', 'password': PW})[0] == 200)
    for u, n, r, p, extra in nutzer_liste:
        st, r_ = a.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
        assert st == 200, r_
    ids = {u['username']: u['id'] for u in a.call('users')[1]['users']}
    k = {}
    for i, (u, _, _, p, _) in enumerate(nutzer_liste):
        k[u] = Client(f'198.51.100.{ip_ab + i}'); k[u].call('login', {'username': u, 'password': p})
    return a, k, ids


def fuellen(cli, n, ziel, praefix):
    """n aktive Einträge ohne Datei in qs-ablage – nur zum Erreichen einer Grenze; die Zahlen zählt danach der Server neu"""
    ab = speicher('qs-ablage')
    ab.setdefault('liste', [])
    ab['liste'] += [{'id': f'{praefix}{i:012d}', 'name': f'Füllung {i}.pdf', 'art': 'pdf', 'mime': 'application/pdf', 'groesse': 1, 'sha256': f'{i:064x}',
                     'hochgeladen': {'t': '2026-11-01T08:00:00+01:00', 'von': 'Test', 'vonId': 'test'}, 'ziel': ziel, 'pfad': 'Füllung'} for i in range(n)]
    storage_write('qs-ablage', ab)
    neu_zaehlen(cli)


def leeren(cli, praefix):
    """Füllung wieder entfernen; den letzten Eintrag löscht der Server im Eingang – dabei zählt er neu (auch wenn die Zahlen noch „voll“ sagen)"""
    ab = speicher('qs-ablage')
    weg = [f for f in ab['liste'] if f['id'].startswith(praefix)]
    ab['liste'] = [f for f in ab['liste'] if not f['id'].startswith(praefix)] + [{**weg[-1], 'ziel': 'eingang'}]
    storage_write('qs-ablage', ab)
    assert cli.call('qs_eingang_loeschen', {'dateien': [weg[-1]['id']]})[0] == 200


_zaehler = [0]


def neu_zaehlen(cli):
    """qs-ablage-zahlen neu zählen lassen wie im Betrieb: eine Datei in den Eingang legen und wieder löschen (jedes Schreiben zählt neu)"""
    _zaehler[0] += 1
    st, r = hochladen(cli, 'eingang', '', 'Zählen.pdf', pdf(f'zählen {_zaehler[0]}'))
    assert st == 200, r
    assert cli.call('qs_eingang_loeschen', {'dateien': [r['datei']]})[0] == 200


def anmelden(br, user, pw, ip, breite=1280, thema='light', hoehe=900):
    """Browser anmelden und das QM-System („Dokumente“) öffnen; Fehler der Seite landen in fehler"""
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


def text(pg, sel):
    return pg.inner_text(sel).replace('\xa0', ' ')


def ohne_scrollen(pg, dlg):
    return pg.evaluate("s => { const d = document.querySelector(s); return d.scrollWidth <= d.clientWidth + 1 && document.documentElement.scrollWidth <= window.innerWidth + 1; }", dlg)
