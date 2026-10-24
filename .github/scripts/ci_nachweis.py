#!/usr/bin/env python3
"""Nachweis „schon im Pull Request vollständig geprüft“ für einen Commit auf main (ci.yml, Auftrag „nachweis“).

Ein CI-Lauf eines Pull Requests prüft den Merge-Stand (refs/pull/N/merge) und hält am Ende im Namen des Auftrags
„Vollständig geprüft (Stand <tree>)“ fest, welchen Inhalt (Git-Tree) er geprüft hat – nur wenn alle Aufträge grün
waren. Nach dem Merge sucht dieses Skript einen solchen Lauf mit GENAU dem Tree des neuen main-Commits. Gefunden →
die schweren Aufträge auf main werden übersprungen, der Release wird sofort vorgelegt. Sonst volle CI wie bisher.

Bedingungen für einen gültigen Nachweis (alle müssen erfüllt sein, sonst volle CI):
  * Tree des Commits (laut API) = Tree des ausgecheckten Stands (--tree)
  * Lauf des Workflows ci.yml in diesem Repository, Ereignis pull_request, abgeschlossen, Ergebnis success
  * Pull Request aus diesem Repository (kein Fork), Kopf-Commit = Eltern-Commit des main-Commits oder Kopf des
    Pull Requests, mit dem GitHub diesen Commit zusammengeführt hat (Merge, Squash, Rebase)
  * im neuesten Versuch des Laufs: Auftrag „Vollständig geprüft (Stand <tree>)“ und alle Pflichtaufträge erfolgreich,
    jeder andere Auftrag erfolgreich oder (nur Release-Vorlage/Übernahme) übersprungen
Es wird nur verglichen (Hashes, Namen, Ergebnisse) – kein Code und keine Dateien aus anderen Läufen ausgeführt.
Jeder Fehler (API, unerwartete Antwort) → kein Nachweis → volle CI.

    python3 -I .github/scripts/ci_nachweis.py --sha <commit> [--tree <tree>] [--trockenlauf]

Umgebung: GITHUB_REPOSITORY, GH_TOKEN (für gh), GITHUB_OUTPUT und GITHUB_STEP_SUMMARY (falls gesetzt).
Ausgaben (GITHUB_OUTPUT, nicht im Trockenlauf): uebernommen=true|false, lauf=<Adresse>, grund=<Text>.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

WORKFLOW = '.github/workflows/ci.yml'
NACHWEIS_PREFIX = 'Vollständig geprüft (Stand '
# Muss zu den Auftragsnamen in ci.yml passen (tests/unit/test_ci_nachweis.py prüft das).
PFLICHT = ['Schon im Pull Request geprüft?', 'Statische Prüfungen', 'Sicherheitsprüfungen', 'Anwendungs-Image prüfen',
           'Sicherung und Release-Prozess', 'Ende-zu-Ende-Tests', 'Anmeldung über Keycloak (nur CI)',
           'App prüfen (iOS, Android, Web)']
ERLAUBT_UEBERSPRUNGEN = {'Release zur Freigabe vorlegen', 'Prüfung aus Pull Request übernommen'}
HEX40 = re.compile(r'^[0-9a-f]{40}$')
# Die gefilterte Läufe-Suche der API liefert gelegentlich (gemessen: 1–2 von 8 Abfragen) eine leere Liste für einen
# vorhandenen Lauf. Leere Antworten daher bis zu VERSUCHE-mal wiederholen.
VERSUCHE, PAUSE = 3, float(os.environ.get('CI_NACHWEIS_PAUSE', '4'))


def nachweis_name(tree):
    return f'{NACHWEIS_PREFIX}{tree})'


def gh_api(pfad):
    r = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json', pfad],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f'gh api {pfad}: {(r.stderr or r.stdout).strip()[:200]}')
    return json.loads(r.stdout)


def auftraege_pruefen(jobs, tree):
    """None, wenn die Aufträge eines Laufs eine vollständige Prüfung von `tree` belegen; sonst der Grund."""
    nach_name = {}
    for j in jobs:
        nach_name.setdefault(j.get('name'), []).append(j)
    fehlend = [n for n in PFLICHT + [nachweis_name(tree)]
               if not nach_name.get(n) or any(j.get('conclusion') != 'success' for j in nach_name[n])]
    if fehlend:
        return 'nicht erfolgreich oder fehlend: ' + ', '.join(fehlend)
    andere = [f"{j.get('name')}={j.get('conclusion')}" for j in jobs
              if j.get('conclusion') != 'success'
              and not (j.get('name') in ERLAUBT_UEBERSPRUNGEN and j.get('conclusion') == 'skipped')]
    if andere:
        return 'weitere Aufträge nicht erfolgreich: ' + ', '.join(andere)
    if any(j.get('status') != 'completed' for j in jobs):
        return 'Aufträge noch nicht abgeschlossen'
    return None


def lauf_pruefen(lauf, repo, kopf):
    """None, wenn der Lauf grundsätzlich als Nachweis in Frage kommt; sonst der Grund."""
    if lauf.get('event') != 'pull_request':
        return 'kein Pull-Request-Lauf'
    if lauf.get('path') != WORKFLOW:
        return f"anderer Workflow ({lauf.get('path')})"
    if (lauf.get('repository') or {}).get('full_name') != repo:
        return 'anderes Repository'
    if (lauf.get('head_repository') or {}).get('full_name') != repo:
        return 'Pull Request aus einem Fork'
    if lauf.get('head_sha') != kopf:
        return 'anderer Kopf-Commit'
    if lauf.get('status') != 'completed' or lauf.get('conclusion') != 'success':
        return f"nicht erfolgreich ({lauf.get('status')}/{lauf.get('conclusion')})"
    return None


def suchen(api, repo, sha, tree=None, log=print):
    """→ (Lauf oder None, Grund). Wirft nie: jeder Fehler bedeutet „kein Nachweis“."""
    try:
        if not HEX40.match(sha or '') or (tree is not None and not HEX40.match(tree)):
            return None, 'ungültige Commit- oder Tree-Angabe'
        commit = api(f'repos/{repo}/commits/{sha}')
        tree_api = ((commit.get('commit') or {}).get('tree') or {}).get('sha')
        if tree is None:
            tree = tree_api
        if not tree_api or tree_api != tree:
            return None, f'Tree des Commits laut API ({tree_api}) passt nicht zum ausgecheckten Stand ({tree})'
        koepfe = []
        try:
            for pr in api(f'repos/{repo}/commits/{sha}/pulls'):
                if (pr.get('merged_at') and pr.get('merge_commit_sha') == sha
                        and ((pr.get('base') or {}).get('repo') or {}).get('full_name') == repo
                        and ((pr.get('head') or {}).get('repo') or {}).get('full_name') == repo):
                    koepfe.append(pr['head']['sha'])
        except Exception as e:   # nur ein zusätzlicher Weg (Squash/Rebase); Eltern-Commits reichen für Merge-Commits
            log(f'Hinweis: zugehörige Pull Requests nicht lesbar ({e})')
        eltern = [p.get('sha') for p in commit.get('parents') or []]
        koepfe += eltern[1:] + eltern[:1]   # zuerst der zusammengeführte Zweig, zuletzt der alte Stand von main
        koepfe = [k for i, k in enumerate(koepfe) if k and HEX40.match(k) and k not in koepfe[:i]]
        log(f'Commit {sha}, Tree {tree}; Kandidaten (Kopf-Commits): {", ".join(k[:7] for k in koepfe) or "keine"}')
        for kopf in koepfe:
            for versuch in range(VERSUCHE):
                laeufe = api(f'repos/{repo}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={kopf}&status=success&per_page=30')
                if laeufe.get('workflow_runs') or versuch == VERSUCHE - 1:
                    break
                time.sleep(PAUSE)
            for lauf in sorted(laeufe.get('workflow_runs') or [], key=lambda r: -int(r.get('id') or 0)):
                grund = lauf_pruefen(lauf, repo, kopf)
                if grund is None:
                    jobs = api(f"repos/{repo}/actions/runs/{int(lauf['id'])}/jobs?filter=latest&per_page=100").get('jobs') or []
                    grund = auftraege_pruefen(jobs, tree)
                log(f"  Lauf {lauf.get('id')} (Kopf {kopf[:7]}): {'gültiger Nachweis' if grund is None else grund}")
                if grund is None:
                    return lauf, f"vollständig geprüft im Lauf {lauf.get('html_url')}"
        return None, 'kein erfolgreicher, vollständiger Pull-Request-Lauf mit genau diesem Stand (z. B. main seither weiter)'
    except Exception as e:
        return None, f'Nachweis nicht prüfbar ({e!r})'


def main(argv=None, api=gh_api):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--sha', required=True)
    ap.add_argument('--tree')
    ap.add_argument('--trockenlauf', action='store_true', help='nur prüfen und berichten, keine Ausgaben für die CI')
    a = ap.parse_args(argv)
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    lauf, grund = suchen(api, repo, a.sha, a.tree)
    ja = lauf is not None
    print(('Übernehmen: ' if ja else 'Volle CI: ') + grund)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(('### ' + ('Trockenlauf: ' if a.trockenlauf else '')
                     + ('Prüfung aus dem Pull Request übernommen' if ja else 'Volle CI') + f' – `{a.sha[:7]}`\n\n{grund}\n'))
    if os.environ.get('GITHUB_OUTPUT') and not a.trockenlauf:
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            f.write(f"uebernommen={'true' if ja else 'false'}\n")
            f.write(f"lauf={(lauf or {}).get('html_url', '')}\n")
            f.write('grund=' + grund.replace('\n', ' ')[:500] + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
