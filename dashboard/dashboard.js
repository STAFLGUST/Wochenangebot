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
  /* Symbolnamen des Registers → Symbole dieser Seite (unbekannt → Raster) */
  const ICON = { tag: 'tag', boxes: 'box', users: 'users', store: 'store', 'shield-check': 'shield', truck: 'cart', upload: 'upload', settings: 'sliders' };
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

  /* Ziel einer Kachel: im Echtbetrieb die eingetragene Adresse, in Test- und Entwicklungsumgebungen derselbe Pfad auf
     dem aktuellen Server (sonst würde ein Test auf die Produktion verlinken). */
  function ziel(adresse) {
    try {
      const u = new URL(adresse);
      return /(^|\.)stafl\.de$/.test(location.hostname) ? u.href : u.pathname;
    } catch { return '#'; }
  }

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
    const kacheln = module.filter((m) => m.dashboard && m.kachel).sort((a, b) => (a.reihenfolge ?? 999) - (b.reihenfolge ?? 999));
    $('#db-grid').innerHTML = kacheln.map((m) => {
      const s = status(m, alle);
      const inhalt = `<span class="db-ico">${icon(ICON[m.icon] || 'grid')}</span>
        <h3 class="db-name">${esc(m.name)}</h3>
        <p class="db-desc">${esc(m.beschreibung)}</p>
        ${s.hinweis ? `<p class="db-hint">${esc(s.hinweis)}</p>` : ''}
        <div class="db-foot"><span class="db-badge ${s.cls}">${esc(s.text)}</span></div>`;
      return m.kachel.zugang
        ? `<a class="db-tile" role="listitem" data-modul="${esc(m.id)}" href="${esc(ziel(m.kachel.adresse))}">${inhalt}</a>`
        : `<div class="db-tile off" role="listitem" data-modul="${esc(m.id)}" aria-disabled="true">${inhalt}</div>`;
    }).join('');
    const frei = kacheln.filter((m) => m.kachel.zugang).length;
    $('#db-sub').textContent = `${frei} von ${kacheln.length} Anwendungen für Sie verfügbar`;
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
    // Angemeldet bei Keycloak, aber hier kein (aktives) Mitarbeiterkonto: Hinweis statt Anmeldemaske
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    csrf = st.data.csrf || '';
    $('#db-user').hidden = false; $('#db-user').textContent = `Angemeldet als ${st.data.user ? st.data.user.name : ''}`;
    $('#db-logout').hidden = false;
    const r = await api('module_status');
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(r.data.error || `Die Anwendungen konnten nicht geladen werden (${r.status}).`); return; }
    $('#db-login').hidden = true; $('#db-bereich').hidden = false;
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
