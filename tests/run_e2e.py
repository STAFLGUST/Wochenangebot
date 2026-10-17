"""Startet für jede Testgruppe einen frischen PHP-Server mit Testdaten und führt die Ende-zu-Ende-Tests aus.

    python3 tests/run_e2e.py              # alle Gruppen
    python3 tests/run_e2e.py users geo    # nur bestimmte

Jede Gruppe läuft gegen eine eigene Kopie von app/ mit eigenem Datenordner (nie gegen echte Daten).
Exit-Code 0 nur, wenn alle Prüfungen aller Gruppen bestanden sind.
"""
import json, os, re, shutil, signal, socket, subprocess, sys, time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
WORK = os.path.join(REPO, 'tests', '.arbeit')
GUARD = "<?php http_response_code(404); exit; ?>\n"
ADMIN_PW = 'Sicheres-Passwort-1'

# Gruppe → (Port, Testdaten, Administrator vorab anlegen)
SUITES = {
    'sys':        (8765, 'data-seed-clean', False),
    'frontend':   (8765, 'data-seed', False),
    'hist':       (8780, 'data-seed', False),
    'users':      (8790, 'data-seed', True),
    'master':     (8790, 'data-seed', True),
    'stock':      (8790, 'data-seed', True),
    'editor_aux': (8790, 'data-seed', True),
    'auth_hardening': (8790, 'data-seed', True),
    'security':   (8790, 'data-seed', True),
    'geo':        (8790, 'data-seed', True),
    'geo_ip':     (8790, 'data-seed', True),
    'revert':     (8790, 'data-seed', True),
    'sidenav':    (8790, 'data-seed', True),
    'p0':         (8790, 'data-seed', True),
    'angebote':   (8790, 'data-seed', True),
    'kunden':     (8790, 'data-seed', True),
    'kunden_mail': (8790, 'data-seed', True, {
        'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': '2526', 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
        'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'MAIL_FROM_NAME': 'Standard-Fleisch',
        'MAIL_REPLY_TO': 'verkauf@example.org', 'WA_URL': 'http://127.0.0.1:8790'}),
    'bestellung': (8790, 'data-seed', True, {
        'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': '2526', 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
        'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'MAIL_FROM_NAME': 'Standard-Fleisch',
        'MAIL_REPLY_TO': 'verkauf@example.org', 'WA_URL': 'http://127.0.0.1:8790'}),
}
# Gruppe → zusätzliche Umgebungsvariablen für den PHP-Server (4. Eintrag, optional)


def wait_port(port, up=True, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            ok = s.connect_ex(('127.0.0.1', port)) == 0
        if ok == up:
            return True
        time.sleep(0.1)
    return False


def admin_file(data):
    h = subprocess.run(['php', '-r', f'echo password_hash("{ADMIN_PW}", PASSWORD_DEFAULT);'], capture_output=True, text=True, check=True).stdout
    with open(os.path.join(data, 'admin.php'), 'w') as fh:
        fh.write(GUARD + json.dumps({'hash': h, 'created': '2026-10-01T00:00:00Z'}))


def run(name):
    port, seed, admin, *extra = SUITES[name]
    php_env = {k: v for k, v in os.environ.items() if not k.startswith('MAIL_') and k not in ('WA_URL', 'DOMAIN')}
    php_env.update(extra[0] if extra else {})
    app = os.path.join(WORK, f'app-{name}')
    shutil.rmtree(app, ignore_errors=True)
    shutil.copytree(os.path.join(REPO, 'app'), app)
    data = os.path.join(app, 'data')
    shutil.rmtree(data)
    shutil.copytree(os.path.join(FIX, seed), data)
    if admin:
        admin_file(data)
    if not wait_port(port, up=False, timeout=5):
        print(f'[{name}] Port {port} ist belegt'); return name, 0, 1, False
    log = open(os.path.join(WORK, f'php-{name}.log'), 'w')
    srv = subprocess.Popen(['php', '-S', f'127.0.0.1:{port}'], cwd=app, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=php_env)
    try:
        wait_port(port)
        env = {**os.environ, 'UDATA': data, 'WA_WORK': WORK}
        t0 = time.time()
        p = subprocess.run([sys.executable, os.path.join(REPO, 'tests', 'e2e', f'test_{name}.py')], cwd=os.path.join(REPO, 'tests', 'e2e'),
                           env=env, capture_output=True, text=True, timeout=900)
        out = p.stdout + p.stderr
        m = re.findall(r'(\d+)/(\d+) passed', out)
        ok_n, total = (int(m[-1][0]), int(m[-1][1])) if m else (0, 0)
        good = p.returncode == 0 and total > 0 and ok_n == total
        for line in out.splitlines():
            if line.startswith('FAIL') or 'Traceback' in line or 'Error' in line[:40]:
                print(f'[{name}] {line[:300]}')
        print(f'[{name}] {ok_n}/{total} bestanden in {time.time() - t0:.0f} s' + ('' if good else '  ← FEHLGESCHLAGEN'))
        if not good and not m:
            print(out[-3000:])
        return name, ok_n, total, good
    finally:
        os.killpg(srv.pid, signal.SIGTERM)
        wait_port(port, up=False)


def main():
    names = sys.argv[1:] or list(SUITES)
    os.makedirs(WORK, exist_ok=True)
    res = [run(n) for n in names]
    passed = sum(r[1] for r in res); total = sum(r[2] for r in res)
    bad = [r[0] for r in res if not r[3]]
    print(f'\nGesamt: {passed}/{total} Prüfungen bestanden' + (f' – fehlgeschlagen: {", ".join(bad)}' if bad else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
