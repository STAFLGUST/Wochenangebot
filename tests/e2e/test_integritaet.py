"""Dateiprüfung (Sicherheit → Dateiprüfung): Programmdateien gegen die Prüfliste (verändert, fehlt, unbekannt),
Datenordner (Sperrzeile, ausführbare Dateien, Schutz des Datenbankordners, Dateiablage), auffällige Muster in Dateien und
gespeicherten Daten, Komponenten, Rechte, Speichern, automatische Prüfung, Benachrichtigung, Oberfläche.
Der Testserver läuft aus einer Kopie von app/ – nur diese Kopie wird verändert."""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B, API
from smtp_test import TestSmtp
from umgebung import REPO, SH, SMTP_PORT, GUARD, shot, until, storage_raw, storage_write, storage_sqlite

PW = 'Sicheres-Passwort-1'
KPW = 'Kunden-Passwort-77'
DATA = os.environ['UDATA']
APP = os.path.dirname(DATA)
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name)
    if raw is None:
        return None
    return json.loads(raw[len(GUARD):] if raw.startswith(GUARD) else raw)


def run(c):
    code, r = c.call('security_integrity', {'run': True})
    return code, r


def by_path(r):
    return {x['path']: x for x in (r.get('result') or {}).get('items', [])}


def mails(word):
    return [m for m in smtp.messages if 'it@example.org' in m['to'] and word in m['subject']]


# ---------- Prüfliste: nicht im Repository, beim Einspielen erzeugt (deploy/bereitstellen.py, hier: run_e2e.py) ----------
p = subprocess.run([sys.executable, os.path.join(REPO, 'werkzeuge', 'integritaet.py')], capture_output=True, text=True)
check('werkzeuge/integritaet.py: list is not part of the repository, generation works', p.returncode == 0 and 'nicht im Repository' in p.stdout, p.stdout + p.stderr)
check('list is not tracked by git', subprocess.run(['git', '-C', REPO, 'ls-files', '--error-unmatch', 'app/api/lib/integritaet-liste.php'], capture_output=True).returncode != 0)
LISTE = os.path.join(APP, 'api', 'lib', 'integritaet-liste.php')
liste = open(LISTE, encoding='utf-8').read()
check('generated list starts with the guard and has no data files', liste.startswith("<?php if (!defined('WA_API')) { http_response_code(404); exit; }") and "'data/" not in liste and "'index.html' =>" in liste and "'.htaccess' =>" in liste and 'deploy/bereitstellen.py' in liste)
check('HTML pages listed with two allowed versions (with/without ?v=)', "'index.html' => ['" in liste and "'admin/index.html' => ['" in liste and "'api/index.php' => '" in liste)
seite = open(os.path.join(APP, 'index.html'), encoding='utf-8').read()
import hashlib
v_frontend = hashlib.sha256(open(os.path.join(APP, 'assets', 'frontend.js'), 'rb').read()).hexdigest()[:10]
check('test copy is provided like the server: ?v= is the content hash', f'assets/frontend.js?v={v_frontend}"' in seite and '?v=' not in open(os.path.join(REPO, 'app', 'index.html'), encoding='utf-8').read())
try:
    st = urllib.request.urlopen(B + '/api/lib/integritaet-liste.php').status
except urllib.error.HTTPError as e:
    st = e.code
check('list file answers 404 when called directly', st == 404, st)

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'id': '', 'name': 'Lea Leser', 'username': 'lea', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
V = Client('198.51.100.4'); V.call('login', {'username': 'lea', 'password': 'Leser-Zugang-77'})
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Prüfung GmbH', 'nr': 'KPRUEF', 'email': 'kantine.pruef@example.org', 'active': True, 'angebote': ['std'],
                              'login': {'username': 'kantine.pruef', 'password': KPW, 'mustChange': False, 'active': True}})
check('customer created', st == 200, r)
K = Client('203.0.113.30'); check('customer login', K.call('kunde_login', {'username': 'kantine.pruef', 'password': KPW})[0] == 200)
N = Client('203.0.113.31')

# ---------- Rechte ----------
check('anonymous: 401', N.call('security_integrity')[0] == 401)
check('customer: 401 (no staff session)', K.call('security_integrity')[0] == 401)
check('viewer: 403', V.call('security_integrity')[0] == 403)
check('editor: 403', E.call('security_integrity')[0] == 403)
check('editor cannot run', run(E)[0] == 403)
check('anonymous cannot run', run(N)[0] in (401, 403))
check('nothing stored by rejected calls', doc('integritaet') is None)

# ---------- Erster Aufruf: automatische Prüfung der sauberen Kopie ----------
code, r = A.call('security_integrity')
R = r.get('result') or {}
check('first view runs automatically', code == 200 and R.get('auto') is True and R.get('ranAt'), r)
c = R.get('counts', {})
check('clean copy: no findings', R.get('ok') is True and R.get('items') == [] and c.get('modified') == 0 and c.get('missing') == 0 and c.get('unknown') == 0 and c.get('critical') == 0 and c.get('warnings') == 0, R.get('items'))
check('clean copy: all listed files checked', R.get('manifest', 0) >= 70 and c.get('checked', 0) >= R.get('manifest', 0), c)
check('result fields', all(k in R for k in ('ok', 'ranAt', 'ms', 'counts', 'items', 'components')) and isinstance(R['ms'], int))
php_ver = subprocess.run(['php', '-r', 'echo PHP_VERSION;'], capture_output=True, text=True).stdout
comp = {x['name']: x for x in R.get('components', [])}
check('components: PHP version with support end', comp.get('PHP', {}).get('version') == php_ver and comp['PHP']['stufe'] in ('ok', 'warnung', 'kritisch') and ('bis' in comp['PHP']['text'] or 'seit' in comp['PHP']['text']), comp.get('PHP'))
check('components: SQLite and OpenSSL', 'SQLite' in comp and comp['SQLite']['version'][:1].isdigit() and 'OpenSSL' in comp, list(comp))
check('components: vendored QR library', any(x.get('file') == 'assets/vendor/qrcode.js' and 'QR' in x['name'] for x in R.get('components', [])), R.get('components'))
check('result stored', (doc('integritaet') or {}).get('last', {}).get('ranAt') == R.get('ranAt'))
time.sleep(1.1)
code, r2 = A.call('security_integrity')
check('second view does not run again', code == 200 and r2['result']['ranAt'] == R['ranAt'] and len(r2['history']) == 1, r2.get('history'))

# ---------- Schreibschutz ----------
A0 = Client('198.51.100.2'); A0.http = A.http; A0.csrf = 'falsch'
check('run needs CSRF', run(A0)[0] == 403)
req = urllib.request.Request(API + 'security_integrity', data=b'run=1', headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRF-Token': A.csrf, 'X-Forwarded-For': '198.51.100.2'})
try:
    st = A.http.open(req).status
except urllib.error.HTTPError as e:
    st = e.code
check('run needs JSON', st == 415, st)
check('run needs run:true', A.call('security_integrity', {'run': 1})[0] == 422)

# ---------- Manuelle Prüfung, Protokoll ----------
code, r = run(A)
check('manual run ok', code == 200 and r['result']['auto'] is False and r['result']['by'] == 'admin' and r['result']['ok'], r.get('result', {}).get('items'))
check('history newest first, counts only', len(r['history']) == 2 and r['history'][0]['auto'] is False and 'items' not in r['history'][0] and 'counts' in r['history'][0])
check('manual run logged', 'Dateiprüfung ausgeführt' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ---------- Veränderungen ----------
A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org'}}})
with open(os.path.join(APP, 'assets', 'theme.js'), 'a', encoding='utf-8') as f: f.write('\n/* verändert */\n')
os.remove(os.path.join(APP, 'assets', 'legal.css'))
BACKDOOR = "<?php eval(base64_decode($_POST['x'])); ?>\n"
with open(os.path.join(APP, 'api', 'x.php'), 'w') as f: f.write(BACKDOOR)
with open(os.path.join(APP, 'assets', 'notiz.txt'), 'w') as f: f.write('harmlos\n')
with open(os.path.join(DATA, 'hinten.php'), 'w') as f: f.write('<?php echo "x";\n')
with open(os.path.join(DATA, 'werkzeug.phtml'), 'w') as f: f.write('nichts\n')
with open(os.path.join(DATA, 'export.json'), 'w') as f: f.write('{}\n')
storage_write('notiz-test', {'text': 'Hallo <script src="http://evil.example/x.js"></script>'})
storage_write('benachrichtigung-stand', {'sicherheit': {'last': 0, 'skipped': 0}})
code, r, raw = A.call('security_integrity', {'run': True}, raw=True)
I = by_path(r); c = r['result']['counts']
check('modified JS file', I.get('assets/theme.js', {}).get('art') == 'geaendert' and I['assets/theme.js']['stufe'] == 'warnung', I.get('assets/theme.js'))
check('missing file', I.get('assets/legal.css', {}).get('art') == 'fehlt', I.get('assets/legal.css'))
x = I.get('api/x.php', {})
check('unknown PHP file: critical with signature', x.get('art') == 'unbekannt' and x.get('stufe') == 'kritisch' and 'eval mit verschleiertem Code' in x.get('signatur', ''), x)
check('unknown harmless file: warning without signature', I.get('assets/notiz.txt', {}).get('stufe') == 'warnung' and 'signatur' not in I.get('assets/notiz.txt', {}), I.get('assets/notiz.txt'))
check('data: PHP file without guard is critical', I.get('data/hinten.php', {}).get('art') == 'daten' and I['data/hinten.php']['stufe'] == 'kritisch', I.get('data/hinten.php'))
check('data: .phtml is critical', I.get('data/werkzeug.phtml', {}).get('stufe') == 'kritisch', I.get('data/werkzeug.phtml'))
check('data: other file is only a hint', I.get('data/export.json', {}).get('stufe') == 'hinweis', I.get('data/export.json'))
sus = [v for k, v in I.items() if 'notiz-test' in k]
check('stored document with foreign script: suspicious', len(sus) == 1 and sus[0]['art'] == 'verdaechtig' and sus[0]['stufe'] == 'kritisch' and 'Fremdes Skript' in sus[0].get('signatur', ''), sus)
check('counts', c['modified'] == 1 and c['missing'] == 1 and c['unknown'] == 2 and c['suspicious'] == 1 and c['critical'] >= 4 and r['result']['ok'] is False, c)
check('critical items first', r['result']['items'][0]['stufe'] == 'kritisch')
check('no file contents in the answer', 'base64_decode' not in raw and 'evil.example' not in raw and 'echo' not in raw)
check('alert mail on new findings', until(lambda: mails('Dateiprüfung'), 8), [m['subject'] for m in smtp.messages])
m = (mails('Dateiprüfung') or [{'text': '', 'subject': ''}])[0]
check('alert names counts and paths', 'neue Auffälligkeiten' in m['subject'] and 'api/x.php' in m['text'] and 'Kritisch' in m['text'], m['text'][:800])
storage_write('benachrichtigung-stand', {'sicherheit': {'last': 0, 'skipped': 0}})
n0 = len(mails('neue Auffälligkeit'))
code, r = run(A)
check('same findings again: no new alert', code == 200 and until(lambda: len(mails('Dateiprüfung ausgeführt')) >= 1, 8) and len(mails('neue Auffälligkeit')) == n0, [m['subject'] for m in smtp.messages])

# ---------- Oberfläche (mit Befunden) ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page(); a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden])')
    a.goto(B + '/module/sicherheit/'); a.wait_for_selector('#sic-gesamt strong')
    check('UI: overall score reflects findings (Lagebild)', 'Handlungsbedarf' in a.inner_text('#sic-gesamt') and 'kritisch' in a.inner_text('#tab-lage .sic-karte:has-text("Dateiprüfung")'))
    a.click('#sic-tabs [data-tab="datei"]'); a.wait_for_selector('#tab-datei .sic-held')
    t = a.inner_text('#tab-datei')
    check('UI: card with status and counts', a.locator('#tab-datei .sic-held.bad').count() == 1 and 'kritisch' in t and 'verändert' in t and 'letzte prüfung' in t.lower(), t[:300])
    check('UI: findings listed with path, kind and signature', 'api/x.php' in t and 'Muster: eval mit verschleiertem Code' in t and 'assets/theme.js' in t and 'Datenordner' in t, t[:1200])
    check('UI: path in monospace', a.locator('#tab-datei .sic-pfad.mono-s', has_text='api/x.php').count() == 1)
    check('UI: component table with PHP', 'PHP' in t and php_ver in t)
    a.click('#tab-datei [data-befund]:has-text("api/x.php")'); a.wait_for_selector('#sic-dlg[open]')
    check('UI: finding details in a dialog with advice', 'api/x.php' in a.inner_text('#sic-dlg') and 'Befund der Dateiprüfung' in a.inner_text('#sic-dlg') and a.locator('#sic-dlg .sic-hinweis').inner_text().strip() != '')
    a.keyboard.press('Escape'); a.wait_for_selector('#sic-dlg', state='hidden')
    h0 = len(A.call('security_integrity')[1]['history'])
    a.click('#tab-datei [data-ip=run]')
    check('UI: run button runs a check', until(lambda: len(A.call('security_integrity')[1]['history']) == h0 + 1, 15))
    a.wait_for_selector('#tab-datei [data-ip=run]:not([disabled])')
    check('UI: result shown again after run', 'api/x.php' in a.inner_text('#tab-datei'))
    shot(a.locator('#tab-datei'), SH + '/integritaet.png')
    a.set_viewport_size({'width': 390, 'height': 844})
    check('UI 390 px: no horizontal page scroll', a.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    check('UI 390 px: card fits', a.evaluate("(() => { const r = document.querySelector('#tab-datei .sic-held').getBoundingClientRect(); return r.right <= window.innerWidth + 1; })()"))
    shot(a.locator('#tab-datei'), SH + '/integritaet-mobil.png')
    check('UI: no page errors', not errs, errs[:3])
    br.close()

# ---------- Keine Fehlalarme: alle Programmdateien als unbekannte Kopie ----------
kopie = os.path.join(APP, 'fremd-kopie')
for root, dirs, files in os.walk(os.path.join(REPO, 'app')):
    rel = os.path.relpath(root, os.path.join(REPO, 'app'))
    if rel.split(os.sep)[0] in ('data', 'geo') or rel.startswith('api' + os.sep + 'geo'):
        continue
    for fn in files:
        if fn.endswith(('.php', '.js', '.html', '.css', '.json', '.htaccess', '.txt')):
            os.makedirs(os.path.join(kopie, rel), exist_ok=True)
            shutil.copy(os.path.join(root, fn), os.path.join(kopie, rel, fn))
code, r = run(A)
fremd = [x for x in r['result']['items'] if x['path'].startswith('fremd-kopie/')]
check('copies of the own code are found as unknown', len(fremd) >= 60, len(fremd))
check('own code triggers no signature (no false alarms)', not [x for x in fremd if 'signatur' in x], [x for x in fremd if 'signatur' in x][:5])
shutil.rmtree(kopie)

# ---------- Aufräumen → wieder sauber ----------
shutil.copy(os.path.join(REPO, 'app', 'assets', 'theme.js'), os.path.join(APP, 'assets', 'theme.js'))
shutil.copy(os.path.join(REPO, 'app', 'assets', 'legal.css'), os.path.join(APP, 'assets', 'legal.css'))
for p in [os.path.join(APP, 'api', 'x.php'), os.path.join(APP, 'assets', 'notiz.txt'), os.path.join(DATA, 'hinten.php'), os.path.join(DATA, 'werkzeug.phtml'), os.path.join(DATA, 'export.json')]:
    os.remove(p)
storage_write('notiz-test', {'text': 'Hallo'})
code, r = run(A)
check('after cleanup: clean again', code == 200 and r['result']['ok'] and r['result']['items'] == [], r['result']['items'][:5])

# ---------- Datenordner: sperrende .htaccess und Proxy-Merkdatei der Anwendung sind erwartet (Befund aus dem Betrieb 26.10.2026) ----------
HT = os.path.join(DATA, '.htaccess')
PX = os.path.join(DATA, 'wa-proxy-4-' + 'd' * 64 + '.json')
with open(HT, 'w') as f:
    f.write('# Kein direkter Zugriff auf gespeicherte Daten (zusätzliche Absicherung)\n<IfModule mod_authz_core.c>\n  Require all denied\n</IfModule>\n'
            '<IfModule !mod_authz_core.c>\n  Deny from all\n</IfModule>\n')
with open(PX, 'w') as f: f.write('["172.18.0.2"]')
code, r = run(A)
check('data: blocking .htaccess and proxy file of the app are no finding', code == 200 and r['result']['ok'] and r['result']['items'] == [], r['result']['items'][:5])
with open(HT, 'a') as f: f.write('AddHandler application/x-httpd-php .txt\n')
with open(PX, 'w') as f: f.write('["172.18.0.2", "<script>"]')
I = by_path(run(A)[1])
check('data: .htaccess with more than a block is critical', I.get('data/.htaccess', {}).get('stufe') == 'kritisch', I.get('data/.htaccess'))
check('data: proxy file with other content is a warning', I.get('data/' + os.path.basename(PX), {}).get('stufe') == 'warnung', I.get('data/' + os.path.basename(PX)))
with open(HT, 'w') as f: f.write('Options -Indexes\n')
I = by_path(run(A)[1])
check('data: .htaccess without a block is critical', I.get('data/.htaccess', {}).get('stufe') == 'kritisch', I.get('data/.htaccess'))
os.remove(HT); os.remove(PX)

# ---------- Dateiablage (lib/dateiablage.php): hochgeladene Dateien sind erwartet, andere Dateien dort nicht (Befund 30.10.2026) ----------
AB = os.path.join(DATA, 'dateien', 'qs', 'ab')
os.makedirs(AB, exist_ok=True); os.makedirs(os.path.join(DATA, 'dateien', '.teile'), exist_ok=True)
with open(os.path.join(AB, 'ab12cd34ef56ab78cd90.bin'), 'wb') as f: f.write(b'%PDF-1.4 erfundene Datei <?php eval($_GET[1]); ?>')
with open(os.path.join(DATA, 'dateien', '.teile', 'f' * 24 + '.tmp'), 'wb') as f: f.write(b'Teil')
code, r = run(A)
check('data: files of the Dateiablage (.bin) and unfinished uploads are no finding', code == 200 and r['result']['ok'] and r['result']['items'] == [], r['result']['items'][:5])
with open(os.path.join(AB, 'werkzeug.php'), 'w') as f: f.write('<?php system($_GET["c"]);')
with open(os.path.join(AB, 'notiz.txt'), 'w') as f: f.write('x')
with open(os.path.join(AB, 'ab12cd34ef56ab78cd90.bin.phtml'), 'w') as f: f.write('x')
I = by_path(run(A)[1])
check('data: PHP file inside the Dateiablage is critical', I.get('data/dateien/qs/ab/werkzeug.php', {}).get('stufe') == 'kritisch', I.get('data/dateien/qs/ab/werkzeug.php'))
check('data: other names inside the Dateiablage are reported', I.get('data/dateien/qs/ab/notiz.txt', {}).get('stufe') == 'hinweis'
      and I.get('data/dateien/qs/ab/ab12cd34ef56ab78cd90.bin.phtml', {}).get('stufe') == 'kritisch', [I.get('data/dateien/qs/ab/notiz.txt'), I.get('data/dateien/qs/ab/ab12cd34ef56ab78cd90.bin.phtml')])
shutil.rmtree(os.path.join(DATA, 'dateien'))
check('data: clean again after the Dateiablage checks', run(A)[1]['result']['ok'])

# ---------- HTML-Seiten: mit und ohne Versionsnummern zulässig, jede andere Abweichung nicht ----------
SEITE = os.path.join(APP, 'index.html')
gestempelt = open(SEITE, encoding='utf-8').read()
with open(SEITE, 'w', encoding='utf-8') as f: f.write(open(os.path.join(REPO, 'app', 'index.html'), encoding='utf-8').read())
code, r = run(A)
check('page without version numbers (state of the commit) is accepted', code == 200 and r['result']['ok'] and r['result']['items'] == [], r['result']['items'][:5])
with open(SEITE, 'w', encoding='utf-8') as f: f.write(gestempelt.replace(f'frontend.js?v={v_frontend}', 'frontend.js?v=0000000000'))
I = by_path(run(A)[1])
check('page with a foreign version number is reported as modified', I.get('index.html', {}).get('art') == 'geaendert', I.get('index.html'))
with open(SEITE, 'w', encoding='utf-8') as f: f.write(gestempelt)

# ---------- Fehlende Prüfliste (z. B. Bereitstellung nicht gelaufen) bleibt kritisch ----------
liste_inhalt = open(LISTE, 'rb').read()
os.remove(LISTE)
code, r = run(A)
I = by_path(r)
check('missing list: critical finding', I.get('api/lib/integritaet-liste.php', {}).get('stufe') == 'kritisch' and 'Prüfliste fehlt' in I['api/lib/integritaet-liste.php']['text'] and r['result']['ok'] is False, I.get('api/lib/integritaet-liste.php'))
with open(LISTE, 'wb') as f: f.write(liste_inhalt)
check('list restored: clean again', run(A)[1]['result']['ok'])

# ---------- Datenbankordner ----------
if storage_sqlite():
    ht = os.path.join(DATA, '.sqlite', '.htaccess')
    alt = open(ht).read()
    os.remove(ht)
    I = by_path(run(A)[1])
    check('sqlite: missing folder protection reported', I.get('data/.sqlite/.htaccess', {}).get('stufe') == 'warnung', I.get('data/.sqlite/.htaccess'))
    with open(ht, 'w') as f: f.write('Require all granted\n')
    I = by_path(run(A)[1])
    check('sqlite: opened folder protection is critical', I.get('data/.sqlite/.htaccess', {}).get('stufe') == 'kritisch', I.get('data/.sqlite/.htaccess'))
    with open(ht, 'w') as f: f.write(alt)
    check('sqlite: restored protection is clean', run(A)[1]['result']['ok'])
else:
    os.makedirs(os.path.join(DATA, 'protokoll'), exist_ok=True)
    with open(os.path.join(DATA, 'protokoll', 'fremd.php'), 'w') as f: f.write('<?php system($_GET["c"]);')
    I = by_path(run(A)[1])
    check('files: document without guard in subfolder is critical', I.get('data/protokoll/fremd.php', {}).get('stufe') == 'kritisch', I.get('data/protokoll/fremd.php'))
    os.remove(os.path.join(DATA, 'protokoll', 'fremd.php'))
    check('files: clean again', run(A)[1]['result']['ok'])

# ---------- Automatische Prüfung bei veraltetem Stand ----------
d = doc('integritaet')
hist = len(d['history'])
alt = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 2 * 86400))
d['last']['ranAt'] = alt; d['autoDay'] = ''
storage_write('integritaet', d)
code, r = A.call('security_integrity')
check('stale result: view runs automatically', code == 200 and r['result']['ranAt'] != alt and r['result']['auto'] is True and len(r['history']) == min(20, hist + 1), (r['result']['ranAt'], len(r['history'])))
d = doc('integritaet')
d['last']['ranAt'] = alt
storage_write('integritaet', d)
code, r = A.call('security_integrity')
check('at most once a day', code == 200 and r['result']['ranAt'] == alt, r['result']['ranAt'])
check('history keeps at most 20 runs', len(r['history']) <= 20)

smtp.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
