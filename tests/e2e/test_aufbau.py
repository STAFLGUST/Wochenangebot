"""Aufbau des Angebots (Knopf „Editor“ in „Angebot bearbeiten“, Wunsch des Inhabers 11.11.2026, Artikel 12.11.2026): Knopf neben „Werbung“
(hellblau, gleiche Höhe, hell/dunkel, 390 px), Fenster mit Bereichen und eingerückten Gruppen in Angebotsreihenfolge
(„ohne Bereich“ an seiner Stelle), Verschieben per Pfeil und per Ziehen (Maus und Touch, Bereich als Ganzes, Gruppe im
Bereich und in einen anderen Bereich), „Abbrechen“ speichert nichts, „Übernehmen“ speichert über den Entwurf (Revision,
Protokoll, Rückgängig, Veröffentlichen-Dialog „Aufbau“), Wirkung im Editor, in Vorschau, auf der Angebotsseite (Liste,
Tabelle) und beim Kunden; ältere Versionen unverändert; Revisionskonflikt mit einem zweiten Bearbeiter; Kundenangebot
„folgt dem Wochenangebot“ nur ansehen, Kundenangebot mit eigener Artikelliste; ohne Bearbeitungsrecht kein Knopf und 403.
Artikel: Gruppen aufklappen (einzeln, alle), Artikel per Pfeil und Ziehen umsortieren, per Ziehen in eine aufgeklappte bzw.
zugeklappte Gruppe und über „In Gruppe …“ verschieben, Zahlen, Abbrechen, Übernehmen (Entwurf, Editor, Protokoll,
Veröffentlichen, Angebotsseite Liste/Tabelle, Kundenangebot), Konflikt, mit Angebotskategorien nur Artikel änderbar, 390 px
mit Touch. Nur Testdaten (Seed-Angebot)."""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, shot, until

PW = 'Sicheres-Passwort-1'
PW_E = 'Editor-Zugang-77'
PW_L = 'Leserin-Zugang-1'
EIGEN = 'testkunde-eigen'   # Kundenangebot mit eigener Artikelliste (nur Testdaten)
FOLGT = 'edeka'             # Voreinstellung: folgt dem Wochenangebot
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def entwurf(cl):
    d = cl.call('draft')[1]
    m = d['draft'] or d['published']
    for k in ('savedAt', 'savedBy', 'publishedAt', 'rev'):
        m.pop(k, None)
    return m, d['revision']


def im_angebot(it, oid):
    v = (it.get('variants') or {}).get(oid)
    if oid == 'std':
        return not (v and v.get('status') == 'hidden')
    if oid == EIGEN:
        return bool(v) and v.get('status') != 'hidden'
    return not (v and v.get('status') == 'hidden')


def bloecke(m, oid='std'):
    """Erwarteter Aufbau: [(Bereich, [Gruppen-IDs])] der Gruppen mit Artikeln des Angebots, aufeinanderfolgend gleicher Bereich"""
    used = {it['groupId'] for it in m['items'] if im_angebot(it, oid)}
    out = []
    for g in m['groups']:
        if g['id'] not in used:
            continue
        if out and out[-1][0] == (g.get('section') or ''):
            out[-1][1].append(g['id'])
        else:
            out.append((g.get('section') or '', [g['id']]))
    return out


def fenster(pg):
    return [(b, ids) for b, ids in pg.eval_on_selector_all('#abf-liste > .abf-ber',
            'bs => bs.map(b => [b.dataset.bereich, [...b.querySelectorAll(".abf-g")].map(g => g.dataset.gid)])')]


def editor(pg):
    """Editor: Gruppen-IDs in Reihenfolge und Bereichsüberschriften"""
    return (pg.eval_on_selector_all('#groups > section.gcard', 'xs => xs.map(x => x.dataset.gid)'),
            pg.eval_on_selector_all('#groups > h2.gsec', 'xs => xs.map(x => x.textContent.trim().toLowerCase())'))


def quoten(t):
    return t.replace('„', '"').replace('“', '"').replace('”', '"').strip().lower()


def art_reihe(m, gid, oid='std'):
    """Artikel-IDs einer Gruppe im Angebot in Reihenfolge des Entwurfs"""
    return [i['id'] for i in m['items'] if i['groupId'] == gid and im_angebot(i, oid)]


def angebot_reihe(m, oid=None):
    """Artikel in Angebotsreihenfolge wie OfferCore.enrichOffer (Gruppe, dann Stelle); oid=None: alle Artikel des Modells"""
    gi = {g['id']: k for k, g in enumerate(m['groups'])}
    its = [(gi.get(i['groupId'], 10 ** 6), k, i['id']) for k, i in enumerate(m['items']) if oid is None or im_angebot(i, oid)]
    return [x[2] for x in sorted(its)]


def dlg_art(pg, gid):
    return pg.eval_on_selector_all(f'#abf-liste .abf-g[data-gid="{gid}"] .abf-a[data-aid]', 'xs => xs.map(x => x.dataset.aid)')


def flach(bl):
    return [g for _, ids in bl for g in ids]


def gruppen_reihe(model):
    used = {it['groupId'] for it in model['items']}
    return [g['id'] for g in model['groups'] if g['id'] in used]


def ziehen(pg, quelle, ziel, oben=True, steps=14):
    """Am Griff „quelle“ ziehen und über dem Element „ziel“ loslassen (obere bzw. untere Hälfte)"""
    a = pg.locator(quelle).bounding_box()
    b = pg.locator(ziel).bounding_box()
    pg.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2)
    pg.mouse.down()
    pg.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2 + (-6 if oben else 6), steps=2)
    pg.mouse.move(b['x'] + 40, b['y'] + b['height'] * (0.2 if oben else 0.8), steps=steps)
    pg.mouse.up()


def touch_ziehen(pg, cdp, quelle, ziel):
    a = pg.locator(quelle).bounding_box()
    b = pg.locator(ziel).bounding_box()
    x, y0, y1 = a['x'] + a['width'] / 2, a['y'] + a['height'] / 2, b['y'] + b['height'] * 0.2
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y0}]})
    for i in range(1, 13):
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y0 + (y1 - y0) * i / 12}]})
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})


def login(pg, user, pw):
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')


def gespeichert(pg):
    pg.wait_for_function("document.querySelector('#save-state').className.includes('saved')", timeout=10000)


def oeffnen(pg):
    pg.click('#btn-aufbau'); pg.wait_for_selector('#dlg-aufbau[open] #abf-liste')
    pg.wait_for_function("document.querySelector('#dlg-aufbau').getAnimations({subtree: true}).every(x => x.playState !== 'running')")   # Einblenden abgeschlossen


# ---------- Testdaten: eine Gruppe ohne Bereich, ein Kundenangebot mit eigener Artikelliste, Nutzer ----------
A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': PW_E, 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': PW_L, 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': PW_E})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': PW_L})[0] == 200
of = A.call('offers')[1]
st, r = A.call('offers_save', {'rev': of['rev'], 'offers': of['offers'] + [{'id': EIGEN, 'name': 'Wochenangebot Testkunde', 'fallback': 'hidden'}]})
assert st == 200, r
m, rev = entwurf(A)
OHNE_G = next(g for g in m['groups'] if g['name'].startswith('Geflügel, frisch'))['id']   # letzte Gruppe des zweiten Bereichs
for g in m['groups']:
    if g['id'] == OHNE_G:
        g['section'] = ''
# eigene Liste: je ein Artikel aus drei Gruppen in drei Bereichen
EIG_GR = [m['groups'][0]['id'], next(g['id'] for g in m['groups'] if g['name'].startswith('Rindfleisch, EU')), m['groups'][-1]['id']]
for gid in EIG_GR:
    it = next(i for i in m['items'] if i['groupId'] == gid)
    it.setdefault('variants', {})[EIGEN] = {'status': 'value', 'value': 12.5}
st, r = A.call('save_draft', {'model': m, 'revision': rev})
assert st == 200, r
M0, _ = entwurf(A)
B0 = bloecke(M0)
SEK = [b for b, _ in B0]
PREISE0 = {i['id']: (i['groupId'], json.dumps(i['price'], sort_keys=True), json.dumps(i.get('variants') or {}, sort_keys=True)) for i in M0['items']}
VERS0 = {v['id'] for v in A.call('versions')[1]['versions']}
PUB0 = gruppen_reihe(A.call('draft')[1]['published'])

errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append(str(e)))
    login(a, 'admin', PW)

    # ---------- Knopf ----------
    k = a.locator('#btn-aufbau')
    check('Knopf „Editor“ sichtbar, direkt neben „Werbung“', k.is_visible() and k.inner_text().strip() == 'Editor'
          and a.evaluate("document.querySelector('#btn-werbung').nextElementSibling.id") == 'btn-aufbau')
    kb, wb = k.bounding_box(), a.locator('#btn-werbung').bounding_box()
    check('gleiche Höhe und Zeile wie „Werbung“', abs(kb['height'] - wb['height']) < 0.5 and abs(kb['y'] - wb['y']) < 0.5 and kb['x'] > wb['x'], (kb, wb))
    farbe = a.evaluate("""() => { const s = getComputedStyle(document.querySelector('#btn-aufbau')), w = getComputedStyle(document.querySelector('#btn-werbung'));
      return [s.backgroundColor, s.color, s.borderTopColor, w.backgroundColor, getComputedStyle(document.querySelector('#btn-aufbau svg')).color, s.borderTopLeftRadius === w.borderTopLeftRadius]; }""")
    check('hellblau: helle blaue Fläche, blauer Rand und Text (Blauton des Kennzeichens „eigene“), Form wie „Werbung“',
          farbe[0] == 'rgb(231, 239, 248)' and farbe[1] == 'rgb(31, 78, 122)' and farbe[2] == 'rgb(169, 196, 224)' and farbe[0] != farbe[3] and farbe[5], farbe)
    shot(a.locator('.ed-toolbar'), SH + '/aufbau-leiste.png')

    # ---------- Fenster: Aufbau in Angebotsreihenfolge ----------
    oeffnen(a)
    check('Fenster: Bereiche und Gruppen in Angebotsreihenfolge, „ohne Bereich“ an seiner Stelle', fenster(a) == B0 and '' in SEK and SEK.index('') == 2, fenster(a))
    titel = a.eval_on_selector_all('#abf-liste > .abf-ber .abf-bt b', 'xs => xs.map(x => x.textContent.trim())')
    check('Überschriften: Bereichsnamen, Block ohne Bereich heißt „ohne Bereich“', titel == [s or 'ohne Bereich' for s in SEK], titel)
    g1 = M0['groups'][0]
    n1 = sum(1 for i in M0['items'] if i['groupId'] == g1['id'])
    z = a.locator(f'#abf-liste .abf-g[data-gid="{g1["id"]}"]')
    check('Gruppe mit Name und Artikelzahl, eingerückt unter ihrem Bereich', g1['name'] in z.inner_text() and f'{n1} Artikel' in z.inner_text()
          and z.locator('.abf-gn').bounding_box()['x'] >= a.locator('#abf-liste .abf-bt').first.bounding_box()['x'] + 16)
    check('Hinweis: gilt für alle Angebote; Titel und Knöpfe', 'Gilt für alle Angebote' in a.inner_text('#dlg-aufbau') and 'Aufbau des Angebots' in a.inner_text('#abf-titel')
          and a.locator('#abf-ok').is_visible() and a.locator('#dlg-aufbau .dlg-foot [data-close]').inner_text().strip() == 'Abbrechen')
    check('erster Bereich ohne ↑, letzter ohne ↓', a.locator('#abf-liste > .abf-ber').first.locator('.abf-bk [data-ab="b-hoch"]').is_disabled()
          and a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-runter"]').is_disabled())
    shot(a.locator('#dlg-aufbau'), SH + '/aufbau-fenster.png')

    # ---------- Pfeile, dann „Abbrechen“ speichert nichts ----------
    a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-hoch"]').click()
    erw = B0[:-2] + [B0[-1], B0[-2]]
    check('Pfeil: letzter Bereich eine Stelle nach oben – mit allen Gruppen', fenster(a) == erw, fenster(a))
    check('Fokus bleibt auf dem Pfeil des verschobenen Bereichs', a.evaluate("document.activeElement.dataset.ab") == 'b-hoch'
          and a.evaluate("document.activeElement.closest('.abf-ber').dataset.bereich") == B0[-1][0])
    g_a, g_b = B0[0][1][0], B0[0][1][1]
    a.click(f'#abf-liste .abf-g[data-gid="{g_b}"] [data-ab="g-hoch"]')
    check('Pfeil: Gruppe innerhalb ihres Bereichs nach oben', fenster(a)[0][1][:2] == [g_b, g_a], fenster(a)[0])
    check('Stand: „Geändert – noch nicht übernommen“', 'Geändert' in a.inner_text('#abf-stand'))
    rev_vor = A.call('draft')[1]['revision']
    a.click('#dlg-aufbau .dlg-foot [data-close]'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    m1, rev1 = entwurf(A)
    check('Abbrechen speichert nichts (Entwurf und Revision unverändert, Editor unverändert)', rev1 == rev_vor and bloecke(m1) == B0
          and editor(a)[0] == flach(B0), (rev1, rev_vor))
    oeffnen(a)
    check('wieder geöffnet: ursprünglicher Aufbau', fenster(a) == B0)
    a.locator('#abf-liste > .abf-ber').nth(1).locator('.abf-bk [data-ab="b-runter"]').click()
    a.keyboard.press('Escape')
    check('Escape mit Änderungen: Fenster bleibt beim ersten Mal offen (Hinweis)', a.locator('#dlg-aufbau[open]').count() == 1)
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    check('zweites Escape schließt, nichts gespeichert', A.call('draft')[1]['revision'] == rev_vor)

    # ---------- Ziehen (Maus): Bereich als Ganzes, Gruppe im Bereich, Gruppe in einen anderen Bereich ----------
    a.set_viewport_size({'width': 1440, 'height': 2400})   # ganzes Fenster sichtbar (Ziehen ohne Rollen)
    oeffnen(a)
    letzter = '#abf-liste > .abf-ber:last-child > .abf-bk [data-griff="b"]'
    ziehen(a, letzter, '#abf-liste > .abf-ber:first-child > .abf-bk')
    erw = [B0[-1]] + B0[:-1]
    check('Ziehen: letzten Bereich mit allen Gruppen ganz nach oben', fenster(a) == erw, [b for b, _ in fenster(a)])
    b1 = erw[1][1]   # Gruppen des (jetzt zweiten) ersten Bereichs
    ziehen(a, f'#abf-liste .abf-g[data-gid="{b1[2]}"] [data-griff="g"]', f'#abf-liste .abf-g[data-gid="{b1[0]}"]')
    erw[1] = (erw[1][0], [b1[2], b1[0], b1[1]] + b1[3:])
    check('Ziehen: Gruppe innerhalb ihres Bereichs an den Anfang', fenster(a) == erw, fenster(a)[1])
    ziehen(a, f'#abf-liste .abf-g[data-gid="{b1[0]}"] [data-griff="g"]', f'#abf-liste .abf-g[data-gid="{b1[4]}"]', oben=False)
    erw[1] = (erw[1][0], [b1[2], b1[1], b1[3], b1[4], b1[0]] + b1[5:])
    check('Ziehen: Gruppe nach unten', fenster(a) == erw, fenster(a)[1])
    ziel = erw[1][1][1]
    ziehen(a, f'#abf-liste .abf-g[data-gid="{OHNE_G}"] [data-griff="g"]', f'#abf-liste .abf-g[data-gid="{ziel}"]')
    neu = fenster(a)
    erw = [x for x in erw if x[0] != '']
    erw[1] = (erw[1][0], [erw[1][1][0], OHNE_G] + erw[1][1][1:])
    check('Ziehen: Gruppe ohne Bereich in einen anderen Bereich – Block „ohne Bereich“ entfällt', neu == erw, [(b, ids[:3]) for b, ids in neu])
    check('Kennzeichen „Bereich neu“ an der Gruppe', 'bereich neu' in a.inner_text(f'#abf-liste .abf-g[data-gid="{OHNE_G}"]').lower()
          and a.locator('#abf-liste .abf-neu').count() == 1)
    ERW = erw
    shot(a.locator('#dlg-aufbau'), SH + '/aufbau-gezogen.png')

    # ---------- Übernehmen ----------
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    a.wait_for_selector('#toast.show:has-text("Aufbau übernommen")')
    gespeichert(a)
    m2, rev2 = entwurf(A)
    check('Übernehmen speichert den Entwurf (neue Revision): Reihenfolge und Bereich wie im Fenster', rev2 > rev_vor and bloecke(m2) == ERW
          and next(g for g in m2['groups'] if g['id'] == OHNE_G)['section'] == ERW[1][0], bloecke(m2)[:2])
    p2 = {i['id']: (i['groupId'], json.dumps(i['price'], sort_keys=True), json.dumps(i.get('variants') or {}, sort_keys=True)) for i in m2['items']}
    check('Artikel, Gruppenzuordnung und Preise unverändert', p2 == PREISE0)
    ed = editor(a)
    check('Editor zeigt die neue Reihenfolge mit Bereichsüberschriften', ed[0] == flach(ERW) and ed[1] == [b.lower() for b, _ in ERW if b], ed[1])
    check('Feld „Bereich“ der verschobenen Gruppe gesetzt', a.locator(f'#groups section.gcard[data-gid="{OHNE_G}"] [data-gf="section"]').input_value() == ERW[1][0])
    log = json.dumps(A.call('log')[1], ensure_ascii=False)
    check('Protokoll: Aufbau des Angebots geändert (Bereich bei 1 Gruppe neu)', 'Aufbau des Angebots geändert (Reihenfolge der Bereiche, Gruppen und Artikel, Bereich bei 1 Gruppe neu)' in log)
    check('Knopf „Veröffentlichen“ nennt den geänderten Aufbau', 'Aufbau geändert' in (a.get_attribute('#btn-publish', 'title') or ''), a.get_attribute('#btn-publish', 'title'))
    vorschau = A.call('offer&draft=1')[1]['offer']
    check('Vorschau (Entwurf): Gruppen in neuer Reihenfolge', [g['id'] for g in vorschau['groups']] == flach(ERW))
    check('Öffentliche Seite noch unverändert (erst nach „Veröffentlichen“)', [g['id'] for g in Client('198.51.100.9').call('offer')[1]['offer']['groups']] == PUB0)
    # Rückgängig nimmt die Übernahme zurück, Wiederholen über das Fenster
    a.click('#btn-undo'); gespeichert(a)
    check('„Rückgängig“ stellt den vorherigen Aufbau wieder her', bloecke(entwurf(A)[0]) == B0)
    oeffnen(a)
    a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-hoch"]').click()
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    B1 = B0[:-2] + [B0[-1], B0[-2]]
    check('Übernehmen per Pfeil gespeichert', bloecke(entwurf(A)[0]) == B1, [b for b, _ in bloecke(entwurf(A)[0])])

    # ---------- Veröffentlichen: Dialog nennt den Aufbau; Wirkung auf Seite, Liste, Tabelle; alte Version unverändert ----------
    a.set_viewport_size({'width': 1440, 'height': 950})
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    check('Veröffentlichen-Dialog: Abschnitt „Aufbau“ mit Rückgängig', 'Reihenfolge der Bereiche, Gruppen oder Artikel geändert' in a.inner_text('#dlg-publish')
          and a.locator('#dlg-publish [data-rv="aufbau"]').count() == 1)
    a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    pub = Client('198.51.100.9').call('offer')[1]['offer']
    check('veröffentlicht: öffentliche Seite liefert die Gruppen in neuer Reihenfolge', [g['id'] for g in pub['groups']] == flach(B1)
          and pub['sections'] == [b for b, _ in B1 if b])
    neu_v = [v for v in A.call('versions')[1]['versions'] if v['id'] not in VERS0]
    alt = A.call('version&id=' + neu_v[0]['id'])[1]['model'] if neu_v else {'groups': [], 'items': []}
    check('vorherige Fassung als Version gesichert – mit ihrem alten Aufbau', len(neu_v) == 1 and gruppen_reihe(alt) == PUB0)
    s = br.new_page(viewport={'width': 1440, 'height': 950})
    s.on('pageerror', lambda e: errors.append(str(e)))
    s.goto(BASE + '/'); s.wait_for_selector('.al .al-sec .al-st h3')
    liste = [quoten(t) for t in s.eval_on_selector_all('.al .al-sec:not(.werb-sec) .al-st h3', 'xs => xs.map(x => x.textContent)')]
    check('Angebotsseite (Angebotsansicht wie Druck/PDF): Bereiche in neuer Reihenfolge', liste == [quoten(b) for b, _ in B1 if b], liste)
    s.goto(BASE + '/#ansicht=tabelle'); s.reload(); s.wait_for_selector('table.grid tr.g-row')
    tab = s.eval_on_selector_all('table.grid tr.s-row', 'xs => xs.map(x => x.textContent.trim())')
    check('Angebotsseite (Tabelle): Bereiche in neuer Reihenfolge', [t.lower() for t in tab] == [b.lower() for b, _ in B1 if b], tab)
    s.close()

    # ---------- Revisionskonflikt mit einem zweiten Bearbeiter ----------
    oeffnen(a)
    start = fenster(a)
    me, mrev = entwurf(E)   # Eddi tauscht die ersten beiden Gruppen und speichert
    ids = [g['id'] for g in me['groups']]
    i0, i1 = ids.index(start[0][1][0]), ids.index(start[0][1][1])
    me['groups'][i0], me['groups'][i1] = me['groups'][i1], me['groups'][i0]
    assert E.call('save_draft', {'model': me, 'revision': mrev})[0] == 200
    E_BL = bloecke(entwurf(A)[0])
    a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-hoch"]').click()
    a.click('#abf-ok')
    a.wait_for_selector('#abf-err:has-text("inzwischen geändert")')
    check('Konflikt: Hinweis mit Namen, nichts übernommen, Fenster zeigt den neuen Stand', 'Eddi Editor hat den Aufbau inzwischen geändert' in a.inner_text('#abf-err')
          and fenster(a) == E_BL and bloecke(entwurf(A)[0]) == E_BL and a.locator('#dlg-aufbau[open]').count() == 1, a.inner_text('#abf-err'))
    shot(a.locator('#dlg-aufbau'), SH + '/aufbau-konflikt.png')
    a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-hoch"]').click()
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    erw = E_BL[:-2] + [E_BL[-1], E_BL[-2]]
    check('danach erneut übernommen: eigene Änderung auf dem Stand des anderen', bloecke(entwurf(A)[0]) == erw)
    # Änderung eines anderen ohne Aufbau (Preis): wird beim Übernehmen zusammengeführt
    oeffnen(a)
    me, mrev = entwurf(E)
    pid = me['items'][0]['id']
    me['items'][0]['price'] = {'status': 'value', 'value': 77.77}
    assert E.call('save_draft', {'model': me, 'revision': mrev})[0] == 200
    a.locator('#abf-liste > .abf-ber').first.locator('.abf-bk [data-ab="b-runter"]').click()
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    m3, _ = entwurf(A)
    erw2 = [erw[1], erw[0]] + erw[2:]
    check('Preisänderung des anderen bleibt erhalten, eigener Aufbau gespeichert', bloecke(m3) == erw2
          and next(i for i in m3['items'] if i['id'] == pid)['price'].get('value') == 77.77, bloecke(m3)[:2])
    # Veröffentlichen-Dialog: „Rückgängig“ beim Aufbau setzt Reihenfolge und Bereiche auf den veröffentlichten Stand
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open] [data-rv="aufbau"]')
    a.click('#dlg-publish [data-rv="aufbau"]'); a.wait_for_selector('#dlg-confirm[open]')
    check('Rücknahme fragt nach („Aufbau zurücknehmen?“)', 'Aufbau zurücknehmen?' in a.inner_text('#dlg-confirm'))
    a.click('#dlg-confirm [data-v="1"]'); a.wait_for_selector('#toast.show:has-text("Änderung zurückgenommen")'); gespeichert(a)
    check('Aufbau zurückgenommen: wieder wie veröffentlicht, Abschnitt „Aufbau“ entfällt', bloecke(entwurf(A)[0]) == B1
          and a.locator('#dlg-publish [data-rv="aufbau"]').count() == 0, [b for b, _ in bloecke(entwurf(A)[0])])
    a.click('#dlg-publish [data-close]'); a.wait_for_selector('#dlg-publish', state='hidden')

    # ---------- Kundenangebote ----------
    a.locator(f'#offer-bar [data-offer="{FOLGT}"]').first.click()
    a.wait_for_function("document.querySelector('#btn-aufbau').classList.contains('gesperrt')")
    check('folgt dem Wochenangebot: Knopf sichtbar, gekennzeichnet, Hinweis im Titel', a.locator('#btn-aufbau').is_visible() and 'folgt dem Wochenangebot' in (a.get_attribute('#btn-aufbau', 'title') or ''))
    oeffnen(a)
    check('folgt dem Wochenangebot: Fenster nur zum Ansehen mit Hinweis, ohne Pfeile, Griffe und „Übernehmen“',
          'folgt dem Wochenangebot und übernimmt dessen Aufbau' in a.inner_text('#dlg-aufbau') and a.locator('#abf-liste [data-griff], #abf-liste [data-ab*="hoch"], #abf-liste [data-ab*="runter"], #abf-ok').count() == 0
          and a.locator('#abf-liste .abf-g').count() > 0)
    a.locator('#abf-liste .abf-g [data-ab="g-auf"]').first.click()
    check('folgt dem Wochenangebot: Artikel aufklappbar, aber ohne Griff, Pfeile und „In Gruppe …“', a.locator('#abf-liste .abf-a[data-aid]').count() > 0
          and a.locator('#abf-liste .abf-a [data-griff], #abf-liste .abf-a select, #abf-liste .abf-a [data-ab]').count() == 0)
    shot(a.locator('#dlg-aufbau'), SH + '/aufbau-folgt.png')
    a.click('#dlg-aufbau .dlg-foot [data-close]'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    a.locator(f'#offer-bar [data-offer="{EIGEN}"]').first.click()
    a.wait_for_function("!document.querySelector('#btn-aufbau').classList.contains('gesperrt')")
    oeffnen(a)
    mvor, _ = entwurf(A)
    fe = fenster(a)
    check('eigene Artikelliste: Fenster zeigt nur die Gruppen dieses Angebots', fe == bloecke(mvor, EIGEN) and len(flach(fe)) == 3, fe)
    a.locator('#abf-liste > .abf-ber').last.locator('.abf-bk [data-ab="b-hoch"]').click()
    neu = flach(fenster(a))
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    m4, _ = entwurf(A)
    check('eigene Artikelliste: Reihenfolge gespeichert (gilt für alle Angebote), übrige Gruppen bleiben bei ihrem Vorgänger',
          flach(bloecke(m4, EIGEN)) == neu and set(gruppen_reihe(m4)) == set(gruppen_reihe(mvor)) and len(gruppen_reihe(m4)) == len(gruppen_reihe(mvor)))
    dr = A.call(f'offer&draft=1&angebot={EIGEN}')[1]['offer']
    check('Kundenangebot (Vorschau): Gruppen in neuer Reihenfolge, Kundenpreis aufgelöst', [g['id'] for g in dr['groups']] == neu
          and all(i['price'].get('value') == 12.5 for i in dr['items']))
    a.locator('#offer-bar [data-offer="std"]').first.click()
    a.wait_for_selector('#btn-aufbau:not(.gesperrt)')
    check('keine Skriptfehler (Bearbeiter)', not errors, errors[:3])

    # ---------- Artikel: aufklappen, umsortieren, verschieben ----------
    m5, rev5 = entwurf(A)
    F = flach(bloecke(m5))
    anz = {g: len(art_reihe(m5, g)) for g in F}
    k = next(i for i in range(1, len(F) - 1) if anz[F[i]] >= 6 and anz[F[i + 1]] >= 3)
    GA, GB, GZ = F[k], F[k + 1], F[k - 1]   # GZ steht über GA (Ziehen nach oben auf eine zugeklappte Gruppe)
    GS = next(g for g in reversed(F) if g not in (GA, GB, GZ))
    gname = {g['id']: g['name'] for g in m5['groups']}
    oeffnen(a)
    check('Artikel: Gruppen zugeklappt, keine Artikelzeilen', a.locator('#abf-liste .abf-a').count() == 0
          and a.locator('#abf-liste .abf-art:not([hidden])').count() == 0 and a.locator('#abf-liste [data-ab="g-auf"][aria-expanded="false"]').count() == len(F))
    auf = f'#abf-liste .abf-g[data-gid="{GA}"] [data-ab="g-auf"]'
    a.click(auf)
    erstes = next(i for i in m5['items'] if i['id'] == art_reihe(m5, GA)[0])
    zeile = a.locator(f'#abf-liste .abf-a[data-aid="{erstes["id"]}"]')
    check('Klick auf die Gruppe klappt sie auf: Artikel mit Art.-Nr. und Bezeichnung in Reihenfolge', dlg_art(a, GA) == art_reihe(m5, GA)
          and a.get_attribute(auf, 'aria-expanded') == 'true' and (erstes['code'] or '') in zeile.inner_text() and erstes['name'] in zeile.inner_text())
    a.click(auf)
    check('erneuter Klick klappt zu', a.locator(f'#abf-liste .abf-g[data-gid="{GA}"] .abf-art').is_hidden() and a.get_attribute(auf, 'aria-expanded') == 'false')
    a.click('#abf-alle')
    gesamt = sum(anz.values())
    check('„Alle Artikel zeigen“ klappt alle Gruppen auf', a.locator('#abf-liste .abf-a[data-aid]').count() == gesamt and 'ausblenden' in a.inner_text('#abf-alle'), gesamt)
    a.click('#abf-alle')
    check('… und wieder zu', a.locator('#abf-liste .abf-a').count() == 0)
    a.click(auf)
    ga = art_reihe(m5, GA)
    a.click(f'#abf-liste .abf-a[data-aid="{ga[1]}"] [data-ab="a-hoch"]')
    check('Pfeil: Artikel innerhalb der Gruppe nach oben, Fokus bleibt', dlg_art(a, GA)[:2] == [ga[1], ga[0]]
          and a.evaluate("document.activeElement.dataset.ab") == 'a-runter' and a.evaluate("document.activeElement.closest('.abf-a').dataset.aid") == ga[1],
          (dlg_art(a, GA)[:2], a.evaluate("document.activeElement.dataset.ab")))   # ganz oben: Fokus auf den anderen Pfeil
    a.select_option(f'#abf-liste .abf-a[data-aid="{ga[2]}"] select', GS)
    check('Auswahl „In Gruppe …“: Artikel ans Ende der gewählten Gruppe, Zahlen aktualisiert, Meldung',
          ga[2] not in dlg_art(a, GA) and f'{anz[GA] - 1} Artikel' in a.inner_text(f'#abf-liste .abf-g[data-gid="{GA}"] > .abf-gk .abf-z')
          and f'{anz[GS] + 1} Artikel' in a.inner_text(f'#abf-liste .abf-g[data-gid="{GS}"] > .abf-gk .abf-z') and 'ans Ende von' in a.inner_text('#abf-stand'))
    a.click(f'#abf-liste .abf-g[data-gid="{GS}"] [data-ab="g-auf"]')
    check('… dort am Ende, gekennzeichnet „verschoben“', dlg_art(a, GS)[-1] == ga[2] and 'verschoben' in a.inner_text(f'#abf-liste .abf-a[data-aid="{ga[2]}"]').lower())
    a.click('#dlg-aufbau .dlg-foot [data-close]'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    check('Abbrechen: Artikel unverändert, nichts gespeichert', entwurf(A)[1] == rev5)

    a.set_viewport_size({'width': 1440, 'height': 3200})   # aufgeklappte Gruppen ganz sichtbar (Ziehen ohne Rollen)
    oeffnen(a)
    a.click(f'#abf-liste .abf-g[data-gid="{GA}"] [data-ab="g-auf"]'); a.click(f'#abf-liste .abf-g[data-gid="{GB}"] [data-ab="g-auf"]')
    ga, gb, gz, gs = art_reihe(m5, GA), art_reihe(m5, GB), art_reihe(m5, GZ), art_reihe(m5, GS)
    a.click(f'#abf-liste .abf-a[data-aid="{ga[1]}"] [data-ab="a-hoch"]')
    ea = [ga[1], ga[0]] + ga[2:]
    ziehen(a, f'#abf-liste .abf-a[data-aid="{ga[4]}"] [data-griff="a"]', f'#abf-liste .abf-a[data-aid="{ea[0]}"]')
    ea = [ga[4]] + [x for x in ea if x != ga[4]]
    check('Ziehen: Artikel innerhalb der Gruppe an den Anfang', dlg_art(a, GA) == ea, dlg_art(a, GA)[:5])
    ziehen(a, f'#abf-liste .abf-a[data-aid="{gb[2]}"] [data-griff="a"]', f'#abf-liste .abf-a[data-aid="{ea[1]}"]')
    ea = [ea[0], gb[2]] + ea[1:]
    eb = [x for x in gb if x != gb[2]]
    check('Ziehen: Artikel in eine andere (aufgeklappte) Gruppe an die Stelle, „verschoben“', dlg_art(a, GA) == ea and dlg_art(a, GB) == eb
          and 'verschoben' in a.inner_text(f'#abf-liste .abf-a[data-aid="{gb[2]}"]').lower(), (dlg_art(a, GA)[:4], dlg_art(a, GB)[:4]))
    letzter = ea[-1]
    ziehen(a, f'#abf-liste .abf-a[data-aid="{letzter}"] [data-griff="a"]', f'#abf-liste .abf-g[data-gid="{GZ}"] > .abf-gk')
    ea = ea[:-1]
    ez = gz + [letzter]
    check('Ziehen auf eine zugeklappte Gruppe: Artikel an deren Ende, Zahl aktualisiert', dlg_art(a, GA) == ea
          and f'{len(ez)} Artikel' in a.inner_text(f'#abf-liste .abf-g[data-gid="{GZ}"] > .abf-gk .abf-z') and a.locator('#abf-liste .abf-ziel').count() == 0)
    a.select_option(f'#abf-liste .abf-a[data-aid="{ea[3]}"] select', GS)
    es = gs + [ea[3]]
    ea = ea[:3] + ea[4:]
    shot(a.locator('#dlg-aufbau'), SH + '/artikel-fenster.png')
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    m6, rev6 = entwurf(A)
    check('Übernehmen: Artikelreihenfolge und Gruppen im Entwurf wie im Fenster (eine Speicherung)', rev6 == rev5 + 1 and art_reihe(m6, GA) == ea and art_reihe(m6, GB) == eb
          and art_reihe(m6, GZ) == ez and art_reihe(m6, GS) == es, (rev5, rev6))
    vorher = {i['id']: i for i in m5['items']}
    gew = {gb[2]: GA, letzter: GZ, es[-1]: GS}
    check('nur die verschobenen Artikel wechseln die Gruppe, Preise und Angebote unverändert',
          all(i['groupId'] == gew.get(i['id'], vorher[i['id']]['groupId']) and i['price'] == vorher[i['id']]['price']
              and i.get('variants') == vorher[i['id']].get('variants') for i in m6['items']) and len(m6['items']) == len(m5['items']))
    check('Gruppenreihenfolge unverändert', gruppen_reihe(m6) == gruppen_reihe(m5))
    ed = a.eval_on_selector_all(f'#groups section.gcard[data-gid="{GA}"] tr[data-id]', 'xs => xs.map(x => x.dataset.id)')
    check('Editor zeigt die Artikel in neuer Reihenfolge', ed == ea, ed[:4])
    check('Protokoll: Gruppe bei 3 Artikeln neu', 'Gruppe bei 3 Artikeln neu' in json.dumps(A.call('log')[1], ensure_ascii=False))
    a.set_viewport_size({'width': 1440, 'height': 950})
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    check('Veröffentlichen nennt den Aufbau', 'Reihenfolge der Bereiche, Gruppen oder Artikel geändert' in a.inner_text('#dlg-publish'))
    a.click('[data-ia=publish]'); a.wait_for_function("!document.querySelector('#dlg-publish').open", timeout=15000)
    m7, _ = entwurf(A)
    pub = Client('198.51.100.9').call('offer')[1]['offer']
    check('veröffentlicht: öffentliche Seite liefert die Artikel in neuer Reihenfolge und Gruppe', angebot_reihe(pub) == angebot_reihe(m7, 'std')
          and next(i for i in pub['items'] if i['id'] == gb[2])['groupId'] == GA)
    s = br.new_page(viewport={'width': 1440, 'height': 950})
    s.on('pageerror', lambda e: errors.append(str(e)))
    s.goto(BASE + '/'); s.wait_for_selector('.al tr.row[data-id]')
    liste = s.eval_on_selector_all('.al .al-sec:not(.werb-sec) tr.row[data-id]', 'xs => xs.map(x => x.dataset.id)')
    check('Angebotsseite (Angebotsansicht wie Druck/PDF): Artikel in neuer Reihenfolge', liste == angebot_reihe(m7, 'std'), liste[:5])
    s.goto(BASE + '/#ansicht=tabelle'); s.reload(); s.wait_for_selector('table.grid tr.row[data-id]')
    tab = s.eval_on_selector_all('table.grid tr.row[data-id]', 'xs => xs.map(x => x.dataset.id)')
    check('Angebotsseite (Tabelle): Artikel in neuer Reihenfolge', tab == angebot_reihe(m7, 'std'), tab[:5])
    s.close()
    kd = A.call(f'offer&angebot={EIGEN}')[1]['offer']
    check('Kundenangebot (veröffentlicht): Artikel in Reihenfolge des Aufbaus', angebot_reihe(kd) == angebot_reihe(m7, EIGEN), angebot_reihe(kd))
    # Konflikt: ein anderer verschiebt inzwischen einen Artikel
    oeffnen(a)
    a.click(f'#abf-liste .abf-g[data-gid="{GA}"] [data-ab="g-auf"]')
    me, mrev = entwurf(E)
    wandert = art_reihe(me, GA)[-1]
    next(i for i in me['items'] if i['id'] == wandert)['groupId'] = GB
    assert E.call('save_draft', {'model': me, 'revision': mrev})[0] == 200
    E_A = art_reihe(entwurf(A)[0], GA)
    a.click(f'#abf-liste .abf-a[data-aid="{ea[0]}"] [data-ab="a-runter"]')
    a.click('#abf-ok'); a.wait_for_selector('#abf-err:has-text("inzwischen geändert")')
    check('Konflikt bei Artikeln: nichts übernommen, Fenster zeigt den neuen Stand', art_reihe(entwurf(A)[0], GA) == E_A and wandert not in E_A
          and dlg_art(a, GA) == E_A and a.locator('#dlg-aufbau[open]').count() == 1, (E_A[:3], dlg_art(a, GA)[:3]))
    a.click('#dlg-aufbau .dlg-foot [data-close]'); a.wait_for_selector('#dlg-aufbau', state='hidden')
    check('keine Skriptfehler (Artikel)', not errors, errors[:3])

    # ---------- Ohne Bearbeitungsrecht: kein Knopf, Server 403 ----------
    lp = br.new_page(viewport={'width': 1440, 'height': 950})
    lp.on('pageerror', lambda e: errors.append(str(e)))
    login(lp, 'lea', PW_L)
    check('Leser: kein Knopf „Editor“ (Werbung nur ansehen bleibt)', lp.locator('#btn-aufbau').is_hidden() and lp.locator('#btn-werbung').is_visible())
    ml, rl = entwurf(L)
    st, r = L.call('save_draft', {'model': ml, 'revision': rl, 'note': {'type': 'aufbau'}})
    check('Leser: Speichern des Aufbaus vom Server abgewiesen (403, fehlende Berechtigung)', st == 403 and 'Berechtigung' in (r.get('error') or ''), (st, r))
    check('ohne Anmeldung: 401', Client('198.51.100.8').call('save_draft', {'model': ml, 'revision': rl, 'note': {'type': 'aufbau'}})[0] == 401)
    lp.close()

    # ---------- Handy 390 px, hell und dunkel; Touch-Ziehen ----------
    for schema in ('light', 'dark'):
        mc = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2, color_scheme=schema)
        mp = mc.new_page()
        mp.on('pageerror', lambda e: errors.append(str(e)))
        login(mp, 'eddi', PW_E)
        mk = mp.locator('#btn-aufbau')
        mk.scroll_into_view_if_needed()
        kb = mk.bounding_box()
        sw = mp.evaluate('document.documentElement.scrollWidth')
        check(f'390 px {schema}: Knopf in der Leiste, ganz sichtbar, kein waagerechtes Scrollen', mk.is_visible() and kb['x'] >= 0 and kb['x'] + kb['width'] <= 390 and sw <= 390, (kb, sw))
        if schema == 'dark':
            f = mp.evaluate("[getComputedStyle(document.querySelector('#btn-aufbau')).color, getComputedStyle(document.querySelector('#btn-aufbau')).backgroundColor]")
            check('dunkel: heller blauer Text auf getönter Fläche', f[0] == 'rgb(138, 184, 228)' and f[1] == 'rgba(138, 184, 228, 0.12)', f)
        shot(mp.locator('.ed-toolbar'), SH + f'/aufbau-leiste-390-{schema}.png')
        oeffnen(mp)
        w = mp.evaluate("(() => { const d = document.querySelector('#dlg-aufbau'); return [d.scrollWidth, d.clientWidth, Math.min(...[...d.querySelectorAll('#abf-liste .ibtn')].map(b => b.getBoundingClientRect().height))]; })()")
        check(f'390 px {schema}: Fenster ohne waagerechtes Scrollen, Pfeile mindestens 36 px', w[0] <= w[1] and w[2] >= 36, w)
        shot(mp, SH + f'/aufbau-fenster-390-{schema}.png')
        if schema == 'light':
            cdp = mc.new_cdp_session(mp)
            vor = fenster(mp)
            g = vor[0][1]
            touch_ziehen(mp, cdp, f'#abf-liste .abf-g[data-gid="{g[1]}"] [data-griff="g"]', f'#abf-liste .abf-g[data-gid="{g[0]}"]')
            nach = fenster(mp)
            check('Touch: Gruppe am Griff ziehen', nach[0][1][:2] == [g[1], g[0]] and nach[1:] == vor[1:], nach[0][1][:3])
            g0 = nach[0][1][0]
            mp.click(f'#abf-liste .abf-g[data-gid="{g0}"] [data-ab="g-auf"]')
            av = dlg_art(mp, g0)
            touch_ziehen(mp, cdp, f'#abf-liste .abf-a[data-aid="{av[2]}"] [data-griff="a"]', f'#abf-liste .abf-a[data-aid="{av[0]}"]')
            check('Touch: Artikel am Griff ziehen', dlg_art(mp, g0)[:3] == [av[2], av[0], av[1]], dlg_art(mp, g0)[:3])
            ziel = nach[-1][1][-1]
            mp.select_option(f'#abf-liste .abf-a[data-aid="{av[1]}"] select', ziel)
            w = mp.evaluate("(() => { const d = document.querySelector('#dlg-aufbau'); const s = [...d.querySelectorAll('#abf-liste .abf-zu')]; return [d.scrollWidth, d.clientWidth, Math.min(...s.map(x => x.getBoundingClientRect().height)), Math.max(...s.map(x => x.getBoundingClientRect().right))]; })()")
            check('390 px: Auswahl „In Gruppe …“ verschiebt, eigene Zeile mit 36 px, nichts ragt heraus', av[1] not in dlg_art(mp, g0) and w[0] <= w[1] and w[2] >= 36 and w[3] <= 390, w)
            shot(mp, SH + '/artikel-390.png')
        mp.click('#dlg-aufbau .dlg-foot [data-close]')
        mc.close()

    # ---------- Angebotskategorien der Stammdaten: Reihenfolge kommt von dort, Fenster nur zum Ansehen ----------
    kr = A.call('angebotskategorien')[1]['rev']
    assert A.call('angebotskategorien_save', {'rev': kr, 'kategorien': [{'name': 'Testkategorie', 'vk': []}]})[0] == 200
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.wait_for_function("(document.querySelector('#btn-aufbau').title || '').includes('Angebotskategorien')")
    check('Angebotskategorien: Hinweis im Titel des Knopfs', a.locator('#btn-aufbau.gesperrt').count() == 0)
    oeffnen(a)
    check('Angebotskategorien: Bereiche und Gruppen fest (Hinweis auf Verwaltung → Angebotskategorien), „Übernehmen“ da',
          'Verwaltung → Angebotskategorien' in a.inner_text('#dlg-aufbau') and a.locator('#abf-liste [data-griff="b"], #abf-liste [data-griff="g"], #abf-liste [data-ab^="b-"], #abf-liste [data-ab="g-hoch"], #abf-liste [data-ab="g-runter"]').count() == 0
          and a.locator('#abf-ok').count() == 1)
    a.wait_for_function("!/pending|saving/.test(document.querySelector('#save-state').className)")   # Ordnen nach Kategorien gespeichert
    mk, rk = entwurf(A)
    g0 = fenster(a)[0][1][0]
    a.click(f'#abf-liste .abf-g[data-gid="{g0}"] [data-ab="g-auf"]')
    av = dlg_art(a, g0)
    a.click(f'#abf-liste .abf-a[data-aid="{av[0]}"] [data-ab="a-runter"]')
    a.click('#abf-ok'); a.wait_for_selector('#dlg-aufbau', state='hidden'); gespeichert(a)
    mk2, _ = entwurf(A)
    check('Angebotskategorien: Artikel lassen sich verschieben, Gruppen bleiben in der Reihenfolge der Kategorien',
          art_reihe(mk2, g0)[:2] == [av[1], av[0]] and gruppen_reihe(mk2) == gruppen_reihe(mk), art_reihe(mk2, g0)[:3])
    check('keine Skriptfehler', not errors, errors[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
