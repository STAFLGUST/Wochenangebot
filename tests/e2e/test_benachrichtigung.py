"""Benachrichtigungen an Mitarbeiter: Einstellungen (nur Administrator), Sicherheitsereignisse, Bündelung,
Anmeldesperre, Abmeldung vom Wochenangebot, Test-Benachrichtigung, Oberfläche. Läuft gegen den Test-Mailserver."""
import base64
import hashlib
import hmac
import json
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, shot, until, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name)
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


def mails_to(addr):
    return [m for m in smtp.messages if addr in m['to']]


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('no mail before notifications are configured', not smtp.messages, [m['subject'] for m in smtp.messages])

# ---------- Einstellungen ----------
code, st = A.call('mail_status')
n = st['notify']
check('status lists the events', [e['key'] for e in n['events']] == ['bestellung', 'sicherheit', 'einkauf', 'mhd', 'abmeldung'], n)
check('defaults: no recipients; security off; unsubscribe notice on (to reply address)', all(not e['to'] for e in n['events']) and [e['on'] for e in n['events']] == [False, False, True, True, True] and n['events'][4]['ersatz'] == 'verkauf@example.org' and n['events'][2]['manuell'] and n['events'][3]['manuell'], n)
check('order event is fixed', [e['fest'] for e in n['events']] == [True, False, False, False, False])
check('editor cannot change notifications', E.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'x@example.org'}}})[0] == 403)
check('editor cannot send test', E.call('benachrichtigung_test', {'event': 'sicherheit'})[0] == 403)
check('editor cannot read mail settings', E.call('mail_status')[0] == 403)
check('invalid address rejected', A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org, kein-mail'}}})[0] == 422)
check('max 5 recipients', A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': ','.join(f'a{i}@example.org' for i in range(6))}}})[0] == 422)
code, r = A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': ''}}})
check('on without recipient rejected', code == 422 and 'Sicherheitsereignisse' in r['error'], r)
check('malformed request rejected', A.call('benachrichtigung_save', {'events': 'x'})[0] == 422)
code, r = A.call('benachrichtigung_save', {'events': {
    'bestellung': {'to': 'bestellung@example.org; Verkauf@example.org bestellung@example.org'},
    'sicherheit': {'on': True, 'to': 'it@example.org'},
    'abmeldung': {'on': True, 'to': 'verkauf@example.org'}}})
ev = {e['key']: e for e in r.get('notify', {}).get('events', [])}
check('settings saved', code == 200 and ev['sicherheit']['on'] and ev['sicherheit']['to'] == ['it@example.org'] and ev['abmeldung']['to'] == ['verkauf@example.org'], r)
check('order recipients deduplicated and stored with the order function', r['orders']['to'] == ['bestellung@example.org', 'Verkauf@example.org'] and (doc('bestellung') or {}).get('to') == ['bestellung@example.org', 'Verkauf@example.org'])
check('order recipients readable by older versions (same field)', 'to' in (doc('bestellung') or {}))
check('order function still off', r['orders']['enabled'] is False)
code, r = A.call('bestell_settings_save', {'enabled': True, 'copy': False})
check('order form without recipients keeps them and can switch on', code == 200 and r['orders']['enabled'] and r['orders']['to'] == ['bestellung@example.org', 'Verkauf@example.org'], r)
code, r = A.call('benachrichtigung_save', {'events': {'bestellung': {'to': ''}}})
check('order recipients cannot be emptied while ordering is on', code == 422 and 'Bestellfunktion' in r['error'])
log = A.call('log')[1]
check('change is logged', 'Benachrichtigungen geändert' in json.dumps(log, ensure_ascii=False))
check('saving settings itself sends no mail', not mails_to('it@example.org'))

# ---------- Sicherheitsereignis: neuer Nutzer ----------
A.call('user_save', {'id': '', 'name': 'Max Muster', 'username': 'max.muster', 'role': 'admin', 'active': True, 'password': 'Max-Zugang-12345', 'mustChange': False})
check('security event: mail to IT', until(lambda: len(mails_to('it@example.org')) == 1, 8), [m['subject'] for m in smtp.messages])
m = mails_to('it@example.org')[0] if mails_to('it@example.org') else {'subject': '', 'text': '', 'html': ''}
check('mail names event, who and what', 'Sicherheitsereignisse' in m['subject'] and 'max.muster' in m['text'] and 'admin' in m['text'] and '198.51.100.2' in m['text'], m['text'][:600])
check('mail links to the admin area', '/admin/' in m['text'] and '/admin/' in m['html'])
check('html is escaped', '<script' not in m['html'])
check('only IT gets security mail', not mails_to('verkauf@example.org') and not mails_to('bestellung@example.org'))
check('mail log lists the notification', any(x['typ'] == 'benachrichtigung' and x['to'] == 'it@example.org' and x['ok'] for x in A.call('mail_status')[1]['log']))

# ---------- Bündelung: innerhalb der Pause nur zählen ----------
check('second user saved', A.call('user_save', {'id': '', 'name': 'Nina Neu', 'username': 'nina', 'role': 'viewer', 'active': True, 'password': 'Zweiter-Zugang-4711', 'mustChange': False})[0] == 200)
check('second event within pause: no extra mail', len(mails_to('it@example.org')) == 1, len(mails_to('it@example.org')))
stand = doc('benachrichtigung-stand') or {}
check('skipped event counted', stand.get('sicherheit', {}).get('skipped') == 1, stand)
stand['sicherheit']['last'] = stand['sicherheit']['last'] - 3600
storage_write('benachrichtigung-stand', stand)
A.call('wartung_save', {'active': True, 'message': '', 'until': ''})
check('after pause: next mail mentions skipped events', until(lambda: len(mails_to('it@example.org')) == 2, 8) and 'weitere Ereignisse' in mails_to('it@example.org')[-1]['text'], [m['text'][-300:] for m in mails_to('it@example.org')[-1:]])
A.call('wartung_save', {'active': False, 'message': '', 'until': ''})

# ---------- Anmeldesperre nach Fehlversuchen ----------
stand = doc('benachrichtigung-stand') or {}
stand['sicherheit'] = {'last': 0, 'skipped': 0}
storage_write('benachrichtigung-stand', stand)
X = Client('203.0.113.77')
for _ in range(5): X.call('login', {'username': 'admin', 'password': 'falsch-falsch-1'})
check('lockout triggers mail', until(lambda: any('Anmeldesperre' in x['subject'] for x in mails_to('it@example.org')), 8), [x['subject'] for x in mails_to('it@example.org')])
lm = [x for x in mails_to('it@example.org') if 'Anmeldesperre' in x['subject']]
check('lockout mail names the IP', bool(lm) and '203.0.113.77' in lm[0]['text'])
check('locked client still gets its error quickly', X.call('login', {'username': 'admin', 'password': PW})[0] == 429)

# Versand geschieht vor dem Ende der Antwort (nach dem Speichern) – Negativprüfungen brauchen also keine Wartezeit.
# ---------- Abmeldung vom Wochenangebot ----------
code, k = A.call('kunden')
code, r = A.call('kunde_save', {'id': '', 'rev': k['rev'], 'firma': 'Gasthaus Linde', 'nr': 'K-9', 'ansprechpartner': '', 'strasse': '', 'plz': '', 'ort': '',
                                'land': '', 'email': 'linde@example.org', 'telefon': '', 'notiz': '', 'active': True, 'angebote': ['std'], 'login': None})
kid = r['customer']['id']
key = bytes(range(32))
storage_write('abmelde-schluessel', {'key': base64.b64encode(key).decode(), 'created': '2026-10-01T00:00:00Z'})
tok = kid + '.' + base64.urlsafe_b64encode(hmac.new(key, ('abmelden|' + kid).encode(), hashlib.sha256).digest()).decode().rstrip('=')[:32]
P = Client('198.51.100.40')
code, r = P.call('kunde_abmelden', {'token': tok})
check('customer unsubscribes', code == 200, r)
check('sales gets unsubscribe notice (configured recipient)', until(lambda: len(mails_to('verkauf@example.org')) == 1, 8) and 'Gasthaus Linde' in mails_to('verkauf@example.org')[0]['text'], [m['subject'] for m in smtp.messages[-3:]])
check('no duplicate notice', len(mails_to('verkauf@example.org')) == 1)

# ---------- Ausgeschaltet: keine E-Mail ----------
A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': False, 'to': 'it@example.org'}}})
before = len(mails_to('it@example.org'))
stand = doc('benachrichtigung-stand') or {}; stand['sicherheit'] = {'last': 0, 'skipped': 0}; storage_write('benachrichtigung-stand', stand)
check('third user saved', A.call('user_save', {'id': '', 'name': 'Olaf Off', 'username': 'olaf', 'role': 'viewer', 'active': True, 'password': 'Dritter-Zugang-4712', 'mustChange': False})[0] == 200)
check('switched off: no mail', len(mails_to('it@example.org')) == before)
check('switched off: recipients kept', A.call('mail_status')[1]['notify']['events'][1]['to'] == ['it@example.org'])

# ---------- Test-Benachrichtigung ----------
code, r = A.call('benachrichtigung_test', {'event': 'sicherheit'})
check('test notification sent', code == 200 and r['results'] == [{'to': 'it@example.org', 'ok': True, 'error': ''}], r)
check('test mail is marked as test', until(lambda: any('Test-Benachrichtigung' in x['text'] for x in mails_to('it@example.org')), 5))
check('unknown event rejected', A.call('benachrichtigung_test', {'event': 'quatsch'})[0] == 422)
A.call('benachrichtigung_save', {'events': {'abmeldung': {'on': True, 'to': ''}}})
code, r = A.call('benachrichtigung_test', {'event': 'abmeldung'})
check('unsubscribe notice without recipients goes to reply address', code == 200 and [x['to'] for x in r['results']] == ['verkauf@example.org'], r)
A.call('benachrichtigung_save', {'events': {'abmeldung': {'on': False, 'to': ''}}})
P2 = Client('198.51.100.41'); n0 = len(mails_to('verkauf@example.org'))
P2.call('kunde_abmelden', {'token': tok, 'wieder': True}); P2.call('kunde_abmelden', {'token': tok})
check('unsubscribe notice switched off: no mail', len(mails_to('verkauf@example.org')) == n0)
check('test requires CSRF (POST + JSON)', A.call('benachrichtigung_test')[0] in (403, 405, 415))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-mail'); a.wait_for_selector('#ml-notify .nt-row')
    check('card shows five events (incl. MHD-Liste)', a.locator('#ml-notify .nt-row').count() == 5)
    check('purchasing row has no switch (on demand)', a.locator('#ml-notify [name=on-einkauf]').count() == 0 and 'Knopf' in a.inner_text('#ml-notify [data-ev=einkauf]'))
    check('order row shows fixed state and recipients', a.input_value('#ml-notify [name=to-bestellung]') == 'bestellung@example.org, Verkauf@example.org' and a.locator('#ml-notify [name=on-bestellung]').count() == 0)
    check('order form shows where recipients are set', 'Benachrichtigungen' in a.inner_text('#ml-orders .ml-oto'))
    a.check('#ml-notify [name=on-sicherheit]')
    check('switch label follows', a.inner_text('#ml-notify [data-ev=sicherheit] .nt-sw span') == 'an')
    a.fill('#ml-notify [name=to-abmeldung]', 'kein-mail'); a.check('#ml-notify [name=on-abmeldung]'); a.click('#ml-notify [type=submit]')
    a.wait_for_selector('#ml-nerr:not(:empty)')
    check('UI shows validation error', 'keine gültige' in a.inner_text('#ml-nerr'))
    a.fill('#ml-notify [name=to-abmeldung]', 'verkauf@example.org, chef@example.org'); a.click('#ml-notify [type=submit]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Benachrichtigungen gespeichert')", timeout=8000)
    ev = {e['key']: e for e in A.call('mail_status')[1]['notify']['events']}
    check('UI saves switches and recipients', ev['sicherheit']['on'] and ev['abmeldung']['on'] and ev['abmeldung']['to'] == ['verkauf@example.org', 'chef@example.org'], ev)
    a.wait_for_selector('#ml-notify [data-ml=ntest][data-ev=abmeldung]:not([disabled])')
    n0 = len(mails_to('chef@example.org'))
    a.click('#ml-notify [data-ml=ntest][data-ev=abmeldung]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Test-Benachrichtigung')", timeout=8000)
    check('UI test button sends', until(lambda: len(mails_to('chef@example.org')) == n0 + 1, 5))
    shot(a.locator('#ml-notify'), SH + '/benachrichtigungen.png')
    a.set_viewport_size({'width': 390, 'height': 844})
    a.locator('#ml-notify').scroll_into_view_if_needed()
    check('mobile: no horizontal scroll', a.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    shot(a.locator('#ml-notify'), SH + '/benachrichtigungen-mobil.png')
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
