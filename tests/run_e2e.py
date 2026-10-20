"""Startet für jede Testgruppe einen frischen PHP-Server mit Testdaten und führt die Ende-zu-Ende-Tests aus.

    python3 tests/run_e2e.py              # alle Gruppen (parallel, WA_JOBS Gruppen gleichzeitig)
    python3 tests/run_e2e.py users geo    # nur bestimmte
    WA_JOBS=1 python3 tests/run_e2e.py    # nacheinander (z. B. zur Fehlersuche)

Jede gleichzeitig laufende Gruppe bekommt eigene Ports (Webserver, Hilfsserver, Test-Mailserver);
die Tests lesen sie aus WA_BASE, WA_AUX_PORT, WA_SMTP_PORT und WA_SMTP_PORT2.

Jede Gruppe läuft gegen eine eigene Kopie von app/ mit eigenem Datenordner (nie gegen echte Daten).
Exit-Code 0 nur, wenn alle Prüfungen aller Gruppen bestanden sind.
"""
import json, os, queue, re, shutil, signal, socket, subprocess, sys, threading, time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
WORK = os.path.join(REPO, 'tests', '.arbeit')
GUARD = "<?php http_response_code(404); exit; ?>\n"
ADMIN_PW = 'Sicheres-Passwort-1'

# Gruppe → (Port, Testdaten, Administrator vorab anlegen)
SUITES = {
    'storage': (8790, 'data-seed', True),
    'wartung':    (8790, 'data-seed', True),
    'gemeinsam':  (8790, 'data-seed', True),
    'legal_pages': (8790, 'data-seed', True),
    'sys':        (8765, 'data-seed-clean', False),
    'frontend':   (8765, 'data-seed', False),
    'design':     (8765, 'data-seed', False),
    'hist':       (8780, 'data-seed', False),
    'users':      (8790, 'data-seed', True),
    'master':     (8790, 'data-seed', True),
    'stock':      (8790, 'data-seed', True),
    'stock_overview': (8790, 'data-seed', True),
    'editor_aux': (8790, 'data-seed', True),
    'admin_confirmation': (8790, 'data-seed', True),
    'admin_confirmation_ui': (8790, 'data-seed', True),
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
    'restposten': (8790, 'data-seed', True, {
        'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': '2526', 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
        'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'MAIL_FROM_NAME': 'Standard-Fleisch',
        'MAIL_REPLY_TO': 'verkauf@example.org', 'WA_URL': 'http://127.0.0.1:8790'}),
    'bestellung': (8790, 'data-seed', True, {
        'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': '2526', 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
        'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'MAIL_FROM_NAME': 'Standard-Fleisch',
        'MAIL_REPLY_TO': 'verkauf@example.org', 'WA_URL': 'http://127.0.0.1:8790'}),
}
SUITES['order_outbox_ui'] = SUITES['bestellung']
SUITES['testumgebung'] = (8790, 'data-seed', True, {'WA_TESTUMGEBUNG': '1', 'WA_URL': 'http://127.0.0.1:8790'})
SUITES['order_outbox'] = SUITES['bestellung']
SUITES['order_management'] = SUITES['bestellung']
SUITES['order_management_ui'] = SUITES['bestellung']
SUITES['benachrichtigung'] = SUITES['bestellung']
SUITES['einkauf'] = SUITES['bestellung']
SUITES['sicherheit_it'] = SUITES['bestellung']
SUITES['versand'] = SUITES['kunden_mail']
SUITES['angebotsliste'] = (8790, 'data-seed', True)
SUITES['rechte'] = SUITES['kunden_mail']
SUITES['app_api'] = SUITES['bestellung']
SUITES['web_app'] = (8790, 'data-seed', True)
SUITES['kundengruppen'] = (8790, 'data-seed', True)
SUITES['einzelangebote'] = SUITES['bestellung']
SUITES['app_web'] = SUITES['bestellung']   # App (mobile/) als Web-Build; braucht mobile/dist-web
# Gruppen, die einen vorherigen Build brauchen: im vollen Lauf nur, wenn der Build vorliegt (sonst Hinweis)
OPTIONAL = {'app_web': os.path.join(REPO, 'mobile', 'dist-web', 'index.html')}
SUITES['auswertung'] = (8790, 'data-seed', True, {'WA_ORT_URL': 'http://127.0.0.1:{AUX}/dbip-city-lite-%s.csv.gz'})
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
    with open(os.path.join(data, 'admin.php'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(GUARD + json.dumps({'hash': h, 'created': '2026-10-01T00:00:00Z'}))


def sqlite_test_seed(data):
    """Windows-only fresh test fixture; production migration still runs on Linux/CI.

    No live data, locks or migration tooling are changed. Read the schema constant without
    importing the Linux deployment module (fcntl is unavailable on Windows).
    """
    import ast
    import sqlite3
    from pathlib import Path
    root = Path(data).resolve()
    if root.parent.parent != Path(WORK).resolve() or root.name != 'data':
        raise ValueError('SQLite seed must stay inside a fresh test app')
    source = Path(REPO, 'deploy', 'datenbank.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    schema = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SCHEMA' for t in n.targets))
    (root / '.sqlite').mkdir()
    with sqlite3.connect(root / '.sqlite/store.sqlite') as db:
        db.executescript(schema)
        for p in root.rglob('*.php'):
            if p.name == 'index.php':
                continue
            raw = p.read_text(encoding='utf-8')
            if not raw.startswith(GUARD):
                raise ValueError('Test fixture missing file guard')
            value = json.loads(raw[len(GUARD):])
            db.execute('INSERT INTO documents VALUES(?,?,?)', (p.relative_to(root).with_suffix('').as_posix(), json.dumps(value), int(p.stat().st_mtime)))
    (root / '.sqlite-active').write_text('1\n', encoding='utf-8')


SLOTS = queue.Queue()
PRINT = threading.Lock()


def ports(slot):
    """Webserver, Hilfsserver, Test-Mailserver 1 und 2 eines Arbeitsplatzes."""
    b = 9100 + slot * 10
    return b, b + 1, b + 2, b + 3


def run(name):
    slot = SLOTS.get()
    try:
        return run_in(name, slot)
    except Exception as e:   # z. B. Zeitüberschreitung: als Fehlschlag melden, Lauf fortsetzen
        with PRINT: print(f'[{name}] Abbruch: {e!r}  ← FEHLGESCHLAGEN', flush=True)
        return name, 0, 1, False
    finally:
        SLOTS.put(slot)


def run_in(name, slot):
    _, seed, admin, *extra = SUITES[name]
    port, aux, smtp1, smtp2 = ports(slot)
    base = f'http://127.0.0.1:{port}'
    php_env = {k: v for k, v in os.environ.items() if not k.startswith('MAIL_') and k not in ('WA_URL', 'DOMAIN')}
    php_env.update(extra[0] if extra else {})
    if 'MAIL_SMTP_PORT' in php_env: php_env['MAIL_SMTP_PORT'] = str(smtp1)
    if 'WA_URL' in php_env: php_env['WA_URL'] = base
    if 'WA_ORT_URL' in php_env: php_env['WA_ORT_URL'] = php_env['WA_ORT_URL'].replace('{AUX}', str(aux))
    lines = []
    say = lines.append
    app = os.path.join(WORK, f'app-{name}')
    shutil.rmtree(app, ignore_errors=True)
    shutil.copytree(os.path.join(REPO, 'app'), app)
    data = os.path.join(app, 'data')
    shutil.rmtree(data)
    shutil.copytree(os.path.join(FIX, seed), data)
    if admin:
        admin_file(data)
    if os.environ.get('WA_TEST_STORAGE') == 'sqlite':
        if os.name == 'nt':
            sqlite_test_seed(data)
        else:
            subprocess.run([sys.executable, os.path.join(REPO, 'deploy/datenbank.py'), 'migrate', data, '--offline'], check=True, capture_output=True)
    if not wait_port(port, up=False, timeout=5):
        with PRINT: print(f'[{name}] Port {port} ist belegt')
        return name, 0, 1, False
    sessions = os.path.join(WORK, f'sessions-{name}')
    shutil.rmtree(sessions, ignore_errors=True)
    os.makedirs(sessions)
    log = open(os.path.join(WORK, f'php-{name}.log'), 'w')
    srv = subprocess.Popen(['php', '-d', 'session.save_path=' + sessions, '-S', f'127.0.0.1:{port}'], cwd=app, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=php_env)
    try:
        wait_port(port)
        env = {**os.environ, 'UDATA': data, 'WA_WORK': WORK, 'WA_SESSION_DIR': sessions,
               'WA_BASE': base, 'WA_AUX_PORT': str(aux), 'WA_SMTP_PORT': str(smtp1), 'WA_SMTP_PORT2': str(smtp2)}
        t0 = time.time()
        p = subprocess.run([sys.executable, os.path.join(REPO, 'tests', 'e2e', f'test_{name}.py')], cwd=os.path.join(REPO, 'tests', 'e2e'),
                           env=env, capture_output=True, text=True, timeout=900)
        out = p.stdout + p.stderr
        m = re.findall(r'(\d+)/(\d+) passed', out)
        ok_n, total = (int(m[-1][0]), int(m[-1][1])) if m else (0, 0)
        good = p.returncode == 0 and total > 0 and ok_n == total
        for line in out.splitlines():
            if line.startswith('FAIL') or 'Traceback' in line or 'Error' in line[:40]:
                say(f'[{name}] {line[:300]}')
        say(f'[{name}] {ok_n}/{total} bestanden in {time.time() - t0:.0f} s' + ('' if good else '  ← FEHLGESCHLAGEN'))
        with open(os.path.join(WORK, f'test-{name}.log'), 'w') as fh: fh.write(out)   # volle Ausgabe (CI-Artefakt)
        if not good:
            say(out[-2500:] if not m else '\n'.join(l for l in out.splitlines()[-30:] if not l.startswith('PASS')))
        with PRINT: print('\n'.join(lines), flush=True)
        return name, ok_n, total, good
    finally:
        if os.name == 'nt':
            srv.terminate()
        else:
            os.killpg(srv.pid, signal.SIGTERM)
        srv.wait(timeout=10)
        wait_port(port, up=False)


def main():
    names = sys.argv[1:] or [n for n in SUITES if n not in OPTIONAL or os.path.isfile(OPTIONAL[n])]
    for n, f in OPTIONAL.items():
        if not sys.argv[1:] and not os.path.isfile(f):
            print(f'Hinweis: Gruppe {n} übersprungen – Build fehlt ({os.path.relpath(f, REPO)}; siehe tests/README.md)')
    unknown = [n for n in names if n not in SUITES]
    if unknown: sys.exit('Unbekannte Testgruppe: ' + ', '.join(unknown))
    os.makedirs(WORK, exist_ok=True)
    jobs = max(1, min(int(os.environ.get('WA_JOBS') or min(4, max(2, os.cpu_count() or 2))), len(names)))
    for i in range(jobs): SLOTS.put(i)
    t0 = time.time()
    # Lange Gruppen zuerst, damit am Ende nicht eine einzelne Gruppe allein läuft
    slow = ['kunden_mail', 'kunden', 'security', 'bestellung', 'users', 'gemeinsam', 'sys', 'restposten', 'angebote', 'hist', 'frontend', 'geo']
    order = sorted(names, key=lambda n: slow.index(n) if n in slow else len(slow))
    res = {}
    def worker(items):
        while True:
            try: n = items.get_nowait()
            except queue.Empty: return
            res[n] = run(n)
    items = queue.Queue()
    for n in order: items.put(n)
    threads = [threading.Thread(target=worker, args=(items,)) for _ in range(jobs)]
    for t in threads: t.start()
    for t in threads: t.join()
    flaky = []
    retry = [n for n in names if not res[n][3]]
    # Einmalige Wiederholung fehlgeschlagener Gruppen allein (ohne Parallellast). Besteht sie dann, gilt sie als
    # wackelig: der Lauf bleibt grün, die Gruppe wird aber deutlich gemeldet (GitHub-Warnung) und muss stabilisiert werden.
    if retry and os.environ.get('WA_RETRY', '1') != '0' and len(retry) <= 3:
        print(f'\nWiederhole allein: {", ".join(retry)}')
        for n in retry:
            log = os.path.join(WORK, f'test-{n}.log')
            if os.path.isfile(log): shutil.copy(log, os.path.join(WORK, f'test-{n}-fehlversuch.log'))
            r = run(n)
            if r[3]:
                flaky.append(n); res[n] = r
    res = [res[n] for n in names]
    print(f'Laufzeit {time.time() - t0:.0f} s mit {jobs} parallelen Gruppen')
    for n in flaky:
        print(f'::warning::Testgruppe {n} erst bei Wiederholung bestanden (wackelig) – bitte stabilisieren, Ausgabe in tests/.arbeit/test-{n}.log')
    passed = sum(r[1] for r in res); total = sum(r[2] for r in res)
    bad = [r[0] for r in res if not r[3]]
    print(f'\nGesamt: {passed}/{total} Prüfungen bestanden' + (f' – fehlgeschlagen: {", ".join(bad)}' if bad else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
