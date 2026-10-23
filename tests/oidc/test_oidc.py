"""Anmeldung über Keycloak (Roadmap 7b, ADR-003, GR-108/GR-110) – Prüfungen gegen die Testumgebung aus umgebung.sh.

Prüft die Bedrohungen aus ADR-003 §1, soweit sie diese Stufe betreffen: Härtung von Keycloak (Verwaltung nicht öffentlich,
kein Passwort-Grant, PKCE, exakte Weiterleitungen), Pflicht zum zweiten Faktor, eigene Sitzung je Host (__Host-Cookies,
keine Domain-Cookies, Sitzung eines Hosts gilt nicht auf dem anderen), Single Sign-on, Rechte bleiben bei uns, Aktionen nur
auf ihrem Host (GR-109, HR), keine
eigenen Anmeldeverfahren auf Keycloak-Hosts, untergeschobene Kopfzeilen, gesperrte und unbekannte Konten, Abmelden für
alle Anwendungen (Back-Channel-Logout).
"""
import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

for _v in ('no_proxy', 'NO_PROXY'):   # Testhosts nie über einen Proxy
    os.environ[_v] = ','.join(x for x in (os.environ.get(_v), '.stafl.test') if x)
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WORK = os.environ.get('OIDC_WORK') or os.path.join(REPO, 'tests', '.arbeit', 'oidc')
SH = os.environ.get('WA_SHOTS') or os.path.join(REPO, 'tests', '.ergebnisse')
os.makedirs(SH, exist_ok=True)
PORT = 8443
D, A, W, B, HR, L = (f'https://{h}.stafl.test:{PORT}' for h in ('dashboard', 'angebot', 'verwaltung', 'bestand', 'hr', 'login'))
LEGACY = f'http://127.0.0.1:{os.environ.get("APACHE_PORT", "8280")}'
KC = f'http://127.0.0.1:{os.environ.get("KC_PORT", "8180")}'
CA = os.path.join(WORK, 'caddy', 'pki', 'authorities', 'local', 'root.crt')
GEHEIM = dict(z.strip().split('=', 1) for z in open(os.path.join(WORK, 'geheim.env')) if '=' in z)
PW_ALT = 'Sicheres-Passwort-1'   # Administrator der Testdaten (tests/fixtures/data-seed)
NUTZER = {'admin': ('Admin-Kennwort-CI-1', 'nur-fuer-tests-otp-admin'), 'erika': ('Erika-Kennwort-CI-1', 'nur-fuer-tests-otp-erika'),
          'fremd': ('Fremd-Kennwort-CI-1', 'nur-fuer-tests-otp-fremd'), 'neu': ('Neu-Kennwort-CI-1', None),
          'chef': ('Chef-Kennwort-CI-1', None)}
SVEN = {'eigen': 'Sven-Eigenes-Kennwort-1', 'zweit': 'Sven-Zweites-Kennwort-2', 'dritt': 'Sven-Drittes-Kennwort-3', 'neu_app': 'Bearbeiter-Zugang-7788', 'chef_app': 'Leitung-Zugang-7788', 'eva': 'Eva-Eigenes-Kennwort-1'}   # über die Konsole angelegte Konten (nur Test)
POSTFACH = {'port': int(os.environ.get('OIDC_SMTP_PORT', '2526')), 'user': 'postfach@stafl.test', 'pass': 'Postfach-Test-' + str(os.getpid())}
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + ' '.join(str(i).split())[:300]) if i else ''), flush=True)


def totp_zaehler(geheim, zaehler):
    """Einmalcode wie Keycloak (HmacSHA1, 6 Stellen, 30 s; Schlüssel = Bytes des gespeicherten Geheimnisses)."""
    h = hmac.new(geheim.encode(), struct.pack('>Q', zaehler), hashlib.sha1).digest()
    o = h[-1] & 15
    return '%06d' % ((struct.unpack('>I', h[o:o + 4])[0] & 0x7fffffff) % 1000000)


BENUTZT = {}   # Geheimnis → schon eingegebene Zeitschritte (Keycloak lässt jeden Code nur einmal zu: otpPolicyCodeReusable=false)


def totp(geheim, versatz=0):
    """Noch nie eingegebener, gültiger Einmalcode (aktueller oder nächster Zeitschritt; Keycloak lässt ±1 Schritt zu).
    Sind beide schon verbraucht, wird bis zum nächsten Zeitschritt gewartet (Zustand der Uhr, keine feste Wartezeit).
    So entstehen keine Fehlversuche, die der Brute-Force-Schutz als schnelle Wiederholung werten würde. „versatz“
    bleibt aus älteren Aufrufen erhalten und ist nur noch ein Mindestabstand."""
    benutzt = BENUTZT.setdefault(geheim, set())
    while True:
        jetzt = int(time.time() // 30)
        frei = [z for z in (jetzt + versatz, jetzt + 1) if z >= jetzt and z <= jetzt + 1 and z not in benutzt]
        if frei:
            benutzt.add(frei[0])
            return totp_zaehler(geheim, frei[0])
        while int(time.time() // 30) == jetzt:
            time.sleep(0.2)


TLS = ssl.create_default_context(cafile=CA)
# Seitenaufruf wie ein Browser (mod_auth_openidc leitet nur Seitenaufrufe zur Anmeldung weiter, sonst 401)
SEITE = {'Accept': 'text/html', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}


class OhneWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def anfrage(url, method='GET', daten=None, kopf=None, folgen=False, jar=None):
    h = [urllib.request.HTTPSHandler(context=TLS)]
    if not folgen: h.append(OhneWeiterleitung())
    if jar is not None: h.append(urllib.request.HTTPCookieProcessor(jar))
    op = urllib.request.build_opener(*h)
    req = urllib.request.Request(url, data=daten, method=method, headers=kopf or {})
    try:
        r = op.open(req, timeout=30)
    except urllib.error.HTTPError as e:
        r = e
    text = r.read().decode('utf-8', 'replace')
    return r.code, r.headers, text


class Legacy:
    """Bisheriger Zugang (wie heute angebot-stafl.de) – nur zur Vorbereitung der Mitarbeiterkonten."""
    def __init__(self):
        self.jar = http.cookiejar.CookieJar(); self.csrf = ''

    def call(self, action, data=None):
        h = {'Host': 'legacy.stafl.test', 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf, 'X-Forwarded-For': '198.51.100.9'}
        code, _, text = anfrage(LEGACY + '/api/?action=' + action, 'POST' if data is not None else 'GET',
                                None if data is None else json.dumps(data).encode(), h, jar=self.jar)
        try: j = json.loads(text)
        except ValueError: j = {}
        if j.get('csrf'): self.csrf = j['csrf']
        return code, j


def protokoll_roh():
    """Einträge des Protokolls (Dateispeicher der Testumgebung, aktueller Monat)."""
    pfad = os.path.join(WORK, 'app', 'data', 'protokoll', time.strftime('%Y-%m', time.gmtime()) + '.php')
    if not os.path.exists(pfad):
        return []
    roh = open(pfad, encoding='utf-8').read()
    return json.loads(roh[roh.index('?>') + 2:].strip()) if '?>' in roh else json.loads(roh)


def nutzer_roh():
    with open(os.path.join(WORK, 'app', 'data', 'nutzer.php'), encoding='utf-8') as f:
        roh = f.read()
    return {u['username']: u for u in json.loads(roh[roh.index('?>') + 2:].strip())['users']}


# ── Vorbereitung: Mitarbeiterkonten im bisherigen Eingabebereich (gleiche Benutzernamen wie in Keycloak) ──
V = Legacy()
check('Vorbereitung: Administrator der Testdaten angemeldet (bisheriger Zugang)', V.call('login', {'username': 'admin', 'password': PW_ALT})[0] == 200)
V.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
if not nutzer_roh()['erika'].get('active'):   # Wiederholung ohne Neustart der Umgebung
    V.call('user_save', {'id': nutzer_roh()['erika']['id'], 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True})
check('Vorbereitung: Bearbeiterin erika angelegt und aktiv', nutzer_roh()['erika'].get('active') is True)
V.call('user_save', {'id': '', 'name': 'Sven Start', 'username': 'Sven.Start', 'role': 'editor', 'active': True, 'password': 'Start-Zugang-77', 'mustChange': False})
check('Vorbereitung: Mitarbeiterkonto für ein später über die Konsole angelegtes Keycloak-Konto', 'sven.start' in nutzer_roh())
V.call('user_save', {'id': '', 'name': 'Neu Ohne Zweitfaktor', 'username': 'neu', 'role': 'editor', 'active': True, 'password': SVEN['neu_app'], 'mustChange': False})
V.call('user_save', {'id': '', 'name': 'Chef Administrator', 'username': 'chef', 'role': 'admin', 'active': True, 'password': SVEN['chef_app'], 'mustChange': False})
check('Vorbereitung: Bearbeiter „neu“ und Administrator „chef“ (beide ohne zweiten Faktor)', {'neu', 'chef'} <= set(nutzer_roh()))
V.call('user_save', {'id': '', 'name': 'Eva Einladung', 'username': 'eva.einladung', 'role': 'editor', 'active': True, 'password': 'Eva-Zugang-7788', 'mustChange': False})
check('Vorbereitung: Mitarbeiterkonto für eine Einladung per Mail', 'eva.einladung' in nutzer_roh())

# ── Härtung von Keycloak (ADR-003 §2) ──
code, _, text = anfrage(L + '/realms/mitarbeiter/.well-known/openid-configuration')
meta = json.loads(text) if code == 200 else {}
check('Realm „mitarbeiter“ über login.stafl.test erreichbar, Aussteller stimmt', meta.get('issuer') == L + '/realms/mitarbeiter', meta.get('issuer'))
check('PKCE mit S256 angeboten', 'S256' in meta.get('code_challenge_methods_supported', []))
for pfad in ('/admin/', '/admin/master/console/', '/realms/master/.well-known/openid-configuration', '/realms/master/protocol/openid-connect/auth'):
    check(f'Verwaltung/Master-Realm nicht öffentlich: {pfad} → 404', anfrage(L + pfad)[0] == 404)
code, _, text = anfrage(meta.get('token_endpoint', L + '/x'), 'POST', urllib.parse.urlencode({
    'grant_type': 'password', 'client_id': 'dashboard', 'client_secret': GEHEIM['OIDC_SECRET_DASHBOARD'],
    'username': 'erika', 'password': NUTZER['erika'][0], 'scope': 'openid'}).encode(), {'Content-Type': 'application/x-www-form-urlencoded'})
check('Passwort-Grant (Anmeldung ohne Browser) abgelehnt', code in (400, 401) and 'access_token' not in text, (code, text[:120]))
code, kopf, _ = anfrage(meta.get('authorization_endpoint', L) + '?' + urllib.parse.urlencode({
    'client_id': 'dashboard', 'response_type': 'code', 'scope': 'openid', 'redirect_uri': 'https://angreifer.example/oidc/callback', 'state': 'x'}))
check('fremde Weiterleitungsadresse abgelehnt (exakte Adressen)', code == 400, code)
code, kopf, _ = anfrage(meta.get('authorization_endpoint', L) + '?' + urllib.parse.urlencode({
    'client_id': 'dashboard', 'response_type': 'code', 'scope': 'openid', 'redirect_uri': D + '/oidc/callback', 'state': 'x'}))
check('Anmeldung ohne PKCE abgelehnt', code in (302, 303, 400) and ('code_challenge' in (kopf.get('Location') or '') or code == 400 or 'error=' in (kopf.get('Location') or '')), (code, kopf.get('Location')))

# Einstellungen aus der Verwaltungsschnittstelle (nur lokal auf 127.0.0.1, nie über Caddy)
code, _, text = anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
    'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung-ci', 'password': GEHEIM['KC_ADMIN_PASSWORD']}).encode(),
    {'Content-Type': 'application/x-www-form-urlencoded'})
tok = json.loads(text).get('access_token', '') if code == 200 else ''
check('Verwaltungszugang nur lokal (Testvorbereitung)', bool(tok), (code, text[:100]))
_, _, text = anfrage(KC + '/admin/realms/mitarbeiter', kopf={'Authorization': 'Bearer ' + tok})
realm = json.loads(text) if text.startswith('{') else {}
check('Realm: Brute-Force-Schutz an, keine Selbstregistrierung, kein Passwort-Zurücksetzen per E-Mail',
      realm.get('bruteForceProtected') is True and realm.get('registrationAllowed') is False and realm.get('resetPasswordAllowed') is False, realm.get('bruteForceProtected'))
check('Realm: nur HTTPS, Anmeldesitzung 4 Std. Leerlauf / 10 Std. höchstens',
      realm.get('sslRequired') == 'all' and realm.get('ssoSessionIdleTimeout') == 14400 and realm.get('ssoSessionMaxLifespan') == 36000)
_, _, text = anfrage(KC + '/admin/realms/mitarbeiter/clients', kopf={'Authorization': 'Bearer ' + tok})
clients = {c['clientId']: c for c in (json.loads(text) if text.startswith('[') else [])}
for cid in ('dashboard', 'angebot', 'verwaltung', 'bestand', 'hr'):
    c = clients.get(cid, {})
    check(f'Client {cid}: vertraulich, nur Code-Ablauf, PKCE S256, exakte Weiterleitung, kein CORS',
          c.get('publicClient') is False and c.get('directAccessGrantsEnabled') is False and c.get('implicitFlowEnabled') is False
          and c.get('serviceAccountsEnabled') is False and c.get('attributes', {}).get('pkce.code.challenge.method') == 'S256'
          and all('*' not in u for u in c.get('redirectUris', ['*'])) and c.get('webOrigins') == [], c.get('redirectUris'))
    check(f'Client {cid}: Back-Channel-Logout eingerichtet', c.get('attributes', {}).get('backchannel.logout.url', '').startswith(f'https://{cid}.stafl.test'))
    check(f'Client {cid}: Standard nur Passwort (zweiter Faktor je Konto), Anmeldemethoden im Claim amr',
          c.get('attributes', {}).get('minimum.acr.value') == 'pwd' and any(m.get('protocolMapper') == 'oidc-amr-mapper' for m in c.get('protocolMappers', [])),
          (c.get('attributes', {}).get('minimum.acr.value'), [m.get('protocolMapper') for m in c.get('protocolMappers', [])]))
check('Realm: eigener Anmeldeablauf mit Stufen (Passwort, zweiter Faktor)', realm.get('browserFlow') == 'mitarbeiter-browser', realm.get('browserFlow'))
_log = open(os.path.join(WORK, 'realm-aktualisieren.log'), encoding='utf-8').read()
check('Realm auf aktuellem Stand (realm-aktualisieren beim Start, Protokoll)', 'Realm aktuell (Stand 5' in _log, _log[-300:])
check('Stand 3: Client „verwaltung“ nachträglich angelegt, Geheimnisse in .env erzeugt (ohne Anzeige), Hinweis auf Neustart',
      'angelegt:  Client verwaltung' in _log and 'erzeugt:   OIDC_SECRET_VERWALTUNG in .env' in _log and 'erzeugt:   OIDC_CRYPTO_VERWALTUNG in .env' in _log
      and GEHEIM['OIDC_SECRET_VERWALTUNG'] not in _log and 'docker compose up -d app' in _log, _log[-400:])
check('Client „verwaltung“: Geheimnis aus .env übernommen (Code-Austausch funktioniert, siehe Anmeldung unten), kein Platzhalter',
      clients.get('verwaltung', {}).get('secret') not in (None, '@GEHEIM_VERWALTUNG@'))
check('Stand 4: Client „bestand“ nachträglich angelegt (Schleife über alle Clients der Realm-Datei), Geheimnisse in .env erzeugt (ohne Anzeige)',
      'angelegt:  Client bestand' in _log and 'erzeugt:   OIDC_SECRET_BESTAND in .env' in _log and 'erzeugt:   OIDC_CRYPTO_BESTAND in .env' in _log
      and GEHEIM['OIDC_SECRET_BESTAND'] not in _log and 'angelegt:  Client dashboard' not in _log and 'angelegt:  Client angebot' not in _log, _log[-500:])
check('Client „bestand“: Geheimnis aus .env übernommen, kein Platzhalter, Rücksprung nur auf den eigenen Host',
      clients.get('bestand', {}).get('secret') not in (None, '@GEHEIM_BESTAND@') and clients.get('bestand', {}).get('redirectUris') == [B + '/oidc/callback'])
check('Stand 5: Client „hr“ nachträglich angelegt (Schleife über die Clients der Realm-Datei), Geheimnisse in .env erzeugt (ohne Anzeige)',
      'angelegt:  Client hr' in _log and 'erzeugt:   OIDC_SECRET_HR in .env' in _log and 'erzeugt:   OIDC_CRYPTO_HR in .env' in _log
      and GEHEIM['OIDC_SECRET_HR'] not in _log, _log[-500:])
check('Client „hr“: Geheimnis aus .env übernommen, kein Platzhalter, Rücksprung nur auf den eigenen Host',
      clients.get('hr', {}).get('secret') not in (None, '@GEHEIM_HR@') and clients.get('hr', {}).get('redirectUris') == [HR + '/oidc/callback'])
def kc_token():
    _, _, t = anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung-ci', 'password': GEHEIM['KC_ADMIN_PASSWORD']}).encode(),
        {'Content-Type': 'application/x-www-form-urlencoded'})
    return json.loads(t)['access_token']


_env = os.path.join(WORK, 'installation', '.env')
_vorher = open(_env, encoding='utf-8').read()
# Zustand wie im Betrieb nachstellen: nur die Passwort-Abfrage meldet ihre Anmeldemethode (amr), Einmalcode und Passkey
# nicht – so hatte „… | while read“ mit docker compose exec den Realm hinterlassen (doppelte Code-Abfrage)
def _ablauf():
    return json.loads(anfrage(KC + '/admin/realms/mitarbeiter/authentication/flows/mitarbeiter-browser/executions', kopf={'Authorization': 'Bearer ' + kc_token()})[2])
_geloescht = 0
for _e in _ablauf():
    if _e.get('providerId') in ('auth-otp-form', 'webauthn-authenticator') and _e.get('authenticationConfig'):
        _geloescht += anfrage(f"{KC}/admin/realms/mitarbeiter/authentication/config/{_e['authenticationConfig']}", 'DELETE', None,
                              {'Authorization': 'Bearer ' + kc_token()})[0] == 204
_vorher_amr = [e['providerId'] for e in _ablauf() if e.get('providerId') in ('auth-otp-form', 'webauthn-authenticator') and not e.get('authenticationConfig')]
check('Vorbereitung: Einmalcode und Passkey ohne gemeldete Anmeldemethode (Zustand im Betrieb)', _geloescht == 4 and len(_vorher_amr) == 4, (_geloescht, _vorher_amr))
_r = subprocess.run(['sh', 'deploy/anmeldung/konten.sh', 'realm-aktualisieren'], cwd=os.path.join(WORK, 'installation'), capture_output=True, text=True,
                    # Ausgabe stückweise wie über docker compose exec (im Betrieb gab es sonst falsche „Abbruch“-Meldungen)
                    env=dict(os.environ, KCADM=f"sh {os.path.join(REPO, 'tests', 'oidc', 'kcadm-stueckweise.sh')} env -u JAVA_TOOL_OPTIONS -u https_proxy -u HTTPS_PROXY {next(d for d in (os.path.join(WORK, x) for x in os.listdir(WORK)) if os.path.isfile(os.path.join(d, 'bin', 'kcadm.sh')))}/bin/kcadm.sh",
                             KC_SERVER=KC, KC_ADMIN_USER_TEST='verwaltung-ci', KC_ADMIN_PASSWORD_TEST=GEHEIM['KC_ADMIN_PASSWORD'],
                             KC_REALM_DATEI=os.path.join(REPO, 'tests', 'oidc', 'realm-mitarbeiter.json')))
check('realm-aktualisieren ein zweites Mal: nichts neu angelegt, .env unverändert',
      _r.returncode == 0 and 'angelegt:' not in _r.stdout and 'erzeugt:' not in _r.stdout and open(_env, encoding='utf-8').read() == _vorher, (_r.returncode, _r.stdout[-300:], _r.stderr[-300:]))
_amr = {}
for _e in _ablauf():
    if _e.get('providerId') in ('auth-username-password-form', 'auth-otp-form', 'webauthn-authenticator') and _e.get('authenticationConfig'):
        _c = json.loads(anfrage(f"{KC}/admin/realms/mitarbeiter/authentication/config/{_e['authenticationConfig']}", kopf={'Authorization': 'Bearer ' + kc_token()})[2])
        _amr.setdefault(_e['providerId'], []).append(_c['config'].get('default.reference.value'))
check('realm-aktualisieren (Eingabe wie docker compose exec mitgelesen): Anmeldemethode für ALLE Einmalcode- und Passkey-Abfragen nachgetragen',
      _amr.get('auth-otp-form') == ['otp', 'otp'] and _amr.get('webauthn-authenticator') == ['hwk', 'hwk'] and _amr.get('auth-username-password-form') == ['pwd']
      and _r.stdout.count("gesetzt:   amr 'otp'") == 2 and _r.stdout.count("gesetzt:   amr 'hwk'") == 2, (_amr, _r.stdout[-400:]))
check('realm-aktualisieren mit stückweiser Ausgabe (wie docker compose exec): keine Abbruch-Meldung', 'Abbruch' not in _r.stderr, _r.stderr[-300:])

# ── Anmeldeseite im Plattform-Design (Theme „stafl“ aus deploy/anmeldung/theme, konten.sh design-setzen) ──
THEME = os.path.join(REPO, 'deploy', 'anmeldung', 'theme', 'stafl', 'login')
_dlog = open(os.path.join(WORK, 'design-setzen.log'), encoding='utf-8').read()
check("Design: beim Start mit konten.sh design-setzen gesetzt (Realm ohne Design wie im Betrieb)", "gesetzt:   Anmeldeseite im Design 'stafl'" in _dlog, _dlog)


def design_setzen(*args):
    return subprocess.run(['sh', 'deploy/anmeldung/konten.sh', 'design-setzen', *args], cwd=os.path.join(WORK, 'installation'), capture_output=True, text=True,
                          env=dict(os.environ, KCADM=f"sh {os.path.join(REPO, 'tests', 'oidc', 'kcadm-stueckweise.sh')} env -u JAVA_TOOL_OPTIONS -u https_proxy -u HTTPS_PROXY {next(d for d in (os.path.join(WORK, x) for x in os.listdir(WORK)) if os.path.isfile(os.path.join(d, 'bin', 'kcadm.sh')))}/bin/kcadm.sh",
                                   KC_SERVER=KC, KC_ADMIN_USER_TEST='verwaltung-ci', KC_ADMIN_PASSWORD_TEST=GEHEIM['KC_ADMIN_PASSWORD']), timeout=300)


def realm_jetzt():   # eigenes Token je Abfrage (Token der Verwaltung gelten nur kurz)
    t = json.loads(anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung-ci', 'password': GEHEIM['KC_ADMIN_PASSWORD']}).encode(),
        {'Content-Type': 'application/x-www-form-urlencoded'})[2])['access_token']
    return json.loads(anfrage(KC + '/admin/realms/mitarbeiter', kopf={'Authorization': 'Bearer ' + t})[2])


def anmeldeseite():
    """Anmeldeseite von Keycloak wie ein Browser (Weiterleitung vom Dashboard)."""
    _, kopf, _ = anfrage(D + '/dashboard/', kopf=SEITE)
    jar = http.cookiejar.CookieJar()
    return anfrage(kopf.get('Location') or L, jar=jar)


_vorher = realm_jetzt()
_r = design_setzen()
check('design-setzen ein zweites Mal: unverändert (idempotent), auch mit stückweiser Ausgabe', _r.returncode == 0 and 'unverändert' in _r.stdout and 'Abbruch' not in _r.stderr,
      (_r.returncode, _r.stdout, _r.stderr[-300:]))
_r = design_setzen('standard')
_std = realm_jetzt()
code, _, text = anmeldeseite()
check('Rückfall: design-setzen standard → mitgeliefertes Design von Keycloak', _r.returncode == 0 and 'gesetzt:' in _r.stdout and _std.get('loginTheme') in (None, '', 'keycloak.v2')
      and code == 200 and '/login/stafl/' not in text and '/login/keycloak.v2/' in text, (_r.stdout, _r.stderr[-200:], _std.get('loginTheme')))
_r = design_setzen()
_r2 = design_setzen()
_nachher = realm_jetzt()
check('design-setzen danach: wieder gesetzt, zweiter Lauf unverändert', _r.returncode == 0 and 'gesetzt:' in _r.stdout and _r2.returncode == 0 and 'unverändert' in _r2.stdout
      and _nachher.get('loginTheme') == 'stafl', (_r.stdout, _r2.stdout, _nachher.get('loginTheme')))
check('design-setzen ändert nur das Design (Brute-Force-Schutz, Einmalcode-Richtlinie, Abläufe, Sitzungen unverändert)',
      {k: v for k, v in _vorher.items() if k != 'loginTheme'} == {k: v for k, v in _nachher.items() if k != 'loginTheme'},
      sorted(k for k in set(_vorher) | set(_nachher) if k != 'loginTheme' and _vorher.get(k) != _nachher.get(k)))
_r = design_setzen('irgendwas')
check('design-setzen mit unbekanntem Wert abgelehnt', _r.returncode == 1 and 'Aufruf' in _r.stderr, (_r.returncode, _r.stderr[-200:]))
code, _, text = anmeldeseite()
_css = re.search(r'href="(/resources/[^"]+/login/stafl/css/stafl\.css)"', text)
check('Anmeldeseite liefert das STAFL-Stylesheet und das Skript für den Einmalcode, Sprache Deutsch',
      code == 200 and bool(_css) and re.search(r'src="/resources/[^"]+/login/stafl/js/stafl-otp\.js"', text) and 'lang="de"' in text
      and 'class="stafl-sr"' in text and '>Plattform<' not in text and 'Anmelden' in text, text[:300])
code, kopf, css = anfrage(L + _css.group(1)) if _css else (0, {}, '')
check('Stylesheet: Farben des Plattform-Designs (Grund, Bordeaux, Farbflächen ohne Rot, Glas, dunkel)',
      code == 200 and all(x in css for x in ('#f4f1ee', '#121011', '#8c1d2c', '#a3202f', 'rgba(143, 167, 196', 'rgba(226, 165, 74', 'rgba(63, 122, 90',
                                            '--st-filter: blur(30px) saturate(180%)', 'backdrop-filter: var(--st-filter)', 'prefers-color-scheme: dark', '28px', '-apple-system')), code)
check('Stylesheet: Browser fragen spätestens nach einer Stunde neu (Änderungen am Design kommen an)', 'max-age=3600' in (kopf.get('Cache-Control') or ''), kopf.get('Cache-Control'))
_res = _css.group(1).rsplit('/css/', 1)[0] if _css else ''
for _quelle, _ziel in (('app/assets/logo-standard-fleisch-kopf.png', '/img/logo-standard-fleisch-kopf.png'), ('app/assets/icons/favicon-32.png', '/img/favicon.ico')):
    _req = urllib.request.Request(L + _res + _ziel)
    with urllib.request.urlopen(_req, context=TLS, timeout=30) as _antwort:
        _bild = _antwort.read()
    check(f'Logo/Symbol der Anmeldeseite ist dieselbe Datei wie im Dashboard ({_quelle})', _bild == open(os.path.join(REPO, _quelle), 'rb').read() and len(_bild) > 500)
_kc_version = re.search(r'^KC_VERSION=(\S+)', open(os.path.join(REPO, 'tests', 'oidc', 'umgebung.sh'), encoding='utf-8').read(), re.M).group(1)
check('eigene Vorlagen beruhen auf der verwendeten Keycloak-Version (bei Updates mit der neuen Fassung vergleichen)',
      all(f'keycloak.v2 aus Keycloak {_kc_version}' in open(os.path.join(THEME, f), encoding='utf-8').read() for f in ('login-otp.ftl', 'login-config-totp.ftl'))
      and f'Keycloak {_kc_version}' in open(os.path.join(THEME, 'theme.properties'), encoding='utf-8').read(), _kc_version)

# ── Ohne Anmeldung ──
code, kopf, _ = anfrage(D + '/dashboard/', kopf=SEITE)
ziel = urllib.parse.urlparse(kopf.get('Location') or '')
q = urllib.parse.parse_qs(ziel.query)
check('Dashboard ohne Anmeldung → Weiterleitung zu Keycloak', code in (302, 303) and ziel.netloc == f'login.stafl.test:{PORT}', kopf.get('Location'))
check('… mit state, nonce und PKCE (S256)', q.get('state') and q.get('nonce') and q.get('code_challenge') and q.get('code_challenge_method') == ['S256'], q)
check('… an die eigene, registrierte Rücksprungadresse', q.get('redirect_uri') == [D + '/oidc/callback'], q.get('redirect_uri'))
code, kopf, text = anfrage(D + '/api/?action=status')
check('Schnittstelle ohne Anmeldung: 401 statt Weiterleitung', code == 401, code)
for k in ({'OIDC_CLAIM_sub': 'x', 'OIDC-CLAIM-sub': 'x', 'OIDC_CLAIM_preferred_username': 'admin'}, {'Remote-User': 'admin', 'X-Remote-User': 'admin'},
          {'X-Forwarded-User': 'admin', 'X-Auth-Request-User': 'admin'}):
    check(f'untergeschobene Kopfzeilen melden nicht an: {", ".join(k)}', anfrage(D + '/api/?action=status', kopf=k)[0] == 401)
check('abgemeldet-Seite und Stylesheets ohne Anmeldung erreichbar', anfrage(D + '/dashboard/abgemeldet.html')[0] == 200 and anfrage(D + '/assets/app.css')[0] == 200)
check('Mitarbeiter-Eingabe (angebot) ohne Anmeldung → Keycloak', anfrage(A + '/admin/', kopf=SEITE)[0] in (302, 303))
code, kopf, _ = anfrage(W + '/admin/', kopf=SEITE)
check('Verwaltung ohne Anmeldung → Keycloak, eigener Client und eigene Rücksprungadresse',
      code in (302, 303) and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('client_id') == ['verwaltung']
      and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('redirect_uri') == [W + '/oidc/callback'], kopf.get('Location'))
check('Verwaltung: Schnittstelle ohne Anmeldung 401', anfrage(W + '/api/?action=status')[0] == 401)
code, kopf, _ = anfrage(B + '/admin/', kopf=SEITE)
check('Bestand ohne Anmeldung → Keycloak, eigener Client und eigene Rücksprungadresse',
      code in (302, 303) and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('client_id') == ['bestand']
      and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('redirect_uri') == [B + '/oidc/callback'], kopf.get('Location'))
check('Bestand: Schnittstelle ohne Anmeldung 401', anfrage(B + '/api/?action=status')[0] == 401)
code, kopf, _ = anfrage(B + '/', kopf=SEITE)
check('Bestand: Startadresse führt in den Eingabebereich', code == 302 and (kopf.get('Location') or '').endswith('/admin/'), (code, kopf.get('Location')))
for pfad in ('/import/', '/import'):
    code, kopf, _ = anfrage(W + pfad, kopf=SEITE)
    check(f'Import-Adresse {pfad} (Verwaltungs-Host): Weiterleitung in die Importzentrale', code == 302 and (kopf.get('Location') or '').endswith('/admin/?ansicht=importe&nur=import'), (code, kopf.get('Location')))
code, kopf, _ = anfrage(B + '/import/', kopf=SEITE)
check('Import-Adresse nur auf dem Verwaltungs-Host (Bestand: keine Weiterleitung in die Importzentrale)', 'ansicht=importe' not in (kopf.get('Location') or ''), (code, kopf.get('Location')))
code, kopf, _ = anfrage(HR + '/module/hr/', kopf=SEITE)
check('HR ohne Anmeldung → Keycloak, eigener Client und eigene Rücksprungadresse',
      code in (302, 303) and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('client_id') == ['hr']
      and urllib.parse.parse_qs(urllib.parse.urlparse(kopf.get('Location') or '').query).get('redirect_uri') == [HR + '/oidc/callback'], kopf.get('Location'))
check('HR: Schnittstelle ohne Anmeldung 401 (auch hr_start)', anfrage(HR + '/api/?action=status')[0] == 401 and anfrage(HR + '/api/?action=hr_start')[0] == 401)
for pfad in ('/', '/admin/', '/admin'):
    code, kopf, _ = anfrage(HR + pfad, kopf=SEITE)
    check(f'HR {pfad}: Weiterleitung zur Urlaubsverwaltung (/module/hr/), kein Eingabebereich auf dem HR-Host',
          code == 302 and (kopf.get('Location') or '').endswith('/module/hr/'), (code, kopf.get('Location')))
check('HR: Stylesheets ohne Anmeldung (Abmeldeseite)', anfrage(HR + '/assets/app.css')[0] == 200 and anfrage(HR + '/dashboard/abgemeldet.html')[0] == 200)
for h in (D, A, W, B, HR):
    code, kopf, text = anfrage(h + '/oidc/callback?' + urllib.parse.urlencode({'state': 'abgelaufen-oder-fremder-tab', 'code': 'x'}), kopf=SEITE)
    check(f'Rückkehr von der Anmeldung ohne passenden Zustand ({h.split("//")[1].split(".")[0]}): Weiterleitung zum Host statt „Bad Request“',
          code in (302, 303) and (kopf.get('Location') or '').startswith(h + '/'), (code, kopf.get('Location'), text[:80]))

fehler = []


def client_attribute(cid, **attr):
    """Attribute eines Clients in Keycloak ändern (Testvorbereitung über die lokale Verwaltungsschnittstelle)."""
    t = kc_token(); kopf = {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json'}
    c = clients[cid]
    _, _, text = anfrage(f"{KC}/admin/realms/mitarbeiter/clients/{c['id']}", kopf=kopf)
    c = json.loads(text); c['attributes'].update(attr)
    return anfrage(f"{KC}/admin/realms/mitarbeiter/clients/{c['id']}", 'PUT', json.dumps(c).encode(), kopf)[0]


def bestaetigung_abgelaufen(ctx, host):
    """Nachgestellt: die Bestätigung sensibler Aktionen ist abgelaufen (sonst 5 Minuten warten) – PHP-Sitzungsdatei."""
    sid = kekse(ctx, host)['__Host-WA_ADMIN']['value']
    pfad = os.path.join(WORK, 'sessions', 'sess_' + sid)
    with open(pfad, encoding='utf-8') as f:
        roh = f.read()
    neu = re.sub(r'adminConfirmedAt\|i:\d+;', 'adminConfirmedAt|i:0;', roh)
    with open(pfad, 'w', encoding='utf-8') as f:
        f.write(neu)
    return neu != roh


def anmelden(pg, wer, otp=True):
    pg.wait_for_selector('#username'); pg.fill('#username', wer); pg.fill('#password', NUTZER[wer][0]); pg.click('#kc-login')
    if otp:
        pg.wait_for_selector('#otp'); pg.fill('#otp', totp(NUTZER[wer][1])); pg.click('#kc-login')


FEHLVERSUCH = [0.0]   # Zeitpunkt des letzten absichtlichen Fehlversuchs


def fehlversuch_abstand():
    """Keycloak sperrt 60 s, wenn zwei Fehlversuche weniger als 1 s (quickLoginCheckMilliSeconds) auseinanderliegen – der
    Test wartet daher bis 1,2 s nach dem letzten absichtlichen Fehlversuch (Zustand der Uhr, keine feste Pause)."""
    while time.time() - FEHLVERSUCH[0] < 1.2:
        time.sleep(0.05)


def otp_eingeben(pg, wer):
    """Einmalcode eingeben – immer ein noch nicht verwendeter Code (totp), daher ohne Fehlversuch."""
    pg.wait_for_selector('#otp'); pg.fill('#otp', totp(NUTZER[wer][1])); pg.click('#kc-login')
    pg.wait_for_load_state()


def eigene_seite(pg):
    pg.on('pageerror', lambda e: fehler.append(f'{pg.url}: {e}') if '.stafl.test' in pg.url and 'login.' not in pg.url else None)
    return pg


def kekse(ctx, host):
    return {c['name']: c for c in ctx.cookies() if c['domain'].lstrip('.') == host}


with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--proxy-server=direct://', '--proxy-bypass-list=*'])   # Testhosts direkt, nie über einen Proxy
    ctx = br.new_context(ignore_https_errors=True, viewport={'width': 1280, 'height': 900})
    pg = eigene_seite(ctx.new_page())

    # ── Skript des Designs: Formular kommt beim Server nur einmal an, auch wenn es mehrmals kurz nacheinander abgeschickt wird
    #    (langsamer Server nachgestellt; ohne das Skript kommen alle Absendungen an → bei Keycloak Sperre für 60 s) ──
    import http.server, socketserver, threading
    _ankunft = []
    _skript = open(os.path.join(REPO, 'deploy', 'anmeldung', 'theme', 'stafl', 'login', 'resources', 'js', 'stafl-otp.js')).read()
    _seite = {'html': ''}

    class _Langsam(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers(); self.wfile.write(_seite['html'].encode())

        def do_POST(self):
            _ankunft.append(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
            time.sleep(0.8)
            try:
                self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers(); self.wfile.write(b'<p id="fertig">ok</p>')
            except OSError:
                pass   # Browser hat die frühere Absendung abgebrochen

        def log_message(self, *a):
            pass

    class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    _srv = _Server(('127.0.0.1', 0), _Langsam); threading.Thread(target=_srv.serve_forever, daemon=True).start()
    _form = ('<!doctype html><html lang="de"><body><form id="f" method="post" action="/anmelden" onsubmit="login.disabled = true; return true;">'
             '<input id="otp" name="otp" data-stafl-otp pattern="[0-9]{6}"><button id="kc-login" name="login" type="submit">Anmelden</button></form>%s</body></html>')
    _zahl = {}
    for _mit in (True, False):
        _seite['html'] = _form % (f'<script>{_skript}</script>' if _mit else ''); _ankunft.clear()
        _pz = br.new_page(); _pz.goto(f'http://127.0.0.1:{_srv.server_address[1]}/')
        _pz.fill('#otp', '12 34 56' if _mit else '123456')
        _pz.evaluate("() => { const f = document.querySelector('#f'); f.requestSubmit(); setTimeout(() => f.requestSubmit(), 150); setTimeout(() => f.requestSubmit(), 300); }")
        _pz.wait_for_selector('#fertig', timeout=10000)
        _zahl[_mit] = (len(_ankunft), list(_ankunft))
        _pz.close()
    _srv.shutdown()
    check('Skript: dreimal kurz nacheinander abgeschickt → beim Server genau einmal, Code ohne Leerzeichen', _zahl[True][0] == 1 and 'otp=123456' in _zahl[True][1][0], _zahl[True])
    check('… Gegenprobe ohne Skript: alle Absendungen kommen an (so entstand die Sperre)', _zahl[False][0] >= 2, _zahl[False])

    # ── Anmeldeseite im Plattform-Design: hell und dunkel, 390 px, keine JavaScript-Fehler ──
    login_fehler = []
    for _schema, _grund in (('light', 'rgb(244, 241, 238)'), ('dark', 'rgb(18, 16, 17)')):
        _ctx = br.new_context(ignore_https_errors=True, viewport={'width': 390, 'height': 844}, color_scheme=_schema)
        _pg = _ctx.new_page(); _pg.on('pageerror', lambda e: login_fehler.append(str(e)))
        _pg.on('console', lambda m: login_fehler.append(m.text) if m.type == 'error' else None)
        _pg.goto(D + '/'); _pg.wait_for_selector('#username')
        _stil = _pg.evaluate("""() => { const k = getComputedStyle(document.querySelector('.pf-v5-c-login__main')); return {
            grund: getComputedStyle(document.body).backgroundColor, radius: k.borderTopLeftRadius, filter: k.backdropFilter || k.webkitBackdropFilter,
            logo: getComputedStyle(document.querySelector('#kc-header-wrapper'), '::before').backgroundImage,
            knopf: getComputedStyle(document.querySelector('#kc-login')).backgroundImage, breit: document.documentElement.scrollWidth > innerWidth }; }""")
        check(f'Anmeldeseite {_schema}, 390 px: Grund, Glaskarte, Logo, Bordeaux-Knopf, kein waagerechtes Scrollen',
              _stil['grund'] == _grund and _stil['radius'] in ('24px', '28px') and 'blur' in (_stil['filter'] or '') and 'logo-standard-fleisch-kopf.png' in _stil['logo']
              and 'rgb(163, 32, 47)' in _stil['knopf'] and not _stil['breit'], _stil)
        _pg.screenshot(path=os.path.join(SH, f'oidc_anmeldung_{_schema}_390.png'), full_page=True)
        _ctx.close()

    # ── Anmeldung erika (Bearbeiterin, Einmalcode freiwillig eingerichtet): wird abgefragt ──
    pg.on('pageerror', lambda e: login_fehler.append(f'{pg.url}: {e}') if pg.url.startswith(L) else None)
    pg.goto(D + '/'); pg.wait_for_selector('#username')
    check('Anmeldeseite von Keycloak (login.stafl.test)', pg.url.startswith(L + '/realms/mitarbeiter/'), pg.url)
    pg.screenshot(path=os.path.join(SH, 'oidc_anmeldung_1280.png'))
    pg.fill('#username', 'erika'); pg.fill('#password', NUTZER['erika'][0]); pg.click('#kc-login')
    pg.wait_for_selector('#otp')
    check('nach dem Passwort wird der Einmalcode verlangt (eingerichtet = wird abgefragt)', pg.is_visible('#otp'))
    _otp = pg.evaluate("""() => { const f = document.querySelector('#otp'); return { ac: f.autocomplete, im: f.inputMode, muster: f.pattern, fokus: document.activeElement === f,
        label: document.querySelector('label[for=otp]').textContent.trim(), hinweis: document.querySelector('#stafl-otp-hinweis').textContent }; }""")
    check('Einmalcode-Feld: autocomplete=one-time-code, Ziffernblock, 6 Ziffern, Fokus, deutscher Hinweis',
          _otp['ac'] == 'one-time-code' and _otp['im'] == 'numeric' and _otp['muster'] == '[0-9]{6}' and _otp['fokus'] and _otp['label'] == 'Einmalcode'
          and 'STAFL-Plattform' in _otp['hinweis'] and '30 Sekunden' in _otp['hinweis'], _otp)
    pg.screenshot(path=os.path.join(SH, 'oidc_einmalcode_1280.png'))
    pg.fill('#otp', '000000'); pg.click('#kc-login'); pg.wait_for_selector('#otp'); FEHLVERSUCH[0] = time.time()
    check('falscher Einmalcode: keine Anmeldung', pg.url.startswith(L))
    _meldung = pg.text_content('#input-error-otp')
    check('falscher Einmalcode: verständliche deutsche Meldung (nur einmal gültig, auf neuen Code warten, Sperre nach Fehlversuchen)',
          'nicht angenommen' in _meldung and 'nur einmal' in _meldung and 'neuen Code' in _meldung and 'gesperrt' in _meldung, _meldung)
    _nach = pg.evaluate("() => ({ leer: document.querySelector('#otp').value === '', fokus: document.activeElement === document.querySelector('#otp'),"
                        " ungueltig: document.querySelector('#otp').getAttribute('aria-invalid'), sichtbar: !!document.querySelector('#input-error-otp').offsetParent })")
    check('… danach: Feld leer und wieder im Fokus, als fehlerhaft markiert, Meldung sichtbar', _nach['leer'] and _nach['fokus'] and _nach['ungueltig'] == 'true' and _nach['sichtbar'], _nach)
    pg.screenshot(path=os.path.join(SH, 'oidc_einmalcode_fehler_1280.png'))
    # Doppelt abgeschickt (Eingabetaste, noch einmal, Klick – in einem Zug): nur ein Fehlversuch. Zwei Fehlversuche in weniger
    # als einer Sekunde sperren das Konto 60 s (quickLoginCheckMilliSeconds), danach gälte auch der richtige Code als falsch.
    _eid = json.loads(anfrage(KC + '/admin/realms/mitarbeiter/users?exact=true&username=erika', kopf={'Authorization': 'Bearer ' + kc_token()})[2])[0]['id']
    _bf = lambda: json.loads(anfrage(f'{KC}/admin/realms/mitarbeiter/attack-detection/brute-force/users/{_eid}', kopf={'Authorization': 'Bearer ' + kc_token()})[2])
    _vor = _bf().get('numFailures', 0)
    fehlversuch_abstand()
    pg.fill('#otp', '000000')
    with pg.expect_navigation():
        pg.evaluate("() => { const f = document.querySelector('#otp').form; f.requestSubmit(); f.requestSubmit(); document.querySelector('#kc-login').click(); }")
    pg.wait_for_selector('#input-error-otp'); FEHLVERSUCH[0] = time.time()
    _nach_bf = _bf()
    check('Formular dreimal schnell abgeschickt: nur ein Fehlversuch, keine Sperre', _nach_bf.get('numFailures', 0) == _vor + 1 and not _nach_bf.get('disabled'), (_vor, _nach_bf))
    # Keycloak selbst nimmt „123 456“ nicht an (Fehlversuch) – deshalb bereinigt das Skript des Designs die Eingabe
    _c = totp(NUTZER['erika'][1])
    fehlversuch_abstand()
    pg.evaluate("c => { const f = document.querySelector('#otp'); f.value = c.slice(0, 3) + ' ' + c.slice(3); f.form.noValidate = true; f.form.submit(); }", _c)
    pg.wait_for_selector('#otp'); FEHLVERSUCH[0] = time.time()
    fehlversuch_abstand()
    check('ohne Skript: Keycloak lehnt einen Code mit Leerzeichen ab (Grund für die Bereinigung im Design)', pg.url.startswith(L) and pg.locator('#input-error-otp').count() == 1)
    pg.evaluate("() => { const f = document.querySelector('#otp'); f.value = '12 34 56'; f.dispatchEvent(new Event('input', { bubbles: true })); }")
    _ohne_ohne = pg.input_value('#otp')
    pg.fill('#otp', ''); pg.focus('#otp'); pg.keyboard.insert_text(_c[:3] + ' ' + _c[3:])
    check('Eingabe „123 456“ (wie in der App angezeigt): Leerzeichen entfernt', pg.input_value('#otp') == _c and _ohne_ohne == '123456', (pg.input_value('#otp'), _ohne_ohne))
    pg.click('#kc-login')
    pg.wait_for_selector('#db-grid .db-tile')
    check('… und angemeldet (derselbe Code, keine Änderung an der Prüfung)', pg.url.startswith(D + '/dashboard/'), pg.url)
    # Häufigster Fall in der Produktion: derselbe Code kurz danach noch einmal (zweiter Tab, Neuladen) – Keycloak lehnt ab,
    # die Seite sagt, warum; mit dem nächsten Code (Eingabetaste statt Klick) klappt es
    _c2 = br.new_context(ignore_https_errors=True, viewport={'width': 390, 'height': 844}); _p2 = eigene_seite(_c2.new_page())
    _p2.on('pageerror', lambda e: login_fehler.append(str(e)))
    _p2.goto(D + '/'); _p2.wait_for_selector('#username'); _p2.fill('#username', 'erika'); _p2.fill('#password', NUTZER['erika'][0]); _p2.keyboard.press('Enter')
    _p2.wait_for_selector('#otp'); _p2.fill('#otp', _c); _p2.keyboard.press('Enter'); _p2.wait_for_selector('#input-error-otp')
    check('derselbe Code ein zweites Mal: abgelehnt mit Hinweis „nur einmal … neuen Code“', _p2.url.startswith(L) and 'nur einmal' in _p2.text_content('#input-error-otp'),
          _p2.text_content('#input-error-otp'))
    _p2.screenshot(path=os.path.join(SH, 'oidc_einmalcode_doppelt_390.png'), full_page=True)
    _p2.fill('#otp', totp(NUTZER['erika'][1])); _p2.keyboard.press('Enter'); _p2.wait_for_selector('#db-grid .db-tile')
    check('… mit dem nächsten Code und der Eingabetaste angemeldet', _p2.url.startswith(D + '/dashboard/'), _p2.url)
    _c2.close()
    check('nach der Anmeldung: Dashboard auf dashboard.stafl.test', pg.url.startswith(D + '/dashboard/'), pg.url)
    check('Dashboard zeigt den Namen aus unserem Mitarbeiterkonto', 'Erika Editor' in pg.text_content('#db-user'), pg.text_content('#db-user'))
    check('elf Kacheln, Angebot verfügbar', pg.locator('#db-grid .db-tile').count() == 11 and pg.text_content('[data-modul="angebot"] .db-badge') == 'Verfügbar')
    check('Kachel Verwaltung verfügbar (freigegeben)', pg.text_content('[data-modul="verwaltung"] .db-badge') == 'Verfügbar'
          and pg.get_attribute('[data-modul="verwaltung"]', 'href') is not None, pg.text_content('[data-modul="verwaltung"] .db-badge'))
    check('Kacheln Bestand, Import und HR verfügbar (freigegeben), 5 von 11', all(pg.text_content(f'[data-modul="{m}"] .db-badge') == 'Verfügbar'
          and pg.get_attribute(f'[data-modul="{m}"]', 'href') for m in ('bestand', 'import', 'hr')) and '5 von 11' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    check('Kachel HR führt zur Urlaubsverwaltung (Testserver: Pfad /module/hr/)', pg.get_attribute('[data-modul="hr"]', 'href') == '/module/hr/', pg.get_attribute('[data-modul="hr"]', 'href'))
    pg.screenshot(path=os.path.join(SH, 'oidc_dashboard_1280.png'), full_page=True)
    k = kekse(ctx, f'dashboard.stafl.test')
    check('Cookies des Dashboards nur mit __Host-Präfix (Secure, Pfad /, ohne Domain)',
          k and all(n.startswith('__Host-') and c['secure'] and c['path'] == '/' for n, c in k.items()), sorted(k))
    check('Sitzungs-Cookies HttpOnly', k.get('__Host-oidc_sitzung', {}).get('httpOnly') and k.get('__Host-WA_ADMIN', {}).get('httpOnly'), sorted(k))
    check('kein Cookie für alle Subdomains (.stafl.test)', not [c for c in ctx.cookies() if c['domain'] in ('.stafl.test', 'stafl.test')])
    check('Verknüpfung: Mitarbeiterkonto erika trägt die Keycloak-Kennung', bool(nutzer_roh()['erika'].get('oidcSub')))

    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('status: angemeldet, zentrale Anmeldung, kein eigener 2FA-Zwang', st.get('loggedIn') and st['user'].get('zentral') and not st['user'].get('needTwofa'), st.get('user'))
    csrf = st.get('csrf', '')
    js_post = "([a, b, t]) => fetch('../api/?action=' + a, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': t}, body: JSON.stringify(b)}).then(async r => [r.status, await r.json().catch(() => ({}))])"
    for a in ('login', 'login_2fa', 'setup', 'change_password', 'twofa_begin', 'passkey_begin', 'passkey_login_begin', 'reauth', 'kunde_login'):
        code, j = pg.evaluate(js_post, [a, {'username': 'admin', 'password': PW_ALT}, csrf])
        check(f'eigenes Anmeldeverfahren auf Keycloak-Host gesperrt: {a} → 403', code == 403 and 'zentral' in j.get('error', ''), (code, j))
    code, j = pg.evaluate("t => fetch('../api/?action=security_status', {headers: {'X-CSRF-Token': t}}).then(async r => [r.status, await r.json()])", csrf)
    check('Rechte bleiben bei uns: Bearbeiterin darf keine Sicherheitseinstellungen lesen (403)', code == 403, (code, j))
    code, _ = pg.evaluate(js_post, ['user_save', {'id': '', 'name': 'X', 'username': 'x', 'role': 'admin', 'active': True}, csrf])
    check('Rechte bleiben bei uns: Bearbeiterin legt keine Nutzer an', code == 403, code)

    # ── Single Sign-on in die zweite Anwendung, aber eigene Sitzung je Host ──
    pa = eigene_seite(ctx.new_page())
    pa.goto(A + '/admin/'); pa.wait_for_function("location.host.startsWith('angebot.')")
    sta = pa.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('Single Sign-on: Mitarbeiter-Eingabe ohne erneute Eingabe angemeldet', sta.get('loggedIn') and sta['user']['username'] == 'erika', sta.get('user'))
    ka = kekse(ctx, 'angebot.stafl.test')
    check('eigene Sitzung je Host: andere Cookie-Werte auf angebot', ka.get('__Host-oidc_sitzung', {}).get('value') not in (None, k.get('__Host-oidc_sitzung', {}).get('value'))
          and ka.get('__Host-WA_ADMIN', {}).get('value') != k.get('__Host-WA_ADMIN', {}).get('value'), sorted(ka))
    pa.wait_for_selector('#screen-editor:not([hidden]), #screen-auth:not([hidden])', timeout=30000)
    check('Mitarbeiter-Eingabe zeigt den Editor (keine eigene Anmeldemaske)', pa.is_visible('#screen-editor'))
    pa.wait_for_function("document.querySelector('#vt-master').hidden && !document.querySelector('#vt-edit').hidden")
    sicht_a = pa.evaluate("[...document.querySelectorAll('[id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))")
    check('Angebot (angebot.stafl.test): nur Angebotsbereiche, keine Verwaltung (Stammdaten, Kunden, Import …) und keine Bestandsliste (wandert ins Bestandsmodul)',
          'edit' in sicht_a and not {'stock', 'master', 'vkgruppen', 'kunden', 'gruppen', 'vertreter', 'importe', 'auswertung', 'users', 'log', 'sec'} & set(sicht_a), sicht_a)
    pa.goto(A + '/admin/?ansicht=stock'); pa.wait_for_selector('#screen-editor:not([hidden])'); pa.wait_for_function("!document.querySelector('#vt-edit').hidden")
    check('Angebot: Bestandsliste auch über die Adresse nicht zu öffnen (?ansicht=stock → Angebot bearbeiten)', pa.is_hidden('#view-stock') and pa.is_visible('#view-edit'))
    check('Angebot: Bestandsdaten im Angebotseditor bleiben (Bestandsliste über die Schnittstelle lesbar)', pa.evaluate("fetch('../api/?action=stock').then(r => r.status)") == 200)
    # Sitzung des Dashboards auf dem anderen Host untergeschoben
    fremd = br.new_context(ignore_https_errors=True)
    fremd.add_cookies([{'name': n, 'value': c['value'], 'url': A + '/'} for n, c in k.items()])
    pf = fremd.new_page(); pf.goto(A + '/dashboard/abgemeldet.html')
    code = pf.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Sitzung des Dashboards gilt nicht auf angebot (GR-108)', code == 401, code)
    fremd.close()

    # ── Verwaltung unter eigener Adresse: Single Sign-on, eigene Sitzung, nur Verwaltungsbereiche (Rechte unverändert) ──
    pv = eigene_seite(ctx.new_page())
    pv.goto(W + '/'); pv.wait_for_selector('#screen-editor:not([hidden]), #screen-auth:not([hidden])', timeout=30000)
    check('Verwaltung: Single Sign-on, Startadresse führt in den Eingabebereich', pv.url == W + '/admin/' and pv.is_visible('#screen-editor'), pv.url)
    stv = pv.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('Verwaltung: Bereich kommt vom Webserver (verwaltung.verwaltung)', stv.get('loggedIn') and stv['user'].get('bereich') == 'verwaltung.verwaltung', stv.get('user'))
    check('Angebot: Bereich angebot.eingabe', sta['user'].get('bereich') == 'angebot.eingabe', sta.get('user'))
    kv = kekse(ctx, 'verwaltung.stafl.test')
    check('Verwaltung: eigene Sitzung (andere Cookie-Werte als angebot)', kv.get('__Host-oidc_sitzung', {}).get('value') not in (None, ka.get('__Host-oidc_sitzung', {}).get('value'))
          and kv.get('__Host-WA_ADMIN', {}).get('value') not in (None, ka.get('__Host-WA_ADMIN', {}).get('value')), sorted(kv))
    pv.wait_for_function("!document.querySelector('#vt-master').hidden")
    check('Verwaltung: Überschrift und Titel', pv.text_content('#topbar h1') == 'Verwaltung' and pv.title().startswith('Verwaltung'), (pv.text_content('#topbar h1'), pv.title()))
    sichtbar = pv.evaluate("[...document.querySelectorAll('[id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))")
    check('Verwaltung: nur Verwaltungsbereiche (kein Angebot, Bestand, Einkauf, Bestellungen); Bearbeiterin ohne Nutzer/Sicherheit',
          'master' in sichtbar and not {'edit', 'einzel', 'hist', 'stock', 'einkauf', 'orders', 'angebote', 'users', 'sec', 'schutz', 'mail'} & set(sichtbar), sichtbar)
    check('Verwaltung: erster erlaubter Bereich geöffnet (nicht der Angebotseditor)', pv.is_hidden('#view-edit') and pv.is_visible('#view-master'))
    check('Verwaltung: keine Angebotsaktionen in der Kopfzeile (Veröffentlichen, Entwurfsstand, Angebotsseite)',
          pv.is_hidden('#btn-publish') and pv.is_hidden('#save-state') and pv.is_hidden('#btn-site') and pv.is_hidden('#btn-send'))
    check('Angebot: Kopfzeile unverändert (Veröffentlichen sichtbar)', pa.is_visible('#btn-publish') and pa.text_content('#topbar h1') == 'Eingabebereich')
    # Rückweg zum Dashboard in der Kopfzeile (Adresse vom Webserver: WA_DASHBOARD, sonst https://dashboard-stafl.de/)
    for name, seite in (('Angebot', pa), ('Verwaltung', pv)):
        check(f'{name}: Knopf „Dashboard“ oben sichtbar, führt zum Dashboard-Host', seite.is_visible('#btn-dashboard')
              and seite.get_attribute('#btn-dashboard', 'href') == D + '/' and seite.text_content('#btn-dashboard').strip() == 'Dashboard',
              (seite.is_visible('#btn-dashboard'), seite.get_attribute('#btn-dashboard', 'href')))
    check('Angebot: Adresse des Dashboards kommt vom Server', sta['user'].get('dashboard') == D + '/', sta['user'].get('dashboard'))
    pz = eigene_seite(ctx.new_page())
    pz.goto(A + '/admin/'); pz.wait_for_selector('#btn-dashboard:not([hidden])', timeout=30000)
    pz.click('#btn-dashboard'); pz.wait_for_selector('#db-grid .db-tile', timeout=30000)
    check('Klick auf „Dashboard“: zurück im Dashboard, ohne erneute Anmeldung', pz.url in (D + '/', D + '/dashboard/'), pz.url)
    pz.close()
    code, _ = pv.evaluate(js_post.replace("'../api/", "'/api/"), ['user_save', {'id': '', 'name': 'X', 'username': 'x', 'role': 'admin', 'active': True}, stv.get('csrf', '')])
    check('Verwaltung: Rechte bleiben serverseitig (Bearbeiterin legt keine Nutzer an)', code == 403, code)
    pv.screenshot(path=os.path.join(SH, 'oidc_verwaltung_1280.png'))
    pv.set_viewport_size({'width': 390, 'height': 860}); pv.reload(); pv.wait_for_selector('#screen-editor:not([hidden])')
    check('Verwaltung 390 px: kein waagerechtes Scrollen', not pv.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    zb = pv.locator('#btn-dashboard').bounding_box()
    check('Verwaltung 390 px: Dashboard-Knopf als Symbol sichtbar und mindestens 36 px groß', pv.is_visible('#btn-dashboard') and zb and zb['x'] >= 0
          and zb['width'] >= 36 and zb['height'] >= 36 and zb['x'] + zb['width'] <= 390, zb)
    pv.screenshot(path=os.path.join(SH, 'oidc_verwaltung_390.png'))
    pv.set_viewport_size({'width': 1280, 'height': 900})
    # Import-Kachel: /import/ auf dem Verwaltungs-Host öffnet die Importzentrale (Single Sign-on)
    pv.goto(W + '/import/'); pv.wait_for_selector('#view-importe:not([hidden])')
    check('Import-Adresse öffnet den Eingabebereich in der Importzentrale', pv.url == W + '/admin/?ansicht=importe&nur=import' and pv.is_hidden('#view-master')
          and pv.get_attribute('#vt-importe', 'aria-selected') == 'true', pv.url)
    pv.screenshot(path=os.path.join(SH, 'oidc_import_1280.png'))
    pv.goto(W + '/admin/#importe'); pv.wait_for_selector('#view-importe:not([hidden])')
    check('Ansicht auch über #importe', pv.is_visible('#view-importe'))
    pv.goto(W + '/admin/?ansicht=edit'); pv.wait_for_selector('#view-master:not([hidden])')
    check('nicht erlaubte Ansicht in der Adresse wird ignoriert (Verwaltung: ?ansicht=edit → erster Verwaltungsbereich)', pv.is_hidden('#view-edit') and pv.is_visible('#view-master'))

    # ── Bestand unter eigener Adresse: Single Sign-on, eigene Sitzung, nur die Bestandsliste (Rechte unverändert) ──
    pb = eigene_seite(ctx.new_page())
    pb.goto(B + '/'); pb.wait_for_selector('#screen-editor:not([hidden]), #screen-auth:not([hidden])', timeout=30000)
    check('Bestand: Single Sign-on, Startadresse führt in den Eingabebereich', pb.url == B + '/admin/' and pb.is_visible('#screen-editor'), pb.url)
    stb = pb.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('Bestand: Bereich kommt vom Webserver (bestand.intern)', stb.get('loggedIn') and stb['user'].get('bereich') == 'bestand.intern', stb.get('user'))
    kb = kekse(ctx, 'bestand.stafl.test')
    check('Bestand: eigene Sitzung (andere Cookie-Werte als angebot und verwaltung, nur __Host-)',
          kb.get('__Host-oidc_sitzung', {}).get('value') not in (None, ka.get('__Host-oidc_sitzung', {}).get('value'), kv.get('__Host-oidc_sitzung', {}).get('value'))
          and kb.get('__Host-WA_ADMIN', {}).get('value') not in (None, ka.get('__Host-WA_ADMIN', {}).get('value'), kv.get('__Host-WA_ADMIN', {}).get('value'))
          and all(n.startswith('__Host-') for n in kb), sorted(kb))
    pb.wait_for_selector('#view-stock:not([hidden])')
    sicht_b = pb.evaluate("[...document.querySelectorAll('.side-tabs [id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))")
    check('Bestand: nur die Bestandsliste (kein Angebot, Einkauf, Stammdaten, Import …)', sicht_b == ['stock'], sicht_b)
    check('Bestand: Bestandsliste geöffnet, Überschrift und Titel', pb.is_hidden('#view-edit') and pb.text_content('#topbar h1') == 'Bestand' and pb.title().startswith('Bestand'),
          (pb.text_content('#topbar h1'), pb.title()))
    check('Bestand: keine Angebotsaktionen in der Kopfzeile (Veröffentlichen, Entwurfsstand, Angebotsseite, Versand)',
          pb.is_hidden('#btn-publish') and pb.is_hidden('#save-state') and pb.is_hidden('#btn-site') and pb.is_hidden('#btn-send'))
    pb.wait_for_selector('#view-stock [data-st="import"]')
    check('Bestand: Bestandsimport angeboten (Bearbeiterin mit Recht bestand.importieren)', pb.is_visible('#view-stock [data-st="import"]'))
    code = pb.evaluate("fetch('../api/?action=stock').then(r => r.status)")
    check('Bestand: Bestandsliste über die Schnittstelle (Recht bestand.sehen)', code == 200, code)
    code, _ = pb.evaluate(js_post.replace("'../api/", "'/api/"), ['user_save', {'id': '', 'name': 'X', 'username': 'x', 'role': 'admin', 'active': True}, stb.get('csrf', '')])
    check('Bestand: Rechte bleiben serverseitig (Bearbeiterin legt keine Nutzer an)', code == 403, code)
    pb.goto(B + '/admin/?ansicht=users'); pb.wait_for_selector('#view-stock:not([hidden])')
    check('Bestand: nicht erlaubte Ansicht in der Adresse wird ignoriert (?ansicht=users → Bestandsliste)', pb.is_hidden('#view-users'))
    pb.screenshot(path=os.path.join(SH, 'oidc_bestand_1280.png'))
    pb.set_viewport_size({'width': 390, 'height': 860}); pb.reload(); pb.wait_for_selector('#view-stock:not([hidden])')
    check('Bestand 390 px: kein waagerechtes Scrollen', not pb.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    pb.screenshot(path=os.path.join(SH, 'oidc_bestand_390.png'))
    # Recht entzogen (Ausnahme je Nutzer): Server verweigert die Bestandsliste auch auf dem Bestands-Host
    uid_e = nutzer_roh()['erika']['id']
    V.call('user_save', {'id': uid_e, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'deny': ['bestand.sehen', 'bestand.importieren', 'bestand.einkaufspreise']})
    code = pb.evaluate("fetch('../api/?action=stock').then(r => r.status)")
    check('Bestand: ohne Recht bestand.sehen verweigert der Server die Bestandsliste (403)', code == 403, code)
    V.call('user_save', {'id': uid_e, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'deny': []})
    check('Bestand: Recht wieder hergestellt', pb.evaluate("fetch('../api/?action=stock').then(r => r.status)") == 200)

    # ── HR unter eigener Adresse: Single Sign-on, eigene Sitzung, Urlaubsverwaltung für jede Mitarbeiterin mit hr.antrag ──
    ph = eigene_seite(ctx.new_page())
    ph.goto(HR + '/'); ph.wait_for_selector('#hr-app:not([hidden]), #hr-err:not([hidden]), #hr-login:not([hidden])', timeout=30000)
    check('HR: Single Sign-on, Startadresse führt zur Urlaubsverwaltung (normale Seite)', ph.url.startswith(HR + '/module/hr/') and ph.is_visible('#hr-app'),
          (ph.url, ph.text_content('#hr-err')))
    sth = ph.evaluate("fetch('../../api/?action=status').then(r => r.json())")
    check('HR: Bereich kommt vom Webserver (hr.intern)', sth.get('loggedIn') and sth['user'].get('bereich') == 'hr.intern', sth.get('user'))
    kh = kekse(ctx, 'hr.stafl.test')
    check('HR: eigene Sitzung (andere Cookie-Werte als angebot, verwaltung und bestand, nur __Host-)',
          kh.get('__Host-oidc_sitzung', {}).get('value') not in (None, ka.get('__Host-oidc_sitzung', {}).get('value'), kv.get('__Host-oidc_sitzung', {}).get('value'), kb.get('__Host-oidc_sitzung', {}).get('value'))
          and kh.get('__Host-WA_ADMIN', {}).get('value') not in (None, ka.get('__Host-WA_ADMIN', {}).get('value'), kv.get('__Host-WA_ADMIN', {}).get('value'), kb.get('__Host-WA_ADMIN', {}).get('value'))
          and all(n.startswith('__Host-') for n in kh), sorted(kh))
    code, j = ph.evaluate("fetch('../../api/?action=hr_start').then(async r => [r.status, await r.json().catch(() => ({}))])")
    check('HR: hr_start für die Mitarbeiterin (Recht hr.antrag, kein Tester-Eintrag nötig) 200', code == 200 and j.get('ok') and j.get('name') == 'Erika Editor', (code, j))
    check('HR: Name im Kopf, Personalbereiche ausgeblendet (ohne hr.verwalten)', 'Erika Editor' in (ph.text_content('#hr-user-name') or '') and ph.is_hidden('[data-tab="antraege"]'),
          ph.text_content('#hr-user-name'))
    ph.goto(HR + '/admin/'); ph.wait_for_selector('#hr-app:not([hidden])')
    check('HR: Adresse /admin/ (Anmeldehinweis der Seite) führt zurück zur Urlaubsverwaltung', ph.url.startswith(HR + '/module/hr/'), ph.url)
    # Aktion ↔ Host (GR-109): HR-Aktionen nur auf dem HR-Host; dort keine Aktionen des Eingabebereichs
    for name, seite in (('Dashboard', pg), ('Angebot', pa), ('Verwaltung', pv), ('Bestand', pb)):
        code = seite.evaluate("fetch('/api/?action=hr_start').then(r => r.status)")
        check(f'GR-109: hr_start auf dem Host „{name}“ abgewiesen (404)', code == 404, code)
    code, _ = pa.evaluate(js_post.replace("'../api/", "'/api/"), ['hr_antrag', {'von': '2031-03-03', 'bis': '2031-03-03'}, sta.get('csrf', '')])
    check('GR-109: Urlaubsantrag über den Angebots-Host abgewiesen (404)', code == 404, code)
    for a in ('stock', 'users', 'module_status'):
        code = ph.evaluate("a => fetch('/api/?action=' + a).then(r => r.status)", a)
        check(f'GR-109: auf dem HR-Host {a} → ' + ('200 (Grundaktion der Plattform)' if a == 'module_status' else '404 (Aktion des Eingabebereichs)'),
              code == (200 if a == 'module_status' else 404), code)
    # Recht entzogen (Ausnahme je Nutzer): Server verweigert die Urlaubsverwaltung auch auf dem HR-Host
    V.call('user_save', {'id': uid_e, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'deny': ['hr.antrag']})
    code = ph.evaluate("fetch('/api/?action=hr_start').then(r => r.status)")
    check('HR: ohne Recht hr.antrag verweigert der Server die Urlaubsverwaltung (403)', code == 403, code)
    V.call('user_save', {'id': uid_e, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'deny': []})
    check('HR: Recht wieder hergestellt', ph.evaluate("fetch('/api/?action=hr_start').then(r => r.status)") == 200)
    ph.reload(); ph.wait_for_selector('#hr-app:not([hidden])')
    ph.screenshot(path=os.path.join(SH, 'oidc_hr_1280.png'), full_page=True)
    ph.set_viewport_size({'width': 390, 'height': 860}); ph.reload(); ph.wait_for_selector('#hr-app:not([hidden])')
    check('HR 390 px: kein waagerechtes Scrollen', not ph.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    ph.screenshot(path=os.path.join(SH, 'oidc_hr_390.png'), full_page=True)
    ph.set_viewport_size({'width': 1280, 'height': 900})

    # ── Gesperrtes Konto: sofort ausgesperrt, trotz gültiger Keycloak-Sitzung ──
    uid = nutzer_roh()['erika']['id']
    V.call('user_save', {'id': uid, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': False})
    code, j = pg.evaluate("fetch('../api/?action=status').then(async r => [r.status, await r.json().catch(() => ({}))])")
    check('gesperrtes Mitarbeiterkonto: sofort 403', code == 403 and 'gesperrt' in j.get('error', ''), (code, j))
    pg.reload(); pg.wait_for_selector('#db-err:not([hidden])')
    check('Dashboard zeigt die Sperre verständlich an', 'gesperrt' in pg.text_content('#db-err'))
    V.call('user_save', {'id': uid, 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True})
    pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('wieder freigegeben: Dashboard nutzbar', pg.is_visible('#db-grid'))

    # ── Mobil ──
    pg.set_viewport_size({'width': 390, 'height': 860}); pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('390 px: kein waagerechtes Scrollen', not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    pg.screenshot(path=os.path.join(SH, 'oidc_dashboard_390.png'), full_page=True)
    pg.set_viewport_size({'width': 1280, 'height': 900})

    # ── Abmelden: beendet die Anmeldung für alle Anwendungen ──
    pg.click('#db-logout'); pg.wait_for_url('**/dashboard/abgemeldet.html')
    check('Abmelden führt über Keycloak zur Abmeldeseite', pg.url == D + '/dashboard/abgemeldet.html', pg.url)
    pg.screenshot(path=os.path.join(SH, 'oidc_abgemeldet.png'))
    code = pg.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Dashboard danach abgemeldet (401)', code == 401, code)
    code = pa.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Back-Channel-Logout: Mitarbeiter-Eingabe ebenfalls abgemeldet', code == 401, code)
    code = pv.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Back-Channel-Logout: Verwaltung ebenfalls abgemeldet', code == 401, code)
    code = pb.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Back-Channel-Logout: Bestand ebenfalls abgemeldet', code == 401, code)
    code = ph.evaluate("fetch('/api/?action=status').then(r => r.status)")
    check('Back-Channel-Logout: HR ebenfalls abgemeldet', code == 401, code)
    # Offene HR-Seite: Antwort 401 ohne JSON (Webserver) → Anmeldehinweis „neu laden“, der über Keycloak zurückführt
    ph.click('[data-jahr="1"]'); ph.wait_for_selector('#hr-login:not([hidden])')
    check('HR nach dem Abmelden: Anmeldehinweis, Knopf lädt die Seite neu (nicht /admin/)', ph.get_attribute('#hr-login a', 'href') == './', ph.get_attribute('#hr-login a', 'href'))
    ph.click('#hr-login a'); ph.wait_for_selector('#username')
    check('… erneute Anmeldung über Keycloak verlangt', ph.url.startswith(L), ph.url)
    pg.goto(D + '/'); pg.wait_for_selector('#username')
    check('erneuter Aufruf verlangt wieder Passwort (zentrale Sitzung beendet)', pg.url.startswith(L))
    ctx.close()

    # ── Import-Adresse mit erstmaliger Anmeldung: die Ansicht übersteht den Weg über Keycloak ──
    ctx = br.new_context(ignore_https_errors=True, viewport={'width': 1280, 'height': 900}); pg = eigene_seite(ctx.new_page())
    pg.goto(W + '/import/'); pg.wait_for_selector('#username')
    pg.fill('#username', 'erika'); pg.fill('#password', NUTZER['erika'][0]); pg.click('#kc-login'); otp_eingeben(pg, 'erika')
    pg.wait_for_selector('#view-importe:not([hidden])')
    check('Import-Adresse ohne Sitzung: nach der Anmeldung direkt in der Importzentrale', pg.url == W + '/admin/?ansicht=importe&nur=import' and pg.is_visible('#view-importe'), pg.url)
    ctx.close()

    # ── Keycloak-Nutzer ohne Mitarbeiterkonto ──
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); anmelden(pg, 'fremd'); pg.wait_for_selector('#db-err:not([hidden])')
    check('ohne Mitarbeiterkonto: kein Zugang, verständlicher Hinweis', 'kein Mitarbeiterkonto' in pg.text_content('#db-err') and pg.is_hidden('#db-bereich'))
    check('ohne Mitarbeiterkonto: keine Verknüpfung angelegt', not any(u.get('oidcSub') and u['username'] == 'fremd' for u in nutzer_roh().values()))
    ctx.close()

    # ── Bearbeiter ohne zweiten Faktor (nicht vorgeschrieben): nur Passwort ──
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); anmelden(pg, 'neu', otp=False); pg.wait_for_selector('#db-grid .db-tile')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('Bearbeiter ohne zweiten Faktor: nur mit Passwort im Dashboard (nicht vorgeschrieben)', st.get('loggedIn') and st['user']['username'] == 'neu', st.get('user'))
    ctx.close()

    # ── Bearbeiter einzeln verpflichtet (Nutzerfeld twofaPflicht, Nutzer bearbeiten): unser Server verlangt die zweite Stufe ──
    V2 = Legacy()   # frische Anmeldung: Bestätigung für user_save gültig
    check('Vorbereitung: Administrator erneut angemeldet (bisheriger Zugang)', V2.call('login', {'username': 'admin', 'password': PW_ALT})[0] == 200)
    code, j = V2.call('user_save', {'id': nutzer_roh()['neu']['id'], 'name': 'Neu Ohne Zweitfaktor', 'role': 'editor', 'active': True, 'twofaPflicht': True})
    check('Zwei-Faktor-Pflicht für Bearbeiter „neu“ gesetzt', code == 200 and nutzer_roh()['neu'].get('twofaPflicht') is True, (code, j))
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.route('**/dashboard/dashboard.js', lambda r: r.abort())   # nur die Antwort der Schnittstelle ansehen
    pg.goto(D + '/'); anmelden(pg, 'neu', otp=False); pg.wait_for_url(D + '/dashboard/**')
    code, j = pg.evaluate("fetch('../api/?action=status').then(async r => [r.status, await r.json().catch(() => ({}))])")
    check('einzeln verpflichteter Bearbeiter nur mit Passwort: kein Zugang, zweite Stufe angefordert (403)', code == 403
          and j.get('code') == 'reauth_required' and 'acr_values%3Dmfa' in j.get('anmelden', ''), (code, j))
    ctx.close()
    code, j = V2.call('user_save', {'id': nutzer_roh()['neu']['id'], 'name': 'Neu Ohne Zweitfaktor', 'role': 'editor', 'active': True, 'twofaPflicht': False})
    check('… Pflicht wieder entfernt', code == 200 and 'twofaPflicht' not in nutzer_roh()['neu'], (code, j))

    # ── Administrator ohne zweiten Faktor: unser Server verlangt ihn (zweite Stufe, Einrichtung bei Keycloak) ──
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.route('**/dashboard/dashboard.js', lambda r: r.abort())   # erst die Antwort der Schnittstelle ansehen
    pg.goto(D + '/'); anmelden(pg, 'chef', otp=False); pg.wait_for_url(D + '/dashboard/**')
    code, j = pg.evaluate("fetch('../api/?action=status').then(async r => [r.status, await r.json().catch(() => ({}))])")
    check('Administrator nur mit Passwort: kein Zugang, zweite Stufe angefordert (403)', code == 403 and j.get('code') == 'reauth_required'
          and 'acr_values%3Dmfa' in j.get('anmelden', '') and 'vorgeschrieben' in j.get('error', ''), (code, j))
    _stufe = [e for e in protokoll_roh() if e.get('a') == 'oidc_stufe' and e.get('u') == 'chef']
    _d = (_stufe[-1].get('d') or {}) if _stufe else {}
    check('Protokoll: zweite Stufe mit gemeldeter Stufe und Anmeldemethoden (nur Kürzel, hier nur Passwort)',
          _stufe and _d.get('stufe') == 'pwd' and _d.get('methoden') == 'pwd', _stufe[-1:] if _stufe else protokoll_roh()[-3:])
    pg.unroute('**/dashboard/dashboard.js'); pg.reload()
    pg.wait_for_selector('#totpSecret', state='attached')
    check('… Dashboard leitet zur zweiten Stufe, Keycloak verlangt die Einrichtung des Einmalcodes', pg.url.startswith(L) and 'CONFIGURE_TOTP' in pg.url, pg.url)
    chef_otp = pg.get_attribute('#totpSecret', 'value')
    pg.fill('#totp', totp(chef_otp)); pg.fill('#userLabel', 'Telefon'); pg.click('#saveTOTPBtn')
    pg.wait_for_selector('#db-grid .db-tile')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('… danach als Administrator angemeldet', st.get('loggedIn') and st['user']['username'] == 'chef', st.get('user'))
    ctx.close()
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(A + '/admin/'); pg.wait_for_selector('#username'); pg.fill('#username', 'chef'); pg.fill('#password', NUTZER['chef'][0]); pg.click('#kc-login')
    pg.wait_for_selector('#otp')
    check('nächste Anmeldung des Administrators: Einmalcode gleich in der ersten Stufe', pg.is_visible('#otp'))
    pg.fill('#otp', totp(chef_otp, 1)); pg.click('#kc-login'); pg.wait_for_selector('#screen-editor:not([hidden])')
    code, _ = pg.evaluate("fetch('../api/?action=status').then(async r => [r.status, await r.json().catch(() => ({}))])")
    check('… ohne zweite Abfrage in der Mitarbeiter-Eingabe (Einmalcode als Anmeldemethode erkannt)', code == 200 and pg.url.startswith(A + '/admin/'), (code, pg.url))
    pg.goto(W + '/admin/'); pg.wait_for_selector('#screen-editor:not([hidden])'); pg.wait_for_function("!document.querySelector('#vt-users').hidden")
    sichtbar = pg.evaluate("[...document.querySelectorAll('[id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))")
    check('Administrator in der Verwaltung (Single Sign-on mit zweitem Faktor): Import, Nutzer, Sicherheit, E-Mail, Protokoll; kein Angebot',
          {'master', 'kunden', 'importe', 'users', 'sec', 'mail', 'log', 'schutz'} <= set(sichtbar) and 'edit' not in sichtbar, sichtbar)
    pg.click('#vt-users'); pg.wait_for_selector('#view-users:not([hidden])')
    pg.screenshot(path=os.path.join(SH, 'oidc_verwaltung_admin_1280.png'))
    # Kachel „Import“: nur die Importzentrale – Nutzer, Protokoll, Sicherheit, Schutz nur über die Kachel „Verwaltung“
    pg.goto(W + '/import/'); pg.wait_for_selector('#view-importe:not([hidden])')
    nur_import = pg.evaluate("[...document.querySelectorAll('[role=tab][id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3))")
    check('Administrator über die Kachel „Import“: nur die Importzentrale, keine Verwaltungsbereiche, ohne Seitenleiste, Titel „Import“',
          nur_import == ['importe'] and pg.is_hidden('.side-nav') and pg.text_content('#topbar h1') == 'Import' and pg.title().startswith('Import')
          and pg.is_visible('#btn-dashboard'), (nur_import, pg.title()))
    pg.goto(W + '/admin/?ansicht=importe&nur=import#users'); pg.wait_for_selector('#view-importe:not([hidden])')
    check('… auch über #users in der Adresse keine Nutzerverwaltung', pg.is_hidden('#view-users'))
    pg.screenshot(path=os.path.join(SH, 'oidc_import_admin_1280.png'))
    pg.set_viewport_size({'width': 390, 'height': 844}); pg.reload(); pg.wait_for_selector('#view-importe:not([hidden])')
    check('Kachel „Import“ 390 px: ohne Seitenleiste, kein waagerechtes Scrollen', pg.is_hidden('.side-nav') and not pg.evaluate('document.documentElement.scrollWidth > innerWidth'))
    pg.screenshot(path=os.path.join(SH, 'oidc_import_admin_390.png'))
    pg.set_viewport_size({'width': 1280, 'height': 900})
    pg.goto(W + '/admin/'); pg.wait_for_selector('#screen-editor:not([hidden])')
    try:
        pg.wait_for_function("!document.querySelector('#vt-users').hidden", timeout=10000)
    except Exception:
        pass
    _zustand = pg.evaluate("({ url: location.href, titel: document.title, sichtbar: [...document.querySelectorAll('[role=tab][id^=vt-]')].filter(b => !b.hidden).map(b => b.id.slice(3)), "
                           "klassen: document.body.className })")
    check('… über die Kachel „Verwaltung“ wieder alle Verwaltungsbereiche', pg.is_visible('.side-nav') and pg.is_visible('#vt-users') and pg.is_visible('#vt-sec'), _zustand)
    ctx.close()

    # ── Sensible Aktion: erneute Anmeldung bei Keycloak statt eigener Passwortabfrage (ADR-003, max_age=0) ──
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(W + '/admin/'); anmelden(pg, 'admin'); pg.wait_for_selector('#screen-editor:not([hidden])')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    js = "([a, t]) => fetch('../api/?action=' + a, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': t}, body: '{}'}).then(async r => [r.status, await r.json().catch(() => ({}))])"
    code, j = pg.evaluate(js, ['geo_clear_stats', st['csrf']])
    check('direkt nach der Anmeldung: sensible Aktion ohne weitere Abfrage (Anmeldezeitpunkt zählt)', code == 200, (code, j))
    check('Bestätigung nachgestellt abgelaufen', bestaetigung_abgelaufen(ctx, 'verwaltung.stafl.test'))
    code, j = pg.evaluate(js, ['geo_clear_stats', st['csrf']])
    check('abgelaufen: 403 „erneut anmelden“ statt Passwortabfrage', code == 403 and j.get('code') == 'reauth_required', (code, j))
    neu = j.get('anmelden', '')
    check('… mit Adresse für die erneute Anmeldung (eigener Host, max_age=0)', neu.startswith('/oidc/callback?iss=') and 'auth_request_params=max_age%3D0' in neu, neu)
    code, j = pg.evaluate(js, ['reauth', st['csrf']])
    check('eigene Passwortbestätigung bleibt gesperrt', code == 403, (code, j))
    # Oberfläche (Verwaltung unter eigener Adresse): Speichern in Sicherheit führt selbst zur erneuten Anmeldung und zurück
    pg.reload(); pg.wait_for_selector('#screen-editor:not([hidden])')
    pg.click('#vt-sec'); pg.wait_for_selector('#sec-form')
    with pg.expect_navigation(url=lambda u: u.startswith(L)):
        pg.click('#sec-form [type=submit]')
    check('Speichern ohne gültige Bestätigung: Weiterleitung zu Keycloak mit max_age=0', 'max_age=0' in urllib.parse.unquote(pg.url), pg.url)
    pg.wait_for_selector('#password')
    check('Keycloak verlangt erneut Passwort und zweiten Faktor', pg.is_visible('#password'))
    pg.fill('#password', NUTZER['admin'][0]); pg.click('#kc-login')
    pg.wait_for_selector('#otp'); pg.fill('#otp', totp(NUTZER['admin'][1], 1)); pg.click('#kc-login')   # nächster Code (keine Wiederverwendung)
    pg.wait_for_url(W + '/admin/'); pg.wait_for_selector('#screen-editor:not([hidden])')
    code, j = pg.evaluate(js, ['geo_clear_stats', st['csrf']])
    check('nach der erneuten Anmeldung: Aktion bestätigt', code == 200, (code, j))
    pg.goto(D + '/'); pg.wait_for_selector('#db-grid .db-tile')   # SSO auf den anderen Host
    pg.goto(A + '/oidc/callback?' + urllib.parse.urlencode({'iss': L + '/realms/mitarbeiter', 'target_link_uri': 'https://angreifer.example/'}))
    check('erneute Anmeldung leitet nie auf fremde Seiten (offene Weiterleitung)', urllib.parse.urlparse(pg.url).hostname != 'angreifer.example', pg.url)
    ctx.close()

    # ── Passkey als zweiter Faktor (virtueller Authenticator mit Bestätigung am Gerät) ──
    kopf = {'Authorization': 'Bearer ' + kc_token(), 'Content-Type': 'application/json'}
    _, _, text = anfrage(KC + '/admin/realms/mitarbeiter/users?exact=true&username=erika', kopf=kopf)
    kc_erika = json.loads(text)[0]
    kc_erika['requiredActions'] = ['webauthn-register']
    check('Testvorbereitung: erika soll einen Passkey einrichten', anfrage(f"{KC}/admin/realms/mitarbeiter/users/{kc_erika['id']}", 'PUT', json.dumps(kc_erika).encode(), kopf)[0] == 204)
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    cdp = ctx.new_cdp_session(pg); cdp.send('WebAuthn.enable')
    cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {'protocol': 'ctap2', 'transport': 'internal', 'hasResidentKey': True,
             'hasUserVerification': True, 'isUserVerified': True, 'automaticPresenceSimulation': True}})
    pg.on('dialog', lambda d: d.accept('Testschlüssel'))
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'erika'); pg.fill('#password', NUTZER['erika'][0]); pg.click('#kc-login')
    otp_eingeben(pg, 'erika')
    pg.wait_for_selector('#registerWebAuthn')
    check('Passkey-Einrichtung bei Keycloak angeboten', pg.is_visible('#registerWebAuthn'))
    pg.click('#registerWebAuthn'); pg.wait_for_selector('#db-grid .db-tile')
    _, _, text = anfrage(f"{KC}/admin/realms/mitarbeiter/users/{kc_erika['id']}/credentials", kopf={'Authorization': 'Bearer ' + kc_token()})
    arten = sorted(c['type'] for c in json.loads(text))
    check('Passkey bei Keycloak gespeichert (neben Passwort und Einmalcode)', 'webauthn' in arten, arten)
    pg.click('#db-logout'); pg.wait_for_url('**/dashboard/abgemeldet.html')
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'erika'); pg.fill('#password', NUTZER['erika'][0]); pg.click('#kc-login')
    pg.wait_for_selector('#authenticateWebAuthnButton')
    check('mit Passkey: zweiter Faktor per Passkey, kein Einmalcode verlangt', pg.locator('#otp').count() == 0)
    pg.click('#authenticateWebAuthnButton'); pg.wait_for_selector('#db-grid .db-tile')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('Anmeldung mit Passkey: Stufe „mfa“, unser Server lässt sie zu', st.get('loggedIn') and st['user']['username'] == 'erika', st.get('user'))
    pg.screenshot(path=os.path.join(SH, 'oidc_passkey_dashboard.png'))
    ctx.close()

    # ── Realm-Einstellungen für den Betrieb ──
    _, _, text = anfrage(KC + '/admin/realms/mitarbeiter', kopf={'Authorization': 'Bearer ' + kc_token()})
    realm = json.loads(text)
    check('Anmeldeereignisse werden 30 Tage aufbewahrt (Datenschutz)', realm.get('eventsEnabled') and realm.get('eventsExpiration') == 2592000, realm.get('eventsExpiration'))
    _, _, text = anfrage(KC + '/admin/realms/mitarbeiter/authentication/required-actions', kopf={'Authorization': 'Bearer ' + kc_token()})
    aktiv = sorted(a['alias'] for a in json.loads(text) if a.get('enabled'))
    check('Pflichtaktionen: nur Passwort ändern, Einmalcode, Passkey', aktiv == sorted(['UPDATE_PASSWORD', 'CONFIGURE_TOTP', 'webauthn-register']), aktiv)
    check('neue Konten müssen den Einmalcode nicht automatisch einrichten', not any(a.get('defaultAction') for a in json.loads(text)), [a['alias'] for a in json.loads(text) if a.get('defaultAction')])

    # ── Konten über die Serverkonsole (deploy/anmeldung/konten.sh, Schritt 4) – zuletzt: löscht das Start-Konto ──
    ordner = tempfile.mkdtemp(prefix='konten-')
    with open(os.path.join(ordner, '.env'), 'w') as f:
        f.write("DOMAIN=angebot-stafl.de\n")
    os.makedirs(os.path.join(ordner, 'daten-anmeldung'), mode=0o700)
    start_datei = os.path.join(ordner, 'daten-anmeldung', 'einrichtung.env')   # Start-Konto wie von einrichten.sh
    with open(start_datei, 'w') as f:
        f.write(f"KC_BOOTSTRAP_ADMIN_USERNAME=verwaltung-ci\nKC_BOOTSTRAP_ADMIN_PASSWORD={GEHEIM['KC_ADMIN_PASSWORD']}\n")
    kc_dir = next(os.path.join(WORK, d) for d in sorted(os.listdir(WORK)) if os.path.isfile(os.path.join(WORK, d, 'bin', 'kcadm.sh')))
    umg = dict(os.environ, KCADM=f"env -u JAVA_TOOL_OPTIONS {kc_dir}/bin/kcadm.sh", KC_SERVER=KC)

    def konten(*args):
        r = subprocess.run(['sh', os.path.join(REPO, 'deploy', 'anmeldung', 'konten.sh'), *args], cwd=ordner, env=umg,
                           capture_output=True, text=True, timeout=300)
        return r.returncode, r.stdout + r.stderr

    def env_datei():
        return dict(z.strip().split('=', 1) for z in open(os.path.join(ordner, '.env')) if '=' in z)

    code, aus = konten('anlegen', 'sven.start', 'sven@stafl.test', 'Sven', 'Start')
    check('Konsole: ohne Verwaltungskonto kein Anlegen (Hinweis auf „verwaltung“)', code == 1 and 'konten.sh verwaltung' in aus, aus)
    code, aus = konten('verwaltung')
    e = env_datei()
    check('Konsole: dauerhaftes Verwaltungskonto angelegt, Start-Konto gelöscht', code == 0 and 'angelegt:' in aus and 'gelöscht:' in aus, aus)
    check('Konsole: Datei mit dem Start-Konto gelöscht', not os.path.exists(start_datei))
    check('Konsole: Start-Konto aus .env entfernt, Verwaltungspasswort nur in .env (nie angezeigt)',
          not any(k.startswith('KC_BOOTSTRAP_') for k in e) and len(e.get('KC_VERWALTUNG_PASSWORD', '')) >= 40
          and e['KC_VERWALTUNG_PASSWORD'] not in aus and oct(os.stat(os.path.join(ordner, '.env')).st_mode)[-3:] == '600')
    code, _, text = anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung-ci', 'password': GEHEIM['KC_ADMIN_PASSWORD']}).encode(),
        {'Content-Type': 'application/x-www-form-urlencoded'})
    check('Konsole: Start-Konto kann sich nicht mehr anmelden', code in (400, 401) and 'access_token' not in text, (code, text[:120]))
    code, aus = konten('verwaltung')
    check('Konsole: „verwaltung“ erneut ausgeführt ändert nichts', code == 0 and 'vorhanden:' in aus and 'angelegt:' not in aus, aus)
    code, aus = konten('anlegen', 'Sven.Start', 'sven@stafl.test', 'Sven', 'Start')
    m = re.search(r'weitergeben\): (\S+)', aus)
    check('Konsole: Mitarbeiterkonto angelegt (Name klein wie im Eingabebereich), Startpasswort einmal angezeigt', code == 0 and m and len(m.group(1)) >= 12, aus)
    start_pw = m.group(1) if m else ''
    code, aus = konten('anlegen', 'sven.start', 'sven@stafl.test', 'Sven', 'Start')
    check('Konsole: doppeltes Konto abgelehnt', code == 1 and 'gibt es schon' in aus, aus)
    code, aus = konten('anlegen', 'x; rm -rf /', 'a@b.de', 'A', 'B')
    check('Konsole: ungültiger Benutzername abgelehnt', code == 1 and 'Benutzername' in aus, aus)
    code, aus = konten('liste')
    check('Konsole: Liste zeigt das neue Konto', code == 0 and 'sven.start,Sven,Start,sven@stafl.test,true' in aus, aus)

    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', start_pw); pg.click('#kc-login')
    pg.wait_for_selector('#password-new')
    check('erste Anmeldung mit Startpasswort: eigenes Passwort verlangt', 'UPDATE_PASSWORD' in pg.url, pg.url)
    pg.fill('#password-new', 'kurz'); pg.fill('#password-confirm', 'kurz'); pg.click('#kc-submit'); pg.wait_for_selector('#password-new')
    check('… zu kurzes Passwort abgelehnt (Richtlinie des Realms)', 'UPDATE_PASSWORD' in pg.url and pg.locator('#input-error-password, .kc-feedback-text, [id*=error]').count() > 0)
    pg.fill('#password-new', SVEN['eigen']); pg.fill('#password-confirm', SVEN['eigen']); pg.click('#kc-submit')
    pg.wait_for_selector('#db-grid .db-tile')
    check('… danach ohne Einmalcode im Dashboard (für Bearbeiter nicht vorgeschrieben)', pg.url.startswith(D + '/dashboard/'), pg.url)
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('… angemeldet und mit dem Mitarbeiterkonto verknüpft', st.get('loggedIn') and st['user']['username'] == 'sven.start', st.get('user'))
    code, aus = konten('sperren', 'sven.start')
    check('Konsole: Konto gesperrt', code == 0 and 'gesperrt' in aus, aus)
    pg.wait_for_function("fetch('../api/?action=status').then(r => r.status === 401)", polling=500, timeout=15000)
    check('… und sofort überall abgemeldet (Back-Channel-Logout)', True)
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', SVEN['eigen']); pg.click('#kc-login')
    pg.wait_for_load_state()
    check('gesperrtes Konto: keine Anmeldung', pg.url.startswith(L) and pg.locator('#db-grid').count() == 0, pg.url)
    code, aus = konten('entsperren', 'sven.start')
    code2, aus2 = konten('startpasswort', 'sven.start')
    m = re.search(r'weitergeben\): (\S+)', aus2)
    check('Konsole: entsperrt, neues Startpasswort', code == 0 and code2 == 0 and m, aus + aus2)
    ctx.close()
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', m.group(1) if m else 'x'); pg.click('#kc-login')
    pg.wait_for_selector('#password-new')
    check('neues Startpasswort: danach eigenes Passwort verlangt', 'UPDATE_PASSWORD' in pg.url, pg.url)
    pg.fill('#password-new', SVEN['zweit']); pg.fill('#password-confirm', SVEN['zweit']); pg.click('#kc-submit')
    pg.wait_for_selector('#db-grid .db-tile')
    ctx.close()
    # Automatische Sperre nach Fehlversuchen (Brute-Force-Schutz): entsperren hebt sie auf
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    for _ in range(6):
        pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', 'Falsch-Falsch-1'); pg.click('#kc-login')
        pg.wait_for_load_state()
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', SVEN['zweit']); pg.click('#kc-login')
    pg.wait_for_selector('#input-error-username, .kc-feedback-text')
    _m = pg.inner_text('.pf-v5-c-login__main')
    check('gesperrt nach Fehlversuchen: auch mit richtigem Passwort keine Anmeldung, Meldung erklärt die Sperre (ohne sie zu verraten)',
          pg.url.startswith(L) and 'Benutzername oder Passwort stimmt nicht' in _m and 'einige Minuten gesperrt' in _m, _m[:300])
    ctx.close()
    def vtoken_bf():   # das Start-Konto der Tests gibt es hier nicht mehr (konten.sh verwaltung)
        return json.loads(anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
            'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung', 'password': env_datei()['KC_VERWALTUNG_PASSWORD']}).encode(),
            {'Content-Type': 'application/x-www-form-urlencoded'})[2])['access_token']
    _, _, text = anfrage(KC + '/admin/realms/mitarbeiter/users?exact=true&username=sven.start', kopf={'Authorization': 'Bearer ' + vtoken_bf()})
    sid = json.loads(text)[0]['id']
    bf = lambda: json.loads(anfrage(f'{KC}/admin/realms/mitarbeiter/attack-detection/brute-force/users/{sid}', kopf={'Authorization': 'Bearer ' + vtoken_bf()})[2])
    vorher = bf()
    check('Fehlversuche: Konto automatisch vorübergehend gesperrt', vorher.get('disabled') is True and vorher.get('numFailures', 0) >= 1, vorher)
    code, aus = konten('entsperren', 'sven.start')
    nachher = bf()
    check('Konsole: entsperren hebt auch die automatische Sperre auf', code == 0 and 'Fehlversuchen' in aus and not nachher.get('disabled') and nachher.get('numFailures', 0) == 0, (aus, nachher))

    # Freiwillig eingerichteter Einmalcode (wie über „Konto“ auf der Anmeldeseite): wird danach immer abgefragt
    def vtoken():
        return json.loads(anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
            'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung', 'password': env_datei()['KC_VERWALTUNG_PASSWORD']}).encode(),
            {'Content-Type': 'application/x-www-form-urlencoded'})[2])['access_token']
    kopf = {'Authorization': 'Bearer ' + vtoken(), 'Content-Type': 'application/json'}
    kc_sven = json.loads(anfrage(KC + '/admin/realms/mitarbeiter/users?exact=true&username=sven.start', kopf=kopf)[2])[0]
    kc_sven['requiredActions'] = ['CONFIGURE_TOTP']
    anfrage(f"{KC}/admin/realms/mitarbeiter/users/{kc_sven['id']}", 'PUT', json.dumps(kc_sven).encode(), kopf)
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', SVEN['zweit']); pg.click('#kc-login')
    pg.wait_for_selector('#totpSecret', state='attached')
    _w = pg.text_content('#stafl-totp-alt') if pg.locator('#stafl-totp-alt').count() else ''
    check('Einrichtung des Einmalcodes: deutlicher Hinweis, alte Einträge in der App zu löschen', pg.is_visible('#stafl-totp-alt') and 'alte Einträge' in _w and 'löschen' in _w
          and 'STAFL-Plattform' in _w, _w)
    _t = pg.evaluate("() => { const f = document.querySelector('#totp'); return [f.autocomplete, f.inputMode, f.pattern, document.querySelector('#kc-page-title').textContent.trim()]; }")
    check('Einrichtung: Code-Feld mit autocomplete=one-time-code, Ziffernblock, 6 Ziffern; Titel „Einmalcode einrichten“',
          _t == ['one-time-code', 'numeric', '[0-9]{6}', 'Einmalcode einrichten'], _t)
    pg.set_viewport_size({'width': 390, 'height': 844})
    check('Einrichtung 390 px: kein waagerechtes Scrollen', not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    pg.screenshot(path=os.path.join(SH, 'oidc_einmalcode_einrichten_390.png'), full_page=True)
    pg.set_viewport_size({'width': 1280, 'height': 900})
    sven_otp = pg.get_attribute('#totpSecret', 'value')
    pg.fill('#totp', totp(sven_otp)); pg.fill('#userLabel', 'Telefon'); pg.click('#saveTOTPBtn')
    pg.wait_for_selector('#db-grid .db-tile')
    ctx.close()
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', SVEN['zweit']); pg.click('#kc-login')
    pg.wait_for_selector('#otp')
    check('freiwillig eingerichteter Einmalcode wird bei der Anmeldung abgefragt', pg.is_visible('#otp'))
    pg.fill('#otp', totp(sven_otp, 1)); pg.click('#kc-login'); pg.wait_for_selector('#db-grid .db-tile')
    ctx.close()
    # Diagnose (konten.sh pruefen): falscher Einmalcode erscheint als Ereignis, nur lesend, kein Geheimnis in der Ausgabe
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', SVEN['zweit']); pg.click('#kc-login')
    pg.wait_for_selector('#otp'); pg.fill('#otp', '000000' if totp(sven_otp, 1) != '000000' else '111111'); pg.click('#kc-login')
    pg.wait_for_selector('#otp')
    ctx.close()
    vorher = anfrage(f"{KC}/admin/realms/mitarbeiter/users/{kc_sven['id']}", kopf={'Authorization': 'Bearer ' + vtoken()})[2]
    code, aus = konten('pruefen', 'Sven.Start')
    check('Konsole pruefen: Konto aktiv, ein Einmalcode-Gerät mit Bezeichnung',
          code == 0 and "Konto 'sven.start': aktiv" in aus and aus.count('Einmalcode (App): eingerichtet') == 1 and '„Telefon“' in aus, aus)
    check('… falscher Einmalcode als Ereignis mit verständlicher Ursache',
          re.search(r'LOGIN_ERROR · Passwort oder Einmalcode falsch', aus) and 'Fehlversuche in Folge: 1' in aus, aus)
    check('… Regeln und Uhr angezeigt, kein Geheimnis des Einmalcodes', 'jeder Code nur einmal' in aus and 'Serveruhr:' in aus and sven_otp not in aus, aus)
    check('… ändert nichts am Konto', json.loads(vorher) == json.loads(anfrage(f"{KC}/admin/realms/mitarbeiter/users/{kc_sven['id']}", kopf={'Authorization': 'Bearer ' + vtoken()})[2]))
    check('… Anmeldeablauf: Passwort und Einmalcode (beide Stufen) melden ihre Anmeldemethode', "Passwort (Ebene" in aus and aus.count("Einmalcode (Ebene") >= 2
          and "meldet NICHTS" not in aus and "meldet 'otp', gültig 36000 s" in aus, aus)
    check('… alle Anwendungen mit Anmeldemethoden im Anmelde-Token', all(f'{c}: amr-Claim im Anmelde-Token' in aus for c in ('dashboard', 'angebot', 'verwaltung', 'bestand'))
          and 'FEHLT' not in aus, aus)
    code, aus = konten('entsperren', 'sven.start')   # Fehlversuch zurücksetzen, damit die folgenden Anmeldungen nicht in die Sperre laufen

    code, aus = konten('zuruecksetzen', 'sven.start')
    m = re.search(r'weitergeben\): (\S+)', aus)
    check('Konsole: zweiter Faktor zurückgesetzt (Handy verloren), neues Startpasswort', code == 0 and 'gelöscht' in aus and m, aus)
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(D + '/'); pg.wait_for_selector('#username'); pg.fill('#username', 'sven.start'); pg.fill('#password', m.group(1) if m else 'x'); pg.click('#kc-login')
    pg.wait_for_selector('#password-new')
    check('… alter Einmalcode nicht mehr abgefragt, eigenes Passwort verlangt', pg.locator('#otp').count() == 0 and 'UPDATE_PASSWORD' in pg.url, pg.url)
    pg.fill('#password-new', SVEN['dritt']); pg.fill('#password-confirm', SVEN['dritt']); pg.click('#kc-submit')
    pg.wait_for_selector('#db-grid .db-tile')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('… danach wieder dasselbe Mitarbeiterkonto (Verknüpfung bleibt)', st.get('loggedIn') and st['user']['username'] == 'sven.start', st.get('user'))
    ctx.close()
    code, aus = konten('passkey', 'gibt-es-nicht')
    check('Konsole: unbekanntes Konto verständlich abgelehnt', code == 1 and 'gibt es in Keycloak nicht' in aus, aus)

    # ── Einladung per Mail (konten.sh mail-einrichten / einladen): Link statt Passwort, Postfach-Passwort nur im Tresor ──
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from postfach import Postfach
    pf = Postfach(POSTFACH['port'], POSTFACH['user'], POSTFACH['pass'])
    umg.update(APP_PHP=f"env WA_APP_DIR={WORK}/app MAIL_SMTP_HOST=127.0.0.1 MAIL_SMTP_PORT={POSTFACH['port']} MAIL_SMTP_SECURE=none "
                       f"MAIL_SMTP_USER={POSTFACH['user']} MAIL_SMTP_PASS={POSTFACH['pass']} MAIL_FROM=anmeldung@stafl.test MAIL_FROM_NAME=STAFL php",
               KC_VAULT_HOST_DIR=os.path.join(WORK, 'vault'), KC_BASEURL_BEHALTEN='1')
    os.symlink(os.path.join(REPO, 'deploy'), os.path.join(ordner, 'deploy'))   # app-abfrage.php relativ zum Installationsordner

    def warte_mail(adresse, anzahl=1):
        for _ in range(60):
            if len(pf.an(adresse)) >= anzahl: return pf.an(adresse)[anzahl - 1]
            time.sleep(0.5)
        return None

    code, aus = konten('einladen', 'eva.einladung')
    check('Einladung: ohne eingerichteten Mailversand abgelehnt', code == 1 and 'mail-einrichten' in aus, aus)
    code, aus = konten('mail-einrichten', 'pruefung@stafl.test')
    tresor = os.path.join(WORK, 'vault', 'mitarbeiter_smtp__password')
    check('Mailversand eingerichtet, Testmail angekommen', code == 0 and warte_mail('pruefung@stafl.test') is not None, aus)
    check('Postfach-Passwort nur in der Tresor-Datei (nur Besitzer), nie in der Ausgabe',
          open(tresor).read() == POSTFACH['pass'] and oct(os.stat(tresor).st_mode)[-3:] == '600' and POSTFACH['pass'] not in aus)
    vtok = json.loads(anfrage(KC + '/realms/master/protocol/openid-connect/token', 'POST', urllib.parse.urlencode({
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'verwaltung', 'password': env_datei()['KC_VERWALTUNG_PASSWORD']}).encode(),
        {'Content-Type': 'application/x-www-form-urlencoded'})[2])['access_token']
    smtp = json.loads(anfrage(KC + '/admin/realms/mitarbeiter', kopf={'Authorization': 'Bearer ' + vtok})[2]).get('smtpServer', {})
    check('Keycloak-Datenbank kennt nur den Verweis auf den Tresor (nicht in der Sicherung)', smtp.get('password') == '${vault.smtp_password}' and smtp.get('host') == '127.0.0.1', smtp)
    check('Postfach mit den Zugangsdaten der Anwendung angemeldet', (POSTFACH['user'], True) in pf.anmeldungen and not any(not ok for _, ok in pf.anmeldungen), pf.anmeldungen)
    code, aus = konten('einladen', 'ohne.konto', 'ohne@stafl.test', 'Ohne', 'Konto')
    check('Einladung ohne Mitarbeiterkonto im Eingabebereich abgelehnt', code == 1 and 'kein Mitarbeiterkonto' in aus and not pf.an('ohne@stafl.test'), aus)
    code, aus = konten('einladen', 'Eva.Einladung', 'eva@stafl.test', 'Eva', 'Einladung')
    m = warte_mail('eva@stafl.test')
    link = re.search(r'https://login\.stafl\.test:8443/realms/mitarbeiter/login-actions/action-token\?key=\S+', m['text']).group(0) if m else ''
    check('Einladung verschickt: Mail mit Link, ohne Passwort, nur „Passwort aktualisieren“', code == 0 and link and 'Passwort aktualisieren' in m['text'] and 'Mehrfachauthentifizierung' not in m['text']
          and m['von'] == 'anmeldung@stafl.test', (aus, m and m['text'][:300]))
    code, aus = konten('einladen', 'eva.einladung', 'eva@stafl.test', 'Eva', 'Einladung')
    check('vorhandenes Konto nicht doppelt angelegt (Hinweis auf erneutes Senden)', code == 1 and 'gibt es schon' in aus, aus)
    ctx = br.new_context(ignore_https_errors=True); pg = eigene_seite(ctx.new_page())
    pg.goto(link); pg.wait_for_selector('a[href*="action-token"], #password-new')
    if pg.locator('#password-new').count() == 0:
        pg.click('a[href*="action-token"]'); pg.wait_for_selector('#password-new')
    check('Link aus der Einladung: eigenes Passwort festlegen', 'UPDATE_PASSWORD' in pg.url, pg.url)
    pg.fill('#password-new', SVEN['eva']); pg.fill('#password-confirm', SVEN['eva']); pg.click('#kc-submit')
    pg.wait_for_selector('a[href="https://dashboard.stafl.test:8443/"]')
    check('… danach Konto aktualisiert (ohne Einmalcode), Rückweg zum Dashboard', 'aktualisiert' in pg.inner_text('body') and pg.locator('#totpSecret').count() == 0)
    pg.click('a[href="https://dashboard.stafl.test:8443/"]')
    pg.wait_for_selector('#db-grid .db-tile, #username, #otp')
    if pg.locator('#username').count():
        pg.fill('#username', 'eva.einladung'); pg.fill('#password', SVEN['eva']); pg.click('#kc-login'); pg.wait_for_selector('#db-grid .db-tile, #otp')
    pg.wait_for_selector('#db-grid .db-tile')
    st = pg.evaluate("fetch('../api/?action=status').then(r => r.json())")
    check('… im Dashboard angemeldet, mit dem Mitarbeiterkonto verknüpft', st.get('loggedIn') and st['user']['username'] == 'eva.einladung', st.get('user'))
    pg.screenshot(path=os.path.join(SH, 'oidc_einladung_dashboard.png'))
    ctx.close()
    ctx = br.new_context(ignore_https_errors=True); pg = ctx.new_page()
    pg.goto(link); pg.wait_for_load_state()
    check('Link aus der Einladung nur einmal verwendbar', pg.locator('#password-new').count() == 0 and pg.url.startswith(L), pg.url)
    ctx.close()
    code, aus = konten('einladen', 'eva.einladung')
    m2 = warte_mail('eva@stafl.test', 2)
    check('erneute Einladung: wieder nur „Passwort aktualisieren“', code == 0 and m2 and 'Passwort aktualisieren' in m2['text'] and 'Mehrfachauthentifizierung' not in m2['text'], (aus, m2 and m2['text'][:200]))
    pf.schliessen()
    br.close()

check('keine JavaScript-Fehler auf unseren Seiten', not fehler, fehler)
check('keine JavaScript-Fehler auf der Anmeldeseite (Design und Skript für den Einmalcode)', not login_fehler, login_fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
