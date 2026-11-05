"""Angebotskategorien (Stammdaten der Verwaltung, Inhaber 05.11.2026): Schnittstelle (Rechte – Lesen auch mit
angebot.bearbeiten, Ändern nur mit stammdaten.bearbeiten –, Prüfungen, Revision, Protokoll), Ansicht Verwaltung →
Angebotskategorien (Vorschlag aus dem Wochenangebot, Reihenfolge, Zuordnen, Speichern, Nur-Ansicht, 390 px) und der Aufbau
des Angebots danach (Editor: Reihenfolge und Abschnitte aus den Stammdaten, VK-Gruppe der Angebotsgruppe statt „Bereich“
und ↑/↓, Gruppen ohne Kategorie am Ende; ohne Kategorien unverändert). Nur Testdaten (Seed-Angebot)."""
import json
import sys
import time

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, storage_raw

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


SEK = ['Eigene Zerlegung, Marke "Fleischmeister"', 'Rindfleisch, Kalbfleisch, Charoluxe, Schweinefleisch, Geflügel, Lammfleisch aus Neuseeland',
       'Südamerika, Australien, Grain Fed, Schwein, Lammfleisch aus Irland', 'Geflügel, Lamm, Gefrierfleisch']
VK = [{'nr': '1050', 'name': 'Färse HV 4xD Fleischmeister'}, {'nr': '1910', 'name': 'Neuseeland Prime Steer'},
      {'nr': '1810', 'name': 'Argentinien frisch'}, {'nr': '1990', 'name': 'Lamm Neuseeland gefroren'}, {'nr': '4100', 'name': 'Geflügel frisch'}]
ART = {'10601': '1050', '10674': '1910', '10635': '1810', '80025': '1990'}   # je ein Artikel aus vier Abschnitten des Seed-Angebots

A = Client('198.51.100.2')
assert A.call('login', {'username': 'admin', 'password': PW})[0] == 200
A.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
E = Client('198.51.100.3'); assert E.call('login', {'username': 'eddi', 'password': 'Editor-Zugang-77'})[0] == 200
L = Client('198.51.100.4'); assert L.call('login', {'username': 'lea', 'password': 'Leserin-Zugang-1'})[0] == 200
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}
assert A.call('vkgruppen_save', {'rev': A.call('vkgruppen')[1]['rev'], 'groups': VK})[0] == 200

# ---------- Schnittstelle ----------
check('ohne Anmeldung gesperrt', Client().call('angebotskategorien')[0] == 401)
st, r = L.call('angebotskategorien')
check('Leser darf ansehen (leer, mit Namen der VK-Gruppen)', st == 200 and r['kategorien'] == [] and r['rev'] == 0 and {g['nr'] for g in r['vk']} == {g['nr'] for g in VK}, r)
check('Leser darf nicht speichern', L.call('angebotskategorien_save', {'rev': 0, 'kategorien': []})[0] == 403)
check('Speichern nur per POST', E.call('angebotskategorien_save')[0] == 405)
check('Bezeichnung fehlt: abgewiesen', E.call('angebotskategorien_save', {'rev': 0, 'kategorien': [{'name': ' ', 'vk': []}]})[0] == 422)
check('doppelte Bezeichnung: abgewiesen', E.call('angebotskategorien_save', {'rev': 0, 'kategorien': [{'name': 'Rind', 'vk': []}, {'name': 'rind', 'vk': []}]})[0] == 422)
st, r = E.call('angebotskategorien_save', {'rev': 0, 'kategorien': [{'name': 'A', 'vk': ['1050']}, {'name': 'B', 'vk': ['1050']}]})
check('VK-Gruppe in zwei Kategorien: abgewiesen mit Hinweis', st == 422 and '1050' in r.get('error', ''), r)
check('ungültige VK-Gruppe: abgewiesen', E.call('angebotskategorien_save', {'rev': 0, 'kategorien': [{'name': 'A', 'vk': ['10 50']}]})[0] == 422)
st, r = E.call('angebotskategorien_save', {'rev': 0, 'kategorien': [{'name': 'Lamm', 'vk': ['1990']}, {'id': 'x y', 'name': '  Rind   frisch ', 'vk': [1050, '1910']}]})
check('Bearbeiter speichert: Reihenfolge bleibt, Zahlen als Text, Leerzeichen bereinigt, ungültige ID ersetzt', st == 200 and r['rev'] == 1
      and [k['name'] for k in r['kategorien']] == ['Lamm', 'Rind frisch'] and r['kategorien'][1]['vk'] == ['1050', '1910'] and r['kategorien'][1]['id'] != 'x y', r)
check('veraltete Revision: 409', E.call('angebotskategorien_save', {'rev': 0, 'kategorien': []})[0] == 409)
check('gespeichert im eigenen Dokument', doc('angebotskategorien')['rev'] == 1 and len(doc('angebotskategorien')['kategorien']) == 2)
check('Protokoll: Angebotskategorien gespeichert', 'Angebotskategorien gespeichert: 2 Kategorien, 3 VK-Gruppen' in json.dumps(A.call('log')[1], ensure_ascii=False))
A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': ['stammdaten.sehen', 'stammdaten.bearbeiten']})
check('Angebotsbearbeiter ohne Stammdatenrecht darf lesen (Editor ordnet danach), aber nicht speichern',
      E.call('angebotskategorien')[0] == 200 and E.call('angebotskategorien_save', {'rev': 1, 'kategorien': []})[0] == 403)
A.call('user_save', {'id': uid['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': [], 'deny': ['stammdaten.sehen']})
check('ohne Stammdaten- und Angebotsrecht: kein Zugriff', L.call('angebotskategorien')[0] == 403)
A.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': []})
A.call('user_save', {'id': uid['lea'], 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'grant': [], 'deny': []})
assert A.call('angebotskategorien_save', {'rev': 1, 'kategorien': []})[0] == 200   # für die Oberfläche: ohne Kategorien beginnen

# VK-Gruppen einiger Artikel in den Artikelstammdaten (der Editor ermittelt daraus die VK-Gruppe der Angebotsgruppe)
m = A.call('master')[1]['master']
arts = [{'code': c, 'name': f'Testartikel {c}', 'category': 'Rind', 'origin': None, 'condition': 'frisch', 'vkGruppe': v} for c, v in ART.items()]
assert A.call('master_save', {'rev': m['rev'], 'articles': arts})[0] == 200

errors = []


def gsec(pg):
    return pg.eval_on_selector_all('#groups .gsec', 'hs => hs.map(h => h.textContent.trim())')


with sync_playwright() as p:
    br = p.chromium.launch()
    a = br.new_page(viewport={'width': 1440, 'height': 950})
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.wait_for_selector('#groups .gcard [data-act="g-up"]')
    check('ohne Kategorien unverändert: Bereich frei, Gruppen mit ↑/↓, Abschnitte wie bisher',
          a.locator('#groups [data-gf="section"]').count() > 0 and a.locator('#groups [data-gf="vk"]').count() == 0 and gsec(a)[:4] == SEK, gsec(a)[:4])
    y = lambda s: a.locator(s).bounding_box()['y']   # noqa: E731
    check('Navigation: Angebotskategorien unter Stammdaten nach den VK-Gruppen', a.locator('#vt-kategorien').is_visible() and y('#vt-vkgruppen') < y('#vt-kategorien') < y('#vt-kunden'))

    # ---------- Ansicht: Vorschlag aus dem Wochenangebot ----------
    a.click('#vt-kategorien'); a.wait_for_selector('#view-kategorien .ed-empty')
    check('leer: Hinweis und Vorschlag-Knopf', 'Noch keine Angebotskategorien' in a.inner_text('#view-kategorien') and a.locator('#ak-vorschlag').count() == 1
          and a.locator('#ak-freiliste li[data-v]').count() == len(VK))
    a.click('#ak-vorschlag'); a.wait_for_selector('#view-kategorien .ak-kat')
    namen = a.eval_on_selector_all('.ak-kat [data-ak="name"]', 'xs => xs.map(x => x.value)')
    vks = a.eval_on_selector_all('.ak-kat', 'ks => ks.map(k => [...k.querySelectorAll(".ak-vks li[data-v]")].map(l => l.dataset.v))')
    check('Vorschlag: heutige Abschnitte in ihrer Reihenfolge, VK-Gruppen aus den Artikeln', namen == SEK and vks == [['1050'], ['1910'], ['1810'], ['1990']], (namen, vks))
    check('Vorschlag noch nicht gespeichert', 'nicht gespeichert' in a.inner_text('#ak-stand') and doc('angebotskategorien')['kategorien'] == [])
    a.screenshot(path=SH + '/angebotskategorien-vorschlag.png', full_page=True)
    # letzte Kategorie nach ganz oben, Geflügel (4100) zu „Geflügel, Lamm, Gefrierfleisch“, dann speichern
    for n in range(3, 0, -1):
        a.locator('.ak-kat').nth(n).locator('[data-ak="k-hoch"]').click()
    namen = a.eval_on_selector_all('.ak-kat [data-ak="name"]', 'xs => xs.map(x => x.value)')
    check('Reihenfolge der Kategorien änderbar', namen == [SEK[3], SEK[0], SEK[1], SEK[2]], namen)
    a.select_option('#ak-freiliste li[data-v="4100"] [data-ak="zu"]', '0')
    vk0 = a.locator('.ak-kat').first.locator('.ak-vks li[data-v]').evaluate_all('ls => ls.map(l => l.dataset.v)')
    check('VK-Gruppe ohne Kategorie zuordnen', vk0 == ['1990', '4100'] and a.locator('#ak-freiliste li[data-v="4100"]').count() == 0, vk0)
    a.locator('.ak-kat').first.locator('li[data-v="4100"] [data-ak="v-hoch"]').click()
    vk0 = a.locator('.ak-kat').first.locator('.ak-vks li[data-v]').evaluate_all('ls => ls.map(l => l.dataset.v)')
    check('Reihenfolge der VK-Gruppen änderbar', vk0 == ['4100', '1990'], vk0)
    a.click('#ak-speichern'); a.wait_for_selector('#toast.show:has-text("Angebotskategorien gespeichert")')
    d = doc('angebotskategorien')
    check('gespeichert', [k['name'] for k in d['kategorien']] == [SEK[3], SEK[0], SEK[1], SEK[2]] and d['kategorien'][0]['vk'] == ['4100', '1990'], d)
    a.screenshot(path=SH + '/angebotskategorien.png', full_page=True)
    ende = time.time() + 10   # der Entwurf wird im Hintergrund geordnet und gespeichert (danach fasst das Protokoll weitere Änderungen zusammen)
    while 'nach den Angebotskategorien geordnet' not in json.dumps(A.call('log')[1], ensure_ascii=False) and time.time() < ende:
        time.sleep(0.3)
    check('Protokoll: Angebot nach den Angebotskategorien geordnet', 'nach den Angebotskategorien geordnet' in json.dumps(A.call('log')[1], ensure_ascii=False))

    # ---------- Editor: Aufbau nach den Kategorien ----------
    a.click('#vt-edit'); a.wait_for_selector('#groups [data-gf="vk"]')
    s = gsec(a)
    check('Editor: Abschnitte in der Reihenfolge der Kategorien, Gruppen ohne Kategorie am Ende', s == [SEK[3], SEK[0], SEK[1], SEK[2], 'Ohne Angebotskategorie'], s)
    check('Editor: VK-Gruppe statt Bereich, keine ↑/↓ an den Gruppen', a.locator('#groups [data-gf="section"]').count() == 0 and a.locator('#groups [data-act="g-up"]').count() == 0
          and a.locator('#groups .g-kat-ohne').count() >= 1)
    g1 = a.locator('#groups section.gcard:has(input[data-f="code"][value="10601"])').first
    check('Editor: VK-Gruppe der Gruppe aus ihren Artikeln ermittelt', g1.locator('[data-gf="vk"]').input_value() == '1050')
    a.screenshot(path=SH + '/angebotskategorien-editor.png')
    # Gruppe ohne Kategorie: VK-Gruppe wählen → rückt in die Kategorie
    ohne = a.locator('#groups section.gcard:has(.g-kat-ohne)').first
    gid = ohne.get_attribute('data-gid')
    ohne.locator('[data-gf="vk"]').select_option('1910')
    a.wait_for_function("gid => { const s = document.querySelector(`#groups section.gcard[data-gid='${gid}']`); return s && !s.querySelector('.g-kat-ohne'); }", arg=gid)
    vor = a.evaluate("gid => { let h = null; for (const el of document.querySelectorAll('#groups > *')) { if (el.matches('.gsec')) h = el.textContent.trim(); if (el.dataset && el.dataset.gid === gid) return h; } return null; }", gid)
    check('Editor: Gruppe ohne Kategorie bekommt per VK-Gruppe ihren Platz', vor == SEK[1], vor)
    ende = time.time() + 10
    while True:
        dr = A.call('draft')[1]['draft']
        gs = [g for g in dr['groups'] if g['id'] == gid]
        if (gs and gs[0].get('vk') == '1910') or time.time() > ende: break
        time.sleep(0.3)
    secs = []
    for g in dr['groups']:
        if g.get('section') and g['section'] not in secs: secs.append(g['section'])
    ids = [g['id'] for g in dr['groups']]
    reihe = [ids.index(it['groupId']) for it in dr['items']]
    check('Entwurf gespeichert: Abschnitte = Kategorien in ihrer Reihenfolge, Artikel in Gruppenreihenfolge, VK-Gruppe gemerkt',
          secs == [SEK[3], SEK[0], SEK[1], SEK[2]] and reihe == sorted(reihe) and gs and gs[0].get('vk') == '1910', (secs, gs[:1]))

    # ---------- Nur-Ansicht und Handy ----------
    l = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    l.on('pageerror', lambda e: errors.append(str(e)))
    l.goto(BASE + '/admin/'); l.wait_for_selector('#screen-auth:not([hidden])')
    l.fill('#au-user', 'lea'); l.fill('#pw1', 'Leserin-Zugang-1'); l.click('#auth-submit'); l.wait_for_selector('#screen-editor:not([hidden])')
    l.evaluate("window.WA.setView('kategorien')"); l.wait_for_selector('#view-kategorien .ak-kat')
    check('Leser: Kategorien sichtbar, nichts änderbar', l.locator('#view-kategorien .ak-kat').count() == 4 and l.locator('#ak-speichern').count() == 0
          and l.locator('#view-kategorien input[data-ak], #view-kategorien select').count() == 0)
    sw = l.evaluate('document.documentElement.scrollWidth')
    check('390 px: kein waagerechtes Scrollen', sw <= 390, sw)
    l.screenshot(path=SH + '/angebotskategorien-390.png', full_page=True)
    l.close()
    check('keine Skriptfehler', not errors, errors[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
