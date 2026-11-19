"""Jedes Angebot für sich (Inhaber 19.11.2026, Schritt 1): Bearbeitungen im Angebotseditor wirken nur auf das gewählte
Angebot – Preise, Bezeichnung und Angebotsgruppen (Name, Bereich, Reihenfolge, Zuordnung der Artikel). Kundenangebote „Bela“
und „Edeka“ mit eigener Artikelliste, ihre Artikel auch im Wochenangebot. Bela → Wochenangebot: Artikelfenster ohne
Wochenpreis, Gruppenauswahl nur mit Gruppen von Bela, Gruppe und Bezeichnung im Artikelfenster, Preis in der Zeile, Gruppe
umbenennen (Trennen und Umbenennen in einem Rückgängig-Schritt), Bereich, zweite Änderung an derselben Gruppenkarte,
Reihenfolge der Gruppen und Artikel in eine andere Gruppe im Fenster „Editor“, „Artikel hinzufügen“ ohne doppelte
Überschrift. Wochenangebot → Edeka: Gruppe umbenennen, Bereich, Artikel in eine andere Gruppe, Bezeichnung in der Zeile,
Reihenfolge der Gruppen (↓). Geprüft wird die aufgelöste Sicht der Angebote über die Schnittstelle (offer&draft=1).
Bildschirmfotos Artikelfenster in Bela 1280/390 px. Nur Testdaten."""
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, shot, until

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


def sicht(oid):
    """Aufgelöstes Angebot im Entwurf: Gruppen (Name, Bereich) in Reihenfolge, je Artikel Gruppe, Bezeichnung, Preis, Zusatzpreise"""
    o = A.call('offer&draft=1' + ('' if oid == 'std' else f'&angebot={oid}'))[1]['offer']
    gn = {g['id']: g for g in o['groups']}
    return {'gruppen': [(g['name'], g.get('section') or '') for g in o['groups']],
            'artikel': {i['id']: (gn[i['groupId']]['name'], i['name'], i['price'], i.get('altPrices') or []) for i in o['items']}}


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
assert A.call('save_draft', {'model': m, 'revision': rev})[0] == 200
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
    check('Bela, Artikelfenster: kein Feld für den Wochenpreis, Bezeichnung des Preises und Zusatzpreise; Hinweis auf den Preis in der Zeile',
          a.locator('#item-body [name=price], #item-body [name=priceLabel], #item-body #altlist').count() == 0
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
    check('keine Skriptfehler', not errors, errors[:3])

    m390 = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    m390.on('pageerror', lambda e: errors.append(str(e)))
    m390.goto(BASE + '/admin/'); m390.wait_for_selector('#screen-auth:not([hidden])')
    m390.fill('#au-user', 'admin'); m390.fill('#pw1', PW); m390.click('#auth-submit'); m390.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    m390.evaluate(f"document.querySelector('#offer-bar [data-offer=\"{BE}\"]').click()")
    m390.wait_for_selector(f'#groups tr[data-id="{x["id"]}"]')
    m390.click(f'#groups tr[data-id="{x["id"]}"] [data-act=item]'); m390.wait_for_selector('#dlg-item[open] #item-body [name=code]')
    sw = m390.evaluate('document.documentElement.scrollWidth')
    check('390 px: Artikelfenster in Bela passt ohne seitliches Scrollen, keine Skriptfehler', sw <= 390 and not errors, (sw, errors[:3]))
    m390.wait_for_function("document.querySelector('#dlg-item').getAnimations().every(x => x.playState !== 'running')")
    m390.screenshot(path=SH + '/angebote-getrennt-fenster-390.png')
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
