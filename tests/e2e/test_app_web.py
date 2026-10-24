"""App (mobile/) als Web-Build gegen den echten Testserver: Kunde (Angebot, Merkliste, Bestellwunsch, Fracht,
eigene Bestellwünsche, offline), Mitarbeiter (Zwei-Faktor, Bestellwunsch bearbeiten), Sitzungsablauf.
Voraussetzung: `cd mobile && npm ci && npm run export:web` (erzeugt mobile/dist-web). Ohne Build überspringt
tests/run_e2e.py diese Gruppe beim vollen Lauf und meldet das."""
import base64
import hashlib
import hmac
import json
import os
import shutil
import struct
import sys
import time

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, REPO, SH, SMTP_PORT, storage_raw

PW = 'Sicheres-Passwort-1'
KPW = 'Kantine-Kennwort-5'
res = []


def check(n, c):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n)


def totp(secret):
    d = hmac.new(base64.b32decode(secret), struct.pack('>Q', int(time.time() // 30)), hashlib.sha1).digest()
    o = d[-1] & 15
    return '%06d' % ((struct.unpack('>I', d[o:o + 4])[0] & 0x7fffffff) % 1000000)


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


# ---------- Web-Build der App neben die API der Testkopie legen (gleiche Herkunft wie in der App: /api/) ----------
DIST = os.path.join(REPO, 'mobile', 'dist-web')
if not os.path.isfile(os.path.join(DIST, 'index.html')):
    print('FAIL App-Web-Build fehlt (cd mobile && npm run export:web)')
    print('0/1 passed')
    sys.exit(1)
APP = os.path.dirname(os.environ['UDATA'])
shutil.copytree(os.path.join(DIST, '_expo'), os.path.join(APP, '_expo'), dirs_exist_ok=True)
shutil.copytree(os.path.join(DIST, 'assets'), os.path.join(APP, 'assets'), dirs_exist_ok=True)
shutil.copy(os.path.join(DIST, 'index.html'), os.path.join(APP, 'index.html'))   # nur in dieser Testkopie

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
admin = Client('198.51.100.2')
assert admin.call('login', {'username': 'admin', 'password': PW})[0] == 200
rev = admin.call('kunden')[1]['rev']
r = admin.call('kunde_save', {'rev': rev, 'firma': 'App Kantine GmbH', 'nr': 'K-77', 'email': 'app.kunde@example.org', 'telefon': '040 123', 'active': True, 'angebote': ['std'],
                              'login': {'username': 'app.kunde', 'password': KPW, 'mustChange': False, 'active': True}})
assert r[0] == 200, r
assert admin.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': False})[0] == 200
admin.call('user_save', {'username': 'app.editor', 'name': 'App Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
web = Client('198.51.100.9')
assert web.call('login', {'username': 'app.editor', 'password': 'Editor-Zugang-77'})[0] == 200
secret = web.call('twofa_begin', {})[1]['secret']
assert web.call('twofa_enable', {'code': totp(secret)})[0] == 200
used_step = int(time.time() // 30)

T = lambda i: f'[data-testid="{i}"]'   # noqa: E731
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, locale='de-DE')
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    # abgebrochene Anfragen (offline-Test) und 401/409-Antworten meldet der Browser selbst – das sind keine Fehler der App
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    sent = []
    page.on('request', lambda rq: sent.append(rq) if '/api/' in rq.url else None)

    # ---------- Gast ----------
    page.goto(BASE + '/')
    page.wait_for_selector(T('angebot-titel'), timeout=30000)
    check('Angebot lädt in der App', 'KW 43' in page.inner_text(T('angebot-titel')))
    check('alle Artikel gezählt', page.inner_text(T('trefferzahl')).startswith('276 Artikel'))
    check('App sendet X-WA-Client und keine Cookies nötig', any(rq.headers.get('x-wa-client') == 'app' for rq in sent))
    page.screenshot(path=SH + '/app-angebot.png')
    page.fill(T('suche'), 'roastbeef')
    page.wait_for_function("document.querySelector('[data-testid=trefferzahl]').innerText.includes('von 276')")
    n = int(page.inner_text(T('trefferzahl')).split()[0])
    check('Suche filtert', 0 < n < 276 and 'Roastbeef' in page.inner_text(T('angebotsliste')))
    page.fill(T('suche'), '')
    page.click(T('bereich-1'))
    page.wait_for_function("document.querySelector('[data-testid=trefferzahl]').innerText.includes('von 276')")
    check('Bereich filtert', 'von 276' in page.inner_text(T('trefferzahl')))
    page.click(T('bereich-alle'))
    page.wait_for_function("document.querySelector('[data-testid=trefferzahl]').innerText.startsWith('276')")
    first = page.locator('[data-testid^="artikel-r"]').first
    first_id = first.get_attribute('data-testid').replace('artikel-', '')
    page.click(T('merken-' + first_id))
    page.click(T('tab-merkliste'))
    page.wait_for_selector('[data-testid="merkliste"] ' + T('artikel-' + first_id))
    check('Merkliste (Gast, auf dem Gerät)', page.locator('[data-testid="merkliste"] [data-testid^="artikel-"]').count() == 1)
    page.click(T('tab-angebot'))
    page.wait_for_selector(T('vermerk'))
    check('Vermerk mit Fracht unter dem Angebot', 'frachtfrei' in page.inner_text(T('vermerk')))
    page.click(T('artikel-' + first_id))
    page.wait_for_selector(T('artikel-name'))
    check('Artikel öffnet, Gast ohne Mengenfeld', page.locator(T('artikel-menge')).count() == 0)
    page.screenshot(path=SH + '/app-artikel-gast.png')
    page.click(T('zurueck'))

    # ---------- Kunde anmelden ----------
    page.click(T('tab-konto'))
    page.click(T('anmelden-kunde'))
    page.fill(T('kunde-name'), 'app.kunde')
    page.fill(T('kunde-pw'), 'falsch-falsch-1')
    page.click(T('kunde-anmelden'))
    page.wait_for_selector(T('anmelden-fehler'))
    check('falsches Passwort gemeldet', 'nicht korrekt' in page.inner_text(T('anmelden-fehler')))
    page.fill(T('kunde-pw'), KPW)
    page.click(T('kunde-anmelden'))
    page.wait_for_selector(T('konto-firma'))
    check('Kunde angemeldet', 'App Kantine GmbH' in page.inner_text(T('konto-firma')))
    page.screenshot(path=SH + '/app-konto.png')
    check('Sitzung nur über Kopfzeile (kein Cookie gesetzt)', not [c for c in ctx.cookies() if c['name'] == 'WA_ADMIN'])
    for _ in range(40):
        if doc('merklisten'):
            break
        time.sleep(0.25)
    check('Merkliste vom Gerät beim Anmelden übernommen (Server)', json.dumps(doc('merklisten') or {}).count('|') >= 2)

    # ---------- Bestellwunsch ----------
    page.click(T('tab-angebot'))
    page.click(T('artikel-' + first_id))
    page.wait_for_selector(T('artikel-menge'))
    page.fill(T('artikel-menge'), '100')
    page.click('text=+10 kg')
    check('Schnellwahl addiert', page.input_value(T('artikel-menge')) == '110')
    page.fill(T('artikel-menge'), '12,345')
    check('ungültige Menge gesperrt', page.get_attribute(T('artikel-uebernehmen'), 'aria-disabled') == 'true')
    page.fill(T('artikel-menge'), '120')
    page.screenshot(path=SH + '/app-artikel-menge.png')
    page.click(T('artikel-uebernehmen'))
    page.wait_for_selector(T('bestellleiste'))
    check('Bestellleiste zeigt Position und Menge', '1 Position' in page.inner_text(T('bestellleiste')) and '120 kg' in page.inner_text(T('bestellleiste')))
    page.screenshot(path=SH + '/app-angebot-bestellleiste.png')
    page.click(T('bestellleiste'))
    page.wait_for_selector(T('fracht-hinweis'))
    check('Frachthinweis unter Mindestmenge (35 €)', 'Mindestmenge nicht erreicht' in page.inner_text(T('fracht-hinweis')) and '35,00 €' in page.inner_text('body'))
    page.fill(T('feld-termin'), '31.02.2027')
    check('ungültiges Datum gemeldet', 'TT.MM.JJJJ' in page.inner_text('body'))
    termin = time.strftime('%d.%m.%Y', time.localtime(time.time() + 7 * 86400))
    page.fill(T('feld-termin'), termin)
    page.fill(T('feld-referenz'), 'App-Referenz <b>1</b>')
    page.fill(T('feld-bemerkung'), 'Bitte morgens liefern')
    page.screenshot(path=SH + '/app-bestellwunsch.png', full_page=True)
    page.click(T('senden'))
    page.wait_for_selector(T('quittung'), timeout=30000)
    check('Bestellwunsch gesendet', 'übermittelt' in page.inner_text(T('quittung')))
    page.screenshot(path=SH + '/app-quittung.png')
    orders = doc('bestellungen')
    o = orders[-1]
    check('Server speichert Menge, Fracht und Termin (ISO)', o['totalQty'] == 120 and o['fracht']['kosten'] == 35 and o['termin'] == time.strftime('%Y-%m-%d', time.localtime(time.time() + 7 * 86400)))
    check('Übermittlungskennung gesetzt', len(o.get('requestId', '')) >= 16)
    check('eine E-Mail an uns', len(smtp.messages) == 1)
    page.click('text=Zu meinen Bestellwünschen')
    page.wait_for_selector(T('vorgang-' + o['nr']))
    check('eigene Bestellwünsche', 'Eingegangen' in page.inner_text(T('vorgang-' + o['nr'])))
    page.click(T('vorgang-' + o['nr']))
    page.wait_for_selector(T('detail-nr'))
    check('Detail zeigt Positionen und Referenz', 'App-Referenz <b>1</b>' in page.inner_text('body') and '120 kg' in page.inner_text('body'))
    page.screenshot(path=SH + '/app-bestellung-detail.png', full_page=True)
    page.click(T('zurueck'))

    # ---------- Wiederholung nach Verbindungsabbruch: keine Doppelbestellung ----------
    page.click(T('tab-angebot'))
    page.click(T('artikel-' + first_id))
    page.fill(T('artikel-menge'), '310')
    page.click(T('artikel-uebernehmen'))
    page.click(T('bestellleiste'))
    page.wait_for_selector(T('fracht-hinweis'))
    check('ab Mindestmenge frachtfrei', 'frachtfrei' in page.inner_text(T('fracht-hinweis')))
    abbruch = {'n': 0}

    def antwort_verlieren(route):
        resp = route.fetch()   # Server verarbeitet den Bestellwunsch …
        abbruch['n'] += 1
        route.abort()          # … aber die Antwort kommt nicht an

    page.route('**/api/?action=kunde_bestellung', antwort_verlieren)
    page.click(T('senden'))
    page.wait_for_selector(T('senden-fehler'))
    check('Verbindungsfehler gemeldet, Entwurf bleibt', 'Keine Verbindung' in page.inner_text(T('senden-fehler')) and abbruch['n'] == 1)
    page.unroute('**/api/?action=kunde_bestellung')
    page.click(T('senden'))
    page.wait_for_selector(T('quittung'), timeout=30000)
    orders = doc('bestellungen')
    check('erneutes Senden ergibt keinen zweiten Bestellwunsch', len(orders) == 2 and len(smtp.messages) == 2)
    page.click('text=Weiter im Angebot')
    page.wait_for_selector(T('angebot-titel'), timeout=30000)   # Wechsel abwarten, sonst bricht das Neuladen ab (ERR_ABORTED)
    page.wait_for_load_state('networkidle')

    # ---------- offline: gespeichertes Angebot mit Hinweis ----------
    # erst offline gehen, wenn das Angebot des Kunden auf dem Gerät liegt (AsyncStorage = localStorage im Web-Build)
    page.wait_for_function("Object.keys(localStorage).some((k) => k.startsWith('angebot.') && !k.includes('.gast.'))", timeout=15000)
    page.route('**/api/?action=offer*', lambda route: route.abort())
    page.reload()
    try:
        page.wait_for_selector(T('hinweis-offline'), timeout=30000)
    except Exception:
        # Befund für die Fehlersuche (CI-Artefakt): was die App zeigt und was auf dem Gerät gespeichert ist
        page.screenshot(path=SH + '/app-offline-fehler.png')
        print('DIAGNOSE Seite:', page.inner_text('body')[:600].replace('\n', ' | '))
        print('DIAGNOSE Ablage:', page.evaluate("Object.keys(localStorage).filter((k) => !k.startsWith('wa.')).sort().join(', ')"))
        raise
    check('offline: gespeichertes Angebot mit Hinweis „ohne Gewähr“', 'ohne Gewähr' in page.inner_text(T('hinweis-offline')) and page.locator('[data-testid^="artikel-r"]').count() > 0)
    page.screenshot(path=SH + '/app-offline.png')
    page.unroute('**/api/?action=offer*')
    page.reload()
    page.wait_for_selector(T('angebot-titel'), timeout=30000)
    check('nach Neustart weiter angemeldet (Kennung im sicheren Speicher)', page.locator(T('hinweis-anmelden')).count() == 0)

    # ---------- Sitzung beendet (Passwortwechsel im Browser) ----------
    kb = Client('203.0.113.50')
    kb.call('kunde_login', {'username': 'app.kunde', 'password': KPW})
    assert kb.call('kunde_passwort', {'current': KPW, 'password': 'Neues-Kennwort-66'})[0] == 200
    page.click(T('tab-bestellungen'))
    page.wait_for_selector('text=Ihre Anmeldung ist abgelaufen', timeout=15000)
    page.click(T('tab-konto'))
    page.wait_for_selector(T('anmelden-team'))
    check('abgelaufene Sitzung: App meldet ab und sagt es', page.locator(T('anmelden-kunde')).count() == 1 and 'abgelaufen' in page.inner_text('body'))

    # ---------- Mitarbeiter ----------
    page.click(T('anmelden-team'))
    page.fill(T('team-name'), 'app.editor')
    page.fill(T('team-pw'), 'Editor-Zugang-77')
    page.click(T('team-weiter'))
    page.wait_for_selector(T('team-code'))
    while int(time.time() // 30) <= used_step or int(time.time()) % 30 > 27:
        time.sleep(0.5)
    page.fill(T('team-code'), '000000' if totp(secret) != '000000' else '111111')
    page.click(T('team-weiter'))
    page.wait_for_selector(T('team-fehler'))
    check('falscher Code abgewiesen', page.locator(T('team-fehler')).count() == 1)
    page.fill(T('team-code'), totp(secret))
    page.click(T('team-weiter'))
    page.wait_for_selector(T('vorgang-' + orders[0]['nr']), timeout=20000)
    check('Mitarbeiter sieht Bestellwünsche', page.locator('[data-testid^="vorgang-B-"]').count() == 2)
    page.screenshot(path=SH + '/app-team-liste.png')
    page.click(T('status-neu'))
    page.wait_for_function("document.querySelectorAll('[data-testid^=\"vorgang-B-\"]').length === 2")
    page.fill(T('vorgang-suche'), 'App-Referenz')
    page.wait_for_function("document.querySelectorAll('[data-testid^=\"vorgang-B-\"]').length === 1")
    check('Suche nach Referenz', True)
    page.click(T('vorgang-' + orders[0]['nr']))
    page.wait_for_selector(T('vorgang-speichern'))
    check('Kundendaten im Detail', 'K-77' in page.inner_text('body') and '040 123' in page.inner_text('body'))
    page.click(T('setze-in_bearbeitung'))
    uid = next(u['id'] for u in doc('nutzer')['users'] if u['username'] == 'app.editor')
    page.click(T('zust-' + uid))
    page.fill(T('vorgang-notiz'), 'Rückruf <i>morgen</i>')
    page.screenshot(path=SH + '/app-team-detail.png', full_page=True)
    page.click(T('vorgang-speichern'))
    page.wait_for_selector(T('vorgang-ok'))
    o0 = next(x for x in doc('bestellungen') if x['nr'] == orders[0]['nr'])
    check('Status, Zuständigkeit und Notiz gespeichert', o0['workflow'] == 'in_bearbeitung' and o0['assignee'] == uid and o0['note'] == 'Rückruf <i>morgen</i>')
    # gleichzeitige Änderung im Eingabebereich → App erhält 409 statt zu überschreiben
    d = web.call('bestellung&nr=' + orders[0]['nr'])[1]['order']
    assert web.call('bestellung_save', {'nr': d['nr'], 'revision': d['revision'], 'workflow': 'bestaetigt', 'assignee': uid, 'note': 'im Browser'})[0] == 200
    page.click(T('setze-storniert'))
    page.click(T('vorgang-speichern'))
    page.wait_for_selector(T('vorgang-fehler'))
    check('gleichzeitige Änderung: kein Überschreiben', 'inzwischen' in page.inner_text(T('vorgang-fehler')) and next(x for x in doc('bestellungen') if x['nr'] == orders[0]['nr'])['workflow'] == 'bestaetigt')
    page.click(T('zurueck'))
    page.click(T('tab-profil'))
    page.wait_for_selector(T('profil-name'))
    page.screenshot(path=SH + '/app-team-konto.png')
    page.click(T('team-abmelden'))
    page.wait_for_selector(T('angebot-titel'))
    check('Mitarbeiter abgemeldet', page.locator(T('hinweis-anmelden')).count() == 1)

    # ---------- Breite Fenster / Tablet ----------
    page.set_viewport_size({'width': 1024, 'height': 900})
    page.wait_for_timeout(300)
    page.screenshot(path=SH + '/app-tablet.png')
    check('kein waagerechtes Überlaufen', page.evaluate('document.documentElement.scrollWidth') <= 1024)
    check('keine JavaScript-Fehler', not errors)
    if errors:
        print('\n'.join(errors[:10]))
    browser.close()

smtp.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
