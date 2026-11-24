"""Container-Import · EUDR: Geodaten-Katalog GEOS-EUDR des Thünen-Instituts (Aktion containerimport_eudr_geodaten,
Datei app/api/module/containerimport/geodatenkatalog.json, Oberfläche app/module/containerimport/eudr-geodaten.js).
Geprüft: Rechte (ohne Anmeldung 401, ohne „EUDR ansehen“ 403, Leserolle sieht ihn); die Aktion liefert genau die Datei,
deren Aufbau stimmt (Pflichtfelder, Anzahl = Summe der Einträge je Thema, Verweise mit https, Quelle, Lizenz MIT) – ohne
feste Inhalte, damit eine neue Fassung den Test nicht bricht. Die Oberfläche läuft gegen einen kleinen erfundenen Katalog
(tests/fixtures/containerimport/geodatenkatalog/katalog-test.json, per Playwright ausgeliefert): Ansicht mit Suche,
aufklappbarem Eintrag und offen bleibenden Einträgen beim Neuzeichnen; Verweise „FNF01“/„FNF17“ unter der Karte öffnen den
richtigen Eintrag im Fenster; Zuordnung der Whisp-Felder zum Katalog (nur eindeutige Produkte, jede Kennung steht im
echten Katalog) und Katalog-ID mit Fassung im Text der Gegenprüfung (auch bei langem Text vollständig, höchstens 500
Zeichen); fremde Texte maskiert, Verweise nur mit http(s); Handy 390 px ohne waagerechtes Scrollen. Bildauswertung,
Whisp-Ergebnis mit Verweis und Katalog nicht erreichbar (500) prüfen die Gruppen containerimport und containerimport_whisp.
Nutzer erfunden."""
import copy
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, seite as seite_oeffnen
from kunden_hilfe import Client
from umgebung import SH, shot

REPO = Path(__file__).resolve().parent.parent.parent
DATEI = json.loads((REPO / 'app/api/module/containerimport/geodatenkatalog.json').read_text(encoding='utf-8'))
TEST = json.loads((REPO / 'tests/fixtures/containerimport/geodatenkatalog/katalog-test.json').read_text(encoding='utf-8'))
A, I, L = nutzer_anlegen()
A.call('user_save', {'id': '', 'name': 'Ole Ohne', 'username': 'ole', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
O = Client('198.51.100.40')
assert O.call('login', {'username': 'ole', 'password': 'Editor-Zugang-77'})[0] == 200

# ---------- Rechte und Aufbau der echten Datei ----------
AKTION = 'containerimport_eudr_geodaten'
st, r = Client('198.51.100.41').call(AKTION)
check('ohne Anmeldung: kein Zugriff (401)', st == 401 and 'eintraege' not in r, (st, r))
st, r = O.call(AKTION)
check('Modulzugang ohne „EUDR ansehen“: 403, kein Katalog', st == 403 and 'eintraege' not in r, (st, r))
st, k = L.call(AKTION)
check('nur ansehen: die Aktion liefert genau die eingecheckte Datei', st == 200 and k == {'ok': True, **DATEI}, st)
ids = [e['id'] for e in k.get('eintraege', [])]
PFLICHT = {'id', 'thema', 'name', 'hersteller', 'links', 'eudrKonform', 'aufloesungM', 'vonJahr', 'bisJahr', 'validierung', 'genauigkeit', 'grenzen'}
check('Aufbau: Einträge mit Pflichtfeldern, Kennung eindeutig, Anzahl = Summe der Einträge je Thema', ids and len(set(ids)) == len(ids)
      and all(PFLICHT <= set(e) and re.fullmatch(r'[A-Z]{2,6}\d{2,4}', e['id']) for e in k['eintraege']) and len(ids) == sum(t['eintraege'] for t in k['themen']), (len(ids), k.get('themen')))
check('Aufbau: Quelle mit Lizenz MIT, jedes Thema mit Fassung, Commit und Zitiervorschlag', k['quelle']['lizenz'] == 'MIT' and k['quelle']['url'].startswith('https://')
      and all(t['version'] and t['zitiervorschlag'] and re.fullmatch(r'[0-9a-f]{7,40}', t['quelleCommit'] or '') for t in k['themen']), k['themen'])
check('Aufbau: alle Verweise mit https', all(l['url'].startswith('https://') for e in k['eintraege'] for g in e['links'].values() for l in g))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light', katalog=TEST):
        """Seite mit erfundenem Katalog: die Seite lädt ihn erst bei Bedarf, die Umleitung greift also vor dem ersten Abruf."""
        pg = seite_oeffnen(br, user, errs, fremd, vp, schema)
        pg.route(re.compile(r'/api/\?action=containerimport_eudr_geodaten'), lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'ok': True, **katalog})))
        return pg

    def katalog_zeigen(p):
        p.click('[data-sicht="geodaten"]'); p.wait_for_selector('#ci-geodaten details')

    eintraege = "[...document.querySelectorAll('#ci-geodaten details')].map((d) => d.dataset.gd)"
    p = seite('lea')
    katalog_zeigen(p)
    quelle = p.inner_text('.ci-gd-quelle')
    check('Leserolle: Ansicht „Geodaten-Katalog“ mit allen Einträgen, Quelle, Fassung mit Commit und Zitiervorschlag', p.evaluate(eintraege) == ['FNF01', 'FNF03', 'FNF17']
          and 'Fassung v9.1 (Commit abc1234)' in quelle and 'Zitiervorschlag: Muster, E. (2026)' in quelle and 'Lizenz MIT' in quelle and '3 Einträge' in quelle, quelle)
    zeile = p.inner_text('#ci-geodaten details[data-gd="FNF01"] summary')
    check('Eintrag kompakt: Kennung, Name, Hersteller, Auflösung, Jahre, EUDR-konform, Gesamtgenauigkeit', all(x in zeile for x in ('FNF01', 'Testwald 2020', 'Beispiel-Institut Nord', 'Auflösung 10 m', 'Jahre 2020', 'EUDR-konform', 'ja', 'Gesamtgenauigkeit 91 %')), zeile)
    check('EUDR-konform nein/unklar, ungefähre Auflösung, Zeitraum und „nicht berichtet“ ausgeschrieben', 'nein/unklar' in p.inner_text('#ci-geodaten details[data-gd="FNF17"] summary')
          and all(x in p.inner_text('#ci-geodaten details[data-gd="FNF03"] summary') for x in ('Auflösung ~30 m', 'Jahre 2015 – 2020', 'teilweise', 'Gesamtgenauigkeit nicht berichtet')))
    check('zugeklappt: Walddefinition und Grenzen verborgen', p.is_hidden('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl'))
    p.evaluate("window.addEventListener('toggle', (e) => e.stopImmediatePropagation(), true)")   # wie in der CI (Chromium 141): „toggle“ kommt nicht an – der Aufklappstand darf nicht davon abhängen
    p.click('#ci-geodaten details[data-gd="FNF01"] summary')
    mehr = p.inner_text('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl')
    check('aufgeklappt: Walddefinition, Validierung, Genauigkeiten, bekannte Grenzen, Verweise', all(x in mehr for x in ('Walddefinition', 'Validierung', 'Hersteller- und Nutzergenauigkeit', 'PA 90 %', 'Bekannte Grenzen', '• Zweite Testgrenze.', 'Google Earth Engine', 'V1')), mehr)
    a = p.locator('#ci-geodaten details[data-gd="FNF01"] .ci-gd-dl a').first
    check('Verweise öffnen ein neues Fenster ohne Zugriff auf die Seite', a.get_attribute('target') == '_blank' and 'noopener' in a.get_attribute('rel') and a.get_attribute('href').startswith('https://'))
    p.fill('#ci-suche', 'lidar')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 1")
    check('Suche nach Sensor „lidar“ findet nur FNF17', p.evaluate(eintraege) == ['FNF17'], p.evaluate(eintraege))
    p.fill('#ci-suche', 'muster')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 2")
    check('Suche nach Hersteller „muster“: FNF03, FNF17', p.evaluate(eintraege) == ['FNF03', 'FNF17'], p.evaluate(eintraege))
    p.fill('#ci-suche', 'gibtesnicht')
    p.wait_for_selector('#ci-inhalt .ci-leer')
    check('Suche ohne Treffer: Hinweis', 'Kein Eintrag passt zur Suche.' in p.inner_text('#ci-inhalt'))
    p.fill('#ci-suche', '')
    p.wait_for_function("document.querySelectorAll('#ci-geodaten details').length === 3")
    check('Neuzeichnen (Suche geleert): aufgeklappter Eintrag bleibt offen', p.evaluate("document.querySelector('#ci-geodaten details[data-gd=\"FNF01\"]').open"))
    shot(p, os.path.join(SH, 'containerimport-geodaten-1280.png'))

    # Verweise unter der Karte öffnen den passenden Eintrag
    p.click('[data-sicht="karte"]'); p.wait_for_selector('#ci-inhalt [data-geodaten="FNF17"]')
    p.click('#ci-inhalt [data-geodaten="FNF01"]'); p.wait_for_selector('#dlg-geodaten[open]')
    titel = p.inner_text('#geodaten-titel')
    check('Karte: Verweis FNF01 öffnet den Eintrag mit Auflösung, Genauigkeit, EUDR-konform, Grenzen und Fassung', titel.startswith('FNF01 · Testwald 2020')
          and all(x in p.inner_text('#dlg-geodaten') for x in ('Auflösung 10 m', 'EUDR-konform', 'Gesamtgenauigkeit', 'Bekannte Grenzen', 'Testthema (erfunden) v9.1')), titel)
    shot(p.locator('#dlg-geodaten'), os.path.join(SH, 'containerimport-geodaten-verweis-1280.png'))
    p.click('#dlg-geodaten [data-zu]')
    p.click('#ci-inhalt [data-geodaten="FNF17"]'); p.wait_for_function("document.querySelector('#geodaten-titel').textContent.startsWith('FNF17')")
    check('Karte: Verweis FNF17 öffnet den Eintrag FNF17', 'Testverlust' in p.inner_text('#geodaten-titel') and p.evaluate("document.querySelector('#dlg-geodaten').open"))
    p.keyboard.press('Escape')
    p.wait_for_function("!document.querySelector('#dlg-geodaten').open")

    # Whisp-Felder → Katalog: nur eindeutige Produkte, jede Kennung steht im echten Katalog
    felder = {k: 1 for k in ('EUFO_2020', 'GFC_TC_2020', 'GFC_loss_after_2020', 'ESA_TC_2020', 'ForTy_forest_2020', 'ForTy_v2_primary_2020', 'GFT_primary',
                             'ESRI_2024_TC', 'TMF_undist', 'RADD_after_2020', 'Forest_FDaP', 'Ind_01_treecover')}
    zuordnung = p.evaluate('(f) => window.EUDR_WHISP.katalog(f)', felder)
    check('Whisp → Katalog: EUFO_2020 = FNF01, ESA_TC_2020 = FNF03, GFC_* = FNF17, ForTy v1 = FNF22; GFT, ESRI, ForTy v2, TMF, RADD ohne Zuordnung',
          zuordnung == [['FNF01', ['EUFO_2020']], ['FNF03', ['ESA_TC_2020']], ['FNF17', ['GFC_TC_2020', 'GFC_loss_after_2020']], ['FNF22', ['ForTy_forest_2020']]]
          and all(i in ids for i, _ in zuordnung), zuordnung)
    beleg = p.evaluate("window.EUDR_GEODATEN.beleg(['FNF01', 'FNF17'])")
    check('Beleg für die Gegenprüfung: Katalog, Thema, Fassung und Kennungen', beleg == 'GEOS-EUDR-Katalog (Thünen-Institut) Testthema v9.1: FNF01, FNF17', beleg)
    lang = {'Ind_01_treecover': 'yes', 'Ind_03_disturbance_before_2020': 'no', 'Ind_04_disturbance_after_2020': 'yes', 'Unit': 'ha',
            **{f'Datensatz_mit_sehr_langem_Namen_{n:02d}_after_2020': 10 + n for n in range(20)}, **{f'risk_x{n}': 'more_info_needed' for n in range(20)}}
    text = p.evaluate('([f, b]) => window.EUDR_WHISP.deuten({ felder: f, version: "" }, 0.5, b).text', [lang, beleg])
    check('Text der Gegenprüfung: höchstens 500 Zeichen, Katalog-ID und Fassung immer vollständig am Ende', len(text) <= 500 and text.endswith('; Datengrundlage ' + beleg + '.'), (len(text), text[-160:]))
    check('ohne Katalog-Angabe bleibt der Text wie bisher', 'Datengrundlage' not in p.evaluate('(f) => window.EUDR_WHISP.deuten({ felder: f, version: "" }, 0.5).text', lang))
    p.context.close()

    # Fremdtexte: ein manipulierter Katalog darf weder HTML noch Skript einschleusen
    boese = copy.deepcopy(TEST); e = boese['eintraege'][0]
    e['name'] = '<img src=x onerror="window.__xss=1">Name'; e['hersteller'] = '<b>fett</b>'; e['grenzen'] = '<script>window.__xss=2</script>'
    e['links']['gee'] = [{'text': 'böse', 'url': 'javascript:window.__xss=3'}, {'text': '"><img src=x>', 'url': 'https://example.org/"onmouseover="x'}]
    p = seite('ina', katalog=boese)
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
