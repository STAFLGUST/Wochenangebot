import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import re, json, time
from playwright.sync_api import sync_playwright, expect
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44
from testdaten import de, preis, preise, artikel, bestand_kg, excel_preis
results = []
def check(n, c, info=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(info)) if info else ''))

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    a = ctx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append('admin: ' + str(e)))
    a.on('dialog', lambda d: d.accept())
    pub = ctx.new_page(); pub.on('pageerror', lambda e: errs.append('pub: ' + str(e)))

    def pub_price(code):
        pub.goto(B + '/?r=' + str(time.time()) + '#ansicht=tabelle&suche=' + code); pub.wait_for_selector('tr.row, .empty')
        return pub.locator('tr.row td.c-price').first.inner_text().replace('\n', ' ') if pub.locator('tr.row').count() else None
    def wait_saved():
        a.wait_for_function("document.querySelector('#save-state').className.includes('saved') || document.querySelector('#save-state').className.includes('clean')", timeout=8000)
    def row(code):
        return a.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])').first

    # ---------- Setup ----------
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    check('setup screen shown', a.locator('#pw2-wrap').is_visible() and 'Ersteinrichtung' in a.inner_text('#auth-intro'))
    a.fill('#au-user', 'admin'); a.fill('#au-name', 'Test Admin')
    a.fill('#pw1', 'kurz'); a.fill('#pw2', 'kurz'); a.click('#auth-submit')
    check('setup: too short rejected', 'mindestens 10' in a.inner_text('#auth-err'))
    a.fill('#pw1', 'Sicheres-Passwort-1'); a.fill('#pw2', 'anders-Passwort-1'); a.click('#auth-submit')
    check('setup: mismatch rejected', 'stimmen nicht' in a.inner_text('#auth-err'))
    a.fill('#pw2', 'Sicheres-Passwort-1'); a.click('#auth-submit')
    a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('editor loaded 276 rows', a.locator('tr[data-id]').count() == 276, a.locator('tr[data-id]').count())
    check('meta KW 43', a.input_value('#m-week') == '43' and a.input_value('#m-year') == '2026' and 'Mo 19.10.' in a.inner_text('#m-info'))
    check('state: no changes', 'Keine Änderungen' in a.inner_text('#save-state'), a.inner_text('#save-state'))
    a.screenshot(path=SH + '/admin-editor.png')

    # ---------- Manual price edit ----------
    inp = row('10601').locator('input[data-f="price"]'); inp.fill('24,1'); inp.press('Tab')
    wait_saved()
    check('price formatted 24,10', row('10601').locator('input[data-f="price"]').input_value() == '24,10')
    check('row marked price change + was', 'is-price' in row('10601').get_attribute('class') and 'bisher' in row('10601').inner_text())
    check('changes bar 1 price', '1 Preis geändert' in a.inner_text('#changes').replace('\n', ' '), a.inner_text('#changes'))
    check('draft saved state', 'noch nicht veröffentlicht' in a.inner_text('#save-state'), a.inner_text('#save-state'))
    check('public unchanged before publish', pub_price('10601').startswith(de(preis('10601'))), pub_price('10601'))
    pv = ctx.new_page(); pv.goto(B + '/?vorschau=1#suche=10601'); pv.wait_for_selector('tr.row')
    check('preview shows draft', pv.locator('tr.row td.c-price').first.inner_text().startswith('24,10') and pv.locator('#preview-banner').is_visible())
    pv.close()
    # Knöpfe „Angebotsseite“ und „Vorschau“: index.html statt „../“ (auf angebot.dashboard-stafl.de leitet „/“ in den Editor um)
    check('Knopf Angebotsseite zeigt auf index.html', a.get_attribute('#btn-site', 'href') == '../index.html', a.get_attribute('#btn-site', 'href'))
    with ctx.expect_page() as neu:
        a.click('#btn-site')
    ps = neu.value; ps.wait_for_selector('tr.row')
    check('Angebotsseite öffnet die öffentliche Seite (veröffentlichter Stand, kein Editor)', ps.url.endswith('/index.html') and ps.locator('#screen-editor').count() == 0
          and ps.locator('#preview-banner').is_hidden(), ps.url)
    ps.close()
    with ctx.expect_page() as neu:
        a.click('#btn-preview')
    ps = neu.value; ps.wait_for_selector('#preview-banner:not([hidden])')
    check('Vorschau öffnet index.html?vorschau=1 mit dem Entwurf', '/index.html?vorschau=1' in ps.url, ps.url)
    ps.close()
    a.reload(); a.wait_for_selector('tr[data-id]')
    check('draft persists after reload', row('10601').locator('input[data-f="price"]').input_value() == '24,10')

    # Enter → next row
    row('10823').locator('input[data-f="price"]').click(); row('10823').locator('input[data-f="price"]').fill('15'); a.keyboard.press('Enter'); a.wait_for_timeout(150)
    check('Enter jumps to next row price', a.evaluate("document.activeElement.closest('tr').querySelector('[data-f=code]').value") == '10701')

    # invalid price
    i2 = row('10701').locator('input[data-f="price"]'); i2.fill('abc'); i2.press('Tab'); a.wait_for_timeout(100)
    check('invalid price marked', 'invalid' in i2.get_attribute('class'))
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    check('publish blocked with invalid price', a.locator('#dlg-publish [data-ia="publish"]').is_disabled() and 'nicht lesbar' in a.inner_text('#dlg-publish'))
    a.click('#dlg-publish [data-close]')
    i2.fill('a. Anfr.'); i2.press('Tab'); a.wait_for_timeout(100)
    check('a. Anfr. accepted', 'invalid' not in (i2.get_attribute('class') or ''))

    # add item with auto attributes
    g = a.locator('section.gcard').nth(1)
    gname = g.locator('[data-gf="name"]').input_value()
    g.locator('[data-act="add-item"]').click(); a.wait_for_timeout(150)
    nm = a.locator(':focus'); nm.fill('Färse Hochrippe Testartikel, frisch'); nm.press('Tab')
    newrow = a.locator('tr.is-new').first
    newrow.locator('input[data-f="code"]').fill('19999'); newrow.locator('input[data-f="code"]').press('Tab')
    a.locator('tr:has(input[data-f="code"][value="19999"]) input[data-f="price"]').fill('12,4'); a.locator('tr:has(input[data-f="code"][value="19999"]) input[data-f="price"]').press('Tab')
    nr = row('19999')
    check('new item auto category Rind + frisch', nr.locator('select[data-f="category"]').input_value() == 'Rind' and nr.locator('select[data-f="condition"]').input_value() == 'frisch', gname)
    check('new tag', 'neu' in nr.inner_text().lower())

    # delete via dialog + undo
    row('10202').locator('[data-act="item"]').click(); a.wait_for_selector('#dlg-item[open]')
    a.screenshot(path=SH + '/admin-item.png')
    a.click('#dlg-item [data-ia="del"]'); a.wait_for_timeout(150)
    check('item deleted', row('10202').count() == 0 and 'entfernt' in a.inner_text('#changes'))
    a.click('#btn-undo'); a.wait_for_timeout(150)
    check('undo restores item', row('10202').count() == 1)
    # delete for real another one
    row('10207').locator('[data-act="item"]').click(); a.click('#dlg-item [data-ia="del"]'); a.wait_for_timeout(100)

    # alt price via dialog
    row('10601').locator('[data-act="item"]').click(); a.click('#dlg-item [data-ia="alt-add"]'); a.wait_for_timeout(100)
    a.locator('#altlist [data-alt="label"]').last.fill('Großgebinde'); a.locator('#altlist [data-alt="label"]').last.press('Tab')
    a.locator('#altlist [data-alt="price"]').last.fill('23,90'); a.locator('#altlist [data-alt="price"]').last.press('Tab'); a.wait_for_timeout(100)
    a.click('#dlg-item button[type="submit"]')
    check('alt price chip shown', 'Großgebinde: 23,90' in row('10601').inner_text())

    # add group
    a.click('#btn-add-group'); a.wait_for_timeout(150)
    f = a.locator(':focus'); f.fill('Wochenaktion'); f.press('Tab'); a.wait_for_timeout(100)
    last = a.locator('section.gcard').last
    last.locator('input[data-f="name"]').fill('Aktions-Rumpsteak, frisch'); last.locator('input[data-f="name"]').press('Tab')
    last.locator('input[data-f="price"]').fill('19,90'); last.locator('input[data-f="price"]').press('Tab')
    wait_saved()

    # search/filter in editor – auf das erwartete Ergebnis warten statt fester Wartezeit (Filter greift verzögert)
    def sichtbar(n):
        try:
            a.wait_for_function("n => document.querySelectorAll('tr[data-id]:not(.hidden-row)').length === n", arg=n, timeout=5000)
        except Exception:
            pass
        return a.locator('tr[data-id]:not(.hidden-row)').count()
    a.fill('#ed-q', 'tomahawk')
    vis = sichtbar(2); check('editor search (2× Tomahawk)', vis == 2, vis)
    a.fill('#ed-q', ''); a.check('#only-changes')
    vis = sichtbar(5); check('only changes filter (3 Preise + 2 neu)', vis == 5, vis)
    a.uncheck('#only-changes'); a.wait_for_timeout(200)

    # publish
    a.click('#btn-publish'); a.wait_for_selector('#dlg-publish[open]')
    t = a.inner_text('#dlg-publish').lower()
    check('publish summary', 'preisänderungen (3)' in t and 'neu (2)' in t and 'entfernt (1)' in t, re.sub(r'\s+', ' ', t)[:400])
    a.screenshot(path=SH + '/admin-publish.png')
    a.click('#dlg-publish [data-ia="publish"]'); a.wait_for_function("!document.querySelector('#dlg-publish').open")
    check('after publish: no changes', 'Keine Änderungen' in a.inner_text('#save-state'), a.inner_text('#save-state'))
    check('public shows new price', pub_price('10601').startswith('24,10'), pub_price('10601'))
    check('public shows alt price', '23,90' in pub_price('10601'), pub_price('10601'))
    check('public shows new item', pub_price('19999') is not None and pub_price('19999').startswith('12,40'))
    check('public shows a. Anfr.', 'auf Anfrage' in pub_price('10701'))
    check('public removed item gone', pub_price('10207') is None)
    pub.goto(B + '/?r=1#suche=rumpsteak'); pub.wait_for_selector('tr.row'); check('public new group', 'Wochenaktion' in pub.inner_text('#list'))

    # import KW44
    with a.expect_file_chooser() as fc: a.click('#btn-import')
    fc.value.set_files(XL44); a.wait_for_selector('#dlg-import [data-ia="apply"]')
    t = a.inner_text('#dlg-import'); check('import preview KW 44', 'KW 44 / 2026 erkannt' in t and 'xx' in t)
    a.screenshot(path=SH + '/admin-import.png')
    a.click('#dlg-import [data-ia="apply"]'); a.wait_for_timeout(200)
    check('import applied to draft', a.input_value('#m-week') == '44' and a.locator('tr[data-id]').count() == 276)
    pub.goto(B + '/?r=2'); pub.wait_for_selector('tr.row'); check('public KW43 still', 'KW 43' in pub.inner_text('#kw-pill'))
    wait_saved()
    a.click('#btn-publish'); a.click('#dlg-publish [data-ia="publish"]'); a.wait_for_function("!document.querySelector('#dlg-publish').open")
    pub.goto(B + '/?r=3'); pub.wait_for_selector('tr.row'); check('public KW44 after publish', 'KW 44' in pub.inner_text('#kw-pill'), pub.inner_text('#kw-pill'))

    # versions
    a.click('#btn-more'); a.click('[data-act="versions"]'); a.wait_for_selector('#dlg-versions [data-ver]')
    n = a.locator('#dlg-versions [data-ver]').count(); check('versions listed', n == 2, n)
    a.locator('#dlg-versions [data-ver]').last.click()
    try: a.wait_for_function("document.querySelector('#m-week') && document.querySelector('#m-week').value === '43'", timeout=10000)
    except Exception: pass
    check('version loaded as draft (KW43 original)', a.input_value('#m-week') == '43' and row('19999').count() == 0)
    a.click('#btn-undo'); a.wait_for_timeout(200); check('undo version load', a.input_value('#m-week') == '44')
    wait_saved()

    # discard draft
    row('10601').locator('input[data-f="price"]').fill('99'); row('10601').locator('input[data-f="price"]').press('Tab'); wait_saved()
    a.click('#btn-more'); a.click('[data-act="discard"]'); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('discard draft resets (published KW 44 price)', row('10601').locator('input[data-f="price"]').input_value() == de(excel_preis('10601')) and 'Keine Änderungen' in a.inner_text('#save-state'), (row('10601').locator('input[data-f="price"]').input_value(), a.inner_text('#save-state')))

    # security: other context without session
    other = br.new_context(); op = other.new_page()
    r = op.request.post(B + '/api/?action=save_draft', data=json.dumps({'model': {}}), headers={'Content-Type': 'application/json'})
    check('API save without login → 401', r.status == 401, r.status)
    r = op.request.post(B + '/api/?action=publish', data=json.dumps({'model': {}}), headers={'Content-Type': 'application/json'})
    check('API publish without login → 401', r.status == 401)
    r = op.request.get(B + '/data/angebot.php'); check('data file not readable', r.status == 404 and 'items' not in r.text(), r.status)
    r = op.request.get(B + '/data/nutzer.php'); check('user hashes not readable', 'hash' not in r.text() and r.status == 404, r.status)
    r = op.request.get(B + '/data/protokoll/' + time.strftime('%Y-%m') + '.php'); check('log not readable', r.status == 404 and 'login' not in r.text(), r.status)
    r = op.request.get(B + '/api/?action=offer&draft=1'); check('draft preview needs login', r.status == 401)
    other.close()

    # CSRF: logged-in cookie but no token
    r = a.request.post(B + '/api/?action=save_draft', data=json.dumps({'model': {}}), headers={'Content-Type': 'application/json'})
    check('CSRF token required', r.status == 403, r.status)

    # change password, logout, login
    a.click('#btn-more'); a.click('[data-act="password"]')
    a.fill('#pw-form [name=current]', 'Sicheres-Passwort-1'); a.fill('#pw-form [name=password]', 'Neues-Passwort-22'); a.fill('#pw-form [name=password2]', 'Neues-Passwort-22')
    a.click('#pw-form button[type=submit]')
    try: a.wait_for_function("document.querySelector('#toast').textContent.includes('Passwort geändert')", timeout=10000)
    except Exception: pass
    check('password changed', 'Passwort geändert' in a.inner_text('#toast'))
    a.click('#btn-more'); a.click('[data-act="logout"]'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', 'Sicheres-Passwort-1'); a.click('#auth-submit'); a.wait_for_function("document.querySelector('#auth-err').textContent.length > 0")
    check('old password rejected', 'nicht korrekt' in a.inner_text('#auth-err'))
    a.fill('#pw1', 'Neues-Passwort-22'); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('login with new password', True)

    # mobile admin
    m = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=2); mp = m.new_page()
    mp.goto(B + '/admin/'); mp.wait_for_selector('#screen-auth:not([hidden])'); mp.fill('#au-user', 'admin'); mp.fill('#pw1', 'Neues-Passwort-22'); mp.click('#auth-submit'); mp.wait_for_selector('tr[data-id]')
    mp.screenshot(path=SH + '/admin-mobile.png'); sw = mp.evaluate('document.documentElement.scrollWidth'); check('admin mobile no h-scroll', sw <= 390, sw)
    m.close()

    check('no JS errors', not errs, errs)
    br.close()
print(f"\n{sum(1 for r in results if r[1])}/{len(results)} passed")
sys.exit(0 if all(r[1] for r in results) else 1)
