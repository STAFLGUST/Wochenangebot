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
    t = Path(t); (t / 'd').mkdir(); (t / 'd' / '.daten-getrennt').write_text('2')
    aus_php = json.loads(php(f"echo json_encode(array_map('store_bereich', {json.dumps(namen)}));", t / 'd') or '[]')
check('Einteilung in PHP und Python identisch (alle registrierten Dokumente, höchste Stufe)',
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
            check(f'{art}: Datenbank geteilt – interne Zeilen nur in daten-intern', set(zeilen(i)) == {'hr-personal', 'nutzer', 'versionen/v1', 'crm-kunden', 'kundenstamm'}
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
        r = php("with_lock('nutzer', function () { store_write('nutzer', ['users' => [1]]); }); with_lock('kunden', function () { store_write('kunden', ['customers' => [['id' => 'k2']]]); }); echo json_encode([store_read('nutzer'), store_read('kunden')]);", d, i)
        check(f'{art}: Mitarbeiterseite schreibt in beide Bereiche (mit Sperren/Transaktionen je Bereich)', json.loads(r or 'null') == [{'users': [1]}, {'customers': [{'id': 'k2'}]}], r)
        r = php("with_lock('kunden', function () { with_lock('nutzer', function () { store_write('nutzer', ['users' => [3]]); }); store_write('kunden', ['customers' => [['id' => 'k3']]]); }); echo json_encode([store_read('nutzer'), store_read('kunden'), empty($GLOBALS['store_tx'])]);", d, i)
        check(f'{art}: verschachtelte Sperren über beide Bereiche, danach keine offene Transaktion', json.loads(r or 'null') == [{'users': [3]}, {'customers': [{'id': 'k3'}]}, True], r)
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

# ─────────────── Trennstufe 2 (ADR-007 Stufe 2b): Kundendokument teilen, Bestand/Stammdaten/Postfächer innen ───────────────

def php_lib(code, daten, intern=None):
    """Anwendung mit allen Funktionen (lib/laden.php) gegen diesen Datenordner – Mitarbeiterseite mit intern, Kundenseite ohne."""
    env = {k: v for k, v in os.environ.items() if k not in ('WA_DATEN_INTERN', 'WA_POSTAUSGANG')}
    if intern: env['WA_DATEN_INTERN'] = str(intern)
    pre = ("define('WA_API', true); define('WA_CLI', true); require " + json.dumps(str(REPO / 'app/api/lib/laden.php')) + "; "
           f"$DATA = {json.dumps(str(daten))}; ")
    p = subprocess.run(['php', '-d', 'display_errors=stderr', '-r', pre + code], capture_output=True, text=True, env=env)
    return p.stdout.strip() + p.stderr.strip()


ks1, ks2 = dt.kundenseite(stufe=1), dt.kundenseite(stufe=2)
check('Stufe 2: Bestand, Stammdaten, Postfächer, Vorlage, Benachrichtigungen erst ab Stufe 2 intern',
      all(not dt.ist_intern(n, ks1) and dt.ist_intern(n, ks2) for n in ('bestand', 'stammdaten', 'mailkonto', 'mailkonto-intern', 'mailvorlage', 'benachrichtigungen'))
      and not dt.ist_intern('kunden', ks2) and not dt.ist_intern('artikelauszug', ks2) and dt.ist_intern('kundenstamm', ks2) and dt.ist_intern('bestellung-empfaenger', ks2))
for stufe, ksx in ((1, ks1), (2, ks2)):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); (t / 'd').mkdir(); (t / 'd' / '.daten-getrennt').write_text(f'{stufe}\n')
        aus_php = json.loads(php(f"echo json_encode(array_map('store_bereich', {json.dumps(namen)}));", t / 'd') or '[]')
    check(f'Stufe {stufe}: Einteilung in PHP und Python identisch', aus_php == ['intern' if dt.ist_intern(n, ksx) else 'haupt' for n in namen],
          [n for n, b in zip(namen, aus_php) if (b == 'intern') != dt.ist_intern(n, ksx)][:5])
php_stufe = php("echo DATEN_TRENNSTUFE;", REPO / 'app')
check('Höchste Stufe gleich in Python, PHP und Regelwerk', php_stufe == str(dt.ZIELSTUFE) == '2', php_stufe)
with tempfile.TemporaryDirectory() as t:
    t = Path(t); (t / 'd').mkdir(); (t / 'd' / '.daten-getrennt').write_text('3\n')
    r = php("try { store_bereich('kunden'); echo 'gelesen'; } catch (RuntimeException $e) { echo $e->getMessage(); }", t / 'd')
check('Kennzeichen einer neueren Stufe → Fehler statt falscher Einteilung', 'zusammenfuehren' in r, r)

KUNDE = {'id': 'kaaaaaaaaaaaa', 'nr': '4711', 'firma': 'Test GmbH', 'ansprechpartner': 'Frau Test', 'strasse': 'Weg 1', 'plz': '20000', 'ort': 'Hamburg',
         'email': 'einkauf@test.invalid', 'telefon': '040 1', 'notiz': 'intern', 'vertreter': '7', 'gruppe': '3', 'angebote': ['standard'], 'active': True,
         'mailAngebot': True, 'login': {'username': 'test', 'hash': '$2y$x', 'active': True, 'sv': 1}, 'wawi': {'umsatz': 12345, 'kreditlimit': 5000},
         'weekly': {'week': 44}, 'created': '2026-01-01T00:00:00Z'}
KUNDE2 = {'id': 'kbbbbbbbbbbbb', 'firma': 'Ohne Mail AG', 'active': False, 'login': None}


def aufbau2(t):
    d = aufbau(t)
    doc(d, 'kunden', {'rev': 5, 'customers': [KUNDE, KUNDE2], 'updatedAt': 'x'})
    doc(d, 'bestellung', {'enabled': True, 'to': ['team@test.invalid', 'chef@test.invalid'], 'copy': True, 'updatedAt': 'y', 'updatedBy': 'admin'})
    doc(d, 'bestand', {'articles': [{'code': '0100', 'kg': 5, 'ek': 3.1, 'lots': [{'lot': 'P1'}]}, {'code': '200', 'kg': 0}]})
    doc(d, 'stammdaten', {'rev': 1, 'articles': [{'code': '0100', 'category': 'Rind', 'origin': 'DE', 'condition': 'frisch', 'gtin': '4000'}]})
    doc(d, 'mailkonto', {'host': 'smtp.test.invalid', 'passEnc': 'v2:x'}); doc(d, 'benachrichtigungen', {'events': {}})
    return d


def portal(c):
    p = {k: v for k, v in c.items() if k in dt.kunden_felder()}
    if 'email' in c: p['emailMaske'] = dt.email_maske(c['email'])
    return p


for art in ('dateien', 'sqlite'):
    for weg in ('0→2', '1→2'):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t); d = aufbau2(t); i = t / 'daten-intern'; w = f'{art} {weg}'
            if art == 'sqlite':
                subprocess.run([sys.executable, str(DB), 'migrate', str(d), '--offline'], check=True, capture_output=True)
            if weg == '1→2':
                code, out = lauf('trennen', str(d), str(i), '--offline', '--stufe', '1')
                check(f'{w}: Stufe 1 lässt Kunden, Bestand und Postfach im gemeinsamen Ordner', code == 0 and (d / '.daten-getrennt').read_text() == '1\n'
                      and dt.dok_lesen(d, 'kunden')['customers'][0] == KUNDE and dt.dok_lesen(d, 'bestand') is not None and dt.dok_lesen(i, 'kundenstamm') is None, out)
                r = php_lib("echo json_encode([customers_load()['customers'][0]['email'] ?? null, order_settings()['to'], stock_codes()]);", d)
                check(f'{w}: auf Stufe 1 arbeitet auch die Kundenseite wie bisher (alle Kundenfelder, Empfänger, Bestand)',
                      json.loads(r or 'null') == ['einkauf@test.invalid', ['team@test.invalid', 'chef@test.invalid'], {'100': True}], r)
            code, out = lauf('pruefen', str(d), str(i))
            check(f'{w}: pruefen nennt die Umstellung', code == 0 and 'Trennstufe' in out and 'kundenstamm' in out and 'kürzen' in out, out)
            code, out = lauf('trennen', str(d), str(i), '--offline')
            check(f'{w}: trennen auf Stufe 2', code == 0 and 'Stufe 2' in out and (d / '.daten-getrennt').read_text() == '2\n' and (i / '.daten-intern').read_text() == '2\n', out)
            k = dt.dok_lesen(d, 'kunden')
            check(f'{w}: gemeinsames Kundendokument nur mit Portalfeldern und gekürzter Adresse', k['rev'] == 5 and k['customers'] == [portal(KUNDE), portal(KUNDE2)]
                  and k['customers'][0]['emailMaske'] == 'e•••@test.invalid' and 'wawi' not in json.dumps(k) and 'Weg 1' not in json.dumps(k), k)
            st = dt.dok_lesen(i, 'kundenstamm')
            check(f'{w}: kundenstamm (intern) mit allen übrigen Feldern', st['customers']['kaaaaaaaaaaaa']['wawi'] == KUNDE['wawi']
                  and st['customers']['kaaaaaaaaaaaa']['email'] == KUNDE['email'] and 'login' not in st['customers']['kaaaaaaaaaaaa'], st)
            check(f'{w}: Empfänger der Bestellwünsche nur innen, außen nur ihre Anzahl', dt.dok_lesen(d, 'bestellung') == {'enabled': True, 'copy': True, 'updatedAt': 'y', 'updatedBy': 'admin', 'empfaenger': 2}
                  and dt.dok_lesen(i, 'bestellung-empfaenger')['to'] == ['team@test.invalid', 'chef@test.invalid'])
            check(f'{w}: Bestand, Stammdaten, Postfach, Benachrichtigungen in daten-intern', all(dt.dok_lesen(d, n) is None and dt.dok_lesen(i, n) is not None
                  for n in ('bestand', 'stammdaten', 'mailkonto', 'benachrichtigungen')))
            # Anwendung: Mitarbeiterseite liest zusammengeführt, Kundenseite nur Portalfelder
            r = php_lib("echo json_encode([customers_load()['customers'][0], order_settings()['to'], order_settings()['empfaenger'], kunden_geteilt()]);", d, i)
            v = json.loads(r or 'null') or [None]
            check(f'{w}: Mitarbeiterseite sieht den Kunden vollständig, Empfänger und Anzahl', v[0] == {**KUNDE, 'emailMaske': 'e•••@test.invalid'} and v[1:] == [['team@test.invalid', 'chef@test.invalid'], 2, True], r)
            r = php_lib("echo json_encode([customers_load()['customers'][0], order_settings()['to'], order_settings()['empfaenger'], kunden_email_anzeige(customers_load()['customers'][0])]);", d)
            check(f'{w}: Kundenseite sieht nur Portalfelder, keine Empfänger, nur deren Anzahl', json.loads(r or 'null') == [portal(KUNDE), [], 2, 'e•••@test.invalid'], r)
            # Auszug aus Bestand und Stammdaten: erzeugt die Mitarbeiterseite (bzw. der Postausgang), die Kundenseite liest nur ihn
            r = php_lib("echo json_encode([stock_codes(), artikelauszug()]);", d)
            check(f'{w}: Kundenseite ohne Auszug: kein Bestand bekannt (nichts ausverkauft)', json.loads(r or 'null') == [None, None], r)
            r = php_lib("echo json_encode([artikelauszug_aktualisieren(false), artikelauszug_aktualisieren(false)]);", d, i)
            check(f'{w}: Auszug wird erzeugt, unverändert nicht erneut', json.loads(r or 'null') == [True, False], r)
            a = dt.dok_lesen(d, 'artikelauszug')
            check(f'{w}: Auszug ohne Mengen, Partien und Einkaufspreise', a['lager'] == ['100'] and a['merkmale'] == {'100': {'category': 'Rind', 'origin': 'DE', 'condition': 'frisch'}}
                  and not any(x in json.dumps(a) for x in ('"kg"', 'ek', 'P1', 'gtin', '4000')), a)
            r = php_lib("echo json_encode([stock_codes(), sold_out(['code' => '0200']), sold_out(['code' => '0100'])]);", d)
            check(f'{w}: Kundenseite: Lagerliste aus dem Auszug', json.loads(r or 'null') == [{'100': True}, True, False], r)
            # Speichern: Mitarbeiterseite teilt, Kundenseite schreibt nur Portalfelder und lässt kundenstamm in Ruhe
            r = php_lib("with_lock('kunden', function () { $d = customers_load(); $d['customers'][0]['telefon'] = '040 2'; $d['customers'][0]['email'] = 'neu@test.invalid'; customers_save($d); }); echo 'ok';", d, i)
            k = dt.dok_lesen(d, 'kunden')['customers'][0]; st = dt.dok_lesen(i, 'kundenstamm')['customers']['kaaaaaaaaaaaa']
            check(f'{w}: Mitarbeiterseite speichert geteilt', r == 'ok' and 'telefon' not in k and k['emailMaske'] == 'n•••@test.invalid' and st['telefon'] == '040 2' and st['email'] == 'neu@test.invalid', (r, k, st))
            r = php_lib("with_lock('kunden', function () { $d = customers_load(); $d['customers'][0]['login']['sv'] = 9; customers_save($d); }); echo 'ok';", d)
            k = dt.dok_lesen(d, 'kunden')['customers'][0]; st2 = dt.dok_lesen(i, 'kundenstamm')['customers']['kaaaaaaaaaaaa']
            check(f'{w}: Kundenseite ändert nur den Zugang, Stammdaten bleiben', r == 'ok' and k['login']['sv'] == 9 and st2 == st and k['emailMaske'] == 'n•••@test.invalid', (r, k))
            r = php_lib("try { store_write('kundenstamm', ['customers' => []]); echo 'geschrieben'; } catch (StoreKeinZugang $e) { echo 'abgelehnt'; }", d)
            check(f'{w}: Kundenseite kann kundenstamm nicht schreiben', r == 'abgelehnt', r)
            r = php_lib("order_settings_speichern(['to' => ['neu@team.invalid']], 'admin'); echo json_encode([order_settings()['to'], order_settings()['empfaenger']]);", d, i)
            check(f'{w}: Empfänger ändern: innen die Adressen, außen die Anzahl', json.loads(r or 'null') == [['neu@team.invalid'], 1] and dt.dok_lesen(d, 'bestellung')['empfaenger'] == 1
                  and 'to' not in dt.dok_lesen(d, 'bestellung'), r)
            # Rest eines Abbruchs: interne Felder wieder im gemeinsamen Ordner, ein Kunde fehlt in kundenstamm → erneutes trennen bereinigt ohne Verlust
            kk = dt.dok_lesen(d, 'kunden'); kk['customers'].append({'id': 'kcccccccccccc', 'firma': 'Rest KG', 'email': 'rest@test.invalid', 'notiz': 'aus Abbruch'})
            dt.dok_schreiben(d, 'kunden', kk)
            code, out = lauf('trennen', str(d), str(i), '--offline')
            st = dt.dok_lesen(i, 'kundenstamm')['customers']
            check(f'{w}: erneutes trennen bereinigt Reste ohne Verlust', code == 0 and st.get('kcccccccccccc') == {'email': 'rest@test.invalid', 'notiz': 'aus Abbruch'}
                  and dt.dok_lesen(d, 'kunden')['customers'][2] == {'id': 'kcccccccccccc', 'firma': 'Rest KG', 'emailMaske': 'r•••@test.invalid'}, (out, st))
            code, out = lauf('pruefen', str(d), str(i))
            check(f'{w}: danach nichts mehr zu tun', code == 0 and not [z for z in out.splitlines() if z.startswith('  ')], out)
            # Zusammenführen: alles wieder in einem Dokument und Ordner wie vor der Trennung (mit den Änderungen von eben)
            code, out = lauf('zusammenfuehren', str(d), str(i), '--offline')
            k = dt.dok_lesen(d, 'kunden')['customers']
            check(f'{w}: zusammenführen setzt das Kundendokument wieder zusammen', code == 0 and k[0] == {**KUNDE, 'telefon': '040 2', 'email': 'neu@test.invalid', 'login': {**KUNDE['login'], 'sv': 9}}
                  and k[1] == KUNDE2 and k[2] == {'id': 'kcccccccccccc', 'firma': 'Rest KG', 'email': 'rest@test.invalid', 'notiz': 'aus Abbruch'}, (out, k))
            check(f'{w}: Bestell-Einstellungen wieder mit Adressen, Auszug entfernt, daten-intern leer', dt.dok_lesen(d, 'bestellung').get('to') == ['neu@team.invalid']
                  and 'empfaenger' not in dt.dok_lesen(d, 'bestellung') and dt.dok_lesen(d, 'artikelauszug') is None and dt.dok_lesen(d, 'bestand') is not None
                  and dt.dok_lesen(d, 'kundenstamm') is None and dt.leer(i) and not (d / '.daten-getrennt').exists())
            r = php_lib("echo json_encode([customers_load()['customers'][0]['wawi'], order_settings()['to'], stock_codes()]);", d)
            check(f'{w}: danach liest die Anwendung wieder alles aus einem Ordner', json.loads(r or 'null') == [KUNDE['wawi'], ['neu@team.invalid'], {'100': True}], r)

print(f'{ok_n}/{ok_n + fail_n} passed')
sys.exit(0 if fail_n == 0 else 1)
