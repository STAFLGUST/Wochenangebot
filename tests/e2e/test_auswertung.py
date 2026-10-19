"""Auswertung: Karte der Kunden-Anmeldungen. Ortsdaten laden (Test-Quelle über WA_ORT_URL, erzeugt aus erfundenen
Bereichen), Anmeldeort je Kunden-Anmeldung (IPv4/IPv6, ohne IP-Adresse gespeichert), Zeitraum, Aufbewahrung,
Löschen mit dem Kunden, Rechte und Oberfläche (Karte, Punkte, Hinweisfeld, Filter, Liste, 390 px)."""
import gzip, http.server, os, sys, threading, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH, AUX_PORT, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


# --- Test-Ortsdaten (Format wie DB-IP City Lite): erfundene Zuordnung, abwechselnde Orte, damit nichts zusammengefasst wird
ORTE = [('EU', 'DE', 'Hamburg', 'Hamburg', 53.5507, 9.993), ('EU', 'DE', 'Bavaria', 'München', 48.1374, 11.5755),
        ('EU', 'DE', 'Berlin', 'Berlin', 52.52, 13.405), ('EU', 'AT', 'Vienna', 'Wien', 48.2085, 16.3721), ('EU', 'DE', 'Lower Saxony', 'Hannover', 52.3744, 9.7386)]


def ortsdaten():
    rows = []
    for i in range(110000):                     # 20.0.0.0 … : je /24 ein Bereich
        a, b = divmod(i, 256)
        c, o = 20 + a // 256, a % 256
        k, reg, region, city, lat, lon = ORTE[i % len(ORTE)]
        rows.append(f'{c}.{o}.{b}.0,{c}.{o}.{b}.255,{k},{reg},{region},"{city}",{lat},{lon}')
    for i in range(12000):                      # 2a10:xxxx::/32
        k, reg, region, city, lat, lon = ORTE[(i + 2) % len(ORTE)]
        rows.append(f'2a10:{i:x}::,2a10:{i:x}:ffff:ffff:ffff:ffff:ffff:ffff,{k},{reg},{region},"{city}",{lat},{lon}')
    return gzip.compress(('\n'.join(rows) + '\n').encode())


GZ = ortsdaten()
SERVE = {'on': True}


class Quelle(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if SERVE['on'] and self.path.startswith('/dbip-city-lite-') and self.path.endswith('.csv.gz'):
            self.send_response(200); self.send_header('Content-Length', str(len(GZ))); self.end_headers(); self.wfile.write(GZ)
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Quelle)
threading.Thread(target=srv.serve_forever, daemon=True).start()

A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'id': '', 'name': 'Vera Viewer', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-55', 'mustChange': False})
kid = {}
for firma, user in [('Kantine Nord', 'kantine.nord'), ('Hotel Süd', 'hotel.sued'), ('Bistro West', 'bistro.west')]:
    rev = A.call('kunden')[1]['rev']
    code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': firma, 'nr': 'K-' + user[:3], 'email': user + '@example.org', 'active': True, 'angebote': ['std'],
                                    'login': {'username': user, 'password': 'Kunden-Kennwort-5', 'mustChange': False, 'active': True}})
    kid[user] = r['customer']['id']
check('customers created', len(kid) == 3)


def kunde_login(user, ip, ua=None):
    c = Client(ip)
    if ua: c.headers['User-Agent'] = ua
    return c.call('kunde_login', {'username': user, 'password': 'Kunden-Kennwort-5'})[0]


IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
code, r = A.call('auswertung')
check('without location data: overview works, data missing', code == 200 and r['ortsdaten'] is None and r['entries'] == [] and r['kannAktualisieren'] is True, code)
check('login before location data is recorded without place', kunde_login('bistro.west', '20.0.4.9') == 200)
e0 = A.call('auswertung')[1]['entries']
check('… entry without coordinates', len(e0) == 1 and 'lat' not in e0[0] and e0[0]['kid'] == kid['bistro.west'], e0)

# Ortsdaten laden: nur Administrator mit Passwortbestätigung
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
check('editor cannot load location data', E.call('ort_update', {})[0] == 403)
check('editor cannot see the evaluation by default', E.call('auswertung')[0] == 403)
t0 = time.time()
code, r = A.call('ort_update', {})
check('admin loads location data', code == 200 and r['ortsdaten']['orte'] == len(ORTE), (code, r))
print(f'  (Ortsdaten in {time.time() - t0:.1f} s gebaut)')
check('location data stored in data folder (not served)', os.path.getsize(os.environ['UDATA'] + '/geo/orte.dat.php') > 1000000)
try:
    st = urllib.request.urlopen(B + '/data/geo/orte.dat.php').status
except urllib.error.HTTPError as ex:
    st = ex.code
check('data file not readable over the web', st == 404, st)

# Anmeldungen: IPv4 (Hamburg/München), IPv6 (Berlin), Handy, private Adresse
check('customer logins succeed', kunde_login('kantine.nord', '20.0.0.17') == 200 and kunde_login('hotel.sued', '20.0.1.200', IPHONE) == 200
      and kunde_login('hotel.sued', '2a10:0:1234::5') == 200 and kunde_login('kantine.nord', '10.20.30.40') == 200)
r = A.call('auswertung')[1]
es = r['entries']
by = lambda user: [e for e in es if e['kid'] == kid[user]]
k = by('kantine.nord'); h = by('hotel.sued')
check('IPv4 login placed in Hamburg', any(e.get('city') == 'Hamburg' and abs(e['lat'] - 53.5507) < 1e-3 and e['cc'] == 'DE' for e in k), k)
check('mobile login placed in München, device recognised', any(e.get('city') == 'München' and e['dev'] == 'mobil' and e['region'] == 'Bavaria' for e in h), h)
check('IPv6 login placed', any(e.get('city') == 'Berlin' and e['dev'] == 'desktop' for e in h), h)
check('private address: login recorded, no place', any('lat' not in e and 'cc' not in e for e in k), k)
check('newest first, customer names included', es[0]['t'] >= es[-1]['t'] and {c['firma'] for c in r['kunden']} == {'Kantine Nord', 'Hotel Süd', 'Bistro West'})
raw = storage_raw('anmeldeorte') or ''
check('no IP addresses stored', raw and '20.0.0.17' not in raw and '2a10' not in raw and '10.20.30.40' not in raw and '"ip"' not in raw)
check('failed login is not recorded', Client('20.0.2.1').call('kunde_login', {'username': 'kantine.nord', 'password': 'falsch-falsch-1'})[0] == 401 and len(A.call('auswertung')[1]['entries']) == len(es))

# Zeitraum und Aufbewahrung (90 Tage)
iso = lambda d: (datetime.now(timezone.utc) - timedelta(days=d)).strftime('%Y-%m-%dT%H:%M:%SZ')
doc = {'entries': [{'t': iso(120), 'kid': kid['kantine.nord'], 'via': 'passwort', 'dev': 'desktop', 'city': 'Wien', 'region': 'Vienna', 'cc': 'AT', 'lat': 48.2085, 'lon': 16.3721},
                   {'t': iso(40), 'kid': kid['kantine.nord'], 'via': 'passwort', 'dev': 'desktop', 'city': 'Wien', 'region': 'Vienna', 'cc': 'AT', 'lat': 48.2085, 'lon': 16.3721}]
       + [x for x in reversed(es)]}
storage_write('anmeldeorte', doc)
n30 = len(A.call('auswertung')[1]['entries'])
c90, r90 = A.call('auswertung&tage=90')
check('30 days excludes older logins', n30 == len(es), n30)
check('90 days includes them, older than 90 days never shown', c90 == 200 and len(r90['entries']) == len(es) + 1, len(r90.get('entries', [])))
check('invalid period falls back to 30 days', A.call('auswertung&tage=5000')[1]['tage'] == 30)
kunde_login('bistro.west', '20.0.5.3')
raw = storage_raw('anmeldeorte') or ''
check('entries older than 90 days are deleted on the next login', iso(120)[:10] not in raw and iso(40)[:10] in raw)

# Rechte: Bearbeiter mit Recht sieht die Auswertung (setzt Kunden ansehen voraus), darf Ortsdaten nicht laden
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}
A.call('user_save', {'id': uid['erika'], 'name': 'Erika Editor', 'role': 'editor', 'active': True, 'grant': ['auswertung.sehen'], 'deny': []})
pe = set(E.call('status')[1]['user']['perms'])
check('right pulls in viewing customers', {'auswertung.sehen', 'kunden.sehen'} <= pe, sorted(pe))
code, r = E.call('auswertung')
check('editor with right sees the evaluation, cannot update', code == 200 and r['kannAktualisieren'] is False and len(r['entries']) > 0 and E.call('ort_update', {})[0] == 403)
check('right appears in the rights table', any(p['key'] == 'auswertung.sehen' and p['requires'] == ['kunden.sehen'] for p in A.call('rechte')[1]['catalog']))

# Fehler beim Laden der Ortsdaten
SERVE['on'] = False
code, r = A.call('ort_update', {})
check('unavailable source: clear error, old data kept', code == 502 and 'nicht aktualisiert' in r.get('error', '') and A.call('auswertung')[1]['ortsdaten'] is not None, (code, r))
SERVE['on'] = True
log = str(A.call('log')[1].get('entries'))
check('update is logged', 'Ortsdaten für die Auswertung aktualisiert' in log)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def page(user, password, w=1440):
        pg = br.new_page(viewport={'width': w, 'height': 950}, is_mobile=w < 500, has_touch=w < 500); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return pg

    vp = page('vera', 'Leser-Zugang-55')
    check('UI: viewer has no evaluation tab', vp.locator('#vt-auswertung').is_hidden())
    vp.close()
    a = page('admin', PW)
    check('UI: admin sees evaluation tab', a.is_visible('#vt-auswertung'))
    a.click('#vt-auswertung'); a.wait_for_selector('#aw-svg #aw-pts .aw-pt')
    check('UI: map drawn from local data (countries)', a.locator('#aw-land path').count() > 150)
    check('UI: one point per place', a.locator('#aw-pts .aw-pt').count() == 3, a.locator('#aw-pts .aw-pt').count())
    check('UI: summary', a.inner_text('#aw-sum') == '6 Anmeldungen · 3 Kunden · 3 Orte', a.inner_text('#aw-sum'))
    check('UI: attribution for location data and map', 'DB-IP' in a.inner_text('.aw-foot') and 'Natural Earth' in a.inner_text('.aw-foot'))
    a.wait_for_timeout(200)
    a.screenshot(path=SH + '/auswertung.png')
    a.emulate_media(color_scheme='dark'); a.wait_for_timeout(150); a.screenshot(path=SH + '/auswertung-dunkel.png'); a.emulate_media(color_scheme='light')
    a.locator('#aw-pts .aw-pt').first.dispatch_event('click')
    a.wait_for_selector('#aw-pop:not([hidden])')
    pb, mb = a.locator('#aw-pop').bounding_box(), a.locator('.aw-map').bounding_box()
    check('UI: clicking a point lists customers there, inside the map', 'Anmeldung' in a.inner_text('#aw-pop') and pb and mb['y'] <= pb['y'] and pb['y'] + pb['height'] <= mb['y'] + mb['height'] + 1, (pb, mb))
    a.screenshot(path=SH + '/auswertung-punkt.png')
    vb0 = a.get_attribute('#aw-svg', 'viewBox')
    a.click('[data-aw=in]')
    check('UI: zoom changes the map section', a.get_attribute('#aw-svg', 'viewBox') != vb0)
    a.click('[data-aw=fit]')
    a.select_option('#aw-kunde', kid['hotel.sued']); a.wait_for_function("document.querySelectorAll('#aw-pts .aw-pt').length === 2")
    check('UI: customer filter shows only their places', a.locator('#aw-pts .aw-pt').count() == 2 and 'Kantine' not in a.inner_text('.aw-list'))
    a.click('.aw-list tr[data-aw-pt]:has-text("München")'); a.wait_for_selector('#aw-pop:not([hidden])')
    check('UI: list row opens the place on the map', 'München' in a.inner_text('#aw-pop') and 'Hotel Süd' in a.inner_text('#aw-pop'))
    check('UI: device shown in list', 'Handy' in a.inner_text('.aw-list'))
    a.click('[data-aw-tage="90"]'); a.wait_for_selector('[data-aw-tage="90"][aria-pressed="true"]')
    a.select_option('#aw-kunde', ''); a.wait_for_function("document.querySelectorAll('#aw-pts .aw-pt').length === 4")
    check('UI: 90 days shows the older place too', a.locator('#aw-pts .aw-pt').count() == 4)
    # Ziehen verschiebt die Karte
    box = a.locator('#aw-svg').bounding_box(); vb1 = a.get_attribute('#aw-svg', 'viewBox')
    a.mouse.move(box['x'] + 200, box['y'] + 200); a.mouse.down(); a.mouse.move(box['x'] + 320, box['y'] + 260, steps=5); a.mouse.up()
    check('UI: dragging pans the map', a.get_attribute('#aw-svg', 'viewBox') != vb1)
    a.set_viewport_size({'width': 390, 'height': 844}); a.wait_for_timeout(300)
    a.click('[data-aw=fit]'); a.wait_for_timeout(100)
    a.screenshot(path=SH + '/auswertung-390.png', full_page=False)
    check('mobile: no horizontal page scroll', a.evaluate('document.documentElement.scrollWidth') <= 390)
    # Kunde löschen entfernt seine Anmeldeorte
    rev = A.call('kunden')[1]['rev']
    check('customer deleted', A.call('kunde_delete', {'id': kid['hotel.sued'], 'rev': rev})[0] == 200)
    check('… and their login places are gone', all(e['kid'] != kid['hotel.sued'] for e in A.call('auswertung&tage=90')[1]['entries']) and kid['hotel.sued'] not in (storage_raw('anmeldeorte') or ''))
    check('no page errors', not errs, errs[:3])
    br.close()

srv.shutdown()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
