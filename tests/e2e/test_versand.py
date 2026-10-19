"""Wochenangebot an Kunden senden: Knopf „An Kunden senden“ im Eingabebereich (an jedem Tag) und Hinweis direkt
nach dem Veröffentlichen; nur für berechtigte Nutzer. Läuft gegen den Test-Mailserver."""
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
rev = A.call('kunden')[1]['rev']
code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Kantine Nord', 'nr': 'K-1', 'email': 'kantine@example.org', 'active': True, 'angebote': ['std'],
                                'login': {'username': 'kantine.nord', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
check('customer created', code == 200, r)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def login(user, password):
        pg = br.new_page(viewport={'width': 1440, 'height': 950}); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return pg

    e = login('erika', 'Editor-Zugang-77')
    check('editor: no send button', not e.is_visible('#btn-send'))
    e.close()
    a = login('admin', PW)
    check('admin: send button in the top bar', a.is_visible('#btn-send') and 'An Kunden senden' in a.inner_text('#btn-send'))
    check('no hint before publishing', a.locator('#send-hint').is_hidden())
    a.click('#btn-send'); a.wait_for_selector('#dlg-rund[open]')
    check('top button opens the send dialog for the published week', 'KW 43/2026' in a.inner_text('#rund-body') and a.is_checked('#rund-body tr:has-text("Kantine Nord") [data-rsel]'))
    a.click('#rund-body [data-close]'); a.wait_for_selector('#dlg-rund', state='hidden')
    # neue Woche veröffentlichen (z. B. am Donnerstag für die nächste Woche)
    a.fill('#m-week', '44'); a.press('#m-week', 'Tab'); a.wait_for_timeout(300)
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]'); a.click('[data-ia=publish]')
    a.wait_for_selector('#send-hint:not([hidden])', timeout=15000)
    check('after publishing: hint offers sending', 'KW 44/2026 ist online' in a.inner_text('#send-hint'))
    a.screenshot(path=SH + '/versand-hinweis.png')
    a.click('#send-hint [data-send=open]'); a.wait_for_selector('#dlg-rund[open]')
    check('hint opens send dialog for the new week, hint closes', 'KW 44/2026' in a.inner_text('#rund-body') and a.locator('#send-hint').is_hidden())
    n0 = len(smtp.messages)
    a.click('#rund-body [data-rd=send]'); a.wait_for_selector('#dlg-confirm[open]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_selector('#rund-body tr:has-text("Kantine Nord") .k-res .st-ok', timeout=10000)
    check('mail sent to the customer', until(lambda: len(smtp.messages) == n0 + 1, 5) and smtp.messages[-1]['to'] == ['kantine@example.org'] and 'KW 44' in smtp.messages[-1]['subject'], [m['subject'] for m in smtp.messages[-1:]])
    a.click('#rund-body [data-close]'); a.wait_for_selector('#dlg-rund', state='hidden')
    a.set_viewport_size({'width': 390, 'height': 844})
    check('mobile: send button still reachable', a.is_visible('#btn-send'))
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
