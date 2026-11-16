"""Design je Angebot (Inhaber 16.11.2026, GR-010): Vorlagen mit Raster (Spalten, Hoch-/Querformat) und Abschnitten (Bereiche und
Gruppen nach Namen, freie Texte), Wahl je Angebot mit Anpassung – wirksam im Druck und auf der Kundenseite erst mit dem
Veröffentlichen (module/angebot/design.php, assets/frontend.js plAbschnitte, assets/angebot-druck.js).
Geprüft wird: ohne Design alles wie bisher; ein gespeichertes Design ist nicht öffentlich, bis veröffentlicht wird – Wochen-,
Kunden- und Sonderangebote über angebot.veroeffentlichen (auch ohne Entwurf), Einzelangebote mit der Freigabe bzw. beim Speichern
des freigegebenen Einzelangebots; die Änderungsliste vor dem Veröffentlichen nennt das Design; der Schnappschuss enthält nur Raster
und Abschnitte mit den Namen des Angebots (keine Vorlagen, keine Mitarbeiternamen); eine frühere Woche behält ihr Design; eine
geänderte Vorlage wirkt erst mit dem Veröffentlichen, nicht angepasste Angebote folgen ihr, angepasste Abschnitte bleiben; Rechte
(Vorlagen nur mit angebote.verwalten, Wahl nur mit angebot.bearbeiten bzw. einzelangebote.bearbeiten, ohne
angebot.veroeffentlichen wird nichts öffentlich, Kunde und anonymer Besucher 401, ohne CSRF 403, Wartung 503, Einzelangebote in
„genutzt“ nur mit einzelangebote.sehen); Grenzen und falsche Typen (422; im Hochformat höchstens 3 Spalten, Namen bis 120 Zeichen,
Größe bis 32 KB); Konflikt der Revision beim Löschen 409; Abschnitt einer neueren Fassung bleibt erhalten und wird nie
ausgeliefert; Kopieren übernimmt das Design; Reihenfolge der Abschnitte im Web und im Druck gleich, kein Artikel fehlt; Texte
escaped; Druck hoch (2 und 3 Spalten lesbar, 4 auf 3 begrenzt) und quer mit 4 Spalten; Einzelangebot mit Überschrift über dem
einzigen Block bleibt eine Seite; Kundenseite bei 390 px einspaltig; Fenster „Design“ mit Live-Vorschau und Hinweis „noch nicht
veröffentlicht“; Bildschirmfotos bei 1280 und 390 px hell/dunkel; keine JavaScript-Fehler. Nur Testdaten (Seed-Angebot)."""
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
res = []
errors = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:600]) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False})
A.call('user_save', {'username': 'vera', 'name': 'Vera Bearbeiterin', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False, 'grant': [], 'deny': ['angebote.verwalten']})
A.call('user_save', {'username': 'pia', 'name': 'Pia Ohnefreigabe', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False, 'grant': ['versand.zugang'], 'deny': ['angebot.veroeffentlichen']})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': PW_L, 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': PW_E})[0] == 200
V = Client('198.51.100.5'); assert V.call('login', {'username': 'vera', 'password': PW_E})[0] == 200
P = Client('198.51.100.6'); assert P.call('login', {'username': 'pia', 'password': PW_E})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': PW_L})[0] == 200
ANON = Client('203.0.113.70')


def oeffentlich(oid=None):
    return ANON.call('offer' + (f'&angebot={oid}' if oid else ''))[1]['offer']


def veroeffentlicht(oid):
    """Veröffentlichter Stand eines Angebots, wie Kunden ihn bekommen (Mitarbeiteransicht ohne Entwurf)"""
    return A.call('offer&angebot=' + oid)[1]['offer']


def veroeffentlichen(c=A):
    return c.call('versand_veroeffentlichen', {'revision': c.call('versand_aenderungen')[1]['revision']})


pub = oeffentlich()
ITEMS = len(pub['items'])
SEKT = pub['sections']
check('ohne Design (GR-006): kein meta.design im Angebot, keine Vorlagen, Revision 0', 'design' not in pub['meta'] and A.call('angebot_designs')[1].get('vorlagen') == []
      and A.call('angebot_designs')[1].get('rev') == 0 and doc('angebot-designs') is None, pub['meta'].keys())

# ---------- Rechte ----------
GASTRO = {'name': 'Gastro', 'raster': {'spalten': 2, 'format': 'hoch'}, 'abschnitte': [
    {'art': 'text', 'titel': 'Willkommen <b>Gastro</b>', 'text': 'Unsere Auswahl für die Küche.\n<img src=x onerror="window.__xss=1">'},
    {'art': 'gruppen', 'titel': '', 'inhalt': [{'bereich': SEKT[2]}]},
    {'art': 'gruppen', 'titel': 'Alles Weitere', 'inhalt': []}]}
GASTRO_LAYOUT = {'raster': GASTRO['raster'], 'abschnitte': [dict(a, titel=a.get('titel', '')) for a in GASTRO['abschnitte']]}
st_anon = ANON.call('angebot_designs')[0]
check('Vorlagen lesen: ohne Anmeldung 401, Leser mit Modulzugang 200', st_anon == 401 and L.call('angebot_designs')[0] == 200, st_anon)
check('Vorlage anlegen ohne „Kundenangebote anlegen“ (angebote.verwalten): 403 – Leser und Bearbeiter ohne das Recht; ohne Anmeldung 401',
      L.call('angebot_design_speichern', dict(GASTRO, rev=0))[0] == 403 and V.call('angebot_design_speichern', dict(GASTRO, rev=0))[0] == 403
      and ANON.call('angebot_design_speichern', dict(GASTRO, rev=0))[0] in (401, 403) and A.call('angebot_designs')[1]['vorlagen'] == [])
check('Design je Angebot ohne „Entwurf bearbeiten“: 403', L.call('angebot_design_setzen', {'angebot': 'std', 'design': None})[0] == 403)


# ---------- Grenzen und falsche Typen ----------
def save(c, body):
    return c.call('angebot_design_speichern', dict(body, rev=A.call('angebot_designs')[1]['rev']))


grenzen = {
    'Spalten 5': dict(GASTRO, raster={'spalten': 5, 'format': 'quer'}),
    'Spalten 0': dict(GASTRO, raster={'spalten': 0, 'format': 'quer'}),
    'Spalten als Text': dict(GASTRO, raster={'spalten': '2', 'format': 'quer'}),
    'Format': dict(GASTRO, raster={'spalten': 2, 'format': 'schraeg'}),
    'Hochformat mit 4 Spalten': dict(GASTRO, raster={'spalten': 4, 'format': 'hoch'}),
    'Hochformat, Abschnitt mit 4 Spalten': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'spalten': 4, 'inhalt': []}]),
    '21 Abschnitte': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': f'T{i}', 'text': ''} for i in range(21)]),
    'Art ohne Namen': dict(GASTRO, abschnitte=[{'art': 5, 'titel': 'X'}]),
    'leerer Text': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': '', 'text': '  '}]),
    '61 Bereiche': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'inhalt': [{'gruppe': f'G{i}'} for i in range(61)]}]),
    'Name mit 121 Zeichen': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'inhalt': [{'gruppe': 'G' * 121}]}]),
    'Spalten im Abschnitt 7': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'spalten': 7, 'inhalt': []}]),
    'Überschrift als Liste': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': ['x'], 'text': 'a'}]),
    'Text als Zahl': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': 'T', 'text': 5}]),
    'Inhalt als Objekt': dict(GASTRO, abschnitte=[{'art': 'gruppen', 'inhalt': {'gruppe': 'Rind'}}]),
    'über 32 KB': dict(GASTRO, abschnitte=[{'art': 'text', 'titel': f'T{i}', 'text': 'ü' * 1000} for i in range(20)]),
    'Name Standard': dict(GASTRO, name='standard'),
    'Name zu kurz': dict(GASTRO, name='G'),
}
codes = {k: save(E, v)[0] for k, v in grenzen.items()}
check('Grenzen und falsche Typen → 422: Spalten 1–4 (Zahl), im Hochformat höchstens 3 (Raster und Abschnitt), Format, 20 Abschnitte, 60 Einträge, Namen bis 120 Zeichen, '
      'Überschrift/Text/Inhalt mit falschem Typ, Größe bis 32 KB, Name nicht „Standard“', all(c == 422 for c in codes.values()) and A.call('angebot_designs')[1]['vorlagen'] == [], codes)
st, r = save(E, GASTRO)
gid = r.get('id')
st2, r2 = E.call('angebot_design_speichern', dict(GASTRO, rev=0))
check('Bearbeiter legt „Gastro“ an; zweites Anlegen mit altem Stand 409', st == 200 and gid and st2 == 409, (st, r, st2))
check('… gleicher Name ein zweites Mal 422', save(E, dict(GASTRO, name='gastro'))[0] == 422)
lang = dict(GASTRO, name='Lang', abschnitte=[{'art': 'text', 'titel': 'X' * 200, 'text': '\n'.join(['Zeile mit Text'] * 40) + 'Y' * 2000}])
st, r = save(E, lang)
gesp = [v for v in A.call('angebot_designs')[1]['vorlagen'] if v['name'] == 'Lang'][0]['abschnitte'][0]
check('Texte begrenzt: Überschrift 80 Zeichen, Text 30 Zeilen und 1000 Zeichen', st == 200 and len(gesp['titel']) == 80 and gesp['text'].count('\n') <= 29 and len(gesp['text']) <= 1000, (len(gesp['titel']), len(gesp['text'])))
LANG = r['id']
BILD = {'art': 'bild', 'titel': 'Logo', 'datei': 'abc123', 'breite': 2}
st, r = save(E, {'name': 'Neuere Fassung', 'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [BILD, {'art': 'gruppen', 'titel': 'Alles', 'inhalt': []}]})
NEUER = r.get('id')
gesp = [v for v in doc('angebot-designs')['vorlagen'] if v['id'] == NEUER]
check('Abschnitt einer neueren Fassung (unbekannte Art) wird unverändert gespeichert (GR-006)', st == 200 and gesp and gesp[0]['abschnitte'][0] == BILD, gesp)

EXPORT = {'name': 'Export', 'raster': {'spalten': 4, 'format': 'quer'}, 'abschnitte': [
    {'art': 'gruppen', 'titel': 'Südamerika', 'inhalt': [{'gruppe': 'argentinien, frisch'}, {'gruppe': 'Uruguay, frisch'}, {'gruppe': 'Gibt es nicht'}]},
    {'art': 'gruppen', 'titel': '', 'spalten': 2, 'inhalt': [{'bereich': SEKT[3]}]},
    {'art': 'gruppen', 'titel': 'Nur für Bela', 'inhalt': [{'gruppe': 'Bela-Spezialität'}]}]}
st, r = save(A, EXPORT)
xid = r.get('id')
check('Administrator legt „Export“ an (4 Spalten quer, kein Abschnitt für übrige Gruppen)', st == 200 and xid)

# ---------- Wählen ist nicht veröffentlichen ----------
p0 = pub['publishedAt']
st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
check('Wochenangebot bekommt „Gastro“: gespeichert, aber nicht öffentlich – Antwort „offen“, anonymer Besucher ohne Design, Stand unverändert',
      st == 200 and r['offen'] is True and r['wirksam'] == GASTRO_LAYOUT and 'design' not in oeffentlich()['meta'] and oeffentlich()['publishedAt'] == p0, r)
vz = A.call('offer&draft=1')[1]['offer']
check('Vorschau im Eingabebereich (Entwurf) zeigt das gespeicherte Design', vz['meta'].get('design') == GASTRO_LAYOUT, vz['meta'].get('design'))
ae = A.call('versand_aenderungen')[1]
dz = [z for z in ae['zeilen'] if z['art'] == 'design']
check('Änderungsliste vor dem Veröffentlichen nennt das Design – auch ohne Entwurf', not ae['entwurf'] and ae['anzahl'] == 1 and len(dz) == 1 and dz[0]['angebot'] == 'std'
      and dz[0]['von'] == 'Standard' and 'Vorlage „Gastro“' in dz[0]['zusatz'] and ae['jeAngebot'].get('std') == 1, ae)
check('Versand: Stand zählt das Design als offene Änderung', A.call('versand_start')[1]['aenderungen']['anzahl'] == 1)
st_p = P.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid, 'anpassung': {'abschnitte': [{'art': 'text', 'titel': 'Achtung', 'text': 'Neue Bankverbindung'}]}}})[0]
rev_p = P.call('versand_aenderungen')[1]['revision']
check('Bearbeiterin ohne „Angebot veröffentlichen“: Design speichern ja, veröffentlichen nein (403, auch über „publish“) – öffentlich bleibt alles, wie es war',
      st_p == 200 and P.call('versand_veroeffentlichen', {'revision': rev_p})[0] == 403 and P.call('publish', {'revision': rev_p})[0] == 403
      and 'Bankverbindung' not in json.dumps(oeffentlich(), ensure_ascii=False) and oeffentlich()['publishedAt'] == p0)
E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
nv = len(A.call('versions')[1]['versions'])
st, r = veroeffentlichen()
o = oeffentlich()
roh = json.dumps(o, ensure_ascii=False)
check('Veröffentlichen ohne Entwurf: anonymer Besucher bekommt das Layout als Schnappschuss – nur Raster und Abschnitte, ohne Kennung der Vorlage und ohne Mitarbeiternamen',
      st == 200 and o['meta'].get('design') == GASTRO_LAYOUT and sorted(o['meta']['design']) == ['abschnitte', 'raster'] and gid not in roh and 'Eddi' not in roh
      and 'genutzt' not in roh and o['publishedAt'] != p0, (st, r, o['meta'].get('design')))
check('… neue Version gesichert, Revision des Entwurfs unverändert (offene Fenster ohne Konflikt), Änderungsliste leer, zweites Veröffentlichen 409 „nichts offen“',
      len(A.call('versions')[1]['versions']) == nv + 1 and r['revision'] == ae['revision'] and A.call('versand_aenderungen')[1]['anzahl'] == 0
      and veroeffentlichen()[0] == 409, r)
check('Kunde sieht über das Design keine weiteren Felder (GR-001/GR-002): dieselben Artikel mit denselben Feldern wie ohne Design',
      [sorted(i) for i in o['items']] == [sorted(i) for i in pub['items']] and [i['id'] for i in o['items']] == [i['id'] for i in pub['items']]
      and {k for k in o if k != 'meta'} == {k for k in pub if k != 'meta'} and not re.search(r'"(qty|kg|lot|mhd|ek|variants)"', roh))
check('Protokoll: Wahl gespeichert („wirkt mit der nächsten Veröffentlichung“), Veröffentlichung nennt das Design',
      'Design von „Wochenangebot“ gespeichert: Vorlage „Gastro“' in json.dumps(A.call('log')[1], ensure_ascii=False)
      and 'Design: Wochenangebot' in json.dumps(A.call('log')[1], ensure_ascii=False))

st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid, 'anpassung': {'raster': {'spalten': 2, 'format': 'quer'}, 'abschnitte': GASTRO['abschnitte']}}})
w = doc('angebote')['stdDesign']
check('Anpassung speichert nur Abweichungen (Spalten und Abschnitte wie die Vorlage fallen weg, Format bleibt); „wirksam“ rechnet der Server',
      st == 200 and w == {'vorlage': gid, 'anpassung': {'raster': {'format': 'quer'}}} and r['wirksam']['raster'] == {'spalten': 2, 'format': 'quer'}, (w, r.get('wirksam')))
st, r = E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})
check('Auf Vorlage zurücksetzen: Anpassung weg, nichts mehr offen', st == 200 and doc('angebote')['stdDesign'] == {'vorlage': gid} and r['offen'] is False, doc('angebote').get('stdDesign'))
check('unbekannte Vorlage 422, unbekanntes Angebot 404', E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': 'ffffffffff'}})[0] == 422
      and E.call('angebot_design_setzen', {'angebot': 'gibt-es-nicht', 'design': None})[0] == 404)
falsch = [{'vorlage': [gid]}, {'vorlage': 123}, {'vorlage': gid, 'anpassung': 'x'}, {'vorlage': gid, 'anpassung': {'abschnitte': {'a': {'art': 'text', 'titel': 'x'}}}},
          {'vorlage': gid, 'anpassung': {'raster': {'format': 'hoch', 'spalten': 4}}}, 'Gastro']
codes = [E.call('angebot_design_setzen', {'angebot': 'std', 'design': d})[0] for d in falsch]
check('falsche Typen beim Wählen (Vorlage als Liste oder Zahl, Anpassung als Text, Abschnitte als Objekt, hoch mit 4 Spalten, Design als Text) → 422; das gespeicherte Design bleibt',
      codes == [422] * len(falsch) and doc('angebote')['stdDesign'] == {'vorlage': gid}, codes)
st, r = E.call('angebot_design_setzen', {'angebot': 'edeka', 'design': {'vorlage': '', 'anpassung': {'raster': {'spalten': 3, 'format': 'quer'}}}})
check('Standard ohne Abweichung = kein Design (nichts gespeichert)', st == 200 and r['wahl'] is None and 'design' not in [x for x in doc('angebote')['offers'] if x['id'] == 'edeka'][0])

# ---------- Kunde, Kundenangebot: Schnappschuss nur mit den Namen des Angebots ----------
rev = A.call('kunden')[1]['rev']
st, r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Design GmbH', 'nr': 'KDES', 'email': 'kantine.design@example.org', 'active': True, 'angebote': ['edeka'], 'gruppe': '',
                              'login': {'username': 'kantine.design', 'password': PW_K, 'mustChange': False, 'active': True}})
assert st == 200, r
kid = r['customer']['id']
K = Client('203.0.113.71'); assert K.call('kunde_login', {'username': 'kantine.design', 'password': PW_K})[0] == 200
st, r = E.call('angebot_design_setzen', {'angebot': 'edeka', 'design': {'vorlage': xid}})
check('Kundenangebot „Edeka“ bekommt „Export“: Kunde sieht es erst nach dem Veröffentlichen', st == 200 and r['wirksam']['raster'] == EXPORT['raster']
      and 'design' not in K.call('offer&angebot=edeka')[1]['offer']['meta'] and any(z['angebot'] == 'edeka' for z in A.call('versand_aenderungen')[1]['zeilen']))
veroeffentlichen()
kd = K.call('offer&angebot=edeka')[1]['offer']['meta'].get('design') or {}
check('… danach nur das Layout mit den Namen, die im Angebot vorkommen: „Gibt es nicht“ fehlt, der Abschnitt „Nur für Bela“ entfällt (er bliebe leer)',
      kd.get('raster') == EXPORT['raster'] and [a['titel'] for a in kd['abschnitte']] == ['Südamerika', '']
      and kd['abschnitte'][0]['inhalt'] == [{'gruppe': 'argentinien, frisch'}, {'gruppe': 'Uruguay, frisch'}] and 'Bela-Spezialität' not in json.dumps(kd), kd)
check('Protokoll: Vorlagen und Wahl je Angebot vermerkt', 'Design-Vorlage „Gastro“ angelegt' in json.dumps(A.call('log')[1], ensure_ascii=False)
      and 'Design von „Wochenangebot Edeka“ gespeichert: Vorlage „Export“' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ---------- Vorlage ändern: wirkt erst mit dem Veröffentlichen; nicht angepasste folgen, angepasste Abschnitte bleiben ----------
SAISON = {'name': 'Saison', 'raster': {'spalten': 2, 'format': 'quer'}, 'abschnitte': [{'art': 'text', 'titel': 'Saison A', 'text': ''}]}
st, r = save(E, SAISON)
sid = r['id']
E.call('angebot_design_setzen', {'angebot': 'bela', 'design': {'vorlage': sid}})
E.call('angebot_design_setzen', {'angebot': 'handelshof-efs', 'design': {'vorlage': sid, 'anpassung': {'abschnitte': [{'art': 'text', 'titel': 'Handelshof eigen', 'text': ''}]}}})
veroeffentlichen()
st = save(E, dict(SAISON, id=sid, raster={'spalten': 3, 'format': 'quer'}, abschnitte=[{'art': 'text', 'titel': 'Saison B', 'text': ''}]))[0]
b1, h1 = veroeffentlicht('bela')['meta']['design'], veroeffentlicht('handelshof-efs')['meta']['design']
ae = A.call('versand_aenderungen')[1]
check('Vorlage geändert: Kunden sehen weiter den veröffentlichten Stand; die Änderungsliste nennt beide Angebote',
      st == 200 and b1['abschnitte'][0]['titel'] == 'Saison A' and b1['raster']['spalten'] == 2 and h1['abschnitte'][0]['titel'] == 'Handelshof eigen'
      and {z['angebot'] for z in ae['zeilen'] if z['art'] == 'design'} == {'bela', 'handelshof-efs'}, (b1, h1, ae['zeilen']))
veroeffentlichen()
b2, h2 = veroeffentlicht('bela')['meta']['design'], veroeffentlicht('handelshof-efs')['meta']['design']
check('… nach dem Veröffentlichen folgt das nicht angepasste Angebot der Vorlage; das angepasste behält seine Abschnitte, Spalten folgen der Vorlage',
      b2 == {'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [{'art': 'text', 'titel': 'Saison B', 'text': ''}]}
      and h2 == {'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [{'art': 'text', 'titel': 'Handelshof eigen', 'text': ''}]}, (b2, h2))

# Hochformat: eine Anpassung mit 4 Spalten bleibt gültig, wechselt die Vorlage ins Hochformat, gilt höchstens 3
QUER = {'name': 'Quer', 'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [{'art': 'gruppen', 'titel': 'Alle', 'spalten': 4, 'inhalt': []}]}
st, r = save(E, QUER)
qid = r['id']
st1 = E.call('angebot_design_setzen', {'angebot': 'chefs-culinar', 'design': {'vorlage': qid, 'anpassung': {'raster': {'spalten': 4}}}})[0]
st2 = save(E, dict(QUER, id=qid, raster={'spalten': 3, 'format': 'hoch'}, abschnitte=[{'art': 'gruppen', 'titel': 'Alle', 'inhalt': []}]))[0]
st3 = E.call('angebot_design_setzen', {'angebot': 'edeka', 'design': {'vorlage': qid, 'anpassung': {'raster': {'spalten': 4}}}})[0]
veroeffentlichen()
cc = veroeffentlicht('chefs-culinar')['meta'].get('design')
check('Hochformat höchstens 3 Spalten: neue Wahl mit 4 Spalten auf einer Hochformat-Vorlage 422; eine ältere Anpassung wird beim Veröffentlichen auf 3 begrenzt',
      st1 == 200 and st2 == 200 and st3 == 422 and cc and cc['raster'] == {'spalten': 3, 'format': 'hoch'}, (st1, st2, st3, cc))

# Abschnitt einer neueren Fassung: wird nie ausgeliefert und zieht keine Gruppen an sich
E.call('angebot_design_setzen', {'angebot': 'bela', 'design': {'vorlage': NEUER}})
veroeffentlichen()
bd = veroeffentlicht('bela')['meta'].get('design')
check('Abschnitt einer neueren Fassung: im Schnappschuss nur die bekannten Abschnitte', bd == {'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [{'art': 'gruppen', 'titel': 'Alles', 'inhalt': []}]}, bd)

# Sonderangebot: derselbe Weg (veröffentlicht mit allen Angeboten)
assert A.call('kundengruppen_save', {'rev': 0, 'groups': [{'nr': '10', 'name': 'Gastronomie'}]})[0] == 200
heute = date.today().isoformat()
st, r = E.call('sonderangebot_save', {'name': 'Grillwoche Design', 'gruppen': ['10'], 'gueltig': {'modus': 'zeitraum', 'von': heute, 'bis': (date.today() + timedelta(days=3)).isoformat()},
                                     'rev': A.call('sonderangebote')[1]['rev']})
SID = r.get('id')
st2, r2 = E.call('angebot_design_setzen', {'angebot': SID, 'design': {'vorlage': sid}})
vor = veroeffentlicht(SID)['meta'].get('design')
veroeffentlichen()
nach = veroeffentlicht(SID)['meta'].get('design')
check('Sonderangebot: Design gespeichert, sichtbar erst nach dem Veröffentlichen', st == 200 and st2 == 200 and vor is None
      and nach == {'raster': {'spalten': 3, 'format': 'quer'}, 'abschnitte': [{'art': 'text', 'titel': 'Saison B', 'text': ''}]}, (st, r, vor, nach))

# ---------- Frühere Woche behält ihr Design ----------
alt = oeffentlich()
E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': xid}})
d = A.call('draft')[1]
m = json.loads(json.dumps(d.get('draft') or d['published']))
woche, jahr = m['meta']['week'], m['meta']['year']
m['meta']['week'] = woche + 1 if woche < 52 else woche - 1
st, r = A.call('publish', {'model': m, 'revision': d['revision']})
frueher = A.call(f'angebot_woche&woche={jahr}-{woche:02d}')[1]
check('frühere Woche behält ihr Design (Schnappschuss der damaligen Veröffentlichung), die neue Woche zeigt das neue (GR-106)',
      st == 200 and (frueher.get('offer') or {}).get('meta', {}).get('design') == alt['meta']['design'] == GASTRO_LAYOUT
      and oeffentlich()['meta']['design']['raster'] == EXPORT['raster'], (st, r, (frueher.get('offer') or {}).get('meta', {}).get('design')))

# ---------- Löschen nur ungenutzter Vorlagen ----------
E.call('angebot_design_setzen', {'angebot': 'bela', 'design': {'vorlage': LANG}})
rev = A.call('angebot_designs')[1]['rev']
st, r = E.call('angebot_design_loeschen', {'rev': rev, 'id': LANG})
check('genutzte Vorlage lässt sich nicht löschen (409, Meldung nennt das Angebot)', st == 409 and 'Bela' in r.get('error', '') and any(v['id'] == LANG for v in A.call('angebot_designs')[1]['vorlagen']), r)
lst = A.call('angebot_designs&angebot=bela')[1]
check('Liste nennt die Nutzung je Vorlage und das Design des Angebots mit Stand (offen)', [v for v in lst['vorlagen'] if v['id'] == LANG][0]['genutzt'] == ['Wochenangebot Bela']
      and lst['wahl'] == {'vorlage': LANG} and lst['offen'] is True and lst['darfWahl'] is True and lst['darfVorlagen'] is True, lst.get('wahl'))
check('Löschen ohne Recht 403, mit altem Stand der Vorlagen 409', V.call('angebot_design_loeschen', {'rev': rev, 'id': LANG})[0] == 403
      and A.call('angebot_design_loeschen', {'rev': rev - 1, 'id': LANG})[0] == 409)
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
check('… auch vom Wochenangebot', st == 200 and neu2 and neu2[0].get('design') == {'vorlage': xid}, neu2 and neu2[0].get('design'))

# ---------- Einzelangebot: Freigabe und Speichern sind das Veröffentlichen ----------
its = pub['items']
bis = (date.today() + timedelta(days=20)).isoformat()


def einzel(titel, n, freigeben=True):
    pos = [{'code': it.get('code') or '', 'name': it['name'], 'qty': None, 'price': round(8 + k * 0.37, 2)} for k, it in enumerate((its * 2)[:n])]
    st, r = A.call('einzel_save', {'kid': kid, 'titel': titel, 'gueltigBis': bis, 'hinweis': '', 'positions': pos})
    assert st == 200, r
    e = r['angebot']
    if freigeben: e = A.call('einzel_status', {'id': e['id'], 'revision': e['revision'], 'status': 'freigegeben'})[1]['angebot']
    return e


ez = einzel('Grillsaison', 30)
EID = 'e-' + ez['id']
check('Einzelangebot: Design nur mit einzelangebote.bearbeiten (Bearbeiter ohne das Recht 403)', E.call('angebot_design_setzen', {'angebot': EID, 'design': {'vorlage': xid}})[0] == 403)
ZWEI = {'raster': {'spalten': 2, 'format': 'quer'}, 'abschnitte': []}
st, r = A.call('angebot_design_setzen', {'angebot': EID, 'design': {'vorlage': '', 'anpassung': {'raster': {'spalten': 2}}}})
eintrag = [e for e in doc('einzelangebote')['list'] if e['id'] == ez['id']][0]
check('Einzelangebot (freigegeben) mit 2 Spalten: gespeichert, beim Kunden noch nicht sichtbar; Revision und Freigabe unverändert; Mitarbeiter sehen es',
      st == 200 and r['offen'] is True and r['freigegeben'] is True and 'design' not in K.call('offer&angebot=' + EID)[1]['offer']['meta']
      and eintrag['revision'] == ez['revision'] and eintrag['freigegebenAt'] == ez['freigegebenAt'] and A.call('offer&angebot=' + EID)[1]['offer']['meta'].get('design') == ZWEI, r)
st, r = A.call('einzel_save', {'id': ez['id'], 'revision': eintrag['revision'], 'kid': kid, 'titel': eintrag['titel'], 'gueltigBis': bis, 'hinweis': '',
                               'positions': [{k: p[k] for k in ('code', 'name', 'qty', 'price')} for p in eintrag['positions']]})
check('… nach dem Speichern des freigegebenen Einzelangebots sieht der Kunde das Design (Schnappschuss am Einzelangebot)',
      st == 200 and K.call('offer&angebot=' + EID)[1]['offer']['meta'].get('design') == ZWEI
      and A.call('angebot_designs&angebot=' + EID)[1]['offen'] is False, (st, r))
ez2 = einzel('Große Auswahl', 110, freigeben=False)
EID2 = 'e-' + ez2['id']
POSITIONEN = {'raster': {'spalten': 4, 'format': 'quer'}, 'abschnitte': [{'art': 'gruppen', 'titel': 'Ihre Positionen', 'inhalt': []}]}
st, r = A.call('angebot_design_setzen', {'angebot': EID2, 'design': {'vorlage': '', 'anpassung': POSITIONEN}})
ez2 = A.call('einzel_status', {'id': ez2['id'], 'revision': ez2['revision'], 'status': 'freigegeben'})[1]['angebot']
check('Einzelangebot im Entwurf: Design wirkt mit der Freigabe', st == 200 and r['freigegeben'] is False and K.call('offer&angebot=' + EID2)[1]['offer']['meta'].get('design') == POSITIONEN, r)
st, r = A.call('angebot_design_setzen', {'angebot': EID, 'design': {'vorlage': gid}})
gen_e = [v for v in E.call('angebot_designs')[1]['vorlagen'] if v['id'] == gid][0]['genutzt']
gen_a = [v for v in A.call('angebot_designs')[1]['vorlagen'] if v['id'] == gid][0]['genutzt']
st_l, r_l = E.call('angebot_design_loeschen', {'rev': A.call('angebot_designs')[1]['rev'], 'id': gid})
check('„genutzt“ und Meldung beim Löschen: Nummer des Einzelangebots nur mit einzelangebote.sehen, sonst nur die Anzahl',
      '1 Einzelangebot' in gen_e and not any('E-' in x for x in gen_e) and any(x.startswith('Einzelangebot E-') for x in gen_a)
      and st_l == 409 and '1 Einzelangebot' in r_l.get('error', '') and 'E-' not in r_l.get('error', ''), (gen_e, gen_a, r_l))
check('Fenster für ein Einzelangebot ohne einzelangebote.sehen: 403', E.call('angebot_designs&angebot=' + EID)[0] == 403)

# ---------- Kunde, anonymer Besucher, CSRF, Wartung ----------
AKTIONEN = [('angebot_design_setzen', {'angebot': 'std', 'design': None}), ('angebot_design_speichern', dict(GASTRO, name='Fremd', rev=0)),
            ('angebot_design_loeschen', {'rev': 0, 'id': xid}), ('angebot_designs', None)]
check('Kunde und anonymer Besucher: alle Design-Aktionen gesperrt (lesen 401, schreiben 401/403)', all(c.call(a, b)[0] in ((401,) if b is None else (401, 403)) for c in (K, ANON) for a, b in AKTIONEN),
      [(a, c.call(a, b)[0]) for c in (K, ANON) for a, b in AKTIONEN])
X = Client('198.51.100.9'); assert X.call('login', {'username': 'eddi', 'password': PW_E})[0] == 200
X.csrf = 'falsch'
check('ohne gültiges CSRF-Zeichen: schreibende Design-Aktionen 403', all(X.call(a, b)[0] == 403 for a, b in AKTIONEN[:3]) and doc('angebote')['stdDesign'] == {'vorlage': xid})
st_w = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Design'})[0]
w_e = (E.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': gid}})[0], E.call('angebot_designs')[0])
w_a = A.call('angebot_design_setzen', {'angebot': 'std', 'design': {'vorlage': xid}})[0]
A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': ''})
check('Wartung des Eingabebereichs (GR-107): Bearbeiter 503, Administrator arbeitet weiter', st_w == 200 and w_e == (503, 503) and w_a == 200
      and doc('angebote')['stdDesign'] == {'vorlage': xid}, (st_w, w_e, w_a))


# ---------- Browser: Kundenseite und Druck ----------
def waehlen_und_veroeffentlichen(oid, design):
    st, r = E.call('angebot_design_setzen', {'angebot': oid, 'design': design})
    assert st == 200, r
    if r['offen']: assert veroeffentlichen()[0] == 200


WEB = """() => ({ reihe: [...document.querySelectorAll('#list .al-text h3, #list .al-band .al-st:not(.al-st-leer) h3')].map((h) => h.textContent.trim()),
  zeilen: [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id),
  k: [...document.querySelectorAll('#list .al-band')].map((b) => getComputedStyle(b).gridTemplateColumns.split(' ').length),
  texte: [...document.querySelectorAll('#list .al-text')].map((t) => t.innerText), html: [...document.querySelectorAll('#list .al-text')].map((t) => t.innerHTML).join(''),
  xss: !!document.querySelector('#list .al-text img, #list .al-text b') || !!window.__xss, sw: document.documentElement.scrollWidth })"""
# Satz prüfen: Seitengröße, Spalten, nichts ragt heraus, keine Überlappung, keine Seite endet mit einer Überschrift; zeileMax: höchste
# Zeile im Verhältnis zur mittleren (lesbar: Bezeichnungen umbrechen höchstens in wenige Zeilen)
DRUCK = """() => { const D = document.querySelector('#print-root .pl-doc'); if (!D) return null;
  const b = (e) => e.getBoundingClientRect();
  const seiten = [...D.querySelectorAll('.pl-page')].map((p) => {
    const pb = b(p), f = p.querySelector('.pl-in > .pl-fuss'), grenze = f ? b(f).top : pb.bottom;
    const kaesten = [...p.querySelectorAll('.al-band .al-grp, .al-band .pl-fest, .al-band .al-st')].map(b), bl = [...p.querySelectorAll('.al-band .al-grp, .al-band .pl-fest')].map(b);
    let ueber = 0;
    for (let i = 0; i < bl.length; i++) for (let j = i + 1; j < bl.length; j++) { const x = bl[i], y = bl[j]; if (Math.min(x.right, y.right) - Math.max(x.left, y.left) > 1 && Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 1) ueber++; }
    return { b: pb.width / (96 / 25.4), h: pb.height / (96 / 25.4), ueber, raus: Math.max(0, ...kaesten.map((k) => Math.max(pb.left - k.left, k.right - pb.right, pb.top - k.top, k.bottom - grenze))),
      k: [...p.querySelectorAll('.al-band')].map((bd) => getComputedStyle(bd).gridTemplateColumns.split(' ').length),
      kopfAmEnde: (() => { const bs = [...p.querySelectorAll('.al-band')], l = bs[bs.length - 1]; return !!(l && l.querySelector(':scope > .pl-fest > h3:only-child')) && p !== [...D.querySelectorAll('.pl-page')].pop(); })() }; });
  const reihe = [...D.querySelectorAll('.al-band .pl-fest h3, .al-band .al-st:not(.pl-trenn) h3')].filter((h) => !h.querySelector('.al-cont')).map((h) => h.textContent.trim());
  const hz = [...D.querySelectorAll('tr.row')].map((r) => b(r).height).sort((x, y) => x - y);
  return { seiten, spalten: +D.dataset.spalten, format: D.dataset.format, zeilen: [...D.querySelectorAll('.al-band tr.row')].map((r) => r.dataset.id), reihe,
    zeileMax: hz.length ? hz[hz.length - 1] / hz[Math.floor(hz.length / 2)] : 0,
    text: D.innerText, xss: !!D.querySelector('.pl-fest img, .pl-fest b') || !!window.__xss, page: (document.querySelector('#page-style') || {}).textContent || '' }; }"""
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
    return pg.evaluate(DRUCK)


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


waehlen_und_veroeffentlichen('std', {'vorlage': gid})
SEKT = [re.sub(r'"([^"]{2,40}?)"', r'„\1“', x) for x in SEKT]   # Bereichsnamen, wie die Angebotsansicht sie zeigt: "Marke" → „Marke“
SCHRITT = ['Willkommen <b>Gastro</b>', SEKT[2], 'Alles Weitere', SEKT[0], SEKT[1], SEKT[3]]
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg)
    w = pg.evaluate(WEB)
    check('Kundenseite (1280 px, „Gastro“ veröffentlicht): Abschnitte in der Reihenfolge des Designs – Text, Bereich 3, „Alles Weitere“ mit den übrigen Bereichen',
          ohne_doppel(w['reihe']) == SCHRITT, w['reihe'])
    check('… jeder Artikel genau einmal (GR-010), zwei Spalten je Zeile', len(w['zeilen']) == ITEMS == len(set(w['zeilen'])) and set(w['k']) == {2}, (len(w['zeilen']), set(w['k'])))
    check('Text-Abschnitt escaped: Markup erscheint als Text, kein Element, kein Skript', not w['xss'] and '<img src=x' in w['texte'][0] and '&lt;b&gt;' in w['html'], w['texte'][:1])
    shot(pg, f'{SH}/design-kundenseite-1280-hell.png')
    s = druck(pg)
    check('Druck „Gastro“: A4 hoch 192 × 280 mm, zwei Spalten, nichts ragt aus der Seite, keine Überlappung, keine Seite endet mit einer Überschrift, Zeilen lesbar',
          s['format'] == 'hoch' and s['spalten'] == 2 and heil(s, 192, 280, 2) == [] and 'portrait' in s['page'] and s['zeileMax'] < 3.5,
          (s['format'], s['spalten'], heil(s, 192, 280, 2)[:3], s['zeileMax']))
    check('… dieselbe Reihenfolge der Abschnitte und Artikel wie auf der Kundenseite, Text escaped', ohne_doppel(s['reihe']) == SCHRITT and s['zeilen'] == w['zeilen'] and not s['xss'] and '<img src=x' in s['text'],
          (ohne_doppel(s['reihe']), len(s['zeilen'])))
    shot(pg.locator('#print-root'), f'{SH}/design-druck-gastro-hoch.png')
    zurueck(pg)
    ctx.close()

    # „Export“: 4 Spalten quer, Gruppen nach Namen, ein Abschnitt mit 2 Spalten, Rest unter „Weitere Artikel“
    waehlen_und_veroeffentlichen('std', {'vorlage': xid})
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

    # Abschnitt einer neueren Fassung (Vorlage „Neuere Fassung“): dieselben Gruppen wie ohne Design, nichts unter dem fremden Abschnitt
    waehlen_und_veroeffentlichen('std', {'vorlage': NEUER})
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg)
    w = pg.evaluate(WEB)
    check('Kundenseite mit einem Abschnitt einer neueren Fassung: er fehlt, alle Artikel stehen unter „Alles“', ohne_doppel(w['reihe']) == ['Alles'] + SEKT and len(w['zeilen']) == ITEMS, w['reihe'])
    ctx.close()

    waehlen_und_veroeffentlichen('std', {'vorlage': gid})
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
    waehlen_und_veroeffentlichen('std', None)
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

    # ---------- Eingabebereich: Fenster „Design“ mit Live-Vorschau ----------
    def anmelden(c, user, pw):
        a = c.new_page(); a.on('pageerror', lambda ex: errors.append(str(ex)))
        a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
        a.fill('#au-user', user); a.fill('#pw1', pw); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return a

    def rahmen(a):
        return a.wait_for_selector('#dlg-design[open] .ds-vorschau').content_frame()

    def satz_im_rahmen(a, spalten, fmt):
        fr = rahmen(a)
        fr.wait_for_function(f"(() => {{ const d = document.querySelector('#print-root > .pl-doc'); return d && d.dataset.spalten === '{spalten}' && d.dataset.format === '{fmt}'; }})()", timeout=20000)
        return fr

    def oeffnen(a):
        a.click('#btn-design'); a.wait_for_selector('#dlg-design[open] #ds-wahl')

    ZEILE_MAX = "(() => { const h = [...document.querySelectorAll('#print-root .pl-doc tr.row')].map((r) => r.getBoundingClientRect().height).sort((x, y) => x - y); return h.length ? h[h.length - 1] / h[Math.floor(h.length / 2)] : 0; })()"
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    a = anmelden(ctx, 'admin', PW)
    check('Knopf „Design“ in „Angebot bearbeiten“ sichtbar (Bearbeitungsrecht)', a.locator('#btn-design').is_visible())
    oeffnen(a)
    satz_im_rahmen(a, 3, 'quer')
    check('Fenster öffnet mit „Standard“ und Druckvorschau des Wochenangebots (3 Spalten quer), ohne Hinweis „offen“', a.input_value('#ds-wahl') == '' and 'Wochenangebot' in a.inner_text('#ds-titel')
          and a.locator('#ds-offen').count() == 0)
    a.select_option('#ds-wahl', gid)
    fr = satz_im_rahmen(a, 2, 'hoch')
    check('Vorlage „Gastro“ gewählt: Vorschau sofort 2 Spalten hoch, mit Text-Abschnitt', 'Willkommen' in fr.inner_text('#print-root') and a.inner_text('#ds-info').startswith('2 Spalten · hoch'), a.inner_text('#ds-info'))
    a.click('#ds-anpassen')
    a.click('.ds-editor [data-ds="spalten"][data-wert="3"]')
    fr = satz_im_rahmen(a, 3, 'hoch')
    zm = fr.evaluate(ZEILE_MAX)
    check('Hochformat: 4 Spalten nicht wählbar; 3 Spalten lesbar (keine Zeile ein Vielfaches der üblichen Höhe)', a.is_disabled('.ds-editor [data-ds="spalten"][data-wert="4"]') and 0 < zm < 3.5, zm)
    a.evaluate("document.querySelector('#dlg-design .ds-vorschau').contentWindow.postMessage({ wa: 'design', design: { raster: { spalten: 4, format: 'hoch' }, abschnitte: [] }, ansicht: 'druck' }, location.origin)")
    fr.wait_for_function("(() => { const d = document.querySelector('#print-root > .pl-doc'); return d && d.dataset.format === 'hoch' && !d.querySelector('.pl-fest'); })()")
    k4 = fr.evaluate("(() => ({ spalten: +document.querySelector('#print-root > .pl-doc').dataset.spalten, k: Math.max(...[...document.querySelectorAll('#print-root .al-band')].map((b) => getComputedStyle(b).gridTemplateColumns.split(' ').length)) }))()")
    check('… ein Design mit 4 Spalten hoch (an der Prüfung vorbei) setzt der Druck mit höchstens 3 Spalten', k4 == {'spalten': 3, 'k': 3}, k4)
    a.click('.ds-editor [data-ds="spalten"][data-wert="2"]'); a.click('.ds-editor [data-ds="spalten"][data-wert="3"]')
    satz_im_rahmen(a, 3, 'hoch')
    a.click('#dlg-design [data-ds="ansicht"][data-wert="web"]')
    rahmen(a).wait_for_function("!document.documentElement.classList.contains('druckansicht') && document.querySelectorAll('#list .al-text').length >= 1 && [...document.querySelectorAll('#list .al-band')].every((b) => getComputedStyle(b).gridTemplateColumns.split(' ').length <= 3)")
    check('Umschalter „Kundenseite“: Vorschau zeigt die Kundenansicht mit dem ungespeicherten Design', a.locator('#dlg-design [data-ds="ansicht"][data-wert="web"][aria-checked="true"]').count() == 1)
    a.click('#dlg-design [data-ds="ansicht"][data-wert="druck"]')
    satz_im_rahmen(a, 3, 'hoch')
    shot(a.locator('#dlg-design'), f'{SH}/design-fenster-1280-hell.png')
    a.click('#ds-fuss [data-ds="speichern"]'); a.wait_for_selector('#dlg-design:not([open])', state='attached')
    check('Speichern: nur die Abweichung (3 Spalten) an der Vorlage „Gastro“; Kunden sehen weiter das veröffentlichte Design (Standard)',
          doc('angebote')['stdDesign'] == {'vorlage': gid, 'anpassung': {'raster': {'spalten': 3}}} and 'design' not in oeffentlich()['meta'], doc('angebote').get('stdDesign'))
    oeffnen(a)
    satz_im_rahmen(a, 3, 'hoch')
    check('erneut geöffnet: „angepasst“ markiert, Hinweis „noch nicht veröffentlicht“', a.locator('#ds-links .ds-angepasst').count() == 1 and a.input_value('#ds-wahl') == gid
          and 'noch nicht veröffentlicht' in a.inner_text('#ds-offen'))
    shot(a.locator('#dlg-design'), f'{SH}/design-fenster-offen-1280-hell.png')
    a.click('#ds-zuruecksetzen')
    satz_im_rahmen(a, 2, 'hoch')
    a.click('#ds-fuss [data-ds="speichern"]'); a.wait_for_selector('#dlg-design:not([open])', state='attached')
    check('„Auf Vorlage zurücksetzen“ und Speichern: Anpassung weg', doc('angebote')['stdDesign'] == {'vorlage': gid}, doc('angebote').get('stdDesign'))

    # Vorlagen: neu, kopieren, umbenennen, löschen
    oeffnen(a)
    a.click('#ds-r-vorlagen')
    a.click('[data-ds="v-neu"]'); a.fill('#ds-name', 'Messe')
    a.click('.ds-editor [data-ds="spalten"][data-wert="4"]')
    a.click('[data-ds="neu-text"]'); a.fill('.ds-ab[data-i="0"] .ds-titel', 'Messe 2026'); a.fill('.ds-ab[data-i="0"] textarea', 'Stand 4, Halle B')
    a.click('[data-ds="neu-gruppen"]'); a.select_option('.ds-ab[data-i="1"] [data-f="neu"]', 'b:' + pub['sections'][0])
    a.click('.ds-ab[data-i="1"] [data-ds="hoch"]')
    satz_im_rahmen(a, 4, 'quer')
    shot(a.locator('#dlg-design'), f'{SH}/design-vorlage-1280-hell.png')
    a.click('.ds-editor [data-ds="format"][data-wert="hoch"]')
    satz_im_rahmen(a, 3, 'hoch')
    check('Vorlage ins Hochformat: 4 Spalten werden zu 3', a.get_attribute('.ds-editor [data-ds="spalten"][data-wert="3"]', 'aria-checked') == 'true')
    a.click('.ds-editor [data-ds="format"][data-wert="quer"]'); a.click('.ds-editor [data-ds="spalten"][data-wert="4"]')
    satz_im_rahmen(a, 4, 'quer')
    a.click('[data-ds="v-speichern"]'); a.wait_for_selector('.ds-vorlagen .ds-v:has-text("Messe")')
    mv = [v for v in A.call('angebot_designs')[1]['vorlagen'] if v['name'] == 'Messe']
    check('Neue Vorlage „Messe“ über das Fenster: 4 Spalten, Gruppen-Abschnitt vor dem Text (verschoben), Bereich nach Namen',
          mv and mv[0]['raster'] == {'spalten': 4, 'format': 'quer'} and [x['art'] for x in mv[0]['abschnitte']] == ['gruppen', 'text']
          and mv[0]['abschnitte'][0]['inhalt'] == [{'bereich': pub['sections'][0]}] and mv[0]['abschnitte'][1]['text'] == 'Stand 4, Halle B', mv)
    a.click('.ds-v:has-text("Messe") [data-ds="v-kopieren"]')
    check('Kopieren schlägt „Kopie von Messe“ vor', a.input_value('#ds-name') == 'Kopie von Messe')
    a.click('[data-ds="v-speichern"]'); a.wait_for_selector('.ds-v:has-text("Kopie von Messe")')
    a.click('.ds-v:has-text("Kopie von Messe") [data-ds="v-bearbeiten"]'); a.fill('#ds-name', 'Messe klein')
    a.click('[data-ds="v-speichern"]'); a.wait_for_selector('.ds-v:has-text("Messe klein")')
    namen = [v['name'] for v in A.call('angebot_designs')[1]['vorlagen']]
    check('Kopie gespeichert und umbenannt', 'Messe klein' in namen and 'Kopie von Messe' not in namen and 'Messe' in namen, namen)
    a.click('.ds-v:has-text("Messe klein") [data-ds="v-loeschen"]'); a.click('#confirm-body [data-v="1"]')
    a.wait_for_function("![...document.querySelectorAll('.ds-v b')].some((b) => b.textContent === 'Messe klein')")
    a.click('.ds-v:has-text("Gastro") [data-ds="v-loeschen"]'); a.click('#confirm-body [data-v="1"]')
    a.wait_for_function("document.querySelector('#ds-err').textContent.includes('noch genutzt')")
    check('Löschen: ungenutzte Vorlage weg; genutzte mit klarer Meldung abgelehnt', 'Messe klein' not in [v['name'] for v in A.call('angebot_designs')[1]['vorlagen']]
          and 'Wochenangebot' in a.inner_text('#ds-err') and any(v['id'] == gid for v in A.call('angebot_designs')[1]['vorlagen']), a.inner_text('#ds-err'))
    a.click('.ds-v:has-text("Neuere Fassung") [data-ds="v-bearbeiten"]')
    check('Abschnitt einer neueren Fassung: im Editor nur angezeigt', a.locator('.ds-ab.fremd').count() == 1 and 'neueren Fassung' in a.inner_text('.ds-ab.fremd'))
    a.fill('#ds-name', 'Neuere Fassung 2'); a.click('[data-ds="v-speichern"]'); a.wait_for_selector('.ds-v:has-text("Neuere Fassung 2")')
    check('… und beim Speichern unverändert behalten (GR-006)', [v for v in doc('angebot-designs')['vorlagen'] if v['id'] == NEUER][0]['abschnitte'][0] == BILD)
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-design:not([open])', state='attached')

    # Einzelangebot: dasselbe Fenster, Vorschau mit dem Einzelangebot (gespeichertes Design: Gastro, hoch 2)
    a.evaluate("(id) => window.WA.angebot.design.oeffnen({ angebot: id, name: 'Testangebot', einzel: true })", EID)
    satz_im_rahmen(a, 2, 'hoch')
    check('Einzelangebot: Fenster „Design“ mit Reiter „Dieses Einzelangebot“, Vorschau des Einzelangebots und Hinweis auf Speichern/Freigabe',
          a.inner_text('#ds-r-angebot') == 'Dieses Einzelangebot' and rahmen(a).locator('#print-root tr.row').count() == 30 and 'Einzelangebot gespeichert' in a.inner_text('#ds-offen'))
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-design:not([open])', state='attached')
    # Einzelangebot mit 110 Positionen (ohne Überschrift eine Seite): Überschrift über dem einzigen Block – weiter eine Seite, gleichmäßig verteilt
    a.evaluate("(id) => window.WA.angebot.design.oeffnen({ angebot: id, name: 'Große Auswahl', einzel: true })", EID2)
    fr = satz_im_rahmen(a, 4, 'quer')
    mit = fr.evaluate("(() => { const d = document.querySelector('#print-root > .pl-doc'); return { seiten: +d.dataset.seiten, fuell: [...d.querySelectorAll('.pl-page')].map((p) => +p.dataset.fuell), kopf: !!d.querySelector('.pl-fest h3') }; })()")
    check('Einzelangebot (110 Positionen, quer, 4 Spalten) mit Überschrift: eine Seite, die Überschrift steht darüber', mit['seiten'] == 1 and mit['kopf'] and mit['fuell'][0] > 80, mit)
    shot(a.locator('#dlg-design'), f'{SH}/design-einzel-ueberschrift-1280-hell.png')
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-design:not([open])', state='attached')
    # Modul Versand (gespeichert ist noch „Gastro“ am Wochenangebot): die Liste „Veröffentlichen“ nennt das Design; danach sehen Kunden es
    a.goto(BASE + '/module/versand/'); a.wait_for_selector('#vs-app:not([hidden]) #vs-s1')
    check('Versand: Schritt 1 offen, „Veröffentlichen“ möglich', a.is_enabled('#vs-pub') and 'nicht veröffentlicht' in a.inner_text('#vs-s1'), a.inner_text('#vs-s1'))
    a.click('#vs-pub'); a.wait_for_selector('#dlg-pub[open] .vs-aend')
    pt = a.inner_text('#dlg-pub').lower()   # Überschriften der Liste in Großbuchstaben (CSS)
    check('Versand: Fenster „Veröffentlichen“ listet das Design des Wochenangebots', 'design (druck und kundenseite) (1)' in pt and 'vorlage „gastro“' in pt and 'standard → 2 spalten, hoch' in pt, pt[-400:])
    a.evaluate("document.querySelector('#dlg-pub .vs-aend:last-of-type').scrollIntoView()")
    shot(a.locator('#dlg-pub'), f'{SH}/design-versand-1280-hell.png')
    a.click('#pub-jetzt'); a.wait_for_selector('#dlg-fertig[open]')
    check('… nach „Jetzt veröffentlichen“ sehen Kunden das Design', oeffentlich()['meta'].get('design', {}).get('raster') == GASTRO['raster'])
    ctx.close()

    for schema in ('light', 'dark'):
        for breite, hoehe in ((1280, 900), (390, 844)):
            c = br.new_context(viewport={'width': breite, 'height': hoehe}, color_scheme=schema, **({'is_mobile': True, 'has_touch': True, 'device_scale_factor': 2} if breite == 390 else {}))
            a = anmelden(c, 'admin', PW)
            oeffnen(a)
            a.click('#ds-anpassen')
            satz_im_rahmen(a, 2, 'hoch')
            m = a.evaluate("""() => { const d = document.querySelector('#dlg-design').getBoundingClientRect(), f = [...document.querySelectorAll('#dlg-design .ds-links button, #dlg-design .ds-links input, #dlg-design .ds-links select, #dlg-design .ds-links textarea')].filter((e) => e.offsetParent).map((e) => e.getBoundingClientRect());
              return { l: d.left, r: d.right, raus: Math.max(0, ...f.map((x) => x.right - d.right)), klein: f.filter((x) => x.height < 30).length, sw: document.documentElement.scrollWidth }; }""")
            if breite == 390:
                check(f'390 px ({schema}): Fenster passt, nichts ragt heraus, Bedienelemente mindestens 30 px hoch', m['l'] >= 0 and m['r'] <= 390.5 and m['raus'] <= .5 and m['klein'] == 0 and m['sw'] <= 390, m)
            shot(a.locator('#dlg-design'), f'{SH}/design-fenster-{breite}-{"hell" if schema == "light" else "dunkel"}.png')
            c.close()

    # Leser: kein Knopf, der Server lehnt ab (oben geprüft)
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    a = anmelden(ctx, 'lea', PW_L)
    check('Leser ohne Bearbeitungsrecht: Knopf „Design“ ausgeblendet', a.locator('#btn-design').is_hidden())
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
