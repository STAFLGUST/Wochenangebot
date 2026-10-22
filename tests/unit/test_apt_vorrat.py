"""Paketvorrat der CI (.github/scripts/apt_vorrat.py) mit nachgebautem apt-cache.

    python3 tests/unit/test_apt_vorrat.py

Prüft: nur Pakete mit passender SHA-256 aus der (signierten) Paketliste werden übernommen; veränderte, veraltete,
unbekannte oder falsch benannte Dateien werden verworfen (apt lädt sie dann selbst); Epoche im Dateinamen (%3a);
fehlendes apt-cache bricht nichts ab; Sammeln kopiert nur .deb-Dateien.
"""
import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SKRIPT = os.path.join(REPO, '.github', 'scripts', 'apt_vorrat.py')
spec = importlib.util.spec_from_file_location('apt_vorrat', SKRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

PASS = FAIL = 0


def ok(name, cond, info=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f'PASS {name}')
    else:
        FAIL += 1; print(f'FAIL {name}  {info}')


ok('Dateiname mit Epoche', v.dateiname_lesen('libnss3_2%3a3.98-1ubuntu0.3_amd64.deb') == ('libnss3', '2:3.98-1ubuntu0.3', 'amd64'))
ok('Dateiname „all“', v.dateiname_lesen('fonts-x_1.0-1_all.deb') == ('fonts-x', '1.0-1', 'all'))
for falsch in ['x.deb', 'a_b.deb', 'a_b_c_d.deb', 'a_b_c.txt', '../a_b_c.deb', '_1_all.deb']:
    ok(f'Dateiname „{falsch}“ abgelehnt', v.dateiname_lesen(falsch) is None)

with tempfile.TemporaryDirectory() as d:
    vorrat, archiv, bin_ = (os.path.join(d, x) for x in ('vorrat', 'archiv', 'bin'))
    for x in (vorrat, archiv, bin_):
        os.makedirs(x)
    inhalt = {'gut_1.0_all.deb': b'gutes paket', 'libx_2%3a1.5_amd64.deb': b'epoche', 'veraendert_1.0_all.deb': b'manipuliert',
              'alt_0.9_all.deb': b'alte version', 'fremd_1.0_all.deb': b'nicht in der liste', 'kaputt.deb': b'x',
              'falsche-arch_1.0_amd64.deb': b'arch'}
    for name, daten in inhalt.items():
        with open(os.path.join(vorrat, name), 'wb') as f:
            f.write(daten)
    h = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731
    liste = (f'Package: gut\nVersion: 1.0\nArchitecture: all\nSHA256: {h(b"gutes paket")}\n\n'
             f'Package: libx\nVersion: 2:1.5\nArchitecture: amd64\nSHA256: {h(b"epoche").upper()}\n\n'
             f'Package: veraendert\nVersion: 1.0\nArchitecture: all\nSHA256: {h(b"original")}\n\n'
             f'Package: falsche-arch\nVersion: 1.0\nArchitecture: i386\nSHA256: {h(b"arch")}\n\n'
             'Package: ohne-pruefsumme\nVersion: 1\nArchitecture: all\n')
    with open(os.path.join(d, 'liste.txt'), 'w') as f:
        f.write(liste)
    stub = os.path.join(bin_, 'apt-cache')
    with open(stub, 'w') as f:   # wie apt-cache: unbekannte Versionen → Fehler, gefundene trotzdem ausgeben
        f.write(f'#!/bin/sh\necho "$@" > {d}/aufruf\ncat {d}/liste.txt\necho "E: Version 0.9 nicht gefunden" >&2\nexit 100\n')
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
    v.ARCHIV, v.APT_CACHE = archiv, stub
    n, verworfen = v.einsetzen(vorrat)
    ok('nur Pakete mit passender Prüfsumme übernommen', sorted(os.listdir(archiv)) == ['gut_1.0_all.deb', 'libx_2%3a1.5_amd64.deb'], os.listdir(archiv))
    ok('verändertes Paket verworfen', 'veraendert_1.0_all.deb' in verworfen)
    ok('veraltete Version verworfen', 'alt_0.9_all.deb' in verworfen)
    ok('unbekanntes Paket verworfen', 'fremd_1.0_all.deb' in verworfen)
    ok('falsche Architektur verworfen', 'falsche-arch_1.0_amd64.deb' in verworfen)
    ok('unlesbarer Name verworfen', 'kaputt.deb' in verworfen)
    ok('Inhalt unverändert kopiert', open(os.path.join(archiv, 'gut_1.0_all.deb'), 'rb').read() == b'gutes paket')
    ok('apt-cache mit Paket=Version befragt', 'libx=2:1.5' in open(os.path.join(d, 'aufruf')).read())

    for x in os.listdir(archiv):
        os.remove(os.path.join(archiv, x))
    v.APT_CACHE = os.path.join(bin_, 'gibt-es-nicht')
    r = v.main(['x', 'einsetzen', vorrat])
    ok('apt-cache fehlt → nichts übernommen, kein Abbruch', r == 0 and os.listdir(archiv) == [])
    ok('leerer/fehlender Vorrat → kein Abbruch', v.main(['x', 'einsetzen', os.path.join(d, 'fehlt')]) == 0)
    ok('falscher Aufruf → Fehlercode 2', v.main(['x', 'loeschen', vorrat]) == 2)

    with open(os.path.join(archiv, 'a_1_all.deb'), 'wb') as f:
        f.write(b'a')
    with open(os.path.join(archiv, 'lock'), 'wb') as f:
        f.write(b'')
    os.makedirs(os.path.join(archiv, 'partial'))
    ziel = os.path.join(d, 'gesammelt')
    v.sammeln(ziel)
    ok('Sammeln: nur .deb-Dateien', os.listdir(ziel) == ['a_1_all.deb'], os.listdir(ziel))

    # Aufruf wie in der CI (python3 -I, eigener Prozess)
    p = subprocess.run([sys.executable, '-I', SKRIPT, 'einsetzen', vorrat], capture_output=True, text=True,
                       env={**os.environ, 'APT_ARCHIV': archiv, 'APT_CACHE': stub})
    ok('Aufruf als Skript', p.returncode == 0 and '2 Pakete geprüft übernommen' in p.stdout, p.stdout + p.stderr)

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(1 if FAIL else 0)
