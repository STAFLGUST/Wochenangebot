"""Rollen und Rechte: eigene Rollen (anlegen, umbenennen, kopieren, löschen), Modulzugang „<modul>.zugang“ je Rolle,
mehrere Rollen je Mitarbeiter, Standardrollen unverändert, Durchsetzung auf dem Server (GR-103), Protokoll und die
Oberfläche (Verwaltung → Rollen und Rechte, Mitarbeiterdialog, Dashboard ohne Kacheln ohne Zugang).

Der Testserver hat keinen eigenen Host (kein WA_OBERFLAECHE): gesperrt wird nach der Oberfläche der Aktion – HR-Aktionen
(hr.intern) brauchen „hr.zugang“, der gemeinsame Eingabebereich (angebot.eingabe) regelt die Sichtbarkeit über die
Einzelrechte. Die Sperre je Host prüft die Gruppe „rollen_host“ (WA_OBERFLAECHE=bestand.intern).
"""
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for name, user, role, pw in [('Lars Lager', 'lars', 'viewer', 'Lager-Zugang-551'), ('Vera Vertrieb', 'vera', 'editor', 'Vertrieb-Zugang-77'),
                             ('Paula Personal', 'paula', 'viewer', 'Personal-Zugang-66')]:
    code, r = A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    check(f'Mitarbeiter {user} angelegt', code == 200, r)
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}


def anmelden(user, pw):
    c = Client('198.51.100.%d' % (20 + len(user)))
    c.call('login', {'username': user, 'password': pw})
    return c


L, V, P = anmelden('lars', 'Lager-Zugang-551'), anmelden('vera', 'Vertrieb-Zugang-77'), anmelden('paula', 'Personal-Zugang-66')
rechte = lambda c: set((c.call('status')[1].get('user') or {}).get('perms') or [])

# ---------- Katalog und Standard ----------
code, rr = A.call('rechte')
check('Übersicht: Rollen, Module und Katalog', code == 200 and [r['id'] for r in rr['rollen']] == ['admin', 'viewer', 'editor']
      and {m['id'] for m in rr['module']} >= {'angebot', 'bestand', 'hr', 'verwaltung', 'import'}, code)
ZUGANG = {p['key'] for p in rr['catalog'] if p['kind'] == 'zugang'}
check('Modulzugang für jede Kachel des Registers', ZUGANG == {f'{m}.zugang' for m in ['angebot', 'bestand', 'crm', 'rewe', 'qs', 'einkauf', 'import', 'hr', 'marketing', 'controlling', 'verwaltung']}, sorted(ZUGANG))
check('Modulzugang gehört zum Modul, Standard: beide Standardrollen', all(p['modul'] == p['key'].split('.')[0] and p['default'] == ['viewer', 'editor'] for p in rr['catalog'] if p['kind'] == 'zugang'))
check('Rechte sind Modulen zugeordnet (Register)', next(p for p in rr['catalog'] if p['key'] == 'kunden.sehen')['modul'] == 'verwaltung'
      and next(p for p in rr['catalog'] if p['key'] == 'preisverlauf.sehen')['modul'] == 'angebot')
check('Bestand: alle Mitarbeiter öffnen weiter alle Module', ZUGANG <= rechte(L) and ZUGANG <= rechte(V))
check('Ältere Oberfläche (rechte_save ohne Modulzugang) entzieht ihn nicht',
      A.call('rechte_save', {'roles': {'viewer': ['preisverlauf.sehen', 'bestand.sehen', 'stammdaten.sehen', 'einkauf.sehen', 'hr.antrag']}})[0] == 200 and ZUGANG <= rechte(L))

# ---------- Eigene Rolle anlegen ----------
check('Bearbeiter darf keine Rollen anlegen', V.call('rolle_save', {'name': 'Hack', 'rechte': ['kunden.bearbeiten']})[0] == 403)
check('Name ist Pflicht', A.call('rolle_save', {'name': ' ', 'rechte': []})[0] == 422)
check('Name doppelt (auch Standardrolle)', A.call('rolle_save', {'name': 'bearbeiter', 'rechte': []})[0] == 422)
check('Administratorrolle ist fest', A.call('rolle_save', {'id': 'admin', 'name': 'Chef', 'rechte': []})[0] == 422)
code, r = A.call('rolle_save', {'name': 'Lager', 'beschreibung': 'Nur Bestand', 'rechte': ['bestand.zugang', 'bestand.einkaufspreise', 'nutzer.verwalten']})
check('Rolle „Lager“ angelegt', code == 200 and r['id'].startswith('r') and len(r['id']) == 9, r)
LAGER = r['id']
lg = next(x for x in r['rollen'] if x['id'] == LAGER)
check('Voraussetzung ergänzt, Unbekanntes ignoriert', set(lg['rechte']) == {'bestand.zugang', 'bestand.einkaufspreise', 'bestand.sehen'} and lg['art'] == 'eigen', lg)

# ---------- Rolle zuordnen ----------
code, r = A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': [LAGER], 'active': True})
check('Mitarbeiter bekommt eine eigene Rolle', code == 200 and r['user']['role'] == LAGER and r['user']['rollen'] == [LAGER], r)
st = L.call('status')[1]['user']
check('Rechte genau laut Rolle', set(st['perms']) == {'bestand.zugang', 'bestand.einkaufspreise', 'bestand.sehen'} and st['rollenName'] == 'Lager', st)
check('Lager sieht Bestand mit EK, nicht den Preisverlauf', L.call('stock')[0] == 200 and L.call('history_list')[0] == 403)
code, r = L.call('hr_start')
check('Ohne HR-Zugang: HR gesperrt (Server)', code == 403 and r.get('code') == 'kein_modulzugang' and r.get('modul') == 'hr', r)
ms = {m['id']: m for m in L.call('module_status')[1]['module']}
check('Dashboard: nur Kacheln mit Zugang', ms['bestand']['kachel']['recht'] and ms['bestand']['kachel']['zugang']
      and not ms['angebot']['kachel']['recht'] and not ms['angebot']['kachel']['zugang'] and not ms['hr']['kachel']['recht'], {k: v['kachel']['recht'] for k, v in ms.items() if v['kachel']})
check('Unbekannte Rolle wird abgelehnt', A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': ['rdeadbeef'], 'active': True})[0] == 422)
check('Leere Rollenliste wird abgelehnt', A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': [], 'active': True})[0] == 422)

# ---------- Mehrere Rollen ----------
code, r = A.call('rolle_save', {'name': 'Personalstelle', 'rechte': ['hr.zugang', 'hr.verwalten']})
PERS = r['id']
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': [PERS, 'editor'], 'active': True})
check('Zwei Rollen: Standardrolle wird Hauptrolle (Rückfall nie mit mehr Rechten)', code == 200 and r['user']['role'] == 'editor' and set(r['user']['rollen']) == {'editor', PERS}, r)
pv = rechte(V)
check('Rechte addieren sich', {'angebot.bearbeiten', 'hr.verwalten', 'hr.antrag', 'hr.zugang'} <= pv and 'kunden.sehen' not in pv, sorted(pv))
check('Personalstelle öffnet die HR-Verwaltung', V.call('hr_verwaltung')[0] == 200)
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['admin', PERS], 'active': True})
check('Administrator schließt weitere Rollen aus', code == 200 and r['user']['role'] == 'admin' and r['user']['rollen'] == ['admin'], r)
A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True})
check('Eigene Rollen nicht änderbar', A.call('user_save', {'id': uid['admin'], 'name': 'Administrator', 'rollen': ['editor'], 'active': True})[0] == 422)
check('Ältere Oberfläche (nur „role“) behält weitere Rollen', A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'role': 'editor', 'active': True})[0] == 200
      and 'hr.verwalten' in rechte(V))
code, r = A.call('bestellungen')
check('Bestellungen zuweisen: alle mit Bearbeitungsrecht (statt Rollenname)', code == 200 and {a['id'] for a in r['assignees']} >= {uid['vera'], uid['admin']}
      and uid['lars'] not in {a['id'] for a in r['assignees']}, r.get('assignees'))

# ---------- Standardrolle ändern, Modulzugang entziehen ----------
code, r = A.call('rolle_save', {'id': 'editor', 'name': 'Vertrieb Innendienst', 'rechte': sorted(set(next(x for x in A.call('rechte')[1]['rollen'] if x['id'] == 'editor')['rechte']) - {'hr.zugang'})})
check('Standardrolle umbenannt, Rechte geändert', code == 200 and next(x for x in r['rollen'] if x['id'] == 'editor')['name'] == 'Vertrieb Innendienst', r)
check('Rechte gelten sofort; HR bleibt über die zweite Rolle offen', 'hr.zugang' in rechte(V) and V.call('hr_start')[0] == 200)
A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor'], 'active': True})
check('Nur noch Standardrolle ohne HR-Zugang: HR gesperrt', V.call('hr_start')[1].get('code') == 'kein_modulzugang')
check('Status bleibt erreichbar (Rückweg, Abmelden)', V.call('status')[0] == 200)
rd = A.call('rechte')[1]
check('Neuer Name überall', rd['roleLabels']['editor'] == 'Vertrieb Innendienst' and V.call('status')[1]['user']['rollenName'] == 'Vertrieb Innendienst')

# ---------- Kopieren, Löschen, Protokoll ----------
code, r = A.call('rolle_save', {'name': 'Lager Nord', 'kopieVon': LAGER})
check('Rolle kopiert (Rechte der Vorlage)', code == 200 and set(next(x for x in r['rollen'] if x['id'] == r['id'])['rechte']) == set(lg['rechte']), r)
code, r = A.call('rolle_loeschen', {'id': LAGER})
check('Rolle in Verwendung wird nicht gelöscht', code == 422 and 'Lars Lager' in r.get('error', ''), r)
check('Standardrolle nicht löschbar', A.call('rolle_loeschen', {'id': 'viewer'})[0] == 422)
check('Bearbeiter darf nicht löschen', V.call('rolle_loeschen', {'id': LAGER})[0] == 403)
log = str(A.call('log')[1].get('entries') or [])
check('Protokoll: angelegt, geändert, Rechte', 'Rolle „Lager“ angelegt' in log and 'Rolle „Vertrieb Innendienst“ geändert' in log and 'Modul „HR“ öffnen' in log)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    fehler = []

    def seite(user, password, w=1440, ziel='/admin/'):
        pg = br.new_page(viewport={'width': w, 'height': 950}, is_mobile=w < 500); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        if ziel != '/admin/': pg.goto(B + ziel)
        return pg

    a = seite('admin', PW)
    a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on')
    check('UI: Rollenliste mit Standard- und eigenen Rollen', a.locator('#view-rollen .rl-item').count() == 6
          and 'Vertrieb Innendienst' in a.inner_text('#view-rollen .rl-liste') and 'Lager Nord' in a.inner_text('#view-rollen .rl-liste'))
    a.screenshot(path=SH + '/rollen-desktop.png', full_page=True)
    # Neue Rolle über die Oberfläche
    a.click('[data-rl-akt="neu"]'); a.wait_for_selector('#rl-name:focus')
    a.fill('#rl-name', 'Einkauf')
    a.check('[data-rl-key="einkauf.melden"]')
    check('UI: Recht hakt seine Voraussetzung an', a.is_checked('[data-rl-key="einkauf.sehen"]'))
    check('UI: ohne Modulzugang abgeblendet mit Hinweis', 'zu' in a.get_attribute('[data-rl-modul="einkauf"]', 'class') and a.is_visible('[data-rl-modul="einkauf"] .rl-mod-hinw'))
    a.click('[data-rl-key="einkauf.zugang"]')
    check('UI: Schalter öffnet das Modul', a.is_checked('[data-rl-key="einkauf.zugang"]') and 'zu' not in a.get_attribute('[data-rl-modul="einkauf"]', 'class').split())
    a.check('[data-rl-key="bestand.zugang"]'); a.check('[data-rl-key="bestand.sehen"]')
    a.uncheck('[data-rl-key="bestand.sehen"]')
    a.check('[data-rl-key="bestand.einkaufspreise"]'); a.uncheck('[data-rl-key="bestand.sehen"]')
    check('UI: Voraussetzung weg → abhängiges Recht weg', not a.is_checked('[data-rl-key="bestand.einkaufspreise"]'))
    a.click('[data-rl-akt="speichern"]'); a.wait_for_selector('#view-rollen .rl-item.on:has-text("Einkauf")')
    ek = next(x for x in A.call('rechte')[1]['rollen'] if x['name'] == 'Einkauf')
    check('UI: Rolle gespeichert', set(ek['rechte']) == {'einkauf.zugang', 'einkauf.sehen', 'einkauf.melden', 'bestand.zugang'}, ek)
    # Wechsel mit ungespeicherten Änderungen fragt nach
    a.fill('#rl-name', 'Einkauf Hamburg')
    a.click('#view-rollen .rl-item:has-text("Lager Nord")'); a.wait_for_selector('#dlg-confirm[open]')
    check('UI: ungespeicherte Änderungen werden nicht stillschweigend verworfen', 'verwerfen' in a.inner_text('#dlg-confirm'))
    a.click('#dlg-confirm [data-v="0"]'); a.wait_for_selector('#dlg-confirm:not([open])', state='attached')
    check('UI: nach Abbrechen bleibt die Rolle gewählt', 'Einkauf' in a.inner_text('#view-rollen .rl-item.on'))
    a.click('[data-rl-akt="verwerfen"]')
    # Rolle löschen (ohne Mitarbeiter)
    a.click('#view-rollen .rl-item:has-text("Lager Nord")'); a.wait_for_selector('#view-rollen .rl-item.on:has-text("Lager Nord")')
    a.click('[data-rl-akt="loeschen"]'); a.wait_for_selector('#dlg-confirm[open]')
    a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("() => !document.querySelector('#view-rollen .rl-liste').textContent.includes('Lager Nord')")
    check('UI: Rolle gelöscht', all(x['name'] != 'Lager Nord' for x in A.call('rechte')[1]['rollen']))
    # Administrator: fest, nichts änderbar
    a.click('#view-rollen .rl-item[data-rl-wahl="admin"]'); a.wait_for_selector('#rl-name[disabled]')
    check('UI: Administrator fest (alles angehakt, gesperrt)', a.locator('#view-rollen [data-rl-key]:not([disabled])').count() == 0 and not a.is_visible('[data-rl-akt="speichern"]'))
    # Mitarbeiterdialog: mehrere Rollen
    a.click('#vt-users'); a.wait_for_selector(f'[data-uedit="{uid["paula"]}"]')
    check('UI: Mitarbeiterliste zeigt Rollennamen', 'Lager' in a.inner_text(f'#view-users tr[data-uid="{uid["lars"]}"]'))
    a.click(f'[data-uedit="{uid["paula"]}"]'); a.wait_for_selector('#dlg-user[open] [name="rollen"]')
    a.check(f'#dlg-user [name="rollen"][value="{PERS}"]')
    a.check('#dlg-user [name="rollen"][value="admin"]')
    check('UI: Administrator wählt die anderen Rollen ab', not a.is_checked(f'#dlg-user [name="rollen"][value="{PERS}"]') and a.locator('#ur-box').is_hidden())
    a.check(f'#dlg-user [name="rollen"][value="{PERS}"]'); a.check('#dlg-user [name="rollen"][value="viewer"]')
    check('UI: andere Rolle wählt Administrator ab', not a.is_checked('#dlg-user [name="rollen"][value="admin"]'))
    a.screenshot(path=SH + '/rollen-mitarbeiter.png')
    a.click('#dlg-user button[type=submit]'); a.wait_for_selector('#dlg-user', state='hidden')
    pu = next(x for x in A.call('users')[1]['users'] if x['username'] == 'paula')
    check('UI: zwei Rollen gespeichert', set(pu['rollen']) == {'viewer', PERS} and pu['role'] == 'viewer', pu)
    # schmal
    a.set_viewport_size({'width': 390, 'height': 844})
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on')
    a.screenshot(path=SH + '/rollen-390.png', full_page=True)
    check('390 px: kein waagerechtes Scrollen', a.evaluate('document.documentElement.scrollWidth') <= 390)
    a.set_viewport_size({'width': 1440, 'height': 950}); a.emulate_media(color_scheme='dark')
    a.click('#view-rollen .rl-item:has-text("Personalstelle")'); a.wait_for_selector('#view-rollen .rl-item.on:has-text("Personalstelle")')
    a.screenshot(path=SH + '/rollen-dunkel.png')
    a.close()
    # Lager: Bestand ja, HR-Seite gesperrt, Dashboard nur mit Bestand
    lp = seite('lars', 'Lager-Zugang-551')
    lp.wait_for_selector('#screen-editor:not([hidden])')
    check('UI Lager: nur Bestand in der Seitenleiste', lp.is_visible('#vt-stock') and not lp.is_visible('#vt-hist') and not lp.is_visible('#vt-rollen'))
    lp.goto(B + '/dashboard/'); lp.wait_for_selector('#db-grid .db-tile')
    kach = lp.eval_on_selector_all('#db-grid .db-tile', 'els => els.map(e => e.dataset.modul)')
    check('UI Lager: Dashboard zeigt nur die Kachel Bestand', kach == ['bestand'] and '1 von 1' in lp.inner_text('#db-sub'), kach)
    lp.screenshot(path=SH + '/rollen-dashboard-lager.png')
    lp.goto(B + '/module/hr/'); lp.wait_for_function("() => /Zugang/.test(document.body.innerText)")
    check('UI Lager: HR zeigt „kein Zugang“', 'Bereich „HR“' in lp.inner_text('body') or 'Kein Zugang' in lp.inner_text('body'), lp.inner_text('body')[:200])
    lp.close()
    check('keine Seitenfehler', not fehler, fehler[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
