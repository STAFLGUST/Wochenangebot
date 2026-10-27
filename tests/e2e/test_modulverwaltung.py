"""Modulverwaltung (Roadmap 5, GR-102): Freigabe und Tester je Bereich zur Laufzeit (lib/module.php).

Der Testlauf stellt in der App-Kopie dieser Gruppe REWE auf „in Prüfung“ und Einkauf auf „fertig“ (REGISTER_TEST in
tests/run_e2e.py) – im Code sind beide noch „geplant“. Geprüft: Rechte, Grenzen (nur was der
Entwicklungsstand zulässt, Produktivbereiche und Verwaltung nicht änderbar), Wirkung auf den Zugang (Tester,
Administratoren nur eingetragen, Produktiv, Deaktiviert, Wartung), Verlauf, Datenformat, Oberfläche (Modul Sicherheit → System).
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:300]) if i else ''))


def ob(cl, ziel):
    m, o = ziel.split('.')
    mod = {x['id']: x for x in cl.call('module_status')[1].get('module', [])}[m]
    return next(x for x in mod['oberflaechen'] if x['id'] == o)


def kachel(cl, modul):
    return {x['id']: x for x in cl.call('module_status')[1]['module']}[modul]['kachel']


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p in (('erika', 'Erika Editor', 'editor', 'Editor-Zugang-77'), ('lea', 'Lea Leser', 'viewer', 'Leser-Zugang-77'), ('gerd', 'Gerd Gesperrt', 'editor', 'Gesperrt-Zugang-77')):
    A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': u != 'gerd', 'password': p, 'mustChange': False})
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
L = Client('198.51.100.5'); L.call('login', {'username': 'lea', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.4')

# ── Rechte ──
for a, b in (('modul_freigabe_save', {'bereich': 'rewe.intern', 'freigabe': 'test', 'grund': 'Test'}), ('modul_tester_save', {'bereich': 'rewe.intern', 'tester': []})):
    check(f'{a}: ohne Anmeldung 401', P.call(a, b)[0] == 401)
    check(f'{a}: Bearbeiter 403', E.call(a, b)[0] == 403)
    check(f'{a}: Leser 403', L.call(a, b)[0] == 403)
check('Ausgangslage: REWE in Prüfung, nicht freigegeben, Verwaltungsangaben nur für Administratoren',
      (lambda o: o['entwicklung'] == 'in_pruefung' and o['freigabe'] == 'keine' and o['verwaltung']['moeglich'] == ['keine', 'test', 'deaktiviert'])(ob(A, 'rewe.intern'))
      and 'verwaltung' not in ob(E, 'rewe.intern'))

# ── Grenzen ──
def fehler(b, wort):
    st, r = A.call('modul_freigabe_save', b)
    return st == 422 and wort in r.get('error', ''), (st, r.get('error'))


for name, b, wort in (
        ('unbekannter Bereich', {'bereich': 'gibt.es', 'freigabe': 'test', 'grund': 'Test'}, 'Unbekannt'),
        ('Eingabebereich läuft produktiv → nur über Release', {'bereich': 'angebot.eingabe', 'freigabe': 'deaktiviert', 'grund': 'Test'}, 'Release'),
        ('Kundenseite läuft produktiv → nur über Release', {'bereich': 'angebot.kunden', 'freigabe': 'deaktiviert', 'grund': 'Test'}, 'Release'),
        ('Sicherheitszentrale (Reiter System) nicht änderbar (Aussperrschutz)', {'bereich': 'sicherheit.intern', 'freigabe': 'deaktiviert', 'grund': 'Test'}, 'Aussperrung'),
        ('frühere Oberfläche Verwaltung → System gibt es nicht mehr', {'bereich': 'verwaltung.system', 'freigabe': 'deaktiviert', 'grund': 'Test'}, 'Unbekannt'),
        ('Dashboard nicht änderbar (Aussperrschutz)', {'bereich': 'dashboard.start', 'freigabe': 'deaktiviert', 'grund': 'Test'}, 'Aussperrung'),
        ('geplanter Code: keine Testfreigabe', {'bereich': 'qs.intern', 'freigabe': 'test', 'grund': 'Test'}, 'Entwicklungsstand'),
        ('Code in Prüfung: nicht produktiv', {'bereich': 'rewe.intern', 'freigabe': 'produktiv', 'grund': 'Test'}, 'fertig'),
        ('unbekannte Freigabe', {'bereich': 'rewe.intern', 'freigabe': 'irgendwie', 'grund': 'Test'}, 'Unbekannte'),
        ('ohne Grund', {'bereich': 'rewe.intern', 'freigabe': 'test', 'grund': ' '}, 'Grund')):
    ok, info = fehler(b, wort)
    check(f'abgewiesen: {name}', ok, info)

# ── Testfreigabe: nur eingetragene Tester ──
st, r = A.call('modul_freigabe_save', {'bereich': 'rewe.intern', 'freigabe': 'test', 'grund': 'Abnahme Fachabteilung'})
check('REWE in Testbetrieb', st == 200 and r['freigabe'] == {'alt': 'keine', 'neu': 'test'}, (st, r))
check('ohne Tester: niemand hat Zugang (auch Administratoren nicht)', not ob(A, 'rewe.intern')['zugang'] and not ob(E, 'rewe.intern')['zugang'])
check('Kachel für Nicht-Tester: „in Prüfung“, ohne Zugang', (lambda k: k['status'] == 'in_pruefung' and not k['zugang'])(kachel(L, 'rewe')))
for name, t, wort in (('unbekanntes Konto', ['u-gibt-es-nicht'], 'Unbekannt'), ('gesperrtes Konto', [ids['gerd']], 'gesperrt')):
    st, r = A.call('modul_tester_save', {'bereich': 'rewe.intern', 'tester': t})
    check(f'Tester abgewiesen: {name}', st == 422 and wort in r.get('error', ''), (st, r))
st, r = A.call('modul_tester_save', {'bereich': 'qs.portal', 'tester': [ids['erika']]})
check('Tester abgewiesen: externer Bereich (QS-Portal)', st == 422 and 'intern' in r.get('error', ''), (st, r))
st, r = A.call('modul_tester_save', {'bereich': 'angebot.eingabe', 'tester': [ids['erika']]})
check('Tester abgewiesen: Produktivbereich (keine Testfreigabe)', st == 422 and 'Release' in r.get('error', ''), (st, r))
st, r = A.call('modul_tester_save', {'bereich': 'rewe.intern', 'tester': [ids['erika']], 'grund': 'Abnahme'})
check('Tester erika eingetragen', st == 200 and r['tester'] == [ids['erika']], (st, r))
check('Testerin erika: Zugang, Kachel „Testbetrieb“', (lambda k: k['status'] == 'testbetrieb' and k['zugang'])(kachel(E, 'rewe')))
check('Leserin lea weiterhin ohne Zugang', not ob(L, 'rewe.intern')['zugang'])
check('Administrator nicht eingetragen: kein Zugang', not ob(A, 'rewe.intern')['zugang'])
A.call('modul_tester_save', {'bereich': 'rewe.intern', 'tester': [ids['erika'], ids['admin']], 'grund': 'Abnahme'})
check('Administrator eingetragen: Zugang', ob(A, 'rewe.intern')['zugang'])
check('Verwaltungsangaben: Tester mit Namen, Herkunft der Freigabe', (lambda v: [t['name'] for t in v['tester']] == ['Erika Editor', 'Administrator'] and v['laufzeit']['grund'] == 'Abnahme Fachabteilung')(ob(A, 'rewe.intern')['verwaltung']))

# ── Wartung wirkt jetzt auf den freigegebenen Bereich ──
st, r = A.call('modul_wartung_save', {'bereich': 'rewe.intern', 'active': True, 'grund': 'Test Wartung'})
check('Wartung für den Testbereich möglich', st == 200 and r['aktiv'], (st, r))
check('Wartung: Testerin ohne Zugang, eingetragener Administrator mit Zugang', not ob(E, 'rewe.intern')['zugang'] and ob(A, 'rewe.intern')['zugang'])
A.call('modul_wartung_save', {'bereich': 'rewe.intern', 'active': False, 'grund': 'Test Ende'})
check('nach der Wartung: Testerin wieder mit Zugang', ob(E, 'rewe.intern')['zugang'])

# ── Produktiv (nur bei fertigem Code) und Deaktiviert ──
st, r = A.call('modul_freigabe_save', {'bereich': 'einkauf.intern', 'freigabe': 'produktiv', 'grund': 'Start Einkauf'})
check('Einkauf (fertig) produktiv freigegeben', st == 200, (st, r))
check('produktiv: alle Mitarbeiter mit Zugang, Kachel „Verfügbar“', ob(L, 'einkauf.intern')['zugang'] and kachel(E, 'einkauf')['status'] == 'verfuegbar')
A.call('modul_freigabe_save', {'bereich': 'einkauf.intern', 'freigabe': 'deaktiviert', 'grund': 'Störung beim Lieferanten'})
check('deaktiviert: niemand, auch kein Administrator', not ob(A, 'einkauf.intern')['zugang'] and kachel(L, 'einkauf')['status'] == 'deaktiviert')
st, r = A.call('modul_freigabe_save', {'bereich': 'einkauf.intern', 'freigabe': 'keine', 'grund': 'zurück auf Code-Stand'})
check('zurück auf den Wert aus dem Register', st == 200 and ob(A, 'einkauf.intern')['freigabe'] == 'keine' and ob(A, 'einkauf.intern')['verwaltung']['laufzeit'] is None, (st, r))

# ── Verlauf, Protokoll, Datenformat ──
v = A.call('module_status')[1].get('verlauf', [])
check('Verlauf: Freigabe- und Testeränderungen mit Grund und Urheber',
      any(x.get('art') == 'freigabe' and x['bereich'] == 'einkauf.intern' and x['neu'] == 'freigabe: deaktiviert' and x['grund'] == 'Störung beim Lieferanten' and x['wer'] == 'Administrator' for x in v)
      and any(x.get('art') == 'tester' and 'Erika Editor' in x['neu'] for x in v), v[:3])
check('Verlauf nur für Administratoren', 'verlauf' not in E.call('module_status')[1])
roh = storage_raw('module') or ''
d = json.loads(roh[roh.index('?>') + 2:] if '?>' in roh else roh)
check('Dokument „module“ nur erweitert: freigabe, tester, wartung, verlauf',
      set(d) >= {'freigabe', 'tester', 'wartung', 'verlauf'} and d['freigabe'] == {'rewe.intern': d['freigabe']['rewe.intern']} and d['tester']['rewe.intern'] == [ids['erika'], ids['admin']], sorted(d))

# ── Oberfläche: Modul Sicherheit → System → Module und Freigaben (bis 27.10.2026 Verwaltung → System) ──
fehler_js = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for breite in (390, 1280):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': f'198.51.100.{40 + breite % 9}'})
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler_js.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden])')
        check(f'{breite}px: Verwaltung ohne System-Ansicht', pg.locator('#vt-sec, #view-sec').count() == 0)
        pg.goto(B + '/module/sicherheit/#system')
        pg.wait_for_selector('#sy-module .mvtab tbody tr')
        zeilen = pg.locator('#sy-module .mvtab tbody tr').count()
        check(f'{breite}px: Tabelle mit allen Bereichen', zeilen >= 12, zeilen)
        check(f'{breite}px: Eingabebereich „nur über ein Release“', 'nur über ein Release' in pg.inner_text('#sy-module tr[data-mvziel="angebot.eingabe"]'))
        check(f'{breite}px: REWE zeigt Testbetrieb, Grund und Tester', (lambda t: 'Testbetrieb' in t and 'Abnahme Fachabteilung' in t and 'Erika Editor' in t)(pg.inner_text('#sy-module tr[data-mvziel="rewe.intern"]')))
        check(f'{breite}px: kein waagerechtes Scrollen der Seite', not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
        pg.locator('#sy-module').scroll_into_view_if_needed()
        pg.screenshot(path=os.path.join(SH, f'modulverwaltung-{breite}.png'), full_page=False)
        if breite == 1280:
            pg.click('#sy-module [data-sy="modul"][data-ziel="rewe.intern"]'); pg.wait_for_selector('#sic-dlg[open] #mv-freigabe')
            opts = pg.eval_on_selector_all('#mv-freigabe option', 'os => os.map(o => o.value)')
            check('Dialog bietet nur erlaubte Freigaben an', opts == ['keine', 'test', 'deaktiviert'], opts)
            pg.select_option('#mv-freigabe', 'keine'); pg.fill('#mv-grund', 'Abnahme beendet')
            pg.click('#sic-dlg [data-d="freigabe"]')
            pg.wait_for_function("document.querySelector('#sy-module tr[data-mvziel=\"rewe.intern\"]') && document.querySelector('#sy-module tr[data-mvziel=\"rewe.intern\"]').innerText.includes('Nicht freigegeben')")
            check('Oberfläche: Freigabe gespeichert und Tabelle aktualisiert', ob(A, 'rewe.intern')['freigabe'] == 'keine')
            pg.wait_for_selector('#sic-dlg[open] [name="mv-tester"]')
            check('… Dialog bleibt mit dem neuen Stand offen', pg.input_value('#mv-freigabe') == 'keine' and 'jetzt: Nicht freigegeben' in pg.inner_text('#sic-dlg .sic-dkopf'))
            pg.uncheck(f'#sic-dlg [name="mv-tester"][value="{ids["admin"]}"]'); pg.click('#sic-dlg [data-d="tester"]')
            pg.wait_for_function("!document.querySelector('#sy-module tr[data-mvziel=\"rewe.intern\"]').innerText.includes('Administrator')")
            check('Oberfläche: Tester gespeichert', [t['name'] for t in ob(A, 'rewe.intern')['verwaltung']['tester']] == ['Erika Editor'])
            pg.keyboard.press('Escape'); pg.wait_for_selector('#sic-dlg', state='hidden')
            check('Produktivbereich und Sicherheitszentrale: ohne „Ändern“', pg.locator('#sy-module [data-sy="modul"][data-ziel="angebot.eingabe"], #sy-module [data-sy="modul"][data-ziel="sicherheit.intern"], #sy-module [data-sy="modul"][data-ziel="dashboard.start"]').count() == 0
                  and pg.locator('#sy-module tr[data-mvziel="sicherheit.intern"]').count() == 1)
            pg.click('#sy-module tr[data-mvziel="qs.intern"] td:first-child'); pg.wait_for_selector('#sic-dlg[open] #mv-freigabe')
            check('Zeile anklicken öffnet den Dialog; geplanter Bereich: nur „nicht freigegeben“ oder „deaktiviert“', pg.eval_on_selector_all('#mv-freigabe option', 'os => os.map(o => o.value)') == ['keine', 'deaktiviert'])
            pg.screenshot(path=os.path.join(SH, 'modulverwaltung-formular-1280.png'), full_page=False)
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler_js, fehler_js)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
