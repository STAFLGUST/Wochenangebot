"""Modul Sicherheit (Oberfläche sicherheit.intern unter /module/sicherheit/, docs/plattform/modul-sicherheit.md).

Geprüft: Register und Kachel (Gruppe „Verwaltung & Daten“ direkt nach der Verwaltung, nur mit Modulzugang, Standardrollen ohne
Zugang); Aktionen sicherheit_lage, sicherheit_ereignisse (Filter, Grenzen), sicherheit_konten (Administratoren und Inhaber
sicherheitsrelevanter Rechte, Sitzungen) mit Rechten (anonym 401, ohne Recht 403); Verwaltung → System (betrieb_status nur
Administrator, Hinweis auf das Modul, keine Sicherheitsansichten mehr); Oberfläche: Reiter je Recht (Administrator alle,
„Notfall auslösen“ nur Notfall, „Sicherheit ansehen“ Lagebild/Notfall/Ereignisse), Lagebild mit Gesamtbewertung, Dialoge
(Ereignis, auffällige Adresse, Vorlage mit Vorschau, Einstellungen, Ländersperre, Passwortbestätigung, Sperre, Sitzung, Konto,
Befund) mit Esc/Schließen und Fokus, Notfall auslösen in Schritten (Wirkung → Grund und Bestätigungswort) und beenden,
Vorlage „Notfall“ startet den Notfallmodus, Dashboard-Hinweis im Notfall; hell/dunkel, Desktop und 390 px (Dialog als Blatt
von unten); keine JavaScript-Fehler. Nur synthetische Testdaten.
"""
import json
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def doc(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('erik', 'Erik Editor', 'editor', 'Bearbeiter-Kennwort-4', {}),
                          ('nele', 'Nele Notfall', 'editor', 'Kollegin-Kennwort-8', {'grant': ['sicherheit.notfall']}),
                          ('sina', 'Sina Sicht', 'viewer', 'Leserin-Kennwort-6', {'grant': ['sicherheit.sehen']}),
                          ('karl', 'Karl Kunde', 'editor', 'Vertrieb-Kennwort-2', {'grant': ['kunden.bearbeiten']})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
E = Client('198.51.100.11'); E.call('login', {'username': 'erik', 'password': 'Bearbeiter-Kennwort-4'})
Ne = Client('198.51.100.12'); Ne.call('login', {'username': 'nele', 'password': 'Kollegin-Kennwort-8'})
Si = Client('198.51.100.13'); Si.call('login', {'username': 'sina', 'password': 'Leserin-Kennwort-6'})
N = Client('198.51.100.30')
# ein paar Ereignisse: Fehlanmeldungen von einer Adresse
X = Client('203.0.113.77')
for i in range(3):
    X.call('login', {'username': 'erik', 'password': f'falsch-{i}'})

# ── Register und Kachel ──
mods = A.call('module_status')[1]['module']
ver = [m for m in mods if m.get('gruppe') == 'verwaltung']
ids = [m['id'] for m in sorted(ver, key=lambda m: m['reihenfolge'])]
check('Kachel Sicherheit in „Verwaltung & Daten“ direkt nach der Verwaltung', ids[-2:] == ['verwaltung', 'sicherheit'], ids)
sk = next(m for m in mods if m['id'] == 'sicherheit')
check('Kachel: Adresse /module/sicherheit/, verfügbar für Administratoren', sk['kachel']['adresse'] == 'https://sicherheit.dashboard-stafl.de/module/sicherheit/'
      and sk['kachel']['status'] == 'verfuegbar' and sk['kachel']['zugang'] and sk['icon'] == 'shield-lock', sk['kachel'])
check('Oberfläche nicht sperrbar (nie in Wartung)', sk['oberflaechen'][0]['sperrbar'] is False)
me = {m['id']: m for m in E.call('module_status')[1]['module']}
check('Bearbeiter ohne Recht: Kachel ohne Zugang', me['sicherheit']['kachel']['recht'] is False and me['sicherheit']['kachel']['zugang'] is False, me['sicherheit']['kachel'])
mn = {m['id']: m for m in Ne.call('module_status')[1]['module']}
check('Recht „Notfall auslösen“ bringt den Modulzugang mit', mn['sicherheit']['kachel']['zugang'] is True)
check('Modulwartung für Sicherheit abgewiesen (nicht sperrbar)', A.call('modul_wartung_save', {'bereich': 'sicherheit.intern', 'active': True, 'grund': 'Test'})[0] == 422)

# ── Aktionen und Rechte ──
check('anonym: Ereignisse und Konten 401', N.call('sicherheit_ereignisse')[0] == 401 and N.call('sicherheit_konten')[0] == 401)
check('Bearbeiter: Lage, Ereignisse, Konten 403', all(E.call(a)[0] == 403 for a in ('sicherheit_lage', 'sicherheit_ereignisse', 'sicherheit_konten')))
st, r = A.call('sicherheit_lage')
L = r.get('lage', {})
check('Lagebild: Kennzahlen, Verlauf 14 Tage, Konfigurationsprüfung, Ereignisse', st == 200 and len(L.get('timeline', [])) == 14 and L['kennzahlen']['fehl24'] >= 3
      and L['config'] and isinstance(L['ereignisse'], list), (st, list(L)))
check('Lagebild: auffällige Adresse mit versuchtem Benutzernamen', any(x['ip'] == '203.0.113.77' and 'erik' in x['users'] for x in L.get('topIps', [])), L.get('topIps'))
check('Lagebild: Wirkungen des Notfalls mit Bestätigungswort und gesperrten Bereichen', r['wirkungen']['wort'] == 'NOTFALL' and 'Verwaltung' in r['wirkungen']['bereiche']
      and 'Sicherheit' not in r['wirkungen']['bereiche'], r['wirkungen'].get('bereiche'))
st, r = A.call('sicherheit_ereignisse')
check('Ereignisse: Standard 7 Tage, Arten mit Zahlen', st == 200 and r['tage'] == 7 and {x['key'] for x in r['arten']} == {'anmeldung', 'kunden', 'konten', 'einstellungen', 'notfall'}, r.get('arten'))
check('Ereignisse: Fehlanmeldung als Warnung', any(e['a'] == 'login_fail' and e['stufe'] == 'warn' and e['ip'] == '203.0.113.77' for e in r['ereignisse']))
st, r2 = A.call('sicherheit_ereignisse&art=konten&q=nele&tage=30')
check('Ereignisse: Filter Art und Suche', st == 200 and r2['ereignisse'] and all(e['art'] == 'konten' for e in r2['ereignisse']) and all('nele' in json.dumps(e, ensure_ascii=False).lower() for e in r2['ereignisse']), r2.get('ereignisse', [])[:2])
check('Ereignisse: ungültiger Zeitraum bzw. Art 422', A.call('sicherheit_ereignisse&tage=5')[0] == 422 and A.call('sicherheit_ereignisse&art=x')[0] == 422)
check('Ansehen-Recht: Ereignisse lesbar', Si.call('sicherheit_ereignisse')[0] == 200)
st, r = A.call('sicherheit_konten')
k = {x['username']: x for x in r.get('konten', [])}
check('Konten: Administrator, Notfall-, Ansehen- und Kundenrecht; Bearbeiter ohne heikle Rechte nicht', {'admin', 'nele', 'sina', 'karl'} <= set(k) and 'erik' not in k, sorted(k))
check('Konten: Rechte und Anmeldeschutz je Konto', [x['key'] for x in k['nele']['rechte']] == ['sicherheit.notfall'] and k['admin']['admin'] and k['nele']['zweiFaktor'] is False
      and k['admin']['sitzungen'] and r['zahlen']['notfall'] == 2, (k['nele'], r.get('zahlen')))
check('Konten: Sitzungen ohne Kennungen anderer Felder (nur sid, ip, Gerät, Zeiten)', set(k['admin']['sitzungen'][0]) == {'sid', 'ip', 'ua', 'created', 'seen', 'current'}, k['admin']['sitzungen'][0])
check('Verwaltung → System: betrieb_status nur Administrator', A.call('betrieb_status')[0] == 200 and E.call('betrieb_status')[0] == 403 and N.call('betrieb_status')[0] == 401)
st, r = A.call('betrieb_status')
check('betrieb_status: Wartung, Sicherung, Speicher, Versand, Notfall – ohne Sicherheitseinstellungen', {'wartung', 'backup', 'storage', 'mail', 'orders', 'notfall'} <= set(r) and 'settings' not in r and 'sessions' not in r, sorted(r))

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1440, thema='light', hoehe=900, ziel='/module/sicherheit/'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin', color_scheme=thema)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        if ziel:
            pg.goto(B + ziel)
        return ctx, pg

    def tab(pg, t):
        pg.click(f'#sic-tabs [data-tab="{t}"]')
        pg.wait_for_selector(f'#tab-{t}:not([hidden]) .sic-block, #tab-{t}:not([hidden]) .sic-held, #tab-{t}:not([hidden]) .sic-einst')

    def dialog_zu(pg):
        pg.keyboard.press('Escape'); pg.wait_for_selector('#sic-dlg', state='hidden')

    ctx, pg = anmelden('admin', PW, '198.51.100.2')
    pg.wait_for_selector('#sic-app:not([hidden])'); pg.wait_for_selector('#sic-gesamt strong')
    sichtbar = pg.eval_on_selector_all('#sic-tabs [data-tab]', 'b => b.filter(x => !x.hidden).map(x => x.dataset.tab)')
    check('Administrator: alle acht Reiter', sichtbar == ['lage', 'notfall', 'firewall', 'sitzungen', 'datei', 'ereignisse', 'einstellungen', 'konten'], sichtbar)
    check('Kopf: Normalbetrieb, Benutzer', 'Normalbetrieb' in pg.inner_text('#sic-lage-pille') and pg.inner_text('#sic-user-name') == 'Administrator')
    pg.wait_for_function("!document.querySelector('#sic-bchecks').textContent.includes('laufen')")
    lage = pg.inner_text('#tab-lage')
    check('Lagebild: Gesamtbewertung, Karten, Verlauf, auffällige Adressen, Prüfung, Ereignisse', all(t in lage for t in (
        'Angriffsversuche', 'Fehlanmeldungen', 'Zwei-Faktor-Anmeldung', 'Dateiprüfung', 'Datensicherung', 'Auffällige Adressen', 'Konfigurationsprüfung', 'Letzte Ereignisse', 'Normalbetrieb')), lage[:500])
    pg.screenshot(path=f'{SH}/sicherheit_lagebild_1440.png', full_page=True)
    pg.click('[data-topip]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Dialog „auffällige Adresse“: Fehlversuche, Benutzername, Sperren-Knopf', '203.0.113.77' in pg.inner_text('#sic-dlg') and 'erik' in pg.inner_text('#sic-dlg') and pg.is_visible('#sic-dlg [data-d="sperren"]'))
    dialog_zu(pg)
    check('Esc schließt den Dialog, Fokus zurück auf die Zeile', pg.evaluate("document.activeElement && document.activeElement.matches('[data-topip]')"))
    pg.click('[data-lev]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Dialog „Ereignis“: Vorgang, Benutzer, IP', 'Vorgang' in pg.inner_text('#sic-dlg') and 'IP-Adresse' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg [data-d="zu"].sic-dzu'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.click('#tab-lage [data-geh="firewall"]'); pg.wait_for_selector('#tab-firewall:not([hidden]) #fw-verkehr')
    check('Karte führt in den Reiter (Firewall)', pg.url.endswith('#firewall'))

    # Firewall
    fw = pg.inner_text('#tab-firewall')
    check('Firewall: Karten, Live-Verkehr, Sperrlisten', all(t in fw for t in ('Firewall', 'Live-Verkehr', 'Gesperrte Adressen', 'Anmeldebremse')), fw[:300])
    pg.click('[data-fw="sperren-neu"]'); pg.wait_for_selector('#sic-dlg[open] #fs-ip')
    check('Sperren-Dialog: Fokus im Adressfeld', pg.evaluate("document.activeElement.id") == 'fs-ip')
    pg.fill('#fs-ip', '198.51.100.250'); pg.fill('#fs-grund', 'Test aus dem Modul'); pg.click('#sic-dlg .sic-dfuss [type=submit]')
    pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_function("document.querySelector('#tab-firewall').textContent.includes('198.51.100.250')")
    check('Adresse gesperrt und in der Liste', 'Test aus dem Modul' in pg.inner_text('#tab-firewall'))
    pg.click('[data-fw="frei"][data-ip="198.51.100.250"]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Freigeben fragt im Dialog nach', 'Sperre aufheben?' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_function("!document.querySelector('#tab-firewall').textContent.includes('198.51.100.250')")
    check('Sperre aufgehoben', '198.51.100.250' not in pg.inner_text('#tab-firewall'))
    pg.click('[data-fw="einstellungen"]'); pg.wait_for_selector('#sic-dlg[open] #fw-form')
    pg.fill('#fw-form [name="treffer"]', '4'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    check('Firewall-Einstellungen im Dialog gespeichert', (doc('firewall') or {}).get('treffer') == 4, doc('firewall'))

    # Sitzungen
    tab(pg, 'sitzungen')
    si = pg.inner_text('#tab-sitzungen')
    check('Sitzungen: aktive Sitzungen, Fehlanmeldungen, ohne Zwei-Faktor', 'Aktive Sitzungen' in si and 'Fehlgeschlagene Anmeldungen' in si and 'Nele Notfall' in si, si[:300])
    pg.click('#sic-sitzungen [data-si="ende"][data-name="Erik Editor"]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Sitzung beenden fragt nach', 'Sitzung beenden?' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    check('Sitzung von Erik beendet', E.call('status')[1].get('loggedIn') is False)

    # Dateiprüfung
    tab(pg, 'datei')
    check('Dateiprüfung: Ergebnis mit Prüfen-Knopf', pg.is_visible('#tab-datei [data-ip="run"]'))
    if pg.query_selector('#tab-datei [data-befund]'):
        pg.click('#tab-datei [data-befund]'); pg.wait_for_selector('#sic-dlg[open]')
        check('Befund im Dialog', 'Befund der Dateiprüfung' in pg.inner_text('#sic-dlg')); dialog_zu(pg)

    # Ereignisse
    tab(pg, 'ereignisse'); pg.wait_for_selector('#ev-liste [data-ev]')
    pg.click('#ev-arten [data-art="anmeldung"]'); pg.wait_for_selector('#ev-arten [data-art="anmeldung"].an')
    check('Ereignisse: Filter Anmeldung', all(t == 'Anmeldung' for t in pg.eval_on_selector_all('#ev-liste .sic-pille', 'x => x.map(e => e.textContent)')))
    pg.fill('#ev-q', '203.0.113.77'); pg.wait_for_function("[...document.querySelectorAll('#ev-liste [data-ev]')].every(r => r.textContent.includes('203.0.113.77'))")
    pg.click('#ev-liste [data-ev]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Ereignis-Details im Dialog', '203.0.113.77' in pg.inner_text('#sic-dlg')); dialog_zu(pg)
    pg.click('#ev-export'); pg.wait_for_selector('#sic-dlg[open] #ex-tage')
    with pg.expect_download() as dl:
        pg.click('#sic-dlg .sic-dfuss [type=submit]')
    check('Export: CSV heruntergeladen', dl.value.suggested_filename.startswith('Sicherheitsprotokoll_'))

    # Einstellungen & Vorlagen
    tab(pg, 'einstellungen')
    ei = pg.inner_text('#tab-einstellungen')
    check('Einstellungen: Vorlagen Standard/Streng/Notfall, Zusammenfassungen', all(t in ei for t in ('Standard', 'Streng', 'Notfall', 'Anmeldung und Passwörter', 'IP-Freigabe', 'Ländersperre', 'Passwortbestätigung')), ei[:300])
    pg.click('#tab-einstellungen [data-v="streng"]'); pg.wait_for_selector('#sic-dlg[open] .vorschau')
    check('Vorlage: Vorschau mit Änderungen (jetzt → danach)', pg.locator('#sic-dlg .vorschau tr.neu').count() >= 3 and 'Zwei-Faktor-Pflicht' in pg.inner_text('#sic-dlg'))
    pg.screenshot(path=f'{SH}/sicherheit_vorlage_dialog_1440.png')
    dialog_zu(pg)
    pg.click('[data-e="e-anmeldung"]'); pg.wait_for_selector('#sic-dlg[open] #sec-form')
    pg.fill('#sec-form [name="pwMin"]', '14'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    check('Anmeldung und Passwörter im Dialog gespeichert (übrige Einstellungen bleiben)', (doc('sicherheit') or {}).get('pwMin') == 14 and doc('sicherheit').get('treffer') is None, doc('sicherheit'))
    pg.click('[data-e="e-geo"]'); pg.wait_for_selector('#sic-dlg[open] #geo-box')
    pg.fill('#geo-q', 'Kanada'); pg.wait_for_selector('#geo-list [data-geo-cc="CA"]'); pg.check('#geo-list [data-geo-cc="CA"]')
    pg.check('#geo-box [name="geoEnabled"]'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg[open] h2:has-text("Ländersperre speichern?")')
    check('Ländersperre: Rückfrage im selben Dialog', 'Kanada' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    check('Ländersperre gespeichert', doc('sicherheit').get('geoEnabled') is True and doc('sicherheit').get('geoCountries') == ['CA'], doc('sicherheit'))
    pg.click('[data-e="e-bst"]'); pg.wait_for_selector('#sic-dlg[open] #bst-form')
    check('Passwortbestätigung: Notfall-Schlüssel (auslösen abschaltbar, beenden fest)', pg.locator('#bst-form [name=bst][value="notfall_ausloesen"]').count() == 1
          and 'Notfallmodus beenden' in pg.inner_text('#bst-form .fest:has-text("Notfallmodus beenden")'))
    dialog_zu(pg)

    # Konten
    tab(pg, 'konten')
    pg.click('#tab-konten [data-konto]:has-text("Nele Notfall")'); pg.wait_for_selector('#sic-dlg[open]')
    check('Konto-Details: Rechte und Anmeldeschutz', 'sicherheit.notfall' in pg.inner_text('#sic-dlg') and 'nur Passwort' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg [data-d="alle"]'); pg.wait_for_function("document.querySelector('#sic-dlg').textContent.includes('Keine aktive Sitzung')")
    check('Konto: alle Sitzungen beendet, Dialog bleibt offen', Ne.call('status')[1].get('loggedIn') is False)
    dialog_zu(pg)
    pg.screenshot(path=f'{SH}/sicherheit_konten_1440.png', full_page=True)

    # Notfall auslösen und beenden über die Oberfläche
    tab(pg, 'notfall')
    check('Notfall: Normalbetrieb mit Wirkungen und Bereichen', 'Kein Notfall aktiv' in pg.inner_text('#tab-notfall') and 'Gesperrte Bereiche' in pg.inner_text('#tab-notfall'))
    pg.screenshot(path=f'{SH}/sicherheit_notfall_1440.png', full_page=True)
    pg.click('#nf-an'); pg.wait_for_selector('#sic-dlg[open]')
    check('Schritt 1: Wirkung', 'Schritt 1 von 2' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg #nf-grund')
    check('Schritt 2: Fokus im Grund, Knopf erst mit Bestätigungswort', pg.evaluate("document.activeElement.id") == 'nf-grund' and pg.is_disabled('#nf-los'))
    pg.fill('#nf-grund', 'Probe über die Oberfläche'); pg.fill('#nf-wort', 'notfal')
    check('falsches Wort: Knopf gesperrt', pg.is_disabled('#nf-los'))
    pg.fill('#nf-wort', 'notfall')
    pg.screenshot(path=f'{SH}/sicherheit_notfall_dialog_1440.png')
    pg.click('#nf-los'); pg.wait_for_selector('#sic-dlg h2:has-text("Notfallmodus ist aktiv")')
    check('Notfall ausgelöst: Zusammenfassung', 'Mitarbeitersitzungen beendet' in pg.inner_text('#sic-dlg') and (doc('sicherheit-notfall') or {}).get('aktiv') is True)
    pg.click('#sic-dlg .sic-dfuss [data-d="zu"]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_selector('#tab-notfall .sic-held.aktiv')
    check('Kopf zeigt den Notfall, Band nicht doppelt im Reiter Notfall', 'Notfall aktiv' in pg.inner_text('#sic-lage-pille') and pg.is_hidden('#sic-notfallband'))
    pg.screenshot(path=f'{SH}/sicherheit_notfall_aktiv_1440.png', full_page=True)
    tab(pg, 'lage'); pg.wait_for_selector('#sic-notfallband:not([hidden])')
    check('in den anderen Reitern: rotes Band mit Grund und Weg zum Notfall', 'Probe über die Oberfläche' in pg.inner_text('#sic-notfallband') and pg.is_visible('#sic-notfallband [data-geh="notfall"]'))
    pg.click('#sic-notfallband [data-geh="notfall"]'); pg.wait_for_selector('#tab-notfall:not([hidden]) .sic-held.aktiv')
    ctx2, pd = anmelden('admin', PW, '198.51.100.2', ziel='/dashboard/')
    pd.wait_for_selector('#db-notfall:not([hidden])')
    check('Dashboard: Hinweis „Notfallmodus aktiv“ für Administratoren', 'Notfallmodus aktiv' in pd.inner_text('#db-notfall'))
    ctx2.close()
    pg.click('#nf-aus'); pg.wait_for_selector('#sic-dlg[open] #nf-notiz')
    pg.fill('#nf-notiz', 'Probe beendet'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg h2:has-text("Notfall beendet")')
    check('Notfall beendet, Einstellungen wiederhergestellt', 'wie vor dem Notfall' in pg.inner_text('#sic-dlg') and doc('sicherheit-notfall').get('aktiv') is False)
    dialog_zu(pg)
    pg.wait_for_selector('#tab-notfall .sic-held:not(.aktiv)')
    check('Verlauf zeigt den Notfall', 'Probe über die Oberfläche' in pg.inner_text('#tab-notfall'))
    # Vorlage „Notfall“ startet den Notfallmodus
    tab(pg, 'einstellungen'); pg.click('#vorlage-notfall'); pg.wait_for_selector('#sic-dlg[open]')
    check('Vorlage „Notfall“ öffnet „Notfall auslösen“ (Schritt 1)', 'Notfall auslösen' in pg.inner_text('#sic-dlg') and 'Schritt 1 von 2' in pg.inner_text('#sic-dlg'))
    dialog_zu(pg)
    # dunkel
    pg.click('#sic-theme'); pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'")
    tab(pg, 'lage'); pg.wait_for_selector('#sic-gesamt strong')
    pg.screenshot(path=f'{SH}/sicherheit_lagebild_dunkel_1440.png', full_page=True)
    pg.click('#sic-theme')
    ctx.close()

    # Handy 390 px
    ctx, pg = anmelden('admin', PW, '198.51.100.2', breite=390, hoehe=844)
    pg.wait_for_selector('#sic-gesamt strong')
    check('390 px: keine waagerechte Scrollleiste', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), pg.evaluate('[document.documentElement.scrollWidth, window.innerWidth]'))
    pg.screenshot(path=f'{SH}/sicherheit_lagebild_390.png', full_page=True)
    pg.click('#sic-tabs [data-tab="notfall"]'); pg.wait_for_selector('#nf-an')
    pg.screenshot(path=f'{SH}/sicherheit_notfall_390.png', full_page=True)
    pg.click('#nf-an'); pg.wait_for_selector('#sic-dlg[open]'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg #nf-grund')
    box = pg.eval_on_selector('#sic-dlg', 'd => { const r = d.getBoundingClientRect(); return [r.left, r.width, Math.round(r.bottom), innerHeight]; }')
    check('390 px: Dialog als Blatt von unten (volle Breite, unten angelegt)', box[0] == 0 and box[1] == 390 and abs(box[2] - box[3]) <= 1, box)
    pg.screenshot(path=f'{SH}/sicherheit_notfall_dialog_390.png')
    dialog_zu(pg)
    ctx.close()

    # Mitarbeiterin mit Recht „Notfall auslösen“: nur der Reiter Notfall
    Ne.call('login', {'username': 'nele', 'password': 'Kollegin-Kennwort-8'})
    ctx, pg = anmelden('nele', 'Kollegin-Kennwort-8', '198.51.100.12')
    pg.wait_for_selector('#sic-app:not([hidden]) #nf-an')
    sichtbar = pg.eval_on_selector_all('#sic-tabs [data-tab]', 'b => b.filter(x => !x.hidden).map(x => x.dataset.tab)')
    check('Recht „Notfall auslösen“: nur Reiter Notfall, ohne Verlauf', sichtbar == ['notfall'] and 'Letzte Notfälle' not in pg.inner_text('#tab-notfall'), sichtbar)
    pg.click('#nf-an'); pg.wait_for_selector('#sic-dlg[open]'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg #nf-grund')
    check('ohne Administratorrolle: keine Option „andere Administratoren abmelden“', pg.locator('#nf-admins').count() == 0)
    pg.fill('#nf-grund', 'Auffälliges Konto im Vertrieb'); pg.fill('#nf-wort', 'NOTFALL'); pg.click('#nf-los')
    pg.wait_for_selector('#sic-dlg h2:has-text("Notfallmodus ist aktiv")')
    check('Mitarbeiterin löst aus', doc('sicherheit-notfall').get('von') == 'nele')
    dialog_zu(pg)
    pg.wait_for_selector('#tab-notfall .sic-held.aktiv')
    check('… sieht den Notfall, darf ihn nicht beenden', pg.locator('#nf-aus').count() == 0 and 'Beenden können nur Administratoren' in pg.inner_text('#tab-notfall'))
    pg.screenshot(path=f'{SH}/sicherheit_notfall_mitarbeiterin_1440.png', full_page=True)
    ctx.close()
    ctx, pd = anmelden('erik', 'Bearbeiter-Kennwort-4', '198.51.100.11', ziel='/dashboard/')
    pd.wait_for_selector('#db-notfall:not([hidden])')
    check('Dashboard: Bearbeiter sieht „vorübergehend gesperrt“ ohne Einzelheiten', 'vorübergehend gesperrt' in pd.inner_text('#db-notfall') and 'Vertrieb' not in pd.inner_text('#db-notfall'))
    pd.screenshot(path=f'{SH}/sicherheit_dashboard_notfall_1280.png', full_page=True)
    ctx.close()
    check('Administrator beendet (API)', A.call('sicherheit_notfall_aus', {})[0] == 200)

    # Ansehen-Recht: Lagebild, Notfall, Ereignisse
    ctx, pg = anmelden('sina', 'Leserin-Kennwort-6', '198.51.100.13')
    pg.wait_for_selector('#sic-gesamt strong')
    sichtbar = pg.eval_on_selector_all('#sic-tabs [data-tab]', 'b => b.filter(x => !x.hidden).map(x => x.dataset.tab)')
    check('Recht „Sicherheit ansehen“: Lagebild, Notfall, Ereignisse', sichtbar == ['lage', 'notfall', 'ereignisse'], sichtbar)
    pg.click('#sic-tabs [data-tab="notfall"]'); pg.wait_for_selector('#tab-notfall .sic-held')
    check('… kein Auslösen, Verlauf sichtbar', pg.locator('#nf-an').count() == 0 and 'Letzte Notfälle' in pg.inner_text('#tab-notfall'))
    ctx.close()

    # Bearbeiter ohne Recht
    E.call('login', {'username': 'erik', 'password': 'Bearbeiter-Kennwort-4'})
    ctx, pg = anmelden('erik', 'Bearbeiter-Kennwort-4', '198.51.100.11')
    pg.wait_for_selector('#sic-err:not([hidden])')
    check('Bearbeiter ohne Recht: Hinweis statt Inhalt', 'Berechtigung' in pg.inner_text('#sic-err'))
    ctx.close()

    # Verwaltung → System
    ctx, pg = anmelden('admin', PW, '198.51.100.2', ziel='')
    pg.wait_for_selector('#screen-editor:not([hidden])')
    pg.click('#vt-sec'); pg.wait_for_selector('#sic-umzug')
    sy = pg.inner_text('#view-sec')
    check('Verwaltung → System: Hinweis mit Link, Betrieb, Wartung, Module – keine Sicherheitsansichten', 'Sicherheit hat ein eigenes Modul' in sy and 'Diagnose' in sy and pg.is_visible('#wartung-form')
          and pg.locator('#sec-form, #bst-form, #geo-box, #ip-out').count() == 0 and pg.get_attribute('#sic-link', 'href') == '../module/sicherheit/', sy[:300])
    check('Verwaltung: Reiter „Schutz“ entfernt, „System“ statt „Sicherheit“', pg.locator('#vt-schutz').count() == 0 and pg.inner_text('#vt-sec') == 'System')
    pg.wait_for_selector('#mv-box table')
    pg.screenshot(path=f'{SH}/verwaltung_system_1440.png', full_page=True)
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
