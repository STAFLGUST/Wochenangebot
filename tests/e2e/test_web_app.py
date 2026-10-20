"""Web-App (zum Home-Bildschirm): Manifest, Symbole, Offline-Speicher (sw.js) nur für Startseite, Dateien und das
öffentliche Wochenangebot, Offline-Hinweis, Hinweis „Zum Home-Bildschirm“ (iPhone, Android, nicht am Computer,
nicht in der installierten Web-App)."""
import json
import os
import socket
import subprocess
import struct
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

from umgebung import AUX_PORT, BASE, SH

res = []


def check(n, c):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n)


def png_groesse(daten):
    """Breite und Höhe aus dem PNG-Kopf (ohne Bildbibliothek, wie in der CI verfügbar)."""
    if daten[:8] != b'\x89PNG\r\n\x1a\n' or daten[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', daten[16:24])


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}


# ---------- Manifest und Symbole ----------
raw, _ = get('/manifest.json')
m = json.loads(raw)
check('Manifest: Name, Vollbild, Start und Geltungsbereich', m['short_name'] == 'Wochenangebot' and m['display'] == 'standalone' and m['start_url'] == './' and m['scope'] == './')
groessen = {}
for ic in m['icons']:
    groessen[ic['sizes'] + ic['purpose']] = png_groesse(get('/' + ic['src'])[0]) == tuple(int(x) for x in ic['sizes'].split('x'))
check('Manifest-Symbole vorhanden und in angegebener Größe (inkl. maskable)', all(groessen.values()) and '512x512maskable' in groessen)
check('iPhone-Symbol 180 × 180', png_groesse(get('/assets/icons/apple-touch-icon.png')[0]) == (180, 180))
html = get('/')[0].decode()
check('Startseite verweist auf Manifest, Symbole und Web-App-Angaben',
      'rel="manifest" href="manifest.json"' in html and 'rel="apple-touch-icon"' in html and 'apple-mobile-web-app-capable' in html and 'assets/webapp.js?v=' in html)
ohne = [s for s in ['/kontakt/', '/impressum/', '/datenschutz/', '/admin/'] if 'favicon-32.png' not in get(s)[0].decode()]
check('Favicon auf allen Seiten', not ohne)

# Für den Offline-Test ein zweiter PHP-Server auf derselben Testkopie, den der Test beenden kann („Verbindung weg“).
# (Die Offline-Simulation des Browsers wirkt nicht auf Service Worker.)
APP = os.path.dirname(os.environ['UDATA'])
WEB = f'http://127.0.0.1:{AUX_PORT}'
srv = None


def server(an):
    global srv
    if an:
        srv = subprocess.Popen(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-S', f'127.0.0.1:{AUX_PORT}'], cwd=APP,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        srv.terminate()
        srv.wait(timeout=10)
    for _ in range(100):
        with socket.socket() as so:
            if (so.connect_ex(('127.0.0.1', AUX_PORT)) == 0) == an:
                return
        time.sleep(0.1)


server(True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch()

    # ---------- Offline-Speicher ----------
    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(WEB + '/')
    page.wait_for_function('navigator.serviceWorker && navigator.serviceWorker.ready.then(() => true)')
    page.reload()
    page.wait_for_function('!!navigator.serviceWorker.controller', timeout=15000)
    page.wait_for_selector('.al-tab tbody tr, #list tr', timeout=20000)
    check('Offline-Speicher aktiv (Seite wird vom Service Worker begleitet)', page.evaluate('!!navigator.serviceWorker.controller'))
    page.evaluate("fetch('api/?action=kunde_status', {cache: 'no-store'}).then(r => r.text())")
    page.wait_for_function("caches.open('wa-webapp-1').then(c => c.keys()).then(k => k.some(r => r.url.includes('action=offer')))")
    keys = page.evaluate("caches.open('wa-webapp-1').then(c => c.keys()).then(k => k.map(r => r.url))")
    check('gespeichert: Startseite, Dateien, öffentliches Angebot', any(k.endswith('/') for k in keys) and any('/assets/frontend.js' in k for k in keys) and any('action=offer' in k for k in keys))
    check('nicht gespeichert: Anmeldung/Kundenstatus, Eingabebereich, andere Aktionen',
          not any('kunde_status' in k or '/admin/' in k or ('/api/' in k and 'action=offer' not in k) for k in keys))
    check('je Datei nur eine Fassung', len([k for k in keys if '/assets/frontend.js' in k]) == 1)

    server(False)
    page.reload()
    page.wait_for_selector('#offline-hint:not([hidden])', timeout=20000)
    txt = page.inner_text('#offline-hint')
    check('offline: Angebot aus dem Speicher mit Hinweis „Preise ohne Gewähr“', 'ohne Gewähr' in txt and 'Keine Verbindung' in txt)
    check('offline: Artikel sichtbar', page.locator('.al-tab tbody tr').count() > 50)
    page.screenshot(path=SH + '/webapp-offline.png')
    kunde = page.evaluate("fetch('api/?action=offer&angebot=kantine').then(r => 'antwort', () => 'netzfehler')")
    check('offline: Kundenangebote nicht aus dem Speicher', kunde == 'netzfehler')
    status = page.evaluate("fetch('api/?action=kunde_status').then(r => 'antwort', () => 'netzfehler')")
    check('offline: Kundenstatus nicht aus dem Speicher', status == 'netzfehler')
    admin_offline = page.context.new_page()
    try:
        admin_offline.goto(WEB + '/admin/', timeout=8000)
        admin_ok = 'Eingabebereich' in admin_offline.content()
    except Exception:
        admin_ok = False
    check('offline: Eingabebereich nicht aus dem Speicher', not admin_ok)
    admin_offline.close()
    server(True)
    page.reload()
    page.wait_for_selector('.al-tab tbody tr', timeout=20000)
    check('wieder online: kein Offline-Hinweis', page.locator('#offline-hint').is_hidden())
    check('am Computer kein Hinweis „Zum Home-Bildschirm“', page.locator('#webapp-hint').is_hidden())
    ctx.close()

    # ---------- iPhone ----------
    iphone = p.devices['iPhone 13']
    ctx = browser.new_context(**iphone)
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE + '/')
    page.wait_for_selector('#webapp-hint:not([hidden])')
    check('iPhone: Hinweis „Zum Home-Bildschirm“', 'Zum Home-Bildschirm' in page.inner_text('#webapp-hint') and 'iPhone' in page.inner_text('#webapp-hint'))
    page.screenshot(path=SH + '/webapp-hinweis-iphone.png')
    check('iPhone: kein seitliches Scrollen', page.evaluate('document.documentElement.scrollWidth') <= page.viewport_size['width'])
    page.click('#webapp-hint [data-wh="aus"]')
    check('Hinweis schließen', page.locator('#webapp-hint').is_hidden())
    page.reload()
    page.wait_for_selector('.al-tab tbody tr, #list tr', timeout=20000)
    check('geschlossener Hinweis bleibt weg', page.locator('#webapp-hint').is_hidden())
    ctx.close()

    # ---------- iPhone offline ----------
    ctx = browser.new_context(**iphone)
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(WEB + '/')
    page.wait_for_function('navigator.serviceWorker.ready.then(() => true)')
    page.reload()
    page.wait_for_function('!!navigator.serviceWorker.controller', timeout=15000)
    page.wait_for_selector('.al-tab tbody tr', timeout=20000)
    page.wait_for_function("caches.open('wa-webapp-1').then(c => c.keys()).then(k => k.some(r => r.url.includes('action=offer')))")
    server(False)
    page.reload()
    page.wait_for_selector('#offline-hint:not([hidden])', timeout=20000)
    page.screenshot(path=SH + '/webapp-offline-mobil.png')
    check('iPhone offline: Hinweis und Angebot, kein seitliches Scrollen', page.locator('.al-tab tbody tr').count() > 50 and page.evaluate('document.documentElement.scrollWidth') <= page.viewport_size['width'])
    server(True)
    ctx.close()

    # ---------- installierte Web-App (iPhone) ----------
    ctx = browser.new_context(**iphone)
    ctx.add_init_script("Object.defineProperty(navigator, 'standalone', { get: () => true })")
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE + '/')
    page.wait_for_selector('.al-tab tbody tr, #list tr', timeout=20000)
    check('installierte Web-App: kein Hinweis, Kennzeichen is-webapp', page.locator('#webapp-hint').is_hidden() and page.evaluate("document.documentElement.classList.contains('is-webapp')"))
    page.screenshot(path=SH + '/webapp-installiert.png')
    ctx.close()

    # ---------- Android: Installationsabfrage des Browsers ----------
    ctx = browser.new_context(**p.devices['Pixel 7'])
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE + '/')
    page.wait_for_selector('.al-tab tbody tr, #list tr', timeout=20000)
    check('Android ohne Browser-Abfrage: kein Hinweis', page.locator('#webapp-hint').is_hidden())
    page.evaluate("""() => { const e = new Event('beforeinstallprompt', { cancelable: true });
      e.prompt = () => { window.__gefragt = true; }; e.userChoice = Promise.resolve({ outcome: 'accepted' }); window.dispatchEvent(e); }""")
    page.wait_for_selector('#webapp-hint [data-wh="installieren"]')
    page.screenshot(path=SH + '/webapp-hinweis-android.png')
    page.click('#webapp-hint [data-wh="installieren"]')
    page.wait_for_function('window.__gefragt === true')
    page.wait_for_selector('#webapp-hint', state='hidden')
    check('Android: „Installieren“ öffnet die Abfrage des Browsers', True)
    ctx.close()

    check('keine JavaScript-Fehler', not errors)
    if errors:
        print('\n'.join(errors[:5]))
    browser.close()

server(False)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
