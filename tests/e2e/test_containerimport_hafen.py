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
letzte lesbare Stand bleibt; eine Meldung verfällt nach ihrer Ankunft; ein hängender Abruf hält weder einen zweiten Aufruf
noch das Speichern auf; die Meldung ändert keinen Container. Oberfläche: Hinweis, Meldung in Liste und Fenster,
Fehlermeldung, Leser."""
import datetime
import http.server
import os
import threading
import zoneinfo
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, container, container_anlegen, kalender, seite as seite_oeffnen
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
SPIEL = {'modus': 'ok', 'haengt': False, 'anfragen': [], 'da': threading.Event(), 'weiter': threading.Event()}   # modus: ok | fehler | fremd


class Hafen(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SPIEL['anfragen'].append({'pfad': self.path, 'kopf': dict(self.headers), 'laenge': self.headers.get('Content-Length')})
        if SPIEL['haengt']:   # antwortet erst, wenn der Test es erlaubt (höchstens bis kurz vor dem Zeitlimit des Servers)
            SPIEL['da'].set(); SPIEL['weiter'].wait(11)
        status = 503 if SPIEL['modus'] == 'fehler' else 200
        text = '<html><body><h1>Wir haben umgebaut</h1></body></html>' if SPIEL['modus'] == 'fremd' else VORLAGE.replace('{T1}', im_format_der_seite(0)).replace('{T2}', im_format_der_seite(1))
        roh = text.encode().replace(b'{ROH}', b'\xfc')
        self.send_response(status); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(roh))); self.end_headers(); self.wfile.write(roh)


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


def abruf(modus=None, wer=I):
    """Aktion aufrufen → (Status, Antwort, neue Anfragen beim Hafen). Mit modus: vorher die Frist für abgelaufen erklären
    (letzter Abruf vor Jahren) und den Nachbau umstellen."""
    if modus:
        gespeichert(lambda d: d.update(abgerufen='2020-01-01T00:00:00Z'))
        SPIEL['modus'] = modus
    vorher = len(SPIEL['anfragen'])
    st, r = wer.call('containerimport_tracking_hafen', {})
    return st, r, len(SPIEL['anfragen']) - vorher


def haengen():
    """Ab jetzt antwortet der Nachbau erst, wenn der Test SPIEL['weiter'] setzt; SPIEL['da'] meldet die Ankunft der Anfrage."""
    SPIEL['da'].clear(); SPIEL['weiter'].clear(); SPIEL['haengt'] = True


def stand():
    return I.call('containerimport_start')[1]


# ---------- Rechte, kein Abruf ohne Bedarf ----------
c1 = anlegen('P-290001', schiff='Beispiel Express', zielhafen='Rotterdam', eta=tag(1), stand='unterwegs')
check('Stand: noch nie abgerufen, keine Meldungen', stand()['hafen'] == {'abgerufen': '', 'gelesen': '', 'fehler': '', 'anzahl': 0, 'meldungen': {}}, stand().get('hafen'))
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_tracking_hafen', {})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_tracking_hafen')[0] == 405)
st, r, neu = abruf()
check('kein Container mit Schiff und Zielhafen Hamburg unterwegs: kein Abruf', st == 200 and r.get('abgerufen') is False and neu == 0, (st, r.get('abgerufen'), neu))

# ---------- Abruf, Lesen, Zuordnen ----------
c2 = anlegen('P-290002', schiff='beispiel-express', zielhafen='Hamburg (Burchardkai)', eta=tag(3), stand='unterwegs')
c3 = anlegen('P-290003', schiff='Fracht & Stern', zielhafen='Hamburg', stand='unterwegs')
c4 = anlegen('P-290004', schiff='Pier Probe', zielhafen='Hamburg', stand='angekommen')
c5 = anlegen('P-290005', schiff='Nicht In Der Liste', zielhafen='Hamburg', stand='unterwegs')
vorher = container(stand(), 'P-290002')
st, r, neu = abruf(wer=L)
h = r.get('hafen', {})
an = SPIEL['anfragen'][-1] if SPIEL['anfragen'] else {}
check('auch wer nur ansehen darf, stößt den Abruf an: genau eine Anfrage', st == 200 and r.get('abgerufen') is True and neu == 1, (st, r.get('error'), neu))
check('die Anfrage enthält nichts von uns: einfacher Abruf der Seite ohne Angaben, mit erkennbarem Absender in reinem ASCII',
      an.get('pfad') == '/expected' and an.get('laenge') is None and 'STAFL' in an['kopf'].get('User-Agent', '') and an['kopf'].get('User-Agent', '').isascii() and 'Cookie' not in an['kopf']
      and not any(x in str(an) for x in ('P-2900', 'Beispiel', 'Stern')), an)
check('gelesen: fünf Einträge ohne Fehler – der unlesbare ist übersprungen, ein ungültiges Byte auf der Seite stört nicht',
      h.get('anzahl') == 5 and h.get('fehler') == '' and h.get('gelesen') == h.get('abgerufen') != '', h)
m = h.get('meldungen', {})
check('Zuordnung über den Schiffsnamen ohne Rücksicht auf Schreibweise, nur für Container mit Zielhafen Hamburg (nicht Rotterdam), nicht für unbekannte Schiffe',
      set(m) == {c2['id'], c3['id'], c4['id']}, (m, c1['id']))
check('Ankunft mit Zeitzone, Liegeplatz, Terminal; steht ein Schiff zweimal in der Liste, zählt der erste Eintrag',
      m.get(c2['id']) == {'schiff': 'Beispiel Express', 'ankunft': ankunft(0, '15:00'), 'liegeplatz': 'Burchardkai', 'terminal': 'HHLA-CTB'}, m.get(c2['id']))
check('Sonderzeichen im Namen, Uhrzeit nach Mitternacht (12:30 am = 00:30), fehlendes Terminal als leer, Steuerzeichen entfernt',
      m.get(c3['id']) == {'schiff': 'Fracht & Stern', 'ankunft': ankunft(1, '00:30'), 'liegeplatz': 'Europakai', 'terminal': 'HHLA-CTT'}
      and m.get(c4['id']) == {'schiff': 'Pier Probe', 'ankunft': ankunft(1, '18:00'), 'liegeplatz': 'Neuhöfer Pier', 'terminal': ''}, m)
check('die Antwort bringt nur die Meldungen: nicht den Stand der Container und nichts aus der fremden Liste, das nicht zu uns gehört',
      set(r) == {'ok', 'abgerufen', 'hafen'} and 'Massengut' not in str(r) and 'Unlesbar' not in str(r) and 'Massengut' not in str(stand()), sorted(r))
check('die Meldung ändert keinen Container: geplante Ankunft, Stand und Revision bleiben', container(stand(), 'P-290002') == vorher, container(stand(), 'P-290002'))
st, r, neu = abruf()
check('innerhalb der Frist: kein zweiter Abruf, die Meldungen bleiben', st == 200 and r.get('abgerufen') is False and neu == 0 and len(r['hafen']['meldungen']) == 3)

# ---------- Fehlschläge, Verfall ----------
gelesen = r['hafen']['gelesen']
st, r, neu = abruf('fehler')
check('Hafen antwortet mit einem Fehler: verständliche Meldung, der letzte lesbare Stand bleibt mit seiner Zeit',
      st == 200 and '503' in r['hafen']['fehler'] and r['hafen']['gelesen'] == gelesen and len(r['hafen']['meldungen']) == 3 and neu == 1, r.get('hafen'))
st, r, neu = abruf()
check('nach einem Fehlschlag nicht sofort wieder (Frist von 15 Minuten)', r.get('abgerufen') is False and neu == 0)
st, r, neu = abruf('fremd')
check('Seite mit geändertem Aufbau: Meldung „ließ sich nicht lesen“, alter Stand bleibt', st == 200 and 'nicht lesen' in r['hafen']['fehler'] and len(r['hafen']['meldungen']) == 3, r.get('hafen'))
gespeichert(lambda d: [x.update(ankunft=ankunft(-1, '09:00')) for x in d['schiffe'] if x['schiff'] == 'Fracht & Stern'])
check('eine Meldung verfällt zwölf Stunden nach ihrer Ankunft: kein „wird erwartet“ für ein Schiff von gestern', set(stand()['hafen']['meldungen']) == {c2['id'], c4['id']}, stand()['hafen']['meldungen'])
st, r, neu = abruf('ok')
check('danach wieder lesbar: Fehler weg, neue Zeit, alle Meldungen', st == 200 and r['hafen']['fehler'] == '' and r['hafen']['gelesen'] == r['hafen']['abgerufen'] and neu == 1 and len(r['hafen']['meldungen']) == 3, r.get('hafen'))

# ---------- ein hängender Abruf hält nichts auf ----------
haengend = {}
haengen()
faden = threading.Thread(target=lambda: haengend.update(antwort=abruf('ok', wer=L)))
faden.start()
check('der Abruf ist beim Hafen angekommen und hängt dort', SPIEL['da'].wait(10))
st, r = I.call('containerimport_tracking_hafen', {})
check('ein zweiter Aufruf währenddessen wartet nicht und ruft nicht auch ab', st == 200 and r.get('abgerufen') is False and len(r['hafen']['meldungen']) == 3, (st, r))
st, r = I.call('containerimport_tracking_save', {'id': c5['id'], 'rev': c5['rev'], 'eta': tag(2)})
check('Speichern geht währenddessen durch – der Abruf hält keine Sperre (im SQLite-Speicher stünde sonst jedes Speichern)', st == 200 and container(r, 'P-290005').get('eta') == tag(2), (st, r.get('error')))
SPIEL['weiter'].set(); faden.join(20)
st, r, neu = haengend.get('antwort', (0, {}, 0))
check('der hängende Abruf kommt danach an und legt sein Ergebnis ab', st == 200 and r.get('abgerufen') is True and r['hafen']['fehler'] == '' and stand()['hafen']['gelesen'] == r['hafen']['gelesen'], (st, r))
SPIEL['haengt'] = False

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        pg = seite_oeffnen(br, user, errs, fremd, vp, schema)
        pg.click('#ci-reiter-tracking'); pg.wait_for_selector('#ci-tracking')
        return pg

    anfragen = len(SPIEL['anfragen'])
    p = seite('ina')
    zeile = p.inner_text(f'[data-tracking="{c2["id"]}"]')
    check('Liste: Meldung von Hafen Hamburg mit Zeit, Liegeplatz und Terminal neben der geplanten Ankunft', 'Hafen Hamburg:' in zeile and '15:00 · Burchardkai, HHLA-CTB' in zeile and 'in 3 Tagen' in zeile, zeile)
    hinweis = p.inner_text('#ci-t-hafen')
    check('Hinweis nennt Quelle, Stand mit Datum und Zahl der gelesenen Schiffe', 'laut Hafen Hamburg (HVCC)' in hinweis and 'die nächsten 5 Schiffe' in hinweis and datetime.date.fromisoformat(tag(0)).strftime('%d.%m.%Y') in hinweis, hinweis)
    check('Container ohne Meldung zeigen keine – auch nicht der nach Rotterdam mit einem Schiff aus der Liste',
          not any('Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c["id"]}"]') for c in (c1, c5)))
    check('innerhalb der Frist löst der Besuch des Reiters keinen Abruf aus', len(SPIEL['anfragen']) == anfragen)
    shot(p, os.path.join(SH, 'containerimport-hafen-1280.png'))
    p.click(f'[data-tracking="{c3["id"]}"]'); p.wait_for_selector('#dlg-tracking[open]')
    fenster = p.inner_text('#dlg-tracking')
    check('Fenster: Meldung mit Schiff, Zeit und Hinweis auf die Quelle; fremder Text als Text', 'Fracht & Stern wird erwartet' in fenster and '00:30 · Europakai, HHLA-CTT' in fenster and 'Quelle HVCC' in fenster, p.inner_text('#dlg-tracking .ci-abschluss'))
    shot(p, os.path.join(SH, 'containerimport-hafen-fenster-1280.png'))
    p.click('#dlg-tracking [data-zu]')
    gespeichert(lambda d: d.update(abgerufen='2020-01-01T00:00:00Z')); SPIEL['modus'] = 'fehler'; haengen()
    p.click('#ci-neu'); p.wait_for_selector('#ci-toast.zeigen')
    check('„Stand neu laden“ fragt die Hafenliste wieder an – die Seite ist schon da, während der Abruf noch läuft', SPIEL['da'].wait(10) and p.is_visible('#ci-tracking'))
    p.fill('#ci-t-suche', 'P-2900'); SPIEL['weiter'].set()
    p.wait_for_function("document.querySelector('#ci-t-hafen')?.textContent.includes('503')")
    check('genau ein Abruf; der Fehlschlag steht im Hinweis, die letzte Meldung bleibt sichtbar',
          'letzte lesbare Stand' in p.inner_text('#ci-t-hafen') and 'Hafen Hamburg:' in p.inner_text(f'[data-tracking="{c2["id"]}"]') and len(SPIEL['anfragen']) == anfragen + 1, p.inner_text('#ci-t-hafen'))
    check('die Antwort im Hintergrund zeichnet neu, ohne die Suche zu stören: Eingabe und Fokus bleiben', p.evaluate("document.activeElement.id") == 'ci-t-suche' and p.input_value('#ci-t-suche') == 'P-2900')
    p.context.close()

    handy = seite('lea', {'width': 390, 'height': 844}, 'dark')
    check('nur ansehen, Handy 390 px: Meldung sichtbar, kein waagerechtes Scrollen', 'Hafen Hamburg:' in handy.inner_text(f'[data-tracking="{c2["id"]}"]') and handy.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(handy, os.path.join(SH, 'containerimport-hafen-390-dunkel.png'))
    handy.context.close()
    br.close()
    check('die Seite im Browser ruft den Hafen nie selbst ab', fremd == [], fremd)

# ---------- nicht erreichbar ----------
srv.shutdown(); srv.server_close()
SPIEL['haengt'] = False
st, r, neu = abruf('ok')
check('Hafen nicht erreichbar: Meldung „gerade nicht erreichbar“, kein Fehler der Aktion', st == 200 and 'nicht erreichbar' in r['hafen']['fehler'], (st, r.get('hafen')))

check('keine JavaScript-Fehler', not errs, errs)
ende()
