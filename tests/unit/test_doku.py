"""Werkzeug der Entwickler-Dokumentation (werkzeuge/doku.py): Kopfkommentare, Pflicht je Dateiart, Referenz.

    python3 tests/unit/test_doku.py

Prüft: erste Aussage des Kopfkommentars je Dateiart (PHP, JS, CSS, Python, Shell, HTML, Markdown), lange Kommentare,
fehlende Kommentare, welche Dateien einen Kopf brauchen, Maskierung in Tabellen, und dass die Referenz alle Aktionen,
Rechte, Dokumente und Module des Regelwerks enthält und stabil erzeugt wird.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'werkzeuge'))
import doku  # noqa: E402
import regeln as rg  # noqa: E402

PASS = FAIL = 0


def ok(name, cond, info=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print('PASS ' + name)
    else:
        FAIL += 1; print('FAIL ' + name + ('  ' + repr(info) if info else ''))


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    faelle = {
        'a.php': ("<?php\ndeclare(strict_types=1);\n/* Kunden: Stammdaten lesen und schreiben. Weitere Sätze folgen hier. */\n", 'Kunden: Stammdaten lesen und schreiben.'),
        'b.js': ("/* ===\n   Eingabebereich – Verwaltung\n   Mehr Text. */\n(function(){})();\n", 'Eingabebereich – Verwaltung Mehr Text.'),
        'c.css': ("/* Gestaltung der Rechtsseiten. Zweiter Satz. */\nbody{}\n", 'Gestaltung der Rechtsseiten.'),
        'd.py': ('#!/usr/bin/env python3\n"""Werkzeug: prüft etwas Wichtiges. Details."""\n', 'Werkzeug: prüft etwas Wichtiges.'),
        'e.sh': ("#!/usr/bin/env bash\n# Sichert die Daten des Servers täglich.\n# zweite Zeile\nset -e\n", 'Sichert die Daten des Servers täglich. zweite Zeile'),
        'f.html': ("<!doctype html><html><head><title>Kontakt</title></head></html>", 'Seite „Kontakt“'),
        'g.md': ("# Überschrift\n\nText", 'Überschrift'),
        'h.js': ("const x = 1;\n", ''),
        'i.php': ("<?php\n" + "/*\n * " + "Lang " * 2000 + "\n */\n", None),
    }
    for name, (inhalt, erwartet) in faelle.items():
        (d / name).write_text(inhalt, encoding='utf-8')
        k = doku.kopfkommentar(d / name)
        if erwartet is None:
            ok(f'{name}: langer Kommentar gekürzt (≤ 220 Zeichen)', 0 < len(k) <= 220, k)
        else:
            ok(f'{name}: Kopfkommentar erkannt', k == erwartet, k)

ok('Code-Datei braucht Kopf', doku.braucht_kopf('app/api/lib/neu.php') and doku.braucht_kopf('tests/e2e/test_x.py'))
ok('fremde Bibliotheken, Testdaten und erzeugte Listen ausgenommen', not doku.braucht_kopf('app/assets/vendor/qrcode.js')
   and not doku.braucht_kopf('tests/fixtures/data-seed/index.php') and not doku.braucht_kopf('app/api/lib/aktionen-liste.php'))
ok('Bilder und Daten brauchen keinen Kopf', not doku.braucht_kopf('app/assets/karte.json') and not doku.braucht_kopf('app/assets/logo-standard-fleisch.png'))
ok('Tabellenzellen maskiert', doku.md('a | b\nc') == 'a \\| b c')

rw = rg.laden()
ref = doku.alle(rw)
ok('fünf Referenzdateien', sorted(ref) == sorted(f'docs/entwickler/referenz/{n}.md' for n in ('api', 'rechte', 'daten', 'module', 'dateien')))
akt = rg.aktionen_tabelle(rw)
ok('API: jede Aktion des Registers', all(f'| `{a}` |' in ref['docs/entwickler/referenz/api.md'] for a in akt), len(akt))
ok('Rechte: jedes Recht aus PERMS und Modulzugang', all(f"`{p['key']}`" in ref['docs/entwickler/referenz/rechte.md'] for p in doku.perms_aus_code(REPO))
   and '`hr.zugang`' in ref['docs/entwickler/referenz/rechte.md'])
ok('Daten: jedes Dokument', all(f"`{x['name']}" in ref['docs/entwickler/referenz/daten.md'] for x in rw.daten.get('dokument', [])))
ok('Module: jedes Modul', all(f"(`{m['id']}`)" in ref['docs/entwickler/referenz/module.md'] for m in rw.modulliste))
ok('stabil: zweimal erzeugt = gleich', ref == doku.alle(rg.laden()))
ok('Dateikarte enthält den API-Einstieg mit Beschreibung', '| `index.php` | plattform | API-Einstieg' in ref['docs/entwickler/referenz/dateien.md'])

# Während einer Zusammenführung mit Konflikt listet git jede Stufe einer Datei einzeln – die Dateiliste bleibt eindeutig
import subprocess  # noqa: E402
with tempfile.TemporaryDirectory() as g:
    g = Path(g)
    def git(*a):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *a], cwd=g, check=False, capture_output=True)
    git('init', '-q', '-b', 'main'); (g / 'a.txt').write_text('1\n'); git('add', '.'); git('commit', '-qm', 'a')
    git('checkout', '-qb', 'zweig'); (g / 'a.txt').write_text('2\n'); git('commit', '-qam', 'b')
    git('checkout', '-q', 'main'); (g / 'a.txt').write_text('3\n'); git('commit', '-qam', 'c'); git('merge', 'zweig')
    ok('Dateiliste bei Konflikt eindeutig', rg.dateien(g) == ['a.txt'], rg.dateien(g))

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(1 if FAIL else 0)
