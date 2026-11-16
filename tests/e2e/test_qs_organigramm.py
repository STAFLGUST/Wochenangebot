"""Qualitätssicherung – Organigramm im QM-System (app/api/module/qs/organigramm.php, Aktionen qs_organigramm_save und
qs_organigramm_vorschau, Oberfläche app/module/qs/organigramm.js). Was geprüft wird: tests/README.md, Gruppe qs_organigramm.
Nur erfundene Testdaten.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH, storage_raw, storage_write

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HIER, '..', '..'))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
HEUTE = datetime.date.today()
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:500]) if i else ''))


def de(iso):
    return f'{iso[8:10]}.{iso[5:7]}.{iso[0:4]}'


def roh(cli, query):
    """GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)"""
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def pdf_text(raw):
    """Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi – je Seite eine Liste von Zeilen"""
    seiten = []
    for m in re.finditer(rb'stream\n(.*?)\nendstream', raw, re.S):
        try:
            s = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        seiten.append([re.sub(rb'\\(.)', rb'\1', t.group(1)).decode('cp1252') for t in re.finditer(rb'\(((?:\\.|[^\\)])*)\) Tj', s)])
    return seiten


# ── Anordnung und PDF ohne Server: zufällige Bäume und ein realistisches Organigramm mit 37 Stellen ──
PHP = r"""define('WA_API', 1);
$CFG = ['company' => 'Testfirma GmbH'];
require $argv[1] . '/app/api/module/qs/qs.php';
require $argv[1] . '/app/api/module/qs/organigramm.php';
require_once $argv[1] . '/app/api/lib/pdf.php';
$e = 0.01; $B = QS_OG_KASTEN_BREITE; $fehler = [];
mt_srand(11);
for ($lauf = 0; $lauf < 1500; $lauf++) {
    $kn = []; $hoehe = []; $n = mt_rand(1, 30);
    for ($i = 0; $i < $n; $i++) {
        $linien = array_values(array_filter($kn, fn($k) => $k['art'] === 'linie'));
        $ueber = $i === 0 || mt_rand(0, 9) === 0 ? '' : $linien[mt_rand(0, count($linien) - 1)]['id'];
        $kn[] = ['id' => "k$i", 'ueber' => $ueber, 'art' => $ueber !== '' && mt_rand(0, 3) === 0 ? 'stab' : 'linie'];
        $hoehe["k$i"] = (float)mt_rand(18, 70);
    }
    $l = qs_organigramm_lage($kn, $hoehe);
    $box = fn($id) => $l['kaesten'][$id] + ['h' => $hoehe[$id]];
    $auf = fn($x, $y, $b) => ($b['y'] - $e <= $y && $y <= $b['y'] + $b['h'] + $e) && (abs($x - $b['x']) < $e || abs($x - $b['x'] - $B) < $e)
        || ($b['x'] - $e <= $x && $x <= $b['x'] + $B + $e) && (abs($y - $b['y']) < $e || abs($y - $b['y'] - $b['h']) < $e);
    $enden = array_merge(...array_map(fn($s) => [[$s[0], $s[1]], [$s[2], $s[3]]], $l['linien']));
    $unten = fn($b) => (bool)array_filter($enden, fn($p) => abs($p[1] - $b['y'] - $b['h']) < $e && $p[0] > $b['x'] - $e && $p[0] < $b['x'] + $B + $e);
    if (count($l['kaesten']) !== $n) { $fehler[] = "Lauf $lauf: Kästen fehlen"; continue; }
    foreach ($kn as $a) {
        $p = $box($a['id']);
        if ($p['x'] < -$e || $p['y'] < -$e || $p['x'] + $B > $l['b'] + $e || $p['y'] + $p['h'] > $l['h'] + $e) $fehler[] = "Lauf $lauf: {$a['id']} außerhalb";
        foreach ($kn as $b) if ($a['id'] < $b['id']) {
            $q = $box($b['id']);
            if ($p['x'] < $q['x'] + $B - $e && $q['x'] < $p['x'] + $B - $e && $p['y'] < $q['y'] + $q['h'] - $e && $q['y'] < $p['y'] + $p['h'] - $e) $fehler[] = "Lauf $lauf: {$a['id']}/{$b['id']} überlappen";
        }
        if ($a['ueber'] === '') continue;
        $o = $box($a['ueber']); $mitte = $o['x'] + $B / 2;
        if ($p['y'] < $o['y'] + $o['h'] - $e) $fehler[] = "Lauf $lauf: {$a['id']} nicht unter {$a['ueber']}";
        if ($a['art'] === 'stab' && !($p['x'] + $B <= $mitte + $e || $p['x'] >= $mitte - $e)) $fehler[] = "Lauf $lauf: Stabsstelle {$a['id']} nicht seitlich";
        if (!array_filter($enden, fn($q) => $auf($q[0], $q[1], $p))) $fehler[] = "Lauf $lauf: {$a['id']} ohne Linie";
        if ($a['art'] === 'linie' && !$unten($o)) $fehler[] = "Lauf $lauf: {$a['ueber']} ohne Linie nach unten";
    }
}
$stamm = ['personen' => [['id' => 'GF', 'name' => 'Gerd Führer'], ['id' => 'QB', 'name' => 'Quinn Beispiel'], ['id' => 'LN', 'name' => 'Maximiliane Musterfrau-Beispielhausen']], 'kapitel' => []];
$k = fn($id, $t, $u = '', $a = 'linie', $p = [], $v = '') => ['id' => $id, 'titel' => $t, 'ueber' => $u, 'art' => $a, 'personen' => $p, 'vertretung' => $v, 'hinweis' => ''];
$kn = [$k('gf', 'Geschäftsführung', '', 'linie', ['GF'], 'QB')];
foreach (['Qualitätsmanagementbeauftragte', 'HACCP-Teamleitung', 'Food Defense', 'Fachkraft für Arbeitssicherheit'] as $i => $t) $kn[] = $k("s$i", $t, 'gf', 'stab', ['QB']);
foreach (['Einkauf', 'Verkauf', 'Produktion', 'Lager', 'Versand', 'Buchhaltung', 'Personal', 'Technik'] as $i => $t) {
    $kn[] = $k("b$i", $t, 'gf', 'linie', ['GF'], 'QB');
    for ($j = 0; $j < 3; $j++) $kn[] = $k("b{$i}u$j", "$t Team " . ($j + 1), "b$i", 'linie', [$j === 2 ? 'LN' : 'QB'], 'GF');
}
$d = ['nr' => '1.2-L02', 'art' => 'L', 'kapitel' => '1.2', 'titel' => 'Organigramm der Standorte Nord, Süd und West mit allen Stabsstellen, Bereichen und Teams einschließlich Vertretungen'];
$v = ['nr' => 1, 'datum' => '2026-11-16', 'organigramm' => qs_organigramm_pruefen(['knoten' => $kn], null, $stamm),
      'erstellt' => ['von' => 'Maximiliane Musterfrau-Beispielhausen', 'vonId' => 'x'], 'geprueft' => ['von' => 'Quinn QMB', 'vonId' => 'y'], 'freigegeben' => ['von' => 'Quinn QMB', 'vonId' => 'y']];
$pdf = qs_organigramm_pdf($d, $v, $stamm);
file_put_contents($argv[2], $pdf);
preg_match('/stream\n(.*?)\nendstream/s', substr($pdf, strpos($pdf, '/FlateDecode')), $m);
preg_match_all('/F(\d) ([\d.]+) Tf [\d. ]+ rg ([\d.]+) ([\d.]+) Td \(((?:\\\\.|[^\\\\)])*)\) Tj/', zlib_decode($m[1]), $t, PREG_SET_ORDER);
$texte = array_map(function ($x) {
    $s = iconv('Windows-1252', 'UTF-8', preg_replace('/\\\\(.)/s', '$1', $x[5]));
    return ['text' => $s, 'g' => (float)$x[2], 'x' => (float)$x[3], 'y' => 595.28 - (float)$x[4], 'b' => Pdf::width($s, (float)$x[2], $x[1] === '2')];
}, $t);
echo json_encode(['fehler' => array_slice($fehler, 0, 5), 'stellen' => count($kn), 'texte' => $texte], JSON_UNESCAPED_UNICODE);"""
p = subprocess.run(['php', '-r', PHP, REPO, os.path.join(SH, 'qs_organigramm_37_stellen.pdf')], capture_output=True, text=True)
try:
    kern = json.loads(p.stdout)
except ValueError:
    print(p.stdout[-800:], p.stderr[-800:]); kern = {'fehler': ['kein Ergebnis'], 'stellen': 0, 'texte': []}
check('Anordnung, 1500 zufällige Bäume: keine Überlappung, Stabsstellen seitlich der Mitte, Unterstellen darunter, alles verbunden und innerhalb', not kern['fehler'], kern['fehler'])
texte = kern['texte']
klein = min((t['g'] for t in texte), default=0)
check(f'PDF mit {kern["stellen"]} Stellen auf A4 quer: kleinste Schrift mindestens 6 pt', kern['stellen'] == 37 and klein >= 6, klein)
titel = max(texte, key=lambda t: t['g'], default={'x': 0, 'g': 0})
check('PDF: langer Titel verkleinert, läuft nicht ins Logo', 138 <= titel['x'] and titel['g'] < 15, titel)
zeilen = {}
for t in texte:
    zeilen.setdefault(round(t['y'], 1), []).append(t)
ueber = [(a['text'], b['text']) for z in zeilen.values() for a, b in zip(sorted(z, key=lambda t: t['x']), sorted(z, key=lambda t: t['x'])[1:]) if a['x'] + a['b'] > b['x'] + 0.5]
check('PDF: kein Text überdeckt einen anderen (langer Name im Fuß gekürzt)', not ueber and any(t['text'].endswith('…') and t['y'] > 560 for t in texte), ueber[:3])
check('PDF: zu lange Wörter mit Trennstrich', {'Qualitätsmanagement-', 'beauftragte'} <= {t['text'] for t in texte})

# ── Nutzer und Grunddaten ──
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten', 'qs.freigeben']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, V, O, N = K['lisa'], K['bernd'], K['quinn'], K['vera'], K['otto'], Client('198.51.100.40')
check('Datenpaket (erfunden) übernommen', V.call('qs_import', {'paket': json.load(open(PAKET_DATEI, encoding='utf-8')), 'ersetzen': True})[0] == 200)
start = V.call('qs_start')[1]
PERSONEN = start['personen'] + [{'id': 'HT', 'name': 'Hanna Team', 'funktion': 'HACCP-Teamleitung'}, {'id': 'FD', 'name': 'Fiete Defense', 'funktion': 'Food Defense'}]
st, r = V.call('qs_stamm_save', {'kapitel': start['kapitel'] + [{'id': '1.2', 'titel': 'Geschäftsleitung'}], 'personen': PERSONEN})
check('Kapitel 1.2 und zwei Personen ergänzt', st == 200 and len(r['personen']) == 6, r)
st, r = Be.call('qs_dokument_save', {'kapitel': '1.2', 'art': 'L', 'nr': '1.2-L02', 'titel': 'Organigramm', 'aenderungen': 'Neu angelegt'})
DOK = r.get('dokument', {})
check('gelenktes Dokument 1.2-L02 mit Entwurf angelegt', st == 200 and DOK['nr'] == '1.2-L02' and DOK['versionen'][0]['status'] == 'entwurf', r)


def dok(cli=L, did=None):
    return {x['id']: x for x in cli.call('qs_start')[1]['dokumente']}[did or DOK['id']]


def knoten(id_, titel, ueber='', art='linie', personen=(), vertretung='', hinweis=''):
    return {'id': id_, 'titel': titel, 'ueber': ueber, 'art': art, 'personen': list(personen), 'vertretung': vertretung, 'hinweis': hinweis}


def speichern(cli, liste, d=None):
    d = d or dok()
    return cli.call('qs_organigramm_save', {'dokument': d['id'], 'rev': d['rev'], 'organigramm': {'knoten': liste}})


def schritt(cli, s, **mehr):
    return cli.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': s, **mehr})[0]


def vorschau(cli, did=None):
    return roh(cli, f'qs_organigramm_vorschau&dokument={did or DOK["id"]}')


STRUKTUR = [knoten('gf', 'Geschäftsführung', personen=['GF'], vertretung='QB'),
            knoten('qmb', 'Qualitätsmanagementbeauftragte', 'gf', 'stab', ['QB'], 'QV'),
            knoten('haccp', 'HACCP-Teamleitung', 'gf', 'stab', ['HT']),
            knoten('fd', 'Food Defense', 'gf', 'stab', ['FD']),
            knoten('asi', 'Fachkraft für Arbeitssicherheit', 'gf', 'stab', hinweis='extern'),
            knoten('ek', 'Einkauf', 'gf', personen=['EK']),
            knoten('qs', 'Qualitätssicherung', 'gf', personen=['QB', 'QV']),
            knoten('lager', 'Lager und Versand', 'gf'),
            knoten('kom', 'Kommissionierung', 'lager')]

# ── Rechte ──
check('ohne Anmeldung 401, ohne QM-Recht 403, nur ansehen 403', N.call('qs_organigramm_save', {'dokument': DOK['id']})[0] == 401
      and speichern(O, STRUKTUR, DOK)[0] == 403 and speichern(L, STRUKTUR, DOK)[0] == 403)
check('nur per POST (405)', Be.call('qs_organigramm_save')[0] == 405)

# ── Anlegen im Entwurf ──
st, r = speichern(Be, STRUKTUR)
v = r.get('dokument', {}).get('versionen', [{}])[0]
check('angelegt: Struktur im Entwurf, Reihenfolge wie gesendet, ohne Namens-Schnappschuss', st == 200 and [k['id'] for k in v['organigramm']['knoten']] == [k['id'] for k in STRUKTUR]
      and v['organigramm']['knoten'][6]['personen'] == ['QB', 'QV'] and 'namen' not in v['organigramm'], r)
check('Verlauf und Bearbeiter', 'Organigramm angelegt (9 Stellen)' in v['verlauf'][-1]['was'] and len(v['bearbeiter']) == 1, v['verlauf'][-1])
rev = dok()['rev']
st, r = speichern(Be, STRUKTUR)
check('unverändert speichern: 200, Stand bleibt', st == 200 and dok()['rev'] == rev)
check('alle mit „QM ansehen“ sehen die Struktur in qs_start', len(dok(L)['versionen'][0]['organigramm']['knoten']) == 9)


def fehler_bei(name, liste, teil):
    st, r = speichern(Be, liste)
    check(f'abgelehnt: {name} (422)', st == 422 and teil in r.get('error', ''), (st, r.get('error')))


fehler_bei('Zyklus', STRUKTUR + [knoten('a', 'A', 'b'), knoten('b', 'B', 'a')], 'selbst untergeordnet')
fehler_bei('Stelle unter sich selbst', STRUKTUR + [knoten('a', 'A', 'a')], 'selbst untergeordnet')
fehler_bei('übergeordnete Stelle fehlt', STRUKTUR + [knoten('a', 'A', 'nichtda')], 'übergeordnete Stelle fehlt')
fehler_bei('übergeordnete Stelle kein Text', STRUKTUR + [dict(knoten('a', 'A'), ueber=5)], 'ungültige übergeordnete Stelle')
fehler_bei('Stabsstelle ohne Linie', STRUKTUR + [knoten('a', 'A', '', 'stab')], 'braucht eine übergeordnete')
fehler_bei('Stelle unter einer Stabsstelle', STRUKTUR + [knoten('a', 'A', 'qmb')], 'keine untergeordneten')
fehler_bei('unbekannte Person', STRUKTUR + [knoten('a', 'A', 'gf', personen=['XX'])], '„XX“ steht nicht in den Personen')
fehler_bei('unbekannte Vertretung', STRUKTUR + [knoten('a', 'A', 'gf', vertretung='XX')], 'Vertretung')
fehler_bei('Kennung doppelt', STRUKTUR + [knoten('gf', 'Doppelt')], 'doppelt')
fehler_bei('Kennung ungültig', STRUKTUR + [knoten('A-1', 'X')], 'ungültige Kennung')
fehler_bei('Stelle ohne Namen', STRUKTUR + [knoten('a', ' ')], 'benennen')
fehler_bei('Stelle mit 121 Zeichen', STRUKTUR + [knoten('a', 'x' * 121)], 'höchstens 120')
fehler_bei('Hinweis mit 201 Zeichen', STRUKTUR + [knoten('a', 'A', hinweis='x' * 201)], 'höchstens 200')
fehler_bei('unbekannte Art', STRUKTUR + [knoten('a', 'A', 'gf', 'quer')], 'Art')
fehler_bei('11 Personen', STRUKTUR + [knoten('a', 'A', personen=['GF'] * 11)], 'höchstens 10 Personen')
fehler_bei('301 Stellen', [knoten(f'k{i}', f'Stelle {i}') for i in range(301)], 'höchstens 300')
check('300 Stellen sind erlaubt', speichern(Be, [knoten('gf', 'GF')] + [knoten(f'k{i}', f'Stelle {i}', 'gf') for i in range(299)])[0] == 200)
st, r = Be.call('qs_organigramm_save', {'dokument': DOK['id'], 'rev': 1, 'organigramm': {'knoten': STRUKTUR}})
check('veralteter Stand: 409 (Konflikt)', st == 409 and r.get('code') == 'konflikt', r)
st, r = speichern(Be, [])
v = r.get('dokument', {}).get('versionen', [{}])[0]
check('leere Liste nimmt das Organigramm aus dem Entwurf', st == 200 and 'organigramm' not in v and v['verlauf'][-1]['was'] == 'Organigramm entfernt', v.get('verlauf', [{}])[-1:])
check('ohne Organigramm keine PDF-Vorschau (404)', vorschau(L)[0] == 404)
check('zurück auf die Struktur', speichern(Be, STRUKTUR)[0] == 200)
d = dok()
st, r = Be.call('qs_organigramm_save', {'dokument': DOK['id'], 'version': 'v000000000000', 'rev': 1, 'organigramm': {'knoten': STRUKTUR[:1]}})
check('Zeichnung eines anderen Entwurfs („version“): 409 mit klarer Meldung vor der Stand-Prüfung, nichts geändert', st == 409 and r.get('code') != 'konflikt'
      and 'verworfen oder freigegeben' in r.get('error', '') and dok()['rev'] == d['rev'], r)
check('passende „version“: gespeichert wie ohne', Be.call('qs_organigramm_save', {'dokument': DOK['id'], 'version': d['versionen'][0]['id'], 'rev': d['rev'],
                                                                              'organigramm': {'knoten': STRUKTUR[:-1]}})[0] == 200
      and len(dok()['versionen'][0]['organigramm']['knoten']) == 8 and speichern(Be, STRUKTUR)[0] == 200)
ordner = next(x for x in start['dokumente'] if x['art'] == 'O')
gueltig = next(x for x in start['dokumente'] if x['nr'] == '1.4-A01')
check('Ordner: 422; gültiges Dokument ohne Entwurf: 409', speichern(Be, STRUKTUR, dok(did=ordner['id']))[0] == 422 and speichern(Be, STRUKTUR, dok(did=gueltig['id']))[0] == 409)

# ── PDF-Vorschau des Entwurfs ──
st, kopf, inhalt = vorschau(L)
z = (pdf_text(inhalt) or [[]])[0]
check('PDF-Vorschau mit „QM ansehen“: als ENTWURF gekennzeichnet, heutige Namen, nächste Version, noch ohne Datum', st == 200 and kopf['content-type'] == 'application/pdf'
      and 'ENTWURF – nicht freigegeben' in z and 'Quinn Beispiel' in z and z[z.index('Version') + 1] == '1' and z[z.index('Datum') + 1] == '—'
      and 'Entwurf Version 1.pdf' in kopf.get('content-disposition', ''), (st, z[:8]))
check('PDF-Vorschau: ohne Anmeldung 401, ohne QM-Recht 403, gültiges Dokument ohne Entwurf 404', vorschau(N)[0] == 401 and vorschau(O)[0] == 403 and vorschau(L, gueltig['id'])[0] == 404)

# ── 4-Augen-Prinzip, Namen ab dem Einreichen, Freigabe ──
ge = [dict(k) for k in STRUKTUR]; ge[7]['personen'] = ['EK']
st, r = speichern(V, ge)
check('zweite Person ändert: zählt als Bearbeiter', st == 200 and len(r['dokument']['versionen'][0]['bearbeiter']) == 2)
check('zur Prüfung gegeben', schritt(Be, 'einreichen') == 200)
check('eingereicht: Namen festgehalten', dok()['versionen'][0]['organigramm'].get('namen', {}).get('QB') == 'Quinn Beispiel', dok()['versionen'][0]['organigramm'].get('namen'))
pers = [dict(p, name='Quinn Zwischendurch') if p['id'] == 'QB' else p for p in V.call('qs_start')[1]['personen']]
check('Person zwischen Einreichen und Freigabe umbenannt', V.call('qs_stamm_save', {'personen': pers})[0] == 200)
z = pdf_text(vorschau(L)[2])[0]
check('PDF-Vorschau in Prüfung: der festgehaltene Name, nicht der neue', 'Quinn Beispiel' in z and 'Quinn Zwischendurch' not in z, z)
check('in Prüfung: Organigramm nicht mehr änderbar (409)', speichern(Be, STRUKTUR)[0] == 409)
st, r = V.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'pruefen_freigeben'})
check('wer am Organigramm geändert hat, prüft nicht (4-Augen, 403)', st == 403 and '4-Augen' in r.get('error', ''), r)
st, r = Q.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'pruefen_freigeben'})
v1 = r.get('dokument', {}).get('versionen', [{}])[0]
pdfs = [f for f in v1.get('dateien', []) if f.get('organigramm')]
check('freigegeben als Version 1 mit genau einer PDF-Fassung', st == 200 and v1['status'] == 'freigegeben' and v1['nr'] == 1 and len(pdfs) == 1
      and pdfs[0]['name'] == '1.2-L02 Organigramm - Version 1.pdf' and pdfs[0]['mime'] == 'application/pdf', v1.get('dateien'))
check('Freigabe übernimmt die geprüften Namen (alle Kürzel, Umbenennung nach dem Einreichen zählt nicht)', v1['organigramm']['namen'] == {
      'GF': 'Geschäftsführung', 'QB': 'Quinn Beispiel', 'QV': 'Vera Vertretung', 'HT': 'Hanna Team', 'FD': 'Fiete Defense', 'EK': 'Emil Einkauf'}, v1['organigramm'].get('namen'))
st, kopf, inhalt = roh(L, f'qs_datei&id={pdfs[0]["id"]}')
text = pdf_text(inhalt)
open(os.path.join(SH, 'qs_organigramm_version1.pdf'), 'wb').write(inhalt)
zeilen = text[0] if text else []
check('PDF mit „QM ansehen“ ladbar, eine Seite mit Logo, ohne ENTWURF', st == 200 and inhalt[:5] == b'%PDF-' and len(text) == 1 and b'/Subtype /Image' in inhalt
      and kopf['content-type'] == 'application/pdf' and not any('ENTWURF' in x for x in zeilen), (st, len(text)))
check('PDF-Kopf: Titel und Nummer', 'Organigramm' in zeilen and any(z.startswith('1.2-L02') for z in zeilen), zeilen[:4])
fuss = zeilen[zeilen.index('Dokument-Nr.'):][:12] if 'Dokument-Nr.' in zeilen else []
check('PDF-Fuß: Lenkungsangaben Nr., Version, Datum, erstellt, geprüft, freigegeben', fuss == ['Dokument-Nr.', '1.2-L02', 'Version', '1', 'Datum', de(HEUTE.isoformat()), 'Erstellt', 'Bernd Bearbeiter',
      'Geprüft', 'Quinn QMB', 'Freigegeben', 'Quinn QMB'], fuss)
check('PDF-Kästen: Stellen, geprüfte Namen, Vertretung, unbesetzt, Hinweis (Zeilen umbrochen)', all(x in ' '.join(zeilen) for x in ('Geschäftsführung', 'Quinn Beispiel', 'Vertretung: Vera Vertretung', 'Lager und Versand',
      'unbesetzt', 'extern', 'Kommissionierung', 'Food Defense')) and 'Quinn Zwischendurch' not in ' '.join(zeilen), zeilen)
check('nach der Freigabe nicht mehr änderbar (409)', speichern(Be, STRUKTUR)[0] == 409)

# ── Unveränderlich bei geänderten Personen ──
stamm = V.call('qs_start')[1]
pers = [dict(p, name='Quinn Umbenannt') if p['id'] == 'QB' else p for p in stamm['personen'] if p['id'] != 'FD']
check('Person umbenannt, eine andere entfernt', V.call('qs_stamm_save', {'personen': pers})[0] == 200)
v1n = dok()['versionen'][0]
st, _, inhalt2 = roh(L, f'qs_datei&id={pdfs[0]["id"]}')
check('freigegebene Version unverändert: Struktur, Namen, PDF', v1n['organigramm'] == v1['organigramm'] and hashlib.sha256(inhalt2).hexdigest() == pdfs[0]['sha256'] == hashlib.sha256(inhalt).hexdigest())

# ── Neue Version übernimmt die Struktur; Zurückgeben entfernt die festgehaltenen Namen ──
st, r = Be.call('qs_version_save', {'dokument': DOK['id'], 'rev': dok()['rev'], 'aenderungen': 'Lager neu besetzt', 'grund': 'Personalwechsel', 'dateien': True})
v2 = r.get('dokument', {}).get('versionen', [{}, {}])[1]
check('Überarbeitung: Struktur übernommen, ohne Namen und ohne PDF', st == 200 and v2['status'] == 'entwurf' and v2['organigramm']['knoten'] == v1['organigramm']['knoten']
      and 'namen' not in v2['organigramm'] and not v2.get('dateien'), v2)
check('entfernte Person im Entwurf: Speichern nennt sie (422)', 'FD' in speichern(Be, v2['organigramm']['knoten'])[1].get('error', ''))
neu = [k for k in v2['organigramm']['knoten'] if k['id'] != 'fd']
neu[-1] = dict(neu[-1], titel='Kommissionierung und Verladung')
check('Entwurf geändert', speichern(Be, neu)[0] == 200)
check('eingereicht', schritt(Be, 'einreichen') == 200 and 'namen' in dok()['versionen'][1]['organigramm'])
check('zurückgegeben: Namen wieder entfernt', schritt(Q, 'zurueck', grund='Lager prüfen') == 200 and 'namen' not in dok()['versionen'][1]['organigramm'])
check('erneut eingereicht', schritt(Be, 'einreichen') == 200)
roh_dok = storage_raw('qs-dokumente')
gespeichert = json.loads(roh_dok.split('\n', 1)[1] if roh_dok.startswith('<?php') else roh_dok)
next(x for x in gespeichert['liste'] if x['id'] == DOK['id'])['versionen'][1]['organigramm'].pop('namen')
storage_write('qs-dokumente', gespeichert)   # wie nach dem Einreichen mit einer Vorversion der Anwendung
check('geprüft (zweistufig): fehlende Namen beim Prüfen festgehalten', schritt(Q, 'pruefen') == 200
      and dok()['versionen'][1]['organigramm'].get('namen', {}).get('QB') == 'Quinn Umbenannt', dok()['versionen'][1]['organigramm'].get('namen'))
st, r = Q.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'freigeben'})
d2 = r.get('dokument', {})
v1e, v2f = d2['versionen'][0], d2['versionen'][1]
check('Version 2 gültig mit neuem Namen, Version 1 ersetzt und unverändert', st == 200 and v2f['nr'] == 2 and v2f['organigramm']['namen']['QB'] == 'Quinn Umbenannt' and v1e['status'] == 'ersetzt'
      and v1e['organigramm'] == v1['organigramm'] and len([f for f in v2f['dateien'] if f.get('organigramm')]) == 1, v2f.get('organigramm', {}).get('namen'))
st, _, inhalt3 = roh(L, f'qs_datei&id={[f for f in v2f["dateien"] if f.get("organigramm")][0]["id"]}')
z3 = pdf_text(inhalt3)[0]
check('PDF der Version 2: neuer Name, geänderte Stelle (umbrochen), Version 2, ohne die entfernte Stelle', 'Quinn Umbenannt' in z3 and 'Kommissionierung und Verladung' in ' '.join(z3)
      and z3[z3.index('Version') + 1] == '2' and 'Food Defense' not in z3, z3)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Organigramm angelegt, geändert und entfernt, Version 2 freigegeben', all(t in log for t in ('Organigramm in 1.2-L02 Organigramm angelegt', 'Organigramm in 1.2-L02 Organigramm geändert',
      'Organigramm in 1.2-L02 Organigramm entfernt', '1.2-L02 Organigramm – Version 2 freigegeben')))

# ── Oberfläche ──
pers = [dict(p, name='Quinn Neu') if p['id'] == 'QB' else p for p in V.call('qs_start')[1]['personen']]
assert V.call('qs_stamm_save', {'personen': pers})[0] == 200
st, r = Be.call('qs_dokument_save', {'kapitel': '1.2', 'art': 'L', 'nr': '', 'titel': 'Organisationsplan Lager', 'aenderungen': 'Neu angelegt'})
PLAN = r['dokument']['id']
dialoge = []


def antwort(ja):
    return lambda d: (dialoge.append(d.message), d.accept() if ja else d.dismiss())


def baum(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#og-baum .og-kasten')].map((k) => k.querySelector('b').textContent)")


def lage(pg):
    return pg.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#og-baum .og-kasten')].map((k) => {
      const r = k.getBoundingClientRect(); return [k.querySelector('b').textContent, { l: r.left, r: r.right, t: r.top, b: r.bottom, m: (r.left + r.right) / 2 }]; }))""")


def meldung(pg, teil):
    pg.wait_for_function('(t) => document.querySelector("#og-meldung").textContent.includes(t)', arg=teil)
    return pg.text_content('#og-meldung')


with sync_playwright() as pw:
    br = pw.chromium.launch()

    def anmelden(user, pw_, ip, breite=1280, thema='light', hoehe=900):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw_); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/qs/#dokumente'); pg.wait_for_selector('#qm-app:not([hidden])')
        return ctx, pg

    def oeffne_dok(pg, did):
        pg.evaluate('(id) => window.STAFL_QS.oeffneDok(id)', did)
        pg.wait_for_selector(f'#qm-dk[data-dok="{did}"] h2')

    # nur „QM ansehen“: gültige Version mit Namen aus dem Schnappschuss und ihrer PDF
    ctx, pg = anmelden('lisa', 'Leserin-Konto-12', '198.51.100.10')
    pg.click(f'#qm-d-liste tr[data-dok="{DOK["id"]}"]'); pg.wait_for_selector('#qm-dk .og-karte')
    check('ansehen: Karte mit gültiger Version, ohne Bearbeiten', 'Version 2: 8 Stellen' in pg.text_content('#qm-dk .og-karte') and pg.locator('#qm-dk [data-og]').count() == 1
          and pg.get_attribute('#qm-dk [data-og]', 'data-og') == 'ansehen', pg.text_content('#qm-dk .og-karte'))
    pg.click('#qm-dk [data-og="ansehen"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    t = pg.text_content('#og-baum')
    check('ansehen: Diagramm der Version 2, Namen aus der Freigabe (nicht der heutige Name)', len(baum(pg)) == 8 and baum(pg)[0] == 'Geschäftsführung' and 'Quinn Umbenannt' in t
          and 'Quinn Neu' not in t and 'unbesetzt' in t and 'Vertretung: Vera Vertretung' in t and 'extern' in t and 'Version 2 gültig seit' in pg.text_content('#og-sub'), t[:300])
    r = lage(pg)
    gf, stab, linie, kom = r['Geschäftsführung'], [r[x] for x in ('Qualitätsmanagementbeauftragte', 'HACCP-Teamleitung', 'Fachkraft für Arbeitssicherheit')], \
        [r[x] for x in ('Einkauf', 'Qualitätssicherung', 'Lager und Versand')], r['Kommissionierung und Verladung']
    check('Lage: Stabsstellen links und rechts der Mitte unter der Geschäftsführung, Bereiche nebeneinander darunter, einzelne Unterstelle eingerückt darunter',
          all(s['t'] >= gf['b'] and (s['r'] <= gf['m'] or s['l'] >= gf['m']) for s in stab) and {s['l'] < gf['m'] for s in stab} == {True, False}
          and all(b['t'] > max(s['b'] for s in stab) for b in linie) and len({round(b['t']) for b in linie}) == 1 and linie[0]['r'] < linie[1]['l'] < linie[1]['r'] < linie[2]['l']
          and kom['t'] > linie[2]['b'] and linie[2]['l'] < kom['l'] < linie[2]['r'], r)
    check('ansehen: keine Seitenleiste, kein Speichern, Kästen nicht wählbar, PDF statt Vorschau', pg.is_hidden('#og-seite') and pg.is_hidden('#og-fuss')
          and pg.locator('#og-baum button').count() == 0 and pg.is_visible('#og-pdf') and pg.is_hidden('#og-vorschau'))
    with pg.expect_download() as dl:
        pg.click('#og-pdf')
    check('PDF-Fassung über das Fenster geladen', dl.value.suggested_filename == '1.2-L02 Organigramm - Version 2.pdf' and open(dl.value.path(), 'rb').read(5) == b'%PDF-', dl.value.suggested_filename)
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_ansehen_1280_light.png'))
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    ctx.close()

    # bearbeiten: Leer-Zustand, Stellen anlegen, Personen, Stabsstelle, Verschieben, Löschen, Speichern, PDF-Vorschau
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    oeffne_dok(pg, PLAN)
    check('Entwurf ohne Organigramm: Angebot „im System zeichnen“', pg.is_visible('#qm-dk [data-og="bearbeiten"]') and 'im System zeichnen' in pg.text_content('#qm-dk .og-karte'))
    oeffne_dok(pg, DOK['id'])
    check('gültiges Organigramm ohne Entwurf: nur ansehen (Überarbeitung über die Lenkung)', pg.locator('#qm-dk [data-og]').count() == 1 and pg.is_visible('#qm-dk [data-og="ansehen"]'))
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-leer')
    check('Leer-Zustand: „Noch kein Organigramm – Stelle anlegen“ mit Vorschlag Geschäftsführung', 'Noch kein Organigramm – Stelle anlegen' in pg.text_content('#og-baum')
          and pg.input_value('#og-erste') == 'Geschäftsführung' and pg.is_disabled('#og-speichern'))
    pg.click('[data-og-tat="erste"]'); pg.wait_for_selector('#og-baum .og-kasten.gewaehlt')
    check('oberste Stelle angelegt und gewählt, Felder sichtbar, „Stabsstelle“ als Art nicht wählbar', baum(pg) == ['Geschäftsführung'] and pg.input_value('#og-titel-in') == 'Geschäftsführung'
          and pg.locator('#og-art option').count() == 1 and pg.is_enabled('#og-speichern'))
    pg.select_option('#og-pers-neu', 'GF'); pg.select_option('#og-vertretung', 'QV')
    pg.wait_for_function("() => document.querySelector('#og-baum .og-kasten').textContent.includes('Vertretung: Vera Vertretung')")
    pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Vertrieb')
    pg.locator('#og-liste .og-zeile').first.click(); pg.click('[data-og-tat="stab"]'); pg.fill('#og-titel-in', 'Qualitätsmanagementbeauftragte'); pg.select_option('#og-pers-neu', 'QB')
    pg.locator('#og-liste .og-zeile').first.click(); pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Einkauf')
    check('Stabsstelle ohne „Untergeordnete Stelle“, Diagramm folgt der Eingabe', pg.locator('#og-baum .og-stabkasten').count() == 1 and baum(pg) == ['Geschäftsführung', 'Qualitätsmanagementbeauftragte', 'Vertrieb', 'Einkauf'], baum(pg))
    pg.click('[data-og-tat="links"]')
    check('„Nach links“ tauscht Einkauf und Vertrieb', baum(pg) == ['Geschäftsführung', 'Qualitätsmanagementbeauftragte', 'Einkauf', 'Vertrieb'] and pg.is_disabled('[data-og-tat="links"]'), baum(pg))
    pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Disposition')
    r = lage(pg)
    check('Unterstelle ohne eigene Unterstellen: gestapelt und eingerückt unter Einkauf', r['Disposition']['t'] > r['Einkauf']['b'] and r['Einkauf']['l'] < r['Disposition']['l'] < r['Einkauf']['r'], r)
    pg.select_option('#og-ueber', pg.get_attribute('#og-liste .og-zeile', 'data-og-knoten'))
    r = lage(pg)
    check('Verschieben: Disposition unter die Geschäftsführung, neben den anderen ganz rechts', baum(pg)[-1] == 'Disposition' and r['Disposition']['l'] > r['Vertrieb']['r'] > r['Einkauf']['r']
          and abs(r['Disposition']['t'] - r['Einkauf']['t']) < 1 and r['Disposition']['t'] > r['Qualitätsmanagementbeauftragte']['b'], r)
    pg.locator('#og-baum .og-kasten', has_text='Vertrieb').click(); pg.click('[data-og-tat="loeschen"]')
    check('Löschen ohne Unterstellen ohne Rückfrage', 'Vertrieb' not in baum(pg) and pg.is_hidden('#og-felder') and not dialoge)
    pg.once('dialog', antwort(False)); pg.click('#og-zu')
    check('Schließen mit ungespeicherten Änderungen fragt nach (abgelehnt: bleibt offen)', dialoge == ['Ungespeicherte Änderungen am Organigramm verwerfen?'] and pg.is_visible('#dlg-og'), dialoge)
    pg.click('#og-vorschau')
    check('PDF-Vorschau mit ungespeicherten Änderungen: erst speichern', 'zuerst speichern' in meldung(pg, 'zuerst speichern'))
    pg.click('#og-speichern'); meldung(pg, 'Organigramm gespeichert.')
    v = dok(Be, PLAN)['versionen'][0]['organigramm']['knoten']
    titel = {k['id']: k['titel'] for k in v}
    nach = {k['titel']: k for k in v}
    check('gespeichert: Struktur, Personen, Vertretung, Stabsstelle, Reihenfolge unter der Stelle', sorted(nach) == ['Disposition', 'Einkauf', 'Geschäftsführung', 'Qualitätsmanagementbeauftragte']
          and nach['Geschäftsführung']['personen'] == ['GF'] and nach['Geschäftsführung']['vertretung'] == 'QV' and nach['Qualitätsmanagementbeauftragte']['art'] == 'stab'
          and nach['Qualitätsmanagementbeauftragte']['personen'] == ['QB'] and [k['titel'] for k in v if k['art'] == 'linie' and k['ueber']] == ['Einkauf', 'Disposition']
          and all(titel.get(k['ueber']) == 'Geschäftsführung' for k in v if k['ueber']), v)
    check('Karte zeigt den Entwurf, Speichern wieder aus', 'Entwurf: 4 Stellen' in pg.text_content('#qm-dk .og-karte') and pg.is_disabled('#og-speichern'))
    with pg.expect_download() as dl:
        pg.click('#og-vorschau')
    check('PDF-Vorschau aus dem Fenster: gespeicherter Entwurf', dl.value.suggested_filename.endswith('Organisationsplan Lager - Entwurf Version 1.pdf')
          and 'ENTWURF – nicht freigegeben' in pdf_text(open(dl.value.path(), 'rb').read())[0], dl.value.suggested_filename)
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_bearbeiten_1280_light.png'))
    pg.locator('#og-baum .og-kasten', has_text='Einkauf').click()
    pg.fill('#og-titel-in', '')
    pg.click('#og-speichern')
    check('Fehler des Servers erscheint im Fenster', 'benennen' in meldung(pg, 'benennen'))
    pg.once('dialog', antwort(True))
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    check('Schließen nach Rückfrage verwirft die Änderung', 'Einkauf' in [k['titel'] for k in dok(Be, PLAN)['versionen'][0]['organigramm']['knoten']])
    with pg.expect_download() as dl:
        pg.click('#qm-dk [data-og="vorschau"]')
    check('PDF-Vorschau aus der Karte des Dokuments', dl.value.suggested_filename.endswith('Entwurf Version 1.pdf'), dl.value.suggested_filename)

    # zwei Personen am selben Entwurf: Rückfrage statt Sackgasse
    def andere_person_speichert(hinweis):
        d = dok(V, PLAN)
        kn = [dict(k, hinweis=hinweis) if k['ueber'] == '' else k for k in d['versionen'][0]['organigramm']['knoten']]
        return V.call('qs_organigramm_save', {'dokument': PLAN, 'rev': d['rev'], 'organigramm': {'knoten': kn}})[0] == 200

    def gf_hinweis():
        return next(k for k in dok(Be, PLAN)['versionen'][0]['organigramm']['knoten'] if k['ueber'] == '')['hinweis']

    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    check('nach „Schließen“ mit Verwerfen keine Frage nach einer gesicherten Zeichnung', pg.is_hidden('#og-wieder'))
    pg.locator('#og-liste .og-zeile').first.click(); pg.fill('#og-hinweis', 'aus dem Browser')
    check('andere Person speichert denselben Entwurf', andere_person_speichert('von Vera'))
    pg.evaluate("""() => { const c = window.confirm; window.confirm = (t) => { window.beimFragen = [document.querySelector('#og-speichern').disabled, document.querySelector('#og-koerper').inert];
      window.confirm = c; return c.call(window, t); }; }""")
    dialoge.clear(); pg.once('dialog', antwort(False))
    pg.click('#og-speichern'); meldung(pg, 'Nicht gespeichert')
    check('Konflikt abgelehnt: Rückfrage nennt die andere Person, eigene Fassung bleibt im Fenster, nichts überschrieben', dialoge == ['Inzwischen geändert von Vera Verwalten – Ihre Fassung trotzdem speichern?']
          and pg.input_value('#og-hinweis') == 'aus dem Browser' and pg.is_enabled('#og-speichern') and gf_hinweis() == 'von Vera', (dialoge, gf_hinweis()))
    check('während der Rückfrage bleiben Speichern und Zeichnung gesperrt (kein zweiter Lauf)', pg.evaluate('() => window.beimFragen') == [True, True], pg.evaluate('() => window.beimFragen'))
    check('andere Person speichert noch einmal', andere_person_speichert('wieder von Vera'))
    dialoge.clear(); pg.once('dialog', antwort(True))
    pg.click('#og-speichern'); meldung(pg, 'Organigramm gespeichert.')
    check('Konflikt bestätigt: eigene Fassung mit neuem Stand gespeichert', len(dialoge) == 1 and gf_hinweis() == 'aus dem Browser', (dialoge, gf_hinweis()))
    pg.fill('#og-hinweis', 'während des Speicherns')
    pg.evaluate("() => { const f = window.fetch; const halt = new Promise((r) => { window.weiter = r; }); window.fetch = async (...a) => { window.fetch = f; await halt; return f(...a); }; }")
    pg.click('#og-speichern')
    check('während des Speicherns: Zeichnung und Speichern gesperrt', pg.is_disabled('#og-speichern')
          and pg.evaluate("() => { const i = document.querySelector('#og-hinweis'); i.focus(); return document.activeElement !== i && document.querySelector('#og-koerper').inert; }"))
    ja = antwort(True); dialoge.clear(); pg.on('dialog', ja)
    pg.keyboard.press('Escape'); pg.keyboard.press('Escape'); pg.click('#og-zu'); pg.click('#og-fuss [data-og-tat="schliessen"]')
    check('während des Speicherns: Esc, × und „Schließen“ warten (keine Rückfrage, Fenster bleibt)', not dialoge and pg.is_visible('#dlg-og'), dialoge)
    pg.remove_listener('dialog', ja)
    pg.evaluate('() => window.weiter()'); meldung(pg, 'Organigramm gespeichert.')
    check('nach dem Speichern wieder frei', not pg.evaluate("() => document.querySelector('#og-koerper').inert") and gf_hinweis() == 'während des Speicherns')
    pg.fill('#og-hinweis', 'nach der Abmeldung')
    ctx.clear_cookies()
    pg.click('#og-speichern'); meldung(pg, 'Anmeldung ist abgelaufen')
    check('abgelaufene Anmeldung: Meldung, Fenster und Eingabe bleiben', pg.is_visible('#dlg-og') and pg.input_value('#og-hinweis') == 'nach der Abmeldung' and pg.is_enabled('#og-speichern'))
    tab = ctx.new_page()   # andere Person meldet sich im selben Browser an: ihr Token darf dieser Tab nicht übernehmen
    tab.goto(B + '/admin/'); tab.wait_for_selector('#screen-auth:not([hidden])')
    tab.fill('#au-user', 'lisa'); tab.fill('#pw1', 'Leserin-Konto-12'); tab.click('#auth-submit'); tab.wait_for_selector('#screen-auth', state='hidden')
    tab.close()
    pg.click('#og-speichern'); meldung(pg, 'Sicherheitsprüfung')
    check('andere Person im neuen Tab angemeldet: nicht unter ihrem Namen gespeichert, Eingabe bleibt', gf_hinweis() == 'während des Speicherns'
          and pg.input_value('#og-hinweis') == 'nach der Abmeldung', gf_hinweis())
    ctx.clear_cookies()
    tab = ctx.new_page()   # „in einem neuen Tab anmelden“: dieselben Cookies, neues CSRF-Token
    tab.goto(B + '/admin/'); tab.wait_for_selector('#screen-auth:not([hidden])')
    tab.fill('#au-user', 'bernd'); tab.fill('#pw1', 'Bearbeit-Konto-34'); tab.click('#auth-submit'); tab.wait_for_selector('#screen-auth', state='hidden')
    tab.close()
    pg.click('#og-speichern'); meldung(pg, 'Organigramm gespeichert.')
    check('nach Anmeldung in einem neuen Tab: im alten Fenster gespeichert, die Zeichnung blieb erhalten', gf_hinweis() == 'nach der Abmeldung', gf_hinweis())

    # Konflikt, während die Anmeldung abläuft: die Anmeldemaske schließt das Fenster – die Zeichnung kommt nach dem Neuladen wieder
    pg.fill('#og-hinweis', 'gesichert')
    check('andere Person speichert vor dem Ablauf', andere_person_speichert('von Vera vor dem Ablauf'))

    def abgelaufen(url):
        return 'action=qs_start' in url

    pg.route(abgelaufen, lambda r: r.fulfill(status=401, content_type='application/json', body='{"ok":false,"error":"Bitte erneut anmelden."}'))
    pg.click('#og-speichern'); pg.wait_for_selector('#qm-login:not([hidden])')
    check('Konflikt bei abgelaufener Anmeldung: Anmeldemaske, Fenster geschlossen, nichts gespeichert', pg.is_hidden('#dlg-og') and gf_hinweis() == 'von Vera vor dem Ablauf')
    pg.unroute(abgelaufen)
    pg.reload(); pg.wait_for_selector('#qm-app:not([hidden])')
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#og-wieder:not([hidden])')
    frage = pg.text_content('#og-wieder-text')
    check('nach dem Neuladen: Frage „Ungespeicherte Zeichnung vom … wiederherstellen?“, bis zur Antwort gesperrt', re.fullmatch(r'Ungespeicherte Zeichnung vom \d\d\.\d\d\.\d{4}, \d\d:\d\d wiederherstellen\?', frage)
          and pg.evaluate("() => document.querySelector('#og-koerper').inert") and pg.is_disabled('#og-speichern'), frage)
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_wiederherstellen_1280_light.png'))
    pg.click('[data-og-tat="wiederherstellen"]'); pg.locator('#og-liste .og-zeile').first.click()
    check('wiederhergestellt: eigene Eingabe wieder da, Frage weg, Speichern frei', pg.input_value('#og-hinweis') == 'gesichert' and pg.is_hidden('#og-wieder') and pg.is_enabled('#og-speichern'))
    dialoge.clear(); pg.once('dialog', antwort(True))
    pg.click('#og-speichern'); meldung(pg, 'Organigramm gespeichert.')
    check('wiederhergestellte Zeichnung: Rückfrage wegen der fremden Änderung, dann gespeichert', dialoge == ['Inzwischen geändert von Vera Verwalten – Ihre Fassung trotzdem speichern?']
          and gf_hinweis() == 'gesichert', (dialoge, gf_hinweis()))
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    check('nach dem Speichern keine Frage mehr', pg.is_hidden('#og-wieder'))
    ctx.close()

    for breite, thema in ((1280, 'dark'), (390, 'light'), (390, 'dark')):
        ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11', breite, thema, 844 if breite < 500 else 900)
        oeffne_dok(pg, PLAN)
        pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
        pg.locator('#og-liste .og-zeile').nth(1).click(); pg.wait_for_selector('#og-felder:not([hidden])')
        check(f'{breite} px {thema}: Gliederung wählt die Stelle', pg.input_value('#og-titel-in') == 'Qualitätsmanagementbeauftragte' and pg.locator('#og-liste .og-zeile').count() == 4)
        breit = pg.evaluate("() => { const d = document.querySelector('#dlg-og'); return [document.documentElement.scrollWidth - window.innerWidth, d.scrollWidth - d.clientWidth, d.getBoundingClientRect().width]; }")
        check(f'{breite} px {thema}: Seite und Fenster ohne waagerechtes Scrollen', breit[0] <= 0 and breit[1] <= 0 and breit[2] <= breite, breit)
        pg.screenshot(path=os.path.join(SH, f'qs_organigramm_bearbeiten_{breite}_{thema}.png'))
        if breite == 390:
            pg.click('[data-og-tat="groesser"]')
            check(f'{breite} px {thema}: Diagramm lässt sich vergrößern und im Fenster scrollen', pg.evaluate("() => { const f = document.querySelector('#og-flaeche'); return f.scrollWidth > f.clientWidth; }"))
            pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
            oeffne_dok(pg, DOK['id'])
            pg.click('#qm-dk [data-og="ansehen"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
            pg.screenshot(path=os.path.join(SH, f'qs_organigramm_ansehen_{breite}_{thema}.png'))
        ctx.close()

    # 390 px: Frage nach dem Neuladen, „Verwerfen“ löscht die Sicherung
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11', 390, 'light', 844)
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    pg.locator('#og-liste .og-zeile').first.click(); pg.fill('#og-hinweis', 'nur im Browser')
    pg.reload(); pg.wait_for_selector('#qm-app:not([hidden])')
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#og-wieder:not([hidden])')
    breit = pg.evaluate("() => { const d = document.querySelector('#dlg-og'); return [document.documentElement.scrollWidth - window.innerWidth, d.scrollWidth - d.clientWidth]; }")
    check('390 px: Frage nach dem Neuladen ohne waagerechtes Scrollen', breit[0] <= 0 and breit[1] <= 0 and pg.is_visible('[data-og-tat="verwerfen"]'), breit)
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_wiederherstellen_390_light.png'))
    pg.click('[data-og-tat="verwerfen"]'); pg.locator('#og-liste .og-zeile').first.click()
    check('„Verwerfen“: gespeicherter Stand, nichts zu speichern', pg.is_hidden('#og-wieder') and pg.input_value('#og-hinweis') == 'gesichert' and pg.is_disabled('#og-speichern'))
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    check('verworfene Sicherung wird nicht erneut angeboten', pg.is_hidden('#og-wieder'))
    ctx.close()

    # Organigramm wieder aus dem Entwurf nehmen
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    pg.locator('#og-liste .og-zeile').first.click()
    dialoge.clear(); pg.once('dialog', antwort(True)); pg.click('[data-og-tat="loeschen"]')
    check('alle Stellen gelöscht: Hinweis, dass Speichern das Organigramm entfernt', dialoge == ['„Geschäftsführung“ mit 3 untergeordneten Stellen löschen?']
          and 'nimmt das Organigramm aus dem Entwurf' in pg.text_content('#og-baum') and pg.is_enabled('#og-speichern'), dialoge)
    pg.click('#og-speichern'); meldung(pg, 'Organigramm gespeichert.')
    check('entfernt: Entwurf ohne Organigramm, Karte bietet wieder „im System zeichnen“', 'organigramm' not in dok(Be, PLAN)['versionen'][0]
          and 'im System zeichnen' in pg.text_content('#qm-dk .og-karte'))

    # Entwurf inzwischen verworfen und neu begonnen: die alte Zeichnung landet nicht im neuen Entwurf
    pg.click('[data-og-tat="erste"]')
    check('andere Person verwirft den Entwurf und beginnt einen neuen', V.call('qs_version_schritt', {'dokument': PLAN, 'rev': dok(V, PLAN)['rev'], 'schritt': 'verwerfen', 'grund': 'neu'})[0] == 200
          and V.call('qs_version_save', {'dokument': PLAN, 'rev': dok(V, PLAN)['rev'], 'aenderungen': 'Neu angelegt'})[0] == 200)
    dialoge.clear(); pg.once('dialog', antwort(True))
    pg.click('#og-speichern'); meldung(pg, 'verworfen oder freigegeben')
    offen = [v for v in dok(Be, PLAN)['versionen'] if v['status'] == 'entwurf']
    check('Speichern im alten Fenster: klare Meldung, keine Rückfrage, neuer Entwurf ohne Organigramm', not dialoge and len(offen) == 1 and 'organigramm' not in offen[0]
          and pg.is_visible('#dlg-og'), (dialoge, offen))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler[:5])

print(f'{sum(res)}/{len(res)} passed')
