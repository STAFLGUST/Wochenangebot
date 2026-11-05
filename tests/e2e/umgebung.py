"""Gemeinsame Pfade für die Ende-zu-Ende-Tests (gesetzt vom Testlauf tests/run_e2e.py)."""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
SH = os.environ.get('WA_SHOTS') or os.path.join(REPO, 'tests', '.ergebnisse')
os.makedirs(SH, exist_ok=True)
WORK = os.environ.get('WA_WORK') or os.path.join(REPO, 'tests', '.arbeit')
os.makedirs(WORK, exist_ok=True)
XL44 = os.path.join(FIX, 'angebote', 'Wochenangebot KW 44 2026.xlsx')
# Adressen des Testservers – vom Testlauf je Gruppe vergeben, damit Gruppen parallel laufen können
BASE = os.environ.get('WA_BASE', 'http://127.0.0.1:8790')
SMTP_PORT = int(os.environ.get('WA_SMTP_PORT', '2526'))
SMTP_PORT2 = int(os.environ.get('WA_SMTP_PORT2', '2527'))
AUX_PORT = int(os.environ.get('WA_AUX_PORT', '8791'))


def datenordner(name):
    """Ordner eines Dokuments: nach der Datentrennung (ADR-007 Stufe 2, WA_TEST_TRENNUNG) liegen interne Dokumente in UINTERN"""
    data = os.environ['UDATA']
    if not os.path.isfile(data + '/.daten-getrennt'):
        return data
    import sys
    sys.path.insert(0, os.path.join(REPO, 'deploy'))
    import daten_trennen
    ks = daten_trennen.kundenseite(stufe=daten_trennen.stufe_lesen(__import__('pathlib').Path(data)))   # Einteilung der Trennstufe im Kennzeichen
    return os.environ['UINTERN'] if daten_trennen.ist_intern(name, ks) else data


def storage_raw(name):
    """Inspect actual persisted state, without going through the application API."""
    import sqlite3
    data = datenordner(name)
    if os.path.isfile(data + '/.sqlite-active'):
        with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
            row = db.execute('SELECT payload FROM documents WHERE name=?', (name,)).fetchone()
            return row[0] if row else None
    path = data + '/' + name + '.php'
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


GUARD = '<?php http_response_code(404); exit; ?>\n'


def storage_sqlite():
    return os.path.isfile(os.environ['UDATA'] + '/.sqlite-active')


def storage_write(name, value):
    """Gespeichertes Dokument direkt ändern (Testvorbereitung, z. B. Zeitablauf simulieren). Veröffentlichte Dokumente (ab
    Trennstufe 3) wie die Mitarbeiterseite: maßgeblich innen und als Kopie im gemeinsamen Ordner."""
    import sys
    data = os.environ['UDATA']
    if os.path.isfile(data + '/.daten-getrennt'):
        sys.path.insert(0, os.path.join(REPO, 'deploy'))
        import daten_trennen
        from pathlib import Path
        if name in daten_trennen.veroeffentlicht(stufe=daten_trennen.stufe_lesen(Path(data))):
            _storage_write(os.environ['UINTERN'], name, value)
    _storage_write(datenordner(name), name, value)


def _storage_write(data, name, value):
    import json
    import sqlite3
    import time
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if os.path.isfile(data + '/.sqlite-active'):
        with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
            db.execute('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime',
                       (name, raw, int(time.time())))
        return
    os.makedirs(os.path.dirname(data + '/' + name + '.php'), exist_ok=True)
    with open(data + '/' + name + '.php', 'w', encoding='utf-8', newline='\n') as f:
        f.write(GUARD + raw)


def storage_docs(prefix=None):
    """Alle gespeicherten Geschäftsdokumente {Name: Inhalt} – unabhängig von der Speicherart."""
    import sqlite3
    from pathlib import Path
    ordner = [os.environ['UDATA']] + ([os.environ['UINTERN']] if os.path.isfile(os.environ['UDATA'] + '/.daten-getrennt') else [])
    if storage_sqlite():
        rows = []
        for data in ordner:
            with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
                rows += db.execute('SELECT name,payload FROM documents ORDER BY name').fetchall()
        return {n: p for n, p in sorted(rows) if prefix is None or n.startswith(prefix + '/')}
    out = {}
    for root in map(Path, ordner):
        for p in sorted(root.rglob('*.php')):
            name = str(p.relative_to(root).with_suffix(''))
            if prefix is None or name.startswith(prefix + '/'):
                out[name] = p.read_text(encoding='utf-8')
    return out


class storage_lock:
    """Hält die Schreibsperre wie ein paralleler Vorgang: Dateisperre bzw. SQLite-Schreibtransaktion."""
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        import fcntl
        import sqlite3
        data = datenordner(self.name)
        if storage_sqlite():
            self.db = sqlite3.connect(data + '/.sqlite/store.sqlite', isolation_level=None, timeout=30)
            self.db.execute('BEGIN IMMEDIATE')
        else:
            self.fh = open(data + '/.' + self.name + '.lock', 'a')
            fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        if storage_sqlite():
            self.db.execute('ROLLBACK'); self.db.close()
        else:
            fcntl.flock(self.fh, fcntl.LOCK_UN); self.fh.close()


def wait_text(page, selector, text, timeout=10000):
    """Wartet, bis ein Element den Text enthält (statt fester Wartezeit); wirft nicht – die Prüfung danach meldet den Fehler.
    Ohne JavaScript-Auswertung, funktioniert also auch unter strenger Content-Security-Policy."""
    import json
    try:
        page.wait_for_selector(f'{selector}:has-text({json.dumps(text)})', timeout=timeout)
    except Exception:
        pass
    return page


def until(cond, timeout=10.0, step=0.1):
    """Wartet, bis cond() wahr ist (Python-seitig, z. B. Anzahl von Elementen); gibt das letzte Ergebnis zurück."""
    import time
    end = time.time() + timeout
    while True:
        r = cond()
        if r or time.time() > end:
            return r
        time.sleep(step)


def shot(target, path, tries=3):
    """Bildschirmfoto für die Sichtprüfung; ein gerade neu gezeichnetes Element wird erneut versucht (kein Testfehler)."""
    import time
    for i in range(tries):
        try:
            return target.screenshot(path=path)
        except Exception as e:
            if i == tries - 1: print('Hinweis: Bildschirmfoto nicht möglich: ' + str(e).splitlines()[0])
            time.sleep(0.3)
