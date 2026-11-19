"""Gemeinsame Hilfen für die Testgruppen des Moduls Container-Import (containerimport_*): Ergebnis sammeln, die beiden
Nutzer anlegen (Ina darf bearbeiten, Lea nur ansehen), anmelden, Container anlegen, Tage ab heute, die Seite des Moduls im
Browser öffnen.
Vorbild: qs_hilfe.py. Die Seite ruft in Tests nie fremde Server ab – jede Anfrage nach außen wird abgebrochen und gemerkt."""
import datetime
import re
from kunden_hilfe import Client, B

PW = 'Sicheres-Passwort-1'
USERS = {'ina': ('Ina Import', 'editor', 'Editor-Zugang-88', ['containerimport.eudr_sehen', 'containerimport.eudr_bearbeiten']),
         'lea': ('Lea Leser', 'viewer', 'Leser-Zugang-55', ['containerimport.eudr_sehen'])}
res = []


def check(n, c, i=''):
    """Eine Prüfung: Name, Ergebnis, bei Fehlschlag ein Hinweis zur Fehlersuche."""
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i and not c else ''))


def ende():
    """Zusammenfassung ausgeben und mit dem Ergebnis der Gruppe enden."""
    print(f'{sum(res)}/{len(res)} passed')
    raise SystemExit(0 if all(res) else 1)


def nutzer_anlegen():
    """Administrator anmelden und die beiden Nutzer des Moduls anlegen → (Administrator, Ina, Lea) als angemeldete Clients."""
    a = Client('198.51.100.2')
    check('Administrator angemeldet', a.call('login', {'username': 'admin', 'password': PW})[0] == 200)
    for user, (name, role, pw, grant) in USERS.items():
        a.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
        nr = next(u['id'] for u in a.call('users')[1]['users'] if u['username'] == user)
        a.call('user_save', {'id': nr, 'name': name, 'role': role, 'active': True, 'grant': grant, 'deny': []})
    return a, login('ina'), login('lea')


def login(user):
    c = Client('198.51.100.' + str(10 + list(USERS).index(user)))
    code, r = c.call('login', {'username': user, 'password': USERS[user][2]})
    assert code == 200, (user, code, r)
    return c


def kalender(client):
    """→ tag(n): Datum n Tage ab heute (Datum des Servers) als JJJJ-MM-TT."""
    heute = datetime.date.fromisoformat(client.call('containerimport_start')[1]['heute'])
    return lambda n: (heute + datetime.timedelta(days=n)).isoformat()


def container_anlegen(client, partie, **mehr):
    """Container mit dieser Partienummer anlegen – muss gelingen."""
    st, r = client.call('containerimport_eudr_sendung_save', {'id': '', 'rev': 0, 'partie': partie, 'lieferant': 'Frigorifico Beispiel', 'land': 'PY', 'ware': 'Rindfleisch, gekühlt', **mehr})
    assert st == 200, (st, r)
    return container(r, partie)


def container(r, partie):
    """Container mit dieser Partienummer aus einer Antwort ({} = nicht dabei)."""
    return next((s for s in r.get('sendungen', []) if s['partie'] == partie), {})


def seite(br, user, errs, fremd, vp=None, schema='light'):
    """Seite des Moduls für einen Nutzer öffnen; JavaScript-Fehler landen in errs, Anfragen nach außen in fremd."""
    ctx = br.new_context(viewport=vp or {'width': 1280, 'height': 900}, color_scheme=schema)
    ctx.route(re.compile(r'^https?://(?!127\.0\.0\.1[:/])'), lambda route: (fremd.append(route.request.url), route.abort()))
    pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', USERS[user][2]); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
    pg.goto(B + '/module/containerimport/'); pg.wait_for_selector('#ci-app:not([hidden])')
    return pg
