"""Container-Import · EUDR (Argentinien): Abfrage von VISEC Carne über die DTE-Nummern eines Containers (Aktion
containerimport_visec_abfragen, app/api/module/containerimport/visec.php, Oberfläche app/module/containerimport/visec.js).
VISEC ist nachgebaut (Hilfsserver auf AUX_PORT, WA_VISEC_URL); der Token dieser Gruppe ist ein Testwert (VISEC_API_TOKEN in
tests/run_e2e.py) – die Gruppe „containerimport“ läuft ohne Token und prüft, dass die Abfrage dann aus ist.
Geprüft: DTE-Nummern am Container (bereinigt, ohne Doppelte, Grenzen, bleiben ohne Eingabe erhalten); Rechte (nur mit
„EUDR bearbeiten“, CSRF, kein GET); an VISEC geht je DTE nur die Nummer mit dem Token in der Kopfzeile; Antworten je DTE
abgelegt und dazugestellt (Zahlen je Stand, ungültige und offene Tiere mit Nummer, höchstens 100 je Liste); Kriterium
„Tiere laut VISEC“ im Risikoprofil (fehlt ohne DTE; nicht abgefragt, unbekannte DTE, offene Tiere = offen; ungültige = kritisch;
alle gültig = in Ordnung) und seine Wirkung auf den Abschluss; nach dem Abschluss keine Abfrage mehr; Fehler von VISEC
(Token abgelehnt, Serverfehler, fremde Antwort, Abbruch) als verständliche Meldung, ohne etwas zu überschreiben, der Token in
keiner Antwort; scheitert VISEC an einer späteren Nummer, wird das Geholte abgelegt und der Rest gemeldet; Protokoll. Oberfläche: Bereich nur bei Argentinien oder gespeicherten Nummern, Speichern und Abfragen in einem
Schritt, Profil im Fenster neu, nur ansehen ohne Eingabe und Knopf, fremde Texte maskiert, 390 px dunkel.
Alle DTE- und Ohrmarkennummern sind erfunden (GR-007)."""
import http.server
import json
import os
import threading
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, stand, container_anlegen, container, seite
from umgebung import AUX_PORT, SH, shot

TOKEN = 'nur-fuer-den-test-visec'   # wie VISEC_API_TOKEN dieser Gruppe in tests/run_e2e.py
UUID = '0f8fad5b-d9cb-469f-a165-70867728950e'


def tiere(*staende, vorsilbe='AR-T'):
    return [{'dteCaravanaId': i + 1, 'caravanaId': i + 1, 'caravanaNumero': f'{vorsilbe}{i + 1:04d}', 'caravanaTipo': 'HEMBRA', 'estado': e} for i, e in enumerate(staende)]


def dte(nummer, caravanas, dte_id=None, tropa='T-0042'):
    return {'dteId': dte_id if dte_id is not None else 4711, 'numero': nummer, 'fechaDte': '2026-10-01T08:30:00', 'fechaEstado': '2026-10-02T09:15:00',
            'fechaArribo': '2026-10-01T18:00:00', 'estado': 'CERRADO', 'tropa': tropa, 'caravanas': caravanas}


# ---------- nachgebautes VISEC ----------
DATEN = {   # DTE-Nummer → Antwort von POST /api/Visec/dte
    '100200300': {'dte': dte('100200300', tiere('VALIDA', 'VALIDA', 'VALIDA'))},
    '100200301': {'dte': dte('100200301', tiere('VALIDA', 'VALIDA', 'EN_VALIDACION', vorsilbe='AR-U'))},
}
SPIEL = {'modus': 'ok', 'anfragen': []}   # modus: ok | token | kaputt | fremd | abbruch


class Visec(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def antwort(self, status, roh, art='application/json'):
        self.send_response(status); self.send_header('Content-Type', art); self.send_header('Content-Length', str(len(roh))); self.end_headers(); self.wfile.write(roh)

    def do_POST(self):
        inhalt = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'null')
        SPIEL['anfragen'].append({'pfad': self.path, 'token': self.headers.get('Authorization'), 'inhalt': inhalt})
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN or SPIEL['modus'] == 'token':
            return self.antwort(401, b'')
        if SPIEL['modus'] == 'kaputt':
            return self.antwort(500, json.dumps({'error': {'code': 'X', 'description': 'boom'}}).encode())
        if SPIEL['modus'] == 'fremd':
            return self.antwort(200, b'<html>Wartung</html>', 'text/html')
        if SPIEL['modus'] == 'abbruch':   # Verbindung ohne Antwort schließen
            self.close_connection = True
            return
        if self.path != '/api/Visec/dte':
            return self.antwort(404, b'')
        nummer = (inhalt or {}).get('numero', '')
        if nummer == '777000777':   # einzelne Nummer, bei der VISEC scheitert
            return self.antwort(500, b'{}')
        r = {'requestId': UUID, 'serverDateUtc': '2026-11-24T12:00:00Z', 'serverVersion': '2026.11.23', 'observaciones': None, 'error': None, 'dte': None}
        if nummer in DATEN:
            r.update(DATEN[nummer])
        else:
            r['error'] = {'code': 'NOT_FOUND', 'description': 'No se encontró el DTE.'}
        self.antwort(200, json.dumps(r).encode(), 'text/plain')   # die echte Schnittstelle liefert auch text/plain


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Visec)
threading.Thread(target=srv.serve_forever, daemon=True).start()

A, I, L = nutzer_anlegen()
kriterium = lambda s: next((k for k in s.get('profil', {}).get('kriterien', []) if k['id'] == 'visec'), None)

# ---------- DTE-Nummern am Container ----------
ar = container_anlegen(I, 'VISEC-1', land='AR', visecDte=' 100 200 300\n100200301\n\n100200300 \n')
check('DTE-Nummern gespeichert: ohne Leerzeichen, ohne Doppelte, in der Reihenfolge der Eingabe', ar.get('visecDte') == ['100200300', '100200301'], ar.get('visecDte'))
py = container_anlegen(I, 'VISEC-2', land='PY')
check('Container ohne DTE-Nummern: leer, kein Kriterium „Tiere laut VISEC“ im Profil', py.get('visecDte') == [] and kriterium(py) is None and py.get('visec') == [], py.get('visecDte'))
k = kriterium(ar)
check('Vor der Abfrage: Kriterium offen „noch nicht abgefragt“ mit beiden DTE', k and k['stand'] == 'offen' and 'Noch nicht bei VISEC abgefragt' in k['text'] and k['betriebe'] == ['DTE 100200300', 'DTE 100200301']
      and [(x['nummer'], x['stand'], x['t'], x['tiere']) for x in ar['visec']] == [('100200300', 'nie', '', 0), ('100200301', 'nie', '', 0)], (k, ar.get('visec')))
for falsch, was in (('100 200\n<script>', 'Zeichen'), ('\n'.join(str(1000 + i) for i in range(31)), 'zu viele'), (['100200300', 5], 'Liste mit Zahl')):
    st, r = I.call('containerimport_eudr_sendung_save', {**ar, 'visecDte': falsch})
    check(f'Ungültige DTE-Nummern ({was}): 422, nichts gespeichert', st == 422 and 'DTE' in r.get('error', '') and container(stand(I), 'VISEC-1')['visecDte'] == ['100200300', '100200301'], (st, r.get('error')))
ohne = {k: v for k, v in container(stand(I), 'VISEC-1').items() if k != 'visecDte'}
st, r = I.call('containerimport_eudr_sendung_save', {**ohne, 'notiz': 'ohne Feld'})
check('Speichern ohne das Feld (ältere Seite): die Nummern bleiben', st == 200 and container(r, 'VISEC-1')['visecDte'] == ['100200300', '100200301'], (st, r.get('error')))
ar = container(r, 'VISEC-1')

# ---------- Rechte ----------
check('Stand: Abfrage eingerichtet – angeboten nur, wer bearbeiten darf', stand(I)['rechte'].get('visec') is True and stand(L)['rechte'].get('visec') is False)
check('nur ansehen: 403', L.call('containerimport_visec_abfragen', {'id': ar['id']})[0] == 403)
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_visec_abfragen', {'id': ar['id']})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_visec_abfragen')[0] == 405)
check('unbekannter Container 404, Container ohne DTE-Nummern 422', [I.call('containerimport_visec_abfragen', {'id': x})[0] for x in ('gibt-es-nicht', py['id'])] == [404, 422])
check('bis hierher ging nichts an VISEC', SPIEL['anfragen'] == [], SPIEL['anfragen'])

# ---------- Abfrage ----------
st, r, roh = I.call('containerimport_visec_abfragen', {'id': ar['id']}, raw=True)
s = container(r, 'VISEC-1')
check('Abfrage: 200, alle DTE abgefragt, neuer Stand dabei', st == 200 and r.get('offen') == [] and s.get('id') == ar['id'], (st, r.get('error')))
check('An VISEC geht je DTE nur die Nummer, mit dem Token in der Kopfzeile',
      [(a['pfad'], a['token'], a['inhalt']) for a in SPIEL['anfragen']] == [('/api/Visec/dte', 'Bearer ' + TOKEN, {'numero': n}) for n in ('100200300', '100200301')], SPIEL['anfragen'])
check('Der Token steht in keiner Antwort', TOKEN not in roh and TOKEN not in json.dumps(stand(I)) and TOKEN not in json.dumps(stand(L)))
v1, v2 = s['visec']
check('Ergebnis je DTE verdichtet: Tropa, Daten, Stand, Zahlen je Stand, Anfrage, Bearbeiter, Einstufung „ok“ – ohne die ganze Liste der Tiere',
      v1['tropa'] == 'T-0042' and v1['fechaDte'] == '2026-10-01' and v1['fechaArribo'] == '2026-10-01' and v1['estado'] == 'CERRADO' and v1['stand'] == 'ok'
      and v1['tiere'] == 3 and v1['zahlen'] == {'VALIDA': 3, 'INVALIDA': 0, 'offen': 0} and v1['registriert'] is True and v1['anfrage'] == UUID and v1['von'] == 'Ina Import'
      and v1['t'] and 'caravanas' not in v1 and 'AR-T0001' not in json.dumps(stand(I)), v1)
check('Offenes Tier mit Nummer und Stand auf Deutsch, Einstufung „offen“', v2['stand'] == 'offen' and v2['zahlen'] == {'VALIDA': 2, 'INVALIDA': 0, 'offen': 1} and v2['offen'] == [['AR-U0003', 'in Validierung']] and v2['ungueltig'] == [], v2)
k = kriterium(s)
check('Kriterium offen: ein Tier noch nicht abschließend geprüft, betroffen ist die zweite DTE',
      k['stand'] == 'offen' and '1 Tier ist bei VISEC noch nicht abschließend geprüft' in k['text'] and k['betriebe'] == ['DTE 100200301'], k)
check('Protokoll: Abfrage mit den Nummern vermerkt', 'DTE-Nummern des Containers „VISEC-1“ bei VISEC abgefragt (100200300, 100200301)' in json.dumps(A.call('log')[1], ensure_ascii=False))
check('Lea sieht die Ergebnisse und das Kriterium', container(stand(L), 'VISEC-1')['visec'][1]['zahlen'] == v2['zahlen'] and kriterium(container(stand(L), 'VISEC-1'))['stand'] == 'offen')

DATEN['100200301'] = {'dte': dte('100200301', tiere('VALIDA', 'VALIDA', 'VALIDA', vorsilbe='AR-U'))}
s = container(I.call('containerimport_visec_abfragen', {'id': ar['id']})[1], 'VISEC-1')
k = kriterium(s)
check('Erneut abgefragt, alle gültig: Kriterium in Ordnung mit Zahl der DTE und Tiere, Hinweis „zertifiziert nicht“',
      k['stand'] == 'ok' and k['text'].startswith('2 DTE mit 6 Tieren, alle gültig laut VISEC (Abfrage vom ') and 'zertifiziert nicht' in k['text'], k)

# ---------- Fehler von VISEC: nichts wird überschrieben ----------
vorher = container(stand(I), 'VISEC-1')['visec']
for modus, status, text in (('token', 503, 'Zugangstoken ab'), ('kaputt', 502, 'HTTP 500'), ('fremd', 502, 'unerwartet'), ('abbruch', 502, 'nicht erreichbar')):
    SPIEL['modus'] = modus
    st, r, roh = I.call('containerimport_visec_abfragen', {'id': ar['id']}, raw=True)
    check(f'VISEC {modus}: {status} mit verständlicher Meldung, Ergebnisse unverändert, kein Token in der Antwort',
          st == status and text in r.get('error', '') and TOKEN not in roh and container(stand(I), 'VISEC-1')['visec'] == vorher, (st, r.get('error')))
SPIEL['modus'] = 'ok'

DATEN['100200300'] = {'dte': dte('100200300', tiere('VALIDA', 'VALIDA', 'VALIDA'), tropa='T-0043')}
st, r = I.call('containerimport_eudr_sendung_save', {**container(stand(I), 'VISEC-1'), 'visecDte': '100200300\n777000777\n100200301'})
vorher = {x['nummer']: x for x in container(r, 'VISEC-1')['visec']}
st, r = I.call('containerimport_visec_abfragen', {'id': ar['id']})
nach = {x['nummer']: x for x in container(r, 'VISEC-1')['visec']}
check('VISEC scheitert an der zweiten Nummer: die erste wird abgelegt, der Rest bleibt beim alten Stand und steht in „offen“ mit dem Grund',
      st == 200 and r.get('offen') == ['777000777', '100200301'] and 'HTTP 500' in r.get('hinweis', '') and nach['100200300']['tropa'] == 'T-0043'
      and nach['100200301'] == vorher['100200301'] and nach['777000777']['stand'] == 'nie', (st, r.get('offen'), r.get('hinweis')))

# ---------- unbekannte DTE, noch nicht erfasste DTE, ungültige Tiere, Abschluss ----------
DATEN['555000111'] = {'dte': dte('555000111', tiere(*(['INVALIDA'] * 150), 'VALIDA', vorsilbe='AR-X'), dte_id=-555000111, tropa='<img src=x onerror=alert(1)>\u0007'),
                      'observaciones': 'Sin permiso de lectura en SENASA.'}
st, r = I.call('containerimport_eudr_sendung_save', {**container(stand(I), 'VISEC-1'), 'visecDte': '100200300\n100200301\n999999999\n555000111'})
s = container(I.call('containerimport_visec_abfragen', {'id': ar['id']})[1], 'VISEC-1')
v = {x['nummer']: x for x in s['visec']}
check('Unbekannte DTE: Fehlercode und Text von VISEC abgelegt, Einstufung „fehler“', v['999999999']['fehler'] == 'NOT_FOUND' and v['999999999']['fehlerText'] == 'No se encontró el DTE.' and v['999999999']['tiere'] == 0 and v['999999999']['stand'] == 'fehler', v['999999999'])
x = v['555000111']
check('Von VISEC noch nicht erfasster DTE (Nummer negativ): „nicht registriert“, Hinweis von VISEC, Steuerzeichen entfernt',
      x['registriert'] is False and x['observaciones'] == 'Sin permiso de lectura en SENASA.' and x['tropa'] == '<img src=x onerror=alert(1)>', x)
check('Ungültige Tiere: Zahl vollständig, Nummern höchstens 100, Einstufung „kritisch“', x['zahlen'] == {'VALIDA': 1, 'INVALIDA': 150, 'offen': 0} and len(x['ungueltig']) == 100 and x['ungueltig'][0] == 'AR-X0001' and x['stand'] == 'kritisch', x['zahlen'])
k = kriterium(s)
check('Kriterium kritisch: 150 ungültige Tiere, betroffen ist nur diese DTE (vor „unbekannt“)', k['stand'] == 'kritisch' and 'VISEC weist 150 Tiere als ungültig aus' in k['text'] and k['betriebe'] == ['DTE 555000111'], k)

st, r = I.call('containerimport_eudr_sendung_save', {**container(stand(I), 'VISEC-1'), 'visecDte': '100200300\n100200301\n999999999'})
s = container(r, 'VISEC-1')
k = kriterium(s)
check('Ohne die DTE mit ungültigen Tieren: offen wegen der unbekannten DTE (gespeicherte Ergebnisse gelten weiter)', k['stand'] == 'offen' and 'kennt einen DTE nicht' in k['text'] and k['betriebe'] == ['DTE 999999999'], k)
st, r = I.call('containerimport_eudr_sendung_abschluss', {'id': s['id'], 'rev': s['rev'], 'ergebnis': 'nicht_vernachlaessigbar', 'begruendung': 'DTE 999999999 klären'})
s = container(r, 'VISEC-1')
check('Abschluss hält das Kriterium im Profil fest', st == 200 and s['abschluss'] and kriterium(s) == k, (st, r.get('error'), kriterium(s)))
anfragen = len(SPIEL['anfragen'])
st, r = I.call('containerimport_visec_abfragen', {'id': ar['id']})
check('Nach dem Abschluss keine Abfrage mehr (409), nichts ging hinaus', st == 409 and 'abgeschlossen' in r.get('error', '') and len(SPIEL['anfragen']) == anfragen, (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {**s, 'visecDte': '123123123', 'notiz': 'nach dem Abschluss'})
check('Nach dem Abschluss bleiben die DTE-Nummern, wie sie waren', st == 200 and container(r, 'VISEC-1')['visecDte'] == ['100200300', '100200301', '999999999'], (st, r.get('error')))

# ---------- Oberfläche ----------
ui = container_anlegen(I, 'VISEC-UI', land='AR')
DATEN['300400500'] = {'dte': dte('300400500', tiere('VALIDA', 'INVALIDA', 'EN_ESPERA', vorsilbe='AR-W'), tropa='<b>T-9</b>')}
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []
    p = seite(br, 'ina', errs, fremd)
    p.click(f'[data-sendung="{py["id"]}"]'); p.wait_for_selector('#dlg-sendung[open]')
    check('Oberfläche: Container aus Paraguay ohne Nummern – Bereich VISEC verborgen', p.is_hidden('#sendung-visec'))
    p.select_option('#sendung-inhalt [name=land]', 'AR')
    check('Herkunftsland im Fenster auf Argentinien: Bereich erscheint (Eingabe, Knopf)', p.is_visible('#sendung-visec textarea[name=visecDte]') and p.is_visible('#visec-abfragen'))
    p.click('#sendung-inhalt .ci-zu'); p.wait_for_function("!document.querySelector('#dlg-sendung').open")   # nicht gespeichert
    p.click(f'[data-sendung="{ui["id"]}"]'); p.wait_for_function(f"document.querySelector('#sendung-inhalt').dataset.id === '{ui['id']}'")
    check('Container aus Argentinien: Bereich mit leerer Eingabe, noch keine Ergebnisse', p.is_visible('#sendung-visec') and p.input_value('[name=visecDte]') == '' and p.locator('.ci-visec-dte').count() == 0)
    p.fill('[name=visecDte]', '300 400 500')
    p.click('#visec-abfragen'); p.wait_for_function("document.querySelector('#sendung-visec').innerText.includes('Abgefragt am')")   # vorher steht die DTE schon als „nicht abgefragt“ da
    text = p.inner_text('#sendung-visec')
    check('Speichern und abfragen in einem Schritt: Nummer gespeichert, DTE mit Marke, Zahlen, ungültigen und offenen Tieren',
          container(stand(I), 'VISEC-UI')['visecDte'] == ['300400500'] and 'DTE 300400500' in text and '1 ungültig' in text and '3 Tiere: 1 gültig · 1 ungültig · 1 offen' in text
          and 'Abgefragt am' in text and 'Ina Import' in text, text)
    check('Fremder Text maskiert (Tropa als Text, kein Element)', 'Tropa <b>T-9</b>' in text and p.locator('#sendung-visec b').count() == 0, text)
    p.click('.ci-visec-tiere summary >> nth=1')
    check('Offene Tiere mit Stand auf Deutsch', 'AR-W0003 (wartet auf den Erzeuger)' in p.inner_text('#sendung-visec'), p.inner_text('#sendung-visec'))
    check('Profil im Fenster neu: Kriterium „Tiere laut VISEC“ kritisch', 'Tiere laut VISEC' in p.inner_text('#sendung-inhalt') and 'VISEC weist 1 Tier als ungültig aus' in p.inner_text('#sendung-inhalt'))
    p.locator('#sendung-visec').scroll_into_view_if_needed(); shot(p, os.path.join(SH, 'containerimport-visec-1280.png'))
    SPIEL['modus'] = 'token'
    p.click('#visec-abfragen'); p.wait_for_selector('#ci-toast.zeigen.fehler')
    check('Token abgelehnt: Meldung, Ergebnisse bleiben stehen', 'Zugangstoken' in p.inner_text('#ci-toast') and p.locator('.ci-visec-dte').count() == 1, p.inner_text('#ci-toast'))
    SPIEL['modus'] = 'ok'
    p.context.close()

    m = seite(br, 'lea', errs, fremd, {'width': 390, 'height': 844}, 'dark')
    m.click(f'[data-sendung="{ui["id"]}"]'); m.wait_for_selector('#dlg-sendung[open] .ci-visec-dte')
    check('Nur ansehen: Ergebnisse ohne Eingabe und ohne Knopf', m.locator('[name=visecDte]').count() == 0 and m.locator('#visec-abfragen').count() == 0 and 'DTE 300400500' in m.inner_text('#sendung-visec'))
    m.locator('#sendung-visec').scroll_into_view_if_needed(); shot(m, os.path.join(SH, 'containerimport-visec-390-dunkel.png'))
    check('390 px: kein waagerechtes Scrollen im Fenster', m.evaluate("(() => { const d = document.querySelector('#sendung-visec'); return d.scrollWidth <= d.clientWidth + 1; })()"))
    m.context.close()
    br.close()
check('Keine JavaScript-Fehler', not errs, errs)
check('Die Seite rief nur Kartendienste ab, nie VISEC', not [u for u in fremd if 'visec' in u.lower()], fremd)
ende()
