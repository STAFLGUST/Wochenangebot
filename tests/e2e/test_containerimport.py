"""Modul Container-Import, Reiter EUDR (app/module/containerimport/, Oberfläche containerimport.intern, Auftrag des Inhabers
18.11.2026): Herkunftsbetriebe mit Geolokalisierung, Sendungen, Risikoprofil, GeoJSON für das EU-Informationssystem.
Geprüft: Register (fertig und produktiv unter container-import.dashboard-stafl.de, Kachel verfügbar, keine Testfreigabe über die
Modulverwaltung, ohne Tester-Eintrag erreichbar); Rechte serverseitig (ohne Anmeldung kein Zugriff, ohne „EUDR
ansehen“ 403, nur ansehen: kein Speichern, ohne CSRF 403, GET auf schreibende Aktion 405); Dateien prüfen ohne zu speichern
(Lieferanten-GeoJSON mit Fehlerbildern: Selbstüberschneidung, vertauschte Koordinaten, Linie, falsch geschriebene
Eigenschaften, Fläche als Text; Bericht mit UTM-Koordinaten gegen eine unabhängige Umrechnung; Runden auf 6 Stellen, Umlauf);
Speichern, Wiedererkennen, Revision (409); Risikoprofil (kritisch bei fehlerhafter Geolokalisierung, offen ohne Nachweise,
Gegenprüfung mit Befund und jüngerer Entwarnung); Abschluss (nie mit kritischem Kriterium, offen nur mit Begründung,
Schnappschuss bleibt bei späteren Änderungen, GR-106; danach nur noch Sorgfaltserklärung änderbar; wieder öffnen mit Grund);
Export (Eigenschaften in vorgeschriebener Schreibweise, Fläche als Zahl, fehlerhafte Flächen ausgelassen).
Originale der Unterlagen im Eingang des QM-Systems (Schnittstelle des QM, nicht doppelt, mehrere Teile, gesperrte Dateiart).
Oberfläche: Bericht als PDF im Browser lesen (pdf.js, erfundener Bericht im Aufbau des Lieferanten), Erklärung ohne
Koordinaten wird abgewiesen, Übernehmen, Karte, Fenster, Datei für TRACES; Desktop und 390 px, hell und dunkel; nur ansehen.
Alle Betriebe sind erfunden (GR-007)."""
import base64
import hashlib
import json
import math
import struct
import zlib
import os
import re
import tempfile
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH, FIX, shot, storage_raw, storage_write, _json

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i and not c else ''))


def utm_nach_wgs84(rechts, hoch, zone, sued=True):
    """Unabhängige Gegenrechnung (Krüger-Reihen nach Karney) – der Server rechnet mit einer anderen Formel."""
    a = 6378137.0; f = 1 / 298.257223563; n = f / (2 - f); k0 = 0.9996
    A = a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64)
    b = [None, n / 2 - 2 * n * n / 3 + 37 * n ** 3 / 96, n * n / 48 + n ** 3 / 15, 17 * n ** 3 / 480]
    d = [None, 2 * n - 2 * n * n / 3 - 2 * n ** 3, 7 * n * n / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15]
    xi = (hoch - (10000000.0 if sued else 0)) / (k0 * A); eta = (rechts - 500000.0) / (k0 * A)
    xi2 = xi - sum(b[j] * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j in (1, 2, 3))
    eta2 = eta - sum(b[j] * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j in (1, 2, 3))
    chi = math.asin(math.sin(xi2) / math.cosh(eta2))
    return (math.degrees(math.atan2(math.sinh(eta2), math.cos(xi2))) + zone * 6 - 183, math.degrees(chi + sum(d[j] * math.sin(2 * j * chi) for j in (1, 2, 3))))


def pdf_bauen(seiten):
    """Einfache PDF-Datei aus Textstücken je Seite [(x, y, Text), …] – für den erfundenen Bericht."""
    teile = [b'<< /Type /Catalog /Pages 2 0 R >>', None, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for seite in seiten:
        inhalt = '\n'.join(f'BT /F1 8 Tf {x} {y} Td ({t.replace("(", "[").replace(")", "]")}) Tj ET' for x, y, t in seite).encode('latin-1')
        teile.append(b'<< /Length %d >>\nstream\n' % len(inhalt) + inhalt + b'\nendstream')
        teile.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1400 842] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>' % len(teile))
        kids.append(len(teile))
    teile[1] = ('<< /Type /Pages /Count %d /Kids [%s] >>' % (len(kids), ' '.join(f'{k} 0 R' for k in kids))).encode()
    aus = b'%PDF-1.4\n'; stellen = []
    for i, t in enumerate(teile):
        stellen.append(len(aus)); aus += b'%d 0 obj\n' % (i + 1) + t + b'\nendobj\n'
    xref = len(aus)
    aus += b'xref\n0 %d\n0000000000 65535 f \n' % (len(teile) + 1) + b''.join(b'%010d 00000 n \n' % s for s in stellen)
    return aus + b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(teile) + 1, xref)


# Erfundener Betrieb: Rechteck 2000 m × 1500 m in UTM 21S, im Uhrzeigersinn (der Server dreht den Umlauf)
UTM = [(500000.00, 7400000.00), (500000.00, 7401500.00), (502000.00, 7401500.00), (502000.00, 7400000.00), (500000.00, 7400000.00)]
ORT = {'name': 'Estancia Beispiel', 'erzeuger': 'AGROGANADERA MUSTER S.A.', 'land': 'PY', 'kennung': '990010001', 'region': 'BEISPIELDEPARTAMENTO', 'ort': 'MUSTERORT',
       'flaecheAngabe': 300.2, 'bericht': {'datum': '2026-11-04', 'entwaldung': 'konform', 'entwaldungHa': 0, 'schutzgebiet': 'konform', 'indigen': 'konform',
                                           'landnutzung': 'unbekannt', 'umwelt': 'unbekannt', 'bilderBis': 2025},
       'koordinaten': {'system': 'utm', 'zone': 21, 'sued': True, 'punkte': [list(p) for p in UTM]}}
BERICHT = {'art': 'bericht', 'datei': 'Compliance_Report_Estancia_Beispiel.pdf', 'sha256': 'a' * 64, 'anbieter': 'Hendata & Global Canopy', 'bezug': 'UTM 21S', 'lieferant': 'Frigorifico Beispiel', 'ort': ORT}
GEOJSON = open(os.path.join(FIX, 'containerimport', 'lieferant.geojson'), encoding='utf-8').read()
DATEI = {'art': 'geojson', 'datei': 'lieferant.geojson', 'sha256': 'b' * 64, 'land': 'PY', 'lieferant': 'Frigorifico Beispiel', 'text': GEOJSON}
SENDUNG = {'id': '', 'rev': 0, 'partie': 'P-260001', 'akte': 'AK-2026-014', 'stand': 'unterwegs', 'nummer': 'FB26-001', 'lieferantNr': '', 'lieferant': 'Frigorifico Beispiel', 'land': 'PY', 'ware': 'Rindfleisch, gekühlt, ohne Knochen', 'hs': '0201', 'mengeKg': '12.345,60',
           'container': 'TEST 123456-7', 'schlachtVon': '2026-11-02', 'schlachtBis': '2026-11-05', 'lose': '2101, 2102, 2103', 'betriebe': [], 'notiz': '',
           'nachweis': {'erklaerung': '', 'rueckverfolgung': 'offen', 'haltung': 'offen', 'legalitaet': 'offen'}, 'dds': {'referenz': '', 'datum': ''}}

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)

# ---------- Register: produktiv (Entscheidung des Inhabers 18.11.2026) ----------
cm = next((m for m in A.call('module_status')[1]['module'] if m['id'] == 'containerimport'), None)
check('Register: Container-Import fertig und produktiv, Adresse container-import.dashboard-stafl.de/module/containerimport/, Kachel verfügbar',
      cm and cm['oberflaechen'][0]['entwicklung'] == 'fertig' and cm['oberflaechen'][0]['freigabe'] == 'produktiv'
      and cm['kachel']['status'] == 'verfuegbar' and cm['kachel']['zugang'] is True and cm['kachel']['ziel'] == 'containerimport.intern'
      and cm['kachel']['adresse'] == 'https://container-import.dashboard-stafl.de/module/containerimport/', cm)
st, r = A.call('modul_freigabe_save', {'bereich': 'containerimport.intern', 'freigabe': 'test', 'grund': 'Test'})
check('Produktivbereich: keine Testfreigabe über die Modulverwaltung (nur über ein Release)', st == 422, (st, r))

# Lieferanten in den Stammdaten der Verwaltung (wie nach dem Einlesen aus der Warenwirtschaft) – mit Angaben, die der
# Container-Import nie sehen darf (Umsatz, Ort)
LIEFERANTEN = [{'nr': '70012', 'name': 'Frigorifico Beispiel S.A.', 'kurz': 'FRIGOBSP', 'ort': 'Asunción', 'umsatzJahr': '1.234.567,89 €'},
               {'nr': '70020', 'name': 'Carnes del Sur Ltda.', 'kurz': 'CARNESUR', 'ort': 'Montevideo'}, {'nr': '70031', 'name': '', 'kurz': 'OHNENAME'}]
st, r = A.call('lieferanten_save', {'rev': 0, 'groups': LIEFERANTEN, 'quelle': 'Test'})
check('Stammdaten: drei Lieferanten in der Verwaltung angelegt', st == 200 and len(r.get('groups', [])) == 3, (st, r.get('error')))

USERS = {'ina': ('Ina Import', 'editor', 'Editor-Zugang-88', ['containerimport.eudr_sehen', 'containerimport.eudr_bearbeiten']),
         'lea': ('Lea Leser', 'viewer', 'Leser-Zugang-55', ['containerimport.eudr_sehen']),
         'ole': ('Ole Ohne', 'editor', 'Editor-Zugang-77', [])}
uid = {}
for user, (name, role, pw, grant) in USERS.items():
    A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    uid[user] = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == user)
    if grant:
        A.call('user_save', {'id': uid[user], 'name': name, 'role': role, 'active': True, 'grant': grant, 'deny': []})


def login(user):
    c = Client('198.51.100.' + str(10 + list(USERS).index(user)))
    code, r = c.call('login', {'username': user, 'password': USERS[user][2]})
    assert code == 200, (user, code, r)
    return c


I, L, O = login('ina'), login('lea'), login('ole')

# ---------- Rechte ----------
st, r = Client('198.51.100.30').call('containerimport_start')
check('ohne Anmeldung: kein Zugriff (401)', st == 401 and 'betriebe' not in r, (st, r))
st, r = O.call('containerimport_start')
check('Modulzugang ohne „EUDR ansehen“: 403', st == 403 and 'Berechtigung' in r.get('error', ''), (st, r))
check('ohne „EUDR ansehen“: auch prüfen, Farmer-Nummern auflösen und exportieren 403', O.call('containerimport_eudr_pruefen', {'dateien': [DATEI]})[0] == 403
      and O.call('containerimport_eudr_nummern', {'land': 'PY', 'nummern': '1'})[0] == 403 and O.call('containerimport_eudr_export&sendung=x')[0] == 403)
st, r = L.call('containerimport_start')
check('nur ansehen: Stand ohne Recht zu bearbeiten, leer', st == 200 and r['rechte'] == {'bearbeiten': False, 'whisp': False} and r['betriebe'] == [] and r['sendungen'] == [], (st, r))
check('nur ansehen: Speichern 403', [L.call(a, {})[0] for a in ('containerimport_eudr_betriebe_save', 'containerimport_eudr_sendung_save', 'containerimport_eudr_gegenpruefung', 'containerimport_eudr_sendung_abschluss')] == [403] * 4)
csrf = I.csrf; I.csrf = ''
check('Speichern ohne CSRF: 403', I.call('containerimport_eudr_sendung_save', SENDUNG)[0] == 403)
check('Farmer-Nummern auflösen ohne CSRF: 403', I.call('containerimport_eudr_nummern', {'land': 'PY', 'nummern': '1'})[0] == 403)
I.csrf = csrf
check('schreibende Aktionen per GET: 405', [I.call(a)[0] for a in ('containerimport_eudr_pruefen', 'containerimport_eudr_betriebe_save', 'containerimport_eudr_sendung_save')] == [405] * 3)
st, r = I.call('containerimport_start')
check('Whisp-Abfrage ohne Zugangsschlüssel auf dem Server: nicht angeboten, Aktion 503', r['rechte'] == {'bearbeiten': True, 'whisp': False}
      and I.call('containerimport_eudr_whisp', {'id': 'x'})[0] == 503 and L.call('containerimport_eudr_whisp', {'id': 'x'})[0] == 403, r.get('rechte'))
check('Stand: Lieferanten der Stammdaten zur Auswahl – nur Nummer und Name, nach Name sortiert, nur für Bearbeiter; Stände des Containers',
      r['lieferanten'] == [{'nr': '70020', 'name': 'Carnes del Sur Ltda.'}, {'nr': '70012', 'name': 'Frigorifico Beispiel S.A.'}, {'nr': '70031', 'name': 'OHNENAME'}]
      and L.call('containerimport_start')[1]['lieferanten'] == [] and list(r['staende']) == ['gekauft', 'unterwegs', 'dokumente', 'angekommen'] and 'Asunción' not in json.dumps(r, ensure_ascii=False) and '1.234.567' not in json.dumps(r), r.get('lieferanten'))
check('bearbeiten: Stand mit Ländern und Portalen', st == 200 and r['rechte']['bearbeiten'] and r['laender']['PY'] == {'name': 'Paraguay', 'klasse': 'standard'}
      and r['laender']['NZ'] == {'name': 'Neuseeland', 'klasse': None}   # wählbar, Einstufung nicht hinterlegt
      and set(r['portale']) == {'gnw', 'whisp', 'sonst'} and r['portale']['gnw']['name'] == 'Global Nature Watch', (st, r))

# ---------- Dateien prüfen (ohne zu speichern) ----------
st, r = L.call('containerimport_eudr_pruefen', {'dateien': [DATEI, BERICHT]})
gj, be = (r.get('dateien') or [{}, {}])[:2]
orte = {o['name']: o for o in gj.get('orte', [])}
check('GeoJSON: vier Flächen gelesen, die Linie abgewiesen', st == 200 and set(orte) == {'Estancia Ejemplo Norte', 'Estancia Ejemplo Acht', 'Corral Ejemplo', 'Estancia Vertauscht'}
      and len(gj['fehler']) == 1 and 'LineString' in gj['fehler'][0], (st, gj.get('fehler'), list(orte)))
nord = orte.get('Estancia Ejemplo Norte', {})
ring = (nord.get('geometrie') or {}).get('coordinates', [[]])[0]
check('GeoJSON: Koordinaten auf 6 Nachkommastellen gerundet, Umriss geschlossen', ring and ring[0] == ring[-1] == [-57.01, -23.5] and all(round(v, 6) == v for p in ring for v in p), ring)
check('GeoJSON: Fläche berechnet (rund 166 ha) und Abweichung zur Angabe (150,12 ha) gemeldet', 165 < nord.get('flaeche', 0) < 168 and nord['stand'] == 'hinweis' and [b['code'] for b in nord['befunde']] == ['flaeche'], (nord.get('flaeche'), nord.get('befunde')))
check('GeoJSON: Selbstüberschneidung ist ein Fehler', orte['Estancia Ejemplo Acht']['stand'] == 'fehler' and 'schnitt' in [b['code'] for b in orte['Estancia Ejemplo Acht']['befunde']], orte['Estancia Ejemplo Acht']['befunde'])
check('GeoJSON: vertauschte Länge und Breite fallen durch die Lageprüfung auf', orte['Estancia Vertauscht']['stand'] == 'fehler' and 'lage' in [b['code'] for b in orte['Estancia Vertauscht']['befunde']], orte['Estancia Vertauscht']['befunde'])
punkt = orte['Corral Ejemplo']
check('GeoJSON: Punkt mit Land der Datei, Erzeuger trotz falscher Schreibweise gelesen, Fläche als Text gemeldet',
      punkt['geometrie']['type'] == 'Point' and punkt['land'] == 'PY' and punkt['erzeuger'] == 'Ganadera Ejemplo S.A.' and punkt['flaeche'] == 3
      and any('Anführungszeichen' in h for h in gj['hinweise']) and sum('anders geschrieben' in h for h in gj['hinweise']) == 2, (punkt, gj['hinweise']))
bo = (be.get('orte') or [{}])[0]
soll = [utm_nach_wgs84(e, n, 21) for e, n in UTM]
ist = (bo.get('geometrie') or {}).get('coordinates', [[]])[0]
check('Bericht: UTM 21S stimmt mit der unabhängigen Umrechnung überein (unter 0,2 m)', len(ist) == 5 and all(min(abs(p[0] - s[0]) + abs(p[1] - s[1]) for s in soll) < 2e-6 for p in ist), (ist, soll))
check('Bericht: Fläche 300 ha (Gitter) → rund 300,24 ha am Boden, Umlauf gegen den Uhrzeigersinn gedreht, kein Befund',
      300.1 < bo.get('flaeche', 0) < 300.4 and bo['stand'] == 'ok' and ist[1][0] > ist[0][0] and bo['bekannt'] == '', (bo.get('flaeche'), bo.get('befunde'), ist))
check('Bericht: Angaben und Quelle übernommen', bo['bericht']['entwaldung'] == 'konform' and bo['bericht']['bilderBis'] == 2025 and bo['quelle']['bezug'] == 'UTM 21S'
      and bo['quelle']['sha256'] == 'a' * 64 and bo['ampel'] == 'gelb', (bo.get('bericht'), bo.get('quelle'), bo.get('ampel')))
for name, d, text in (('kein JSON', {**DATEI, 'text': '{"type": "FeatureCollection", '}, 'kein gültiges JSON'), ('keine Flächen', {**DATEI, 'text': '{"type":"FeatureCollection","features":[]}'}, 'keine Flächen'),
                      ('ohne UTM-Zone', {**BERICHT, 'ort': {**ORT, 'koordinaten': {'system': 'utm', 'punkte': ORT['koordinaten']['punkte']}}}, 'UTM-Zone'),
                      ('ohne Land', {**BERICHT, 'ort': {**ORT, 'land': ''}}, 'Land fehlt')):
    st, r = L.call('containerimport_eudr_pruefen', {'dateien': [d]})
    check(f'Prüfen: {name} wird verständlich gemeldet', st == 200 and r['dateien'][0]['orte'] == [] and text in ' '.join(r['dateien'][0]['fehler']), (st, r))
FORMEN = json.dumps({'type': 'FeatureCollection', 'features': [
    {'type': 'Feature', 'properties': {'ProductionPlace': 'Mit Loch'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-57, -23], [-56.9, -23], [-56.9, -23.1], [-57, -23.1], [-57, -23]], [[-56.96, -23.04], [-56.94, -23.04], [-56.94, -23.06], [-56.96, -23.04]]]}},
    {'type': 'Feature', 'properties': {'ProductionPlace': 'Zwei Teile'}, 'geometry': {'type': 'MultiPolygon', 'coordinates': [[[[-57, -24], [-56.99, -24], [-56.99, -24.01], [-57, -24]]], [[[-56.9, -24], [-56.89, -24], [-56.89, -24.01], [-56.9, -24]]]]}},
    {'type': 'Feature', 'properties': {}, 'geometry': {'type': 'MultiPoint', 'coordinates': [[-57.3, -23.3], [-57.4, -23.4]]}}]})
st, r = L.call('containerimport_eudr_pruefen', {'dateien': [{**DATEI, 'datei': 'formen.geojson', 'text': FORMEN},
                                                           {'art': 'koordinaten', 'datei': '', 'land': 'UY', 'ort': {'name': 'Campo Ejemplo', 'koordinaten': {'system': 'wgs84', 'punkte': [[-56, -32], [-55.99, -32], [-55.99, -32.01], [-56, -32.01]]}}}]})
fo = {o['name']: o for d in r.get('dateien', []) for o in d['orte']}
check('Formen: Loch ist ein Fehler, zwei Teilflächen bleiben ein Farmer, mehrere Punkte werden einzelne Farmer mit Ersatznamen', st == 200 and [b['code'] for b in fo['Mit Loch']['befunde']] == ['loch']
      and fo['Zwei Teile']['geometrie']['type'] == 'MultiPolygon' and fo['Zwei Teile']['stand'] == 'ok' and 100 < fo['Zwei Teile']['flaeche'] < 120
      and {'Fläche 3.1 aus formen.geojson', 'Fläche 3.2 aus formen.geojson'} <= set(fo), (st, {k: (v['stand'], v['flaeche'], v['befunde']) for k, v in fo.items()}))
campo = fo.get('Campo Ejemplo', {})
check('eingefügte Koordinaten (WGS84): offener Umriss geschlossen und als Korrektur vermerkt; Land außerhalb der Liste bleibt erhalten', campo.get('land') == 'UY' and campo['quelle']['korrekturen'] == ['offen']
      and [b['code'] for b in campo['befunde']] == ['korrektur'] and campo['eingabe']['quelle']['korrekturen'] == ['offen'] and len(campo['geometrie']['coordinates'][0]) == 5, campo)
check('Prüfen: ohne Dateien 422', L.call('containerimport_eudr_pruefen', {'dateien': []})[0] == 422)
check('Prüfen speichert nichts', L.call('containerimport_start')[1]['betriebe'] == [])

# ---------- Sendung und Betriebe speichern ----------
st, r = I.call('containerimport_eudr_sendung_save', SENDUNG)
sid = r.get('id')
check('Container angelegt, Menge in deutscher Schreibweise gelesen', st == 200 and r['sendungen'][0]['nummer'] == 'FB26-001' and r['sendungen'][0]['mengeKg'] == 12345.6, (st, r))
c = (r.get('sendungen') or [{}])[0]
check('Container: Partie-, Akten- und Containernummer, Stand; heißt nach seiner Partienummer; Lieferant als freier Text ohne Verknüpfung',
      [c.get(k) for k in ('partie', 'akte', 'container', 'stand', 'name', 'lieferantNr', 'lieferant')] == ['P-260001', 'AK-2026-014', 'TEST 123456-7', 'unterwegs', 'P-260001', '', 'Frigorifico Beispiel'], c)
check('Containernummer: falsche Prüfziffer als Hinweis, gespeichert wird die Eingabe', c.get('containerPruefung') == 'pruefziffer', c.get('containerPruefung'))
check('Partienummer ist je Container eindeutig, auch bei anderer Schreibweise (klein, Leerzeichen, anderer Strich, geschütztes Leerzeichen): 422',
      [I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': x})[0] for x in ('p-260001', 'P 260001', 'P–260001', 'P-260001\u00a0')] == [422] * 4)
check('Stand außerhalb der Liste 422, unbekannter Lieferant der Stammdaten 422', I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-9', 'stand': 'verschollen'})[0] == 422
      and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-9', 'lieferantNr': '99999'})[0] == 422)
st, r = I.call('containerimport_eudr_sendung_save', {'id': '', 'rev': 0, 'partie': 'P-260003', 'lieferantNr': '70012', 'lieferant': 'wird ersetzt', 'land': 'PY', 'container': 'msku 907032-3'})
c3 = next((x for x in r.get('sendungen', []) if x['partie'] == 'P-260003'), {})
check('Container mit Lieferant aus den Stammdaten: Name aus den Stammdaten, Stand „gekauft“, Auftragsnummer nicht nötig, Containernummer gültig',
      st == 200 and [c3.get(k) for k in ('lieferantNr', 'lieferant', 'stand', 'nummer', 'containerPruefung', 'name')] == ['70012', 'Frigorifico Beispiel S.A.', 'gekauft', '', 'ok', 'P-260003'], (st, r.get('error'), c3))
st, r = I.call('containerimport_eudr_sendung_save', {'id': '', 'rev': 0, 'partie': 'P-260004', 'lieferantNr': '70031', 'land': 'UY'})
check('Lieferant ohne Namen in den Stammdaten: der Kurzname steht am Container', st == 200 and next(x for x in r['sendungen'] if x['partie'] == 'P-260004')['lieferant'] == 'OHNENAME', (st, r.get('error')))
# Lieferant verschwindet aus den Stammdaten: die gespeicherte Verknüpfung bleibt beim nächsten Speichern, eine neue geht nicht
A.call('lieferanten_save', {'rev': 1, 'groups': LIEFERANTEN[1:], 'quelle': 'Test'})
st, r = I.call('containerimport_eudr_sendung_save', {**c3, 'akte': 'AK-3'})
c3 = next((x for x in r.get('sendungen', []) if x['partie'] == 'P-260003'), {})
check('Lieferant nicht mehr in den Stammdaten: Verknüpfung und Name bleiben am Container, neu wählen lässt er sich nicht',
      st == 200 and c3.get('lieferantNr') == '70012' and c3.get('lieferant') == 'Frigorifico Beispiel S.A.' and c3.get('akte') == 'AK-3'
      and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-9', 'lieferantNr': '70012'})[0] == 422, (st, r.get('error'), c3))
# Lieferant wird in den Stammdaten umbenannt: ein Container in Arbeit übernimmt den Namen beim nächsten Speichern
A.call('lieferanten_save', {'rev': 2, 'groups': [{**LIEFERANTEN[0], 'name': 'Frigorifico Beispiel Nuevo S.A.'}] + LIEFERANTEN[1:], 'quelle': 'Test'})
st, r = I.call('containerimport_eudr_sendung_save', c3)
c3 = next((x for x in r.get('sendungen', []) if x['partie'] == 'P-260003'), {})
check('Lieferant in den Stammdaten umbenannt: der Container in Arbeit übernimmt den neuen Namen beim Speichern', st == 200 and c3.get('lieferant') == 'Frigorifico Beispiel Nuevo S.A.', (st, r.get('error'), c3))
A.call('lieferanten_save', {'rev': 3, 'groups': LIEFERANTEN, 'quelle': 'Test'})
# Eintrag aus der Zeit vor dem Umbau (ohne Partienummer, Akte, Stand, Verknüpfung): bleibt lesbar, heißt nach der Auftragsnummer
doc = _json(storage_raw('containerimport-eudr-sendungen'))
alt = next(x for x in doc['liste'] if x['partie'] == 'P-260004')
for k in ('partie', 'akte', 'stand', 'lieferantNr'): del alt[k]
alt['nummer'] = 'ALT-77'; alt['spaeter'] = {'schlachthof': 'x1'}   # ein Feld, das erst eine spätere Version kennt
storage_write('containerimport-eudr-sendungen', doc)
c4 = next(x for x in I.call('containerimport_start')[1]['sendungen'] if x['nummer'] == 'ALT-77')
check('Eintrag aus der Zeit vor dem Umbau: lesbar, heißt nach der Auftragsnummer, Stand „gekauft“, nicht verknüpft', [c4[k] for k in ('name', 'partie', 'akte', 'stand', 'lieferantNr')] == ['ALT-77', '', '', 'gekauft', ''], c4)
st, r = I.call('containerimport_eudr_sendung_save', {**c4, 'aktiv': False})
c4 = next((x for x in r.get('sendungen', []) if x['id'] == c4['id']), c4)
check('Eintrag aus der Zeit vor dem Umbau: lässt sich ohne Partienummer archivieren, Wiederherstellen und Speichern verlangen sie', st == 200 and c4['aktiv'] is False and c4['partie'] == ''
      and I.call('containerimport_eudr_sendung_save', {**c4, 'aktiv': True})[0] == 422, (st, r.get('error')))
check('Eintrag aus der Zeit vor dem Umbau: mit Partienummer heißt er nach ihr; Felder einer späteren Version bleiben beim Speichern erhalten',
      next(x for x in I.call('containerimport_eudr_sendung_save', {**c4, 'partie': 'P-260004'})[1]['sendungen'] if x['id'] == c4['id'])['name'] == 'P-260004'
      and next(x for x in _json(storage_raw('containerimport-eudr-sendungen'))['liste'] if x['id'] == c4['id'])['spaeter'] == {'schlachthof': 'x1'})
I.call('containerimport_eudr_sendung_save', {**next(x for x in I.call('containerimport_start')[1]['sendungen'] if x['partie'] == 'P-260003'), 'aktiv': False})
check('Container: Pflichtfelder und Datumsfolge geprüft (422)', I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': ''})[0] == 422 and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-9', 'lieferant': ''})[0] == 422
      and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'schlachtBis': '2026-11-01'})[0] == 422 and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'betriebe': ['gibt-es-nicht']})[0] == 422)
alle = [o['eingabe'] for o in list(orte.values()) + [bo]]   # wie die Oberfläche: genau das, was die Prüfung als Eingabe liefert
st, r = I.call('containerimport_eudr_betriebe_save', {'sendung': sid, 'betriebe': alle})
ids = {b['name']: b['id'] for b in r.get('betriebe', [])}
check('Farmer gespeichert und dem Container zugeordnet', st == 200 and len(ids) == 5 and set(r['sendungen'][0]['betriebe']) == set(ids.values()), (st, r.get('error'), ids))
st, r = L.call('containerimport_eudr_pruefen', {'dateien': [DATEI, BERICHT]})
check('erneutes Einlesen erkennt die Farmer wieder (Kennung bzw. Umriss)', st == 200 and [o['bekannt'] for d in r['dateien'] for o in d['orte']] == [ids[o['name']] for d in r['dateien'] for o in d['orte']], r)


def stand(c=None):
    return (c or I).call('containerimport_start')[1]


def profil(s):
    return {k['id']: k['stand'] for k in s['profil']['kriterien']}


def betrieb(name):
    return next(b for b in stand()['betriebe'] if b['name'] == name)


s = stand()['sendungen'][0]
check('Risikoprofil: fehlerhafte Geolokalisierung ist kritisch und nennt die Farmer', s['profil']['stand'] == 'kritisch' and profil(s)['geo'] == 'kritisch'
      and set(next(k for k in s['profil']['kriterien'] if k['id'] == 'geo')['betriebe']) == {'Estancia Ejemplo Acht', 'Estancia Vertauscht'}, s['profil'])
check('Risikoprofil: Paraguay Standardrisiko (Hinweis), Nachweise offen', profil(s)['land'] == 'hinweis' and [profil(s)[k] for k in ('rueckverfolgung', 'haltung', 'legalitaet', 'erklaerung', 'gegenpruefung')] == ['offen'] * 5, profil(s))
check('Abschluss „vernachlässigbar“ mit kritischem Kriterium: 422', I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'ergebnis': 'vernachlaessigbar', 'begruendung': 'x' * 40})[0] == 422)
st, r = I.call('containerimport_eudr_export&sendung=' + sid)
props = [f['properties'] for f in r.get('geojson', {}).get('features', [])]
check('Export: nur einreichbare Flächen, fehlerhafte ausgelassen', st == 200 and r['datei'] == 'EUDR_P-260001.geojson' and len(props) == 3 and set(r['ausgelassen']) == {'Estancia Ejemplo Acht', 'Estancia Vertauscht'}, (st, r))
check('Export: Eigenschaften in vorgeschriebener Schreibweise, Fläche als Zahl, Kennung im Ortsnamen',
      all(set(p) == {'ProducerName', 'ProducerCountry', 'ProductionPlace', 'Area'} and isinstance(p['Area'], (int, float)) and p['ProducerCountry'] == 'PY' for p in props)
      and 'Estancia Beispiel (990010001)' in [p['ProductionPlace'] for p in props], props)
check('Export: Umrisse geschlossen, 6 Nachkommastellen', all(f['geometry']['coordinates'][0][0] == f['geometry']['coordinates'][0][-1] and all(round(v, 6) == v for p in f['geometry']['coordinates'][0] for v in p)
                                                          for f in r['geojson']['features'] if f['geometry']['type'] == 'Polygon'))
st, r = L.call('containerimport_eudr_export&betrieb=' + ids['Estancia Beispiel'])
check('Export eines einzelnen Farmers (für die Gegenprüfung)', st == 200 and r['datei'] == 'EUDR_990010001.geojson' and len(r['geojson']['features']) == 1, (st, r))
check('Export: unbekannter Container 404', I.call('containerimport_eudr_export&sendung=nein')[0] == 404)

# Sendung auf die beiden einreichbaren Flächen beschränken; Revision schützt vor überschriebenen Änderungen
gut = [ids['Estancia Ejemplo Norte'], ids['Estancia Beispiel']]
check('Container mit veraltetem Stand: 409', I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': sid, 'rev': s['rev'] - 1, 'betriebe': gut})[0] == 409)
st, r = I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': sid, 'rev': s['rev'], 'betriebe': gut})
s = r['sendungen'][0]
check('Profil ohne die fehlerhaften Flächen: nicht mehr kritisch, Entwaldung offen (ein Farmer ohne Bericht)', st == 200 and s['profil']['stand'] == 'offen' and profil(s)['geo'] == 'hinweis' and profil(s)['entwaldung'] == 'offen', s['profil'])
nb = betrieb('Estancia Ejemplo Norte')
check('Farmer mit veraltetem Stand: 409', I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'rev': nb['rev'] - 1}]})[0] == 409)
st, r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'flaecheAngabe': '166,2', 'bericht': {**nb['bericht'], 'datum': '2026-10-20', 'entwaldung': 'konform', 'schutzgebiet': 'konform', 'indigen': 'konform', 'bilderBis': 2023}}]})
s = r['sendungen'][0]
check('Bericht nachgetragen: Satellitenbilder enden zu früh → Entwaldung bleibt offen', st == 200 and profil(s)['entwaldung'] == 'offen' and 'Satellitenbilder' in next(k for k in s['profil']['kriterien'] if k['id'] == 'entwaldung')['text'], s['profil'])
nb = betrieb('Estancia Ejemplo Norte')
r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'bericht': {**nb['bericht'], 'bilderBis': 2025}}]})[1]
check('Bericht aktuell: Entwaldung und Gebiete in Ordnung, Fläche ohne Hinweis', [profil(r['sendungen'][0])[k] for k in ('entwaldung', 'gebiete', 'geo')] == ['ok', 'ok', 'ok'], r['sendungen'][0]['profil'])

nb = betrieb('Estancia Ejemplo Norte')
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'kennung': 'EJ-0001', 'notiz': 'gepflegt'}]})
o = next(o for o in L.call('containerimport_eudr_pruefen', {'dateien': [DATEI]})[1]['dateien'][0]['orte'] if o['name'] == 'Estancia Ejemplo Norte')
check('erneutes Einlesen: Vorschau zeigt den zusammengeführten Stand', o['bekannt'] == nb['id'] and o['kennung'] == 'EJ-0001' and o['bericht']['entwaldung'] == 'konform' and o['flaecheAngabe'] == 150.12, o)
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**o['eingabe'], 'id': o['bekannt'], 'rev': o['bekanntRev']}]})
nb = betrieb('Estancia Ejemplo Norte')
check('erneutes Einlesen überschreibt nur, was die Datei kennt: Kennung, Bericht und Notiz bleiben', nb['kennung'] == 'EJ-0001' and nb['notiz'] == 'gepflegt' and nb['bericht'] == {**nb['bericht'], 'entwaldung': 'konform', 'bilderBis': 2025, 'datum': '2026-10-20'}
      and nb['flaecheAngabe'] == 150.12 and len(stand()['betriebe']) == 5, nb)

# Land, Legalität, Zahlen, Datum, Grenzen
st, r = I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-260002', 'nummer': 'FB26-002'})
s2 = next(x for x in r['sendungen'] if x['nummer'] == 'FB26-002')
check('Container ohne Farmer: Geolokalisierung kritisch, „vernachlässigbar“ ausgeschlossen', profil(s2)['geo'] == 'kritisch' and s2['profil']['vernachlaessigbar'] == 'nein', s2['profil'])
fremd = {'name': 'Fazenda Exemplo', 'land': 'BR', 'geometrie': {'type': 'Polygon', 'coordinates': [[[-55, -15], [-54.99, -15], [-54.99, -15.01], [-55, -15]]]}}
st, r = I.call('containerimport_eudr_betriebe_save', {'sendung': s2['id'], 'betriebe': [fremd]})
s2 = next(x for x in r['sendungen'] if x['nummer'] == 'FB26-002')
check('Farmer in einem anderen Land als der Container: Einstufung offen, Farmer genannt', st == 200 and profil(s2)['land'] == 'offen' and next(k for k in s2['profil']['kriterien'] if k['id'] == 'land')['betriebe'] == ['Fazenda Exemplo'], s2['profil'])
fb = betrieb('Fazenda Exemplo')
r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**fb, 'land': 'RU'}]})[1]
s2 = next(x for x in r['sendungen'] if x['nummer'] == 'FB26-002')
check('Farmer in einem Land mit hohem Risiko: kritisch, auch wenn der Container ein anderes Land nennt', profil(s2)['land'] == 'kritisch', s2['profil'])
fb = betrieb('Fazenda Exemplo')
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**fb, 'land': 'PY', 'geometrie': {'type': 'Polygon', 'coordinates': [[[-57.5, -23], [-57.49, -23], [-57.49, -23.01], [-57.5, -23]]]}, 'bericht': {**fb['bericht'], 'umwelt': 'nicht_konform'}}]})
I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': s2['id'], 'rev': s2['rev'], 'partie': 'P-260002', 'nummer': 'FB26-002', 'betriebe': [fb['id']], 'nachweis': {**SENDUNG['nachweis'], 'legalitaet': 'ja'}})
s2 = next(x for x in stand()['sendungen'] if x['nummer'] == 'FB26-002')
check('Umweltgenehmigung laut Bericht nicht konform: Legalität kritisch, auch mit „Nachweise liegen vor“', profil(s2)['legalitaet'] == 'kritisch' and betrieb('Fazenda Exemplo')['ampel'] == 'rot', s2['profil'])
fb = betrieb('Fazenda Exemplo')
st, r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**fb, 'flaecheAngabe': '0.125'}]})
check('Zahl „0.125“ bleibt 0,125 (kein Tausenderpunkt), „1.234,5“ ist 1234,5', st == 200 and betrieb('Fazenda Exemplo')['flaecheAngabe'] == 0.125
      and I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**betrieb('Fazenda Exemplo'), 'flaecheAngabe': '1.234,5'}]})[0] == 200 and betrieb('Fazenda Exemplo')['flaecheAngabe'] == 1234.5, betrieb('Fazenda Exemplo')['flaecheAngabe'])
fb = betrieb('Fazenda Exemplo')
check('Datum in der Zukunft wird abgewiesen (Bericht, Erklärung, Sorgfaltserklärung)', I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**fb, 'bericht': {**fb['bericht'], 'datum': '2062-01-01'}}]})[0] == 422
      and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-260002', 'id': s2['id'], 'rev': s2['rev'], 'nachweis': {**SENDUNG['nachweis'], 'erklaerung': '2062-01-01'}})[0] == 422
      and I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'partie': 'P-260002', 'id': s2['id'], 'rev': s2['rev'], 'dds': {'referenz': 'x', 'datum': '2062-01-01'}})[0] == 422)
riesig = {'name': 'Riesig', 'land': 'PY', 'geometrie': {'type': 'Polygon', 'coordinates': [[[1e308, 1e308], [-1e308, 1e308], [-1e308, -1e308], [1e308, 1e308]]]}}
viele = {'name': 'Viele Punkte', 'land': 'PY', 'geometrie': {'type': 'Polygon', 'coordinates': [[[-57 + i * 1e-5, -23 - (i % 2) * 1e-3] for i in range(5001)] + [[-57, -23]]]}}
check('unsinnig große Zahlen und zu viele Punkte werden nicht gespeichert (422), der Stand bleibt lesbar', I.call('containerimport_eudr_betriebe_save', {'betriebe': [riesig]})[0] == 422
      and I.call('containerimport_eudr_betriebe_save', {'betriebe': [viele]})[0] == 422 and len(stand()['betriebe']) == 6)
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**fb, 'aktiv': False}]})
I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': s2['id'], 'rev': s2['rev'], 'partie': 'P-260002', 'nummer': 'FB26-002', 'betriebe': [], 'aktiv': False})

# ---------- Eigene Gegenprüfung ----------
P = {'portal': 'gnw', 'datum': '2026-11-10', 'ergebnis': 'ohne_befund', 'verlustHa': '0', 'bemerkung': 'kein Baumverlust seit 2021'}
check('Gegenprüfung: Datum in der Zukunft und unbekanntes Portal 422, unbekannter Farmer 404', I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[0], 'datum': '2099-01-01'})[0] == 422
      and I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[0], 'portal': 'x'})[0] == 422 and I.call('containerimport_eudr_gegenpruefung', {**P, 'id': 'nein'})[0] == 404)
I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[0]})
st, r = I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[1], 'portal': 'whisp', 'ergebnis': 'befund', 'verlustHa': '2,5', 'bemerkung': 'Risk_Livestock: high'})
s = r['sendungen'][0]
check('Gegenprüfung mit Befund: kritisch, Farmer rot', st == 200 and profil(s)['gegenpruefung'] == 'kritisch' and betrieb('Estancia Beispiel')['ampel'] == 'rot' and betrieb('Estancia Beispiel')['pruefungen'][0]['von'] == 'Ina Import', s['profil'])
r = I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[1], 'portal': 'whisp', 'datum': '2026-11-12', 'bemerkung': 'Fläche war 2020 schon Weide, mit Lieferant geklärt'})[1]
check('jüngere Prüfung desselben Portals ohne Befund zählt; die ältere bleibt stehen', profil(r['sendungen'][0])['gegenpruefung'] == 'ok' and len(betrieb('Estancia Beispiel')['pruefungen']) == 2 and betrieb('Estancia Beispiel')['bewertung']['gegenpruefung'] == 'ok'
      and betrieb('Estancia Beispiel')['ampel'] == 'gelb', betrieb('Estancia Beispiel')['bewertung'])   # gelb: Landnutzungsplan und Umweltgenehmigung ohne Angabe

I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[0], 'portal': 'whisp', 'datum': '2026-11-01', 'ergebnis': 'befund'})
nb = betrieb('Estancia Ejemplo Norte')
check('zwei Portale: der ältere Befund des einen bleibt kritisch, bis dasselbe Portal entwarnt', nb['bewertung']['gegenpruefung'] == 'kritisch' and len(nb['pruefungenAktuell']) == 2 and nb['ampel'] == 'rot', nb['pruefungenAktuell'])
I.call('containerimport_eudr_gegenpruefung', {**P, 'id': gut[0], 'portal': 'whisp', 'datum': '2026-11-11'})
check('zwei Portale: nach der Entwarnung wieder in Ordnung', betrieb('Estancia Ejemplo Norte')['bewertung']['gegenpruefung'] == 'ok')

# ---------- Abschluss ----------
s = stand()['sendungen'][0]
check('offene Punkte: „vernachlässigbar“ nur mit Begründung (422)', s['profil']['stand'] == 'offen' and s['profil']['vernachlaessigbar'] == 'begruendung' and I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'ergebnis': 'vernachlaessigbar', 'begruendung': 'ok'})[0] == 422)
st, r = I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': sid, 'rev': s['rev'], 'betriebe': gut, 'nachweis': {'erklaerung': '2026-11-12', 'rueckverfolgung': 'ja', 'haltung': 'ja', 'legalitaet': 'ja'}})
s = r['sendungen'][0]
check('alle Nachweise da: kein Risiko erkennbar', st == 200 and s['profil']['stand'] == 'ok' and set(profil(s).values()) == {'ok', 'hinweis'} and 'Sorgfaltserklärung kann abgegeben werden' in s['profil']['vorschlag'], s['profil'])
check('Abschluss mit veraltetem Stand 409, unbekanntes Ergebnis 422', I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'] - 1, 'ergebnis': 'vernachlaessigbar'})[0] == 409
      and I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'ergebnis': 'egal'})[0] == 422)
st, r = I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'ergebnis': 'vernachlaessigbar', 'begruendung': 'Alle Nachweise geprüft.'})
s = r['sendungen'][0]
check('Bewertung abgeschlossen: Ergebnis, Bearbeiter, Schnappschuss von Profil und Farmern', st == 200 and s['abschluss']['ergebnis'] == 'vernachlaessigbar' and s['abschluss']['wer']['von'] == 'Ina Import'
      and s['abschluss']['profil']['stand'] == 'ok' and len(s['abschluss']['betriebe']) == 2, (st, r.get('error')))
nb = betrieb('Estancia Ejemplo Norte')
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'name': 'Estancia Umbenannt', 'bericht': {**nb['bericht'], 'entwaldung': 'nicht_konform'}}]})
s = stand()['sendungen'][0]
check('spätere Änderung am Farmer ändert die abgeschlossene Bewertung nicht (GR-106)', s['profil']['stand'] == 'ok' and 'Estancia Ejemplo Norte' in [b['name'] for b in s['abschluss']['betriebe']]
      and betrieb('Estancia Umbenannt')['ampel'] == 'rot', s['profil'])
r = I.call('containerimport_eudr_export&sendung=' + sid)[1]
check('Export eines abgeschlossenen Containers nutzt den Schnappschuss', any(f['properties']['ProductionPlace'].startswith('Estancia Ejemplo Norte') for f in r['geojson']['features']), r)
st, r = I.call('containerimport_eudr_sendung_save', {**SENDUNG, 'id': sid, 'rev': s['rev'], 'nummer': 'ANDERS', 'partie': 'P-ANDERS', 'lieferantNr': '70020', 'betriebe': [], 'dds': {'referenz': '26DEABC123456', 'datum': '2026-11-16'}, 'notiz': 'DDS abgegeben',
                                                     'stand': 'angekommen', 'container': 'MSKU 907032 3', 'akte': 'AK-2026-014/2'})
s = r['sendungen'][0]
check('nach dem Abschluss: der Container reist weiter – Stand, Container- und Aktennummer bleiben änderbar; Partienummer und Lieferant nicht',
      [s[k] for k in ('stand', 'container', 'akte', 'partie', 'lieferantNr', 'lieferant')] == ['angekommen', 'MSKU 907032 3', 'AK-2026-014/2', 'P-260001', '', 'Frigorifico Beispiel'], s)
check('nach dem Abschluss: Sorgfaltserklärung und Notiz änderbar, Auftragsnummer und Farmer nicht', st == 200 and s['nummer'] == 'FB26-001' and len(s['betriebe']) == 2 and s['dds'] == {'referenz': '26DEABC123456', 'datum': '2026-11-16'} and s['notiz'] == 'DDS abgegeben' and s['abschluss'], s)
# abgeschlossener Eintrag aus der Zeit vor dem Umbau: die Partienummer lässt sich nachtragen – einmal, und nur eine freie
doc = _json(storage_raw('containerimport-eudr-sendungen'))
next(x for x in doc['liste'] if x['id'] == sid)['partie'] = ''
storage_write('containerimport-eudr-sendungen', doc)
s = next(x for x in stand()['sendungen'] if x['id'] == sid)
st4 = I.call('containerimport_eudr_sendung_save', {**s, 'partie': 'p 260004'})[0]
s = next(x for x in I.call('containerimport_eudr_sendung_save', {**s, 'partie': 'P-260001'})[1]['sendungen'] if x['id'] == sid)
s = next(x for x in I.call('containerimport_eudr_sendung_save', {**s, 'partie': 'P-NOCHMAL'})[1]['sendungen'] if x['id'] == sid)
check('abgeschlossener Eintrag von vorher: Partienummer nachtragen geht einmal, eine vergebene 422, die Bewertung bleibt abgeschlossen', st4 == 422 and s['partie'] == 'P-260001' and s['name'] == 'P-260001' and s['abschluss'], (st4, s['partie']))
check('abgeschlossen: Farmer zuordnen 409, erneut abschließen 409, öffnen ohne Grund 422', I.call('containerimport_eudr_betriebe_save', {'sendung': sid, 'betriebe': [bo]})[0] == 409
      and I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'ergebnis': 'vernachlaessigbar'})[0] == 409
      and I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'oeffnen': True, 'grund': ''})[0] == 422)
st, r = I.call('containerimport_eudr_sendung_abschluss', {'id': sid, 'rev': s['rev'], 'oeffnen': True, 'grund': 'Betrieb nachträglich auffällig'})
s = r['sendungen'][0]
check('wieder geöffnet: früherer Abschluss samt Schnappschuss im Verlauf, Profil rechnet neu (jetzt kritisch)', st == 200 and s['abschluss'] is None and s['fruehere'][0]['grund'] == 'Betrieb nachträglich auffällig'
      and s['fruehere'][0]['ergebnis'] == 'vernachlaessigbar' and 'betriebe' not in s['fruehere'][0]
      and s['profil']['stand'] == 'kritisch' and s['profil']['vernachlaessigbar'] == 'nein', s)
frueher = next(x for x in _json(storage_raw('containerimport-eudr-sendungen'))['liste'] if x['id'] == sid)['fruehere'][0]
check('wieder geöffnet: der Schnappschuss bleibt gespeichert (GR-106), wird aber nicht mit jedem Stand ausgeliefert', len(frueher['betriebe']) == 2 and frueher['profil']['stand'] == 'ok')
nb = betrieb('Estancia Umbenannt')
I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**nb, 'name': 'Estancia Ejemplo Norte', 'bericht': {**nb['bericht'], 'entwaldung': 'konform'}}]})
st, r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [{**betrieb('Estancia Vertauscht'), 'aktiv': False}]})
check('Farmer archivieren statt löschen', st == 200 and not betrieb('Estancia Vertauscht')['aktiv'] and len(stand()['betriebe']) == 6)
verlauf = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Speichern, Gegenprüfung, Abschluss und Wiederöffnen', all(t in verlauf for t in ('EUDR: 5 Farmer gespeichert', 'Container „P-260001“ gespeichert', 'EUDR: Bewertung des Containers „P-260001“ abgeschlossen', 'Gegenprüfung für „Estancia Beispiel“',
                                                                                       'abgeschlossen (Risiko vernachlässigbar)', 'wieder geöffnet')), verlauf[:600])

# ---------- Oberfläche ----------
ERKL = pdf_bauen([[(60, 700, 'To Whom It May Concern'), (60, 680, 'The company expresses its commitment to deforestation-free production.')]])
REPORT = pdf_bauen([
    [(60, 700, 'Hendata & Global Canopy'), (60, 660, 'REPORT ON COMPLIANCE WITH THE EU'), (60, 640, 'Analysis Date: 04/11/2026, 17:56'), (60, 628, 'Farm Country: Paraguay')],
    [(230, 760, 'Farm information summary'),
     (50, 720, 'SIGOR code'), (160, 720, 'Farm Name'), (300, 720, 'Owner'), (450, 720, 'Country'), (540, 720, 'Department'), (700, 720, 'District'), (820, 720, 'Farm area (ha)'),
     (50, 690, '990010001'), (150, 690, 'Estancia Beispiel'), (280, 696, 'AGROGANADERA'), (285, 684, 'MUSTER S.A.'), (445, 690, 'PARAGUAY'), (510, 690, 'BEISPIELDEPARTAMENTO'), (695, 690, 'MUSTERORT'), (835, 690, '300.2'),
     (200, 640, 'Deforestation-free compliance table'), (120, 620, 'Compliance Status'), (340, 620, 'Cumulative deforested Area 2021 - 2025 [ha]'), (60, 600, 'Compliant'), (340, 600, '0'),
     (200, 560, 'Overlap with Protected Areas Table'), (60, 540, 'Compliant'), (240, 540, '0'), (420, 540, 'None'),
     (200, 500, 'Overlap with Indigenous Territories Table'), (60, 480, 'Compliant'), (240, 480, '0'), (420, 480, 'None')],
    [(200, 760, 'National Compliance Table'), (60, 740, 'No information'), (60, 700, 'Data used for the analysis'),
     (60, 680, '2020'), (120, 680, 'COPERNICUS/S2_SR_HARMONIZED/20201219T135109_20201219T135108_T21KWQ'), (60, 660, '2025'), (120, 660, 'COPERNICUS/S2_SR_HARMONIZED/20251014T134709_20251014T135818_T21KWQ')],
    [(60, 760, 'Coordinates of farm 990010001:'), (60, 740, ', '.join(f'p{i} {e:.2f} {n:.2f}' for i, (e, n) in enumerate(UTM[:3])) + ','), (60, 728, ', '.join(f'p{i + 3} {e:.2f} {n:.2f}' for i, (e, n) in enumerate(UTM[3:])))],
])
tmp = tempfile.mkdtemp()
pfade = {}
for name, inhalt in (('Compliance_Report_Estancia_Beispiel.pdf', REPORT), ('Erklaerung_Lieferant.pdf', ERKL)):
    pfade[name] = os.path.join(tmp, name)
    with open(pfade[name], 'wb') as fh:
        fh.write(inhalt)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    # Kartendienste (Satellitenbild, Wald 2020, Waldverlust): Tests rufen nie fremde Server ab (einzige Ausnahme: von Hand mit
    # WA_KARTE_ECHT, nur Bildschirmfotos). Ohne Angabe sind die Dienste
    # „nicht erreichbar“ (die Karte zeichnet dann wie ohne Netz), sonst antwortet kartendienste() mit einem Testbild.
    DIENSTE = re.compile(r'^https://(tiles\.maps\.eox\.at|ies-ows\.jrc\.ec\.europa\.eu|tiles\.globalforestwatch\.org)/')
    BILD = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')   # 1 × 1 Punkt, PNG

    def png(punkt):
        """PNG mit 512 × 512 Bildpunkten, punkt(x, y) → (R, G, B, A)"""
        zeilen = b''.join(b'\x00' + bytes(k for x in range(512) for k in punkt(x, y)) for y in range(512))
        teil = lambda art, daten: struct.pack('>I', len(daten)) + art + daten + struct.pack('>I', zlib.crc32(art + daten))
        return b'\x89PNG\r\n\x1a\n' + teil(b'IHDR', struct.pack('>IIBBBBB', 512, 512, 8, 6, 0, 0, 0)) + teil(b'IDAT', zlib.compress(zeilen)) + teil(b'IEND', b'')

    # Muster für die Bildauswertung, je Kachel gleich: Wald 2020 in der linken Hälfte; Verlust 2022 in den Zeilen 100–199
    # (100/512 der Kachel), Verlust 2019 – vor dem Stichtag – in den Zeilen 300–349 (50/512). Kodierung wie die Dienste.
    WALD_BILD = png(lambda x, y: (77, 146, 33, 255) if x < 256 else (0, 0, 0, 0))
    VERLUST_BILD = png(lambda x, y: (255, 0, 22, 255) if 100 <= y < 200 else (255, 0, 19, 255) if 300 <= y < 350 else (0, 0, 0, 0))

    def kartendienste(abrufe, ohne=(), verlust=VERLUST_BILD):
        """Antwortet wie die drei Dienste, mit CORS-Freigabe: Kacheln der Karte als Testbild; für die Bildauswertung die Muster
        (Wald als WMS mit 512 Punkten, Verlust unverarbeitet ohne Zusatz); ein Endjahr ohne Daten lehnt der Dienst ab (422)."""
        def antwort(route):
            u = route.request.url; abrufe.append(u)
            if any(teil(u) if callable(teil) else teil in u for teil in ohne): return route.abort()
            jahr = re.search(r'end_year=(\d+)', u)
            if jahr and int(jahr[1]) > 2025: return route.fulfill(status=422, headers={'Access-Control-Allow-Origin': '*'}, body='{}')
            bild = WALD_BILD if 'WIDTH=512' in u else verlust if re.search(r'/dynamic/12/\d+/\d+\.png$', u) else BILD
            route.fulfill(status=200, headers={'Access-Control-Allow-Origin': '*', 'Content-Type': 'image/png'}, body=bild)
        return antwort

    def seite(user, vp=None, schema='light', dienste=None):
        ctx = br.new_context(viewport=vp or {'width': 1280, 'height': 900}, color_scheme=schema, accept_downloads=True)
        ctx.route(DIENSTE, dienste or (lambda route: route.abort()))
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', USERS[user][2]); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.goto(B + '/module/containerimport/')
        return pg

    o = seite('ole'); o.wait_for_selector('#ci-err:not([hidden])')
    check('Oberfläche ohne „EUDR ansehen“: Hinweis statt Inhalt', 'Berechtigung' in o.inner_text('#ci-err') and o.locator('#ci-app').is_hidden())
    o.context.close()

    p = seite('ina'); p.wait_for_selector('#ci-app:not([hidden]) #ci-sendungen tr[data-sendung]')
    p.wait_for_selector('#r-leiste a.r-eintrag[data-modul="containerimport"]', state='attached')
    lf = p.evaluate("""() => { const t = document.createElement('span'); t.style.color = 'var(--r-text)'; document.querySelector('#r-leiste').append(t); const soll = getComputedStyle(t).color; t.remove();
      return { soll, ist: [...new Set([...document.querySelectorAll('#r-leiste a.r-eintrag')].map((a) => getComputedStyle(a).color))] }; }""")
    check('Seitenleiste: Einträge in der Textfarbe des Rahmens (hell: schwarz), nicht in der Linkfarbe des Moduls', lf['ist'] == [lf['soll']], lf)
    p.evaluate('window.STAFL_RAHMEN.sucheOeffnen()'); p.wait_for_selector('#r-palette[open] a.r-palette-treffer')
    tf = p.evaluate("""() => { const t = document.createElement('span'); t.style.color = 'var(--r-text)'; document.querySelector('#r-palette').append(t); const soll = getComputedStyle(t).color; t.remove();
      return { soll, ist: [...new Set([...document.querySelectorAll('#r-palette a.r-palette-treffer')].map((a) => getComputedStyle(a).color))] }; }""")
    check('Suche des Rahmens: Treffer ebenfalls in der Textfarbe des Rahmens', tf['ist'] == [tf['soll']], tf)
    p.keyboard.press('Escape'); p.wait_for_selector('#r-palette:not([open])', state='attached')
    p.wait_for_selector('.r-app.r-bereit:not(.r-fest):not(.r-auf)')
    p.hover('#r-leiste a[data-modul="containerimport"]'); p.wait_for_function("document.querySelector('.r-app').classList.contains('r-auf')")
    shot(p, os.path.join(SH, 'containerimport-leiste-offen-1280.png'))
    p.mouse.move(700, 500); p.wait_for_function("!document.querySelector('.r-app').classList.contains('r-auf')")

    # Berichtsleser: Fehlbilder dürfen nie still einen falschen Wert liefern (erfundene Textstücke, im Browser ausgewertet)
    fehl = p.evaluate('''() => {
      const B = window.EUDR_BERICHT, f = [];
      const lies = (zeilen) => B.lesen([zeilen.map((s, i) => ({ s, x: 50, y: 800 - i * 12, w: s.length * 4 }))]);
      const koord = 'p0 500000.00 7400000.00, p1 500000.00 7401500.00, p2 502000.00 7401500.00, p3 500000.00 7400000.00';
      const mit = (x, y, k = koord, extra = []) => lies(['Deforestation-free compliance table', x, 'Overlap with Protected Areas Table', y, 'Overlap with Indigenous Territories Table', 'Compliant 0',
        'National Compliance Table', 'COPERNICUS/S2_SR_HARMONIZED/20251014T134709_20251014T135818_T21KWQ', ...extra, 'Coordinates of farm 1:', k]);
      const check = (n, c) => { if (!c) f.push(n); };
      for (const t of ['Non-compliant 12.5', 'Non - compliant 12.5', 'Non-\\ncompliant 12.5', 'Not  compliant 12.5', 'Non\u2011compliant 12.5', 'NON-COMPLIANT 12.5']) {
        const r = mit(t, 'Compliant 0'); check('nicht konform: ' + t, r.ort.bericht.entwaldung === 'nicht_konform' && r.ort.bericht.entwaldungHa === 12.5);
      }
      check('Verneinung nach Erläuterung', mit('Compliant 0', 'A farm is compliant if no overlap. Non-compliant 3').ort.bericht.schutzgebiet === 'nicht_konform');
      check('Tausenderkomma', mit('Non-compliant 1,234.5', 'Compliant 0').ort.bericht.entwaldungHa === 1234.5);
      const gut = mit('Compliant 0', 'Compliant 0');
      check('konform', gut.ort.bericht.entwaldung === 'konform' && gut.bezug === 'UTM 21S' && gut.ort.koordinaten.punkte.length === 4 && !('landnutzung' in gut.ort.bericht));
      for (const k of ['p0 500000 .00 7400000.00, p1 500000.00 7401500.00, p2 502000.00 7401500.00', 'p0 500000.00 7400000.00, p1 500000.\\n00 7401500.00, p2 502000.00 7401500.00, p3 500000.00 7400000.00',
        'p0 500000.00 3 7400000.00, p1 500000.00 7401500.00, p2 502000.00 7401500.00', 'p0 500,000.00 7,400,000.00, p1 500,000.00 7,401,500.00, p2 502,000.00 7,401,500.00']) check('Koordinatenfehler: ' + k.slice(0, 30), typeof (mit('Compliant 0', 'Compliant 0', k) || {}).fehler === 'string');
      check('zwei Flächen', /mehrere Flächen/.test((lies(['Coordinates of farm 1:', koord, 'Coordinates of farm 2:', koord]) || {}).fehler || ''));
      check('zwei Zonen', mit('Compliant 0', 'Compliant 0', koord, ['S2_SR_HARMONIZED/20251014T134709_20251014T135818_T20KQV']).ort.koordinaten.zone === null);
      check('ohne Liste', lies(['To whom it may concern']) === null);
      return f;
    }''')
    check('Berichtsleser: „Non-compliant“ in jeder Schreibweise, zerrissene Koordinaten, zwei Flächen oder zwei Zonen ergeben nie still einen falschen Wert', fehl == [], fehl)
    check('Oberfläche: Container mit Risikoprofil in der Liste, Reiter EUDR', 'P-260001' in p.inner_text('#ci-sendungen') and p.get_attribute('#ci-reiter-eudr', 'aria-selected') == 'true'
          and 'kein Risiko erkennbar' in p.inner_text('#ci-sendungen') and '26DEABC123456' in p.inner_text('#ci-sendungen'), p.inner_text('#ci-sendungen'))
    shot(p, os.path.join(SH, 'containerimport-sendungen-1280.png'))

    # Neuer Container aus dem Fenster: Lieferant aus den Stammdaten wählen, drei Nummern, Stand
    gespeichert = "document.querySelector('#sendung-titel')?.textContent === 'Akte AK-10 · Partie P-260010' && document.querySelector('#dlg-sendung').innerText.includes('%s')"
    p.click('#ci-sendung-neu'); p.wait_for_selector('#dlg-sendung[open]')
    check('Fenster „Neuer Container“: Stände zur Auswahl, Lieferanten der Stammdaten als Vorschläge',
          p.eval_on_selector_all('#dlg-sendung [name=stand] option', 'os => os.map(o => o.textContent)') == ['gekauft', 'unterwegs', 'Dokumente da', 'angekommen']
          and p.eval_on_selector_all('#ci-lieferanten option', 'os => os.map(o => o.value)') == ['Carnes del Sur Ltda. (70020)', 'Frigorifico Beispiel S.A. (70012)', 'OHNENAME (70031)'])
    p.fill('#dlg-sendung [name=partie]', 'P-260010'); p.fill('#dlg-sendung [name=akte]', 'AK-10'); p.fill('#dlg-sendung [name=container]', 'MSKU 907032 4'); p.fill('#dlg-sendung [name=lieferant]', 'Carnes del Sur Ltda. (70020)')
    p.select_option('#dlg-sendung [name=land]', 'UY'); p.select_option('#dlg-sendung [name=stand]', 'unterwegs')
    p.click('#dlg-sendung button[type=submit]'); p.wait_for_function(gespeichert % 'Stammdaten Nr. 70020')
    c = next(x for x in stand()['sendungen'] if x['partie'] == 'P-260010')
    check('Neuer Container gespeichert: mit dem Lieferanten der Stammdaten verknüpft, Name von dort, Stand „unterwegs“',
          [c[k] for k in ('lieferantNr', 'lieferant', 'akte', 'stand', 'land')] == ['70020', 'Carnes del Sur Ltda.', 'AK-10', 'unterwegs', 'UY'], c)
    check('Fenster „Container“: Hinweis auf die falsche Prüfziffer der Containernummer', 'Prüfziffer passt nicht' in p.inner_text('#dlg-sendung'))
    shot(p.locator('#dlg-sendung'), os.path.join(SH, 'containerimport-container-fenster-1280.png'))
    p.fill('#dlg-sendung [name=lieferant]', 'Lieferant ohne Stammdaten'); p.fill('#dlg-sendung [name=container]', 'MSKU 907032 3')
    p.click('#dlg-sendung button[type=submit]'); p.wait_for_function(gespeichert % 'Nicht mit den Stammdaten verknüpft')
    c = next(x for x in stand()['sendungen'] if x['partie'] == 'P-260010')
    check('Lieferant als freier Text: gespeichert ohne Verknüpfung, das Fenster sagt es; gültige Containernummer ohne Hinweis',
          c['lieferantNr'] == '' and c['lieferant'] == 'Lieferant ohne Stammdaten' and c['containerPruefung'] == 'ok' and 'Prüfziffer' not in p.inner_text('#dlg-sendung'), c)
    p.click('#dlg-sendung .dlg-foot [data-zu]'); p.wait_for_selector('#dlg-sendung', state='hidden')
    p.fill('#ci-suche', 'ak-10 ohne'); p.wait_for_function("document.querySelectorAll('#ci-sendungen tbody tr').length === 1")
    zeile = p.inner_text('#ci-sendungen tbody tr')
    check('Liste der Container: Suche über Akte und Lieferant; Zeile mit Partie, Akte, Containernummer, Stand und dem Hinweis „nicht verknüpft“',
          all(t in zeile for t in ('P-260010', 'Akte AK-10', 'Container MSKU 907032 3', 'unterwegs', 'nicht mit den Stammdaten verknüpft', 'Uruguay')), zeile)
    p.fill('#ci-suche', 'gibt es nicht'); p.wait_for_selector('#ci-inhalt .ci-leer')
    check('Liste der Container: Suche ohne Treffer sagt das', p.inner_text('#ci-inhalt .ci-leer') == 'Kein Container passt zur Suche.' and p.input_value('#ci-suche') == 'gibt es nicht')
    p.fill('#ci-suche', ''); p.wait_for_selector('#ci-sendungen tbody tr')
    I.call('containerimport_eudr_sendung_save', {**c, 'aktiv': False})   # die folgenden Prüfungen arbeiten mit dem ersten Container
    p.click('#ci-neu'); p.wait_for_function("document.querySelectorAll('#ci-sendungen tbody tr').length === 1")

    # Unterlagen einlesen: Bericht (PDF, im Browser gelesen), Lieferanten-GeoJSON, Erklärung ohne Koordinaten
    p.click('#ci-lesen'); p.wait_for_selector('#dlg-lesen[open]')
    p.select_option('#dlg-lesen [name=sendung]', sid); p.fill('#dlg-lesen [name=lieferant]', 'Frigorifico/Beispiel')
    p.set_input_files('#lesen-dateien', [pfade['Compliance_Report_Estancia_Beispiel.pdf'], os.path.join(FIX, 'containerimport', 'lieferant.geojson'), pfade['Erklaerung_Lieferant.pdf']])
    p.wait_for_selector('#lesen-ergebnis .ci-datei')
    text = p.inner_text('#lesen-ergebnis')
    check('Einlesen: Bericht im Browser gelesen (Name, Erzeuger über zwei Zeilen, Kennung, Fläche)', all(t in text for t in ('Estancia Beispiel', 'AGROGANADERA MUSTER S.A.', 'Kennung 990010001', '300,24 ha', 'angegeben 300,20 ha')), text)
    check('Einlesen: Erklärung ohne Koordinaten wird abgewiesen, Linie gemeldet', 'Erklaerung_Lieferant.pdf: Keine Koordinatenliste' in text and 'LineString' in text, text)
    check('Einlesen: vorhandene Farmer werden erkannt (mit ihrer Nummer), Fehlerhaftes ist markiert', text.count('aktualisiert F-0') == 5 and text.count('fehlerhaft') >= 2 and 'überschneidet sich selbst' in text, text)
    shot(p.locator('#dlg-lesen'), os.path.join(SH, 'containerimport-einlesen-1280.png'))
    for nr in p.eval_on_selector_all('#lesen-ergebnis [data-ort]', 'els => els.map((e, i) => [i, e.closest("li").innerText]).filter(([, t]) => !t.includes("Estancia Beispiel")).map(([i]) => i)'):
        p.uncheck(f'#lesen-ergebnis [data-ort="{nr}"]')
    check('Einlesen: Knopf zählt die Auswahl', p.inner_text('#lesen-ok') == '1 Farmer übernehmen', p.inner_text('#lesen-ok'))
    p.click('#lesen-ok'); p.wait_for_selector('#dlg-sendung[open]')
    b = betrieb('Estancia Beispiel')
    check('Einlesen: Farmer aktualisiert (kein Doppelter), Quelle mit Dateiname und Prüfsumme, dem Container zugeordnet', len(stand()['betriebe']) == 6 and b['quelle']['datei'] == 'Compliance_Report_Estancia_Beispiel.pdf'
          and len(b['quelle']['sha256']) == 64 and b['quelle']['sha256'] != 'a' * 64 and b['region'] == 'BEISPIELDEPARTAMENTO' and b['ort'] == 'MUSTERORT' and b['bericht']['datum'] == '2026-11-04'
          and b['bericht']['bilderBis'] == 2025 and len(b['pruefungen']) == 2 and b['id'] in stand()['sendungen'][0]['betriebe'], b)

    # Original im QM-System: nur die übernommene Datei, im Eingang unter „EUDR/<Lieferant>“ (Schrägstrich im Namen ist kein Ordner)
    eingang = [f for f in _json(storage_raw('qs-ablage'))['liste'] if f.get('ziel') == 'eingang']
    check('Original des übernommenen Berichts liegt im Eingang des QM-Systems, am Farmer vermerkt', len(eingang) == 1 and eingang[0]['name'] == 'Compliance_Report_Estancia_Beispiel.pdf'
          and eingang[0]['pfad'] == 'EUDR/Frigorifico Beispiel' and eingang[0]['sha256'] == b['quelle']['sha256'] and eingang[0]['hochgeladen']['von'] == 'Ina Import'
          and b['quelle']['qm']['status'] == 'eingang' and b['quelle']['qm']['datei'] == eingang[0]['id'] and b['quelle']['qm']['pfad'] == 'EUDR/Frigorifico Beispiel', (eingang, b['quelle']))
    check('Toast nennt die Ablage', 'Original im QM-System abgelegt' in p.inner_text('#ci-toast'), p.inner_text('#ci-toast'))

    # Fenster „Sendung“: Risikoprofil, Karte, Datei für TRACES
    p.wait_for_function("document.querySelector('#sendung-karte')?.dataset.karte === 'bereit'")
    check('Container: Risikoprofil mit allen Kriterien und Vorschlag, Karte mit zwei Flächen', p.locator('#dlg-sendung .ci-kriterien li').count() == len(stand()['sendungen'][0]['profil']['kriterien']) and p.locator('#dlg-sendung .ci-vorschlag').count() == 1
          and p.locator('#sendung-karte .ci-k-flaeche').count() == 2 and p.locator('#sendung-karte .ci-k-land').count() == 1)
    shot(p.locator('#dlg-sendung'), os.path.join(SH, 'containerimport-sendung-1280.png'))
    with p.expect_download() as dl:
        p.click('#dlg-sendung [data-export-sendung]')
    datei = json.load(open(dl.value.path(), encoding='utf-8'))
    check('Container: „GeoJSON für TRACES“ lädt die Datei', dl.value.suggested_filename == 'EUDR_P-260001.geojson' and datei['type'] == 'FeatureCollection' and len(datei['features']) == 2, datei)
    p.fill('#dlg-sendung [name=d_referenz]', '26DEXYZ000111'); p.click('#dlg-sendung button[type=submit]')
    p.wait_for_function("document.querySelector('#ci-toast').textContent.includes('Container gespeichert')")
    check('Container: Speichern aus dem Fenster', stand()['sendungen'][0]['dds']['referenz'] == '26DEXYZ000111')
    p.click('#sendung-druck')
    druck = p.text_content('#ci-druck')
    check('Risikoprofil drucken: Druckfassung mit Container, Farmern und Kriterien', all(t in druck for t in ('Risikoprofil EUDR · Akte AK-2026-014/2 · Partie P-260001', 'Partienummer', 'AK-2026-014/2', 'MSKU 907032 3', 'Estancia Beispiel', 'Rückverfolgung Los → Farmer', '26DEXYZ000111')), druck[:300])
    p.click('#dlg-sendung .dlg-foot [data-zu]'); p.wait_for_selector('#dlg-sendung', state='hidden')

    # Herkunftsbetriebe, Fenster „Betrieb“ mit Umriss, Gegenprüfung
    p.click('[data-sicht="betriebe"]'); p.wait_for_selector('#ci-betriebe tr[data-betrieb]')
    check('Farmer: Liste ohne Archivierte, Suche mit Umlaut-Regel', p.locator('#ci-betriebe tbody tr').count() == 4)
    p.fill('#ci-suche', 'muster beispiel'); p.wait_for_function("document.querySelectorAll('#ci-betriebe tbody tr').length === 1")
    shot(p, os.path.join(SH, 'containerimport-betriebe-1280.png'))
    p.click('#ci-betriebe tr[data-betrieb]'); p.wait_for_selector('#dlg-betrieb[open]')
    check('Links im eigenen Fenster behalten die Linkfarbe des Moduls (nur der Rahmen ist ausgenommen)',
          p.evaluate("""() => { const t = document.createElement('span'); t.style.color = 'var(--r-akzent-text)'; document.querySelector('#dlg-betrieb').append(t); const soll = getComputedStyle(t).color; t.remove();
            return getComputedStyle(document.querySelector('#dlg-betrieb a[href*="openstreetmap"]')).color === soll; }"""))
    p.wait_for_function("document.querySelector('#betrieb-karte')?.dataset.karte === 'bereit'")
    check('Farmer: Umriss mit vier Eckpunkten, Maßstab, Lage im Land; Verweise auf Global Nature Watch und Whisp', p.locator('#betrieb-karte .ci-k-ecke').count() == 4 and p.inner_text('#betrieb-karte .ci-k-massstab').strip() in ('500 m', '1 km')
          and p.locator('#betrieb-karte .ci-k-lage svg').count() == 1 and p.eval_on_selector_all('#dlg-betrieb .ci-portale a', 'as => as.map(a => a.hostname)') == ['www.globalnaturewatch.org', 'whisp.openforis.org']
          and p.eval_on_selector_all('#dlg-betrieb a[target=_blank]', 'as => as.every(a => a.rel.includes("noopener"))'))
    p.select_option('#dlg-betrieb [name=p_portal]', 'gnw'); p.fill('#dlg-betrieb [name=p_bemerkung]', 'ohne Auffälligkeit'); p.click('#betrieb-pruefung')
    p.wait_for_function("document.querySelectorAll('#dlg-betrieb .ci-pruefungen li').length === 3")
    check('Farmer: Gegenprüfung aus dem Fenster eingetragen', len(betrieb('Estancia Beispiel')['pruefungen']) == 3)
    shot(p.locator('#dlg-betrieb'), os.path.join(SH, 'containerimport-betrieb-1280.png'))
    p.keyboard.press('Escape'); p.wait_for_selector('#dlg-betrieb', state='hidden')

    # Karte
    p.fill('#ci-suche', ''); p.click('[data-sicht="karte"]'); p.wait_for_function("document.querySelector('#ci-karte')?.dataset.karte === 'bereit'")
    check('Karte: Marke je aktivem Farmer, Farbe nach Ampel', p.locator('#ci-karte .ci-k-marke').count() == 4 and p.locator('#ci-karte .ci-k-marke.gelb').count() >= 1 and p.locator('#ci-karte .ci-k-marke.rot').count() >= 1)
    shot(p, os.path.join(SH, 'containerimport-karte-1280.png'))
    oben = p.locator('#ci-karte .ci-k-marke').last   # die zuletzt gezeichnete Marke liegt oben (Betriebe können sich überdecken)
    name = oben.locator('title').text_content()
    oben.click(); p.wait_for_selector('#dlg-betrieb[open]')
    check('Karte: Klick auf eine Marke öffnet diesen Farmer', p.inner_text('#betrieb-titel') == name, (p.inner_text('#betrieb-titel'), name))
    p.keyboard.press('Escape'); p.wait_for_selector('#dlg-betrieb', state='hidden')
    p.select_option('#ci-karte-sendung', sid); p.wait_for_function("document.querySelectorAll('#ci-karte .ci-k-marke').length === 2")
    check('Karte: Auswahl eines Containers zeigt nur seine Farmer', p.locator('.ci-kartenliste button').count() == 2)
    p.context.close()

    # Herkunftskarte des Servers (Südamerika, Neuseeland): ist /karte/herkunft.pmtiles da, zeichnet die Detailkarte Straßen und
    # Orte unter die Flächen. Der Testserver kennt keine Byte-Bereiche – die Datei kommt hier aus dem Testauszug der Detailkarte.
    PM = open(os.path.join(FIX, 'karte', 'hamburg.pmtiles'), 'rb').read()

    def kartendatei(route):
        m = re.match(r'bytes=(\d+)-(\d*)', route.request.headers.get('range', ''))
        a, e = (int(m[1]), min(int(m[2] or len(PM) - 1), len(PM) - 1)) if m else (0, len(PM) - 1)
        route.fulfill(status=206 if m else 200, headers={'Content-Range': f'bytes {a}-{e}/{len(PM)}', 'Accept-Ranges': 'bytes', 'Content-Type': 'application/octet-stream'}, body=PM[a:e + 1])

    d = seite('ina'); d.context.route('**/karte/herkunft.pmtiles', kartendatei)
    d.reload(); d.wait_for_selector('#ci-app:not([hidden]) #ci-sendungen tr[data-sendung]')
    d.click('[data-sicht="karte"]'); d.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    aktiv = [x for x in stand()['betriebe'] if x['aktiv']]
    check('Herkunftskarte: Detailkarte statt SVG, alle Flächen und eine Marke je Farmer', d.locator('#ci-karte svg.ci-k-haupt').count() == 0
          and d.evaluate("(() => { const k = document.querySelector('#ci-karte').staflKarte; return [k.gebiete(), k.anzahl()]; })()") == [len([x for x in aktiv if x['geometrie']['type'] != 'Point']), len(aktiv)])
    shot(d, os.path.join(SH, 'containerimport-herkunftskarte-1280.png'))
    d.click('.ci-kartenliste button >> nth=0'); d.wait_for_selector('#betrieb-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Herkunftskarte im Fenster „Farmer“: genau diese Fläche, ohne Marken', d.evaluate("(() => { const k = document.querySelector('#betrieb-karte').staflKarte; return [k.gebiete(), k.anzahl()]; })()") == [1, 0])
    d.keyboard.press('Escape'); d.select_option('#ci-karte-sendung', sid); d.wait_for_selector('#ci-karte[data-karte="bereit"] canvas')
    check('Herkunftskarte: Auswahl eines Containers zeichnet neu (eine Karte, nicht zwei übereinander)', d.locator('#ci-karte canvas').count() == 1 and d.evaluate("document.querySelector('#ci-karte').staflKarte.anzahl()") == 2)
    d.context.close()

    # Karte mit Satellitenbild und Waldebenen (Auftrag des Inhabers 18.11.2026): drei fremde Dienste, vom Browser direkt abgerufen
    abrufe, alle = [], []
    k = seite('ina', dienste=kartendienste(abrufe)); k.on('request', lambda r: alle.append(r.url))
    k.reload(); k.wait_for_selector('#ci-app:not([hidden]) #ci-sendungen tr[data-sendung]')
    k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    ebenen = "(() => { const k = document.querySelector('%s').staflKarte; return Object.fromEntries(['satellit', 'wald2020', 'verlust', 'grund'].map((e) => [e, k.sichtbar(e)])); })()"
    check('Karte mit Bildern: Satellitenbild, Wald 2020 und Waldverlust bis zum jüngsten Jahr mit Daten; ohne Herkunftskarte kein Schalter „Straßen und Orte“',
          k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts() == ['Satellitenbild (2016)', 'Wald Ende 2020 (EU)', 'Waldverlust 2021–2025']
          and k.evaluate(ebenen % '#ci-karte') == {'satellit': True, 'wald2020': True, 'verlust': True, 'grund': False}
          and k.locator('#ci-karte svg.ci-k-haupt').count() == 0, (k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts(), k.evaluate(ebenen % '#ci-karte')))
    check('Karte mit Bildern: Flächen und Marken wie bisher', k.evaluate("(() => { const k = document.querySelector('#ci-karte').staflKarte; return [k.gebiete(), k.anzahl()]; })()")
          == [len([x for x in aktiv if x['geometrie']['type'] != 'Point']), len(aktiv)])
    kacheln = [u for u in abrufe if not re.search(r'/0/0/0\.', u)]   # ohne die Proben
    check('Kartendienste: Satellitenbild 2016 von EOX, Wald 2020 der EU als WMS je Kachel, Waldverlust ab 2021 gefiltert und eingefärbt',
          any(re.search(r'^https://tiles\.maps\.eox\.at/wmts/1\.0\.0/s2cloudless_3857/default/g/\d+/\d+/\d+\.jpg$', u) for u in kacheln)
          and any('LAYERS=gfc2020_v3' in u and 'CRS=EPSG:3857' in u and re.search(r'BBOX=-?[\d.]+,-?[\d.]+,-?[\d.]+,-?[\d.]+&', u) for u in kacheln)
          and any(re.search(r'^https://tiles\.globalforestwatch\.org/umd_tree_cover_loss/latest/dynamic/\d+/\d+/\d+\.png\?start_year=2021&end_year=2025&render_type=true_color$', u) for u in kacheln), kacheln[:6])
    check('Kartendienste: Proben vor dem Zeichnen (Satellitenbild erreichbar? jüngstes Jahr des Waldverlusts)',
          any('s2cloudless_3857/default/g/0/0/0.jpg' in u for u in abrufe) and [re.search(r'end_year=(\d+)', u)[1] for u in abrufe if '/dynamic/0/0/0.png' in u][-1] == '2025')
    check('Karte: keine Anfrage an andere fremde Adressen als die drei Dienste', all(u.startswith(B) or DIENSTE.match(u) or u.startswith(('blob:', 'data:')) for u in alle),
          [u for u in alle if not (u.startswith(B) or DIENSTE.match(u) or u.startswith(('blob:', 'data:')))][:3])
    shot(k, os.path.join(SH, 'containerimport-karte-bilder-1280.png'))
    k.uncheck('#ci-karte .ci-k-ebenen input[value="wald2020"]')
    check('Ebenenschalter: Wald 2020 ausgeblendet, die anderen bleiben', k.evaluate(ebenen % '#ci-karte') == {'satellit': True, 'wald2020': False, 'verlust': True, 'grund': False})
    zoom = lambda: k.evaluate("document.querySelector('#ci-karte').staflKarte.map.getZoom()")
    z0 = zoom()   # jeder Klick setzt die Karte sofort auf „lädt“; „bereit“ heißt: Bewegung zu Ende
    k.click('#ci-karte .ci-k-zoom [data-zoom="+"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"]'); z1 = zoom()
    k.click('#ci-karte .ci-k-zoom [data-zoom="0"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"]'); z2 = zoom()
    check('Zoomknöpfe: vergrößern, zurück genau zur Ansicht vom Anfang, Knopf für die große Karte; Maßstab; Quellenangaben eingeklappt',
          abs(z1 - z0 - 1) < 0.01 and abs(z2 - z0) < 0.01 and k.locator('#ci-karte .ci-k-zoom [data-zoom="v"]').count() == 1 and k.locator('#ci-karte .maplibregl-ctrl-scale').count() == 1
          and k.locator('#ci-karte .maplibregl-ctrl-attrib.maplibregl-compact-show').count() == 0
          and 'EOX IT Services GmbH' in k.locator('#ci-karte .maplibregl-ctrl-attrib').inner_html() and 'Global Forest Watch' in k.locator('#ci-karte .maplibregl-ctrl-attrib').inner_html(), (z0, z1, z2))
    # Klick in eine Fläche öffnet ihren Betrieb: auf die Fläche zoomen, in ihre Mitte klicken
    nord = next(x for x in aktiv if x['name'] == 'Estancia Ejemplo Norte')
    k.evaluate("(m) => document.querySelector('#ci-karte').staflKarte.map.jumpTo({ center: m, zoom: 12 })", nord['mitte']); k.wait_for_selector('#ci-karte[data-karte="bereit"]')
    ort = k.evaluate("(m) => { const k = document.querySelector('#ci-karte'), r = k.getBoundingClientRect(), p = k.staflKarte.position(m[0] + 0.004, m[1] + 0.003); return [r.left + p[0], r.top + p[1]]; }", nord['mitte'])
    k.mouse.click(ort[0], ort[1]); k.wait_for_selector('#dlg-betrieb[open] #betrieb-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Karte mit Bildern: Klick in eine Fläche öffnet ihren Farmer', k.inner_text('#betrieb-titel') == 'Estancia Ejemplo Norte', k.inner_text('#betrieb-titel'))
    check('Fenster „Farmer“ ohne Whisp-Schlüssel: kein Knopf „In Whisp prüfen“', k.locator('#betrieb-whisp').count() == 0)
    check('Fenster „Farmer“: dieselbe Auswahl der Ebenen, genau diese Fläche', k.evaluate(ebenen % '#betrieb-karte') == {'satellit': True, 'wald2020': False, 'verlust': True, 'grund': False}
          and not k.is_checked('#betrieb-karte .ci-k-ebenen input[value="wald2020"]') and k.evaluate("document.querySelector('#betrieb-karte').staflKarte.gebiete()") == 1)
    k.evaluate("window.altesFenster = document.querySelector('#betrieb-karte')")
    k.keyboard.press('Escape'); k.click('.ci-kartenliste button >> nth=1'); k.wait_for_selector('#betrieb-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Fenster neu aufgebaut: die Karte des vorigen Fensters ist abgebaut (der Browser hält nur wenige Karten zugleich)',
          k.evaluate("!window.altesFenster.isConnected && !window.altesFenster.querySelector('canvas') && !window.altesFenster.staflKarte"))
    k.keyboard.press('Escape'); k.click('.ci-kartenliste button >> nth=0'); k.wait_for_selector('#betrieb-karte[data-karte="bereit"] canvas', timeout=60000)
    shot(k, os.path.join(SH, 'containerimport-karte-betrieb-1280.png'))

    # Bildauswertung: Wald 2020 und Waldverlust seit 2021 in der Fläche. Probe mit einer Fläche, die genau eine Kachel der
    # Zoomstufe 12 bedeckt – die Anteile der Muster sind dann bekannt, die Fläche rechnet der Server unabhängig (Ellipsoid).
    kx, ky = 1399, 2324   # Kachel in Paraguay
    lon = lambda x: x / 4096 * 360 - 180
    lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 4096))))
    ecken = [[lon(kx), lat(ky)], [lon(kx + 1), lat(ky)], [lon(kx + 1), lat(ky + 1)], [lon(kx), lat(ky + 1)]]
    st, r = L.call('containerimport_eudr_pruefen', {'dateien': [{'art': 'koordinaten', 'datei': '', 'land': 'PY', 'ort': {'name': 'Kachel', 'koordinaten': {'system': 'wgs84', 'punkte': ecken}}}]})
    soll = r['dateien'][0]['orte'][0]['flaeche']
    e = k.evaluate('(g) => window.EUDR_KARTE.auswerten(g)', {'type': 'Polygon', 'coordinates': [ecken + [ecken[0]]]})
    nah = lambda ist, erwartet, toleranz=0.003: abs(ist - erwartet) <= toleranz * erwartet
    check('Bildauswertung: gezählte Fläche = Fläche des Servers (unter 0,3 % Abweichung)', st == 200 and nah(e['flaecheHa'], soll), (e['flaecheHa'], soll))
    check('Bildauswertung: Wald 2020 auf der Hälfte der Fläche', nah(e['waldHa'], soll / 2), (e['waldHa'], soll / 2))
    check('Bildauswertung: Verlust 2022 zählt (100/512 der Fläche), die Hälfte davon auf Wald von 2020, nur dem Jahr 2022 zugeordnet',
          nah(e['verlustHa'], soll * 100 / 512) and nah(e['verlustAufWaldHa'], soll * 50 / 512) and nah(e['jahre']['2022'], soll * 100 / 512)
          and [j for j, v in e['jahre'].items() if v > 0] == ['2022'] and sorted(e['jahre']) == ['2021', '2022', '2023', '2024', '2025'], e)
    check('Bildauswertung: Verlust 2019 liegt vor dem Stichtag – eigens ausgewiesen, nicht als Verlust seit 2021', nah(e['vorherHa'], soll * 50 / 512), e['vorherHa'])
    gross = [[-57.0, -23.0], [-56.4, -23.0], [-56.4, -23.6], [-57.0, -23.6], [-57.0, -23.0]]
    check('Bildauswertung: zu große Fläche wird nicht gröber geschätzt, sondern abgelehnt; ein Punkt hat keine Fläche',
          k.evaluate('(g) => window.EUDR_KARTE.auswerten(g)', {'type': 'Polygon', 'coordinates': [gross]}) == {'zuGross': True}
          and k.evaluate('(g) => window.EUDR_KARTE.auswerten(g)', {'type': 'Point', 'coordinates': [-57, -23]}) is None)
    k.wait_for_selector('#betrieb-auswertung:not([hidden]) dl')
    text = k.inner_text('#betrieb-auswertung')
    check('Fenster „Farmer“: Bildauswertung mit Wald 2020, Verlust je Jahr, Kontrollfläche und dem Hinweis „kein Nachweis“',
          'kein Nachweis' in text and 'Wald Ende 2020' in text and 'Waldverlust 2021–2025' in text and 'Ausgewertet' in text and 'weicht ab' not in text and '2022:' in text, text)
    pruefungen = lambda: len(next(x for x in stand()['betriebe'] if x['id'] == k.evaluate("document.querySelector('#betrieb-inhalt').dataset.id"))['pruefungen'])
    vorher = pruefungen()
    offen = next(x for x in stand()['betriebe'] if x['id'] == k.evaluate("document.querySelector('#betrieb-inhalt').dataset.id"))
    erwartet = k.evaluate('(g) => window.EUDR_KARTE.auswerten(g)', offen['geometrie'])
    k.click('#betrieb-auswertung-nehmen')
    w = k.evaluate("(() => { const w = document.querySelector('#betrieb-inhalt').elements; return [w.p_portal.value, w.p_ergebnis.value, w.p_verlustHa.value, w.p_bemerkung.value]; })()")
    check('Bildauswertung übernehmen: füllt nur das Formular der Gegenprüfung (Andere Quelle, Verlust in ha, Bemerkung mit Quellen), trägt nichts ein',
          w[0] == 'sonst' and w[2] == ('%.2f' % erwartet['verlustHa']).replace('.', ',') and 'JRC GFC 2020' in w[3] and len(w[3]) <= 500
          and pruefungen() == vorher, w)
    check('Bildauswertung übernehmen: mindestens 0,5 ha Verlust auf Wald von 2020 → Vorschlag „Befund“, rot markiert',
          erwartet['verlustAufWaldHa'] >= 0.5 and w[1] == 'befund' and k.locator('#betrieb-auswertung dd .ci-marke.rot').count() == 1, (erwartet['verlustAufWaldHa'], w[1]))
    check('Bildauswertung: Text der Gegenprüfung nennt Datengrundlage mit Katalog-ID und Fassung (GEOS-EUDR …: FNF01, FNF17)',
          re.search(r'GEOS-EUDR-Katalog \(Thünen-Institut\) \w+ v\d+\.\d+: FNF01, FNF17\)', w[3]), w[3])
    k.click('#betrieb-auswertung [data-geodaten="FNF01"]'); k.wait_for_selector('#dlg-geodaten[open]')
    check('Bildauswertung: Verweis FNF01 öffnet den Katalogeintrag über dem Fenster „Farmer“',
          k.inner_text('#geodaten-titel').startswith('FNF01 · ') and k.evaluate("document.querySelector('#dlg-betrieb').open"), k.inner_text('#geodaten-titel'))
    k.click('#dlg-geodaten [data-zu]'); k.wait_for_function("!document.querySelector('#dlg-geodaten').open")
    check('Katalogeintrag geschlossen: Fenster „Farmer“ bleibt offen', k.evaluate("document.querySelector('#dlg-betrieb').open"))
    shot(k.locator('#dlg-betrieb'), os.path.join(SH, 'containerimport-bildauswertung-1280.png'))
    k.context.close()

    betriebMitBild = lambda pg: (pg.click('[data-sicht="karte"]'), pg.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000),
                                 pg.click('.ci-kartenliste button >> nth=0'), pg.wait_for_selector('#betrieb-auswertung:not([hidden])', timeout=60000))
    # Verlust nur außerhalb des Waldes von 2020 (rechte Hälfte): kein Befund; das Feld „Baumverlust“ bleibt leer, weil der
    # Server dort jede Zahl über 0 als kritisch wertet – der eingetragene Vorschlag darf den Betrieb nicht rot machen
    k = seite('ina', dienste=kartendienste([], verlust=png(lambda x, y: (255, 0, 22, 255) if x >= 256 and y < 256 else (0, 0, 0, 0)))); betriebMitBild(k)
    text = k.inner_text('#betrieb-auswertung'); nr = k.evaluate("document.querySelector('#betrieb-inhalt').dataset.id"); k.click('#betrieb-auswertung-nehmen')
    w = k.evaluate("(() => { const w = document.querySelector('#betrieb-inhalt').elements; return [w.p_ergebnis.value, w.p_verlustHa.value]; })()")
    gezaehlt = len(next(x for x in stand()['betriebe'] if x['id'] == nr)['pruefungen'])
    k.click('#betrieb-pruefung'); k.wait_for_function("(n) => document.querySelectorAll('#dlg-betrieb .ci-pruefungen li').length === n + 1", arg=gezaehlt)
    nach = next(x for x in stand()['betriebe'] if x['id'] == nr)
    check('Bildauswertung, Verlust nur außerhalb des Waldes von 2020: Vorschlag „ohne Befund“, Feld „Baumverlust“ leer; eingetragen bleibt die Gegenprüfung in Ordnung',
          'davon 0,0 ha auf Wald von 2020' in text and w == ['ohne_befund', ''] and len(nach['pruefungen']) == gezaehlt + 1 and nach['bewertung']['gegenpruefung'] == 'ok'
          and any('Bildauswertung im Container-Import' in x['bemerkung'] and x['portal'] == 'sonst' for x in nach['pruefungen']), (text, w, nach['bewertung'], len(nach['pruefungen'])))
    k.context.close()

    # Der Walddienst besteht die Probe, liefert dann aber keine Kacheln: die Karte wird trotzdem fertig, die Auswertung meldet es
    k = seite('ina', dienste=kartendienste([], ohne=(lambda u: 'ies-ows' in u and 'BBOX=0,0,1000,1000' not in u,))); betriebMitBild(k)
    check('Bildauswertung, ein Dienst antwortet nicht: Meldung statt Zahlen, nichts zu übernehmen',
          'Bildauswertung nicht möglich' in k.inner_text('#betrieb-auswertung') and 'nicht geantwortet' in k.inner_text('#betrieb-auswertung')
          and k.locator('#betrieb-auswertung dl, #betrieb-auswertung-nehmen').count() == 0, k.inner_text('#betrieb-auswertung'))
    k.context.close()

    # Geodaten-Katalog nicht erreichbar (500): die Bildauswertung erscheint trotzdem, der Beleg nennt die Kennungen ohne Fassung
    k = seite('ina', dienste=kartendienste([]))
    k.route(re.compile(r'/api/\?action=containerimport_eudr_geodaten'), lambda route: route.fulfill(status=500, content_type='application/json', body='{"ok":false,"error":"Der Geodaten-Katalog ist nicht lesbar."}'))
    betriebMitBild(k); k.wait_for_selector('#betrieb-auswertung:not([hidden]) dl')
    k.click('#betrieb-auswertung-nehmen')
    bemerkung = k.evaluate("document.querySelector('#betrieb-inhalt').elements.p_bemerkung.value")
    check('Katalog nicht erreichbar: Bildauswertung erscheint trotzdem, Beleg „Fassung nicht geladen: FNF01, FNF17“',
          'Wald Ende 2020' in k.inner_text('#betrieb-auswertung') and 'GEOS-EUDR-Katalog (Thünen-Institut) Fassung nicht geladen: FNF01, FNF17' in bemerkung, bemerkung)
    k.click('#betrieb-auswertung [data-geodaten="FNF01"]'); k.wait_for_selector('#dlg-geodaten[open]')
    check('Katalog nicht erreichbar: Verweis öffnet ein Fenster mit Hinweis statt Eintrag', 'gerade nicht erreichbar' in k.inner_text('#dlg-geodaten'), k.inner_text('#dlg-geodaten'))
    k.click('#dlg-geodaten [data-zu]'); k.keyboard.press('Escape'); k.wait_for_function("!document.querySelector('#dlg-betrieb').open")
    k.click('[data-sicht="geodaten"]'); k.wait_for_selector('#ci-inhalt .ci-leer:not([role])')
    check('Katalog nicht erreichbar: Ansicht „Geodaten-Katalog“ meldet es', 'Der Geodaten-Katalog ist gerade nicht erreichbar' in k.inner_text('#ci-inhalt'), k.inner_text('#ci-inhalt'))
    k.context.close()

    # Satellitenbild und Walddienst fallen aus: die Karte zeigt, was erreichbar ist; die Auswertung braucht den Walddienst
    k = seite('ina', dienste=kartendienste([], ohne=('eox.at',)))
    k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Satellitenbild nicht erreichbar: Karte mit Wald 2020 und Waldverlust', k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts() == ['Wald Ende 2020 (EU)', 'Waldverlust 2021–2025'])
    k.click('.ci-kartenliste button >> nth=0'); k.wait_for_selector('#betrieb-auswertung:not([hidden]) dl', timeout=60000)
    check('Satellitenbild nicht erreichbar: die Bildauswertung rechnet trotzdem', 'Wald Ende 2020' in k.inner_text('#betrieb-auswertung'))
    k.context.close()

    k = seite('ina', dienste=kartendienste([], ohne=('ies-ows',)))
    k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    k.click('.ci-kartenliste button >> nth=0'); k.wait_for_selector('#betrieb-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Walddienst nicht erreichbar: Karte ohne diese Ebene, keine Bildauswertung',
          k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts() == ['Satellitenbild (2016)', 'Waldverlust 2021–2025'] and k.is_hidden('#betrieb-auswertung'))
    k.context.close()

    abrufe = []
    k = seite('ina', dienste=kartendienste(abrufe, ohne=('globalforestwatch',)))
    k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Waldverlust-Dienst nicht erreichbar: Karte mit Satellitenbild und Wald 2020, ohne dritte Ebene',
          k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts() == ['Satellitenbild (2016)', 'Wald Ende 2020 (EU)'])
    k.context.close()

    k = seite('ina', dienste=kartendienste([])); k.context.route('**/karte/herkunft.pmtiles', kartendatei)
    k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Bilder und Herkunftskarte zusammen: Straßen und Orte als vierte Ebene über den Bildern',
          k.locator('#ci-karte .ci-k-ebenen label').all_inner_texts()[-1] == 'Straßen und Orte' and k.evaluate(ebenen % '#ci-karte')['grund'] is True)
    k.uncheck('#ci-karte .ci-k-ebenen input[value="grund"]')
    check('Straßen und Orte lassen sich abschalten', k.evaluate(ebenen % '#ci-karte')['grund'] is False)
    k.context.close()

    k = seite('ina', {'width': 390, 'height': 844}, 'dark', dienste=kartendienste([]))
    k.wait_for_selector('#ci-app:not([hidden])'); k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=60000)
    check('Karte mit Bildern, Handy 390 px: Ebenen eingeklappt, nichts läuft über den Rand',
          k.evaluate("!document.querySelector('#ci-karte .ci-k-ebenen').open && document.documentElement.scrollWidth <= window.innerWidth + 1"))
    k.click('#ci-karte .ci-k-ebenen summary')
    shot(k, os.path.join(SH, 'containerimport-karte-bilder-390-dunkel.png'))
    k.context.close()

    if os.environ.get('WA_KARTE_ECHT'):   # nur von Hand: Bildschirmfotos mit den echten Diensten (braucht Netz), keine Prüfung
        k = seite('ina', dienste=lambda route: route.continue_())
        k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=120000)
        shot(k, os.path.join(SH, 'containerimport-karte-echt-uebersicht.png'))
        k.click('.ci-kartenliste button >> nth=0'); k.wait_for_selector('#betrieb-karte[data-karte="bereit"] canvas', timeout=120000)
        shot(k, os.path.join(SH, 'containerimport-karte-echt-betrieb.png'))
        k.wait_for_selector('#betrieb-auswertung:not([hidden])', timeout=120000)
        print('Bildauswertung mit echten Diensten:', k.inner_text('#dlg-betrieb h2, #dlg-betrieb .dlg-head').split('\n')[0], '|', k.inner_text('#betrieb-auswertung').replace('\n', ' | '))
        k.locator('#betrieb-auswertung').scroll_into_view_if_needed(); shot(k, os.path.join(SH, 'containerimport-karte-echt-auswertung.png'))
        probe = [[-56.25, -22.85], [-56.15, -22.85], [-56.15, -22.95], [-56.25, -22.95], [-56.25, -22.85]]   # Gegend mit viel Verlust, zum Nachrechnen
        print('Bildauswertung Probefläche:', json.dumps(k.evaluate('(g) => window.EUDR_KARTE.auswerten(g)', {'type': 'Polygon', 'coordinates': [probe]})))
        k.context.close()
        k = seite('ina', dienste=lambda route: route.continue_()); k.context.route('**/karte/herkunft.pmtiles', kartendatei)   # Straßen und Orte über dem Bild: der Testauszug kennt nur Hamburg
        k.click('[data-sicht="karte"]'); k.wait_for_selector('#ci-karte[data-karte="bereit"] canvas', timeout=120000)
        k.evaluate("document.querySelector('#ci-karte').staflKarte.map.jumpTo({ center: [9.99, 53.55], zoom: 12.5 })"); k.wait_for_selector('#ci-karte[data-karte="bereit"]', timeout=120000)
        shot(k, os.path.join(SH, 'containerimport-karte-echt-strassen.png'))
        k.context.close()

    # Handy 390 px, dunkel: nichts läuft über den Rand
    m = seite('ina', {'width': 390, 'height': 844}, 'dark'); m.wait_for_selector('#ci-app:not([hidden]) #ci-sendungen tr[data-sendung]')
    breit = lambda pg: pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
    check('390 px: Liste ohne Querlauf', breit(m))
    shot(m, os.path.join(SH, 'containerimport-sendungen-390-dunkel.png'))
    m.click('#ci-sendungen tr[data-sendung]'); m.wait_for_selector('#dlg-sendung[open]')
    check('390 px: Fenster „Container“ passt in die Breite, Tippflächen ab 36 px', m.evaluate("document.querySelector('#dlg-sendung').getBoundingClientRect().width <= window.innerWidth")
          and m.eval_on_selector_all('#dlg-sendung button, #dlg-sendung select, #dlg-sendung input:not([type=checkbox])', 'els => els.filter(e => e.offsetParent).every(e => e.getBoundingClientRect().height >= 36)'))
    shot(m, os.path.join(SH, 'containerimport-sendung-390-dunkel.png'))
    m.keyboard.press('Escape'); m.click('[data-sicht="karte"]'); m.wait_for_function("document.querySelector('#ci-karte')?.dataset.karte === 'bereit'")
    check('390 px: Karte ohne Querlauf', breit(m))
    shot(m, os.path.join(SH, 'containerimport-karte-390-dunkel.png'))
    m.context.close()

    # Nur ansehen
    v = seite('lea'); v.wait_for_selector('#ci-app:not([hidden]) #ci-sendungen tr[data-sendung]')
    check('nur ansehen: keine Knöpfe „Unterlagen einlesen“ und „Neue Container“', v.locator('#ci-lesen').count() == 0 and v.locator('#ci-sendung-neu').count() == 0)
    v.click('#ci-sendungen tr[data-sendung]'); v.wait_for_selector('#dlg-sendung[open]')
    check('nur ansehen: Felder gesperrt, kein „Speichern“, Export bleibt', v.eval_on_selector_all('#dlg-sendung input, #dlg-sendung select, #dlg-sendung textarea', 'els => els.every(e => e.disabled)')
          and v.locator('#dlg-sendung button[type=submit]').count() == 0 and v.locator('#dlg-sendung [data-export-sendung]').count() == 1)
    v.context.close()
    br.close()
# ---------- Originale im QM-System (Schnittstelle qs_eingang_hochladen) ----------
def original(c, name, inhalt, lieferant='Frigorifico Beispiel', teil=1 << 20):
    """Datei in Teilen an containerimport_eudr_original geben; Antwort des letzten Aufrufs."""
    upload = ''; antwort = (0, {})
    for nr, ab in enumerate(range(0, max(len(inhalt), 1), teil)):
        antwort = c.call('containerimport_eudr_original', {'upload': upload, 'teil': nr, 'daten': base64.b64encode(inhalt[ab:ab + teil]).decode(), 'name': name,
                                                            'groesse': len(inhalt), 'sha256': hashlib.sha256(inhalt).hexdigest(), 'lieferant': lieferant})
        if antwort[0] != 200 or antwort[1].get('fertig'):
            break
        upload = antwort[1]['upload']
    return antwort


check('Original ablegen: nur mit „EUDR bearbeiten“ (403), nicht per GET (405)', original(L, 'x.pdf', REPORT)[0] == 403 and I.call('containerimport_eudr_original')[0] == 405)
st, r = original(I, 'Compliance_Report_Estancia_Beispiel.pdf', REPORT)
check('dasselbe Original noch einmal: nicht doppelt abgelegt', st == 200 and r['fertig'] and r['status'] == 'vorhanden' and r['vermerkt'] == 1 and len(r['betriebe']) == 6
      and len([f for f in _json(storage_raw('qs-ablage'))['liste'] if f.get('ziel') == 'eingang']) == 1, (st, r.get('status'), r.get('error')))
gross = REPORT + b'%' + b' ' * (2 * 1024 * 1024 + 500)   # über zwei Teile
st, r = original(I, 'Grosser_Bericht.pdf', gross)
neu = [f for f in _json(storage_raw('qs-ablage'))['liste'] if f.get('name') == 'Grosser_Bericht.pdf']
check('Original in mehreren Teilen: vollständig im Eingang, ohne passenden Farmer kein Vermerk', st == 200 and r['status'] == 'eingang' and r['vermerkt'] == 0 and len(neu) == 1 and neu[0]['groesse'] == len(gross)
      and neu[0]['sha256'] == hashlib.sha256(gross).hexdigest(), (st, r.get('status'), r.get('error'), neu))
st, r = original(I, 'lieferant.json', GEOJSON.encode(), lieferant='')
check('GeoJSON als „.json“, ohne Lieferant direkt im Ordner „EUDR“', st == 200 and r['status'] == 'eingang' and [f['pfad'] for f in _json(storage_raw('qs-ablage'))['liste'] if f['name'] == 'lieferant.json'] == ['EUDR'], (st, r))
st, r = original(I, 'bericht.exe', b'MZ' + b'0' * 100)
check('gesperrte Dateiart wird abgewiesen (422)', st == 422, (st, r))
eingang = A.call('qs_eingang')
check('QM-System: die Originale erscheinen im Eingang (nur mit qs.bearbeiten)', eingang[0] == 200 and 'Compliance_Report_Estancia_Beispiel.pdf' in json.dumps(eingang[1], ensure_ascii=False) and I.call('qs_eingang')[0] == 403, eingang[0])
check('Protokoll nennt die Ablage', 'im Eingang des QM-Systems abgelegt' in json.dumps(A.call('log')[1], ensure_ascii=False))
check('keine JavaScript-Fehler', not errs, errs)

print(f'{sum(res)}/{len(res)} passed')
