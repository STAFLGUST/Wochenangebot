"""Aufbewahrung und Grenzen des Aktivitätsprotokolls (lib/protokoll.php, PROTOKOLL_MONATE = 6; Inhaber 25.10.2026).

Geprüft (beide Speicherarten): Monatsdokumente „protokoll/JJJJ-MM“ älter als der laufende Monat minus 6 werden beim
nächsten Protokolleintrag gelöscht, der Grenzmonat und neuere bleiben; im laufenden Monat steht genau ein Vermerk ohne
Inhalte der gelöschten Monate; die Protokollansicht bietet ältere Monate nie an (auch nicht vor dem Aufräumen und nicht
über ?month=); das Monatsdokument ist ein Ringpuffer (PROTOKOLL_EINTRAEGE_MAX = 20 000 Einträge, PROTOKOLL_BYTES_MAX =
4 MiB, Befund 22.11.2026): die ältesten Einträge fallen weg, der neue Vorgang bleibt, genau ein fortgeschriebener
Vermerk „protokoll_groesse“; eine Flut gelungener Kundenanmeldungen verdrängt nur Anmeldeeinträge (Rechte- und
Fehlanmeldungseinträge bleiben); Oberfläche „Protokoll“ mit Hinweis zur Aufbewahrung, Desktop und 390 px, ohne
JavaScript-Fehler.
"""
import json
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def monat(zurueck):
    jetzt = datetime.now(timezone.utc)
    j, m = jetzt.year, jetzt.month - zurueck
    while m < 1:
        m += 12; j -= 1
    return f'{j:04d}-{m:02d}'


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
JETZT, GRENZE = monat(0), monat(6)
ALT = [monat(9), monat(8), monat(7)]          # werden entfernt
BLEIBT = [monat(6), monat(5), monat(1)]       # Grenzmonat und neuer bleiben
for m in ALT + BLEIBT:
    storage_write('protokoll/' + m, [{'t': m + '-15T08:00:00+00:00', 'u': 'admin', 'n': 'Administrator', 'r': 'admin', 'ip': '', 'a': 'draft', 's': 'Testeintrag ' + m}])

st, r = A.call('log')
check('Ansicht: nur aufbewahrte Monate, auch bevor aufgeräumt wurde', st == 200 and not set(ALT) & set(r['months']) and set(BLEIBT) <= set(r['months'])
      and r['months'] == sorted(r['months'], reverse=True), r.get('months'))
check('Ansicht: Aufbewahrungsdauer für die Oberfläche', r.get('aufbewahrung') == 6, r.get('aufbewahrung'))
st, r = A.call('log&month=' + ALT[1])
check('Ansicht: alter Monat über ?month= nicht abrufbar (laufender Monat stattdessen)', st == 200 and r['month'] == JETZT and 'Testeintrag ' + ALT[1] not in json.dumps(r), r.get('month'))
st, r = A.call('log&month=' + GRENZE)
check('Ansicht: Grenzmonat abrufbar', st == 200 and r['month'] == GRENZE and 'Testeintrag ' + GRENZE in json.dumps(r), r.get('month'))
check('Lesen allein löscht nichts', all(storage_raw('protokoll/' + m) for m in ALT))

# Nächster Protokolleintrag (fehlgeschlagene Anmeldung) räumt auf
Client('198.51.100.40').call('login', {'username': 'admin', 'password': 'falsch-falsch-1'})
check('alte Monate gelöscht', all(storage_raw('protokoll/' + m) is None for m in ALT), [m for m in ALT if storage_raw('protokoll/' + m)])
check('Grenzmonat und neuere bleiben unverändert', all('Testeintrag ' + m in (storage_raw('protokoll/' + m) or '') for m in BLEIBT))
log = A.call('log')[1]['entries']
vermerk = [e for e in log if e['a'] == 'protokoll_aufbewahrung']
check('genau ein Vermerk im laufenden Monat, mit Zeitraum', len(vermerk) == 1 and vermerk[0]['s'] == f'Protokoll: 3 Monate älter als 6 Monate entfernt ({ALT[0]} bis {ALT[2]})'
      and vermerk[0]['u'] == 'system', vermerk)
check('… ohne Inhalte der gelöschten Monate', not any('Testeintrag ' + m in json.dumps(log) for m in ALT))
check('… danach normaler Eintrag (Fehlversuch) dahinter', any(e['a'] == 'login_fail' for e in log))
A.call('log')
Client('198.51.100.41').call('login', {'username': 'admin', 'password': 'falsch-falsch-2'})
log = A.call('log')[1]['entries']
check('kein weiterer Vermerk, wenn nichts zu löschen ist', len([e for e in log if e['a'] == 'protokoll_aufbewahrung']) == 1)

# Ein einzelner alter Monat: Vermerk in der Einzahl
storage_write('protokoll/' + monat(12), [{'t': 'x', 'u': 'admin', 'n': '', 'r': '', 'ip': '', 'a': 'draft', 's': 'ganz alt'}])
Client('198.51.100.42').call('login', {'username': 'admin', 'password': 'falsch-falsch-3'})
log = A.call('log')[1]['entries']
check('ein Monat: „1 Monat … (JJJJ-MM)“', any(e['a'] == 'protokoll_aufbewahrung' and e['s'] == f'Protokoll: 1 Monat älter als 6 Monate entfernt ({monat(12)})' for e in log)
      and storage_raw('protokoll/' + monat(12)) is None)

# ---------- Grenzen des Monatsdokuments: Ringpuffer und Byte-Grenze (Befund 22.11.2026) ----------
MAXE, MAXB = 20000, 4 * 1024 * 1024   # PROTOKOLL_EINTRAEGE_MAX und PROTOKOLL_BYTES_MAX in lib/protokoll.php


def fuellen(n, text):
    storage_write('protokoll/' + JETZT, [{'t': JETZT + '-01T08:00:00+00:00', 'u': 'admin', 'n': 'Administrator', 'r': 'admin', 'ip': '',
                                          'a': 'draft', 's': text % i} for i in range(n)])


def protokoll():
    raw = storage_raw('protokoll/' + JETZT) or '[]'
    return json.loads(raw.split('?>\n', 1)[-1])


fuellen(MAXE + 50, 'Fuelleintrag %d')
Client('198.51.100.43').call('login', {'username': 'admin', 'password': 'falsch-falsch-4'})
log = protokoll()
gross = [e for e in log if e['a'] == 'protokoll_groesse']
check(f'mehr als {MAXE} Einträge: die ältesten fallen weg, der neue Vorgang bleibt', len(log) == MAXE + 1 and log[0]['s'] == 'Fuelleintrag 51'
      and any(e['a'] == 'login_fail' for e in log) and len(gross) == 1 and gross[0]['weg'] == 51 and gross[0]['u'] == 'system'
      and str(MAXE) in gross[0]['s'], (len(log), log[0]['s'], gross))
Client('198.51.100.44').call('login', {'username': 'admin', 'password': 'falsch-falsch-5'})
log = protokoll()
gross = [e for e in log if e['a'] == 'protokoll_groesse']
check('weiterer Eintrag: nur ein Vermerk, fortgeschrieben (der Vermerk füllt das Dokument nicht)', len(log) <= MAXE + 1 and len(gross) == 1
      and gross[0]['weg'] == 53 and any(e['a'] == 'login_fail' for e in log), (len(log), gross))
# Byte-Grenze: wenige, aber sehr große Einträge (die Zahl der Einträge begrenzt die Größe nicht)
fuellen(50, 'Grosser Eintrag %d ' + 'X' * 100000)
Client('198.51.100.45').call('login', {'username': 'admin', 'password': 'falsch-falsch-6'})
log, roh = protokoll(), storage_raw('protokoll/' + JETZT) or ''
check('Byte-Grenze je Monatsdokument: gekürzt, neuer Vorgang und Vermerk vorhanden', len(roh) <= MAXB and len(log) < 50
      and any(e['a'] == 'login_fail' for e in log) and len([e for e in log if e['a'] == 'protokoll_groesse']) == 1, (len(roh), len(log)))
# Flut gelungener Kundenanmeldungen (ungebremst): verdrängt nur Anmeldeeinträge, nie Rechte-, Mitarbeiter- oder Sicherheitseinträge
WICHTIG = [{'t': JETZT + '-01T07:00:00+00:00', 'u': 'admin', 'n': 'Administrator', 'r': 'admin', 'ip': '', 'a': 'user', 's': 'Rolle von „vera“ geändert'},
           {'t': JETZT + '-01T07:01:00+00:00', 'u': 'kunde:opfer', 'n': '', 'r': 'kunde', 'ip': '192.0.2.7', 'a': 'kunde_login_fail', 's': 'Kunden-Anmeldung fehlgeschlagen'}]
storage_write('protokoll/' + JETZT, WICHTIG + [{'t': JETZT + '-01T08:00:00+00:00', 'u': 'kunde:viel', 'n': 'Firma Viel', 'r': 'kunde', 'ip': '', 'a': 'kunde_login',
                                                's': 'Kunde angemeldet %d' % i} for i in range(MAXE)])
Client('198.51.100.46').call('login', {'username': 'admin', 'password': 'falsch-falsch-7'})
log = protokoll()
anm = [e['s'] for e in log if e['a'] == 'kunde_login']
check('Flut gelungener Kundenanmeldungen: Rechte- und Fehlanmeldungseinträge bleiben, die ältesten Anmeldungen fallen weg',
      log[:2] == WICHTIG and len(anm) == MAXE - 3 and anm[0] == 'Kunde angemeldet 3' and any(e['a'] == 'login_fail' for e in log)
      and [e['weg'] for e in log if e['a'] == 'protokoll_groesse'] == [3], (log[:3], len(anm), anm[:1]))
# ebenso selbst gesetzte Kunden-Passwörter (kunde_password, ebenfalls ungebremst)
storage_write('protokoll/' + JETZT, WICHTIG + [{'t': JETZT + '-01T08:00:00+00:00', 'u': 'kunde:viel', 'n': 'Firma Viel', 'r': 'kunde', 'ip': '', 'a': 'kunde_password',
                                                's': 'Kunde hat eigenes Passwort festgelegt %d' % i} for i in range(MAXE)])
Client('198.51.100.47').call('login', {'username': 'admin', 'password': 'falsch-falsch-8'})
log = protokoll()
pw = [e['s'] for e in log if e['a'] == 'kunde_password']
check('Flut selbst gesetzter Kunden-Passwörter: Rechte- und Fehlanmeldungseinträge bleiben, die ältesten Passwort-Einträge fallen weg',
      log[:2] == WICHTIG and len(pw) == MAXE - 3 and pw[0] == 'Kunde hat eigenes Passwort festgelegt 3' and any(e['a'] == 'login_fail' for e in log)
      and [e['weg'] for e in log if e['a'] == 'protokoll_groesse'] == [3], (log[:3], len(pw), pw[:1]))
# eine Anmelde-Flut verdrängt nicht den älteren Nachweis „Passwort über den Link festgelegt“ (Prüfung SEC-1b-1)
LINK = {'t': JETZT + '-01T07:30:00+00:00', 'u': 'kunde:opfer', 'n': 'Firma Opfer', 'r': 'kunde', 'ip': '192.0.2.8', 'a': 'kunde_password',
        's': 'Kunde hat Passwort über den Link aus der E-Mail festgelegt'}
storage_write('protokoll/' + JETZT, WICHTIG + [LINK] + [{'t': JETZT + '-01T08:00:00+00:00', 'u': 'kunde:viel', 'n': 'Firma Viel', 'r': 'kunde', 'ip': '',
                                                         'a': 'kunde_login', 's': 'Kunde angemeldet %d' % i} for i in range(MAXE)])
Client('198.51.100.48').call('login', {'username': 'admin', 'password': 'falsch-falsch-9'})
log = protokoll()
check('Flut gelungener Kundenanmeldungen: der ältere Nachweis „Passwort über den Link festgelegt“ bleibt, verworfen werden Anmeldungen',
      log[:3] == WICHTIG + [LINK] and [e['weg'] for e in log if e['a'] == 'protokoll_groesse'] == [4], (log[:4], len(log)))
storage_write('protokoll/' + JETZT, [])   # aufgeräumt für die Oberflächenprüfung

# Oberfläche
fehler = []
with sync_playwright() as p:
    br = p.chromium.launch()
    for breite in (1280, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.2'}, locale='de-DE')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        pg.click('#vt-log'); pg.wait_for_selector('#log-month')
        werte = pg.eval_on_selector_all('#log-month option', 'os => os.map(o => o.value)')
        check(f'{breite}px: Monatsauswahl ohne alte Monate', not set(ALT) & set(werte) and JETZT in werte and GRENZE in werte, werte)
        titel = pg.eval_on_selector('#log-month', 'el => el.closest("label").title')
        check(f'{breite}px: Hinweis zur Aufbewahrung', 'die 6 Monate davor' in titel and 'automatisch gelöscht' in titel, titel)
        pg.screenshot(path=SH + f'/protokoll_aufbewahrung_{breite}.png')
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
