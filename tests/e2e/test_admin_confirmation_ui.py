"""Abgelaufene Admin-Freigabe im Browser: Abbruch, Fehlversuch und einmalige Wiederholung.

Geprüft im Modul Sicherheit (Einstellungen → Anmeldung und Passwörter, Dialog auf 390 px): Die Bestätigung legt sich im selben
Dialog über das Formular (kein zweiter Dialog); Abbrechen kehrt mit allen Eingaben zum Formular zurück, ohne die Änderung erneut
zu senden; ein falsches Passwort lässt den Schritt offen und leert das Feld; nach richtiger Bestätigung wird die Änderung genau
einmal wiederholt. Nur synthetische Testdaten."""
import json
import sys
from umgebung import BASE, storage_raw  # Testserver je Gruppe (parallel)
from playwright.sync_api import sync_playwright
from auth_helpers import expire_session, PW
results = []


def check(name, value, info=''):
    results.append(bool(value)); print(('PASS ' if value else 'FAIL ') + name + (('  ' + str(info)[:300]) if info else ''))


def sicherheit():
    raw = storage_raw('sicherheit') or '{}'
    return json.loads(raw.split('\n', 1)[1] if raw.startswith('<?php') else raw)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    errors = []; saves = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('response', lambda r: saves.append(r.status) if 'action=security_save' in r.url else None)
    page.goto(BASE + '/admin/')
    page.fill('#au-user', 'admin'); page.fill('#pw1', PW); page.click('#auth-submit')
    page.wait_for_selector('#screen-auth', state='hidden')
    page.goto(BASE + '/module/sicherheit/#einstellungen'); page.wait_for_selector('[data-e="e-anmeldung"]')
    page.click('[data-e="e-anmeldung"]'); page.wait_for_selector('#sic-dlg[open] #sec-form')
    sid = next(c['value'] for c in page.context.cookies() if c['name'] == 'WA_ADMIN')
    expire_session(sid)
    page.locator('#sec-form [name="pwMin"]').fill('12')
    page.click('#sic-dlg .sic-dfuss [type=submit]')
    page.wait_for_selector('#sic-dlg .sic-pwschritt #sic-pw')
    check('Bestätigung im selben Dialog, Formular verdeckt', page.locator('#sic-pw').is_visible() and page.locator('#sec-form').is_hidden() and page.locator('dialog[open]').count() == 1)
    check('Fokus im Passwortfeld', page.evaluate('document.activeElement.id') == 'sic-pw')
    check('390 px: Dialog passt (keine waagerechte Scrollleiste)', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
    page.click('.sic-pwschritt [data-pw="nein"].btn')
    page.wait_for_selector('#sec-form', state='visible')
    check('Abbrechen: zurück zum Formular, Änderung nicht erneut gesendet', saves == [403], saves)
    check('Eingabe nach dem Abbrechen erhalten', page.locator('#sec-form [name="pwMin"]').input_value() == '12')
    page.click('#sic-dlg .sic-dfuss [type=submit]'); page.wait_for_selector('#sic-pw')
    page.fill('#sic-pw', 'Falsch-Geheimnis-123'); page.click('#sic-pw-ok')
    page.wait_for_selector('#sic-pw-err:not(:empty)')
    check('falsches Passwort: Schritt bleibt offen', page.locator('#sic-pw').is_visible())
    check('falsches Passwort: Feld geleert', page.locator('#sic-pw').input_value() == '')
    check('falsches Passwort: Änderung nicht wiederholt', saves == [403, 403], saves)
    page.fill('#sic-pw', PW); page.click('#sic-pw-ok')
    page.wait_for_selector('#sic-dlg', state='hidden')
    page.wait_for_function('document.querySelector("#sic-toast").textContent.includes("Sicherheitseinstellungen gespeichert")')
    check('richtige Bestätigung: genau eine Wiederholung', saves == [403, 403, 200], saves)
    check('Einstellung gespeichert', sicherheit().get('pwMin') == 12, sicherheit())
    page.keyboard.press('Escape')
    check('keine Skriptfehler', not errors, errors)
    browser.close()
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
