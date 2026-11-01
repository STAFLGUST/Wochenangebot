"""Werkzeug der Entwickler-Dokumentation (werkzeuge/doku.py): Kopfkommentare, Pflicht je Dateiart, Referenz.

    python3 tests/unit/test_doku.py

Prüft: erste Aussage des Kopfkommentars je Dateiart (PHP, JS, CSS, Python, Shell, HTML, Markdown), lange Kommentare,
fehlende Kommentare, welche Dateien einen Kopf brauchen, Maskierung in Tabellen, und dass die Referenz alle Aktionen,
Rechte, Dokumente und Module des Regelwerks enthält und stabil erzeugt wird; Funktionsübersicht: Funktionen, Parameter und
Kommentar je Sprache (PHP, JavaScript, Python), Abschnitte, Kopfkommentar und Leerzeile zählen nicht, lokale Hilfen und
Testfälle weggelassen, Abkürzungen kürzen nicht, Absatz „Testdaten:“, eine Datei je Modul, veraltete Datei wird gemeldet.
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
ok('fünf Referenzdateien und die Funktionsübersicht', sorted(k for k in ref if '/funktionen/' not in k) == sorted(f'docs/entwickler/referenz/{n}.md' for n in ('api', 'rechte', 'daten', 'module', 'dateien'))
   and 'docs/entwickler/referenz/funktionen/README.md' in ref and 'docs/entwickler/referenz/funktionen/plattform.md' in ref)
akt = rg.aktionen_tabelle(rw)
ok('API: jede Aktion des Registers', all(f'| `{a}` |' in ref['docs/entwickler/referenz/api.md'] for a in akt), len(akt))
ok('Rechte: jedes Recht aus PERMS und Modulzugang', all(f"`{p['key']}`" in ref['docs/entwickler/referenz/rechte.md'] for p in doku.perms_aus_code(REPO))
   and '`hr.zugang`' in ref['docs/entwickler/referenz/rechte.md'])
ok('Daten: jedes Dokument', all(f"`{x['name']}" in ref['docs/entwickler/referenz/daten.md'] for x in rw.daten.get('dokument', [])))
ok('Module: jedes Modul', all(f"(`{m['id']}`)" in ref['docs/entwickler/referenz/module.md'] for m in rw.modulliste))
ok('stabil: zweimal erzeugt = gleich', ref == doku.alle(rg.laden()))
ok('Dateikarte enthält den API-Einstieg mit Beschreibung', '| `index.php` | plattform | API-Einstieg' in ref['docs/entwickler/referenz/dateien.md'])

# Funktionsübersicht
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / 'a.php').write_text("""<?php
/* Kopf: diese Datei tut etwas. */
function kopf_folgt(): void {}

/* Kunden lesen bzw. Artikel zählen. Zweiter Satz. */
function lesen(array $q, ?string $nr = null, int &...$rest): array { return []; }
// Zeilenkommentar zur Funktion
function zeile(\\Foo $x,
               bool $y = true): int { return 1; }

/* ---------- Abschnitt Detail ---------- */
/* Kommentar mit Leerzeile davor */

function ohne(): void {}
if (true) {
    function eingerueckt(): void {}
}
""", encoding='utf-8')
    f = doku.funktionen(d / 'a.php')
    ok('PHP: Funktionen in Reihenfolge, Abschnitt dazwischen', [e[1] for e in f] == ['kopf_folgt', 'lesen', 'zeile', 'Abschnitt Detail', 'ohne', 'eingerueckt'], f)
    ok('PHP: Kopfkommentar der Datei gehört nicht zur ersten Funktion', f[0] == ('funktion', 'kopf_folgt', '', ''), f[0])
    ok('PHP: Parameter ohne Typen und Vorgaben, erster Satz, „bzw.“ kürzt nicht', f[1] == ('funktion', 'lesen', 'q, nr, ...rest', 'Kunden lesen bzw. Artikel zählen.'), f[1])
    ok('PHP: Zeilenkommentar, Parameter über zwei Zeilen', f[2] == ('funktion', 'zeile', 'x, y', 'Zeilenkommentar zur Funktion'), f[2])
    ok('PHP: Leerzeile trennt Kommentar und Funktion', f[4] == ('funktion', 'ohne', '', ''), f[4])
    (d / 'b.js').write_text("""/* Kopf der Seite. */
'use strict';
(() => {
  /* ---------- Laden ---------- */
  /* Daten holen und zeichnen */
  async function laden(nr, { still } = {}, liste = []) {
    function lokal() {}
  }
  function zeichne() {}
})();
""", encoding='utf-8')
    f = doku.funktionen(d / 'b.js')
    ok('JavaScript: async, Vorgaben und Zerlegung, lokale Hilfen weggelassen', f == [('abschnitt', 'Laden'), ('funktion', 'laden', 'nr, {…}, liste', 'Daten holen und zeichnen'),
                                                                                      ('funktion', 'zeichne', '', '')], f)
    (d / 'tests').mkdir()
    (d / 'tests' / 'c.py').write_text('''"""Prüft etwas.

Geprüft: viel.

Testdaten: Kunde 1 und Kunde 2,
Artikel 40100.

Weiter.
"""


class K:
    def methode(self, a: int = 1, *rest, **kw) -> None:
        """Methode mit Docstring. Mehr."""


def test_etwas():
    pass


def hilfe(x):
    """
    Docstring über
    mehrere Zeilen.
    """
''', encoding='utf-8')
    f = doku.funktionen(d / 'tests' / 'c.py')
    ok('Python: self weg, Docstring (auch mehrzeilig), Testfälle weggelassen', f == [('funktion', 'methode', 'a, *rest, **kw', 'Methode mit Docstring.'),
                                                                                  ('funktion', 'hilfe', 'x', 'Docstring über mehrere Zeilen.')], f)
    ok('Absatz „Testdaten:“ aus dem Kopfkommentar', doku.testdaten_absatz(d / 'tests' / 'c.py') == 'Testdaten: Kunde 1 und Kunde 2, Artikel 40100.',
       doku.testdaten_absatz(d / 'tests' / 'c.py'))
    (d / 'leer.js').write_text('/* Nur Daten. */\nconst x = 1;\n', encoding='utf-8')
    ok('Datei ohne Funktionen erscheint nicht', doku.funktionen(d / 'leer.js') == [])
ok('Kurztext: höchstens 160 Zeichen', len(doku._kurz('Wort ' * 100)) <= 160 and doku._kurz('Wort ' * 100).endswith('…'))
fu = {k: v for k, v in ref.items() if '/funktionen/' in k}
ok('Funktionsübersicht: eine Datei je Modul mit Funktionen, alle in der Übersicht verlinkt', all(f'({Path(k).name})' in fu['docs/entwickler/referenz/funktionen/README.md']
   for k in fu if not k.endswith('README.md')) and len(fu) >= 10)
ok('Funktionsübersicht: Funktion mit Kommentar und Testdaten-Absatz', '- `umsatz_abc(zeilen, rang)` – ABC-Klasse je Zeile' in fu['docs/entwickler/referenz/funktionen/controlling.md']
   and '> Testdaten: Vertreter V1 Vera Vertrieb' in fu['docs/entwickler/referenz/funktionen/controlling.md'])
ok('Funktionsübersicht ohne Zeilennummern', not any(':' + str(n) + ')' in v for v in fu.values() for n in (10, 100)))
alt = REPO / 'docs/entwickler/referenz/funktionen/veraltet-test.md'
try:
    alt.write_text('# alt\n', encoding='utf-8')
    import io, contextlib  # noqa: E401,E402
    with contextlib.redirect_stdout(io.StringIO()) as aus:
        rc = doku.main(['pruefen'])
    ok('pruefen meldet eine veraltete Datei der Funktionsübersicht', rc == 1 and 'veraltet-test.md gehört zu keinem Modul' in aus.getvalue(), aus.getvalue()[-300:])
finally:
    alt.unlink(missing_ok=True)

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
