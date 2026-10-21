"""Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6): Kacheln aus dem Modulregister, Status, Wartung, Abmeldung.

Das Dashboard liegt noch außerhalb der Dokumentwurzel (wird nicht produktiv ausgeliefert); der Testlauf blendet es nur für
diese Gruppe unter /dashboard/ ein. Die Kachel ist nur Anzeige – die Sperre setzt der Server durch (GR-102, GR-103).
"""
import json
import os
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
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
REIHE = ['angebot', 'bestand', 'crm', 'rewe', 'qs', 'einkauf', 'import', 'verwaltung']
fehler = []


def anmelden(br, user, pw, ip, breite=1280, dunkel=False):
    ctx = br.new_context(viewport={'width': breite, 'height': 900}, color_scheme='dark' if dunkel else 'light',
                         extra_http_headers={'X-Forwarded-For': ip})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
    pg.wait_for_selector('#screen-auth', state='hidden')
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    return ctx, pg


def kacheln(pg):
    return pg.eval_on_selector_all('#db-grid .db-tile', '''els => els.map(e => ({id: e.dataset.modul, tag: e.tagName, href: e.getAttribute('href'),
        name: e.querySelector('.db-name').textContent, badge: e.querySelector('.db-badge').textContent,
        hint: (e.querySelector('.db-hint') || {}).textContent || '', bilder: e.querySelectorAll('.db-hint img').length}))''')


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ── Ohne Anmeldung: Hinweis auf die Anmeldung, keine Kacheln ──
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis sichtbar, Kachelbereich verborgen', pg.is_hidden('#db-bereich') and pg.is_hidden('#db-logout'))
    check('Anmeldehinweis führt zur Mitarbeiter-Anmeldung', (pg.get_attribute('#db-login a', 'href') or '').endswith('/admin/'), pg.get_attribute('#db-login a', 'href'))
    check('keine Kacheln ohne Anmeldung', pg.locator('#db-grid .db-tile').count() == 0)
    ctx.close()

    # ── Administrator: acht Kacheln aus dem Register ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.41')
    k = kacheln(pg)
    check('acht Kacheln in der Reihenfolge des Modulregisters', [x['id'] for x in k] == REIHE, [x['id'] for x in k])
    check('Kachelnamen aus dem Register', [x['name'] for x in k][:2] == ['Angebot', 'Bestand'], [x['name'] for x in k])
    ang = k[0]
    check('Angebot: verfügbar, als Verweis auf die Mitarbeiter-Eingabe (Testserver: gleicher Host)', ang['tag'] == 'A' and ang['href'] == '/admin/' and ang['badge'] == 'Verfügbar', ang)
    gesperrt = [x for x in k[1:] if x['tag'] != 'DIV' or x['href']]
    check('alle anderen Kacheln ohne Verweis (nicht freigegeben)', not gesperrt, gesperrt)
    check('nicht freigegebene Module zeigen ihren Entwicklungsstand', all(x['badge'] in ('Geplant', 'In Entwicklung', 'In Prüfung', 'In Vorbereitung') for x in k[1:]), [x['badge'] for x in k])
    check('gesperrte Kacheln als deaktiviert gekennzeichnet', pg.locator('#db-grid .db-tile.off[aria-disabled="true"]').count() == 7)
    check('Zähler: 1 von 8 Anwendungen', '1 von 8' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    check('Name des angemeldeten Nutzers im Kopf', 'Angemeldet als' in pg.text_content('#db-user'))
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280.png'), full_page=True)
    pg.click('#db-grid a[data-modul="angebot"]'); pg.wait_for_url('**/admin/')
    check('Klick auf Angebot öffnet die Mitarbeiter-Eingabe', pg.url.endswith('/admin/'))
    ctx.close()

    # ── Mobil (390 px) und dunkles Design ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.42', breite=390, dunkel=True)
    breiter = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    check('390 px: kein waagerechtes Scrollen', not breiter)
    kopf = pg.evaluate("""(() => { const t = document.querySelector('.db-top-inner').getBoundingClientRect();
        return [...document.querySelectorAll('.db-top-inner > *')].every(e => { const r = e.getBoundingClientRect(); return r.left >= t.left - 1 && r.right <= t.right + 1; }); })()""")
    check('390 px: Kopfzeile passt in die Breite', kopf)
    spalten = pg.evaluate("getComputedStyle(document.querySelector('#db-grid')).gridTemplateColumns.split(' ').length")
    check('390 px: Kacheln untereinander (eine Spalte)', spalten == 1, spalten)
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design folgt der Systemeinstellung', hg != 'rgb(255, 255, 255)', hg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_dunkel.png'), full_page=True)
    pg.click('#db-theme'); pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'")
    gespeichert = pg.evaluate("localStorage.getItem('wochenangebot.theme')")
    check('Umschalter speichert das Design wie die Angebotsseite', json.loads(gespeichert or 'null') == 'light', gespeichert)
    pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('gewähltes Design bleibt nach dem Neuladen', pg.evaluate("document.documentElement.getAttribute('data-theme')") == 'light')
    ctx.close()

    # ── Wartung des Eingabebereichs: Bearbeiter gesperrt, Administrator mit Hinweis ──
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Dashboard',
                                          'message': 'Kurz weg <img src=x onerror="window.__xss=1">'})
    check('Wartung des Eingabebereichs gestartet', st == 200 and r.get('aktiv') is True, (st, r))
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.43')
    a = kacheln(pg)[0]
    check('Bearbeiter: Angebot in Wartung, ohne Verweis', a['tag'] == 'DIV' and not a['href'] and a['badge'] == 'Wartung', a)
    check('Bearbeiter: Wartungshinweis als Text (kein HTML)', 'Kurz weg <img' in a['hint'] and a['bilder'] == 0 and not pg.evaluate('window.__xss'), a)
    check('Bearbeiter: 0 von 8 Anwendungen', '0 von 8' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_bearbeiter.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.44')
    a = kacheln(pg)[0]
    check('Administrator: Angebot in Wartung, aber weiter erreichbar', a['tag'] == 'A' and a['badge'] == 'Wartung – Zugang für Administratoren', a)
    ctx.close()
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': 'Test beendet'})
    check('Wartung beendet', st == 200 and r.get('aktiv') is False, (st, r))

    # ── Abmelden beendet die Sitzung serverseitig ──
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.45')
    check('nach der Wartung wieder verfügbar', kacheln(pg)[0]['badge'] == 'Verfügbar')
    pg.click('#db-logout'); pg.wait_for_selector('#db-login:not([hidden])')
    angemeldet = pg.evaluate("fetch('../api/?action=status', {credentials: 'same-origin'}).then(r => r.json()).then(j => j.loggedIn)")
    check('Abmelden: Anmeldehinweis und Sitzung beendet', angemeldet is False and pg.is_hidden('#db-bereich'), angemeldet)
    pg.reload(); pg.wait_for_selector('#db-login:not([hidden])')
    check('nach dem Neuladen weiter abgemeldet', pg.is_hidden('#db-bereich'))
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
