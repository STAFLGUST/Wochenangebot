"""Gemerktes Lesen der Speicherschicht in beiden Speicherarten: tests/unit/speicher_gemerkt.php einmal mit Dateien und einmal
mit SQLite (leerer Datenordner, mit deploy/datenbank.py migrate --offline umgestellt). Aufruf: python3 tests/unit/test_speicher_gemerkt.py"""
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
fehler = 0
for art in ('dateien', 'sqlite'):
    with tempfile.TemporaryDirectory() as d:
        if art == 'sqlite':
            subprocess.run([sys.executable, os.path.join(REPO, 'deploy', 'datenbank.py'), 'migrate', d, '--offline'], check=True, capture_output=True)
        p = subprocess.run(['php', os.path.join(REPO, 'tests', 'unit', 'speicher_gemerkt.php')], env={**os.environ, 'DATA_DIR': d},
                           capture_output=True, text=True, timeout=120)
        print(f'--- {art}\n' + p.stdout + p.stderr, end='')
        if p.returncode != 0 or 'FAIL' in p.stdout + p.stderr or f'Speicherart: {"sqlite" if art == "sqlite" else "files"}' not in p.stdout:
            fehler += 1
print('Gesamt:', 'OK' if not fehler else f'{fehler} Speicherart(en) fehlgeschlagen')
sys.exit(1 if fehler else 0)
