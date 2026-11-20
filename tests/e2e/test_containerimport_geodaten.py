"""Container-Import · EUDR: Geodaten-Katalog GEOS-EUDR des Thünen-Instituts (Aktion containerimport_eudr_geodaten,
Datei app/api/module/containerimport/geodatenkatalog.json, Oberfläche app/module/containerimport/eudr-geodaten.js).
Geprüft: Rechte (ohne Anmeldung 401, ohne „EUDR ansehen“ 403, Leserolle sieht ihn), Inhalt (22 Einträge FNF01–FNF22,
Quelle, Lizenz MIT, Fassung und Zitiervorschlag); Ansicht mit Suche, aufklappbarem Eintrag und offen bleibenden Einträgen
beim Neuzeichnen; Verweise „FNF01“/„FNF17“ unter der Karte öffnen den richtigen Eintrag im Fenster; Zuordnung der
Whisp-Felder zum Katalog (nur eindeutige Produkte) und Katalog-ID mit Fassung im Text der Gegenprüfung (auch bei langem
Text vollständig, höchstens 500 Zeichen); fremde Texte maskiert, Verweise nur mit http(s); Handy 390 px ohne waagerechtes
Scrollen. Bildauswertung und Whisp-Ergebnis mit Verweis prüfen die Gruppen containerimport und containerimport_whisp.
Testdaten: der eingecheckte Katalog (öffentliche Metadaten); Nutzer erfunden."""
import json
import os
import re
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, seite as seite_oeffnen
from kunden_hilfe import Client
from umgebung import SH, shot

A, I, L = nutzer_anlegen()
A.call('user_save', {'id': '', 'name': 'Ole Ohne', 'username': 'ole', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
O = Client('198.51.100.40')
assert O.call('login', {'username': 'ole', 'password': 'Editor-Zugang-77'})[0] == 200

# ---------- Rechte und Inhalt ----------
AKTION = 'containerimport_eudr_geodaten'
st, r = Client('198.51.100.41').call(AKTION)
check('ohne Anmeldung: kein Zugriff (401)', st == 401 and 'eintraege' not in r, (st, r))
st, r = O.call(AKTION)
check('Modulzugang ohne „EUDR ansehen“: 403, kein Katalog', st == 403 and 'eintraege' not in r, (st, r))
st, k = L.call(AKTION)
ids = [e['id'] for e in k.get('eintraege', [])]
check('nur ansehen: Katalog mit 22 Einträgen FNF01–FNF22', st == 200 and ids == ['FNF%02d' % n for n in range(1, 23)], (st, ids))
t = k['themen'][0]
check('Quelle, Lizenz MIT, Urheber, Fassung v1.0 mit Commit und Zitiervorschlag', k['quelle']['lizenz'] == 'MIT' and 'Thünen' in k['quelle']['urheber']
      and k['quelle']['url'] == 'https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR' and t['version'] == '1.0' and re.fullmatch(r'[0-9a-f]{7,40}', t['quelleCommit'] or '')
      and 'zenodo.org/records/20698510' in t['zitiervorschlag'], k['quelle'] | t)
e1 = next(e for e in k['eintraege'] if e['id'] == 'FNF01'); e17 = next(e for e in k['eintraege'] if e['id'] == 'FNF17')
check('FNF01 = JRC GFC 2020 (EUDR-konform ja, 10 m), FNF17 = Hansen/GFW (nein/unklar, 30 m, Hinweis abgetrennt)',
      e1['name'].startswith('JRC GFC 2020') and e1['eudrKonform'] == 'ja' and e1['aufloesungM'] == '10'
      and 'Hansen' in e17['name'] and e17['eudrKonform'] == 'nein_unklar' and e17['aufloesungM'] == '30' and e17['hinweis'].startswith('The dataset provides'), (e1['name'], e17['name']))
check('Verweise nur mit http(s); „NR“ bleibt erkennbar', all(re.match(r'https?://', l['url']) for e in k['eintraege'] for g in e['links'].values() for l in g)
      and any(e['genauigkeit']['oa'] == 'NR' for e in k['eintraege']))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        return seite_oeffnen(br, user, errs, fremd, vp, schema)

    def katalog_zeigen(p):
        p.click('[data-sicht="geodaten"]'); p.wait_for_selector('#ci-geodaten details')

    eintraege = "[...document.querySelectorAll('#ci-geodaten details')].map((d) => d.dataset.gd)"
    p = seite('lea')
    katalog_zeigen(p)
    check('Leserolle: Ansicht „Geodaten-Katalog“ mit 22 Einträgen, Quelle, Fassung und Zitiervorschlag', p.evaluate(eintraege) == ids
          and 'Fassung v1.0' in p.inner_text('.ci-gd-quelle') and 'Zitiervorschlag: Freitas Beyer' in p.inner_text('.ci-gd-quelle') and 'Lizenz MIT' in p.inner_text('.ci-gd-quelle'))
    zeile = p.inner_text('#ci-geodaten details[data-gd="FNF01"] summary')
    check('Eintrag kompakt: Kennung, Name, Hersteller, Auflösung, Jahre, EUDR-konform, Gesamtgenauigkeit', all(x in zeile for x in ('FNF01', 'JRC GFC 2020', 'Joint Research Centre', 'Auflösung 10 m', 'Jahre 2020', 'EUDR-konform', 'ja', 'Gesamtgenauigkeit')), zeile)
    check('EUDR-konform nein/unklar und „nicht berichtet“ ausgeschrieben', 'nein/unklar' in p.inner_text('#ci-geodaten details[data-gd="FNF17"] summary')
          and 'Gesamtgenauigkeit nicht berichtet' in p.inner_text('#ci-geodaten details[data-gd="FNF02"] summary'))
    check('zugeklappt: Walddefinition und Grenzen verborgen', p.is_hidden('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl'))
    p.click('#ci-geodaten details[data-gd="FNF01"] summary')
    mehr = p.inner_text('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl')
    check('aufgeklappt: Walddefinition, Validierung, Genauigkeiten, bekannte Grenzen, Verweise', all(x in mehr for x in ('Walddefinition', 'Validierung', 'Hersteller- und Nutzergenauigkeit', 'Bekannte Grenzen', 'Commission errors', 'Google Earth Engine')), mehr)
    a = p.locator('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl a').first
    check('Verweise öffnen ein neues Fenster ohne Zugriff auf die Seite', a.get_attribute('target') == '_blank' and 'noopener' in a.get_attribute('rel') and a.get_attribute('href').startswith('https://'))
    p.fill('#ci-suche', 'global forest watch')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 1")
    check('Suche „global forest watch“ findet nur FNF17', p.evaluate(eintraege) == ['FNF17'], p.evaluate(eintraege))
    p.fill('#ci-suche', 'deepmind')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 3")
    check('Suche nach Hersteller „deepmind“: FNF18, FNF20, FNF22', p.evaluate(eintraege) == ['FNF18', 'FNF20', 'FNF22'], p.evaluate(eintraege))
    p.fill('#ci-suche', 'gibtesnicht')
    p.wait_for_selector('#ci-inhalt .ci-leer')
    check('Suche ohne Treffer: Hinweis', 'Kein Eintrag passt zur Suche.' in p.inner_text('#ci-inhalt'))
    p.fill('#ci-suche', '')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 22")
    check('Neuzeichnen (Suche geleert): aufgeklappter Eintrag bleibt offen', p.evaluate("document.querySelector('#ci-geodaten details[data-gd=\"FNF01\"]').open"))
    shot(p, os.path.join(SH, 'containerimport-geodaten-1280.png'))

    # Verweise unter der Karte öffnen den passenden Eintrag
    p.click('[data-sicht="karte"]'); p.wait_for_selector('#ci-inhalt [data-geodaten="FNF17"]')
    p.click('#ci-inhalt [data-geodaten="FNF01"]'); p.wait_for_selector('#dlg-geodaten[open]')
    titel = p.inner_text('#geodaten-titel')
    check('Karte: Verweis FNF01 öffnet den Eintrag JRC GFC 2020 mit Auflösung, Genauigkeit, EUDR-konform und Grenzen', titel.startswith('FNF01 · JRC GFC 2020')
          and all(x in p.inner_text('#dlg-geodaten') for x in ('Auflösung 10 m', 'EUDR-konform', 'Gesamtgenauigkeit', 'Bekannte Grenzen', 'v1.0')), titel)
    shot(p.locator('#dlg-geodaten'), os.path.join(SH, 'containerimport-geodaten-verweis-1280.png'))
    p.click('#dlg-geodaten [data-zu]')
    p.click('#ci-inhalt [data-geodaten="FNF17"]'); p.wait_for_function("document.querySelector('#geodaten-titel').textContent.startsWith('FNF17')")
    check('Karte: Verweis FNF17 öffnet Hansen/GFW', 'Hansen' in p.inner_text('#geodaten-titel') and p.evaluate("document.querySelector('#dlg-geodaten').open"))
    p.keyboard.press('Escape')
    p.wait_for_function("!document.querySelector('#dlg-geodaten').open")

    # Whisp-Felder → Katalog: nur eindeutige Produkte, jede Kennung steht im Katalog
    felder = {k: 1 for k in ('EUFO_2020', 'GFC_TC_2020', 'GFC_loss_after_2020', 'ESA_TC_2020', 'ForTy_forest_2020', 'ForTy_v2_primary_2020', 'GFT_primary',
                             'ESRI_2024_TC', 'TMF_undist', 'RADD_after_2020', 'Forest_FDaP', 'Ind_01_treecover')}
    zuordnung = p.evaluate('(f) => window.EUDR_WHISP.katalog(f)', felder)
    check('Whisp → Katalog: EUFO_2020 = FNF01, ESA_TC_2020 = FNF03, GFC_* = FNF17, ForTy v1 = FNF22; GFT, ESRI, ForTy v2, TMF, RADD ohne Zuordnung',
          zuordnung == [['FNF01', ['EUFO_2020']], ['FNF03', ['ESA_TC_2020']], ['FNF17', ['GFC_TC_2020', 'GFC_loss_after_2020']], ['FNF22', ['ForTy_forest_2020']]]
          and all(i in ids for i, _ in zuordnung), zuordnung)
    beleg = p.evaluate("window.EUDR_GEODATEN.beleg(['FNF01', 'FNF17'])")
    check('Beleg für die Gegenprüfung: Katalog, Thema, Fassung und Kennungen', beleg == 'GEOS-EUDR-Katalog (Thünen-Institut) ForestCover_TreeExtent v1.0: FNF01, FNF17', beleg)
    lang = {'Ind_01_treecover': 'yes', 'Ind_03_disturbance_before_2020': 'no', 'Ind_04_disturbance_after_2020': 'yes', 'Unit': 'ha',
            **{f'Datensatz_mit_sehr_langem_Namen_{n:02d}_after_2020': 10 + n for n in range(20)}, **{f'risk_x{n}': 'more_info_needed' for n in range(20)}}
    text = p.evaluate('([f, b]) => window.EUDR_WHISP.deuten({ felder: f, version: "" }, 0.5, b).text', [lang, beleg])
    check('Text der Gegenprüfung: höchstens 500 Zeichen, Katalog-ID und Fassung immer vollständig am Ende', len(text) <= 500 and text.endswith('; Datengrundlage ' + beleg + '.'), (len(text), text[-160:]))
    check('ohne Katalog-Angabe bleibt der Text wie bisher', 'Datengrundlage' not in p.evaluate('(f) => window.EUDR_WHISP.deuten({ felder: f, version: "" }, 0.5).text', lang))
    p.context.close()

    # Fremdtexte: ein manipulierter Katalog darf weder HTML noch Skript einschleusen
    p = seite('ina')
    def boese(route):
        d = route.fetch().json()
        e = d['eintraege'][0]
        e['name'] = '<img src=x onerror="window.__xss=1">Name'; e['hersteller'] = '<b>fett</b>'; e['grenzen'] = '<script>window.__xss=2</script>'
        e['links']['gee'] = [{'text': 'böse', 'url': 'javascript:window.__xss=3'}, {'text': '"><img src=x>', 'url': 'https://example.org/"onmouseover="x'}]
        route.fulfill(status=200, content_type='application/json', body=json.dumps(d))
    p.route(re.compile(r'/api/\?action=containerimport_eudr_geodaten'), boese)
    katalog_zeigen(p)
    p.click('#ci-geodaten details[data-gd="FNF01"] summary')
    gd = '#ci-geodaten details[data-gd="FNF01"]'
    check('Fremdtext maskiert: kein eingeschleustes Element, kein Skript, Text sichtbar', p.locator(f'{gd} img, {gd} b:not(.ci-zahlen), {gd} script').count() == 0
          and p.evaluate('window.__xss === undefined') and '<img src=x onerror' in p.inner_text(f'{gd} summary') and '<script>' in p.inner_text(f'{gd} .ci-gd-dl'))
    check('Verweis mit javascript: wird nur Text, Anführungszeichen bleiben in der Adresse', p.locator(f'{gd} a[href^="javascript"]').count() == 0 and 'böse' in p.inner_text(f'{gd} .ci-gd-dl')
          and p.locator(f'{gd} a[href="https://example.org/\\"onmouseover=\\"x"]').count() == 1)
    p.context.close()

    # Handy 390 px
    m = seite('ina', {'width': 390, 'height': 844}, 'dark')
    katalog_zeigen(m)
    m.click('#ci-geodaten details[data-gd="FNF17"] summary')
    breit = lambda pg: pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    check('Handy 390 px: Katalog mit aufgeklapptem Eintrag ohne waagerechtes Scrollen', breit(m))
    shot(m, os.path.join(SH, 'containerimport-geodaten-390-dunkel.png'))
    m.click('[data-sicht="karte"]'); m.wait_for_selector('#ci-inhalt [data-geodaten="FNF01"]')
    m.click('#ci-inhalt [data-geodaten="FNF01"]'); m.wait_for_selector('#dlg-geodaten[open]')
    check('Handy 390 px: Fenster des Eintrags passt in die Breite', breit(m) and m.evaluate("document.querySelector('#dlg-geodaten').getBoundingClientRect().width <= window.innerWidth"))
    shot(m, os.path.join(SH, 'containerimport-geodaten-verweis-390-dunkel.png'))
    m.context.close()
    br.close()
    check('die Seite hat keine fremden Server abgerufen', fremd == [], fremd)

check('keine JavaScript-Fehler', not errs, errs)
ende()
