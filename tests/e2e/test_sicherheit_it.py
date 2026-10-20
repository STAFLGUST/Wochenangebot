"""Sicherheit für IT-Administratoren: Lagebild (Verlauf, auffällige Adressen), Konfigurationsprüfung (Server und
Browser), nur lesende Diagnosen (Datenablage, E-Mail, Dateien, PHP), Export des Sicherheitsprotokolls, Rechte, Oberfläche."""
import json
import os
import sqlite3
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, shot, until, storage_sqlite, GUARD

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def put_raw(name, payload):
    """Absichtlich beschädigten Datensatz ablegen (bzw. mit None entfernen) – nur für die Diagnose-Prüfung."""
    data = os.environ['UDATA']
    if storage_sqlite():
        with sqlite3.connect(data + '/.sqlite/store.sqlite') as db:
            if payload is None: db.execute('DELETE FROM documents WHERE name=?', (name,))
            else: db.execute('INSERT OR REPLACE INTO documents(name,payload,mtime) VALUES(?,?,0)', (name, payload))
        return
    p = data + '/' + name + '.php'
    if payload is None:
        os.remove(p)
    else:
        with open(p, 'w') as f: f.write(GUARD + payload)


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('admin login', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
E = Client('198.51.100.3'); E.call('login', {'username': 'erika', 'password': 'Editor-Zugang-77'})
X = Client('203.0.113.9')
for u in ['admin', 'admin', '=HYPERLINK("x")']: X.call('login', {'username': u, 'password': 'falsch-falsch-1'})

# ---------- Lagebild und Konfiguration ----------
code, d = A.call('security_status')
check('status ok', code == 200)
check('timeline: 14 days, today counts failures', len(d['timeline']) == 14 and d['timeline'][-1]['staff'] >= 3, d['timeline'][-1])
top = {x['ip']: x for x in d['topIps']}
check('suspicious address listed with count and usernames', '203.0.113.9' in top and top['203.0.113.9']['n'] == 3 and 'admin' in top['203.0.113.9']['users'], d['topIps'][:2])
titles = {c['title']: c for c in d['config']}
for t in ['Administratoren', 'Unbenutzte Zugänge', 'Sitzungs-Cookies', 'Fehlermeldungen', 'PHP-Version', 'PHP-Erweiterungen', 'E-Mail-Verbindung', 'Alarm bei Sicherheitsereignissen', 'Länderdaten']:
    check(f'config check present: {t}', t in titles and titles[t]['level'] in ('ok', 'warn', 'bad', 'info'), titles.get(t))
check('alarm off → hint', titles['Alarm bei Sicherheitsereignissen']['level'] == 'warn')
check('new accounts are not reported as unused', titles['Unbenutzte Zugänge']['level'] == 'ok', titles['Unbenutzte Zugänge'])
A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org'}}})
titles = {c['title']: c for c in A.call('security_status')[1]['config']}
check('alarm on → ok', titles['Alarm bei Sicherheitsereignissen']['level'] == 'ok' and 'it@example.org' in titles['Alarm bei Sicherheitsereignissen']['text'])
check('editor cannot read security status', E.call('security_status')[0] == 403)
check('error messages not shown in the browser', titles['Fehlermeldungen']['level'] == 'ok', titles['Fehlermeldungen'])
check('PHP version not revealed (config)', titles['PHP-Version im Header']['level'] == 'ok', titles['PHP-Version im Header'])
import urllib.request
hdr = urllib.request.urlopen(B + '/api/?action=offer').headers
check('API responses carry no X-Powered-By', hdr.get('X-Powered-By') is None, hdr.get('X-Powered-By'))

# ---------- Diagnosen ----------
check('editor cannot run diagnostics', E.call('security_diag', {'check': 'storage'})[0] == 403)
check('diagnostics need CSRF (POST + JSON)', A.call('security_diag')[0] in (403, 405, 415))
check('unknown check rejected', A.call('security_diag', {'check': 'rm -rf'})[0] == 422)
code, r = A.call('security_diag', {'check': 'storage'})
items = {x['label']: x for x in r['result']['items']}
check('storage check ok', code == 200 and r['result']['ok'] and items['Fehlerhafte Datensätze']['value'] == 'keine', r)
if storage_sqlite():
    # Datenbank: das Schema lässt beschädigte Datensätze gar nicht zu; geprüft wird zusätzlich quick_check
    try: put_raw('kaputt-test', '{kaputt'); blocked = False
    except sqlite3.IntegrityError: blocked = True
    check('database refuses broken records', blocked)
    check('database quick_check reported', items.get('Datenbank-Prüfung (quick_check)', {}).get('value') == 'ok')
else:
    put_raw('kaputt-test', '{kaputt')
    r = A.call('security_diag', {'check': 'storage'})[1]['result']
    items = {x['label']: x for x in r['items']}
    check('broken record detected', r['ok'] is False and 'kaputt-test' in items['Fehlerhafte Datensätze']['value'], items.get('Fehlerhafte Datensätze'))
    put_raw('kaputt-test', None)
    check('after cleanup ok again', A.call('security_diag', {'check': 'storage'})[1]['result']['ok'])
n0 = len(smtp.messages)
r = A.call('security_diag', {'check': 'mail'})[1]['result']
check('mail check: connection and login ok, no mail sent', r['ok'] and any('erfolgreich' in x['value'] for x in r['items']) and len(smtp.messages) == n0, r)
check('mail check used real login', until(lambda: len(smtp.logins) >= 1, 3))
r = A.call('security_diag', {'check': 'files'})[1]['result']
check('files check', r['ok'] and any(x['label'] == 'Datenordner beschreibbar' and x['value'] == 'ja' for x in r['items']), r)
r = A.call('security_diag', {'check': 'php'})[1]['result']
check('php check lists version and server time', any(x['label'] == 'PHP' for x in r['items']) and any(x['label'] == 'Serverzeit UTC' for x in r['items']))
check('diagnostics change nothing (no log entry)', 'security_diag' not in json.dumps(A.call('log')[1]))

# ---------- Export ----------
check('editor cannot export', E.call('security_export', {'days': 90})[0] == 403)
check('invalid period rejected', A.call('security_export', {'days': 3})[0] == 422)
code, r = A.call('security_export', {'days': 30})
lines = r.get('csv', '').splitlines()
check('export: BOM, header, rows', code == 200 and lines[0].startswith('﻿Zeit (UTC);Vorgang') and r['count'] >= 3 and r['filename'].endswith('_30T.csv'), (code, lines[:1]))
check('export contains failed logins with IP', any('login_fail' in l and '203.0.113.9' in l for l in lines))
check('export neutralises formulas', not any(';"=hyperlink' in l.lower() for l in lines) and any("\"'=hyperlink" in l.lower() for l in lines), [l for l in lines if 'hyperlink' in l.lower()][:2])
check('export contains no password hashes', '$2y$' not in r['csv'] and 'hash' not in r['csv'].lower())
check('export is logged', 'Sicherheitsprotokoll exportiert' in json.dumps(A.call('log')[1], ensure_ascii=False))

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []
    ctx = br.new_context(viewport={'width': 1440, 'height': 950}, accept_downloads=True)
    a = ctx.new_page(); a.on('pageerror', lambda e: errs.append(str(e)))
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden])')
    a.click('#vt-sec'); a.wait_for_selector('#sec-lage .sec-grid')
    check('section navigation', a.eval_on_selector_all('.sec-nav a', 'e => e.map(x => x.getAttribute("href"))') == ['#sec-lage', '#sec-konfig', '#sec-diag', '#sec-einst', '#sec-bst', '#sec-zugang'])
    check('overall status shown', a.locator('#sec-score strong').count() == 1 and 'in Ordnung' in a.inner_text('#sec-score'))
    check('timeline chart with 14 days', a.locator('svg.tl g').count() == 14)
    check('suspicious address in table', '203.0.113.9' in a.inner_text('#sec-lage'))
    a.wait_for_selector('#sec-bchecks tr.cf-ok, #sec-bchecks tr.cf-warn, #sec-bchecks tr.cf-bad')
    bt = a.inner_text('#sec-bchecks')
    check('browser checks: data folder and program files locked', 'Datenordner von außen gesperrt' in bt and 'Programmdateien von außen gesperrt' in bt and bt.count('gesperrt (Status') == 2, bt)
    check('browser checks: headers and clock', 'Content-Security-Policy' in bt or 'CSP' in bt)
    check('browser check: server software hidden', 'Server-Software verborgen' in bt and 'keine Versionsangabe' in bt, bt)
    check('config table lists server checks', a.locator('#sec-konfig tbody tr').count() >= 12)
    a.click('.sec-nav a[href="#sec-diag"]')
    a.click('#sec-diag [data-diag=storage]'); a.wait_for_selector('#dg-out .dg-res[data-res=storage]')
    check('UI diagnostic result', 'Fehlerhafte Datensätze' in a.inner_text('#dg-out') and a.locator('#dg-out .dg-res.ok').count() == 1)
    a.click('#sec-diag [data-diag=php]'); a.wait_for_selector('#dg-out .dg-res[data-res=php]')
    check('newest result on top', a.locator('#dg-out .dg-res').first.get_attribute('data-res') == 'php')
    with a.expect_download() as dl: a.click('#sec-diag [data-diag=export]')
    check('UI export downloads CSV', dl.value.suggested_filename.startswith('Sicherheitsprotokoll_') and dl.value.suggested_filename.endswith('.csv'))
    check('existing settings still on the page', a.locator('#sec-form').count() == 1 and a.locator('#wartung-form').count() == 1)
    shot(a.locator('#sec-lage'), SH + '/sicherheit-lage.png')
    shot(a.locator('#sec-konfig'), SH + '/sicherheit-konfig.png')
    shot(a.locator('#sec-diag'), SH + '/sicherheit-diagnose.png')
    a.set_viewport_size({'width': 390, 'height': 844})
    check('mobile: no horizontal page scroll', a.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    a.screenshot(path=SH + '/sicherheit-mobil.png')
    check('no page errors', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
