"""Inkrementelle Sicherung der Dateiablage (dateien/<bereich>/<xx>/<id>.bin, lib/dateiablage.php) für deploy/sichern.sh.

Jeder Lauf legt unter sicherungen/dateien/<Zeit>/ einen vollständigen Stand an, mit derselben Zeit wie die Archive des
Laufs. Dateien, die im vorigen Stand mit gleicher Größe und Änderungszeit liegen, werden dort fest verlinkt (Hardlink), nur
neue kopiert. Alle Stände belegen so etwa einen Bestand plus die Änderungen, und jeder lässt sich für sich zurückspielen
(cp -a). Halbe Uploads (.teile), Verweise und fremde Namen kommen nicht hinein. Festschreiben (<Zeit>.tmp → <Zeit>) und
Aufbewahrung übernimmt sichern.sh gemeinsam mit den Archiven, erst wenn alles geprüft ist.

  bedarf <ablage> <ziel>                     Bytes, die ein neuer Stand kopieren müsste (Platzprüfung)
  aufbauen <ablage> <ziel> <zeit>            <zeit>.tmp anlegen bzw. ergänzen
  pruefen <ablage> <ziel> <zeit> <daten …>   <zeit>.tmp noch einmal ergänzen und gegen die Verweise der entpackten
                                             Sicherung prüfen (Einteilung: pruefen()); Warnungen in einer Zeile auf
                                             stderr, Rückgabe 0
  abschliessen <ziel> <zeit>                 JSON zum festgeschriebenen Stand: anzahl, groesse, neu (Bytes nur in diesem
                                             Stand), staende, belegt (Bytes aller Stände), fehlend
  fehlende <ablage> <daten …>                für den Betreiber: Verweise, deren Datei in der Ablage fehlt oder eine andere
                                             Größe hat, je Zeile Kennung, Dokument und Befund

Ein Verweis ist ein Eintrag {id, groesse, sha256} in einem Dokument (Rückgabe von ablage_teil/ablage_ablegen/
ablage_kopieren), Ausnahme QS-Rohfassung {roh, sha256Roh} ohne Größe (docs/entwickler/05-daten.md). Dokumente liest
datenbank.py (Dateien oder SQLite). Kommandozeile nur erweitern (das Release nutzt das Werkzeug des Vorstands, wenn der neue
Commit keins hat). Fehler: Meldung auf stderr, Rückgabewert 1.
"""
import argparse
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

from datenbank import documents, validate

NAME = re.compile(r'[a-z][a-z0-9-]{1,30}/[a-z0-9]{2}/([a-z0-9]{12,40})\.bin')   # wie ablage_pfad() in lib/dateiablage.php
ZEIT = re.compile(r'\d{4}-\d{2}-\d{2}_\d{6}')
ID = re.compile(r'[a-z0-9]{12,40}')
SHA = re.compile(r'[0-9a-f]{64}')
STICHPROBE = 20


def dateien(wurzel):
    """relativer Pfad → lstat der regulären Dateien mit gültigem Namen; folgt keinem Verweis, fehlender Ordner = leer"""
    aus = {}
    for ordner, _, namen in os.walk(wurzel):
        for n in namen:
            p = os.path.join(ordner, n)
            rel = os.path.relpath(p, wurzel)
            if not NAME.fullmatch(rel):
                continue
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue   # gerade gelöscht (Entwurf)
            if stat.S_ISREG(st.st_mode):
                aus[rel] = st
    return aus


def staende(ziel):
    return sorted(p for p in ziel.iterdir() if p.is_dir() and ZEIT.fullmatch(p.name)) if ziel.is_dir() else []


def gleich(a, b):
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def plan(ablage, ziel):
    """je Datei der Ablage: (relativer Pfad, lstat, gleiche Datei im neuesten Stand zum Verlinken oder None = kopieren)"""
    s = staende(ziel)
    alt = dateien(s[-1]) if s else {}
    for rel, st in dateien(ablage).items():
        yield rel, st, s[-1] / rel if rel in alt and gleich(alt[rel], st) else None


def bedarf(ablage, ziel):
    return sum(st.st_size for _, st, vorlage in plan(ablage, ziel) if vorlage is None)


def kopieren(quelle, z):
    """frische Kopie (eigene Inode); False, wenn die Quelle inzwischen gelöscht ist"""
    z.unlink(missing_ok=True)
    try:
        shutil.copy2(quelle, z, follow_symlinks=False)
    except FileNotFoundError:
        z.unlink(missing_ok=True)
        return False
    return True


def aufbauen(ablage, ziel, zeit):
    """<zeit>.tmp ergänzen; gibt die Dateien der Ablage zurück, die jetzt im Stand liegen (relativer Pfad → lstat)"""
    neu = ziel / f'{zeit}.tmp'
    neu.mkdir(mode=0o700, parents=True, exist_ok=True)
    schon = dateien(neu)
    da = {}
    for rel, st, vorlage in plan(ablage, ziel):
        z = neu / rel
        if not (rel in schon and gleich(schon[rel], st)):
            z.parent.mkdir(parents=True, exist_ok=True)
            if vorlage:
                z.unlink(missing_ok=True)
                os.link(vorlage, z)
            elif not kopieren(ablage / rel, z):
                continue
        da[rel] = st
    return da


def verweise(daten):
    """id → (Dokument, groesse oder None, sha256 oder '') aus den Dokumenten eines Datenordners oder einer entpackten Sicherung"""
    if (daten / '.sqlite-active').is_file():
        with sqlite3.connect((daten / '.sqlite/store.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as c:
            zeilen = validate(c)
    else:
        zeilen = list(documents(daten))
    aus = {}

    def lauf(x, dok):
        if isinstance(x, dict):
            i, g, s = x.get('id'), x.get('groesse'), x.get('sha256')
            if isinstance(i, str) and ID.fullmatch(i) and isinstance(g, int) and isinstance(s, str) and SHA.fullmatch(s):
                aus[i] = (dok, g, s)
            r, rs = x.get('roh'), x.get('sha256Roh')
            if isinstance(r, str) and ID.fullmatch(r) and r not in aus:
                aus[r] = (dok, None, rs if isinstance(rs, str) and SHA.fullmatch(rs) else '')
            x = list(x.values())
        if isinstance(x, list):
            for v in x:
                lauf(v, dok)
    for name, inhalt, _ in zeilen:
        lauf(json.loads(inhalt), name)
    return aus


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def je_id(liste):
    return {NAME.fullmatch(rel).group(1): rel for rel in liste}


def pruefen(ablage, ziel, zeit, daten):
    """Ergänzt <zeit>.tmp mit einer neuen Auflistung der Ablage und teilt jeden Verweis der Sicherung ein:
    im Stand mit passender Größe: in Ordnung. In der Ablage, im Stand fehlend oder mit anderer Größe: einmal nachkopieren,
    sonst Fehler. Weder in der Ablage noch im Stand: nur Warnung, Liste in sicherungen/.dateien-fehlend (die Anwendung
    rechnet selbst mit fehlenden Dateien, z. B. ZIP-Export mit Hinweise.txt). Stichprobe mit SHA-256: stimmt die Kopie im
    Stand nicht, die Datei in der Ablage aber schon, wird sie im neuen Stand frisch kopiert statt verlinkt (Warnung);
    stimmen beide nicht, Fehler. Gibt die Warnungen zurück."""
    neu = ziel / f'{zeit}.tmp'
    lebend = je_id(aufbauen(ablage, ziel, zeit))
    stand = je_id(dateien(neu))
    refs = {}
    for d in daten:
        refs.update(verweise(d))
    fehlend = []
    for i, (dok, g, _) in sorted(refs.items()):
        if i in stand and (g is None or (neu / stand[i]).lstat().st_size == g):
            continue
        if i in lebend:
            if kopieren(ablage / lebend[i], neu / lebend[i]):
                stand[i] = lebend[i]
                if g is None or (neu / stand[i]).lstat().st_size == g:
                    continue
            else:
                del lebend[i]
                stand.pop(i, None)
        if i in stand or i in lebend:
            raise ValueError(f'Datei {i} ({dok}) hat eine andere Größe als im Dokument ({g} Bytes) – Datei aus einem älteren '
                             'Stand zurückholen oder Verweis prüfen (docs/entwickler/08-betrieb.md)')
        fehlend.append((i, dok))
    mit_sha = [i for i, (_, _, s) in refs.items() if s and i in stand]
    geheilt = []
    for i in random.sample(mit_sha, min(STICHPROBE, len(mit_sha))):
        dok, _, s = refs[i]
        if sha256(neu / stand[i]) == s:
            continue
        if i in lebend and sha256(ablage / lebend[i]) == s and kopieren(ablage / lebend[i], neu / stand[i]) \
                and sha256(neu / stand[i]) == s:
            geheilt.append(i)
            continue
        raise ValueError(f'Prüfsumme der Datei {i} ({dok}) stimmt weder in der Sicherung noch in der Ablage – Datei aus einem '
                         'älteren Stand zurückholen (docs/entwickler/08-betrieb.md)')
    liste = ziel.parent / '.dateien-fehlend'
    if fehlend:
        liste.write_text(''.join(f'{i}\t{dok}\n' for i, dok in fehlend))
    else:
        liste.unlink(missing_ok=True)
    warnungen = []
    if fehlend:
        warnungen.append(f'{len(fehlend)} Datei(en) fehlen in Ablage und Sicherung ({", ".join(i for i, _ in fehlend[:3])}'
                         f'{" …" if len(fehlend) > 3 else ""}), Liste: sicherungen/.dateien-fehlend')
    if geheilt:
        warnungen.append(f'{len(geheilt)} beschädigte Kopie(n) in der Sicherung neu kopiert ({", ".join(geheilt[:3])})')
    return warnungen


def belegt(staende_liste):
    """Bytes aller Stände, fest verlinkte Dateien einmal; die Inode kommt aus dem Verzeichnis, stat nur bei einer neuen
    (bei 150 Ständen mit je 15.000 Dateien sonst Millionen lstat je Lauf)"""
    groesse = {}

    def lauf(ordner):
        with os.scandir(ordner) as eintraege:
            for e in eintraege:
                if e.is_dir(follow_symlinks=False):
                    lauf(e.path)
                elif e.inode() not in groesse:
                    groesse[e.inode()] = e.stat(follow_symlinks=False).st_size
    for s in staende_liste:
        lauf(s)
    return sum(groesse.values())


def abschliessen(ziel, zeit):
    s = staende(ziel)
    letzte = dateien(ziel / zeit).values()
    liste = ziel.parent / '.dateien-fehlend'
    return {'anzahl': len(letzte), 'groesse': sum(st.st_size for st in letzte), 'neu': sum(st.st_size for st in letzte if st.st_nlink == 1),
            'staende': len(s), 'belegt': belegt(s), 'fehlend': len(liste.read_text().splitlines()) if liste.is_file() else 0}


def fehlende(ablage, daten):
    lebend = {NAME.fullmatch(rel).group(1): st for rel, st in dateien(ablage).items()}
    for d in daten:
        for i, (dok, g, _) in sorted(verweise(d).items()):
            if i not in lebend:
                yield i, dok, 'fehlt'
            elif g is not None and lebend[i].st_size != g:
                yield i, dok, f'Größe {lebend[i].st_size} statt {g} Bytes'


def zeit(wert):
    if not ZEIT.fullmatch(wert):
        raise argparse.ArgumentTypeError('Zeit im Format JJJJ-MM-TT_HHMMSS')
    return wert


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    b = p.add_subparsers(dest='befehl', required=True)
    for name, felder in (('bedarf', 'ablage ziel'), ('aufbauen', 'ablage ziel zeit'), ('pruefen', 'ablage ziel zeit daten'),
                         ('abschliessen', 'ziel zeit'), ('fehlende', 'ablage daten')):
        u = b.add_parser(name)
        for f in felder.split():
            u.add_argument(f, type=zeit if f == 'zeit' else Path, nargs='+' if f == 'daten' else None)
    a = p.parse_args()
    if 'ablage' in a and a.ablage.is_symlink():
        p.error('Dateiablage ist ein Verweis')
    if a.befehl == 'bedarf':
        print(bedarf(a.ablage, a.ziel))
    elif a.befehl == 'aufbauen':
        aufbauen(a.ablage, a.ziel, a.zeit)
    elif a.befehl == 'pruefen':
        warnungen = pruefen(a.ablage, a.ziel, a.zeit, a.daten)
        if warnungen:
            print('; '.join(warnungen), file=sys.stderr)
    elif a.befehl == 'abschliessen':
        print(json.dumps(abschliessen(a.ziel, a.zeit), separators=(',', ':')))
    else:
        for zeile in fehlende(a.ablage, a.daten):
            print(*zeile, sep='\t')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error) as e:
        print(f'Dateisicherung: {e}', file=sys.stderr)
        sys.exit(1)
