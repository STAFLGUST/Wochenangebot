"""Mitarbeiter-Dashboard (dashboard/, Roadmap PR 6) im gemeinsamen Rahmen „C2“ (app/assets/rahmen.css, rahmen.js):
Kacheln und Seitenleiste aus dem Modulregister, Stand, Wartung, Abmeldung, Begrüßung, kompakte Kacheln ohne Unterzeile,
Klebeband „Bald“ für nicht freigegebene Anwendungen, schmale Leiste, Menü am Handy, hell/dunkel, 390 px.

Das Dashboard liegt außerhalb der Dokumentwurzel; der Testlauf blendet es nur für diese Gruppe unter /dashboard/ ein. Kachel
und Eintrag der Seitenleiste sind nur Anzeige – die Sperre setzt der Server durch (GR-102, GR-103).
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
FREI = ['angebot', 'bestand', 'leergut', 'crm', 'rewe', 'qs', 'hr', 'marketing', 'controlling']
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
        badgeSichtbar: e.querySelector('.db-badge').getBoundingClientRect().width > 2,
        bald: (e.querySelector('.r-bald') || {}).textContent || '', baldVersteckt: (e.querySelector('.r-bald') || {getAttribute: () => null}).getAttribute('aria-hidden'),
        gesperrt: e.classList.contains('gesperrt'), symbol: e.querySelector('.db-ico').dataset.symbol, svg: !!e.querySelector('.db-ico svg :is(path, rect, circle)'),
        hint: (e.querySelector('.db-hint') || {}).textContent || '', bilder: e.querySelectorAll('.db-hint img').length}))''')


# Seitenleiste: Gruppen mit ihren Einträgen (Modul-ID, Verweis, aktiv, gesperrt, Stand, Klebeband)
LEISTE = '''[...document.querySelectorAll('#r-leiste .r-liste')].map(l => [(l.closest('.r-gruppe') || {querySelector: () => null}).querySelector('.r-gruppe-titel')?.textContent || '',
  [...l.querySelectorAll('.r-eintrag')].map(e => ({id: e.dataset.modul, tag: e.tagName, href: e.getAttribute('href'), aktiv: e.getAttribute('aria-current'),
    aus: e.getAttribute('aria-disabled'), label: e.getAttribute('aria-label'), stand: (e.querySelector('.r-stand') || {}).textContent || '',
    bald: (e.querySelector('.r-bald') || {}).textContent || '', symbol: e.dataset.symbol}))])'''


def leiste(pg):
    return {t: e for t, e in pg.evaluate(LEISTE)}


# Kontrast Text ↔ Untergrund: halbtransparente Flächen werden bis zum deckenden Seitengrund verrechnet.
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
TEXTE = ['#db-datum', '#db-titel', '#db-sub', '#db-apps-titel', '#db-grid [data-modul="angebot"] .db-name', '#db-grid [data-modul="containerimport"] .db-name',
         '#db-grid [data-modul="containerimport"] .db-badge', '#db-grid .r-bald', '#r-leiste .r-gruppe-titel', '#r-leiste [data-modul="angebot"] .r-text',
         '#r-leiste [data-modul="einkauf"] .r-text', '#r-leiste [data-modul="start"] .r-text', '#r-initialen', '#r-nutzer-name', '#r-rolle', '.db-fuss']


def kontrast_ok(pg, name):
    werte = pg.evaluate(KONTRAST, TEXTE)
    check(f'{name}: Textkontrast mindestens 4,5:1 (Seite, Kacheln, Seitenleiste)', all(w >= 4.5 for _, w in werte), werte)


# Wörter, die über eine Zeile hinaus umbrechen (mitten im Wort getrennt), je Kachelname; Notlösung (db-name-umbruch) getrennt
WORT_GETRENNT = """[...document.querySelectorAll('#db-bereich .db-name')].map(e => {
  const t = e.firstChild, text = t ? t.textContent : '', getrennt = [];
  for (const m of text.matchAll(/\\S+/g)) { const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
    if (new Set([...r.getClientRects()].map(q => Math.round(q.top))).size > 1) getrennt.push(m[0]); }
  return [e.textContent, getrennt, e.classList.contains('db-name-umbruch'), parseFloat(getComputedStyle(e).fontSize), getComputedStyle(e).hyphens]; })"""
UEBERLAUF = "[...document.querySelectorAll('.db-name, #r-leiste .r-text')].filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)"


def bilder(pg):   # auf zwei Bilder warten: ResizeObserver und Neuberechnung nach einer Größenänderung
    pg.wait_for_function("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))))")


with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ── Ohne Anmeldung: Hinweis auf die Anmeldung, keine Kacheln, keine Seitenleiste ──
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-login:not([hidden])')
    check('ohne Anmeldung: Anmeldehinweis sichtbar, Kachelbereich und Seitenleiste verborgen', pg.is_hidden('#db-bereich') and pg.is_hidden('#r-leiste')
          and not pg.evaluate("document.querySelector('.r-app').classList.contains('r-bereit')"))
    check('Anmeldehinweis führt zur Mitarbeiter-Anmeldung', (pg.get_attribute('#db-login a', 'href') or '').endswith('/admin/'), pg.get_attribute('#db-login a', 'href'))
    check('keine Kacheln und keine Einträge ohne Anmeldung', pg.locator('#db-grid .db-tile').count() == 0 and pg.locator('#r-leiste .r-eintrag').count() == 0)
    knopf = pg.evaluate("[document.querySelector('.db-login-i').getBoundingClientRect().width, getComputedStyle(document.querySelector('#db-login a')).textDecorationLine, !!document.querySelector('#db-login img.r-logo')]")
    check('Anmeldehinweis: Logo, Schloss-Symbol 28 px, Knopf ohne Unterstreichung', knopf == [28, 'none', True], knopf)
    ctx.close()

    # ── Administrator: vierzehn Kacheln und die Seitenleiste aus dem Register ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.41')
    k = kacheln(pg)
    check('vierzehn Kacheln in der Reihenfolge des Modulregisters, Verwaltung & Daten zuletzt', [x['id'] for x in k] == REIHE, [x['id'] for x in k])
    bereiche = pg.evaluate("""[[...document.querySelectorAll('#db-grid .db-tile')].map(t => t.dataset.modul),
        [...document.querySelectorAll('#db-grid-verwaltung .db-tile')].map(t => t.dataset.modul), document.querySelector('#db-verwaltung-titel').textContent,
        document.querySelector('#db-verwaltung').getBoundingClientRect().top > Math.max(...[...document.querySelectorAll('#db-grid .db-tile')].map(t => t.getBoundingClientRect().bottom)),
        [...document.querySelectorAll('#db-bereich .db-tile')].every(t => getComputedStyle(t).flexDirection === 'row' && t.querySelector('.db-ico').getBoundingClientRect().right <= t.querySelector('.db-name').getBoundingClientRect().left)]""")
    check('Import, Verwaltung und Sicherheit im eigenen Bereich „Verwaltung & Daten“ unter den Anwendungen; kompakte Kacheln (Symbol links, Name rechts)',
          bereiche[0] == REIHE[:-3] and bereiche[1] == ['import', 'verwaltung', 'sicherheit'] and bereiche[2] == 'Verwaltung & Daten' and bereiche[3] and bereiche[4], bereiche)
    check('Kachelnamen aus dem Register', [x['name'] for x in k][:2] == ['Angebot', 'Bestand'], [x['name'] for x in k])
    unter = pg.evaluate("[...document.querySelectorAll('#db-bereich a.db-tile')].map(t => [t.dataset.modul, [...t.querySelectorAll('.db-text > *')].filter(e => e.getBoundingClientRect().width > 2).length])")
    check('keine Unterzeile unter verfügbaren Kacheln (nur der Name ist sichtbar, keine Beschreibung)', unter and all(n == 1 for _, n in unter)
          and pg.locator('#db-bereich .db-desc').count() == 0, unter)
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
    check('Kacheln Leergut (freigegeben, Auftrag des Inhabers 29.10.2026 – führt zu /module/leergut/) und Container-Import (geplant, gesperrt): Name aus dem Register, eigene Symbole',
          [x['name'] for x in neu2] == ['Leergut', 'Container-Import'] and [x['badge'] for x in neu2] == ['Verfügbar', 'Geplant']
          and neu2[0]['tag'] == 'A' and neu2[0]['href'] == '/module/leergut/' and neu2[1]['tag'] == 'DIV' and neu2[1]['gesperrt']
          and [x['symbol'] for x in neu2] == ['crate', 'container'] and all(x['svg'] for x in neu2), neu2)
    rw = kid['rewe']
    check('REWE: freigegeben (Auftrag des Inhabers 30.10.2026), Verweis auf das REWE-Modul (Testserver: Pfad /module/rewe/)',
          rw['tag'] == 'A' and rw['href'] == '/module/rewe/' and rw['badge'] == 'Verfügbar', rw)
    qs = kid['qs']
    check('Qualitätssicherung: freigegeben (Entscheidung des Inhabers 30.10.2026), Verweis auf das QM-System (Testserver: Pfad /module/qs/)',
          qs['tag'] == 'A' and qs['href'] == '/module/qs/' and qs['badge'] == 'Verfügbar', qs)
    offen = [kid[m] for m in ('einkauf', 'containerimport')]
    gesperrt = [x for x in offen if x['tag'] != 'DIV' or x['href']]
    check('alle anderen Kacheln ohne Verweis (nicht freigegeben)', not gesperrt, gesperrt)
    check('nicht freigegebene Module zeigen ihren Entwicklungsstand (sichtbar unter dem Namen)',
          all(x['badge'] in ('Geplant', 'In Entwicklung', 'In Prüfung', 'In Vorbereitung') and x['badgeSichtbar'] for x in offen), [(x['badge'], x['badgeSichtbar']) for x in offen])
    check('gesperrte Kacheln als deaktiviert gekennzeichnet', pg.locator('#db-grid .db-tile.off[aria-disabled="true"]').count() == 2)
    check('Zähler: 12 von 14', '12 von 14' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    sic = kid['sicherheit']
    check('Sicherheit: freigegeben (Inhaber 26.10.2026), rechts neben der Verwaltung, Verweis auf die Sicherheitszentrale, eigenes Symbol',
          sic['tag'] == 'A' and sic['href'] == '/module/sicherheit/' and sic['badge'] == 'Verfügbar' and sic['symbol'] == 'shield-lock' and sic['svg'], sic)
    neu = [kid[m] for m in ('hr', 'marketing', 'controlling')]
    check('Module HR, Marketing, Controlling: Name aus dem Register, verfügbar; Controlling (Inhaber 28.10.2026) führt zu /module/controlling/',
          [x['name'] for x in neu] == ['HR', 'Marketing', 'Controlling'] and neu[2]['tag'] == 'A' and neu[2]['href'] == '/module/controlling/'
          and [x['badge'] for x in neu] == ['Verfügbar', 'Verfügbar', 'Verfügbar'], neu)
    check('eigene Symbole (Kalender, Megafon, Diagramm) aus dem gemeinsamen Rahmen', [x['symbol'] for x in neu] == ['calendar', 'megaphone', 'chart'] and all(x['svg'] for x in neu), neu)
    gesperrt = [x for x in k if x['tag'] == 'DIV']
    check('Klebeband „Bald“ auf jeder nicht freigegebenen Kachel (nur Anzeige, für Screenreader der genaue Stand)',
          len(gesperrt) == 2 and all(x['gesperrt'] and x['bald'] == 'Bald' and x['baldVersteckt'] == 'true' for x in gesperrt), gesperrt)
    check('kein Klebeband auf verfügbaren Kacheln', all(not x['bald'] and not x['gesperrt'] for x in k if x['tag'] == 'A'))
    check('„Verfügbar“ nur für Screenreader (keine sichtbare Pille), grün markiert', all('ok' in x['badgeCls'] and 'sr-only' in x['badgeCls'] and not x['badgeSichtbar']
                                                                                  for x in k if x['badge'] == 'Verfügbar'))
    band = pg.evaluate("""(() => { const s = getComputedStyle(document.querySelector('#db-grid .r-bald'));
        return [s.textTransform, s.backgroundImage.includes('repeating-linear-gradient'), s.boxShadow]; })()""")
    check('Klebeband gestreift, Großbuchstaben, ohne Schatten (wie in der Seitenleiste)', band == ['uppercase', True, 'none'], band)
    blass = pg.evaluate("[getComputedStyle(document.querySelector('.gesperrt .db-name')).color, getComputedStyle(document.querySelector('a.db-tile .db-name')).color, getComputedStyle(document.querySelector('.gesperrt')).borderTopStyle]")
    check('gesperrte Kacheln zurückgenommen (leiser Name, gestrichelter Rand), verfügbare in voller Stärke', blass == ['rgb(106, 100, 95)', 'rgb(29, 27, 26)', 'dashed'], blass)
    check('Symbolfarbe je Registersymbol (Angebot: tag, Verwaltung: settings)', k[0]['symbol'] == 'tag' and kid['verwaltung']['symbol'] == 'settings'
          and pg.evaluate("getComputedStyle(document.querySelector('#db-grid [data-modul=\"angebot\"] .db-ico')).backgroundColor") == 'rgb(155, 35, 53)', [x['symbol'] for x in k])
    ruhig = pg.evaluate("""[...document.querySelectorAll('a.db-tile, #r-leiste')].map(e => { const s = getComputedStyle(e);
        return [s.backdropFilter, s.backgroundColor, e.classList.contains('db-tile') ? s.borderTopWidth : '1px']; })""")
    check('ruhige Flächen: kein Glas (keine Unschärfe), Kacheln weiß mit feiner Linie', ruhig and all(b == 'none' and c.startswith('rgb(') and w == '1px' for b, c, w in ruhig), ruhig[:3])
    form = pg.evaluate("[getComputedStyle(document.querySelector('.db-tile')).borderTopLeftRadius, Math.round(document.querySelector('#r-leiste').getBoundingClientRect().width), getComputedStyle(document.querySelector('#r-leiste')).position]")
    check('Kacheln mit 14 px Radius, Seitenleiste 208 px breit und fest (sticky)', form == ['14px', 208, 'sticky'], form)
    hg = pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('#r-leiste')).backgroundColor]")
    check('heller Grund #f6f4f1, Seitenleiste #eeebe7', hg == ['rgb(246, 244, 241)', 'rgb(238, 235, 231)'], hg)
    ueberlauf = pg.evaluate(UEBERLAUF)
    check('Namen passen in Kachel und Seitenleiste', not ueberlauf, ueberlauf)
    check('Schrift Geist (selbst gehostet)', 'Geist' in pg.evaluate("getComputedStyle(document.querySelector('#db-titel')).fontFamily"))
    check('Desktop: keine Kopfzeile fürs Handy, kein Menüknopf sichtbar', pg.evaluate("getComputedStyle(document.querySelector('.r-mobilkopf')).display") == 'none')

    # Seitenleiste: dieselben Module, Gruppen wie im Entwurf, Ziele wie die Kacheln
    L = leiste(pg)
    check('Seitenleiste: Start (aktiv), Anwendungen, In Entwicklung, Verwaltung & Daten', list(L) == ['', 'Anwendungen', 'In Entwicklung', 'Verwaltung & Daten']
          and L[''][0]['id'] == 'start' and L[''][0]['aktiv'] == 'page' and L[''][0]['href'] == './', list(L))
    check('Seitenleiste: freigegebene Anwendungen in der Reihenfolge des Registers als Verweise', [e['id'] for e in L['Anwendungen']] == FREI
          and all(e['tag'] == 'A' and not e['aktiv'] for e in L['Anwendungen']), [e['id'] for e in L['Anwendungen']])
    check('Seitenleiste: Einkauf und Container-Import unter „In Entwicklung“, ohne Verweis, mit „Bald“',
          [e['id'] for e in L['In Entwicklung']] == ['einkauf', 'containerimport'] and all(e['tag'] == 'SPAN' and e['aus'] == 'true' and not e['href']
          and e['bald'] == 'Bald' and 'bald verfügbar' in e['label'] for e in L['In Entwicklung']), L['In Entwicklung'])
    check('Seitenleiste: Import, Verwaltung, Sicherheit unten unter „Verwaltung & Daten“', [e['id'] for e in L['Verwaltung & Daten']] == ['import', 'verwaltung', 'sicherheit'])
    ziele = {e['id']: e['href'] for g in L.values() for e in g}
    check('Seitenleiste: gleiche Ziele wie die Kacheln', all(ziele[x['id']] == x['href'] for x in k if x['tag'] == 'A'), ziele)
    check('Seitenleiste: Symbolfarbe je Registersymbol', pg.evaluate("getComputedStyle(document.querySelector('#r-leiste [data-modul=\"crm\"] svg')).color") == 'rgb(46, 94, 158)')
    check('Seitenleiste: Name des angemeldeten Nutzers, Rolle und Initialen im Fuß', pg.text_content('#r-nutzer-name') == 'Administrator' and 'Angemeldet als' in pg.text_content('.r-person')
          and pg.text_content('#r-rolle') == 'Administrator' and pg.text_content('#r-initialen') == 'AD', pg.text_content('.r-fuss'))
    check('Seitenleiste: Abmelden als Knopf mit Beschriftung', pg.get_attribute('#r-abmelden', 'aria-label') == 'Abmelden')
    kontrast_ok(pg, 'hell')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280.png'), full_page=True)

    # Schmale Leiste (Module mit eigener Navigation): nur Symbole, Namen als Beschriftung, aktiver Eintrag markiert
    pg.evaluate("""Promise.all([fetch('../api/?action=module_status').then(r => r.json()), fetch('../api/?action=status').then(r => r.json())])
        .then(([d, s]) => STAFL_RAHMEN.zeichnen({ module: d.module, aktiv: 'crm', nutzer: s.user, start: './', schmal: true, abmelden() {} }))""")
    pg.wait_for_selector('.r-app.r-schmal'); bilder(pg)
    schmal = pg.evaluate("""(() => { const n = document.querySelector('#r-leiste');
        return { breite: Math.round(n.getBoundingClientRect().width), texte: [...n.querySelectorAll('.r-text, .r-gruppe-titel, .r-person, .r-bald')].every(e => getComputedStyle(e).display === 'none'),
                 namen: [...n.querySelectorAll('a.r-eintrag')].every(e => e.getAttribute('aria-label') && e.title), aktiv: [...n.querySelectorAll('[aria-current="page"]')].map(e => e.dataset.modul),
                 trenner: [...n.querySelectorAll('.r-trenner')].filter(e => getComputedStyle(e).display === 'block').length, band: getComputedStyle(document.querySelector('#db-grid .r-bald')).display,
                 abmelden: document.querySelector('#r-abmelden').getBoundingClientRect().width > 0 }; })()""")
    check('schmale Leiste: 60 px, nur Symbole, jeder Eintrag beschriftet (Tooltip), CRM aktiv, Trenner statt Überschriften, Abmelden erreichbar',
          schmal['breite'] == 60 and schmal['texte'] and schmal['namen'] and schmal['aktiv'] == ['crm'] and schmal['trenner'] == 3 and schmal['abmelden'], schmal)
    check('schmale Leiste: Klebeband der Kacheln bleibt sichtbar', schmal['band'] != 'none', schmal['band'])
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_schmal.png'))
    pg.reload(); pg.wait_for_selector('#db-grid .db-tile')

    # Gemeldet: „Qualitätssicherungskon-zept“ – Namen werden nicht mehr automatisch getrennt
    for breite in (1920, 1280, 1024, 768, 575, 390, 360):
        pg.set_viewport_size({'width': breite, 'height': 900}); bilder(pg)
        namen = pg.evaluate(WORT_GETRENNT)
        check(f'{breite} px: Registernamen ohne Silbentrennung und ohne Umbruch im Wort (auch „Qualitätssicherung“, „Container-Import“)',
              all(not g and not u and h != 'auto' for _, g, u, _f, h in namen), namen)
        ueber = pg.evaluate(UEBERLAUF)
        check(f'{breite} px: kein Name ragt aus Kachel oder Seitenleiste', not ueber, ueber)
    pg.set_viewport_size({'width': 1280, 'height': 900}); bilder(pg)
    echt = pg.evaluate("""fetch('../api/?action=module_status').then(r => r.json()).then(d => {
        const alle = Object.fromEntries(d.module.map((m) => [m.id, m]));
        return ['angebot', 'verwaltung', 'bestand', 'import', 'hr'].map((id) => [window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'dashboard-stafl.de'),
                                                      window.STAFL_KACHEL_ZIEL(alle[id].kachel, alle, 'angebot.stafl.test')]); })""")
    check('Echtbetrieb (dashboard-stafl.de): Kacheln und Seitenleiste führen zu den Hosts der zentralen Anmeldung, nicht zum bisherigen /admin/',
          echt == [['https://angebot.dashboard-stafl.de/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/admin/', '/admin/'],
                   ['https://bestand.dashboard-stafl.de/admin/', '/admin/'], ['https://verwaltung.dashboard-stafl.de/import/', '/import/'],
                   ['https://hr.dashboard-stafl.de/module/hr/', '/module/hr/']], echt)
    pg.click('#r-leiste a[data-modul="crm"]'); pg.wait_for_url('**/module/crm/')
    check('Klick auf CRM in der Seitenleiste öffnet das CRM', pg.url.endswith('/module/crm/'))
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    pg.click('#db-grid a[data-modul="angebot"]'); pg.wait_for_url('**/admin/')
    check('Klick auf die Kachel Angebot öffnet die Mitarbeiter-Eingabe', pg.url.endswith('/admin/'))
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
        check(f'{breite} px: überlange Namen erst mit kleinerer Schrift; Umbruch nur als Notlösung in kleinster Schrift (12 px)',
              len(lang) == 2 and all(f < 15 and (not u or f == 12) for _, _g, u, f, _h in lang), lang)
        check(f'{breite} px: kurze Namen behalten ihre Schriftgröße (15 px)', all(f == 15 for n, _g, _u, f, _h in namen if n in ('Angebot', 'REWE')), namen)
        ueber = pg.evaluate(UEBERLAUF)
        check(f'{breite} px: überlange Namen ragen weder aus der Kachel noch aus der Seitenleiste', not ueber, ueber)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_lange_namen.png'), full_page=True)
    hoehen = pg.evaluate("[...document.querySelectorAll('#db-grid .db-tile')].map(t => Math.round(t.getBoundingClientRect().top) + ':' + Math.round(t.getBoundingClientRect().height))")
    reihen = {}
    for h in hoehen: reihen.setdefault(h.split(':')[0], set()).add(h.split(':')[1])
    check('Kacheln einer Reihe gleich hoch (auch wenn ein Name umbricht)', all(len(v) == 1 for v in reihen.values()), hoehen)
    ctx.close()

    # ── Begrüßung nach Tageszeit mit Vornamen und Datum (feste Uhr, Europe/Berlin), dunkles Design am Desktop ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.46', dunkel=True, uhr=datetime(2026, 10, 22, 19, 30, tzinfo=BERLIN))
    check('Datum deutsch ausgeschrieben', pg.text_content('#db-datum') == 'Donnerstag, 22. Oktober', pg.text_content('#db-datum'))
    check('abends: „Guten Abend, <Vorname>“ als Hauptüberschrift', pg.text_content('#db-titel') == 'Guten Abend, Administrator' and pg.evaluate("document.querySelector('#db-titel').tagName") == 'H1',
          pg.text_content('#db-titel'))
    grenzen = pg.evaluate("[0, 4, 5, 10, 11, 17, 18, 23].map((h) => window.STAFL_GRUSS(h))")
    check('Begrüßung: Grenzen 5/11/18 Uhr', grenzen == ['Guten Abend', 'Guten Abend', 'Guten Morgen', 'Guten Morgen', 'Guten Tag', 'Guten Tag', 'Guten Abend', 'Guten Abend'], grenzen)
    hg = pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('#r-leiste')).backgroundColor]")
    check('dunkles Design folgt der Systemeinstellung (Grund #121011, Seitenleiste #1b1a19)', hg == ['rgb(18, 16, 17)', 'rgb(27, 26, 25)'], hg)
    aus = pg.evaluate("getComputedStyle(document.querySelector('#db-grid [data-modul=\"einkauf\"] .db-ico')).color")
    check('dunkel: Symbol gesperrter Kacheln bleibt zurückgenommen (keine Modulfarbe)', aus == 'rgb(111, 104, 99)', aus)
    kontrast_ok(pg, 'dunkel')
    pg.screenshot(path=os.path.join(SH, 'dashboard_1280_dunkel.png'), full_page=True)
    pg.clock.set_fixed_time(datetime(2026, 10, 23, 8, 15, tzinfo=BERLIN)); pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('morgens: „Guten Morgen, <Vorname>“, Datum des Tages', pg.text_content('#db-titel') == 'Guten Morgen, Administrator' and pg.text_content('#db-datum') == 'Freitag, 23. Oktober',
          (pg.text_content('#db-titel'), pg.text_content('#db-datum')))
    # Weniger Transparenz und weniger Bewegung (Systemeinstellungen)
    cdp = ctx.new_cdp_session(pg)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-transparency', 'value': 'reduce'}]})
    deckend = pg.evaluate("[...document.querySelectorAll('#r-leiste, .db-tile:not(.gesperrt)')].map(e => getComputedStyle(e).backgroundColor)")
    check('deckende Flächen (auch bei „Transparenz reduzieren“ kein Glas nötig)', all(c.startswith('rgb(') for c in deckend), deckend)
    cdp.send('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
    pg.wait_for_function("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration === '0s'")
    check('weniger Bewegung: keine Übergänge an den Kacheln', pg.evaluate("getComputedStyle(document.querySelector('a.db-tile')).transitionDuration") == '0s')
    ctx.close()

    # ── Mobil (390 px) und dunkles Design: Kopfzeile mit Menü, Seitenleiste als Menü ──
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.42', breite=390, dunkel=True)
    breiter = pg.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    check('390 px: kein waagerechtes Scrollen', not breiter)
    kopf = pg.evaluate("""(() => { const t = document.querySelector('.r-mobilkopf').getBoundingClientRect();
        return [t.height > 0, [...document.querySelectorAll('.r-mobilkopf img, .r-mobilkopf button')].every(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.left >= t.left - 1 && r.right <= t.right + 1; }),
                getComputedStyle(document.querySelector('#r-leiste')).visibility, document.querySelector('#r-menue').getAttribute('aria-expanded')]; })()""")
    check('390 px: Kopfzeile mit Menüknopf und Logo, Seitenleiste eingeklappt (unsichtbar, nicht per Tab erreichbar)', kopf == [True, True, 'hidden', 'false'], kopf)
    pg.click('#r-menue'); pg.wait_for_function("Math.round(document.querySelector('#r-leiste').getBoundingClientRect().left) === 0")
    menue = pg.evaluate("""(() => { const n = document.querySelector('#r-leiste').getBoundingClientRect();
        return [document.querySelector('#r-menue').getAttribute('aria-expanded'), document.activeElement.closest('#r-leiste') !== null, Math.round(n.left), n.right <= innerWidth,
                ['#r-abmelden', '#r-initialen', '#r-leiste a[data-modul="crm"]'].every(s => document.querySelector(s).getBoundingClientRect().width > 0)]; })()""")
    check('390 px: Menü öffnet die Seitenleiste (Fokus darin, ganz im Bild), Abmelden und Anwendungen erreichbar', menue == ['true', True, 0, True, True], menue)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_menue_dunkel.png'))
    pg.keyboard.press('Escape'); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'hidden'")
    check('390 px: Escape schließt das Menü, Fokus zurück auf den Menüknopf', pg.evaluate("[document.querySelector('#r-menue').getAttribute('aria-expanded'), document.activeElement.id]") == ['false', 'r-menue'])
    pg.click('#r-menue'); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'visible'")
    pg.mouse.click(370, 450); pg.wait_for_function("getComputedStyle(document.querySelector('#r-leiste')).visibility === 'hidden'")
    check('390 px: Klick neben das Menü schließt es', pg.get_attribute('#r-menue', 'aria-expanded') == 'false')
    sichtbar = pg.evaluate("['#db-theme', '#db-darstellung'].map((s) => document.querySelector(s).getBoundingClientRect().width > 0)")
    check('390 px: Hell/Dunkel und einfache Darstellung erreichbar', all(sichtbar), sichtbar)
    spalten = pg.evaluate("[...document.querySelectorAll('#db-grid, #db-grid-verwaltung')].map(g => getComputedStyle(g).gridTemplateColumns.split(' ').length)")
    check('390 px: zwei Kachelspalten (Anwendungen und Verwaltung & Daten)', spalten == [2, 2], spalten)
    senkrecht = pg.evaluate("[...document.querySelectorAll('#db-bereich .db-tile')].every(t => getComputedStyle(t).flexDirection === 'column')")
    check('390 px: Symbol über dem Namen', senkrecht)
    gross = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#db-titel')).fontSize)")
    check('390 px: Überschrift 26 px', gross == 26, gross)
    ueberlauf = pg.evaluate(UEBERLAUF)
    check('390 px: Kachelnamen passen in die Kachel', not ueberlauf, ueberlauf)
    frei = pg.evaluate("""[...document.querySelectorAll('.gesperrt')].map(t => { const b = t.querySelector('.r-bald').getBoundingClientRect(), n = t.querySelector('.db-name').getBoundingClientRect(),
        i = t.querySelector('.db-ico').getBoundingClientRect(), k = t.getBoundingClientRect();
        return [t.dataset.modul, b.bottom <= n.top || b.left >= n.right, b.left >= i.right, b.right <= k.right]; })""")
    check('390 px: Klebeband oben rechts, verdeckt weder Namen noch Symbol', frei and all(all(x[1:]) for x in frei), frei)
    check('390 px: Stand gesperrter Kacheln bleibt im Text', all(x['badge'] for x in kacheln(pg)))
    hg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design folgt der Systemeinstellung', hg == 'rgb(18, 16, 17)', hg)
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_dunkel.png'), full_page=True)
    pg.click('#db-theme'); pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'")
    gespeichert = pg.evaluate("localStorage.getItem('wochenangebot.theme')")
    check('Umschalter speichert das Design wie die Angebotsseite', json.loads(gespeichert or 'null') == 'light', gespeichert)
    pg.reload(); pg.wait_for_selector('#db-grid .db-tile')
    check('gewähltes Design bleibt nach dem Neuladen', pg.evaluate("document.documentElement.getAttribute('data-theme')") == 'light')
    check('helles Design trotz dunkler Systemeinstellung', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(246, 244, 241)')
    pg.screenshot(path=os.path.join(SH, 'dashboard_390_hell.png'), full_page=True)
    ctx.close()

    # ── Wartung des Eingabebereichs: Bearbeiter gesperrt, Administrator mit Hinweis ──
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': True, 'grund': 'Test Dashboard',
                                          'message': 'Kurz weg <img src=x onerror="window.__xss=1"> Infos: https://angebot-stafl.de/hinweise/wartungsfenster-oktober-2026'})
    check('Wartung des Eingabebereichs gestartet', st == 200 and r.get('aktiv') is True, (st, r))
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.43')
    a = kacheln(pg)[0]
    check('Bearbeiter: Angebot in Wartung, ohne Verweis', a['tag'] == 'DIV' and not a['href'] and a['badge'] == 'Wartung', a)
    check('Wartung bleibt eigener Zustand: sichtbare Wartungs-Pille, kein Klebeband', 'warn' in a['badgeCls'] and a['badgeSichtbar'] and not a['bald'] and not a['gesperrt'], a)
    check('Bearbeiter: Initialen „EE“, Vorname in der Begrüßung', pg.text_content('#r-initialen') == 'EE' and pg.text_content('#db-titel').endswith(', Erika'),
          (pg.text_content('#r-initialen'), pg.text_content('#db-titel')))
    check('Bearbeiter: Wartungshinweis als Text (kein HTML)', 'Kurz weg <img' in a['hint'] and a['bilder'] == 0 and not pg.evaluate('window.__xss'), a)
    # Controlling: Modulzugang standardmäßig niemand (Finanzdaten, 28.10.2026) – Kachel und Eintrag fehlen Bearbeitern ganz
    check('Bearbeiter: Bestand, Import, HR, CRM, Marketing, Leergut, REWE, Qualitätssicherung und Verwaltung weiter verfügbar (9 von 12, ohne Controlling)', '9 von 12' in pg.text_content('#db-sub'), pg.text_content('#db-sub'))
    L = leiste(pg)
    ang = next(e for e in L['Anwendungen'] if e['id'] == 'angebot')
    check('Bearbeiter: Seitenleiste ohne Controlling; Angebot ohne Verweis mit Stand „Wartung“', 'controlling' not in [e['id'] for g in L.values() for e in g]
          and ang['tag'] == 'SPAN' and ang['aus'] == 'true' and ang['stand'] == 'Wartung' and '(Wartung)' in ang['label'], ang)
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_bearbeiter.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden(br, 'admin', PW, '198.51.100.44')
    a = kacheln(pg)[0]
    check('Administrator: Angebot in Wartung, aber weiter erreichbar', a['tag'] == 'A' and a['badge'] == 'Wartung – Zugang für Administratoren', a)
    check('Administrator: Wartungs-Pille ohne Klebeband', 'warn' in a['badgeCls'] and a['badgeSichtbar'] and not a['bald'], a)
    ang = next(e for e in leiste(pg)['Anwendungen'] if e['id'] == 'angebot')
    check('Administrator: Angebot in der Seitenleiste als Verweis mit Stand „Wartung“', ang['tag'] == 'A' and ang['stand'] == 'Wartung', ang)
    pg.set_viewport_size({'width': 360, 'height': 900}); bilder(pg)
    zu = pg.evaluate("(() => { const s = getComputedStyle(document.querySelector('#r-leiste')); return [s.visibility, s.transitionDuration]; })()")
    check('Wechsel von breit auf schmal: Seitenleiste sofort eingeklappt (ohne Hineinrutschen)', zu[0] == 'hidden' and zu[1] in ('0s', '0s, 0s'), zu)
    lage = pg.evaluate("""(() => { const t = document.querySelector('#db-grid [data-modul="angebot"]'), k = t.getBoundingClientRect(), h = t.querySelector('.db-hint'), p = t.querySelector('.db-badge');
        const pr = p.getBoundingClientRect(), s = getComputedStyle(p);
        return {hinweis: h.scrollWidth <= h.clientWidth + 1 && h.getBoundingClientRect().right <= k.right - 8, pille: pr.right <= k.right - 8 && pr.left >= k.left,
                zeilen: Math.round(pr.height / parseFloat(s.lineHeight)), radius: parseFloat(s.borderTopLeftRadius)}; })()""")
    check('360 px: langer Wartungshinweis (Adresse) bricht innerhalb der Kachel um', lage['hinweis'], lage)
    check('360 px: lange Pille „Wartung – Zugang für Administratoren“ bleibt in der Kachel, mehrzeilig als abgerundetes Feld', lage['pille'] and lage['zeilen'] >= 2 and lage['radius'] <= 13, lage)
    pg.screenshot(path=os.path.join(SH, 'dashboard_wartung_admin_360.png'), full_page=True)
    ctx.close()
    st, r = A.call('modul_wartung_save', {'bereich': 'angebot.eingabe', 'active': False, 'grund': 'Test beendet'})
    check('Wartung beendet', st == 200 and r.get('aktiv') is False, (st, r))

    # ── Abmelden (Knopf in der Seitenleiste) beendet die Sitzung serverseitig ──
    ctx, pg = anmelden(br, 'erika', 'Editor-Zugang-77', '198.51.100.45')
    check('nach der Wartung wieder verfügbar', kacheln(pg)[0]['badge'] == 'Verfügbar')
    pg.click('#r-abmelden'); pg.wait_for_selector('#db-login:not([hidden])')
    angemeldet = pg.evaluate("fetch('../api/?action=status', {credentials: 'same-origin'}).then(r => r.json()).then(j => j.loggedIn)")
    check('Abmelden: Anmeldehinweis, Seitenleiste entfernt, Sitzung beendet', angemeldet is False and pg.is_hidden('#db-bereich') and pg.is_hidden('#r-leiste')
          and pg.locator('#r-leiste .r-eintrag').count() == 0, angemeldet)
    pg.reload(); pg.wait_for_selector('#db-login:not([hidden])')
    check('nach dem Neuladen weiter abgemeldet', pg.is_hidden('#db-bereich'))
    check('Anmeldehinweis als deckende Karte mit echtem Link', pg.evaluate("getComputedStyle(document.querySelector('#db-login')).backgroundColor") == 'rgb(255, 255, 255)'
          and pg.evaluate("document.querySelector('#db-login a').tagName") == 'A')
    pg.goto(B + '/dashboard/abgemeldet.html'); pg.wait_for_selector('#db-abgemeldet')
    check('Abmeldeseite im neuen Design (Grund, Karte mit Logo, Link zur Anmeldung)', pg.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(246, 244, 241)'
          and pg.get_attribute('#db-abgemeldet a', 'href') == './' and pg.locator('#db-abgemeldet img.r-logo').count() == 1
          and not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth'))
    check('Abmeldeseite: Knopf „Erneut anmelden“ ohne Unterstreichung', pg.evaluate("getComputedStyle(document.querySelector('#db-abgemeldet a')).textDecorationLine") == 'none')
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
