/* STAFL-Plattform · Controlling – Grundgerüst der Seite: Anmeldung über den Status, Bereiche aus controlling_start
   (nur die, für die der Mitarbeiter ein Recht hat), Reiter über location.hash, Hell/Dunkel am Konto (theme.js).
   Jeder Bereich (Umsatzstatistik, später OP-Konten, Liquidität …) ist ein eigenes Skript, das sich mit
   window.STAFL_CONTROLLING.bereich(id, { anzeigen(container, rechte) }) anmeldet – neue Bereiche ändern dieses Skript nicht.
   Rechte prüft der Server bei jeder Aktion (GR-103); ausgeblendete Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const S = { csrf: '', bereiche: [], aktiv: null, geladen: new Set(), toast: 0 };
  const bereichsModule = {};

  /* Aufruf der API: wirft nie, liefert { status, data, json } */
  async function api(action, body, query = '') {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {}, json: false }; }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  function toast(text, fehlerhaft = false) {
    const t = $('#ctl-toast');
    t.textContent = text; t.className = 'ctl-toast zeigen' + (fehlerhaft ? ' fehler' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'ctl-toast'; }, fehlerhaft ? 4200 : 2400);
  }
  function fehler(text) { $('#ctl-login').hidden = true; $('#ctl-app').hidden = true; $('#ctl-err').hidden = false; $('#ctl-err').textContent = text; }
  function zeigeAnmeldung() { $('#ctl-login').hidden = false; $('#ctl-app').hidden = true; $('#ctl-user').hidden = true; }
  const initialen = (name) => { const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean); return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };

  /* Rückweg zum Dashboard auf der echten Adresse */
  if (/(^|\.)dashboard-stafl\.de$/.test(location.hostname)) $('#ctl-zurueck').href = 'https://dashboard-stafl.de/';

  /* ---------- Hell/Dunkel ---------- */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#ctl-theme');
    b.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-${d ? 'sun' : 'moon'}"/></svg>`;
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#ctl-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);

  /* ---------- Bereiche ---------- */
  /* Hash: „#umsatz“ oder „#umsatz/datenpflege“ (Bereich / Reiter im Bereich) */
  const hashTeile = () => location.hash.slice(1).split('/');
  async function zeigeBereich(id) {
    const b = S.bereiche.find((x) => x.id === id) || S.bereiche[0];
    if (!b) return;
    S.aktiv = b.id;
    $$('#ctl-bereiche [role="tab"]').forEach((x) => x.setAttribute('aria-selected', String(x.dataset.bereich === b.id)));
    $$('#ctl-inhalt > [data-bereich]').forEach((x) => { x.hidden = x.dataset.bereich !== b.id; });
    let box = $(`#ctl-inhalt > [data-bereich="${CSS.escape(b.id)}"]`);
    if (!box) {
      box = document.createElement('section');
      box.dataset.bereich = b.id; box.id = 'ctl-b-' + b.id; box.setAttribute('role', 'tabpanel');
      $('#ctl-inhalt').append(box);
    }
    if (hashTeile()[0] !== b.id) history.replaceState(null, '', '#' + b.id);
    if (!S.geladen.has(b.id)) {
      S.geladen.add(b.id);
      const m = bereichsModule[b.id];
      if (!m) { box.innerHTML = `<p class="ctl-leer-bereich ctl-glas">${esc(b.name)}: Dieser Bereich ist in dieser Version noch nicht verfügbar.</p>`; return; }
      await m.anzeigen(box, { bearbeiten: b.bearbeiten }, hashTeile()[1] || '');
    }
  }
  $('#ctl-bereiche').addEventListener('click', (ev) => { const b = ev.target.closest('[role="tab"]'); if (b) zeigeBereich(b.dataset.bereich); });

  /* ---------- Start ---------- */
  async function laden() {
    const st = await api('status');
    if (st.status === 401 && !st.json) { zeigeAnmeldung(); return; }   // zentrale Sitzung abgelaufen (Webserver)
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, S.csrf, API); themaKnopf(); }
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#ctl-user').hidden = false; $('#ctl-user-name').textContent = name; $('#ctl-initialen').textContent = initialen(name);
    const r = await api('controlling_start');
    if (r.status === 404) { fehler('Das Controlling ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Das Controlling wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return; }
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Das Controlling konnte nicht geladen werden')); return; }
    S.bereiche = r.data.bereiche || [];
    $('#ctl-bereiche').innerHTML = S.bereiche.map((b) => `<button type="button" role="tab" data-bereich="${esc(b.id)}" aria-selected="false">${esc(b.name)}</button>`).join('');
    $('#ctl-bereiche').hidden = S.bereiche.length === 0;
    $('#ctl-kein-bereich').hidden = S.bereiche.length > 0;
    $('#ctl-login').hidden = true; $('#ctl-app').hidden = false;
    await zeigeBereich(hashTeile()[0]);
  }

  /* Schnittstelle für die Bereichsskripte (umsatz.js usw.) */
  window.STAFL_CONTROLLING = {
    bereich(id, modul) { bereichsModule[id] = modul; },
    api, esc, toast, fehlerText, zeigeAnmeldung,
    hashSetzen(teil) { history.replaceState(null, '', '#' + S.aktiv + (teil ? '/' + teil : '')); },
  };
  themaKnopf();
  document.addEventListener('DOMContentLoaded', () => { laden().catch(() => fehler('Keine Verbindung zum Server.')); });
})();
