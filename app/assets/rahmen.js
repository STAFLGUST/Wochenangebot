/* STAFL-Plattform · Gemeinsamer Rahmen: Seitenleiste mit allen Anwendungen (Gestaltung „C2“, rahmen.css)
   Die Leiste entsteht aus der Modulliste der Aktion module_status (Modulregister) – keine fest programmierte Liste. Was ein
   Eintrag zeigt, ist nur Anzeige: Zugang und Rechte prüft der Server bei jeder Aktion (GR-102, GR-103); Module ohne
   Modulzugang der Rolle (kachel.recht === false) erscheinen nicht. Die Seite lädt status und module_status selbst und ruft
   STAFL_RAHMEN.zeichnen() – so fragt keine Seite die Liste doppelt ab.
   Aufbau der Seite: <div class="r-app"><nav class="r-leiste" id="r-leiste" aria-label="Hauptnavigation" hidden></nav>
   <div class="r-inhalt">…</div></div>. Unter 900 px setzt rahmen.js eine Kopfzeile mit Menüknopf davor; Escape, ein Klick
   daneben oder das Verlassen des Menüs mit der Tabulatortaste schließt es.
   Breite am Desktop (10.11.2026, auf jeder Seite gleich): schmal mit Symbolen; mit dem Mauszeiger (kurz verzögert) oder der
   Tastatur klappt die Leiste über dem Inhalt auf, Escape oder Verlassen klappt sie wieder ein. Der Pin oben stellt sie fest
   (immer breit). Die Wahl gilt am Konto auf jedem Host (Status user.leiste, gespeichert mit theme_save).
   Ziele der Einträge wie bisher die Kacheln: unter dashboard-stafl.de die Adressen der zentralen Anmeldung, in Test- und
   Entwicklungsumgebungen derselbe Pfad auf dem aktuellen Server (nie die Produktion).
   Modulseiten binden den Rahmen ohne eigenes Skript ein: <body data-rahmen="<modul-id>"> (siehe selbst() unten).
   Suche (Feld „Suchen“ oben in der Leiste, Strg K bzw. ⌘ K): springt zu einer Anwendung; Seiten können weitere Ziele
   ergänzen (STAFL_RAHMEN.suche, Dashboard: Schnellaktionen). Zahlen offener Punkte je Anwendung setzt nur das Dashboard
   (STAFL_RAHMEN.zahlen – Daten der Aktion start_heute, die es nur auf dem Dashboard-Host gibt, GR-109).
   Kein Inline-Skript (Content-Security-Policy); fremde Texte (Namen aus Register und Konto) nur maskiert. */
'use strict';
(() => {
  const QUELLE = document.currentScript ? document.currentScript.src : location.href;
  const LOGO = new URL('logo-standard-fleisch-kopf.png', QUELLE).href;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  /* Suche (siehe sucheOeffnen unten): Tastenkürzel je System, Ziele und Zustand des Dialogs */
  const API = new URL('../api/', QUELLE).pathname;   // Schnittstelle des eigenen Hosts (GR-109)
  const TASTE = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '') ? '⌘ K' : 'Strg K';
  const such = { module: [], extra: [], treffer: [], wahl: 0, dlg: null, zurueck: null };

  /* Symbole je Registersymbol (icon), gleiche Formen wie bisher auf dem Dashboard; unbekannt → Raster */
  const PFADE = {
    start: '<path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v11h13V9"/><path d="M10 20v-5.5h4V20"/>',
    tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.6" cy="7.6" r="1.7" fill="currentColor" stroke="none"/>',
    boxes: '<rect x="7.5" y="3" width="9" height="8" rx="1.6"/><rect x="2.5" y="13" width="9" height="8" rx="1.6"/><rect x="12.5" y="13" width="9" height="8" rx="1.6"/><path d="M10.5 6.5h3M5.5 16.5h3M15.5 16.5h3"/>',
    users: '<circle cx="9" cy="8" r="3.6"/><path d="M2.5 20.5a6.5 6.5 0 0 1 13 0M15.5 4.6a3.6 3.6 0 0 1 0 6.8M17.6 14.2a6.5 6.5 0 0 1 3.9 6.3"/>',
    store: '<path d="M4.4 4h15.2L21 9H3z"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M4.8 11.6V20h14.4v-8.4M10 20v-4.5h4V20"/>',
    'shield-check': '<path d="M12 3 4.5 6v6c0 4.4 3.2 8 7.5 9 4.3-1 7.5-4.6 7.5-9V6z"/><path d="m8.6 12 2.4 2.4 4.4-4.8"/>',
    'shield-lock': '<path d="M12 3 4.5 6v6c0 4.4 3.2 8 7.5 9 4.3-1 7.5-4.6 7.5-9V6z"/><rect x="9" y="11" width="6" height="5" rx="1"/><path d="M10.3 11V9.6a1.7 1.7 0 0 1 3.4 0V11"/>',
    truck: '<circle cx="9.5" cy="19.6" r="1.5" fill="currentColor" stroke="none"/><circle cx="17.5" cy="19.6" r="1.5" fill="currentColor" stroke="none"/><path d="M2.5 3.5h2.8l2.4 11.2a1.8 1.8 0 0 0 1.8 1.4h7.9a1.8 1.8 0 0 0 1.7-1.3L21 8H6.2"/>',
    upload: '<path d="M4 14.5v3.5a2.5 2.5 0 0 0 2.5 2.5h11A2.5 2.5 0 0 0 20 18v-3.5M12 15.5V4M7.5 8.5 12 4l4.5 4.5"/>',
    settings: '<path d="M3.5 20.5V9.5L12 3.5l8.5 6v11"/><circle cx="12" cy="14.5" r="2.4"/><path d="M12 10.3v1.4M12 17.3v1.4M7.8 14.5h1.4M14.8 14.5h1.4M9 11.5l1 1M14 16.5l1 1M9 17.5l1-1M14 12.5l1-1"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/><circle cx="8.5" cy="14" r="1.1" fill="currentColor" stroke="none"/><circle cx="12" cy="14" r="1.1" fill="currentColor" stroke="none"/><circle cx="15.5" cy="14" r="1.1" fill="currentColor" stroke="none"/><circle cx="8.5" cy="17.3" r="1.1" fill="currentColor" stroke="none"/><circle cx="12" cy="17.3" r="1.1" fill="currentColor" stroke="none"/>',
    megaphone: '<path d="M3.5 10v4h3.2l6.8 4.4V5.6L6.7 10z" fill="currentColor"/><path d="M6.7 14l1.2 5.5h2.4M16.6 9a4.4 4.4 0 0 1 0 6M19.4 6.4a8.2 8.2 0 0 1 0 11.2"/>',
    chart: '<path d="M5 20.5v-4M10 20.5v-7M15 20.5v-5M20 20.5V10M4 11.5 9.5 7l4 3L19.5 4M15.5 4h4v4"/>',
    crate: '<rect x="3" y="10" width="18" height="10.5" rx="2"/><path d="M3 15h18M9.5 12.5h5"/><path d="M7 7.2a5.5 5.5 0 0 1 9.6-2.4"/><path d="M17 2.2v3h-3"/>',
    container: '<rect x="2.5" y="6" width="19" height="12" rx="1.6"/><path d="M6.5 9v6M10 9v6M14 9v6M17.5 9v6"/><path d="M2.5 21h19"/>',
    raster: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    abmelden: '<path d="M14 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H14M10 12h10M16.5 8.5 20 12l-3.5 3.5"/>',
    menue: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    suche: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    pfeil: '<path d="m9 5.5 6.5 6.5L9 18.5"/>',
    schliessen: '<path d="M6 6l12 12M18 6 6 18"/>',
    pin: '<path d="M9 3.5h6l-.8 6 3.3 3v1.5h-11V12.5l3.3-3z"/><path d="M12 14v6.5"/>',
  };
  const symbol = (name, cls = 'r-i') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${PFADE[name] || PFADE.raster}</svg>`;

  /* Ziel eines Eintrags bzw. einer Kachel. Im Echtbetrieb (unter dashboard-stafl.de) die Adresse unter der zentralen
     Anmeldung: das beschlossene Ziel der Oberfläche (z. B. angebot.dashboard-stafl.de statt angebot-stafl.de/admin/), sonst
     ihre Adresse. In Test- und Entwicklungsumgebungen derselbe Pfad auf dem aktuellen Server (nie auf die Produktion). */
  function ziel(k, alle, host) {
    const [zm, zo] = String((k && k.ziel) || '').split('.');
    const ob = (((alle || {})[zm] || {}).oberflaechen || []).find((o) => o.id === zo) || {};
    try {
      return /(^|\.)dashboard-stafl\.de$/.test(host) ? new URL(ob.ziel || k.adresse).href : new URL(k.adresse).pathname;
    } catch { return '#'; }
  }

  /* frei = nutzbar (Verweis); aus = Wartung oder abgeschaltet ohne Zugang; bald = noch nicht freigegeben */
  function art(m) {
    const k = m.kachel || {};
    if (k.zugang) return 'frei';
    return ['wartung', 'deaktiviert'].includes(k.status) ? 'aus' : 'bald';
  }
  const STAND = { wartung: 'Wartung', deaktiviert: 'Aus', testbetrieb: 'Test', in_pruefung: 'Test' };

  /* Sichtbare Module in der Reihenfolge des Registers (wie die Kacheln des Dashboards) */
  function sichtbar(module) {
    return (module || []).filter((m) => m.dashboard && m.kachel && m.kachel.recht !== false)
      .sort((a, b) => (a.reihenfolge ?? 999) - (b.reihenfolge ?? 999));
  }

  /* Initialen: erste Buchstaben der ersten beiden Namensteile („Erika Editor“ → „EE“) */
  function initialen(name) {
    const teile = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean);
    const z = teile.length > 1 ? teile[0][0] + teile[1][0] : (teile[0] || '?').slice(0, 2);
    return z.toLocaleUpperCase('de-DE');
  }

  function eintrag(m, alle, host, aktiv) {
    const a = art(m), stand = a === 'bald' ? '' : (STAND[m.kachel.status] || '');
    const name = esc(m.name), label = esc(m.name + (a === 'bald' ? ' – bald verfügbar' : stand ? ` (${stand})` : ''));
    const innen = `${symbol(m.icon in PFADE ? m.icon : 'raster')}<span class="r-text">${name}</span>`
      + (stand ? `<span class="r-stand">${esc(stand)}</span>` : '') + (a === 'bald' ? '<span class="r-bald" aria-hidden="true">Bald</span>' : '');
    if (a !== 'frei') {
      return `<li><span class="r-eintrag r-aus" role="link" aria-disabled="true" data-modul="${esc(m.id)}" data-symbol="${esc(m.icon)}" title="${label}" aria-label="${label}">${innen}</span></li>`;
    }
    const cur = aktiv === m.id ? ' aria-current="page"' : '';
    return `<li><a class="r-eintrag" href="${esc(ziel(m.kachel, alle, host))}" data-modul="${esc(m.id)}" data-symbol="${esc(m.icon)}" title="${label}" aria-label="${label}"${cur}>${innen}</a></li>`;
  }

  function gruppe(titel, liste) {
    return liste ? `<div class="r-gruppe"><p class="r-gruppe-titel">${titel}</p><span class="r-trenner" aria-hidden="true"></span><ul class="r-liste">${liste}</ul></div>` : '';
  }

  let app = null, knopf = null;
  function menue(auf, fokus) {
    if (!app || !knopf) return;
    if (auf !== app.classList.contains('r-offen')) {   // nur ein echter Wechsel bewegt die Leiste
      app.classList.add('r-bewegung');
      clearTimeout(menue.zeit); menue.zeit = setTimeout(() => app.classList.remove('r-bewegung'), 260);
    }
    app.classList.toggle('r-offen', auf);
    knopf.setAttribute('aria-expanded', String(auf));
    knopf.setAttribute('aria-label', auf ? 'Menü schließen' : 'Menü öffnen');
    const nav = document.getElementById('r-leiste');
    if (auf && fokus) { const z = nav.querySelector('a, button'); if (z) z.focus(); }
    if (!auf && fokus) knopf.focus();
  }

  /* Breite am Desktop: r-fest (Pin, am Konto) = immer breit; sonst schmal und r-auf, solange Mauszeiger oder Tastatur auf der
     Leiste sind. Aufklappen kurz verzögert (kein Aufspringen beim Überfahren), Zuklappen etwas später (kein Flackern). */
  const DESKTOP = '(min-width: 901px)', AUF_MS = 150, ZU_MS = 300;
  const leiste = { fest: false, csrf: '', nutzer: null, uhr: 0 };
  function aufklappen(auf, sofort) {
    clearTimeout(leiste.uhr);
    if (!app) return;
    if (auf && (leiste.fest || !matchMedia(DESKTOP).matches)) return;
    const tun = () => app.classList.toggle('r-auf', auf);
    if (sofort) tun(); else leiste.uhr = setTimeout(tun, auf ? AUF_MS : ZU_MS);
  }
  function feststellen(fest, merken) {
    leiste.fest = !!fest;
    if (!app) return;
    app.classList.toggle('r-fest', leiste.fest);
    const p = document.getElementById('r-pin');
    if (p) {
      p.setAttribute('aria-pressed', String(leiste.fest));
      const text = leiste.fest ? 'Seitenleiste lösen (schmal, klappt bei Bedarf auf)' : 'Seitenleiste feststellen (immer breit)';
      p.setAttribute('aria-label', text); p.title = text;
    }
    if (!merken) return;
    if (leiste.nutzer) leiste.nutzer.leiste = leiste.fest ? 'fest' : '';
    if (!leiste.csrf) return;   // ohne Anmeldung nur auf dieser Seite
    fetch(API + '?action=theme_save', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': leiste.csrf }, body: JSON.stringify({ leiste: leiste.fest ? 'fest' : '' }) })
      .catch(() => { /* gilt auf dieser Seite; gespeichert beim nächsten Wechsel */ });
  }
  /* Ereignisse einmal je Leiste (zeichnen() kann mehrfach laufen) */
  function leisteBinden(nav) {
    if (nav.dataset.gebunden) return;
    nav.dataset.gebunden = '1';
    nav.addEventListener('mouseenter', () => aufklappen(true));
    nav.addEventListener('mouseleave', () => { if (!nav.contains(document.activeElement) || !document.activeElement.matches(':focus-visible')) aufklappen(false); });
    nav.addEventListener('focusin', (e) => { if (e.target.matches(':focus-visible')) aufklappen(true, true); });
    nav.addEventListener('focusout', (e) => { if (!e.relatedTarget || !nav.contains(e.relatedTarget)) aufklappen(false, true); });
    nav.addEventListener('keydown', (e) => { if (e.key === 'Escape' && app && app.classList.contains('r-auf')) { e.preventDefault(); aufklappen(false, true); } });
    nav.addEventListener('click', (e) => {
      if (!e.target.closest('#r-pin')) return;
      feststellen(!leiste.fest, true);
      aufklappen(!leiste.fest && nav.matches(':hover'), true);   // gelöst und Zeiger noch darauf: bleibt aufgeklappt bis zum Verlassen
    });
  }

  /* Kopfzeile am Handy (nur unter 900 px sichtbar): Menüknopf und Logo; einmal je Seite */
  function mobilkopf(start) {
    const inhalt = app.querySelector('.r-inhalt');
    let kopf = app.querySelector('.r-mobilkopf');
    if (!kopf && inhalt) {
      kopf = document.createElement('header');
      kopf.className = 'r-mobilkopf';
      kopf.innerHTML = `<button class="r-menue" id="r-menue" type="button" aria-controls="r-leiste" aria-expanded="false" aria-label="Menü öffnen">${symbol('menue')}</button>`
        + `<a class="r-marke" href="#"><img class="r-logo" src="${esc(LOGO)}" width="428" height="96" alt="Standard-Fleisch – Start"></a>`;
      inhalt.prepend(kopf);
      knopf = kopf.querySelector('#r-menue');
      knopf.addEventListener('click', () => menue(!app.classList.contains('r-offen'), true));
      const schleier = document.createElement('div');
      schleier.className = 'r-schleier';
      schleier.setAttribute('aria-hidden', 'true');
      schleier.addEventListener('click', () => menue(false, true));
      app.append(schleier);
      document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && app.classList.contains('r-offen')) { e.preventDefault(); menue(false, true); } });
      document.getElementById('r-leiste').addEventListener('focusout', (e) => {
        if (app.classList.contains('r-offen') && e.relatedTarget && !e.relatedTarget.closest('#r-leiste, #r-menue')) menue(false, false);
      });
    }
    if (kopf) { kopf.hidden = false; kopf.querySelector('.r-marke').setAttribute('href', start); }
  }

  /* Leiste zeichnen.
     o.module   Liste aus module_status (data.module)
     o.aktiv    'start' oder die Modul-ID der Seite
     o.nutzer   Konto aus status (name, rollenName)
     o.start    Adresse der Startseite (Dashboard)
     o.csrf     CSRF-Token der Sitzung (zum Speichern des Pins am Konto; ohne: Pin gilt nur auf dieser Seite)
     o.abmelden Funktion für den Knopf „Abmelden“ (ohne: Knopf entfällt)
     Feststellen: o.nutzer.leiste === 'fest' (Status). o.schmal gibt es nicht mehr (seit 10.11.2026 auf jeder Seite gleich),
     wird aber weiter angenommen und übergangen. */
  function zeichnen(o) {
    const nav = document.getElementById('r-leiste');
    if (!nav) return;
    app = nav.closest('.r-app') || document.body;
    const host = o.host || location.hostname, alle = Object.fromEntries((o.module || []).map((m) => [m.id, m]));
    const liste = sichtbar(o.module), aktiv = o.aktiv || 'start', start = o.start || './';
    const apps = liste.filter((m) => m.gruppe !== 'verwaltung' && art(m) !== 'bald');
    const bald = liste.filter((m) => art(m) === 'bald');
    const verw = liste.filter((m) => m.gruppe === 'verwaltung' && art(m) !== 'bald');
    const zeile = (m) => eintrag(m, alle, host, aktiv);
    const n = o.nutzer || {}, name = n.name || n.username || '';
    nav.innerHTML = `<div class="r-kopf"><a class="r-marke" href="${esc(start)}"><img class="r-logo" src="${esc(LOGO)}" width="428" height="96" alt="Standard-Fleisch – Start"></a>`
      + `<button class="r-pin" id="r-pin" type="button" aria-pressed="false">${symbol('pin')}</button></div>`
      + `<button class="r-suche" id="r-suche" type="button" aria-haspopup="dialog" aria-label="Suchen (${esc(TASTE)})" title="Suchen · ${esc(TASTE)}">${symbol('suche')}`
      + `<span class="r-text">Suchen</span><kbd class="r-taste" aria-hidden="true">${esc(TASTE)}</kbd></button>`
      + `<ul class="r-liste"><li><a class="r-eintrag" href="${esc(start)}" data-modul="start" data-symbol="start" title="Start" aria-label="Start"${aktiv === 'start' ? ' aria-current="page"' : ''}>${symbol('start')}<span class="r-text">Start</span></a></li></ul>`
      + gruppe('Anwendungen', apps.map(zeile).join(''))
      + gruppe('In Entwicklung', bald.map(zeile).join(''))
      + '<div class="r-luecke"></div>'
      + gruppe('Verwaltung &amp; Daten', verw.map(zeile).join(''))
      + `<div class="r-fuss"><span class="r-initialen" id="r-initialen" title="${esc(name)}" aria-hidden="true">${esc(initialen(name))}</span>`
      + `<span class="r-person"><span class="sr-only">Angemeldet als </span><span class="r-name" id="r-nutzer-name">${esc(name)}</span>`
      + (n.rollenName ? `<span class="r-rolle" id="r-rolle">${esc(n.rollenName)}</span>` : '') + '</span>'
      + (o.abmelden ? `<button class="r-abmelden" id="r-abmelden" type="button" aria-label="Abmelden" title="Abmelden">${symbol('abmelden')}</button>` : '') + '</div>';
    if (o.abmelden) nav.querySelector('#r-abmelden').addEventListener('click', o.abmelden);
    nav.querySelector('#r-suche').addEventListener('click', () => sucheOeffnen());
    such.module = [...apps, ...verw].map((m) => ({ titel: m.name, href: ziel(m.kachel, alle, host), symbol: m.icon, gruppe: 'Anwendungen' }));
    nav.hidden = false;
    app.classList.add('r-bereit');
    leiste.nutzer = o.nutzer || null; leiste.csrf = o.csrf || '';
    feststellen(n.leiste === 'fest', false);
    aufklappen(false, true);
    leisteBinden(nav);
    mobilkopf(start);
  }

  /* Leiste entfernen (z. B. nach dem Abmelden): Seite wieder ohne Rahmen */
  function entfernen() {
    const nav = document.getElementById('r-leiste');
    if (!nav) return;
    menue(false, false);
    if (such.dlg && such.dlg.open) such.dlg.close();
    nav.hidden = true; nav.innerHTML = '';
    const a = nav.closest('.r-app');
    clearTimeout(leiste.uhr);
    if (a) { a.classList.remove('r-bereit', 'r-fest', 'r-auf'); const k = a.querySelector('.r-mobilkopf'); if (k) k.hidden = true; }
  }

  /* Modulseiten: <body … data-rahmen="<modul-id>"> (Eingabebereich: data-rahmen="auto" = Modul des Hosts) – der Rahmen
     holt status und module_status selbst, damit das Skript des
     Moduls unverändert bleibt. Ohne Anmeldung oder bei einem Fehler bleibt die Seite ohne Leiste (das Modul zeigt seinen
     Hinweis wie bisher). Abmelden: wie auf dem Dashboard, danach lädt die Seite neu (zeigt den Anmeldehinweis). */
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  async function holen(action, body, csrf) {
    const r = await fetch(API + '?action=' + action, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf || '' } : {}, body: body ? JSON.stringify(body) : undefined });
    let d = null;
    try { d = await r.json(); } catch { /* keine JSON-Antwort */ }
    return { status: r.status, data: d || {} };
  }
  async function selbst(wunsch) {
    const st = await holen('status');
    if (st.status !== 200 || !st.data.loggedIn) return false;
    const nutzer = st.data.user || {}, csrf = st.data.csrf || '';
    const ms = await holen('module_status');
    if (ms.status !== 200 || !ms.data.ok) return false;
    const module = ms.data.module || [];
    let aktiv = wunsch;
    if (wunsch === 'auto') {   // Eingabebereich: Oberfläche dieses Hosts (z. B. bestand.intern) → Modul, dessen Kachel dorthin führt
      const bereich = nutzer.bereich || 'angebot.eingabe';
      const treffer = module.find((m) => m.kachel && m.kachel.ziel === bereich);
      aktiv = treffer ? treffer.id : bereich.split('.')[0];
    }
    const start = ECHT ? (nutzer.dashboard && /^https:/.test(nutzer.dashboard) ? nutzer.dashboard : 'https://dashboard-stafl.de/') : new URL('../dashboard/', QUELLE).pathname;
    zeichnen({ module, aktiv, nutzer, start, csrf, abmelden: async () => {
      const r = await holen('logout', {}, csrf);
      if (typeof r.data.abmelden === 'string' && r.data.abmelden.startsWith('/oidc/')) { location.replace(r.data.abmelden); return; }
      location.reload();
    } });
    return true;
  }
  /* data-rahmen-nach="<Selektor>": erst zeichnen, wenn dieser Bereich sichtbar ist (Eingabebereich: nach der Anmeldung im
     selben Fenster, ohne Neuladen), und wieder entfernen, wenn er verschwindet */
  const wunsch = document.body && document.body.dataset.rahmen;
  const nach = wunsch && document.body.dataset.rahmenNach ? document.querySelector(document.body.dataset.rahmenNach) : null;
  if (wunsch && nach) {
    let gezeichnet = false, laeuft = false;
    const pruefen = () => {
      if (!nach.hidden && !gezeichnet && !laeuft) {
        laeuft = true;
        selbst(wunsch).then((ok) => { gezeichnet = ok; }, () => { /* ohne Leiste weiter */ }).finally(() => { laeuft = false; });
      } else if (nach.hidden && gezeichnet) { entfernen(); gezeichnet = false; }
    };
    new MutationObserver(pruefen).observe(nach, { attributes: true, attributeFilter: ['hidden'] });
    pruefen();
  } else if (wunsch) selbst(wunsch).catch(() => { /* ohne Leiste weiter */ });

  /* Zahlen offener Punkte je Anwendung an den Einträgen der Leiste (nur Dashboard): {crm: {offen: 3, ueberfaellig: 1}, …}.
     Rot, wenn etwas überfällig ist; in der schmalen Leiste als Punkt am Symbol. Die Zahl steht auch in der Beschriftung. */
  function zahlen(z) {
    for (const e of document.querySelectorAll('#r-leiste .r-eintrag[data-modul]')) {
      const alt = e.querySelector('.r-zahl');
      if (alt) alt.remove();
      if (!e.dataset.label) e.dataset.label = e.getAttribute('aria-label') || '';
      const n = z && z[e.dataset.modul];
      e.setAttribute('aria-label', e.dataset.label + (n && n.offen ? `, ${n.offen} offen${n.ueberfaellig ? `, davon ${n.ueberfaellig} überfällig` : ''}` : ''));
      if (!n || !n.offen) continue;
      const s = document.createElement('span');
      s.className = 'r-zahl' + (n.ueberfaellig ? ' r-zahl-rot' : '');
      s.setAttribute('aria-hidden', 'true');
      s.textContent = n.offen > 99 ? '99+' : String(n.offen);
      e.append(s);
    }
  }

  /* Suche: Dialog mit Eingabefeld und Trefferliste (Tastatur: ↑ ↓ Enter; Escape oder Kreuz schließt, ein Klick daneben nicht).
     Ziele: freie Anwendungen der Leiste
     und was die Seite ergänzt (suche([{titel, href, symbol, gruppe}])). Nur Sprünge – Rechte prüft das Ziel selbst. */
  function suche(liste) { such.extra = Array.isArray(liste) ? liste : []; }
  function sucheDialog() {
    if (such.dlg) return such.dlg;
    const d = document.createElement('dialog');
    d.className = 'r-palette'; d.id = 'r-palette'; d.setAttribute('aria-label', 'Suchen');
    d.innerHTML = `<div class="r-palette-feld">${symbol('suche')}<input id="r-palette-eingabe" type="text" role="combobox" aria-expanded="true" aria-controls="r-palette-liste"`
      + ` aria-autocomplete="list" autocomplete="off" spellcheck="false" placeholder="Anwendung oder Aktion suchen …" aria-label="Suchbegriff">`
      + `<button class="r-palette-zu" type="button" aria-label="Suche schließen">${symbol('schliessen')}</button></div>`
      + '<div class="r-palette-liste" id="r-palette-liste" role="listbox" aria-label="Treffer"></div>'
      + '<p class="r-palette-fuss" aria-hidden="true"><kbd>↑</kbd><kbd>↓</kbd> auswählen · <kbd>Enter</kbd> öffnen · <kbd>Esc</kbd> schließen</p>';
    document.body.append(d);
    const ein = d.querySelector('input');
    ein.addEventListener('input', () => { such.wahl = 0; sucheZeigen(); });
    ein.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (such.treffer.length) { such.wahl = (such.wahl + (e.key === 'ArrowDown' ? 1 : -1) + such.treffer.length) % such.treffer.length; sucheZeigen(); }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const z = such.treffer[such.wahl];
        if (z) location.assign(z.href);
      }
    });
    d.querySelector('.r-palette-zu').addEventListener('click', () => d.close());
    // Kein Schließen per Klick daneben (Vorgabe 02.11.2026: Fenster nur mit Escape oder Kreuz schließen)
    d.addEventListener('close', () => {   // Fokus zurück; lag er im inzwischen geschlossenen Menü (Handy), auf den Menüknopf
      const z = such.zurueck;
      if (z && z.isConnected && z.getClientRects().length && getComputedStyle(z).visibility !== 'hidden' && !(z.closest('#r-leiste') && knopf && knopf.offsetParent)) z.focus();
      else if (knopf && knopf.offsetParent) knopf.focus();
    });
    such.dlg = d;
    return d;
  }
  function sucheZeigen() {
    const d = sucheDialog(), q = d.querySelector('input').value.trim(), SU = window.STAFL_SUCHE;   // Suchregel aller Seiten (assets/suche.js)
    const alle = [...such.module, ...such.extra];
    such.treffer = q ? alle.filter((z) => SU.findet(q, z.titel, z.stichworte)) : alle;
    if (such.wahl >= such.treffer.length) such.wahl = 0;
    let gruppe = '';
    const zeilen = such.treffer.map((z, i) => {
      const kopf = z.gruppe !== gruppe ? `<p class="r-palette-gruppe" role="presentation">${esc(gruppe = z.gruppe)}</p>` : '';
      return kopf + `<a class="r-palette-treffer" id="r-palette-${i}" role="option" aria-selected="${i === such.wahl}" href="${esc(z.href)}" data-symbol="${esc(z.symbol || '')}">`
        + `${symbol(z.symbol in PFADE ? z.symbol : 'raster')}<span>${esc(z.titel)}</span>${symbol('pfeil', 'r-i r-palette-pfeil')}</a>`;
    });
    const liste = d.querySelector('.r-palette-liste');
    liste.innerHTML = zeilen.join('') || '<p class="r-palette-leer">Nichts gefunden.</p>';
    const ein = d.querySelector('input');
    if (such.treffer.length) ein.setAttribute('aria-activedescendant', 'r-palette-' + such.wahl); else ein.removeAttribute('aria-activedescendant');
    const aktiv = liste.querySelector('[aria-selected="true"]');
    if (aktiv) aktiv.scrollIntoView({ block: 'nearest' });
  }
  function sucheOeffnen() {
    if (!document.getElementById('r-suche')) return;   // ohne Leiste (nicht angemeldet) keine Suche
    menue(false, false);
    const d = sucheDialog();
    if (d.open) return;
    such.zurueck = document.activeElement;
    d.querySelector('input').value = ''; such.wahl = 0;
    sucheZeigen();
    d.showModal();
    d.querySelector('input').focus();
  }
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k' && document.getElementById('r-suche')) { e.preventDefault(); sucheOeffnen(); }
  });

  window.STAFL_RAHMEN = { zeichnen, entfernen, ziel, initialen, sichtbar, art, symbol, zahlen, suche, sucheOeffnen };
})();
