"""Container-Import · Tracking: bestätigte Ankunft in Hamburg aus der öffentlichen Liste „Expected vessels“ von Hafen Hamburg
(app/api/module/containerimport/hafen.php, Aktion containerimport_tracking_hafen, Anzeige in tracking.js).
Die Seite des Hafens ist nachgebaut (Hilfsserver auf AUX_PORT, WA_HAFEN_HH_URL; tests/fixtures/containerimport/hafen-hamburg.html
mit dem Aufbau der echten Seite und erfundenen Schiffen) – die Tests rufen nie den echten Hafen ab (für alle anderen Gruppen
zeigt die Adresse auf einen geschlossenen Port, tests/run_e2e.py).
Geprüft: Rechte (auch nur ansehen darf anstoßen, CSRF, kein GET); kein Abruf, solange kein Container mit Schiff und Zielhafen
Hamburg unterwegs ist; Abruf ohne eigene Daten (keine Containernummer, kein Schiffsname in der Anfrage); gelesen werden Schiff,
Ankunft mit Zeitzone, Liegeplatz, Terminal – „-“ als keine Angabe, Sonderzeichen, Steuerzeichen entfernt, Unlesbares
übersprungen, ein ungültiges Byte auf der Seite stört nicht; Zuordnung über den Schiffsnamen ohne Rücksicht auf Schreibweise und
nur für Container mit Zielhafen Hamburg; ein doppeltes Schiff; die Antwort bringt nur die Meldungen, nie die fremde Liste;
Frist zwischen zwei Abrufen; Fehlschlag (Fehlerstatus, geänderter Aufbau, nicht erreichbar) als verständliche Meldung, der
letzte lesbare Stand bleibt; eine stückweise Antwort („chunked“) wird zusammengesetzt, eine abgeschnittene gilt nie als
vollständig – weder mit angekündigter Länge noch ohne Schlussstück, und ebenso nicht über 2 MiB mit angekündigter
Länge und ohne („chunked“); eine tröpfelnde Gegenstelle endet nach der Gesamtfrist des Abrufs statt den Webserver-Prozess
beliebig lange zu binden; eine Meldung verfällt nach ihrer Ankunft; ein hängender Abruf hält weder einen zweiten Aufruf
noch das Speichern auf; die Meldung ändert keinen Container. Oberfläche: Hinweis, Meldung in Liste und Fenster,
Fehlermeldung, Leser."""
import contextlib
import datetime
import http.server
import os
import threading
import time
import zoneinfo
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, container, container_anlegen, kalender, stand, seite as seite_oeffnen
from umgebung import AUX_PORT, FIX, SH, shot, storage_raw, storage_write, _json

A, I, L = nutzer_anlegen()
tag = kalender(I)
DOKUMENT = 'containerimport-hafenmeldungen'


def im_format_der_seite(n):
    d = datetime.date.fromisoformat(tag(n))
    return f'{d.strftime("%B")} {d.day}, {d.year}'


def ankunft(n, uhr):
    """Ankunft, wie der Server sie ablegt: Ortszeit Hamburg mit Zeitzone."""
    return datetime.datetime.fromisoformat(f'{tag(n)}T{uhr}').replace(tzinfo=zoneinfo.ZoneInfo('Europe/Berlin')).isoformat()


# ---------- nachgebaute Seite des Hafens ----------
VORLAGE = open(os.path.join(FIX, 'containerimport', 'hafen-hamburg.html'), encoding='utf-8').read()
SPIEL = {'modus': 'ok', 'haengt': False, 'anfragen': [], 'da': threading.Event(), 'weiter': threading.Event()}
# modus: ok | fehler | fremd | abgeschnitten | offen | chunked | chunked-abgeschnitten | zu-gross | zu-gross-chunked | troepfelt


class Hafen(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def roh(self, bytes_):
        """Antwort Byte für Byte selbst schreiben (für Modi, die send_response nicht abbilden kann)."""
        try:
            self.wfile.write(bytes_); self.wfile.flush()
        except OSError:   # der Server hat die Verbindung nach seiner Gesamtfrist beendet
            raise ConnectionError

    def do_GET(self):
        SPIEL['anfragen'].append({'pfad': self.path, 'kopf': dict(self.headers), 'laenge': self.headers.get('Content-Length')})
        if SPIEL['haengt']:   # antwortet erst, wenn der Test es erlaubt (höchstens bis kurz vor dem Zeitlimit des Servers)
            SPIEL['da'].set(); SPIEL['weiter'].wait(11)
        try:
            if SPIEL['modus'] in ('zu-gross', 'zu-gross-chunked'):   # mehr Inhalt als CI_HAFEN_MAX_BYTE (2 MiB)
                fuell = b'<p>' + b'x' * 65536 + b'</p>'
                if SPIEL['modus'] == 'zu-gross':
                    self.roh(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n' % (40 * len(fuell)))
                    for _ in range(40):
                        self.roh(fuell)
                else:   # stückweise, ohne angekündigte Länge
                    self.roh(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nTransfer-Encoding: chunked\r\n\r\n')
                    for _ in range(40):
                        self.roh(b'%x\r\n' % len(fuell) + fuell + b'\r\n')
                    self.roh(b'0\r\n\r\n')
                return
            if SPIEL['modus'] == 'troepfelt':   # Kopfzeilen Byte für Byte, zusammen weit über CI_HAFEN_ZEITLIMIT
                self.roh(b'HTTP/1.1 200 OK\r\n')
                for b in b'X-Fuell: ' + b'0' * 200 + b'\r\n':
                    self.roh(bytes([b])); time.sleep(0.2)
                return
        except ConnectionError:
            return
        status = 503 if SPIEL['modus'] == 'fehler' else 200
        text = '<html><body><h1>Wir haben umgebaut</h1></body></html>' if SPIEL['modus'] == 'fremd' else VORLAGE.replace('{T1}', im_format_der_seite(0)).replace('{T2}', im_format_der_seite(1))
        roh = text.encode().replace(b'{ROH}', b'\xfc')
        if SPIEL['modus'] in ('chunked', 'chunked-abgeschnitten'):   # stückweise Antwort ohne angekündigte Länge
            try:
                self.roh(b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nTransfer-Encoding: chunked\r\n\r\n')
                for i in range(0, len(roh), 700):   # mehrere Stücke, damit das Zusammensetzen geprüft ist
                    self.roh(b'%x\r\n' % len(roh[i:i + 700]) + roh[i:i + 700] + b'\r\n')
                if SPIEL['modus'] == 'chunked':
                    self.roh(b'0\r\n\r\n')   # chunked-abgeschnitten: ohne Schlussstück endet die Verbindung mitten in der Antwort
            except ConnectionError:
                pass
            return
        laenge = len(roh) + (500 if SPIEL['modus'] == 'abgeschnitten' else 0)   # abgeschnitten: kündigt mehr an, als kommt
        self.send_response(status); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(laenge)); self.end_headers(); self.wfile.write(roh); self.wfile.flush()
        if SPIEL['modus'] == 'offen':   # alles geliefert, aber die Verbindung bleibt stehen
            SPIEL['weiter'].wait(11)


srv = http.server.ThreadingHTTPServer(('127.0.0.1', AUX_PORT), Hafen)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def anlegen(partie, **tracking):
    c = container_anlegen(I, partie)
    st, r = I.call('containerimport_tracking_save', {'id': c['id'], 'rev': c['rev'], **tracking})
    assert st == 200, (st, r)
    return container(r, partie)


def gespeichert(aendern):
    """Das gespeicherte Dokument der Meldungen ändern (aendern bekommt es als dict)."""
    d = _json(storage_raw(DOKUMENT))
    aendern(d)
    storage_write(DOKUMENT, d)


def faellig(modus):
    """Der nächste Aufruf ruft wieder ab (letzter Abruf vor Jahren), der Nachbau antwortet im angegebenen Modus."""
    gespeichert(lambda d: d.update(abgerufen='2020-01-01T00:00:00Z'))
    SPIEL['modus'] = modus


def abruf(modus=None, wer=I):
    """Aktion aufrufen → (Status, Antwort, neue Anfragen beim Hafen). Mit modus: vorher faellig(modus)."""
    if modus:
        faellig(modus)
    vorher = len(SPIEL['anfragen'])
    st, r = wer.call('containerimport_tracking_hafen', {})
    return st, r, len(SPIEL['anfragen']) - vorher


@contextlib.contextmanager
def haengend():
    """Solange der Block läuft, antwortet der Nachbau nicht. haengt_dort() wartet, bis eine Anfrage dort angekommen ist;
    am Ende des Blocks antwortet er wieder."""
    SPIEL['da'].clear(); SPIEL['weiter'].clear(); SPIEL['haengt'] = True
    try:
        yield
    finally:
        SPIEL['haengt'] = False; SPIEL['weiter'].set()


def haengt_dort():
    return SPIEL['da'].wait(10)


# ---------- Rechte, kein Abruf ohne Bedarf ----------
c1 = anlegen('P-290001', schiff='Beispiel Express', zielhafen='Rotterdam', eta=tag(1), stand='unterwegs')
check('Stand: noch nie abgerufen, keine Meldungen', stand(I)['hafen'] == {'abgerufen': '', 'gelesen': '', 'fehler': '', 'anzahl': 0, 'meldungen': {}}, stand(I).get('hafen'))
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_tracking_hafen', {})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_tracking_hafen')[0] == 405)
st, r, neu = abruf()
check('kein Container mit Schiff und Zielhafen Hamburg unterwegs: kein Abruf', st == 200 and r.get('geholt') is False and neu == 0, (st, r.get('geholt'), neu))

# ---------- Abruf, Lesen, Zuordnen ----------
c2 = anlegen('P-290002', schiff='beispiel-express', zielhafen='Hamburg (Burchardkai)', eta=tag(3), stand='unterwegs')
c3 = anlegen('P-290003', schiff='Fracht & Stern', zielhafen='Hamburg', stand='unterwegs')
c4 = anlegen('P-290004', schiff='Pier Probe', zielhafen='Hamburg', stand='angekommen')
c5 = anlegen('P-290005', schiff='Nicht In Der Liste', zielhafen='Hamburg', stand='unterwegs')
MIT_MELDUNG = {c2['id'], c3['id'], c4['id']}
vorher = container(stand(I), 'P-290002')
st, r, neu = abruf(wer=L)
h = r.get('hafen', {})
an = SPIEL['anfragen'][-1] if SPIEL['anfragen'] else {}
check('auch wer nur ansehen darf, stößt den Abruf an: genau eine Anfrage', st == 200 and r.get('geholt') is True and neu == 1, (st, r.get('error'), neu))
check('die Anfrage enthält nichts von uns: einfacher Abruf der Seite ohne Angaben, mit erkennbarem Absender in reinem ASCII',
      an.get('pfad') == '/expected' and an.get('laenge') is None and 'STAFL' in an['kopf'].get('User-Agent', '') and an['kopf'].get('User-Agent', '').isascii() and 'Cookie' not in an['kopf']
      and not any(x in str(an) for x in ('P-2900', 'Beispiel', 'Stern')), an)
check('gelesen: fünf Einträge ohne Fehler – der unlesbare ist übersprungen, ein ungültiges Byte auf der Seite stört nicht',
      h.get('anzahl') == 5 and h.get('fehler') == '' and h.get('gelesen') == h.get('abgerufen') != '', h)
m = h.get('meldungen', {})
check('Zuordnung über den Schiffsnamen ohne Rücksicht auf Schreibweise, nur für Container mit Zielhafen Hamburg (nicht Rotterdam), nicht für unbekannte Schiffe',
      set(m) == MIT_MELDUNG, (m, c1['id']))
check('Ankunft mit Zeitzone, Liegeplatz, Terminal; steht ein Schiff zweimal in der Liste, zählt der erste Eintrag',
      m.get(c2['id']) == {'schiff': 'Beispiel Express', 'ankunft': ankunft(0, '15:00'), 'liegeplatz': 'Burchardkai', 'terminal': 'HHLA-CTB'}, m.get(c2['id']))
check('Sonderzeichen im Namen, Uhrzeit nach Mitternacht (12:30 am = 00:30), fehlendes Terminal als leer, Steuerzeichen entfernt',
      m.get(c3['id']) == {'schiff': 'Fracht & Stern', 'ankunft': ankunft(1, '00:30'), 'liegeplatz': 'Europakai', 'terminal': 'HHLA-CTT'}
      and m.get(c4['id']) == {'schiff': 'Pier Probe', 'ankunft': ankunft(1, '18:00'), 'liegeplatz': 'Neuhöfer Pier', 'terminal': ''}, m)
check('die Antwort bringt nur die Meldungen: nicht den Stand der Container und nichts aus der fremden Liste, das nicht zu uns gehört',
      set(r) == {'ok', 'geholt', 'hafen'} and 'Massengut' not in str(r) and 'Unlesbar' not in str(r) and 'Massengut' not in str(stand(I)), sorted(r))
check('die Meldung ändert keinen Container: geplante Ankunft, Stand und Revision bleiben', container(stand(I), 'P-290002') == vorher, container(stand(I), 'P-290002'))
st, r, neu = abruf()
check('innerhalb der Frist: kein zweiter Abruf, die Meldungen bleiben', st == 200 and r.get('geholt') is False and neu == 0 and set(r['hafen']['meldungen']) == MIT_MELDUNG)

# ---------- Fehlschläge, Verfall ----------
gelesen = r['hafen']['gelesen']
st, r, neu = abruf('fehler')
check('Hafen antwortet mit einem Fehler: verständliche Meldung, der letzte lesbare Stand bleibt mit seiner Zeit',
      st == 200 and '503' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG and neu == 1, r.get('hafen'))
st, r, neu = abruf()
check('nach einem Fehlschlag nicht sofort wieder (Frist von 15 Minuten)', r.get('geholt') is False and neu == 0)
st, r, neu = abruf('fremd')
check('Seite mit geändertem Aufbau: Meldung „ließ sich nicht lesen“, alter Stand bleibt', st == 200 and 'nicht lesen' in r['hafen']['fehler'] and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
gespeichert(lambda d: [x.update(ankunft=ankunft(-1, '09:00')) for x in d['schiffe'] if x['schiff'] == 'Fracht & Stern'])
check('eine Meldung verfällt zwölf Stunden nach ihrer Ankunft: kein „wird erwartet“ für ein Schiff von gestern', set(stand(I)['hafen']['meldungen']) == {c2['id'], c4['id']}, stand(I)['hafen']['meldungen'])
gespeichert(lambda d: d.update(schiffe={'hamburg': {'liste': d['schiffe']}, 'x': 'Text', 'y': {'schiff': 'Beispiel Express'}}))
st, r = I.call('containerimport_start')
check('anders geschnittener Zwischenspeicher (spätere Version, dann Rückfall): das Modul startet, nur ohne Meldungen', st == 200 and r['hafen']['meldungen'] == {} and r['hafen']['anzahl'] == 0, (st, r.get('error'), r.get('hafen')))
st, r, neu = abruf('ok')   # der Rückfall-Test hat den Zwischenspeicher geleert: erst wieder einen lesbaren Stand, den die folgenden Fehlschläge behalten müssen
gelesen = r['hafen']['gelesen']
check('nach dem Rückfall wieder lesbar: alle Meldungen stehen', st == 200 and r['hafen']['fehler'] == '' and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
st, r, neu = abruf('abgeschnitten')
check('Antwort kürzer als angekündigt: Fehlschlag statt einer halben Liste als neuem Stand',
      st == 200 and 'nicht vollständig' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
st, r, neu = abruf('chunked')
check('stückweise Antwort ohne angekündigte Länge: die Stücke werden zusammengesetzt und gelesen',
      st == 200 and r['hafen']['fehler'] == '' and r['hafen']['gelesen'] != gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
gelesen = r['hafen']['gelesen']
st, r, neu = abruf('chunked-abgeschnitten')
check('stückweise Antwort ohne Schlussstück: Fehlschlag statt einer halben Liste als neuem Stand',
      st == 200 and 'nicht vollständig' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
for modus in ('zu-gross', 'zu-gross-chunked'):
    st, r, neu = abruf(modus)
    check(f'mehr als 2 MiB ({modus}): Fehlschlag statt der abgeschnittenen ersten 2 MiB als neuem Stand',
          st == 200 and 'unerwartet groß' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))
# Gesamtfrist: eine tröpfelnde Gegenstelle darf keinen Webserver-Prozess beliebig lange binden (CI_HAFEN_ZEITLIMIT)
t0 = time.monotonic()
st, r, neu = abruf('troepfelt')
dauer = time.monotonic() - t0
check('tröpfelnde Gegenstelle: der Abruf endet nach der Gesamtfrist mit einem Fehlschlag, nicht erst mit der Gegenstelle',
      st == 200 and r['hafen']['fehler'] != '' and dauer < 35 and r['hafen']['gelesen'] == gelesen and set(r['hafen']['meldungen']) == MIT_MELDUNG, (st, round(dauer, 1), r.get('hafen')))
SPIEL['weiter'].clear()
st, r, neu = abruf('offen')
check('alles geliefert, Verbindung bleibt offen: gelesen, ohne auf das Ende der Verbindung zu warten (der Nachbau hält sie noch)',
      st == 200 and r.get('geholt') is True and r['hafen']['fehler'] == '' and set(r['hafen']['meldungen']) == MIT_MELDUNG and not SPIEL['weiter'].is_set(), r.get('hafen'))
SPIEL['weiter'].set()
jetzt = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
gespeichert(lambda d: d.update(abgerufen='2020-01-01T00:00:00Z', versuch=jetzt))
st, r, neu = abruf()
check('ein anderer Abruf läuft gerade (vorgemerkt): kein zweiter', st == 200 and r.get('geholt') is False and neu == 0, (st, r.get('geholt'), neu))
gespeichert(lambda d: d.update(versuch='2020-01-01T00:00:00Z'))
st, r, neu = abruf()
check('Abruf mitten drin abgebrochen (Vormerkung alt, nie beendet): der nächste Aufruf ruft ab, statt zwei Stunden still zu warten', st == 200 and r.get('geholt') is True and neu == 1 and r['hafen']['fehler'] == '', (st, r.get('geholt'), neu))
st, r, neu = abruf('ok')
check('danach wieder lesbar: Fehler weg, neue Zeit, alle Meldungen', st == 200 and r['hafen']['fehler'] == '' and r['hafen']['gelesen'] == r['hafen']['abgerufen'] and neu == 1 and set(r['hafen']['meldungen']) == MIT_MELDUNG, r.get('hafen'))

# ---------- ein hängender Abruf hält nichts auf ----------
haengend_antwort = {}
with haengend():
    faden = threading.Thread(target=lambda: haengend_antwort.update(antwort=abruf('ok', wer=L)))
    faden.start()
    check('der Abruf ist beim Hafen angekommen und hängt dort', haengt_dort())
    st, r = I.call('containerimport_tracking_hafen', {})
    check('ein zweiter Aufruf währenddessen wartet nicht und ruft nicht auch ab', st == 200 and r.get('geholt') is False and set(r['hafen']['meldungen']) == MIT_MELDUNG, (st, r))
    st, r = I.call('containerimport_tracking_save', {'id': c5['id'], 'rev': c5['rev'], 'eta': tag(2)})
    check('Speichern geht währenddessen durch – der Abruf hält keine Sperre (im SQLite-Speicher stünde sonst jedes Speichern)', st == 200 and container(r, 'P-290005').get('eta') == tag(2), (st, r.get('error')))
    c6 = anlegen('P-290006', schiff='Pier Probe', zielhafen='Hamburg', stand='unterwegs')
faden.join(20)
st, r, neu = haengend_antwort.get('antwort', (0, {}, 0))
check('der hängende Abruf kommt danach an und legt sein Ergebnis ab', st == 200 and r.get('geholt') is True and r['hafen']['fehler'] == '' and stand(I)['hafen']['gelesen'] == r['hafen']['gelesen'], (st, r))
check('seine Antwort kennt auch den Container, der während des Abrufs dazukam', set(r['hafen']['meldungen']) == MIT_MELDUNG | {c6['id']}, r.get('hafen'))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        pg = seite_oeffnen(br, user, errs, fremd, vp, schema)
        with pg.expect_response(lambda r: 'action=containerimport_tracking_hafen' in r.url):   # der Reiter bittet den Server im Hintergrund um das Auffrischen
            pg.click('#ci-reiter-tracking')
        pg.wait_for_selector('#ci-tracking')
        return pg

    anfragen = len(SPIEL['anfragen'])
    p = seite('ina')
    zeile = p.inner_text(f'[data-tracking="{c2["id"]}"]')
    check('Liste: Meldung von Hafen Hamburg mit Zeit, Liegeplatz und Terminal neben der geplanten Ankunft', 'Hafen Hamburg:' in zeile and '15:00 · Burchardkai, HHLA-CTB' in zeile and 'in 3 Tagen' in zeile, zeile)
    hinweis = p.inner_text('#ci-t-hafen')
    check('Hinweis nennt Quelle, Stand mit Datum und Zahl der gelesenen Schiffe', 'laut Hafen Hamburg (HVCC)' in hinweis and 'die nächsten 5 Schiffe' in hinweis and datetime.date.fromisoformat(tag(0)).strftime('%d.%m.%Y') in hinweis, hinweis)
    check('Container ohne Meldung zeigen keine – auch nicht der nach Rotterdam mit einem Schiff aus der Liste',
          not any('Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c["id"]}"]') for c in (c1, c5)))
    check('der Reiter hat den Server gefragt; innerhalb der Frist löst das keinen Abruf aus', len(SPIEL['anfragen']) == anfragen)
    shot(p, os.path.join(SH, 'containerimport-hafen-1280.png'))
    p.click(f'[data-tracking="{c3["id"]}"]'); p.wait_for_selector('#dlg-tracking[open]')
    fenster = p.inner_text('#dlg-tracking')
    check('Fenster: Meldung mit Schiff, Zeit und Hinweis auf die Quelle; fremder Text als Text', 'Fracht & Stern wird erwartet' in fenster and '00:30 · Europakai, HHLA-CTT' in fenster and 'Quelle HVCC' in fenster, p.inner_text('#dlg-tracking .ci-abschluss'))
    shot(p, os.path.join(SH, 'containerimport-hafen-fenster-1280.png'))
    p.click('#dlg-tracking [data-zu]')
    faellig('fehler')
    with haengend():
        p.click('#ci-neu'); p.wait_for_selector('#ci-toast.zeigen')
        check('„Stand neu laden“ fragt die Hafenliste wieder an – die Seite ist schon da, während der Abruf noch läuft', haengt_dort() and p.is_visible('#ci-tracking'))
        p.fill('#ci-t-suche', 'P-2900')
    p.wait_for_function("document.querySelector('#ci-t-hafen')?.textContent.includes('503')")
    check('genau ein Abruf; der Fehlschlag steht im Hinweis, die letzte Meldung bleibt sichtbar',
          'letzte lesbare Stand' in p.inner_text('#ci-t-hafen') and 'Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c2["id"]}"]') and len(SPIEL['anfragen']) == anfragen + 1, p.inner_text('#ci-t-hafen'))
    check('die Antwort im Hintergrund zeichnet neu, ohne die Suche zu stören: Eingabe und Fokus bleiben', p.evaluate("document.activeElement.id") == 'ci-t-suche' and p.input_value('#ci-t-suche') == 'P-2900')
    faellig('ok')
    with haengend():
        p.click('#ci-neu'); haengt_dort()
        p.focus(f'[data-tracking="{c2["id"]}"]')
    p.wait_for_function("!document.querySelector('#ci-t-hafen')?.textContent.includes('503')")
    check('wer mit der Tastatur auf einer Zeile steht, bleibt nach der Antwort im Hintergrund dort', p.evaluate("document.activeElement.dataset.tracking") == c2['id'], p.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
    p.click(f'[data-tracking="{c1["id"]}"]'); p.wait_for_selector('#dlg-tracking[open]')
    p.fill('#dlg-tracking [name=zielhafen]', 'Hamburg')
    with p.expect_response(lambda r: 'action=containerimport_tracking_hafen' in r.url):
        p.click('#dlg-tracking button[type=submit]')
    p.click('#dlg-tracking [data-zu]')
    check('nach dem Speichern fragt die offene Seite gleich wieder an: der Container mit neuem Zielhafen Hamburg zeigt seine Meldung', 'Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c1["id"]}"]'), p.inner_text(f'[data-tracking="{c1["id"]}"]'))
    p.context.close()

    handy = seite('lea', {'width': 390, 'height': 844}, 'dark')
    check('nur ansehen, Handy 390 px: Meldung sichtbar, kein waagerechtes Scrollen', 'Hafen Hamburg:' in handy.inner_text(f'[data-tracking="{c2["id"]}"]') and handy.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(handy, os.path.join(SH, 'containerimport-hafen-390-dunkel.png'))
    handy.context.close()
    br.close()
    check('die Seite im Browser ruft den Hafen nie selbst ab', fremd == [], fremd)

# ---------- nicht erreichbar ----------
srv.shutdown(); srv.server_close()
st, r, neu = abruf('ok')
check('Hafen nicht erreichbar: Meldung „gerade nicht erreichbar“, kein Fehler der Aktion', st == 200 and 'nicht erreichbar' in r['hafen']['fehler'], (st, r.get('hafen')))

check('keine JavaScript-Fehler', not errs, errs)
ende()
