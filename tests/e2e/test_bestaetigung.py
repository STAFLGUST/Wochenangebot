"""Sicherheit → Passwortbestätigung: je Aktion einstellbar, ob das Passwort verlangt wird; feste Aktionen (Zugänge, Rechte,
Sicherheit, Postfach) immer mit Bestätigung; Gültigkeitsdauer 5/15/30/60 Minuten; Prüfungen, Protokoll, Rechte bleiben
erhalten, ältere Oberfläche ohne Feld ändert nichts. Oberfläche: Karte mit Häkchen, Schloss, Rückfrage beim Abschalten, 390 px."""
import json
import os
import re
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

from auth_helpers import Client, PW
from umgebung import BASE, REPO, SH, storage_raw, until

res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def bestaetigt_vor(cl, sekunden):
    """Passwortbestätigung dieser Sitzung auf „vor <sekunden> Sekunden“ setzen (simulierter Zeitablauf)."""
    sid = next(c.value for c in cl.cookies if c.name == 'WA_ADMIN')
    subprocess.run(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-r',
                    'session_id($argv[1]); session_start(); $_SESSION["adminConfirmedAt"] = time() - (int)$argv[2]; session_write_close();', sid, str(sekunden)], check=True)


def sec_doc():
    raw = storage_raw('sicherheit') or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw) or {}


a = Client()
assert a.login()[0] == 200
st, r = a.call('security_status')
kat = {b['key']: b for b in r.get('bestaetigung', [])}
FEST = ['user_save', 'user_delete', 'user_unlock', 'rechte_save', 'session_end', 'ip_unblock', 'security_save', 'security_export', 'mail_konto_save']
check('Katalog in der Sicherheitsübersicht, standardmäßig überall Pflicht', st == 200 and kat and all(b['noetig'] for b in kat.values()) and r['bestaetigungMinuten'] == [5, 15, 30, 60]
      and r['settings'].get('bestaetigungMinuten') == 5, len(kat))
check('Zugänge, Rechte, Sicherheit und Postfach fest', all(kat.get(k, {}).get('fest') for k in FEST) and not kat['kunde_save']['fest'] and not kat['einzel_senden']['fest'])

# Jede Aktion mit Passwortbestätigung im Code steht im Katalog (sonst wäre sie nicht einstellbar und nicht sichtbar)
code = ''
for d in ('app/api/aktionen', 'app/api/lib'):
    for f in os.listdir(os.path.join(REPO, d)):
        if f.endswith('.php'):
            code += open(os.path.join(REPO, d, f), encoding='utf-8').read()
benutzt = set(re.findall(r"require_admin_confirmation\('([a-z_]+)'\)", code)) | set(re.findall(r"require_perm_confirmed\('[a-z._]+', '([a-z_]+)'\)", code))
ohne = re.findall(r"require_admin_confirmation\(\)|require_perm_confirmed\('[a-z._]+'\)", code)
check('jede Bestätigungsstelle im Code hat einen Katalogschlüssel', benutzt and benutzt <= set(kat) and not ohne, (benutzt - set(kat), ohne))
check('jeder Katalogschlüssel wird im Code verwendet', set(kat) <= benutzt, set(kat) - benutzt)

# ---------- Prüfungen ----------
S = r['settings']
basis = {k: S[k] for k in ('twofa', 'pwMin', 'pwComplex', 'idleMinutes', 'ipEnabled', 'adminIps', 'lockAfter', 'lockMinutes', 'geoEnabled', 'geoMode', 'geoCountries', 'geoScope')}
a.expire()
check('Einstellung ändern verlangt selbst die Bestätigung', (lambda x: x[0] == 403 and x[1].get('code') == 'confirmation_required')(a.call('security_save', {**basis, 'bestaetigungAus': ['kunde_save']})))
assert a.call('reauth', {'password': PW})[0] == 200
st, r = a.call('security_save', {**basis, 'bestaetigungAus': ['user_save']})
check('feste Aktion lässt sich nicht abschalten', st == 422 and 'immer' in r.get('error', ''), r)
check('unbekannte Aktion abgewiesen', a.call('security_save', {**basis, 'bestaetigungAus': ['gibt_es_nicht']})[0] == 422)
check('ungültige Gültigkeitsdauer abgewiesen', a.call('security_save', {**basis, 'bestaetigungMinuten': 7})[0] == 422)
check('nach Ablehnungen nichts gespeichert', not sec_doc().get('bestaetigungAus'))

# ---------- Abschalten ----------
st, r = a.call('security_save', {**basis, 'bestaetigungAus': ['geo_clear_stats', 'mail_save', 'kunde_save', 'kunde_save'], 'bestaetigungMinuten': 15})
check('abschaltbare Aktionen gespeichert (ohne Doppelte, Katalogreihenfolge), Dauer 15 Min.', st == 200 and r['settings']['bestaetigungAus'] == ['kunde_save', 'mail_save', 'geo_clear_stats']
      and r['settings']['bestaetigungMinuten'] == 15, r.get('settings', {}).get('bestaetigungAus'))
log = json.dumps(a.call('log')[1], ensure_ascii=False)
check('Protokoll: je Aktion „verlangt → nicht verlangt“ und Dauer', 'Passwortbestätigung: Kunde anlegen oder ändern' in log and 'nicht verlangt' in log and 'Passwortbestätigung gilt (Min.)' in log)
kat2 = {b['key']: b for b in a.call('security_status')[1]['bestaetigung']}
check('Übersicht zeigt den neuen Stand', not kat2['kunde_save']['noetig'] and not kat2['mail_save']['noetig'] and kat2['kunde_delete']['noetig'] and kat2['user_save']['noetig'])

bestaetigt_vor(a, 3600)   # länger her als die eingestellten 15 Minuten
check('abgeschaltet: ohne Bestätigung möglich (Administrator)', a.call('geo_clear_stats', {})[0] == 200)
check('abgeschaltet: Signatur ohne Bestätigung', a.call('mail_save', {'signature': 'Viele Grüße\nTest'})[0] == 200)
for act in ('user_save', 'security_save', 'rechte_save', 'mail_konto_save', 'kunde_delete', 'wartung_save'):
    st, r = a.call(act, {})
    check(f'weiterhin Pflicht: {act}', st == 403 and r.get('code') == 'confirmation_required', (st, r.get('code')))

# Rechte bleiben: ohne Bestätigung genügt das Recht, nicht weniger
assert a.call('reauth', {'password': PW})[0] == 200
assert a.call('user_save', {'username': 'lea', 'name': 'Lea Leser', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})[0] == 200
assert a.call('user_save', {'username': 'eddi', 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})[0] == 200
uid = {u['username']: u['id'] for u in a.call('users')[1]['users']}
assert a.call('user_save', {'id': uid['eddi'], 'name': 'Eddi Editor', 'role': 'editor', 'active': True, 'grant': ['kunden.sehen', 'kunden.bearbeiten'], 'deny': []})[0] == 200
L = Client('192.0.2.21'); assert L.login('lea', 'Leserin-Zugang-1')[0] == 200
E = Client('192.0.2.22'); assert E.login('eddi', 'Editor-Zugang-77')[0] == 200
bestaetigt_vor(E, 3600); bestaetigt_vor(L, 3600)
rev = E.call('kunden')[1]['rev']
st, r = E.call('kunde_save', {'rev': rev, 'firma': 'Ohne Rückfrage GmbH', 'active': True, 'angebote': ['std']})
check('Bearbeiter mit Kundenrecht: Kunde anlegen ohne Passwort', st == 200, r)
check('Leser ohne Kundenrecht bleibt gesperrt (403, keine Bestätigung angeboten)', (lambda x: x[0] == 403 and x[1].get('code') != 'confirmation_required')(L.call('kunde_save', {'rev': rev, 'firma': 'X'})))
check('Leser: keine Verwaltungsaktion ohne Administratorrolle', L.call('geo_clear_stats', {})[0] == 403)
check('ohne Anmeldung gesperrt', Client('192.0.2.23').call('geo_clear_stats', {})[0] == 401)

# Gültigkeitsdauer 15 Minuten
bestaetigt_vor(a, 600)
check('Bestätigung vor 10 Min. gilt bei 15 Min.', a.call('user_unlock', {'id': uid['lea']})[0] == 200)
bestaetigt_vor(a, 15 * 60 + 5)
check('Bestätigung vor 15 Min. abgelaufen', a.call('user_unlock', {'id': uid['lea']})[0] == 403)
assert a.call('reauth', {'password': PW})[0] == 200
st, r = a.call('reauth', {'password': PW})
check('Bestätigung meldet die eingestellte Dauer', st == 200 and 15 * 60 - 5 <= r['confirmedUntil'] - int(time.time()) <= 15 * 60 + 5, r)

# Ältere Oberfläche (ohne Feld) ändert die Liste nicht
st, r = a.call('security_save', {**basis, 'idleMinutes': 240})
check('Speichern ohne Feld behält die Passwortbestätigung', st == 200 and r['settings']['bestaetigungAus'] == ['kunde_save', 'mail_save', 'geo_clear_stats'] and r['settings']['bestaetigungMinuten'] == 15)

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={'width': 1440, 'height': 950})
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
    pg.click('#vt-sec'); pg.wait_for_selector('#bst-form')
    f = '#bst-form'
    check('Karte „Passwortbestätigung“ mit Abschnittslink', pg.locator('.sec-nav a[href="#sec-bst"]').count() == 1 and 'Passwortbestätigung' in pg.inner_text(f + ' h3'))
    check('Stand: abgeschaltete ohne Haken, andere mit Haken, Dauer 15 Min.', not pg.is_checked(f + ' input[value="kunde_save"]') and pg.is_checked(f + ' input[value="kunde_delete"]')
          and pg.input_value(f + ' select[name="bestaetigungMinuten"]') == '15' and '3 Aktionen ohne Bestätigung' in pg.inner_text(f))
    fest = pg.locator(f + ' .bst-z.fest')
    check('feste Aktionen mit Schloss, angehakt und gesperrt', fest.count() == len(FEST) and all(fest.nth(i).locator('input').is_disabled() and fest.nth(i).locator('input').is_checked() for i in range(fest.count()))
          and 'Sicherheitseinstellungen ändern' in pg.inner_text(f + ' .bst-g.fest'))
    check('Hinweis oben nennt die eingestellte Dauer', 'höchstens 15 Minuten' in pg.inner_text('#view-sec'))
    pg.locator(f).scroll_into_view_if_needed()
    pg.uncheck(f + ' input[value="einzel_senden"]'); pg.check(f + ' input[value="kunde_save"]')
    pg.select_option(f + ' select[name="bestaetigungMinuten"]', '30')
    pg.evaluate("document.querySelector('#bst-form').dataset.alt = '1'")   # nach dem Speichern wird die Karte neu aufgebaut
    pg.click(f + ' button[type="submit"]')
    pg.wait_for_selector('#dlg-confirm[open]')
    check('Abschalten fragt nach und nennt die Aktion', 'Einzelangebot per E-Mail senden' in pg.inner_text('#dlg-confirm'))
    pg.click('#dlg-confirm .btn.primary')
    pg.wait_for_function("() => document.querySelector('#dlg-pw[open], #dlg-reauth[open], dialog[open] input[type=password]') || (document.querySelector('#bst-form input[value=\"einzel_senden\"]') && !document.querySelector('#bst-form input[value=\"einzel_senden\"]').checked && document.querySelector('#bst-form select').value === '30' && !document.querySelector('#dlg-confirm[open]'))")
    if pg.locator('dialog[open] input[type=password]').count():   # Passwortbestätigung abgelaufen → Dialog
        pg.fill('dialog[open] input[type=password]', PW); pg.keyboard.press('Enter')
    pg.wait_for_selector('text=Passwortbestätigung gespeichert.')   # Server hat gespeichert, die Ansicht wird neu geladen
    until(lambda: sec_doc().get('bestaetigungMinuten') == 30)
    pg.wait_for_selector('#bst-form:not([data-alt])')
    pg.wait_for_function("() => { const s = document.querySelector('#bst-form select'); return s && s.value === '30' && document.querySelector('#bst-form input[value=\"kunde_save\"]').checked; }")
    d = sec_doc()
    check('gespeichert: Einzelangebot-Mail ohne, Kunde mit Bestätigung, 30 Min.', d.get('bestaetigungAus') == ['einzel_senden', 'mail_save', 'geo_clear_stats'] and d.get('bestaetigungMinuten') == 30, d.get('bestaetigungAus'))
    pg.locator(f).screenshot(path=SH + '/sicherheit-bestaetigung.png')
    pg.set_viewport_size({'width': 390, 'height': 820}); pg.emulate_media(color_scheme='dark')
    pg.locator(f).scroll_into_view_if_needed()
    over = pg.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Mobil 390 px: kein seitliches Scrollen', over <= 1, over)
    pg.locator(f).screenshot(path=SH + '/sicherheit-bestaetigung-mobil.png')
    br.close()
check('keine JavaScript-Fehler', not errors, errors[:3])

# Zurück auf Standard: überall Pflicht
assert a.call('reauth', {'password': PW})[0] == 200
check('zurück auf „überall Pflicht“', a.call('security_save', {**basis, 'bestaetigungAus': [], 'bestaetigungMinuten': 5})[0] == 200)
a.expire()
check('danach wieder Bestätigung verlangt', a.call('geo_clear_stats', {})[0] == 403 and E.call('kunde_save', {'rev': 0, 'firma': 'Y'})[1].get('code') == 'confirmation_required')

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
