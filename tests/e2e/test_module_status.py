"""Modulzustand zur Laufzeit (GR-102): Aktion module_status wertet Modulregister und Entscheidungstabelle aus.

Heute sind nur die beiden Oberflächen des Angebots produktiv; alle anderen Module sind geplant und gesperrt. Der bisherige
Wartungsmodus der Angebotsseite erscheint als Wartung der Oberfläche angebot.kunden.
"""
import json
import sys
import urllib.request

from kunden_hilfe import Client, API

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def nach_id(module):
    return {m['id']: m for m in module}


def ob(m, oid):
    return next(o for o in m['oberflaechen'] if o['id'] == oid)


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
A.call('user_save', {'id': '', 'name': 'Lea Leser', 'username': 'lea', 'role': 'viewer', 'active': True, 'password': 'Leser-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
L = Client('198.51.100.5'); L.call('login', {'username': 'lea', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.4')

check('ohne Anmeldung 401', P.call('module_status')[0] == 401)
code, r = L.call('module_status')
check('Leser darf die Übersicht sehen', code == 200 and r.get('ok'), (code, r))
mods = nach_id(r.get('module', []))
check('alle Module des Registers', set(mods) == {'angebot', 'bestand', 'crm', 'rewe', 'qs', 'einkauf', 'import', 'verwaltung', 'dashboard', 'plattform', 'mobile'}, sorted(mods))
kacheln = [m['id'] for m in sorted(r['module'], key=lambda m: m['reihenfolge'] or 999) if m['dashboard']]
check('acht Kacheln in fester Reihenfolge', kacheln == ['angebot', 'bestand', 'crm', 'rewe', 'qs', 'einkauf', 'import', 'verwaltung'], kacheln)

ang = mods['angebot']
check('Angebot-Kachel führt zur Mitarbeiter-Eingabe und ist verfügbar', ang['kachel']['ziel'] == 'angebot.eingabe' and ang['kachel']['zugang'] is True and ang['kachel']['status'] == 'verfuegbar', ang['kachel'])
check('Angebot · Kunden-Frontend: produktiv, normal, Zugang', (lambda o: o['freigabe'] == 'produktiv' and o['betrieb'] == 'normal' and o['zugang'] is True and o['art'] == 'extern')(ob(ang, 'kunden')))
check('Angebot · Eingabe: heutige Adresse und beschlossenes Ziel', (lambda o: o['adresse'] == 'https://angebot-stafl.de/admin/' and o['ziel'] == 'https://angebot.dashboard-stafl.de/')(ob(ang, 'eingabe')))
imp = mods['import']
check('Import: eigene Kachel, Teil der Verwaltung, Ziel verwaltung.import', imp['teil_von'] == 'verwaltung' and imp['kachel']['ziel'] == 'verwaltung.import' and imp['oberflaechen'] == [], imp)
verw = mods['verwaltung']
check('Verwaltung freigegeben (verwaltung.dashboard-stafl.de): Kachel verfügbar, Importzentrale freigegeben, System noch nicht',
      verw['kachel']['ziel'] == 'verwaltung.verwaltung' and verw['kachel']['zugang'] is True and verw['kachel']['status'] == 'verfuegbar'
      and ob(verw, 'verwaltung')['adresse'] == 'https://verwaltung.dashboard-stafl.de/admin/' and ob(verw, 'import')['zugang'] and not ob(verw, 'system')['zugang'], verw)
check('Import freigegeben: Kachel verfügbar, Adresse /import/ auf dem Verwaltungs-Host (auch für Leser – Rechte je Importart prüft der Server)',
      imp['kachel']['zugang'] is True and imp['kachel']['status'] == 'verfuegbar' and imp['kachel']['adresse'] == 'https://verwaltung.dashboard-stafl.de/import/'
      and (lambda o: o['entwicklung'] == 'fertig' and o['freigabe'] == 'produktiv')(ob(verw, 'import')), imp['kachel'])
best = mods['bestand']
check('Bestand freigegeben (bestand.dashboard-stafl.de, Phase 1): Kachel verfügbar, Adresse /admin/ auf dem Bestands-Host',
      best['kachel']['ziel'] == 'bestand.intern' and best['kachel']['zugang'] is True and best['kachel']['status'] == 'verfuegbar'
      and (lambda o: o['adresse'] == 'https://bestand.dashboard-stafl.de/admin/' and o['entwicklung'] == 'fertig' and o['freigabe'] == 'produktiv')(ob(best, 'intern')), best['kachel'])
for mid in ('crm', 'rewe', 'qs', 'einkauf'):
    k = mods[mid]['kachel']
    check(f'{mid}: noch nicht freigegeben → kein Zugang (Entwicklungsstand)', k['zugang'] is False and k['status'] == 'entwicklungsstand', k)
qs = mods['qs']
check('QS-Portal extern, QS-Verwaltung intern – beide gesperrt', ob(qs, 'portal')['art'] == 'extern' and ob(qs, 'intern')['art'] == 'intern' and not ob(qs, 'portal')['zugang'] and not ob(qs, 'intern')['zugang'])
check('Anmelde-Oberfläche (Keycloak) und Dashboard freigegeben (Inbetriebnahme Schritt 6)', all(o['entwicklung'] == 'fertig' and o['freigabe'] == 'produktiv' for o in (ob(mods['plattform'], 'anmeldung'), ob(mods['dashboard'], 'start'))))
roh = json.dumps(r, ensure_ascii=False)
check('keine Entwickler-Interna in der Antwort (Pfade, Agenten, Testgruppen)', not any(w in roh for w in ('"pfade"', '"agent"', '"testgruppen"', 'app/api/', 'tests/e2e')))

antwort = A.http.open(urllib.request.Request(API + 'module_status', headers={'X-Forwarded-For': A.ip}))
check('Antwort wird nicht zwischengespeichert (no-store)', 'no-store' in (antwort.headers.get('Cache-Control') or ''), antwort.headers.get('Cache-Control'))
code, r2 = A.call('module_status')
check('Administrator sieht dieselbe Übersicht', code == 200 and nach_id(r2['module'])['angebot']['kachel']['zugang'] is True)

# Wartungsmodus der Angebotsseite = Wartung der Oberfläche angebot.kunden
code, r = A.call('wartung_save', {'active': True, 'message': 'Kurze Pause', 'until': ''})
check('Administrator schaltet den Wartungsmodus ein', code == 200, r)
ke = ob(nach_id(E.call('module_status')[1]['module'])['angebot'], 'kunden')
check('Bearbeiter: Kunden-Frontend in Wartung, kein Zugang, 503', ke['betrieb'] == 'wartung' and ke['zugang'] is False and ke['http'] == 503 and ke['kachel'] == 'wartung', ke)
ka = ob(nach_id(A.call('module_status')[1]['module'])['angebot'], 'kunden')
check('Administrator: Zugang trotz Wartung, mit Hinweis (nicht ausgesperrt)', ka['zugang'] is True and ka['hinweis'] is True and ka['kachel'] == 'wartung', ka)
ee = ob(nach_id(E.call('module_status')[1]['module'])['angebot'], 'eingabe')
check('Mitarbeiter-Eingabe bleibt verfügbar (getrennte Oberflächen)', ee['betrieb'] == 'normal' and ee['zugang'] is True, ee)
check('Wartung beenden', A.call('wartung_save', {'active': False})[0] == 200)
ke = ob(nach_id(E.call('module_status')[1]['module'])['angebot'], 'kunden')
check('nach der Wartung wieder normal', ke['betrieb'] == 'normal' and ke['zugang'] is True, ke)
check('Wartung beenden macht nichts produktiv (Bestand bleibt gesperrt)', nach_id(E.call('module_status')[1]['module'])['bestand']['kachel']['zugang'] is False)

# Kundenzugang berechtigt nicht zur Mitarbeiter-Übersicht (GR-104)
rev = A.call('kunden')[1]['rev']
A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Modul Test GmbH', 'nr': 'M-1', 'email': 'modul@example.org', 'active': True, 'angebote': ['std'],
                      'login': {'username': 'modul.kunde', 'password': 'Kunden-Kennwort-8', 'mustChange': False, 'active': True}})
K = Client('198.51.100.6')
check('Kunde angemeldet', K.call('kunde_login', {'username': 'modul.kunde', 'password': 'Kunden-Kennwort-8'})[0] == 200)
check('Kunde erhält keine Modulübersicht (401)', K.call('module_status')[0] == 401)

print(f'\n{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
