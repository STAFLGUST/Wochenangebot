"""Gemeinsame Pfade für die Ende-zu-Ende-Tests (gesetzt vom Testlauf tests/run_e2e.py)."""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FIX = os.path.join(REPO, 'tests', 'fixtures')
SH = os.environ.get('WA_SHOTS') or os.path.join(REPO, 'tests', '.ergebnisse')
os.makedirs(SH, exist_ok=True)
WORK = os.environ.get('WA_WORK') or os.path.join(REPO, 'tests', '.arbeit')
os.makedirs(WORK, exist_ok=True)
XL44 = os.path.join(FIX, 'angebote', 'Wochenangebot KW 44 2026.xlsx')
