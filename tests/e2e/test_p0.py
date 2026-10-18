import sys
from umgebung import BASE, AUX_PORT  # Testserver je Gruppe (parallel)
import os, re, subprocess, time, json, shutil, glob
from playwright.sync_api import sync_playwright
from umgebung import SH, FIX, REPO, WORK
S = WORK
B = BASE; DATA = os.environ['UDATA']; res = []
GUARD = "<?php http_response_code(404); exit; ?>\n"
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))
def srv(port, data, env=None):
    subprocess.run(f"pkill -f 'php -S 127.0.0.1:{port}$'", shell=True)
    app = S + f'/p0_{port}'; shutil.rmtree(app, ignore_errors=True); shutil.copytree(REPO + '/app', app)
    shutil.rmtree(app + '/data'); shutil.copytree(data, app + '/data') if data else os.makedirs(app + '/data')
    subprocess.Popen(['php', '-S', f'127.0.0.1:{port}'], cwd=app, env={**os.environ, **(env or {})}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(0.7); return app
with sync_playwright() as p:
    br = p.chromium.launch(); errs = []
    def st(url):
        pg = br.new_page(); pg.goto(url + '/admin/'); pg.wait_for_timeout(500)
        j = pg.evaluate("async () => (await fetch('/api/?action=status')).json()")
        r = pg.evaluate("async () => { const r = await fetch('/api/?action=setup', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:'boss', password:'Uebernahme-Versuch-1'})}); return [r.status, await r.json()]; }")
        return pg, j, r
    # 1) leeres System ohne WA_INSTALLED → Ersteinrichtung erlaubt
    srv(AUX_PORT, None)
    pg, j, r = st(f'http://127.0.0.1:{AUX_PORT}')
    check('empty system: setup allowed', j['setupRequired'] and not j['setupLocked'] and r[0] == 200, (j, r[0]))
    # 2) leeres System mit WA_INSTALLED=1 → gesperrt
    srv(AUX_PORT, None, {'WA_INSTALLED': '1'})
    pg, j, r = st(f'http://127.0.0.1:{AUX_PORT}')
    check('WA_INSTALLED: setup locked', not j['setupRequired'] and j['setupLocked'] and r[0] == 403, (j, r))
    check('WA_INSTALLED: UI shows locked message, no setup form', 'gesperrt' in pg.inner_text('body') and pg.locator('#pw2-wrap:visible').count() == 0, pg.inner_text('body')[:200])
    # 3) kaputte Nutzerdatei → gesperrt (kein Übernehmen möglich)
    app = srv(AUX_PORT, FIX + '/data-seed')
    open(app + '/data/nutzer.php', 'w').write(GUARD + '{kaputt')
    pg, j, r = st(f'http://127.0.0.1:{AUX_PORT}')
    check('corrupt users file: setup locked', j['setupLocked'] and r[0] == 403 and not os.path.getsize(app + '/data/nutzer.php') > 100, (j, r[0]))
    lr = pg.evaluate("async () => { const r = await fetch('/api/?action=login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:'admin', password:'x'})}); return [r.status, await r.json()]; }")
    check('corrupt users file: login explains', lr[0] == 409 and 'Server' in lr[1]['error'], lr)
    subprocess.run(f"pkill -f 'php -S 127.0.0.1:{AUX_PORT}$'", shell=True)
    # 4) CSV-Formel-Injection über Benutzername im Protokoll
    a = br.new_page(viewport={'width': 1440, 'height': 950}, accept_downloads=True); a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', '=cmd|x!a0'); a.fill('#pw1', 'falsch-falsch'); a.click('#auth-submit'); a.wait_for_timeout(500)
    a.fill('#au-user', 'admin'); a.fill('#pw1', 'Sicheres-Passwort-1'); a.click('#auth-submit'); a.wait_for_selector('tr[data-id]')
    a.click('#vt-log'); a.wait_for_selector('.ltab')
    with a.expect_download() as dl: a.click('#log-csv')
    txt = open(dl.value.path(), encoding='utf-8-sig').read()
    cells = [c for line in txt.splitlines() for c in line.split(';')]
    check('log CSV: formula neutralized', any(c.startswith("'=cmd") for c in cells) and not any(c.startswith('=') for c in cells), [c for c in cells if 'cmd' in c][:3])
    # 5) Sicherungs-Status im Bereich Sicherheit
    a.click('#vt-sec'); a.wait_for_selector('.sec-grid')
    check('backup card: none yet', 'noch keine automatische Sicherung' in a.inner_text('.sec-grid'))
    t = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    open(DATA + '/sicherung.php', 'w').write(GUARD + json.dumps({'t': t, 'ok': True, 'datei': 'daten-x.tar.gz', 'groesse': 2400000, 'dateien': 40, 'fehler': 0, 'anzahl': 12, 'behalten': 30}))
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_timeout(600)
    g = a.inner_text('.sec-grid'); check('backup card: ok', 'geprüft' in g and '12 Stände' in g, g)
    open(DATA + '/sicherung.php', 'w').write(GUARD + json.dumps({'t': t, 'ok': False, 'datei': '', 'groesse': 0, 'dateien': 0, 'fehler': 1, 'anzahl': 12, 'behalten': 30}))
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_timeout(600)
    check('backup card: failure shown red', a.locator('.sec-card.bad:has-text("Datensicherung")').count() == 1)
    # 6) Bereitstellungs-Status (Release-Modus)
    check('deploy card: not yet set up', a.locator('.sec-card.warn:has-text("Bereitstellung")').count() == 1 and 'ohne Freigabe' in a.inner_text('.sec-grid'))
    open(DATA + '/deployment.php', 'w').write(GUARD + json.dumps({'t': t, 'ok': True, 'sha': 'abcdef1234567890abcdef1234567890abcdef12', 'vorher': '', 'lauf': '1', 'meldung': ''}))
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_timeout(600)
    check('deploy card: release ok', a.locator('.sec-card.ok:has-text("Release abcdef1")').count() == 1)
    open(DATA + '/deployment.php', 'w').write(GUARD + json.dumps({'t': t, 'ok': False, 'sha': '1234567890abcdef1234567890abcdef12345678', 'vorher': '', 'lauf': '2', 'meldung': 'Release fehlerhaft – automatisch auf Vorversion zurückgesetzt'}))
    a.click('#vt-edit'); a.click('#vt-sec'); a.wait_for_timeout(600)
    check('deploy card: rollback shown red', a.locator('.sec-card.bad:has-text("Vorversion")').count() == 1)
    a.screenshot(path=SH + '/p0-sec.png')
    check('no JS errors', not errs, errs)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
