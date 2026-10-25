"""Aufbewahrung des Aktivitätsprotokolls (lib/protokoll.php, PROTOKOLL_MONATE = 6; Inhaber 25.10.2026).

Geprüft (beide Speicherarten): Monatsdokumente „protokoll/JJJJ-MM“ älter als der laufende Monat minus 6 werden beim
nächsten Protokolleintrag gelöscht, der Grenzmonat und neuere bleiben; im laufenden Monat steht genau ein Vermerk ohne
Inhalte der gelöschten Monate; die Protokollansicht bietet ältere Monate nie an (auch nicht vor dem Aufräumen und nicht
über ?month=); Oberfläche „Protokoll“ mit Hinweis zur Aufbewahrung, Desktop und 390 px, ohne JavaScript-Fehler.
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
