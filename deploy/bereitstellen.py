#!/usr/bin/env python3
"""Bereitstellung eines Stands: Versionsnummern der Skripte/Stylesheets und Prüfliste der Dateiprüfung.

Beides wird nicht mehr im Repository gepflegt (dort entstanden bei fast jedem Pull Request Merge-Konflikte), sondern
beim Einspielen aus genau dem aktiven Commit erzeugt – dem Commit, den der Release-Prozess geprüft hat (freigegeben,
CI grün, auf main). Gelesen wird aus den Git-Objekten dieses Commits, nicht aus dem Arbeitsordner: eine vor oder
während des Einspielens veränderte oder hinzugefügte Datei wird so nie als „freigegeben“ übernommen.

1. Versionsnummern: Jede Einbindung einer eigenen .js- oder .css-Datei (src/href, relativ oder ab /, nie fremde
   Adressen) in einer HTML-Seite unter app/ – Angebotsseite, Eingabebereich und Modulseiten – und im Dashboard
   (dashboard/, im Betrieb unter /dashboard/ neben app/) bekommt ?v=<SHA-256 des Inhalts, 10 Zeichen>. Caddy speichert
   Adressen mit ?v= ein Jahr („immutable“, auf den Mitarbeiter-Hosts nur im Browser), alles andere nur mit Rückfrage
   („no-cache“). Fehlt die Nummer (z. B. direkt nach „git reset“ oder wenn dieses Skript nicht lief), lädt der Browser
   also trotzdem immer die aktuelle Fassung.
   Eine Seite wird nur überschrieben, wenn sie genau dem Commit entspricht (ohne oder mit Nummern); eine anders
   veränderte Seite bleibt unangetastet, damit die Dateiprüfung sie meldet.
2. Prüfliste app/api/lib/integritaet-liste.php (Pfad unter app/ => SHA-256) für Sicherheit → Dateiprüfung. HTML-Seiten
   stehen mit beiden zulässigen Fassungen darin (mit und ohne Versionsnummern), beide stammen aus dem Commit.
   Die Datei liegt im Programmordner, der im Container nur lesend eingebunden ist (wie bisher).

Ein Commit, der die Prüfliste selbst noch enthält (Stand vor dieser Umstellung, z. B. nach einem Rückfall), bringt
Nummern und Liste mit – dann ändert dieses Skript nichts.

  python3 deploy/bereitstellen.py                    Stand HEAD dieses Ordners bereitstellen (Server; mehrfach
                                                     aufrufbar, schreibt nur bei Abweichung)
  python3 deploy/bereitstellen.py --pruefen          nur prüfen: entspricht app/ dem bereitgestellten Stand HEAD?
  python3 deploy/bereitstellen.py --verzeichnis DIR  Kopie eines app/-Ordners aus ihren eigenen Dateien bereitstellen
                                                     (Testserver, tests/run_e2e.py)
Ausgang 0 = in Ordnung, 1 = Fehler bzw. Abweichung.
"""
import hashlib
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
ZUSATZ = 'dashboard'   # Seiten außerhalb von app/, im Betrieb unter /dashboard/ (Alias, apache-oidc.conf) – nicht in der Prüfliste
LISTE = 'api/lib/integritaet-liste.php'            # relativ zu app/
# Eigene Skripte und Stylesheets: relativ (qs.js, ../../assets/app.css) oder ab / – keine Adressen mit Schema oder //
REF = re.compile(r'''(?P<attr>(?:src|href)=")(?P<pfad>(?![a-zA-Z][a-zA-Z0-9+.-]*:|//)[^"?#]+\.(?:js|css))(?:\?v=[^"#]*)?"''')
REF_B = re.compile(REF.pattern.encode())
KOPF = ("<?php if (!defined('WA_API')) { http_response_code(404); exit; }\n"
        "/* Prüfliste der ausgelieferten Dateien (Pfad unter app/ => SHA-256) für die Dateiprüfung.\n"
        "   Erzeugt beim Einspielen von deploy/bereitstellen.py aus @QUELLE@ – nicht von Hand ändern.\n"
        "   HTML-Seiten: [mit Versionsnummern, ohne Versionsnummern]; beide Fassungen stammen aus dem Commit. */\n")


def version(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()[:10]


def ausgeliefert(rel: str) -> bool:
    """Gehört die Datei (Pfad unter app/) zur Prüfliste? Nicht: Datenordner, Arbeitsordner, die Liste selbst."""
    teile = rel.split('/')
    return teile[0] != 'data' and '.arbeit' not in teile and rel != LISTE


def ist_seite(rel: str) -> bool:
    return rel.endswith('.html') and '.arbeit' not in rel.split('/')


def ziel(seite: str, pfad: str) -> str:
    """Pfad einer Einbindung relativ zu app/ (wie im Browser aufgelöst)."""
    if pfad.startswith('/'):
        return pfad.lstrip('/')
    return posixpath.normpath(posixpath.join(posixpath.dirname(seite), pfad))


def stempeln(seite: str, inhalt: bytes, dateien: dict, fehlend: list) -> bytes:
    """HTML-Seite mit Versionsnummern aus dem Inhalt der eingebundenen Dateien (fehlt eine Datei: ohne Nummer)."""
    def ersetzen(m):
        pfad = m.group('pfad').decode()
        datei = dateien.get(ziel(seite, pfad))
        if datei is None:
            fehlend.append(f'{seite}: {pfad} existiert nicht')
            return m.group('attr') + m.group('pfad') + b'"'
        return m.group('attr') + m.group('pfad') + b'?v=' + version(datei).encode() + b'"'
    return REF_B.sub(ersetzen, inhalt)


def ohne_versionen(inhalt: bytes) -> bytes:
    return REF_B.sub(lambda m: m.group('attr') + m.group('pfad') + b'"', inhalt)


def bereitstellung(dateien: dict) -> tuple:
    """dateien: Pfad unter app/ → Inhalt (wie im Commit). Ergebnis: (Seiten: Pfad → gestempelt, Liste: Pfad → [Hashes], fehlend)."""
    fehlend, seiten, liste = [], {}, {}
    for rel in sorted(dateien):
        if ist_seite(rel):
            seiten[rel] = stempeln(rel, dateien[rel], dateien, fehlend)
    for rel in sorted(dateien):
        if not ausgeliefert(rel):
            continue
        hashes = [hashlib.sha256(seiten.get(rel, dateien[rel])).hexdigest()]
        if rel in seiten and seiten[rel] != dateien[rel]:
            hashes.append(hashlib.sha256(dateien[rel]).hexdigest())
        liste[rel] = hashes
    return seiten, liste, fehlend


def zusatz_seiten(dateien: dict, zusatz: dict) -> tuple:
    """Seiten des Dashboards stempeln. zusatz: Pfad unter dashboard/ → Inhalt; Einbindungen werden wie im Browser
    aufgelöst (/dashboard/ liegt neben app/: ../assets/app.css → assets/app.css). Ergebnis: (Pfad unter dashboard/ →
    gestempelt, fehlend)."""
    alle = {**dateien, **{ZUSATZ + '/' + k: v for k, v in zusatz.items()}}
    fehlend, seiten = [], {}
    for k in sorted(zusatz):
        if ist_seite(k):
            seiten[k] = stempeln(ZUSATZ + '/' + k, zusatz[k], alle, fehlend)
    return seiten, fehlend


def php_text(s: str) -> str:
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


def liste_php(liste: dict, quelle: str) -> bytes:
    zeilen = [KOPF.replace("@QUELLE@", quelle), 'return [\n']
    for rel, hashes in liste.items():
        wert = php_text(hashes[0]) if len(hashes) == 1 else '[' + ', '.join(php_text(h) for h in hashes) + ']'
        zeilen.append(f'    {php_text(rel)} => {wert},\n')
    zeilen.append('];\n')
    return ''.join(zeilen).encode('utf-8')


def schreiben(pfad: Path, inhalt: bytes, modus: int = 0o644) -> None:
    """Atomar ersetzen (Apache liest nie eine halb geschriebene Datei); lesbar für den Webserver."""
    tmp = pfad.with_name('.' + pfad.name + '.bereitstellen-tmp')
    try:
        with open(tmp, 'wb') as f:
            f.write(inhalt)
        os.chmod(tmp, modus)
        os.replace(tmp, pfad)
    finally:
        if tmp.exists():
            tmp.unlink()


def lesen(pfad: Path):
    try:
        return pfad.read_bytes() if pfad.is_file() and not pfad.is_symlink() else None
    except OSError:
        return None


# ─────────────── Quelle: Git-Objekte des Commits (Server) ───────────────

def git(*args, eingabe=None) -> bytes:
    return subprocess.run(['git', '-C', str(WURZEL), *args], input=eingabe, capture_output=True, check=True).stdout


def commit_dateien(commit: str, ordner: str = 'app') -> dict:
    """Pfad unter <ordner>/ → Inhalt aller normalen Dateien des Commits (ohne Verweise und Untermodule)."""
    eintraege = []
    for z in git('ls-tree', '-r', '-z', '--full-tree', commit, '--', ordner).split(b'\0'):
        if not z:
            continue
        kopf, pfad = z.split(b'\t', 1)
        modus, art, sha = kopf.split(b' ')
        if art == b'blob' and modus in (b'100644', b'100755'):
            eintraege.append((pfad.decode('utf-8')[len(ordner) + 1:], sha.decode()))
    if not eintraege:
        return {}
    roh = git('cat-file', '--batch', eingabe=''.join(s + '\n' for _, s in eintraege).encode())
    dateien, pos = {}, 0
    for rel, sha in eintraege:
        ende = roh.index(b'\n', pos)
        teile = roh[pos:ende].split(b' ')
        if teile[0].decode() != sha or teile[1] != b'blob':
            raise RuntimeError(f'Git-Objekt {sha} ({rel}) nicht lesbar')
        groesse = int(teile[2])
        dateien[rel] = roh[ende + 1:ende + 1 + groesse]
        pos = ende + 1 + groesse + 1
    return dateien


def server(nur_pruefen: bool) -> int:
    try:
        commit = git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f'Bereitstellung: kein Git-Stand in {WURZEL} ({e})')
        return 1
    if subprocess.run(['git', '-C', str(WURZEL), 'cat-file', '-e', f'{commit}:app/{LISTE}'], capture_output=True).returncode == 0:
        if nur_pruefen:
            print(f'Stand {commit[:12]} bringt Versionsnummern und Prüfliste selbst mit (ältere Fassung).')
        return 0
    dateien = commit_dateien(commit)
    seiten, liste, fehlend = bereitstellung(dateien)
    for f in fehlend:
        print(f'Hinweis: {f} – Einbindung bleibt ohne Versionsnummer')
    app = WURZEL / 'app'
    abweichend, geschrieben = [], []
    for rel, inhalt in dateien.items():
        if not ausgeliefert(rel):
            continue
        ist = lesen(app / rel)
        gestempelt = seiten.get(rel, inhalt)
        if ist == gestempelt:
            continue
        if ist == inhalt and rel in seiten:          # Seite genau wie im Commit, nur ohne Nummern → Nummern setzen
            if not nur_pruefen:
                schreiben(app / rel, gestempelt, (app / rel).stat().st_mode & 0o777)
                geschrieben.append(rel)
            else:
                abweichend.append(f'{rel}: ohne Versionsnummern')
        elif ist != inhalt:
            abweichend.append(f'{rel}: {"fehlt" if ist is None else "weicht vom Commit ab"}')
    soll = liste_php(liste, f'Commit {commit}')
    if lesen(app / LISTE) != soll:
        if nur_pruefen:
            abweichend.append(f'{LISTE}: {"fehlt" if not (app / LISTE).exists() else "passt nicht zum Commit"}')
        else:
            schreiben(app / LISTE, soll)
            geschrieben.append(LISTE)
    # Dashboard (neben app/) erst nach der Prüfliste: ein Fehler hier lässt Seiten und Prüfliste unter app/ unberührt
    try:
        zusatz = commit_dateien(commit, ZUSATZ)
        zseiten, zfehlend = zusatz_seiten(dateien, zusatz)
        for f in zfehlend:
            print(f'Hinweis: {f} – Einbindung bleibt ohne Versionsnummer')
        for k, gestempelt in zseiten.items():
            pfad = WURZEL / ZUSATZ / k
            ist = lesen(pfad)
            if ist == gestempelt:
                continue
            if ist == zusatz[k]:
                if not nur_pruefen:
                    schreiben(pfad, gestempelt, pfad.stat().st_mode & 0o777)
                    geschrieben.append(f'{ZUSATZ}/{k}')
                else:
                    abweichend.append(f'{ZUSATZ}/{k}: ohne Versionsnummern')
            else:
                abweichend.append(f'{ZUSATZ}/{k}: {"fehlt" if ist is None else "weicht vom Commit ab"}')
    except (OSError, subprocess.CalledProcessError) as e:
        abweichend.append(f'{ZUSATZ}/: nicht bereitgestellt ({e})')
    if geschrieben:
        print(f'Bereitgestellt für {commit[:12]}: ' + ', '.join(geschrieben))
    if abweichend:
        print(('Abweichungen vom Stand ' if nur_pruefen else 'Nicht verändert (weicht vom Commit ab – die Dateiprüfung meldet es): ')
              + commit[:12] + '\n  ' + '\n  '.join(abweichend))
        return 1
    if nur_pruefen:
        print(f'app/ entspricht dem bereitgestellten Stand {commit[:12]} ({len(liste)} Dateien in der Prüfliste).')
    return 0


# ─────────────── Quelle: Ordner (Testkopie, CI-Prüfung) ───────────────

def ordner_dateien(app: Path) -> dict:
    dateien = {}
    for ordner, unter, namen in os.walk(app):
        rel = Path(ordner).relative_to(app)
        if rel == Path('.'):
            unter[:] = [u for u in unter if u != 'data']
        for n in namen:
            p = Path(ordner) / n
            r = p.relative_to(app).as_posix()
            if r == LISTE or p.is_symlink() or not p.is_file():
                continue
            dateien[r] = p.read_bytes()
    return dateien


def verzeichnis(app: Path, quelle: str = 'einer Arbeitskopie') -> int:
    """Kopie eines app/-Ordners bereitstellen: Seiten stempeln, Prüfliste schreiben (wie auf dem Server)."""
    dateien = ordner_dateien(app)
    seiten, liste, fehlend = bereitstellung(dateien)
    for rel, inhalt in seiten.items():
        if inhalt != dateien[rel]:
            schreiben(app / rel, inhalt, (app / rel).stat().st_mode & 0o777)
    schreiben(app / LISTE, liste_php(liste, quelle))
    for f in fehlend:
        print(f'Hinweis: {f}')
    return 1 if fehlend else 0


def zusatz_verzeichnis(app: Path) -> int:
    """Im Testlauf unter app/dashboard/ eingeblendetes Dashboard (tests/run_e2e.py, ZUSATZ) wie auf dem Server stempeln."""
    vorsilbe = ZUSATZ + '/'
    dateien = ordner_dateien(app)
    zusatz = {k[len(vorsilbe):]: v for k, v in dateien.items() if k.startswith(vorsilbe)}
    seiten, fehlend = zusatz_seiten({k: v for k, v in dateien.items() if not k.startswith(vorsilbe)}, zusatz)
    for k, inhalt in seiten.items():
        if inhalt != zusatz[k]:
            schreiben(app / ZUSATZ / k, inhalt, (app / ZUSATZ / k).stat().st_mode & 0o777)
    for f in fehlend:
        print(f'Hinweis: {f}')
    return 1 if fehlend else 0


def main(argv) -> int:
    if argv[:1] == ['--verzeichnis'] and len(argv) == 2:
        return verzeichnis(Path(argv[1]).resolve())
    if argv in ([], ['--pruefen']):
        return server(argv == ['--pruefen'])
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
