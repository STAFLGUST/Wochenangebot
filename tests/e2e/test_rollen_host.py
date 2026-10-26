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
check('Bestand-Host ohne Modulzugang Angebot: kein Entwurf und keine Kundenpreise', L.call('draft')[0] == 403 and L.call('versions')[0] == 403
      and L.call('offer&angebot=' + A.call('offers')[1]['offers'][0]['id'])[0] == 403 and L.call('offers')[0] == 403)

# Wartung des Bestands (GR-107): Der Bestand-Host hat keine eigenen Aktionen (er nutzt die des gemeinsamen
# Eingabebereichs) – die Wartung gilt trotzdem für alles, was über ihn läuft. Administratoren arbeiten weiter.
code, r = A.call('modul_wartung_save', {'bereich': 'bestand.intern', 'active': True, 'grund': 'Inventur', 'message': 'Bestand gleich zurück.'})
check('Bestand in Wartung gesetzt', code == 200 and r['aktiv'] is True, (code, r))
code, r = L.call('stock')
check('Wartung Bestand: Aktion des Eingabebereichs auf dem Bestand-Host 503', code == 503 and r.get('bereich') == 'bestand.intern' and r.get('error') == 'Bestand gleich zurück.', (code, r))
check('… auch schreibend (Bestandsimport)', L.call('stock_import', {'date': '2026-10-16', 'articles': []})[0] == 503)
check('… Status bleibt erreichbar', L.call('status')[0] == 200)
check('… Administrator arbeitet weiter', A.call('stock')[0] == 200)
check('Wartung Bestand beendet: wieder offen', A.call('modul_wartung_save', {'bereich': 'bestand.intern', 'active': False, 'grund': 'fertig'})[0] == 200 and L.call('stock')[0] == 200)
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
    # Bestand ohne Modulzugang Angebot: Oberfläche startet ohne Entwurf (kein Abruf, keine Fehler)
    for breite in (1280, 390):
        pg = br.new_page(viewport={'width': breite, 'height': 800}, is_mobile=breite < 500); pg.on('pageerror', lambda e: fehler.append(str(e)))
        abrufe = []
        pg.on('request', lambda q: abrufe.append(q.url))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'lars'); pg.fill('#pw1', 'Lager-Zugang-551'); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.wait_for_load_state('networkidle')
        pg.click('#vt-stock'); pg.wait_for_selector('#view-stock:not([hidden])')
        pg.wait_for_function("document.querySelector('#view-stock').textContent.trim().length > 0")
        check(f'UI {breite}: ohne Modulzugang Angebot – Bestandsliste da, kein Entwurf abgerufen', not [u for u in abrufe if 'action=draft' in u or 'action=versions' in u],
              [u for u in abrufe if 'action=' in u][:8])
        pg.screenshot(path=SH + f'/rollen-bestand-ohne-angebot-{breite}.png')
        pg.close()
    check('keine Seitenfehler', not fehler, fehler[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
