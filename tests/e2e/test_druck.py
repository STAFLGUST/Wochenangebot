"""Druck der Angebote (Wunsch des Inhabers 13.11.2026): die Druckfassung „Angebotsansicht“ (A4 quer) zeigt alles, was die
Vorschau zeigt – fortlaufend und kompakt. Geprüft wird: Druck-DOM vollständig (Artikel, Gruppen, Bereiche, Reihenfolge, Werbung,
Sonderposten wie am Bildschirm), Farben aktiv (print-color-adjust, auch ohne „Hintergrundgrafiken“); feste Vorgaben für jede
Druckfassung (Funktion heil): Seiten 279 × 193 mm, immer genau drei Spalten, kein Block geteilt, nichts läuft über (Fuß,
rechter Rand, Preisspalte), Bereichsbalken nie ohne Block, „Forts.“-Balken nur am Seitenanfang, Schrift nicht unter 7,5 pt;
Seiten fortlaufend gefüllt (erster Bereich gleich unter der Werbung, Füllgrad je Seite, Bereich zwischen Blöcken umbrochen);
Dichte in drei Stufen, automatisch die größte Schrift mit der kleinsten Seitenzahl (?stufe= zum Vergleich, unbekannter Wert);
Grenzfälle: Gruppe höher als eine Seite (nur sie wird geteilt, gleich große Teile), einzelner Block (Einzelangebot mit 8, 46
und 190 Positionen, sortierte Liste) gleichmäßig über drei Spalten; echter Druck: PDF A4 quer, Seitenzahl wie gesetzt und
jede Zeile wirklich im PDF (Text aus dem PDF gelesen); Kopf „Seite x von y“; Fußzeile des Briefbogens mit dem Hinweis
darüber nur auf der letzten Seite (Vorgabe) oder auf jeder Seite (Einstellung bzw. ?fuss=); Einstellung „Fußzeile im Druck“
(Rechte 401/403, leer = Vorgabe aus dem Impressum, Bereinigung, Fracht-Einstellung bleibt erhalten, Protokoll);
Bankangaben nur für angemeldete Nutzer (Server entscheidet; öffentlich ohne Cookie); PDF des Servers mit Fußzeile;
Hochformat-Layouts mit Fußzeile am Ende; im Eingabebereich Knopf „Drucken“ (links neben „An Kunden senden“/„Veröffentlichen“,
druckt das gewählte Angebot als Entwurf wie die Vorschau, speichert vorher), „Drucken“ im Vorschaufenster, Schnittstelle
WA.angebot.druck.drucken für andere Module, Fenster „Fußzeile im Druck“ nur für Administratoren, 390 px, keine
JavaScript-Fehler. Nur Testdaten (Seed-Angebot) und erfundene Angaben in der Fußzeile."""
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


def norm(t):
    """Text ohne Leerraum und Trennstriche (im PDF trennt der Browser lange Bezeichnungen am Zeilenende)"""
    return re.sub(r'[\s\-‐­]', '', t)


def norm_titel(name):
    """Gruppenname, wie die Angebotsansicht ihn zeigt: "Marke" → „Marke“"""
    return re.sub(r'"([^"]{2,40}?)"', r'„\1“', name).strip()


def pdf_chromium_text(data):
    """Text eines vom Browser gedruckten PDF in Zeichenreihenfolge, ohne Leerraum und Trennstriche. Chromium schreibt Glyphennummern;
    die Zuordnung zu Zeichen steht je Schrift in der ToUnicode-Tabelle (Schrift „F<n>“ = Objekt n)."""
    objs = {int(mm.group(1)): mm.group(2) for mm in re.finditer(rb'(\d+) 0 obj\b(.*?)\bendobj', data, re.S)}

    def strom(o):
        mm = re.search(rb'stream\r?\n(.*?)\r?\nendstream', o or b'', re.S)
        try:
            return zlib.decompress(mm.group(1)) if mm else b''
        except zlib.error:
            return b''

    hexstr = lambda h: bytes.fromhex(h.decode()).decode('utf-16-be', 'replace')
    karten = {}
    for nr, o in objs.items():
        mm = re.search(rb'/ToUnicode (\d+) 0 R', o)
        if not mm:
            continue
        cm, k, breite = strom(objs.get(int(mm.group(1)))), {}, 1
        for teil in re.findall(rb'beginbfchar(.*?)endbfchar', cm, re.S):
            for a, b in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', teil):
                k[int(a, 16)] = hexstr(b); breite = len(a) // 2
        for teil in re.findall(rb'beginbfrange(.*?)endbfrange', cm, re.S):
            for a, b, c in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', teil):
                breite = len(a) // 2
                for n in range(int(a, 16), int(b, 16) + 1):
                    k[n] = hexstr(c)[:-1] + chr(ord(hexstr(c)[-1]) + n - int(a, 16))
        karten[nr] = (k, breite)
    out = []
    for o in objs.values():
        st = strom(o)
        if b' Tf' not in st:
            continue
        k, breite = {}, 1
        for f, h in re.findall(rb'/F(\d+) [\d.]+ Tf|<([0-9A-Fa-f]+)>', st):
            if f:
                k, breite = karten.get(int(f), ({}, 1))
            else:
                roh_ = bytes.fromhex(h.decode() if len(h) % 2 == 0 else h.decode() + '0')
                out.append(''.join(k.get(int.from_bytes(roh_[i:i + breite], 'big'), '') for i in range(0, len(roh_), breite)))
    return norm(''.join(out))


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
check('Vorgabe ohne eigene Texte: nur Angaben aus dem Impressum, nur auf der letzten Seite, Bankangaben geschützt',
      st == 200 and r['fuss']['eigen'] is False and r['fuss']['spalten'] == vorgabe['spalten'] and r['fuss']['zeilen'] == vorgabe['zeilen']
      and r['fuss']['modus'] == 'letzte' and r['fuss']['bankGeschuetzt'] is True, r.get('fuss'))
vt = json.dumps(vorgabe, ensure_ascii=False)
check('Vorgabe im Code ohne Bank- und Steuernummer (GR-007)', not re.search(r'IBAN|BIC|Bank|Konto|Steuer-?Nr|Sparkasse', vt, re.I) and 'Lagerstraße 17' in vt, vt[:200])
check('Vorgabe steht so im Impressum der Angebotsseite', all(t.replace(' ', '') in urllib.request.urlopen(BASE + '/impressum/').read().decode('utf-8').replace(' ', '') for t in ('Lagerstraße 17', '20357 Hamburg', 'DE 118949959')))
check('Lesen: Bearbeiter und Leser mit Modulzugang ja, ohne Anmeldung 401', E.call('druck_fuss')[0] == 200 and L.call('druck_fuss')[0] == 200 and ANON.call('druck_fuss')[0] == 401,
      (E.call('druck_fuss')[0], L.call('druck_fuss')[0], ANON.call('druck_fuss')[0]))
neu = {'spalten': [SP1, SP2, SP3], 'zeilen': [Z1, Z2], 'modus': 'letzte'}
check('Speichern: Bearbeiter und Leser 403, ohne Anmeldung 401 – nichts gespeichert',
      E.call('druck_fuss_save', {'fuss': neu})[0] == 403 and L.call('druck_fuss_save', {'fuss': neu})[0] == 403 and ANON.call('druck_fuss_save', {'fuss': neu})[0] in (401, 403)
      and A.call('druck_fuss')[1]['fuss']['eigen'] is False and 'druck' not in (doc('fracht') or {}))
off0 = ANON.call('offer')[1]
check('Angebot liefert die Fußzeile mit (leer = Vorgabe) und den Hinweis zu Mengen und Fracht', off0['fracht']['fuss']['spalten'] == vorgabe['spalten'] and off0['fracht']['fuss']['modus'] == 'letzte'
      and 'Mindestbestellmenge von ca. 300 kg' in off0['fracht']['hinweis'][0], off0['fracht'].get('fuss'))
schmutz = {'spalten': [SP1 + '\n\n  ' + '\n'.join(f'Zeile {i}' for i in range(9)), 'x' * 90 + '\tTab\x07', SP3, 'vierte Spalte'], 'zeilen': [Z1 + '\nzweite Zeile', 'y' * 300, 'dritte'],
           'modus': 'quer', 'fremd': 'weg', 'updatedBy': 'Fälscher'}
st, r = A.call('druck_fuss_save', {'fuss': schmutz})
f = r.get('fuss', {})
check('Bereinigung: höchstens 6 Zeilen je Spalte, 70 Zeichen je Zeile, Steuerzeichen weg, Registerzeile einzeilig (200 Zeichen), unbekannter Modus → letzte (Vorgabe), fremde Felder weg',
      st == 200 and f['spalten'][0].count('\n') == 5 and f['spalten'][1] == 'x' * 70 and len(f['spalten']) == 3 and f['zeilen'] == [Z1, 'y' * 200]
      and f['modus'] == 'letzte' and 'fremd' not in f and f.get('updatedBy') != 'Fälscher', f)
st, r = A.call('druck_fuss_save', {'fuss': neu})
check('Administrator speichert die Fußzeile (eigene Texte)', st == 200 and r['fuss']['eigen'] is True and r['fuss']['spalten'] == [SP1, SP2, SP3] and r['fuss']['zeilen'] == [Z1, Z2]
      and r['fuss']['bankGeschuetzt'] is True, r)
gesp = doc('fracht')
check('gespeichert als Feld „druck“ im Dokument „fracht“ (nur erweitert)', gesp['druck']['spalten'] == [SP1, SP2, SP3] and gesp['druck']['modus'] == 'letzte' and 'aktiv' in gesp and 'staffeln' in gesp, list(gesp))
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
# Druckdialog ersetzen: zählen und – wie der Browser vor dem Drucken – „beforeprint“ melden (die Seite setzt dann ihre Druckfassung)
INIT = "window.print = () => { window.__gedruckt = (window.__gedruckt || 0) + 1; window.dispatchEvent(new Event('beforeprint')); };"

SATZ = """() => {
  const R = document.querySelector('#print-root'), D = R.querySelector('.pl-doc');
  if (!D) return null;
  const pages = [...D.querySelectorAll('.pl-page')];
  const box = (e) => e.getBoundingClientRect();
  const z = parseFloat(getComputedStyle(D).getPropertyValue('--z'));
  const pt = (e) => parseFloat(getComputedStyle(e).fontSize) * z * .75;   // gedruckte Schriftgröße (Satzfläche wird um z verkleinert)
  const ohneForts = (e) => [...e.childNodes].filter((n) => !(n.classList && n.classList.contains('al-cont'))).map((n) => n.textContent).join('').trim();
  return {
    seiten: pages.length, spalten: +D.dataset.spalten, fuss: D.dataset.fuss, seitenAttr: +D.dataset.seiten, stufe: D.dataset.stufe, geteilt: +D.dataset.geteilt, z,
    zeilen: [...D.querySelectorAll('.al-band tr.row')].map((r) => r.dataset.id),
    texte: [...D.querySelectorAll('.al-band tr.row, .werb-sec tr.row')].map((r) => r.querySelector('.c-code').textContent + ((r.querySelector('.c-name').firstChild || {}).textContent || '')),
    werb: [...D.querySelectorAll('.werb-sec tr.row')].map((r) => r.dataset.id),
    gruppen: [...D.querySelectorAll('.al-band .al-gt')].filter((g) => !g.querySelector('.al-cont')).map((g) => g.textContent.trim()),
    forts: D.querySelectorAll('.al-band .al-gt .al-cont').length,
    bereiche: [...D.querySelectorAll('.al-band .al-st:not(.pl-trenn) h3')].filter((h) => !h.querySelector('.al-cont')).map((h) => h.textContent.trim()),
    sektionen: [...D.querySelectorAll('.al-band > .al-sec')].map((x) => { const b = x.querySelector(':scope > .al-st:not(.pl-trenn)');
      return { name: b ? ohneForts(b.querySelector('h3')) : '', anzahl: b ? parseInt(b.querySelector(':scope > span').textContent, 10) : null, linie: !!x.querySelector(':scope > .pl-trenn'),
        zeilen: x.querySelectorAll('tr.row').length, titel: [...x.querySelectorAll('.al-gt')].map(ohneForts), nachbarn: x.parentElement.children.length - 1 }; }),
    bloecke: [...D.querySelectorAll('.al-band .al-grp')].map((g) => ({ titel: ohneForts(g.querySelector('.al-gt')), forts: !!g.querySelector('.al-cont'), zeilen: g.querySelectorAll('tr.row').length })),
    jeSeite: pages.map((p) => {
      const pb = box(p), f = p.querySelector('.pl-in > .pl-fuss'), bands = [...p.querySelectorAll('.al-band')], grp = [...p.querySelectorAll('.al-band .al-grp')];
      const grenze = f ? box(f).top : pb.bottom, oben = bands.length ? box(bands[0]).top : grenze, unten = Math.max(oben, ...grp.map((g) => box(g).bottom));
      const st = [...p.querySelectorAll('.al-band .al-st:not(.pl-trenn)')];
      const hin = f && f.querySelector('.pl-hinweis'), br = f && f.querySelector('.pl-brief'), si = f && f.querySelector('.pl-siegel');
      const letzte = bands.length ? [...bands[bands.length - 1].querySelectorAll('.al-col')] : [];
      return { h: pb.height, b: pb.width, fuell: +p.dataset.fuell, hoehe: Math.round(100 * (unten - oben) / Math.max(1, grenze - oben)),
        spalten: bands.map((b) => [...b.querySelectorAll(':scope > .al-sec')].reduce((a, s) => a + s.querySelectorAll(':scope > .al-cols > .al-col').length, 0)),
        bereiche: st.length, namen: st.map((x) => ohneForts(x.querySelector('h3'))), fortsBalken: st.map((x) => !!x.querySelector('.al-cont')),
        fortsSpaeter: bands.slice(1).reduce((a, b) => a + b.querySelectorAll('.al-st .al-cont').length, 0),
        balkenOhneBlock: [...p.querySelectorAll('.al-band > .al-sec')].filter((x) => !x.querySelector('.al-grp')).length,
        kopf: (p.querySelector('.pl-ph') || {}).innerText || '', logo: p.querySelectorAll('img.al-logo').length, werb: p.querySelector('.werb-sec') ? 1 : 0,
        ueber: unten - grenze, oberhalb: Math.max(0, ...grp.map((g) => pb.top - box(g).top)),
        rechts: Math.max(pb.right, ...[...p.querySelectorAll('.al-band td, .al-band .al-st, .werb-sec td, .al-sale')].map((e) => box(e).right)) - pb.right,
        preisUeber: Math.max(0, ...[...p.querySelectorAll('td.c-price')].map((td) => Math.max(0, ...[...td.children].map((e) => Math.max(box(e).right - box(td).right, box(td).left - box(e).left))))),
        spaltenUnten: letzte.map((c) => (c.lastElementChild ? Math.round(box(c.lastElementChild).bottom - pb.top) : 0)),
        fuss: f ? { unten: pb.bottom - box(f).bottom, links: box(br).left - pb.left, rechts: pb.right - box(br).right, hinweisUeber: hin && br ? box(br).top - box(hin).bottom : null,
          hinweis: hin ? hin.innerText : '', brief: br ? br.innerText : '', siegel: !!(si && si.complete && si.naturalWidth > 0), hinweisMitte: hin ? Math.abs((box(hin).left + box(hin).right) / 2 - (pb.left + pb.right) / 2) : null } : null };
    }),
    schrift: Math.min(...[...D.querySelectorAll('.al-band td.c-code, .al-band td.c-name, .al-band td.c-price:not(.al-np), .al-band .al-gt, .al-band .al-st h3')].filter((e) => e.textContent.trim()).map(pt)),
    farben: { adjust: getComputedStyle(D).printColorAdjust || getComputedStyle(D).webkitPrintColorAdjust, marke: (D.querySelector('.al-brand') ? getComputedStyle(D.querySelector('.al-brand')).color : ''),
      band: (D.querySelector('.al-band .al-st') ? getComputedStyle(D.querySelector('.al-band .al-st')).backgroundColor : ''), werb: (D.querySelector('.werb-st') ? getComputedStyle(D.querySelector('.werb-st')).backgroundColor : ''),
      sonder: (D.querySelector('.al-sale') ? getComputedStyle(D.querySelector('.al-sale')).color : ''), umbruch: (D.querySelector('.al-band .al-st') ? getComputedStyle(D.querySelector('.al-band .al-st')).breakBefore : ''),
      schema: getComputedStyle(document.documentElement).colorScheme },
    text: D.innerText,
  };
}"""
STUFEN = ['normal', 'kompakt', 'eng']   # wie in app/assets/angebot-druck.js, von der größten zur kleinsten Schrift


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
    pg.emulate_media(media='null')
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")


def laden(pg, pfad):
    pg.goto(BASE + pfad); pg.wait_for_selector('.al tr.row'); pg.evaluate('document.fonts.ready')


def heil(s, modus=None):
    """Feste Vorgaben des Satzes, die für jede Druckfassung gelten: Liste der Verstöße (leer = in Ordnung)"""
    f = []
    N = s['seiten']
    for i, x in enumerate(s['jeSeite']):
        nr = f'Seite {i + 1}: '
        if abs(x['h'] - 193 * MM) >= 1 or abs(x['b'] - 279 * MM) >= 1: f.append(nr + f"Größe {x['b']:.0f}×{x['h']:.0f}")
        if x['ueber'] > 0.5: f.append(nr + f"läuft {x['ueber']:.1f} px über den Fuß")
        if x['oberhalb'] > 0.5: f.append(nr + 'Block über dem Seitenanfang')
        if x['rechts'] > 0.5: f.append(nr + f"ragt {x['rechts']:.1f} px über den rechten Rand")
        if x['preisUeber'] > 0.5: f.append(nr + f"Preis ragt {x['preisUeber']:.1f} px aus seiner Spalte")
        if any(k != 3 for k in x['spalten']): f.append(nr + f"Zeile ohne genau drei Spalten {x['spalten']}")
        if x['balkenOhneBlock']: f.append(nr + 'Bereichsbalken ohne Block')
        if x['fortsSpaeter']: f.append(nr + '„Forts.“-Balken nicht am Seitenanfang')
        if i and any(x['fortsBalken'][:1]) and x['namen'][0] != s['jeSeite'][i - 1]['namen'][-1]: f.append(nr + 'Fortsetzung eines anderen Bereichs')
        if modus and bool(x['fuss']) != (modus == 'jede' or i == N - 1): f.append(nr + 'Fußzeile ' + ('fehlt' if not x['fuss'] else 'zu viel'))
        if x['fuss'] and abs(x['fuss']['unten']) > 1: f.append(nr + 'Fußzeile nicht am unteren Rand')
        if abs(x['fuell'] - x['hoehe']) > 3: f.append(nr + f"Füllgrad {x['fuell']} % ≠ gemessen {x['hoehe']} %")
    if s['spalten'] != 3 or s['seitenAttr'] != N: f.append('Kennzahlen am Satz')
    if s['schrift'] < 7.45: f.append(f"Schrift {s['schrift']:.2f} pt")
    return f


def pdf_alles(data, s):
    """Zeilen (Nummer + Bezeichnung) der Druckfassung, die im PDF fehlen"""
    t = pdf_chromium_text(data)
    return [x for x in s['texte'] if norm(x) not in t]


with sync_playwright() as p:
    br = p.chromium.launch()

    # ---------- Angebotsseite (öffentlich): Druck = Angebotsansicht am Bildschirm ----------
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg, '/')
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
    pd = pg.evaluate("""() => ({ sonder: document.querySelectorAll('#print-root .al-band .al-sale').length, was: document.querySelectorAll('#print-root .al-band .al-was').length,
      anfrage: document.querySelectorAll('#print-root .al-band td.al-np').length, tags: document.querySelectorAll('#print-root .al-band .tag.sale').length, an: document.querySelectorAll('#print-root .al-band tr.werb-an').length,
      bedien: document.querySelectorAll('#print-root .star, #print-root .qty, #print-root button, #print-root input').length })""")
    check('Druck-DOM: Hervorhebungen wie am Bildschirm (Sonderposten mit bisherigem Preis, „a. Anfr.“, beworbene Zeilen), keine Bedienelemente',
          pd['sonder'] == schirm['sonder'] == len(SALE) and pd['was'] == len(SALE) and pd['tags'] == len(SALE) and pd['anfrage'] == schirm['anfrage'] >= 2 and pd['an'] == 5 and pd['bedien'] == 0, (pd, schirm['sonder'], schirm['anfrage']))
    fb = s['farben']
    check('Farben aktiv: print-color-adjust „exact“, Marke bordeaux, Bereichs- und Werbeband getönt, Sonderpreis farbig, helles Schema',
          fb['adjust'] == 'exact' and fb['marke'] == 'rgb(140, 29, 44)' and fb['band'] not in ('rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)')
          and fb['werb'] not in ('rgba(0, 0, 0, 0)', 'transparent', 'rgb(255, 255, 255)') and fb['sonder'] == 'rgb(194, 65, 12)' and fb['schema'] == 'light', fb)
    N = s['seiten']
    check('feste Vorgaben: Seiten 279 × 193 mm, immer genau drei Spalten, nichts läuft über (Fuß, rechter Rand, Preisspalte), Fußzeile nur auf der letzten Seite am unteren Rand',
          heil(s, 'letzte') == [] and s['fuss'] == 'letzte', heil(s, 'letzte'))
    check('kein Block geteilt: jede Gruppe genau einmal, ohne „Forts.“', s['forts'] == 0 and s['geteilt'] == 0 and len(s['bloecke']) == 32, (s['forts'], len(s['bloecke'])))
    check('fortlaufend: kein erzwungener Seitenumbruch je Bereich (break-before „auto“), jeder Balken nennt die Artikelzahl seines Bereichs',
          fb['umbruch'] == 'auto' and all(x['anzahl'] == sum(y['zeilen'] for y in s['sektionen'] if y['name'] == x['name']) for x in s['sektionen'] if x['name']) and sum(x['zeilen'] for x in s['sektionen']) == 276,
          [(x['name'], x['anzahl'], x['zeilen']) for x in s['sektionen']])
    check('erste Seite: der erste Bereich beginnt gleich unter der Werbung', s['jeSeite'][0]['bereiche'] >= 1 and s['jeSeite'][0]['hoehe'] >= 60, s['jeSeite'][0])
    check('kompakt: höchstens 4 Seiten (vorher 6), alle Seiten vor der letzten zu mindestens 70 % der Höhe gefüllt (vier große Bereiche: der Rest einer Seite fasst keinen ganzen Block mehr)',
          N <= 4 and all(x['fuell'] >= 70 for x in s['jeSeite'][:-1]), (N, [x['fuell'] for x in s['jeSeite']]))
    check('Kopf: Logo nur auf Seite 1, jede Seite mit Titel und „Seite x von y“ – ohne Angebotswoche, Stand und „Preise in € je kg“ (Wunsch Inhaber 13.11.2026)',
          [x['logo'] for x in s['jeSeite']] == [1] + [0] * (N - 1) and all(f'Seite {i + 1} von {N}' in x['kopf'] and 'KW 43' in x['kopf']
          and not re.search(r'Angebotswoche|Stand |je kg', x['kopf']) for i, x in enumerate(s['jeSeite'])), s['jeSeite'][0]['kopf'])
    check('Schrift (Nummer, Bezeichnung, Preis, Überschriften) gedruckt nicht unter 7,5 pt; Stufe genannt', s['schrift'] >= 7.45 and s['stufe'] in STUFEN, (s['schrift'], s['stufe']))
    check('GR-001/GR-008: Druck ohne Mengen, Partien, MHD und Einkaufspreise', not re.search(r'Bestand|Partie|MHD|Einkauf|EK-Preis', s['text']) and pg.locator('#print-root [data-qty], #print-root .c-qty').count() == 0)
    f1 = s['jeSeite'][-1]['fuss']
    check('Fußzeile über die ganze Breite, Hinweis mittig darüber, Siegel geladen', f1 and abs(f1['links']) <= 1 and abs(f1['rechts']) <= 1 and f1['hinweisMitte'] <= 1 and 0 <= f1['hinweisUeber'] <= 12 and f1['siegel'],
          f1 and (round(f1['links'], 1), round(f1['rechts'], 1), round(f1['hinweisUeber'], 1)))
    hin = off0['fracht']['hinweis'][:2]
    check('Hinweis = „Fracht und Hinweis im Angebot“ (Mindestmenge, Frachtanteil) und derselbe Text wie am Bildschirm', all(z in f1['hinweis'] for z in hin) and 'Telefon Test: 000 - 00 00 00' in f1['hinweis']
          and all(z in schirm['hinweis'] for z in hin), f1['hinweis'][:120])
    check('Fußzeile: drei Spalten und zwei Registerzeilen aus der Einstellung; öffentlich ohne Bankangaben', all(t in f1['brief'] for t in ('Musterfleisch Test GmbH', 'www.example.org', 'Musterstadt B 000 00', 'Musterstadt A 000 00'))
          and 'Testbank' not in s['text'] and 'DE 118949959' in f1['brief'], f1['brief'][:200])
    lay = pg.evaluate("""() => { const p = [...document.querySelectorAll('#print-root .pl-page')].pop(), b = (e) => e.getBoundingClientRect();
      const bs = [...p.querySelectorAll('.pl-bs')], bz = p.querySelector('.pl-bz'), br = p.querySelector('.pl-brief');
      const w = document.querySelector('#print-root .werb-sec.werb-ein'), st = w && w.querySelector('.werb-st'), r1 = w && w.querySelector('tr.row');
      return { oben: bs.map((e) => Math.round(b(e).top)), unterSpalten: bz && bs.length ? b(bz).top - Math.max(...bs.map((e) => b(e).bottom)) : null,
        bzLinks: bz && bs.length ? Math.round(b(bz).left - b(bs[0]).left) : null, text: br ? br.innerText : '',
        werbAbstand: st && r1 ? b(r1).top - b(st).bottom : null, werbEh: st ? (st.querySelector('.werb-eh') || {}).textContent : '',
        werbKopf: w ? getComputedStyle(w.querySelector('.al-h')).display : '' }; }""")
    check('Fußzeile: Spalten oben bündig, Registerzeilen darunter ab der ersten Spalte, „ * “ als „ · “ und ohne Leerzeichen vor dem Doppelpunkt',
          len(lay['oben']) == 3 and len(set(lay['oben'])) == 1 and lay['unterSpalten'] is not None and lay['unterSpalten'] >= 0 and lay['bzLinks'] == 0
          and ' * ' not in lay['text'] and ' :' not in lay['text'] and 'Musterstadt B 000 00 · Geschäftsführer: Erika Beispiel' in lay['text'], lay)
    check('Werbung: Balken direkt auf den Zeilen wie der Kopf einer Artikelgruppe („€/kg“ im Balken, keine leere Kopfzeile)',
          lay['werbEh'] == '€/kg' and lay['werbKopf'] == 'none' and lay['werbAbstand'] is not None and 0 <= lay['werbAbstand'] <= 8, lay)
    zurueck(pg)
    # echter Druck (wie Strg+P, ohne „Hintergrundgrafiken“): dasselbe Ergebnis wie gesetzt
    pdf = pg.pdf(prefer_css_page_size=True, print_background=False)
    open(SH + '/druck-wochenangebot.pdf', 'wb').write(pdf)
    boxes = [tuple(float(v) for v in mm.groups()) for mm in re.finditer(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)', pdf)]
    check('PDF: A4 quer, genau so viele Seiten wie gesetzt', pdf_seiten(pdf) == N and boxes and all(w > h for w, h in boxes), (pdf_seiten(pdf), N, boxes[:1]))
    fehlt = pdf_alles(pdf, s)
    check('PDF: jede Zeile der Druckfassung steht wirklich im PDF (kein Block im Seitenumbruch des Browsers verloren)', len(s['texte']) == 281 and not fehlt, (len(s['texte']), fehlt[:3]))
    check('PDF auch ohne „Hintergrundgrafiken“ farbig (Bänder, Marke, Sonderposten)', pdf_farbig(pdf) >= 10, pdf_farbig(pdf))
    check('nach dem Druck ist die Druckfassung wieder entfernt', pg.locator('#print-root .pl-page').count() == 0 and pg.locator('.al tr.row').count() == schirm['alle'])
    s = satz(pg)
    for i, nr in ((0, 's1'), (N - 1, 'letzte')):
        shot(pg.locator('#print-root .pl-page').nth(i), f'{SH}/druck-wochenangebot-{nr}.png')
    zurueck(pg)

    # Dichte: drei feste Stufen; automatisch die größte Schrift, mit der es nicht mehr Seiten werden als mit der kleinsten
    je = {}
    for st in STUFEN:
        laden(pg, '/?stufe=' + st)
        x = satz(pg)
        je[st] = x
        zurueck(pg)
    sn = [je[st]['seiten'] for st in STUFEN]
    check('Stufen einzeln (?stufe=): vollständig, feste Vorgaben eingehalten, Schrift von groß nach klein (8,3 / 7,9 / 7,5 pt), Seitenzahl steigt mit kleinerer Schrift nie',
          all(je[st]['stufe'] == st and je[st]['zeilen'] == schirm['zeilen'] and heil(je[st], 'letzte') == [] for st in STUFEN) and sn == sorted(sn, reverse=True)
          and all(abs(je[st]['schrift'] - pt) < .06 for st, pt in zip(STUFEN, (8.29, 7.85, 7.50))), (sn, [round(je[st]['schrift'], 2) for st in STUFEN], [heil(je[st], 'letzte') for st in STUFEN]))
    erwartet = next(st for st in STUFEN if je[st]['seiten'] == min(sn))
    check('automatisch: die größte Schrift mit der kleinsten Seitenzahl', s['stufe'] == erwartet and N == min(sn), (s['stufe'], erwartet, sn))
    laden(pg, '/?stufe=riesig')
    x = satz(pg)
    check('unbekannte Stufe in der Adresse: es bleibt bei der automatischen Wahl', x['stufe'] == s['stufe'] and x['seiten'] == N, (x['stufe'], x['seiten']))
    zurueck(pg)

    # Variante „auf jeder Seite“ (?fuss=jede) und über die Einstellung
    laden(pg, '/?fuss=jede')
    s2 = satz(pg)
    check('Variante „jede Seite“: Fußzeile mit Hinweis am Fuß jeder Seite, vollständig, nichts läuft über, nicht weniger Seiten als mit „letzte“',
          s2['fuss'] == 'jede' and heil(s2, 'jede') == [] and s2['zeilen'] == schirm['zeilen'] and s2['seiten'] >= N and all(z in x['fuss']['hinweis'] for x in s2['jeSeite'] for z in hin), (s2['seiten'], N, heil(s2, 'jede')))
    zurueck(pg)
    pdf2 = pg.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-jede-seite.pdf', 'wb').write(pdf2)
    check('PDF „jede Seite“: Seiten wie gesetzt, jede Zeile im PDF', pdf_seiten(pdf2) == s2['seiten'] and not pdf_alles(pdf2, s2), (pdf_seiten(pdf2), s2['seiten'], pdf_alles(pdf2, s2)[:3]))
    assert A.call('druck_fuss_save', {'fuss': dict(neu, modus='jede')})[0] == 200
    laden(pg, '/?r=modus')
    s3 = satz(pg)
    check('Einstellung „auf jeder Seite“ wirkt ohne Parameter', s3['fuss'] == 'jede' and heil(s3, 'jede') == [], (s3['fuss'], heil(s3, 'jede')))
    shot(pg.locator('#print-root .pl-page').first, f'{SH}/druck-jede-seite-s1.png')
    zurueck(pg)
    laden(pg, '/?fuss=letzte')
    s4 = satz(pg)
    check('… und ?fuss=letzte schaltet für den Vergleich um', s4['fuss'] == 'letzte' and heil(s4, 'letzte') == [] and s4['seiten'] == N, (s4['fuss'], s4['seiten']))
    zurueck(pg)
    assert A.call('druck_fuss_save', {'fuss': neu})[0] == 200

    # Auswahl und Merkliste: nur die gewählten Artikel, ohne Werbung; ungegliedert: eine Liste über alle Spalten
    laden(pg, '/')
    pg.fill('#q', 'Roastbeef'); pg.wait_for_function("document.querySelectorAll('#list .al-band tr.row').length < 60")
    treffer = pg.locator('#list .al-band tr.row').count()
    s5 = satz(pg)
    check('Auswahl drucken (Suche): nur die Treffer, ohne Werbung, Auswahl im Kopf genannt, eine Seite in der größten Schrift', len(s5['zeilen']) == treffer and 0 < treffer < 60 and not s5['werb'] and 'Roastbeef' in s5['jeSeite'][0]['kopf']
          and s5['seiten'] == 1 and s5['stufe'] == 'normal' and heil(s5, 'letzte') == [], (len(s5['zeilen']), treffer, s5['stufe'], heil(s5, 'letzte')))
    zurueck(pg)
    pg.fill('#q', ''); pg.wait_for_function("document.querySelectorAll('#list .al-band tr.row').length === 276")
    pg.click('#btn-print'); pg.wait_for_selector('#dlg-print[open]')
    check('Druckdialog: „Angebotsansicht, A4 quer“ ist die Vorgabe und nennt Werbung, Hinweis und Fußzeile', pg.is_checked('#dlg-print input[name=layout][value=liste]')
          and 'Fußzeile' in pg.inner_text('#dlg-print label:has(input[name=layout][value=liste])'), pg.inner_text('#dlg-print label:has(input[name=layout][value=liste])'))
    pg.evaluate("""() => { const f = document.querySelector('#print-form'); f.querySelector('input[name=scope][value=all]').checked = true; f.querySelector('input[name=layout][value=liste]').checked = true;
      f.querySelector('input[name=grouped]').checked = false; f.requestSubmit(); }""")
    pg.wait_for_function('window.__gedruckt >= 1')
    s6 = satz(pg, wie='')
    z6 = [[b['zeilen'] for b in s6['bloecke']][i:i + 3] for i in range(0, len(s6['bloecke']), 3)]
    check('ungegliedert: alle Artikel als eine Liste gleichmäßig über die drei Spalten jeder Seite („Forts.“), ohne Werbung, nichts läuft über',
          len(s6['zeilen']) == 276 and s6['forts'] == len(s6['bloecke']) - 1 >= 2 and len(s6['gruppen']) == 1 and not s6['werb'] and heil(s6, 'letzte') == [] and s6['seiten'] <= 4
          and all(len(z) == 3 and max(z) - min(z) <= 4 for z in z6), (len(s6['zeilen']), s6['forts'], s6['seiten'], z6, heil(s6, 'letzte')))
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

    # ---------- Viele Bereiche (wie mit Angebotskategorien): fortlaufend statt einer Seite je Bereich ----------
    d = A.call('draft')[1]
    m2 = d['draft'] or d['published']
    for k in ('savedAt', 'savedBy', 'publishedAt', 'rev'):
        m2.pop(k, None)
    BER = ['Eigene Zerlegung, Marke "Fleischmeister"', 'Färse und Ochse', 'Kalb "Fleischmeister"', 'Rindfleisch EU', 'Schwein', 'Neuseeland und Australien', 'Kalbfleisch',
           'Charoluxe und Geflügel', 'Südamerika', 'Iberico und Spanferkel', 'Grain Fed', 'Irland', 'Gefrierfleisch', 'Gefrierfleisch Rind und Schwein']
    for i, g in enumerate(m2['groups']):
        g['section'] = BER[min(len(BER) - 1, i * len(BER) // len(m2['groups']))]
    m2['groups'][-1]['section'] = ''
    # Grenzfall: eine Gruppe, die allein höher ist als eine ganze Seite – nur sie darf geteilt werden („Forts.“)
    g1 = m2['groups'][0]['id']
    G1_NAME = m2['groups'][0]['name']
    vor = [it for it in m2['items'] if it['groupId'] == g1]
    extra = [dict(it, id=f"{it['id']}x{n}", code=str(int(it['code']) + 1000 * n) if it.get('code') else None, name=it['name'] + f', Zuschnitt {n}') for n in range(1, 6) for it in vor]
    for it in extra:
        it.pop('sale', None)
    stelle = max(k for k, it in enumerate(m2['items']) if it['groupId'] == g1) + 1
    m2['items'][stelle:stelle] = extra
    GESAMT = len(m2['items'])
    G1_ZEILEN = len(vor) + len(extra)
    st, r = A.call('save_draft', {'model': m2, 'revision': d['revision']})
    assert st == 200, r

    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    v = ctx.new_page(); v.on('pageerror', lambda ex: errors.append(str(ex)))
    v.goto(BASE + '/admin/'); v.wait_for_selector('#screen-auth:not([hidden])')
    v.fill('#au-user', 'admin'); v.fill('#pw1', PW); v.click('#auth-submit'); v.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    laden(v, '/?vorschau=1')
    vs = v.evaluate("""() => ({ zeilen: [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id), gruppen: [...document.querySelectorAll('#list .al-band .al-gt')].map((g) => g.textContent.trim()),
      bereiche: [...document.querySelectorAll('#list .al-band .al-st:not(.al-st-leer) h3')].map((h) => h.textContent.trim()) })""")
    s7 = satz(v)
    check('Entwurf mit 14 Bereichen: Druck vollständig wie die Vorschau (Artikel, Gruppen, Bereiche, Reihenfolge)', len(vs['zeilen']) == GESAMT and s7['zeilen'] == vs['zeilen'] and s7['gruppen'] == vs['gruppen']
          and s7['bereiche'] == vs['bereiche'] and len(s7['bereiche']) == 14, (len(s7['zeilen']), GESAMT, len(s7['bereiche'])))
    check('… feste Vorgaben eingehalten (drei Spalten, nichts läuft über, Fußzeile nur am Ende)', heil(s7, 'letzte') == [], heil(s7, 'letzte'))
    check('… höchstens 6 Seiten statt einer Seite je Bereich (14), mehrere Bereiche je Seite, alle Seiten vor der letzten zu mindestens 80 % der Höhe gefüllt',
          s7['seiten'] <= 6 and max(x['bereiche'] for x in s7['jeSeite']) >= 3 and all(x['fuell'] >= 80 for x in s7['jeSeite'][:-1]), (s7['seiten'], [x['bereiche'] for x in s7['jeSeite']], [x['fuell'] for x in s7['jeSeite']]))
    fb7 = [(i, x['namen'][0]) for i, x in enumerate(s7['jeSeite']) if x['fortsBalken'][:1] == [True]]
    check('ein Bereich wird nur zwischen Blöcken umbrochen: auf der nächsten Seite steht sein Balken noch einmal mit „Forts.“, nur ganz oben',
          len(fb7) >= 1 and all(n == s7['jeSeite'][i - 1]['namen'][-1] for i, n in fb7) and sum(sum(x['fortsBalken']) for x in s7['jeSeite']) == len(fb7), fb7)
    lang = [b for b in s7['bloecke'] if b['titel'] == norm_titel(G1_NAME)]
    andere = [b for b in s7['bloecke'] if b['titel'] != norm_titel(G1_NAME)]
    check('Grenzfall Gruppe höher als eine Seite: nur sie ist geteilt – in etwa gleich große Teile mit „Forts.“ im wiederholten Gruppenkopf',
          len(lang) >= 2 and sum(b['zeilen'] for b in lang) == G1_ZEILEN and [b['forts'] for b in lang] == [False] + [True] * (len(lang) - 1)
          and max(b['zeilen'] for b in lang) - min(b['zeilen'] for b in lang) <= 4 and s7['geteilt'] == len(lang) - 1 == s7['forts'], [(b['zeilen'], b['forts']) for b in lang])
    check('… alle anderen Blöcke bleiben ganz (jede Gruppe genau ein Block)', len(andere) == len(s7['gruppen']) - 1 and not any(b['forts'] for b in andere), (len(andere), len(s7['gruppen'])))
    # Überschriften und Artikelzahlen gehen beim Verteilen nicht verloren; die Gruppe ohne Bereich gehört sichtbar zu keinem Nachbarn
    je_name = {}
    for x in s7['sektionen']:
        je_name[x['name']] = je_name.get(x['name'], 0) + x['zeilen']
    soll = {}
    for it in m2['items']:
        sec = next(g['section'] for g in m2['groups'] if g['id'] == it['groupId'])
        soll[norm_titel(sec)] = soll.get(norm_titel(sec), 0) + 1
    check('jeder Bereich behält Überschrift und Artikelzahl: Zeilen je Bereich wie im Angebot, „n Artikel“ im Balken (auch im wiederholten) = alle Artikel des Bereichs',
          je_name == soll and all(x['anzahl'] == soll[x['name']] for x in s7['sektionen'] if x['name']), (je_name, [(x['name'], x['anzahl']) for x in s7['sektionen'] if x['name'] and x['anzahl'] != soll.get(x['name'])]))
    ohne = [x for x in s7['sektionen'] if not x['name']]
    check('Gruppe ohne Bereich: steht für sich unter einer Linie statt eines Balkens (kein fremder Balken darüber), mit allen ihren Artikeln',
          len(ohne) == 1 and ohne[0]['linie'] and ohne[0]['anzahl'] is None and ohne[0]['titel'] == [norm_titel(m2['groups'][-1]['name'])] and ohne[0]['zeilen'] == soll['']
          and v.evaluate("(() => { const l = document.querySelector('#print-root .pl-trenn'), b = l.getBoundingClientRect(); return getComputedStyle(l).backgroundImage !== 'none' && b.width > 100 && b.height > 4; })()"), ohne)
    check('Vermerk „Entwurf“ im Kopf ist vorbereitet, aber ausgeschaltet; Mitarbeiter sehen die ganze Fußzeile', v.locator('#print-root .pl-entwurf').count() == 0 and 'Testbank Musterstadt' in s7['jeSeite'][-1]['fuss']['brief'])
    shot(v.locator('#print-root .pl-page').first, SH + '/druck-viele-bereiche-s1.png')
    shot(v.locator('#print-root .pl-page').nth(1), SH + '/druck-viele-bereiche-s2.png')
    zurueck(v)
    pdf7 = v.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-viele-bereiche.pdf', 'wb').write(pdf7)
    check('PDF mit vielen Bereichen: Seiten wie gesetzt, jede Zeile im PDF', pdf_seiten(pdf7) == s7['seiten'] and not pdf_alles(pdf7, s7), (pdf_seiten(pdf7), s7['seiten'], pdf_alles(pdf7, s7)[:3]))
    # jede Stufe mit beiden Fußzeilen-Varianten: immer vollständig und innerhalb der festen Vorgaben
    schlecht = []
    for st in STUFEN:
        for modus in ('letzte', 'jede'):
            laden(v, f'/?vorschau=1&stufe={st}&fuss={modus}')
            x = satz(v)
            if x['zeilen'] != vs['zeilen'] or x['stufe'] != st or heil(x, modus):
                schlecht.append((st, modus, len(x['zeilen']), heil(x, modus)))
            zurueck(v)
    check('viele Bereiche in jeder Stufe und mit Fußzeile auf jeder bzw. nur der letzten Seite: vollständig, drei Spalten, nichts läuft über', not schlecht, schlecht)

    # ---------- Einzelangebot: Druck der Angebotsseite und PDF des Servers ----------
    laden(v, '/?angebot=e-' + ez['id'])
    s8 = satz(v)
    f8 = s8['jeSeite'][-1]['fuss']
    z8 = [b['zeilen'] for b in s8['bloecke']]
    check('Einzelangebot: alle 46 Positionen auf einer Seite in der größten Schrift, gleichmäßig über die drei Spalten verteilt, ohne Werbung', len(s8['zeilen']) == 46 and s8['seiten'] == 1 and s8['stufe'] == 'normal'
          and len(z8) == 3 and max(z8) - min(z8) <= 3 and not s8['werb'] and heil(s8, 'letzte') == [], (len(s8['zeilen']), s8['seiten'], s8['stufe'], z8, heil(s8, 'letzte')))
    check('Einzelangebot: Kopf mit Angebotsnummer und Kunde, Seite 1 von 1', ez['nr'] in s8['jeSeite'][0]['kopf'] and 'Kantine Druck GmbH' in s8['jeSeite'][0]['kopf'] and 'Seite 1 von 1' in s8['jeSeite'][0]['kopf'], s8['jeSeite'][0]['kopf'])
    check('Einzelangebot: eigener Hinweis vor dem Hinweis zu Mengen und Fracht, darunter die Fußzeile', f8 and 'Lieferung nur dienstags' in f8['hinweis'] and f8['hinweis'].index('Lieferung nur dienstags') < f8['hinweis'].index('Die Preise verstehen sich')
          and 'Musterfleisch Test GmbH' in f8['brief'] and 'Testbank Musterstadt' in f8['brief'] and abs(f8['unten']) <= 1, f8 and f8['hinweis'][:100])
    check('Einzelangebot: nur eigene Preise, kein Bestand', 'P-0001' not in s8['text'] and not re.search(r'Bestand|Partie|MHD', s8['text']))
    shot(v.locator('#print-root .pl-page').first, SH + '/druck-einzelangebot.png')
    zurueck(v)
    pdf8 = v.pdf(prefer_css_page_size=True, print_background=True)
    open(SH + '/druck-einzelangebot.pdf', 'wb').write(pdf8)
    check('Einzelangebot-PDF (Browser): eine Seite, jede Position im PDF', pdf_seiten(pdf8) == 1 and not pdf_alles(pdf8, s8), (pdf_seiten(pdf8), pdf_alles(pdf8, s8)[:3]))
    st, h, spdf = roh(A, 'einzel_pdf&id=' + ez['id'])
    inh = pdf_text(spdf) if st == 200 else ''
    open(SH + '/druck-einzelangebot-server.pdf', 'wb').write(spdf)
    check('PDF des Servers (E-Mail-Anhang, PDF-Vorschau): Fußzeile mit drei Spalten und Registerzeilen, Siegel eingebettet', st == 200 and all(t in inh for t in ('Musterfleisch Test GmbH', 'www.example.org', 'Testbank Musterstadt',
          'Musterstadt B 000 00', 'Beispiel Verwaltung mbH')) and spdf.count(b'/Subtype /Image') == 2, (st, spdf.count(b'/Subtype /Image')))
    n_letzte = pdf_seiten(spdf)
    check('… Variante „letzte Seite“: Fußzeile einmal; Hinweis zu Mengen und Fracht einmal', inh.count('Musterfleisch Test GmbH') == 1 and inh.count('Mindestbestellmenge von ca. 300 kg') == 1 and 'Lieferung nur dienstags' in inh,
          (inh.count('Musterfleisch Test GmbH'), n_letzte))
    # kleines Einzelangebot (Grenze: weniger als drei Zeilen je Spalte): bleibt ein Block
    st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Klein', 'gueltigBis': bis, 'hinweis': '', 'positions': pos[:8]})
    assert st == 200, r
    laden(v, '/?angebot=e-' + r['angebot']['id'])
    s8k = satz(v)
    check('Einzelangebot mit 8 Positionen: ein Block, nicht über die Spalten verteilt (kein „Forts.“)', len(s8k['zeilen']) == 8 and [b['zeilen'] for b in s8k['bloecke']] == [8] and s8k['forts'] == 0 and heil(s8k, 'letzte') == [],
          ([b['zeilen'] for b in s8k['bloecke']], heil(s8k, 'letzte')))
    zurueck(v)
    # langes Einzelangebot über mehrere Seiten: im Browser gleichmäßig über drei Spalten je Seite; PDF des Servers in beiden Varianten
    pos2 = [{'code': str(20000 + n), 'name': f'Testposition {n} mit etwas längerer Bezeichnung, vakuumiert', 'qty': None, 'price': 9.5} for n in range(190)]
    st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Großes Angebot', 'gueltigBis': bis, 'hinweis': '', 'positions': pos2})
    assert st == 200, r
    ez2 = r['angebot']
    laden(v, '/?angebot=e-' + ez2['id'])
    s8g = satz(v)
    z8g = [[b['zeilen'] for b in s8g['bloecke']][i:i + 3] for i in range(0, len(s8g['bloecke']), 3)]
    check('Einzelangebot mit 190 Positionen: über mehrere Seiten, auf jeder Seite drei etwa gleich lange Spalten, Fußzeile nur am Ende, nichts läuft über',
          len(s8g['zeilen']) == 190 and 2 <= s8g['seiten'] == len(z8g) <= 3 and all(len(z) == 3 and max(z) - min(z) <= 3 for z in z8g) and heil(s8g, 'letzte') == [], (s8g['seiten'], z8g, heil(s8g, 'letzte')))
    zurueck(v)
    pdf8g = v.pdf(prefer_css_page_size=True, print_background=True)
    check('… PDF (Browser): Seiten wie gesetzt, jede Position im PDF', pdf_seiten(pdf8g) == s8g['seiten'] and not pdf_alles(pdf8g, s8g), (pdf_seiten(pdf8g), s8g['seiten'], pdf_alles(pdf8g, s8g)[:3]))
    lz = roh(A, 'einzel_pdf&id=' + ez2['id'])[2]; lt = pdf_text(lz); nl = pdf_seiten(lz)
    assert A.call('druck_fuss_save', {'fuss': dict(neu, modus='jede')})[0] == 200
    jz = roh(A, 'einzel_pdf&id=' + ez2['id'])[2]; j = pdf_text(jz); nj = pdf_seiten(jz)
    check('PDF des Servers über mehrere Seiten: „jede“ = Fußzeile je Seite, „letzte“ = einmal; alle Positionen, Seitenzahl stimmt', nj >= 2 and j.count('Musterfleisch Test GmbH') == nj and lt.count('Musterfleisch Test GmbH') == 1
          and nl <= nj and all(f'Testposition {n} ' in lt for n in (0, 95, 189)) and f'Seite {nl} von {nl}' in lt and f'Seite {nj} von {nj}' in j, (nj, nl, j.count('Musterfleisch Test GmbH'), lt.count('Musterfleisch Test GmbH')))
    assert A.call('druck_fuss_save', {'fuss': {'spalten': ['', '', ''], 'zeilen': ['', ''], 'modus': 'letzte'}})[0] == 200
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

    def drucke(a, ausloesen):
        """Druck auslösen und auf den neuen unsichtbaren Rahmen mit der Druckfassung warten (ein früherer Rahmen bleibt stehen, bis
        der Entwurf gespeichert ist – er wird vorher markiert); Rückgabe: der Rahmen nach dem Druckaufruf"""
        a.evaluate("document.querySelectorAll('#druck-frame').forEach((f) => { f.dataset.alt = '1'; })")
        ausloesen()
        h = a.wait_for_selector('#druck-frame:not([data-alt])', state='attached')
        fr = h.content_frame()
        fr.wait_for_function('window.__gedruckt >= 1', timeout=20000)
        return fr

    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    ctx.add_init_script(INIT)
    a = anmelden(ctx, 'admin', PW)
    # Seit 13.11.2026 liegen „Veröffentlichen“ und „An Kunden senden“ im Modul Versand – „Drucken“ steht an ihrer Stelle, direkt vor „⋯“
    lage = a.evaluate("""() => { const d = document.querySelector('#btn-drucken'), v = document.querySelector('#btn-preview'), r = (e) => e.getBoundingClientRect();
      return { text: d.innerText.trim(), sichtbar: r(d).width > 0, nachVorschau: !!(v.compareDocumentPosition(d) & Node.DOCUMENT_POSITION_FOLLOWING),
        vorMenue: d.nextElementSibling.classList.contains('menu-wrap'), rechts: r(v).right <= r(d).left + 1, zeile: Math.abs(r(d).top - r(v).top) < 4, hoehe: Math.abs(r(d).height - r(v).height) < 2, titel: d.title,
        send: !!document.querySelector('#btn-send'), pub: !!document.querySelector('#btn-publish') }; }""")
    check('Knopf „Drucken“ in der Leiste von „Angebot bearbeiten“: an der Stelle der früheren Knöpfe „An Kunden senden“ und „Veröffentlichen“ (rechts von „Vorschau“, direkt vor „⋯“, gleiche Zeile und Höhe)',
          lage['text'] == 'Drucken' and lage['sichtbar'] and lage['nachVorschau'] and lage['vorMenue'] and lage['rechts'] and lage['zeile'] and lage['hoehe'] and not lage['send'] and not lage['pub'], lage)
    check('… Beschriftung sagt, was gedruckt wird (gewähltes Angebot, Entwurf wie in der Vorschau)', 'Gewähltes Angebot' in lage['titel'] and 'Entwurf' in lage['titel'] and 'Vorschau' in lage['titel'], lage['titel'])
    shot(a.locator('#topbar'), SH + '/druck-knopf-1440.png')
    fr = drucke(a, lambda: a.click('#btn-drucken'))
    fs = fr.evaluate("""() => ({ seiten: document.querySelectorAll('#print-root .pl-page').length, zeilen: document.querySelectorAll('#print-root .al-band tr.row').length, n: window.__gedruckt, url: location.search,
      fuss: document.querySelectorAll('#print-root .pl-page .pl-fuss').length, vorschau: new URLSearchParams(location.search).has('vorschau') })""")
    check('„Drucken“ setzt den Entwurf des Wochenangebots in der Angebotsansicht (alle Artikel, Fußzeile) und ruft den Druck genau einmal auf',
          fs['zeilen'] == GESAMT and fs['seiten'] >= 2 and fs['n'] == 1 and fs['fuss'] == 1 and fs['vorschau'] and 'drucken' not in fs['url'] and 'angebot=' not in fs['url'], fs)
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    check('Eingabebereich selbst druckt nicht, Knopf danach wieder frei, Rahmen unsichtbar', a.evaluate('window.__gedruckt || 0') == 0 and not a.locator('#btn-drucken').is_disabled()
          and a.evaluate("(() => { const r = document.querySelector('#druck-frame').getBoundingClientRect(); return r.right <= 0 && r.width >= 1000; })()"))
    # ungespeicherte Änderung: vor dem Druck gespeichert, der Ausdruck zeigt sie
    erste = a.locator('#groups tr[data-id]').first
    code1 = erste.locator('input[data-f="code"]').input_value()
    feld = erste.locator('input[data-f="price"]')
    feld.fill('99,91')
    fr = drucke(a, lambda: a.click('#btn-drucken'))
    zeile = fr.evaluate("""(c) => { const r = [...document.querySelectorAll('#print-root .al-band tr.row')].find((x) => x.querySelector('.c-code').textContent.trim() === c); return r ? r.innerText : ''; }""", code1)
    d2 = A.call('draft')[1]
    check('ungespeicherte Eingabe wird vor dem Druck gespeichert und steht im Ausdruck', '99,91' in zeile and any(it.get('code') == code1 and it['price'].get('value') == 99.91 for it in d2['draft']['items']), zeile)
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    # gewähltes Kundenangebot
    a.locator('#offer-bar [data-offer]:has-text("Edeka")').first.click(); a.wait_for_selector('#offer-bar [data-offer="edeka"][aria-selected="true"]')
    fr = drucke(a, lambda: a.click('#btn-drucken'))
    fe = fr.evaluate("""() => ({ url: location.search, kopf: document.querySelector('#print-root .pl-ph').innerText, zeilen: document.querySelectorAll('#print-root .al-band tr.row').length })""")
    ed = A.call('offer&angebot=edeka&draft=1')[1]['offer']
    check('gewähltes Kundenangebot: „Drucken“ druckt dessen Entwurf (Name im Kopf, seine Artikel)', 'angebot=edeka' in fe['url'] and 'Edeka' in fe['kopf'] and fe['zeilen'] == len(ed['items']) > 0, (fe['url'], fe['kopf'], fe['zeilen'], len(ed['items'])))
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    # Schnittstelle für andere Module (Versand: „Angebote dieser Woche“): veröffentlichter Stand eines beliebigen Angebots
    fr = drucke(a, lambda: a.evaluate("window.WA.angebot.druck.drucken({ angebot: 'std', name: 'Wochenangebot' })"))
    fv = fr.evaluate("""() => ({ vorschau: new URLSearchParams(location.search).has('vorschau'), zeilen: document.querySelectorAll('#print-root .al-band tr.row').length, n: window.__gedruckt })""")
    check('Schnittstelle WA.angebot.druck.drucken({angebot}): druckt den veröffentlichten Stand (nicht den Entwurf) in derselben Fassung', fv['vorschau'] is False and fv['zeilen'] == 276 and fv['n'] == 1, fv)
    fr = drucke(a, lambda: a.evaluate("window.WA.angebot.druck.drucken({ angebot: 'edeka', entwurf: true })"))
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
    pvs = pv.evaluate("""() => ({ seiten: document.querySelectorAll('#print-root .pl-page').length, zeilen: document.querySelectorAll('#print-root .al-band tr.row').length })""")
    check('Vorschaufenster: „Drucken“ druckt die Vorschau in der Angebotsansicht, der Eingabebereich druckt nicht', pvs['zeilen'] == GESAMT and pvs['seiten'] >= 2 and a.evaluate('window.__gedruckt || 0') == 0, pvs)
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-vorschau', state='hidden')
    # Fenster „Fußzeile im Druck“
    a.click('#btn-more'); a.wait_for_selector('#menu-more [data-act="druck-fuss"]:not([hidden])')
    a.click('#menu-more [data-act="druck-fuss"]'); a.wait_for_selector('#dlg-druck-fuss[open] textarea[name=s0]')
    df = a.evaluate("""() => { const f = document.querySelector('#druck-fuss-body').elements; return { s0: f.s0.value, s2: f.s2.value, z1: f.z1.value, modus: f.modus.value, bank: f.bank.checked,
      hinweis: document.querySelector('.df-hinweis p').innerText, platz: f.s0.placeholder }; }""")
    check('Fenster „Fußzeile im Druck“ (Administrator): gespeicherte Texte, Wahl jede/letzte Seite, Bankschalter an, Hinweis zur Ansicht, Vorgabe als Platzhalter',
          df['s0'] == SP1 and df['s2'] == SP3 and df['z1'] == Z2 and df['modus'] == 'letzte' and df['bank'] is True and 'Mindestbestellmenge' in df['hinweis'] and 'Lagerstraße 17' in df['platz'], df)
    shot(a.locator('#dlg-druck-fuss'), SH + '/druck-fusszeile-fenster.png')
    a.fill('#druck-fuss-body textarea[name=s1]', SP2 + '\nFax 000 - 00 00 01')
    a.check('#druck-fuss-body input[name=modus][value=jede]')
    a.click('#df-ok'); a.wait_for_selector('#dlg-druck-fuss', state='hidden')
    g = doc('fracht')['druck']
    check('Speichern im Fenster: Text und Variante gespeichert, Bankschalter bleibt an', g['spalten'][1].endswith('Fax 000 - 00 00 01') and g['modus'] == 'jede' and g['bankGeschuetzt'] is True and g['updatedBy'], g)
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
    fr = drucke(b, lambda: b.click('#btn-drucken'))
    check('Bearbeiter druckt den Entwurf', fr.evaluate("document.querySelectorAll('#print-root .al-band tr.row').length") == GESAMT)
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
            fr = drucke(mo, lambda: mo.tap('#btn-drucken'))
            check('390 px: Druckfassung unabhängig vom Bildschirm (A4 quer, alle Artikel)', fr.evaluate("document.querySelectorAll('#print-root .al-band tr.row').length") == GESAMT
                  and fr.evaluate("+document.querySelector('#print-root .pl-doc').dataset.spalten") == 3)
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
    check('Angebotsseite 390 px: Druck wie am Desktop (gleiche Seitenzahl, Stufe und Füllung je Seite, drei Spalten, vollständig)', s9['seiten'] == N and s9['stufe'] == s['stufe'] and s9['zeilen'] == schirm['zeilen']
          and [x['fuell'] for x in s9['jeSeite']] == [x['fuell'] for x in s['jeSeite']] and heil(s9, 'letzte') == [], (s9['seiten'], N, s9['stufe'], [x['fuell'] for x in s9['jeSeite']], heil(s9, 'letzte')))
    zurueck(mk)
    mc.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
