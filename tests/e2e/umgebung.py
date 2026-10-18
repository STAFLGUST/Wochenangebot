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
