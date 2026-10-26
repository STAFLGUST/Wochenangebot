"""Notfallmodus (Modul Sicherheit, lib/notfall.php, docs/plattform/modul-sicherheit.md).

Geprüft: Rechte (sicherheit.notfall löst aus, beenden nur Administrator, sicherheit.sehen nur lesen, ohne Recht 403, anonym 401,
Standardrollen ohne Modulzugang); Pflichtangaben (Grund, Bestätigungswort); Wirkung: Kunden sehen Wartung mit neutralem Hinweis
(Kundenaktionen 503, Kundensitzungen beendet), Mitarbeiter ohne Administratorrolle ausgesperrt (Sitzungen beendet, nach neuer
Anmeldung 503 auf allen sperrbaren Oberflächen, Status/Abmelden/Modulübersicht bleiben), Administratoren arbeiten weiter (auch auf
der Kundenseite), eigene Sitzung bleibt; Firewall-Vorlage „Notfall“ mit Schnappschuss; E-Mail-Versand pausiert, Benachrichtigung
geht sofort raus; Protokoll und Wartungsverlauf; doppeltes Auslösen 409; Beenden stellt Einstellungen wieder her (oder behält
sie), Verlauf; von Hand eingeschaltete Wartung bleibt; Option „andere Administratoren abmelden“; Server-Werkzeug
deploy/notfall-aus.php. Nur synthetische Testdaten.
"""
import json
import os
import subprocess
import sys

from kunden_hilfe import Client
from order_setup import setup
from umgebung import REPO, until, storage_raw

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def doc(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


smtp, A, K, K2, kid, payload, nr = setup()
mails_to = lambda a: [m for m in smtp.messages if a in m['to']]   # noqa: E731
check('Benachrichtigung „Sicherheitsereignisse“ an it@ eingerichtet',
      A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org'}}})[0] == 200)

for u, n, r, p, extra in (('bea', 'Bea Bearbeiterin', 'editor', 'Kollegin-Zugang-3', {}),
                          ('nina', 'Nina Notfall', 'editor', 'Notfall-Zugang-7', {'grant': ['sicherheit.notfall']}),
                          ('sven', 'Sven Sicht', 'viewer', 'Leser-Zugang-55', {'grant': ['sicherheit.sehen']}),
                          ('adam', 'Adam Zweitadmin', 'admin', 'Zweiter-Admin-Zugang-9', {})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
Be = Client('198.51.100.11'); Ni = Client('198.51.100.12'); Sv = Client('198.51.100.13'); Ad = Client('198.51.100.14')
check('Anmeldungen der Testkonten', all(c.call('login', {'username': u, 'password': p})[0] == 200 for c, u, p in (
    (Be, 'bea', 'Kollegin-Zugang-3'), (Ni, 'nina', 'Notfall-Zugang-7'), (Sv, 'sven', 'Leser-Zugang-55'), (Ad, 'adam', 'Zweiter-Admin-Zugang-9'))))
P = Client('198.51.100.20')   # anonymer Besucher der Angebotsseite

# ── Rechte ──
kat = {r['key']: r for r in A.call('rechte')[1].get('catalog', [])}
check('Rechte sicherheit.sehen und sicherheit.notfall ohne Standardrollen, Voraussetzung Modulzugang',
      kat.get('sicherheit.notfall', {}).get('default') == [] and kat.get('sicherheit.sehen', {}).get('default') == []
      and kat['sicherheit.notfall'].get('requires') == ['sicherheit.zugang'], {k: kat.get(k) for k in ('sicherheit.notfall', 'sicherheit.zugang')})
check('Modulzugang Sicherheit: keine Standardrolle (Registerfeld zugang_rollen = [])', kat.get('sicherheit.zugang', {}).get('default') == [], kat.get('sicherheit.zugang'))
check('Bearbeiterin ohne Recht: Lagebild 403', Be.call('sicherheit_lage')[0] == 403)
check('anonym: Lagebild 401', P.call('sicherheit_lage')[0] == 401)
st, r = Ni.call('sicherheit_lage')
check('Recht „Notfall auslösen“: Zustand ja, Lagebild nein', st == 200 and r['rechte'] == {'admin': False, 'sehen': False, 'notfall': True, 'beenden': False}
      and 'lage' not in r and r['notfall'] is None and r['wirkungen']['wort'] == 'NOTFALL', (st, r.get('rechte')))
st, r = Sv.call('sicherheit_lage')
check('Recht „Sicherheit ansehen“: Lagebild mit Kennzahlen, kein Auslösen', st == 200 and r['rechte']['sehen'] and not r['rechte']['notfall'] and 'kennzahlen' in r.get('lage', {}), (st, r.get('rechte')))
check('Recht „Sicherheit ansehen“: Ereignisse 200, Einstellungen/Konten 403',
      Sv.call('sicherheit_ereignisse')[0] == 200 and Sv.call('sicherheit_konten')[0] == 403 and Sv.call('security_status')[0] == 403)
check('Recht „Notfall auslösen“: keine Ereignisse, keine Einstellungen', Ni.call('sicherheit_ereignisse')[0] == 403 and Ni.call('security_status')[0] == 403)
check('Ansehen-Recht löst keinen Notfall aus (403)', Sv.call('sicherheit_notfall_an', {'grund': 'Test Test', 'wort': 'NOTFALL'})[0] == 403)
check('Bearbeiterin ohne Recht löst keinen Notfall aus (403)', Be.call('sicherheit_notfall_an', {'grund': 'Test Test', 'wort': 'NOTFALL'})[0] == 403)
check('ohne Anmeldung kein Notfall (401)', P.call('sicherheit_notfall_an', {'grund': 'Test Test', 'wort': 'NOTFALL'})[0] == 401)
st, r = Ni.call('sicherheit_notfall_an', {'grund': 'x', 'wort': 'NOTFALL'})
check('Grund ist Pflicht (422)', st == 422 and 'Grund' in r.get('error', ''), (st, r))
st, r = Ni.call('sicherheit_notfall_an', {'grund': 'Verdacht auf Zugriff', 'wort': 'notfal'})
check('Bestätigungswort muss stimmen (422)', st == 422 and 'NOTFALL' in r.get('error', ''), (st, r))
check('vor dem Notfall: Bearbeiterin arbeitet, Kunden sehen das Angebot', Be.call('stock')[0] == 200 and P.call('offer')[0] == 200 and K.call('kunde_status')[1].get('kunde'))
fw_vorher = doc('firewall') or {}
treffer_vorher = fw_vorher.get('treffer', 5)

# ── Auslösen durch eine Mitarbeiterin mit Recht ──
st, r = Ni.call('sicherheit_notfall_an', {'grund': 'Verdacht auf fremden Zugriff', 'wort': 'notfall', 'kundentext': 'Gleich wieder da.', 'admins': True, 'keycloak': True})
check('Notfall ausgelöst (Bestätigungswort ohne Groß-/Kleinschreibung)', st == 200 and r['notfall']['aktiv'] and r['notfall']['grund'] == 'Verdacht auf fremden Zugriff', (st, r))
n = doc('sicherheit-notfall') or {}
check('Dokument: aktiv, Urheber, Schnappschuss der Einstellungen', n.get('aktiv') and n.get('von') == 'nina' and set(n.get('vorher') or {}) == {'sicherheit', 'firewall'}, {k: n.get(k) for k in ('aktiv', 'von', 'optionen')})
check('Option „andere Administratoren“ nur für Administratoren, zentrale Anmeldung nur wenn eingerichtet',
      n.get('optionen') == {'firewall': True, 'admins': False, 'keycloak': False}, n.get('optionen'))
check('Firewall auf „Notfall“: Sperre ab dem 1. Treffer für 7 Tage', (doc('firewall') or {}).get('treffer') == 1 and doc('firewall').get('sperrMinuten') == 10080, doc('firewall'))
check('ohne eigenen zweiten Faktor: Zwei-Faktor-Pflicht unverändert, im Notfall vermerkt', 'Zwei-Faktor-Pflicht unverändert' in n.get('wirkung', {}).get('firewall', ''), n.get('wirkung'))
st, r = Ni.call('sicherheit_notfall_an', {'grund': 'Noch einmal auslösen', 'wort': 'NOTFALL'})
check('doppeltes Auslösen abgewiesen (409)', st == 409, (st, r))

# Kunden
st, r = P.call('offer')
check('Kunden: Angebot 503 mit neutralem Hinweis', st == 503 and r.get('wartung') and r.get('error') == 'Gleich wieder da.', (st, r))
ks = K.call('kunde_status')[1]
check('Kunden: Sitzung beendet, Status meldet Wartung ohne Urheber', ks.get('kunde') is None and ks['wartung']['message'] == 'Gleich wieder da.' and ks['wartung'].get('by') == '' and ks['wartung'].get('notfall'), ks.get('wartung'))
check('Kunden: neue Anmeldung pausiert (503)', Client('198.51.100.21').call('kunde_login', {'username': 'kantine.test', 'password': 'Kantine-Kennwort-5'})[0] == 503)
check('Abmelden vom Wochenangebot bleibt möglich (nicht in der Wartung)', P.call('abmelden1')[0] != 503)

# Mitarbeiter ohne Administratorrolle
check('Bearbeiterin: Sitzung beendet', Be.call('status')[1].get('loggedIn') is False)
check('Bearbeiterin: Anmeldung möglich (zentral nicht sperrbar)', Be.call('login', {'username': 'bea', 'password': 'Kollegin-Zugang-3'})[0] == 200)
st, r = Be.call('stock')
check('Bearbeiterin: Fachaktion gesperrt (503, Hinweis ohne Grund)', st == 503 and r.get('wartung') and 'Sicherheitsmaßnahme' in r.get('error', '') and 'fremden' not in json.dumps(r), (st, r))
check('Bearbeiterin: Schreibaktion gesperrt (503)', Be.call('save_draft', {'model': {}})[0] == 503)
sb = Be.call('status')[1]
check('Bearbeiterin: Status meldet Notfall ohne Einzelheiten, Eingabebereich gesperrt', sb['notfall'] == {'aktiv': True, 'seit': n['seit']} and sb['eingabeGesperrt'] is True, sb.get('notfall'))
mods = {m['id']: m for m in Be.call('module_status')[1]['module']}
check('Bearbeiterin: Kacheln Angebot und Verwaltung „Wartung“, Modulübersicht erreichbar',
      mods['angebot']['kachel']['status'] == 'wartung' and not mods['angebot']['kachel']['zugang'] and mods['verwaltung']['kachel']['status'] == 'wartung', mods['angebot']['kachel'])
check('Bearbeiterin: Kundenseite mit Mitarbeitersitzung ebenfalls gesperrt (503)', Be.call('offer')[0] == 503 and Be.call('kunde_status')[1]['staff'] is False)
check('Notfall-Mitarbeiterin: eigene Sitzung bleibt, Fachaktionen gesperrt, Zustand sichtbar',
      Ni.call('status')[1]['loggedIn'] and Ni.call('stock')[0] == 503 and Ni.call('sicherheit_lage')[1]['notfall']['grund'] == 'Verdacht auf fremden Zugriff')
check('Ansehen-Recht: Sitzung beendet (keine Administratorrolle)', Sv.call('status')[1].get('loggedIn') is False)

# Administratoren
check('Administrator: arbeitet weiter (Bestand, Entwurf)', A.call('stock')[0] == 200 and A.call('draft')[0] == 200)
check('Administrator: sieht die Kundenseite trotz Wartung', A.call('offer')[0] == 200 and A.call('kunde_status')[1]['staff'] is True)
check('zweiter Administrator: Sitzung bleibt (Option nur für Administratoren)', Ad.call('status')[1].get('loggedIn') is True)
ma = {m['id']: m for m in A.call('module_status')[1]['module']}
check('Administrator: Kachel „Wartung“ mit Hinweis, aber Zugang; Grund sichtbar', ma['angebot']['kachel']['status'] == 'wartung' and ma['angebot']['kachel']['zugang']
      and A.call('module_status')[1]['notfall']['grund'] == 'Verdacht auf fremden Zugriff', ma['angebot']['kachel'])
check('Modul Sicherheit bleibt erreichbar (nicht sperrbar)', ma['sicherheit']['kachel']['status'] == 'verfuegbar', ma['sicherheit']['kachel'])

# E-Mail
st, r = A.call('mail_test', {'to': 'test@example.org'})
check('E-Mail-Versand pausiert (Testmail 502 mit Hinweis)', st == 502 and 'Notfallmodus' in r.get('error', ''), (st, r))
check('keine Testmail beim Mailserver', not mails_to('test@example.org'))
check('Benachrichtigung sofort an it@ (trotz Versandpause)', until(lambda: any('NOTFALLMODUS AUSGELÖST' in m['subject'] for m in mails_to('it@example.org')), 8),
      [m['subject'] for m in smtp.messages])
m = next((m for m in mails_to('it@example.org') if 'NOTFALLMODUS' in m['subject']), {'text': ''})
check('Benachrichtigung nennt Auslöser, Grund und Wirkung', 'Nina Notfall' in m['text'] and 'Verdacht auf fremden Zugriff' in m['text'] and 'ausgesperrt' in m['text'], m['text'][:600])
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Notfall ausgelöst', 'Notfallmodus ausgelöst: Verdacht auf fremden Zugriff' in log)
v = A.call('module_status')[1]['verlauf']
check('Wartungsverlauf: Notfall vermerkt', v[0]['bereich'] == 'alle' and v[0]['grund'].startswith('Notfallmodus'), v[:1])
ev = A.call('sicherheit_ereignisse')[1]
check('Ereignisse: Notfall als eigene Art', any(e['a'] == 'notfall' and e['art'] == 'notfall' and e['stufe'] == 'bad' for e in ev['ereignisse']), ev.get('arten'))

# Von Hand eingeschaltete Wartung bleibt unabhängig
check('Wartungsmodus von Hand einschalten während des Notfalls', A.call('wartung_save', {'active': True, 'message': 'Inventur', 'until': ''})[0] == 200)

# ── Beenden: nur Administrator ──
check('Notfall-Mitarbeiterin darf nicht beenden (403)', Ni.call('sicherheit_notfall_aus', {})[0] == 403)
st, r = A.call('sicherheit_notfall_aus', {'notiz': 'Fehlalarm geprüft'})
check('Administrator beendet den Notfall, Einstellungen wiederhergestellt', st == 200 and r['ende']['einstellungen'] == 'wie vor dem Notfall wiederhergestellt' and r['verlauf'][0]['beendetVon'] == 'Administrator', (st, r))
check('Firewall wie vorher', (doc('firewall') or {}).get('treffer', 5) == treffer_vorher, doc('firewall'))
check('Dokument: aus, ohne Schnappschuss, Verlauf mit Grund und Notiz', (doc('sicherheit-notfall') or {}).get('aktiv') is False and 'vorher' not in doc('sicherheit-notfall')
      and doc('sicherheit-notfall')['verlauf'][0]['notiz'] == 'Fehlalarm geprüft')
check('zweites Beenden: 409', A.call('sicherheit_notfall_aus', {})[0] == 409)
check('Bearbeiterin arbeitet wieder', Be.call('stock')[0] == 200 and Be.call('status')[1]['notfall'] is None)
st, r = P.call('offer')
check('von Hand eingeschaltete Wartung bleibt (Hinweis „Inventur“)', st == 503 and r.get('error') == 'Inventur', (st, r))
check('Wartung von Hand beenden', A.call('wartung_save', {'active': False, 'message': '', 'until': ''})[0] == 200 and P.call('offer')[0] == 200)
check('E-Mail-Versand wieder möglich', A.call('mail_test', {'to': 'test@example.org'})[0] == 200)
check('Benachrichtigung „beendet“', until(lambda: any('Notfallmodus beendet' in m['subject'] for m in mails_to('it@example.org')), 8), [m['subject'] for m in mails_to('it@example.org')])

# ── Administrator löst aus: andere Administratoren abmelden, strenge Einstellungen behalten ──
st, r = A.call('sicherheit_notfall_an', {'grund': 'Übung mit allen Optionen', 'wort': 'NOTFALL', 'admins': True, 'firewall': True})
check('Administrator löst aus (Option andere Administratoren)', st == 200 and r['notfall']['optionen']['admins'] is True, (st, r))
check('zweiter Administrator abgemeldet, eigene Sitzung bleibt', Ad.call('status')[1].get('loggedIn') is False and A.call('status')[1].get('loggedIn') is True)
st, r = A.call('sicherheit_notfall_aus', {'firewall': False})
check('Beenden ohne Wiederherstellen: strenge Firewall bleibt', st == 200 and r['ende']['einstellungen'] == 'unverändert (streng)' and (doc('firewall') or {}).get('treffer') == 1, (st, r))

# ── Firewall abgewählt ──
fw_davor = doc('firewall')
st, r = A.call('sicherheit_notfall_an', {'grund': 'Nur Aussperren, ohne Firewall', 'wort': 'NOTFALL', 'firewall': False})
check('Notfall ohne Firewall-Vorlage: Einstellungen unverändert', st == 200 and doc('firewall') == fw_davor and 'abgewählt' in (doc('sicherheit-notfall') or {}).get('wirkung', {}).get('firewall', ''), (st, doc('firewall')))

# ── Server-Werkzeug ──
DATA = os.environ['UDATA']
out = subprocess.run(['php', os.path.join(REPO, 'deploy', 'notfall-aus.php')], env={**os.environ, 'DATA_DIR': DATA}, capture_output=True, text=True)
check('Server-Werkzeug beendet den Notfall', out.returncode == 0 and 'Notfallmodus beendet' in out.stdout, (out.stdout, out.stderr))
Be.call('login', {'username': 'bea', 'password': 'Kollegin-Zugang-3'})
check('danach: Bearbeiterin arbeitet, Kunden sehen das Angebot', Be.call('stock')[0] == 200 and P.call('offer')[0] == 200)
nd = doc('sicherheit-notfall') or {}
check('Verlauf: Server-Werkzeug als Beender', nd.get('aktiv') is False and nd['verlauf'][0]['beendetVon'] == 'Notfallwerkzeug (Server)' and len(nd['verlauf']) == 3, nd.get('verlauf', [])[:1])
check('Protokoll: Ende auf dem Server vermerkt', 'Notfallmodus auf dem Server beendet' in json.dumps(A.call('log')[1], ensure_ascii=False))
out = subprocess.run(['php', os.path.join(REPO, 'deploy', 'notfall-aus.php')], env={**os.environ, 'DATA_DIR': DATA}, capture_output=True, text=True)
check('zweiter Aufruf: nicht aktiv', 'nicht aktiv' in out.stdout, out.stdout)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
