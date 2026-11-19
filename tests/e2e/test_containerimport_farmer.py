"""Container-Import: Farmer je Container (Auftrag des Inhabers 19.11.2026) – eigene fortlaufende Farmer-Nummer neben der
Nummer aus den Papieren (Kennung), Farmer über die Nummern aus den Papieren einem Container zuordnen (Vorschau, Aktion
containerimport_eudr_nummern; bekannte verknüpft, unbekannte als „Unterlagen fehlen“ am Container vermerkt und später
selbsttätig zugeordnet), Gesamtprüfung je Container aus allen Farmern, Gesamtübersicht der Farmer mit ihren Containern,
Akten- und Partienummer gleichrangig vorn, zuletzt benutzter Schlachthof des Lieferanten als Vorschlag.
Geprüft auch: Nummer aus den Papieren je Land eindeutig, auch zweimal in einem Einlese-Durchgang; Nummern ohne Inhalt („-“)
lassen keine Farmer zusammenfallen; die eigene Nummer wird nie gespeichert; Gesamtprüfung je Thema nach kritisch und offen;
archivierte Container werden nicht selbsttätig zugeordnet; ältere Einträge ohne die neuen Felder (GR-006, Rückfall);
abgeschlossene Container bleiben, wie sie sind (GR-106). Alle Namen und Nummern sind erfunden (GR-007)."""
import json
import os
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, seite, container_anlegen, container, stand
from kunden_hilfe import Client
from umgebung import SH, shot, storage_raw, storage_write, _json

A, I, L = nutzer_anlegen()
A.call('lieferanten_save', {'rev': 0, 'groups': [{'nr': '70012', 'name': 'Frigorifico Beispiel S.A.', 'kurz': 'FRIGOBSP'}], 'quelle': 'Test'})


def farmer(name, kennung, x, land='PY', y=-23.0, **mehr):
    """Farmer mit kleinem Umriss (Westecke x/y) und Nummer aus den Papieren."""
    ring = [[x, y], [x + 0.01, y], [x + 0.01, y - 0.01], [x, y - 0.01], [x, y]]
    return {'name': name, 'land': land, 'kennung': kennung, 'geometrie': {'type': 'Polygon', 'coordinates': [ring]}, **mehr}


def betrieb(name, r=None):
    return next(b for b in (r or stand(I))['betriebe'] if b['name'] == name)


def speichern(*betriebe, sendung=''):
    return I.call('containerimport_eudr_betriebe_save', {'sendung': sendung, 'betriebe': list(betriebe)})


# ---------- Eigene Farmer-Nummer, Nummer aus den Papieren ----------
KONFORM = {'datum': stand(I)['heute'], 'entwaldung': 'konform', 'schutzgebiet': 'konform', 'indigen': 'konform', 'landnutzung': 'konform', 'umwelt': 'konform'}
st, r = speichern(farmer('Estancia Uno', '12.345', -57.5, bericht=KONFORM), farmer('Estancia Dos', 'PY-2002', -57.4))
check('eigene Farmer-Nummer: fortlaufend in der Reihenfolge des Anlegens, neben der Nummer aus den Papieren',
      st == 200 and [(b['farmerNr'], b['kennung']) for b in r['betriebe']] == [('F-0001', '12.345'), ('F-0002', 'PY-2002')], (st, r.get('error')))
uno, dos = betrieb('Estancia Uno', r), betrieb('Estancia Dos', r)
I.call('containerimport_eudr_gegenpruefung', {'id': uno['id'], 'portal': 'gnw', 'datum': stand(I)['heute'], 'ergebnis': 'ohne_befund'})
check('Farmer mit Bericht und eigener Prüfung ohne Befund ist grün', betrieb('Estancia Uno')['ampel'] == 'gruen', betrieb('Estancia Uno')['bewertung'])

st, r = speichern(farmer('Estancia Doppelt', '12 345', -57.3))
check('Nummer aus den Papieren je Land eindeutig: anders geschrieben („12 345“ = „12.345“) wird abgewiesen und nennt den Farmer',
      st == 422 and 'Estancia Uno' in r.get('error', '') and 'F-0001' in r.get('error', ''), (st, r))
st, r = speichern({**dos, 'kennung': '12345'})
check('auch beim Ändern: die Nummer eines anderen Farmers wird abgewiesen', st == 422, (st, r))
st, r = speichern(farmer('Estancia Argentina', '12345', -60.0, land='AR', y=-30.0))
check('dieselbe Nummer in einem anderen Land ist ein anderer Farmer', st == 200 and betrieb('Estancia Argentina', r)['farmerNr'] == 'F-0003', (st, r.get('error')))
st, r = speichern({**betrieb('Estancia Dos'), 'notiz': 'geändert'})
check('Farmer ändern behält seine Nummer', st == 200 and betrieb('Estancia Dos', r)['farmerNr'] == 'F-0002', (st, r.get('error')))
speichern({**betrieb('Estancia Argentina'), 'aktiv': False})
st, r = speichern(farmer('Estancia Cuatro', 'C-4', -57.2))
check('archivierte Farmer behalten ihre Nummer, keine wird wiederverwendet', st == 200 and betrieb('Estancia Cuatro', r)['farmerNr'] == 'F-0004'
      and betrieb('Estancia Argentina', r)['farmerNr'] == 'F-0003', (st, r.get('error')))

# Die eigene Nummer ergibt sich aus der Stelle in der Liste und wird nie gespeichert (Rückfall auf die Vorversion, GR-006)
doc = _json(storage_raw('containerimport-eudr-betriebe'))
check('eigene Nummer steht nicht im Speicher', [b.get('nr') for b in doc['liste']] == [None] * 4, [b.get('nr') for b in doc['liste']])
for b in doc['liste']: b['nr'] = 99
storage_write('containerimport-eudr-betriebe', doc)
r = stand(I)
check('eine gespeicherte Nummer (fremder Stand) zählt nicht – es gilt die Stelle', [b['farmerNr'] for b in r['betriebe']] == ['F-0001', 'F-0002', 'F-0003', 'F-0004'],
      [b.get('farmerNr') for b in r['betriebe']])
speichern({**betrieb('Estancia Dos', r), 'notiz': 'nochmal'})
check('mit dem nächsten Speichern ist sie wieder aus dem Speicher', [b.get('nr') for b in _json(storage_raw('containerimport-eudr-betriebe'))['liste']] == [None] * 4)

o = L.call('containerimport_eudr_pruefen', {'dateien': [{'art': 'koordinaten', 'datei': '', 'land': 'PY', 'ort': {'name': 'Andere Schreibweise', 'kennung': '12-345', 'koordinaten': {'system': 'wgs84', 'punkte': [[-57.0, -23.5]]}}}]})[1]
o = o['dateien'][0]['orte'][0] if o.get('dateien') else {}
check('Einlesen erkennt den Farmer an der Nummer aus den Papieren (andere Schreibweise) und nennt seine eigene Nummer', o.get('bekannt') == uno['id'] and o.get('farmerNr') == 'F-0001', o)


def ort(name, kennung, x):
    return {'art': 'koordinaten', 'datei': name + '.txt', 'land': 'PY', 'ort': {'name': name, 'kennung': kennung, 'koordinaten': {'system': 'wgs84', 'punkte': [[x, -24.0]]}}}


st, r = L.call('containerimport_eudr_pruefen', {'dateien': [ort('Doppel Eins', 'D-500', -56.0), ort('Doppel Zwei', 'd 500', -55.9), ort('Einzeln Drei', 'E-600', -55.8)]})
check('Einlesen: dieselbe neue Nummer zweimal in einer Auswahl – die Vorschau meldet das zweite Vorkommen und übernimmt es nicht',
      st == 200 and [[o['name'] for o in d['orte']] for d in r['dateien']] == [['Doppel Eins'], [], ['Einzeln Drei']]
      and 'gleiche Nummer „d 500“ aus den Papieren wie „Doppel Eins“' in ' '.join(r['dateien'][1]['fehler']), (st, r.get('error'), [d.get('fehler') for d in r.get('dateien', [])]))
st, r = speichern(*[o['eingabe'] for d in r['dateien'] for o in d['orte']])
check('der Rest der Auswahl wird gespeichert', st == 200 and betrieb('Doppel Eins', r)['farmerNr'] == 'F-0005' and betrieb('Einzeln Drei', r)['farmerNr'] == 'F-0006', (st, r.get('error')))
st, r = speichern(farmer('Zweimal A', 'Z-1', -55.5), farmer('Zweimal B', 'Z 1', -55.4))
check('Speichern: dieselbe neue Nummer zweimal in einem Durchgang nennt die Auswahl, keinen Farmer mit erfundener eigener Nummer',
      st == 422 and 'in dieser Auswahl zweimal' in r.get('error', '') and 'Zweimal A' in r.get('error', '') and 'F-0' not in r.get('error', ''), (st, r))

st, r = speichern(farmer('Strich Eins', '-', -55.3), farmer('Strich Zwei', '.', -55.2))
check('Nummer ohne Inhalt („-“, „.“) zählt nicht: verschiedene Farmer fallen nicht zusammen', st == 200 and betrieb('Strich Eins', r)['id'] != betrieb('Strich Zwei', r)['id'], (st, r.get('error')))
o = L.call('containerimport_eudr_pruefen', {'dateien': [ort('Strich Drei', '-', -55.1)]})[1]['dateien'][0]['orte'][0]
check('… und Einlesen erkennt keinen Farmer an „-“', o['bekannt'] == '', o.get('bekannt'))
st, r = L.call('containerimport_eudr_nummern', {'land': 'PY', 'betriebe': [], 'offeneNummern': [], 'nummern': '-\n.\nE-600'})
check('… und als Farmer-Nummer am Container fällt sie weg', st == 200 and [z['nummer'] for z in r['zeilen']] == ['E-600'], (st, r))

# ---------- Nummern einem Container zuordnen ----------
c = container_anlegen(I, 'P-290001', akte='AK-29-1', lieferantNr='70012')
c2 = container_anlegen(I, 'P-290002', lieferantNr='70012')
VORSCHAU = {'land': 'PY', 'betriebe': [], 'offeneNummern': [], 'nummern': '12 345\nPY-2002\n77-001\n12345\n'}
check('Vorschau ohne Anmeldung: 401', Client('198.51.100.40').call('containerimport_eudr_nummern', VORSCHAU)[0] == 401)
st, r = L.call('containerimport_eudr_nummern', VORSCHAU)
zeilen = [(z['nummer'], z['status'], z['farmerNr']) for z in r.get('zeilen', [])]
check('Vorschau: bekannte Nummern mit ihrem Farmer, unbekannte als neu, Doppelte erkannt (andere Schreibweise zählt gleich)',
      st == 200 and zeilen == [('12 345', 'bekannt', 'F-0001'), ('PY-2002', 'bekannt', 'F-0002'), ('77-001', 'neu', ''), ('12345', 'doppelt', 'F-0001')], (st, zeilen, r.get('error')))
st, r = L.call('containerimport_eudr_nummern', {**VORSCHAU, 'betriebe': [uno['id']], 'offeneNummern': ['77001']})
check('Vorschau kennt den Stand des Fensters: schon zugeordnet, schon vermerkt', [z['status'] for z in r.get('zeilen', [])] == ['zugeordnet', 'bekannt', 'offen', 'doppelt'], r)
check('Vorschau speichert nichts', container(stand(I), 'P-290001')['rev'] == c['rev'])
check('Vorschau: zu viele Nummern oder unsinnige Werte 422', L.call('containerimport_eudr_nummern', {**VORSCHAU, 'nummern': '\n'.join(str(n) for n in range(501))})[0] == 422
      and L.call('containerimport_eudr_nummern', {**VORSCHAU, 'nummern': {'x': 1}})[0] == 422)

st, r = I.call('containerimport_eudr_sendung_save', {**c, 'betriebe': [uno['id']], 'offeneNummern': ['77-001', 'py 2002', '77001']})
c = container(r, 'P-290001')
check('Container speichern: vermerkte Nummern eines bekannten Farmers werden zugeordnet, Doppelte nur einmal vermerkt',
      st == 200 and set(c['betriebe']) == {uno['id'], dos['id']} and c['offeneNummern'] == ['77-001'], (st, r.get('error'), c.get('betriebe'), c.get('offeneNummern')))
p = c['farmerPruefung']
check('Gesamtprüfung je Container: alle Farmer und Nummern ohne Unterlagen gezählt, rot solange Unterlagen fehlen',
      [p['gesamt'], p['inOrdnung'], p['ohneUnterlagen'], p['ampel']] == [3, 1, 1, 'rot'] and p['themen'].get('gegenpruefung') == {'offen': 1}, p)
I.call('containerimport_eudr_gegenpruefung', {'id': dos['id'], 'portal': 'gnw', 'datum': stand(I)['heute'], 'ergebnis': 'befund'})
p = container(stand(I), 'P-290001')['farmerPruefung']
check('Gesamtprüfung trennt je Thema nach Stufe: ein Befund ist kritisch, nicht „offen“', p['themen'].get('gegenpruefung') == {'kritisch': 1}, p['themen'])
geo = next(k for k in c['profil']['kriterien'] if k['id'] == 'geo')
check('Risikoprofil: fehlende Unterlagen sind kritisch und nennen die Nummer', geo['stand'] == 'kritisch' and 'Nr. 77-001' in geo['betriebe'] and c['profil']['vernachlaessigbar'] == 'nein', geo)
check('Container heißt weiter nach der Partienummer (Dateiname, Protokoll)', c['name'] == 'P-290001')

st, r = I.call('containerimport_eudr_sendung_save', {**c2, 'offeneNummern': ['77-001']})
c2 = container(r, 'P-290002')
st, r = I.call('containerimport_eudr_sendung_abschluss', {'id': c2['id'], 'rev': c2['rev'], 'ergebnis': 'nicht_vernachlaessigbar', 'begruendung': 'Unterlagen fehlen'})
check('Container mit fehlenden Unterlagen lässt sich nur als „nicht vernachlässigbar“ abschließen', st == 200 and container(r, 'P-290002')['abschluss']['ergebnis'] == 'nicht_vernachlaessigbar', (st, r.get('error')))
st, r = speichern(farmer('Estancia Siete', '77001', -57.1))
siete = betrieb('Estancia Siete', r)
c, c2n = container(r, 'P-290001'), container(r, 'P-290002')
check('Farmer mit einer vermerkten Nummer angelegt: dem offenen Container selbsttätig zugeordnet, der Vermerk ist weg',
      siete['id'] in c['betriebe'] and c['offeneNummern'] == [] and c['farmerPruefung']['gesamt'] == 3 and c['farmerPruefung']['ohneUnterlagen'] == 0, (c['betriebe'], c['offeneNummern']))
check('abgeschlossener Container bleibt, wie er abgeschlossen wurde (GR-106)', c2n['offeneNummern'] == ['77-001'] and c2n['betriebe'] == [] and c2n['rev'] == c2['rev'] + 1, c2n)
check('Übersicht: die Nummer gilt nicht mehr als „Unterlagen fehlen“, auch nicht beim abgeschlossenen Container', all(o['nummer'] != '77-001' for o in r['offeneNummern']), r['offeneNummern'])
verlauf = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll nennt die selbsttätige Zuordnung', 'Farmer-Nummern an 1 Container zugeordnet' in verlauf, verlauf[:300])

st, r = I.call('containerimport_eudr_sendung_save', {**c, 'offeneNummern': ['X-1']})
st2, r2 = I.call('containerimport_eudr_sendung_save', {**container(r, 'P-290001'), 'offeneNummern': []})
check('vermerkte Nummer wieder entfernen (Tippfehler)', st == 200 and container(r, 'P-290001')['offeneNummern'] == ['X-1'] and st2 == 200 and container(r2, 'P-290001')['offeneNummern'] == [], (st, st2))
st, r = I.call('containerimport_eudr_sendung_save', {**container(r2, 'P-290001'), 'offeneNummern': ['NEU-1']})
st2, r2 = I.call('containerimport_eudr_sendung_save', {k: v for k, v in container(r, 'P-290001').items() if k != 'offeneNummern'})
check('ältere Seite ohne das Feld: vermerkte Nummern bleiben', st2 == 200 and container(r2, 'P-290001')['offeneNummern'] == ['NEU-1'], (st2, r2.get('error')))
I.call('containerimport_eudr_sendung_save', {**container(r2, 'P-290001'), 'offeneNummern': []})

doc = _json(storage_raw('containerimport-eudr-sendungen'))
for s in doc['liste']:
    if s['partie'] == 'P-290002': s.pop('offeneNummern')
storage_write('containerimport-eudr-sendungen', doc)
c2n = container(stand(I), 'P-290002')
check('Container aus der Zeit vor den vermerkten Nummern: lesbar, ohne Vermerk (GR-006)', c2n['offeneNummern'] == [] and c2n['farmerPruefung']['ampel'] == 'rot', c2n)

c3 = container_anlegen(I, 'P-290003', lieferantNr='70012', offeneNummern=['88-001'])
I.call('containerimport_eudr_sendung_save', {**c3, 'aktiv': False})
c3 = container(stand(I), 'P-290003')
st, r = speichern(farmer('Estancia Ocho', '88-001', -54.9))
check('archivierter Container wird nicht selbsttätig zugeordnet', st == 200 and container(r, 'P-290003')['betriebe'] == [] and container(r, 'P-290003')['rev'] == c3['rev'], (st, container(r, 'P-290003')))

# ---------- Schlachthof: Vorschlag ----------
st, r = I.call('containerimport_schlachthof_save', {'id': '', 'rev': 0, 'name': 'Werk Beispiel', 'lieferantNr': '70012', 'land': 'PY'})
hof = r['id']
c = container(stand(I), 'P-290001')
I.call('containerimport_eudr_sendung_save', {**c, 'schlachthof': hof})

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []
    pg = seite(br, 'ina', errs, fremd)
    zeile = pg.locator('#ci-sendungen tr:has-text("P-290001")')
    check('Containerliste: Akten- und Partienummer gleichrangig vorn', zeile.locator('.ci-name').first.inner_text() == 'Akte AK-29-1 · Partie P-290001', zeile.inner_text())
    check('Containerliste: Gesamtprüfung der Farmer mit dem, was fehlt, je Thema kritisch und offen getrennt', '1 von 3 in Ordnung' in zeile.inner_text()
          and 'eigene Prüfung kritisch: 1 · eigene Prüfung offen: 1' in zeile.inner_text()
          and 'kein Farmer' in pg.inner_text('#ci-sendungen tr:has-text("P-290002")'), zeile.inner_text())
    pg.fill('#ci-suche', 'ak-29-1'); pg.wait_for_function("document.querySelectorAll('#ci-sendungen tbody tr').length === 1")
    pg.fill('#ci-suche', '')

    zeile.click(); pg.wait_for_selector('#dlg-sendung[open]')
    check('Fenster „Container“: Überschrift mit Akten- und Partienummer, Gesamtprüfung', pg.inner_text('#sendung-titel') == 'Akte AK-29-1 · Partie P-290001'
          and 'Gesamtprüfung: 1 von 3 in Ordnung' in pg.inner_text('#dlg-sendung'), pg.inner_text('#sendung-titel'))
    check('Fenster „Container“: zugeordnete Farmer mit beiden Nummern', all(t in pg.inner_text('#sendung-farmer') for t in ('F-0001', 'Nr. 12.345', 'Estancia Siete')), pg.inner_text('#sendung-farmer'))
    pg.fill('#nummern-text', 'C-4\nNEU-9\n12345'); pg.click('#nummern-pruefen'); pg.wait_for_selector('#nummern-vorschau li')
    check('Nummern einfügen: Vorschau vor dem Übernehmen', [t.strip() for t in pg.eval_on_selector_all('#nummern-vorschau li .ci-marke', 'ms => ms.map(m => m.textContent)')] == ['wird zugeordnet', 'unbekannt – Unterlagen fehlen', 'schon zugeordnet'],
          pg.inner_text('#nummern-vorschau'))
    shot(pg, os.path.join(SH, 'containerimport-farmer-nummern-1280.png'))
    pg.click('#nummern-ok'); pg.wait_for_selector('#sendung-farmer input[name=offeneNummern][value="NEU-9"]')
    pg.click('#dlg-sendung button[type=submit]')
    pg.wait_for_function("document.querySelector('#dlg-sendung').innerText.includes('Gesamtprüfung: 1 von 5 in Ordnung')")
    c = container(stand(I), 'P-290001')
    check('übernommen und gespeichert: bekannter Farmer zugeordnet, unbekannte Nummer vermerkt', betrieb('Estancia Cuatro')['id'] in c['betriebe'] and c['offeneNummern'] == ['NEU-9'], c)
    shot(pg, os.path.join(SH, 'containerimport-farmer-container-1280.png'))
    pg.click('#dlg-sendung [data-zu]')

    pg.click('#ci-sendung-neu'); pg.wait_for_selector('#dlg-sendung[open]')
    pg.fill('#dlg-sendung [name=lieferant]', 'Frigorifico Beispiel S.A. (70012)'); pg.locator('#dlg-sendung [name=lieferant]').blur()
    pg.wait_for_function("document.querySelector('#dlg-sendung [name=schlachthof]').options.length === 2")
    check('neuer Container: der zuletzt beim Lieferanten benutzte Schlachthof ist vorgeschlagen', pg.input_value('#dlg-sendung [name=schlachthof]') == hof)
    pg.click('#dlg-sendung [data-zu]')

    pg.click('[data-sicht="betriebe"]'); pg.wait_for_selector('#ci-betriebe')
    uebersicht = pg.inner_text('#ci-betriebe')
    check('Gesamtübersicht Farmer: beide Nummern, Container mit Akten- und Partienummer, Nummern ohne Unterlagen',
          all(t in uebersicht for t in ('F-0001', '12.345', 'Akte AK-29-1 · Partie P-290001', 'Unterlagen fehlen', 'NEU-9')), uebersicht)
    shot(pg, os.path.join(SH, 'containerimport-farmer-uebersicht-1280.png'))
    for suche, erwartet in (('F-0002', 'Estancia Dos'), ('77001', 'Estancia Siete'), ('NEU-9', 'Unterlagen fehlen')):
        pg.fill('#ci-suche', suche); pg.wait_for_function("document.querySelectorAll('#ci-betriebe tbody tr').length === 1")
        check(f'Gesamtübersicht: Suche „{suche}“ findet genau den einen Eintrag', erwartet in pg.inner_text('#ci-betriebe tbody'), pg.inner_text('#ci-betriebe tbody'))
    pg.fill('#ci-suche', 'P-290001'); pg.wait_for_function("document.querySelectorAll('#ci-betriebe tbody tr').length === 5")
    pg.fill('#ci-suche', ''); pg.click('#ci-betriebe tr:has-text("Estancia Dos")'); pg.wait_for_selector('#dlg-betrieb[open]')
    check('Fenster „Farmer“: eigene Nummer und Container', 'F-0002' in pg.inner_text('#dlg-betrieb .dlg-head') and 'Akte AK-29-1 · Partie P-290001' in pg.inner_text('#dlg-betrieb'), pg.inner_text('#dlg-betrieb .dlg-head'))
    pg.context.close()

    le = seite(br, 'lea', errs, fremd)
    le.click('#ci-sendungen tr:has-text("P-290001")'); le.wait_for_selector('#dlg-sendung[open]')
    check('nur ansehen: Gesamtprüfung sichtbar, kein Feld zum Einfügen von Nummern', 'Gesamtprüfung' in le.inner_text('#dlg-sendung') and le.locator('#nummern-text').count() == 0)
    le.context.close()

    m = seite(br, 'ina', errs, fremd, {'width': 390, 'height': 844}, 'dark')
    check('Handy 390 px: Containerliste ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    m.click('#ci-sendungen tr:has-text("P-290001")'); m.wait_for_selector('#dlg-sendung[open]')
    m.fill('#nummern-text', 'C-4\nNEU-10'); m.click('#nummern-pruefen'); m.wait_for_selector('#nummern-vorschau li')
    check('Handy 390 px: Fenster „Container“ ohne waagerechtes Scrollen', m.evaluate("document.querySelector('#dlg-sendung form').scrollWidth <= document.querySelector('#dlg-sendung form').clientWidth"))
    shot(m, os.path.join(SH, 'containerimport-farmer-container-390-dunkel.png'))
    m.click('#dlg-sendung [data-zu]')
    m.click('[data-sicht="betriebe"]'); m.wait_for_selector('#ci-betriebe')
    check('Handy 390 px: Gesamtübersicht ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(m, os.path.join(SH, 'containerimport-farmer-uebersicht-390-dunkel.png'))
    m.context.close()
    br.close()

check('keine JavaScript-Fehler', not errs, errs)
ende()
