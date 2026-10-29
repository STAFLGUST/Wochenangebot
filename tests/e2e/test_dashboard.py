"""Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6): Kacheln aus dem Modulregister, Status, Wartung, Abmeldung,
Gestaltung „Liquid Glass“ (Glasflächen, Begrüßung, Absperrband für nicht nutzbare Anwendungen, hell/dunkel, 390 px).

Das Dashboard liegt noch außerhalb der Dokumentwurzel (wird nicht produktiv ausgeliefert); der Testlauf blendet es nur für
diese Gruppe unter /dashboard/ ein. Die Kachel ist nur Anzeige – die Sperre setzt der Server durch (GR-102, GR-103).
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
A.call('user_save', {'id': '', 'name': 'Erika Editor', 'username': 'erika', 'role': 'editor', 'active': True, 'password': 'Editor-Zugang-77', 'mustChange': False})
# Anwendungen in der Reihenfolge des Registers, danach der Bereich „Verwaltung & Daten“ (dashboard_gruppe)
REIHE = ['angebot', 'bestand', 'leergut', 'crm', 'rewe', 'qs', 'einkauf', 'containerimport', 'hr', 'marketing', 'controlling', 'import', 'verwaltung', 'sicherheit']
fehler = []


BERLIN = ZoneInfo('Europe/Berlin')


def anmelden(br, user, pw, ip, breite=1280, dunkel=False, uhr=None):
    ctx = br.new_context(viewport={'width': breite, 'height': 900}, color_scheme='dark' if dunkel else 'light',
                         extra_http_headers={'X-Forwarded-For': ip}, timezone_id='Europe/Berlin', locale='de-DE')
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
    pg.wait_for_selector('#screen-auth', state='hidden')
    if uhr:   # feste Uhrzeit nur für das Dashboard (Begrüßung, Datum); Zeitgeber laufen weiter
        pg.clock.set_fixed_time(uhr)
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    return ctx, pg


def kacheln(pg):
    return pg.eval_on_selector_all('#db-bereich .db-tile', '''els => els.map(e => ({id: e.dataset.modul, tag: e.tagName, href: e.getAttribute('href'),
        name: e.querySelector('.db-name').textContent, badge: e.querySelector('.db-badge').textContent, badgeCls: e.querySelector('.db-badge').className,
        band: (e.querySelector('.db-band') || {}).textContent || '', bandVersteckt: (e.querySelector('.db-band') || {getAttribute: () => null}).getAttribute('aria-hidden'),
        gesperrt: e.classList.contains('gesperrt'), symbol: e.querySelector('.db-ico').dataset.symbol,
        hint: (e.querySelector('.db-hint') || {}).textContent || '', bilder: e.querySelectorAll('.db-hint img').length}))''')


# Kontrast Text ↔ Untergrund: halbtransparente Flächen (Glas, Pillen) werden bis zum deckenden Seitengrund verrechnet.
# Die weichen Farbflächen im Hintergrund (Deckkraft ≤ .22, stark unscharf) bleiben unberücksichtigt.
KONTRAST = '''(sels) => {
  const rgba = (s) => { const m = s.match(/[\\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
  const ueber = (o, u) => [0, 1, 2].map((i) => o[i] * o[3] + u[i] * (1 - o[3])).concat(1);
  const grund = (el) => { const s = []; for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c[3] > 0) s.push(c); if (c[3] >= 1) break; }
    return s.reverse().reduce((u, o) => ueber(o, u), [255, 255, 255, 1]); };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  return sels.map((s) => { const el = document.querySelector(s); if (!el) return [s, 0];
    const g = grund(el), t = ueber(rgba(getComputedStyle(el).color), g), [h, d] = [lum(t), lum(g)].sort((x, y) => y - x);
    return [s, Math.round((h + .05) / (d + .05) * 100) / 100]; });
}'''
TEXTE = ['#db-datum', '#db-titel', '#db-sub', '[data-modul="angebot"] .db-name', '[data-modul="angebot"] .db-desc',
         '[data-modul="angebot"] .db-badge', '.db-band > span', '#db-initialen', '#db-user-name', '#db-logout']


def kontrast_ok(pg, name):
    werte = pg.evaluate(KONTRAST, TEXTE)
    check(f'{name}: Textkontrast mindestens 4,5:1 (auch auf Glas)', all(w >= 4.5 for _, w in werte), werte)


# Abstand des gedrehten Absperrbands zu Name und Status-Pille je gesperrter Kachel (px; < 0 = verdeckt). Gemessen an den
# Ecken der Textzeilen bzw. der Pille gegen die Mittellinie des Bandes. Pille am Handy nur für Screenreader → None.
BAND_ABSTAND = """[...document.querySelectorAll('#db-bereich .gesperrt')].map(t => {
  const band = t.querySelector('.db-band'), r = band.getBoundingClientRect(), m = new DOMMatrix(getComputedStyle(band).transform);
  const w = Math.atan2(m.b, m.a), cx = r.left + r.width / 2, cy = r.top + r.height / 2, halb = band.offsetHeight / 2;
  const abst = (q) => { const d = q.flatMap(z => [[z.left, z.top], [z.right, z.top], [z.left, z.bottom], [z.right, z.bottom]])
      .map(([x, y]) => -(x - cx) * Math.sin(w) + (y - cy) * Math.cos(w));
    return Math.round(Math.max(Math.min(...d) - halb, -Math.max(...d) - halb)); };
  const n = document.createRange(); n.selectNodeContents(t.querySelector('.db-name'));
  const fuss = t.querySelector('.db-foot').getBoundingClientRect();
  return [t.dataset.modul, abst([...n.getClientRects()]), fuss.width > 2 ? abst([t.querySelector('.db-badge').getBoundingClientRect()]) : null]; })"""
# Wörter, die über eine Zeile hinaus umbrechen (mitten im Wort getrennt), je Kachelname; Notlösung (db-name-umbruch) getrennt
WORT_GETRENNT = """[...document.querySelectorAll('#db-bereich .db-name')].map(e => {
  const t = e.firstChild, text = t ? t.textContent : '', getrennt = [];
  for (const m of text.matchAll(/\\S+/g)) { const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
    if (new Set([...r.getClientRects()].map(q => Math.round(q.top))).size > 1) getrennt.push(m[0]); }
  return [e.textContent, getrennt, e.classList.contains('db-name-umbruch'), parseFloat(getComputedStyle(e).fontSize), getComputedStyle(e).hyphens]; })"""


def bilder(pg):   # auf zwei Bilder warten: ResizeObserver und Neuberechnung nach einer Größenänderung
    pg.wait_for_function("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))")


def band_frei(pg, name):
    werte = pg.evaluate(BAND_ABSTAND)
    check(f'{name}: Absperrband verdeckt weder Namen noch Status-Pille', werte and all(n >= 0 and (p is None or p >= 0) for _, n, p in werte), werte)


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ── Ohne Anmeldung: Hinweis auf die Anmeldung, keine Kacheln ──
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis sichtbar, Kachelbereich verborgen', pg.is_hidden('#db-bereich') and pg.is_hidden('#db-logout'))
    check('Anmeldehinweis führt zur Mitarbeiter-Anmeldung', (pg.get_attribute('#db-login a', 'href') or '').endswith('/admin/'), pg.get_attribute('#db-login a', 'href'))
    check('keine Kacheln ohne Anmeldung', pg.locator('#db-grid .db-tile').count() == 0)
    knopf = pg.evaluate("[document.querySelector('.db-login-i').getBoundingClientRect().width, getComputedStyle(document.querySelector('#db-login a')).textDecorationLine]")
    check('Anmeldehinweis: Schloss-Symbol 30 px, Knopf ohne Unterstreichung', knopf == [30, 'none'], knopf)
    ctx.close()

    # ── Administrator: vierzehn Kacheln aus dem Register ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.41')
    k = kacheln(pg)
    check('vierzehn Kacheln in der Reihenfolge des Modulregisters, Verwaltung & Daten zuletzt', [x['id'] for x in k] == REIHE, [x['id'] for x in k])
    bereiche = pg.evaluate("""[[...document.querySelectorAll('#db-grid .db-tile')].map(t => t.dataset.modul),
        [...document.querySelectorAll('#db-grid-verwaltung .db-tile')].map(t => t.dataset.modul), document.querySelector('#db-verwaltung-titel').textContent,
        document.querySelector('#db-verwaltung').getBoundingClientRect().top > Math.max(...[...document.querySelectorAll('#db-grid .db-tile')].map(t => t.getBoundingClientRect().bottom)),
        [...document.querySelectorAll('#db-grid-verwaltung .db-tile')].every(t => t.classList.contains('db-breit') && getComputedStyle(t).flexDirection === 'row')]""")
    check('Import, Verwaltung und Sicherheit abgesetzt im eigenen Bereich „Verwaltung & Daten“ unter den Anwendungen, breite Kacheln (Symbol links)',
          bereiche[0] == REIHE[:-3] and bereiche[1] == ['import', 'verwaltung', 'sicherheit'] and bereiche[2] == 'Verwaltung & Daten' and bereiche[3] and bereiche[4], bereiche)
    check('Desktop: kein Pfeil in den breiten Kacheln (nur am Handy)', pg.evaluate("[...document.querySelectorAll('.db-pfeil')].every(e => getComputedStyle(e).display === 'none')"))
    check('Kachelnamen aus dem Register', [x['name'] for x in k][:2] == ['Angebot', 'Bestand'], [x['name'] for x in k])
    ang = k[0]
    check('Angebot: verfügbar, als Verweis auf die Mitarbeiter-Eingabe (Testserver: gleicher Host)', ang['tag'] == 'A' and ang['href'] == '/admin/' and ang['badge'] == 'Verfügbar', ang)
    kid = {x['id']: x for x in k}
    verw = kid['verwaltung']
    check('Verwaltung: freigegeben (Roadmap 10a), Verweis auf den Eingabebereich (Testserver: gleicher Host, Pfad /admin/)',
          verw['tag'] == 'A' and verw['href'] == '/admin/' and verw['badge'] == 'Verfügbar', verw)
    best = kid['bestand']
    check('Bestand: freigegeben (Phase 1), Verweis auf den Eingabebereich (Testserver: gleicher Host, Pfad /admin/)',
          best['tag'] == 'A' and best['href'] == '/admin/' and best['badge'] == 'Verfügbar', best)
    imp = kid['import']
    check('Import: freigegeben, Verweis auf /import/ (Testserver: gleicher Host)', imp['tag'] == 'A' and imp['href'] == '/import/' and imp['badge'] == 'Verfügbar', imp)
    hr = kid['hr']
    check('HR: freigegeben (Inhaber 23.10.2026), Verweis auf die Urlaubsverwaltung (Testserver: gleicher Host, Pfad /module/hr/)',
          hr['tag'] == 'A' and hr['href'] == '/module/hr/' and hr['badge'] == 'Verfügbar', hr)
    crm = kid['crm']
    check('CRM: freigegeben (Inhaber 23.10.2026), Verweis auf das CRM (Testserver: gleicher Host, Pfad /module/crm/)',
          crm['tag'] == 'A' and crm['href'] == '/module/crm/' and crm['badge'] == 'Verfügbar', crm)
    mkt = kid['marketing']
    check('Marketing: freigegeben (Inhaber 25.10.2026), Verweis auf den Redaktionsplan (Testserver: gleicher Host, Pfad /module/marketing/)',
          mkt['tag'] == 'A' and mkt['href'] == '/module/marketing/' and mkt['badge'] == 'Verfügbar', mkt)
    neu2 = [kid[m] for m in ('leergut', 'containerimport')]
    check('neue Kacheln Leergut (freigegeben, Auftrag des Inhabers 29.10.2026 – führt zu /module/leergut/) und Container-Import (geplant, gesperrt mit Band): Name aus dem Register, eigene Symbole',
          [x['name'] for x in neu2] == ['Leergut', 'Container-Import'] and [x['badge'] for x in neu2] == ['Verfügbar', 'Geplant']
          and neu2[0]['tag'] == 'A' and neu2[0]['href'] == '/module/leergut/' and neu2[1]['tag'] == 'DIV' and neu2[1]['gesperrt']
          and [x['symbol'] for x in neu2] == ['crate', 'container'], neu2)
    sym2 = pg.eval_on_selector_all('[data-modul="leergut"] use, [data-modul="containerimport"] use', 'e => e.map(x => [x.getAttribute("href"), !!document.querySelector(x.getAttribute("href"))])')
    check('Symbole Kiste und Container vorhanden', [x[0] for x in sym2] == ['#i-kiste', '#i-container'] and all(x[1] for x in sym2), sym2)
    offen = [kid[m] for m in ('rewe', 'qs', 'einkauf', 'containerimport')]
    gesperrt = [x for x in offen if x['tag'] != 'DIV' or x['href']]
    check('alle anderen Kacheln ohne Verweis (nicht freigegeben)', not gesperrt, gesperrt)
    check('nicht freigegebene Module zeigen ihren Entwicklungsstand', all(x['badge'] in ('Geplant', 'In Entwicklung', 'In Prüfung', 'In Vorbereitung') for x in offen), [x['badge'] for x in k])
    check('gesperrte Kacheln als deaktiviert gekennzeichnet', pg.locator('#db-grid .db-tile.off[aria-disabled="true"]').count() == 4)
    check('Zähler: 10 von 14 Anwendungen', '10 von 14' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    sic = kid['sicherheit']
    check('Sicherheit: freigegeben (Inhaber 26.10.2026), rechts neben der Verwaltung, Verweis auf die Sicherheitszentrale, eigenes Symbol',
          sic['tag'] == 'A' and sic['href'] == '/module/sicherheit/' and sic['badge'] == 'Verfügbar' and sic['symbol'] == 'shield-lock'
          and pg.evaluate("!!document.querySelector('#i-schild') && document.querySelector('[data-modul=\"sicherheit\"] use').getAttribute('href') === '#i-schild'"), sic)
    neu = [kid[m] for m in ('hr', 'marketing', 'controlling')]
    check('neue Module HR, Marketing, Controlling: Name aus dem Register, verfügbar; Controlling (Inhaber 28.10.2026) führt zu /module/controlling/',
          [x['name'] for x in neu] == ['HR', 'Marketing', 'Controlling'] and neu[2]['tag'] == 'A' and neu[2]['href'] == '/module/controlling/'
          and [x['badge'] for x in neu] == ['Verfügbar', 'Verfügbar', 'Verfügbar'], neu)
    sym = pg.eval_on_selector_all('#db-grid .db-tile[data-modul="hr"] use, #db-grid .db-tile[data-modul="marketing"] use, #db-grid .db-tile[data-modul="controlling"] use',
                                  'e => e.map(x => [x.getAttribute("href"), !!document.querySelector(x.getAttribute("href"))])')
    check('eigene Symbole (Kalender, Megafon, Diagramm), vorhanden', [x[0] for x in sym] == ['#i-calendar', '#i-megaphone', '#i-chart'] and all(x[1] for x in sym), sym)
    check('Name des angemeldeten Nutzers im Kopf', 'Angemeldet als' in pg.text_content('#db-user') and pg.text_content('#db-user-name') == 'Administrator', pg.text_content('#db-user'))
    check('Nutzer-Chip mit Initialen', pg.text_content('#db-initialen') == 'AD', pg.text_content('#db-initialen'))
    gesperrt = [x for x in k if x['tag'] == 'DIV']
    check('Absperrband auf jeder nicht nutzbaren Kachel (Text „Im Bau · Bald verfügbar“, nur Anzeige)',
          len(gesperrt) == 4 and all(x['gesperrt'] and 'Im Bau' in x['band'] and 'Bald verfügbar' in x['band'] and x['bandVersteckt'] == 'true' for x in gesperrt), gesperrt)
    check('kein Absperrband auf verfügbaren Kacheln', all(not x['band'] and not x['gesperrt'] for x in k if x['tag'] == 'A'))
    check('Status-Pille „Verfügbar“ grün markiert', all('ok' in x['badgeCls'] for x in k if x['badge'] == 'Verfügbar'))
    band = pg.evaluate("""(() => { const s = getComputedStyle(document.querySelector('.db-band > span')), b = getComputedStyle(document.querySelector('.db-band'));
        return [s.backgroundColor, s.textTransform, b.transform !== 'none', b.backgroundImage.includes('repeating-linear-gradient')]; })()""")
    check('Absperrband zurückhaltend (blasses Sandgelb wie der Grund, gestreift), Großbuchstaben, gedreht, ohne Schatten', band == ['rgb(239, 229, 200)', 'uppercase', True, True]
          and pg.evaluate("getComputedStyle(document.querySelector('.db-band')).boxShadow") == 'none', band)
    blass = pg.evaluate("[getComputedStyle(document.querySelector('.gesperrt .db-text')).opacity, getComputedStyle(document.querySelector('a.db-tile .db-text')).opacity]")
    check('gesperrte Kacheln blass, verfügbare in voller Stärke', blass == ['0.55', '1'], blass)
    check('Symbolfarbe je Registersymbol (Angebot: tag, Verwaltung: settings)', k[0]['symbol'] == 'tag' and kid['verwaltung']['symbol'] == 'settings', [x['symbol'] for x in k])
    glas = pg.evaluate("""[...document.querySelectorAll('.db-kopf, a.db-tile')].map(e => { const s = getComputedStyle(e);
        return (s.backdropFilter || s.webkitBackdropFilter || '').includes('blur(28px)') && s.backgroundColor.startsWith('rgba'); })""")
    check('Kopfzeile und Kacheln als Glasflächen (halbtransparent, unscharf)', glas and all(glas), glas)
    form = pg.evaluate("[getComputedStyle(document.querySelector('.db-kopf')).borderTopLeftRadius, getComputedStyle(document.querySelector('.db-tile')).borderTopLeftRadius]")
    check('Kopfzeile als Kapsel, Kacheln mit 28 px Radius', form[0] in ('999px', '9.99e+02px') and form[1] == '28px', form)
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('heller Grund #f4f1ee', hg == 'rgb(244, 241, 238)', hg)
    ueberlauf = pg.evaluate("[...document.querySelectorAll('.db-name')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)")
    check('Kachelnamen passen in die Kachel (lange Registernamen brechen um)', not ueberlauf, ueberlauf)
    check('Schrift Geist (selbst gehostet)', 'Geist' in pg.evaluate("getComputedStyle(document.querySelector('#db-titel')).fontFamily"))
    kontrast_ok(pg, 'hell')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280.png'), full_page=True)
    # Gemeldet: „Qualitätssicherungskon-zept“ – Namen werden nicht mehr automatisch getrennt, Band lässt Name und Pille frei
    for breite in (1920, 1280, 1024, 768, 575, 390, 360):
        pg.set_viewport_size({'width': breite, 'height': 900}); bilder(pg)
        namen = pg.evaluate(WORT_GETRENNT)
        check(f'{breite} px: Registernamen ohne Silbentrennung und ohne Umbruch im Wort (auch „Qualitätssicherung“)',
              all(not g and not u and h != 'auto' for _, g, u, _f, h in namen), namen)
        band_frei(pg, f'{breite} px')
    pg.set_viewport_size({'width': 1280, 'height': 900}); bilder(pg)
    echt = pg.evaluate("""fetch('../api/?action=module_status').then(r => r.json()).then(d => {
        const alle = Object.fromEntries(d.module.map((m) => [m.id, m]));
        return ['angebot', 'verwaltung', 'bestand', 'import', 'hr'].map((id) => [window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'dashboard-stafl.de'),
                                                      window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'angebot.stafl.test')]); })""")
    check('Echtbetrieb (dashboard-stafl.de): Kacheln führen zu den Hosts der zentralen Anmeldung, nicht zum bisherigen /admin/',
          echt == [['https://angebot.dashboard-stafl.de/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/admin/', '/admin/'],
                   ['https://bestand.dashboard-stafl.de/admin/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/import/', '/import/'],
                   ['https://hr.dashboard-stafl.de/module/hr/', '/module/hr/']], echt)
    pg.click('#db-grid a[data-modul="angebot"]'); pg.wait_for_url('**/admin/')
    check('Klick auf Angebot öffnet die Mitarbeiter-Eingabe', pg.url.endswith('/admin/'))
    ctx.close()

    # ── Überlange Registernamen (nachgestellte Antwort): erst kleinere Schrift, Trennung nur als Notlösung ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.47')
    def lange_namen(route):
        r = route.fetch(); d = r.json()
        for m in d['module']:
            if m['id'] == 'qs': m['name'] = 'Qualitätssicherungskonzept'
            if m['id'] == 'crm': m['name'] = 'Kundenbeziehungsmanagement'
        route.fulfill(response=r, body=json.dumps(d))
    pg.route('**/api/?action=module_status', lange_namen); pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    for breite in (1280, 1024, 575, 390):
        pg.set_viewport_size({'width': breite, 'height': 900}); bilder(pg)
        namen = pg.evaluate(WORT_GETRENNT)
        lang = [x for x in namen if x[0] in ('Qualitätssicherungskonzept', 'Kundenbeziehungsmanagement')]
        if breite > 560:
            check(f'{breite} px: überlange Namen in einer Zeile, nicht getrennt (Schrift höchstens 19 px)',
                  len(lang) == 2 and all(not g and not u and f <= 19 for _, g, u, f, _h in lang), lang)
        if breite == 1280:
            check('1280 px: zu lange Namen mit kleinerer Schrift statt Trennung', any(f < 19 for *_x, f, _h in lang), lang)
        check(f'{breite} px: kurze Namen behalten ihre Schriftgröße', all(f == (19 if breite > 560 else 16) for n, _g, _u, f, _h in namen if n in ('Angebot', 'REWE')), namen)
        band_frei(pg, f'{breite} px, überlange Namen')
        ueber = pg.evaluate("[...document.querySelectorAll('.db-name')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)")
        check(f'{breite} px: überlange Namen ragen nicht aus der Kachel', not ueber, ueber)
    namen = pg.evaluate(WORT_GETRENNT)   # 390 px: zwei Spalten, 26 Zeichen passen auch mit 12 px nicht
    lang = [x for x in namen if x[0] in ('Qualitätssicherungskonzept', 'Kundenbeziehungsmanagement')]
    check('390 px: passt ein Wort auch in kleinster Schrift nicht, bricht es als Notlösung um (12 px, ohne Überlauf)',
          all(u and f == 12 for _, _g, u, f, _h in lang) and not pg.evaluate("[...document.querySelectorAll('.db-name')].some(e => e.scrollWidth > e.clientWidth + 1)"), lang)
    band_frei(pg, '390 px, überlange Namen')
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_lange_namen.png'), full_page=True)
    hoehen = pg.evaluate("[...document.querySelectorAll('#db-grid .db-tile')].map(t => Math.round(t.getBoundingClientRect().top) + ':' + Math.round(t.getBoundingClientRect().height))")
    reihen = {}
    for h in hoehen: reihen.setdefault(h.split(':')[0], set()).add(h.split(':')[1])
    check('Kacheln einer Reihe gleich hoch (auch wenn eine Kachel für das Band höher wird)', all(len(v) == 1 for v in reihen.values()), hoehen)
    ctx.close()

    # ── Begrüßung nach Tageszeit und Datum (feste Uhr, Europe/Berlin), dunkles Design am Desktop ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.46', dunkel=True, uhr=datetime(2026, 10, 22, 19, 30, tzinfo=BERLIN))
    check('Datum deutsch ausgeschrieben', pg.text_content('#db-datum') == 'Donnerstag, 22. Oktober', pg.text_content('#db-datum'))
    check('abends: „Guten Abend“ als Hauptüberschrift', pg.text_content('#db-titel') == 'Guten Abend' and pg.evaluate("document.querySelector('#db-titel').tagName") == 'H1')
    grenzen = pg.evaluate("[0, 4, 5, 10, 11, 17, 18, 23].map((h) => window.STAFL_GRUSS(h))")
    check('Begrüßung: Grenzen 5/11/18 Uhr', grenzen == ['Guten Abend', 'Guten Abend', 'Guten Morgen', 'Guten Morgen', 'Guten Tag', 'Guten Tag', 'Guten Abend', 'Guten Abend'], grenzen)
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design folgt der Systemeinstellung (Grund #121011)', hg == 'rgb(18, 16, 17)', hg)
    kontrast_ok(pg, 'dunkel')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_dunkel.png'), full_page=True)
    pg.clock.set_fixed_time(datetime(2026, 10, 23, 8, 15, tzinfo=BERLIN)); pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('morgens: „Guten Morgen“, Datum des Tages', pg.text_content('#db-titel') == 'Guten Morgen' and pg.text_content('#db-datum') == 'Freitag, 23. Oktober',
          (pg.text_content('#db-titel'), pg.text_content('#db-datum')))
    # Weniger Transparenz (Systemeinstellung): deckende Flächen statt Glas
    cdp = ctx.new_cdp_session(pg)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-transparency', 'value': 'reduce'}]})
    pg.wait_for_function("getComputedStyle(document.querySelector('.db-tile')).backdropFilter === 'none'")
    deckend = pg.evaluate("[...document.querySelectorAll('.db-kopf, .db-tile')].map(e => getComputedStyle(e).backgroundColor)")
    check('weniger Transparenz: deckende Flächen, kein Glas', all(c.startswith('rgb(') for c in deckend), deckend)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
    pg.wait_for_function("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration === '0s'")
    check('weniger Bewegung: keine Übergänge an den Kacheln', pg.evaluate("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration") == '0s')
    ctx.close()

    # ── Mobil (390 px) und dunkles Design ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.42', breite=390, dunkel=True)
    breiter = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    check('390 px: kein waagerechtes Scrollen', not breiter)
    kopf = pg.evaluate("""(() => { const t = document.querySelector('.db-kopf').getBoundingClientRect();
        return [...document.querySelectorAll('.db-kopf img, .db-kopf button, .db-initialen')].every(e => { const r = e.getBoundingClientRect(); return r.left >= t.left - 1 && r.right <= t.right + 1; }); })()""")
    check('390 px: Kopfzeile passt in die Breite', kopf)
    sichtbar = pg.evaluate("['#db-theme', '#db-logout', '#db-initialen'].map((s) => document.querySelector(s).getBoundingClientRect().width > 0)")
    abm = pg.evaluate("[document.querySelector('#db-logout').textContent.trim(), document.querySelector('#db-logout').getBoundingClientRect().width]")
    check('390 px: Hell/Dunkel, Initialen und Abmelden erreichbar (Abmelden als Symbol mit Text für Screenreader)', all(sichtbar) and abm[0] == 'Abmelden' and abm[1] <= 44, (sichtbar, abm))
    spalten = pg.evaluate("getComputedStyle(document.querySelector('#db-grid')).gridTemplateColumns.split(' ').length")
    check('390 px: zwei Kachelspalten', spalten == 2, spalten)
    breit = pg.evaluate("""[getComputedStyle(document.querySelector('#db-grid-verwaltung')).gridTemplateColumns.split(' ').length,
        [...document.querySelectorAll('#db-grid-verwaltung a.db-breit')].map(t => [getComputedStyle(t.querySelector('.db-pfeil')).display !== 'none',
          t.querySelector('.db-foot').getBoundingClientRect().width < 2, t.querySelector('.db-badge').textContent])]""")
    check('390 px: Verwaltung & Daten einspaltig, Pfeil statt grüner Pille (Stand bleibt für Screenreader)', breit[0] == 1 and len(breit[1]) == 3
          and all(p and f and b == 'Verfügbar' for p, f, b in breit[1]), breit)
    gross = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#db-titel')).fontSize)")
    check('390 px: große Überschrift (34 px)', gross == 34, gross)
    ueberlauf = pg.evaluate("[...document.querySelectorAll('.db-name')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)")
    check('390 px: Kachelnamen passen in die Kachel', not ueberlauf, ueberlauf)
    # Abstand der Ecken des Namenstextes zur gedrehten Mittellinie des Bandes (Rechteck des Bandes allein wäre zu grob)
    verdeckt = pg.evaluate("""[...document.querySelectorAll('.gesperrt')].filter(t => {
        const band = t.querySelector('.db-band'), r = band.getBoundingClientRect(), m = new DOMMatrix(getComputedStyle(band).transform);
        const w = Math.atan2(m.b, m.a), cx = r.left + r.width / 2, cy = r.top + r.height / 2, halb = band.offsetHeight / 2;
        const bereich = document.createRange(); bereich.selectNodeContents(t.querySelector('.db-name'));
        const d = [...bereich.getClientRects()].flatMap(q => [[q.left, q.top], [q.right, q.top], [q.left, q.bottom], [q.right, q.bottom]])
          .map(([x, y]) => -(x - cx) * Math.sin(w) + (y - cy) * Math.cos(w));
        return Math.max(...d) > -halb && Math.min(...d) < halb; }).map(t => t.dataset.modul)""")
    check('390 px: Absperrband verdeckt die Kachelnamen nicht', not verdeckt, verdeckt)
    check('390 px: Stand gesperrter Kacheln bleibt für Screenreader im Text', all(x['badge'] for x in kacheln(pg)))
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design folgt der Systemeinstellung', hg == 'rgb(18, 16, 17)', hg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_dunkel.png'), full_page=True)
    pg.click('#db-theme'); pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'")
    gespeichert = pg.evaluate("localStorage.getItem('wochenangebot.theme')")
    check('Umschalter speichert das Design wie die Angebotsseite', json.loads(gespeichert or 'null') == 'light', gespeichert)
    pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('gewähltes Design bleibt nach dem Neuladen', pg.evaluate("document.documentElement.getAttribute('data-theme')") == 'light')
    check('helles Design trotz dunkler Systemeinstellung', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(244, 241, 238)')
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_hell.png'), full_page=True)
    ctx.close()

    # ── Wartung des Eingabebereichs: Bearbeiter gesperrt, Administrator mit Hinweis ──
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Dashboard',
                                          'message': 'Kurz weg <img src=x onerror="window.__xss=1"> Infos: https://angebot-stafl.de/hinweise/wartungsfenster-oktober-2026'})
    check('Wartung des Eingabebereichs gestartet', st == 200 and r.get('aktiv') is True, (st, r))
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.43')
    a = kacheln(pg)[0]
    check('Bearbeiter: Angebot in Wartung, ohne Verweis', a['tag'] == 'DIV' and not a['href'] and a['badge'] == 'Wartung', a)
    check('Wartung bleibt eigener Zustand: Wartungs-Pille, kein Absperrband', 'warn' in a['badgeCls'] and not a['band'] and not a['gesperrt'], a)
    check('Bearbeiter: Initialen „EE“', pg.text_content('#db-initialen') == 'EE', pg.text_content('#db-initialen'))
    check('Bearbeiter: Wartungshinweis als Text (kein HTML)', 'Kurz weg <img' in a['hint'] and a['bilder'] == 0 and not pg.evaluate('window.__xss'), a)
    # Controlling: Modulzugang standardmäßig niemand (Finanzdaten, 28.10.2026) – die Kachel fehlt Bearbeitern ganz
    check('Bearbeiter: Bestand, Import, HR, CRM, Marketing, Leergut und Verwaltung weiter verfügbar (7 von 12, ohne Controlling)', '7 von 12' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_bearbeiter.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.44')
    a = kacheln(pg)[0]
    check('Administrator: Angebot in Wartung, aber weiter erreichbar', a['tag'] == 'A' and a['badge'] == 'Wartung – Zugang für Administratoren', a)
    check('Administrator: Wartungs-Pille ohne Absperrband', 'warn' in a['badgeCls'] and not a['band'], a)
    pg.set_viewport_size({'width': 360, 'height': 900}); bilder(pg)
    lage = pg.evaluate("""(() => { const t = document.querySelector('[data-modul="angebot"]'), k = t.getBoundingClientRect(), h = t.querySelector('.db-hint'), p = t.querySelector('.db-badge');
        const pr = p.getBoundingClientRect(), s = getComputedStyle(p);
        return {hinweis: h.scrollWidth <= h.clientWidth + 1 && h.getBoundingClientRect().right <= k.right - 8, pille: pr.right <= k.right - 8 && pr.left >= k.left,
                zeilen: Math.round(pr.height / parseFloat(s.lineHeight)), radius: parseFloat(s.borderTopLeftRadius)}; })()""")
    check('360 px: langer Wartungshinweis (Adresse) bricht innerhalb der Kachel um', lage['hinweis'], lage)
    check('360 px: lange Pille „Wartung – Zugang für Administratoren“ bleibt in der Kachel, mehrzeilig als abgerundetes Feld', lage['pille'] and lage['zeilen'] >= 2 and lage['radius'] <= 13, lage)
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_admin_360.png'), full_page=True)
    ctx.close()
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': 'Test beendet'})
    check('Wartung beendet', st == 200 and r.get('aktiv') is False, (st, r))

    # ── Abmelden beendet die Sitzung serverseitig ──
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.45')
    check('nach der Wartung wieder verfügbar', kacheln(pg)[0]['badge'] == 'Verfügbar')
    pg.click('#db-logout'); pg.wait_for_selector('#db-login:not([hidden])')
    angemeldet = pg.evaluate("fetch('../api/?action=status', {credentials: 'same-origin'}).then(r => r.json()).then(j => j.loggedIn)")
    check('Abmelden: Anmeldehinweis und Sitzung beendet', angemeldet is False and pg.is_hidden('#db-bereich'), angemeldet)
    pg.reload(); pg.wait_for_selector('#db-login:not([hidden])')
    check('nach dem Neuladen weiter abgemeldet', pg.is_hidden('#db-bereich'))
    check('Anmeldehinweis als Glasfläche mit echtem Link', pg.evaluate("getComputedStyle(document.querySelector('#db-login')).backgroundColor").startswith('rgba')
          and pg.evaluate("document.querySelector('#db-login a').tagName") == 'A')
    pg.goto(B + '/dashboard/abgemeldet.html'); pg.wait_for_selector('#db-abgemeldet')
    check('Abmeldeseite im neuen Design (Grund, Glaskarte, Link zur Anmeldung)', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(244, 241, 238)'
          and pg.get_attribute('#db-abgemeldet a', 'href') == './' and not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    check('Abmeldeseite: Knopf „Erneut anmelden“ ohne Unterstreichung', pg.evaluate("getComputedStyle(document.querySelector('#db-abgemeldet a')).textDecorationLine") == 'none')
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
