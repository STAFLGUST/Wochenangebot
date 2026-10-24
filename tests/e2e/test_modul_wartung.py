"""Wartung je Oberfläche (GR-107): Eingabebereich in Wartung – serverseitig durchgesetzt, protokolliert, mit Notfallwerkzeug.

Kunden-Frontend (bisheriger Wartungsmodus) und Eingabebereich sind getrennt steuerbar. Administratoren arbeiten
während der Wartung weiter; Anmeldung, Abmelden und Status bleiben erreichbar (wartung_frei).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, API, B
from umgebung import REPO, SH, shot

PW = 'Sicheres-Passwort-1'
DATA = os.environ['UDATA']
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def eingabe(cl):
    m = {x['id']: x for x in cl.call('module_status')[1]['module']}['angebot']
    return next(o for o in m['oberflaechen'] if o['id'] == 'eingabe')


def kopf(cl, action):
    """Kopfzeilen einer Antwort mit der Sitzung des Clients (auch bei Fehlerstatus)."""
    try:
        r = cl.http.open(urllib.request.Request(API + action, headers={'X-Forwarded-For': cl.ip}))
    except urllib.error.HTTPError as e:
        r = e
    return r.code, r.headers


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
P = Client('198.51.100.4')
rev = A.call('kunden')[1]['rev']
A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Wartung Test GmbH', 'nr': 'W-1', 'email': 'wartung@example.org', 'active': True, 'angebote': ['std'],
                      'login': {'username': 'wartung.kunde', 'password': 'Kunden-Kennwort-9', 'mustChange': False, 'active': True}})

# ── Rechte und Prüfungen ──
check('Bearbeiter darf keine Wartung setzen (403)', E.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test'})[0] == 403)
check('ohne Anmeldung 401', P.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test'})[0] == 401)
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': ''})
check('ohne Grund abgewiesen (422)', st == 422 and 'Grund' in r.get('error', ''), r)
check('unbekannter Bereich abgewiesen', A.call('modul_wartung_save', {'bereich': 'gibt.es_nicht', 'active': True, 'grund': 'Test'})[0] == 422)
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.kunden', 'active': True, 'grund': 'Test'})
check('Kunden-Frontend weiter nur über den bisherigen Schalter', st == 422 and 'Angebotsseite' in r.get('error', ''), r)
st, r = A.call('modul_wartung_save', {'bereich': 'rewe.intern', 'active': True, 'grund': 'Test'})
check('nicht freigegebener Bereich abgewiesen (Wartung ohne Wirkung)', st == 422 and 'nicht freigegeben' in r.get('error', ''), r)
check('Verwaltung → System nicht sperrbar (Aussperrschutz)', 'Aussperrung' in A.call('modul_wartung_save', {'bereich': 'verwaltung.system', 'active': True, 'grund': 'Test'})[1].get('error', ''))
check('ungültige Uhrzeit abgewiesen', A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test', 'until': 'morgen'})[0] == 422)

# ── Geplante Wartung: wirkt erst ab Beginn ──
spaeter = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Datenübernahme', 'message': 'Morgen Wartung', 'ab': spaeter})
check('Wartung für morgen geplant', st == 200 and r['wartung']['geplant'] is True and r['zustand']['betrieb'] == 'normal', r)
check('geplante Wartung sperrt noch nicht', E.call('stock')[0] == 200 and eingabe(E)['zugang'] is True)

# ── Wartung jetzt: Bearbeiter gesperrt, Administrator arbeitet weiter ──
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Datenübernahme Stammdaten', 'message': 'Kurze Wartung – gleich zurück.', 'until': '2026-10-21T18:00'})
check('Wartung des Eingabebereichs gestartet', st == 200 and r['aktiv'] is True and r['wartung']['geplant'] is False, r)
st, r = E.call('stock')
check('Bearbeiter: Aktion mit 503 und Hinweis abgewiesen', st == 503 and r.get('wartung') is True and r.get('bereich') == 'angebot.eingabe' and r.get('error') == 'Kurze Wartung – gleich zurück.', (st, r))
code, h = kopf(E, 'stock')
check('503 ohne Zwischenspeicher, mit Retry-After', code == 503 and 'no-store' in (h.get('Cache-Control') or '') and h.get('Retry-After') == '600', dict(h))
st, r = E.call('draft_ping', {})
check('Bearbeiter: auch Schreibaktionen gesperrt (auch in laufender Sitzung)', st == 503, (st, r))
st, r = E.call('status')
check('Bearbeiter: Status erreichbar und meldet die Sperre', st == 200 and r['loggedIn'] is True and r['eingabeGesperrt'] is True and r['wartungEingabe']['message'] == 'Kurze Wartung – gleich zurück.', r)
check('Bearbeiter sieht weder Grund noch Urheber', 'grund' not in r['wartungEingabe'] and 'by' not in r['wartungEingabe'], r['wartungEingabe'])
E2 = Client('198.51.100.5')
check('Anmeldung bleibt möglich (danach gesperrt)', E2.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})[0] == 200 and E2.call('stock')[0] == 503)
check('Abmelden bleibt möglich', E2.call('logout', {})[0] == 200)
check('Administrator arbeitet weiter (Bestand, Stammdaten)', A.call('stock')[0] == 200 and A.call('master')[0] == 200)
st, r = A.call('status')
check('Administrator: Status mit Hinweis, nicht gesperrt', r['eingabeGesperrt'] is False and r['wartungEingabe']['grund'] == 'Datenübernahme Stammdaten', r)
z = eingabe(E)
check('Modulübersicht: Eingabe in Wartung, für Bearbeiter 503', z['betrieb'] == 'wartung' and z['zugang'] is False and z['http'] == 503, z)
z = eingabe(A)
check('Modulübersicht: Administrator mit Hinweis zugelassen', z['zugang'] is True and z['hinweis'] is True and z['wartung']['by'] == 'Administrator', z)

# ── Kunden-Frontend unberührt ──
K = Client('198.51.100.6')
check('Kunden-Anmeldung und Kundenstatus unberührt', K.call('kunde_login', {'username': 'wartung.kunde', 'password': 'Kunden-Kennwort-9'})[0] == 200 and K.call('kunde_status')[1]['kunde'] is not None)
check('Angebot für den Kunden erreichbar', K.call('offer')[0] == 200)

# ── Protokoll und Verlauf ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Wartung gestartet mit Grund', 'Wartung gestartet: Angebot · Mitarbeiter-Eingabe – Grund: Datenübernahme Stammdaten' in log)
check('Protokoll: Planung vermerkt', 'Wartung geplant: Angebot · Mitarbeiter-Eingabe' in log)
verlauf = A.call('module_status')[1].get('verlauf', [])
neu = verlauf[0] if verlauf else {}
check('Verlauf: wer, wann, Bereich, alt, neu, Grund, bis', neu.get('wer') == 'Administrator' and neu.get('bereich') == 'angebot.eingabe' and neu.get('neu') == 'wartung'
      and neu.get('alt') == 'wartung geplant' and neu.get('grund') == 'Datenübernahme Stammdaten' and neu.get('bis') == '2026-10-21T18:00' and neu.get('t'), neu)
check('Bearbeiter erhält keinen Verlauf', 'verlauf' not in (E.call('module_status')[1] or {}))
sec = A.call('security_status')[1]
check('Sicherheitsübersicht: Wartung Eingabebereich und Verlauf', sec['wartungEingabe']['grund'] == 'Datenübernahme Stammdaten' and sec['wartungVerlauf'][0]['bereich'] == 'angebot.eingabe')

# ── Oberfläche: Sperrbildschirm für Bearbeiter, Hinweis für Administratoren ──
fehler = []
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for breite in (1280, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': f'198.51.100.{20 + breite % 9}'})
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'erika'); pg.fill('#pw1', 'Editor-Zugang-77'); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-wartung:not([hidden])')
        check(f'Bearbeiter {breite}px: Wartungshinweis statt Eingabebereich', 'Kurze Wartung – gleich zurück.' in pg.inner_text('#ew-text') and pg.is_hidden('#screen-editor') and '21.10.2026' in pg.inner_text('#ew-bis'))
        shot(pg, f'{SH}/modul-wartung-bearbeiter-{breite}.png')
        ctx.close()
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': f'198.51.100.{30 + breite % 9}'})
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        pg.wait_for_selector('#adm-wartung:not([hidden])')
        check(f'Administrator {breite}px: Eingabebereich mit Hinweis „nur Administratoren“', 'Eingabebereich in Wartung' in pg.inner_text('#adm-wartung'))
        if breite == 1280:
            pg.click('#vt-sec'); pg.wait_for_selector('#ew-form')
            check('Verwaltung: Formular mit Grund, Status und Verlauf', pg.input_value('#ew-form [name=grund]') == 'Datenübernahme Stammdaten' and 'Aktiv seit' in pg.inner_text('#ew-form') and pg.locator('#ew-form .wv-list li').count() >= 2)
            pg.locator('#ew-form').scroll_into_view_if_needed()
            shot(pg.locator('#ew-form'), f'{SH}/modul-wartung-verwaltung-1280.png')
        ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

# ── Beenden: Bearbeiter wieder frei ──
st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': 'fertig'})
check('Wartung beendet', st == 200 and r['aktiv'] is False and r['zustand']['betrieb'] == 'normal', r)
check('Bearbeiter arbeitet wieder', E.call('stock')[0] == 200 and E.call('status')[1]['eingabeGesperrt'] is False)
check('Protokoll: Wartung beendet', 'Wartung beendet: Angebot · Mitarbeiter-Eingabe' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ── Notfallwerkzeug beendet alle Wartungen (auch die der Angebotsseite) ──
A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Notfall'})
A.call('wartung_save', {'active': True, 'message': 'Pause', 'until': ''})
check('vor dem Notfallwerkzeug: beide Bereiche in Wartung', E.call('stock')[0] == 503 and P.call('offer')[0] == 503)
out = subprocess.run(['php', REPO + '/deploy/wartung-aus.php'], env={**os.environ, 'DATA_DIR': DATA}, capture_output=True, text=True)
check('Notfallwerkzeug meldet beendete Bereiche', out.returncode == 0 and 'angebot.kunden' in out.stdout and 'angebot.eingabe' in out.stdout, (out.stdout, out.stderr))
check('danach alles wieder erreichbar', E.call('stock')[0] == 200 and A.call('status')[1]['wartung'] is None)
v = A.call('module_status')[1]['verlauf']
check('Notfall im Verlauf vermerkt', v[0]['wer'] == 'Notfallwerkzeug (Server)' and {x['bereich'] for x in v[:2]} == {'angebot.kunden', 'angebot.eingabe'}, v[:2])
out = subprocess.run(['php', REPO + '/deploy/wartung-aus.php'], env={**os.environ, 'DATA_DIR': DATA}, capture_output=True, text=True)
check('zweiter Aufruf: keine Wartung aktiv', 'Keine Wartung aktiv' in out.stdout, out.stdout)

# ── Wartung eines Fachmoduls gilt auch für seine schreibenden Aktionen im gemeinsamen Eingabebereich (GR-107) ──
st, r = A.call('rolle_save', {'name': 'Personalstelle', 'rechte': ['hr.zugang', 'hr.verwalten']})
PERS = r.get('id')
A.call('user_save', {'id': '', 'name': 'Paula Personal', 'username': 'paula', 'rollen': [PERS], 'active': True, 'password': 'Personal-Zugang-77', 'mustChange': False})
Pa = Client('198.51.100.7'); Pa.call('login', {'username': 'paula', 'password': 'Personal-Zugang-77'})
check('Personalstelle speichert HR-Einstellungen (Verwaltung)', Pa.call('hr_einstellungen_save', {'sperren': [], 'ferien': []})[0] == 200)
check('HR in Wartung gesetzt', A.call('modul_wartung_save', {'bereich': 'hr.intern', 'active': True, 'grund': 'Datenübernahme HR'})[0] == 200)
st, r = Pa.call('hr_einstellungen_save', {'sperren': [], 'ferien': []})
check('Wartung HR: HR-Einstellungen über den Eingabebereich nicht speicherbar (503)', st == 503 and r.get('bereich') == 'hr.intern', (st, r))
check('… lesen im Eingabebereich bleibt möglich (Mitarbeiter-Angaben)', Pa.call('mitarbeiter_hr')[0] == 200)
check('… Administrator speichert weiter', A.call('hr_einstellungen_save', {'sperren': [], 'ferien': []})[0] == 200)
check('Wartung HR beendet: Personalstelle speichert wieder', A.call('modul_wartung_save', {'bereich': 'hr.intern', 'active': False, 'grund': 'fertig'})[0] == 200
      and Pa.call('hr_einstellungen_save', {'sperren': [], 'ferien': []})[0] == 200)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
