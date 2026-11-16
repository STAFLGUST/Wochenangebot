"""Design je Angebot (Inhaber 16.11.2026): Vorlagen mit Raster (Spalten, Hoch-/Querformat) und Abschnitten (Bereiche und Gruppen
nach Namen, freie Texte), Wahl je Angebot mit Anpassung – wirksam im Druck und auf der Kundenseite (module/angebot/design.php,
assets/frontend.js plAbschnitte, assets/angebot-druck.js). Geprüft wird: ohne Design alles wie bisher (kein meta.design, drei
Spalten quer); Rechte (Vorlagen nur mit angebote.verwalten, Design je Angebot nur mit angebot.bearbeiten bzw.
einzelangebote.bearbeiten, ohne Anmeldung 401); Grenzen (Spalten 1–4, Format, Zahl der Abschnitte, Textlänge, Namen, Revision);
Anpassung speichert nur Abweichungen; genutzte Vorlage nicht löschbar; Kopieren übernimmt das Design; Einzelangebot; Kunde
bekommt nur Layout (keine weiteren Felder); Reihenfolge der Abschnitte im Web und im Druck gleich; Gruppen außerhalb des Designs
unter „Weitere Artikel“, kein Artikel fehlt (GR-010); Texte escaped; Druck mit 2 Spalten hoch und 4 Spalten quer (Seitengröße,
Spaltenzahl, Kästen in der Seite, keine Überlappung); Kundenseite bei 390 px einspaltig; Fenster „Design“ im Eingabebereich mit
Live-Vorschau; Bildschirmfotos bei 1280 und 390 px hell/dunkel; keine JavaScript-Fehler. Nur Testdaten (Seed-Angebot)."""
import json
import re
import sys
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, shot, storage_raw

PW = 'Sicheres-Passwort-1'
PW_E = 'Editor-Zugang-77'
PW_L = 'Leserin-Zugang-1'
PW_K = 'Kunden-Zugang-99'
MM = 96 / 25.4
res = []
errors = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False})
A.call('user_save', {'username': 'vera', 'name': 'Vera Bearbeiterin', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False, 'grant': [], 'deny': ['angebote.verwalten']})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': PW_L, 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': PW_E})[0] == 200
V = Client('198.51.100.5'); assert V.call('login', {'username': 'vera', 'password': PW_E})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': PW_L})[0] == 200
ANON = Client('203.0.113.70')

pub = ANON.call('offer')[1]['offer']
ITEMS = len(pub['items'])
SEKT = pub['sections']
GRUPPE = {g['id']: g for g in pub['groups']}
check('ohne Design (GR-006): kein meta.design im Angebot, keine Vorlagen, Revision 0', 'design' not in pub['meta'] and A.call('angebot_designs')[1].get('vorlagen') == []
      and A.call('angebot_designs')[1].get('rev') == 0 and doc('angebot-designs') is None, pub['meta'].keys())

# ---------- Rechte ----------
GASTRO = {'name': 'Gastro', 'raster': {'spalten': 2, 'format': 'hoch'}, 'abschnitte': [
    {'art': 'text', 'titel': 'Willkommen <b>Gastro</b>', 'text': 'Unsere Auswahl für die Küche.\n<img src=x onerror="window.__xss=1">'},
    {'art': 'gruppen', 'titel': '', 'inhalt': [{'bereich': SEKT[2]}]},
    {'art': 'gruppen', 'titel': 'Alles Weitere', 'inhalt': []}]}
st_anon = ANON.call('angebot_designs')[0]
check('Vorlagen lesen: ohne Anmeldung 401, Leser mit Modulzugang 200', st_anon == 401 and L.call('angebot_designs')[0] == 200, st_anon)
check('Vorlage anlegen ohne „Kundenangebote anlegen“ (angebote.verwalten): 403 – Leser und Bearbeiter ohne das Recht; ohne Anmeldung 401',
      L.call('angebot_design_save', dict(GASTRO, rev=0))[0] == 403 and V.call('angebot_design_save', dict(GASTRO, rev=0))[0] == 403
      and ANON.call('angebot_design_save', dict(GASTRO, rev=0))[0] in (401, 403) and A.call('angebot_designs')[1]['vorlagen'] == [])
check('Design je Angebot ohne „Entwurf bearbeiten“: 403', L.call('angebot_design_setzen', {'angebot': 'std', 'design': None})[0] == 403)

# ---------- Grenzen ----------
def save(c, body):
    return c.call('angebot_design_save', dict(body, rev=A.call('angebot_designs')[1]['rev']))


grenzen = {
    'Spalten 5': dict(GASTRO, raster={'spalten': 5, 'format': 'quer'}),
    'Spalten 0': dict(GASTRO, raster={'spalten': 0, 'format': 'quer'}),
    'Spalten als Text': dict(GASTRO, raster={'spalten': '2', 'format': 'quer'}),
    'Format': dict(GASTRO, raster={'spalten': 2, 'format': 'schraeg'}),
    '21 Abschnitte': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': f'T{i}', 'text': ''} for i in range(21)]),
    'unbekannte Art': dict(GASTRO, abschnitte=[{'art': 'bild', 'titel': 'Logo'}]),
    'leerer Text': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': '', 'text': '  '}]),
    '61 Bereiche': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'inhalt': [{'gruppe': f'G{i}'} for i in range(61)]}]),
    'Spalten im Abschnitt 7': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'spalten': 7, 'inhalt': []}]),
    'Name Standard': dict(GASTRO, name='standard'),
    'Name zu kurz': dict(GASTRO, name='G'),
}
codes = {k: save(E, v)[0] for k, v in grenzen.items()}
check('Grenzen: Spalten 1–4 (Zahl), Format quer/hoch, höchstens 20 Abschnitte und 60 Einträge, nur Text- und Gruppen-Abschnitte, Name nicht „Standard“ → 422',
      all(c == 422 for c in codes.values()) and A.call('angebot_designs')[1]['vorlagen'] == [], codes)
st, r = save(E, GASTRO)
gid = r.get('id')
st2, r2 = E.call('angebot_design_save', dict(GASTRO, rev=0))
check('Bearbeiter legt „Gastro“ an; zweites Anlegen mit altem Stand 409', st == 200 and gid and st2 == 409, (st, r, st2))
check('… gleicher Name ein zweites Mal 422', save(E, dict(GASTRO, name='gastro'))[0] == 422)
lang = dict(GASTRO, name='Lang', abschnitte=[{'art': 'text', 'titel': 'X' * 200, 'text': '\n'.join(['Zeile mit Text'] * 40) + 'Y' * 2000}])
st, r = save(E, lang)
gesp = [v for v in A.call('angebot_designs')[1]['vorlagen'] if v['name'] == 'Lang'][0]['abschnitte'][0]
check('Texte begrenzt: Überschrift 80 Zeichen, Text 30 Zeilen und 1000 Zeichen', st == 200 and len(gesp['titel']) == 80 and gesp['text'].count('\n') <= 29 and len(gesp['text']) <= 1000, (len(gesp['titel']), len(gesp['text'])))
LANG = r['id']

EXPORT = {'name': 'Export', 'raster': {'spalten': 4, 'format': 'quer'}, 'abschnitte': [
    {'art': 'gruppen', 'titel': 'Südamerika', 'inhalt': [{'gruppe': 'argentinien, frisch'}, {'gruppe': 'Uruguay, frisch'}]},
    {'art': 'gruppen', 'titel': '', 'spalten': 2, 'inhalt': [{'bereich': SEKT[3]}]}]}
st, r = save(A, EXPORT)
xid = r.get('id')
check('Administrator legt „Export“ an (4 Spalten quer, kein Abschnitt für übrige Gruppen)', st == 200 and xid)

# ---------- Design je Angebot ----------
st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
o = ANON.call('offer')[1]['offer']
check('Wochenangebot bekommt „Gastro“: ausgeliefert nur das Layout (Raster, Abschnitte) – ohne Kennung, Name oder Nutzung der Vorlage',
      st == 200 and o['meta'].get('design') == {'raster': GASTRO['raster'], 'abschnitte': [dict(a, titel=a.get('titel', '')) for a in GASTRO['abschnitte']]}
      and sorted(o['meta']['design']) == ['abschnitte', 'raster'] and gid not in json.dumps(o) and 'genutzt' not in json.dumps(o), o['meta'].get('design'))
check('Kunde sieht über das Design keine weiteren Felder (GR-001/GR-002): dieselben Artikel mit denselben Feldern wie ohne Design',
      [sorted(i) for i in o['items']] == [sorted(i) for i in pub['items']] and [i['id'] for i in o['items']] == [i['id'] for i in pub['items']]
      and {k for k in o if k != 'meta'} == {k for k in pub if k != 'meta'} and not re.search(r'"(qty|kg|lot|mhd|ek|variants)"', json.dumps(o)))
st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid, 'anpassung': {'raster': {'spalten': 2, 'format': 'quer'}, 'abschnitte': GASTRO['abschnitte']}}})
w = doc('angebote')['stdDesign']
check('Anpassung speichert nur Abweichungen (Spalten und Abschnitte wie die Vorlage fallen weg, Format bleibt)',
      st == 200 and w == {'vorlage': gid, 'anpassung': {'raster': {'format': 'quer'}}} and ANON.call('offer')[1]['offer']['meta']['design']['raster'] == {'spalten': 2, 'format': 'quer'}, w)
st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
check('Auf Vorlage zurücksetzen: Anpassung weg', st == 200 and doc('angebote')['stdDesign'] == {'vorlage': gid}, doc('angebote').get('stdDesign'))
check('unbekannte Vorlage 422, unbekanntes Angebot 404', E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': 'ffffffffff'}})[0] == 422
      and E.call('angebot_design_setzen', {'angebot': 'gibt-es-nicht', 'design': None})[0] == 404)
st, r = E.call('angebot_design_setzen', {'angebot': 'edeka', 'design': {'vorlage': '', 'anpassung': {'raster': {'spalten': 3, 'format': 'quer'}}}})
check('Standard ohne Abweichung = kein Design (nichts gespeichert)', st == 200 and r['wahl'] is None and 'design' not in [x for x in doc('angebote')['offers'] if x['id'] == 'edeka'][0])
st, r = E.call('angebot_design_setzen', {'angebot': 'edeka', 'design': {'vorlage': xid}})
check('Kundenangebot „Edeka“ bekommt „Export“', st == 200 and r['wirksam']['raster'] == EXPORT['raster'])
prot = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Vorlagen und Wahl je Angebot vermerkt', 'Design-Vorlage „Gastro“ angelegt' in prot and 'Design von „Wochenangebot“: Vorlage „Gastro“' in prot and 'Design von „Wochenangebot Edeka“: Vorlage „Export“' in prot)

# ---------- Löschen nur ungenutzter Vorlagen ----------
E.call('angebot_design_setzen', {'angebot': 'bela', 'design': {'vorlage': LANG}})
rev = A.call('angebot_designs')[1]['rev']
st, r = E.call('angebot_design_loeschen', {'rev': rev, 'id': LANG})
check('genutzte Vorlage lässt sich nicht löschen (409, Meldung nennt das Angebot)', st == 409 and 'Bela' in r.get('error', '') and any(v['id'] == LANG for v in A.call('angebot_designs')[1]['vorlagen']), r)
lst = A.call('angebot_designs&angebot=bela')[1]
check('Liste nennt die Nutzung je Vorlage und das Design des Angebots', [v for v in lst['vorlagen'] if v['id'] == LANG][0]['genutzt'] == ['Wochenangebot Bela'] and lst['wahl'] == {'vorlage': LANG}
      and lst['darfWahl'] is True and lst['darfVorlagen'] is True, lst.get('wahl'))
check('Löschen ohne Recht 403', V.call('angebot_design_loeschen', {'rev': rev, 'id': LANG})[0] == 403)
E.call('angebot_design_setzen', {'angebot': 'bela', 'design': None})
st, r = E.call('angebot_design_loeschen', {'rev': A.call('angebot_designs')[1]['rev'], 'id': LANG})
check('… nach dem Wechsel auf Standard löschbar', st == 200 and all(v['id'] != LANG for v in A.call('angebot_designs')[1]['vorlagen']), r)

# ---------- Kopieren übernimmt das Design ----------
d = A.call('draft')[1]
st, r = A.call('offer_kopieren', {'quelle': 'edeka', 'name': 'Edeka Export', 'rev': A.call('offers')[1]['rev'], 'revision': d['revision']})
neu = [x for x in doc('angebote')['offers'] if x['name'] == 'Edeka Export']
check('Kopie eines Angebots übernimmt das Design', st == 200 and neu and neu[0].get('design') == {'vorlage': xid} and r.get('design') is True, (st, neu and neu[0].get('design')))
st, r = A.call('offer_kopieren', {'quelle': 'std', 'name': 'Wochen Kopie', 'rev': A.call('offers')[1]['rev'], 'revision': A.call('draft')[1]['revision']})
neu2 = [x for x in doc('angebote')['offers'] if x['name'] == 'Wochen Kopie']
check('… auch vom Wochenangebot', st == 200 and neu2 and neu2[0].get('design') == {'vorlage': gid}, neu2 and neu2[0].get('design'))

# ---------- Kunde und Einzelangebot ----------
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Design GmbH', 'nr': 'KDES', 'email': 'kantine.design@example.org', 'active': True, 'angebote': ['edeka'], 'gruppe': '',
                              'login': {'username': 'kantine.design', 'password': PW_K, 'mustChange': False, 'active': True}})
assert st == 200, r
kid = r['customer']['id']
K = Client('203.0.113.71'); assert K.call('kunde_login', {'username': 'kantine.design', 'password': PW_K})[0] == 200
ko = K.call('offer&angebot=edeka')[1]['offer']
check('Kunde mit Kundenangebot bekommt dessen Design (nur Layout)', ko['meta'].get('design', {}).get('raster') == EXPORT['raster'] and sorted(ko['meta']['design']) == ['abschnitte', 'raster'])
its = pub['items']
bis = (date.today() + timedelta(days=20)).isoformat()
pos = [{'code': it.get('code') or '', 'name': it['name'], 'qty': None, 'price': round(8 + n * 0.37, 2)} for n, it in enumerate(its[:30])]
st, r = A.call('einzel_save', {'kid': kid, 'titel': 'Grillsaison', 'gueltigBis': bis, 'hinweis': '', 'positions': pos})
assert st == 200, r
ez = A.call('einzel_status', {'id': r['angebot']['id'], 'revision': r['angebot']['revision'], 'status': 'freigegeben'})[1]['angebot']
EID = 'e-' + ez['id']
check('Einzelangebot: Design nur mit einzelangebote.bearbeiten (Bearbeiter ohne das Recht 403)', E.call('angebot_design_setzen', {'angebot': EID, 'design': {'vorlage': xid}})[0] == 403)
st, r = A.call('angebot_design_setzen', {'angebot': EID, 'design': {'vorlage': '', 'anpassung': {'raster': {'spalten': 2}}}})
ke = K.call('offer&angebot=' + EID)[1]['offer']
check('Einzelangebot mit angepasstem Standard (2 Spalten): Kunde bekommt es, Revision und Freigabe unverändert',
      st == 200 and ke['meta'].get('design') == {'raster': {'spalten': 2, 'format': 'quer'}, 'abschnitte': []}
      and [e for e in doc('einzelangebote')['list'] if e['id'] == ez['id']][0]['revision'] == ez['revision'], ke['meta'].get('design'))


# ---------- Browser: Kundenseite und Druck ----------
WEB = """() => ({ reihe: [...document.querySelectorAll('#list .al-text h3, #list .al-band .al-st:not(.al-st-leer) h3')].map((h) => h.textContent.trim()),
  zeilen: [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id),
  k: [...document.querySelectorAll('#list .al-band')].map((b) => getComputedStyle(b).gridTemplateColumns.split(' ').length),
  texte: [...document.querySelectorAll('#list .al-text')].map((t) => t.innerText), html: [...document.querySelectorAll('#list .al-text')].map((t) => t.innerHTML).join(''),
  xss: !!document.querySelector('#list .al-text img, #list .al-text b') || !!window.__xss, sw: document.documentElement.scrollWidth })"""
DRUCK = """() => { const D = document.querySelector('#print-root .pl-doc'); if (!D) return null;
  const b = (e) => e.getBoundingClientRect();
  const seiten = [...D.querySelectorAll('.pl-page')].map((p) => {
    const pb = b(p), f = p.querySelector('.pl-in > .pl-fuss'), grenze = f ? b(f).top : pb.bottom;
    const kaesten = [...p.querySelectorAll('.al-band .al-grp, .al-band .pl-text, .al-band .al-st')].map(b), bl = [...p.querySelectorAll('.al-band .al-grp, .al-band .pl-text')].map(b);
    let ueber = 0;
    for (let i = 0; i < bl.length; i++) for (let j = i + 1; j < bl.length; j++) { const x = bl[i], y = bl[j]; if (Math.min(x.right, y.right) - Math.max(x.left, y.left) > 1 && Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 1) ueber++; }
    return { b: pb.width / (96 / 25.4), h: pb.height / (96 / 25.4), ueber, raus: Math.max(0, ...kaesten.map((k) => Math.max(pb.left - k.left, k.right - pb.right, pb.top - k.top, k.bottom - grenze))),
      k: [...p.querySelectorAll('.al-band')].map((bd) => getComputedStyle(bd).gridTemplateColumns.split(' ').length),
      kopfAmEnde: (() => { const bs = [...p.querySelectorAll('.al-band')], l = bs[bs.length - 1]; return !!(l && l.querySelector(':scope > .pl-text > h3:only-child')) && p !== [...D.querySelectorAll('.pl-page')].pop(); })() }; });
  const reihe = [...D.querySelectorAll('.al-band .pl-text h3, .al-band .al-st:not(.pl-trenn) h3')].filter((h) => !h.querySelector('.al-cont')).map((h) => h.textContent.trim());
  return { seiten, spalten: +D.dataset.spalten, format: D.dataset.format, zeilen: [...D.querySelectorAll('.al-band tr.row')].map((r) => r.dataset.id), reihe,
    text: D.innerText, xss: !!D.querySelector('.pl-text img, .pl-text b') || !!window.__xss, page: (document.querySelector('#page-style') || {}).textContent || '' }; }"""
INIT = "window.print = () => { window.__gedruckt = (window.__gedruckt || 0) + 1; window.dispatchEvent(new Event('beforeprint')); };"


def ohne_doppel(xs):
    return [x for i, x in enumerate(xs) if i == 0 or xs[i - 1] != x]


def druck(pg):
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    try:
        pg.wait_for_selector('#print-root .pl-doc .pl-page', state='attached', timeout=15000)
    except Exception:
        print('JavaScript-Fehler:', errors)
        raise
    pg.wait_for_function("[...document.querySelectorAll('#print-root img')].every((i) => i.complete)")
    pg.emulate_media(media='print')
    s = pg.evaluate(DRUCK)
    return s


def zurueck(pg):
    pg.emulate_media(media='null')
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")


def laden(pg, pfad='/'):
    pg.goto(BASE + pfad); pg.wait_for_selector('.al tr.row'); pg.evaluate('document.fonts.ready')


def heil(s, b, h, kmax):
    f = []
    for i, x in enumerate(s['seiten']):
        if abs(x['b'] - b) > .5 or abs(x['h'] - h) > .5: f.append(f"Seite {i + 1}: {x['b']:.1f}×{x['h']:.1f} mm")
        if x['ueber']: f.append(f"Seite {i + 1}: {x['ueber']} Überlappungen")
        if x['raus'] > .5: f.append(f"Seite {i + 1}: ragt {x['raus']:.1f} px aus der Seite")
        if any(k > kmax for k in x['k']): f.append(f"Seite {i + 1}: Zeile mit {x['k']} Spalten")
        if x['kopfAmEnde']: f.append(f"Seite {i + 1}: endet mit einer Überschrift")
    return f


SEKT = [re.sub(r'"([^"]{2,40}?)"', r'„\1“', x) for x in SEKT]   # Bereichsnamen, wie die Angebotsansicht sie zeigt: "Marke" → „Marke“
SCHRITT = ['Willkommen <b>Gastro</b>', SEKT[2], 'Alles Weitere', SEKT[0], SEKT[1], SEKT[3]]
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg)
    w = pg.evaluate(WEB)
    check('Kundenseite (1280 px, „Gastro“): Abschnitte in der Reihenfolge des Designs – Text, Bereich 3, „Alles Weitere“ mit den übrigen Bereichen',
          ohne_doppel(w['reihe']) == SCHRITT, w['reihe'])
    check('… jeder Artikel genau einmal (GR-010), zwei Spalten je Zeile', len(w['zeilen']) == ITEMS == len(set(w['zeilen'])) and set(w['k']) == {2}, (len(w['zeilen']), set(w['k'])))
    check('Text-Abschnitt escaped: Markup erscheint als Text, kein Element, kein Skript', not w['xss'] and '<img src=x' in w['texte'][0] and '&lt;b&gt;' in w['html'], w['texte'][:1])
    shot(pg, f'{SH}/design-kundenseite-1280-hell.png')
    s = druck(pg)
    check('Druck „Gastro“: A4 hoch 192 × 280 mm, zwei Spalten, nichts ragt aus der Seite, keine Überlappung, keine Seite endet mit einer Überschrift', s['format'] == 'hoch' and s['spalten'] == 2 and heil(s, 192, 280, 2) == [] and 'portrait' in s['page'],
          (s['format'], s['spalten'], heil(s, 192, 280, 2)[:3]))
    check('… dieselbe Reihenfolge der Abschnitte und Artikel wie auf der Kundenseite, Text escaped', ohne_doppel(s['reihe']) == SCHRITT and s['zeilen'] == w['zeilen'] and not s['xss'] and '<img src=x' in s['text'],
          (ohne_doppel(s['reihe']), len(s['zeilen'])))
    shot(pg.locator('#print-root'), f'{SH}/design-druck-gastro-hoch.png')
    zurueck(pg)
    ctx.close()

    # „Export“: 4 Spalten quer, Gruppen nach Namen, ein Abschnitt mit 2 Spalten, Rest unter „Weitere Artikel“
    E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': xid}})
    sued = [g['section'] for g in pub['groups'] if g['name'] in ('Argentinien, frisch', 'Uruguay, frisch')]
    ERW = ['Südamerika', sued[0], SEKT[3], 'Weitere Artikel', SEKT[0], SEKT[1], SEKT[2]]
    for schema in ('light', 'dark'):
        ctx = br.new_context(viewport={'width': 1280, 'height': 900}, color_scheme=schema)
        ctx.add_init_script(INIT)
        pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
        laden(pg)
        w = pg.evaluate(WEB)
        if schema == 'light':
            check('Kundenseite „Export“: Gruppen nach Namen (Groß-/Kleinschreibung egal), übrige Gruppen unter „Weitere Artikel“, kein Artikel fehlt (GR-010)',
                  ohne_doppel(w['reihe']) == ERW and len(w['zeilen']) == ITEMS == len(set(w['zeilen'])), (w['reihe'], len(w['zeilen'])))
            check('… Spalten je Abschnitt: 4, 2 (Abschnitt), 4', set(w['k']) == {4, 2}, w['k'])
            s = druck(pg)
            check('Druck „Export“: A4 quer 279 × 193 mm, höchstens vier Spalten, nichts ragt heraus, keine Überlappung, alle Artikel in Reihenfolge der Kundenseite',
                  s['format'] == 'quer' and s['spalten'] == 4 and heil(s, 279, 193, 4) == [] and s['zeilen'] == w['zeilen'] and ohne_doppel(s['reihe']) == ERW and 'landscape' in s['page'],
                  (heil(s, 279, 193, 4)[:3], ohne_doppel(s['reihe'])))
            check('… Zeilen mit vier und mit zwei Spalten', {4, 2} <= {k for x in s['seiten'] for k in x['k']}, [x['k'] for x in s['seiten']])
            shot(pg.locator('#print-root'), f'{SH}/design-druck-export-quer.png')
            zurueck(pg)
        shot(pg, f'{SH}/design-kundenseite-export-1280-{"hell" if schema == "light" else "dunkel"}.png')
        ctx.close()

    E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
    for schema in ('light', 'dark'):
        mc = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, color_scheme=schema)
        mc.add_init_script(INIT)
        mo = mc.new_page(); mo.on('pageerror', lambda ex: errors.append(str(ex)))
        laden(mo)
        w = mo.evaluate(WEB)
        check(f'Kundenseite 390 px ({schema}): einspaltig, Reihenfolge der Abschnitte bleibt, kein Querscrollen', set(w['k']) == {1} and ohne_doppel(w['reihe']) == SCHRITT and w['sw'] <= 390 and len(w['zeilen']) == ITEMS,
              (set(w['k']), w['sw']))
        shot(mo, f'{SH}/design-kundenseite-390-{"hell" if schema == "light" else "dunkel"}.png')
        mc.close()

    # ohne Design: wie bisher (drei Spalten quer, keine Texte)
    E.call('angebot_design_setzen', {'angebot': 'std', 'design': None})
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg)
    w = pg.evaluate(WEB)
    s = druck(pg)
    check('ohne Design: Kundenseite ohne Texte in Angebotsreihenfolge, Druck drei Spalten quer', not w['texte'] and ohne_doppel(w['reihe']) == SEKT and set(w['k']) == {3}
          and s['spalten'] == 3 and s['format'] == 'quer' and heil(s, 279, 193, 3) == [] and s['zeilen'] == w['zeilen'], (w['reihe'], s['spalten']))
    zurueck(pg)
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
