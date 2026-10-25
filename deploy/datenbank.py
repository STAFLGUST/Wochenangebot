"""Offline migration/rollback and online SQLite backup. Never executes PHP input."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile

GUARD = '<?php http_response_code(404); exit; ?>\n'
SIDECARS = {'mail-schluessel', 'sicherung', 'deployment'}
KEY = re.compile(r'^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$')
SCHEMA = '''CREATE TABLE documents(name TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload)), mtime INTEGER NOT NULL) WITHOUT ROWID; PRAGMA user_version=1;'''


def document_path(relative):
    """True for a data file that belongs in the database: not a dot path, geo/, index.php or a sidecar."""
    if any(part.startswith('.') for part in relative.parts) or relative.parts[0] == 'geo' or relative.name == 'index.php':
        return False
    return str(relative.with_suffix('')) not in SIDECARS


def documents(root):
    for p in sorted(root.rglob('*.php')):
        relative = p.relative_to(root)
        if p.is_symlink():
            raise ValueError('Symbolic links are not supported')
        if not document_path(relative):
            continue
        name = str(relative.with_suffix(''))
        if not KEY.fullmatch(name):
            raise ValueError('Invalid document name')
        raw = p.read_text()
        if not raw.startswith(GUARD):
            raise ValueError('Missing file guard: ' + name)
        value = json.loads(raw[len(GUARD):])
        if not isinstance(value, (dict, list)):
            raise ValueError('Invalid document: ' + name)
        yield name, json.dumps(value, ensure_ascii=False, separators=(',', ':')), int(p.stat().st_mtime)


def validate(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('Database integrity check failed')
    if db.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise ValueError('Unsupported schema')
    rows = db.execute('SELECT name,payload,mtime FROM documents ORDER BY name').fetchall()
    for name, raw, stamp in rows:
        if not KEY.fullmatch(name) or name in SIDECARS or name == 'index' or name.startswith('geo/'):
            raise ValueError('Invalid database key')
        if not isinstance(json.loads(raw), (dict, list)) or not isinstance(stamp, int):
            raise ValueError('Invalid database document')
    return rows


def connect(root):
    # mode=rw prevents accidentally creating an empty replacement when the DB is missing.
    return sqlite3.connect((root / '.sqlite/store.sqlite').resolve().as_uri() + '?mode=rw', uri=True, timeout=30)


def migrate(root):
    if (root / '.sqlite-active').exists() or (root / '.sqlite').exists():
        raise ValueError('Database already present; inspect/rename previous database before a new migration')
    rows = list(documents(root))  # Reject ALL invalid files before creating a database.
    target = root / '.sqlite'
    stage = Path(tempfile.mkdtemp(prefix='.sqlite-stage-', dir=root))
    try:
        (stage / '.htaccess').write_text('Require all denied\n')
        with sqlite3.connect(stage / 'store.sqlite') as db:
            db.executescript(SCHEMA)
            db.executemany('INSERT INTO documents VALUES(?,?,?)', rows)
            db.commit()
            if validate(db) != rows:
                raise ValueError('Migration comparison failed')
        os.chmod(stage / 'store.sqlite', 0o600)
        stage.rename(target)
        # Marker is last. Without it the application keeps using the original files.
        marker = root / '.sqlite-active.tmp'
        marker.write_text('1\n'); marker.replace(root / '.sqlite-active')
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f'{len(rows)} documents imported and verified; originals retained')


def rollback(root):
    if not (root / '.sqlite-active').is_file():
        raise ValueError('SQLite not active')
    with connect(root) as db:
        rows = validate(db)
    stage = Path(tempfile.mkdtemp(prefix='.export-', dir=root))
    try:
        for name, raw, stamp in rows:
            p = stage / (name + '.php'); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(GUARD + raw); os.utime(p, (stamp, stamp))
        if [(n, json.loads(v), t) for n, v, t in documents(stage)] != [(n, json.loads(v), t) for n, v, t in rows]:
            raise ValueError('Export comparison failed')
        wanted = {name for name, _, _ in rows}
        for p in root.rglob('*.php'):
            relative = p.relative_to(root)
            name = str(relative.with_suffix(''))
            if not document_path(relative):
                continue
            if name not in wanted:
                p.unlink()  # Do not resurrect deleted users/offers on rollback.
        for name, _, _ in rows:
            dst = root / (name + '.php'); dst.parent.mkdir(parents=True, exist_ok=True)
            (stage / (name + '.php')).replace(dst)
        (root / '.sqlite-active').unlink()  # Switch only after all current data is exported.
    finally:
        shutil.rmtree(stage)
    print(f'{len(rows)} current documents exported; SQLite deactivated')


def legacy_files(root):
    """Old data files after the switch to SQLite: same selection as documents(), never read by the application."""
    if not (root / '.sqlite-active').is_file():
        raise ValueError('SQLite not active; old data files are still the live data')
    with connect(root) as db:
        validate(db)   # only with a sound database: the files are no longer needed for anything else
    out = []
    for p in sorted(root.rglob('*.php')):
        relative = p.relative_to(root)
        if not document_path(relative):
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError('Unexpected entry (symbolic link or special file): ' + str(relative))
        out.append(p)
    return out


def _sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def legacy(root, archive):
    """List old data files or move them into a checked archive (never deletes before the archive is verified)."""
    files = legacy_files(root)
    size = sum(p.stat().st_size for p in files)
    if archive is None:
        for p in files:
            print(f'{p.stat().st_size:>10}  {p.relative_to(root)}')
        print(f'{len(files)} old data files, {size} bytes (not used while SQLite is active)')
        return
    if not files:
        print('No old data files present; nothing archived')
        return
    archive = archive.resolve()
    if archive.exists():
        raise ValueError('Archive destination must not exist')
    if root in archive.parents or archive == root:
        raise ValueError('Archive must be outside the data directory')
    expected = {str(p.relative_to(root)): (_sha(p), p.stat().st_size) for p in files}
    tmp = archive.with_name(archive.name + '.tmp')
    try:
        with tarfile.open(tmp, 'w:gz') as tar:
            for p in files:
                tar.add(p, arcname=str(p.relative_to(root)), recursive=False)
        os.chmod(tmp, 0o600)
        found = {}
        with tarfile.open(tmp, 'r:gz') as tar:
            for m in tar.getmembers():
                if not m.isfile():
                    raise ValueError('Archive check failed: unexpected entry ' + m.name)
                found[m.name] = (hashlib.sha256(tar.extractfile(m).read()).hexdigest(), m.size)
        if found != expected:
            raise ValueError('Archive check failed: contents differ from the data files')
        tmp.replace(archive)
    finally:
        if tmp.exists():
            tmp.unlink()
    for p in files:
        if _sha(p) != expected[str(p.relative_to(root))][0]:
            raise ValueError('File changed during archiving, stopped before removing: ' + str(p.relative_to(root)))
    for p in files:
        p.unlink()
    # Leave directories that still hold other entries; never touch dot directories or geo/
    for d in sorted({p.parent for p in files}, key=lambda d: len(d.parts), reverse=True):
        while d != root and root in d.parents:
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent
    print(f'{len(files)} old data files ({size} bytes) archived to {archive} and removed from the data directory')


def snapshot(root, target):
    if target.exists():
        raise ValueError('Snapshot destination must not exist')
    target.mkdir(mode=0o700, parents=True)
    if (root / '.sqlite-active').is_file():
        (target / '.sqlite').mkdir()
        with connect(root) as source, sqlite3.connect(target / '.sqlite/store.sqlite') as dest:
            source.backup(dest)
            validate(dest)
        (target / '.sqlite-active').write_text('1\n')
        (target / '.sqlite/.htaccess').write_text('Require all denied\n')
        # DB contains all business records. Operational statuses remain sidecars.
        for name in ('deployment.php', 'index.php'):
            if (root / name).is_file():
                shutil.copy2(root / name, target / name)
    else:
        raise ValueError('Snapshot command requires an active database')
    print('Consistent SQLite snapshot created and verified')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['migrate', 'rollback', 'check', 'snapshot', 'altdateien'])
    p.add_argument('directory', type=Path)
    p.add_argument('--offline', action='store_true', help='confirm app container stopped (required for migration/rollback)')
    p.add_argument('--output', type=Path)
    p.add_argument('--archiv', type=Path, help='altdateien: move old data files into this new .tar.gz (verified first)')
    a = p.parse_args(); root = a.directory.resolve()
    if not root.is_dir():
        p.error('Data directory missing')
    if a.command in ('migrate', 'rollback') and not a.offline:
        p.error('Stop application first and pass --offline')
    with (root / '.storage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if a.command in ('migrate', 'rollback') else fcntl.LOCK_SH)
        if a.command == 'migrate': migrate(root)
        elif a.command == 'rollback': rollback(root)
        elif a.command == 'altdateien': legacy(root, a.archiv)
        elif a.command == 'snapshot':
            if not a.output: p.error('--output required')
            snapshot(root, a.output)
        else:
            with connect(root) as db: print(f'{len(validate(db))} documents verified')

if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, sqlite3.Error) as e:
        print('Database operation failed: ' + str(e), file=sys.stderr)
        sys.exit(1)
