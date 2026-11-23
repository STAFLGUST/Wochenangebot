"""Einheitliches Erscheinungsbild aller Mitarbeiter-Oberflächen (Dashboard, Eingabebereich auf den Bereichs-Hosts Angebot,
Verwaltung, Bestand, alle Modulseiten – HR, CRM, Controlling, Leergut, Marketing, QS, REWE, Sicherheit, Versand,
Container-Import –, Abmeldeseite, Hinweis „Kein Zugang“): je hell/dunkel und 1440/390 px

- kein waagerechtes Scrollen, kein abgeschnittener Text (Text breiter als sein Kasten bei verdecktem Überlauf, Text
  außerhalb des Bildschirms) – Ausnahmen nur für bewusst gekürzte Zellen mit vollem Text im Tooltip (title),
- Logo im dunklen Design weiß auf dunklem Grund (keine helle Fläche hinter dem Logo),
- derselbe Zurück-Knopf „Dashboard“ (Maße, Rundung, Schrift, Symbol) auf jeder Modulseite, Ziel = Dashboard,
- Hell/Dunkel gilt für das Konto auf jedem Host: die Wahl wird am Mitarbeiterkonto gespeichert (Aktion theme_save) und
  von jeder Seite nach der Anmeldung übernommen.
- Einfache Darstellung für Remote-Desktop (02.11.2026): automatisch, wenn der Browser ohne Grafikkarte zeichnet (unter
  Automatisierung nur mit abgeschaltetem navigator.webdriver), Knopf im Dashboard, Wahl am Konto (theme_save „darstellung“)
  gilt auf jedem Host; dann keine Unschärfe, keine Farbflächen, keine Übergänge.
- Fenster (<dialog>) auf jeder Seite gleich (02.11.2026): ein Klick daneben schließt nie, Escape schließt; Hinweise (Toasts)
  erscheinen über einem offenen Fenster, nicht dahinter; jedes fest geschriebene Fenster hat oben rechts ein × („Schließen“) –
  ausgenommen reine Rückfragen (Ja/Abbrechen).
- Zahlen und Einheiten (02.11.2026): jede Seite lädt app/assets/format.js; Beträge, kg, €/kg, Prozent, Datum und KW wie
  vereinbart (docs/entwickler/10-konventionen.md).
- Fingerbedienung am Handy (10.11.2026): mit pointer: coarse auf jeder Seite Eingabefelder ≥ 16 px Schrift (kein
  Hineinzoomen am iPhone), kleine Knöpfe (.btn.sm) antippbar, kein waagerechtes Scrollen.
- Suche (10.11.2026): jede Seite lädt app/assets/suche.js; alle Suchfelder folgen einer Regel (Umlaute auch ausgeschrieben,
  mehrere Wörter, gegliederte Nummern).
Bildschirmfotos: tests/.ergebnisse/einheit-*.png (Bestandsaufnahme für die Durchsicht).
"""
import glob
import json
import os
import re
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


# Jedes fest im HTML stehende Fenster hat ein × (Knopf mit „…schließen“ als Beschriftung); per Skript gefüllte Fenster prüft
# die Durchsicht am Bild, reine Rückfragen (dlg-frage, dlg-confirm) haben nur Ja/Abbrechen, Pflichtfenster (data-pflicht) keins
APP = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
ohne_x = []
for datei in glob.glob(os.path.join(APP, '**', 'index.html'), recursive=True):
    for m in re.finditer(r'<dialog\b([^>]*)>(.*?)</dialog>', open(datei, encoding='utf-8').read(), re.S):
        dlg_id = (re.search(r'\bid="([^"]+)"', m.group(1)) or [None, ''])[1]
        inhalt = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if not inhalt or re.search(r'frage|confirm', dlg_id) or 'data-pflicht' in m.group(1):
            continue
        if not re.search(r'<button[^>]*aria-label="[^"]*[Ss]chließen"', m.group(2)):
            ohne_x.append(os.path.relpath(datei, APP) + '#' + dlg_id)
check('Fenster mit festem Inhalt haben ein × zum Schließen', not ohne_x, ohne_x)

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
# CRM: produktiv freigegeben (Register) – solange ein Modul noch nicht freigegeben ist, prüft die Durchsicht es als Testfreigabe
ADMIN = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == 'admin')
crm = next(o for m in A.call('module_status')[1]['module'] if m['id'] == 'crm' for o in m['oberflaechen'] if o['id'] == 'intern')
if not crm['zugang']:
    check('CRM zur Prüfung freigegeben (Test, Tester Administrator)', A.call('modul_freigabe_save', {'bereich': 'crm.intern', 'freigabe': 'test', 'grund': 'Durchsicht'})[0] == 200
          and A.call('modul_tester_save', {'bereich': 'crm.intern', 'tester': [ADMIN], 'grund': 'Durchsicht'})[0] == 200)
check('CRM für den Administrator erreichbar', next(o for m in A.call('module_status')[1]['module'] if m['id'] == 'crm' for o in m['oberflaechen'] if o['id'] == 'intern')['zugang'])

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
    // bewusst gekürzt (verdeckter Überlauf mit vollem Text im Tooltip): der Text liegt nur rechnerisch hinter dem Rand
    const gekuerzt = verdeckt && (e.title || e.closest('[title]'));
    if (b.width && !gekuerzt && ((b.right > W + 1 && b.left < W) || (b.left < -1 && b.right > 0)) && !e.closest('.stafl-streifen, [class*="scroll"], .tblwrap, .rm-wrap, table')) out.push('rand ' + name + ` ${Math.round(b.left)}..${Math.round(b.right)}/${W}`);
  }
  return [...new Set(out)].slice(0, 12);
}'''
# Logo: im dunklen Design ohne helle Fläche dahinter und weiß gefärbt (Filter oder weiße Datei)
LOGO = r'''() => [...document.querySelectorAll('img[src*="logo-standard-fleisch"]')].filter((e) => e.getBoundingClientRect().width > 0).map((e) => {
  const s = getComputedStyle(e); return { bg: s.backgroundColor, filter: s.filter, src: e.getAttribute('src').split('/').pop() }; })'''
# Rahmen „C2“: Zustand der Seitenleiste und Glasflächen (backdrop-filter) auf der Seite – Hinweise (Toasts) ausgenommen
RAHMEN = r'''() => { const n = document.querySelector('#r-leiste'), k = document.querySelector('.r-mobilkopf');
  return { aktiv: [...n.querySelectorAll('[aria-current="page"]')].map((e) => e.dataset.modul), breite: Math.round(n.getBoundingClientRect().width),
           zu: getComputedStyle(n).visibility === 'hidden', kopf: !!k && k.getBoundingClientRect().height > 0, start: n.querySelector('[data-modul="start"]').getAttribute('href'),
           glas: [...document.querySelectorAll('body *')].filter((e) => { const s = getComputedStyle(e); return s.backdropFilter && s.backdropFilter !== 'none' && !/toast/.test(e.id + ' ' + e.className); })
             .map((e) => e.id || String(e.className)).slice(0, 5) }; }'''
# „Artikel hinzufügen“: Zahl der Knopfreihen im Fuß, Breite des Platzhalters gegen den Platz im Suchfeld (Feld hat beim Öffnen
# den Fokus – Chrome kürzt den Platzhalter dann ohne „…“)
ARTIKELWAHL = r'''() => { const d = document.querySelector('#dlg-ez-pick'), i = d.querySelector('#ezp-q'), s = getComputedStyle(i);
  const c = document.createElement('canvas').getContext('2d'); c.font = `${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
  const reihen = new Set([...d.querySelectorAll('.ezp-foot > .btn')].filter((b) => b.offsetParent).map((b) => Math.round(b.getBoundingClientRect().top)));
  return { platzhalter: Math.ceil(c.measureText(i.placeholder).width), feld: Math.floor(i.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight)), reihen: reihen.size }; }'''
# Rollen „Auf einen Blick“: Name jeder Kachel innerhalb der Kachel (lange Namen werden getrennt, ragen nicht hinaus)
KACHELN = r'''() => [...document.querySelectorAll('.rl-kachel')].filter((k) => k.offsetParent).map((k) => { const n = k.querySelector('.rl-kachel-n'), r = document.createRange();
  r.selectNodeContents(n); const t = r.getBoundingClientRect(), kb = k.getBoundingClientRect(); return [n.textContent.trim(), Math.round(t.left - kb.left), Math.round(kb.right - t.right)]; })
  .filter((x) => x[1] < 0 || x[2] < 0)'''
# Hauptknöpfe (sichtbar, auch in Seiten aus den Bausteinen): Fläche und Schrift wie --r-akzent / --r-akzent-ink (Probe-Element)
HAUPTKNOPF = r'''() => { const p = document.createElement('i'); p.style.cssText = 'background-color:var(--r-akzent);color:var(--r-akzent-ink)'; document.body.append(p);
  const soll = [getComputedStyle(p).backgroundColor, getComputedStyle(p).color]; p.remove();
  const k = [...document.querySelectorAll('.btn.primary, .ci-knopf.primaer, .vs-knopf.primaer')].filter((b) => b.offsetParent);
  return { n: k.length, soll, abw: k.filter((b) => { const s = getComputedStyle(b); return s.backgroundColor !== soll[0] || s.color !== soll[1]; })
    .map((b) => (b.id || b.textContent.trim().slice(0, 20)) + ' ' + getComputedStyle(b).backgroundColor + ' ' + getComputedStyle(b).color).slice(0, 4) }; }'''
# Pfeil: Form des Symbols (aus dem Sprite der Seite über <use> oder vom Rahmen direkt gezeichnet)
ZURUECK = r'''() => { const e = document.querySelector('.stafl-zurueck'); if (!e || !e.offsetParent) return null; const s = getComputedStyle(e), r = e.getBoundingClientRect();
  const svg = e.querySelector('svg'), use = svg && svg.querySelector('use'), form = use ? document.querySelector(use.getAttribute('href')) : svg;
  return { h: Math.round(r.height), w: Math.round(r.width), radius: s.borderTopLeftRadius, font: s.fontSize + ' ' + s.fontWeight, text: e.textContent.trim(), href: e.getAttribute('href'),
           icon: form ? form.innerHTML.trim() : null, pad: s.paddingLeft + ' ' + s.paddingRight, farbe: s.color,
           // Kopf: Lage des Knopfs, daneben (nächstes sichtbares Geschwister mit Text) Symbol und Name des Moduls in einer Zeile
           x: Math.round(r.left), y: Math.round(r.top), titel: (() => { const t = [...e.parentElement.children].find((x) => x !== e && x.offsetParent && x.textContent.trim());
             if (!t) return null; const q = t.getBoundingClientRect(); return [getComputedStyle(t).fontSize, [...t.querySelectorAll('svg')].some((s) => s.getBoundingClientRect().width > 0), Math.abs((q.top + q.bottom) / 2 - (r.top + r.bottom) / 2) <= 4]; })() }; }'''

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
              ('verwaltung', 'verwaltung.verwaltung', '/admin/', '#screen-editor:not([hidden])', ['master', 'kunden', 'users', 'rollen', 'log']),
              ('bestand', 'bestand.intern', '/admin/', '#view-stock:not([hidden])', ['stock']),
              ('hr', None, '/module/hr/', '#hr-app:not([hidden])', []),
              ('crm', None, '/module/crm/', '#crm-app:not([hidden])', []),
              ('controlling', None, '/module/controlling/', '#ctl-app:not([hidden])', []),
              ('leergut', None, '/module/leergut/', '#lg-app:not([hidden])', []),
              ('marketing', None, '/module/marketing/', '#mkt-app:not([hidden])', []),
              ('qs', None, '/module/qs/', '#qm-app:not([hidden])', []),
              ('rewe', None, '/module/rewe/', '#rw-app:not([hidden])', []),
              ('sicherheit', None, '/module/sicherheit/', '#sic-app:not([hidden])', []),
              ('versand', None, '/module/versand/', '#vs-app:not([hidden])', []),
              ('containerimport', None, '/module/containerimport/', '#ci-app:not([hidden])', [])]
    zurueck = {}
    for breite in (1440, 390):
        for dunkel in (False, True):
            ctx, pg = neue_seite(breite, dunkel)
            tag = f'{"dunkel" if dunkel else "hell"}-{breite}'
            for name, bereich, pfad, warte, ansichten in SEITEN:
                if bereich: als_bereich(pg, bereich)
                pg.goto(B + pfad); pg.wait_for_selector(warte, timeout=20000)
                if name != 'dashboard':   # Rahmen „C2“ (06.11.2026): gemeinsame Seitenleiste auf jeder Mitarbeiterseite
                    pg.wait_for_selector('.r-app.r-bereit', timeout=20000)
                    rh = pg.evaluate(RAHMEN)
                    breit = 60   # seit 10.11.2026 überall gleich: schmal, bis man sie mit dem Pin feststellt (Testnutzer ohne eigene Wahl)
                    if breite > 900:
                        check(f'{name} {tag}: Seitenleiste ({breit} px), eigenes Modul aktiv, Start zum Dashboard, kein Glas', rh['aktiv'] == [name] and rh['breite'] == breit
                              and rh['start'].rstrip('/').endswith('dashboard') and not rh['glas'] and not rh['kopf'], rh)
                    else:
                        check(f'{name} {tag}: Seitenleiste als Menü (zu), Kopfzeile mit Menüknopf, eigenes Modul aktiv', rh['aktiv'] == [name] and rh['zu'] and rh['kopf'] and not rh['glas'], rh)
                for v in (ansichten or [None]):
                    if v:
                        pg.evaluate("v => { const b = document.querySelector('#vt-' + v); if (b && !b.hidden) b.click(); }", v)
                        pg.wait_for_selector(f'#view-{v}:not([hidden])', timeout=20000)
                        pg.wait_for_function("() => !document.querySelector('.adm-page .loading:not([hidden])')", timeout=20000)
                    teil = f'{name}{"-" + v if v else ""}'
                    if v == 'edit' and name == 'angebot' and not dunkel:   # „Artikel hinzufügen“: eine Knopfreihe (PC), Platzhalter passt ins Feld
                        pg.click('#btn-add-art'); pg.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
                        aw = pg.evaluate(ARTIKELWAHL)
                        pg.evaluate("document.querySelector('#dlg-ez-pick').close()")
                        check(f'{teil} {tag}: „Artikel hinzufügen“ – Platzhalter passt ins Suchfeld' + (', Knöpfe in einer Reihe' if breite > 900 else ''),
                              aw['platzhalter'] <= aw['feld'] and (breite <= 900 or aw['reihen'] == 1), aw)
                    if v == 'rollen':   # „Auf einen Blick“: Namen bleiben in ihrer Kachel
                        raus = pg.evaluate(KACHELN)
                        check(f'{teil} {tag}: Rollen – Namen der Kacheln ragen nicht über die Kachel', not raus, raus)
                    if v == 'users' and breite == 390 and not dunkel:   # Fehlermeldung im langen Formular „Mitarbeiter anlegen“ sichtbar (Raster scrollt)
                        pg.click('#user-add'); pg.wait_for_selector('#dlg-user[open] #user-err', state='attached')
                        fe = pg.evaluate("""() => { const e = document.querySelector('#user-err'), b = e.closest('.dlg-body'); e.textContent = 'Benutzername ist schon vergeben.';
                          e.scrollIntoView({ block: 'nearest' }); const h = e.getBoundingClientRect().height; e.textContent = ''; return [Math.round(h), b.scrollHeight > b.clientHeight]; }""")
                        pg.evaluate("document.querySelector('#dlg-user').close()")
                        check(f'{teil} {tag}: Fehlermeldung im langen Formular sichtbar (nicht auf Höhe 0)', fe[0] >= 15 and fe[1], fe)
                    if v == 'orders':   # Werkzeugleiste „Bestellungen“: Suche und Statusauswahl gleich hoch (wie in den anderen Leisten)
                        hoehen = pg.evaluate("['#orders-filter .search input', '#orders-filter select'].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().height))")
                        check(f'{teil} {tag}: Suche und Auswahl der Werkzeugleiste gleich hoch', hoehen[0] == hoehen[1], hoehen)
                    pg.screenshot(path=f'{SH}/einheit-{teil}-{tag}.png')
                    pg.evaluate('document.fonts.ready.then(() => true)')
                    weg = pg.evaluate(ABGESCHNITTEN)
                    check(f'{teil} {tag}: kein abgeschnittener Text', not weg, weg)
                    check(f'{teil} {tag}: kein waagerechtes Scrollen', pg.evaluate('document.documentElement.scrollWidth') <= breite)
                    if bereich:   # Eingabebereich im Rahmen „C2“: Hauptknöpfe flach wie im Versand – kein Verlauf, kein Glühschatten
                        glanz = pg.evaluate("[...document.querySelectorAll('.btn.primary')].filter((b) => b.offsetParent).map((b) => [b.textContent.trim().slice(0, 24), getComputedStyle(b).backgroundImage, getComputedStyle(b).boxShadow]).filter((x) => x[1] !== 'none' || x[2] !== 'none')")
                        check(f'{teil} {tag}: Hauptknöpfe flach (ohne Verlauf und Schatten)', not glanz, glanz)
                    if dunkel and name != 'dashboard':   # Hauptknopf im dunklen Design überall wie Versand und Container-Import (weiße Schrift)
                        hk = pg.evaluate(HAUPTKNOPF)
                        check(f'{teil} {tag}: Hauptknöpfe in der Akzentfarbe des Rahmens ({hk["n"]})', not hk['abw'], hk)
                    if not dunkel:
                        ohne = pg.evaluate("[...document.querySelectorAll('input[placeholder]')].filter((e) => e.offsetParent && getComputedStyle(e).textOverflow !== 'ellipsis').map((e) => e.id || e.name || e.placeholder).slice(0, 6)")
                        check(f'{teil} {tag}: lange Platzhalter enden mit „…“', not ohne, ohne)
                    if dunkel:
                        lg = pg.evaluate(LOGO)
                        # Angebot am Handy: Zurück-Knopf und sechs Aktionen füllen die Kopfzeile – dort bewusst ohne Logo (admin.css)
                        ohne_logo = name == 'angebot' and breite <= 480
                        check(f'{teil} {tag}: Logo weiß ohne helle Fläche', (lg or ohne_logo) and all(x['bg'] in ('rgba(0, 0, 0, 0)', 'transparent') and ('invert' in x['filter'] or 'weiss' in x['src']) for x in lg), lg)
                if breite == 1440 and not dunkel and name == 'angebot':   # Haus = „Start“ (Leiste); die Angebotsseite hat das Symbol aus dem Menü
                    sy = pg.evaluate("['#btn-site', '#menu-more [data-act=open-site]'].map((s) => document.querySelector(s + ' use').getAttribute('href'))")
                    check('angebot: Knopf „Angebotsseite“ mit demselben Symbol wie „Öffentliche Seite öffnen“, nicht dem Haus von „Start“', sy[0] == sy[1] != '#i-home', sy)
                    pg.evaluate("document.querySelector('#vt-angebote').click()"); pg.wait_for_selector('#view-angebote:not([hidden]) .hint a')
                    vw = pg.evaluate("""() => { const ref = document.createElement('button'); ref.className = 'link-btn'; document.querySelector('#view-angebote').append(ref);
                        const r = [getComputedStyle(ref).color, [...document.querySelectorAll('#view-angebote a')].filter((a) => a.offsetParent).map((a) => a.textContent.trim() + ' | ' + getComputedStyle(a).color)]; ref.remove(); return r; }""")
                    check('angebot → Angebote: Verweise in der Farbe aller Verweise (nicht Browser-Blau)', vw[1] and all(x.endswith('| ' + vw[0]) for x in vw[1]), vw)
                if breite == 1440 and not dunkel:
                    check(f'{name}: gemeinsames Zahlenformat geladen (format.js)', pg.evaluate("!!(window.STAFL_FORMAT && window.STAFL_FORMAT.euro)"))
                    check(f'{name}: gemeinsame Suchregel geladen (suche.js)', pg.evaluate("!!(window.STAFL_SUCHE && window.STAFL_SUCHE.findet)"))
                zr = pg.evaluate(ZURUECK)
                if name != 'dashboard':
                    zurueck.setdefault(breite, {})[name] = zr
                    check(f'{name} {tag}: Zurück-Knopf zum Dashboard sichtbar', zr is not None and zr['icon'] and zr['href'] and (zr['href'].rstrip('/').endswith('dashboard') or zr['href'] == 'https://dashboard-stafl.de/'), zr)
            ctx.close()
    # Fingerbedienung (Prüfung am Handy 10.11.2026): mit Finger (pointer: coarse) haben Eingabefelder, Auswahlen und Textfelder
    # auf jeder Seite mindestens 16 px Schrift (sonst zoomt iOS beim Antippen hinein) und kleine Knöpfe (.btn.sm) sind sicher
    # antippbar (rahmen.css); kein waagerechtes Scrollen.
    FINGER = r'''() => { const sicht = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
      const n = (e) => (e.id || e.name || e.className || e.tagName) + ' ' + getComputedStyle(e).fontSize;
      return { finger: matchMedia('(pointer: coarse)').matches,
        eingabe: [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]):not([type=hidden]), select, textarea')]
          .filter((e) => sicht(e) && parseFloat(getComputedStyle(e).fontSize) < 16).map(n).slice(0, 6),
        knopf: [...document.querySelectorAll('.btn.sm')].filter((e) => sicht(e) && e.getBoundingClientRect().height < 32)
          .map((e) => (e.id || e.textContent.trim().slice(0, 20)) + ' ' + Math.round(e.getBoundingClientRect().height)).slice(0, 6),
        // Tippflächen ≥ 36 px: Bestand in der Angebotszeile, „Zum Versand →“, Verweise im Versand
        tipp: [...document.querySelectorAll('.e-bst, .save-state .link-btn, .vs-link')].filter(sicht).map((e) => [e.className, Math.round(e.getBoundingClientRect().height)]) }; }'''
    bestand = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'bestand', 'summen.json'), encoding='utf-8'))
    check('Bestand für die Angebotszeilen übernommen (erfundene Testdaten)', A.call('stock_import', {k: bestand[k] for k in ('date', 'source', 'articles', 'incoming')})[0] == 200)
    fctx = br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='de-DE', timezone_id='Europe/Berlin',
                          extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
    fp = fctx.new_page(); fp.on('pageerror', lambda e: fehler.append(f'{fp.url}: {e}'))
    fp.goto(B + '/admin/'); fp.wait_for_selector('#screen-auth:not([hidden])')
    fp.fill('#au-user', 'admin'); fp.fill('#pw1', PW); fp.click('#auth-submit'); fp.wait_for_selector('#screen-auth', state='hidden')
    for name, bereich, pfad, warte, _ in SEITEN:
        if bereich: als_bereich(fp, bereich)
        fp.goto(B + pfad); fp.wait_for_selector(warte, timeout=20000)
        fp.evaluate('document.fonts.ready.then(() => true)')
        fi = fp.evaluate(FINGER)
        check(f'{name} Handy mit Finger: Eingaben ≥ 16 px (kein Hineinzoomen), kleine Knöpfe antippbar', fi['finger'] and not fi['eingabe'] and not fi['knopf'], fi)
        check(f'{name} Handy mit Finger: kein waagerechtes Scrollen', fp.evaluate('document.documentElement.scrollWidth') <= 390)
        if name in ('angebot', 'versand'):   # Angebot mit Bestand (oben übernommen) zeigt den Bestand-Knopf, der Versand „Im Angebot ansehen“
            fp.wait_for_selector('.e-bst' if name == 'angebot' else '.vs-link')
            fi = fp.evaluate(FINGER)
            check(f'{name} Handy mit Finger: Bestand-Knopf, „Zum Versand“ und Verweise mindestens 36 px hoch', fi['tipp'] and all(h >= 36 for _, h in fi['tipp']), fi['tipp'][:6])
    fctx.close()
    # Bausteine je Reiter jeder Modulseite (Durchsicht 23.11.2026): Tabellenköpfe, Kennzahl-Kacheln, Reiterleiste, Knöpfe,
    # Beschriftungen und Tippflächen in EINER Form auf allen Modulseiten; Farben als --r-* über ein Probe-Element gelesen. PC 1440
    # hell, Handy 390 mit Finger – gemessen ohne Bildschirmfoto (ein Ganzseitenfoto hebt in Chromium die Finger-Emulation auf).
    # Jeder Baustein: JS-Ausdruck (inhalt, sicht, name, tok, finger) → Liste der Abweichungen (null = in Ordnung)
    BAUSTEINE = {}
    BAUSTEINE['tabellenkopf'] = r"""[...inhalt.querySelectorAll('thead th')].filter((e) => sicht(e) && !e.closest('.hr-plan')).map((e) => { const s = getComputedStyle(e);
      return s.fontSize === '11px' && s.fontWeight === '600' && s.textTransform === 'uppercase' && s.color === tok.leise && s.backgroundColor === tok.flaeche2 && !/Mono/.test(s.fontFamily) ? null
        : name(e) + ' ' + s.fontSize + '/' + s.fontWeight + ' ' + s.textTransform + ' ' + s.color + ' auf ' + s.backgroundColor + ' ' + s.fontFamily.slice(0, 14); })"""
    BAUSTEINE['kennzahl'] = r"""[...inhalt.querySelectorAll('.lg-kpi, .rw-kpi, .qm-kpi, .ctl-kpi, .crm-wert, .mkt-wert, .hr-wert, .sic-karte')].filter(sicht).map((e) => {
      const l = e.matches('.sic-karte') ? e.querySelector('.sic-ktitel') : e.querySelector(':scope > span'); if (!l || !sicht(l)) return null;
      const s = getComputedStyle(l), r = getComputedStyle(e).borderTopLeftRadius, farbig = e.matches('.warn, .bad, .minus');
      return s.fontSize === '13px' && s.fontWeight === '500' && s.textTransform === 'none' && (farbig || s.color === tok.leise) && r === '16px' ? null
        : name(e) + ' Beschriftung ' + s.fontSize + '/' + s.fontWeight + ' ' + s.textTransform + ' ' + s.color + ', Kachel ' + r; })"""
    TITEL = {'tabellenkopf': 'Tabellenköpfe 11 px/600 in Großbuchstaben, Schrift --r-leise auf --r-flaeche-2, in Geist (nicht Mono)',
             'kennzahl': 'Kennzahl-Kacheln 16 px rund, Beschriftung 13 px/500 in normaler Schreibweise (--r-leise)'}
    BAUSTEINE['reiterleiste'] = r"""(() => { const l = [...inhalt.querySelectorAll('[role=tablist]')].find(sicht); if (!l) return [];
      const s = getComputedStyle(l), t = [...l.querySelectorAll('[role=tab]')].filter(sicht), a = t.find((b) => b.getAttribute('aria-selected') === 'true'), out = [];
      if (s.backgroundColor !== tok.spur || s.borderTopLeftRadius !== '999px' || s.paddingTop !== '4px') out.push(name(l).slice(0, 20) + ' Spur ' + s.backgroundColor + ' r' + s.borderTopLeftRadius + ' p' + s.paddingTop);
      for (const b of t) { const q = getComputedStyle(b), h = Math.round(b.getBoundingClientRect().height);
        if (h !== 36 || q.fontSize !== '14px' || q.fontWeight !== '600' || q.borderTopLeftRadius !== '999px') out.push(name(b) + ' ' + h + ' px ' + q.fontSize + '/' + q.fontWeight + ' r' + q.borderTopLeftRadius); }
      if (a && getComputedStyle(a).backgroundColor !== tok.flaeche) out.push('gewählt ' + name(a) + ' ' + getComputedStyle(a).backgroundColor);
      return out; })()"""
    BAUSTEINE['knopf'] = r"""[...inhalt.querySelectorAll('.btn, .ci-knopf, .vs-knopf')].filter((e) => sicht(e) && !e.closest('[role=tablist]')).map((e) => {
      const r = getComputedStyle(e).borderTopLeftRadius; return r === '999px' ? null : name(e) + ' r' + r; })"""
    TITEL['reiterleiste'] = 'Reiterleiste als Kapsel (Spur --r-neutral-bg), Reiter 36 px, 14 px/600, gewählt --r-flaeche'
    TITEL['knopf'] = 'Knöpfe als Kapsel wie überall'
    BAUSTEINE['kartenbeschriftung'] = r"""(finger ? [...inhalt.querySelectorAll('td[data-label]')].filter(sicht) : []).map((e) => { const b = getComputedStyle(e, '::before');
      return b.content === 'none' || b.display === 'none' || parseFloat(b.fontSize) >= 11 ? null : name(e).slice(0, 30) + ' ' + b.fontSize; })"""
    TITEL['kartenbeschriftung'] = 'Beschriftungen der Karten-Tabellen am Handy mindestens 11 px'
    # Tippflächen mit Finger: Knöpfe, Verweise, Auswahlen, Felder ≥ 32 px hoch (Verweise im Fließtext und Diagramme ausgenommen),
    # Kästchen ≥ 20 px (wie .check in app.css); Schalter (role=switch) haben ihre eigene Größe
    BAUSTEINE['tippflaeche'] = r"""(finger ? [...inhalt.querySelectorAll('button, a[href], summary, select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), [role=button]')] : [])
      .filter((e) => sicht(e) && !e.closest('svg, .hr-jp-balken, [role=tablist]')).map((e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
        if (e.tagName === 'A' && s.display === 'inline' && e.closest('p, li, td, small')) return null;
        return r.height >= 31.5 ? null : name(e) + ' ' + Math.round(r.width) + '×' + Math.round(r.height); })
      .concat((finger ? [...inhalt.querySelectorAll('input[type=checkbox], input[type=radio]')] : []).filter((e) => sicht(e) && e.getAttribute('role') !== 'switch' && getComputedStyle(e).opacity !== '0')
        .map((e) => e.getBoundingClientRect().width >= 19.5 ? null : name(e) + ' Kästchen ' + Math.round(e.getBoundingClientRect().width)))"""
    TITEL['tippflaeche'] = 'Tippflächen mit Finger mindestens 32 px, Kästchen 20 px'
    TOUR = r"""({ finger }) => { const inhalt = document.querySelector('.r-inhalt');
      const sicht = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && !e.closest('[hidden], dialog, .sr-only, [aria-hidden="true"]'); };
      const name = (e) => (e.id ? '#' + e.id : e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : ''))
        + ' „' + (e.textContent || e.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 24) + '“';
      const p = document.createElement('i'); p.style.cssText = 'color:var(--r-leise);background-color:var(--r-flaeche-2);border-top:1px solid var(--r-neutral-bg);outline:1px solid var(--r-flaeche)';
      document.body.append(p); const ps = getComputedStyle(p), tok = { leise: ps.color, flaeche2: ps.backgroundColor, spur: ps.borderTopColor, flaeche: ps.outlineColor }; p.remove();
      return { /*BAUSTEINE*/ }; }"""
    TOUR = TOUR.replace('/*BAUSTEINE*/', ', '.join(f"'{k}': ({v}).filter(Boolean)" for k, v in BAUSTEINE.items()))
    REITER = r"""(i) => { const l = [...document.querySelectorAll('.r-inhalt [role=tablist]')].find((t) => t.offsetParent && !t.closest('dialog'));
      const t = l ? [...l.querySelectorAll('[role=tab]')].filter((b) => b.offsetParent) : []; if (i >= 0 && t[i]) t[i].click(); return t.length; }"""
    befund = {}
    for breite, finger in ((1440, False), (390, True)):
        tctx = br.new_context(viewport={'width': breite, 'height': 900 if breite > 500 else 844}, is_mobile=finger, has_touch=finger, locale='de-DE',
                              timezone_id='Europe/Berlin', extra_http_headers={'X-Forwarded-For': '198.51.100.40'})
        tp = tctx.new_page(); tp.on('pageerror', lambda e: fehler.append(f'{tp.url}: {e}'))
        tp.goto(B + '/admin/'); tp.wait_for_selector('#screen-auth:not([hidden])')
        tp.fill('#au-user', 'admin'); tp.fill('#pw1', PW); tp.click('#auth-submit'); tp.wait_for_selector('#screen-auth', state='hidden')
        for name, bereich, pfad, warte, _ in SEITEN:
            if not pfad.startswith('/module/'):
                continue
            tp.goto(B + pfad); tp.wait_for_selector(warte, timeout=20000); tp.wait_for_selector('.r-app.r-bereit', timeout=20000)
            for i in range(max(tp.evaluate(REITER, -1), 1)):
                if tp.evaluate(REITER, i):   # Reiter gewählt; die Daten liegen seit dem Laden der Seite vor, gezeichnet wird im nächsten Bild
                    tp.wait_for_function(REITER.replace('if (i >= 0 && t[i]) t[i].click(); return t.length;', "return !!t[i] && t[i].getAttribute('aria-selected') === 'true';"), arg=i)
                tp.evaluate('document.fonts.ready.then(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))))')
                for k, v in tp.evaluate(TOUR, {'finger': finger}).items():
                    befund.setdefault((k, breite, name), []).extend(v)
        tctx.close()
    for (k, breite, name), abw in sorted(befund.items()):
        check(f'{name} {breite} px, alle Reiter: {TITEL[k]}', not abw, sorted(set(abw))[:5])
    # Fenster (Vorgabe des Inhabers 02.11.2026): auf jeder Seite schließt ein Klick neben ein <dialog> es nie, Escape schließt.
    # Jedes Fenster der Seite wird direkt geöffnet (Inhalt egal – geprüft wird das gemeinsame Verhalten), dann wird an einer
    # Stelle außerhalb geklickt (am Handy füllen manche Fenster den Bildschirm – dann nur Escape).
    FENSTER_AUF = r'''(id) => { const d = document.getElementById(id); if (!d || d.open) return null; d.showModal();
      const r = d.getBoundingClientRect(), W = innerWidth, H = innerHeight;
      const p = [[4, 4], [W - 4, 4], [4, H - 4], [W - 4, H - 4], [W / 2, 4], [W / 2, H - 4], [4, H / 2]]
        .find(([x, y]) => x < r.left || x > r.right || y < r.top || y > r.bottom);
      return p || 'voll'; }'''
    OFFEN = "id => document.getElementById(id).open"
    # Aussehen eines offenen Fensters (C2): Unschärfe des Hintergrunds, Rundung, Schatten
    FENSTER_STIL = r'''(id) => { const d = document.getElementById(id), s = getComputedStyle(d);
      return d.classList.contains('modal') || id === 'r-palette' ? [id, getComputedStyle(d, '::backdrop').backdropFilter, s.borderTopLeftRadius, s.boxShadow] : null; }'''
    stile = {}
    # Form jedes Fensters auf jeder Seite im Rahmen (C2): Schleier, Rundung je Ecke, Linie, Schatten, Lage, Kreuz zum Schließen
    FENSTER_FORM = r'''(id) => { const d = document.getElementById(id); d.getAnimations().forEach((a) => a.finish()); if (document.activeElement) document.activeElement.blur();
      const s = getComputedStyle(d), b = getComputedStyle(d, '::backdrop'), r = d.getBoundingClientRect();
      const x = [...d.querySelectorAll('button[aria-label$="chließen"]')].find((e) => e.offsetParent), xr = x && x.getBoundingClientRect(), xs = x && getComputedStyle(x);
      return { id, unschaerfe: b.backdropFilter, schleier: b.backgroundColor, rund: [s.borderTopLeftRadius, s.borderTopRightRadius, s.borderBottomRightRadius, s.borderBottomLeftRadius].join(' '),
               schatten: s.boxShadow, linie: s.borderTopColor, lr: [Math.round(r.left), Math.round(r.right)],
               kreuz: x ? [Math.round(xr.width), Math.round(xr.height), xs.borderTopLeftRadius, xs.backgroundColor].join(' ') : null }; }'''
    formen = {}
    # Hinweise (Toasts) liegen über einem offenen Fenster (oberste Ebene, theme.js) – sonst lägen sie unter dem unscharfen Hintergrund
    TOAST_OBEN = r'''async () => { const t = document.querySelector('[role="status"].toast, [role="status"][class*="-toast"]');
      const d = document.querySelector('dialog[id]:not([open])'); if (!t || !d) return 'ohne';
      let neu = 0; const f = (e) => { if (e.newState === 'open') neu++; }; t.addEventListener('toggle', f);
      d.showModal(); await new Promise((r) => setTimeout(r, 80)); t.removeEventListener('toggle', f); d.close();
      return t.matches(':popover-open') && neu > 0; }'''
    for breite in (1440, 390):
        ctx, pg = neue_seite(breite, False)
        for name, bereich, pfad, warte, _ in SEITEN + [('kundenseite', None, '/', 'html[data-bereit="1"]', [])]:
            pg.unroute('**/api/?action=status*')
            if bereich: als_bereich(pg, bereich)
            pg.goto(B + pfad); pg.wait_for_selector(warte, timeout=20000)
            ids = pg.evaluate("[...document.querySelectorAll('dialog[id]')].map((d) => d.id)")
            if breite == 1440:
                oben = pg.evaluate(TOAST_OBEN)
                check(f'{name}: Hinweise (Toast) erscheinen über einem offenen Fenster', oben in (True, 'ohne'), oben)
            if breite == 1440 and (bereich or name == 'dashboard'):   # Suche (Strg K) wie jedes Fenster
                pg.wait_for_selector('#r-suche'); pg.keyboard.press('Control+k'); pg.wait_for_selector('#r-palette[open]')
                stile.setdefault(name, []).append(pg.evaluate(FENSTER_STIL, 'r-palette'))
                formen.setdefault((breite, name), []).append(pg.evaluate(FENSTER_FORM, 'r-palette')); pg.keyboard.press('Escape')
            per_klick, nicht_esc = [], []
            for i in ids:
                p = pg.evaluate(FENSTER_AUF, i)
                if p is None:
                    continue
                if name != 'kundenseite':   # Kundenseite: eigenes Aussehen („Liquid Glass“)
                    formen.setdefault((breite, name), []).append(pg.evaluate(FENSTER_FORM, i))
                if breite == 1440 and bereich and pg.evaluate(FENSTER_STIL, i):
                    stile.setdefault(name, []).append(pg.evaluate(FENSTER_STIL, i))
                if p != 'voll':
                    pg.mouse.click(p[0], p[1])
                    if not pg.evaluate(OFFEN, i):
                        per_klick.append(i); continue
                pg.keyboard.press('Escape')
                if pg.evaluate(OFFEN, i):
                    nicht_esc.append(i); pg.evaluate("id => document.getElementById(id).close()", i)
            check(f'{name} {breite} px: Klick neben ein Fenster schließt es nicht ({len(ids)} Fenster)', not per_klick, per_klick)
            check(f'{name} {breite} px: Escape schließt jedes Fenster', not nicht_esc, nicht_esc)
        ctx.close()
    # Fenster und Suche im Eingabebereich wie die Suche des Dashboards (rahmen.css): ohne Unschärfe, gleiche Rundung und Schatten
    ref = stile['dashboard'][0]
    for name in ('angebot', 'verwaltung', 'bestand'):
        abw = [x for x in stile.get(name, []) if x[1:] != ref[1:]]
        check(f'{name}: Fenster und Suche wie im Rahmen ({len(stile.get(name, []))}: ohne Unschärfe, {ref[2]}, Schatten der Suche)', len(stile.get(name, [])) > 1 and not abw, (ref, abw[:4]))
    # Alle Seiten im Rahmen, alle Fenster (Durchsicht 23.11.2026): Bezug ist die Suche des Dashboards (rahmen.css)
    suche = next(f for f in formen[(1440, 'dashboard')] if f['id'] == 'r-palette')
    for (breite, name), liste in sorted(formen.items()):
        glas = [(f['id'], f['unschaerfe'], f['schleier']) for f in liste if f['unschaerfe'] != 'none' or f['schleier'] != suche['schleier']]
        check(f'{name} {breite} px: Hintergrund jedes Fensters nur abgedunkelt wie bei der Suche, ohne Unschärfe ({len(liste)} Fenster)', not glas, glas[:4])
        if breite == 390:   # am Handy jedes Fenster über die ganze Breite (Suche und Hinweis „Dashboard als Startseite“ schweben)
            schmal = [(f['id'], f['lr']) for f in liste if f['id'] not in ('r-palette', 'db-sp') and (abs(f['lr'][0]) > 1 or abs(f['lr'][1] - 390) > 1)]
            check(f'{name} 390 px: jedes Fenster so breit wie der Bildschirm', not schmal, schmal)
        # eine Fensterform: PC 16 px mit Linie und Schatten der Suche; Handy Blatt von unten (20 px oben) oder ganz (0 px)
        if breite == 1440:
            anders = [(f['id'], f['rund'], f['linie'], f['schatten']) for f in liste if (f['rund'], f['linie'], f['schatten']) != (suche['rund'], suche['linie'], suche['schatten'])]
        else:
            anders = [(f['id'], f['rund']) for f in liste if f['id'] not in ('r-palette', 'db-sp') and f['rund'] not in ('20px 20px 0px 0px', '0px 0px 0px 0px')]
        check(f'{name} {breite} px: Fenster in der Form des Rahmens', not anders, anders[:4])
        kreuze = {f['kreuz'] for f in liste if f['kreuz']}
        check(f'{name} {breite} px: Kreuz zum Schließen wie bei der Suche ({suche["kreuz"]})', kreuze <= {suche['kreuz']}, kreuze)
    ctx, pg = neue_seite(1440, False)   # Menüs im Eingabebereich (Mehr, Drucken) wie Fenster und Suche
    als_bereich(pg, 'angebot.eingabe'); pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-editor:not([hidden])')
    me = pg.evaluate("""() => { const m = document.querySelector('#menu-more'); m.hidden = false; const s = getComputedStyle(m);
      const r = [s.borderTopLeftRadius, s.borderTopColor, s.boxShadow]; m.hidden = true; return r; }""")
    check('Eingabebereich: Menü „Mehr“ in der Form der Fenster und der Suche', me == [suche['rund'].split(' ')[0], suche['linie'], suche['schatten']], (me, suche))
    pg.unroute_all(behavior='ignoreErrors'); ctx.close()   # Statusabfrage noch unterwegs: Umleitung ohne Fehler beenden
    # Getippte Eingaben: erstes Escape zeigt den gemeinsamen Hinweis (theme.js), zweites schließt – hier am Formular
    # „Korrektur melden“ (HR) und „Neue Kampagne“ (Marketing) stellvertretend für alle Formularfenster
    ctx, pg = neue_seite(1440, False)
    for pfad, dlg, feld in (('/module/hr/', 'dlg-korrektur', '#korrektur-text'), ('/module/marketing/', 'dlg-kampagne', '#kp-name')):
        pg.goto(B + pfad); pg.wait_for_function("document.readyState === 'complete'")
        pg.evaluate("id => document.getElementById(id).showModal()", dlg)
        pg.fill(feld, 'Test – noch nicht gespeichert')
        pg.keyboard.press('Escape')
        warn = pg.evaluate("id => [document.getElementById(id).open, (document.querySelector('#stafl-hinweis') || {}).textContent || '']", dlg)
        pg.keyboard.press('Escape')
        zu = not pg.evaluate("id => document.getElementById(id).open", dlg)
        check(f'{dlg}: getippt → erstes Escape warnt, zweites schließt', warn[0] and 'noch nicht gespeichert' in warn[1] and zu, (warn, zu))
    # Speichern schlägt fehl (Server 500): die Eingaben bleiben geschützt – Escape warnt weiter, die Meldung ist sichtbar
    pg.goto(B + '/module/hr/'); pg.wait_for_function("document.readyState === 'complete'")
    pg.route('**/api/?action=hr_korrektur*', lambda r: r.fulfill(status=500, json={'error': 'Testfehler'}))
    pg.evaluate("document.getElementById('dlg-korrektur').showModal()")
    pg.fill('#korrektur-text', 'Am 10.09. war ich im Urlaub')
    pg.click('#korrektur-senden'); pg.wait_for_function("document.querySelector('#korrektur-meldung').textContent.trim() !== ''")
    pg.keyboard.press('Escape')
    offen = pg.evaluate("document.getElementById('dlg-korrektur').open")
    pg.keyboard.press('Escape')
    check('Speichern fehlgeschlagen: erstes Escape warnt weiter, Eingaben bleiben', offen and pg.evaluate("!document.getElementById('dlg-korrektur').open"), offen)
    pg.unroute('**/api/?action=hr_korrektur*')
    # Fenster ohne <form>: Notiz/Bemerkung im Textfeld ist ebenso geschützt (Kundenseite „Bestellwunsch prüfen“ steht für alle)
    pg.evaluate("""() => { const d = document.createElement('dialog'); d.id = 't-ohne-form'; d.innerHTML = '<textarea id="t-notiz"></textarea>';
      document.body.appendChild(d); d.showModal(); }""")
    pg.fill('#t-notiz', 'Bitte bis 10 Uhr'); pg.keyboard.press('Escape')
    check('Fenster ohne Formular: getippte Notiz → erstes Escape warnt', pg.evaluate("document.getElementById('t-ohne-form').open"))
    ctx.close()
    # Aufklappliste (<details data-menue>) am Handy ganz im Bild, auch wenn ihr Titel weit rechts steht (theme.js)
    ctx, pg = neue_seite(390, False)
    pg.goto(B + '/module/crm/'); pg.wait_for_function("document.readyState === 'complete'")
    pg.evaluate("""() => { const d = document.createElement('details'); d.setAttribute('data-menue', ''); d.className = 'crm-mehrfach'; d.id = 't-menue';
      Object.assign(d.style, { position: 'absolute', left: '200px', top: '300px', zIndex: '99' });
      d.innerHTML = '<summary>Wann: alle</summary><div class="optionen">Liste</div>'; document.body.appendChild(d); d.open = true; }""")
    pg.wait_for_function("document.querySelector('#t-menue .optionen').style.left !== ''")
    lr = pg.evaluate("(() => { const r = document.querySelector('#t-menue .optionen').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), innerWidth]; })()")
    check('390 px: aufgeklappte Liste bleibt ganz im Bild', lr[0] >= 0 and lr[1] <= lr[2], lr)
    # Zahlen und Einheiten (02.11.2026): ein Format für alle Seiten (docs/entwickler/10-konventionen.md)
    ctx, pg = neue_seite(1280, False)
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    FORMATE = pg.evaluate('''() => { const F = window.STAFL_FORMAT; return {
      euro: F.euro(1234.5), euroNeg: F.euro(-3.456), euroNull: F.euro(0), leer: F.euro(null), kachel: F.euroKachel(123456789), kachelKlein: F.euroKachel(9876543.21),
      kg: F.kg(1782.5), kgSumme: F.kgSumme(1782.5), kgKlein: F.kgSumme(12.34), preis: F.euroKg(12.3), preis3: F.euroKg(12.345), preisCent: F.euroKg(4.125),
      prozent: F.prozent(0.1234), plus: F.veraenderung(0.05), minus: F.veraenderung(-0.05), null: F.veraenderung(0), pp: F.pp(0.012),
      diff: F.differenz(0.5, '€/kg'), datum: F.datum('2026-11-02'), zeit: F.datumZeit('2026-11-02T13:05:00Z'), kw: F.kw(45, 2026),
      glatt: F.glatt ? [1.005 * 100, 4.245 * 100, 2.675 * 100, -1.005 * 100, -100.5, 100.4].map(F.glatt).join(' ') : 'fehlt' }; }''')
    ERWARTET = {'euro': '1.234,50 €', 'euroNeg': '−3,46 €', 'euroNull': '0,00 €', 'leer': '—', 'kachel': '123,46 Mio. €', 'kachelKlein': '9.876.543,21 €',
                'kg': '1.782,50 kg', 'kgSumme': '1.783 kg', 'kgKlein': '12,3 kg', 'preis': '12,30 €/kg', 'preis3': '12,35 €/kg', 'preisCent': '4,13 €/kg',
                'prozent': '12,3 %', 'plus': '+5,0 %', 'minus': '−5,0 %', 'null': '±0,0 %', 'pp': '+1,2 Pp',
                'diff': '+0,50 €/kg', 'datum': '02.11.2026', 'zeit': '02.11.2026, 14:05', 'kw': 'KW 45/2026',
                'glatt': '101 425 268 -101 -101 100'}   # wie PHP round(): Cent ohne Binärfehler, halbe von der Null weg
    abw = {k: (FORMATE.get(k), v) for k, v in ERWARTET.items() if FORMATE.get(k) != v}
    check('Zahlenformat: Beträge, kg, €/kg, Prozent, Datum und KW wie vereinbart, glatt() rundet wie der Server', not abw, abw)
    # Suchregel (10.11.2026): eine Regel für alle Suchfelder (app/assets/suche.js, serverseitig such_passt in lib/kern.php)
    SUCHE = pg.evaluate('''() => { const S = window.STAFL_SUCHE; return {
      umlaut: S.findet('muller', 'Müller GmbH'), ausgeschrieben: S.findet('Mueller', 'Müller GmbH') && S.findet('faerse', 'Färse HV') && S.findet('müller', 'Mueller KG'),
      eszett: S.findet('Strasse', 'Hauptstraße 3') && S.findet('straße', 'Hauptstrasse 3'), akzent: S.findet('cafe', 'Café Crème'), gross: S.findet('RIND', 'Rinderfilet'),
      woerter: S.findet('filet rind', 'Rinderfilet 4/5 lbs.') && S.findet('eiche  hamburg ', 'Gasthaus Eiche', '20095', 'Hamburg'), nichtAlle: !S.findet('eiche berlin', 'Gasthaus Eiche', 'Hamburg'),
      nummer: S.findet('0401234567', '040 12 34-567') && S.findet('040/1234567', '040 1234567'), feldgrenze: !S.findet('0012', '900001', '20095') && !S.findet('eichehamburg', 'Eiche', 'Hamburg'),
      leer: S.findet('   ', 'x') && S.findet('', null), leereFelder: S.findet('a', null, undefined, '', 'a'), zahlFeld: S.findet('123', 123),
      vorbereitet: S.passt(S.woerter('nord fleisch'), S.heu('Musterfleischerei Nord GmbH')) }; }''')
    check('Suchregel: Umlaute (auch ausgeschrieben), ß/ss, Akzente, mehrere Wörter, gegliederte Nummern, nie über Feldgrenzen, leere Suche', all(SUCHE.values()), SUCHE)
    ctx.close()
    # Seiten ohne Mitarbeiteranmeldung: Abmeldeseite, Kundenseite, Rechtsseiten – Logo im Dunkeln weiß, nichts abgeschnitten
    for breite in (1440, 390):
        for dunkel in (False, True):
            ctx = br.new_context(viewport={'width': breite, 'height': 900}, is_mobile=breite < 500, color_scheme='dark' if dunkel else 'light',
                                 extra_http_headers={'X-Forwarded-For': '198.51.100.41'}, locale='de-DE')
            pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(f'{pg.url}: {e}'))
            tag = f'{"dunkel" if dunkel else "hell"}-{breite}'
            for name, pfad, warte in (('abgemeldet', '/dashboard/abgemeldet.html', 'img.r-logo'), ('kundenseite', '/', '.brand-logo'),
                                      ('kontakt', '/kontakt/', '.legal-logo')):
                pg.goto(B + pfad); pg.wait_for_selector(warte)
                pg.evaluate('document.fonts.ready.then(() => true)')
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
    # Einfache Darstellung (Remote-Desktop, 02.11.2026)
    OHNE_GLAS = "() => [...document.querySelectorAll('*')].filter((e) => { const s = getComputedStyle(e); return s.backdropFilter && s.backdropFilter !== 'none'; }).length"
    ctx, pg = neue_seite(1280, False)
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    # Dashboard im Rahmen „C2“ (06.11.2026): ohne Glas – Effekte dort sind nur noch Übergänge
    BEWEGT = "getComputedStyle(document.querySelector('a.db-tile')).transitionDuration !== '0s'"
    check('Einfache Darstellung: unter Automatisierung keine Erkennung – Effekte (Übergänge) wie bisher', pg.get_attribute('html', 'data-darstellung') is None
          and pg.evaluate(BEWEGT) and pg.get_attribute('#db-darstellung', 'aria-pressed') == 'false' and pg.is_hidden('#db-darstellung-hinweis'))
    with pg.expect_response(lambda r: 'action=theme_save' in r.url) as antwort:
        pg.click('#db-darstellung')
    st = A.call('status')[1]['user']
    check('Dashboard: Knopf schaltet die einfache Darstellung ein und speichert sie am Konto (Hell/Dunkel bleibt)', antwort.value.status == 200
          and pg.get_attribute('html', 'data-darstellung') == 'einfach' and pg.get_attribute('#db-darstellung', 'aria-pressed') == 'true'
          and st.get('darstellung') == 'einfach' and st.get('theme') == 'light', st)
    check('Einfach: keine Unschärfe, keine Übergänge, Hinweis „Ihre Wahl“', pg.evaluate(OHNE_GLAS) == 0
          and pg.evaluate("getComputedStyle(document.querySelector('.db-tile')).transitionDuration") == '0s' and 'Ihre Wahl' in pg.inner_text('#db-darstellung-hinweis'))
    pg.screenshot(path=f'{SH}/einheit-dashboard-einfach-1280.png')
    ctx.close()
    ctx, pg = neue_seite(1280, False)   # frischer Browser: Wahl kommt vom Konto
    pg.wait_for_function("() => document.documentElement.dataset.darstellung === 'einfach'")
    check('Eingabebereich übernimmt die einfache Darstellung vom Konto (ohne Glas, ohne Farbflächen)', pg.evaluate(OHNE_GLAS) == 0
          and pg.evaluate("getComputedStyle(document.body, '::before').display") == 'none')
    pg.evaluate('localStorage.clear()')
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#hr-app:not([hidden])')
    pg.wait_for_function("() => document.documentElement.dataset.darstellung === 'einfach'")
    check('HR übernimmt sie vom Konto', pg.evaluate(OHNE_GLAS) == 0 and pg.evaluate("getComputedStyle(document.querySelector('.hr-bg')).display") == 'none')
    pg.screenshot(path=f'{SH}/einheit-hr-einfach-1280.png')
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    with pg.expect_response(lambda r: 'action=theme_save' in r.url):
        pg.click('#db-darstellung')
    check('Ausschalten: entspricht der Erkennung dieses Geräts → wieder „automatisch“', pg.get_attribute('html', 'data-darstellung') is None
          and A.call('status')[1]['user'].get('darstellung') == '')
    ctx.close()
    ctx, pg = neue_seite(1280, False)
    ctx.add_init_script("Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false })")   # wie ein normaler Browser
    pg.goto(B + '/dashboard/'); pg.wait_for_selector('#db-grid .db-tile')
    check('Automatisch: Browser ohne Grafikkarte (Software-Darstellung) → einfach, mit Hinweis', pg.get_attribute('html', 'data-darstellung') == 'einfach'
          and 'automatisch' in pg.inner_text('#db-darstellung-hinweis') and '"software":true' in (pg.evaluate("localStorage.getItem('stafl.grafik')") or ''))
    with pg.expect_response(lambda r: 'action=theme_save' in r.url):
        pg.click('#db-darstellung')
    check('Automatisch erkannt, aber ausgeschaltet → „Effekte“ am Konto', pg.get_attribute('html', 'data-darstellung') is None
          and A.call('status')[1]['user'].get('darstellung') == 'effekte' and pg.evaluate(BEWEGT))
    ctx.close()
    check('Einfache Darstellung: ungültiger Wert und leere Anfrage abgewiesen', A.call('theme_save', {'darstellung': 'bunt'})[0] == 422 and A.call('theme_save', {})[0] == 422)
    check('Zurück auf „automatisch“', A.call('theme_save', {'darstellung': ''})[0] == 200 and A.call('status')[1]['user'].get('darstellung') == '')
    check('Ungültige Darstellung abgewiesen', A.call('theme_save', {'theme': 'pink'})[0] == 422)
    check('Ohne Anmeldung nicht speicherbar', Client('198.51.100.77').call('theme_save', {'theme': 'dark'})[0] in (401, 403))
    check('Zurück auf „wie das Gerät“', A.call('theme_save', {'theme': ''})[0] == 200 and A.call('status')[1]['user'].get('theme') == '')
    for breite, je in zurueck.items():
        # gleiche Form: Höhe, Breite (Pfeil und „Start“, am Handy nur der Pfeil – auf jedem Host gleich), Rundung, Schrift, Schriftfarbe, Pfeil
        # Schriftfarbe: gleicher Farbton (kleine Abweichungen der Textfarbe zwischen Eingabebereich und Modulen zählen nicht)
        ton = lambda c: tuple(round(int(x) / 16) for x in re.findall(r'\d+', c or '')[:3])   # noqa: E731
        formen = {json.dumps({k: (ton(v) if k == 'farbe' else v) for k, v in (z or {}).items() if k in ('h', 'w', 'radius', 'font', 'icon', 'text', 'farbe')}, sort_keys=True) for z in je.values()}
        check(f'{breite} px: Zurück-Knopf auf allen Modulseiten gleich', len(formen) == 1, je)
        # Kopf der Modulseiten (Container-Import und Versand aus den Bausteinen des Rahmens, die übrigen mit eigenem Kopf): „Start“ an
        # derselben Stelle (± 3 px), daneben Symbol und Name gleich groß und mittig zum Knopf
        mods = {n: z for n, z in je.items() if z and n not in ('angebot', 'verwaltung', 'bestand')}
        ref = mods['hr']
        abw = {n: (z['x'], z['y'], z['titel']) for n, z in mods.items() if abs(z['x'] - ref['x']) > 3 or abs(z['y'] - ref['y']) > 3 or z['titel'] != ref['titel'] or not z['titel'][2]}
        check(f'{breite} px: Kopf aller Modulseiten gleich („Start“ an derselben Stelle, Symbol und Name daneben gleich groß, {len(mods)} Seiten)', len(mods) == 10 and not abw, (ref['x'], ref['y'], ref['titel'], abw))
    check('keine Seitenfehler', not fehler, fehler[:4])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
