"""HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht, Personalstelle hr.verwalten sieht sie auch).

Geprüft: Rechte serverseitig (GR-103: ohne Recht 403, ohne Anmeldung 401, mit hr.uebersicht oder hr.verwalten 200,
hr.uebersicht öffnet keine Personalstellen-Aktionen), Recht im Katalog (zuweisbar, ohne Standardrollen), Summen je
Mitarbeiter (Anspruch, genommen/geplant/beantragt, Rest, Krank- und Gleittage nur genehmigt und nur Arbeitstage –
4-Tage-Woche, Feiertage, freie Tage), nur Mitarbeiter im Urlaubsplan, Datenschutz (keine Zeiträume, Notizen, Gründe in
der Antwort), Oberfläche (Reiter nur mit Recht, Jahr wechseln, Abteilungsfilter, Summenzeile; Desktop, 390 px, dunkel).
Nur Testdaten.
"""
import datetime as dt
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def montag(jahr, monat, woche=1):
    d = dt.date(jahr, monat, 1)
    while d.weekday() != 0: d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=woche - 1)


def iso(d): return d.isoformat()


Y = dt.date.today().year + 1           # alles im nächsten Jahr: genehmigter Urlaub zählt als „geplant“
FEB = montag(Y, 2)
MRZ = montag(Y, 3, 2)
AUG = montag(Y, 8, 2)

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('lena', 'Lena Leser', 'viewer', 'Leser-Zugang-77', {}), ('paul', 'Paul Personal', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.verwalten']}),
                          ('uwe', 'Uwe Uebersicht', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.uebersicht']})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
st, r_ = A.call('user_save', {'id': '', 'vorname': 'Andre', 'nachname': 'Vierzig', 'role': 'viewer', 'active': True, 'zugang': False})
assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
L = Client('198.51.100.4'); L.call('login', {'username': 'lena', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.5'); P.call('login', {'username': 'paul', 'password': 'Personal-Zugang-77'})
U = Client('198.51.100.6'); U.call('login', {'username': 'uwe', 'password': 'Personal-Zugang-77'})
N = Client('198.51.100.7')

rev = P.call('mitarbeiter_hr')[1]['rev']


def hr(uid, **werte):
    global rev
    # eigene Urlaubsangaben ändert eine andere Person der Personalstelle (Vier-Augen-Prinzip) – für Paul der Administrator
    st, r = (A if uid == ids['paul'] else P).call('mitarbeiter_hr_save', {'nutzer': uid, 'rev': rev, **werte})
    assert st == 200, r
    rev = r['rev']


hr(ids['lena'], abteilung='Verwaltung', pos=1, jahr=Y, anspruch=30)
hr(ids['andre-vierzig'], abteilung='Lager', pos=2, arbeitstage=[1, 2, 3, 4], jahr=Y, anspruch=24)
for x in ('admin', 'paul', 'uwe'):
    hr(ids[x], aktiv=False)
PL, PA = ids['lena'], ids['andre-vierzig']

# ── Rechte ──
kat = {x['key']: x for x in A.call('rechte')[1]['catalog']}
check('Recht im Katalog: Gruppe HR, keine Standardrollen, setzt hr.antrag voraus', kat.get('hr.uebersicht', {}).get('default') == []
      and kat['hr.uebersicht']['requires'] == ['hr.antrag'] and kat['hr.uebersicht']['group'] == 'HR', kat.get('hr.uebersicht'))
check('ohne Anmeldung: 401', N.call('hr_uebersicht')[0] == 401)
check('ohne Recht: 403', L.call('hr_uebersicht')[0] == 403)
check('mit hr.uebersicht: 200', U.call('hr_uebersicht')[0] == 200)
check('Personalstelle (hr.verwalten): 200', P.call('hr_uebersicht')[0] == 200)
check('Administrator: 200', A.call('hr_uebersicht')[0] == 200)
check('hr.uebersicht öffnet keine Personalstelle (hr_verwaltung, Export, Einträge 403)', U.call('hr_verwaltung')[0] == 403
      and U.call('hr_export', {'jahr': Y, 'monate': [2]})[0] == 403 and U.call('hr_eintrag_save', {'person': PL, 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB)})[0] == 403)
check('hr_start meldet die Übersicht nur mit Recht', U.call('hr_start')[1].get('uebersicht') is True and P.call('hr_start')[1].get('uebersicht') is True
      and L.call('hr_start')[1].get('uebersicht') is False)
check('ungültiges Jahr: 400er-Antwort', U.call('hr_uebersicht&jahr=1800')[0] >= 400)

# ── Daten (Personalstelle trägt ein, Lena beantragt) ──
def eintrag(person, art, von, bis, notiz=''):
    st, r = P.call('hr_eintrag_save', {'person': person, 'art': art, 'von': iso(von), 'bis': iso(bis), 'notiz': notiz})
    assert st == 200, r
    return r['eintrag']['id']


eintrag(PL, 'U', FEB, FEB + dt.timedelta(days=2))                                         # 3 Tage Urlaub (geplant)
eintrag(PL, 'K', FEB + dt.timedelta(days=7), FEB + dt.timedelta(days=8), 'Arztbesuch-Notiz')  # 2 Krankheitstage
eintrag(PL, 'G', MRZ, MRZ)                                                                # 1 Gleittag
weih = dt.date(Y, 12, 22)
eintrag(PL, 'K', weih, weih + dt.timedelta(days=6))                                       # über Weihnachten
erw_weih = sum(1 for i in range(7) if (weih + dt.timedelta(days=i)).weekday() < 5 and (weih + dt.timedelta(days=i)).strftime('%m-%d') not in ('12-25', '12-26'))
eintrag(PA, 'K', AUG, AUG + dt.timedelta(days=4))                                         # Mo–Fr, 4-Tage-Woche: 4
storno = eintrag(PA, 'G', AUG + dt.timedelta(days=7), AUG + dt.timedelta(days=7))
check('stornierter Gleittag', P.call('hr_eintrag_save', {'id': storno, 'stornieren': True})[0] == 200)
st, r = L.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=1)), 'notiz': 'Sommerreise-Notiz'})
check('Lena beantragt 2 Tage', st == 200, r)

st, r, raw = U.call('hr_uebersicht&jahr=' + str(Y), raw=True)
z = {x['id']: x for x in r['zeilen']}
check('nur Mitarbeiter im Urlaubsplan', set(z) == {PL, PA}, sorted(z))
lz = z.get(PL, {})
check('Lena: Anspruch 30, geplant 3, beantragt 2, Rest 27', (lz.get('anspruch'), lz.get('geplant'), lz.get('beantragt'), lz.get('genommen'), lz.get('rest')) == (30, 3, 2, 0, 27), lz)
check(f'Lena: Krank 2 + {erw_weih} über Weihnachten (ohne Wochenende und Feiertage), Gleittage 1', lz.get('krank') == 2 + erw_weih and lz.get('gleittage') == 1, lz)
az = z.get(PA, {})
check('Andre (4-Tage-Woche): Krank Mo–Fr = 4, stornierter Gleittag zählt nicht', az.get('krank') == 4 and az.get('gleittage') == 0 and az.get('anspruch') == 24 and az.get('rest') == 24, az)
check('Reihenfolge nach Abteilung/Position', [x['id'] for x in r['zeilen']] == [PL, PA], [x['name'] for x in r['zeilen']])
check('Datenschutz: keine Zeiträume, Notizen, Gründe oder Entscheidungen in der Antwort',
      'Notiz' not in raw and not re.search(r'\d{4}-\d{2}-\d{2}', raw.replace('"heute":"' + r['heute'] + '"', '')) and 'entscheidung' not in raw
      and not any(k in x for x in r['zeilen'] for k in ('von', 'bis', 'notiz', 'eintraege', 'personalnummer')), raw[:300])
check('anderes Jahr: Konto ohne Einträge', all(x['krank'] == 0 and x['geplant'] == 0 for x in U.call('hr_uebersicht&jahr=' + str(Y - 2))[1]['zeilen']))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll ohne Art der Abwesenheit (Krankheit)', not re.search(r'HR:[^"]*Krank', log) and 'Arztbesuch' not in log)

# ── Oberfläche ──
fehler = []
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    for breite in (1280, 390):
        ctx, pg = anmelden('uwe', 'Personal-Zugang-77', '198.51.100.6', breite)
        pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector('#ueb-tabelle thead')
        check(f'{breite}px: Reiter Übersicht sichtbar, Anträge und Export nicht', pg.is_visible('[data-tab="uebersicht"]') and not pg.is_visible('[data-tab="antraege"]')
              and not pg.is_visible('[data-tab="export"]'))
        pg.click('#tab-uebersicht [data-ujahr="1"]')
        # neues Jahr geladen: Summenzeile mit dem Anspruch des Folgejahres (Titel wechselt schon vor der Antwort)
        pg.wait_for_function('(document.querySelector("#ueb-tabelle tfoot") || {}).textContent?.includes("54")')
        zeile = pg.text_content('#ueb-tabelle tbody')
        check(f'{breite}px: Tabelle mit Abteilungen und Zahlen', 'Verwaltung' in zeile and 'Lager' in zeile and 'Lena Leser' in zeile and 'Andre Vierzig' in zeile, zeile[:200])
        check(f'{breite}px: Summenzeile (2 Mitarbeiter, Anspruch 54)', 'Summe (2)' in pg.text_content('#ueb-tabelle tfoot') and '54' in pg.text_content('#ueb-tabelle tfoot'))
        check(f'{breite}px: kein waagerechtes Scrollen der Seite', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_uebersicht_{breite}.png'), full_page=True)
        if breite == 1280:
            pg.select_option('#ueb-abteilung', 'Lager')
            pg.wait_for_function('!document.querySelector("#ueb-tabelle tbody").textContent.includes("Lena")')
            check('Filter Abteilung: nur Lager, keine Summenzeile bei einer Person', 'Andre Vierzig' in pg.text_content('#ueb-tabelle tbody') and pg.locator('#ueb-tabelle tfoot').count() == 0)
            pg.select_option('#ueb-abteilung', '')
            pg.emulate_media(color_scheme='dark')
            pg.screenshot(path=os.path.join(SH, 'hr_uebersicht_1280_dunkel.png'), full_page=True)
        ctx.close()
    ctx, pg = anmelden('lena', 'Leser-Zugang-77', '198.51.100.4')
    pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector('#mein-konto .hr-wert')
    check('ohne Recht: Reiter ausgeblendet, Adresse #uebersicht führt zu „Mein Urlaub“', not pg.is_visible('[data-tab="uebersicht"]') and pg.is_visible('#tab-mein'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
