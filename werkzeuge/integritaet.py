#!/usr/bin/env python3
"""Prüfliste der Dateiprüfung (app/api/lib/integritaet-liste.php): prüfen, dass sie NICHT im Repository steht.

Die Liste (Pfad unter app/ => SHA-256) entsteht beim Einspielen aus genau dem freigegebenen Commit
(deploy/bereitstellen.py) und liegt dann im nur lesend eingebundenen Programmordner – wie früher, nur ohne
Merge-Konflikte. Die Dateiprüfung im Eingabebereich (Sicherheit → Dateiprüfung) vergleicht damit den Stand auf dem
Server und meldet veränderte, fehlende und unbekannte Dateien; fehlt die Liste, meldet sie das als kritisch.

  python3 werkzeuge/integritaet.py           prüfen (CI): Liste nicht versioniert, in .gitignore, Erzeugung funktioniert
  python3 werkzeuge/integritaet.py --setzen  eine lokal liegende Liste entfernen (früherer Arbeitsschritt, jetzt unnötig)
  python3 werkzeuge/integritaet.py --zeigen  Liste ausgeben, wie sie der Server für den Arbeitsstand erzeugen würde
"""
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
_spec = importlib.util.spec_from_file_location('bereitstellen', ROOT / 'deploy' / 'bereitstellen.py')
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
REL = 'app/' + B.LISTE
LISTE = ROOT / REL


def git(*args) -> int:
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True).returncode


def main() -> int:
    args = sys.argv[1:]
    if '--setzen' in args:
        if LISTE.exists() and git('ls-files', '--error-unmatch', REL) != 0:
            LISTE.unlink()
            print(f'Lokale Prüfliste entfernt: {REL}')
        print('Nichts weiter zu tun – die Prüfliste erzeugt der Server beim Einspielen (deploy/bereitstellen.py).')
        return 0
    seiten, liste, fehlend = B.bereitstellung(B.ordner_dateien(APP))
    if '--zeigen' in args:
        sys.stdout.write(B.liste_php(liste, 'dem Arbeitsstand').decode('utf-8'))
        return 0
    fehler = []
    if git('ls-files', '--error-unmatch', REL) == 0:
        fehler.append(f'{REL} steht im Repository – entfernen (git rm --cached {REL}); sie entsteht beim Einspielen.')
    if git('check-ignore', '-q', REL) != 0:
        fehler.append(f'{REL} fehlt in .gitignore.')
    if not {'index.html', '.htaccess', 'api/index.php', 'api/lib/integritaet.php'} <= set(liste) or B.LISTE in liste:
        fehler.append('Erzeugung der Prüfliste liefert nicht die erwarteten Dateien.')
    fehler += fehlend
    if fehler:
        print('\n'.join(fehler))
        return 1
    print(f'Prüfliste in Ordnung: nicht im Repository, entsteht beim Einspielen ({len(liste)} Dateien).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
