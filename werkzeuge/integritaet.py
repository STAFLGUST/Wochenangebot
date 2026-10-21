#!/usr/bin/env python3
"""Prüfliste der ausgelieferten Programmdateien prüfen bzw. neu erzeugen.

app/api/lib/integritaet-liste.php enthält für jede Datei unter app/ (außer app/data/ und der Liste selbst)
die SHA-256-Prüfsumme. Die Dateiprüfung im Eingabebereich (Sicherheit → Dateiprüfung) vergleicht damit
den Stand auf dem Server und meldet veränderte, fehlende und unbekannte Dateien.

  python3 werkzeuge/integritaet.py           prüfen (Exit 1 bei veralteter Liste)
  python3 werkzeuge/integritaet.py --setzen  Liste neu erzeugen

Reihenfolge nach Änderungen unter app/: erst asset_versionen.py --setzen (ändert HTML-Seiten), dann diese Liste.
"""
import hashlib
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
LISTE = APP / 'api' / 'lib' / 'integritaet-liste.php'
KOPF = ("<?php if (!defined('WA_API')) { http_response_code(404); exit; }\n"
        "/* Prüfliste der ausgelieferten Dateien (Pfad unter app/ => SHA-256) für die Dateiprüfung.\n"
        "   Automatisch erzeugt mit: python3 werkzeuge/integritaet.py --setzen – nicht von Hand ändern. */\n")


def dateien():
    out = []
    for ordner, unter, namen in os.walk(APP):
        rel = pathlib.Path(ordner).relative_to(APP)
        if rel.parts[:1] == ('data',):
            unter[:] = []
            continue
        unter[:] = [u for u in unter if not (rel == pathlib.Path('.') and u == 'data')]
        for n in namen:
            p = pathlib.Path(ordner) / n
            if p == LISTE or p.is_symlink() or not p.is_file():
                continue
            out.append((p.relative_to(APP).as_posix(), p))
    return sorted(out)


def inhalt() -> str:
    zeilen = [KOPF, 'return [\n']
    for rel, p in dateien():
        pfad = rel.replace('\\', '\\\\').replace("'", "\\'")
        zeilen.append(f"    '{pfad}' => '{hashlib.sha256(p.read_bytes()).hexdigest()}',\n")
    zeilen.append('];\n')
    return ''.join(zeilen)


def main() -> int:
    neu = inhalt()
    if '--setzen' in sys.argv[1:]:
        with open(LISTE, 'w', encoding='utf-8', newline='\n') as f:
            f.write(neu)
        print(f'Prüfliste geschrieben: {LISTE.relative_to(ROOT)} ({neu.count(" => ")} Dateien)')
        return 0
    alt = LISTE.read_bytes().decode('utf-8') if LISTE.is_file() else ''
    if alt != neu:
        print('Prüfliste der Dateien (app/api/lib/integritaet-liste.php) ist veraltet.\n'
              'Bitte zuerst python3 werkzeuge/asset_versionen.py --setzen und danach\n'
              'python3 werkzeuge/integritaet.py --setzen ausführen (die Versionsnummern ändern HTML-Seiten).')
        return 1
    print('Prüfliste aktuell.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
