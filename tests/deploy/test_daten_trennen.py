"""Test von deploy/daten_trennen.py (ADR-007 Stufe 2: interne Dokumente aus dem gemeinsamen Datenordner) – in Wegwerf-Ordnern,
für Dateien und SQLite: Trennen, Wiederholen nach Abbruch, Schutz vor Überschreiben, Zusammenführen ohne Verlust – und dass die
Speicherschicht (app/api/storage.php) danach auf beiden Seiten richtig liest: Mitarbeiterseite alles, Kundenseite nichts Internes."""
import json, os, shutil, sqlite3, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKRIPT = REPO / 'deploy' / 'daten_trennen.py'
DB = REPO / 'deploy' / 'datenbank.py'
G = '<?php http_response_code(404); exit; ?>\n'
sys.path.insert(0, str(REPO / 'deploy'))
import daten_trennen as dt  # noqa: E402

ok_n = fail_n = 0


def check(name, cond, info=''):
    global ok_n, fail_n
    if cond: ok_n += 1; print('PASS ' + name)
    else: fail_n += 1; print('FAIL ' + name + (('  ' + str(info)) if info else ''))


def doc(root, name, value):
    p = root / (name + '.php'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(G + json.dumps(value))


def aufbau(t):
    d = t / 'daten'; d.mkdir()
    doc(d, 'angebot', {'items': [1]}); doc(d, 'kunden', {'customers': []}); doc(d, 'protokoll/2026-11', [{'a': 'kunde_login'}])
    doc(d, 'hr-personal', {'personen': [{'name': 'Test Person'}]}); doc(d, 'nutzer', {'users': []}); doc(d, 'versionen/v1', {'x': 1})
    doc(d, 'crm-kunden', {'k': 1}); doc(d, 'sicherung', {'ok': True}); doc(d, 'deployment', {'sha': 'abc'})
    (d / 'index.php').write_text('<?php http_response_code(404);'); (d / 'geo').mkdir(); (d / 'geo' / 'laender.dat.php').write_text(G + '{}')
    (d / 'dateien' / 'qs' / 'ab').mkdir(parents=True); (d / 'dateien' / 'qs' / 'ab' / 'ab12.bin').write_bytes(b'PDF-Inhalt')
    return d


def lauf(*args):
    p = subprocess.run([sys.executable, str(SKRIPT), *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def baum(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file() and not p.name.endswith('.lock')}


def zeilen(root):
    with sqlite3.connect(root / '.sqlite/store.sqlite') as c:
        return {n: json.loads(v) for n, v in c.execute('SELECT name,payload FROM documents')}


def php(code, daten, intern=None):
    env = {k: v for k, v in os.environ.items() if k != 'WA_DATEN_INTERN'}
    if intern: env['WA_DATEN_INTERN'] = str(intern)
    pre = f"$DATA = {json.dumps(str(daten))}; require {json.dumps(str(REPO / 'app/api/storage.php'))}; "
    p = subprocess.run(['php', '-r', pre + code], capture_output=True, text=True, env=env)
    return p.stdout.strip() + p.stderr.strip()


ks = dt.kundenseite()
check('Regelwerk: Kundenseite enthält Angebot, Kunden, Protokoll; HR und Nutzer sind intern',
      not dt.ist_intern('angebot', ks) and not dt.ist_intern('kunden', ks) and not dt.ist_intern('protokoll/2026-11', ks)
      and dt.ist_intern('hr-personal', ks) and dt.ist_intern('nutzer', ks) and dt.ist_intern('versionen/v1', ks) and not dt.ist_intern('sicherung', ks))

# Gleiche Einteilung in Python (Migration) und PHP (Anwendung) für jedes registrierte Dokument
import tomllib
namen = [d['name'].replace('/*', '/beispiel') for d in tomllib.load(open(REPO / 'regeln/datenverantwortung.toml', 'rb'))['dokument']]
namen += [d['name'][:-2] for d in tomllib.load(open(REPO / 'regeln/datenverantwortung.toml', 'rb'))['dokument'] if d['name'].endswith('/*')]   # Sperren der Gruppen
with tempfile.TemporaryDirectory() as t:
    t = Path(t); (t / 'd').mkdir(); (t / 'd' / '.daten-getrennt').write_text('1')
    aus_php = json.loads(php(f"echo json_encode(array_map('store_bereich', {json.dumps(namen)}));", t / 'd') or '[]')
check('Einteilung in PHP und Python identisch (alle registrierten Dokumente)',
      aus_php == ['intern' if dt.ist_intern(n, ks) else 'haupt' for n in namen], [n for n, b in zip(namen, aus_php) if (b == 'intern') != dt.ist_intern(n, ks)][:5])

for art in ('dateien', 'sqlite'):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); d = aufbau(t); i = t / 'daten-intern'
        if art == 'sqlite':
            subprocess.run([sys.executable, str(DB), 'migrate', str(d), '--offline'], check=True, capture_output=True)
        vorher = baum(d); vorher_db = zeilen(d) if art == 'sqlite' else None
        code, out = lauf('pruefen', str(d), str(i))
        check(f'{art}: pruefen zeigt den Plan und ändert nichts', code == 0 and 'hr-personal' in out and baum(d) == vorher and not i.exists(), out)
        code, out = lauf('trennen', str(d), str(i))
        check(f'{art}: trennen nur mit --offline', code != 0 and '--offline' in out and baum(d) == vorher)
        code, out = lauf('trennen', str(d), str(i), '--offline')
        check(f'{art}: trennen läuft', code == 0 and 'Getrennt' in out, out)
        check(f'{art}: Kennzeichen gesetzt', (d / '.daten-getrennt').is_file() and (i / '.daten-intern').is_file())
        if art == 'dateien':
            check(f'{art}: interne Dateien verschoben, Kundenseite und Sidecars bleiben', (i / 'hr-personal.php').is_file() and (i / 'versionen/v1.php').is_file()
                  and not (d / 'hr-personal.php').exists() and not (d / 'nutzer.php').exists() and not (d / 'versionen').exists()
                  and (d / 'angebot.php').is_file() and (d / 'protokoll/2026-11.php').is_file() and (d / 'sicherung.php').is_file() and (d / 'geo/laender.dat.php').is_file())
            check(f'{art}: Inhalt unverändert', (i / 'hr-personal.php').read_bytes() == vorher['hr-personal.php'])
        else:
            check(f'{art}: Datenbank geteilt – interne Zeilen nur in daten-intern', set(zeilen(i)) == {'hr-personal', 'nutzer', 'versionen/v1', 'crm-kunden'}
                  and not ({'hr-personal', 'nutzer', 'crm-kunden'} & set(zeilen(d))) and {'angebot', 'kunden', 'protokoll/2026-11'} <= set(zeilen(d))
                  and (i / '.sqlite-active').is_file(), (sorted(zeilen(i)), sorted(zeilen(d))))
            check(f'{art}: alte interne Datendateien ebenfalls aus dem gemeinsamen Ordner', not (d / 'hr-personal.php').exists() and (i / 'hr-personal.php').is_file())
        check(f'{art}: Dateiablage verschoben', (i / 'dateien/qs/ab/ab12.bin').read_bytes() == b'PDF-Inhalt' and not (d / 'dateien').exists())
        # Speicherschicht: Mitarbeiterseite (WA_DATEN_INTERN) liest alles, Kundenseite nichts Internes und schreibt nichts Internes
        r = php("echo json_encode([store_read('hr-personal'), store_read('angebot'), store_names('versionen')]);", d, i)
        check(f'{art}: Mitarbeiterseite liest interne und gemeinsame Dokumente', json.loads(r or 'null') == [{'personen': [{'name': 'Test Person'}]}, {'items': [1]}, ['versionen/v1']], r)
        r = php("echo json_encode([store_read('hr-personal'), store_read('angebot'), store_names('versionen'), store_mtime('nutzer')]);", d)
        check(f'{art}: Kundenseite sieht interne Dokumente nicht', json.loads(r or 'null') == [None, {'items': [1]}, [], None], r)
        r = php("try { store_write('hr-personal', ['x' => 1]); echo 'geschrieben'; } catch (StoreKeinZugang $e) { echo 'abgelehnt'; }", d)
        check(f'{art}: Kundenseite kann nichts Internes schreiben (auch nicht in den gemeinsamen Ordner)', r == 'abgelehnt' and not (d / 'hr-personal.php').exists(), r)
        r = php("with_lock('nutzer', function () { store_write('nutzer', ['users' => [1]]); }); with_lock('kunden', function () { store_write('kunden', ['customers' => [2]]); }); echo json_encode([store_read('nutzer'), store_read('kunden')]);", d, i)
        check(f'{art}: Mitarbeiterseite schreibt in beide Bereiche (mit Sperren/Transaktionen je Bereich)', json.loads(r or 'null') == [{'users': [1]}, {'customers': [2]}], r)
        r = php("with_lock('kunden', function () { with_lock('nutzer', function () { store_write('nutzer', ['users' => [3]]); }); store_write('kunden', ['customers' => [3]]); }); echo json_encode([store_read('nutzer'), store_read('kunden'), empty($GLOBALS['store_tx'])]);", d, i)
        check(f'{art}: verschachtelte Sperren über beide Bereiche, danach keine offene Transaktion', json.loads(r or 'null') == [{'users': [3]}, {'customers': [3]}, True], r)
        r = php("echo json_encode(store_stats());", d, i)
        check(f'{art}: Kennzahlen zählen beide Bereiche', json.loads(r or '{}').get('getrennt') is True and json.loads(r)['documents'] >= 7, r)
        r = php("echo json_encode(store_read('hr-personal'));", d, t / 'falsch')
        r2 = php("echo store_read('angebot') === null ? 'leer' : 'ok';", d, t / 'falsch')
        check(f'{art}: WA_DATEN_INTERN ohne Kennzeichen → Fehler statt leerer interner Daten (gemeinsame lesbar)', 'nicht eingerichtet' in r and 'null' not in r and r2 == 'ok', (r, r2))
        # Wiederholung nach Abbruch: Kopie liegt noch im gemeinsamen Ordner → erneutes trennen entfernt sie (nur bei gleichem Inhalt)
        if art == 'dateien':
            shutil.copy2(i / 'crm-kunden.php', d / 'crm-kunden.php')
            code, out = lauf('trennen', str(d), str(i), '--offline')
            check(f'{art}: erneutes trennen entfernt übrig gebliebene gleiche Kopien', code == 0 and not (d / 'crm-kunden.php').exists(), out)
            (d / 'crm-kunden.php').write_text(G + '{"k":99}')
            code, out = lauf('trennen', str(d), str(i), '--offline')
            check(f'{art}: abweichende Kopie → Abbruch, nichts entfernt', code == 1 and 'Abweichende' in out and (d / 'crm-kunden.php').exists())
            (d / 'crm-kunden.php').unlink()
        # Zusammenführen: alles wieder wie vorher (bis auf die Schreibproben oben)
        code, out = lauf('zusammenfuehren', str(d), str(i), '--offline')
        check(f'{art}: zusammenführen läuft, Kennzeichen entfernt', code == 0 and not (d / '.daten-getrennt').exists() and not (i / '.daten-intern').exists(), out)
        if art == 'dateien':
            nachher = baum(d)
            erwartet = {**vorher, 'nutzer.php': nachher.get('nutzer.php'), 'kunden.php': nachher.get('kunden.php')}
            check(f'{art}: alle Dateien wieder im gemeinsamen Ordner, Inhalt gleich', nachher == erwartet and json.loads(nachher['nutzer.php'][len(G):]) == {'users': [3]},
                  sorted(set(nachher) ^ set(erwartet)))
        else:
            z = zeilen(d)
            check(f'{art}: alle Datensätze wieder in der gemeinsamen Datenbank', set(z) == set(vorher_db) and z['hr-personal'] == vorher_db['hr-personal'] and z['nutzer'] == {'users': [3]},
                  sorted(set(z) ^ set(vorher_db)))
        check(f'{art}: Dateiablage zurück, daten-intern leer', (d / 'dateien/qs/ab/ab12.bin').read_bytes() == b'PDF-Inhalt' and dt.leer(i))
        r = php("echo json_encode(store_read('hr-personal'));", d)
        check(f'{art}: nach dem Zusammenführen liest auch eine Seite ohne WA_DATEN_INTERN wieder alles', json.loads(r or 'null') == {'personen': [{'name': 'Test Person'}]}, r)
        # Schutz: Zielordner mit Daten wird nicht überschrieben
        doc(i, 'fremd', {'x': 1})
        code, out = lauf('trennen', str(d), str(i), '--offline')
        check(f'{art}: Zielordner mit Daten → Abbruch, nichts verändert', code == 1 and 'schon Daten' in out and not (d / '.daten-getrennt').exists(), out)
        code, out = lauf('zusammenfuehren', str(d), str(i), '--offline')
        check(f'{art}: zusammenführen ohne Trennung → Abbruch', code == 1 and 'nicht getrennt' in out)

with tempfile.TemporaryDirectory() as t:
    t = Path(t); d = aufbau(t)
    code, out = lauf('trennen', str(d), str(d / 'intern'), '--offline')
    check('daten-intern innerhalb von daten/ abgelehnt', code != 0 and 'nicht darin' in out)

print(f'{ok_n}/{ok_n + fail_n} passed')
sys.exit(0 if fail_n == 0 else 1)
