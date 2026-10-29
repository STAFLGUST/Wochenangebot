"""Startet für jede Testgruppe einen frischen PHP-Server mit Testdaten und führt die Ende-zu-Ende-Tests aus.

    python3 tests/run_e2e.py              # alle Gruppen (parallel, WA_JOBS Gruppen gleichzeitig)
    python3 tests/run_e2e.py users geo    # nur bestimmte
    WA_JOBS=1 python3 tests/run_e2e.py    # nacheinander (z. B. zur Fehlersuche)
    WA_TEIL=2/3 python3 tests/run_e2e.py  # nur Teil 2 von 3 (CI: Aufträge je Speicherart und Teil, siehe teile())

Jede gleichzeitig laufende Gruppe bekommt eigene Ports (Webserver, Hilfsserver, Test-Mailserver);
die Tests lesen sie aus WA_BASE, WA_AUX_PORT, WA_SMTP_PORT und WA_SMTP_PORT2.

Jede Gruppe läuft gegen eine eigene Kopie von app/ mit eigenem Datenordner (nie gegen echte Daten).
Exit-Code 0 nur, wenn alle Prüfungen aller Gruppen bestanden sind.
"""
import importlib.util, json, os, pathlib, queue, re, shutil, signal, socket, subprocess, sys, threading, time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
WORK = os.path.join(REPO, 'tests', '.arbeit')
GUARD = "<?php http_response_code(404); exit; ?>\n"
# Bereitstellung wie beim Einspielen auf dem Server (Versionsnummern der Skripte/Stylesheets, Prüfliste der Dateiprüfung)
_spec = importlib.util.spec_from_file_location('bereitstellen', os.path.join(REPO, 'deploy', 'bereitstellen.py'))
BEREITSTELLEN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BEREITSTELLEN)
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
    'bestaetigung': (8790, 'data-seed', True),
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
SUITES['vkgruppen'] = (8790, 'data-seed', True)
SUITES['kundenimport'] = SUITES['bestellung']
SUITES['vertreter'] = SUITES['bestellung']
SUITES['sicherheit_freigaben'] = SUITES['bestellung']
SUITES['schutz'] = SUITES['bestellung']
SUITES['nutzer_anlegen'] = SUITES['bestellung']
SUITES['mhd_mail'] = SUITES['bestellung']   # MHD-Liste an den Verkauf (Test-Mailserver)
SUITES['mail_intern'] = SUITES['bestellung']   # Postfach für interne E-Mails (zweiter Test-Mailserver)
SUITES['fehlerpruefung'] = SUITES['bestellung']
SUITES['sicherheit_druck'] = SUITES['bestellung']
SUITES['integritaet'] = SUITES['bestellung']   # Dateiprüfung; Test-Mailserver für die Benachrichtigung
SUITES['geraete'] = SUITES['bestellung']   # vertraute Geräte
SUITES['bestand_pdf'] = (8790, 'data-seed', True)   # Bestand: Marke, MHD-Farben, PDF
SUITES['passwortpruefung'] = (8790, 'data-seed', True, {'WA_PWNED_URL': 'http://127.0.0.1:{AUX}/range/%s'})   # Datenleck-Prüfung (nachgebauter Dienst)
SUITES['app_web'] = SUITES['bestellung']   # App (mobile/) als Web-Build; braucht mobile/dist-web
# Gruppen, die einen vorherigen Build brauchen: im vollen Lauf nur, wenn der Build vorliegt (sonst Hinweis)
OPTIONAL = {'app_web': os.path.join(REPO, 'mobile', 'dist-web', 'index.html')}
SUITES['passkeys'] = (8790, 'data-seed', True)
SUITES['modul_wartung'] = (8790, 'data-seed', True)   # Wartung je Oberfläche (GR-107)
SUITES['module_status'] = (8790, 'data-seed', True)   # Modulzustand zur Laufzeit (GR-102)
SUITES['aktionsregister'] = (8790, 'data-seed', True)   # Register wirkt für jede Aktion (Schreibschutz, 404)
SUITES['protokoll'] = (8790, 'data-seed', True)   # Aufbewahrung des Aktivitätsprotokolls (6 Monate)
SUITES['herkunft'] = (8790, 'data-seed', True)   # Herkunftsprüfung im API-Einstieg (GR-109), fremde Seite auf AUX_PORT
SUITES['dashboard'] = (8790, 'data-seed', True)   # Mitarbeiter-Dashboard (dashboard/, liegt außerhalb von app/)
SUITES['oidc_kern'] = (8790, 'data-seed', True, {'WA_OIDC': '1', 'WA_OIDC_ISSUER': 'https://login.example/realms/mitarbeiter', 'WA_OBERFLAECHE': 'angebot.eingabe'})   # Keycloak-Host ohne Modul (GR-110, GR-109)
SUITES['oidc_dashboard'] = (8790, 'data-seed', True, {'WA_OIDC': '1', 'WA_OIDC_ISSUER': 'https://login.example/realms/mitarbeiter', 'WA_OBERFLAECHE': 'dashboard.start'})   # Dashboard-Host: nur Grundaktionen (GR-109)
SUITES['anmeldebremse'] = (8790, 'data-seed', True)   # Fehlversuchsbremse je Adresse, Abmelden mit CSRF, Bedrohungsliste ohne Nebenwirkung
SUITES['modulverwaltung'] = (8790, 'data-seed', True)   # Freigabe und Tester zur Laufzeit (Roadmap 5)
SUITES['sitzung_cookie'] = (8790, 'data-seed', True)   # __Host-Präfix des Sitzungs-Cookies über HTTPS (GR-108)
SUITES['auswertung'] =(8790, 'data-seed', True, {'WA_ORT_URL': 'http://127.0.0.1:{AUX}/dbip-city-lite-%s.csv.gz'})
SUITES['importzentrale'] = (8790, 'data-seed', True)   # Importzentrale (Verwaltung → Import, Roadmap 10b)
SUITES['hr'] = (8790, 'data-seed', True)   # HR · Urlaubsverwaltung (app/module/hr/, Oberfläche hr.intern)
SUITES['hr_uebersicht'] = (8790, 'data-seed', True)   # HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht)
SUITES['rollen'] = (8790, 'data-seed', True)   # Rollen und Rechte, Modulzugang je Rolle (lib/rechte.php)
SUITES['rollen_host'] = (8790, 'data-seed', True, {'WA_OBERFLAECHE': 'bestand.intern'})   # Modulzugang je Host (wie bestand.dashboard-stafl.de)
SUITES['einheit'] = (8790, 'data-seed', True)   # einheitliches Erscheinungsbild aller Mitarbeiter-Oberflächen
SUITES['stilllegung'] = (8790, 'data-seed', True, {'WA_EIGENE_ANMELDUNG': 'aus'})   # alter Eingabebereich angebot-stafl.de/admin/ stillgelegt
# Host der Anmeldeseite in der Anwendung (wie login.dashboard-stafl.de in apache-oidc.conf): Prüfung vor Keycloak (Caddy forward_auth)
SUITES['anmeldeseite'] = (8790, 'data-seed', True, {'WA_OIDC': '1', 'WA_OIDC_ISSUER': 'https://login.example/realms/mitarbeiter', 'WA_OBERFLAECHE': 'plattform.anmeldung', 'WA_EIGENE_ANMELDUNG': 'aus'})
# Adressverzeichnis der CRM-Karte (lib/adressen.php) aus erfundenen Testadressen, vor dem Lauf erzeugt (adressen_test)
ADRESSEN_TEST = os.path.join(WORK, 'adressen-test.sqlite')
SUITES['crm'] = (8790, 'data-seed', True, {'WA_ADRESSEN': ADRESSEN_TEST})   # CRM · Vertrieb (app/module/crm/, Oberfläche crm.intern)
SUITES['marketing'] = (8790, 'data-seed', True)   # Marketing · Redaktionsplan (app/module/marketing/, Oberfläche marketing.intern)
SUITES['controlling'] = (8790, 'data-seed', True)   # Controlling · Umsatzstatistik (app/module/controlling/, Oberfläche controlling.intern)
SUITES['sicherheit_modul'] = SUITES['bestellung']   # Modul Sicherheit (app/module/sicherheit/, Oberfläche sicherheit.intern); Test-Mailserver
SUITES['notfall'] = SUITES['bestellung']   # Notfallmodus (lib/notfall.php): Kunden-Wartung, Aussperren, Sitzungen, Mailsperre, Firewall
SUITES['sicherheit_bereitschaft'] = SUITES['bestellung']   # Leitfaden, Probealarm, Wochenbericht, ungenutzte Zugänge (lib/bereitschaft.php); Test-Mailserver
# Gruppe → zusätzliche Umgebungsvariablen für den PHP-Server (4. Eintrag, optional)

# Laufzeit je Gruppe in Sekunden (Median aus 12 CI-Aufträgen vom 22.10.2026, beide Speicherarten, 4 Gruppen parallel).
# Nur für die Startreihenfolge (lange zuerst) und die Aufteilung auf CI-Aufträge (WA_TEIL) – nicht für das Ergebnis.
# Gruppen ohne Eintrag zählen mit GEWICHT_STANDARD; Werte bei Bedarf aus den Zeilen „[gruppe] … bestanden in N s“ erneuern.
GEWICHT_STANDARD = 15
GEWICHT = {
    'sicherheit_freigaben': 118, 'security': 60, 'users': 46, 'sys': 41, 'geraete': 40, 'angebote': 38,
    'passkeys': 28, 'kunden': 28, 'revert': 26, 'hist': 25, 'master': 25, 'sidenav': 24, 'gemeinsam': 22,
    'geo': 21, 'einzelangebote': 20, 'stock': 18, 'editor_aux': 18, 'bestellung': 18, 'frontend': 18,
    'app_api': 17, 'vkgruppen': 16, 'restposten': 15, 'kunden_mail': 15, 'p0': 15, 'schutz': 15, 'rechte': 14,
    'fehlerpruefung': 14, 'kundengruppen': 13, 'importzentrale': 13, 'versand': 12, 'kundenimport': 12,
    'sicherheit_druck': 11, 'angebotsliste': 11, 'stock_overview': 11, 'sicherheit_it': 10, 'auswertung': 9,
    'benachrichtigung': 9, 'vertreter': 9, 'admin_confirmation': 8, 'einkauf': 8, 'wartung': 7,
    'order_management_ui': 7, 'nutzer_anlegen': 7, 'mhd_mail': 6, 'mail_intern': 5, 'auth_hardening': 7, 'web_app': 7, 'dashboard': 6,
    'passwortpruefung': 6, 'bestaetigung': 6, 'geo_ip': 6, 'integritaet': 6, 'sitzung_cookie': 6, 'design': 5,
    'testumgebung': 5, 'modul_wartung': 5, 'bestand_pdf': 5, 'modulverwaltung': 4, 'order_outbox_ui': 4,
    'admin_confirmation_ui': 4, 'herkunft': 4, 'legal_pages': 2, 'order_outbox': 1, 'order_management': 1,
    'module_status': 1, 'storage': 1, 'aktionsregister': 1, 'oidc_kern': 1, 'oidc_dashboard': 1, 'anmeldebremse': 2,
    'hr': 60,   # gemessen lokal (Oktober 2026), noch ohne CI-Median
    'hr_uebersicht': 15,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'stilllegung': 8,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'anmeldeseite': 5,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'crm': 45,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'sicherheit_modul': 40,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'notfall': 25,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'sicherheit_bereitschaft': 45,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'marketing': 45,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'controlling': 25,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'protokoll': 6,   # geschätzt (Oktober 2026), noch ohne CI-Median
    'rollen': 20, 'rollen_host': 8, 'einheit': 90,   # geschätzt (Oktober 2026), noch ohne CI-Median
}


def gewicht(name):
    return GEWICHT.get(name, GEWICHT_STANDARD)


def teil_lesen(text):
    """„k/n“ (1 ≤ k ≤ n) → (k, n); sonst ValueError. Leer → None (alle Gruppen)."""
    if not text:
        return None
    m = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', text)
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        raise ValueError(f'WA_TEIL muss „k/n“ mit 1 ≤ k ≤ n sein, nicht „{text}“')
    return int(m.group(1)), int(m.group(2))


def teile(namen, n):
    """Verteilt die Gruppen auf n Teile mit möglichst gleicher Laufzeit (längste zuerst in den leichtesten Teil).
    Deterministisch und unabhängig von der Reihenfolge der Eingabe; jede Gruppe landet in genau einem Teil."""
    last = [0] * n
    ergebnis = [[] for _ in range(n)]
    for name in sorted(set(namen), key=lambda g: (-gewicht(g), g)):
        i = min(range(n), key=lambda t: (last[t], t))
        ergebnis[i].append(name)
        last[i] += gewicht(name)
    return ergebnis


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
    b = int(os.environ.get("WA_PORT_BASE", "9100")) + slot * 10   # WA_PORT_BASE: getrennte Ports für parallele Läufe
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


# Noch nicht produktiv ausgelieferte Oberflächen (nicht in app/): nur in der jeweiligen Testgruppe unter dem Testserver
ZUSATZ = {'dashboard': [('dashboard', 'dashboard')], 'einheit': [('dashboard', 'dashboard')], 'rollen': [('dashboard', 'dashboard')], 'sicherheit_modul': [('dashboard', 'dashboard')]}

# Testzustand des Modulregisters für einzelne Gruppen: um Testfreigabe und Produktivfreigabe der Modulverwaltung zu
# prüfen, stellt die Gruppe zwei noch geplante Module in ihrer App-Kopie weiter (REWE: in Prüfung, Einkauf: fertig;
# Bestand ist seit Phase 1 produktiv). Nur die Kopie im Testordner; das Register im Code bleibt unverändert.
REGISTER_TEST = {'modulverwaltung': [("'rewe' => [", 'in_pruefung'), ("'einkauf' => [", 'fertig')]}


def register_anpassen(app, aenderungen):
    pfad = os.path.join(app, 'api', 'lib', 'module-liste.php')
    with open(pfad, encoding='utf-8') as f:
        zeilen = f.read().split('\n')
    for anfang, stand in aenderungen:
        i = next(n for n, z in enumerate(zeilen) if z.strip().startswith(anfang))
        assert "'entwicklung' => 'geplant'" in zeilen[i], anfang
        zeilen[i] = zeilen[i].replace("'entwicklung' => 'geplant'", f"'entwicklung' => '{stand}'", 1)
    with open(pfad, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(zeilen))


def run_in(name, slot):
    _, seed, admin, *extra = SUITES[name]
    port, aux, smtp1, smtp2 = ports(slot)
    base = f'http://127.0.0.1:{port}'
    php_env = {k: v for k, v in os.environ.items() if not k.startswith('MAIL_') and k not in ('WA_URL', 'DOMAIN')}
    php_env.update(extra[0] if extra else {})
    if 'MAIL_SMTP_PORT' in php_env: php_env['MAIL_SMTP_PORT'] = str(smtp1)
    if 'WA_URL' in php_env: php_env['WA_URL'] = base
    for k in list(php_env):   # Platzhalter {AUX} (nachgebaute externe Dienste) in allen Angaben
        if isinstance(php_env[k], str) and '{AUX}' in php_env[k]: php_env[k] = php_env[k].replace('{AUX}', str(aux))
    lines = []
    say = lines.append
    app = os.path.join(WORK, f'app-{name}')
    shutil.rmtree(app, ignore_errors=True)
    shutil.copytree(os.path.join(REPO, 'app'), app)
    BEREITSTELLEN.verzeichnis(pathlib.Path(app))   # wie der Server: ?v=… setzen, Prüfliste erzeugen
    for quelle, ziel in ZUSATZ.get(name, ()):   # Oberflächen außerhalb der Dokumentwurzel nur für ihre Gruppe einblenden
        shutil.copytree(os.path.join(REPO, quelle), os.path.join(app, ziel))
    if name in REGISTER_TEST:
        register_anpassen(app, REGISTER_TEST[name])
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
        env = {**os.environ, 'TZ': 'Europe/Berlin', 'UDATA': data, 'WA_WORK': WORK, 'WA_SESSION_DIR': sessions,   # Tests rechnen wie der Server in deutscher Zeit
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


def adressen_test():
    """Adressverzeichnis der Tests aus tests/fixtures/karte/adressen.json (deploy/karte/adressen.py, ohne pyosmium)."""
    subprocess.run([sys.executable, os.path.join(REPO, 'deploy', 'karte', 'adressen.py'), '--json',
                    os.path.join(FIX, 'karte', 'adressen.json'), ADRESSEN_TEST], check=True, capture_output=True)


def main():
    try:
        teil = teil_lesen(os.environ.get('WA_TEIL', ''))
    except ValueError as e:
        sys.exit(str(e))
    names = sys.argv[1:] or list(SUITES)
    if teil:   # Aufteilung über alle Gruppen (auch optionale), damit sie nicht davon abhängt, ob ein Build vorliegt
        names = [n for n in names if n in teile(names, teil[1])[teil[0] - 1]]
        print(f'Teil {teil[0]}/{teil[1]}: {len(names)} Gruppen ({sum(gewicht(n) for n in names)} s geschätzt): {" ".join(names)}')
    if not sys.argv[1:]:
        for n, f in OPTIONAL.items():
            if n in names and not os.path.isfile(f):
                print(f'Hinweis: Gruppe {n} übersprungen – Build fehlt ({os.path.relpath(f, REPO)}; siehe tests/README.md)')
        names = [n for n in names if n not in OPTIONAL or os.path.isfile(OPTIONAL[n])]
    unknown = [n for n in names if n not in SUITES]
    if unknown: sys.exit('Unbekannte Testgruppe: ' + ', '.join(unknown))
    if not names: sys.exit('Keine Testgruppe ausgewählt')
    os.makedirs(WORK, exist_ok=True)
    adressen_test()
    jobs = max(1, min(int(os.environ.get('WA_JOBS') or min(4, max(2, os.cpu_count() or 2))), len(names)))
    for i in range(jobs): SLOTS.put(i)
    t0 = time.time()
    # Lange Gruppen zuerst (GEWICHT), damit am Ende nicht eine einzelne Gruppe allein läuft
    order = sorted(names, key=lambda n: -gewicht(n))
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
