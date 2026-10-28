#!/usr/bin/env python3
"""Adressverzeichnis der CRM-Karte: Aufbau (deploy/karte/adressen.py) und Nachschlagen (app/api/lib/adressen.php).

Prüft: gleiche Schreibweisen-Regeln in Python und PHP (tests/fixtures/karte/normalisierung.json), Zerlegen des
Straßenfelds, Aufbau aus OpenStreetMap-Daten (tests/fixtures/karte/adressen.osm, braucht pyosmium) und aus Testdaten
(--json), Genauigkeit Haus/Straße, Rückfälle (andere PLZ, ohne PLZ, unbekannt, ohne Datei).

  python3 tests/unit/test_adressen.py
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'deploy', 'karte'))
import adressen  # noqa: E402

FIX = os.path.join(REPO, 'tests', 'fixtures', 'karte')
PASS = FAIL = 0


def check(name, ok, info=''):
    global PASS, FAIL
    if ok:
        PASS += 1; print('PASS', name)
    else:
        FAIL += 1; print('FAIL', name, info)


def php(eingabe, db):
    env = {**os.environ, 'WA_ADRESSEN': db}
    r = subprocess.run(['php', os.path.join(REPO, 'tests', 'unit', 'adressen.php')], input=json.dumps(eingabe), capture_output=True, text=True, env=env, check=True)
    return json.loads(r.stdout)


with open(os.path.join(FIX, 'normalisierung.json'), encoding='utf-8') as f:
    V = json.load(f)

# 1. Schreibweisen: Python und PHP liefern dasselbe wie die Prüffälle
py = {'strasse': adressen.norm_strasse, 'text': adressen.norm_text, 'nr': adressen.norm_nr}
for art, f in py.items():
    falsch = [(e, f(e), s) for e, s in V[art] if f(e) != s]
    check(f'Python: Schreibweise {art} wie die Prüffälle', not falsch, falsch)
TEILEN = [['Musterstraße 10', ['Musterstraße', '10']], ['Musterstr. 12 a', ['Musterstr.', '12 a']], ['Am Markt 3-5', ['Am Markt', '3-5']],
          ['Straße des 17. Juni 5', ['Straße des 17. Juni', '5']], ['Musterstraße', ['Musterstraße', '']], ['Hauptstraße 7/1', ['Hauptstraße', '7/1']],
          ['Beispielweg, 4', ['Beispielweg', '4']], ['', ['', '']]]

with tempfile.TemporaryDirectory() as t:
    leer = os.path.join(t, 'fehlt.sqlite')
    r = php({'norm': {a: [e for e, _ in V[a]] for a in py}, 'teilen': [e for e, _ in TEILEN], 'punkte': [['Musterstraße 10', '20095', 'Hamburg']]}, leer)
    for art in py:
        falsch = [(e, g, s) for (e, s), g in zip(V[art], r['norm'][art]) if g != s]
        check(f'PHP: Schreibweise {art} wie die Prüffälle (gleich wie beim Aufbau)', not falsch, falsch)
    falsch = [(e, g, s) for (e, s), g in zip(TEILEN, r['teilen']) if g != s]
    check('PHP: Straßenfeld in Straße und Hausnummer zerlegt', not falsch, falsch)
    check('ohne Adressverzeichnis: kein Punkt, kein Stand (Karte nimmt den PLZ-Mittelpunkt)', r['punkte'] == [None] and r['stand'] is None, r)

    # 2. Aufbau aus OpenStreetMap-Daten (zwei Durchläufe mit pyosmium)
    try:
        import osmium  # noqa: F401
        mit_osm = True
    except ImportError:
        mit_osm = False
    db = os.path.join(t, 'adressen.sqlite')
    if mit_osm:
        subprocess.run([sys.executable, os.path.join(REPO, 'deploy', 'karte', 'adressen.py'), os.path.join(FIX, 'adressen.osm'), db], check=True, capture_output=True)
        P = [['Musterstraße 10', '20095', 'Hamburg'],     # Gebäude: Mitte aus gegenüberliegenden Ecken
             ['Musterstr. 12a', '20095', 'Hamburg'],       # Punkt, Nummer „12 A“ in OpenStreetMap
             ['Musterstraße 12', '20095', 'Hamburg'],      # ohne Zusatz nicht vorhanden → Straße
             ['Beispielweg 5', '20095', 'Hamburg'],        # zweite Nummer an einem Objekt („3;5“)
             ['Beispielweg 3 b', '20095', 'Hamburg'],      # 3b unbekannt → 3
             ['Am Testhof 2', '20095', 'Hamburg'],         # in OpenStreetMap ohne PLZ, über den Ort
             ['Max-Planck-Straße 4', '10117', 'Berlin'],   # „Max-Planck-Str.“ in OpenStreetMap
             ['Musterstraße 10', '10117', 'Berlin'],       # gleiche Straße, andere PLZ und anderer Ort → unbekannt
             ['Unbekannter Weg 1', '20095', 'Hamburg'],
             ['Musterstraße 99', '20095', 'Hamburg']]      # Objekt ohne PLZ/Ort wurde verworfen → Straße
        r = php({'punkte': P}, db)
        e = r['punkte']
        nah = lambda p, lat, lon: p is not None and abs(p['lat'] - lat) < 0.00002 and abs(p['lon'] - lon) < 0.00002  # noqa: E731
        check('OSM: Gebäude auf Hausnummer genau (Mitte des Gebäudes)', nah(e[0], 53.5501, 9.9902) and e[0]['genau'] == 'haus', e[0])
        check('OSM: Punkt-Adresse, Nummer mit Zusatz in anderer Schreibweise', nah(e[1], 53.5510, 9.9910) and e[1]['genau'] == 'haus', e[1])
        check('OSM: unbekannte Nummer → Straßenmitte', e[2] is not None and e[2]['genau'] == 'strasse', e[2])
        check('OSM: mehrere Nummern an einem Objekt einzeln auffindbar', nah(e[3], 53.5520, 9.9920) and e[3]['genau'] == 'haus', e[3])
        check('OSM: unbekannter Zusatz → Nummer ohne Zusatz', nah(e[4], 53.5520, 9.9920) and e[4]['genau'] == 'haus', e[4])
        check('OSM: Adresse ohne PLZ über den Ort gefunden', nah(e[5], 53.5530, 9.9930) and e[5]['genau'] == 'haus', e[5])
        check('OSM: Abkürzung „Str.“ und Bindestriche gleichwertig', nah(e[6], 52.5200, 13.4050), e[6])
        check('OSM: gleiche Straße in anderer PLZ und anderem Ort wird nicht verwechselt', e[7] is None, e[7])
        check('OSM: unbekannte Straße → kein Punkt', e[8] is None, e[8])
        check('OSM: Objekte ohne PLZ und Ort nicht aufgenommen', e[9] is not None and e[9]['genau'] == 'strasse', e[9])
        check('OSM: Stand mit Anzahl der Adressen', r['stand'] and r['stand']['adressen'] == 6, r['stand'])
    else:
        print('HINWEIS pyosmium fehlt (pip install osmium) – Aufbau aus OpenStreetMap-Daten nicht geprüft')
        if os.environ.get('CI'):
            check('pyosmium in der CI vorhanden (tests/requirements.txt)', False)

    # 3. Aufbau aus Testdaten (ohne pyosmium; so entsteht das Verzeichnis der E2E-Tests)
    db2 = os.path.join(t, 'test.sqlite')
    subprocess.run([sys.executable, os.path.join(REPO, 'deploy', 'karte', 'adressen.py'), '--json', os.path.join(FIX, 'adressen.json'), db2], check=True, capture_output=True)
    with open(os.path.join(FIX, 'adressen.json'), encoding='utf-8') as f:
        J = json.load(f)['adressen']
    r = php({'punkte': [[f"{a['strasse']} {a['nr']}", a['plz'], a['ort']] for a in J]}, db2)
    check('Testdaten: jede Adresse auf Hausnummer genau wiedergefunden', all(p and p['genau'] == 'haus' and abs(p['lat'] - a['lat']) < 0.00002 and abs(p['lon'] - a['lon']) < 0.00002 for p, a in zip(r['punkte'], J)), r['punkte'])
    # Unbekanntes Format wird nicht gelesen (Rückfall auf den PLZ-Mittelpunkt statt falscher Punkte)
    import sqlite3
    c = sqlite3.connect(db2); c.execute("UPDATE info SET wert = '99' WHERE schluessel = 'format'"); c.commit(); c.close()
    r = php({'punkte': [[f"{J[0]['strasse']} {J[0]['nr']}", J[0]['plz'], J[0]['ort']]]}, db2)
    check('unbekanntes Format der Datei: wird nicht genutzt', r['punkte'] == [None] and r['stand'] is None, r)

print(f'{PASS}/{PASS + FAIL} passed')
sys.exit(1 if FAIL else 0)
