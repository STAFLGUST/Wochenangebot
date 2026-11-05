"""Abgelaufene Admin-Freigabe im Browser: Abbruch, Fehlversuch und einmalige Wiederholung.

Geprüft im Modul Sicherheit (Einstellungen → Anmeldung und Passwörter, Dialog auf 390 px): Die Bestätigung legt sich im selben
Dialog über das Formular (kein zweiter Dialog); Abbrechen kehrt mit allen Eingaben zum Formular zurück, ohne die Änderung erneut
zu senden; ein falsches Passwort lässt den Schritt offen und leert das Feld; nach richtiger Bestätigung wird die Änderung genau
einmal wiederholt.

Dazu die Bestätigung im eigenen Fenster (Keycloak-Hosts, hier nachgestellt): Kommt aus dem Anmeldefenster keine Meldung an,
genügt sein Schließen – die Anfrage wird wiederholt; ob bestätigt ist, entscheidet weiter der Server. Nur synthetische Testdaten."""
import json
import re
import sys
from umgebung import BASE, SH, storage_raw  # Testserver je Gruppe (parallel)
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

    # Bestätigung im eigenen Fenster (zentrale Anmeldung; Server-Antwort und Anmeldefenster hier nachgestellt): Das Fenster
    # schließt sich, ohne eine der drei Meldungen zu senden (BroadcastChannel, postMessage, localStorage) – der Eingabebereich
    # wiederholt die Anfrage trotzdem, sobald es zu ist. Lehnt der Server erneut ab, bleibt alles offen (nichts umgangen).
    ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
    pg = ctx.new_page(); fehler = []
    pg.on('pageerror', lambda e: fehler.append(str(e)))
    ablehnen = {'n': 1}; versuche = []
    def kunde_save(route):
        versuche.append(route.request.method)
        if len(versuche) <= ablehnen['n']:
            route.fulfill(status=403, content_type='application/json', body=json.dumps({
                'ok': False, 'code': 'reauth_required', 'anmelden': '/oidc/callback?iss=test&target_link_uri=', 'error': 'Bitte bestätigen.'}))
        else:
            route.continue_()
    ctx.route(re.compile(r'/api/\?action=kunde_save(&|$)'), kunde_save)
    ctx.route('**/oidc/callback*', lambda r: r.fulfill(status=200, content_type='text/html',
                                                      body='<!doctype html><title>Anmeldung</title><script>window.close()</script>'))
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit')
    pg.wait_for_selector('#screen-editor:not([hidden])')
    pg.click('#vt-kunden'); pg.wait_for_selector('#view-kunden #k-add')

    def kunde_anlegen(firma):
        pg.click('#k-add'); pg.wait_for_selector('#dlg-kunde[open] [name="firma"]')
        pg.fill('#kunde-body [name="firma"]', firma)
        pg.click('#kunde-body [data-kact=gen]')   # Startpasswort vorschlagen (Pflicht für den Zugang)
        pg.click('#kunde-body [type="submit"]'); pg.wait_for_selector('#dlg-reauth-kc[open]')
        with ctx.expect_page() as neu:
            pg.click('#rkc-auf')
        return neu.value

    fenster = kunde_anlegen('Gasthaus Fensterrückfall')
    pg.wait_for_function("!document.querySelector('#dlg-kunde').open", timeout=10000)
    check('eigenes Fenster ohne Meldung: nach dem Schließen genau einmal wiederholt und gespeichert', versuche == ['POST', 'POST']
          and fenster.is_closed() and pg.locator('#dlg-reauth-kc[open]').count() == 0, versuche)
    pg.wait_for_selector('#view-kunden tr[data-kid]:has-text("Gasthaus Fensterrückfall")')
    check('… Kunde angelegt', '"Gasthaus Fensterrückfall"' in (storage_raw('kunden') or ''))

    ablehnen['n'] = 2; versuche.clear()
    kunde_anlegen('Gasthaus Nicht Bestätigt')
    pg.wait_for_selector('#dlg-reauth-kc[open] #rkc-status.st-warn')
    check('Server lehnt nach dem Schließen erneut ab: Hinweis „noch nicht angekommen“, Eingaben bleiben',
          'noch nicht angekommen' in pg.inner_text('#rkc-status') and pg.locator('#dlg-kunde[open]').count() == 1
          and pg.input_value('#kunde-body [name="firma"]') == 'Gasthaus Nicht Bestätigt' and versuche == ['POST', 'POST'], versuche)
    pg.screenshot(path=SH + '/bestaetigung-fenster-rueckfall-1280.png')
    pg.click('#dlg-reauth-kc [data-close].btn:not(.icon)'); pg.wait_for_selector('#dlg-reauth-kc', state='hidden')
    check('… Abbrechen: nichts gespeichert', '"Gasthaus Nicht Bestätigt"' not in (storage_raw('kunden') or '') and versuche == ['POST', 'POST'], versuche)
    check('… keine Skriptfehler', not fehler, fehler)
    ctx.close()
    browser.close()
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
