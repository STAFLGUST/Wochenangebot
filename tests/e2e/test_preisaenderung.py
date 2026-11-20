"""Angebot „mit Preisänderung“ (Inhaber 20.11.2026): je Artikel die Veränderung zur Vorwoche (▼ günstiger, ▲ teurer, neu) als
Zusatzfunktion – auf der Angebotsseite und im Druck nur mit ?vergleich=vorwoche bzw. =aenderungen, im Versand nur mit Schalter.
Geprüft über die Aktion offer (Verhalten, nicht das Speicherformat): ohne Vorwoche null; ohne Parameter unverändert (kein
„vorwoche“), mit Parameter nur {kw, jahr, aenderungen} – nur geänderte und neue Artikel, Zuordnung über Art.-Nr. und Bezeichnung
auch bei neuen Artikel-IDs; jeder Kunde gegen sein eigenes Angebot der Vorwoche (Kundenangebot A, B, eigene Artikelliste H);
ein in der Vorwoche im Wochenangebot ausgeblendeter Artikel ist dort „neu“; neue Variante mit vorhandener Art.-Nr. „neu“; gleiche
Bezeichnung ohne Art.-Nr. in zwei Gruppen getrennt; später angelegtes Angebot ohne Vergleich (nie Wochenangebotspreise);
öffentlich keine Kundenpreise (GR-002), Kunde ohne Recht 403, ohne Anmeldung 401; keine Mengen/MHD/EK (GR-001/GR-008);
Vorschau des Entwurfs mit Vergleich; Veröffentlichen scheitert nicht an einer kaputten Vorwoche; Jahreswechsel KW 1 → KW 53.
Angebotsseite: Hinweise (Klasse, Zeichen) und Legende nur mit Parameter, Kurzfassung „Nur Änderungen“, ohne Vorwoche ein Hinweis
statt des ganzen Angebots; Druck mit Vergleich: dieselben Seiten, Stufe und Zeilenhöhen wie ohne, Hinweis kleiner als die
Zeilenschrift und innerhalb der Zelle; Karten am Handy (390 px) mit Pille; „Angebot bearbeiten“: „Drucken“ wie bisher, Pfeil mit
Menü „Zusatz“, das Menü „⋯“ schließt beim Öffnen; Versand: Vorschau und E-Mail mit Schalter (Übersicht, Links mit
vergleich=vorwoche, „Nur Änderungen“), ohne Schalter wie bisher, nur echte Wahrheitswerte, Übersicht in der Vorschau nur mit
Zugang zum Angebot, Protokoll „mit Preisänderung“; Fenster „Wochenangebot senden“ mit Zusatz; keine JavaScript-Fehler.
Nur Testdaten (Seed-Angebot, erfundene Kunden)."""
import json
import re
import sys
from copy import deepcopy

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import BASE, SH, SMTP_PORT, shot, storage_write, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:600]) if i and not c else ''))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200

# ---------- Kundenangebote, Kunden, Versender ----------
cur = A.call('offers')[1]
assert A.call('offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [
    {'id': 'kunde-a', 'name': 'Angebot Kunde A', 'fallback': 'standard'}, {'id': 'kunde-b', 'name': 'Angebot Kunde B', 'fallback': 'standard'},
    {'id': 'kunde-h', 'name': 'Angebot Kunde H', 'fallback': 'hidden'}]})[0] == 200
kid = {}
for nr, (firma, ang, user) in enumerate([('Testküche Alpha GmbH', 'kunde-a', 'alpha'), ('Beispielhandel Beta KG', 'kunde-b', 'beta')]):
    rev = A.call('kunden')[1]['rev']
    st, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': firma, 'nr': f'K-90{nr}', 'email': f'{user}@kunde.example', 'active': True, 'angebote': [ang],
                                  'login': {'username': user, 'password': 'Kunden-Kennwort-5', 'mustChange': False, 'active': True}})
    assert st == 200, r
    kid[user] = r['customer']['id']
A.call('user_save', {'id': '', 'name': 'Sina Sender', 'username': 'sina', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-55', 'mustChange': False})
sid = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == 'sina')
A.call('user_save', {'id': sid, 'name': 'Sina Sender', 'role': 'viewer', 'active': True, 'grant': ['versand.zugang', 'wochenangebot.senden'], 'deny': []})
S = Client('198.51.100.21')
assert S.call('login', {'username': 'sina', 'password': 'Leser-Zugang-55'})[0] == 200
# Versender ohne Zugang zum Angebot: die Übersicht (Kundenpreise) erscheint in seiner Vorschau nicht
A.call('user_save', {'id': '', 'name': 'Otto Ohnepreis', 'username': 'otto', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-56', 'mustChange': False})
oid_ = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == 'otto')
A.call('user_save', {'id': oid_, 'name': 'Otto Ohnepreis', 'role': 'viewer', 'active': True, 'grant': ['versand.zugang', 'wochenangebot.senden'], 'deny': ['angebot.zugang']})
O = Client('198.51.100.22')
assert O.call('login', {'username': 'otto', 'password': 'Leser-Zugang-56'})[0] == 200


def kunde(user):
    c = Client('198.51.100.3' + str(len(user)))
    assert c.call('kunde_login', {'username': user, 'password': 'Kunden-Kennwort-5'})[0] == 200
    return c


KA, KB, P = kunde('alpha'), kunde('beta'), Client('198.51.100.99')


def veroeffentlichen(m):
    d = A.call('draft')[1]
    st, r = A.call('publish', {'model': m, 'revision': d['revision']})
    assert st == 200, r


# ---------- KW 43 (Vorwoche): Seed mit Kundenpreisen für D (A, B), eigener Liste H (G, U, OC1, OC2), X im Wochenangebot ausgeblendet ----------
m = deepcopy(A.call('draft')[1].get('published'))
codes = {}
for it in m['items']:
    codes[it.get('code')] = codes.get(it.get('code'), 0) + 1
frei = [i for i, it in enumerate(m['items']) if it.get('code') and codes[it['code']] == 1 and it['price'].get('status') == 'value']
G, T, U, D, X = frei[0], frei[1], frei[2], frei[3], frei[4]
alt = {k: m['items'][i]['price']['value'] for k, i in (('G', G), ('T', T), ('U', U), ('D', D))}
VAL = lambda v: {'status': 'value', 'value': v}   # noqa: E731
NUR_H = lambda v: {'std': {'status': 'hidden'}, 'kunde-a': {'status': 'hidden'}, 'kunde-b': {'status': 'hidden'}, 'kunde-h': VAL(v)}   # noqa: E731
m['items'][D]['variants'] = {'kunde-a': VAL(20.0), 'kunde-b': VAL(30.0)}
m['items'][G]['variants'] = {'kunde-h': VAL(10.0)}
m['items'][U]['variants'] = {'kunde-h': VAL(11.0)}
m['items'][X]['variants'] = {'std': {'status': 'hidden'}}
g0, g1 = m['groups'][0]['id'], m['groups'][1]['id']
for oid, gid, v in (('oc1', g0, 7.0), ('oc2', g1, 8.0)):   # gleiche Bezeichnung ohne Art.-Nr. in zwei Gruppen (nur Liste H)
    m['items'].append({'id': oid, 'code': None, 'name': 'Testartikel ohne Nummer', 'category': 'Rind', 'origin': None, 'condition': 'frisch',
                       'groupId': gid, 'price': VAL(v), 'altPrices': [], 'variants': NUR_H(v)})
veroeffentlichen(m)
check('ohne veröffentlichte Vorwoche (KW 42): Vergleich null', P.call('offer&vergleich=vorwoche')[1].get('vorwoche', 'fehlt') is None,
      P.call('offer&vergleich=vorwoche')[1].get('vorwoche', 'fehlt'))

# ---------- KW 44: G günstiger, T teurer, U gleich, D nur für Kunde A günstiger, N neu; alle Artikel-IDs neu (wie ein neuer Excel-Import) ----------
m2 = deepcopy(A.call('draft')[1].get('published'))
m2['meta']['week'] = 44
m2['items'][G]['price'] = {'status': 'value', 'value': round(alt['G'] - 2, 2)}
m2['items'][T]['price'] = {'status': 'value', 'value': round(alt['T'] + 1, 2)}
m2['items'][T]['name'] = 'Steakhüfte mit Deckel, ca. 6–8 kg, vakuumiert, Reifung 21 Tage, frisch'   # lang: zweizeilig; Zuordnung über die Art.-Nr.
m2['items'][D]['variants'] = {'kunde-a': VAL(19.0), 'kunde-b': VAL(30.0)}
m2['items'][G]['variants'] = {'kunde-h': VAL(9.0)}
m2['items'][X]['variants'] = {}
next(it for it in m2['items'] if it['id'] == 'oc1')['variants'] = NUR_H(6.0)
# neue Variante mit der Art.-Nr. von U in einer anderen Gruppe (nur Liste H): „neu“, nicht „▲“ gegen U
m2['items'].append({'id': 'var1', 'code': m2['items'][U]['code'], 'name': 'Variante gefroren', 'category': 'Rind', 'origin': None, 'condition': 'gefroren',
                    'groupId': g1 if m2['items'][U]['groupId'] != g1 else g0, 'price': VAL(12.0), 'altPrices': [], 'variants': NUR_H(12.0)})
for it in m2['items']:
    it['id'] = 'k44' + it['id']
    it.pop('vorwoche', None)
m2['items'].insert(0, {'id': 'neu1', 'code': '99001', 'name': 'Testartikel neu', 'category': 'Rind', 'origin': None, 'condition': 'frisch',
                       'groupId': m2['items'][0]['groupId'], 'price': VAL(9.99), 'altPrices': [], 'variants': {'kunde-h': VAL(5.0)}})
ID = {k: m2['items'][i + 1]['id'] for k, i in (('G', G), ('T', T), ('U', U), ('D', D), ('X', X))}
ID['N'] = 'neu1'
veroeffentlichen(m2)
NEU = {'art': 'neu'}
RUNTER = lambda k, d: {'art': 'guenstiger', 'd': d, 'alt': alt[k]}   # noqa: E731

d0 = A.call('draft')[1]
check('… nicht im Entwurf weitergetragen (clean_model verwirft die Felder)', not d0.get('draft') or all('vorwoche' not in x for x in d0['draft']['items']))

# ---------- Aktion offer ----------
st, ohne, roh0 = P.call('offer', raw=True)
check('ohne Parameter: keine „vorwoche“, Artikel ohne Vergleichsfelder, kein meta.vorwoche (wie bisher)',
      st == 200 and 'vorwoche' not in ohne and 'vorwoche' not in roh0, [k for k in ohne])
st, mit, roh1 = P.call('offer&vergleich=vorwoche', raw=True)
vw = mit.get('vorwoche') or {}
check('öffentliches Wochenangebot mit vergleich=vorwoche: nur {kw, jahr, aenderungen}, KW 43',
      st == 200 and set(vw) == {'kw', 'jahr', 'aenderungen'} and vw['kw'] == 43 and vw['jahr'] == 2026, vw.keys())
ae = vw.get('aenderungen', {})
check('… nur Änderungen: G ▼ 2,00, T ▲ 1,00 (umbenannt, Zuordnung über die Art.-Nr. trotz neuer IDs), N neu, X neu (in KW 43 im Wochenangebot ausgeblendet); U und D unverändert fehlen',
      ae == {ID['G']: RUNTER('G', -2.0), ID['T']: {'art': 'teurer', 'd': 1.0, 'alt': alt['T']}, 'neu1': NEU, ID['X']: NEU}, ae)
check('GR-002: öffentlich keine Kundenpreise (20/30 von A/B) und keine Angebotskennungen der Kunden', all(x.get('alt') not in (20.0, 30.0, 10.0) for x in ae.values())
      and 'kunde-a' not in roh1 and 'kunde-b' not in roh1 and 'kunde-h' not in roh1)
check('GR-001/GR-008: Vergleich ohne Mengen, Chargen, MHD, EK – je Artikel nur Art, Differenz und Vorwochenpreis',
      all(set(x) <= {'art', 'd', 'alt'} for x in ae.values()) and not re.search(r'"(kg|menge|mhd|charge|lot|ek|einkauf|bestand)"', roh1, re.I)
      and all('vorwoche' not in x and 'variants' not in x for x in mit['offer']['items']))
st, a, _ = KA.call('offer&angebot=kunde-a&vergleich=vorwoche', raw=True)
aa = (a.get('vorwoche') or {}).get('aenderungen', {})
check('Kundenangebot A gegen sein eigenes Angebot der Vorwoche: D ▼ 1,00 gegen den A-Preis 20,00, X unverändert (bei A sichtbar), G wie im Wochenangebot',
      st == 200 and aa.get(ID['D']) == {'art': 'guenstiger', 'd': -1.0, 'alt': 20.0} and ID['X'] not in aa and aa.get(ID['G']) == RUNTER('G', -2.0), aa)
st, b = KB.call('offer&angebot=kunde-b&vergleich=vorwoche')
check('Kundenangebot B: D unverändert (B-Preis 30,00 in beiden Wochen) fehlt', st == 200 and ID['D'] not in b['vorwoche']['aenderungen'])
st, h = A.call('offer&angebot=kunde-h&vergleich=vorwoche')
ah = (h.get('vorwoche') or {}).get('aenderungen', {})
check('Kundenangebot mit eigener Liste H: G ▼ 1,00 gegen 10,00, N neu, Variante mit vorhandener Art.-Nr. neu, gleiche Bezeichnung ohne Art.-Nr. je Gruppe getrennt (OC1 ▼, OC2 unverändert), U unverändert',
      st == 200 and ah == {ID['G']: {'art': 'guenstiger', 'd': -1.0, 'alt': 10.0}, 'neu1': NEU, 'k44var1': NEU, 'k44oc1': {'art': 'guenstiger', 'd': -1.0, 'alt': 7.0}}, ah)
st, x, rx = KA.call('offer&angebot=kunde-b&vergleich=vorwoche', raw=True)
check('Kunde A fragt Angebot B an: 403, keine Vorwoche, keine B-Preise', st == 403 and 'vorwoche' not in x and '30' not in rx, (st, rx[:200]))
check('ohne Anmeldung Kundenangebot A mit Vergleich: 401', P.call('offer&angebot=kunde-a&vergleich=vorwoche')[0] == 401)
check('unbekannter Wert vergleich=alles: kein Vergleich', 'vorwoche' not in P.call('offer&vergleich=alles')[1])
st, pv = A.call('offer&draft=1&vergleich=vorwoche')
check('Vorschau (Entwurf, Mitarbeiter): Vergleich wie beim Veröffentlichen (KW 43)', st == 200 and pv.get('preview') and pv['vorwoche']['kw'] == 43
      and pv['vorwoche']['aenderungen'] == ae, (st, (pv.get('vorwoche') or {}).get('kw')))
check('Vorschau mit Vergleich ohne Anmeldung: 401/403', P.call('offer&draft=1&vergleich=vorwoche')[0] in (401, 403))

# ---------- Versand ----------
st, em = S.call('versand_empfaenger&art=woche')
check('Versand: Empfänger nennen die Vergleichswoche (KW 43)', st == 200 and em['woche'].get('vorwoche') == {'kw': 43, 'jahr': 2026}, em['woche'].get('vorwoche'))
st, v0 = S.call('versand_vorschau', {'art': 'woche', 'id': kid['alpha']})
st1, v1 = S.call('versand_vorschau', {'art': 'woche', 'id': kid['alpha'], 'preis': {'an': True, 'uebersicht': True, 'kurz': True}})
check('Vorschau ohne Schalter: wie bisher (keine Übersicht, Links ohne vergleich)', st == 200 and 'vergleich=' not in v0['html'] and 'Veränderung zur' not in v0['html'])
h = v1.get('html', '')
check('Vorschau mit Schalter: Übersicht „▼ 2 günstiger · ▲ 1 teurer · 1 neu“ (Kunde A: G, D günstiger), Links mit vergleich=vorwoche und „Nur Änderungen“',
      st1 == 200 and 'Veränderung zur KW 43' in h and '▼ 2 günstiger' in h and '▲ 1 teurer' in h and '1 neu' in h and 'vergleich=vorwoche' in h
      and 'vergleich=aenderungen' in h and 'Nur Änderungen ansehen' in h and '▼ 2,00' in h and '▼ 1,00' in h, re.sub(r'<[^>]+>', ' ', h)[:900])
st2, v2 = S.call('versand_vorschau', {'art': 'woche', 'id': kid['alpha'], 'preis': {'an': 'ja', 'uebersicht': 1}})
check('nur echte Wahrheitswerte: {an: "ja"} gilt als aus', st2 == 200 and 'vergleich=' not in v2['html'] and 'Veränderung zur' not in v2['html'])
st4, v4 = O.call('versand_vorschau', {'art': 'woche', 'id': kid['alpha'], 'preis': {'an': True, 'uebersicht': True, 'kurz': True}})
check('Versender ohne Zugang zum Angebot: Vorschau ohne Übersicht (keine Kundenpreise), mit Hinweis; Links mit Vergleich bleiben',
      st4 == 200 and 'Veränderung zur' not in v4['html'] and '2,00' not in v4['html'] and 'vergleich=vorwoche' in v4['html'] and 'Zugang zum Angebot' in v4.get('hinweis', ''), (st4, v4.get('hinweis')))
st3, v3 = S.call('versand_vorschau', {'art': 'woche', 'id': kid['alpha'], 'preis': {'an': True}})
check('Schalter ohne Unterpunkte: nur Links mit Vergleich', st3 == 200 and 'vergleich=vorwoche' in v3['html'] and 'Veränderung zur' not in v3['html'] and 'vergleich=aenderungen' not in v3['html'])
n0 = len(smtp.messages)
st, r = S.call('versand_senden', {'art': 'woche', 'ids': [kid['alpha']], 'week': 44, 'year': 2026, 'preis': {'an': True, 'uebersicht': True}})
st_b, r_b = S.call('versand_senden', {'art': 'woche', 'ids': [kid['beta']], 'week': 44, 'year': 2026})
until(lambda: len(smtp.messages) >= n0 + 2, 8)
mails = {mm['to'][0]: mm for mm in smtp.messages[n0:]}
ma, mb = mails.get('alpha@kunde.example', {}), mails.get('beta@kunde.example', {})
check('E-Mail mit Schalter: Übersicht (HTML und Text) und Link mit vergleich=vorwoche; ohne Schalter: wie bisher',
      st == 200 and st_b == 200 and 'Veränderung zur KW 43' in ma.get('html', '') and 'Veränderung zur KW 43' in ma.get('text', '') and 'vergleich=vorwoche' in ma.get('text', '')
      and 'vergleich=' not in mb.get('text', 'vergleich=') and 'Veränderung zur' not in mb.get('html', 'Veränderung zur'), (st, r, st_b, list(mails)))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll vermerkt „mit Preisänderung“ nur beim Versand mit Schalter', 'Wochenangebot KW 44/2026 mit Preisänderung an 1 Kunden versendet' in log
      and 'Wochenangebot KW 44/2026 an 1 Kunden versendet' in log)

# ---------- Oberfläche ----------
errors = []
INIT = "window.print = () => { window.__gedruckt = (window.__gedruckt || 0) + 1; window.dispatchEvent(new Event('beforeprint')); };"
ZEILEN = """() => [...document.querySelectorAll('#print-root .pl-page')].map((p) => [...p.querySelectorAll('tr.row')].map((r) => Math.round(r.getBoundingClientRect().height * 10)))"""
SATZ = """() => { const D = document.querySelector('#print-root .pl-doc'), seiten = [...D.querySelectorAll('.pl-page')];
  const vw = [...D.querySelectorAll('td.c-name > .vw')].map((v) => { const td = v.closest('td'), a = v.getBoundingClientRect(), b = td.getBoundingClientRect();
    return { innen: a.left >= b.left - 0.5 && a.right <= b.right + 0.5 && a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5,
             anteil: parseFloat(getComputedStyle(v).fontSize) / parseFloat(getComputedStyle(td).fontSize), text: v.querySelector('[aria-hidden]').textContent, flaeche: getComputedStyle(v).backgroundImage }; });
  return { seiten: seiten.length, stufe: D.dataset.stufe, fuell: seiten.map((p) => +p.dataset.fuell), zeilen: D.querySelectorAll('.al-band tr.row').length, vw,
           kopf: (D.querySelector('.pl-ph') || {}).innerText || '' }; }"""


def satz(pg):
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pg.wait_for_selector('#print-root .pl-doc .pl-page', state='attached')
    pg.wait_for_function("[...document.querySelectorAll('#print-root img')].every((i) => i.complete)")
    pg.emulate_media(media='print')
    s = pg.evaluate(SATZ)
    s['hoehen'] = pg.evaluate(ZEILEN)
    return s


def zurueck(pg):
    pg.emulate_media(media='null')
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")


def laden(pg, pfad):
    pg.goto(BASE + pfad); pg.wait_for_selector('#list tr.row, #list .card'); pg.evaluate('document.fonts.ready')


ZEILE = """(id) => { const r = document.querySelector(`#list tr.row[data-id="${id}"]`); const v = r && r.querySelector('.vw'); return v ? v.className.replace('vw ', '') + '|' + v.querySelector('[aria-hidden]').textContent : ''; }"""
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, color_scheme='light')
    ctx.add_init_script(INIT)
    pg = ctx.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    laden(pg, '/')
    check('Angebotsseite ohne Parameter: keine Hinweise, keine Legende (wie bisher)', pg.locator('.vw').count() == 0 and pg.locator('.vw-leg').count() == 0)
    s0 = satz(pg); zurueck(pg)
    laden(pg, '/?vergleich=vorwoche')
    z = {k: pg.evaluate(ZEILE, v) for k, v in ID.items()}
    check('Angebotsansicht mit vergleich=vorwoche: G „▼ 2,00“, T „▲ 1,00“, N und X „neu“, U und D (Wochenangebot unverändert) ohne Hinweis',
          z['G'] == 'vw-guenstiger|▼ 2,00' and z['T'] == 'vw-teurer|▲ 1,00' and z['N'] == 'vw-neu|neu' and z['X'] == 'vw-neu|neu' and z['U'] == '' and z['D'] == '', z)
    leg = pg.locator('#list .al-head .vw-leg').inner_text()
    check('… Legende im Kopf „Veränderung zur KW 43: ▼ günstiger ▲ teurer neu“', 'Veränderung zur KW 43' in leg and '▼ günstiger' in leg and '▲ teurer' in leg and 'neu' in leg, leg)
    shot(pg, SH + '/preisaenderung-1280.png')
    s1 = satz(pg)
    shot(pg.locator('#print-root .pl-page').first, SH + '/preisaenderung-druck-s1.png')
    check('Druck mit Vergleich: dieselben Seiten, dieselbe Stufe und Füllung, dieselben Zeilenhöhen je Seite wie ohne (Aufbau unverändert)',
          s1['seiten'] == s0['seiten'] and s1['stufe'] == s0['stufe'] and s1['fuell'] == s0['fuell'] and s1['hoehen'] == s0['hoehen'] and s1['zeilen'] == s0['zeilen'],
          (s0['seiten'], s1['seiten'], s0['stufe'], s1['stufe'], s0['fuell'], s1['fuell']))
    vws = s1['vw']
    check('Druck: Hinweise an G, T, N, X, kleiner als die Zeilenschrift (etwa 75 %), ganz in der Zelle',
          len(vws) == 4 and all(v['innen'] and 0.7 <= v['anteil'] <= 0.8 for v in vws) and sorted(v['text'] for v in vws) == sorted(['▼ 2,00', '▲ 1,00', 'neu', 'neu']), vws)
    check('Druck: Legende im Kopf neben „Seite 1 von …“', 'Veränderung zur KW 43' in s1['kopf'] and 'Seite 1 von' in s1['kopf'], s1['kopf'])
    zurueck(pg)
    laden(pg, '/?vergleich=aenderungen')
    ids = pg.evaluate("() => [...document.querySelectorAll('#list .al-band tr.row')].map((r) => r.dataset.id)")
    check('Kurzfassung „Nur Änderungen“: nur G, T, N und X (geändert oder neu)', sorted(ids) == sorted([ID['G'], ID['T'], 'neu1', ID['X']]) and 'Nur Änderungen zur KW 43' in pg.locator('.vw-leg').first.inner_text(), ids)
    s2 = satz(pg)
    check('… Druck der Kurzfassung: eine Seite mit den vier Artikeln', s2['seiten'] == 1 and s2['zeilen'] == 4, (s2['seiten'], s2['zeilen']))
    shot(pg.locator('#print-root .pl-page').first, SH + '/preisaenderung-druck-aenderungen.png')
    zurueck(pg)
    # Handy: Karten mit Pille unter dem Preis
    m390 = br.new_context(viewport={'width': 390, 'height': 844}, color_scheme='light', is_mobile=True, has_touch=True)
    h = m390.new_page(); h.on('pageerror', lambda ex: errors.append(str(ex)))
    h.goto(BASE + '/?vergleich=vorwoche#ansicht=karten'); h.wait_for_selector('#list .card')
    pille = h.evaluate(f"""() => {{ const c = document.querySelector('#list .card[data-id="{ID['G']}"] .price .vw'); return c ? [c.textContent, c.className] : null; }}""")
    check('390 px, Karten: Pille „▼ 2,00“ (günstiger) unter dem Preis, Legende über der Liste', pille and '▼ 2,00' in pille[0] and 'vw-pille' in pille[1] and 'vw-guenstiger' in pille[1]
          and h.locator('.vw-leiste').count() == 1 and h.evaluate('document.documentElement.scrollWidth <= 390'), pille)
    h.evaluate(f"document.querySelector('#list .card[data-id=\"{ID['G']}\"]').scrollIntoView()")
    shot(h, SH + '/preisaenderung-390-karten.png')
    h.goto(BASE + '/?vergleich=vorwoche'); h.wait_for_selector('#list tr.row')
    check('390 px, Angebotsansicht: Hinweis rechts, Bezeichnung einzeilig abgeschnitten, keine waagerechte Rollleiste',
          h.evaluate(f"""() => {{ const r = document.querySelector('#list tr.row[data-id="{ID['G']}"]'), b = r.querySelector('.name-btn'), v = r.querySelector('.vw');
            return getComputedStyle(b).whiteSpace === 'nowrap' && v.getBoundingClientRect().right <= r.querySelector('td.c-name').getBoundingClientRect().right + 1 && document.documentElement.scrollWidth <= 390; }}"""))
    h.evaluate(f"document.querySelector('#list tr.row[data-id=\"{ID['G']}\"]').scrollIntoView({{block: 'center'}})")
    shot(h, SH + '/preisaenderung-390-liste.png')
    m390.close()

    # ---------- Angebot bearbeiten: Drucken und Menü „Zusatz“ ----------
    a = ctx.new_page(); a.on('pageerror', lambda ex: errors.append(str(ex)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')

    def drucke(ausloesen):
        a.evaluate("document.querySelectorAll('#druck-frame').forEach((f) => { f.dataset.alt = '1'; })")
        ausloesen()
        fr = a.wait_for_selector('#druck-frame:not([data-alt])', state='attached').content_frame()
        fr.wait_for_function('window.__gedruckt >= 1', timeout=20000)
        return fr

    fr = drucke(lambda: a.click('#btn-drucken'))
    check('„Drucken“ druckt wie bisher ohne Preisänderung', 'vergleich' not in fr.url and fr.evaluate("document.querySelectorAll('#print-root .vw').length") == 0, fr.url)
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    a.click('#btn-more'); a.wait_for_selector('#menu-more:not([hidden])')
    a.click('#btn-drucken-zusatz')
    check('Pfeil „Zusatz“ schließt das offene Menü „⋯“', a.evaluate("document.querySelector('#menu-more').hidden"))
    menue = a.evaluate("() => ({ offen: !document.querySelector('#menu-drucken').hidden, punkte: [...document.querySelectorAll('#menu-drucken [data-druck]')].map((b) => b.textContent.trim()), expanded: document.querySelector('#btn-drucken-zusatz').getAttribute('aria-expanded') })")
    check('Pfeil neben „Drucken“ öffnet das Menü „Zusatz“ mit „Mit Preisänderung drucken“ und „Nur Änderungen drucken“',
          menue['offen'] and menue['punkte'] == ['Mit Preisänderung drucken', 'Nur Änderungen drucken'] and menue['expanded'] == 'true', menue)
    shot(a, SH + '/preisaenderung-drucken-menue.png')
    fr = drucke(lambda: a.click('#menu-drucken [data-druck="vorwoche"]'))
    n = fr.evaluate("document.querySelectorAll('#print-root td.c-name > .vw').length")
    check('„Mit Preisänderung drucken“: Entwurf mit vergleich=vorwoche, Hinweise in der Druckfassung, Menü wieder zu',
          'vergleich=vorwoche' in fr.url and 'vorschau' in fr.url and n == 4 and a.evaluate("document.querySelector('#menu-drucken').hidden"), (fr.url, n))
    a.wait_for_function("!document.querySelector('#btn-drucken').disabled")
    a.click('#btn-drucken-zusatz')
    fr = drucke(lambda: a.click('#menu-drucken [data-druck="aenderungen"]'))
    check('„Nur Änderungen drucken“: nur die vier geänderten/neuen Artikel', 'vergleich=aenderungen' in fr.url and fr.evaluate("document.querySelectorAll('#print-root .al-band tr.row').length") == 4, fr.url)

    # ---------- Versand: Fenster „Wochenangebot senden“ mit Zusatz ----------
    vs = ctx.new_page(); vs.on('pageerror', lambda ex: errors.append(str(ex)))
    vs.goto(BASE + '/module/versand/'); vs.wait_for_selector('#vs-send')
    vs.click('#vs-send'); vs.wait_for_selector('#dlg-send[open] #send-preis')
    aus = vs.evaluate("() => ({ an: document.querySelector('#send-preis').checked, unter: !!document.querySelector('#send-preis-uebersicht'), text: document.querySelector('.vs-zusatz').innerText })")
    check('Versandfenster: Zusatz „Preisänderung zur Vorwoche zeigen“ beim Öffnen aus, nennt KW 43', not aus['an'] and not aus['unter'] and 'KW 43' in aus['text'], aus)
    vs.check('#send-preis')
    vs.wait_for_selector('#send-preis-uebersicht')
    ein = vs.evaluate("() => ({ u: document.querySelector('#send-preis-uebersicht').checked, k: document.querySelector('#send-preis-kurz').checked })")
    check('… eingeschaltet: Übersicht vorgewählt, Kurzfassung aus', ein == {'u': True, 'k': False}, ein)
    with vs.expect_response(lambda r: 'versand_vorschau' in r.url) as rv:
        vs.click('#send-prev')
    body = json.loads(rv.value.request.post_data or '{}')
    vs.wait_for_selector('#send-vorschau:not([hidden])')
    check('… Vorschau schickt preis = {an, uebersicht, kurz} und zeigt die Übersicht', body.get('preis') == {'an': True, 'uebersicht': True, 'kurz': False}
          and 'Veränderung zur KW 43' in vs.frame_locator('#send-frame').locator('body').inner_text(), body.get('preis'))
    shot(vs.locator('#dlg-send'), SH + '/preisaenderung-versand.png')
    vs.keyboard.press('Escape')
    vs.click('#vs-send'); vs.wait_for_selector('#dlg-send[open] #send-preis')
    check('… erneut geöffnet: wieder aus (nicht gemerkt)', not vs.is_checked('#send-preis'))
    br.close()

# ---------- später angelegtes Angebot: kein Vergleich (nie die Preise des Wochenangebots) ----------
cur = A.call('offers')[1]
assert A.call('offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': 'kunde-spaet', 'name': 'Angebot später', 'fallback': 'standard'}]})[0] == 200
st, sp = A.call('offer&angebot=kunde-spaet&vergleich=vorwoche')
check('Angebot nach dem Veröffentlichen angelegt: kein Vergleich (null), Angebot selbst da', st == 200 and sp.get('vorwoche', 'fehlt') is None and sp['offer']['items'], (st, sp.get('vorwoche', 'fehlt')))

# ---------- Veröffentlichen scheitert nicht an einer kaputten Vorwoche ----------
storage_write('angebot-woche/2026-44', {'format': 1, 'woche': '2026-44', 'stand': '9999-12-31T00:00:00Z', 'quelle': 'veroeffentlichung', 'angebote': None,
                                         'modell': {'meta': {'week': 44, 'year': 2026}, 'groups': [], 'items': ['kaputt']}})
m3 = deepcopy(A.call('draft')[1].get('published'))
m3['meta']['week'] = 45
d = A.call('draft')[1]
st, r = A.call('publish', {'model': m3, 'revision': d['revision']})
check('KW 45 mit kaputter Vorwoche: veröffentlicht (200), ohne Vergleich', st == 200 and P.call('offer&vergleich=vorwoche')[1].get('vorwoche', 'fehlt') is None, (st, r))
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(); pg.on('pageerror', lambda ex: errors.append(str(ex)))
    pg.goto(BASE + '/?vergleich=aenderungen'); pg.wait_for_selector('#list .empty')
    txt = pg.locator('#list').inner_text()
    check('„Nur Änderungen“ ohne Vorwoche: Hinweis statt des ganzen Angebots', 'keinen Vergleich mit der Vorwoche' in txt and pg.locator('#list tr.row, #list .card').count() == 0, txt[:200])
    br.close()

# ---------- Jahreswechsel: KW 1/2027 vergleicht mit KW 53/2026 ----------
for wo, ja in ((53, 2026), (1, 2027)):
    m4 = deepcopy(A.call('draft')[1].get('published'))
    m4['meta']['week'], m4['meta']['year'] = wo, ja
    st, r = A.call('publish', {'model': m4, 'revision': A.call('draft')[1]['revision']})
    assert st == 200, r
vj = P.call('offer&vergleich=vorwoche')[1].get('vorwoche') or {}
check('Jahreswechsel: KW 1/2027 vergleicht mit KW 53/2026 (ISO-Wochen), keine Änderungen', vj.get('kw') == 53 and vj.get('jahr') == 2026 and vj.get('aenderungen') == {}, vj)

check('keine JavaScript-Fehler', not errors, errors[:3])
smtp.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
