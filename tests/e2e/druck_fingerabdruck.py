"""Fingerabdruck des Angebotsdrucks (Inhaber 26.11.2026: „damit das nun immer gleich bleibt“) – gemeinsam für die Testgruppen
druck, angebot_design und preisaenderung.

Festgehalten werden Lage und Größe jedes Bausteins je Seite (Kopf, Balken, Blöcke, Gruppen, Zeilen, Spalten der ersten Zeile je
Block, Preisänderung ▼/▲/Pfeil, Fuß; in den Hochformat-Layouts „Kompakt“ und „Tabelle“ Gruppen, Zeilen und Tabellenzeilen) und die Stile jeder
Bausteinart (Schrift, Farben, Rahmen, Abstände). Verglichen wird mit einer Referenz unter tests/fixtures/angebote/: jede
Abweichung über TOLERANZ px oder jede Stiländerung schlägt an und wird benannt („Stil gruppe.al-gt paddingTop: 0px → 2px“).

Ziffern im Kopf und im Seitentext (Datum, Angebotsnummer, Stand) zählen nicht mit: sie ändern sich je Tag, der Satz nicht.
Unsichtbare Rahmen (Breite 0) zählen als „kein Rahmen“ – ihre Farbe unterscheidet sich je Chromium-Fassung.

Gewollte Änderung am Druck (nur mit Freigabe des Inhabers, der Druck geht an Kunden):
  WA_DRUCK_REFERENZ=neu python3 tests/run_e2e.py druck angebot_design preisaenderung
mit der Playwright-Fassung aus tests/requirements.txt (wie die CI), die geänderte Referenz im PR begründen. Lage und Größe gelten
für die Chromium-Fassung der Referenz; mit einer anderen Fassung prüft der Test nur Kennzahlen und Stile (Hinweis im Protokoll).
Wird Playwright in tests/requirements.txt erhöht, die Referenzen im selben PR neu schreiben. In der CI (Variable CI)
wird nie eine Referenz geschrieben.
"""
import json
import os

TOLERANZ = 0.6   # px auf der Satzfläche: Rundung, kein sichtbarer Unterschied
ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fixtures', 'angebote')

FINGER = """() => {
  const D = document.querySelector('#print-root > .pl-doc, #print-root > .p-doc, #print-root .pl-doc, #print-root .p-doc');
  if (!D) return null;
  const ART = [['seite', '.pl-page'], ['kopf', '.pl-ph, .p-head'], ['logo', 'img.al-logo, img.p-logo'], ['werbung', '.werb-sec'], ['fest', '.pl-fest'],
    ['band', '.al-band'], ['balken', '.al-st'], ['block', '.al-grp'], ['gruppe', '.al-gt'], ['zeile', 'tr.row'], ['vergleich', '.vw'],
    ['abschnitt-h', '.p-section'], ['gruppe-h', '.p-group'], ['gruppenkopf-h', '.p-gh, .p-gt'], ['zeile-h', '.p-row'], ['tabelle-h', '.p-table'],
    ['tabzeile-h', '.p-table tr'], ['hinweis-h', '.al-note, .p-note'],
    ['fuss', '.pl-fuss'], ['hinweis', '.pl-hinweis'], ['brief', '.pl-brief'], ['siegel', '.pl-siegel']];
  const ZELLEN = ['td.c-code', 'td.c-name', 'td.c-price'];
  const PROPS = ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'lineHeight', 'letterSpacing', 'textTransform', 'textAlign', 'whiteSpace', 'color',
    'backgroundColor', 'borderRadius', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft'];
  const rahmen = (c, s) => (c['border' + s + 'Style'] === 'none' || parseFloat(c['border' + s + 'Width']) === 0 ? 'kein' : `${c['border' + s + 'Width']} ${c['border' + s + 'Style']} ${c['border' + s + 'Color']}`);
  const r1 = (v) => Math.round(v * 10) / 10;
  const txt = (art, e) => { const t = (e.textContent || e.getAttribute('alt') || '').replace(/\\s+/g, ' ').trim().slice(0, 28); return art === 'kopf' || art === 'seite' ? t.replace(/\\d/g, '#') : t; };
  const stile = {};
  const stil = (art, e) => { const k = art + (e.classList.length ? '.' + [...e.classList].sort().join('.') : ''); if (!stile[k]) { const c = getComputedStyle(e);
    stile[k] = Object.fromEntries(PROPS.map((p) => [p, c[p]]).concat(['Top', 'Right', 'Bottom', 'Left'].map((x) => ['border' + x, rahmen(c, x)]))); } };
  const pages = D.querySelectorAll('.pl-page').length ? [...D.querySelectorAll('.pl-page')] : [D];
  const seiten = pages.map((p) => {
    const pb = p.getBoundingClientRect(), out = [];
    // Preisänderung ▼/▲: die Zeichen fehlen in Geist, der Browser nimmt eine Systemschrift (je Rechner verschieden breit); der Hinweis
    // steht absolut und nimmt keinen Platz – Breite und waagerechte Lage zählen deshalb nicht, Höhe, senkrechte Lage, Text und Stil schon.
    // Unsichtbare Bausteine (ohne Box): Lage 0, 0 – sonst hinge sie am Seitenursprung.
    const ohneBreite = (art) => art === 'vergleich';
    const rein = (art, e) => { const b = e.getBoundingClientRect(), w = !ohneBreite(art), da = e.getClientRects().length > 0;
      out.push([art, txt(art, e), w && da ? r1(b.left - pb.left) : 0, da ? r1(b.top - pb.top) : 0, w ? r1(b.width) : 0, r1(b.height)]); stil(art, e); };
    for (const [art, sel] of ART) for (const e of (p.matches(sel) ? [p] : p.querySelectorAll(sel))) rein(art, e);
    // Spalten: erste Zeile je Block bzw. Gruppe/Tabelle mit Lage, alle Zeilen für die Stile
    for (const g of p.querySelectorAll('.al-grp')) { const z = g.querySelector('tr.row'); if (z) for (const sel of ZELLEN) { const c = z.querySelector(sel); if (c) rein(sel.slice(5), c); } }
    for (const g of p.querySelectorAll('.p-group')) { const z = g.querySelector('.p-row'); if (z) [...z.children].forEach((c) => rein('teil-h', c)); }
    for (const t of p.querySelectorAll('.p-table tbody')) { const z = t.querySelector('tr:not(.gr):not(.sr)'); if (z) [...z.children].forEach((c) => rein('zelle-h', c)); }
    for (const z of p.querySelectorAll('tr.row')) for (const sel of ZELLEN) { const c = z.querySelector(sel); if (c) stil(sel.slice(5), c); }
    return out;
  });
  const z = parseFloat(getComputedStyle(D).getPropertyValue('--z'));
  return { meta: { seiten: seiten.length, stufe: D.dataset.stufe || '', spalten: +(D.dataset.spalten || 0), z: Number.isFinite(z) ? r1(z * 1000) / 1000 : 1 }, stile, seiten };
}"""


# Wächter 1: keine Regel eines anderen Stylesheets (app.css …) trifft ein Element des Drucks – der Druck hat seine Regeln nur in
# angebot-druck.css (Trennung 26.11.2026). Geprüft wird je Selektor, unabhängig vom Medium (auch Handy-, Dunkel- und Bildschirmregeln),
# in mehreren Zuständen der Seite (ZUSTAENDE) und mit einer Probe seltener Druckbausteine (PROBE).
FREMD = """() => {
  const R = document.querySelector('#print-root'), els = [R, ...R.querySelectorAll('*')], out = [];
  const ohnePseudo = (s) => s.replace(/::?(before|after|marker|placeholder|selection|first-line|first-letter|backdrop|-webkit-[a-z-]+)\\b(\\([^)]*\\))?/g, '');
  const teile = (s) => { const t = []; let tiefe = 0, a = 0; for (let i = 0; i < s.length; i++) { const c = s[i];
    if (c === '(' || c === '[') tiefe++; else if (c === ')' || c === ']') tiefe--; else if (c === ',' && !tiefe) { t.push(s.slice(a, i)); a = i + 1; } } t.push(s.slice(a)); return t.map((x) => x.trim()); };
  const gehe = (rs, quelle) => { for (const r of rs) { if (r.cssRules && !r.selectorText) { gehe(r.cssRules, quelle); continue; } if (!r.selectorText) continue;
    for (const s of teile(r.selectorText)) { try { if (els.some((e) => e.matches(ohnePseudo(s) || '*'))) out.push(quelle + ': ' + s); } catch (f) { out.push(quelle + ': nicht lesbar ' + s); } } } };
  for (const sh of document.styleSheets) { const q = (sh.href || 'eingebettet').replace(/^.*\\//, '').replace(/\\?.*$/, ''); if (q === 'angebot-druck.css') continue; try { gehe(sh.cssRules, q); } catch {} }
  return [...new Set(out)];
}"""
# Zustände der Seite, unter denen Wächter 1 zusätzlich prüft (Regeln, die nur dann greifen): ausdrücklich dunkel/hell, einfache
# Darstellung, bestellberechtigter Kunde, Designvorschau
ZUSTAENDE = [[], [['H', 'data-theme', 'dark']], [['H', 'data-theme', 'light']], [['H', 'data-darstellung', 'einfach']], [['B', 'class', 'can-order']],
             [['H', 'class', 'druckansicht']]]
ZUSTAND = """(zu) => { const H = document.documentElement, B = document.body;
  H.removeAttribute('data-theme'); H.removeAttribute('data-darstellung'); B.classList.remove('can-order'); H.classList.remove('druckansicht');
  for (const [w, a, v] of zu || []) { const e = w === 'H' ? H : B; if (a === 'class') e.classList.add(v); else e.setAttribute(a, v); } }"""
# Probe für Wächter 1: seltene Bausteine des Drucks, die in den Testdaten nicht vorkommen (Partie mit MHD im Einzelangebot,
# Suchtreffer <mark>, gestapelte Werbung, Sonderpreis mit altem Preis, „a. Anfr.“). Neue seltene Druckbausteine hier ergänzen.
PROBE = """(an) => { document.querySelectorAll('[data-druckprobe]').forEach((e) => e.remove()); if (!an) return;
  const D = document.querySelector('#print-root .pl-doc, #print-root .p-doc') || document.querySelector('#print-root');
  const p = document.createElement('div'); p.dataset.druckprobe = '1';
  p.innerHTML = '<div class="werb-duo werb-stapel"><div class="werb-sec"></div></div><table class="al-tab"><tbody><tr class="row"><td class="c-code"><mark>1</mark></td>'
    + '<td class="c-name">x <span class="partie al-partie"><span>P</span> · <span>MHD</span></span></td><td class="c-price al-np"><span class="al-was">2</span><span class="al-sale">1</span></td></tr></tbody></table>';
  D.appendChild(p); }"""
# Wächter 2 (Störversuch): fremde Farben, Schriften, Größen und Abstände an :root und body – der Druck muss gleich bleiben
STOER_CSS = ('--accent --accent-line --accent-soft --line --muted --muted-fein --sale --sale-bg --surface --surface-2 --surface-3 --text --text-2 '
             '--vw-g --vw-n --vw-t --aus --zebra --linie --regel').split()
STOER = """([an, regeln]) => { document.getElementById('__stoer')?.remove(); if (!an) return;
  const s = document.createElement('style'); s.id = '__stoer'; s.textContent = `:root, html, body { ${regeln} }`; document.head.appendChild(s); }"""
STOER_REGELN = (' '.join(f'{n}: rgb(0, 200, 0) !important;' for n in STOER_CSS)
                + ' --font: serif !important; --mono: cursive !important; --r: 40px !important; --r-lg: 40px !important; --shadow: 0 0 9px red !important;'
                + ' font: italic 700 22px/3 serif !important; letter-spacing: 2px !important; word-spacing: 9px !important; text-transform: uppercase !important;'
                + ' color: rgb(0, 200, 0) !important; text-align: center !important; hyphens: auto !important; font-feature-settings: "smcp" !important; text-indent: 3em !important;')


def vergleich(alt, neu, lage=True):
    """Abweichungen in Alltagssprache (leer = gleich); lage=False: nur Kennzahlen und Stile"""
    d = []
    if alt['meta'] != neu['meta']: d.append(f"Kennzahlen: {alt['meta']} → {neu['meta']}")
    for k in sorted(set(alt['stile']) | set(neu['stile'])):
        a, b = alt['stile'].get(k), neu['stile'].get(k)
        if a is None or b is None: d.append(f"Bausteinart {k}: {'neu' if a is None else 'fehlt'}"); continue
        d += [f"Stil {k} {p}: {a[p]} → {b.get(p)}" for p in a if a[p] != b.get(p)]
    for i, (sa, sb) in enumerate(zip(alt['seiten'], neu['seiten']) if lage else []):
        if len(sa) != len(sb): d.append(f"Seite {i + 1}: {len(sa)} → {len(sb)} Bausteine"); continue
        for x, y in zip(sa, sb):
            if x[:2] != y[:2]: d.append(f"Seite {i + 1}: {x[0]} „{x[1]}“ → {y[0]} „{y[1]}“"); break
            if any(abs(u - v) > TOLERANZ for u, v in zip(x[2:], y[2:])): d.append(f"Seite {i + 1}, {x[0]} „{x[1]}“: x/y/Breite/Höhe {x[2:]} → {y[2:]}")
    return d


class Fingerabdruck:
    """f = Fingerabdruck('druck-fingerabdruck.json', check); f.nehmen(pg, 'wochenangebot') nach dem Setzen; am Ende f.pruefen(browser)"""

    def __init__(self, datei, check):
        self.datei, self.check, self.varianten, self.fremd, self.stoer = os.path.join(ORDNER, datei), check, {}, {}, {}

    def nehmen(self, pg, variante, medium_zurueck=False):
        pg.wait_for_function("[...document.querySelectorAll('#print-root img')].every((i) => i.complete)")
        pg.evaluate('document.fonts.ready')
        pg.emulate_media(media='print')
        self.varianten[variante] = pg.evaluate(FINGER)
        pg.evaluate(PROBE, True); fremd = set()
        for zu in ZUSTAENDE: pg.evaluate(ZUSTAND, zu); fremd |= set(pg.evaluate(FREMD))
        pg.evaluate(ZUSTAND, []); pg.evaluate(PROBE, False)
        self.fremd[variante] = sorted(fremd)
        # Vergleich gegen eine Messung nach neutraler Neuberechnung (leere Störung): der zweispaltige Satz „Kompakt“ (column-fill: balance)
        # verteilt nach jeder Neuberechnung der Seite etwas anders – unabhängig vom Inhalt; gezählt wird nur, was die fremden Werte bewirken
        pg.evaluate(STOER, [True, '--neutral: 0;']); neutral = pg.evaluate(FINGER)
        pg.evaluate(STOER, [True, STOER_REGELN]); gestoert = pg.evaluate(FINGER); pg.evaluate(STOER, [False, ''])
        self.stoer[variante] = vergleich(neutral, gestoert)
        if medium_zurueck: pg.emulate_media(media='null')

    def pruefen(self, browser):
        neu = {'browser': browser, 'varianten': self.varianten}
        name = os.path.basename(self.datei)
        fremd = {v: f for v, f in self.fremd.items() if f}
        self.check(f'Druck getrennt vom Bildschirm ({len(self.fremd)} Varianten): keine Regel aus app.css oder einem anderen Stylesheet trifft den Druck – '
                   'Druckregeln nur in angebot-druck.css', self.fremd and not fremd,
                   {v: f[:5] for v, f in fremd.items()} or 'keine Variante gemessen')
        stoer = {v: d for v, d in self.stoer.items() if d}
        self.check(f'Störversuch ({len(self.stoer)} Varianten): fremde Farben, Schrift, Größen und Abstände an :root/body ändern den Druck nicht',
                   self.stoer and not stoer, {v: d[:4] for v, d in stoer.items()} or 'keine Variante gemessen')
        if os.environ.get('WA_DRUCK_REFERENZ') == 'neu':
            if os.environ.get('CI'): self.check(f'Fingerabdruck {name}: in der CI wird keine Referenz geschrieben', False); return
            with open(self.datei, 'w', encoding='utf-8') as f: json.dump(neu, f, ensure_ascii=False, separators=(',', ':')); f.write('\n')
            self.check(f'Fingerabdruck {name}: Referenz neu geschrieben ({", ".join(self.varianten)}; {browser})', True); return
        try: alt = json.load(open(self.datei, encoding='utf-8'))
        except FileNotFoundError: self.check(f'Fingerabdruck: Referenz tests/fixtures/angebote/{name} vorhanden', False); return
        # Lage und Größe gelten für die Chromium-Fassung der Referenz (tests/requirements.txt, wie die CI): eine andere Fassung bricht
        # Zeilen teils anders um. Dann werden nur Kennzahlen und Stile verglichen, die Lage nur als Hinweis gemeldet.
        gleich = alt['browser'] == browser
        for v in alt['varianten']:
            if not self.varianten.get(v): self.check(f'Druck unverändert (Fingerabdruck „{v}“)', False, 'Variante nicht gesetzt'); continue
            d = vergleich(alt['varianten'][v], self.varianten[v], lage=gleich)
            self.check(f'Druck unverändert (Fingerabdruck „{v}“: {"Lage, Größe und " if gleich else ""}Stil jedes Bausteins wie in der Referenz)', not d,
                       f"{len(d)} Abweichungen, z. B.: " + ' | '.join(d[:12]))
            if not gleich:
                hin = vergleich(alt['varianten'][v], self.varianten[v])
                if hin: print(f"HINWEIS Fingerabdruck „{v}“: Referenz mit {alt['browser']}, Test mit {browser} – Lage nicht geprüft ({len(hin)} Abweichungen, z. B. {hin[0]}). "
                              'Für die volle Prüfung die Playwright-Fassung aus tests/requirements.txt nutzen (wie die CI).')
        neue = [v for v in self.varianten if v not in alt['varianten']]
        self.check(f'Fingerabdruck {name}: jede gemessene Variante hat eine Referenz', not neue, neue)
