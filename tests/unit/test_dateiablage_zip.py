"""ZIP-Export der Dateiablage (app/api/lib/dateiablage.php, ablage_zip_senden) über die Grenzen des klassischen ZIP-Formats:
kleines Archiv ohne Zip64-Felder; Versatz über 4 GB (18 Dateien zu 250 MB, als Lücken-Dateien ohne Platz auf der Platte) mit
Umlauten in den Namen und genau 65535 Einträge mit Zip64-Feldern, 65534 noch ohne; eine Datei, die während des Exports
verschwindet, fehlt im Archiv, das gültig bleibt. Geprüft mit Pythons zipfile (Prüfsummen aller Einträge) und Info-ZIP unzip
(prüft auch, dass lokaler und zentraler Name gleich gelesen werden).

Prüfung beim Hochladen (ablage_zip_pruefen): die eigenen Exporte, Archive von Pythons zipfile (auch 65535 Einträge ohne Zip64,
Kommentar mit Ende-Signatur, in einen Datenstrom mit Data Descriptor), Info-ZIP, leere Archive, mit NUL-Bytes aufgefüllte Archive
(bsdtar nach stdout) und Ordner wie „chart.js/“ werden angenommen; präparierte Archive, in denen Python, Go, Java, 7-Zip oder
unzip ein Programm zeigen, das Verzeichnis aber nicht (NUL im Namen, falsche Zahl der Einträge, Verzeichnis an anderer Stelle,
Unicode-Pfad, abweichender lokaler Name, Doppelpunkt, „a.exe/.“, „a.exe\\“, versteckter lokaler Kopf vorn oder in einer Lücke,
abweichende lokale Größe, überlappende Köpfe), werden abgelehnt; die Meldung nennt höchstens 5 gesperrte Einträge;
mehr als 200.000 Einträge werden abgelehnt. PHP gibt dabei keine Warnung aus."""
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

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


def pruefen(*pfade):
    """ablage_zip_pruefen über das Hilfsskript: je Datei „ok“ oder die Meldung; jede PHP-Warnung lässt den Test scheitern"""
    p = subprocess.run(['php', '-d', 'error_reporting=-1', '-d', 'display_errors=stderr', os.path.join(REPO, 'tests', 'unit', 'dateiablage_zip.php'), *pfade],
                       capture_output=True, text=True)
    assert p.returncode == 0 and not p.stderr, 'PHP-Fehler: ' + p.stderr
    return json.loads(p.stdout)


def lokal(name, daten, extra=b''):
    return b'PK\x03\x04' + struct.pack('<HHHHHIIIHH', 20, 0x0800, 0, 0, 0x21, zlib.crc32(daten), len(daten), len(daten), len(name), len(extra)) + name + extra + daten


def zentral(name, daten, versatz, extra=b''):
    return b'PK\x01\x02' + struct.pack('<HHHHHHIIIHHHHHII', 20, 20, 0x0800, 0, 0, 0x21, zlib.crc32(daten), len(daten), len(daten), len(name), len(extra),
                                        0, 0, 0, 0, versatz) + name + extra


def ende(anzahl, laenge, start, kommentar=b''):
    return b'PK\x05\x06' + struct.pack('<HHHHIIH', 0, 0, anzahl, anzahl, laenge, start, len(kommentar)) + kommentar


def archiv(eintraege, anzahl=None, extra=None, lokal_extra=None, lokal_name=None):
    """eintraege: [(name, daten)]; anzahl: Zahl im Ende-Satz (Standard: richtig); extra/lokal_extra/lokal_name: {Nummer: Wert}"""
    inhalt, verz, versatz = [], [], 0
    for i, (n, d) in enumerate(eintraege):
        verz.append(zentral(n, d, versatz, (extra or {}).get(i, b'')))
        inhalt.append(lokal((lokal_name or {}).get(i, n), d, (lokal_extra or {}).get(i, b'')))
        versatz += len(inhalt[-1])
    verz = b''.join(verz)
    return b''.join(inhalt) + verz + ende(len(eintraege) if anzahl is None else anzahl, len(verz), versatz)


def unicode_pfad(echt, angezeigt):
    return struct.pack('<HHBI', 0x7075, 5 + len(angezeigt), 1, zlib.crc32(echt)) + angezeigt


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
    check('kleines Archiv: Prüfung beim Hochladen nimmt es an', pruefen(os.path.join(tmp, 'klein.zip')) == ['ok'])

    gross = [datei(i, b'%PDF-' + str(i).encode(), 250 * MB) for i in range(18)]
    z, z64, _ = export(tmp, [{'pfad': 'QM-System/Dokumentenliste.csv', 'inhalt': 'Nr;Titel\r\n'}] + gross, os.path.join(tmp, 'gross.zip'))
    infos = z.infolist()
    check('über 4 GB: Zip64, alle 19 Einträge lesbar, Versatz über 4 GB, Prüfsummen stimmen', z64 and len(infos) == 19 and max(i.header_offset for i in infos) > 0xFFFFFFFF
          and z.testzip() is None and z.read(infos[-1].filename)[:7] == b'%PDF-17', [i.header_offset for i in infos[-2:]])
    z.close()
    check('über 4 GB: unzip liest Namen mit Umlaut nach 4 GB lokal und zentral gleich', *unzip_test(os.path.join(tmp, 'gross.zip')))
    check('über 4 GB: Prüfung beim Hochladen nimmt es an (Versatz der lokalen Köpfe aus dem Zip64-Feld)', pruefen(os.path.join(tmp, 'gross.zip')) == ['ok'])
    os.remove(os.path.join(tmp, 'gross.zip'))

    for n, soll in ((65534, False), (65535, True)):
        z, z64, _ = export(tmp, [{'pfad': f'K/{i}.txt', 'inhalt': f'x{i}'} for i in range(n)], os.path.join(tmp, f'n{n}.zip'))
        check(f'{n} Einträge: {"mit" if soll else "ohne"} Zip64, alle lesbar', z64 == soll and len(z.infolist()) == n and z.read(f'K/{n - 1}.txt') == f'x{n - 1}'.encode())
        check(f'{n} Einträge: Prüfung beim Hochladen nimmt es an', pruefen(os.path.join(tmp, f'n{n}.zip')) == ['ok'])

    weg = datei(30, b'%PDF-weg', 1000)
    z, _, log = export(tmp, [datei(31, b'%PDF-vorher', 20 * MB), weg, datei(32, b'%PDF-nachher', 1000)], os.path.join(tmp, 'weg.zip'),
                       lambda: os.remove(os.path.join(tmp, 'dateien', 'qs', 'ab', weg['id'] + '.bin')))
    namen = z.namelist()
    check('Datei verschwindet während des Exports: fehlt im Archiv, Archiv gültig, im Protokoll vermerkt', namen == ['QM-System/1.4 Qualität/Datei 31.pdf', 'QM-System/1.4 Qualität/Datei 32.pdf']
          and z.testzip() is None and unzip_test(os.path.join(tmp, 'weg.zip'))[0] and 'Datei 30.pdf' in log, (namen, log))

    # ── Prüfung beim Hochladen: echte Archive anderer Packer werden angenommen ──
    def zipfile_bytes(eintraege, kommentar=b''):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            for n, d in eintraege:
                z.writestr(n, d)
            z.comment = kommentar
        return b.getvalue()

    py65535 = zipfile_bytes([(f'k/{i}.txt', 'x') for i in range(65535)])
    assert b'PK\x06\x07' not in py65535[-200:] and py65535[-12:-10] == b'\xff\xff', 'Python schreibt 65535 Einträge ohne Zip64'
    os.makedirs(os.path.join(tmp, 'zip'))
    os.chdir(os.path.join(tmp, 'zip'))
    with open('Anleitung.txt', 'w') as f:
        f.write('Prüfung')
    if shutil.which('zip'):
        subprocess.run(['zip', '-q', 'infozip.zip', 'Anleitung.txt'], check=True)
    class Strom(io.BytesIO):   # nicht spulbar wie eine Leitung: zipfile schreibt Größen und Prüfsumme in einen Data Descriptor (Bit 3)
        def seek(self, *a):
            raise io.UnsupportedOperation

    strom = Strom()
    with zipfile.ZipFile(strom, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('QM/Plan.txt', 'Prüfplan ' * 50); z.writestr('QM/Liste.csv', 'a;b')
    assert zipfile.ZipFile(io.BytesIO(strom.getvalue())).infolist()[0].flag_bits & 8, 'zipfile schreibt in den Strom mit Bit 3'
    bsdtar = zipfile_bytes([('QM/Plan.pdf', b'%PDF-1.4'), ('QM/Liste.csv', 'a;b')])
    gut = {
        'zipfile mit Unterordnern und Ordnereintrag': zipfile_bytes([('QM/1.4/Plan.pdf', b'%PDF-1.4'), ('QM/leer/', b''), ('QM/Liste.csv', 'a;b')]),
        'zipfile, 65535 Einträge ohne Zip64': py65535,
        'zipfile mit Kommentar, der die Ende-Signatur enthält': zipfile_bytes([('Ordner/Prüfplan.xlsx', bytes(1000))], b'Kommentar mit PK\x05\x06 darin'),
        'leeres Archiv': ende(0, 0, 0),
        'zipfile in einen Datenstrom (Data Descriptor)': strom.getvalue(),
        'wie bsdtar nach stdout: mit NUL-Bytes auf 10240er-Blöcke aufgefüllt': bsdtar + bytes(10240 - len(bsdtar) % 10240),
        'Ordner, dessen Name auf .js endet': zipfile_bytes([('Web/chart.js/', b''), ('Web/chart.js/Liesmich.txt', 'x')]),
    }
    if os.path.exists('infozip.zip'):
        gut['Info-ZIP zip (Zeit- und Unix-Zusatzfelder)'] = open('infozip.zip', 'rb').read()
    for i, (n, b) in enumerate(gut.items()):
        with open(f'gut{i}.zip', 'wb') as f:
            f.write(b)
    assert unzip_test('gut2.zip')[0], 'Kommentar mit Ende-Signatur: unzip liest das Archiv (Python nicht)'
    for (n, b), r in zip(gut.items(), pruefen(*[f'gut{i}.zip' for i in range(len(gut))])):
        check(f'Prüfung nimmt an: {n}', r == 'ok', r)

    # ── präparierte Archive: Python, Go, Java oder unzip zeigen Rechnung.exe, das Verzeichnis nicht → abgelehnt ──
    H, B = (b'Pruefplan.txt', b'harmlos'), (b'Rechnung.exe', b'MZ-nur-Test')
    echt = zentral(*B, 0)
    traeger = lokal(b'Tarnung.bin', zentral(b'Rechnung.txt', B[1], 0))   # Inhalt einer Datei = harmloses, falsches Verzeichnis
    d = lokal(*B) + traeger
    voll = archiv([H, B])
    zwei = zentral(*H, 0)
    z64_daneben = lokal(*H) + zwei + b'PK\x06\x06' + struct.pack('<QHHIIQQQQ', 44, 45, 45, 0, 0, 1, 1, len(zwei) + 10, 0)
    z64_daneben += b'PK\x06\x07' + struct.pack('<IQI', 0, len(lokal(*H)) + len(zwei), 1) + ende(1, len(zwei), len(lokal(*H)))
    geteilt = lokal(*H) + zentral(*H, 0) * 2
    # versteckte lokale Köpfe ohne Eintrag im Verzeichnis: 7-Zip entpackt sie ohne Warnung
    Z = (b'Zweite.txt', b'zwei')
    vorne = lokal(*B) + lokal(*H) + zentral(*H, len(lokal(*B)))
    vorne += ende(1, len(zentral(*H, 0)), len(lokal(*B) + lokal(*H)))
    zz = zentral(*H, 0) + zentral(*Z, len(lokal(*H) + lokal(*B)))
    luecke = lokal(*H) + lokal(*B) + lokal(*Z) + zz + ende(2, len(zz), len(lokal(*H) + lokal(*B) + lokal(*Z)))
    kleiner = bytearray(archiv([(H[0], H[1] + lokal(*B))]))   # Verzeichnis zählt Rechnung.exe zu den Daten, der lokale Kopf nicht
    kleiner[18:22] = struct.pack('<I', len(H[1]))
    # lokaler Kopf von Zweite.txt liegt im Zusatzfeld des ersten: so lassen sich Köpfe vielfach überlappend lesen (Rechenzeit)
    innen = lokal(*Z)
    aussen = lokal(*H, extra=struct.pack('<HH', 0x9999, len(innen)) + innen)
    zz = zentral(*H, 0) + zentral(*Z, 30 + len(H[0]) + 4)
    ueberlappend = aussen + zz + ende(2, len(zz), len(aussen))
    boese = {
        'a) NUL am Ende des Namens': (archiv([H, (b'Rechnung.exe\0', B[1])]), 'beschädigt'),
        'a) NUL vor .txt': (archiv([H, (b'Rechnung.exe\0.txt', B[1])]), 'beschädigt'),
        'b) Zahl der Einträge 0': (archiv([B], anzahl=0), 'beschädigt'),
        'c) Zahl 1 bei 2 Einträgen': (archiv([H, B], anzahl=1), 'beschädigt'),
        'c2) 65537 Einträge, Zahl 1 (65537 mod 65536)': (archiv([H] + [(b'k/%d.txt' % i, b'x') for i in range(65535)] + [B], anzahl=1), 'gesperrte Dateiart'),
        'd) Versatz zeigt auf ein falsches Verzeichnis im Inhalt': (d + echt + ende(1, len(echt), len(d) - len(zentral(b'Rechnung.txt', B[1], 0))), 'beschädigt'),
        'Unicode-Pfad 0x7075 im Verzeichnis': (archiv([(b'Rechnung.txt', B[1])], extra={0: unicode_pfad(b'Rechnung.txt', b'Rechnung.exe')}), 'gesperrte Dateiart'),
        'Unicode-Pfad 0x7075 im lokalen Kopf': (archiv([(b'Rechnung.txt', B[1])], lokal_extra={0: unicode_pfad(b'Rechnung.txt', b'Rechnung.exe')}), 'gesperrte Dateiart'),
        'abweichender Name im lokalen Kopf': (archiv([(b'Rechnung.txt', B[1])], lokal_name={0: b'Rechnung.exe'}), 'beschädigt'),
        'Doppelpunkt: Datenstrom von Rechnung.exe': (archiv([H, (b'Rechnung.exe:x', B[1])]), 'gesperrte Dateiart'),
        'zweites Ende im Kommentar': (voll[:-2] + struct.pack('<H', 22) + ende(0, 0, len(voll) - 22), 'beschädigt'),
        'Kommentarlänge reicht nicht bis zum Dateiende': (voll + b'x', 'beschädigt'),
        'nach dem Ende NUL-Bytes und dann weitere Bytes': (voll + bytes(16) + b'x', 'beschädigt'),
        'versteckter lokaler Kopf vor dem ersten Eintrag': (vorne, 'beschädigt'),
        'versteckter lokaler Kopf in einer Lücke zwischen zwei Einträgen': (luecke, 'beschädigt'),
        'lokaler Kopf nennt kleinere gepackte Größe als das Verzeichnis': (bytes(kleiner), 'beschädigt'),
        'lokale Köpfe überlappen': (ueberlappend, 'beschädigt'),
        'Rechnung.exe/. (Python und bsdtar entpacken die Datei Rechnung.exe)': (archiv([H, (b'Rechnung.exe/.', B[1])]), 'gesperrte Dateiart'),
        'Rechnung.exe\\ (Windows-Trennzeichen am Ende)': (archiv([H, (b'Rechnung.exe\\', B[1])]), 'gesperrte Dateiart'),
        'index.html/..': (archiv([H, (b'Ordner/index.html/..', B[1])]), 'gesperrte Dateiart'),
        'Zip64-Ende und klassisches Ende nennen verschiedene Längen': (z64_daneben, 'beschädigt'),
        'zwei Einträge teilen einen lokalen Kopf': (geteilt + ende(2, len(geteilt) - len(lokal(*H)), len(lokal(*H))), 'beschädigt'),
        'mehr als 16 Zusatzfelder': (archiv([H], extra={0: b'\x99\x99\0\0' * 17}), 'beschädigt'),
        'abgeschnittenes Zusatzfeld': (archiv([H], extra={0: struct.pack('<HH', 0x7075, 20) + b'Rechnung.exe'}), 'beschädigt'),
        'leere Datei': (b'', 'beschädigt'),
        'Großbuchstaben, Unterordner, Punkt und Leerzeichen am Ende': (archiv([(b'Ordner\\RECHNUNG.EXE . .', B[1])]), 'gesperrte Dateiart'),
    }
    for i, (n, (b, _)) in enumerate(boese.items()):
        with open(f'boese{i}.zip', 'wb') as f:
            f.write(b)
    for (n, (b, soll)), r in zip(boese.items(), pruefen(*[f'boese{i}.zip' for i in range(len(boese))])):
        check(f'Prüfung lehnt ab: {n}', soll in r, r)

    with open('sieben.zip', 'wb') as f:
        f.write(archiv([H] + [(b'Programm %d.exe' % i, B[1]) for i in range(7)]))
    with open('viele.zip', 'wb') as f:
        f.write(archiv([(b'%d' % i, b'') for i in range(200001)], anzahl=200001 % 65536))
    r = pruefen('sieben.zip', 'viele.zip')
    check('Meldung nennt 5 gesperrte Einträge und die Zahl der übrigen', r[0] == 'Das ZIP-Archiv enthält gesperrte Dateiarten: „Programm 0.exe“, „Programm 1.exe“, '
          '„Programm 2.exe“, „Programm 3.exe“, „Programm 4.exe“ und 2 weitere.', r[0])
    check('mehr als 200.000 Einträge → abgelehnt mit klarer Meldung', 'mehr als 200.000 Einträge' in r[1], r[1])
    os.chdir(REPO)

print('FEHLER: ' + ', '.join(fehler) if fehler else 'alle Prüfungen bestanden')
sys.exit(1 if fehler else 0)
