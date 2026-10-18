"""E-Mail an Kunden: Einladung mit Einmal-Link, Passwort-Link, Angebotslink, Wochenversand, Testmail.
Läuft gegen einen Test-Mailserver (smtp_test.py) – es werden nie echte E-Mails versendet."""
from umgebung import storage_raw
from umgebung import SMTP_PORT, SMTP_PORT2  # Testserver je Gruppe (parallel)
import json
import re
import sys
import time
from playwright.sync_api import sync_playwright
from smtp_test import TestSmtp
from umgebung import SH
from kunden_hilfe import Client, B

PW = 'Sicheres-Passwort-1'
SMTP_PW = 'Test-Postfach-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def link_of(m):
    t = re.search(r'#zugang=([A-Za-z0-9_-]{40,64})', m['text'])
    return t.group(1) if t else None


smtp = TestSmtp(SMTP_PORT, password=SMTP_PW)
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)

# ---------- Status ----------
code, st, raw = A.call('mail_status', raw=True)
check('mail configured from environment', code == 200 and st['configured'] is True and st['smtp']['host'] == '127.0.0.1' and st['smtp']['from'] == 'angebot@example.org')
check('mail status never reveals the SMTP password', st['smtp']['password'] is True and SMTP_PW not in raw)
check('base URL from configuration', st['baseUrl'] == B)
check('current week from published offer', st['week'] and st['week']['week'] == 43 and st['week']['year'] == 2026, st['week'])

# ---------- Einladung ----------
base = {'id': '', 'rev': 0, 'firma': 'Gasthaus <b>Muster</b>', 'nr': 'K-1', 'ansprechpartner': 'Frau Beispiel', 'strasse': '', 'plz': '', 'ort': 'Hamburg',
        'land': '', 'email': 'einkauf@example.org', 'telefon': '', 'notiz': '', 'active': True, 'angebote': ['edeka', 'bela'],
        'login': {'username': 'gasthaus.muster', 'password': '', 'active': True, 'invite': True}}
check('no password and no invite rejected', A.call('kunde_save', {**base, 'login': {**base['login'], 'invite': False}})[0] == 422)
check('invite without email rejected', A.call('kunde_save', {**base, 'email': ''})[0] == 422)
check('email with line break rejected', A.call('kunde_save', {**base, 'email': 'a@example.org\r\nBcc: x@example.org'})[0] == 422)
code, r = A.call('kunde_save', base)
check('customer with pending invitation saved', code == 200 and r['customer']['login']['hasPassword'] is False, r)
K1, rev = r['customer']['id'], r['rev']
check('no login possible before password is set', Client('198.51.100.9').call('kunde_login', {'username': 'gasthaus.muster', 'password': ''})[0] == 401)
code, r = A.call('kunde_mail', {'id': K1, 'type': 'zugang'})
check('invitation sent', code == 200 and r['typ'] == 'invite' and len(smtp.messages) == 1, r)
m = smtp.messages[-1]
tok1 = link_of(m)
check('invitation: recipient, sender, reply-to', m['to'] == ['einkauf@example.org'] and 'angebot@example.org' in str(m['msg']['from']) and 'Standard-Fleisch' in str(m['msg']['from']) and str(m['msg']['reply-to']) == 'verkauf@example.org')
check('invitation: subject + username + link', 'Zugang' in m['subject'] and 'gasthaus.muster' in m['text'] and tok1 and (B + '/#zugang=' + tok1) in m['text'])
check('invitation: HTML escapes customer data', '<b>Muster</b>' not in m['html'] and 'Passwort festlegen' in m['html'])
check('SMTP login with configured account', smtp.logins and smtp.logins[-1][:2] == ('portal@example.org', True))
check('mail never contains SMTP password', SMTP_PW.encode() not in m['raw'])
code, r, raw = A.call('kunden', raw=True)
c1 = r['customers'][0]
check('pending invitation visible to admin', c1['login']['link']['p'] == 'invite' and c1['mailLast']['typ'] == 'invite' and c1['mailLast']['ok'] is True)
check('token never in API responses', tok1 not in raw and '"h":' not in raw)

# ---------- Einmal-Link ----------
K = Client('198.51.100.10')
check('wrong token rejected (410)', K.call('kunde_token_check', {'token': 'x' * 43})[0] == 410)
code, r = K.call('kunde_token_check', {'token': tok1})
check('token check names customer', code == 200 and r['purpose'] == 'invite' and r['username'] == 'gasthaus.muster', r)
check('weak password rejected, token stays valid', K.call('kunde_token_set', {'token': tok1, 'password': 'passwort123'})[0] == 422 and K.call('kunde_token_check', {'token': tok1})[0] == 200)
code, r = K.call('kunde_token_set', {'token': tok1, 'password': 'Eigenes-Kennwort-55'})
check('password set via link + logged in', code == 200 and r['kunde']['mustChange'] is False and K.call('offer&angebot=edeka')[0] == 200, r)
check('link works only once', Client('198.51.100.11').call('kunde_token_check', {'token': tok1})[0] == 410)
check('login with own password works', Client('198.51.100.12').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})[0] == 200)
check('customer cannot send mails', K.call('kunde_mail', {'id': K1, 'type': 'angebot'})[0] in (401, 403) and K.call('mail_status')[0] in (401, 403))

# ---------- Passwort zurücksetzen ----------
A.call('kunde_mail', {'id': K1, 'type': 'zugang'})
m = smtp.messages[-1]; tokA = link_of(m)
check('reset link for customer with password', 'neu festlegen' in m['subject'] and tokA, m['subject'])
check('old password still valid until reset is used', Client('198.51.100.13').call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})[0] == 200)
A.call('kunde_mail', {'id': K1, 'type': 'zugang'})
tokB = link_of(smtp.messages[-1])
check('new link replaces older one', Client('198.51.100.14').call('kunde_token_check', {'token': tokA})[0] == 410 and Client('198.51.100.14').call('kunde_token_check', {'token': tokB})[0] == 200)
K2 = Client('198.51.100.15'); K2.call('kunde_login', {'username': 'gasthaus.muster', 'password': 'Eigenes-Kennwort-55'})
code, r = Client('198.51.100.16').call('kunde_token_set', {'token': tokB, 'password': 'Neues-Kennwort-66'})
check('reset via link ends other sessions', code == 200 and K2.call('offer&angebot=edeka')[0] == 401 and K.call('offer&angebot=edeka')[0] == 401)
A.call('kunde_mail', {'id': K1, 'type': 'zugang'})
tokC = link_of(smtp.messages[-1])
code, r = A.call('kunden')
rev = r['rev']
A.call('kunde_save', {**base, 'id': K1, 'rev': rev, 'login': {'username': 'gasthaus.muster', 'password': 'Admin-Gesetzt-77', 'mustChange': True, 'active': True}})
check('admin setting a password invalidates the link', Client('198.51.100.17').call('kunde_token_check', {'token': tokC})[0] == 410)

# ---------- Angebotslink ----------
code, r = A.call('kunde_mail', {'id': K1, 'type': 'angebot', 'note': '<script>alert(1)</script> Roastbeef diese Woche'})
m = smtp.messages[-1]
check('offer link mail sent', code == 200 and r['typ'] == 'angebot')
check('offer mail: KW in subject, link per assigned offer', 'KW 43/2026' in m['subject'] and B + '/?angebot=edeka' in m['text'] and B + '/?angebot=bela' in m['text'] and B + '/?angebot=chefs' not in m['text'], m['subject'])
check('offer mail: no prices, note escaped', '€' not in m['text'] and '<script>' not in m['html'] and '&lt;script&gt;' in m['html'])
check('offer mail: unsubscribe note + username', 'abbestellen' in m['text'] and 'Vom Wochenangebot abmelden' in m['text'] and 'gasthaus.muster' in m['text'])

# ---------- Header-Injection, Signatur ----------
code, r = A.call('kunden')
A.call('kunde_save', {**base, 'id': K1, 'rev': r['rev'], 'ansprechpartner': 'Max\r\nBcc: boese@example.org', 'login': {'username': 'gasthaus.muster', 'password': '', 'active': True}})
code, r = A.call('mail_save', {'signature': 'Viele Grüße\nIhr Verkaufsteam\x07\nTel. 040 000'})
check('signature saved (control chars removed)', code == 200 and r['signature'] == 'Viele Grüße\nIhr Verkaufsteam\nTel. 040 000', r)
A.call('kunde_mail', {'id': K1, 'type': 'angebot'})
m = smtp.messages[-1]
headers = m['raw'].split(b'\r\n\r\n', 1)[0].decode()
check('no header injection via contact name', not re.search(r'^Bcc:', headers, re.M) and m['to'] == ['einkauf@example.org'])
check('signature in mail', 'Ihr Verkaufsteam' in m['text'] and 'Ihr Verkaufsteam' in m['html'])

# ---------- Wochenversand ----------
def mk(firma, nr, email, user, **kw):
    code, r = A.call('kunden')
    b = {**base, 'rev': r['rev'], 'firma': firma, 'nr': nr, 'email': email, 'ansprechpartner': '', 'login': {'username': user, 'password': 'Start-Kennwort-42', 'mustChange': False, 'active': True}, **kw}
    code, r = A.call('kunde_save', b)
    assert code == 200, r
    return r['customer']['id']
K_ok = mk('Hotel Seeblick', 'K-2', 'kueche@example.org', 'hotel.seeblick')
K_opt = mk('Ohne Werbung KG', 'K-3', 'nein@example.org', 'ohne.werbung', mailAngebot=False)
K_nomail = mk('Ohne Adresse', 'K-4', '', 'ohne.adresse')
K_bad = mk('Falsche Adresse', 'K-5', 'abgelehnt@example.org', 'falsche.adresse')
n0 = len(smtp.messages)
check('wrong week rejected (409)', A.call('kunden_rundmail', {'ids': [K_ok], 'week': 42, 'year': 2026})[0] == 409)
code, r = A.call('kunden_rundmail', {'ids': [K1, K_ok, K_opt, K_nomail, K_bad, 'gibts-nicht'], 'note': 'Schönes Wochenende!', 'week': 43, 'year': 2026})
byid = {x['id']: x for x in r.get('results', [])}
check('weekly mail: eligible customers sent', code == 200 and byid[K1]['ok'] and byid[K_ok]['ok'], r)
check('weekly mail: opted-out customer skipped', not byid[K_opt]['ok'] and 'nicht gewünscht' in byid[K_opt]['error'])
check('weekly mail: customer without email skipped', not byid[K_nomail]['ok'] and 'E-Mail' in byid[K_nomail]['error'])
check('weekly mail: rejected recipient reported, others unaffected', not byid[K_bad]['ok'] and 'abgelehnt' in byid[K_bad]['error'])
check('weekly mail: unknown id reported', not byid['gibts-nicht']['ok'])
sent = smtp.messages[n0:]
check('exactly two weekly mails delivered over the server', len(sent) == 2 and sorted(x['to'][0] for x in sent) == ['einkauf@example.org', 'kueche@example.org'], [x['to'] for x in sent])
check('one personal mail per customer (no shared recipients)', all(len(x['to']) == 1 for x in sent))
mk2 = next(x for x in sent if x['to'] == ['kueche@example.org'])
check('weekly mail content', 'Wochenangebot KW 43/2026' in mk2['subject'] and 'Schönes Wochenende!' in mk2['text'] and 'Guten Tag,' in mk2['text'] and 'hotel.seeblick' in mk2['text'])
code, r = A.call('kunden')
cs = {c['id']: c for c in r['customers']}
check('weekly send recorded per customer', cs[K_ok]['weekly']['week'] == 43 and cs[K1]['weekly']['week'] == 43 and 'weekly' not in cs[K_opt])
check('failed delivery recorded', cs[K_bad]['mailLast']['ok'] is False and 'weekly' not in cs[K_bad])
code, r = A.call('kunden_rundmail', {'ids': [K_ok] * 30, 'week': 43, 'year': 2026})
check('batch limited to 20 ids per request', code == 200 and len(r['results']) == 20)

# ---------- Abmelden vom Wochenangebot ----------
import urllib.request, urllib.error
abm = re.search(r'#abmelden=(k[a-f0-9]{12}\.[A-Za-z0-9_-]{32})', mk2['text'])
ABM = abm.group(1) if abm else ''
check('weekly mail has personal unsubscribe link (text + button)', ABM.startswith(K_ok + '.') and (B + '/#abmelden=' + ABM) in mk2['html'] and 'Vom Wochenangebot abmelden' in mk2['html'])
lu = str(mk2['msg']['list-unsubscribe'] or '')
check('one-click unsubscribe headers (RFC 8058)', ('/api/?action=abmelden1&t=' + ABM) in lu and str(mk2['msg']['list-unsubscribe-post']) == 'List-Unsubscribe=One-Click', lu)
check('invitation mail has no unsubscribe link', 'abmelden' not in smtp.messages[0]['text'].lower())
P = Client('198.51.100.60')
check('invalid unsubscribe code rejected', P.call('kunde_abmelden_info', {'token': 'k000000000000.' + 'x' * 32})[0] == 404)
check('tampered code rejected', P.call('kunde_abmelden', {'token': ABM[:-1] + ('A' if ABM[-1] != 'A' else 'B')})[0] == 404)
code, r = P.call('kunde_abmelden_info', {'token': ABM})
check('info: firma + masked address, still subscribed', code == 200 and r['firma'] == 'Hotel Seeblick' and r['email'] == 'k•••@example.org' and r['subscribed'] is True, r)
n0 = len(smtp.messages)
code, r = P.call('kunde_abmelden', {'token': ABM})
check('unsubscribe works without login', code == 200 and r['subscribed'] is False)
code, r = A.call('kunden'); cs = {c['id']: c for c in r['customers']}
check('customer flagged, email kept in master data', cs[K_ok]['mailAngebot'] is False and cs[K_ok]['abgemeldet']['via'] == 'link' and cs[K_ok]['email'] == 'kueche@example.org')
note = smtp.messages[-1] if len(smtp.messages) > n0 else None
check('we get notified (reply-to address)', note and note['to'] == ['verkauf@example.org'] and 'Abmeldung Wochenangebot: Hotel Seeblick' in note['subject'], note and note['subject'])
code, r = A.call('kunden_rundmail', {'ids': [K_ok], 'week': 43, 'year': 2026})
check('no more weekly mails', not r['results'][0]['ok'] and 'abgemeldet' in r['results'][0]['error'])
check('no single offer mails either', A.call('kunde_mail', {'id': K_ok, 'type': 'angebot'})[0] == 422)
check('password link still possible', A.call('kunde_mail', {'id': K_ok, 'type': 'zugang'})[0] == 200)
check('second unsubscribe: no duplicate notification', P.call('kunde_abmelden', {'token': ABM})[0] == 200 and not smtp.messages[-1]['subject'].startswith('Abmeldung'))
code, r = P.call('kunde_abmelden', {'token': ABM, 'wieder': True})
check('customer can re-subscribe via same link', code == 200 and r['subscribed'] is True and 'Wiederanmeldung' in smtp.messages[-1]['subject'])
def oneclick(method='POST', tok=ABM):
    req = urllib.request.Request(B + '/api/?action=abmelden1&t=' + tok, data=b'List-Unsubscribe=One-Click' if method == 'POST' else None, method=method,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-Forwarded-For': '198.51.100.61'})
    try: return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e: return e.code
check('one-click needs POST (link previews do nothing)', oneclick('GET') == 405)
check('one-click from mail program', oneclick() == 200)
code, r = A.call('kunden'); c_ok = next(c for c in r['customers'] if c['id'] == K_ok)
check('one-click recorded', c_ok['mailAngebot'] is False and c_ok['abgemeldet']['via'] == '1klick')
code, r = A.call('kunde_save', {**{k: c_ok[k] for k in ['nr', 'firma', 'ansprechpartner', 'strasse', 'plz', 'ort', 'land', 'email', 'telefon', 'notiz', 'angebote', 'active']}, 'id': K_ok, 'rev': r['rev'], 'mailAngebot': True, 'login': {'username': 'hotel.seeblick', 'password': '', 'active': True}})
check('admin can switch it back on (clears flag)', code == 200 and r['customer']['mailAngebot'] is True and 'abgemeldet' not in r['customer'])
code, r = A.call('log')
check('audit: unsubscribe events', sum(1 for e in r['entries'] if e['a'] == 'kunde_abmeldung') >= 3)

# ---------- Testmail, Rechte, Protokoll ----------
check('test mail needs valid address', A.call('mail_test', {'to': 'kein'})[0] == 422)
n0 = len(smtp.messages)
check('test mail sent', A.call('mail_test', {'to': 'ich@example.org'})[0] == 200 and len(smtp.messages) == n0 + 1 and smtp.messages[-1]['to'] == ['ich@example.org'])
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
for act, body in [('mail_status', None), ('mail_test', {'to': 'x@example.org'}), ('kunde_mail', {'id': K1, 'type': 'angebot'}), ('kunden_rundmail', {'ids': [K1], 'week': 43, 'year': 2026}), ('mail_save', {'signature': 'x'}), ('kunden_mail_vorschau', {'type': 'woche'})]:
    check(f'editor cannot use {act}', E.call(act, body)[0] == 403)
    check(f'anonymous cannot use {act}', Client('198.51.100.4').call(act, body)[0] == 401)
code, st, raw = A.call('mail_status', raw=True)
check('mail log lists deliveries incl. errors', any(x['typ'] == 'test' for x in st['log']) and any(not x['ok'] for x in st['log']))
code, r, raw = A.call('log', raw=True)
check('audit: mails logged', sum(1 for e in r['entries'] if e['a'] == 'mail') >= 5 and any('Wochenangebot KW 43/2026' in e['s'] for e in r['entries']))
check('audit: no tokens or passwords', all(t not in raw for t in [tok1, tokA, tokB, tokC, SMTP_PW, 'Eigenes-Kennwort-55']))
code, r = A.call('kunden_mail_vorschau', {'id': K_ok, 'type': 'woche', 'note': 'Hallo'})
check('preview renders without sending', code == 200 and 'Hallo' in r['html'] and r['to'] == 'kueche@example.org' and len(smtp.messages) == n0 + 1)

# ---------- Mailserver nicht erreichbar ----------
smtp.close(); time.sleep(0.2)
code, r = A.call('kunde_mail', {'id': K1, 'type': 'zugang'})
check('server down: clear error', code == 502 and 'Verbindung' in r.get('error', ''), r)
code, r = A.call('kunden')
c1 = next(c for c in r['customers'] if c['id'] == K1)
check('undelivered link is not left valid', c1['login']['link'] is None and c1['mailLast']['ok'] is False)
smtp = TestSmtp(SMTP_PORT, password=SMTP_PW)

# ---------- Postfach im Eingabebereich hinterlegen (Vorrang vor .env) ----------
import os
UDATA = os.environ['UDATA']
KONTO_PW = 'Konto-Passwort-9'
smtp2 = TestSmtp(SMTP_PORT2, user='konto@example.org', password=KONTO_PW)
konto = {'host': '127.0.0.1', 'port': SMTP_PORT2, 'secure': 'none', 'user': 'konto@example.org', 'password': KONTO_PW, 'from': 'konto@example.org', 'fromName': 'STAFL Versand', 'replyTo': ''}
check('editor cannot change mail account', E.call('mail_konto_save', konto)[0] == 403)
check('unencrypted only to local server', A.call('mail_konto_save', {**konto, 'host': 'smtp.example.org'})[0] == 422)
check('invalid sender rejected', A.call('mail_konto_save', {**konto, 'from': 'kein'})[0] == 422)
check('invalid host rejected', A.call('mail_konto_save', {**konto, 'host': 'smtp example.org'})[0] == 422)
code, r = A.call('mail_konto_save', konto)
check('account saved, connection + login verified', code == 200 and r['connection']['ok'] is True and smtp2.logins[-1] == ('konto@example.org', True, False), r)
code, st, raw = A.call('mail_status', raw=True)
check('saved account takes precedence over .env', st['smtp']['source'] == 'admin' and st['smtp']['from'] == 'konto@example.org' and st['account']['password'] is True and st['envConfigured'] is True)
check('password never returned', KONTO_PW not in raw)
stored = storage_raw('mailkonto')
check('password stored encrypted only', KONTO_PW not in stored and '"passEnc": "v1:' in stored.replace('":"', '": "'))
check('separate key file exists', os.path.exists(os.path.join(UDATA, 'mail-schluessel.php')))
n0 = len(smtp2.messages)
check('mails go via saved account', A.call('mail_test', {'to': 'ich@example.org'})[0] == 200 and len(smtp2.messages) == n0 + 1 and 'STAFL Versand' in str(smtp2.messages[-1]['msg']['from']))
code, r = A.call('mail_konto_save', {**konto, 'port': SMTP_PORT, 'password': ''})
check('changed server requires password again (never reused elsewhere)', code == 422 and 'Passwort' in r.get('error', ''))
code, r = A.call('mail_konto_save', {**konto, 'password': '', 'fromName': 'STAFL Verkauf'})
check('same server: stored password kept', code == 200 and r['connection']['ok'] is True)
code, r = A.call('mail_konto_save', {**konto, 'password': 'Falsches-Passwort-1'})
check('wrong password: saved, but connection check reports login failure', code == 200 and r['connection']['ok'] is False and 'Anmeldung' in r['connection']['error'], r)
A.call('mail_konto_save', konto)
os.remove(os.path.join(UDATA, 'mail-schluessel.php'))
code, st = A.call('mail_status')
check('missing key detected (e.g. after restore)', st['smtp']['passError'] is True)
code, r = A.call('mail_test', {'to': 'ich@example.org'})
check('sending with unreadable password: clear message', code == 502 and 'neu eingeben' in r.get('error', ''), r)
code, r = A.call('mail_konto_save', konto)
check('re-entering password fixes it', code == 200 and r['connection']['ok'] and A.call('mail_status')[1]['smtp']['passError'] is False)
code, r, raw = A.call('log', raw=True)
check('audit: account change logged without password', any(e['a'] == 'mail' and 'Postfach' in e['s'] for e in r['entries']) and KONTO_PW not in raw)
check('remove account', A.call('mail_konto_save', {'remove': True})[0] == 200 and A.call('mail_status')[1]['smtp']['source'] == 'env')
n0 = len(smtp.messages)
check('after removal .env account is used again', A.call('mail_test', {'to': 'ich@example.org'})[0] == 200 and len(smtp.messages) == n0 + 1)
smtp2.close()

# ---------- Oberfläche ----------
with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-kunden'); a.wait_for_selector('#view-kunden tr[data-kid]')
    check('toolbar: mail configured, send button', 'nicht eingerichtet' not in a.inner_text('#k-mailcfg') and a.is_visible('#k-rund'))
    check('list shows weekly status', 'KW 43 gesendet' in a.locator('#view-kunden tr[data-kid]:has-text("Hotel Seeblick")').inner_text())
    # Neukunde mit Einladung
    a.click('#k-add'); a.wait_for_selector('#dlg-kunde[open]')
    check('new customer: invitation preselected, no password field', a.is_checked('#kunde-body [name=pwmode][value=invite]') and a.locator('#kunde-body [name=password]').is_hidden())
    a.fill('#kunde-body [name=firma]', 'Kantine Nord GmbH'); a.fill('#kunde-body [name=ansprechpartner]', 'Herr Koch'); a.fill('#kunde-body [name=email]', 'kantine@example.org')
    a.check('#kunde-body [name=angebot][value=handelshof-efs]')
    n0 = len(smtp.messages)
    a.click('#kunde-body [type=submit]'); a.wait_for_function("!document.querySelector('#dlg-kunde').open", timeout=8000)
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Einladung')", timeout=8000)
    check('invitation sent on create', len(smtp.messages) == n0 + 1 and smtp.messages[-1]['to'] == ['kantine@example.org'], a.inner_text('#toast'))
    tok = link_of(smtp.messages[-1]); inv_msg = smtp.messages[-1]
    a.wait_for_selector('#view-kunden tr[data-kid]:has-text("Kantine Nord")')
    check('list shows open invitation', 'Einladung offen' in a.locator('#view-kunden tr[data-kid]:has-text("Kantine Nord")').inner_text())
    # Kunde öffnet den Link
    cctx = br.new_context(viewport={'width': 1280, 'height': 900}); c = cctx.new_page(); cerr = []
    c.on('pageerror', lambda e: cerr.append(str(e)))
    c.goto(B + '/#zugang=' + tok); c.wait_for_selector('#dlg-kunde-link[open]')
    check('link page: welcome dialog, token removed from address', 'Willkommen' in c.inner_text('#kk-title') and '#zugang' not in c.url and 'kantine.nord' in c.inner_text('#kk-intro'), c.url)
    c.screenshot(path=SH + '/mail-link.png')
    c.keyboard.press('Escape'); c.wait_for_timeout(150)
    check('link dialog not dismissable', c.locator('#dlg-kunde-link[open]').count() == 1)
    c.fill('#kk-form [name=password]', 'Kantine-Eigen-2026'); c.fill('#kk-form [name=password2]', 'Kantine-Eigen-2027'); c.click('#kk-form [type=submit]')
    check('mismatch shown', 'stimmen nicht' in c.inner_text('#kk-err'))
    c.fill('#kk-form [name=password2]', 'Kantine-Eigen-2026'); c.click('#kk-form [type=submit]')
    c.wait_for_url(re.compile(r'angebot=handelshof-efs'), timeout=8000); c.wait_for_selector('tr.row')
    check('after setting password: own offer opens, logged in', 'Kantine Nord' in c.inner_text('#preview-banner'))
    c.goto(B + '/#abmelden=' + ABM); c.wait_for_selector('.k-abm [data-abm=ab]')
    check('unsubscribe page asks first, code removed from address', 'abbestellen' in c.inner_text('#list') and 'Hotel Seeblick' in c.inner_text('#list') and '#abmelden' not in c.url)
    c.click('.k-abm [data-abm=ab]'); c.wait_for_selector('.k-abm [data-abm=wieder]')
    check('confirmation shown to customer', 'Sie sind abgemeldet' in c.inner_text('#list'))
    c.screenshot(path=SH + '/mail-abgemeldet.png')
    check('admin sees unsubscribed customer', A.call('kunden')[1]['customers'] and next(x for x in A.call('kunden')[1]['customers'] if x['id'] == K_ok)['mailAngebot'] is False)
    c.click('.k-abm [data-abm=wieder]'); c.wait_for_selector('.k-abm:has-text("Wieder angemeldet")')
    check('re-subscribe from confirmation page', next(x for x in A.call('kunden')[1]['customers'] if x['id'] == K_ok)['mailAngebot'] is True)
    c.goto(B + '/?neu=1#zugang=' + tok); c.wait_for_timeout(800)
    check('used link shows clear message', 'abgelaufen' in c.inner_text('#list'))
    # Wochenversand im Dialog
    a.click('#k-rund'); a.wait_for_selector('#dlg-rund[open]')
    t = a.inner_text('#rund-body')
    check('send dialog: title with KW, skipped customers explained', 'KW 43/2026' in t and 'nicht berücksichtigt' in t)
    check('already-sent customers unchecked by default', not a.is_checked('#rund-body tr:has-text("Hotel Seeblick") [data-rsel]') and 'bereits gesendet' in a.inner_text('#rund-body tr:has-text("Hotel Seeblick")'))
    check('new customer preselected', a.is_checked('#rund-body tr:has-text("Kantine Nord") [data-rsel]'))
    a.fill('#rd-note', 'Diese Woche: Roastbeef im Angebot.')
    a.click('#rund-body [data-rd=prev]'); a.wait_for_selector('#rund-body .k-prevwrap:not([hidden])')
    fr = a.frame_locator('#rd-prev')
    check('preview shows mail with note', 'Roastbeef im Angebot' in fr.locator('body').inner_text())
    a.screenshot(path=SH + '/mail-versand.png')
    n0 = len(smtp.messages)
    a.click('#rund-body [data-rd=send]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_selector('#rund-body tr:has-text("Kantine Nord") .k-res .st-ok', timeout=10000)
    check('sent from dialog', len(smtp.messages) == n0 + 1 and smtp.messages[-1]['to'] == ['kantine@example.org'] and 'Roastbeef im Angebot' in smtp.messages[-1]['text'])
    a.wait_for_selector('#rund-body tr:has-text("Falsche Adresse") .k-res .st-err', timeout=10000)
    check('failed recipient shows error and stays selected for retry', 'abgelehnt' in a.inner_text('#rund-body tr:has-text("Falsche Adresse") .k-res') and a.is_checked('#rund-body tr:has-text("Falsche Adresse") [data-rsel]') and not a.is_checked('#rund-body tr:has-text("Kantine Nord") [data-rsel]'))
    check('summary toast reports failures', 'nicht zugestellt' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.click('#rund-body [data-close]'); a.wait_for_timeout(200)
    # Einstellungen, Testmail
    a.click('#k-mailcfg'); a.wait_for_selector('#view-mail #ml-form')
    check('E-Mail button opens settings view', a.get_attribute('#vt-mail', 'aria-selected') == 'true' and a.is_visible('#vt-mail'))
    t = a.inner_text('#view-mail')
    check('settings: configured from .env, password never shown', 'eingerichtet' in t and '.env' in t and SMTP_PW not in a.content())
    a.fill('#ml-to', 'test@example.org'); a.click('#view-mail [data-ml=test]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Testmail')", timeout=8000)
    check('test mail from settings', smtp.messages[-1]['to'] == ['test@example.org'])
    a.click('#view-mail [data-ml=preset][data-p=hostinger]')
    check('preset fills Hostinger server data', a.input_value('#ml-form [name=host]') == 'smtp.hostinger.com' and a.input_value('#ml-form [name=port]') == '465' and a.input_value('#ml-form [name=secure]') == 'ssl')
    a.fill('#ml-form [name=user]', 'versand@example.org'); a.fill('#ml-form [name=from]', 'versand@example.org')
    a.screenshot(path=SH + '/mail-einstellungen.png', full_page=True)
    a.click('#ml-form [type=submit]'); a.wait_for_function("document.querySelector('#ml-err').textContent.length > 0", timeout=8000)
    check('new server without password: clear message, nothing sent', 'Passwort' in a.inner_text('#ml-err') and A.call('mail_status')[1]['account'] is None, a.inner_text('#ml-err'))
    a.click('#vt-kunden'); a.wait_for_selector('#view-kunden tr[data-kid]')
    # Angebotslink einzeln
    a.locator('#view-kunden tr[data-kid]:has-text("Kantine Nord")').click(); a.wait_for_selector('#dlg-kunde[open]')
    check('dialog offers reset link for customer with password', 'Passwort-Zurücksetzen' in a.inner_text('#kunde-body [data-kact=m-zugang]'))
    n0 = len(smtp.messages)
    a.click('#kunde-body [data-kact=m-angebot]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("document.querySelector('#toast').textContent.includes('Angebotslink')", timeout=8000)
    check('single offer link sent', len(smtp.messages) == n0 + 1 and B + '/?angebot=handelshof-efs' in smtp.messages[-1]['text'])
    for name, msg in (('mail-wochenangebot', mk2), ('mail-einladung', inv_msg)):
        pg = br.new_page(viewport={'width': 700, 'height': 900}); pg.set_content(msg['html']); pg.screenshot(path=SH + f'/{name}.png', full_page=True); pg.close()
    check('no JS errors (admin)', not errs, errs[:3])
    check('no JS errors (customer)', not cerr, cerr[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
