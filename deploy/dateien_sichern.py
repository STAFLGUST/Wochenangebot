"""Inkrementelle Sicherung der Dateiablage (dateien/<bereich>/<xx>/<id>.bin, lib/dateiablage.php) für deploy/sichern.sh.

Jeder Lauf legt unter sicherungen/dateien/<Zeit>/ einen vollständigen Stand an, mit derselben Zeit wie die Archive des
Laufs. Dateien, die im vorigen Stand mit gleicher Größe und Änderungszeit liegen, werden dort fest verlinkt (Hardlink), nur
neue kopiert. Alle Stände belegen so etwa einen Bestand plus die Änderungen, und jeder lässt sich für sich zurückspielen
(cp -a). Halbe Uploads (.teile), Verweise und fremde Namen kommen nicht hinein. Festschreiben (<Zeit>.tmp → <Zeit>) und
Aufbewahrung übernimmt sichern.sh gemeinsam mit den Archiven, erst wenn alles geprüft ist.

  bedarf <ablage> <ziel> [<zeit>]            Bytes, die ein neuer Stand kopieren müsste (Platzprüfung)
  aufbauen <ablage> <ziel> <zeit>            <zeit>.tmp anlegen bzw. ergänzen
  pruefen <ablage> <ziel> <zeit> <daten …>   <zeit>.tmp noch einmal ergänzen und jede Datei, auf die die entpackte
                                             Sicherung verweist, in den Stand bringen (pruefen()); Zustand der Ablage
                                             (ok, warnung, kritisch) auf stdout, Warnungen in einer Zeile auf stderr,
                                             Rückgabe 0
  abschliessen <ziel> <zeit> [<zustand>]     JSON zum festgeschriebenen Stand: anzahl, groesse, neu (Bytes nur in diesem
                                             Stand), staende, belegt (Bytes aller Stände), fehlend (in der Ablage), zustand
  fehlende <ablage> <daten …>                für den Betreiber: Verweise, deren Datei in der Ablage fehlt oder eine andere
                                             Größe hat, je Zeile Kennung, Dokument und Befund
  zurueckholen <ziel>                        für den Betreiber (root): jede Datei aus sicherungen/.dateien-fehlend aus dem
                                             neuesten Stand in die Ablage zurückholen (zurueckholen()); Rückgabe 1, wenn
                                             eine nicht zurückkam

Ein Verweis ist ein Eintrag {id, groesse, sha256} in einem Dokument (Rückgabe von ablage_teil/ablage_ablegen/
ablage_kopieren), Ausnahme QS-Rohfassung {roh, sha256Roh} ohne Größe (docs/entwickler/05-daten.md). Dokumente: SQLite über
datenbank.validate, Dateien so nachsichtig wie sicherung-pruefen.py. Beim Release läuft dieses Werkzeug des neuen Commits mit
datenbank.py des alten (Vermerk dort). Kommandozeile nur erweitern (das Release nutzt das Werkzeug des Vorstands, wenn der
neue Commit keins hat). Fehler nur bei Störungen der Sicherung selbst (Ein-/Ausgabe, Datenbank): Meldung auf stderr,
Rückgabewert 1.
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
import zlib
from datetime import date
from pathlib import Path

from datenbank import GUARD, document_path, validate

NAME = re.compile(r'[a-z][a-z0-9-]{1,30}/[a-z0-9]{2}/([a-z0-9]{12,40})\.bin')   # wie ablage_pfad() in lib/dateiablage.php
ZEIT = re.compile(r'\d{4}-\d{2}-\d{2}_\d{6}')
ID = re.compile(r'[a-z0-9]{12,40}')
SHA = re.compile(r'[0-9a-f]{64}')
DOKUMENT = re.compile(r'[\w.-]+(?:/[\w.-]+)*', re.ASCII)   # wie datenbank.KEY, dazu Punkte (angebot.alt.php); nie Steuer- oder Shell-Zeichen
STICHPROBE = 20   # zufällig je Lauf, dazu jede Datei einmal in RUNDE Tagen (Kennung mod RUNDE = Tag mod RUNDE)
RUNDE = 30
KRITISCH = 10     # fehlen mehr Dateien in der Ablage (oder mehr als 1 % der verwiesenen), ist der Zustand kritisch
WEBSERVER = '33'  # www-data in den Containern; Besitzer der Ablage (docs/entwickler/08-betrieb.md)


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


def vorlage(ziel, zeit=None):
    """neuester festgeschriebener Stand vor <zeit>; ein Stand mit späterer Zeit (vorgestellte Uhr) dient nie als Vorlage"""
    s = [p for p in staende(ziel) if zeit is None or p.name < zeit]
    return s[-1] if s else None


def plan(ablage, ziel, zeit=None):
    """je Datei der Ablage: (relativer Pfad, lstat, gleiche Datei im vorigen Stand zum Verlinken oder None = kopieren)"""
    v = vorlage(ziel, zeit)
    alt = dateien(v) if v else {}
    for rel, st in dateien(ablage).items():
        yield rel, st, v / rel if rel in alt and gleich(alt[rel], st) else None


def bedarf(ablage, ziel, zeit=None):
    return sum(st.st_size for _, st, quelle in plan(ablage, ziel, zeit) if quelle is None)


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
    for rel, st, quelle in plan(ablage, ziel, zeit):
        z = neu / rel
        if not (rel in schon and gleich(schon[rel], st)):
            z.parent.mkdir(parents=True, exist_ok=True)
            if quelle:
                z.unlink(missing_ok=True)
                os.link(quelle, z)
            elif not kopieren(ablage / rel, z):
                continue
        da[rel] = st
    return da


def verweise(daten):
    """({id → (Dokument, groesse oder None, sha256 oder '')}, [nicht lesbare Dokumente]) aus einem Datenordner oder einer
    entpackten Sicherung. Im Dateispeicher wird jedes Dokument für sich gelesen, so nachsichtig wie sicherung-pruefen.py:
    ein fehlerhaftes nennt die Sicherung als Warnung, statt abzubrechen."""
    dokumente, kaputt = [], []
    if (daten / '.sqlite-active').is_file():
        with sqlite3.connect((daten / '.sqlite/store.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as c:
            dokumente = [(name, json.loads(inhalt)) for name, inhalt, _ in validate(c)]
    else:
        for p in sorted(daten.rglob('*.php')):
            rel = p.relative_to(daten)
            if not document_path(rel):
                continue
            if not DOKUMENT.fullmatch(str(rel.with_suffix(''))):
                kaputt.append(ascii(str(rel)))   # Name aus dem beschreibbaren Datenordner: kein Tabulator oder Zeilenumbruch in Liste und Meldung
                continue
            try:
                if p.is_symlink():
                    raise OSError('Verweis')   # root folgt keinem Verweis aus dem beschreibbaren Datenordner
                t = p.read_text()
                dokumente.append((str(rel.with_suffix('')), json.loads(t[len(GUARD):] if t.startswith(GUARD) else t)))
            except (OSError, ValueError):
                kaputt.append(str(rel))
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
    for name, wert in dokumente:
        lauf(wert, name)
    return aus, kaputt


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def je_id(liste):
    return {NAME.fullmatch(rel).group(1): rel for rel in liste}


def kurz(ids):
    return ', '.join(ids[:3]) + (' …' if len(ids) > 3 else '')


def schreiben(quelle, ablage, rel):
    """im Kindprozess: quelle (Sicherung, nur root lesbar) als neue Datei ablage/rel anlegen. Die Ablage ist im Container
    beschreibbar: geschrieben wird als Webserver, kein Ordner darf ein Verweis sein, ein Verweis am Ziel wird ersetzt"""
    q = os.open(quelle, os.O_RDONLY | os.O_NOFOLLOW)
    st = os.fstat(q)
    if os.geteuid() == 0:
        u = int(WEBSERVER)
        os.setgroups([])
        os.setresgid(u, u, u)
        os.setresuid(u, u, u)
    d = None
    for teil in (str(ablage), *rel.parts[:-1]):
        try:
            os.mkdir(teil, 0o755, dir_fd=d)
        except FileExistsError:
            pass
        d = os.open(teil, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=d)
    tmp = f'.{rel.name}.{os.getpid()}.neu'
    f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=d)
    try:
        with open(q, 'rb') as a, open(f, 'wb') as b:
            shutil.copyfileobj(a, b, 1 << 20)
            b.flush()
            os.fchmod(f, stat.S_IMODE(st.st_mode))
            os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))   # gleiche Größe und Zeit: der nächste Lauf verlinkt statt zu kopieren
        os.replace(tmp, rel.name, src_dir_fd=d, dst_dir_fd=d)
    except BaseException:
        os.unlink(tmp, dir_fd=d)
        raise


def zurueckholen(ziel):
    """Jede Datei aus sicherungen/.dateien-fehlend, die im neuesten Stand liegt, als eigene Datei (nie ein fester Verweis in
    die Sicherung) in die Ablage zurückholen; vorhandene Dateien bleiben. Jede Zeile wird gegen den Stand geprüft (Kennung
    und Ziel passen zusammen). Gibt (zurückgeholt, nicht zurückgeholt) zurück, Gründe auf stderr."""
    s = vorlage(ziel)
    stand = je_id(dateien(s)) if s else {}
    liste = ziel.parent / '.dateien-fehlend'
    da = offen = 0
    for zeile in liste.read_text().splitlines() if liste.is_file() else []:
        f = zeile.split('\t')
        i, z = f[0], Path(f[-1])
        rel = Path(*z.parts[-3:])
        if not (z.is_absolute() and stand.get(i) == str(rel)):
            print(f'{ascii(i)}: nicht in der Sicherung ({ascii(f[-1])})', file=sys.stderr)
            offen += 1
            continue
        try:
            if stat.S_ISREG(os.lstat(z).st_mode):
                continue
        except OSError:
            pass
        pid = os.fork()
        if pid == 0:
            code = 1
            try:
                schreiben(s / rel, z.parents[2], rel)
                code = 0
            except Exception as e:
                print(f'{i}: {e}', file=sys.stderr, flush=True)
            finally:
                os._exit(code)
        if os.waitpid(pid, 0)[1]:
            offen += 1
        else:
            da += 1
    return da, offen


def pruefen(ablage, ziel, zeit, daten):
    """Ergänzt <zeit>.tmp mit einer neuen Auflistung der Ablage und bringt jede Datei, auf die die Sicherung verweist, in den
    Stand (Tabelle in docs/entwickler/08-betrieb.md): aus der Ablage; passt dort die Größe nicht zum Dokument, die passende
    Fassung des vorigen Stands; fehlt sie in der Ablage, die des vorigen Stands. So trägt jeder Stand eine Datei weiter,
    solange ein Dokument auf sie verweist, und die Aufbewahrung verliert sie nie. Alles nur Warnungen: Liste
    sicherungen/.dateien-fehlend mit Kennung, Dokument und Ziel in der Ablage je Datei (zurueckholen; die Anwendung rechnet selbst mit fehlenden
    Dateien, z. B. ZIP-Export mit Hinweise.txt). Stichprobe mit SHA-256 (rotierend und zufällig): stimmt die Kopie im Stand
    nicht, die Datei in der Ablage aber schon, wird sie frisch kopiert statt verlinkt. Gibt (Zustand, Warnungen) zurück."""
    neu = ziel / f'{zeit}.tmp'
    da = aufbauen(ablage, ziel, zeit)
    lebend = je_id(da)
    stand = je_id(dateien(neu))
    v = vorlage(ziel, zeit)
    alt = je_id(dateien(v)) if v else {}
    refs, kaputt = {}, []
    for d in daten:
        r, k = verweise(d)
        refs.update(r)
        kaputt += k

    def passt(p, g):
        return g is None or p.lstat().st_size == g

    fehlen, aus_stand, anders = [], [], []   # (Kennung, Dokument) fehlt in der Ablage; Größe in der Ablage falsch, Stand richtig; Größe im Stand falsch
    for i, (dok, g, _) in sorted(refs.items()):
        if i in lebend and not (i in stand and passt(neu / stand[i], g)):
            if kopieren(ablage / lebend[i], neu / lebend[i]):
                stand[i] = lebend[i]
            else:   # beim Kopieren verschwunden (Entwurf gelöscht)
                del lebend[i]
                stand.pop(i, None)
        if not (i in stand and passt(neu / stand[i], g)) and i in alt and (i not in stand or passt(v / alt[i], g)):
            z = neu / alt[i]
            z.parent.mkdir(parents=True, exist_ok=True)
            z.unlink(missing_ok=True)
            os.link(v / alt[i], z)
            stand[i] = alt[i]
        if i not in lebend:
            fehlen.append((i, dok))
        if i in stand and not passt(neu / stand[i], g):
            anders.append(i)
        elif i in lebend and g is not None and da[lebend[i]].st_size != g:
            aus_stand.append(i)
    mit_sha = sorted(i for i, (_, _, s) in refs.items() if s and i in stand and i not in anders)
    tag = date.fromisoformat(zeit[:10]).toordinal() % RUNDE
    probe = {i for i in mit_sha if zlib.crc32(i.encode()) % RUNDE == tag} | set(random.sample(mit_sha, min(STICHPROBE, len(mit_sha))))
    geheilt, falsch = [], []
    for i in sorted(probe):
        s = refs[i][2]
        if sha256(neu / stand[i]) == s:
            continue
        if i in lebend and sha256(ablage / lebend[i]) == s and kopieren(ablage / lebend[i], neu / stand[i]) \
                and sha256(neu / stand[i]) == s:
            geheilt.append(i)
        else:
            falsch.append(i)
    liste = ziel.parent / '.dateien-fehlend'
    if fehlen:
        liste.write_text(''.join(f'{i}\t{dok}\t{ablage / stand[i] if i in stand else "fehlt in Ablage und Sicherung"}\n'
                                 for i, dok in fehlen))
    else:
        liste.unlink(missing_ok=True)
    weg = [i for i, _ in fehlen if i not in stand]
    warnungen = []
    if len(fehlen) > len(weg):
        warnungen.append(f'{len(fehlen) - len(weg)} Datei(en) fehlen in der Ablage, in der Sicherung erhalten (Stand {zeit}), '
                         'zurückholen: python3 deploy/dateien_sichern.py zurueckholen sicherungen/dateien')
    if weg:
        warnungen.append(f'{len(weg)} Datei(en) fehlen in Ablage und Sicherung ({kurz(weg)}), Liste: sicherungen/.dateien-fehlend')
    if aus_stand:
        warnungen.append(f'{len(aus_stand)} Datei(en) in der Ablage mit anderer Größe als im Dokument, passende Fassung aus Stand '
                         f'{v.name} gesichert ({kurz(aus_stand)})')
    if anders:
        warnungen.append(f'{len(anders)} Datei(en) mit anderer Größe als im Dokument, vorhandene Fassung gesichert ({kurz(anders)})')
    if geheilt:
        warnungen.append(f'{len(geheilt)} beschädigte Kopie(n) in der Sicherung neu kopiert ({kurz(geheilt)})')
    if falsch:
        warnungen.append(f'{len(falsch)} Datei(en) mit falscher Prüfsumme in Sicherung und Ablage, vorhandene Fassung gesichert ({kurz(falsch)})')
    if kaputt:
        warnungen.append(f'{len(kaputt)} Dokument(e) nicht lesbar, Verweise darin nicht geprüft ({kurz(kaputt)})')
    zustand = 'kritisch' if len(fehlen) > KRITISCH or len(fehlen) * 100 > len(refs) else 'warnung' if warnungen else 'ok'
    return zustand, warnungen


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


def abschliessen(ziel, zeit, zustand):
    s = staende(ziel)
    letzte = dateien(ziel / zeit).values()
    liste = ziel.parent / '.dateien-fehlend'
    return {'anzahl': len(letzte), 'groesse': sum(st.st_size for st in letzte), 'neu': sum(st.st_size for st in letzte if st.st_nlink == 1),
            'staende': len(s), 'belegt': belegt(s), 'fehlend': len(liste.read_text().splitlines()) if liste.is_file() else 0,
            'zustand': zustand}


def fehlende(ablage, daten):
    lebend = {NAME.fullmatch(rel).group(1): st for rel, st in dateien(ablage).items()}
    for d in daten:
        refs, kaputt = verweise(d)
        for name in kaputt:
            yield '-', name, 'Dokument nicht lesbar'
        for i, (dok, g, _) in sorted(refs.items()):
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
    for name, felder in (('bedarf', 'ablage ziel zeit?'), ('aufbauen', 'ablage ziel zeit'), ('pruefen', 'ablage ziel zeit daten+'),
                         ('abschliessen', 'ziel zeit zustand?'), ('fehlende', 'ablage daten+'), ('zurueckholen', 'ziel')):
        u = b.add_parser(name)
        for f in felder.split():   # Endung ? = optional, + = mindestens einmal
            n = f.rstrip('?+')
            u.add_argument(n, type=zeit if n == 'zeit' else str if n == 'zustand' else Path, nargs=f[len(n):] or None)
    a = p.parse_args()
    if 'ablage' in a and a.ablage.is_symlink():
        p.error('Dateiablage ist ein Verweis')
    if a.befehl == 'bedarf':
        print(bedarf(a.ablage, a.ziel, a.zeit))
    elif a.befehl == 'aufbauen':
        aufbauen(a.ablage, a.ziel, a.zeit)
    elif a.befehl == 'pruefen':
        zustand, warnungen = pruefen(a.ablage, a.ziel, a.zeit, a.daten)
        print(zustand)
        if warnungen:
            print('; '.join(warnungen), file=sys.stderr)
    elif a.befehl == 'abschliessen':
        print(json.dumps(abschliessen(a.ziel, a.zeit, a.zustand or 'ok'), separators=(',', ':')))
    elif a.befehl == 'zurueckholen':
        da, offen = zurueckholen(a.ziel)
        print(f'{da} Datei(en) zurückgeholt' + (f', {offen} nicht (Gründe oben)' if offen else ''))
        sys.exit(1 if offen else 0)
    else:
        for zeile in fehlende(a.ablage, a.daten):
            print(*zeile, sep='\t')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, sqlite3.Error) as e:
        print(f'Dateisicherung: {e}', file=sys.stderr)
        sys.exit(1)
