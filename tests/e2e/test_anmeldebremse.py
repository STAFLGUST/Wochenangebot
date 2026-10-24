"""Fehlversuchsbremse je Adresse (lib/protokoll.php), Abmelden mit CSRF und Bedrohungsliste ohne Nebenwirkung beim Lesen.

- Eine erfolgreiche Anmeldung setzt die Fehlversuche einer Adresse nicht mehr zurück: Mit einem eigenen gültigen Zugang
  ließ sich sonst zwischen je vier Fehlversuchen an fremden Konten unbegrenzt weiterraten (Passwort-Spraying).
- Mitarbeiter- und Kundenanmeldung zählen getrennt: Kunden-Fehlversuche sperren keine Mitarbeiter und umgekehrt, eine
  Kundenanmeldung entsperrt keine Mitarbeiteranmeldung.
- `logout` mit bestehender Sitzung nur mit CSRF-Token; ohne Sitzung immer.
- `fw_status` (GET) lädt die Bedrohungsliste nicht mehr selbst; auffrischen über `fw_feed_auffrischen` (POST, Administrator).
"""
import json
import sys

from kunden_hilfe import Client
from umgebung import storage_raw, storage_write


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
check('Bearbeiterin angelegt', A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True,
                                                     'password': 'Editor-Zugang-77', 'mustChange': False})[0] == 200)
rev = A.call('kunden')[1]['rev']
check('Kunde mit Zugang angelegt', A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Bremse Test GmbH', 'nr': 'B-1', 'email': 'bremse@example.org', 'active': True,
                                                         'angebote': ['std'], 'login': {'username': 'bremse.kunde', 'password': 'Kunden-Kennwort-9', 'mustChange': False, 'active': True}})[0] == 200)
ERIKA = {'username': 'erika', 'password': 'Editor-Zugang-77'}
KUNDE = {'username': 'bremse.kunde', 'password': 'Kunden-Kennwort-9'}

# ── Passwort-Spraying mit eigenem Zugang ──
S = Client('203.0.113.50')
for i in range(4):
    S.call('login', {'username': f'fremd{i}', 'password': 'Falsches-Passwort-1'})
check('vier Fehlversuche an fremden Konten, dann eigene Anmeldung erfolgreich', S.call('login', ERIKA)[0] == 200)
check('… Abmelden', S.call('logout', {})[0] == 200)
S.call('login', {'username': 'fremd9', 'password': 'Falsches-Passwort-1'})
code, r = S.call('login', ERIKA)
check('fünfter Fehlversuch sperrt die Adresse trotz der Anmeldung dazwischen (429)', code == 429 and 'Fehlversuche' in r.get('error', ''), (code, r))

# ── Mitarbeiter und Kunden getrennt ──
K = Client('203.0.113.60')
for i in range(5):
    K.call('kunde_login', {'username': f'unbekannt{i}', 'password': 'Falsches-Passwort-1'})
check('Kunden-Fehlversuche: Kundenanmeldung der Adresse gesperrt (429)', K.call('kunde_login', KUNDE)[0] == 429)
check('… Mitarbeiteranmeldung derselben Adresse nicht gesperrt', K.call('login', ERIKA)[0] == 200)
M = Client('203.0.113.61')
for i in range(5):
    M.call('login', {'username': f'fremd{i}', 'password': 'Falsches-Passwort-1'})
check('Mitarbeiter-Fehlversuche: Mitarbeiteranmeldung gesperrt (429)', M.call('login', ERIKA)[0] == 429)
check('… Kundenanmeldung derselben Adresse weiter möglich', M.call('kunde_login', KUNDE)[0] == 200)
M2 = Client('203.0.113.62')
for i in range(4):
    M2.call('login', {'username': f'fremd{i}', 'password': 'Falsches-Passwort-1'})
check('Kundenanmeldung erfolgreich …', M2.call('kunde_login', KUNDE)[0] == 200)
M2.call('login', {'username': 'fremd8', 'password': 'Falsches-Passwort-1'})
check('… setzt die Mitarbeiter-Fehlversuche nicht zurück (429)', M2.call('login', ERIKA)[0] == 429)
logins = doc('logins') or {}
check('Sperren tragen ihren Bereich (Format nur erweitert)', {v.get('bereich') for v in logins.values() if v.get('ip') in ('203.0.113.60', '203.0.113.61')} == {'kunde', 'mitarbeiter'},
      sorted((v.get('ip'), v.get('bereich')) for v in logins.values()))
gesperrt = A.call('security_status')[1].get('blockedIps', [])
check('Sicherheitsübersicht nennt den Bereich je Sperre', {x.get('bereich') for x in gesperrt if x.get('ip') in ('203.0.113.60', '203.0.113.61')} == {'kunde', 'mitarbeiter'}, gesperrt)

# ── Abmelden mit CSRF ──
E = Client('198.51.100.70')
check('Bearbeiterin angemeldet', E.call('login', ERIKA)[0] == 200)
echt = E.csrf
E.csrf = 'falsch'
check('Abmelden mit falschem Token abgewiesen (403)', E.call('logout', {})[0] == 403)
E.csrf = echt
check('… Sitzung besteht weiter', E.call('status')[1].get('loggedIn') is True)
check('Abmelden mit Token', E.call('logout', {})[0] == 200 and E.call('status')[1].get('loggedIn') is False)
E.csrf = ''
check('Abmelden ohne Sitzung geht ohne Token', E.call('logout', {})[0] == 200)

# ── Bedrohungsliste: Lesen ohne Nebenwirkung ──
alt = {'quelle': 'Testliste', 'stand': '2026-01-01T10:00:00Z', 'anzahl': 1, 'netze': ['192.0.2.0/24']}
storage_write('bedrohungsliste', alt)
check('Bedrohungsliste eingeschaltet (veraltete Liste vorhanden)', A.call('fw_save', {'feed': True})[0] == 200)
code, r = A.call('fw_status')
check('fw_status meldet die veraltete Liste, ohne sie zu laden', code == 200 and r.get('feedVeraltet') is True and (doc('bedrohungsliste') or {}).get('stand') == alt['stand'], (code, r.get('feedVeraltet')))
E2 = Client('198.51.100.71'); E2.call('login', ERIKA)
check('Auffrischen: Bearbeiterin nicht (403)', E2.call('fw_feed_auffrischen', {})[0] == 403)
gut = A.csrf; A.csrf = 'falsch'
check('Auffrischen: ohne gültiges Token nicht (403)', A.call('fw_feed_auffrischen', {})[0] == 403)
A.csrf = gut
code, r = A.call('fw_feed_auffrischen', {})
check('Auffrischen: Administrator (geladen oder ohne Verbindung unverändert)', code == 200 and r.get('aufgefrischt') in (True, False) and 'feed' in r, (code, r.get('aufgefrischt')))
check('Auffrischen nur per POST (405)', A.call('fw_feed_auffrischen')[0] == 405)
A.call('fw_save', {'feed': False})
check('ausgeschaltet: nicht veraltet', A.call('fw_status')[1].get('feedVeraltet') is False)

ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
