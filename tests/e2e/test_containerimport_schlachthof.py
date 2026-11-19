"""Container-Import: Schlachthöfe als Stammdaten unter dem Lieferanten (Aktion containerimport_schlachthof_save,
app/api/module/containerimport/schlachthoefe.php, Oberfläche app/module/containerimport/schlachthoefe.js).
Geprüft: Rechte (ansehen mit „EUDR ansehen“, speichern nur mit „EUDR bearbeiten“, CSRF, kein GET); anlegen mit Lieferant aus
den Stammdaten oder als freier Text; Pflichtfelder; Name je Lieferant eindeutig; Revision (409); archivieren statt löschen;
am Container nur ein Schlachthof des eigenen Lieferanten, kein archivierter neu; Name am Container mitgespeichert, Umbenennung
geht an offene Container, nicht an abgeschlossene (GR-106); nach dem Abschluss einmal nachtragen; ältere Container ohne das
Feld bleiben lesbar (GR-006); Felder einer späteren Version bleiben erhalten; Protokoll.
Oberfläche: Ansicht „Schlachthöfe“ mit Suche, Fenster zum Anlegen, Auswahl im Fenster „Container“ folgt dem Lieferanten,
Leser ohne Knöpfe, Handy 390 px. Alle Namen sind erfunden (GR-007)."""
import json
import os
import re
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH, shot, storage_raw, storage_write, _json

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i and not c else ''))


# ---------- Nutzer und Stammdaten ----------
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
USERS = {'ina': ('Ina Import', 'editor', 'Editor-Zugang-88', ['containerimport.eudr_sehen', 'containerimport.eudr_bearbeiten']),
         'lea': ('Lea Leser', 'viewer', 'Leser-Zugang-55', ['containerimport.eudr_sehen'])}
for user, (name, role, pw, grant) in USERS.items():
    A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    nr = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == user)
    A.call('user_save', {'id': nr, 'name': name, 'role': role, 'active': True, 'grant': grant, 'deny': []})
A.call('lieferanten_save', {'rev': 0, 'groups': [{'nr': '70012', 'name': 'Frigorifico Beispiel S.A.', 'kurz': 'FRIGOBSP'}, {'nr': '70020', 'name': 'Carnes del Sur Ltda.', 'kurz': 'CARNESUR'}], 'quelle': 'Test'})


def login(user):
    c = Client('198.51.100.' + str(10 + list(USERS).index(user)))
    code, r = c.call('login', {'username': user, 'password': USERS[user][2]})
    assert code == 200, (user, code, r)
    return c


I, L = login('ina'), login('lea')
HOF = {'id': '', 'rev': 0, 'name': 'Werk Asunción', 'lieferantNr': '70012', 'land': 'PY', 'ort': 'Asunción', 'zulassung': 'PY-38', 'notiz': ''}
CONTAINER = {'id': '', 'rev': 0, 'partie': 'P-270001', 'lieferantNr': '70012', 'land': 'PY'}


def hoefe(r):
    return {h['name']: h for h in r.get('schlachthoefe', [])}


def container(r, partie):
    return next((s for s in r.get('sendungen', []) if s['partie'] == partie), {})


def hof_speichern(daten):
    """Schlachthof speichern → (Status, Antwort, der gespeicherte Eintrag)."""
    st, r = I.call('containerimport_schlachthof_save', daten)
    return st, r, next((h for h in r.get('schlachthoefe', []) if h['id'] == r.get('id')), {})


def abschliessen(c, **mehr):
    """Bewertung eines Containers abschließen (oder mit oeffnen=True, grund=… wieder öffnen) → (Status, Antwort)."""
    return I.call('containerimport_eudr_sendung_abschluss', {'id': c['id'], 'rev': c['rev'], 'ergebnis': 'nicht_vernachlaessigbar', 'begruendung': 'Unterlagen fehlen noch – Test der Schlachthöfe.', **mehr})


# ---------- Rechte ----------
check('Stand: zu Beginn kein Schlachthof – auch wer nur ansehen darf, bekommt die Liste', I.call('containerimport_start')[1].get('schlachthoefe') == [] and L.call('containerimport_start')[1].get('schlachthoefe') == [])
check('nur ansehen: Speichern 403', L.call('containerimport_schlachthof_save', HOF)[0] == 403)
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_schlachthof_save', HOF)[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_schlachthof_save')[0] == 405)

# ---------- Anlegen und ändern ----------
st, r = I.call('containerimport_schlachthof_save', {**HOF, 'lieferant': 'wird ersetzt'})
asu = hoefe(r).get('Werk Asunción', {})
check('Schlachthof angelegt: Lieferant aus den Stammdaten (Name von dort), Land, Ort, Zulassungsnummer',
      st == 200 and [asu.get(k) for k in ('lieferantNr', 'lieferant', 'land', 'ort', 'zulassung', 'aktiv', 'rev')] == ['70012', 'Frigorifico Beispiel S.A.', 'PY', 'Asunción', 'PY-38', True, 1], (st, r.get('error'), asu))
check('Pflichtfelder: ohne Name 422, ohne Lieferant 422, unbekannter Lieferant der Stammdaten 422, Land ungültig 422',
      [I.call('containerimport_schlachthof_save', {**HOF, **x})[0] for x in ({'name': ''}, {'lieferantNr': '', 'lieferant': ''}, {'name': 'X', 'lieferantNr': '99999'}, {'name': 'X', 'land': 'Paraguay'})] == [422] * 4)
st, r = I.call('containerimport_schlachthof_save', {**HOF, 'name': 'werk asunción'})
check('Name ist je Lieferant eindeutig, auch bei anderer Schreibweise (422)', st == 422 and 'gibt es bei dem Lieferanten schon' in r.get('error', ''), (st, r))
st, r = I.call('containerimport_schlachthof_save', {**HOF, 'lieferantNr': '70020', 'zulassung': 'UY-2'})
sur = next((h for h in r.get('schlachthoefe', []) if h['lieferantNr'] == '70020'), {})
check('derselbe Name bei einem anderen Lieferanten ist erlaubt', st == 200 and sur.get('lieferant') == 'Carnes del Sur Ltda.', (st, r.get('error')))
st, r = I.call('containerimport_schlachthof_save', {**HOF, 'name': 'Werk Frei', 'lieferantNr': '', 'lieferant': 'Lieferant ohne Stammdaten', 'zulassung': ''})
frei = hoefe(r).get('Werk Frei', {})
check('Lieferant noch nicht in den Stammdaten: freier Text ohne Verknüpfung', st == 200 and frei.get('lieferantNr') == '' and frei.get('lieferant') == 'Lieferant ohne Stammdaten', (st, r.get('error')))
check('veralteter Stand: 409, unbekannte Kennung: 404', I.call('containerimport_schlachthof_save', {**asu, 'rev': 0})[0] == 409 and I.call('containerimport_schlachthof_save', {**HOF, 'id': 'hgibtesnicht'})[0] == 404)
st, r = I.call('containerimport_schlachthof_save', {**HOF, 'name': 'Werk Concepción', 'ort': 'Concepción', 'zulassung': 'PY-17'})
con = hoefe(r).get('Werk Concepción', {})
check('zweiter Schlachthof desselben Lieferanten', st == 200 and con.get('id') and con['id'] != asu['id'], (st, r.get('error')))

# ---------- Schlachthof am Container ----------
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'schlachthof': asu['id']})
c1 = container(r, 'P-270001')
check('Container mit Schlachthof seines Lieferanten: Kennung und Name stehen am Container', st == 200 and c1.get('schlachthof') == asu['id'] and c1.get('schlachthofName') == 'Werk Asunción', (st, r.get('error'), c1))
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270002', 'schlachthof': sur['id']})
check('Schlachthof eines anderen Lieferanten: 422 mit verständlicher Meldung', st == 422 and 'anderen Lieferanten' in r.get('error', ''), (st, r))
check('unbekannter Schlachthof: 422', I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270002', 'schlachthof': 'hgibtesnicht'})[0] == 422)
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270002', 'lieferantNr': '', 'lieferant': 'lieferant OHNE stammdaten', 'schlachthof': frei['id']})
check('Lieferant als freier Text: sein Schlachthof passt über den Namen, ohne Rücksicht auf Groß- und Kleinschreibung', st == 200 and container(r, 'P-270002').get('schlachthofName') == 'Werk Frei', (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270003'})
c3 = container(r, 'P-270003')
check('Container ohne Schlachthof bleibt möglich', st == 200 and c3.get('schlachthof') == '' and c3.get('schlachthofName') == '', (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {k: v for k, v in c1.items() if k != 'schlachthof'} | {'akte': 'AK-1'})
c1 = container(r, 'P-270001')
check('älterer Stand der Seite ohne das Feld: der gespeicherte Schlachthof bleibt', st == 200 and c1.get('schlachthof') == asu['id'] and c1.get('akte') == 'AK-1', (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {**c1, 'lieferantNr': '70020'})
check('Lieferant des Containers gewechselt, Schlachthof nicht: 422 statt stiller Übernahme', st == 422 and 'anderen Lieferanten' in r.get('error', ''), (st, r))
st, r = I.call('containerimport_eudr_sendung_save', {**c1, 'lieferantNr': '70020', 'schlachthof': ''})
c1 = container(r, 'P-270001')
check('Lieferant gewechselt und Schlachthof geleert: gespeichert', st == 200 and c1.get('schlachthof') == '' and c1.get('lieferant') == 'Carnes del Sur Ltda.', (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {**c1, 'lieferantNr': '70012', 'schlachthof': asu['id']})
c1 = container(r, 'P-270001')

# ---------- Archivieren ----------
st, r = I.call('containerimport_schlachthof_save', {**con, 'aktiv': False})
con = hoefe(r).get('Werk Concepción', {})
check('Schlachthof archiviert, nicht gelöscht', st == 200 and con.get('aktiv') is False and len(r['schlachthoefe']) == 4, (st, r.get('error')))
st, r = I.call('containerimport_eudr_sendung_save', {**c3, 'schlachthof': con['id']})
check('archivierter Schlachthof lässt sich nicht neu wählen (422)', st == 422 and 'archiviert' in r.get('error', ''), (st, r))
st, r = I.call('containerimport_schlachthof_save', {**asu, 'aktiv': False})
asu = next(h for h in r['schlachthoefe'] if h['id'] == asu['id'])   # der Name allein ist nicht eindeutig: Werk Asunción gibt es bei zwei Lieferanten
st, r = I.call('containerimport_eudr_sendung_save', {**c1, 'akte': 'AK-2'})
c1 = container(r, 'P-270001')
check('archivierter Schlachthof bleibt an dem Container, an dem er schon steht', st == 200 and c1.get('schlachthof') == asu['id'] and c1.get('akte') == 'AK-2', (st, r.get('error')))
st, r = I.call('containerimport_schlachthof_save', {**asu, 'aktiv': True})
asu = next(h for h in r['schlachthoefe'] if h['id'] == asu['id'])

# ---------- Umbenennen: offene Container folgen, abgeschlossene nicht (GR-106) ----------
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270004', 'schlachthof': asu['id']})
c4 = container(r, 'P-270004')
st, r = abschliessen(c4)
check('Bewertung eines Containers abgeschlossen (Vorbereitung)', st == 200 and container(r, 'P-270004').get('abschluss'), (st, r.get('error')))
st, r = I.call('containerimport_schlachthof_save', {**asu, 'name': 'Werk Asunción Norte'})
asu = hoefe(r).get('Werk Asunción Norte', {})
check('Schlachthof umbenannt: der offene Container zeigt den neuen Namen, der abgeschlossene den von damals',
      st == 200 and container(r, 'P-270001').get('schlachthofName') == 'Werk Asunción Norte' and container(r, 'P-270004').get('schlachthofName') == 'Werk Asunción', (st, r.get('error')))
c4 = container(r, 'P-270004')
st, r = I.call('containerimport_eudr_sendung_save', {**c4, 'schlachthof': '', 'stand': 'unterwegs'})
c4 = container(r, 'P-270004')
check('nach dem Abschluss bleibt der Schlachthof, wie er abgeschlossen wurde (der Stand lässt sich weiter pflegen)', st == 200 and c4.get('schlachthof') == asu['id'] and c4.get('schlachthofName') == 'Werk Asunción' and c4.get('stand') == 'unterwegs', (st, r.get('error')))

# Wieder öffnen: ab dann wieder der aktuelle Name; Lieferant eines Schlachthofs mit Containern bleibt
st, r, probe = hof_speichern({**HOF, 'name': 'Werk Probe', 'lieferantNr': '70020', 'zulassung': ''})
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270006', 'lieferantNr': '70020', 'schlachthof': probe['id']})
st, r = abschliessen(container(r, 'P-270006'))
st, r, probe = hof_speichern({**probe, 'name': 'Werk Probe Neu'})
c6 = container(r, 'P-270006')
st, r = abschliessen(c6, oeffnen=True, grund='Schlachthof wurde umbenannt')
check('Bewertung wieder geöffnet: der Container zeigt wieder den aktuellen Namen des Schlachthofs', c6.get('schlachthofName') == 'Werk Probe' and st == 200 and container(r, 'P-270006').get('schlachthofName') == 'Werk Probe Neu', (st, r.get('error')))
st, r, _ = hof_speichern({**probe, 'lieferantNr': '70012'})
check('Lieferant eines Schlachthofs wechseln, an dem schon Container stehen: 422', st == 422 and 'Container zugeordnet' in r.get('error', ''), (st, r))
st, r, frei = hof_speichern({**frei, 'lieferant': 'Lieferant ohne Stammdaten GmbH'})
c2 = container(r, 'P-270002')
check('Lieferant als freier Text am Schlachthof berichtigt: sein offener Container bekommt den neuen Namen mit und bleibt speicherbar',
      st == 200 and c2.get('lieferant') == 'Lieferant ohne Stammdaten GmbH' and I.call('containerimport_eudr_sendung_save', {**c2, 'stand': 'unterwegs'})[0] == 200, (st, r.get('error'), c2.get('lieferant')))
st, r, frei = hof_speichern({**frei, 'lieferant': 'Lieferant ohne Stammdaten'})
check('… und wieder zurück', st == 200 and container(r, 'P-270002').get('lieferant') == 'Lieferant ohne Stammdaten', (st, r.get('error')))
I.call('containerimport_eudr_sendung_save', {**container(r, 'P-270006'), 'aktiv': False})   # die Oberfläche unten arbeitet ohne diesen Container und seinen Schlachthof
hof_speichern({**probe, 'aktiv': False})

# ---------- Ältere Container ohne das Feld (GR-006), Nachtragen nach dem Abschluss, Felder einer späteren Version ----------
st, r = I.call('containerimport_eudr_sendung_save', {**CONTAINER, 'partie': 'P-270005'})
c5 = container(r, 'P-270005')
abschliessen(c5)
doc = _json(storage_raw('containerimport-eudr-sendungen'))
for s in doc['liste']:
    if s['partie'] in ('P-270003', 'P-270005'):
        del s['schlachthof'], s['schlachthofName']
storage_write('containerimport-eudr-sendungen', doc)
hd = _json(storage_raw('containerimport-schlachthoefe'))
next(h for h in hd['liste'] if h['id'] == frei['id'])['spaeter'] = {'farmer': ['x1']}   # ein Feld, das erst eine spätere Version kennt
storage_write('containerimport-schlachthoefe', hd)
r = I.call('containerimport_start')[1]
c3, c5 = container(r, 'P-270003'), container(r, 'P-270005')
check('Container aus der Zeit vor den Schlachthöfen: lesbar, ohne Schlachthof', c3.get('schlachthof') == '' and c5.get('schlachthofName') == '' and c5.get('abschluss'), (c3, c5))
st, r = I.call('containerimport_eudr_sendung_save', {**c5, 'schlachthof': asu['id']})
c5 = container(r, 'P-270005')
st2, r = I.call('containerimport_eudr_sendung_save', {**c5, 'schlachthof': frei['id']})
check('abgeschlossener Container ohne Schlachthof: nachtragen geht einmal, die Bewertung bleibt abgeschlossen',
      st == 200 and st2 == 200 and container(r, 'P-270005').get('schlachthofName') == 'Werk Asunción Norte' and container(r, 'P-270005').get('abschluss'), (st, st2, r.get('error')))
st, r = I.call('containerimport_schlachthof_save', {**hoefe(r)['Werk Frei'], 'ort': 'Encarnación'})
check('Schlachthof speichern erhält Felder einer späteren Version', st == 200 and next(h for h in _json(storage_raw('containerimport-schlachthoefe'))['liste'] if h['id'] == frei['id']).get('spaeter') == {'farmer': ['x1']}, (st, r.get('error')))
verlauf = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll nennt das Speichern der Schlachthöfe', 'Schlachthof „Werk Asunción Norte“ gespeichert' in verlauf and 'Schlachthof „Werk Frei“ gespeichert' in verlauf, verlauf[:400])

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        ctx = br.new_context(viewport=vp or {'width': 1280, 'height': 900}, color_scheme=schema)
        ctx.route(re.compile(r'^https?://(?!127\.0\.0\.1[:/])'), lambda route: (fremd.append(route.request.url), route.abort()))   # Tests rufen nie fremde Server ab
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', USERS[user][2]); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.goto(B + '/module/containerimport/'); pg.wait_for_selector('#ci-app:not([hidden])')
        return pg

    p = seite('ina')
    check('Liste der Container nennt den Schlachthof', 'Werk Asunción Norte' in p.inner_text('#ci-sendungen tr:has-text("P-270001")'), p.inner_text('#ci-sendungen'))
    p.click('[data-sicht="schlachthoefe"]'); p.wait_for_selector('#ci-schlachthoefe')
    zeilen = p.eval_on_selector_all('#ci-schlachthoefe tbody tr', 'rs => rs.map(r => r.cells[0].querySelector(".ci-name").textContent + "|" + r.cells[1].querySelector("span").textContent + "|" + r.cells[3].textContent)')
    check('Ansicht „Schlachthöfe“: aktive Schlachthöfe nach Lieferant und Name, mit Zahl der Container; der archivierte fehlt',
          zeilen == ['Werk Asunción|Carnes del Sur Ltda.|0', 'Werk Asunción Norte|Frigorifico Beispiel S.A.|3', 'Werk Frei|Lieferant ohne Stammdaten|1'] and p.inner_text('[data-sicht="schlachthoefe"] b') == '3', zeilen)
    shot(p, os.path.join(SH, 'containerimport-schlachthoefe-1280.png'))
    p.fill('#ci-suche', 'py-38'); p.wait_for_function("document.querySelectorAll('#ci-schlachthoefe tbody tr').length === 1")
    check('Suche findet über die Zulassungsnummer und behält den Fokus', 'Werk Asunción Norte' in p.inner_text('#ci-schlachthoefe') and p.evaluate("document.activeElement.id") == 'ci-suche')
    p.fill('#ci-suche', 'gibt es nicht'); p.wait_for_selector('#ci-inhalt .ci-leer')
    check('Suche ohne Treffer sagt das', p.inner_text('#ci-inhalt .ci-leer') == 'Kein Schlachthof passt zur Suche.')
    p.fill('#ci-suche', ''); p.wait_for_selector('#ci-schlachthoefe')
    p.check('#ci-archiv'); p.wait_for_function("document.querySelectorAll('#ci-schlachthoefe tbody tr').length === 5")
    check('„Archivierte anzeigen“ zeigt auch die archivierten Schlachthöfe', 'Werk Concepción' in p.inner_text('#ci-schlachthoefe') and 'Werk Probe Neu' in p.inner_text('#ci-schlachthoefe'))
    p.uncheck('#ci-archiv'); p.wait_for_function("document.querySelectorAll('#ci-schlachthoefe tbody tr').length === 3")

    # Neuer Schlachthof aus dem Fenster
    p.click('#ci-schlachthof-neu'); p.wait_for_selector('#dlg-schlachthof[open]')
    check('Fenster „Neuer Schlachthof“: Lieferanten der Stammdaten als Vorschläge', p.inner_text('#schlachthof-titel') == 'Neuer Schlachthof'
          and p.eval_on_selector_all('#dlg-schlachthof datalist option', 'os => os.map(o => o.value)') == ['Carnes del Sur Ltda. (70020)', 'Frigorifico Beispiel S.A. (70012)'])
    p.fill('#dlg-schlachthof [name=name]', 'Werk <b>Sur</b>'); p.fill('#dlg-schlachthof [name=lieferant]', 'carnes del sur ltda. (70020)'); p.select_option('#dlg-schlachthof [name=land]', 'UY')
    p.fill('#dlg-schlachthof [name=ort]', 'Montevideo'); p.fill('#dlg-schlachthof [name=zulassung]', 'UY-7')
    shot(p, os.path.join(SH, 'containerimport-schlachthof-fenster-1280.png'))
    p.click('#dlg-schlachthof button[type=submit]'); p.wait_for_function("!document.querySelector('#dlg-schlachthof').open && document.querySelectorAll('#ci-schlachthoefe tbody tr').length === 4")
    neu = next(h for h in I.call('containerimport_start')[1]['schlachthoefe'] if h['zulassung'] == 'UY-7')
    check('Schlachthof aus dem Fenster gespeichert: mit den Stammdaten verknüpft (Vorschlag zählt ohne Rücksicht auf Groß- und Kleinschreibung), Name als Text angezeigt',
          [neu[k] for k in ('name', 'lieferantNr', 'lieferant', 'land', 'ort')] == ['Werk <b>Sur</b>', '70020', 'Carnes del Sur Ltda.', 'UY', 'Montevideo']
          and 'Werk <b>Sur</b>' in p.inner_text('#ci-schlachthoefe') and p.locator('#ci-schlachthoefe b').count() == 0, neu)
    p.focus(f'[data-schlachthof="{asu["id"]}"]'); p.keyboard.press('Enter'); p.wait_for_selector('#dlg-schlachthof[open]')
    p.keyboard.up('Enter')
    check('Zeile mit der Eingabetaste geöffnet: das Fenster bleibt offen (derselbe Tastendruck schließt es nicht wieder)', p.evaluate("document.querySelector('#dlg-schlachthof').open"))
    check('Fenster eines Schlachthofs nennt seine Container', p.inner_text('#schlachthof-titel') == 'Werk Asunción Norte' and all(x in p.inner_text('#dlg-schlachthof') for x in ('P-270001', 'P-270004', 'P-270005')), p.inner_text('#dlg-schlachthof'))
    p.fill('#dlg-schlachthof [name=name]', 'Werk Asunción'); p.fill('#dlg-schlachthof [name=lieferant]', 'Carnes del Sur Ltda. (70020)'); p.click('#dlg-schlachthof button[type=submit]')
    p.wait_for_selector('#ci-toast.zeigen.fehler')
    check('Fehler des Servers erscheint als Meldung, das Fenster bleibt offen', 'gibt es bei dem Lieferanten schon' in p.inner_text('#ci-toast') and p.evaluate("document.querySelector('#dlg-schlachthof').open"))
    p.click('#dlg-schlachthof [data-zu]')

    # Fenster „Container“: Auswahl folgt dem Lieferanten
    p.click('[data-sicht="sendungen"]'); p.click('#ci-sendung-neu'); p.wait_for_selector('#dlg-sendung[open]')
    wahl = "[...document.querySelector('#dlg-sendung [name=schlachthof]').options].map(o => o.textContent)"
    check('Neuer Container: ohne Lieferant steht kein Schlachthof zur Wahl, die Auswahl sagt das', p.evaluate(wahl) == ['— für diesen Lieferanten ist keiner angelegt —'], p.evaluate(wahl))
    p.fill('#dlg-sendung [name=lieferant]', 'Frigorifico Beispiel S.A. (70012)'); p.locator('#dlg-sendung [name=lieferant]').blur()
    p.wait_for_function(wahl + '.length === 2')
    check('Lieferant gewählt: seine aktiven Schlachthöfe mit Zulassungsnummer stehen zur Wahl', p.evaluate(wahl) == ['— kein Schlachthof —', 'Werk Asunción Norte · PY-38'], p.evaluate(wahl))
    p.select_option('#dlg-sendung [name=schlachthof]', asu['id'])
    p.fill('#dlg-sendung [name=lieferant]', 'Carnes del Sur Ltda. (70020)'); p.locator('#dlg-sendung [name=lieferant]').blur()
    p.wait_for_function(wahl + ".includes('Werk <b>Sur</b> · UY-7')")
    check('Lieferant gewechselt: die Auswahl zeigt die Schlachthöfe des neuen Lieferanten, der gewählte fremde ist abgewählt',
          p.evaluate(wahl) == ['— kein Schlachthof —', 'Werk <b>Sur</b> · UY-7', 'Werk Asunción · UY-2'] and p.input_value('#dlg-sendung [name=schlachthof]') == '', p.evaluate(wahl))
    p.fill('#dlg-sendung [name=partie]', 'P-270010'); p.select_option('#dlg-sendung [name=schlachthof]', neu['id'])
    shot(p, os.path.join(SH, 'containerimport-container-schlachthof-1280.png'))
    p.click('#dlg-sendung button[type=submit]'); p.wait_for_function("document.querySelector('#sendung-titel')?.textContent === 'Container P-270010'")
    c10 = container(I.call('containerimport_start')[1], 'P-270010')
    check('Container aus dem Fenster gespeichert: Schlachthof steht am Container und bleibt im Fenster gewählt', c10.get('schlachthof') == neu['id'] and c10.get('schlachthofName') == 'Werk <b>Sur</b>'
          and p.input_value('#dlg-sendung [name=schlachthof]') == neu['id'], c10)
    p.click('#dlg-sendung [data-zu]')
    p.click('#ci-sendungen tr:has-text("P-270001")'); p.wait_for_selector('#dlg-sendung[open]')
    p.fill('#dlg-sendung [name=lieferant]', 'Carnes del Sur Ltda. (70020)'); p.locator('#dlg-sendung [name=lieferant]').blur()
    p.wait_for_function(wahl + ".includes('Werk Asunción · UY-2')")
    p.fill('#dlg-sendung [name=lieferant]', 'Frigorifico Beispiel S.A. (70012)'); p.locator('#dlg-sendung [name=lieferant]').blur()
    p.wait_for_function(wahl + ".includes('Werk Asunción Norte · PY-38')")
    check('Lieferant im Fenster gewechselt und wieder zurück: der gespeicherte Schlachthof ist wieder gewählt, nichts geht still verloren', p.input_value('#dlg-sendung [name=schlachthof]') == asu['id'])
    p.click('#dlg-sendung [data-zu]')
    p.click('#ci-sendungen tr:has-text("P-270004")'); p.wait_for_selector('#dlg-sendung[open]')
    check('abgeschlossener Container: Schlachthof gesperrt, mit dem Namen von damals', p.is_disabled('#dlg-sendung [name=schlachthof]') and p.evaluate(wahl) == ['Werk Asunción'], p.evaluate(wahl))
    p.click('#dlg-sendung [data-zu]')
    p.context.close()

    le = seite('lea')
    le.click('[data-sicht="schlachthoefe"]'); le.wait_for_selector('#ci-schlachthoefe')
    le.click(f'[data-schlachthof="{asu["id"]}"]'); le.wait_for_selector('#dlg-schlachthof[open]')
    check('nur ansehen: Liste und Fenster ohne Knöpfe zum Anlegen, Speichern und Archivieren, Felder gesperrt',
          le.locator('#ci-schlachthof-neu').count() == 0 and le.locator('#dlg-schlachthof button[type=submit]').count() == 0 and le.locator('#schlachthof-archiv').count() == 0
          and le.is_disabled('#dlg-schlachthof [name=name]') and le.input_value('#dlg-schlachthof [name=lieferant]') == 'Frigorifico Beispiel S.A.')
    le.click('#dlg-schlachthof [data-zu]'); le.click(f'[data-schlachthof="{frei["id"]}"]'); le.wait_for_selector('#dlg-schlachthof[open]')
    check('nur ansehen, Lieferant als freier Text: Hinweis ohne falsche Aussage über die Stammdaten', 'Nicht mit den Stammdaten verknüpft.' in le.inner_text('#dlg-schlachthof') and 'noch keine Lieferanten' not in le.inner_text('#dlg-schlachthof'))
    le.context.close()

    m = seite('ina', {'width': 390, 'height': 844}, 'dark')
    m.click('[data-sicht="schlachthoefe"]'); m.wait_for_selector('#ci-schlachthoefe')
    check('Handy 390 px: Ansicht ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(m, os.path.join(SH, 'containerimport-schlachthoefe-390-dunkel.png'))
    m.click('[data-sicht="sendungen"]'); m.click('#ci-sendungen tr:has-text("P-270010")'); m.wait_for_selector('#dlg-sendung[open]')
    check('Handy 390 px: Fenster „Container“ einspaltig – jedes Feld so breit wie das Formular, nichts ragt hinaus',
          m.evaluate("(() => { const b = document.querySelector('#dlg-sendung .ci-raster.drei'), w = b.clientWidth; return [...b.querySelectorAll(':scope > .ci-feld')].every((f) => Math.abs(f.offsetWidth - w) <= 1); })()"))
    shot(m, os.path.join(SH, 'containerimport-container-schlachthof-390-dunkel.png'))
    m.context.close()
    br.close()

check('keine JavaScript-Fehler', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
raise SystemExit(0 if all(res) else 1)
