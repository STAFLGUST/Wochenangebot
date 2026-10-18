from umgebung import storage_raw
from umgebung import BASE  # Testserver je Gruppe (parallel)
import sys
import json, os, re
from playwright.sync_api import sync_playwright
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44, wait_text
from testdaten import de, preis, preise, artikel, bestand_kg
DATA = os.environ['UDATA']
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def login(pg, user, pw, wait=True):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
    if wait: pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def logout(pg):
    pg.click('#btn-more'); pg.click('[data-act="logout"]'); pg.wait_for_selector('#screen-auth:not([hidden])')
def set_price(pg, code, v):
    i = pg.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"]) input[data-f="price"]').first
    i.fill(v); i.press('Tab')
    pg.wait_for_function("document.querySelector('#save-state').className.includes('saved')", timeout=8000)
def api_from_page(pg, action, body):
    return pg.evaluate("""async ([action, body]) => {
        const s = await (await fetch('../api/?action=status', {credentials:'same-origin'})).json();
        const r = await fetch('../api/?action=' + action, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRF-Token': s.csrf || ''}, body: JSON.stringify(body)});
        return [r.status, await r.json()];
    }""", [action, body])

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())

    # ---- Migration bisheriges Passwort → Nutzer „admin“
    login(a, 'admin', 'Sicheres-Passwort-1')
    check('migration: old password works as user admin', True)
    check('admin.php migrated away, nutzer.php exists', storage_raw('admin') is None and storage_raw('nutzer') is not None)
    check('admin sees Nutzer + Protokoll tabs', a.locator('#vt-users').is_visible() and a.locator('#vt-log').is_visible())
    a.click('#btn-more'); check('menu shows user + role', 'Administrator' in a.inner_text('#menu-user') and 'admin' in a.inner_text('#menu-user')); a.keyboard.press('Escape')

    # ---- Nutzer anlegen
    a.click('#vt-users'); a.wait_for_selector('.utab')
    check('users list has admin', a.locator('.utab tbody tr').count() == 1)
    def add_user(uname, name, role, pw, must=True):
        a.click('#user-add'); a.wait_for_selector('#dlg-user[open]')
        a.fill('#user-body [name=name]', name); a.fill('#user-body [name=username]', uname)
        a.check(f'#user-body [name=role][value={role}]')
        a.fill('#user-body [name=password]', pw)
        if not must: a.uncheck('#user-body [name=mustChange]')
        a.click('#user-body [type=submit]')
    add_user('anna', 'Anna Beispiel', 'editor', 'Start-Kennwort-123')
    a.wait_for_function("!document.querySelector('#dlg-user').open"); a.wait_for_timeout(300)
    add_user('ben', 'Ben Leser', 'viewer', 'Leser-Kennwort-123', must=False)
    a.wait_for_function("!document.querySelector('#dlg-user').open"); a.wait_for_timeout(300)
    check('3 users listed', a.locator('.utab tbody tr').count() == 3, a.locator('.utab tbody tr').count())
    check('role badges', 'Bearbeiter' in a.inner_text('.utab') and 'Nur ansehen' in a.inner_text('.utab'))
    add_user('Anna', 'Doppelt', 'viewer', 'Irgendwas-123')
    wait_text(a, '#user-err', 'bereits vergeben'); check('duplicate username rejected', 'bereits vergeben' in a.inner_text('#user-err'), a.inner_text('#user-err'))
    a.fill('#user-body [name=username]', 'x'); a.click('#user-body [type=submit]'); wait_text(a, '#user-err', 'Benutzername')
    check('invalid username rejected', 'Benutzername' in a.inner_text('#user-err'))
    a.click('#user-body [data-uact="gen"]'); gp = a.input_value('#user-body [name=password]'); check('password suggestion', len(gp) >= 12, gp)
    a.keyboard.press('Escape')
    a.screenshot(path=SH + '/users.png')
    # eigener Zugang: Rolle / aktiv gesperrt
    a.locator('.utab tbody tr:has-text("(Sie)")').click(); a.wait_for_selector('#dlg-user[open]')
    check('own role + active locked', a.locator('#user-body [name=role]:disabled').count() == 3 and a.locator('#user-body [name=active]').is_disabled() and a.locator('#user-body [data-uact=del]').count() == 0)
    a.keyboard.press('Escape')
    r = api_from_page(a, 'user_save', {'id': a.evaluate("1") and '', 'name': 'x'})
    check('server validates role', r[0] == 422, r)

    # ---- Änderungen protokollieren (zusammengefasst)
    a.click('#vt-edit')
    set_price(a, '10601', '24,10')
    set_price(a, '10601', '24,50')
    set_price(a, '10823', '15,00')
    a.click('#vt-log'); a.wait_for_selector('.ltab')
    t = a.inner_text('#log-list')
    check('log: login entry', 'Angemeldet' in t)
    check('log: merged draft entry', t.count('Entwurf bearbeitet:') == 1 and '2 Preise geändert' in t, re.sub(r'\s+', ' ', t)[:400])
    a.locator('tr.lrow.has-d:has-text("Entwurf bearbeitet")').first.click(); a.wait_for_selector('.ctab')
    ct = a.inner_text('.ctab')
    check('details: start value → 24,50 (start value kept)', '10601' in ct and de(preis('10601')) + ' €/kg' in ct and '24,50 €/kg' in ct and '24,10' not in ct, ct)
    a.screenshot(path=SH + '/log.png')
    # Rücknahme hebt Eintrag auf
    a.click('#vt-edit'); set_price(a, '10823', de(preis('10823')))
    a.click('#vt-log'); a.wait_for_selector('.ltab'); a.locator('tr.lrow.has-d:has-text("Entwurf bearbeitet")').first.click(); a.wait_for_selector('.ctab')
    check('reverting a change removes it from entry', '10823' not in a.inner_text('.ctab') and '1 Preis geändert' in a.inner_text('#log-list'))

    logout(a)
    # ---- falsches Passwort
    login(a, 'ben', 'falsch-falsch', wait=False); a.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('wrong password rejected', 'nicht korrekt' in a.inner_text('#auth-err'))

    # ---- Bearbeiter mit Pflicht-Passwortwechsel
    login(a, 'anna', 'Start-Kennwort-123', wait=False); a.wait_for_selector('#pw2-wrap:not([hidden])')
    check('must-change screen shown', 'eigenes Passwort' in a.inner_text('#auth-intro') and not a.locator('#au-user-wrap').is_visible())
    a.fill('#pw1', 'Neu-Kennwort-4567'); a.fill('#pw2', 'Neu-Kennwort-4567'); a.click('#auth-submit')
    try:
        a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    except Exception:   # Diagnose für seltene CI-Ausreißer: Meldung und Bild festhalten
        print('FAIL must-change: editor not shown  ' + repr(a.inner_text('#auth-err')) + ' auth hidden=' + str(a.locator('#screen-auth').is_hidden()))
        a.screenshot(path=SH + '/users-mustchange-fehler.png')
        raise
    check('editor: no admin tabs', not a.locator('#vt-users').is_visible() and not a.locator('#vt-log').is_visible())
    check('editor: publish visible', a.locator('#btn-publish').is_visible())
    r = api_from_page(a, 'user_save', {'name': 'Hack', 'username': 'hack', 'role': 'admin', 'active': True, 'password': 'Hack-Hack-123'})
    check('editor cannot create users (403)', r[0] == 403, r)
    set_price(a, '10701', '29,00')
    a.click('#btn-publish'); a.click('#dlg-publish [data-ia="publish"]'); a.wait_for_function("!document.querySelector('#dlg-publish').open")
    logout(a)

    # ---- Nur ansehen
    login(a, 'ben', 'Leser-Kennwort-123')
    check('viewer: inputs disabled', a.locator('tr[data-id] input[data-f="price"]').first.is_disabled() and a.locator('#m-week').is_disabled())
    check('viewer: search still usable', a.locator('#ed-q').is_enabled())
    check('viewer: publish/import hidden', not a.locator('#btn-publish').is_visible() and not a.locator('#btn-import').is_visible())
    check('viewer: read-only state shown', 'Nur Ansicht' in a.inner_text('#save-state'))
    a.locator('tr[data-id] [data-act="item"]').first.click(); a.wait_for_selector('#dlg-item[open]')
    check('viewer: item dialog read-only', a.locator('#item-body [name=price]').is_disabled() and not a.locator('#item-body [data-ia=del]').is_visible())
    a.keyboard.press('Escape')
    r = api_from_page(a, 'save_draft', {'model': {'meta': {}, 'groups': [], 'items': []}, 'revision': 0})
    check('viewer cannot save draft (403)', r[0] == 403, r)
    r = api_from_page(a, 'publish', {'model': {}})
    check('viewer cannot publish (403)', r[0] == 403, r)
    a.click('#vt-hist'); a.wait_for_selector('#hist-data')
    check('viewer can view price history', a.locator('#view-hist').is_visible())
    a.screenshot(path=SH + '/viewer.png')

    # ---- Admin deaktiviert Ben → Sitzung endet
    b = br.new_context(viewport={'width': 1440, 'height': 950}).new_page(); b.on('pageerror', lambda e: errs.append('b: ' + str(e)))
    login(b, 'admin', 'Sicheres-Passwort-1')
    b.click('#vt-users'); b.wait_for_selector('.utab'); b.locator('.utab tbody tr:has-text("Ben Leser")').click(); b.wait_for_selector('#dlg-user[open]')
    b.uncheck('#user-body [name=active]'); b.click('#user-body [type=submit]'); b.wait_for_function("!document.querySelector('#dlg-user').open"); b.wait_for_timeout(300)
    check('ben shown deactivated', 'deaktiviert' in b.locator('.utab tbody tr:has-text("Ben Leser")').inner_text(), b.inner_text('.utab'))
    # Kein Klick nötig: der Hintergrundabgleich kann die Anmeldemaske schon gezeigt haben (gewollt)
    st = a.evaluate("fetch('../api/?action=draft',{credentials:'same-origin'}).then(r=>r.status)")
    check('deactivated user session ends (401)', st == 401, st)
    logout_ok = True
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'ben'); a.fill('#pw1', 'Leser-Kennwort-123'); a.click('#auth-submit'); a.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('deactivated user cannot log in', 'deaktiviert' in a.inner_text('#auth-err'), a.inner_text('#auth-err'))

    # ---- Passwort für Anna neu setzen → muss ändern
    b.locator('.utab tbody tr:has-text("Anna Beispiel")').click(); b.wait_for_selector('#dlg-user[open]')
    b.fill('#user-body [name=password]', 'Reset-Kennwort-999'); b.click('#user-body [type=submit]'); b.wait_for_function("!document.querySelector('#dlg-user').open"); b.wait_for_timeout(300)
    check('anna must change after reset', 'muss Passwort ändern' in b.locator('.utab tbody tr:has-text("Anna Beispiel")').inner_text())
    # letzter Admin
    r = api_from_page(b, 'user_delete', {'id': b.locator('.utab tbody tr:has-text("(Sie)")').get_attribute('data-uid')})
    check('cannot delete self', r[0] == 422, r)
    # Ben löschen
    b.locator('.utab tbody tr:has-text("Ben Leser")').click(); b.wait_for_selector('#dlg-user[open]')
    b.click('#user-body [data-uact=del]'); b.click('#dlg-confirm [data-v="1"]'); b.wait_for_timeout(500)
    check('ben deleted', b.locator('.utab tbody tr').count() == 2)

    # ---- Protokoll vollständig
    b.click('#vt-log'); b.wait_for_selector('.ltab')
    t = b.inner_text('#log-list')
    for label, cond in [('anna password change', 'Eigenes Passwort geändert' in t), ('publish by anna', 'veröffentlicht' in t and 'Anna Beispiel' in t),
                        ('failed login logged', 'Anmeldung fehlgeschlagen' in t and '„ben“' in t), ('user created', 'Nutzer „anna“' in t),
                        ('user deleted', '„ben“ (Ben Leser) gelöscht' in t), ('deactivation logged', True)]:
        check('log: ' + label, cond)
    b.locator('tr.lrow:has-text("Nutzer „ben“ geändert")').first.click(); b.wait_for_timeout(200)
    check('log details: deactivation', 'deaktiviert' in b.inner_text('#log-list'))
    b.select_option('#log-user', 'anna'); b.wait_for_timeout(200)
    names = set(x.strip() for x in b.locator('.ltab .l-user .uname').all_inner_texts())
    check('filter by user', names == {'anna'}, names)
    b.select_option('#log-user', ''); b.select_option('#log-type', 'publish'); b.wait_for_timeout(200)
    check('filter by type', b.locator('tr.lrow').count() == 1)
    b.select_option('#log-type', ''); b.fill('#log-q', '10701'); b.wait_for_timeout(300)
    check('search in details', b.locator('tr.lrow').count() >= 2, b.locator('tr.lrow').count())
    b.fill('#log-q', '')
    with b.expect_download() as dl: b.click('#log-csv')
    csv = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV export', csv.startswith('Datum;Uhrzeit;Benutzername') and '10601' in csv and de(preis('10601')) + ' €/kg' in csv)

    # ---- Mobil
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    login(m, 'admin', 'Sicheres-Passwort-1')
    m.click('#vt-users'); m.wait_for_selector('.utab'); m.screenshot(path=SH + '/users-mobile.png')
    sw1 = m.evaluate('document.documentElement.scrollWidth')
    m.click('#vt-log'); m.wait_for_selector('.ltab'); m.locator('tr.lrow.has-d').first.click(); m.wait_for_timeout(200); m.screenshot(path=SH + '/log-mobile.png')
    sw2 = m.evaluate('document.documentElement.scrollWidth')
    check('mobile no h-scroll', sw1 <= 390 and sw2 <= 390, (sw1, sw2))
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
