"""QM-System: „dateien“ an Ordnern und externen Dokumenten nur in den vier Lesern von app/api/module/qs/ablage.php lesen.

Ältere Dateien liegen am Dokument (qs-dokumente, „dateien“), neue in qs-ablage. Wer nur eines davon liest, übersieht Dateien.
Darum lesen alle anderen Stellen über qs_ablage_nach_ziel, qs_ordner_dateien, qs_ablage_belegt und qs_datei_suchen; im Browser
liefert der Server die Zahlen (ablageZahlen) und die Dateien (qs_archiv). Aufruf: python3 werkzeuge/qs_ablage_leser.py – Exitcode 1
mit den Fundstellen. Läuft in der E2E-Gruppe qs_eingang (also in der CI).
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
LESER = ('qs_ablage_nach_ziel', 'qs_ordner_dateien', 'qs_ablage_belegt', 'qs_datei_suchen')
PHP = re.compile(r"\$(?:d|x|alt|dok|od|o)\['dateien'\](?!\s*\[[^\]]*\]\s*=[^=>])")   # Lesen; Schreiben einer Datei ($d['dateien'][$k] = …) ist erlaubt
JS = re.compile(r"\b(?:x|dok)\.dateien\b")   # x/dok = Dokument; o ist im Code eine Version bzw. ein gewählter Ordner


def funde(wurzel=WURZEL):
    aus = []
    php = sorted((wurzel / 'app/api/module/qs').glob('*.php')) + [wurzel / 'app/api/aktionen/qs.php']
    for p in php:
        funktion = ''
        for n, zeile in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            m = re.match(r'function (\w+)', zeile)
            if m:
                funktion = m.group(1)
            if PHP.search(zeile) and not (p.name == 'ablage.php' and funktion in LESER):
                aus.append(f'{p.relative_to(wurzel)}:{n}: {zeile.strip()[:140]}')
    for p in sorted((wurzel / 'app/module/qs').glob('*.js')):
        for n, zeile in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            if JS.search(zeile):
                aus.append(f'{p.relative_to(wurzel)}:{n}: {zeile.strip()[:140]}')
    return aus


if __name__ == '__main__':
    f = funde()
    for x in f:
        print(x)
    print('„dateien“ an Ordnern nur über die Leser in module/qs/ablage.php: ' + ('ok' if not f else f'{len(f)} Fundstellen'))
    sys.exit(1 if f else 0)
