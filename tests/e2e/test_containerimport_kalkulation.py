"""Container-Import: Kalkulation je Container (Aktionen containerimport_kalkulation_*, app/api/module/containerimport/kalkulation.php,
Oberfläche app/module/containerimport/kalkulation.js). Die Formeln selbst prüft tests/unit/test_ci_kalkulation.py.
Geprüft: Rechte (ansehen und rechnen mit „EUDR ansehen“, speichern/festschreiben nur mit „EUDR bearbeiten“, ohne Recht 403,
CSRF, kein GET); rechnen speichert nichts und nimmt vom Browser gesendete Ergebnisse nicht an; Entwurf anlegen und ändern,
Revision (409), ungültige Eingabe (422); unmögliche Kombination (Hilton für ZA) ist ein Fehler; festschreiben nur
vollständig, danach unveränderlich (Ergebnis mit den wirksamen Sätzen und Container nur einmal gespeichert, GR-106), neue
Fassung nur mit Grund, Fassungen bleiben; ältere Einträge ohne neue Felder (GR-006) lesbar und festschreibbar (gespeichert
wird die geprüfte Eingabe), Felder einer späteren Version bleiben; Prüfhinweise; Protokoll. Oberfläche: Reiter, Liste,
Eingabe mit Rechnung des Servers, Speichern, Festschreiben mit Rückfrage, neue Fassung, Leser ohne Bearbeiten, CSV (exakte
Zeile, Schutz vor Formeln, ungespeicherte Änderungen gekennzeichnet), Druckansicht (A4 quer, danach geleert, der EUDR-Druck
bleibt hochkant), Handy 390 px.
Alle Namen und Zahlen sind erfunden (GR-007)."""
import copy
import os
import re
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client
from containerimport_hilfe import check, ende, nutzer_anlegen, container, container_anlegen, stand, seite as seite_oeffnen
from umgebung import SH, shot, storage_raw, storage_write, _json

A, I, L = nutzer_anlegen()
A.call('user_save', {'id': '', 'name': 'Otto Ohne', 'username': 'otto', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-56', 'mustChange': False})
O = Client('198.51.100.30')
assert O.call('login', {'username': 'otto', 'password': 'Leser-Zugang-56'})[0] == 200

c1 = container_anlegen(I, 'P-470001')
c2 = container_anlegen(I, 'P-470002', land='UY')
DOK = 'containerimport-kalkulationen'

# Kurs 1,25; Seefracht 1.000 USD = 800 € auf 1.000 kg → 0,80 €/kg; Preis 10 USD = 8 €; Vers.-Wert (8.000 + 800) × 1,1 = 9.680,
# Prämie 0,5 % = 48,40 → 0,0484 €/kg; Hilton Ursprung UY nach dem 01.05.2026 0 %; Einstand 8,8484 €/kg
EINGABE = {'kopf': {'kurs': '1,25', 'datum': '2026-10-01', 'seefracht': 1000, 'seefrachtWaehrung': 'USD', 'provisionT': 0, 'provisionEinkauf': True,
                    'nachlauf': 0, 'nachlaufKg': 0, 'zins': 0, 'tage': 70, 'zahlPromille': 0, 'zahlFix': 0, 'imagGewinn': 10},
           'teile': [{'id': 't1', 'name': 'Teil Nord', 'abnehmer': 'Großhandel Beispiel', 'versicherung': 0.5}],
           'positionen': [{'teil': 't1', 'artikel': 'Roastbeef', 'rl': True, 'regime': 'hilton', 'land': 'UY', 'kn': '0201 30 00', 'kartons': 40, 'brutto': 1080, 'netto': 1000, 'preis': 10, 'waehrung': 'USD', 'vk': 10}],
           'ueberschrieben': {}, 'notiz': ''}


def laden(client, c):
    return client.call('containerimport_kalkulation_laden&sendung=' + c['id'])


def speichern(c, rev, eingabe=None, **mehr):
    return I.call('containerimport_kalkulation_speichern', {'sendung': c['id'], 'rev': rev, 'eingabe': eingabe or EINGABE, **mehr})


# ---------- Rechte ----------
st, start = L.call('containerimport_kalkulation_start')
check('nur ansehen: Stand mit Sätzen (Quelle, TARIC-Hinweis), Zollregimen und ohne Recht zum Bearbeiten',
      st == 200 and start['saetze']['drittland_frisch']['spez'] == 303.4 and 'TARIC' in start['taric'] and 'mercosur' in start['regime'] and start['rechte']['bearbeiten'] is False, start)
check('ohne „EUDR ansehen“: Stand, Laden und Rechnen 403', [O.call('containerimport_kalkulation_start')[0], laden(O, c1)[0], O.call('containerimport_kalkulation_rechnen', {'eingabe': EINGABE})[0]] == [403] * 3)
check('nur ansehen: Speichern und Festschreiben 403', [L.call('containerimport_kalkulation_speichern', {'sendung': c1['id'], 'rev': 0, 'eingabe': EINGABE})[0],
                                                      L.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': 1})[0]] == [403, 403])
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', speichern(c1, 0)[0] == 403)
I.csrf = csrf
check('Speichern per GET: 405', I.call('containerimport_kalkulation_speichern')[0] == 405)
check('unbekannter Container: 404', I.call('containerimport_kalkulation_laden&sendung=sgibtesnicht')[0] == 404 and speichern({'id': 'sgibtesnicht'}, 0)[0] == 404)
check('ohne Kalkulation: Laden liefert keine', laden(L, c1)[1].get('kalkulation', 'x') is None)

# ---------- Rechnen ----------
fremd = copy.deepcopy(EINGABE)
fremd['positionen'][0]['einstandKg'] = 0.01
fremd['ergebnis'] = {'gesamt': {'ist': 1}}
st, r = L.call('containerimport_kalkulation_rechnen', {'eingabe': fremd, 'ergebnis': {'vollstaendig': True}})
p = r.get('ergebnis', {}).get('positionen', [{}])[0]
check('rechnen (auch nur ansehen): Einstand 8,8484 €/kg vom Server, vom Browser gesendete Werte zählen nicht',
      st == 200 and abs(p.get('einstandKg', 0) - 8.8484) < 1e-9 and abs(r['ergebnis']['gesamt']['ist'] - 8848.4) < 1e-6 and 'einstandKg' not in r['eingabe']['positionen'][0] and 'ergebnis' not in r['eingabe'], r)
check('rechnen speichert nichts', storage_raw(DOK) in (None, '', b'') or not _json(storage_raw(DOK)).get('liste'))
falsch = copy.deepcopy(EINGABE); falsch['positionen'][0]['land'] = 'ZA'
st, r = I.call('containerimport_kalkulation_rechnen', {'eingabe': falsch})
check('Hilton für Ursprung ZA: Fehler an Position 1, unvollständig', st == 200 and not r['ergebnis']['vollstaendig']
      and any(h['stufe'] == 'fehler' and 'gibt es nicht für Ursprung ZA' in h['text'] and h['pos'] == 0 for h in r['ergebnis']['hinweise']), r)
check('rechnen mit ungültiger Eingabe: 422 mit Meldung', I.call('containerimport_kalkulation_rechnen', {'eingabe': {**EINGABE, 'kopf': {**EINGABE['kopf'], 'zins': 'viel'}}})[0] == 422)

# ---------- Entwurf, Revision, Festschreiben, Fassungen ----------
st, r = speichern(c1, 0, fremd)
k = r.get('kalkulation') or {}
f1 = (k.get('fassungen') or [{}])[0]
check('Entwurf angelegt: Fassung 1 vorläufig, Ergebnis vom Server, gesendete Werte nicht gespeichert, Übersicht',
      st == 200 and len(k['fassungen']) == 1 and f1['stand'] == 'entwurf' and f1['nr'] == 1 and abs(f1['ergebnis']['gesamt']['ist'] - 8848.4) < 1e-6
      and 'ergebnis' not in f1['eingabe'] and 'einstandKg' not in f1['eingabe']['positionen'][0] and r['uebersicht'][c1['id']]['stand'] == 'entwurf', (st, r.get('error')))
check('zweites Anlegen mit Revision 0: 409', speichern(c1, 0)[0] == 409)
check('ungültige Eingabe (negativer Preis): 422, nichts geändert',
      speichern(c1, k['rev'], {**EINGABE, 'positionen': [{**EINGABE['positionen'][0], 'preis': -1}]})[0] == 422 and laden(I, c1)[1]['kalkulation']['rev'] == k['rev'])
ohne_kurs = copy.deepcopy(EINGABE); ohne_kurs['kopf']['kurs'] = ''
st, r = speichern(c1, k['rev'], ohne_kurs)
k = r['kalkulation']
check('Entwurf ohne Kurs lässt sich speichern (unvollständig, Fehler „Kurs fehlt“), bleibt Fassung 1',
      st == 200 and len(k['fassungen']) == 1 and not k['fassungen'][0]['ergebnis']['vollstaendig'] and any(h['text'] == 'Kurs USD/€ fehlt.' for h in k['fassungen'][0]['ergebnis']['hinweise']))
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': k['rev']})
check('unvollständig festschreiben: 422 mit Grund', st == 422 and 'Kurs' in r.get('error', ''), r)
st, r = speichern(c1, k['rev'])
k = r['kalkulation']
check('veralteter Stand beim Festschreiben: 409', I.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': k['rev'] - 1})[0] == 409)
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': k['rev']})
k = r.get('kalkulation') or {}
f1 = (k.get('fassungen') or [{}])[0]
gespeichert = _json(storage_raw(DOK))['liste'][0]['fassungen'][0]
check('festgeschrieben: endgültig mit wer/wann und Container, Ergebnis mit den wirksamen Sätzen – jedes nur einmal gespeichert',
      st == 200 and f1['stand'] == 'endgueltig' and f1['endgueltig']['wer']['von'] == 'Ina Import' and f1['ergebnis']['saetze']['mercosur']['wert'] == 7.5
      and abs(f1['ergebnis']['gesamt']['ist'] - 8848.4) < 1e-6 and f1['endgueltig']['container']['partie'] == 'P-470001'
      and set(gespeichert['endgueltig']) == {'wer', 'container'} and 'saetze' in gespeichert['ergebnis'] and set(f1['endgueltig']) == {'wer', 'container'}, (st, r.get('error'), gespeichert.get('endgueltig')))
check('endgültige Fassung erneut festschreiben: 409', I.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': k['rev']})[0] == 409)
geaendert = copy.deepcopy(EINGABE); geaendert['positionen'][0]['netto'] = 900
st, r = speichern(c1, k['rev'], geaendert)
check('nach dem Festschreiben ohne Grund: 422, nichts geändert', st == 422 and 'Grund' in r.get('error', '') and len(laden(I, c1)[1]['kalkulation']['fassungen']) == 1)

# Schnappschuss: die endgültige Fassung wird nie neu gerechnet (Sätze im Code könnten sich ändern)
doc = _json(storage_raw(DOK))
doc['liste'][0]['fassungen'][0]['ergebnis']['gesamt']['ist'] = 1234.5
doc['liste'][0]['zukunft'] = {'feld': 'einer späteren Version'}
storage_write(DOK, doc)
check('endgültige Fassung zeigt ihren Schnappschuss (nicht neu gerechnet, GR-106)', laden(L, c1)[1]['kalkulation']['fassungen'][0]['ergebnis']['gesamt']['ist'] == 1234.5)
st, r = speichern(c1, k['rev'], geaendert, grund='Endgültige Gewichte laut Packliste')
k = r.get('kalkulation') or {}
check('neue Fassung mit Grund: Fassung 2 vorläufig, Fassung 1 unverändert, Feld einer späteren Version bleibt',
      st == 200 and [f['stand'] for f in k['fassungen']] == ['endgueltig', 'entwurf'] and k['fassungen'][1]['grund'] == 'Endgültige Gewichte laut Packliste'
      and k['fassungen'][1]['eingabe']['positionen'][0]['netto'] == 900 and k['fassungen'][0]['eingabe']['positionen'][0]['netto'] == 1000
      and k['fassungen'][0]['ergebnis']['gesamt']['ist'] == 1234.5 and _json(storage_raw(DOK))['liste'][0].get('zukunft') == {'feld': 'einer späteren Version'}, (st, r.get('error')))
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c1['id'], 'rev': k['rev']})
check('Fassung 2 festgeschrieben, beide bleiben', st == 200 and [f['stand'] for f in r['kalkulation']['fassungen']] == ['endgueltig', 'endgueltig'] and r['uebersicht'][c1['id']]['endgueltige'] == 2)

# GR-006: Entwurf aus einer älteren Version ohne neuere Felder
st, r = speichern(c2, 0)
doc = _json(storage_raw(DOK))
alt = next(x for x in doc['liste'] if x['sendung'] == c2['id'])
for f in ('nachlaufKg', 'zahlFix', 'provisionEinkauf'):
    alt['fassungen'][0]['eingabe']['kopf'].pop(f)
alt['fassungen'][0]['eingabe'].pop('ueberschrieben')
storage_write(DOK, doc)
st, r = laden(I, c2)
f = r['kalkulation']['fassungen'][0] if st == 200 else {}
check('älterer Entwurf ohne neue Felder: lesbar und gerechnet (Vorgaben für fehlende Felder)', st == 200 and f['ergebnis']['vollstaendig'] and f['eingabe']['kopf']['provisionEinkauf'] is True, (st, r))
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c2['id'], 'rev': r['kalkulation']['rev']})
alt = next(x for x in _json(storage_raw(DOK))['liste'] if x['sendung'] == c2['id'])['fassungen'][0]
check('älterer Entwurf ohne neue Felder festschreiben: gespeichert wird die geprüfte Eingabe (neue Felder mit Vorgabe, Zahlen als Zahlen)',
      st == 200 and alt['stand'] == 'endgueltig' and alt['eingabe']['kopf']['provisionEinkauf'] is True and alt['eingabe']['kopf']['zahlFix'] == 0
      and alt['eingabe']['kopf']['nachlaufKg'] == 0 and not alt['eingabe']['ueberschrieben'] and alt['eingabe']['kopf']['kurs'] == 1.25 and alt['ergebnis']['vollstaendig'], (st, r.get('error'), alt.get('eingabe')))
# Gesamtgrenze des Dokuments: es wird bei jedem Zugriff ganz gelesen und ganz geschrieben (CI_KALK_MAX_POSITIONEN_GESAMT)
c9 = container_anlegen(I, 'P-470009', land='UY')
st, r = speichern(c9, 0)
rev9 = r['kalkulation']['rev']
sicherung = copy.deepcopy(_json(storage_raw(DOK)))
voll = copy.deepcopy(sicherung)
voll['liste'].append({'id': 'kvoll', 'sendung': 'svoll', 'rev': 1,
                      'fassungen': [{'nr': 1, 'stand': 'endgueltig', 'eingabe': {'positionen': [{'artikel': 'Platzhalter'}] * 9000}}]})
storage_write(DOK, voll)
st, r = speichern(c9, rev9, grund='Noch eine Fassung')
check('Bestand über der Gesamtgrenze: speichern mit 422 abgelehnt statt mit einem Speicherabbruch (HTTP 500)',
      st == 422 and 'auslagern' in r.get('error', ''), (st, r))
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c9['id'], 'rev': rev9})
check('Bestand über der Gesamtgrenze: auch festschreiben mit 422 abgelehnt (es vergrößert die Fassung noch einmal)',
      st == 422 and 'auslagern' in r.get('error', ''), (st, r))
check('nichts geschrieben: der Bestand ist unverändert', len(_json(storage_raw(DOK))['liste']) == len(voll['liste']))
storage_write(DOK, sicherung)   # ausgelagert: der Platzhalter ist weg (deploy/ci-kalkulationen-auslagern.php)
st, r = I.call('containerimport_kalkulation_festschreiben', {'sendung': c9['id'], 'rev': rev9})
check('nach dem Auslagern wieder festschreibbar', st == 200, (st, r.get('error')))

verlauf = str(A.call('log')[1])
check('Protokoll: angelegt, festgeschrieben, neue Fassung mit Grund', all(t in verlauf for t in ('Kalkulation des Containers „P-470001“: angelegt', 'Fassung 1 endgültig festgeschrieben',
                                                                                              'Fassung 2 angelegt (Grund: Endgültige Gewichte laut Packliste)', 'Fassung 2 endgültig festgeschrieben')), verlauf[:400])

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremdeAdressen = [], []

    def seite(user, vp=None, schema='light'):
        return seite_oeffnen(br, user, errs, fremdeAdressen, vp, schema)

    pg = seite('ina')
    pg.click('#ci-reiter-kalkulation'); pg.wait_for_selector('#kk-liste')
    zeilen = pg.evaluate("[...document.querySelectorAll('#kk-liste tbody tr')].map(r => r.cells[0].querySelector('.ci-name').textContent + '|' + r.cells[2].textContent.trim())")
    check('Reiter „Kalkulation“: Container mit Stand der Kalkulation', 'Partie P-470001|Fassung 2 · endgültig' in zeilen and 'Partie P-470002|Fassung 1 · endgültig' in zeilen, zeilen)
    c3 = container_anlegen(I, 'P-470003', land='UY')
    pg.click('#ci-neu'); pg.wait_for_selector(f'tr[data-kalk="{c3["id"]}"]')
    pg.click(f'tr[data-kalk="{c3["id"]}"]'); pg.wait_for_selector('#kk-editor')
    check('neue Kalkulation: Kopf mit Vorgaben (70 Zinstage, 1,5 ‰ + 50 €), ein Teil, keine Position, Fehler „Noch keine Position“',
          pg.input_value('[data-k=tage]') == '70' and pg.input_value('[data-k=zahlPromille]') == '1,5' and pg.locator('tr[data-teil]').count() == 1
          and pg.locator('tr[data-pos]').count() == 0 and (pg.wait_for_selector('#kk-hinweise li[data-stufe=fehler]') and 'Noch keine Position.' in pg.inner_text('#kk-hinweise')))
    pg.fill('[data-k=kurs]', '1,25'); pg.fill('[data-k=datum]', '2026-10-01'); pg.fill('[data-k=seefracht]', '1000')
    pg.fill('[data-k=zahlPromille]', '0'); pg.fill('[data-k=zahlFix]', '0')
    pg.fill('tr[data-teil] [data-f=versicherung]', '0,5')
    pg.click('#kk-pos-neu'); pg.wait_for_selector('tr[data-pos="0"]')
    zeile = 'tr[data-pos="0"] '
    for f, w in (('artikel', 'Roastbeef'), ('kn', '0201 30 00'), ('kartons', '40'), ('brutto', '1080'), ('netto', '1.000'), ('preis', '10'), ('vk', '10')):
        pg.fill(zeile + f'[data-f={f}]', w)
    check('Ursprung der neuen Position vom Container übernommen', pg.input_value(zeile + '[data-f=land]') == 'UY')
    pg.wait_for_function("document.querySelector('#kk-pos-ergebnis') && document.querySelector('#kk-pos-ergebnis tbody tr').innerText.includes('8,8484')")
    teil = pg.inner_text('#kk-teil-ergebnis')
    check('Ergebnis vom Server: Wert Ist 8.848,40 €, VK-Wert 10.000,00 € (kein „VK fehlt“), als ungespeichert markiert',
          '8.848,40' in teil and '10.000,00' in teil and 'VK fehlt' not in teil and pg.is_visible('#kk-ungespeichert'), teil)
    pg.click(zeile + '[data-kk-kopie]'); pg.wait_for_selector('tr[data-pos="1"]')
    pg.select_option('tr[data-pos="1"] [data-f=regime]', 'mercosur')
    pg.wait_for_function("document.querySelector('#kk-kontingente') && document.querySelector('#kk-kontingente').innerText.includes('Anteilig Hilton')")
    kont = pg.inner_text('#kk-kontingente').replace('\xa0', ' ')
    check('Position kopiert und ins Mercosur-Kontingent gesetzt: anteilig Hilton 50 %, Schlachtkörperäquivalent 1.300 kg', '50,0 %' in kont and '1.300 kg' in kont, kont)
    pg.select_option('tr[data-pos="1"] [data-f=regime]', 'drittland'); pg.fill('tr[data-pos="1"] [data-f=kn]', '')
    pg.wait_for_selector('#kk-unvollstaendig')
    check('Drittland ohne KN-Code: unvollständig mit Fehler an Position 2', 'Pos. 2:' in pg.inner_text('#kk-hinweise') and '0201 30 00' in pg.inner_text('#kk-hinweise'))
    pg.click('tr[data-pos="1"] [data-kk-weg]'); pg.wait_for_selector('#kk-pos-ergebnis')
    with pg.expect_response(lambda r: 'action=containerimport_kalkulation_speichern' in r.url):
        pg.click('#kk-speichern')
    pg.wait_for_selector('[data-kk-fassung="0"]')
    gespeichert = laden(I, c3)[1]['kalkulation']
    check('gespeichert: Fassung 1 vorläufig mit den Eingaben der Seite', gespeichert['fassungen'][0]['eingabe']['positionen'][0]['netto'] == 1000
          and gespeichert['fassungen'][0]['eingabe']['kopf']['kurs'] == 1.25 and pg.is_hidden('#kk-ungespeichert'))
    shot(pg, os.path.join(SH, 'containerimport-kalkulation-1280.png'))
    pg.locator('#kk-teil-ergebnis').scroll_into_view_if_needed()
    shot(pg, os.path.join(SH, 'containerimport-kalkulation-ergebnis-1280.png'))
    with pg.expect_download() as dl:
        pg.click('#kk-csv')
    zeilen = open(dl.value.path(), encoding='utf-8-sig', newline='').read().split('\r\n')
    check('CSV: Stand, Kopfzeile, Position genau (Komma, ohne Tausenderpunkt, höchstens 6 Stellen), Summen je Teil, Dateiname',
          zeilen[0].startswith('"Kalkulation Partie P-470003";"Fassung 1 · vorläufig";"erstellt ') and zeilen[1] == '' and zeilen[2].startswith('"Pos";"Teil";"Artikel";"R/L"')
          and zeilen[3] == '1;"Teil 1";"Roastbeef";"";"Hilton-Kontingent";"Hilton-Kontingent, Ursprung Mercosur";"UY";"02013000";40;1080;1000;10;"USD";8;0,8;0,0484;0;8,8484;0;8,8484;0;8,8484;8848,4;;;10;10000'
          and '"Wert Ist (Einstand)";8848,4;8848,4' in zeilen and dl.value.suggested_filename == 'Kalkulation_P-470003_Fassung_1.csv', zeilen[:5])
    pg.evaluate("window.print = () => { window.__gedruckt = true; }")
    pg.click('#kk-druck')
    pg.emulate_media(media='print')
    check('Druckansicht: Kalkulation mit Ergebnis in eigenem Block der Druckfassung (A4 quer)', pg.evaluate("window.__gedruckt === true && !!document.querySelector('#ci-druck > .kk-druck')")
          and 'Kalkulation Partie P-470003' in pg.inner_text('#ci-druck') and 'Fassung 1 · vorläufig' in pg.inner_text('#ci-druck') and '8,8484' in pg.inner_text('#ci-druck') and pg.is_hidden('#ci-app'))
    gross = pg.evaluate("""() => [...document.querySelectorAll('#ci-druck .kk-druck table')].flatMap((t) => { const f = parseFloat(getComputedStyle(t).fontSize);
      return [...t.querySelectorAll('th, td, .ci-unter')].filter((e) => parseFloat(getComputedStyle(e).fontSize) > f + 0.1).map((e) => e.textContent.trim().slice(0, 24) + ' ' + getComputedStyle(e).fontSize); })""")
    check('Druck: Zeilennamen, Spaltenköpfe und Unterzeilen in der Schrift der Tabelle (nicht größer als die Zahlen)', not gross, gross[:6])
    pdf = pg.pdf(prefer_css_page_size=True)
    with open(os.path.join(SH, 'containerimport-kalkulation-druck.pdf'), 'wb') as datei:
        datei.write(pdf)
    seiten = re.findall(rb'/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]', pdf)
    check('Druck im Querformat A4 (842 × 595 pt) und nicht leer', seiten and all(abs(float(w) - 841.9) < 1 and abs(float(h) - 595) < 1 for w, h in seiten), seiten)
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    check('nach dem Druck: Druckfassung geleert', pg.evaluate("document.querySelector('#ci-druck').innerHTML === ''"))
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    check('Drucken über das Browsermenü im Reiter: Druckfassung frisch erzeugt', pg.evaluate("!!document.querySelector('#ci-druck > .kk-druck')") and '8,8484' in pg.inner_text('#ci-druck'))
    pg.emulate_media(media='screen')
    pg.click('#ci-reiter-eudr'); pg.click(f'tr[data-sendung="{c3["id"]}"]'); pg.wait_for_selector('#dlg-sendung[open]')
    pg.click('#sendung-druck')   # ohne afterprint (window.print ist ersetzt): der EUDR-Druck darf nichts von der Kalkulation erben
    pg.emulate_media(media='print')
    seiten = re.findall(rb'/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]', pg.pdf(prefer_css_page_size=True))
    check('danach EUDR-Risikoprofil drucken: ohne Kalkulation, hochkant', 'Risikoprofil EUDR' in pg.inner_text('#ci-druck') and pg.locator('#ci-druck .kk-druck').count() == 0
          and seiten and all(float(w) < float(h) for w, h in seiten), seiten)
    pg.emulate_media(media='screen')
    pg.click('#dlg-sendung .dlg-foot [data-zu]'); pg.wait_for_selector('#dlg-sendung', state='hidden')
    pg.click('#ci-reiter-kalkulation'); pg.wait_for_selector('#kk-editor')
    pg.click('#kk-fest'); pg.wait_for_selector('#kk-fest-ja')
    check('Festschreiben fragt nach', 'unveränderlich' in pg.inner_text('.kk-frage'))
    pg.click('#kk-fest-ja'); pg.wait_for_selector('#kk-neu')
    check('festgeschrieben: Felder gesperrt, „Neue Fassung anlegen“', pg.is_disabled('[data-k=kurs]') and pg.is_disabled(zeile + '[data-f=netto]') and pg.locator('#kk-speichern').count() == 0
          and laden(I, c3)[1]['kalkulation']['fassungen'][0]['stand'] == 'endgueltig')
    pg.click('#kk-neu'); pg.wait_for_selector('#kk-grund')
    pg.fill('[data-k=nachlauf]', '100'); pg.fill(zeile + '[data-f=artikel]', '=HYPERLINK("https://beispiel.invalid","x")')
    pg.wait_for_function("document.querySelector('#kk-pos-ergebnis') && document.querySelector('#kk-pos-ergebnis').innerText.includes('HYPERLINK') && document.querySelector('#kk-ergebnis').innerText.includes('Nachlauf 100,00')")
    with pg.expect_download() as dl:
        pg.click('#kk-csv')
    text = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV mit ungespeicherten Änderungen: gekennzeichnet (Stand und Dateiname), Formel als Text mit Apostroph',
          text.startswith('"Kalkulation Partie P-470003";"neue Fassung, nicht gespeichert · mit ungespeicherten Änderungen"') and dl.value.suggested_filename == 'Kalkulation_P-470003_Fassung_neu_ungespeichert.csv'
          and '"\'=HYPERLINK(""https://beispiel.invalid"",""x"")"' in text and ';"=HYPERLINK' not in text, text[:400])
    pg.fill(zeile + '[data-f=artikel]', 'Roastbeef')
    pg.click('#kk-speichern'); pg.wait_for_selector('#ci-toast.zeigen.fehler')
    check('neue Fassung ohne Grund: Meldung, nichts gespeichert', 'Grund' in pg.inner_text('#ci-toast') and len(laden(I, c3)[1]['kalkulation']['fassungen']) == 1)
    pg.fill('#kk-grund', 'Nachlauf ergänzt')
    with pg.expect_response(lambda r: 'action=containerimport_kalkulation_speichern' in r.url):
        pg.click('#kk-speichern')
    pg.wait_for_selector('[data-kk-fassung="1"][aria-pressed=true]')
    k3 = laden(I, c3)[1]['kalkulation']
    check('neue Fassung gespeichert: Fassung 2 vorläufig mit Grund, Fassung 1 bleibt', [f['stand'] for f in k3['fassungen']] == ['endgueltig', 'entwurf'] and k3['fassungen'][1]['grund'] == 'Nachlauf ergänzt'
          and k3['fassungen'][1]['eingabe']['kopf']['nachlauf'] == 100 and k3['fassungen'][0]['eingabe']['kopf']['nachlauf'] == 0)
    pg.click('[data-kk-fassung="0"]'); pg.wait_for_selector('[data-kk-fassung="0"][aria-pressed=true]')
    check('ältere Fassung ansehen: gesperrt, Nachlauf 0', pg.is_disabled('[data-k=nachlauf]') and pg.input_value('[data-k=nachlauf]') == '0')

    # GR-106: nach einer Stammdatenänderung zeigt eine festgeschriebene Fassung weiter den Container von damals
    s3 = container(stand(I), 'P-470003')
    st, r = I.call('containerimport_eudr_sendung_save', {'id': s3['id'], 'rev': s3['rev'], 'partie': 'P-470099', 'akte': 'AKTE-99',
                                                         'lieferant': 'Frigorifico Zwei', 'land': s3['land'], 'ware': 'Rindfleisch gefroren'})
    check('Container umbenannt (Partie, Akte, Lieferant, Ware)', st == 200 and container(r, 'P-470099'), (st, r.get('error')))
    pg.reload(); pg.wait_for_selector('#ci-app:not([hidden])')
    pg.click('#ci-reiter-kalkulation'); pg.wait_for_selector('#kk-liste')
    pg.wait_for_function("document.querySelector('#kk-liste').textContent.includes('P-470099')")
    pg.click(f'tr[data-kalk="{c3["id"]}"]'); pg.wait_for_selector('#kk-editor')
    pg.click('[data-kk-fassung="0"]'); pg.wait_for_selector('[data-kk-fassung="0"][aria-pressed=true]')
    kopf = pg.inner_text('.kk-titel')
    check('festgeschriebene Fassung: Kopfzeile mit dem Container von damals, nicht mit den heutigen Stammdaten (GR-106)',
          'Partie P-470003' in kopf and 'P-470099' not in kopf and 'AKTE-99' not in kopf and 'Frigorifico Zwei' not in kopf
          and 'Rindfleisch gefroren' not in kopf, kopf)
    with pg.expect_download() as dl:
        pg.click('#kk-csv')
    csvText = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV der festgeschriebenen Fassung: Dateiname und erste Zeile mit dem Container von damals',
          dl.value.suggested_filename == 'Kalkulation_P-470003_Fassung_1.csv' and csvText.startswith('"Kalkulation Partie P-470003";"Fassung 1 · endgültig')
          and 'P-470099' not in csvText, (dl.value.suggested_filename, csvText[:200]))
    pg.evaluate("window.print = () => {}")   # die Seite wurde neu geladen, der Ersatz von oben ist weg
    pg.click('#kk-druck')
    druck = pg.evaluate("document.querySelector('#ci-druck').textContent")
    check('Druckfassung der festgeschriebenen Fassung: Container von damals', 'Kalkulation Partie P-470003' in druck and 'P-470099' not in druck
          and 'Frigorifico Zwei' not in druck, druck[:200])
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    pg.click('[data-kk-fassung="1"]'); pg.wait_for_selector('[data-kk-fassung="1"][aria-pressed=true]')
    check('die offene Fassung zeigt weiter die heutigen Stammdaten', 'P-470099' in pg.inner_text('.kk-titel'), pg.inner_text('.kk-titel'))
    pg.click('#kk-zurueck'); pg.wait_for_selector('#kk-liste')
    pg.context.close()

    le = seite('lea')
    le.click('#ci-reiter-kalkulation'); le.wait_for_selector('#kk-liste')
    le.click(f'tr[data-kalk="{c1["id"]}"]'); le.wait_for_selector('#kk-editor')
    check('nur ansehen: Kalkulation sichtbar, Felder gesperrt, keine Knöpfe zum Speichern', le.is_disabled('[data-k=kurs]') and le.locator('#kk-speichern, #kk-fest, #kk-neu, #kk-pos-neu').count() == 0
          and le.is_visible('#kk-csv') and le.is_visible('#kk-teil-ergebnis'))
    le.context.close()

    m = seite('ina', {'width': 390, 'height': 844}, 'dark')
    m.click('#ci-reiter-kalkulation'); m.wait_for_selector('#kk-liste')
    check('Handy 390 px: Liste ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    m.click(f'tr[data-kalk="{c3["id"]}"]'); m.wait_for_selector('#kk-pos-ergebnis')
    check('Handy 390 px: Kalkulation ohne waagerechtes Scrollen der Seite, Tabellen im eigenen Scrollbereich',
          m.evaluate("document.documentElement.scrollWidth <= window.innerWidth && [...document.querySelectorAll('.kk-scroll')].some((x) => x.scrollWidth > x.clientWidth)"))
    shot(m, os.path.join(SH, 'containerimport-kalkulation-390-dunkel.png'))
    m.context.close()
    br.close()
    check('die Seite hat keine fremden Server abgerufen', fremdeAdressen == [], fremdeAdressen)

check('keine JavaScript-Fehler', not errs, errs)
ende()
