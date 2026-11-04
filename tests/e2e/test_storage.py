"""Publication persists consistently; injected storage failures never report success."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from kunden_hilfe import Client
from umgebung import datenordner

results = []
def check(name, condition):
    results.append(bool(condition)); print(('PASS ' if condition else 'FAIL ') + name)

c = Client()
check('login', c.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
model = c.call('draft')[1]['published']
model['meta']['source'] = 'Storage regression'
check('save draft', c.call('save_draft', {'model': model, 'revision': 0})[0] == 200)
# Datenbanken wie der Server sie sieht (nach der Datentrennung liegen Entwurf, Versionen, Protokoll … innen; ADR-007)
ordner = sorted({datenordner(n) for n in ('angebot', 'entwurf', 'versionen/x', 'historie/x', 'protokoll/x')})
if (Path(os.environ['UDATA']) / '.sqlite-active').is_file():
    def state():
        out = []
        for o in ordner:
            with sqlite3.connect(Path(o) / '.sqlite/store.sqlite') as db:
                out += db.execute("SELECT name,payload FROM documents WHERE name IN ('angebot','entwurf') OR name LIKE 'versionen/%' OR name LIKE 'historie/%' ORDER BY name").fetchall()
        return out
    before = state()
    with sqlite3.connect(Path(datenordner('protokoll/x')) / '.sqlite/store.sqlite') as db:
        db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON documents WHEN NEW.name LIKE 'protokoll/%' BEGIN SELECT RAISE(ABORT, 'test storage failure'); END")
    check('publication storage failure is reported', c.call('publish', {'model': model})[0] == 500)
    check('failed publication changes no offer, draft, history or version', state() == before)
    with sqlite3.connect(Path(datenordner('protokoll/x')) / '.sqlite/store.sqlite') as db:
        db.execute('DROP TRIGGER fail_audit')
check('publication succeeds after failure removed', c.call('publish', {'model': model})[0] == 200)
draft = c.call('draft')[1]
check('publication clears draft and keeps new content', draft['draft'] is None and draft['published']['meta']['source'] == 'Storage regression')
check('previous publication retained', len(c.call('versions')[1]['versions']) == 1)
check('history available', c.call('history_list')[0] == 200)
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
