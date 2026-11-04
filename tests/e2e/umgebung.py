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


# Getrennte Daten (ADR-007, WA_TEST_TRENNUNG): die Hilfen lesen und schreiben Dokumente so, wie der Testserver sie sieht –
# als Mitarbeiterseite (WA_DATEN_INTERN gesetzt) maßgeblich innen, als Kundenseite (Gruppe datentrennung) nur den gemeinsamen Ordner.
MITARBEITERSEITE = bool(os.environ.get('WA_DATEN_INTERN'))


def _trennung():
    """(Modul deploy/daten_trennen.py, Trennstufe aus dem Kennzeichen) bei getrennten Testdaten, sonst None"""
    data = os.environ['UDATA']
    if not os.path.isfile(data + '/.daten-getrennt'):
        return None
    import sys
    from pathlib import Path
    sys.path.insert(0, os.path.join(REPO, 'deploy'))
    import daten_trennen
    return daten_trennen, daten_trennen.stufe_lesen(Path(data))


def datenordner(name):
    """Ordner eines Dokuments: nach der Datentrennung liegen interne Dokumente in UINTERN; veröffentlichte (Stufe 3) und je Seite
    getrennte (Stufe 5) liest die Mitarbeiterseite innen, die Kundenseite im gemeinsamen Ordner"""
    t = _trennung()
    if not t:
        return os.environ['UDATA']
    dt, stufe = t
    if MITARBEITERSEITE and (name in dt.veroeffentlicht(stufe=stufe) or name in dt.je_seite(stufe=stufe)):
        return os.environ['UINTERN']
    return os.environ['UINTERN'] if dt.ist_intern(name, dt.kundenseite(stufe=stufe)) else os.environ['UDATA']


def trennstufe():
    """Trennstufe der Testdaten (0 = nicht getrennt)"""
    t = _trennung()
    return t[1] if t else 0


def ablageordner():
    """Ordner mit der Dateiablage dateien/ (QS-Dateien): nach der Datentrennung immer innen"""
    return os.environ['UINTERN'] if _trennung() else os.environ['UDATA']


def _kunden_geteilt():
    """Kundendokument geteilt (ab Stufe 2: Portalfelder in kunden, übrige in kundenstamm) und der Testserver sieht beide Teile"""
    t = _trennung()
    if not t or not MITARBEITERSEITE:
        return None
    dt, stufe = t
    return dt if dt.ist_intern('kundenstamm', dt.kundenseite(stufe=stufe)) else None


def _json(raw):
    import json
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


def storage_raw(name):
    """Inspect actual persisted state, without going through the application API. Das geteilte Kundendokument liefert die
    Mitarbeiterseite zusammengesetzt wie customers_load() (Portalfelder aus kunden, übrige aus kundenstamm)."""
    if name == 'kunden' and _kunden_geteilt():
        import json
        d, st = _json(_storage_raw(os.environ['UDATA'], 'kunden')), _json(_storage_raw(os.environ['UINTERN'], 'kundenstamm'))
        if not isinstance(d, dict) or not isinstance(d.get('customers'), list):
            return _storage_raw(os.environ['UDATA'], 'kunden')
        m = (st or {}).get('customers') if isinstance((st or {}).get('customers'), dict) else {}
        d['customers'] = [{**c, **{k: v for k, v in (m.get(c.get('id')) or {}).items() if k not in c}} if isinstance(c, dict) else c
                          for c in d['customers']]
        raw = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
        return raw if storage_sqlite() else GUARD + raw
    return _storage_raw(datenordner(name), name)


def _storage_raw(data, name):
    import sqlite3
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
    """Gespeichertes Dokument direkt ändern (Testvorbereitung, z. B. Zeitablauf simulieren). Wie die Mitarbeiterseite:
    veröffentlichte Dokumente (ab Trennstufe 3) maßgeblich innen und als Kopie im gemeinsamen Ordner, das geteilte
    Kundendokument (ab Stufe 2) aufgeteilt wie customers_save() in kunden (Portalfelder) und kundenstamm."""
    t = _trennung()
    if name == 'kunden' and isinstance(value, dict) and isinstance(value.get('customers'), list) and _kunden_geteilt():
        dt = t[0]
        felder = set(dt.kunden_felder())
        portal, stamm = [], {}
        for c in value['customers']:
            p = {k: v for k, v in c.items() if k in felder}
            if 'email' in c:
                p['emailMaske'] = dt.email_maske(c.get('email'))
            portal.append(p)
            stamm[c['id']] = {k: v for k, v in c.items() if k not in felder and k != 'id'}
        _storage_write(os.environ['UINTERN'], 'kundenstamm', {'customers': stamm, 'updatedAt': value.get('updatedAt')})
        _storage_write(os.environ['UDATA'], 'kunden', {**value, 'customers': portal})
        return
    if t and name in t[0].veroeffentlicht(stufe=t[1]):
        _storage_write(os.environ['UINTERN'], name, value)
        _storage_write(os.environ['UDATA'], name, value)
        return
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
