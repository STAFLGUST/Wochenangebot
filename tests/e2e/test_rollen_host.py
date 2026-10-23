"""Modulzugang je Host: der Testserver meldet sich wie bestand.dashboard-stafl.de (WA_OBERFLAECHE=bestand.intern).
Ohne „bestand.zugang“ laufen dort keine Aktionen (auch nicht die des gemeinsamen Eingabebereichs, die andere Hosts
dürfen) – außer Status, Abmelden und Funktionen des Plattformkerns. Die Seite zeigt „Kein Zugang“ mit Rückweg.
Gegenstück ohne Host: Gruppe „rollen“."""
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
check('Administrator: Host frei', A.call('status')[1]['user']['modulzugang'] is True and A.call('stock')[0] == 200)
code, r = A.call('rolle_save', {'name': 'Lager', 'rechte': ['bestand.zugang', 'bestand.sehen']})
LAGER = r['id']
editor = next(x for x in r['rollen'] if x['id'] == 'editor')['rechte']
check('Bearbeiter ohne Bestandszugang', A.call('rolle_save', {'id': 'editor', 'name': 'Bearbeiter', 'rechte': [k for k in editor if k != 'bestand.zugang']})[0] == 200)
for name, user, rollen, pw in [('Lars Lager', 'lars', [LAGER], 'Lager-Zugang-551'), ('Erika Editor', 'erika', ['editor'], 'Editor-Zugang-77')]:
    check(f'{user} angelegt', A.call('user_save', {'id': '', 'name': name, 'username': user, 'rollen': rollen, 'active': True, 'password': pw, 'mustChange': False})[0] == 200)

L, E = Client('198.51.100.31'), Client('198.51.100.32')
L.call('login', {'username': 'lars', 'password': 'Lager-Zugang-551'}); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
st = E.call('status')[1]['user']
check('Status nennt fehlenden Zugang für diesen Host', st['modulzugang'] is False and st['modulName'] == 'Bestand' and 'bestand.sehen' in st['perms'], st)
code, r = E.call('stock')
check('Ohne Modulzugang: Bestand gesperrt, obwohl das Einzelrecht da ist', code == 403 and r.get('code') == 'kein_modulzugang' and r.get('name') == 'Bestand', r)
check('Gesperrt auch Aktionen des gemeinsamen Eingabebereichs', E.call('history_list')[1].get('code') == 'kein_modulzugang')
check('Schreibende Aktionen ebenso', E.call('stock_import', {'date': '2026-10-16', 'articles': []})[1].get('code') == 'kein_modulzugang')
check('Plattformkern bleibt erreichbar (Modulübersicht)', E.call('module_status')[0] == 200)
check('Mit Modulzugang: Bestand offen', L.call('status')[1]['user']['modulzugang'] is True and L.call('stock')[0] == 200)
check('Mit Modulzugang, ohne Einzelrecht: weiter gesperrt (Recht)', L.call('history_list')[0] == 403 and L.call('history_list')[1].get('code') != 'kein_modulzugang')
check('Abmelden geht', E.call('logout', {})[0] == 200)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    fehler = []
    for breite, datei in [(1280, 'rollen-kein-zugang.png'), (390, 'rollen-kein-zugang-390.png')]:
        pg = br.new_page(viewport={'width': breite, 'height': 800}, is_mobile=breite < 500); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'erika'); pg.fill('#pw1', 'Editor-Zugang-77'); pg.click('#auth-submit')
        pg.wait_for_selector('#kein-zugang')
        check(f'UI {breite}: Hinweis „Kein Zugang zu Bestand“', 'Kein Zugang zu „Bestand“' in pg.inner_text('#kein-zugang'))
        check(f'UI {breite}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth') <= breite)
        pg.screenshot(path=SH + '/' + datei)
        pg.close()
    check('keine Seitenfehler', not fehler, fehler[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
