"""Testgruppe postausgang: Postausgang von innen (ADR-007, lib/postausgang.php). Wie im Betrieb zwei Seiten auf denselben Daten:
der Testserver ist die Kundenseite (WA_POSTAUSGANG=warteschlange, keine Postfach-Zugangsdaten), ein zweiter PHP-Server auf dem
Hilfsport die Mitarbeiterseite (Postfach, Schlüssel in WA_GEHEIM_DIR). Der Dienst api/postausgang.php läuft wie im Container
postausgang mit den Zugangsdaten der Mitarbeiterseite. Geprüft: Bestellwunsch, Wiederholung bei Ausfall, Benachrichtigungen,
Abmeldehinweis, Bestellfunktion nur mit Lebenszeichen des Dienstes, keine Geheimnisse in den Aufträgen."""
import base64, hashlib, hmac, http.cookiejar, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import AUX_PORT, BASE, SH, SMTP_PORT, WORK, storage_raw, storage_write, until

PW = 'Sicheres-Passwort-1'
DATA = os.environ['UDATA']
APP = os.path.dirname(DATA)
GEHEIM = os.path.join(WORK, 'geheim-postausgang-' + str(AUX_PORT))
shutil.rmtree(GEHEIM, ignore_errors=True); os.makedirs(GEHEIM)
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name)
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


class Mitarbeiter(Client):
    """Client gegen die Mitarbeiterseite (zweiter Server auf dem Hilfsport)"""
    def call(self, action, data=None, raw=False):
        headers = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        req = urllib.request.Request(f'http://127.0.0.1:{AUX_PORT}/api/?action=' + action, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            r = self.http.open(req)
        except urllib.error.HTTPError as e:
            r = e
        j = json.loads(r.read() or b'{}')
        if isinstance(j, dict) and j.get('csrf'): self.csrf = j['csrf']
        return r.code, j


POSTFACH = {'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': str(SMTP_PORT), 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
            'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'MAIL_FROM_NAME': 'Standard-Fleisch', 'WA_URL': BASE}
basis = {k: v for k, v in os.environ.items() if not k.startswith('MAIL_') and k not in ('WA_URL', 'WA_POSTAUSGANG', 'WA_GEHEIM_DIR')}
INNEN = {**basis, **POSTFACH, 'WA_GEHEIM_DIR': GEHEIM}
srv = subprocess.Popen(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-S', f'127.0.0.1:{AUX_PORT}'], cwd=APP, env=INNEN,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def dienst(env=None):
    """Ein Durchgang des Dienstes postausgang (wie im Container: eigener Prozess je Durchgang)"""
    p = subprocess.run(['php', os.path.join(APP, 'api', 'postausgang.php')], env=env or INNEN, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def faellig_machen():
    q = doc('postausgang') or {'auftraege': []}
    for a in q['auftraege']: a['faellig'] = 0
    storage_write('postausgang', q)


try:
    until(lambda: subprocess.run(['php', '-r', f'exit(@fsockopen("127.0.0.1", {AUX_PORT}) ? 0 : 1);']).returncode == 0, 10)
    smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
    A = Mitarbeiter('198.51.100.2')
    check('Mitarbeiterseite: Anmeldung', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
    rev = A.call('kunden')[1]['rev']
    r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Post', 'nr': 'K-PA', 'email': 'kantine.post@example.org', 'active': True, 'angebote': ['std'],
                              'login': {'username': 'kantine.post', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
    check('Mitarbeiterseite: Kunde angelegt', r[0] == 200, r)
    kid = r[1]['customer']['id']
    check('Mitarbeiterseite: Bestellfunktion mit Kopie', A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': True})[0] == 200)
    K = Client('198.51.100.20')
    check('Kundenseite: Kundenanmeldung', K.call('kunde_login', {'username': 'kantine.post', 'password': 'Kantine-Kennwort-5'})[0] == 200)

    # ---------- Bestellfunktion nur mit Lebenszeichen des Dienstes ----------
    st = K.call('kunde_status')[1]
    check('ohne Dienst: Kundenseite nimmt keine Bestellwünsche an (kann kein Postfach prüfen)', st['bestellfunktion'] is False, st)
    code, out = dienst({**basis, 'WA_URL': BASE})
    check('Dienst ohne Postfach: läuft, meldet „kein Versand“', code == 0 and (doc('postausgang-stand') or {}).get('versand') is False, out)
    check('Dienst ohne Postfach: Bestellfunktion bleibt aus', K.call('kunde_status')[1]['bestellfunktion'] is False)
    code, out = dienst()
    stand = doc('postausgang-stand') or {}
    check('Dienst mit Postfach: Lebenszeichen und „Versand eingerichtet“', code == 0 and stand.get('versand') is True and stand.get('t', 0) > time.time() - 30, (out, stand))
    check('mit Lebenszeichen: Bestellfunktion an', K.call('kunde_status')[1]['bestellfunktion'] is True)
    code, out = subprocess.run(['php', os.path.join(APP, 'api', 'postausgang.php'), '--pruefen'], env=INNEN, capture_output=True, text=True).returncode, ''
    check('Zustandsprüfung (Docker): frisches Lebenszeichen', code == 0)
    alt = dict(stand); stand['t'] = int(time.time()) - 3600; storage_write('postausgang-stand', stand)
    check('Zustandsprüfung: altes Lebenszeichen → Fehler', subprocess.run(['php', os.path.join(APP, 'api', 'postausgang.php'), '--pruefen'], env=INNEN, capture_output=True).returncode == 1)
    check('Dienst seit 15 Minuten still: Bestellfunktion aus', K.call('kunde_status')[1]['bestellfunktion'] is False)
    storage_write('postausgang-stand', alt)
    code, r = urllib.request.urlopen(BASE + '/api/postausgang.php').getcode(), None
except urllib.error.HTTPError as e:
    code = e.code
except Exception as e:   # Abbruch in der Vorbereitung: als Fehlschlag melden
    check('Vorbereitung', False, repr(e)); code = None
check('api/postausgang.php ist über den Webserver nicht aufrufbar (404)', code == 404, code)

try:
    # ---------- Bestellwunsch: nur abgelegt, dann vom Dienst verschickt ----------
    pub = A.call('draft')[1]['published']; item = pub['items'][0]
    payload = {'angebot': 'std', 'publishedAt': pub.get('publishedAt', pub.get('savedAt', '')), 'positions': [{'id': item['id'], 'qty': 3}], 'requestId': 'postausgang-request-0001'}
    code, q = K.call('kunde_bestellung', payload)
    nr = q.get('nr')
    check('Bestellwunsch angenommen: „eingegangen“, Kopie angekündigt, noch nicht gesendet', code == 200 and q.get('delivery') == 'eingegangen'
          and q.get('copyPlanned') == 'kantine.post@example.org' and q.get('copy') is None, q)
    check('Kundenseite hat keine E-Mail verschickt', not smtp.messages, [m['subject'] for m in smtp.messages])
    auftraege = (doc('postausgang') or {}).get('auftraege', [])
    check('Auftrag abgelegt (nur Bestellnummer)', [(a['art'], a.get('nr')) for a in auftraege] == [('bestellung', nr)], auftraege)
    roh = storage_raw('postausgang') or ''
    check('Auftrag enthält keine Postfachdaten und keinen Mailinhalt', not any(s in roh for s in ('Test-Postfach-1', 'portal@example.org', 'MAIL_', 'html', 'subject')), roh[:300])
    o = A.call('bestellung&nr=' + nr)[1]['order']
    check('Versandaufträge warten beim Vorgang', [j['state'] for j in o['outbox']] == ['queued', 'queued'], o['outbox'])
    code, out = dienst()
    check('Dienst: Team-Mail und Kopie an den Kunden verschickt', code == 0 and until(lambda: len(smtp.messages) == 2, 5)
          and sorted(m['to'][0] for m in smtp.messages) == ['kantine.post@example.org', 'orders@example.org'], (out, [m['to'] for m in smtp.messages]))
    check('Team-Mail mit Bestellnummer, Antwort an den Kunden', any(nr in m['text'] for m in smtp.messages if m['to'] == ['orders@example.org']))
    o = A.call('bestellung&nr=' + nr)[1]['order']
    check('Vorgang: alles zugestellt, durch „Postausgang“', [j['state'] for j in o['outbox']] == ['sent', 'sent'] and o['delivery'] == 'gesendet'
          and all(j['history'][-1]['by'] == 'Postausgang' for j in o['outbox']), o['outbox'])
    check('Warteschlange leer', (doc('postausgang') or {}).get('auftraege') == [])
    versand = [x for x in (doc('mailversand') or []) if x.get('by') == 'Postausgang']
    check('Versandprotokoll vermerkt den Postausgang', len(versand) == 2 and all(x['ok'] for x in versand), versand)
    n = len(smtp.messages)
    code, r = K.call('kunde_bestellung', payload)
    dienst()
    check('Wiederholte Übermittlung: gleicher Vorgang, kein neuer Auftrag, keine neue Mail', code == 200 and r['nr'] == nr and r['replayed'] is True and len(smtp.messages) == n, r)
    check('Kunde sieht den Vorgang', K.call('kunde_bestellung_detail&nr=' + nr)[1]['order']['nr'] == nr)

    # ---------- Postfach gestört: erneute Versuche, Kopie erst nach der Team-Mail ----------
    smtp.close()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0002', 'positions': [{'id': item['id'], 'qty': 4}]})
    nr2 = r.get('nr')
    check('Ausfall: Kunde erhält trotzdem „eingegangen“ (kein 502 mehr)', code == 200 and r.get('delivery') == 'eingegangen', r)
    code, out = dienst()
    o = A.call('bestellung&nr=' + nr2)[1]['order']
    a2 = (doc('postausgang') or {}).get('auftraege', [])
    check('Ausfall: Team-Mail fehlgeschlagen, Kopie wartet', [j['state'] for j in o['outbox']] == ['failed', 'queued'], o['outbox'])
    check('Ausfall: neuer Versuch in 1 Minute eingeplant', len(a2) == 1 and a2[0]['nr'] == nr2 and a2[0]['versuche'] == 1 and 50 <= a2[0]['faellig'] - time.time() <= 61, a2)
    smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
    dienst()
    check('vor Fälligkeit: kein Versand', not smtp.messages and [j['state'] for j in A.call('bestellung&nr=' + nr2)[1]['order']['outbox']] == ['failed', 'queued'])
    faellig_machen(); code, out = dienst()
    o = A.call('bestellung&nr=' + nr2)[1]['order']
    check('fällig: Team-Mail und danach die Kopie zugestellt', [j['state'] for j in o['outbox']] == ['sent', 'sent'] and until(lambda: len(smtp.messages) == 2, 5)
          and smtp.messages[0]['to'] == ['orders@example.org'], (out, o['outbox']))
    check('nach Erfolg: Warteschlange leer', (doc('postausgang') or {}).get('auftraege') == [])
    # endgültig fehlgeschlagen: nach drei Wiederholungen bleibt der Vorgang zum Nachsenden im Eingabebereich stehen
    smtp.close()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0003', 'positions': [{'id': item['id'], 'qty': 5}]})
    nr3 = r.get('nr')
    for _ in range(4):
        faellig_machen(); dienst()
    o = A.call('bestellung&nr=' + nr3)[1]['order']
    check('nach dem letzten Versuch: kein Auftrag mehr, Vorgang mit offener Mail sichtbar', (doc('postausgang') or {}).get('auftraege') == [] and o['mailPending'] == 2
          and o['outbox'][0]['attempts'] == 4, o['outbox'])
    smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
    j = o['outbox'][0]
    rr = A.call('bestellung_mail_retry', {'nr': nr3, 'jobId': j['id'], 'attempts': j['attempts'], 'confirm': True})
    check('Mitarbeiterseite kann wie bisher nachsenden', rr[0] == 200 and rr[1]['order']['outbox'][0]['state'] == 'sent', rr)

    # unklarer Ausgang (Verbindung nach dem Senden abgebrochen): nie automatisch erneut – nur bestätigt im Eingabebereich
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0007', 'positions': [{'id': item['id'], 'qty': 9}]})
    nr7 = r.get('nr'); dienst()
    def unklar(data):
        for o in data:
            if o['nr'] == nr7:
                o['outbox'][1]['state'] = 'failed'; o['outbox'][1]['attempts'] = 1; o['outbox'][1]['error'] = 'Der Mailserver hat die Verbindung beendet.'
    alle = doc('bestellungen'); unklar(alle); storage_write('bestellungen', alle)
    storage_write('postausgang', {'auftraege': [{'id': 'unklar-0001', 'art': 'bestellung', 't': '2026-11-04T18:00:00Z', 'faellig': 0, 'versuche': 1, 'nr': nr7}]})
    n = len(smtp.messages); dienst()
    j = A.call('bestellung&nr=' + nr7)[1]['order']['outbox'][1]
    check('unklarer Ausgang: kein automatischer Neuversand, Auftrag erledigt', len(smtp.messages) == n and j['state'] == 'failed' and j['attempts'] == 1
          and (doc('postausgang') or {}).get('auftraege') == [], j)

    # ---------- Durchsicht: Vorgang mit offenem Auftrag, aber ohne Eintrag in der Warteschlange ----------
    smtp.messages.clear()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0004', 'positions': [{'id': item['id'], 'qty': 6}]})
    nr4 = r.get('nr')
    storage_write('postausgang', {'auftraege': []})   # wie ein Abbruch zwischen Speichern und Ablegen
    st = doc('postausgang-stand'); st['durchsicht'] = 0; storage_write('postausgang-stand', st)
    dienst()
    check('Durchsicht findet liegengebliebene Versandaufträge', [j['state'] for j in A.call('bestellung&nr=' + nr4)[1]['order']['outbox']] == ['sent', 'sent'])

    # ---------- Oberfläche: Quittung im Kundenportal (Desktop und 390 px) ----------
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        for breite, name in ((1360, 'desktop'), (390, 'mobil')):
            ctx = br.new_context(viewport={'width': breite, 'height': 900}); c = ctx.new_page(); errs = []
            c.on('pageerror', lambda e: errs.append(str(e)))
            c.goto(BASE + '/'); c.wait_for_selector('#btn-kunde-login'); c.click('#btn-kunde-login')
            c.fill('#kl-form [name=username]', 'kantine.post'); c.fill('#kl-form [name=password]', 'Kantine-Kennwort-5'); c.click('#kl-form [type=submit]')
            c.wait_for_selector('#modebar [data-mode=liste]'); c.click('#modebar [data-mode=liste]'); c.wait_for_selector('tr.row .qty')
            q = c.locator(f'#list .qty[data-qty="{item["id"]}"]'); q.fill('2'); q.press('Tab'); c.wait_for_selector('#orderbar:not([hidden])')
            c.click('#orderbar [data-order=open]'); c.wait_for_selector('#dlg-order[open]')
            c.click('#order-body [data-order=send]'); c.wait_for_selector('#order-body .o-done', timeout=10000)
            t = c.inner_text('#order-body')
            check(f'Oberfläche ({name}): Quittung „eingegangen“, Kopie angekündigt', 'ist bei uns eingegangen' in t and 'Eine Kopie senden wir in Kürze an kantine.post@example.org' in t
                  and 'noch nicht bestätigt' not in t, t)
            c.screenshot(path=SH + f'/postausgang-quittung-{name}.png')
            check(f'Oberfläche ({name}): keine Skriptfehler, kein seitliches Scrollen', not errs and c.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), errs)
            ctx.close()
        br.close()

    # ---------- Benachrichtigung (Anmeldesperre auf der Kundenseite) ----------
    check('Benachrichtigung „Sicherheit“ eingeschaltet', A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org'}}})[0] == 200)
    storage_write('benachrichtigung-stand', {})
    smtp.messages.clear()
    X = Client('203.0.113.88')
    for _ in range(5): X.call('kunde_login', {'username': 'kantine.post', 'password': 'falsch-falsch-1'})
    until(lambda: any(a['art'] == 'benachrichtigung' for a in (doc('postausgang') or {}).get('auftraege', [])), 5)   # abgelegt am Ende der Anfrage
    a3 = (doc('postausgang') or {}).get('auftraege', [])
    check('Kundenseite: Sperre nur als Auftrag abgelegt, keine Mail', any(a['art'] == 'benachrichtigung' for a in a3) and not smtp.messages, a3)
    dienst()
    m = [x for x in smtp.messages if x['to'] == ['it@example.org']]
    check('Dienst: Sicherheitsbenachrichtigung mit IP verschickt', len(m) == 1 and 'Anmeldesperre' in m[0]['subject'] and '203.0.113.88' in m[0]['text'], [x['subject'] for x in smtp.messages])

    # ---------- Abmeldehinweis ----------
    A.call('benachrichtigung_save', {'events': {'abmeldung': {'on': True, 'to': 'verkauf@example.org'}}})
    key = bytes(range(32))
    storage_write('abmelde-schluessel', {'key': base64.b64encode(key).decode(), 'created': '2026-10-01T00:00:00Z'})
    tok = kid + '.' + base64.urlsafe_b64encode(hmac.new(key, ('abmelden|' + kid).encode(), hashlib.sha256).digest()).decode().rstrip('=')[:32]
    smtp.messages.clear()
    code, r = Client('198.51.100.41').call('kunde_abmelden', {'token': tok})
    until(lambda: any(a['art'] == 'hinweis' for a in (doc('postausgang') or {}).get('auftraege', [])), 5)
    a4 = (doc('postausgang') or {}).get('auftraege', [])
    hinweis = [a for a in a4 if a['art'] == 'hinweis']
    check('Abmeldung: Hinweis nur abgelegt, mit Firma, ohne Zugangsdaten', code == 200 and len(hinweis) == 1 and hinweis[0]['kunde']['firma'] == 'Kantine Post'
          and set(hinweis[0]['kunde']) <= {'id', 'firma', 'nr', 'email'} and not smtp.messages, a4)
    dienst()
    m = [x for x in smtp.messages if x['to'] == ['verkauf@example.org']]
    check('Dienst: Abmeldehinweis an den Verkauf', len(m) == 1 and 'Kantine Post' in m[0]['text'] and 'abgemeldet' in m[0]['text'], [x['subject'] for x in smtp.messages])

    # ---------- Postfach-Passwort im Eingabebereich: Schlüssel nur auf der Mitarbeiterseite ----------
    r = A.call('mail_konto_save', {'host': '127.0.0.1', 'port': SMTP_PORT, 'secure': 'none', 'user': 'portal@example.org', 'password': 'Test-Postfach-1',
                                   'from': 'angebot@example.org', 'fromName': 'Standard-Fleisch', 'replyTo': '', 'confirm': PW})
    check('Postfach im Eingabebereich hinterlegt', r[0] == 200, r)
    check('Schlüssel liegt im eigenen Ordner, nicht im gemeinsamen Datenordner', os.path.isfile(os.path.join(GEHEIM, 'mail-schluessel.php'))
          and not os.path.exists(os.path.join(DATA, 'mail-schluessel.php')))
    check('gespeichertes Passwort nur verschlüsselt', 'Test-Postfach-1' not in (storage_raw('mailkonto') or ''))
    smtp.messages.clear()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0005', 'positions': [{'id': item['id'], 'qty': 7}]})
    code, out = dienst({**basis, 'WA_URL': BASE, 'WA_GEHEIM_DIR': GEHEIM})   # nur hinterlegtes Postfach, keine Werte aus .env
    check('Dienst entschlüsselt das hinterlegte Postfach (Schlüssel aus WA_GEHEIM_DIR)', until(lambda: len(smtp.messages) == 2, 5), out)
    konto = doc('mailkonto')
    check('Passwort an Server und Benutzer gebunden (Format v2)', konto['passEnc'].startswith('v2:'), konto['passEnc'][:3])
    # Angriff über den gemeinsamen Datenordner: fremden Server eintragen → der Dienst gibt das Passwort nicht heraus
    storage_write('mailkonto', {**konto, 'host': 'smtp.angreifer.example', 'port': 465, 'secure': 'ssl'})
    smtp.messages.clear()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0008', 'positions': [{'id': item['id'], 'qty': 10}]})
    dienst({**basis, 'WA_URL': BASE, 'WA_GEHEIM_DIR': GEHEIM})
    j = A.call('bestellung&nr=' + r['nr'])[1]['order']['outbox'][0]
    check('ausgetauschter Server: Passwort nicht entschlüsselt, keine Anmeldung dort', j['state'] == 'failed' and 'entschlüsselt' in j['error'], j)
    storage_write('mailkonto', konto)
    cli = lambda arg: subprocess.run(['php', os.path.join(APP, 'api', 'postausgang.php'), arg], env=INNEN, capture_output=True, text=True)
    p1 = cli('--entbinden')
    check('Rückweg für ältere Releases: --entbinden stellt auf Format v1', p1.returncode == 0 and doc('mailkonto')['passEnc'].startswith('v1:') and 'Format v1' in p1.stdout, p1.stdout + p1.stderr)
    smtp.messages.clear()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0009', 'positions': [{'id': item['id'], 'qty': 11}]})
    dienst({**basis, 'WA_URL': BASE, 'WA_GEHEIM_DIR': GEHEIM})
    check('Format v1 wird weiter gelesen (Versand klappt)', until(lambda: len(smtp.messages) == 2, 5))
    p2 = cli('--umschluesseln')
    check('--umschluesseln bindet wieder (v2), zweiter Aufruf ändert nichts', p2.returncode == 0 and doc('mailkonto')['passEnc'].startswith('v2:')
          and 'bereits gebunden' in cli('--umschluesseln').stdout, p2.stdout + p2.stderr)
    smtp.messages.clear()
    code, r = K.call('kunde_bestellung', {**payload, 'requestId': 'postausgang-request-0006', 'positions': [{'id': item['id'], 'qty': 8}]})
    code, out = dienst({**basis, 'WA_URL': BASE})   # wie die Kundenseite: ohne Zugang zum Schlüssel
    o = A.call('bestellung&nr=' + r['nr'])[1]['order']
    check('ohne Schlüssel (Kundenseite) kein Versand möglich', not smtp.messages and o['outbox'][0]['state'] == 'failed', o['outbox'])
finally:
    srv.terminate()
    shutil.rmtree(GEHEIM, ignore_errors=True)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
