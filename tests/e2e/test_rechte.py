"""Nutzerrechte: Rechte je Rolle (einstellbar) und Ausnahmen je Nutzer (erlauben/verbieten).
Prüft Standards (= bisheriges Rollenmodell plus Modulzugang für alle Kacheln), Durchsetzung auf dem Server,
Voraussetzungen, Schutz der Administratorrechte, Protokoll und die Oberfläche (Rollen und Rechte, Ausnahmen im
Nutzer-Dialog, Sichtbarkeit). Eigene Rollen und Modulzugang im Einzelnen: Gruppen „rollen“ und „rollen_host“.
Läuft gegen den Test-Mailserver (Versand durch einen berechtigten Bearbeiter)."""
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


EDITOR_DEFAULT = {'angebot.bearbeiten', 'angebot.veroeffentlichen', 'angebote.verwalten', 'preisverlauf.sehen', 'preisverlauf.bearbeiten',
                  'bestand.sehen', 'bestand.einkaufspreise', 'bestand.importieren', 'stammdaten.sehen', 'stammdaten.bearbeiten', 'einkauf.sehen', 'einkauf.melden',
                  'bestellungen.sehen', 'bestellungen.bearbeiten', 'hr.antrag'}
VIEWER_DEFAULT = {'preisverlauf.sehen', 'bestand.sehen', 'stammdaten.sehen', 'einkauf.sehen', 'hr.antrag'}   # hr.antrag: eigener Urlaub (Modul HR)
# Modulzugang „<modul>.zugang“ je Kachel (lib/rechte.php): Standard für beide Standardrollen – alle behalten ihre Kacheln
ZUGANG = {f'{m}.zugang' for m in ['angebot', 'bestand', 'crm', 'rewe', 'qs', 'einkauf', 'import', 'hr', 'marketing', 'controlling', 'verwaltung']}
EDITOR_DEFAULT |= ZUGANG
VIEWER_DEFAULT |= ZUGANG
STOCK = {'date': '2026-10-16', 'source': 'Bestand.xls', 'articles': [{'code': '1', 'name': 'Testartikel', 'kg': 10, 'lots': []}]}

smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for name, user, role, pw in [('Erika Editor', 'erika', 'editor', 'Editor-Zugang-77'), ('Vera Viewer', 'vera', 'viewer', 'Leser-Zugang-55'),
                             ('Emil Editor', 'emil', 'editor', 'Editor-Zugang-88')]:
    A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
rev = A.call('kunden')[1]['rev']
code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': 'Kantine Nord', 'nr': 'K-1', 'email': 'kantine@example.org', 'active': True, 'angebote': ['std'],
                                'login': {'username': 'kantine.nord', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
check('customer created', code == 200, r)
kid = r['customer']['id']
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}


def login(user, pw):
    c = Client('198.51.100.%d' % (10 + len(user)))
    c.call('login', {'username': user, 'password': pw})
    return c


E, V, M = login('erika', 'Editor-Zugang-77'), login('vera', 'Leser-Zugang-55'), login('emil', 'Editor-Zugang-88')
perms = lambda c: set((c.call('status')[1].get('user') or {}).get('perms') or [])
# Standard = bisheriges Rollenmodell
check('defaults: editor rights unchanged', perms(E) == EDITOR_DEFAULT, sorted(perms(E) ^ EDITOR_DEFAULT))
check('defaults: viewer rights unchanged', perms(V) == VIEWER_DEFAULT, sorted(perms(V) ^ VIEWER_DEFAULT))
check('defaults: viewer cannot import stock', V.call('stock_import', STOCK)[0] == 403)
check('defaults: editor sees no customers and log', E.call('kunden')[0] == 403 and E.call('log')[0] == 403)
check('defaults: editor cannot reauthenticate', E.call('reauth', {'password': 'Editor-Zugang-77'})[0] == 403)
# nur Administratoren verwalten Rechte
check('editor cannot read or change rights', E.call('rechte')[0] == 403 and E.call('rechte_save', {'roles': {'editor': list(EDITOR_DEFAULT) + ['kunden.bearbeiten']}})[0] == 403)
check('editor cannot grant itself rights', E.call('user_save', {'id': uid['erika'], 'name': 'Erika Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.bearbeiten']})[0] == 403)
code, rr = A.call('rechte')
check('rights overview for admin', code == 200 and len(rr['catalog']) >= 19 and set(rr['roles']['editor']) == EDITOR_DEFAULT and rr['adminOnly'] and not rr['custom'], code)

# Ausnahme je Nutzer: Leser darf Bestand hochladen
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Viewer', 'role': 'viewer', 'active': True, 'grant': ['bestand.importieren'], 'deny': []})
check('admin grants a single right', code == 200, r)
check('viewer with grant can import stock', V.call('stock_import', STOCK)[0] == 200)
check('viewer with grant still cannot edit draft', V.call('save_draft', {'model': {}})[0] == 403)
# Verbot: Bearbeiter darf nicht veröffentlichen
code, r = A.call('user_save', {'id': uid['emil'], 'name': 'Emil Editor', 'role': 'editor', 'active': True, 'grant': [], 'deny': ['angebot.veroeffentlichen', 'preisverlauf.sehen']})
check('admin denies rights', code == 200, r)
pm = perms(M)
check('denied rights removed, dependent rights too', 'angebot.veroeffentlichen' not in pm and 'preisverlauf.sehen' not in pm and 'preisverlauf.bearbeiten' not in pm and 'angebot.bearbeiten' in pm, sorted(pm))
check('denied publish is refused by the server', M.call('publish', {'model': {}})[0] == 403 and M.call('history_list')[0] == 403)
code, r = A.call('user_save', {'id': uid['emil'], 'name': 'Emil Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.sehen'], 'deny': ['kunden.sehen']})
check('deny wins over grant', code == 200 and 'kunden.sehen' not in perms(M) and M.call('kunden')[0] == 403)
# Bearbeiter darf das Wochenangebot senden (inkl. Passwortbestätigung)
A.call('user_save', {'id': uid['erika'], 'name': 'Erika Editor', 'role': 'editor', 'active': True, 'grant': ['wochenangebot.senden'], 'deny': []})
pe = perms(E)
check('grant pulls in its requirement (sending needs viewing customers)', {'wochenangebot.senden', 'kunden.sehen'} <= pe and 'kunden.bearbeiten' not in pe, sorted(pe))
check('editor with send right sees customers but cannot change them', E.call('kunden')[0] == 200 and E.call('kunde_save', {'id': kid, 'firma': 'X'})[0] == 403)
check('editor with send right may confirm its password', E.call('reauth', {'password': 'Editor-Zugang-77'})[0] == 200)
code, r = E.call('kunden_rundmail', {'week': 43, 'year': 2026, 'ids': [kid], 'note': ''})
check('editor sends the weekly offer', code == 200 and until(lambda: any('kantine@example.org' in m['to'] for m in smtp.messages), 5), r)
check('editor still has no admin-only access', [E.call('users')[0], E.call('mail_save', {})[0], E.call('security_diag', {})[0], E.call('rechte')[0]] == [403] * 4, [E.call('users')[0], E.call('mail_save', {})[0], E.call('security_diag', {})[0]])
# Administratorrolle: Ausnahmen werden verworfen
code, r = A.call('user_save', {'id': uid['emil'], 'name': 'Emil Editor', 'role': 'admin', 'active': True, 'grant': [], 'deny': ['kunden.sehen']})
u = next(x for x in A.call('rechte')[1]['users'] if x['id'] == uid['emil'])
check('admin role clears exceptions', code == 200 and u['deny'] == [] and u['grant'] == [], u)
A.call('user_save', {'id': uid['emil'], 'name': 'Emil Editor', 'role': 'editor', 'active': True})

# Rechte je Rolle ändern
roles = {'viewer': sorted(VIEWER_DEFAULT | {'protokoll.sehen', 'stammdaten.bearbeiten'}), 'editor': sorted(EDITOR_DEFAULT - {'preisverlauf.sehen'})}
code, r = A.call('rechte_save', {'roles': roles})
check('role rights saved, requirements kept consistent', code == 200 and 'preisverlauf.sehen' in r['roles']['editor'] and 'stammdaten.sehen' in r['roles']['viewer'], r)
check('role rights apply immediately', V.call('log')[0] == 200 and V.call('master_save', {'master': {}})[0] != 403)
check('unknown rights are ignored', A.call('rechte_save', {'roles': {'viewer': roles['viewer'] + ['nutzer.verwalten'], 'editor': roles['editor']}})[0] == 200 and 'nutzer.verwalten' not in perms(V))
entries = A.call('log')[1].get('entries') or []
check('changes are logged', any('Rechte der Rollen geändert' in str(e) for e in entries) and any('Verboten' in str(e) for e in entries))
check('rights change needs a fresh password confirmation', A.call('rechte_save', {'roles': 'x'})[0] == 422)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def page(user, password, w=1440):
        pg = br.new_page(viewport={'width': w, 'height': 950}, is_mobile=w < 500); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return pg

    a = page('admin', PW)
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on')
    box = lambda k: a.locator(f'#view-rollen [data-rl-key="{k}"]')
    waehle = lambda r: (a.click(f'#view-rollen [data-rl-wahl="{r}"]'), a.wait_for_selector(f'#view-rollen .rl-item.on[data-rl-wahl="{r}"]'))
    waehle('viewer')
    check('UI: role view shows saved role rights', box('protokoll.sehen').is_checked() and a.locator('#view-rollen .rl-admin .rl-recht').count() == 3)
    waehle('editor')
    check('UI: editor rights as saved', not box('kunden.sehen').is_checked() and box('angebot.zugang').is_checked())
    a.screenshot(path=SH + '/rechte-tabelle.png')
    box('kunden.bearbeiten').check()
    check('UI: checking a right ticks its requirement', box('kunden.sehen').is_checked())
    box('kunden.sehen').uncheck()
    check('UI: unchecking a requirement clears dependent rights', not box('kunden.bearbeiten').is_checked())
    box('bestellungen.sehen').uncheck()
    a.click('[data-rl-akt=speichern]'); a.wait_for_function("() => !document.querySelector('#rl-stand') || !document.querySelector('#rl-stand').textContent")
    check('UI: rights saved', 'bestellungen.sehen' not in A.call('rechte')[1]['roles']['editor'] and 'bestellungen.bearbeiten' not in A.call('rechte')[1]['roles']['editor'])
    a.click('[data-rl-akt=standard]')
    check('UI: restore defaults fills the role', box('bestellungen.sehen').is_checked() and box('bestellungen.bearbeiten').is_checked())
    a.click('[data-rl-akt=speichern]'); a.wait_for_function("() => !document.querySelector('#rl-stand').textContent")
    waehle('viewer'); a.click('[data-rl-akt=standard]'); a.click('[data-rl-akt=speichern]'); a.wait_for_function("() => !document.querySelector('#rl-stand').textContent")
    check('UI: defaults saved', set(A.call('rechte')[1]['roles']['editor']) == EDITOR_DEFAULT and set(A.call('rechte')[1]['roles']['viewer']) == VIEWER_DEFAULT)
    a.click('#vt-users'); a.wait_for_selector('#us-zu-rollen')
    check('UI: users table shows exceptions', '+1' in a.inner_text('#view-users tr:has-text("vera")'))
    a.click(f'[data-uedit="{uid["vera"]}"]'); a.wait_for_selector('#dlg-user[open] #ur-box')
    check('UI: user dialog lists exceptions', a.locator('#ur-list [data-ur="bestand.importieren"]').input_value() == 'grant')
    a.select_option('#ur-list [data-ur="kunden.sehen"]', 'grant')
    a.check('#dlg-user input[name=rollen][value=editor]')
    check('UI: role change keeps chosen exceptions', a.locator('#ur-list [data-ur="kunden.sehen"]').input_value() == 'grant')
    a.check('#dlg-user input[name=rollen][value=admin]')
    check('UI: no exceptions for administrators', a.locator('#ur-box').is_hidden())
    a.check('#dlg-user input[name=rollen][value=viewer]')
    a.screenshot(path=SH + '/rechte-nutzer.png')
    a.click('#dlg-user button[type=submit]'); a.wait_for_selector('#dlg-user', state='hidden')
    v = next(x for x in A.call('rechte')[1]['users'] if x['username'] == 'vera')
    check('UI: exceptions saved with the user', set(v['grant']) == {'bestand.importieren', 'kunden.sehen'} and v['role'] == 'viewer', v)
    a.set_viewport_size({'width': 390, 'height': 844}); a.wait_for_timeout(200)
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on'); a.screenshot(path=SH + '/rechte-390.png')
    check('mobile: no horizontal page scroll', a.evaluate('document.documentElement.scrollWidth') <= 390)
    # Leser mit Kundenansicht: sieht Kunden, darf nichts ändern
    vp = page('vera', 'Leser-Zugang-55')
    check('UI viewer: customers tab visible, no admin areas', vp.is_visible('#vt-kunden') and not vp.is_visible('#vt-users') and not vp.is_visible('#vt-log'))
    vp.click('#vt-kunden'); vp.wait_for_selector('#view-kunden tr:has-text("Kantine Nord")')
    check('UI viewer: no add and no send buttons', not vp.is_visible('#k-add') and not vp.is_visible('#k-rund') and not vp.is_visible('#btn-send'))
    vp.click(f'[data-kedit="{kid}"]'); vp.wait_for_selector('#dlg-kunde[open]')
    check('UI viewer: customer dialog read-only', vp.locator('#dlg-kunde input:not([disabled]):visible').count() == 0 and not vp.is_visible('#dlg-kunde button[type=submit]'))
    vp.close()
    # Bearbeiter mit Verbot: kein Veröffentlichen-Knopf; Bearbeiter mit Versandrecht: Senden-Knopf
    A.call('user_save', {'id': uid['emil'], 'name': 'Emil Editor', 'role': 'editor', 'active': True, 'deny': ['angebot.veroeffentlichen']})
    mp = page('emil', 'Editor-Zugang-88')
    check('UI: denied publish hides the button', not mp.is_visible('#btn-publish') and not mp.is_visible('#btn-send'))
    mp.close()
    ep = page('erika', 'Editor-Zugang-77')
    check('UI: editor with send right sees the send button', ep.is_visible('#btn-send'))
    ep.click('#btn-send'); ep.wait_for_selector('#dlg-rund[open]')
    check('UI: send dialog opens for the editor', 'Kantine Nord' in ep.inner_text('#rund-body'))
    ep.close()
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
