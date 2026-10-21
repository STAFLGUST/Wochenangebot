"""Herkunftsprüfung im API-Einstieg (GR-109, lib/herkunft.php): nur Anfragen von der eigenen Seite.

`Sec-Fetch-Site` same-site/cross-site → 403 (auch von Nachbar-Subdomains wie test.angebot-stafl.de); bei Anfragen außer
GET/HEAD muss ein mitgesendeter `Origin` genau der eigene sein. Ohne diese Kopfzeilen (App, Server-zu-Server) gilt der
bisherige Schutz unverändert. Ausnahme nur `abmelden1` (Ein-Klick-Abmeldung aus dem E-Mail-Programm).
"""
import http.server
import sys
import threading
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, API, B
from umgebung import AUX_PORT

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def mit(cl, **kopf):
    """Kopfzeilen für die nächsten Anfragen des Clients setzen (None entfernt)."""
    cl.headers = {k.replace('_', '-'): v for k, v in kopf.items() if v is not None}
    return cl


def roh(action, method='GET', kopf=None, daten=None):
    req = urllib.request.Request(API + action, data=daten, method=method, headers={'X-Forwarded-For': '198.51.100.70', **(kopf or {})})
    try:
        r = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, r.headers, r.read().decode('utf-8', 'replace')


EIGEN = B   # http://127.0.0.1:<port>
LOGIN = {'username': 'admin', 'password': PW}

# ── Anmelden (POST) je nach Herkunft ──
for site, erwartet in (('cross-site', 403), ('same-site', 403), ('same-origin', 200), ('none', 200), (None, 200)):
    cl = mit(Client('198.51.100.10'), Sec_Fetch_Site=site)
    code, r = cl.call('login', LOGIN)
    check(f'Anmelden mit Sec-Fetch-Site {site or "(fehlt)"} → {erwartet}', code == erwartet, (code, r.get('error')))
code, r = mit(Client('198.51.100.11'), Sec_Fetch_Site='CROSS-SITE').call('login', LOGIN)
check('Groß-/Kleinschreibung spielt keine Rolle', code == 403)
code, r = mit(Client('198.51.100.11'), Sec_Fetch_Site='cross-site').call('login', LOGIN)
check('Abweisung mit verständlicher Meldung, ohne Anmeldung', code == 403 and 'nicht von unserer Seite' in r.get('error', '') and not r.get('csrf'), r)

# ── Origin bei Anfragen, die etwas ändern ──
for origin, erwartet in ((EIGEN, 200), ('http://angreifer.example', 403), ('null', 403), (EIGEN.replace('127.0.0.1', 'localhost'), 403),
                         (EIGEN.rsplit(':', 1)[0] + ':1', 403), (EIGEN.replace('http://', 'https://'), 403), (EIGEN + '.angreifer.example', 403)):
    code, r = mit(Client('198.51.100.12'), Origin=origin, Sec_Fetch_Site='same-origin').call('login', LOGIN)
    check(f'Anmelden mit Origin {origin} → {erwartet}', code == erwartet, (code, r.get('error')))
code, r = mit(Client('198.51.100.13'), Origin=EIGEN.replace('http://', 'https://'), X_Forwarded_Proto='https').call('login', LOGIN)
check('hinter dem Proxy (HTTPS): eigener https-Origin angenommen', code == 200, (code, r.get('error')))
code, r = mit(Client('198.51.100.13'), Origin=EIGEN, X_Forwarded_Proto='https').call('login', LOGIN)
check('hinter dem Proxy (HTTPS): http-Origin abgewiesen', code == 403, code)

# ── Angemeldete Sitzung: Lesen und Schreiben nur von der eigenen Seite ──
A = Client('198.51.100.14')
check('Administrator angemeldet (ohne Kopfzeilen, wie bisher)', A.call('login', LOGIN)[0] == 200)
check('Lesen ohne Kopfzeilen (App/Werkzeuge) wie bisher', A.call('users')[0] == 200)
check('Lesen von der eigenen Seite', mit(A, Sec_Fetch_Site='same-origin').call('users')[0] == 200)
check('Lesen von einer Nachbar-Subdomain abgewiesen (trotz Sitzung)', mit(A, Sec_Fetch_Site='same-site').call('users')[0] == 403)
check('Lesen von fremder Seite abgewiesen', mit(A, Sec_Fetch_Site='cross-site').call('users')[0] == 403)
check('GET mit fremdem Origin, aber eigener Seite: Lesen erlaubt (Origin nur beim Ändern)', mit(A, Origin='http://angreifer.example', Sec_Fetch_Site='same-origin').call('users')[0] == 200)
code, r = mit(A, Origin='http://angreifer.example').call('logout', {})
check('Abmelden mit fremdem Origin abgewiesen', code == 403)
check('… Sitzung besteht weiter', mit(A).call('status')[1].get('loggedIn') is True)
check('Abmelden von der eigenen Seite', mit(A, Origin=EIGEN, Sec_Fetch_Site='same-origin').call('logout', {})[0] == 200)

# ── Öffentliche Aktionen, unbekannte Aktionen, Ausnahme abmelden1 ──
check('öffentliches Angebot ohne Kopfzeilen', roh('offer')[0] == 200)
check('öffentliches Angebot von der eigenen Seite', roh('offer', kopf={'Sec-Fetch-Site': 'same-origin'})[0] == 200)
check('öffentliches Angebot von fremder Seite abgewiesen', roh('offer', kopf={'Sec-Fetch-Site': 'cross-site'})[0] == 403)
check('Kunden-Anmeldung von Nachbar-Subdomain abgewiesen', roh('kunde_login', 'POST', {'Sec-Fetch-Site': 'same-site', 'Content-Type': 'application/json'}, b'{}')[0] == 403)
check('unbekannte Aktion von fremder Seite: 403 vor 404', roh('gibt_es_nicht', kopf={'Sec-Fetch-Site': 'cross-site'})[0] == 403)
check('unbekannte Aktion von eigener Seite: 404', roh('gibt_es_nicht', kopf={'Sec-Fetch-Site': 'same-origin'})[0] == 404)
code, kopf, text = roh('abmelden1&t=ungueltig', 'POST', {'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://mail.example', 'Content-Type': 'application/x-www-form-urlencoded'}, b'List-Unsubscribe=One-Click')
check('Ein-Klick-Abmeldung aus dem E-Mail-Programm nicht durch die Herkunft abgewiesen', code != 403 or 'nicht von unserer Seite' not in text, (code, text[:120]))
code, kopf, text = roh('status', kopf={'Sec-Fetch-Site': 'cross-site'})
check('Abweisung nicht zwischenspeicherbar', code == 403 and 'no-store' in (kopf.get('Cache-Control') or ''), dict(kopf))

# ── Fremde Seiten können ihre Besucher nicht sperren lassen (Firewall unberührt) ──
for _ in range(60):
    roh('login', 'POST', {'Sec-Fetch-Site': 'cross-site', 'Content-Type': 'application/json', 'X-Forwarded-For': '198.51.100.71'}, b'{"username":"x","password":"y"}')
st = Client('198.51.100.71')
check('nach 60 abgewiesenen Fremdanfragen: Adresse nicht gesperrt', st.call('login', LOGIN)[0] == 200)


# ── Echter Browser: Chromium meldet die Herkunft selbst ──
class Fremd(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        seite = (f'<!doctype html><meta charset="utf-8"><title>fremd</title>'
                 f'<form id="f" method="post" action="{API}logout" enctype="text/plain"><input name="x" value="1"></form>').encode()
        self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(seite)))
        self.end_headers(); self.wfile.write(seite)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Fremd)
threading.Thread(target=srv.serve_forever, daemon=True).start()
fehler = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    ctx = br.new_context(extra_http_headers={'X-Forwarded-For': '198.51.100.72'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
    pg.wait_for_selector('#screen-auth', state='hidden')
    check('Browser: Anmelden auf der eigenen Seite funktioniert (same-origin + Origin)', True)
    eigen = pg.evaluate("fetch('../api/?action=status').then(r => r.json()).then(j => j.loggedIn)")
    check('Browser: eigene Seite liest die Schnittstelle', eigen is True, eigen)
    pg.goto(B + '/api/?action=status')
    check('Browser: Adresse direkt aufgerufen (Sec-Fetch-Site none) → beantwortet', '"loggedIn":true' in pg.content(), pg.content()[:200])
    fremd = ctx.new_page(); fremd.on('pageerror', lambda e: fehler.append(str(e)))
    fremd.goto(f'http://127.0.0.1:{AUX_PORT}/')
    with fremd.expect_navigation():
        fremd.evaluate("document.getElementById('f').submit()")
    check('Browser: Formular einer anderen Seite (anderer Port = same-site) wird abgewiesen', 'nicht von unserer Seite' in fremd.content(), fremd.content()[:300])
    weiter = pg.evaluate("fetch('../api/?action=status', {credentials: 'same-origin'}).then(r => r.json()).then(j => j.loggedIn)") if pg.goto(B + '/admin/') else None
    check('Browser: Sitzung danach weiter angemeldet (Abmelden der fremden Seite wirkungslos)', weiter is True, weiter)
    br.close()
srv.shutdown()

check('keine JavaScript-Fehler', not fehler, fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
