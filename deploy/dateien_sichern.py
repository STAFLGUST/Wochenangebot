"""Inkrementelle Sicherung der Dateiablage (dateien/<bereich>/<xx>/<id>.bin, lib/dateiablage.php) für deploy/sichern.sh.

Jeder Lauf legt unter sicherungen/dateien-<name>/<Zeit>/ einen vollständigen Stand an. Dateien, die schon im vorigen Stand
mit gleicher Größe und Änderungszeit liegen, werden dort fest verlinkt (Hardlink), nur neue oder geänderte kopiert. So
belegen alle Stände zusammen etwa einen Bestand plus die Änderungen, und jeder Stand lässt sich für sich zurückspielen
(cp -a). Halbe Uploads (.teile), Verweise und fremde Namen kommen nicht hinein.

  bedarf <quelle> <ziel>                       Bytes, die ein neuer Stand kopieren müsste (Platzprüfung vor dem Sichern)
  aufbauen <quelle> <ziel> <zeit>              <zeit>.tmp anlegen bzw. ergänzen; gibt die kopierten Bytes aus. sichern.sh ruft
                                               es vor dem Datenarchiv und danach noch einmal auf (Dateien, die inzwischen
                                               hinzukamen, stehen sonst im Archiv, aber nicht im Stand)
  abschliessen <behalten> <zeit> <ziel …> --daten <entpackte Sicherung …>
                                               jede Datei, auf die die Daten verweisen, muss im Stand liegen (gleiche Größe),
                                               Stichprobe mit SHA-256; dann <zeit>.tmp → <zeit>, je Ziel <behalten> Stände.
                                               Ausgabe: Anzahl, Bytes, Stände, belegte Bytes aller Stände
Ein Verweis ist ein Eintrag mit „id“, „groesse“ und „sha256“ (Rückgabe von ablage_teil/ablage_ablegen/ablage_kopieren) bzw.
„roh“ und „sha256Roh“ (Rohfassung, module/qs/vorlagen.php). Fehler: Meldung auf stderr, Rückgabewert 1.
"""
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import stat
import sys
from pathlib import Path

NAME = re.compile(r'[a-z][a-z0-9-]{1,30}/[a-z0-9]{2}/([a-z0-9]{12,40})\.bin')   # wie ablage_pfad() in lib/dateiablage.php
ZEIT = re.compile(r'\d{4}-\d{2}-\d{2}_\d{6}')
ID = re.compile(r'[a-z0-9]{12,40}')
SHA = re.compile(r'[0-9a-f]{64}')
GUARD = '<?php http_response_code(404); exit; ?>\n'
STICHPROBE = 20


def dateien(wurzel):
    """relativer Pfad → lstat der regulären Dateien mit gültigem Namen; folgt keinem Verweis"""
    aus = {}
    for ordner, unter, namen in os.walk(wurzel):
        unter[:] = [u for u in unter if u != '.teile']
        for n in namen:
            p = os.path.join(ordner, n)
            rel = os.path.relpath(p, wurzel)
            st = os.lstat(p)
            if NAME.fullmatch(rel) and stat.S_ISREG(st.st_mode):
                aus[rel] = st
    return aus


def staende(ziel):
    return sorted(p for p in ziel.iterdir() if p.is_dir() and ZEIT.fullmatch(p.name)) if ziel.is_dir() else []


def gleich(a, b):
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def vorher(ziel):
    s = staende(ziel)
    return (s[-1], dateien(s[-1])) if s else (None, {})


def bedarf(quelle, ziel):
    _, alt = vorher(ziel)
    return sum(st.st_size for rel, st in dateien(quelle).items() if not (rel in alt and gleich(alt[rel], st)))


def aufbauen(quelle, ziel, zeit):
    neu = ziel / f'{zeit}.tmp'
    neu.mkdir(mode=0o700, parents=True, exist_ok=True)
    letzt, alt = vorher(ziel)
    schon = dateien(neu)
    kopiert = 0
    for rel, st in dateien(quelle).items():
        if rel in schon and gleich(schon[rel], st):
            continue
        z = neu / rel
        z.parent.mkdir(parents=True, exist_ok=True)
        z.unlink(missing_ok=True)
        if rel in alt and gleich(alt[rel], st):
            os.link(letzt / rel, z)
        else:
            shutil.copy2(quelle / rel, z, follow_symlinks=False)
            kopiert += st.st_size
    return kopiert


def verweise(daten):
    """id → (groesse oder None, sha256 oder '') aus allen Dokumenten einer entpackten Sicherung (Dateien oder SQLite)"""
    texte = []
    for p in daten.rglob('*.php'):
        t = p.read_text(encoding='utf-8', errors='replace')
        texte.append(t[len(GUARD):] if t.startswith(GUARD) else t)
    db = daten / '.sqlite' / 'store.sqlite'
    if (daten / '.sqlite-active').is_file() and db.is_file():
        with sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True) as c:
            texte += [r[0] for r in c.execute('SELECT payload FROM documents')]
    aus = {}

    def lauf(x):
        if isinstance(x, dict):
            i, g, s = x.get('id'), x.get('groesse'), x.get('sha256')
            if isinstance(i, str) and ID.fullmatch(i) and isinstance(g, int) and isinstance(s, str) and SHA.fullmatch(s):
                aus[i] = (g, s)
            r, rs = x.get('roh'), x.get('sha256Roh')
            if isinstance(r, str) and ID.fullmatch(r) and r not in aus:
                aus[r] = (None, rs if isinstance(rs, str) and SHA.fullmatch(rs) else '')
            for v in x.values():
                lauf(v)
        elif isinstance(x, list):
            for v in x:
                lauf(v)
    for t in texte:
        try:
            lauf(json.loads(t))
        except ValueError:
            pass   # unlesbare Dokumente meldet sicherung-pruefen.py
    return aus


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def abschliessen(behalten, zeit, ziele, daten):
    neu = [z / f'{zeit}.tmp' for z in ziele if (z / f'{zeit}.tmp').is_dir()]
    index = {NAME.fullmatch(rel).group(1): (n / rel, st) for n in neu for rel, st in dateien(n).items()}
    refs = {}
    for d in daten:
        refs.update(verweise(d))
    fehlend = [i for i, (g, _) in refs.items() if i not in index or (g is not None and index[i][1].st_size != g)]
    if fehlend:
        raise ValueError(f'{len(fehlend)} Datei(en), auf die die Daten verweisen, fehlen in der Dateisicherung oder haben eine andere Größe')
    probe = random.sample([i for i, (_, s) in refs.items() if s], min(STICHPROBE, sum(1 for _, s in refs.values() if s)))
    falsch = [i for i in probe if sha256(index[i][0]) != refs[i][1]]
    if falsch:
        raise ValueError(f'Prüfsumme in der Dateisicherung stimmt nicht ({len(falsch)} von {len(probe)} geprüften Dateien)')
    for n in neu:
        n.rename(n.with_name(zeit))
    anzahl = groesse = belegt = staende_max = 0
    for z in ziele:
        s = staende(z)
        for alt in s[:-behalten]:
            shutil.rmtree(alt)
        s = s[-behalten:]
        staende_max = max(staende_max, len(s))
        if s and s[-1].name == zeit:
            letzte = dateien(s[-1]).values()
            anzahl += len(letzte); groesse += sum(st.st_size for st in letzte)
        inodes = {}
        for x in s:
            for st in dateien(x).values():
                inodes[(st.st_dev, st.st_ino)] = st.st_size
        belegt += sum(inodes.values())
    return anzahl, groesse, staende_max, belegt


def main(a):
    if a[0] == 'bedarf':
        print(bedarf(Path(a[1]), Path(a[2])))
    elif a[0] == 'aufbauen':
        print(aufbauen(Path(a[1]), Path(a[2]), a[3]))
    elif a[0] == 'abschliessen':
        trenner = a.index('--daten')
        print(*abschliessen(int(a[1]), a[2], [Path(x) for x in a[3:trenner]], [Path(x) for x in a[trenner + 1:]]))
    else:
        raise ValueError('unbekannter Befehl')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, IndexError, sqlite3.Error) as e:
        print(f'Dateisicherung: {e}', file=sys.stderr)
        sys.exit(1)
