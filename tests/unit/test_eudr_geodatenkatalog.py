"""Geodaten-Katalog des Container-Imports (werkzeuge/eudr_geodatenkatalog.py) – ohne Netz, mit einer kleinen erfundenen
Tabelle im Aufbau der Metadatenbank GEOS-EUDR (tests/fixtures/containerimport/geodatenkatalog/).

    python3 tests/unit/test_eudr_geodatenkatalog.py

Prüft: gültige Datei → Einträge mit deutschen Schlüsseln, „NR“/„NA“ erkennbar, leere Zellen null, Einstufung EUDR-konform,
Verweise mit Beschriftung, Hinweis in eckigen Klammern abgetrennt, Aufzählungen je Zeile; zweiter Lauf ergibt dieselbe
Datei; weiteres Thema ergänzt, ohne das erste zu ändern; Abbruch ohne zu schreiben bei geänderten Spalten, neuer
Hauptversion, unbekannter Einstufung, doppelter Item-ID, fehlendem Zitiervorschlag (neues Thema oder neue Fassung), fehlendem
Commit; Zeilenumbruch in einer Zelle mit Anführungszeichen bleibt erhalten. Dazu der Aufbau des eingecheckten Katalogs
(Pflichtfelder, Anzahl je Thema, eindeutige Kennungen, Verweise mit https), Quelle und Lizenztext daneben – ohne feste
Anzahl, damit eine neue Fassung den Test nicht bricht.
"""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FIX = REPO / 'tests/fixtures/containerimport/geodatenkatalog/ForestCover_TreeExtent_GeosEUDR_Thuenen_v1.0.tsv'
spec = importlib.util.spec_from_file_location('eudr_geodatenkatalog', REPO / 'werkzeuge/eudr_geodatenkatalog.py')
W = importlib.util.module_from_spec(spec); spec.loader.exec_module(W)
res = []


def ok(name, cond, info=''):
    res.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(info)[:400]) if info and not cond else ''))


def lauf(*args):
    """Werkzeug aufrufen → (Exit-Code, Fehlerausgabe)."""
    fehler = io.StringIO()
    with contextlib.redirect_stderr(fehler), contextlib.redirect_stdout(io.StringIO()):
        code = W.main([str(a) for a in args])
    return code, fehler.getvalue()


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp); ziel = tmp / 'katalog.json'
    basis = ['--ziel', ziel, '--abgerufen', '2026-11-20', '--commit', '4b95506']
    code, f = lauf(FIX, *basis)
    ok('ohne Zitiervorschlag für ein neues Thema: Abbruch, nichts geschrieben', code == 1 and 'Zitiervorschlag' in f and not ziel.exists(), f)
    code, f = lauf(FIX, *basis, '--zitat', 'Muster (2026). Testkatalog (Version 1.0).')
    k = json.loads(ziel.read_text(encoding='utf-8')) if ziel.exists() else {}
    ok('gültige Datei: geschrieben', code == 0 and [e['id'] for e in k.get('eintraege', [])] == ['TST01', 'TST02'], f)
    t, e1, e2 = k['themen'][0], k['eintraege'][0], k['eintraege'][1]
    ok('Thema, Fassung, Commit, Abrufdatum und Zitiervorschlag', t == {'id': 'ForestCover_TreeExtent', 'name': 'Wald und Baumbedeckung (Forest/Tree Cover)', 'version': '1.0',
       'datei': FIX.name, 'eintraege': 2, 'quelleCommit': '4b95506', 'abgerufen': '2026-11-20', 'zitiervorschlag': 'Muster (2026). Testkatalog (Version 1.0).'}, t)
    ok('Quelle mit Lizenz MIT und Urhebern', k['quelle']['lizenz'] == 'MIT' and 'Thünen' in k['quelle']['urheber'] and k['schema'] == 1)
    ok('deutsche Schlüssel, Einstufung Yes → ja, No/Unclear → nein_unklar', (e1['eudrKonform'], e2['eudrKonform'], e1['aufloesungM'], e2['aufloesungM']) == ('ja', 'nein_unklar', '10', '~30'))
    ok('„NR“ und „NA“ bleiben erkennbar, leere Zellen werden null', (e1['genauigkeit']['paUa'], e1['genauigkeit']['zusatz'], e1['genauigkeit']['weitere'], e2['walddefinition']) == ('NR', 'NA', None, 'NR'))
    ok('Verweise mit Beschriftung vor der Adresse', e1['links']['gee'] == [{'text': 'V1', 'url': 'https://example.org/gee/v1'}, {'text': 'V2', 'url': 'https://example.org/gee/v2'}]
       and e1['links']['andere'] == [] and e1['links']['veroeffentlichung'] == [{'text': 'v2', 'url': 'https://example.org/bericht'}], e1['links'])
    ok('Rest hinter der letzten Adresse hängt an ihr; Trenner und Satzzeichen fallen weg', e2['links']['andere'] == [{'text': 'Info', 'url': 'https://example.org/info'}, {'text': 'Download – noch nicht in GEE', 'url': 'https://example.org/dl'}]
       and e2['links']['gee'] == [{'text': None, 'url': 'https://example.org/a'}, {'text': None, 'url': 'https://example.org/b#x=1;y=2'}], e2['links'])
    ok('Anmerkung in eckigen Klammern als Hinweis abgetrennt', (e2['name'], e2['hinweis'], e1['hinweis']) == ('Testverlust v1.0', 'Nur Verlust, kein Bestand.', None), (e2['name'], e2['hinweis']))
    ok('Aufzählungspunkte je auf einer Zeile', e1['grenzen'] == '• Erster Punkt.\n• Zweiter Punkt.', e1['grenzen'])
    ok('Jahre als Text wie in der Quelle', (e2['vonJahr'], e2['bisJahr']) == ('2000', '2023 (bis 2025 bei GFW)'))
    vorher = ziel.read_bytes()
    ok('zweiter Lauf: dieselbe Datei, Zitiervorschlag bleibt', lauf(FIX, *basis)[0] == 0 and ziel.read_bytes() == vorher)

    # neue Fassung desselben Themas: der alte Zitiervorschlag gehört zur alten Fassung
    neu = tmp / FIX.name.replace('v1.0', 'v1.1'); shutil.copy(FIX, neu)
    code, f = lauf(neu, *basis)
    ok('neue Fassung v1.1 ohne --zitat: Abbruch mit Hinweis auf die Fassung, nichts geschrieben', code == 1 and 'neue Fassung v1.1 (bisher v1.0)' in f and ziel.read_bytes() == vorher, f)
    code, f = lauf(neu, *basis, '--zitat', 'Muster (2026). Testkatalog (Version 1.1).')
    t = json.loads(ziel.read_text(encoding='utf-8'))['themen'][0]
    ok('neue Fassung mit --zitat: übernommen', code == 0 and (t['version'], t['zitiervorschlag']) == ('1.1', 'Muster (2026). Testkatalog (Version 1.1).'), (f, t))
    ziel.write_bytes(vorher)
    code, f = lauf(FIX, '--ziel', ziel, '--zitat', 'x')
    ok('ohne --commit: Abbruch, nichts geschrieben (Herkunft nie still leer)', code == 1 and '--commit' in f and ziel.read_bytes() == vorher, f)

    # Zelle mit Anführungszeichen über zwei Zeilen: der Umbruch bleibt, die Zeile zählt einmal
    mehrzeilig = tmp / 'mehrzeilig' / FIX.name; mehrzeilig.parent.mkdir()
    mehrzeilig.write_text(FIX.read_text(encoding='utf-8').replace('\tForest, Non-forest\t', '\t"Forest,\nNon-forest"\t', 1), encoding='utf-8')
    code, f = lauf(mehrzeilig, '--ziel', tmp / 'mehrzeilig.json', '--commit', '4b95506', '--zitat', 'x')
    km = json.loads((tmp / 'mehrzeilig.json').read_text(encoding='utf-8')) if code == 0 else {}
    ok('mehrzeilige Zelle: Zeilenumbruch erhalten, zwei Einträge', code == 0 and [e['klassen'] for e in km['eintraege']][0] == 'Forest,\nNon-forest' and len(km['eintraege']) == 2, (f, km.get('eintraege', [{}])[0].get('klassen')))

    # weiteres Thema mit gleichem Aufbau: ergänzt, das erste bleibt unverändert
    zweites = tmp / 'Deforestation_TreeLoss_GeosEUDR_Thuenen_v1.2.tsv'
    zweites.write_text(FIX.read_text(encoding='utf-8').replace('TST01', 'DEF01').replace('TST02', 'DEF02'), encoding='utf-8')
    code, f = lauf(zweites, *basis, '--zitat', 'Muster (2026). Entwaldung (Version 1.2).')
    k2 = json.loads(ziel.read_text(encoding='utf-8'))
    ok('weiteres Thema ergänzt, erstes unverändert', code == 0 and [t['id'] for t in k2['themen']] == ['Deforestation_TreeLoss', 'ForestCover_TreeExtent']
       and [e['id'] for e in k2['eintraege']] == ['DEF01', 'DEF02', 'TST01', 'TST02'] and k2['themen'][0]['version'] == '1.2'
       and [e for e in k2['eintraege'] if e['thema'] == 'ForestCover_TreeExtent'] == k['eintraege'], f)
    ziel.write_bytes(vorher)

    def abbruch(name, dateiname, aendern, erwartet):
        p = tmp / dateiname
        p.write_text(aendern(FIX.read_text(encoding='utf-8')), encoding='utf-8')
        code, f = lauf(p, *basis)
        ok(name, code == 1 and erwartet in f and ziel.read_bytes() == vorher, f)

    abbruch('Spalte umbenannt: Abbruch mit Namen der Spalte, nichts geschrieben', FIX.name, lambda s: s.replace('Reported limitations', 'Known limitations', 1), "fehlt: ['Reported limitations']")
    abbruch('Spalte dazu: Abbruch', FIX.name, lambda s: s.replace('Reported limitations', 'Reported limitations\tNeue Spalte', 1), "neu: ['Neue Spalte']")
    abbruch('Spalten vertauscht: Abbruch', FIX.name, lambda s: s.replace('Start Year\tEnd Year', 'End Year\tStart Year', 1), 'Reihenfolge')
    abbruch('neue Hauptversion v2.0: Abbruch', FIX.name.replace('v1.0', 'v2.0'), lambda s: s, 'Hauptversion v2.0')
    abbruch('unbekannte Einstufung „EUDR forest definition conform?“: Abbruch', FIX.name, lambda s: s.replace('\tNo/Unclear\t', '\tMaybe\t'), "'Maybe'")
    abbruch('doppelte Item-ID: Abbruch', FIX.name, lambda s: s.replace('TST02', 'TST01'), 'doppelt')
    abbruch('fremder Dateiname: Abbruch', 'katalog.tsv', lambda s: s, 'Muster')
    ok('ungültiger Commit: Abbruch', lauf(FIX, '--ziel', ziel, '--commit', 'main; rm', '--zitat', 'x')[0] == 1 and ziel.read_bytes() == vorher)

# ---------- eingecheckter Katalog ----------
ort = REPO / 'app/api/module/containerimport'
k = json.loads((ort / 'geodatenkatalog.json').read_text(encoding='utf-8'))
THEMA = {'id', 'name', 'version', 'datei', 'eintraege', 'quelleCommit', 'abgerufen', 'zitiervorschlag'}
EINTRAG = {'id', 'thema', 'name', 'hinweis', 'hersteller', 'zitat', 'links', 'klassen', 'walddefinition', 'eudrKonform', 'ausdehnung', 'aufloesungM',
           'vonJahr', 'bisJahr', 'zeitlich', 'sensor', 'methode', 'kategorie', 'validierung', 'genauigkeit', 'grenzen'}
ids = [e['id'] for e in k['eintraege']]
ok('eingecheckter Katalog: Themen mit Fassung, Commit und Zitiervorschlag', k['schema'] == 1 and k['themen'] and all(set(t) == THEMA and t['version'] and t['zitiervorschlag']
   and W.re.fullmatch(r'[0-9a-f]{7,40}', t['quelleCommit'] or '') for t in k['themen']), k['themen'])
ok('eingecheckter Katalog: Einträge mit allen Feldern, Kennung eindeutig, Thema bekannt, Einstufung bekannt',
   ids and len(set(ids)) == len(ids) and all(set(e) == EINTRAG and e['thema'] in {t['id'] for t in k['themen']} and e['eudrKonform'] in W.KONFORM.values() for e in k['eintraege']))
ok('eingecheckter Katalog: Anzahl = Summe der Einträge je Thema', len(ids) == sum(t['eintraege'] for t in k['themen'])
   and all(t['eintraege'] == sum(e['thema'] == t['id'] for e in k['eintraege']) for t in k['themen']))
ok('Lizenztext (MIT, Thünen-Institut) liegt daneben', (ort / k['quelle']['lizenzdatei']).read_text(encoding='utf-8').startswith('MIT License')
   and 'Thünen-Institute' in (ort / k['quelle']['lizenzdatei']).read_text(encoding='utf-8'))
ok('alle Verweise mit https', all(l['url'].startswith('https://') for e in k['eintraege'] for g in e['links'].values() for l in g))

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
