"""ZIP-Export der Dateiablage (app/api/lib/dateiablage.php, ablage_zip_senden) über die Grenzen des klassischen ZIP-Formats:
kleines Archiv ohne Zip64-Felder; Versatz über 4 GB (18 Dateien zu 250 MB, als Lücken-Dateien ohne Platz auf der Platte) mit
Umlauten in den Namen und genau 65535 Einträge mit Zip64-Feldern, 65534 noch ohne; eine Datei, die während des Exports
verschwindet, fehlt im Archiv, das gültig bleibt. Geprüft mit Pythons zipfile (Prüfsummen aller Einträge) und Info-ZIP unzip
(prüft auch, dass lokaler und zentraler Name gleich gelesen werden)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MB = 1024 * 1024
fehler = []


def check(n, c, i=''):
    print(('PASS ' if c else 'FAIL ') + n + (f'  {i}' if i and not c else ''))
    if not c:
        fehler.append(n)


def export(wurzel, eintraege, ziel, nach_erstem_teil=None):
    """ZIP über das Hilfsskript erzeugen; lange Nullfolgen als Lücke schreiben (die Testdateien bestehen fast nur aus Nullen).
    nach_erstem_teil läuft, sobald das erste MB gelesen ist – PHP wartet dann am vollen Puffer der Leitung. Rückgabe: ZipFile,
    Zip64-Ende vorhanden, Fehlerausgabe von PHP"""
    p = subprocess.Popen(['php', '-d', 'memory_limit=128M', os.path.join(REPO, 'tests', 'unit', 'dateiablage_zip.php')],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.stdin.write(json.dumps({'wurzel': wurzel, 'eintraege': eintraege}).encode()); p.stdin.close()
    null = bytes(MB)
    with open(ziel, 'wb') as f:
        while b := p.stdout.read(MB):
            if b == null[:len(b)]:
                f.seek(len(b), 1)
            else:
                f.write(b)
            if nach_erstem_teil:
                nach_erstem_teil(); nach_erstem_teil = None
        f.truncate()
    fehler_php = p.stderr.read().decode()
    assert p.wait() == 0, 'PHP-Fehler: ' + fehler_php
    with open(ziel, 'rb') as f:
        f.seek(max(0, os.path.getsize(ziel) - 200)); ende = f.read()
    return zipfile.ZipFile(ziel), b'PK\x06\x06' in ende, fehler_php


def unzip_test(ziel):
    """Info-ZIP unzip -t: 0 nur ohne Warnung (z. B. „mismatching local filename“)"""
    p = subprocess.run(['unzip', '-tq', ziel], capture_output=True, text=True, env={**os.environ, 'LC_ALL': 'C'})
    return p.returncode == 0, (p.stdout + p.stderr)[-500:]


assert shutil.which('unzip'), 'Info-ZIP unzip fehlt (apt install unzip)'


with tempfile.TemporaryDirectory() as tmp:
    def datei(i, inhalt, groesse):
        did = f'ab{i:018d}'
        pfad = os.path.join(tmp, 'dateien', 'qs', did[:2], did + '.bin')
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, 'wb') as f:
            f.write(inhalt); f.truncate(groesse)
        return {'pfad': f'QM-System/1.4 Qualität/Datei {i}.pdf', 'bereich': 'qs', 'id': did}

    z, z64, _ = export(tmp, [datei(0, b'%PDF-klein', 1000), {'pfad': 'QM-System/Dokumentenliste.csv', 'inhalt': 'Nr;Titel\r\n'}], os.path.join(tmp, 'klein.zip'))
    check('kleines Archiv: klassisches ZIP ohne Zip64-Felder, Inhalt gleich', not z64 and z.testzip() is None
          and z.read('QM-System/Dokumentenliste.csv') == b'Nr;Titel\r\n' and z.read('QM-System/1.4 Qualität/Datei 0.pdf')[:10] == b'%PDF-klein')

    gross = [datei(i, b'%PDF-' + str(i).encode(), 250 * MB) for i in range(18)]
    z, z64, _ = export(tmp, [{'pfad': 'QM-System/Dokumentenliste.csv', 'inhalt': 'Nr;Titel\r\n'}] + gross, os.path.join(tmp, 'gross.zip'))
    infos = z.infolist()
    check('über 4 GB: Zip64, alle 19 Einträge lesbar, Versatz über 4 GB, Prüfsummen stimmen', z64 and len(infos) == 19 and max(i.header_offset for i in infos) > 0xFFFFFFFF
          and z.testzip() is None and z.read(infos[-1].filename)[:7] == b'%PDF-17', [i.header_offset for i in infos[-2:]])
    z.close()
    check('über 4 GB: unzip liest Namen mit Umlaut nach 4 GB lokal und zentral gleich', *unzip_test(os.path.join(tmp, 'gross.zip')))
    os.remove(os.path.join(tmp, 'gross.zip'))

    for n, soll in ((65534, False), (65535, True)):
        z, z64, _ = export(tmp, [{'pfad': f'K/{i}.txt', 'inhalt': f'x{i}'} for i in range(n)], os.path.join(tmp, f'n{n}.zip'))
        check(f'{n} Einträge: {"mit" if soll else "ohne"} Zip64, alle lesbar', z64 == soll and len(z.infolist()) == n and z.read(f'K/{n - 1}.txt') == f'x{n - 1}'.encode())

    weg = datei(30, b'%PDF-weg', 1000)
    z, _, log = export(tmp, [datei(31, b'%PDF-vorher', 20 * MB), weg, datei(32, b'%PDF-nachher', 1000)], os.path.join(tmp, 'weg.zip'),
                       lambda: os.remove(os.path.join(tmp, 'dateien', 'qs', 'ab', weg['id'] + '.bin')))
    namen = z.namelist()
    check('Datei verschwindet während des Exports: fehlt im Archiv, Archiv gültig, im Protokoll vermerkt', namen == ['QM-System/1.4 Qualität/Datei 31.pdf', 'QM-System/1.4 Qualität/Datei 32.pdf']
          and z.testzip() is None and unzip_test(os.path.join(tmp, 'weg.zip'))[0] and 'Datei 30.pdf' in log, (namen, log))

print('FEHLER: ' + ', '.join(fehler) if fehler else 'alle Prüfungen bestanden')
sys.exit(1 if fehler else 0)
