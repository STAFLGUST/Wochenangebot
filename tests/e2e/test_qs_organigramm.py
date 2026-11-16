"""Qualitätssicherung – Organigramm im QM-System (app/api/module/qs/organigramm.php, Aktion qs_organigramm_save, Oberfläche
app/module/qs/organigramm.js).

Geprüft über die Schnittstelle: Rechte (ohne Anmeldung 401, ohne QM-Recht und nur „ansehen“ 403, nur per POST); Anlegen im
Entwurf (Struktur, Bearbeiter, Verlauf, unverändert speichern ändert nichts); Grenzen und Fehler (Zyklus, sich selbst
untergeordnet, fehlende übergeordnete Stelle, Stabsstelle ohne Linie bzw. mit Unterstellen, unbekannte Person, doppelte bzw.
ungültige Kennung, Textlängen, höchstens 300 Stellen und 10 Personen, leer, veralteter Stand 409); nur im Entwurf (in
Prüfung, ohne Entwurf und nach der Freigabe 409, Ordner 422); 4-Augen-Prinzip (wer am Organigramm ändert, prüft nicht);
Freigabe legt die PDF-Fassung ab (Kopf, Kästen, Lenkungsangaben im Fuß) und hält die Namen fest; die freigegebene Version
bleibt bei geänderten Personen unverändert (Struktur, Namen, PDF); „Überarbeitung beginnen“ übernimmt die Struktur ohne
Namen und ohne PDF; zweite Freigabe ersetzt die erste, die erste bleibt unverändert; Protokoll.
Oberfläche: Karte im Dokument, Leer-Zustand mit Vorschlag „Geschäftsführung“, Stellen anlegen, Personen, Vertretung,
Stabsstelle, Verschieben, Löschen, Speichern; Ansicht ohne Bearbeiten-Recht nur mit der gültigen Version und PDF;
Gliederung auf dem Handy; 1280/390 px hell und dunkel ohne waagerechtes Scrollen der Seite, keine JavaScript-Fehler.
Nur erfundene Testdaten.
"""
import datetime
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B, API
from umgebung import SH

HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
HEUTE = datetime.date.today()
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:500]) if i else ''))


def de(iso):
    return f'{iso[8:10]}.{iso[5:7]}.{iso[0:4]}'


def roh(cli, query):
    """GET ohne JSON-Auswertung: (Status, Kopfzeilen, Inhalt)"""
    req = urllib.request.Request(API + query, headers={'X-Forwarded-For': cli.ip, **cli.headers})
    try:
        r = cli.http.open(req)
    except urllib.error.HTTPError as e:
        r = e
    return r.code, {k.lower(): v for k, v in r.headers.items()}, r.read()


def pdf_text(raw):
    """Text aus den (komprimierten) Seiteninhalten des PDF-Erzeugers: (…) Tj, WinAnsi – je Seite eine Liste von Zeilen"""
    seiten = []
    for m in re.finditer(rb'stream\n(.*?)\nendstream', raw, re.S):
        try:
            s = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        seiten.append([re.sub(rb'\\(.)', rb'\1', t.group(1)).decode('cp1252') for t in re.finditer(rb'\(((?:\\.|[^\\)])*)\) Tj', s)])
    return seiten


# ── Nutzer und Grunddaten ──
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': 'Sicheres-Passwort-1'})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten', 'qs.freigeben']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, V, O, N = K['lisa'], K['bernd'], K['quinn'], K['vera'], K['otto'], Client('198.51.100.40')
check('Datenpaket (erfunden) übernommen', V.call('qs_import', {'paket': json.load(open(PAKET_DATEI, encoding='utf-8')), 'ersetzen': True})[0] == 200)
start = V.call('qs_start')[1]
PERSONEN = start['personen'] + [{'id': 'HT', 'name': 'Hanna Team', 'funktion': 'HACCP-Teamleitung'}, {'id': 'FD', 'name': 'Fiete Defense', 'funktion': 'Food Defense'}]
st, r = V.call('qs_stamm_save', {'kapitel': start['kapitel'] + [{'id': '1.2', 'titel': 'Geschäftsleitung'}], 'personen': PERSONEN})
check('Kapitel 1.2 und zwei Personen ergänzt', st == 200 and len(r['personen']) == 6, r)
st, r = Be.call('qs_dokument_save', {'kapitel': '1.2', 'art': 'L', 'nr': '1.2-L02', 'titel': 'Organigramm', 'aenderungen': 'Neu angelegt'})
DOK = r.get('dokument', {})
check('gelenktes Dokument 1.2-L02 mit Entwurf angelegt', st == 200 and DOK['nr'] == '1.2-L02' and DOK['versionen'][0]['status'] == 'entwurf', r)


def dok(cli=L, did=None):
    return {x['id']: x for x in cli.call('qs_start')[1]['dokumente']}[did or DOK['id']]


def knoten(id_, titel, ueber='', art='linie', personen=(), vertretung='', hinweis=''):
    return {'id': id_, 'titel': titel, 'ueber': ueber, 'art': art, 'personen': list(personen), 'vertretung': vertretung, 'hinweis': hinweis}


def speichern(cli, liste, d=None):
    d = d or dok()
    return cli.call('qs_organigramm_save', {'dokument': d['id'], 'rev': d['rev'], 'organigramm': {'knoten': liste}})


STRUKTUR = [knoten('gf', 'Geschäftsführung', personen=['GF'], vertretung='QB'),
            knoten('qmb', 'Qualitätsmanagementbeauftragte', 'gf', 'stab', ['QB'], 'QV'),
            knoten('haccp', 'HACCP-Teamleitung', 'gf', 'stab', ['HT']),
            knoten('fd', 'Food Defense', 'gf', 'stab', ['FD']),
            knoten('asi', 'Fachkraft für Arbeitssicherheit', 'gf', 'stab', hinweis='extern'),
            knoten('ek', 'Einkauf', 'gf', personen=['EK']),
            knoten('qs', 'Qualitätssicherung', 'gf', personen=['QB', 'QV']),
            knoten('lager', 'Lager und Versand', 'gf'),
            knoten('kom', 'Kommissionierung', 'lager')]

# ── Rechte ──
check('ohne Anmeldung 401, ohne QM-Recht 403, nur ansehen 403', N.call('qs_organigramm_save', {'dokument': DOK['id']})[0] == 401
      and speichern(O, STRUKTUR, DOK)[0] == 403 and speichern(L, STRUKTUR, DOK)[0] == 403)
check('nur per POST (405)', Be.call('qs_organigramm_save')[0] == 405)

# ── Anlegen im Entwurf ──
st, r = speichern(Be, STRUKTUR)
v = r.get('dokument', {}).get('versionen', [{}])[0]
check('angelegt: Struktur im Entwurf, Reihenfolge wie gesendet, ohne Namens-Schnappschuss', st == 200 and [k['id'] for k in v['organigramm']['knoten']] == [k['id'] for k in STRUKTUR]
      and v['organigramm']['knoten'][6]['personen'] == ['QB', 'QV'] and 'namen' not in v['organigramm'], r)
check('Verlauf und Bearbeiter', 'Organigramm angelegt (9 Stellen)' in v['verlauf'][-1]['was'] and len(v['bearbeiter']) == 1, v['verlauf'][-1])
rev = dok()['rev']
st, r = speichern(Be, STRUKTUR)
check('unverändert speichern: 200, Stand bleibt', st == 200 and dok()['rev'] == rev)
check('alle mit „QM ansehen“ sehen die Struktur in qs_start', len(dok(L)['versionen'][0]['organigramm']['knoten']) == 9)


def fehler_bei(name, liste, teil):
    st, r = speichern(Be, liste)
    check(f'abgelehnt: {name} (422)', st == 422 and teil in r.get('error', ''), (st, r.get('error')))


fehler_bei('Zyklus', STRUKTUR + [knoten('a', 'A', 'b'), knoten('b', 'B', 'a')], 'selbst untergeordnet')
fehler_bei('Stelle unter sich selbst', STRUKTUR + [knoten('a', 'A', 'a')], 'selbst untergeordnet')
fehler_bei('übergeordnete Stelle fehlt', STRUKTUR + [knoten('a', 'A', 'nichtda')], 'übergeordnete Stelle fehlt')
fehler_bei('Stabsstelle ohne Linie', STRUKTUR + [knoten('a', 'A', '', 'stab')], 'braucht eine übergeordnete')
fehler_bei('Stelle unter einer Stabsstelle', STRUKTUR + [knoten('a', 'A', 'qmb')], 'keine untergeordneten')
fehler_bei('unbekannte Person', STRUKTUR + [knoten('a', 'A', 'gf', personen=['XX'])], '„XX“ steht nicht in den Personen')
fehler_bei('unbekannte Vertretung', STRUKTUR + [knoten('a', 'A', 'gf', vertretung='XX')], 'Vertretung')
fehler_bei('Kennung doppelt', STRUKTUR + [knoten('gf', 'Doppelt')], 'doppelt')
fehler_bei('Kennung ungültig', STRUKTUR + [knoten('A-1', 'X')], 'ungültige Kennung')
fehler_bei('Stelle ohne Namen', STRUKTUR + [knoten('a', ' ')], 'benennen')
fehler_bei('Stelle mit 121 Zeichen', STRUKTUR + [knoten('a', 'x' * 121)], 'höchstens 120')
fehler_bei('Hinweis mit 201 Zeichen', STRUKTUR + [knoten('a', 'A', hinweis='x' * 201)], 'höchstens 200')
fehler_bei('unbekannte Art', STRUKTUR + [knoten('a', 'A', 'gf', 'quer')], 'Art')
fehler_bei('11 Personen', STRUKTUR + [knoten('a', 'A', personen=['GF'] * 11)], 'höchstens 10 Personen')
fehler_bei('301 Stellen', [knoten(f'k{i}', f'Stelle {i}') for i in range(301)], 'höchstens 300')
fehler_bei('keine Stelle', [], 'mindestens eine Stelle')
check('300 Stellen sind erlaubt', speichern(Be, [knoten('gf', 'GF')] + [knoten(f'k{i}', f'Stelle {i}', 'gf') for i in range(299)])[0] == 200)
check('veralteter Stand: 409', Be.call('qs_organigramm_save', {'dokument': DOK['id'], 'rev': 1, 'organigramm': {'knoten': STRUKTUR}})[0] == 409)
check('zurück auf die Struktur', speichern(Be, STRUKTUR)[0] == 200)
ordner = next(x for x in start['dokumente'] if x['art'] == 'O')
gueltig = next(x for x in start['dokumente'] if x['nr'] == '1.4-A01')
check('Ordner: 422; gültiges Dokument ohne Entwurf: 409', speichern(Be, STRUKTUR, dok(did=ordner['id']))[0] == 422 and speichern(Be, STRUKTUR, dok(did=gueltig['id']))[0] == 409)

# ── 4-Augen-Prinzip und Freigabe ──
ge = [dict(k) for k in STRUKTUR]; ge[7]['personen'] = ['EK']
st, r = speichern(V, ge)
check('zweite Person ändert: zählt als Bearbeiter', st == 200 and len(r['dokument']['versionen'][0]['bearbeiter']) == 2)
check('zur Prüfung gegeben', Be.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'einreichen'})[0] == 200)
check('in Prüfung: Organigramm nicht mehr änderbar (409)', speichern(Be, STRUKTUR)[0] == 409)
st, r = V.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'pruefen_freigeben'})
check('wer am Organigramm geändert hat, prüft nicht (4-Augen, 403)', st == 403 and '4-Augen' in r.get('error', ''), r)
st, r = Q.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'pruefen_freigeben'})
v1 = r.get('dokument', {}).get('versionen', [{}])[0]
pdfs = [f for f in v1.get('dateien', []) if f.get('organigramm')]
check('freigegeben als Version 1 mit genau einer PDF-Fassung', st == 200 and v1['status'] == 'freigegeben' and v1['nr'] == 1 and len(pdfs) == 1
      and pdfs[0]['name'] == '1.2-L02 Organigramm - Version 1.pdf' and pdfs[0]['mime'] == 'application/pdf', v1.get('dateien'))
check('Namens-Schnappschuss bei der Freigabe (alle Kürzel)', v1['organigramm']['namen'] == {'GF': 'Geschäftsführung', 'QB': 'Quinn Beispiel', 'QV': 'Vera Vertretung', 'HT': 'Hanna Team',
                                                                                          'FD': 'Fiete Defense', 'EK': 'Emil Einkauf'}, v1['organigramm'].get('namen'))
st, kopf, inhalt = roh(L, f'qs_datei&id={pdfs[0]["id"]}')
text = pdf_text(inhalt)
open(os.path.join(SH, 'qs_organigramm_version1.pdf'), 'wb').write(inhalt)
zeilen = text[0] if text else []
check('PDF mit „QM ansehen“ ladbar, eine Seite mit Logo', st == 200 and inhalt[:5] == b'%PDF-' and len(text) == 1 and b'/Subtype /Image' in inhalt and kopf['content-type'] == 'application/pdf', (st, len(text)))
check('PDF-Kopf: Titel und Nummer', 'Organigramm' in zeilen and any(z.startswith('1.2-L02') for z in zeilen), zeilen[:4])
fuss = zeilen[zeilen.index('Dokument-Nr.'):][:12] if 'Dokument-Nr.' in zeilen else []
check('PDF-Fuß: Lenkungsangaben Nr., Version, Datum, erstellt, geprüft, freigegeben', fuss == ['Dokument-Nr.', '1.2-L02', 'Version', '1', 'Datum', de(HEUTE.isoformat()), 'Erstellt', 'Bernd Bearbeiter',
      'Geprüft', 'Quinn QMB', 'Freigegeben', 'Quinn QMB'], fuss)
check('PDF-Kästen: Stellen, Personen, Vertretung, unbesetzt, Hinweis; lange Wörter ungetrennt', all(x in zeilen for x in ('Geschäftsführung', 'Quinn Beispiel', 'Vertretung: Vera Vertretung',
      'Lager und Versand', 'unbesetzt', 'extern', 'Kommissionierung', 'Food Defense', 'Qualitätsmanagementbeauftragte')), zeilen)
check('nach der Freigabe nicht mehr änderbar (409)', speichern(Be, STRUKTUR)[0] == 409)

# ── Unveränderlich bei geänderten Personen ──
stamm = V.call('qs_start')[1]
pers = [dict(p, name='Quinn Umbenannt') if p['id'] == 'QB' else p for p in stamm['personen'] if p['id'] != 'FD']
check('Person umbenannt, eine andere entfernt', V.call('qs_stamm_save', {'personen': pers})[0] == 200)
v1n = dok()['versionen'][0]
st, _, inhalt2 = roh(L, f'qs_datei&id={pdfs[0]["id"]}')
check('freigegebene Version unverändert: Struktur, Namen, PDF', v1n['organigramm'] == v1['organigramm'] and hashlib.sha256(inhalt2).hexdigest() == pdfs[0]['sha256'] == hashlib.sha256(inhalt).hexdigest())

# ── Neue Version übernimmt die Struktur ──
st, r = Be.call('qs_version_save', {'dokument': DOK['id'], 'rev': dok()['rev'], 'aenderungen': 'Lager neu besetzt', 'grund': 'Personalwechsel', 'dateien': True})
v2 = r.get('dokument', {}).get('versionen', [{}, {}])[1]
check('Überarbeitung: Struktur übernommen, ohne Namen und ohne PDF', st == 200 and v2['status'] == 'entwurf' and v2['organigramm']['knoten'] == v1['organigramm']['knoten']
      and 'namen' not in v2['organigramm'] and not v2.get('dateien'), v2)
check('entfernte Person im Entwurf: Speichern nennt sie (422)', 'FD' in speichern(Be, v2['organigramm']['knoten'])[1].get('error', ''))
neu = [k for k in v2['organigramm']['knoten'] if k['id'] != 'fd']
neu[-1] = dict(neu[-1], titel='Kommissionierung und Verladung')
check('Entwurf geändert', speichern(Be, neu)[0] == 200)
check('eingereicht', Be.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'einreichen'})[0] == 200)
st, r = Q.call('qs_version_schritt', {'dokument': DOK['id'], 'rev': dok()['rev'], 'schritt': 'pruefen_freigeben'})
d2 = r.get('dokument', {})
v1e, v2f = d2['versionen'][0], d2['versionen'][1]
check('Version 2 gültig mit neuem Namen, Version 1 ersetzt und unverändert', st == 200 and v2f['nr'] == 2 and v2f['organigramm']['namen']['QB'] == 'Quinn Umbenannt' and v1e['status'] == 'ersetzt'
      and v1e['organigramm'] == v1['organigramm'] and len([f for f in v2f['dateien'] if f.get('organigramm')]) == 1, v2f.get('organigramm', {}).get('namen'))
st, _, inhalt3 = roh(L, f'qs_datei&id={[f for f in v2f["dateien"] if f.get("organigramm")][0]["id"]}')
z3 = pdf_text(inhalt3)[0]
check('PDF der Version 2: neuer Name, geänderte Stelle (umbrochen), Version 2, ohne die entfernte Stelle', 'Quinn Umbenannt' in z3 and 'Kommissionierung und Verladung' in ' '.join(z3)
      and z3[z3.index('Version') + 1] == '2' and 'Food Defense' not in z3, z3)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Organigramm angelegt und geändert, Version 2 freigegeben', all(t in log for t in ('Organigramm in 1.2-L02 Organigramm angelegt', 'Organigramm in 1.2-L02 Organigramm geändert',
      '1.2-L02 Organigramm – Version 2 freigegeben')))

# ── Oberfläche ──
pers = [dict(p, name='Quinn Neu') if p['id'] == 'QB' else p for p in V.call('qs_start')[1]['personen']]
assert V.call('qs_stamm_save', {'personen': pers})[0] == 200
st, r = Be.call('qs_dokument_save', {'kapitel': '1.2', 'art': 'L', 'nr': '', 'titel': 'Organisationsplan Lager', 'aenderungen': 'Neu angelegt'})
PLAN = r['dokument']['id']


def baum(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#og-baum .og-kasten')].map((k) => k.querySelector('b').textContent)")


with sync_playwright() as pw:
    br = pw.chromium.launch()

    def anmelden(user, pw_, ip, breite=1280, thema='light', hoehe=900):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw_); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/qs/#dokumente'); pg.wait_for_selector('#qm-app:not([hidden])')
        return ctx, pg

    def oeffne_dok(pg, did):
        pg.evaluate('(id) => window.STAFL_QS.oeffneDok(id)', did)
        pg.wait_for_selector(f'#qm-dk[data-dok="{did}"] h2')

    # nur „QM ansehen“: gültige Version mit Namen aus dem Schnappschuss, PDF, Drucken
    ctx, pg = anmelden('lisa', 'Leserin-Konto-12', '198.51.100.10')
    pg.click(f'#qm-d-liste tr[data-dok="{DOK["id"]}"]'); pg.wait_for_selector('#qm-dk .og-karte')
    check('ansehen: Karte mit gültiger Version, ohne Bearbeiten', 'Version 2: 8 Stellen' in pg.text_content('#qm-dk .og-karte') and pg.locator('#qm-dk [data-og]').count() == 1
          and pg.get_attribute('#qm-dk [data-og]', 'data-og') == 'ansehen', pg.text_content('#qm-dk .og-karte'))
    pg.click('#qm-dk [data-og="ansehen"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
    t = pg.text_content('#og-baum')
    check('ansehen: Diagramm der Version 2, Namen aus der Freigabe (nicht der heutige Name)', len(baum(pg)) == 8 and baum(pg)[0] == 'Geschäftsführung' and 'Quinn Umbenannt' in t
          and 'Quinn Neu' not in t and 'unbesetzt' in t and 'Vertretung: Vera Vertretung' in t and 'extern' in t, t[:300])
    check('ansehen: Stabsstellen seitlich an der Linie, Unterstellen darunter', pg.locator('#og-baum .og-stabzeile .og-stabkasten').count() == 3
          and pg.locator('#og-baum .og-kinder > .og-k').count() == 4 and 'Version 2 gültig seit' in pg.text_content('#og-sub'))
    check('ansehen: keine Seitenleiste, kein Speichern, Kästen nicht wählbar, PDF vorhanden', pg.is_hidden('#og-seite') and pg.is_hidden('#og-fuss')
          and pg.locator('#og-baum button').count() == 0 and pg.is_visible('#og-pdf'))
    lage = pg.evaluate("""() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
      const gf = r('#og-baum .og-wurzeln > .og-k > .og-kasten'), l = r('#og-baum .og-l .og-kasten'), rr = r('#og-baum .og-r .og-kasten'), k = r('#og-baum .og-kinder .og-kasten');
      return { links: l.right <= gf.left + gf.width / 2, rechts: rr.left >= gf.left + gf.width / 2, unter: k.top > rr.bottom }; }""")
    check('Lage: Stabsstelle links und rechts der Mitte, Linie darunter', all(lage.values()), lage)
    with pg.expect_download() as dl:
        pg.click('#og-pdf')
    check('PDF-Fassung über das Fenster geladen', dl.value.suggested_filename == '1.2-L02 Organigramm - Version 2.pdf' and open(dl.value.path(), 'rb').read(5) == b'%PDF-', dl.value.suggested_filename)
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_ansehen_1280_light.png'))
    pg.evaluate('() => { window.print = () => {}; }')
    pg.click('#og-druck')
    check('Drucken: Diagramm ohne Bedienelemente im Druckbereich', pg.locator('#print-root .og-kasten').count() == 8 and pg.locator('#print-root button').count() == 0
          and '1.2-L02 Organigramm' in pg.text_content('#print-root .og-druck-kopf'))
    pg.emulate_media(media='print')
    check('Druckansicht: nur der Druckbereich sichtbar', pg.is_visible('#print-root .og-kasten') and pg.is_hidden('#qm-app'))
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_druck.png'), full_page=True)
    pg.emulate_media(media='screen')
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    ctx.close()

    # bearbeiten: Leer-Zustand, Stellen anlegen, Personen, Stabsstelle, Verschieben, Löschen, Speichern
    ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    oeffne_dok(pg, PLAN)
    check('Entwurf ohne Organigramm: Angebot „im System zeichnen“', pg.is_visible('#qm-dk [data-og="bearbeiten"]') and 'im System zeichnen' in pg.text_content('#qm-dk .og-karte'))
    oeffne_dok(pg, DOK['id'])
    check('gültiges Organigramm ohne Entwurf: nur ansehen (Überarbeitung über die Lenkung)', pg.locator('#qm-dk [data-og]').count() == 1 and pg.is_visible('#qm-dk [data-og="ansehen"]'))
    oeffne_dok(pg, PLAN)
    pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-leer')
    check('Leer-Zustand: „Noch kein Organigramm – Stelle anlegen“ mit Vorschlag Geschäftsführung', 'Noch kein Organigramm – Stelle anlegen' in pg.text_content('#og-baum')
          and pg.input_value('#og-erste') == 'Geschäftsführung' and pg.is_disabled('#og-speichern'))
    pg.click('[data-og-tat="erste"]'); pg.wait_for_selector('#og-baum .og-kasten.gewaehlt')
    check('oberste Stelle angelegt und gewählt, Felder sichtbar, „Stabsstelle“ als Art nicht wählbar', baum(pg) == ['Geschäftsführung'] and pg.input_value('#og-titel-in') == 'Geschäftsführung'
          and pg.locator('#og-art option').count() == 1 and pg.is_enabled('#og-speichern'))
    pg.select_option('#og-pers-neu', 'GF'); pg.select_option('#og-vertretung', 'QV')
    pg.wait_for_function("() => document.querySelector('#og-baum .og-kasten').textContent.includes('Vertretung: Vera Vertretung')")
    pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Vertrieb')
    pg.locator('#og-liste [data-og-knoten]').first.click(); pg.click('[data-og-tat="stab"]'); pg.fill('#og-titel-in', 'Qualitätsmanagementbeauftragte'); pg.select_option('#og-pers-neu', 'QB')
    pg.locator('#og-liste [data-og-knoten]').first.click(); pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Einkauf')
    check('Stabsstelle ohne „Untergeordnete Stelle“, Diagramm folgt der Eingabe', pg.locator('#og-baum .og-stabkasten').count() == 1 and baum(pg) == ['Geschäftsführung', 'Qualitätsmanagementbeauftragte', 'Vertrieb', 'Einkauf'], baum(pg))
    pg.click('[data-og-tat="links"]')
    check('„Nach links“ tauscht Einkauf und Vertrieb', baum(pg) == ['Geschäftsführung', 'Qualitätsmanagementbeauftragte', 'Einkauf', 'Vertrieb'] and pg.is_disabled('[data-og-tat="links"]'), baum(pg))
    pg.click('[data-og-tat="linie"]'); pg.fill('#og-titel-in', 'Disposition')
    wurzel = pg.get_attribute('#og-liste [data-og-knoten]', 'data-og-knoten')
    pg.select_option('#og-ueber', wurzel)
    check('Verschieben: Disposition unter die Geschäftsführung (ganz rechts)', baum(pg)[-1] == 'Disposition' and pg.locator('#og-baum .og-wurzeln > .og-k > .og-kinder > .og-k').count() == 3, baum(pg))
    pg.locator('#og-baum .og-kasten', has_text='Vertrieb').click(); pg.click('[data-og-tat="loeschen"]')
    check('Löschen ohne Unterstellen ohne Rückfrage', 'Vertrieb' not in baum(pg) and pg.is_hidden('#og-felder'))
    pg.click('#og-zu')
    check('Schließen mit ungespeicherten Änderungen fragt nach (abgelehnt: bleibt offen)', pg.is_visible('#dlg-og'))
    pg.click('#og-speichern'); pg.wait_for_selector('#og-speichern:disabled')
    v = dok(Be, PLAN)['versionen'][0]['organigramm']['knoten']
    titel = {k['id']: k['titel'] for k in v}
    nach = {k['titel']: k for k in v}
    check('gespeichert: Struktur, Personen, Vertretung, Stabsstelle, Reihenfolge unter der Stelle', sorted(nach) == ['Disposition', 'Einkauf', 'Geschäftsführung', 'Qualitätsmanagementbeauftragte']
          and nach['Geschäftsführung']['personen'] == ['GF'] and nach['Geschäftsführung']['vertretung'] == 'QV' and nach['Qualitätsmanagementbeauftragte']['art'] == 'stab'
          and nach['Qualitätsmanagementbeauftragte']['personen'] == ['QB'] and [k['titel'] for k in v if k['art'] == 'linie' and k['ueber']] == ['Einkauf', 'Disposition']
          and all(titel.get(k['ueber']) == 'Geschäftsführung' for k in v if k['ueber']), v)
    check('Karte zeigt den Entwurf, Meldung im Fenster', 'Entwurf: 4 Stellen' in pg.text_content('#qm-dk .og-karte') and pg.text_content('#og-meldung') == 'Organigramm gespeichert.')
    pg.screenshot(path=os.path.join(SH, 'qs_organigramm_bearbeiten_1280_light.png'))
    pg.locator('#og-baum .og-kasten', has_text='Einkauf').click()
    pg.fill('#og-titel-in', '')
    pg.click('#og-speichern'); pg.wait_for_function("() => document.querySelector('#og-meldung').textContent.includes('benennen')")
    check('Fehler des Servers erscheint im Fenster', 'benennen' in pg.text_content('#og-meldung'))
    pg.once('dialog', lambda d: d.accept())
    pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
    check('Schließen nach Rückfrage verwirft die Änderung', 'Einkauf' in [k['titel'] for k in dok(Be, PLAN)['versionen'][0]['organigramm']['knoten']])
    ctx.close()

    for breite, thema in ((1280, 'dark'), (390, 'light'), (390, 'dark')):
        ctx, pg = anmelden('bernd', 'Bearbeit-Konto-34', '198.51.100.11', breite, thema, 844 if breite < 500 else 900)
        oeffne_dok(pg, PLAN)
        pg.click('#qm-dk [data-og="bearbeiten"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
        pg.locator('#og-liste [data-og-knoten]').nth(1).click(); pg.wait_for_selector('#og-felder:not([hidden])')
        check(f'{breite} px {thema}: Gliederung wählt die Stelle', pg.input_value('#og-titel-in') == 'Qualitätsmanagementbeauftragte' and pg.locator('#og-liste .og-zeile').count() == 4)
        breit = pg.evaluate("() => { const d = document.querySelector('#dlg-og'); return [document.documentElement.scrollWidth - window.innerWidth, d.scrollWidth - d.clientWidth, d.getBoundingClientRect().width]; }")
        check(f'{breite} px {thema}: Seite und Fenster ohne waagerechtes Scrollen', breit[0] <= 0 and breit[1] <= 0 and breit[2] <= breite, breit)
        pg.screenshot(path=os.path.join(SH, f'qs_organigramm_bearbeiten_{breite}_{thema}.png'))
        if breite == 390:
            pg.click('[data-og-zoom="0.1"]')
            check(f'{breite} px {thema}: Diagramm lässt sich vergrößern und im Fenster scrollen', pg.evaluate("() => { const f = document.querySelector('#og-flaeche'); return f.scrollWidth > f.clientWidth; }"))
            pg.once('dialog', lambda d: d.accept())
            pg.click('#og-zu'); pg.wait_for_selector('#dlg-og', state='hidden')
            oeffne_dok(pg, DOK['id'])
            pg.click('#qm-dk [data-og="ansehen"]'); pg.wait_for_selector('#dlg-og[open] .og-kasten')
            pg.screenshot(path=os.path.join(SH, f'qs_organigramm_ansehen_{breite}_{thema}.png'))
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler[:5])

print(f'{sum(res)}/{len(res)} passed')
