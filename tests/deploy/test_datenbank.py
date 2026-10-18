"""Real PHP/SQLite, independent SQL inspection, migration failure and restore tests."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dbtools', REPO / 'deploy/datenbank.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
results = []


def check(name, condition):
    results.append(bool(condition)); print(('PASS ' if condition else 'FAIL ') + name)


def command(root, action, *args):
    return subprocess.run([sys.executable, str(REPO / 'deploy/datenbank.py'), action, str(root), *args], capture_output=True, text=True)


def php(root, code):
    prefix = '$DATA = getenv("DATA_DIR"); require getenv("STORE_LIB"); '
    return subprocess.run(['php', '-r', prefix + code], env={**os.environ, 'DATA_DIR': str(root), 'STORE_LIB': str(REPO / 'app/api/storage.php')}, capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / 'data'
    shutil.copytree(REPO / 'tests/fixtures/data-seed', root)
    (root / 'mail-schluessel.php').write_text(mod.GUARD + '{"key":"test-only"}')
    (root / 'deleted.php').write_text(mod.GUARD + '{"old":true}')
    check('offline confirmation required', command(root, 'migrate').returncode != 0)
    (root / 'broken.php').write_text(mod.GUARD + '{broken')
    check('invalid source aborts before activation', command(root, 'migrate', '--offline').returncode != 0 and not (root / '.sqlite-active').exists() and not (root / '.sqlite').exists())
    (root / 'broken.php').unlink()
    original = list(mod.documents(root))
    check('migration succeeds', command(root, 'migrate', '--offline').returncode == 0)
    with mod.connect(root) as db:
        check('every source record and timestamp preserved', mod.validate(db) == original)
        check('mail encryption key excluded from DB', not db.execute("SELECT 1 FROM documents WHERE name='mail-schluessel'").fetchone())
    check('second migration refused', command(root, 'migrate', '--offline').returncode != 0)
    r = php(root, 'store_write("new", ["value"=>42]); store_delete("deleted"); echo store_read("new")["value"];')
    check('PHP reads and writes database', r.returncode == 0 and r.stdout == '42' and not (root / 'new.php').exists())
    r = php(root, 'try { with_lock("tx", function(){ store_write("a", ["n"=>9]); store_write("b", ["n"=>9]); throw new RuntimeException("abort"); }); } catch (RuntimeException $e) {} echo json_encode([store_read("a"),store_read("b")]);')
    check('exception rolls back both records', r.returncode == 0 and r.stdout == '[null,null]')
    r = php(root, 'with_lock("outer", function(){ store_write("a", ["n"=>0]); with_lock("inner", function(){store_write("b", ["n"=>0]);});});')
    check('nested locks commit together', r.returncode == 0)
    code = 'for($i=0;$i<30;$i++){with_lock("counter", function(){ $n=store_read("a")["n"]+1; store_write("a",["n"=>$n]); usleep(2000); store_write("b",["n"=>$n]); });}'
    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = [pool.submit(php, root, code) for _ in range(4)]
        snap = Path(tmp) / 'snapshot'
        r = command(root, 'snapshot', '--output', str(snap))
        check('online snapshot succeeds while writers run', r.returncode == 0)
        check('parallel writers all finish', all(f.result().returncode == 0 for f in futures))
    with mod.connect(root) as db:
        check('no lost updates under parallel writes', json.loads(db.execute("SELECT payload FROM documents WHERE name='a'").fetchone()[0])['n'] == 120)
    with mod.connect(snap) as db:
        values = {n:json.loads(v)['n'] for n,v,_ in mod.validate(db) if n in ('a','b')}
        check('backup contains complete transaction, never half', values['a'] == values['b'])
    check('snapshot excludes mail encryption key', not (snap / 'mail-schluessel.php').exists())
    check('restored snapshot works with PHP', php(snap, 'echo store_read("new")["value"];').stdout == '42')
    (root / '.sqlite/store.sqlite').rename(root / '.sqlite/saved.sqlite')
    check('missing active DB fails closed without stale fallback', php(root, 'store_read("angebot");').returncode != 0 and not (root / '.sqlite/store.sqlite').exists())
    (root / '.sqlite/saved.sqlite').rename(root / '.sqlite/store.sqlite')
    check('rollback succeeds', command(root, 'rollback', '--offline').returncode == 0)
    check('rollback preserves latest writes and deletions', not (root / 'deleted.php').exists() and php(root, 'echo store_read("new")["value"];').stdout == '42' and php(root, 'echo store_read("a")["n"];').stdout == '120')
    check('rollback retains separate encryption key', (root / 'mail-schluessel.php').exists())
    check('bad path rejected', php(root, 'store_read("../outside");').returncode != 0)

print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
