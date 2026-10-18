"""Gemeinsame Pfade für die Ende-zu-Ende-Tests (gesetzt vom Testlauf tests/run_e2e.py)."""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
SH = os.environ.get('WA_SHOTS') or os.path.join(REPO, 'tests', '.ergebnisse')
os.makedirs(SH, exist_ok=True)
WORK = os.environ.get('WA_WORK') or os.path.join(REPO, 'tests', '.arbeit')
os.makedirs(WORK, exist_ok=True)
XL44 = os.path.join(FIX, 'angebote', 'Wochenangebot KW 44 2026.xlsx')


def storage_raw(name):
    """Inspect actual persisted state, without going through the application API."""
    import sqlite3
    data = os.environ['UDATA']
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
    """Gespeichertes Dokument direkt ändern (Testvorbereitung, z. B. Zeitablauf simulieren)."""
    import json
    import sqlite3
    import time
    data = os.environ['UDATA']
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if storage_sqlite():
        with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
            db.execute('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime',
                       (name, raw, int(time.time())))
        return
    with open(data + '/' + name + '.php', 'w', encoding='utf-8') as f:
        f.write(GUARD + raw)


def storage_docs(prefix=None):
    """Alle gespeicherten Geschäftsdokumente {Name: Inhalt} – unabhängig von der Speicherart."""
    import sqlite3
    from pathlib import Path
    data = os.environ['UDATA']
    if storage_sqlite():
        with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
            rows = db.execute('SELECT name,payload FROM documents ORDER BY name').fetchall()
        return {n: p for n, p in rows if prefix is None or n.startswith(prefix + '/')}
    root = Path(data)
    out = {}
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
        data = os.environ['UDATA']
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
