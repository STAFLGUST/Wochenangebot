/* STAFL-Plattform · Dashboard (Startseite, Gestaltung „C2“)
   Kacheln und Seitenleiste kommen ausschließlich aus dem Modulregister (Aktion module_status, regeln/module.toml) – keine fest
   programmierte Liste. Die Seitenleiste zeichnet der gemeinsame Rahmen (../assets/rahmen.js) mit denselben Daten. Der Stand je
   Kachel ist nur Anzeige; ob eine Anwendung nutzbar ist und welche Rechte gelten, entscheidet der Server bei jeder Aktion
   (GR-102, GR-103). Kein Inline-Skript (Content-Security-Policy).
   Knopf „Einfache Darstellung“ (Blitz, neben Hell/Dunkel): für Remote-Desktop ohne Effekte und Bewegung – Wahl am Konto, sonst
   automatisch erkannt (theme.js). */
'use strict';
(() => {
  const API = '../api/';
  const R = window.STAFL_RAHMEN;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="r-i" aria-hidden="true"><use href="#i-${n}"/></svg>`;   // Symbole dieser Seite (Hell/Dunkel)
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

  window.STAFL_KACHEL_ZIEL = R.ziel;   // für die Tests (reine Funktion, keine Daten; liegt im gemeinsamen Rahmen)

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

  /* Eine kompakte Kachel: Symbol und Name, keine Unterzeile. Eine zweite Zeile nur bei besonderem Stand (Wartung mit
     Hinweis, Testbetrieb …); „Verfügbar“ bleibt für Screenreader im Text. Noch nicht freigegebene Anwendungen sind
     zurückgenommen und tragen das Klebeband „Bald“ wie in der Seitenleiste – der genaue Stand steht darunter. */
  function kachel(m, alle) {
    const s = status(m, alle);
    const bald = R.art(m) === 'bald';
    const inhalt = `<span class="db-ico" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>
      <span class="db-text"><span class="db-name">${esc(m.name)}</span><span class="db-badge ${s.cls}${s.cls === 'ok' ? ' sr-only' : ''}">${esc(s.text)}</span>
      ${s.hinweis ? `<span class="db-hint">${esc(s.hinweis)}</span>` : ''}</span>
      ${bald ? '<span class="r-bald" aria-hidden="true">Bald</span>' : ''}`;
    return m.kachel.zugang
      ? `<a class="db-tile" role="listitem" data-modul="${esc(m.id)}" href="${esc(R.ziel(m.kachel, alle, location.hostname))}">${inhalt}</a>`
      : `<div class="db-tile off${bald ? ' gesperrt' : ''}" role="listitem" data-modul="${esc(m.id)}" aria-disabled="true">${inhalt}</div>`;
  }

  function render(module) {
    const alle = Object.fromEntries(module.map((m) => [m.id, m]));
    // Kacheln ohne Modulzugang der Rolle erscheinen nicht (recht: false) – die Sperre selbst setzt der Server durch
    const kacheln = R.sichtbar(module);
    // Bereiche aus dem Register (dashboard_gruppe): Fachanwendungen oben, „Verwaltung & Daten“ darunter
    const verw = kacheln.filter((m) => m.gruppe === 'verwaltung'), apps = kacheln.filter((m) => m.gruppe !== 'verwaltung');
    $('#db-grid').innerHTML = apps.map((m) => kachel(m, alle)).join('');
    $('#db-grid-verwaltung').innerHTML = verw.map((m) => kachel(m, alle)).join('');
    $('#db-verwaltung').hidden = !verw.length;
    if (!kacheln.length) $('#db-grid').innerHTML = '<p class="db-leer" role="listitem">Für Ihre Rolle ist noch keine Anwendung freigegeben. Bitte an einen Administrator wenden.</p>';
    const frei = kacheln.filter((m) => m.kachel.zugang).length;
    $('#db-sub').textContent = `${frei} von ${kacheln.length} Anwendungen für Sie verfügbar`;
    einpassen();
  }

  /* Lange Kachelnamen (Registernamen wie „Qualitätssicherung“, „Container-Import“) nicht mitten im Wort trennen: Schrift in halben Pixeln
     verkleinern, bis das längste Wort in die Kachel passt – höchstens auf drei Viertel der Grundgröße. Reicht das
     nicht, darf das Wort als Notlösung umbrechen (Klasse db-name-umbruch), statt über die Kachel hinauszuragen. */
  /* true, wenn ein Wort über zwei Zeilen läuft – auch am Bindestrich („Container-Import“), den der Browser sonst trennt */
  function wortGebrochen(el) {
    const t = el.firstChild;
    if (!t || t.nodeType !== 3) return false;
    for (const m of t.textContent.matchAll(/\S+/g)) {
      const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
      if (new Set([...r.getClientRects()].map((q) => Math.round(q.top))).size > 1) return true;
    }
    return false;
  }
  function namenEinpassen() {
    for (const el of document.querySelectorAll('#db-bereich .db-name')) {
      el.style.fontSize = ''; el.classList.remove('db-name-umbruch');
      const basis = parseFloat(getComputedStyle(el).fontSize), min = Math.max(12, basis * .75);
      const zuBreit = () => el.scrollWidth > el.clientWidth + 1 || wortGebrochen(el);
      let g = basis;
      while (zuBreit() && g > min) { g = Math.max(min, g - .5); el.style.fontSize = g + 'px'; }
      if (zuBreit()) el.classList.add('db-name-umbruch');
    }
  }

  let breite = 0;
  function einpassen() { breite = $('#db-grid').clientWidth; namenEinpassen(); }
  // Neu einpassen, wenn sich die Breite ändert (Fenster, Drehen) und sobald die Schrift geladen ist
  new ResizeObserver(() => { if ($('#db-grid').clientWidth !== breite && $('#db-grid .db-tile')) einpassen(); }).observe($('#db-grid'));
  if (document.fonts) document.fonts.ready.then(() => { if ($('#db-grid .db-tile')) einpassen(); });

  /* Begrüßung nach Tageszeit (Uhr des Geräts) mit Vornamen und Datum, z. B. „Guten Tag, Erika“ · „Donnerstag, 22. Oktober“ */
  function gruss(stunde) {
    if (stunde >= 5 && stunde < 11) return 'Guten Morgen';
    if (stunde >= 11 && stunde < 18) return 'Guten Tag';
    return 'Guten Abend';
  }
  window.STAFL_GRUSS = gruss;   // für die Tests (reine Funktion)
  /* Vorname = erster Namensteil ohne Titel („Dr. Erika Editor“ → „Erika“); ohne Namen nur der Gruß */
  function vorname(name) {
    return String(name || '').trim().split(/\s+/).find((t) => t && !t.endsWith('.')) || '';
  }
  function begruessung(name) {
    const jetzt = new Date(), v = vorname(name);
    $('#db-datum').textContent = jetzt.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    $('#db-titel').textContent = gruss(jetzt.getHours()) + (v ? `, ${v}` : '');
  }

  function fehler(text) {
    R.entfernen();
    $('#db-login').hidden = true; $('#db-bereich').hidden = true;
    $('#db-err').hidden = false; $('#db-err').textContent = text;
  }

  function zeigeAnmeldung(ziel) {
    R.entfernen();
    if (ziel) $('#db-login a').setAttribute('href', ziel);
    $('#db-login').hidden = false; $('#db-bereich').hidden = true;
  }

  async function abmelden() {
    const r = await api('logout', {});
    // Zentrale Anmeldung (Keycloak-Host): auch bei Keycloak abmelden – beendet die Anmeldung für alle Anwendungen
    if (typeof r.data.abmelden === 'string' && r.data.abmelden.startsWith('/oidc/')) { location.replace(r.data.abmelden); return; }
    zeigeAnmeldung();
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
    const nutzer = st.data.user || {};
    const r = await api('module_status');
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(r.data.error || `Die Anwendungen konnten nicht geladen werden (${r.status}).`); return; }
    $('#db-login').hidden = true; $('#db-bereich').hidden = false;
    R.zeichnen({ module: r.data.module || [], aktiv: 'start', nutzer, start: './', abmelden });
    begruessung(nutzer.name || nutzer.username || '');
    notfallHinweis(r.data.notfall);
    render(r.data.module || []);
  }

  /* Notfallmodus (Modul Sicherheit): Hinweis über den Kacheln – Einzelheiten nur für Administratoren und Berechtigte */
  function notfallHinweis(n) {
    const el = $('#db-notfall');
    el.hidden = !n;
    if (!n) return;
    const seit = new Date(n.seit).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    el.innerHTML = n.grund !== undefined
      ? `<strong>Notfallmodus aktiv</strong> seit ${esc(seit)} Uhr${n.von ? ` · ausgelöst von ${esc(n.von)}` : ''}. Kunden sehen Wartung, Mitarbeiter ohne Administratorrolle sind gesperrt.`
      : '<strong>Anwendungen vorübergehend gesperrt.</strong> Wegen einer Sicherheitsmaßnahme ist der Zugriff gerade nicht möglich. Bitte wenden Sie sich an einen Administrator.';
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
  /* Einfache Darstellung (theme.js): an/aus, gespeichert am Konto; Hinweis unter der Begrüßung, solange sie an ist */
  function darstellungKnopf() {
    const D = window.STAFL_DARSTELLUNG, b = $('#db-darstellung');
    if (!D) { b.hidden = true; return; }
    const an = D.einfach();
    b.setAttribute('aria-pressed', String(an));
    b.setAttribute('aria-label', an ? 'Einfache Darstellung ausschalten' : 'Einfache Darstellung einschalten (für Remote-Desktop)');
    b.title = an ? 'Einfache Darstellung ist an – Effekte wieder einschalten' : 'Einfache Darstellung für Remote-Desktop einschalten';
    const h = $('#db-darstellung-hinweis');
    h.hidden = !an;
    h.textContent = !an ? '' : D.wahl() === 'einfach' ? 'Einfache Darstellung ist an (Ihre Wahl) – ruhiger und flüssiger, z. B. über Remote-Desktop.'
      : 'Einfache Darstellung ist an – automatisch, weil dieser Computer ohne Grafikkarte zeichnet (z. B. Remote-Desktop).';
  }
  $('#db-darstellung').addEventListener('click', () => {
    const neu = !window.STAFL_DARSTELLUNG.einfach();
    if (window.STAFL_THEME) window.STAFL_THEME.darstellung(neu); else window.STAFL_DARSTELLUNG.setzen(neu);
    darstellungKnopf();
  });
  document.addEventListener('stafl-darstellung', darstellungKnopf);

  themaKnopf();
  darstellungKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
