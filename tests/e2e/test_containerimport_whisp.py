"""Container-Import · EUDR: Abfrage von Whisp (FAO) für die eigene Gegenprüfung (Aktion containerimport_eudr_whisp,
app/api/module/containerimport/whisp.php, Deutung in app/module/containerimport/eudr-whisp.js).
Whisp ist nachgebaut (Hilfsserver auf AUX_PORT, WA_WHISP_URL); der Zugangsschlüssel dieser Gruppe ist ein Testwert
(WHISP_API_KEY in tests/run_e2e.py) – die Gruppe „containerimport“ läuft ohne Schlüssel und prüft, dass die Abfrage dann aus ist.
Geprüft: Rechte (nur mit „EUDR bearbeiten“, CSRF, kein GET); an Whisp geht nur der Umriss mit dem Schlüssel in der Kopfzeile,
keine Namen; Vorgang starten, nachfragen, Ergebnis gefiltert (nur einfache Werte mit harmlosen Namen); nichts wird gespeichert,
der Versand steht im Protokoll; Fehler von Whisp (Schlüssel abgelehnt, Drosselung, unbekannter Vorgang, nicht erreichbar)
als verständliche Meldung, der Schlüssel erscheint in keiner Antwort; zu große Fläche und ungültige Vorgangsnummer gehen nicht hinaus.
Oberfläche: Knopf nur mit Recht, Wartemeldung, Ergebnis mit Vorschlag, Übernahme ins Formular (Befund mit Baumverlust, kein
Vorschlag lässt die Auswahl stehen), Eintragen erst mit dem Knopf des Formulars, fremde Texte maskiert, Fehlermeldung; Deutung
der Felder (Regel für Baumbestand und Störung, künftige Spalte für Rinder hat Vorrang). Alle Betriebe sind erfunden (GR-007)."""
import http.server
import json
import os
import re
import threading
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import AUX_PORT, SH, FIX, shot

PW = 'Sicheres-Passwort-1'
SCHLUESSEL = 'nur-fuer-den-test'   # wie WHISP_API_KEY dieser Gruppe in tests/run_e2e.py
VORGANG = 'vorgang-abc123'       # Vorgangsnummer des nachgebauten Dienstes
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i and not c else ''))


# ---------- nachgebautes Whisp ----------
FELDER = {'plotId': '1', 'Area': 166.3, 'Country': 'PRY', 'Unit': 'ha', 'In_waterbody': False, 'GFC_TC_2020': 80.5,
          'Ind_01_treecover': 'yes', 'Ind_02_commodities': 'no', 'Ind_03_disturbance_before_2020': 'no', 'Ind_04_disturbance_after_2020': 'yes',
          'GFC_loss_after_2020': 12.34, 'RADD_after_2020': 3.2, 'MODIS_fire_after_2020': 0, 'risk_pcrop': 'high', 'risk_acrop': 'high', 'risk_timber': 'more_info_needed',
          'whisp_processing_metadata': {'whisp_version': '3.0.0a22', 'processing_timestamp_utc': '2026-11-19 08:00:00+0000'},
          'geo<b>': 'x', 'Zu_lang': 'x' * 300, 'Liste': [1, 2]}
SPIEL = {'modus': 'ok', 'felder': FELDER, 'anfragen': [], 'nachfragen': 0}


class Whisp(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def antwort(self, status, inhalt):
        roh = json.dumps(inhalt).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(roh))); self.end_headers(); self.wfile.write(roh)

    def bedienen(self):
        inhalt = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'null')
        SPIEL['anfragen'].append({'methode': self.command, 'pfad': self.path, 'schluessel': self.headers.get('x-api-key'), 'inhalt': inhalt})
        if self.headers.get('x-api-key') != SCHLUESSEL or SPIEL['modus'] == 'schluessel':
            return self.antwort(401, {'code': 'auth_invalid_api_key', 'message': 'Invalid or expired API key.'})
        if SPIEL['modus'] == 'drossel':
            return self.antwort(429, {'code': 'auth_rate_limit_exceeded', 'message': 'Rate limit exceeded. Try again in 30 seconds.'})
        if self.command == 'POST' and self.path == '/api/submit/geojson':
            SPIEL['nachfragen'] = 0
            return self.antwort(202, {'code': 'analysis_queued', 'message': 'Analysis queued', 'data': {'token': VORGANG, 'statusUrl': '/api/status/' + VORGANG, 'featureCount': 1}})
        if self.command == 'GET' and self.path == '/api/status/' + VORGANG:
            SPIEL['nachfragen'] += 1
            if SPIEL['nachfragen'] == 1:
                return self.antwort(202, {'code': 'analysis_processing', 'message': 'Analysis in progress...', 'data': {'token': VORGANG, 'percent': 42.0, 'processStatusMessage': []}})
            return self.antwort(200, {'code': 'analysis_completed', 'message': 'Analysis completed successfully', 'data': {'type': 'FeatureCollection', 'features': [
                {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [0, 0]}, 'properties': SPIEL['felder']}]}})
        return self.antwort(404, {'code': 'analysis_job_not_found', 'message': 'Analysis job not found.'})

    do_GET = do_POST = bedienen


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Whisp)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# ---------- Nutzer und Betriebe ----------
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
USERS = {'ina': ('Ina Import', 'editor', 'Editor-Zugang-88', ['containerimport.eudr_sehen', 'containerimport.eudr_bearbeiten']),
         'lea': ('Lea Leser', 'viewer', 'Leser-Zugang-55', ['containerimport.eudr_sehen'])}
for user, (name, role, pw, grant) in USERS.items():
    A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    nr = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == user)
    A.call('user_save', {'id': nr, 'name': name, 'role': role, 'active': True, 'grant': grant, 'deny': []})


def login(user):
    c = Client('198.51.100.' + str(10 + list(USERS).index(user)))
    code, r = c.call('login', {'username': user, 'password': USERS[user][2]})
    assert code == 200, (user, code, r)
    return c


I, L = login('ina'), login('lea')
GEOJSON = open(os.path.join(FIX, 'containerimport', 'lieferant.geojson'), encoding='utf-8').read()
RIESIG = json.dumps({'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': {'ProducerName': 'Ganadera Ejemplo S.A.', 'ProducerCountry': 'PY', 'ProductionPlace': 'Estancia Riesig'},
                    'geometry': {'type': 'Polygon', 'coordinates': [[[-60, -25], [-56, -25], [-56, -21], [-60, -21], [-60, -25]]]}}]})
dateien = [{'art': 'geojson', 'datei': 'lieferant.geojson', 'sha256': 'b' * 64, 'land': 'PY', 'lieferant': 'Frigorifico Beispiel', 'text': GEOJSON},
           {'art': 'geojson', 'datei': 'riesig.geojson', 'sha256': 'c' * 64, 'land': 'PY', 'lieferant': 'Frigorifico Beispiel', 'text': RIESIG}]
orte = [o for d in I.call('containerimport_eudr_pruefen', {'dateien': dateien})[1]['dateien'] for o in d['orte']]
st, r = I.call('containerimport_eudr_betriebe_save', {'betriebe': [o['eingabe'] for o in orte if o['name'] in ('Estancia Ejemplo Norte', 'Estancia Riesig')]})
betrieb = {b['name']: b for b in r.get('betriebe', [])}
nord, riesig = betrieb.get('Estancia Ejemplo Norte'), betrieb.get('Estancia Riesig')
check('Betriebe angelegt (166 ha und über 100.000 ha)', st == 200 and nord and riesig and riesig['flaeche'] > 100000, (st, r.get('error'), list(betrieb)))

# ---------- Rechte ----------
check('Stand: Abfrage eingerichtet – nur wer bearbeiten darf, bekommt sie angeboten',
      I.call('containerimport_start')[1]['rechte'] == {'bearbeiten': True, 'whisp': True} and L.call('containerimport_start')[1]['rechte'] == {'bearbeiten': False, 'whisp': False})
check('nur ansehen: Abfrage 403', L.call('containerimport_eudr_whisp', {'id': nord['id']})[0] == 403)
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_eudr_whisp', {'id': nord['id']})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_eudr_whisp')[0] == 405)
check('unbekannter Betrieb 404, ungültige Vorgangsnummer 422, zu große Fläche 422', [I.call('containerimport_eudr_whisp', x)[0] for x in ({'id': 'gibt-es-nicht'}, {'token': '../config'}, {'token': 'a b'}, {'id': riesig['id']})] == [404, 422, 422, 422])
check('bis hierher ging nichts an Whisp', SPIEL['anfragen'] == [], SPIEL['anfragen'])

# ---------- Abfrage: starten, nachfragen, Ergebnis ----------
st, r, roh1 = I.call('containerimport_eudr_whisp', {'id': nord['id']}, raw=True)
an = SPIEL['anfragen'][-1] if SPIEL['anfragen'] else {}
check('Start: Vorgangsnummer, noch nicht fertig', st == 200 and r.get('fertig') is False and r.get('token') == VORGANG, (st, r))
check('An Whisp geht nur der Umriss: eine Fläche ohne Eigenschaften, Auswertung im Hintergrund in Hektar, Schlüssel in der Kopfzeile',
      len(SPIEL['anfragen']) == 1 and an['methode'] == 'POST' and an['pfad'] == '/api/submit/geojson' and an['schluessel'] == SCHLUESSEL
      and set(an['inhalt']) == {'type', 'features', 'analysisOptions'} and an['inhalt']['analysisOptions'] == {'async': True, 'unitType': 'ha'}
      and an['inhalt']['features'] == [{'type': 'Feature', 'properties': {}, 'geometry': nord['geometrie']}] and 'Ejemplo' not in json.dumps(an['inhalt']), an)
st, r, roh2 = I.call('containerimport_eudr_whisp', {'token': VORGANG}, raw=True)
check('Nachfragen: in Arbeit mit Fortschritt', st == 200 and r.get('fertig') is False and r.get('prozent') == 42 and r.get('token') == VORGANG, (st, r))
st, r, roh3 = I.call('containerimport_eudr_whisp', {'token': VORGANG}, raw=True)
felder = (r.get('ergebnis') or {}).get('felder', {})
check('Ergebnis: Eigenschaften der Fläche und Version', st == 200 and r.get('fertig') is True and r['ergebnis']['version'] == '3.0.0a22'
      and felder.get('Ind_04_disturbance_after_2020') == 'yes' and felder.get('GFC_loss_after_2020') == 12.34 and felder.get('In_waterbody') is False and felder.get('Unit') == 'ha', (st, r))
check('Ergebnis gefiltert: keine verschachtelten Werte, keine auffälligen Namen, keine überlangen Texte, kein Umriss',
      not {'whisp_processing_metadata', 'geo<b>', 'Zu_lang', 'Liste'} & set(felder) and 'geometry' not in roh3 and 'coordinates' not in roh3, sorted(felder))
check('Der Schlüssel steht in keiner Antwort', all(SCHLUESSEL not in x for x in (roh1, roh2, roh3)))
check('Nichts gespeichert: der Betrieb hat keine Gegenprüfung', next(b for b in I.call('containerimport_start')[1]['betriebe'] if b['id'] == nord['id'])['pruefungen'] == [])
check('Protokoll: Versand des Umrisses an Whisp vermerkt', 'Umriss von „Estancia Ejemplo Norte“ zur Prüfung an Whisp gesendet' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ---------- Fehler von Whisp ----------
SPIEL['modus'] = 'schluessel'
st, r, roh = I.call('containerimport_eudr_whisp', {'id': nord['id']}, raw=True)
check('Whisp lehnt den Schlüssel ab: 503 mit Hinweis auf den Administrator, ohne Schlüssel im Text', st == 503 and 'Zugangsschlüssel' in r.get('error', '') and SCHLUESSEL not in roh, (st, r))
SPIEL['modus'] = 'drossel'
st, r = I.call('containerimport_eudr_whisp', {'id': nord['id']})
check('Whisp drosselt: 502 „in einigen Minuten erneut“', st == 502 and 'einigen Minuten' in r.get('error', ''), (st, r))
SPIEL['modus'] = 'ok'
st, r = I.call('containerimport_eudr_whisp', {'token': 'gibt-es-nicht'})
check('Unbekannter Vorgang: 502 „bitte neu starten“', st == 502 and 'neu starten' in r.get('error', ''), (st, r))

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        ctx = br.new_context(viewport=vp or {'width': 1280, 'height': 900}, color_scheme=schema)
        ctx.route(re.compile(r'^https?://(?!127\.0\.0\.1[:/])'), lambda route: (fremd.append(route.request.url), route.abort()))   # Kartendienste: Tests rufen nie fremde Server ab
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', USERS[user][2]); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.goto(B + '/module/containerimport/'); pg.wait_for_selector('#ci-app:not([hidden])')
        pg.click('[data-sicht="betriebe"]'); pg.click(f'[data-betrieb="{nord["id"]}"]'); pg.wait_for_selector('#dlg-betrieb[open] #betrieb-inhalt')
        return pg

    formular = "(() => { const w = document.querySelector('#betrieb-inhalt').elements; return [w.p_portal.value, w.p_ergebnis.value, w.p_verlustHa.value, w.p_bemerkung.value]; })()"

    le = seite('lea')
    le.wait_for_selector('#betrieb-karte[data-karte="bereit"]')
    check('Kartendienste sind im Test gesperrt (die Karte fragt sie an, bekommt nichts): keine Bildauswertung', fremd and le.is_hidden('#betrieb-auswertung'), fremd[:3])
    check('Oberfläche, nur ansehen: kein Knopf „In Whisp prüfen“', le.locator('#betrieb-whisp').count() == 0 and le.locator('#betrieb-whisp-ergebnis').is_hidden())
    le.context.close()

    # Deutung der Felder (reine Rechnung in eudr-whisp.js)
    p = seite('ina')
    deuten = lambda felder: p.evaluate('(f) => window.EUDR_WHISP.deuten({ felder: f, version: "" })', felder)
    wald = {'Unit': 'ha', 'Ind_01_treecover': 'yes', 'Ind_03_disturbance_before_2020': 'no'}
    d = [deuten({**wald, 'Ind_04_disturbance_after_2020': 'yes', 'GFC_loss_after_2020': 4.0}), deuten({**wald, 'Ind_04_disturbance_after_2020': 'no', 'RADD_after_2020': 0.4}),
         deuten({**wald, 'Ind_04_disturbance_after_2020': 'no', 'RADD_after_2020': 3.2}), deuten({**wald, 'Ind_01_treecover': 'no', 'Ind_04_disturbance_after_2020': 'yes', 'GFC_loss_after_2020': 9.0})]
    check('Deutung: Baumbestand 2020 und Störung danach = Befund mit Baumverlust; kleine Störung = ohne Befund; Störung ab 0,5 ha unter der Schwelle von Whisp = kein Vorschlag; kein Baumbestand 2020 = ohne Befund',
          [(x['vorschlag'], x['verlustHa']) for x in d] == [('befund', 4), ('ohne_befund', None), (None, None), ('ohne_befund', None)], [(x['vorschlag'], x['verlustHa']) for x in d])
    d = [deuten({**wald, 'Ind_01_treecover': 'no', 'Ind_04_disturbance_after_2020': 'no', 'risk_cattle': 'high'}), deuten({**wald, 'Ind_04_disturbance_after_2020': 'yes', 'risk_cattle': 'low'}),
         deuten({**wald, 'Ind_04_disturbance_after_2020': 'yes', 'risk_cattle': 'more_info_needed'}), deuten({'Area': 5}), deuten({**wald, 'Unit': '%', 'Ind_04_disturbance_after_2020': 'no', 'RADD_after_2020': 30})]
    check('Deutung: eine Risikospalte für Rinder hat Vorrang; „weitere Angaben nötig“ und unbekanntes Format = kein Vorschlag; Prozentwerte werden nicht als Hektar gelesen',
          [x['vorschlag'] for x in d] == ['befund', 'ohne_befund', None, None, 'ohne_befund'] and d[3]['wald'] is None, [x['vorschlag'] for x in d])

    # Abfrage aus dem Fenster: warten, Ergebnis, übernehmen, eintragen
    vorher = len(SPIEL['anfragen'])
    p.click('#betrieb-whisp'); p.wait_for_selector('#betrieb-whisp-ergebnis [role="status"]')
    check('Oberfläche: Wartemeldung, Knopf gesperrt', 'Whisp wertet die Fläche aus' in p.inner_text('#betrieb-whisp-ergebnis') and p.is_disabled('#betrieb-whisp'))
    p.wait_for_selector('#betrieb-whisp-nehmen', timeout=30000)
    text = p.inner_text('#betrieb-whisp-ergebnis')
    check('Oberfläche: Ergebnis mit Baumbestand, Störungen je Datensatz, Risiko laut Whisp und Vorschlag „Befund“',
          'Ergebnis von Whisp' in text and 'GFC_loss_after_2020: 12,3 ha' in text and 'RADD_after_2020: 3,2 ha' in text and 'MODIS_fire' not in text
          and 'Dauerkulturen: hoch' in text and 'Holz: weitere Angaben nötig' in text and 'Ausgewertet 166,3 ha in PRY' in text
          and p.inner_text('#betrieb-whisp-ergebnis dl dd:last-child .ci-marke') == 'Befund' and p.is_enabled('#betrieb-whisp'), text)
    check('Oberfläche: gestartet und zweimal nachgefragt', [x['methode'] for x in SPIEL['anfragen'][vorher:]] == ['POST', 'GET', 'GET'], SPIEL['anfragen'][vorher:])
    shot(p, os.path.join(SH, 'containerimport-whisp-1280.png'))
    p.click('#betrieb-whisp-nehmen'); w = p.evaluate(formular)
    check('Übernehmen: Portal Whisp, Befund, Baumverlust 12,34 ha, Bemerkung mit Version – noch nichts gespeichert',
          w[:3] == ['whisp', 'befund', '12,34'] and w[3].startswith('Whisp (FAO, Version 3.0.0a22): Baumbestand 2020 ja, Störung vor 2020 nein, Störung nach 2020 ja') and len(w[3]) <= 500
          and next(b for b in I.call('containerimport_start')[1]['betriebe'] if b['id'] == nord['id'])['pruefungen'] == [], w)
    p.click('#betrieb-pruefung'); p.wait_for_function("document.querySelectorAll('#dlg-betrieb .ci-pruefungen li').length === 1")
    nach = next(b for b in I.call('containerimport_start')[1]['betriebe'] if b['id'] == nord['id'])
    check('Eintragen: Gegenprüfung „Whisp (FAO)“ mit Befund am Betrieb', len(nach['pruefungen']) == 1 and nach['pruefungen'][0]['portal'] == 'whisp' and nach['pruefungen'][0]['ergebnis'] == 'befund'
          and nach['pruefungen'][0]['verlustHa'] == 12.34 and nach['bewertung']['gegenpruefung'] == 'kritisch', nach['pruefungen'])

    # Kein Vorschlag: die Auswahl im Formular bleibt, Baumverlust leer; fremde Texte werden maskiert
    SPIEL['felder'] = {**FELDER, 'Ind_04_disturbance_after_2020': 'no', 'GFC_loss_after_2020': 0, 'Country': '<img src=x onerror=alert(1)>', 'Unit': 'ha'}
    p.select_option('[name="p_ergebnis"]', 'befund')
    p.click('#betrieb-whisp'); p.wait_for_selector('#betrieb-whisp-nehmen', timeout=30000)
    check('Oberfläche: Störung unter der Schwelle von Whisp – „kein Vorschlag“; fremder Text erscheint als Text',
          'kein Vorschlag' in p.inner_text('#betrieb-whisp-ergebnis') and '<img src=x' in p.inner_text('#betrieb-whisp-ergebnis') and p.locator('#betrieb-whisp-ergebnis img').count() == 0, p.inner_text('#betrieb-whisp-ergebnis'))
    p.click('#betrieb-whisp-nehmen'); w = p.evaluate(formular)
    check('Übernehmen ohne Vorschlag: Auswahl „Befund“ bleibt stehen, Baumverlust leer', w[:3] == ['whisp', 'befund', ''] and 'Störung nach 2020 nein' in w[3], w)

    SPIEL['modus'] = 'drossel'
    p.click('#betrieb-whisp'); p.wait_for_function("document.querySelector('#betrieb-whisp-ergebnis').innerText.includes('einigen Minuten')")
    check('Oberfläche: Meldung von Whisp statt Ergebnis, Knopf wieder frei', p.locator('#betrieb-whisp-nehmen').count() == 0 and p.is_enabled('#betrieb-whisp'), p.inner_text('#betrieb-whisp-ergebnis'))
    SPIEL['modus'] = 'ok'; SPIEL['felder'] = FELDER
    p.context.close()

    m = seite('ina', {'width': 390, 'height': 844}, 'dark')
    m.click('#betrieb-whisp'); m.wait_for_selector('#betrieb-whisp-nehmen', timeout=30000)
    check('Handy 390 px: Ergebnis ohne waagerechtes Scrollen', m.evaluate("document.querySelector('#betrieb-whisp-ergebnis').scrollWidth <= document.querySelector('#betrieb-whisp-ergebnis').clientWidth + 1"))
    m.locator('#betrieb-whisp-ergebnis').scroll_into_view_if_needed(); shot(m, os.path.join(SH, 'containerimport-whisp-390-dunkel.png'))
    m.context.close()
    br.close()

# ---------- Whisp nicht erreichbar ----------
srv.shutdown(); srv.server_close()
st, r = I.call('containerimport_eudr_whisp', {'id': nord['id']})
check('Whisp nicht erreichbar: 502 „gerade nicht erreichbar“', st == 502 and 'nicht erreichbar' in r.get('error', ''), (st, r))

check('keine JavaScript-Fehler', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
raise SystemExit(0 if all(res) else 1)
