"""Jedes Angebot für sich (Inhaber 19.11.2026, Schritt 1): Bearbeitungen im Angebotseditor wirken nur auf das gewählte
Angebot – Preise, Bezeichnung und Angebotsgruppen (Name, Bereich, Reihenfolge, Zuordnung der Artikel). Kundenangebote „Bela“
und „Edeka“ mit eigener Artikelliste, ihre Artikel auch im Wochenangebot. Bela → Wochenangebot: Artikelfenster ohne
Wochenpreis, Gruppenauswahl nur mit Gruppen von Bela, Gruppe und Bezeichnung im Artikelfenster, Preis in der Zeile, Gruppe
umbenennen (Trennen und Umbenennen in einem Rückgängig-Schritt), Bereich, zweite Änderung an derselben Gruppenkarte,
Reihenfolge der Gruppen und Artikel in eine andere Gruppe im Fenster „Editor“, „Artikel hinzufügen“ ohne doppelte
Überschrift. Wochenangebot → Edeka: Gruppe umbenennen, Bereich, Artikel in eine andere Gruppe, Bezeichnung in der Zeile,
Reihenfolge der Gruppen (↓). Geprüft wird die aufgelöste Sicht der Angebote über die Schnittstelle (offer&draft=1).
Schritt 2: Reihenfolge je Angebot (items[].stellen, auch beim Ordnen nach Angebotskategorien), Zusatzpreise je Angebot,
Duplizieren, Zurücknehmen je Angebot, Empfehlung; ohne Browser die Prüfung der neuen Felder auf dem Server, Preisimport und
„Angebot kopieren“. Bildschirmfotos Artikelfenster in Bela 1280/390 px. Nur Testdaten."""
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, shot, until
from versand_hilfe import veroeffentlichen

PW = 'Sicheres-Passwort-1'
BE, ED = 'bela', 'edeka'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.41')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200


def entwurf():
    d = A.call('draft')[1]
    return d['draft'] or d['published'], d['revision']


def sicht(oid, entwurf=True):
    """Aufgelöstes Angebot (Entwurf bzw. veröffentlicht): Gruppen (Name, Bereich) in Reihenfolge, je Artikel Gruppe, Bezeichnung,
    Preis, Zusatzpreise, Empfehlung; „reihe“ = Artikel-IDs in der Reihenfolge der Kundenseite (Gruppe, dann Stelle – wie
    OfferCore.enrichOffer)"""
    o = A.call('offer' + ('&draft=1' if entwurf else '') + ('' if oid == 'std' else f'&angebot={oid}'))[1]['offer']
    gn = {g['id']: g for g in o['groups']}
    gi = {g['id']: k for k, g in enumerate(o['groups'])}
    return {'gruppen': [(g['name'], g.get('section') or '') for g in o['groups']],
            'artikel': {i['id']: (gn[i['groupId']]['name'], i['name'], i['price'], i.get('altPrices') or [], bool(i.get('sale') or i.get('empfehlung'))) for i in o['items']},
            'reihe': [i['id'] for _, i in sorted(enumerate(o['items']), key=lambda x: (gi.get(x[1]['groupId'], 10 ** 9), x[0]))]}


def gname(oid, iid):
    return sicht(oid)['artikel'][iid][0]


# ---------- Testdaten: Bela und Edeka mit eigener Artikelliste, alle Artikel auch im Wochenangebot ----------
# Bela: x, y (Gruppe G1), z (G2) – Bearbeitungen in Bela. Edeka: w (G3), h1, h2 (H1, H2: im Wochenangebot benachbart) –
# Bearbeitungen im Wochenangebot; so trennt jede Richtung Gruppen, die beide Seiten noch gemeinsam nutzen.
of = A.call('offers')[1]
assert A.call('offers_save', {'rev': of['rev'], 'offers': [{**o, 'fallback': 'hidden'} if o['id'] in (BE, ED) else o for o in of['offers']]})[0] == 200
m, rev = entwurf()
frei = [i for i in m['items'] if i.get('code') and not i.get('variants') and not i.get('namen') and not i.get('gruppen') and not i.get('sale')]
nfrei = {}
for i in frei:
    nfrei[i['groupId']] = nfrei.get(i['groupId'], 0) + 1
sichtbar = [g['id'] for g in m['groups'] if any(i['groupId'] == g['id'] for i in m['items'])]
H1, H2 = next((a, b) for a, b in zip(sichtbar, sichtbar[1:]) if nfrei.get(a) and nfrei.get(b))
G1, G2, G3, G4 = [g for g in sichtbar if nfrei.get(g, 0) >= 2 and g not in (H1, H2)][:4]
GN = {g['id']: g['name'] for g in m['groups']}
x, y = [i for i in frei if i['groupId'] == G1][:2]
z = next(i for i in frei if i['groupId'] == G2)
w = next(i for i in frei if i['groupId'] == G3)
h1, h2 = (next(i for i in frei if i['groupId'] == h) for h in (H1, H2))
for i, o, p in ((x, BE, 11.5), (y, BE, 12.5), (z, BE, 13.5), (w, ED, 14.5), (h1, ED, 15.5), (h2, ED, 16.5)):
    i['variants'] = {o: {'status': 'value', 'value': p}}
# t: Gruppe G4, gemeinsam im Wochenangebot, in Bela und in Edeka (drei Familien an einer Gruppe)
t = next(i for i in frei if i['groupId'] == G4)
t['variants'] = {BE: {'status': 'value', 'value': 17.5}, ED: {'status': 'value', 'value': 18.5}}
# Schritt 2: r1–r3 (Gruppe G5) im Wochenangebot, in Bela und in Edeka – Reihenfolge je Angebot; q, s, s2, d (andere Gruppen)
# im Wochenangebot und in Bela – Zurücknehmen, Empfehlung, Duplizieren. s und s2 mit Empfehlung (gilt in beiden).
G5 = next(g for g in sichtbar if nfrei.get(g, 0) >= 3 and g not in (G1, G2, G3, G4, H1, H2))
r1, r2, r3 = [i for i in frei if i['groupId'] == G5][:3]
for i, pr in ((r1, 21.5), (r2, 22.5), (r3, 23.5)):
    i['variants'] = {BE: {'status': 'value', 'value': pr}, ED: {'status': 'value', 'value': pr + 1}}
q, s, s2, d = [i for i in frei if i['groupId'] not in (G1, G2, G3, G4, G5, H1, H2)][:4]
for i, pr in ((q, 31.5), (s, 32.5), (s2, 33.5), (d, 34.5)):
    i['variants'] = {BE: {'status': 'value', 'value': pr}}
s['sale'] = {'value': 5.5}
s2['sale'] = {'value': 6.5}
R = [r1['id'], r2['id'], r3['id']]
assert A.call('save_draft', {'model': m, 'revision': rev})[0] == 200
m, rev = entwurf()
assert A.call('publish', {'model': m, 'revision': rev})[0] == 200   # veröffentlicht ohne Stellen (wie vor Schritt 2)
BE0, ED0 = sicht(BE), sicht(ED)
assert all(BE0['artikel'][i['id']][0] == GN[i['groupId']] for i in (x, y, z)) and [g for g, _ in ED0['gruppen']].index(GN[H1]) + 1 == [g for g, _ in ED0['gruppen']].index(GN[H2]), ED0['gruppen']

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1280, 'height': 900})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    ruhig = lambda: a.wait_for_function("!/pending|saving/.test(document.querySelector('#save-state').className)")

    def angebot(oid, iid):
        a.locator(f'#offer-bar [data-offer="{oid}"]').first.click()
        a.wait_for_selector(f'#offer-bar [data-offer="{oid}"][aria-selected="true"]'); a.wait_for_selector(f'#groups tr[data-id="{iid}"]')

    def fenster(iid):
        a.click(f'#groups tr[data-id="{iid}"] [data-act=item]'); a.wait_for_selector('#dlg-item[open] #item-body [name=code]')

    def zu():
        a.click('#item-body [type=submit]'); a.wait_for_selector('#dlg-item', state='hidden')

    def karte(gid, feld, wert):
        el = a.locator(f'#groups section.gcard[data-gid="{gid}"] [data-gf={feld}]')
        el.fill(wert); el.evaluate('e => e.blur()')

    def karte_von(iid):
        return a.evaluate(f"document.querySelector('#groups tr[data-id=\"{iid}\"]').closest('section.gcard').dataset.gid")

    # ---------- Bela → Wochenangebot ----------
    S0 = sicht('std')
    angebot(BE, x['id'])
    fenster(x['id'])
    txt = a.text_content('#item-body')
    check('Bela, Artikelfenster: kein Feld für den Wochenpreis, Bezeichnung des Preises und Zusatzpreise des Wochenangebots; Hinweis auf den Preis in der Zeile',
          a.locator('#item-body [name=price], #item-body [name=priceLabel]').count() == 0 and 'Zusatzpreise im Wochenangebot' not in txt
          and 'Preis Wochenangebot' not in txt and 'steht in der Zeile' in txt, txt[:300])
    opts = a.eval_on_selector('#item-body [name=groupId]', 'e => [...e.options].map(o => o.textContent)')
    bela_g = sorted({v[0] for v in sicht(BE)['artikel'].values()})
    check('Bela, Artikelfenster: Gruppenauswahl nur mit Gruppen von Bela (und „Neue Gruppe“), gewählt ist die Gruppe in Bela',
          sorted(opts[:-1]) == bela_g and 'Neue Gruppe' in opts[-1] and a.input_value('#item-body [name=groupId]') == G1, (opts, bela_g))
    a.wait_for_function("document.querySelector('#dlg-item').getAnimations().every(x => x.playState !== 'running')")
    shot(a.locator('#dlg-item'), SH + '/angebote-getrennt-fenster-1280.png')
    a.select_option('#item-body [name=groupId]', G2)
    until(lambda: gname(BE, x['id']) == GN[G2]); ruhig()
    check('Bela: Artikel im Artikelfenster in eine andere Gruppe – Wochenangebot unverändert', gname(BE, x['id']) == GN[G2] and sicht('std') == S0,
          gname('std', x['id']))
    a.fill('#item-body [name=name]', 'Bela Spezial'); a.locator('#item-body [name=name]').evaluate('e => e.blur()')
    until(lambda: sicht(BE)['artikel'][x['id']][1] == 'Bela Spezial'); ruhig()
    check('Bela: Bezeichnung im Artikelfenster – nur in Bela, Wochenangebot unverändert', sicht(BE)['artikel'][x['id']][1] == 'Bela Spezial' and sicht('std') == S0,
          sicht('std')['artikel'][x['id']][1])
    zu()
    vp = a.locator(f'#groups tr[data-id="{y["id"]}"] [data-f=vprice]')
    vp.fill('9,90'); vp.evaluate('e => e.blur()')
    until(lambda: sicht(BE)['artikel'][y['id']][2].get('value') == 9.9); ruhig()
    check('Bela: Preis in der Zeile – nur in Bela, Wochenpreis unverändert', sicht(BE)['artikel'][y['id']][2] == {'status': 'value', 'value': 9.9} and sicht('std') == S0)
    # Jedes Angebot mit eigener Artikelliste hat für jeden seiner Artikel eine Stelle – ergänzt ohne sichtbare Änderung
    me = entwurf()[0]['items']
    ohne = [(o, i['id']) for i in me for o in (BE, ED) if o in (i.get('variants') or {}) and not isinstance((i.get('stellen') or {}).get(o), int)]
    ae = A.call('versand_aenderungen')[1]
    check('Stellen ergänzt: jeder Artikel von Bela und Edeka hat eine Stelle, ohne „Aufbau geändert“ (Versand-Liste) und ohne Bearbeitung in Edeka',
          not ohne and 'aufbau' not in ae['arten'] and sicht(ED) == ED0, (ohne[:3], ae['arten']))

    # Gruppe umbenennen (G1 noch gemeinsam mit dem Wochenangebot): Bela bekommt eine eigene Gruppe, Rückgängig in einem Schritt
    n_gr = len(entwurf()[0]['groups'])
    gk = karte_von(y['id'])
    karte(gk, 'name', 'Bela Rind')
    until(lambda: gname(BE, y['id']) == 'Bela Rind'); ruhig()
    check('Bela: Gruppe umbenannt – nur in Bela, Wochenangebot behält den Namen', gname(BE, y['id']) == 'Bela Rind' and sicht('std') == S0, sicht('std')['gruppen'][:4])
    a.click('#btn-undo')
    until(lambda: gname(BE, y['id']) == GN[G1]); ruhig()
    check('Rückgängig: Umbenennen und Trennen der Gruppe in einem Schritt zurück', gname(BE, y['id']) == GN[G1] and len(entwurf()[0]['groups']) == n_gr
          and sicht('std') == S0, len(entwurf()[0]['groups']) - n_gr)
    gk = karte_von(y['id'])
    karte(gk, 'name', 'Bela Rind')
    until(lambda: gname(BE, y['id']) == 'Bela Rind'); ruhig()
    karte(karte_von(y['id']), 'section', 'Bela-Bereich')
    until(lambda: ('Bela Rind', 'Bela-Bereich') in sicht(BE)['gruppen']); ruhig()
    check('Bela: Bereich der Gruppe geändert – Wochenangebot unverändert', ('Bela Rind', 'Bela-Bereich') in sicht(BE)['gruppen'] and sicht('std') == S0)
    karte(karte_von(y['id']), 'name', 'Bela Rind 2')
    until(lambda: gname(BE, y['id']) == 'Bela Rind 2'); ruhig()
    check('… zweite Änderung an derselben Gruppenkarte trifft weiter die Gruppe von Bela', sicht('std') == S0)

    # Fenster „Editor“ (Aufbau): Reihenfolge der Gruppen und Artikel in eine andere Gruppe
    vor = [g for g, _ in sicht(BE)['gruppen']]
    a.click('#btn-aufbau'); a.wait_for_selector('#dlg-aufbau[open] #abf-liste')
    a.locator('#abf-liste [data-ab="g-runter"]:not([disabled]), #abf-liste [data-ab="b-runter"]:not([disabled])').first.click()
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    until(lambda: [g for g, _ in sicht(BE)['gruppen']] != vor); ruhig()
    check('Bela, Editor: Reihenfolge der Gruppen geändert – Wochenangebot behält seine Reihenfolge', [g for g, _ in sicht(BE)['gruppen']] != vor and sicht('std') == S0,
          ([g for g, _ in sicht(BE)['gruppen']], vor))
    gy, gz = karte_von(y['id']), karte_von(z['id'])
    a.click('#btn-aufbau'); a.wait_for_selector('#dlg-aufbau[open] #abf-liste')
    a.click(f'#abf-liste .abf-g[data-gid="{gy}"] [data-ab="g-auf"]')
    a.select_option(f'#abf-liste .abf-a[data-aid="{y["id"]}"] select', gz)
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    until(lambda: gname(BE, y['id']) == gname(BE, z['id'])); ruhig()
    check('Bela, Editor: Artikel in eine andere Gruppe – Wochenangebot unverändert', gname(BE, y['id']) == gname(BE, z['id']) and sicht('std') == S0,
          (gname('std', y['id']), S0['artikel'][y['id']][0]))

    # „Artikel hinzufügen“ in Bela: ein Artikel des Wochenangebots kommt in Belas eigene Gruppe gleichen Namens (keine doppelte Überschrift)
    v2 = [i for i in frei if i['groupId'] == G2][1]
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    a.fill('#ezp-q', v2['code']); a.wait_for_selector(f'#ezp-list tr[data-code="{v2["code"]}"]'); a.click(f'#ezp-list tr[data-code="{v2["code"]}"] .ezp-n')
    a.fill(f'#ezp-list [data-preis="{v2["code"]}"]', '7,70')
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    until(lambda: v2['id'] in sicht(BE)['artikel']); ruhig()
    namen = [g for g, _ in sicht(BE)['gruppen']]
    check('Bela: hinzugefügter Artikel steht in Belas Gruppe gleichen Namens – keine Überschrift doppelt, Wochenangebot unverändert',
          gname(BE, v2['id']) == GN[G2] and len(namen) == len(set(namen)) and sicht('std') == S0, namen)

    check('… Edeka bleibt bei allen Bearbeitungen in Bela unverändert', sicht(ED) == ED0)

    # ---------- Wochenangebot → Edeka (Edeka benutzt G3, H1, H2 noch gemeinsam mit dem Wochenangebot) ----------
    angebot('std', w['id'])
    karte(G3, 'name', 'Std G3 neu')
    until(lambda: gname('std', w['id']) == 'Std G3 neu'); ruhig()
    check('Wochenangebot: Gruppe umbenannt – in Edeka heißt sie wie bisher', gname('std', w['id']) == 'Std G3 neu' and gname(ED, w['id']) == GN[G3],
          (gname('std', w['id']), gname(ED, w['id'])))
    karte(G3, 'section', 'Std-Bereich')
    until(lambda: ('Std G3 neu', 'Std-Bereich') in sicht('std')['gruppen']); ruhig()
    check('Wochenangebot: Bereich der Gruppe geändert – in Edeka unverändert', not any(b == 'Std-Bereich' for _, b in sicht(ED)['gruppen']), sicht(ED)['gruppen'])
    fenster(w['id'])
    a.select_option('#item-body [name=groupId]', G4)
    until(lambda: gname('std', w['id']) == GN[G4]); ruhig()
    check('Wochenangebot: Artikel im Artikelfenster in eine andere Gruppe – in Edeka bleibt er in seiner Gruppe', gname(ED, w['id']) == GN[G3], gname(ED, w['id']))
    zu()
    nm = a.locator(f'#groups tr[data-id="{w["id"]}"] [data-f=name]')
    nm.fill('Std Bezeichnung w'); nm.evaluate('e => e.blur()')
    until(lambda: sicht('std')['artikel'][w['id']][1] == 'Std Bezeichnung w'); ruhig()
    check('Wochenangebot: Bezeichnung in der Zeile geändert – Edeka behält die bisherige', sicht(ED)['artikel'][w['id']][1] == w['name'], sicht(ED)['artikel'][w['id']])
    # Reihenfolge der Gruppen (↓ an der Gruppenkarte H1, im Wochenangebot direkt vor H2)
    vor_std = [g for g, _ in sicht('std')['gruppen']]
    a.click(f'#groups section.gcard[data-gid="{H1}"] [data-act="g-down"]')
    until(lambda: [g for g, _ in sicht('std')['gruppen']] != vor_std); ruhig()
    std_g, ed_g = [g for g, _ in sicht('std')['gruppen']], [g for g, _ in sicht(ED)['gruppen']]
    check('Wochenangebot: Reihenfolge der Gruppen geändert – Edeka behält seine Reihenfolge', std_g.index(GN[H2]) < std_g.index(GN[H1])
          and ed_g.index(GN[H1]) < ed_g.index(GN[H2]), (std_g, ed_g))
    check('… Gruppe, Bezeichnung und Preis aller Artikel von Edeka unverändert', {k: v[2] for k, v in sicht(ED)['artikel'].items()} == {k: v[2] for k, v in ED0['artikel'].items()}
          and {k: v[:2] for k, v in sicht(ED)['artikel'].items()} == {k: v[:2] for k, v in ED0['artikel'].items()})
    # Drei Angebote an einer Gruppe: Umbenennen in Bela trennt nur Bela ab – Edeka bleibt auch im Entwurf unberührt
    angebot(BE, t['id'])
    karte(karte_von(t['id']), 'name', 'Bela G4')
    until(lambda: gname(BE, t['id']) == 'Bela G4'); ruhig()
    ti = next(i for i in entwurf()[0]['items'] if i['id'] == t['id'])
    check('Gruppe in Bela umbenannt, die auch Edeka nutzt: nur Bela bekommt eine Kopie, Edeka im Entwurf unverändert (kein eigener Eintrag)',
          gname(ED, t['id']) == GN[G4] and gname('std', t['id']) == GN[G4] and ED not in (ti.get('gruppen') or {}), ti.get('gruppen'))
    # Angebot, das dem Wochenangebot folgt, übernimmt eine Umbenennung im Wochenangebot (bis Schritt 2); Edeka behält den Namen
    FOLGT = next(o['id'] for o in A.call('offers')[1]['offers'] if o.get('fallback') == 'standard')
    angebot('std', t['id'])
    karte(karte_von(t['id']), 'name', 'Std G4')
    until(lambda: gname('std', t['id']) == 'Std G4'); ruhig()
    check('Wochenangebot: Gruppe umbenannt – folgendes Angebot übernimmt den Namen, Edeka und Bela behalten ihren',
          gname(FOLGT, t['id']) == 'Std G4' and gname(ED, t['id']) == GN[G4] and gname(BE, t['id']) == 'Bela G4', (gname(FOLGT, t['id']), gname(ED, t['id'])))
    # Im folgenden Angebot ändert eine Gruppenkarte das Wochenangebot nicht (Hinweis statt Änderung)
    angebot(FOLGT, t['id'])
    karte(karte_von(t['id']), 'name', 'Folgt G4')
    a.wait_for_selector('#toast.show:has-text("folgt dem Wochenangebot")')
    check('Folgendes Angebot: Gruppe umbenennen ändert das Wochenangebot nicht (Hinweis)', gname('std', t['id']) == 'Std G4' and gname(FOLGT, t['id']) == 'Std G4'
          and a.input_value(f'#groups section.gcard[data-gid="{karte_von(t["id"])}"] [data-gf=name]') == 'Std G4', gname('std', t['id']))

    # ---------- Schritt 2: Reihenfolge der Artikel je Angebot ----------
    def reihe(oid, ids, entwurf=True):
        return [i for i in sicht(oid, entwurf)['reihe'] if i in ids]

    check('Ausgang: r1–r3 in allen drei Angeboten in derselben Reihenfolge', reihe('std', R) == R and reihe(BE, R) == R and reihe(ED, R) == R, (reihe('std', R), reihe(BE, R)))
    angebot(BE, r2['id']); fenster(r2['id'])
    a.click('#item-body [data-ia=up]')
    until(lambda: reihe(BE, R) == [R[1], R[0], R[2]]); ruhig()
    check('Bela: Artikel im Artikelfenster nach oben – nur in Bela, Wochenangebot und Edeka behalten ihre Reihenfolge',
          reihe(BE, R) == [R[1], R[0], R[2]] and reihe('std', R) == R and reihe(ED, R) == R, (reihe(BE, R), reihe('std', R), reihe(ED, R)))
    zu()
    a.click('#btn-aufbau'); a.wait_for_selector('#dlg-aufbau[open] #abf-liste')
    g5 = karte_von(r3['id'])
    a.click(f'#abf-liste .abf-g[data-gid="{g5}"] [data-ab="g-auf"]')
    a.click(f'#abf-liste .abf-a[data-aid="{r3["id"]}"] [data-ab="a-hoch"]')
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    until(lambda: reihe(BE, R) == [R[1], R[2], R[0]]); ruhig()
    check('Bela, Editor: Artikel nach oben – Wochenangebot und Edeka unverändert', reihe(BE, R) == [R[1], R[2], R[0]] and reihe('std', R) == R and reihe(ED, R) == R,
          (reihe(BE, R), reihe('std', R)))
    angebot('std', r3['id']); fenster(r3['id'])
    a.click('#item-body [data-ia=up]')
    until(lambda: reihe('std', R) == [R[0], R[2], R[1]]); ruhig()
    check('Wochenangebot: Artikel nach oben – Bela und Edeka (ohne eigene Reihenfolge bisher) behalten ihre',
          reihe('std', R) == [R[0], R[2], R[1]] and reihe(BE, R) == [R[1], R[2], R[0]] and reihe(ED, R) == R, (reihe(BE, R), reihe(ED, R)))
    zu()

    # ---------- Zusatzpreise je Angebot ----------
    def zusatz(feld, label, preis):
        a.click('#item-body [data-ia=alt-add]'); a.wait_for_selector(f'#altlist .altrow:nth-child({feld})')
        lb = a.locator(f'#altlist .altrow:nth-child({feld}) [data-alt=label]'); lb.fill(label); lb.evaluate('e => e.blur()')
        pr = a.locator(f'#altlist .altrow:nth-child({feld}) [data-alt=price]'); pr.fill(preis); pr.evaluate('e => e.blur()')

    alt_std0 = sicht('std')['artikel'][r1['id']][3]
    angebot(BE, r1['id']); fenster(r1['id'])
    check('Bela, Artikelfenster: Zusatzpreise dieses Angebots bearbeitbar (ohne Wochenpreis)', a.locator('#item-body #altlist').count() == 1
          and a.locator('#item-body [name=price]').count() == 0 and 'Zusatzpreise in „' in a.text_content('#item-body'), a.text_content('#item-body')[:300])
    zusatz(1, 'Flugware', '19,90')
    FLUG = [{'status': 'value', 'value': 19.9, 'label': 'Flugware'}]
    until(lambda: sicht(BE)['artikel'][r1['id']][3] == FLUG); ruhig()
    check('Bela: Zusatzpreis im Artikelfenster – nur in Bela, Wochenangebot und Edeka ohne', sicht(BE)['artikel'][r1['id']][3] == FLUG
          and sicht('std')['artikel'][r1['id']][3] == alt_std0 and sicht(ED)['artikel'][r1['id']][3] == [], (sicht(BE)['artikel'][r1['id']][3], sicht('std')['artikel'][r1['id']][3]))
    a.wait_for_function("document.querySelector('#dlg-item').getAnimations().every(x => x.playState !== 'running')")
    shot(a.locator('#dlg-item'), SH + '/angebote-getrennt-zusatzpreise-1280.png')
    zu()
    vp = a.locator(f'#groups tr[data-id="{r1["id"]}"] [data-f=vprice]')
    vp.fill('20,50'); vp.evaluate('e => e.blur()')
    until(lambda: sicht(BE)['artikel'][r1['id']][2].get('value') == 20.5); ruhig()
    check('Bela: Preis in der Zeile geändert – Zusatzpreis bleibt', sicht(BE)['artikel'][r1['id']][3] == FLUG, sicht(BE)['artikel'][r1['id']][3])
    angebot('std', r1['id']); fenster(r1['id'])
    zusatz(len(alt_std0) + 1, 'Schiffsware', '7,70')
    until(lambda: len(sicht('std')['artikel'][r1['id']][3]) == len(alt_std0) + 1); ruhig()
    check('Wochenangebot: Zusatzpreis – Bela behält seinen, Edeka ohne', sicht(BE)['artikel'][r1['id']][3] == FLUG and sicht(ED)['artikel'][r1['id']][3] == [],
          sicht(BE)['artikel'][r1['id']][3])
    zu()

    # ---------- Duplizieren nur im gewählten Angebot ----------
    def neue(vorher):
        return [i for i in entwurf()[0]['items'] if i['id'] not in vorher]

    vorher = {i['id'] for i in entwurf()[0]['items']}
    angebot(BE, d['id']); fenster(d['id'])
    a.click('#item-body [data-ia=dup]')
    until(lambda: len(neue(vorher)) == 1); ruhig()
    k1 = neue(vorher)[0]['id']; sb = sicht(BE)
    check('Bela: Duplizieren – Kopie nur in Bela, direkt hinter dem Original; nicht im Wochenangebot',
          k1 in sb['artikel'] and k1 not in sicht('std')['artikel'] and sb['reihe'].index(k1) == sb['reihe'].index(d['id']) + 1
          and sb['artikel'][k1][1:3] == sb['artikel'][d['id']][1:3], (k1 in sicht('std')['artikel'], sb['artikel'].get(k1)))
    zu()
    vorher = {i['id'] for i in entwurf()[0]['items']}
    angebot('std', d['id']); fenster(d['id'])
    a.click('#item-body [data-ia=dup]')
    until(lambda: len(neue(vorher)) == 1); ruhig()
    k2 = neue(vorher)[0]['id']
    check('Wochenangebot: Duplizieren – Kopie nur im Wochenangebot, nicht in Bela', k2 in sicht('std')['artikel'] and k2 not in sicht(BE)['artikel'], k2 in sicht(BE)['artikel'])
    zu()

    # ---------- Veröffentlichen: Kunden sehen Reihenfolge und Zusatzpreise ihres Angebots ----------
    veroeffentlichen(a)
    pb, ps = sicht(BE, False), sicht('std', False)
    check('veröffentlicht: Bela in seiner Reihenfolge mit seinem Zusatzpreis, Wochenangebot in seiner',
          [i for i in pb['reihe'] if i in R] == [R[1], R[2], R[0]] and [i for i in ps['reihe'] if i in R] == [R[0], R[2], R[1]] and reihe(ED, R, False) == R
          and pb['artikel'][r1['id']][3] == FLUG and len(ps['artikel'][r1['id']][3]) == len(alt_std0) + 1, ([i for i in pb['reihe'] if i in R], pb['artikel'][r1['id']][3]))
    o = A.call(f'offer&angebot={BE}')[1]['offer']
    roh = [A.call(f'offer&angebot={BE}')[1]['offer'], A.call(f'offer&draft=1&angebot={BE}')[1]['offer'], A.call(f'offer&draft=1&angebot={ED}')[1]['offer'],
           Client('198.51.100.42').call('offer')[1]['offer']]
    check('veröffentlicht und Entwurf, Kundenangebot und öffentliches Wochenangebot: keine Stellen, Angebotspreise oder Bezeichnungen je Angebot ausgeliefert',
          all('reihen' not in x for x in roh) and not any(k in i for x in roh for i in x['items'] for k in ('stellen', 'variants', 'namen', 'gruppen'))
          and any((i.get('stellen') or {}).get(BE) is not None for i in entwurf()[0]['items']), [sorted(x.keys()) for x in roh])

    # ---------- Änderung zurücknehmen (Liste der Änderungen) nur im gewählten Angebot ----------
    def zeile_name(oid, iid, text):
        f = a.locator(f'#groups tr[data-id="{iid}"] [data-f={"name" if oid == "std" else "oname"}]')
        f.fill(text); f.evaluate('e => e.blur()')

    def zuruecknehmen(iid, oid=None):
        """„Rückgängig“ der Zeile „Bearbeitet“ – je Angebot, in dem die Bearbeitung liegt (oid); ohne oid: der einzige Knopf"""
        a.click('#offen-liste'); a.wait_for_selector('#dlg-publish[open]')
        a.click(f'#publish-body [data-rv=changed][data-rid="{iid}|{oid}"]' if oid else f'#publish-body [data-rv=changed][data-rid^="{iid}"]'); a.click('#dlg-confirm [data-v="1"]')
        a.wait_for_selector('#dlg-confirm', state='hidden'); a.click('#dlg-publish [data-close]'); a.wait_for_selector('#dlg-publish', state='hidden')

    angebot('std', q['id']); zeile_name('std', q['id'], 'Std q neu')
    until(lambda: sicht('std')['artikel'][q['id']][1] == 'Std q neu'); ruhig()
    angebot(BE, q['id']); zeile_name(BE, q['id'], 'Bela q neu')
    until(lambda: sicht(BE)['artikel'][q['id']][1] == 'Bela q neu'); ruhig()
    zuruecknehmen(q['id'], BE)
    until(lambda: sicht(BE)['artikel'][q['id']][1] == q['name']); ruhig()
    check('Bela: Bearbeitung zurückgenommen – nur in Bela, Wochenangebot behält „Std q neu“',
          sicht(BE)['artikel'][q['id']][1] == q['name'] and sicht('std')['artikel'][q['id']][1] == 'Std q neu', (sicht(BE)['artikel'][q['id']][1], sicht('std')['artikel'][q['id']][1]))
    zeile_name(BE, q['id'], 'Bela q neu 2')
    until(lambda: sicht(BE)['artikel'][q['id']][1] == 'Bela q neu 2'); ruhig()
    angebot('std', q['id']); zuruecknehmen(q['id'], 'std')
    until(lambda: sicht('std')['artikel'][q['id']][1] == q['name']); ruhig()
    check('Wochenangebot: Bearbeitung zurückgenommen – Bela behält „Bela q neu 2“',
          sicht('std')['artikel'][q['id']][1] == q['name'] and sicht(BE)['artikel'][q['id']][1] == 'Bela q neu 2', (sicht('std')['artikel'][q['id']][1], sicht(BE)['artikel'][q['id']][1]))
    # Zurücknehmen wirkt auf das Angebot, in dem die Änderung liegt – auch wenn gerade ein anderes gewählt ist
    namen_z = lambda: next(i for i in entwurf()[0]['items'] if i['id'] == z['id']).get('namen') or {}
    angebot('std', z['id']); zeile_name('std', z['id'], 'Std z neu')
    until(lambda: sicht('std')['artikel'][z['id']][1] == 'Std z neu'); ruhig()
    angebot(BE, z['id']); zuruecknehmen(z['id'])
    until(lambda: sicht('std')['artikel'][z['id']][1] == z['name']); ruhig()
    check('nur im Wochenangebot bearbeitet, „Rückgängig“ bei gewähltem Bela: Wochenangebot zurück, Bela ohne eigene Bezeichnung',
          sicht('std')['artikel'][z['id']][1] == z['name'] and sicht(BE)['artikel'][z['id']][1] == z['name'] and BE not in namen_z(), (sicht('std')['artikel'][z['id']][1], namen_z()))
    zeile_name(BE, z['id'], 'Bela z neu')
    until(lambda: sicht(BE)['artikel'][z['id']][1] == 'Bela z neu'); ruhig()
    angebot('std', z['id']); zuruecknehmen(z['id'])
    until(lambda: sicht(BE)['artikel'][z['id']][1] == z['name']); ruhig()
    check('nur in Bela bearbeitet, „Rückgängig“ bei gewähltem Wochenangebot: Bela zurück, Wochenangebot unverändert',
          sicht(BE)['artikel'][z['id']][1] == z['name'] and sicht('std')['artikel'][z['id']][1] == z['name'] and not namen_z(), (sicht(BE)['artikel'][z['id']][1], namen_z()))

    # ---------- Empfehlung je Angebot ----------
    def empfehlung(iid):
        a.click(f'#groups tr[data-id="{iid}"] [data-act=sale]'); a.wait_for_selector('#dlg-sale[open] #sale-body [name=value]')

    angebot(BE, s['id']); empfehlung(s['id'])
    a.click('#sale-body [data-sp=remove]'); a.wait_for_selector('#dlg-sale', state='hidden')
    until(lambda: not sicht(BE)['artikel'][s['id']][4]); ruhig()
    check('Bela: „Empfehlung entfernen“ – nur in Bela, im Wochenangebot bleibt sie', not sicht(BE)['artikel'][s['id']][4]
          and sicht('std')['artikel'][s['id']][4] and sicht('std')['artikel'][s['id']][2] == {'status': 'value', 'value': 5.5}, sicht('std')['artikel'][s['id']])
    angebot('std', s2['id']); empfehlung(s2['id'])
    a.fill('#sale-body [name=value]', '4,40'); a.click('#sale-body [type=submit]'); a.wait_for_selector('#dlg-sale', state='hidden')
    until(lambda: sicht('std')['artikel'][s2['id']][2].get('value') == 4.4); ruhig()
    check('Wochenangebot: Empfehlungspreis („wie oben“) geändert – Bela behält 6,50', sicht(BE)['artikel'][s2['id']][2] == {'status': 'value', 'value': 6.5},
          sicht(BE)['artikel'][s2['id']][2])
    angebot(BE, s2['id']); empfehlung(s2['id'])
    a.fill('#sale-body [name=value]', '3,30'); a.click('#sale-body [type=submit]'); a.wait_for_selector('#dlg-sale', state='hidden')
    until(lambda: sicht(BE)['artikel'][s2['id']][2].get('value') == 3.3); ruhig()
    check('Bela: Empfehlungspreis geändert – Wochenangebot behält 4,40', sicht('std')['artikel'][s2['id']][2] == {'status': 'value', 'value': 4.4},
          sicht('std')['artikel'][s2['id']][2])

    # ---------- Angebotskategorien ordnen die gemeinsame Stelle neu – Bela behält seine Reihenfolge ----------
    # In Bela steht y2 (Basisgruppe X, in Bela eigene Gruppe Y) vor b1, b2 (Gruppe Y); in der Liste direkt vor x2 (Gruppe X).
    # Die Kategorien stellen Y vor X: im Wochenangebot wandert y2 mit X hinter b1, b2 – in Bela darf sich nichts ändern.
    ruhig(); mk, rk = entwurf()
    vergeben = {i['id'] for i in (x, y, z, w, h1, h2, t, r1, r2, r3, q, s, s2, d, v2)}
    bei = lambda g: [i for i in mk['items'] if i['groupId'] == g and i['id'] in {f['id'] for f in frei} - vergeben and not i.get('gruppen')]
    XG, YG = [g['id'] for g in mk['groups'] if g['id'] not in (G1, G2, G3, G4, G5, H1, H2) and len(bei(g['id'])) >= 2][:2]
    (y2, x2), (b1, b2) = bei(XG)[:2], bei(YG)[:2]
    for i, pr in ((y2, 41.5), (b1, 42.5), (b2, 43.5)):
        i['variants'] = {**(i.get('variants') or {}), BE: {'status': 'value', 'value': pr}}
    y2['gruppen'] = {BE: YG}
    mk['items'].remove(y2); mk['items'].insert(mk['items'].index(x2), y2)
    for g in mk['groups']:
        if g['id'] in (XG, YG): g['vk'] = '9901' if g['id'] == XG else '9902'
    YR = [y2['id'], b1['id'], b2['id']]
    assert mk['items'].index(y2) < mk['items'].index(b1) and A.call('save_draft', {'model': mk, 'revision': rk})[0] == 200
    vor_k = reihe(BE, YR)
    assert A.call('angebotskategorien_save', {'rev': A.call('angebotskategorien')[1]['rev'], 'kategorien': [{'name': 'Test Y', 'vk': ['9902']}, {'name': 'Test X', 'vk': ['9901']}]})[0] == 200
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    li = lambda: [i['id'] for i in entwurf()[0]['items']]
    until(lambda: li().index(b1['id']) < li().index(y2['id']), 15); ruhig()
    std_k = [g for g, _ in sicht('std')['gruppen']]
    check('Angebotskategorien geändert (Y vor X, gemeinsame Stelle neu geordnet): Bela behält seine Reihenfolge',
          vor_k == YR and li().index(b1['id']) < li().index(y2['id']) and std_k.index(GN[YG]) < std_k.index(GN[XG]) and reihe(BE, YR) == YR, (vor_k, reihe(BE, YR)))
    # Eine Ordnungsregel: Zeilen des Editors in Bela in derselben Reihenfolge wie die Sicht des Servers (Kundenseite)
    angebot(BE, y2['id'])
    zeilen = a.eval_on_selector_all('#groups tr[data-id]', 'xs => xs.map(x => x.dataset.id)')
    check('Editor (Bela): Zeilenfolge gleich der Reihenfolge der Serversicht (offer&draft=1&angebot=bela)', zeilen == sicht(BE)['reihe'], (zeilen[:6], sicht(BE)['reihe'][:6]))
    check('keine Skriptfehler', not errors, errors[:3])

    m390 = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    m390.on('pageerror', lambda e: errors.append(str(e)))
    m390.goto(BASE + '/admin/'); m390.wait_for_selector('#screen-auth:not([hidden])')
    m390.fill('#au-user', 'admin'); m390.fill('#pw1', PW); m390.click('#auth-submit'); m390.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    m390.evaluate(f"document.querySelector('#offer-bar [data-offer=\"{BE}\"]').click()")
    m390.wait_for_selector(f'#groups tr[data-id="{r1["id"]}"]')
    m390.click(f'#groups tr[data-id="{r1["id"]}"] [data-act=item]'); m390.wait_for_selector('#dlg-item[open] #item-body #altlist .altrow')
    sw = m390.evaluate('document.documentElement.scrollWidth')
    check('390 px: Artikelfenster in Bela (mit Zusatzpreis) passt ohne seitliches Scrollen, keine Skriptfehler', sw <= 390 and not errors, (sw, errors[:3]))
    m390.wait_for_function("document.querySelector('#dlg-item').getAnimations().every(x => x.playState !== 'running')")
    m390.screenshot(path=SH + '/angebote-getrennt-fenster-390.png')
    m390.locator('#item-body #altlist').scroll_into_view_if_needed()
    m390.screenshot(path=SH + '/angebote-getrennt-zusatzpreise-390.png')
    br.close()

# ---------- Prüfung auf dem Server (ohne Browser): Stellen und Zusatzpreise je Angebot ----------
def art(mm, iid):
    return next(i for i in mm['items'] if i['id'] == iid)


def speichern(mm):
    return A.call('save_draft', {'model': mm, 'revision': entwurf()[1]})


def angebote_setzen(fn):
    o = A.call('offers')[1]
    assert A.call('offers_save', {'rev': o['rev'], 'offers': fn([x for x in o['offers'] if x.get('art') != 'sonder'])})[0] == 200


FL = lambda n: [{'status': 'value', 'value': 10.0 + k, 'label': f'Zusatz {k}'} for k in range(n)]   # noqa: E731
WEG = 'weg-test'
angebote_setzen(lambda l: l + [{'id': WEG, 'name': 'Weg Test', 'fallback': 'hidden'}])
mm = entwurf()[0]
art(mm, x['id'])['variants'][WEG] = {'status': 'value', 'value': 1.0}
art(mm, x['id'])['stellen'] = {**(art(mm, x['id']).get('stellen') or {}), WEG: 4}
assert speichern(mm)[0] == 200 and art(entwurf()[0], x['id'])['stellen'].get(WEG) == 4
angebote_setzen(lambda l: [o for o in l if o['id'] != WEG])
mm = entwurf()[0]
art(mm, r1['id'])['stellen'] = {BE: 999999, ED: 0, 'gibt-es-nicht': 1, FOLGT: 2, 'std': 3}
art(mm, r2['id'])['stellen'] = {BE: -1, ED: 1000000}
art(mm, r3['id'])['stellen'] = {BE: '3', ED: True}
art(mm, z['id'])['stellen'] = {BE: 1.5}
art(mm, q['id'])['stellen'] = {BE: 5, ED: 6}
art(mm, w['id'])['variants'][BE] = {'status': 'hidden', 'alt': FL(1)}
art(mm, w['id'])['stellen'] = {BE: 7, ED: 8}
art(mm, r1['id'])['variants'][BE]['alt'] = FL(7)
st_, _ = speichern(mm)
me = entwurf()[0]
st = lambda iid: art(me, iid).get('stellen') or {}   # noqa: E731
check('Server: gültige Stellen bleiben (auch 999999), fremde und gelöschte Angebote, Wochenangebot und folgendes Angebot fallen weg',
      st_ == 200 and st(r1['id']) == {BE: 999999, ED: 0} and WEG not in st(x['id']) and WEG not in (art(me, x['id']).get('variants') or {}), (st(r1['id']), st(x['id'])))
check('Server: negative oder zu große Stellen fallen weg', not st(r2['id']), st(r2['id']))
check('Server: Stellen, die keine ganze Zahl sind (Text, Wahrheitswert, Kommazahl), fallen weg', not st(r3['id']) and BE not in st(z['id']), (st(r3['id']), st(z['id'])))
check('Server: Stellen nur für Artikel, die im Angebot stehen (nicht in Edeka, in Bela ausgeblendet)', st(q['id']) == {BE: 5} and st(w['id']) == {ED: 8}, (st(q['id']), st(w['id'])))
check('Server: Zusatzpreise bei ausgeblendetem Artikel fallen weg, höchstens 5 je Angebot', 'alt' not in art(me, w['id'])['variants'][BE]
      and art(me, r1['id'])['variants'][BE]['alt'] == FL(5), (art(me, w['id'])['variants'][BE], len(art(me, r1['id'])['variants'][BE].get('alt') or [])))
mm = entwurf()[0]
art(mm, r1['id'])['variants'][BE]['alt'] = [{'status': 'value', 'value': -5}]
st_, r_ = speichern(mm)
check('Server: ungültiger Zusatzpreis wird abgewiesen, nichts gespeichert', st_ in (400, 422) and art(entwurf()[0], r1['id'])['variants'][BE]['alt'] == FL(5), (st_, r_))
mm = entwurf()[0]
for i, k in ((r1, 2), (r2, 1), (r3, 0)):
    art(mm, i['id'])['stellen'] = {**(art(mm, i['id']).get('stellen') or {}), BE: k}
assert speichern(mm)[0] == 200
check('Server: Kundenangebot in der Reihenfolge seiner Stellen (Entwurf), ohne die Stellen auszuliefern', reihe(BE, R) == [R[2], R[1], R[0]]
      and not any('stellen' in i for i in A.call(f'offer&draft=1&angebot={BE}')[1]['offer']['items']), reihe(BE, R))
# Artikelpreise-Import (Kundengruppe von Bela) behält die Zusatzpreise des Angebots
KG = (next(o for o in A.call('offers')[1]['offers'] if o['id'] == BE).get('gruppen') or [None])[0]
if not KG:
    kg = A.call('kundengruppen')[1]
    KG = '77'
    assert A.call('kundengruppen_save', {'rev': kg['rev'], 'groups': kg['groups'] + [{'nr': KG, 'name': 'Test Bela'}]})[0] == 200
    angebote_setzen(lambda l: [{**o, 'gruppen': [KG]} if o['id'] == BE else o for o in l])
zl = [{'zeile': 2, 'code': r1['code'], 'gruppe': KG, 'preis': 44.0}]
pr = A.call('import_pruefen', {'art': 'angebot_preise', 'daten': {'preise': zl}, 'optionen': {'gruppen': []}})[1]
st_, r_ = A.call('import_uebernehmen', {'art': 'angebot_preise', 'daten': {'preise': zl}, 'optionen': {'gruppen': []}, 'stand': pr['stand']})
if st_ == 403 and r_.get('code') == 'confirmation_required':
    assert A.call('reauth', {'password': PW})[0] == 200
    st_, r_ = A.call('import_uebernehmen', {'art': 'angebot_preise', 'daten': {'preise': zl}, 'optionen': {'gruppen': []}, 'stand': pr['stand']})
vb = art(entwurf()[0], r1['id'])['variants'][BE]
check('Artikelpreise-Import: neuer Preis in Bela, Zusatzpreise des Angebots bleiben', st_ == 200 and vb.get('value') == 44.0 and vb.get('alt') == FL(5), (st_, vb))
# Angebot kopieren: Stellen und Zusatzpreise kommen mit; aus dem Wochenangebot werden dessen Zusatzpreise die der Kopie
def kopieren(quelle, name):
    st_, r_ = A.call('offer_kopieren', {'quelle': quelle, 'name': name, 'rev': A.call('offers')[1]['rev'], 'revision': entwurf()[1]})
    assert st_ == 200, r_
    return next(o['id'] for o in A.call('offers')[1]['offers'] if o['name'] == name)


KB = kopieren(BE, 'Bela Kopie Test')
me = entwurf()[0]
check('Kopie von Bela: Stellen und Zusatzpreise übernommen, Reihenfolge wie in Bela', all(st(i).get(KB) is not None and st(i).get(KB) == st(i).get(BE) for i in R)
      and art(me, r1['id'])['variants'][KB].get('alt') == FL(5) and reihe(KB, R) == reihe(BE, R), ([st(i) for i in R], art(me, r1['id'])['variants'][KB]))
KS = kopieren('std', 'Wochen Kopie Test')
me = entwurf()[0]
ap = art(me, r1['id'])['altPrices']
check('Kopie des Wochenangebots: Zusatzpreise des Wochenangebots werden Zusatzpreise der Kopie', ap and art(me, r1['id'])['variants'][KS].get('alt') == ap
      and sicht(KS)['artikel'][r1['id']][3] == ap, (ap, art(me, r1['id'])['variants'][KS]))

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
