"""Daten trennen (ADR-007 Stufe 2): interne Dokumente aus daten/ in daten-intern/ verschieben – bzw. zurückführen.

Nur offline (Anwendung gestoppt), aufgerufen von deploy/daten-trennen.sh. Welche Dokumente die Kundenseite braucht, steht in
regeln/datenverantwortung.toml (Feld bereich) – dieselbe Quelle wie app/api/lib/datenbereiche-liste.php. Führt nie PHP aus.

  python3 deploy/daten_trennen.py pruefen         daten daten-intern   Plan anzeigen, nichts ändern
  python3 deploy/daten_trennen.py trennen         daten daten-intern --offline
  python3 deploy/daten_trennen.py zusammenfuehren daten daten-intern --offline

Ablauf beim Trennen: interne Dokumente (Dateien bzw. Zeilen der SQLite-Datenbank) und die Dateiablage dateien/ nach
daten-intern kopieren und vergleichen, dann die Kennzeichen setzen (daten-intern/.daten-intern, zuletzt daten/.daten-getrennt –
erst damit liest die Anwendung dort), dann die Originale im gemeinsamen Ordner entfernen. Ein Abbruch vor dem Kennzeichen lässt
alles wie vorher; ein Abbruch danach lässt nur Kopien zurück, die ein erneutes `trennen` entfernt. Zusammenführen umgekehrt.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datenbank as db  # noqa: E402  GUARD, SIDECARS, SCHEMA, document_path, validate, connect

MARKER_HAUPT = '.daten-getrennt'
MARKER_INTERN = '.daten-intern'
REGELN = Path(__file__).resolve().parent.parent / 'regeln' / 'datenverantwortung.toml'


def kundenseite(regeln=REGELN):
    namen, praefixe = set(), []
    with open(regeln, 'rb') as f:
        for d in tomllib.load(f)['dokument']:
            if d.get('bereich') == 'kundenseite':
                n = d['name']
                if n.endswith('/*'):
                    praefixe.append(n[:-1])
                else:
                    namen.add(n)
    if not namen:
        raise ValueError('Keine Dokumente der Kundenseite in ' + str(regeln) + ' – Feld bereich fehlt?')
    return namen, praefixe


def ist_intern(name, ks):
    """Wie store_bereich() in app/api/storage.php: Sidecars und Dokumente der Kundenseite bleiben im gemeinsamen Ordner."""
    namen, praefixe = ks
    if name in db.SIDECARS or name in namen:
        return False
    return not any(name.startswith(p) or name + '/' == p for p in praefixe)


def interne_dateien(root, ks):
    """Datendateien (*.php) interner Dokumente im Ordner – im SQLite-Modus auch übrig gebliebene alte Dateien."""
    out = []
    for p in sorted(root.rglob('*.php')):
        rel = p.relative_to(root)
        if rel.parts[0] == 'dateien' or not db.document_path(rel):
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError('Unerwarteter Eintrag (Verweis oder Sonderdatei): ' + str(rel))
        if ist_intern(str(rel.with_suffix('')), ks):
            out.append(rel)
    return out


def ablage_dateien(root):
    d = root / 'dateien'
    if not d.exists():
        return []
    if d.is_symlink() or not d.is_dir():
        raise ValueError('dateien/ ist kein Ordner')
    out = []
    for p in sorted(d.rglob('*')):
        if p.is_symlink():
            raise ValueError('Verweis in der Dateiablage: ' + str(p.relative_to(root)))
        if p.is_file():
            out.append(p.relative_to(root))
    return out


def sqlite_aktiv(root):
    return (root / '.sqlite-active').is_file()


def interne_zeilen(root, ks):
    if not sqlite_aktiv(root):
        return []
    with db.connect(root) as c:
        return [r for r in db.validate(c) if ist_intern(r[0], ks)]


def leer(intern):
    """Zielordner ohne Daten (Kennzeichen, Sperrdateien und leere Ordner sind erlaubt)."""
    if not intern.exists():
        return True
    for p in intern.rglob('*'):
        if p.is_file() and not (p.name == '.storage.lock' or (p.name.startswith('.') and p.name.endswith('.lock'))):
            return False
    return True


def kopieren(quelle, ziel, rel):
    s, z = quelle / rel, ziel / rel
    z.parent.mkdir(parents=True, exist_ok=True)
    tmp = z.with_name(z.name + '.kopie')
    shutil.copy2(s, tmp)
    if tmp.read_bytes() != s.read_bytes():
        tmp.unlink()
        raise ValueError('Kopie weicht ab: ' + str(rel))
    tmp.replace(z)


def ordner_aufraeumen(root, rels):
    for d in sorted({(root / r).parent for r in rels}, key=lambda d: len(d.parts), reverse=True):
        while d != root and root in d.parents:
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent


def db_anlegen(ziel, zeilen):
    """Neue Datenbank im Zielordner mit genau diesen Zeilen (wie datenbank.py migrate: erst komplett, dann aktiv)."""
    stage = Path(tempfile.mkdtemp(prefix='.sqlite-stage-', dir=ziel))
    try:
        (stage / '.htaccess').write_text('Require all denied\n')
        with sqlite3.connect(stage / 'store.sqlite') as c:
            c.executescript(db.SCHEMA)
            c.executemany('INSERT INTO documents VALUES(?,?,?)', zeilen)
            c.commit()
            if db.validate(c) != sorted(zeilen):
                raise ValueError('Vergleich der neuen Datenbank fehlgeschlagen')
        os.chmod(stage / 'store.sqlite', 0o600)
        stage.rename(ziel / '.sqlite')
        m = ziel / '.sqlite-active.tmp'
        m.write_text('1\n'); m.replace(ziel / '.sqlite-active')
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def kennzeichen(p):
    t = p.with_name(p.name + '.tmp')
    t.write_text('1\n'); t.replace(p)


def plan(haupt, intern, ks):
    getrennt = (haupt / MARKER_HAUPT).is_file()
    dateien = interne_dateien(haupt, ks)
    zeilen = interne_zeilen(haupt, ks)
    ablage = ablage_dateien(haupt)
    print(f"Zustand: {'getrennt' if getrennt else 'gemeinsam'}; Speicher: {'SQLite' if sqlite_aktiv(haupt) else 'Dateien'}")
    print(f'Interne Dokumente im gemeinsamen Ordner: {len(zeilen)} in der Datenbank, {len(dateien)} als Datei, {len(ablage)} Dateien in der Ablage')
    for name, _, _ in zeilen[:200]:
        print('  ' + name)
    for rel in dateien[:200]:
        print('  ' + str(rel))
    return getrennt, dateien, zeilen, ablage


def trennen(haupt, intern, ks):
    getrennt, dateien, zeilen, ablage = plan(haupt, intern, ks)
    if not getrennt:
        if not leer(intern):
            raise ValueError('daten-intern enthält schon Daten – erst prüfen (z. B. Rest eines Abbruchs), dann leeren')
        if (intern / '.sqlite').exists() or (intern / '.sqlite-active').exists():
            raise ValueError('daten-intern enthält schon eine Datenbank')
        # 1. kopieren und vergleichen – der gemeinsame Ordner bleibt unverändert
        if sqlite_aktiv(haupt):
            db_anlegen(intern, zeilen)
        for rel in dateien + ablage:
            kopieren(haupt, intern, rel)
        # 2. umschalten: erst der interne Ordner, zuletzt der gemeinsame (ab hier liest die Anwendung intern)
        kennzeichen(intern / MARKER_INTERN)
        kennzeichen(haupt / MARKER_HAUPT)
    else:
        if not (intern / MARKER_INTERN).is_file():
            raise ValueError('daten/ ist als getrennt markiert, daten-intern aber nicht – nicht automatisch reparieren')
        # erneuter Aufruf nach einem Abbruch: nur Kopien entfernen, deren Gegenstück im internen Ordner gleich ist
        if zeilen:
            if not sqlite_aktiv(intern):
                raise ValueError('Interne Zeilen im gemeinsamen Datenbestand, aber keine Datenbank in daten-intern')
            with db.connect(intern) as c:
                dort = {n: (v, t) for n, v, t in db.validate(c)}
            for n, v, t in zeilen:
                if dort.get(n) is None or json.loads(dort[n][0]) != json.loads(v):
                    raise ValueError('Abweichender Stand für ' + n + ' – nicht automatisch entfernen')
        for rel in dateien + ablage:
            if not (intern / rel).is_file() or (intern / rel).read_bytes() != (haupt / rel).read_bytes():
                raise ValueError('Abweichende oder fehlende Kopie: ' + str(rel) + ' – nicht automatisch entfernen')
    # 3. Originale im gemeinsamen Ordner entfernen
    if zeilen:
        with db.connect(haupt) as c:
            c.executemany('DELETE FROM documents WHERE name=?', [(n,) for n, _, _ in zeilen])
            c.commit()
            rest = [r for r in db.validate(c) if ist_intern(r[0], ks)]
            if rest:
                raise ValueError('Interne Zeilen nicht entfernt: ' + ', '.join(r[0] for r in rest[:5]))
    for rel in dateien + ablage:
        (haupt / rel).unlink()
    ordner_aufraeumen(haupt, dateien + ablage)
    if (haupt / 'dateien').is_dir() and not any((haupt / 'dateien').iterdir()):
        (haupt / 'dateien').rmdir()
    print(f'Getrennt: {len(zeilen)} Datensätze und {len(dateien)} Datendateien sowie {len(ablage)} Dateien der Ablage liegen jetzt in daten-intern')


def zusammenfuehren(haupt, intern, ks):
    if not (haupt / MARKER_HAUPT).is_file():
        raise ValueError('Daten sind nicht getrennt – nichts zusammenzuführen')
    if not (intern / MARKER_INTERN).is_file():
        raise ValueError('daten-intern ist nicht als interner Datenordner markiert')
    if sqlite_aktiv(haupt) != sqlite_aktiv(intern):
        raise ValueError('Unterschiedliche Speicherarten in daten/ und daten-intern/ – nicht automatisch zusammenführen')
    dateien = [p.relative_to(intern) for p in sorted(intern.rglob('*.php'))
               if not any(part.startswith('.') for part in p.relative_to(intern).parts) and p.relative_to(intern).parts[0] != 'dateien']
    ablage = ablage_dateien(intern)
    zeilen = []
    if sqlite_aktiv(intern):
        with db.connect(intern) as c:
            zeilen = db.validate(c)
    for rel in dateien + ablage:
        if (haupt / rel).exists() and (haupt / rel).read_bytes() != (intern / rel).read_bytes():
            raise ValueError('Datei gibt es in beiden Ordnern mit verschiedenem Inhalt: ' + str(rel))
    # 1. zurückkopieren und vergleichen
    if zeilen:
        with db.connect(haupt) as c:
            vorhanden = {n: v for n, v, _ in db.validate(c)}
            for n, v, _ in zeilen:
                if n in vorhanden and json.loads(vorhanden[n]) != json.loads(v):
                    raise ValueError('Datensatz in beiden Datenbanken mit verschiedenem Inhalt: ' + n)
            c.executemany('INSERT OR REPLACE INTO documents VALUES(?,?,?)', zeilen)
            c.commit()
            neu = {n: v for n, v, _ in db.validate(c)}
            if any(json.loads(neu.get(n, 'null')) != json.loads(v) for n, v, _ in zeilen):
                raise ValueError('Vergleich nach dem Zurückführen fehlgeschlagen')
    for rel in dateien + ablage:
        kopieren(intern, haupt, rel)
    # 2. umschalten (ab hier liest die Anwendung wieder alles aus dem gemeinsamen Ordner)
    (haupt / MARKER_HAUPT).unlink()
    # 3. interne Kopien entfernen; Kennzeichen zuletzt
    if zeilen:
        shutil.rmtree(intern / '.sqlite')
        (intern / '.sqlite-active').unlink()
    for rel in dateien + ablage:
        (intern / rel).unlink()
    ordner_aufraeumen(intern, dateien + ablage)
    if (intern / 'dateien').is_dir() and not any((intern / 'dateien').iterdir()):
        (intern / 'dateien').rmdir()
    (intern / MARKER_INTERN).unlink()
    print(f'Zusammengeführt: {len(zeilen)} Datensätze, {len(dateien)} Datendateien und {len(ablage)} Dateien der Ablage wieder in daten/')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('befehl', choices=['pruefen', 'trennen', 'zusammenfuehren'])
    p.add_argument('daten', type=Path)
    p.add_argument('intern', type=Path)
    p.add_argument('--offline', action='store_true', help='Anwendung ist gestoppt (Pflicht für trennen/zusammenfuehren)')
    p.add_argument('--regeln', type=Path, default=REGELN)
    a = p.parse_args()
    haupt, intern = a.daten.resolve(), a.intern.resolve()
    if not haupt.is_dir():
        p.error('Datenordner fehlt: ' + str(haupt))
    if haupt == intern or haupt in intern.parents or intern in haupt.parents:
        p.error('daten-intern muss neben daten/ liegen, nicht darin')
    if a.befehl != 'pruefen' and not a.offline:
        p.error('Erst die Anwendung stoppen und --offline angeben')
    ks = kundenseite(a.regeln)
    if a.befehl == 'pruefen':
        with (haupt / '.storage.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            plan(haupt, intern, ks)
        return
    intern.mkdir(mode=0o700, exist_ok=True)
    with (haupt / '.storage.lock').open('a') as l1, (intern / '.storage.lock').open('a') as l2:
        fcntl.flock(l1, fcntl.LOCK_EX); fcntl.flock(l2, fcntl.LOCK_EX)
        if a.befehl == 'trennen':
            trennen(haupt, intern, ks)
        else:
            zusammenfuehren(haupt, intern, ks)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, KeyError) as e:
        print('Daten trennen fehlgeschlagen: ' + str(e), file=sys.stderr)
        sys.exit(1)
