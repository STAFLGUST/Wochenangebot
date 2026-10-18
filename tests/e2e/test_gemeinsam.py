"""Mehrere Mitarbeiter bearbeiten den Entwurf gleichzeitig: Abgleich, Konflikte, Anwesenheit, Inaktivität."""
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
EPW = 'Editor-Zugang-77'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def sess_seen(cli, value=None):
    """Liest (bzw. setzt) den Zeitpunkt der letzten Aktivität in der getrennten Test-Sitzungsablage."""
    jar = next(h.cookiejar for h in cli.http.handlers if hasattr(h, 'cookiejar'))
    sid = next(c.value for c in jar if c.name == 'WA_ADMIN')
    code = 'session_id($argv[1]); session_start(); ' + (f'$_SESSION["seen"] = {value}; ' if value is not None else '') + 'echo (int)($_SESSION["seen"] ?? 0); session_write_close();'
    out = subprocess.run(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-r', code, sid], check=True, capture_output=True, text=True).stdout
    return int(out.strip() or 0)


def price(m, iid):
    it = next(x for x in m['items'] if x['id'] == iid)
    return (it.get('price') or {}).get('value')


def set_price(m, iid, v):
    next(x for x in m['items'] if x['id'] == iid)['price'] = {'status': 'value', 'value': v}


A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': EPW, 'mustChange': False})
E = Client('198.51.100.3')
check('editor login', E.call('login', {'username': 'erika', 'password': EPW})[0] == 200)
ADMIN_NAME = A.call('status')[1]['user']['name']

d = A.call('draft')[1]
m0 = d['published']; r0 = d['revision']
ids = [x['id'] for x in m0['items'] if (x.get('price') or {}).get('status') == 'value']
I1, I2, I3, I4, I5, I6 = ids[:6]

# --- API: Revisionen, Konflikt, Anwesenheit
ma = dict(m0); set_price(ma, I1, 11.11)
code, r = A.call('save_draft', {'model': ma, 'revision': r0})
check('first save ok', code == 200 and r['revision'] == r0 + 1, (code, r))
r1 = r['revision']
code, r = E.call('save_draft', {'model': m0, 'revision': r0})
check('stale save rejected (409) naming who saved', code == 409 and r.get('conflict') is True and r['revision'] == r1 and ADMIN_NAME in r['error'], (code, r))
d = E.call('draft')[1]
check('draft names who saved last', d['draftSavedBy'] == ADMIN_NAME and d['revision'] == r1)
check('stored draft carries savedBy', d['draft'].get('savedBy') == ADMIN_NAME)
check('ping: needs login', Client('198.51.100.9').call('draft_ping', {})[0] == 401)
check('ping: needs CSRF token (POST + JSON)', E.call('draft_ping')[0] in (403, 405, 415))
A.call('draft_ping', {})
code, p = E.call('draft_ping', {})
check('ping: revision and who else is here', code == 200 and p['revision'] == r1 and [x['name'] for x in p['editors']] == [ADMIN_NAME], p)
check('ping: own name not listed, others are', [x['name'] for x in A.call('draft_ping', {})[1]['editors']] == ['Erika Editor'])

# --- Hintergrundabfragen verlängern die Sitzung nicht (Abmeldung nach Inaktivität bleibt wirksam)
old = int(time.time()) - 600
sess_seen(E, old)
E.call('draft_ping', {}); E.call('draft_ping', {})
check('background ping keeps idle timer', sess_seen(E) == old, sess_seen(E))
E.http.open(urllib.request.Request(B + '/api/?action=draft&bg=1', headers={'X-Forwarded-For': E.ip}))
check('background draft fetch keeps idle timer', sess_seen(E) == old)
E.call('draft')
check('normal request counts as activity', sess_seen(E) > old)

# --- Veröffentlichen/Verwerfen prüfen die Revision; veraltete Fenster legen den Entwurf nicht neu an
code, r = E.call('publish', {'model': m0, 'revision': r0})
check('publish with stale revision rejected', code == 409, code)
code, r = A.call('publish', {'model': ma, 'revision': r1})
check('publish with current revision ok', code == 200 and r['revision'] == r1 + 1, (code, r))
r2 = r['revision']
code, r = E.call('save_draft', {'model': m0, 'revision': r1})
check('old window cannot recreate draft after publish', code == 409 and 'veröffentlicht' in r['error'], (code, r))
d = E.call('draft')[1]
check('after publish: no draft, revision kept', d['draft'] is None and d['revision'] == r2)
code, r = E.call('save_draft', {'model': d['published'], 'revision': r2})
check('new draft continues revision', code == 200 and r['revision'] == r2 + 1)
code, r = A.call('discard_draft', {'revision': r2})
check('discard with stale revision rejected', code == 409)
code, r = A.call('discard_draft', {'revision': r2 + 1})
check('discard with current revision ok', code == 200 and r['revision'] == r2 + 2)
REV = r['revision']

# --- Oberfläche: zwei Personen gleichzeitig
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def open_editor(user, password):
        ctx = br.new_context(viewport={'width': 1440, 'height': 950})
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
        return pg

    def sync(pg):
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_timeout(900)

    def pin(pg, iid):
        return pg.locator(f'tr[data-id="{iid}"] input[data-f="price"]')

    def wait_saved(pg):
        pg.wait_for_function("document.querySelector('#save-state').classList.contains('saved')", timeout=10000)

    a = open_editor('admin', PW)
    e = open_editor('erika', EPW)
    sync(a); sync(e)
    check('presence shown in editor', 'Auch hier' in e.inner_text('#save-state') and ADMIN_NAME in e.inner_text('#save-state'), e.inner_text('#save-state'))

    # beide ändern verschiedene Artikel
    pin(a, I2).fill('22,22'); pin(a, I2).press('Enter'); wait_saved(a)
    pin(e, I3).fill('33,33'); pin(e, I3).press('Enter'); wait_saved(e)
    sync(a); sync(e)
    check('editor sees admin change', pin(e, I2).input_value() == '22,22', pin(e, I2).input_value())
    check('admin sees editor change', pin(a, I3).input_value() == '33,33', pin(a, I3).input_value())
    srv = A.call('draft')[1]['draft']
    check('server draft holds both changes', price(srv, I2) == 22.22 and price(srv, I3) == 33.33)

    # gleichzeitiges Speichern ohne vorherigen Abgleich (409 → zusammenführen → erneut speichern)
    d = A.call('draft')[1]; m = d['draft']; set_price(m, I4, 44.44)
    check('api save in between', A.call('save_draft', {'model': m, 'revision': d['revision']})[0] == 200)
    pin(e, I5).fill('55,55'); pin(e, I5).press('Enter'); wait_saved(e)
    srv = A.call('draft')[1]['draft']
    check('conflicting save merged: both kept', price(srv, I4) == 44.44 and price(srv, I5) == 55.55, (price(srv, I4), price(srv, I5)))
    check('merged value visible without reload', pin(e, I4).input_value() == '44,44')

    # angefangene Eingabe bleibt beim Abgleich erhalten
    pin(e, I6).click(); pin(e, I6).fill('66,66')
    d = A.call('draft')[1]; m = d['draft']; set_price(m, I1, 12.34)
    A.call('save_draft', {'model': m, 'revision': d['revision']})
    sync(e)
    check('typing not interrupted by remote change', pin(e, I6).input_value() == '66,66' and e.evaluate("document.activeElement.dataset.f") == 'price')
    pin(e, I6).press('Tab'); e.wait_for_timeout(300); wait_saved(e)
    e.wait_for_timeout(300)
    srv = A.call('draft')[1]['draft']
    check('after leaving field: own and remote change saved', price(srv, I6) == 66.66 and price(srv, I1) == 12.34, (price(srv, I6), price(srv, I1)))
    check('remote change then shown', pin(e, I1).input_value() == '12,34', pin(e, I1).input_value())

    # Veröffentlichen, während jemand anderes noch gespeichert hat
    e.click('#btn-publish'); e.wait_for_selector('#dlg-publish[open] [data-ia="publish"]')
    d = A.call('draft')[1]; m = d['draft']; set_price(m, I2, 23.45)
    A.call('save_draft', {'model': m, 'revision': d['revision']})
    e.click('#dlg-publish [data-ia="publish"]')
    e.wait_for_selector('#dlg-publish .err-box', timeout=8000)
    check('publish conflict explained', ADMIN_NAME in e.inner_text('#dlg-publish .err-box') and 'erneut veröffentlichen' in e.inner_text('#dlg-publish .err-box'), e.inner_text('#dlg-publish .err-box'))
    e.screenshot(path=SH + '/gemeinsam-konflikt.png')
    e.click('#dlg-publish [data-ia="publish"]')
    e.wait_for_selector('#dlg-publish', state='hidden', timeout=8000)
    pub_items = A.call('draft')[1]['published']['items']
    pv = {x['id']: (x.get('price') or {}).get('value') for x in pub_items}
    check('second publish includes everyone\'s changes', pv.get(I2) == 23.45 and pv.get(I6) == 66.66 and pv.get(I4) == 44.44, {k: pv.get(k) for k in (I2, I4, I6)})
    sync(a)
    check('other window follows publication (no stale draft)', A.call('draft')[1]['draft'] is None and 'Keine Änderungen' in a.inner_text('#save-state'), a.inner_text('#save-state'))
    a.screenshot(path=SH + '/gemeinsam.png')
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
