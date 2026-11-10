"""Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6) im gemeinsamen Rahmen „C2“ (app/assets/rahmen.css, rahmen.js):
Startseite mit Favoriten (kompakte Kacheln, „Bearbeiten“ am Konto), „Heute für Sie“ (offene Punkte der Module nach Rechten,
Aktion start_heute), Schnellaktionen, „Zuletzt bearbeitet“, Hinweisen zu Wartungen; Seitenleiste aus dem Modulregister mit
Suche (Strg K) und Zahlen je Anwendung, Stand, Wartung, Abmeldung, Begrüßung, Klebeband „Bald“, schmale Leiste (klappt mit Maus
oder Tastatur auf, Pin stellt sie am Konto fest), Menü am Handy,
hell/dunkel, 390 px.

Das Dashboard liegt außerhalb der Dokumentwurzel; der Testlauf blendet es nur für diese Gruppe unter /dashboard/ ein. Kachel,
offener Punkt und Eintrag der Seitenleiste sind nur Anzeige – die Sperre setzt der Server durch (GR-102, GR-103).
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
storage_write('vertreter', {'rev': 1, 'groups': [{'nr': '11', 'name': 'Vera Vertrieb', 'kurz': 'VV', 'telefon': '', 'plz': '', 'ort': '', 'land': ''}]})
A.call('user_save', {'id': '', 'name': 'Fritz Freigabe', 'username': 'fritz', 'role': 'editor', 'active': True, 'password': 'Zweiter-Zugang-4711', 'mustChange': False,
                     'grant': ['marketing.sehen', 'marketing.bearbeiten', 'marketing.freigeben']})
A.call('user_save', {'id': '', 'name': 'Vera Vertrieb', 'username': 'vera', 'role': 'editor', 'active': True, 'password': 'Dritter-Zugang-4712', 'mustChange': False,
                     'grant': ['crm.sehen'], 'vertreter': '11'})
IDS = {u['username']: u['id'] for u in A.call('users')[1]['users']}
ADMIN = IDS['admin']
HEUTE = date.today()


def tag(n):
    return (HEUTE + timedelta(days=n)).isoformat()


# ── Testdaten für „Heute für Sie“: je Modul ein offener Punkt (nur über die Schnittstellen der Module) ──
# HR: Antrag von Erika (nächstes Jahr), zu entscheiden vom Administrator
rev = A.call('mitarbeiter_hr')[1]['rev']
check('HR: Urlaubsanspruch für Erika gesetzt', A.call('mitarbeiter_hr_save', {'nutzer': IDS['erika'], 'rev': rev, 'jahr': HEUTE.year + 1, 'anspruch': 30})[0] == 200)
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
FEB = date(HEUTE.year + 1, 2, 1)
while FEB.weekday() != 0:
    FEB += timedelta(days=1)
st, r = E.call('hr_antrag', {'von': FEB.isoformat(), 'bis': (FEB + timedelta(days=4)).isoformat(), 'vertretung': ADMIN})
check('HR: Urlaubsantrag von Erika gestellt', st == 200, (st, r))
# QS: Kapitel, Kürzel des Administrators, tägliche Prüfung (heute fällig), jährliche Prüfung (2 Tage überfällig), Maßnahme über der Frist
check('QS: Kapitel und Kürzel', A.call('qs_stamm_save', {'kapitel': [{'id': '1.1', 'titel': 'Managementsystem'}, {'id': '4.2', 'titel': 'Hygiene'}],
                                                        'personen': [{'id': 'AD', 'name': 'Administrator', 'mitarbeiter': ADMIN}]})[0] == 200)
PRUEF = {'beschreibung': 'laut Plan', 'sollwert': 'in Ordnung', 'massnahme': 'melden', 'womit': 'Liste', 'zustaendig': 'AD', 'vertreter': ''}
check('QS: Prüfungen angelegt', A.call('qs_pruefung_save', {**PRUEF, 'kapitel': '4.2', 'titel': 'Temperatur Kühlraum 2', 'intervall': 'taeglich', 'start': tag(0)})[0] == 200
      and A.call('qs_pruefung_save', {**PRUEF, 'kapitel': '1.1', 'titel': 'Kalibrierung Waagen', 'intervall': 'jaehrlich', 'start': tag(-2)})[0] == 200)
st, r = A.call('qs_massnahme_save', {'quelle': 'intern', 'bezug': 'Audit', 'kapitel': '1.1', 'anforderung': '4.8.2', 'bewertung': 'B', 'feststellung': 'Thermometer nicht kalibriert',
                                     'massnahme': 'Kalibrierplan erstellen', 'zustaendig': 'AD', 'frist': tag(-2), 'status': 'offen'})
check('QS: Maßnahme mit abgelaufener Frist', st == 200, (st, r))
# Leergut: Auszug mit abgelaufener Frist (Eingang vor 16 Tagen, Frist 14 Tage)
st, r = A.call('leergut_partner_save', {'name': 'Spedition Nord', 'art': 'spedition', 'mandant': 'standard', 'kontoNr': '4711', 'fristTage': 14,
                                        'email': 'leergut@example.invalid', 'lademittel': ['e2', 'eu']})
check('Leergut: Auszug mit abgelaufener Frist', st == 200 and A.call('leergut_abstimmung_save', {'partner': r['partner']['id'], 'stichtag': tag(-30), 'eingang': tag(-16),
                                                                                                    'saldo': {'e2': 8}, 'quelle': 'Mail', 'notiz': ''})[0] == 200, r)
# REWE: zwei Märkte in der eigenen Liste, noch ohne Antwort
LW = A.call('rewe_start')[1]['lieferwege'][0]['id']
for i in range(2):
    st, r = A.call('rewe_markt_save', {'name': f'REWE Testmarkt {i}', 'kdNr': f'17990{i}9', 'strasse': 'Marktweg 1', 'plz': '20001', 'ort': 'Musterstadt', 'lieferweg': LW, 'zustaendig': ADMIN})
    check(f'REWE: Markt {i} angelegt', st == 200, (st, r))
# Marketing: Beitrag zur Freigabe (morgen) und eigener Beitrag in Produktion (übermorgen)
check('Marketing: Beiträge angelegt', A.call('marketing_beitrag_save', {'felder': {'titel': 'Herbstaktion Rinderbraten', 'veroeffentlichung': tag(1)}, 'status': 'freigabe'})[0] == 200
      and A.call('marketing_beitrag_save', {'felder': {'titel': 'Rezept-Video Gulasch', 'veroeffentlichung': tag(2), 'verantwortlich': ADMIN}, 'status': 'produktion'})[0] == 200)
# CRM: Interessent von Vera (Vertreter 11) mit Wiedervorlage in zwei Tagen
st, r = A.call('crm_interessent_save', {'firma': 'Grillhaus am Hafen', 'plz': '22765', 'ort': 'Hamburg', 'vertreter': '11'})
check('CRM: Interessent angelegt', st == 200, (st, r))
check('CRM: Wiedervorlage gesetzt', A.call('crm_kunde_save', {'key': r['kunde']['key'], 'felder': {'wiedervorlage': tag(2), 'naechsterSchritt': 'Probepaket nachfassen'}})[0] == 200)

# ── Schnittstelle start_heute: Punkte nach Rechten und Modulzugang (GR-103), Zahlen, Schnellaktionen, Zuletzt, Favoriten ──
st, H = A.call('start_heute')
check('start_heute: Administrator 200', st == 200 and H.get('ok'), (st, H))
PUNKTE = H.get('punkte', [])
mod = lambda liste: sorted({p['modul'] for p in liste})
check('Administrator: offene Punkte aus HR, Leergut, Marketing, QS und REWE (CRM nur mit Vertreternummer)', mod(PUNKTE) == ['hr', 'leergut', 'marketing', 'qs', 'rewe'], PUNKTE)
arten = [p['art'] for p in PUNKTE]
check('Reihenfolge: überfällig vor heute vor demnächst', arten == sorted(arten, key=['ueberfaellig', 'heute', 'demnaechst'].index), arten)
p_ = {(p['modul'], p['titel']): p for p in PUNKTE}
check('Leergut: Auszug mit abgelaufener Frist überfällig, Ziel Reiter „Abstimmungen“', (lambda x: x and x['art'] == 'ueberfaellig' and x['datum'] == tag(-2)
      and x['ziel'] == 'abstimmungen')(p_.get(('leergut', 'Auszug abstimmen: Spedition Nord'))), PUNKTE)
massn = [p for p in PUNKTE if p['modul'] == 'qs' and p['titel'].startswith('Maßnahme ') and p['titel'].endswith(': Kalibrierplan erstellen')]
check('QS: eigene Prüfungen (überfällig bzw. heute fällig) und eigene Maßnahme über der Frist',
      p_.get(('qs', 'Prüfung: Kalibrierung Waagen'), {}).get('art') == 'ueberfaellig' and p_.get(('qs', 'Prüfung: Kalibrierung Waagen'), {}).get('detail') == '2 Tage überfällig'
      and p_.get(('qs', 'Prüfung: Temperatur Kühlraum 2'), {}).get('art') == 'heute' and len(massn) == 1 and massn[0]['art'] == 'ueberfaellig'
      and massn[0]['ziel'] == 'massnahmen', PUNKTE)
hr_p = p_.get(('hr', 'Antrag entscheiden'), {})
check('HR: Sammelpunkt „Antrag entscheiden“ ohne Namen und Art (Personaldaten)', hr_p.get('art') == 'heute' and hr_p.get('anzahl') == 1 and hr_p.get('ziel') == 'antraege'
      and 'Erika' not in json.dumps(hr_p) and 'Urlaub' not in json.dumps(hr_p), hr_p)
check('Marketing: Freigabe (heute) und eigener Beitrag (demnächst)', p_.get(('marketing', 'Beitrag freigeben'), {}).get('art') == 'heute'
      and p_.get(('marketing', 'Beitrag: Rezept-Video Gulasch'), {}).get('art') == 'demnaechst', PUNKTE)
rw = p_.get(('rewe', '2 Märkte ohne Antwort'), {})
check('REWE: Märkte der eigenen Liste ohne Antwort als Sammelpunkt', rw.get('anzahl') == 2 and rw.get('ziel') == 'woche' and rw.get('art') in ('heute', 'demnaechst'), rw)
Z = H.get('zahlen', {})
check('Zahlen je Modul (für die Seitenleiste) und gesamt', Z.get('qs') == {'offen': 3, 'ueberfaellig': 2} and Z.get('leergut') == {'offen': 1, 'ueberfaellig': 1}
      and Z.get('rewe') == {'offen': 2, 'ueberfaellig': 0} and H.get('gesamt') == {'offen': 9, 'ueberfaellig': 3}, (Z, H.get('gesamt')))
AKT = [(a['titel'], a['ziel']) for a in H.get('aktionen', [])]
check('Schnellaktionen des Administrators in fester Reihenfolge (die ersten vier wie im Entwurf), Fenster zum Anlegen über „<reiter>/neu“', AKT == [
      ('Kundenangebot erstellen', 'einzel'), ('Urlaub beantragen', 'mein'), ('Interessent anlegen', 'kunden/neu'), ('Daten importieren', ''), ('Wochenangebot bearbeiten', ''),
      ('Beitrag anlegen', 'kalender/neu'), ('Prüfnachweis erfassen', 'pruefplan'), ('Wiedervorlagen ansehen', 'wiedervorlagen'), ('REWE-Wochenabfrage', 'woche'),
      ('Leergut abstimmen', 'abstimmungen')], AKT)
zl = H.get('zuletzt', [])
check('Zuletzt bearbeitet: eigene Änderungen, neueste zuerst, ohne Vorsatz des Moduls, höchstens sechs',
      0 < len(zl) <= 6 and zl[0]['modul'] == 'crm' and all(not x['text'].startswith(('CRM:', 'REWE:', 'Marketing:')) for x in zl) and zl == sorted(zl, key=lambda x: x['zeit'], reverse=True), zl)
check('Zuletzt bearbeitet: keine Einträge anderer Mitarbeiter', all('Antrag' not in x['text'] for x in zl), zl)
check('Favoriten noch nicht gewählt (Standard)', H.get('favoriten') is None, H.get('favoriten'))

st, he = E.call('start_heute')
check('Bearbeiter: keine Punkte aus Modulen ohne Recht (kein Genehmigen, nicht in QS eingeteilt, kein Leergut, keine REWE-Liste)', st == 200 and he['punkte'] == []
      and he['gesamt'] == {'offen': 0, 'ueberfaellig': 0}, he.get('punkte'))
check('Bearbeiter: nur Schnellaktionen mit Recht (kein Kundenangebot, kein CRM)', [a['titel'] for a in he['aktionen']] == ['Urlaub beantragen', 'Daten importieren', 'Wochenangebot bearbeiten'], he['aktionen'])
check('Bearbeiter: eigener Urlaubsantrag unter „Zuletzt bearbeitet“, maskiert (ohne Recht „HR verwalten“)', any(x['modul'] == 'hr' and x['text'] == 'Vorgang der Urlaubsverwaltung'
      for x in he['zuletzt']), he['zuletzt'])
V = Client('198.51.100.4'); V.call('login', {'username': 'vera', 'password': 'Dritter-Zugang-4712'})
st, hv = V.call('start_heute')
check('Vertrieb: Wiedervorlage des eigenen Interessenten (Vertreter 11), demnächst', st == 200 and [(p['modul'], p['art'], p['titel'], p['detail'], p['ziel']) for p in hv['punkte']]
      == [('crm', 'demnaechst', 'Wiedervorlage: Grillhaus am Hafen', 'Probepaket nachfassen', 'wiedervorlagen')], hv.get('punkte'))
F = Client('198.51.100.5'); F.call('login', {'username': 'fritz', 'password': 'Zweiter-Zugang-4711'})
check('Freigabe Marketing: Beitrag zur Freigabe sichtbar', [p['titel'] for p in F.call('start_heute')[1]['punkte']] == ['Beitrag freigeben'])
st, r = A.call('modul_wartung_save', {'bereich': 'marketing.intern', 'active': True, 'grund': 'Test Startseite', 'message': 'Gleich zurück.'})
st2, hf = F.call('start_heute')
check('Marketing in Wartung: keine Punkte aus Marketing für Mitarbeiter (nur Module mit nutzbarer Kachel), Startseite antwortet weiter', st == 200 and st2 == 200
      and hf['punkte'] == [] and not [a for a in hf['aktionen'] if a['modul'] == 'marketing'], hf)
check('Wartung Marketing beendet', A.call('modul_wartung_save', {'bereich': 'marketing.intern', 'active': False, 'grund': 'fertig'})[0] == 200)

# Favoriten am Konto: nur Anwendungen mit Kachel, ohne Doppelte, höchstens acht, nur mit Sicherheitsprüfung
check('Favoriten: ohne Anmeldung 401', Client('198.51.100.6').call('start_heute')[0] == 401 and Client('198.51.100.6').call('start_favoriten_save', {'favoriten': []})[0] in (401, 403))
for name, b in (('unbekannte Anwendung', {'favoriten': ['gibtsnicht']}), ('Bereich ohne Kachel', {'favoriten': ['plattform']}), ('keine Liste', {'favoriten': 'crm'}),
                ('mehr als acht', {'favoriten': ['angebot', 'bestand', 'leergut', 'crm', 'rewe', 'qs', 'hr', 'marketing', 'controlling']}), ('Zahl statt Kennung', {'favoriten': [1]})):
    check(f'Favoriten: {name} → 422', E.call('start_favoriten_save', b)[0] == 422)
check('Favoriten: nur per POST', E.call('start_favoriten_save')[0] == 405)
check('Favoriten: ohne Angabe → 422', E.call('start_favoriten_save', {})[0] == 422)
csrf, E.csrf = E.csrf, ''
check('Favoriten: ohne Sicherheitsprüfung (CSRF) 403', E.call('start_favoriten_save', {'favoriten': ['hr']})[0] == 403)
E.csrf = csrf
st, r = E.call('start_favoriten_save', {'favoriten': ['hr', 'crm', 'hr']})
E2 = Client('198.51.100.7')
check('Favoriten gespeichert (ohne Doppelte), am Konto (auch in einer neuen Sitzung)', st == 200 and r['favoriten'] == ['hr', 'crm']
      and E2.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})[0] == 200 and E2.call('start_heute')[1]['favoriten'] == ['hr', 'crm'], r)
check('Favoriten: leere Liste erlaubt (bewusst keine)', E.call('start_favoriten_save', {'favoriten': []})[1].get('favoriten') == [] and E2.call('start_heute')[1]['favoriten'] == [])
check('Favoriten: null = zurück zum Standard', E.call('start_favoriten_save', {'favoriten': None})[0] == 200 and E2.call('start_heute')[1]['favoriten'] is None)
# Freigegebene Anwendungen in der Reihenfolge des Registers (Seitenleiste „Anwendungen“)
FREI = ['angebot', 'bestand', 'leergut', 'crm', 'rewe', 'qs', 'hr', 'marketing', 'controlling']
fehler = []


BERLIN = ZoneInfo('Europe/Berlin')


def anmelden(br, user, pw, ip, breite=1280, dunkel=False, uhr=None):
    ctx = br.new_context(viewport={'width': breite, 'height': 900}, color_scheme='dark' if dunkel else 'light',
                         extra_http_headers={'X-Forwarded-For': ip}, timezone_id='Europe/Berlin', locale='de-DE')
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
    pg.wait_for_selector('#screen-auth', state='hidden')
    if uhr:   # feste Uhrzeit nur für das Dashboard (Begrüßung, Datum); Zeitgeber laufen weiter
        pg.clock.set_fixed_time(uhr)
    pg.goto(B + '/dashboard/'); bereit(pg)
    return ctx, pg


def bereit(pg):   # Seite fertig: Favoriten am Konto bekannt, offene Punkte geladen
    pg.wait_for_selector('#db-heute-liste[aria-busy="false"]'); pg.wait_for_selector('#db-grid .db-tile[data-modul], #db-grid .db-leer')


def kacheln(pg):
    return pg.eval_on_selector_all('#db-grid .db-tile[data-modul]', '''els => els.map(e => ({id: e.dataset.modul, tag: e.tagName, href: e.getAttribute('href'),
        name: e.querySelector('.db-name').textContent, badge: e.querySelector('.db-badge').textContent, badgeCls: e.querySelector('.db-badge').className,
        badgeSichtbar: e.querySelector('.db-badge').getBoundingClientRect().width > 2,
        bald: (e.querySelector('.r-bald') || {}).textContent || '', baldVersteckt: (e.querySelector('.r-bald') || {getAttribute: () => null}).getAttribute('aria-hidden'),
        gesperrt: e.classList.contains('gesperrt'), symbol: e.querySelector('.db-ico').dataset.symbol, svg: !!e.querySelector('.db-ico svg :is(path, rect, circle)'),
        hint: (e.querySelector('.db-hint') || {}).textContent || '', bilder: e.querySelectorAll('.db-hint img').length}))''')


# Seitenleiste: Gruppen mit ihren Einträgen (Modul-ID, Verweis, aktiv, gesperrt, Stand, Klebeband)
LEISTE = '''[...document.querySelectorAll('#r-leiste .r-liste')].map(l => [(l.closest('.r-gruppe') || {querySelector: () => null}).querySelector('.r-gruppe-titel')?.textContent || '',
  [...l.querySelectorAll('.r-eintrag')].map(e => ({id: e.dataset.modul, tag: e.tagName, href: e.getAttribute('href'), aktiv: e.getAttribute('aria-current'),
    aus: e.getAttribute('aria-disabled'), label: e.getAttribute('aria-label'), stand: (e.querySelector('.r-stand') || {}).textContent || '',
    bald: (e.querySelector('.r-bald') || {}).textContent || '', symbol: e.dataset.symbol}))])'''


def leiste(pg):
    return {t: e for t, e in pg.evaluate(LEISTE)}


# Kontrast Text ↔ Untergrund: halbtransparente Flächen werden bis zum deckenden Seitengrund verrechnet.
KONTRAST = '''(sels) => {
  const rgba = (s) => { const m = s.match(/[\\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
  const ueber = (o, u) => [0, 1, 2].map((i) => o[i] * o[3] + u[i] * (1 - o[3])).concat(1);
  const grund = (el) => { const s = []; for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c[3] > 0) s.push(c); if (c[3] >= 1) break; }
    return s.reverse().reduce((u, o) => ueber(o, u), [255, 255, 255, 1]); };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  return sels.map((s) => { const el = document.querySelector(s); if (!el) return [s, 0];
    const g = grund(el), t = ueber(rgba(getComputedStyle(el).color), g), [h, d] = [lum(t), lum(g)].sort((x, y) => y - x);
    return [s, Math.round((h + .05) / (d + .05) * 100) / 100]; });
}'''
TEXTE = ['#db-datum', '#db-titel', '#db-sub', '#db-fav-titel', '#db-fav-bearbeiten', '#db-grid [data-modul="angebot"] .db-name', '#db-grid .db-zahl',
         '#db-heute-titel', '#db-heute-zahl', '.db-gruppe.ueberfaellig .db-gruppe-titel', '.db-gruppe.heute .db-gruppe-titel', '.db-zeile-titel', '.db-zeile-meta',
         '.db-zeile-datum.ueberfaellig', '.db-zeile-datum.heute', '#db-heute-alle', '#db-aktionen-liste .db-zeile-titel', '#db-zuletzt-liste .db-zeile-meta',
         '#r-leiste .r-bald', '#r-leiste .r-gruppe-titel', '#r-leiste [data-modul="angebot"] .r-text', '#r-leiste .r-zahl', '#r-leiste .r-zahl-rot', '#r-suche .r-text',
         '#r-leiste [data-modul="einkauf"] .r-text', '#r-leiste [data-modul="start"] .r-text', '#r-initialen', '#r-nutzer-name', '#r-rolle', '.db-fuss']


def kontrast_ok(pg, name):
    werte = pg.evaluate(KONTRAST, TEXTE)
    check(f'{name}: Textkontrast mindestens 4,5:1 (Seite, Kacheln, Listen, Seitenleiste)', all(w >= 4.5 for _, w in werte), werte)


# Wörter, die über eine Zeile hinaus umbrechen (mitten im Wort getrennt), je Kachelname; Notlösung (db-name-umbruch) getrennt
WORT_GETRENNT = """[...document.querySelectorAll('#db-bereich .db-name')].map(e => {
  const t = e.firstChild, text = t ? t.textContent : '', getrennt = [];
  for (const m of text.matchAll(/\\S+/g)) { const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
    if (new Set([...r.getClientRects()].map(q => Math.round(q.top))).size > 1) getrennt.push(m[0]); }
  return [e.textContent, getrennt, e.classList.contains('db-name-umbruch'), parseFloat(getComputedStyle(e).fontSize), getComputedStyle(e).hyphens]; })"""
UEBERLAUF = "[...document.querySelectorAll('.db-name, #r-leiste .r-text, .db-zeile-titel, .db-zeile-meta')].filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)"


def bilder(pg):   # auf zwei Bilder warten: ResizeObserver und Neuberechnung nach einer Größenänderung
    pg.wait_for_function("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))")


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ── Ohne Anmeldung: Hinweis auf die Anmeldung, keine Kacheln, keine Seitenleiste ──
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis sichtbar, Startseite und Seitenleiste verborgen', pg.is_hidden('#db-bereich') and pg.is_hidden('#r-leiste')
          and not pg.evaluate("document.querySelector('.r-app').classList.contains('r-bereit')"))
    check('Anmeldehinweis führt zur Mitarbeiter-Anmeldung', (pg.get_attribute('#db-login a', 'href') or '').endswith('/admin/'), pg.get_attribute('#db-login a', 'href'))
    check('keine Kacheln und keine Einträge ohne Anmeldung', pg.locator('#db-grid .db-tile[data-modul]').count() == 0 and pg.locator('#r-leiste .r-eintrag').count() == 0)
    knopf = pg.evaluate("[document.querySelector('.db-login-i').getBoundingClientRect().width, getComputedStyle(document.querySelector('#db-login a')).textDecorationLine, !!document.querySelector('#db-login img.r-logo')]")
    check('Anmeldehinweis: Logo, Schloss-Symbol 28 px, Knopf ohne Unterstreichung', knopf == [28, 'none', True], knopf)
    pg.keyboard.press('Control+k')
    check('ohne Anmeldung: keine Suche (Strg K tut nichts)', pg.locator('#r-palette[open]').count() == 0)
    ctx.close()

    # ── Seitenleiste (10.11.2026): auf jeder Seite schmal, klappt mit Maus oder Tastatur über dem Inhalt auf, Pin stellt sie fest ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.49')
    LAGE = """(() => { const n = document.querySelector('#r-leiste'), a = document.querySelector('.r-app');
        return { breite: Math.round(n.getBoundingClientRect().width), inhalt: Math.round(document.querySelector('.r-inhalt').getBoundingClientRect().left),
                 fest: a.classList.contains('r-fest'), auf: a.classList.contains('r-auf'), pin: document.querySelector('#r-pin').getAttribute('aria-pressed'),
                 texte: getComputedStyle(n.querySelector('[data-modul="crm"] .r-text')).display !== 'none' }; })()"""
    st = A.call('status')[1]['user']
    check('Seitenleiste: ohne eigene Wahl nicht festgestellt (Status leiste leer)', st.get('leiste') == '', st.get('leiste'))
    lg = pg.evaluate(LAGE)
    check('Seitenleiste schmal (60 px, nur Symbole), Inhalt daneben, Pin sichtbar und nicht gedrückt',
          lg == {'breite': 60, 'inhalt': 60, 'fest': False, 'auf': False, 'pin': 'false', 'texte': False} and pg.locator('#r-pin').is_visible(), lg)
    pg.hover('#r-leiste a[data-modul="crm"]'); pg.wait_for_function("document.querySelector('.r-app').classList.contains('r-auf')")
    lg = pg.evaluate(LAGE)
    check('Mauszeiger auf der Leiste: klappt auf 208 px auf, liegt über dem Inhalt (Inhalt springt nicht), Namen sichtbar',
          lg['breite'] == 208 and lg['inhalt'] == 60 and lg['texte'] and not lg['fest'], lg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_leiste_aufgeklappt.png'))
    pg.mouse.move(900, 600); pg.wait_for_function("!document.querySelector('.r-app').classList.contains('r-auf')")
    check('Mauszeiger weg: klappt wieder ein', pg.evaluate(LAGE)['breite'] == 60)
    pg.mouse.move(30, 300); pg.mouse.move(400, 300)   # nur kurz darüber: klappt nicht auf (Verzögerung)
    pg.wait_for_function("new Promise(r => setTimeout(() => r(true), 400))")
    check('nur kurz überfahren: bleibt schmal', not pg.evaluate(LAGE)['auf'])
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    for _ in range(4):
        pg.keyboard.press('Tab')
        if pg.evaluate("!!document.activeElement.closest('#r-leiste')"):
            break
    pg.wait_for_function("document.querySelector('.r-app').classList.contains('r-auf')")
    check('Tastatur: Fokus in der Leiste klappt sie auf', pg.evaluate(LAGE)['breite'] == 208)
    pg.keyboard.press('Escape'); pg.wait_for_function("!document.querySelector('.r-app').classList.contains('r-auf')")
    check('Escape klappt sie wieder ein', pg.evaluate(LAGE)['breite'] == 60)
    pg.hover('#r-leiste a[data-modul="crm"]'); pg.wait_for_function("document.querySelector('.r-app').classList.contains('r-auf')")
    pg.click('#r-pin'); pg.wait_for_function("document.querySelector('.r-app').classList.contains('r-fest')")
    pg.mouse.move(900, 600)
    pg.wait_for_function("(() => fetch('../api/?action=status').then(r => r.json()).then(d => d.user.leiste === 'fest'))()")
    lg = pg.evaluate(LAGE)
    check('Pin: festgestellt, immer 208 px, Inhalt rückt daneben (208 px), Pin gedrückt, am Konto gespeichert',
          lg == {'breite': 208, 'inhalt': 208, 'fest': True, 'auf': False, 'pin': 'true', 'texte': True}
          and 'lösen' in pg.get_attribute('#r-pin', 'aria-label') and A.call('status')[1]['user']['leiste'] == 'fest', lg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_leiste_fest.png'))
    pg.reload(); bereit(pg)
    check('nach dem Neuladen weiter festgestellt (Wahl am Konto)', pg.evaluate(LAGE)['fest'] and pg.evaluate(LAGE)['breite'] == 208)
    pg.goto(B + '/module/crm/'); pg.wait_for_selector('.r-app.r-bereit')
    lg = pg.evaluate(LAGE)
    check('Modulseite (CRM): dieselbe Wahl – festgestellt, 208 px, Pin gedrückt', lg['fest'] and lg['breite'] == 208 and lg['pin'] == 'true', lg)
    pg.click('#r-pin'); pg.wait_for_function("!document.querySelector('.r-app').classList.contains('r-fest')")
    pg.mouse.move(900, 600); pg.wait_for_function("!document.querySelector('.r-app').classList.contains('r-auf')")
    pg.wait_for_function("(() => fetch('../../api/?action=status').then(r => r.json()).then(d => d.user.leiste === ''))()")
    lg = pg.evaluate(LAGE)
    check('Modulseite: Pin lösen – wieder schmal (60 px), am Konto gespeichert', lg['breite'] == 60 and lg['inhalt'] == 60 and lg['pin'] == 'false'
          and A.call('status')[1]['user']['leiste'] == '', lg)
    check('ungültiger Wert für die Leiste: 422', A.call('theme_save', {'leiste': 'quer'})[0] == 422)
    check('Leiste mit Hell/Dunkel zusammen speicherbar, Hell/Dunkel bleibt erhalten', A.call('theme_save', {'leiste': 'fest', 'theme': ''})[0] == 200
          and A.call('status')[1]['user']['leiste'] == 'fest')
    ctx.close()
    # Für die folgenden Prüfungen der breiten Leiste bleibt der Administrator festgestellt; die schmale Leiste prüft der
    # Abschnitt „Schmale Leiste“ unten, die anderen Testnutzer haben keine eigene Wahl.

    # ── Administrator: Favoriten (Standard), Heute für Sie, Schnellaktionen, Zuletzt bearbeitet, Seitenleiste ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.41')
    k = kacheln(pg)
    check('Favoriten ohne eigene Wahl: die ersten vier Anwendungen des Registers (ohne Verwaltung & Daten)', [x['id'] for x in k] == ['angebot', 'bestand', 'leergut', 'crm'], [x['id'] for x in k])
    check('Favoriten: kompakte Kacheln (Symbol links, Name rechts), Namen aus dem Register', pg.evaluate("""[...document.querySelectorAll('#db-grid .db-tile')].every(t => getComputedStyle(t).flexDirection === 'row'
          && t.querySelector('.db-ico').getBoundingClientRect().right <= t.querySelector('.db-name').getBoundingClientRect().left)""") and [x['name'] for x in k] == ['Angebot', 'Bestand', 'Leergut', 'CRM'])
    check('Favoriten: vier nebeneinander (1280 px)', len({round(pg.evaluate(f"document.querySelectorAll('#db-grid .db-tile')[{i}].getBoundingClientRect().top")) for i in range(4)}) == 1)
    unter = pg.evaluate("[...document.querySelectorAll('#db-grid a.db-tile')].map(t => [t.dataset.modul, [...t.querySelectorAll('.db-text > *')].filter(e => e.getBoundingClientRect().width > 2).length])")
    check('keine Unterzeile unter verfügbaren Kacheln (nur der Name ist sichtbar, keine Beschreibung)', unter and all(n == 1 for _, n in unter) and pg.locator('.db-desc').count() == 0, unter)
    kid = {x['id']: x for x in k}
    check('Angebot: verfügbar, als Verweis auf die Mitarbeiter-Eingabe (Testserver: gleicher Host)', kid['angebot']['tag'] == 'A' and kid['angebot']['href'] == '/admin/' and kid['angebot']['badge'] == 'Verfügbar', kid['angebot'])
    check('„Verfügbar“ nur für Screenreader (keine sichtbare Pille), grün markiert', all('ok' in x['badgeCls'] and 'sr-only' in x['badgeCls'] and not x['badgeSichtbar'] for x in k))
    check('Kachel Leergut: Zahl der offenen Punkte, rot (überfällig)', pg.evaluate("[document.querySelector('#db-grid [data-modul=\"leergut\"] .db-zahl')?.textContent, document.querySelector('#db-grid [data-modul=\"leergut\"] .db-zahl')?.classList.contains('rot')]") == ['1 offen', True])
    check('Symbolfarbe je Registersymbol (Angebot: tag)', k[0]['symbol'] == 'tag' and pg.evaluate("getComputedStyle(document.querySelector('#db-grid [data-modul=\"angebot\"] .db-ico')).backgroundColor") == 'rgb(155, 35, 53)')
    ruhig = pg.evaluate("""[...document.querySelectorAll('a.db-tile, #r-leiste, .db-liste')].map(e => { const s = getComputedStyle(e);
        return [s.backdropFilter, s.backgroundColor, e.id === 'r-leiste' ? '1px' : s.borderTopWidth]; })""")
    check('ruhige Flächen: kein Glas (keine Unschärfe), Kacheln und Listen weiß mit feiner Linie', ruhig and all(b == 'none' and c.startswith('rgb(') and w == '1px' for b, c, w in ruhig), ruhig[:3])
    form = pg.evaluate("[getComputedStyle(document.querySelector('.db-tile')).borderTopLeftRadius, Math.round(document.querySelector('#r-leiste').getBoundingClientRect().width), getComputedStyle(document.querySelector('#r-leiste')).position]")
    check('Kacheln mit 14 px Radius, Seitenleiste 208 px breit und fest (sticky)', form == ['14px', 208, 'sticky'], form)
    hg = pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('#r-leiste')).backgroundColor]")
    check('heller Grund #f6f4f1, Seitenleiste #eeebe7', hg == ['rgb(246, 244, 241)', 'rgb(238, 235, 231)'], hg)
    check('Schrift Geist (selbst gehostet)', 'Geist' in pg.evaluate("getComputedStyle(document.querySelector('#db-titel')).fontFamily"))
    check('Desktop: keine Kopfzeile fürs Handy, kein Menüknopf sichtbar', pg.evaluate("getComputedStyle(document.querySelector('.r-mobilkopf')).display") == 'none')

    # Unterzeile und „Heute für Sie“
    check('Unterzeile: Datum und „9 offene Punkte, 3 davon überfällig“', pg.text_content('#db-sub') == '9 offene Punkte, 3 davon überfällig' and pg.is_visible('#db-sub-trenner'), pg.text_content('#db-sub'))
    check('„Heute für Sie“ mit Zahl (rot, weil etwas überfällig ist)', pg.text_content('#db-heute-zahl') == '9' and 'rot' in pg.get_attribute('#db-heute-zahl', 'class'))
    gr = pg.evaluate("[...document.querySelectorAll('#db-heute-liste .db-gruppe')].map(g => [g.querySelector('.db-gruppe-titel').textContent, g.querySelectorAll('.db-zeile').length])")
    je = {}
    for p in PUNKTE: je[p['art']] = je.get(p['art'], 0) + 1
    erwartet = [[n, min(3, je[a])] for a, n in (('ueberfaellig', 'Überfällig'), ('heute', 'Heute'), ('demnaechst', 'Demnächst')) if je.get(a)]
    check('Gruppen Überfällig, Heute, Demnächst – je höchstens drei Punkte', gr == erwartet, (gr, erwartet))
    zeile = pg.evaluate("""(() => { const z = [...document.querySelectorAll('#db-heute-liste a.db-zeile')].find(a => a.textContent.includes('Spedition Nord'));
        return z && [z.getAttribute('href'), z.querySelector('.db-zeile-meta').textContent, z.querySelector('.db-zeile-datum').className, getComputedStyle(z.querySelector('.db-zeile-datum')).color]; })()""")
    check('Punkt: Verweis auf den Reiter des Moduls, Modul und Einzelheit darunter, Datum rot (überfällig)', zeile and zeile[0] == '/module/leergut/#abstimmungen'
          and zeile[1].startswith('Leergut · Frist abgelaufen am') and 'ueberfaellig' in zeile[2] and zeile[3] == 'rgb(163, 25, 44)', zeile)
    texte = pg.evaluate("[...document.querySelectorAll('#db-heute-liste .db-zeile-titel')].map(e => e.textContent)")
    check('Texte der Module nur als Text (keine Auszeichnung)', pg.locator('#db-heute-liste img, #db-heute-liste script').count() == 0 and texte, texte)
    mehr = len(PUNKTE) > sum(n for _, n in erwartet)
    check('„Alle offenen Punkte“ nur, wenn eine Gruppe mehr als drei Punkte hat', pg.is_visible('#db-heute-alle') == mehr)
    if mehr:
        pg.click('#db-heute-alle'); pg.wait_for_function(f"document.querySelectorAll('#db-heute-liste .db-zeile').length === {len(PUNKTE)}")
        check('„Alle offenen Punkte“ zeigt alle, „Weniger anzeigen“ klappt zurück', pg.get_attribute('#db-heute-alle', 'aria-expanded') == 'true')
        pg.click('#db-heute-alle')
    # Schnellaktionen und Zuletzt bearbeitet
    akt = pg.evaluate("[...document.querySelectorAll('#db-aktionen-liste a')].map(a => [a.textContent.trim(), a.getAttribute('href')])")
    check('Schnellaktionen: die ersten vier wie im Entwurf, mit Verweis (Reiter bzw. Fenster zum Anlegen)', akt == [['Kundenangebot erstellen', '/admin/#einzel'],
          ['Urlaub beantragen', '/module/hr/#mein'], ['Interessent anlegen', '/module/crm/#kunden/neu'], ['Daten importieren', '/import/']], akt)
    zl_ui = pg.evaluate("[...document.querySelectorAll('#db-zuletzt-liste .db-zeile')].map(z => [z.dataset.modul, z.querySelector('.db-zeile-titel').textContent, z.querySelector('.db-zeile-meta').textContent])")
    check('Zuletzt bearbeitet: Text, Modul und Zeit („gerade eben“ / „vor … Min.“)', len(zl_ui) == len(zl) and zl_ui[0][0] == 'crm' and zl_ui[0][2].startswith('CRM · ')
          and all(('gerade eben' in m or 'vor ' in m or 'Uhr' in m) for _, _t, m in zl_ui), zl_ui)
    spalten = pg.evaluate("[document.querySelector('#db-heute').getBoundingClientRect().right < document.querySelector('#db-aktionen').getBoundingClientRect().left, Math.round(document.querySelector('#db-aktionen').getBoundingClientRect().width)]")
    check('1280 px: Heute für Sie links, Schnellaktionen und Zuletzt rechts (320 px)', spalten == [True, 320], spalten)

    # Seitenleiste: dieselben Module, Gruppen wie im Entwurf, Zahlen offener Punkte, Ziele wie die Kacheln
    L = leiste(pg)
    check('Seitenleiste: Start (aktiv), Anwendungen, In Entwicklung, Verwaltung & Daten', list(L) == ['', 'Anwendungen', 'In Entwicklung', 'Verwaltung & Daten']
          and L[''][0]['id'] == 'start' and L[''][0]['aktiv'] == 'page' and L[''][0]['href'] == './', list(L))
    check('Seitenleiste: freigegebene Anwendungen in der Reihenfolge des Registers als Verweise', [e['id'] for e in L['Anwendungen']] == FREI
          and all(e['tag'] == 'A' and not e['aktiv'] for e in L['Anwendungen']), [e['id'] for e in L['Anwendungen']])
    check('Seitenleiste: Einkauf und Container-Import unter „In Entwicklung“, ohne Verweis, mit „Bald“',
          [e['id'] for e in L['In Entwicklung']] == ['einkauf', 'containerimport'] and all(e['tag'] == 'SPAN' and e['aus'] == 'true' and not e['href']
          and e['bald'] == 'Bald' and 'bald verfügbar' in e['label'] for e in L['In Entwicklung']), L['In Entwicklung'])
    check('Seitenleiste: Import, Verwaltung, Sicherheit unten unter „Verwaltung & Daten“', [e['id'] for e in L['Verwaltung & Daten']] == ['import', 'verwaltung', 'sicherheit'])
    ziele = {e['id']: e['href'] for g in L.values() for e in g}
    check('Ziele im Testserver (gleicher Host): Eingabebereich, Import und Modulseiten', {m: ziele[m] for m in ('angebot', 'bestand', 'verwaltung', 'import', 'hr', 'crm', 'marketing', 'leergut', 'rewe', 'qs', 'controlling', 'sicherheit')}
          == {'angebot': '/admin/', 'bestand': '/admin/', 'verwaltung': '/admin/', 'import': '/import/', 'hr': '/module/hr/', 'crm': '/module/crm/', 'marketing': '/module/marketing/',
              'leergut': '/module/leergut/', 'rewe': '/module/rewe/', 'qs': '/module/qs/', 'controlling': '/module/controlling/', 'sicherheit': '/module/sicherheit/'}, ziele)
    check('Seitenleiste: gleiche Ziele wie die Kacheln', all(ziele[x['id']] == x['href'] for x in k if x['tag'] == 'A'), ziele)
    zahlen = pg.evaluate("""Object.fromEntries([...document.querySelectorAll('#r-leiste .r-eintrag')].filter(e => e.querySelector('.r-zahl'))
        .map(e => [e.dataset.modul, [e.querySelector('.r-zahl').textContent, e.querySelector('.r-zahl').classList.contains('r-zahl-rot'), e.getAttribute('aria-label')]]))""")
    check('Seitenleiste: Zahl offener Punkte je Anwendung, rot bei Überfälligem, auch in der Beschriftung', zahlen.get('qs') == ['3', True, 'Qualitätssicherung, 3 offen, davon 2 überfällig']
          and zahlen.get('hr') == ['1', False, 'HR, 1 offen'] and zahlen.get('rewe', [''])[0] == '2' and 'crm' not in zahlen and 'angebot' not in zahlen, zahlen)
    check('Seitenleiste: Symbolfarbe je Registersymbol', pg.evaluate("getComputedStyle(document.querySelector('#r-leiste [data-modul=\"crm\"] svg')).color") == 'rgb(46, 94, 158)')
    check('Seitenleiste: Name des angemeldeten Nutzers, Rolle und Initialen im Fuß', pg.text_content('#r-nutzer-name') == 'Administrator' and 'Angemeldet als' in pg.text_content('.r-person')
          and pg.text_content('#r-rolle') == 'Administrator' and pg.text_content('#r-initialen') == 'AD', pg.text_content('.r-fuss'))
    check('Seitenleiste: Abmelden als Knopf mit Beschriftung', pg.get_attribute('#r-abmelden', 'aria-label') == 'Abmelden')
    check('Seitenleiste: Suchfeld mit Tastenkürzel (Strg K)', pg.text_content('#r-suche .r-taste') == 'Strg K' and pg.get_attribute('#r-suche', 'aria-haspopup') == 'dialog')
    ueberlauf = pg.evaluate(UEBERLAUF)
    check('Namen und Texte passen in Kachel, Liste und Seitenleiste', not ueberlauf, ueberlauf)
    kontrast_ok(pg, 'hell')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280.png'), full_page=True)

    # ── Suche (Strg K, Feld in der Seitenleiste; kein eigener Knopf mehr auf der Startseite) ──
    pg.keyboard.press('Control+k'); pg.wait_for_selector('#r-palette[open]')
    check('Strg K öffnet die Suche, Fokus im Suchfeld, alle Anwendungen und Schnellaktionen', pg.evaluate("document.activeElement.id") == 'r-palette-eingabe'
          and pg.locator('#r-palette [role="option"]').count() == len(FREI) + 3 + len(H['aktionen']))
    pg.keyboard.type('qualit')
    tr = pg.evaluate("[...document.querySelectorAll('#r-palette [role=\"option\"]')].map(o => [o.textContent.trim(), o.getAttribute('href'), o.getAttribute('aria-selected')])")
    check('Suche „qualit“: Qualitätssicherung (ohne Umlaut-Probleme), erster Treffer gewählt', tr == [['Qualitätssicherung', '/module/qs/', 'true']], tr)
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_suche.png'))
    pg.fill('#r-palette-eingabe', 'urlaub')
    tr = pg.evaluate("[...document.querySelectorAll('#r-palette [role=\"option\"]')].map(o => [o.textContent.trim(), o.getAttribute('href')])")
    check('Suche findet Schnellaktionen („Urlaub beantragen“ → HR, Reiter „Mein Urlaub“)', tr == [['Urlaub beantragen', '/module/hr/#mein']], tr)
    pg.fill('#r-palette-eingabe', 'gibt es nicht')
    check('Suche ohne Treffer: Hinweis', pg.text_content('#r-palette-liste') == 'Nichts gefunden.')
    pg.mouse.click(20, 860)   # Klick daneben (Hintergrund) – Fenster schließen nur mit Escape oder Kreuz (Vorgabe 02.11.2026)
    check('Klick neben die Suche schließt sie nicht', pg.locator('#r-palette[open]').count() == 1)
    pg.keyboard.press('Escape'); pg.wait_for_selector('#r-palette', state='hidden')
    check('Escape schließt die Suche', pg.locator('#r-palette[open]').count() == 0)
    check('kein Blitz-Knopf mehr im Kopf der Startseite (Suche steht in der Seitenleiste)', pg.locator('#db-schnell').count() == 0
          and pg.locator('.r-seitenkopf .r-aktionen .r-rund').count() == 2)
    pg.click('#r-suche'); pg.wait_for_selector('#r-palette[open]')
    pg.keyboard.type('rew'); pg.keyboard.press('ArrowDown')
    sel = pg.evaluate("[...document.querySelectorAll('#r-palette [role=\"option\"]')].map(o => [o.textContent.trim(), o.getAttribute('aria-selected')])")
    check('Suchfeld der Leiste öffnet die Suche; Pfeiltasten wählen (REWE, REWE-Wochenabfrage)', sel == [['REWE', 'false'], ['REWE-Wochenabfrage', 'true']]
          and pg.get_attribute('#r-palette-eingabe', 'aria-activedescendant') == 'r-palette-1', sel)
    pg.keyboard.press('Enter'); pg.wait_for_url(lambda u: '/module/rewe/' in u)
    check('Enter öffnet den gewählten Treffer (REWE, Reiter „Woche“)', '/module/rewe/#woche' in pg.url, pg.url)
    pg.goto(B + '/dashboard/'); bereit(pg)
    pg.click('#r-suche'); pg.wait_for_selector('#r-palette[open]'); pg.click('.r-palette-zu'); pg.wait_for_selector('#r-palette', state='hidden')
    check('Suchfeld der Leiste öffnet die Suche; Schließen gibt den Fokus zurück', pg.evaluate("document.activeElement.id") == 'r-suche')

    # ── Schnellaktionen mit Fenster: „<reiter>/neu“ öffnet im Modul gleich das Fenster zum Anlegen ──
    pg.click('#db-aktionen-liste a[href$="#kunden/neu"]'); pg.wait_for_selector('#dlg-interessent[open]')
    check('„Interessent anlegen“: CRM öffnet „Neuer Interessent“, Adresse auf den Reiter gekürzt (Neuladen öffnet nicht erneut)',
          pg.text_content('#interessent-titel') == 'Neuer Interessent' and pg.evaluate('location.hash') == '#kunden'
          and pg.get_attribute('#crm-tabs button[data-tab="kunden"]', 'aria-selected') == 'true', pg.evaluate('location.hash'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#dlg-interessent', state='hidden')
    pg.goto(B + '/module/marketing/#kalender/neu'); pg.wait_for_selector('#dlg-beitrag[open]')
    check('„Beitrag anlegen“: Marketing öffnet einen neuen Beitrag im Redaktionsplan', pg.evaluate('location.hash') == '#kalender' and pg.input_value('#bt-titel') == '')
    pg.goto(B + '/dashboard/'); bereit(pg)

    # ── Favoriten bearbeiten (am Konto) ──
    pg.click('#db-fav-bearbeiten'); pg.wait_for_selector('#db-fav-wahl:not([hidden])')
    chips = pg.evaluate("[...document.querySelectorAll('.db-fav-chip')].map(b => [b.dataset.modul, b.getAttribute('aria-pressed')])")
    check('Bearbeiten: alle nutzbaren Anwendungen (ohne „Bald“) als Schalter, Favoriten gedrückt', [c for c, _ in chips] == FREI + ['import', 'verwaltung', 'sicherheit']
          and [c for c, p in chips if p == 'true'] == ['angebot', 'bestand', 'leergut', 'crm'] and pg.is_hidden('#db-grid') and pg.is_hidden('#db-fav-bearbeiten'), chips)
    pg.click('.db-fav-chip[data-modul="crm"]'); pg.click('.db-fav-chip[data-modul="qs"]')
    check('Zähler in der Erklärung (4 von 8)', '(4 von 8)' in pg.text_content('#db-fav-text'))
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_favoriten.png'))
    pg.click('#db-fav-speichern'); pg.wait_for_selector('#db-fav-wahl', state='hidden')
    check('Gespeichert: Favoriten in der Reihenfolge des Registers', [x['id'] for x in kacheln(pg)] == ['angebot', 'bestand', 'leergut', 'qs']
          and A.call('start_heute')[1]['favoriten'] == ['angebot', 'bestand', 'leergut', 'qs'] and pg.evaluate("document.activeElement.id") == 'db-fav-bearbeiten')
    pg.reload(); bereit(pg)
    check('nach dem Neuladen: eigene Favoriten (kein Springen von der Standardauswahl)', [x['id'] for x in kacheln(pg)] == ['angebot', 'bestand', 'leergut', 'qs'])
    pg.click('#db-fav-bearbeiten'); pg.wait_for_selector('#db-fav-wahl:not([hidden])')
    for m in ('crm', 'rewe', 'hr', 'marketing'):
        pg.click(f'.db-fav-chip[data-modul="{m}"]')
    voll = pg.evaluate("[...document.querySelectorAll('.db-fav-chip')].filter(b => b.disabled).map(b => b.dataset.modul)")
    check('höchstens acht: weitere Schalter gesperrt', voll and all(m not in voll for m in ('crm', 'rewe', 'hr', 'marketing')) and '(8 von 8)' in pg.text_content('#db-fav-text'), voll)
    pg.click('#db-fav-abbrechen'); pg.wait_for_selector('#db-fav-wahl', state='hidden')
    check('Abbrechen verwirft die Auswahl', [x['id'] for x in kacheln(pg)] == ['angebot', 'bestand', 'leergut', 'qs'])

    # Schmale Leiste (nicht festgestellt): nur Symbole, Namen als Beschriftung, aktiver Eintrag markiert, Zahl als Punkt
    pg.mouse.move(900, 600)
    pg.evaluate("""Promise.all([fetch('../api/?action=module_status').then(r => r.json()), fetch('../api/?action=status').then(r => r.json()), fetch('../api/?action=start_heute').then(r => r.json())])
        .then(([d, s, h]) => { STAFL_RAHMEN.zeichnen({ module: d.module, aktiv: 'crm', nutzer: Object.assign({}, s.user, { leiste: '' }), start: './', abmelden() {} }); STAFL_RAHMEN.zahlen(h.zahlen); })""")
    pg.wait_for_selector('.r-app.r-bereit:not(.r-fest):not(.r-auf)'); bilder(pg)
    schmal = pg.evaluate("""(() => { const n = document.querySelector('#r-leiste');
        return { breite: Math.round(n.getBoundingClientRect().width), texte: [...n.querySelectorAll('.r-text, .r-gruppe-titel, .r-person, .r-bald, .r-taste')].every(e => getComputedStyle(e).display === 'none'),
                 namen: [...n.querySelectorAll('a.r-eintrag')].every(e => e.getAttribute('aria-label') && e.title), aktiv: [...n.querySelectorAll('[aria-current="page"]')].map(e => e.dataset.modul),
                 trenner: [...n.querySelectorAll('.r-trenner')].filter(e => getComputedStyle(e).display === 'block').length,
                 abmelden: document.querySelector('#r-abmelden').getBoundingClientRect().width > 0, suche: document.querySelector('#r-suche').getBoundingClientRect().width,
                 punkt: (() => { const z = n.querySelector('[data-modul="qs"] .r-zahl').getBoundingClientRect(); return [Math.round(z.width), Math.round(z.height)]; })() }; })()""")
    check('schmale Leiste: 60 px, nur Symbole, jeder Eintrag beschriftet (Tooltip), CRM aktiv, Trenner statt Überschriften, Abmelden und Suche erreichbar, Zahl als Punkt',
          schmal['breite'] == 60 and schmal['texte'] and schmal['namen'] and schmal['aktiv'] == ['crm'] and schmal['trenner'] == 3 and schmal['abmelden']
          and 0 < schmal['suche'] <= 44 and schmal['punkt'] == [8, 8], schmal)
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_schmal.png'))
    pg.reload(); bereit(pg)

    # Gemeldet: „Qualitätssicherungskon-zept“ – Namen werden nicht mehr automatisch getrennt
    for breite in (1920, 1280, 1024, 768, 575, 390, 360):
        pg.set_viewport_size({'width': breite, 'height': 900}); bilder(pg)
        namen = pg.evaluate(WORT_GETRENNT)
        check(f'{breite} px: Registernamen ohne Silbentrennung und ohne Umbruch im Wort (auch „Qualitätssicherung“)',
              all(not g and not u and h != 'auto' for _, g, u, _f, h in namen), namen)
        ueber = pg.evaluate(UEBERLAUF)
        check(f'{breite} px: kein Name ragt aus Kachel, Liste oder Seitenleiste', not ueber, ueber)
        check(f'{breite} px: kein waagerechtes Scrollen', not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    pg.set_viewport_size({'width': 1280, 'height': 900}); bilder(pg)
    echt = pg.evaluate("""fetch('../api/?action=module_status').then(r => r.json()).then(d => {
        const alle = Object.fromEntries(d.module.map((m) => [m.id, m]));
        return ['angebot', 'verwaltung', 'bestand', 'import', 'hr'].map((id) => [window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'dashboard-stafl.de'),
                                                      window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'angebot.stafl.test')]); })""")
    check('Echtbetrieb (dashboard-stafl.de): Kacheln und Seitenleiste führen zu den Hosts der zentralen Anmeldung, nicht zum bisherigen /admin/',
          echt == [['https://angebot.dashboard-stafl.de/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/admin/', '/admin/'],
                   ['https://bestand.dashboard-stafl.de/admin/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/import/', '/import/'],
                   ['https://hr.dashboard-stafl.de/module/hr/', '/module/hr/']], echt)
    pg.click('#r-leiste a[data-modul="crm"]'); pg.wait_for_url('**/module/crm/')
    check('Klick auf CRM in der Seitenleiste öffnet das CRM', pg.url.endswith('/module/crm/'))
    pg.goto(B + '/dashboard/'); bereit(pg)
    pg.click('#db-grid a[data-modul="angebot"]'); pg.wait_for_url('**/admin/')
    check('Klick auf die Kachel Angebot öffnet die Mitarbeiter-Eingabe', pg.url.endswith('/admin/'))
    ctx.close()

    # ── Überlange Registernamen (nachgestellte Antwort): erst kleinere Schrift, Trennung nur als Notlösung ──
    check('Favoriten für den Test der langen Namen', A.call('start_favoriten_save', {'favoriten': ['angebot', 'crm', 'rewe', 'qs']})[0] == 200)
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.47')
    def lange_namen(route):
        r = route.fetch(); d = r.json()
        for m in d['module']:
            if m['id'] == 'qs': m['name'] = 'Qualitätssicherungskonzept'
            if m['id'] == 'crm': m['name'] = 'Kundenbeziehungsmanagement'
        route.fulfill(response=r, body=json.dumps(d))
    pg.route('**/api/?action=module_status', lange_namen); pg.reload(); bereit(pg)
    for breite in (1280, 1024, 575, 390):
        pg.set_viewport_size({'width': breite, 'height': 900}); bilder(pg)
        namen = pg.evaluate(WORT_GETRENNT)
        lang = [x for x in namen if x[0] in ('Qualitätssicherungskonzept', 'Kundenbeziehungsmanagement')]
        check(f'{breite} px: überlange Namen erst mit kleinerer Schrift; Umbruch nur als Notlösung in kleinster Schrift (12 px)',
              len(lang) == 2 and all(f < 15 and (not u or f == 12) for _, _g, u, f, _h in lang), lang)
        check(f'{breite} px: kurze Namen behalten ihre Schriftgröße (15 px)', all(f == 15 for n, _g, _u, f, _h in namen if n in ('Angebot', 'REWE')), namen)
        ueber = pg.evaluate(UEBERLAUF)
        check(f'{breite} px: überlange Namen ragen weder aus der Kachel noch aus der Seitenleiste', not ueber, ueber)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_lange_namen.png'), full_page=True)
    hoehen = pg.evaluate("[...document.querySelectorAll('#db-grid .db-tile')].map(t => Math.round(t.getBoundingClientRect().top) + ':' + Math.round(t.getBoundingClientRect().height))")
    reihen = {}
    for h in hoehen: reihen.setdefault(h.split(':')[0], set()).add(h.split(':')[1])
    check('Kacheln einer Reihe gleich hoch (auch wenn ein Name umbricht)', all(len(v) == 1 for v in reihen.values()), hoehen)
    ctx.close()
    check('Favoriten zurück auf Standard', A.call('start_favoriten_save', {'favoriten': None})[0] == 200)

    # ── Begrüßung nach Tageszeit mit Vornamen und Datum (feste Uhr, Europe/Berlin), dunkles Design am Desktop ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.46', dunkel=True, uhr=datetime(2026, 10, 22, 19, 30, tzinfo=BERLIN))
    check('Datum deutsch ausgeschrieben', pg.text_content('#db-datum') == 'Donnerstag, 22. Oktober', pg.text_content('#db-datum'))
    check('abends: „Guten Abend, <Vorname>“ als Hauptüberschrift', pg.text_content('#db-titel') == 'Guten Abend, Administrator' and pg.evaluate("document.querySelector('#db-titel').tagName") == 'H1',
          pg.text_content('#db-titel'))
    grenzen = pg.evaluate("[0, 4, 5, 10, 11, 17, 18, 23].map((h) => window.STAFL_GRUSS(h))")
    check('Begrüßung: Grenzen 5/11/18 Uhr', grenzen == ['Guten Abend', 'Guten Abend', 'Guten Morgen', 'Guten Morgen', 'Guten Tag', 'Guten Tag', 'Guten Abend', 'Guten Abend'], grenzen)
    hg = pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('#r-leiste')).backgroundColor]")
    check('dunkles Design folgt der Systemeinstellung (Grund #121011, Seitenleiste #1b1a19)', hg == ['rgb(18, 16, 17)', 'rgb(27, 26, 25)'], hg)
    aus = pg.evaluate("getComputedStyle(document.querySelector('#r-leiste [data-modul=\"einkauf\"] svg')).color")
    check('dunkel: Symbol nicht freigegebener Anwendungen bleibt zurückgenommen (keine Modulfarbe)', aus == 'rgb(111, 104, 99)', aus)
    rot = pg.evaluate("[getComputedStyle(document.querySelector('#r-leiste .r-zahl-rot')).backgroundColor, getComputedStyle(document.querySelector('#r-leiste .r-zahl-rot')).color]")
    check('dunkel: rote Zahl hell mit dunkler Schrift (lesbar)', rot == ['rgb(243, 160, 170)', 'rgb(42, 16, 20)'], rot)
    kontrast_ok(pg, 'dunkel')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_dunkel.png'), full_page=True)
    pg.clock.set_fixed_time(datetime(2026, 10, 23, 8, 15, tzinfo=BERLIN)); pg.reload(); bereit(pg)
    check('morgens: „Guten Morgen, <Vorname>“, Datum des Tages', pg.text_content('#db-titel') == 'Guten Morgen, Administrator' and pg.text_content('#db-datum') == 'Freitag, 23. Oktober',
          (pg.text_content('#db-titel'), pg.text_content('#db-datum')))
    # Weniger Transparenz und weniger Bewegung (Systemeinstellungen)
    cdp = ctx.new_cdp_session(pg)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-transparency', 'value': 'reduce'}]})
    deckend = pg.evaluate("[...document.querySelectorAll('#r-leiste, .db-tile, .db-liste')].map(e => getComputedStyle(e).backgroundColor)")
    check('deckende Flächen (auch bei „Transparenz reduzieren“ kein Glas nötig)', all(c.startswith('rgb(') for c in deckend), deckend)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
    pg.wait_for_function("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration === '0s'")
    check('weniger Bewegung: keine Übergänge an den Kacheln', pg.evaluate("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration") == '0s')
    ctx.close()

    # ── Mobil (390 px) und dunkles Design: Kopfzeile mit Menü, Seitenleiste als Menü ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.42', breite=390, dunkel=True)
    breiter = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    check('390 px: kein waagerechtes Scrollen', not breiter)
    kopf = pg.evaluate("""(() => { const t = document.querySelector('.r-mobilkopf').getBoundingClientRect();
        return [t.height > 0, [...document.querySelectorAll('.r-mobilkopf img, .r-mobilkopf button')].every(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.left >= t.left - 1 && r.right <= t.right + 1; }),
                getComputedStyle(document.querySelector('#r-leiste')).visibility, document.querySelector('#r-menue').getAttribute('aria-expanded')]; })()""")
    check('390 px: Kopfzeile mit Menüknopf und Logo, Seitenleiste eingeklappt (unsichtbar, nicht per Tab erreichbar)', kopf == [True, True, 'hidden', 'false'], kopf)
    pg.click('#r-menue'); pg.wait_for_function("Math.round(document.querySelector('#r-leiste').getBoundingClientRect().left) === 0")
    menue = pg.evaluate("""(() => { const n = document.querySelector('#r-leiste').getBoundingClientRect();
        return [document.querySelector('#r-menue').getAttribute('aria-expanded'), document.activeElement.closest('#r-leiste') !== null, Math.round(n.left), n.right <= innerWidth,
                ['#r-abmelden', '#r-initialen', '#r-suche', '#r-leiste a[data-modul="crm"]'].every(s => document.querySelector(s).getBoundingClientRect().width > 0),
                getComputedStyle(document.querySelector('#r-suche .r-taste')).display]; })()""")
    check('390 px: Menü öffnet die Seitenleiste (Fokus darin, ganz im Bild), Suche, Abmelden und Anwendungen erreichbar, ohne Tastenkürzel', menue == ['true', True, 0, True, True, 'none'], menue)
    check('390 px: im Menü kein Pin (das Menü ist ohnehin breit), Namen sichtbar', pg.evaluate("getComputedStyle(document.querySelector('#r-pin')).display") == 'none'
          and pg.evaluate("getComputedStyle(document.querySelector('#r-leiste [data-modul=\"crm\"] .r-text')).display") != 'none')
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_menue_dunkel.png'))
    pg.keyboard.press('Escape'); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'hidden'")
    check('390 px: Escape schließt das Menü, Fokus zurück auf den Menüknopf', pg.evaluate("[document.querySelector('#r-menue').getAttribute('aria-expanded'), document.activeElement.id]") == ['false', 'r-menue'])
    pg.click('#r-menue'); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'visible'")
    pg.mouse.click(370, 450); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'hidden'")
    check('390 px: Klick neben das Menü schließt es', pg.get_attribute('#r-menue', 'aria-expanded') == 'false')
    pg.click('#r-menue'); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'visible'")
    pg.click('#r-suche'); pg.wait_for_selector('#r-palette[open]')
    pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'hidden'")
    lage = pg.evaluate("(() => { const d = document.querySelector('#r-palette').getBoundingClientRect(); return [d.left >= 0, d.right <= innerWidth, getComputedStyle(document.querySelector('#r-leiste')).visibility]; })()")
    check('390 px: Suche aus dem Menü – Dialog im Bild, Menü geschlossen', lage == [True, True, 'hidden'], lage)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_suche_dunkel.png'))
    pg.keyboard.press('Escape'); pg.wait_for_selector('#r-palette', state='hidden')
    try:   # das Ereignis „close“ des Dialogs folgt dem Schließen etwas später
        pg.wait_for_function("document.activeElement && document.activeElement.id === 'r-menue'", timeout=3000)
    except Exception:
        pass
    check('390 px: nach dem Schließen der Suche Fokus auf dem Menüknopf (Menü ist zu)', pg.evaluate("document.activeElement.id") == 'r-menue', pg.evaluate("document.activeElement.id"))
    sichtbar = pg.evaluate("['#db-theme', '#db-darstellung'].map((s) => document.querySelector(s).getBoundingClientRect().width > 0)")
    check('390 px: Hell/Dunkel und einfache Darstellung erreichbar', all(sichtbar), sichtbar)
    spalten = pg.evaluate("getComputedStyle(document.querySelector('#db-grid')).gridTemplateColumns.split(' ').length")
    check('390 px: zwei Kachelspalten', spalten == 2, spalten)
    senkrecht = pg.evaluate("[...document.querySelectorAll('#db-grid .db-tile')].every(t => getComputedStyle(t).flexDirection === 'column')")
    check('390 px: Symbol über dem Namen', senkrecht)
    reihe = pg.evaluate("['#db-favoriten', '#db-heute', '#db-aktionen', '#db-zuletzt'].map(s => Math.round(document.querySelector(s).getBoundingClientRect().top))")
    check('390 px: Favoriten, Heute für Sie, Schnellaktionen, Zuletzt bearbeitet untereinander', reihe == sorted(reihe), reihe)
    zahl = pg.evaluate("""(() => { const t = document.querySelector('#db-grid [data-modul="leergut"]'), z = t.querySelector('.db-zahl').getBoundingClientRect(), n = t.querySelector('.db-name').getBoundingClientRect(),
        i = t.querySelector('.db-ico').getBoundingClientRect(), k = t.getBoundingClientRect(); return [z.left >= i.right, z.bottom <= n.top, z.right <= k.right]; })()""")
    check('390 px: Zahl an der Kachel oben rechts, verdeckt weder Namen noch Symbol', zahl == [True, True, True], zahl)
    gross = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#db-titel')).fontSize)")
    check('390 px: Überschrift 26 px', gross == 26, gross)
    ueberlauf = pg.evaluate(UEBERLAUF)
    check('390 px: Namen und Texte passen', not ueberlauf, ueberlauf)
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design folgt der Systemeinstellung', hg == 'rgb(18, 16, 17)', hg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_dunkel.png'), full_page=True)
    pg.click('#db-theme'); pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'")
    gespeichert = pg.evaluate("localStorage.getItem('wochenangebot.theme')")
    check('Umschalter speichert das Design wie die Angebotsseite', json.loads(gespeichert or 'null') == 'light', gespeichert)
    pg.reload(); bereit(pg)
    check('gewähltes Design bleibt nach dem Neuladen', pg.evaluate("document.documentElement.getAttribute('data-theme')") == 'light')
    check('helles Design trotz dunkler Systemeinstellung', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(246, 244, 241)')
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_hell.png'), full_page=True)
    ctx.close()

    # ── Geplante Wartung: gelber Hinweis mit Zeitraum, schließbar (bleibt geschlossen) ──
    morgen = datetime.now() + timedelta(days=1)
    ab, bis = morgen.strftime('%Y-%m-%dT22:00'), morgen.strftime('%Y-%m-%dT23:00')
    st, r = A.call('modul_wartung_save', {'bereich': 'crm.intern', 'active': True, 'grund': 'Test Hinweis', 'message': 'Das CRM ist in dieser Zeit kurz nicht erreichbar.', 'ab': ab, 'until': bis})
    check('Wartung des CRM für morgen 22–23 Uhr geplant', st == 200, (st, r))
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.48')
    hw = pg.evaluate("[...document.querySelectorAll('#db-hinweise .db-hinweis')].map(h => h.textContent.trim())")
    tag_text = morgen.strftime('%-d')
    check('Hinweis: „Wartung am <Wochentag>, <Tag>. <Monat>, 22:00–23:00 Uhr · CRM. <Text>“', len(hw) == 1 and hw[0].startswith('Wartung am ') and f', {tag_text}. ' in hw[0]
          and '22:00–23:00 Uhr · CRM. Das CRM ist in dieser Zeit kurz nicht erreichbar.' in hw[0], hw)
    check('Hinweis: gelb (Warnfarbe), Kontrast der Schrift ausreichend', pg.evaluate(KONTRAST, ['.db-hinweis p', '.db-hinweis strong'])[0][1] >= 4.5
          and pg.evaluate("getComputedStyle(document.querySelector('.db-hinweis')).backgroundColor") == 'rgb(251, 239, 217)')
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_geplant.png'))
    pg.click('.db-hinweis-zu'); pg.wait_for_selector('.db-hinweis', state='detached')
    pg.reload(); bereit(pg)
    check('geschlossener Hinweis bleibt geschlossen (dieses Gerät)', pg.locator('.db-hinweis').count() == 0)
    ctx.close()
    check('geplante Wartung aufgehoben', A.call('modul_wartung_save', {'bereich': 'crm.intern', 'active': False, 'grund': 'Test beendet'})[0] == 200)

    # ── Laufende Wartung des Eingabebereichs: Bearbeiter gesperrt, Administrator mit Hinweis ──
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Dashboard',
                                          'message': 'Kurz weg <img src=x onerror="window.__xss=1"> Infos: https://angebot-stafl.de/hinweise/wartungsfenster-oktober-2026'})
    check('Wartung des Eingabebereichs gestartet', st == 200 and r.get('aktiv') is True, (st, r))
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.43')
    a = kacheln(pg)[0]
    check('Bearbeiter: Favorit Angebot in Wartung, ohne Verweis', a['id'] == 'angebot' and a['tag'] == 'DIV' and not a['href'] and a['badge'] == 'Wartung', a)
    check('Wartung bleibt eigener Zustand: sichtbare Wartungs-Pille, kein Klebeband', 'warn' in a['badgeCls'] and a['badgeSichtbar'] and not a['bald'] and not a['gesperrt'], a)
    check('Bearbeiter: Initialen „EE“, Vorname in der Begrüßung', pg.text_content('#r-initialen') == 'EE' and pg.text_content('#db-titel').endswith(', Erika'),
          (pg.text_content('#r-initialen'), pg.text_content('#db-titel')))
    check('Bearbeiter: Wartungshinweis in Kachel und gelbem Hinweis als Text (kein HTML)', 'Kurz weg <img' in a['hint'] and a['bilder'] == 0 and not pg.evaluate('window.__xss')
          and pg.locator('#db-hinweise img').count() == 0 and 'Wartung läuft · Angebot. Kurz weg <img' in pg.text_content('#db-hinweise'), (a, pg.text_content('#db-hinweise')))
    check('Bearbeiter: keine offenen Punkte – „Alles erledigt“', pg.locator('#db-heute-liste .db-erledigt').count() == 1 and pg.is_hidden('#db-heute-zahl')
          and pg.text_content('#db-sub') == 'keine offenen Punkte', pg.text_content('#db-sub'))
    check('Bearbeiter: Schnellaktionen nur mit Recht und nutzbarem Modul (Angebot in Wartung fehlt)', pg.evaluate("[...document.querySelectorAll('#db-aktionen-liste a')].map(a => a.textContent.trim())")
          == ['Urlaub beantragen', 'Daten importieren'])
    # Controlling: Modulzugang standardmäßig niemand (Finanzdaten, 28.10.2026) – Eintrag fehlt Bearbeitern ganz
    L = leiste(pg)
    ang = next(e for e in L['Anwendungen'] if e['id'] == 'angebot')
    check('Bearbeiter: Seitenleiste ohne Controlling; Angebot ohne Verweis mit Stand „Wartung“', 'controlling' not in [e['id'] for g in L.values() for e in g]
          and ang['tag'] == 'SPAN' and ang['aus'] == 'true' and ang['stand'] == 'Wartung' and '(Wartung)' in ang['label'], ang)
    check('Bearbeiter: Bestand, Leergut, CRM, REWE, Qualitätssicherung, HR, Marketing verfügbar, Import und Verwaltung unten', [e['id'] for e in L['Anwendungen'] if e['tag'] == 'A']
          == ['bestand', 'leergut', 'crm', 'rewe', 'qs', 'hr', 'marketing'] and [e['id'] for e in L['Verwaltung & Daten']] == ['import', 'verwaltung'], L)
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_bearbeiter.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.44')
    a = kacheln(pg)[0]
    check('Administrator: Angebot in Wartung, aber weiter erreichbar', a['tag'] == 'A' and a['badge'] == 'Wartung – Zugang für Administratoren', a)
    check('Administrator: Wartungs-Pille ohne Klebeband', 'warn' in a['badgeCls'] and a['badgeSichtbar'] and not a['bald'], a)
    ang = next(e for e in leiste(pg)['Anwendungen'] if e['id'] == 'angebot')
    check('Administrator: Angebot in der Seitenleiste als Verweis mit Stand „Wartung“', ang['tag'] == 'A' and ang['stand'] == 'Wartung', ang)
    pg.set_viewport_size({'width': 360, 'height': 900}); bilder(pg)
    zu = pg.evaluate("(() => { const s = getComputedStyle(document.querySelector('#r-leiste')); return [s.visibility, s.transitionDuration]; })()")
    check('Wechsel von breit auf schmal: Seitenleiste sofort eingeklappt (ohne Hineinrutschen)', zu[0] == 'hidden' and zu[1] in ('0s', '0s, 0s'), zu)
    lage = pg.evaluate("""(() => { const t = document.querySelector('#db-grid [data-modul="angebot"]'), k = t.getBoundingClientRect(), h = t.querySelector('.db-hint'), p = t.querySelector('.db-badge');
        const pr = p.getBoundingClientRect(), s = getComputedStyle(p);
        return {hinweis: h.scrollWidth <= h.clientWidth + 1 && h.getBoundingClientRect().right <= k.right - 8, pille: pr.right <= k.right - 8 && pr.left >= k.left,
                zeilen: Math.round(pr.height / parseFloat(s.lineHeight)), radius: parseFloat(s.borderTopLeftRadius)}; })()""")
    check('360 px: langer Wartungshinweis (Adresse) bricht innerhalb der Kachel um', lage['hinweis'], lage)
    check('360 px: lange Pille „Wartung – Zugang für Administratoren“ bleibt in der Kachel, mehrzeilig als abgerundetes Feld', lage['pille'] and lage['zeilen'] >= 2 and lage['radius'] <= 13, lage)
    check('360 px: kein waagerechtes Scrollen (auch mit langem Hinweis)', not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_admin_360.png'), full_page=True)
    ctx.close()
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': 'Test beendet'})
    check('Wartung beendet', st == 200 and r.get('aktiv') is False, (st, r))

    # ── Abmelden (Knopf in der Seitenleiste) beendet die Sitzung serverseitig ──
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.45')
    check('nach der Wartung wieder verfügbar', kacheln(pg)[0]['badge'] == 'Verfügbar' and pg.locator('.db-hinweis').count() == 0)
    pg.click('#r-abmelden'); pg.wait_for_selector('#db-login:not([hidden])')
    angemeldet = pg.evaluate("fetch('../api/?action=status', {credentials: 'same-origin'}).then(r => r.json()).then(j => j.loggedIn)")
    check('Abmelden: Anmeldehinweis, Seitenleiste entfernt, Sitzung beendet', angemeldet is False and pg.is_hidden('#db-bereich') and pg.is_hidden('#r-leiste')
          and pg.locator('#r-leiste .r-eintrag').count() == 0, angemeldet)
    pg.keyboard.press('Control+k')
    check('nach dem Abmelden: keine Suche mehr', pg.locator('#r-palette[open]').count() == 0)
    pg.reload(); pg.wait_for_selector('#db-login:not([hidden])')
    check('nach dem Neuladen weiter abgemeldet', pg.is_hidden('#db-bereich'))
    check('Anmeldehinweis als deckende Karte mit echtem Link', pg.evaluate("getComputedStyle(document.querySelector('#db-login')).backgroundColor") == 'rgb(255, 255, 255)'
          and pg.evaluate("document.querySelector('#db-login a').tagName") == 'A')
    pg.goto(B + '/dashboard/abgemeldet.html'); pg.wait_for_selector('#db-abgemeldet')
    check('Abmeldeseite im neuen Design (Grund, Karte mit Logo, Link zur Anmeldung)', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(246, 244, 241)'
          and pg.get_attribute('#db-abgemeldet a', 'href') == './' and pg.locator('#db-abgemeldet img.r-logo').count() == 1
          and not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    check('Abmeldeseite: Knopf „Erneut anmelden“ ohne Unterstreichung', pg.evaluate("getComputedStyle(document.querySelector('#db-abgemeldet a')).textDecorationLine") == 'none')
    ctx.close()
    br.close()

# ── Weitere Quellen für „Heute für Sie“: Bestand (MHD-Liste) und Bestellwünsche (Angebot) ──
storage_write('bestand', {'date': tag(0), 'source': 'test', 'importedAt': tag(0) + 'T08:00:00+01:00', 'importedBy': 'Test', 'incoming': [], 'articles': [
    {'code': '1001', 'name': 'Rinderhüfte', 'kg': 50.0, 'mhd': tag(-1), 'mhdKg': 10.0, 'lots': []},
    {'code': '1002', 'name': 'Schweinenacken', 'kg': 40.0, 'mhd': tag(2), 'mhdKg': 5.0, 'lots': []},
    {'code': '1003', 'name': 'Kalbsrücken', 'kg': 30.0, 'mhd': tag(3), 'mhdKg': 5.0, 'lots': []},
    {'code': '1004', 'name': 'Lammkeule', 'kg': 20.0, 'mhd': tag(6), 'mhdKg': 4.0, 'lots': []},
    {'code': '1005', 'name': 'Putenbrust', 'kg': 10.0, 'mhd': tag(30), 'mhdKg': 2.0, 'lots': []}]})
storage_write('bestellungen', [
    {'nr': 'B-TEST-1', 't': tag(-1) + 'T09:00:00+01:00', 'firma': 'Kantine Test', 'workflow': 'neu', 'positions': [], 'total': 0, 'totalQty': 0},
    {'nr': 'B-TEST-2', 't': tag(0) + 'T07:00:00+01:00', 'firma': 'Kantine Test', 'workflow': 'neu', 'positions': [], 'total': 0, 'totalQty': 0},
    {'nr': 'B-TEST-3', 't': tag(-2) + 'T07:00:00+01:00', 'firma': 'Andere Firma', 'workflow': 'in_bearbeitung', 'assignee': ADMIN, 'positions': [], 'total': 0, 'totalQty': 0},
    {'nr': 'B-TEST-4', 't': tag(-3) + 'T07:00:00+01:00', 'firma': 'Andere Firma', 'workflow': 'erledigt', 'assignee': ADMIN, 'positions': [], 'total': 0, 'totalQty': 0}])
st, H2 = A.call('start_heute')
q = {(p['modul'], p['titel']): p for p in H2.get('punkte', []) if p['modul'] in ('bestand', 'angebot')}
check('Bestand: abgelaufenes MHD überfällig, MHD in höchstens 4 Tagen heute, in 5–7 Tagen demnächst (wie die Stufen der MHD-Liste), Ziel Bestandsliste',
      st == 200 and q.get(('bestand', '1 Artikel mit abgelaufenem MHD'), {}).get('art') == 'ueberfaellig' and q.get(('bestand', '2 Artikel mit MHD in höchstens 4 Tagen'), {}).get('art') == 'heute'
      and q.get(('bestand', '1 Artikel mit MHD in 5–7 Tagen'), {}).get('art') == 'demnaechst' and all(p['ziel'] == 'stock' for k, p in q.items() if k[0] == 'bestand')
      and H2['zahlen'].get('bestand') == {'offen': 4, 'ueberfaellig': 1}, q)
check('Bestand: nur Anzahlen, keine Artikel, Mengen oder Preise', not any(w in json.dumps(list(q.values()), ensure_ascii=False) for w in ('Rinderhüfte', 'kg', '€')), q)
check('Bestellwünsche: neue (Sammelpunkt) und die mir zugewiesenen in Bearbeitung, ohne Kundendaten, Ziel „Bestellwünsche“',
      q.get(('angebot', '2 neue Bestellwünsche'), {}).get('anzahl') == 2 and q.get(('angebot', 'Bestellwunsch bei Ihnen in Bearbeitung'), {}).get('ziel') == 'orders'
      and 'Kantine' not in json.dumps(list(q.values()), ensure_ascii=False) and H2['zahlen'].get('angebot') == {'offen': 3, 'ueberfaellig': 0}, q)
st, he2 = E.call('start_heute')
qe = {(p['modul'], p['titel']) for p in he2.get('punkte', [])}
check('Bearbeiter (Recht „MHD-Liste senden“ und „Bestellwünsche bearbeiten“ als Standard): MHD-Punkte und neue Bestellwünsche, nicht die des Administrators',
      ('bestand', '1 Artikel mit abgelaufenem MHD') in qe and ('angebot', '2 neue Bestellwünsche') in qe and ('angebot', 'Bestellwunsch bei Ihnen in Bearbeitung') not in qe, qe)
check('Vertrieb: Rechte „MHD-Liste senden“ und „Bestellwünsche bearbeiten“ entzogen', A.call('user_save', {'id': IDS['vera'], 'name': 'Vera Vertrieb', 'role': 'editor', 'active': True,
      'vertreter': '11', 'grant': ['crm.sehen'], 'deny': ['bestand.mhd_senden', 'bestellungen.bearbeiten']})[0] == 200)
V = Client('198.51.100.8'); V.call('login', {'username': 'vera', 'password': 'Dritter-Zugang-4712'})
check('ohne diese Rechte: keine Punkte aus Bestand und Bestellwünschen (eigene Rechteprüfung der Module)', [p['modul'] for p in V.call('start_heute')[1]['punkte']] == ['crm'])

check('keine JavaScript-Fehler', not fehler, fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
