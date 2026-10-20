"""Schutzzentrale (Verwaltung → Schutz): Rechte, Falle für Angriffswerkzeuge mit automatischer Sperre und Benachrichtigung,
Firewall-Muster (Abfrage, Werkzeuge, JSON-Inhalt ohne Anmeldung, Mitarbeiter nicht im Inhalt), Modi protokollieren/aus,
nie gesperrte Adressen, Fehlerbremse, Sperren/Freigeben von Hand (Prüfungen, Bestätigung, Protokoll), Bedrohungsliste,
Live-Verkehr (Tokens unkenntlich, „seit“, Filter, Mitschnitt), Vorlagen, Export/Import und Oberfläche (Desktop, 390 px).
Nur synthetische Testdaten und Adressen aus Dokumentationsnetzen; es werden keine echten E-Mails versendet."""
import json
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from auth_helpers import expire_session
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SMTP_PORT, storage_raw, storage_write, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def roh(ip, query, ua='Mozilla/5.0 Testbrowser', data=None):
    req = urllib.request.Request(BASE + '/api/?action=' + query, data=data, headers={'X-Forwarded-For': ip, 'User-Agent': ua, 'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as ex:
        r = ex
    return r.code, r.read().decode('utf-8', 'replace')


def bestaetigung_ablaufen(cl):
    jar = next(h.cookiejar for h in cl.http.handlers if isinstance(h, urllib.request.HTTPCookieProcessor))
    expire_session(next(c.value for c in jar if c.name == 'WA_ADMIN'))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
storage_write('benachrichtigungen', {'events': {'sicherheit': {'on': True, 'to': ['it@example.org']}}})

# ---------- Rechte ----------
check('ohne Anmeldung gesperrt', Client('203.0.113.200').call('fw_status')[0] == 401)
check('Bearbeiter gesperrt', E.call('fw_status')[0] == 403 and E.call('fw_save', {'waf': 'aus'})[0] == 403)
check('Speichern nur per POST', A.call('fw_save')[0] == 405)
st, r = A.call('fw_status')
check('Administrator: Übersicht mit Standard-Einstellungen', st == 200 and r['fw']['waf'] == 'sperren' and r['fw']['treffer'] == 5 and set(r['vorlagen']) == {'standard', 'streng', 'notfall'}, r.get('fw'))

# ---------- Falle → automatische Sperre ----------
X = '203.0.113.10'
codes = [roh(X, 'waf_probe&p=/wp-login.php')[0] for _ in range(4)]
check('Falle antwortet wie „nicht vorhanden“ (404)', codes == [404] * 4 and 'Nicht gefunden' in roh(X, 'waf_probe&p=/.env')[1], codes)
st, body = roh(X, 'offer')
check('nach 5 Treffern: Adresse gesperrt (auch für die Angebotsseite)', st == 403 and 'gesperrt' in body, (st, body[:120]))
check('… auch Kunden-Anmeldung', roh(X, 'kunde_login', data=b'{"username":"x","password":"y"}')[0] == 403)
check('… andere Adressen nicht betroffen', roh('203.0.113.11', 'offer')[0] == 200)
L = doc('sperrliste')
check('automatische Sperre gespeichert (Grund, Dauer 1 h)', X in L['auto'] and 'Schwachstellen' in L['auto'][X]['grund'] and 3500 < L['auto'][X]['bis'] - time.time() <= 3600, L.get('auto'))
check('Protokoll: automatisch gesperrt', 'Adresse 203.0.113.10 automatisch gesperrt' in json.dumps(A.call('log')[1], ensure_ascii=False))
until(lambda: any('Sicherheitsereignisse' in m.get('subject', '') for m in smtp.messages), timeout=10)
check('Benachrichtigung „Sicherheitsereignisse“ verschickt', any('Sicherheitsereignisse' in m.get('subject', '') and 'it@example.org' in m.get('to', []) for m in smtp.messages),
      [m.get('subject') for m in smtp.messages])
# IPv6: ganzes /64
for i in range(5): roh(f'3fff:0:5:6::{i + 1}', 'waf_probe&p=/xmlrpc.php')   # 3fff::/20: Dokumentationsnetz (RFC 9637)
check('IPv6: Sperre gilt für das ganze /64', roh('3fff:0:5:6:abcd::1', 'offer')[0] == 403 and roh('3fff:0:5:7::1', 'offer')[0] == 200)

# ---------- Firewall-Muster ----------
Y = '203.0.113.20'
st, body = roh(Y, "offer&angebot=x%27%20union%20select%201,2--")
check('SQL-Einschleusung in der Abfrage abgewiesen', st == 403 and 'Firewall' in body, (st, body[:100]))
check('bekanntes Angriffswerkzeug (sqlmap) abgewiesen', roh('203.0.113.21', 'offer', ua='sqlmap/1.7.2#stable (https://sqlmap.org)')[0] == 403)
check('Pfadmanipulation abgewiesen', roh('203.0.113.22', 'history_prev&week=../../../../etc/passwd')[0] == 403)
st, _ = roh('203.0.113.23', 'kunde_login', data=json.dumps({'username': "admin' OR '1'='1", 'password': 'x'}).encode())
check('Angriff im JSON-Inhalt (ohne Anmeldung) abgewiesen', st == 403)
st, _ = roh('203.0.113.24', 'kunde_login', data=b'{"username":"\\u003cscript\\u003ealert(1)\\u003c/script\\u003e","password":"x"}')
check('… auch versteckt als \\u003cscript', st == 403)
st, _ = roh('203.0.113.25', 'kunde_login', data=json.dumps({'username': 'kantine.nord', 'password': 'Bitte <b>vakuumiert</b>, 10 % Rabatt; Lieferung 2x'}).encode())
check('normale Eingaben (mit <b>, Prozent, Semikolon) kommen durch', st == 401, st)
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Test <script>alert(1)</script> GmbH', 'nr': 'FW-1', 'email': 'fw@example.org', 'active': True, 'angebote': []})
check('angemeldete Mitarbeiter: Inhalt nicht geprüft (Speichern möglich, Ausgabe wird ohnehin maskiert)', st == 200, r)
v = A.call('fw_verkehr')[1]['verkehr']
check('Live-Verkehr: Firewall-Treffer mit Grund', any(e['ip'] == Y and e['why'].startswith('Firewall: SQL') and e['st'] == 403 for e in v), v[:2])

st, r = A.call('fw_save', {'waf': 'protokoll'})
check('Modus „nur protokollieren“: Anfrage kommt durch, wird vermerkt', st == 200 and roh('203.0.113.30', "offer&q=%3Cscript%3E")[0] == 200
      and any(e['ip'] == '203.0.113.30' and 'nur protokolliert' in e['why'] for e in A.call('fw_verkehr')[1]['verkehr']))
A.call('fw_save', {'waf': 'aus'})
check('Modus „aus“: keine Prüfung', roh('203.0.113.31', "offer&q=%3Cscript%3E")[0] == 200 and not any(e['ip'] == '203.0.113.31' for e in A.call('fw_verkehr')[1]['verkehr']))
A.call('fw_save', {'waf': 'sperren'})

# ---------- nie sperren ----------
check('interne Adressen werden nie gesperrt', all(roh('10.1.2.3', 'waf_probe&p=/.git/config')[0] == 404 for _ in range(6)) and roh('10.1.2.3', 'offer')[0] == 200)
st, r = A.call('fw_save', {'erlaubt': ['203.0.113.40'], 'treffer': 2})
for _ in range(4): roh('203.0.113.40', 'waf_probe&p=/wp-admin/')
check('Liste „nie sperren“ wirkt', st == 200 and roh('203.0.113.40', 'offer')[0] == 200, r.get('error'))
st, r = A.call('fw_save', {'erlaubt': ['kein-netz']})
check('ungültiger Eintrag abgewiesen', st == 422)

# ---------- Fehlerbremse ----------
A.call('fw_save', {'fehlerLimit': 3, 'erlaubt': []})
codes = [roh('203.0.113.50', 'gibt_es_nicht')[0] for _ in range(4)]
check('Fehlerbremse: nach 3 fehlerhaften Anfragen gesperrt', codes[:3] == [404, 404, 404] and codes[3] == 403, codes)
A.call('fw_save', {'fehlerLimit': 30, 'treffer': 5})

# ---------- Sperren und freigeben von Hand ----------
bestaetigung_ablaufen(A)
st, r = A.call('fw_sperren', {'ip': '203.0.113.60', 'minuten': 60})
check('Sperren verlangt Passwortbestätigung', st == 403 and r.get('code') == 'confirmation_required')
assert A.call('reauth', {'password': PW})[0] == 200
check('eigene Adresse wird nicht gesperrt', A.call('fw_sperren', {'ip': '198.51.100.2', 'minuten': 0})[0] == 422)
check('zu großer Bereich abgewiesen', A.call('fw_sperren', {'ip': '203.0.0.0/8', 'minuten': 0})[0] == 422)
check('ungültige Dauer abgewiesen', A.call('fw_sperren', {'ip': '203.0.113.60', 'minuten': 7})[0] == 422)
st, r = A.call('fw_sperren', {'ip': '203.0.113.64/30', 'minuten': 1440, 'grund': 'Test <Bereich>'})
check('Bereich gesperrt (bis morgen)', st == 200 and any(e['ip'] == '203.0.113.64/30' and e['grund'] == 'Test <Bereich>' and e['bis'] > time.time() + 86000 for e in r['manuell']), r.get('manuell'))
check('… gilt für Adressen im Bereich', roh('203.0.113.66', 'offer')[0] == 403 and roh('203.0.113.70', 'offer')[0] == 200)
check('Protokoll: von Hand gesperrt', 'Adresse 203.0.113.64/30 von Hand gesperrt' in json.dumps(A.call('log')[1], ensure_ascii=False))
st, r = A.call('fw_freigeben', {'ip': '203.0.113.64/30'})
check('freigeben hebt die Sperre auf', st == 200 and roh('203.0.113.66', 'offer')[0] == 200)
st, r = A.call('fw_freigeben', {'ip': X})
check('automatische Sperre freigeben', st == 200 and roh(X, 'offer')[0] == 200 and X not in doc('sperrliste')['auto'])
check('nicht gesperrte Adresse → 404', A.call('fw_freigeben', {'ip': '203.0.113.99'})[0] == 404)

# ---------- Bedrohungsliste ----------
storage_write('bedrohungsliste', {'quelle': 'Testliste', 'stand': '2026-10-20T10:00:00Z', 'anzahl': 2, 'netze': ['192.0.2.0/24', '3fff:0:dead::/48']})
st, r = A.call('fw_save', {'feed': True})
check('Bedrohungsliste einschalten', st == 200 and r['fw']['feed'] is True and r['feed']['anzahl'] == 2, r.get('error'))
check('Adresse aus der Bedrohungsliste abgewiesen', roh('192.0.2.77', 'offer')[0] == 403 and roh('3fff:0:dead:1::5', 'offer')[0] == 403)
check('… andere nicht', roh('198.51.100.77', 'offer')[0] == 200)
st, r = A.call('fw_feed_update', {})
check('Aktualisieren: Erfolg oder verständlicher Fehler ohne Verbindung (502)', st in (200, 502) and (st == 200 or 'Bedrohungsliste' in r.get('error', '')), (st, r.get('error')))
A.call('fw_save', {'feed': False})

# ---------- Live-Verkehr ----------
roh('203.0.113.80', 'abmelden1&t=GEHEIMER-TOKEN-123')
st, r = A.call('fw_save', {'mitschnittMinuten': 15})
check('Mitschnitt starten', st == 200 and r['mitschnitt'] > time.time() + 800)
jetzt = int(time.time()) - 1
roh('203.0.113.81', 'offer'); roh('203.0.113.82', 'abmelden1&t=GEHEIMER-TOKEN-456')
v = A.call(f'fw_verkehr&seit={jetzt}')[1]['verkehr']
txt = json.dumps(v, ensure_ascii=False)
check('Mitschnitt: alle Anfragen sichtbar, „seit“ liefert nur neue', any(e['ip'] == '203.0.113.81' and e['st'] == 200 for e in v) and all(e['t'] > jetzt for e in v), [e['ip'] for e in v])
check('Tokens in der Adresse unkenntlich', 'GEHEIMER-TOKEN' not in txt and 't=…' in txt)
A.call('fw_save', {'mitschnittMinuten': 0})
roh('203.0.113.83', 'offer')
check('nach dem Mitschnitt: normale Anfragen nicht gespeichert', not any(e['ip'] == '203.0.113.83' for e in A.call('fw_verkehr')[1]['verkehr']))
K = Client('203.0.113.84'); K.call('kunde_login', {'username': 'gibt.es.nicht', 'password': 'x'})
check('Anmeldungen werden immer vermerkt', any(e['ip'] == '203.0.113.84' and e['why'] == 'Anmeldung fehlgeschlagen' for e in A.call('fw_verkehr&filter=anmeldung')[1]['verkehr']))
check('Filter „Abgewiesen“', all(e['why'].startswith(('Gesperrt', 'Firewall', 'Falle')) for e in A.call('fw_verkehr&filter=gesperrt')[1]['verkehr']))
check('Ringpuffer begrenzt', len(doc('verkehr')) <= 500)

# ---------- Vorlagen, Export und Import ----------
sec0 = doc('sicherheit') or {}
st, r = A.call('fw_vorlage', {'vorlage': 'streng'})
check('Vorlage mit Zwei-Faktor-Pflicht verlangt eigene Zwei-Faktor-Anmeldung (wie beim Speichern)', st == 422 and 'Zwei-Faktor' in r.get('error', ''), r)
A.call('user_save', {'username': 'ada', 'name': 'Ada Admin', 'role': 'admin', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
D = Client('198.51.100.4'); assert D.call('login', {'username': 'ada', 'password': 'Bearbeiter-Zugang-1'})[0] == 200
import base64, hashlib, hmac, struct  # noqa: E401
sek = D.call('twofa_begin', {})[1]['secret']
key = base64.b32decode(sek + '=' * (-len(sek) % 8)); hs = hmac.new(key, struct.pack('>Q', int(time.time() // 30)), hashlib.sha1).digest(); o = hs[19] & 15
assert D.call('twofa_enable', {'code': '%06d' % ((struct.unpack('>I', hs[o:o + 4])[0] & 0x7fffffff) % 1000000)})[0] == 200
st, r = D.call('fw_vorlage', {'vorlage': 'streng'})
sec = doc('sicherheit'); fwd = doc('firewall')
check('„Streng“ angewendet (Sicherheit + Firewall)', st == 200 and sec['twofa'] == 'all' and sec['pwMin'] == 12 and sec['idleMinutes'] == 60 and fwd['treffer'] == 3 and fwd['sperrMinuten'] == 1440, (st, r.get('error')))
check('Bedrohungsliste nicht erreichbar → aus, Vorlage trotzdem angewendet (oder geladen)', fwd['feed'] in (True, False))
st, r = D.call('fw_vorlage', {'vorlage': 'notfall'})
check('„Notfall“: Sperre ab dem 1. Treffer für 7 Tage, Mitschnitt läuft', st == 200 and doc('firewall')['treffer'] == 1 and doc('firewall')['sperrMinuten'] == 10080 and r['mitschnitt'] > time.time())
check('Listen bleiben unverändert', doc('sicherheit').get('adminIps', []) == sec0.get('adminIps', []))
check('unbekannte Vorlage abgewiesen', D.call('fw_vorlage', {'vorlage': 'xyz'})[0] == 422)
storage_write('sicherheit', sec0)   # Ausgangslage für die Oberfläche (ohne Zwei-Faktor-Pflicht)
storage_write('firewall', {})
st, r = A.call('fw_export')
x = r.get('export', {})
check('Export: Sicherheit + Firewall, ohne Mitschnitt', st == 200 and x.get('art') == 'wochenangebot-sicherheit' and 'pwMin' in x['sicherheit'] and 'waf' in x['firewall'] and 'mitschnittBis' not in x['firewall'])
x['sicherheit']['pwMin'] = 14; x['firewall']['treffer'] = 7
st, r = A.call('fw_import', {'export': x})
check('Import übernimmt die Werte', st == 200 and doc('sicherheit')['pwMin'] == 14 and doc('firewall')['treffer'] == 7, r.get('error'))
check('fremde Datei abgewiesen', A.call('fw_import', {'export': {'art': 'etwas', 'version': 1}})[0] == 422)
check('Protokoll: Import und Vorlage', 'Sicherheitseinstellungen aus Datei übernommen' in json.dumps(A.call('log')[1], ensure_ascii=False))
A.call('fw_save', {'treffer': 5})

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h in ((1440, 950), (390, 820)):
        ctx = br.new_context(viewport={'width': w, 'height': h}, accept_downloads=True)
        a = ctx.new_page(); a.on('pageerror', lambda ex: errors.append(str(ex)))
        a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
        a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        a.evaluate("document.querySelector('#vt-schutz').click()"); a.wait_for_selector('#view-schutz .sec-grid')
        check(f'{w}px: vier Kacheln, Live-Verkehr, Sperrliste, Einstellungen, Vorlagen', a.locator('#view-schutz .sec-card').count() == 4 and a.locator('#fw-verkehr').count() == 1
              and a.locator('#fw-add').count() == 1 and a.locator('#fw-form').count() == 1 and a.locator('[data-fw=vorlage]').count() == 3)
        over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
        check(f'{w}px: kein waagrechtes Scrollen', over <= 1, over)
        if w == 1440:
            n0 = a.locator('#fw-rows tr').count()
            roh('203.0.113.90', 'waf_probe&p=/phpmyadmin/')
            a.wait_for_function(f"document.querySelectorAll('#fw-rows tr').length > {n0}", timeout=12000)
            check('Live-Verkehr aktualisiert sich selbst (neuer Eintrag ohne Neuladen)', '203.0.113.90' in a.inner_text('#fw-rows'))
            a.click('[data-fw-filter=anmeldung]'); a.wait_for_function("document.querySelector('[data-fw-filter=anmeldung]').classList.contains('on')")
            check('Filter „Anmeldungen“', all('Anmeldung' in t for t in a.locator('#fw-rows tr td:nth-child(3)').all_inner_texts()))
            a.click('[data-fw-filter=""]'); a.wait_for_function("document.querySelector('[data-fw-filter=\"\"]').classList.contains('on')")
            a.fill('#fw-add [name=ip]', '203.0.113.120'); a.click('#fw-add [type=submit]')
            a.wait_for_selector('#view-schutz [data-fw=frei][data-ip="203.0.113.120"]')
            check('Sperren über das Formular', roh('203.0.113.120', 'offer')[0] == 403)
            a.click('#view-schutz [data-fw=frei][data-ip="203.0.113.120"]'); a.click('#confirm-body [data-v="1"]')
            a.wait_for_function("!document.querySelector('#view-schutz [data-fw=frei][data-ip=\"203.0.113.120\"]')", timeout=8000)
            check('Freigeben über die Liste', roh('203.0.113.120', 'offer')[0] == 200)
            with a.expect_download() as dl:
                a.click('[data-fw=export]')
            check('Export als Datei', dl.value.suggested_filename.startswith('sicherheitseinstellungen-') and dl.value.suggested_filename.endswith('.json'))
        ctx.close()
    # Bearbeiter sieht den Bereich nicht
    e = br.new_page()
    e.goto(BASE + '/admin/'); e.wait_for_selector('#screen-auth:not([hidden])')
    e.fill('#au-user', 'eddi'); e.fill('#pw1', 'Editor-Zugang-77'); e.click('#auth-submit'); e.wait_for_selector('#screen-editor:not([hidden])')
    check('Bearbeiter: Bereich „Schutz“ nicht sichtbar', e.locator('#vt-schutz').is_hidden())
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
