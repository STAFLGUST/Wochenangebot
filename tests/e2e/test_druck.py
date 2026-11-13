"""Druck der Angebote (Wunsch des Inhabers 13.11.2026): die Druckfassung „Angebotsansicht“ (A4 quer) zeigt alles, was die
Vorschau zeigt – fortlaufend und kompakt statt „jeder Bereich auf einer neuen Seite“. Geprüft wird: Druck-DOM vollständig
(Artikel, Gruppen, Bereiche, Reihenfolge, Werbung, Sonderposten wie am Bildschirm), Farben aktiv (print-color-adjust, auch
ohne „Hintergrundgrafiken“), kein Seitenumbruch je Bereich, Seitenzahl (PDF) unter dem Grenzwert und gleich den gesetzten
Seiten, nichts läuft über, Kopf „Seite x von y“, Schrift nicht unter 7,5 pt; Fußzeile des Briefbogens mit dem Hinweis
darüber in beiden Varianten (jede Seite / nur letzte Seite, eine Einstellung bzw. ?fuss=); Einstellung „Fußzeile im Druck“
(Rechte 401/403, leer = Vorgabe aus dem Impressum, Bereinigung, Fracht-Einstellung bleibt erhalten, Protokoll);
Bankangaben nur für angemeldete Nutzer (Server entscheidet; öffentlich ohne Cookie); Einzelangebot (Druck und PDF des
Servers mit Fußzeile); Hochformat-Layouts mit Fußzeile am Ende; im Eingabebereich Knopf „Drucken“ (links neben „An Kunden
senden“/„Veröffentlichen“, druckt das gewählte Angebot als Entwurf wie die Vorschau, speichert vorher), „Drucken“ im
Vorschaufenster, Schnittstelle WA.angebot.druck.drucken für andere Module, Fenster „Fußzeile im Druck“ nur für
Administratoren, 390 px, keine JavaScript-Fehler. Nur Testdaten (Seed-Angebot) und erfundene Angaben in der Fußzeile."""
import json
import re
import sys
import urllib.error
import urllib.request
import zlib
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, shot, storage_raw

PW = 'Sicheres-Passwort-1'
PW_E = 'Editor-Zugang-77'
PW_L = 'Leserin-Zugang-1'
res = []
MM = 96 / 25.4   # px je mm


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


def roh(cl, action, headers=None):
    """GET ohne JSON-Auswertung: (Status, Kopfzeilen, Bytes)"""
    req = urllib.request.Request(BASE + '/api/?action=' + action, headers={'X-Forwarded-For': cl.ip, **(headers or {})})
    try:
        r = cl.http.open(req)
    except urllib.error.HTTPError as ex:
        r = ex
    return r.code, r.headers, r.read()


def pdf_stroeme(data):
    """Entpackte Inhaltsströme (FlateDecode) eines PDF"""
    out = []
    for mm in re.finditer(rb'stream\r?\n', data):
        ende = data.find(b'endstream', mm.end())
        try:
            out.append(zlib.decompress(data[mm.end():ende].rstrip(b'\r\n')))
        except zlib.error:
            pass
    return out


def pdf_text(data):
    return b''.join(pdf_stroeme(data)).decode('cp1252', 'replace')


def pdf_seiten(data):
    return len(re.findall(rb'/Type\s*/Page[^s]', data))


def pdf_farbig(data):
    """Anzahl farbiger (nicht grauer) Füllfarben in den Seiteninhalten"""
    n = 0
    for s in pdf_stroeme(data):
        for r, g, b in re.findall(rb'(?<![\d.])([\d.]+) ([\d.]+) ([\d.]+) rg\b', s):
            if abs(float(r) - float(g)) > .02 or abs(float(g) - float(b)) > .02:
                n += 1
    return n


# Erfundene Angaben für die Fußzeile (GR-007: keine echten Bank- oder Steuerangaben im Repository)
SP1 = 'Musterfleisch Test GmbH\nTeststraße 1\n00000 Musterstadt'
SP2 = 'Telefon 000 - 00 00 00\nwww.example.org\ninfo@example.org'
SP3 = 'Testbank Musterstadt\nKonto TEST 0000 0000 00\nSteuer-Nr. 00/000/00000'
Z1 = 'Eingetragen Handelsregister Musterstadt B 000 00 * Geschäftsführer : Erika Beispiel'
Z2 = 'Eingetragen Handelsregister Musterstadt A 000 00 * Persönlich haftende Gesellschafterin : Beispiel Verwaltung mbH'

A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': PW_L, 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': PW_E})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': PW_L})[0] == 200
ANON = Client('203.0.113.60')

# ---------- Einstellung „Fußzeile im Druck“: Rechte, Vorgabe, Bereinigung ----------
st, r = A.call('druck_fuss')
vorgabe = r.get('vorgabe', {})
check('Vorgabe ohne eigene Texte: nur Angaben aus dem Impressum, auf jeder Seite, Bankangaben geschützt',
      st == 200 and r['fuss']['eigen'] is False and r['fuss']['spalten'] == vorgabe['spalten'] and r['fuss']['zeilen'] == vorgabe['zeilen']
      and r['fuss']['modus'] == 'jede' and r['fuss']['bankGeschuetzt'] is True, r.get('fuss'))
vt = json.dumps(vorgabe, ensure_ascii=False)
check('Vorgabe im Code ohne Bank- und Steuernummer (GR-007)', not re.search(r'IBAN|BIC|Bank|Konto|Steuer-?Nr|Sparkasse', vt, re.I) and 'Lagerstraße 17' in vt, vt[:200])
check('Vorgabe steht so im Impressum der Angebotsseite', all(t in urllib.request.urlopen(BASE + '/impressum/').read().decode('utf-8') for t in ('Lagerstraße 17', '20357 Hamburg', 'DE 118949959')))
check('Lesen: Bearbeiter und Leser mit Modulzugang ja, ohne Anmeldung 401', E.call('druck_fuss')[0] == 200 and L.call('druck_fuss')[0] == 200 and ANON.call('druck_fuss')[0] == 401,
      (E.call('druck_fuss')[0], L.call('druck_fuss')[0], ANON.call('druck_fuss')[0]))
neu = {'spalten': [SP1, SP2, SP3], 'zeilen': [Z1, Z2], 'modus': 'jede'}
check('Speichern: Bearbeiter und Leser 403, ohne Anmeldung 401 – nichts gespeichert',
      E.call('druck_fuss_save', {'fuss': neu})[0] == 403 and L.call('druck_fuss_save', {'fuss': neu})[0] == 403 and ANON.call('druck_fuss_save', {'fuss': neu})[0] in (401, 403)
      and A.call('druck_fuss')[1]['fuss']['eigen'] is False and 'druck' not in (doc('fracht') or {}))
off0 = ANON.call('offer')[1]
check('Angebot liefert die Fußzeile mit (leer = Vorgabe) und den Hinweis zu Mengen und Fracht', off0['fracht']['fuss']['spalten'] == vorgabe['spalten'] and off0['fracht']['fuss']['modus'] == 'jede'
      and 'Mindestbestellmenge von ca. 300 kg' in off0['fracht']['hinweis'][0], off0['fracht'].get('fuss'))
schmutz = {'spalten': [SP1 + '\n\n  ' + '\n'.join(f'Zeile {i}' for i in range(9)), 'x' * 90 + '\tTab\x07', SP3, 'vierte Spalte'], 'zeilen': [Z1 + '\nzweite Zeile', 'y' * 300, 'dritte'],
           'modus': 'quer', 'fremd': 'weg', 'updatedBy': 'Fälscher'}
st, r = A.call('druck_fuss_save', {'fuss': schmutz})
f = r.get('fuss', {})
check('Bereinigung: höchstens 6 Zeilen je Spalte, 70 Zeichen je Zeile, Steuerzeichen weg, Registerzeile einzeilig (200 Zeichen), unbekannter Modus → jede, fremde Felder weg',
      st == 200 and f['spalten'][0].count('\n') == 5 and f['spalten'][1] == 'x' * 70 and len(f['spalten']) == 3 and f['zeilen'] == [Z1, 'y' * 200]
      and f['modus'] == 'jede' and 'fremd' not in f and f.get('updatedBy') != 'Fälscher', f)
st, r = A.call('druck_fuss_save', {'fuss': neu})
check('Administrator speichert die Fußzeile (eigene Texte)', st == 200 and r['fuss']['eigen'] is True and r['fuss']['spalten'] == [SP1, SP2, SP3] and r['fuss']['zeilen'] == [Z1, Z2]
      and r['fuss']['bankGeschuetzt'] is True, r)
gesp = doc('fracht')
check('gespeichert als Feld „druck“ im Dokument „fracht“ (nur erweitert)', gesp['druck']['spalten'] == [SP1, SP2, SP3] and gesp['druck']['modus'] == 'jede' and 'aktiv' in gesp and 'staffeln' in gesp, list(gesp))
st, _ = A.call('fracht_save', {'aktiv': True, 'staffeln': [{'unter': 300, 'kosten': 30}, {'unter': 200, 'kosten': 35}], 'zusatz': 'Telefon Test: 000 - 00 00 00'})
check('„Fracht und Hinweis“ speichern lässt die Fußzeile unverändert – und umgekehrt', st == 200 and doc('fracht')['druck']['spalten'] == [SP1, SP2, SP3]
      and A.call('druck_fuss_save', {'fuss': neu})[0] == 200 and doc('fracht')['zusatz'] == 'Telefon Test: 000 - 00 00 00', st)
prot = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Änderung der Fußzeile vermerkt', 'Fußzeile im Druck der Angebote geändert' in prot)

# ---------- Bankangaben nur für angemeldete Nutzer (der Server entscheidet) ----------
st, h, body = roh(ANON, 'offer')
oeff = json.loads(body)['fracht']['fuss']
check('öffentlich (ohne Anmeldung): Spalten 1 und 2 und Registerzeilen wie eingetragen, Spalte 3 nur die Vorgabe aus dem Impressum',
      st == 200 and oeff['spalten'][:2] == [SP1, SP2] and oeff['spalten'][2] == vorgabe['spalten'][2] and oeff['zeilen'] == [Z1, Z2], oeff)
check('öffentlich: Bankangaben nirgends in der Antwort, kein Sitzungs-Cookie, weiter zwischenspeicherbar', b'Testbank' not in body and b'TEST 0000' not in body and not h.get('Set-Cookie')
      and 'no-store' not in (h.get('Cache-Control') or '') and 'bankGeschuetzt' not in oeff, (h.get('Set-Cookie'), h.get('Cache-Control')))
etag_oeff = h.get('ETag')
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Druck GmbH', 'nr': 'KDRUCK', 'email': 'kantine.druck@example.org', 'active': True, 'angebote': ['edeka'], 'gruppe': '',
                              'login': {'username': 'kantine.druck', 'password': PW_L, 'mustChange': False, 'active': True}})
assert st == 200, r
kid = r['customer']['id']
K = Client('203.0.113.61'); assert K.call('kunde_login', {'username': 'kantine.druck', 'password': PW_L})[0] == 200
st, h, body = roh(K, 'offer')
check('angemeldeter Kunde: ganze Fußzeile im öffentlichen Wochenangebot, Antwort „private“, anderes ETag', st == 200 and json.loads(body)['fracht']['fuss']['spalten'] == [SP1, SP2, SP3]
      and 'private' in (h.get('Cache-Control') or '') and h.get('ETag') != etag_oeff, (h.get('Cache-Control'), h.get('ETag') == etag_oeff))
st, _, _ = roh(ANON, 'offer', {'If-None-Match': h.get('ETag')})
check('ETag eines Angemeldeten gilt ohne Anmeldung nicht (200 statt 304), das eigene schon', st == 200 and roh(ANON, 'offer', {'If-None-Match': etag_oeff})[0] == 304, st)
check('Kundenangebot und Entwurf (Mitarbeiter): ganze Fußzeile', K.call('offer&angebot=edeka')[1]['fracht']['fuss']['spalten'][2] == SP3
      and A.call('offer&draft=1')[1]['fracht']['fuss']['spalten'][2] == SP3 and L.call('offer')[1]['fracht']['fuss']['spalten'][2] == SP3)
st, r = A.call('druck_fuss_save', {'fuss': dict(neu, bankGeschuetzt=False)})
check('Schalter aus: Bankangaben auch öffentlich', st == 200 and r['fuss']['bankGeschuetzt'] is False and ANON.call('offer')[1]['fracht']['fuss']['spalten'] == [SP1, SP2, SP3])
check('… steht im Protokoll', 'Bankangaben nur für angemeldete Nutzer' in json.dumps(A.call('log')[1], ensure_ascii=False))
assert A.call('druck_fuss_save', {'fuss': dict(neu, bankGeschuetzt=True)})[0] == 200
check('Schalter wieder an: öffentlich ohne Bankangaben', ANON.call('offer')[1]['fracht']['fuss']['spalten'][2] == vorgabe['spalten'][2])

# ---------- Angebot für den Druck: Werbung, Sonderposten, „auf Anfrage“, Zusatzpreis ----------
d = A.call('draft')[1]
m = d['draft'] or d['published']
for k in ('savedAt', 'savedBy', 'publishedAt', 'rev'):
    m.pop(k, None)
its = m['items']
its[3]['name'] = 'Roastbeef mit Kette, 4 Rippen, ca. 6–8 kg, vakuumiert, Reifung 21 Tage, frisch'
for i in (7, 120):
    its[i]['price'] = {'status': 'request'}
SALE = [i for i in (5, 60, 130) if its[i]['price'].get('status') == 'value']
for i in SALE:
    its[i]['sale'] = {'value': round(its[i]['price']['value'] * 0.85, 2)}
m['meta']['werbung'] = {'std': {'titel': 'Unsere Empfehlung der Woche', 'text': 'Nur solange der Vorrat reicht.',
                               'artikel': [{'id': its[1]['id'], 'text': 'Top-Preis'}, {'id': its[30]['id']}, {'id': its[61]['id']}],
                               'weitere': [{'titel': 'Aktion der Woche', 'artikel': [{'id': its[150]['id']}, {'id': its[151]['id'], 'text': 'Grillsaison'}]}]}}
st, r = A.call('save_draft', {'model': m, 'revision': d['revision']})
assert st == 200, r
d = A.call('draft')[1]
st, r = A.call('publish', {'model': d['draft'], 'revision': d['revision']})
assert st == 200, r

# Einzelangebot mit 46 Positionen und eigenem Hinweis
bis = (date.today() + timedelta(days=20)).isoformat()
pos = [{'code': it.get('code') or '', 'name': it['name'], 'qty': 5 if n % 7 == 0 else None, 'price': round(8 + n * 0.37, 2) if n % 11 else None} for n, it in enumerate(its[:46])]
st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Grillsaison', 'gueltigBis': bis, 'hinweis': 'Lieferung nur dienstags', 'positions': pos})
assert st == 200, r
ez = A.call('einzel_status', {'id': r['angebot']['id'], 'revision': r['angebot']['revision'], 'status': 'freigegeben'})[1]['angebot']

errors = []
INIT = 'window.print = () => { window.__gedruckt = (window.__gedruckt || 0) + 1; };'

SATZ = """() => {
  const R = document.querySelector('#print-root'), D = R.querySelector('.pl-doc');
  if (!D) return null;
  const pages = [...D.querySelectorAll('.pl-page')];
  const box = (e) => e.getBoundingClientRect();
  return {
    seiten: pages.length, spalten: +D.dataset.spalten, fuss: D.dataset.fuss, seitenAttr: +D.dataset.seiten,
    zeilen: [...D.querySelectorAll('.pl-cols tr.row')].map((r) => r.dataset.id),
    werb: [...D.querySelectorAll('.pl-werb tr.row')].map((r) => r.dataset.id),
    gruppen: [...D.querySelectorAll('.pl-cols .al-gt')].filter((g) => !g.querySelector('.al-cont')).map((g) => g.textContent.trim()),
    forts: D.querySelectorAll('.pl-cols .al-cont').length,
    bereiche: [...D.querySelectorAll('.pl-st h3')].map((h) => h.textContent.trim()),
    jeSeite: pages.map((p) => {
      const pb = box(p), f = p.querySelector(':scope > .pl-fuss'), cols = [...p.querySelectorAll('.pl-col')];
      const unten = Math.max(0, ...cols.map((c) => (c.lastElementChild ? box(c.lastElementChild).bottom : pb.top)));
      const hin = f && f.querySelector('.pl-hinweis'), br = f && f.querySelector('.pl-brief'), si = f && f.querySelector('.pl-siegel');
      return { h: pb.height, b: pb.width, spalten: cols.length, bereiche: p.querySelectorAll('.pl-st').length, kopf: (p.querySelector('.pl-ph') || {}).innerText || '',
        logo: p.querySelectorAll('img.al-logo').length, werb: p.querySelectorAll('.pl-werb').length,
        ueber: unten - (f ? box(f).top : pb.bottom), spaltenUnten: cols.map((c) => (c.lastElementChild ? Math.round(box(c.lastElementChild).bottom - pb.top) : 0)),
        fuss: f ? { unten: pb.bottom - box(f).bottom, links: box(br).left - pb.left, rechts: pb.right - box(br).right, hinweisUeber: hin && br ? box(br).top - box(hin).bottom : null,
          hinweis: hin ? hin.innerText : '', brief: br ? br.innerText : '', siegel: !!(si && si.complete && si.naturalWidth > 0), hinweisMitte: hin ? Math.abs((box(hin).left + box(hin).right) / 2 - (pb.left + pb.right) / 2) : null } : null };
    }),
    schrift: Math.min(...[...D.querySelectorAll('.pl-cols td, .pl-cols th, .pl-st h3')].filter((e) => e.textContent.trim()).map((e) => parseFloat(getComputedStyle(e).fontSize))),
    farben: { adjust: getComputedStyle(D).printColorAdjust || getComputedStyle(D).webkitPrintColorAdjust, marke: (D.querySelector('.al-brand') ? getComputedStyle(D.querySelector('.al-brand')).color : ''),
      band: (D.querySelector('.pl-st') ? getComputedStyle(D.querySelector('.pl-st')).backgroundColor : ''), werb: (D.querySelector('.werb-st') ? getComputedStyle(D.querySelector('.werb-st')).backgroundColor : ''),
      sonder: (D.querySelector('.al-sale') ? getComputedStyle(D.querySelector('.al-sale')).color : ''), umbruch: (D.querySelector('.pl-st') ? getComputedStyle(D.querySelector('.pl-st')).breakBefore : ''),
      schema: getComputedStyle(document.documentElement).colorScheme },
    text: D.innerText,
  };
}"""


def satz(pg, wie='beforeprint'):
    """Druckfassung setzen (wie Strg+P) und im Druckmedium vermessen"""
    if wie:
        pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pg.wait_for_selector('#print-root .pl-doc .pl-page', state='attached')
    pg.wait_for_function("[...document.querySelectorAll('#print-root img')].every((i) => i.complete)")
    pg.emulate_media(media='print')
    s = pg.evaluate(SATZ)
    return s


def zurueck(pg):
    pg.emulate_media(media='screen')
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")


with sync_playwright() as p:
    br = p.chromium.launch()

    # ---------- Angebotsseite (öffentlich): Druck = Angebotsansicht am Bildschirm ----------
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    pg.goto(BASE + '/'); pg.wait_for_selector('.al tr.row')
    schirm = pg.evaluate("""() => ({ zeilen: [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id), werb: [...document.querySelectorAll('#list .werb-sec tr.row, #list .al-werb tr.row')].map((r) => r.dataset.id),
      gruppen: [...document.querySelectorAll('#list .al-band .al-gt')].map((g) => g.textContent.trim()), bereiche: [...document.querySelectorAll('#list .al-band .al-st:not(.al-st-leer) h3')].map((h) => h.textContent.trim()),
      sonder: document.querySelectorAll('#list .al-band .al-sale').length, anfrage: document.querySelectorAll('#list .al-band td.al-np').length, alle: document.querySelectorAll('#list tr.row').length,
      hinweis: (document.querySelector('#list .al-note') || {}).innerText || '' })""")
    s = satz(pg)
    check('Druck-DOM: jeder Artikel der Angebotsansicht genau einmal, in derselben Reihenfolge', len(schirm['zeilen']) == 276 and s['zeilen'] == schirm['zeilen'], (len(s['zeilen']), len(schirm['zeilen'])))
    check('Druck-DOM: dieselben Gruppen und Bereiche in derselben Reihenfolge', s['gruppen'] == schirm['gruppen'] and len(s['gruppen']) == 32 and s['bereiche'] == schirm['bereiche'] and len(s['bereiche']) == 4,
          (len(s['gruppen']), len(schirm['gruppen']), s['bereiche']))
    werb_schirm = schirm['alle'] - len(schirm['zeilen'])
    check('Druck-DOM: Werbung wie am Bildschirm (beide Bänder, alle beworbenen Artikel) auf der ersten Seite', len(s['werb']) == 5 == werb_schirm and s['jeSeite'][0]['werb'] == 1
          and sum(x['werb'] for x in s['jeSeite']) == 1 and 'Unsere Empfehlung der Woche' in s['text'] and 'Aktion der Woche' in s['text'] and 'Top-Preis' in s['text'], (len(s['werb']), werb_schirm))
    pd = pg.evaluate("""() => ({ sonder: document.querySelectorAll('#print-root .pl-cols .al-sale').length, was: document.querySelectorAll('#print-root .pl-cols .al-was').length,
      anfrage: document.querySelectorAll('#print-root .pl-cols td.al-np').length, tags: document.querySelectorAll('#print-root .pl-cols .tag.sale').length, an: document.querySelectorAll('#print-root .pl-cols tr.werb-an').length,
      bedien: document.querySelectorAll('#print-root .star, #print-root .qty, #print-root button, #print-root input').length })""")
    check('Druck-DOM: Hervorhebungen wie am Bildschirm (Sonderposten mit bisherigem Preis, „a. Anfr.“, beworbene Zeilen), keine Bedienelemente',
          pd['sonder'] == schirm['sonder'] == len(SALE) and pd['was'] == len(SALE) and pd['tags'] == len(SALE) and pd['anfrage'] == schirm['anfrage'] >= 2 and pd['an'] == 5 and pd['bedien'] == 0, (pd, schirm['sonder'], schirm['anfrage']))
    fb = s['farben']
    check('Farben aktiv: print-color-adjust „exact“, Marke bordeaux, Bereichs- und Werbeband getönt, Sonderpreis farbig, helles Schema',
          fb['adjust'] == 'exact' and fb['marke'] == 'rgb(140, 29, 44)' and fb['band'] not in ('rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)')
          and fb['werb'] not in ('rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)') and fb['sonder'] == 'rgb(194, 65, 12)' and fb['schema'] == 'light', fb)
    N = s['seiten']
    check('kein Seitenumbruch je Bereich: weniger Seiten als Bereiche, mehrere Bereiche auf einer Seite, break-before „auto“',
          N < len(s['bereiche']) and max(x['bereiche'] for x in s['jeSeite']) >= 2 and fb['umbruch'] == 'auto', (N, [x['bereiche'] for x in s['jeSeite']]))
    check('kompakt: höchstens 4 Seiten (bisher 6 mit einer Seite je Bereich), drei oder vier Spalten je Seite', N <= 4 and s['spalten'] in (3, 4) and all(x['spalten'] == s['spalten'] for x in s['jeSeite'])
          and s['seitenAttr'] == N, (N, s['spalten']))
    check('Seiten fester Größe (Satzspiegel 279 × 193 mm), nichts läuft über den Seitenfuß', all(abs(x['h'] - 193 * MM) < 1 and abs(x['b'] - 279 * MM) < 1 and x['ueber'] <= 0.5 for x in s['jeSeite']),
          [(round(x['h']), round(x['ueber'], 1)) for x in s['jeSeite']])
    check('Gruppen nicht geteilt (keine „Forts.“ – jede Gruppe passt in eine Spalte)', s['forts'] == 0, s['forts'])
    check('Kopf: Logo nur auf Seite 1, jede Seite mit Titel, Angebotswoche bzw. Stand und „Seite x von y“',
          [x['logo'] for x in s['jeSeite']] == [1] + [0] * (N - 1) and all(f'Seite {i + 1} von {N}' in x['kopf'] and 'KW 43' in x['kopf'] and 'Stand ' in x['kopf'] for i, x in enumerate(s['jeSeite'])), s['jeSeite'][0]['kopf'])
    check('Schrift nicht unter 7,5 pt (10 px)', s['schrift'] >= 10 - .01, s['schrift'])
    letzte = s['jeSeite'][-1]['spaltenUnten']
    check('letzte Seite ausgeglichen: alle Spalten belegt, keine fast leer', all(u > 0 for u in letzte) and min(letzte) >= max(letzte) * .45, letzte)
    check('GR-001/GR-008: Druck ohne Mengen, Partien, MHD und Einkaufspreise', not re.search(r'Bestand|Partie|MHD|Einkauf|EK-Preis', s['text']) and pg.locator('#print-root [data-qty], #print-root .c-qty').count() == 0)
    # Fußzeile auf jeder Seite (Vorgabe „jede“)
    f1 = [x['fuss'] for x in s['jeSeite']]
    check('Variante „jede Seite“: Fußzeile mit Hinweis am Fuß jeder Seite', s['fuss'] == 'jede' and all(f1) and all(abs(x['unten']) <= 1 for x in f1), [x and round(x['unten'], 1) for x in f1])
    check('Fußzeile über die ganze Breite, Hinweis mittig darüber, Siegel geladen', all(abs(x['links']) <= 1 and abs(x['rechts']) <= 1 and x['hinweisMitte'] <= 1 and 0 <= x['hinweisUeber'] <= 12 and x['siegel'] for x in f1),
          [(round(x['links'], 1), round(x['rechts'], 1), round(x['hinweisUeber'], 1)) for x in f1])
    hin = off0['fracht']['hinweis'][:2]
    check('Hinweis = „Fracht und Hinweis im Angebot“ (Mindestmenge, Frachtanteil) und derselbe Text wie am Bildschirm', all(z in f1[0]['hinweis'] for z in hin) and 'Telefon Test: 000 - 00 00 00' in f1[0]['hinweis']
          and all(z in schirm['hinweis'] for z in hin), f1[0]['hinweis'][:120])
    check('Fußzeile: drei Spalten und zwei Registerzeilen aus der Einstellung; öffentlich ohne Bankangaben', all(t in f1[0]['brief'] for t in ('Musterfleisch Test GmbH', 'www.example.org', 'Musterstadt B 000 00', 'Musterstadt A 000 00'))
          and 'Testbank' not in s['text'] and 'DE 118949959' in f1[0]['brief'], f1[0]['brief'][:200])
    pdf = pg.pdf(prefer_css_page_size=True, print_background=False)
    open(SH + '/druck-jede-seite.pdf', 'wb').write(pdf)
    boxes = [tuple(float(v) for v in mm.groups()) for mm in re.finditer(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)', pdf)]
    check('PDF: A4 quer, genau so viele Seiten wie gesetzt (nichts läuft über)', pdf_seiten(pdf) == N and boxes and all(w > h for w, h in boxes), (pdf_seiten(pdf), N, boxes[:1]))
    check('PDF auch ohne „Hintergrundgrafiken“ farbig (Bänder, Marke, Sonderposten)', pdf_farbig(pdf) >= 10, pdf_farbig(pdf))
    for i, nr in ((0, 's1'), (N - 1, 'letzte')):
        shot(pg.locator('#print-root .pl-page').nth(i), f'{SH}/druck-jede-seite-{nr}.png')
    zurueck(pg)
    check('nach dem Druck ist die Druckfassung wieder entfernt', pg.locator('#print-root .pl-page').count() == 0 and pg.locator('.al tr.row').count() == schirm['alle'])

    # Variante „nur letzte Seite“ (?fuss=letzte) und über die Einstellung
    pg.goto(BASE + '/?fuss=letzte'); pg.wait_for_selector('.al tr.row')
    s2 = satz(pg)
    f2 = [x['fuss'] for x in s2['jeSeite']]
    check('Variante „nur letzte Seite“: Fußzeile mit Hinweis nur am Fuß der letzten Seite', s2['fuss'] == 'letzte' and all(x is None for x in f2[:-1]) and f2[-1] and abs(f2[-1]['unten']) <= 1
          and all(z in f2[-1]['hinweis'] for z in hin), [bool(x) for x in f2])
    check('… vollständig, nichts läuft über, nicht mehr Seiten als mit Fußzeile auf jeder Seite', s2['zeilen'] == schirm['zeilen'] and all(x['ueber'] <= 0.5 for x in s2['jeSeite']) and s2['seiten'] <= N, (s2['seiten'], N))
    pdf2 = pg.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-letzte-seite.pdf', 'wb').write(pdf2)
    check('PDF „nur letzte Seite“: Seiten wie gesetzt', pdf_seiten(pdf2) == s2['seiten'], (pdf_seiten(pdf2), s2['seiten']))
    shot(pg.locator('#print-root .pl-page').last, f'{SH}/druck-letzte-seite-letzte.png')
    zurueck(pg)
    assert A.call('druck_fuss_save', {'fuss': dict(neu, modus='letzte')})[0] == 200
    pg.goto(BASE + '/?r=modus'); pg.wait_for_selector('.al tr.row')
    s3 = satz(pg)
    check('Einstellung „nur auf der letzten Seite“ wirkt ohne Parameter; ?fuss=jede schaltet für den Vergleich um', s3['fuss'] == 'letzte' and [bool(x['fuss']) for x in s3['jeSeite']] == [False] * (s3['seiten'] - 1) + [True], s3['fuss'])
    zurueck(pg)
    pg.goto(BASE + '/?fuss=jede&spalten=3'); pg.wait_for_selector('.al tr.row')
    s4 = satz(pg)
    check('… und ?spalten=3 legt die Spaltenzahl fest', s4['fuss'] == 'jede' and all(x['fuss'] for x in s4['jeSeite']) and s4['spalten'] == 3 and all(x['ueber'] <= 0.5 for x in s4['jeSeite']), (s4['fuss'], s4['spalten']))
    zurueck(pg)
    assert A.call('druck_fuss_save', {'fuss': neu})[0] == 200

    # Auswahl und Merkliste: nur die gewählten Artikel, ohne Werbung; ungegliedert: eine Liste über alle Spalten
    pg.goto(BASE + '/'); pg.wait_for_selector('.al tr.row')
    pg.fill('#q', 'Roastbeef'); pg.wait_for_function("document.querySelectorAll('#list .al-band tr.row').length < 60")
    treffer = pg.locator('#list .al-band tr.row').count()
    s5 = satz(pg)
    check('Auswahl drucken (Suche): nur die Treffer, ohne Werbung, Auswahl im Kopf genannt', len(s5['zeilen']) == treffer and 0 < treffer < 60 and not s5['werb'] and 'Roastbeef' in s5['jeSeite'][0]['kopf'] and s5['seiten'] == 1,
          (len(s5['zeilen']), treffer, s5['jeSeite'][0]['kopf']))
    zurueck(pg)
    pg.fill('#q', ''); pg.wait_for_function("document.querySelectorAll('#list .al-band tr.row').length === 276")
    pg.click('#btn-print'); pg.wait_for_selector('#dlg-print[open]')
    check('Druckdialog: „Angebotsansicht, A4 quer“ ist die Vorgabe und nennt Werbung, Hinweis und Fußzeile', pg.is_checked('#dlg-print input[name=layout][value=liste]')
          and 'Fußzeile' in pg.inner_text('#dlg-print label:has(input[name=layout][value=liste])'), pg.inner_text('#dlg-print label:has(input[name=layout][value=liste])'))
    pg.evaluate("""() => { const f = document.querySelector('#print-form'); f.querySelector('input[name=scope][value=all]').checked = true; f.querySelector('input[name=layout][value=liste]').checked = true;
      f.querySelector('input[name=grouped]').checked = false; f.requestSubmit(); }""")
    pg.wait_for_function('window.__gedruckt >= 1')
    s6 = satz(pg, wie='')
    check('ungegliedert: alle Artikel als eine Liste über die Spalten verteilt („Forts.“), nichts läuft über', len(s6['zeilen']) == 276 and s6['forts'] >= 2 and s6['gruppen'] and all(x['ueber'] <= 0.5 for x in s6['jeSeite']) and s6['seiten'] <= 4,
          (len(s6['zeilen']), s6['forts'], s6['seiten']))
    zurueck(pg)
    # Hochformat (Kompakt, Tabelle): Fußzeile einmal am Ende
    for layout, sel in (('compact', '.p-row'), ('table', '.p-table tbody tr:not(.gr):not(.sr)')):
        pg.evaluate("""(l) => { const f = document.querySelector('#print-form'); f.querySelector('input[name=scope][value=all]').checked = true; f.querySelector(`input[name=layout][value=${l}]`).checked = true;
          f.querySelector('input[name=grouped]').checked = true; f.requestSubmit(); }""", layout)
        pg.wait_for_selector('#print-root .p-doc', state='attached')
        hf = pg.evaluate("""() => { const d = document.querySelector('#print-root .p-doc'), f = d.querySelectorAll('.pl-fuss'); return { n: f.length, hoch: f.length ? f[0].classList.contains('pl-fuss-hoch') : false,
          letzt: f.length ? d.lastElementChild === f[0] : false, brief: f.length ? f[0].innerText : '', note: d.querySelectorAll('.al-note').length } }""")
        check(f'Hochformat „{layout}“: alle Artikel, Hinweis und einmal die Fußzeile am Ende', pg.locator('#print-root ' + sel).count() == 276 and hf['n'] == 1 and hf['hoch'] and hf['letzt'] and hf['note'] == 1
              and 'Musterfleisch Test GmbH' in hf['brief'] and 'Musterstadt A 000 00' in hf['brief'], hf)
        pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    ctx.close()

    # ---------- Viele Bereiche (wie mit Angebotskategorien): fortlaufend statt 15 Seiten ----------
    d = A.call('draft')[1]
    m2 = d['draft'] or d['published']
    for k in ('savedAt', 'savedBy', 'publishedAt', 'rev'):
        m2.pop(k, None)
    BER = ['Eigene Zerlegung, Marke "Fleischmeister"', 'Färse und Ochse', 'Kalb "Fleischmeister"', 'Rindfleisch EU', 'Schwein', 'Neuseeland und Australien', 'Kalbfleisch',
           'Charoluxe und Geflügel', 'Südamerika', 'Iberico und Spanferkel', 'Grain Fed', 'Irland', 'Gefrierfleisch', 'Gefrierfleisch Rind und Schwein']
    for i, g in enumerate(m2['groups']):
        g['section'] = BER[min(len(BER) - 1, i * len(BER) // len(m2['groups']))]
    m2['groups'][-1]['section'] = ''
    # eine Gruppe, die länger als eine Spalte ist: wird geteilt und trägt „Forts.“
    g1 = m2['groups'][0]['id']
    vor = [it for it in m2['items'] if it['groupId'] == g1]
    extra = [dict(it, id=f"{it['id']}x{n}", code=str(int(it['code']) + 1000 * n) if it.get('code') else None, name=it['name'] + f', Zuschnitt {n}') for n in range(1, 6) for it in vor]
    for it in extra:
        it.pop('sale', None)
    stelle = max(k for k, it in enumerate(m2['items']) if it['groupId'] == g1) + 1
    m2['items'][stelle:stelle] = extra
    GESAMT = len(m2['items'])
    st, r = A.call('save_draft', {'model': m2, 'revision': d['revision']})
    assert st == 200, r

    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    v = ctx.new_page(); v.on('pageerror', lambda ex: errors.append(str(ex)))
    v.goto(BASE + '/admin/'); v.wait_for_selector('#screen-auth:not([hidden])')
    v.fill('#au-user', 'admin'); v.fill('#pw1', PW); v.click('#auth-submit'); v.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    v.goto(BASE + '/?vorschau=1'); v.wait_for_selector('.al tr.row')
    vs = v.evaluate("""() => ({ zeilen: [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id), gruppen: [...document.querySelectorAll('#list .al-band .al-gt')].map((g) => g.textContent.trim()),
      bereiche: [...document.querySelectorAll('#list .al-band .al-st:not(.al-st-leer) h3')].map((h) => h.textContent.trim()) })""")
    s7 = satz(v)
    check('Entwurf mit 14 Bereichen: Druck vollständig wie die Vorschau (Artikel, Gruppen, Bereiche, Reihenfolge)', len(vs['zeilen']) == GESAMT and s7['zeilen'] == vs['zeilen'] and s7['gruppen'] == vs['gruppen']
          and s7['bereiche'] == vs['bereiche'] and len(s7['bereiche']) == 14, (len(s7['zeilen']), GESAMT, len(s7['bereiche'])))
    check('… höchstens 5 Seiten statt einer Seite je Bereich, mehrere Bereiche je Seite, nichts läuft über', s7['seiten'] <= 5 and max(x['bereiche'] for x in s7['jeSeite']) >= 3 and all(x['ueber'] <= 0.5 for x in s7['jeSeite']),
          (s7['seiten'], [x['bereiche'] for x in s7['jeSeite']]))
    lang = v.evaluate("""() => { const k = [...document.querySelectorAll('#print-root .pl-cols .al-grp')].filter((g) => g.querySelector('.al-cont')); return { teile: k.length, min: Math.min(...k.map((g) => g.querySelectorAll('tr.row').length)),
      kopf: k.length ? k[0].querySelector('.al-gt').textContent : '' } }""")
    check('Gruppe länger als eine Spalte: geteilt mit „Forts.“ im wiederholten Gruppenkopf, nie weniger als 3 Zeilen', s7['forts'] >= 1 and lang['teile'] == s7['forts'] and lang['min'] >= 3 and 'Forts.' in lang['kopf'], lang)
    haengt = v.evaluate("""() => [...document.querySelectorAll('#print-root .pl-col')].filter((c) => c.lastElementChild && c.lastElementChild.classList.contains('pl-st')).length""")
    check('Bereichsüberschrift steht nie allein am Spaltenende (bleibt bei ihrer ersten Gruppe)', haengt == 0, haengt)
    check('Vermerk „Entwurf“ im Kopf ist vorbereitet, aber ausgeschaltet; Mitarbeiter sehen die ganze Fußzeile', v.locator('#print-root .pl-entwurf').count() == 0 and 'Testbank Musterstadt' in s7['jeSeite'][0]['fuss']['brief'])
    pdf7 = v.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-viele-bereiche.pdf', 'wb').write(pdf7)
    check('PDF mit vielen Bereichen: Seiten wie gesetzt', pdf_seiten(pdf7) == s7['seiten'], (pdf_seiten(pdf7), s7['seiten']))
    shot(v.locator('#print-root .pl-page').first, SH + '/druck-viele-bereiche-s1.png')
    zurueck(v)

    # ---------- Einzelangebot: Druck der Angebotsseite und PDF des Servers ----------
    v.goto(BASE + '/?angebot=e-' + ez['id']); v.wait_for_selector('.al tr.row')
    s8 = satz(v)
    f8 = s8['jeSeite'][-1]['fuss']
    check('Einzelangebot: alle 46 Positionen auf einer Seite, über die Spalten verteilt, ohne Werbung', len(s8['zeilen']) == 46 and s8['seiten'] == 1 and all(u > 0 for u in s8['jeSeite'][0]['spaltenUnten']) and not s8['werb']
          and s8['jeSeite'][0]['ueber'] <= 0.5, (len(s8['zeilen']), s8['seiten'], s8['jeSeite'][0]['spaltenUnten']))
    check('Einzelangebot: Kopf mit Angebotsnummer und Kunde, Seite 1 von 1', ez['nr'] in s8['jeSeite'][0]['kopf'] and 'Kantine Druck GmbH' in s8['jeSeite'][0]['kopf'] and 'Seite 1 von 1' in s8['jeSeite'][0]['kopf'], s8['jeSeite'][0]['kopf'])
    check('Einzelangebot: eigener Hinweis vor dem Hinweis zu Mengen und Fracht, darunter die Fußzeile', f8 and 'Lieferung nur dienstags' in f8['hinweis'] and f8['hinweis'].index('Lieferung nur dienstags') < f8['hinweis'].index('Die Preise verstehen sich')
          and 'Musterfleisch Test GmbH' in f8['brief'] and 'Testbank Musterstadt' in f8['brief'] and abs(f8['unten']) <= 1, f8 and f8['hinweis'][:100])
    check('Einzelangebot: nur eigene Preise, kein Bestand', 'P-0001' not in s8['text'] and not re.search(r'Bestand|Partie|MHD', s8['text']))
    pdf8 = v.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-einzelangebot.pdf', 'wb').write(pdf8)
    check('Einzelangebot-PDF (Browser): eine Seite', pdf_seiten(pdf8) == 1, pdf_seiten(pdf8))
    shot(v.locator('#print-root .pl-page').first, SH + '/druck-einzelangebot.png')
    zurueck(v)
    st, h, spdf = roh(A, 'einzel_pdf&id=' + ez['id'])
    inh = pdf_text(spdf) if st == 200 else ''
    open(SH + '/druck-einzelangebot-server.pdf', 'wb').write(spdf)
    check('PDF des Servers (E-Mail-Anhang, PDF-Vorschau): Fußzeile mit drei Spalten und Registerzeilen, Siegel eingebettet', st == 200 and all(t in inh for t in ('Musterfleisch Test GmbH', 'www.example.org', 'Testbank Musterstadt',
          'Musterstadt B 000 00', 'Beispiel Verwaltung mbH')) and spdf.count(b'/Subtype /Image') == 2, (st, spdf.count(b'/Subtype /Image')))
    n_jede = pdf_seiten(spdf)
    check('… Variante „jede Seite“: Fußzeile so oft wie Seiten; Hinweis zu Mengen und Fracht einmal', inh.count('Musterfleisch Test GmbH') == n_jede and inh.count('Mindestbestellmenge von ca. 300 kg') == 1 and 'Lieferung nur dienstags' in inh,
          (inh.count('Musterfleisch Test GmbH'), n_jede))
    # langes Einzelangebot über mehrere Seiten, Variante „letzte“
    pos2 = [{'code': str(20000 + n), 'name': f'Testposition {n} mit etwas längerer Bezeichnung, vakuumiert', 'qty': None, 'price': 9.5} for n in range(190)]
    st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Großes Angebot', 'gueltigBis': bis, 'hinweis': '', 'positions': pos2})
    assert st == 200, r
    ez2 = r['angebot']
    j = pdf_text(roh(A, 'einzel_pdf&id=' + ez2['id'])[2]); nj = pdf_seiten(roh(A, 'einzel_pdf&id=' + ez2['id'])[2])
    assert A.call('druck_fuss_save', {'fuss': dict(neu, modus='letzte')})[0] == 200
    lz = roh(A, 'einzel_pdf&id=' + ez2['id'])[2]; lt = pdf_text(lz); nl = pdf_seiten(lz)
    check('PDF des Servers über mehrere Seiten: „jede“ = Fußzeile je Seite, „letzte“ = einmal; alle Positionen, Seitenzahl stimmt', nj >= 2 and j.count('Musterfleisch Test GmbH') == nj and lt.count('Musterfleisch Test GmbH') == 1
          and nl <= nj and all(f'Testposition {n} ' in lt for n in (0, 95, 189)) and f'Seite {nl} von {nl}' in lt and f'Seite {nj} von {nj}' in j, (nj, nl, j.count('Musterfleisch Test GmbH'), lt.count('Musterfleisch Test GmbH')))
    assert A.call('druck_fuss_save', {'fuss': {'spalten': ['', '', ''], 'zeilen': ['', ''], 'modus': 'jede'}})[0] == 200
    leer = A.call('druck_fuss')[1]['fuss']
    check('leere Felder: wieder die Vorgabe (Impressum), auch im PDF des Servers', leer['eigen'] is False and leer['spalten'] == vorgabe['spalten'] and 'Lagerstraße 17' in pdf_text(roh(A, 'einzel_pdf&id=' + ez['id'])[2])
          and ANON.call('offer')[1]['fracht']['fuss']['spalten'] == vorgabe['spalten'], leer)
    assert A.call('druck_fuss_save', {'fuss': neu})[0] == 200
    ctx.close()

    # ---------- Eingabebereich: Knopf „Drucken“, Vorschau, Fenster „Fußzeile im Druck“ ----------
    def anmelden(c, user, pw):
        a = c.new_page(); a.on('pageerror', lambda ex: errors.append(str(ex)))
        a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
        a.fill('#au-user', user); a.fill('#pw1', pw); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return a

    def rahmen(a):
        """Unsichtbarer Rahmen mit der Druckfassung: wartet auf den Druckaufruf"""
        a.wait_for_selector('#druck-frame', state='attached')
        fr = a.locator('#druck-frame').element_handle().content_frame()
        fr.wait_for_function('window.__gedruckt >= 1', timeout=20000)
        return fr

    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    a = anmelden(ctx, 'admin', PW)
    lage = a.evaluate("""() => { const d = document.querySelector('#btn-drucken'), s = document.querySelector('#btn-send'), p = document.querySelector('#btn-publish'), r = (e) => e.getBoundingClientRect();
      return { text: d.innerText.trim(), sichtbar: r(d).width > 0, vorSend: !!(d.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING), vorPub: !!(d.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING),
        links: r(d).right <= r(p).left + 1, zeile: Math.abs(r(d).top - r(p).top) < 4, hoehe: Math.abs(r(d).height - r(p).height) < 2, titel: d.title, send: !!s, pub: r(p).width > 0 }; }""")
    check('Knopf „Drucken“ in der Leiste von „Angebot bearbeiten“, links neben „An Kunden senden“ und „Veröffentlichen“ (gleiche Zeile und Höhe)',
          lage['text'] == 'Drucken' and lage['sichtbar'] and lage['vorSend'] and lage['vorPub'] and lage['links'] and lage['zeile'] and lage['hoehe'] and lage['send'] and lage['pub'], lage)
    check('… Beschriftung sagt, was gedruckt wird (gewähltes Angebot, Entwurf wie in der Vorschau)', 'Gewähltes Angebot' in lage['titel'] and 'Entwurf' in lage['titel'] and 'Vorschau' in lage['titel'], lage['titel'])
    shot(a.locator('#topbar'), SH + '/druck-knopf-1440.png')
    a.click('#btn-drucken')
    fr = rahmen(a)
    fs = fr.evaluate("""() => ({ seiten: document.querySelectorAll('#print-root .pl-page').length, zeilen: document.querySelectorAll('#print-root .pl-cols tr.row').length, n: window.__gedruckt, url: location.search,
      fuss: document.querySelectorAll('#print-root .pl-page > .pl-fuss').length, vorschau: new URLSearchParams(location.search).has('vorschau') })""")
    check('„Drucken“ setzt den Entwurf des Wochenangebots in der Angebotsansicht (alle Artikel, Fußzeile) und ruft den Druck genau einmal auf',
          fs['zeilen'] == GESAMT and fs['seiten'] >= 2 and fs['n'] == 1 and fs['fuss'] == fs['seiten'] and fs['vorschau'] and 'drucken' not in fs['url'] and 'angebot=' not in fs['url'], fs)
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    check('Eingabebereich selbst druckt nicht, Knopf danach wieder frei, Rahmen unsichtbar', a.evaluate('window.__gedruckt || 0') == 0 and not a.locator('#btn-drucken').is_disabled()
          and a.evaluate("(() => { const r = document.querySelector('#druck-frame').getBoundingClientRect(); return r.right <= 0 && r.width >= 1000; })()"))
    # ungespeicherte Änderung: vor dem Druck gespeichert, der Ausdruck zeigt sie
    erste = a.locator('#groups tr[data-id]').first
    code1 = erste.locator('input[data-f="code"]').input_value()
    feld = erste.locator('input[data-f="price"]')
    feld.fill('99,91')
    a.click('#btn-drucken')
    fr = rahmen(a)
    zeile = fr.evaluate("""(c) => { const r = [...document.querySelectorAll('#print-root .pl-cols tr.row')].find((x) => x.querySelector('.c-code').textContent.trim() === c); return r ? r.innerText : ''; }""", code1)
    d2 = A.call('draft')[1]
    check('ungespeicherte Eingabe wird vor dem Druck gespeichert und steht im Ausdruck', '99,91' in zeile and any(it.get('code') == code1 and it['price'].get('value') == 99.91 for it in d2['draft']['items']), zeile)
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    # gewähltes Kundenangebot
    a.locator('#offer-bar [data-offer]:has-text("Edeka")').first.click(); a.wait_for_selector('#offer-bar [data-offer="edeka"][aria-selected="true"]')
    a.click('#btn-drucken')
    fr = rahmen(a)
    fe = fr.evaluate("""() => ({ url: location.search, kopf: document.querySelector('#print-root .pl-ph').innerText, zeilen: document.querySelectorAll('#print-root .pl-cols tr.row').length })""")
    ed = A.call('offer&angebot=edeka&draft=1')[1]['offer']
    check('gewähltes Kundenangebot: „Drucken“ druckt dessen Entwurf (Name im Kopf, seine Artikel)', 'angebot=edeka' in fe['url'] and 'Edeka' in fe['kopf'] and fe['zeilen'] == len(ed['items']) > 0, (fe['url'], fe['kopf'], fe['zeilen'], len(ed['items'])))
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    # Schnittstelle für andere Module (Versand: „Angebote dieser Woche“): veröffentlichter Stand eines beliebigen Angebots
    a.evaluate("window.WA.angebot.druck.drucken({ angebot: 'std', name: 'Wochenangebot' })")
    fr = rahmen(a)
    fv = fr.evaluate("""() => ({ vorschau: new URLSearchParams(location.search).has('vorschau'), zeilen: document.querySelectorAll('#print-root .pl-cols tr.row').length, n: window.__gedruckt })""")
    check('Schnittstelle WA.angebot.druck.drucken({angebot}): druckt den veröffentlichten Stand (nicht den Entwurf) in derselben Fassung', fv['vorschau'] is False and fv['zeilen'] == 276 and fv['n'] == 1, fv)
    a.evaluate("window.WA.angebot.druck.drucken({ angebot: 'edeka', entwurf: true })")
    fr = rahmen(a)
    check('… mit entwurf: true den Entwurf des genannten Angebots', fr.evaluate("new URLSearchParams(location.search).has('vorschau') && location.search.includes('angebot=edeka')"))
    a.evaluate("window.WA.angebot.druck.drucken({ angebot: 'gibt-es-nicht' })")
    a.wait_for_function("/konnte nicht geladen werden/.test(document.querySelector('#toast').textContent)", timeout=10000)
    check('unbekanntes Angebot: Meldung statt Druck (die Seite meldet den Fehler)', True)
    # Vorschaufenster: „Drucken“ druckt die Vorschau, nicht den Eingabebereich
    a.locator('#offer-bar [data-offer="std"]').first.click(); a.wait_for_selector('#offer-bar [data-offer="std"][aria-selected="true"]')
    a.click('#btn-preview'); a.wait_for_selector('#pv-stage:not(.laden)')
    pv = a.locator('#pv-frame').element_handle().content_frame()
    pv.wait_for_selector('.al tr.row')
    a.click('#pv-drucken')
    pv.wait_for_function('window.__gedruckt >= 1')
    pvs = pv.evaluate("""() => ({ seiten: document.querySelectorAll('#print-root .pl-page').length, zeilen: document.querySelectorAll('#print-root .pl-cols tr.row').length })""")
    check('Vorschaufenster: „Drucken“ druckt die Vorschau in der Angebotsansicht, der Eingabebereich druckt nicht', pvs['zeilen'] == GESAMT and pvs['seiten'] >= 2 and a.evaluate('window.__gedruckt || 0') == 0, pvs)
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-vorschau', state='hidden')
    # Fenster „Fußzeile im Druck“
    a.click('#btn-more'); a.wait_for_selector('#menu-more [data-act="druck-fuss"]:not([hidden])')
    a.click('#menu-more [data-act="druck-fuss"]'); a.wait_for_selector('#dlg-druck-fuss[open] textarea[name=s0]')
    df = a.evaluate("""() => { const f = document.querySelector('#druck-fuss-body').elements; return { s0: f.s0.value, s2: f.s2.value, z1: f.z1.value, modus: f.modus.value, bank: f.bank.checked,
      hinweis: document.querySelector('.df-hinweis p').innerText, platz: f.s0.placeholder }; }""")
    check('Fenster „Fußzeile im Druck“ (Administrator): gespeicherte Texte, Wahl jede/letzte Seite, Bankschalter an, Hinweis zur Ansicht, Vorgabe als Platzhalter',
          df['s0'] == SP1 and df['s2'] == SP3 and df['z1'] == Z2 and df['modus'] == 'jede' and df['bank'] is True and 'Mindestbestellmenge' in df['hinweis'] and 'Lagerstraße 17' in df['platz'], df)
    shot(a.locator('#dlg-druck-fuss'), SH + '/druck-fusszeile-fenster.png')
    a.fill('#druck-fuss-body textarea[name=s1]', SP2 + '\nFax 000 - 00 00 01')
    a.check('#druck-fuss-body input[name=modus][value=letzte]')
    a.click('#df-ok'); a.wait_for_selector('#dlg-druck-fuss', state='hidden')
    g = doc('fracht')['druck']
    check('Speichern im Fenster: Text und Variante gespeichert, Bankschalter bleibt an', g['spalten'][1].endswith('Fax 000 - 00 00 01') and g['modus'] == 'letzte' and g['bankGeschuetzt'] is True and g['updatedBy'], g)
    a.click('#btn-more'); a.click('#menu-more [data-act="druck-fuss"]'); a.wait_for_selector('#dlg-druck-fuss[open] textarea[name=s0]')
    for n in ('s0', 's1', 's2'):
        a.fill(f'#druck-fuss-body textarea[name={n}]', '')
    for n in ('z0', 'z1'):
        a.fill(f'#druck-fuss-body input[name={n}]', '')
    a.click('#df-vorgabe')
    check('„Vorgabe einsetzen“ schreibt die Vorgabe in die leeren Felder', a.input_value('#druck-fuss-body textarea[name=s0]') == vorgabe['spalten'][0] and a.input_value('#druck-fuss-body input[name=z1]') == vorgabe['zeilen'][1])
    a.click('#dlg-druck-fuss .dlg-foot [data-close]')
    if a.locator('#dlg-frage[open]').count():
        a.click('#fr-ja')
    a.wait_for_selector('#dlg-druck-fuss', state='hidden')
    check('Abbrechen speichert nichts', doc('fracht')['druck']['spalten'][0] == SP1)
    assert A.call('druck_fuss_save', {'fuss': neu})[0] == 200
    ctx.close()

    # Bearbeiter: Knopf „Drucken“ ja, Einstellung nein
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    b = anmelden(ctx, 'eddi', PW_E)
    b.click('#btn-more'); b.wait_for_selector('#menu-more:not([hidden])')
    check('Bearbeiter: Knopf „Drucken“ sichtbar, Menüeintrag „Fußzeile im Druck“ nicht', b.locator('#btn-drucken').is_visible() and b.locator('#menu-more [data-act="druck-fuss"]').is_hidden())
    b.keyboard.press('Escape')
    b.click('#btn-drucken')
    fr = rahmen(b)
    check('Bearbeiter druckt den Entwurf', fr.evaluate("document.querySelectorAll('#print-root .pl-cols tr.row').length") == GESAMT)
    ctx.close()

    # 390 px (Handy): Knopf erreichbar, kein Querscrollen, Fenster passt
    for schema in ('light', 'dark'):
        mc = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, color_scheme=schema)
        mc.add_init_script(INIT)
        mo = anmelden(mc, 'admin', PW)
        mb = mo.evaluate("""() => { const r = document.querySelector('#btn-drucken').getBoundingClientRect(); return { l: r.left, r: r.right, h: r.height, w: r.width, sw: document.documentElement.scrollWidth }; }""")
        check(f'390 px ({schema}): Knopf „Drucken“ sichtbar und groß genug, kein Querscrollen', mb['w'] > 0 and mb['l'] >= 0 and mb['r'] <= 390 and mb['h'] >= 36 and mb['sw'] <= 390, mb)
        shot(mo.locator('#topbar'), f'{SH}/druck-knopf-390-{schema}.png')
        if schema == 'light':
            mo.tap('#btn-drucken')
            fr = rahmen(mo)
            check('390 px: Druckfassung unabhängig vom Bildschirm (A4 quer, alle Artikel)', fr.evaluate("document.querySelectorAll('#print-root .pl-cols tr.row').length") == GESAMT
                  and fr.evaluate("+document.querySelector('#print-root .pl-doc').dataset.spalten") in (3, 4))
            mo.wait_for_function("!document.querySelector('#btn-drucken').disabled")
            mo.tap('#btn-more'); mo.tap('#menu-more [data-act="druck-fuss"]'); mo.wait_for_selector('#dlg-druck-fuss[open] textarea[name=s0]')
            dm = mo.evaluate("""() => { const d = document.querySelector('#dlg-druck-fuss').getBoundingClientRect(), t = [...document.querySelectorAll('#dlg-druck-fuss textarea, #dlg-druck-fuss input[type=text], #dlg-druck-fuss .df-bank')].map((e) => e.getBoundingClientRect());
              return { l: d.left, r: d.right, feld: Math.max(...t.map((x) => x.right)), sw: document.documentElement.scrollWidth }; }""")
            check('390 px: Fenster „Fußzeile im Druck“ passt (Felder untereinander, nichts ragt heraus)', dm['l'] >= 0 and dm['r'] <= 390 and dm['feld'] <= 390 and dm['sw'] <= 390, dm)
            shot(mo, SH + '/druck-fusszeile-390.png')
        mc.close()

    # Angebotsseite am Handy (Kunde): Druckfassung bleibt A4 quer
    mc = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    mc.add_init_script(INIT)
    mk = mc.new_page(); mk.on('pageerror', lambda ex: errors.append(str(ex)))
    mk.goto(BASE + '/'); mk.wait_for_selector('.al tr.row')
    s9 = satz(mk)
    check('Angebotsseite 390 px: Druck wie am Desktop (gleiche Seiten- und Spaltenzahl, vollständig)', s9['seiten'] == N and s9['spalten'] == s['spalten'] and s9['zeilen'] == schirm['zeilen'] and all(x['ueber'] <= 0.5 for x in s9['jeSeite']),
          (s9['seiten'], N, s9['spalten']))
    zurueck(mk)
    mc.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'\n{sum(res)}/{len(res)} Prüfungen bestanden')
sys.exit(0 if all(res) else 1)
