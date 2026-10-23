"""Verwaltung → Nutzer anlegen: Vorname, Nachname, E-Mail; Benutzername automatisch aus Vorname-Nachname (Umlaute,
Akzente, belegt → -2); ältere Oberfläche mit „name“ und einwortige Altnamen bleiben möglich; Zugangsdaten per E-Mail an den
Mitarbeiter (optional mit Startpasswort, nur wenn es geändert werden muss und zum gespeicherten Passwort passt; Rechte,
Passwortbestätigung, Protokoll, Versandprotokoll). Oberfläche: Dialog schließt weder per Klick daneben noch per Escape,
automatischer Benutzername, Abschluss-Schritt mit Mail-Knopf, 390 px. Nur Test-Mailserver, keine echten E-Mails."""
import json
import sys

from playwright.sync_api import sync_playwright

from auth_helpers import Client, PW
from smtp_test import TestSmtp
from umgebung import BASE, SH, SMTP_PORT, storage_raw, until

res = []


def check(n, c, i=''):
    res.append(bool(c))
    print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def doc(name):
    raw = storage_raw(name) or 'null'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client()
assert A.login()[0] == 200

# ---------- Anlegen mit Vorname/Nachname/E-Mail, Benutzername automatisch ----------
NEU = {'role': 'editor', 'active': True, 'password': 'Start-Kennwort-4711', 'mustChange': True}
st, r = A.call('user_save', {**NEU, 'vorname': 'Max', 'nachname': 'Mustermann', 'email': 'Max.Mustermann@Example.org', 'username': ''})
mx = r.get('user', {})
check('ohne Benutzernamen: automatisch „vorname-nachname“', st == 200 and mx.get('username') == 'max-mustermann' and mx.get('name') == 'Max Mustermann'
      and mx.get('vorname') == 'Max' and mx.get('nachname') == 'Mustermann' and mx.get('email') == 'max.mustermann@example.org', r)
st, r = A.call('user_save', {**NEU, 'vorname': 'Max', 'nachname': 'Mustermann', 'username': ''})
check('gleicher Name: „-2“ angehängt', st == 200 and r['user']['username'] == 'max-mustermann-2', r)
st, r = A.call('user_save', {**NEU, 'vorname': 'Jörg', 'nachname': 'Weiß-Müller', 'username': ''})
check('Umlaute und ß: „joerg-weiss-mueller“', st == 200 and r['user']['username'] == 'joerg-weiss-mueller', r)
st, r = A.call('user_save', {**NEU, 'vorname': 'José Luis', 'nachname': 'Núñez', 'username': ''})
check('Akzente und Leerzeichen: „jose-luis-nunez“', st == 200 and r['user']['username'] == 'jose-luis-nunez', r)
st, r = A.call('user_save', {**NEU, 'vorname': 'Eva', 'nachname': 'Test', 'username': 'eva.t'})
check('eigener Benutzername bleibt möglich', st == 200 and r['user']['username'] == 'eva.t', r)
check('neu: Nachname fehlt → 422', A.call('user_save', {**NEU, 'vorname': 'Nur', 'nachname': '', 'username': ''})[0] == 422)
check('ungültige E-Mail → 422', A.call('user_save', {**NEU, 'vorname': 'Ina', 'nachname': 'Fehler', 'email': 'keine-adresse', 'username': ''})[0] == 422)
check('E-Mail mit Zeilenumbruch → 422', A.call('user_save', {**NEU, 'vorname': 'Ina', 'nachname': 'Fehler', 'email': 'a@b.de\nBcc: x@y.de', 'username': ''})[0] == 422)
st, r = A.call('user_save', {**NEU, 'name': 'Alt Oberflaeche', 'username': 'alt'})
check('ältere Oberfläche (nur „name“) funktioniert weiter', st == 200 and r['user']['name'] == 'Alt Oberflaeche' and r['user']['vorname'] == '' and r['user']['email'] == '', r)
uid = {u['username']: u for u in A.call('users')[1]['users']}

# ---------- Ändern ----------
st, r = A.call('user_save', {'id': uid['alt']['id'], 'vorname': 'Solo', 'nachname': '', 'role': 'editor', 'active': True, 'email': 'solo@example.org'})
check('bestehender Zugang mit einwortigem Namen bleibt speicherbar', st == 200 and r['user']['name'] == 'Solo' and r['user']['email'] == 'solo@example.org', r)
st, r = A.call('user_save', {'id': mx['id'], 'vorname': 'Max', 'nachname': 'Mustermann', 'role': 'editor', 'active': True, 'email': 'max@example.org'})
check('E-Mail geändert, Benutzername bleibt', st == 200 and r['user']['email'] == 'max@example.org' and r['user']['username'] == 'max-mustermann', r)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: E-Mail beim Anlegen und Ändern', 'max.mustermann@example.org' in log and 'max@example.org' in log)
st, r = A.call('user_save', {'id': uid['eva.t']['id'], 'name': 'Eva Test', 'role': 'editor', 'active': True})
check('ältere Oberfläche ohne E-Mail-Feld lässt E-Mail und Namensteile unverändert', st == 200 and r['user']['vorname'] == 'Eva' and r['user']['nachname'] == 'Test', r)

# ---------- Zugangsdaten per E-Mail ----------
assert A.call('user_save', {**NEU, 'vorname': 'Erik', 'nachname': 'Editor', 'username': '', 'email': 'erik@example.org', 'mustChange': False, 'password': 'Erik-Kennwort-123'})[0] == 200
E = Client('192.0.2.30'); assert E.login('erik-editor', 'Erik-Kennwort-123')[0] == 200
check('Bearbeiter darf keine Zugangsdaten senden', E.call('user_mail', {'id': mx['id']})[0] == 403)
check('ohne Anmeldung gesperrt', Client('192.0.2.31').call('user_mail', {'id': mx['id']})[0] == 401)
check('nur per POST', A.call('user_mail')[0] == 405)
A.expire()
check('verlangt die Passwortbestätigung (fest)', (lambda x: x[0] == 403 and x[1].get('code') == 'confirmation_required')(A.call('user_mail', {'id': mx['id']})))
kat = {b['key']: b for b in A.call('security_status')[1].get('bestaetigung', [])}
check('im Katalog „Immer mit Bestätigung“', kat.get('user_mail', {}).get('fest') is True)
assert A.call('reauth', {'password': PW})[0] == 200
check('unbekannter Nutzer → 404', A.call('user_mail', {'id': 'u000000000000'})[0] == 404)
check('ohne E-Mail-Adresse → 422', A.call('user_mail', {'id': uid['max-mustermann-2']['id']})[0] == 422)
check('falsches Startpasswort → 422', A.call('user_mail', {'id': mx['id'], 'password': 'Falsches-Kennwort-1'})[0] == 422)
erik = next(u for u in A.call('users')[1]['users'] if u['username'] == 'erik-editor')
check('Passwort nur, wenn es geändert werden muss → 422', A.call('user_mail', {'id': erik['id'], 'password': 'Erik-Kennwort-123'})[0] == 422)
n0 = len(smtp.messages)
st, r = A.call('user_mail', {'id': mx['id'], 'password': 'Start-Kennwort-4711'})
check('gesendet mit Startpasswort, Vermerk am Nutzer', st == 200 and r['user']['mailInfo']['to'] == 'max@example.org' and r['user']['mailInfo']['mitPasswort'] is True and r['user']['mailInfo']['ok'], r)
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
body = (m.get('text') or '') + (m.get('html') or '')
check('E-Mail: an den Mitarbeiter, Gruß mit Vorname, Benutzername, Startpasswort, Link, Hinweis', m and m.get('to') == ['max@example.org'] and 'Eingabebereich' in m.get('subject', '')
      and 'Hallo Max,' in body and 'max-mustermann' in body and 'Start-Kennwort-4711' in body and '/admin/' in body and 'eigenes Passwort' in body, (m.get('subject'), (m.get('text') or '')[:400]))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll ohne Passwort', 'mit Startpasswort per E-Mail versendet' in log and 'Start-Kennwort-4711' not in log)
check('Versandprotokoll: Typ „zugang“', any(e.get('typ') == 'zugang' and e.get('to') == 'max@example.org' for e in doc('mailversand') or []))
check('Startpasswort nirgends gespeichert', 'Start-Kennwort-4711' not in (storage_raw('nutzer') or '') and 'Start-Kennwort-4711' not in (storage_raw('mailversand') or ''))
n0 = len(smtp.messages)
st, r = A.call('user_mail', {'id': erik['id']})
until(lambda: len(smtp.messages) > n0)
m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
check('ohne Passwort: Hinweis „separat“, kein Passwort in der E-Mail', st == 200 and r['user']['mailInfo']['mitPasswort'] is False and 'separat' in (m.get('text') or '') and 'Erik-Kennwort-123' not in (m.get('text') or ''))
A.call('user_save', {'id': erik['id'], 'vorname': 'Erik', 'nachname': 'Editor', 'role': 'editor', 'active': False, 'email': 'erik@example.org'})
check('deaktivierter Zugang → 422', A.call('user_mail', {'id': erik['id']})[0] == 422)

# ---------- Oberfläche ----------
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1440, 'height': 950})
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append(str(e)))
    a.goto(BASE + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', PW); a.click('#auth-submit'); a.wait_for_selector('#screen-editor:not([hidden])')
    a.click('#vt-users'); a.wait_for_selector('.utab')
    check('Liste zeigt die E-Mail', 'max@example.org' in a.inner_text('.utab tr:has-text("max-mustermann")'))
    a.click('#user-add'); a.wait_for_selector('#dlg-user[open] [name=vorname]')
    check('Felder Vorname, Nachname, E-Mail, Benutzername; Fokus auf Vorname', all(a.locator(f'#user-body [name={n}]').count() == 1 for n in ('vorname', 'nachname', 'email', 'username'))
          and a.locator('#user-body [name=name]').count() == 0 and a.evaluate('document.activeElement.name') == 'vorname')
    a.fill('#user-body [name=vorname]', 'Jörg'); a.fill('#user-body [name=nachname]', 'Weiß-Müller')
    check('Benutzername wird beim Tippen gebildet, belegt → „-2“', a.input_value('#user-body [name=username]') == 'joerg-weiss-mueller-2', a.input_value('#user-body [name=username]'))
    a.fill('#user-body [name=nachname]', 'Neu')
    check('Benutzername folgt dem Namen', a.input_value('#user-body [name=username]') == 'joerg-neu')
    a.mouse.click(30, 30)
    check('Klick daneben schließt den Dialog nicht, Eingaben bleiben', a.evaluate("document.querySelector('#dlg-user').open") and a.input_value('#user-body [name=vorname]') == 'Jörg')
    a.keyboard.press('Escape')
    check('Escape schließt den Dialog nicht', a.evaluate("document.querySelector('#dlg-user').open") and a.input_value('#user-body [name=nachname]') == 'Neu')
    a.fill('#user-body [name=username]', 'jn')
    a.fill('#user-body [name=nachname]', 'Neumann')
    check('selbst eingetragener Benutzername wird nicht überschrieben', a.input_value('#user-body [name=username]') == 'jn')
    a.fill('#user-body [name=username]', '')
    a.fill('#user-body [name=vorname]', 'Lena'); a.fill('#user-body [name=nachname]', 'Lager')
    check('nach Leeren wieder automatisch', a.input_value('#user-body [name=username]') == 'lena-lager')
    a.fill('#user-body [name=email]', 'lena.lager@example.org')
    a.click('#user-body [data-uact="gen"]'); pw = a.input_value('#user-body [name=password]')
    a.screenshot(path=SH + '/nutzer-anlegen.png')
    a.click('#user-body [type=submit]'); a.wait_for_selector('#user-body .us-fertig')
    t = a.inner_text('#user-body')
    check('Abschluss: Mitarbeiter angelegt mit Benutzername, Startpasswort, E-Mail, Mail-Knopf', 'Mitarbeiter angelegt' in t and 'lena-lager' in t and pw in t and 'lena.lager@example.org' in t
          and a.locator('#user-body [data-uact="sendmail"]').is_visible() and a.is_checked('#us-mitpw'), t[:300])
    check('Liste schon aktualisiert', a.locator('.utab tr:has-text("lena-lager")').count() == 1)
    a.mouse.click(30, 30)
    check('Abschluss bleibt bei Klick daneben offen', a.evaluate("document.querySelector('#dlg-user').open"))
    a.screenshot(path=SH + '/nutzer-angelegt.png')
    n0 = len(smtp.messages)
    a.click('#user-body [data-uact="sendmail"]')
    a.wait_for_function("document.querySelector('#us-mail-st') && document.querySelector('#us-mail-st').textContent.includes('gesendet')")
    until(lambda: len(smtp.messages) > n0)
    m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
    if m:   # die E-Mail so ansehen, wie sie beim Mitarbeiter ankommt
        mp = ctx.new_page(); mp.set_content(m.get('html') or ''); mp.screenshot(path=SH + '/nutzer-mail.png', full_page=True); mp.close()
    check('Knopf sendet die Zugangsdaten mit Startpasswort', m and m.get('to') == ['lena.lager@example.org'] and pw in (m.get('text') or '') and 'Hallo Lena,' in (m.get('text') or ''))
    check('Status „gesendet“, Knopf „Erneut senden“', 'lena.lager@example.org' in a.inner_text('#us-mail-st') and 'Erneut senden' in a.inner_text('#user-body [data-uact="sendmail"]'))
    a.click('#user-body .dlg-foot [data-close]'); a.wait_for_function("!document.querySelector('#dlg-user').open")
    check('„Fertig“ schließt', True)
    # bestehender Nutzer: Knopf „Zugangsdaten per E-Mail“ ohne Passwort
    a.locator('.utab tbody tr:has-text("lena-lager")').click(); a.wait_for_selector('#dlg-user[open] [data-uact="mail"]')
    check('Bearbeiten: Vorname/Nachname getrennt, Benutzername gesperrt, letzter Versand', a.input_value('#user-body [name=vorname]') == 'Lena' and a.input_value('#user-body [name=nachname]') == 'Lager'
          and a.locator('#user-body [name=username]').is_disabled() and 'zuletzt per E-Mail' in a.inner_text('#user-body'))
    n0 = len(smtp.messages)
    a.click('#user-body [data-uact="mail"]'); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("!document.querySelector('#dlg-user').open")
    until(lambda: len(smtp.messages) > n0)
    m = smtp.messages[-1] if len(smtp.messages) > n0 else {}
    check('Zugangsdaten erneut gesendet, ohne Passwort', m and pw not in (m.get('text') or '') and 'separat' in (m.get('text') or ''))
    a.locator('.utab tbody tr:has-text("Solo")').click(); a.wait_for_selector('#dlg-user[open]')
    check('Altzugang: Name im Vornamen, Nachname leer und nicht Pflicht', a.input_value('#user-body [name=vorname]') == 'Solo' and a.input_value('#user-body [name=nachname]') == ''
          and a.get_attribute('#user-body [name=nachname]', 'required') is None)
    a.click('#user-body [type=submit]'); a.wait_for_function("!document.querySelector('#dlg-user').open")
    check('Altzugang speicherbar', True)
    # Handy
    a.set_viewport_size({'width': 390, 'height': 844}); a.emulate_media(color_scheme='dark')
    a.click('#user-add'); a.wait_for_selector('#dlg-user[open] [name=vorname]')
    over = a.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    check('Mobil 390 px: kein seitliches Scrollen', over <= 1, over)
    a.screenshot(path=SH + '/nutzer-anlegen-mobil.png')
    a.click('#user-body .dlg-foot [data-close]'); a.wait_for_function("!document.querySelector('#dlg-user').open")
    br.close()

check('keine JavaScript-Fehler', not errors, errors[:3])
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
