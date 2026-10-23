"""Einheitliches Erscheinungsbild aller Mitarbeiter-Oberflächen (Dashboard, Eingabebereich auf den Bereichs-Hosts Angebot,
Verwaltung, Bestand, HR, CRM, Abmeldeseite, Hinweis „Kein Zugang“): je hell/dunkel und 1440/390 px

- kein waagerechtes Scrollen, kein abgeschnittener Text (Text breiter als sein Kasten bei verdecktem Überlauf, Text
  außerhalb des Bildschirms) – Ausnahmen nur für bewusst gekürzte Zellen mit vollem Text im Tooltip (title),
- Logo im dunklen Design weiß auf dunklem Grund (keine helle Fläche hinter dem Logo),
- derselbe Zurück-Knopf „Dashboard“ (Maße, Rundung, Schrift, Symbol) auf jeder Modulseite, Ziel = Dashboard,
- Hell/Dunkel gilt für das Konto auf jedem Host: die Wahl wird am Mitarbeiterkonto gespeichert (Aktion theme_save) und
  von jeder Seite nach der Anmeldung übernommen.
Bildschirmfotos: tests/.ergebnisse/einheit-*.png (Bestandsaufnahme für die Durchsicht).
"""
import json
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
# CRM ist noch in Entwicklung: für die Durchsicht als Testfreigabe mit dem Administrator als Tester (Modulverwaltung)
ADMIN = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == 'admin')
check('CRM zur Prüfung freigegeben (Test, Tester Administrator)', A.call('modul_freigabe_save', {'bereich': 'crm.intern', 'freigabe': 'test', 'grund': 'Durchsicht'})[0] == 200
      and A.call('modul_tester_save', {'bereich': 'crm.intern', 'tester': [ADMIN], 'grund': 'Durchsicht'})[0] == 200)

# Abgeschnittener Text: sichtbare Elemente mit eigenem Text, deren Inhalt breiter/höher als der Kasten ist, während der
# Überlauf verdeckt wird (hidden/clip/ellipsis) – oder deren Text über den Bildschirmrand hinausragt.
ABGESCHNITTEN = r'''() => {
  const out = [];
  const W = document.documentElement.clientWidth;
  const sichtbar = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 1 && r.height > 1 && s.clipPath === 'none' && s.clip === 'auto' && s.visibility !== 'hidden' && s.display !== 'none' && !e.closest('[hidden], [aria-hidden="true"], .sr-only, .visually-hidden'); };
  const eigenerText = (e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
  for (const e of document.querySelectorAll('body *')) {
    if (!eigenerText(e) || !sichtbar(e)) continue;
    if (['SCRIPT', 'STYLE', 'OPTION', 'TEXTAREA', 'svg', 'use'].includes(e.tagName)) continue;
    const s = getComputedStyle(e);
    const verdeckt = ['hidden', 'clip'].includes(s.overflowX) || ['hidden', 'clip'].includes(s.overflow) || s.textOverflow === 'ellipsis';
    const name = (e.id ? '#' + e.id : e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).join('.') : '')) + ' „' + e.textContent.trim().slice(0, 40) + '“';
    if (verdeckt && e.scrollWidth > e.clientWidth + 1 && !e.title && !(e.closest('[title]'))) out.push('breite ' + name + ` ${e.scrollWidth}>${e.clientWidth}`);
    if (verdeckt && s.whiteSpace !== 'nowrap' && e.scrollHeight > e.clientHeight + 2 && e.clientHeight > 0 && s.webkitLineClamp === 'none' && !e.title) out.push('hoehe ' + name + ` ${e.scrollHeight}>${e.clientHeight}`);
    const r = document.createRange(); r.selectNodeContents(e); const b = r.getBoundingClientRect();
    // teilweise sichtbar am Rand (ganz außerhalb = eingeklappte Leiste); waagerecht scrollende Leisten laufen weich aus (.stafl-streifen)
    if (b.width && ((b.right > W + 1 && b.left < W) || (b.left < -1 && b.right > 0)) && !e.closest('.stafl-streifen, [class*="scroll"], .tblwrap, .rm-wrap, table')) out.push('rand ' + name + ` ${Math.round(b.left)}..${Math.round(b.right)}/${W}`);
  }
  return [...new Set(out)].slice(0, 12);
}'''
# Logo: im dunklen Design ohne helle Fläche dahinter und weiß gefärbt (Filter oder weiße Datei)
LOGO = r'''() => [...document.querySelectorAll('img[src*="logo-standard-fleisch"]')].filter((e) => e.getBoundingClientRect().width > 0).map((e) => {
  const s = getComputedStyle(e); return { bg: s.backgroundColor, filter: s.filter, src: e.getAttribute('src').split('/').pop() }; })'''
ZURUECK = r'''() => { const e = document.querySelector('.stafl-zurueck'); if (!e || !e.offsetParent) return null; const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return { h: Math.round(r.height), radius: s.borderTopLeftRadius, font: s.fontSize + ' ' + s.fontWeight, text: e.textContent.trim(), href: e.getAttribute('href'),
           icon: !!e.querySelector('svg use[href="#i-back"]'), pad: s.paddingLeft + ' ' + s.paddingRight }; }'''

with sync_playwright() as pw:
    br = pw.chromium.launch()
    fehler = []

    def neue_seite(breite, dunkel):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, is_mobile=breite < 500, color_scheme='dark' if dunkel else 'light',
                             extra_http_headers={'X-Forwarded-For': '198.51.100.40'}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(f'{pg.url}: {e}'))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    def als_bereich(pg, bereich):
        def umleiten(route):
            r = route.fetch(); j = r.json()
            if j.get('user'):
                j['user'].update({'zentral': True, 'bereich': bereich, 'dashboard': 'https://dashboard-stafl.de/'})
            route.fulfill(response=r, json=j)
        pg.unroute('**/api/?action=status*')
        pg.route('**/api/?action=status*', umleiten)

    SEITEN = [('dashboard', None, '/dashboard/', '#db-grid .db-tile', []),
              ('angebot', 'angebot.eingabe', '/admin/', '#screen-editor:not([hidden]) tr[data-id]', ['edit', 'hist', 'einzel', 'orders', 'einkauf']),
              ('verwaltung', 'verwaltung.verwaltung', '/admin/', '#screen-editor:not([hidden])', ['master', 'kunden', 'users', 'rollen', 'log', 'sec']),
              ('bestand', 'bestand.intern', '/admin/', '#view-stock:not([hidden])', ['stock']),
              ('hr', None, '/module/hr/', '#hr-app:not([hidden])', []),
              ('crm', None, '/module/crm/', '#crm-app:not([hidden])', [])]
    zurueck = {}
    for breite in (1440, 390):
        for dunkel in (False, True):
            ctx, pg = neue_seite(breite, dunkel)
            tag = f'{"dunkel" if dunkel else "hell"}-{breite}'
            for name, bereich, pfad, warte, ansichten in SEITEN:
                if bereich: als_bereich(pg, bereich)
                pg.goto(B + pfad); pg.wait_for_selector(warte, timeout=20000)
                for v in (ansichten or [None]):
                    if v:
                        pg.evaluate("v => { const b = document.querySelector('#vt-' + v); if (b && !b.hidden) b.click(); }", v)
                        pg.wait_for_selector(f'#view-{v}:not([hidden])', timeout=20000)
                        pg.wait_for_function("() => !document.querySelector('.adm-page .loading:not([hidden])')", timeout=20000)
                    teil = f'{name}{"-" + v if v else ""}'
                    pg.screenshot(path=f'{SH}/einheit-{teil}-{tag}.png')
                    weg = pg.evaluate(ABGESCHNITTEN)
                    check(f'{teil} {tag}: kein abgeschnittener Text', not weg, weg)
                    check(f'{teil} {tag}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth') <= breite)
                    if dunkel:
                        lg = pg.evaluate(LOGO)
                        check(f'{teil} {tag}: Logo weiß ohne helle Fläche', lg and all(x['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and ('invert' in x['filter'] or 'weiss' in x['src']) for x in lg), lg)
                zr = pg.evaluate(ZURUECK)
                if name != 'dashboard':
                    zurueck.setdefault(breite, {})[name] = zr
                    check(f'{name} {tag}: Zurück-Knopf zum Dashboard sichtbar', zr is not None and zr['icon'] and zr['href'] and (zr['href'].rstrip('/').endswith('dashboard') or zr['href'] == 'https://dashboard-stafl.de/'), zr)
            ctx.close()
    # Seiten ohne Mitarbeiteranmeldung: Abmeldeseite, Kundenseite, Rechtsseiten – Logo im Dunkeln weiß, nichts abgeschnitten
    for breite in (1440, 390):
        for dunkel in (False, True):
            ctx = br.new_context(viewport={'width': breite, 'height': 900}, is_mobile=breite < 500, color_scheme='dark' if dunkel else 'light',
                                 extra_http_headers={'X-Forwarded-For': '198.51.100.41'}, locale='de-DE')
            pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(f'{pg.url}: {e}'))
            tag = f'{"dunkel" if dunkel else "hell"}-{breite}'
            for name, pfad, warte in (('abgemeldet', '/dashboard/abgemeldet.html', 'img.brand-logo'), ('kundenseite', '/', '.brand-logo'),
                                      ('kontakt', '/kontakt/', '.legal-logo')):
                pg.goto(B + pfad); pg.wait_for_selector(warte)
                pg.screenshot(path=f'{SH}/einheit-{name}-{tag}.png')
                weg = pg.evaluate(ABGESCHNITTEN)
                check(f'{name} {tag}: kein abgeschnittener Text', not weg, weg)
                check(f'{name} {tag}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth') <= breite)
                if dunkel:
                    lg = pg.evaluate(LOGO)
                    check(f'{name} {tag}: Logo weiß ohne helle Fläche', lg and all(x['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and 'invert' in x['filter'] for x in lg), lg)
            ctx.close()
    # Hell/Dunkel am Konto: Wahl auf dem Dashboard gilt auch in einem Browser ohne gespeicherte Wahl (wie ein anderer Host)
    ctx, pg = neue_seite(1280, False)
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    with pg.expect_response(lambda r: 'action=theme_save' in r.url) as antwort:
        pg.click('#db-theme')
    check('Dashboard: Wechsel auf dunkel wird am Konto gespeichert', antwort.value.status == 200 and A.call('status')[1]['user'].get('theme') == 'dark', antwort.value.status)
    ctx.close()
    ctx, pg = neue_seite(1280, False)   # frischer Browser, Gerät hell
    pg.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
    check('Eingabebereich übernimmt Dunkel vom Konto', pg.evaluate("getComputedStyle(document.querySelector('#topbar .brand-logo')).filter").startswith('brightness(0)'))
    pg.evaluate('localStorage.clear()')
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-app:not([hidden])')
    pg.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
    check('HR übernimmt Dunkel vom Konto (ohne gespeicherte Wahl im Browser)', pg.get_attribute('#hr-theme', 'aria-label') == 'Helles Design einschalten')
    with pg.expect_response(lambda r: 'action=theme_save' in r.url) as antwort:
        pg.click('#hr-theme')
    check('HR: Wechsel auf hell am Konto gespeichert', antwort.value.status == 200 and A.call('status')[1]['user'].get('theme') == 'light')
    pg.evaluate('localStorage.clear()')
    pg.goto(B + '/module/crm/'); pg.wait_for_selector('#crm-app:not([hidden])')
    pg.wait_for_function("() => document.documentElement.dataset.theme === 'light'")
    check('CRM übernimmt Hell vom Konto', pg.get_attribute('#crm-theme', 'aria-label') == 'Dunkles Design einschalten')
    ctx.close()
    check('Ungültige Darstellung abgewiesen', A.call('theme_save', {'theme': 'pink'})[0] == 422)
    check('Ohne Anmeldung nicht speicherbar', Client('198.51.100.77').call('theme_save', {'theme': 'dark'})[0] in (401, 403))
    check('Zurück auf „wie das Gerät“', A.call('theme_save', {'theme': ''})[0] == 200 and A.call('status')[1]['user'].get('theme') == '')
    for breite, je in zurueck.items():
        # gleiche Form: Höhe, Rundung, Schrift, Pfeil (die Beschriftung kann bei voller Kopfzeile – Angebot – nur für Screenreader sein)
        formen = {json.dumps({k: v for k, v in (z or {}).items() if k in ('h', 'radius', 'font', 'icon', 'text')}, sort_keys=True) for z in je.values()}
        check(f'{breite} px: Zurück-Knopf auf allen Modulseiten gleich', len(formen) == 1, je)
    check('keine Seitenfehler', not fehler, fehler[:4])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
