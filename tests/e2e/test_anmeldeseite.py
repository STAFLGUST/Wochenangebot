"""Testgruppe anmeldeseite: Prüfung vor der Anmeldeseite (login.dashboard-stafl.de). Caddy fragt vor jeder Seite von Keycloak
die Aktion anmeldung_pruefen ab (forward_auth, Caddyfile); der Testserver meldet sich wie der Host der Anmeldung in der
Anwendung (WA_OIDC=1, WA_OBERFLAECHE=plattform.anmeldung, WA_EIGENE_ANMELDUNG=aus – deploy/anmeldung/apache-oidc.conf).
Geprüft: Ländersperre (beide Geltungsbereiche, sperren/nur zulassen, freigegebene und interne Adressen), IP-Freigabe,
Firewall-Sperre, Wartung und Notfallmodus, Herkunftsangaben, andere Aktionen auf diesem Host. Den Weg über Caddy und Keycloak
prüft tests/oidc/ (CI-Auftrag „Anmeldung über Keycloak“), die Weiterleitung selbst tests/deploy/test_dashboard_domains.py."""
import json
import sys
import urllib.request

from kunden_hilfe import API, Client
from umgebung import storage_raw, storage_write

CN, AU, DE = '1.0.1.1', '1.0.0.1', '46.114.0.1'   # Länder laut Testdatenbank (wie test_geo)
GRUND = {'twofa': 'off', 'idleMinutes': 480, 'pwMin': 10, 'pwComplex': False, 'lockAfter': 10, 'lockMinutes': 15, 'ipEnabled': False, 'adminIps': [],
         'geoEnabled': False, 'geoMode': 'block', 'geoCountries': [], 'geoScope': 'admin'}
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def sicherheit(**w):
    storage_write('sicherheit', {**GRUND, **w})


def pruefen(ip, kopf=None):
    c = Client(ip)
    c.headers = kopf or {}
    code, r, roh = c.call('anmeldung_pruefen', raw=True)
    return code, r


code, r = pruefen(CN)
check('ohne Sperren: Anmeldeseite frei (200, ok)', code == 200 and r == {'ok': True}, (code, r))
antwort = urllib.request.urlopen(urllib.request.Request(API + 'anmeldung_pruefen', headers={'X-Forwarded-For': AU}))
check('Antwort wird nie zwischengespeichert', antwort.headers.get('Cache-Control') == 'no-store', antwort.headers.get('Cache-Control'))

# ---------- Ländersperre ----------
sicherheit(geoEnabled=True, geoMode='block', geoCountries=['CN'], geoScope='admin')
code, r = pruefen(CN)
check('Land gesperrt (nur Eingabebereich): Anmeldeseite gesperrt (403)', code == 403 and 'Land' in r.get('error', ''), (code, r))
check('anderes Land frei', pruefen(AU)[0] == 200 and pruefen(DE)[0] == 200)
sicherheit(geoEnabled=True, geoMode='block', geoCountries=['CN'], geoScope='all')
check('Land gesperrt (ganze Seite): ebenso gesperrt', pruefen(CN)[0] == 403 and pruefen(AU)[0] == 200)
sicherheit(geoEnabled=True, geoMode='allow', geoCountries=['DE'], geoScope='admin')
check('nur Deutschland zugelassen: Australien und China gesperrt, Deutschland frei', pruefen(AU)[0] == 403 and pruefen(CN)[0] == 403 and pruefen(DE)[0] == 200)
check('interne Adresse (Abrufe der Anwendung selbst) nie gesperrt', pruefen('10.20.30.40')[0] == 200 and pruefen('172.18.0.1')[0] == 200)
sicherheit(geoEnabled=True, geoMode='allow', geoCountries=['DE'], geoScope='admin', adminIps=['1.0.1.0/24'])
check('freigegebene Adresse trotz Ländersperre frei', pruefen(CN)[0] == 200 and pruefen(AU)[0] == 403)
sicherheit(geoEnabled=False, geoMode='block', geoCountries=['CN'])
check('Ländersperre ausgeschaltet: wieder frei', pruefen(CN)[0] == 200)
zaehler = json.loads((storage_raw('laendersperre') or 'null').split('\n', 1)[-1] or 'null') or {}
check('abgewiesene Zugriffe zählen in der Statistik (Sicherheit)', zaehler.get('cc', {}).get('CN', {}).get('n', 0) >= 2 and zaehler.get('cc', {}).get('AU', {}).get('n', 0) >= 1, zaehler)

# ---------- IP-Freigabe des Eingabebereichs ----------
sicherheit(ipEnabled=True, adminIps=['198.51.100.0/24'])
code, r = pruefen('203.0.113.9')
check('IP-Freigabe: fremde Adresse gesperrt (403)', code == 403 and 'Internetadresse' in r.get('error', ''), (code, r))
check('IP-Freigabe: freigegebene Adresse frei', pruefen('198.51.100.9')[0] == 200)
sicherheit()

# ---------- Firewall ----------
storage_write('sperrliste', {'manuell': [{'ip': '203.0.113.50', 'grund': 'Test', 'bis': 0}], 'auto': {}, 'meldung': {}})
code, r = pruefen('203.0.113.50')
check('von Hand gesperrte Adresse kommt nicht zur Anmeldung (403)', code == 403 and 'gesperrt' in r.get('error', ''), (code, r))
check('andere Adresse frei', pruefen('203.0.113.51')[0] == 200)
storage_write('sperrliste', {'manuell': [], 'auto': {}, 'meldung': {}})

# ---------- Wartung und Notfall: Administratoren müssen sich anmelden können ----------
storage_write('sicherheit-notfall', {'aktiv': True, 'seit': '2026-10-29T08:00:00Z', 'von': 'Test'})
check('Notfallmodus: Anmeldeseite bleibt erreichbar (wartung_frei)', pruefen(AU)[0] == 200)
storage_write('sicherheit-notfall', {'aktiv': False})

# ---------- Herkunftsangaben und andere Aktionen auf diesem Host ----------
code, r = pruefen(AU, {'Sec-Fetch-Site': 'same-site'})
check('mit Herkunftsangabe des Browsers abgewiesen – Caddy entfernt sie vor der Prüfung (header_up -Sec-Fetch-*)', code == 403, (code, r))
for a in ('users', 'draft', 'kunde_login', 'hr_start'):
    check(f'andere Aktion auf dem Host der Anmeldung: {a} → 404', Client(AU).call(a)[0] == 404)
check('Status bleibt (Grundaktion)', Client(AU).call('status')[0] == 200)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
