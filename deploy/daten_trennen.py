"""Daten trennen (ADR-007 Stufe 2): interne Dokumente aus daten/ in daten-intern/ verschieben – bzw. zurückführen.

Nur offline (Anwendung gestoppt), aufgerufen von deploy/daten-trennen.sh. Welche Dokumente die Kundenseite braucht, steht in
regeln/datenverantwortung.toml (Felder bereich, trennstufe, felder_kundenseite) – dieselbe Quelle wie
app/api/lib/datenbereiche-liste.php. Führt nie PHP aus.

  python3 deploy/daten_trennen.py pruefen         daten daten-intern   Plan anzeigen, nichts ändern
  python3 deploy/daten_trennen.py trennen         daten daten-intern --offline   auf die höchste Trennstufe dieses Stands
  python3 deploy/daten_trennen.py zusammenfuehren daten daten-intern --offline   alles zurück in einen Ordner (Stufe 0)

Trennstufen (Inhalt von daten/.daten-getrennt): 1 = interne Dokumente getrennt (Stufe 2a); 2 = zusätzlich Bestand, Stammdaten,
Postfächer, Vorlage und Benachrichtigungen innen, Kundendokument geteilt (Portalfelder bleiben in kunden, alle übrigen Felder in
kundenstamm) und Empfänger der Bestellwünsche innen (bestellung-empfaenger) – Stufe 2b.

Ablauf beim Trennen: interne Dokumente (Dateien bzw. Zeilen der SQLite-Datenbank), die Dateiablage dateien/ und die neuen internen
Dokumente der Umstellung nach daten-intern kopieren und vergleichen, dann die Kennzeichen setzen (daten-intern/.daten-intern, zuletzt
daten/.daten-getrennt mit der Stufe – erst damit liest die Anwendung dort), dann im gemeinsamen Ordner bereinigen (Originale entfernen,
kunden und bestellung auf die Felder der Kundenseite kürzen). Ein Abbruch vor dem Kennzeichen lässt die Anwendung beim alten Stand;
ein Abbruch danach lässt nur Reste zurück, die ein erneutes `trennen` bereinigt. Zusammenführen umgekehrt (geteilte Dokumente werden
dabei wieder zusammengesetzt).
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
import time
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datenbank as db  # noqa: E402  GUARD, SIDECARS, SCHEMA, document_path, validate, connect

MARKER_HAUPT = '.daten-getrennt'
MARKER_INTERN = '.daten-intern'
REGELN = Path(__file__).resolve().parent.parent / 'regeln' / 'datenverantwortung.toml'
ZIELSTUFE = 2   # höchste Trennstufe dieses Stands (wie TRENNSTUFE_MAX in werkzeuge/regeln.py, DATEN_TRENNSTUFE in PHP)
# Neue interne Dokumente der Stufe 2: entstehen beim Trennen aus kunden bzw. bestellung und gehen beim Zusammenführen dort wieder auf
GETEILT = ('kundenstamm', 'bestellung-empfaenger')
AUSZUG = 'artikelauszug'   # Auszug für die Kundenseite (erzeugt die Anwendung ab Stufe 2); beim Zusammenführen entfernt


def regeln_laden(regeln=REGELN):
    with open(regeln, 'rb') as f:
        return tomllib.load(f)['dokument']


def kundenseite(regeln=REGELN, stufe=ZIELSTUFE):
    """Dokumente im gemeinsamen Ordner bei dieser Trennstufe: (Namen, Präfixe aus Mustern „name/*“) – alle anderen sind intern."""
    namen, praefixe = set(), []
    for d in regeln_laden(regeln):
        if d.get('bereich') == 'kundenseite' or (d.get('bereich') == 'intern' and d.get('trennstufe', 1) > stufe):
            n = d['name']
            if n.endswith('/*'):
                praefixe.append(n[:-1])
            else:
                namen.add(n)
    if not namen:
        raise ValueError('Keine Dokumente der Kundenseite in ' + str(regeln) + ' – Feld bereich fehlt?')
    return namen, praefixe


def kunden_felder(regeln=REGELN):
    for d in regeln_laden(regeln):
        if d.get('name') == 'kunden' and d.get('felder_kundenseite'):
            return list(d['felder_kundenseite'])
    raise ValueError('felder_kundenseite für kunden fehlt in ' + str(regeln))


def ist_intern(name, ks):
    """Wie store_bereich() in app/api/storage.php: Sidecars und Dokumente der Kundenseite bleiben im gemeinsamen Ordner."""
    namen, praefixe = ks
    if name in db.SIDECARS or name in namen:
        return False
    return not any(name.startswith(p) or name + '/' == p for p in praefixe)


def stufe_lesen(haupt):
    p = haupt / MARKER_HAUPT
    if not p.is_file():
        return 0
    try:
        return max(1, int(p.read_text().strip() or '1'))
    except ValueError:
        raise ValueError('Kennzeichen daten/' + MARKER_HAUPT + ' unlesbar – nicht automatisch reparieren')


# ─────────────── Dokumente lesen und schreiben (Dateien oder SQLite, wie app/api/storage.php) ───────────────

def sqlite_aktiv(root):
    return (root / '.sqlite-active').is_file()


def dok_lesen(root, name):
    if sqlite_aktiv(root):
        with db.connect(root) as c:
            r = c.execute('SELECT payload FROM documents WHERE name=?', (name,)).fetchone()
        return None if r is None else json.loads(r[0])
    p = root / (name + '.php')
    if not p.is_file():
        return None
    raw = p.read_text()
    if not raw.startswith(db.GUARD):
        raise ValueError('Datei ohne Schutzzeile: ' + name)
    return json.loads(raw[len(db.GUARD):])


def json_text(wert):
    return json.dumps(wert, ensure_ascii=False, separators=(',', ':'))


def dok_schreiben(root, name, wert):
    if sqlite_aktiv(root):
        with db.connect(root) as c:
            c.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)', (name, json_text(wert), int(time.time())))
            c.commit()
        if dok_lesen(root, name) != wert:
            raise ValueError('Vergleich nach dem Schreiben fehlgeschlagen: ' + name)
        return
    p = root / (name + '.php')
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.neu')
    tmp.write_text(db.GUARD + json_text(wert))
    if json.loads(tmp.read_text()[len(db.GUARD):]) != wert:
        tmp.unlink()
        raise ValueError('Vergleich nach dem Schreiben fehlgeschlagen: ' + name)
    tmp.replace(p)


def dok_loeschen(root, name):
    if sqlite_aktiv(root):
        with db.connect(root) as c:
            c.execute('DELETE FROM documents WHERE name=?', (name,))
            c.commit()
    p = root / (name + '.php')   # im SQLite-Modus auch eine alte Datendatei
    if p.is_file():
        p.unlink()


# ─────────────── Teilung des Kundendokuments und der Bestell-Einstellungen (Stufe 2) ───────────────

def email_maske(e):
    """Wie kunden_email_maske() in app/api/lib/kunden.php: erstes Zeichen, Punkte, Domain."""
    e = str(e or '').strip()
    if '@' not in e:
        return ''
    lokal, domain = e.split('@', 1)
    return (lokal[:1] + '•••@' + domain) if lokal else ''


def kunden_teilen(kunden, felder, stamm=None):
    """kunden (alle Felder) → (kunden mit Portalfeldern, kundenstamm). Bestehende kundenstamm-Einträge bleiben (sie gelten ab Stufe 2);
    nur fehlende Einträge entstehen aus den übrigen Feldern."""
    stamm = json.loads(json.dumps({'customers': {}, **(stamm or {})}))   # Kopie: der gelesene Stand bleibt zum Vergleich unverändert
    if isinstance(stamm.get('customers'), list) and not stamm['customers']:
        stamm['customers'] = {}                                            # leer aus PHP (json_encode([]))
    if not isinstance(stamm.get('customers'), dict):
        raise ValueError('kundenstamm hat kein gültiges Feld customers')
    portal = []
    for c in kunden.get('customers', []):
        if not isinstance(c, dict) or not isinstance(c.get('id'), str):
            raise ValueError('Kunde ohne Kennung im Dokument kunden – nicht automatisch teilen')
        rest = {k: v for k, v in c.items() if k not in felder and k != 'id'}
        p = {k: v for k, v in c.items() if k in felder}
        if 'email' in c:
            p['emailMaske'] = email_maske(c.get('email'))
        if c['id'] not in stamm['customers']:
            stamm['customers'][c['id']] = rest
        portal.append(p)
    return {**kunden, 'customers': portal}, stamm


def kunden_zusammen(kunden, stamm):
    """Umkehrung von kunden_teilen: Portalfelder aus kunden, übrige Felder aus kundenstamm; emailMaske entfällt."""
    st = (stamm or {}).get('customers') or {}
    out = []
    for c in kunden.get('customers', []):
        if not isinstance(c, dict):
            out.append(c)
            continue
        x = {k: v for k, v in c.items() if k != 'emailMaske'}
        rest = st.get(c.get('id')) or {}
        out.append({**rest, **x} if rest else x)
    return {**kunden, 'customers': out}


def hat_interne_felder(kunden, felder):
    return any(isinstance(c, dict) and any(k not in felder for k in c) for c in (kunden or {}).get('customers', []))


# ─────────────── Plan ───────────────

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


def db_ergaenzen(ziel, zeilen):
    """Zeilen in die vorhandene Datenbank des Zielordners übernehmen (Hochstufen) und vergleichen."""
    with db.connect(ziel) as c:
        c.executemany('INSERT OR REPLACE INTO documents VALUES(?,?,?)', zeilen)
        c.commit()
        dort = {n: v for n, v, _ in db.validate(c)}
    for n, v, _ in zeilen:
        if json.loads(dort.get(n, 'null')) != json.loads(v):
            raise ValueError('Vergleich in daten-intern fehlgeschlagen: ' + n)


def kennzeichen(p, stufe):
    t = p.with_name(p.name + '.tmp')
    t.write_text(f'{stufe}\n'); t.replace(p)


def umstellung_planen(haupt, intern, regeln, stufe):
    """Neue interne Dokumente der Stufe 2 aus dem gemeinsamen Ordner: {Name: Inhalt}. Nur beim Überschreiten der Stufe 2 –
    bis dahin gilt der gemeinsame Ordner (frühere Reste eines Abbruchs in daten-intern werden überschrieben)."""
    neu = {}
    if stufe >= 2:
        return neu
    kunden = dok_lesen(haupt, 'kunden')
    if isinstance(kunden, dict) and isinstance(kunden.get('customers'), list):
        _, neu['kundenstamm'] = kunden_teilen(kunden, kunden_felder(regeln))
    best = dok_lesen(haupt, 'bestellung')
    if isinstance(best, dict) and 'to' in best:
        neu['bestellung-empfaenger'] = {'to': best['to'], 'updatedAt': best.get('updatedAt'), 'updatedBy': best.get('updatedBy', '')}
    return neu


def bereinigung_noetig(haupt, regeln):
    kunden = dok_lesen(haupt, 'kunden')
    best = dok_lesen(haupt, 'bestellung')
    return hat_interne_felder(kunden, kunden_felder(regeln)) or (isinstance(best, dict) and 'to' in best)


def plan(haupt, intern, regeln, ziel=ZIELSTUFE):
    stufe = stufe_lesen(haupt)
    ks = kundenseite(regeln, ziel)
    dateien = interne_dateien(haupt, ks)
    zeilen = interne_zeilen(haupt, ks)
    ablage = ablage_dateien(haupt)
    neu = umstellung_planen(haupt, intern, regeln, stufe) if ziel >= 2 else {}
    bereinigen = ziel >= 2 and bereinigung_noetig(haupt, regeln)
    zustand = 'gemeinsam' if stufe == 0 else f'getrennt, Stufe {stufe}'
    print(f"Zustand: {zustand}; Ziel dieses Stands: Stufe {ziel}; Speicher: {'SQLite' if sqlite_aktiv(haupt) else 'Dateien'}")
    print(f'Interne Dokumente im gemeinsamen Ordner: {len(zeilen)} in der Datenbank, {len(dateien)} als Datei, {len(ablage)} Dateien in der Ablage')
    for name, _, _ in zeilen[:200]:
        print('  ' + name)
    for rel in dateien[:200]:
        print('  ' + str(rel))
    if stufe < ziel:
        print(f'  Trennstufe {stufe} → {ziel}')
    for n in sorted(neu):
        print(f'  neu in daten-intern: {n}' + (' (Anschrift, E-Mail, Telefon, Notiz, Vertreter, Warenwirtschaft der Kunden)' if n == 'kundenstamm' else ' (Empfänger der Bestellwünsche)'))
    if bereinigen:
        print('  im gemeinsamen Ordner kürzen: kunden auf die Portalfelder, bestellung ohne Empfängeradressen')
    return stufe, ks, dateien, zeilen, ablage, neu


# ─────────────── Trennen und Zusammenführen ───────────────

def trennen(haupt, intern, regeln, ziel=ZIELSTUFE):
    stufe, ks, dateien, zeilen, ablage, neu = plan(haupt, intern, regeln, ziel)
    if stufe > ziel:
        raise ValueError(f'Daten sind schon weiter getrennt (Stufe {stufe}) als dieser Stand (Stufe {ziel}) – mit dem neueren Stand zusammenführen')
    if stufe == 0:
        if not leer(intern):
            raise ValueError('daten-intern enthält schon Daten – erst prüfen (z. B. Rest eines Abbruchs), dann leeren')
        if (intern / '.sqlite').exists() or (intern / '.sqlite-active').exists():
            raise ValueError('daten-intern enthält schon eine Datenbank')
    elif not (intern / MARKER_INTERN).is_file():
        raise ValueError('daten/ ist als getrennt markiert, daten-intern aber nicht – nicht automatisch reparieren')
    elif sqlite_aktiv(haupt) != sqlite_aktiv(intern):
        raise ValueError('Unterschiedliche Speicherarten in daten/ und daten-intern/ – nicht automatisch fortsetzen')
    neu_zeilen = [(n, json_text(v), int(time.time())) for n, v in sorted(neu.items())]
    if stufe < ziel:
        # 1. kopieren und vergleichen – die Anwendung liest bis zum Kennzeichen weiter wie bisher
        if stufe == 0:
            if sqlite_aktiv(haupt):
                db_anlegen(intern, zeilen + neu_zeilen)
            else:
                for n, v in neu.items():
                    dok_schreiben(intern, n, v)
        elif sqlite_aktiv(haupt):
            db_ergaenzen(intern, zeilen + neu_zeilen)
        else:
            for n, v in neu.items():
                dok_schreiben(intern, n, v)
        for rel in dateien + ablage:
            kopieren(haupt, intern, rel)
        # 2. umschalten: erst der interne Ordner, zuletzt der gemeinsame (ab hier liest die Anwendung mit der neuen Stufe)
        kennzeichen(intern / MARKER_INTERN, ziel)
        kennzeichen(haupt / MARKER_HAUPT, ziel)
    else:
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
    # 3. im gemeinsamen Ordner bereinigen: Originale entfernen, geteilte Dokumente auf die Felder der Kundenseite kürzen
    if ziel >= 2:
        bereinigen(haupt, intern, regeln)
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
    print(f'Getrennt (Stufe {ziel}): {len(zeilen)} Datensätze und {len(dateien)} Datendateien sowie {len(ablage)} Dateien der Ablage liegen jetzt in daten-intern'
          + (f'; neu angelegt: {", ".join(sorted(neu))}' if neu else ''))


def bereinigen(haupt, intern, regeln):
    """Ab Stufe 2: kunden auf die Portalfelder kürzen, bestellung ohne Adressen. Fehlt ein Eintrag in kundenstamm bzw.
    bestellung-empfaenger (Rest eines Abbruchs), entsteht er vorher aus den gekürzten Feldern – nichts geht verloren."""
    felder = kunden_felder(regeln)
    kunden = dok_lesen(haupt, 'kunden')
    if isinstance(kunden, dict) and isinstance(kunden.get('customers'), list) and hat_interne_felder(kunden, felder):
        alt = dok_lesen(intern, 'kundenstamm')
        portal, stamm = kunden_teilen(kunden, felder, alt)
        if stamm != alt:
            dok_schreiben(intern, 'kundenstamm', stamm)
        dok_schreiben(haupt, 'kunden', portal)
    best = dok_lesen(haupt, 'bestellung')
    if isinstance(best, dict) and 'to' in best:
        if dok_lesen(intern, 'bestellung-empfaenger') is None:
            dok_schreiben(intern, 'bestellung-empfaenger', {'to': best['to'], 'updatedAt': best.get('updatedAt'), 'updatedBy': best.get('updatedBy', '')})
        to = best['to'] if isinstance(best['to'], list) else []
        dok_schreiben(haupt, 'bestellung', {**{k: v for k, v in best.items() if k != 'to'}, 'empfaenger': len(to)})


def zusammenfuehren(haupt, intern, regeln):
    if not (haupt / MARKER_HAUPT).is_file():
        raise ValueError('Daten sind nicht getrennt – nichts zusammenzuführen')
    if not (intern / MARKER_INTERN).is_file():
        raise ValueError('daten-intern ist nicht als interner Datenordner markiert')
    if sqlite_aktiv(haupt) != sqlite_aktiv(intern):
        raise ValueError('Unterschiedliche Speicherarten in daten/ und daten-intern/ – nicht automatisch zusammenführen')
    stufe = stufe_lesen(haupt)
    if stufe > ZIELSTUFE:
        raise ValueError(f'Daten sind weiter getrennt (Stufe {stufe}), als dieser Stand kennt – mit dem neueren Stand zusammenführen')
    dateien = [p.relative_to(intern) for p in sorted(intern.rglob('*.php'))
               if not any(part.startswith('.') for part in p.relative_to(intern).parts) and p.relative_to(intern).parts[0] != 'dateien'
               and str(p.relative_to(intern).with_suffix('')) not in GETEILT]
    ablage = ablage_dateien(intern)
    zeilen = []
    if sqlite_aktiv(intern):
        with db.connect(intern) as c:
            zeilen = [r for r in db.validate(c) if r[0] not in GETEILT]
    for rel in dateien + ablage:
        if (haupt / rel).exists() and (haupt / rel).read_bytes() != (intern / rel).read_bytes():
            raise ValueError('Datei gibt es in beiden Ordnern mit verschiedenem Inhalt: ' + str(rel))
    # 1. geteilte Dokumente im gemeinsamen Ordner wieder vollständig machen (bei Stufe 2 gelten dort nur die Portalfelder –
    #    die zusätzlichen Felder stören die laufende Stufe nicht, ein Abbruch hier lässt alles lesbar)
    if stufe >= 2:
        kunden = dok_lesen(haupt, 'kunden')
        stamm = dok_lesen(intern, 'kundenstamm')
        if isinstance(kunden, dict) and isinstance(kunden.get('customers'), list):
            dok_schreiben(haupt, 'kunden', kunden_zusammen(kunden, stamm))
        best = dok_lesen(haupt, 'bestellung')
        emp = dok_lesen(intern, 'bestellung-empfaenger')
        if isinstance(best, dict) and isinstance(emp, dict):
            dok_schreiben(haupt, 'bestellung', {**{k: v for k, v in best.items() if k != 'empfaenger'}, 'to': emp.get('to', [])})
    # 2. zurückkopieren und vergleichen
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
    # 3. umschalten (ab hier liest die Anwendung wieder alles aus dem gemeinsamen Ordner)
    (haupt / MARKER_HAUPT).unlink()
    # 4. interne Kopien und der Auszug der Kundenseite entfernen; Kennzeichen zuletzt
    if sqlite_aktiv(intern):
        shutil.rmtree(intern / '.sqlite')
        (intern / '.sqlite-active').unlink()
    for rel in dateien + ablage:
        (intern / rel).unlink()
    for n in GETEILT:
        if (intern / (n + '.php')).is_file():
            (intern / (n + '.php')).unlink()
    dok_loeschen(haupt, AUSZUG)
    ordner_aufraeumen(intern, dateien + ablage)
    if (intern / 'dateien').is_dir() and not any((intern / 'dateien').iterdir()):
        (intern / 'dateien').rmdir()
    (intern / MARKER_INTERN).unlink()
    print(f'Zusammengeführt (von Stufe {stufe}): {len(zeilen)} Datensätze, {len(dateien)} Datendateien und {len(ablage)} Dateien der Ablage wieder in daten/'
          + ('; Kundendokument und Bestell-Einstellungen wieder vollständig' if stufe >= 2 else ''))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('befehl', choices=['pruefen', 'trennen', 'zusammenfuehren'])
    p.add_argument('daten', type=Path)
    p.add_argument('intern', type=Path)
    p.add_argument('--offline', action='store_true', help='Anwendung ist gestoppt (Pflicht für trennen/zusammenfuehren)')
    p.add_argument('--regeln', type=Path, default=REGELN)
    p.add_argument('--stufe', type=int, choices=range(1, ZIELSTUFE + 1), default=ZIELSTUFE,
                   help='Zielstufe beim Trennen (Standard: höchste dieses Stands; nur für Tests und schrittweises Vorgehen)')
    a = p.parse_args()
    haupt, intern = a.daten.resolve(), a.intern.resolve()
    if not haupt.is_dir():
        p.error('Datenordner fehlt: ' + str(haupt))
    if haupt == intern or haupt in intern.parents or intern in haupt.parents:
        p.error('daten-intern muss neben daten/ liegen, nicht darin')
    if a.befehl != 'pruefen' and not a.offline:
        p.error('Erst die Anwendung stoppen und --offline angeben')
    if a.befehl == 'pruefen':
        with (haupt / '.storage.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            plan(haupt, intern, a.regeln, a.stufe)
        return
    intern.mkdir(mode=0o700, exist_ok=True)
    with (haupt / '.storage.lock').open('a') as l1, (intern / '.storage.lock').open('a') as l2:
        fcntl.flock(l1, fcntl.LOCK_EX); fcntl.flock(l2, fcntl.LOCK_EX)
        if a.befehl == 'trennen':
            trennen(haupt, intern, a.regeln, a.stufe)
        else:
            zusammenfuehren(haupt, intern, a.regeln)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error, KeyError) as e:
        print('Daten trennen fehlgeschlagen: ' + str(e), file=sys.stderr)
        sys.exit(1)
