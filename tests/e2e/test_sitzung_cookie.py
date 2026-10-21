"""Sitzungs-Cookie mit Präfix __Host- über HTTPS (GR-108, ADR-003 Befund B-1).

HTTPS wird wie hinter Caddy über „X-Forwarded-Proto: https“ nachgestellt. Cookies werden von Hand geführt, weil ein
Cookie-Speicher Secure-Cookies über http://127.0.0.1 nicht zurückschicken würde – so lassen sich auch die genauen
Set-Cookie-Angaben prüfen.
"""
import json
import sys
import urllib.error
import urllib.request

from kunden_hilfe import Client
from umgebung import BASE, SH, shot

API = BASE + '/api/?action='
PW = 'Sicheres-Passwort-1'
NEU = '__Host-WA_ADMIN'
ALT = 'WA_ADMIN'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def roh(action, data=None, https=True, cookies=None, csrf='', ip='198.51.100.70', extra=None):
    """Eine Anfrage; Rückgabe: Status, JSON, Liste der Set-Cookie-Zeilen, Kopfzeilen."""
    h = {'X-Forwarded-For': ip, 'Content-Type': 'application/json', 'X-CSRF-Token': csrf}
    if https:
        h['X-Forwarded-Proto'] = 'https'
    if cookies:
        h['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
    h.update(extra or {})
    req = urllib.request.Request(API + action, data=None if data is None else json.dumps(data).encode(), headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        r = e
    body = r.read()
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    return r.code, j, r.headers.get_all('Set-Cookie') or [], r.headers


def cookie(zeilen, name):
    """Wert und Attribute (klein geschrieben) des zuletzt gesetzten Cookies „name“, sonst (None, '')."""
    wert, attr = None, ''
    for z in zeilen:
        kopf = z.split(';', 1)
        k, _, v = kopf[0].partition('=')
        if k.strip() == name:
            wert, attr = v.strip(), (kopf[1] if len(kopf) > 1 else '').lower()
    return wert, attr


# ── HTTP (lokale Tests): Name unverändert, damit bestehende Tests und Werkzeuge weiter funktionieren ──
st, j, sc, _ = roh('login', {'username': 'admin', 'password': PW}, https=False, ip='198.51.100.71')
alt_sid, attr = cookie(sc, ALT)
check('HTTP: Anmeldung setzt Cookie ohne Präfix', st == 200 and alt_sid and cookie(sc, NEU)[0] is None, sc)
check('HTTP: ohne Secure (Browser würden es sonst verwerfen)', 'secure' not in attr, attr)

# ── HTTPS: Präfix und Attribute ──
st, j, sc, _ = roh('login', {'username': 'admin', 'password': PW})
sid, attr = cookie(sc, NEU)
csrf = j.get('csrf', '')
check('HTTPS: Anmeldung erfolgreich', st == 200 and j.get('ok'), j)
check('HTTPS: Sitzung als __Host-WA_ADMIN', bool(sid), sc)
check('HTTPS: kein Cookie ohne Präfix gesetzt', cookie(sc, ALT)[0] is None, sc)
check('HTTPS: Secure, HttpOnly, SameSite=Strict, Pfad /', all(a in attr for a in ('secure', 'httponly', 'samesite=strict', 'path=/')), attr)
check('HTTPS: keine Domain-Angabe (hostgebunden)', 'domain=' not in attr, attr)

st, j, sc, _ = roh('status', cookies={NEU: sid})
check('HTTPS: Sitzung über __Host-Cookie gültig', st == 200 and j.get('loggedIn') is True, j)
check('HTTPS: Schreibaktion mit CSRF-Token möglich', roh('draft_ping', {}, cookies={NEU: sid}, csrf=j.get('csrf', ''))[0] == 200)

# ── Altes Cookie ohne Präfix wird über HTTPS nicht gelesen, sondern gelöscht ──
st, j, sc, _ = roh('status', cookies={ALT: sid})
check('HTTPS: gültige Kennung unter altem Namen wird nicht angenommen', st == 200 and j.get('loggedIn') is False, j)
wert, attr = cookie(sc, ALT)
check('HTTPS: altes Cookie wird im Browser gelöscht', wert in ('', 'deleted') and ('max-age=0' in attr or 'expires=thu, 01 jan 1970' in attr) and 'path=/' in attr, sc)
st, j, sc, _ = roh('status', cookies={NEU: sid})
check('HTTPS: neue Sitzung bleibt davon unberührt', j.get('loggedIn') is True, j)

# ── Untergeschobenes Cookie (Cookie-Tossing einer Nachbar-Subdomain) ──
st, j, sc, _ = roh('status', cookies={ALT: alt_sid}, ip='198.51.100.72')
check('HTTPS: untergeschobene Kennung ohne Präfix wird ignoriert', j.get('loggedIn') is False, j)
st, j, sc, _ = roh('login', {'username': 'admin', 'password': PW}, cookies={NEU: 'angreifer-kennung-0123456789abcdef'}, ip='198.51.100.72')
neu_sid = cookie(sc, NEU)[0]
check('HTTPS: vorgegebene Kennung wird bei der Anmeldung nicht übernommen', st == 200 and neu_sid and neu_sid != 'angreifer-kennung-0123456789abcdef', sc)

# ── Kunden nutzen dieselbe Sitzung: ebenfalls mit Präfix ──
A = Client('198.51.100.73')
A.call('login', {'username': 'admin', 'password': PW})
rev = A.call('kunden')[1]['rev']
code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Cookie Test GmbH', 'nr': 'C-1', 'email': 'cookie@example.org', 'active': True,
                                'angebote': ['std'], 'login': {'username': 'cookie.kunde', 'password': 'Kunden-Kennwort-7', 'mustChange': False, 'active': True}})
check('Testkunde angelegt', code == 200, r)
st, j, sc, _ = roh('kunde_login', {'username': 'cookie.kunde', 'password': 'Kunden-Kennwort-7'}, ip='198.51.100.74')
ksid, kattr = cookie(sc, NEU)
check('HTTPS: Kunden-Anmeldung setzt __Host-Cookie', st == 200 and ksid and 'secure' in kattr and 'domain=' not in kattr, sc)
st, j, sc, _ = roh('kunde_status', cookies={NEU: ksid}, ip='198.51.100.74')
check('HTTPS: Kundensitzung gültig', (j.get('kunde') or {}).get('firma') == 'Cookie Test GmbH', j)
check('HTTPS: Kundensitzung ist keine Mitarbeitersitzung', j.get('staff') is False and roh('status', cookies={NEU: ksid}, ip='198.51.100.74')[1].get('loggedIn') is False)
st, j, sc, _ = roh('kunde_status', cookies={ALT: ksid}, ip='198.51.100.74')
check('HTTPS: Kundensitzung unter altem Namen nicht angenommen', j.get('kunde') is None, j)

# ── App: Sitzung nur über Kopfzeile, kein Cookie ──
app = {'X-WA-Client': 'app'}
st, j, sc, hd = roh('login', {'username': 'admin', 'password': PW}, ip='198.51.100.75', extra=app)
app_sid = hd.get('X-WA-Sitzung', '')
check('HTTPS-App: Anmeldung ohne Sitzungs-Cookie', st == 200 and cookie(sc, NEU)[0] is None and cookie(sc, ALT)[0] is None, sc)
st, j, sc, hd = roh('status', ip='198.51.100.75', extra={**app, 'X-WA-Sitzung': app_sid})
check('HTTPS-App: Sitzung über X-WA-Sitzung gültig', bool(app_sid) and j.get('loggedIn') is True, j)

# ── Firewall erkennt angemeldete Mitarbeiter am neuen Cookie (keine Inhaltsprüfung ihrer Eingaben) ──
probe = {'notiz': '<script>alert(1)</script>'}
st_anon = roh('kunde_status', probe, ip='198.51.100.76')[0]
st_staff = roh('kunde_status', probe, cookies={NEU: sid}, ip='198.51.100.77')[0]
check('Firewall: anonyme Anfrage mit Skript-Muster abgewiesen', st_anon == 403, st_anon)
check('Firewall: angemeldeter Mitarbeiter (__Host-Cookie) wird erkannt', st_staff != 403, st_staff)

# ── Abmelden beendet die Sitzung ──
st, j, sc, _ = roh('status', cookies={NEU: sid})
roh('logout', {}, cookies={NEU: sid}, csrf=j.get('csrf', ''))
check('HTTPS: nach Abmelden ungültig', roh('status', cookies={NEU: sid})[1].get('loggedIn') is False)

# ── Echter Browser: Chromium behandelt 127.0.0.1 als sicheren Ursprung und speichert dort auch __Host-Cookies ──
from playwright.sync_api import sync_playwright  # noqa: E402

# Wie hinter Caddy: der Browser sähe https://… als eigene Herkunft (Herkunftsprüfung, GR-109)
HTTPS_ORIGIN = BASE.replace('http://', 'https://', 1)


def wie_https(ctx):
    """Origin der API-Anfragen wie hinter Caddy (https://…) – Chromium setzt ihn selbst, daher über route umschreiben."""
    def umschreiben(route):
        h = dict(route.request.headers)
        if 'origin' in h: h['origin'] = HTTPS_ORIGIN
        route.continue_(headers=h)
    ctx.route('**/api/**', umschreiben)
    return ctx
fehler = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for breite in (1280, 390):
        ctx = wie_https(br.new_context(viewport={'width': breite, 'height': 900},
                             extra_http_headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-For': f'198.51.100.{80 + breite % 7}'}))
        ctx.add_cookies([{'name': ALT, 'value': alt_sid, 'url': BASE + '/'}])   # Altbestand bzw. untergeschoben
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        check(f'Browser {breite}px: altes Cookie meldet nicht an (Anmeldemaske)', pg.is_visible('#screen-auth'))
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        namen = {c['name']: c for c in ctx.cookies()}
        c = namen.get(NEU, {})
        check(f'Browser {breite}px: Eingabebereich nach Anmeldung, Cookie __Host-WA_ADMIN', c.get('secure') and c.get('httpOnly') and c.get('sameSite') == 'Strict' and c.get('path') == '/', namen.keys())
        check(f'Browser {breite}px: altes Cookie entfernt', ALT not in namen, namen.keys())
        shot(pg, f'{SH}/sitzung-cookie-{breite}.png')
        pg.reload(); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        check(f'Browser {breite}px: Sitzung bleibt nach Neuladen bestehen', pg.is_visible('#screen-editor'))
        ctx.close()
    # Kundenseite im Browser
    ctx = wie_https(br.new_context(viewport={'width': 390, 'height': 900}, extra_http_headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '198.51.100.90'}))
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(BASE + '/'); pg.wait_for_selector('#btn-kunde-login')
    pg.click('#btn-kunde-login'); pg.fill('#kl-form [name=username]', 'cookie.kunde'); pg.fill('#kl-form [name=password]', 'Kunden-Kennwort-7'); pg.click('#kl-form [type=submit]')
    pg.wait_for_selector('#btn-kunde'); pg.wait_for_selector('tr.row')
    check('Browser: Kunden-Anmeldung mit __Host-Cookie', any(c['name'] == NEU for c in ctx.cookies()))
    shot(pg, f'{SH}/sitzung-cookie-kunde-390.png')
    ctx.close(); br.close()
check('Browser: keine JavaScript-Fehler', not fehler, fehler)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
