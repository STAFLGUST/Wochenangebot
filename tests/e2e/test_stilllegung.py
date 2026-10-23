"""Alter Eingabebereich stillgelegt (WA_EIGENE_ANMELDUNG=aus, lib/oidc.php): auf dem Host ohne zentrale Anmeldung
(angebot-stafl.de) gibt es keine Mitarbeiteranmeldung und keine Mitarbeiteraktionen mehr; die Kundenseite und alle
Kundenfunktionen bleiben unverändert. Den Normalbetrieb ohne die Einstellung prüfen alle übrigen Gruppen."""
import sys

from kunden_hilfe import Client
from playwright.sync_api import sync_playwright
from umgebung import BASE, SH

PW = 'Sicheres-Passwort-1'
ZIEL = 'https://angebot.dashboard-stafl.de/admin/'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


M = Client('198.51.100.40')
code, r = M.call('status')
check('Status bleibt erreichbar (Healthcheck), nicht angemeldet, mit neuer Adresse', code == 200 and r.get('ok') is True and r.get('loggedIn') is False
      and r.get('umgezogen') == ZIEL, r)
for a, daten in (('login', {'username': 'admin', 'password': PW}), ('login_2fa', {'code': '123456'}), ('setup', {'username': 'x', 'password': PW}),
                 ('passkey_login_begin', {}), ('change_password', {'password': PW})):
    code, r = M.call(a, daten)
    check(f'Mitarbeiteranmeldung {a}: 410 „umgezogen“ mit Ziel', code == 410 and r.get('code') == 'umgezogen' and r.get('ziel') == ZIEL
          and 'umgezogen' in r.get('error', ''), (code, r))
for a in ('draft', 'users', 'security_status', 'module_status', 'einkauf_list'):
    code, r = M.call(a)
    check(f'Mitarbeiteraktion {a}: 410, keine Daten', code == 410 and r.get('code') == 'umgezogen' and set(r) <= {'ok', 'code', 'ziel', 'error'}, (code, sorted(r)))
code, r = M.call('draft_save', {'week': 1})
check('Schreibende Mitarbeiteraktion: 410 (vor Rechte- und Herkunftsprüfung der Aktion selbst)', code == 410, (code, r))
check('Abmelden bleibt möglich (alte Sitzung beenden)', M.call('logout', {})[0] == 200)

K = Client('198.51.100.41')
code, r = K.call('offer')
check('Kundenseite: öffentliches Wochenangebot unverändert', code == 200 and r.get('ok') is not False and 'umgezogen' not in r, (code, sorted(r)[:8]))
check('Kundenstatus unverändert', K.call('kunde_status')[0] == 200)
code, r = K.call('kunde_login', {'username': 'gibt-es-nicht', 'password': 'falsch-falsch'})
check('Kundenanmeldung unverändert (falsche Daten: abgelehnt, nicht „umgezogen“)', code in (401, 403, 422) and r.get('code') != 'umgezogen', (code, r))

with sync_playwright() as p:
    br = p.chromium.launch(); fehler = []
    for w in (1280, 390):
        pg = br.new_page(viewport={'width': w, 'height': 844}, is_mobile=w < 500)
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.route('https://angebot.dashboard-stafl.de/**', lambda route: route.fulfill(status=200, content_type='text/html', body='<p id="neu">neu</p>'))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#umgezogen-weiter')
        check(f'{w}px alter Eingabebereich: Hinweis „umgezogen“ statt Anmeldemaske, Verweis auf die neue Adresse',
              'umgezogen' in pg.inner_text('h1') and pg.get_attribute('#umgezogen-weiter', 'href') == ZIEL and pg.locator('#au-user').count() == 0
              and pg.evaluate('document.documentElement.scrollWidth') <= w)
        pg.screenshot(path=f"{SH}/stilllegung-{w}.png")
        pg.wait_for_url(ZIEL, timeout=10000)
        check(f'{w}px … danach automatisch weitergeleitet', pg.url == ZIEL, pg.url)
        pg.close()
    k = br.new_page(); k.on('pageerror', lambda e: fehler.append(str(e)))
    k.goto(BASE + '/'); k.wait_for_selector('#topbar')
    check('Kundenseite lädt normal', k.locator('#topbar').is_visible())
    check('keine JavaScript-Fehler', not fehler, fehler)
    br.close()

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
