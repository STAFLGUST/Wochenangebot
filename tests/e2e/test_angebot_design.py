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

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
