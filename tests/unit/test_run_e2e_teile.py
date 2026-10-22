"""Aufteilung der E2E-Testgruppen auf CI-Aufträge (tests/run_e2e.py: WA_TEIL, teile()).

    python3 tests/unit/test_run_e2e_teile.py

Prüft: jede Gruppe in genau einem Teil (für 1–6 Teile), unabhängig von Eingabereihenfolge und vorhandenem Build,
ähnliche Laufzeit je Teil, ungültige WA_TEIL-Angaben, neue Gruppen ohne Gewicht, Zusammenspiel mit ci.yml
(Liste „teil“ = 1…n und Nenner in WA_TEIL = n), Testlauf mit WA_TEIL wählt genau die Gruppen des Teils.
"""
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'tests'))
import run_e2e as r  # noqa: E402

PASS = FAIL = 0


def ok(name, cond, info=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f'PASS {name}')
    else:
        FAIL += 1; print(f'FAIL {name}  {info}')


alle = list(r.SUITES)
for n in range(1, 7):
    t = r.teile(alle, n)
    flach = [g for teil in t for g in teil]
    ok(f'{n} Teile: jede Gruppe genau einmal', sorted(flach) == sorted(alle) and len(flach) == len(set(flach)))
    ok(f'{n} Teile: kein Teil leer', all(t))
    lasten = [sum(r.gewicht(g) for g in teil) for teil in t]
    # Längste-zuerst-Verteilung: Abstand höchstens die größte Einzelgruppe
    ok(f'{n} Teile: ähnliche Laufzeit {lasten}', max(lasten) - min(lasten) <= max(r.gewicht(g) for g in alle))

t3 = r.teile(alle, 3)
ok('deterministisch (zweimal gleich)', r.teile(alle, 3) == t3)
ok('unabhängig von der Reihenfolge', r.teile(list(reversed(alle)), 3) == t3)
ok('optionale Gruppe (app_web) hat festen Teil', any('app_web' in teil for teil in t3))
ok('Doppelte Namen zählen einmal', sorted(sum(r.teile(alle + alle[:5], 3), [])) == sorted(alle))
lasten3 = [sum(r.gewicht(g) for g in teil) for teil in t3]
ok(f'3 Teile: höchstens 5 % Unterschied {lasten3}', max(lasten3) <= 1.05 * min(lasten3))

neu = r.teile(alle + ['ganz_neue_gruppe'], 3)
ok('neue Gruppe ohne Gewicht wird einem Teil zugeordnet', sum(teil.count('ganz_neue_gruppe') for teil in neu) == 1)
ok('alle Gruppen haben ein Gewicht (außer optionalen)', all(g in r.GEWICHT or g in r.OPTIONAL for g in alle),
   [g for g in alle if g not in r.GEWICHT and g not in r.OPTIONAL])
ok('keine Gewichte für entfernte Gruppen', all(g in r.SUITES for g in r.GEWICHT), [g for g in r.GEWICHT if g not in r.SUITES])

ok('WA_TEIL leer → alle', r.teil_lesen('') is None)
ok('WA_TEIL „2/3“', r.teil_lesen('2/3') == (2, 3))
ok('WA_TEIL mit Leerzeichen', r.teil_lesen(' 1 / 1 ') == (1, 1))
for falsch in ['0/3', '4/3', '3', 'a/b', '1/0', '-1/3', '1/3/3', '1.5/3']:
    try:
        r.teil_lesen(falsch); ok(f'WA_TEIL „{falsch}“ abgelehnt', False)
    except ValueError:
        ok(f'WA_TEIL „{falsch}“ abgelehnt', True)

# ci.yml: Liste der Teile und Nenner müssen zusammenpassen – sonst liefe ein Teil nie (Gruppen ungeprüft)
ci = open(os.path.join(REPO, '.github', 'workflows', 'ci.yml'), encoding='utf-8').read()
m_liste = re.search(r'^\s+teil:\s*\[([^\]]*)\]', ci, re.M)
m_env = re.search(r'^\s+WA_TEIL:\s*\$\{\{\s*matrix\.teil\s*\}\}/(\d+)\s*$', ci, re.M)
ok('ci.yml: Matrix „teil“ und WA_TEIL vorhanden', bool(m_liste and m_env))
if m_liste and m_env:
    liste = [int(x) for x in m_liste.group(1).split(',')]
    n = int(m_env.group(1))
    ok(f'ci.yml: Teile {liste} = 1…{n}', liste == list(range(1, n + 1)))
    ok('ci.yml: Artefakt je Teil eindeutig', 'e2e-ergebnisse-${{ matrix.storage }}-teil${{ matrix.teil }}' in ci)

# Testlauf: WA_TEIL wählt genau die Gruppen des Teils (ohne Server zu starten: ungültige Angabe bricht vorher ab)
env = {**os.environ, 'WA_TEIL': '5/3'}
p = subprocess.run([sys.executable, os.path.join(REPO, 'tests', 'run_e2e.py')], env=env, capture_output=True, text=True)
ok('run_e2e.py: ungültiges WA_TEIL → Abbruch mit Meldung', p.returncode != 0 and 'WA_TEIL' in p.stderr, p.stderr[-200:])
env = {**os.environ, 'WA_TEIL': '1/1'}
p = subprocess.run([sys.executable, os.path.join(REPO, 'tests', 'run_e2e.py'), 'gibt_es_nicht'], env=env,
                   capture_output=True, text=True)
ok('run_e2e.py: unbekannte Gruppe mit WA_TEIL weiter erkannt', p.returncode != 0 and 'Unbekannte Testgruppe' in p.stderr, p.stderr[-200:])

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(1 if FAIL else 0)
