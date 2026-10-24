/* STAFL-Plattform · Dashboard
   Kacheln kommen ausschließlich aus dem Modulregister (Aktion module_status, regeln/module.toml) – keine fest
   programmierte Liste. Der Status je Kachel ist nur Anzeige; ob eine Anwendung nutzbar ist und welche Rechte gelten,
   entscheidet der Server bei jeder Aktion (GR-102, GR-103). Kein Inline-Skript (Content-Security-Policy). */
'use strict';
(() => {
  const API = '../api/';
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  /* Symbolnamen des Registers → Symbole dieser Seite (unbekannt → Raster). Die Farbe des Symbol-Quadrats hängt im
     Stylesheet ebenfalls am Symbolnamen (data-symbol), nicht am Modul. */
  const ICON = { tag: 'tag', boxes: 'box', users: 'users', store: 'store', 'shield-check': 'shield', truck: 'cart', upload: 'upload', settings: 'haus',
    calendar: 'calendar', megaphone: 'megaphone', chart: 'chart' };
  const BAND = 'Im Bau · Bald verfügbar · Im Bau · Bald verfügbar';
  const ENTWICKLUNG = { geplant: 'Geplant', in_entwicklung: 'In Entwicklung', in_pruefung: 'In Prüfung', fertig: 'Nicht freigegeben' };
  let csrf = '';

  async function api(action, body) {
    const res = await fetch(API + '?action=' + action, {
      method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {}, body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }

  /* Ziel einer Kachel. Im Echtbetrieb (Dashboard unter dashboard-stafl.de) die Adresse unter der zentralen Anmeldung:
     das beschlossene Ziel der Oberfläche (z. B. angebot.dashboard-stafl.de statt angebot-stafl.de/admin/), sonst ihre
     Adresse. In Test- und Entwicklungsumgebungen derselbe Pfad auf dem aktuellen Server (nie auf die Produktion). */
  function kachelZiel(k, alle, host) {
    const [zm, zo] = String((k && k.ziel) || '').split('.');
    const ob = ((alle[zm] || {}).oberflaechen || []).find((o) => o.id === zo) || {};
    try {
      return /(^|\.)dashboard-stafl\.de$/.test(host) ? new URL(ob.ziel || k.adresse).href : new URL(k.adresse).pathname;
    } catch { return '#'; }
  }
  window.STAFL_KACHEL_ZIEL = kachelZiel;   // für die Tests (reine Funktion, keine Daten)

  function status(m, alle) {
    const k = m.kachel || {};
    const [zm, zo] = String(k.ziel || '').split('.');
    const ob = ((alle[zm] || {}).oberflaechen || []).find((o) => o.id === zo) || {};
    switch (k.status) {
      case 'verfuegbar': return { text: 'Verfügbar', cls: 'ok' };
      case 'wartung': return { text: k.zugang ? 'Wartung – Zugang für Administratoren' : 'Wartung', cls: 'warn', hinweis: ob.wartung && ob.wartung.message };
      case 'testbetrieb': return { text: 'Testbetrieb', cls: 'warn' };
      case 'in_pruefung': return { text: 'Nur für Tester', cls: '' };
      case 'deaktiviert': return { text: 'Deaktiviert', cls: '' };
      case 'entwicklungsstand': return { text: ENTWICKLUNG[ob.entwicklung] || 'In Vorbereitung', cls: '' };
      default: return { text: 'Nicht verfügbar', cls: '' };
    }
  }

  function render(module) {
    const alle = Object.fromEntries(module.map((m) => [m.id, m]));
    // Kacheln ohne Modulzugang der Rolle erscheinen nicht (recht: false) – die Sperre selbst setzt der Server durch
    const kacheln = module.filter((m) => m.dashboard && m.kachel && m.kachel.recht !== false).sort((a, b) => (a.reihenfolge ?? 999) - (b.reihenfolge ?? 999));
    $('#db-grid').innerHTML = kacheln.map((m) => {
      const s = status(m, alle);
      // Absperrband nur für Anwendungen, die (noch) nicht nutzbar sind – nicht für Wartung (eigener Zustand mit Hinweis)
      // und nicht für abgeschaltete Module; der Text der Pille nennt weiter den genauen Stand.
      const band = !m.kachel.zugang && !['wartung', 'deaktiviert'].includes(m.kachel.status);
      const inhalt = `<span class="db-ico" data-symbol="${esc(m.icon)}">${icon(ICON[m.icon] || 'grid')}</span>
        <div class="db-text"><h2 class="db-name">${esc(m.name)}</h2><p class="db-desc">${esc(m.beschreibung)}</p></div>
        ${s.hinweis ? `<p class="db-hint">${esc(s.hinweis)}</p>` : ''}
        <span class="db-foot"><span class="db-badge ${s.cls}">${esc(s.text)}</span></span>
        ${band ? `<span class="db-band" aria-hidden="true"><span>${BAND}</span></span>` : ''}`;
      return m.kachel.zugang
        ? `<a class="db-tile db-glas" role="listitem" data-modul="${esc(m.id)}" href="${esc(kachelZiel(m.kachel, alle, location.hostname))}">${inhalt}</a>`
        : `<div class="db-tile db-glas off${band ? ' gesperrt' : ''}" role="listitem" data-modul="${esc(m.id)}" aria-disabled="true">${inhalt}</div>`;
    }).join('');
    if (!kacheln.length) $('#db-grid').innerHTML = '<p class="db-leer" role="listitem">Für Ihre Rolle ist noch keine Anwendung freigegeben. Bitte an einen Administrator wenden.</p>';
    const frei = kacheln.filter((m) => m.kachel.zugang).length;
    $('#db-sub').textContent = `${frei} von ${kacheln.length} Anwendungen für Sie verfügbar`;
    einpassen();
  }

  /* Lange Kachelnamen (Registernamen wie „Qualitätssicherung“) nicht mitten im Wort trennen: Schrift in halben Pixeln
     verkleinern, bis das längste Wort in die Kachel passt – höchstens auf drei Viertel der Grundgröße. Reicht das
     nicht, darf das Wort als Notlösung umbrechen (Klasse db-name-umbruch), statt über die Kachel hinauszuragen. */
  function namenEinpassen() {
    for (const el of document.querySelectorAll('#db-grid .db-name')) {
      el.style.fontSize = ''; el.classList.remove('db-name-umbruch');
      const basis = parseFloat(getComputedStyle(el).fontSize), min = Math.max(12, basis * .75);
      let g = basis;
      while (el.scrollWidth > el.clientWidth + 1 && g > min) { g = Math.max(min, g - .5); el.style.fontSize = g + 'px'; }
      if (el.scrollWidth > el.clientWidth + 1) el.classList.add('db-name-umbruch');
    }
  }

  /* Absperrband je gesperrter Kachel so legen, dass es weder den Namen (oben links) noch die Status-Pille (unten links)
     schneidet: das Band ist gedreht (rechts höher), also zählt beim Namen sein rechtes Ende, bei der Pille ihr linker
     Rand. Mittellinie in die Mitte des freien Bereichs. Reicht der Platz nicht (breite, flache Kachel, sehr langer
     Name), wird die Kachel so viel höher, dass das Band passt – die Pille rutscht nach unten, die Reihe bleibt gleich hoch.
     Am Handy ist die Pille nur für Screenreader da und das Band unten verankert (Stylesheet): dort wird die Kachel nur
     höher, falls ein langer Name sonst ans Band reicht. */
  const RAND = 4;
  function bandLage(t) {
    const band = t.querySelector('.db-band'), pille = t.querySelector('.db-badge'), name = t.querySelector('.db-name');
    if (!band || !pille || !name) return null;
    const k = t.getBoundingClientRect(), p = pille.getBoundingClientRect();
    const m = new DOMMatrix(getComputedStyle(band).transform), w = Math.atan2(m.b, m.a);
    const steig = Math.abs(Math.tan(w)), halb = band.offsetHeight / 2 / Math.cos(w), mitte = k.left + k.width / 2;
    const r = document.createRange(); r.selectNodeContents(name);
    const z = [...r.getClientRects()];
    if (!z.length) return null;
    const unten = Math.max(...z.map((q) => q.bottom)) - k.top, rechts = Math.max(...z.map((q) => q.right));
    const ab = unten + halb + steig * (rechts - mitte) + RAND;              // tiefste Lage, die den Namen frei lässt
    if (pille.parentElement.getBoundingClientRect().width < 2) {            // Handy: Pille nur für Screenreader
      return { hoehe: k.height, ab, bis: band.offsetTop + band.offsetHeight / 2, fest: true };
    }
    return { hoehe: k.height, ab, bis: p.top - k.top - halb + steig * (p.left - mitte) - RAND };   // bis: höchste Lage vor der Pille
  }
  function baenderLegen() {
    const gesperrt = [...document.querySelectorAll('#db-grid .gesperrt')];
    for (const t of gesperrt) { t.style.removeProperty('--db-band-y'); t.style.minHeight = ''; }
    for (const t of gesperrt) {
      const l = bandLage(t);
      if (l && l.ab > l.bis) t.style.minHeight = Math.ceil(l.hoehe + l.ab - l.bis) + 'px';
    }
    for (const t of gesperrt) {
      const l = bandLage(t);
      if (l && !l.fest) t.style.setProperty('--db-band-y', Math.round((l.ab + l.bis) / 2) + 'px');
    }
  }

  let breite = 0;
  function einpassen() { breite = $('#db-grid').clientWidth; namenEinpassen(); baenderLegen(); }
  // Neu einpassen, wenn sich die Breite ändert (Fenster, Drehen) und sobald die Schrift geladen ist
  new ResizeObserver(() => { if ($('#db-grid').clientWidth !== breite && $('#db-grid .db-tile')) einpassen(); }).observe($('#db-grid'));
  if (document.fonts) document.fonts.ready.then(() => { if ($('#db-grid .db-tile')) einpassen(); });

  /* Begrüßung nach Tageszeit (Uhr des Geräts) und Datum, z. B. „Donnerstag, 22. Oktober“ */
  function gruss(stunde) {
    if (stunde >= 5 && stunde < 11) return 'Guten Morgen';
    if (stunde >= 11 && stunde < 18) return 'Guten Tag';
    return 'Guten Abend';
  }
  window.STAFL_GRUSS = gruss;   // für die Tests (reine Funktion)
  function begruessung() {
    const jetzt = new Date();
    $('#db-datum').textContent = jetzt.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    $('#db-titel').textContent = gruss(jetzt.getHours());
  }

  /* Initialen für den Nutzer-Chip: erste Buchstaben der ersten beiden Namensteile („Erika Editor“ → „EE“) */
  function initialen(name) {
    const teile = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean);
    const z = teile.length > 1 ? teile[0][0] + teile[1][0] : (teile[0] || '?').slice(0, 2);
    return z.toLocaleUpperCase('de-DE');
  }

  function fehler(text) {
    $('#db-login').hidden = true; $('#db-bereich').hidden = true;
    $('#db-err').hidden = false; $('#db-err').textContent = text;
  }

  function zeigeAnmeldung(ziel) {
    if (ziel) $('#db-login a').setAttribute('href', ziel);
    $('#db-login').hidden = false; $('#db-bereich').hidden = true; $('#db-logout').hidden = true; $('#db-user').hidden = true;
  }

  async function laden() {
    const st = await api('status');
    // Keycloak-Host: zentrale Sitzung abgelaufen (401 vom Webserver, kein JSON) → Anmelden = Seite neu laden
    if (st.status === 401 && !st.json) { zeigeAnmeldung('./'); return; }
    // Zweiter Faktor für dieses Konto vorgeschrieben: zweite Stufe bei Keycloak, danach zurück auf diese Seite
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    // Angemeldet bei Keycloak, aber hier kein (aktives) Mitarbeiterkonto: Hinweis statt Anmeldemaske
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, csrf, API); themaKnopf(); }   // Hell/Dunkel am Konto (theme.js)
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#db-user').hidden = false; $('#db-user-name').textContent = name; $('#db-initialen').textContent = initialen(name);
    $('#db-user').title = `Angemeldet als ${name}`;
    $('#db-logout').hidden = false;
    const r = await api('module_status');
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(r.data.error || `Die Anwendungen konnten nicht geladen werden (${r.status}).`); return; }
    $('#db-login').hidden = true; $('#db-bereich').hidden = false;
    begruessung();
    render(r.data.module || []);
  }

  /* Hell/Dunkel wie auf der Angebotsseite (gleicher Speicherschlüssel, theme.js setzt es vor dem ersten Zeichnen) */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const b = $('#db-theme'), d = dunkel();
    b.innerHTML = icon(d ? 'sun' : 'moon');
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#db-theme').addEventListener('click', () => {
    const neu = dunkel() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });
  $('#db-logout').addEventListener('click', async () => {
    const r = await api('logout', {});
    // Zentrale Anmeldung (Keycloak-Host): auch bei Keycloak abmelden – beendet die Anmeldung für alle Anwendungen
    if (typeof r.data.abmelden === 'string' && r.data.abmelden.startsWith('/oidc/')) { location.replace(r.data.abmelden); return; }
    zeigeAnmeldung();
  });

  themaKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
