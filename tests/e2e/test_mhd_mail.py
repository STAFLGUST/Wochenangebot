"""Bestand → „MHD an Verkauf“: die MHD-Liste (Suche „MHD“: kürzestes MHD bis heute + 14 Tage) per E-Mail an die Empfänger der
Benachrichtigung „MHD-Liste an den Verkauf“ – Bild der Liste eingebettet (cid), Excel-Datei im Anhang. Rechte, Prüfungen
(Empfänger, Liste geändert, Bild), Inhalt der Excel-Datei aus dem gespeicherten Bestand, Versandprotokoll, Oberfläche
1440/390 px. Datumsangaben relativ zu heute; nur Test-Mailserver, keine echten E-Mails."""
import base64
import datetime as dt
import io
import os
import re
import struct
import sys
import zipfile
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, storage_raw, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def png(w=300, h=120):
    """Kleines gültiges PNG (weiß) ohne Zusatzbibliotheken."""
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    raw = b''.join(b'\x00' + b'\xff' * (w * 3) for _ in range(h))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def teil(msg, typ):
    return [p for p in msg.walk() if p.get_content_type() == typ]


heute = dt.date.today()
tag = lambda n: (heute + dt.timedelta(days=n)).isoformat()   # noqa: E731
ARTIKEL = [
    {'code': '700001', 'name': 'Test Abgelaufen', 'kg': 40.0, 'mhd': tag(-2), 'mhdKg': 15.5, 'lots': []},
    {'code': '700002', 'name': 'Test Bald', 'kg': 120.25, 'mhd': tag(3), 'mhdKg': 60.0, 'lots': []},
    {'code': '700003', 'name': 'Test Zwei Wochen <b>fett</b>', 'kg': 80.0, 'mhd': tag(10), 'mhdKg': 80.0, 'lots': []},
    {'code': '700004', 'name': 'Test Später', 'kg': 300.0, 'mhd': tag(30), 'mhdKg': 300.0, 'lots': []},
    {'code': '700005', 'name': 'Test Ohne MHD', 'kg': 50.0, 'lots': []},
]
ZUGANG = [{'code': '700002', 'name': 'Test Bald', 'kg': 25.5, 'arrival': tag(2), 'lot': 'Z-1'}]
IN_LISTE = ['700001', '700002', '700003']

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
check('Bestand mit MHD relativ zu heute übernommen', A.call('stock_import', {'date': heute.isoformat(), 'source': 'Test-MHD.xls', 'articles': ARTIKEL, 'incoming': ZUGANG})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'id': '', 'name': 'Lea Leser', 'username': 'lea', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
V = Client('198.51.100.4'); V.call('login', {'username': 'lea', 'password': 'Leser-Zugang-77'})
BILD = base64.b64encode(png()).decode()
GUT = {'codes': IN_LISTE, 'bild': 'data:image/png;base64,' + BILD}

# ---------- Rechte und Prüfungen ----------
check('ohne Anmeldung 401', Client('198.51.100.9').call('stock_mhd_senden', GUT)[0] == 401)
check('Leser ohne Recht „MHD-Liste senden“ → 403', V.call('stock_mhd_senden', GUT)[0] == 403)
katalog = A.call('rechte')[1]['catalog']
check('Recht im Katalog (Bestand, Standard: Bearbeiter, setzt „Bestand ansehen“ voraus)', any(p['key'] == 'bestand.mhd_senden' and p['default'] == ['editor'] and p['requires'] == ['bestand.sehen'] for p in katalog))
code, r = E.call('stock_mhd_senden', GUT)
check('ohne Empfänger → 409 mit Hinweis auf die Verwaltung', code == 409 and 'Benachrichtigungen' in r.get('error', ''), r)
st = A.call('mail_status')[1]
ev = next((e for e in st['notify']['events'] if e['key'] == 'mhd'), None)
check('Benachrichtigung „MHD-Liste an den Verkauf“ in der Verwaltung (auf Knopfdruck)', ev and ev['manuell'] is True and ev['label'] == 'MHD-Liste an den Verkauf', ev)
check('Empfänger speichern', A.call('benachrichtigung_save', {'events': {'mhd': {'to': 'verkauf@example.org, leitung@example.org'}}})[0] == 200)
check('Bearbeiter darf die Empfänger nicht ändern', E.call('benachrichtigung_save', {'events': {'mhd': {'to': 'x@example.org'}}})[0] == 403)
code, r = E.call('stock_mhd_senden', {**GUT, 'codes': IN_LISTE[:2]})
check('Liste weicht vom Bestand ab → 409 (neu laden)', code == 409 and 'neu laden' in r.get('error', ''), r)
check('Artikel außerhalb der 14 Tage zählt als Abweichung', E.call('stock_mhd_senden', {**GUT, 'codes': IN_LISTE + ['700004']})[0] == 409)
check('ohne Bild → 422', E.call('stock_mhd_senden', {'codes': IN_LISTE})[0] == 422)
check('kein PNG → 422', E.call('stock_mhd_senden', {'codes': IN_LISTE, 'bild': base64.b64encode(b'GIF89a' + b'x' * 200).decode()})[0] == 422)
check('PNG zu klein → 422', E.call('stock_mhd_senden', {'codes': IN_LISTE, 'bild': base64.b64encode(png(20, 10)).decode()})[0] == 422)
check('kein Base64 → 422', E.call('stock_mhd_senden', {'codes': IN_LISTE, 'bild': '%%%'})[0] == 422)

# ---------- Versand ----------
n0 = len(smtp.messages)
code, r = E.call('stock_mhd_senden', {**GUT, 'codes': list(reversed(IN_LISTE))})
check('gesendet (Reihenfolge der Nummern egal), Ergebnis je Empfänger', code == 200 and r['artikel'] == 3 and [x['to'] for x in r['results']] == ['verkauf@example.org', 'leitung@example.org']
      and all(x['ok'] for x in r['results']), r)
until(lambda: len(smtp.messages) >= n0 + 2)
neu = smtp.messages[n0:]
check('je Empfänger eine E-Mail', sorted(m['to'][0] for m in neu) == ['leitung@example.org', 'verkauf@example.org'])
m = neu[0]
msg = m['msg']
check('Betreff: MHD-Liste mit Datum und Anzahl', re.match(r'MHD-Liste vom \d\d\.\d\d\.\d{4}: 3 Artikel mit MHD bis', m['subject']), m['subject'])
bilder = teil(msg, 'image/png')
check('Bild eingebettet (multipart/related, Content-ID, inline) und im HTML verwendet', len(bilder) == 1 and bilder[0]['Content-ID'] == '<mhd-liste>'
      and bilder[0].get_content_disposition() == 'inline' and 'cid:mhd-liste' in m['html'] and teil(msg, 'multipart/related'))
check('Bild unverändert übernommen', bilder and bilder[0].get_content() == png())
xl = [p for p in msg.walk() if p.get_content_type() == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
check('Excel-Datei im Anhang', len(xl) == 1 and xl[0].get_content_disposition() == 'attachment' and re.match(r'MHD-Liste_\d{4}-\d\d-\d\d\.xlsx', xl[0].get_filename() or ''), [p.get_content_type() for p in msg.walk()])
z = zipfile.ZipFile(io.BytesIO(xl[0].get_content()))
check('Excel: gültiges Paket (Arbeitsmappe, Blatt, Formate)', {'[Content_Types].xml', 'xl/workbook.xml', 'xl/worksheets/sheet1.xml', 'xl/styles.xml'} <= set(z.namelist()) and z.testzip() is None)
blatt = z.read('xl/worksheets/sheet1.xml').decode()
codes = re.findall(r'<t xml:space="preserve">(70000\d)</t>', blatt)
check('Excel: genau die MHD-Liste, früheste zuerst (ohne MHD in 30 Tagen, ohne Artikel ohne MHD)', codes == IN_LISTE, codes)
check('Excel: Name sicher (kein HTML), Mengen als Zahlen, Summen als Formel', '&lt;b&gt;fett&lt;/b&gt;' in blatt and '<v>120.25</v>' in blatt and '<v>25.5</v>' in blatt and '<f>SUM(' in blatt)
check('Excel: Kopf mit Preisen der Wochen (Absender darf Preisverlauf sehen) und ETA', 'Aktueller Preis KW' in blatt and 'Nächste ETA' in blatt and 'Erfasster Bestand' in blatt)
check('Text: Liste und Hinweis auf den Anhang', '700002' in m['text'] and 'Excel-Datei im Anhang' in m['text'] and 'davon 1 bereits abgelaufen' in m['text'])
check('über das interne Postfach (ohne eigenes: Kunden-Postfach, angebot@)', m['from'] == 'angebot@example.org')
check('Versandprotokoll: Typ „mhd“ je Empfänger', storage_raw('mailversand').count('"typ":"mhd"') + storage_raw('mailversand').count('"typ": "mhd"') == 2)
code, r, raw = A.call('log', raw=True)
check('Protokoll: MHD-Liste gesendet', 'MHD-Liste (3 Artikel) an den Verkauf gesendet an verkauf@example.org' in raw)

# ---------- Oberfläche ----------
with sync_playwright() as p:
    br = p.chromium.launch()
    errs = []

    def anmelden(page, user, pw):
        page.on('pageerror', lambda e: errs.append(str(e)))
        page.goto(B + '/admin/'); page.wait_for_selector('#screen-auth:not([hidden])')
        page.fill('#au-user', user); page.fill('#pw1', pw); page.click('#auth-submit')
        page.wait_for_selector('#screen-editor:not([hidden])')
        page.click('#vt-stock'); page.wait_for_selector('.stab')

    a = br.new_page(viewport={'width': 1440, 'height': 950})
    anmelden(a, 'erika', 'Editor-Zugang-77')
    knopf = a.locator('[data-st=mhdmail]')
    check('Knopf „MHD an Verkauf“ neben „Drucken“', knopf.count() == 1 and 'MHD an Verkauf' in knopf.inner_text()
          and a.evaluate("document.querySelector('[data-st=mhdmail]').previousElementSibling.dataset.st") == 'print')
    a.fill('#st-q', 'MHD'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 3")
    a.screenshot(path=os.path.join(SH, 'mhd-mail-1440.png'))
    n0 = len(smtp.messages)
    knopf.click(); a.wait_for_selector('#dlg-confirm[open]')
    check('Rückfrage nennt Anzahl und Empfänger-Einstellung', '3 Artikel' in a.inner_text('#confirm-body') and 'Benachrichtigungen' in a.inner_text('#confirm-body'))
    a.click('#confirm-body [data-v="1"]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('gesendet an')")
    check('Rückmeldung mit Empfängern', 'verkauf@example.org' in a.inner_text('#toast'), a.inner_text('#toast'))
    until(lambda: len(smtp.messages) >= n0 + 2)
    bild = teil(smtp.messages[n0]['msg'], 'image/png')[0].get_content()
    with open(os.path.join(SH, 'mhd-mail-bild.png'), 'wb') as f:
        f.write(bild)
    breite, hoehe = struct.unpack('>II', bild[16:24])
    check('Bild aus der Oberfläche: PNG in doppelter Auflösung, Höhe passt zu 3 Zeilen', bild[:8] == b'\x89PNG\r\n\x1a\n' and breite >= 2400 and 400 <= hoehe <= 800, (breite, hoehe))
    # Gleiche Liste unabhängig von der aktuellen Suche
    a.fill('#st-q', 'Test Später'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 1")
    n0 = len(smtp.messages)
    knopf.click(); a.wait_for_selector('#dlg-confirm[open]')
    check('andere Suche: trotzdem die MHD-Liste (3 Artikel)', '3 Artikel' in a.inner_text('#confirm-body'))
    a.click('#confirm-body [data-v="0"]')
    a.set_viewport_size({'width': 390, 'height': 844})
    a.fill('#st-q', 'MHD'); a.wait_for_function("document.querySelectorAll('.stab tr.srow').length === 3")
    a.screenshot(path=os.path.join(SH, 'mhd-mail-390.png'))
    check('390 px: kein waagerechtes Scrollen', a.evaluate('document.documentElement.scrollWidth') <= 390)
    v = br.new_page(viewport={'width': 1440, 'height': 950})
    anmelden(v, 'lea', 'Leser-Zugang-77')
    check('Leser: kein Knopf', v.locator('[data-st=mhdmail]').count() == 0)
    check('keine JavaScript-Fehler', not errs, errs)
    br.close()

smtp.close()
print(f"{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
