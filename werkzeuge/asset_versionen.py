#!/usr/bin/env python3
"""Versionsnummern der eingebundenen Skripte und Stylesheets prüfen bzw. setzen.

Jede Einbindung von /assets/... in den HTML-Seiten unter app/ trägt ?v=<Prüfsumme>.
Die Prüfsumme ergibt sich aus dem Dateiinhalt. Ändert sich eine Datei, ändert sich
ihre Adresse – Browser laden sie dann sicher neu statt eine alte Kopie zu verwenden.

  python3 werkzeuge/asset_versionen.py           prüfen (Exit 1 bei veralteter Nummer)
  python3 werkzeuge/asset_versionen.py --setzen  alle Nummern aktualisieren
"""
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
REF = re.compile(r'''(?P<attr>(?:src|href)=")(?P<pfad>(?:\.\./|/)?assets/[^"?#]+\.(?:js|css))(?:\?v=[^"#]*)?"''')


def version(datei: pathlib.Path) -> str:
    return hashlib.sha256(datei.read_bytes()).hexdigest()[:10]


def seiten():
    for p in sorted(APP.rglob('*.html')):
        if '.arbeit' not in p.parts:
            yield p


def ziel(seite: pathlib.Path, pfad: str) -> pathlib.Path:
    return APP / pfad.lstrip('/') if pfad.startswith('/') else (seite.parent / pfad).resolve()


def main() -> int:
    setzen = '--setzen' in sys.argv[1:]
    fehler = []
    for seite in seiten():
        text = seite.read_text(encoding='utf-8')

        def ersetzen(m):
            datei = ziel(seite, m.group('pfad'))
            if not datei.is_file():
                fehler.append(f'{seite.relative_to(ROOT)}: {m.group("pfad")} existiert nicht')
                return m.group(0)
            neu = f'{m.group("attr")}{m.group("pfad")}?v={version(datei)}"'
            if neu != m.group(0) and not setzen:
                fehler.append(f'{seite.relative_to(ROOT)}: {m.group("pfad")} braucht ?v={version(datei)}')
            return neu

        neu = REF.sub(ersetzen, text)
        if setzen and neu != text:
            seite.write_text(neu, encoding='utf-8')
            print(f'aktualisiert: {seite.relative_to(ROOT)}')
    if fehler:
        print('\n'.join(fehler))
        if not setzen:
            print('\nVersionsnummern veraltet – bitte ausführen: python3 werkzeuge/asset_versionen.py --setzen')
        return 1
    if not setzen:
        print('Versionsnummern aktuell.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
