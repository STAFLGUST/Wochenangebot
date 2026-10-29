"""Postfach für interne E-Mails (z. B. verwaltung@…): eigenes Postfach neben dem Kunden-Postfach. Interne E-Mails
(Zugangsdaten an Mitarbeiter, Benachrichtigungen, Bestellwunsch an das Team) gehen darüber, alles an Kunden
(Testmail Standard, Bestellkopie) weiter über das Kunden-Postfach. Ohne eigenes internes Postfach gilt das
Kunden-Postfach. Rechte, Prüfungen, Passwort nur verschlüsselt, Protokoll, Oberfläche 1440/390 px.
Läuft gegen zwei Test-Mailserver – es werden nie echte E-Mails versendet."""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, SMTP_PORT2, storage_raw, until

PW = 'Sicheres-Passwort-1'
INTERN_PW = 'Verwaltung-Postfach-7'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def neu(server, n0):
    until(lambda: len(server.messages) > n0)
    return server.messages[n0:]


kunden = TestSmtp(SMTP_PORT, password='Test-Postfach-1')                       # Postfach für Kunden (.env der Gruppe)
intern = TestSmtp(SMTP_PORT2, user='verwaltung@example.org', password=INTERN_PW)  # Postfach für interne E-Mails
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3')
E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})

# ---------- Ohne eigenes internes Postfach: Kunden-Postfach ----------
code, st = A.call('mail_status')
check('Status: kein internes Postfach, intern wird das Kunden-Postfach verwendet', code == 200 and st['accountIntern'] is None
      and st['smtpIntern']['from'] == 'angebot@example.org' and st['smtpIntern']['source'] == 'env', st.get('smtpIntern'))
NEU = {'role': 'editor', 'active': True, 'password': 'Start-Kennwort-4711', 'mustChange': True}
st_, r = A.call('user_save', {**NEU, 'vorname': 'Max', 'nachname': 'Muster', 'email': 'max@example.org', 'username': ''})
MAX = r['user']['id']
n0 = len(kunden.messages)
check('Zugangsdaten ohne internes Postfach: über das Kunden-Postfach', A.call('user_mail', {'id': MAX})[0] == 200
      and neu(kunden, n0)[-1]['to'] == ['max@example.org'])
check('Testmail „intern“ ohne internes Postfach: über das Kunden-Postfach', A.call('mail_test', {'to': 'ich@example.org', 'konto': 'intern'})[0] == 200
      and len(kunden.messages) == n0 + 2)

# ---------- Internes Postfach einrichten ----------
konto = {'konto': 'intern', 'host': '127.0.0.1', 'port': SMTP_PORT2, 'secure': 'none', 'user': 'verwaltung@example.org', 'password': INTERN_PW,
         'from': 'verwaltung@example.org', 'fromName': 'STAFL Verwaltung', 'replyTo': 'it@example.org'}
check('Bearbeiter darf das interne Postfach nicht ändern', E.call('mail_konto_save', konto)[0] == 403)
check('unbekanntes Postfach → 422', A.call('mail_konto_save', {**konto, 'konto': 'privat'})[0] == 422)
check('unverschlüsselt nur an einen lokalen Server', A.call('mail_konto_save', {**konto, 'host': 'smtp.example.org'})[0] == 422)
check('ungültige Absenderadresse → 422', A.call('mail_konto_save', {**konto, 'from': 'kein'})[0] == 422)
check('ungültige Antwortadresse → 422', A.call('mail_konto_save', {**konto, 'replyTo': 'kein'})[0] == 422)
code, r = A.call('mail_konto_save', konto)
check('gespeichert, Verbindung und Anmeldung geprüft', code == 200 and r['connection']['ok'] is True and intern.logins[-1] == ('verwaltung@example.org', True, False), r)
code, st, raw = A.call('mail_status', raw=True)
check('Status: internes Postfach eingerichtet, Kunden-Postfach unverändert',
      st['accountIntern']['from'] == 'verwaltung@example.org' and st['accountIntern']['password'] is True and st['smtpIntern']['source'] == 'intern'
      and st['smtp']['from'] == 'angebot@example.org' and st['account'] is None, (st['accountIntern'], st['smtp']['from']))
check('Passwort nie in der Antwort', INTERN_PW not in raw)
gespeichert = storage_raw('mailkonto-intern') or ''
check('Passwort nur verschlüsselt gespeichert (eigenes Dokument)', INTERN_PW not in gespeichert and '"passEnc": "v1:' in gespeichert.replace('":"', '": "'))
check('Kunden-Postfach-Dokument nicht angelegt', not (storage_raw('mailkonto') or '').strip() or 'verwaltung@' not in storage_raw('mailkonto'))
code, r = A.call('mail_konto_save', {**konto, 'port': SMTP_PORT, 'password': ''})
check('geänderter Server: Passwort erneut nötig', code == 422 and 'Passwort' in r.get('error', ''))
check('gleicher Server: gespeichertes Passwort bleibt', A.call('mail_konto_save', {**konto, 'password': ''})[1]['connection']['ok'] is True)

# ---------- Intern über verwaltung@, Kunden über das Kunden-Postfach ----------
n0, k0 = len(intern.messages), len(kunden.messages)
check('Zugangsdaten an Mitarbeiter: über das interne Postfach', A.call('user_mail', {'id': MAX, 'password': 'Start-Kennwort-4711'})[0] == 200)
m = neu(intern, n0)[-1]
check('… Absender verwaltung@ mit Namen, Antwort an it@, an den Mitarbeiter', m['to'] == ['max@example.org'] and m['from'] == 'verwaltung@example.org'
      and 'STAFL Verwaltung' in str(m['msg']['from']) and str(m['msg']['reply-to']) == 'it@example.org' and len(kunden.messages) == k0, str(m['msg']['from']))
check('Benachrichtigung speichern', A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'sicherheit@example.org'}}})[0] == 200)
n0 = len(intern.messages)
code, r = A.call('benachrichtigung_test', {'event': 'sicherheit'})
check('Benachrichtigung: über das interne Postfach', code == 200 and r['results'][0]['ok'] and neu(intern, n0)[-1]['to'] == ['sicherheit@example.org']
      and len(kunden.messages) == k0, r)
n0 = len(intern.messages)
check('Testmail „intern“: über das interne Postfach', A.call('mail_test', {'to': 'ich@example.org', 'konto': 'intern'})[0] == 200
      and 'interne E-Mails' in neu(intern, n0)[-1]['msg']['subject'])
k0 = len(kunden.messages)
check('Testmail ohne Angabe: über das Kunden-Postfach', A.call('mail_test', {'to': 'ich@example.org'})[0] == 200
      and neu(kunden, k0)[-1]['from'] == 'angebot@example.org')

# Bestellwunsch: an das Team intern, Kopie an den Kunden über das Kunden-Postfach
code, d = A.call('draft')
model = d['draft'] or d['published']
I1 = model['items'][0]
I1.setdefault('variants', {})['edeka'] = {'status': 'value', 'value': 19.99}
check('Angebot veröffentlicht', A.call('publish', {'model': model})[0] == 200)
code, r = A.call('kunden')
code, r = A.call('kunde_save', {'id': '', 'rev': r['rev'], 'firma': 'Kantine Intern-Test', 'nr': 'K-88', 'ansprechpartner': 'Frau Koch', 'strasse': '', 'plz': '', 'ort': 'Hamburg',
                                'land': '', 'email': 'kantine@example.org', 'telefon': '', 'notiz': '', 'active': True, 'angebote': ['edeka'],
                                'login': {'username': 'kantine.intern', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
check('Bestellfunktion an, Kopie an den Kunden', A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org', 'copy': True})[0] == 200)
K = Client('198.51.100.20')
check('Kunde angemeldet', K.call('kunde_login', {'username': 'kantine.intern', 'password': 'Kantine-Kennwort-5'})[0] == 200)
code, off = K.call('offer&angebot=edeka')
pub = off['offer'].get('publishedAt') or off['offer'].get('savedAt') or ''
n0, k0 = len(intern.messages), len(kunden.messages)
code, r = K.call('kunde_bestellung', {'angebot': 'edeka', 'publishedAt': pub, 'termin': '', 'referenz': '', 'bemerkung': '', 'positions': [{'id': I1['id'], 'qty': 5}]})
check('Bestellwunsch angenommen', code == 200, r)
until(lambda: len(intern.messages) > n0 and len(kunden.messages) > k0)
an_team = [x for x in intern.messages[n0:] if x['to'] == ['bestellung@example.org']]
kopie = [x for x in kunden.messages[k0:] if x['to'] == ['kantine@example.org']]
check('Bestellwunsch an das Team: über das interne Postfach, Antwort an den Kunden', len(an_team) == 1 and str(an_team[0]['msg']['reply-to']) == 'kantine@example.org',
      [x['to'] for x in intern.messages[n0:]])
check('Kopie an den Kunden: über das Kunden-Postfach (nie über verwaltung@)', len(kopie) == 1 and kopie[0]['from'] == 'angebot@example.org'
      and not [x for x in intern.messages[n0:] if x['to'] == ['kantine@example.org']], [x['to'] for x in kunden.messages[k0:]])

code, r, raw = A.call('log', raw=True)
check('Protokoll: internes Postfach eingerichtet, ohne Passwort', 'Postfach für interne E-Mails eingerichtet' in raw and INTERN_PW not in raw)

# ---------- Oberfläche ----------
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/')
    a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit')
    a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-mail'); a.wait_for_selector('#ml-form-int')
    check('zwei Postfächer: Kunden und intern', a.inner_text('#ml-form h3.sec-h >> nth=0') == 'Postfach für Kunden-E-Mails'
          and a.inner_text('#ml-form-int h3.sec-h >> nth=0') == 'Postfach für interne E-Mails')
    check('internes Postfach: Werte vorbelegt, Passwort nie angezeigt, Stand sichtbar', a.input_value('#ml-form-int [name=from]') == 'verwaltung@example.org'
          and a.input_value('#ml-form-int [name=password]') == '' and 'Eingerichtet' in a.inner_text('#ml-form-int .ml-int-st'))
    check('gespeicherte Verschlüsselung bleibt erhalten (lokaler Server: unverschlüsselt)', a.input_value('#ml-form-int [name=secure]') == 'none')
    check('Testmail: Postfach wählbar', a.locator('#ml-tkonto option[value=intern]:not([disabled])').count() == 1)
    a.locator('#ml-form-int').scroll_into_view_if_needed()
    a.screenshot(path=os.path.join(SH, 'mail-intern-1440.png'))
    # Speichern über die Oberfläche (Absendername geändert, Passwort leer = unverändert)
    a.fill('#ml-form-int [name=fromName]', 'STAFL Verwaltung Hamburg')
    a.click('#ml-form-int [type=submit]')
    # Passwortbestätigung des Administrators, falls die letzte Anmeldung zu lange her ist
    a.wait_for_function("document.querySelector('#dlg-reauth').open || document.querySelector('#ml-form-int .ml-int-st').textContent.includes('Hamburg') || document.querySelector('#ml-err-int').textContent")
    if a.locator('#dlg-reauth[open]').count():
        a.fill('#reauth-password', PW); a.click('#reauth-submit')
    a.wait_for_function("document.querySelector('#ml-form-int .ml-int-st') && document.querySelector('#ml-form-int .ml-int-st').textContent.includes('Hamburg')")
    check('Oberfläche: internes Postfach gespeichert', A.call('mail_status')[1]['accountIntern']['fromName'] == 'STAFL Verwaltung Hamburg')
    a.set_viewport_size({'width': 390, 'height': 844})
    a.locator('#ml-form-int').scroll_into_view_if_needed()
    a.screenshot(path=os.path.join(SH, 'mail-intern-390.png'))
    check('390 px: kein waagerechtes Scrollen', a.evaluate('document.documentElement.scrollWidth') <= 390)
    check('keine JavaScript-Fehler', not errs, errs)
    br.close()

# ---------- Entfernen: zurück zum Kunden-Postfach ----------
check('internes Postfach entfernen', A.call('mail_konto_save', {'konto': 'intern', 'remove': True})[0] == 200)
code, st = A.call('mail_status')
check('danach wieder Kunden-Postfach für interne E-Mails', st['accountIntern'] is None and st['smtpIntern']['from'] == 'angebot@example.org')
k0 = len(kunden.messages)
check('Zugangsdaten danach über das Kunden-Postfach', A.call('user_mail', {'id': MAX})[0] == 200 and neu(kunden, k0)[-1]['to'] == ['max@example.org'])

kunden.close(); intern.close()
print(f"{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
