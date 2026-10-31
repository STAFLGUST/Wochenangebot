#!/usr/bin/env python3
"""Einbindungen der Skripte und Stylesheets in den HTML-Seiten unter app/ und dashboard/ prüfen.

Versionsnummern (?v=<Prüfsumme des Inhalts>) stehen nicht mehr im Repository: Sie entstanden bei fast jedem Pull
Request neu und lösten Merge-Konflikte aus. Der Server setzt sie beim Einspielen aus genau dem freigegebenen Commit
(deploy/bereitstellen.py) – dieselbe Prüfsumme wie früher, also dieselben Adressen und dasselbe Zwischenspeichern.
Fehlt eine Nummer, lädt der Browser die Datei mit Rückfrage („no-cache“, Caddyfile) – nie eine veraltete Kopie.

  python3 werkzeuge/asset_versionen.py           prüfen: jede eingebundene Datei existiert, keine ?v= im Repository
  python3 werkzeuge/asset_versionen.py --setzen  vorhandene ?v= entfernen (früherer Arbeitsschritt, jetzt unschädlich)
  python3 werkzeuge/asset_versionen.py --zeigen  Seiten so ausgeben, wie der Server sie bereitstellt (nur Anzeige)
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
_spec = importlib.util.spec_from_file_location('bereitstellen', ROOT / 'deploy' / 'bereitstellen.py')
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
ZUSATZ = ROOT / B.ZUSATZ   # Dashboard (im Betrieb unter /dashboard/ neben app/)


def seiten():
    """(Pfad wie im Browser relativ zur App-Wurzel, Datei): Seiten unter app/ und des Dashboards (/dashboard/ neben app/)"""
    for p in sorted(APP.rglob('*.html')):
        rel = p.relative_to(APP).as_posix()
        if B.ist_seite(rel) and B.ausgeliefert(rel):
            yield rel, p
    for p in sorted(ZUSATZ.rglob('*.html')):
        rel = B.ZUSATZ + '/' + p.relative_to(ZUSATZ).as_posix()
        if B.ist_seite(rel):
            yield rel, p


def main() -> int:
    args = sys.argv[1:]
    dateien = B.ordner_dateien(APP)
    dateien.update({B.ZUSATZ + '/' + k: v for k, v in B.ordner_dateien(ZUSATZ).items()})
    fehler = []
    for rel, p in seiten():
        inhalt = p.read_bytes()
        fehlend = []
        gestempelt = B.stempeln(rel, inhalt, dateien, fehlend)
        fehler += fehlend
        ohne = B.ohne_versionen(inhalt)
        if '--setzen' in args:
            if ohne != inhalt:
                p.write_bytes(ohne)
                print(f'Versionsnummern entfernt: {p.relative_to(ROOT).as_posix()}')
        elif '--zeigen' in args:
            print(f'===== {p.relative_to(ROOT).as_posix()}')
            sys.stdout.write(gestempelt.decode('utf-8'))
        elif ohne != inhalt:
            fehler.append(f'{"" if rel.startswith(B.ZUSATZ + "/") else "app/"}{rel}: enthält ?v=… – Versionsnummern setzt der Server beim Einspielen')
    if fehler:
        print('\n'.join(fehler))
        if any('?v=' in f for f in fehler):
            print('\nEntfernen: python3 werkzeuge/asset_versionen.py --setzen')
        return 1
    if not args:
        print('Einbindungen in Ordnung (Versionsnummern setzt der Server beim Einspielen: deploy/bereitstellen.py).')
    elif '--setzen' in args:
        print('Nichts weiter zu tun – Versionsnummern setzt der Server beim Einspielen (deploy/bereitstellen.py).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
