"""Container-Import · Tracking: bestätigte Ankunft in Hamburg aus der öffentlichen Liste „Expected vessels“ von Hafen Hamburg
(app/api/module/containerimport/hafen.php, Aktion containerimport_tracking_hafen, Anzeige in tracking.js).
Die Seite des Hafens ist nachgebaut (Hilfsserver auf AUX_PORT, WA_HAFEN_HH_URL; tests/fixtures/containerimport/hafen-hamburg.html
mit dem Aufbau der echten Seite und erfundenen Schiffen) – die Tests rufen nie den echten Hafen ab.
Geprüft: Rechte (auch nur ansehen darf anstoßen, CSRF, kein GET); kein Abruf, solange kein Container mit Schiff und Zielhafen
Hamburg unterwegs ist; Abruf ohne eigene Daten (keine Containernummer, kein Schiffsname in der Anfrage); gelesen werden Schiff,
Ankunft, Liegeplatz, Terminal – „-“ als keine Angabe, Sonderzeichen, Unlesbares übersprungen; Zuordnung über den Schiffsnamen
ohne Rücksicht auf Schreibweise; die fremde Liste selbst wird nicht ausgeliefert; Frist zwischen zwei Abrufen; Fehlschlag
(Fehlerstatus, geänderter Aufbau, nicht erreichbar) als verständliche Meldung, der letzte lesbare Stand bleibt; die Meldung
ändert keinen Container. Oberfläche: Hinweis, Meldung in Liste und Fenster, Fehlermeldung, Leser."""
import http.server
import os
import threading
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, container, seite as seite_oeffnen
from umgebung import AUX_PORT, FIX, SH, shot, storage_raw, storage_write, _json

A, I, L = nutzer_anlegen()
HEUTE = __import__('datetime').date.fromisoformat(I.call('containerimport_start')[1]['heute'])


def tag(n):
    return (HEUTE + __import__('datetime').timedelta(days=n)).isoformat()


def im_format_der_seite(n):
    d = HEUTE + __import__('datetime').timedelta(days=n)
    return f'{d.strftime("%B")} {d.day}, {d.year}'


# ---------- nachgebaute Seite des Hafens ----------
VORLAGE = open(os.path.join(FIX, 'containerimport', 'hafen-hamburg.html'), encoding='utf-8').read()
SPIEL = {'modus': 'ok', 'anfragen': []}   # modus: ok | fehler | fremd


class Hafen(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SPIEL['anfragen'].append({'pfad': self.path, 'kopf': dict(self.headers), 'laenge': self.headers.get('Content-Length')})
        status = 503 if SPIEL['modus'] == 'fehler' else 200
        text = '<html><body><h1>Wir haben umgebaut</h1></body></html>' if SPIEL['modus'] == 'fremd' else VORLAGE.replace('{T1}', im_format_der_seite(0)).replace('{T2}', im_format_der_seite(1))
        roh = text.encode()
        self.send_response(status); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(roh))); self.end_headers(); self.wfile.write(roh)


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Hafen)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def anlegen(partie, **tracking):
    st, r = I.call('containerimport_eudr_sendung_save', {'id': '', 'rev': 0, 'partie': partie, 'lieferant': 'Frigorifico Beispiel', 'land': 'PY'})
    assert st == 200, (st, r)
    c = container(r, partie)
    st, r = I.call('containerimport_tracking_save', {'id': c['id'], 'rev': c['rev'], **tracking})
    assert st == 200, (st, r)
    return container(r, partie)


def frist_abgelaufen():
    """Den letzten Abruf drei Stunden zurücklegen, damit der Server wieder abrufen darf."""
    d = _json(storage_raw('containerimport-hafenmeldungen'))
    d['abgerufen'] = '2020-01-01T00:00:00Z'
    storage_write('containerimport-hafenmeldungen', d)


# ---------- Rechte, kein Abruf ohne Bedarf ----------
c1 = anlegen('P-290001', schiff='Beispiel Express', zielhafen='Rotterdam', eta=tag(1), stand='unterwegs')
r = I.call('containerimport_start')[1]
check('Stand: noch nie abgerufen, keine Meldungen', r['hafen'] == {'abgerufen': '', 'gelesen': '', 'fehler': '', 'anzahl': 0, 'meldungen': {}}, r.get('hafen'))
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_tracking_hafen', {})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_tracking_hafen')[0] == 405)
st, r = I.call('containerimport_tracking_hafen', {})
check('kein Container mit Schiff und Zielhafen Hamburg unterwegs: kein Abruf', st == 200 and r.get('abgerufen') is False and SPIEL['anfragen'] == [], (st, r.get('abgerufen'), SPIEL['anfragen']))

# ---------- Abruf, Lesen, Zuordnen ----------
c2 = anlegen('P-290002', schiff='beispiel-express', zielhafen='Hamburg (Burchardkai)', eta=tag(3), stand='unterwegs')
c3 = anlegen('P-290003', schiff='Fracht & Stern', zielhafen='Hamburg', stand='unterwegs')
c4 = anlegen('P-290004', schiff='Pier Probe', zielhafen='Hamburg', stand='angekommen')
c5 = anlegen('P-290005', schiff='Nicht In Der Liste', zielhafen='Hamburg', stand='unterwegs')
vorher = container(I.call('containerimport_start')[1], 'P-290002')
st, r = L.call('containerimport_tracking_hafen', {})
h = r.get('hafen', {})
an = SPIEL['anfragen'][-1] if SPIEL['anfragen'] else {}
check('auch wer nur ansehen darf, stößt den Abruf an: genau eine Anfrage', st == 200 and r.get('abgerufen') is True and len(SPIEL['anfragen']) == 1, (st, r.get('error'), len(SPIEL['anfragen'])))
check('die Anfrage enthält nichts von uns: einfacher Abruf der Seite ohne Angaben, mit erkennbarem Absender',
      an.get('pfad') == '/expected' and an.get('laenge') is None and 'STAFL' in an['kopf'].get('User-Agent', '') and 'Cookie' not in an['kopf']
      and not any(x in str(an) for x in ('P-2900', 'Beispiel', 'Stern')), an)
check('gelesen: vier Schiffe (der unlesbare Eintrag ist übersprungen), ohne Fehler', h.get('anzahl') == 4 and h.get('fehler') == '' and h.get('gelesen') == h.get('abgerufen') != '', h)
m = h.get('meldungen', {})
check('Zuordnung über den Schiffsnamen ohne Rücksicht auf Schreibweise – auch für Container mit anderem Zielhafen, nicht für unbekannte Schiffe',
      set(m) == {c1['id'], c2['id'], c3['id'], c4['id']} and m[c2['id']] == {'schiff': 'Beispiel Express', 'ankunft': tag(0) + ' 15:00', 'liegeplatz': 'Burchardkai', 'terminal': 'HHLA-CTB'}, m)
check('Sonderzeichen im Namen, Uhrzeit nach Mitternacht (12:30 am = 00:30), fehlendes Terminal als leer',
      m.get(c3['id']) == {'schiff': 'Fracht & Stern', 'ankunft': tag(1) + ' 00:30', 'liegeplatz': 'Europakai', 'terminal': 'HHLA-CTT'}
      and m.get(c4['id'], {}).get('terminal') == '' and m.get(c4['id'], {}).get('liegeplatz') == 'Neuhöfer Pier', m)
check('die fremde Liste selbst wird nicht ausgeliefert (kein Schiff, das nicht zu uns gehört)', 'Massengut' not in str(r) and 'Unlesbar' not in str(r))
check('die Meldung ändert keinen Container: geplante Ankunft, Stand und Revision bleiben', container(r, 'P-290002') == vorher, container(r, 'P-290002'))
st, r = I.call('containerimport_tracking_hafen', {})
check('innerhalb der Frist: kein zweiter Abruf, die Meldungen bleiben', st == 200 and r.get('abgerufen') is False and len(SPIEL['anfragen']) == 1 and len(r['hafen']['meldungen']) == 4)

# ---------- Fehlschläge ----------
gelesen = r['hafen']['gelesen']
frist_abgelaufen(); SPIEL['modus'] = 'fehler'
st, r = I.call('containerimport_tracking_hafen', {})
check('Hafen antwortet mit einem Fehler: verständliche Meldung, der letzte lesbare Stand bleibt mit seiner Zeit',
      st == 200 and '503' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and len(r['hafen']['meldungen']) == 4 and len(SPIEL['anfragen']) == 2, r.get('hafen'))
st, r = I.call('containerimport_tracking_hafen', {})
check('nach einem Fehlschlag nicht sofort wieder (Frist von 15 Minuten)', r.get('abgerufen') is False and len(SPIEL['anfragen']) == 2)
frist_abgelaufen(); SPIEL['modus'] = 'fremd'
st, r = I.call('containerimport_tracking_hafen', {})
check('Seite mit geändertem Aufbau: Meldung „ließ sich nicht lesen“, alter Stand bleibt', st == 200 and 'nicht lesen' in r['hafen']['fehler'] and len(r['hafen']['meldungen']) == 4, r.get('hafen'))
frist_abgelaufen(); SPIEL['modus'] = 'ok'
st, r = I.call('containerimport_tracking_hafen', {})
check('danach wieder lesbar: Fehler weg, neue Zeit', st == 200 and r['hafen']['fehler'] == '' and r['hafen']['gelesen'] == r['hafen']['abgerufen'] and len(SPIEL['anfragen']) == 4, r.get('hafen'))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        pg = seite_oeffnen(br, user, errs, fremd, vp, schema)
        pg.click('#ci-reiter-tracking'); pg.wait_for_selector('#ci-tracking')
        return pg

    p = seite('ina')
    zeile = p.inner_text(f'[data-tracking="{c2["id"]}"]')
    check('Liste: Meldung von Hafen Hamburg mit Zeit, Liegeplatz und Terminal neben der geplanten Ankunft', 'Hafen Hamburg:' in zeile and '15:00 · Burchardkai, HHLA-CTB' in zeile and 'in 3 Tagen' in zeile, zeile)
    check('Hinweis nennt Quelle, Stand und Zahl der gelesenen Schiffe; Container ohne Meldung zeigen keine', 'laut Hafen Hamburg (HVCC)' in p.inner_text('#ci-t-hafen') and '4 Schiffe' in p.inner_text('#ci-t-hafen')
          and 'Hafen Hamburg:' not in p.inner_text(f'[data-tracking="{c5["id"]}"]'), p.inner_text('#ci-t-hafen'))
    check('der Besuch des Reiters hat den Server um Auffrischen gebeten, innerhalb der Frist ohne neuen Abruf', len(SPIEL['anfragen']) == 4)
    shot(p, os.path.join(SH, 'containerimport-hafen-1280.png'))
    p.click(f'[data-tracking="{c3["id"]}"]'); p.wait_for_selector('#dlg-tracking[open]')
    check('Fenster: Meldung mit Schiff, Zeit und Hinweis auf die Quelle; fremder Text als Text', 'Fracht & Stern wird erwartet' in p.inner_text('#dlg-tracking') and '00:30 · Europakai, HHLA-CTT' in p.inner_text('#dlg-tracking')
          and 'Quelle HVCC' in p.inner_text('#dlg-tracking'), p.inner_text('#dlg-tracking .ci-abschluss'))
    shot(p, os.path.join(SH, 'containerimport-hafen-fenster-1280.png'))
    p.click('#dlg-tracking [data-zu]')
    frist_abgelaufen(); SPIEL['modus'] = 'fehler'
    p.click('#ci-neu'); p.wait_for_function("document.querySelector('#ci-t-hafen')?.textContent.includes('503')")
    check('„Stand neu laden“ fragt die Hafenliste wieder an; Fehlschlag steht im Hinweis, die letzte Meldung bleibt sichtbar',
          'letzte lesbare Stand' in p.inner_text('#ci-t-hafen') and 'Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c2["id"]}"]') and len(SPIEL['anfragen']) == 5, p.inner_text('#ci-t-hafen'))
    p.context.close()

    m = seite('lea', {'width': 390, 'height': 844}, 'dark')
    check('nur ansehen, Handy 390 px: Meldung sichtbar, kein waagerechtes Scrollen', 'Hafen Hamburg:' in m.inner_text(f'[data-tracking="{c2["id"]}"]') and m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(m, os.path.join(SH, 'containerimport-hafen-390-dunkel.png'))
    m.context.close()
    br.close()
    check('die Seite im Browser ruft den Hafen nie selbst ab', fremd == [], fremd)

# ---------- nicht erreichbar ----------
srv.shutdown(); srv.server_close()
frist_abgelaufen()
st, r = I.call('containerimport_tracking_hafen', {})
check('Hafen nicht erreichbar: Meldung „gerade nicht erreichbar“, kein Fehler der Aktion', st == 200 and 'nicht erreichbar' in r['hafen']['fehler'], (st, r.get('hafen')))

check('keine JavaScript-Fehler', not errs, errs)
ende()
