"""Nachweis „schon im Pull Request vollständig geprüft“ (.github/scripts/ci_nachweis.py) mit nachgebauter GitHub-API.

    python3 tests/unit/test_ci_nachweis.py

Prüft: Merge-, Squash- und Rebase-Commit mit passendem PR-Lauf → übernehmen; main seither weiter (anderer Tree),
Fork, anderer Workflow, Push-Lauf, fehlgeschlagener/abgebrochener Lauf, fehlender oder fremder Nachweis-Auftrag,
fehlgeschlagener oder übersprungener Pflichtauftrag, ausgecheckter Stand ≠ Commit, API-Fehler, ungültige Eingaben →
volle CI; Ausgaben für die CI (GITHUB_OUTPUT), Trockenlauf ohne Ausgaben; Auftragsnamen passen zu ci.yml.
"""
import copy
import importlib.util
import os
import re
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ['CI_NACHWEIS_PAUSE'] = '0'
spec = importlib.util.spec_from_file_location('ci_nachweis', os.path.join(REPO, '.github', 'scripts', 'ci_nachweis.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)

PASS = FAIL = 0


def ok(name, cond, info=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f'PASS {name}')
    else:
        FAIL += 1; print(f'FAIL {name}  {info}')


R = 'o/r'
MAIN, ALT, KOPF, TREE, TREE2 = ('a' * 40), ('b' * 40), ('c' * 40), ('d' * 40), ('e' * 40)
FORK = 'f' * 40


def jobs(tree=TREE, **abweichung):
    namen = n.PFLICHT + ['Ende-zu-Ende-Tests (files, Teil 1/3)', 'Ende-zu-Ende-Tests (sqlite, Teil 3/3)', n.nachweis_name(tree)]
    liste = [{'name': x, 'status': 'completed', 'conclusion': 'success'} for x in namen]
    liste += [{'name': 'Release zur Freigabe vorlegen', 'status': 'completed', 'conclusion': 'skipped'}]
    for name, ergebnis in abweichung.items():
        for j in liste:
            if j['name'] == name.replace('_', ' '):
                j['conclusion'] = ergebnis
    return {'jobs': liste}


def lauf(id_, kopf=KOPF, **x):
    r = {'id': id_, 'event': 'pull_request', 'path': '.github/workflows/ci.yml', 'status': 'completed', 'conclusion': 'success',
         'head_sha': kopf, 'repository': {'full_name': R}, 'head_repository': {'full_name': R},
         'html_url': f'https://github.com/{R}/actions/runs/{id_}'}
    r.update(x)
    return r


def welt(eltern=(ALT, KOPF), tree=TREE, pulls=None, laeufe=None, auftraege=None):
    w = {
        f'repos/{R}/commits/{MAIN}': {'sha': MAIN, 'commit': {'tree': {'sha': tree}}, 'parents': [{'sha': e} for e in eltern]},
        f'repos/{R}/commits/{MAIN}/pulls': pulls if pulls is not None else [],
    }
    laeufe = {**{e: [] for e in eltern}, **(laeufe if laeufe is not None else {KOPF: [lauf(7)]})}   # API: leere Liste
    for kopf, liste in laeufe.items():
        w[f'repos/{R}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={kopf}&status=success&per_page=30'] = {'workflow_runs': liste}
    for id_, j in (auftraege if auftraege is not None else {7: jobs()}).items():
        w[f'repos/{R}/actions/runs/{id_}/jobs?filter=latest&per_page=100'] = j
    return w


def api_aus(w):
    def api(pfad):
        if pfad not in w:
            raise RuntimeError(f'404 {pfad}')
        v = w[pfad]
        if isinstance(v, Exception):
            raise v
        return copy.deepcopy(v)
    return api


def suche(w, tree=TREE, sha=MAIN):
    return n.suchen(api_aus(w), R, sha, tree, log=lambda *_: None)


l, g = suche(welt())
ok('Merge-Commit: PR-Lauf mit gleichem Tree → übernehmen', l is not None and l['id'] == 7, g)

pr = [{'merged_at': '2026-10-22T10:00:00Z', 'merge_commit_sha': MAIN, 'base': {'repo': {'full_name': R}},
       'head': {'sha': KOPF, 'repo': {'full_name': R}}}]
l, g = suche(welt(eltern=(ALT,), pulls=pr))
ok('Squash/Rebase: Kopf aus zugehörigem PR → übernehmen', l is not None, g)
pr_fork = copy.deepcopy(pr); pr_fork[0]['head']['repo']['full_name'] = 'x/r'
l, g = suche(welt(eltern=(ALT,), pulls=pr_fork))
ok('Squash aus Fork-PR → volle CI', l is None, g)
pr_anders = copy.deepcopy(pr); pr_anders[0]['merge_commit_sha'] = ALT
l, g = suche(welt(eltern=(ALT,), pulls=pr_anders))
ok('PR mit anderem Merge-Commit zählt nicht → volle CI', l is None, g)
w = welt(); w[f'repos/{R}/commits/{MAIN}/pulls'] = RuntimeError('403')
l, g = suche(w)
ok('PR-Liste nicht lesbar: Eltern-Commits reichen weiter', l is not None, g)

l, g = suche(welt(tree=TREE2), tree=TREE2)
ok('main seither weiter (anderer Tree als im PR-Lauf) → volle CI', l is None and 'kein erfolgreicher' in g, g)
l, g = suche(welt(), tree=TREE2)
ok('ausgecheckter Stand ≠ Tree des Commits → volle CI', l is None and 'passt nicht' in g, g)
l, g = suche(welt(laeufe={KOPF: []}))
ok('kein PR-Lauf → volle CI', l is None, g)
l, g = suche(welt(eltern=(ALT, FORK)))
ok('PR-Lauf nur für anderen Kopf → volle CI', l is None, g)

for name, x in [('Fork', {'head_repository': {'full_name': 'x/r'}}), ('anderes Repository', {'repository': {'full_name': 'x/r'}}),
                ('Push-Lauf', {'event': 'push'}), ('anderer Workflow', {'path': '.github/workflows/ci-nachweis.yml'}),
                ('fehlgeschlagen', {'conclusion': 'failure'}), ('abgebrochen', {'conclusion': 'cancelled'}),
                ('läuft noch', {'status': 'in_progress', 'conclusion': None}), ('anderer Kopf im Lauf', {'head_sha': ALT}),
                ('ohne head_repository', {'head_repository': None})]:
    l, g = suche(welt(laeufe={KOPF: [lauf(7, **x)]}))
    ok(f'Lauf {name} → volle CI', l is None, g)

for name, j in [('Nachweis-Auftrag fehlt (Lauf vor dieser Änderung)', {'jobs': [x for x in jobs()['jobs'] if not x['name'].startswith('Vollständig')]}),
                ('Nachweis für anderen Tree', jobs(tree=TREE2)),
                ('E2E-Teil fehlgeschlagen', jobs(**{'Ende-zu-Ende-Tests (files, Teil 1/3)': 'failure'})),
                ('Keycloak übersprungen', jobs(**{'Anmeldung über Keycloak (nur CI)': 'skipped'})),
                ('Statische Prüfungen abgebrochen', jobs(**{'Statische Prüfungen': 'cancelled'})),
                ('Nachweis-Auftrag übersprungen', jobs(**{n.nachweis_name(TREE): 'skipped'})),
                ('Pflichtauftrag fehlt', {'jobs': [x for x in jobs()['jobs'] if x['name'] != 'Sicherheitsprüfungen']}),
                ('Release-Vorlage fehlgeschlagen', jobs(**{'Release zur Freigabe vorlegen': 'failure'})),
                ('keine Aufträge', {'jobs': []})]:
    l, g = suche(welt(auftraege={7: j}))
    ok(f'{name} → volle CI', l is None, g)

zaehler = {'n': 0}
w = welt()
pfad = f'repos/{R}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={KOPF}&status=success&per_page=30'
echt = w.pop(pfad)
def wackelig(p, _api=api_aus(w)):
    if p == pfad:
        zaehler['n'] += 1
        return {'workflow_runs': []} if zaehler['n'] < 3 else copy.deepcopy(echt)
    return _api(p)
l, g = n.suchen(wackelig, R, MAIN, TREE, log=lambda *_: None)
ok('Läufe-Suche zweimal leer, dann gefunden → übernehmen', l is not None and zaehler['n'] == 3, g)
zaehler['n'] = -10
l, g = n.suchen(wackelig, R, MAIN, TREE, log=lambda *_: None)
ok('Läufe-Suche bleibt leer → volle CI nach 3 Versuchen', l is None and zaehler['n'] == -7, (g, zaehler))
reihenfolge = []
def merken(p, _api=api_aus(welt())):
    if '/runs?' in p:
        reihenfolge.append(p.split('head_sha=')[1][:40])
    return _api(p)
n.suchen(merken, R, MAIN, TREE, log=lambda *_: None)
ok('zuerst der zusammengeführte Zweig (2. Eltern-Commit) befragt', reihenfolge[:1] == [KOPF], reihenfolge)
l, g = suche(welt(laeufe={KOPF: [lauf(7), lauf(9)]}, auftraege={7: jobs(), 9: jobs(**{'Sicherheitsprüfungen': 'failure'})}))
ok('mehrere Läufe: gültiger älterer Lauf genügt', l is not None and l['id'] == 7, g)
w = welt(); w[f'repos/{R}/commits/{MAIN}'] = RuntimeError('API nicht erreichbar')
l, g = suche(w)
ok('API-Fehler → volle CI (ohne Ausnahme)', l is None and 'nicht prüfbar' in g, g)
w = welt(); w[f'repos/{R}/actions/runs/7/jobs?filter=latest&per_page=100'] = {'unerwartet': 1}
l, g = suche(w)
ok('unerwartete Antwort → volle CI', l is None, g)
for name, sha, tree in [('kurzer Commit', 'abc', TREE), ('Commit mit Großbuchstaben', 'A' * 40, TREE), ('Tree ungültig', MAIN, 'x;rm')]:
    l, g = suche(welt(), tree=tree, sha=sha)
    ok(f'{name} → volle CI', l is None, g)
l, g = n.suchen(api_aus(welt()), R, MAIN, None, log=lambda *_: None)
ok('ohne --tree (Trockenlauf): Tree aus der API', l is not None, g)

# Ausgaben für die CI
with tempfile.TemporaryDirectory() as d:
    out, summ = os.path.join(d, 'out'), os.path.join(d, 'summary')
    os.environ.update(GITHUB_REPOSITORY=R, GITHUB_OUTPUT=out, GITHUB_STEP_SUMMARY=summ)
    n.main(['--sha', MAIN, '--tree', TREE], api=api_aus(welt()))
    t = open(out, encoding='utf-8').read()
    ok('Ausgabe: uebernommen=true und Lauf', 'uebernommen=true\n' in t and 'lauf=https://github.com/o/r/actions/runs/7' in t, t)
    os.remove(out)
    n.main(['--sha', MAIN, '--tree', TREE2], api=api_aus(welt()))
    t = open(out, encoding='utf-8').read()
    ok('Ausgabe: uebernommen=false mit Grund', 'uebernommen=false\n' in t and 'grund=' in t, t)
    os.remove(out)
    n.main(['--sha', MAIN, '--trockenlauf'], api=api_aus(welt()))
    ok('Trockenlauf: keine Ausgaben für die CI', not os.path.exists(out))
    ok('Trockenlauf: Bericht in der Zusammenfassung', 'Trockenlauf' in open(summ, encoding='utf-8').read())
    for k in ('GITHUB_OUTPUT', 'GITHUB_STEP_SUMMARY'):
        del os.environ[k]

# Namen müssen zu ci.yml passen (sonst fände der Nachweis nie etwas oder prüfte zu wenig)
ci = open(os.path.join(REPO, '.github', 'workflows', 'ci.yml'), encoding='utf-8').read()
namen = re.findall(r'^    name: (.+)$', ci, re.M)
for p in n.PFLICHT + sorted(n.ERLAUBT_UEBERSPRUNGEN):
    ok(f'ci.yml hat Auftrag „{p}“', p in namen)
ok('ci.yml: Nachweis-Auftrag mit Tree im Namen', any(x.startswith(n.NACHWEIS_PREFIX) and 'needs.nachweis.outputs.tree' in x for x in namen))
ok('ci.yml: jeder Auftrag ist Pflicht, Nachweis oder erlaubt übersprungen',
   all(x in n.PFLICHT or x in n.ERLAUBT_UEBERSPRUNGEN or x.startswith(n.NACHWEIS_PREFIX) or x.startswith('Ende-zu-Ende-Tests (') for x in namen),
   [x for x in namen if x not in n.PFLICHT and x not in n.ERLAUBT_UEBERSPRUNGEN])
rel = open(os.path.join(REPO, '.github', 'scripts', 'release-pruefen.sh'), encoding='utf-8').read()
ok('release-pruefen.sh verlangt dieselben Nachweis-Namen', n.NACHWEIS_PREFIX in rel and 'Prüfung aus Pull Request übernommen' in rel)

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(1 if FAIL else 0)
