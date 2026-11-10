"""Sicherheitsupdates der Container-Images (werkzeuge/images_aktualisieren.py) – ohne Netz, mit Digests aus einer Datei.

    python3 tests/unit/test_images_aktualisieren.py

Prüft an einer Kopie der echten Dateien: Fundstellen aller festgelegten Images; prüfen ändert nichts (Exit 3 bei neueren
Digests, 0 wenn aktuell); --setzen trägt neue Digests überall gleich ein und lässt die übrigen unverändert –
tests/deploy/test_images.py bleibt grün (PHP-Grundimage einheitlich, CI lädt dieselben Fassungen); verschiedene Digests
derselben Fassung werden nicht angefasst (Exit 1); Bericht für den Pull Request; neuere Fassungen derselben Reihe;
Zuordnung zur Registry.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location('images_aktualisieren', REPO / 'werkzeuge' / 'images_aktualisieren.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

PASS = FAIL = 0


def ok(name, cond, info=''):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f'PASS {name}')
    else:
        FAIL += 1; print(f'FAIL {name}' + (f'  {info}' if info else ''))


DATEIEN = ['docker-compose.yml', 'deploy/anmeldung/docker-compose.anmeldung.yml', 'deploy/testumgebung/docker-compose.yml',
           'deploy/testumgebung.sh', 'deploy/image/Dockerfile', '.github/workflows/ci.yml', 'deploy/anmeldung/pruefen.sh',
           'deploy/karte-laden.sh', 'deploy/adressen-laden.sh', 'tests/deploy/test_images.py']


def kopie():
    t = Path(tempfile.mkdtemp())
    for d in DATEIEN:
        (t / d).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / d, t / d)
    return t


def lauf(*args):
    return w.main([str(a) for a in args])


# Fundstellen im echten Repository: jedes festgelegte Image genau einmal mit einem Digest
echt = w.fundstellen(REPO)
namen = {f'{n}:{t}' for n, t in echt}
ok('Fundstellen: PHP, Caddy, Keycloak, PostgreSQL und Hilfsimages gefunden',
   {'php:8.3-apache', 'postgres:17-alpine'} <= namen
   and all(any(n.startswith(p) for n in namen) for p in ('caddy:2.', 'quay.io/keycloak/keycloak:')), sorted(namen))
ok('Fundstellen: PHP-Grundimage an vier Stellen (Kundenseite, Testumgebung, Skript, Dockerfile)',
   len(next(v for (n, t), v in echt.items() if n == 'php').popitem()[1]) == 4)
ok('Fundstellen: erzeugte Doku und Testarbeitsordner werden ausgelassen',
   not any(o.startswith(w.AUSLASSEN) for v in echt.values() for orte in v.values() for o in orte))

t = kopie()
funde = w.fundstellen(t)
php = next((n, tg) for n, tg in funde if n == 'php')
kc = next((n, tg) for n, tg in funde if n.startswith('quay.io/keycloak/'))
alt_php, alt_kc = next(iter(funde[php])), next(iter(funde[kc]))
neu_php, neu_kc = 'a' * 64, 'b' * 64
quelle = t / 'quelle.json'
quelle.write_text(json.dumps({f'{php[0]}:{php[1]}': 'sha256:' + neu_php, f'{kc[0]}:{kc[1]}': 'sha256:' + neu_kc}))
vorher = {d: (t / d).read_text() for d in DATEIEN}

ok('prüfen: neuere Digests gefunden → Exit 3', lauf('--wurzel', t, '--quelle', quelle, '--bericht', t / 'b.md') == 3)
ok('prüfen: ändert keine Datei', all((t / d).read_text() == vorher[d] for d in DATEIEN))
bericht = (t / 'b.md').read_text()
ok('Bericht nennt geänderte Images mit allen Stellen, unveränderte nicht',
   f'`{php[0]}:{php[1]}`' in bericht and 'deploy/image/Dockerfile' in bericht and f'`{kc[0]}:{kc[1]}`' in bericht and 'caddy' not in bericht, bericht)

ok('setzen: Exit 3 (eingetragen)', lauf('--wurzel', t, '--quelle', quelle, '--setzen') == 3)
alle = '\n'.join((t / d).read_text() for d in DATEIEN)
ok('setzen: PHP-Grundimage an allen vier Stellen neu, alter Digest nirgends mehr', alle.count(neu_php) == 4 and alt_php not in alle)
ok('setzen: Keycloak in der Compose-Datei neu (CI lädt von dort, Workflows ohne Digests)', alle.count(neu_kc) == 1 and alt_kc not in alle
   and neu_kc not in (t / '.github/workflows/ci.yml').read_text())
ok('setzen: übrige Images unverändert', all(next(iter(v)) in alle for k, v in funde.items() if k not in (php, kc)))
r = subprocess.run([sys.executable, 'tests/deploy/test_images.py'], cwd=t, capture_output=True, text=True)
ok('danach: tests/deploy/test_images.py grün (einheitlich, CI lädt dieselben Fassungen)', r.returncode == 0, r.stdout + r.stderr)
ok('erneut prüfen: alles aktuell → Exit 0', lauf('--wurzel', t, '--quelle', quelle) == 0)

# verschiedene Digests derselben Fassung: nicht automatisch vereinheitlichen
d = t / 'deploy/testumgebung.sh'
d.write_text(d.read_text().replace(neu_php, 'c' * 64))
ok('uneinheitliche Fassung: Exit 1, nichts geändert', lauf('--wurzel', t, '--quelle', quelle, '--setzen') == 1 and ('c' * 64) in d.read_text()
   and (t / 'deploy/image/Dockerfile').read_text().count(neu_php) == 1)
shutil.rmtree(t)

# neuere Fassungen derselben Reihe
ok('neuere Fassungen: Patch derselben Reihe, sortiert', w.neuere_fassungen('26.8.1', ['26.8.0', '26.8.10', '26.9.0', '26.8.2', '26.8.2-alpine', '27.0.0']) == ['26.8.2', '26.8.10'])
ok('neuere Fassungen: mit Zusatz und Präfix', w.neuere_fassungen('3.12.14-bookworm', ['3.12.15-bookworm', '3.12.15-slim', '3.13.0-bookworm']) == ['3.12.15-bookworm']
   and w.neuere_fassungen('v1.31.2', ['v1.31.3', '1.31.4', 'v1.32.0']) == ['v1.31.3'])
ok('neuere Fassungen: gleitende Fassung hat keine', w.neuere_fassungen('8.3-apache', ['8.3.30-apache']) == [] and w.neuere_fassungen('17-alpine', ['17.7-alpine']) == [])

# Registry
ok('Registry: offizielle Images unter library/ auf Docker Hub', w.registry('php') == ('https://registry-1.docker.io', 'library/php'))
ok('Registry: Organisation auf Docker Hub', w.registry('protomaps/go-pmtiles') == ('https://registry-1.docker.io', 'protomaps/go-pmtiles'))
ok('Registry: eigene Registry (quay.io)', w.registry('quay.io/keycloak/keycloak') == ('https://quay.io', 'keycloak/keycloak'))

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(0 if FAIL == 0 else 1)
