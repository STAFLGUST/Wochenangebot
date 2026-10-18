"""Publication persists consistently; injected storage failures never report success."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from kunden_hilfe import Client

results = []
def check(name, condition):
    results.append(bool(condition)); print(('PASS ' if condition else 'FAIL ') + name)

c = Client()
check('login', c.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
model = c.call('draft')[1]['published']
model['meta']['source'] = 'Storage regression'
check('save draft', c.call('save_draft', {'model': model, 'revision': 0})[0] == 200)
root = Path(os.environ['UDATA'])
if (root / '.sqlite-active').is_file():
    def state(db):
        return db.execute("SELECT name,payload FROM documents WHERE name IN ('angebot','entwurf') OR name LIKE 'versionen/%' OR name LIKE 'historie/%' ORDER BY name").fetchall()
    with sqlite3.connect(root / '.sqlite/store.sqlite') as db:
        before = state(db)
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON documents WHEN NEW.name LIKE 'protokoll/%' BEGIN SELECT RAISE(ABORT, 'test storage failure'); END")
    check('publication storage failure is reported', c.call('publish', {'model': model})[0] == 500)
    with sqlite3.connect(root / '.sqlite/store.sqlite') as db:
        check('failed publication changes no offer, draft, history or version', state(db) == before)
        db.execute('DROP TRIGGER fail_audit')
check('publication succeeds after failure removed', c.call('publish', {'model': model})[0] == 200)
draft = c.call('draft')[1]
check('publication clears draft and keeps new content', draft['draft'] is None and draft['published']['meta']['source'] == 'Storage regression')
check('previous publication retained', len(c.call('versions')[1]['versions']) == 1)
check('history available', c.call('history_list')[0] == 200)
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
