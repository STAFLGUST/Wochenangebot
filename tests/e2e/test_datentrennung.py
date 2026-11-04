"""Testgruppe datentrennung (ADR-007 Stufe 2): getrennte Daten wie im Betrieb. Der Testlauf trennt die Testdaten vorher mit dem echten
Werkzeug deploy/daten_trennen.py. Der Testserver ist die Kundenseite (kein interner Ordner, Postausgang), ein zweiter PHP-Server auf
dem Hilfsport die Mitarbeiterseite (WA_DATEN_INTERN). Geprüft: Kundenfunktionen laufen vollständig ohne interne Dokumente (keine
einzige Anfrage danach im Serverprotokoll), die Mitarbeiterseite arbeitet mit beiden Ordnern, interne Daten landen nie im gemeinsamen
Ordner, die Kundenseite kann keine Mitarbeiteranmeldung oder Ersteinrichtung nutzen.
Trennstufe 2 (Stufe 2b): Kundendokument geteilt (außen nur Portalfelder), Empfänger, Bestand, Stammdaten, Postfach nur innen; der
Postausgang bestimmt Empfänger und Inhalt selbst und verwirft gefälschte Versandaufträge aus dem gemeinsamen Ordner."""
import base64, hashlib, hmac, json, os, sqlite3, subprocess, sys, time, urllib.error, urllib.request
from kunden_hilfe import Client
from smtp_test import TestSmtp
from umgebung import AUX_PORT, BASE, REPO, SMTP_PORT, WORK, storage_raw, storage_write, until

sys.path.insert(0, os.path.join(REPO, 'deploy'))
import daten_trennen  # noqa: E402

PW = 'Sicheres-Passwort-1'
DATA = os.environ['UDATA']
INTERN = os.environ['UINTERN']
APP = os.path.dirname(DATA)
KS = daten_trennen.kundenseite(stufe=daten_trennen.stufe_lesen(__import__('pathlib').Path(DATA)))
LOG = os.path.join(WORK, 'php-datentrennung.log')
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name)
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


def interne_im_gemeinsamen_ordner():
    """Interne Dokumente, die (fälschlich) im gemeinsamen Ordner liegen – als Datei oder Datenbankzeile"""
    out = []
    for root, _, files in os.walk(DATA):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), DATA)
            if f.endswith('.php') and not rel.startswith(('.', 'geo/')) and f != 'index.php':
                if daten_trennen.ist_intern(rel[:-4], KS): out.append(rel)
    if os.path.isfile(DATA + '/.sqlite-active'):
        with sqlite3.connect(DATA + '/.sqlite/store.sqlite') as c:
            out += [n for (n,) in c.execute('SELECT name FROM documents') if daten_trennen.ist_intern(n, KS)]
    if os.path.isdir(os.path.join(DATA, 'dateien')): out.append('dateien/')
    return out


def spur():
    with open(LOG, encoding='utf-8', errors='replace') as f:
        return [z.strip() for z in f if '[speicher]' in z]


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


basis = {k: v for k, v in os.environ.items() if not k.startswith('MAIL_') and k not in ('WA_URL', 'WA_POSTAUSGANG', 'WA_DATEN_INTERN', 'WA_SPUR_INTERN')}
INNEN = {**basis, 'MAIL_SMTP_HOST': '127.0.0.1', 'MAIL_SMTP_PORT': str(SMTP_PORT), 'MAIL_SMTP_SECURE': 'none', 'MAIL_SMTP_USER': 'portal@example.org',
         'MAIL_SMTP_PASS': 'Test-Postfach-1', 'MAIL_FROM': 'angebot@example.org', 'WA_URL': BASE, 'WA_DATEN_INTERN': INTERN, 'WA_SPUR_INTERN': '1'}
srv = subprocess.Popen(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-S', f'127.0.0.1:{AUX_PORT}'], cwd=APP, env=INNEN,
                       stdout=open(os.path.join(WORK, 'php-datentrennung-innen.log'), 'w'), stderr=subprocess.STDOUT, start_new_session=True)


def dienst():
    p = subprocess.run(['php', os.path.join(APP, 'api', 'postausgang.php')], env=INNEN, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


try:
    until(lambda: subprocess.run(['php', '-r', f'exit(@fsockopen("127.0.0.1", {AUX_PORT}) ? 0 : 1);']).returncode == 0, 10)
    smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
    # ---------- Ausgangslage nach dem Trennen ----------
    check('Kennzeichen der Trennung in beiden Ordnern', os.path.isfile(DATA + '/.daten-getrennt') and os.path.isfile(INTERN + '/.daten-intern'))
    check('keine internen Dokumente im gemeinsamen Ordner', not interne_im_gemeinsamen_ordner(), interne_im_gemeinsamen_ordner()[:5])
    check('Zugang des Administrators liegt im internen Ordner', storage_raw('admin') is not None and not os.path.exists(DATA + '/admin.php'))

    # ---------- Mitarbeiterseite: arbeitet mit beiden Ordnern ----------
    A = Mitarbeiter('198.51.100.2')
    check('Mitarbeiterseite: Anmeldung (Nutzer aus dem internen Ordner)', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
    r = A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
    check('Mitarbeiterseite: neuer Nutzer gespeichert – im internen Ordner', r[0] == 200 and 'erika' in json.dumps(doc('nutzer')) and not interne_im_gemeinsamen_ordner(), r)
    rev = A.call('kunden')[1]['rev']
    r = A.call('kunde_save', {'rev': rev, 'firma': 'Kantine Trennung', 'nr': 'K-DT', 'email': 'kantine.dt@example.org', 'active': True, 'angebote': ['std'],
                              'login': {'username': 'kantine.dt', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
    check('Mitarbeiterseite: Kunde angelegt (gemeinsamer Ordner)', r[0] == 200 and os.path.exists(DATA + '/kunden.php') or os.path.isfile(DATA + '/.sqlite-active'), r)
    kid = r[1]['customer']['id']
    check('Mitarbeiterseite: Bestellfunktion eingeschaltet', A.call('bestell_settings_save', {'enabled': True, 'to': 'orders@example.org', 'copy': True})[0] == 200)
    code, out = dienst()
    check('Postausgang mit internem Ordner: Lebenszeichen', code == 0 and (doc('postausgang-stand') or {}).get('versand') is True, out)
    pub = A.call('draft')[1]['published']; item = pub['items'][0]

    # ---------- Kundenseite: alle Kundenfunktionen ohne interne Dokumente ----------
    vorher = len(spur())
    K = Client('198.51.100.30')
    code, st = K.call('kunde_status')
    check('Kundenseite: Status (Bestellfunktion über das Lebenszeichen des Postausgangs)', code == 200 and st['bestellfunktion'] is True, st)
    code, o = K.call('offer')
    check('Kundenseite: Wochenangebot öffentlich', code == 200 and len((o.get('offer') or {}).get('items', [])) > 0, code)
    X = Client('203.0.113.40')
    check('Kundenseite: falsches Passwort abgewiesen (Anmeldeversuche gezählt)', X.call('kunde_login', {'username': 'kantine.dt', 'password': 'falsch-falsch-1'})[0] == 401)
    check('Kundenseite: Kundenanmeldung', K.call('kunde_login', {'username': 'kantine.dt', 'password': 'Kantine-Kennwort-5'})[0] == 200)
    check('Kundenseite: Angebot des Kunden', K.call('offer&angebot=std')[0] == 200)
    check('Kundenseite: Merkliste speichern und lesen', K.call('kunde_merkliste_save', {'keys': [str(item.get('code') or item['id'])]})[0] == 200 and K.call('kunde_merkliste')[0] == 200)
    payload = {'angebot': 'std', 'publishedAt': pub.get('publishedAt', pub.get('savedAt', '')), 'positions': [{'id': item['id'], 'qty': 2}], 'requestId': 'datentrennung-req-0001'}
    code, q = K.call('kunde_bestellung', payload)
    check('Kundenseite: Bestellwunsch angenommen (eingegangen)', code == 200 and q.get('delivery') == 'eingegangen', q)
    check('Stufe 2: Quittung nennt die Kopie nur mit gekürzter Adresse', q.get('copyPlanned') == 'k•••@example.org', q.get('copyPlanned'))
    o = A.call('bestellung&nr=' + str(q.get('nr')))[1].get('order', {})
    check('Stufe 2: Kundenseite legt nur einen offenen Auftrag an, ohne Empfänger und ohne Anschrift/E-Mail im Schnappschuss',
          [(j['kind'], j['to']) for j in o.get('outbox', [])] == [('offen', '')] and 'email' not in (o.get('kunde') or {}), (o.get('outbox'), o.get('kunde')))
    check('Kundenseite: eigene Bestellwünsche', any(x['nr'] == q.get('nr') for x in K.call('kunde_bestellungen')[1].get('orders', [])))
    check('Kundenseite: Detail des Bestellwunschs', K.call('kunde_bestellung_detail&nr=' + str(q.get('nr')))[0] == 200)
    check('Kundenseite: eigenes Passwort ändern', K.call('kunde_passwort', {'current': 'Kantine-Kennwort-5', 'password': 'Neues-Kennwort-88'})[0] == 200)
    check('Kundenseite: abmelden', K.call('kunde_logout', {})[0] == 200)
    key = bytes(range(32))
    storage_write('abmelde-schluessel', {'key': base64.b64encode(key).decode(), 'created': '2026-10-01T00:00:00Z'})
    tok = kid + '.' + base64.urlsafe_b64encode(hmac.new(key, ('abmelden|' + kid).encode(), hashlib.sha256).digest()).decode().rstrip('=')[:32]
    P = Client('198.51.100.41')
    check('Kundenseite: Abmeldelink aus der Angebotsmail', P.call('kunde_abmelden_info', {'token': tok})[0] == 200 and P.call('kunde_abmelden', {'token': tok})[0] == 200)
    check('Kundenseite: Grunddaten für die App', Client().call('app_info')[0] == 200)
    check('Kundenseite: Passwort-Link ungültig (410)', Client().call('kunde_token_check', {'token': 'x' * 40})[0] == 410)
    check('Kundenseite: Falle für Angriffswerkzeuge (404)', Client('203.0.113.41').call('waf_probe&p=wp-login.php')[0] == 404)
    monat = time.strftime('%Y-%m', time.gmtime())
    check('Kundenseite: Protokoll wird weiter geschrieben (Anmeldung, Bestellwunsch, Abmeldung)', {'kunde_login', 'kunde_login_fail', 'bestellung', 'kunde_abmeldung'}
          <= {e.get('a') for e in (doc('protokoll/' + monat) or [])}, sorted({e.get('a') for e in (doc('protokoll/' + monat) or [])}))
    neu = spur()[vorher:]
    check('Kundenseite: keine einzige Anfrage nach internen Dokumenten (Serverprotokoll)', not neu, neu[:8])
    check('Kundenseite: nichts Internes in den gemeinsamen Ordner geschrieben', not interne_im_gemeinsamen_ordner(), interne_im_gemeinsamen_ordner()[:5])

    # ---------- Postausgang verschickt (Versandprotokoll intern) ----------
    code, out = dienst()
    check('Postausgang: Bestellwunsch und Abmeldehinweis verschickt', until(lambda: any(m['to'] == ['orders@example.org'] for m in smtp.messages), 5), out)
    check('Versandprotokoll im internen Ordner', any(x.get('by') == 'Postausgang' for x in (doc('mailversand') or [])) and not os.path.exists(DATA + '/mailversand.php'))

    # ---------- Stufe 2: Teilung, Empfänger und Inhalt nur von innen ----------
    check('Trennstufe 2 im Kennzeichen', open(DATA + '/.daten-getrennt').read().strip() == '2')
    felder = set(daten_trennen.kunden_felder())
    kd = doc('kunden')
    check('gemeinsames Kundendokument nur mit Portalfeldern (keine Adresse, keine Warenwirtschaft)', all(set(c) <= felder for c in kd['customers'])
          and 'kantine.dt@example.org' not in json.dumps(kd) and any(c.get('emailMaske') == 'k•••@example.org' for c in kd['customers']), [sorted(set(c) - felder) for c in kd['customers']][:3])
    check('Stammdaten der Kunden im internen Dokument kundenstamm', (doc('kundenstamm') or {}).get('customers', {}).get(kid, {}).get('email') == 'kantine.dt@example.org')
    check('Bestell-Einstellungen außen ohne Adressen, innen die Empfänger', 'orders@example.org' not in json.dumps(doc('bestellung')) and doc('bestellung').get('empfaenger') == 1
          and doc('bestellung-empfaenger')['to'] == ['orders@example.org'])
    storage_write('bestand', {'date': '2026-11-02', 'articles': [{'code': '0815', 'name': 'Test', 'kg': 12.5, 'mhd': '2026-12-01', 'lots': [{'lot': 'P-77', 'kg': 12.5, 'ek': 4.2}]},
                                                                {'code': '0999', 'name': 'Leer', 'kg': 0}], 'incoming': []})
    storage_write('stammdaten', {'rev': 1, 'articles': [{'code': '0815', 'name': 'Test', 'category': 'Rind', 'origin': 'DE', 'condition': 'frisch', 'gtin': '4000000000001'}]})
    check('Bestand und Stammdaten liegen innen', os.path.isfile(INTERN + '/.sqlite-active') or os.path.isfile(INTERN + '/bestand.php') and not os.path.exists(DATA + '/bestand.php'))
    dienst()
    a = doc('artikelauszug')
    check('Auszug für die Kundenseite (vom Postausgang erzeugt) ohne Mengen, Partien, MHD und Einkaufspreise', a is not None and a.get('lager') == ['815']
          and a.get('merkmale') == {'815': {'category': 'Rind', 'origin': 'DE', 'condition': 'frisch'}}
          and not any(x in json.dumps(a) for x in ('12.5', '4.2', 'P-77', '2026-12-01', '4000000000001')), str(a)[:300])
    o = A.call('bestellung&nr=' + str(q.get('nr')))[1].get('order', {})
    check('Postausgang: Aufträge je Empfänger aus den internen Daten, Schnappschuss ergänzt', sorted((j['kind'], j['to'], j['state']) for j in o.get('outbox', []))
          == [('bestellkopie', 'kantine.dt@example.org', 'sent'), ('bestellung', 'orders@example.org', 'sent')] and (o.get('kunde') or {}).get('email') == 'kantine.dt@example.org', o.get('outbox'))
    team = [m for m in smtp.messages if m['to'] == ['orders@example.org']]
    check('Team-Mail mit Adresse des Kunden aus den Stammdaten', team and 'kantine.dt@example.org' in team[-1]['text'], team[-1]['text'][:300] if team else None)
    # gefälschte Versandaufträge im gemeinsamen Ordner (wie von einer übernommenen Kundenseite) – nichts davon darf hinaus
    alle = json.loads(storage_raw('bestellungen').split('?>\n', 1)[-1])
    echt = next(x for x in alle if x['nr'] == q.get('nr'))
    falsch = {**echt, 'nr': 'B-2099-9999', 'requestId': 'gefaelscht-0001', 'outbox': [
        {'id': 'f1', 'kind': 'bestellung', 'to': 'angreifer@example.net', 'state': 'queued', 'attempts': 0, 'error': '', 'history': [], 'subject': 'Phish', 'text': 'Phish', 'html': 'Phish'},
        {'id': 'f3', 'kind': 'bestellung', 'to': 'orders@example.org', 'state': 'queued', 'attempts': 0, 'error': '', 'history': [], 'subject': 'Phish-Betreff', 'text': 'Phish-Text', 'html': 'Phish-Text'},
        {'id': 'f2', 'kind': 'bestellkopie', 'to': 'opfer@example.net', 'state': 'queued', 'attempts': 0, 'error': '', 'history': [], 'subject': 'Phish', 'text': 'Phish', 'html': 'Phish'}]}
    storage_write('bestellungen', alle + [falsch])
    storage_write('postausgang', {'auftraege': [
        {'id': 'p1', 'art': 'bestellung', 'nr': 'B-2099-9999', 't': '2026-11-04T00:00:00Z', 'faellig': 0, 'versuche': 0},
        {'id': 'p2', 'art': 'hinweis', 'kunde': {'id': kid, 'firma': 'Gefälscht AG', 'email': 'angreifer@example.net'}, 'ab': True, 't': '2026-11-04T00:00:00Z', 'faellig': 0, 'versuche': 0},
        {'id': 'p3', 'art': 'benachrichtigung', 'items': [{'ev': 'abmeldung', 'title': 'Phish-Ereignis', 'facts': [], 't': '2026-11-04T00:00:00Z'}], 't': '2026-11-04T00:00:00Z', 'faellig': 0, 'versuche': 0}]})
    vorher_n = len(smtp.messages)
    code, out = dienst()
    neu_m = smtp.messages[vorher_n:]
    empf = [r for m in neu_m for r in m['to']]
    check('gefälschte Empfänger erhalten nichts', not {'angreifer@example.net', 'opfer@example.net'} & set(empf), empf)
    check('gefälschter Inhalt wird nicht verschickt (Team-Mail neu aus dem Vorgang)', not any('Phish' in m['subject'] + m['text'] for m in neu_m)
          and any(m['to'] == ['orders@example.org'] and 'B-2099-9999' in m['subject'] for m in neu_m), [(m['to'], m['subject']) for m in neu_m])
    o = A.call('bestellung&nr=B-2099-9999')[1].get('order', {})
    st = {j['id']: (j['state'], j['error']) for j in o.get('outbox', [])}
    check('verworfene Aufträge stehen mit Grund beim Vorgang', st.get('f1', ('',))[0] == 'failed' and 'verworfen' in st['f1'][1]
          and st.get('f2', ('',))[0] == 'failed' and 'Stammdaten' in st['f2'][1] and st.get('f3', ('',))[0] == 'sent', st)
    check('verworfene Aufträge im Protokoll als Sicherheitsereignis', any(e.get('a') == 'security' and 'verworfen' in e.get('s', '') for e in (doc('protokoll/' + monat) or [])))
    hinweis = [m for m in neu_m if 'Abmeldung' in m['subject']]
    check('Abmeldehinweis nur mit Daten aus den Stammdaten (nicht aus dem Auftrag)', hinweis and 'Kantine Trennung' in hinweis[0]['subject']
          and 'Gefälscht' not in hinweis[0]['text'] and 'angreifer' not in hinweis[0]['text'], [(m['subject']) for m in neu_m])
    check('Benachrichtigung einer Art, die die Kundenseite nicht auslöst, wird verworfen', not any('Phish-Ereignis' in m['subject'] for m in neu_m))
    # Originalempfänger: nach einer Änderung der Empfänger geht ein älterer Auftrag weiter an den früheren Empfänger (nicht an beliebige)
    check('Empfänger ändern (Mitarbeiterseite)', A.call('bestell_settings_save', {'enabled': True, 'to': 'neu-team@example.org', 'copy': True})[0] == 200
          and doc('bestellung-empfaenger').get('frueher') == ['orders@example.org'] and 'neu-team' not in json.dumps(doc('bestellung')))
    alle = json.loads(storage_raw('bestellungen').split('?>\n', 1)[-1])
    alt = {**echt, 'nr': 'B-2099-9998', 'requestId': 'gefaelscht-0002', 'outbox': [
        {'id': 'g1', 'kind': 'bestellung', 'to': 'orders@example.org', 'state': 'queued', 'attempts': 0, 'error': '', 'history': []},
        {'id': 'g2', 'kind': 'bestellung', 'to': 'sonstwer@example.org', 'state': 'queued', 'attempts': 0, 'error': '', 'history': []}]}
    storage_write('bestellungen', alle + [alt])
    storage_write('postausgang', {'auftraege': [{'id': 'p4', 'art': 'bestellung', 'nr': 'B-2099-9998', 't': '2026-11-04T00:00:00Z', 'faellig': 0, 'versuche': 0}]})
    vorher_n = len(smtp.messages); dienst()
    empf = [r for m in smtp.messages[vorher_n:] for r in m['to']]
    check('früherer Empfänger erhält den älteren Auftrag, ein unbekannter nicht', empf == ['orders@example.org'], empf)

    # ---------- Kundenseite: keine Mitarbeiteranmeldung, keine Ersteinrichtung ----------
    S = Client('198.51.100.50')
    code, r = S.call('login', {'username': 'admin', 'password': PW})
    check('Kundenseite: Mitarbeiteranmeldung scheitert (Nutzer nicht lesbar)', code != 200, (code, r))
    code, r = S.call('setup', {'username': 'eindringling', 'password': 'Angreifer-Kennwort-77', 'name': 'X'})
    check('Kundenseite: Ersteinrichtung legt nichts an', code != 200 and 'eindringling' not in json.dumps(doc('nutzer')) and not interne_im_gemeinsamen_ordner(), (code, r))
    check('Mitarbeiterseite: Anmeldung danach unverändert', Mitarbeiter('198.51.100.3').call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})[0] == 200)
    innen = [z for z in open(os.path.join(WORK, 'php-datentrennung-innen.log'), encoding='utf-8', errors='replace') if '[speicher]' in z]
    check('Mitarbeiterseite: keine öffentliche Aktion mit internen Dokumenten', not innen, innen[:5])
finally:
    srv.terminate()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
