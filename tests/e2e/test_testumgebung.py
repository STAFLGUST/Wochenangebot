"""Testumgebung (WA_TESTUMGEBUNG=1): Kennzeichen, E-Mails nur ins Testpostfach (nie an einen Mailserver)."""
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client
from umgebung import BASE, SH, shot

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
check('status shows test environment', A.call('status')[1].get('testumgebung') is True)
check('customer status shows test environment', Client('198.51.100.9').call('kunde_status')[1].get('testumgebung') is True)
ms = A.call('mail_status')[1]
check('mail ready without real mail server (test mailbox)', ms['configured'] is True and ms['smtp']['source'] == 'test' and ms['testumgebung'] is True, ms.get('smtp'))
rev = A.call('kunden')[1]['rev']
code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Testkunde GmbH', 'nr': 'T-1', 'email': 'echt@example.org', 'active': True, 'angebote': ['std'],
                                'login': {'username': 'testkunde', 'password': 'Kunden-Kennwort-5', 'mustChange': False, 'active': True}})
KID = r['customer']['id']
code, r = A.call('kunde_mail', {'id': KID, 'type': 'angebot'})
check('mail to customer "sent" (into test mailbox)', code == 200, r)
code, tp = A.call('testpostfach')
check('test mailbox lists the mail', code == 200 and tp['mails'] and tp['mails'][0]['to'] == 'echt@example.org', tp)
code, one = A.call('testpostfach&i=0')
check('test mailbox shows the content', code == 200 and 'testkunde' in one['mail']['html'] and one['mail']['subject'])
check('mail log records it', any(x['to'] == 'echt@example.org' and x['ok'] for x in A.call('mail_status')[1]['log']))
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('test mailbox only for administrators', E.call('testpostfach')[0] == 403 and Client('198.51.100.8').call('testpostfach')[0] == 401)
# Bestellwunsch: geht ebenfalls nur ins Testpostfach
check('order settings', A.call('bestell_settings_save', {'enabled': True, 'to': 'bestellung@example.org', 'copy': True})[0] == 200)
K = Client('198.51.100.20'); K.call('kunde_login', {'username': 'testkunde', 'password': 'Kunden-Kennwort-5'})
pub = A.call('draft')[1]['published']
code, r = K.call('kunde_bestellung', {'angebot': 'std', 'publishedAt': pub.get('publishedAt', ''), 'positions': [{'id': pub['items'][0]['id'], 'qty': 3}]})
check('order accepted, mails into test mailbox', code == 200 and r.get('delivery') == 'gesendet', r)
to = [m['to'] for m in A.call('testpostfach')[1]['mails']]
check('order mail and customer copy in test mailbox', 'bestellung@example.org' in to and to.count('echt@example.org') == 2, to)

with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    a = br.new_page(viewport={'width': 1300, 'height': 900}); a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    check('admin page marked as test environment', a.evaluate("document.body.classList.contains('is-test')"))
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-mail'); a.wait_for_selector('#ml-tp-list tr[data-tp]')
    check('mail view shows test mailbox', 'Testpostfach' in a.inner_text('#view-mail') and a.locator('#ml-tp-list tr[data-tp]').count() >= 3)
    a.locator('#ml-tp-list tr[data-tp]').first.click(); a.wait_for_selector('#ml-tp-prev:not([hidden])')
    check('test mail preview opens', a.locator('#ml-tp-prev').is_visible())
    shot(a, SH + '/testumgebung-postfach.png')
    pg = br.new_page(viewport={'width': 1300, 'height': 900}); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(BASE + '/'); pg.wait_for_selector('tr.row')
    pg.wait_for_function("document.body.classList.contains('is-test')", timeout=5000)
    badge = pg.evaluate("getComputedStyle(document.body, '::after').content")
    check('public page shows test badge', 'TESTUMGEBUNG' in badge, badge)
    shot(pg, SH + '/testumgebung-seite.png')
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
