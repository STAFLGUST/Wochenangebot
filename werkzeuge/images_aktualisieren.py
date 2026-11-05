#!/usr/bin/env python3
"""Sicherheitsupdates der Container-Images: festgelegte Digests auf den neuesten Stand derselben Fassung bringen.

Alle fremden Images sind über Fassung und Digest festgelegt (tests/deploy/test_images.py) – ein Release holt nie unbemerkt
etwas anderes. Die Herausgeber bauen dieselbe Fassung (z. B. php:8.3-apache, postgres:17-alpine, caddy:2.11.7) aber
regelmäßig neu, wenn das Betriebssystem darunter Sicherheitskorrekturen bekommt. Dieses Werkzeug fragt die Registries nach
dem aktuellen Digest jeder eingetragenen Fassung und ersetzt ihn – überall gleich (Compose-Dateien, Dockerfile,
Testumgebung, CI). Neuere Fassungen derselben Reihe (z. B. Keycloak 26.8.2 statt 26.8.1) meldet es nur: Ein Wechsel der
Fassung betrifft auch Prüfsummen und Downloads der CI (tests/oidc/umgebung.sh) und wird von Hand gemacht.

  python3 werkzeuge/images_aktualisieren.py                  prüfen (Exit 0: alles aktuell, 3: neuere Digests vorhanden,
                                                             1: Fehler, z. B. Registry nicht erreichbar, und nichts Neues)
  python3 werkzeuge/images_aktualisieren.py --setzen         neuere Digests überall eintragen (Exit 0 bzw. 3 wie oben)
  python3 werkzeuge/images_aktualisieren.py --neuere         zusätzlich neuere Fassungen derselben Reihe melden
  --bericht DATEI   Bericht als Markdown (Beschreibung des Pull Requests)
  --quelle DATEI    Digests aus einer JSON-Datei {"name:fassung": "sha256:…"} statt aus den Registries (Tests)
  --wurzel ORDNER   anderes Repository-Verzeichnis (Tests)

Wöchentlich ausgeführt vom Workflow .github/workflows/sicherheitsupdates.yml (Pull Request, Merge und Release wie immer
nur durch den Inhaber). Netz: nur lesende Anfragen an die Registries (Docker Hub, quay.io), ohne Zugangsdaten.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = re.compile(r'(?P<name>[a-z0-9][a-z0-9./_-]*):(?P<tag>[A-Za-z0-9._-]+)@sha256:(?P<digest>[0-9a-f]{64})')
AUSLASSEN = ('.git/', 'node_modules/', 'tests/.arbeit/', 'tests/.ergebnisse/', 'docs/entwickler/referenz/')
ACCEPT = ', '.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])
AGENT = 'stafl-images-aktualisieren'


def dateien(wurzel):
    """Textdateien des Repositorys (git ls-files, sonst Ordner durchsuchen)."""
    try:
        namen = subprocess.run(['git', 'ls-files'], cwd=wurzel, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        namen = [str(p.relative_to(wurzel)) for p in Path(wurzel).rglob('*') if p.is_file()]
    for n in sorted(namen):
        if n.startswith(AUSLASSEN) or '/__pycache__/' in n:
            continue
        p = Path(wurzel) / n
        try:
            yield n, p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue


def fundstellen(wurzel):
    """{(name, tag): {digest: [Datei:Zeile, …]}} aller festgelegten Images"""
    out = {}
    for n, text in dateien(wurzel):
        for nr, zeile in enumerate(text.splitlines(), 1):
            for m in REF.finditer(zeile):
                out.setdefault((m['name'], m['tag']), {}).setdefault(m['digest'], []).append(f'{n}:{nr}')
    return out


def registry(name):
    """(Registry-Adresse, Repository) – Docker Hub für Namen ohne eigene Registry, offizielle Images unter library/"""
    teile = name.split('/')
    if len(teile) > 1 and ('.' in teile[0] or ':' in teile[0]):
        return 'https://' + teile[0], '/'.join(teile[1:])
    return 'https://registry-1.docker.io', name if len(teile) > 1 else 'library/' + name


def _anfrage(url, methode='GET', token=None, accept=None, versuche=3):
    """Eine Anfrage; bei „zu viele Anfragen“ (429) oder Serverfehler kurz warten und erneut versuchen"""
    kopf = {'User-Agent': AGENT}
    if token:
        kopf['Authorization'] = 'Bearer ' + token
    if accept:
        kopf['Accept'] = accept
    for i in range(versuche):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, method=methode, headers=kopf), timeout=30)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == versuche - 1:
                raise
            warte = e.headers.get('Retry-After', '')
            time.sleep(min(int(warte) if warte.isdigit() else 5 * (i + 1), 30))


def _token(www_auth):
    """Anonymes Lese-Token nach den Angaben aus WWW-Authenticate (Bearer realm, service, scope)"""
    felder = dict(re.findall(r'(\w+)="([^"]*)"', www_auth or ''))
    if 'realm' not in felder:
        return None
    q = '&'.join(f'{k}={urllib.request.quote(v, safe=":/,")}' for k, v in felder.items() if k in ('service', 'scope'))
    with _anfrage(felder['realm'] + ('?' + q if q else '')) as r:
        d = json.load(r)
    return d.get('token') or d.get('access_token')


def _mit_token(url, methode, accept, tokens, schluessel):
    try:
        return _anfrage(url, methode, tokens.get(schluessel), accept)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        tokens[schluessel] = _token(e.headers.get('WWW-Authenticate'))
        return _anfrage(url, methode, tokens[schluessel], accept)


def digest_holen(name, tag, tokens):
    basis, repo = registry(name)
    with _mit_token(f'{basis}/v2/{repo}/manifests/{tag}', 'HEAD', ACCEPT, tokens, (basis, repo)) as r:
        d = r.headers.get('Docker-Content-Digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', d):
        raise RuntimeError(f'{name}:{tag}: Registry liefert keinen Digest')
    return d.split(':', 1)[1]


def fassungen_holen(name, tag, tokens, grenze=10):
    """Fassungen (Tags) derselben Reihe wie `tag` – über die gefilterten Schnittstellen von Docker Hub bzw. quay.io (wenige
    Anfragen statt tausender Tags), sonst über die Registry (tags/list, mit Seiten)."""
    basis, repo = registry(name)
    reihe = '.'.join(re.sub(r'^v', '', tag).split('.')[:2]) + '.'
    if basis == 'https://registry-1.docker.io':
        url, out = f'https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100&name={urllib.request.quote(reihe)}', []
        for _ in range(grenze):
            with _anfrage(url) as r:
                d = json.load(r)
            out += [t['name'] for t in d.get('results') or []]
            url = d.get('next')
            if not url:
                return out
        return out
    if basis == 'https://quay.io':
        url = f'https://quay.io/api/v1/repository/{repo}/tag/?onlyActiveTags=true&limit=100&filter_tag_name=like:{urllib.request.quote(reihe)}'
        out = []
        for seite in range(1, grenze + 1):
            with _anfrage(url + f'&page={seite}') as r:
                d = json.load(r)
            out += [t['name'] for t in d.get('tags') or []]
            if not d.get('has_additional'):
                break
        return out
    url, out = f'{basis}/v2/{repo}/tags/list?n=1000', []
    for _ in range(grenze):
        with _mit_token(url, 'GET', None, tokens, (basis, repo)) as r:
            out += json.load(r).get('tags') or []
            link = r.headers.get('Link', '')
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        if not m:
            break
        url = m.group(1) if m.group(1).startswith('http') else basis + m.group(1)
    return out


def neuere_fassungen(tag, alle):
    """Neuere Fassungen derselben Reihe: gleiche Haupt- und Nebenversion, gleicher Zusatz (z. B. 26.8.1 → 26.8.2,
    3.12.14-bookworm → 3.12.15-bookworm, v1.31.2 → v1.31.3). Gleitende Fassungen wie 8.3-apache haben keine."""
    m = re.fullmatch(r'(v?)(\d+)\.(\d+)\.(\d+)(.*)', tag)
    if not m:
        return []
    vor, a, b, c, zusatz = m[1], int(m[2]), int(m[3]), int(m[4]), m[5]
    out = []
    for t in alle:
        n = re.fullmatch(r'(v?)(\d+)\.(\d+)\.(\d+)(.*)', t)
        if n and n[1] == vor and int(n[2]) == a and int(n[3]) == b and n[5] == zusatz and int(n[4]) > c:
            out.append((int(n[4]), t))
    return [t for _, t in sorted(out)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--setzen', action='store_true')
    ap.add_argument('--neuere', action='store_true')
    ap.add_argument('--bericht')
    ap.add_argument('--quelle')
    ap.add_argument('--wurzel', default=str(ROOT))
    a = ap.parse_args(argv)
    wurzel = Path(a.wurzel)
    funde = fundstellen(wurzel)
    if not funde:
        print('Keine festgelegten Images gefunden.', file=sys.stderr)
        return 1
    quelle = json.loads(Path(a.quelle).read_text(encoding='utf-8')) if a.quelle else None
    tokens, neu, fehler, hinweise, zeilen = {}, {}, [], [], []
    for (name, tag), digests in sorted(funde.items()):
        ref = f'{name}:{tag}'
        if len(digests) > 1:
            fehler.append(f'{ref}: verschiedene Digests im Repository ({", ".join(d[:12] for d in digests)}) – erst vereinheitlichen')
            continue
        alt = next(iter(digests))
        try:
            aktuell = (quelle[ref].split(':', 1)[-1] if ref in quelle else alt) if quelle is not None else digest_holen(name, tag, tokens)
        except (OSError, RuntimeError, urllib.error.URLError) as e:
            fehler.append(f'{ref}: Registry nicht erreichbar ({e})')
            continue
        orte = digests[alt]
        if aktuell != alt:
            neu[alt] = aktuell
        zeilen.append((ref, alt, aktuell, orte))
        if a.neuere and quelle is None and re.fullmatch(r'v?\d+\.\d+\.\d+.*', tag):   # gleitende Fassungen (8.3-apache) haben keine
            try:
                weiter = neuere_fassungen(tag, fassungen_holen(name, tag, tokens))
                if weiter:
                    hinweise.append(f'{ref}: neuere Fassung(en) {", ".join(weiter)} – Wechsel von Hand (auch CI-Downloads/Prüfsummen prüfen)')
            except (OSError, urllib.error.URLError) as e:
                hinweise.append(f'{ref}: Fassungen nicht abrufbar ({e})')
    if a.setzen and neu:
        for n, text in dateien(wurzel):
            ersetzt = REF.sub(lambda m: m.group(0).replace(m['digest'], neu.get(m['digest'], m['digest'])), text)
            if ersetzt != text:
                (wurzel / n).write_text(ersetzt, encoding='utf-8')
    # Ausgabe
    for ref, alt, aktuell, orte in zeilen:
        zustand = 'aktuell' if alt == aktuell else f'neu: {aktuell[:12]}…' + (' (eingetragen)' if a.setzen else '')
        print(f'{ref:<48} {alt[:12]}…  {zustand}  [{len(orte)} Stelle(n)]')
    for h in hinweise:
        print('Hinweis: ' + h)
    for f in fehler:
        print('FEHLER: ' + f, file=sys.stderr)
    if a.bericht:
        b = ['## Sicherheitsupdates der Container-Images', '',
             'Neuer Digest derselben Fassung = vom Herausgeber neu gebaut (meist Sicherheitskorrekturen im Betriebssystem). '
             'Wirksam erst mit dem nächsten Release (das Anwendungs-Image wird dabei neu gebaut).', '',
             '| Image | bisher | neu | Stellen |', '| --- | --- | --- | --- |']
        for ref, alt, aktuell, orte in zeilen:
            if alt != aktuell:
                b.append(f'| `{ref}` | `{alt[:12]}` | `{aktuell[:12]}` | {", ".join(f"`{o}`" for o in orte)} |')
        if not neu:
            b.append('| – | – | – | alles aktuell |')
        if hinweise:
            b += ['', '**Neuere Fassungen (nicht automatisch):**', ''] + [f'- {h}' for h in hinweise]
        if fehler:
            b += ['', '**Fehler:**', ''] + [f'- {f}' for f in fehler]
        Path(a.bericht).write_text('\n'.join(b) + '\n', encoding='utf-8')
    if neu:
        return 3          # neuere Digests gefunden (mit --setzen eingetragen) – auch wenn einzelne Images nicht abrufbar waren
    return 1 if fehler else 0


if __name__ == '__main__':
    sys.exit(main())
